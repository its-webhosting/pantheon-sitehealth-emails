
import os
import sys
import json
import time
import tempfile

import cloudflare  # for cloudflare.CloudflareError
import rich.progress

import script_context as sc


# ---------------------------------------------------------------------------------------------
# Move the old standalone `get_proxied_fqdns` here, as a Cloudflare-plugin setup hook.
#
# `fqdns.json` maps every Cloudflare-*proxied* website FQDN to the zone it lives in and its DNS
# origins:  { "<fqdn>": { "zone_id": "<uuid>", "origins": [ "<ip-or-cname>", ... ] }, ... }
# The main program consumes only the KEYS (a membership test: "is this hostname proxied?"); the
# zone_id is stored for a near-future feature and is not read yet.
#
# The whole flow runs ONCE in a setup hook, before the per-site loop:
#   decide whether to refresh -> (maybe) fetch from Cloudflare + write fqdns.json -> load it into
#   sc.plugin_context['plugin.cloudflare']['proxied_fqdns'].
# ---------------------------------------------------------------------------------------------


FQDNS_FILE = "fqdns.json"
STALE_SECONDS = 24 * 60 * 60  # 86400 -- a day


class CloudflareFqdnsError(Exception):
    """A failure while fetching proxied FQDNs from Cloudflare (always fatal)."""


def progress_bar() -> rich.progress.Progress:
    # Ported from the standalone get_proxied_fqdns.
    return rich.progress.Progress(
        rich.progress.TextColumn("[progress.description]{task.description}"),
        rich.progress.MofNCompleteColumn(),
        rich.progress.BarColumn(),
        rich.progress.TaskProgressColumn(),
        rich.progress.TimeElapsedColumn(),
        rich.progress.TimeRemainingColumn(),
        console=sc.console,
        transient=False if sc.options.verbose else True,
    )


def decide_fqdns_update(*, exists, age_seconds, multi_site, force, suppress, traffic_only):
    """Pure decision: should we refresh fqdns.json?  Returns (should_update, reason).  No I/O.

    Order matters:
      - an explicit --update-cloudflare-fqdns forces a refresh (even in non-consuming runs);
      - runs that never consume fqdns (--update / --import-older-metrics / --create-tables) skip
        the refresh -- passed in as `traffic_only`;
      - a missing file must be fetched (any run that reaches consumption needs it);
      - otherwise refresh only a stale file when processing multiple sites and not suppressed.
    """
    if force:
        return True, "--update-cloudflare-fqdns requested"
    if traffic_only:
        return False, "run does not consume fqdns (--update/--import-older-metrics/--create-tables)"
    if not exists:
        return True, "fqdns.json does not exist"
    if age_seconds > STALE_SECONDS and multi_site and not suppress:
        return True, "fqdns.json older than 24h and processing multiple sites"
    return False, "fqdns.json present (fresh, single-site, or update suppressed)"


def fetch_proxied_fqdns(client) -> tuple:
    """Query Cloudflare for every proxied FQDN across every account/zone the credentials can see.

    Returns (websites, conflicts) where:
      websites  = { "<fqdn>": { "zone_id": "<uuid>", "origins": [ "<content>", ... ] }, ... }
      conflicts = { "<fqdn>": [ "<zone_id>", ... ] } for any FQDN proxied in more than one zone
                  (the file stores only the first zone_id, so this is surfaced to owners live).
    Any Cloudflare API error becomes CloudflareFqdnsError (fatal).  Zero zones is treated as a
    (fatal) scope/permission problem; zero proxied FQDNs across present zones is a loud warning
    but not fatal (a DNS-only Cloudflare org is legitimate).
    """
    try:
        with sc.console.status('[bold green]Getting Cloudflare accounts and zones ...'):
            accounts = list(client.accounts.list())
            account_count = len(accounts)
            zones = []
            for account in accounts:
                zones.extend(client.zones.list(account={'id': account.id}))
        zone_count = len(zones)
    except cloudflare.CloudflareError as e:
        raise CloudflareFqdnsError(f'listing accounts/zones failed: {e}') from e

    # Deliberate raise placed OUTSIDE the try above so it is never re-wrapped/swallowed.
    if zone_count == 0:
        raise CloudflareFqdnsError(
            f'Cloudflare returned {account_count} account(s) but 0 zones -- '
            'the credentials likely lack DNS:Read for the zones.'
        )

    websites = {}
    conflicts = {}
    blank = ' '
    try:
        with progress_bar() as progress:
            zone_task = progress.add_task(f'Checking zone:  {blank:32s}', total=zone_count)
            for zone in zones:
                progress.update(zone_task, description=f'Checking zone:  {zone.name:32s}', advance=1)
                for record in client.dns.records.list(zone_id=zone.id, proxied=True):
                    name = record.name
                    content = record.content
                    if name not in websites:
                        websites[name] = {'zone_id': zone.id, 'origins': [content]}
                    else:
                        websites[name]['origins'].append(content)
                        if websites[name]['zone_id'] != zone.id:
                            zone_ids = conflicts.setdefault(name, [websites[name]['zone_id']])
                            if zone.id not in zone_ids:
                                zone_ids.append(zone.id)
                            sc.console.print(
                                f":exclamation: [bold red] ATTENTION: {name} appears in more than "
                                f"one Cloudflare zone ({websites[name]['zone_id']} and {zone.id}); "
                                "keeping the first zone_id"
                            )
    except cloudflare.CloudflareError as e:
        raise CloudflareFqdnsError(f'listing DNS records failed: {e}') from e

    fqdn_count = len(websites)
    sc.console.print(
        f"[bold green]Fetched {fqdn_count} proxied FQDNs across {zone_count} zones "
        f"in {account_count} account(s)."
    )
    if fqdn_count == 0:
        sc.console.print(
            ":exclamation: [bold red] ATTENTION: Cloudflare returned zero proxied FQDNs across "
            f"{zone_count} zones -- every custom domain will be reported as not proxied."
        )
    return websites, conflicts


def _load_existing(path) -> dict:
    """Load an existing fqdns.json.  Missing -> {} (only reachable on the traffic-only skip).
    Invalid JSON -> fatal.  Tolerates both the old array-value and new object-value formats
    (the program reads only the keys)."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        sys.exit(f"ERROR: {path} is not valid JSON; run --update-cloudflare-fqdns to regenerate it.")


def write_fqdns_atomic(path, data) -> None:
    """Write data as JSON to a temp file in the same directory, then os.replace() it onto `path`.

    Atomic: an interrupted write never leaves a half-written or truncated fqdns.json.  Replacing
    onto a symlink path replaces the symlink itself with the new plain file.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".fqdns-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=4, sort_keys=True)
            f.write("\n")
        # mkstemp creates the temp file mode 0600, which os.replace would preserve; restore a
        # normal umask-based mode (typically 0644) so other readers keep the access they had on
        # the previous fqdns.json.
        current_umask = os.umask(0)
        os.umask(current_umask)
        os.chmod(tmp, 0o666 & ~current_umask)
        os.replace(tmp, path)
    except BaseException:  # incl. KeyboardInterrupt: clean up the temp file, leave fqdns.json intact
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def update_and_load_proxied_fqdns() -> None:
    """setup hook: refresh fqdns.json from Cloudflare when appropriate, then load it into
    sc.plugin_context['plugin.cloudflare']['proxied_fqdns'] for the per-site loop to consume."""
    exists = os.path.exists(FQDNS_FILE)
    age_seconds = (time.time() - os.path.getmtime(FQDNS_FILE)) if exists else 0
    multi_site = sc.options.all or len(sc.options.sites) > 1
    force = sc.options.update_cloudflare_fqdns
    suppress = sc.options.no_update_cloudflare_fqdns
    # Run modes that never reach the per-site fqdns consumption: traffic-only refreshes
    # (--update / --import-older-metrics) AND schema creation (--create-tables, which exits before
    # the per-site loop).  Setup hooks run before all of these, so without this skip a bare
    # --create-tables would trigger a full live Cloudflare crawl (and a Cloudflare error would
    # abort table creation).  `force` still overrides, so --update-cloudflare-fqdns works anywhere.
    does_not_consume = (
        sc.options.update or sc.options.import_older_metrics or sc.options.create_tables
    )

    should_update, reason = decide_fqdns_update(
        exists=exists,
        age_seconds=age_seconds,
        multi_site=multi_site,
        force=force,
        suppress=suppress,
        traffic_only=does_not_consume,
    )
    sc.debug(f"Cloudflare fqdns update decision: {should_update} ({reason})")

    conflicts = {}
    if should_update:
        sc.console.print(f"[bold green]Updating {FQDNS_FILE} from Cloudflare ({reason}) ...")
        client = sc.plugin_context["plugin.cloudflare"]["get_client"]()  # the one shared instance
        try:
            proxied, conflicts = fetch_proxied_fqdns(client)
        except CloudflareFqdnsError as e:
            sys.exit(f"ERROR: could not fetch proxied FQDNs from Cloudflare: {e}")
        write_fqdns_atomic(FQDNS_FILE, proxied)
        sc.console.print(f"[bold green]Wrote {len(proxied)} proxied FQDNs to {FQDNS_FILE}.")
    else:
        # Only warn about staleness when the file will actually be consumed (not a
        # traffic-only / create-tables run, which never reads it).
        if not does_not_consume and exists and age_seconds > STALE_SECONDS:
            sc.console.print(
                f":exclamation: [bold red] ATTENTION: {FQDNS_FILE} is more than a day old!"
            )
        proxied = _load_existing(FQDNS_FILE)

    sc.plugin_context["plugin.cloudflare"]["proxied_fqdns"] = proxied
    # Cross-zone conflicts are only known on a fresh fetch (the file stores a single zone_id per
    # FQDN); {} on a load-only run.  Consumed per-site to warn owners.
    sc.plugin_context["plugin.cloudflare"]["fqdn_zone_conflicts"] = conflicts

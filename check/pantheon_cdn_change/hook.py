"""site_post_dns hook for the Pantheon CDN-change check.

Owns the two run-time decisions the pure modules cannot make: which detection sources are
available (sc.cloudflare_enabled + the plugin.cloudflare bag), and which copy variant applies
(sc.umich_enabled + the cutoff).

There is deliberately NO fqdns.json staleness warning here.  The plugin already warns, once per
run, exactly when the file is stale and the run will consume it (plugin/cloudflare/fqdns.py
:219-223), and a missing file on a consuming run is auto-refreshed (decide_fqdns_update:64).  A
per-site copy of that warning -- and the module-level "already warned" flag it would need -- was
designed, reviewed, and cut.  Do not reintroduce it.
"""
import datetime

from rich.markup import escape as rich_escape

import script_context as sc

from .detect import find_findings
from .notices import cdn_change_notice

# The ONE dated constant in this feature.  TWO future edits are expected:
#   (a) once the ITS maintenance is scheduled, change this date to the real one;
#   (b) once that date has passed, DELETE this constant, today(), the before_cutoff argument,
#       and the U-M branch of cdn_change_notice() -- leaving only the generic copy.
# The date itself is NEVER shown to site owners; it only selects the copy variant.
UMICH_MAINTENANCE_CUTOFF = datetime.date(2026, 9, 15)


def today() -> datetime.date:
    """The one date seam: tests monkeypatch hook.today so the copy variant is deterministic."""
    return datetime.date.today()


def check_pantheon_cdn_change(site_context) -> None:
    site = site_context["site"]
    site_name = site["name"]
    # site["id"] is a UUID -- it is what terminus needs (core builds live_site the same way,
    # pantheon-sitehealth-emails:1540).  site["name"] is what the operator reads.
    site_id = site["id"]

    cloudflare_on = sc.cloudflare_enabled()
    # .get chains: a run without the Cloudflare plugin bag must not KeyError (F6).
    proxied_fqdns = {}
    if cloudflare_on:
        proxied_fqdns = sc.plugin_context.get("plugin.cloudflare", {}).get("proxied_fqdns") or {}

    findings = find_findings(
        site_id, site_name, site_context["custom_domains"], proxied_fqdns, cloudflare_on)
    if not findings:
        return

    # Verbosity 0 (SPEC §9): -notices.csv is only written under --all, so on a single-site run the
    # console is the operator's only channel.  Every other DNS/Cloudflare problem in this codebase
    # announces itself here; this one does too.  rich_escape even though Pantheon site names are
    # [a-z0-9-]: the rule is "escape every remote string", so nobody has to re-derive that.
    sc.console.print(
        f":exclamation: [bold red] ATTENTION: {rich_escape(str(site_name))} has "
        f"{len(findings)} custom domain(s) still CNAME'd to the legacy Pantheon GCDN")

    site_context.add_notice(cdn_change_notice(
        site_name,
        findings,
        umich=sc.umich_enabled(),
        before_cutoff=today() < UMICH_MAINTENANCE_CUTOFF,
    ))

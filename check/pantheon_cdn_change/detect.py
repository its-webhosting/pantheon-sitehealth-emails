"""Findings for the Pantheon CDN-change check: which custom domains still reach the legacy
Pantheon GCDN (Fastly) through a CNAME record, and what Pantheon says to use instead.

DETECTION -- two independent, NON-redundant sources per custom domain (SPEC §2):

  (1) PUBLIC DNS         walk the CNAME chain from the FQDN itself.  The ONLY source that can see
                         an unproxied (grey-cloud) Cloudflare CNAME.
  (2) CLOUDFLARE ORIGINS the `origins` of the FQDN's Cloudflare-PROXIED records, already fetched
                         into fqdns.json by plugin/cloudflare/fqdns.py.  The ONLY source that can
                         see a proxied FQDN's CNAME -- public DNS shows only
                         *.cdn.cloudflare.net -> Cloudflare anycast addresses.

REQUIRED RECORDS -- from Pantheon, per domain, ONE lazy `terminus domain:dns` call for the whole
site, made only if detection found at least one candidate (a clean site costs nothing on --all).
NEVER by resolving the legacy-GCDN name: a stale target belongs to a DIFFERENT Pantheon site and
we would email its addresses to the wrong owner (SPEC §4.1).

If the two sources reach DIFFERENT legacy names (F11), that is one row -- Pantheon's answer is
correct for both records -- plus an operator ATTENTION, because the disagreement itself means
something on the site is misconfigured.
"""
from rich.markup import escape as rich_escape

import script_context as sc

from . import chain, pantheon
from .model import Finding

# Characters that would corrupt -notices.csv, which is split/re-joined on commas with NO escaping
# (pantheon-sitehealth-emails:3924-3926).  fqdn_re rejects a comma but its `$` accepts a trailing
# newline, so reject these explicitly rather than trusting the regex (F13).
CSV_HOSTILE = (",", "\r", "\n")


def is_safe_domain_id(fqdn: str) -> bool:
    """True when the id is safe to resolve, display, and write to the CSV (F13).

    NOT a DNS-validity check: fqdn_re ACCEPTS `a..b` (that case is F10's -- dns_classify.resolve
    raises the named MalformedNameError and chain.walk swallows it).  This guards ONE thing: a
    remote domain id must not be able to inject a column break into the ITS work list.
    """
    text = str(fqdn)
    if any(bad in text for bad in CSV_HOSTILE):
        return False
    return bool(sc.fqdn_re.match(text))


def cloudflare_origins(fqdn: str, proxied_fqdns: dict) -> list:
    """The proxied-record origins for `fqdn` from fqdns.json.

    Tolerates BOTH file formats (CLAUDE.md): the current object form
    {"fqdn": {"zone_id": ..., "origins": [...]}} and the legacy bare-array form
    {"fqdn": ["origin", ...]}.  Anything else -> [] (never a KeyError, never a TypeError).
    fqdns.json keys are Cloudflare-normalized (lowercase, no trailing dot), so the lookup
    normalizes too.
    """
    entry = (proxied_fqdns or {}).get(chain.normalize(fqdn))
    if isinstance(entry, dict):
        origins = entry.get("origins")
        if not isinstance(origins, list):
            origins = []
    elif isinstance(entry, list):
        origins = entry
    else:
        origins = []
    return [str(origin) for origin in origins]


def _cloudflare_target(fqdn: str, proxied_fqdns: dict) -> str:
    """The first legacy-GCDN name reached from any of the FQDN's Cloudflare origins ("" = none)."""
    for origin in cloudflare_origins(fqdn, proxied_fqdns):
        if not chain.is_hostname(origin):          # a proxied A/AAAA record's IP literal (F8)
            continue
        sc.debug(f"{rich_escape(str(fqdn))} has Cloudflare origin {rich_escape(origin)}", level=2)
        result = chain.walk(origin)
        if result.target:
            return result.target
    return ""


def _candidates(custom_domains: list, proxied_fqdns: dict, cloudflare_on: bool) -> list:
    """[(fqdn, where, target)] in custom_domains order -- detection only, no Pantheon call."""
    found = []
    for fqdn in custom_domains or []:
        if not is_safe_domain_id(fqdn):
            sc.debug(f"skipping invalid domain id {rich_escape(str(fqdn))}")
            continue

        sc.debug(f"checking {rich_escape(str(fqdn))} for legacy-GCDN CNAMEs")
        dns_target = chain.walk(fqdn).target       # transient/malformed -> "" -> never a finding
        cloudflare_target = _cloudflare_target(fqdn, proxied_fqdns) if cloudflare_on else ""

        if not dns_target and not cloudflare_target:
            continue

        if dns_target and cloudflare_target:
            if dns_target != cloudflare_target:
                # F11.  ONE row (Pantheon's records are right for both), but the operator needs to
                # know the two records point at different Pantheon sites.
                sc.console.print(
                    f":exclamation: [bold red] ATTENTION: {rich_escape(str(fqdn))} reaches "
                    f"DIFFERENT legacy-GCDN names in DNS ({rich_escape(dns_target)}) and "
                    f"Cloudflare ({rich_escape(cloudflare_target)}) -- the records disagree; "
                    "check the site")
            where = "both"
        elif dns_target:
            where = "dns"
        else:
            where = "cloudflare"

        target = dns_target or cloudflare_target
        sc.debug(f"{rich_escape(str(fqdn))} reaches {rich_escape(target)} via {where}")
        found.append((fqdn, where, target))
    return found


def find_findings(site_id: str, site_name: str, custom_domains: list, proxied_fqdns: dict,
                   cloudflare_on: bool) -> list:
    """Detect candidates, then enrich them with Pantheon's required records (lazily).

    site_id is the UUID the terminus command needs; site_name is what operator messages print.
    """
    candidates = _candidates(custom_domains, proxied_fqdns, cloudflare_on)
    if not candidates:
        return []      # a clean site issues NO domain:dns call

    required = pantheon.required_records(site_id, site_name)   # {} on failure -- never fatal (F4)
    findings = []
    for fqdn, where, target in candidates:
        records = required.get(chain.normalize(fqdn), pantheon.EMPTY)
        if records is pantheon.EMPTY and required:
            # The call succeeded (required is non-empty) but Pantheon's answer has no row for
            # THIS fqdn -- as opposed to a total call failure, which already prints its own
            # ATTENTION in pantheon.required_records (a second line per domain there would be
            # noise).  Without this, the owner is silently emailed "unavailable" and the operator
            # never finds out.
            sc.console.print(
                ":exclamation: [bold red] ATTENTION: Pantheon returned no required records for "
                f"{rich_escape(str(fqdn))} -- the owner will be told they are unavailable")
        if not records.a and not records.aaaa and records.cname:
            # F14: an already-migrated site -- Pantheon requires a CNAME, not addresses.  This is
            # an ANSWER, not a failure; say so, and let the notice show what Pantheon requires.
            sc.console.print(
                ":exclamation: [bold red] ATTENTION: Pantheon requires no A/AAAA for "
                f"{rich_escape(str(fqdn))} -- it requires CNAME "
                f"{rich_escape(', '.join(records.cname))}; the site may already be on the new "
                "GCDN Beta")
        findings.append(
            Finding(fqdn, where, target, records.a, records.aaaa, records.cname))
    return findings

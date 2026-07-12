"""Pantheon's AUTHORITATIVE required records for a site's custom domains (domain:dns).

Why not resolve the legacy-GCDN name ourselves (SPEC §4.1): when a record points at a STALE
legacy name -- the site was renamed on Pantheon, a Cloudflare origin was never updated, a domain
moved between sites -- that name belongs to a DIFFERENT Pantheon site, and resolving it returns
THAT site's edge addresses.  Publishing them to an owner would be confidently wrong.  Pantheon
answers per-domain, is never stale, and auto-follows its own migration.

Why terminus and not the Pantheon API: the API has the same endpoint
(GET /v0/sites/{id}/environments/{env}/domains/dns), and CLAUDE.md prefers the API for new code
-- but the script has NO API client.  Building machine-token -> session-token auth, a session
cache, an HTTP seam and new fixtures, for a check that gets deleted after the migration, is not
worth it; terminus() is the established wrapper and run_terminus() is the harness's mock seam, so
this rides the existing offline test machinery.  CLAUDE.md allows terminus when it is
"significantly simpler" -- it is.  When the API client is built, this module is a one-function swap.

Shape of `terminus domain:dns <site>.live --format=json` (both verified live, 2026-07-12):

    NOT migrated (bus-occb):
      {"domain": "occb.bus.umich.edu", "type": "A",     "value": "23.185.0.4",  ...}
      {"domain": "occb.bus.umich.edu", "type": "AAAA",  "value": "2620:12a:8000::4", ...}
      {"domain": "occb.bus.umich.edu", "type": "CNAME", "value": "",            # <- no requirement
       "detected_value": "live-bus-occb.pantheonsite.io", "status_message": "Remove this detected record"}

    ALREADY migrated (its-wws-test1) -- CNAME only, NO A/AAAA rows:
      {"domain": "wws-test1.cdn-dev.it.umich.edu", "type": "CNAME",
       "value": "fe.cfp2c.edge.pantheon.io", "status": "okay", ...}

A row with an empty `value` states no requirement and is skipped.  Everything else -- A, AAAA and
CNAME -- is kept: the CNAME-only answer is F14, an ANSWER rather than a failure, and it must stay
distinguishable from {} (which is what a terminus failure returns).
"""
from typing import NamedTuple

from rich.markup import escape as rich_escape

import script_context as sc

from . import chain


class Required(NamedTuple):
    a: list            # Pantheon's required A records,     IN PANTHEON'S ORDER
    aaaa: list         # Pantheon's required AAAA records,  IN PANTHEON'S ORDER
    cname: list        # Pantheon's required CNAME values (an already-migrated site -- F14)


# The "Pantheon said nothing about this domain" answer (F4).  It is a SHARED instance handed out
# as a default, so it is READ-ONLY by contract: never mutate EMPTY's lists.  Lists (not tuples)
# deliberately -- every other Required carries lists, and a mixed-type field would make
# `finding.a == []` false for exactly this case, which is the one the notice renders specially.
EMPTY = Required([], [], [])


def required_records(site_id: str, site_name: str = "") -> dict:
    """{normalized fqdn: Required} for the site's LIVE environment.

    `site_id` is what the command needs (it is a UUID in production -- core builds live_site the
    same way, pantheon-sitehealth-emails:1540).  `site_name` is for the OPERATOR message: an
    ATTENTION reading "could not fetch ... for 9cf2c790-..." is not actionable.

    NEVER fatal: this is an enrichment call.  A terminus failure, an undecodable result, or a
    malformed row yields {} (or simply omits that domain) plus a console ATTENTION -- the caller
    still reports every finding, with the records shown as "unavailable" (F4).  A missing record
    must never hide a CNAME that has to be fixed.

    Records are NEVER re-sorted (a sort key over remote strings is a crash class; Pantheon's own
    order is deterministic and is what its dashboard shows).
    """
    label = site_name or site_id
    rows, errors, fatal = sc.terminus("domain:dns", f"{site_id}.live")
    if fatal or rows is None:
        sc.console.print(
            ":exclamation: [bold red] ATTENTION: could not fetch Pantheon's required DNS "
            f"records for {rich_escape(str(label))}: {rich_escape(str(errors))}")
        return {}
    if not isinstance(rows, list):
        sc.console.print(
            ":exclamation: [bold red] ATTENTION: unexpected domain:dns result for "
            f"{rich_escape(str(label))} (expected a list, got {type(rows).__name__})")
        return {}

    buckets = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_domain = row.get("domain")
        # A JSON `null` (or any other non-string) is ABSENT, not the literal string "None" --
        # str(None) == "None" would pass the truthiness check below and publish a fabricated key.
        domain = chain.normalize(raw_domain) if isinstance(raw_domain, str) else ""
        rrtype = row.get("type")
        raw_value = row.get("value")
        value = raw_value.strip() if isinstance(raw_value, str) else ""
        if not domain or not value or rrtype not in ("A", "AAAA", "CNAME"):
            continue          # an empty `value` ("Remove this detected record") is no requirement
        buckets.setdefault(domain, {"A": [], "AAAA": [], "CNAME": []})[rrtype].append(value)

    records = {d: Required(v["A"], v["AAAA"], v["CNAME"]) for d, v in buckets.items()}
    if not records:
        # The call SUCCEEDED but nothing usable came back -- an empty list, or rows whose shape
        # changed (a renamed key, every `value` empty).  Without this line the failure is totally
        # silent: the three guards above only print for fatal/None/non-list, and the caller's
        # per-domain warning is skipped because it cannot tell {} apart from "call failed".  Every
        # affected owner would then be emailed "unavailable" while the run reports success.
        sc.console.print(
            ":exclamation: [bold red] ATTENTION: Pantheon's domain:dns answer for "
            f"{rich_escape(str(label))} contained no usable records "
            f"({len(rows)} row(s) returned) -- owners will be told the records are unavailable")
    sc.debug(
        f"Pantheon requires records for {len(records)} domain(s) of {rich_escape(str(label))}",
        level=2)
    return records

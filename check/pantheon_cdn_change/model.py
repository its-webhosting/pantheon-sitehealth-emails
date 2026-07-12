"""The Finding NamedTuple: the one type shared by detect.py (which produces them) and
notices.py (which renders them).

It lives in its own module so notices.py stays PURE -- importing it from detect.py would drag
chain.py and dnspython into the notice builder for no reason.
"""
from typing import NamedTuple


class Finding(NamedTuple):
    fqdn: str          # the site's custom domain (CSV-safe: see detect.is_safe_domain_id, F13)
    where: str         # machine value: "dns" | "cloudflare" | "both"  (canonical -- SPEC §5)
    target: str        # the legacy-GCDN name the record's chain reaches (operator context only)
    a: list            # Pantheon's required A records     -- all three empty when domain:dns
    aaaa: list         # Pantheon's required AAAA records     failed or had no row (F4)
    cname: list        # Pantheon's required CNAME values  -- non-empty only for a site already
                       #                                      on the new GCDN Beta (F14)

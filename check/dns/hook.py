# check/dns/hook.py
"""site_post_dns hook: build DNS-resolution notices from the contract facts.

Emission order: the aggregated transient warning FIRST, then the three Cloudflare notices (each
from its own independent guard — bug #1 fix), then not-in-dns. Transient-first keeps a
warning-only site's email subject as "DNS lookup failed (transient)" (the renderer takes the
subject from the first notice after a type sort), matching the pre-refactor loop. See design §7
note (b) for the one accepted residual (an enabled Cloudflare-cache check's warnings now precede
the transient notice).
"""
import script_context as sc

from .notices import (behind_cloudflare_not_proxied_notice, not_behind_cloudflare_notice,
                      not_in_dns_notice, proxied_in_multiple_zones_notice, transient_notice)


def emit_dns_notices(site_context) -> None:
    umich = sc.umich_enabled()
    site = site_context["site"]["name"]

    if site_context["dns_transient"]:
        site_context.add_notice(transient_notice(site, site_context["dns_transient"]))

    if sc.cloudflare_enabled():
        if site_context["fqdns_not_behind_cloudflare"]:
            site_context.add_notice(not_behind_cloudflare_notice(
                site, site_context["fqdns_not_behind_cloudflare"], umich=umich))
        if site_context["behind_cloudflare_not_proxied"]:
            site_context.add_notice(behind_cloudflare_not_proxied_notice(
                site, site_context["behind_cloudflare_not_proxied"], umich=umich))
        if site_context["proxied_in_multiple_zones"]:
            site_context.add_notice(proxied_in_multiple_zones_notice(
                site, site_context["proxied_in_multiple_zones"]))

    if site_context["not_in_dns"]:
        site_context.add_notice(not_in_dns_notice(site, site_context["not_in_dns"]))

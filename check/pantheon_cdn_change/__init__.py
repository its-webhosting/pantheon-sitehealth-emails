"""Pantheon CDN-change check (site_post_dns): custom domains that still reach the legacy
Pantheon GCDN (Fastly) through a CNAME record, in public DNS or in Cloudflare.

TEMPORARY.  Delete this whole package (`git rm -r check/pantheon_cdn_change` plus its tests)
once Pantheon's migration to the new GCDN Beta is complete.  See docs/pantheon-cdn-change.md.

Registers UNCONDITIONALLY (like check/dns): every site this tool reports on is a Pantheon site,
so the check always applies.  The Cloudflare-origins source self-gates on sc.cloudflare_enabled(),
so an institution with no Cloudflare still gets the public-DNS half.
"""
import script_context as sc

from .hook import check_pantheon_cdn_change

sc.add_hook('site_post_dns',
            {'name': 'check.pantheon_cdn_change.hook.check_pantheon_cdn_change',
             'func': check_pantheon_cdn_change})


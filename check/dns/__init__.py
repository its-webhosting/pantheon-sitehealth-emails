"""Site-level DNS-resolution notices (site_post_dns).

Registers unconditionally: DNS checks are not disable-able.  The three Cloudflare notices
self-gate on sc.cloudflare_enabled(); U-M wording is chosen via sc.umich_enabled().  The
resolution FACTS are produced by dns_classify.classify_domains() in core before the phase
fires (see docs/superpowers/specs/2026-07-10-modular-dns-checks-design.md).
"""
import script_context as sc

from .hook import emit_dns_notices

sc.add_hook('site_post_dns', {'name': 'check.dns.hook.emit_dns_notices',
                              'func': emit_dns_notices})

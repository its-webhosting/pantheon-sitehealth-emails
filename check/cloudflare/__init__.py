"""Cloudflare cache-configuration checks ([Cloudflare.cachecheck], opt-in).

Registers (when [Cloudflare].enabled AND [Cloudflare.cachecheck].enabled):
  - setup:          egress-IP allowlist check (once per run, report paths only)
  - site_post_dns:  per-FQDN page/asset cache-header checks

See docs/cloudflare-cachecheck.md and CLAUDE.md ("Per-site report pipeline").
"""

import sys

import script_context as sc

_cf = sc.config.get('Cloudflare', {})
_cachecheck = _cf.get('cachecheck', {})
if _cf.get('enabled') and isinstance(_cachecheck, dict) and _cachecheck.get('enabled'):
    try:
        from .egress import check_egress_ip
        from .cache import check_cloudflare_cache
    except ImportError as e:
        if e.name and e.name.startswith(__name__):
            # A bug inside this package (e.g. a typo'd relative import), not a missing
            # third-party dependency -- show the real traceback instead of the
            # misleading install hint below.
            raise
        sc.console.print(
            f"[bold red]ERROR: \\[Cloudflare.cachecheck] is enabled but the Python package "
            f"'{e.name}' is not installed.  Install this check's dependencies with:\n"
            f"    uv pip install .\\[cloudflare]"
        )
        sys.exit(1)
    from .cfg import validate_cachecheck_config
    validate_cachecheck_config()
    sc.add_hook('setup', {'name': 'check.cloudflare.egress.check_egress_ip',
                          'func': check_egress_ip,
                          'consumes': [], 'produces': []})
    sc.add_hook('site_post_dns', {'name': 'check.cloudflare.cache.check_cloudflare_cache',
                                  'func': check_cloudflare_cache,
                                  'consumes': ['fqdns_behind_cloudflare', 'primary_domain'],
                                  'produces': []})
else:
    sc.console.print(
        '[bold yellow] Skipping check.cloudflare because [Cloudflare] and/or '
        '[Cloudflare.cachecheck] is not enabled')

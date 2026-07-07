
import sys

from cloudflare import Cloudflare

import script_context as sc


# The whole Cloudflare plugin shares ONE Cloudflare client instance (one auth, one HTTP
# session).  It is built lazily on first use by get_client() and cached in
# sc.plugin_context['plugin.cloudflare']['client'].  __init__ stores a reference to get_client in
# the same bag so the other parts of the plugin (ips.py, fqdns.py) can reach it WITHOUT importing
# this module -- keeping them free of relative imports and standalone-loadable by the tests, and
# removing any hook-registration-order dependency (the client is built on first access, whichever
# hook runs first).


def build_client() -> Cloudflare:
    """Construct the Cloudflare client from the [Cloudflare] config section.

    api_token (preferred) else email + api_key.  There is no direct-environment fallback; the
    operator decides in the config file where those values come from (literals, <{secret env
    ...}>, <{secret aws ...}>, ...).  Missing credentials while enabled -> clear exit.
    """
    cf = sc.config['Cloudflare']
    api_token = cf.get('api_token')
    if api_token:
        return Cloudflare(api_token=api_token)
    email = cf.get('email')
    api_key = cf.get('api_key')
    if not email or not api_key:
        sys.exit('ERROR: [Cloudflare] is enabled but needs either api_token, '
                 'or both email and api_key.')
    return Cloudflare(api_email=email, api_key=api_key)


def get_client() -> Cloudflare:
    """Return the shared Cloudflare client, building it on first use.

    Runs at the setup-hook stage (via the first consumer), AFTER the pre-setup config-substitution
    pass -- so credentials are resolved (not still <{...}> placeholders).  The client's creds must
    be pass-1-resolvable (nothing today defers Cloudflare creds; only plugin.umich returns
    sc.DEFER).
    """
    ctx = sc.plugin_context.setdefault('plugin.cloudflare', {})
    if ctx.get('client') is None:
        ctx['client'] = build_client()
    return ctx['client']

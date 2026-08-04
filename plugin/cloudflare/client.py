
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


API_BASE_URL = 'https://api.cloudflare.com/client/v4'   # pinned; see pinned_client()


def pinned_client(**creds) -> Cloudflare:
    """Build a Cloudflare client that uses EXACTLY the credentials the config supplied.

    build_client's docstring has always promised "no direct-environment fallback".  Measured on
    cloudflare 5.4.0, that promise was FALSE: the SDK back-fills every credential argument left
    None from the environment, and ambient values reach the wire by four routes --

      1. `auth_headers` returns the FIRST of email -> key -> token -> user_service_key that is
         set, and only that one, so an ambient $CLOUDFLARE_EMAIL beats a configured api_token
         and the token is never sent at all;
      2. `default_headers` separately adds X-Auth-Key / X-Auth-Email whenever those attributes
         are not None;
      3. $CLOUDFLARE_CUSTOM_HEADERS is merged LAST into default_headers, overriding 1 and 2; and
      4. $CLOUDFLARE_BASE_URL redirects every request, sending the configured credential to an
         arbitrary host.

    Routes 1 and 2 are closed by nulling the fields the config did not supply (both read these
    attributes at request-build time), route 3 by clearing _custom_headers, route 4 by pinning
    base_url.  Route 4 is the serious one: the credential LEAVES THE MACHINE rather than merely
    failing to authenticate, and this program runs unattended against production every month.

    NOT closed, and deliberately: httpx is constructed with trust_env=True, so $HTTPS_PROXY and
    $SSL_CERT_FILE still influence transport.  Closing that would break legitimate proxied
    deployments; it is recorded in development/2026-07-30-platform-domain-util2/SPEC.md §8.13.

    The pin is SDK-version-sensitive (measured against 5.4.0) and pyproject declares `cloudflare`
    unpinned, which is why the test asserts the headers of a real built request, not these
    attribute assignments.
    """
    client = Cloudflare(**creds, base_url=API_BASE_URL)
    for field in ('api_token', 'api_key', 'api_email', 'user_service_key'):
        # `creds.get(field) is None`, NOT `field not in creds`: the SDK's own __init__ back-fills
        # a credential from the environment whenever the value it receives IS None -- an EXPLICIT
        # api_email=None triggers that back-fill exactly like an omitted keyword does, before
        # this loop ever runs.  A `field not in creds` guard only re-nulls the OMITTED case, so
        # an explicit None left the SDK's own ambient back-fill standing on the instance.
        # Matching the SDK's own None-triggered back-fill is what makes this pin correct
        # regardless of how a caller spells "no credential".
        if creds.get(field) is None:
            setattr(client, field, None)
    client._custom_headers = {}  # noqa: SLF001 -- route 3 above; the SDK has no public API for
    # "ignore $CLOUDFLARE_CUSTOM_HEADERS", and it is merged after everything this function pins
    return client


def build_client() -> Cloudflare:
    """Construct the Cloudflare client from the [Cloudflare] config section.

    api_token (preferred) else email + api_key.  There is no direct-environment fallback -- the
    operator decides in the config file where those values come from (literals, <{secret env
    ...}>, <{secret aws ...}>, ...) -- and pinned_client() is what makes that sentence TRUE
    rather than merely intended.  Missing credentials while enabled -> clear exit.
    """
    cf = sc.config['Cloudflare']
    api_token = cf.get('api_token')
    if api_token:
        return pinned_client(api_token=api_token)
    email = cf.get('email')
    api_key = cf.get('api_key')
    if not email or not api_key:
        sys.exit('ERROR: [Cloudflare] is enabled but needs either api_token, '
                 'or both email and api_key.')
    return pinned_client(api_email=email, api_key=api_key)


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

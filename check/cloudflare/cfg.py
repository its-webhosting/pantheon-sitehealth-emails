"""[Cloudflare.cachecheck] configuration access + validation.

All keys must be pass-1-resolvable substitutions (same invariant as the Cloudflare creds):
the egress setup hook runs before the deferred substitution pass.  See
docs/cloudflare-cachecheck.md.
"""

import sys

import script_context as sc

DEFAULTS = {
    # Sent on every request to sites so owners can identify us in their webserver logs:
    "user_agent": "pantheon-sitehealth-emails (Linux; UMich WWS 0.1) webmaster@umich.edu",
    # Per-request timeout, seconds:
    "timeout": 5,
    # The "Understanding your Cloudflare cache report" page notices link to; override in
    # config once published (U-M) or point at your own institution's page:
    "report_doc_url": "https://documentation.its.umich.edu/cloudflare-cache-report",
}

# Required when the check is enabled; missing = fatal (zero silent failures):
REQUIRED = ("account_id", "list_name")


def cachecheck_config() -> dict:
    """The merged [Cloudflare.cachecheck] settings (defaults overlaid by config)."""
    return DEFAULTS | sc.config.get("Cloudflare", {}).get("cachecheck", {})


def validate_cachecheck_config() -> None:
    """Fatal if a REQUIRED key is absent.  Presence-only: values may still hold <{...}>
    substitution markers at import time; they resolve before the hooks run."""
    cachecheck = sc.config.get("Cloudflare", {}).get("cachecheck", {})
    missing = [key for key in REQUIRED if key not in cachecheck]
    if missing:
        sys.exit(
            f"ERROR: [Cloudflare.cachecheck] is enabled but missing required setting(s): "
            f"{', '.join(missing)}"
        )

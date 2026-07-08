"""U-M Cloudflare CMS-integration checks (site_post_gather hook).

Recommends the U-M Cloudflare cache integrations on sites that have FQDNs proxied behind
Cloudflare.  Relocated from the main script (was inline in the WP/Drush gather); the
umich_enabled() gate is implied by the check.umich package gate, and the fqdns gate travels
via site_context["fqdns_behind_cloudflare"] (site_post_dns data contract, see CLAUDE.md).

Uses the helpers the main script exposes on sc (sc.check_wordpress_plugin /
sc.check_drupal_module) because check modules cannot import the dash-named script.
"""

import script_context as sc

DOC_WP = "https://documentation.its.umich.edu/node/5114"
DOC_DRUPAL = "https://documentation.its.umich.edu/node/4242"

# (module slug, display name, reason, extra check_drupal_module kwargs)
DRUPAL_MODULES = (
    ("cloudflare",
     "CloudFlare",  # note: capital F here
     "Necessary for automatically clearing Cloudflare's caches when content is updated.", {}),
    ("cloudflarepurger",
     "CloudFlare Purger",
     "Necessary for automatically clearing Cloudflare's caches when content is updated.", {}),
    ("purge_processor_lateruntime",
     "Late runtime processor (purge_processor_lateruntime)",
     "Necessary for automatically clearing Cloudflare's caches when content is updated.", {}),
    ("purge_processor_cron",
     "Purge Cron Processor (purge_processor_cron)",
     "Recommended as a fallback for clearing Cloudflare's caches when content is updated.",
     {"level": "info"}),
)


def check_cloudflare_cms_integrations(site_context) -> None:
    site = site_context["site"]["name"]
    if not site_context.get("fqdns_behind_cloudflare"):
        return
    framework = site_context.get("framework") or ""
    if framework.startswith("wordpress"):
        plugins = site_context.get("wordpress_plugins")
        if plugins is None:
            return  # wp failure already produced its own alert notice in the gather
        site_context.add_notices(sc.check_wordpress_plugin(
            site,
            plugins,
            "umich-cloudflare",
            "University of Michigan: Cloudflare Cache",
            DOC_WP,
            "Needed for automatically clearing Cloudflare's caches when content is updated.",
        ))
    elif framework.startswith("drupal"):
        mods = site_context.get("drupal_modules")
        drupal_version = site_context.get("drupal_version") or ""
        if mods is None or drupal_version.startswith("7."):
            return  # drush failure already noticed; D7ES sites keep their own module set
        for slug, display_name, reason, kwargs in DRUPAL_MODULES:
            site_context.add_notices(sc.check_drupal_module(
                site, mods, slug, display_name, DOC_DRUPAL, reason, **kwargs))

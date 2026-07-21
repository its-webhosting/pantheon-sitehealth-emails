"""The Pantheon Advanced Page Cache recommended-plugin check (campaign I9, from B34)."""

import script_context as sc


def check_papc(site_context):
    if not site_context["framework"].startswith("wordpress"):
        return
    site = site_context["site"]
    site_context.add_notices(
        sc.check_wordpress_plugin(
            site["name"],
            site_context["wordpress_plugins"],
            "pantheon-advanced-page-cache",
            "Pantheon Advanced Page Cache",
            "https://docs.pantheon.io/guides/wordpress-configurations/wordpress-cache-plugin",
            "Needed for automatically clearing Pantheon's caches (not Cloudflare's) when content is updated.",
        )
    )

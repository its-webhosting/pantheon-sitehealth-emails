"""The Pantheon Advanced Page Cache Drupal-module check (campaign I10, from B35)."""

import script_context as sc


def check_papc(site_context):
    if not site_context["framework"].startswith("drupal"):
        return
    site_context.add_notices(
        sc.check_drupal_module(
            site_context["site"]["name"],
            site_context["drupal_modules"],
            "pantheon_advanced_page_cache",
            "Pantheon Advanced Page Cache",
            "https://www.drupal.org/project/pantheon_advanced_page_cache",
            "Necessary for automatically clearing Pantheon's caches (not Cloudflare's) when content is updated.",
        )
    )

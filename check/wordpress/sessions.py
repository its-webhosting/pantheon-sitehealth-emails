"""The WP Native PHP Sessions recommended-plugin check (campaign I9, from B34)."""

import script_context as sc


def check_native_php_sessions(site_context):
    if not site_context["framework"].startswith("wordpress"):
        return
    site = site_context["site"]
    site_context.add_notices(
        sc.check_wordpress_plugin(
            site["name"],
            site_context["wordpress_plugins"],
            "wp-native-php-sessions",
            "Native PHP Sessions",
            "https://docs.pantheon.io/guides/php/wordpress-sessions#install-wordpress-native-php-sessions-plugin",
            "Strongly recommended to ensure PHP sessions work correctly on Pantheon.",
        )
    )

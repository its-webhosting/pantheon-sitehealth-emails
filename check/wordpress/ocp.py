"""The Object Cache Pro configuration check (campaign I9, from B34).

Iterates the plugin list for an active object-cache-pro and probes the live
environment's OCP config via a WP-CLI eval.  Rebinds site_context["wp_smell"] on
non-fatal stderr -- the one sanctioned mutate-during-phase contract key (SPEC D-i9-3)."""

import script_context as sc


def check_ocp_config(site_context):
    if not site_context["framework"].startswith("wordpress"):
        return
    plugins = site_context["wordpress_plugins"]
    if plugins is None:
        return
    site = site_context["site"]
    live_site = site["id"] + ".live"
    for p in plugins:
        # Special check for Object Cache Pro upgrade, see https://docs.pantheon.io/release-notes/2025/10/updated-ocp-config
        if p["name"] == "object-cache-pro" and p["status"] != "inactive":
            # This isn't a plugin, but here is a good place to check for it.
            ocp_config, errors, fatal = sc.wp_eval(
                live_site,
                'echo (defined("WP_REDIS_CONFIG") && isset(WP_REDIS_CONFIG["analytics"]["persist"]) && WP_REDIS_CONFIG["analytics"]["persist"])? "true": "false";',
            )
            if fatal or ocp_config is None:
                site_context.add_notices(
                    sc.wp_error(
                        site["name"],
                        "ocp-config-check",
                        f"Unable to check OCP configuration for {site['name']}.",
                        errors,
                    )
                )
            elif errors != "":
                site_context["wp_smell"] = errors
            if isinstance(ocp_config, str) and ocp_config.startswith(
                "true"
            ):
                site_context.add_notice(
                    {
                        "type": "alert",
                        "icon": "&#x1F6A8;",  # police car light
                        "csv": f"{site['name']},ocp-config-fix-needed",
                        "short": "Fix Object Cache Pro configuration",
                        "message": f'<p>Please <a href="https://docs.pantheon.io/release-notes/2025/10/updated-ocp-config">fix this site\'s Object Cache Pro configuration</a>.</p>',  # noqa: F541 -- verbatim-moved notice literal, f-prefix kept for byte-identity (Invariant 8)
                        "text": f"Please fix this site's Object Cache Pro configuration: https://docs.pantheon.io/release-notes/2025/10/updated-ocp-config",  # noqa: F541 -- verbatim-moved notice literal, f-prefix kept for byte-identity (Invariant 8)
                    }
                )

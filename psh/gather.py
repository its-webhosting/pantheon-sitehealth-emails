"""WordPress gather core: the network-URL fetch (B32) and the version / plugin-list /
add-on-update / theme-list gather (B34), moved out of main()'s per-site loop at campaign
I9 (CAMPAIGN.md section 3.1, development/2026-07-21-mod-I9-wordpress/SPEC.md D-i9-1 /
D-i9-2).

Loop control stays in main(): these functions return their results (a WordPressGather /
a (url, smell) pair) and main() threads them into its locals -- site_url,
wordpress_version, plugins, add_on_updates, wp_smell, site_results -- per SPEC D-i9-2.
The returned smells participate in main()'s last-wins overwrite semantics: a later empty
smell never clears an earlier one, so main() only rebinds wp_smell when the returned
smell is non-empty.

The notice-emitting checks that used to be interleaved in this code live in
check/wordpress/ and check/umich/ (site_post_gather hooks); the wp_error notices below
describe *failed gathers*, not checks, so they stay with the fetches (D-i9-1).

check_wordpress_plugin is the recommended-plugin notice builder the papc / sessions /
cloudflare_cms hooks call via sc.check_wordpress_plugin (exposed from psh/_legacy.py's
re-import; check_drupal_module, its Drupal sibling, moves here at I10).
"""
import html
from typing import NamedTuple

from rich.pretty import pprint

import script_context as sc
from psh.gateway import wp, wp_error, wp_eval


class WordPressGather(NamedTuple):
    wordpress_version: str  # "" when the fetch failed (fatal wp_eval stdout; the "unknown" fallback below is unreachable through the gateway)
    plugins: object         # raw wp plugin list result (list | None | junk)
    add_on_updates: list    # plugin updates then theme updates, list order
    wp_smell: str           # last-wins stderr across version/plugins/themes; "" if none
    results_entry: dict     # {"framework", "version", "plan_name"} for site_results


def check_wordpress_plugin(  # noqa: PLR0913 -- moved verbatim, signature unchanged (Task 4 brief): one input per notice ingredient, pinned by the papc/sessions/cloudflare_cms call sites
    site: str,
    installed_plugins: list,
    name: str,
    display_name: str,
    url: str,
    reason: str,
) -> list:
    # Cycle: _legacy imports this module.  escape_url moves to psh.render at I12
    # (D-i6-2 precedent).
    from psh._legacy import escape_url  # noqa: PLC0415

    notices = []
    if not isinstance(installed_plugins, list):
        return notices  # this error should already have been handled by our caller, so skip additional work

    installed = [p for p in installed_plugins if p["name"] == name]

    if len(installed) == 0:
        sc.console.print(
            f":exclamation: [bold red] ATTENTION: {site} does not have the {display_name} plugin installed."
        )
        notices.append(
            {
                "type": "warning",
                "icon": "&#x26A0;",  # warning sign
                "csv": f"{site},not-installed,{name}",
                "short": f"install the {name} plugin",
                "message": f'<p>The <a href="{escape_url(url)}">{html.escape(display_name)}</a> WordPress plugin needs to be installed:</p><p>{html.escape(reason)}</p>',
                "text": f"The {display_name} WordPress plugin\n<{url}>\nneeds to be installed: {reason}",
            }
        )
        return notices

    if len(installed) > 1:
        sc.console.print(
            f":exclamation: [bold red] ATTENTION: {site} has more than one {display_name} plugin installed."
        )
        notices.append(
            {
                "type": "info",
                "icon": "&#x1F50E;",  # magnifying glass
                "csv": f"{site},multiple-installed,{name}",
                "short": f"plugin {name} installed multiple times",
                "message": f'<p>The <a href="{escape_url(url)}">{html.escape(display_name)}</a> WordPress plugin is installed multiple times.</p>',
                "text": f"The {display_name} WordPress plugin\n<{url}>\nis installed multiple times.",
            }
        )

    plugin = installed[0]
    if "status" not in plugin or plugin["status"] not in (
        "active",
        "active-network",
        "must-use",
    ):
        sc.console.print(
            f":exclamation: [bold red] ATTENTION: {site} has the {display_name} plugin installed but it is not active."
        )
        notices.append(
            {
                "type": "warning",
                "icon": "&#x26A0;",  # warning sign
                "csv": f"{site},turned-off,{name}",
                "short": f"activate plugin {name}",
                "message": f'<p>The <a href="{escape_url(url)}">{html.escape(display_name)}</a> WordPress plugin needs to be activated:</p><p>{html.escape(reason)}</p>',
                "text": f"The {display_name} WordPress plugin\n<{url}>\nneeds to be activated: {reason}",
            }
        )

    return notices


def wordpress_network_url(site: dict, live_site: str, site_context) -> tuple[str | None, str]:
    """B32: fetch the WordPress-network home URL (wordpress_network sites only).

    Returns (stripped URL | None, smell): None when the eval produced no string, the
    smell being the probe's non-fatal stderr ("" when clean or fatal -- a fatal fetch
    adds the wp_error notice to site_context instead, exactly the inline behavior).
    """
    wp_smell = ""
    sc.console.print(
        f"[bold magenta]=== Getting WordPress network URL for {site['name']}:"
    )
    network_home_url, errors, fatal = wp_eval(
        live_site, "echo network_home_url();"
    )
    if fatal or network_home_url is None:
        site_context.add_notices(
            wp_error(
                site["name"],
                "version-check",
                f"Unable to get WordPress network URL for {site['name']}.",
                errors,
            )
        )
    elif errors != "":
        wp_smell = errors
    sc.debug(f"{site['name']} WordPress network URL: {network_home_url}")
    if isinstance(network_home_url, str):
        return network_home_url.strip(), wp_smell
    return None, wp_smell


def gather_wordpress(site: dict, live_site: str, site_context) -> WordPressGather:  # noqa: C901, PLR0912 -- moved verbatim (CAMPAIGN.md section 3.1: moves get no algorithmic redesign)
    """B34 gather core: version fetch, plugin-list fetch, add-on-update collection
    (plugins then themes, list order -- golden-load-bearing, SPEC section 6), the
    must-use diagnostic print, and the theme-list fetch, verbatim from main()."""
    wp_smell = ""
    add_on_updates = []
    sc.console.print(
        f"[bold magenta]=== Getting WordPress version for {site['name']}:"
    )
    wordpress_version, errors, fatal = wp_eval(
        live_site, 'require ABSPATH . WPINC . "/version.php"; echo $wp_version;'
    )
    if fatal or wordpress_version is None:
        site_context.add_notices(
            wp_error(
                site["name"],
                "version-check",
                f"Unable to check WordPress version for {site['name']}.",
                errors,
            )
        )
    elif errors != "":
        wp_smell = errors
    sc.debug(f"{site['name']} WordPress version: {wordpress_version}")
    if not isinstance(wordpress_version, str):
        wordpress_version = "unknown"
    wordpress_version = wordpress_version.strip()
    results_entry = {
        "framework": site["framework"],
        "version": wordpress_version,
        "plan_name": site["plan_name"],
    }
    sc.console.print(
        f"[bold magenta]=== Checking WordPress plugins for {site['name']}:"
    )
    plugins, errors, fatal = wp(
        live_site,
        "plugin",
        "list",
        "--fields=name,status,update,version,update_version,title",
    )
    if fatal or plugins is None:
        site_context.add_notices(
            wp_error(
                site["name"],
                "plugin-list",
                f"Unable to run <code>wp plugin list</code> for {site['name']}.",
                errors,
            )
        )
    elif errors != "":
        wp_smell = errors
    if sc.options.verbose:
        pprint(plugins)
    # The PAPC and native-PHP-sessions plugin checks moved to
    # check/wordpress/papc.py and check/wordpress/sessions.py (site_post_gather hooks).
    # The umich-cloudflare plugin check moved to check/umich/cloudflare_cms.py
    # (site_post_gather hook).
    if isinstance(plugins, list):
        for p in plugins:
            if p["update"] == "available":
                add_on_updates.append(
                    {
                        "slug": p["name"],
                        "name": p["title"],
                        "type": "plugin",
                        "current_version": p["version"],
                        "new_version": p["update_version"],
                    }
                )
            if p["status"] == "must-use" and p["name"] != "loader":
                sc.console.print(
                    f"[bold yellow]{site['name']} has must-use plugin:"
                )
                pprint(p)
            # The umich-oidc-login reinstall check moved to
            # check/umich/oidc_login.py (site_post_gather hook).
            # The Object Cache Pro configuration check moved to
            # check/wordpress/ocp.py (site_post_gather hook).
        # The UMich Hummingbird fork check moved to
        # check/umich/hummingbird.py (site_post_gather hook).
    sc.console.print(
        f"[bold magenta]=== Checking WordPress themes for {site['name']}:"
    )
    themes, errors, fatal = wp(
        live_site,
        "theme",
        "list",
        "--fields=name,status,update,version,update_version,title",
    )
    if fatal or themes is None:
        site_context.add_notices(
            wp_error(
                site["name"],
                "plugin-list",
                f"Unable to run <code>wp theme list</code> for {site['name']}.",
                errors,
            )
        )
    elif errors != "":
        wp_smell = errors
    if sc.options.verbose:
        pprint(themes)
    if isinstance(themes, list):
        for t in themes:
            if t["update"] == "available":
                add_on_updates.append(  # noqa: PERF401 -- moved verbatim; rewriting the loop as a comprehension is a review activity, not part of a behavior-preserving move
                    {
                        "slug": t["name"],
                        "name": t["title"],
                        "type": "theme",
                        "current_version": t["version"],
                        "new_version": t["update_version"],
                    }
                )
    # The favicon.ico presence check moved to check/wordpress/favicon.py
    # (site_post_gather hook).
    return WordPressGather(
        wordpress_version=wordpress_version,
        plugins=plugins,
        add_on_updates=add_on_updates,
        wp_smell=wp_smell,
        results_entry=results_entry,
    )

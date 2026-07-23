"""WordPress and Drupal gather cores: the network-URL fetch (B32), the WordPress
version / plugin-list / add-on-update / theme-list gather (B34, campaign I9,
development/2026-07-21-mod-I9-wordpress/SPEC.md D-i9-1/D-i9-2), and the Drupal
core-status / pm:list / pm:updatestatus-or-composer-audit gather (B35, campaign I10,
development/2026-07-22-mod-I10-drupal/SPEC.md D-i10-1/D-i10-2) -- moved out of main()'s
per-site loop (CAMPAIGN.md section 3.1).

Loop control stays in main(): these functions return their results (a WordPressGather /
a DrupalGather / a (url, smell) pair) and main() threads them into its locals -- site_url,
wordpress_version, plugins, drupal_version, mods, add_on_updates, wp_smell, drush_smell,
composer_smell, site_results -- per SPEC D-i9-2/D-i10-2. The returned smells participate
in main()'s last-wins overwrite semantics: a later empty smell never clears an earlier
one, so main() only rebinds wp_smell/drush_smell when the returned smell is non-empty.

The notice-emitting checks that used to be interleaved in this code live in
check/wordpress/, check/drupal/, check/addon_updates/, and check/umich/ (site_post_gather
hooks); the wp_error/drush_error notices below describe *failed gathers*, not checks, so
they stay with the fetches (D-i9-1/D-i10-1).

check_wordpress_plugin / check_drupal_module are the recommended-plugin/module notice
builders the papc / sessions / cloudflare_cms / d7_eol hooks call via
sc.check_wordpress_plugin / sc.check_drupal_module (exposed from psh/_legacy.py's
re-import).

build_smell_notices is the B48 smell-notice *builder* (SPEC D-i10-1 amendment 1): it
lives here beside its sibling gathers, but its *emission* stays in main() (behind the
--only-warn gate) because no hook position can guarantee it runs after the
wp_smell/drush_smell in-place mutators (D-i9-3/D-i10-4).
"""
import html
import json
import re
from typing import NamedTuple

from rich.pretty import pprint

import script_context as sc
from psh.gateway import (
    drush,
    drush_error,
    run_terminus,
    terminus,
    wp,
    wp_error,
    wp_eval,
)
from psh.render import escape_url


class WordPressGather(NamedTuple):
    wordpress_version: str  # "" when the fetch failed (fatal wp_eval stdout; the "unknown" fallback below is unreachable through the gateway)
    plugins: object         # raw wp plugin list result (list | None | junk)
    add_on_updates: list    # plugin updates then theme updates, list order
    wp_smell: str           # last-wins stderr across version/plugins/themes; "" if none
    results_entry: dict     # {"framework", "version", "plan_name"} for site_results


class DrupalGather(NamedTuple):
    drupal_version: str  # "unknown" when the core-status fetch failed (real here, unlike WP)
    modules: object       # raw drush pm:list result (dict | None | junk)
    add_on_updates: list  # D7: pm:updatestatus entries; D8+: composer audit entries
    drush_smell: str      # last-wins stderr across core-status/pm:list; "" if none
    composer_smell: str   # composer dry-run stderr; "" if none
    results_entry: dict   # {"framework", "version", "plan_name"} for site_results


def check_wordpress_plugin(  # noqa: PLR0913 -- moved verbatim, signature unchanged (Task 4 brief): one input per notice ingredient, pinned by the papc/sessions/cloudflare_cms call sites
    site: str,
    installed_plugins: list,
    name: str,
    display_name: str,
    url: str,
    reason: str,
) -> list:
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


def check_drupal_module(  # noqa: PLR0913 -- moved verbatim, signature unchanged (Task 4 brief): one input per notice ingredient, pinned by the papc/d7_eol call sites
    site: str,
    installed_mods: dict,
    name: str,
    display_name: str,
    url: str,
    reason: str,
    level: str = "warning",
) -> list:
    notices = []
    if not isinstance(installed_mods, dict):
        return notices  # this error should already have been handled by our caller, so skip additional work

    icon = "&#x26A0;"  # warning sign
    if level == "info":
        icon = "&#x1F50E;"  # magnifying glass

    if name not in installed_mods:
        sc.console.print(
            f":exclamation: [bold red] ATTENTION: {site} does not have the {display_name} module installed."
        )
        notices.append(
            {
                "type": level,
                "icon": icon,
                "csv": f"{site},not-installed,{name}",
                "short": f"install module {name}",
                "message": f'<p>The <a href="{escape_url(url)}">{html.escape(display_name)}</a> Drupal module needs to be installed:</p><p>{html.escape(reason)}</p>',
                "text": f"The {display_name} Drupal module\n<{url}>\nneeds to be installed: {reason}",
            }
        )
        return notices

    mod = installed_mods[name]
    if "status" not in mod or mod["status"] != "Enabled":
        sc.console.print(
            f":exclamation: [bold red] ATTENTION: {site} has the {display_name} module installed but it is not enabled."
        )
        notices.append(
            {
                "type": level,
                "icon": icon,
                "csv": f"{site},turned-off,{name}",
                "short": f"enable module {name}",
                "message": f'<p>The <a href="{escape_url(url)}">{html.escape(display_name)}</a> Drupal module needs to be enabled:</p><p>{html.escape(reason)}</p>',
                "text": f"The {display_name} Drupal module\n<{url}>\nneeds to be enabled: {reason}",
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


def gather_drupal(site: dict, live_site: str, site_context) -> DrupalGather:  # noqa: C901, PLR0912, PLR0915 -- moved verbatim (CAMPAIGN.md section 3.1: moves get no algorithmic redesign)
    """B35 gather core: core-status fetch (version derivation, results entry), pm:list
    fetch, then D7 pm:updatestatus add-on collection OR D8+ composer dry-run + composer
    audit add-on collection (advisories, abandoned-packages print), verbatim from
    main()."""
    drush_smell = ""
    composer_smell = ""
    add_on_updates = []
    sc.console.print(
        f"[bold magenta]=== Checking Drupal modules for {site['name']}:"
    )
    drupal_status, errors, fatal = drush(live_site, "core-status")
    if fatal or drupal_status is None:
        site_context.add_notices(
            drush_error(
                site["name"],
                "core-status",
                f"Unable to run <code>drush core-status</code> for {site['name']}.",
                errors,
            )
        )
    elif errors != "":
        drush_smell = errors
    if sc.options.verbose:
        pprint(drupal_status)
    drupal_version = (
        drupal_status["drupal-version"]
        if isinstance(drupal_status, dict) and "drupal-version" in drupal_status
        else "unknown"
    )
    results_entry = {
        "framework": site["framework"],
        "version": drupal_version,
        "plan_name": site["plan_name"],
    }
    mods, errors, fatal = drush(live_site, "pm:list")
    if fatal or mods is None:
        site_context.add_notices(
            drush_error(
                site["name"],
                "pm-list",
                f"Unable to run <code>drush pm:list</code> for {site['name']}.",
                errors,
            )
        )
    elif errors != "":
        drush_smell = errors
    if sc.options.verbose:
        pprint(mods)
    # The PAPC module check, the Drupal 7 EOL alert, and the tag1_d7es
    # module check moved to check/drupal/papc.py and check/drupal/d7_eol.py
    # (site_post_gather hooks, campaign I10).
    # else: the four U-M Cloudflare module checks (cloudflare, cloudflarepurger,
    # purge_processor_lateruntime, purge_processor_cron) moved to
    # check/umich/cloudflare_cms.py (site_post_gather hook).
    if drupal_version.startswith("7."):
        updates, errors, fatal = drush(live_site, "pm:updatestatus", "--full")
        if fatal:
            site_context.add_notices(
                drush_error(
                    site["name"],
                    "pm-updatestatus",
                    f"Unable to run <code>drush pm:updatestatus</code> for {site['name']}.",
                    errors,
                )
            )
        # pm:updatestatus stderr is deliberately not captured as a smell -- it always
        # contains verbose progress output.
        if sc.options.verbose:
            pprint(updates)
        if isinstance(updates, dict):
            for package in updates:
                u = updates[package]
                current_version = u["existing_version"]
                new_version = current_version
                if "candidate_version" in u:
                    new_version = u["candidate_version"]
                elif "recommended" in u:
                    new_version = u["recommended"]
                elif "latest_version" in u:
                    new_version = u["latest_version"]
                if new_version == current_version:
                    new_version = f"none: {u['project_status']}"
                add_on_updates.append(
                    {
                        "slug": package,
                        "name": f'<a href="{escape_url(u["link"])}">{html.escape(u["title"])}</a>'
                        if "link" in u
                        else html.escape(u["title"]),
                        "type": u.get("type", "package"),
                        "current_version": current_version,
                        "new_version": new_version,
                    }
                )
    else:
        sc.console.print(
            f"[bold magenta]=== Dry-run update for packages on {site['name']}:"
        )
        command = ["composer", live_site, "--", "update", "--dry-run"]
        updates, errors, fatal = run_terminus(command)
        if fatal or updates is None:
            site_context.add_notice(
                {
                    "type": "alert",
                    "icon": "&#x1F6A8;",  # police car light
                    "csv": f"{site['name']},composer-update",
                    "short": "fix composer error",
                    "message": f"""
                    <p>Unable to run <code>composer update --dry-run</code> for {site["name"]}.
                    <code>composer</code> returned the following error:</p>
                    <pre>{html.escape(errors)}</pre>
                    """,
                    "text": f"""
                    Unable to run 'composer update --dry-run' for {site["name"]}.
                    composer returned the following error:

                    ----- START DRUSH ERROR -----
                    {errors}
                    ----- END ERROR -----

                    """,
                }
            )
        elif errors != "":
            composer_smell = errors
        if sc.options.verbose:
            pprint(updates)
        package_updates = {}
        if isinstance(updates, str):
            for line in updates.split("\n"):
                # Example line:
                # - Upgrading drupal/admin_toolbar (3.4.2 => 3.5.3)
                m = re.search(
                    r"^\s*-\s+Upgrading\s+(\S+)\s+\((.+) => (.+)\)\s*$", line
                )
                if m:
                    package_updates[m.group(1)] = {
                        "current": m.group(2),
                        "new": m.group(3),
                    }
        sc.console.print(
            f"[bold magenta]=== Running audit for packages on {site['name']}:"
        )
        audit, _errors, _fatal = terminus("composer", live_site, "--", "audit")
        if isinstance(audit, dict):
            if "advisories" in audit:
                package_list = audit["advisories"]
                for package in package_list:
                    vuln = []
                    # advisory_list could theoretically be empty, leaving "advisory"
                    # unbound below -- unreachable in practice (a composer-audit
                    # "advisories" entry always carries >=1 item), but psh/_legacy.py
                    # never type-checked this line; init added here for pyright.
                    advisory = None
                    advisory_list = package_list[package]
                    for advisory in advisory_list:
                        if isinstance(advisory, str):
                            advisory = package_list[package][advisory]  # noqa: PLW2901 -- moved verbatim (CAMPAIGN.md section 3.1: moves get no algorithmic redesign)
                        if sc.options.verbose:
                            sc.console.print(
                                f"[bold yellow]Advisory for {package}:"
                            )
                            pprint(advisory)
                        title = advisory["title"]
                        t = title.split(" - ")
                        if advisory["severity"]:
                            severity = advisory["severity"]
                        elif len(t) == 4:  # noqa: PLR2004 -- moved verbatim (CAMPAIGN.md section 3.1: moves get no algorithmic redesign)
                            severity = t[1]
                            title = " - ".join([t[0], t[2], t[3]])
                        else:
                            severity = "unknown"
                        vuln.append(
                            {
                                "title": f'<a href="{escape_url(advisory["link"])}">{html.escape(title)}</a>',
                                "severity": severity,
                            }
                        )
                    current_version = "unknown"
                    new_version = "unknown"
                    new_version_url = None
                    if package in package_updates:
                        if "current" in package_updates[package]:
                            current_version = package_updates[package][
                                "current"
                            ]
                        if "new" in package_updates[package]:
                            new_version = package_updates[package]["new"]
                        elif "cve" in package_updates[package]:
                            cve = package_updates[package]["cve"]
                            new_version = f"See {cve}"
                            new_version_url = (
                                f"https://nvd.nist.gov/vuln/detail/{cve}"
                            )
                    if new_version == "unknown":
                        new_version = "See advisory"
                        new_version_url = advisory["link"]  # pyright: ignore[reportOptionalSubscript] -- unreachable in practice (see the "advisory = None" comment above)
                    a = {
                        "slug": package,
                        "name": vuln,
                        "type": "package",
                        "current_version": current_version,
                        "new_version": new_version,
                    }
                    if new_version_url:
                        a["new_version_url"] = new_version_url
                    add_on_updates.append(a)
            if "abandoned" in audit and len(audit["abandoned"]) > 0:
                sc.console.print("[bold yellow]Abandoned packages:")
                pprint(audit["abandoned"])
        else:
            sc.console.print(
                f"[bold red]Unable to run <code>composer audit</code> for {site['name']}"
            )
        if sc.options.verbose:
            pprint(audit)
        # The Drupal user-agent check moved to check/umich/drupal_ua.py
        # (campaign I10, D-i10-6) -- a site_post_gather hook, now
        # [UMich].enabled-gated (a deliberate behavior change).

    return DrupalGather(
        drupal_version=drupal_version,
        modules=mods,
        add_on_updates=add_on_updates,
        drush_smell=drush_smell,
        composer_smell=composer_smell,
        results_entry=results_entry,
    )


def build_smell_notices(site_name, wp_smell, drush_smell, composer_smell):
    """Return the list of smell notice dicts (possibly empty) for one site (BLOCKMAP
    B48). The emission call stays in main() (SPEC D-i10-1 amendment 1); this is only
    the builder."""
    notices = []
    if wp_smell != "":
        notices.append(
            {
                "type": "info",
                "icon": "&#x1F50E;",  # magnifying glass
                "csv": f"{site_name},wp-smell,{json.dumps(wp_smell).replace(',', '\\,')}",
                "short": "PHP code problems",
                "message": f"""
<p>The <code>wp</code> (WP CLI) command is reporting PHP code problems with <strong>{site_name}</strong>.
Even if this is not breaking anything at the moment, it should be fixed to avoid possible future problems:</p>
<pre>{html.escape(wp_smell)}</pre>
""",
                "text": f"""
The "wp" (WP CLI) command is reporting PHP code problems with
{site_name}. Even if this is not breaking anything at
the moment, it should be fixed to avoid possible future problems:

----- START WP CLI REPORTED PROBLEMS -----
{wp_smell}
----- END OF WP CLI REPORTED PROBLEMS -----

    """,
            }
        )

    if drush_smell != "":
        notices.append(
            {
                "type": "info",
                "icon": "&#x1F50E;",  # magnifying glass
                "csv": f"{site_name},drush-smell,{json.dumps(drush_smell).replace(',', '\\,')}",
                "short": "PHP code problems",
                "message": f"""
<p>The <code>drush</code> command is reporting PHP code problems with <strong>{site_name}</strong>. Even
if this is not breaking anything at the moment, it should be fixed to avoid possible future problems:</p>
<pre>{html.escape(drush_smell)}</pre>
""",
                "text": f"""
The "drush" command is reporting PHP code problems with
{site_name}. Even if this is not breaking anything
at the moment, it should be fixed to avoid possible future problems:

----- START DRUSH REPORTED PROBLEMS -----
{drush_smell}
----- END OF DRUSH REPORTED PROBLEMS -----

""",
            }
        )

    if composer_smell != "":
        notices.append(
            {
                "type": "info",
                "icon": "&#x1F50E;",  # magnifying glass
                "csv": f"{site_name},composer-smell,{json.dumps(composer_smell).replace(',', '\\,')}",
                "short": "PHP code problems",
                "message": f"""
<p>The <code>composer</code> command is reporting PHP code problems with <strong>{site_name}</strong>. Even
if this is not breaking anything at the moment, it should be fixed to avoid possible future problems:</p>
<pre>{html.escape(composer_smell)}</pre>
""",
                "text": f"""
The "composer" command is reporting PHP code problems with
{site_name}. Even if this is not breaking anything
at the moment, it should be fixed to avoid possible future problems:

----- START COMPOSER REPORTED PROBLEMS -----
{composer_smell}
----- END OF COMPOSER REPORTED PROBLEMS -----

""",
            }
        )
    return notices

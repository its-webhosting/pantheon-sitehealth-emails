"""The Drupal multisite probe (campaign I10, from B30; site_post_dns).

Produces site_context["drupal_multisite"] (bool) / ["drupal_multisite_smell"] (str) --
the campaign's first hook-produced contract keys (SPEC D-i10-3, CAMPAIGN.md section 4
amendment 2): DAG-declared in this hook's `produces`, present only when the gate below
lets the probe run, read downstream with `.get()` (main()'s post-dns wiring; no in-repo
hook consumes them today)."""

import script_context as sc


def check_multisite(site_context):
    site = site_context["site"]
    if (
        len(site_context["custom_domains"]) <= 1
        or len(site_context["primary_domain"]) != 0
        or not site["framework"].startswith("drupal")
    ):
        return                      # keys deliberately absent when not probed
    live_site = site["id"] + ".live"
    smell = ""
    is_multisite = False
    sites_file, errors, fatal = sc.drush_php_script(
        live_site,
        'echo json_encode( ["result" => (is_file("/code/web/sites/sites.php") || is_file("/code/sites/sites.php") ? true : false) ] );',
    )
    if fatal or sites_file is None:
        site_context.add_notices(
            sc.drush_error(
                site["name"],
                "multisite-check",
                f"The check for whether {site['name']} is a Drupal multisite failed.",
                errors,
            )
        )
    elif errors != "":
        smell = errors
    if (
        isinstance(sites_file, dict)
        and "result" in sites_file
        and sites_file["result"] is True
    ):
        is_multisite = True
    sc.console.print(
        f"{site['name']} is a Drupal multisite: {sites_file}"
    )
    site_context["drupal_multisite"] = is_multisite
    site_context["drupal_multisite_smell"] = smell

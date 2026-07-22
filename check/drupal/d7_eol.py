"""The Drupal 7 end-of-life alert + tag1_d7es module check (campaign I10, from B35)."""

import script_context as sc


def check_d7_eol(site_context):
    if not site_context["framework"].startswith("drupal"):
        return
    if not site_context["drupal_version"].startswith("7."):
        return
    site = site_context["site"]
    site_context.add_notice(
        {
            "type": "alert",
            "icon": "&#x1F6A8;",  # police car light
            "csv": f"{site['name']},drupal7-eol",
            "short": "Migrate off Drupal 7 ASAP",
            "message": f"""
<p><b>Drupal 7 Extended Support for {site["name"]} will end in December 2026.</b>
Please migrate this site's content to a new site as soon as possible and
then switch {site["name"]} to the Sandbox plan. Plan on a large amount of
time being needed to design the new website, set it up, migrate content, and
then launch the new website before December.</p>
                """,
            "text": f"""
Drupal 7 Extended Support for {site["name"]} will end in
December 2026.  Please migrate this site's content to a new site
as soon as possible and then switch {site["name"]} to
the Sandbox plan. Plan on a large amount of time being needed to
design the new website, set it up, migrate content, and then
launch the new website before December.
                """,
        }
    )
    site_context.add_notices(
        sc.check_drupal_module(
            site_context["site"]["name"],
            site_context["drupal_modules"],
            "tag1_d7es",
            "Tag1 D7ES",
            "https://docs.pantheon.io/supported-drupal#drupal-7-long-term-support",
            "Necessary for receiving extended support for Drupal 7.",
        )
    )

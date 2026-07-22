"""The Drupal user-agent check (campaign I10, from B35; U-M-gated since I10 -- D-i10-6).

A site_post_gather hook.  University of Michigan Drupal sites are asked to identify
themselves to other campus websites with a `Drupal (+https://drupal.org/); UMich;
https://...` outgoing HTTP user agent; probe the live site via `drush php:script` and
advise configuring it when the string is missing/still the template value.  D7 sites are
skipped (the user-agent module this relies on is D8+ only) -- a failed version fetch
reports "unknown", which correctly does not match "7." and so still runs the probe,
exactly as today's inline D8+-else placement did.

Behavior change (deliberate, ledgered -- the D-i9-6 precedent): this check used to run
un-gated in main(), so a non-U-M Drupal 8+ site was told to configure a UMich-specific
user agent -- factually wrong off campus.  Moving it here, behind [UMich].enabled, is the
gating fix.
"""

import script_context as sc


def check_drupal_ua(site_context):
    if not site_context["framework"].startswith("drupal"):
        return
    drupal_version = site_context["drupal_version"]
    if drupal_version is None or drupal_version.startswith("7."):
        return
    site = site_context["site"]
    live_site = site["id"] + ".live"
    sc.console.print(
        f"[bold magenta]=== Checking for Drupal user agent on {site['name']}:"
    )
    ua_check_script = """
$result = 'unknown';
try {
    $client = \\Drupal::httpClient();
    $response = $client->get( 'https://ifconfig.me/ua' );
    $result = $response->getBody();
}
catch ( RequestException $e ) {
    watchdog_exception( 'pantheon_sitehealth_emails', $e->getMessage() );
}
echo( json_encode( array( 'result' => "{$result}" ) ) );
"""
    ua, errors, fatal = sc.drush_php_script(
        live_site,
        ua_check_script,
    )
    if fatal or ua is None:
        site_context.add_notices(
            sc.drush_error(
                site["name"],
                "drupal-ua-check",
                f"Failed to get the user agent string used by {site['name']}.",
                errors,
            )
        )
    elif errors != "":
        site_context["drush_smell"] = errors
    if (
        not isinstance(ua, dict)
        or "result" not in ua
        or not isinstance(ua["result"], str)
    ):
        site_context.add_notices(
            sc.drush_error(
                site["name"],
                "drupal-ua-check",
                f"Failed to get the user agent string used by {site['name']}.",
                "Unexpected result from drush php-script.",
            )
        )
    elif (
        not ua["result"].startswith(
            "Drupal (+https://drupal.org/); UMich; https://"
        )
        or "your-site" in ua["result"].lower()
        or "your_site" in ua["result"].lower()
    ):
        site_context.add_notice(
            {
                "type": "info",
                "icon": "&#x1F50E;",  # magnifying glass
                "csv": f"{site['name']},drupal-ua,{ua['result']}",
                "short": "Drupal user agent needs to be configured",
                "message": f"""
<p>Please <a href="https://documentation.its.umich.edu/node/4242#:~:text=Configure%20site%20User%20Agent">
configure the user agent string</a> that <strong>{site["name"]}</strong> uses for outgoing HTTP requests.
This will ensure that requests for data that this site makes of other University of Michigan websites do
not get blocked.</p>
""",
                "text": f"""
Please configure the user agent string that {site["name"]}
uses for outgoing HTTP requests.  This will ensure that requests for
data that this site makes of other University of Michigan websites do
not get blocked.

<https://documentation.its.umich.edu/node/4242#:~:text=Configure%20site%20User%20Agent>
""",
            }
        )

"""The /favicon.ico presence check (campaign I9, from B34).

Probes the live environment for a favicon.ico and, when absent and the site has FQDNs
that are not behind Cloudflare, recommends adding one.  Rebinds site_context["wp_smell"]
on non-fatal stderr -- the one sanctioned mutate-during-phase contract key (SPEC D-i9-3).

Still hardcoded U-M: the notice body's its.umich.edu link moved verbatim from B34
(Invariant 8; de-U-M-ifying it is post-campaign work, CLAUDE.md still-hardcoded-U-M list)."""

import script_context as sc


def check_favicon(site_context):
    if not site_context["framework"].startswith("wordpress"):
        return
    site = site_context["site"]
    live_site = site["id"] + ".live"
    # This isn't a plugin, but here is a good place to check for it.
    favicon, errors, fatal = sc.wp_eval(
        live_site, 'echo is_file("favicon.ico") ? "true": "false";'
    )
    if fatal or favicon is None:
        site_context.add_notices(
            sc.wp_error(
                site["name"],
                "favicon-check",
                f"Unable to check for <code>/favicon.ico</code> file for {site['name']}.",
                errors,
            )
        )
    elif errors != "":
        site_context["wp_smell"] = errors
    sc.debug(f"{site['name']} has a favicon.ico file: {favicon}")
    if (
        isinstance(favicon, str)
        and favicon.startswith("false")
        and len(site_context["fqdns_not_behind_cloudflare"]) > 0
    ):
        site_context.add_notice(
            {
                "type": "warning",
                "icon": "&#x26A0;",  # warning sign
                "csv": f"{site['name']},no-favicon",
                "short": "add favicon.ico file",
                "message": f'<p><a href="https://its.umich.edu/computing/web-mobile/cloudflare/getting-started">Put this site behind Cloudflare</a> or add a <a href="https://en.wikipedia.org/wiki/Favicon"><code>/code/favicon.ico</code> file</a> to lower Pantheon visitor numbers and increase the site\'s traffic capacity.</p>',  # noqa: F541 -- verbatim-moved notice literal, f-prefix kept for byte-identity (Invariant 8)
                "text": f"Put this site behind Cloudflare\n<https://its.umich.edu/computing/web-mobile/cloudflare/getting-started>\nor add a /code/favicon.ico file\n<https://en.wikipedia.org/wiki/Favicon>\nto lower Pantheon visitor numbers and increase the amount of traffic the site can handle at any time.",  # noqa: F541 -- verbatim-moved notice literal, f-prefix kept for byte-identity (Invariant 8)
            }
        )

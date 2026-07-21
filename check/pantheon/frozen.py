"""The frozen-site check (campaign I8, BLOCKMAP B19): a paid-plan site should never be
frozen -- Pantheon freezes inactive Sandbox-tier sites."""

import script_context as sc


def check_frozen_site(site_context):
    site = site_context["site"]
    if site["frozen"] is not False:
        sc.console.print(
            f":exclamation: [bold red] ATTENTION: {site['name']} is frozen!"
        )
        site_context.add_notice(
            {
                "type": "alert",
                "icon": "&#x1F6A8;",  # police car light
                "csv": f"{site['name']},frozen",
                "short": "unfreeze site",
                "message": f"""
<p>Website <strong>{site["name"]}</strong> is frozen!</p>
<p><a href="https://docs.pantheon.io/guides/platform-considerations/platform-site-info#inactive-site-freezing">
This should not happen</a> to a website on a paid Pantheon plan.</p>
<p><a href="https://its.umich.edu/computing/web-mobile/pantheon/support#support">Contact Pantheon</a> to get
<strong>{site["name"]}</strong> unfrozen and to find out what went wrong.</p>
""",
                "text": f"""
Website {site["name"]} is frozen!
<https://docs.pantheon.io/guides/platform-considerations/platform-site-info#inactive-site-freezing>

This should not happen</a> to a website on a paid Pantheon plan.
Contact Pantheon to get {site["name"]} unfrozen
and to find out what went wrong:
<https://its.umich.edu/computing/web-mobile/pantheon/support#support>
""",
            }
        )

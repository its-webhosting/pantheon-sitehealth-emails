"""The frozen-site check (campaign I8, BLOCKMAP B19): a paid-plan site should never be
frozen -- Pantheon freezes inactive Sandbox-tier sites."""

import script_context as sc

# Notice code this module emits, registered once at import (SPEC I14c D-i14c-6): a
# module-level constant cannot drift from what was registered.  `registry` is reached
# through the facade as sc.registry (CAMPAIGN.md section 3.5: checks and plugins import
# only sc), added at I14c Task 6.
NOTICE_FROZEN = sc.registry.register(
    "frozen", description="site frozen by Pantheon for inactivity")


def check_frozen_site(site_context):
    site = site_context["site"]
    if site["frozen"] is not False:
        sc.console.print(
            f":exclamation: [bold red] ATTENTION: {site['name']} is frozen!"
        )
        site_context.add_notice(
            sc.Notice(
                severity=sc.Severity.ALERT,
                code=NOTICE_FROZEN,
                short="unfreeze site",
                html=f"""
<p>Website <strong>{site["name"]}</strong> is frozen!</p>
<p><a href="https://docs.pantheon.io/guides/platform-considerations/platform-site-info#inactive-site-freezing">
This should not happen</a> to a website on a paid Pantheon plan.</p>
<p><a href="https://its.umich.edu/computing/web-mobile/pantheon/support#support">Contact Pantheon</a> to get
<strong>{site["name"]}</strong> unfrozen and to find out what went wrong.</p>
""",
                text=f"""
Website {site["name"]} is frozen!
<https://docs.pantheon.io/guides/platform-considerations/platform-site-info#inactive-site-freezing>

This should not happen</a> to a website on a paid Pantheon plan.
Contact Pantheon to get {site["name"]} unfrozen
and to find out what went wrong:
<https://its.umich.edu/computing/web-mobile/pantheon/support#support>
""",
            )
        )

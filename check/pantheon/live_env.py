"""The live-environment check (campaign I8, BLOCKMAP B21's notice half): a paid plan
whose live environment was never initialized is wasted money.  The env:list fetch and
its fatal guards stay in main() (SPEC D-i8-2)."""

import script_context as sc
from psh.notice import registry

# Notice code this module emits, registered once at import (SPEC I14c D-i14c-6): a
# module-level constant cannot drift from what was registered.  `registry` comes from
# psh.notice rather than sc because sc.registry does not exist yet -- I14c Task 6 adds it
# and repoints every check/ module (CAMPAIGN.md section 3.5).
NOTICE_NO_LIVE_ENV = registry.register(
    "no-live-env-but-paid-plan", description="paid plan with an uninitialized live environment")


def check_live_env(site_context):
    site = site_context["site"]
    if site_context["envs"]["live"]["initialized"] is False:
        sc.console.print(
            f":exclamation: [bold red] ERROR: {site['name']} is on a paid plan but its live "
            "environment is not initialized"
        )
        site_context.add_notice(
            sc.Notice(
                severity=sc.Severity.ALERT,
                code=NOTICE_NO_LIVE_ENV,
                short="no live environment",
                html=f"""
            <p>{site["name"]} is on a paid plan but its live environment is not initialized.  Either initialize
            the live environment and connect a domain through which people will access the site or downgrade the
            site's plan to Sandbox to save money.</p>
            """,
                text=f"""
            {site["name"]} is on a paid plan but its
            live environment is not initialized.  Either initialize the
            live environment and connect a domain through which people
            will access the site or downgrade the site's plan to
            Sandbox to save money.
            """,
            )
        )

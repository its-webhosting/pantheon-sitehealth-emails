"""The live-environment check (campaign I8, BLOCKMAP B21's notice half): a paid plan
whose live environment was never initialized is wasted money.  The env:list fetch and
its fatal guards stay in main() (SPEC D-i8-2)."""

import script_context as sc


def check_live_env(site_context):
    site = site_context["site"]
    if site_context["envs"]["live"]["initialized"] is False:
        sc.console.print(
            f":exclamation: [bold red] ERROR: {site['name']} is on a paid plan but its live "
            "environment is not initialized"
        )
        site_context.add_notice(
            {
                "type": "alert",
                "icon": "&#x1F6A8;",  # police car light
                "csv": f"{site['name']},no-live-env-but-paid-plan",
                "short": "no live environment",
                "message": f"""
            <p>{site["name"]} is on a paid plan but its live environment is not initialized.  Either initialize
            the live environment and connect a domain through which people will access the site or downgrade the
            site's plan to Sandbox to save money.</p>
            """,
                "text": f"""
            {site["name"]} is on a paid plan but its
            live environment is not initialized.  Either initialize the
            live environment and connect a domain through which people
            will access the site or downgrade the site's plan to
            Sandbox to save money.
            """,
            }
        )

"""The unapplied-upstream-updates check (campaign I8, BLOCKMAP B38): fetches
upstream:updates:list for the live environment itself (the check-specific-fetch case,
CAMPAIGN.md section 3.2) and emits an age-tiered notice with the update table."""

import datetime
from pprint import pprint

import script_context as sc


def check_upstream_updates(site_context):
    site = site_context["site"]
    live_site = site["id"] + ".live"
    # Check for un-applied site updates:

    sc.console.print(
        f"[bold magenta]=== Checking for unapplied updates for {site['name']}:"
    )
    updates, _errors, _fatal = sc.terminus("upstream:updates:list", live_site)
    if isinstance(updates, list):
        num_updates = len(updates)
        if num_updates > 0:
            update_times = [
                datetime.datetime.fromisoformat(update["datetime"]).replace(
                    tzinfo=datetime.UTC
                )
                for update in updates
            ]
            oldest_update = min(update_times)
            oldest_update_days = (
                datetime.datetime.now(datetime.UTC) - oldest_update
            ).days
            sc.console.print(
                f"{site['name']} has {num_updates} unapplied updates from Pantheon, the oldest from {oldest_update_days} days ago ( {oldest_update} )"
            )
            update_table_rows = ""
            update_bullet_list = ""
            for i, update in enumerate(updates):
                update_release_date = datetime.datetime.fromisoformat(
                    update["datetime"]
                ).strftime("%B %e, %Y")
                background_color = "#fff" if i % 2 == 0 else "#CCCFCA"
                update_table_rows += f"""
<tr style="background-color: {background_color};">
<td><div class="rt-data-header rt-plan">Date</div><div class="rt-data rt-plan">{update_release_date}</div></td>
<td><div class="rt-data-header rt-plan">Description</div><div class="rt-data rt-plan">{update["message"]}</div></td>
<td><div class="rt-data-header rt-plan">Author</div><div class="rt-data rt-plan">{update["author"]}</div></td>
</tr>
"""
                update_bullet_list += f"""
* {update_release_date}
  - {update["message"]}
  - Author: {update["author"]}

"""
            if oldest_update_days <= 7:  # noqa: PLR2004 -- verbatim age tier from B38 (<=1wk = info)
                site_context.add_notice(
                    {
                        "type": "info",
                        "icon": "&#x1F50E;",  # magnifying glass
                        "csv": f"{site['name']},updates-info,{num_updates},{oldest_update_days}",
                        "short": f"{num_updates} pending Pantheon updates"
                        if num_updates > 1
                        else "1 pending Pantheon update",
                        "message": f"""
<p><strong>{site["name"]}</strong> has
<a href="https://dashboard.pantheon.io/sites/{site["id"]}#dev/code">{num_updates} pending recent updates from Pantheon</a>.</p>
<div class="container">
<table class="responsive-table site-updates">
<thead><th class="rt-plan">Date</th><th class="rt-plan">Description</th><th class="rt-plan">Author</th></thead>
<tbody>{update_table_rows}</tbody>
</table>
</div>
<p>How to: <a href="https://docs.pantheon.io/core-updates">apply updates</a>,
<a href="https://docs.pantheon.io/pantheon-workflow">deploy updates</a>,
<a href="https://its.umich.edu/computing/web-mobile/pantheon/support">get support</a>.</p>
""",
                        "text": f"""
{site["name"]} has {num_updates} pending recent updates from Pantheon
<https://dashboard.pantheon.io/sites/{site["id"]}#dev/code>.

{update_bullet_list}
How to:
  * apply updates <https://docs.pantheon.io/core-updates>
  * deploy updates <https://docs.pantheon.io/pantheon-workflow>,
  * get support <https://its.umich.edu/computing/web-mobile/pantheon/support>
""",
                    }
                )
            elif oldest_update_days <= 30:  # noqa: PLR2004 -- verbatim age tier from B38 (<=1mo = warning)
                site_context.add_notice(
                    {
                        "type": "warning",
                        "icon": "&#x26A0;",  # warning sign
                        "csv": f"{site['name']},updates-warning,{num_updates},{oldest_update_days}",
                        "short": f"{num_updates} pending Pantheon updates"
                        if num_updates > 1
                        else "1 pending Pantheon update",
                        "message": f"""
<p><strong>{site["name"]}</strong> has
<a href="https://dashboard.pantheon.io/sites/{site["id"]}#dev/code">{num_updates} pending updates from Pantheon</a>, the oldest
from {oldest_update_days} days ago.</p>
<p>Please <a href="https://docs.pantheon.io/core-updates">apply these updates</a> and
<a href="https://docs.pantheon.io/pantheon-workflow">deploy them to the Live environment</a>.
<a href="https://its.umich.edu/computing/web-mobile/pantheon/support">A variety of support options are available</a>.</p>
<div class="container">
<table class="responsive-table site-updates">
<thead><th class="rt-plan">Date</th><th class="rt-plan">Description</th><th class="rt-plan">Author</th></thead>
<tbody>{update_table_rows}</tbody>
</table>
</div>
""",
                        "text": f"""
{site["name"]} has {num_updates} pending updates from Pantheon
<https://dashboard.pantheon.io/sites/{site["id"]}#dev/code>, the
oldest from {oldest_update_days} days ago. Please apply these updates
<https://docs.pantheon.io/core-updates> and deploy them to the
Live environment. <https://docs.pantheon.io/pantheon-workflow>
A variety of support options are available.
<a href="https://its.umich.edu/computing/web-mobile/pantheon/support">

{update_bullet_list}
""",
                    }
                )
            else:
                site_context.add_notice(
                    {
                        "type": "alert",
                        "icon": "&#x1F6A8;",  # police car light
                        "csv": f"{site['name']},updates-alert,{num_updates},{oldest_update_days}",
                        "short": f"needs maintenance: {num_updates} Pantheon updates, oldest {oldest_update_days} days old"
                        if num_updates > 1
                        else f"needs maintenance: 1 Pantheon update, {oldest_update_days} days old",
                        "message": f"""
<p><strong>{site["name"]}</strong> has
<a href="https://dashboard.pantheon.io/sites/{site["id"]}#dev/code">{num_updates} pending updates from Pantheon</a>, the oldest
from {oldest_update_days} days ago.</p>
<p><i>Please <a href="https://docs.pantheon.io/core-updates">apply these updates</a> immediately</i> and then
<a href="https://docs.pantheon.io/pantheon-workflow">deploy them to the Live environment</a>. Websites that are
unmaintained or insecure may be shut down to protect the university.</p>
<p>U-M Procurement has a <a href="https://procurement.umich.edu/u-m-employees/purchasing/ordering/quote-to-order/">list
of web agencies</a> that will maintain a website for you and bill a university shortcode. If you would like help
applying the updates yourself, you can <a href="https://its.umich.edu/computing/web-mobile/pantheon/support">obtain
support through either Pantheon or ITS</a>.</p>
<div class="container">
<table class="responsive-table site-updates">
<thead><th class="rt-plan">Date</th><th class="rt-plan">Description</th><th class="rt-plan">Author</th></thead>
<tbody>{update_table_rows}</tbody>
</table>
</div>
""",
                        "text": f"""
{site["name"]} has {num_updates} pending updates from Pantheon
<https://dashboard.pantheon.io/sites/{site["id"]}#dev/code>, the
oldest from {oldest_update_days} days ago.

PLEASE APPLY THESE UPDATES IMMEDIATELY
<https://docs.pantheon.io/core-updates> and then deploy them to the
Live environment. <https://docs.pantheon.io/pantheon-workflow>

Websites that are unmaintained or insecure may be shut down to protect
the university.

U-M Procurement has a list of web agencies
<https://procurement.umich.edu/u-m-employees/purchasing/ordering/quote-to-order/>
that will maintain a website for you and bill a university shortcode.
If you would like help applying the updates yourself, you can obtain
support through either Pantheon or ITS.
<a href="https://its.umich.edu/computing/web-mobile/pantheon/support">

{update_bullet_list}
""",
                    }
                )

    else:
        sc.console.print(
            f":exclamation: [bold red] ERROR: unable to check updates for {site['name']}"
        )
        pprint(updates)  # noqa: T203 -- existing operator diagnostic on the non-list error path (verbatim B38)

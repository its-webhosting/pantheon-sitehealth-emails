"""The pending add-on updates table notice (campaign I10, BLOCKMAP B39).

Moved verbatim from main()'s post-site_post_gather region (psh/_legacy.py, pre-move
:1708-1783): the verbose pprint preamble, the table-row / bullet-list f-string builders,
and the `updates-addons` notice dict.  Renames only (SPEC section 8 acceptance item 3):
`escape_url(` -> `sc.escape_url(` (the checks-import-only-sc convention, Invariant 9);
`site["name"]`/`site["id"]` now read through the local `site = site_context["site"]`
introduced here; `add_on_updates` is read straight off `site_context["add_on_updates"]`
-- the SAME list object the I9 stuffer published (test_contract_registry.py pins the
stuffer side).

Still hardcoded U-M: the notice body's its.umich.edu support link moved verbatim
(Invariant 8; de-U-M-ifying it is post-campaign work, CLAUDE.md still-hardcoded-U-M
list).  The stray doubled quote in the Name column header (`rt-data-header rt-plan""`)
is golden-rendered -- moved byte-verbatim, NOT fixed (SPEC D-i10-5)."""

import html

from rich.pretty import pprint

import script_context as sc


def check_add_on_updates(site_context):
    site = site_context["site"]
    add_on_updates = site_context["add_on_updates"]
    if sc.options.verbose:
        sc.console.print(f"[bold yellow]=== Add-on updates for {site['name']}:")
        pprint(add_on_updates)
    num_updates = len(add_on_updates)
    if num_updates > 0:
        update_table_rows = ""
        update_bullet_list = ""
        for i, update in enumerate(add_on_updates):
            name = update["name"]
            if isinstance(name, list):
                name = "\n".join(
                    [
                        f"{n['title']}, ({n['severity'].upper()})<br /><br />"
                        for n in name
                    ]
                )
            if "new_version_url" in update:
                new_version = f'<a href="{sc.escape_url(update["new_version_url"])}">{html.escape(update["new_version"])}</a>'
            else:
                new_version = html.escape(update["new_version"])
            background_color = "#fff" if i % 2 == 0 else "#CCCFCA"
            update_table_rows += f"""
<tr style="background-color: {background_color};">
<td><div class="rt-data-header rt-plan">ID</div><div class="rt-data rt-plan">{html.escape(update["slug"])}</div></td>
<td><div class="rt-data-header rt-plan"">Name</div><div class="rt-data rt-plan">{name}</div></td>
<td><div class="rt-data-header rt-plan">Type</div><div class="rt-data rt-plan">{html.escape(update["type"])}</div></td>
<td><div class="rt-data-header rt-plan">Current version</div><div class="rt-data rt-plan">{html.escape(update["current_version"])}</div></td>
<td><div class="rt-data-header rt-plan">New version</div><div class="rt-data rt-plan">{new_version}</div></td>
</tr>
"""
            update_bullet_list += f"""
* {update["slug"]}
  - Name: {update["name"]}
  - Type: {update["type"]}
  - Current version: {update["current_version"]}
  - New version:     {update["new_version"]}

"""
        site_context.add_notice(
            {
                "type": "warning",
                "icon": "&#x26A0;",  # warning sign
                "csv": f"{site['name']},updates-addons,{num_updates}",
                "short": f"{num_updates} pending add-on updates"
                if num_updates > 1
                else "1 pending add-on update",
                "message": f"""
<p><strong>{site["name"]}</strong> has {num_updates} pending add-on updates.</p>
<p>Please update these add-ons in the site's Dev environment and
<a href="https://docs.pantheon.io/pantheon-workflow">deploy them to the Live environment</a>.
Uninstall any add-ons you are not using to improve your site's security, size, and speed.
<a href="https://its.umich.edu/computing/web-mobile/pantheon/support">A variety of support options are available</a>.</p>
<div class="container">
<table class="responsive-table site-updates">
<thead><th class="rt-plan">ID</th><th class="rt-plan">Name</th><th class="rt-plan">Type</th><th class="rt-plan">Current version</th><th class="rt-plan">New version</th></thead>
<tbody>{update_table_rows}</tbody>
</table>
</div>
""",
                "text": f"""
{site["name"]} has {num_updates} pending add-on updates
<https://dashboard.pantheon.io/sites/{site["id"]}#dev/code>.
Please update these add-ons in the site's Dev environment and deploy
them to the Live environment.
<https://docs.pantheon.io/pantheon-workflow>

Uninstall any add-ons you are not using to improve your site's
security, size, and speed.

A variety of support options are available.
<a href="https://its.umich.edu/computing/web-mobile/pantheon/support">

{update_bullet_list}
""",
            }
        )

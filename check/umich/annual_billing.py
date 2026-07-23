"""U-M annual-billing notices (campaign I12, from B50/B51), as site_pre_render hooks.

These two notices are published as HOOK-PRODUCED site_context keys (CAMPAIGN.md §4, the
I10 drupal_multisite precedent) -- `annual_bill_upcoming` and `annual_bill_in_progress` --
NOT via `add_notice`.  main()'s `sort_notices_and_subject` reads them with `.get()` and
inserts them at the front of the *rendered* notice list; they NEVER enter
site_context["notices"].  This is deliberate and load-bearing (SPEC I12 §2.2): the
pre-campaign code inserted them straight into the render-only `sorted_notices` local, so
their csv rows have never reached `all_warnings` / `-notices.csv`, and the in-progress
notice -- inserted after the subject is computed -- renders first yet never influences the
subject.  Using `add_notice` would break both quirks (csv rows + front ordering), so the
absence of a csv path here is a feature, not an omission.

Registered inside check/umich/__init__.py's [UMich].enabled guard, so the `umich_enabled()`
test is subsumed by the registration gate (the oidc_login/drupal_ua precedent).
"""

import script_context as sc


def build_annual_bill_upcoming_notice(site_name, plan_name, annual_bill, shortcode, portal_site_id):
    """The contract-year-end "will be billed July 1" alert (BLOCKMAP B50)."""
    return {
        "type": "alert",
        "icon": "&#x1F4B5;",  # dollar banknotes
        "csv": f"{site_name},annual-bill,{annual_bill},{shortcode}",
        "short": f"${annual_bill:,.2f} will be billed to shortcode {shortcode} on July 1",
        "message": f"""
                <p style="background-color: #f8d7da; padding: 1em; border: 2px solid #58151c;">
                    On July 1, ${annual_bill:,.2f} will be billed to shortcode <strong>{shortcode}</strong>
                    when ITS runs its billing process.  This charge will be for a
                    full year (July 1 - June 30) of Pantheon hosting on the {plan_name} plan for the site
                    <strong>{site_name}</strong>.
                </p>
                <p>Please see if a different plan would be better:</p>
                <ul>
                    <li><a href="#estimated-costs">Estimated Plan Costs for {site_name}</a> (see the table, below)</li>
                    <li><a href="https://docs.pantheon.io/guides/account-mgmt/plans/resources">Pantheon Plan Resources</a></li>
                    <li><a href="https://its.umich.edu/computing/web-mobile/pantheon/pricing">U-M Pantheon pricing</a></li>
                </ul>
                <p>Do you want to change to a different plan or have use a different shortcode?</p>
                <ul>
                    <li>
                        <a href="https://admin.webservices.umich.edu/sites/{portal_site_id}/plan/">Change the plan for {site_name}</a>.
                        Changes must be made by the end of the day on June 29 for the July 1 annual billing.
                    </li>
                    <li>
                        <a href="https://admin.webservices.umich.edu/sites/{portal_site_id}/edit/">Change the shortcode for {site_name}</a>.
                        (for all future billing).
                    </li>
                </ul>
                <p>On July 1, you will be billed for the plan the site was on as of June 30.</p>
                """,
        "text": f"""
=======================================================================
On July 1, ${annual_bill:,.2f} will be billed to shortcode {shortcode}
when ITS runs its billing process.  This charge will be for a full
year (July 1 - June 30) of Pantheon hosting on the
{plan_name} plan for the site {site_name}.
=======================================================================

Please see if a different plan would be better:

  * See the Estimated Plan Costs for {site_name}
    in the table below.
  * See the Pantheon Plan Resources table at
    <https://docs.pantheon.io/guides/account-mgmt/plans/resources>
  * See U-M Pantheon pricing at
    <https://its.umich.edu/computing/web-mobile/pantheon/pricing>

Do you want to change to a different plan or have use a different
shortcode?

  * Change the plan for {site_name}:
    <https://admin.webservices.umich.edu/sites/{portal_site_id}/plan/>
    Changes must be made by the end of the day on June 29 for the
    July 1 annual billing.

  * Change the shortcode for {site_name}</a>
    <https://admin.webservices.umich.edu/sites/{portal_site_id}/edit/>
    (for all future billing).

On July 1, you will be billed for the plan the site was on as of
June 30.
""",
    }


def build_annual_bill_in_progress_notice(site_name, plan_name, annual_bill, shortcode):
    """The "ITS is in the process of billing" alert (BLOCKMAP B51; deletion is I12's call)."""
    return {
        "type": "alert",
        "icon": "&#x1F4B5;",  # dollar banknotes
        "csv": f"{site_name},annual-bill-in-progress,{annual_bill},{shortcode}",
        "short": f"${annual_bill:,.2f} is being billed to shortcode {shortcode}",
        "message": f"""
                <p style="background-color: #f8d7da; padding: 1em; border: 2px solid #58151c;">
                    ITS is in the process of billing ${annual_bill:,.2f} to shortcode <strong>{shortcode}</strong>
                    for a Pantheon {plan_name} plan to cover website hosting for the site
                    <strong>{site_name}</strong> from July 1, 2026 - June 30, 2027.
                </p>
                <p>Any changes to the site's plan between these dates will result in an additional pro-rated bill or credit in the following month.</p>
                """,
        "text": f"""
=======================================================================
ITS is in the process of billing ${annual_bill:,.2f} to shortcode {shortcode}
for a Pantheon {plan_name} plan to cover website hosting
for the site {site_name} from July 1, 2026 - June 30, 2027.
=======================================================================

Any changes to the site's plan between these dates will result in
an additional pro-rated bill or credit in the following month.
""",
    }


def _billing_inputs(site_context) -> tuple[dict, str, float]:
    site = site_context["site"]
    portal_site = sc.config["UMich"]["portal"]["sites"][site["name"]]
    annual_bill = float(sc.config["Pantheon"]["plan_info"][site_context["current_plan"]]["cost"])
    return site, portal_site, annual_bill


def check_annual_bill_upcoming(site_context) -> None:
    """B50's billing half: the June-window "will be billed July 1" alert, as a produced key."""
    if not sc.contract_year_end(site_context["end_date"]):
        return
    site, portal_site, annual_bill = _billing_inputs(site_context)
    site_context["annual_bill_upcoming"] = build_annual_bill_upcoming_notice(
        site["name"], site["plan_name"], annual_bill, portal_site["shortcode"], portal_site["id"]
    )


# TODO: remove this check at the beginning of August 2026 (BLOCKMAP B51; I14 re-evaluates).
def check_annual_bill_in_progress(site_context) -> None:
    """B51: the "ITS is in the process of billing" alert, as a produced key."""
    site, portal_site, annual_bill = _billing_inputs(site_context)
    site_context["annual_bill_in_progress"] = build_annual_bill_in_progress_notice(
        site["name"], site["plan_name"], annual_bill, portal_site["shortcode"]
    )

"""Plans layer: plan catalog, cost model, and the recommendation notice.

Moved out of the main script at campaign I7 (CAMPAIGN.md section 3.1, development/
2026-07-20-mod-I7-plans/SPEC.md).
"""
import copy
import dataclasses
import datetime
import sys

import numpy as np
from rich.markup import escape

import script_context as sc
from psh.configuration import umich_enabled
from psh.db import db_retry, load_overage_protection_window
from psh.gateway import terminus

cost_table_columns = [
    {"name": "plan", "label": "Plan"},
    {"name": "cost-same", "label": "Same Traffic Cost"},
    {"name": "cost-median", "label": "Median Traffic Cost"},
    {"name": "notes", "label": ""},
]


def overage_blocks(overage: int, overage_block_size: int) -> int:
    """Number of overage blocks billed for `overage` visits (rounded to the nearest block)."""
    return round((overage + overage_block_size / 2.0) / overage_block_size)


def contract_year_end(report_date: datetime.date) -> bool:
    """True if `report_date` is in the U-M contract-year-end window (June 16-29)."""
    return report_date.month == 6 and 16 <= report_date.day < 30  # noqa: PLR2004 -- verbatim move; the U-M contract-year-end window boundaries (CAMPAIGN.md section 3.1: moves get no algorithmic redesign)


def plan_costs(  # noqa: C901, PLR0912, PLR0913 -- moved verbatim (CAMPAIGN.md section 3.1: moves get no algorithmic redesign); the 10-arg signature is pinned by test_plan_costs.py/test_property_plan.py and the recommend_plan call site (SPEC D-i7-2)
    plan_info,
    plan_names,
    visits_by_month,
    v,
    estimate,
    end_date_yyyy_mm,
    site_plan_start,
    overage_block_size,
    overage_block_cost,
    op_lookup,
) -> tuple[dict, dict, dict, float]:
    """Project each plan's annual cost for a site and pick per-plan cost metrics.

    Pure cost model extracted from main().  ``op_lookup(month) -> PantheonOverageProtection
    | None`` injects the overage-protection state so this function does no DB I/O.  Returns
    ``(cost_same, costs_median, costs_best, median_visitors)``.  Only invoked when a site has
    more than four months of data (main() leaves ``median_visitors = 0`` otherwise).
    """
    sc.debug("[bold magenta]=== Generating plan recommendations:")
    sc.debug("===== future costs for same traffic")
    cost_same = {}
    costs_median = {}
    for plan in plan_names:
        cost = float(plan_info[plan]["cost"])
        cost_by_month = []
        cost_for_plan_months = []
        op_remaining = 0
        for month in visits_by_month:
            visits = visits_by_month[month]
            if month == end_date_yyyy_mm and estimate > 0:
                visits = estimate
            overage = max(visits - int(plan_info[plan]["traffic_limit"]), 0)
            overage_cost = (
                overage_blocks(overage, overage_block_size) * overage_block_cost
            )
            if plan != "Basic":
                op = op_lookup(month)
                if op is not None:
                    if op.used_this_month:
                        overage_cost = 0
                else:
                    if month.endswith("-01"):
                        op_remaining = 4
                    if overage > 0 and op_remaining > 0:
                        overage_cost = 0
                        op_remaining -= 1
            cost += overage_cost
            cost_by_month.append(overage_cost)
            if month >= site_plan_start.strftime("%Y-%m"):
                cost_for_plan_months.append(overage_cost)
        if len(cost_by_month) < 12:  # noqa: PLR2004 -- verbatim move; months per year (CAMPAIGN.md section 3.1: moves get no algorithmic redesign)
            cost += (12 - len(cost_by_month)) * np.median(cost_for_plan_months)
        cost_same[plan] = cost
        sc.debug(f"{plan}: ${cost:,.2f}")

    v = list(v)
    if estimate > 0:
        v[-1] = estimate
    median_visitors = np.median(v)
    sc.debug(f"Median Pantheon visitors per month: {median_visitors:,.0f}")
    sc.debug("===== future costs for median traffic")
    for plan in plan_names:
        overage = median_visitors - int(plan_info[plan]["traffic_limit"])
        overage = max(overage, 0)
        months_without_op = 12 if plan == "Basic" else 8
        costs_median[plan] = (
            float(plan_info[plan]["cost"])
            + overage_blocks(overage, overage_block_size)
            * overage_block_cost
            * months_without_op
        )
        sc.debug(f"{plan}: ${costs_median[plan]:,.2f}")

    # find best costs
    # For each plan, we want to be conservative by picking the highest cost metric:
    costs_best = {p: max(cost_same[p], costs_median[p]) for p in plan_names}
    return cost_same, costs_median, costs_best, median_visitors


def build_plan_over_time(plan_on_day: dict, plot_right_date: datetime.date) -> list:
    """
    Collapse a {date: plan_name} mapping into a list of contiguous plan spans,
    each `{"start", "end", "plan"}`, with the final span ending at plot_right_date.

    Returns [] for an empty mapping (a site with no traffic history); callers must
    guard that case before using the result, since the plan/graph sections assume at
    least one traffic day (see P10 -- indexing days[0] on an empty dict raised IndexError).
    """
    plan_over_time = []
    days = sorted(plan_on_day.keys())
    if not days:
        return plan_over_time
    plan = plan_on_day[days[0]]
    plan_start = days[0]
    for i in range(1, len(days)):
        today = days[i]
        if plan_on_day[today] != plan:
            plan_over_time.append(
                {"start": plan_start, "end": days[i - 1], "plan": plan}
            )
            plan_start = today
            plan = plan_on_day[plan_start]
    plan_over_time.append({"start": plan_start, "end": plot_right_date, "plan": plan})
    return plan_over_time


def build_plan_recommendation_notice(  # noqa: PLR0913 -- moved verbatim (CAMPAIGN.md section 3.1: moves get no algorithmic redesign); 6-arg signature pinned by test_plan_recommendation_notice.py and the recommend_plan call site
    site_name, current_plan, recommended_plan, savings, portal_site_id, umich
):
    """The its-recommends-plan notice.  umich selects the U-M (portal-linked) or generic copy."""
    if umich:
        message = f"""
<p><a href="https://admin.webservices.umich.edu/sites/{portal_site_id}/plan/">Moving <strong>{site_name}</strong>
to Pantheon's <strong>{recommended_plan}</strong> plan</a> may save you up to <strong>${savings:,.2f}</strong>
over the coming year if the site's traffic for the next 12 months is similar to the previous 12.</p>
<p>You may want to stay on the <strong>{current_plan}</strong> plan if the site has had one-time traffic spikes
or you think site traffic will be decreasing soon. Sites can move to higher plans any time, but can only be moved to
a lower plan between June 16 - 30 each year.</p>
"""
        text = f"""
Moving {site_name} to Pantheon's {recommended_plan} plan
<https://admin.webservices.umich.edu/sites/{portal_site_id}/plan/>
may save you up to ${savings:,.2f} over the coming year if the site's
traffic for the next 12 months is similar to the previous 12.

You may want to stay on the {current_plan} plan if the site
has had one-time traffic spikes or you think site traffic will be
decreasing soon. Sites can move to higher plans any time, but can only
be moved to a lower plan between June 16 - 30 each year.
"""
    else:
        message = f"""
<p>Moving <strong>{site_name}</strong>
to Pantheon's <strong>{recommended_plan}</strong> plan may save you up to <strong>${savings:,.2f}</strong>
over the coming year if the site's traffic for the next 12 months is similar to the previous 12.</p>
<p>You may want to stay on the <strong>{current_plan}</strong> plan if the site has had one-time traffic spikes
or you think site traffic will be decreasing soon.</p>
"""
        text = f"""
Moving {site_name} to Pantheon's {recommended_plan} plan
may save you up to ${savings:,.2f} over the coming year if the site's
traffic for the next 12 months is similar to the previous 12.

You may want to stay on the {current_plan} plan if the site
has had one-time traffic spikes or you think site traffic will be
decreasing soon.
"""
    return {
        "type": "info",
        "icon": "&#x1F50E;",  # magnifying glass
        "csv": f"{site_name},its-recommends-plan,{current_plan},{recommended_plan},{savings:.2f}",
        "short": "plan change recommended",
        "message": message,
        "text": text,
    }


@dataclasses.dataclass(frozen=True)
class PlanInfo:
    """One [Pantheon].plan_info entry, typed (CAMPAIGN.md section 6, campaign I7)."""

    cost: float
    traffic_limit: int
    upgrade_at: int
    upgrade_to: str | None
    downgrade_to: str | None


@dataclasses.dataclass(frozen=True)
class PlanCatalog:
    """The typed view over [Pantheon].plan_info plus the two overage constants.

    from_config() performs the B12 "-" -> None normalization MUTATING the plan_info
    sub-dict in place: main()'s plan_info alias and the chart/annual-billing regions
    (I11/I12) read the same object, and a copy would fork two views of one config.
    plan_info/plan_names are the raw views main() aliases; plans is the typed view --
    its heavy consumers arrive as I11/I12 move their regions (SPEC D-i7-2).
    """

    plan_info: dict
    plan_names: list[str]
    plans: dict[str, PlanInfo]
    overage_block_size: int
    overage_block_cost: float

    @classmethod
    def from_config(cls, pantheon_config: dict, *, overage_block_size: int,
                    overage_block_cost: float) -> "PlanCatalog":
        plan_info = pantheon_config["plan_info"]
        for plan in plan_info:
            upgrade_to = plan_info[plan]["upgrade_to"]
            downgrade_to = plan_info[plan]["downgrade_to"]
            plan_info[plan]["upgrade_to"] = upgrade_to if upgrade_to != "-" else None
            plan_info[plan]["downgrade_to"] = (
                downgrade_to if downgrade_to != "-" else None
            )
        plans = {
            name: PlanInfo(
                cost=float(info["cost"]),
                traffic_limit=int(info["traffic_limit"]),
                upgrade_at=int(info["upgrade_at"]),
                upgrade_to=info["upgrade_to"],
                downgrade_to=info["downgrade_to"],
            )
            for name, info in plan_info.items()
        }
        return cls(plan_info=plan_info, plan_names=list(plan_info.keys()), plans=plans,
                   overage_block_size=overage_block_size,
                   overage_block_cost=overage_block_cost)


def resolve_plan_name(site: dict) -> str | None:
    """Resolve the billing plan name for a site (B17).

    Pantheon uses the same display name (but a different SKU) for each Elite plan, so an
    Elite site's real plan comes from `terminus plan:info` via [Pantheon].plan_sku_to_name.
    Returns None on a transient/undecodable Terminus failure (caller skips the site --
    loop control stays in main(), SPEC D-i7-1); unknown/missing SKU stays fatal.
    """
    if site["plan_name"] != "Elite":
        return site["plan_name"]
    site_plan_info, errors, fatal = terminus("plan:info", site["name"])
    if fatal or site_plan_info is None:
        # A transient/undecodable Terminus failure for one site skips that site rather
        # than aborting the whole run (consistent with the other per-site terminus calls).
        sc.console.print(
            f":exclamation: [bold red] ERROR: could not fetch plan info for {site['name']}: {escape(errors)}"
        )
        return None
    if "sku" not in site_plan_info:
        sc.console.print(
            f":exclamation: [bold red] ERROR: {site['name']} doesn't have a plan SKU"
        )
        sys.exit("Bailing out.")
    plan_sku = site_plan_info["sku"]
    if plan_sku not in sc.config["Pantheon"]["plan_sku_to_name"]:
        sc.console.print(
            f":exclamation: [bold red] ERROR: {site['name']} has an unknown plan SKU: {plan_sku}"
        )
        sys.exit("Bailing out.")
    return sc.config["Pantheon"]["plan_sku_to_name"][plan_sku]


@dataclasses.dataclass(frozen=True)
class PlanRecommendation:
    """Everything main() and the site_pre_render contract need from the cost model."""

    months_until_recommendations: int
    median_visitors: float
    cost_same: dict
    costs_median: dict
    costs_best: dict
    cost_table_rows: dict
    current_plan: str
    recommended_plan: str
    current_plan_index: int
    recommended_plan_index: int
    savings: float
    estimate_start_date: datetime.date
    estimate_end_date: datetime.date
    savings_entry: dict | None


def recommend_plan(  # noqa: C901, PLR0912, PLR0913, PLR0915 -- moved verbatim (CAMPAIGN.md section 3.1: moves get no algorithmic redesign); one flow input per param (B47 seam, SPEC D-i7-7)
    db_session, site, catalog, visits_by_month, site_plan_start, estimate,
    start_date, end_date, portal_site_id, site_context,
) -> PlanRecommendation:
    """Compare the site's current plan cost to every other plan and recommend the cheapest.

    Extracted verbatim from main()'s per-site loop (B47) at campaign I7 (SPEC D-i7-7).  Adds
    the upgrade recommendation notice to site_context itself (it holds the context, the I6
    flow-function pattern) and returns a PlanRecommendation the caller unpacks into the
    template locals; main() keeps the run accumulators, appending savings_entry to
    site_savings when it is not None.  Returns default (no-recommendation) values when the
    site has 4 or fewer in-window months -- no overage-protection DB read happens then.
    """
    plan_info = catalog.plan_info
    plan_names = catalog.plan_names
    overage_block_size = catalog.overage_block_size
    overage_block_cost = catalog.overage_block_cost
    site_current_plan = site["plan_name"]
    end_date_yyyy_mm = end_date.strftime("%Y-%m")
    savings = 0.0
    savings_entry = None
    site_recommended_plan = site["plan_name"]
    site_current_plan_index = 0
    site_recommended_plan_index = 0
    costs_best = {}  # set only on the >4-month path; kept for the PlanRecommendation return

    # Compare current plan cost to other plan costs

    median_visitors = 0
    cost_same = {}
    costs_median = {}
    cost_table_rows = {}
    estimate_start_date = (
        end_date  # default both estimate start/end dates to the report end date
    )
    estimate_end_date = end_date
    k = [
        d for d in visits_by_month if d >= site_plan_start.strftime("%Y-%m")
    ]
    v = [visits_by_month[d] for d in k]
    months_until_recommendations = 0 if len(v) > 4 else 5 - len(v)  # noqa: PLR2004 -- verbatim move; a recommendation needs >4 in-window months (CAMPAIGN.md section 3.1: moves get no algorithmic redesign)
    if len(v) > 4:  # noqa: PLR2004 -- verbatim move; a recommendation needs >4 in-window months (CAMPAIGN.md section 3.1: moves get no algorithmic redesign)

        # One ranged query for the whole window, snapshotted as plain data; plan_costs()
        # then does ~91 dict lookups instead of ~91 committed round trips to a remote
        # RDS.  Safe because nothing writes to pantheon_overage_protection between
        # build_traffic_table_rows()' commit (which main() now runs before this function,
        # above the recommendation) and these plan_costs() reads.
        overage_protection = db_retry(
            db_session,
            lambda: load_overage_protection_window(
                db_session, site, start_date, end_date
            ),
            what=f"loading overage protection for {site['name']}",
            site=site["name"],
        )

        def op_lookup(month):
            return overage_protection.get(
                datetime.date.fromisoformat(month + "-01")
            )

        cost_same, costs_median, costs_best, median_visitors = plan_costs(
            plan_info,
            plan_names,
            visits_by_month,
            v,
            estimate,
            end_date_yyyy_mm,
            site_plan_start,
            overage_block_size,
            overage_block_cost,
            op_lookup,
        )
        # find the key in costs_best with the lowest value:
        site_recommended_plan = min(costs_best, key=lambda plan: costs_best[plan])

        if site["plan_name"] != site_recommended_plan:
            site_current_plan_index = plan_names.index(site["plan_name"])
            site_recommended_plan_index = plan_names.index(site_recommended_plan)
            savings = abs(
                cost_same[site["plan_name"]] - costs_best[site_recommended_plan]
            )
            if site_current_plan_index > site_recommended_plan_index:
                if site_recommended_plan == "Basic":
                    # Basic is a better deal, but only if the site owner isn't using Performance features
                    # other than Overage Protection.
                    # TODO: check to see if performance features are in use
                    #    New Relic, Solr, Redis, WP/Drupal Multisite
                    if site_current_plan == "Performance Small":
                        site_recommended_plan = "Performance Small"
                        savings = 0
                    # check to see if there is a plan between the current plan and Basic that also saves money
                    if site_current_plan_index > 1:  # not already Performance Small
                        sc.console.print(
                            f"Checking for a better plan between {site_current_plan} and Basic"
                        )
                        bc = copy.copy(costs_best)
                        del bc["Basic"]
                        alt = min(bc, key=lambda plan: bc[plan])
                        sc.console.print(f"cheapest plan excluding Basic: {alt}")
                        if alt != site_current_plan:
                            sc.console.log(f"Found a better plan: {alt}")
                            savings = abs(
                                cost_same[site["plan_name"]] - costs_best[alt]
                            )
                            site_recommended_plan = alt
                        else:
                            site_recommended_plan = site_current_plan
                            savings = 0
                    # TODO: if Basic still looks best, give a special message recommending switching to Basic.
                # D-i7-4 (campaign I7): every surviving downgrade recommendation
                # reaches the operator's savings summary -- non-Basic downgrades
                # used to vanish from it.  Still no owner notice (campaign non-goal;
                # README TODO).
                savings_entry = {
                    "site": site["name"],
                    "savings": savings,
                    "current_plan": site["plan_name"],
                    "recommended_plan": site_recommended_plan,
                }
            else:
                site_context.add_notice(
                    build_plan_recommendation_notice(
                        site["name"], site["plan_name"], site_recommended_plan,
                        savings, portal_site_id, umich_enabled(),
                    )
                )
                savings_entry = {
                    "site": site["name"],
                    "savings": savings,
                    "current_plan": site["plan_name"],
                    "recommended_plan": site_recommended_plan,
                }

        sc.debug(
            f"Best plan for {site['name']} is {site_recommended_plan} "
            f"at ${costs_best[site_recommended_plan]:,.2f}"
        )
        for plan in plan_names:
            cost_table_rows[plan] = {}
            cost_table_rows[plan]["plan"] = plan
            cost_table_rows[plan]["cost-same"] = f"${cost_same[plan]:,.2f}"
            cost_table_rows[plan]["cost-median"] = f"${costs_median[plan]:,.2f}"
            cost_table_rows[plan]["notes"] = ""
            if plan == site_recommended_plan:
                cost_table_rows[plan]["notes"] = (
                    '<span class="pill pill-warning">Recommended Plan</span>'
                )
            if plan == site["plan_name"]:
                if cost_table_rows[plan]["notes"] != "":
                    cost_table_rows[plan]["notes"] += " &nbsp; "
                cost_table_rows[plan]["notes"] += (
                    '<span class="pill pill-primary">Current Plan</span>'
                )
            cost_table_rows[plan]["recommend"] = (
                "Yes" if plan == site_recommended_plan else "No"
            )

        estimate_start_date = (
            end_date.replace(day=1) + datetime.timedelta(days=32)
        ).replace(day=1)
        estimate_end_date = estimate_start_date.replace(
            year=estimate_start_date.year + 1
        ) - datetime.timedelta(days=1)

    return PlanRecommendation(
        months_until_recommendations=months_until_recommendations,
        median_visitors=median_visitors,
        cost_same=cost_same,
        costs_median=costs_median,
        costs_best=costs_best,
        cost_table_rows=cost_table_rows,
        current_plan=site_current_plan,
        recommended_plan=site_recommended_plan,
        current_plan_index=site_current_plan_index,
        recommended_plan_index=site_recommended_plan_index,
        savings=savings,
        estimate_start_date=estimate_start_date,
        estimate_end_date=estimate_end_date,
        savings_entry=savings_entry,
    )


def stuff_plans_contract(site_context, current_plan: str, recommended_plan: str,
                         costs: dict, savings: float) -> None:
    """Publish the site_pre_render contract keys (psh.modules.CONTRACT is authoritative).

    costs is {"same": {plan: cost}, "median": {...}, "best": {...}} -- {} when the site
    has too few in-window months for a recommendation.  recommended_plan equals
    current_plan when no change is recommended."""
    site_context["current_plan"] = current_plan
    site_context["recommended_plan"] = recommended_plan
    site_context["plan_costs"] = costs
    site_context["savings"] = savings

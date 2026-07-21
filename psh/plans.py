"""Plans layer: plan catalog, cost model, and the recommendation notice.

Moved out of the main script at campaign I7 (CAMPAIGN.md section 3.1, development/
2026-07-20-mod-I7-plans/SPEC.md).
"""
import dataclasses
import datetime
import sys

import numpy as np
from rich.markup import escape

import script_context as sc
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

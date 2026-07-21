"""Traffic layer: metrics gather, DB update/load flow, and per-month aggregation.

Moved out of the main script at campaign I6 (CAMPAIGN.md section 3.1, development/
2026-07-20-mod-I6-traffic/SPEC.md).  Holds the traffic-report table columns, the
older-metrics backfill, the extracted per-site gather/load flow (B22-B24, B26 -- loop
control stays in main(), these functions signal via return values, SPEC D-i6-1), and the
B43 visits-by-month aggregation.  build_traffic_table_rows remains one of db_retry()'s
five named idempotent units (CLAUDE.md section Database).

overage_blocks is imported from psh.plans (bridge discharged at I7 per LEDGER I6).
"""
import calendar
import datetime

from rich.markup import escape

import script_context as sc
from psh.db import (
    PantheonOverageProtection,
    TrafficRow,
    db_retry,
    insert_traffic_rows,
    load_traffic_rows,
    update_traffic_rows,
)
from psh.gateway import TerminusError, terminus, terminus_data
from psh.plans import overage_blocks

traffic_table_columns = [
    {"name": "month", "label": "Month"},
    {"name": "visitors", "label": "Pantheon Visitors"},
    {"name": "month", "label": "Month"},
    {"name": "visitors", "label": "Pantheon Visitors"},
    {"name": "plan", "label": "Plan"},
    {"name": "plan-limit", "label": "Plan Limit"},
    {"name": "overage", "label": "Overage"},
    {"name": "overage-blocks", "label": "Overage Blocks"},
    {"name": "overage-cost", "label": "Overage Cost"},
    {"name": "overage-protection", "label": "Overage Protection"},
    {"name": "upgrade-at", "label": "Upgrade At"},
    {"name": "next-plan", "label": "Upgrade To"},
    {"name": "downgrade-at", "label": "Downgrade At"},
    {"name": "previous-plan", "label": "Downgrade To"},
]


def get_old_metrics(
    site_env: str, site: dict, period: str, end_date: datetime.date
) -> list[dict]:
    sc.console.print(f"[bold magenta]=== Processing old data by {period}:")
    try:
        metrics = terminus_data("env:metrics", site_env, f"--period={period}")
    except TerminusError as e:
        # Older-metrics import is best-effort supplementary data: a transient/undecodable
        # failure for one site returns no rows (import nothing) rather than raising and
        # aborting the whole run.
        sc.console.print(
            f":exclamation: [bold red] ERROR: could not fetch {period} metrics for "
            f"{site['name']}: {escape(str(e))}"
        )
        return []
    new_rows = []

    for e in metrics["timeseries"]:
        entry = metrics["timeseries"][e]
        if entry["visits"] == 0 and entry["pages_served"] == 0:
            sc.debug(f"No traffic for {period} {entry['datetime']}")
            continue

        traffic_date = datetime.datetime.strptime(  # noqa: DTZ007 -- Pantheon env:metrics timestamps are naive date markers; only .date() is taken, and attaching a tzinfo risks an off-by-one-day shift (a behavior change a move may not make)
            entry["datetime"], "%Y-%m-%dT%H:%M:%S"
        ).date()
        if period == "week":
            days_in_period = 7
        else:
            _, days_in_period = calendar.monthrange(
                traffic_date.year, traffic_date.month
            )

        visits_per_day = entry["visits"] // days_in_period
        visits_last_day = visits_per_day + entry["visits"] % days_in_period
        pages_served_per_day = entry["pages_served"] // days_in_period
        pages_served_last_day = (
            pages_served_per_day + entry["pages_served"] % days_in_period
        )
        cache_hits_per_day = entry["cache_hits"] // days_in_period
        cache_hits_last_day = cache_hits_per_day + entry["cache_hits"] % days_in_period

        sc.debug(
            f"traffic/day for {period} starting {traffic_date}: visits={visits_per_day} "
            f"pages={pages_served_per_day} cache_hits={cache_hits_per_day}",
            level=2,
        )

        for i in range(days_in_period):
            if traffic_date < end_date:
                if i < days_in_period - 1:
                    daily_traffic = {
                        "site_id": site["id"],
                        "traffic_date": traffic_date,
                        "site_plan": site["plan_name"],
                        "visits": visits_per_day,
                        "pages_served": pages_served_per_day,
                        "cache_hits": cache_hits_per_day,
                    }
                else:
                    daily_traffic = {
                        "site_id": site["id"],
                        "traffic_date": traffic_date,
                        "site_plan": site["plan_name"],
                        "visits": visits_last_day,
                        "pages_served": pages_served_last_day,
                        "cache_hits": cache_hits_last_day,
                    }
                new_rows.append(daily_traffic)
            traffic_date += datetime.timedelta(days=1)

    return new_rows


def estimate_month_visits(visits_by_month, dates, last_day, end_day) -> int:
    """Extrapolate the final (partial) month's visits.

    Returns -1 when the reporting month is complete or too early to extrapolate (i.e. not
    ``1 < end_day < last_day``), matching the inline behavior it replaces.  ``dates`` is the
    ordered list of month midpoints (datetime.date) whose keys index ``visits_by_month``.
    """
    estimate = -1
    if last_day > end_day > 1:
        extrapolate = (
            visits_by_month[dates[-1].strftime("%Y-%m")] * last_day / (end_day - 1)
        )
        if len(visits_by_month) > 1:
            previous_month = visits_by_month[dates[-2].strftime("%Y-%m")]
            if last_day >= 25:  # noqa: PLR2004 -- extrapolation-weighting day thresholds; inline per the original
                estimate = round(extrapolate)
            elif last_day >= 15:  # noqa: PLR2004 -- extrapolation-weighting day thresholds; inline per the original
                estimate = round((2 * extrapolate + previous_month) / 3)
            else:
                estimate = round((extrapolate + previous_month) / 2)
        else:
            estimate = round(extrapolate)
    return estimate


def build_traffic_table_rows(  # noqa: C901, PLR0912, PLR0915, PLR0913 -- moved verbatim (CAMPAIGN.md section 3.1: moves get no algorithmic redesign); the 12-arg signature is pinned by tests and the main() call site
    session,
    site: dict,
    visits_by_month: dict,
    plan_on_day: dict,
    plan_info: dict,
    site_plan_start: datetime.date,
    first_plan_day: datetime.date,
    last_plan_day: datetime.date,
    start_date: datetime.date,
    end_date: datetime.date,
    overage_block_size: int,
    overage_block_cost: float,
) -> dict:
    """Build the report's per-month traffic table and persist overage-protection state.

    Idempotent, so db_retry() may re-run it after a rollback: every local (traffic_table_rows,
    op_remaining, old_plan) is reset on entry, and the PantheonOverageProtection rows are
    get-or-create by primary key.  Extracting this block out of main() is what makes that true --
    see SPEC 3.3.1 for what a statement-level retry would corrupt instead.
    """
    traffic_table_rows = {}
    d = (start_date.replace(day=1) - datetime.timedelta(days=15)).replace(day=1)
    op = session.get(
        PantheonOverageProtection, {"site_id": site["id"], "month": d}
    )
    op_remaining = 0 if op is None else op.months_remaining
    old_plan = None
    for month, month_visits in visits_by_month.items():
        ymd = datetime.date.fromisoformat(month + "-15")
        ymd1 = ymd.replace(day=1)
        ymd = max(ymd, first_plan_day)
        ymd = min(ymd, last_plan_day)
        ymd1 = max(ymd1, start_date)
        if ymd1 > end_date:
            ymd1 = end_date.replace(day=1)
        if ymd1 < site_plan_start:
            continue
        d = max(ymd, first_plan_day)
        plan = plan_on_day[d]
        if ymd1 == site_plan_start and plan != "Basic":
            op_remaining = 4
        if old_plan in ("Sandbox", "Basic") and plan not in ("Sandbox", "Basic"):
            op_remaining = 4
        old_plan = plan
        traffic_table_rows[month] = {}
        traffic_table_rows[month]["month"] = datetime.datetime.strptime(  # noqa: DTZ007 -- "YYYY-MM" month label parsed only to re-format as "Month YYYY"; no instant, no timezone
            month, "%Y-%m"
        ).strftime("%B %Y")
        traffic_table_rows[month]["visitors"] = f"{month_visits:,.0f}"
        traffic_table_rows[month]["plan"] = plan
        traffic_limit = int(plan_info[plan]["traffic_limit"])
        traffic_table_rows[month]["plan-limit"] = f"{traffic_limit:,.0f}"
        traffic_table_rows[month]["upgrade-at"] = (
            f"{plan_info[plan]['upgrade_at']:,.0f}"
        )
        traffic_table_rows[month]["next-plan"] = plan_info[plan]["upgrade_to"]
        downgrade_to = plan_info[plan]["downgrade_to"]
        if downgrade_to is not None:
            downgrade_at = plan_info[downgrade_to]["upgrade_at"]
            traffic_table_rows[month]["downgrade-at"] = f"{downgrade_at:,.0f}"
            traffic_table_rows[month]["previous-plan"] = downgrade_to
        else:
            traffic_table_rows[month]["downgrade-at"] = "-"
            traffic_table_rows[month]["previous-plan"] = "-"
        overage = max(month_visits - traffic_limit, 0)
        n_blocks = overage_blocks(overage, overage_block_size)
        overage_cost = n_blocks * overage_block_cost
        overage_text = f"{overage:,.0f}"
        overage_blocks_text = f"{n_blocks:,.0f}"
        overage_cost_text = f"${overage_cost:,.0f}"
        overage_protection_status = "-"
        # Overage protection started retroactively on 2024-01-01
        if month >= "2024-01" and plan != "Basic":
            overage_protection_status = ""
            if ymd.month == 1:
                op_remaining = 4
                overage_protection_status = "Set to 4 months, "
            op_used = False
            if overage > 0 and op_remaining > 0:
                op_remaining -= 1
                op_used = True
            op = session.get(
                PantheonOverageProtection, {"site_id": site["id"], "month": ymd1}
            )
            if op is None:
                op = PantheonOverageProtection(
                    site_id=site["id"],
                    month=ymd1,
                    months_remaining=op_remaining,
                    used_this_month=op_used,
                )
                session.add(op)
            else:
                op.months_remaining = op_remaining
                op.used_this_month = op_used
            if op_used:
                overage_protection_status += "used 1 month, "
                overage_cost_text = (
                    '$0 (<span style="font-size:smaller;">waived '
                    + overage_cost_text
                    + ")</span>"
                )
            overage_protection_status += (
                "1 month remaining"
                if op_remaining == 1
                else f"{op_remaining} months remaining"
            )
        else:
            op_remaining = 0
            if plan != "Basic":
                overage_text = "-"
                overage_blocks_text = "-"
                overage_cost_text = "-"
        traffic_table_rows[month]["overage"] = overage_text
        traffic_table_rows[month]["overage-blocks"] = overage_blocks_text
        traffic_table_rows[month]["overage-cost"] = overage_cost_text
        traffic_table_rows[month]["overage-protection"] = overage_protection_status

    session.commit()  # save the changes we made to the pantheon_overage_protection table
    return traffic_table_rows


def update_site_traffic(
    db_session, site: dict, live_site: str, start_date: datetime.date, end_date: datetime.date
) -> bool:
    """Fetch a site's daily env:metrics and merge them into pantheon_traffic.

    Returns False when the metrics fetch was fatal or undecodable (the caller skips the
    site), True once the rows are merged (B22+B23 of main()'s per-site loop).
    """
    metrics, errors, fatal = terminus("env:metrics", live_site, "--period=day")
    if fatal or metrics is None:
        sc.console.print(
            f":exclamation: [bold red] ERROR: could not fetch metrics for {site['name']}: {escape(errors)}"
        )
        return False

    sc.debug(f"[bold magenta]=== Updating metrics for {site['name']}:")
    db_retry(
        db_session,
        lambda: update_traffic_rows(db_session, site, metrics, start_date, end_date),
        what=f"updating traffic rows for {site['name']}",
        site=site["name"],
    )
    return True


def import_older_site_metrics(
    db_session, site: dict, live_site: str, end_date: datetime.date
) -> None:
    """Backfill daily rows from Pantheon's weekly/monthly aggregates (B24; --import-older-metrics)."""
    sc.console.print(
        f"[bold magenta]=== Importing older metrics for {site['name']}:"
    )
    # The terminus call stays OUTSIDE the retried unit: a retry must not re-run it.
    # Order (fetch week -> insert week -> fetch month -> insert month) is unchanged.
    for period in ("week", "month"):
        new_rows = get_old_metrics(live_site, site, period, end_date)
        db_retry(
            db_session,
            lambda rows=new_rows: insert_traffic_rows(db_session, rows),
            what=f"importing older {period} metrics for {site['name']}",
            site=site["name"],
        )


def load_site_traffic(
    db_session, site: dict, start_date: datetime.date, end_date: datetime.date
) -> list[TrafficRow]:
    """Load the report window's TrafficRows and release the DB connection (B26).

    The retried unit is load_traffic_rows(), whose post-SELECT commit releases the
    connection before the multi-minute per-site gather -- see load_traffic_rows().
    """
    results = db_retry(
        db_session,
        lambda: load_traffic_rows(db_session, site, start_date, end_date),
        what=f"loading traffic rows for {site['name']}",
        site=site["name"],
    )
    sc.debug(
        f"{len(results)} records found in the database for {site['name']} "
        f"between {start_date} and {end_date}:",
        level=2,
    )
    return results


def aggregate_visits_by_month(
    rows: list[TrafficRow], start_date: datetime.date, end_date: datetime.date
) -> tuple[dict[str, int], dict[datetime.date, str]]:
    """Aggregate TrafficRows into (visits_by_month, plan_on_day) -- B43's aggregation.

    visits_by_month seeds every "%Y-%m" month in [start_date, end_date] to 0, then sums
    row.visits into its month; plan_on_day maps each row's traffic_date to its site_plan
    (last row wins).  Rows are assumed in-window (load_traffic_rows() returns only such);
    an out-of-window month KeyErrors, exactly as the inline code this replaces did.
    """
    visits_by_month: dict[str, int] = {}
    plan_on_day: dict[datetime.date, str] = {}
    d = start_date
    while d <= end_date:
        month = d.strftime("%Y-%m")
        visits_by_month[month] = 0
        d = d.replace(day=1) + datetime.timedelta(days=32)
        d = d.replace(day=1)
    for row in rows:
        month = row.traffic_date.strftime("%Y-%m")
        visits_by_month[month] += row.visits
        plan_on_day[row.traffic_date] = row.site_plan
    return visits_by_month, plan_on_day

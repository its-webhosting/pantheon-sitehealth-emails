"""The per-site traffic chart: cap geometry, data prep, matplotlib build -> PNG bytes.

Moved out of main()'s per-site loop by campaign increment I11 (CAMPAIGN.md section 3.1:
B13's cap-shape geometry + B44 chart data prep + B45 matplotlib build).  main() calls
build_chart() with the shaped per-site locals (SPEC D-i11-1) and attaches the returned
PNG to the report email (B55, still in psh/_legacy.py until I12).

Precondition (documented, not handled -- the D-i6-4 posture): plan_on_day must contain
every month midpoint clamped to [first_plan_day, last_plan_day].  Production data always
satisfies this (plan_on_day maps every traffic-row date, and first_plan_day /
last_plan_day are its min/max), and a violation raises KeyError exactly as the pre-move
code did.

Two scoped-suppression families live in this file (each site carries the narrowest
per-line ignore; see SPEC section 5):
- pyright reportArgumentType: matplotlib's stubs reject runtime-valid dynamic API use
  (datetime bin edges, BarContainer unions, NDArray xlims, tuple transform points);
  the code is moved verbatim and exercised end-to-end by the e2e goldens.
- pyright reportPossiblyUnboundVariable: ax_surge / est_bars / bars are bound iff the
  surge branch or the axes loop ran, which pyright cannot correlate.  A None init would
  trade these for optional-member errors and a fabricated default would silently draw
  on the wrong axes (PD#1) -- the loud runtime NameError is the correct failure mode.
"""

import datetime
import io
from typing import Any

import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec
from matplotlib.patches import Polygon

import script_context as sc


def build_chart(  # noqa: C901, PLR0912, PLR0913, PLR0915  # moved verbatim from main() (CAMPAIGN.md §3.1: no algorithmic redesign in a move); arg set = the shaped main() locals the chart consumes
    site: dict,
    site_url: str,
    visits_by_month: dict[str, int],
    plan_on_day: dict[datetime.date, str],
    plan_info: dict,
    plan_over_time: list[dict],
    dates: list[datetime.date],
    estimate: int,
    first_plan_day: datetime.date,
    last_plan_day: datetime.date,
    start_date: datetime.date,
    end_date: datetime.date,
    plot_right_date: datetime.date,
) -> bytes:
    """Build the per-site traffic chart and return it as PNG bytes."""
    # Generate a cap shape to use at the end of the traffic surge chart bars
    cap_size = 2 * np.pi
    x = np.linspace(0, cap_size, 31)
    y = (np.sin(x - np.pi / 2) + 1) / 2
    cap_points = np.array(list(zip(x, y, strict=True)))
    cap_points_inv = np.concatenate(
        ([[0, 0]], cap_points - [0, 1], [[cap_size, 0]]), axis=0
    )
    cap_points = np.concatenate(([[0, 0]], cap_points, [[cap_size, 0]]), axis=0)

    end_date_yyyy_mm = end_date.strftime("%Y-%m")
    visits = list(visits_by_month.values())
    visits_covered_by_month = {}
    for month, month_visits in visits_by_month.items():
        ymd = datetime.date.fromisoformat(month + "-15")
        ymd = max(ymd, first_plan_day)
        ymd = min(ymd, last_plan_day)
        visits_covered_by_month[month] = min(
            month_visits,
            int(plan_info[plan_on_day[ymd]]["traffic_limit"]),
        )
    visits_covered = list(visits_covered_by_month.values())

    xbins = [
        # Month keys are naive date labels; attaching a tzinfo could shift the bin
        # edge by a day, a behavior change a move may not make.
        datetime.datetime.strptime(d, "%Y-%m").replace(day=1)  # noqa: DTZ007
        for d in visits_by_month
    ]
    xbins.append(
        datetime.datetime.combine(plot_right_date, datetime.datetime.min.time())
        + datetime.timedelta(days=1)
    )

    # Convert dates to numerical format
    dates_num = mdates.date2num(np.array(dates))

    #
    # Create the chart
    #
    sc.debug(f"[bold magenta]=== Creating chart for {site['name']}:")

    estimates = []
    if estimate != -1:
        estimates_by_month = visits_covered_by_month.copy()
        for month in estimates_by_month:
            estimates_by_month[month] = 0
        estimates_by_month[end_date_yyyy_mm] = estimate
        estimates = list(estimates_by_month.values())

    # figure out whether to show a traffic surge chart
    upgrade_at_max = 0
    for plan in plan_over_time:
        upgrade_at = plan_info[plan["plan"]]["upgrade_at"]
        upgrade_at_max = max(upgrade_at_max, upgrade_at)
    surge_threshold = upgrade_at_max * 1.5
    visits_max = max(visits)
    surge = visits_max > surge_threshold

    visits_plan = [v if v <= surge_threshold else upgrade_at_max for v in visits]

    # set the plot height: top data point plus 15% for annotations and labels
    ymax = max(visits_max, upgrade_at_max) * 1.15

    if surge:
        fig = plt.figure()
        fig.set_size_inches(12, 12)
        gs = GridSpec(2, 1, height_ratios=[1, 2], hspace=0.1)
        ax_surge = fig.add_subplot(gs[0])
        ax_plan = fig.add_subplot(gs[1], sharex=ax_surge)
        axs = [ax_plan, ax_surge]
        ax_top = ax_surge
        ax_surge.set_ylim(surge_threshold, ymax)
        ax_plan.set_ylim(0, surge_threshold)
        ax_surge.spines.bottom.set_visible(False)
        ax_surge.xaxis.set_visible(False)
        ax_plan.spines.top.set_visible(False)
    else:
        fig, ax_plan = plt.subplots()
        fig.set_size_inches(12, 9)
        axs = [ax_plan]
        ax_top = ax_plan
        ax_plan.set_ylim(0, ymax)

    for ax in axs:
        est_bars = []
        if estimate >= 0:
            _, _, est_bars = ax.hist(
                dates_num,
                bins=xbins,  # pyright: ignore[reportArgumentType]
                weights=estimates,
                histtype="barstacked",
                color="lemonchiffon",
                edgecolor="black",
            )
            est_labels = ax.bar_label(
                est_bars,  # pyright: ignore[reportArgumentType]
                fmt="{:,.0f}",
                backgroundcolor=(1.0, 1.0, 1.0, 0.0),
                fontstyle="italic",
                fontsize="small",
                padding=5,
                zorder=3.5,
                path_effects=[
                    path_effects.Stroke(linewidth=3, foreground="white"),
                    path_effects.Normal(),
                ],
            )
            for i in range(len(est_labels) - 1):
                est_labels[i].set(
                    visible=False
                )  # only show the label for the last month's estimate
            est_labels[-1].set_text(
                f"{estimate:,}\n(estimate)\n"
                f"{last_plan_day.strftime('%b ') + str(last_plan_day.day)}"
            )
            est_labels[-1].set_fontsize("small")
            est_labels[-1].set_path_effects(
                [
                    path_effects.Stroke(linewidth=3, foreground="white"),
                    path_effects.Normal(),
                ]
            )

        _, _, bars = ax.hist(
            dates_num,
            bins=xbins,  # pyright: ignore[reportArgumentType]
            weights=visits,
            histtype="barstacked",
            color="tab:pink",
            edgecolor="black",
        )
        ax.bar_label(
            bars,  # pyright: ignore[reportArgumentType]
            labels=[f"{v:,.0f}" for v in visits],
            backgroundcolor=(1.0, 1.0, 1.0, 0.0),
            fontweight="bold",
            padding=5,
            path_effects=[
                path_effects.Stroke(linewidth=3, foreground="white"),
                path_effects.Normal(),
            ],
        )

    gap_bars = []
    gap_bars.extend(est_bars)  # pyright: ignore[reportPossiblyUnboundVariable, reportArgumentType]
    gap_bars.extend(bars)  # pyright: ignore[reportPossiblyUnboundVariable, reportArgumentType]

    # these bars are both below surge_threshold, so we only need to draw them on the plan portion of the chart
    ax_plan.hist(
        dates_num,
        bins=xbins,  # pyright: ignore[reportArgumentType]
        weights=visits_plan,
        histtype="barstacked",
        color="tab:cyan",
        edgecolor="black",
    )
    ax_plan.hist(
        dates_num,
        bins=xbins,  # pyright: ignore[reportArgumentType]
        weights=visits_covered,
        histtype="barstacked",
        color="tab:blue",
        edgecolor="black",
    )

    # Format the x-axis ticks to be in the middle of each month
    left_num = mdates.date2num(start_date)
    right_num = mdates.date2num(plot_right_date)
    ax_plan.set_xlim(left=left_num, right=right_num)  # pyright: ignore[reportArgumentType]
    ax_plan.xaxis.set_major_locator(mdates.MonthLocator(bymonthday=15))
    ax_plan.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.autofmt_xdate()

    # add bar caps between the two charts
    if surge:
        ylim = ax_plan.get_ylim()
        d = (ylim[1] - ylim[0]) * 0.05
        ylim = ax_surge.get_ylim()  # pyright: ignore[reportPossiblyUnboundVariable]
        d2 = (
            ylim[1] - ylim[0]
        ) * 0.10  # surge chart canvas height is 1/2 the plan chart canvas height
        for rect in gap_bars:
            x = rect.get_x()
            w = rect.get_width()
            h = rect.get_height()
            fc = rect.get_facecolor()
            if h >= surge_threshold:
                # bottom cap
                points = cap_points * [w / (2 * np.pi), d] + [x, surge_threshold]
                p = Polygon(
                    points,
                    closed=True,
                    facecolor=fc,
                    clip_on=False,
                    aa=True,
                    snap=True,
                )
                ax_plan.add_patch(p)
                # top cap
                points = cap_points_inv * [w / (2 * np.pi), d2] + [
                    x,
                    surge_threshold,
                ]
                p = Polygon(
                    points,
                    closed=True,
                    facecolor=fc,
                    clip_on=False,
                    aa=True,
                    snap=True,
                )
                ax_surge.add_patch(p)  # pyright: ignore[reportPossiblyUnboundVariable]
                ax_surge.vlines(  # pyright: ignore[reportPossiblyUnboundVariable]
                    x=[x, x + w - 0.00001],
                    ymin=surge_threshold - d2,
                    ymax=surge_threshold,
                    color="black",
                    linewidth=0.8,
                    clip_on=False,
                    aa=True,
                    snap=True,
                )
        # add axes caps
        kwargs: dict[str, Any] = {
            "marker": r"$\sim$",
            "markersize": 10,
            "color": "black",
            "markerfacecolor": "black",
            "markeredgecolor": "none",
            "linestyle": "none",
            "clip_on": False,
        }
        ax_plan.plot([0, 1], [1, 1], transform=ax_plan.transAxes, **kwargs)
        ax_surge.plot([0, 1], [0, 0], transform=ax_surge.transAxes, **kwargs)  # pyright: ignore[reportPossiblyUnboundVariable]

    # Add horizontal lines for plan limit and upgrade/downgrade
    created_upgrade_labels = False
    created_downgrade_labels = False
    i = 0
    for plan in plan_over_time:
        plan_xmin = mdates.date2num(plan["start"])
        plan_xmax = mdates.date2num(plan["end"])
        traffic_limit = int(plan_info[plan["plan"]]["traffic_limit"])
        upgrade_at = plan_info[plan["plan"]]["upgrade_at"]
        if traffic_limit is not None and upgrade_at is not None:
            # Limit and upgrade lines
            for ax in axs:
                limit_text = {}
                upgrade_text = {}
                if not created_upgrade_labels:
                    limit_text["label"] = "plan traffic limit (overages start)"
                    upgrade_text["label"] = (
                        "upgrade to higher plan at "
                        f"{plan_info[plan_over_time[-1]['plan']]['upgrade_at']:,}"
                    )
                    created_upgrade_labels = True
                ax.hlines(
                    y=traffic_limit,
                    xmin=plan_xmin,
                    xmax=plan_xmax,
                    color="darkorange",
                    gapcolor="w",
                    linestyle="dotted",
                    linewidth=3,
                    **limit_text,
                )
                ax.hlines(
                    y=upgrade_at,
                    xmin=plan_xmin,
                    xmax=plan_xmax,
                    color="r",
                    gapcolor="w",
                    linestyle="dashed",
                    linewidth=3,
                    **upgrade_text,
                )
        # Downgrade line
        downgrade_to = plan_info[plan["plan"]]["downgrade_to"]
        if downgrade_to is not None:
            for ax in axs:
                downgrade_text = {}
                ending_downgrade_to = plan_info[plan_over_time[-1]["plan"]][
                    "downgrade_to"
                ]
                if not created_downgrade_labels and ending_downgrade_to is not None:
                    ending_downgrade_at = plan_info[ending_downgrade_to][
                        "upgrade_at"
                    ]
                    downgrade_text["label"] = (
                        "downgrade to lower plan at " + f"{ending_downgrade_at:,}"
                    )
                    created_downgrade_labels = True
                downgrade_at = plan_info[downgrade_to]["upgrade_at"]
                ax.hlines(
                    y=downgrade_at,
                    xmin=plan_xmin,
                    xmax=plan_xmax,
                    color="g",
                    gapcolor="w",
                    path_effects=[
                        path_effects.Stroke(linewidth=4, foreground="white"),
                        path_effects.Normal(),
                    ],
                    linestyle="dashdot",
                    linewidth=3,
                    **downgrade_text,
                )
        # Plan label
        text_height = mpl.rcParams["font.size"] * 1.25
        level = text_height * (i + 2)
        ax_top.annotate(
            plan["plan"],
            xy=(plan_xmin, ymax),
            xycoords="data",
            xytext=(2, 0 - level),
            textcoords="offset points",
            weight="bold",
        )
        # Plan label line calculations
        data_point = (plan_xmin, ymax)
        offset_points = (0, 2 * level + text_height / 2)
        display_point = ax_top.transData.transform_point(
            data_point  # pyright: ignore[reportArgumentType]
        )  # Transform data coord to display (pixel) coord
        # Apply offset in pixels
        dpi = fig.dpi
        offset_in_inches = (offset_points[0] / dpi, offset_points[1] / dpi)
        offset_in_pixels = fig.dpi_scale_trans.transform_point(offset_in_inches)
        text_display_point = (
            display_point[0] + offset_in_pixels[0],
            display_point[1] - offset_in_pixels[1],
        )  # Final display coordinate for the text
        text_data_point = ax_top.transData.inverted().transform_point(
            text_display_point
        )  # Transform to data coord
        text_data_y = text_data_point[1]
        # Draw the plan label line
        for ax in axs:
            ax.vlines(
                x=plan_xmin,
                ymin=traffic_limit,
                ymax=text_data_y,
                color="r",
                linestyle="dotted",
                gapcolor="w",
            )

        i = 1 - i  # alternate plan label levels

    fig.legend(handlelength=3.0)

    ax_plan.set_xlabel("Month", fontsize="large")
    fig.supylabel("Pantheon Visitors")
    for ax in axs:
        ax.yaxis.set_major_formatter("{x:,.0f}")
    chart_title = f"{site['name']} Pantheon Traffic"
    if site_url:
        chart_title += f"\n{site_url}"
    ax_top.set_title(chart_title, loc="left")
    fig.text(
        0.90,
        0.10,
        "as of " + end_date.strftime("%B %e, %Y"),
        ha="right",
        fontsize="small",
    )

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    buf.seek(0)
    chart_image = buf.read()
    buf.close()
    plt.close(fig)

    # TODO: Create SVG chart

    return chart_image

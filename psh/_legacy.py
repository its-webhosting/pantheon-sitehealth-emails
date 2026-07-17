#!/usr/bin/env python
#
# pantheon-sitehealth-emails
#
# Send emails to website owners letting them know what their Pantheon traffic has been and make recommendations about
# whether/how they should change their current plan or the configuration of their site.
#
# Usage:
#   pantheon-sitehealth-emails [-h|--help]
#
# TODO: add WordPress MU plugin check (report on anything except plugin)

import argparse
import calendar
import copy
import datetime
import html
import importlib
import io
import json
import os
import re
import shlex
import signal
import stat
import subprocess
import sys
import time
import tomllib
import urllib.parse
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import make_msgid
from smtplib import SMTP_SSL
from typing import NamedTuple

import matplotlib
import matplotlib.dates as mdates
import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
import numpy as np
import semver
import sqlalchemy as db
from jinja2 import Template
from matplotlib.gridspec import GridSpec
from matplotlib.patches import Polygon
from rich.markup import escape
from rich.padding import Padding
from rich.pretty import pprint
from sqlalchemy import (
    Boolean,
    Date,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    insert,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import CHAR

import dns_classify
import script_context as sc

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

cost_table_columns = [
    {"name": "plan", "label": "Plan"},
    {"name": "cost-same", "label": "Same Traffic Cost"},
    {"name": "cost-median", "label": "Median Traffic Cost"},
    {"name": "notes", "label": ""},
]

fqdn_re = re.compile(r"^_?[a-z0-9-]+\.[a-z0-9.-]+$", re.IGNORECASE)


class Base(DeclarativeBase):
    pass


class PantheonTraffic(Base):
    __tablename__ = "pantheon_traffic"

    # id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(CHAR(36))
    traffic_date: Mapped[datetime.date] = mapped_column(Date)
    site_plan: Mapped[str] = mapped_column(String(64))
    visits: Mapped[int] = mapped_column(Integer)
    pages_served: Mapped[int] = mapped_column(Integer)
    cache_hits: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        PrimaryKeyConstraint("site_id", "traffic_date", name="pk_site_id_traffic_date"),
        UniqueConstraint("site_id", "traffic_date", name="uix_site_id_traffic_date"),
    )

    def __repr__(self):
        return (
            f"<{self.site_id} {self.traffic_date} : {self.site_plan} visits={self.visits} "
            f"pages={self.pages_served} cache_hits={self.cache_hits}>"
        )


class PantheonOverageProtection(Base):
    __tablename__ = "pantheon_overage_protection"

    site_id: Mapped[str] = mapped_column(CHAR(36))
    month: Mapped[datetime.date] = mapped_column(Date)
    months_remaining: Mapped[int] = mapped_column(Integer)
    used_this_month: Mapped[bool] = mapped_column(Boolean)

    __table_args__ = (
        PrimaryKeyConstraint("site_id", "month", name="pk_op_site_id_traffic_date"),
        UniqueConstraint("site_id", "month", name="uix_op_site_id_traffic_date"),
    )

    def __repr__(self):
        return f"<{self.site_id} {self.month} : {self.months_remaining}>"


class TrafficRow(NamedTuple):
    """A pantheon_traffic row, detached from the ORM.

    Plain data on purpose: a db_retry() rollback expires every live ORM object, so a row held
    across a retryable unit would emit an unretried SELECT on the next attribute read -- outside
    every unit of work.  The attribute names match PantheonTraffic's, so consumers of the
    site_post_traffic data-contract key `traffic_rows` are unaffected.  See SPEC 3.3.2.
    """

    site_id: str
    traffic_date: datetime.date
    site_plan: str
    visits: int
    pages_served: int
    cache_hits: int


class OverageProtectionRow(NamedTuple):
    """A pantheon_overage_protection row, detached from the ORM.

    Plain data for the same reason as TrafficRow: load_overage_protection_window() snapshots the
    site's whole window in one unit of work, and plan_costs() reads it minutes later, after other
    db_retry() units may have rolled back (which expires every live ORM object).  The attribute
    names match PantheonOverageProtection's.
    """

    site_id: str
    month: datetime.date
    months_remaining: int
    used_this_month: bool


#
# Global initialization:
#


# Command-line argument parsing.  Building the parser is side-effect-free; parse_args()
# (which reads sys.argv) is only invoked from the __main__ block at the bottom of this
# file, so the module can be imported by the test harness without argv side effects.
# Every function reads sc.options (set by the caller) at call time, not at import time.
def build_arg_parser() -> argparse.ArgumentParser:
    args_parser = argparse.ArgumentParser(
        # Reject option abbreviations (e.g. `--for` resolving to `--for-real`, `--al` to
        # `--all`).  These are dangerous options; requiring the exact spelling is a safety guard.
        allow_abbrev=False,
        description="Send emails to website owners letting them know what their Pantheon traffic has been"
        "and make recommendations about whether/how they should change their current plan or"
        "the configuration of their site.",
    )
    args_parser.add_argument(
        "sites",
        metavar="SITE",
        nargs="*",
        help="a list of site names to process; if not specified, all sites in the Pantheon organization will be processed",
    )
    args_parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        default=False,
        help="process all sites in the Pantheon organization",
    )
    args_parser.add_argument(
        "--resume-from",
        metavar="SITE_NAME",
        action="store",
        default=None,
        help="with --all, start the site loop at SITE_NAME (processing it and every site "
        "after it in sorted order); use to resume an --all run that died or was interrupted",
    )
    args_parser.add_argument(
        "--date",
        "-d",
        type=datetime.date.fromisoformat,
        default=datetime.date.today(),
        help="generate the report as if it were this date (YYYYMMDD or YYYY-MM-DD); defaults to today",
    )
    args_parser.add_argument(
        "--update",
        action="store_true",
        default=False,
        help="just update the site visitors in the database, skipping the reports",
    )
    args_parser.add_argument(
        "--for-real",
        action="store_true",
        default=False,
        help="send email to the site owners; without this option, the emails will go to the logged-in user instead",
    )
    args_parser.add_argument(
        "--config",
        "-c",
        action="store",
        default="pantheon-sitehealth-emails.toml",
        help="TOML configuration file, see pantheon-sitehealth-emails.toml.sample",
    )
    args_parser.add_argument(
        "--only-warn",
        action="store_true",
        default=False,
        help="only check sites for warnings, do not generate reports or send emails",
    )
    args_parser.add_argument(
        "--allow-any-source-ip",
        action="store_true",
        default=False,
        help="skip the Cloudflare egress-IP allowlist check that normally runs before "
        "site cache checks ([Cloudflare.cachecheck])",
    )
    args_parser.add_argument(
        "--smtp-username",
        "-u",
        action="store",
        default=None,
        help="username for logging into the SMTP server to send mail "
        "(overrides [SMTP].username in the config file)",
    )
    args_parser.add_argument(
        "--create-tables",
        action="store_true",
        default=False,
        help="create the database tables and then stop, ignoring all other command line options",
    )
    args_parser.add_argument(
        "--import-older-metrics",
        action="store_true",
        default=False,
        help="load weekly and monthly Pantheon metrics into the database and then stop, "
        "ignoring all other command line options",
    )
    # Refreshing fqdns.json (the map of Cloudflare-proxied FQDNs) from the Cloudflare API is
    # handled by the cloudflare plugin.  --update-cloudflare-fqdns forces a refresh;
    # --no-update-cloudflare-fqdns suppresses the automatic stale-file refresh.  They are
    # contradictory, so make them mutually exclusive (argparse reports the conflict).
    cloudflare_fqdns_group = args_parser.add_mutually_exclusive_group()
    cloudflare_fqdns_group.add_argument(
        "--update-cloudflare-fqdns",
        action="store_true",
        default=False,
        help="force-refresh fqdns.json from Cloudflare before this run "
        "(requires the [Cloudflare] section to be enabled)",
    )
    cloudflare_fqdns_group.add_argument(
        "--no-update-cloudflare-fqdns",
        action="store_true",
        default=False,
        help="suppress the automatic refresh of a stale fqdns.json",
    )
    args_parser.add_argument(
        "--verbose",
        "-v",
        action="count",
        default=0,
        help="include extra information in the output",
    )
    return args_parser


def parse_args(argv=None):
    return build_arg_parser().parse_args(argv)


def escape_url(url):
    return urllib.parse.quote(url, safe=":/?#&=", encoding="utf-8", errors="strict")


from psh.configuration import (
    cloudflare_enabled,
    config_substitution,
    gate_disabled_sections,
    load_news_items,
    process_config,
    umich_enabled,
)
from psh.gateway import (
    GatewayResult,
    TerminusError,
    drush,
    drush_error,
    drush_php_script,
    fix_drush_output,
    run_terminus,
    terminus,
    terminus_data,
    wp,
    wp_error,
    wp_eval,
)


def get_old_metrics(
    site_env: str, site: dict, period: str, end_date: datetime.date
) -> list:
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

        traffic_date = datetime.datetime.strptime(
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


def check_wordpress_plugin(
    site: str,
    installed_plugins: list,
    name: str,
    display_name: str,
    url: str,
    reason: str,
) -> list:
    notices = []
    if not isinstance(installed_plugins, list):
        return notices  # this error should already have been handled by our caller, so skip additional work

    installed = [p for p in installed_plugins if p["name"] == name]

    if len(installed) == 0:
        sc.console.print(
            f":exclamation: [bold red] ATTENTION: {site} does not have the {display_name} plugin installed."
        )
        notices.append(
            {
                "type": "warning",
                "icon": "&#x26A0;",  # warning sign
                "csv": f"{site},not-installed,{name}",
                "short": f"install the {name} plugin",
                "message": f'<p>The <a href="{escape_url(url)}">{html.escape(display_name)}</a> WordPress plugin needs to be installed:</p><p>{html.escape(reason)}</p>',
                "text": f"The {display_name} WordPress plugin\n<{url}>\nneeds to be installed: {reason}",
            }
        )
        return notices

    if len(installed) > 1:
        sc.console.print(
            f":exclamation: [bold red] ATTENTION: {site} has more than one {display_name} plugin installed."
        )
        notices.append(
            {
                "type": "info",
                "icon": "&#x1F50E;",  # magnifying glass
                "csv": f"{site},multiple-installed,{name}",
                "short": f"plugin {name} installed multiple times",
                "message": f'<p>The <a href="{escape_url(url)}">{html.escape(display_name)}</a> WordPress plugin is installed multiple times.</p>',
                "text": f"The {display_name} WordPress plugin\n<{url}>\nis installed multiple times.",
            }
        )

    plugin = installed[0]
    if not "status" in plugin or plugin["status"] not in (
        "active",
        "active-network",
        "must-use",
    ):
        sc.console.print(
            f":exclamation: [bold red] ATTENTION: {site} has the {display_name} plugin installed but it is not active."
        )
        notices.append(
            {
                "type": "warning",
                "icon": "&#x26A0;",  # warning sign
                "csv": f"{site},turned-off,{name}",
                "short": f"activate plugin {name}",
                "message": f'<p>The <a href="{escape_url(url)}">{html.escape(display_name)}</a> WordPress plugin needs to be activated:</p><p>{html.escape(reason)}</p>',
                "text": f"The {display_name} WordPress plugin\n<{url}>\nneeds to be activated: {reason}",
            }
        )

    return notices


def check_drupal_module(
    site: str,
    installed_mods: dict,
    name: str,
    display_name: str,
    url: str,
    reason: str,
    level: str = "warning",
) -> list:
    notices = []
    if not isinstance(installed_mods, dict):
        return notices  # this error should already have been handled by our caller, so skip additional work

    icon = "&#x26A0;"  # warning sign
    if level == "info":
        icon = "&#x1F50E;"  # magnifying glass

    if not name in installed_mods:
        sc.console.print(
            f":exclamation: [bold red] ATTENTION: {site} does not have the {display_name} module installed."
        )
        notices.append(
            {
                "type": level,
                "icon": icon,
                "csv": f"{site},not-installed,{name}",
                "short": f"install module {name}",
                "message": f'<p>The <a href="{escape_url(url)}">{html.escape(display_name)}</a> Drupal module needs to be installed:</p><p>{html.escape(reason)}</p>',
                "text": f"The {display_name} Drupal module\n<{url}>\nneeds to be installed: {reason}",
            }
        )
        return notices

    mod = installed_mods[name]
    if not "status" in mod or mod["status"] != "Enabled":
        sc.console.print(
            f":exclamation: [bold red] ATTENTION: {site} has the {display_name} module installed but it is not enabled."
        )
        notices.append(
            {
                "type": level,
                "icon": icon,
                "csv": f"{site},turned-off,{name}",
                "short": f"enable module {name}",
                "message": f'<p>The <a href="{escape_url(url)}">{html.escape(display_name)}</a> Drupal module needs to be enabled:</p><p>{html.escape(reason)}</p>',
                "text": f"The {display_name} Drupal module\n<{url}>\nneeds to be enabled: {reason}",
            }
        )

    return notices


def find_modules(module_type: str) -> list[str]:
    modules = []
    # find all non-empty regular files in/under the directory f"{type}" that are named "__init__.py":
    for dirpath, dirs, files in os.walk(module_type, followlinks=True):
        for file in files:
            if file == "__init__.py":
                target = os.path.join(dirpath, file)
                st = os.stat(target)
                if stat.S_ISREG(st.st_mode) and st.st_size != 0:
                    parts = target.split("/")[:-1]
                    target_name = ".".join(parts)
                    modules.append(target_name)
    modules.sort()  # ensure a consistent order when importing to simplify troubleshooting
    return modules


def smtp_login() -> SMTP_SSL:
    smtp_cfg = sc.config.get("SMTP", {})
    host = smtp_cfg.get("host", "smtp.mail.umich.edu")
    port = smtp_cfg.get("port", 465)
    username = sc.smtp_username()
    password = smtp_cfg.get("password")
    if not username or not password:
        sys.exit(
            "SMTP is enabled but the username or password is not configured "
            "(set [SMTP].username / [SMTP].password, or pass --smtp-username)."
        )
    smtp_connection = SMTP_SSL(host, port=port)
    smtp_connection.login(username, password)
    return smtp_connection


def overage_blocks(overage, overage_block_size) -> int:
    """Number of overage blocks billed for `overage` visits (rounded to the nearest block)."""
    return round((overage + overage_block_size / 2.0) / overage_block_size)


def contract_year_end(report_date: datetime.date) -> bool:
    """True if `report_date` is in the U-M contract-year-end window (June 16-29)."""
    return report_date.month == 6 and 16 <= report_date.day < 30


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
            if last_day >= 25:
                estimate = round(extrapolate)
            elif last_day >= 15:
                estimate = round((2 * extrapolate + previous_month) / 3)
            else:
                estimate = round((extrapolate + previous_month) / 2)
        else:
            estimate = round(extrapolate)
    return estimate


def build_traffic_table_rows(
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
    for month in visits_by_month.keys():
        ymd = datetime.date.fromisoformat(month + "-15")
        ymd1 = ymd.replace(day=1)
        if ymd < first_plan_day:
            ymd = first_plan_day
        if ymd > last_plan_day:
            ymd = last_plan_day
        if ymd1 < start_date:
            ymd1 = start_date
        if ymd1 > end_date:
            ymd1 = end_date.replace(day=1)
        if ymd1 < site_plan_start:
            continue
        d = ymd if ymd >= first_plan_day else first_plan_day
        plan = plan_on_day[d]
        if ymd1 == site_plan_start and plan != "Basic":
            op_remaining = 4
        if old_plan in ("Sandbox", "Basic") and plan not in ("Sandbox", "Basic"):
            op_remaining = 4
        old_plan = plan
        traffic_table_rows[month] = {}
        traffic_table_rows[month]["month"] = datetime.datetime.strptime(
            month, "%Y-%m"
        ).strftime("%B %Y")
        traffic_table_rows[month]["visitors"] = f"{visits_by_month[month]:,.0f}"
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
        overage = max(visits_by_month[month] - traffic_limit, 0)
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
                overage_protection_status += f"used 1 month, "
                overage_cost_text = (
                    '$0 (<span style="font-size:smaller;">waived '
                    + overage_cost_text
                    + ")</span>"
                )
            overage_protection_status += (
                f"1 month remaining"
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


def plan_costs(
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
):
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
        for month in visits_by_month.keys():
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
        if len(cost_by_month) < 12:
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
        if overage < 0:
            overage = 0
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


def build_plan_over_time(plan_on_day: dict, plot_right_date) -> list:
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


class ResumeSiteNotFoundError(Exception):
    """--resume-from named a site not present in the org site list."""


class DatabaseUnavailableError(RuntimeError):
    """A database operation failed, was retried once, and failed again.

    Raised by db_retry().  Caught once, around the site loop in main(), which flushes the
    end-of-run artifacts and exits nonzero with a command to re-run what is left (SPEC 3.5).
    """


# Reconnects HEALED by db_retry() -- the retry ran and succeeded -- attributed to the site that
# caused them.  Counted only after the second attempt returns: counting the attempt instead would
# let an aborted run report a reconnect it never actually made.
db_reconnects_by_site = {}

# Connection losses db_retry() could NOT heal, attributed the same way: the retry failed, or the
# rollback before it did.  The counterpart of the dict above, and the reason it can be trusted --
# every lost connection lands in exactly one of the two, so "0 healed" never means "nothing
# happened".  Both are reported on the console and in {ymd}-run.json (SPEC 3.6).
db_reconnect_failures_by_site = {}


def record_db_reconnect(counter: dict, site: str) -> None:
    """Attribute one reconnect (healed or failed) to `site`, or to "(no site)" outside the loop."""
    key = site if site is not None else "(no site)"
    counter[key] = counter.get(key, 0) + 1


def db_retryable(error: DBAPIError) -> bool:
    """Is this DBAPI error one db_retry() may roll back and re-run?

    NOT a hardcoded class list.  SQLAlchemy's MySQLdb dialect classifies a lost connection by
    error code, not by exception class: mysqlclient raises InterfaceError for errno 0 and
    ProgrammingError for CR_COMMANDS_OUT_OF_SYNC (2014, a connection reaped mid-result-set), and
    both are SIBLINGS of OperationalError under DBAPIError, not subclasses.  What every disconnect
    DOES share is connection_invalidated -- SQLAlchemy sets it from the dialect's is_disconnect().
    So retry on that, plus OperationalError (a deadlock, a lock-wait timeout or too-many-connections
    does not invalidate the connection but is still worth one retry -- SPEC 2.2).

    Everything else -- an IntegrityError, a genuine ProgrammingError bug -- is a real bug: it is a
    DBAPIError but neither an OperationalError nor an invalidated connection, so it propagates
    untouched and stays loud.
    """
    return isinstance(error, OperationalError) or error.connection_invalidated


def db_retry(session, unit, *, what: str, site: str = None):
    """Run `unit()`; on a database failure, roll back and re-run it exactly once.

    `unit` MUST be idempotent.  A rollback discards every pending ORM change in the session, so
    the retry re-runs the unit from scratch -- which is why retries happen at unit-of-work
    granularity and NEVER around a single statement that runs while writes are pending
    (SPEC 3.3.1).

    A rollback ALSO expires every loaded ORM object, regardless of expire_on_commit.  So a
    retryable unit must never be placed where live ORM rows will be read afterwards: the read
    would emit a fresh SELECT outside any unit, and therefore outside any retry.  This is why
    load_traffic_rows() returns plain TrafficRow data (SPEC 3.3.2).

    What is retried is decided by db_retryable(), not by an exception class: an OperationalError
    (a lost connection, but also a deadlock, a lock-wait timeout, or too-many-connections -- we
    deliberately do not sniff codes to tell those apart, SPEC 2.2), or ANY DBAPIError whose
    connection was invalidated.  A reaped connection can arrive as an InterfaceError or even a
    ProgrammingError(2014); those are not OperationalError subclasses, and retrying them is the
    whole point of this function.  A DBAPIError that is neither -- an IntegrityError, a real
    ProgrammingError bug -- is a bug and must stay loud, so it is re-raised untouched.
    """
    try:
        return unit()
    except DBAPIError as first_error:
        if not db_retryable(first_error):
            raise
        try:
            session.rollback()
        except DBAPIError as rollback_error:
            if not db_retryable(rollback_error):
                raise  # a real bug surfacing on the rollback: still not ours to rename
            # The rollback hit the wire and died too (the connection was not invalidated, so
            # SQLAlchemy really emitted a ROLLBACK).  Name it rather than let a raw
            # DBAPIError escape past main()'s handler -- SPEC 3.3.3.  It is also the run's most
            # definite connection loss, so it is COUNTED (as a failure): reporting zero here would
            # tell the operator nothing went wrong on the very run that died of it.
            record_db_reconnect(db_reconnect_failures_by_site, site)
            raise DatabaseUnavailableError(
                f"{what}: rollback failed after {first_error}"
            ) from rollback_error
        sc.console.print(
            f":warning: [bold yellow]Lost the database connection during {escape(what)}; "
            "reconnecting and retrying."
        )
        time.sleep(1)
        try:
            result = unit()
        except DBAPIError as retry_error:
            if not db_retryable(retry_error):
                # Not a connection issue itself, but first_error's connection loss never got
                # healed -- record it as a failure so it lands in a dict, not neither (the
                # comment above promises every lost connection lands in exactly one).
                record_db_reconnect(db_reconnect_failures_by_site, site)
                raise  # a real bug surfacing on the retry: still not ours to rename
            record_db_reconnect(db_reconnect_failures_by_site, site)
            raise DatabaseUnavailableError(f"{what}: {retry_error}") from retry_error
        # Counted HERE, not before the retry: a reconnect is a connection that came BACK.  An
        # abort that reported "1 reconnect" alongside "reason: database" was claiming a heal that
        # never happened -- and the operator reads this number to judge whether the connection
        # fix is working.
        record_db_reconnect(db_reconnects_by_site, site)
        return result


def update_traffic_rows(session, site: dict, metrics: dict, start_date, end_date) -> None:
    """Merge a site's daily metrics into pantheon_traffic and commit.

    Idempotent (session.merge() is upsert-by-primary-key), so db_retry() may re-run it.
    """
    # Preload the session with the data we're going to be updating.  This makes the merge()
    # calls below much faster.
    _ = (
        session.query(PantheonTraffic)
        .filter(
            PantheonTraffic.site_id == site["id"],
            PantheonTraffic.traffic_date.between(start_date, end_date),
        )
        .all()
    )
    for e in metrics["timeseries"]:
        entry = metrics["timeseries"][e]
        traffic_date = datetime.datetime.strptime(
            entry["datetime"], "%Y-%m-%dT%H:%M:%S"
        ).date()
        if traffic_date == end_date:
            continue  # skip today's partial data
        session.merge(
            PantheonTraffic(
                site_id=site["id"],
                traffic_date=traffic_date,
                site_plan=site["plan_name"],
                visits=entry["visits"],
                pages_served=entry["pages_served"],
                cache_hits=entry["cache_hits"],
            )
        )
    session.commit()


def insert_traffic_rows(session, rows: list) -> None:
    """Insert-or-ignore historical traffic rows and commit.

    Idempotent (ON CONFLICT DO NOTHING / INSERT IGNORE), so db_retry() may re-run it.
    """
    if len(rows) == 0:
        return
    if sc.config["Database"]["type"] == "sqlite":
        session.execute(
            sqlite_insert(PantheonTraffic).on_conflict_do_nothing(
                index_elements=["site_id", "traffic_date"]
            ),
            rows,
        )
    else:  # mysql:
        session.execute(insert(PantheonTraffic).prefix_with("IGNORE"), rows)
    session.commit()


def load_traffic_rows(session, site: dict, start_date, end_date) -> list:
    """Read a site's traffic rows for the report, then RELEASE the connection.

    The commit here looks redundant for a read-only query.  It is not, and it MUST NOT be
    removed: without it the session holds its connection, inside an open transaction, for the
    entire per-site gather (terminus, wp/drush, DNS, cache checks, matplotlib -- minutes).  A
    NAT/firewall on the path to RDS reaps that idle flow and the next query dies with MySQL error
    2013.  Committing returns the connection to the pool, where pool_pre_ping can validate and
    silently replace it on the next checkout.

    Returns plain TrafficRow data rather than ORM rows, so that a later db_retry() rollback --
    which expires every live ORM object -- cannot turn a downstream attribute read into an
    unretried SELECT.  See development/2026-07-13-db-connection-resilience/SPEC.md 3.1, 3.3.2.

    The TrafficRow list is built BEFORE the commit, on purpose: a default session (unlike
    main()'s, which sets expire_on_commit=False) expires every loaded ORM object on commit, and
    reading r.site_id etc. from an expired object triggers a lazy-refresh SELECT that opens a new
    transaction -- silently reintroducing the very connection-holding bug this function exists to
    fix. Materializing first makes "the connection is released on return" true unconditionally,
    independent of expire_on_commit.
    """
    rows = [
        TrafficRow(
            site_id=r.site_id,
            traffic_date=r.traffic_date,
            site_plan=r.site_plan,
            visits=r.visits,
            pages_served=r.pages_served,
            cache_hits=r.cache_hits,
        )
        for r in session.query(PantheonTraffic)
        .filter(
            PantheonTraffic.site_id == site["id"],
            PantheonTraffic.traffic_date.between(start_date, end_date),
        )
        .all()
    ]
    session.commit()  # releases the connection -- see the docstring; MUST NOT be removed
    return rows


def load_overage_protection_window(session, site: dict, start_date, end_date) -> dict:
    """Snapshot a site's overage-protection rows for the report window in ONE query.

    Returns {month (a date, day=1) -> OverageProtectionRow}, for plan_costs()' op_lookup to read
    as a plain dict.  A missing month is simply absent from the dict, so op_lookup's `.get()`
    returns None exactly where the old per-month Session.get() did.

    One query, not ~91.  plan_costs() asks for the overage state once per candidate plan PER
    MONTH (~7 non-Basic plans x ~13 months), and a Session.get() that misses is never negatively
    cached, so it re-SELECTs every time -- and a Basic-plan site, which has no rows at all, missed
    on every single call.  Each of those was its own db_retry() unit against a remote RDS over the
    WAN: pool checkout + pre-ping probe + SELECT + COMMIT.  A snapshot is equivalent because
    nothing writes to pantheon_overage_protection between build_traffic_table_rows()' commit and
    plan_costs()' reads.

    The commit is load_traffic_rows()' commit, for the same reason and with the same rule: it MUST
    NOT be removed.  Even a read autobegins a transaction, and without the commit the session
    would hold that connection, idle, through matplotlib, the Jinja render, the php inliner, the
    SMTP send and the NEXT site's terminus calls -- exactly the reaped-idle-flow bug this change
    exists to fix.  The rows are materialized as plain data BEFORE the commit, so that holds
    regardless of expire_on_commit (see load_traffic_rows()).
    """
    rows = {
        r.month: OverageProtectionRow(
            site_id=r.site_id,
            month=r.month,
            months_remaining=r.months_remaining,
            used_this_month=r.used_this_month,
        )
        for r in session.query(PantheonOverageProtection)
        .filter(
            PantheonOverageProtection.site_id == site["id"],
            PantheonOverageProtection.month.between(start_date.replace(day=1), end_date),
        )
        .all()
    }
    session.commit()  # releases the connection -- see the docstring; MUST NOT be removed
    return rows


def sites_from_resume_point(sorted_site_names: list, resume_from: str) -> list:
    """
    Return the suffix of sorted_site_names starting at resume_from (inclusive).

    sorted_site_names is the already-sorted list of org site names; resume_from is the
    --resume-from value.  Raises ResumeSiteNotFoundError if resume_from is absent, so that a
    typo becomes a fatal error rather than degrading into "silently skip every site".
    """
    try:
        i = sorted_site_names.index(resume_from)
    except ValueError:
        raise ResumeSiteNotFoundError(resume_from)
    return sorted_site_names[i:]


def db_engine_args(db_config: dict) -> (str, dict):
    """Build the (connection string, create_engine kwargs) for the traffic database.

    Behavior-preserving extraction of main()'s inline construction, so the pool settings below
    are unit-testable.  `type` and `name` are read unconditionally: a [Database] section without
    them is a KeyError, not a default (see CLAUDE.md).
    """
    if db_config["type"] == "sqlite":
        return f"sqlite:///{db_config['name']}", {}
    if db_config["type"] == "mysql":
        conn_str = (
            f"mysql+mysqldb://{db_config['user']}:{db_config['password']}@"
            f"{db_config['host']}:{db_config['port']}/{db_config['name']}"
        )
        # The database is remote (RDS) and the network path crosses NAT/firewall middleboxes
        # that reap idle flows.  pool_pre_ping is the LOAD-BEARING setting: it validates the
        # connection at pool checkout and transparently replaces a reaped one -- it is the only
        # thing here that actually defends against the reaping this whole change exists to fix.
        # pool_recycle does NOT: it bounds a connection's total AGE since creation (SQLAlchemy
        # compares time.time() - starttime at checkout), not its idle time, so a NAT gateway with
        # a 350s idle timeout can reap a connection nowhere near 1800s old.  It is a cheap
        # backstop against long-lived-connection problems, nothing more.  Do not weaken or drop
        # pool_pre_ping on the strength of it.  Deliberately hardcoded rather than configurable:
        # development/2026-07-13-db-connection-resilience/SPEC.md section 2.2.
        return conn_str, {
            "pool_size": 10,
            "max_overflow": 20,
            "pool_pre_ping": True,
            "pool_recycle": 1800,
        }
    sys.exit(f"Unsupported database type: {db_config['type']}")


def merge_prior_results(path: str, new_results: dict, *, what: str = "results") -> dict:
    """
    Return the JSON dict already at path merged with new_results, which wins on key collision
    (a site processed by the resumed run supersedes any earlier entry for it).

    A missing file yields new_results alone.  A malformed existing file warns loudly and yields
    new_results alone, rather than crashing at the very end of an otherwise-complete run.
    "Malformed" covers valid JSON that is not an object (a hand-edited `[]` or `null`) as well as
    unparseable or unreadable content: both would otherwise blow up on merged.update() below.

    `what` names, in the warning, the kind of content being merged/read -- this helper reads
    both {ymd}-results.json ("results") and {ymd}-run.json ("run metadata"; see finish_run()),
    and the warning must name whichever file actually failed to read.
    """
    merged = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                merged = json.load(f)
            if not isinstance(merged, dict):
                raise ValueError(f"expected a JSON object, found {type(merged).__name__}")
        # json.JSONDecodeError is a ValueError, so this catches an unparseable file too.
        except (ValueError, OSError) as e:
            sc.console.print(
                f":warning: [bold yellow]could not read existing {path} "
                f"({escape(str(e))}); writing only this run's {what}."
            )
            merged = {}
    merged.update(new_results)
    return merged


# Expose helpers for check/ packages, which cannot import this dash-named script.
# Same convention as sc.plugin_context['plugin.cloudflare']['get_client']: shared state /
# callables travel via the sc module.  Tests monkeypatch these sc attributes when loading
# check modules standalone.
sc.escape_url = escape_url
sc.check_wordpress_plugin = check_wordpress_plugin
sc.check_drupal_module = check_drupal_module
sc.umich_enabled = umich_enabled
sc.cloudflare_enabled = cloudflare_enabled
sc.terminus = terminus      # check packages: Pantheon calls (e.g. domain:dns) go through this
sc.fqdn_re = fqdn_re        # check packages: validate remote domain ids with the SAME regex
sc.db_engine_args = db_engine_args  # plugin/umich/portal.py: ONE URL builder, ONE set of pool
                                    # settings for every database this program connects to


def finish_run(
    db_session,
    db_engine,
    site_count: int,
    emails_sent: int,
    all_warnings: list,
    site_results: dict,
    site_savings: list,
    *,
    aborted_at: str = None,
    reason: str = None,
) -> None:
    """Close out a run: release the DB, print the totals, write the summary artifacts.

    Called from two places -- normal completion, and abort_run() (SPEC 3.5).  One epilogue with
    two callers is what makes an aborted run's artifacts identical in shape to a completed run's.

    `aborted_at` / `reason` are None on a normal run.  When set, the totals say so instead of
    claiming success, and both are recorded in {ymd}-run.json so the outcome outlives the terminal
    (SPEC 3.6).

    The run metadata gets its OWN artifact rather than a `_run` key inside {ymd}-results.json:
    results.json is consumed (monthly-report.txt) with `jq to_entries`, which enumerates every key
    as a site -- a metadata key there silently becomes a bogus site row in the operator's monthly
    stats.  {ymd}-results.json is site-keyed and nothing else.
    """
    # Two separate try blocks, deliberately: a failing close() must not skip dispose().  The
    # catches are narrow -- (SQLAlchemyError, OSError), not Exception -- so a TypeError from a
    # future edit still crashes loudly.  Neither failure may cost the operator the artifacts:
    # finish_run() is called from the abort path, on a session whose database is already sick
    # (SPEC 3.3.3).
    # escape() on every interpolated exception, here and everywhere else this file prints one:
    # rich parses `[parameters: (...)]` -- a lowercase-initial bracket, exactly what SQLAlchemy
    # appends to a DBAPIError -- as a style tag and DELETES it, and an unmatched `[/x]` raises
    # MarkupError from inside the very handler that exists so nothing is lost.
    try:
        db_session.close()
    except (SQLAlchemyError, OSError) as e:
        sc.console.print(
            f":warning: [yellow]Could not close the database session: {escape(str(e))}"
        )
    try:
        db_engine.dispose()
    except (SQLAlchemyError, OSError) as e:
        sc.console.print(
            f":warning: [yellow]Could not dispose the database engine: {escape(str(e))}"
        )

    reconnects = sum(db_reconnects_by_site.values())
    reconnect_failures = sum(db_reconnect_failures_by_site.values())

    # --update and --import-older-metrics `continue` before a report is ever built, so they have no
    # notices and no results to write.  Writing anyway would open {ymd}-notices.csv in "w" mode with
    # an empty list and overwrite {ymd}-results.json with an empty object -- DESTROYING the
    # artifacts of a report run made earlier the same day.  Print the totals, write nothing.
    write_artifacts = not (sc.options.update or sc.options.import_older_metrics)

    if sc.options.all:
        # On a resumed run these two on-disk summaries accumulate across the original and the
        # resumed run instead of being truncated to just the resumed subset.  (The console-only
        # totals printed here and below still cover only this run's sites.)
        resuming = sc.options.resume_from is not None
        # An ABORTED run accumulates too, for the same reason it flushes at all: the artifacts on
        # disk may belong to an earlier, COMPLETED run of the same day (the monthly --all --for-real
        # run in the morning, a Ctrl-C'd dry run in the afternoon).  Truncating them would destroy
        # a good run's record to make room for a partial one's.  Only a run that reaches the end
        # legitimately truncates; the worst case here is duplicate rows on a re-run, which
        # docs/resuming-interrupted-runs.md already documents as tolerable.
        accumulating = resuming or reason is not None
        if reason is None:
            sc.console.print(
                f"\n[bold green]Email sent for {emails_sent} of {site_count} sites"
                + (f" (resumed from {sc.options.resume_from}).\n" if resuming else ".\n")
            )
        elif aborted_at is None:
            # An interrupt landing before the first site's body ran passes aborted_at=None --
            # there is no "at X" to report (SPEC 3.5.4).
            sc.console.print(
                f"\n[bold yellow]Email sent for {emails_sent} sites before aborting.\n"
            )
        else:
            sc.console.print(
                f"\n[bold yellow]Email sent for {emails_sent} sites before aborting at "
                f"{aborted_at}.\n"
            )
        if write_artifacts:
            ymd = datetime.datetime.today().strftime("%Y%m%d")
            with open(
                f"{ymd}-notices.csv", "a" if accumulating else "w", encoding="utf-8"
            ) as f:
                for n in all_warnings:
                    f.write(n + "\n")

            results_path = f"{ymd}-results.json"
            # merge_prior_results() rather than a hand-rolled {**prior, **site_results}: it owns
            # the "new wins" rule AND the malformed-prior-file handling, and that logic must live
            # in one place.
            payload = (
                merge_prior_results(results_path, site_results)
                if accumulating
                else site_results
            )
            # A results.json written by an older version carries a "_run" metadata key, which is
            # exactly the bogus-site-row bug this split exists to remove.  Drop it on the way
            # through; nothing writes it any more -- but keep it: if this run is the FIRST since
            # the upgrade (no {ymd}-run.json yet), this legacy key is the ONLY copy of the prior
            # run's reconnect evidence, and dropping it here would silently lose the exact thing
            # "previous" exists to preserve.  Migrated into run_meta["previous"] below.
            legacy_run = payload.pop("_run", None)
            with open(results_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=4)

            run_path = f"{ymd}-run.json"
            run_json_existed = os.path.exists(run_path)
            # Read the prior metadata first so this run's block can NEST the earlier run's under
            # "previous" -- an aborted run's block carries the reconnect evidence that prompted
            # the resume in the first place.  merge_prior_results() is just the reader here (with
            # its malformed-file handling); the file is then overwritten, not merged, because the
            # nesting IS the accumulation.
            prior_run = (
                merge_prior_results(run_path, {}, what="run metadata") if accumulating else {}
            )
            # "this_run" in the names, not "processed": the artifacts on disk describe the original
            # run plus this one, while these numbers describe only this one.  (An --only-warn run
            # emails nobody, so this counts sites processed, not sites emailed.)
            run_meta = {
                "aborted_at": aborted_at,
                "reason": reason,
                "sites_completed_this_run": len(site_results),
                # Healed vs. failed, never one ambiguous "reconnects" number: a run that aborted
                # on the database healed NOTHING, and saying otherwise misleads the operator about
                # the one thing this counter exists to answer.
                "db_reconnects_healed_this_run": reconnects,
                "db_reconnect_failures_this_run": reconnect_failures,
                "reconnects_by_site": dict(db_reconnects_by_site),
                "reconnect_failures_by_site": dict(db_reconnect_failures_by_site),
            }
            if prior_run:
                run_meta["previous"] = prior_run
            elif legacy_run is not None and not run_json_existed:
                # First run since the upgrade: {ymd}-run.json didn't exist yet, so the only
                # record of the prior run's reconnect evidence was the "_run" key we just popped
                # out of results.json above.  Carry it forward instead of discarding it.
                run_meta["previous"] = legacy_run
            with open(run_path, "w", encoding="utf-8") as f:
                json.dump(run_meta, f, indent=4)
    else:
        for n in all_warnings:
            sc.console.print(n)
        pprint(site_results)

    sc.console.print(f"\n[bold green]Site savings:\n")
    pprint(site_savings)
    sc.console.print(f"Sites with savings: {len(site_savings)}")
    sc.console.print(
        f"Total savings: ${sum([s['savings'] for s in site_savings]):,.2f}"
    )
    # Both numbers, always: "Database reconnects: 1" used to mean "one retry was attempted",
    # printed identically whether the connection came back or the run died of it.
    sc.console.print(
        f"Database reconnects: {reconnects} healed, {reconnect_failures} failed"
    )

    sc.debug("Done!")


def resume_point(site_names: list, site_name: str, emailed: bool) -> str:
    """Where a resumed run must start.

    Normally the aborting site itself: --resume-from is inclusive, so it is redone from the top.
    But if the interrupt landed AFTER that site's report was emailed, restarting there would send
    its owner a SECOND copy of the same monthly report, so the resume point is the next site.
    Returns None when the emailed site was the last one (nothing remains).  See SPEC 3.5.3.
    """
    if not emailed:
        return site_name
    i = site_names.index(site_name)
    return site_names[i + 1] if i + 1 < len(site_names) else None


def option_strings_taking_a_value() -> set:
    """Every option string that consumes a following argument, derived from the parser itself.

    Derived rather than hardcoded: a hardcoded list rots the first time an option is added, and
    rerun_command() would then mistake that option's VALUE for a site name and delete it.  Same
    denylist-by-omission failure that SPEC 3.5.1 exists to prevent.
    """
    return {
        opt
        for action in build_arg_parser()._actions
        if action.option_strings and action.nargs != 0
        for opt in action.option_strings
    }


def resume_command(argv: list, site_name: str) -> str:
    """Rebuild an --all invocation with --resume-from <site_name>.

    Built from argv rather than from sc.options on purpose.  Re-enumerating flags would be a
    denylist by omission -- the first flag added next year would silently vanish from the hint, and
    an operator pasting the command would get a run that does something DIFFERENT from the one that
    died (e.g. a full report-and-send instead of an --import-older-metrics backfill).
    allow_abbrev=False guarantees only these two spellings exist.  See SPEC 3.5.1.
    """
    args = []
    skip_next = False
    for arg in argv:
        if skip_next:
            skip_next = False
            continue
        if arg == "--resume-from":
            skip_next = True  # drop its value too
            continue
        if arg.startswith("--resume-from="):
            continue
        args.append(arg)
    return shlex.join(args + ["--resume-from", site_name])


def rerun_command(argv: list, original_sites: list, remaining_sites: list) -> str:
    """Rebuild an explicit-SITE invocation with only the sites that were not processed.

    NOT --resume-from: that flag requires --all (main() exits otherwise), so printing it here would
    hand the operator a command that fails the moment they paste it.

    Only POSITIONAL site names are dropped.  A site name sitting in an option's value slot
    (`-c its-wws-test1`) must survive, or `-c` swallows the next token and the command is mangled.
    See SPEC 3.5.1.
    """
    value_opts = option_strings_taking_a_value()
    args = []
    previous = None
    for arg in argv:
        is_option_value = previous in value_opts
        if not is_option_value and arg in original_sites:
            previous = arg
            continue  # a site positional: dropped here, re-appended below if still pending
        args.append(arg)
        previous = arg
    return shlex.join(args + list(remaining_sites))


def abort_reason(error: BaseException) -> str:
    """Classify an exception escaping the site loop into an abort reason.

    "database" -> exit 1;  "interrupted" -> exit 130;  "fatal" -> re-raise the original error.

    A DBAPIError is a database abort only when it is one db_retry() would have retried
    (db_retryable() is the single source of truth for that -- SPEC 2.2); an IntegrityError or
    other non-retryable DBAPIError is a data bug and belongs on the fatal path, with its
    traceback.
    """
    if isinstance(error, DatabaseUnavailableError) or (
        isinstance(error, DBAPIError) and db_retryable(error)
    ):
        # A database failure raised OUTSIDE a unit of work (a future code path, an expired-row
        # lazy load) must still land on the named abort path (SPEC 3.3.3).
        return "database"
    elif isinstance(error, KeyboardInterrupt):
        return "interrupted"
    else:
        return "fatal"


def abort_run(
    db_session,
    db_engine,
    site_name: str,
    reason: str,
    error: BaseException,
    *,
    emailed: bool,
    site_names: list,
    site_count: int,
    emails_sent: int,
    all_warnings: list,
    site_results: dict,
    site_savings: list,
) -> None:
    """Report an aborted run, flush its artifacts, print how to finish it, and exit.  Never returns.

    `reason` is "database" (exit 1), "interrupted" (exit 130, the conventional SIGINT code), or
    "fatal" -- anything else that escaped the site loop (a SystemExit("Bailing out."), an SMTP
    hiccup on site 250 of 300, a KeyError from changed terminus JSON).  A fatal RE-RAISES the
    original exception after the flush, so its traceback -- or a SystemExit's own code and message
    -- reaches the operator unchanged.  Nothing is swallowed.

    This is the ONE flush path, so every exit has the same invariants: the aborting site is popped
    from the results unless its report was already emailed, and a runnable continuation command is
    printed.  `emailed` says whether that report went out; every caller passes the real value,
    because a report that has gone out must never be re-sent by the resumed run.

    This function runs when things are ALREADY broken, so it must not be able to crash: every input
    it slices on is guarded (SPEC 3.5.4).
    """
    # A second Ctrl-C must not truncate the flush -- losing the artifacts is exactly the failure
    # this function exists to prevent.  The flush is sub-second (SPEC 3.5).
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    try:
        db_session.rollback()
    except (SQLAlchemyError, OSError) as e:  # the database is already sick; see finish_run()
        sc.console.print(
            f":warning: [yellow]Could not roll back the database session: {escape(str(e))}"
        )

    if not emailed:
        # site_results[site] is written DURING the gather, ~1400 lines before the failure point --
        # so the aborting site is already in there, while its notices (appended at the END of a
        # successful site) are not.  Drop it, so the artifacts contain exactly the sites that
        # completed end-to-end.  --resume-from is inclusive, so the resumed run redoes this site
        # and rewrites the entry.  See SPEC 3.5.2.
        site_results.pop(site_name, None)
        # site_savings is appended to just as early, so the same rule applies to it: leaving the
        # aborting site in would make the epilogue's "Sites with savings" / "Total savings" count
        # the very site it is telling the operator to redo -- and the resumed run would count it
        # again.  A list of dicts, not a dict, hence the filter rather than a pop.
        site_savings[:] = [s for s in site_savings if s.get("site") != site_name]

    # escape() every interpolated exception.  A SQLAlchemy DBAPIError's message ends with
    # `[SQL: ...]` and `[parameters: (...)]`; rich's markup parser reads the lowercase-initial
    # `[parameters: ...]` as a style tag and DELETES it from the output -- silently dropping the
    # bound values from the very message the operator has to debug.  An unmatched `[/...]` in an
    # error is worse: it raises MarkupError HERE, after SIGINT was ignored and BEFORE finish_run(),
    # losing every artifact this function exists to save.  The [bold] markup around the site name
    # is ours and stays live.
    if reason == "database":
        if site_name is None:
            # Reached before any site's body ran -- there is no "processing X" to name, and
            # interpolating site_name here would render the literal word "None" (SPEC 3.5.4).
            sc.console.print(
                f"\n:exclamation: [bold red]FATAL: a database operation failed and could not "
                f"be retried before any site was processed:\n{escape(str(error))}"
            )
        else:
            sc.console.print(
                f"\n:exclamation: [bold red]FATAL: a database operation failed and could not be "
                f"retried.  Aborting while processing [bold]{escape(site_name)}[/bold]:\n"
                f"{escape(str(error))}"
            )
    elif reason == "fatal":
        # The traceback (or the SystemExit message) follows when we re-raise below; this line is
        # what ties it to the site that was in flight and tells the operator the artifacts are safe.
        detail = escape(f"{type(error).__name__}: {error}")
        if site_name is None:
            sc.console.print(
                f"\n:exclamation: [bold red]FATAL: the run failed before any site was "
                f"processed:\n{detail}"
            )
        else:
            sc.console.print(
                f"\n:exclamation: [bold red]FATAL: aborting while processing "
                f"[bold]{escape(site_name)}[/bold]:\n{detail}"
            )
    elif site_name is None:
        sc.console.print("\n:hand: [bold yellow]Interrupted before any site was processed.")
    else:
        sc.console.print(
            f"\n:hand: [bold yellow]Interrupted while processing [bold]{escape(site_name)}[/bold]."
            + (
                "  Its report had already been sent, so resuming will start at the next site."
                if emailed
                else ""
            )
        )

    finish_run(
        db_session,
        db_engine,
        site_count,
        emails_sent,
        all_warnings,
        site_results,
        site_savings,
        aborted_at=site_name,
        reason=reason,
    )

    # Everything below is guarded: an interrupt can land before the first site's body runs
    # (site_name is None), or -- on a non---all run, which iterates every org site and `continue`s
    # the ones it was not asked for -- on a site the operator never requested.  Slicing on either
    # would raise INSIDE this handler, after SIGINT was ignored and the artifacts were written, and
    # the operator would get a traceback instead of a command.  See SPEC 3.5.4.
    resume_site = (
        resume_point(site_names, site_name, emailed)
        if site_name in site_names
        else None
    )

    if resume_site is None and emailed:
        sc.console.print("\n[bold]Every site was processed; nothing remains to resume.\n")
    elif sc.options.all:
        if site_name is None:
            # The interrupt landed before any site was processed -- there is no "sites before X"
            # to report, and {resume_site or site_name} would render as the literal word "None".
            # soft_wrap=True on EVERY print that emits a copy-pasteable command.  sc.console is a
            # bare Console(), so on a non-tty -- cron, nohup, a redirect, i.e. exactly how a
            # multi-hour --all run is launched -- rich falls back to width 80 and puts a REAL
            # newline in the output.  These commands are longer than that, and bash treats the
            # newline as a command separator: the operator pastes it and the first line re-parses
            # as a complete `--all --for-real` run with no --resume-from, re-mailing every owner
            # who already got their report.
            sc.console.print(
                "\n[bold]No sites were processed.  Continue this run with:\n\n"
                f"    {shlex.join(sys.argv)}\n",
                soft_wrap=True,
            )
        else:
            # resume_site is necessarily set here: an --all run only ever aborts on a site the
            # loop is iterating, so site_name is in site_names and resume_point() returned None
            # only if the emailed site was the last one -- which the "nothing remains" branch
            # above already consumed.  There is deliberately NO shlex.join(sys.argv) fallback: a
            # command without --resume-from would re-process and, on --for-real, re-mail every
            # owner who already has their report.
            sc.console.print(
                f"\n[bold]The sites before {resume_site} were processed and their "
                "results written.  Continue this run with:\n\n"
                f"    {resume_command(sys.argv, resume_site)}\n",
                soft_wrap=True,  # never wrap a command; see above
            )
    else:
        # --resume-from requires --all, so an explicit-SITE run gets a re-run command listing the
        # sites it never reached.  The site loop iterates every ORG site (site_names) and `continue`s
        # the ones not requested, so slicing the requested list at resume_site (an org site name) is
        # wrong -- it is frequently not even a member of the requested list.  Instead, compute what
        # the loop actually walked past in ORG order and drop that from the requested list: this is
        # correct whether or not the aborting site was requested, and whether or not it was emailed.
        if site_name in site_names:
            i = site_names.index(site_name) + (1 if emailed else 0)
            done = set(site_names[:i])  # every org site the loop already walked past
            remaining = [s for s in sorted(sc.options.sites) if s not in done]
        else:
            # site_name is not a known org site -- in practice this means None (the interrupt
            # landed before any site was processed).  Kept general, not assumed-None-only: this
            # handler must not crash on any input (SPEC 3.5.4), and the guard above this whole
            # if/elif/else already treats "not in site_names" as the general case, not a
            # None-only one.
            remaining = sorted(sc.options.sites)

        # The org list being exhausted (resume_site is None and emailed, above) is the --all
        # check for "nothing remains"; here the equivalent signal is an empty explicit-SITE
        # remaining list -- e.g. the requested SITE was the last one processed before the abort.
        if not remaining:
            sc.console.print("\n[bold]Every site was processed; nothing remains to resume.\n")
        else:
            sc.console.print(
                "\n[bold]Continue this run with:\n\n"
                f"    {rerun_command(sys.argv, sc.options.sites, remaining)}\n",
                soft_wrap=True,  # never wrap a command; see above
            )

    if reason == "fatal":
        # Re-raise, do not exit: a SystemExit keeps its own code and message, and anything else
        # keeps its traceback.  The flush above is all this path adds.
        raise error

    sys.exit(1 if reason == "database" else 130)


def build_smell_notices(site_name, wp_smell, drush_smell, composer_smell):
    """Return the list of smell notice dicts (possibly empty) for one site."""
    notices = []
    if wp_smell != "":
        notices.append(
            {
                "type": "info",
                "icon": "&#x1F50E;",  # magnifying glass
                "csv": f"{site_name},wp-smell,{json.dumps(wp_smell).replace(',', '\\,')}",
                "short": "PHP code problems",
                "message": f"""
<p>The <code>wp</code> (WP CLI) command is reporting PHP code problems with <strong>{site_name}</strong>.
Even if this is not breaking anything at the moment, it should be fixed to avoid possible future problems:</p>
<pre>{html.escape(wp_smell)}</pre>
""",
                "text": f"""
The "wp" (WP CLI) command is reporting PHP code problems with
{site_name}. Even if this is not breaking anything at
the moment, it should be fixed to avoid possible future problems:

----- START WP CLI REPORTED PROBLEMS -----
{wp_smell}
----- END OF WP CLI REPORTED PROBLEMS -----

    """,
            }
        )

    if drush_smell != "":
        notices.append(
            {
                "type": "info",
                "icon": "&#x1F50E;",  # magnifying glass
                "csv": f"{site_name},drush-smell,{json.dumps(drush_smell).replace(',', '\\,')}",
                "short": "PHP code problems",
                "message": f"""
<p>The <code>drush</code> command is reporting PHP code problems with <strong>{site_name}</strong>. Even
if this is not breaking anything at the moment, it should be fixed to avoid possible future problems:</p>
<pre>{html.escape(drush_smell)}</pre>
""",
                "text": f"""
The "drush" command is reporting PHP code problems with
{site_name}. Even if this is not breaking anything
at the moment, it should be fixed to avoid possible future problems:

----- START DRUSH REPORTED PROBLEMS -----
{drush_smell}
----- END OF DRUSH REPORTED PROBLEMS -----

""",
            }
        )

    if composer_smell != "":
        notices.append(
            {
                "type": "info",
                "icon": "&#x1F50E;",  # magnifying glass
                "csv": f"{site_name},composer-smell,{json.dumps(composer_smell).replace(',', '\\,')}",
                "short": "PHP code problems",
                "message": f"""
        <p>The <code>composer</code> command is reporting PHP code problems with <strong>{site_name}</strong>. Even
        if this is not breaking anything at the moment, it should be fixed to avoid possible future problems:</p>
        <pre>{html.escape(composer_smell)}</pre>
        """,
                "text": f"""
        The "composer" command is reporting PHP code problems with
        {site_name}. Even if this is not breaking anything
        at the moment, it should be fixed to avoid possible future problems:

        ----- START COMPOSER REPORTED PROBLEMS -----
        {composer_smell}
        ----- END OF COMPOSER REPORTED PROBLEMS -----

        """,
            }
        )
    return notices


def build_php_eol_notice(site_name, php_version):
    """Return the PHP-EOL notice dict for php_version, or None when no notice is needed."""
    if php_version in ("7.4", "8.1"):
        return {
            "type": "warning",
            "icon": "&#x26A0;",  # warning sign
            "csv": f"{site_name},php-eol-warning",
            "short": f"Upgrade PHP",
            "message": f"""
<p><b>{site_name} is using PHP {php_version}.</b>
You may want to <a href="https://docs.pantheon.io/guides/php/php-versions">manually upgrade your site to PHP 8.2 or later</a>
since <a href="https://docs.pantheon.io/release-notes/2026/03/php-removal-schedule">Pantheon has announced they will no
longer offer PHP {php_version} soon</a>, likely sometime in 2027.</p>
""",
            "text": f"""
{site_name} is using PHP {php_version}.

You may want to manually upgrade your site to PHP 8.2 or later
<https://docs.pantheon.io/guides/php/php-versions>
since Pantheon has announced they will no longer offer PHP {php_version}
soon</a>, likely sometime in 2027.
<https://docs.pantheon.io/release-notes/2026/03/php-removal-schedule>
""",
        }
    if php_version < "8.2":
        new_php = "7.4" if php_version.startswith("7") else "8.1"
        return {
            "type": "alert",
            "icon": "&#x1F6A8;",  # police car light
            "csv": f"{site_name},php-eol-alert",
            "short": f"Upgrade PHP",
            "message": f"""
<p><b>{site_name} is using PHP {php_version}.  On September 30, 2026,
<a href="https://docs.pantheon.io/release-notes/2026/03/php-removal-schedule">Pantheon will move your site
to PHP {new_php}</a>, which may break your site.</b></p>
<p>Please <a href="https://docs.pantheon.io/guides/php/php-versions">manually upgrade your site to PHP 8.2 or later</a>
so you can fix any problems without affecting your site's visitors.  Although you can update
your site to use PHP {new_php} instead of 8.2, please note that Pantheon has already announced that they will also remove
PHP {new_php} sometime after September 30, 2026.</p>
""",
            "text": f"""
{site_name} is using PHP {php_version}.  On
September 30, 2026, Pantheon will move your site to PHP {new_php},
which may break your site.
<https://docs.pantheon.io/release-notes/2026/03/php-removal-schedule>

Please manually upgrade your site to PHP 8.2 or later so you can fix
any problems without affecting your site's visitors.
<https://docs.pantheon.io/guides/php/php-versions>

Although you can update your site to use PHP {new_php} instead of 8.2,
please note that Pantheon has already announced that they will also
remove PHP {new_php} sometime after September 30, 2026.
""",
        }
    return None


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


def build_plan_recommendation_notice(site_name, current_plan, recommended_plan, savings,
                                     portal_site_id, umich):
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
        "csv": f"{site_name},its-recommends-plan,{current_plan},{recommended_plan},{savings:,.2f}",
        "short": "plan change recommended",
        "message": message,
        "text": text,
    }


def main() -> None:

    sc.debug(f"Loading configuration from {sc.options.config}")
    with open(sc.options.config, "rb") as f:
        sc.config = tomllib.load(f)

    # Drop the non-`enabled` settings of any disabled section BEFORE substitution resolution,
    # so a disabled feature's <{secret env ...}> values are never required to exist.
    sc.config = gate_disabled_sections(sc.config)

    sc.debug(f"[bold magenta]=== Loading plugins:")
    for plugin_name in find_modules("plugin"):
        sc.debug(f"Loading plugin: {plugin_name}")
        module = importlib.import_module(plugin_name)
        sc.plugin[plugin_name] = module

    sc.debug(f"Doing pre-setup configuration substitutions")
    sc.config = process_config(sc.config)

    sc.debug(f"[bold magenta]=== Loading checks:")
    for check_name in find_modules("check"):
        sc.debug(f"Loading check: {check_name}")
        module = importlib.import_module(check_name)
        sc.check[check_name] = module

    # Validate and process arguments.  The --resume-from guards come first: the create-tables and
    # sites-or-all checks below both exit before they would be reached, shadowing these more
    # precise messages.  --create-tables never runs the site loop, so a --resume-from on it would
    # be silently dropped; reject it instead.
    if sc.options.resume_from is not None:
        if sc.options.create_tables:
            sys.exit(
                "The --resume-from and --create-tables options are mutually exclusive."
            )
        if not sc.options.all:
            sys.exit("--resume-from can only be used together with --all.")

    if sc.options.create_tables:
        if sc.options.import_older_metrics:
            sys.exit(
                "The --import-older-metrics and --create-tables options are mutually exclusive."
            )
        sc.options.verbose = 3  # force verbose output
    elif (sc.options.all and len(sc.options.sites) != 0) or (
        not sc.options.all and len(sc.options.sites) == 0
    ):
        sys.exit("You must specify either at least one site or the --all option.")

    # --update-cloudflare-fqdns only does anything with the Cloudflare plugin enabled; refuse it
    # otherwise rather than silently doing nothing.  (Gate on config, not `"plugin.cloudflare" in
    # sc.plugin`: every plugin package is imported regardless of `enabled`.)
    if sc.options.update_cloudflare_fqdns and not sc.config.get("Cloudflare", {}).get("enabled"):
        sys.exit(
            "--update-cloudflare-fqdns requires the [Cloudflare] section to be enabled in the config."
        )

    if sc.options.verbose:
        sc.debug("Arguments:")
        pprint(sc.options)
        self_info, _errors, _fatal = terminus("self:info")
        pprint(self_info)

    # Create a directory named "build" if it doesn't exist:
    if not os.path.exists("build"):
        os.makedirs("build")

    sc.invoke_hooks("setup")

    sc.debug(f"Doing post-setup configuration substitutions")
    sc.config = process_config(sc.config, deferred_pass=True)
    if sc.options.verbose:
        sc.debug("Configuration after substitutions:")
        pprint(sc.config)

    overage_block_size = sc.config["Pantheon"]["overage_block_size"]
    overage_block_cost = sc.config["Pantheon"]["overage_block_cost"]

    sc.debug(
        "[bold magenta]=== Connecting to the [green]pantheon-sitehealth-emails[/green] traffic database:"
    )

    traffic_db_conn_str, traffic_db_conn_kwargs = db_engine_args(sc.config["Database"])

    db_engine = db.create_engine(
        traffic_db_conn_str,
        echo=True if sc.options.verbose >= 2 else False,
        **traffic_db_conn_kwargs,
    )
    # expire_on_commit=False is REQUIRED, not a tuning knob: load_traffic_rows() commits to
    # release the connection before the gather (SPEC 3.1), and the report reads those rows
    # afterwards.  With expiry on, that commit would silently re-SELECT every row.  Safe here
    # because both models use composite natural primary keys with no server defaults, so nothing
    # depends on a post-commit refresh.
    db_session_factory = db.orm.sessionmaker(bind=db_engine, expire_on_commit=False)
    db_session = db_session_factory()

    if sc.options.create_tables:
        Base.metadata.create_all(db_engine)
        sys.exit("Tables created.")

    with open("header-image.png", "rb") as img:
        wordmark_image = img.read()

    load_news_items()
    if sc.options.verbose:
        sc.debug("[bold magenta]=== News:")
        pprint(sc.news)

    for plan in sc.config["Pantheon"]["plan_info"]:
        upgrade_to = sc.config["Pantheon"]["plan_info"][plan]["upgrade_to"]
        downgrade_to = sc.config["Pantheon"]["plan_info"][plan]["downgrade_to"]
        sc.config["Pantheon"]["plan_info"][plan]["upgrade_to"] = (
            upgrade_to if upgrade_to != "-" else None
        )
        sc.config["Pantheon"]["plan_info"][plan]["downgrade_to"] = (
            downgrade_to if downgrade_to != "-" else None
        )
    plan_info = sc.config["Pantheon"][
        "plan_info"
    ]  # create an alias for convenience and readability
    plan_names = list(plan_info.keys())

    end_date = sc.options.date
    end_date_yyyy_mm = end_date.strftime("%Y-%m")
    start_date = end_date.replace(
        day=1, year=end_date.year - 1
    )  # fist day of the same month last year
    end_of_contract_year = contract_year_end(end_date)
    sc.debug(f"Generating report for {start_date} through {end_date}")

    # Generate a cap shape to use at the end of the traffic surge chart bars
    cap_size = 2 * np.pi
    x = np.linspace(0, cap_size, 31)
    y = (np.sin(x - np.pi / 2) + 1) / 2
    cap_points = np.array(list(zip(x, y)))
    cap_points_inv = np.concatenate(
        ([[0, 0]], cap_points - [0, 1], [[cap_size, 0]]), axis=0
    )
    cap_points = np.concatenate(([[0, 0]], cap_points, [[cap_size, 0]]), axis=0)

    try:
        sites = terminus_data("org:site:list", sc.config["Pantheon"]["org_id"])
    except TerminusError as e:
        sys.exit(f"Could not list organization sites: {e}")
    site_count = len(sites)
    current_site_number = 1
    emails_sent = 0
    site_savings = []
    all_warnings = []
    site_results = {}
    sc.debug(
        "Cloudflare is "
        + ("[bold green]enabled" if cloudflare_enabled() else "[bold red]DISABLED")
    )
    smtp_enabled = bool(sc.config.get("SMTP", {}).get("enabled"))
    sc.debug(
        "SMTP sending is "
        + ("[bold green]enabled" if smtp_enabled else "[bold red]DISABLED")
    )
    site_name_to_id = {site["name"]: site_id for (site_id, site) in sites.items()}
    sc.debug(site_name_to_id)

    # Sites are processed in sorted order, so --resume-from can drop the prefix of sites that
    # an interrupted run already handled.  Filtering here (rather than `continue`ing inside the
    # loop) means a skipped-over site does no work at all: no banner, no plan:info, no context.
    site_names = sorted(site_name_to_id.keys())
    if sc.options.resume_from is not None:
        try:
            site_names = sites_from_resume_point(site_names, sc.options.resume_from)
        except ResumeSiteNotFoundError:
            sys.exit(
                f"--resume-from: site '{sc.options.resume_from}' was not found among the "
                f"{len(site_names)} sites for org {sc.config['Pantheon']['org_id']}."
            )
        sc.console.print(
            f"[bold magenta]=== Resuming from [bold]{sc.options.resume_from}[/bold] "
            f"({len(site_names)} of {site_count} sites remaining)"
        )

    site_name = None
    site_emailed = False
    try:
        for site_name in site_names:
            site_emailed = False
            site_id = site_name_to_id[site_name]
            site = sites[site_id]
            wp_smell = ""
            drush_smell = ""
            composer_smell = ""
            portal_site_id = 0
            if umich_enabled():
                if site["name"] not in sc.config["UMich"]["portal"]["sites"]:
                    sc.console.print(
                        f":exclamation: [bold red] ATTENTION: {site['name']} is not in the WWS portal!"
                    )
                    continue
                portal_site_id = sc.config["UMich"]["portal"]["sites"][site["name"]]["id"]

            if not sc.options.all and site["name"] not in sc.options.sites:
                sc.debug(
                    f"[bold magenta]=== Skipping site {site['name']} (not in list of sites to process)",
                    level=2,
                )
                continue
            sc.console.print(
                "\n",
                Padding(
                    f"Pantheon site {current_site_number} of {site_count}: [bold]{site['name']}[/bold]",
                    1,
                    style="white on blue",
                ),
                "\n",
            )
            current_site_number += 1

            if site["plan_name"] == "Elite":
                # Pantheon uses the same display name (but a different SKU) for each Elite plan.
                site_plan_info, errors, fatal = terminus("plan:info", site["name"])
                if fatal or site_plan_info is None:
                    # A transient/undecodable Terminus failure for one site skips that site
                    # rather than aborting the whole run (consistent with the other per-site
                    # terminus calls below).
                    sc.console.print(
                        f":exclamation: [bold red] ERROR: could not fetch plan info for {site_name}: {escape(errors)}"
                    )
                    continue
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
                site["plan_name"] = sc.config["Pantheon"]["plan_sku_to_name"][plan_sku]
            site_current_plan = site["plan_name"]
            site_recommended_plan = site["plan_name"]
            site_current_plan_index = 0
            site_recommended_plan_index = 0

            if site["plan_name"] == "Sandbox":
                sc.console.print(f"{site['name']} is on the Sandbox plan, skipping it.")
                continue

            # This site will be processed: build its context as far up as possible (past the
            # portal / not-requested / Sandbox skips above).  notices/sections/attachments
            # accumulate into it through the pipeline below.
            site_context = sc.SiteContext(site)

            if site["frozen"] is not False:
                sc.console.print(
                    f":exclamation: [bold red] ATTENTION: {site['name']} is frozen!"
                )
                site_context.add_notice(
                    {
                        "type": "alert",
                        "icon": "&#x1F6A8;",  # police car light
                        "csv": f"{site['name']},frozen",
                        "short": "unfreeze site",
                        "message": f"""
<p>Website <strong>{site["name"]}</strong> is frozen!</p>
<p><a href="https://docs.pantheon.io/guides/platform-considerations/platform-site-info#inactive-site-freezing">
This should not happen</a> to a website on a paid Pantheon plan.</p>
<p><a href="https://its.umich.edu/computing/web-mobile/pantheon/support#support">Contact Pantheon</a> to get
<strong>{site["name"]}</strong> unfrozen and to find out what went wrong.</p>
""",
                        "text": f"""
Website {site["name"]} is frozen!
<https://docs.pantheon.io/guides/platform-considerations/platform-site-info#inactive-site-freezing>

This should not happen</a> to a website on a paid Pantheon plan.
Contact Pantheon to get {site["name"]} unfrozen
and to find out what went wrong:
<https://its.umich.edu/computing/web-mobile/pantheon/support#support>
""",
                    }
                )

            if site["plan_name"] not in plan_names:
                sc.console.print(
                    f":exclamation: [bold red] ATTENTION: {site['name']} "
                    f"is on an unknown plan: {site['plan_name']}"
                )
                sys.exit("Bailing out.")

            # From https://docs.pantheon.io/guides/account-mgmt/traffic/overages
            # FAQ 1 as of April 25, 2024:
            # "Only traffic for the Live environment is counted towards a site plan's traffic limit."

            # The live environment will always exist, but may not be initialized.
            envs, errors, fatal = terminus(
                "env:list",
                site["id"],
                "--fields=id,created,domain,connection_mode,locked,initialized,php_version,php_runtime_generation",
            )
            if fatal or envs is None:
                # Transient/undecodable failure: skip this site, don't abort the whole run.
                sc.console.print(
                    f":exclamation: [bold red] ERROR: could not fetch environments for {site_name}: {escape(errors)}"
                )
                continue
            if "live" not in envs or "initialized" not in envs["live"]:
                sc.console.print(
                    f":exclamation: [bold red] ERROR: {site['name']} does not have a live environment, "
                    "this should never happen"
                )
                sys.exit("Bailing out.")
            if envs["live"]["initialized"] is False:
                sc.console.print(
                    f":exclamation: [bold red] ERROR: {site['name']} is on a paid plan but its live "
                    "environment is not initialized"
                )
                site_context.add_notice(
                    {
                        "type": "alert",
                        "icon": "&#x1F6A8;",  # police car light
                        "csv": f"{site['name']},no-live-env-but-paid-plan",
                        "short": f"no live environment",
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

            # Metrics for an uninitialized live environment will be all zeroes; this is OK.

            live_site = site["id"] + ".live"
            metrics, errors, fatal = terminus("env:metrics", live_site, "--period=day")
            if fatal or metrics is None:
                sc.console.print(
                    f":exclamation: [bold red] ERROR: could not fetch metrics for {site_name}: {escape(errors)}"
                )
                continue

            sc.debug(f"[bold magenta]=== Updating metrics for {site['name']}:")
            db_retry(
                db_session,
                lambda: update_traffic_rows(db_session, site, metrics, start_date, end_date),
                what=f"updating traffic rows for {site['name']}",
                site=site["name"],
            )

            if sc.options.import_older_metrics:
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
                continue  # skip the rest of the processing for the sites

            if sc.options.update:
                sc.console.print("site visitors updated, skipping report")
                continue

            # Get all the data we will use.  This ALSO releases the DB connection before the gather
            # below -- see load_traffic_rows().
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
            # for row in results:
            #    sc.debug(row, level=2)

            sc.invoke_hooks("site_pre", site_context)

            # Per-phase data contract (see CLAUDE.md "Per-site report pipeline"): the traffic
            # window is guaranteed populated from site_post_traffic onward.
            site_context["traffic_rows"] = results
            site_context["start_date"] = start_date
            site_context["end_date"] = end_date
            sc.invoke_hooks("site_post_traffic", site_context)

            # The set of Cloudflare-proxied FQDNs (fqdns.json) is fetched-or-loaded once, before this
            # loop, by the cloudflare plugin's update_and_load_proxied_fqdns setup hook; read it from
            # plugin_context here.  Only consulted below under `if cloudflare_enabled` (which is where
            # the plugin_context bag exists).

            # Query Pantheon for the site's domains
            domains, errors, fatal = terminus("domain:list", live_site)
            if fatal or domains is None:
                sc.console.print(
                    f":exclamation: [bold red] ERROR: could not fetch domains for {site_name}: {escape(errors)}"
                )
                continue
            if sc.options.verbose:
                sc.debug(f"=== Domains for {site['name']}:")
                pprint(domains)
            site_url = ""
            # Resolve the Cloudflare gate and its plugin_context bag once (the bag's net/proxied
            # keys exist only when [Cloudflare] is enabled).
            cf_on = cloudflare_enabled()
            cf_ctx = sc.plugin_context["plugin.cloudflare"] if cf_on else {}
            facts = dns_classify.classify_domains(
                domains,
                cf_on,
                cf_ctx["cloudflare_ipv4_nets"] if cf_on else [],
                cf_ctx["cloudflare_ipv6_nets"] if cf_on else [],
                cf_ctx["proxied_fqdns"] if cf_on else {},
                cf_ctx.get("fqdn_zone_conflicts", {}) if cf_on else {},
                fqdn_re,
            )
            main_fqdn = facts.main_fqdn
            custom_domains = facts.custom_domains
            primary_domain = facts.primary_domain
            fqdns_not_behind_cloudflare = facts.fqdns_not_behind_cloudflare  # used by favicon check
            if isinstance(domains, dict):
                if len(custom_domains) == 0:
                    site_context.add_notice(
                        {
                            "type": "alert",
                            "icon": "&#x1F6A8;",  # police car light
                            "csv": f"{site['name']},no-domains",
                            "short": f"no domains connected",
                            "message": f"""
                <p>{site["name"]} is on a paid plan but does not have any custom domains connected.  Either connect
                a domain through which people will access the site or downgrade the site's plan to Sandbox to save
                money.</p>
                """,
                            "text": f"""
                {site["name"]} is on a paid plan but does not have
                any custom domains connected. Either connect a domain through
                which people will access the ste or downgrade the site's plan
                to Sandbox to save money.
                """,
                        }
                    )
                if (
                    len(custom_domains) > 1
                    and len(primary_domain) == 0
                    and site["framework"] != "wordpress_network"
                ):
                    is_multisite = False
                    if site["framework"].startswith("drupal"):
                        sites_file, errors, fatal = drush_php_script(
                            live_site,
                            'echo json_encode( ["result" => (is_file("/code/web/sites/sites.php") || is_file("/code/sites/sites.php") ? true : false) ] );',
                        )
                        if fatal or sites_file is None:
                            site_context.add_notices(
                                drush_error(
                                    site["name"],
                                    "multisite-check",
                                    f"The check for whether {site['name']} is a Drupal multisite failed.",
                                    errors,
                                )
                            )
                        elif errors != "":
                            drush_smell = errors
                        if (
                            isinstance(sites_file, dict)
                            and "result" in sites_file
                            and sites_file["result"] == True
                        ):
                            is_multisite = True
                        sc.console.print(
                            f"{site['name']} is a Drupal multisite: {sites_file}"
                        )
                    if not is_multisite:
                        site_context.add_notice(
                            {
                                "type": "info",
                                "icon": "&#x1F50E;",  # magnifying glass
                                "csv": f"{site['name']},no-primary-domain,",
                                "short": f"set a primary domain",
                                "message": f"""
                    <p><strong>{site["name"]}</strong>
                    <a href="https://dashboard.pantheon.io/sites/{site["id"]}#live/DomainsHTTPS/list">
                    does not have a primary domain set</a> in the Pantheon dashboard. Setting a
                    <a href="https://docs.pantheon.io/guides/redirect/primary-domain">primary domain</a> will improve SEO.
                    It will also increase the Cloudflare cache hit ratio, lowering Pantheon visitor numbers.</p>
                    <p><i>Do not set a primary domain if </i><strong>{site["name"]}</strong><i> is a multisite.</i></p>
                    """,
                                "text": f"""
                    {site["name"]} does not have a primary domain set
                    in the Pantheon dashboard.
                    <https://dashboard.pantheon.io/sites/{site["id"]}#live/DomainsHTTPS/list>
                    Setting a primary domain
                    <https://docs.pantheon.io/guides/redirect/primary-domain>
                    will improve SEO. It will also increase the Cloudflare
                    cache hit ratio, lowering Pantheon visitor numbers.

                    DO NOT set a primary domain if {site["name"]} is a
                    multisite.
                    """,
                            }
                        )

            # Per-phase data contract (see CLAUDE.md): publish the DnsFacts via the pure helper
            # (unit-tested against value-swaps in test_dns_classify.py), then fire the phase. The
            # check.dns hook consumes these keys to emit the DNS-resolution notices.
            dns_classify.stuff_dns_contract(site_context, domains, facts)
            sc.invoke_hooks("site_post_dns", site_context)

            if main_fqdn != "":
                site_url = f"https://{main_fqdn}/"

            if site["framework"] == "wordpress_network":
                sc.console.print(
                    f"[bold magenta]=== Getting WordPress network URL for {site['name']}:"
                )
                network_home_url, errors, fatal = wp_eval(
                    live_site, "echo network_home_url();"
                )
                if fatal or network_home_url is None:
                    site_context.add_notices(
                        wp_error(
                            site["name"],
                            "version-check",
                            f"Unable to get WordPress network URL for {site['name']}.",
                            errors,
                        )
                    )
                elif errors != "":
                    wp_smell = errors
                sc.debug(f"{site['name']} WordPress network URL: {network_home_url}")
                if isinstance(network_home_url, str):
                    site_url = network_home_url.strip()

            sc.debug(f"Main domain for {site['name']}: {main_fqdn}")
            sc.debug(f"Site URL for {site['name']}:    {site_url}")

            # Check the site's plugins/modules

            # Initialized before the framework branch so the site_post_gather data-contract
            # stuffing below the chain is unconditional (None = not that framework, or the
            # gather failed):
            plugins = None
            mods = None
            wordpress_version = None
            drupal_version = None

            add_on_updates = []
            if site["framework"].startswith("wordpress"):
                sc.console.print(
                    f"[bold magenta]=== Getting WordPress version for {site['name']}:"
                )
                wordpress_version, errors, fatal = wp_eval(
                    live_site, 'require ABSPATH . WPINC . "/version.php"; echo $wp_version;'
                )
                if fatal or wordpress_version is None:
                    site_context.add_notices(
                        wp_error(
                            site["name"],
                            "version-check",
                            f"Unable to check WordPress version for {site['name']}.",
                            errors,
                        )
                    )
                elif errors != "":
                    wp_smell = errors
                sc.debug(f"{site['name']} WordPress version: {wordpress_version}")
                if not isinstance(wordpress_version, str):
                    wordpress_version = "unknown"
                wordpress_version = wordpress_version.strip()
                site_results[site["name"]] = {
                    "framework": site["framework"],
                    "version": wordpress_version,
                    "plan_name": site["plan_name"],
                }
                sc.console.print(
                    f"[bold magenta]=== Checking WordPress plugins for {site['name']}:"
                )
                plugins, errors, fatal = wp(
                    live_site,
                    "plugin",
                    "list",
                    "--fields=name,status,update,version,update_version,title",
                )
                if fatal or plugins is None:
                    site_context.add_notices(
                        wp_error(
                            site["name"],
                            "plugin-list",
                            f"Unable to run <code>wp plugin list</code> for {site['name']}.",
                            errors,
                        )
                    )
                elif errors != "":
                    wp_smell = errors
                if sc.options.verbose:
                    pprint(plugins)
                site_context.add_notices(
                    check_wordpress_plugin(
                        site["name"],
                        plugins,
                        "pantheon-advanced-page-cache",
                        "Pantheon Advanced Page Cache",
                        "https://docs.pantheon.io/guides/wordpress-configurations/wordpress-cache-plugin",
                        "Needed for automatically clearing Pantheon's caches (not Cloudflare's) when content is updated.",
                    )
                )
                site_context.add_notices(
                    check_wordpress_plugin(
                        site["name"],
                        plugins,
                        "wp-native-php-sessions",
                        "Native PHP Sessions",
                        "https://docs.pantheon.io/guides/php/wordpress-sessions#install-wordpress-native-php-sessions-plugin",
                        "Strongly recommended to ensure PHP sessions work correctly on Pantheon.",
                    )
                )
                # The umich-cloudflare plugin check moved to check/umich/cloudflare_cms.py
                # (site_post_gather hook).
                if isinstance(plugins, list):
                    for p in plugins:
                        if p["update"] == "available":
                            add_on_updates.append(
                                {
                                    "slug": p["name"],
                                    "name": p["title"],
                                    "type": "plugin",
                                    "current_version": p["version"],
                                    "new_version": p["update_version"],
                                }
                            )
                        if p["status"] == "must-use" and p["name"] != "loader":
                            sc.console.print(
                                f"[bold yellow]{site['name']} has must-use plugin:"
                            )
                            pprint(p)
                        # Special check for umich-oidc-login upgrade, December 2025
                        if p["name"] == "umich-oidc-login" and p["status"] != "inactive":
                            if semver.compare(p["version"], "1.2.99") <= 0:
                                site_context.add_notice(
                                    {
                                        "type": "warning",
                                        "icon": "&#x26A0;",  # warning sign
                                        "csv": f"{site['name']},umich-oidc-login-reinstall",
                                        "short": "Reinstall the UMich OIDC Login plugin to get the latest version",
                                        "message": f"""
<p><strong>Please reinstall the UMich OIDC Login plugin to get the latest version.</strong></p>
<p>Versions 1.3.0 and later of the UMich OIDC Login plugin are hosted
<a href="https://github.com/its-webhosting/umich-oidc-login">on GitHub</a> rather than on wordpress.org.
{site["name"]} is using version {p["version"]}, so you will need to install version 1.3.0 or later by hand to get
future updates of this plugin through WordPress.  Please use one of the following three methods:
</p>
<ul>
    <li>
        (Simplest method, if you already have <a href="https://docs.pantheon.io/terminus">Terminus</a> set up <a href="https://docs.pantheon.io/terminus/install#ssh-authentication-optional-but-recommended">to work with WP CLI</a>): Run the command
        <pre>
terminus wp {site["name"]}.dev -- plugin install --force --activate https://github.com/its-webhosting/umich-oidc-login/releases/latest/download/umich-oidc-login.zip</pre>And then deploy from Dev to Test, and from Test to Live.<br /><br />
    </li>
    <li>
        Or, <a href="https://github.com/its-webhosting/umich-oidc-login/releases/latest/download/umich-oidc-login.zip">download the latest version</a>,
        upload the zip file through your WordPress admin dashboard using <code>Plugins -> Add New -> Upload Plugin</code>, then activate the plugin.<br /><br />
    </li>
    <li>
        Or, <a href="https://github.com/its-webhosting/umich-oidc-login/releases/latest/download/umich-oidc-login.zip">download the latest version</a>,
        unzip it on your local computer, upload the resulting <code>umich-oidc-login</code> folder to the <code>wp-content/plugins/</code> folder in your site
        (replacing any umich-oidc-login folder that is already there), then activate the plugin.
    </li>
</ul>
<p style="font-size: smaller;"><strong>NOTE:</strong> If your site uses any <code>[umich_oidc_button]</code> or <code>[umich_oidc_link]</code> shortcodes and uses an HTML
attribute (such as <code>class</code> or <code>style</code>) in those shortcodes, after you upgrade, the site will not look right and may
not function correctly unless you turn on the option <code>Settings -> UMich OIDC Login -> Shortcodes ->
Custom buttons and links -> Allow HTML attributes</code>.  This is safe to turn on as long as you trust any users with the
WordPress roles Contributor, Author, and Editor not to use Cross-Site Scripting to compromise an Administrator account
and gain Administrator access for themselves.  If you don't want to turn this option on, an alternative is to use a
child theme or a custom plugin to style the OIDC buttons/links.</p>
""",
                                        "text": f"""
Please reinstall the UMich OIDC Login plugin
to get the latest version.

Versions 1.3.0 and later of the UMich OIDC Login plugin are hosted
on GitHub <https://github.com/its-webhosting/umich-oidc-login>
rather than on wordpress.org. {site["name"]} is using
version {p["version"]}, so you will need to install version 1.3.0
or later by hand to get future updates of this plugin through
WordPress.  Please use one of the following three methods:

* Simplest method, if you already have Terminus
<https://docs.pantheon.io/terminus> set up to work with WP CLI
<https://docs.pantheon.io/terminus/install#ssh-authentication-optional-but-recommended">
Run the command

terminus wp {site["name"]}.dev -- plugin install --force --activate https://github.com/its-webhosting/umich-oidc-login/releases/latest/download/umich-oidc-login.zip

And then deploy from Dev to Test, and from Test to Live.

* Or, download the latest version
<https://github.com/its-webhosting/umich-oidc-login/releases/latest/download/umich-oidc-login.zip>
upload the zip file through your WordPress admin dashboard using
Plugins -> Add New -> Upload Plugin, then activate the plugin.

* Or, download the latest version
<https://github.com/its-webhosting/umich-oidc-login/releases/latest/download/umich-oidc-login.zip>
unzip it on your local computer, upload the resulting
umich-oidc-login folder to the wp-content/plugins/ folder in your
site (replacing any umich-oidc-login folder that is already there),
then activate the plugin.

NOTE: If your site uses any [umich_oidc_button] or
[umich_oidc_link] shortcodes and uses an HTML attribute (such as
"class" or "style") in those shortcodes, after you upgrade, the
site will not look right and may not function correctly unless you
turn on the option Settings -> UMich OIDC Login -> Shortcodes ->
Custom buttons and links -> Allow HTML attributes.  This is safe
to turn on as long as you trust any users with the WordPress roles
Contributor, Author, and Editor not to use Cross-Site Scripting to
compromise an Administrator account and gain Administrator access
for themselves.  If you don't want to turn this option on, an
alternative is to use a child theme or a custom plugin to style
the OIDC buttons/links.
""",
                                    }
                                )
                        # Special check for Object Cache Pro upgrade, see https://docs.pantheon.io/release-notes/2025/10/updated-ocp-config
                        if p["name"] == "object-cache-pro" and p["status"] != "inactive":
                            # This isn't a plugin, but here is a good place to check for it.
                            ocp_config, errors, fatal = wp_eval(
                                live_site,
                                'echo (defined("WP_REDIS_CONFIG") && isset(WP_REDIS_CONFIG["analytics"]["persist"]) && WP_REDIS_CONFIG["analytics"]["persist"])? "true": "false";',
                            )
                            if fatal or ocp_config is None:
                                site_context.add_notices(
                                    wp_error(
                                        site["name"],
                                        "ocp-config-check",
                                        f"Unable to check OCP configuration for {site['name']}.",
                                        errors,
                                    )
                                )
                            elif errors != "":
                                wp_smell = errors
                            if isinstance(ocp_config, str) and ocp_config.startswith(
                                "true"
                            ):
                                site_context.add_notice(
                                    {
                                        "type": "alert",
                                        "icon": "&#x1F6A8;",  # police car light
                                        "csv": f"{site['name']},ocp-config-fix-needed",
                                        "short": "Fix Object Cache Pro configuration",
                                        "message": f'<p>Please <a href="https://docs.pantheon.io/release-notes/2025/10/updated-ocp-config">fix this site\'s Object Cache Pro configuration</a>.</p>',
                                        "text": f"Please fix this site's Object Cache Pro configuration: https://docs.pantheon.io/release-notes/2025/10/updated-ocp-config",
                                    }
                                )
                    # Special check for our fork of Hummingbird (version number contains 'umich')
                    name = "hummingbird-performance"
                    display_name = "UMich Hummingbird"
                    url = "https://documentation.its.umich.edu/node/4243"
                    url2 = "https://documentation.its.umich.edu/node/5114"
                    reason = "UMich Hummingbird is unsupported and has been replaced by University of Michigan: Cloudflare Cache"
                    installed = [
                        p for p in plugins if p["name"] == name and "umich" in p["version"]
                    ]
                    if len(installed) != 0:
                        plugin = installed[0]
                        sc.console.print(
                            f":exclamation: [bold red] ATTENTION: {site} has {display_name} installed."
                        )
                        if "status" in plugin and plugin["status"] == "inactive":
                            site_context.add_notice(
                                {
                                    "type": "info",
                                    "icon": "&#x1F50E;",  # magnifying glass
                                    "csv": f"{site['name']},unsupported-turned-off,{name}",
                                    "short": f"delete inactive plugin {name}",
                                    "message": f'<p>The <a href="{escape_url(url)}">{html.escape(display_name)}</a> WordPress plugin is inactive but should be deleted:</p><p>{html.escape(reason)}</p>',
                                    "text": f"The {display_name} WordPress plugin\n<{url}>\nis inactive but should be deleted: {reason}",
                                }
                            )
                        else:
                            site_context.add_notice(
                                {
                                    "type": "alert",
                                    "icon": "&#x1F6A8;",  # police car light
                                    "csv": f"{site['name']},unsupported,{name}",
                                    "short": f"replace plugin {name} with umich-cloudflare",
                                    "message": f'''
<p>The <a href="{escape_url(url)}">{html.escape(display_name)}</a> WordPress plugin needs to be replaced! It is unsupported and out of date.</p>
<p>Please install the <a href="{escape_url(url2)}">University of Michigan: Cloudflare Cache</a> plugin and remove {html.escape(display_name)}.</p>
''',
                                    "text": f"""
The {display_name} WordPress plugin\n<{url}>\nneeds to be replaced!
It is unsupported and out of date.

Please install the University of Michigan: Cloudflare Cache
<{url2}>
plugin and remove {display_name}.
""",
                                }
                            )
                sc.console.print(
                    f"[bold magenta]=== Checking WordPress themes for {site['name']}:"
                )
                themes, errors, fatal = wp(
                    live_site,
                    "theme",
                    "list",
                    "--fields=name,status,update,version,update_version,title",
                )
                if fatal or themes is None:
                    site_context.add_notices(
                        wp_error(
                            site["name"],
                            "plugin-list",
                            f"Unable to run <code>wp theme list</code> for {site['name']}.",
                            errors,
                        )
                    )
                elif errors != "":
                    wp_smell = errors
                if sc.options.verbose:
                    pprint(themes)
                if isinstance(themes, list):
                    for t in themes:
                        if t["update"] == "available":
                            add_on_updates.append(
                                {
                                    "slug": t["name"],
                                    "name": t["title"],
                                    "type": "theme",
                                    "current_version": t["version"],
                                    "new_version": t["update_version"],
                                }
                            )
                # This isn't a plugin, but here is a good place to check for it.
                favicon, errors, fatal = wp_eval(
                    live_site, 'echo is_file("favicon.ico") ? "true": "false";'
                )
                if fatal or favicon is None:
                    site_context.add_notices(
                        wp_error(
                            site["name"],
                            "favicon-check",
                            f"Unable to check for <code>/favicon.ico</code> file for {site['name']}.",
                            errors,
                        )
                    )
                elif errors != "":
                    wp_smell = errors
                sc.debug(f"{site['name']} has a favicon.ico file: {favicon}")
                if (
                    isinstance(favicon, str)
                    and favicon.startswith("false")
                    and len(fqdns_not_behind_cloudflare) > 0
                ):
                    site_context.add_notice(
                        {
                            "type": "warning",
                            "icon": "&#x26A0;",  # warning sign
                            "csv": f"{site['name']},no-favicon",
                            "short": "add favicon.ico file",
                            "message": f'<p><a href="https://its.umich.edu/computing/web-mobile/cloudflare/getting-started">Put this site behind Cloudflare</a> or add a <a href="https://en.wikipedia.org/wiki/Favicon"><code>/code/favicon.ico</code> file</a> to lower Pantheon visitor numbers and increase the site\'s traffic capacity.</p>',
                            "text": f"Put this site behind Cloudflare\n<https://its.umich.edu/computing/web-mobile/cloudflare/getting-started>\nor add a /code/favicon.ico file\n<https://en.wikipedia.org/wiki/Favicon>\nto lower Pantheon visitor numbers and increase the amount of traffic the site can handle at any time.",
                        }
                    )

            elif site["framework"].startswith("drupal"):
                sc.console.print(
                    f"[bold magenta]=== Checking Drupal modules for {site['name']}:"
                )
                drupal_status, errors, fatal = drush(live_site, "core-status")
                if fatal or drupal_status is None:
                    site_context.add_notices(
                        drush_error(
                            site["name"],
                            "core-status",
                            f"Unable to run <code>drush core-status</code> for {site['name']}.",
                            errors,
                        )
                    )
                elif errors != "":
                    drush_smell = errors
                if sc.options.verbose:
                    pprint(drupal_status)
                drupal_version = (
                    drupal_status["drupal-version"]
                    if isinstance(drupal_status, dict) and "drupal-version" in drupal_status
                    else "unknown"
                )
                site_results[site["name"]] = {
                    "framework": site["framework"],
                    "version": drupal_version,
                    "plan_name": site["plan_name"],
                }
                mods, errors, fatal = drush(live_site, "pm:list")
                if fatal or mods is None:
                    site_context.add_notices(
                        drush_error(
                            site["name"],
                            "pm-list",
                            f"Unable to run <code>drush pm:list</code> for {site['name']}.",
                            errors,
                        )
                    )
                elif errors != "":
                    drush_smell = errors
                if sc.options.verbose:
                    pprint(mods)
                site_context.add_notices(
                    check_drupal_module(
                        site["name"],
                        mods,
                        "pantheon_advanced_page_cache",
                        "Pantheon Advanced Page Cache",
                        "https://www.drupal.org/project/pantheon_advanced_page_cache",
                        "Necessary for automatically clearing Pantheon's caches (not Cloudflare's) when content is updated.",
                    )
                )
                if drupal_version.startswith("7."):
                    site_context.add_notice(
                        {
                            "type": "alert",
                            "icon": "&#x1F6A8;",  # police car light
                            "csv": f"{site['name']},drupal7-eol",
                            "short": f"Migrate off Drupal 7 ASAP",
                            "message": f"""
<p><b>Drupal 7 Extended Support for {site["name"]} will end in December 2026.</b>
Please migrate this site's content to a new site as soon as possible and
then switch {site["name"]} to the Sandbox plan. Plan on a large amount of
time being needed to design the new website, set it up, migrate content, and
then launch the new website before December.</p>
                """,
                            "text": f"""
Drupal 7 Extended Support for {site["name"]} will end in
December 2026.  Please migrate this site's content to a new site
as soon as possible and then switch {site["name"]} to
the Sandbox plan. Plan on a large amount of time being needed to
design the new website, set it up, migrate content, and then
launch the new website before December.
                """,
                        }
                    )
                    site_context.add_notices(
                        check_drupal_module(
                            site["name"],
                            mods,
                            "tag1_d7es",
                            "Tag1 D7ES",
                            "https://docs.pantheon.io/supported-drupal#drupal-7-long-term-support",
                            "Necessary for receiving extended support for Drupal 7.",
                        )
                    )
                # else: the four U-M Cloudflare module checks (cloudflare, cloudflarepurger,
                # purge_processor_lateruntime, purge_processor_cron) moved to
                # check/umich/cloudflare_cms.py (site_post_gather hook).
                if drupal_version.startswith("7."):
                    updates, errors, fatal = drush(live_site, "pm:updatestatus", "--full")
                    if fatal:
                        site_context.add_notices(
                            drush_error(
                                site["name"],
                                "pm-updatestatus",
                                f"Unable to run <code>drush pm:updatestatus</code> for {site['name']}.",
                                errors,
                            )
                        )
                    # elif errors != '':
                    #     drush_smell = errors  # there will always be verbose progress output for pm:upstatestatus
                    if sc.options.verbose:
                        pprint(updates)
                    if isinstance(updates, dict):
                        for package in updates:
                            u = updates[package]
                            current_version = u["existing_version"]
                            new_version = current_version
                            if "candidate_version" in u:
                                new_version = u["candidate_version"]
                            elif "recommended" in u:
                                new_version = u["recommended"]
                            elif "latest_version" in u:
                                new_version = u["latest_version"]
                            if new_version == current_version:
                                new_version = f"none: {u['project_status']}"
                            add_on_updates.append(
                                {
                                    "slug": package,
                                    "name": f'<a href="{escape_url(u["link"])}">{html.escape(u["title"])}</a>'
                                    if "link" in u
                                    else html.escape(u["title"]),
                                    "type": u["type"] if type in u else "package",
                                    "current_version": current_version,
                                    "new_version": new_version,
                                }
                            )
                else:
                    sc.console.print(
                        f"[bold magenta]=== Dry-run update for packages on {site['name']}:"
                    )
                    command = ["composer", live_site, "--", "update", "--dry-run"]
                    updates, errors, fatal = run_terminus(command)
                    if fatal or updates is None:
                        site_context.add_notice(
                            {
                                "type": "alert",
                                "icon": "&#x1F6A8;",  # police car light
                                "csv": f"{site['name']},composer-update",
                                "short": f"fix composer error",
                                "message": f"""
                    <p>Unable to run <code>composer update --dry-run</code> for {site["name"]}.
                    <code>composer</code> returned the following error:</p>
                    <pre>{html.escape(errors)}</pre>
                    """,
                                "text": f"""
                    Unable to run 'composer update --dry-run' for {site["name"]}.
                    composer returned the following error:

                    ----- START DRUSH ERROR -----
                    {errors}
                    ----- END ERROR -----

                    """,
                            }
                        )
                    elif errors != "":
                        composer_smell = errors
                    if sc.options.verbose:
                        pprint(updates)
                    package_updates = {}
                    if isinstance(updates, str):
                        for line in updates.split("\n"):
                            # Example line:
                            # - Upgrading drupal/admin_toolbar (3.4.2 => 3.5.3)
                            m = re.search(
                                r"^\s*-\s+Upgrading\s+(\S+)\s+\((.+) => (.+)\)\s*$", line
                            )
                            if m:
                                package_updates[m.group(1)] = {
                                    "current": m.group(2),
                                    "new": m.group(3),
                                }
                    sc.console.print(
                        f"[bold magenta]=== Running audit for packages on {site['name']}:"
                    )
                    audit, _errors, _fatal = terminus("composer", live_site, "--", "audit")
                    if isinstance(audit, dict):
                        if "advisories" in audit:
                            package_list = audit["advisories"]
                            for package in package_list:
                                vuln = []
                                advisory_list = package_list[package]
                                for advisory in advisory_list:
                                    if isinstance(advisory, str):
                                        advisory = package_list[package][advisory]
                                    if sc.options.verbose:
                                        sc.console.print(
                                            f"[bold yellow]Advisory for {package}:"
                                        )
                                        pprint(advisory)
                                    title = advisory["title"]
                                    t = title.split(" - ")
                                    if advisory["severity"]:
                                        severity = advisory["severity"]
                                    elif len(t) == 4:
                                        severity = t[1]
                                        title = " - ".join([t[0], t[2], t[3]])
                                    else:
                                        severity = "unknown"
                                    vuln.append(
                                        {
                                            "title": f'<a href="{escape_url(advisory["link"])}">{html.escape(title)}</a>',
                                            "severity": severity,
                                        }
                                    )
                                current_version = "unknown"
                                new_version = "unknown"
                                new_version_url = None
                                if package in package_updates:
                                    if "current" in package_updates[package]:
                                        current_version = package_updates[package][
                                            "current"
                                        ]
                                    if "new" in package_updates[package]:
                                        new_version = package_updates[package]["new"]
                                    elif "cve" in package_updates[package]:
                                        cve = package_updates[package]["cve"]
                                        new_version = f"See {cve}"
                                        new_version_url = (
                                            f"https://nvd.nist.gov/vuln/detail/{cve}"
                                        )
                                if new_version == "unknown":
                                    new_version = "See advisory"
                                    new_version_url = advisory["link"]
                                a = {
                                    "slug": package,
                                    "name": vuln,
                                    "type": "package",
                                    "current_version": current_version,
                                    "new_version": new_version,
                                }
                                if new_version_url:
                                    a["new_version_url"] = new_version_url
                                add_on_updates.append(a)
                        if "abandoned" in audit and len(audit["abandoned"]) > 0:
                            sc.console.print("[bold yellow]Abandoned packages:")
                            pprint(audit["abandoned"])
                    else:
                        sc.console.print(
                            f"[bold red]Unable to run <code>composer audit</code> for {site['name']}"
                        )
                    if sc.options.verbose:
                        pprint(audit)
                    sc.console.print(
                        f"[bold magenta]=== Checking for Drupal user agent on {site['name']}:"
                    )
                    ua_check_script = """
$result = 'unknown';
try {
    $client = \\Drupal::httpClient();
    $response = $client->get( 'https://ifconfig.me/ua' );
    $result = $response->getBody();
}
catch ( RequestException $e ) {
    watchdog_exception( 'pantheon_sitehealth_emails', $e->getMessage() );
}
echo( json_encode( array( 'result' => "{$result}" ) ) );
"""
                    ua, errors, fatal = drush_php_script(
                        live_site,
                        ua_check_script,
                    )
                    if fatal or ua is None:
                        site_context.add_notices(
                            drush_error(
                                site["name"],
                                "drupal-ua-check",
                                f"Failed to get the user agent string used by {site['name']}.",
                                errors,
                            )
                        )
                    elif errors != "":
                        drush_smell = errors
                    if (
                        not isinstance(ua, dict)
                        or "result" not in ua
                        or not isinstance(ua["result"], str)
                    ):
                        site_context.add_notices(
                            drush_error(
                                site["name"],
                                "drupal-ua-check",
                                f"Failed to get the user agent string used by {site['name']}.",
                                "Unexpected result from drush php-script.",
                            )
                        )
                    elif (
                        not ua["result"].startswith(
                            "Drupal (+https://drupal.org/); UMich; https://"
                        )
                        or "your-site" in ua["result"].lower()
                        or "your_site" in ua["result"].lower()
                    ):
                        site_context.add_notice(
                            {
                                "type": "info",
                                "icon": "&#x1F50E;",  # magnifying glass
                                "csv": f"{site['name']},drupal-ua,{ua['result']}",
                                "short": "Drupal user agent needs to be configured",
                                "message": f"""
<p>Please <a href="https://documentation.its.umich.edu/node/4242#:~:text=Configure%20site%20User%20Agent">
configure the user agent string</a> that <strong>{site["name"]}</strong> uses for outgoing HTTP requests.
This will ensure that requests for data that this site makes of other University of Michigan websites do
not get blocked.</p>
""",
                                "text": f"""
Please configure the user agent string that {site["name"]}
uses for outgoing HTTP requests.  This will ensure that requests for
data that this site makes of other University of Michigan websites do
not get blocked.

<https://documentation.its.umich.edu/node/4242#:~:text=Configure%20site%20User%20Agent>
""",
                            }
                        )
            else:
                sc.console.print(
                    f":exclamation: [bold red] ATTENTION: unknown framework for {site['name']}: {site['framework']}"
                )
                site_results[site["name"]] = {
                    "framework": site["framework"],
                    "version": "unknown",
                    "plan_name": site["plan_name"],
                }

            # Per-phase data contract (see CLAUDE.md): WP/Drush gather results are guaranteed
            # present from site_post_gather onward.  NOTE: the *_version values are the string
            # "unknown" (not None) when the version fetch failed -- None only means "not that
            # framework".  Only the plugins/modules keys use None for "gather failed".
            site_context["framework"] = site["framework"]
            site_context["site_url"] = site_url
            site_context["wordpress_version"] = wordpress_version
            site_context["wordpress_plugins"] = plugins if isinstance(plugins, list) else None
            site_context["drupal_version"] = drupal_version
            # NOTE: drush pm:list returns a DICT keyed by module name (unlike wp plugin list,
            # which returns a list) -- check_drupal_module requires the dict shape.
            site_context["drupal_modules"] = mods if isinstance(mods, dict) else None
            sc.invoke_hooks("site_post_gather", site_context)

            # Check for un-applied site updates:

            sc.console.print(
                f"[bold magenta]=== Checking for unapplied updates for {site['name']}:"
            )
            updates, _errors, _fatal = terminus("upstream:updates:list", live_site)
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
                    if oldest_update_days <= 7:
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
                    elif oldest_update_days <= 30:
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
                                else "needs maintenance: 1 Pantheon update, {oldest_update_days} days old",
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
                pprint(updates)

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
                        new_version = f'<a href="{escape_url(update["new_version_url"])}">{html.escape(update["new_version"])}</a>'
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

            # April 2026 - September 2026:
            # Check to see if a PHP version upgrade is needed
            php_eol_notice = build_php_eol_notice(site["name"], envs["live"]["php_version"])
            if php_eol_notice is not None:
                site_context.add_notice(php_eol_notice)

            # TODO: Warn if no Autopilot

            # TODO: instead of continuing here, proceed below to calculate plan recommendations, skipping the graph and email
            if sc.options.only_warn:
                for n in site_context["notices"]:
                    all_warnings.append(n["csv"])
                continue

            # Create an array containing the sum of visits by month:
            visits_by_month = {}
            plan_on_day = {}
            d = start_date
            while d <= end_date:
                month = d.strftime("%Y-%m")
                visits_by_month[month] = 0
                d = d.replace(day=1) + datetime.timedelta(days=32)
                d = d.replace(day=1)
            for row in results:
                month = row.traffic_date.strftime("%Y-%m")
                visits_by_month[month] += row.visits
                plan_on_day[row.traffic_date] = row.site_plan
            if sc.options.verbose:
                pprint(visits_by_month)
                if sc.options.verbose > 1:
                    pprint(plan_on_day)

            # Create a list of time ranges when the site was on each plan
            last_day = calendar.monthrange(end_date.year, end_date.month)[1]
            plot_right_date = end_date.replace(day=last_day)
            if not plan_on_day:
                # A brand-new site with no traffic history yet.  Rather than dropping the whole
                # report -- which would silently discard any alerts already gathered above
                # (frozen, not-in-DNS, missing security/cache plugins, ...) and never email the
                # owner -- seed a single synthetic plan-day at the report end date.  That gives
                # the chart/plan code a non-empty plan_on_day (no IndexError, P10) and, because
                # it counts as one in-window month, the report renders in the normal "not enough
                # data yet" state (median_visitors stays 0) while still delivering the alerts.
                sc.console.print(
                    f":mag: No traffic recorded yet for {site_name}; rendering the "
                    f'"not enough data" report with any alerts.'
                )
                plan_on_day = {end_date: site_current_plan}

            # noinspection PyTypeChecker
            days = sorted(plan_on_day.keys())
            plan_over_time = build_plan_over_time(plan_on_day, plot_right_date)
            sc.debug(plan_over_time)

            # Convert the keys of the visits_by_month dictionary to datetime objects
            dates = [datetime.date.fromisoformat(d + "-15") for d in visits_by_month.keys()]
            visits = list(visits_by_month.values())
            visits_covered_by_month = {}
            first_plan_day = days[0]
            last_plan_day = days[-1]
            for month in visits_by_month.keys():
                ymd = datetime.date.fromisoformat(month + "-15")
                if ymd < first_plan_day:
                    ymd = first_plan_day
                if ymd > last_plan_day:
                    ymd = last_plan_day
                visits_covered_by_month[month] = min(
                    visits_by_month[month],
                    int(plan_info[plan_on_day[ymd]]["traffic_limit"]),
                )
            visits_covered = list(visits_covered_by_month.values())

            xbins = [
                datetime.datetime.strptime(d, "%Y-%m").replace(day=1)
                for d in visits_by_month.keys()
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

            # Estimate the visits for the last month if it isn't over yet:
            estimate = estimate_month_visits(visits_by_month, dates, last_day, end_date.day)
            if estimate != -1:
                estimates_by_month = visits_covered_by_month.copy()
                for month in estimates_by_month.keys():
                    estimates_by_month[month] = 0
                estimates_by_month[end_date_yyyy_mm] = estimate
                estimates = list(estimates_by_month.values())

            # figure out whether to show a traffic surge chart
            upgrade_at_max = 0
            for plan in plan_over_time:
                upgrade_at = plan_info[plan["plan"]]["upgrade_at"]
                if upgrade_at > upgrade_at_max:
                    upgrade_at_max = upgrade_at
            surge_threshold = upgrade_at_max * 1.5
            visits_max = max(visits)
            surge = True if visits_max > surge_threshold else False

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
                        bins=xbins,
                        weights=estimates,
                        histtype="barstacked",
                        color="lemonchiffon",
                        edgecolor="black",
                    )
                    est_labels = ax.bar_label(
                        est_bars,
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
                    bins=xbins,
                    weights=visits,
                    histtype="barstacked",
                    color="tab:pink",
                    edgecolor="black",
                )
                ax.bar_label(
                    bars,
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
            gap_bars.extend(est_bars)
            gap_bars.extend(bars)

            # these bars are both below surge_threshold, so we only need to draw them on the plan portion of the chart
            ax_plan.hist(
                dates_num,
                bins=xbins,
                weights=visits_plan,
                histtype="barstacked",
                color="tab:cyan",
                edgecolor="black",
            )
            ax_plan.hist(
                dates_num,
                bins=xbins,
                weights=visits_covered,
                histtype="barstacked",
                color="tab:blue",
                edgecolor="black",
            )

            # Format the x-axis ticks to be in the middle of each month
            left_num = mdates.date2num(start_date)
            right_num = mdates.date2num(plot_right_date)
            ax_plan.set_xlim(left=left_num, right=right_num)
            ax_plan.xaxis.set_major_locator(mdates.MonthLocator(bymonthday=15))
            ax_plan.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
            fig.autofmt_xdate()

            # add bar caps between the two charts
            if surge:
                ylim = ax_plan.get_ylim()
                d = (ylim[1] - ylim[0]) * 0.05
                ylim = ax_surge.get_ylim()
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
                        ax_surge.add_patch(p)
                        ax_surge.vlines(
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
                kwargs = dict(
                    marker=r"$\sim$",
                    markersize=10,
                    color="black",
                    markerfacecolor="black",
                    markeredgecolor="none",
                    linestyle="none",
                    clip_on=False,
                )
                ax_plan.plot([0, 1], [1, 1], transform=ax_plan.transAxes, **kwargs)
                ax_surge.plot([0, 1], [0, 0], transform=ax_surge.transAxes, **kwargs)

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
                                + f"{plan_info[plan_over_time[-1]['plan']]['upgrade_at']:,}"
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
                text_height = matplotlib.rcParams["font.size"] * 1.25
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
                    data_point
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

            sc.debug(f"[bold magenta]=== Creating the traffic table:")

            # TODO: for upgrade/downgrade and new plan columns, add an icon and a colored background so people can
            #   see at a glance if it's more or less than 50% of the time.

            # TODO: If Performance small and below Basic upgrade + no New Relic + No Solr + No Redis + mem usage low --> Switch to Basic

            # Load the overage protection data we need for this site and date range:

            site_plan_start = plan_over_time[0]["start"].replace(day=1)
            traffic_table_rows = db_retry(
                db_session,
                lambda: build_traffic_table_rows(
                    db_session,
                    site,
                    visits_by_month,
                    plan_on_day,
                    plan_info,
                    site_plan_start,
                    first_plan_day,
                    last_plan_day,
                    start_date,
                    end_date,
                    overage_block_size,
                    overage_block_cost,
                ),
                what=f"building the traffic table for {site['name']}",
                site=site["name"],
            )

            sc.debug(traffic_table_rows)

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
                d for d in visits_by_month.keys() if d >= site_plan_start.strftime("%Y-%m")
            ]
            v = [visits_by_month[d] for d in k]
            months_until_recommendations = 0 if len(v) > 4 else 5 - len(v)
            if len(v) > 4:

                # One ranged query for the whole window, snapshotted as plain data; plan_costs()
                # then does ~91 dict lookups instead of ~91 committed round trips to a remote
                # RDS.  Safe because nothing writes to pantheon_overage_protection between
                # build_traffic_table_rows()' commit (above) and plan_costs()' reads (below).
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
                site_recommended_plan = min(costs_best, key=costs_best.get)

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
                                alt = min(bc, key=bc.get)
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
                            site_savings.append(
                                {
                                    "site": site["name"],
                                    "savings": savings,
                                    "current_plan": site["plan_name"],
                                    "recommended_plan": site_recommended_plan,
                                }
                            )
                    else:
                        site_context.add_notice(
                            build_plan_recommendation_notice(
                                site["name"], site["plan_name"], site_recommended_plan,
                                savings, portal_site_id, umich_enabled(),
                            )
                        )
                        site_savings.append(
                            {
                                "site": site["name"],
                                "savings": savings,
                                "current_plan": site["plan_name"],
                                "recommended_plan": site_recommended_plan,
                            }
                        )

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

            site_context.add_notices(
                build_smell_notices(site["name"], wp_smell, drush_smell, composer_smell)
            )

            sc.debug("===== Notices:\n", site_context["notices"])
            sc.debug("===== Sections:\n", site_context["sections"])

            if umich_enabled():
                r = sc.config["UMich"]["portal"]["sites"][site["name"]]["owner_group"]
                r = r.replace(" ", ".")
                recipients = f"{r}@umich.edu, {r}-owners@umich.edu"
                if site_name in ("lsa-disko-project", "umma-inside-wp"):
                    # special case, see TDx 10112051, 10165816
                    recipients = f"{r}@umich.edu"
                contacts = f"{r}@umich.edu"
            else:
                site_team, errors, fatal = terminus("site:team:list", site_id)
                if fatal or site_team is None:
                    sc.console.print(
                        f":exclamation: [bold red] ERROR: could not fetch team for {site_name}: {escape(errors)}"
                    )
                    continue
                recipients = ", ".join(
                    [site_team[team_member]["email"] for team_member in site_team]
                )
                contacts = recipients.replace(",", "")

            # Create email from template
            sorted_notices = (
                [n for n in site_context["notices"] if n["type"] == "alert"]
                + [n for n in site_context["notices"] if n["type"] == "warning"]
                + [n for n in site_context["notices"] if n["type"] == "info"]
            )
            report = f"Pantheon Traffic Report, {end_date.strftime('%b %e, %Y')}"
            subject = f"{site['name']}: {report}"
            # U-M-specific annual-billing subject + notice; only when the UMich plugin is enabled
            # (this block reads the U-M portal config).  end_of_contract_year is date-driven, so
            # without the UMich guard a non-U-M June-dated report crashed with KeyError('UMich').
            if end_of_contract_year and umich_enabled():
                subject = f"Time Sensitive: {site['name']} annual billing"
                shortcode = sc.config["UMich"]["portal"]["sites"][site["name"]]["shortcode"]
                annual_bill = float(plan_info[site_current_plan]["cost"])
                sorted_notices.insert(
                    0,
                    build_annual_bill_upcoming_notice(
                        site["name"], site["plan_name"], annual_bill, shortcode, portal_site_id
                    ),
                )
            elif len(sorted_notices) > 0:
                if sorted_notices[0]["type"] == "alert":
                    subject = f"Action Required: {site['name']}: {sorted_notices[0]['short']} | {report}"
                elif sorted_notices[0]["type"] == "warning":
                    subject = f"Action Recommended: {site['name']}: {sorted_notices[0]['short']} | {report}"
                # no subject prefix for info notices

            # TODO: remove this section at the beginning of August 2026:
            # U-M-specific annual-billing notice; only for institutions running the UMich
            # plugin (it reads the U-M portal config).  Previously an unconditional `if True:`,
            # which crashed every non-U-M / plugin-disabled run with KeyError('UMich').
            if umich_enabled():
                shortcode = sc.config["UMich"]["portal"]["sites"][site["name"]]["shortcode"]
                annual_bill = float(plan_info[site_current_plan]["cost"])
                sorted_notices.insert(
                    0,
                    build_annual_bill_in_progress_notice(
                        site["name"], site["plan_name"], annual_bill, shortcode
                    ),
                )

            # Last per-site seam before rendering (full-report path only; --only-warn continued
            # above).  No consumer yet -- the documented seam for future report-shaping hooks.
            sc.invoke_hooks("site_pre_render", site_context)

            banner_cid = make_msgid(domain=sc.msgid_domain())
            chart_cid = make_msgid(domain=sc.msgid_domain())

            template_dict = dict(
                dry_run_recipient="" if sc.options.for_real else recipients,
                subject=subject,
                site_name=site["name"],
                site_url=site_url,
                portal_site_id=portal_site_id,
                current_plan=site_current_plan,
                recommended_plan=site_recommended_plan,
                current_plan_index=site_current_plan_index,
                recommended_plan_index=site_recommended_plan_index,
                traffic_table_columns=traffic_table_columns,
                traffic_table_rows=traffic_table_rows,
                cost_table_columns=cost_table_columns,
                cost_table_rows=cost_table_rows,
                traffic_date=end_date.strftime("%B %e, %Y"),
                current_month_estimate=f"Estimate for Pantheon visitors at the end of {end_date.strftime('%B %Y')}: "
                f"{estimate:,.0f}"
                if estimate >= 0
                else "",
                median_monthly_visitors=f"{median_visitors:,.0f}",
                months_until_recommendations=months_until_recommendations,
                estimate_start_date=estimate_start_date.strftime("%B %e, %Y"),
                estimate_end_date=estimate_end_date.strftime("%B %e, %Y"),
                notices=sorted_notices,
                news=sc.news,
                sections=site_context["sections"],
                end_of_contract_year=end_of_contract_year,
                banner_cid=banner_cid[1:-1],
                chart_cid=chart_cid[1:-1],
            )

            with open("email_template.html", "r", encoding="utf-8") as f:
                html_template = Template(f.read())
            html_body = html_template.render(**template_dict)
            # Write the results to a file for debugging.  Later, we'll use this file as input to the PHP script that
            # inlines the CSS. We're not piping the data to/from the script directly because the files are useful
            # for inspecting/debugging.
            with open(f"build/{site['name']}.html", "w", encoding="utf-8") as f:
                f.write(html_body)

            with open("email_template.txt", "r", encoding="utf-8") as f:
                text_template = Template(f.read())
            text_body = text_template.render(**template_dict)
            with open(f"build/{site['name']}.txt", "w", encoding="utf-8") as f:
                f.write(text_body)

            subprocess.run(
                [
                    "php",
                    "inline-styles.php",
                    f"build/{site['name']}.html",
                    f"build/{site['name']}-inline.html",
                ],
                stdout=sys.stdout,
                stderr=sys.stderr,
                check=True,
            )
            with open(f"build/{site['name']}-inline.html", "r", encoding="utf-8") as f:
                html_body = f.read()

            style_elements = re.findall(r"(<style.*?</style>)", html_body, re.DOTALL)
            for style in style_elements:
                # Add !important to the end of each CSS attribute that doesn't already end with !important
                modified_style = re.sub(
                    r"(?<!important);", " !important;", style, flags=re.DOTALL
                )
                html_body = html_body.replace(style, modified_style)

            with open(f"build/{site['name']}-inline2.html", "w", encoding="utf-8") as f:
                f.write(html_body)

            msg = EmailMessage()
            # Sender identity + dry-run addressing come from the [Email] config section; the
            # defaults reproduce the historical U-M literals byte-for-byte so an institution that
            # does not set [Email] gets the same output (P8a).
            email_cfg = sc.config.get("Email", {})
            msg["From"] = email_cfg.get(
                "from", "University of Michigan Webmaster Team <webmaster@umich.edu>"
            )
            if sc.options.for_real:
                msg["To"] = recipients
                msg["Bcc"] = email_cfg.get(
                    "bcc", "januside@go.mail.umich.edu, its-webmaster@go.mail.umich.edu"
                )
            else:
                dry_run_to = email_cfg.get("dry_run_to", "januside@go.mail.umich.edu")
                dry_run_domain = email_cfg.get("dry_run_username_domain", "umich.edu")
                # Address the dry run to the configured dry_run_to plus, when a username is
                # resolvable (--smtp-username or [SMTP].username), an operator copy.  When no
                # username is available (e.g. SMTP disabled and no --smtp-username), the operator
                # copy is omitted rather than reading USER from the environment directly.
                username = sc.smtp_username()
                parts = [dry_run_to]
                if username:
                    parts.append(f"{username}@{dry_run_domain}")
                msg["To"] = ", ".join(p for p in parts if p)
            msg["Reply-to"] = email_cfg.get("reply_to", "webmaster@umich.edu")
            msg["Date"] = datetime.datetime.now(datetime.UTC).strftime("%a, %d %b %Y %T %z")
            msg["Subject"] = subject

            msg.set_content(text_body, subtype="plain", charset="utf-8")
            msg.add_alternative(html_body, subtype="html", charset="utf-8")

            msg.get_payload()[1].add_related(
                wordmark_image,
                maintype="image",
                subtype="png",
                filename="pantheon-traffic-email-banner.png",
                cid=banner_cid,
                disposition="inline",
            )

            msg.get_payload()[1].add_related(
                chart_image,
                maintype="image",
                subtype="png",
                filename=f"pantheon-traffic_{site['name']}_{end_date.strftime('%Y%m%d')}.png",
                cid=chart_cid,
                disposition="inline",
            )

            for attachment in site_context["attachments"]:
                msg.get_payload()[1].add_related(
                    attachment["data"],
                    maintype=attachment["maintype"],
                    subtype=attachment["subtype"],
                    filename=attachment["filename"],
                    cid=attachment["cid"],
                    disposition=attachment["disposition"],
                )

            with open(f"build/{site['name']}.eml", "wb") as f:
                f.write(msg.as_bytes(policy=SMTP))

            # BEFORE the send, not after: a Ctrl-C between send_message() and this loop -- a window
            # that includes smtp_connection.quit(), a network round-trip -- used to set
            # site_emailed=True and so advance the resume point PAST this site, and its notices
            # then never reached {ymd}-notices.csv on any run, even though its owner had the email
            # describing them.  Appending first downgrades that to at worst a duplicate CSV row on
            # a re-run, which docs/resuming-interrupted-runs.md already documents as tolerable.
            for n in site_context["notices"]:
                fields = n["csv"].split(",")
                fields.insert(1, contacts)
                all_warnings.append(",".join(fields))

            # The send is gated on [SMTP].enabled; when disabled we still write the .eml above.
            if smtp_enabled:
                smtp_connection = smtp_login()
                smtp_connection.send_message(msg)
                emails_sent += 1
                site_emailed = True
                smtp_connection.quit()

            # TODO: % Pages Cached -- should be Cloudflare
            # TODO: CSV attachment
    except BaseException as e:  # noqa: BLE001 -- DELIBERATE; see the comment below and CLAUDE.md § Database
        # ONE flush path for every way out of the site loop, because finish_run() is the only
        # writer of the run's artifacts and main() has no `finally`.  Enumerating exception classes
        # is what let an SMTP hiccup on site 250 of 300, a php inliner failure, a SystemExit
        # ("Bailing out.") or a KeyError from changed terminus JSON discard 249 sites' work.
        #
        # Only the OUTCOME differs by class, and that is what `reason` selects: a database failure
        # exits 1, an interrupt exits 130, and everything else is re-raised by abort_run() with its
        # traceback (or its SystemExit code and message) intact.  Nothing is swallowed.
        #
        reason = abort_reason(e)
        abort_run(
            db_session, db_engine, site_name, reason, e,
            emailed=site_emailed,
            site_names=site_names, site_count=site_count, emails_sent=emails_sent,
            all_warnings=all_warnings, site_results=site_results, site_savings=site_savings,
        )

    finish_run(
        db_session,
        db_engine,
        site_count,
        emails_sent,
        all_warnings,
        site_results,
        site_savings,
    )


if __name__ == "__main__":
    sc.options = parse_args()
    main()

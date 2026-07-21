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
import datetime
import html
import importlib
import io
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
import tomllib
import urllib.parse
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import make_msgid
from smtplib import SMTP_SSL

import matplotlib
import matplotlib.dates as mdates
import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
import numpy as np
import sqlalchemy as db
from jinja2 import Template
from matplotlib.gridspec import GridSpec
from matplotlib.patches import Polygon
from rich.markup import escape
from rich.padding import Padding
from rich.pretty import pprint
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

import dns_classify
import script_context as sc

fqdn_re = re.compile(r"^_?[a-z0-9-]+\.[a-z0-9.-]+$", re.IGNORECASE)


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
from psh.db import (
    Base,
    DatabaseUnavailableError,
    OverageProtectionRow,
    PantheonOverageProtection,
    PantheonTraffic,
    TrafficRow,
    db_engine_args,
    db_retry,
    db_retryable,
    insert_traffic_rows,
    load_overage_protection_window,
    load_traffic_rows,
    record_db_reconnect,
    update_traffic_rows,
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
from psh.gather import (
    WordPressGather,
    check_wordpress_plugin,
    gather_wordpress,
    wordpress_network_url,
)
from psh.traffic import (
    aggregate_visits_by_month,
    build_traffic_table_rows,
    estimate_month_visits,
    get_old_metrics,
    import_older_site_metrics,
    load_site_traffic,
    traffic_table_columns,
    update_site_traffic,
)
from psh.plans import (
    PlanCatalog,
    PlanInfo,
    PlanRecommendation,
    build_plan_over_time,
    build_plan_recommendation_notice,
    contract_year_end,
    cost_table_columns,
    overage_blocks,
    plan_costs,
    recommend_plan,
    resolve_plan_name,
    stuff_plans_contract,
)
from psh.notice import Notice, Severity, registry
from psh.modules import (
    HookDagError,
    find_modules,
    stuff_envs_contract,
    stuff_gather_contract,
    stuff_traffic_contract,
    validate_hooks,
)

registry.register("no-domains", description="paid plan with no custom domains connected")


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


class ResumeSiteNotFoundError(Exception):
    """--resume-from named a site not present in the org site list."""





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
sc.wp_eval = wp_eval        # check packages: WP-CLI eval probes (check/wordpress ocp, favicon)
sc.wp_error = wp_error      # check packages: WP command-failure notices
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
    # Run-level seam (CAMPAIGN.md section 4): fire before ANY teardown or artifact write so
    # future hooks see the run intact.  No arguments until I13's RunState.
    sc.invoke_hooks("run_finish")
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

    reconnects = sum(sc.db_reconnects_by_site.values())
    reconnect_failures = sum(sc.db_reconnect_failures_by_site.values())

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
                "reconnects_by_site": dict(sc.db_reconnects_by_site),
                "reconnect_failures_by_site": dict(sc.db_reconnect_failures_by_site),
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

    # All modules are loaded; every hook is registered.  Validate the consumes/produces
    # DAG before anything runs (CAMPAIGN.md section 4) -- a bad declaration is a startup
    # fatal, not a mid-run surprise.
    try:
        validate_hooks()
    except HookDagError as e:
        sc.console.print(f"[bold red]ERROR: hook validation failed: {escape(str(e))}")
        sys.exit(1)

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

    catalog = PlanCatalog.from_config(
        sc.config["Pantheon"],
        overage_block_size=overage_block_size,
        overage_block_cost=overage_block_cost,
    )
    # Aliases for readability; the chart (I11) and annual-billing (I12) regions read the
    # raw normalized dict.
    plan_info = catalog.plan_info
    plan_names = catalog.plan_names

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

            plan_name = resolve_plan_name(site)
            if plan_name is None:
                continue
            site["plan_name"] = plan_name
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

            # Metrics for an uninitialized live environment will be all zeroes; this is OK.

            live_site = site["id"] + ".live"
            if not update_site_traffic(db_session, site, live_site, start_date, end_date):
                continue

            if sc.options.import_older_metrics:
                import_older_site_metrics(db_session, site, live_site, end_date)
                continue  # skip the rest of the processing for the sites

            if sc.options.update:
                sc.console.print("site visitors updated, skipping report")
                continue

            results = load_site_traffic(db_session, site, start_date, end_date)

            stuff_envs_contract(site_context, envs)
            sc.invoke_hooks("site_pre", site_context)

            # Per-phase data contract (see CLAUDE.md "Per-site report pipeline"): the traffic
            # window is guaranteed populated from site_post_traffic onward.
            stuff_traffic_contract(site_context, results, start_date, end_date)
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
            if isinstance(domains, dict):
                if len(custom_domains) == 0:
                    site_context.add_notice(
                        Notice(
                            severity=Severity.ALERT,
                            code="no-domains",
                            short="no domains connected",
                            html=f"""
                <p>{site["name"]} is on a paid plan but does not have any custom domains connected.  Either connect
                a domain through which people will access the site or downgrade the site's plan to Sandbox to save
                money.</p>
                """,
                            text=f"""
                {site["name"]} is on a paid plan but does not have
                any custom domains connected. Either connect a domain through
                which people will access the ste or downgrade the site's plan
                to Sandbox to save money.
                """,
                        )
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
                network_url, network_smell = wordpress_network_url(site, live_site, site_context)
                if network_smell != "":
                    wp_smell = network_smell
                if network_url is not None:
                    site_url = network_url

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
                gather = gather_wordpress(site, live_site, site_context)
                wordpress_version = gather.wordpress_version
                plugins = gather.plugins
                add_on_updates = gather.add_on_updates
                if gather.wp_smell != "":
                    wp_smell = gather.wp_smell
                site_results[site["name"]] = gather.results_entry

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
            # present from site_post_gather onward.
            stuff_gather_contract(site_context, site["framework"], site_url,
                                  wordpress_version, plugins, drupal_version, mods,
                                  add_on_updates, wp_smell, drush_smell, composer_smell)
            sc.invoke_hooks("site_post_gather", site_context)

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

            # TODO: Warn if no Autopilot

            visits_by_month, plan_on_day = aggregate_visits_by_month(
                results, start_date, end_date
            )
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

            # Estimate the visits for the last month if it isn't over yet:
            estimate = estimate_month_visits(visits_by_month, dates, last_day, end_date.day)

            first_plan_day = days[0]
            last_plan_day = days[-1]
            site_plan_start = plan_over_time[0]["start"].replace(day=1)

            sc.debug(f"[bold magenta]=== Creating the traffic table:")

            # TODO: for upgrade/downgrade and new plan columns, add an icon and a colored background so people can
            #   see at a glance if it's more or less than 50% of the time.

            # TODO: If Performance small and below Basic upgrade + no New Relic + No Solr + No Redis + mem usage low --> Switch to Basic

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

            # Build the traffic table (which persists+commits this run's overage-protection
            # rows) BEFORE the recommendation, so recommend_plan's op-window read sees them --
            # otherwise the first render of a report, with no prior OP rows, recommends against
            # a different cost table than every later render (campaign I7 final review).
            # Then compare current-plan cost to the other plans (psh.plans.recommend_plan),
            # still before the --only-warn gate so warning-only runs include the recommendation
            # (D7, campaign I7).
            rec = recommend_plan(
                db_session,
                site,
                catalog,
                visits_by_month,
                site_plan_start,
                estimate,
                start_date,
                end_date,
                portal_site_id,
                site_context,
            )
            site_recommended_plan = rec.recommended_plan
            site_current_plan_index = rec.current_plan_index
            site_recommended_plan_index = rec.recommended_plan_index
            median_visitors = rec.median_visitors
            cost_table_rows = rec.cost_table_rows
            months_until_recommendations = rec.months_until_recommendations
            estimate_start_date = rec.estimate_start_date
            estimate_end_date = rec.estimate_end_date
            if rec.savings_entry is not None:
                site_savings.append(rec.savings_entry)

            if sc.options.only_warn:
                for n in site_context["notices"]:
                    all_warnings.append(n["csv"])
                continue

            visits_covered_by_month = {}
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

            site_context.add_notices(
                build_smell_notices(site["name"], site_context["wp_smell"],
                                    site_context["drush_smell"],
                                    site_context["composer_smell"])
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

            stuff_plans_contract(
                site_context,
                site_current_plan,
                site_recommended_plan,
                {"same": rec.cost_same, "median": rec.costs_median,
                 "best": rec.costs_best}
                if rec.cost_same
                else {},
                rec.savings,
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

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
import importlib
import os
import re
import signal  # noqa: F401 -- retained as the psh.signal.signal monkeypatch seam (CLAUDE.md § Two mock seams): abort_run's SIGINT guard moved to psh/lifecycle.py at I13, but test_abort_run.py patches the shared signal module object via psh.signal (SPEC I13 §5)
import subprocess  # noqa: F401 -- retained as the psh.subprocess.Popen monkeypatch seam (CLAUDE.md § Two mock seams): run_terminus lives in psh/gateway.py but tests patch the shared module object via psh._legacy.subprocess; render's subprocess.run moved to psh/render.py at I12
import sys
import time
import tomllib
from email.utils import make_msgid

import sqlalchemy as db
from rich.markup import escape
from rich.padding import Padding
from rich.pretty import pprint

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
from psh.charts import build_chart
from psh.gather import (
    DrupalGather,
    WordPressGather,
    build_smell_notices,
    check_drupal_module,
    check_wordpress_plugin,
    gather_drupal,
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
from psh.render import escape_url, render_report
from psh.mail import assemble_message, resolve_recipients, smtp_login
from psh.notice import Notice, Severity, registry
from psh.modules import (
    HookDagError,
    find_modules,
    stuff_envs_contract,
    stuff_gather_contract,
    stuff_traffic_contract,
    validate_hooks,
)
from psh.lifecycle import (
    RunState,
    ResumeSiteNotFoundError,
    abort_reason,
    abort_run,
    finish_run,
    merge_prior_results,
    option_strings_taking_a_value,
    rerun_command,
    resume_command,
    resume_point,
    sites_from_resume_point,
)

registry.register("no-domains", description="paid plan with no custom domains connected")


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
sc.drush_php_script = drush_php_script  # check packages: drush php probes (check/drupal multisite, check/umich drupal_ua)
sc.drush_error = drush_error            # check packages: drush command-failure notices
sc.contract_year_end = contract_year_end  # check packages: U-M billing-window test (check/umich annual_billing)
sc.fqdn_re = fqdn_re        # check packages: validate remote domain ids with the SAME regex
sc.db_engine_args = db_engine_args  # plugin/umich/portal.py: ONE URL builder, ONE set of pool
                                    # settings for every database this program connects to


def no_primary_domain_notice(site, custom_domains, primary_domain, is_multisite):
    """Return the no-primary-domain info notice dict, or None when it does not apply
    (BLOCKMAP B30; extracted at campaign I10 -- SPEC D-i10-3)."""
    if (
        len(custom_domains) > 1
        and len(primary_domain) == 0
        and site["framework"] != "wordpress_network"
        and not is_multisite
    ):
        return {
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
    return None


def sort_notices_and_subject(site_context, report):
    """B50 sort/subject core + billing-key wiring (pure; final home I13's main()).

    Returns ``(sorted_notices, subject)``.  Reads the two hook-produced billing keys
    (`annual_bill_upcoming` / `annual_bill_in_progress`, from check/umich/annual_billing)
    with ``.get()`` and inserts them into the render-only `sorted_notices` list -- they
    never enter ``site_context["notices"]``, so no -notices.csv rows (SPEC I12 §2.2).
    Preserved quirks: `annual_bill_upcoming` overrides the subject and is inserted at
    subject-computation time; `annual_bill_in_progress` is inserted LAST (so it renders
    first) but AFTER the subject is fixed, so it never influences the subject.
    """
    site_name = site_context["site"]["name"]
    sorted_notices = (
        [n for n in site_context["notices"] if n["type"] == "alert"]
        + [n for n in site_context["notices"] if n["type"] == "warning"]
        + [n for n in site_context["notices"] if n["type"] == "info"]
    )
    subject = f"{site_name}: {report}"
    # U-M-specific annual-billing subject + notice: the `annual_bill_upcoming` key exists iff
    # the upcoming hook was registered ([UMich].enabled) AND its window condition held
    # (end_of_contract_year) -- equivalent by construction to the old inline guard.
    if (upcoming := site_context.get("annual_bill_upcoming")) is not None:
        subject = f"Time Sensitive: {site_name} annual billing"
        sorted_notices.insert(0, upcoming)
    elif len(sorted_notices) > 0:
        if sorted_notices[0]["type"] == "alert":
            subject = f"Action Required: {site_name}: {sorted_notices[0]['short']} | {report}"
        elif sorted_notices[0]["type"] == "warning":
            subject = f"Action Recommended: {site_name}: {sorted_notices[0]['short']} | {report}"
        # no subject prefix for info notices

    # TODO: remove this section at the beginning of August 2026:
    # the `annual_bill_in_progress` key, produced by check/umich/annual_billing's in-progress
    # hook.  Inserted last so it renders first, but AFTER the subject computation so it never
    # influences the subject (preserved quirk).
    if (in_progress := site_context.get("annual_bill_in_progress")) is not None:
        sorted_notices.insert(0, in_progress)

    return sorted_notices, subject


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

    # The run's accumulators live on ONE RunState, bound to sc.run_state BEFORE any hook fires:
    # a setup hook that reached db_retry would otherwise write into a RunState main() then
    # discards (SPEC 2.1).  db_retry() writes the reconnect counters through sc.run_state; the
    # site loop below fills the rest; finish_run/abort_run read it back as a parameter.
    sc.run_state = RunState()
    run_state = sc.run_state

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
    start_date = end_date.replace(
        day=1, year=end_date.year - 1
    )  # fist day of the same month last year
    end_of_contract_year = contract_year_end(end_date)
    sc.debug(f"Generating report for {start_date} through {end_date}")

    try:
        sites = terminus_data("org:site:list", sc.config["Pantheon"]["org_id"])
    except TerminusError as e:
        sys.exit(f"Could not list organization sites: {e}")
    site_count = len(sites)
    current_site_number = 1
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

            # Per-phase data contract (see CLAUDE.md): publish the DnsFacts via the pure helper
            # (unit-tested against value-swaps in test_dns_classify.py), then fire the phase. The
            # check.dns hook consumes these keys to emit the DNS-resolution notices.
            dns_classify.stuff_dns_contract(site_context, domains, facts)
            sc.invoke_hooks("site_post_dns", site_context)

            # The Drupal multisite probe (was B30, inline here) moved to
            # check/drupal/multisite.py, a site_post_dns hook -- its produced keys are
            # DAG-declared, not contract-guaranteed (CLAUDE.md, CAMPAIGN.md section 4
            # amendment 2), so read with .get() (campaign I10, SPEC D-i10-3).
            probe_smell = site_context.get("drupal_multisite_smell", "")
            if probe_smell != "":
                drush_smell = probe_smell
            notice = no_primary_domain_notice(
                site, custom_domains, primary_domain, site_context.get("drupal_multisite", False)
            )
            if notice is not None:
                site_context.add_notice(notice)

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
                run_state.site_results[site["name"]] = gather.results_entry

            elif site["framework"].startswith("drupal"):
                gather = gather_drupal(site, live_site, site_context)
                drupal_version = gather.drupal_version
                mods = gather.modules
                add_on_updates = gather.add_on_updates
                if gather.drush_smell != "":
                    drush_smell = gather.drush_smell
                if gather.composer_smell != "":
                    composer_smell = gather.composer_smell
                run_state.site_results[site["name"]] = gather.results_entry

            else:
                sc.console.print(
                    f":exclamation: [bold red] ATTENTION: unknown framework for {site['name']}: {site['framework']}"
                )
                run_state.site_results[site["name"]] = {
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
                run_state.site_savings.append(rec.savings_entry)

            if sc.options.only_warn:
                for n in site_context["notices"]:
                    run_state.all_warnings.append(n["csv"])
                continue

            chart_image = build_chart(
                site, site_url, visits_by_month, plan_on_day, plan_info,
                plan_over_time, dates, estimate, first_plan_day, last_plan_day,
                start_date, end_date, plot_right_date,
            )

            site_context.add_notices(
                build_smell_notices(site["name"], site_context["wp_smell"],
                                    site_context["drush_smell"],
                                    site_context["composer_smell"])
            )

            sc.debug("===== Notices:\n", site_context["notices"])
            sc.debug("===== Sections:\n", site_context["sections"])

            resolved = resolve_recipients(site, site_id)
            if resolved is None:
                continue
            recipients, contacts = resolved

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
            # above).  check.umich.annual_billing's two hooks run here, producing the billing
            # keys the sort/subject helper wires in below; other future hooks may add notices.
            sc.invoke_hooks("site_pre_render", site_context)

            # Sort + subject AFTER the phase (campaign I12): hooks that add notices now
            # render, and the billing hooks' produced keys are wired in by the helper.
            report = f"Pantheon Traffic Report, {end_date.strftime('%b %e, %Y')}"
            sorted_notices, subject = sort_notices_and_subject(site_context, report)

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

            html_body, text_body = render_report(site["name"], template_dict)

            msg = assemble_message(
                subject, recipients, text_body, html_body, wordmark_image, chart_image,
                banner_cid, chart_cid, site_context["attachments"], site["name"], end_date,
            )

            # BEFORE the send, not after: a Ctrl-C between send_message() and this loop -- a window
            # that includes smtp_connection.quit(), a network round-trip -- used to set
            # site_emailed=True and so advance the resume point PAST this site, and its notices
            # then never reached {ymd}-notices.csv on any run, even though its owner had the email
            # describing them.  Appending first downgrades that to at worst a duplicate CSV row on
            # a re-run, which docs/resuming-interrupted-runs.md already documents as tolerable.
            for n in site_context["notices"]:
                fields = n["csv"].split(",")
                fields.insert(1, contacts)
                run_state.all_warnings.append(",".join(fields))

            # The send is gated on [SMTP].enabled; when disabled we still write the .eml above.
            if smtp_enabled:
                smtp_connection = smtp_login()
                smtp_connection.send_message(msg)
                run_state.emails_sent += 1
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
            site_names=site_names, site_count=site_count, run_state=run_state,
        )

    finish_run(
        db_session,
        db_engine,
        site_count,
        run_state,
    )


if __name__ == "__main__":
    sc.options = parse_args()
    main()

"""The pantheon-sitehealth-emails orchestrator: argparse, main(), and the per-site pipeline.

This is the program body -- the extension-less ./pantheon-sitehealth-emails shim sets
sc.options = parse_args() and calls main() here.  The modularization campaign carved the
gateway, config, db, traffic, plans, gather, charts, render, mail, and lifecycle layers
into sibling psh/ modules; this module orchestrates them and re-exports their public
surface so the test harness reaches every name as psh.<name> (see the re-export note below).
See development/2026-07-17-modularization-campaign/CAMPAIGN.md.

TODO: add WordPress MU plugin check (report on anything except plugin)
"""

import argparse
import datetime
import re
import signal  # noqa: F401 -- retained as the psh.signal.signal monkeypatch seam (CLAUDE.md § Two mock seams): abort_run's SIGINT guard moved to psh/lifecycle.py at I13, but test_abort_run.py patches the shared signal module object via psh.signal (SPEC I13 §5)
import subprocess  # noqa: F401 -- retained as the psh.subprocess.Popen monkeypatch seam (CLAUDE.md § Two mock seams): run_terminus lives in psh/gateway.py but tests patch the shared module object via psh.subprocess (the conftest psh fixture is this module, psh.cli); render's subprocess.run moved to psh/render.py at I12
import sys
import time  # noqa: F401 -- retained as the psh.time.sleep monkeypatch seam (CLAUDE.md § Two mock seams): the real time.sleep(5) lives in psh/gateway.py, but 13 tests patch the shared module object via psh.time (the conftest psh fixture is this module, psh.cli)
import tomllib
from email.utils import make_msgid
from pathlib import Path
from typing import NamedTuple

import sqlalchemy as db  # noqa: F401 -- retained as the psh.db.* test seam (tests/conftest.py TempDB uses psh.db.create_engine / psh.db.orm.sessionmaker, which resolve to THIS alias on the psh.cli module, not the psh/db.py package): B10's last in-file use (db.create_engine/db.orm.sessionmaker) moved to psh.db.open_database at I13
from rich.markup import escape
from rich.padding import Padding
from rich.pretty import pprint

import psh.dns_classify as dns_classify  # noqa: PLR0402 -- SPEC D-i14a-2 mandates this alias form: it keeps every qualified dns_classify.<attr> call site and the single-object monkeypatch seam byte-compatible
import script_context as sc
from psh.charts import build_chart

# Re-export surface (SPEC D-i14a-3): the conftest `psh` fixture exposes THIS module's
# attributes as psh.<name>, so the whole former-psh._legacy public surface must stay
# importable from here.  Names main() does not itself use are marked F401-suppressed per
# line -- they are deliberate re-exports the harness reaches through the fixture, not dead imports.
from psh.configuration import (
    cloudflare_enabled,
    config_substitution,  # noqa: F401
    gate_disabled_sections,
    load_news_items,
    process_config,
    umich_enabled,
)
from psh.db import (
    Base,
    DatabaseUnavailableError,  # noqa: F401
    OverageProtectionRow,  # noqa: F401
    PantheonOverageProtection,  # noqa: F401
    PantheonTraffic,  # noqa: F401
    TrafficRow,  # noqa: F401
    db_engine_args,
    db_retry,
    db_retryable,  # noqa: F401
    insert_traffic_rows,  # noqa: F401
    load_overage_protection_window,  # noqa: F401
    load_traffic_rows,  # noqa: F401
    open_database,
    record_db_reconnect,  # noqa: F401
    update_traffic_rows,  # noqa: F401
)
from psh.gateway import (
    GatewayResult,  # noqa: F401
    TerminusError,
    drush,  # noqa: F401
    drush_error,
    drush_php_script,
    fix_drush_output,  # noqa: F401
    run_terminus,  # noqa: F401
    terminus,
    terminus_data,
    wp,  # noqa: F401
    wp_error,
    wp_eval,
)
from psh.gather import (
    DrupalGather,  # noqa: F401
    WordPressGather,  # noqa: F401
    build_smell_notices,
    check_drupal_module,
    check_wordpress_plugin,
    gather_framework,
    wordpress_network_url,
)
from psh.lifecycle import (
    ResumeSiteNotFoundError,
    RunState,
    abort_reason,
    abort_run,
    finish_run,
    merge_prior_results,  # noqa: F401
    option_strings_taking_a_value,  # noqa: F401
    rerun_command,  # noqa: F401
    resume_command,  # noqa: F401
    resume_point,  # noqa: F401
    sites_from_resume_point,
)
from psh.mail import assemble_message, resolve_recipients, smtp_login
from psh.modules import (
    HookDagError,
    find_modules,  # noqa: F401
    import_packages,
    stuff_envs_contract,
    stuff_gather_contract,
    stuff_traffic_contract,
    validate_hooks,
)
from psh.notice import Notice, Severity, registry
from psh.plans import (
    PlanCatalog,
    PlanInfo,  # noqa: F401
    PlanRecommendation,  # noqa: F401
    build_plan_over_time,  # noqa: F401 -- re-export surface (SPEC D-i14a-3): tests/unit/test_plan_over_time.py calls it as psh.build_plan_over_time, not psh.traffic.build_plan_over_time
    build_plan_recommendation_notice,  # noqa: F401
    contract_year_end,
    cost_table_columns,
    overage_blocks,  # noqa: F401
    plan_costs,  # noqa: F401
    recommend_plan,
    resolve_site_plan,
    stuff_plans_contract,
)
from psh.render import escape_url, render_report
from psh.traffic import (
    build_traffic_table_rows,
    build_traffic_window,
    estimate_month_visits,  # noqa: F401 -- re-export surface (SPEC D-i14a-3): tests/unit/test_plan_math.py calls it as psh.estimate_month_visits
    get_old_metrics,  # noqa: F401
    import_older_site_metrics,
    load_site_traffic,
    traffic_table_columns,
    update_site_traffic,
)

fqdn_re = re.compile(r"^_?[a-z0-9-]+\.[a-z0-9.-]+$", re.IGNORECASE)


# Notice codes registered at import; see CLAUDE.md § Notices vs. news.
NOTICE_NO_DOMAINS = registry.register(
    "no-domains", description="paid plan with no custom domains connected")
NOTICE_NO_PRIMARY_DOMAIN = registry.register(
    "no-primary-domain", description="multiple custom domains, none primary")


# Expose helpers for check/ packages, which cannot import this dash-named script.
# Same convention as sc.plugin_context['plugin.cloudflare']['get_client']: shared state /
# callables travel via the sc module.  Tests monkeypatch these sc attributes when loading
# check modules standalone.  script_context gains these attributes at RUNTIME (assigned
# here), invisible to pyright, so each line carries a scoped reportAttributeAccessIssue
# ignore; the real guard is the test_documented_sc_facade_names_exist house-rule.
sc.escape_url = escape_url  # pyright: ignore[reportAttributeAccessIssue]
sc.check_wordpress_plugin = check_wordpress_plugin  # pyright: ignore[reportAttributeAccessIssue]
sc.check_drupal_module = check_drupal_module  # pyright: ignore[reportAttributeAccessIssue]
sc.umich_enabled = umich_enabled  # pyright: ignore[reportAttributeAccessIssue]
sc.cloudflare_enabled = cloudflare_enabled  # pyright: ignore[reportAttributeAccessIssue]
sc.terminus = terminus  # pyright: ignore[reportAttributeAccessIssue]  # check packages: Pantheon calls (e.g. domain:dns) go through this
sc.wp_eval = wp_eval  # pyright: ignore[reportAttributeAccessIssue]  # check packages: WP-CLI eval probes (check/wordpress ocp, favicon)
sc.wp_error = wp_error  # pyright: ignore[reportAttributeAccessIssue]  # check packages: WP command-failure notices
sc.drush_php_script = drush_php_script  # pyright: ignore[reportAttributeAccessIssue]  # check packages: drush php probes (check/drupal multisite, check/umich drupal_ua)
sc.drush_error = drush_error  # pyright: ignore[reportAttributeAccessIssue]  # check packages: drush command-failure notices
sc.contract_year_end = contract_year_end  # pyright: ignore[reportAttributeAccessIssue]  # check packages: U-M billing-window test (check/umich annual_billing)
sc.fqdn_re = fqdn_re  # pyright: ignore[reportAttributeAccessIssue]  # check packages: validate remote domain ids with the SAME regex
sc.db_engine_args = db_engine_args  # pyright: ignore[reportAttributeAccessIssue]  # plugin/umich/portal.py: ONE URL builder, ONE set of pool
                                    # settings for every database this program connects to


# Command-line argument parsing.  Building the parser is side-effect-free; parse_args()
# (which reads sys.argv) is invoked only by the extension-less ./pantheon-sitehealth-emails
# shim, so this module can be imported by the test harness without argv side effects.
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
        default=datetime.date.today(),  # noqa: DTZ011 -- verbatim; the --date default is the operator's local calendar day, and a tz-aware default risks an off-by-one at midnight UTC (a behavior change a move may not make)
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


def validate_options() -> None:
    """B5: the four argument guards, in their shadowing order, verbatim from main()
    (development/2026-08-07-main-extraction/SPEC.md section 5.6).

    Each guard calls sys.exit(<message>) -- a POSTCONDITION of this function, not a
    caller concern (the same idiom as resolve_site_plan's "Bailing out." exit).  NOT
    pure: the --create-tables branch sets sc.options.verbose = 3 in place.

    Reads sc.options/sc.config at call time -- the house rule (sc.smtp_username(),
    resolve_plan_name, cloudflare_enabled all do this) -- so main() MUST call this
    AFTER process_config() pass 1, because the fourth guard reads sc.config.
    """
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


# INVARIANT 8 -- DO NOT RE-INDENT THE html=/text= LITERALS BELOW.  Every interior line, and
# both closing triple quotes, MUST stay at column 16 counted from the start of the line --
# NOT at an indent relative to the `html=`/`text=` keyword, and NOT whatever a formatter
# thinks this frame deserves.  Those leading spaces are string content: they are rendered
# into three of the four e2e goldens (tests/e2e/__snapshots__/test_golden.ambr,
# test_golden_drupal.ambr, test_golden_nonumich.ambr) and into the email every site owner
# on a paid plan with no custom domains receives.  `git diff -w` cannot see a violation;
# tests/unit/test_no_domains_notice.py::test_the_literal_interior_stays_at_column_16 can.
# (CAMPAIGN.md section 9.8; development/2026-08-07-main-extraction/SPEC.md R3.6/R3.6a.)
def no_domains_notice(site, domains, custom_domains) -> Notice | None:
    """Return the no-domains alert Notice, or None when it does not apply (BLOCKMAP B29's
    notice half; extracted from main() at development/2026-08-07-main-extraction/SPEC.md
    section 5.3, R3.6d).

    PURE: no I/O, no sc.console, no SiteContext.  Deliberately mirrors its sibling
    no_primary_domain_notice below -- same module, same shape, same `-> Notice | None`
    contract -- so both of this module's notice builders are unit-testable at the same
    seam.  fetch_site_domains calls it and does the site_context.add_notice(), exactly as
    main() already does for no_primary_domain_notice.

    `domains` is the RAW terminus("domain:list") payload and `custom_domains` the
    already-classified DnsFacts field.  Both guards are needed and neither is defensive:
    classify_domains returns an all-empty DnsFacts for any non-dict payload, so the
    isinstance guard is the only thing standing between a malformed domain:list and a
    false ALERT telling the owner to downgrade a site whose domains were never read.
    """
    if isinstance(domains, dict):  # noqa: SIM102 -- NOT merged with the nested if: the body is a moved-verbatim Notice whose html/text f-strings carry golden-pinned column-16 leading whitespace (three e2e goldens); collapsing the ifs would dedent that literal and change the rendered email (Invariant 8)
        if len(custom_domains) == 0:
            return Notice(
                severity=Severity.ALERT,
                code=NOTICE_NO_DOMAINS,
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
    return None


def no_primary_domain_notice(site, custom_domains, primary_domain, is_multisite) -> Notice | None:
    """Return the no-primary-domain info Notice, or None when it does not apply
    (BLOCKMAP B30; extracted at campaign I10 -- SPEC D-i10-3; rode to psh/cli.py with
    main() at I14a -- D-i13-1 discharged).

    csv_extra is one EMPTY field: this row has always ended in a trailing comma, and the
    empty field is part of the historical -notices.csv shape (SPEC I14c §2.1)."""
    if (
        len(custom_domains) > 1
        and len(primary_domain) == 0
        and site["framework"] != "wordpress_network"
        and not is_multisite
    ):
        return Notice(
            severity=Severity.INFO,
            code=NOTICE_NO_PRIMARY_DOMAIN,
            csv_extra=("",),
            short="set a primary domain",
            html=f"""
                    <p><strong>{site["name"]}</strong>
                    <a href="https://dashboard.pantheon.io/sites/{site["id"]}#live/DomainsHTTPS/list">
                    does not have a primary domain set</a> in the Pantheon dashboard. Setting a
                    <a href="https://docs.pantheon.io/guides/redirect/primary-domain">primary domain</a> will improve SEO.
                    It will also increase the Cloudflare cache hit ratio, lowering Pantheon visitor numbers.</p>
                    <p><i>Do not set a primary domain if </i><strong>{site["name"]}</strong><i> is a multisite.</i></p>
                    """,
            text=f"""
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
        )
    return None


class SiteDomains(NamedTuple):
    domains: object               # the RAW domain:list payload; never None (a fatal/undecodable fetch returns the skip sentinel instead)
    facts: dns_classify.DnsFacts  # all-empty when `domains` is not a dict


def fetch_site_domains(site: dict, live_site: str, site_context) -> SiteDomains | None:
    """B29: fetch the site's domains and classify them, verbatim from main().

    Returns None -- the SKIP SENTINEL -- on a fatal or undecodable domain:list; the caller
    does the `continue` (loop control stays in main(), D-i6-1 / SPEC R-G3).  The skip is
    never silent: it prints the ERROR line naming the site first (PD#1).

    Parameter order and annotations match gather_framework(site, live_site, site_context)
    and resolve_site_url on purpose: the three read as one stage in main() and a swapped
    (site, live_site) pair is otherwise invisible to pyright.  There is no separate
    site_name parameter -- main() binds `site = sites[site_name_to_id[site_name]]` from a
    map keyed by `site["name"]`, so the two are the same string, and one identity per site
    cannot be passed mismatched by a test.

    The set of Cloudflare-proxied FQDNs (fqdns.json) is fetched-or-loaded once, before the
    site loop, by the cloudflare plugin's update_and_load_proxied_fqdns setup hook; this
    reads it from plugin_context.  The bag is only consulted under `if cf_on`, which is the
    only state in which it exists.

    Emits the no-domains alert through the pure no_domains_notice builder, in the identical
    `if notice is not None` shape main() already uses for no_primary_domain_notice.  Extracted
    at development/2026-08-07-main-extraction/SPEC.md section 5.3.
    """
    # Query Pantheon for the site's domains
    domains, errors, fatal = terminus("domain:list", live_site)
    if fatal or domains is None:
        sc.console.print(
            f":exclamation: [bold red] ERROR: could not fetch domains for {site['name']}: {escape(errors)}"
        )
        return None
    if sc.options.verbose:
        sc.debug(f"=== Domains for {site['name']}:")
        pprint(domains)
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
    notice = no_domains_notice(site, domains, facts.custom_domains)
    if notice is not None:
        site_context.add_notice(notice)
    return SiteDomains(domains=domains, facts=facts)


class SiteUrlFacts(NamedTuple):
    site_url: str      # "" when there is no main_fqdn and no WP-network URL
    wp_smell: str      # "" = no NEW smell -- a delta, merged by main()
    drush_smell: str   # "" = no NEW smell -- a delta, merged by main()


def resolve_site_url(site: dict, live_site: str, site_context, facts) -> SiteUrlFacts:
    """B30 (residue) + B31's site_url derivation + B32 (residue): the post-site_post_dns half
    of the domains stage, verbatim from main().  Never returns None -- this region has no
    skip path.

    Runs AFTER sc.invoke_hooks("site_post_dns"), which is why it can read
    drupal_multisite_smell / drupal_multisite at all: check.drupal.multisite PRODUCES them in
    that phase.  Both are hook-produced, not registry-owned, so both are read with .get() --
    they are absent whenever the probe did not run (every WordPress site, [Check.drupal]
    disabled, or a failed gate), and an index read would be a KeyError on the common path.

    The two smells are DELTAS (SPEC R-G5 / psh/gather.py's module docstring): "" means no NEW
    smell, NEVER "clear the previous one", and this function is deliberately never handed the
    caller's current values -- main() keeps the last-wins merge.  Extracted at
    development/2026-08-07-main-extraction/SPEC.md section 5.3.
    """
    site_url = ""
    wp_smell = ""
    drush_smell = ""
    # The Drupal multisite probe (was B30, inline here) moved to
    # check/drupal/multisite.py, a site_post_dns hook -- its produced keys are
    # DAG-declared, not contract-guaranteed (CLAUDE.md, CAMPAIGN.md section 4
    # amendment 2), so read with .get() (campaign I10, SPEC D-i10-3).
    probe_smell = site_context.get("drupal_multisite_smell", "")
    if probe_smell != "":
        drush_smell = probe_smell
    notice = no_primary_domain_notice(
        site, facts.custom_domains, facts.primary_domain,
        site_context.get("drupal_multisite", False),
    )
    if notice is not None:
        site_context.add_notice(notice)

    if facts.main_fqdn != "":
        site_url = f"https://{facts.main_fqdn}/"

    if site["framework"] == "wordpress_network":
        network_url, network_smell = wordpress_network_url(site, live_site, site_context)
        if network_smell != "":
            wp_smell = network_smell
        if network_url is not None:
            site_url = network_url

    sc.debug(f"Main domain for {site['name']}: {facts.main_fqdn}")
    sc.debug(f"Site URL for {site['name']}:    {site_url}")
    return SiteUrlFacts(site_url=site_url, wp_smell=wp_smell, drush_smell=drush_smell)


class SiteRoster(NamedTuple):
    sites: dict                  # org:site:list payload keyed by site id
    name_to_id: dict[str, str]
    site_names: list[str]        # sorted, resume-filtered
    site_count: int              # len(sites) BEFORE the filter -- the banner/finish_run denominator, NEVER len(site_names)


def resolve_site_roster(org_id: str) -> SiteRoster:
    """B14: fetch the org's site list and build the sorted, --resume-from-filtered roster,
    verbatim from main().

    sys.exit()s on a fatal org:site:list (TerminusError) or an unknown --resume-from site
    name (ResumeSiteNotFoundError); both keep their exact messages (PD#2 -- both are already
    named exception classes).

    site_count is len(sites) BEFORE the --resume-from filter -- it is the denominator BOTH
    the resume banner below and finish_run's "Email sent for N of M sites" read, and MUST NOT
    become len(site_names) (SPEC development/2026-08-07-main-extraction/SPEC.md section 5.4,
    R5.4.3).  Nothing at the subprocess tier would go red if it did: --resume-from requires
    --all, and --all is in tests/conftest.py's FORBIDDEN_FLAGS, so this whole region is
    permanently unreachable there by design (SPEC section 1.2) --
    test_site_count_is_the_pre_filter_total_not_len_site_names is the instrument that closes
    that gap.

    Reads sc.options.resume_from at call time (the house rule); org_id is a parameter because
    the ResumeSiteNotFoundError message interpolates it and passing it keeps the helper's
    contract legible.  Extracted at development/2026-08-07-main-extraction/SPEC.md section 5.4.
    """
    try:
        sites = terminus_data("org:site:list", org_id)
    except TerminusError as e:
        sys.exit(f"Could not list organization sites: {e}")
    site_count = len(sites)
    name_to_id = {site["name"]: site_id for (site_id, site) in sites.items()}
    sc.debug(name_to_id)

    # Sites are processed in sorted order, so --resume-from can drop the prefix of sites that
    # an interrupted run already handled.  Filtering here (rather than `continue`ing inside the
    # loop) means a skipped-over site does no work at all: no banner, no plan:info, no context.
    site_names = sorted(name_to_id.keys())
    if sc.options.resume_from is not None:
        try:
            site_names = sites_from_resume_point(site_names, sc.options.resume_from)
        except ResumeSiteNotFoundError:
            sys.exit(
                f"--resume-from: site '{sc.options.resume_from}' was not found among the "
                f"{len(site_names)} sites for org {org_id}."
            )
        sc.console.print(
            f"[bold magenta]=== Resuming from [bold]{sc.options.resume_from}[/bold] "
            f"({len(site_names)} of {site_count} sites remaining)"
        )

    return SiteRoster(
        sites=sites, name_to_id=name_to_id, site_names=site_names, site_count=site_count
    )


def sort_notices_and_subject(site_context, report):
    """B50 sort/subject core + billing-key wiring (pure; rode to psh/cli.py with main() at I14a -- D-i13-1 discharged).

    Returns ``(sorted_notices, subject)``.  Reads the hook-produced billing key
    (`annual_bill_upcoming`, from check/umich/annual_billing) with ``.get()`` and inserts
    it into the render-only `sorted_notices` list -- it never enters
    ``site_context["notices"]``, so no -notices.csv rows (SPEC I12 §2.2).
    Preserved quirk: `annual_bill_upcoming` overrides the subject and is inserted at
    subject-computation time.
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

    return sorted_notices, subject


def main() -> None:  # noqa: C901, PLR0912, PLR0915 -- moved verbatim (CAMPAIGN.md section 3.1: moves get no algorithmic redesign); main() orchestrates the whole per-site pipeline in one straight-line body

    sc.debug(f"Loading configuration from {sc.options.config}")
    with Path(sc.options.config).open("rb") as f:
        sc.config = tomllib.load(f)

    # Drop the non-`enabled` settings of any disabled section BEFORE substitution resolution,
    # so a disabled feature's <{secret env ...}> values are never required to exist.
    sc.config = gate_disabled_sections(sc.config)

    sc.plugin = import_packages("plugin")

    sc.debug("Doing pre-setup configuration substitutions")
    sc.config = process_config(sc.config)

    sc.check = import_packages("check")

    # All modules are loaded; every hook is registered -- registration happens at package
    # import time (each __init__.py self-registers as import_packages() imports it), so
    # validate_hooks() below runs ONCE after both import loops.  Validate the consumes/produces
    # DAG before anything runs (CAMPAIGN.md section 4) -- a bad declaration is a startup fatal,
    # not a mid-run surprise; a hook somehow registered later (no in-repo case exists) would
    # bypass DAG conditions 1-4, with only add_hook's own declaration check firing.
    try:
        validate_hooks()
    except HookDagError as e:
        sc.console.print(f"[bold red]ERROR: hook validation failed: {escape(str(e))}")
        sys.exit(1)

    # Validate and process arguments.  The --resume-from guards come first: the create-tables and
    # sites-or-all checks in validate_options() would otherwise exit before they are reached,
    # shadowing these more precise messages.  --create-tables never runs the site loop, so a
    # --resume-from on it would be silently dropped; reject it instead.
    validate_options()

    if sc.options.verbose:
        sc.debug("Arguments:")
        pprint(sc.options)
        self_info, _errors, _fatal = terminus("self:info")
        pprint(self_info)

    # Create a directory named "build" if it doesn't exist.  exist_ok=True is the exists() guard
    # this replaced; unlike that guard, an existing NON-directory "build" now fails here rather
    # than at the first render write.
    Path("build").mkdir(exist_ok=True)

    # The run's accumulators live on ONE RunState, bound to sc.run_state BEFORE any hook fires:
    # a setup hook that reached db_retry would otherwise write into a RunState main() then
    # discards (SPEC 2.1).  db_retry() writes the reconnect counters through sc.run_state; the
    # site loop below fills the rest; finish_run/abort_run read it back as a parameter.
    sc.run_state = RunState()
    run_state = sc.run_state

    sc.invoke_hooks("setup")

    sc.debug("Doing post-setup configuration substitutions")
    sc.config = process_config(sc.config, deferred_pass=True)
    if sc.options.verbose:
        sc.debug("Configuration after substitutions:")
        pprint(sc.config)

    overage_block_size = sc.config["Pantheon"]["overage_block_size"]
    overage_block_cost = sc.config["Pantheon"]["overage_block_cost"]

    sc.debug(
        "[bold magenta]=== Connecting to the [green]pantheon-sitehealth-emails[/green] traffic database:"
    )

    db_engine, db_session = open_database(
        sc.config["Database"], echo=sc.options.verbose >= 2  # noqa: PLR2004 -- verbatim; 2 is the -vv level (echo SQL), not a constant worth naming
    )

    if sc.options.create_tables:
        Base.metadata.create_all(db_engine)
        sys.exit("Tables created.")

    wordmark_image = Path("header-image.png").read_bytes()

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

    sc.debug(
        "Cloudflare is "
        + ("[bold green]enabled" if cloudflare_enabled() else "[bold red]DISABLED")
    )
    smtp_enabled = bool(sc.config.get("SMTP", {}).get("enabled"))
    sc.debug(
        "SMTP sending is "
        + ("[bold green]enabled" if smtp_enabled else "[bold red]DISABLED")
    )

    roster = resolve_site_roster(sc.config["Pantheon"]["org_id"])
    sites = roster.sites
    site_name_to_id = roster.name_to_id
    site_names = roster.site_names
    site_count = roster.site_count  # len(sites) BEFORE the resume filter -- never len(site_names)

    site_name = None
    site_emailed = False
    current_site_number = 1
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

            plan_name = resolve_site_plan(site, plan_names)
            if plan_name is None:
                continue
            site_current_plan = plan_name

            # This site will be processed: build its context as far up as possible (past the
            # portal / not-requested / Sandbox skips above).  notices/sections/attachments
            # accumulate into it through the pipeline below.
            site_context = sc.SiteContext(site)

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

            # Not a pure fetch: also emits the `no-domains` alert into site_context.
            fetched = fetch_site_domains(site, live_site, site_context)
            if fetched is None:
                continue  # fatal/undecodable domain:list -- skip this site (D-i6-1)
            domains, facts = fetched

            # Per-phase data contract (see CLAUDE.md): publish the DnsFacts via the pure helper
            # (unit-tested against value-swaps in test_dns_classify.py), then fire the phase. The
            # check.dns hook consumes these keys to emit the DNS-resolution notices.
            dns_classify.stuff_dns_contract(site_context, domains, facts)
            sc.invoke_hooks("site_post_dns", site_context)

            # Not a pure derivation: also emits the `no-primary-domain` notice into
            # site_context.  MUST stay below the site_post_dns phase -- it reads the
            # drupal_multisite / drupal_multisite_smell keys check.drupal.multisite produces
            # there (pinned by tests/integration/test_regressions.py).
            url_facts = resolve_site_url(site, live_site, site_context, facts)
            site_url = url_facts.site_url
            # Smell merges stay in main() (D-i9-2/D-i10-2): a returned "" means "no NEW smell",
            # never "clear the previous one".  Source order matches the inline code these two
            # replace -- the multisite-probe drush_smell first, then the WP-network wp_smell.
            if url_facts.drush_smell != "":
                drush_smell = url_facts.drush_smell
            if url_facts.wp_smell != "":
                wp_smell = url_facts.wp_smell

            # Check the site's plugins/modules
            gather = gather_framework(site, live_site, site_context)
            wordpress_version = gather.wordpress_version
            plugins = gather.plugins
            drupal_version = gather.drupal_version
            mods = gather.modules
            add_on_updates = gather.add_on_updates
            # Smell merges stay in main() (D-i9-2/D-i10-2): a returned "" means "no NEW smell",
            # never "clear the previous one".
            if gather.wp_smell != "":
                wp_smell = gather.wp_smell
            if gather.drush_smell != "":
                drush_smell = gather.drush_smell
            if gather.composer_smell != "":
                composer_smell = gather.composer_smell
            run_state.site_results[site["name"]] = gather.results_entry

            # Per-phase data contract (see CLAUDE.md): WP/Drush gather results are guaranteed
            # present from site_post_gather onward.
            stuff_gather_contract(site_context, site["framework"], site_url,
                                  wordpress_version, plugins, drupal_version, mods,
                                  add_on_updates, wp_smell, drush_smell, composer_smell)
            sc.invoke_hooks("site_post_gather", site_context)

            # TODO: Warn if no Autopilot

            window = build_traffic_window(
                results, start_date, end_date, site_current_plan, site_name
            )
            # Unpacked into the pre-existing local names on purpose: the db_retry lambda below
            # carries six per-line B023 suppressions keyed to these exact names.  Named as
            # bare "B023" on purpose: ruff scans EVERY comment for a suppression directive,
            # so writing the full form here (even as prose, even in backticks) makes it warn
            # "Invalid ... directive" on every gate run and every edit-time hook run.
            visits_by_month = window.visits_by_month
            plan_on_day = window.plan_on_day
            plan_over_time = window.plan_over_time
            dates = window.dates
            estimate = window.estimate
            first_plan_day = window.first_plan_day
            last_plan_day = window.last_plan_day
            site_plan_start = window.site_plan_start
            plot_right_date = window.plot_right_date

            sc.debug("[bold magenta]=== Creating the traffic table:")

            # TODO: for upgrade/downgrade and new plan columns, add an icon and a colored background so people can
            #   see at a glance if it's more or less than 50% of the time.

            # TODO: If Performance small and below Basic upgrade + no New Relic + No Solr + No Redis + mem usage low --> Switch to Basic

            traffic_table_rows = db_retry(
                db_session,
                lambda: build_traffic_table_rows(
                    db_session,
                    site,  # noqa: B023 -- lambda is invoked synchronously by db_retry within this iteration; no deferred capture (verbatim body, no redesign)
                    visits_by_month,  # noqa: B023 -- see above
                    plan_on_day,  # noqa: B023 -- see above
                    plan_info,
                    site_plan_start,  # noqa: B023 -- see above
                    first_plan_day,  # noqa: B023 -- see above
                    last_plan_day,  # noqa: B023 -- see above
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
            # above).  check.umich.annual_billing's hook runs here, producing the billing
            # key the sort/subject helper wires in below; other future hooks may add notices.
            sc.invoke_hooks("site_pre_render", site_context)

            # Sort + subject AFTER the phase (campaign I12): hooks that add notices now
            # render, and the billing hook's produced key is wired in by the helper.
            report = f"Pantheon Traffic Report, {end_date.strftime('%b %e, %Y')}"
            sorted_notices, subject = sort_notices_and_subject(site_context, report)

            banner_cid = make_msgid(domain=sc.msgid_domain())
            chart_cid = make_msgid(domain=sc.msgid_domain())

            template_dict = dict(  # noqa: C408 -- verbatim; the kwargs dict() form is preserved from the pre-move main() (CAMPAIGN.md section 3.1: no redesign for moves); a {...} rewrite would churn 28 lines of a golden-pinned block for no behavior change
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

            # BEFORE the send -- see RunState.record_site_notices (Invariant 4).
            run_state.record_site_notices(site_context["notices"], contacts)

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

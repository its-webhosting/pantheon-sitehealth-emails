"""The Drupal 10 end-of-life notice (development/2026-10-30-d10-eol/SPEC.md).

Severity is judged by the REPORT date (site_context["end_date"], i.e. --date), never the wall
clock, so a re-run of an old month renders the same report (SPEC D2)."""

import datetime

import script_context as sc

# Notice code registered at import; see CLAUDE.md § Notices vs. news.
NOTICE_DRUPAL10_EOL = sc.registry.register(
    "drupal10-eol", description="Drupal 10 security support ends December 9, 2026")

# drupal.org core release schedule: "Drupal 10 will reach end of life on December 9, 2026."
DRUPAL10_EOL = datetime.date(2026, 12, 9)

EOL_URL = "https://pantheon.io/learning-center/drupal/10-end-of-life"
EOL_TITLE = "Drupal 10 End of Life Date, Risks and Next Steps"


def check_d10_eol(site_context):
    if not site_context["framework"].startswith("drupal"):
        return
    if not site_context["drupal_version"].startswith("10."):
        return
    before_eol = site_context["end_date"] < DRUPAL10_EOL
    # Tense follows severity: the first ALERT is mailed after December 9 has passed (SPEC D5).
    verb = "stops" if before_eol else "stopped"
    site_context.add_notice(
        sc.Notice(
            severity=sc.Severity.WARNING if before_eol else sc.Severity.ALERT,
            code=NOTICE_DRUPAL10_EOL,
            short="Upgrade to Drupal 11",
            html=f"""
<p><b>Drupal 10 {verb} getting security updates on December 9, 2026.</b>
All Drupal 10 sites should upgrade to Drupal 11. For details, see
Pantheon's <a href="{EOL_URL}">{EOL_TITLE}</a>.</p>
                """,
            text=f"""
Drupal 10 {verb} getting security updates on December 9, 2026.
All Drupal 10 sites should upgrade to Drupal 11. For details,
see Pantheon's {EOL_TITLE} ({EOL_URL}).
                """,
        )
    )

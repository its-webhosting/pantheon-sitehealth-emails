"""The three smell notices: non-fatal wp / drush / composer stderr, reported to the site owner
as "PHP code problems" (BLOCKMAP B48).

Moved verbatim from psh/gather.py:673-752 on 2026-08-07
(development/2026-08-07-smell-notice-relocation/SPEC.md section 5.2), where it had lived since
campaign I10 as a builder whose emission stayed in main().

Campaign Invariant 8: the interiors of the six f-string literals below are string content that
reaches the rendered email.  The composer html/text pair sits at COLUMN 0 (D-i10-8), matching
its wp/drush siblings, and tests/unit/test_smell_notices.py::
test_composer_literals_are_column_zero_like_siblings is what goes red if that changes --
`git diff -w` cannot see it.

Five sanctioned substitutions were applied to the moved block and no others: the psh.notice
import became `import script_context as sc`, and `registry.` / `Notice(` / `Severity.` /
`list[Notice]` became their `sc.`-prefixed forms -- the checks-import-only-sc convention
(Invariant 9) and the check/-registers-through-the-facade rule (CLAUDE.md, Notices vs. news).
"""
import html
import json

import script_context as sc

# Notice codes registered at import; see CLAUDE.md section "Notices vs. news".
NOTICE_WP_SMELL = sc.registry.register("wp-smell", description="wp-cli wrote to stderr")
NOTICE_DRUSH_SMELL = sc.registry.register("drush-smell", description="drush wrote to stderr")
NOTICE_COMPOSER_SMELL = sc.registry.register(
    "composer-smell", description="composer wrote to stderr")


def build_smell_notices(site_name, wp_smell, drush_smell, composer_smell) -> list[sc.Notice]:
    """Return the list of smell Notices (possibly empty) for one site (BLOCKMAP B48).

    Pure: the emission is check/smells/hook.py's, at site_pre_render."""
    notices = []
    if wp_smell != "":
        notices.append(
            sc.Notice(
                severity=sc.Severity.INFO,
                code=NOTICE_WP_SMELL,
                csv_extra=(json.dumps(wp_smell).replace(',', '\\,'),),
                short="PHP code problems",
                html=f"""
<p>The <code>wp</code> (WP CLI) command is reporting PHP code problems with <strong>{site_name}</strong>.
Even if this is not breaking anything at the moment, it should be fixed to avoid possible future problems:</p>
<pre>{html.escape(wp_smell)}</pre>
""",
                text=f"""
The "wp" (WP CLI) command is reporting PHP code problems with
{site_name}. Even if this is not breaking anything at
the moment, it should be fixed to avoid possible future problems:

----- START WP CLI REPORTED PROBLEMS -----
{wp_smell}
----- END OF WP CLI REPORTED PROBLEMS -----

    """,
            )
        )

    if drush_smell != "":
        notices.append(
            sc.Notice(
                severity=sc.Severity.INFO,
                code=NOTICE_DRUSH_SMELL,
                csv_extra=(json.dumps(drush_smell).replace(',', '\\,'),),
                short="PHP code problems",
                html=f"""
<p>The <code>drush</code> command is reporting PHP code problems with <strong>{site_name}</strong>. Even
if this is not breaking anything at the moment, it should be fixed to avoid possible future problems:</p>
<pre>{html.escape(drush_smell)}</pre>
""",
                text=f"""
The "drush" command is reporting PHP code problems with
{site_name}. Even if this is not breaking anything
at the moment, it should be fixed to avoid possible future problems:

----- START DRUSH REPORTED PROBLEMS -----
{drush_smell}
----- END OF DRUSH REPORTED PROBLEMS -----

""",
            )
        )

    if composer_smell != "":
        notices.append(
            sc.Notice(
                severity=sc.Severity.INFO,
                code=NOTICE_COMPOSER_SMELL,
                csv_extra=(json.dumps(composer_smell).replace(',', '\\,'),),
                short="PHP code problems",
                html=f"""
<p>The <code>composer</code> command is reporting PHP code problems with <strong>{site_name}</strong>. Even
if this is not breaking anything at the moment, it should be fixed to avoid possible future problems:</p>
<pre>{html.escape(composer_smell)}</pre>
""",
                text=f"""
The "composer" command is reporting PHP code problems with
{site_name}. Even if this is not breaking anything
at the moment, it should be fixed to avoid possible future problems:

----- START COMPOSER REPORTED PROBLEMS -----
{composer_smell}
----- END OF COMPOSER REPORTED PROBLEMS -----

""",
            )
        )
    return notices

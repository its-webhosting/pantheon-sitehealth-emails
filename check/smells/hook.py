"""Emit the three smell notices at site_pre_render (BLOCKMAP B48's emission).

Reads the three smell keys off the SiteContext LIVE and never caches them: wp_smell and
drush_smell are the two sanctioned mutate-during-phase contract keys (CLAUDE.md's
site_post_gather row), rebound IN PLACE during that phase by check.wordpress.ocp /
check.wordpress.favicon and check.umich.drupal_ua.  This is a straight transcription of the
call this replaced (psh/cli.py:975-979 before 2026-08-07), which already read site_context
rather than main()'s locals.  Pinned by tests/integration/test_check_smells.py::
test_reads_the_rebound_wp_smell_not_the_stuffed_one.
"""

from . import notices


def emit_smell_notices(site_context):
    site_context.add_notices(
        notices.build_smell_notices(
            site_context["site"]["name"],
            site_context["wp_smell"],
            site_context["drush_smell"],
            site_context["composer_smell"],
        )
    )

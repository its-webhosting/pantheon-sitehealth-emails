"""check.smells.hook seam (SPEC section 6.3): the BLOCKMAP B48 emission as a site_pre_render
hook.

It reads the three smell keys off the SiteContext LIVE.  wp_smell and drush_smell are the two
sanctioned mutate-during-phase contract keys (CLAUDE.md's site_post_gather row): check.wordpress
.ocp / .favicon and check.umich.drupal_ua rebind them IN PLACE during that phase, so a hook that
captured them into locals -- or a caller that passed main()'s stale local -- would emit the
pre-mutation value.  test_reads_the_rebound_wp_smell_not_the_stuffed_one is the only test that
pins that."""
import pytest
from helpers.checkload import load_check_module

pytestmark = pytest.mark.integration

SITE_NAME = "its-wws-test1"
SITE_ID = "9cf2c790-c7b8-4f2f-a6f1-27385b8f958e"


@pytest.fixture
def hook_mod(psh, request):
    return load_check_module(psh, "smells", "hook", "smells_hook_probe", request)


def _ctx(reset_sc, wp="", drush="", composer=""):
    ctx = reset_sc.SiteContext({"name": SITE_NAME, "id": SITE_ID})
    ctx["wp_smell"] = wp
    ctx["drush_smell"] = drush
    ctx["composer_smell"] = composer
    return ctx


def _codes(ctx):
    # the render dict's csv row is "site,code,*csv_extra" (SiteContext.notice_to_dict); the site
    # name contains no comma, so field 1 is the code.
    return [n["csv"].split(",")[1] for n in ctx["notices"]]


def test_all_three_smells_become_three_notices_in_builder_order(hook_mod, reset_sc):
    ctx = _ctx(reset_sc, wp="wp broke", drush="drush broke", composer="composer broke")
    hook_mod.emit_smell_notices(ctx)
    assert _codes(ctx) == ["wp-smell", "drush-smell", "composer-smell"]


def test_no_smells_adds_no_notices(hook_mod, reset_sc):
    # PD#3's empty-input shadow path: all three keys are "" on a clean site, which is the
    # overwhelmingly common case -- a report must not gain an empty "PHP code problems" notice.
    ctx = _ctx(reset_sc)
    hook_mod.emit_smell_notices(ctx)
    assert ctx["notices"] == []


def test_the_site_name_comes_from_the_site_context(hook_mod, reset_sc):
    ctx = _ctx(reset_sc, wp="wp broke")
    hook_mod.emit_smell_notices(ctx)
    (n,) = ctx["notices"]
    assert n["csv"].startswith(f"{SITE_NAME},wp-smell,")
    assert SITE_NAME in n["message"]


def test_reads_the_rebound_wp_smell_not_the_stuffed_one(hook_mod, reset_sc):
    # Simulates check.wordpress.ocp: core stuffs wp_smell="" at site_post_gather, then the ocp
    # probe rebinds it IN PLACE during the phase.  This hook runs at site_pre_render, after that
    # phase, and MUST report the rebound value.
    ctx = _ctx(reset_sc, wp="")
    ctx["wp_smell"] = "PHP Deprecated: strlen(): Passing null is deprecated"
    hook_mod.emit_smell_notices(ctx)
    (n,) = ctx["notices"]
    assert "PHP Deprecated" in n["message"]
    assert _codes(ctx) == ["wp-smell"]

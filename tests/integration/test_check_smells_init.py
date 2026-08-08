"""check/smells registration + [Check.smells] gating
(development/2026-08-07-smell-notice-relocation/SPEC.md section 6.2).

Default is ENABLED: relocating code must not silently disable notices that rendered
unconditionally before -- the D-i8-6/D-i9-5/D-i10-5 shape."""
import pytest
from helpers.checkload import load_check_package
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration

EXPECTED_NAMES = ["check.smells.hook.emit_smell_notices"]
SITE_NAME = "its-wws-test1"
SITE_ID = "9cf2c790-c7b8-4f2f-a6f1-27385b8f958e"


def test_registers_hook_when_config_is_silent(psh, reset_sc, request):
    reset_sc.config = {}
    load_check_package(psh, "smells", "smells_init_probe", request)
    assert [h["name"] for h in reset_sc.hooks["site_pre_render"]] == EXPECTED_NAMES


def test_registers_hook_when_explicitly_enabled(psh, reset_sc, request):
    reset_sc.config = {"Check": {"smells": {"enabled": True}}}
    load_check_package(psh, "smells", "smells_on_probe", request)
    assert [h["name"] for h in reset_sc.hooks["site_pre_render"]] == EXPECTED_NAMES


def test_disabled_registers_nothing_and_says_so(psh, reset_sc, request, monkeypatch):
    console = recording_console(monkeypatch, reset_sc)
    reset_sc.config = {"Check": {"smells": {"enabled": False}}}
    load_check_package(psh, "smells", "smells_off_probe", request)
    assert not reset_sc.hooks.get("site_pre_render")
    assert "Skipping check.smells" in console.export_text()


def test_no_smell_notice_exists_until_the_site_pre_render_phase(psh, reset_sc, request):
    """The --only-warn output surface, pinned as BEHAVIOR rather than as a phase-name string.

    An --only-warn run reaches every phase up to and including site_post_gather and then
    `continue`s (psh/cli.py:964), so site_pre_render is the first phase it never fires.  The
    invariant that gives the relocation its behavior-neutrality is therefore exactly this: NO
    smell notice may exist before that horizon.  Register this hook one phase earlier and every
    --only-warn run silently starts writing smell rows into -notices.csv (PD#1, SPEC section
    3.2 obstacle 3).

    This drives the phases through sc.invoke_hooks instead of asserting on the registered phase
    string, because a string assertion pins the spelling and not the consequence: it goes red on
    a phase move, but it would also stay green if the hook were somehow reached early by another
    route, and it says nothing about what the move would COST.  Only check.smells is loaded here,
    so the pre-horizon loop fires an empty hook list for every other phase -- which is the point:
    the assertion fails for a move to ANY earlier phase, not only to site_post_gather.

    test_hook_dag.py stays GREEN under such a move (the declarations are legal at
    site_post_gather too, so the DAG cannot detect it), and so do the three gating tests above
    if they are ever loosened.  Nothing else in the suite reaches this."""
    reset_sc.config = {}
    load_check_package(psh, "smells", "smells_phase_probe", request)

    site_context = reset_sc.SiteContext({"name": SITE_NAME, "id": SITE_ID})
    site_context["wp_smell"] = "PHP Deprecated: strlen(): Passing null is deprecated"
    site_context["drush_smell"] = ""
    site_context["composer_smell"] = ""

    for phase in reset_sc.PHASES[:reset_sc.PHASES.index("site_pre_render")]:
        reset_sc.invoke_hooks(phase, site_context)
    assert site_context["notices"] == [], (
        "a smell notice exists before site_pre_render, so an --only-warn run -- which continues "
        "after site_post_gather -- would now write smell rows into -notices.csv")

    reset_sc.invoke_hooks("site_pre_render", site_context)
    assert [n["csv"].split(",")[1] for n in site_context["notices"]] == ["wp-smell"], (
        "the hook did not emit at site_pre_render, the one phase --only-warn never reaches")


def test_declarations_match_the_spec_table(psh, reset_sc, request):
    """The DAG declarations (SPEC section 6.2).  `consumes` is what orders this hook after the
    core stuffer; `produces` MUST stay empty -- claiming any of the three smell keys would be a
    duplicate-producer fatal against the core CONTRACT registry (D-i9-3), which is the obstacle
    that kept this emission in main() for the whole campaign."""
    reset_sc.config = {}
    load_check_package(psh, "smells", "smells_decl_probe", request)

    registered = reset_sc.hooks.get("site_pre_render", [])
    assert len(registered) == 1, "expected exactly one site_pre_render hook from check.smells"
    (hook,) = registered
    assert hook["name"] == EXPECTED_NAMES[0]
    assert hook["consumes"] == ["wp_smell", "drush_smell", "composer_smell"]
    assert hook["produces"] == []

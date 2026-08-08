"""check/smells registration + [Check.smells] gating
(development/2026-08-07-smell-notice-relocation/SPEC.md section 6.2).

Default is ENABLED: relocating code must not silently disable notices that rendered
unconditionally before -- the D-i8-6/D-i9-5/D-i10-5 shape."""
import pytest
from helpers.checkload import load_check_package
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration

EXPECTED_NAMES = ["check.smells.hook.emit_smell_notices"]


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


def test_the_phase_is_site_pre_render_and_that_is_load_bearing(psh, reset_sc, request):
    """The phase string carries THREE guarantees at once (SPEC section 3.2), which is why it
    gets its own assertion rather than riding along in the gating tests above:

      1. Ordering.  The in-place wp_smell/drush_smell mutators (check.wordpress.ocp,
         check.wordpress.favicon, check.umich.drupal_ua) are all site_post_gather hooks and are
         deliberately DAG-invisible (D-i9-3).  A later phase is unconditionally after them; a
         same-phase hook would need a `mutates` edge kind that this repo deliberately does not
         have (SPEC section 3.3).
      2. The --only-warn gate.  main() `continue`s at psh/cli.py:964, ABOVE the site_pre_render
         firing at :1003.  Move this hook to site_post_gather and every --only-warn run starts
         writing smell rows into -notices.csv -- a silent output-surface change (PD#1).
      3. Notice order.  Nothing between the old emission point and the phase firing appends to
         site_context["notices"], so the info bucket is byte-identical to the pre-move report.

    test_hook_dag.py stays GREEN if this hook moves to site_post_gather -- the declarations are
    legal there too.  This assertion is the only thing that goes red."""
    reset_sc.config = {}
    load_check_package(psh, "smells", "smells_decl_probe", request)

    assert [h["name"] for h in reset_sc.hooks["site_pre_render"]] == EXPECTED_NAMES
    for phase in reset_sc.PHASES:
        if phase == "site_pre_render":
            continue
        assert all(h["name"] not in EXPECTED_NAMES for h in reset_sc.hooks.get(phase, [])), (
            f"the smells hook must be registered ONLY at site_pre_render, not {phase}")

    (hook,) = reset_sc.hooks["site_pre_render"]
    assert hook["consumes"] == ["wp_smell", "drush_smell", "composer_smell"]
    assert hook["produces"] == []

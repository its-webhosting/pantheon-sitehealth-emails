"""Regression tests for the bugs fixed alongside this harness (SPEC §3.1, §9).

Each would fail on the pre-fix code:
  * terminus() session-expiry retry did args.push()/del args[...] on a tuple -> crash.
  * check/umich/__init__.py disabled branch called sc.console(...) as if callable -> TypeError.

The two non-UMich render-path bugs discovered during implementation (the `contacts`
UnboundLocalError and the unconditional `if True:` UMich annual-billing block) are
regressed by the offline e2e in tests/e2e/ — it renders under the plugin-disabled config,
which crashed on the pre-fix code.
"""
import importlib.util
import inspect
import re
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_terminus_retries_on_expired_session(psh, gateway, monkeypatch):
    calls = {"n": 0}

    def fake_run_terminus(command, input_data=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return ("", "Invalid or expired session header: X-Pantheon-Session", False)
        return ('{"ok": 1}', "", False)

    monkeypatch.setattr(gateway, "run_terminus", fake_run_terminus)
    monkeypatch.setattr(psh.time, "sleep", lambda *_a, **_k: None)

    result, errors, fatal = psh.terminus("org:site:list", "some-org")
    assert result == {"ok": 1}
    assert errors == ""
    assert fatal is False
    assert calls["n"] == 2  # original + one retry (pre-fix this path raised on the tuple)


def test_terminus_retry_does_not_loop_forever(psh, gateway, monkeypatch):
    calls = {"n": 0}

    def always_expired(command, input_data=None):
        calls["n"] += 1
        return ("", "Invalid or expired session header: X-Pantheon-Session", False)

    monkeypatch.setattr(gateway, "run_terminus", always_expired)
    monkeypatch.setattr(psh.time, "sleep", lambda *_a, **_k: None)

    psh.terminus("org:site:list", "some-org")
    assert calls["n"] == 2  # one retry only; the sentinel disables a second retry


def test_check_umich_disabled_import_does_not_crash(psh, reset_sc):
    sc = reset_sc
    sc.config = {}  # UMich absent -> the module's else branch runs sc.console.print(...)
    init = Path(psh.__file__).resolve().parents[1] / "check" / "umich" / "__init__.py"
    loader = SourceFileLoader("check_umich_probe", str(init))
    spec = importlib.util.spec_from_loader("check_umich_probe", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)  # pre-fix: TypeError from sc.console('...'); post-fix: fine
    # The disabled (else) branch ran — it only prints — so no site_pre hooks were registered
    # (the enabled branch would have added three). This confirms the fixed path executed.
    assert sc.hooks["site_pre"] == []


def test_site_notices_are_recorded_before_the_email_is_sent(psh):
    # A Ctrl-C between send_message() and the notices append -- a window that includes
    # smtp_connection.quit(), a NETWORK ROUND-TRIP -- landed with site_emailed already True, so
    # abort_run() kept the site's results entry and advanced the resume point to the NEXT site.
    # The resumed run never revisited it, and that site's notices never reached {ymd}-notices.csv
    # on ANY run -- even though its owner had already received the email describing them.
    # Permanent, silent loss.  Recording the notices FIRST downgrades it to at worst a duplicate
    # CSV row on a re-run, which docs/resuming-interrupted-runs.md documents as tolerable.
    #
    # The interrupt itself is not reachable from the harness (the subprocess interlock bans --all,
    # and the window is a single unsynchronizable instant), so the ORDER is what is pinned.
    source = inspect.getsource(psh.main)
    # Since I13 the pre-send append is a single RunState.record_site_notices() call (the loop body
    # itself moved into psh/lifecycle.py, covered by tests/unit/test_run_state.py). That call is
    # unique in main(): the --only-warn early-continue branch (well before the send, and unrelated
    # to this bug) appends via run_state.all_warnings.append, a different-shaped row, so it does not
    # match this anchor. Assert exactly one so source.index() below cannot latch onto the wrong one.
    append_anchor = "run_state.record_site_notices("
    assert source.count(append_anchor) == 1, (
        "expected exactly one notices-record-before-send call; "
        "a duplicate would defeat the record < send check below"
    )
    append = source.index(append_anchor)
    # Anchored on the call itself, not a two-line literal that embeds exact indentation: extracting
    # the send into a helper keeps "smtp_login()" in the source but breaks a literal match on the
    # surrounding "if smtp_enabled:\n                smtp_connection = ..." lines, and source.index()
    # raising ValueError on that miss reads like a harness bug, not a signal that the send moved.
    send = source.index("smtp_login()")
    assert append < send, "the notices append must precede the SMTP send"


# ── The composition glue main() kept after the 2026-08-07 main-extraction increment ──────
#
# The six extracted helpers each carry their own tests.  What no test reached was the WIRING
# main() kept between them, and two of the increment's own global invariants (SPEC
# development/2026-08-07-main-extraction/SPEC.md R-G5 and resolve_site_url's docstring) live
# only there.  Both were measured green under violation on the shipped branch: collapsing the
# smell merges to unconditional assignment, and hoisting resolve_site_url above the
# site_post_dns phase, each left all 1818 tests passing.
#
# Same idiom and same justification as test_site_notices_are_recorded_before_the_email_is_sent
# above: main() has no in-process caller (the subprocess interlock bans --all/--for-real, and
# no golden site is a Drupal multisite or a wordpress_network), so the ORDER and the SHAPE of
# the glue are what get pinned.  These are source assertions on purpose; PD#14 -- they were
# each shown red by re-running the two injections before being committed.


def test_resolve_site_url_runs_after_the_site_post_dns_phase(psh):
    # resolve_site_url reads site_context["drupal_multisite_smell"] and ["drupal_multisite"],
    # which check/drupal/multisite.py PRODUCES in the site_post_dns phase.  Called before the
    # phase fires, both .get() reads return their defaults: the multisite probe's drush_smell
    # is lost (nobody learns the site emits PHP notices) AND no_primary_domain_notice's
    # multisite suppression stops working, so a multisite with several custom domains and no
    # primary is told to set one -- exactly what check/drupal/multisite.py exists to prevent.
    #
    # Before the extraction this was structural: 25 lines physically below the phase firing.
    # It is now a single call, so the constraint is a one-line move away from being violated.
    source = inspect.getsource(psh.main)
    phase = 'sc.invoke_hooks("site_post_dns"'
    call = "resolve_site_url("
    assert source.count(phase) == 1, "expected exactly one site_post_dns phase firing in main()"
    assert source.count(call) == 1, "expected exactly one resolve_site_url() call in main()"
    assert source.index(phase) < source.index(call), (
        "resolve_site_url() must run AFTER sc.invoke_hooks('site_post_dns') -- it reads the "
        "hook-produced drupal_multisite_smell / drupal_multisite keys that phase publishes"
    )


def test_the_notices_dump_runs_after_the_site_pre_render_phase(psh):
    # The -v "===== Notices:" dump must run after the LAST seam that can add a notice, or it
    # under-reports what the report will contain.  It DID: relocating the smell notices to
    # check/smells/ (a site_pre_render hook, 2026-08-07) moved their emission BELOW a dump that
    # still sat above the phase, so every -v/-vv/-vvv run silently stopped listing them --
    # sc.debug defaults to level=1, so this was not a -vvv-only detail.
    #
    # Invisible to every tier: the four goldens assert on the .eml, never on stdout, and no test
    # at any tier reads the dump's content.  PD#1 -- a failure that can happen silently.  Same
    # idiom and justification as the two source assertions above; the dump is one line away from
    # being hoisted back above the phase by anyone tidying this region.
    source = inspect.getsource(psh.main)
    phase = 'sc.invoke_hooks("site_pre_render"'
    dump = 'sc.debug("===== Notices:'
    assert source.count(phase) == 1, "expected exactly one site_pre_render phase firing in main()"
    assert source.count(dump) == 1, "expected exactly one ===== Notices: dump in main()"
    assert source.index(phase) < source.index(dump), (
        "the ===== Notices: dump must run AFTER sc.invoke_hooks('site_pre_render') -- hooks in "
        "that phase add notices (check.smells does), and a dump above it under-reports them"
    )


@pytest.mark.parametrize(
    ("owner", "smell"),
    [
        ("url_facts", "wp_smell"),
        ("url_facts", "drush_smell"),
        ("gather", "wp_smell"),
        ("gather", "drush_smell"),
        ("gather", "composer_smell"),
    ],
)
def test_each_smell_merge_stays_guarded(psh, owner, smell):
    # SPEC R-G5 / psh/gather.py's module docstring: a returned smell is a DELTA -- "" means
    # "no NEW smell", NEVER "clear the previous one".  Collapsing any of these five to an
    # unconditional `x = <owner>.x` clears a smell an earlier stage recorded.  Concretely: a
    # Drupal multisite whose drush php probe emits a PHP deprecation on stderr (drush_smell
    # set by resolve_site_url) and whose pm:list/composer calls are clean (gather.drush_smell
    # == "") loses the smell, stuff_gather_contract publishes drush_smell="",
    # the check.smells hook emits nothing, and nobody learns the site emits PHP notices.
    # Invisible to all four goldens (PD#1 -- a failure that can happen silently).
    source = inspect.getsource(psh.main)
    guard = f'if {owner}.{smell} != "":'
    assignment = f"{smell} = {owner}.{smell}"
    assert source.count(guard) == 1, f"expected exactly one `{guard}` merge guard in main()"
    assert source.count(assignment) == 1, (
        f"expected exactly one `{assignment}`; a second one outside the guard would defeat "
        f"the delta rule even with the guard still present"
    )
    assert re.search(re.escape(guard) + r"\n\s+" + re.escape(assignment), source), (
        f"`{assignment}` must sit directly inside `{guard}` -- an unconditional assignment "
        f"turns the delta into a clear-the-previous-smell overwrite (SPEC R-G5)"
    )

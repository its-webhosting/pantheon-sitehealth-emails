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
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_terminus_retries_on_expired_session(psh, monkeypatch):
    calls = {"n": 0}

    def fake_run_terminus(command, input_data=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return ("", "Invalid or expired session header: X-Pantheon-Session", False)
        return ('{"ok": 1}', "", False)

    monkeypatch.setattr(psh, "run_terminus", fake_run_terminus)
    monkeypatch.setattr(psh.time, "sleep", lambda *_a, **_k: None)

    result, errors, fatal = psh.terminus("org:site:list", "some-org")
    assert result == {"ok": 1}
    assert errors == ""
    assert fatal is False
    assert calls["n"] == 2  # original + one retry (pre-fix this path raised on the tuple)


def test_terminus_retry_does_not_loop_forever(psh, monkeypatch):
    calls = {"n": 0}

    def always_expired(command, input_data=None):
        calls["n"] += 1
        return ("", "Invalid or expired session header: X-Pantheon-Session", False)

    monkeypatch.setattr(psh, "run_terminus", always_expired)
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
    # The bare 'for n in site_context["notices"]:' substring is NOT unique: the --only-warn
    # early-continue branch (well before the send, and unrelated to this bug) has its own copy,
    # so source.index() on it alone can silently latch onto the wrong occurrence and
    # source.count() on it is 2 today, not 1. Anchor on the next line too, which only appears at
    # the real pre-send append site.
    append_anchor = 'for n in site_context["notices"]:\n                fields = n["csv"].split(",")'
    assert source.count(append_anchor) == 1, (
        "expected exactly one notices-append-before-send block; "
        "a duplicate would defeat the append < send check below"
    )
    append = source.index(append_anchor)
    # Anchored on the call itself, not a two-line literal that embeds exact indentation: extracting
    # the send into a helper keeps "smtp_login()" in the source but breaks a literal match on the
    # surrounding "if smtp_enabled:\n                smtp_connection = ..." lines, and source.index()
    # raising ValueError on that miss reads like a harness bug, not a signal that the send moved.
    send = source.index("smtp_login()")
    assert append < send, "the notices append must precede the SMTP send"

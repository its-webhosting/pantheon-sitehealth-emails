"""Integration tier: the terminus() (result, errors, fatal) contract + TerminusError (P3).

Before P3, terminus() returned only the parsed result and set it to "" on a JSON-decode
failure, swallowing the stderr; a caller indexing into it then raised TypeError far from the
real cause.  Now terminus() returns a 3-tuple, terminus_data() raises a named TerminusError
at call sites that need the data, and get_old_metrics() (a real call site) surfaces that
error instead of TypeError.
"""
import datetime

import pytest

pytestmark = pytest.mark.integration


def _run(output, errors="", fatal=False):
    return lambda *a, **k: (output, errors, fatal)


def test_wellformed_returns_result_empty_errors_not_fatal(psh, monkeypatch):
    monkeypatch.setattr(psh, "run_terminus", _run('{"sku": "plan-basic"}'))
    result, errors, fatal = psh.terminus("plan:info", "its-wws-test1")
    assert result == {"sku": "plan-basic"}
    assert errors == ""
    assert fatal is False


def test_decode_failure_returns_none_and_keeps_errors(psh, monkeypatch):
    monkeypatch.setattr(psh, "run_terminus", _run("not json", errors="boom"))
    result, errors, fatal = psh.terminus("plan:info", "x")
    assert result is None          # was "" pre-fix (silently swallowed)
    assert "boom" in errors        # original stderr preserved
    assert "not json" in errors    # plus the undecodable output for context
    assert fatal is False


def test_fatal_flag_propagates(psh, monkeypatch):
    monkeypatch.setattr(psh, "run_terminus", _run('{"ok": 1}', fatal=True))
    result, errors, fatal = psh.terminus("env:metrics", "x")
    assert fatal is True


def test_terminus_data_returns_result_on_success(psh, monkeypatch):
    monkeypatch.setattr(psh, "run_terminus", _run('{"ok": 1}'))
    assert psh.terminus_data("site:info", "x") == {"ok": 1}


def test_terminus_data_raises_on_decode_failure(psh, monkeypatch):
    monkeypatch.setattr(psh, "run_terminus", _run("garbage", errors="bad"))
    with pytest.raises(psh.TerminusError) as exc:
        psh.terminus_data("plan:info", "x")
    assert "plan:info" in str(exc.value)  # names the command
    assert "bad" in exc.value.errors


def test_terminus_data_raises_on_fatal(psh, monkeypatch):
    monkeypatch.setattr(psh, "run_terminus", _run('{"ok": 1}', errors="timeout", fatal=True))
    with pytest.raises(psh.TerminusError):
        psh.terminus_data("env:metrics", "x")


def test_get_old_metrics_returns_empty_on_failure_not_type_error(psh, reset_sc, monkeypatch):
    # get_old_metrics() indexes metrics["timeseries"]; pre-fix a decode failure made metrics
    # "" and this raised TypeError far from the cause.  Now terminus_data() raises
    # TerminusError, which get_old_metrics catches and returns [] (older-metrics import is
    # best-effort) -- no TypeError, and one bad site does not abort the whole run.
    monkeypatch.setattr(psh, "run_terminus", _run("not json", errors="decode boom"))
    result = psh.get_old_metrics("its-wws-test1.live", {"name": "its-wws-test1"},
                                 "month", datetime.date(2026, 3, 31))
    assert result == []


def test_session_expiry_retries_once_then_returns(psh, monkeypatch):
    calls = {"n": 0}

    def flaky(command, input_data=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return ("", "Invalid or expired session header: X-Pantheon-Session", False)
        return ('{"ok": 1}', "", False)

    monkeypatch.setattr(psh, "run_terminus", flaky)
    monkeypatch.setattr(psh.time, "sleep", lambda *_a, **_k: None)
    result, errors, fatal = psh.terminus("org:site:list", "org")
    assert result == {"ok": 1}
    assert calls["n"] == 2


def test_check_helpers_are_exposed_on_sc(psh, reset_sc):
    # Check packages cannot import the dash-named script; these are the documented seam
    # (CLAUDE.md).  check/pantheon_cdn_change calls sc.terminus("domain:dns", ...) and validates
    # domain ids with sc.fqdn_re before they reach -notices.csv (which has no escaping).
    assert reset_sc.terminus is psh.terminus
    assert reset_sc.fqdn_re is psh.fqdn_re
    assert reset_sc.fqdn_re.match("occb.bus.umich.edu")
    assert not reset_sc.fqdn_re.match("has,comma.example.org")

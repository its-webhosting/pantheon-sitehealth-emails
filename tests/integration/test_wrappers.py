"""Integration tests for the WP/Drush wrappers around the single run_terminus seam
(test-suite SPEC §7.3).  run_terminus is monkeypatched so nothing shells out.

These pin the ACTUAL 3-tuple return contract (result, errors, fatal) — the docstrings still
declare 2-tuples (PROBLEMS-DISCOVERED.md P6); the tests document the truth.
"""
import pytest

pytestmark = pytest.mark.integration


def _fake(output, errors="", fatal=False, record=None):
    def run_terminus(command, input_data=None):
        if record is not None:
            record["command"] = command
            record["input"] = input_data
        return (output, errors, fatal)

    return run_terminus


def test_wp_parses_json_three_tuple(psh, monkeypatch):
    monkeypatch.setattr(psh, "run_terminus", _fake('{"active": true}'))
    result, errors, fatal = psh.wp("its-wws-test1.live", "plugin", "list")
    assert result == {"active": True}
    assert errors == ""
    assert fatal is False


def test_wp_bad_json_returns_none_and_keeps_errors(psh, monkeypatch):
    monkeypatch.setattr(psh, "run_terminus", _fake("this is not json"))
    result, errors, fatal = psh.wp("its-wws-test1.live", "plugin", "list")
    assert result is None
    assert "this is not json" in errors


def test_wp_eval_strips_and_three_tuple(psh, monkeypatch):
    monkeypatch.setattr(psh, "run_terminus", _fake("6.4.2\n", errors="  warn \n"))
    output, errors, fatal = psh.wp_eval("its-wws-test1.live", "echo $wp_version;")
    assert output == "6.4.2"
    assert errors == "warn"
    assert fatal is False


def test_drush_parses_json_three_tuple(psh, monkeypatch):
    monkeypatch.setattr(psh, "run_terminus", _fake('{"drupal": 10}'))
    result, errors, fatal = psh.drush("its-wws-test2.live", "core:status")
    assert result == {"drupal": 10}
    assert fatal is False


def test_drush_moves_leading_noise_to_errors(psh, monkeypatch):
    # Drush sometimes prints warnings before the JSON body; fix_drush_output relocates them.
    monkeypatch.setattr(psh, "run_terminus", _fake('[warning] deprecated\n{"drupal": 10}'))
    result, errors, fatal = psh.drush("its-wws-test2.live", "core:status")
    assert result == {"drupal": 10}
    assert "[warning] deprecated" in errors


def test_drush_php_script_passes_script_as_input(psh, monkeypatch):
    record = {}
    monkeypatch.setattr(psh, "run_terminus", _fake('{"ok": 1}', record=record))
    result, _errors, _fatal = psh.drush_php_script("its-wws-test2.live", "return ['ok'=>1];")
    assert result == {"ok": 1}
    assert record["input"] == "return ['ok'=>1];"  # script piped as stdin, not argv


# ── fix_drush_output (pure) ──────────────────────────────────────────────────────────
def test_fix_drush_output_relocates_leading_lines(psh):
    output, errors = psh.fix_drush_output("noise line\nmore noise\n{\"a\": 1}", "")
    assert output.startswith("{")
    assert "noise line" in errors and "more noise" in errors


def test_fix_drush_output_leaves_clean_json(psh):
    assert psh.fix_drush_output('{"a": 1}', "") == ('{"a": 1}', "")


def test_fix_drush_output_empty(psh):
    assert psh.fix_drush_output("", "err") == ("", "err")


# ── error-notice builders ────────────────────────────────────────────────────────────
def test_wp_error_shape(psh):
    notices = psh.wp_error("its-wws-test1", "PLUGIN_FAIL", "Site its-wws-test1 broke.", "boom")
    assert isinstance(notices, list) and len(notices) == 1
    n = notices[0]
    assert n["type"] == "alert"
    assert set(("type", "icon", "csv", "short", "message", "text")) <= set(n)
    assert "<strong>its-wws-test1</strong>" in n["message"]
    assert n["csv"].startswith("its-wws-test1,wp-error,PLUGIN_FAIL,")
    assert "boom" in n["text"]


def test_drush_error_shape(psh):
    notices = psh.drush_error("its-wws-test2", "DRUSH_FAIL", "Site its-wws-test2 broke.", "kaboom")
    assert len(notices) == 1
    n = notices[0]
    assert n["type"] == "alert"
    assert n["csv"].startswith("its-wws-test2,drush-error,DRUSH_FAIL,")
    assert "<strong>its-wws-test2</strong>" in n["message"]

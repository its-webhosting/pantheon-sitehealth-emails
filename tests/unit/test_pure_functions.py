"""Unit tier: directly-callable helpers, no I/O (SPEC §9, `unit`).

These need sc.options populated (they call sc.debug -> sc.options.verbose); the autouse
reset_sc fixture provides a default namespace.
"""
import pytest

pytestmark = pytest.mark.unit


def test_escape_url_encodes_spaces_but_keeps_url_syntax(psh):
    assert psh.escape_url("https://x.test/a b?q=1&r=2") == "https://x.test/a%20b?q=1&r=2"


def test_escape_url_is_idempotent_on_safe_chars(psh):
    url = "https://x.test/path?a=1&b=2"
    assert psh.escape_url(url) == url


def test_fix_drush_output_passes_through_clean_json(psh):
    out, err = psh.fix_drush_output('{"ok": true}', "")
    assert out == '{"ok": true}'
    assert err == ""


def test_fix_drush_output_moves_leading_errors_into_errors(psh):
    raw = 'Warning: something\nAnother line\n{"ok": true}'
    out, err = psh.fix_drush_output(raw, "")
    assert out == '{"ok": true}'
    assert "Warning: something" in err
    assert "Another line" in err


def test_fix_drush_output_empty_is_unchanged(psh):
    assert psh.fix_drush_output("", "prior") == ("", "prior")

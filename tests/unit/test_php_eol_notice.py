"""build_php_eol_notice unit tests (campaign I1, SPEC F2)."""
import pytest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("version", ["7.4", "8.1"])
def test_deprecated_versions_warn(psh, version):
    n = psh.build_php_eol_notice("s", version)
    assert n["type"] == "warning"
    assert n["csv"] == "s,php-eol-warning"
    assert version in n["message"] and version in n["text"]


@pytest.mark.parametrize("version,fallback", [("8.0", "8.1"), ("7.0", "7.4")])
def test_older_versions_alert_with_fallback(psh, version, fallback):
    n = psh.build_php_eol_notice("s", version)
    assert n["type"] == "alert"
    assert n["csv"] == "s,php-eol-alert"
    assert f"PHP {fallback}" in n["message"] and f"PHP {fallback}" in n["text"]


@pytest.mark.parametrize("version", ["8.2", "8.3"])
def test_current_versions_need_no_notice(psh, version):
    assert psh.build_php_eol_notice("s", version) is None


def test_warning_and_alert_codes_are_distinct(psh):
    # RED pre-fix: both branches emitted the identical "s,php-eol", so the notices CSV
    # could not distinguish severity.
    warn = psh.build_php_eol_notice("s", "8.1")["csv"]
    alert = psh.build_php_eol_notice("s", "8.0")["csv"]
    assert warn != alert

"""build_php_eol_notice unit tests (campaign I1 SPEC F2; builder moved to
check/pantheon/php_eol.py at I8, where SPEC D-i8-4 fixed the version comparison and
None handling, red-first)."""
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

import psh

pytestmark = pytest.mark.unit

_PATH = Path(psh.__file__).resolve().parents[1] / "check" / "pantheon" / "php_eol.py"
build_php_eol_notice = SourceFileLoader(
    "php_eol_for_unit_tests", str(_PATH)).load_module().build_php_eol_notice


@pytest.mark.parametrize("version", ["7.4", "8.1"])
def test_deprecated_versions_warn(version):
    n = build_php_eol_notice("s", version)
    assert n["type"] == "warning"
    assert n["csv"] == "s,php-eol-warning"
    assert version in n["message"] and version in n["text"]


@pytest.mark.parametrize("version,fallback", [("8.0", "8.1"), ("7.0", "7.4")])
def test_older_versions_alert_with_fallback(version, fallback):
    n = build_php_eol_notice("s", version)
    assert n["type"] == "alert"
    assert n["csv"] == "s,php-eol-alert"
    assert f"PHP {fallback}" in n["message"] and f"PHP {fallback}" in n["text"]


@pytest.mark.parametrize("version", ["8.2", "8.3"])
def test_current_versions_need_no_notice(version):
    assert build_php_eol_notice("s", version) is None


def test_warning_and_alert_codes_are_distinct():
    warn = build_php_eol_notice("s", "8.1")["csv"]
    alert = build_php_eol_notice("s", "8.0")["csv"]
    assert warn != alert


@pytest.mark.parametrize("version", ["8.10", "9.0"])
def test_high_versions_are_not_lexicographically_eol(version):
    # RED pre-fix (D-i8-4.1): "8.10" < "8.2" is True as STRINGS -> false alert.
    assert build_php_eol_notice("s", version) is None


def test_missing_php_version_needs_no_notice():
    # RED pre-fix (D-i8-4.2): None < "8.2" raised TypeError (and the old main() call
    # site KeyError'd before the builder was even reached).
    assert build_php_eol_notice("s", None) is None


def test_unparseable_version_needs_no_notice():
    assert build_php_eol_notice("s", "banana") is None   # old behavior, preserved


def test_single_component_version_still_alerts():
    assert build_php_eol_notice("s", "8")["type"] == "alert"   # old behavior, preserved

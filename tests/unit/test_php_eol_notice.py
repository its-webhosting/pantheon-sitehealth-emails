"""build_php_eol_notice unit tests (campaign I1 SPEC F2; builder moved to
check/pantheon/php_eol.py at I8, where SPEC D-i8-4 fixed the version comparison and
None handling, red-first)."""
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

import psh

pytestmark = pytest.mark.unit

_PATH = Path(psh.__file__).resolve().parents[1] / "check" / "pantheon" / "php_eol.py"


@pytest.fixture
def build_php_eol_notice(reset_sc):
    """Load check/pantheon/php_eol.py fresh per test.  MUST stay function-scoped and inside a
    test's reset_sc window -- a module-level load registers its codes before reset_sc snapshots
    the registry, and the next load then raises DuplicateNoticeCodeError (SPEC I14c §2.3)."""
    return SourceFileLoader(
        "php_eol_for_unit_tests", str(_PATH)).load_module().build_php_eol_notice


@pytest.mark.parametrize("version", ["7.4", "8.1"])
def test_deprecated_versions_warn(build_php_eol_notice, version):
    n = build_php_eol_notice("s", version)
    assert n.severity == "warning"
    assert n.code == "php-eol-warning"
    assert n.csv_extra == ()
    assert version in n.html and version in n.text


@pytest.mark.parametrize(("version", "fallback"), [("8.0", "8.1"), ("7.0", "7.4")])
def test_older_versions_alert_with_fallback(build_php_eol_notice, version, fallback):
    n = build_php_eol_notice("s", version)
    assert n.severity == "alert"
    assert n.code == "php-eol-alert"
    assert n.csv_extra == ()
    assert f"PHP {fallback}" in n.html and f"PHP {fallback}" in n.text


@pytest.mark.parametrize("version", ["8.2", "8.3"])
def test_current_versions_need_no_notice(build_php_eol_notice, version):
    assert build_php_eol_notice("s", version) is None


def test_warning_and_alert_codes_are_distinct(build_php_eol_notice):
    warn = build_php_eol_notice("s", "8.1").code
    alert = build_php_eol_notice("s", "8.0").code
    assert warn != alert


@pytest.mark.parametrize("version", ["8.10", "9.0"])
def test_high_versions_are_not_lexicographically_eol(build_php_eol_notice, version):
    # RED pre-fix (D-i8-4.1): "8.10" < "8.2" is True as STRINGS -> false alert.
    assert build_php_eol_notice("s", version) is None


def test_missing_php_version_needs_no_notice(build_php_eol_notice):
    # RED pre-fix (D-i8-4.2): None < "8.2" raised TypeError (and the old main() call
    # site KeyError'd before the builder was even reached).
    assert build_php_eol_notice("s", None) is None


def test_unparseable_version_needs_no_notice(build_php_eol_notice):
    assert build_php_eol_notice("s", "banana") is None   # old behavior, preserved


def test_single_component_version_still_alerts(build_php_eol_notice):
    assert build_php_eol_notice("s", "8").severity == "alert"   # old behavior, preserved

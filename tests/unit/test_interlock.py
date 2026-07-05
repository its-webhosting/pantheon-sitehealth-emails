"""The safety interlock: run_program must refuse --all/-a/--for-real (SPEC §5.11, §2 C1/C2),
and refuse --create-tables/--import-older-metrics unless the run is offline against a fixture
config (test-suite SPEC Part C, constraint C2).

This is the fail-closed guard that makes the hard constraints impossible to violate, even by
a mistaken test.  Uses fixtures so the raised class matches exactly.
"""
import pytest

from conftest import MINIMAL_CONFIG

pytestmark = pytest.mark.unit


# Exact spellings, argparse abbreviations (--al/--fo/--for), and short-flag bundles (-av/-va)
# must all be refused — the guard checks meaning, not just literal tokens.
@pytest.mark.parametrize(
    "flag",
    ["--all", "-a", "--for-real", "--al", "--fo", "--for", "-av", "-va"],
)
def test_run_program_refuses_forbidden_flags(program_runner, forbidden_flag_error, flag, tmp_path):
    with pytest.raises(forbidden_flag_error):
        program_runner([flag, "its-wws-test1"], cwd=tmp_path)


def test_run_program_refuses_forbidden_flag_among_others(program_runner, forbidden_flag_error, tmp_path):
    with pytest.raises(forbidden_flag_error):
        program_runner(["its-wws-test1", "--date", "2026-03-31", "--for-real"], cwd=tmp_path)


def test_allowed_flags_do_not_raise_the_interlock(program_runner, forbidden_flag_error, tmp_path):
    # A benign invocation must not trip the interlock (it will fail for other reasons,
    # e.g. missing config, but NOT ForbiddenFlagError).
    try:
        program_runner(["--help"], cwd=tmp_path)
    except forbidden_flag_error:
        pytest.fail("interlock wrongly raised for an allowed invocation")


# ── Part C: --create-tables / --import-older-metrics must never touch the production DB ──


@pytest.mark.parametrize(
    "flag",
    ["--create-tables", "--import-older-metrics", "--create", "--import"],
)
def test_data_flags_refused_in_live_mode(program_runner, forbidden_live_data_error, flag, tmp_path):
    # Live mode implies the real config/DB; schema/import flags (and their abbreviations) are
    # refused before the program ever execs.
    with pytest.raises(forbidden_live_data_error):
        program_runner([flag, "--config", str(MINIMAL_CONFIG)], cwd=tmp_path, mode="live")


@pytest.mark.parametrize("flag", ["--create-tables", "--import-older-metrics"])
def test_data_flags_refused_without_fixture_config(program_runner, forbidden_live_data_error, flag, tmp_path):
    # No --config -> falls back to the production default filename -> not on the allowlist.
    with pytest.raises(forbidden_live_data_error):
        program_runner([flag], cwd=tmp_path)
    # An explicit config outside the fixture allowlist (and outside cwd) is also refused.
    with pytest.raises(forbidden_live_data_error):
        program_runner([flag, "--config", "/etc/pantheon-prod.toml"], cwd=tmp_path)


def test_create_tables_offline_with_fixture_config_allowed(
    program_runner, forbidden_live_data_error, tmp_path
):
    # The sanctioned offline path (fixture config, replay mode) must NOT trip the live-data
    # guard.  It exits non-zero by design (sys.exit("Tables created.")) and writes test.db
    # into the throwaway cwd.
    try:
        proc = program_runner(
            ["--create-tables", "--config", str(MINIMAL_CONFIG)], cwd=tmp_path
        )
    except forbidden_live_data_error:
        pytest.fail("live-data interlock wrongly raised for an offline fixture-config run")
    assert (tmp_path / "test.db").exists()
    assert "Tables created." in (proc.stdout + proc.stderr)


def test_create_tables_config_after_double_dash_is_refused(
    program_runner, forbidden_live_data_error, tmp_path
):
    # Regression: a --config placed AFTER `--` is positional to argparse (so the program would
    # use its DEFAULT/production config), but the guard used to read it and pass.  The config
    # resolver must stop at `--` too, so no effective fixture config is seen -> refuse.
    with pytest.raises(forbidden_live_data_error):
        program_runner(
            ["--create-tables", "--", "--config", str(MINIMAL_CONFIG)], cwd=tmp_path
        )

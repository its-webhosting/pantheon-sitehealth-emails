"""The safety interlock: run_program must refuse --all/-a/--for-real (SPEC §5.11, §2 C1/C2).

This is the fail-closed guard that makes the two hard constraints impossible to violate,
even by a mistaken test.  Uses fixtures so the raised class matches exactly.
"""
import pytest

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

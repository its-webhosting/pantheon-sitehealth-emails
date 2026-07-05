"""Unit tests locking the CLI contract (test-suite SPEC §7.1).

Parser-level rules (unknown options, bad --date, defaults) are tested in-process via
psh.parse_args.  The two validations that live in main() (mutual exclusion, sites-or-all) are
exercised through run_program, which stays inside the safety interlock and asserts a nonzero
exit + message rather than an in-process SystemExit.
"""
import datetime
import os

import pytest

from conftest import MINIMAL_CONFIG

pytestmark = pytest.mark.unit


# ── Parser level ─────────────────────────────────────────────────────────────────────
def test_defaults(psh):
    ns = psh.parse_args([])
    assert ns.all is False
    assert ns.sites == []
    assert ns.config == "pantheon-sitehealth-emails.toml"
    assert ns.smtp_username == os.environ.get("USER", "")
    assert ns.verbose == 0
    assert ns.create_tables is False
    assert ns.import_older_metrics is False
    assert ns.for_real is False
    assert isinstance(ns.date, datetime.date)  # defaults to today


def test_verbose_counts(psh):
    assert psh.parse_args(["-vvv"]).verbose == 3
    assert psh.parse_args(["-v"]).verbose == 1


def test_sites_positional(psh):
    assert psh.parse_args(["its-wws-test1", "its-wws-test2"]).sites == [
        "its-wws-test1",
        "its-wws-test2",
    ]


def test_date_parses_isoformat(psh):
    assert psh.parse_args(["--date", "2026-03-31"]).date == datetime.date(2026, 3, 31)


def test_bad_date_exits(psh):
    with pytest.raises(SystemExit):
        psh.parse_args(["--date", "2026-13-40"])


@pytest.mark.parametrize("bad", ["--fo", "--al", "--for", "--unknown"])
def test_abbreviations_rejected_allow_abbrev_false(psh, bad):
    # allow_abbrev=False -> prefixes of real options are unknown options, not matches.
    with pytest.raises(SystemExit):
        psh.parse_args([bad])


# ── main()-level validation (via the interlock-guarded runner) ───────────────────────
def test_create_tables_and_import_are_mutually_exclusive(program_runner, tmp_path):
    proc = program_runner(
        ["--create-tables", "--import-older-metrics", "--config", str(MINIMAL_CONFIG)],
        cwd=tmp_path,
    )
    assert proc.returncode != 0
    assert "mutually exclusive" in (proc.stdout + proc.stderr)


def test_requires_sites_or_all(program_runner, tmp_path):
    proc = program_runner(
        ["--config", str(MINIMAL_CONFIG), "--date", "2026-03-31"], cwd=tmp_path
    )
    assert proc.returncode != 0
    assert "must specify either at least one site or the --all option" in (
        proc.stdout + proc.stderr
    )

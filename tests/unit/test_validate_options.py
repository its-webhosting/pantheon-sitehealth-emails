"""Unit tier: psh.cli.validate_options, main()'s four argument guards
(development/2026-08-07-main-extraction/SPEC.md section 5.6 -- B5).

Seam (SPEC section 6 row 6): called directly, no subprocess, no run_program(). Drive
sc.options via `reset_sc.options = psh.parse_args([...])` and sc.config via
`reset_sc.config = {...}`, then assert `pytest.raises(SystemExit)` on the message -- the
exact idiom tests/unit/test_argparse_contract.py already uses for sc.smtp_username().

Three of the four guards were previously reachable only through a full subprocess boot
via run_program (tests/integration/test_argparse_contract.py's "main()-level validation"
section, which stays -- it still exercises the same code through main(), now delegating
to this function). The fourth -- --update-cloudflare-fqdns without [Cloudflare].enabled --
had NO coverage at any tier before this file: no exit message for it appears anywhere
under tests/ (SPEC R6.5). sc.options.verbose == 3 after --create-tables is likewise
unobservable through a subprocess (only inferrable from output volume), and the
`--all and sites != 0` half of the sites-or-all disjunction is UNREACHABLE at the
subprocess tier at all, because --all is in conftest.FORBIDDEN_FLAGS.

The guard SHADOWING ORDER (SPEC R6.3) is load-bearing: the --resume-from guards run
before the create-tables and sites-or-all checks, which would otherwise exit first and
hide the more precise --resume-from messages. test_guard_shadowing_order below is a
table-driven parametrize over exactly this, at microsecond cost instead of eight
subprocess boots (SPEC R6.5).
"""
import pytest

pytestmark = pytest.mark.unit


# ── shadowing order, table-driven (SPEC R6.3 / R6.5) ────────────────────────────────────
@pytest.mark.parametrize(
    ("argv", "expected_message"),
    [
        # Guard 1: --resume-from + --create-tables -- its own message, not shadowed by
        # the sites-or-all check below it.
        (
            ["--resume-from", "its-wws-test1", "--create-tables"],
            "The --resume-from and --create-tables options are mutually exclusive.",
        ),
        # Guard 2: --resume-from without --all -- its own message, not shadowed by the
        # sites-or-all check (which would otherwise fire first, since neither --all nor
        # a SITE was given here either).
        (
            ["--resume-from", "its-wws-test1"],
            "--resume-from can only be used together with --all.",
        ),
        # Guard 3, first half: --create-tables + --import-older-metrics.
        (
            ["--create-tables", "--import-older-metrics"],
            "The --import-older-metrics and --create-tables options are mutually exclusive.",
        ),
        # Guard 3, second half (elif): neither --all nor a SITE.
        (
            [],
            "You must specify either at least one site or the --all option.",
        ),
        # Guard 3, second half, the OTHER disjunct: --all together with a SITE. This is
        # the case that is UNREACHABLE at the subprocess tier (--all is a
        # conftest.FORBIDDEN_FLAGS entry) -- reachable here in one line.
        (
            ["--all", "its-wws-test1"],
            "You must specify either at least one site or the --all option.",
        ),
    ],
)
def test_guard_shadowing_order(psh, reset_sc, argv, expected_message):
    reset_sc.options = psh.parse_args(argv)
    reset_sc.config = {}

    with pytest.raises(SystemExit) as exc:
        psh.validate_options()
    assert expected_message in str(exc.value)


# ── the in-place mutation: sc.options.verbose = 3 after --create-tables ─────────────────
def test_create_tables_forces_verbose_3(psh, reset_sc):
    reset_sc.options = psh.parse_args(["--create-tables"])
    assert reset_sc.options.verbose == 0  # precondition: not already 3

    psh.validate_options()

    assert reset_sc.options.verbose == 3


def test_create_tables_does_not_force_verbose_when_already_higher(psh, reset_sc):
    # -vvv already asked for 3; validate_options must not be the ONLY path that can set
    # it (guarding against a future rewrite like `sc.options.verbose = max(3, ...)`
    # accidentally becoming `= 3` unconditionally in a way that regresses a HIGHER
    # requested verbosity -- verbose only ever counts up to 3 via -v/-vv/-vvv, so this
    # is the ceiling case).
    reset_sc.options = psh.parse_args(["--create-tables", "-vvv"])
    assert reset_sc.options.verbose == 3

    psh.validate_options()

    assert reset_sc.options.verbose == 3


# ── guard 4: --update-cloudflare-fqdns requires [Cloudflare].enabled (SPEC R6.5) ────────
# This guard has NO coverage at any tier before this file: no exit message for it
# appears anywhere under tests/ (verified in SPEC section 1.2 / R6.5).
def test_update_cloudflare_fqdns_without_cloudflare_section_exits(psh, reset_sc):
    reset_sc.options = psh.parse_args(["--all", "--update-cloudflare-fqdns"])
    reset_sc.config = {}  # no [Cloudflare] section at all

    with pytest.raises(SystemExit) as exc:
        psh.validate_options()
    assert (
        "--update-cloudflare-fqdns requires the [Cloudflare] section to be enabled in the config."
        in str(exc.value)
    )


def test_update_cloudflare_fqdns_with_cloudflare_disabled_exits(psh, reset_sc):
    reset_sc.options = psh.parse_args(["--all", "--update-cloudflare-fqdns"])
    reset_sc.config = {"Cloudflare": {"enabled": False}}

    with pytest.raises(SystemExit) as exc:
        psh.validate_options()
    assert "--update-cloudflare-fqdns requires the [Cloudflare] section" in str(exc.value)


def test_update_cloudflare_fqdns_with_cloudflare_enabled_does_not_exit(psh, reset_sc):
    reset_sc.options = psh.parse_args(["--all", "--update-cloudflare-fqdns"])
    reset_sc.config = {"Cloudflare": {"enabled": True}}

    assert psh.validate_options() is None  # no sys.exit


# ── shadow paths (SPEC R6.6) ─────────────────────────────────────────────────────────────
def test_nil_no_flags_at_all_exits_sites_or_all(psh, reset_sc):
    # Nil input: nothing specified at all.
    reset_sc.options = psh.parse_args([])
    reset_sc.config = {}

    with pytest.raises(SystemExit) as exc:
        psh.validate_options()
    assert "must specify either at least one site or the --all option" in str(exc.value)


def test_empty_config_with_no_cloudflare_section_does_not_keyerror(psh, reset_sc):
    # Empty/upstream-shaped input: sc.config has no [Cloudflare] key at all, and the
    # flag was not passed -- the .get(...).get(...) chain must not KeyError.
    reset_sc.options = psh.parse_args(["its-wws-test1"])
    reset_sc.config = {}

    assert psh.validate_options() is None


def test_upstream_error_create_tables_and_import_older_metrics_mutually_exclusive(
    psh, reset_sc
):
    reset_sc.options = psh.parse_args(["--create-tables", "--import-older-metrics"])
    reset_sc.config = {}

    with pytest.raises(SystemExit) as exc:
        psh.validate_options()
    assert (
        "The --import-older-metrics and --create-tables options are mutually exclusive."
        in str(exc.value)
    )


# ── happy path: no exit at all ───────────────────────────────────────────────────────────
def test_valid_single_site_no_flags_returns_none(psh, reset_sc):
    reset_sc.options = psh.parse_args(["its-wws-test1"])
    reset_sc.config = {"Cloudflare": {"enabled": True}}

    assert psh.validate_options() is None

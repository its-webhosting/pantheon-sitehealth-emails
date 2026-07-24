import dataclasses

import pytest

from psh.notice import (
    DuplicateNoticeCodeError,
    Notice,
    NoticeRegistry,
    Severity,
    registry,
)

pytestmark = pytest.mark.unit


def test_notice_is_frozen():
    n = Notice(severity=Severity.INFO, code="c", html="<p>x</p>")
    assert dataclasses.replace(n, short="s").short == "s"       # copy works
    with pytest.raises(dataclasses.FrozenInstanceError):
        n.short = "s"                                            # in-place assignment blocked


def test_severity_is_str_enum():
    assert Severity.ALERT == "alert"
    assert str(Severity.ALERT) == "alert"
    assert {s.value for s in Severity} == {"alert", "warning", "info"}


def test_registry_rejects_duplicate_code():
    # THE registry test (SPEC §New tests #1).  Fresh instance -> no global pollution.
    reg = NoticeRegistry()
    reg.register("x")
    with pytest.raises(DuplicateNoticeCodeError):
        reg.register("x")


def test_registry_registers_distinct_codes():
    reg = NoticeRegistry()
    reg.register("a")
    reg.register("b")
    assert reg.codes() == frozenset({"a", "b"})


def test_global_registry_has_the_poc_code(psh):
    # Importing the program (psh fixture -> psh.cli) registered the PoC code at import.
    assert "no-domains" in registry.codes()


def test_csv_extra_defaults_to_empty_and_is_a_tuple():
    n = Notice(severity=Severity.ALERT, code="frozen", html="<p>x</p>")
    assert n.csv_extra == ()


def test_registry_snapshot_and_restore_round_trip():
    r = NoticeRegistry()
    r.register("a")
    saved = r.snapshot()
    r.register("b")
    assert r.codes() == frozenset({"a", "b"})
    r.restore(saved)
    assert r.codes() == frozenset({"a"})
    r.register("b")          # restore must make a re-registration legal again
    assert r.codes() == frozenset({"a", "b"})


def test_csv_extra_rejects_a_non_str_element_by_name():
    # Most producers live in check/, outside pyright's scope, so a forgotten str() around an int
    # csv field must fail AT the producer with the notice code in the message, not later inside
    # script_context's ",".join (PD#2 -- every error has a name).
    with pytest.raises(TypeError, match=r"Notice\('updates-addons'\)\.csv_extra"):
        Notice(severity=Severity.WARNING, code="updates-addons", html="<p>x</p>", csv_extra=(3,))


def test_severity_must_be_a_severity_member():
    # A bare string reaches the projection's icon map and surfaces as an anonymous
    # KeyError: 'warn' -- naming neither the notice nor the module (PD#2).  Most producers
    # live in check/, outside pyright's scope, so the type system cannot catch it either.
    # VALIDATION, not coercion: the csv_extra posture (D-i14c-1) applied to severity.
    with pytest.raises(TypeError, match=r"Notice\('frozen'\)\.severity"):
        Notice(severity="warning", code="frozen", html="<p>x</p>")

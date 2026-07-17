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
    # Importing the program (psh fixture -> psh._legacy) registered the PoC code at import.
    assert "no-domains" in registry.codes()

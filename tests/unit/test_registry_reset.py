"""The autouse reset_sc fixture restores psh.notice.registry between tests (campaign I14c).

Producing modules register their notice codes at import, and the suite loads check/ modules
standalone once per test, so an in-test registration MUST be undone or the next load of that
module raises DuplicateNoticeCodeError.  Registering the SAME code from two consecutive tests is
the only condition that can go red, so that is what this pins -- parametrized rather than written
as two sibling functions, so the ordering is explicit instead of dependent on file order.

Without this test the restore has no permanent cover: tests/unit/test_notice.py's round-trip test
exercises a FRESH NoticeRegistry and never touches the conftest wiring, so deleting the restore
line changes no result (measured -- 1028 passed either way).  PD#14: a green check is a claim
until it has been shown capable of going red on the condition it guards.
"""
import pytest

from psh.notice import registry

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("_run", [1, 2])
def test_reset_sc_restores_the_notice_registry(_run, reset_sc):
    registry.register("probe-reset-sc")

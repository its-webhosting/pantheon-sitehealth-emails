"""Syrupy pins of the three build_smell_notices bodies (campaign I10, D-i10-8): the
forward byte-identity guard for the composer-literal de-indent -- CAMPAIGN.md
section 10's grep still finds zero smell renders in any golden, so this file is the
only render coverage for these three notice bodies.

Repointed on 2026-08-07 when the builder relocated to check/smells/notices.py
(development/2026-08-07-smell-notice-relocation/SPEC.md).  The three test names are unchanged
on purpose: syrupy keys the .ambr by file name AND test name, so this file's snapshots stay
byte-identical across the move -- which is precisely the evidence that the literals moved
verbatim."""
import pytest
from helpers.checkload import load_check_module

pytestmark = pytest.mark.integration


@pytest.fixture
def smells(psh, request):
    return load_check_module(psh, "smells", "notices", "smells_notices_render_probe", request)


def test_wp_smell_notice_snapshot(smells, snapshot):
    (n,) = smells.build_smell_notices("its-wws-test1", "wp broke", "", "")
    assert n.html == snapshot
    assert n.text == snapshot
    assert n.short == snapshot


def test_drush_smell_notice_snapshot(smells, snapshot):
    (n,) = smells.build_smell_notices("its-wws-test1", "", "drush broke", "")
    assert n.html == snapshot
    assert n.text == snapshot
    assert n.short == snapshot


def test_composer_smell_notice_snapshot(smells, snapshot):
    # D-i10-8: pins the de-indented (column-0) composer literal, matching the wp/drush
    # siblings' shape.
    (n,) = smells.build_smell_notices("its-wws-test1", "", "", "composer broke")
    assert n.html == snapshot
    assert n.text == snapshot
    assert n.short == snapshot

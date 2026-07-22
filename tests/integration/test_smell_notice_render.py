"""Syrupy pins of the three build_smell_notices bodies (campaign I10, D-i10-8): the
forward byte-identity guard for the composer-literal de-indent -- CAMPAIGN.md
section 10's grep still finds zero smell renders in any golden, so this file is the
only render coverage for these three notice bodies."""
import pytest

pytestmark = pytest.mark.integration


def test_wp_smell_notice_snapshot(psh, snapshot):
    (n,) = psh.build_smell_notices("its-wws-test1", "wp broke", "", "")
    assert n["message"] == snapshot
    assert n["text"] == snapshot
    assert n["short"] == snapshot


def test_drush_smell_notice_snapshot(psh, snapshot):
    (n,) = psh.build_smell_notices("its-wws-test1", "", "drush broke", "")
    assert n["message"] == snapshot
    assert n["text"] == snapshot
    assert n["short"] == snapshot


def test_composer_smell_notice_snapshot(psh, snapshot):
    # D-i10-8: pins the de-indented (column-0) composer literal, matching the wp/drush
    # siblings' shape.
    (n,) = psh.build_smell_notices("its-wws-test1", "", "", "composer broke")
    assert n["message"] == snapshot
    assert n["text"] == snapshot
    assert n["short"] == snapshot

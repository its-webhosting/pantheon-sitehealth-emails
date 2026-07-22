"""Syrupy pin of the relocated check/umich Drupal user-agent notice body -- the forward
byte-identity guard for the verbatim move (campaign I10; move-time evidence is the
extracted-block diff in the task report, the I2 precedent)."""
import json

import pytest

from helpers.checkload import load_check_module

pytestmark = pytest.mark.integration

SITE = "its-wws-test1"
SITE_ID = "abc123"
TEMPLATE_UA = "Drupal (+https://drupal.org/); UMich; https://your-site.example.edu/"


def _ctx(reset_sc):
    ctx = reset_sc.SiteContext({"name": SITE, "id": SITE_ID})
    ctx["framework"] = "drupal10"
    ctx["drupal_version"] = "10.1"
    return ctx


def test_drupal_ua_notice_snapshot(psh, reset_sc, request, gateway, monkeypatch, snapshot):
    monkeypatch.setattr(
        gateway,
        "run_terminus",
        lambda command, input_data=None: (json.dumps({"result": TEMPLATE_UA}), "", False),
    )
    mod = load_check_module(psh, "umich", "drupal_ua", "umich_drupal_ua_snap", request)
    ctx = _ctx(reset_sc)
    mod.check_drupal_ua(ctx)
    n = ctx["notices"][0]
    assert n["message"] == snapshot
    assert n["text"] == snapshot
    assert n["short"] == snapshot

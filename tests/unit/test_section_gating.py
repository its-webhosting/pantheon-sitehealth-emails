"""Unit tests for gate_disabled_sections (the `enabled = false` strip rule).

A disabled section keeps only {'enabled': False}; its other settings are dropped BEFORE
substitution, so a disabled feature never forces its <{secret env ...}> values to exist.
"""
import importlib

import pytest

import plugin.env

pytestmark = pytest.mark.unit


def test_disabled_section_keeps_only_enabled(psh, reset_sc):
    cfg = {"Widget": {"enabled": False, "email": "e", "password": "p"}}
    out = psh.gate_disabled_sections(cfg)
    assert out["Widget"] == {"enabled": False}


def test_enabled_true_section_untouched(psh, reset_sc):
    cfg = {"Widget": {"enabled": True, "email": "e"}}
    out = psh.gate_disabled_sections(cfg)
    assert out["Widget"] == {"enabled": True, "email": "e"}


def test_section_without_enabled_untouched(psh, reset_sc):
    cfg = {"Email": {"from": "x", "reply_to": "y"}}
    out = psh.gate_disabled_sections(cfg)
    assert out["Email"] == {"from": "x", "reply_to": "y"}


def test_string_false_is_not_stripped(psh, reset_sc):
    # Only the boolean False triggers the strip; the string "false" is left alone.
    cfg = {"Widget": {"enabled": "false", "k": "v"}}
    out = psh.gate_disabled_sections(cfg)
    assert out["Widget"] == {"enabled": "false", "k": "v"}


def test_non_table_top_level_values_untouched(psh, reset_sc):
    cfg = {"scalar": 5, "Widget": {"enabled": False, "k": "v"}}
    out = psh.gate_disabled_sections(cfg)
    assert out["scalar"] == 5
    assert out["Widget"] == {"enabled": False}


def test_nested_disabled_subtable_is_stripped(psh, reset_sc):
    # Recursion: [Cloudflare.cachecheck] enabled=false is reduced even though its parent stays.
    cfg = {"Cloudflare": {"enabled": True, "api_token": "t",
                          "cachecheck": {"enabled": False, "account_id": "a", "list_name": "l"}}}
    out = psh.gate_disabled_sections(cfg)
    assert out["Cloudflare"]["cachecheck"] == {"enabled": False}
    assert out["Cloudflare"]["api_token"] == "t"


def test_disabled_parent_wins_over_enabled_child(psh, reset_sc):
    # A disabled parent drops its nested tables entirely, even enabled ones.
    cfg = {"Cloudflare": {"enabled": False, "api_token": "t",
                          "cachecheck": {"enabled": True, "account_id": "a"}}}
    out = psh.gate_disabled_sections(cfg)
    assert out["Cloudflare"] == {"enabled": False}


def test_enabled_child_untouched_but_disabled_grandchild_gated(psh, reset_sc):
    cfg = {"A": {"enabled": True,
                 "B": {"enabled": True, "keep": 1,
                       "C": {"enabled": False, "secret": "<{secret env X}"}}}}
    out = psh.gate_disabled_sections(cfg)
    assert out["A"]["B"]["keep"] == 1
    assert out["A"]["B"]["C"] == {"enabled": False}


def test_string_false_at_depth_untouched(psh, reset_sc):
    cfg = {"A": {"B": {"enabled": "false", "k": "v"}}}
    out = psh.gate_disabled_sections(cfg)
    assert out["A"]["B"] == {"enabled": "false", "k": "v"}


def test_disabled_section_substitution_is_never_resolved(psh, reset_sc, monkeypatch):
    # The whole point: a disabled section referencing an UNSET env var must not abort the run,
    # because gate_disabled_sections drops the value before process_config runs.
    importlib.reload(plugin.env)  # register env substitutions into the reset list
    monkeypatch.delenv("DEFINITELY_UNSET_X", raising=False)

    cfg = {"Widget": {"enabled": False, "password": "<{secret env DEFINITELY_UNSET_X}"}}
    gated = psh.gate_disabled_sections(cfg)
    # Must NOT raise SystemExit:
    out = psh.process_config(gated)
    assert out["Widget"] == {"enabled": False}


def test_enabled_section_substitution_still_required(psh, reset_sc, monkeypatch):
    # Contrast: the same unresolvable value in an ENABLED section aborts (no strip).
    importlib.reload(plugin.env)
    monkeypatch.delenv("DEFINITELY_UNSET_X", raising=False)

    cfg = {"Widget": {"enabled": True, "password": "<{secret env DEFINITELY_UNSET_X}"}}
    gated = psh.gate_disabled_sections(cfg)
    with pytest.raises(SystemExit):
        psh.process_config(gated)

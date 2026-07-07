"""Unit tests for the `env` config-substitution plugin (plugin/env/).

get_env is pure given os.environ; the substitution wiring is exercised end-to-end through the
real engine (process_config / config_substitution).  reset_sc empties sc.substitutions per test,
so we reload plugin.env to re-run its top-level registration into the fresh list.
"""
import importlib
import os

import pytest
from hypothesis import given, strategies as st

import plugin.env
import script_context as sc
from plugin.env.get_env import get_env

pytestmark = pytest.mark.unit


@pytest.fixture
def env_plugin(reset_sc):
    """Register the env substitutions into the freshly-reset sc.substitutions."""
    importlib.reload(plugin.env)  # re-runs the module-level sc.substitutions.append(...) calls
    return reset_sc


# ── get_env, in isolation ────────────────────────────────────────────────────────────
def test_get_env_returns_value_when_set(monkeypatch):
    monkeypatch.setenv("PSH_TEST_VAR", "hello")
    assert get_env("PSH_TEST_VAR") == "hello"


def test_get_env_empty_but_set_returns_empty(monkeypatch):
    monkeypatch.setenv("PSH_TEST_VAR", "")
    assert get_env("PSH_TEST_VAR") == ""  # set != unset: no default, no error


def test_get_env_unset_with_default_returns_default(monkeypatch):
    monkeypatch.delenv("PSH_TEST_VAR", raising=False)
    assert get_env("PSH_TEST_VAR", "fallback") == "fallback"


def test_get_env_unset_no_default_raises(monkeypatch):
    monkeypatch.delenv("PSH_TEST_VAR", raising=False)
    with pytest.raises(sc.ConfigSubstitutionError) as exc:
        get_env("PSH_TEST_VAR")
    assert "PSH_TEST_VAR" in str(exc.value)


def test_empty_string_default_is_honored(monkeypatch):
    # An empty-string default is a real default, distinct from "no default supplied" (which raises).
    monkeypatch.delenv("PSH_TEST_VAR", raising=False)
    assert get_env("PSH_TEST_VAR", "") == ""


# ── Registration ─────────────────────────────────────────────────────────────────────
def test_registers_four_patterns_in_order(env_plugin):
    patterns = [s["args"] for s in env_plugin.substitutions]
    assert patterns == [
        ["env", "$name"],
        ["env", "$name", "$default"],
        ["secret", "env", "$name"],
        ["secret", "env", "$name", "$default"],
    ]
    # The 2-arg form MUST precede its 3-arg counterpart (perfect-match short-circuit).
    assert patterns.index(["env", "$name"]) < patterns.index(["env", "$name", "$default"])
    assert patterns.index(["secret", "env", "$name"]) < patterns.index(
        ["secret", "env", "$name", "$default"]
    )


# ── End-to-end through the real engine ───────────────────────────────────────────────
@pytest.mark.parametrize("expr", ["<{env FOO}", "<{secret env FOO}"])
def test_bare_and_secret_forms_resolve(psh, env_plugin, monkeypatch, expr):
    monkeypatch.setenv("FOO", "barval")
    assert psh.process_config({"x": expr})["x"] == "barval"


@pytest.mark.parametrize("expr", ["<{env MISSING_X fallback}", "<{secret env MISSING_X fallback}"])
def test_default_used_when_unset(psh, env_plugin, monkeypatch, expr):
    monkeypatch.delenv("MISSING_X", raising=False)
    assert psh.process_config({"x": expr})["x"] == "fallback"


def test_default_with_spaces_via_quotes(psh, env_plugin, monkeypatch):
    monkeypatch.delenv("MISSING_X", raising=False)
    assert psh.process_config({"x": '<{env MISSING_X "multi word"}'})["x"] == "multi word"


def test_set_value_beats_default(psh, env_plugin, monkeypatch):
    monkeypatch.setenv("FOO", "realval")
    assert psh.process_config({"x": "<{env FOO ignored_default}"})["x"] == "realval"


def test_missing_no_default_exits_with_path_and_name(psh, env_plugin, monkeypatch, capsys):
    monkeypatch.delenv("MISSING_X", raising=False)
    with pytest.raises(SystemExit):
        psh.process_config({"SMTP": {"password": "<{env MISSING_X}"}})
    msg = capsys.readouterr()
    out = msg.out + msg.err
    assert "SMTP.password" in out and "MISSING_X" in out


def test_secret_env_does_not_collide_with_aws_secret(psh, env_plugin, monkeypatch):
    # Register an aws-shaped `secret aws` pattern alongside env's `secret env`; each dispatches
    # to its own function (disjoint second token).
    monkeypatch.setenv("FOO", "envval")
    env_plugin.substitutions.append(
        {"args": ["secret", "aws", "$n", "$k"], "func": lambda n, k: f"aws:{n}.{k}",
         "func_args": ["$n", "$k"]}
    )
    assert psh.process_config({"x": "<{secret env FOO}"})["x"] == "envval"
    assert psh.process_config({"y": "<{secret aws webinfo db_pass}"})["y"] == "aws:webinfo.db_pass"


# ── Property: set -> get round-trips; unset -> default ────────────────────────────────
@given(
    name=st.text(alphabet=st.characters(min_codepoint=65, max_codepoint=90), min_size=1, max_size=12),
    # os.environ rejects the null byte and lone surrogates in values (OS/UTF-8 constraints, not a
    # get_env concern).
    value=st.text(
        alphabet=st.characters(blacklist_characters="\x00", blacklist_categories=["Cs"]),
        max_size=50,
    ),
)
def test_property_set_get_roundtrip(name, value):
    # os.environ managed directly (not via the function-scoped monkeypatch fixture, which
    # Hypothesis would reuse across examples).
    name = "PSH_PROP_" + name
    saved = os.environ.get(name)
    try:
        os.environ[name] = value
        assert get_env(name) == value
        del os.environ[name]
        assert get_env(name, "D") == "D"
    finally:
        if saved is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = saved

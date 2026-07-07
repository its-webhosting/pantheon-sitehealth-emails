"""Unit tests for the config <{ ... }> substitution engine (test-suite SPEC §7.1).

config_substitution / process_config are pure given the registered sc.substitutions, which the
autouse reset_sc fixture resets to [] per test.  reset_sc yields the script_context module, so
tests register substitutions on it directly.
"""
import pytest

pytestmark = pytest.mark.unit


def _sub(args, func, func_args=None):
    return {"args": args, "func_args": func_args or [], "func": func}


def test_exact_plus_wildcard_resolves(psh, reset_sc):
    reset_sc.substitutions.append(
        _sub(["greet", "$who"], lambda who: f"HELLO {who}", ["$who"])
    )
    assert psh.config_substitution("greet world", "Some.path") == "HELLO world"


def test_result_is_stringified(psh, reset_sc):
    reset_sc.substitutions.append(_sub(["answer"], lambda: 42))
    assert psh.config_substitution("answer", "p") == "42"


def test_shlex_honours_quotes(psh, reset_sc):
    reset_sc.substitutions.append(
        _sub(["greet", "$who"], lambda who: f"HELLO {who}", ["$who"])
    )
    assert psh.config_substitution('greet "big world"', "p") == "HELLO big world"


def test_more_specific_match_wins_over_partial_literal_mismatch(psh, reset_sc):
    # A sub whose literal mismatches breaks early (lower score) and loses to a wildcard sub.
    reset_sc.substitutions.append(_sub(["config", "value"], lambda: "A"))
    reset_sc.substitutions.append(_sub(["config", "$x"], lambda x: f"B{x}", ["$x"]))
    assert psh.config_substitution("config other", "p") == "Bother"


def test_unknown_expression_exits(psh, reset_sc):
    # No registered substitution matches at all -> best_match_score == 0 -> sys.exit(1).
    with pytest.raises(SystemExit):
        psh.config_substitution("totally unknown thing", "p")


def test_partial_match_exits(psh, reset_sc):
    # Matches the first token but the expression is longer than the sub's args -> no full match.
    reset_sc.substitutions.append(_sub(["a"], lambda: "x"))
    with pytest.raises(SystemExit):
        psh.config_substitution("a b", "p")


def test_none_result_exits(psh, reset_sc):
    reset_sc.substitutions.append(_sub(["nothing"], lambda: None))
    with pytest.raises(SystemExit):
        psh.config_substitution("nothing", "p")


def test_resolved_value_with_delimiters_survives_two_passes(psh, reset_sc):
    # A substitution whose OUTPUT contains a "<{...}" sequence (e.g. a password that happens to
    # contain one) must NOT be re-interpreted by the post-setup pass -- it must be preserved
    # literally, not aborted as an "unknown substitution".
    reset_sc.substitutions.append(_sub(["pw"], lambda: "p@ss<{x}"))
    cfg = {"SMTP": {"password": "<{pw}"}}
    cfg = psh.process_config(cfg)                        # pass 1 (pre-setup)
    assert cfg["SMTP"]["password"] == "p@ss<{x}"
    cfg = psh.process_config(cfg, deferred_pass=True)    # pass 2 (post-setup) must not touch it
    assert cfg["SMTP"]["password"] == "p@ss<{x}"


def test_defer_sentinel_reresolves_on_second_pass(psh, reset_sc):
    # A substitution that returns sc.DEFER is re-emitted by pass 1 and re-resolved by the
    # deferred (post-setup) pass -- this is how plugin.umich's plan_info waits for its DB data.
    import script_context as sc

    calls = {"n": 0}

    def deferring():
        calls["n"] += 1
        return sc.DEFER if calls["n"] == 1 else "ready"

    reset_sc.substitutions.append(_sub(["thing"], deferring))
    cfg = {"x": "<{thing}"}
    cfg = psh.process_config(cfg)                        # pass 1 -> defers, re-emits a tagged marker
    assert cfg["x"] != "ready" and "thing" in cfg["x"]  # not yet resolved
    cfg = psh.process_config(cfg, deferred_pass=True)    # pass 2 -> resolves against ready data
    assert cfg["x"] == "ready"


def test_deferred_pass_ignores_untagged_markers(psh, reset_sc):
    # The deferred pass must ignore a plain "<{...}" that is NOT a deferred re-emission (it would
    # be a pass-1 final literal), even if it looks like a registered substitution.
    reset_sc.substitutions.append(_sub(["greet", "$who"], lambda who: f"HELLO {who}", ["$who"]))
    out = psh.process_config({"x": "<{greet world}"}, deferred_pass=True)
    assert out["x"] == "<{greet world}"  # untouched: not a deferred marker


def test_uncaptured_var_exits_cleanly(psh, reset_sc, capsys):
    # A pattern that matches on token count but leaves a $var uncaptured (the short-form of a
    # $var-bearing pattern, e.g. the zero-name "<{env}") must exit with a "malformed" message,
    # not a bare KeyError traceback (the func_args guard).
    reset_sc.substitutions.append(_sub(["env", "$name"], lambda name: name, ["$name"]))
    with pytest.raises(SystemExit):
        psh.config_substitution("env", "Some.path")
    err = capsys.readouterr()
    assert "malformed substitution" in (err.out + err.err)


def test_process_config_recurses_dict_list_str(psh, reset_sc):
    reset_sc.substitutions.append(
        _sub(["greet", "$who"], lambda who: f"HELLO {who}", ["$who"])
    )
    data = {
        "a": "<{ greet x }",
        "b": ["<{ greet y }", 5],
        "c": {"d": "<{ greet z }"},
        "n": 42,
    }
    out = psh.process_config(data)
    assert out["a"] == "HELLO x"
    assert out["b"] == ["HELLO y", 5]
    assert out["c"]["d"] == "HELLO z"
    assert out["n"] == 42


def test_process_config_result_reflects_data_available_at_call_time(psh, reset_sc):
    # Why main() runs process_config again after the setup hooks: a substitution's return value
    # reflects the backing data available WHEN it runs.  Two runs, changed data -> changed result.
    state = {"v": "before"}
    reset_sc.substitutions.append(_sub(["s"], lambda: state["v"]))

    first = psh.process_config({"x": "<{ s }"})
    assert first["x"] == "before"

    state["v"] = "after"  # e.g. a setup hook populated the data
    second = psh.process_config({"x": "<{ s }"})
    assert second["x"] == "after"


def test_plain_strings_are_untouched(psh, reset_sc):
    out = psh.process_config({"a": "no substitution here", "b": 7})
    assert out == {"a": "no substitution here", "b": 7}

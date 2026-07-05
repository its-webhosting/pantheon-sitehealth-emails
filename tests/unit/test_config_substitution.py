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

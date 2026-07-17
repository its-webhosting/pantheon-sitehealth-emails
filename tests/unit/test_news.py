"""Unit tests for load_news_items() (P2 fix).

Before the fix, config-inline [News.<x>] sub-tables were never added: the loop tested
`isinstance(news_item_name, dict)` on a dict KEY (always a str), so the guard's `continue`
always fired and the add_news_item call was dead code.  load_news_items() now iterates the
[News] table's items() and skips non-dict VALUES (scalar directives such as `folder`).

reset_sc yields the script_context module; tests set sc.config directly.  sc.options is a
real parsed default namespace (reset_sc sets it), so sc.options.config is available.
"""
import pytest

pytestmark = pytest.mark.unit


def _item(message="Hello", type="info"):
    return {"type": type, "message": message}


def test_config_inline_items_are_added(psh, reset_sc, tmp_path):
    reset_sc.config = {
        "News": {
            "folder": str(tmp_path),  # empty dir -> scalar directive, must be skipped
            "one": _item("First"),
            "two": _item("Second"),
        }
    }
    psh.load_news_items()
    messages = [n["message"] for n in reset_sc.news]
    assert messages == ["First", "Second"]  # both dict sub-tables added, folder skipped


def test_folder_scalar_directive_is_skipped(psh, reset_sc, tmp_path):
    # Only the scalar `folder` directive, no sub-tables -> nothing added, no crash.
    reset_sc.config = {"News": {"folder": str(tmp_path)}}
    psh.load_news_items()
    assert reset_sc.news == []


def test_no_news_section_is_noop_not_crash(psh, reset_sc):
    # Latent-bug fix: the old folder glob ran outside the `if "News"` guard and would
    # KeyError when [News] was absent.  load_news_items() uses .get() -> clean no-op.
    reset_sc.config = {}
    psh.load_news_items()  # must not raise
    assert reset_sc.news == []


def test_disabled_inline_item_is_skipped(psh, reset_sc, tmp_path):
    # enabled = false disables an item.  This also covers the recursive
    # gate_disabled_sections() interaction: a gated [News.<x>] sub-table arrives here
    # stripped to {'enabled': False}, which must NOT hit add_news_item's
    # missing-"message" fatal.
    reset_sc.config = {
        "News": {
            "kept": _item("Kept"),
            "off": {"enabled": False},  # as stripped by gate_disabled_sections
            "off2": {"enabled": False, "type": "info", "message": "Never shown"},
        }
    }
    psh.load_news_items()
    assert [n["message"] for n in reset_sc.news] == ["Kept"]


def test_disabled_file_item_is_skipped(psh, reset_sc, tmp_path):
    (tmp_path / "a.toml").write_text(
        '[News.off]\nenabled = false\ntype = "info"\nmessage = "Never shown"\n'
        '[News.kept]\ntype = "info"\nmessage = "Kept"\n'
    )
    reset_sc.config = {"News": {"folder": str(tmp_path)}}
    psh.load_news_items()
    assert [n["message"] for n in reset_sc.news] == ["Kept"]


def test_enabled_true_item_is_kept(psh, reset_sc):
    reset_sc.config = {"News": {"on": {"enabled": True, "type": "info", "message": "Shown"}}}
    psh.load_news_items()
    assert [n["message"] for n in reset_sc.news] == ["Shown"]


def test_file_based_items_are_added(psh, reset_sc, tmp_path):
    (tmp_path / "a.toml").write_text(
        '[News.item]\ntype = "info"\nmessage = "From file"\n'
    )
    reset_sc.config = {"News": {"folder": str(tmp_path)}}
    psh.load_news_items()
    assert [n["message"] for n in reset_sc.news] == ["From file"]


def test_config_items_precede_file_items(psh, reset_sc, tmp_path):
    (tmp_path / "a.toml").write_text(
        '[News.item]\ntype = "info"\nmessage = "FILE"\n'
    )
    reset_sc.config = {
        "News": {"folder": str(tmp_path), "inline": _item("CONFIG")}
    }
    psh.load_news_items()
    assert [n["message"] for n in reset_sc.news] == ["CONFIG", "FILE"]


def test_item_missing_message_exits(psh, reset_sc, tmp_path):
    reset_sc.config = {
        "News": {"folder": str(tmp_path), "bad": {"type": "info"}}  # no message
    }
    with pytest.raises(SystemExit):
        psh.load_news_items()


def test_file_missing_news_key_exits(psh, reset_sc, tmp_path):
    (tmp_path / "a.toml").write_text('title = "no News table here"\n')
    reset_sc.config = {"News": {"folder": str(tmp_path)}}
    with pytest.raises(SystemExit):
        psh.load_news_items()


def test_folder_items_sorted_by_filename(psh, reset_sc, tmp_path):
    # Pin the within-folder sort order BEFORE the glob->Path.glob conversion (SPEC §New tests #4).
    # Files created in a non-lexical order; a dropped sorted() would surface OS readdir order.
    for name, msg in (("c.toml", "CCC"), ("a.toml", "AAA"), ("b.toml", "BBB")):
        (tmp_path / name).write_text(
            f'[News.item]\ntype = "info"\nmessage = "{msg}"\n'
        )
    reset_sc.config = {"News": {"folder": str(tmp_path)}}
    psh.load_news_items()
    assert [n["message"] for n in reset_sc.news] == ["AAA", "BBB", "CCC"]

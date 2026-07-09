"""Owner-facing HTML must be pure ASCII, using named entities for anything above U+007F.

A raw UTF-8 character in notice/report HTML is re-encoded as mojibake ("â€”") by any
consumer that mis-guesses the charset -- Emogrifier's libxml did exactly that until
email_template.html declared `charset=utf-8` (see tests/integration/test_css_inliner_encoding.py).
The charset declaration is the fix; this ASCII policy is the belt-and-braces, so a notice
survives a mis-declaring email client too.

Scope: string literals that can reach HTML, in the modules that build notices and report
sections.  Explicitly EXEMPT, because they never touch an HTML parser:

  * docstrings and comments (never rendered);
  * console/debug/log output -- it goes to a terminal, and rich already renders shortcodes
    like `:exclamation:` to non-ASCII glyphs, so an ASCII *source* rule buys nothing there
    (check/cloudflare/notices.py's `_CONSOLE` is its own dict, with its own ASCII test in
    test_cachecheck_consolidation.py, for terminal-encoding reasons rather than charset);
  * matplotlib labels -- rasterized into a PNG, with no charset exposure;
  * email_template.txt -- the plaintext alternative, written as UTF-8, where entities would
    be nonsense (it legitimately carries emoji);
  * plugin/ -- data sources and integrations; they build no owner-facing HTML.

Runtime values (URLs, cookie names, error strings) may legitimately be non-ASCII; they are
escaped, not policed.
"""
import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Modules that put HTML into a notice, a report section, or the template.
SOURCES = ["pantheon-sitehealth-emails", "script_context.py"]
SOURCES += sorted(str(p.relative_to(REPO_ROOT)) for p in (REPO_ROOT / "check").rglob("*.py"))

# Calls whose string arguments never reach an HTML parser.  A whole call subtree is exempt,
# so wrappers like `sc.debug(rich_escape(f"..."))` are covered.
_EXEMPT_CALLS = {
    "debug", "print", "log", "warn", "error", "update",          # console / status / logging
    "set_xlabel", "set_ylabel", "set_title", "suptitle", "legend",  # matplotlib
    "annotate", "text", "bar_label", "set_label",
}
# Module-level names whose assigned value is console text, not HTML.
_EXEMPT_ASSIGNMENTS = {"_CONSOLE"}


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _exempt_node_ids(tree) -> set:
    """ids of every node under a docstring, an exempt call, or an exempt assignment."""
    exempt = set()

    def mark(node):
        for child in ast.walk(node):
            exempt.add(id(child))

    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            first = node.body[0] if node.body else None
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                exempt.add(id(first.value))
        elif isinstance(node, ast.Call) and _call_name(node) in _EXEMPT_CALLS:
            mark(node)
        elif isinstance(node, ast.Assign):
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if names & _EXEMPT_ASSIGNMENTS:
                mark(node.value)
    return exempt


def _non_ascii_literals(source: str):
    """(line, text, offending chars) for each HTML-reachable literal with non-ASCII."""
    tree = ast.parse(source)
    exempt = _exempt_node_ids(tree)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in exempt and not node.value.isascii()):
            yield node.lineno, node.value, sorted({c for c in node.value if ord(c) > 127})


@pytest.mark.parametrize("source", SOURCES)
def test_no_raw_non_ascii_in_html_reachable_literals(source):
    found = list(_non_ascii_literals((REPO_ROOT / source).read_text(encoding="utf-8")))
    assert not found, "\n".join(
        f"{source}:{line}: {chars} in {text[:60]!r} -- use a named entity "
        f"(&mdash;, &middot;, ...) so the HTML survives a charset mis-guess"
        for line, text, chars in found)


def test_the_scan_catches_a_violation_and_honors_its_exemptions():
    # The policy is only as good as the scan.  It must flag a raw em dash in an
    # HTML-reachable literal...
    assert [chars for _line, _text, chars in _non_ascii_literals('x = "a — b"\n')] == [["—"]]
    # ...and must not flag one in a docstring, a comment, a console call (even wrapped),
    # or the _CONSOLE dict.
    for exempt in ('"""doc — dash"""\nx = 1  # — dash\n',
                   'sc.debug(f"still MISS — never cached")\n',
                   'sc.debug(rich_escape(f"still MISS — never cached"))\n',
                   'print("a — b")\n',
                   'ax.set_xlabel("Visitors — monthly")\n',
                   '_CONSOLE = {"miss-persistent": "still MISS — never cached"}\n'):
        assert not list(_non_ascii_literals(exempt)), exempt


def test_html_template_is_ascii():
    html = (REPO_ROOT / "email_template.html").read_text(encoding="utf-8")
    bad = sorted({c for c in html if ord(c) > 127})
    assert not bad, f"email_template.html has raw non-ASCII {bad}; use named entities"

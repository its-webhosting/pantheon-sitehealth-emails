#!/usr/bin/env python
"""I14c instrument: inventory every notice producer, and gate the conversion's completeness.

Run from the repo root:

    python development/2026-07-24-mod-I14c-notice/tools/notice_inventory.py            # table
    python development/2026-07-24-mod-I14c-notice/tools/notice_inventory.py --gate     # close gate

A "dict-form producer" is a dict literal carrying a "csv"/'csv' key in psh/, check/, plugin/
or script_context.py.  This finds them regardless of quote style -- a plain `grep '"csv":'`
does NOT (check/umich/sitelens.py:108 uses single quotes), which is why the SPEC's close gate
is this script and not a grep (SPEC section 4 instrument I3g; PD#14 -- an instrument that
cannot see one of the 37 things it certifies is a lying instrument).

--gate exits 1 unless exactly ONE dict-form producer remains: script_context.py's projection.
"""
import argparse
import ast
import pathlib
import sys

ROOTS = ("psh", "check", "plugin", "script_context.py")
SEVERITY_ICON = {  # script_context.icon, duplicated here deliberately: an instrument that
    "info": "&#x1F50E;",  # imported the map it is checking could not detect a change to it.
    "warning": "&#x26A0;",
    "alert": "&#x1F6A8;",
}


def python_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for root in ROOTS:
        path = pathlib.Path(root)
        files.extend([path] if path.is_file() else sorted(path.rglob("*.py")))
    return files


def format_string(node: ast.AST) -> str:
    """Render an f-string/BinOp csv expression back to readable source-ish text."""
    if isinstance(node, ast.Constant):
        return str(node.value)
    if isinstance(node, ast.JoinedStr):
        out = ""
        for part in node.values:
            out += str(part.value) if isinstance(part, ast.Constant) else "{" + ast.unparse(part) + "}"
        return out
    if isinstance(node, ast.BinOp):
        return format_string(node.left) + " + " + ast.unparse(node.right)
    return ast.unparse(node)


def producers() -> list[dict]:
    """Every dict-form notice producer, in file order."""
    found = []
    for path in python_files():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            pairs = {k.value: v for k, v in zip(node.keys, node.values, strict=False)
                     if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            if "csv" not in pairs:
                continue
            type_node = pairs.get("type")
            severity = str(type_node.value) if isinstance(type_node, ast.Constant) \
                else ast.unparse(type_node) if type_node is not None else "<missing>"
            icon_node = pairs.get("icon")
            if icon_node is None:
                icon = None
            elif isinstance(icon_node, ast.Constant):
                icon = icon_node.value
            else:
                icon = "<expr: " + ast.unparse(icon_node) + ">"
            found.append({
                "where": f"{path}:{node.lineno}",
                "severity": severity,
                "csv": format_string(pairs["csv"]),
                "icon": icon,
                "icon_is_default": icon is not None and icon == SEVERITY_ICON.get(severity),
                "own_text": "text" in pairs,
            })
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", action="store_true",
                        help="exit 1 unless only script_context.py's projection remains")
    args = parser.parse_args()

    found = producers()
    if args.gate:
        # BOTH halves of the contract, or the gate does not enforce what its docstring says:
        # a SECOND hand-built render dict inside script_context.py -- the single most likely
        # place for one, since that is where the projection lives -- would otherwise pass
        # silently (whole-branch review finding 4; the third defect in this instrument family).
        projection = [p for p in found if p["where"].startswith("script_context.py:")]
        remaining = [p for p in found if p not in projection]
        for producer in remaining:
            print(f"STILL A DICT PRODUCER: {producer['where']}  {producer['csv']}")
        print(f"dict-form producers outside script_context.py: {len(remaining)} (expected 0)")
        print(f"projection dicts in script_context.py: {len(projection)} (expected 1)")
        return 1 if remaining or len(projection) != 1 else 0

    for producer in found:
        icon = "derived" if producer["icon"] is None else (
            "default" if producer["icon_is_default"] else f"CUSTOM {producer['icon']}")
        print(f"{producer['where']}\t{producer['severity']}\t{producer['csv']}\t{icon}\t"
              f"{'own text' if producer['own_text'] else 'derived text'}")
    # script_context.py's projection is a notice dict too, but it is the CONSUMER of the
    # Notice type, not a producer -- count it separately so the SPEC's figures mean one thing.
    real = [p for p in found if not p["where"].startswith("script_context.py:")]
    with_icon = [p for p in real if p["icon"] is not None]
    default_icons = [p for p in with_icon if p["icon_is_default"]]
    # Field counting ignores commas inside {...} placeholders (json.dumps(...).replace(',', ...)
    # embeds one), so a two-field csv is one whose text outside the braces has a single comma.
    def field_count(csv: str) -> int:
        depth, commas = 0, 0
        for char in csv:
            depth += (char == "{") - (char == "}")
            commas += (char == "," and depth == 0)
        return commas + 1
    two_field = [p for p in real if field_count(p["csv"]) == 2]
    print(f"\nproducers: {len(real)} (+1 projection in script_context.py)   "
          f"explicit icon: {len(with_icon)}   "
          f"of which equal to the severity default: {len(default_icons)}   "
          f"two-field csv: {len(two_field)}   extra-field csv: {len(real) - len(two_field)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

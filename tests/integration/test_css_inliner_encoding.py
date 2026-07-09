"""The `php inline-styles.php` CSS-inlining step must not mangle non-ASCII characters.

Emogrifier parses with libxml, which assumes ISO-8859-1 unless the document declares a
charset -- and Emogrifier's own <meta charset> injection is suppressed by a Content-Type
meta tag that lacks one.  A UTF-8 em dash (E2 80 94) was therefore read as three Latin-1
characters and re-emitted as `&acirc;&#128;&#148;`, which Gmail renders as "â€”".  This is
the regression test for that (real, reported) bug.

Two independent defenses, each tested here: email_template.html declares `charset=utf-8`,
AND inline-styles.php normalizes non-ASCII to numeric entities before parsing, so no future
caller can reintroduce the bug by omitting the meta.
"""
import html as html_module
import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


_NUMERIC_REF = re.compile(r"&#(?:x([0-9a-fA-F]+)|(\d+));")


def _assert_no_mojibake(out: str, label: str) -> None:
    """Mojibake is detected by what it always produces, not by guessing at markers.

    Reading UTF-8 as Latin-1 maps the continuation bytes (0x80-0xBF) to U+0080-U+00BF, so
    every multi-byte character yields at least one C1 control (U+0080-U+009F): an em dash
    (E2 80 94) becomes "â" + U+0080 + U+0094, which Emogrifier escapes as
    `&acirc;&#128;&#148;`.  C1 controls never occur in valid text, so they are an exact
    signature.  Substring markers would be wrong in BOTH directions -- a legitimate "â" is
    also emitted as `&acirc;`, so that marker false-fails on French "âme".

    The output is scanned RAW, plus its numeric references decoded by hand.  html.unescape()
    must not be used here: per the HTML5 spec it remaps numeric refs in the C1 range through
    cp1252 (`&#128;` -> U+20AC EUR), erasing the very signature we are looking for -- which
    is also exactly why a reader sees "â€”" in Gmail rather than the raw controls.
    """
    offenders = {f"U+{ord(c):04X}" for c in out if 0x80 <= ord(c) <= 0x9F}
    for hex_ref, dec_ref in _NUMERIC_REF.findall(out):
        value = int(hex_ref, 16) if hex_ref else int(dec_ref)
        if 0x80 <= value <= 0x9F:
            offenders.add(f"&#{value};")
    assert not offenders, (f"{label!r} -> mojibake: C1 controls "
                           f"{sorted(offenders)} in {out[:200]!r}")


def _inline(tmp_path, html: str) -> str:
    infile, outfile = tmp_path / "in.html", tmp_path / "out.html"
    infile.write_text(html, encoding="utf-8")
    subprocess.run(["php", str(REPO_ROOT / "inline-styles.php"), str(infile), str(outfile)],
                   check=True, cwd=REPO_ROOT)
    return outfile.read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _require_php():
    if shutil.which("php") is None:
        pytest.skip("php not on PATH")


def test_the_mojibake_detector_actually_fires():
    # Otherwise every assertion above could pass vacuously.  Both forms are what Emogrifier
    # really emitted for an em dash before the fix: escaped, and the same characters raw.
    for real_mojibake in ("caching &acirc;&#128;&#148; defeated",
                          "caching â defeated"):
        with pytest.raises(AssertionError, match="C1 controls"):
            _assert_no_mojibake(real_mojibake, "probe")
    # ...and does not fire on legitimate accents, entities, or emoji.
    for clean in ("âme Âtre São", "a &mdash; b", "café", "🎯 ✅", "&acirc;me"):
        _assert_no_mojibake(clean, "probe")


def test_template_declares_utf8_so_libxml_does_not_guess():
    head = (REPO_ROOT / "email_template.html").read_text(encoding="utf-8")[:600]
    assert "charset=utf-8" in head.lower()


CASES = [
    ("a &mdash; b", "—"),          # the entity the cache-check notices emit
    ("a &middot; b", "·"),         # the doc-link separator
    ("a — b", "—"),                # a raw em dash, should any future notice use one
    ("caf&eacute;", "café"),
    ("naïve résumé", "naïve résumé"),
    ("âme Âtre São", "âme Âtre São"),  # bare â/Â/Ã are legitimate letters, not mojibake
    ("emoji 🎯 ✅", "emoji 🎯 ✅"),      # astral plane, as email_template.txt uses
]


@pytest.mark.parametrize("markup, expected", CASES)
def test_inliner_preserves_characters_with_a_charset(tmp_path, markup, expected):
    html = ('<!DOCTYPE html><html lang="en"><head>'
            '<META http-equiv="Content-Type" content="text/html; charset=utf-8">'
            f'<title>t</title></head><body><p>{markup}</p></body></html>')
    out = _inline(tmp_path, html)
    _assert_no_mojibake(out, markup)
    assert expected in html_module.unescape(out)


@pytest.mark.parametrize("markup, expected", CASES)
def test_inliner_preserves_characters_without_a_charset(tmp_path, markup, expected):
    # inline-styles.php normalizes non-ASCII to numeric entities before handing the
    # document to Emogrifier, so a caller that forgets the charset meta -- the original
    # bug -- can no longer produce mojibake.  html.unescape() reverses the entities the
    # way any HTML consumer (browser, email client, html2text) does.
    html = ('<!DOCTYPE html><html lang="en"><head>'
            '<META http-equiv="Content-Type" content="text/html;">'
            f'<title>t</title></head><body><p>{markup}</p></body></html>')
    out = _inline(tmp_path, html)
    _assert_no_mojibake(out, markup)
    assert expected in html_module.unescape(out)


def test_xml_prolog_never_leaks_into_the_output(tmp_path):
    # A tempting alternative fix (prepending `<?xml encoding="utf-8">`) leaves a stray
    # processing instruction in the emailed HTML.  Ours must not.
    html = ('<!DOCTYPE html><html lang="en"><head>'
            '<META http-equiv="Content-Type" content="text/html;">'
            '<title>t</title></head><body><p>a — b</p></body></html>')
    assert "<?xml" not in _inline(tmp_path, html)


def test_css_inlining_still_works(tmp_path):
    html = ('<!DOCTYPE html><html lang="en"><head><title>t</title>'
            '<style>p { color: red; }</style></head><body><p>x</p></body></html>')
    assert 'style="color: red;"' in _inline(tmp_path, html)

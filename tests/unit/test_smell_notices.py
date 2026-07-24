"""build_smell_notices unit tests (campaign I1, SPEC F1).

Repointed at campaign I14c: the builder returns Notice objects, so the reads are
`.code`/`.csv_extra`/`.html`/`.text` instead of the render dict's subscripts.  The asserted
VALUES are unchanged -- the site-name half of the csv row now comes from the SiteContext at
projection time (SPEC I14c §2.2), pinned by tests/unit/test_add_notice_from_notice.py.
"""
import json

import pytest

pytestmark = pytest.mark.unit


def test_no_smells_returns_empty_list(psh):
    assert psh.build_smell_notices("s", "", "", "") == []


def test_wp_smell_alone(psh):
    (n,) = psh.build_smell_notices("s", "wp broke", "", "")
    assert n.code == "wp-smell"
    assert n.csv_extra == (json.dumps("wp broke").replace(",", "\\,"),)
    assert "wp broke" in n.html and "wp broke" in n.text


def test_drush_smell_alone(psh):
    (n,) = psh.build_smell_notices("s", "", "drush broke", "")
    assert n.code == "drush-smell"
    assert n.csv_extra == (json.dumps("drush broke").replace(",", "\\,"),)
    assert "drush broke" in n.html and "drush broke" in n.text


def test_composer_smell_alone_is_reported(psh):
    # RED pre-fix: the composer block was nested inside the drush check, so a composer
    # smell without a drush smell was silently dropped.
    (n,) = psh.build_smell_notices("s", "", "", "composer broke")
    assert n.code == "composer-smell"
    assert n.csv_extra == (json.dumps("composer broke").replace(",", "\\,"),)


@pytest.mark.parametrize(("wp", "drush", "composer", "expected"), [
    ("a, b\nc", "", "", '"a\\, b\\nc"'),
    ("", "d, e", "", '"d\\, e"'),
    ("", "", "f, g", '"f\\, g"'),
])
def test_smell_csv_field_escapes_embedded_commas(psh, wp, drush, composer, expected):
    # The json.dumps(...).replace(",", "\\,") escaping is what keeps a multi-line stderr
    # containing commas inside ONE csv field; csv_extra carries it verbatim.  All THREE
    # builders carry their own copy of the expression, so all three are pinned against a
    # comma-bearing input -- a comma-free one makes the .replace a no-op and the assertion
    # unable to go red (Task-2 review finding 3).
    (n,) = psh.build_smell_notices("s", wp, drush, composer)
    assert n.csv_extra == (expected,)


def test_composer_html_interpolates_composer_not_drush(psh):
    # RED pre-fix: the composer html body interpolated {drush_smell}.
    notices = psh.build_smell_notices("s", "", "drush text", "composer text")
    composer = next(n for n in notices if n.code == "composer-smell")
    assert "composer text" in composer.html
    assert "drush text" not in composer.html


def test_all_three_in_emission_order(psh):
    notices = psh.build_smell_notices("s", "w", "d", "c")
    assert [n.code for n in notices] == ["wp-smell", "drush-smell", "composer-smell"]


def test_composer_literals_are_column_zero_like_siblings(psh):
    # D-i10-8 (LEDGER I1 Obs. 4): the composer message/text literals carried 8 spaces of
    # accidental leading indentation on every interior line -- the wp/drush siblings are
    # column-0.  RED on the pre-move builder (psh/_legacy.py) before the D-i10-8 de-indent.
    notices = psh.build_smell_notices("s", "", "d", "c")
    _drush, composer = notices
    assert not composer.html.startswith("\n        ")
    assert composer.html.splitlines()[1].startswith("<p>The <code>composer</code>")
    assert composer.text.splitlines()[1].startswith('The "composer" command')

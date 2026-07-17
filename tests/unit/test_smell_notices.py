"""build_smell_notices unit tests (campaign I1, SPEC F1)."""
import pytest

pytestmark = pytest.mark.unit


def test_no_smells_returns_empty_list(psh):
    assert psh.build_smell_notices("s", "", "", "") == []


def test_wp_smell_alone(psh):
    (n,) = psh.build_smell_notices("s", "wp broke", "", "")
    assert n["csv"].startswith("s,wp-smell,")
    assert "wp broke" in n["message"] and "wp broke" in n["text"]


def test_drush_smell_alone(psh):
    (n,) = psh.build_smell_notices("s", "", "drush broke", "")
    assert n["csv"].startswith("s,drush-smell,")
    assert "drush broke" in n["message"] and "drush broke" in n["text"]


def test_composer_smell_alone_is_reported(psh):
    # RED pre-fix: the composer block was nested inside the drush check, so a composer
    # smell without a drush smell was silently dropped.
    (n,) = psh.build_smell_notices("s", "", "", "composer broke")
    assert n["csv"].startswith("s,composer-smell,")


def test_composer_html_interpolates_composer_not_drush(psh):
    # RED pre-fix: the composer html body interpolated {drush_smell}.
    notices = psh.build_smell_notices("s", "", "drush text", "composer text")
    composer = [n for n in notices if n["csv"].startswith("s,composer-smell,")][0]
    assert "composer text" in composer["message"]
    assert "drush text" not in composer["message"]


def test_all_three_in_emission_order(psh):
    notices = psh.build_smell_notices("s", "w", "d", "c")
    codes = [n["csv"].split(",")[1] for n in notices]
    assert codes == ["wp-smell", "drush-smell", "composer-smell"]

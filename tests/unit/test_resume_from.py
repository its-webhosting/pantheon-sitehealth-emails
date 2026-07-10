"""Unit tests for the --resume-from pure helpers.

`--all` is banned inside the subprocess safety interlock, so the happy-path resume logic can
only be exercised in-process, through the two pure helpers it was extracted into:
`sites_from_resume_point` (which suffix of the sorted site list to process) and
`merge_prior_results` (how the resumed run's -results.json accumulates).
"""
import json

import pytest
from hypothesis import given, strategies as st

pytestmark = pytest.mark.unit

SITES = ["aaum-alumni", "advance-program", "its-wws-test1", "its-wws-test2", "zzz-last"]


# ── sites_from_resume_point ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("index", range(len(SITES)))
def test_returns_inclusive_suffix(psh, index):
    result = psh.sites_from_resume_point(SITES, SITES[index])
    assert result == SITES[index:]
    assert result[0] == SITES[index]


def test_unknown_site_raises(psh):
    with pytest.raises(psh.ResumeSiteNotFoundError):
        psh.sites_from_resume_point(SITES, "no-such-site")


def test_empty_list_raises(psh):
    # An org with zero eligible sites has nothing to resume from; that is fatal, not a no-op.
    with pytest.raises(psh.ResumeSiteNotFoundError):
        psh.sites_from_resume_point([], "its-wws-test1")


@given(names=st.lists(st.text(min_size=1), min_size=1, unique=True), i=st.integers(min_value=0))
def test_suffix_property(psh, names, i):
    names = sorted(names)
    resume_from = names[i % len(names)]
    result = psh.sites_from_resume_point(names, resume_from)

    assert result[0] == resume_from
    assert names[names.index(resume_from) :] == result  # contiguous suffix, order preserved
    assert set(result) <= set(names)


# ── merge_prior_results ──────────────────────────────────────────────────────────────
def test_merge_missing_file(psh, tmp_path):
    path = tmp_path / "20260709-results.json"
    assert psh.merge_prior_results(str(path), {"a": 1}) == {"a": 1}


def test_merge_unions_with_new_winning(psh, tmp_path):
    path = tmp_path / "20260709-results.json"
    path.write_text(json.dumps({"a": "old", "b": "kept"}), encoding="utf-8")

    merged = psh.merge_prior_results(str(path), {"a": "new", "c": "added"})
    assert merged == {"a": "new", "b": "kept", "c": "added"}


def test_merge_malformed_file_warns_and_keeps_new(psh, tmp_path, capsys):
    path = tmp_path / "20260709-results.json"
    path.write_text("{not json", encoding="utf-8")

    merged = psh.merge_prior_results(str(path), {"a": 1})
    assert merged == {"a": 1}
    assert "could not read existing" in capsys.readouterr().out

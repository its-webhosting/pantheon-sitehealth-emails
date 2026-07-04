"""Property tier: Hypothesis over a pure/deterministic helper (SPEC §9 `property`, §5.10).

Proves the Hypothesis wiring and exercises fix_drush_output across generated inputs.
"""
import pytest
from hypothesis import given
from hypothesis import strategies as st

pytestmark = pytest.mark.unit


@given(output=st.text(), errors=st.text())
def test_fix_drush_output_returns_two_strings(psh, output, errors):
    out, err = psh.fix_drush_output(output, errors)
    assert isinstance(out, str)
    assert isinstance(err, str)


@given(output=st.text(), errors=st.text())
def test_fix_drush_output_is_idempotent(psh, output, errors):
    once = psh.fix_drush_output(output, errors)
    twice = psh.fix_drush_output(*once)
    # A second pass never moves more lines: the output half is stable.
    assert twice[0] == once[0]


@given(
    noise=st.lists(
        st.text(alphabet=st.characters(blacklist_characters="{\n"), min_size=1),
        min_size=1,
        max_size=4,
    ),
    body=st.text(),
)
def test_leading_noise_is_moved_to_errors(psh, noise, body):
    # Non-JSON lines before the JSON body must be split off into errors; the JSON survives
    # as output. This exercises the branch the old test named but never reached.
    payload = "\n".join(noise) + '\n{"k": ' + repr(body) + "}"
    out, err = psh.fix_drush_output(payload, "")
    assert out.startswith("{")
    for line in noise:
        assert line in err

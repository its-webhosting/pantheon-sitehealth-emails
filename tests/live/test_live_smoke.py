"""Live tier: real Terminus, read-only, no shim (SPEC §9 `live`, live-first decision).

Catches Terminus/Pantheon API drift and auth breakage that mocked tiers structurally
cannot.  Off in `--fast` (marked live+slow); never uses --all/--for-real.
"""
import pytest

pytestmark = [pytest.mark.live, pytest.mark.slow]


def test_real_terminus_self_info_parses(psh):
    # Uses the program's own terminus() wrapper against the real binary (the shim is NOT
    # on PATH in-process), proving auth + subprocess + JSON parse end to end.
    info = psh.terminus("self:info")
    assert isinstance(info, dict) and info, f"unexpected self:info result: {info!r}"


def test_real_read_only_site_info(psh):
    info = psh.terminus("site:info", "its-wws-test1")
    assert isinstance(info, dict)
    assert info.get("name") == "its-wws-test1"
    assert info.get("framework", "").startswith("wordpress")

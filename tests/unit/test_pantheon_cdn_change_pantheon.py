import pytest

from helpers.checkload import load_check_module
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.unit


# Verbatim shape of `terminus domain:dns bus-occb.live --format=json` (verified 2026-07-12).
OCCB_ROWS = [
    {"domain": "occb.bus.umich.edu", "type": "A", "value": "23.185.0.4",
     "detected_value": "", "status": "action_required",
     "status_message": "Add this required record"},
    {"domain": "occb.bus.umich.edu", "type": "AAAA", "value": "2620:12a:8000::4",
     "detected_value": "", "status": "action_required",
     "status_message": "Add this required record"},
    {"domain": "occb.bus.umich.edu", "type": "AAAA", "value": "2620:12a:8001::4",
     "detected_value": "", "status": "action_required",
     "status_message": "Add this required record"},
    {"domain": "occb.bus.umich.edu", "type": "CNAME", "value": "",
     "detected_value": "live-bus-occb.pantheonsite.io", "status": "action_required",
     "status_message": "Remove this detected record"},
]

# An already-migrated site (its-wws-test1, verified live): CNAME only, NO A/AAAA rows.
MIGRATED_ROWS = [
    {"domain": "wws-test1.cdn-dev.it.umich.edu", "type": "CNAME",
     "value": "fe.cfp2c.edge.pantheon.io", "detected_value": "fe.cfp2c.edge.pantheon.io",
     "status": "okay", "status_message": "Correct value detected"},
]


@pytest.fixture
def pantheon(psh, reset_sc, request):
    return load_check_module(
        psh, "pantheon_cdn_change", "pantheon", "pcc_pantheon_probe", request)


@pytest.fixture
def chain(psh, reset_sc, request):
    return load_check_module(
        psh, "pantheon_cdn_change", "chain", "pcc_pantheon_chain_probe", request)


def _fake_terminus(reset_sc, monkeypatch, result, errors="", fatal=False, calls=None):
    def _terminus(*args):
        if calls is not None:
            calls.append(args)
        return result, errors, fatal
    monkeypatch.setattr(reset_sc, "terminus", _terminus)


def test_parses_required_a_and_aaaa(pantheon, reset_sc, monkeypatch):
    calls = []
    _fake_terminus(reset_sc, monkeypatch, OCCB_ROWS, calls=calls)
    # In production site_id is a UUID; the call shape is what matters here.
    out = pantheon.required_records("9cf2c790-c7b8-4f2f-a6f1-27385b8f958e", "bus-occb")
    assert calls == [("domain:dns", "9cf2c790-c7b8-4f2f-a6f1-27385b8f958e.live")]  # LIVE env
    assert out == {"occb.bus.umich.edu": pantheon.Required(
        ["23.185.0.4"], ["2620:12a:8000::4", "2620:12a:8001::4"], [])}


def test_valueless_remove_rows_are_skipped(pantheon, reset_sc, monkeypatch):
    _fake_terminus(reset_sc, monkeypatch, OCCB_ROWS)
    out = pantheon.required_records("s", "s")
    # The "Remove this detected record" CNAME row has an empty `value` -- no requirement.
    assert out["occb.bus.umich.edu"].cname == []
    assert "live-bus-occb.pantheonsite.io" not in str(out)


def test_cname_only_answer_is_kept(pantheon, reset_sc, monkeypatch):
    # F14: an already-migrated site.  This is an ANSWER, not a failure -- it must NOT come back
    # as {} (which is what a terminus failure returns) and must NOT render as "unavailable".
    _fake_terminus(reset_sc, monkeypatch, MIGRATED_ROWS)
    out = pantheon.required_records("s", "its-wws-test1")
    got = out["wws-test1.cdn-dev.it.umich.edu"]
    assert got.a == [] and got.aaaa == []
    assert got.cname == ["fe.cfp2c.edge.pantheon.io"]
    assert got != pantheon.EMPTY               # distinguishable from "no answer at all"


def test_multiple_domains_per_site(pantheon, reset_sc, monkeypatch):
    rows = [
        {"domain": "backstage.its.umich.edu", "type": "A", "value": "23.185.0.2"},
        {"domain": "news.backstage.its.umich.edu", "type": "A", "value": "23.185.0.2"},
        {"domain": "news.backstage.its.umich.edu", "type": "AAAA", "value": "2620:12a:8000::2"},
    ]
    _fake_terminus(reset_sc, monkeypatch, rows)
    out = pantheon.required_records("s", "its-backstage")
    assert set(out) == {"backstage.its.umich.edu", "news.backstage.its.umich.edu"}
    assert out["news.backstage.its.umich.edu"].aaaa == ["2620:12a:8000::2"]


def test_order_is_pantheons_order_not_ours(pantheon, reset_sc, monkeypatch):
    # Records are NEVER re-sorted: a sort key over remote strings (ipaddress.ip_address) would
    # raise on garbage.  Pantheon's order is already deterministic.
    rows = [
        {"domain": "x.example.org", "type": "AAAA", "value": "2620:12a:8001::4"},
        {"domain": "x.example.org", "type": "AAAA", "value": "2620:12a:8000::4"},
    ]
    _fake_terminus(reset_sc, monkeypatch, rows)
    assert pantheon.required_records("s", "s")["x.example.org"].aaaa == [
        "2620:12a:8001::4", "2620:12a:8000::4"]


@pytest.mark.parametrize(
    "result,fatal",
    [(None, True), (None, False), ("not a list", False), ([{"junk": 1}], False)],
    ids=["fatal", "undecodable", "wrong-type", "malformed-rows"])
def test_failure_yields_empty_map_and_never_raises(
        pantheon, reset_sc, monkeypatch, result, fatal):
    # F4: domain:dns is an ENRICHMENT call.  Its failure must never abort the site -- the
    # findings are still reported, with the records rendered "unavailable".
    console = recording_console(monkeypatch, reset_sc)
    _fake_terminus(reset_sc, monkeypatch, result, errors="boom", fatal=fatal)
    assert pantheon.required_records("9cf2c790-c7b8-4f2f-a6f1-27385b8f958e", "bus-occb") == {}
    if fatal or not isinstance(result, list):
        out = console.export_text()
        assert "ATTENTION" in out
        assert "bus-occb" in out                    # the NAME, never the UUID
        assert "9cf2c790" not in out


@pytest.mark.parametrize(
    "rows",
    [[], [{"junk": 1}], [{"domain": "occb.bus.umich.edu", "type": "A", "value": ""}]],
    ids=["empty-list", "unrecognized-shape", "every-value-empty"])
def test_a_successful_call_with_no_usable_rows_is_announced(
        pantheon, reset_sc, monkeypatch, rows):
    # The gap this closes: the call SUCCEEDS (not fatal, result is a list), so none of the three
    # failure guards fire -- but nothing parses, so {} comes back.  The caller cannot tell that {}
    # apart from "the call failed", so its per-domain warning stays quiet too.  Left unannounced,
    # every affected owner is emailed "unavailable" while the run reports success and the operator
    # sees nothing at all.
    console = recording_console(monkeypatch, reset_sc)
    monkeypatch.setattr(reset_sc, "terminus", lambda *args: (rows, "", False))
    assert pantheon.required_records("9cf2c790-uuid", "bus-occb") == {}
    out = console.export_text()
    assert "ATTENTION" in out
    assert "no usable records" in out
    assert "bus-occb" in out                        # the NAME, never the UUID
    assert "9cf2c790" not in out


def test_a_usable_answer_is_not_announced_as_empty(pantheon, reset_sc, monkeypatch):
    # The negative half: a normal answer must NOT trip the "no usable records" warning.
    console = recording_console(monkeypatch, reset_sc)
    monkeypatch.setattr(reset_sc, "terminus", lambda *args: (OCCB_ROWS, "", False))
    assert pantheon.required_records("uuid", "bus-occb")
    assert "no usable records" not in console.export_text()


def test_null_value_row_produces_no_entry(pantheon, reset_sc, monkeypatch):
    # A JSON `null` value must be treated as ABSENT, not stringified into the literal "None" --
    # str(None) == "None" would otherwise pass the truthiness check and get published as a
    # fabricated record value.
    rows = [
        {"domain": "x.example.org", "type": "A", "value": None},
        {"domain": "x.example.org", "type": "AAAA", "value": "2620:12a:8000::4"},
    ]
    _fake_terminus(reset_sc, monkeypatch, rows)
    out = pantheon.required_records("s", "s")
    assert out == {"x.example.org": pantheon.Required([], ["2620:12a:8000::4"], [])}
    assert "None" not in str(out)


def test_null_domain_row_produces_no_entry(pantheon, reset_sc, monkeypatch):
    # A JSON `null` domain must be treated as ABSENT, not stringified into the literal "None" --
    # str(None) == "None" would otherwise pass the truthiness check and get published as a
    # fabricated domain key.
    rows = [{"domain": None, "type": "A", "value": "23.185.0.4"}]
    _fake_terminus(reset_sc, monkeypatch, rows)
    out = pantheon.required_records("s", "s")
    assert out == {}
    assert "none" not in str(out).lower()


def test_normalization_matches_chain_normalize(pantheon, chain, reset_sc, monkeypatch):
    # detect.py (a later task) looks these keys up with chain.normalize(fqdn) -- the two MUST
    # agree, so pantheon.py must not reimplement normalization inline.
    rows = [{"domain": "OCCB.Bus.UMich.edu.", "type": "A", "value": "23.185.0.4"}]
    _fake_terminus(reset_sc, monkeypatch, rows)
    out = pantheon.required_records("s", "s")
    key = chain.normalize("OCCB.Bus.UMich.edu.")
    assert key == "occb.bus.umich.edu"
    assert key in out
    assert out[key].a == ["23.185.0.4"]


def test_empty_carries_the_same_field_types_as_a_real_answer(pantheon):
    # EMPTY is the "Pantheon said nothing about this domain" answer (F4), which the notice renders
    # as "unavailable".  Its fields MUST be lists like every other Required: the renderer and the
    # tests both compare `finding.a == []`, and a tuple here would make that false for exactly the
    # case that needs the special rendering.  (EMPTY is shared, so it is read-only by contract.)
    assert pantheon.EMPTY == pantheon.Required([], [], [])
    assert all(isinstance(field, list) for field in pantheon.EMPTY)

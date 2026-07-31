"""Offline tests for the find-platform-domains-cloudflare utility (SPEC section 7).

The script has no .py extension, so it is loaded with the SourceFileLoader idiom the suite
already uses for standalone scripts and check/plugin modules (see
tests/unit/test_find_platform_domains_dns.py).  It is loaded FRESH PER TEST so no module-level
state leaks between tests -- which is also what makes monkeypatching module attributes safe in
the main() tests at the bottom (SPEC section 4, seams).

Imports: each task ADDS to the block below, in the task that first needs the name.  Editing the
top block is fine; adding an import further down the file is what ruff's E402 forbids, and E402
is not in the tests/** ignore list.

TEMPORARY, deleted with the script after the Pantheon CDN migration -- see
development/2026-07-30-platform-domain-util2/SPEC.md section 11.
"""
import contextlib
import datetime
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import types
from importlib.machinery import SourceFileLoader
from pathlib import Path

import dns.resolver
import pytest

pytestmark = pytest.mark.unit

SCRIPT = Path(__file__).resolve().parent.parent.parent / "find-platform-domains-cloudflare"


@pytest.fixture
def fpc():
    """The utility, loaded fresh.  Its entry point is __main__-guarded, so import runs nothing."""
    loader = SourceFileLoader("find_platform_domains_cloudflare_probe", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _refuse_real_dns(fpc, monkeypatch):
    """SPEC section 7: "NOTHING in the suite may touch real DNS."  Since Task 4 wired resolution
    into main(), any test driving main() with a non-empty, non-ambiguous sweep reaches this seam
    -- and a test that forgets fake_dns(...) was passing silently against the REAL network in this
    sandbox (task 4 review, finding 1), because "resolve to whatever the network answers" happened
    to satisfy assertions that don't care about the resolution outcome (interrupt-message wording,
    stream-doomedness, etc.).  Default `resolve` to a stub that fails LOUDLY instead, closing the
    whole class of "forgot fake_dns" defects at once rather than patching found instances one at a
    time (PD#14: an instrument that can pass by accident is not evidence).  A test that legitimately
    needs an answer opts in via fake_dns(fpc, monkeypatch, ...), which monkeypatches over this
    default the same way any other override would.

    READING THE FAILURE: since the whole-branch review added main()'s last line of defence
    (finding 2), a test driving main() no longer sees this AssertionError propagate -- main()
    catches it, names it on stderr and returns 2.  So the top-line failure is an unexpected
    `2` from main(), and the sentence naming the missing fake_dns is in pytest's "Captured
    stderr call" section.  Verified after that change: the message still reaches the report.
    """
    def refuse(hostname, rrtype):
        raise AssertionError(
            f"real DNS seam reached for ({hostname!r}, {rrtype!r}) -- this test is missing "
            "fake_dns(fpc, monkeypatch, ...) (SPEC section 7 forbids touching real DNS)")
    monkeypatch.setattr(fpc, "resolve", refuse)


def record(**overrides):
    """A stand-in for a cloudflare RecordResponse; the code under test only reads attributes."""
    fields = {"type": "CNAME", "name": "www.example.edu", "id": "rec-1",
              "content": "live-umich-example1.pantheonsite.io", "proxied": True,
              "ttl": 1, "comment": None, "tags": [], "settings": None}
    fields.update(overrides)
    return types.SimpleNamespace(**fields)


# --- Task 1: the match rule ------------------------------------------------------------------

def test_normalize_strips_case_whitespace_and_the_root_dot(fpc):
    assert fpc.normalize("  LIVE-Umich-X.PantheonSite.IO.  ") == "live-umich-x.pantheonsite.io"


@pytest.mark.parametrize("name", [
    "live-umich-example1.pantheonsite.io",
    "LIVE-UMICH-EXAMPLE1.PANTHEONSITE.IO",
    "live-umich-example1.pantheonsite.io.",
])
def test_is_platform_domain_accepts_platform_hostnames(fpc, name):
    assert fpc.is_platform_domain(name) is True


@pytest.mark.parametrize("name", [
    "notpantheonsite.io",          # the leading dot in PLATFORM_SUFFIX is what rejects this
    "pantheonsite.io",             # the bare apex is not a site's platform domain
    "www.example.edu",
    "live-umich-example1.pantheonsite.io.evil.example",
])
def test_is_platform_domain_rejects_everything_else(fpc, name):
    assert fpc.is_platform_domain(name) is False


# --- Task 2: credentials ---------------------------------------------------------------------

AMBIENT_CLOUDFLARE_VARS = {
    "CLOUDFLARE_API_TOKEN": "ambient-token",
    "CLOUDFLARE_API_KEY": "ambient-key",
    "CLOUDFLARE_EMAIL": "ambient@example.edu",
    "CLOUDFLARE_API_USER_SERVICE_KEY": "ambient-usk",
    "CLOUDFLARE_BASE_URL": "https://evil.example/v4",
    "CLOUDFLARE_CUSTOM_HEADERS": "X-Auth-Email: attacker@evil.example\nX-Auth-Key: evil-key",
}


def write_config(tmp_path, body):
    """A config file containing just a [Cloudflare] table."""
    path = tmp_path / "config.toml"
    path.write_text(f"[Cloudflare]\n{body}\n")
    return str(path)


def sent_request(client):
    """The request the SDK would actually send.  Offline: _build_request performs no I/O."""
    from cloudflare._models import FinalRequestOptions
    return client._build_request(FinalRequestOptions(method="get", url="/zones"))


def test_resolve_config_value_passes_literals_and_non_strings_through(fpc):
    assert fpc.resolve_config_value("plain-literal", "where") == "plain-literal"
    assert fpc.resolve_config_value(True, "where") is True
    assert fpc.resolve_config_value(None, "where") is None


@pytest.mark.parametrize("marker", ["<{env CF_TEST_VAR}", "<{secret env CF_TEST_VAR}"])
def test_resolve_config_value_reads_the_environment(fpc, monkeypatch, marker):
    monkeypatch.setenv("CF_TEST_VAR", "from-the-environment")
    assert fpc.resolve_config_value(marker, "where") == "from-the-environment"


def test_resolve_config_value_substitutes_inside_a_larger_string(fpc, monkeypatch):
    monkeypatch.setenv("CF_TEST_VAR", "middle")
    assert fpc.resolve_config_value("a<{env CF_TEST_VAR}z", "where") == "amiddlez"


def test_resolve_config_value_uses_the_default_when_the_variable_is_unset(fpc, monkeypatch):
    monkeypatch.delenv("CF_TEST_VAR", raising=False)
    assert fpc.resolve_config_value("<{secret env CF_TEST_VAR fallback}", "where") == "fallback"


def test_resolve_config_value_reports_an_unset_variable_with_no_default(fpc, monkeypatch):
    monkeypatch.delenv("CF_TEST_VAR", raising=False)
    with pytest.raises(fpc.StartupError) as caught:
        fpc.resolve_config_value("<{env CF_TEST_VAR}", "config.toml [Cloudflare].api_key")
    assert "CF_TEST_VAR" in str(caught.value)
    assert "config.toml [Cloudflare].api_key" in str(caught.value)


def test_resolve_config_value_rejects_a_substitution_it_cannot_resolve(fpc):
    with pytest.raises(fpc.StartupError) as caught:
        fpc.resolve_config_value("<{secret aws cloudflare/token}", "where")
    assert "secret aws" in str(caught.value)
    # The rest of the body is withheld on purpose: an <{env NAME DEFAULT} default can be a
    # literal credential, and this message reaches stderr and any operator log.
    assert "cloudflare/token" not in str(caught.value)


def test_resolve_config_value_names_a_malformed_substitution(fpc):
    """An unbalanced quote makes shlex raise ValueError, which escaped as a raw traceback at
    exit 1 -- a code SPEC section R6 does not use (adversarial review round 1, finding 3)."""
    with pytest.raises(fpc.StartupError) as caught:
        fpc.resolve_config_value("<{env FOO don't}", "config.toml [Cloudflare].api_key")
    assert "config.toml [Cloudflare].api_key" in str(caught.value)


def test_cloudflare_client_prefers_the_api_token(fpc, tmp_path, monkeypatch):
    monkeypatch.setenv("CF_TEST_TOKEN", "tok-123")
    path = write_config(tmp_path, 'api_token = "<{secret env CF_TEST_TOKEN}"\n'
                                  'email = "someone@example.edu"\napi_key = "k-456"')
    client = fpc.cloudflare_client(path)
    assert client.api_token == "tok-123"


def test_cloudflare_client_sends_only_the_configured_credential(fpc, tmp_path, monkeypatch):
    """SPEC R2a, asserted as the security property rather than the attribute state implementing it.

    The SDK reads six ambient variables; ALL of them are exported here, so a regression that
    dropped any one field from the pin goes red.  Measured against cloudflare 5.4.0; an SDK that
    captured credentials at construction, or added a fifth route, would make this go red -- which
    is the point, since pyproject declares the dependency unpinned.
    """
    for name, value in AMBIENT_CLOUDFLARE_VARS.items():
        monkeypatch.setenv(name, value)
    path = write_config(tmp_path, 'api_token = "tok-123"')
    client = fpc.cloudflare_client(path)

    assert client.auth_headers == {"Authorization": "Bearer tok-123"}
    request = sent_request(client)
    assert str(request.url).startswith("https://api.cloudflare.com/client/v4/")
    # Each route named explicitly.  A set-intersection against the env var VALUES cannot see
    # route 3: $CLOUDFLARE_CUSTOM_HEADERS is "X-Auth-Email: attacker@..." while the header it
    # injects is just "attacker@...".  Mutation-tested -- the intersection form stayed green
    # with the _custom_headers clearing deleted.
    assert request.headers.get("x-auth-email") is None      # routes 1, 2 and 3
    assert request.headers.get("x-auth-key") is None        # routes 2 and 3
    assert "evil.example" not in str(request.headers)       # route 3 payload
    assert "ambient-key" not in str(request.headers)


def test_cloudflare_client_ignores_an_ambient_base_url(fpc, tmp_path, monkeypatch):
    """$CLOUDFLARE_BASE_URL would otherwise send the configured token to an arbitrary host --
    strictly worse than the defect the credential pin was written for (round 2, finding 3)."""
    monkeypatch.setenv("CLOUDFLARE_BASE_URL", "https://evil.example/v4")
    path = write_config(tmp_path, 'api_token = "tok-123"')
    request = sent_request(fpc.cloudflare_client(path))
    assert "evil.example" not in str(request.url)


def test_cloudflare_client_falls_back_to_email_and_key(fpc, tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "ambient-token")
    path = write_config(tmp_path, 'email = "someone@example.edu"\napi_key = "k-456"')
    client = fpc.cloudflare_client(path)
    assert client.api_email == "someone@example.edu"
    assert client.api_key == "k-456"
    assert client.api_token is None
    assert "ambient-token" not in set(sent_request(client).headers.values())


def test_cloudflare_client_requires_both_email_and_key(fpc, tmp_path):
    path = write_config(tmp_path, 'email = "someone@example.edu"')
    with pytest.raises(fpc.StartupError) as caught:
        fpc.cloudflare_client(path)
    assert "api_token" in str(caught.value)


def test_cloudflare_client_rejects_a_non_string_credential(fpc, tmp_path):
    """TOML is typed: `api_token = true` would otherwise reach the SDK and be stringified into
    `Authorization: Bearer True` -- the confusing 401 the marker rules exist to prevent."""
    path = write_config(tmp_path, "api_token = true")
    with pytest.raises(fpc.StartupError) as caught:
        fpc.cloudflare_client(path)
    assert "api_token" in str(caught.value)
    assert "bool" in str(caught.value)


def test_cloudflare_client_without_a_cloudflare_section_is_a_startup_error(fpc, tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[Pantheon]\norg_id = "abc"\n')
    with pytest.raises(fpc.StartupError) as caught:
        fpc.cloudflare_client(str(path))
    assert "[Cloudflare]" in str(caught.value)


def test_cloudflare_client_with_a_missing_file_is_a_startup_error(fpc, tmp_path):
    with pytest.raises(fpc.StartupError):
        fpc.cloudflare_client(str(tmp_path / "nope.toml"))


def test_cloudflare_client_with_a_non_utf8_file_is_a_startup_error(fpc, tmp_path):
    """tomllib.load decodes the bytes itself, so a non-UTF-8 config raises UnicodeDecodeError --
    NOT a TOMLDecodeError.  It escaped as a raw traceback at exit 1 until the guard was widened
    to ValueError, which is the common base of both (round 3, finding 1)."""
    path = tmp_path / "config.toml"
    path.write_bytes(b'[Cloudflare]\napi_token = "caf\xe9"\n')
    with pytest.raises(fpc.StartupError) as caught:
        fpc.cloudflare_client(str(path))
    assert "not valid TOML" in str(caught.value)


# --- Task 3: the fold ------------------------------------------------------------------------

def test_collect_entries_builds_the_output_structure(fpc):
    entries, warnings, excluded = fpc.collect_entries(
        [("zone-a", "example.edu", record(ttl=300, comment="migrated", tags=["cdn"]))])
    assert entries == {
        "www.example.edu": {
            "name": "www.example.edu",
            "zone_id": "zone-a",
            "zone_name": "example.edu",
            "origins": ["live-umich-example1.pantheonsite.io"],
            "record_id": "rec-1",
            "proxied": True,
            "ttl": 300,
            "comment": "migrated",
            "tags": ["cdn"],
            "settings": None,
        },
    }
    assert warnings == []
    assert excluded == {}


def test_collect_entries_keeps_dns_only_records(fpc):
    """The whole reason this script exists next to fqdns.json, which is proxied=True only."""
    entries, _, _ = fpc.collect_entries([("zone-a", "example.edu", record(proxied=False))])
    assert entries["www.example.edu"]["proxied"] is False


def test_collect_entries_serializes_a_pydantic_settings_model(fpc):
    """record.settings is a pydantic model; json.dump cannot serialize one."""
    from cloudflare.types.dns.cname_record import Settings
    entries, _, _ = fpc.collect_entries(
        [("zone-a", "example.edu", record(settings=Settings(flatten_cname=True)))])
    settings = entries["www.example.edu"]["settings"]
    assert settings["flatten_cname"] is True
    # Asserting the whole dict would pin the SDK's model shape (it also carries ipv4_only /
    # ipv6_only); what matters is the value round-tripping and the entry staying serializable,
    # which a live pydantic model would not be.
    json.dumps(entries)


def test_collect_entries_tolerates_a_record_missing_the_optional_fields(fpc):
    bare = types.SimpleNamespace(type="CNAME", name="www.example.edu", id="rec-1",
                                 content="live-umich-example1.pantheonsite.io")
    entries, _, _ = fpc.collect_entries([("zone-a", "example.edu", bare)])
    entry = entries["www.example.edu"]
    assert entry["proxied"] is None      # unknown, NOT coerced to False -- see R5
    assert entry["ttl"] is None
    assert entry["comment"] is None
    assert entry["tags"] == []
    assert entry["settings"] is None


@pytest.mark.parametrize("skipped", [
    {"type": "A", "content": "23.185.0.4"},
    {"type": "A", "content": "live-umich-example1.pantheonsite.io"},   # not a CNAME
    {"type": "TXT", "content": "v=spf1 -all"},
    {"type": "CNAME", "content": "www.example.edu.cdn.cloudflare.net"},  # not a platform domain
    {"type": "CNAME", "content": "notpantheonsite.io"},
])
def test_collect_entries_skips_everything_that_is_not_a_platform_cname(fpc, skipped):
    entries, warnings, excluded = fpc.collect_entries(
        [("zone-a", "example.edu", record(**skipped))])
    assert entries == {}
    assert warnings == []
    assert excluded == {}


def test_collect_entries_normalizes_the_key_and_keeps_origins_raw(fpc):
    entries, _, _ = fpc.collect_entries(
        [("zone-a", "example.edu", record(name="WWW.Example.EDU.",
                                          content="Live-Umich-Example1.PantheonSite.IO"))])
    assert list(entries) == ["www.example.edu"]
    assert entries["www.example.edu"]["origins"] == ["Live-Umich-Example1.PantheonSite.IO"]


def test_collect_entries_excludes_a_cross_zone_duplicate_and_appends_no_warning(fpc):
    """SPEC R4.1: this used to be the first-record-wins case (entry kept, origins accumulated).
    A cross-zone duplicate is now ambiguous and is REMOVED from `entries` -- kept in `excluded`
    instead -- because the kept record_id was never safe to act on.

    `warnings` is now asserted EMPTY, not the old per-fact ATTENTION text: controller decision
    (task 6 report, decision A) retired collect_entries()'s own warning because it duplicated
    main()'s uniform R7.1 exclusion line for the very same fact -- two stderr lines reporting
    one exclusion.  test_an_ambiguous_exclusion_produces_exactly_one_operator_line (Task 6
    section) now covers the single, real operator-facing line, driven through the actual
    fetch_platform_cnames()/main() path rather than a canned SweepResult."""
    entries, warnings, excluded = fpc.collect_entries([
        ("zone-a", "example.edu",
         record(id="rec-1", content="live-a.pantheonsite.io", proxied=True, ttl=1)),
        ("zone-b", "example.org",
         record(id="rec-2", content="live-b.pantheonsite.io", proxied=False, ttl=300)),
    ])
    assert entries == {}
    assert excluded["www.example.edu"]["reason"] == "ambiguous-multiple-zones"
    assert excluded["www.example.edu"]["origins"] == ["live-a.pantheonsite.io",
                                                      "live-b.pantheonsite.io"]
    assert excluded["www.example.edu"]["zone_ids"] == ["zone-a", "zone-b"]
    assert warnings == []


def test_collect_entries_excludes_two_matches_in_one_zone_and_appends_no_warning(fpc):
    """API-unreachable (a name holds at most one CNAME), but the file would keep one record_id
    of two and feed a destructive rewrite, so silence is the wrong default -- the `excluded`
    entry (asserted below) is that non-silence, not a printed warning (see the docstring on the
    cross-zone sibling test above for why `warnings` is now empty).

    SPEC R4.1: this used to be the first-record-wins case (entry kept with record_id "rec-1").
    A same-zone duplicate is now ambiguous and is REMOVED from `entries` -- kept in `excluded`
    instead."""
    entries, warnings, excluded = fpc.collect_entries([
        ("zone-a", "example.edu", record(id="rec-1", content="live-a.pantheonsite.io")),
        ("zone-a", "example.edu", record(id="rec-2", content="live-b.pantheonsite.io")),
    ])
    assert entries == {}
    assert excluded["www.example.edu"]["reason"] == "ambiguous-multiple-origins"
    assert warnings == []


# --- Task 4: the atomic write ----------------------------------------------------------------

def test_write_json_atomic_writes_sorted_indented_json_with_a_trailing_newline(fpc, tmp_path):
    target = tmp_path / "out.json"
    fpc.write_json_atomic(str(target), {"b": {"zone_id": "z"}, "a": {"zone_id": "y"}})
    text = target.read_text()
    assert text.endswith("\n")
    assert list(json.loads(text)) == ["a", "b"]
    assert '    "a"' in text          # indent=4


def test_write_json_atomic_overwrites_an_existing_file_and_leaves_no_temp_file(fpc, tmp_path):
    """SPEC: the output file is regenerated in full on every run, whatever its age."""
    target = tmp_path / "out.json"
    target.write_text('{"stale": {"zone_id": "old"}}\n')
    fpc.write_json_atomic(str(target), {})
    assert json.loads(target.read_text()) == {}
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]


def test_write_json_atomic_leaves_the_previous_file_intact_when_serialization_fails(fpc, tmp_path):
    target = tmp_path / "out.json"
    target.write_text('{"previous": {"zone_id": "kept"}}\n')
    with pytest.raises(TypeError):
        fpc.write_json_atomic(str(target), {"bad": {object()}})
    assert json.loads(target.read_text()) == {"previous": {"zone_id": "kept"}}
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]


# --- Task 5: the walk and the CLI ------------------------------------------------------------

class FakePage:
    """A stand-in for SyncV4PagePaginationArray.

    Iterating the real page object walks EVERY page (BaseSyncPage.__iter__ -> iter_pages), so
    this fake yields across chunks: an implementation that read `page.result` instead would see
    only the first, and this fake has no `result` attribute at all, so it would fail loudly.
    (test_the_real_page_class_has_a_result_attribute proves that trap is real, not imagined.)
    """

    def __init__(self, chunks, total_count=None, *, with_result_info=True):
        self._chunks = chunks
        self.result_info = types.SimpleNamespace(
            model_extra={} if total_count is None else {"total_count": total_count},
        ) if with_result_info else None

    def __iter__(self):
        for chunk in self._chunks:
            yield from chunk


class FakeCloudflareClient:
    """The three list() calls fetch_platform_cnames makes, and nothing else.

    `pages_by_zone` maps a zone id to the sequence of pages returned by successive calls (the
    last repeats), so a re-read can be made to agree or disagree with the first.
    """

    def __init__(self, accounts, zones, pages_by_zone=None, error=None):
        self._error = error
        self._pages_by_zone = pages_by_zone or {}
        self._calls = {}
        self.accounts = types.SimpleNamespace(list=lambda: accounts)
        self.zones = types.SimpleNamespace(list=lambda account: zones)
        self.dns = types.SimpleNamespace(records=types.SimpleNamespace(list=self._records))

    def _records(self, zone_id):
        if self._error is not None:
            raise self._error
        pages = self._pages_by_zone.get(zone_id) or [FakePage([[]])]
        index = min(self._calls.get(zone_id, 0), len(pages) - 1)
        self._calls[zone_id] = index + 1
        return pages[index]


def account(identifier="acct-1"):
    return types.SimpleNamespace(id=identifier)


def zone(identifier, name="example.edu"):
    return types.SimpleNamespace(id=identifier, name=name)


def test_fetch_platform_cnames_walks_every_zone_regardless_of_proxy_status(fpc):
    client = FakeCloudflareClient(
        accounts=[account()],
        zones=[zone("zone-a"), zone("zone-b", "example.org")],
        pages_by_zone={
            "zone-a": [FakePage([[record(name="proxied.example.edu", id="rec-1", proxied=True),
                                  record(name="mail.example.edu", id="rec-2", type="MX",
                                         content="mx.example.edu")]], total_count=2)],
            "zone-b": [FakePage([[record(name="dnsonly.example.org", id="rec-3",
                                         proxied=False)]], total_count=1)],
        })
    sweep = fpc.fetch_platform_cnames(client)
    assert sorted(sweep.entries) == ["dnsonly.example.org", "proxied.example.edu"]
    assert sweep.entries["dnsonly.example.org"]["proxied"] is False
    assert sweep.warnings == []
    assert (sweep.accounts, sweep.zones, sweep.records) == (1, 2, 3)
    # both record lists complete; the account and zone list fakes are plain lists
    # with no result_info, so they are unverifiable rather than complete.
    assert (sweep.lists_complete, sweep.lists_unverifiable) == (2, 2)


def test_fetch_platform_cnames_reads_every_page(fpc):
    """Pagination: a single list() call is N HTTP requests, and a short read would write a
    silently incomplete file."""
    client = FakeCloudflareClient(
        accounts=[account()], zones=[zone("zone-a")],
        pages_by_zone={"zone-a": [FakePage(
            [[record(name="page1.example.edu", id="rec-1")],
             [record(name="page2.example.edu", id="rec-2")]], total_count=2)]})
    sweep = fpc.fetch_platform_cnames(client)
    assert sorted(sweep.entries) == ["page1.example.edu", "page2.example.edu"]


def test_fetch_platform_cnames_unions_a_reread_to_close_a_gap(fpc):
    """A second walk steps over different rows, so the union is more complete than either read
    alone -- and often closes the gap outright."""
    client = FakeCloudflareClient(
        accounts=[account()], zones=[zone("zone-a")],
        pages_by_zone={"zone-a": [
            FakePage([[record(name="a.example.edu", id="rec-1")]], total_count=2),
            FakePage([[record(name="b.example.edu", id="rec-2")]], total_count=2),
        ]})
    sweep = fpc.fetch_platform_cnames(client)
    assert sorted(sweep.entries) == ["a.example.edu", "b.example.edu"]
    assert sweep.lists_short == 0


def test_fetch_platform_cnames_reports_a_short_list_without_aborting(fpc, capsys):
    """The first live sweep aborted an entire 187-zone run over 2 records missed in one
    18,848-record zone.  A shortfall is now reported and the file is still written."""
    client = FakeCloudflareClient(
        accounts=[account()], zones=[zone("zone-a")],
        pages_by_zone={"zone-a": [FakePage([[record()]], total_count=3)]})
    sweep = fpc.fetch_platform_cnames(client)
    assert list(sweep.entries) == ["www.example.edu"]
    assert sweep.lists_short == 1
    assert "were missed while paging" in capsys.readouterr().err


def test_fetch_platform_cnames_counts_every_list_it_reads(fpc):
    """Completeness is counted over the account list, each zone list, and each record list --
    reporting only record lists would leave the zone-list check unaccounted for."""
    client = FakeCloudflareClient(
        accounts=[account()], zones=[zone("zone-a"), zone("zone-b", "example.org")],
        pages_by_zone={"zone-a": [FakePage([[record()]], with_result_info=False)],
                       "zone-b": [FakePage([[]], total_count=0)]})
    sweep = fpc.fetch_platform_cnames(client)
    assert list(sweep.entries) == ["www.example.edu"]
    # account list (no result_info) + zone list (no result_info) + zone-a records = 3
    # unverifiable; zone-b's empty-but-counted record list = 1 complete.
    assert (sweep.lists_complete, sweep.lists_short, sweep.lists_unverifiable) == (1, 0, 3)


def test_fetch_platform_cnames_treats_zero_zones_as_fatal(fpc):
    """A missing scope and a genuinely empty org produce an identical empty file."""
    client = FakeCloudflareClient(accounts=[account()], zones=[])
    with pytest.raises(fpc.StartupError) as caught:
        fpc.fetch_platform_cnames(client)
    assert "0 zones" in str(caught.value)


def test_fetch_platform_cnames_turns_an_api_error_into_a_startup_error(fpc):
    import cloudflare
    client = FakeCloudflareClient(
        accounts=[account()], zones=[zone("zone-a")],
        error=cloudflare.APIConnectionError(request=None))
    with pytest.raises(fpc.StartupError) as caught:
        fpc.fetch_platform_cnames(client)
    assert "DNS records" in str(caught.value)


def test_expected_record_count_reads_a_real_result_info(fpc):
    """Against the SDK's own model, not the fake: total_count survives only because
    V4PagePaginationArrayResultInfo sets model_config extra="allow".  An SDK that tightened
    that, or renamed the field, would make the whole truncation guard no-op in production --
    and every fake-backed test would stay green."""
    from cloudflare.pagination import V4PagePaginationArrayResultInfo
    info = V4PagePaginationArrayResultInfo.model_validate(
        {"page": 1, "per_page": 100, "count": 1, "total_count": 137})
    assert fpc.expected_record_count(types.SimpleNamespace(result_info=info)) == 137


def test_the_real_page_class_has_a_result_attribute(fpc):
    """FakePage deliberately lacks `result` so an implementation reading page.result (page 1
    only) fails loudly.  That trap is only meaningful if the real class HAS the attribute."""
    from cloudflare.pagination import SyncV4PagePaginationArray
    assert "result" in SyncV4PagePaginationArray.model_fields


def test_api_error_text_never_includes_a_real_response_body(fpc):
    """Against a real SDK exception.  If status_code is ever renamed, api_error_text falls back
    to str(e) -- which IS "Error code: NNN - {body}", the leak the NEVER-block forbids."""
    import cloudflare
    import httpx
    body = {"errors": [{"code": 10000, "message": "token cf-secret-xyz invalid"}]}
    request = httpx.Request("GET", "https://api.cloudflare.com/client/v4/zones")
    error = cloudflare.PermissionDeniedError(
        f"Error code: 403 - {body}",
        response=httpx.Response(403, request=request, json=body), body=body)
    text = fpc.api_error_text(error)
    assert text == "PermissionDeniedError: HTTP 403"
    assert "cf-secret-xyz" not in text


def test_read_all_reports_a_complete_read(fpc):
    page = FakePage([[record(id="rec-1"), record(id="rec-2")]], total_count=2)
    items, shortfall = fpc.read_all(lambda: page, "the record list for zone x", print)
    assert len(items) == 2
    assert shortfall == 0


def test_read_all_deduplicates_records_repeated_across_pages(fpc):
    """MEASURED on the first live sweep.  The SDK paginates by page NUMBER, so rows shifting
    between page fetches make one record come back twice while another is stepped over.  Passing
    the duplicate onward would append one record's origin twice and raise a FALSE "more than one
    platform-domain CNAME in this zone" warning."""
    page = FakePage([[record(id="rec-1"), record(id="rec-2")],
                     [record(id="rec-2"), record(id="rec-3")]], total_count=3)
    items, shortfall = fpc.read_all(lambda: page, "the record list for zone x", print)
    assert sorted(i.id for i in items) == ["rec-1", "rec-2", "rec-3"]
    assert shortfall == 0


def test_read_all_cannot_check_without_total_count(fpc):
    page = FakePage([[record()]], with_result_info=False)
    items, shortfall = fpc.read_all(lambda: page, "the record list for zone x", print)
    assert len(items) == 1
    assert shortfall is None             # unverifiable, NOT asserted as complete


def test_read_all_unions_a_reread_to_close_the_gap(fpc):
    """A second walk usually steps over different rows, so the union is more complete than
    either read alone."""
    pages = iter([FakePage([[record(id="rec-1")]], total_count=2),
                  FakePage([[record(id="rec-2")]], total_count=2)])
    said = []
    items, shortfall = fpc.read_all(lambda: next(pages), "the record list for zone x", said.append)
    assert sorted(i.id for i in items) == ["rec-1", "rec-2"]
    assert shortfall == 0
    assert any("re-reading to close the gap" in m for m in said)


def test_read_all_warns_but_does_not_abort_when_records_stay_missing(fpc):
    """A shortfall is a WARNING, never fatal: a paginated walk of a continuously-written zone may
    never be exactly complete, and aborting would mean never producing output at all."""
    pages = iter([FakePage([[record(id="rec-1")]], total_count=3),
                  FakePage([[record(id="rec-2")]], total_count=3)])
    said = []
    items, shortfall = fpc.read_all(lambda: next(pages), "the record list for zone x", said.append)
    assert sorted(i.id for i in items) == ["rec-1", "rec-2"]
    assert shortfall == 1
    assert any("1 record(s) were missed" in m for m in said)
    assert any("NOT in the output" in m for m in said)


def test_a_reread_is_reported_without_v(fpc, capsys):
    """A re-read means the data moved under the sweep -- an operator wants that on a default run,
    not only when they happened to pass -v (round 3, finding 3)."""
    client = FakeCloudflareClient(
        accounts=[account()], zones=[zone("zone-a")],
        pages_by_zone={"zone-a": [
            FakePage([[record(name="a.example.edu", id="rec-1")]], total_count=2),
            FakePage([[record(name="a.example.edu", id="rec-1"),
                       record(name="b.example.edu", id="rec-2")]], total_count=2),
        ]})
    fpc.fetch_platform_cnames(client, verbose=False)
    assert "re-reading to close the gap" in capsys.readouterr().err


def test_verbose_reports_each_zone_and_whether_it_was_cross_checked(fpc, capsys):
    """SPEC section 6's -v contract, which nothing asserted until round 3 finding 5."""
    client = FakeCloudflareClient(
        accounts=[account()], zones=[zone("zone-a"), zone("zone-b", "example.org")],
        pages_by_zone={"zone-a": [FakePage([[record()]], total_count=1)],
                       "zone-b": [FakePage([[record(name="b.example.org")]],
                                           with_result_info=False)]})
    fpc.fetch_platform_cnames(client, verbose=True)
    err = capsys.readouterr().err
    assert "[1/2] zone example.edu -- 1 records" in err
    assert "[2/2] zone example.org -- 1 records (total_count unavailable, not cross-checked)" in err


# Task 4 wires resolution into EVERY main() call, so any pre-Task-4 test driving main() with an
# ENTRY-shaped dict now needs its target resolved too, or it hits real DNS (SPEC section 7:
# "NOTHING in the suite may touch real DNS") -- enforced class-wide by the autouse
# `_refuse_real_dns` fixture above, which fails loudly on any un-mocked resolve() call.  This is
# the one in-range answer set every such test uses via fake_dns(fpc, monkeypatch,
# ENTRY_HAPPY_DNS) -- addresses inside both PLATFORM_A_RANGE and PLATFORM_AAAA_RANGE, so
# classify() returns (None, "") and these pre-existing tests' exit-0 assertions are unaffected by
# this task.
#
# There is deliberately no module-level ENTRY constant: main() mutates the entry dict it is
# handed in place (adding resolved_a/resolved_aaaa), so a single shared dict object reused across
# many tests both leaks state between them and makes any assertion of the shape
# `... == {"a.example.edu": ENTRY}` self-referential -- it compares the mutated object to itself
# and passes no matter what was actually written (task 4 review, finding 2, which is what masked
# finding 1: two tests below were reaching real DNS while their content assertions kept passing
# against the very state real DNS had just written into the shared object).  Every test below
# builds its own entry fresh via swept() (defined in the Task 4 section further down -- forward
# references to test-local helpers are safe here because pytest fully executes this module before
# running any test, the same reason fake_dns() is usable from tests above its own definition).
ENTRY_HAPPY_DNS = {("live-a.pantheonsite.io", "A"): ["23.185.0.4"],
                   ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8000::4"]}


def fake_sweep(fpc, monkeypatch, sweep):
    """Drive main() with a canned SweepResult, skipping the client build and the walk."""
    monkeypatch.setattr(fpc, "cloudflare_client", lambda config_path: object())
    monkeypatch.setattr(fpc, "fetch_platform_cnames",
                        lambda client, verbose=False, zone_names=(): sweep)


def test_main_writes_the_json_to_stdout_by_default(fpc, tmp_path, monkeypatch, capsys):
    """SPEC A1.5: stdout is the result stream; the file is written only when -o names it."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult(
        {"a.example.edu": swept(proxied=False)},
        ["ATTENTION: something worth seeing"], 1, 4, 12431, 40, 1, 2, 4))
    fake_dns(fpc, monkeypatch, ENTRY_HAPPY_DNS)
    assert fpc.main(["-c", "ignored.toml"]) == 0
    captured = capsys.readouterr()
    assert list(json.loads(captured.out)) == ["a.example.edu"]
    assert not (tmp_path / f"{fpc.OUTPUT_BASENAME}.json").exists(), "no -o, so no file is written"
    err = captured.err
    assert "ATTENTION: something worth seeing" in err
    assert "Wrote 1 platform-domain CNAMEs (1 DNS-only" in err
    assert "from 12431 records in 4 zones in 1 account(s) to standard output." in err
    assert ("Completeness cross-check: 40 of 43 paginated lists verified complete, 1 short, "
            "2 unverifiable.") in err
    assert "the short lists are named above" in err


def test_main_writes_a_file_when_output_is_given(fpc, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": swept(proxied=False)}, [], 1, 4,
                                                 12431, 40, 1, 2, 4))
    fake_dns(fpc, monkeypatch, ENTRY_HAPPY_DNS)
    assert fpc.main(["-o", fpc.OUTPUT_BASENAME]) == 0
    captured = capsys.readouterr()
    assert list(json.loads((tmp_path / f"{fpc.OUTPUT_BASENAME}.json").read_text())) == \
        ["a.example.edu"]
    assert captured.out == "", "with -o, stdout carries only argparse output"
    # Review finding 2: the summary names ALL FOUR files in basename mode, each with its own
    # entry count -- not just the inventory.
    err = captured.err
    assert f"{fpc.OUTPUT_BASENAME}.json (1 entries)" in err
    assert f"{fpc.OUTPUT_BASENAME}-plan.json (1 entries)" in err
    assert f"{fpc.OUTPUT_BASENAME}-revert.json (1 entries)" in err
    assert f"{fpc.OUTPUT_BASENAME}-excluded.json (0 entries)" in err


def test_main_writes_byte_identical_json_to_stdout_and_to_a_file(fpc, tmp_path, monkeypatch,
                                                                 capsys):
    """SPEC A1.5: the two destinations differ in WHERE, never in WHAT."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult(
        {"a.example.edu": swept(proxied=False), "b.example.edu": swept(proxied=False)},
        [], 1, 4, 1, 1, 0, 0, 4))
    fake_dns(fpc, monkeypatch, ENTRY_HAPPY_DNS)
    assert fpc.main([]) == 0
    from_stdout = capsys.readouterr().out
    assert fpc.main(["-o", "out"]) == 0
    assert (tmp_path / "out.json").read_text() == from_stdout


def test_main_says_how_many_zones_of_how_many_on_a_subset_run(fpc, tmp_path, monkeypatch, capsys):
    """SPEC A1.6: a subset run can never read as a full sweep in a log."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({}, [], 1, 2, 900, 6, 0, 0, 187))
    assert fpc.main(["engin.umich.edu", "seas.umich.edu"]) == 0
    assert "in 2 of 187 zones in 1 account(s)" in capsys.readouterr().err


def test_main_passes_the_zone_arguments_through_to_the_sweep(fpc, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seen = {}
    monkeypatch.setattr(fpc, "cloudflare_client", lambda config_path: object())

    def capture(client, *, verbose=False, zone_names=()):
        seen["zone_names"] = zone_names
        seen["verbose"] = verbose
        return fpc.SweepResult({}, [], 1, 1, 0, 1, 0, 0, 1)

    monkeypatch.setattr(fpc, "fetch_platform_cnames", capture)
    assert fpc.main(["-v", "engin.umich.edu", "seas.umich.edu"]) == 0
    assert seen == {"zone_names": ["engin.umich.edu", "seas.umich.edu"], "verbose": True}


def test_main_does_not_count_an_unknown_proxy_status_as_dns_only(fpc, tmp_path, monkeypatch,
                                                                 capsys):
    """research.md: "proxied: true is the load-bearing field in both directions".  A null
    flattened to false would inflate the headline count AND tell a rewriter to re-create a
    proxied hostname unproxied (round 3, finding 4).

    Exit is now 1, not 0 (Task 4): classify() excludes an unknown-proxy-status entry regardless
    of what it resolves to (SPEC 6, evaluated before any resolution outcome) -- fake_dns is still
    required so resolve_target's unconditional call does not reach real DNS."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fpc, "cloudflare_client", lambda config_path: object())
    entry = {"zone_id": "z", "origins": ["live-a.pantheonsite.io"], "record_id": "r",
             "proxied": None, "ttl": 1, "comment": None, "tags": [], "settings": None}
    monkeypatch.setattr(fpc, "fetch_platform_cnames", lambda client, verbose=False, zone_names=():
                        fpc.SweepResult({"a.example.edu": entry}, [], 1, 1, 1, 3, 0, 0, 1))
    fake_dns(fpc, monkeypatch, ENTRY_HAPPY_DNS)
    assert fpc.main([]) == 1
    err = capsys.readouterr().err
    assert "(0 DNS-only" in err
    assert "unknown proxy status" in err
    assert "a.example.edu" in err


def test_main_says_so_when_nothing_matched(fpc, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fpc, "cloudflare_client", lambda config_path: object())
    monkeypatch.setattr(fpc, "fetch_platform_cnames", lambda client, verbose=False, zone_names=():
                        fpc.SweepResult({}, [], 1, 4, 900, 6, 0, 0, 4))
    assert fpc.main([]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {}
    assert "no platform-domain CNAMEs found in 4 zones" in captured.err


def test_main_reports_a_startup_error_as_exit_2(fpc, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert fpc.main(["-c", str(tmp_path / "nope.toml")]) == 2
    assert "ERROR: cannot read" in capsys.readouterr().err


def test_main_reports_an_interrupt_as_exit_130(fpc, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    def interrupt(config_path):
        raise KeyboardInterrupt

    monkeypatch.setattr(fpc, "cloudflare_client", interrupt)
    assert fpc.main([]) == 130
    assert "INTERRUPTED" in capsys.readouterr().err


def test_main_names_an_unwritable_output_file_instead_of_crashing(fpc, tmp_path, monkeypatch,
                                                                  capsys):
    """An OSError here lands AFTER the whole multi-minute walk; it escaped as a raw traceback at
    exit 1 until it was named (adversarial review round 1, finding 3)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fpc, "cloudflare_client", lambda config_path: object())
    monkeypatch.setattr(fpc, "fetch_platform_cnames", lambda client, verbose=False, zone_names=():
                        fpc.SweepResult({}, [], 1, 1, 0, 3, 0, 0, 1))

    def refuse(path, data):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(fpc, "write_json_atomic", refuse)
    assert fpc.main(["-o", fpc.OUTPUT_BASENAME]) == 2
    assert "cannot write" in capsys.readouterr().err


# --- Amendment A1: zone selection ------------------------------------------------------------

def test_select_zones_keeps_only_the_named_zones_in_the_order_given(fpc):
    zones = [zone("z-a", "a.umich.edu"), zone("z-b", "b.umich.edu"), zone("z-c", "c.umich.edu")]
    picked = fpc.select_zones(zones, ["c.umich.edu", "a.umich.edu"])
    assert [z.id for z in picked] == ["z-c", "z-a"]


def test_select_zones_normalizes_case_and_the_trailing_dot_on_both_sides(fpc):
    zones = [zone("z-a", "Engin.UMich.edu."), zone("z-b", "b.umich.edu")]
    assert [z.id for z in fpc.select_zones(zones, ["  ENGIN.umich.EDU  "])] == ["z-a"]


def test_select_zones_deduplicates_a_repeated_name_and_keeps_the_order(fpc):
    zones = [zone("z-a", "a.umich.edu"), zone("z-b", "b.umich.edu")]
    picked = fpc.select_zones(zones, ["b.umich.edu", "a.umich.edu", "b.umich.edu"])
    assert [z.id for z in picked] == ["z-b", "z-a"]


def test_select_zones_keeps_every_zone_when_one_name_matches_more_than_one(fpc):
    """The same name in two accounts: both are swept, so collect_entries can still warn."""
    zones = [zone("z-a", "shared.umich.edu"), zone("z-b", "shared.umich.edu")]
    assert [z.id for z in fpc.select_zones(zones, ["shared.umich.edu"])] == ["z-a", "z-b"]


def test_select_zones_names_every_unmatched_name_not_just_the_first(fpc):
    zones = [zone("z-a", "a.umich.edu")]
    with pytest.raises(fpc.StartupError) as excinfo:
        fpc.select_zones(zones, ["typo1.umich.edu", "a.umich.edu", "typo2.umich.edu"])
    message = str(excinfo.value)
    assert "typo1.umich.edu" in message
    assert "typo2.umich.edu" in message
    assert "a.umich.edu" not in message.replace("typo1.umich.edu", "").replace(
        "typo2.umich.edu", "")


def test_fetch_platform_cnames_reads_records_for_the_named_zones_only(fpc):
    """The point of the feature: the other zones are never queried at all."""
    client = FakeCloudflareClient(
        accounts=[account()],
        zones=[zone("z-a", "a.umich.edu"), zone("z-b", "b.umich.edu"),
               zone("z-c", "c.umich.edu")],
        pages_by_zone={
            "z-a": [FakePage([[record(name="www.a.umich.edu", id="rec-a")]], total_count=1)],
            "z-b": [FakePage([[record(name="www.b.umich.edu", id="rec-b")]], total_count=1)],
            "z-c": [FakePage([[record(name="www.c.umich.edu", id="rec-c")]], total_count=1)],
        })
    sweep = fpc.fetch_platform_cnames(client, zone_names=["c.umich.edu", "a.umich.edu"])
    assert sorted(sweep.entries) == ["www.a.umich.edu", "www.c.umich.edu"]
    assert sorted(client._calls) == ["z-a", "z-c"]      # the fake's own call record
    assert (sweep.zones, sweep.zones_total) == (2, 3)


def test_fetch_platform_cnames_without_zone_names_still_sweeps_everything(fpc):
    client = FakeCloudflareClient(
        accounts=[account()],
        zones=[zone("z-a", "a.umich.edu"), zone("z-b", "b.umich.edu")],
        pages_by_zone={
            "z-a": [FakePage([[record(name="www.a.umich.edu", id="rec-a")]], total_count=1)],
            "z-b": [FakePage([[record(name="www.b.umich.edu", id="rec-b")]], total_count=1)],
        })
    sweep = fpc.fetch_platform_cnames(client)
    assert sorted(sweep.entries) == ["www.a.umich.edu", "www.b.umich.edu"]
    assert (sweep.zones, sweep.zones_total) == (2, 2)


def test_fetch_platform_cnames_rejects_an_unmatched_zone_name_before_reading_records(fpc):
    client = FakeCloudflareClient(accounts=[account()], zones=[zone("z-a", "a.umich.edu")])
    with pytest.raises(fpc.StartupError, match=re.escape("no Cloudflare zone matches nope.umich.edu")):
        fpc.fetch_platform_cnames(client, zone_names=["nope.umich.edu"])
    assert client._calls == {}                          # the fake's own call record


# --- Amendment A1: stream guards (SPEC A1.5) --------------------------------------------------

DEV_FULL = "/dev/full"
needs_dev_full = pytest.mark.skipif(not os.path.exists(DEV_FULL),  # noqa: PTH110 -- a device
                                    reason="/dev/full is Linux-only")   # node, not a repo path


def test_a_closed_stdout_with_no_output_flag_is_a_named_exit_2(fpc, tmp_path, monkeypatch,
                                                               capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdout", None)
    assert fpc.main([]) == 2
    assert "standard output is closed" in capsys.readouterr().err


def test_a_closed_stdout_is_allowed_when_output_names_a_file(fpc, tmp_path, monkeypatch):
    """-o gives the JSON somewhere to go, so the stdout guard must not fire."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": swept(proxied=False)}, [], 1, 1,
                                                 1, 1, 0, 0, 1))
    fake_dns(fpc, monkeypatch, ENTRY_HAPPY_DNS)
    monkeypatch.setattr(sys, "stdout", None)
    assert fpc.main(["-o", "out"]) == 0
    assert list(json.loads((tmp_path / "out.json").read_text())) == ["a.example.edu"]


def test_a_closed_stderr_is_a_named_exit_2_reported_on_the_stdout_fallback(fpc, tmp_path,
                                                                          monkeypatch, capsys):
    """Measured: print(file=sys.stderr) with stderr None falls back to stdout, which would
    otherwise interleave operator messages into the JSON."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stderr", None)
    assert fpc.main([]) == 2
    assert "standard error is closed" in capsys.readouterr().out


@needs_dev_full
def test_a_doomed_stdout_becomes_a_named_startup_error_not_exit_120(fpc, monkeypatch):
    with Path(DEV_FULL).open("w") as doomed:
        monkeypatch.setattr(sys, "stdout", doomed)
        with pytest.raises(fpc.StartupError, match="cannot write the JSON to standard output"):
            fpc.write_json_stdout({"a.example.edu": swept(proxied=False)})


def spy_on_dup2(fpc, monkeypatch):
    """Record every os.dup2 the script performs.  Driven over a REAL file descriptor, never
    capsys: capsys's pseudo-stream raises io.UnsupportedOperation from fileno(), which
    point_at_devnull suppresses, so os.dup2 is never reached and the mutation "detach
    unconditionally" stays green -- an instrument that cannot go red on the condition it guards
    (PD#14).  The sibling's suite names this exact trap."""
    calls = []
    monkeypatch.setattr(fpc.os, "dup2", lambda *args: calls.append(args))
    return calls


def test_a_healthy_stdout_is_never_detached_by_a_successful_write(fpc, tmp_path, monkeypatch):
    calls = spy_on_dup2(fpc, monkeypatch)
    entry = swept(proxied=False)
    with (tmp_path / "out.json").open("w") as real_stdout:
        monkeypatch.setattr(sys, "stdout", real_stdout)
        fpc.write_json_stdout({"a.example.edu": entry})
    assert calls == [], "a stream no write has failed on must never be detached"
    assert json.loads((tmp_path / "out.json").read_text()) == {"a.example.edu": entry}


def test_a_healthy_stderr_is_never_detached_by_report_line(fpc, tmp_path, monkeypatch):
    calls = spy_on_dup2(fpc, monkeypatch)
    with (tmp_path / "err.txt").open("w") as real_stderr:
        monkeypatch.setattr(sys, "stderr", real_stderr)
        fpc.report_line("ERROR: something happened")
    assert calls == []
    assert "ERROR: something happened" in (tmp_path / "err.txt").read_text()


@needs_dev_full
def test_a_doomed_stdout_is_detached_after_its_write_fails(fpc, monkeypatch):
    calls = spy_on_dup2(fpc, monkeypatch)
    # No `with`: the dup2 spy suppresses the real detach, so the fd still points at /dev/full and
    # close() would raise ENOSPC out of __exit__ -- the very condition under test.
    doomed = Path(DEV_FULL).open("w")           # noqa: SIM115 -- closed in the finally below
    try:
        monkeypatch.setattr(sys, "stdout", doomed)
        with pytest.raises(fpc.StartupError):
            fpc.write_json_stdout({"a.example.edu": swept(proxied=False)})
    finally:
        with contextlib.suppress(OSError):
            doomed.close()
    assert calls, "a stream a real write proved doomed MUST be detached, or exit 120 wins"


@needs_dev_full
def test_a_doomed_stderr_is_detached_by_report_line_without_raising(fpc, monkeypatch):
    calls = spy_on_dup2(fpc, monkeypatch)
    doomed = Path(DEV_FULL).open("w")           # noqa: SIM115 -- see the stdout twin above
    try:
        monkeypatch.setattr(sys, "stderr", doomed)
        fpc.report_line("ERROR: nowhere left to report this")
    finally:
        with contextlib.suppress(OSError):
            doomed.close()
    assert calls, "report_line is the end of the road; it must detach rather than propagate"


@needs_dev_full
def test_a_doomed_stderr_exits_2_in_a_real_subprocess(tmp_path):
    """End to end: without report_line's guard the interpreter's shutdown flush of the same
    doomed stderr overrides the exit code with 120, a code SPEC R6 does not contain."""
    with Path(DEV_FULL).open("w") as doomed:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "-c", str(tmp_path / "missing.toml")],
            stdout=subprocess.PIPE, stderr=doomed, check=False)
    assert completed.returncode == 2, "a doomed stderr must not become exit 120"


def run_main_in_a_subprocess(tmp_path, argv, *, stderr, stdout=subprocess.PIPE,
                            sweep="canned"):
    """Drive the REAL main() in a real interpreter, so the shutdown flush that produces exit 120
    actually runs.  An in-process test cannot observe it: pytest never tears the interpreter down
    between tests, so the whole 120 mechanism is invisible to one (SPEC A1.8, row A12)."""
    driver = tmp_path / "driver.py"
    driver.write_text(f"""
import sys
from importlib.machinery import SourceFileLoader
import importlib.util
loader = SourceFileLoader("fpc", {str(SCRIPT)!r})
spec = importlib.util.spec_from_loader("fpc", loader)
m = importlib.util.module_from_spec(spec)
sys.modules["fpc"] = m
loader.exec_module(m)
entry = {{"name": "a.example.edu", "zone_id": "z", "origins": ["live-a.pantheonsite.io"],
         "record_id": "r", "proxied": False, "ttl": 1, "comment": None, "tags": [],
         "settings": None}}
entries = {{"a.example.edu": entry}} if {sweep!r} == "canned" else {{}}
m.cloudflare_client = lambda path: object()
m.fetch_platform_cnames = (
    lambda client, verbose=False, zone_names=(): m.SweepResult(entries, [], 1, 2, 5, 1, 0, 0, 187))
# Task 4 wires resolve_target into every main() call; this is a real subprocess (SPEC A1.8), not
# an in-process test, so the module-level `resolve` monkeypatch idiom (fake_dns) does not apply
# here -- patch the same seam directly on this fresh module instance instead.  Without it, main()
# would resolve "live-a.pantheonsite.io" against REAL DNS, which SPEC section 7 forbids.
m.resolve = lambda hostname, rrtype: {{"A": ["23.185.0.4"], "AAAA": ["2620:12a:8000::4"]}}[rrtype]
sys.exit(m.main(sys.argv[1:]))
""")
    return subprocess.run([sys.executable, str(driver), *argv],
                          stdout=stdout, stderr=stderr, check=False)


@needs_dev_full
def test_a_doomed_stderr_on_the_success_path_exits_2_not_120(tmp_path):
    """The guards originally covered only the error path.  Measured before this test existed:
    a completed sweep whose summary line hit ENOSPC escaped main() and the interpreter's shutdown
    flush of the same doomed stderr turned exit 0 into 120 -- a code outside the 0/2/130 taxonomy,
    so a `case $?` wrapper falls through with a complete JSON already on stdout."""
    with Path(DEV_FULL).open("w") as doomed:
        completed = run_main_in_a_subprocess(tmp_path, [], stderr=doomed)
    assert completed.returncode == 2, "a doomed stderr on the success path must not become 120"


@needs_dev_full
def test_a_doomed_stdout_exits_2_not_120_in_a_real_subprocess(tmp_path):
    """SPEC A1.8 row A12, as specified: a subprocess, observing the exit code.  The in-process
    variant cannot pin this -- pytest never tears the interpreter down, so the shutdown flush
    that produces 120 never runs."""
    with Path(DEV_FULL).open("w") as doomed_out:
        completed = run_main_in_a_subprocess(tmp_path, [], stdout=doomed_out,
                                             stderr=subprocess.PIPE)
    assert completed.returncode == 2
    assert b"cannot write the JSON to standard output" in completed.stderr


def test_the_zero_match_attention_names_the_real_destination(fpc, tmp_path, monkeypatch, capsys):
    """It named platform-domains-cloudflare.json unconditionally -- telling an operator that a
    prior full sweep's baseline had just been overwritten empty, when no file was written at
    all."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({}, [], 1, 2, 5, 1, 0, 0, 187))
    assert fpc.main([]) == 0
    err = capsys.readouterr().err
    assert "an empty result ({}) was written to standard output" in err
    assert f"{fpc.OUTPUT_BASENAME}.json" not in err, \
        "no file was written; naming one implies a baseline died"


def test_the_zero_match_attention_names_the_output_file_when_one_is_given(fpc, tmp_path,
                                                                         monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({}, [], 1, 2, 5, 1, 0, 0, 187))
    assert fpc.main(["-o", "chosen"]) == 0
    assert "an empty result ({}) was written to chosen.json" in capsys.readouterr().err


def test_an_interrupt_after_a_successful_stdout_write_does_not_claim_nothing_was_produced(
        fpc, tmp_path, monkeypatch, capsys):
    """The message was categorical, so an operator or wrapper acting on it would discard a
    complete, valid document that is already on stdout."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch,
               fpc.SweepResult({"a.example.edu": swept(proxied=False)}, [], 1, 1, 1, 1, 0, 0, 1))
    fake_dns(fpc, monkeypatch, ENTRY_HAPPY_DNS)

    def interrupt_after_the_write(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(fpc, "summarize", interrupt_after_the_write)
    assert fpc.main([]) == 130
    captured = capsys.readouterr()
    # An INDEPENDENTLY built expected dict, never the object main() mutated (task 4 review round
    # 3, finding 2 residual): asserting against the same object main() wrote into cannot fail no
    # matter what resolve_target/classify actually computed.  The literal resolved_a/resolved_aaaa
    # values below come from what fake_dns(ENTRY_HAPPY_DNS) was told to answer, not from reading
    # main()'s output back.
    expected = swept(proxied=False)
    expected["resolved_a"] = ["23.185.0.4"]
    expected["resolved_aaaa"] = ["2620:12a:8000::4"]
    assert json.loads(captured.out) == {"a.example.edu": expected}
    assert "no complete JSON document was produced" not in captured.err
    assert "complete JSON document was already written to standard output" in captured.err


def test_an_interrupt_before_the_write_says_nothing_was_produced(fpc, tmp_path, monkeypatch,
                                                                 capsys):
    monkeypatch.chdir(tmp_path)

    def interrupt(config_path):
        raise KeyboardInterrupt

    monkeypatch.setattr(fpc, "cloudflare_client", interrupt)
    assert fpc.main([]) == 130
    assert "no complete JSON document was produced" in capsys.readouterr().err


def test_a_subset_run_written_to_a_file_warns_that_it_is_not_a_full_sweep(fpc, tmp_path,
                                                                          monkeypatch, capsys):
    """-o accepts a subset, and the file is byte-shape-identical to a full sweep with no in-band
    marker of scope.  The stderr line is the only signal, so it must be loud."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": swept(proxied=False)}, [], 1, 2,
                                                 5, 1, 0, 0, 187))
    fake_dns(fpc, monkeypatch, ENTRY_HAPPY_DNS)
    assert fpc.main(["-o", "subset", "engin.umich.edu", "seas.umich.edu"]) == 0
    err = capsys.readouterr().err
    assert "ATTENTION" in err
    assert "2 of 187" in err
    assert "NOT an organization-wide sweep" in err


def test_a_full_sweep_written_to_a_file_does_not_warn(fpc, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": swept(proxied=False)}, [], 1,
                                                 187, 5, 1, 0, 0, 187))
    fake_dns(fpc, monkeypatch, ENTRY_HAPPY_DNS)
    assert fpc.main(["-o", "full"]) == 0
    assert "NOT an organization-wide sweep" not in capsys.readouterr().err


def test_write_json_atomic_and_stdout_share_one_serializer(fpc, tmp_path, monkeypatch):
    """dump_json's docstring calls itself "the ONE serialization"; write_json_atomic formatted
    separately, so the byte-identity held only by duplicated literals."""
    seen = []
    real = fpc.dump_json
    monkeypatch.setattr(fpc, "dump_json", lambda data, stream: (seen.append(stream), real(
        data, stream))[1])
    fpc.write_json_atomic(str(tmp_path / "out.json"), {"a.example.edu": swept(proxied=False)})
    assert len(seen) == 1, "write_json_atomic must serialize through dump_json"


def test_an_interrupt_with_output_after_the_write_says_the_file_was_fully_written(
        fpc, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": swept(proxied=False)}, [], 1, 1,
                                                 1, 1, 0, 0, 1))
    fake_dns(fpc, monkeypatch, ENTRY_HAPPY_DNS)

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(fpc, "summarize", interrupt)
    assert fpc.main(["-o", "out"]) == 130
    err = capsys.readouterr().err
    # Task 6: interrupt_message() now describes all FOUR files, not just the inventory --
    # main() writes the plan/revert/excluded files too under -o (SPEC 9.4).
    assert "out.json" in err
    assert "were fully written." in err
    assert list(json.loads((tmp_path / "out.json").read_text())) == ["a.example.edu"]


def test_an_interrupt_with_output_before_the_write_never_claims_the_file_is_unchanged(
        fpc, tmp_path, monkeypatch, capsys):
    """`wrote` is a reliable YES and an unreliable NO: a SIGINT between os.replace() and the
    assignment leaves wrote=False with the file already replaced, so this branch must state only
    what is always true -- the write is atomic, never partial."""
    monkeypatch.chdir(tmp_path)

    def interrupt(config_path):
        raise KeyboardInterrupt

    monkeypatch.setattr(fpc, "cloudflare_client", interrupt)
    assert fpc.main(["-o", "out"]) == 130
    err = capsys.readouterr().err
    assert "never partial" in err
    assert "out.json is unchanged --" not in err, "an unqualified 'unchanged' can be false"


def test_the_zone_positional_is_documented_as_not_interleavable(fpc):
    """argparse cannot interleave positionals with options; the operator sees only
    'unrecognized arguments'.  Pinned so the help text keeps saying so."""
    parser = fpc.build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["a.example", "-v", "b.example"])
    assert "cannot interleave" in parser.format_help()


# --- Task 1: the output basename -------------------------------------------------------------

def test_output_paths_appends_the_four_suffixes(fpc):
    paths = fpc.output_paths("engin-zone")
    assert paths == ("engin-zone.json", "engin-zone-plan.json",
                     "engin-zone-revert.json", "engin-zone-excluded.json")
    assert paths.inventory == "engin-zone.json"
    assert paths.excluded == "engin-zone-excluded.json"


@pytest.mark.parametrize("basename", ["engin-zone", "out/engin-zone", "out/v1.2/engin-zone"])
def test_check_basename_accepts_a_dotless_final_component(fpc, tmp_path, basename):
    """A dot in a DIRECTORY component is fine; only the filename component is checked (R2.2)."""
    target = tmp_path / basename
    target.parent.mkdir(parents=True, exist_ok=True)
    assert fpc.check_basename(str(target)) == str(target)


@pytest.mark.parametrize("basename", ["engin-zone.json", "engin.umich.edu", ".hidden",
                                      "report.txt"])
def test_check_basename_rejects_an_extension(fpc, tmp_path, basename):
    """The old `-o platform-domains-cloudflare.json` is muscle memory and would otherwise
    produce platform-domains-cloudflare.json.json (R2.2)."""
    with pytest.raises(fpc.StartupError) as excinfo:
        fpc.check_basename(str(tmp_path / basename))
    assert basename in str(excinfo.value)
    assert "extension" in str(excinfo.value)


def test_check_basename_rejects_a_directory_with_no_filename_component(fpc, tmp_path):
    """Path('out/').name is 'out', so a Path-based check would ACCEPT this; os.path.basename
    returns '' and catches it (R2.2)."""
    with pytest.raises(fpc.StartupError) as excinfo:
        fpc.check_basename(f"{tmp_path}/")
    assert "no filename component" in str(excinfo.value)


def test_check_basename_rejects_an_unwritable_directory(fpc, tmp_path):
    """R2.4: the sweep takes ~2 minutes and today's write failure surfaces only after it."""
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        with pytest.raises(fpc.StartupError) as excinfo:
            fpc.check_basename(str(locked / "engin-zone"))
    finally:
        locked.chmod(0o700)
    assert "cannot write output files" in str(excinfo.value)


def test_check_basename_leaves_no_probe_file_behind(fpc, tmp_path):
    """The probe proves writability; leaving it would litter the operator's directory."""
    fpc.check_basename(str(tmp_path / "engin-zone"))
    assert list(tmp_path.iterdir()) == []


def test_the_output_option_takes_a_basename_not_a_path(fpc, tmp_path, monkeypatch, capsys):
    """R2.1: -o/--output-basename replaces -o/--output."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch,
               fpc.SweepResult({"a.example.edu": swept(proxied=False)}, [], 1, 2, 5, 1, 0, 0, 2))
    fake_dns(fpc, monkeypatch, ENTRY_HAPPY_DNS)
    assert fpc.main(["-o", "engin-zone"]) == 0
    # An INDEPENDENTLY built expected dict, never the object main() mutated (task 4 review round
    # 3, finding 2 residual) -- see the sibling comment above for why that assertion shape is a
    # dead instrument.  resolved_a/resolved_aaaa below are the literal values ENTRY_HAPPY_DNS
    # tells fake_dns to answer with.
    expected = swept(proxied=False)
    expected["resolved_a"] = ["23.185.0.4"]
    expected["resolved_aaaa"] = ["2620:12a:8000::4"]
    assert json.loads((tmp_path / "engin-zone.json").read_text()) == {"a.example.edu": expected}


def test_the_old_output_path_form_is_rejected_before_any_api_call(fpc, tmp_path, monkeypatch,
                                                                  capsys):
    """The probe must fire BEFORE cloudflare_client, or an operator waits ~2 minutes to learn
    they mistyped the destination (R2.4)."""
    monkeypatch.chdir(tmp_path)

    def explode(config_path):
        raise AssertionError("cloudflare_client must not be reached")

    monkeypatch.setattr(fpc, "cloudflare_client", explode)
    assert fpc.main(["-o", "platform-domains-cloudflare.json"]) == 2
    assert "contains a file extension" in capsys.readouterr().err


def test_bare_double_dash_output_is_not_accepted(fpc, capsys):
    """allow_abbrev=False, so no prefix match rescues the removed spelling."""
    with pytest.raises(SystemExit):
        fpc.build_arg_parser().parse_args(["--output", "engin-zone"])


# --- Task 1 review fixes ----------------------------------------------------------------------

def test_a_blank_output_basename_is_rejected_not_treated_as_stdout_mode(fpc, tmp_path, monkeypatch,
                                                                        capsys):
    """R2.2: `-o ""` must fail through check_basename's "no filename component" rule.  A
    truthiness test (`if options.output_basename else None`) would treat "" the same as no -o
    at all and silently fall back to stdout mode -- a real regression from the pre-Task-1
    behavior, where an empty PATH was a real destination attempt that failed loudly via the
    existing OSError -> StartupError path (task review, finding 1)."""
    monkeypatch.chdir(tmp_path)

    def explode(config_path):
        raise AssertionError("cloudflare_client must not be reached")

    monkeypatch.setattr(fpc, "cloudflare_client", explode)
    assert fpc.main(["-o", ""]) == 2
    assert "no filename component" in capsys.readouterr().err


def test_an_interrupt_before_paths_is_assigned_does_not_crash_with_unboundlocalerror(
        fpc, tmp_path, monkeypatch, capsys):
    """A KeyboardInterrupt landing before `paths` is assigned -- e.g. inside
    require_usable_streams, which runs first in main()'s try block -- must still report the
    interrupt normally.  Without `paths = None` initialized ahead of the try, the except
    KeyboardInterrupt clause's `paths=paths` read raises UnboundLocalError instead (task review,
    finding 2)."""
    monkeypatch.chdir(tmp_path)

    def interrupt(output):
        raise KeyboardInterrupt

    monkeypatch.setattr(fpc, "require_usable_streams", interrupt)
    assert fpc.main(["-o", "engin-zone"]) == 130
    assert "no complete JSON document was produced" in capsys.readouterr().err


# --- Task 2: the DNS layer -------------------------------------------------------------------

def fake_dns(fpc, monkeypatch, answers):
    """Patch the ONE DNS seam.  `answers` maps (hostname, rrtype) to a list of address strings,
    or to an exception INSTANCE to raise.  Nothing in this suite may touch real DNS (SPEC 7)."""
    calls = []

    def fake(hostname, rrtype):
        calls.append((hostname, rrtype))
        answer = answers[(hostname, rrtype)]
        if isinstance(answer, BaseException):
            raise answer
        return answer

    monkeypatch.setattr(fpc, "resolve", fake)
    return calls


def test_sorted_addresses_orders_by_value_not_lexically(fpc):
    """23.185.0.10 sorts BEFORE 23.185.0.4 as a string.  A lexical sort would make the plan
    file's post order depend on nothing meaningful (SPEC 5.2)."""
    assert fpc.sorted_addresses(["23.185.0.10", "23.185.0.4", "23.185.0.2"]) == [
        "23.185.0.2", "23.185.0.4", "23.185.0.10"]


def test_sorted_addresses_normalizes_rotating_rrset_order(fpc):
    """Measured 2026-07-31: two live AAAA queries returned the pair in OPPOSITE orders, so
    without this no two sweeps produce identical bytes (SPEC 1, SPEC 5.2)."""
    one = fpc.sorted_addresses(["2620:12a:8001::4", "2620:12a:8000::4"])
    two = fpc.sorted_addresses(["2620:12a:8000::4", "2620:12a:8001::4"])
    assert one == two == ["2620:12a:8000::4", "2620:12a:8001::4"]


def test_resolve_target_returns_both_sorted_rrsets(fpc, monkeypatch):
    fake_dns(fpc, monkeypatch, {
        ("live-a.pantheonsite.io", "A"): ["23.185.0.4"],
        ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8001::4", "2620:12a:8000::4"],
    })
    assert fpc.resolve_target("live-a.pantheonsite.io") == (
        ["23.185.0.4"], ["2620:12a:8000::4", "2620:12a:8001::4"], "")


def test_resolve_target_reports_a_definitive_absence_as_empty_not_null(fpc, monkeypatch):
    """R4.4: [] means "definitively none", null means "we do not know"."""
    fake_dns(fpc, monkeypatch, {
        ("live-a.pantheonsite.io", "A"): dns.resolver.NoAnswer(),
        ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8000::4"],
    })
    result = fpc.resolve_target("live-a.pantheonsite.io")
    assert result.a == []
    assert result.problem == ""


def test_resolve_target_reports_an_indeterminate_lookup_as_null(fpc, monkeypatch):
    """R4.4 again, the other half: a timeout must never be rendered as "no records"."""
    fake_dns(fpc, monkeypatch, {("live-a.pantheonsite.io", "A"): dns.resolver.Timeout()})
    result = fpc.resolve_target("live-a.pantheonsite.io")
    assert result.a is None
    assert result.aaaa is None
    assert "Timeout" in result.problem


def test_resolve_target_keeps_a_good_a_when_only_aaaa_is_indeterminate(fpc, monkeypatch):
    """The A answer was definitive and is still evidence; only the unknown half goes null."""
    fake_dns(fpc, monkeypatch, {
        ("live-a.pantheonsite.io", "A"): ["23.185.0.4"],
        ("live-a.pantheonsite.io", "AAAA"): dns.resolver.NoNameservers(),
    })
    result = fpc.resolve_target("live-a.pantheonsite.io")
    assert result.a == ["23.185.0.4"]
    assert result.aaaa is None
    assert "NoNameservers" in result.problem


def test_resolve_target_reports_a_malformed_name_as_indeterminate(fpc, monkeypatch):
    fake_dns(fpc, monkeypatch,
             {("a..b.pantheonsite.io", "A"): fpc.MalformedNameError("a..b: SyntaxError")})
    assert fpc.resolve_target("a..b.pantheonsite.io").problem.startswith("MalformedNameError")


def test_resolve_retrying_retries_a_timeout_exactly_once(fpc, monkeypatch):
    """R3.3.  Exactly once: a retry loop would multiply a whole sweep's wall time by the
    resolver's timeout on a systemic failure."""
    attempts = []

    def flaky(hostname, rrtype):
        attempts.append(rrtype)
        if len(attempts) == 1:
            raise dns.resolver.Timeout
        return ["23.185.0.4"]

    monkeypatch.setattr(fpc, "resolve", flaky)
    assert fpc.resolve_retrying("live-a.pantheonsite.io", "A") == ["23.185.0.4"]
    assert attempts == ["A", "A"]


def test_resolve_retrying_gives_up_after_the_second_failure(fpc, monkeypatch):
    attempts = []

    def always_down(hostname, rrtype):
        attempts.append(rrtype)
        raise dns.resolver.Timeout

    monkeypatch.setattr(fpc, "resolve", always_down)
    monkeypatch.setattr(fpc.time, "sleep", lambda seconds: None)
    with pytest.raises(dns.resolver.Timeout):
        fpc.resolve_retrying("live-a.pantheonsite.io", "A")
    assert attempts == ["A", "A"]


def test_resolve_retrying_sleeps_before_retrying_a_nonameservers(fpc, monkeypatch):
    """Copied reasoning from find-platform-domains-dns:139 -- a Timeout has already consumed
    dnspython's ~5s lifetime, but NoNameservers returns in ~0.3s and is most often the recursive
    resolver rate-limiting us, so an immediate retry re-fires into the same condition."""
    slept = []
    monkeypatch.setattr(fpc.time, "sleep", slept.append)
    attempts = []

    def flaky(hostname, rrtype):
        attempts.append(rrtype)
        if len(attempts) == 1:
            raise dns.resolver.NoNameservers
        return ["23.185.0.4"]

    monkeypatch.setattr(fpc, "resolve", flaky)
    assert fpc.resolve_retrying("live-a.pantheonsite.io", "A") == ["23.185.0.4"]
    assert slept == [fpc.DNS_RETRY_SLEEP]


# --- Task 3: zone_name, the raw name, and ambiguity exclusion --------------------------------

def test_collect_entries_records_the_raw_name_and_the_zone_name(fpc):
    """The inventory key is normalize()d, but a batch POST body's `name` must be exactly what
    Cloudflare holds -- Punycode included (R4.2)."""
    entries, warnings, excluded = fpc.collect_entries(
        [("zone-a", "example.edu", record(name="WWW.Example.edu"))])
    assert list(entries) == ["www.example.edu"]
    assert entries["www.example.edu"]["name"] == "WWW.Example.edu"
    assert entries["www.example.edu"]["zone_name"] == "example.edu"
    assert (warnings, excluded) == ([], {})


def test_collect_entries_excludes_a_name_with_two_platform_cnames_in_one_zone(fpc):
    """R4.1: the entry would keep the FIRST record_id of two and present it as actionable.

    `warnings == []`: the operator-facing line for this exclusion is now main()'s uniform R7.1
    ATTENTION, not a second one collect_entries() used to append (task 6 report, decision A) --
    see test_an_ambiguous_exclusion_produces_exactly_one_operator_line (Task 6 section)."""
    entries, warnings, excluded = fpc.collect_entries([
        ("zone-a", "example.edu", record(name="a.example.edu", id="rec-1",
                                         content="live-one.pantheonsite.io")),
        ("zone-a", "example.edu", record(name="a.example.edu", id="rec-2",
                                         content="live-two.pantheonsite.io")),
    ])
    assert entries == {}
    assert excluded["a.example.edu"]["reason"] == "ambiguous-multiple-origins"
    assert excluded["a.example.edu"]["origins"] == ["live-one.pantheonsite.io",
                                                   "live-two.pantheonsite.io"]
    assert excluded["a.example.edu"]["zone_ids"] == ["zone-a"]
    assert warnings == []


def test_collect_entries_excludes_a_name_present_in_two_zones(fpc):
    entries, _warnings, excluded = fpc.collect_entries([
        ("zone-a", "example.edu", record(name="a.example.edu", id="rec-1")),
        ("zone-b", "example.org", record(name="a.example.edu", id="rec-2")),
    ])
    assert entries == {}
    assert excluded["a.example.edu"]["reason"] == "ambiguous-multiple-zones"
    assert excluded["a.example.edu"]["zone_ids"] == ["zone-a", "zone-b"]


def test_a_cross_zone_duplicate_outranks_a_same_zone_duplicate(fpc):
    """One FQDN carries exactly one reason code (SPEC 6).  Cross-zone is the more serious
    finding -- it means two Cloudflare zones both answer for the name -- so it wins."""
    entries, _warnings, excluded = fpc.collect_entries([
        ("zone-a", "example.edu", record(name="a.example.edu", id="rec-1",
                                         content="live-one.pantheonsite.io")),
        ("zone-a", "example.edu", record(name="a.example.edu", id="rec-2",
                                         content="live-two.pantheonsite.io")),
        ("zone-b", "example.org", record(name="a.example.edu", id="rec-3")),
    ])
    assert entries == {}
    assert excluded["a.example.edu"]["reason"] == "ambiguous-multiple-zones"


def test_an_unambiguous_neighbour_survives_an_ambiguous_entry(fpc):
    """Exclusion is per-FQDN, never per-zone or per-run."""
    entries, _warnings, excluded = fpc.collect_entries([
        ("zone-a", "example.edu", record(name="a.example.edu", id="rec-1")),
        ("zone-b", "example.org", record(name="a.example.edu", id="rec-2")),
        ("zone-a", "example.edu", record(name="b.example.edu", id="rec-3")),
    ])
    assert list(entries) == ["b.example.edu"]
    assert list(excluded) == ["a.example.edu"]


def test_fetch_platform_cnames_carries_the_excluded_map_on_the_sweep_result(fpc):
    client = FakeCloudflareClient(
        accounts=[account()],
        zones=[zone("zone-a"), zone("zone-b", "example.org")],
        pages_by_zone={
            "zone-a": [FakePage([[record(name="a.example.edu", id="rec-1")]], total_count=1)],
            "zone-b": [FakePage([[record(name="a.example.edu", id="rec-2")]], total_count=1)],
        })
    sweep = fpc.fetch_platform_cnames(client)
    assert sweep.entries == {}
    assert sweep.excluded["a.example.edu"]["reason"] == "ambiguous-multiple-zones"


def test_the_sweep_result_excluded_default_cannot_be_mutated(fpc):
    """A shared mutable default on a NamedTuple is a cross-test contamination bug waiting to
    happen; MappingProxyType makes an attempted write loud (PD#14)."""
    sweep = fpc.SweepResult({}, [], 1, 2, 5, 1, 0, 0, 187)
    with pytest.raises(TypeError):
        sweep.excluded["oops"] = {}


# --- Task 3 review fixes ----------------------------------------------------------------------

def test_fetch_platform_cnames_wires_the_real_zone_name_not_the_zone_id(fpc):
    """FINDING 1 (task 3 review): zone.name reaches collect_entries through exactly one place --
    the `yield zone.id, zone.name, dns_record` line in fetch_platform_cnames's zone_records()
    generator.  Every other test either calls collect_entries directly (bypassing that line) or
    uses a zone id/name pair that happen to differ only coincidentally.  Here the zone id
    ("zone-a") and zone name ("engin.umich.edu") are deliberately distinct and neither looks like
    the other, so a regression that yields zone.id twice (`zone.id, zone.id, dns_record`) is
    caught: `zone_name` would read back "zone-a", not "engin.umich.edu"."""
    client = FakeCloudflareClient(
        accounts=[account()],
        zones=[zone("zone-a", "engin.umich.edu")],
        pages_by_zone={"zone-a": [FakePage([[record(name="a.engin.umich.edu")]],
                                           total_count=1)]})
    sweep = fpc.fetch_platform_cnames(client)
    assert sweep.entries["a.engin.umich.edu"]["zone_name"] == "engin.umich.edu"


def test_collect_entries_excluded_entry_carries_the_kept_record_id(fpc):
    """FINDING 3 (task 3 review): SPEC section 5.6's own worked example puts the kept record_id
    in `detail` ("kept record_id 9f1c...") -- discarding it left an operator unable to act on
    -excluded.json without re-sweeping Cloudflare.  The kept id (the first one seen) is asserted
    both as its own field and inside `detail`'s text."""
    entries, _warnings, excluded = fpc.collect_entries([
        ("zone-a", "example.edu", record(name="a.example.edu", id="rec-1",
                                         content="live-one.pantheonsite.io")),
        ("zone-a", "example.edu", record(name="a.example.edu", id="rec-2",
                                         content="live-two.pantheonsite.io")),
    ])
    assert entries == {}
    excluded_entry = excluded["a.example.edu"]
    assert excluded_entry["record_id"] == "rec-1"
    assert "rec-1" in excluded_entry["detail"]


def test_collect_entries_excluded_entry_carries_every_duplicates_record_id(fpc):
    """FINDING 3 (task 3 review), the "later duplicates' ids too" half: the second (and any
    further) record's id is never captured anywhere today -- not even in a local variable --
    so it is unrecoverable once the sweep ends.  `record_ids` preserves all of them, in the
    order the sweep saw them, across all zones a cross-zone duplicate spans."""
    entries, _warnings, excluded = fpc.collect_entries([
        ("zone-a", "example.edu", record(name="a.example.edu", id="rec-1")),
        ("zone-b", "example.org", record(name="a.example.edu", id="rec-2")),
    ])
    assert entries == {}
    assert excluded["a.example.edu"]["record_ids"] == ["rec-1", "rec-2"]


def test_collect_entries_excluded_entry_detail_is_never_blank(fpc):
    """FINDING 5 (task 3 review): SPEC section 5.6 makes `detail` one of the two keys every
    exclusion entry MUST carry.  Nothing previously asserted its content, so blanking it to ""
    left the whole suite green.  Pin real content: the CNAME count, the zone(s), and the kept
    record_id -- not merely "truthy"."""
    entries, _warnings, excluded = fpc.collect_entries([
        ("zone-a", "example.edu", record(name="a.example.edu", id="rec-1",
                                         content="live-one.pantheonsite.io")),
        ("zone-a", "example.edu", record(name="a.example.edu", id="rec-2",
                                         content="live-two.pantheonsite.io")),
    ])
    assert entries == {}
    detail = excluded["a.example.edu"]["detail"]
    assert "2 platform-domain CNAMEs" in detail
    assert "zone-a" in detail
    assert "rec-1" in detail


# --- Task 4: classify and the reason codes ----------------------------------------------------

def swept(**overrides):
    """An inventory entry as collect_entries builds one."""
    entry = {"name": "a.example.edu", "zone_id": "zone-a", "zone_name": "example.edu",
             "origins": ["live-a.pantheonsite.io"], "record_id": "rec-1", "proxied": True,
             "ttl": 1, "comment": None, "tags": [], "settings": None}
    entry.update(overrides)
    return entry


def test_classify_passes_a_healthy_proxied_entry(fpc):
    resolution = fpc.Resolution(["23.185.0.4"], ["2620:12a:8000::4"], "")
    assert fpc.classify(swept(), resolution) == (None, "")


def test_classify_passes_a_dns_only_entry(fpc):
    """5 of 218 in the last live sweep.  The swap is type-only and preserves proxied=false,
    so a DNS-only entry is NOT excluded (SPEC 6)."""
    resolution = fpc.Resolution(["23.185.0.4"], ["2620:12a:8000::4"], "")
    assert fpc.classify(swept(proxied=False), resolution) == (None, "")


def test_classify_excludes_an_unknown_proxy_status(fpc):
    resolution = fpc.Resolution(["23.185.0.4"], ["2620:12a:8000::4"], "")
    reason, detail = fpc.classify(swept(proxied=None), resolution)
    assert reason == "unknown-proxy-status"
    assert "null" in detail


def test_classify_excludes_an_indeterminate_resolution_before_testing_for_no_a(fpc):
    """SPEC 6, evaluation order: resolution-failed (8) MUST be tested before no-a (4).  With
    `a` null, a `not a` test treats "we do not know" and "definitively none" alike, and would
    report a timeout as "the target has no A records" (R4.4)."""
    resolution = fpc.Resolution(None, None, "Timeout resolving A for live-a.pantheonsite.io")
    reason, detail = fpc.classify(swept(), resolution)
    assert reason == "resolution-failed"
    assert "Timeout" in detail


def test_classify_excludes_a_target_with_no_a_records(fpc):
    resolution = fpc.Resolution([], ["2620:12a:8000::4"], "")
    assert fpc.classify(swept(), resolution)[0] == "no-a"


def test_classify_excludes_an_a_record_outside_the_pantheon_range(fpc):
    resolution = fpc.Resolution(["104.18.2.7"], ["2620:12a:8000::4"], "")
    reason, detail = fpc.classify(swept(), resolution)
    assert reason == "platform-a-out-of-range"
    assert "104.18.2.7" in detail
    assert "23.185.0.0/24" in detail


def test_classify_excludes_a_mixed_a_rrset_even_though_one_address_is_in_range(fpc):
    """SPEC 6: EVERY resolved A must be in range, not merely one.  Under a >=1 rule the plan
    would post 104.18.2.7 as a proxied origin."""
    resolution = fpc.Resolution(["23.185.0.4", "104.18.2.7"], ["2620:12a:8000::4"], "")
    assert fpc.classify(swept(), resolution)[0] == "platform-a-out-of-range"


def test_classify_excludes_a_target_with_no_aaaa_records(fpc):
    resolution = fpc.Resolution(["23.185.0.4"], [], "")
    assert fpc.classify(swept(), resolution)[0] == "no-aaaa"


def test_classify_excludes_an_aaaa_record_outside_the_pantheon_range(fpc):
    resolution = fpc.Resolution(["23.185.0.4"], ["2606:4700::1111"], "")
    reason, detail = fpc.classify(swept(), resolution)
    assert reason == "platform-aaaa-out-of-range"
    assert "2620:12a::/32" in detail


def test_classify_accepts_both_live_observed_address_sets(fpc):
    """Measured 2026-07-31 against live DNS; a range that rejected either would be wrong."""
    for a, aaaa in ((["23.185.0.4"], ["2620:12a:8000::4", "2620:12a:8001::4"]),
                    (["23.185.0.1"], ["2620:12a:8000::1", "2620:12a:8001::1"])):
        assert fpc.classify(swept(), fpc.Resolution(a, aaaa, "")) == (None, "")


def test_main_records_the_resolved_addresses_on_each_inventory_entry(fpc, tmp_path, monkeypatch,
                                                                     capsys):
    """R4.2/Expansion 2: the inventory carries the evidence behind every plan entry."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": swept()}, [], 1, 2, 5, 1, 0, 0, 2))
    fake_dns(fpc, monkeypatch, {
        ("live-a.pantheonsite.io", "A"): ["23.185.0.4"],
        ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8000::4", "2620:12a:8001::4"],
    })
    assert fpc.main([]) == 0
    written = json.loads(capsys.readouterr().out)
    assert written["a.example.edu"]["resolved_a"] == ["23.185.0.4"]
    assert written["a.example.edu"]["resolved_aaaa"] == ["2620:12a:8000::4", "2620:12a:8001::4"]


def test_main_resolves_in_stdout_mode_too(fpc, tmp_path, monkeypatch, capsys):
    """R3.2: if resolution were basename-mode only, the two modes would produce different
    inventories for the same sweep -- the divergence dump_json() exists to prevent."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": swept()}, [], 1, 2, 5, 1, 0, 0, 2))
    calls = fake_dns(fpc, monkeypatch, {
        ("live-a.pantheonsite.io", "A"): ["23.185.0.4"],
        ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8000::4"],
    })
    assert fpc.main([]) == 0
    assert calls == [("live-a.pantheonsite.io", "A"), ("live-a.pantheonsite.io", "AAAA")]


def test_main_exits_1_and_names_every_exclusion_on_stderr(fpc, tmp_path, monkeypatch, capsys):
    """R7.1/R7.3: unconditional, not -v-gated.  A file that drives a destructive rewrite while
    the warnings about it go nowhere is the failure this design is organized against."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": swept()}, [], 1, 2, 5, 1, 0, 0, 2))
    fake_dns(fpc, monkeypatch, {("live-a.pantheonsite.io", "A"): ["104.18.2.7"],
                                ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8000::4"]})
    assert fpc.main([]) == 1
    err = capsys.readouterr().err
    assert "a.example.edu" in err
    assert "platform-a-out-of-range" in err


def test_main_exits_1_for_an_ambiguous_entry_in_stdout_mode(fpc, tmp_path, monkeypatch, capsys):
    """The one exclusion detectable without DNS, and the one that also leaves the inventory."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult(
        {}, [], 1, 2, 5, 1, 0, 0, 2,
        {"a.example.edu": {"reason": "ambiguous-multiple-zones", "detail": "two zones",
                           "zone_ids": ["z1", "z2"], "origins": ["live-a.pantheonsite.io"]}}))
    assert fpc.main([]) == 1
    assert json.loads(capsys.readouterr().out) == {}


def test_main_exits_0_when_nothing_was_excluded(fpc, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": swept()}, [], 1, 2, 5, 1, 0, 0, 2))
    fake_dns(fpc, monkeypatch, {("live-a.pantheonsite.io", "A"): ["23.185.0.4"],
                                ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8000::4"]})
    assert fpc.main([]) == 0


def test_an_indeterminate_lookup_leaves_null_in_the_inventory_not_an_empty_list(
        fpc, tmp_path, monkeypatch, capsys):
    """R4.4 end to end: [] would tell an operator the target has no addresses."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": swept()}, [], 1, 2, 5, 1, 0, 0, 2))
    fake_dns(fpc, monkeypatch, {("live-a.pantheonsite.io", "A"): dns.resolver.Timeout()})
    assert fpc.main([]) == 1
    written = json.loads(capsys.readouterr().out)
    assert written["a.example.edu"]["resolved_a"] is None
    assert written["a.example.edu"]["resolved_aaaa"] is None


# --- Task 4 review fixes (findings 3 and 4) ---------------------------------------------------

def test_summarize_reports_excluded_counts_by_reason_code(fpc, tmp_path, monkeypatch, capsys):
    """SPEC section 10: the always-printed summary gains 'a count of exclusions by reason code'.
    This had ZERO coverage before -- deleting summarize()'s whole `if excluded:` block left the
    suite green (task 4 review, finding 3).  Mutation used to confirm red: temporarily removed
    that block; this test failed (see FIX REPORT in task-4-report.md for the pasted red run).

    Two DIFFERENT reason codes with a known count each, so the test pins the format precisely --
    "N reason, M reason", sorted by reason, comma-joined -- not merely "something got printed"."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult(
        {"a.example.edu": swept(name="a.example.edu"),
         "b.example.edu": swept(name="b.example.edu", proxied=None,
                                origins=["live-b.pantheonsite.io"])},
        [], 1, 2, 10, 1, 0, 0, 2))
    fake_dns(fpc, monkeypatch, {
        ("live-a.pantheonsite.io", "A"): [],
        ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8000::4"],
        ("live-b.pantheonsite.io", "A"): ["23.185.0.4"],
        ("live-b.pantheonsite.io", "AAAA"): ["2620:12a:8000::4"],
    })
    assert fpc.main([]) == 1
    err = capsys.readouterr().err
    assert "Excluded from the rewrite plan: 1 no-a, 1 unknown-proxy-status" in err


def test_render_rrset_distinguishes_indeterminate_empty_and_present(fpc):
    """The pure helper in isolation (SPEC section 10 / R4.4, task 4 review, finding 4): three
    shapes that must never render as each other."""
    assert fpc.render_rrset(None) == "indeterminate"
    assert fpc.render_rrset([]) == "none"
    assert fpc.render_rrset(["23.185.0.4"]) == "23.185.0.4"
    assert fpc.render_rrset(["23.185.0.4", "23.185.0.1"]) == "23.185.0.4, 23.185.0.1"


def test_verbose_reports_target_resolution_in_the_spec_documented_format(fpc, tmp_path,
                                                                         monkeypatch, capsys):
    """SPEC section 10's exact documented line: 'live-umich-x.pantheonsite.io -> A 23.185.0.4 |
    AAAA 2620:12a:8000::4, 2620:12a:8001::4'.  The brief's code printed Python's list repr
    instead (`A ['23.185.0.4']`) and prefixed the fqdn, which SPEC's example does not have (task 4
    review, finding 4).  Mutation used to confirm red: reverted the -v print line to the brief's
    original `f"{fqdn} -> {target} -> A {resolution.a} | AAAA {resolution.aaaa}"`; this test
    failed (see FIX REPORT in task-4-report.md for the pasted red run)."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult(
        {"a.example.edu": swept(origins=["live-umich-x.pantheonsite.io"])}, [], 1, 2, 5, 1, 0, 0, 2))
    fake_dns(fpc, monkeypatch, {
        ("live-umich-x.pantheonsite.io", "A"): ["23.185.0.4"],
        ("live-umich-x.pantheonsite.io", "AAAA"): ["2620:12a:8000::4", "2620:12a:8001::4"],
    })
    assert fpc.main(["-v"]) == 0
    err = capsys.readouterr().err
    assert ("live-umich-x.pantheonsite.io -> A 23.185.0.4 | AAAA 2620:12a:8000::4, "
            "2620:12a:8001::4") in err


def test_verbose_renders_an_indeterminate_resolution_as_the_word_indeterminate(fpc, tmp_path,
                                                                               monkeypatch,
                                                                               capsys):
    """R4.4 carried into the -v line (task 4 review, finding 4): an f-string's bare `{None}`
    would print the literal word "None", which is not visibly different from a real value at a
    glance."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": swept()}, [], 1, 2, 5, 1, 0, 0, 2))
    fake_dns(fpc, monkeypatch, {("live-a.pantheonsite.io", "A"): dns.resolver.Timeout()})
    assert fpc.main(["-v"]) == 1
    err = capsys.readouterr().err
    assert "live-a.pantheonsite.io -> A indeterminate | AAAA indeterminate" in err


def test_verbose_renders_a_definitive_empty_rrset_as_none_not_indeterminate(fpc, tmp_path,
                                                                            monkeypatch, capsys):
    """The other half of the same distinction: a DEFINITIVE absence must not read the same as an
    indeterminate one (task 4 review, finding 4)."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": swept()}, [], 1, 2, 5, 1, 0, 0, 2))
    fake_dns(fpc, monkeypatch, {("live-a.pantheonsite.io", "A"): dns.resolver.NoAnswer(),
                                ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8000::4"]})
    assert fpc.main(["-v"]) == 1
    err = capsys.readouterr().err
    assert "live-a.pantheonsite.io -> A none | AAAA 2620:12a:8000::4" in err


# --- Task 5: the batch bodies ----------------------------------------------------------------

FULL_SETTINGS = {"flatten_cname": False, "ipv4_only": True, "ipv6_only": None}


def test_clean_settings_drops_flatten_cname_going_forward(fpc):
    """flatten_cname is not a member of the A/AAAA settings schema, and is already inert on a
    proxied CNAME: "unavailable for proxied records, since they are always flattened" (R6)."""
    assert fpc.clean_settings(FULL_SETTINGS, drop_cname_only=True) == {"ipv4_only": True}


def test_clean_settings_keeps_flatten_cname_going_back(fpc):
    assert fpc.clean_settings(FULL_SETTINGS, drop_cname_only=False) == {
        "flatten_cname": False, "ipv4_only": True}


def test_clean_settings_returns_none_when_nothing_survives(fpc):
    """R6.1: an empty settings object is omitted from the body, not sent as {}."""
    assert fpc.clean_settings({"flatten_cname": True}, drop_cname_only=True) is None
    assert fpc.clean_settings(None, drop_cname_only=True) is None
    assert fpc.clean_settings({}, drop_cname_only=False) is None


@pytest.mark.parametrize(("proxied", "ttl"), [(True, 1), (False, 300)])
def test_record_body_always_emits_proxied(fpc, proxied, ttl):
    """R6: the API default is false, and a silently DNS-only replacement takes the hostname out
    of certificate service.

    Parametrized over BOTH proxy states (whole-branch review, finding 1).  It used to assert only
    the proxied=False case -- 5 of 218 records in the last live sweep -- so mutating
    `"proxied": proxied` to `"proxied": False` inside record_body left the entire suite green
    while every one of the other 213 hostnames would have been re-created DNS-only, out of
    certificate service.  `is`, not `==`: True == 1 in Python, and the API distinguishes them."""
    body = fpc.record_body(swept(proxied=proxied, ttl=ttl), "A", "23.185.0.4", None)
    assert body["proxied"] is proxied


def test_record_body_forces_ttl_1_when_proxied(fpc):
    """Cloudflare forces a proxied record's TTL to Auto regardless, and whether the API rejects
    or coerces a non-1 ttl is documented silence we do not build on (R6)."""
    assert fpc.record_body(swept(proxied=True, ttl=300), "A", "23.185.0.4", None)["ttl"] == 1


def test_record_body_carries_a_dns_only_ttl_verbatim(fpc):
    assert fpc.record_body(swept(proxied=False, ttl=300), "A", "23.185.0.4", None)["ttl"] == 300


def test_record_body_falls_back_to_ttl_1_when_dns_only_ttl_is_missing(fpc):
    """R6's ttl rule has a THIRD case beyond "proxied -> 1" / "dns-only -> verbatim" (task 5
    review, finding 1): a null/zero swept ttl on a DNS-only record also falls back to 1
    ("automatic"), because ttl is a required field (SPEC R4.3) and there is no better answer.
    `collect_entries()` reads ttl via `getattr(..., None)` defensively, so a record missing the
    attribute -- which should not happen, since every record model declares it -- is the only way
    this null shape can arise; it is covered rather than assumed unreachable."""
    assert fpc.record_body(swept(proxied=False, ttl=None), "A", "23.185.0.4", None)["ttl"] == 1


def test_record_body_omits_a_null_comment_and_empty_tags(fpc):
    body = fpc.record_body(swept(), "A", "23.185.0.4", None)
    assert "comment" not in body
    assert "tags" not in body
    assert "settings" not in body


def test_record_body_carries_a_comment_and_tags(fpc):
    body = fpc.record_body(swept(comment="owned by ITS", tags=["team:wws"]),
                           "A", "23.185.0.4", {"ipv4_only": True})
    assert body["comment"] == "owned by ITS"
    assert body["tags"] == ["team:wws"]
    assert body["settings"] == {"ipv4_only": True}


def test_record_body_uses_the_raw_record_name(fpc):
    assert fpc.record_body(swept(name="WWW.Example.edu"), "A", "23.185.0.4", None)["name"] == \
        "WWW.Example.edu"


def test_proxied_ttl_anomaly_flags_a_proxied_record_whose_ttl_is_not_1(fpc):
    assert fpc.proxied_ttl_anomaly(swept(proxied=True, ttl=300)) is True
    assert fpc.proxied_ttl_anomaly(swept(proxied=True, ttl=1)) is False
    assert fpc.proxied_ttl_anomaly(swept(proxied=False, ttl=300)) is False


def test_plan_entry_deletes_the_cname_and_posts_the_addresses(fpc):
    resolution = fpc.Resolution(["23.185.0.4"],
                                ["2620:12a:8000::4", "2620:12a:8001::4"], "")
    entry = fpc.plan_entry(swept(settings=FULL_SETTINGS), resolution)
    assert entry["zone_id"] == "zone-a"
    assert entry["method"] == "POST"
    assert entry["path"] == "/zones/zone-a/dns_records/batch"
    assert entry["delete_match"] == [
        {"type": "CNAME", "name": "a.example.edu", "content": "live-a.pantheonsite.io"}]
    assert [p["type"] for p in entry["body"]["posts"]] == ["A", "AAAA", "AAAA"]
    assert [p["content"] for p in entry["body"]["posts"]] == [
        "23.185.0.4", "2620:12a:8000::4", "2620:12a:8001::4"]
    assert all(p["settings"] == {"ipv4_only": True} for p in entry["body"]["posts"])


def test_the_plan_posts_reproduce_every_writable_field_of_a_proxied_entry(fpc):
    """R6, the PLAN-side mirror of test_the_revert_reproduces_every_writable_field_of_the_swept
    _cname (whole-branch review, finding 1).  That one -- the branch's only exhaustive
    `post == {...}` -- runs on a proxied=FALSE entry, so before this test nothing in the suite
    could go red on a plan `posts` item emitted DNS-only.  research.md: "proxied: true is the
    load-bearing field in both directions"; under "What would break it" the first bullet is
    "Creating the replacement records DNS-only instead of proxied".

    Exhaustive `==` on the whole dict rather than per-key asserts: a MISSING or EXTRA key is a
    defect too, and only equality catches one.  This pins, in one instrument: proxied carried
    true, ttl forced to 1, flatten_cname dropped forward, a null-valued setting dropped (R6.1),
    ipv4_only carried, and comment/tags carried."""
    entry = swept(proxied=True, ttl=1, comment="owned by ITS", tags=["team:wws"],
                  settings={"flatten_cname": False, "ipv4_only": True, "ipv6_only": None})
    plan = fpc.plan_entry(entry, fpc.Resolution(["23.185.0.4"], ["2620:12a:8000::4"], ""))
    a_post, aaaa_post = plan["body"]["posts"]
    assert a_post == {"type": "A", "name": "a.example.edu", "content": "23.185.0.4",
                      "proxied": True, "ttl": 1, "settings": {"ipv4_only": True},
                      "comment": "owned by ITS", "tags": ["team:wws"]}
    assert aaaa_post == {"type": "AAAA", "name": "a.example.edu",
                         "content": "2620:12a:8000::4",
                         "proxied": True, "ttl": 1, "settings": {"ipv4_only": True},
                         "comment": "owned by ITS", "tags": ["team:wws"]}


def test_plan_entry_keeps_delete_match_outside_the_body(fpc):
    """R5.3: `body` must be a real, postable batch body at all times.  A shape like
    {"deletes": [{"match": ...}]} looks postable and is not."""
    entry = fpc.plan_entry(swept(), fpc.Resolution(["23.185.0.4"], ["2620:12a:8000::4"], ""))
    assert set(entry["body"]) == {"posts"}
    assert "deletes" not in entry["body"]


def test_record_body_refuses_an_entry_with_unknown_proxy_status(fpc):
    """Mirrors the origins invariant above (task 5 review, finding 2): classify() already excludes
    an entry whose swept `proxied` is null upstream (`unknown-proxy-status`, SPEC section 6), so
    this is defense-in-depth, not a live bug -- but a silent null would emit "proxied": null into
    a rewrite body, which Cloudflare defaults to false: the exact certificate-service loss R6's
    always-emit rule exists to prevent.  The invariant is asserted rather than assumed, the same
    reasoning `sole_origin` already gets."""
    with pytest.raises(fpc.InvariantError):
        fpc.record_body(swept(proxied=None), "A", "23.185.0.4", None)


def test_plan_entry_refuses_an_entry_with_more_than_one_origin(fpc):
    """An ambiguous entry never reaches here (Task 3 removes it).  The invariant is asserted
    rather than assumed, because a silent [0] would rewrite one of two records.

    Asserts the NAMED subclass `InvariantError`, not merely `StartupError` (task 5 review,
    finding 3): this is a mid-sweep internal-invariant violation, not an operator error, and the
    two must not collapse into the same anonymous exception."""
    with pytest.raises(fpc.InvariantError):
        fpc.plan_entry(swept(origins=["live-a.pantheonsite.io", "live-b.pantheonsite.io"]),
                       fpc.Resolution(["23.185.0.4"], ["2620:12a:8000::4"], ""))


def test_revert_entry_deletes_the_addresses_and_restores_the_cname(fpc):
    resolution = fpc.Resolution(["23.185.0.4"],
                                ["2620:12a:8000::4", "2620:12a:8001::4"], "")
    entry = fpc.revert_entry(swept(settings=FULL_SETTINGS, comment="note", tags=["t:1"]),
                             resolution)
    assert entry["delete_match"] == [
        {"type": "A", "name": "a.example.edu", "content": "23.185.0.4"},
        {"type": "AAAA", "name": "a.example.edu", "content": "2620:12a:8000::4"},
        {"type": "AAAA", "name": "a.example.edu", "content": "2620:12a:8001::4"}]
    post, = entry["body"]["posts"]
    assert post["type"] == "CNAME"
    assert post["content"] == "live-a.pantheonsite.io"
    assert post["settings"] == {"flatten_cname": False, "ipv4_only": True}


def test_the_revert_reproduces_every_writable_field_of_the_swept_cname(fpc):
    """R5.4, the round-trip property.  The writable CNAME fields are exactly name, type, content,
    ttl, proxied, settings, tags, comment (SPEC R4.3)."""
    entry = swept(settings={"flatten_cname": True, "ipv4_only": False, "ipv6_only": False},
                  comment="owned by ITS", tags=["team:wws"], proxied=False, ttl=300)
    post, = fpc.revert_entry(entry, fpc.Resolution(["23.185.0.4"], ["2620:12a:8000::4"], "")
                             )["body"]["posts"]
    assert post == {"type": "CNAME", "name": "a.example.edu",
                    "content": "live-a.pantheonsite.io", "proxied": False, "ttl": 300,
                    "settings": {"flatten_cname": True, "ipv4_only": False, "ipv6_only": False},
                    "comment": "owned by ITS", "tags": ["team:wws"]}


# --- Task 6: the four files ------------------------------------------------------------------

def freeze_clock(fpc, monkeypatch, stamp="2026-07-31T14:02:11Z"):
    """Pin the ONE clock seam, so all three headed files are byte-deterministic (SPEC 5.5)."""
    monkeypatch.setattr(fpc, "now_utc", lambda: stamp)
    return stamp


def planned_run(fpc, monkeypatch, tmp_path):
    """A one-entry sweep that resolves cleanly, plus a frozen clock."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch,
               fpc.SweepResult({"a.example.edu": swept()}, [], 1, 2, 5, 1, 0, 0, 187))
    fake_dns(fpc, monkeypatch, {
        ("live-a.pantheonsite.io", "A"): ["23.185.0.4"],
        ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8000::4", "2620:12a:8001::4"],
    })
    return freeze_clock(fpc, monkeypatch)


def test_basename_mode_writes_all_four_files(fpc, tmp_path, monkeypatch, capsys):
    planned_run(fpc, monkeypatch, tmp_path)
    assert fpc.main(["-o", "engin-zone"]) == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "engin-zone-excluded.json", "engin-zone-plan.json",
        "engin-zone-revert.json", "engin-zone.json"]


def test_stdout_mode_writes_no_other_file(fpc, tmp_path, monkeypatch, capsys):
    planned_run(fpc, monkeypatch, tmp_path)
    assert fpc.main([]) == 0
    assert list(tmp_path.iterdir()) == []


def test_the_inventory_is_byte_identical_between_the_two_modes(fpc, tmp_path, monkeypatch,
                                                               capsys):
    """R3.2's whole point: `-o x` and `> x.json` must not diverge for the same sweep."""
    planned_run(fpc, monkeypatch, tmp_path)
    assert fpc.main([]) == 0
    from_stdout = capsys.readouterr().out
    planned_run(fpc, monkeypatch, tmp_path)
    assert fpc.main(["-o", "engin-zone"]) == 0
    assert (tmp_path / "engin-zone.json").read_text() == from_stdout


def test_all_three_headed_files_share_one_generated_at(fpc, tmp_path, monkeypatch, capsys):
    """SPEC 9.3: os.replace is atomic per file, not across four.  A shared timestamp is what
    makes a mixed set detectable."""
    stamp = planned_run(fpc, monkeypatch, tmp_path)
    assert fpc.main(["-o", "engin-zone"]) == 0
    for suffix, direction in (("plan", "plan"), ("revert", "revert"), ("excluded", "excluded")):
        header = json.loads((tmp_path / f"engin-zone-{suffix}.json").read_text())["generated"]
        assert header["at"] == stamp
        assert header["direction"] == direction
        assert header["zones_swept"] == 2
        assert header["zones_total"] == 187
        assert header["required_a_range"] == "23.185.0.0/24"
        assert header["required_aaaa_range"] == "2620:12a::/32"


def test_the_header_entry_count_is_per_file(fpc, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult(
        {"a.example.edu": swept(), "b.example.edu": swept(name="b.example.edu",
                                                          origins=["live-b.pantheonsite.io"])},
        [], 1, 2, 5, 1, 0, 0, 187))
    fake_dns(fpc, monkeypatch, {
        ("live-a.pantheonsite.io", "A"): ["23.185.0.4"],
        ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8000::4"],
        ("live-b.pantheonsite.io", "A"): ["104.18.2.7"],
        ("live-b.pantheonsite.io", "AAAA"): ["2620:12a:8000::4"],
    })
    freeze_clock(fpc, monkeypatch)
    assert fpc.main(["-o", "engin-zone"]) == 1
    plan = json.loads((tmp_path / "engin-zone-plan.json").read_text())
    excluded = json.loads((tmp_path / "engin-zone-excluded.json").read_text())
    assert plan["generated"]["entries"] == 1
    assert excluded["generated"]["entries"] == 1
    assert list(plan["entries"]) == ["a.example.edu"]
    assert excluded["entries"]["b.example.edu"]["reason"] == "platform-a-out-of-range"


def test_the_plan_and_revert_hold_the_same_fqdns(fpc, tmp_path, monkeypatch, capsys):
    planned_run(fpc, monkeypatch, tmp_path)
    assert fpc.main(["-o", "engin-zone"]) == 0
    plan = json.loads((tmp_path / "engin-zone-plan.json").read_text())["entries"]
    revert = json.loads((tmp_path / "engin-zone-revert.json").read_text())["entries"]
    assert list(plan) == list(revert) == ["a.example.edu"]


def test_an_excluded_fqdn_gets_no_plan_or_revert_entry(fpc, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch,
               fpc.SweepResult({"a.example.edu": swept(proxied=None)}, [], 1, 2, 5, 1, 0, 0, 187))
    fake_dns(fpc, monkeypatch, {("live-a.pantheonsite.io", "A"): ["23.185.0.4"],
                                ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8000::4"]})
    freeze_clock(fpc, monkeypatch)
    assert fpc.main(["-o", "engin-zone"]) == 1
    assert json.loads((tmp_path / "engin-zone-plan.json").read_text())["entries"] == {}
    assert json.loads((tmp_path / "engin-zone-revert.json").read_text())["entries"] == {}
    assert "unknown-proxy-status" in (tmp_path / "engin-zone-excluded.json").read_text()


def test_a_construction_failure_writes_nothing(fpc, tmp_path, monkeypatch, capsys):
    """SPEC 9.3: all four documents are built in memory BEFORE any of them is written.

    REWRITTEN by the whole-branch review, finding 2 -- a strengthening, not a weakening.  It used
    to assert `pytest.raises(RuntimeError)` around main(), i.e. it ENCODED as correct the very
    hole finding 2 names: a construction error escaping main() uncaught, which CPython turns into
    exit 1 -- the code SPEC section 8 reserves for a completed sweep with exclusions.  It now
    asserts the whole outcome: exit 2, the class named on stderr, and still nothing on disk."""
    planned_run(fpc, monkeypatch, tmp_path)
    monkeypatch.setattr(fpc, "plan_entry",
                        lambda entry, resolution: (_ for _ in ()).throw(RuntimeError("boom")))
    assert fpc.main(["-o", "engin-zone"]) == 2
    assert "ERROR: unexpected RuntimeError: boom" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_the_subset_warning_names_all_four_files(fpc, tmp_path, monkeypatch, capsys):
    """SPEC 9.5: a subset sweep cannot see a cross-zone duplicate, so it can emit a PLAN entry
    for an FQDN a full sweep would have excluded as ambiguous."""
    planned_run(fpc, monkeypatch, tmp_path)
    assert fpc.main(["-o", "engin-zone", "example.edu"]) in (0, 1)
    err = capsys.readouterr().err
    assert "2 of 187 zones" in err
    assert "engin-zone-plan.json" in err
    assert "MUST NOT be used as the baseline" in err


def test_the_summary_counts_exclusions_by_reason(fpc, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch,
               fpc.SweepResult({"a.example.edu": swept(proxied=None)}, [], 1, 2, 5, 1, 0, 0, 187))
    fake_dns(fpc, monkeypatch, {("live-a.pantheonsite.io", "A"): ["23.185.0.4"],
                                ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8000::4"]})
    freeze_clock(fpc, monkeypatch)
    assert fpc.main([]) == 1
    assert "1 unknown-proxy-status" in capsys.readouterr().err


# --- Task 6: controller decisions (task-6-report.md) -----------------------------------------

def test_an_ambiguous_exclusion_produces_exactly_one_operator_line(fpc, tmp_path, monkeypatch,
                                                                    capsys):
    """Controller decision (A): collect_entries() used to append its OWN ATTENTION line for an
    ambiguous FQDN (printed via sweep.warnings, in main()'s `for message in sweep.warnings`
    loop) ON TOP OF main()'s uniform R7.1 exclusion ATTENTION -- two stderr lines reporting one
    fact.  collect_entries() no longer appends that warning; the uniform line -- which carries
    the reason code and is identical in shape across all eight reason codes (SPEC R7.1) -- is
    now the ONLY operator-facing report of this exclusion.

    This drives the REAL fetch_platform_cnames()/collect_entries() path (not a canned
    SweepResult, whose `warnings` field would just echo back whatever the test hardcoded and so
    could never prove collect_entries()'s own behavior).  Rewritten from the two
    test_collect_entries_excludes_*_and_appends_no_warning tests, which asserted the retired
    per-fact warning text directly at the collect_entries() seam; those now assert
    `warnings == []` and point here.  Their names said `_and_warns` until the whole-branch review
    (finding 6) -- a name promising a warning over a body asserting there is none.
    """
    monkeypatch.chdir(tmp_path)
    client = FakeCloudflareClient(
        accounts=[account()],
        zones=[zone("zone-a"), zone("zone-b", "example.org")],
        pages_by_zone={
            "zone-a": [FakePage([[record(name="a.example.edu", id="rec-1",
                                         content="live-a.pantheonsite.io")]], total_count=1)],
            "zone-b": [FakePage([[record(name="a.example.edu", id="rec-2",
                                         content="live-b.pantheonsite.io")]], total_count=1)],
        })
    monkeypatch.setattr(fpc, "cloudflare_client", lambda config_path: client)
    assert fpc.main([]) == 1
    err = capsys.readouterr().err
    assert err.count("a.example.edu") == 1
    assert "ATTENTION: a.example.edu excluded (ambiguous-multiple-zones):" in err


def test_summarize_distinguishes_all_excluded_from_none_found(fpc, tmp_path, monkeypatch,
                                                               capsys):
    """Controller decision (B): summarize()'s zero-entry message said 'no platform-domain
    CNAMEs found' even when the sweep found some and excluded every one as ambiguous -- false
    and misleading on a sweep that found something and correctly refused to act on it.
    test_main_says_so_when_nothing_matched (Task 4 section) covers the genuine
    found-nothing-at-all case and is unaffected."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult(
        {}, [], 1, 2, 5, 1, 0, 0, 187,
        {"a.example.edu": {"reason": "ambiguous-multiple-zones", "detail": "two zones",
                           "zone_ids": ["z1", "z2"], "origins": ["live-a.pantheonsite.io"]}}))
    assert fpc.main([]) == 1
    err = capsys.readouterr().err
    assert "no platform-domain CNAMEs found" not in err
    assert "every platform-domain CNAME found in 2 zones was excluded" in err


def test_main_warns_on_a_proxied_entry_with_a_non_one_ttl(fpc, tmp_path, monkeypatch, capsys):
    """Controller decision (C): proxied_ttl_anomaly (built in Task 5) had no emission site until
    now -- wire it into main()'s per-entry loop.  The anomaly is a warning, not an exclusion: the
    entry still gets a plan/revert entry, with ttl forced to 1 regardless (R6)."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult(
        {"a.example.edu": swept(ttl=300)}, [], 1, 2, 5, 1, 0, 0, 2))
    fake_dns(fpc, monkeypatch, {
        ("live-a.pantheonsite.io", "A"): ["23.185.0.4"],
        ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8000::4"],
    })
    assert fpc.main(["-o", "engin-zone"]) == 0
    err = capsys.readouterr().err
    assert ("ATTENTION: a.example.edu is proxied but its stored ttl is 300, not 1; the rewrite "
            "bodies use 1, which is what Cloudflare enforces anyway") in err
    plan = json.loads((tmp_path / "engin-zone-plan.json").read_text())["entries"]
    assert plan["a.example.edu"]["body"]["posts"][0]["ttl"] == 1


# --- Task 6 review round 2: findings 1/2/3/4 ---------------------------------------------------

def test_now_utc_is_called_exactly_once_and_every_headed_file_shares_that_stamp(
        fpc, tmp_path, monkeypatch, capsys):
    """Review finding 1 (CRITICAL): provenance() used to call now_utc() itself, once per headed
    file, so the three files COULD carry three DIFFERENT generated.at values -- falsifying both
    write_outputs()'s "all three headed files share one generated.at" docstring claim and
    interrupt_message()'s operator advice to compare them for a partial write.

    A CONSTANT stub (freeze_clock, used everywhere else in this file) can NEVER catch this class
    of defect: every call returns the same value no matter how many times it is made, so a test
    built on one can pass against three independent now_utc() calls just as easily as against
    one.  A TICKING stub -- returning a DIFFERENT value each call -- is the only instrument that
    can go red on "called more than once" (PD#14)."""
    planned_run(fpc, monkeypatch, tmp_path)
    stamps = iter(["2026-07-31T14:02:11Z", "2026-07-31T14:02:12Z", "2026-07-31T14:02:13Z",
                  "2026-07-31T14:02:14Z"])
    calls = []

    def ticking():
        stamp = next(stamps)
        calls.append(stamp)
        return stamp

    monkeypatch.setattr(fpc, "now_utc", ticking)
    assert fpc.main(["-o", "engin-zone"]) == 0
    assert len(calls) == 1, "now_utc() must be called EXACTLY ONCE per run, not once per file"
    seen = {json.loads((tmp_path / f"engin-zone-{suffix}.json").read_text())["generated"]["at"]
            for suffix in ("plan", "revert", "excluded")}
    assert seen == {calls[0]}, "every headed file must carry the SAME generated.at"


def test_the_summary_names_all_four_files_with_per_file_entry_counts(fpc, tmp_path, monkeypatch,
                                                                     capsys):
    """Review finding 2: SPEC section 10's `destination` row says the summary "names all four
    paths in basename mode" -- unimplemented pre-fix, where a full-org run's summary named only
    the inventory and left the plan/revert/excluded files (the ones that actually drive a
    destructive rewrite) invisible.  Uses a mixed sweep (one plan-worthy entry, one excluded) so
    all four counts differ and "something got printed" cannot pass by accident."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult(
        {"a.example.edu": swept(), "b.example.edu": swept(name="b.example.edu",
                                                          origins=["live-b.pantheonsite.io"])},
        [], 1, 2, 5, 1, 0, 0, 187))
    fake_dns(fpc, monkeypatch, {
        ("live-a.pantheonsite.io", "A"): ["23.185.0.4"],
        ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8000::4"],
        ("live-b.pantheonsite.io", "A"): ["104.18.2.7"],   # out of range -> excluded
        ("live-b.pantheonsite.io", "AAAA"): ["2620:12a:8000::4"],
    })
    assert fpc.main(["-o", "engin-zone"]) == 1
    err = capsys.readouterr().err
    assert "engin-zone.json (2 entries)" in err
    assert "engin-zone-plan.json (1 entries)" in err
    assert "engin-zone-revert.json (1 entries)" in err
    assert "engin-zone-excluded.json (1 entries)" in err


def test_a_failed_write_of_the_second_file_names_that_file_not_the_first(fpc, tmp_path,
                                                                         monkeypatch, capsys):
    """Review findings 3/4: forcing an OSError on the PLAN write (file 2) used to report
    'cannot write <inventory>' -- naming the WRONG file, since the inventory (file 1) had
    already succeeded -- and said nothing about which of the four files were actually left
    fresh vs. stale/absent.  The fix names the file that actually failed and reports exactly
    what was already replaced (so an operator recovering from this knows the inventory is fresh
    while the plan/revert/excluded are untouched, not the other way around)."""
    planned_run(fpc, monkeypatch, tmp_path)
    real_write_json_atomic = fpc.write_json_atomic

    def flaky(path, data):
        if path.endswith("-plan.json"):
            raise OSError(28, "No space left on device")
        real_write_json_atomic(path, data)

    monkeypatch.setattr(fpc, "write_json_atomic", flaky)
    assert fpc.main(["-o", "engin-zone"]) == 2
    err = capsys.readouterr().err
    assert "ERROR: cannot write engin-zone-plan.json:" in err
    assert "cannot write engin-zone.json" not in err
    assert "Already replaced before this failure (fresh): engin-zone.json" in err
    assert ("NOT written by this run (unchanged or absent): engin-zone-plan.json, "
            "engin-zone-revert.json, engin-zone-excluded.json") in err
    # What is ACTUALLY on disk matches the message: the inventory really is fresh, the other
    # three were never attempted.
    assert (tmp_path / "engin-zone.json").exists()
    assert not (tmp_path / "engin-zone-plan.json").exists()
    assert not (tmp_path / "engin-zone-revert.json").exists()
    assert not (tmp_path / "engin-zone-excluded.json").exists()


def test_a_ctrl_c_mid_write_outputs_leaves_only_fully_written_files_behind(fpc, tmp_path,
                                                                          monkeypatch, capsys):
    """Review finding 3's named coverage gap: 'No test exists for any partial multi-file write,
    by OSError or by Ctrl-C inside write_outputs.'  Each os.replace is atomic, so a SIGINT
    landing between file 2 (plan) and file 3 (revert) must leave files 1-2 complete and files
    3-4 absent -- never a partial file.  Checked against what is ACTUALLY on disk, not merely
    against interrupt_message()'s wording."""
    planned_run(fpc, monkeypatch, tmp_path)
    real_write_json_atomic = fpc.write_json_atomic

    def interrupt_after_plan(path, data):
        real_write_json_atomic(path, data)
        if path.endswith("-plan.json"):
            raise KeyboardInterrupt

    monkeypatch.setattr(fpc, "write_json_atomic", interrupt_after_plan)
    assert fpc.main(["-o", "engin-zone"]) == 130
    err = capsys.readouterr().err
    assert "INTERRUPTED" in err
    assert "never partial" in err
    assert (tmp_path / "engin-zone.json").exists()
    assert (tmp_path / "engin-zone-plan.json").exists()
    assert not (tmp_path / "engin-zone-revert.json").exists()
    assert not (tmp_path / "engin-zone-excluded.json").exists()


# --- Whole-branch review: the exit-code last line of defence ----------------------------------

def test_an_unexpected_exception_exits_2_not_1(fpc, tmp_path, monkeypatch, capsys):
    """Whole-branch review, finding 2 (CRITICAL, PD#1).  Task 4 gave exit 1 the meaning
    "completed with exclusions", but CPython exits 1 on ANY uncaught traceback -- so before the
    last line of defence a KeyError escaping cloudflare_client() was indistinguishable, to an
    operator's `case $?`, from a healthy sweep with a few exclusions.  The sibling
    find-platform-domains-dns has carried this guard since its own whole-branch review, for
    exactly this reason, and SPEC section 8 justifies exit 1 here by consistency with that
    sibling -- a claim that was false until this arm existed.

    KeyError specifically: it is the shape an unexpected Cloudflare/SDK response would take, and
    its str() is repr()-quoted, so the assertion below also proves the class is NAMED rather than
    the message being printed bare (PD#2)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fpc, "cloudflare_client",
                        lambda config_path: (_ for _ in ()).throw(KeyError("some internal bug")))
    assert fpc.main([]) == 2
    assert "ERROR: unexpected KeyError: 'some internal bug'" in capsys.readouterr().err


def test_a_system_exit_is_never_absorbed_by_the_last_line_of_defence(fpc, tmp_path, monkeypatch,
                                                                     capsys):
    """The `except SystemExit: raise` arm, copied from the sibling.  SystemExit is a
    BaseException, so without that arm the catch-all below it would swallow one and return 2,
    replacing whatever code the exit carried.  Nothing in this script raises SystemExit inside
    main()'s try today -- argparse's own exits happen before it -- so this is defence in depth,
    pinned rather than assumed because the arm is invisible until it is deleted."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fpc, "cloudflare_client",
                        lambda config_path: (_ for _ in ()).throw(SystemExit(3)))
    with pytest.raises(SystemExit) as excinfo:
        fpc.main([])
    assert excinfo.value.code == 3


def test_a_serialization_failure_on_the_second_file_reports_the_partial_set(fpc, tmp_path):
    """Whole-branch review, finding 3 (PD#1).  write_outputs' docstring promises that "a failed
    write here reports EXACTLY which paths were already replaced (fresh) and which were not
    touched by this run" -- but the handler caught only OSError, while write_json_atomic ->
    dump_json -> json.dump raises TypeError/ValueError on an unserializable value and
    write_json_atomic's own `except BaseException` re-raises it untouched.  Measured before the
    fix: a TypeError on file 2 left engin-zone.json replaced, produced NO report at all, and
    (before finding 2's guard) exited 1.

    Reachable in production, which is why it is caught rather than declared impossible: plain()
    passes through anything without model_dump, so an SDK shape change putting a non-JSON type
    into `settings` lands here.  Driven with a REAL json.dump failure at the real write_outputs
    seam -- not a monkeypatched write_json_atomic -- so the assertion covers the actual
    serializer, and what is on disk afterwards is checked against what the message claims."""
    paths = fpc.output_paths(str(tmp_path / "engin-zone"))
    with pytest.raises(fpc.OutputWriteError) as excinfo:
        fpc.write_outputs(paths, {"a.example.edu": {"zone_id": "z"}},
                          {"generated": {}, "entries": {"a.example.edu": object()}}, {}, {})
    message = str(excinfo.value)
    assert f"cannot write {paths.plan}: TypeError:" in message
    assert f"Already replaced before this failure (fresh): {paths.inventory}" in message
    assert (f"NOT written by this run (unchanged or absent): {paths.plan}, {paths.revert}, "
            f"{paths.excluded}") in message
    # The message's claim, checked against the filesystem.
    assert Path(paths.inventory).exists()
    assert not Path(paths.plan).exists()
    assert not Path(paths.revert).exists()
    assert not Path(paths.excluded).exists()


def test_a_serialization_failure_is_a_named_startup_error_at_exit_2(fpc, tmp_path, monkeypatch,
                                                                    capsys):
    """The main() half of finding 3: OutputWriteError subclasses StartupError, so it lands in
    main()'s existing exit-2 arm and its message is relayed verbatim -- NOT caught by the
    catch-all last line of defence (which would report it as "unexpected", losing the fresh/stale
    detail an operator recovering from a partial set needs)."""
    planned_run(fpc, monkeypatch, tmp_path)
    real_write_json_atomic = fpc.write_json_atomic

    def unserializable(path, data):
        if path.endswith("-plan.json"):
            data = {"entries": object()}
        real_write_json_atomic(path, data)

    monkeypatch.setattr(fpc, "write_json_atomic", unserializable)
    assert fpc.main(["-o", "engin-zone"]) == 2
    err = capsys.readouterr().err
    assert "ERROR: cannot write engin-zone-plan.json: TypeError:" in err
    assert "unexpected" not in err
    assert "Already replaced before this failure (fresh): engin-zone.json" in err


def test_now_utc_is_utc_with_a_z_suffix(fpc, monkeypatch):
    """Whole-branch review, finding 7 (PD#14).  now_utc() is the ONE clock seam and every other
    test in this file replaces it (freeze_clock, or the ticking stub), so its real body -- the
    thing that decides what `generated.at` actually means -- never executed under test.  SPEC 5.5
    requires "UTC ISO-8601 with a Z suffix"; if it emitted LOCAL time with a Z suffix, nothing
    went red, and an operator comparing generated.at against `date -u` while recovering from a
    partial multi-file write (SPEC 9.3) would be misled by hours.

    The local timezone is forced to America/Detroit for the call, which is what makes this a live
    instrument rather than a tautology: this sandbox runs on UTC, so under TZ=UTC a naive
    datetime.now() and an aware now(tz=UTC) are byte-identical and no assertion here could tell
    them apart.  At UTC-4 the two differ by four hours and the bounds below reject it.

    The one-second slack absorbs strftime truncating to whole seconds.
    """
    monkeypatch.setenv("TZ", "America/Detroit")
    time.tzset()
    try:
        before = datetime.datetime.now(tz=datetime.UTC)
        stamp = fpc.now_utc()
        after = datetime.datetime.now(tz=datetime.UTC)
    finally:
        monkeypatch.undo()
        time.tzset()

    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", stamp), stamp
    parsed = datetime.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.UTC)
    slack = datetime.timedelta(seconds=1)
    assert before - slack <= parsed <= after + slack

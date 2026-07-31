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
import importlib.util
import json
import os
import re
import subprocess
import sys
import types
from importlib.machinery import SourceFileLoader
from pathlib import Path

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
    entries, warnings = fpc.collect_entries([("zone-a", record(ttl=300, comment="migrated",
                                                               tags=["cdn"]))])
    assert entries == {
        "www.example.edu": {
            "zone_id": "zone-a",
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


def test_collect_entries_keeps_dns_only_records(fpc):
    """The whole reason this script exists next to fqdns.json, which is proxied=True only."""
    entries, _ = fpc.collect_entries([("zone-a", record(proxied=False))])
    assert entries["www.example.edu"]["proxied"] is False


def test_collect_entries_serializes_a_pydantic_settings_model(fpc):
    """record.settings is a pydantic model; json.dump cannot serialize one."""
    from cloudflare.types.dns.cname_record import Settings
    entries, _ = fpc.collect_entries(
        [("zone-a", record(settings=Settings(flatten_cname=True)))])
    settings = entries["www.example.edu"]["settings"]
    assert settings["flatten_cname"] is True
    # Asserting the whole dict would pin the SDK's model shape (it also carries ipv4_only /
    # ipv6_only); what matters is the value round-tripping and the entry staying serializable,
    # which a live pydantic model would not be.
    json.dumps(entries)


def test_collect_entries_tolerates_a_record_missing_the_optional_fields(fpc):
    bare = types.SimpleNamespace(type="CNAME", name="www.example.edu", id="rec-1",
                                 content="live-umich-example1.pantheonsite.io")
    entries, _ = fpc.collect_entries([("zone-a", bare)])
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
    entries, warnings = fpc.collect_entries([("zone-a", record(**skipped))])
    assert entries == {}
    assert warnings == []


def test_collect_entries_normalizes_the_key_and_keeps_origins_raw(fpc):
    entries, _ = fpc.collect_entries(
        [("zone-a", record(name="WWW.Example.EDU.",
                           content="Live-Umich-Example1.PantheonSite.IO"))])
    assert list(entries) == ["www.example.edu"]
    assert entries["www.example.edu"]["origins"] == ["Live-Umich-Example1.PantheonSite.IO"]


def test_collect_entries_is_first_record_wins_across_zones_and_warns(fpc):
    entries, warnings = fpc.collect_entries([
        ("zone-a", record(id="rec-1", content="live-a.pantheonsite.io", proxied=True, ttl=1)),
        ("zone-b", record(id="rec-2", content="live-b.pantheonsite.io", proxied=False, ttl=300)),
    ])
    entry = entries["www.example.edu"]
    assert entry["zone_id"] == "zone-a"
    assert entry["record_id"] == "rec-1"
    assert entry["proxied"] is True
    assert entry["ttl"] == 1
    assert entry["origins"] == ["live-a.pantheonsite.io", "live-b.pantheonsite.io"]
    assert len(warnings) == 1
    assert "www.example.edu" in warnings[0]
    assert "zone-a" in warnings[0]
    assert "zone-b" in warnings[0]


def test_collect_entries_warns_for_two_matches_in_one_zone(fpc):
    """API-unreachable (a name holds at most one CNAME), but the file would keep one record_id
    of two and feed a destructive rewrite, so silence is the wrong default."""
    entries, warnings = fpc.collect_entries([
        ("zone-a", record(id="rec-1", content="live-a.pantheonsite.io")),
        ("zone-a", record(id="rec-2", content="live-b.pantheonsite.io")),
    ])
    assert entries["www.example.edu"]["record_id"] == "rec-1"
    assert len(warnings) == 1
    assert "rec-1" in warnings[0]


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


ENTRY = {"zone_id": "z", "origins": ["live-a.pantheonsite.io"], "record_id": "r",
         "proxied": False, "ttl": 1, "comment": None, "tags": [], "settings": None}


def fake_sweep(fpc, monkeypatch, sweep):
    """Drive main() with a canned SweepResult, skipping the client build and the walk."""
    monkeypatch.setattr(fpc, "cloudflare_client", lambda config_path: object())
    monkeypatch.setattr(fpc, "fetch_platform_cnames",
                        lambda client, verbose=False, zone_names=(): sweep)


def test_main_writes_the_json_to_stdout_by_default(fpc, tmp_path, monkeypatch, capsys):
    """SPEC A1.5: stdout is the result stream; the file is written only when -o names it."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult(
        {"a.example.edu": ENTRY}, ["ATTENTION: something worth seeing"], 1, 4, 12431, 40, 1, 2, 4))
    assert fpc.main(["-c", "ignored.toml"]) == 0
    captured = capsys.readouterr()
    assert list(json.loads(captured.out)) == ["a.example.edu"]
    assert not (tmp_path / fpc.OUTPUT_FILE).exists(), "no -o, so no file is written"
    err = captured.err
    assert "ATTENTION: something worth seeing" in err
    assert "Wrote 1 platform-domain CNAMEs (1 DNS-only" in err
    assert "from 12431 records in 4 zones in 1 account(s) to standard output." in err
    assert ("Completeness cross-check: 40 of 43 paginated lists verified complete, 1 short, "
            "2 unverifiable.") in err
    assert "the short lists are named above" in err


def test_main_writes_a_file_when_output_is_given(fpc, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": ENTRY}, [], 1, 4, 12431,
                                                 40, 1, 2, 4))
    assert fpc.main(["-o", fpc.OUTPUT_FILE]) == 0
    captured = capsys.readouterr()
    assert list(json.loads((tmp_path / fpc.OUTPUT_FILE).read_text())) == ["a.example.edu"]
    assert captured.out == "", "with -o, stdout carries only argparse output"
    assert f"to {fpc.OUTPUT_FILE}." in captured.err


def test_main_writes_byte_identical_json_to_stdout_and_to_a_file(fpc, tmp_path, monkeypatch,
                                                                 capsys):
    """SPEC A1.5: the two destinations differ in WHERE, never in WHAT."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": ENTRY, "b.example.edu": ENTRY},
                                                 [], 1, 4, 1, 1, 0, 0, 4))
    assert fpc.main([]) == 0
    from_stdout = capsys.readouterr().out
    assert fpc.main(["-o", "out.json"]) == 0
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
    proxied hostname unproxied (round 3, finding 4)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fpc, "cloudflare_client", lambda config_path: object())
    entry = {"zone_id": "z", "origins": ["live-a.pantheonsite.io"], "record_id": "r",
             "proxied": None, "ttl": 1, "comment": None, "tags": [], "settings": None}
    monkeypatch.setattr(fpc, "fetch_platform_cnames", lambda client, verbose=False, zone_names=():
                        fpc.SweepResult({"a.example.edu": entry}, [], 1, 1, 1, 3, 0, 0, 1))
    assert fpc.main([]) == 0
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
    assert fpc.main(["-o", fpc.OUTPUT_FILE]) == 2
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
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": ENTRY}, [], 1, 1, 1, 1, 0, 0, 1))
    monkeypatch.setattr(sys, "stdout", None)
    assert fpc.main(["-o", "out.json"]) == 0
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
            fpc.write_json_stdout({"a.example.edu": ENTRY})


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
    with (tmp_path / "out.json").open("w") as real_stdout:
        monkeypatch.setattr(sys, "stdout", real_stdout)
        fpc.write_json_stdout({"a.example.edu": ENTRY})
    assert calls == [], "a stream no write has failed on must never be detached"
    assert json.loads((tmp_path / "out.json").read_text()) == {"a.example.edu": ENTRY}


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
            fpc.write_json_stdout({"a.example.edu": ENTRY})
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
entry = {{"zone_id": "z", "origins": ["live-a.pantheonsite.io"], "record_id": "r",
         "proxied": False, "ttl": 1, "comment": None, "tags": [], "settings": None}}
entries = {{"a.example.edu": entry}} if {sweep!r} == "canned" else {{}}
m.cloudflare_client = lambda path: object()
m.fetch_platform_cnames = (
    lambda client, verbose=False, zone_names=(): m.SweepResult(entries, [], 1, 2, 5, 1, 0, 0, 187))
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
    assert fpc.OUTPUT_FILE not in err, "no file was written; naming one implies a baseline died"


def test_the_zero_match_attention_names_the_output_file_when_one_is_given(fpc, tmp_path,
                                                                         monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({}, [], 1, 2, 5, 1, 0, 0, 187))
    assert fpc.main(["-o", "chosen.json"]) == 0
    assert "an empty result ({}) was written to chosen.json" in capsys.readouterr().err


def test_an_interrupt_after_a_successful_stdout_write_does_not_claim_nothing_was_produced(
        fpc, tmp_path, monkeypatch, capsys):
    """The message was categorical, so an operator or wrapper acting on it would discard a
    complete, valid document that is already on stdout."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": ENTRY}, [], 1, 1, 1, 1, 0, 0, 1))

    def interrupt_after_the_write(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(fpc, "summarize", interrupt_after_the_write)
    assert fpc.main([]) == 130
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"a.example.edu": ENTRY}
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
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": ENTRY}, [], 1, 2, 5, 1, 0, 0,
                                                 187))
    assert fpc.main(["-o", "subset.json", "engin.umich.edu", "seas.umich.edu"]) == 0
    err = capsys.readouterr().err
    assert "ATTENTION" in err
    assert "2 of 187" in err
    assert "NOT an organization-wide sweep" in err


def test_a_full_sweep_written_to_a_file_does_not_warn(fpc, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": ENTRY}, [], 1, 187, 5, 1, 0, 0,
                                                 187))
    assert fpc.main(["-o", "full.json"]) == 0
    assert "NOT an organization-wide sweep" not in capsys.readouterr().err


def test_write_json_atomic_and_stdout_share_one_serializer(fpc, tmp_path, monkeypatch):
    """dump_json's docstring calls itself "the ONE serialization"; write_json_atomic formatted
    separately, so the byte-identity held only by duplicated literals."""
    seen = []
    real = fpc.dump_json
    monkeypatch.setattr(fpc, "dump_json", lambda data, stream: (seen.append(stream), real(
        data, stream))[1])
    fpc.write_json_atomic(str(tmp_path / "out.json"), {"a.example.edu": ENTRY})
    assert len(seen) == 1, "write_json_atomic must serialize through dump_json"


def test_an_interrupt_with_output_after_the_write_says_the_file_was_fully_written(
        fpc, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": ENTRY}, [], 1, 1, 1, 1, 0, 0, 1))

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(fpc, "summarize", interrupt)
    assert fpc.main(["-o", "out.json"]) == 130
    assert "out.json was fully written." in capsys.readouterr().err
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
    assert fpc.main(["-o", "out.json"]) == 130
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

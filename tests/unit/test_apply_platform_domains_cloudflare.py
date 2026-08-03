"""Offline tests for the apply-platform-domains-cloudflare utility (SPEC section 13/14).

The script has no .py extension, so it is loaded with the SourceFileLoader idiom the suite
already uses for standalone scripts (see tests/unit/test_find_platform_domains_cloudflare.py).
It is loaded FRESH PER TEST so no module-level state leaks between tests -- which is also what
makes monkeypatching module attributes (now_utc, sleep) safe.

Imports: each task ADDS to the block below, in the task that first needs the name.  Adding an
import further down the file is what ruff's E402 forbids, and E402 is not in the tests/** ignore
list.

TEMPORARY, deleted with the script after the Pantheon CDN migration -- see
development/2026-08-03-platform-domain-util4/SPEC.md section 19.
"""
import importlib.util
import json
import os
import subprocess
import sys
import types
from importlib.machinery import SourceFileLoader
from pathlib import Path

import cloudflare
import httpx
import pytest

pytestmark = pytest.mark.unit

SCRIPT = Path(__file__).resolve().parent.parent.parent / "apply-platform-domains-cloudflare"

DEV_FULL = "/dev/full"
needs_dev_full = pytest.mark.skipif(not os.path.exists(DEV_FULL),  # noqa: PTH110 -- a device
                                    reason="/dev/full is Linux-only")   # node, not a repo path


@pytest.fixture
def apc():
    """The utility, loaded fresh.  Its entry point is __main__-guarded, so import runs nothing."""
    loader = SourceFileLoader("apply_platform_domains_cloudflare_probe", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def refuse_real_network(monkeypatch):
    """SPEC section 13 (amended, task 5 review): fails the test if a real outbound HTTP request
    is attempted -- module-scoped to this test file only, no promise about any other.

    Task 3's credential tests build a REAL `Cloudflare` client by design -- that is the whole
    point of asserting the environment pin against a real built request, and SPEC section 16
    requires it -- so this guard does NOT ban client CONSTRUCTION, only the outbound request. A
    constructed-but-unused client performs no I/O, so banning construction would buy nothing the
    request interception below does not already buy.

    The seam: cloudflare._base_client.SyncAPIClient._request calls `self._client.send(request,
    ...)` exactly once per outbound call -- an httpx.Client instance method -- for BOTH a read
    (dns.records.list) and a write (dns.records.batch), regardless of which Cloudflare instance
    made the call. Patching httpx.Client.send at the CLASS level intercepts every one of them.
    Task 3's `sent_request()` helper instead calls `client._build_request(...)` directly, which
    (per its own docstring) "performs no I/O" and never reaches `.send()` -- so those tests are
    untouched by this guard, proven by test_cloudflare_client_prefers_the_api_token and its
    siblings staying green with this fixture autouse.

    THE ASSERTION LIVES AT TEARDOWN, NOT INSIDE THE PATCH -- the same shape as
    tests/unit/test_find_platform_domains_cloudflare.py's `_refuse_real_dns` fixture, and for the
    same reason (its docstring, quoted there): main()'s `except BaseException` last line of
    defence would otherwise catch a raise-inside-the-patch AssertionError and convert it into
    `report_line(...)` + `return 2`, so a test asserting only `main(...) == 2` would pass green
    while this guard fired unread. Measured directly (task 5 review): the Cloudflare SDK's OWN
    retry loop (`except Exception as err:` in `cloudflare/_base_client.py`) swallows an inline
    `AssertionError` from `refuse` and retries -- three times -- before converting it to
    `cloudflare.APIConnectionError`, so an in-run assertion is eaten by the library under test
    before the caller ever sees it. `refuse` therefore only RECORDS the call; the raise and the
    real assertion happen at teardown, unconditionally, whatever the code under test did with the
    exception in between.

    Yields `reached` (not just `None`): SPEC section 13 mandates a guard self-test, since this
    fixture hooks the SDK's transport and a future SDK upgrade that changes the request path
    could otherwise leave it silently inert with no test noticing (CLAUDE.md's
    two-`sitecustomize.py` failure shape). `test_the_network_guard_itself_can_fire` below depends
    on this fixture explicitly (autouse does not prevent that) to read and then clear `reached`,
    so proving the guard fires does not also trip THIS teardown assertion for an unrelated reason.
    """
    reached = []

    def refuse(self, request, **kwargs):
        reached.append(f"{request.method} {request.url}")
        raise AssertionError(
            f"real network call attempted: {request.method} {request.url} -- this test is "
            "missing FakeCloudflareClient (SPEC section 13 forbids a real Cloudflare API call)")

    monkeypatch.setattr(httpx.Client, "send", refuse)
    yield reached
    assert not reached, (
        f"real network call(s) attempted: {reached} -- this test is missing "
        "FakeCloudflareClient (SPEC section 13 forbids a real Cloudflare API call)")


def test_the_symlink_points_at_the_real_file():
    """The .py symlink is what ruff, pyright and CodeGraph resolve the script through; a plain
    copy would silently drift.  CLAUDE.md records that the main program had ZERO symbols indexed
    until one was added."""
    link = SCRIPT.parent / "apply-platform-domains-cloudflare.py"
    assert link.is_symlink()
    assert link.resolve() == SCRIPT.resolve()


def test_help_documents_the_safety_gate_and_the_exit_codes(apc):
    text = apc.build_arg_parser().format_help()
    assert "--for-real" in text
    assert "WITHOUT THIS FLAG NOTHING IS CHANGED" in text
    assert "--only" in text
    for code in ("0 =", "1 =", "2 =", "3 =", "130 ="):
        assert code in text


def test_the_parser_refuses_an_abbreviation_of_for_real(apc):
    """allow_abbrev=False: `--for` must NOT become `--for-real`.  Without it a dry run silently
    becomes a production rewrite."""
    with pytest.raises(SystemExit):
        apc.build_arg_parser().parse_args(["--for", "plan.json"])


def test_only_is_repeatable_and_never_swallows_the_filename(apc):
    """SPEC R2.2: action="append", not nargs="+".  Under nargs="+" the second FQDN and the
    filename would both land in --only and FILE would be missing."""
    options = apc.build_arg_parser().parse_args(
        ["--only", "a.umich.edu", "--only", "b.umich.edu", "plan.json"])
    assert options.only == ["a.umich.edu", "b.umich.edu"]
    assert options.file == "plan.json"


def test_for_real_defaults_to_false(apc):
    """The blast-radius gate (SPEC R2.6).  A default of True would be catastrophic and is
    exactly the kind of one-character defect a test must pin."""
    assert apc.build_arg_parser().parse_args(["plan.json"]).for_real is False


def test_require_usable_streams_refuses_a_closed_stderr(apc, monkeypatch):
    monkeypatch.setattr(apc.sys, "stderr", None)
    with pytest.raises(apc.StartupError, match="standard error is closed"):
        apc.require_usable_streams()


def test_require_usable_streams_refuses_a_closed_stdout(apc, monkeypatch):
    monkeypatch.setattr(apc.sys, "stdout", None)
    with pytest.raises(apc.StartupError, match="standard output is closed"):
        apc.require_usable_streams()


def test_the_exception_spine_keeps_startup_errors_at_exit_two(apc):
    """PlanFileError, InvariantError, OutputWriteError and CloudflareReadError are all
    StartupError subclasses so main()'s ONE handler gives them all exit 2 -- they add names,
    not code paths (PD#2).  ApplyError is deliberately NOT one: it usually means exit 3."""
    for name in ("PlanFileError", "InvariantError", "OutputWriteError", "CloudflareReadError"):
        assert issubclass(getattr(apc, name), apc.StartupError), name
    assert not issubclass(apc.ApplyError, apc.StartupError)


def run_apc_in_a_subprocess(tmp_path, argv, *, stdout, stderr):
    """Drive the REAL main() in a real interpreter, so the shutdown flush that produces exit 120
    actually runs.  An in-process test cannot observe it: pytest never tears the interpreter down
    between tests, so the whole 120 mechanism is invisible to one (SPEC 11.1).

    The fake client is a plain class embedded in the driver source (not FakeCloudflareClient --
    that class lives in THIS process, not the subprocess's fresh interpreter) returning rows that
    make the one entry `already-applied`, so main() reaches pass 2's report and the summary
    without ever needing a real Cloudflare credential.
    """
    driver = tmp_path / "driver.py"
    driver.write_text(f"""
import sys
import types
from importlib.machinery import SourceFileLoader
import importlib.util
loader = SourceFileLoader("apc_subprocess", {str(SCRIPT)!r})
spec = importlib.util.spec_from_loader("apc_subprocess", loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)


class FakeClient:
    def __init__(self):
        rows = [types.SimpleNamespace(id="rec-a", type="A", name="a.umich.edu",
                                      content="23.185.0.4"),
                types.SimpleNamespace(id="rec-b", type="AAAA", name="a.umich.edu",
                                      content="2620:12a:8000::4")]
        self.dns = types.SimpleNamespace(
            records=types.SimpleNamespace(list=lambda **kw: rows, batch=lambda **kw: None))


m.cloudflare_client = lambda path: FakeClient()
sys.exit(m.main(sys.argv[1:]))
""")
    return subprocess.run([sys.executable, str(driver), *argv],
                          stdout=stdout, stderr=stderr, check=False, cwd=str(tmp_path))


@needs_dev_full
def test_a_doomed_stdout_exits_2_not_120_in_a_real_subprocess(tmp_path):
    """SPEC 11.1, as amended by the task 7 review: the false predecessor of this test used
    stdout=subprocess.DEVNULL (which accepts every write -- never doomed) and a FILE argument
    that made read_apply_file abort before a single stdout byte was written, so it could never
    fail no matter what main() did.  Real bug it should have caught, measured before the fix:
    main() wrote six un-guarded stdout prints, and a doomed stdout there overrode this program's
    own `except OSError: return 2` with the interpreter's shutdown-flush 120."""
    path = write_doc(tmp_path, plan_doc())
    with Path(DEV_FULL).open("w") as doomed_out:
        completed = run_apc_in_a_subprocess(tmp_path, [path], stdout=doomed_out,
                                            stderr=subprocess.PIPE)
    assert completed.returncode == 2
    assert b"cannot write the report to standard output" in completed.stderr


@needs_dev_full
def test_write_report_detaches_and_raises_on_a_doomed_stdout(apc, monkeypatch):
    """Direct proof of write_report's own mechanism (SPEC 11.1), independent of which call site
    happens to reach it first in a given run -- the subprocess test above proves the end-to-end
    exit code for one such run; this pins the seam itself: a doomed write is detached
    IMMEDIATELY and raises a named StartupError, never swallowed and never left for the
    interpreter's shutdown flush to convert into exit 120."""
    with Path(DEV_FULL).open("w") as doomed:
        monkeypatch.setattr(sys, "stdout", doomed)
        with pytest.raises(apc.StartupError, match="cannot write the report to standard output"):
            apc.write_report("a line of the report")


def plan_entry(zone_id="zone-a", fqdn="a.umich.edu",
               target="live-umich-x.pantheonsite.io",
               addresses=("23.185.0.4", "2620:12a:8000::4")):
    """One well-formed plan entry, in util3 SPEC section 5.3's shape."""
    posts = []
    for address in addresses:
        rtype = "AAAA" if ":" in address else "A"
        posts.append({"type": rtype, "name": fqdn, "content": address,
                      "proxied": True, "ttl": 1,
                      "settings": {"ipv4_only": False, "ipv6_only": False}})
    return {
        "zone_id": zone_id,
        "method": "POST",
        "path": f"/zones/{zone_id}/dns_records/batch",
        "delete_match": [{"type": "CNAME", "name": fqdn, "content": target}],
        "body": {"posts": posts},
    }


def plan_doc(entries=None, direction="plan"):
    return {"generated": {"direction": direction, "at": "2026-08-01T00:22:23Z"},
            "entries": entries if entries is not None else {"a.umich.edu": plan_entry()}}


def write_doc(tmp_path, doc, name="platform-domains-cloudflare-plan.json"):
    path = tmp_path / name
    path.write_text(json.dumps(doc))
    return str(path)


def test_read_apply_file_rejects_a_missing_file(apc, tmp_path):
    with pytest.raises(apc.PlanFileError, match=r"nope\.json"):
        apc.read_apply_file(str(tmp_path / "nope.json"))


def test_read_apply_file_rejects_invalid_json(apc, tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json")
    with pytest.raises(apc.PlanFileError, match="not valid JSON"):
        apc.read_apply_file(str(path))


def test_read_apply_file_rejects_a_json_array(apc, tmp_path):
    path = tmp_path / "array.json"
    path.write_text("[]")
    with pytest.raises(apc.PlanFileError, match="a JSON object"):
        apc.read_apply_file(str(path))


def test_check_file_contract_returns_the_direction(apc):
    assert apc.check_file_contract(plan_doc(), "p.json") == "plan"
    assert apc.check_file_contract(plan_doc(direction="revert"), "p.json") == "revert"


def test_check_file_contract_refuses_an_excluded_file_by_name(apc):
    """SPEC section 6 check 2.  An -excluded.json has the same header shape and no `body`
    anywhere, so it must be named, not merely rejected as malformed."""
    doc = plan_doc(direction="excluded")
    with pytest.raises(apc.PlanFileError, match="excluded"):
        apc.check_file_contract(doc, "p.json")


def test_check_file_contract_refuses_a_missing_direction(apc):
    doc = plan_doc()
    del doc["generated"]["direction"]
    with pytest.raises(apc.PlanFileError, match="direction"):
        apc.check_file_contract(doc, "p.json")


def test_check_file_contract_refuses_an_empty_entries_object(apc):
    with pytest.raises(apc.PlanFileError, match="no entries"):
        apc.check_file_contract(plan_doc(entries={}), "p.json")


@pytest.mark.parametrize("field", ["zone_id", "method", "path", "body", "delete_match"])
def test_check_file_contract_names_a_missing_required_field(apc, field):
    entry = plan_entry()
    del entry[field]
    with pytest.raises(apc.PlanFileError, match=rf"a\.umich\.edu.*{field}"):
        apc.check_file_contract(plan_doc(entries={"a.umich.edu": entry}), "p.json")


def test_check_file_contract_refuses_a_non_post_method(apc):
    entry = plan_entry()
    entry["method"] = "PUT"
    with pytest.raises(apc.PlanFileError, match="POST"):
        apc.check_file_contract(plan_doc(entries={"a.umich.edu": entry}), "p.json")


def test_check_file_contract_refuses_a_path_that_disagrees_with_zone_id(apc):
    """SPEC section 6 check 5.  This assertion is what keeps the file's `path` field from being
    decorative: the typed SDK call builds its own path, so an unchecked one would be silently
    ignored."""
    entry = plan_entry()
    entry["path"] = "/zones/SOMEWHERE-ELSE/dns_records/batch"
    with pytest.raises(apc.PlanFileError, match="path"):
        apc.check_file_contract(plan_doc(entries={"a.umich.edu": entry}), "p.json")


def test_check_file_contract_refuses_deletes_inside_body(apc):
    """util3 SPEC R5.3: ids are resolved at apply time, so a baked-in `deletes` cannot be
    correct."""
    entry = plan_entry()
    entry["body"]["deletes"] = [{"id": "stale"}]
    with pytest.raises(apc.PlanFileError, match="deletes"):
        apc.check_file_contract(plan_doc(entries={"a.umich.edu": entry}), "p.json")


def test_check_file_contract_refuses_empty_posts(apc):
    entry = plan_entry()
    entry["body"]["posts"] = []
    with pytest.raises(apc.PlanFileError, match="posts"):
        apc.check_file_contract(plan_doc(entries={"a.umich.edu": entry}), "p.json")


@pytest.mark.parametrize("bad_type", ["MX", "TXT", "cname"])
def test_check_file_contract_refuses_an_out_of_scope_post_type(apc, bad_type):
    """SPEC R1.1 -- and the check is what makes the governed-type rule total: after it, D and P
    contain only CNAME/A/AAAA by construction.  A lowercase "cname" is refused too: record_key
    upper-cases for comparison, and accepting it here would let a file smuggle a type past a
    reader's eye."""
    entry = plan_entry()
    entry["body"]["posts"][0]["type"] = bad_type
    with pytest.raises(apc.PlanFileError, match="type"):
        apc.check_file_contract(plan_doc(entries={"a.umich.edu": entry}), "p.json")


def test_check_file_contract_refuses_an_empty_delete_match(apc):
    entry = plan_entry()
    entry["delete_match"] = []
    with pytest.raises(apc.PlanFileError, match="delete_match"):
        apc.check_file_contract(plan_doc(entries={"a.umich.edu": entry}), "p.json")


def test_select_entries_returns_everything_without_only(apc):
    entries = {"a.umich.edu": plan_entry(), "b.umich.edu": plan_entry(fqdn="b.umich.edu")}
    assert apc.select_entries(entries, None) == entries


def test_select_entries_filters_and_normalizes(apc):
    entries = {"a.umich.edu": plan_entry(), "b.umich.edu": plan_entry(fqdn="b.umich.edu")}
    selected = apc.select_entries(entries, ["A.UMICH.EDU."])
    assert list(selected) == ["a.umich.edu"]


def test_select_entries_names_every_miss(apc):
    """SPEC R7.3: a typo that silently narrows a destructive run is the under-reporting failure
    this family refuses to have -- so EVERY miss is named, not just the first."""
    entries = {"a.umich.edu": plan_entry()}
    with pytest.raises(apc.StartupError) as excinfo:
        apc.select_entries(entries, ["nope.umich.edu", "also-nope.umich.edu"])
    message = str(excinfo.value)
    assert "nope.umich.edu" in message
    assert "also-nope.umich.edu" in message


def config_file(tmp_path, body):
    path = tmp_path / "config.toml"
    path.write_text(body)
    return str(path)


def sent_request(client):
    """The request the SDK would actually send.  Offline: _build_request performs no I/O.

    Review round 1, finding 1: the ORIGINAL version of this test file asserted against attribute
    state (`client.base_url`, `client._custom_headers`, `client.api_email`) for three of the four
    pinned routes, and SPEC section 16 / section 14 group 13 are explicit that this is not a
    substitute for a real built request -- an SDK refactor that kept the same public attribute
    names but snapshotted credentials at __init__ time left all three attribute assertions green
    while the ambient credential still reached the wire.  `cloudflare._models.FinalRequestOptions`
    is the SDK's own request-options type, not a `types.SimpleNamespace` stand-in (the sibling's
    idiom, ported here by name).
    """
    from cloudflare._models import FinalRequestOptions
    return client._build_request(FinalRequestOptions(method="get", url="/zones"))


# The SDK reads six ambient variables (cloudflare 5.4.0); exporting ALL of them is what makes
# test_cloudflare_client_sends_only_the_configured_credential a real proof rather than a sample --
# a regression that dropped any one field from the pin goes red.  Ported from the sibling's
# AMBIENT_CLOUDFLARE_VARS (review round 1, finding 1).
AMBIENT_CLOUDFLARE_VARS = {
    "CLOUDFLARE_API_TOKEN": "ambient-token",
    "CLOUDFLARE_API_KEY": "ambient-key",
    "CLOUDFLARE_EMAIL": "ambient@example.edu",
    "CLOUDFLARE_API_USER_SERVICE_KEY": "ambient-usk",
    "CLOUDFLARE_BASE_URL": "https://attacker.example/v4",
    "CLOUDFLARE_CUSTOM_HEADERS": "X-Auth-Email: attacker@attacker.example\nX-Auth-Key: evil-key",
}


def test_cloudflare_client_prefers_the_api_token(apc, tmp_path):
    path = config_file(tmp_path, '[Cloudflare]\napi_token = "tok-123"\n')
    client = apc.cloudflare_client(path)
    request = sent_request(client)
    assert request.headers["Authorization"] == "Bearer tok-123"


def test_cloudflare_client_sends_only_the_configured_credential(apc, tmp_path, monkeypatch):
    """SPEC section 16, asserted as the security property itself rather than the attribute state
    that implements it (review round 1, finding 1).  ALL SIX ambient variables the SDK reads are
    exported, so a regression in any one of the four pinned routes goes red here -- proven by
    mutation: with `client._custom_headers = {}` deleted, this test goes red while the three
    attribute-only assertions it replaces stayed green (pasted in the task report)."""
    for name, value in AMBIENT_CLOUDFLARE_VARS.items():
        monkeypatch.setenv(name, value)
    path = config_file(tmp_path, '[Cloudflare]\napi_token = "tok-123"\n')
    client = apc.cloudflare_client(path)

    request = sent_request(client)
    assert str(request.url).startswith(apc.API_BASE_URL)
    assert request.headers.get("authorization") == "Bearer tok-123"
    # Each route named explicitly.  A set-intersection against the env var VALUES cannot see
    # route 3 ($CLOUDFLARE_CUSTOM_HEADERS): its value is "X-Auth-Email: attacker@..." while the
    # header it injects is just "attacker@...".
    assert request.headers.get("x-auth-email") is None      # routes 1, 2 and 3
    assert request.headers.get("x-auth-key") is None         # routes 2 and 3
    assert "attacker.example" not in str(request.headers)    # route 3 payload
    assert "attacker.example" not in str(request.url)        # route 4
    assert "ambient-key" not in str(request.headers)
    assert "ambient-token" not in str(request.headers)


def test_cloudflare_client_ignores_an_ambient_base_url(apc, tmp_path, monkeypatch):
    """The worst of the four routes: an ambient CLOUDFLARE_BASE_URL sends the CONFIGURED
    credential to an arbitrary host.  Asserted against a REAL BUILT REQUEST, not against the
    attribute assignments that implement the pin -- the sibling's set-intersection version of
    this assertion silently missed the _custom_headers route."""
    monkeypatch.setenv("CLOUDFLARE_BASE_URL", "https://attacker.example/")
    path = config_file(tmp_path, '[Cloudflare]\napi_token = "tok-123"\n')
    request = sent_request(apc.cloudflare_client(path))
    assert "attacker.example" not in str(request.url)
    assert str(request.url).startswith(apc.API_BASE_URL)


def test_cloudflare_client_ignores_ambient_custom_headers(apc, tmp_path, monkeypatch):
    """Attribute-state MECHANISM check, kept alongside the wire-level proof above -- SPEC section
    16 / section 14 group 13 forbid this being the ONLY assertion, not that it may not exist."""
    monkeypatch.setenv("CLOUDFLARE_CUSTOM_HEADERS", "X-Auth-Email: leak@example.com")
    path = config_file(tmp_path, '[Cloudflare]\napi_token = "tok-123"\n')
    client = apc.cloudflare_client(path)
    assert client._custom_headers == {}


def test_cloudflare_client_ignores_an_ambient_email(apc, tmp_path, monkeypatch):
    """auth_headers returns the FIRST of email -> key -> token, so an ambient CLOUDFLARE_EMAIL
    beats a configured api_token and the token is never sent.  Attribute-state MECHANISM check,
    kept alongside the wire-level proof above (same rationale as the custom-headers test)."""
    monkeypatch.setenv("CLOUDFLARE_EMAIL", "ambient@example.com")
    monkeypatch.setenv("CLOUDFLARE_API_KEY", "ambient-key")
    path = config_file(tmp_path, '[Cloudflare]\napi_token = "tok-123"\n')
    client = apc.cloudflare_client(path)
    assert client.api_email is None
    assert client.api_key is None


def test_cloudflare_client_falls_back_to_email_and_key(apc, tmp_path):
    path = config_file(tmp_path,
                       '[Cloudflare]\nemail = "a@b.edu"\napi_key = "k"\n')
    client = apc.cloudflare_client(path)
    assert client.api_email == "a@b.edu"
    assert client.api_token is None


def test_cloudflare_client_refuses_a_non_string_credential(apc, tmp_path):
    """TOML is typed: `api_token = true` is an ordinary unquoted-value typo, and the SDK would
    stringify it into `Authorization: Bearer True` -- a baffling 401."""
    path = config_file(tmp_path, "[Cloudflare]\napi_token = true\n")
    with pytest.raises(apc.StartupError, match="must be a string"):
        apc.cloudflare_client(path)


# Ported from tests/unit/test_find_platform_domains_cloudflare.py (review round 1, finding 5):
# the copied 43-line resolver had one test here vs. seven in the sibling.

def test_resolve_config_value_passes_literals_and_non_strings_through(apc):
    assert apc.resolve_config_value("plain-literal", "where") == "plain-literal"
    assert apc.resolve_config_value(True, "where") is True
    assert apc.resolve_config_value(None, "where") is None


@pytest.mark.parametrize("marker", ["<{env CF_TEST_VAR}", "<{secret env CF_TEST_VAR}"])
def test_resolve_config_value_reads_the_environment(apc, monkeypatch, marker):
    monkeypatch.setenv("CF_TEST_VAR", "from-the-environment")
    assert apc.resolve_config_value(marker, "where") == "from-the-environment"


def test_resolve_config_value_substitutes_inside_a_larger_string(apc, monkeypatch):
    monkeypatch.setenv("CF_TEST_VAR", "middle")
    assert apc.resolve_config_value("a<{env CF_TEST_VAR}z", "where") == "amiddlez"


def test_resolve_config_value_uses_the_default_when_the_variable_is_unset(apc, monkeypatch):
    monkeypatch.delenv("CF_TEST_VAR", raising=False)
    assert apc.resolve_config_value("<{secret env CF_TEST_VAR fallback}", "where") == "fallback"


def test_resolve_config_value_reports_an_unset_variable_with_no_default(apc, monkeypatch):
    monkeypatch.delenv("CF_TEST_VAR", raising=False)
    with pytest.raises(apc.StartupError) as caught:
        apc.resolve_config_value("<{env CF_TEST_VAR}", "config.toml [Cloudflare].api_key")
    assert "CF_TEST_VAR" in str(caught.value)
    assert "config.toml [Cloudflare].api_key" in str(caught.value)


def test_resolve_config_value_names_a_malformed_substitution(apc):
    """An unbalanced quote makes shlex raise ValueError, which escaped as a raw traceback at
    exit 1 in the sibling before it was closed (adversarial review round 1, finding 3 there)."""
    with pytest.raises(apc.StartupError) as caught:
        apc.resolve_config_value("<{env FOO don't}", "config.toml [Cloudflare].api_key")
    assert "config.toml [Cloudflare].api_key" in str(caught.value)


def test_resolve_env_marker_refuses_a_form_it_cannot_resolve(apc):
    """A literal "<{secret aws ...}" handed to the API as a token surfaces as a baffling 401
    instead of a config error.  The body is withheld: an inline default can be a credential."""
    with pytest.raises(apc.StartupError) as excinfo:
        apc.resolve_env_marker("secret aws prod/key", "cfg [Cloudflare].api_token")
    assert "prod/key" not in str(excinfo.value)


def api_status_error(error_cls, status_code, body):
    """A REAL cloudflare SDK exception -- not a stand-in.

    Review round 1 (finding 4) rejected a `types.SimpleNamespace(...)` + `__class__`
    reassignment fake (it always raises TypeError -- SimpleNamespace is not a CPython heap type,
    `__flags__ & Py_TPFLAGS_HEAPTYPE == 0`) AND its dynamic-bare-`Exception`-subclass replacement
    (str(e) == "" on that fake, which would make finding 2's "str(e) never appears" assertion
    vacuous -- a check that cannot go red is not evidence, PD#14).  Constructing the exception the
    way the SDK itself raises one keeps str(e) genuinely present, so a test that asserts it is
    excluded is actually exercising something.
    """
    request = httpx.Request("GET", "https://api.cloudflare.com/client/v4/zones")
    response = httpx.Response(status_code, request=request, json=body)
    return error_cls(f"Error code: {status_code} - {body}", response=response, body=body)


def test_api_error_text_says_nothing_but_the_status_on_an_auth_failure(apc):
    """SPEC 9.1 rule 2.  The sibling's docstring: "an auth-failure body can echo the credential".
    401 and 403 report the class and status ALONE."""
    for status, error_cls in ((401, cloudflare.AuthenticationError),
                              (403, cloudflare.PermissionDeniedError)):
        error = api_status_error(
            error_cls, status, {"errors": [{"code": 10000, "message": "SECRET-TOKEN"}]})
        assert "SECRET-TOKEN" in str(error)   # sanity: the real exception DOES carry it
        text = apc.api_error_text(error)
        assert str(status) in text
        assert "SECRET-TOKEN" not in text


def test_api_error_text_admits_structured_errors_on_a_non_auth_failure(apc):
    error = api_status_error(
        cloudflare.BadRequestError, 400,
        {"errors": [{"code": 81058, "message": "An identical record already exists."}]})
    text = apc.api_error_text(error)
    assert "81058" in text
    assert "identical record already exists" in text


def test_api_error_text_truncates_a_long_message(apc):
    """SPEC 9.1 rule 3: an unexpectedly large or repeating error array must not become a dump of
    arbitrary server-supplied text in an operator's log."""
    error = api_status_error(
        cloudflare.BadRequestError, 400, {"errors": [{"code": 1, "message": "x" * 300}]})
    text = apc.api_error_text(error)
    assert "x" * apc.ERROR_MESSAGE_LIMIT in text
    assert "x" * (apc.ERROR_MESSAGE_LIMIT + 1) not in text


def test_api_error_text_never_includes_str_e_when_there_is_no_status_code(apc):
    """Review round 1, finding 2: SPEC 9.1 rule 1's fourth case ("str(e) never appears in any
    message") had NO test, and it is exactly the one that would have caught the fallback branch
    returning f"{type(e).__name__}: {e}".  A status_code-less exception (e.g. a connection
    failure, which carries no response at all) can still carry credential material in its own
    message -- str(cloudflare.APIConnectionError(...)) is exactly its `message` argument."""
    request = httpx.Request("GET", "https://api.cloudflare.com/client/v4/zones")
    error = cloudflare.APIConnectionError(
        message="token BEARER-SECRET rejected during connect", request=request)
    assert getattr(error, "status_code", None) is None
    assert "BEARER-SECRET" in str(error)   # sanity: the real exception DOES carry it
    text = apc.api_error_text(error)
    assert "BEARER-SECRET" not in text
    assert "APIConnectionError" in text


def test_api_error_text_bounds_the_total_message_length(apc):
    """SPEC 9.1 rule 3's INTENT, not just the per-message cap: an unexpectedly large or repeating
    error array must not turn an operator's terminal or log into a dump of server-supplied text.
    Review round 1, finding 3 -- measured pre-fix: a 5000-element array produced a message over
    1,000,000 characters (truncating `message` bounded each entry but not the array's LENGTH),
    and a single oversized `code` field (100k characters) was never truncated at all."""
    errors = [{"code": "c" * 100_000, "message": "x" * 300} for _ in range(5000)]
    error = api_status_error(cloudflare.BadRequestError, 400, {"errors": errors})
    text = apc.api_error_text(error)
    assert len(text) < 2000


def row(rtype="CNAME", name="a.umich.edu", content="live-umich-x.pantheonsite.io",
        identifier="rec-1"):
    """A stand-in for one SDK record object as dns.records.list returns it."""
    return types.SimpleNamespace(id=identifier, type=rtype, name=name, content=content)


def cname_rows():
    return [row()]


def address_rows():
    return [row("A", content="23.185.0.4", identifier="rec-a"),
            row("AAAA", content="2620:12a:8000::4", identifier="rec-b")]


def test_record_key_treats_two_spellings_of_one_ipv6_address_as_one_record(apc):
    """A string comparison would call these two records and invent a partially-applied verdict
    on a healthy zone."""
    assert (apc.record_key("AAAA", "a.umich.edu", "2620:12a:8000::4")
            == apc.record_key("AAAA", "a.umich.edu", "2620:12A:8000:0:0:0:0:4"))


def test_record_key_ignores_case_and_a_trailing_dot(apc):
    assert (apc.record_key("CNAME", "A.Umich.EDU.", "Live-X.PantheonSite.io.")
            == apc.record_key("cname", "a.umich.edu", "live-x.pantheonsite.io"))


def test_governed_records_drops_unrelated_types(apc):
    """SPEC R1.1: a TXT/MX/CAA at the same name is none of this script's business."""
    rows = [row(), row("TXT", content="v=spf1 -all", identifier="rec-t"),
            row("MX", content="mx.umich.edu", identifier="rec-m")]
    assert [r.id for r in apc.governed_records(rows)] == ["rec-1"]


def test_governed_records_drops_a_row_with_a_missing_or_none_type(apc):
    """Review round 1, finding 3: the defensive `str(getattr(r, "type", "")).upper()` read was
    unproven by the suite.  A row missing `type` entirely, or carrying `type=None`, must never
    raise and must never be counted as governed -- an unrelated malformed SDK row must not
    silently qualify as an A/AAAA/CNAME."""
    missing_type = types.SimpleNamespace(id="rec-missing", name="a.umich.edu", content="x")
    none_type = types.SimpleNamespace(id="rec-none", type=None, name="a.umich.edu", content="x")
    assert apc.governed_records([missing_type, none_type]) == []


def test_verdict_ready_when_cloudflare_holds_exactly_the_delete_match(apc):
    verdict, detail = apc.verdict_for(plan_entry(), cname_rows())
    assert verdict == "ready"
    assert detail == ""


def test_verdict_already_applied_when_cloudflare_holds_exactly_the_posts(apc):
    """SPEC R4.3: established affirmatively (R == P), NEVER inferred from the absence of D."""
    verdict, _ = apc.verdict_for(plan_entry(), address_rows())
    assert verdict == "already-applied"


def test_verdict_record_ambiguous_when_a_key_occurs_twice(apc):
    """Review round 1, finding 4 raised whether record-ambiguous's detail should name the
    colliding record ids; review round 2's controller ruling (SPEC 7.3, amended) says it MUST --
    by construction the two records share a record_key (that IS what makes them ambiguous), so a
    detail in record_key terms alone cannot tell them apart, and the id is the only field that
    distinguishes them in the dashboard or API.  Asserting BOTH ids present (not just one) is what
    makes this non-vacuous: dropping either id from the detail would turn this red."""
    rows = [row(), row(identifier="rec-2")]
    verdict, detail = apc.verdict_for(plan_entry(), rows)
    assert verdict == "record-ambiguous"
    assert "CNAME live-umich-x.pantheonsite.io" in detail
    assert "rec-1" in detail
    assert "rec-2" in detail


def test_verdict_partially_applied_on_a_mix_of_both_sides(apc):
    rows = [*cname_rows(), row("A", content="23.185.0.4", identifier="rec-a")]
    verdict, _ = apc.verdict_for(plan_entry(), rows)
    assert verdict == "partially-applied"


def test_verdict_unexpected_records_on_a_proper_superset(apc):
    """SPEC 7.3 row 5 -- this is util3 SPEC 5.4's "known and accepted" hazard (an unrelated
    fourth A record at the name), caught at validation time instead of as a rollback."""
    rows = [*address_rows(), row("A", content="23.185.0.99", identifier="rec-extra")]
    verdict, detail = apc.verdict_for(plan_entry(), rows)
    assert verdict == "unexpected-records"
    assert "23.185.0.99" in detail


def test_verdict_unexpected_records_on_a_proper_superset_of_delete_match(apc):
    """Review round 1, finding 2: the symmetric R > D branch (the OTHER iteration of the
    `for expected, side in ((want_delete, ...), (want_post, ...))` loop) had no test -- only the
    R > P case above did.  An unrelated extra AAAA that overlaps with neither D nor P."""
    rows = [*cname_rows(), row("AAAA", content="2620:12a:8000::99", identifier="rec-extra")]
    verdict, detail = apc.verdict_for(plan_entry(), rows)
    assert verdict == "unexpected-records"
    assert "2620:12a:8000::99" in detail


def test_verdict_for_raises_invariant_error_on_the_impossible_empty_shape(apc):
    """SPEC 7.4's nil shadow: section 6 checks 7 and 8 make an empty/absent delete_match or
    body.posts FATAL before pass 1 ever runs, so this shape reaching verdict_for is a defect in
    this script's own reasoning, not a file to classify -- asserted here, not assumed (PD#1/
    PD#14).  Review round 1, finding 1: without this guard, empty D together with an empty R made
    `have == want_delete` (both empty sets) return a false "ready", indistinguishable from a
    healthy, fully-processed entry.

    Review round 2, item 2: the guard's own message says "empty OR MISSING", so an entry from
    which the key is ABSENT ENTIRELY (not merely empty) must raise the SAME named InvariantError
    too, not a bare KeyError -- covered by the three del-the-key cases below.  Review round 3:
    the round-2 diff exercised only 2 of the 3 named shapes (missing delete_match, missing
    body.posts with body present) -- missing `entry["body"]` ENTIRELY was untested, and the
    re-reviewer demonstrated it is not academic: reverting ONLY the outer defensive read
    (`entry.get("body", {}).get("posts")` -> `entry["body"].get("posts")`, leaving the other two
    `.get`s intact) left every case the suite exercised at the time still green, while
    `del entry["body"]` on that reverted module raised a bare `KeyError: 'body'`.
    """
    entry = plan_entry()
    entry["delete_match"] = []
    entry["body"]["posts"] = []
    with pytest.raises(apc.InvariantError):
        apc.verdict_for(entry, [])

    missing_delete_match = plan_entry()
    del missing_delete_match["delete_match"]
    with pytest.raises(apc.InvariantError):
        apc.verdict_for(missing_delete_match, [])

    missing_posts = plan_entry()
    del missing_posts["body"]["posts"]
    with pytest.raises(apc.InvariantError):
        apc.verdict_for(missing_posts, [])

    missing_body = plan_entry()
    del missing_body["body"]
    with pytest.raises(apc.InvariantError):
        apc.verdict_for(missing_body, [])


def test_verdict_records_missing_when_nothing_governed_is_there(apc):
    """SPEC 7.4's empty shadow: NOT silently treated as already-applied."""
    verdict, _ = apc.verdict_for(plan_entry(), [])
    assert verdict == "records-missing"


def test_verdict_records_missing_on_a_strict_subset(apc):
    rows = [row("A", content="23.185.0.4", identifier="rec-a")]
    verdict, _ = apc.verdict_for(plan_entry(), rows)
    assert verdict == "records-missing"


def test_verdict_ambiguity_is_evaluated_before_the_set_comparisons(apc):
    """SPEC 7.3: row 1 first, so a duplicated key can never make a set comparison accidentally
    succeed -- a set() of [X, X] equals a set() of [X]."""
    rows = [*cname_rows(), row(identifier="rec-dup")]
    verdict, _ = apc.verdict_for(plan_entry(), rows)
    assert verdict == "record-ambiguous"


def test_verdict_ignores_an_unrelated_txt_record_at_the_same_name(apc):
    rows = [*cname_rows(), row("TXT", content="v=spf1 -all", identifier="rec-t")]
    verdict, _ = apc.verdict_for(plan_entry(), rows)
    assert verdict == "ready"


def test_a_revert_entry_is_ready_when_the_addresses_are_present(apc):
    """The same engine, both directions: a revert's D is the A/AAAA set and its P is the CNAME."""
    entry = plan_entry()
    entry["delete_match"], entry["body"]["posts"] = (
        [{"type": "A", "name": "a.umich.edu", "content": "23.185.0.4"},
         {"type": "AAAA", "name": "a.umich.edu", "content": "2620:12a:8000::4"}],
        [{"type": "CNAME", "name": "a.umich.edu",
          "content": "live-umich-x.pantheonsite.io", "proxied": True, "ttl": 1}])
    verdict, _ = apc.verdict_for(entry, address_rows())
    assert verdict == "ready"


class FakeCloudflareClient:
    """The two calls this script makes: dns.records.list and dns.records.batch.

    `rows_by_name` maps a normalized FQDN to the SEQUENCE of row-lists returned by successive
    list() calls for that name (the last repeats), so a post-apply verification can be made to
    agree or disagree with what pass 1 saw.  Every call is recorded, which is what lets a test
    assert that a dry run made ZERO batch calls rather than inferring it.
    """

    def __init__(self, rows_by_name=None, list_error=None, batch_error=None):
        self.rows_by_name = rows_by_name or {}
        self.list_error = list_error
        self.batch_error = batch_error
        self.list_calls = []
        self.batch_calls = []
        self._served = {}
        self.dns = types.SimpleNamespace(
            records=types.SimpleNamespace(list=self._list, batch=self._batch))

    def _list(self, *, zone_id, name=None, type=None, **kwargs):  # noqa: A002 -- mirrors the
        # real SDK's dns.records.list(..., type=...) keyword verbatim (confirmed via
        # inspect.signature(RecordsResource.list)), and this is a fake honoring that seam's shape,
        # not a program-facing API that could confuse a caller with the builtin (task 5 review,
        # Minor 6).
        self.list_calls.append({"zone_id": zone_id, "name": name, "type": type, **kwargs})
        if self.list_error is not None:
            raise self.list_error
        key = (name or {}).get("exact", "")
        sequence = self.rows_by_name.get(key, [[]])
        index = min(self._served.get(key, 0), len(sequence) - 1)
        self._served[key] = index + 1
        rows = sequence[index]
        if type is not None:
            rows = [r for r in rows if str(getattr(r, "type", "")).upper() == str(type).upper()]
        return rows

    def _batch(self, *, zone_id, deletes=None, posts=None, **kwargs):
        self.batch_calls.append({"zone_id": zone_id, "deletes": deletes, "posts": posts})
        if self.batch_error is not None:
            raise self.batch_error
        return types.SimpleNamespace(deletes=deletes, posts=posts)


def test_records_at_name_asks_cloudflare_for_exactly_that_name(apc):
    """One filtered list per FQDN, NOT a whole-zone walk: util3 measured 2 duplicates and 2
    misses in one walk of an 18,848-record zone, and a miss would be a FALSE validation
    failure."""
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})
    rows = apc.records_at_name(client, "zone-a", "a.umich.edu")
    assert [r.id for r in rows] == ["rec-1"]
    assert client.list_calls[0]["zone_id"] == "zone-a"
    assert client.list_calls[0]["name"] == {"exact": "a.umich.edu"}


def test_records_at_name_names_a_cloudflare_read_failure(apc):
    # NOTE: the task brief's literal `cloudflare_error()` helper (a types.SimpleNamespace with
    # `__class__` reassigned) raises TypeError on construction -- SimpleNamespace is not a
    # CPython heap type, exactly the defect review round 1 finding 4 (above, api_status_error's
    # docstring) already rejected for this same file.  Using the sanctioned real-SDK builder
    # instead, per this task's brief: "plus Task 3's real-SDK error builders."
    error = api_status_error(cloudflare.InternalServerError, 500,
                             {"errors": [{"code": 1000, "message": "boom"}]})
    client = FakeCloudflareClient(list_error=error)
    with pytest.raises(apc.CloudflareReadError):
        apc.records_at_name(client, "zone-a", "a.umich.edu")


def test_validate_entries_resolves_the_delete_ids_for_a_ready_entry(apc):
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})
    result = apc.validate_entries(client, {"a.umich.edu": plan_entry()}, verbose=False)
    assert result["a.umich.edu"].verdict == "ready"
    assert result["a.umich.edu"].delete_ids == ["rec-1"]


def test_validate_entries_resolves_no_ids_for_an_already_applied_entry(apc):
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [address_rows()]})
    result = apc.validate_entries(client, {"a.umich.edu": plan_entry()}, verbose=False)
    assert result["a.umich.edu"].verdict == "already-applied"
    assert result["a.umich.edu"].delete_ids == []


def test_validate_entries_classifies_every_entry_not_just_the_first(apc):
    """A first-failure-wins loop would hide the second problem and force a second full run.

    Task 5 review, Critical 1: the ORIGINAL version of this test put the one invalid entry on the
    LAST key in sort order ("b.umich.edu" after "a.umich.edu"), so a loop that stops at the first
    invalid entry still produced both results -- proven measured: adding `if verdict not in
    ("ready", "already-applied"): break` to validate_entries left the whole suite green, INCLUDING
    this test. Putting the invalid entry FIRST in sort order ("a.umich.edu" before "b.umich.edu")
    is what makes a first-failure-wins loop actually fail to reach the second entry.

    NOTE on the review's suggested replacement: it reused `cname_rows()` (a row hardcoded to
    `name="a.umich.edu"`, see `row()`'s default) for the "b.umich.edu" entry. Verified directly:
    that combination does NOT produce "ready" -- `record_key` includes the name, so a row named
    "a.umich.edu" can never match a "b.umich.edu" delete_match, and the entry falls through to
    "records-missing" regardless of the break mutation. `row(name="b.umich.edu")` is used below
    instead, so this entry's row genuinely matches its own delete_match.
    """
    client = FakeCloudflareClient(rows_by_name={
        "a.umich.edu": [[]],
        "b.umich.edu": [[row(name="b.umich.edu")]],
    })
    entries = {"a.umich.edu": plan_entry(), "b.umich.edu": plan_entry(fqdn="b.umich.edu")}
    result = apc.validate_entries(client, entries, verbose=False)
    assert result["a.umich.edu"].verdict == "records-missing"
    assert result["b.umich.edu"].verdict == "ready"


def test_validate_entries_prints_the_verdict_word_only_under_verbose(apc, capsys):
    """SPEC 11.2 (amended, task 5 review, Important 3): the pass-1 progress line is `<fqdn>:
    <verdict>` -- the verdict word ONLY, `-v`, stdout.  The detail belongs to the unconditional
    stderr ATTENTION line a later task adds; printing both under -v would put the same fact on
    two streams.  All four other validate_entries tests pass verbose=False, so before this test
    the verbose=True branch had zero coverage."""
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [[]]})
    entry = plan_entry()
    result = apc.validate_entries(client, {"a.umich.edu": entry}, verbose=True)
    assert result["a.umich.edu"].verdict == "records-missing"
    assert result["a.umich.edu"].detail   # the detail DOES exist on the Validation...
    captured = capsys.readouterr()
    assert captured.out.strip() == "a.umich.edu: records-missing"   # ...but never on stdout
    assert result["a.umich.edu"].detail not in captured.out


def test_validate_entries_raises_invariant_error_when_delete_ids_diverge_from_delete_match(
        apc, monkeypatch):
    """Task 5 review, Important 4: verdict_for and validate_entries both derive D from
    delete_match through the ONE shared want_delete_keys() helper -- this proves the two stay
    wired together by forcing them apart and watching the shared-derivation guard catch it. If
    the two derivations could silently drift, this shape would resolve a PARTIAL delete_ids list
    (2 ids for a 1-item delete_match) instead of raising, and pass 3 would delete part of D while
    posting P -- the partial write SPEC section 3 exists to prevent.

    verdict_for is monkeypatched to force a `ready` verdict for rows that do NOT actually satisfy
    R == D (plan_entry()'s delete_match names ONE CNAME; address_rows() is TWO A/AAAA records) --
    a shape verdict_for itself would never produce, which is exactly why the check inside
    validate_entries has to be a same-scope invariant assertion rather than trusted from the
    verdict alone.
    """
    monkeypatch.setattr(apc, "verdict_for", lambda entry, rows: ("ready", ""))
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [address_rows()]})
    with pytest.raises(apc.InvariantError) as excinfo:
        apc.validate_entries(client, {"a.umich.edu": plan_entry()}, verbose=False)
    assert "a.umich.edu" in str(excinfo.value)
    assert "2 delete ids" in str(excinfo.value)
    assert "1 delete_match" in str(excinfo.value)


def test_the_network_guard_itself_can_fire(apc, tmp_path, refuse_real_network):
    """SPEC section 13's mandated guard self-test (task 5 review, Minor 5): refuse_real_network
    hooks httpx.Client.send, which is an implementation detail of the CURRENT cloudflare SDK's
    request path -- if a future SDK upgrade changed that path, the guard would go silently inert
    and every other test in this file would pass for the wrong reason (PD#14; CLAUDE.md's
    two-sitecustomize.py failure shape).

    Calls httpx.Client.send DIRECTLY, via client._client (the SAME `sent_request()` idiom this
    file already uses for the credential tests, `from cloudflare._models import
    FinalRequestOptions`), rather than through a full `client.zones.list()` round trip: the SDK's
    OWN retry loop (see refuse_real_network's docstring) would catch the inline AssertionError
    and re-raise it as `cloudflare.APIConnectionError` instead, which is exactly the swallowing
    this guard's teardown placement exists to survive -- but that swallowing means asserting
    `pytest.raises(AssertionError)` around `client.zones.list()` itself would raise the WRONG
    exception here and fail this test for an uninformative reason.  Depends on
    `refuse_real_network` explicitly (autouse does not prevent that) to read the fixture's own
    `reached` list and then clear it, so proving the guard fired here does not ALSO trip the
    fixture's teardown assertion for an unrelated test.
    """
    from cloudflare._models import FinalRequestOptions
    path = config_file(tmp_path, '[Cloudflare]\napi_token = "tok-123"\n')
    client = apc.cloudflare_client(path)
    request = client._build_request(FinalRequestOptions(method="get", url="/zones"))
    with pytest.raises(AssertionError, match="real network call attempted"):
        httpx.Client.send(client._client, request)
    assert refuse_real_network, (
        "the guard never reached httpx.Client.send -- SPEC section 13's self-test requirement "
        "exists for exactly this: prove it before trusting it")
    refuse_real_network.clear()


# ---------------------------------------------------------------------------------------------
# Task 6: the outcome tally, exit codes, and the summary block (SPEC section 8, 11.3, R8).  Pure.
# ---------------------------------------------------------------------------------------------


def test_tally_zero_fills_every_outcome(apc):
    counts = apc.tally({"a": "applied"})
    assert counts == {"applied": 1, "already-applied": 0, "planned": 0,
                      "failed": 0, "unknown": 0, "not-attempted": 0}


def test_exit_code_zero_when_everything_applied(apc):
    assert apc.exit_code_for(apc.tally({"a": "applied", "b": "applied"})) == 0


def test_exit_code_zero_for_a_clean_dry_run(apc):
    assert apc.exit_code_for(apc.tally({"a": "planned", "b": "planned"})) == 0


def test_exit_code_one_when_anything_was_already_applied(apc):
    assert apc.exit_code_for(apc.tally({"a": "applied", "b": "already-applied"})) == 1


def test_exit_code_one_when_everything_was_already_applied(apc):
    """SPEC section 14 group 11 names the already-applied-ONLY case explicitly, distinct from
    the mix above (which pairs already-applied with a fresh apply)."""
    assert apc.exit_code_for(
        apc.tally({"a": "already-applied", "b": "already-applied"})) == 1


def test_tally_raises_invariant_error_on_an_unrecognized_outcome(apc):
    """tally's closed vocabulary MUST be enforced the same way verdict_for's and
    validate_entries's already are -- a typo'd outcome literal upstream must be named, not
    silently dropped (PD#2)."""
    with pytest.raises(apc.InvariantError):
        apc.tally({"a": "bogus"})


def test_exit_code_two_when_a_failure_changed_nothing(apc):
    """The first entry failed, so its batch never committed -- Cloudflare is untouched."""
    assert apc.exit_code_for(apc.tally({"a": "failed", "b": "not-attempted"})) == 2


def test_exit_code_three_when_a_failure_followed_a_successful_apply(apc):
    assert apc.exit_code_for(
        apc.tally({"a": "applied", "b": "failed", "c": "not-attempted"})) == 3


def test_exit_code_three_when_the_only_outcome_is_unknown(apc):
    """SPEC 8.1: an entry whose call raised a timeout did not tell us whether Cloudflare
    committed it.  Counting that as unchanged would let the process claim "nothing was changed"
    about a production DNS rewrite it cannot account for."""
    assert apc.exit_code_for(apc.tally({"a": "unknown", "b": "not-attempted"})) == 3


def test_exit_code_one_beats_zero_but_never_masks_a_failure(apc):
    assert apc.exit_code_for(
        apc.tally({"a": "already-applied", "b": "failed"})) == 2


def test_summary_says_entries_are_fqdns_not_sites(apc):
    """SPEC R8.2: the plan file carries no site information, and several FQDNs can belong to one
    Pantheon site.  Printing an FQDN count under the word "sites" would be a wrong number in an
    operator's incident notes."""
    lines = apc.summary_lines(
        direction="plan", source="p.json", source_generated_at="2026-08-01T00:22:23Z",
        for_real=False, entries_in_file=217, selected=217,
        counts=apc.tally({"a": "planned"}), record_path="p-run-X.json")
    text = "\n".join(lines)
    assert "entries are FQDNs, not Pantheon sites" in text
    assert "entries in file: 217" in text
    assert "selected: 217" in text


def test_summary_never_swaps_entries_in_file_and_selected(apc):
    """R7.2/R7.4: entries_in_file != selected is the NORMAL shape of any --only subset run --
    exactly the scenario R8.2 exists to report correctly.  Using distinct, non-equal values (as
    every other summary test in this file deliberately does NOT) is load-bearing here: a bare
    `"217" in text` cannot tell the two fields apart when both happen to be 217, and a later task
    passing the two arguments in the wrong order would ship silently against such a test."""
    lines = apc.summary_lines(
        direction="plan", source="p.json", source_generated_at="x", for_real=False,
        entries_in_file=217, selected=3, counts=apc.tally({"a": "planned"}),
        record_path="p-run-X.json")
    text = "\n".join(lines)
    assert "entries in file: 217" in text
    assert "selected: 3" in text
    assert "entries in file: 3" not in text
    assert "selected: 217" not in text


def test_summary_names_the_mode_unmistakably(apc):
    dry = "\n".join(apc.summary_lines(
        direction="plan", source="p.json", source_generated_at="x", for_real=False,
        entries_in_file=1, selected=1, counts=apc.tally({"a": "planned"}),
        record_path="r.json"))
    real = "\n".join(apc.summary_lines(
        direction="plan", source="p.json", source_generated_at="x", for_real=True,
        entries_in_file=1, selected=1, counts=apc.tally({"a": "applied"}),
        record_path="r.json"))
    assert "DRY RUN -- no changes were made" in dry
    assert "FOR REAL" in real
    assert "DRY RUN" not in real


def test_summary_for_real_mode_line_is_derived_from_the_tally_not_the_flag(apc):
    """SPEC 11.3 (amended, task 7 review, important 2): 'FOR REAL -- changes were made' is a
    claim about production DNS.  Measured before this fix: a --for-real run that reached no
    entry (every one already-applied, or an abort in validation) printed that claim while
    `batch_calls == []` -- a for-real run that changed nothing must say so honestly."""
    zero_changed = "\n".join(apc.summary_lines(
        direction="plan", source="p.json", source_generated_at="x", for_real=True,
        entries_in_file=1, selected=1, counts=apc.tally({"a": "already-applied"}),
        record_path="r.json"))
    assert "FOR REAL -- 0 of 1 entries changed" in zero_changed
    assert "changes were made" not in zero_changed

    some_changed = "\n".join(apc.summary_lines(
        direction="plan", source="p.json", source_generated_at="x", for_real=True,
        entries_in_file=3, selected=3,
        counts=apc.tally({"a": "applied", "b": "unknown", "c": "already-applied"}),
        record_path="r.json"))
    assert "FOR REAL -- 2 of 3 entries changed" in some_changed   # applied + unknown, per SPEC 8.1


def test_summary_prints_the_source_files_own_timestamp(apc):
    """SPEC 11.3: this spec deliberately does not re-resolve targets, so the age of the file is
    the operator's only staleness signal -- and mtime survives neither a copy nor `git add`."""
    lines = apc.summary_lines(
        direction="revert", source="r.json", source_generated_at="2026-08-01T00:22:23Z",
        for_real=True, entries_in_file=1, selected=1,
        counts=apc.tally({"a": "applied"}), record_path="x.json")
    assert any("2026-08-01T00:22:23Z" in line for line in lines)


# ---------------------------------------------------------------------------------------------
# Task 7: pass 2 (the report) and the dry run end to end (SPEC R3.3, R2.6, section 11).
# ---------------------------------------------------------------------------------------------


def test_merge_body_puts_deletes_beside_the_files_posts_unchanged(apc):
    entry = plan_entry()
    body = apc.merge_body(entry, ["rec-1"])
    assert body["deletes"] == [{"id": "rec-1"}]
    assert body["posts"] == entry["body"]["posts"]
    assert set(body) == {"deletes", "posts"}


def test_merge_body_never_mutates_the_entry(apc):
    """The entry is written to the run record afterwards; a mutated body would misreport what
    the file said."""
    entry = plan_entry()
    apc.merge_body(entry, ["rec-1"])
    assert "deletes" not in entry["body"]


def test_merge_body_raises_invariant_error_on_missing_or_empty_posts(apc):
    """SPEC 9.1: section 6 check 7 should already have made an empty/missing body.posts fatal
    before pass 1 ever ran.  Task 7 review, important 4: measured on HEAD before this guard
    existed, merge_body(entry-without-posts, ids) raised a bare, unnamed `KeyError: 'posts'`."""
    entry = plan_entry()
    entry["body"]["posts"] = []
    with pytest.raises(apc.InvariantError):
        apc.merge_body(entry, ["rec-1"])

    missing_body = plan_entry()
    del missing_body["body"]
    with pytest.raises(apc.InvariantError):
        apc.merge_body(missing_body, ["rec-1"])


def test_merge_body_raises_invariant_error_on_empty_delete_ids(apc):
    """SPEC 9.1's own trigger list names 'a delete id pass 1 never resolved'.  Task 7 review,
    important 4: measured on HEAD before this guard existed, merge_body(entry, []) silently
    returned {"deletes": [], "posts": [...]} -- posting the new records while deleting NOTHING,
    the exact partial-write shape section 3 exists to prevent (Task 8's apply would then leave
    the CNAME standing beside the new A/AAAA records)."""
    with pytest.raises(apc.InvariantError):
        apc.merge_body(plan_entry(), [])


def test_describe_change_shows_both_sides_and_the_zone_id(apc):
    """SPEC 11.4: the zone ID, not a zone name -- the plan entry carries zone_id and nothing
    else about the zone, and looking up a name would be a second API read for cosmetics.

    Task 7 review, minor 6: (proxied, ttl N) is deletable from describe_change with the whole
    suite still green (measured) unless something asserts it -- this does."""
    line = apc.describe_change("a.umich.edu", plan_entry())
    assert "a.umich.edu" in line
    assert "zone-a" in line
    assert "live-umich-x.pantheonsite.io" in line
    assert "23.185.0.4" in line
    assert "2620:12a:8000::4" in line
    assert "(proxied, ttl 1)" in line


def test_describe_change_groups_same_type_records_and_joins_types_with_plus(apc):
    """SPEC 11.4's own example line groups same-TYPE contents with ', ' and joins DIFFERENT
    types with ' + ': "A 23.185.0.4 + AAAA 2620:12a:8000::4, 2620:12a:8001::4".  Task 7 review,
    minor 9: the shipped code used ", ".join throughout, which cannot express that distinction
    (two A records would render indistinguishably from one A and one AAAA)."""
    entry = plan_entry(addresses=("23.185.0.4", "23.185.0.5", "2620:12a:8000::4"))
    line = apc.describe_change("a.umich.edu", entry)
    assert "A 23.185.0.4, 23.185.0.5 + AAAA 2620:12a:8000::4" in line


def test_describe_change_renders_a_revert_entry_correctly(apc):
    """Task 7 review, minor 7: revert is the EMERGENCY path and the one direction where
    posts[0] is a different record type (CNAME) than delete_match (A/AAAA) -- rendered correctly
    by hand-inspection in the review, but with no test pinning it before this one."""
    entry = plan_entry()
    entry["delete_match"], entry["body"]["posts"] = (
        [{"type": "A", "name": "a.umich.edu", "content": "23.185.0.4"},
         {"type": "AAAA", "name": "a.umich.edu", "content": "2620:12a:8000::4"}],
        [{"type": "CNAME", "name": "a.umich.edu",
          "content": "live-umich-x.pantheonsite.io", "proxied": True, "ttl": 1}])
    line = apc.describe_change("a.umich.edu", entry)
    assert "A 23.185.0.4 + AAAA 2620:12a:8000::4 -> CNAME live-umich-x.pantheonsite.io" in line


def test_describe_change_raises_invariant_error_on_the_impossible_empty_shape(apc):
    """SPEC 9.1: an entry reaching describe_change with an empty/missing delete_match or
    body.posts is a defect in this script's own reasoning (section 6 checks 7/8 should already
    have made it fatal), not a shape to render.  Task 7 review, important 4: measured on HEAD
    before this guard existed, describe_change(empty posts) raised a bare, unnamed
    `IndexError: list index out of range` from `posts[0]` -- PD#2 requires a name."""
    entry = plan_entry()
    entry["body"]["posts"] = []
    with pytest.raises(apc.InvariantError):
        apc.describe_change("a.umich.edu", entry)

    missing_delete_match = plan_entry()
    del missing_delete_match["delete_match"]
    with pytest.raises(apc.InvariantError):
        apc.describe_change("a.umich.edu", missing_delete_match)


def run_main(apc, argv, tmp_path, client, monkeypatch):
    """Drive main() with a fake client and a frozen clock."""
    monkeypatch.setattr(apc, "cloudflare_client", lambda path: client)
    monkeypatch.setattr(apc, "now_utc", lambda: "2026-08-03T14:22:11Z")
    monkeypatch.chdir(tmp_path)
    return apc.main(argv)


def test_a_dry_run_makes_zero_batch_calls(apc, tmp_path, monkeypatch, capsys):
    """SPEC R2.6, the primary blast-radius control.  Asserted against the fake client's RECORDED
    calls, never inferred from the absence of an error."""
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})
    code = run_main(apc, [path], tmp_path, client, monkeypatch)
    assert client.batch_calls == []
    assert code == 0
    assert "DRY RUN" in capsys.readouterr().out


def test_a_dry_run_reports_the_change_it_would_make(apc, tmp_path, monkeypatch, capsys):
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})
    run_main(apc, [path], tmp_path, client, monkeypatch)
    out = capsys.readouterr().out
    assert "a.umich.edu" in out
    assert "23.185.0.4" in out


def test_a_dry_run_reports_a_revert_entrys_change_correctly(
        apc, tmp_path, monkeypatch, capsys):
    """Task 7 review, minor 7: report_entries/describe_change had zero revert-direction coverage
    through main() before this test -- revert is the emergency path."""
    entry = plan_entry()
    entry["delete_match"], entry["body"]["posts"] = (
        [{"type": "A", "name": "a.umich.edu", "content": "23.185.0.4"},
         {"type": "AAAA", "name": "a.umich.edu", "content": "2620:12a:8000::4"}],
        [{"type": "CNAME", "name": "a.umich.edu",
          "content": "live-umich-x.pantheonsite.io", "proxied": True, "ttl": 1}])
    doc = plan_doc(entries={"a.umich.edu": entry}, direction="revert")
    path = write_doc(tmp_path, doc, name="platform-domains-cloudflare-revert.json")
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [address_rows()]})
    code = run_main(apc, [path], tmp_path, client, monkeypatch)
    assert code == 0
    out = capsys.readouterr().out
    assert "A 23.185.0.4 + AAAA 2620:12a:8000::4 -> CNAME live-umich-x.pantheonsite.io" in out
    assert "direction=revert" in out


def test_verbose_prints_the_exact_request_body(apc, tmp_path, monkeypatch, capsys):
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})
    run_main(apc, ["-v", path], tmp_path, client, monkeypatch)
    out = capsys.readouterr().out
    assert "/zones/zone-a/dns_records/batch" in out
    assert '"deletes"' in out
    assert '"rec-1"' in out


def test_an_invalid_entry_aborts_the_run_at_exit_two_with_nothing_applied(
        apc, tmp_path, monkeypatch, capsys):
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [[]]})
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    assert code == 2
    assert client.batch_calls == []
    captured = capsys.readouterr()
    assert "ATTENTION" in captured.err
    # Task 7 review, minor 8: a bare `"ATTENTION" in out` assertion would still pass if the line
    # were duplicated onto stdout -- SPEC 11.2 puts it on stderr ONLY.
    assert "ATTENTION" not in captured.out


def test_every_invalid_entry_is_named_on_stderr_never_v_gated(
        apc, tmp_path, monkeypatch, capsys):
    """SPEC R7.3 / 11.2: these are the only signal that a destructive run was refused."""
    doc = plan_doc(entries={"a.umich.edu": plan_entry(),
                            "b.umich.edu": plan_entry(fqdn="b.umich.edu")})
    path = write_doc(tmp_path, doc)
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [[]], "b.umich.edu": [[]]})
    run_main(apc, [path], tmp_path, client, monkeypatch)
    captured = capsys.readouterr()
    assert "a.umich.edu" in captured.err
    assert "b.umich.edu" in captured.err
    assert "records-missing" in captured.err
    assert "records-missing" not in captured.out


def test_an_already_applied_run_exits_one_and_calls_nothing(
        apc, tmp_path, monkeypatch, capsys):
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [address_rows()]})
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    assert code == 1
    assert client.batch_calls == []
    # Task 7 review, minor 6: deleting report_entries' already-applied line entirely left the
    # whole suite green (measured) because no test called readouterr() here -- this does.
    assert "a.umich.edu  already applied -- nothing to do" in capsys.readouterr().out


def test_a_subset_run_warns_how_much_of_the_file_it_covers(
        apc, tmp_path, monkeypatch, capsys):
    doc = plan_doc(entries={"a.umich.edu": plan_entry(),
                            "b.umich.edu": plan_entry(fqdn="b.umich.edu")})
    path = write_doc(tmp_path, doc)
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})
    run_main(apc, ["--only", "a.umich.edu", path], tmp_path, client, monkeypatch)
    captured = capsys.readouterr()
    assert "ATTENTION: applying 1 of 2 entries" in captured.err
    assert "ATTENTION" not in captured.out


def test_an_unselected_entry_is_never_validated(apc, tmp_path, monkeypatch):
    """SPEC R7.2a: validating an entry the run will not touch would let an unrelated FQDN's
    drift abort a deliberately narrow, safe run."""
    doc = plan_doc(entries={"a.umich.edu": plan_entry(),
                            "b.umich.edu": plan_entry(fqdn="b.umich.edu")})
    path = write_doc(tmp_path, doc)
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})
    code = run_main(apc, ["--only", "a.umich.edu", path], tmp_path, client, monkeypatch)
    assert code == 0
    assert [call["name"]["exact"] for call in client.list_calls] == ["a.umich.edu"]


def test_a_for_real_run_prints_the_warning_banner_on_stderr_only(
        apc, tmp_path, monkeypatch, capsys):
    """SPEC 11.2's `FOR REAL -- changes WILL be made to Cloudflare` banner.  Task 7 review,
    important 2: absent before this fix, so the operator got the misleading `mode:` line with no
    warning beside it.  stderr only -- Task 7 review, minor 8: a stream assertion that only
    checks `in out` cannot tell a correctly-placed banner from one duplicated onto stdout."""
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [address_rows()]})
    run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    captured = capsys.readouterr()
    assert "FOR REAL -- changes WILL be made to Cloudflare" in captured.err
    assert "FOR REAL -- changes WILL be made to Cloudflare" not in captured.out


def test_a_dry_run_never_prints_the_for_real_banner(apc, tmp_path, monkeypatch, capsys):
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})
    run_main(apc, [path], tmp_path, client, monkeypatch)
    captured = capsys.readouterr()
    assert "FOR REAL" not in captured.err
    assert "FOR REAL" not in captured.out


def test_a_validation_failure_still_prints_the_summary_block(
        apc, tmp_path, monkeypatch, capsys):
    """SPEC R8.1: 'On every exit path -- normal, fatal, or interrupted -- the run MUST print the
    summary block.'  Task 7 review, important 3: measured on HEAD before this fix, the
    validation-failure path wrote ZERO bytes to stdout -- exit 2 with no report at all."""
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [[]]})
    code = run_main(apc, [path], tmp_path, client, monkeypatch)
    assert code == 2
    out = capsys.readouterr().out
    assert "apply-platform-domains-cloudflare: direction=plan" in out
    assert "not attempted 1" in out


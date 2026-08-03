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


@pytest.fixture
def apc():
    """The utility, loaded fresh.  Its entry point is __main__-guarded, so import runs nothing."""
    loader = SourceFileLoader("apply_platform_domains_cloudflare_probe", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


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


def test_a_doomed_stdout_is_a_named_exit_two_not_the_interpreters_120(apc):
    """CPython's shutdown flush of a doomed stream overrides the exit code with 120, which is
    outside this program's taxonomy entirely.  Measured on the sibling before its guards existed.
    """
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--only", "nope", "missing.json"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False,
        cwd=str(SCRIPT.parent))
    assert result.returncode != 120


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

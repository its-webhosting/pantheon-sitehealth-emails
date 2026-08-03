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


def test_cloudflare_client_prefers_the_api_token(apc, tmp_path, monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_EMAIL", raising=False)
    path = config_file(tmp_path, '[Cloudflare]\napi_token = "tok-123"\n')
    client = apc.cloudflare_client(path)
    request = client._build_request(
        types.SimpleNamespace(method="get", url="/zones", headers={}, json_data=None,
                              files=None, params={}, extra_json=None, timeout=None,
                              follow_redirects=None, idempotency_key=None, post_parser=None))
    assert request.headers["Authorization"] == "Bearer tok-123"


def test_cloudflare_client_ignores_an_ambient_base_url(apc, tmp_path, monkeypatch):
    """The worst of the four routes: an ambient CLOUDFLARE_BASE_URL sends the CONFIGURED
    credential to an arbitrary host.  Asserted against a REAL BUILT REQUEST, not against the
    attribute assignments that implement the pin -- the sibling's set-intersection version of
    this assertion silently missed the _custom_headers route."""
    monkeypatch.setenv("CLOUDFLARE_BASE_URL", "https://attacker.example/")
    path = config_file(tmp_path, '[Cloudflare]\napi_token = "tok-123"\n')
    client = apc.cloudflare_client(path)
    assert str(client.base_url).startswith(apc.API_BASE_URL)


def test_cloudflare_client_ignores_ambient_custom_headers(apc, tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_CUSTOM_HEADERS", "X-Auth-Email: leak@example.com")
    path = config_file(tmp_path, '[Cloudflare]\napi_token = "tok-123"\n')
    client = apc.cloudflare_client(path)
    assert client._custom_headers == {}


def test_cloudflare_client_ignores_an_ambient_email(apc, tmp_path, monkeypatch):
    """auth_headers returns the FIRST of email -> key -> token, so an ambient CLOUDFLARE_EMAIL
    beats a configured api_token and the token is never sent."""
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


def test_resolve_env_marker_refuses_a_form_it_cannot_resolve(apc):
    """A literal "<{secret aws ...}" handed to the API as a token surfaces as a baffling 401
    instead of a config error.  The body is withheld: an inline default can be a credential."""
    with pytest.raises(apc.StartupError) as excinfo:
        apc.resolve_env_marker("secret aws prod/key", "cfg [Cloudflare].api_token")
    assert "prod/key" not in str(excinfo.value)


def fake_api_status_error(status_code, body):
    """A fake matching the shape api_error_text() reads: status_code + body, class name
    "APIStatusError".

    NOT `types.SimpleNamespace(...)` with `__class__` reassigned afterwards: SimpleNamespace is
    not a CPython heap type (`__flags__ & Py_TPFLAGS_HEAPTYPE == 0`), so that reassignment always
    raises "TypeError: __class__ assignment only supported for mutable types..." -- reproducible
    on plain SimpleNamespace with no api_error_text involved at all.  The sibling's own
    `test_api_error_text_never_includes_a_real_response_body` sidesteps the same trap by
    constructing a real `cloudflare.PermissionDeniedError` instead.  Building the dynamic class
    and instantiating it directly (rather than grafting it onto an existing instance) gets the
    same "class name is APIStatusError" fake without hitting that restriction.
    """
    error_cls = type("APIStatusError", (Exception,), {})
    error = error_cls()
    error.status_code = status_code
    error.body = body
    return error


def test_api_error_text_says_nothing_but_the_status_on_an_auth_failure(apc):
    """SPEC 9.1 rule 2.  The sibling's docstring: "an auth-failure body can echo the credential".
    401 and 403 report the class and status ALONE."""
    for status in (401, 403):
        error = fake_api_status_error(
            status, {"errors": [{"code": 10000, "message": "SECRET-TOKEN"}]})
        text = apc.api_error_text(error)
        assert str(status) in text
        assert "SECRET-TOKEN" not in text


def test_api_error_text_admits_structured_errors_on_a_non_auth_failure(apc):
    error = fake_api_status_error(
        400, {"errors": [{"code": 81058, "message": "An identical record already exists."}]})
    text = apc.api_error_text(error)
    assert "81058" in text
    assert "identical record already exists" in text


def test_api_error_text_truncates_a_long_message(apc):
    """SPEC 9.1 rule 3: an unexpectedly large or repeating error array must not become a dump of
    arbitrary server-supplied text in an operator's log."""
    error = fake_api_status_error(400, {"errors": [{"code": 1, "message": "x" * 300}]})
    text = apc.api_error_text(error)
    assert "x" * apc.ERROR_MESSAGE_LIMIT in text
    assert "x" * (apc.ERROR_MESSAGE_LIMIT + 1) not in text

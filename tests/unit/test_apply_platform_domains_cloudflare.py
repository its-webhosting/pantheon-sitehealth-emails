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
import datetime
import importlib.util
import io
import json
import os
import re
import shlex
import signal
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

# Captured at IMPORT time, before `refuse_real_network` (below) ever monkeypatches
# httpx.Client.send -- CRITICAL 1's real-retry test (test_apply_entry_sends_the_batch_post_
# exactly_once_on_a_retryable_status) needs the SDK's own retry loop to run against a
# MockTransport-backed client, which means going THROUGH httpx.Client.send, exactly what that
# autouse guard exists to block for every OTHER test in this file.  A MockTransport never opens a
# real socket -- interception happens at the transport layer -- so restoring the true `send` for
# one test's duration is not a hole in the guard, it is the one place this file's own SPEC section
# 13 seam (a real Cloudflare client) needs its request path to actually run.
REAL_HTTPX_CLIENT_SEND = httpx.Client.send

DEV_FULL = "/dev/full"
needs_dev_full = pytest.mark.skipif(not os.path.exists(DEV_FULL),  # noqa: PTH110 -- a device
                                    reason="/dev/full is Linux-only")   # node, not a repo path


@pytest.fixture(autouse=True)
def _restore_sigint_handler():
    """Task 9: finish() calls the REAL `signal.signal(SIGINT, SIG_IGN)` (SPEC 9.3) on every exit
    path, and only the two tests that monkeypatch `apc.signal.signal` (the interrupt/second-Ctrl-C
    tests) intercept it -- every OTHER test in this file that drives `main()` to completion (most
    of them) calls the real one, and a process's signal handler is global and outlives the test
    that set it.  This is the EXACT bug class `tests/unit/test_find_platform_domains_dns.py`'s
    `_restore_sigint_handler` documents as "fix round 2, N1" for `report_stop()`'s identical
    guard -- measured here too: without this fixture, SIGINT was still SIG_IGN at the end of the
    WHOLE `--fast` session, caught only by that OTHER file's session-scoped
    `_sigint_handler_is_never_left_ignored_at_session_end` fixture (which is session-scoped and so
    applies across every test file, not just its own).  Autouse and function-scoped -- restoring
    the handler that was in place BEFORE this test ran, regardless of what the test (or the code
    under test) did to it, is what catches a leak between any two tests, not just at session end.
    """
    original = signal.getsignal(signal.SIGINT)
    yield
    signal.signal(signal.SIGINT, original)


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
    StartupError subclasses so main()'s ONE `except StartupError` handler catches them all --
    they add names, not code paths (PD#2).

    Minor 7 (review round 1): this docstring used to claim the handler "gives them all exit 2",
    which stopped being true once `failure_code(state)` made that handler changed-aware
    (Critical 1): InvariantError and OutputWriteError can both earn exit 3 when an earlier entry
    in the same run already applied (`test_a_mid_run_invariant_error_after_an_applied_entry_exits_
    three_not_two` and the record-write-failure precedence tests cover that directly).  What THIS
    test actually pins is narrower and still true: they share ONE handler, not that the handler's
    output is a constant.  ApplyError is deliberately NOT a StartupError subclass: it usually
    means exit 3."""
    for name in ("PlanFileError", "InvariantError", "OutputWriteError", "CloudflareReadError"):
        assert issubclass(getattr(apc, name), apc.StartupError), name
    assert not issubclass(apc.ApplyError, apc.StartupError)


def run_apc_in_a_subprocess(tmp_path, argv, *, stdout, stderr, empty_rows=False):
    """Drive the REAL main() in a real interpreter, so the shutdown flush that produces exit 120
    actually runs.  An in-process test cannot observe it: pytest never tears the interpreter down
    between tests, so the whole 120 mechanism is invisible to one (SPEC 11.1).

    The fake client is a plain class embedded in the driver source (not FakeCloudflareClient --
    that class lives in THIS process, not the subprocess's fresh interpreter).  By default it
    returns rows that make the one entry `already-applied`, so main() reaches pass 2's report and
    the summary without ever needing a real Cloudflare credential.  `empty_rows=True` (I2,
    whole-branch review) makes it return NOTHING instead, so the entry classifies
    `records-missing` -- the shape that reaches `abort_on_invalid_entries`' UNGUARDED stderr
    ATTENTION print (SPEC 11.2), the one this file's doomed-stderr test needs to hit.
    """
    driver = tmp_path / "driver.py"
    rows_literal = "[]" if empty_rows else """[
                types.SimpleNamespace(id="rec-a", type="A", name="a.umich.edu",
                                      content="23.185.0.4"),
                types.SimpleNamespace(id="rec-b", type="AAAA", name="a.umich.edu",
                                      content="2620:12a:8000::4")]"""
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
        rows = {rows_literal}
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
def test_a_doomed_stderr_exits_2_not_120_in_a_real_subprocess(tmp_path):
    """I2 (whole-branch review): SPEC section 14 group 14 requires this counterpart to the
    doomed-stdout test above, and it had none -- the reviewer verified BY HAND that
    report_line()'s detach-on-failure guard already makes the behavior correct, so this closes a
    missing INSTRUMENT (PD#14), not a defect.  `empty_rows=True` makes the one entry classify
    `records-missing`, which is what reaches `abort_on_invalid_entries`' UNGUARDED stderr
    ATTENTION print (SPEC 11.2) -- the first stderr write in this run, and one that happens
    BEFORE `report_line`'s own guarded write ever gets a turn."""
    path = write_doc(tmp_path, plan_doc())
    with Path(DEV_FULL).open("w") as doomed_err:
        completed = run_apc_in_a_subprocess(tmp_path, [path], stdout=subprocess.PIPE,
                                            stderr=doomed_err, empty_rows=True)
    assert completed.returncode == 2


def test_require_usable_streams_exits_2_with_stdout_truly_closed_in_a_real_subprocess(tmp_path):
    """I5 (whole-branch review): replacing run_once's `require_usable_streams()` call with `pass`
    leaves the whole suite green -- the guard is load-bearing precisely because a subprocess with
    stdout genuinely CLOSED (`>&-`), not merely doomed (`/dev/full`), needs it: measured directly
    (see the bare `sys.stdout = None; print("hi")` probe in the task report), CPython's own
    `print()` SILENTLY DOES NOTHING when `sys.stdout is None` -- no exception, no output at all --
    so nothing short of this guard would ever report the failure.  `stdout=subprocess.DEVNULL`
    cannot reproduce this: /dev/null accepts every write, so `sys.stdout` would stay a healthy
    stream.  An in-process `monkeypatch.setattr(apc.sys, "stdout", None)` test already exists for
    the FUNCTION (`test_require_usable_streams_refuses_a_closed_stdout`); this is its end-to-end
    counterpart through a real interpreter, matching this file's other subprocess tests' reason
    for existing (SPEC 11.1)."""
    path = write_doc(tmp_path, plan_doc())
    driver = tmp_path / "driver.py"
    driver.write_text(f"""
import sys
from importlib.machinery import SourceFileLoader
import importlib.util
loader = SourceFileLoader("apc_closed_stdout", {str(SCRIPT)!r})
spec = importlib.util.spec_from_loader("apc_closed_stdout", loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)
sys.exit(m.main(sys.argv[1:]))
""")
    command = shlex.join([sys.executable, str(driver), path]) + " 1>&-"
    completed = subprocess.run(["sh", "-c", command], stderr=subprocess.PIPE, check=False,  # noqa: S607 --
                               # "sh" via PATH is deliberate: `1>&-` is POSIX shell redirection
                               # syntax, not something subprocess.run can express without a shell.
                               cwd=str(tmp_path))
    assert completed.returncode == 2
    assert b"standard output is closed" in completed.stderr


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


@needs_dev_full
def test_report_line_detaches_stdout_not_stderr_when_stderr_is_none(apc, monkeypatch):
    """B10 (final-batch review): `report_line`'s except-clause stream choice --
    `point_at_devnull(sys.stdout if sys.stderr is None else sys.stderr)` -- was unpinned.  With
    stderr CLOSED (`sys.stderr is None`, CPython's `2>&-` shape) and stdout doomed,
    `print(text, file=sys.stderr, ...)` falls back to `sys.stdout` (report_line's own docstring)
    and THAT write fails -- so a mutated form that targeted `sys.stderr` (None) instead of the
    conditional would call `point_at_devnull(None)`, whose `AttributeError` (`None` has no
    `.fileno`) is not in `point_at_devnull`'s suppress list and would escape from inside this
    `except OSError` clause: an unnamed crash in the "nowhere left to report" path SPEC 11.1
    exists to guard.  `monkeypatch.setattr(apc.sys, "stderr", None)` reproduces `2>&-` directly
    in-process -- the same direct-seam idiom `test_write_report_detaches_and_raises_on_a_doomed_
    stdout` above already uses for `write_report`'s mechanism, and the honest, observable cover:
    it can confirm stdout was actually REPOINTED (a later write through the same file object
    succeeds), not just that nothing raised."""
    with Path(DEV_FULL).open("w") as doomed:
        monkeypatch.setattr(apc.sys, "stdout", doomed)
        monkeypatch.setattr(apc.sys, "stderr", None)
        apc.report_line("nowhere to report this")   # must not raise -- report_line's own
        # contract: it swallows an OSError here, there being nothing left to report to.
        doomed.write("proof the fd was repointed at /dev/null, not merely that nothing raised")


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


def plan_doc(entries=None, direction="plan", generated=None):
    """A document in the shape `find-platform-domains-cloudflare` really writes.

    `zones_swept`/`zones_total` are part of that shape (its `provenance()` emits both, as two
    integers, so "a machine reads this") and were missing from this fixture until the 2026-08-04
    adversarial review's finding 5 -- a file with no coverage header is not the file the sibling
    produces, so a fixture without them cannot exercise the complete-sweep path at all.

    `at` stays 2026-08-01T00:22:23Z against `run_main`'s frozen 2026-08-03T14:22:11Z clock, which
    is 62 hours: DELIBERATELY older than STALE_PLAN_HOURS, so every main()-driving test in this
    file carries the staleness ATTENTION finding 10 added, and a mutation removing it has ~60
    tests' worth of stderr to survive.
    """
    header = {"direction": direction, "at": "2026-08-01T00:22:23Z",
              "zones_swept": 187, "zones_total": 187}
    header.update(generated or {})
    return {"generated": header,
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


def test_read_apply_file_rejects_a_duplicate_top_level_key(apc, tmp_path):
    """Final-batch review, A1: plain `json.load` is silently LAST-WINS on a duplicate JSON object
    key, so a duplicated `generated` object is discarded without a trace rather than reported --
    the same under-reporting shape R7.3 refuses to have for an unmatched --only name.  Applied to
    the WHOLE document, not just `entries` (a duplicated `generated` is exactly as silent as a
    duplicated entry key)."""
    path = tmp_path / "dup-generated.json"
    path.write_text(
        '{"generated": {"direction": "plan", "at": "a"}, '
        '"generated": {"direction": "revert", "at": "b"}, '
        '"entries": {"a.umich.edu": {}}}')
    with pytest.raises(apc.PlanFileError, match=r"duplicate.*generated"):
        apc.read_apply_file(str(path))


def test_read_apply_file_rejects_a_duplicate_entry_key(apc, tmp_path):
    """Final-batch review, A1.  Measured: two entry objects for the SAME FQDN naming DIFFERENT
    zones -- `entries in file` reported 1, not 2, and the operator got no signal a second entry
    was silently discarded (the exact `zone-SECOND`-wins shape the review measured)."""
    path = tmp_path / "dup-entry.json"
    path.write_text(
        '{"generated": {"direction": "plan", "at": "a"}, '
        '"entries": {"a.umich.edu": {"zone_id": "zone-FIRST"}, '
        '"a.umich.edu": {"zone_id": "zone-SECOND"}}}')
    with pytest.raises(apc.PlanFileError, match=r"duplicate.*a\.umich\.edu"):
        apc.read_apply_file(str(path))


def test_check_file_contract_returns_the_direction(apc):
    assert apc.check_file_contract(plan_doc(), "p.json") == "plan"
    assert apc.check_file_contract(plan_doc(direction="revert"), "p.json") == "revert"


def test_check_file_contract_refuses_an_excluded_file_by_name(apc):
    """SPEC section 6 check 2.  An -excluded.json has the same header shape and no `body`
    anywhere, so it must be named, not merely rejected as malformed.

    I3 (whole-branch review): `match="excluded"` also matches the FALL-THROUGH message
    ("generated.direction must be 'plan' or 'revert', got 'excluded'") -- deleting the entire
    by-name branch left the whole suite green.  Asserting the distinguishing "is an EXCLUDED
    file" phrase, plus the "carries no request body" sentence that only the by-name branch
    writes, is what makes this test able to fail."""
    doc = plan_doc(direction="excluded")
    with pytest.raises(apc.PlanFileError, match="is an EXCLUDED file") as excinfo:
        apc.check_file_contract(doc, "p.json")
    assert "carries no request body" in str(excinfo.value)


def test_check_file_contract_refuses_a_missing_direction(apc):
    doc = plan_doc()
    del doc["generated"]["direction"]
    with pytest.raises(apc.PlanFileError, match="direction"):
        apc.check_file_contract(doc, "p.json")


def test_check_file_contract_refuses_an_empty_entries_object(apc):
    with pytest.raises(apc.PlanFileError, match="no entries"):
        apc.check_file_contract(plan_doc(entries={}), "p.json")


def test_check_file_contract_refuses_a_json_array_for_entries(apc):
    """B3 (final-batch review): `if not entries:` in place of `if not isinstance(entries, dict)
    or not entries:` left 164 passing.  A non-empty JSON ARRAY for `entries` is TRUTHY, so it
    would fall straight through a bare `if not entries:` guard and degrade section 6 check 3 to
    an anonymous `AttributeError` the moment `sorted(entries.items())` runs a few lines down (a
    list has no `.items()`) -- exactly the un-named failure PD#2 forbids."""
    with pytest.raises(apc.PlanFileError, match="no entries"):
        apc.check_file_contract(plan_doc(entries=[1, 2, 3]), "p.json")


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


@pytest.mark.parametrize("side", ["posts", "delete_match"])
@pytest.mark.parametrize("field", ["type", "name", "content"])
def test_check_record_list_names_a_missing_field_in_either_side(apc, side, field):
    """B2 (final-batch review): `check_record_list`'s required-field loop was proven only for
    `type` -- the out-of-scope-type test above exercises a BAD `type` VALUE, never a MISSING
    field, and no existing test covers `name`/`content` at all.  `for field in ("type",):` in
    place of `for field in ("type", "name", "content"):` left 164 passing: a post or
    `delete_match` item missing `name`/`content` would then reach `record_key` downstream as an
    anonymous `KeyError` instead of the named `PlanFileError` this loop exists to raise (PD#2).
    Parametrized over BOTH `posts` and `delete_match`: `check_record_list` is called
    independently for each."""
    entry = plan_entry()
    if side == "posts":
        del entry["body"]["posts"][0][field]
    else:
        del entry["delete_match"][0][field]
    with pytest.raises(apc.PlanFileError, match=rf"missing '{field}'"):
        apc.check_file_contract(plan_doc(entries={"a.umich.edu": entry}), "p.json")


@pytest.mark.parametrize("side", ["posts", "delete_match"])
def test_check_record_list_refuses_a_non_dict_item(apc, side):
    """B2 (final-batch review): the `if not isinstance(item, dict): raise PlanFileError(...)`
    guard was DEAD to the suite -- `if False:  # not isinstance(item, dict)` in its place left
    164 passing.  A non-dict item (a bare string, say) would otherwise reach `item.get(field)` /
    `item["type"]` a few lines down as an anonymous `AttributeError`/`TypeError` instead of this
    named check."""
    entry = plan_entry()
    if side == "posts":
        entry["body"]["posts"] = ["not-a-dict", *entry["body"]["posts"]]
    else:
        entry["delete_match"] = ["not-a-dict", *entry["delete_match"]]
    with pytest.raises(apc.PlanFileError, match="not an object"):
        apc.check_file_contract(plan_doc(entries={"a.umich.edu": entry}), "p.json")


def test_check_file_contract_refuses_an_empty_delete_match(apc):
    entry = plan_entry()
    entry["delete_match"] = []
    with pytest.raises(apc.PlanFileError, match="delete_match"):
        apc.check_file_contract(plan_doc(entries={"a.umich.edu": entry}), "p.json")


def test_check_file_contract_refuses_a_post_naming_a_different_fqdn(apc):
    """CRITICAL 2 (whole-branch review): SPEC section 6 check 7 validated a post's type/name/
    content are PRESENT, never that `name` is the FQDN the entry is keyed by.  Everything
    downstream assumes it -- pass 1 lists and computes the verdict at the entry's key, pass 3
    POSTs whatever `posts[].name` says.  Measured before this check existed: an entry keyed
    a.umich.edu with a post naming another host reached apply_entry's batch call unnoticed --
    the verdict had been computed at ONE name, the write would land at another whose records
    were never read."""
    entry = plan_entry()
    entry["body"]["posts"][0]["name"] = "www.other-tenant.umich.edu"
    with pytest.raises(apc.PlanFileError, match=r"a\.umich\.edu.*does not match"):
        apc.check_file_contract(plan_doc(entries={"a.umich.edu": entry}), "p.json")


def test_check_file_contract_refuses_a_delete_match_naming_a_different_fqdn(apc):
    """The delete side is structurally safer than posts (R's names come from a `name.exact`
    listing at the entry's own fqdn, so a mismatched `delete_match` name can only resolve zero
    delete ids, which `verdict_for` already turns into an invalid `records-missing`) -- guarded
    here too because a named PlanFileError at file-load time is a far clearer signal than the
    confusing `records-missing` an operator would otherwise have to puzzle out."""
    entry = plan_entry()
    entry["delete_match"][0]["name"] = "www.other-tenant.umich.edu"
    with pytest.raises(apc.PlanFileError, match=r"a\.umich\.edu.*does not match"):
        apc.check_file_contract(plan_doc(entries={"a.umich.edu": entry}), "p.json")


def test_check_file_contract_accepts_a_post_name_that_only_differs_by_case_or_trailing_dot(apc):
    """The new name check normalizes both sides -- util3 SPEC section 5.1 states file keys are
    already normalized, but a hand-edited plan (SPEC section 15 item 13 explicitly anticipates
    one) could still carry a differently-cased or dotted name for the SAME host."""
    entry = plan_entry()
    entry["body"]["posts"][0]["name"] = "A.UMICH.EDU."
    entry["delete_match"][0]["name"] = "a.umich.edu."
    assert apc.check_file_contract(
        plan_doc(entries={"a.umich.edu": entry}), "p.json") == "plan"


def test_check_file_contract_refuses_posts_that_disagree_on_proxied_or_ttl(apc):
    """Adversarial review 2026-08-04, finding 11: this was `describe_change`'s `InvariantError`
    -- a class whose own docstring says it is "not an operator error" -- raised in PASS 2, after
    pass 1 had already read every entry from Cloudflare.  It is a property of the operator-supplied
    FILE, so it belongs in the section 6 contract (check 9): a named `PlanFileError`, before any
    Cloudflare call, naming the file and the offending post index.

    Both fields are exercised, and the disagreeing post is the SECOND of two, so a check that only
    ever read `posts[0]` -- the exact defect this replaces -- cannot pass."""
    proxied_disagrees = plan_entry(addresses=("23.185.0.4", "2620:12a:8000::4"))
    proxied_disagrees["body"]["posts"][1]["proxied"] = False
    with pytest.raises(apc.PlanFileError, match="disagree"):
        apc.check_file_contract(plan_doc(entries={"a.umich.edu": proxied_disagrees}), "p.json")

    ttl_disagrees = plan_entry(addresses=("23.185.0.4", "2620:12a:8000::4"))
    ttl_disagrees["body"]["posts"][1]["ttl"] = 300
    with pytest.raises(apc.PlanFileError, match="disagree"):
        apc.check_file_contract(plan_doc(entries={"a.umich.edu": ttl_disagrees}), "p.json")


def _malform_missing_zone_id(entry):
    del entry["zone_id"]


def _malform_non_post_method(entry):
    entry["method"] = "PUT"


def _malform_path_mismatch(entry):
    entry["path"] = "/zones/SOMEWHERE-ELSE/dns_records/batch"


def _malform_deletes_in_body(entry):
    entry["body"]["deletes"] = [{"id": "stale"}]


def _malform_empty_posts(entry):
    entry["body"]["posts"] = []


def _malform_out_of_scope_post_type(entry):
    entry["body"]["posts"][0]["type"] = "TXT"


def _malform_empty_delete_match(entry):
    entry["delete_match"] = []


@pytest.mark.parametrize(("mutate", "match"), [
    (_malform_missing_zone_id, "zone_id"),
    (_malform_non_post_method, "POST"),
    (_malform_path_mismatch, "path"),
    (_malform_deletes_in_body, "deletes"),
    (_malform_empty_posts, "posts"),
    (_malform_out_of_scope_post_type, "type"),
    (_malform_empty_delete_match, "delete_match"),
])
def test_check_file_contract_checks_every_entry_not_just_the_first(apc, mutate, match):
    """B1 (final-batch review): every EXISTING section 6 per-entry test above builds a ONE-entry
    doc, so a `break` added to `check_file_contract`'s `for fqdn, entry in
    sorted(entries.items()): check_entry_contract(...)` loop -- stopping after the FIRST entry --
    left 164 passing: the path-vs-zone_id cross-check, and every other per-entry check, then never
    ran for entries 2..N.  This parametrizes each check over a TWO-entry doc with the malformation
    on the SECOND key in SORT order ("b.umich.edu"), well-formed "a.umich.edu" first -- a
    first-entry-only loop passes the clean first entry and never reaches the malformed second
    one, so only a loop that actually visits every entry can raise here."""
    good = plan_entry(fqdn="a.umich.edu")
    bad = plan_entry(fqdn="b.umich.edu")
    mutate(bad)
    with pytest.raises(apc.PlanFileError, match=match):
        apc.check_file_contract(
            plan_doc(entries={"a.umich.edu": good, "b.umich.edu": bad}), "p.json")


NOW = "2026-08-03T14:22:11Z"   # the same frozen clock run_main installs


def provenance_header(drop=(), **overrides):
    header = {"direction": "plan", "at": "2026-08-03T12:22:11Z",
              "zones_swept": 187, "zones_total": 187}
    header.update(overrides)
    for key in drop:
        del header[key]
    return header


def test_read_provenance_is_quiet_on_a_complete_recent_sweep(apc):
    """Adversarial review 2026-08-04, findings 5 and 10.  The quiet case is asserted first and
    separately: a function that warned unconditionally would satisfy every other test here."""
    result = apc.read_provenance(provenance_header(), NOW)
    assert result.warnings == []
    assert (result.zones_swept, result.zones_total) == (187, 187)


def test_read_provenance_warns_that_a_partial_sweep_is_not_a_baseline(apc):
    """Finding 5.  The sibling writes zones_swept/zones_total "so an applier can verify the
    assumptions the file was built under" -- and the applier, the last program to see the file
    before production DNS changes, read only `generated.at`.  A subset sweep also cannot see a
    cross-zone duplicate, so an entry can look unambiguous when it is not."""
    result = apc.read_provenance(provenance_header(zones_swept=1), NOW)
    assert (result.zones_swept, result.zones_total) == (1, 187)
    assert len(result.warnings) == 1
    assert "PARTIAL sweep (1 of 187 zones)" in result.warnings[0]
    assert "MUST NOT" in result.warnings[0]


@pytest.mark.parametrize("header", [
    provenance_header(zones_swept=None, zones_total=None),
    provenance_header(drop=("zones_total",)),
    provenance_header(drop=("zones_swept", "zones_total")),
    provenance_header(zones_swept=True, zones_total=187),   # bool is an int subclass, not a count
    provenance_header(zones_swept="187", zones_total="187"),
])
def test_read_provenance_warns_when_the_coverage_cannot_be_verified(apc, header):
    """PD#3's nil/upstream shadows for a header this script does not write.  Silence would be
    ambiguous between "a complete sweep" and "no idea", which is PD#1's shape exactly.  `True` is
    included because `isinstance(True, int)` is True in Python -- a `zones_swept = true` typo must
    not read as one zone."""
    result = apc.read_provenance(header, NOW)
    assert result.warnings == [w for w in result.warnings if "CANNOT BE VERIFIED" in w]
    assert len(result.warnings) == 1
    assert result.zones_swept is None or result.zones_total is None


def test_read_provenance_warns_that_a_stale_plan_must_be_regenerated(apc):
    """Finding 10.  SPEC 20 declines RE-RESOLUTION and this does not reopen that: the age is
    already in the file and costs nothing to read.  Validation compares R against D (the CNAME),
    so a plan whose P addresses have gone stale validates perfectly `ready` and then writes the
    wrong addresses -- and the recorded project knowledge is that Pantheon rotates them."""
    result = apc.read_provenance(provenance_header(at="2026-07-31T14:22:11Z"), NOW)
    assert len(result.warnings) == 1
    assert "generated 72 hours ago (2026-07-31T14:22:11Z)" in result.warnings[0]
    assert "regenerate the baseline" in result.warnings[0]


def test_read_provenance_is_quiet_just_under_the_staleness_threshold(apc):
    """The boundary, from the quiet side -- without this, a threshold of zero would pass every
    other test in this group."""
    fresh = apc.read_provenance(provenance_header(at="2026-08-02T14:22:12Z"), NOW)
    assert fresh.warnings == []
    stale = apc.read_provenance(provenance_header(at="2026-08-02T14:22:11Z"), NOW)
    assert len(stale.warnings) == 1
    assert "24 hours ago" in stale.warnings[0]


@pytest.mark.parametrize("at", [None, "", "yesterday", 20260801, "2026-08-01"])
def test_read_provenance_warns_when_the_timestamp_cannot_be_read(apc, at):
    result = apc.read_provenance(provenance_header(at=at), NOW)
    assert len(result.warnings) == 1
    assert "CANNOT BE CHECKED" in result.warnings[0]


def test_read_provenance_warns_when_the_timestamp_is_in_the_future(apc):
    """Clock skew between the machine that swept and the machine applying.  Treating it as fresh
    would silently disable the staleness signal for exactly the file most likely to be wrong."""
    result = apc.read_provenance(provenance_header(at="2026-08-04T00:00:00Z"), NOW)
    assert len(result.warnings) == 1
    assert "FUTURE" in result.warnings[0]


def test_read_provenance_reports_both_problems_at_once(apc):
    """Neither warning may swallow the other: an operator holding a partial sweep from last week
    needs to be told both things, and a first-problem-wins function would name only one."""
    result = apc.read_provenance(
        provenance_header(zones_swept=1, at="2026-07-27T14:22:11Z"), NOW)
    assert len(result.warnings) == 2
    assert any("PARTIAL sweep" in w for w in result.warnings)
    assert any("hours ago" in w for w in result.warnings)


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


def test_cloudflare_client_email_and_key_branch_sends_only_the_configured_credential(
        apc, tmp_path, monkeypatch):
    """M7 (whole-branch review): the email+api_key branch was asserted only against ATTRIBUTE
    state (the test just above) -- `test_cloudflare_client_sends_only_the_configured_credential`
    covers only the `api_token` branch, and SPEC section 16 calls the real-built-request proof
    load-bearing precisely BECAUSE this script is the write-capable copy of the pin.  Same shape
    as that test, all six ambient variables exported, this time with an email/api_key config."""
    for name, value in AMBIENT_CLOUDFLARE_VARS.items():
        monkeypatch.setenv(name, value)
    path = config_file(tmp_path, '[Cloudflare]\nemail = "a@b.edu"\napi_key = "k-123"\n')
    client = apc.cloudflare_client(path)

    request = sent_request(client)
    assert str(request.url).startswith(apc.API_BASE_URL)
    assert request.headers.get("x-auth-email") == "a@b.edu"
    assert request.headers.get("x-auth-key") == "k-123"
    assert request.headers.get("authorization") is None   # no token configured
    assert "attacker.example" not in str(request.headers)    # route 3 payload
    assert "attacker.example" not in str(request.url)        # route 4
    assert "ambient-key" not in str(request.headers)
    assert "ambient-token" not in str(request.headers)
    assert "ambient@example.edu" not in str(request.headers)   # the AMBIENT email, not the
    # configured one -- route 1/2's whole hazard is an ambient credential beating a configured
    # one, so the header must carry "a@b.edu", never the exported CLOUDFLARE_EMAIL value.


def test_cloudflare_client_refuses_a_section_with_no_credentials(apc, tmp_path):
    """Adversarial review finding 4: mutating this guard (`if not email or not api_key:` ->
    `if False:`) left the whole suite green -- no test in this file ever drove `cloudflare_client`
    with a `[Cloudflare]` section that supplies NEITHER api_token NOR email+api_key.  This is not
    merely a message check: with the guard disabled, `cloudflare_client` would call
    `build_client(api_email=None, api_key=None)` -- see the sibling test below for why that is a
    credential-disclosure risk, not just a confusing error."""
    path = config_file(tmp_path, "[Cloudflare]\n")
    with pytest.raises(apc.StartupError, match="needs either api_token, or both email and api_key"):
        apc.cloudflare_client(path)


def test_build_client_sends_no_ambient_credential_when_none_are_configured(apc, monkeypatch):
    """Adversarial review finding 4, the more important half of the pair: this pins the
    `field not in creds` idiom in `build_client`'s pin ITSELF, independent of whether
    `cloudflare_client`'s guard above ever gets bypassed (by a future refactor or a defect, not
    just today's literal mutation) -- this is exactly the call `cloudflare_client` would make if
    it were.  Measured against cloudflare 5.4.0, with all six ambient variables the SDK reads
    exported: BEFORE this fix, `Cloudflare(api_email=None, api_key=None, ...)` reached the SDK's
    own `__init__`, which back-fills any credential still `None` from the environment -- and the
    ORIGINAL pin loop only re-nulled a field `not in creds`, so an EXPLICIT `api_email=None`/
    `api_key=None` (present in creds, merely None-valued) was left holding whatever the SDK had
    just back-filled: a REAL built request carried `x-auth-email: ambient@example.edu` /
    `x-auth-key: ambient-key` (measured, pasted in the task report).  With the fix
    (`creds.get(field) is None`, matching the SDK's own back-fill trigger), the client genuinely
    holds NO credential on any field -- proven at the attribute level -- and the SDK's OWN
    `_validate_headers` then refuses to build a request AT ALL (a real, independent safety net
    this test also proves is actually reached, not merely assumed): no header, ambient or
    otherwise, is ever sent."""
    for name, value in AMBIENT_CLOUDFLARE_VARS.items():
        monkeypatch.setenv(name, value)
    client = apc.build_client(api_email=None, api_key=None)
    assert client.api_email is None
    assert client.api_key is None
    assert client.api_token is None
    with pytest.raises(TypeError, match="Could not resolve authentication method"):
        sent_request(client)


def test_cloudflare_client_refuses_a_non_string_credential(apc, tmp_path):
    """TOML is typed: `api_token = true` is an ordinary unquoted-value typo, and the SDK would
    stringify it into `Authorization: Bearer True` -- a baffling 401."""
    path = config_file(tmp_path, "[Cloudflare]\napi_token = true\n")
    with pytest.raises(apc.StartupError, match="must be a string"):
        apc.cloudflare_client(path)


def test_build_client_pins_max_retries_to_zero(apc):
    """CRITICAL 1 (whole-branch review): cloudflare 5.4.0's `BaseClient._should_retry` has NO
    HTTP-method check, so the SDK's own default of 2 retries applies to a destructive POST
    exactly as to a GET.  `dns_records/batch` is one transaction (SPEC R5.4) -- a "failed"
    response the SDK silently retried can mean the FIRST attempt already committed.  Attribute
    check kept alongside the wire-level proof below (same rationale the other pin mechanism
    checks in this file state)."""
    assert apc.build_client(api_token="tok-123").max_retries == 0


def test_build_client_pin_is_destroyed_by_with_options_or_copy(apc, monkeypatch):
    """The `NEVER client.with_options(...)/client.copy(...)` line in `build_client`'s docstring,
    pinned as the security property it exists to prevent, not just asserted as prose.  Measured:
    both re-read the ambient environment for exactly the fields `build_client` nulls AFTER
    construction, so applying either to an already-pinned client re-opens routes 1/2 of the
    four-route pin (SPEC section 16) -- the configured token is DROPPED and the ambient
    X-Auth-Email is SENT, on the exact client that performs the write.  This is not a defect in
    `build_client` (which never calls `with_options`/`copy` itself) -- it pins the REASON the
    docstring's NEVER line exists, so a future maintainer reaching for `.with_options(max_retries=
    0)` as a "simpler" per-call spelling cannot ship that change with this suite green."""
    monkeypatch.setenv("CLOUDFLARE_EMAIL", "attacker@evil.example")
    client = apc.build_client(api_token="tok-123")

    copy = client.with_options(max_retries=0)
    request = sent_request(copy)

    assert request.headers.get("authorization") is None          # the configured token: GONE
    assert request.headers.get("x-auth-email") == "attacker@evil.example"   # the ambient one: SENT


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


def test_api_error_text_does_not_drop_a_real_error_hidden_behind_junk_entries(apc):
    """M1 (whole-branch review): `api_error_text` sliced `errors[:MAX_ADMITTED_ERRORS]` BEFORE
    filtering out non-dict junk entries -- five junk entries ahead of the one real error meant
    the real diagnosis was silently dropped entirely (measured pre-fix: 'BadRequestError: HTTP
    400', no code, no message at all).  Filtering to dicts FIRST, then slicing, is what keeps
    it."""
    junk = [None, "oops", 1, [], True]
    error = api_status_error(
        cloudflare.BadRequestError, 400,
        {"errors": [*junk, {"code": 81058, "message": "An identical record already exists."}]})
    text = apc.api_error_text(error)
    assert "81058" in text
    assert "identical record already exists" in text


def test_api_error_text_computes_remaining_from_the_filtered_set(apc):
    """M1: `remaining` must count REAL (dict) errors dropped by the cap, not the raw array
    length including junk -- a mix of junk and more real errors than MAX_ADMITTED_ERRORS must
    still report the correct number hidden."""
    dict_errors = [{"code": i, "message": f"reason {i}"}
                   for i in range(apc.MAX_ADMITTED_ERRORS + 2)]
    errors = ["junk", "more junk", *dict_errors]
    error = api_status_error(cloudflare.BadRequestError, 400, {"errors": errors})
    text = apc.api_error_text(error)
    assert f"and {len(dict_errors) - apc.MAX_ADMITTED_ERRORS} more" in text


def row(rtype="CNAME", name="a.umich.edu", content="live-umich-x.pantheonsite.io",
        identifier="rec-1", *, proxied=True):
    """A stand-in for one SDK record object as dns.records.list returns it.

    `proxied` is a real field on every SDK record model (`Optional[bool]`), and until the
    2026-08-04 adversarial review's finding 3 this helper omitted it entirely -- so no fixture in
    this file could tell a proxied replacement from a DNS-only one, which is the state whose loss
    the sibling calls "out of certificate service".  It defaults to True to match `plan_entry()`'s
    posts; a fixture in which EVERY record is proxied cannot detect a proxy-status defect either,
    so tests that care pass it explicitly, including `None` (the unknown status the sibling
    excludes as `unknown-proxy-status`).
    """
    return types.SimpleNamespace(id=identifier, type=rtype, name=name, content=content,
                                 proxied=proxied)


def cname_rows():
    return [row()]


def address_rows(*, proxied=True):
    return [row("A", content="23.185.0.4", identifier="rec-a", proxied=proxied),
            row("AAAA", content="2620:12a:8000::4", identifier="rec-b", proxied=proxied)]


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


def test_verdict_already_applied_requires_every_records_proxy_status_to_match(apc):
    """SPEC 7.3 row 3a, adversarial review 2026-08-04 finding 3.  `record_key` is
    `(TYPE, name, content)` and carries no proxy state -- deliberately, because it must stay
    comparable against `delete_match`, whose items are `{type, name, content}` only -- so a
    DNS-only record whose ADDRESSES match used to classify `already-applied` and be reported to
    the operator, in the run record they attach to a change ticket, as "nothing to do".  A
    replacement created DNS-only is out of certificate service: an HTTPS outage plus origin-IP
    exposure, which is the migration's worst outcome, invisible to the applier's strongest
    instrument.

    The fixture varies deliberately (SPEC 22's named failure class): only the SECOND of the two
    records is DNS-only, so the detail must name the AAAA and must NOT name the A -- an
    implementation that flags the whole entry from the first record it looks at, or one that only
    ever checks `posts[0]`, cannot pass this.
    """
    verdict, detail = apc.verdict_for(plan_entry(), address_rows())
    assert verdict == "already-applied"
    assert detail == ""

    mixed = [row("A", content="23.185.0.4", identifier="rec-a", proxied=True),
             row("AAAA", content="2620:12a:8000::4", identifier="rec-b", proxied=False)]
    verdict, detail = apc.verdict_for(plan_entry(), mixed)
    assert verdict == "proxy-status-drift"
    assert "2620:12a:8000::4" in detail
    assert "23.185.0.4" not in detail
    assert "DNS-only" in detail


def test_verdict_proxy_status_drift_on_an_unknown_null_proxy_status(apc):
    """PD#3's nil shadow for the new comparison, and a real input shape: `proxied` is
    `Optional[bool]` on every SDK record model, and the sibling excludes an entry whose swept
    proxy status is null as `unknown-proxy-status` precisely because "guessing either way is
    unsafe".  Reading one back is the same problem -- a null must never pass for a match."""
    verdict, detail = apc.verdict_for(plan_entry(), address_rows(proxied=None))
    assert verdict == "proxy-status-drift"
    assert "has an UNKNOWN (null) proxy status where the file asks for proxied" in detail
    assert "DNS-only" not in detail   # an unknown status is not a claim that it is DNS-only


def test_verdict_proxy_status_drift_when_the_file_asks_for_dns_only(apc):
    """The symmetric direction: a revert file restoring a DNS-only CNAME must not accept a
    PROXIED record as already-applied either.  Without this, a one-way `if not held` test would
    look correct against every other test in this file, all of which ask for `proxied: True`."""
    entry = plan_entry()
    for post in entry["body"]["posts"]:
        post["proxied"] = False
    verdict, detail = apc.verdict_for(entry, address_rows(proxied=True))
    assert verdict == "proxy-status-drift"
    assert "is proxied where the file asks for DNS-only" in detail


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


def test_verdict_for_treats_a_different_name_as_records_missing_not_ready(apc):
    """B7 (final-batch review): `record_key`'s NAME component was unpinned --
    `test_record_key_ignores_case_and_a_trailing_dot` only compares two keys that stay EQUAL
    under `return (rtype, "", canonical)`, since blanking the name out entirely leaves both sides
    of that comparison identical too.  The demonstrated cross-name-write shape is now blocked
    EARLIER, by `check_record_list`'s own file-contract name check, so this is a lower-severity
    gap than when it was first found -- but `record_key`'s name component is still the guard that
    Cloudflare's RETURNED rows are compared at the right name, and `verdict_for` is what reads it.
    These rows carry a DIFFERENT host than the entry's own key; if `record_key` ignored `name`, R
    would equal D by type+content alone and this would wrongly classify `ready`."""
    entry = plan_entry()   # keyed a.umich.edu; delete_match also names a.umich.edu
    wrong_host_rows = [row("CNAME", name="other.umich.edu")]
    verdict, _detail = apc.verdict_for(entry, wrong_host_rows)
    assert verdict == "records-missing"


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
    # B10 (final-batch review): the error TEXT naming the FQDN and zone -- `f"cannot list DNS
    # records for {fqdn} in zone {zone_id}: ..."` -- was unpinned; only the exception CLASS was
    # asserted, so emptying the message down to just the api_error_text() tail left 164 passing.
    # An operator staring at a bare "InternalServerError: HTTP 500" with no FQDN or zone has no
    # way to know which of 217 entries pass 1 was reading when it failed.
    with pytest.raises(apc.CloudflareReadError, match=r"a\.umich\.edu.*zone-a"):
        apc.records_at_name(client, "zone-a", "a.umich.edu")


def test_validate_entries_resolves_the_delete_ids_for_a_ready_entry(apc):
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})
    result = apc.validate_entries(client, {"a.umich.edu": plan_entry()}, verbose=False)
    assert result["a.umich.edu"].verdict == "ready"
    assert result["a.umich.edu"].delete_ids == ["rec-1"]


def test_validate_entries_reads_the_entrys_own_zone(apc):
    """I4 (whole-branch review): `FakeCloudflareClient` keys `rows_by_name` purely on NAME, so
    neither read call was ever proven to use the entry's own `zone_id` -- mutating
    `validate_entries`'s `records_at_name(client, entry["zone_id"], fqdn)` call to
    `records_at_name(client, "WRONG", fqdn)` left the whole suite green.  A distinct zone_id
    (not the "zone-a" every other fixture in this file shares) plus asserting the RECORDED call
    is what catches it."""
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})
    entry = plan_entry(zone_id="zone-distinct")
    apc.validate_entries(client, {"a.umich.edu": entry}, verbose=False)
    assert client.list_calls[0]["zone_id"] == "zone-distinct"


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
    assert counts == {"applied": 1, "already-applied": 0, "planned": 0, "failed": 0,
                      "unverified": 0, "unknown": 0, "not-attempted": 0}


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


def test_summary_prints_the_source_and_record_lines_by_name(apc):
    """B10 (final-batch review): the summary's `source: <path>` line (the only pointer to WHICH
    file this run read) and its `record: <path>` line (the only pointer to the audit artifact,
    SPEC 12.1) were both deletable with the whole suite green -- no existing test asserted either
    literal label, only that the source's OWN `generated.at` timestamp appeared somewhere in the
    block (the test directly above)."""
    lines = apc.summary_lines(
        direction="plan", source="platform-domains-cloudflare-plan.json",
        source_generated_at="2026-08-01T00:22:23Z", for_real=False,
        entries_in_file=1, selected=1, counts=apc.tally({"a": "planned"}),
        record_path="platform-domains-cloudflare-plan-run-20260803T142211Z.json")
    text = "\n".join(lines)
    assert "source: platform-domains-cloudflare-plan.json" in text
    assert "record: platform-domains-cloudflare-plan-run-20260803T142211Z.json" in text


# ---------------------------------------------------------------------------------------------
# Task 7: pass 2 (the report) and the dry run end to end (SPEC R3.3, R2.6, section 11).
# ---------------------------------------------------------------------------------------------


def test_merge_body_puts_deletes_beside_the_files_posts_unchanged(apc):
    entry = plan_entry()
    body = apc.merge_body(entry, ["rec-1"])
    assert body["deletes"] == [{"id": "rec-1"}]
    assert body["posts"] == entry["body"]["posts"]
    assert set(body) == {"deletes", "posts"}


def test_merge_body_includes_every_delete_id_not_just_the_first(apc):
    """Adversarial review finding 2: mutating merge_body to `[{"id": delete_ids[0]}]` (dropping
    every id past the first) left the WHOLE suite green, because every existing merge_body/
    apply_entry test in this file passed a single-id list -- a "delete only the first id" defect
    was structurally invisible.  On the EMERGENCY ROLLBACK path (a revert, where D is the A+AAAA
    pair), dropping the second id would leave one address record standing beside the restored
    CNAME -- exactly the partial write section 3 exists to prevent.  Two DISTINCT ids, so a
    transposition or an early-exit mutation fails too, not just a first-only one."""
    entry = plan_entry()
    body = apc.merge_body(entry, ["rec-a", "rec-b"])
    assert body["deletes"] == [{"id": "rec-a"}, {"id": "rec-b"}]


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


def test_describe_change_renders_dns_only_flags_correctly(apc):
    """B8 (final-batch review): every EXISTING describe_change/dry-run fixture in this file uses
    `proxied: True, ttl: 1` uniformly -- `flags = "proxied"` and the `ttl 1)` literal both
    survive with the whole suite green if hardcoded, and CLAUDE.md records 5 of 218 real records
    as DNS-only.  Intersects A4: uses a UNIFORM `proxied=False, ttl=300` entry (every post agrees
    -- not a disagreement, which A4's InvariantError now refuses), so this pins
    `describe_change`'s actual DNS-only rendering path rather than A4's guard."""
    entry = plan_entry()
    for post in entry["body"]["posts"]:
        post["proxied"] = False
        post["ttl"] = 300
    line = apc.describe_change("a.umich.edu", entry)
    assert "(DNS-only, ttl 300)" in line


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


def test_describe_change_raises_invariant_error_when_posts_disagree_on_proxied_or_ttl(apc):
    """A4 (final-batch review): `describe_change` read `proxied`/`ttl` from `posts[0]` ONLY, so an
    entry whose posts genuinely differ in those fields was misreported on the dry run's only
    change line -- the operator's authorization artifact (SPEC 11.4).  0 of 217 real entries are
    affected today (CLAUDE.md), so this converts the silent misreport into a loud, named defect
    (PD#1/PD#2) rather than redesigning SPEC 11.4's single-flags-block line format -- the option
    this task's brief calls out as the alternative to per-group rendering.  Chosen over rendering
    per group because SPEC 11.4's own example line pins ONE trailing `(flags, ttl N)` block, and
    every existing format-pinning test in this file (grouping, revert-direction rendering) already
    depends on that shape; rendering flags per group would need to change all of them for a
    disagreement that, measured, has never actually occurred."""
    entry = plan_entry(addresses=("23.185.0.4", "2620:12a:8000::4"))
    entry["body"]["posts"][1]["proxied"] = False   # first post proxied, second is not
    with pytest.raises(apc.InvariantError, match="disagree"):
        apc.describe_change("a.umich.edu", entry)

    entry2 = plan_entry(addresses=("23.185.0.4", "2620:12a:8000::4"))
    entry2["body"]["posts"][1]["ttl"] = 300   # first post ttl 1, second ttl 300
    with pytest.raises(apc.InvariantError, match="disagree"):
        apc.describe_change("a.umich.edu", entry2)


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


def test_a_for_real_revert_deletes_both_resolved_ids_and_posts_the_cname(
        apc, tmp_path, monkeypatch):
    """Adversarial review finding 2: no --for-real apply anywhere in this file exercised the
    EMERGENCY ROLLBACK direction (D = the A/AAAA pair, P = the single CNAME) with more than one
    delete id -- every apply_entry/merge_body test used a single-id ["rec-1"] list, so a "delete
    only the first id" defect on the revert path (the path an operator reaches MID-INCIDENT) was
    invisible.  The two delete ids here (`rec-a`, `rec-b`, from address_rows()) are DISTINCT, so a
    transposition or an early-loop-exit mutation fails this test too, not just a first-only one.
    Asserts the FULL client.batch_calls entry, both ids included, not just a count or a subset."""
    entry = plan_entry()
    entry["delete_match"], entry["body"]["posts"] = (
        [{"type": "A", "name": "a.umich.edu", "content": "23.185.0.4"},
         {"type": "AAAA", "name": "a.umich.edu", "content": "2620:12a:8000::4"}],
        [{"type": "CNAME", "name": "a.umich.edu",
          "content": "live-umich-x.pantheonsite.io", "proxied": True, "ttl": 1}])
    doc = plan_doc(entries={"a.umich.edu": entry}, direction="revert")
    path = write_doc(tmp_path, doc, name="platform-domains-cloudflare-revert.json")
    # address_rows() gives the A/AAAA pair (D) with DISTINCT ids "rec-a"/"rec-b"; the verification
    # read (after the batch call) must find exactly the posted CNAME (P), matching cname_rows().
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [address_rows(), cname_rows()]})
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    assert code == 0
    assert client.batch_calls == [{
        "zone_id": "zone-a",
        "deletes": [{"id": "rec-a"}, {"id": "rec-b"}],
        "posts": entry["body"]["posts"],
    }]


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
    # I6 (whole-branch review): SPEC 11.2's validation-failure abort line -- the sentence telling
    # an operator a destructive run was refused AND that nothing changed -- was deletable with
    # the whole suite green.
    assert "1 of 1 selected entries did not match" in captured.err
    assert "NOTHING was changed" in captured.err


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


def test_a_dry_run_over_a_mixed_already_applied_and_ready_doc_reports_both_correctly(
        apc, tmp_path, monkeypatch, capsys):
    """B5 (final-batch review): every EXISTING already-applied test in this file uses
    --for-real; a dry run over an already-applied entry was untested.  A mutation making the
    dry-run outcome comprehension in `run_once` (`{fqdn: ("already-applied" if v.verdict ==
    "already-applied" else "planned") for fqdn, v in validations.items()}`) unconditionally
    `"planned"` left 164 passing: under that mutation the dry run reports `planned 2` and exits 0
    where a --for-real run over the SAME file exits 1, while `report_entries` (pass 2, identical
    in both modes, SPEC R3.3) still prints "already applied -- nothing to do" for the `a` entry --
    the report and the tally disagreeing inside the SAME run, breaking "a dry run is a rehearsal
    of the real run" and the run record SPEC 12.1 says an operator attaches to a change ticket."""
    doc = plan_doc(entries={"a.umich.edu": plan_entry(fqdn="a.umich.edu"),
                            "b.umich.edu": plan_entry(fqdn="b.umich.edu")})
    path = write_doc(tmp_path, doc)
    client = FakeCloudflareClient(rows_by_name={
        "a.umich.edu": [address_rows()],   # already-applied: R == P
        "b.umich.edu": [[row("CNAME", name="b.umich.edu")]],   # ready: R == D
    })
    code = run_main(apc, [path], tmp_path, client, monkeypatch)
    out = capsys.readouterr().out
    assert code == 1
    assert ("applied 0   already applied 1   planned 1   failed 0   unverified 0   unknown 0   "
            "not attempted 0") in out
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    assert record["entries"]["a.umich.edu"]["outcome"] == "already-applied"
    assert record["entries"]["b.umich.edu"]["outcome"] == "planned"


def test_a_file_whose_posts_disagree_is_refused_before_any_cloudflare_call(
        apc, tmp_path, monkeypatch, capsys):
    """The other half of adversarial review finding 11: the PLACEMENT, not just the class.  The
    old guard fired from `report_entries` -- pass 2 -- so a file that could be rejected in
    milliseconds first cost a full read-only validation pass against live Cloudflare.  Asserted
    against the fake client's recorded LIST calls, not inferred from the exit code."""
    entry = plan_entry(addresses=("23.185.0.4", "2620:12a:8000::4"))
    entry["body"]["posts"][1]["proxied"] = False
    path = write_doc(tmp_path, plan_doc(entries={"a.umich.edu": entry}))
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})
    code = run_main(apc, [path], tmp_path, client, monkeypatch)
    assert code == 2
    assert client.list_calls == []
    assert "disagree" in capsys.readouterr().err


def test_a_partial_sweep_file_is_reported_on_stderr_and_in_the_run_record(
        apc, tmp_path, monkeypatch, capsys):
    """Adversarial review 2026-08-04, finding 5, end to end.  A plan built with
    `find-platform-domains-cloudflare -o /tmp/one-zone engin.umich.edu` and applied a week later
    used to run with no signal at all: the generating run's own ATTENTION scrolled away, and the
    machine-readable evidence survived in the file the applier then dropped.

    It WARNS, it does not refuse -- the single-zone workflow is one CLAUDE.md documents -- so the
    run still completes (exit 0 here), and the numbers land in the run record, which SPEC R9.2
    calls "the thing an operator can attach to a change ticket"."""
    path = write_doc(tmp_path, plan_doc(generated={"zones_swept": 1, "zones_total": 187}))
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})
    code = run_main(apc, [path], tmp_path, client, monkeypatch)
    captured = capsys.readouterr()
    assert code == 0
    assert "ATTENTION: this file was generated from a PARTIAL sweep (1 of 187 zones)" in captured.err
    assert "ATTENTION" not in captured.out
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    assert record["run"]["source_zones_swept"] == 1
    assert record["run"]["source_zones_total"] == 187


def test_a_complete_sweep_still_records_its_coverage(apc, tmp_path, monkeypatch, capsys):
    """The other half of finding 5: the numbers are recorded on EVERY run, not only the alarming
    one -- a run record that carried them only when they differed could not be audited for the
    case it is meant to prove.  A one-fixture version of the test above cannot tell an
    always-1-of-187 bug from a correct read, which is SPEC 22's named fixture failure class."""
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})
    run_main(apc, [path], tmp_path, client, monkeypatch)
    assert "PARTIAL sweep" not in capsys.readouterr().err
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    assert record["run"]["source_zones_swept"] == 187
    assert record["run"]["source_zones_total"] == 187


def test_a_stale_plan_is_reported_on_stderr_before_any_cloudflare_call(
        apc, tmp_path, monkeypatch, capsys):
    """Finding 10, end to end.  plan_doc()'s own header is 62 hours older than run_main's frozen
    clock, so this is the ordinary shape, not a contrived one.  Printed to stderr, which SPEC 11.1
    reserves for "problems reach a watching operator", rather than buried in the summary block
    that prints AFTER a 217-line report on a run the operator has already committed to."""
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})
    run_main(apc, [path], tmp_path, client, monkeypatch)
    captured = capsys.readouterr()
    assert "ATTENTION: this file was generated 62 hours ago (2026-08-01T00:22:23Z)" in captured.err
    assert "regenerate the baseline" in captured.err
    assert "ATTENTION" not in captured.out


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


def test_a_mixed_ready_and_invalid_file_aborts_before_any_write(
        apc, tmp_path, monkeypatch, capsys):
    """CRITICAL 3 (whole-branch review): every OTHER invalid-entry fixture in this file is either
    a single entry (test_an_invalid_entry_aborts_the_run_at_exit_two_with_nothing_applied) or ALL
    invalid (test_every_invalid_entry_is_named_on_stderr_never_v_gated) -- so a mutation that
    narrows `run_once`'s gate from "abort when ANY selected entry is invalid" to "abort only when
    EVERY selected entry is invalid" left the whole 164-test suite green:

        if abort_on_invalid_entries(validations) and not any(
                v.verdict == "ready" for v in validations.values()):
            return 2

    Under that mutation, a file mixing a `ready` entry with an invalid one no longer returns 2 --
    it falls through into `report_entries`/`apply_all`, which DOES apply the ready entry before
    `apply_all`'s own `InvariantError` back-stop trips on the invalid one two entries later.  That
    back-stop is real cover for an invalid-FIRST fixture, which is exactly why one is not enough:
    the reviewer measured that an invalid-first fixture survives the SAME mutation (apply_all's
    sorted loop reaches the invalid entry before ever calling batch(), so `changed_count` is still
    0 and the mutated code still happens to return 2) -- proving nothing.  Alphabetical order
    ("a" < "b" < "c") is what makes the READY entry sort first here, by construction rather than
    by luck, so this test can only pass if the ORIGINAL "any invalid" gate is the one running.
    """
    doc = plan_doc(entries={
        "a.umich.edu": plan_entry(fqdn="a.umich.edu"),   # sorts FIRST, and is READY
        "b.umich.edu": plan_entry(fqdn="b.umich.edu"),   # invalid: records-missing
        "c.umich.edu": plan_entry(fqdn="c.umich.edu"),   # invalid: records-missing
    })
    path = write_doc(tmp_path, doc)
    client = FakeCloudflareClient(rows_by_name={
        "a.umich.edu": [cname_rows()],
        "b.umich.edu": [[]],
        "c.umich.edu": [[]],
    })
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    captured = capsys.readouterr()
    assert code == 2
    assert client.batch_calls == []
    assert "b.umich.edu" in captured.err
    assert "c.umich.edu" in captured.err
    assert "records-missing" in captured.err


class RaiseOnceStream:
    """A stderr stand-in whose FIRST write raises OSError -- simulating one of SPEC 11.2's
    UNGUARDED stderr prints (the subset-coverage ATTENTION line here) landing on a doomed
    descriptor -- and every later write succeeds and is recorded.  `report_line`'s own retry is
    what this test needs to observe, and `capsys` cannot see a stream the test replaced outright.
    `fileno()` raises `io.UnsupportedOperation`, one of the three exceptions `point_at_devnull`
    suppresses, so its own best-effort detach attempt is a harmless no-op here, matching a real
    doomed stream that also has no usable fd to redirect.
    """

    def __init__(self):
        self.calls = 0
        self.written = []

    def write(self, text):
        self.calls += 1
        if self.calls == 1:
            raise OSError("simulated write failure")
        self.written.append(text)
        return len(text)

    def flush(self):
        pass

    def fileno(self):
        raise io.UnsupportedOperation("no real fd")


def test_a_doomed_first_attention_write_no_longer_silences_every_later_one(
        apc, tmp_path, monkeypatch):
    """Final-batch review, A2: both ATTENTION lines (the per-entry one here, and the --only
    subset-coverage one) now go through `report_line`, which SWALLOWS an OSError internally
    (SPEC 11.1) rather than letting it propagate.  BEFORE this fix, both were bare `print(...,
    file=sys.stderr)` calls: a doomed stderr made the FIRST ATTENTION line raise, which escaped
    `abort_on_invalid_entries`'s loop entirely -- so NONE of the invalid entries got named (not
    even the second), and the run's validation-abort path was silently replaced by a generic
    `except OSError` abort with an incomplete report.  `--only`ing both invalid entries makes the
    subset-coverage line the doomed FIRST write; the second entry's own ATTENTION line is what
    proves the loop kept going past the first failure rather than dying on it.
    """
    entries = {"a.umich.edu": plan_entry(), "b.umich.edu": plan_entry(fqdn="b.umich.edu"),
              "c.umich.edu": plan_entry(fqdn="c.umich.edu")}
    path = write_doc(tmp_path, plan_doc(entries=entries))
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [[]], "b.umich.edu": [[]]})
    stream = RaiseOnceStream()
    monkeypatch.setattr(apc.sys, "stderr", stream)
    code = run_main(apc, ["--only", "a.umich.edu", "--only", "b.umich.edu", path], tmp_path,
                    client, monkeypatch)
    assert code == 2
    # The doomed FIRST write (the subset-coverage line) is lost, but BOTH invalid entries' own
    # ATTENTION lines -- writes 2 and 3 on the same stream -- still made it through.
    assert any("a.umich.edu" in text and "records-missing" in text for text in stream.written)
    assert any("b.umich.edu" in text and "records-missing" in text for text in stream.written)


def test_a_bare_oserror_mid_run_still_uses_failure_code(apc, tmp_path, monkeypatch, capsys):
    """Final-batch review, A2 aftermath: routing both ATTENTION lines through `report_line`
    removes the last UNGUARDED stderr write in this script, so main()'s bare `except OSError`
    clause (SPEC 9.1) has no remaining live trigger through ordinary I/O today -- a consequence
    of the A2 fix reported separately (out of this review pass's scope), not fixed here.  This
    keeps the CLAUSE ITSELF under test -- its own `report_line` + `failure_code(state)` handling
    -- for whatever future OSError source reaches it, by injecting one directly into
    `select_entries` (an arbitrary point inside `run_once`'s try)."""
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})

    def raise_oserror(entries, only):
        raise OSError("simulated mid-run I/O failure")

    monkeypatch.setattr(apc, "select_entries", raise_oserror)
    code = run_main(apc, [path], tmp_path, client, monkeypatch)
    assert code == 2   # nothing changed yet -- failure_code(state) with changed_count == 0
    assert "ERROR: simulated mid-run I/O failure" in capsys.readouterr().err
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    assert record["run"]["exit_code"] == 2


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


# ---------------------------------------------------------------------------------------------
# Task 8: pass 3 -- apply, verify, and stop at the first failure (SPEC R5, R6, 8.1, 9.1, 9.3/9.4).
# ---------------------------------------------------------------------------------------------


_STATUS_ERROR_CLASSES = {
    400: cloudflare.BadRequestError,
    401: cloudflare.AuthenticationError,
    403: cloudflare.PermissionDeniedError,
    404: cloudflare.NotFoundError,
    409: cloudflare.ConflictError,
    422: cloudflare.UnprocessableEntityError,
    429: cloudflare.RateLimitError,
    500: cloudflare.InternalServerError,
}


def cloudflare_error(status_code, code, message):
    """A REAL cloudflare SDK exception for one error entry (SPEC 9.1), built via
    `api_status_error`.

    The task brief sketches a `cloudflare_error()` helper as a `types.SimpleNamespace` with its
    `__class__` reassigned -- the exact defect class `api_status_error`'s own docstring above
    already rejects (SimpleNamespace is not a CPython heap type, so the reassignment raises
    TypeError on construction; `test_records_at_name_names_a_cloudflare_read_failure` records the
    same substitution for an earlier task).  This maps `status_code` to the SAME exception class
    `Cloudflare._make_status_error` picks (verified against cloudflare 5.4.0), so a test built
    through this helper exercises the identical exception class the SDK would actually raise.
    """
    error_cls = _STATUS_ERROR_CLASSES.get(status_code, cloudflare.APIStatusError)
    return api_status_error(error_cls, status_code,
                            {"errors": [{"code": code, "message": message}]})


def test_verify_records_accepts_exactly_the_posts(apc):
    assert apc.verify_records(plan_entry(), address_rows()) is True


def test_verify_records_ignores_an_unrelated_txt_record_at_the_name(apc):
    """Adversarial review finding 3: mutating verify_records' `have = {record_key(...) for r in
    rows}` (dropping the governed_records() filter that scopes it to CNAME/A/AAAA) left the whole
    suite green, because no verify_records fixture in this file ever carried a non-governed
    record.  An apex CNAME/A record with an SPF (TXT) record beside it is an ORDINARY shape -- a
    site's SPF record must not be able to make a HEALTHY apply look unverified (SPEC R1.1's
    governed-type rule applies here exactly as it does to verdict_for's own TXT test above)."""
    rows = [*address_rows(), row("TXT", content="v=spf1 -all", identifier="rec-t")]
    assert apc.verify_records(plan_entry(), rows) is True


def test_verify_records_rejects_a_leftover_record(apc):
    rows = [*address_rows(), row(identifier="rec-leftover")]
    assert apc.verify_records(plan_entry(), rows) is False


@pytest.mark.parametrize("held", [False, None])
def test_verify_records_rejects_a_replacement_in_the_wrong_proxy_status(apc, held):
    """R6.1, adversarial review 2026-08-04 finding 3.  R6.1 is justified by PD#14 -- "a 200 from
    the batch endpoint is Cloudflare's CLAIM that the swap happened; the record list is the
    EVIDENCE" -- but the evidence collected was `(TYPE, name, content)` only, so a batch that
    created the records DNS-only verified True and was reported `applied`, exit 0.  `None` (the
    SDK's unknown proxy status) must fail the same way: an unconfirmed state is not a confirmed
    one."""
    assert apc.verify_records(plan_entry(), address_rows(proxied=held)) is False


def test_verify_records_rejects_a_proxied_record_where_the_file_asks_for_dns_only(apc):
    """The symmetric direction, for the same reason the verdict has one."""
    entry = plan_entry()
    for post in entry["body"]["posts"]:
        post["proxied"] = False
    assert apc.verify_records(entry, address_rows(proxied=True)) is False


def test_apply_entry_calls_batch_with_the_resolved_ids_and_the_files_posts(apc):
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [address_rows()]})
    entry = plan_entry()
    created = apc.apply_entry(client, "a.umich.edu", entry, ["rec-1"])
    assert client.batch_calls == [{"zone_id": "zone-a", "deletes": [{"id": "rec-1"}],
                                   "posts": entry["body"]["posts"]}]
    assert sorted(created) == ["rec-a", "rec-b"]


def test_apply_entry_verifies_against_the_entrys_own_zone(apc):
    """I4 (whole-branch review): the R6.1 post-apply verification read -- the ONE instrument
    between "Cloudflare claimed 200" and "the records really changed" -- was never proven to use
    the entry's own zone either.  Mutating apply_entry's verification `client.dns.records.list
    (zone_id=entry["zone_id"], ...)` call to `zone_id="WRONG"` left the whole suite green.  A
    distinct zone_id plus asserting the recorded verification call is what catches it."""
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [address_rows()]})
    entry = plan_entry(zone_id="zone-distinct")
    apc.apply_entry(client, "a.umich.edu", entry, ["rec-1"])
    # list_calls[0] is validate_entries' job in a real run; called directly here, index 0 IS the
    # post-apply verification read (apply_entry never calls records_at_name itself).
    assert client.list_calls[0]["zone_id"] == "zone-distinct"


def test_apply_entry_retries_verification_once_before_failing(apc, monkeypatch):
    """SPEC R6.2.  Cloudflare's own batch docs warn that "the propagation of changes is not
    atomic", so an immediate re-read can legitimately lag."""
    slept = []
    monkeypatch.setattr(apc, "sleep", slept.append)
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [[], address_rows()]})
    created = apc.apply_entry(client, "a.umich.edu", plan_entry(), ["rec-1"])
    assert slept == [apc.VERIFY_RETRY_SLEEP]
    assert sorted(created) == ["rec-a", "rec-b"]


def test_apply_entry_raises_verify_error_when_verification_never_matches(apc, monkeypatch):
    """SPEC R6.3: a surviving mismatch is `VerifyError` (`unverified`), never plain `ApplyError`
    (`failed`) -- the batch call already returned, so Cloudflare committed SOMETHING.

    Minor 5 (Task 8 review): R6.2 pins the re-list at ONE retry, so exactly TWO `list()` calls
    total -- the initial read plus the one retry.  `for attempt in (1, 2)` -> `(1, 2, 3)` left the
    suite green before this asserted the call COUNT (the sleep-count alone does not distinguish
    the two: this code sleeps only after the FIRST failed attempt regardless of how many follow),
    and a second retry would make the raised message's "twice VERIFY_RETRY_SLEEPs apart" false.
    """
    slept = []
    monkeypatch.setattr(apc, "sleep", slept.append)
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [[]]})
    with pytest.raises(apc.VerifyError, match=r"a\.umich\.edu"):
        apc.apply_entry(client, "a.umich.edu", plan_entry(), ["rec-1"])
    assert slept == [apc.VERIFY_RETRY_SLEEP]
    assert len(client.list_calls) == 2  # SPEC R6.2: re-list ONCE, not twice


def test_apply_entry_names_what_cloudflare_actually_holds_when_nothing_governed_is_there(
        apc, monkeypatch):
    """Minor 8 (Task 8 review): the surviving-mismatch message truncated to "...it now holds "
    on the COMMONEST shape (nothing governed at the name) -- `verdict_for` already guards this
    with `describe_keys(...) or 'no CNAME/A/AAAA record'`; `apply_entry` did not."""
    monkeypatch.setattr(apc, "sleep", lambda seconds: None)
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [[]]})
    with pytest.raises(apc.VerifyError, match="it now holds no CNAME/A/AAAA record"):
        apc.apply_entry(client, "a.umich.edu", plan_entry(), ["rec-1"])


def test_apply_entry_raises_verify_error_when_the_verification_read_itself_fails(apc):
    """SPEC R6.3's second trigger: the batch call already succeeded, so a failing verification
    READ is `VerifyError` (`unverified`) too, never plain `ApplyError` (`failed`)."""
    error = api_status_error(cloudflare.InternalServerError, 500,
                             {"errors": [{"code": 1000, "message": "boom"}]})
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [address_rows()]},
                                  list_error=error)
    with pytest.raises(apc.VerifyError, match="verification read failed"):
        apc.apply_entry(client, "a.umich.edu", plan_entry(), ["rec-1"])


@pytest.mark.parametrize("error_factory", [
    lambda: TimeoutError("verification read timed out"),
    lambda: OSError("verification read timed out"),
])
def test_apply_entry_raises_verify_error_when_the_verification_read_raises_a_bare_transport_error(
        apc, error_factory):
    """SPEC R6.3, amended after the adversarial review (finding 1): the batch call already
    RETURNED 200 -- so Cloudflare committed something -- and only `cloudflare.CloudflareError` was
    caught at the verification read.  A bare `TimeoutError`/`OSError` (not wrapped in the SDK's own
    exception hierarchy) escaped `apply_entry` entirely and was left for `apply_all`'s unknown-fate
    clause, which is listed for a DIFFERENT reason (the BATCH call's own dropped-connection
    shadow) -- asserting the call "did not complete" for a write that, in fact, already had.  This
    must be `VerifyError`/`unverified`, exactly like the `cloudflare.CloudflareError` case just
    above."""
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [address_rows()]},
                                  list_error=error_factory())
    with pytest.raises(apc.VerifyError, match="verification read failed"):
        apc.apply_entry(client, "a.umich.edu", plan_entry(), ["rec-1"])


def test_apply_entry_raises_apply_error_not_verify_error_on_a_batch_rejection(apc):
    """A REJECTED batch call means nothing committed for this entry (SPEC 8.1's `failed` row) --
    the exact TYPE (not merely `isinstance(..., ApplyError)`, which `VerifyError` would also
    satisfy) is what `apply_all`'s except-clause ordering actually depends on to keep `failed` and
    `unverified` apart."""
    client = FakeCloudflareClient(batch_error=cloudflare_error(400, 81058, "already exists"))
    with pytest.raises(apc.ApplyError, match="81058") as excinfo:
        apc.apply_entry(client, "a.umich.edu", plan_entry(), ["rec-1"])
    assert type(excinfo.value) is apc.ApplyError


@pytest.mark.parametrize("status", [429, 500])
def test_apply_entry_sends_the_batch_post_exactly_once_on_a_retryable_status(
        apc, monkeypatch, status):
    """CRITICAL 1 (whole-branch review): `FakeCloudflareClient` sits ABOVE HTTP and structurally
    cannot see the SDK's own retry loop -- every other `apply_entry` test in this file uses it and
    none of them can catch this.  cloudflare 5.4.0's `BaseClient._should_retry` has NO HTTP-method
    check, so it retries 429/5xx for a POST exactly as for a GET, and the default `max_retries=2`
    would silently RE-SEND `dns_records/batch` -- a call that is not idempotent (SPEC R5.4: one
    transaction, Deletes then Posts).  A first attempt that committed and a retry that lands on
    the now-changed state is exactly the shape that made a real two-entry live run report `EXIT:
    2` ("nothing was changed") after Cloudflare actually rejected a SECOND, self-inflicted
    duplicate-create.

    A REAL `Cloudflare` client over `httpx.MockTransport`, built through `build_client` (the seam
    this fix lives in), not `FakeCloudflareClient`.  `httpx.Client.send` is restored to the TRUE
    implementation for this test only (captured at import time, before `refuse_real_network`
    patches it) -- a `MockTransport` never opens a real socket, so this does not weaken that
    guard, it is the one place this file's real-client seam needs its actual request path to run;
    see the module-level comment by `REAL_HTTPX_CLIENT_SEND`.
    """
    monkeypatch.setattr(httpx.Client, "send", REAL_HTTPX_CLIENT_SEND)
    calls = []

    def handler(request):
        calls.append((request.method, str(request.url)))
        return httpx.Response(status, json={"errors": [{"code": 1000, "message": "boom"}]})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = apc.build_client(api_token="tok-123", http_client=http_client)
    with pytest.raises(apc.ApplyError):
        apc.apply_entry(client, "a.umich.edu", plan_entry(), ["rec-1"])

    posts = [call for call in calls if call[0] == "POST"]
    assert posts == [("POST", f"{apc.API_BASE_URL}/zones/zone-a/dns_records/batch")], (
        f"expected exactly ONE POST, the SDK sent {len(posts)}: {posts}")


def three_entry_doc():
    """Task 8 re-review, Important 2: each entry carries a DISTINCT `zone_id`
    ("zone-a"/"zone-b"/"zone-c") rather than the three sharing "zone-a" -- Critical 1's fix closed
    the class for `deletes` (distinct ids in `three_entry_rows`) but left it open for `zone_id`:
    a full `batch_calls ==` assertion built from entries that all share one zone cannot tell "this
    entry's zone" from "any entry's zone", and a wrong `zone_id` also silently steers the
    post-apply verification read at a DIFFERENT zone than the one just written to."""
    return plan_doc(entries={
        "a.umich.edu": plan_entry(zone_id="zone-a", fqdn="a.umich.edu"),
        "b.umich.edu": plan_entry(zone_id="zone-b", fqdn="b.umich.edu"),
        "c.umich.edu": plan_entry(zone_id="zone-c", fqdn="c.umich.edu"),
    })


def three_entry_rows(applied=()):
    """Pass-1 rows for three FQDNs; those in `applied` are already swapped.

    Each entry's CNAME (or, once applied, A/AAAA) row carries an id DERIVED FROM ITS OWN FQDN
    ("rec-a-cname" for a.umich.edu, "rec-b-a"/"rec-b-aaaa" for an applied b.umich.edu, ...)
    rather than the row() defaults ("rec-1"/"rec-a"/"rec-b") every FQDN shared before.  Critical 1
    (Task 8 review): with every entry resolving the SAME delete id, `apply_all` could hand
    `apply_entry` a wrong -- even a hardcoded literal -- id and the whole suite stayed green,
    because nothing distinguished "the id THIS entry resolved" from "the id ANY entry resolved".

    The `applied` branch re-ids `address_rows()` rather than hardcoding "23.185.0.4"/
    "2620:12a:8000::4" a second time (Task 8 re-review, minor 7): `plan_entry()`'s own posts come
    from that SAME default, and a hand-maintained second copy of those two literals would silently
    stop meaning "already applied" the moment either drifted from the other -- the verdict compares
    against the entry's actual posts, not against this fixture's literals.
    """
    rows = {}
    for name in ("a.umich.edu", "b.umich.edu", "c.umich.edu"):
        letter = name[0]
        if name in applied:
            base = [row(r.type, name, r.content, f"rec-{letter}-{r.type.lower()}")
                   for r in address_rows()]
        else:
            base = [row("CNAME", name, "live-umich-x.pantheonsite.io", f"rec-{letter}-cname")]
        rows[name] = [base]
    return rows


def test_apply_all_processes_entries_in_sorted_key_order_not_insertion_order(
        apc, tmp_path, monkeypatch):
    """B9 (final-batch review): SPEC R3.4 says pass 3 applies entries in the file's own SORTED
    key order -- `apply_all` sorts `entries.items()` for exactly this reason.  Every fixture in
    this file happens to insert its `entries` dict in already-sorted order (three_entry_doc's
    a/b/c, plan_doc's single entry, ...), so `entries.items()` in place of
    `sorted(entries.items())` left the whole suite green.  This builds a doc whose `entries` dict
    is inserted c, a, b -- deliberately NOT sorted -- and stops at the first failure, so the
    resulting outcome set can only match SORTED processing (a applied, b failed, c not-attempted)
    or INSERTION-order processing (c applied, a failed, b not-attempted); the two are mutually
    exclusive, so this is not merely "a" test but the one shape that tells them apart."""
    doc = plan_doc(entries={
        "c.umich.edu": plan_entry(zone_id="zone-c", fqdn="c.umich.edu"),
        "a.umich.edu": plan_entry(zone_id="zone-a", fqdn="a.umich.edu"),
        "b.umich.edu": plan_entry(zone_id="zone-b", fqdn="b.umich.edu"),
    })
    path = write_doc(tmp_path, doc)

    class FailOnSecond(FakeCloudflareClient):
        def _batch(self, **kwargs):
            if len(self.batch_calls) == 1:
                self.batch_calls.append(kwargs)
                raise cloudflare_error(400, 81058, "already exists")
            return super()._batch(**kwargs)

    rows = three_entry_rows()
    for name in rows:
        rows[name] = [rows[name][0], [row(r.type, name, r.content, r.id)
                                      for r in address_rows()]]
    client = FailOnSecond(rows_by_name=rows)
    monkeypatch.setattr(apc, "sleep", lambda seconds: None)
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    assert code == 3
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    outcomes = {k: v["outcome"] for k, v in record["entries"].items()}
    assert outcomes == {"a.umich.edu": "applied", "b.umich.edu": "failed",
                        "c.umich.edu": "not-attempted"}


def test_a_failure_on_the_second_entry_leaves_the_third_not_attempted(
        apc, tmp_path, monkeypatch, capsys):
    """SPEC R3.4 and 8.1: stop immediately, revert nothing, attempt nothing further -- and exit 3
    because the FIRST entry did commit.

    Minor 10 (Task 8 review): `"applied 1" in out` also matches `already applied 1` -- harmless
    today only because this fixture's already-applied count happens to be 0.  Asserting the WHOLE
    counts line is what makes the check actually pin the shape rather than get lucky.

    Important 1 (Task 8 re-review): the `FAILED` result line was the ONE of SPEC 11.2's four
    result-line shapes with no cover at all -- `write_report(f"{fqdn}  FAILED -- {e}")` could be
    reduced to `write_report(f"{fqdn}  FAILED")`, or the whole `report_line(f"ERROR: {e}")` call
    deleted, with 135/135 still green, exactly the "a log recording that an entry failed and never
    why... is not an account of anything" gap `f6639ad`'s ruling exists to close.  The reason is
    asserted on BOTH streams here.  It appears ONCE, not twice, in the stdout line (minor 6: `str(e)`
    already begins "b.umich.edu: ...", and `apply_all` strips that redundant prefix before printing
    the result line -- see the `except ApplyError`/`except VerifyError` arms)."""
    path = write_doc(tmp_path, three_entry_doc())

    class FailOnSecond(FakeCloudflareClient):
        def _batch(self, **kwargs):
            if len(self.batch_calls) == 1:
                self.batch_calls.append(kwargs)
                raise cloudflare_error(400, 81058, "already exists")
            return super()._batch(**kwargs)

    rows = three_entry_rows()
    for name in rows:
        rows[name] = [rows[name][0], [row(r.type, name, r.content, r.id)
                                      for r in address_rows()]]
    client = FailOnSecond(rows_by_name=rows)
    monkeypatch.setattr(apc, "sleep", lambda seconds: None)
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    captured = capsys.readouterr()
    out, err = captured.out, captured.err
    assert code == 3
    assert ("applied 1   already applied 0   planned 0   failed 1   unverified 0   unknown 0   "
            "not attempted 1") in out
    assert len(client.batch_calls) == 2  # stop-at-first-failure: entry c never reached
    assert "b.umich.edu  FAILED -- batch call rejected:" in out
    assert "81058" in out
    assert "b.umich.edu  FAILED -- b.umich.edu:" not in out  # minor 6: no duplicated fqdn
    assert "ERROR: b.umich.edu:" in err
    assert "81058" in err
    # Important 4 (review round 1): the STDOUT lines above make this arm LOOK covered, but the
    # run record's own copy of the failure reason -- SPEC R9.2's "the thing an operator can attach
    # to a change ticket" -- was unpinned: dropping `"error": reason` from the failed/unverified/
    # unknown arms, or emptying `item["detail"]` in outcome_document, left 145 passing.
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    assert "81058" in record["entries"]["b.umich.edu"]["error"]
    # B6 (final-batch review): the assertion above only proves SOME text made it through -- four
    # mutations (dropping `deleted_ids` from the interrupt/unknown/unverified/failed arms, or
    # dropping the per-entry `at`) each left 164 passing, because nothing compared the WHOLE
    # per-entry dict the way the success-path byte-exact test already does.  `deleted_ids` on a
    # failed entry is exactly the list an operator needs to hand-repair a stopped rewrite.
    expected_error = "batch call rejected: " + apc.api_error_text(
        cloudflare_error(400, 81058, "already exists"))
    assert record["entries"]["b.umich.edu"] == {
        "outcome": "failed",
        "at": "2026-08-03T14:22:11Z",
        "error": expected_error,
        "deleted_ids": ["rec-b-cname"],
    }


def test_a_failure_on_the_first_entry_exits_two_because_nothing_committed(
        apc, tmp_path, monkeypatch):
    path = write_doc(tmp_path, three_entry_doc())
    client = FakeCloudflareClient(rows_by_name=three_entry_rows(),
                                  batch_error=cloudflare_error(400, 81058, "already exists"))
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    assert code == 2


@pytest.mark.parametrize("error_factory", [
    lambda: cloudflare.APIConnectionError(request=None),
    lambda: cloudflare.APITimeoutError(request=None),
    TimeoutError,
    OSError,
])
def test_every_unknown_fate_transport_error_makes_the_outcome_unknown_and_exits_three(
        apc, tmp_path, monkeypatch, capsys, error_factory):
    """SPEC 8.1: the call did not tell us whether Cloudflare committed it, so "nothing was
    changed" is a claim this run cannot make.

    Minor 6 (Task 8 review): only `cloudflare.APIConnectionError` had a test -- narrowing
    `apply_all`'s `except (cloudflare.APIConnectionError, TimeoutError, OSError)` tuple to drop
    either of the other two left the whole suite green.  `TimeoutError` IS an `OSError` subclass
    in the stdlib, so this also proves listing both is verified to be redundant rather than
    silently load-bearing -- either alone would still catch a raw `TimeoutError`."""
    path = write_doc(tmp_path, plan_doc())

    class Dropped(FakeCloudflareClient):
        def _batch(self, **kwargs):
            self.batch_calls.append(kwargs)
            raise error_factory()

    client = Dropped(rows_by_name={"a.umich.edu": [cname_rows()]})
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    out = capsys.readouterr().out
    assert code == 3
    assert "unknown 1" in out
    assert "a.umich.edu  UNKNOWN --" in out


def test_a_connection_error_makes_the_outcome_unknown_and_exits_three(
        apc, tmp_path, monkeypatch, capsys):
    """SPEC 8.1: the call did not tell us whether Cloudflare committed it, so "nothing was
    changed" is a claim this run cannot make.  Also asserts the reason reaches BOTH streams
    (SPEC 11.2, ruling f6639ad)."""
    path = write_doc(tmp_path, plan_doc())

    class Dropped(FakeCloudflareClient):
        def _batch(self, **kwargs):
            self.batch_calls.append(kwargs)
            raise cloudflare.APIConnectionError(request=None)

    client = Dropped(rows_by_name={"a.umich.edu": [cname_rows()]})
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    captured = capsys.readouterr()
    assert code == 3
    assert "unknown 1" in captured.out
    assert "a.umich.edu  UNKNOWN -- the call did not complete (APIConnectionError" in captured.out
    assert "ERROR: a.umich.edu:" in captured.err
    assert "UNKNOWN" in captured.err
    # B6 (final-batch review): the stdout/stderr assertions above only prove SOME text made it
    # through -- dropping `deleted_ids` (or the per-entry `at`) from this UNKNOWN arm's own
    # `details[fqdn] = {...}` left 164 passing, because nothing compared the run record's WHOLE
    # per-entry dict.  `deleted_ids` here is exactly the list an operator needs to hand-repair an
    # entry whose fate is genuinely unknown.
    error = cloudflare.APIConnectionError(request=None)
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    assert record["entries"]["a.umich.edu"] == {
        "outcome": "unknown",
        "at": "2026-08-03T14:22:11Z",
        "error": f"the call did not complete ({type(error).__name__}: {error})",
        "deleted_ids": ["rec-1"],
    }


def test_a_verify_mismatch_makes_the_outcome_unverified_and_exits_three(
        apc, tmp_path, monkeypatch, capsys):
    """Item A (Task 8 review): SPEC R6.3/8.1, amended after Task 8's review surfaced the
    contradiction -- a surviving verification mismatch means Cloudflare's batch call RETURNED
    (it committed), so the outcome is `unverified`, never `failed`, and `changed_count` must
    count it or `exit_code_for` reports exit 2 ("nothing was changed") about a write it cannot
    fully account for.  Also pins the result line's UNVERIFIED shape and the both-streams reason
    (SPEC 11.2, ruling f6639ad) -- the reason appears ONCE, not twice, on stdout (minor 6: `str(e)`
    already begins "a.umich.edu: ...", and `apply_all` strips that redundant prefix)."""
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows(), []]})
    monkeypatch.setattr(apc, "sleep", lambda seconds: None)
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    captured = capsys.readouterr()
    assert code == 3
    assert "unverified 1" in captured.out
    assert "a.umich.edu  UNVERIFIED -- the batch call succeeded but" in captured.out
    assert "a.umich.edu  UNVERIFIED -- a.umich.edu:" not in captured.out  # no duplicated fqdn
    assert "ERROR: a.umich.edu:" in captured.err
    # B6 (final-batch review): the stdout/stderr assertions above only prove SOME text made it
    # through -- dropping `deleted_ids` (or the per-entry `at`) from this UNVERIFIED arm's own
    # `details[fqdn] = {...}` left 164 passing.  `deleted_ids` here is exactly the list an
    # operator needs to hand-repair an entry Cloudflare committed but never confirmed.
    held = apc.describe_keys([]) or "no CNAME/A/AAAA record"
    expected_error = (
        "the batch call succeeded but Cloudflare does not hold the expected records "
        f"afterwards, twice {apc.VERIFY_RETRY_SLEEP}s apart; it now holds {held}")
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    assert record["entries"]["a.umich.edu"] == {
        "outcome": "unverified",
        "at": "2026-08-03T14:22:11Z",
        "error": expected_error,
        "deleted_ids": ["rec-1"],
    }


def test_a_batch_that_leaves_the_records_dns_only_is_unverified_never_applied(
        apc, tmp_path, monkeypatch, capsys):
    """Adversarial review 2026-08-04 finding 3, scenario (b), end to end: the batch returns, the
    verification read shows the right ADDRESSES in the wrong proxy status, and the run must not
    report `applied`/exit 0.  It is `unverified`/exit 3, because Cloudflare committed something
    and the something is not what the file asked for -- exactly the state R6.3 exists to name.

    The message must say WHY: "does not hold the expected records" would be false here (it holds
    exactly those records) and would send an operator hunting a content difference that is not
    there."""
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(
        rows_by_name={"a.umich.edu": [cname_rows(), address_rows(proxied=False)]})
    monkeypatch.setattr(apc, "sleep", lambda seconds: None)
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    captured = capsys.readouterr()
    assert code == 3
    assert "unverified 1" in captured.out
    assert "a.umich.edu  UNVERIFIED -- the batch call succeeded but" in captured.out
    assert "proxy status" in captured.out
    assert "DNS-only" in captured.out
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    assert record["entries"]["a.umich.edu"]["outcome"] == "unverified"


def test_a_rerun_over_an_unproxied_record_refuses_instead_of_reporting_already_applied(
        apc, tmp_path, monkeypatch, capsys):
    """Adversarial review 2026-08-04 finding 3, scenario (a), end to end.  Re-running the same
    plan file is the action R4.2's `already-applied` carve-out exists to make safe, and CLAUDE.md
    advertises as "safe, cheap, and call zero Cloudflare write endpoints".  If someone has since
    turned the orange cloud off, the honest answer is to REFUSE -- the whole file, per section 3's
    all-or-nothing property -- not to tell the operator, and the run record they attach to the
    change ticket, that the state is already correct.

    Zero batch calls asserted against the fake client's record, and exit 2 ("nothing was
    changed") is therefore true of this run."""
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [address_rows(proxied=False)]})
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    captured = capsys.readouterr()
    assert code == 2
    assert client.batch_calls == []
    assert "already applied -- nothing to do" not in captured.out
    assert "ATTENTION: a.umich.edu proxy-status-drift" in captured.err
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    assert record["entries"]["a.umich.edu"]["verdict"] == "proxy-status-drift"


def test_a_bare_transport_error_on_the_verification_read_is_unverified_not_unknown(
        apc, tmp_path, monkeypatch, capsys):
    """SPEC R6.3's amendment, end to end (adversarial review finding 1).  Measured on HEAD before
    this fix: the batch call RETURNED 200 (Cloudflare committed), the verification read then
    raised a bare TimeoutError, and the run reported `a.umich.edu  UNKNOWN -- the call did not
    complete (TimeoutError: ...)` with `unknown 1`/exit 3 -- asserting the write's fate was
    unknown when it was not: it had already committed, only OUR confirmation of it failed.  This
    pins both the outcome word AND that the UNKNOWN line/count never appear."""
    path = write_doc(tmp_path, plan_doc())

    class VerifyReadTimesOut(FakeCloudflareClient):
        def _list(self, **kwargs):
            if len(self.list_calls) == 1:   # the SECOND list() call -- pass 1's own read (the
                # first) must succeed normally; only the POST-BATCH verification read fails.
                self.list_calls.append(kwargs)
                raise TimeoutError("verification read timed out")
            return super()._list(**kwargs)

    client = VerifyReadTimesOut(rows_by_name={"a.umich.edu": [cname_rows()]})
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    captured = capsys.readouterr()
    assert code == 3
    assert "unverified 1" in captured.out
    assert "unknown 0" in captured.out
    assert "a.umich.edu  UNVERIFIED --" in captured.out
    assert "a.umich.edu  UNKNOWN --" not in captured.out
    assert "ERROR: a.umich.edu:" in captured.err


def test_an_unrecognised_exception_after_the_batch_returned_is_unverified_never_exit_two(
        apc, tmp_path, monkeypatch, capsys):
    """Fix-pass review, CRITICAL 1: exit 2 must never be reported once a batch call has RETURNED.

    Reproduced by the reviewer on HEAD before this fix, with a ONE-entry plan so no earlier
    `applied` entry can mask the arithmetic: the batch POST succeeded (Cloudflare swapped the
    CNAME for the A records), the post-apply verification read then raised a bare `ValueError`
    -- the SDK calls `response.json()` unguarded (`cloudflare/_response.py:266`), so a truncated
    or non-JSON 200 on that read raises `json.JSONDecodeError`, which is a `ValueError`, NOT a
    `cloudflare.CloudflareError` and NOT an `OSError`.  `apply_all` caught neither, so the entry
    kept its `not-attempted` seed, `changed_count()` saw 0, and `failure_code()` returned **2** --
    the code SPEC section 8 defines as "could not complete, and nothing in Cloudflare was
    changed".  Three artifacts lied at once: the exit code, the `mode:` line ("0 of 1 entries
    changed") and the run record.

    The fix is in `apply_entry`, not here: everything after the batch call returned is now inside
    a try that converts any unrecognised exception into `VerifyError`, on SPEC R6.3's existing
    reasoning -- "the transport failing is not evidence the batch did not commit" generalizes to
    anything raised after the commit.  So the outcome is `unverified` (inspect this FQDN by hand),
    never `unknown` and never `not-attempted`.  The ORIGINAL class is named in the message: an
    operator who is told only "the verification failed" cannot tell an SDK shape change from a
    truncated response.
    """
    path = write_doc(tmp_path, plan_doc())

    class VerifyReadReturnsGarbage(FakeCloudflareClient):
        def _list(self, **kwargs):
            if len(self.list_calls) == 1:   # the SECOND list() call -- pass 1's own read (the
                # first) must succeed normally; only the POST-BATCH verification read fails.
                self.list_calls.append(kwargs)
                raise ValueError("Expecting value: line 1 column 1 (char 0)")
            return super()._list(**kwargs)

    client = VerifyReadReturnsGarbage(rows_by_name={"a.umich.edu": [cname_rows()]})
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    captured = capsys.readouterr()
    # The batch RETURNED -- this is what makes exit 2 a lie, and it is asserted against the fake
    # client's recorded calls, never inferred.
    assert len(client.batch_calls) == 1
    assert code == 3
    assert "unverified 1" in captured.out
    assert "not attempted 0" in captured.out
    assert "FOR REAL -- 1 of 1 entries changed" in captured.out
    assert "a.umich.edu  UNVERIFIED --" in captured.out
    assert "ValueError" in captured.out
    assert "ERROR: a.umich.edu:" in captured.err
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    assert record["run"]["exit_code"] == 3
    assert record["entries"]["a.umich.edu"]["outcome"] == "unverified"
    assert "ValueError" in record["entries"]["a.umich.edu"]["error"]


def test_an_unrecognised_exception_from_the_batch_call_itself_is_unknown_never_exit_two(
        apc, tmp_path, monkeypatch, capsys):
    """Fix-pass review, CRITICAL 1, the other half: an unrecognised exception raised from the
    batch call ITSELF cannot be placed relative to the commit, so the entry's fate is `unknown`.

    `apply_entry` re-raises anything that is not `cloudflare.APIConnectionError`/
    `cloudflare.CloudflareError` from the batch clause untouched -- an `AttributeError` from an SDK
    shape change while building the request (nothing sent) and a `json.JSONDecodeError` while
    parsing a truncated 200 (committed) are indistinguishable from outside.  `apply_all`'s final
    arm therefore records `unknown`, the conservative label whose operator action is "inspect this
    FQDN by hand", and RE-RAISES so `main()`'s last line of defence still names the class on
    stderr (SPEC 8.3: "the catch-all NEVER swallows").

    ONE entry, deliberately: with the entry left at `not-attempted` (HEAD's behaviour) there is no
    earlier `applied` to carry `changed_count()` above zero, so the run exited 2 -- "nothing in
    Cloudflare was changed" -- about a call whose fate it could not account for.
    """
    path = write_doc(tmp_path, plan_doc())

    class BatchReturnsGarbage(FakeCloudflareClient):
        def _batch(self, **kwargs):
            self.batch_calls.append(kwargs)
            raise ValueError("Expecting value: line 1 column 1 (char 0)")

    client = BatchReturnsGarbage(rows_by_name={"a.umich.edu": [cname_rows()]})
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    captured = capsys.readouterr()
    assert len(client.batch_calls) == 1
    assert code == 3
    assert "unknown 1" in captured.out
    assert "not attempted 0" in captured.out
    assert "FOR REAL -- 1 of 1 entries changed" in captured.out
    assert "a.umich.edu  UNKNOWN --" in captured.out
    # SPEC 8.3: the class is always named on stderr, by main()'s catch-all -- so the re-raise is
    # load-bearing and is pinned here, not just the outcome word.
    assert "ERROR: unexpected ValueError:" in captured.err
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    assert record["run"]["exit_code"] == 3
    assert record["entries"]["a.umich.edu"]["outcome"] == "unknown"
    assert "ValueError" in record["entries"]["a.umich.edu"]["error"]


def test_an_unknown_fate_on_the_second_entry_leaves_the_third_never_posted(
        apc, tmp_path, monkeypatch):
    """Fix-pass review, IMPORTANT 2 (PD#14): `apply_all`'s UNKNOWN arm ends in `return`, and that
    `return` was unpinned -- every test reaching it used a ONE-entry document, where `return` and
    `continue` are indistinguishable.  Measured by the reviewer: changing it to `continue` left all
    211 tests green while the mutated run went on to rewrite a THIRD production zone past an entry
    whose fate was unknown -- the single behaviour `PROMPT.md` forbids most explicitly ("it should
    not attempt to make the remaining changes specified in the file"; SPEC R3.4).

    Asserted on the fake client's RECORDED batch calls, not on the outcome labels: a `continue`
    would still leave `c.umich.edu` with a plausible-looking `applied`, so only "the third entry
    was never POSTed" tells the two apart.
    """
    path = write_doc(tmp_path, three_entry_doc())

    class DropOnSecond(FakeCloudflareClient):
        def _batch(self, **kwargs):
            if len(self.batch_calls) == 1:
                self.batch_calls.append(kwargs)
                raise cloudflare.APIConnectionError(request=None)
            return super()._batch(**kwargs)

    rows = three_entry_rows()
    for name in rows:
        rows[name] = [rows[name][0], [row(r.type, name, r.content, r.id)
                                      for r in address_rows()]]
    client = DropOnSecond(rows_by_name=rows)
    monkeypatch.setattr(apc, "sleep", lambda seconds: None)
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    assert code == 3
    assert len(client.batch_calls) == 2
    assert [call["zone_id"] for call in client.batch_calls] == ["zone-a", "zone-b"]
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    outcomes = {k: v["outcome"] for k, v in record["entries"].items()}
    assert outcomes == {"a.umich.edu": "applied", "b.umich.edu": "unknown",
                        "c.umich.edu": "not-attempted"}


def test_an_unverified_entry_on_the_second_entry_leaves_the_third_never_posted(
        apc, tmp_path, monkeypatch):
    """Fix-pass review, IMPORTANT 2 (PD#14), the UNVERIFIED arm's twin of the test above -- its
    `return` was unpinned in exactly the same way and for exactly the same reason (one-entry
    documents only), and `return` -> `continue` there also left all 211 tests green.

    b.umich.edu's post-batch verification read returns NO records, twice `VERIFY_RETRY_SLEEP`
    apart, so `apply_entry` raises `VerifyError` after a batch that RETURNED.  c.umich.edu must
    never be POSTed."""
    path = write_doc(tmp_path, three_entry_doc())
    rows = three_entry_rows()
    for name in rows:
        if name == "b.umich.edu":
            rows[name] = [rows[name][0], []]   # pass 1 sees the CNAME; verification sees nothing
        else:
            rows[name] = [rows[name][0], [row(r.type, name, r.content, r.id)
                                          for r in address_rows()]]
    client = FakeCloudflareClient(rows_by_name=rows)
    monkeypatch.setattr(apc, "sleep", lambda seconds: None)
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    assert code == 3
    assert len(client.batch_calls) == 2
    assert [call["zone_id"] for call in client.batch_calls] == ["zone-a", "zone-b"]
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    outcomes = {k: v["outcome"] for k, v in record["entries"].items()}
    assert outcomes == {"a.umich.edu": "applied", "b.umich.edu": "unverified",
                        "c.umich.edu": "not-attempted"}


def test_exit_code_three_when_the_only_outcome_is_unverified(apc):
    """Item A (Task 8 review): the pure-function pin for R6.3's exit-3 rule, independent of any
    end-to-end run."""
    assert apc.exit_code_for(apc.tally({"a": "unverified", "b": "not-attempted"})) == 3


def test_changed_count_sums_applied_unverified_and_unknown(apc):
    """Important 3 (Task 8 review): `changed_count` is the ONE shared formula `exit_code_for` and
    `summary_lines` both call, so this pins its definition directly rather than only through the
    two call sites' own tests."""
    counts = apc.tally({"a": "applied", "b": "unverified", "c": "unknown",
                        "d": "failed", "e": "already-applied"})
    assert apc.changed_count(counts) == 3


def test_a_clean_for_real_run_applies_every_entry_and_exits_zero(
        apc, tmp_path, monkeypatch, capsys):
    """Critical 1 (Task 8 review): asserting only `len(client.batch_calls) == 3` (as this test did
    before the fix) proves `apply_entry` was called three times, never that it was called with the
    id PASS 1 actually resolved for THAT entry -- mutating `apply_all`'s call site to
    `apply_entry(client, fqdn, entry, ["WRONG-ID"])` left the whole suite green.  `three_entry_rows`
    now gives each FQDN a distinct delete id, and `three_entry_doc` a distinct `zone_id` (Important
    2, Task 8 re-review: Critical 1's fix closed the class for `deletes` but left it open for
    `zone_id`, which every fixture still shared), so asserting the full `batch_calls` list (matched
    per entry against the file's own `zone_id`/`deletes`/`posts`) actually catches a cross-wired id
    OR a cross-wired zone.  Also asserts the `applied` result line (Important 1): the only one of
    SPEC 11.2's four result-line shapes with no cover at all before this."""
    doc = three_entry_doc()
    path = write_doc(tmp_path, doc)
    rows = three_entry_rows()
    for name in rows:
        rows[name] = [rows[name][0], [row(r.type, name, r.content, r.id)
                                      for r in address_rows()]]
    client = FakeCloudflareClient(rows_by_name=rows)
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    assert code == 0
    assert client.batch_calls == [
        {"zone_id": doc["entries"]["a.umich.edu"]["zone_id"], "deletes": [{"id": "rec-a-cname"}],
         "posts": doc["entries"]["a.umich.edu"]["body"]["posts"]},
        {"zone_id": doc["entries"]["b.umich.edu"]["zone_id"], "deletes": [{"id": "rec-b-cname"}],
         "posts": doc["entries"]["b.umich.edu"]["body"]["posts"]},
        {"zone_id": doc["entries"]["c.umich.edu"]["zone_id"], "deletes": [{"id": "rec-c-cname"}],
         "posts": doc["entries"]["c.umich.edu"]["body"]["posts"]},
    ]
    assert "a.umich.edu  applied" in capsys.readouterr().out


def test_a_mixed_already_applied_and_ready_run_applies_only_the_ready_entries(
        apc, tmp_path, monkeypatch, capsys):
    """Critical 2 (Task 8 review): mutating `apply_all`'s already-applied `continue` into `return
    outcomes, details` left 122/122 green -- both the correct and the mutated behavior exit 1 on
    every EXISTING already-applied fixture, because each used a single, homogeneous entry (the one
    shape that survives that mutation: both a real skip-and-continue and a wrongful early-return
    produce "nothing else happened, exit 1").  This file mixes ONE already-applied entry FIRST in
    sort order with two ready ones, so the regression changes both the batch calls actually made
    and the counts line, not just the exit code."""
    path = write_doc(tmp_path, three_entry_doc())
    rows = three_entry_rows(applied=("a.umich.edu",))
    for name in ("b.umich.edu", "c.umich.edu"):
        rows[name] = [rows[name][0], [row(r.type, name, r.content, r.id)
                                      for r in address_rows()]]
    client = FakeCloudflareClient(rows_by_name=rows)
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    out = capsys.readouterr().out
    assert code == 1
    assert ("applied 2   already applied 1   planned 0   failed 0   unverified 0   unknown 0   "
            "not attempted 0") in out
    assert [call["posts"][0]["name"] for call in client.batch_calls] == [
        "b.umich.edu", "c.umich.edu"]


def test_for_real_verbose_prints_the_post_body_exactly_once(apc, tmp_path, monkeypatch, capsys):
    """Minor 9 (Task 8 review): `apply_all` printed a second, bare `POST <path>` line under -v --
    `report_entries` (pass 2) already prints the full POST line with the exact merged body per
    SPEC 11.2's `-v` row, and pass 3 has no line of its own in that table."""
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows(), address_rows()]})
    run_main(apc, ["-v", "--for-real", path], tmp_path, client, monkeypatch)
    out = capsys.readouterr().out
    assert out.count("POST /zones/zone-a/dns_records/batch") == 1


def test_verify_records_raises_invariant_error_on_the_impossible_empty_shape(apc):
    """Minor 7 (Task 8 review): the FOURTH instance of the nil-shadow class this file guards
    against elsewhere (`verdict_for`, `merge_body`, `describe_change`) -- `verify_records(entry
    with posts=[], rows=[])` returned True (two EMPTY sets compare equal, a false "verified"), and
    a missing `body` raised a bare, unnamed `KeyError`.  Unreachable through `apply_entry` today
    (`merge_body` already guards the same shape first), but this is a section-13-listed public
    helper in its own right -- "fix the class, not the instance."""
    entry = plan_entry()
    entry["body"]["posts"] = []
    with pytest.raises(apc.InvariantError):
        apc.verify_records(entry, [])

    missing_body = plan_entry()
    del missing_body["body"]
    with pytest.raises(apc.InvariantError):
        apc.verify_records(missing_body, [])


def test_apply_all_marks_the_in_flight_entry_unknown_on_a_keyboard_interrupt(apc, monkeypatch):
    """Minor 11 (Task 8 review): `apply_all` returned `outcomes`/`details` BY VALUE, so a
    `KeyboardInterrupt` raised out of `apply_entry` discarded every outcome accumulated so far --
    SPEC 9.3 requires the in-flight entry `unknown` and the rest `not-attempted`, which Task 9's
    summary+run-record write cannot honor unless the caller can still see this state AFTER the
    exception propagates.  Fixed by making the caller own `outcomes`/`details` (mutated in place,
    never returned as the only copy) and catching `KeyboardInterrupt` around the in-flight call to
    mark it before re-raising.

    Minor 5 (Task 8 re-review): a SINGLE-entry fixture only proves "in-flight -> unknown" -- it
    cannot distinguish that from a bug that clobbers EVERY outcome to `unknown` on interrupt, which
    would also pass a single-entry check.  SPEC 9.3's actual claim ("the in-flight entry unknown,
    the REST not-attempted") needs entries on both sides of the interrupted one: three entries, the
    interrupt lands on the second, and the assertion covers the WHOLE `outcomes` dict plus the
    batch call the first entry actually made (proving it was not reverted, PROMPT.md/R3.4)."""
    real_apply_entry = apc.apply_entry

    def flaky(client, fqdn, entry, delete_ids):
        if fqdn == "b.umich.edu":
            raise KeyboardInterrupt
        return real_apply_entry(client, fqdn, entry, delete_ids)

    monkeypatch.setattr(apc, "apply_entry", flaky)
    entries = three_entry_doc()["entries"]
    rows = three_entry_rows()
    rows["a.umich.edu"] = [rows["a.umich.edu"][0],
                           [row(r.type, "a.umich.edu", r.content, r.id) for r in address_rows()]]
    client = FakeCloudflareClient(rows_by_name=rows)
    validations = apc.validate_entries(client, entries, verbose=False)
    outcomes = dict.fromkeys(entries, "not-attempted")
    details = {}
    with pytest.raises(KeyboardInterrupt):
        apc.apply_all(client, entries, validations, outcomes, details)
    assert outcomes == {"a.umich.edu": "applied", "b.umich.edu": "unknown",
                        "c.umich.edu": "not-attempted"}
    assert details["b.umich.edu"]["error"] == "interrupted"
    assert client.batch_calls == [
        {"zone_id": entries["a.umich.edu"]["zone_id"], "deletes": [{"id": "rec-a-cname"}],
         "posts": entries["a.umich.edu"]["body"]["posts"]},
    ]


def test_apply_all_raises_invariant_error_on_a_non_ready_verdict(apc):
    """M4 (whole-branch review): SPEC R3.5's pass-3 invariant -- "an entry reaching pass 3
    without a `ready` verdict is an InvariantError" -- had no test; replacing the `if
    validation.verdict != "ready":` guard with `if False:` left the whole suite green.  Pass 1
    is supposed to have aborted the whole run before any invalid verdict ever reaches this
    function, so this is a defect-in-this-script's-own-reasoning guard (PD#1/PD#14), asserted
    here directly rather than trusted."""
    client = FakeCloudflareClient()
    entries = {"a.umich.edu": plan_entry()}
    validations = {"a.umich.edu": apc.Validation("records-missing", "contrived detail", [])}
    with pytest.raises(apc.InvariantError, match="records-missing"):
        apc.apply_all(client, entries, validations, {"a.umich.edu": "not-attempted"}, {})


def test_a_bare_apply_error_at_the_verification_position_yields_failed_not_unverified(
        apc, monkeypatch):
    """SPEC section 14 group 9's amendment (adversarial review finding 1): the whole reason
    `VerifyError` is a NAMED SUBCLASS of `ApplyError`, and not a sibling, is that `apply_all`
    catches it BEFORE the broader `ApplyError` clause -- so a bare `ApplyError` raised from the
    verification position (a defect that would reintroduce SPEC 8.1's originally-shipped bug) must
    still land on `failed`/exit 2 ("rejected, nothing committed"), never `unverified`/exit 3.
    Proven directly against `apply_all`'s except-clause DISPATCH by monkeypatching `apply_entry`
    itself -- independent of the real client mechanics `apply_entry`'s own tests already cover --
    which is what makes this test able to fail if the clause order in `apply_all` is ever
    reordered or collapsed, the exact regression this pair guards against (see the sibling test
    just below for the other half)."""
    def raises_apply_error(client, fqdn, entry, delete_ids):
        raise apc.ApplyError(f"{fqdn}: contrived rejection")

    monkeypatch.setattr(apc, "apply_entry", raises_apply_error)
    client = FakeCloudflareClient()
    entries = {"a.umich.edu": plan_entry()}
    validations = {"a.umich.edu": apc.Validation("ready", "", ["rec-1"])}
    outcomes = {"a.umich.edu": "not-attempted"}
    details = {}
    apc.apply_all(client, entries, validations, outcomes, details)
    assert outcomes == {"a.umich.edu": "failed"}
    assert apc.exit_code_for(apc.tally(outcomes)) == 2


def test_a_verify_error_at_the_verification_position_yields_unverified_not_failed(
        apc, monkeypatch):
    """The other half of the pair above (SPEC section 14 group 9): a `VerifyError` raised from the
    SAME position is `unverified`/exit 3, because Cloudflare's batch call already returned and
    committed -- only our confirmation of it is in doubt.  Together with the test above, this pair
    is the whole reason `VerifyError` exists as a distinct, subclassed exception rather than a
    bare `ApplyError` raised at the verification site."""
    def raises_verify_error(client, fqdn, entry, delete_ids):
        raise apc.VerifyError(f"{fqdn}: contrived verification failure")

    monkeypatch.setattr(apc, "apply_entry", raises_verify_error)
    client = FakeCloudflareClient()
    entries = {"a.umich.edu": plan_entry()}
    validations = {"a.umich.edu": apc.Validation("ready", "", ["rec-1"])}
    outcomes = {"a.umich.edu": "not-attempted"}
    details = {}
    apc.apply_all(client, entries, validations, outcomes, details)
    assert outcomes == {"a.umich.edu": "unverified"}
    assert apc.exit_code_for(apc.tally(outcomes)) == 3


# ---------------------------------------------------------------------------------------------
# Task 9: the run record and interruption (SPEC R8, R9, 9.2, 9.3, 9.4, 12).
# ---------------------------------------------------------------------------------------------


def test_now_utc_is_a_zulu_iso8601_timestamp_close_to_the_real_clock(apc):
    """B4 (final-batch review): `now_utc()` -- a SPEC section 13-named seam covering "every
    timestamp and the run-record filename" -- had NO test at all; every OTHER test in this file
    replaces it.  Mutation to `datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")` left 164
    passing: naive LOCAL time labelled Z in the only audit artifact of a destructive rewrite, and
    a filename with a SPACE in it that no longer matches SPEC 12.1's documented shape."""
    value = apc.now_utc()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value)
    parsed = datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=datetime.UTC)
    assert abs((datetime.datetime.now(tz=datetime.UTC) - parsed).total_seconds()) < 5


def test_outcome_path_is_named_run_not_applied(apc):
    """A DRY RUN writes one too, so "-applied-" would be a lie.  The timestamp makes a run
    incapable of clobbering a previous one."""
    # outcome_path is a pure string function -- no file at this path is ever opened, the literal
    # is only here to prove the directory is preserved (matches SPEC 12.1's own example).
    path = apc.outcome_path("/tmp/platform-domains-cloudflare-plan.json",  # noqa: S108
                            "2026-08-03T14:22:11Z")
    assert path.endswith("platform-domains-cloudflare-plan-run-20260803T142211Z.json")
    assert "-applied-" not in path


@pytest.mark.parametrize("bad_path", ["", ".", "/", "./."])
def test_outcome_path_is_total_even_for_a_pathological_file_argument(apc, bad_path):
    """I1 (whole-branch review): `Path("").with_name(...)`, `Path(".")`, `Path("/")` and
    `Path("./.")` all raise `ValueError: ... has an empty name` -- `outcome_path` used
    `with_name()`, so `./apply-platform-domains-cloudflare /` crashed with a raw traceback
    (measured on HEAD).  `outcome_path` is called from `finish()`, itself invoked from INSIDE
    main()'s own `except` clauses, so a fresh exception raised there is never redispatched to a
    sibling handler -- it must simply never raise.  This pins the pure function directly; the
    next test drives the same shape through the real `main()`."""
    result = apc.outcome_path(bad_path, "2026-08-03T14:22:11Z")
    assert result.endswith("-run-20260803T142211Z.json")


def test_a_pathological_file_argument_still_exits_named_not_crashing(apc, tmp_path, monkeypatch):
    """I1, end to end: `./apply-platform-domains-cloudflare .` is a plausible operator slip (a
    bare directory argument).  Before the fix this raised ValueError out of finish() -- called
    from inside main()'s `except StartupError` clause -- past main() entirely: no exit code, no
    summary, no run record.  reading "." raises IsADirectoryError (an OSError), so main() reaches
    exactly that clause and must still finish cleanly."""
    monkeypatch.setattr(apc, "now_utc", lambda: "2026-08-03T14:22:11Z")
    monkeypatch.chdir(tmp_path)
    code = apc.main(["."])
    assert code == 2
    record_path = apc.outcome_path(".", "2026-08-03T14:22:11Z")
    assert Path(record_path).exists()


def test_the_run_record_is_written_on_a_clean_dry_run(apc, tmp_path, monkeypatch):
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})
    run_main(apc, [path], tmp_path, client, monkeypatch)
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    assert record["run"]["for_real"] is False
    assert record["run"]["direction"] == "plan"
    assert record["entries"]["a.umich.edu"]["outcome"] == "planned"


def test_the_run_record_is_written_when_validation_fails(apc, tmp_path, monkeypatch):
    """SPEC R9.1: EVERY exit path, including the fatal ones -- this is the record an operator
    attaches to a change ticket."""
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [[]]})
    code = run_main(apc, [path], tmp_path, client, monkeypatch)
    assert code == 2
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    assert record["run"]["exit_code"] == 2
    assert record["entries"]["a.umich.edu"]["outcome"] == "not-attempted"
    assert "records-missing" in record["entries"]["a.umich.edu"]["verdict"]
    # Important 4 (review round 1): the `detail` half was unpinned -- emptying `item["detail"]`
    # in outcome_document left 145 passing.  The expected text is derived from verdict_for itself
    # (the same function that produced it), not a hand-copied literal that could drift from it.
    expected_detail = apc.verdict_for(plan_entry(), [])[1]
    assert record["entries"]["a.umich.edu"]["detail"] == expected_detail


def test_the_run_record_captures_created_and_deleted_ids(apc, tmp_path, monkeypatch):
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows(), address_rows()]})
    run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    entry = record["entries"]["a.umich.edu"]
    assert entry["outcome"] == "applied"
    assert entry["deleted_ids"] == ["rec-1"]
    assert sorted(entry["created_ids"]) == ["rec-a", "rec-b"]


def test_created_ids_exclude_an_unrelated_txt_record_at_the_name(apc, tmp_path, monkeypatch):
    """Adversarial review finding 3: mutating apply_entry's `return [r.id for r in rows]` (in
    place of `governed_records(rows)`) at the post-apply verification read left the whole suite
    green -- no --for-real apply fixture in this file carried a non-governed record at the
    verification read. A TXT (SPF) row beside the newly-created A/AAAA pair -- an ordinary DNS
    shape -- must never be reported as one of THIS entry's created ids in the run record."""
    path = write_doc(tmp_path, plan_doc())
    verify_rows = [*address_rows(), row("TXT", content="v=spf1 -all", identifier="rec-t")]
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows(), verify_rows]})
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    assert code == 0
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    assert sorted(record["entries"]["a.umich.edu"]["created_ids"]) == ["rec-a", "rec-b"]


def test_the_run_record_is_byte_exact_on_a_subset_for_real_run(apc, tmp_path, monkeypatch):
    """Important 3 (review round 1): eight of the ten `run` fields, including `entries_in_file`/
    `selected` TRANSPOSED, were unpinned by any existing test -- every record-writing test used
    `entries_in_file == selected` (1/1 or 3/3), so a swap of the two, an emptied `argv`/`counts`/
    `source`/`source_generated_at`, a dropped `at`, or a changed `tool` string all left 145
    passing.  ONE whole-document equality assertion on a `--only` SUBSET run (`entries_in_file=3,
    selected=1`) closes every one of those mutations at once: a swap, a drop or a change to any
    field is visible in an exact dict comparison the moment two numbers -- or any other value --
    differ.  SPEC 12.3: the clock is frozen (`run_main`'s `now_utc` patch), so the record is
    byte-deterministic and an exact comparison is honest, not brittle."""
    doc = three_entry_doc()
    path = write_doc(tmp_path, doc)
    rows = {"b.umich.edu": [
        [row("CNAME", "b.umich.edu", "live-umich-x.pantheonsite.io", "rec-b-cname")],
        [row("A", "b.umich.edu", "23.185.0.4", "rec-b-a"),
         row("AAAA", "b.umich.edu", "2620:12a:8000::4", "rec-b-aaaa")],
    ]}
    client = FakeCloudflareClient(rows_by_name=rows)
    argv = ["--for-real", "--only", "b.umich.edu", path]
    code = run_main(apc, argv, tmp_path, client, monkeypatch)
    assert code == 0
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    assert record == {
        "run": {
            "at": "2026-08-03T14:22:11Z",
            "tool": "apply-platform-domains-cloudflare",
            "direction": "plan",
            "source": path,
            "source_generated_at": "2026-08-01T00:22:23Z",
            "source_zones_swept": 187,
            "source_zones_total": 187,
            "for_real": True,
            "argv": argv,
            "exit_code": 0,
            "entries_in_file": 3,
            "selected": 1,
            "counts": {"applied": 1, "already-applied": 0, "planned": 0, "failed": 0,
                       "unverified": 0, "unknown": 0, "not-attempted": 0},
        },
        "entries": {
            "b.umich.edu": {
                "outcome": "applied",
                "at": "2026-08-03T14:22:11Z",
                "deleted_ids": ["rec-b-cname"],
                "created_ids": ["rec-b-a", "rec-b-aaaa"],
            },
        },
    }


def test_a_record_write_failure_never_claims_nothing_changed(apc, tmp_path, monkeypatch, capsys):
    """SPEC 9.2: exiting 2 after a for-real run that rewrote records would assert "nothing was
    changed" about production DNS.  The earned code stands; the error is still named."""
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows(), address_rows()]})

    def boom(record_path, document):
        raise apc.OutputWriteError(f"cannot write {record_path}: disk full")

    monkeypatch.setattr(apc, "write_run_record", boom)
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    assert code == 0
    assert "cannot write" in capsys.readouterr().err


def test_a_record_write_failure_on_a_dry_run_is_exit_two(apc, tmp_path, monkeypatch):
    """The other branch: a dry run whose only deliverable was the record has genuinely failed."""
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})

    def boom(record_path, document):
        raise apc.OutputWriteError(f"cannot write {record_path}: disk full")

    monkeypatch.setattr(apc, "write_run_record", boom)
    assert run_main(apc, [path], tmp_path, client, monkeypatch) == 2


def test_an_interrupted_run_keeps_exit_130_even_when_the_record_write_fails(
        apc, tmp_path, monkeypatch, capsys):
    """A3 (final-batch review): `finish()`'s SPEC 9.2 precedence rule ends `return code if
    changed_count(counts) else 2` -- with `code == 130` and NOTHING yet changed (a Ctrl-C during
    pass 1, before any entry is attempted), that formula silently downgrades an INTERRUPTED run to
    2, a code SPEC 9.2's table never names for this situation.  130 means the OPERATOR caused the
    run to stop; 2 means the run could not complete on its own -- losing that distinction is a
    real information loss even though both codes technically mean the run failed to finish
    cleanly.  130 is exempt from the "changed nothing -> 2" rule because an interrupt is not a
    failure to complete in the same sense a validation/apply failure is: the operator already
    knows why the run stopped, and reporting 2 instead would erase that they are the reason."""
    path = write_doc(tmp_path, plan_doc())

    class Interrupting(FakeCloudflareClient):
        def _list(self, **kwargs):
            raise KeyboardInterrupt

    def boom(record_path, document):
        raise apc.OutputWriteError(f"cannot write {record_path}: disk full")

    monkeypatch.setattr(apc, "write_run_record", boom)
    code = run_main(apc, [path], tmp_path, Interrupting(), monkeypatch)
    assert code == 130
    assert "cannot write" in capsys.readouterr().err


def test_a_real_unwritable_record_directory_is_named_not_swallowed(
        apc, tmp_path, monkeypatch, capsys):
    """Important 2 (review round 1): BOTH tests above monkeypatch write_run_record ITSELF,
    replacing its whole body -- so write_run_record's OWN try/except (OSError/TypeError/ValueError
    -> OutputWriteError) had zero cover, and reducing it to a bare write_json_atomic() call left
    145 passing.  Measured: with that wrapping gone, a REAL unwritable directory raises a bare
    PermissionError that escapes write_run_record, escapes finish() (whose own try/except only
    catches OutputWriteError, never a plain OSError), and -- because finish() is called a SECOND
    time from inside main()'s own `except OSError` clause on this path -- escapes THAT clause too
    (a fresh exception raised inside an except clause is never redispatched to a sibling clause of
    the same try), reaching main()'s caller as an uncaught traceback: exit 1, the code that means
    "completed with already-applied skips," the worst possible lie for a run that just rewrote
    production DNS.  This drives main() end to end against a REAL chmod'd directory rather than a
    monkeypatched write_run_record, so it is the wrapping logic itself under test."""
    record_dir = tmp_path / "unwritable"
    record_dir.mkdir()
    path = write_doc(record_dir, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})
    record_dir.chmod(0o500)
    try:
        code = run_main(apc, [path], tmp_path, client, monkeypatch)
    finally:
        record_dir.chmod(0o700)   # tmp_path's own fixture cleanup needs write access back
    err = capsys.readouterr().err
    assert "cannot write the run record" in err
    assert "PermissionError" in err
    assert code == 2   # dry run: changed nothing, SPEC 9.2's other precedence branch


def test_write_run_record_wraps_a_serialization_failure(apc, monkeypatch):
    """Important 2 (review round 1), the TypeError branch: patches `write_json_atomic` -- NOT
    `write_run_record` itself, which the two tests above already fully replace -- so
    write_run_record's OWN wrapping is what is under test.  A genuinely unserializable value in
    the document is a second, indirect way to trigger this same branch; patching the seam
    write_run_record calls is simpler and just as honest, since write_run_record does not care WHY
    write_json_atomic raised, only that it did."""
    def boom(path, data):
        raise TypeError("Object of type object is not JSON serializable")

    monkeypatch.setattr(apc, "write_json_atomic", boom)
    with pytest.raises(apc.OutputWriteError, match="TypeError"):
        apc.write_run_record("run.json", {"run": {}})


def test_an_interrupt_during_a_batch_call_records_unknown_and_exits_130(
        apc, tmp_path, monkeypatch, capsys):
    """SPEC 9.3: the in-flight entry is `unknown` -- never `failed`, never `not-attempted`."""
    path = write_doc(tmp_path, three_entry_doc())
    monkeypatch.setattr(apc.signal, "signal", lambda *args: None)  # see SPEC 9.3's test caveat

    class InterruptOnSecond(FakeCloudflareClient):
        def _batch(self, **kwargs):
            if len(self.batch_calls) == 1:
                raise KeyboardInterrupt
            return super()._batch(**kwargs)

    rows = three_entry_rows()
    for name in rows:
        rows[name] = [rows[name][0], [row(r.type, name, r.content, r.id)
                                      for r in address_rows()]]
    client = InterruptOnSecond(rows_by_name=rows)
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    assert code == 130
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    outcomes = {k: v["outcome"] for k, v in record["entries"].items()}
    assert outcomes["a.umich.edu"] == "applied"
    assert outcomes["b.umich.edu"] == "unknown"
    assert outcomes["c.umich.edu"] == "not-attempted"
    assert "unknown 1" in capsys.readouterr().out
    # B6 (final-batch review): the outcome-only comparison above only proves the WORD "unknown"
    # made it through -- dropping `deleted_ids` (or the per-entry `at`) from this INTERRUPT arm's
    # own `details[fqdn] = {...}` left 164 passing, because nothing compared the whole per-entry
    # dict the way the success-path byte-exact test already does.  `deleted_ids` here is exactly
    # the list an operator needs to hand-repair an interrupted rewrite; "c" gets none of this --
    # `not-attempted` never reaches apply_all at all (SPEC 12.2's own example agrees).
    assert record["entries"]["b.umich.edu"] == {
        "outcome": "unknown",
        "at": "2026-08-03T14:22:11Z",
        "error": "interrupted",
        "deleted_ids": ["rec-b-cname"],
    }
    assert record["entries"]["c.umich.edu"] == {"outcome": "not-attempted"}


def test_the_flush_ignores_a_second_ctrl_c(apc, tmp_path, monkeypatch, capsys):
    """SPEC 9.3: a second Ctrl-C must not truncate the ONE record of what a destructive run
    did.  Asserted by observing the SIG_IGN call, since the real behavior cannot be provoked
    in-process.

    Minor 6 (review round 1): this test asserted NEITHER the exit code nor that the record was
    actually written -- it proved SIG_IGN was requested, but not that the interrupted run still
    completed its SPEC R8.1/R9.1 obligations around that guard.  Both added below.

    I6 (whole-branch review): SPEC 9.1's `KeyboardInterrupt` row -- `report_line("ERROR:
    interrupted")` -- was deletable with the whole suite green.  This is a Ctrl-C during PASS 1
    (raised straight out of `_list`, before `apply_all` ever runs), so it reaches main()'s
    `except KeyboardInterrupt` clause directly, never `apply_all`'s own interrupt handling.
    """
    calls = []
    monkeypatch.setattr(apc.signal, "signal", lambda sig, handler: calls.append((sig, handler)))
    path = write_doc(tmp_path, plan_doc())

    class Interrupting(FakeCloudflareClient):
        def _list(self, **kwargs):
            raise KeyboardInterrupt

    code = run_main(apc, [path], tmp_path, Interrupting(), monkeypatch)
    assert (apc.signal.SIGINT, apc.signal.SIG_IGN) in calls
    assert code == 130
    assert "ERROR: interrupted" in capsys.readouterr().err
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    assert record["run"]["exit_code"] == 130


def test_the_sigint_guard_runs_before_the_flushs_own_writes(apc, tmp_path, monkeypatch):
    """Minor 5 (review round 1): the guard's POSITION inside finish() was unpinned -- moving
    `signal.signal(SIGINT, SIG_IGN)` to AFTER write_run_record left 145 passing, so no test could
    tell a guard that actually protects the flush from a useless one sitting after it.  SPEC 9.3:
    "During THAT FINAL FLUSH, SIGINT MUST be set to SIG_IGN" -- meaning before ANY of the flush's
    own writes, not merely somewhere inside finish().

    A VALIDATION-FAILURE run is used deliberately: it is the one path where pass 2
    (report_entries) never runs, so the ONLY write_report/write_run_record calls in this run are
    finish()'s own flush -- isolating the ordering assertion to exactly what SPEC 9.3 is about,
    rather than picking up an earlier, unrelated write_report call from pass 2's report.

    (Review round 1, Minor 5 also noted the brief's sketch wraps this call in
    `contextlib.suppress(ValueError)`, which this implementation deliberately omits -- see the
    fix report's deviation note: both sibling scripts (`find-platform-domains-dns`'s
    `report_stop()`, `psh/lifecycle.py`'s `abort_run()`) call it bare, and nothing in this
    single-threaded script can raise "signal only works in main thread".)
    """
    order = []
    monkeypatch.setattr(apc.signal, "signal", lambda *args: order.append("signal"))

    real_write_report = apc.write_report

    def recording_write_report(text):
        order.append("write_report")
        return real_write_report(text)

    monkeypatch.setattr(apc, "write_report", recording_write_report)

    real_write_run_record = apc.write_run_record

    def recording_write_run_record(path, document):
        order.append("write_run_record")
        return real_write_run_record(path, document)

    monkeypatch.setattr(apc, "write_run_record", recording_write_run_record)

    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [[]]})
    code = run_main(apc, [path], tmp_path, client, monkeypatch)
    assert code == 2
    assert order[0] == "signal"
    assert "write_report" in order
    assert "write_run_record" in order


def test_a_mid_run_invariant_error_after_an_applied_entry_exits_three_not_two(
        apc, tmp_path, monkeypatch):
    """Task 9 review-deferred defect (task brief item 2): SPEC 9.1's table pins InvariantError's
    exit flatly to 2, which contradicts SPEC 8.1 once an EARLIER entry in the same run already
    applied -- exactly the same "changed > 0 -> 3" rule ApplyError/VerifyError already earn
    through exit_code_for.  Reproduced by making apply_entry raise InvariantError for the second
    of three entries, after the first has genuinely applied -- the resolution routes a
    StartupError/InvariantError escaping mid-run through the SAME changed-aware code finish()'s
    record-write precedence rule already uses, rather than reporting the flat 2 that would assert
    "nothing was changed" about an entry this very run just applied."""
    path = write_doc(tmp_path, three_entry_doc())
    real_apply_entry = apc.apply_entry

    def flaky(client, fqdn, entry, delete_ids):
        if fqdn == "b.umich.edu":
            raise apc.InvariantError("contrived mid-run invariant violation")
        return real_apply_entry(client, fqdn, entry, delete_ids)

    monkeypatch.setattr(apc, "apply_entry", flaky)
    rows = three_entry_rows()
    for name in rows:
        rows[name] = [rows[name][0], [row(r.type, name, r.content, r.id)
                                      for r in address_rows()]]
    client = FakeCloudflareClient(rows_by_name=rows)
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    assert code == 3
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    assert record["run"]["exit_code"] == 3
    assert record["entries"]["a.umich.edu"]["outcome"] == "applied"
    assert record["entries"]["b.umich.edu"]["outcome"] == "not-attempted"
    assert record["entries"]["c.umich.edu"]["outcome"] == "not-attempted"


def test_a_plain_exception_mid_apply_after_an_applied_entry_exits_three_not_two(
        apc, tmp_path, monkeypatch, capsys):
    """Review round 1, Critical 1: `except OSError` and `except BaseException` each still had
    their OWN independently-written flat `2`, even after the InvariantError test above fixed
    `except StartupError` alone.  Measured by the reviewer: a bare `RuntimeError` out of
    apply_entry on the second of three entries -- an unexpected SDK shape change, exactly what the
    `except BaseException` last-line-of-defence exists for (SPEC 8.3) -- landed on that flat 2
    even though entry `a` had genuinely applied and verified; the run's own summary line read "1 of
    3 entries changed" while the exit code claimed nothing had.  Fixed by routing all three failure
    arms through the ONE shared `failure_code(state)` helper.  `RuntimeError` (not
    `apc.InvariantError`, which the test above already covers) is what actually exercises `except
    BaseException` here: `apply_all` only catches KeyboardInterrupt/transport errors/ApplyError/
    VerifyError, so anything else -- including a plain RuntimeError -- propagates all the way past
    `run_once()` uncaught, past `except StartupError` (RuntimeError is not one), to the
    catch-all.

    I6 (whole-branch review): `report_line(f"ERROR: unexpected {type(e).__name__}: {e}")` --
    SPEC 8.3's "the catch-all NEVER swallows -- the class is always named on stderr" -- was
    deletable with the whole suite green.  The stderr assertion below is what closes that."""
    path = write_doc(tmp_path, three_entry_doc())
    real_apply_entry = apc.apply_entry

    def flaky(client, fqdn, entry, delete_ids):
        if fqdn == "b.umich.edu":
            raise RuntimeError("contrived SDK-shape defect")
        return real_apply_entry(client, fqdn, entry, delete_ids)

    monkeypatch.setattr(apc, "apply_entry", flaky)
    rows = three_entry_rows()
    for name in rows:
        rows[name] = [rows[name][0], [row(r.type, name, r.content, r.id)
                                      for r in address_rows()]]
    client = FakeCloudflareClient(rows_by_name=rows)
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    assert code == 3
    assert ("ERROR: unexpected RuntimeError: contrived SDK-shape defect"
            in capsys.readouterr().err)
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    assert record["run"]["exit_code"] == 3
    assert record["entries"]["a.umich.edu"]["outcome"] == "applied"


@needs_dev_full
def test_a_doomed_stdout_during_the_flush_still_exits_a_named_code_not_crashing(tmp_path):
    """A latent gap Task 9's own restructure introduces, not one of the brief's seven tests: the
    summary-block print now happens inside finish(), and finish() is called from FOUR places,
    THREE of them already inside one of main()'s own `except` clauses.  A fresh exception raised
    INSIDE an except clause is never redispatched to a sibling except of the SAME try statement,
    so a doomed stdout hit for the FIRST time inside such a finish() call -- e.g. a run that fails
    before a single byte of output exists, like a missing FILE argument -- would otherwise escape
    main() entirely as an unhandled StartupError instead of the named exit 2 every other doomed-
    stdout path in this script produces.  Reproduced with a nonexistent FILE (so main() never
    reaches the FakeClient or a single stdout write before finish()'s own summary print is the
    first one attempted)."""
    path = str(tmp_path / "does-not-exist.json")
    with Path(DEV_FULL).open("w") as doomed_out:
        completed = run_apc_in_a_subprocess(tmp_path, [path], stdout=doomed_out,
                                            stderr=subprocess.PIPE)
    assert completed.returncode == 2
    assert b"does-not-exist.json" in completed.stderr
    assert b"cannot write the report to standard output" in completed.stderr

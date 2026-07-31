"""Offline tests for development/finalize-session.py (the /archive-session workhorse).

BACKFILL, per prompts/add-tests-for-change.prompt.md: this code shipped untested, so these tests
could not go red first and they verify what the code DOES.  The one adversarial move still
available is used throughout -- every expected value is derived from the behavior each pattern's
own comment CLAIMS, or from a hand-built worked example, never by running the script and pasting
what it printed.

Why this module earns tests at all, being a dev tool rather than program code: `scrub()` is the
only thing standing between a session transcript and a committed secret, and
development/README.md's manual grep is explicitly described as a backstop to it, not a substitute.
A silent regression here is a credential in git history.

The script has no importable module name (a dash, and it lives outside any package), so it is
loaded with the SourceFileLoader idiom the suite already uses for the standalone utilities.
"""
import importlib.util
import json
import os
import re
import sys
from datetime import datetime
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

pytestmark = pytest.mark.unit

SCRIPT = Path(__file__).resolve().parent.parent.parent / "development" / "finalize-session.py"


@pytest.fixture
def fs():
    """The script, loaded fresh.  Its entry point is __main__-guarded, so import runs nothing."""
    loader = SourceFileLoader("finalize_session_probe", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


# --- scrub(): the security-critical surface ---------------------------------------------------
#
# Positive cases.  `secret` is the substring that MUST NOT survive; `label` is the redaction tag
# the pattern's own comment says it applies, so a pattern silently rewired to a different tag
# (or caught by the generic high-entropy fallback instead of its specific rule) goes red.

@pytest.mark.parametrize(("text", "secret", "label"), [
    # KEY=value / KEY: value for the named env vars
    ("SMTP_PASSWORD=hunter2-correct-horse", "hunter2-correct-horse", "SMTP_PASSWORD"),
    ("AWS_SECRET_ACCESS_KEY: wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY",
     "wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY", "AWS_SECRET_ACCESS_KEY"),
    ("CLOUDFLARE_EMAIL=person@example.edu", "person@example.edu", "CLOUDFLARE_EMAIL"),
    # Lowercased env-var name: the pattern is (?i)
    ("smtp_password=lower-case-name-still-caught", "lower-case-name-still-caught", "smtp_password"),
    # AWS access key ID, bare
    ("the id AKIAIOSFODNN7EXAMPLE appears", "AKIAIOSFODNN7EXAMPLE", "aws-key-id"),
    # Cloudflare key by VALUE SHAPE, with no field name at all, and no length floor --
    # the comment is explicit that even a truncated 8-char prefix must not ship.
    ("token is cfk_v1_abcd", "cfk_v1_abcd", "cloudflare-api-key"),
    # API field names rather than env-var names, 24+ chars
    ("api_token: abcdefghijklmnopqrstuvwxyz012345", "abcdefghijklmnopqrstuvwxyz012345",
     "credential"),
    ("machine-token = ABCDEFGHIJKLMNOPQRSTUVWX", "ABCDEFGHIJKLMNOPQRSTUVWX", "credential"),
    ("api_email: someone@umich.edu", "someone@umich.edu", "credential-email"),
    # Pantheon tokens in JSON
    ('{"machine_token": "mt-abcdefghijklmnop"}', "mt-abcdefghijklmnop", "token"),
    ('{"session": "sess-abcdefghijklmnop"}', "sess-abcdefghijklmnop", "token"),
    # Authorization header
    ("Authorization: Bearer abcdefghijklmnop", "abcdefghijklmnop", "bearer"),
    # Cloudflare edge cookies (added after a real `curl -D -` put one in a transcript)
    ("set-cookie: __cf_bm=C46vVhbEXxxVjf.Nny7h-7BKHdt4v; HttpOnly",
     "C46vVhbEXxxVjf.Nny7h-7BKHdt4v", "cf-cookie"),
    ("cf_clearance=Ab3.def-ghi_jklmnop", "Ab3.def-ghi_jklmnop", "cf-cookie"),
    # Bare high-entropy run: mixed case AND a digit, 32+ chars, no anchor of any kind
    ("leaked " + "aB3" * 12, "aB3" * 12, "high-entropy"),
])
def test_scrub_redacts(fs, text, secret, label):
    out = fs.scrub(text)
    assert secret not in out, f"{label}: the secret survived scrubbing"
    assert f"«REDACTED:{label}»" in out, f"{label}: redacted, but not by the expected rule"


def test_scrub_redacts_a_pem_private_key_block_including_its_body(fs):
    body = "MIIEowIBAAKCAQEAxGgB3nQ7Vd5ePzQ2LmKp8fRt\nYzWq0aBcDeFgHiJkLmNoPq1234567890"
    text = f"-----BEGIN RSA PRIVATE KEY-----\n{body}\n-----END RSA PRIVATE KEY-----"
    out = fs.scrub(text)
    assert "«REDACTED:private-key»" in out
    assert "MIIEowIBAAKCAQEAxGgB3nQ7Vd5ePzQ2LmKp8fRt" not in out
    assert "BEGIN RSA PRIVATE KEY" not in out, "the whole block goes, not just the body"


# Negative cases.  These MUST survive: a scrubber that redacted them would make development
# transcripts unreadable, which is the stated reason the high-entropy rule is narrow.

@pytest.mark.parametrize(("text", "why"), [
    ("commit 6389e08a1b2c3d4e5f60718293a4b5c6d7e8f9a0 fixed it",
     "a 40-char git SHA is all-lowercase hex -- no uppercase, so it is not high-entropy"),
    ("ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJ", "an all-caps constant has no lowercase"),
    ("averylongallslowercaseidentifiernameheretoo", "a long lowercase identifier has no uppercase"),
    ("MixedCaseButNoDigitsAtAllInThisLongRun", "mixed case WITHOUT a digit is not a token shape"),
    ('api_key = "k-456"', "short values keep ordinary source readable (24-char floor)"),
    ("api_token = cf.get('api_token')", "source code referencing the field name is not a value"),
    ("the SMTP_PASSWORD variable is documented in docs/env-and-smtp-configuration.md",
     "a prose mention with no = or : separator carries no value"),
])
def test_scrub_leaves_readable_text_alone(fs, text, why):
    assert fs.scrub(text) == text, why


def test_scrub_is_idempotent(fs):
    """Re-scrubbing must not chew through its own markers -- finalize-session scrubs the stats
    document that may already quote scrubbed transcript text."""
    text = ("SMTP_PASSWORD=hunter2 and AKIAIOSFODNN7EXAMPLE and Bearer abcdefghijklmnop "
            "and " + "aB3" * 12)
    once = fs.scrub(text)
    assert fs.scrub(once) == once


def test_scrub_redacts_every_occurrence_not_just_the_first(fs):
    # Both IDs are AKIA + exactly 16 chars: the pattern is \bAKIA[0-9A-Z]{16}\b, so a 17-char
    # tail fails the trailing \b and is (correctly) left alone.
    out = fs.scrub("AKIAIOSFODNN7EXAMPLE then AKIAJKLMNOPQ7EXAMPLE")
    assert "AKIA" not in out
    assert out.count("«REDACTED:aws-key-id»") == 2


def test_scrub_declines_an_aws_key_id_of_the_wrong_length(fs):
    """The trailing \b is load-bearing: AKIA + 17 chars is not an access key ID, and widening
    the pattern to catch it would start eating ordinary uppercase identifiers.

    NOTE for anyone running /archive-session's verification grep: this fixture WILL show up as a
    hit, because that grep is `AKIA[0-9A-Z]{16}` with no trailing \b and so matches the first 16
    of these 17 characters.  It is an invented string, not a key -- and the mismatch is the point
    of the test.  Do not "fix" it by renaming the fixture; the AKIA prefix is what exercises the
    boundary."""
    text = "AKIAJKLMNOPQR7EXAMPLE is one character too long"
    assert fs.scrub(text) == text


def test_scrub_handles_a_secret_glued_to_an_escaped_newline(fs):
    """The env-var pattern deliberately has NO leading \\b: a secret rendered right after an
    escaped newline in a JSON-encoded command input glues an `n` onto the key name."""
    out = fs.scrub(r"{\"command\": \"export FOO=1\nSMTP_PASSWORD=hunter2-secret\"}")
    assert "hunter2-secret" not in out


@given(st.text(alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
               min_size=32, max_size=80))
def test_scrub_never_leaves_a_token_shaped_secret_behind_an_env_var_name(secret):
    """Property: whatever the value looks like, `SMTP_PASSWORD=<it>` must not survive.

    Loaded per-call rather than via the fixture: Hypothesis test functions cannot take
    function-scoped fixtures.
    """
    loader = SourceFileLoader("finalize_session_prop", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    assert secret not in module.scrub(f"SMTP_PASSWORD={secret}")


# --- load(): JSONL reading --------------------------------------------------------------------

def test_load_reads_one_object_per_line_and_skips_blanks(fs, tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text('{"a": 1}\n\n   \n{"a": 2}\n', encoding="utf-8")
    assert fs.load(path) == [{"a": 1}, {"a": 2}]


def test_load_silently_drops_a_malformed_line(fs, tmp_path):
    """Documented behavior, and a sharp edge worth pinning: a truncated JSONL row (a session
    killed mid-write) is dropped with NO warning, so the transcript is quietly short."""
    path = tmp_path / "s.jsonl"
    path.write_text('{"a": 1}\n{"a": 2\n{"a": 3}\n', encoding="utf-8")
    assert fs.load(path) == [{"a": 1}, {"a": 3}]


# --- render_transcript() ----------------------------------------------------------------------

def row(rtype, blocks, **extra):
    """One JSONL row carrying a message with the given content blocks."""
    return {"type": rtype, "message": {"content": blocks}, **extra}


def test_render_transcript_renders_each_block_kind_under_its_own_heading(fs):
    out = fs.render_transcript([
        row("user", [{"type": "text", "text": "do the thing"}]),
        row("assistant", [{"type": "thinking", "thinking": "considering"},
                          {"type": "text", "text": "done"},
                          {"type": "tool_use", "name": "Bash", "id": "t1",
                           "input": {"command": "ls"}}]),
        row("user", [{"type": "tool_result", "content": "file.txt"}]),
    ])
    assert "## User\n\ndo the thing" in out
    assert "## Assistant thinking\n\nconsidering" in out
    assert "## Assistant\n\ndone" in out
    assert "### ⚙ Tool call: `Bash`" in out
    assert '"command": "ls"' in out
    assert "### ↳ Tool result" in out
    assert "file.txt" in out


def test_render_transcript_tags_subagent_rows(fs):
    out = fs.render_transcript([
        row("assistant", [{"type": "text", "text": "sub work"}], isSidechain=True)])
    assert "## Assistant _(subagent)_" in out


def test_render_transcript_accepts_string_content_as_one_text_block(fs):
    assert "hello there" in fs.render_transcript([{"type": "user",
                                                   "message": {"content": "hello there"}}])


@pytest.mark.parametrize("skipped", [
    {"type": "summary", "message": {"content": [{"type": "text", "text": "SHOULD NOT APPEAR"}]}},
    {"type": "user", "message": "not-a-dict"},
    {"type": "user", "message": {"content": [{"type": "text", "text": "   "}]}},
])
def test_render_transcript_skips_what_it_cannot_or_should_not_render(fs, skipped):
    out = fs.render_transcript([skipped])
    assert out.strip() == "# Session transcript", "only the header should remain"


def test_result_text_joins_only_the_text_parts_of_a_block_list(fs):
    assert fs._result_text([{"type": "text", "text": "one"},
                            {"type": "image", "source": "..."},
                            {"type": "text", "text": "two"}]) == "one\ntwo"
    assert fs._result_text("plain string  ") == "plain string"
    assert fs._result_text(None) == ""


# --- collect_stats(): the dedup logic that a naive version gets ~3x wrong ---------------------

def assistant_row(request_id, out_tokens, *, blocks=(), model="claude-opus-5", **usage):
    return {"type": "assistant", "requestId": request_id,
            "message": {"id": f"msg_{request_id}", "model": model,
                        "content": list(blocks),
                        "usage": {"output_tokens": out_tokens, **usage}}}


def test_collect_stats_counts_one_request_once_even_though_it_spans_many_rows(fs):
    """Claude Code writes one row per content block, each repeating the SAME usage block.
    Summing per row would triple the tokens and the turn count -- the defect the dedupe exists
    for, and the reason these numbers are hand-derived: 3 rows x 100 output tokens is ONE
    request of 100, not 300."""
    rows = [assistant_row("req-1", 100, input_tokens=50, cache_read_input_tokens=7)
            for _ in range(3)]
    s = fs.collect_stats(rows)
    assert s["turns"] == 1
    assert s["per_model"]["claude-opus-5"]["out"] == 100
    assert s["per_model"]["claude-opus-5"]["inp"] == 50
    assert s["per_model"]["claude-opus-5"]["read"] == 7


def test_collect_stats_keeps_the_row_with_the_largest_output_for_a_request(fs):
    """Rows for one request are written as output accumulates, so the LAST/largest is the
    complete one; keeping a smaller one would under-report."""
    s = fs.collect_stats([assistant_row("req-1", 10), assistant_row("req-1", 250),
                          assistant_row("req-1", 90)])
    assert s["per_model"]["claude-opus-5"]["out"] == 250


def test_collect_stats_falls_back_to_the_message_id_when_there_is_no_request_id(fs):
    a = {"type": "assistant",
         "message": {"id": "msg_A", "model": "m", "content": [], "usage": {"output_tokens": 5}}}
    b = {"type": "assistant",
         "message": {"id": "msg_B", "model": "m", "content": [], "usage": {"output_tokens": 6}}}
    s = fs.collect_stats([a, dict(a), b])
    assert s["turns"] == 2, "two distinct message ids are two requests"
    assert s["per_model"]["m"]["out"] == 11


def test_collect_stats_separates_models(fs):
    s = fs.collect_stats([assistant_row("r1", 10, model="claude-opus-5"),
                          assistant_row("r2", 20, model="claude-haiku-4-5")])
    assert s["per_model"]["claude-opus-5"]["out"] == 10
    assert s["per_model"]["claude-haiku-4-5"]["out"] == 20


def test_collect_stats_counts_each_tool_use_block_once_by_id(fs):
    """Tool blocks are deduped by BLOCK id, not request id: one request can legitimately hold
    several tool calls, but the same block repeated across rows must count once."""
    call = {"type": "tool_use", "id": "toolu_1", "name": "Bash"}
    other = {"type": "tool_use", "id": "toolu_2", "name": "Read"}
    s = fs.collect_stats([assistant_row("r1", 1, blocks=[call, other]),
                          assistant_row("r1", 2, blocks=[call])])
    assert s["tools"] == {"Bash": 1, "Read": 1}


def test_collect_stats_reports_the_largest_single_prompt_as_the_context_high_water_mark(fs):
    """max_ctx is input + cache read + cache write on ONE turn -- 1+2+3 and 10+20+30 give 60,
    not the 66 a sum-of-all-turns version would report."""
    s = fs.collect_stats([
        assistant_row("r1", 1, input_tokens=1, cache_read_input_tokens=2,
                      cache_creation_input_tokens=3),
        assistant_row("r2", 1, input_tokens=10, cache_read_input_tokens=20,
                      cache_creation_input_tokens=30),
    ])
    assert s["max_ctx"] == 60


def test_collect_stats_splits_cache_creation_by_ttl(fs):
    s = fs.collect_stats([assistant_row(
        "r1", 1, cache_creation={"ephemeral_5m_input_tokens": 4, "ephemeral_1h_input_tokens": 9})])
    assert (s["per_model"]["claude-opus-5"]["w5"], s["per_model"]["claude-opus-5"]["w1"]) == (4, 9)


def test_collect_stats_takes_first_and_last_timestamps_from_any_row_type(fs):
    s = fs.collect_stats([{"type": "user", "timestamp": "2026-07-31T10:00:00"},
                          {"type": "assistant", "timestamp": "2026-07-31T10:30:00",
                           "message": {"id": "m", "model": "m", "content": [], "usage": {}}},
                          {"type": "summary", "timestamp": "2026-07-31T11:00:00"}])
    assert s["first"].isoformat() == "2026-07-31T10:00:00"
    assert s["last"].isoformat() == "2026-07-31T11:00:00"


def test_collect_stats_tolerates_unparseable_and_absent_timestamps(fs):
    s = fs.collect_stats([{"type": "user", "timestamp": "not-a-timestamp"}, {"type": "user"}])
    assert (s["first"], s["last"]) == (None, None)


# --- render_stats() ---------------------------------------------------------------------------

def stats(**overrides):
    base = {"per_model": {"claude-opus-5": {"inp": 1000, "out": 2000, "read": 3000,
                                            "w5": 40, "w1": 5}},
            "tools": {"Bash": 7, "Read": 2}, "turns": 12, "max_ctx": 123456,
            "first": None, "last": None}
    base.update(overrides)
    return base


def test_render_stats_formats_numbers_with_thousands_separators_and_sums_cache_writes(fs):
    out = fs.render_stats(stats(), None)
    assert "| claude-opus-5 | 1,000 | 2,000 | 3,000 | 45 |" in out, "w5 + w1 = 45"
    assert "~123,456 tokens" in out


def test_render_stats_orders_tool_counts_by_descending_frequency(fs):
    out = fs.render_stats(stats(), None)
    assert "Bash \u00d7 7, Read \u00d7 2" in out   # MULTIPLICATION SIGN, as the script emits


def test_render_stats_does_not_claim_the_usage_capture_outranks_the_jsonl(fs):
    """/usage's per-session block reports the window /usage itself ran in, so a capture taken
    after a resumed or re-entered session reads `$0.00 / 0 tokens` while the JSONL table is
    populated.  Measured on the 2026-07-31 session: $0.0000 and 0 tokens against 171k output and
    32.3M cache read.  A caption calling the capture "authoritative" would tell a reader to
    believe the zeros -- a document making its reader less accurate than no document."""
    out = fs.render_stats(stats(), "Total cost: $0.0000\nUsage: 0 input, 0 output")
    assert "authoritative" not in out
    assert "do not assume it wins" in out
    assert "| claude-opus-5 | 1,000 | 2,000 |" in out, "the populated table still renders"


def test_render_stats_says_so_when_usage_was_not_captured(fs):
    out = fs.render_stats(stats(), None)
    assert "not captured" in out
    assert "```" not in out.split("## Cost")[1].split("## Context")[0]


def test_render_stats_embeds_the_usage_capture_verbatim_in_a_fence(fs):
    out = fs.render_stats(stats(), "Current session: $1.23\nWeekly limit: 40%")
    assert "```\nCurrent session: $1.23\nWeekly limit: 40%\n```" in out
    assert "not captured" not in out


@pytest.mark.parametrize("blank", ["", "   \n  "])
def test_render_stats_treats_a_blank_usage_capture_as_not_captured(fs, blank):
    assert "not captured" in fs.render_stats(stats(), blank)


def test_render_stats_reports_duration_in_whole_minutes(fs):
    # fromisoformat, matching what the script's own _ts() produces: naive datetimes, because
    # Claude Code's JSONL timestamps carry no offset.
    out = fs.render_stats(stats(first=datetime.fromisoformat("2026-07-31T10:00:00"),
                                last=datetime.fromisoformat("2026-07-31T12:34:30")), None)
    assert "**Duration:** 154 min" in out, "2h34m30s truncates to 154, not 155"


def test_render_stats_omits_the_time_block_when_no_timestamps_were_found(fs):
    out = fs.render_stats(stats(), None)
    assert "**Started:**" not in out
    assert "**Model(s):**" in out, "the rest of the metadata still renders"


def test_render_stats_says_unknown_when_no_model_was_seen(fs):
    assert "**Model(s):** unknown" in fs.render_stats(stats(per_model={}), None)


# --- newest_jsonl() ---------------------------------------------------------------------------

def test_newest_jsonl_picks_the_most_recently_modified(fs, tmp_path, monkeypatch):
    home = tmp_path / "home"
    sessions = home / ".claude" / "projects" / "-workspace"
    sessions.mkdir(parents=True)
    old, new = sessions / "old.jsonl", sessions / "new.jsonl"
    old.write_text("{}\n", encoding="utf-8")
    new.write_text("{}\n", encoding="utf-8")
    os.utime(old, (1_000_000, 1_000_000))
    os.utime(new, (2_000_000, 2_000_000))
    monkeypatch.setenv("HOME", str(home))
    assert fs.newest_jsonl() == new


def test_newest_jsonl_exits_with_a_named_message_when_there_is_nothing_to_find(fs, tmp_path,
                                                                              monkeypatch):
    (tmp_path / ".claude" / "projects" / "-workspace").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(SystemExit, match="no session JSONL found"):
        fs.newest_jsonl()


# --- main(): the end-to-end contract ----------------------------------------------------------

def write_session(tmp_path, rows):
    path = tmp_path / "session.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def run_main(fs, monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["finalize-session.py", *argv])
    fs.main()


def test_main_writes_the_three_documents_and_scrubs_only_the_committed_ones(
        fs, tmp_path, monkeypatch, capsys):
    """The .raw.md is gitignored ON PURPOSE and keeps the unscrubbed text; transcript.md and
    statistics.md are the committed pair and must both be scrubbed.  A regression that scrubbed
    the raw file would be harmless; one that stopped scrubbing either committed file is a
    credential in git history."""
    jsonl = write_session(tmp_path, [
        {"type": "user", "message": {"content": "run it"}},
        {"type": "assistant", "requestId": "r1",
         "message": {"id": "m1", "model": "claude-opus-5", "usage": {"output_tokens": 3},
                     "content": [{"type": "text", "text": "SMTP_PASSWORD=hunter2-secret"}]}},
    ])
    out_dir = tmp_path / "development" / "2026-07-31-thing"
    run_main(fs, monkeypatch, ["--dir", str(out_dir), "--jsonl", str(jsonl)])

    scrubbed = (out_dir / "transcript.md").read_text(encoding="utf-8")
    raw = (out_dir / "transcript.raw.md").read_text(encoding="utf-8")
    statistics = (out_dir / "statistics.md").read_text(encoding="utf-8")
    assert "hunter2-secret" not in scrubbed
    assert "«REDACTED:SMTP_PASSWORD»" in scrubbed
    assert "hunter2-secret" in raw, "the raw copy is the gitignored unscrubbed one"
    assert "run it" in scrubbed
    assert "# Session statistics" in statistics
    printed = capsys.readouterr().out
    assert str(jsonl) in printed


def test_main_scrubs_the_statistics_document_too(fs, tmp_path, monkeypatch):
    """statistics.md embeds the /usage capture verbatim; if that paste carried a secret it must
    not reach the committed file."""
    jsonl = write_session(tmp_path, [{"type": "user", "message": {"content": "hi"}}])
    capture = tmp_path / "usage.raw.txt"
    capture.write_text("cost $1.00\nAKIAIOSFODNN7EXAMPLE\n", encoding="utf-8")
    out_dir = tmp_path / "out"
    run_main(fs, monkeypatch, ["--dir", str(out_dir), "--jsonl", str(jsonl),
                               "--usage-capture", str(capture)])
    statistics = (out_dir / "statistics.md").read_text(encoding="utf-8")
    assert "AKIAIOSFODNN7EXAMPLE" not in statistics
    assert "cost $1.00" in statistics


def test_main_suffixes_every_output_with_the_label(fs, tmp_path, monkeypatch):
    jsonl = write_session(tmp_path, [{"type": "user", "message": {"content": "hi"}}])
    out_dir = tmp_path / "out"
    run_main(fs, monkeypatch, ["--dir", str(out_dir), "--jsonl", str(jsonl), "--label", "02"])
    assert (out_dir / "transcript-02.md").exists()
    assert (out_dir / "transcript-02.raw.md").exists()
    assert (out_dir / "statistics-02.md").exists()
    assert not (out_dir / "transcript.md").exists(), "the unlabelled name must not also appear"


def test_main_creates_the_output_directory_including_parents(fs, tmp_path, monkeypatch):
    jsonl = write_session(tmp_path, [{"type": "user", "message": {"content": "hi"}}])
    out_dir = tmp_path / "a" / "b" / "c"
    run_main(fs, monkeypatch, ["--dir", str(out_dir), "--jsonl", str(jsonl)])
    assert (out_dir / "transcript.md").exists()


def test_main_uses_a_transcript_input_instead_of_rendering_the_jsonl_but_still_scrubs_it(
        fs, tmp_path, monkeypatch):
    jsonl = write_session(tmp_path, [
        {"type": "user", "message": {"content": "FROM THE JSONL"}}])
    export = tmp_path / "export.txt"
    export.write_text("FROM THE EXPORT\nSMTP_PASSWORD=hunter2-secret\n", encoding="utf-8")
    out_dir = tmp_path / "out"
    run_main(fs, monkeypatch, ["--dir", str(out_dir), "--jsonl", str(jsonl),
                               "--transcript-input", str(export)])
    scrubbed = (out_dir / "transcript.md").read_text(encoding="utf-8")
    assert "FROM THE EXPORT" in scrubbed
    assert "FROM THE JSONL" not in scrubbed
    assert "hunter2-secret" not in scrubbed


def test_main_falls_back_to_rendering_when_the_transcript_input_does_not_exist(
        fs, tmp_path, monkeypatch):
    """_read() returns None for a missing path, and the fallback is `is not None` -- so a typo'd
    --transcript-input silently renders the JSONL instead of failing."""
    jsonl = write_session(tmp_path, [{"type": "user", "message": {"content": "FROM THE JSONL"}}])
    out_dir = tmp_path / "out"
    run_main(fs, monkeypatch, ["--dir", str(out_dir), "--jsonl", str(jsonl),
                               "--transcript-input", str(tmp_path / "nope.txt")])
    assert "FROM THE JSONL" in (out_dir / "transcript.md").read_text(encoding="utf-8")


def test_main_requires_dir(fs, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["finalize-session.py"])
    with pytest.raises(SystemExit):
        fs.main()


# --- the module's own shape -------------------------------------------------------------------

def test_every_secret_pattern_compiles_and_carries_a_replacement(fs):
    """A malformed pattern would raise only when a matching line appeared, i.e. possibly never
    until the one session that carried a secret."""
    assert fs._SECRET_PATTERNS, "the scrubber must not be empty"
    for pattern, repl in fs._SECRET_PATTERNS:
        re.compile(pattern)
        assert callable(repl)


def test_the_script_imports_only_the_standard_library(fs):
    """Documented as 'stdlib only, no third-party deps' so /archive-session works in any
    environment -- including one where the project venv is not active."""
    source = SCRIPT.read_text(encoding="utf-8")
    imported = set(re.findall(r"^(?:import|from)\s+([a-zA-Z_][\w.]*)", source, re.MULTILINE))
    allowed = {"argparse", "contextlib", "json", "re", "datetime", "pathlib"}
    assert imported, "sanity: the regex found the import block at all"
    assert imported <= allowed, f"non-stdlib import: {imported - allowed}"

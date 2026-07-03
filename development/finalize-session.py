#!/usr/bin/env python
"""Finalize a Claude session for archiving under development/<date-slug>/.

Two deterministic jobs (kept in code, not left to LLM judgment):

  A. Render + scrub the transcript.  Read a Claude Code session JSONL, render it
     to readable markdown (development/<dir>/transcript.raw.md, gitignored), then
     write a secret-scrubbed copy (transcript.md, committed).

  B. Assemble statistics.md from the same JSONL (metadata, token usage, context)
     plus optional captures that only the /archive-session skill can gather in a
     live session (rtk gain, ctx-stats, and /usage for the dollar cost — Claude Code
     estimates cost locally, so we embed its /usage output instead of pricing here).

Standalone and testable: run it by hand against any session JSONL, or let the
/archive-session skill drive it.  Stdlib only, no third-party deps.

Usage:
  finalize-session.py --dir development/2026-07-03-daily-traffic-alerts \
      [--jsonl ~/.claude/projects/-workspace/<id>.jsonl] \
      [--rtk-capture <file>] [--ctx-capture <file>] [--usage-capture <file>] \
      [--transcript-input <export.txt>] [--label "01"]

--jsonl defaults to the newest *.jsonl under ~/.claude/projects/-workspace/.
--label suffixes the outputs (transcript-01.md / statistics-01.md) for
multi-session features; omit it for a single-session feature.
"""

import argparse
import glob
import json
import os
import re
from datetime import datetime

# Dollar cost is NOT computed here.  The session JSONL records no cost field, and
# there's no programmatic price source (the Models API returns capabilities, not
# prices).  Claude Code's own `/usage` already estimates cost locally from token
# counts — so rather than maintain a duplicate price table that goes stale, the
# /archive-session skill pastes `/usage` output in and this script embeds it
# verbatim (see --usage-capture).  Token counts below come straight from the JSONL.

# --- Secret scrubbing -------------------------------------------------------
# Best-effort regex redaction; development/README.md documents the manual grep
# that backs it up.  Each pattern keeps a label so the redaction is auditable.
_REDACT = "«REDACTED:{}»"
_SECRET_PATTERNS = [
    # KEY=value / KEY: value for the known secret env vars.  No leading \b: a
    # secret rendered right after an escaped newline (\nKEY=... in a JSON-encoded
    # command input) glues an `n` before the key and would defeat \b.
    (r"(?i)(SMTP_PASSWORD|AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|"
     r"CLOUDFLARE_API_KEY|CLOUDFLARE_EMAIL|ANTHROPIC_API_KEY)(\s*[=:]\s*)(\S+)",
     lambda m: m.group(1) + m.group(2) + _REDACT.format(m.group(1))),
    # AWS access key IDs
    (r"\bAKIA[0-9A-Z]{16}\b", lambda m: _REDACT.format("aws-key-id")),
    # Pantheon machine/session tokens in JSON
    (r'(?i)("?(?:machine_token|session)"?\s*[=:]\s*")([^"]{12,})(")',
     lambda m: m.group(1) + _REDACT.format("token") + m.group(3)),
    # Bearer / Authorization headers
    (r"(?i)(Authorization:\s*Bearer\s+|Bearer\s+)([A-Za-z0-9._\-]{12,})",
     lambda m: m.group(1) + _REDACT.format("bearer")),
    # PEM private key blocks
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
     lambda m: _REDACT.format("private-key")),
]


def scrub(text):
    for pattern, repl in _SECRET_PATTERNS:
        text = re.sub(pattern, repl, text, flags=re.DOTALL)
    return text


# --- JSONL loading ----------------------------------------------------------
def newest_jsonl():
    d = os.path.expanduser("~/.claude/projects/-workspace")
    files = glob.glob(os.path.join(d, "*.jsonl"))
    if not files:
        raise SystemExit(f"no session JSONL found under {d}; pass --jsonl")
    return max(files, key=os.path.getmtime)


def load(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def _blocks(msg):
    c = msg.get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return c if isinstance(c, list) else []


# --- Job A: render transcript ----------------------------------------------
def render_transcript(rows):
    out = ["# Session transcript\n"]
    for row in rows:
        rtype = row.get("type")
        if rtype not in ("user", "assistant"):
            continue
        msg = row.get("message")
        if not isinstance(msg, dict):
            continue
        tag = " _(subagent)_" if row.get("isSidechain") else ""
        for b in _blocks(msg):
            if not isinstance(b, dict):
                continue
            bt = b.get("type")
            if bt == "text" and b.get("text", "").strip():
                who = "User" if rtype == "user" else "Assistant"
                out.append(f"## {who}{tag}\n\n{b['text'].rstrip()}\n")
            elif bt == "thinking" and b.get("thinking", "").strip():
                out.append(f"## Assistant thinking{tag}\n\n{b['thinking'].rstrip()}\n")
            elif bt == "tool_use":
                inp = json.dumps(b.get("input", {}), indent=2, ensure_ascii=False)
                out.append(f"### ⚙ Tool call: `{b.get('name')}`{tag}\n\n"
                           f"```json\n{inp}\n```\n")
            elif bt == "tool_result":
                out.append(f"### ↳ Tool result{tag}\n\n```\n"
                           f"{_result_text(b.get('content'))}\n```\n")
    return "\n".join(out) + "\n"


def _result_text(content):
    if isinstance(content, str):
        return content.rstrip()
    if isinstance(content, list):
        parts = [x.get("text", "") for x in content
                 if isinstance(x, dict) and x.get("type") == "text"]
        return "\n".join(parts).rstrip()
    return ""


# --- Job B: statistics ------------------------------------------------------
def _ts(row):
    t = row.get("timestamp")
    if not t:
        return None
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        return None


def collect_stats(rows):
    # Claude Code writes ONE JSONL row per content block, so a single assistant
    # request spans several rows that all repeat the same `usage` block.  Summing
    # per-row would multiply tokens (~3x here) and turns.  So: dedupe usage per
    # request (keyed by requestId, falling back to message.id), but count tool_use
    # blocks per unique block id (each block appears on exactly one row).
    per_model = {}
    tools = {}
    seen_tool_ids = set()
    req_usage = {}   # request key -> (model, usage) — keep the row with max output
    first = last = None
    for row in rows:
        ts = _ts(row)
        if ts:
            first = first or ts
            last = ts
        if row.get("type") != "assistant":
            continue
        msg = row.get("message")
        if not isinstance(msg, dict):
            continue
        key = row.get("requestId") or msg.get("id") or id(row)
        u = msg.get("usage") or {}
        prev = req_usage.get(key)
        if prev is None or u.get("output_tokens", 0) > prev[1].get("output_tokens", 0):
            req_usage[key] = (msg.get("model", "unknown"), u)
        for b in _blocks(msg):
            if isinstance(b, dict) and b.get("type") == "tool_use":
                tid = b.get("id")
                if tid in seen_tool_ids:
                    continue
                seen_tool_ids.add(tid)
                tools[b.get("name", "?")] = tools.get(b.get("name", "?"), 0) + 1

    max_ctx = 0
    for model, u in req_usage.values():
        creation = u.get("cache_creation") or {}
        acc = per_model.setdefault(model, dict(inp=0, out=0, read=0, w5=0, w1=0))
        acc["inp"] += u.get("input_tokens", 0)
        acc["out"] += u.get("output_tokens", 0)
        acc["read"] += u.get("cache_read_input_tokens", 0)
        acc["w5"] += creation.get("ephemeral_5m_input_tokens", 0)
        acc["w1"] += creation.get("ephemeral_1h_input_tokens", 0)
        # Context approximation: the largest single prompt sent this session.
        prompt = (u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                  + u.get("cache_creation_input_tokens", 0))
        max_ctx = max(max_ctx, prompt)

    return dict(per_model=per_model, tools=tools, turns=len(req_usage),
                max_ctx=max_ctx, first=first, last=last)


def render_stats(s, rtk_text, ctx_text, usage_text):
    L = ["# Session statistics\n"]

    # Session metadata
    L.append("## Session metadata\n")
    if s["first"] and s["last"]:
        dur = s["last"] - s["first"]
        mins = int(dur.total_seconds() // 60)
        L.append(f"- **Started:** {s['first'].isoformat()}")
        L.append(f"- **Ended:** {s['last'].isoformat()}")
        L.append(f"- **Duration:** {mins} min")
    L.append(f"- **Model(s):** {', '.join(sorted(s['per_model'])) or 'unknown'}")
    L.append(f"- **Assistant turns:** {s['turns']}")
    if s["tools"]:
        counts = ", ".join(f"{k} × {v}" for k, v in
                           sorted(s["tools"].items(), key=lambda kv: -kv[1]))
        L.append(f"- **Tool calls:** {counts}")
    L.append("")

    # Token usage (from the JSONL)
    L.append("## Token usage\n")
    L.append("_Per-model totals from the session JSONL, deduped per request. "
             "**Approximate** — the JSONL is Claude Code's internal format; the "
             "embedded `/usage` below is authoritative for tokens and cost._\n")
    L.append("| Model | Input | Output | Cache read | Cache write |")
    L.append("|---|--:|--:|--:|--:|")
    for model, a in sorted(s["per_model"].items()):
        L.append(f"| {model} | {a['inp']:,} | {a['out']:,} | {a['read']:,} "
                 f"| {a['w5'] + a['w1']:,} |")
    L.append("")

    # Cost — pasted verbatim from Claude Code's /usage (no local price table)
    L.append("## Cost — Claude Code `/usage`\n")
    if usage_text and usage_text.strip():
        L.append("_Captured from Claude Code's `/usage` at archive time; Claude Code "
                 "estimates cost locally from token counts._\n")
        L.append("```\n" + usage_text.rstrip() + "\n```\n")
    else:
        L.append("_Run `/usage` in-session for the estimated cost — not captured "
                 "for this session._\n")

    # Context window (like /context) — approximation
    L.append("## Context window (approximate)\n")
    L.append(f"- **Largest prompt sent:** ~{s['max_ctx']:,} tokens "
             "(input + cache read + cache write on the biggest single turn)")
    L.append("\n_Approximate: reconstructed from the JSONL after the fact. The "
             "exact live `/context` breakdown by component can't be reproduced "
             "post-hoc._\n")

    # rtk gain (skill-supplied)
    L.append("## rtk gain\n")
    if rtk_text and rtk_text.strip():
        L.append(f"_Cumulative rtk savings captured at archive time._\n")
        L.append("```\n" + rtk_text.rstrip() + "\n```\n")
    else:
        L.append("_rtk not present / not captured for this session._\n")

    # context-mode (skill-supplied)
    L.append("## context-mode (/ctx-stats)\n")
    if ctx_text and ctx_text.strip():
        L.append("```\n" + ctx_text.rstrip() + "\n```\n")
    else:
        L.append("_context-mode not configured / not captured for this session._\n")

    return "\n".join(L) + "\n"


# --- main -------------------------------------------------------------------
def _read(path):
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True,
                    help="feature folder to write outputs into")
    ap.add_argument("--jsonl", help="session JSONL (default: newest)")
    ap.add_argument("--rtk-capture", help="file with `rtk gain` output")
    ap.add_argument("--ctx-capture", help="file with `/ctx-stats` output")
    ap.add_argument("--usage-capture", help="file with `/usage` output")
    ap.add_argument("--transcript-input",
                    help="pre-run /export text to scrub instead of rendering JSONL")
    ap.add_argument("--label", default="",
                    help="suffix for multi-session features, e.g. 01")
    args = ap.parse_args()

    os.makedirs(args.dir, exist_ok=True)
    sfx = f"-{args.label}" if args.label else ""

    jsonl = args.jsonl or newest_jsonl()
    rows = load(jsonl)

    # Job A: transcript
    override = _read(args.transcript_input)
    raw = override if override is not None else render_transcript(rows)
    raw_path = os.path.join(args.dir, f"transcript{sfx}.raw.md")
    with open(raw_path, "w", encoding="utf-8") as fh:
        fh.write(raw)
    scrubbed_path = os.path.join(args.dir, f"transcript{sfx}.md")
    with open(scrubbed_path, "w", encoding="utf-8") as fh:
        fh.write(scrub(raw))

    # Job B: statistics
    stats = collect_stats(rows)
    stats_md = render_stats(stats, _read(args.rtk_capture), _read(args.ctx_capture),
                            _read(args.usage_capture))
    stats_path = os.path.join(args.dir, f"statistics{sfx}.md")
    with open(stats_path, "w", encoding="utf-8") as fh:
        fh.write(scrub(stats_md))

    print(f"source JSONL: {jsonl}")
    print(f"wrote {scrubbed_path} (scrubbed) and {raw_path} (raw, gitignored)")
    print(f"wrote {stats_path}")


if __name__ == "__main__":
    main()

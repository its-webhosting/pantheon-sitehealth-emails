# `development/` — Claude session archive

This directory is a committed, **historical record** of how features were built with
Claude: the prompts used, the specs produced and hand-edited, scrubbed session
transcripts, and per-session statistics. It is a record of what was asked, discussed,
and decided — **not a primary source of documentation.** For how the code actually
works, read the code, the root `CLAUDE.md`, and `docs/`.

## Layout — one folder per feature

```
development/
  README.md                 # this file
  finalize-session.py       # renders+scrubs transcripts and builds statistics
  2026-07-03-daily-traffic-alerts/
    01-design.prompt.md      # input: the design prompt used
    design-notes/            # input: optional hand-authored design docs
    SPEC.md                  # generated spec/plan, then hand-edited
    02-implement.prompt.md   # input: the implementation prompt used
    transcript.md            # rendered + secret-scrubbed transcript (committed)
    statistics.md            # auto-generated session stats (committed; don't hand-edit)
    analytics.md             # your narrative analysis (optional, hand-written)
```

Conventions:
- **Folder name:** `YYYY-MM-DD-slug`, so folders sort chronologically. Prefer a slug
  that matches the relevant `README.md` TODO wording when the work maps to one.
- **Prompt ordering:** number prompt files `01-`, `02-`, … in the order they were used.
- **Fixed names:** `SPEC.md`, `transcript.md`, `statistics.md`, `analytics.md`.
- **Multiple sessions for one feature:** suffix the per-session files —
  `transcript-01.md` / `statistics-01.md`, `transcript-02.md`, … A single-session
  feature leaves them unsuffixed.
- **`statistics.md` is machine-generated** — don't hand-edit it. Put your own
  commentary in `analytics.md`.

## Two safety rules

1. **Transcripts are scrubbed of secrets before commit.** This repo's live secrets
   (`SMTP_PASSWORD`, the Pantheon machine token, `AWS_*`, `CLOUDFLARE_*`) flow through
   the environment and command output, so a raw transcript can leak credentials.
   `finalize-session.py` redacts the known patterns; as a backstop, before committing,
   eyeball with a **value-shaped** grep — it matches actual secret VALUES, not prose
   that merely mentions a key name (a session discussing `SMTP_PASSWORD` is fine; a
   `SMTP_PASSWORD=<value>` is not):
   ```
   grep -rnE '(SMTP_PASSWORD|AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|CLOUDFLARE_API_KEY|CLOUDFLARE_EMAIL)[[:space:]]*[=:][[:space:]]*[^[:space:]«]|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|Bearer [A-Za-z0-9._-]{12,}' development/<dir>/
   ```
2. **The raw session JSONL is never committed.** It's the data source for statistics,
   but it's bulky and secret-heavy. `.gitignore` blocks `development/**/*.jsonl`,
   `*.raw.md`, and `*.raw.txt` so raw exports/logs can't be committed by accident.

## End-to-end workflow

1. Create `development/<date-slug>/`; save the design prompt as `01-design.prompt.md`.
   The design run writes `SPEC.md` into that folder. (Per the project's
   `new-feature-standards.md`, the spec is written to the same directory
   as the initial prompt.)
2. Hand-edit `SPEC.md`; add any `design-notes/`.
3. Implement using the spec; save the implementation prompt as `02-implement.prompt.md`.
4. Run **`/archive-session`** (the skill). It renders + scrubs `transcript.md`, writes
   `statistics.md`, and scaffolds `analytics.md` — from the session JSONL plus the
   captured `/usage` output.
5. Optionally fill in `analytics.md`.
6. Ask Claude to commit everything — the code **and** `development/<date-slug>/` — in a
   single commit (Claude writes the message).

## `finalize-session.py`

The deterministic core the skill drives (also runnable by hand). It:
- renders the newest Claude Code session JSONL to readable markdown, writes the
  unscrubbed `transcript.raw.md` (gitignored), then the scrubbed `transcript.md`;
- assembles `statistics.md`: session metadata (duration, models, turns, tool-call
  counts), per-model token totals, an approximate context size, and the captured
  `/usage` section when present.

**No price table.** The JSONL records no cost and there's no programmatic price
source, so the script does not compute dollars. Instead the `/archive-session` skill
asks you to paste Claude Code's own `/usage` output (which estimates cost locally from
token counts) into `usage.raw.txt`, and the script embeds it verbatim. Nothing to keep
up to date here — Claude Code owns the pricing.

```
python development/finalize-session.py --dir development/<date-slug> \
    [--jsonl <path>] [--usage-capture <file>] \
    [--transcript-input <export.txt>] [--label NN]
```

`--transcript-input` scrubs a pre-run `/export` text instead of rendering the JSONL,
if you want Claude Code's official transcript formatting.

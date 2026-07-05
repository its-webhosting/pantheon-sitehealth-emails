# Session statistics

## Session metadata

- **Started:** 2026-07-05T17:52:35.293000+00:00
- **Ended:** 2026-07-05T20:30:36.873000+00:00
- **Duration:** 158 min
- **Model(s):** claude-opus-4-8
- **Assistant turns:** 279
- **Tool calls:** Edit × 90, Bash × 81, Read × 60, Write × 16, Agent × 10, AskUserQuestion × 4, ToolSearch × 3, mcp__plugin_context-mode_context-mode__ctx_index × 2, ExitPlanMode × 1, ReportFindings × 1, mcp__plugin_context-mode_context-mode__ctx_stats × 1

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-opus-4-8 | 34,708 | 283,135 | 79,523,571 | 1,691,973 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
Session

Total cost:            $75.88
Total duration (API):  1h 48m 36s
Total duration (wall): 2h 36m 50s
Total code changes:    2367 lines added, 335 lines removed
Usage by model:
     claude-opus-4-8:  125.2k input, 421.4k output, 85.5m cache read, 2.5m cache write ($75.87)
    claude-haiku-4-5:  1.1k input, 26 output, 0 cache read, 0 cache write ($0.0012)

Current session
████████████████████████████                       56% used
Resets 6:50pm (America/Detroit)

Current week (all models)
█████████                                          18% used
Resets Jul 7, 7pm (America/Detroit)

Current week (Fable)
                                                   0% used

What's contributing to your limits usage?
Approximate, based on local sessions on this machine — does not include other devices or claude.ai

Last 24h · these are independent characteristics of your usage, not a breakdown

99% of your usage came from subagent-heavy sessions
 Each subagent runs its own requests. Be deliberate about spawning them — and consider configuring a cheaper model for simpler subagents.

81% of your usage was at >150k context
 Longer sessions are more expensive even when cached. /compact mid-task, /clear when switching to new tasks.

Skills                  % of usage
/code-review                    6%
/context-mode:ctx-stats         4%
/archive-session                1%
/context-mode:ctx-index         1%

Subagents               % of usage
code-review                     5%
Explore                         4%
general-purpose                 3%

Plugins                 % of usage
context-mode                    4%

MCP servers             % of usage
plugin:context-mode:context…    6%
```

## Context window (approximate)

- **Largest prompt sent:** ~497,547 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._

## rtk gain

_Cumulative rtk savings captured at archive time._

```
RTK Token Savings (Global Scope)
════════════════════════════════════════════════════════════

Total commands:    132
Input tokens:      73.2K
Output tokens:     37.3K
Tokens saved:      35.9K (49.1%)
Total exec time:   5.3s (avg 40ms)
Efficiency meter: ████████████░░░░░░░░░░░░ 49.1%

By Command
───────────────────────────────────────────────────────────────────────
  #  Command                   Count  Saved    Avg%    Time  Impact    
───────────────────────────────────────────────────────────────────────
 1.  rtk grep                     73  17.0K   32.3%     1ms  ██████████
 2.  rtk read                     12  14.2K   29.4%     0ms  ████████░░
 3.  rtk pytest tests/unit...      1   1.2K   98.1%    2.3s  █░░░░░░░░░
 4.  rtk pytest tests/unit...      1   1.2K   98.1%    2.3s  █░░░░░░░░░
 5.  rtk ls -la .                  2    968   62.2%     4ms  █░░░░░░░░░
 6.  rtk git diff pantheon...      3    636    7.0%     8ms  ░░░░░░░░░░
 7.  rtk git diff --cached...      1    432   49.7%    11ms  ░░░░░░░░░░
 8.  rtk ls -la tests/e2e/...      2     92   70.2%     1ms  ░░░░░░░░░░
 9.  rtk git diff HEAD -- ...      1     65    1.7%    14ms  ░░░░░░░░░░
10.  rtk ls -la developmen...      1     47   72.3%     1ms  ░░░░░░░░░░
───────────────────────────────────────────────────────────────────────
```

## context-mode (/ctx-stats)

```
  Across 2 days you ran 8 conversations in Claude Code.
  context-mode kept 1.0 MB out of your context window — about 528 KB every single day.


  ─── 1. Where you are now ───

  This conversation started 5 Jul 2026 at 13:52 (America/Detroit) in /workspace.
  3 hr alive · still going.

  Without context-mode   13.8 MB  ████████████████████████████████      3.6M tokens
  With context-mode       294 KB  █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░     75.4K tokens
                          97.9% kept out of context · your AI ran 48× longer before /compact fired

  How that 14.5 MB built up — 1 days, 1 active:

  jul 4 █─────────────────────────────────────────────────────── jul 4

    jul 4    614 captures  ← peak

  ●  active day      █  peak day      ◆  /compact rescue


  ─── 2. What this chat captured (used when you --continue or /resume here) ───

  614 things — files, errors, decisions, agent runs:

    Files tracked                129   ████████████████████████████
    Data references              105   ███████████████████████░░░░░
    Constraints you set           57   ████████████░░░░░░░░░░░░░░░░
    External docs indexed         54   ████████████░░░░░░░░░░░░░░░░
    Environment setup             37   ████████░░░░░░░░░░░░░░░░░░░░
    Slow tools recorded           31   ███████░░░░░░░░░░░░░░░░░░░░░
    redirect                      30   ███████░░░░░░░░░░░░░░░░░░░░░
    sandbox                       30   ███████░░░░░░░░░░░░░░░░░░░░░
    Project rules (CLAUDE.md)     23   █████░░░░░░░░░░░░░░░░░░░░░░░
    Approaches you rejected       21   █████░░░░░░░░░░░░░░░░░░░░░░░
    cost                          15   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    session                       15   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    Agent insights kept           10   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Delegated work                10   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Working directory              9   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Errors caught                  8   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Plans drafted                  8   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Your messages remembered       7   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Your decisions                 5   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    Session intent                 5   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    Git operations                 4   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    session_start                  1   █░░░░░░░░░░░░░░░░░░░░░░░░░░░


  ─── 3. The scope, getting wider ───

  This chat: 14.5 MB kept out · 614 captures · started Jul 5, 2026.
  All your work: 1.0 MB kept out · 1,806 captures across 10 projects · since Jul 3, 2026.


  ─── 4. The bottom line ───

  $28.47 of Opus 4.7 tokens your team didn't burn.
  context-mode kept 1.0 MB out of context — that's 1 months of Cursor Pro paid for itself.

  Scale across a 10-dev team and that's ~$51,951/year saved.

  (Opus rates shown for context. On cheaper models the dollar number drops; the savings ratio holds.)


  ─── 5. What context-mode learned about how you work ───

  3 preferences picked up across 1 project:
    Long-term context           1   ████████████████████
    askuserquestion             1   ████████████████████
    no                          1   ████████████████████


  Your AI talks less, remembers more, costs less.
  Locale en-US · timezone America/Detroit · pricing examples for illustration only.

  v1.0.169
```


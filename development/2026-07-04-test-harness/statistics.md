# Session statistics

## Session metadata

- **Started:** 2026-07-04T11:47:59.102000+00:00
- **Ended:** 2026-07-04T17:49:50.903000+00:00
- **Duration:** 361 min
- **Model(s):** claude-opus-4-8
- **Assistant turns:** 149
- **Tool calls:** Edit × 51, Bash × 40, Write × 25, Read × 19, TaskUpdate × 15, Agent × 9, TaskCreate × 8, ToolSearch × 6, AskUserQuestion × 2, mcp__plugin_context-mode_context-mode__ctx_index × 1, ExitPlanMode × 1, ReportFindings × 1, mcp__plugin_context-mode_context-mode__ctx_stats × 1

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-opus-4-8 | 32,407 | 257,225 | 40,059,436 | 1,373,560 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
Session

Total cost:            $45.78
Total duration (API):  1h 39m 33s
Total duration (wall): 5h 58m 41s
Total code changes:    2488 lines added, 213 lines removed
Usage by model:
     claude-opus-4-8:  117.3k input, 402.5k output, 44.5m cache read, 1.5m cache write ($45.78)
    claude-haiku-4-5:  1.1k input, 27 output, 0 cache read, 0 cache write ($0.0012)

Current session
                                                   0% used

Current week (all models)
███▌                                               7% used
Resets Jul 7, 7pm (America/Detroit)

Current week (Fable)
                                                   0% used

What's contributing to your limits usage?
Approximate, based on local sessions on this machine — does not include other devices or claude.ai

Last 24h · these are independent characteristics of your usage, not a breakdown

99% of your usage came from subagent-heavy sessions
 Each subagent runs its own requests. Be deliberate about spawning them — and consider configuring a cheaper model for simpler subagents.

80% of your usage was at >150k context
 Longer sessions are more expensive even when cached. /compact mid-task, /clear when switching to new tasks.

19% of your usage came from MCP server "plugin:context-mode:context-mode"
 MCP tool results stay in context for the rest of the session. /compact to flush them, or disable servers you don't need.

Skills                  % of usage
/code-review                    6%
/context-mode:ctx-index         1%
/context-mode:ctx-stats         1%

Subagents               % of usage
Explore                         8%
code-review                     4%

Plugins                 % of usage
context-mode                    1%

MCP servers             % of usage
plugin:context-mode:context…   19%
```

## Context window (approximate)

- **Largest prompt sent:** ~462,628 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._

## rtk gain

_Cumulative rtk savings captured at archive time._

```
RTK Token Savings (Global Scope)
════════════════════════════════════════════════════════════

Total commands:    76
Input tokens:      120.9K
Output tokens:     20.1K
Tokens saved:      100.8K (83.4%)
Total exec time:   3.5s (avg 45ms)
Efficiency meter: ████████████████████░░░░ 83.4%

By Command
───────────────────────────────────────────────────────────────────────
  #  Command                   Count  Saved    Avg%    Time  Impact    
───────────────────────────────────────────────────────────────────────
 1.  rtk read                     10  82.2K   27.2%     0ms  ██████████
 2.  rtk grep                     33  15.8K   39.5%     2ms  ██░░░░░░░░
 3.  rtk git diff HEAD -- ...      1    732   31.6%    22ms  ░░░░░░░░░░
 4.  rtk git diff HEAD -- ...      1    647   30.2%    11ms  ░░░░░░░░░░
 5.  rtk ls -la .                  1    547   71.7%     5ms  ░░░░░░░░░░
 6.  rtk ls -la tests/             1    152   85.4%     2ms  ░░░░░░░░░░
 7.  rtk ls -la tests/fixt...      1    124   61.7%     1ms  ░░░░░░░░░░
 8.  rtk git status                1    115   51.6%    35ms  ░░░░░░░░░░
 9.  rtk ls -la tests/fixt...      1     97   40.4%     1ms  ░░░░░░░░░░
10.  rtk git diff HEAD -- ...      1     84   44.0%    10ms  ░░░░░░░░░░
───────────────────────────────────────────────────────────────────────
```

## context-mode (/ctx-stats)

```
  Across 1 days you ran 6 conversations in Claude Code.
  context-mode kept 433 KB out of your context window — about 433 KB every single day.


  ─── 1. Where you are now ───

  This conversation started 4 Jul 2026 at 07:47 (America/Detroit) in /workspace.
  6 hr alive · still going.

  Without context-mode    5.4 MB  ████████████████████████████████      1.4M tokens
  With context-mode       145 KB  █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░     37.0K tokens
                          97.4% kept out of context · your AI ran 38× longer before /compact fired

  How that 5.7 MB built up — 1 days, 1 active:

  jul 3 █─────────────────────────────────────────────────────── jul 3

    jul 3    484 captures  ← peak

  ●  active day      █  peak day      ◆  /compact rescue


  ─── 2. What this chat captured (used when you --continue or /resume here) ───

  484 things — files, errors, decisions, agent runs:

    Files tracked                119   ████████████████████████████
    Data references               73   █████████████████░░░░░░░░░░░
    Constraints you set           41   ██████████░░░░░░░░░░░░░░░░░░
    External docs indexed         36   ████████░░░░░░░░░░░░░░░░░░░░
    Tasks in progress             23   █████░░░░░░░░░░░░░░░░░░░░░░░
    Slow tools recorded           22   █████░░░░░░░░░░░░░░░░░░░░░░░
    redirect                      21   █████░░░░░░░░░░░░░░░░░░░░░░░
    sandbox                       19   ████░░░░░░░░░░░░░░░░░░░░░░░░
    Working directory             16   ████░░░░░░░░░░░░░░░░░░░░░░░░
    Errors caught                 15   ████░░░░░░░░░░░░░░░░░░░░░░░░
    cost                          13   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    session                       13   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    Approaches you rejected       11   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    Agent insights kept            9   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Delegated work                 9   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Project rules (CLAUDE.md)      8   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Your messages remembered       8   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Environment setup              7   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Git operations                 7   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Session intent                 6   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    Your decisions                 3   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    Plans drafted                  3   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    retrieval                      1   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    session_start                  1   █░░░░░░░░░░░░░░░░░░░░░░░░░░░


  ─── 3. The scope, getting wider ───

  This chat: 5.7 MB kept out · 484 captures · started Jul 4, 2026.
  All your work: 433 KB kept out · 667 captures across 7 projects · since Jul 3, 2026.


  ─── 4. The bottom line ───

  $10.73 of Opus 4.7 tokens your team didn't burn.
  context-mode kept 433 KB out of context — that's 1 months of Cursor Pro paid for itself.

  Scale across a 10-dev team and that's ~$39,154/year saved.

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


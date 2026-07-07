# Session statistics

## Session metadata

- **Started:** 2026-07-07T10:38:14.122000+00:00
- **Ended:** 2026-07-07T13:56:37.134000+00:00
- **Duration:** 198 min
- **Model(s):** claude-opus-4-8
- **Assistant turns:** 207
- **Tool calls:** Edit × 73, Bash × 49, Read × 41, TaskUpdate × 15, Write × 13, Agent × 12, TaskCreate × 9, ToolSearch × 4, AskUserQuestion × 2, ExitPlanMode × 2, mcp__plugin_context-mode_context-mode__ctx_index × 1, ReportFindings × 1, Skill × 1, mcp__plugin_context-mode_context-mode__ctx_stats × 1

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-opus-4-8 | 48,339 | 274,566 | 61,526,240 | 1,271,219 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```

 Session

 Total cost:            $61.79
 Total duration (API):  1h 37m 0s
 Total duration (wall): 3h 16m 0s
 Total code changes:    1872 lines added, 342 lines removed
 Usage by model:
      claude-opus-4-8:  163.6k input, 406.6k output, 66.4m cache read, 2.1m cache write ($61.79)
     claude-haiku-4-5:  1.1k input, 37 output, 0 cache read, 0 cache write ($0.0013)

 Current session
 █████████████████████████                          50% used
 Resets 11:29am (America/Detroit)

 Current week (all models)
 ███████████████▌                                   31% used
 Resets Jul 7, 6:59pm (America/Detroit)

 Current week (Fable)
                                                    0% used

 What's contributing to your limits usage?
 Approximate, based on local sessions on this machine — does not include other devices or claude.ai

 Last 24h · these are independent characteristics of your usage, not a breakdown

 97% of your usage came from subagent-heavy sessions
  Each subagent runs its own requests. Be deliberate about spawning them — and consider configuring a cheaper model for simpler subagents.

 73% of your usage was at >150k context
  Longer sessions are more expensive even when cached. /compact mid-task, /clear when switching to new tasks.

 Skills                  % of usage
 /code-review                    6%
 /context-mode:ctx-stats         4%
 /archive-session                2%
 /update-config                  1%
 /context-mode:ctx-index         1%

 Subagents               % of usage
code-review                     6%
general-purpose                 4%
Explore                         3%
superpowers:brainstorming       1%

Plugins                 % of usage
context-mode                    4%
superpowers                     1%

MCP servers             % of usage
plugin:context-mode:context…    2%
codegraph                       1%
```

## Context window (approximate)

- **Largest prompt sent:** ~536,589 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._

## rtk gain

_Cumulative rtk savings captured at archive time._

```
RTK Token Savings (Global Scope)
════════════════════════════════════════════════════════════

Total commands:    166
Input tokens:      211.0K
Output tokens:     49.6K
Tokens saved:      161.4K (76.5%)
Total exec time:   3.8s (avg 22ms)
Efficiency meter: ██████████████████░░░░░░ 76.5%

By Command
────────────────────────────────────────────────────────────────────────
  #  Command                   Count   Saved    Avg%    Time  Impact    
────────────────────────────────────────────────────────────────────────
 1.  rtk grep                    104  152.2K   30.6%    23ms  ██████████
 2.  rtk ls -la .                  5    2.5K   62.3%     3ms  ░░░░░░░░░░
 3.  rtk ls -la tests/             2    2.1K   70.3%     6ms  ░░░░░░░░░░
 4.  rtk git diff HEAD -- ...      1    1.8K   20.8%    35ms  ░░░░░░░░░░
 5.  rtk ls -la /workspace/        1     494   62.3%     2ms  ░░░░░░░░░░
 6.  rtk ls -la /workspace         1     494   62.3%     2ms  ░░░░░░░░░░
 7.  rtk read                     16     484    4.5%     0ms  ░░░░░░░░░░
 8.  rtk pytest tests/unit...      1     324   93.6%   481ms  ░░░░░░░░░░
 9.  rtk ls -la tests/unit/        2     292   64.5%     1ms  ░░░░░░░░░░
10.  rtk git diff prompts/...      1     222   13.3%    10ms  ░░░░░░░░░░
────────────────────────────────────────────────────────────────────────
```

## context-mode (/ctx-stats)

```
  Across 4 days you ran 26 conversations in Claude Code.
  context-mode kept 2.3 MB out of your context window — about 598 KB every single day.


  ─── 1. Where you are now ───

  This conversation started 7 Jul 2026 at 06:38 (America/Detroit) in /workspace.
  3 hr alive · still going.

  Without context-mode   23.2 MB  ████████████████████████████████      6.1M tokens
  With context-mode      82.9 KB  █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░     21.2K tokens
                          99.7% kept out of context · your AI ran 287× longer before /compact fired

  How that 25.5 MB built up — 1 days, 1 active:

  jul 6 █─────────────────────────────────────────────────────── jul 6

    jul 6    557 captures  ← peak

  ●  active day      █  peak day      ◆  /compact rescue


  ─── 2. What this chat captured (used when you --continue or /resume here) ───

  557 things — files, errors, decisions, agent runs:

    Files tracked                134   ████████████████████████████
    Data references               90   ███████████████████░░░░░░░░░
    Constraints you set           65   ██████████████░░░░░░░░░░░░░░
    Working directory             30   ██████░░░░░░░░░░░░░░░░░░░░░░
    redirect                      30   ██████░░░░░░░░░░░░░░░░░░░░░░
    Project rules (CLAUDE.md)     26   █████░░░░░░░░░░░░░░░░░░░░░░░
    Tasks in progress             24   █████░░░░░░░░░░░░░░░░░░░░░░░
    External docs indexed         22   █████░░░░░░░░░░░░░░░░░░░░░░░
    cost                          15   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    session                       15   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    Approaches you rejected       13   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    Agent insights kept           12   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    Delegated work                12   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    sandbox                       11   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Slow tools recorded           10   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Plans drafted                  9   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Your messages remembered       9   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Errors caught                  8   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Environment setup              6   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    Git operations                 6   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    Session intent                 5   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    Your decisions                 4   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    Skills used                    1   █░░░░░░░░░░░░░░░░░░░░░░░░░░░


  ─── 3. The scope, getting wider ───

  This chat: 25.5 MB kept out · 557 captures · started Jul 7, 2026.
  All your work: 2.3 MB kept out · 3,462 captures across 20 projects · since Jul 3, 2026.


  ─── 4. The bottom line ───

  $32.70 of Opus 4.7 tokens your team didn't burn.
  context-mode kept 2.3 MB out of context — that's 2 months of Cursor Pro paid for itself.

  Scale across a 10-dev team and that's ~$29,837/year saved.

  (Opus rates shown for context. On cheaper models the dollar number drops; the savings ratio holds.)


  ─── 5. What context-mode learned about how you work ───

  5 preferences picked up across 1 project:
    Long-term context           1   ████████████████████
    askuserquestion             1   ████████████████████
    browser                     1   ████████████████████
    no                          1   ████████████████████
    shared                      1   ████████████████████


  Your AI talks less, remembers more, costs less.
  Locale en-US · timezone America/Detroit · pricing examples for illustration only.

  v1.0.169
```


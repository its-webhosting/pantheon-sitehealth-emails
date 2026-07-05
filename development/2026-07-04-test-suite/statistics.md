# Session statistics

## Session metadata

- **Started:** 2026-07-04T22:20:16.851000+00:00
- **Ended:** 2026-07-05T14:08:17.157000+00:00
- **Duration:** 948 min
- **Model(s):** claude-opus-4-8
- **Assistant turns:** 178
- **Tool calls:** Bash × 45, Edit × 44, Read × 34, Write × 21, TaskUpdate × 20, TaskCreate × 10, Agent × 7, ToolSearch × 6, AskUserQuestion × 3, mcp__plugin_context-mode_context-mode__ctx_index × 2, ExitPlanMode × 1, SendMessage × 1, ReportFindings × 1, mcp__plugin_context-mode_context-mode__ctx_stats × 1

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-opus-4-8 | 47,157 | 282,683 | 52,822,078 | 1,171,225 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
Session

Total cost:            $54.32
Total duration (API):  1h 34m 51s
Total duration (wall): 15h 44m 5s
Total code changes:    2790 lines added, 268 lines removed
Usage by model:
     claude-opus-4-8:  121.5k input, 384.5k output, 57.6m cache read, 1.7m cache write ($54.32)
    claude-haiku-4-5:  1.1k input, 27 output, 0 cache read, 0 cache write ($0.0012)

Current session
█████████████▌                                     27% used
Resets 1:09pm (America/Detroit)

Current week (all models)
██████                                             12% used
Resets Jul 7, 6:59pm (America/Detroit)

Current week (Fable)
                                                   0% used

What's contributing to your limits usage?
Approximate, based on local sessions on this machine — does not include other devices or claude.ai

Last 24h · these are independent characteristics of your usage, not a breakdown

99% of your usage came from subagent-heavy sessions
 Each subagent runs its own requests. Be deliberate about spawning them — and consider configuring a cheaper model for simpler subagents.

85% of your usage was at >150k context
 Longer sessions are more expensive even when cached. /compact mid-task, /clear when switching to new tasks.

Skills                  % of usage
/code-review                    9%
/context-mode:ctx-stats         5%
/archive-session                2%

Subagents               % of usage
code-review                     5%
Explore                         3%
general-purpose                 1%

Plugins                 % of usage
context-mode                    6%

MCP servers             % of usage
plugin:context-mode:context…    4%
```

## Context window (approximate)

- **Largest prompt sent:** ~499,047 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._

## rtk gain

_Cumulative rtk savings captured at archive time._

```
RTK Token Savings (Global Scope)
════════════════════════════════════════════════════════════

Total commands:    40
Input tokens:      36.9K
Output tokens:     19.2K
Tokens saved:      17.6K (47.9%)
Total exec time:   338ms (avg 8ms)
Efficiency meter: ███████████░░░░░░░░░░░░░ 47.9%

By Command
───────────────────────────────────────────────────────────────────────
  #  Command                   Count  Saved    Avg%    Time  Impact    
───────────────────────────────────────────────────────────────────────
 1.  rtk read                      3  13.8K   86.9%     0ms  ██████████
 2.  rtk grep                     17   3.1K   32.4%     3ms  ██░░░░░░░░
 3.  rtk git diff pantheon...      3    636    7.0%     8ms  ░░░░░░░░░░
 4.  rtk git diff HEAD -- ...      1     65    1.7%    14ms  ░░░░░░░░░░
 5.  rtk ls -la tests/e2e/...      1     39   69.6%     1ms  ░░░░░░░░░░
 6.  rtk ls -la /home/node...      1     32   82.1%     1ms  ░░░░░░░░░░
 7.  rtk git diff --name-o...      1     26   45.6%    12ms  ░░░░░░░░░░
 8.  rtk wc -c tests/vendo...      1      6   75.0%     0ms  ░░░░░░░░░░
 9.  rtk git status --shor...      2      2    0.5%    15ms  ░░░░░░░░░░
10.  rtk proxy git diff HE...      1      0    0.0%    13ms  ░░░░░░░░░░
───────────────────────────────────────────────────────────────────────
```

## context-mode (/ctx-stats)

```
  Across 2 days you ran 7 conversations in Claude Code.
  context-mode kept 642 KB out of your context window — about 321 KB every single day.


  ─── 1. Where you are now ───

  This conversation started 4 Jul 2026 at 18:20 (America/Detroit) in /workspace.
  16 hr alive · still going.

  Without context-mode    8.2 MB  ████████████████████████████████      2.1M tokens
  With context-mode       237 KB  █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░     60.7K tokens
                          97.2% kept out of context · your AI ran 35× longer before /compact fired

  How that 8.6 MB built up — 2 days, 2 active:

  jul 3 ●──────────────────────────────────────────────────────█ jul 4

    jul 3    162 captures
    jul 4    312 captures  ← peak

  ●  active day      █  peak day      ◆  /compact rescue


  ─── 2. What this chat captured (used when you --continue or /resume here) ───

  474 things — files, errors, decisions, agent runs:

    Files tracked                110   ████████████████████████████
    Data references               68   █████████████████░░░░░░░░░░░
    Constraints you set           49   ████████████░░░░░░░░░░░░░░░░
    Tasks in progress             30   ████████░░░░░░░░░░░░░░░░░░░░
    Slow tools recorded           27   ███████░░░░░░░░░░░░░░░░░░░░░
    Working directory             24   ██████░░░░░░░░░░░░░░░░░░░░░░
    Errors caught                 24   ██████░░░░░░░░░░░░░░░░░░░░░░
    sandbox                       22   ██████░░░░░░░░░░░░░░░░░░░░░░
    External docs indexed         19   █████░░░░░░░░░░░░░░░░░░░░░░░
    redirect                      14   ████░░░░░░░░░░░░░░░░░░░░░░░░
    Approaches you rejected       14   ████░░░░░░░░░░░░░░░░░░░░░░░░
    cost                          13   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    session                       13   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    Agent insights kept            7   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Delegated work                 7   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Your messages remembered       7   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Project rules (CLAUDE.md)      6   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Git operations                 5   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    Session intent                 5   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    Your decisions                 3   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    Plans drafted                  3   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    retrieval                      2   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    Environment setup              1   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    session_start                  1   █░░░░░░░░░░░░░░░░░░░░░░░░░░░


  ─── 3. The scope, getting wider ───

  This chat: 8.6 MB kept out · 474 captures · started Jul 4, 2026.
  All your work: 642 KB kept out · 1,164 captures across 9 projects · since Jul 3, 2026.


  ─── 4. The bottom line ───

  $14.93 of Opus 4.7 tokens your team didn't burn.
  context-mode kept 642 KB out of context — that's 1 months of Cursor Pro paid for itself.

  Scale across a 10-dev team and that's ~$27,240/year saved.

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


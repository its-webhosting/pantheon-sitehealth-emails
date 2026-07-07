# Session statistics

## Session metadata

- **Started:** 2026-07-07T00:22:25.282000+00:00
- **Ended:** 2026-07-07T02:07:30.958000+00:00
- **Duration:** 105 min
- **Model(s):** claude-opus-4-8
- **Assistant turns:** 184
- **Tool calls:** Edit × 61, Bash × 36, Read × 29, TaskUpdate × 16, Write × 9, TaskCreate × 8, Agent × 6, ToolSearch × 5, AskUserQuestion × 2, Skill × 1, ExitPlanMode × 1, SendMessage × 1, ReportFindings × 1, mcp__plugin_context-mode_context-mode__ctx_stats × 1

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-opus-4-8 | 34,406 | 197,097 | 37,946,825 | 996,679 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```

 Session

 Total cost:            $40.58
 Total duration (API):  1h 10m 31s
 Total duration (wall): 1h 43m 5s
 Total code changes:    1458 lines added, 122 lines removed
 Usage by model:
     claude-haiku-4-5:  1.1k input, 28 output, 0 cache read, 0 cache write ($0.0012)
      claude-opus-4-8:  94.4k input, 290.7k output, 40.4m cache read, 1.4m cache write ($40.58)

 Current session
 █████████████████                                  34% used
 Resets 1:10am (America/Detroit)

 Current week (all models)
 ████████████▌                                      25% used
 Resets Jul 7, 7pm (America/Detroit)

 Current week (Fable)
                                                    0% used

 What's contributing to your limits usage?
 Approximate, based on local sessions on this machine — does not include other devices or claude.ai

 Last 24h · these are independent characteristics of your usage, not a breakdown

 83% of your usage came from subagent-heavy sessions
  Each subagent runs its own requests. Be deliberate about spawning them — and consider configuring a cheaper model for simpler subagents.

 54% of your usage was at >150k context
  Longer sessions are more expensive even when cached. /compact mid-task, /clear when switching to new tasks.

 Skills                  % of usage
 /code-review                    7%
 /context-mode:ctx-stats         6%
 /context-mode:ctx-index         1%
 /superpowers:brainstorming      1%

Subagents               % of usage
general-purpose                 4%
Explore                         4%
code-review                     3%
superpowers:brainstorming       2%

Plugins                 % of usage
context-mode                    6%
superpowers                     3%

MCP servers             % of usage
chrome-devtools                 2%
codegraph                       1%
plugin:context-mode:context…    1%
```

## Context window (approximate)

- **Largest prompt sent:** ~363,256 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._

## rtk gain

_Cumulative rtk savings captured at archive time._

```
RTK Token Savings (Global Scope)
════════════════════════════════════════════════════════════

Total commands:    99
Input tokens:      179.7K
Output tokens:     38.0K
Tokens saved:      141.7K (78.9%)
Total exec time:   2.5s (avg 25ms)
Efficiency meter: ███████████████████░░░░░ 78.9%

By Command
────────────────────────────────────────────────────────────────────────
  #  Command                   Count   Saved    Avg%    Time  Impact    
────────────────────────────────────────────────────────────────────────
 1.  rtk grep                     59  136.1K   31.1%    32ms  ██████████
 2.  rtk git diff HEAD -- ...      1    1.8K   20.8%    35ms  ░░░░░░░░░░
 3.  rtk ls -la .                  3    1.5K   62.3%     2ms  ░░░░░░░░░░
 4.  rtk ls -la /workspace/        1     494   62.3%     2ms  ░░░░░░░░░░
 5.  rtk ls -la /workspace         1     494   62.3%     2ms  ░░░░░░░░░░
 6.  rtk read                     12     484    6.1%     0ms  ░░░░░░░░░░
 7.  rtk pytest tests/unit...      1     324   93.6%   481ms  ░░░░░░░░░░
 8.  rtk ls -la tests/unit/        1     137   64.9%     1ms  ░░░░░░░░░░
 9.  rtk ls -la /workspace...      1      87   67.4%     1ms  ░░░░░░░░░░
10.  rtk ls -la .codegraph         1      87   67.4%     1ms  ░░░░░░░░░░
────────────────────────────────────────────────────────────────────────
```

## context-mode (/ctx-stats)

```
  Across 4 days you ran 24 conversations in Claude Code.
  context-mode kept 1.9 MB out of your context window — about 487 KB every single day.


  ─── 1. Where you are now ───

  This conversation started 6 Jul 2026 at 20:22 (America/Detroit) in /workspace.
  2 hr alive · still going.

  Without context-mode   18.7 MB  ████████████████████████████████      4.9M tokens
  With context-mode          1 B  █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░         1 tokens
                          100.0% kept out of context · your AI ran 4890338× longer before /compact fired

  How that 20.6 MB built up — 1 days, 1 active:

  jul 6 █─────────────────────────────────────────────────────── jul 6

    jul 6    374 captures  ← peak

  ●  active day      █  peak day      ◆  /compact rescue


  ─── 2. What this chat captured (used when you --continue or /resume here) ───

  374 things — files, errors, decisions, agent runs:

    Files tracked                100   ████████████████████████████
    Data references               63   ██████████████████░░░░░░░░░░
    Constraints you set           31   █████████░░░░░░░░░░░░░░░░░░░
    Slow tools recorded           24   ███████░░░░░░░░░░░░░░░░░░░░░
    Tasks in progress             24   ███████░░░░░░░░░░░░░░░░░░░░░
    External docs indexed         21   ██████░░░░░░░░░░░░░░░░░░░░░░
    Environment setup             17   █████░░░░░░░░░░░░░░░░░░░░░░░
    Errors caught                 12   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    Project rules (CLAUDE.md)     11   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    redirect                      10   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    cost                           9   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    session                        9   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    Working directory              8   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Agent insights kept            6   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Delegated work                 6   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Your messages remembered       6   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Approaches you rejected        5   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    Session intent                 4   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    Your decisions                 3   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    Git operations                 2   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    Plans drafted                  2   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    Skills used                    1   █░░░░░░░░░░░░░░░░░░░░░░░░░░░


  ─── 3. The scope, getting wider ───

  This chat: 20.6 MB kept out · 374 captures · started Jul 6, 2026.
  All your work: 1.9 MB kept out · 2,858 captures across 19 projects · since Jul 3, 2026.


  ─── 4. The bottom line ───

  $71.22 of Opus 4.7 tokens your team didn't burn.
  context-mode kept 1.9 MB out of context — that's 4 months of Cursor Pro paid for itself.

  Scale across a 10-dev team and that's ~$64,986/year saved.

  (Opus rates shown for context. On cheaper models the dollar number drops; the savings ratio holds.)


  ─── 5. What context-mode learned about how you work ───

  4 preferences picked up across 1 project:
    Long-term context           1   ████████████████████
    askuserquestion             1   ████████████████████
    browser                     1   ████████████████████
    no                          1   ████████████████████


  Your AI talks less, remembers more, costs less.
  Locale en-US · timezone America/Detroit · pricing examples for illustration only.

  v1.0.169
```


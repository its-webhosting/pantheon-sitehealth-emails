# Session statistics

## Session metadata

- **Started:** 2026-07-09T17:48:08.835000+00:00
- **Ended:** 2026-07-10T14:18:52.138000+00:00
- **Duration:** 1230 min
- **Model(s):** claude-opus-4-8
- **Assistant turns:** 89
- **Tool calls:** Bash × 33, Edit × 26, Agent × 15, Read × 14, Write × 3, ToolSearch × 3, mcp__plugin_context-mode_context-mode__ctx_index × 2, mcp__plugin_context-mode_context-mode__ctx_stats × 2, Skill × 1, ReportFindings × 1, mcp__plugin_context-mode_context-mode__ctx_search × 1

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-opus-4-8 | 42,579 | 54,075 | 9,797,105 | 493,935 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
Session

Total cost:            $73.19
Total duration (API):  2h 17m 15s
Total duration (wall): 1d 3h 29m
Total code changes:    1476 lines added, 247 lines removed
Usage by model:
    claude-haiku-4-5:  2.9k input, 106 output, 0 cache read, 0 cache write ($0.0034)
     claude-opus-4-8:  617.3k input, 502.8k output, 58.3m cache read, 3.7m cache write ($73.19)

   Current session
   ██████████                                         20% used
   Resets 2pm (America/Detroit)

   Current week (all models)
   █                                                  2% used
   Resets Jul 14, 7pm (America/Detroit)

   Current week (Fable)
                                                      0% used

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

Last 24h · these are independent characteristics of your usage, not a breakdown

87% of your usage came from subagent-heavy sessions
 Each subagent runs its own requests. Be deliberate about spawning them — and consider configuring a cheaper model for simpler subagents.

15% of your usage was at >150k context
 Longer sessions are more expensive even when cached. /compact mid-task, /clear when switching to new tasks.

35% of your usage came from subagents under "code-review"
 If this runs frequently, consider configuring its subagents with a cheaper model or tightening their prompts.

13% of your usage came from /superpowers:executing-plans
 Heavy skills can be scoped down or run with a cheaper model via skill frontmatter.

13% of your usage came from plugin "superpowers"
 Review what this plugin contributes — its agents, skills, and MCP tools all count toward your limit.


Skills                  % of usage
/superpowers:executing-plans   13%
/context-mode:ctx-index         7%
/code-review                    5%
/archive-session                4%
/context-mode:ctx-stats         2%

Subagents               % of usage
code-review                    35%

Plugins                 % of usage
superpowers                    13%
context-mode                    9%

MCP servers             % of usage
plugin:context-mode:context…    8%
```

## Context window (approximate)

- **Largest prompt sent:** ~182,068 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._

## rtk gain

_Cumulative rtk savings captured at archive time._

```
RTK Token Savings (Global Scope)
════════════════════════════════════════════════════════════

Total commands:    171
Input tokens:      311.7K
Output tokens:     217.9K
Tokens saved:      93.8K (30.1%)
Total exec time:   15.9s (avg 92ms)
Efficiency meter: ███████░░░░░░░░░░░░░░░░░ 30.1%

By Command
───────────────────────────────────────────────────────────────────────
  #  Command                   Count  Saved    Avg%    Time  Impact    
───────────────────────────────────────────────────────────────────────
 1.  rtk grep                     64  40.0K   26.0%   104ms  ██████████
 2.  rtk git diff HEAD~1           4  17.2K   41.5%   133ms  ████░░░░░░
 3.  rtk git diff HEAD             3  13.7K   25.0%    26ms  ███░░░░░░░
 4.  rtk read                     12   5.0K   15.0%     0ms  █░░░░░░░░░
 5.  rtk pytest tests/inte...      1   3.4K   99.4%    5.0s  █░░░░░░░░░
 6.  rtk git diff HEAD -- ...      3   2.3K   14.5%    22ms  █░░░░░░░░░
 7.  rtk git diff HEAD -- ...      1   1.6K   45.8%     9ms  ░░░░░░░░░░
 8.  rtk git diff HEAD -- ...      1   1.3K   11.2%   161ms  ░░░░░░░░░░
 9.  rtk git diff HEAD -- ...      1   1.2K   17.2%    17ms  ░░░░░░░░░░
10.  rtk git diff check/cl...      1   1.2K   17.2%    36ms  ░░░░░░░░░░
───────────────────────────────────────────────────────────────────────
```

## context-mode (/ctx-stats)

```
  Across 7 days you ran 35 conversations in Claude Code.
  context-mode kept 4.8 MB out of your context window — about 708 KB every single day.


  ─── 1. Where you are now ───

  This conversation started 9 Jul 2026 at 13:48 (America/Detroit) in /workspace.
  20 hr alive · still going.

  Without context-mode   33.7 MB  ████████████████████████████████      8.8M tokens
  With context-mode       113 KB  █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░     29.0K tokens
                          99.7% kept out of context · your AI ran 305× longer before /compact fired

  How that 38.4 MB built up — 2 days, 2 active:

  jul 8 ●──────────────────────────────────────────────────────█ jul 9

    jul 8    55 captures
    jul 9    233 captures  ← peak

  ●  active day      █  peak day      ◆  /compact rescue


  ─── 2. What this chat captured (used when you --continue or /resume here) ───

  288 things — files, errors, decisions, agent runs:

    Data references               49   ████████████████████████████
    Constraints you set           36   █████████████████████░░░░░░░
    Files tracked                 35   ████████████████████░░░░░░░░
    Errors caught                 18   ██████████░░░░░░░░░░░░░░░░░░
    Approaches you rejected       16   █████████░░░░░░░░░░░░░░░░░░░
    Agent insights kept           15   █████████░░░░░░░░░░░░░░░░░░░
    Git operations                15   █████████░░░░░░░░░░░░░░░░░░░
    sandbox                       15   █████████░░░░░░░░░░░░░░░░░░░
    Delegated work                15   █████████░░░░░░░░░░░░░░░░░░░
    redirect                      13   ███████░░░░░░░░░░░░░░░░░░░░░
    External docs indexed         12   ███████░░░░░░░░░░░░░░░░░░░░░
    Environment setup             11   ██████░░░░░░░░░░░░░░░░░░░░░░
    Slow tools recorded            8   █████░░░░░░░░░░░░░░░░░░░░░░░
    Your messages remembered       8   █████░░░░░░░░░░░░░░░░░░░░░░░
    cost                           7   ████░░░░░░░░░░░░░░░░░░░░░░░░
    session                        7   ████░░░░░░░░░░░░░░░░░░░░░░░░
    Session intent                 6   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    retrieval                      1   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    Skills used                    1   █░░░░░░░░░░░░░░░░░░░░░░░░░░░


  ─── 3. The scope, getting wider ───

  This chat: 38.4 MB kept out · 288 captures · started Jul 9, 2026.
  All your work: 4.8 MB kept out · 5,810 captures across 26 projects · since Jul 3, 2026.


  ─── 4. The bottom line ───

  $51.65 of Opus 4.7 tokens your team didn't burn.
  context-mode kept 4.8 MB out of context — that's 3 months of Cursor Pro paid for itself.

  Scale across a 10-dev team and that's ~$26,933/year saved.

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


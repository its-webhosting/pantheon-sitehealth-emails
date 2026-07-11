# Session statistics

## Session metadata

- **Started:** 2026-07-10T19:55:01.896000+00:00
- **Ended:** 2026-07-11T15:41:35.076000+00:00
- **Duration:** 1186 min
- **Model(s):** claude-opus-4-8
- **Assistant turns:** 174
- **Tool calls:** Bash × 56, Edit × 46, Read × 20, Agent × 17, Write × 9, AskUserQuestion × 6, Skill × 5, ToolSearch × 3, mcp__plugin_context-mode_context-mode__ctx_index × 2, mcp__plugin_context-mode_context-mode__ctx_search × 1, mcp__codegraph__codegraph_explore × 1, ReportFindings × 1, mcp__plugin_context-mode_context-mode__ctx_stats × 1

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-opus-4-8 | 29,181 | 332,409 | 54,326,651 | 1,305,899 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $66.91
   Total duration (API):  2h 0m 9s
   Total duration (wall): 19h 43m 53s
   Total code changes:    3329 lines added, 213 lines removed
   Usage by model:
        claude-opus-4-8:  94.1k input, 454.6k output, 63.5m cache read, 2.0m cache write ($61.13)
       claude-haiku-4-5:  590 input, 23 output, 0 cache read, 0 cache write ($0.0007)
        claude-sonnet-5:  120.4k input, 83.1k output, 6.8m cache read, 569.8k cache write ($5.78)

   Current session
   ████████████████████████████                       56% used
   Resets 1:20pm (America/Detroit)

   Current week (all models)
   ████▌                                              9% used
   Resets Jul 14, 7pm (America/Detroit)

   Current week (Fable)
                                                      0% used

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   86% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   60% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   14% of your usage came from subagents under
   "superpowers:subagent-driven-development"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   14% of your usage came from /superpowers:subagent-driven-development
    Heavy skills can be scoped down or run with a cheaper model via skill
    frontmatter.

   46% of your usage came from plugin "superpowers"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   Skills                  % of usage
   /superpowers:subagent-drive…   14%
   /superpowers:systematic-deb…    7%
   /context-mode:ctx-stats         6%
   /superpowers:finishing-a-de…    4%
   /superpowers:writing-plans      4%
   /superpowers:brainstorming      4%
   /archive-session                3%
   /code-review                    3%
   … 1 more

   Subagents               % of usage
   superpowers:subagent-driven…   14%
   general-purpose                 6%

   Plugins                 % of usage
   superpowers                    46%
   context-mode                    6%

   MCP servers             % of usage
   codegraph                       3%
   plugin:context-mode:context…    2%
```

## Context window (approximate)

- **Largest prompt sent:** ~546,887 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._

## rtk gain

_Cumulative rtk savings captured at archive time._

```
RTK Token Savings (Global Scope)
════════════════════════════════════════════════════════════

Total commands:    188
Input tokens:      98.2K
Output tokens:     75.8K
Tokens saved:      22.4K (22.8%)
Total exec time:   11.8s (avg 62ms)
Efficiency meter: █████░░░░░░░░░░░░░░░░░░░ 22.8%

By Command
───────────────────────────────────────────────────────────────────────
  #  Command                   Count  Saved    Avg%    Time  Impact    
───────────────────────────────────────────────────────────────────────
 1.  rtk grep                     65  15.2K   33.1%     9ms  ██████████
 2.  rtk pytest tests/unit...      1   2.8K   99.2%    4.1s  ██░░░░░░░░
 3.  rtk:toml ps aux               1    679   49.8%    10ms  ░░░░░░░░░░
 4.  rtk ls -la .                  1    504   62.4%     2ms  ░░░░░░░░░░
 5.  rtk ls -la tests/unit...      1    474   60.3%     2ms  ░░░░░░░░░░
 6.  rtk ls -la tests/unit         2    438   61.0%     1ms  ░░░░░░░░░░
 7.  rtk git status                7    369   58.5%    91ms  ░░░░░░░░░░
 8.  rtk ls -la tests/inte...      1    253   59.1%     1ms  ░░░░░░░░░░
 9.  rtk git diff CLAUDE.md        1    238   18.6%    17ms  ░░░░░░░░░░
10.  rtk pytest tests/unit...      2    230   83.9%    1.1s  ░░░░░░░░░░
───────────────────────────────────────────────────────────────────────
```

## context-mode (/ctx-stats)

```
  Across 7 days you ran 36 conversations in Claude Code.
  context-mode kept 5.3 MB out of your context window — about 769 KB every single day.


  ─── 1. Where you are now ───

  This conversation started 10 Jul 2026 at 15:55 (America/Detroit) in /workspace.
  20 hr alive · still going.

  Without context-mode   31.8 MB  ████████████████████████████████      8.3M tokens
  With context-mode      43.9 KB  █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░     11.2K tokens
                          99.9% kept out of context · your AI ran 742× longer before /compact fired

  How that 37.0 MB built up — 2 days, 2 active:

  jul 9 ●──────────────────────────────────────────────────────█ jul 10

    jul 9    73 captures
    jul 10   742 captures  ← peak

  ●  active day      █  peak day      ◆  /compact rescue


  ─── 2. What this chat captured (used when you --continue or /resume here) ───

  815 things — files, errors, decisions, agent runs:

    Files tracked                141   ████████████████████████████
    Data references              130   ██████████████████████████░░
    External docs indexed        103   ████████████████████░░░░░░░░
    Constraints you set           83   ████████████████░░░░░░░░░░░░
    Git operations                53   ███████████░░░░░░░░░░░░░░░░░
    Errors caught                 49   ██████████░░░░░░░░░░░░░░░░░░
    Slow tools recorded           42   ████████░░░░░░░░░░░░░░░░░░░░
    Environment setup             37   ███████░░░░░░░░░░░░░░░░░░░░░
    Working directory             30   ██████░░░░░░░░░░░░░░░░░░░░░░
    Approaches you rejected       22   ████░░░░░░░░░░░░░░░░░░░░░░░░
    redirect                      19   ████░░░░░░░░░░░░░░░░░░░░░░░░
    Agent insights kept           17   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    Delegated work                17   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    Project rules (CLAUDE.md)     12   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Your messages remembered      12   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    cost                          11   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    session                       11   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Your decisions                 8   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Session intent                 6   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    sandbox                        5   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    Skills used                    5   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    retrieval                      1   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    session_start                  1   █░░░░░░░░░░░░░░░░░░░░░░░░░░░


  ─── 3. The scope, getting wider ───

  This chat: 37.0 MB kept out · 815 captures · started Jul 10, 2026.
  All your work: 5.3 MB kept out · 6,113 captures across 27 projects · since Jul 4, 2026.


  ─── 4. The bottom line ───

  $49.89 of Opus 4.7 tokens your team didn't burn.
  context-mode kept 5.3 MB out of context — that's 2 months of Cursor Pro paid for itself.

  Scale across a 10-dev team and that's ~$26,015/year saved.

  (Opus rates shown for context. On cheaper models the dollar number drops; the savings ratio holds.)


  ─── 5. What context-mode learned about how you work ───

  8 preferences picked up across 1 project:
    Long-term context           1   ████████████████████
    askuserquestion             1   ████████████████████
    browser                     1   ████████████████████
    dns                         1   ████████████████████
    hook                        1   ████████████████████
    no                          1   ████████████████████
    reset                       1   ████████████████████
    shared                      1   ████████████████████


  Your AI talks less, remembers more, costs less.
  Locale en-US · timezone America/Detroit · pricing examples for illustration only.

  v1.0.169
```


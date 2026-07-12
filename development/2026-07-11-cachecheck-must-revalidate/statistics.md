# Session statistics

## Session metadata

- **Started:** 2026-07-12T00:46:39.587000+00:00
- **Ended:** 2026-07-12T03:56:01.314000+00:00
- **Duration:** 189 min
- **Model(s):** claude-opus-4-8
- **Assistant turns:** 227
- **Tool calls:** Bash × 95, Edit × 48, Read × 25, Agent × 15, Write × 11, AskUserQuestion × 9, Skill × 6, mcp__plugin_cloudflare_cloudflare-docs__search_cloudflare_documentation × 3, ToolSearch × 2, ReportFindings × 1, mcp__plugin_context-mode_context-mode__ctx_stats × 1

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-opus-4-8 | 447 | 199,758 | 53,162,859 | 461,162 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $50.16
   Total duration (API):  1h 16m 2s
   Total duration (wall): 3h 7m 45s
   Total code changes:    1938 lines added, 749 lines removed
   Usage by model:
       claude-haiku-4-5:  615 input, 9.0k output, 354.4k cache read, 44.5k cache write ($0.1366)
        claude-opus-4-8:  18.2k input, 294.3k output, 60.2m cache read, 1.1m cache write ($46.05)
        claude-sonnet-5:  4.8k input, 47.5k output, 5.9m cache read, 389.9k cache write ($3.97)

   Current session
   ████████████████                                   32% used
   Resets 1:39am (America/Detroit)

   Current week (all models)
   ██████▌                                            13% used
   Resets Jul 14, 6:59pm (America/Detroit)

   Current week (Fable)
                                                      0% used

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   94% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   69% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   12% of your usage came from subagents under
   "superpowers:subagent-driven-development"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   12% of your usage came from /superpowers:subagent-driven-development
    Heavy skills can be scoped down or run with a cheaper model via skill
    frontmatter.

   35% of your usage came from plugin "superpowers"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   11% of your usage came from MCP server "plugin:cloudflare:cloudflare-docs"
    MCP tool results stay in context for the rest of the session. /compact to flush
    them, or disable servers you don't need.

   Skills                  % of usage
   /superpowers:subagent-drive…   12%
   /superpowers:systematic-deb…    7%
   /context-mode:ctx-stats         4%
   /archive-session                4%
   /code-review                    3%
   /superpowers:finishing-a-de…    2%
   /claude-md-management:claud…    2%
   /superpowers:brainstorming      2%
   … 1 more

   Subagents               % of usage
   superpowers:subagent-driven…   12%
   general-purpose                 6%
   claude-md-management:claude…    2%

   Plugins                 % of usage
   superpowers                    35%
   context-mode                    4%
   claude-md-management            4%

   MCP servers             % of usage
   plugin:cloudflare:cloudflar…   11%
   plugin:context-mode:context…    2%
```

## Context window (approximate)

- **Largest prompt sent:** ~419,284 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._

## rtk gain

_Cumulative rtk savings captured at archive time._

```
RTK Token Savings (Global Scope)
════════════════════════════════════════════════════════════

Total commands:    223
Input tokens:      549.5K
Output tokens:     114.0K
Tokens saved:      435.5K (79.3%)
Total exec time:   1m45s (avg 475ms)
Efficiency meter: ███████████████████░░░░░ 79.3%

By Command
────────────────────────────────────────────────────────────────────────
  #  Command                   Count   Saved    Avg%    Time  Impact    
────────────────────────────────────────────────────────────────────────
 1.  rtk grep                     87  407.2K   28.4%   400ms  ██████████
 2.  rtk pytest tests/unit...      1   12.1K   99.8%   14.1s  ░░░░░░░░░░
 3.  rtk pytest tests/unit...      1    4.7K   99.5%    6.1s  ░░░░░░░░░░
 4.  rtk pytest tests/unit...      1    2.9K   99.2%    4.1s  ░░░░░░░░░░
 5.  rtk pytest tests/unit...      1    2.9K   99.2%    4.2s  ░░░░░░░░░░
 6.  rtk ls -la .                  2    1.2K   72.2%     2ms  ░░░░░░░░░░
 7.  rtk:toml ps aux               1    1.1K   62.3%    11ms  ░░░░░░░░░░
 8.  rtk git diff tests/in...      1     580   26.6%    13ms  ░░░░░░░░░░
 9.  rtk pytest tests/inte...      1     577   96.3%    1.5s  ░░░░░░░░░░
10.  rtk ls -la /workspace...      2     419   53.7%     3ms  ░░░░░░░░░░
────────────────────────────────────────────────────────────────────────
```

## context-mode (/ctx-stats)

```
  Across 6 days you ran 36 conversations in Claude Code.
  context-mode kept 5.8 MB out of your context window — about 994 KB every single day.


  ─── 1. Where you are now ───

  This conversation started 11 Jul 2026 at 20:46 (America/Detroit) in /workspace.
  3 hr alive · still going.

  Without context-mode   29.6 MB  ████████████████████████████████      7.8M tokens
  With context-mode       110 KB  █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░     28.3K tokens
                          99.6% kept out of context · your AI ran 275× longer before /compact fired

  How that 35.3 MB built up — 1 days, 1 active:

  jul 11 █─────────────────────────────────────────────────────── jul 11

    jul 11   796 captures  ← peak

  ●  active day      █  peak day      ◆  /compact rescue


  ─── 2. What this chat captured (used when you --continue or /resume here) ───

  796 things — files, errors, decisions, agent runs:

    Data references              130   ████████████████████████████
    External docs indexed        127   ███████████████████████████░
    Files tracked                127   ███████████████████████████░
    Constraints you set           83   ██████████████████░░░░░░░░░░
    Errors caught                 54   ████████████░░░░░░░░░░░░░░░░
    Slow tools recorded           45   ██████████░░░░░░░░░░░░░░░░░░
    Environment setup             37   ████████░░░░░░░░░░░░░░░░░░░░
    Git operations                37   ████████░░░░░░░░░░░░░░░░░░░░
    Project rules (CLAUDE.md)     28   ██████░░░░░░░░░░░░░░░░░░░░░░
    Approaches you rejected       18   ████░░░░░░░░░░░░░░░░░░░░░░░░
    Agent insights kept           15   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    Delegated work                15   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    Your messages remembered      12   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    cost                          11   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Your decisions                11   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    session                       11   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Working directory             10   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    sandbox                       10   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Session intent                 7   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Skills used                    5   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    redirect                       2   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    session_start                  1   █░░░░░░░░░░░░░░░░░░░░░░░░░░░


  ─── 3. The scope, getting wider ───

  This chat: 35.3 MB kept out · 796 captures · started Jul 11, 2026.
  All your work: 5.8 MB kept out · 6,513 captures across 30 projects · since Jul 5, 2026.


  ─── 4. The bottom line ───

  $48.15 of Opus 4.7 tokens your team didn't burn.
  context-mode kept 5.8 MB out of context — that's 2 months of Cursor Pro paid for itself.

  Scale across a 10-dev team and that's ~$29,288/year saved.

  (Opus rates shown for context. On cheaper models the dollar number drops; the savings ratio holds.)


  ─── 5. What context-mode learned about how you work ───

  10 preferences picked up across 1 project:
    Long-term context           1   ████████████████████
    askuserquestion             1   ████████████████████
    browser                     1   ████████████████████
    cloudflare                  1   ████████████████████
    dns                         1   ████████████████████
    fix                         1   ████████████████████
    hook                        1   ████████████████████
    no                          1   ████████████████████
    reset                       1   ████████████████████
    shared                      1   ████████████████████


  Your AI talks less, remembers more, costs less.
  Locale en-US · timezone America/Detroit · pricing examples for illustration only.

  v1.0.169
```


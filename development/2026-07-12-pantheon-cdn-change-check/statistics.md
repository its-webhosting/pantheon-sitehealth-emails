# Session statistics

## Session metadata

- **Started:** 2026-07-12T17:45:40.047000+00:00
- **Ended:** 2026-07-13T00:40:01.041000+00:00
- **Duration:** 414 min
- **Model(s):** claude-opus-4-8
- **Assistant turns:** 309
- **Tool calls:** Bash × 133, Edit × 77, Read × 40, Agent × 32, Write × 12, AskUserQuestion × 9, Skill × 3, mcp__plugin_context-mode_context-mode__ctx_execute × 2, ReportFindings × 1, mcp__plugin_context-mode_context-mode__ctx_stats × 1

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-opus-4-8 | 595 | 392,068 | 133,200,923 | 1,757,851 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $133.70
   Total duration (API):  2h 58m 39s
   Total duration (wall): 6h 52m 22s
   Total code changes:    8590 lines added, 1668 lines removed
   Usage by model:
       claude-haiku-4-5:  537 input, 16 output, 0 cache read, 0 cache write ($0.0006)
        claude-opus-4-8:  26.3k input, 580.4k output, 153.7m cache read, 2.6m cache write ($114.42)
        claude-sonnet-5:  19.0k input, 285.5k output, 28.4m cache read, 1.7m cache write ($19.28)

   Current session
   █████▌                                             11% used
   Resets 11:19pm (America/Detroit)

   Current week (all models)
   ██████████▌                                        21% used
   Resets Jul 14, 6:59pm (America/Detroit)

   Current week (Fable)
                                                      0% used

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   93% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   67% of your usage came from sessions active for 8+ hours
    These are often background/loop sessions. Continuous usage can add up quickly
    so make sure it is intentional.

   67% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   15% of your usage came from subagents under
   "superpowers:subagent-driven-development"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   20% of your usage came from /superpowers:subagent-driven-development
    Heavy skills can be scoped down or run with a cheaper model via skill
    frontmatter.

   41% of your usage came from plugin "superpowers"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   11% of your usage came from MCP server "plugin:context-mode:context-mode"
    MCP tool results stay in context for the rest of the session. /compact to flush
    them, or disable servers you don't need.

   Skills                  % of usage
   /superpowers:subagent-drive…   20%
   /archive-session                4%
   /code-review                    3%
   /superpowers:systematic-deb…    3%
   /superpowers:writing-plans      2%
   /superpowers:brainstorming      2%
   /claude-md-management:claud…    1%

   Subagents               % of usage
   superpowers:subagent-driven…   15%
   general-purpose                 6%
   claude-md-management:claude…    1%

   Plugins                 % of usage
   superpowers                    41%
   claude-md-management            2%
   context-mode                    1%

   MCP servers             % of usage
   plugin:context-mode:context…   11%
   plugin:cloudflare:cloudflar…    7%
```

## Context window (approximate)

- **Largest prompt sent:** ~667,651 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._

## rtk gain

_Cumulative rtk savings captured at archive time._

```
RTK Token Savings (Global Scope)
════════════════════════════════════════════════════════════

Total commands:    538
Input tokens:      210.3K
Output tokens:     161.6K
Tokens saved:      48.8K (23.2%)
Total exec time:   9.2s (avg 17ms)
Efficiency meter: ██████░░░░░░░░░░░░░░░░░░ 23.2%

By Command
───────────────────────────────────────────────────────────────────────
  #  Command                   Count  Saved    Avg%    Time  Impact    
───────────────────────────────────────────────────────────────────────
 1.  rtk grep                    180  28.7K   26.3%     9ms  ██████████
 2.  rtk:toml ps aux               6   7.4K   61.8%    13ms  ███░░░░░░░
 3.  rtk diff                      1   1.3K   89.5%     1ms  ░░░░░░░░░░
 4.  rtk ls -la /workspace...      4   1.2K   51.3%     3ms  ░░░░░░░░░░
 5.  rtk ls -la check/ che...      1   1.1K   69.6%     4ms  ░░░░░░░░░░
 6.  rtk ls -la /workspace...      1    706   64.5%     5ms  ░░░░░░░░░░
 7.  rtk ls -la .                  1    595   72.2%     6ms  ░░░░░░░░░░
 8.  rtk git diff bb5206b....      1    505   17.5%    39ms  ░░░░░░░░░░
 9.  rtk ls -la /workspace...      6    496   75.7%     1ms  ░░░░░░░░░░
10.  rtk git show HEAD -- ...      1    393   53.3%    32ms  ░░░░░░░░░░
───────────────────────────────────────────────────────────────────────
```

## context-mode (/ctx-stats)

```
  Across 7 days you ran 40 conversations in Claude Code.
  context-mode kept 7.0 MB out of your context window — about 1024 KB every single day.


  ─── 1. Where you are now ───

  This conversation started 12 Jul 2026 at 13:46 (America/Detroit) in /workspace.
  7 hr alive · still going.

  Without context-mode   30.2 MB  ████████████████████████████████      7.9M tokens
  With context-mode          1 B  █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░         1 tokens
                          100.0% kept out of context · your AI ran 7920949× longer before /compact fired

  How that 37.2 MB built up — 1 days, 2 active:

  jul 11 █──────────────────────────────────────────────────────● jul 12

    jul 11   998 captures  ← peak
    jul 12   2 captures

  ●  active day      █  peak day      ◆  /compact rescue


  ─── 2. What this chat captured (used when you --continue or /resume here) ───

  1,000 things — files, errors, decisions, agent runs:

    Data references              272   ████████████████████████████
    Constraints you set          183   ███████████████████░░░░░░░░░
    External docs indexed        129   █████████████░░░░░░░░░░░░░░░
    Errors caught                108   ███████████░░░░░░░░░░░░░░░░░
    Git operations                87   █████████░░░░░░░░░░░░░░░░░░░
    Slow tools recorded           85   █████████░░░░░░░░░░░░░░░░░░░
    Environment setup             32   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    Agent insights kept           29   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    Delegated work                29   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    Approaches you rejected       28   ███░░░░░░░░░░░░░░░░░░░░░░░░░
    cost                           5   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    Working directory              4   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    redirect                       4   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    Session intent                 3   █░░░░░░░░░░░░░░░░░░░░░░░░░░░
    Your decisions                 2   █░░░░░░░░░░░░░░░░░░░░░░░░░░░


  ─── 3. The scope, getting wider ───

  This chat: 37.2 MB kept out · 1,000 captures · started Jul 12, 2026.
  All your work: 7.0 MB kept out · 7,601 captures across 32 projects · since Jul 5, 2026.


  ─── 4. The bottom line ───

  $50.67 of Opus 4.7 tokens your team didn't burn.
  context-mode kept 7.0 MB out of context — that's 3 months of Cursor Pro paid for itself.

  Scale across a 10-dev team and that's ~$26,421/year saved.

  (Opus rates shown for context. On cheaper models the dollar number drops; the savings ratio holds.)


  ─── 5. What context-mode learned about how you work ───

  12 preferences picked up across 1 project:
    Long-term context           1   ████████████████████
    askuserquestion             1   ████████████████████
    browser                     1   ████████████████████
    cloudflare                  1   ████████████████████
    dns                         1   ████████████████████
    e                           1   ████████████████████
    fix                         1   ████████████████████
    hook                        1   ████████████████████
    no                          1   ████████████████████
    pantheon                    1   ████████████████████
    reset                       1   ████████████████████
    shared                      1   ████████████████████


  Your AI talks less, remembers more, costs less.
  Locale en-US · timezone America/Detroit · pricing examples for illustration only.

  v1.0.169
```


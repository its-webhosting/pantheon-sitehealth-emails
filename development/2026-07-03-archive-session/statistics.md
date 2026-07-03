# Session statistics

## Session metadata

- **Started:** 2026-07-03T16:42:32.349000+00:00
- **Ended:** 2026-07-03T18:20:53.237000+00:00
- **Duration:** 98 min
- **Model(s):** claude-opus-4-8
- **Assistant turns:** 67
- **Tool calls:** Edit × 23, Bash × 12, Write × 10, AskUserQuestion × 7, mcp__plugin_context-mode_context-mode__ctx_execute × 6, ToolSearch × 5, TaskCreate × 5, TaskUpdate × 5, ExitPlanMode × 4, Agent × 2, Read × 2, Skill × 1, SendMessage × 1, mcp__plugin_context-mode_context-mode__ctx_stats × 1

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-opus-4-8 | 20,337 | 153,795 | 17,464,138 | 815,119 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Settings  Status   Config   Usage   Stats

   Session

   Total cost:            $23.33
   Total duration (API):  40m 26s
   Total duration (wall): 2h 0m 41s
   Total code changes:    1147 lines added, 379 lines removed
   Usage by model:
        claude-opus-4-8:  48.5k input, 160.4k output, 17.3m cache read, 1.0m cache write ($22.93)
       claude-haiku-4-5:  101.5k input, 12.3k output, 716.0k cache read, 115.0k cache write, 2 web search
   ($0.3984)

   Current session
   ███████▌                                           15% used
   Resets 5:59pm (America/Detroit)

   Current week (all models)
   █▌                                                 3% used
   Resets Jul 7, 6:59pm (America/Detroit)

   Current week (Fable)
                                                      0% used

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   84% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   63% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   17% of your usage came from /claude-api
    Heavy skills can be scoped down or run with a cheaper model via skill
    frontmatter.

   37% of your usage came from MCP server "plugin:context-mode:context-mode"
    MCP tool results stay in context for the rest of the session. /compact to flush
    them, or disable servers you don't need.

   Skills                  % of usage
   /claude-api                    17%
   /claude-md-management:claud…    5%
   /init                           4%
   /update-config                  2%
   /context-mode:ctx-doctor        2%
   /context-mode:ctx-index         1%

   Subagents               % of usage
   Explore                         2%
   claude-code-guide               1%

   Plugins                 % of usage
   claude-md-management            5%
   context-mode                    2%

   MCP servers             % of usage
   plugin:context-mode:context…   37%
```

## Context window (approximate)

- **Largest prompt sent:** ~460,498 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._

## rtk gain

_Cumulative rtk savings captured at archive time._

```
RTK Token Savings (Global Scope)
════════════════════════════════════════════════════════════

Total commands:    42
Input tokens:      109.1K
Output tokens:     32.9K
Tokens saved:      76.2K (69.9%)
Total exec time:   233ms (avg 5ms)
Efficiency meter: █████████████████░░░░░░░ 69.9%

By Command
───────────────────────────────────────────────────────────────────────
  #  Command                   Count  Saved    Avg%    Time  Impact    
───────────────────────────────────────────────────────────────────────
 1.  rtk read                     15  39.8K    6.5%     0ms  ██████████
 2.  rtk grep                     11  19.7K   33.7%     0ms  █████░░░░░
 3.  rtk ls -la build              1  15.3K   56.2%   196ms  ████░░░░░░
 4.  rtk ls -la .                  2    814   61.3%     4ms  ░░░░░░░░░░
 5.  rtk ls -la /home/node...      1    121   51.3%     1ms  ░░░░░░░░░░
 6.  rtk ls -la news sampl...      1     81   81.8%     1ms  ░░░░░░░░░░
 7.  rtk ls -la plugin             1     78   88.6%     1ms  ░░░░░░░░░░
 8.  rtk ls -la vendor             1     74   83.1%     1ms  ░░░░░░░░░░
 9.  rtk ls -la check              1     58   90.6%     1ms  ░░░░░░░░░░
10.  rtk ls -la email_temp...      1     54   60.7%     1ms  ░░░░░░░░░░
───────────────────────────────────────────────────────────────────────
```

## context-mode (/ctx-stats)

```
  Across 1 days you ran 4 conversations in Claude Code.
  context-mode kept 128 KB out of your context window — about 128 KB every single day.


  ─── 1. Where you are now ───

  This conversation started 3 Jul 2026 at 12:55 (America/Detroit) in /workspace.
  1 hr alive · still going.

  Without context-mode    131 KB  ████████████████████████████████     33.4K tokens
  With context-mode      32.4 KB  ████████░░░░░░░░░░░░░░░░░░░░░░░░      8.3K tokens
                          75.2% kept out of context · your AI ran 4× longer before /compact fired

  How that 226 KB built up — 1 days, 1 active:

  jul 2 █─────────────────────────────────────────────────────── jul 2

    jul 2    90 captures  ← peak

  ●  active day      █  peak day      ◆  /compact rescue


  ─── 2. What this chat captured (used when you --continue or /resume here) ───

  90 things — files, errors, decisions, agent runs:

    Files tracked                 14   ████████████████████████████
    Tasks in progress             10   ████████████████████░░░░░░░░
    Data references                8   ████████████████░░░░░░░░░░░░
    Your decisions                 7   ██████████████░░░░░░░░░░░░░░
    cost                           6   ████████████░░░░░░░░░░░░░░░░
    session                        6   ████████████░░░░░░░░░░░░░░░░
    Your messages remembered       5   ██████████░░░░░░░░░░░░░░░░░░
    External docs indexed          4   ████████░░░░░░░░░░░░░░░░░░░░
    Session intent                 4   ████████░░░░░░░░░░░░░░░░░░░░
    Approaches you rejected        4   ████████░░░░░░░░░░░░░░░░░░░░
    sandbox                        4   ████████░░░░░░░░░░░░░░░░░░░░
    Working directory              3   ██████░░░░░░░░░░░░░░░░░░░░░░
    Plans drafted                  3   ██████░░░░░░░░░░░░░░░░░░░░░░
    Agent insights kept            2   ████░░░░░░░░░░░░░░░░░░░░░░░░
    Constraints you set            2   ████░░░░░░░░░░░░░░░░░░░░░░░░
    Project rules (CLAUDE.md)      2   ████░░░░░░░░░░░░░░░░░░░░░░░░
    Delegated work                 2   ████░░░░░░░░░░░░░░░░░░░░░░░░
    Errors caught                  1   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Git operations                 1   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Slow tools recorded            1   ██░░░░░░░░░░░░░░░░░░░░░░░░░░
    Skills used                    1   ██░░░░░░░░░░░░░░░░░░░░░░░░░░


  ─── 3. The scope, getting wider ───

  This chat: 226 KB kept out · 90 captures · started Jul 3, 2026.
  All your work: 128 KB kept out · 143 captures across 3 projects · since Jul 3, 2026.


  ─── 4. The bottom line ───

  $0.48 of Opus 4.7 tokens your team didn't burn.
  context-mode kept 128 KB out of context — that's 0 months of Cursor Pro paid for itself.

  Scale across a 10-dev team and that's ~$1,764/year saved.

  (Opus rates shown for context. On cheaper models the dollar number drops; the savings ratio holds.)


  ─── 5. What context-mode learned about how you work ───

  No preferences learned yet — context-mode picks them up automatically.


  Your AI talks less, remembers more, costs less.
  Locale en-US · timezone America/Detroit · pricing examples for illustration only.

  v1.0.169
```


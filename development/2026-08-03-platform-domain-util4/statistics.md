# Session statistics

## Session metadata

- **Started:** 2026-08-03T18:55:18.895000+00:00
- **Ended:** 2026-08-04T17:36:28.159000+00:00
- **Duration:** 1361 min
- **Model(s):** claude-opus-5
- **Assistant turns:** 372
- **Tool calls:** Bash × 240, Edit × 48, Agent × 43, TaskUpdate × 25, TaskCreate × 17, SendMessage × 11, AskUserQuestion × 9, Read × 7, Write × 4, Skill × 3, ToolSearch × 3, mcp__cloudflare-docs__search_cloudflare_documentation × 2

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format. Compare against the embedded `/usage` below, but do not assume it wins: its per-session block reports the window `/usage` itself ran in, so a capture taken after a resumed or re-entered session can read `$0.00 / 0 tokens` while this table is populated. Where they disagree, the larger non-zero source is the session._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-opus-5 | 722 | 429,674 | 163,764,532 | 2,183,225 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $391.34
   Total duration (API):  9h 0m 40s
   Total duration (wall): 22h 38m 33s
   Total code changes:    17860 lines added, 1300 lines removed
   Usage by model:
       claude-haiku-4-5:  535 input, 12 output, 0 cache read, 0 cache write ($0.0006)
          claude-opus-5:  34.6k input, 1.2m output, 304.3m cache read, 5.5m cache write ($224.73)
        claude-sonnet-5:  4.0k input, 1.3m output, 394.9m cache read, 7.6m cache write ($166.62)

   Current session
                                                      0% used
   Resets 6:10pm (America/Detroit)

   Current week (all models)
   █████████████████████████████████████              74% used
   Resets Aug 4, 7pm (America/Detroit)
   +50% weekly limits promo through Aug 19 · clau.de/cc-50-promo

   Current week (Fable)
   ██████████████████████████████████████████         84% used
   Resets Aug 4, 6:59pm (America/Detroit)

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   100% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   100% of your usage came from sessions active for 8+ hours
    These are often background/loop sessions. Continuous usage can add up quickly
    so make sure it is intentional.

   79% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   43% of your usage came from subagents under "psh-implementer"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   Skills                  % of usage
   /superpowers:subagent-drive…    1%
   /superpowers:writing-plans      1%
   /superpowers:brainstorming      1%

   Subagents               % of usage
   psh-implementer                43%
   psh-reviewer                   21%
   superpowers:subagent-driven…    4%

   Plugins                 % of usage
   superpowers                     8%

   MCP servers             % of usage
   codegraph                       2%
```

## Context window (approximate)

- **Largest prompt sent:** ~779,090 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


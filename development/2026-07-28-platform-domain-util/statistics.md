# Session statistics

## Session metadata

- **Started:** 2026-07-28T11:03:18.695000+00:00
- **Ended:** 2026-07-29T02:57:06.318000+00:00
- **Duration:** 953 min
- **Model(s):** claude-opus-5
- **Assistant turns:** 357
- **Tool calls:** Bash × 211, Edit × 42, Agent × 27, AskUserQuestion × 16, Read × 15, TaskUpdate × 14, Write × 12, SendMessage × 9, TaskCreate × 6, Skill × 4, ToolSearch × 2

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-opus-5 | 679 | 440,595 | 103,135,261 | 1,433,183 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $250.71
   Total duration (API):  6h 8m 29s
   Total duration (wall): 15h 52m 22s
   Total code changes:    12989 lines added, 826 lines removed
   Usage by model:
       claude-haiku-4-5:  534 input, 12 output, 0 cache read, 0 cache write ($0.0006)
          claude-opus-5:  21.0k input, 1.1m output, 217.9m cache read, 4.3m cache write ($169.22)
         claude-fable-5:  15 input, 23.9k output, 534.7k cache read, 87.8k cache write ($2.83)
        claude-sonnet-5:  4.5k input, 544.8k output, 188.0m cache read, 3.8m cache write ($78.66)

   Current session
                                                      0% used
   Resets 3:40am (America/Detroit)

   Current week (all models)
   ████▌                                              9% used
   Resets Aug 4, 7pm (America/Detroit)
   +50% weekly limits promo through Aug 19 · clau.de/cc-50-promo

   Current week (Fable)
   ████████                                           16% used
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

   78% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   43% of your usage came from subagents under "psh-implementer"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   Skills                  % of usage
   /superpowers:writing-plans      3%
   /superpowers:brainstorming      1%
   /superpowers:subagent-drive…    1%
   /mattpocock-skills:grilling     1%

   Subagents               % of usage
   psh-implementer                43%
   psh-reviewer                   22%
   superpowers:subagent-driven…    2%

   Plugins                 % of usage
   superpowers                     7%
   mattpocock-skills               1%
```

## Context window (approximate)

- **Largest prompt sent:** ~527,704 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


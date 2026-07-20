# Session statistics

## Session metadata

- **Started:** 2026-07-17T19:30:37.978000+00:00
- **Ended:** 2026-07-20T17:26:13.602000+00:00
- **Duration:** 4195 min
- **Model(s):** claude-opus-4-8
- **Assistant turns:** 106
- **Tool calls:** Bash × 50, Read × 19, Edit × 17, Agent × 7, Skill × 4, Write × 4, AskUserQuestion × 3

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-opus-4-8 | 194 | 157,241 | 23,317,452 | 625,920 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $39.82
   Total duration (API):  1h 21m 56s
   Total duration (wall): 2d 21h 54m
   Total code changes:    2773 lines added, 305 lines removed
   Usage by model:
       claude-haiku-4-5:  531 input, 19 output, 0 cache read, 0 cache write ($0.0006)
        claude-opus-4-8:  3.5k input, 224.2k output, 27.5m cache read, 905.3k cache write ($27.39)
        claude-sonnet-5:  490 input, 134.3k output, 24.4m cache read, 824.1k cache write ($12.43)

   Current session
   ▌                                                  1% used
   Resets 6:09pm (America/Detroit)

   Current week (all models)
   ████                                               8% used
   Resets Jul 21, 6:59pm (America/Detroit)
   +50% weekly limits promo through Aug 19 · clau.de/cc-50-promo

   Current week (Fable)
   ███▌                                               7% used
   Resets Jul 21, 6:59pm (America/Detroit)

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   100% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   100% of your usage came from /superpowers:subagent-driven-development
    Heavy skills can be scoped down or run with a cheaper model via skill
    frontmatter.

   100% of your usage came from plugin "superpowers"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   Skills                  % of usage
   /superpowers:subagent-drive…  100%

   Plugins                 % of usage
   superpowers                   100%
```

## Context window (approximate)

- **Largest prompt sent:** ~341,549 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


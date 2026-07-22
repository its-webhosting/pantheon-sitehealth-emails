# Session statistics

## Session metadata

- **Started:** 2026-07-22T11:28:38.612000+00:00
- **Ended:** 2026-07-22T17:02:38.090000+00:00
- **Duration:** 333 min
- **Model(s):** claude-fable-5
- **Assistant turns:** 91
- **Tool calls:** Edit × 39, Bash × 35, Read × 27, Agent × 11, Write × 4, Skill × 3, AskUserQuestion × 1

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-fable-5 | 5,974 | 152,810 | 25,198,713 | 782,602 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $122.59
   Total duration (API):  2h 35m 23s
   Total duration (wall): 5h 32m 18s
   Total code changes:    5524 lines added, 796 lines removed
   Usage by model:
       claude-haiku-4-5:  531 input, 19 output, 0 cache read, 0 cache write ($0.0006)
         claude-fable-5:  8.4k input, 240.7k output, 36.7m cache read, 1.2m cache write ($69.38)
        claude-sonnet-5:  1.9k input, 339.2k output, 104.9m cache read, 1.3m cache write ($41.56)
        claude-opus-4-8:  170 input, 78.9k output, 14.5m cache read, 390.3k cache write ($11.65)

   Current session
   █▌                                                 3% used
   Resets 5:59pm (America/Detroit)

   Current week (all models)
   ██▌                                                5% used
   Resets Jul 28, 6:59pm (America/Detroit)
   +50% weekly limits promo through Aug 19 · clau.de/cc-50-promo

   Current week (Fable)
   ███▌                                               7% used
   Resets Jul 28, 6:59pm (America/Detroit)

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   100% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   75% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   52% of your usage came from subagents under
   "superpowers:subagent-driven-development"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   13% of your usage came from /superpowers:subagent-driven-development
    Heavy skills can be scoped down or run with a cheaper model via skill
    frontmatter.

   69% of your usage came from plugin "superpowers"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   Skills                  % of usage
   /superpowers:subagent-drive…   13%
   /andrej-karpathy-skills:kar…    9%
   /archive-session                5%
   /superpowers:writing-plans      4%

   Subagents               % of usage
   superpowers:subagent-driven…   52%
   andrej-karpathy-skills:karp…    8%

   Plugins                 % of usage
   superpowers                    69%
   andrej-karpathy-skills         17%
```

## Context window (approximate)

- **Largest prompt sent:** ~419,143 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


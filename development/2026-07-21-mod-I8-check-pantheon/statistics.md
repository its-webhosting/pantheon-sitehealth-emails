# Session statistics

## Session metadata

- **Started:** 2026-07-21T12:49:18.887000+00:00
- **Ended:** 2026-07-21T14:10:35.688000+00:00
- **Duration:** 81 min
- **Model(s):** claude-fable-5
- **Assistant turns:** 54
- **Tool calls:** Bash × 29, Read × 8, Agent × 8, Write × 4, Skill × 3

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-fable-5 | 105 | 99,324 | 9,812,209 | 256,314 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $37.85
   Total duration (API):  1h 2m 7s
   Total duration (wall): 1h 20m 6s
   Total code changes:    2450 lines added, 96 lines removed
   Usage by model:
       claude-haiku-4-5:  531 input, 14 output, 0 cache read, 0 cache write ($0.0006)
         claude-fable-5:  607 input, 98.2k output, 9.8m cache read, 255.1k cache write ($19.83)
        claude-sonnet-5:  78 input, 16.2k output, 3.0m cache read, 168.0k cache write ($1.76)
        claude-opus-4-8:  306 input, 151.4k output, 16.0m cache read, 717.0k cache write ($16.26)

   Current session
   ████████                                           16% used
   Resets 12:19pm (America/Detroit)

   Current week (all models)
   ██████████                                         20% used
   Resets Jul 21, 6:59pm (America/Detroit)
   +50% weekly limits promo through Aug 19 · clau.de/cc-50-promo

   Current week (Fable)
   ███████████▌                                       23% used
   Resets Jul 21, 6:59pm (America/Detroit)

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   98% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   59% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   37% of your usage came from subagents under
   "superpowers:subagent-driven-development"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   28% of your usage came from /superpowers:subagent-driven-development
    Heavy skills can be scoped down or run with a cheaper model via skill
    frontmatter.

   73% of your usage came from plugin "superpowers"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   Skills                  % of usage
   /superpowers:subagent-drive…   28%
   /andrej-karpathy-skills:kar…    9%
   /superpowers:writing-plans      8%
   /archive-session                4%

   Subagents               % of usage
   superpowers:subagent-driven…   37%
   psh-reviewer                    3%
   psh-implementer                 2%

   Plugins                 % of usage
   superpowers                    73%
   andrej-karpathy-skills          9%

   MCP servers             % of usage
   codegraph                       6%
```

## Context window (approximate)

- **Largest prompt sent:** ~277,884 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


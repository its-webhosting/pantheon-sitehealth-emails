# Session statistics

## Session metadata

- **Started:** 2026-07-17T16:48:43.081000+00:00
- **Ended:** 2026-07-17T18:12:24.435000+00:00
- **Duration:** 83 min
- **Model(s):** claude-fable-5
- **Assistant turns:** 78
- **Tool calls:** Bash × 40, Read × 16, Agent × 13, Edit × 12, Write × 5, Skill × 4, ToolSearch × 2, SendMessage × 2, TaskOutput × 2

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-fable-5 | 145 | 106,215 | 15,392,542 | 263,068 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $46.45
   Total duration (API):  1h 7m 37s
   Total duration (wall): 1h 22m 3s
   Total code changes:    2349 lines added, 657 lines removed
   Usage by model:
       claude-haiku-4-5:  552 input, 14 output, 0 cache read, 0 cache write ($0.0006)
         claude-fable-5:  669 input, 125.6k output, 16.4m cache read, 414.2k cache write ($29.84)
        claude-opus-4-8:  320 input, 146.1k output, 11.4m cache read, 797.2k cache write ($14.34)
        claude-sonnet-5:  64 input, 26.1k output, 2.5m cache read, 296.7k cache write ($2.27)

   Current session
   █████████████▌                                     27% used
   Resets 3:39pm (America/Detroit)

   Current week (all models)
   ███                                                6% used
   Resets Jul 21, 6:59pm (America/Detroit)

   Current week (Fable)
   ███▌                                               7% used
   Resets Jul 21, 6:59pm (America/Detroit)

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   94% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   59% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   11% of your usage came from subagents under
   "superpowers:subagent-driven-development"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   12% of your usage came from /superpowers:subagent-driven-development
    Heavy skills can be scoped down or run with a cheaper model via skill
    frontmatter.

   35% of your usage came from plugin "superpowers"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   Skills                  % of usage
   /superpowers:subagent-drive…   12%
   /superpowers:brainstorming      6%
   /superpowers:writing-plans      4%
   /mattpocock-skills:grilling     4%
   /andrej-karpathy-skills:kar…    3%
   /mattpocock-skills:domain-m…    3%
   /mattpocock-skills:code-rev…    2%
   /archive-session                1%
   … 1 more

   Subagents               % of usage
   superpowers:subagent-driven…   11%
   psh-implementer                 7%
   psh-reviewer                    3%
   general-purpose                 2%
   mattpocock-skills:code-revi…    1%
   mattpocock-skills:grilling      1%
   superpowers:brainstorming       1%

   Plugins                 % of usage
   superpowers                    35%
   mattpocock-skills              11%
   andrej-karpathy-skills          3%
```

## Context window (approximate)

- **Largest prompt sent:** ~284,671 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


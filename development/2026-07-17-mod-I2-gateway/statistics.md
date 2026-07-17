# Session statistics

## Session metadata

- **Started:** 2026-07-17T18:14:08.597000+00:00
- **Ended:** 2026-07-17T19:28:55.071000+00:00
- **Duration:** 74 min
- **Model(s):** claude-fable-5, claude-opus-4-8
- **Assistant turns:** 57
- **Tool calls:** Bash × 24, Read × 15, Edit × 14, Agent × 6, Write × 3, Skill × 2

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-fable-5 | 5,912 | 14,066 | 444,407 | 91,689 |
| claude-opus-4-8 | 94 | 91,407 | 9,630,068 | 313,175 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $27.99
   Total duration (API):  1h 3m 47s
   Total duration (wall): 1h 13m 4s
   Total code changes:    1030 lines added, 47 lines removed
   Usage by model:
       claude-haiku-4-5:  531 input, 14 output, 0 cache read, 0 cache write ($0.0006)
         claude-fable-5:  5.9k input, 14.1k output, 444.4k cache read, 91.7k cache write ($3.04)
        claude-opus-4-8:  880 input, 240.8k output, 23.7m cache read, 945.7k cache write ($24.95)

   Current session
   █████████████████                                  34% used
   Resets 3:40pm (America/Detroit)

   Current week (all models)
   ███▌                                               7% used
   Resets Jul 21, 7pm (America/Detroit)

   Current week (Fable)
   ███▌                                               7% used
   Resets Jul 21, 7pm (America/Detroit)

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   96% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   56% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   10% of your usage came from /superpowers:subagent-driven-development
    Heavy skills can be scoped down or run with a cheaper model via skill
    frontmatter.

   30% of your usage came from plugin "superpowers"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   Skills                  % of usage
   /superpowers:subagent-drive…   10%
   /andrej-karpathy-skills:kar…    7%
   /superpowers:brainstorming      5%
   /superpowers:writing-plans      4%
   /mattpocock-skills:grilling     3%
   /mattpocock-skills:domain-m…    2%
   /mattpocock-skills:code-rev…    2%
   /archive-session                1%
   … 1 more

   Subagents               % of usage
   superpowers:subagent-driven…    9%
   psh-implementer                 6%
   andrej-karpathy-skills:karp…    6%
   psh-reviewer                    2%
   general-purpose                 2%
   mattpocock-skills:code-revi…    1%
   mattpocock-skills:grilling      1%
   superpowers:brainstorming       1%

   Plugins                 % of usage
   superpowers                    30%
   andrej-karpathy-skills         14%
   mattpocock-skills               9%
```

## Context window (approximate)

- **Largest prompt sent:** ~247,067 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


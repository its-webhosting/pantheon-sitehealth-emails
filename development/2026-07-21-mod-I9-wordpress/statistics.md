# Session statistics

## Session metadata

- **Started:** 2026-07-21T14:12:52.700000+00:00
- **Ended:** 2026-07-21T16:23:26.702000+00:00
- **Duration:** 130 min
- **Model(s):** claude-fable-5
- **Assistant turns:** 75
- **Tool calls:** Bash × 35, Read × 14, Agent × 12, Skill × 3, Write × 3, Edit × 3, SendMessage × 2, TaskOutput × 2, ToolSearch × 1

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-fable-5 | 147 | 104,212 | 16,596,050 | 293,171 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $90.42
   Total duration (API):  1h 43m 40s
   Total duration (wall): 2h 9m 18s
   Total code changes:    3306 lines added, 354 lines removed
   Usage by model:
       claude-haiku-4-5:  531 input, 19 output, 0 cache read, 0 cache write ($0.0006)
         claude-fable-5:  571 input, 248.1k output, 39.2m cache read, 1.2m cache write ($68.82)
        claude-sonnet-5:  132 input, 23.4k output, 5.0m cache read, 257.9k cache write ($2.82)
        claude-opus-4-8:  308 input, 168.5k output, 19.3m cache read, 782.8k cache write ($18.77)

   Current session
                                                      0% used
   Resets 5:20pm (America/Detroit)

   Current week (all models)
   ████████████                                       24% used
   Resets Jul 21, 7pm (America/Detroit)
   +50% weekly limits promo through Aug 19 · clau.de/cc-50-promo

   Current week (Fable)
   ██████████████▍                                    29% used
   Resets Jul 21, 7pm (America/Detroit)

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   98% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   59% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   43% of your usage came from subagents under
   "superpowers:subagent-driven-development"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   25% of your usage came from /superpowers:subagent-driven-development
    Heavy skills can be scoped down or run with a cheaper model via skill
    frontmatter.

   75% of your usage came from plugin "superpowers"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   Skills                  % of usage
   /superpowers:subagent-drive…   25%
   /andrej-karpathy-skills:kar…    7%
   /superpowers:writing-plans      7%
   /archive-session                3%

   Subagents               % of usage
   superpowers:subagent-driven…   43%
   psh-reviewer                    3%
   psh-implementer                 1%

   Plugins                 % of usage
   superpowers                    75%
   andrej-karpathy-skills          7%

   MCP servers             % of usage
   codegraph                       5%
```

## Context window (approximate)

- **Largest prompt sent:** ~314,832 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


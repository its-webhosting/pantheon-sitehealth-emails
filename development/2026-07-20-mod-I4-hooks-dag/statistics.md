# Session statistics

## Session metadata

- **Started:** 2026-07-20T17:34:48.131000+00:00
- **Ended:** 2026-07-20T20:45:53.181000+00:00
- **Duration:** 191 min
- **Model(s):** claude-fable-5
- **Assistant turns:** 102
- **Tool calls:** Bash × 47, Read × 18, Agent × 13, Edit × 11, TaskUpdate × 8, Write × 6, Skill × 4, TaskCreate × 4, ToolSearch × 3, SendMessage × 3, TaskOutput × 3

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-fable-5 | 200 | 118,861 | 23,558,572 | 590,147 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $64.77
   Total duration (API):  1h 19m 14s
   Total duration (wall): 3h 9m 33s
   Total code changes:    3504 lines added, 181 lines removed
   Usage by model:
       claude-haiku-4-5:  531 input, 19 output, 0 cache read, 0 cache write ($0.0006)
         claude-fable-5:  702 input, 117.8k output, 23.6m cache read, 588.3k cache write ($41.22)
        claude-sonnet-5:  7.0k input, 236.4k output, 36.3m cache read, 1.7m cache write ($20.72)
        claude-opus-4-8:  42 input, 26.5k output, 2.4m cache read, 153.4k cache write ($2.83)

   Current session
   ██████▌                                            13% used
   Resets 6:10pm (America/Detroit)

   Current week (all models)
   █████▌                                             11% used
   Resets Jul 21, 7pm (America/Detroit)
   +50% weekly limits promo through Aug 19 · clau.de/cc-50-promo

   Current week (Fable)
   █████▌                                             11% used
   Resets Jul 21, 7pm (America/Detroit)

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   93% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   63% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   27% of your usage came from subagents under
   "superpowers:subagent-driven-development"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   45% of your usage came from /superpowers:subagent-driven-development
    Heavy skills can be scoped down or run with a cheaper model via skill
    frontmatter.

   77% of your usage came from plugin "superpowers"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   Skills                  % of usage
   /superpowers:subagent-drive…   45%
   /archive-session                6%
   /superpowers:writing-plans      5%
   /andrej-karpathy-skills:kar…    4%

   Subagents               % of usage
   superpowers:subagent-driven…   27%
   psh-implementer                 4%
   psh-reviewer                    1%

   Plugins                 % of usage
   superpowers                    77%
   andrej-karpathy-skills          4%
```

## Context window (approximate)

- **Largest prompt sent:** ~318,257 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


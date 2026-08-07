# Session statistics

## Session metadata

- **Started:** 2026-08-07T10:43:42.294000+00:00
- **Ended:** 2026-08-07T16:11:34.738000+00:00
- **Duration:** 327 min
- **Model(s):** claude-opus-5
- **Assistant turns:** 89
- **Tool calls:** Bash × 42, Agent × 24, Write × 13, TaskCreate × 8, TaskUpdate × 5, ToolSearch × 4, SendMessage × 3, TaskOutput × 3, Skill × 2, Read × 2, AskUserQuestion × 2, ExitPlanMode × 1, Edit × 1

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format. Compare against the embedded `/usage` below, but do not assume it wins: its per-session block reports the window `/usage` itself ran in, so a capture taken after a resumed or re-entered session can read `$0.00 / 0 tokens` while this table is populated. Where they disagree, the larger non-zero source is the session._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-opus-5 | 1,810 | 136,610 | 25,000,019 | 401,105 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $136.12
   Total duration (API):  3h 49m 17s
   Total duration (wall): 5h 24m 14s
   Total code changes:    7558 lines added, 452 lines removed
   Usage by model:
       claude-haiku-4-5:  1.2k input, 38 output, 0 cache read, 0 cache write ($0.0014)
          claude-opus-5:  38.8k input, 628.0k output, 118.6m cache read, 3.3m cache write ($97.55)
        claude-sonnet-5:  11.1k input, 263.2k output, 82.5m cache read, 2.6m cache write ($38.57)

   Current session
   ██                                                 4% used
   Resets 4:09pm (America/Detroit)

   Current week (all models)
   ████████                                           16% used
   Resets Aug 11, 6:59pm (America/Detroit)

   Current week (Fable)
   ███████████▌                                       23% used
   Resets Aug 11, 7pm (America/Detroit)

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   99% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   72% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   70% of your usage came from subagents under
   "superpowers:subagent-driven-development"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   12% of your usage came from /superpowers:subagent-driven-development
    Heavy skills can be scoped down or run with a cheaper model via skill
    frontmatter.

   82% of your usage came from plugin "superpowers"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   Skills                  % of usage
   /superpowers:subagent-drive…   12%
   /andrej-karpathy-skills:kar…    1%

   Subagents               % of usage
   superpowers:subagent-driven…   70%
   psh-implementer                11%
   andrej-karpathy-skills:karp…    4%

   Plugins                 % of usage
   superpowers                    82%
   andrej-karpathy-skills          5%
```

## Context window (approximate)

- **Largest prompt sent:** ~424,268 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


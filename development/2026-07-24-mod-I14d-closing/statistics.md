# Session statistics

## Session metadata

- **Started:** 2026-07-24T15:17:39.594000+00:00
- **Ended:** 2026-07-24T20:10:15.086000+00:00
- **Duration:** 292 min
- **Model(s):** claude-opus-4-8
- **Assistant turns:** 143
- **Tool calls:** Bash × 74, Read × 15, Agent × 14, AskUserQuestion × 8, Edit × 8, TaskCreate × 5, TaskUpdate × 5, Skill × 4, Write × 4, ToolSearch × 1

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-opus-4-8 | 277 | 174,906 | 32,611,865 | 359,638 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $80.33
   Total duration (API):  2h 29m 39s
   Total duration (wall): 4h 51m 19s
   Total code changes:    6632 lines added, 3192 lines removed
   Usage by model:
       claude-haiku-4-5:  531 input, 19 output, 0 cache read, 0 cache write ($0.0006)
        claude-opus-4-8:  10.4k input, 614.2k output, 89.2m cache read, 2.6m cache write ($77.57)
        claude-sonnet-5:  94 input, 38.4k output, 4.4m cache read, 231.9k cache write ($2.76)

   Current session
   ██████▌                                            13% used
   Resets 6:20pm (America/Detroit)

   Current week (all models)
   ██████████████                                     28% used
   Resets Jul 28, 7pm (America/Detroit)
   +50% weekly limits promo through Aug 19 · clau.de/cc-50-promo

   Current week (Fable)
   ███████████████                                    30% used
   Resets Jul 28, 7pm (America/Detroit)

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   100% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   74% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   24% of your usage came from subagents under "superpowers:writing-plans"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   48% of your usage came from plugin "superpowers"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   Skills                  % of usage
   /superpowers:writing-plans      6%
   /archive-session                4%
   /superpowers:subagent-drive…    3%
   /andrej-karpathy-skills:kar…    2%
   /superpowers:brainstorming      1%

   Subagents               % of usage
   superpowers:writing-plans      24%
   psh-implementer                16%
   superpowers:subagent-driven…   15%
   psh-reviewer                   10%
   andrej-karpathy-skills:karp…    2%

   Plugins                 % of usage
   superpowers                    48%
   andrej-karpathy-skills          4%
```

## Context window (approximate)

- **Largest prompt sent:** ~351,680 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


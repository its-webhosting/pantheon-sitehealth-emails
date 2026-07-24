# Session statistics

## Session metadata

- **Started:** 2026-07-23T18:32:23.460000+00:00
- **Ended:** 2026-07-24T11:46:02.499000+00:00
- **Duration:** 1033 min
- **Model(s):** claude-fable-5
- **Assistant turns:** 150
- **Tool calls:** Bash × 63, Edit × 40, Agent × 20, TaskUpdate × 19, Read × 14, TaskCreate × 10, Write × 8, SendMessage × 6, ToolSearch × 3, AskUserQuestion × 2, Skill × 2

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-fable-5 | 1,839 | 191,738 | 49,583,862 | 1,310,450 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $214.96
   Total duration (API):  4h 16m 7s
   Total duration (wall): 17h 12m 33s
   Total code changes:    4279 lines added, 1446 lines removed
   Usage by model:
       claude-haiku-4-5:  531 input, 19 output, 0 cache read, 0 cache write ($0.0006)
         claude-fable-5:  5.2k input, 312.5k output, 67.4m cache read, 2.0m cache write ($117.94)
        claude-opus-4-8:  4.0k input, 443.5k output, 52.0m cache read, 2.3m cache write ($51.37)
        claude-sonnet-5:  8.2k input, 369.9k output, 102.6m cache read, 2.5m cache write ($45.66)

   Current session
   █▌                                                 3% used
   Resets 12:40pm (America/Detroit)

   Current week (all models)
   ███████████▌                                       23% used
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

   69% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   53% of your usage came from sessions active for 8+ hours
    These are often background/loop sessions. Continuous usage can add up quickly
    so make sure it is intentional.

   24% of your usage came from subagents under
   "superpowers:subagent-driven-development"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   33% of your usage came from plugin "superpowers"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   Skills                  % of usage
   /superpowers:subagent-drive…    7%
   /andrej-karpathy-skills:kar…    6%
   /archive-session                4%
   /superpowers:writing-plans      3%

   Subagents               % of usage
   superpowers:subagent-driven…   24%
   psh-implementer                17%
   psh-reviewer                   13%
   andrej-karpathy-skills:karp…    2%

   Plugins                 % of usage
   superpowers                    33%
   andrej-karpathy-skills          7%
```

## Context window (approximate)

- **Largest prompt sent:** ~509,103 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


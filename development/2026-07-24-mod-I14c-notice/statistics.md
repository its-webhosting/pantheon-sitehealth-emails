# Session statistics

## Session metadata

- **Started:** 2026-07-24T11:51:12.580000+00:00
- **Ended:** 2026-07-24T15:15:59.742000+00:00
- **Duration:** 204 min
- **Model(s):** claude-opus-4-8
- **Assistant turns:** 147
- **Tool calls:** Bash × 97, Edit × 14, Agent × 11, Read × 9, Write × 8, AskUserQuestion × 3, Skill × 2

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-opus-4-8 | 281 | 186,051 | 38,885,669 | 420,258 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $116.19
   Total duration (API):  2h 38m 19s
   Total duration (wall): 3h 23m 38s
   Total code changes:    5451 lines added, 814 lines removed
   Usage by model:
       claude-haiku-4-5:  531 input, 19 output, 0 cache read, 0 cache write ($0.0006)
        claude-opus-4-8:  7.2k input, 676.1k output, 161.2m cache read, 2.7m cache write ($116.19)

   Current session
   ████████                                           16% used
   Resets 12:40pm (America/Detroit)

   Current week (all models)
   ████████████▌                                      25% used
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

   72% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   47% of your usage came from sessions active for 8+ hours
    These are often background/loop sessions. Continuous usage can add up quickly
    so make sure it is intentional.

   19% of your usage came from subagents under "superpowers:writing-plans"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   45% of your usage came from plugin "superpowers"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   Skills                  % of usage
   /superpowers:subagent-drive…    5%
   /superpowers:writing-plans      4%
   /andrej-karpathy-skills:kar…    3%
   /archive-session                3%

   Subagents               % of usage
   superpowers:writing-plans      19%
   superpowers:subagent-driven…   18%
   psh-implementer                15%
   psh-reviewer                   10%
   andrej-karpathy-skills:karp…    3%

   Plugins                 % of usage
   superpowers                    45%
   andrej-karpathy-skills          6%
```

## Context window (approximate)

- **Largest prompt sent:** ~442,459 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


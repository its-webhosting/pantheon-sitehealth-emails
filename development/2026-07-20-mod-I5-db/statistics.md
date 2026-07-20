# Session statistics

## Session metadata

- **Started:** 2026-07-20T20:47:54.026000+00:00
- **Ended:** 2026-07-20T23:58:51.530000+00:00
- **Duration:** 190 min
- **Model(s):** claude-fable-5
- **Assistant turns:** 36
- **Tool calls:** Bash × 22, Read × 7, Agent × 6, Skill × 3, Write × 2

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-fable-5 | 65 | 70,022 | 5,874,197 | 434,995 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Total cost:            $32.22
   Total duration (API):  43m 37s
   Total duration (wall): 3h 9m 40s
   Total code changes:    1904 lines added, 64 lines removed
   Usage by model:
       claude-haiku-4-5:  621 input, 3.1k output, 426.6k cache read, 49.1k cache write ($0.1200)
         claude-fable-5:  567 input, 68.8k output, 5.9m cache read, 433.6k cache write ($17.99)
        claude-sonnet-5:  3.7k input, 92.2k output, 20.0m cache read, 481.2k cache write ($9.18)
        claude-opus-4-8:  60 input, 36.7k output, 4.2m cache read, 310.1k cache write ($4.93)

   Current session
   █                                                  2% used
   Resets 12:49am (America/Detroit)

   Current week (all models)
   ██████                                             12% used
   Resets Jul 21, 6:59pm (America/Detroit)
   +50% weekly limits promo through Aug 19 · clau.de/cc-50-promo

   Current week (Fable)
   ██████▌                                            13% used
   Resets Jul 21, 6:59pm (America/Detroit)

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   95% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   62% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   32% of your usage came from subagents under
   "superpowers:subagent-driven-development"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   35% of your usage came from /superpowers:subagent-driven-development
    Heavy skills can be scoped down or run with a cheaper model via skill
    frontmatter.

   72% of your usage came from plugin "superpowers"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   Skills                  % of usage
   /superpowers:subagent-drive…   35%
   /andrej-karpathy-skills:kar…    7%
   /archive-session                7%
   /superpowers:writing-plans      5%

   Subagents               % of usage
   superpowers:subagent-driven…   32%
   psh-implementer                 3%
   psh-reviewer                    1%

   Plugins                 % of usage
   superpowers                    72%
   andrej-karpathy-skills          7%
```

## Context window (approximate)

- **Largest prompt sent:** ~240,653 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


# Session statistics

## Session metadata

- **Started:** 2026-07-23T16:22:34.734000+00:00
- **Ended:** 2026-07-23T18:30:14.649000+00:00
- **Duration:** 127 min
- **Model(s):** claude-fable-5
- **Assistant turns:** 59
- **Tool calls:** Bash × 28, Read × 10, Edit × 10, Agent × 8, Skill × 3, Write × 2, AskUserQuestion × 1

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-fable-5 | 115 | 94,123 | 14,079,184 | 313,516 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $77.28
   Total duration (API):  1h 39m 18s
   Total duration (wall): 2h 6m 24s
   Total code changes:    2874 lines added, 262 lines removed
   Usage by model:
       claude-haiku-4-5:  531 input, 19 output, 0 cache read, 0 cache write ($0.0006)
         claude-fable-5:  303 input, 161.8k output, 20.5m cache read, 750.7k cache write ($40.27)
        claude-opus-4-8:  588 input, 254.4k output, 47.7m cache read, 897.3k cache write ($35.84)
        claude-sonnet-5:  54 input, 14.8k output, 2.0m cache read, 91.5k cache write ($1.17)

   Current session
   ██                                                 4% used
   Resets 7pm (America/Detroit)

   Current week (all models)
   ███████▌                                           15% used
   Resets Jul 28, 7pm (America/Detroit)
   +50% weekly limits promo through Aug 19 · clau.de/cc-50-promo

   Current week (Fable)
   ██████████                                         20% used
   Resets Jul 28, 7pm (America/Detroit)

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   100% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   63% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   47% of your usage came from subagents under
   "superpowers:subagent-driven-development"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   13% of your usage came from /andrej-karpathy-skills:karpathy-guidelines
    Heavy skills can be scoped down or run with a cheaper model via skill
    frontmatter.

   64% of your usage came from plugin "superpowers"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   Skills                  % of usage
   /andrej-karpathy-skills:kar…   13%
   /superpowers:subagent-drive…   12%
   /superpowers:writing-plans      5%
   /archive-session                1%

   Subagents               % of usage
   superpowers:subagent-driven…   47%
   psh-reviewer                    4%
   andrej-karpathy-skills:karp…    3%

   Plugins                 % of usage
   superpowers                    64%
   andrej-karpathy-skills         16%
```

## Context window (approximate)

- **Largest prompt sent:** ~335,220 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


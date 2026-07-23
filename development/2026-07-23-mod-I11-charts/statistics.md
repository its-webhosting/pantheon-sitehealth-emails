# Session statistics

## Session metadata

- **Started:** 2026-07-23T13:22:24.144000+00:00
- **Ended:** 2026-07-23T14:18:40.293000+00:00
- **Duration:** 56 min
- **Model(s):** claude-fable-5
- **Assistant turns:** 77
- **Tool calls:** Bash × 51, Read × 12, Edit × 11, Agent × 4, Skill × 3, Write × 2, ToolSearch × 1, SendMessage × 1

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-fable-5 | 151 | 98,362 | 17,369,573 | 289,104 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $39.59
   Total duration (API):  40m 17s
   Total duration (wall): 54m 54s
   Total code changes:    1593 lines added, 43 lines removed
   Usage by model:
       claude-haiku-4-5:  605 input, 2.5k output, 428.8k cache read, 60.3k cache write ($0.1313)
         claude-fable-5:  893 input, 122.0k output, 19.7m cache read, 462.3k cache write ($33.76)
        claude-sonnet-5:  101 input, 23.0k output, 5.1m cache read, 123.4k cache write ($2.35)
        claude-opus-4-8:  40 input, 23.9k output, 2.1m cache read, 274.7k cache write ($3.35)

   Current session
   ███████▌                                           15% used
   Resets 2pm (America/Detroit)

   Current week (all models)
   ████                                               8% used
   Resets Jul 28, 7pm (America/Detroit)
   +50% weekly limits promo through Aug 19 · clau.de/cc-50-promo

   Current week (Fable)
   ██████                                             12% used
   Resets Jul 28, 7pm (America/Detroit)

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   100% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   76% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   33% of your usage came from subagents under
   "superpowers:subagent-driven-development"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   13% of your usage came from /superpowers:subagent-driven-development
    Heavy skills can be scoped down or run with a cheaper model via skill
    frontmatter.

   49% of your usage came from plugin "superpowers"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   Skills                  % of usage
   /superpowers:subagent-drive…   13%
   /andrej-karpathy-skills:kar…   13%
   /archive-session                8%
   /superpowers:writing-plans      3%

   Subagents               % of usage
   superpowers:subagent-driven…   33%
   psh-reviewer                    8%

   Plugins                 % of usage
   superpowers                    49%
   andrej-karpathy-skills         13%
```

## Context window (approximate)

- **Largest prompt sent:** ~310,595 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


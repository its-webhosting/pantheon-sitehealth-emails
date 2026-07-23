# Session statistics

## Session metadata

- **Started:** 2026-07-23T14:19:50.762000+00:00
- **Ended:** 2026-07-23T16:21:10.142000+00:00
- **Duration:** 121 min
- **Model(s):** claude-fable-5
- **Assistant turns:** 59
- **Tool calls:** Bash × 30, Read × 13, Agent × 11, Skill × 3, Write × 3

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-fable-5 | 115 | 99,484 | 13,557,451 | 301,340 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $62.99
   Total duration (API):  1h 27m 58s
   Total duration (wall): 2h 0m 13s
   Total code changes:    2832 lines added, 263 lines removed
   Usage by model:
       claude-haiku-4-5:  531 input, 19 output, 0 cache read, 0 cache write ($0.0006)
         claude-fable-5:  677 input, 127.4k output, 18.3m cache read, 520.1k cache write ($33.46)
        claude-opus-4-8:  560 input, 225.9k output, 31.3m cache read, 977.4k cache write ($27.40)
        claude-sonnet-5:  97 input, 17.9k output, 3.8m cache read, 187.3k cache write ($2.13)

   Current session
   ████████████████                                   32% used
   Resets 1:59pm (America/Detroit)

   Current week (all models)
   █████▌                                             11% used
   Resets Jul 28, 6:59pm (America/Detroit)
   +50% weekly limits promo through Aug 19 · clau.de/cc-50-promo

   Current week (Fable)
   ███████▌                                           15% used
   Resets Jul 28, 6:59pm (America/Detroit)

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   90% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   63% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   36% of your usage came from subagents under
   "superpowers:subagent-driven-development"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   13% of your usage came from /andrej-karpathy-skills:karpathy-guidelines
    Heavy skills can be scoped down or run with a cheaper model via skill
    frontmatter.

   53% of your usage came from plugin "superpowers"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   Skills                  % of usage
   /andrej-karpathy-skills:kar…   13%
   /superpowers:subagent-drive…   12%
   /archive-session                7%
   /superpowers:writing-plans      5%

   Subagents               % of usage
   superpowers:subagent-driven…   36%
   psh-reviewer                    6%

   Plugins                 % of usage
   superpowers                    53%
   andrej-karpathy-skills         13%
```

## Context window (approximate)

- **Largest prompt sent:** ~323,016 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


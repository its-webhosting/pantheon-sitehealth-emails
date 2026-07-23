# Session statistics

## Session metadata

- **Started:** 2026-07-23T18:32:23.460000+00:00
- **Ended:** 2026-07-23T23:18:34.111000+00:00
- **Duration:** 286 min
- **Model(s):** claude-fable-5
- **Assistant turns:** 86
- **Tool calls:** Bash × 33, Edit × 22, Read × 14, Agent × 10, TaskUpdate × 10, TaskCreate × 5, Write × 4, ToolSearch × 3, Skill × 2, SendMessage × 2, AskUserQuestion × 1

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-fable-5 | 1,712 | 113,336 | 21,719,396 | 685,139 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $95.73
   Total duration (API):  1h 58m 58s
   Total duration (wall): 4h 44m 47s
   Total code changes:    1846 lines added, 333 lines removed
   Usage by model:
       claude-haiku-4-5:  531 input, 19 output, 0 cache read, 0 cache write ($0.0006)
         claude-fable-5:  2.9k input, 171.0k output, 30.8m cache read, 1.1m cache write ($57.70)
        claude-opus-4-8:  258 input, 182.7k output, 23.5m cache read, 500.5k cache write ($19.45)
        claude-sonnet-5:  6.0k input, 165.8k output, 39.9m cache read, 1.1m cache write ($18.58)

   Current session
   █                                                  2% used
   Resets 12:09am (America/Detroit)

   Current week (all models)
   █████████▌                                         19% used
   Resets Jul 28, 6:59pm (America/Detroit)
   +50% weekly limits promo through Aug 19 · clau.de/cc-50-promo

   Current week (Fable)
   ████████████▌                                      25% used
   Resets Jul 28, 6:59pm (America/Detroit)

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   100% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   66% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   34% of your usage came from subagents under
   "superpowers:subagent-driven-development"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   10% of your usage came from /superpowers:subagent-driven-development
    Heavy skills can be scoped down or run with a cheaper model via skill
    frontmatter.

   47% of your usage came from plugin "superpowers"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   Skills                  % of usage
   /superpowers:subagent-drive…   10%
   /andrej-karpathy-skills:kar…    8%
   /superpowers:writing-plans      4%
   /archive-session                3%

   Subagents               % of usage
   superpowers:subagent-driven…   34%
   psh-reviewer                   10%
   psh-implementer                 8%
   andrej-karpathy-skills:karp…    2%

   Plugins                 % of usage
   superpowers                    47%
   andrej-karpathy-skills         10%
```

## Context window (approximate)

- **Largest prompt sent:** ~366,524 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


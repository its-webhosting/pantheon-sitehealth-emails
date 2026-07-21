# Session statistics

## Session metadata

- **Started:** 2026-07-21T01:00:35.100000+00:00
- **Ended:** 2026-07-21T12:04:20.220000+00:00
- **Duration:** 663 min
- **Model(s):** claude-fable-5
- **Assistant turns:** 86
- **Tool calls:** Bash × 38, Read × 16, Edit × 12, Agent × 10, TaskUpdate × 7, TaskCreate × 4, Write × 4, Skill × 3, ToolSearch × 3, SendMessage × 3, TaskOutput × 3, AskUserQuestion × 1

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-fable-5 | 206 | 144,219 | 19,997,590 | 580,993 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $80.21
   Total duration (API):  1h 44m 27s
   Total duration (wall): 11h 2m 26s
   Total code changes:    4072 lines added, 367 lines removed
   Usage by model:
       claude-haiku-4-5:  531 input, 14 output, 0 cache read, 0 cache write ($0.0006)
         claude-fable-5:  1.3k input, 189.9k output, 24.3m cache read, 993.9k cache write ($50.54)
        claude-sonnet-5:  7.9k input, 156.3k output, 28.8m cache read, 1.2m cache write ($15.36)
        claude-opus-4-8:  232 input, 133.7k output, 15.9m cache read, 485.5k cache write ($14.32)

   Current session
   ███                                                6% used
   Resets 12:19pm (America/Detroit)

   Current week (all models)
   █████████                                          18% used
   Resets Jul 21, 6:59pm (America/Detroit)
   +50% weekly limits promo through Aug 19 · clau.de/cc-50-promo

   Current week (Fable)
   ██████████                                         20% used
   Resets Jul 21, 6:59pm (America/Detroit)

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   98% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   62% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   36% of your usage came from subagents under
   "superpowers:subagent-driven-development"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   30% of your usage came from /superpowers:subagent-driven-development
    Heavy skills can be scoped down or run with a cheaper model via skill
    frontmatter.

   73% of your usage came from plugin "superpowers"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   Skills                  % of usage
   /superpowers:subagent-drive…   30%
   /superpowers:writing-plans      8%
   /andrej-karpathy-skills:kar…    8%
   /archive-session                4%

   Subagents               % of usage
   superpowers:subagent-driven…   36%
   psh-reviewer                    3%
   psh-implementer                 2%

   Plugins                 % of usage
   superpowers                    73%
   andrej-karpathy-skills          8%

   MCP servers             % of usage
   codegraph                       7%
```

## Context window (approximate)

- **Largest prompt sent:** ~330,844 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


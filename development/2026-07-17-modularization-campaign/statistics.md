# Session statistics

## Session metadata

- **Started:** 2026-07-17T14:43:22.589000+00:00
- **Ended:** 2026-07-17T16:45:47.898000+00:00
- **Duration:** 122 min
- **Model(s):** claude-fable-5
- **Assistant turns:** 111
- **Tool calls:** Bash × 52, Edit × 25, TaskUpdate × 20, TaskCreate × 11, Agent × 11, AskUserQuestion × 11, Skill × 7, Write × 7, Read × 6, SendMessage × 4, ToolSearch × 2, TaskList × 1

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-fable-5 | 1,432 | 159,767 | 23,484,638 | 328,554 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $63.56
   Total duration (API):  1h 37m 12s
   Total duration (wall): 2h 0m 43s
   Total code changes:    2352 lines added, 656 lines removed
   Usage by model:
       claude-haiku-4-5:  534 input, 14 output, 0 cache read, 0 cache write ($0.0006)
         claude-fable-5:  5.6k input, 158.7k output, 25.5m cache read, 329.7k cache write ($40.07)
        claude-opus-4-8:  454 input, 243.5k output, 18.1m cache read, 1.3m cache write ($23.49)

   Current session
   ███████▌                                           15% used
   Resets 3:39pm (America/Detroit)

   Current week (all models)
   █▌                                                 3% used
   Resets Jul 21, 6:59pm (America/Detroit)

   Current week (Fable)
   ██                                                 4% used
   Resets Jul 21, 6:59pm (America/Detroit)

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   92% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   62% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   10% of your usage came from subagents under "psh-implementer"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   19% of your usage came from plugin "superpowers"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   Skills                  % of usage
   /superpowers:brainstorming      9%
   /mattpocock-skills:grilling     5%
   /mattpocock-skills:domain-m…    4%
   /superpowers:subagent-drive…    4%
   /mattpocock-skills:code-rev…    3%
   /superpowers:writing-plans      3%
   /archive-session                2%
   /superpowers:test-driven-de…    1%
   … 1 more

   Subagents               % of usage
   psh-implementer                10%
   psh-reviewer                    3%
   general-purpose                 3%
   superpowers:subagent-driven…    1%
   mattpocock-skills:code-revi…    1%
   mattpocock-skills:grilling      1%
   superpowers:brainstorming      1%

   Plugins                 % of usage
   superpowers                    19%
   mattpocock-skills              15%
   andrej-karpathy-skills          1%
```

## Context window (approximate)

- **Largest prompt sent:** ~351,954 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


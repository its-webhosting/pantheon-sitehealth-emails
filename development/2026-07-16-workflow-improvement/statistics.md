# Session statistics

## Session metadata

- **Started:** 2026-07-16T20:35:23.376000+00:00
- **Ended:** 2026-07-17T02:29:41.248000+00:00
- **Duration:** 354 min
- **Model(s):** claude-opus-4-8
- **Assistant turns:** 188
- **Tool calls:** Bash × 124, AskUserQuestion × 19, Edit × 18, Write × 11, Read × 10, Agent × 5, Skill × 2

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-opus-4-8 | 815 | 272,035 | 55,813,913 | 598,407 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $48.28
   Total duration (API):  1h 21m 59s
   Total duration (wall): 5h 52m 26s
   Total code changes:    1479 lines added, 258 lines removed
   Usage by model:
       claude-haiku-4-5:  48.5k input, 2.1k output, 54.2k cache read, 28.5k cache write ($0.1003)
        claude-opus-4-8:  5.2k input, 357.0k output, 61.9m cache read, 960.7k cache write ($48.18)

   Current session
   ██████████▌                                        21% used
   Resets 1:30am (America/Detroit)

   Current week (all models)
   █▌                                                 3% used
   Resets Jul 21, 7pm (America/Detroit)

   Current week (Fable)
                                                      0% used

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   83% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   71% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   11% of your usage came from /mattpocock-skills:grilling
    Heavy skills can be scoped down or run with a cheaper model via skill
    frontmatter.

   15% of your usage came from plugin "mattpocock-skills"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   Skills                  % of usage
   /mattpocock-skills:grilling    11%
   /superpowers:brainstorming      8%
   /superpowers:test-driven-de…    3%
   /archive-session                1%
   /mattpocock-skills:setup-ma…    1%
   /mattpocock-skills:ask-matt     1%

   Subagents               % of usage
   general-purpose                 6%
   mattpocock-skills:grilling      3%
   superpowers:brainstorming       1%

   Plugins                 % of usage
   mattpocock-skills              15%
   superpowers                    12%
```

## Context window (approximate)

- **Largest prompt sent:** ~472,723 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


# Session statistics

## Session metadata

- **Started:** 2026-07-13T18:50:45.651000+00:00
- **Ended:** 2026-07-14T11:56:55.560000+00:00
- **Duration:** 1026 min
- **Model(s):** claude-opus-4-8
- **Assistant turns:** 162
- **Tool calls:** Bash × 59, Agent × 48, Edit × 23, Write × 11, Read × 8, AskUserQuestion × 7, Skill × 4, ReportFindings × 1

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-opus-4-8 | 4,089 | 344,262 | 50,894,482 | 2,024,638 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $162.41
   Total duration (API):  6h 29m 16s
   Total duration (wall): 17h 4m 51s
   Total code changes:    8497 lines added, 2355 lines removed
   Usage by model:
        claude-opus-4-8:  13.2k input, 1.3m output, 115.7m cache read, 5.2m cache write ($130.88)
       claude-haiku-4-5:  13.8k input, 472 output, 0 cache read, 0 cache write, 1 web search ($0.0261)
        claude-sonnet-5:  1.3k input, 518.8k output, 54.4m cache read, 2.0m cache write ($31.51)

   Current session
   ██████▌                                            13% used
   Resets 12:19pm (America/Detroit)

   Current week (all models)
   █████████████████                                  34% used
   Resets Jul 14, 6:59pm (America/Detroit)

   Current week (Fable)
                                                      0% used

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   92% of your usage came from subagent-heavy sessions
   92% of your usage came from sessions active for 8+ hours
   40% of your usage was at >150k context
   22% of your usage came from subagents under "code-review"
   25% of your usage came from plugin "superpowers"

   Skills                  % of usage
   /superpowers:subagent-drive…    9%
   /code-review                    4%
   /andrej-karpathy-skills:kar…    2%
   /archive-session                1%

   Subagents               % of usage
   code-review                    22%
   general-purpose                18%
   superpowers:subagent-driven…   16%

   Plugins                 % of usage
   superpowers                    25%
   andrej-karpathy-skills          2%

   MCP servers             % of usage
   codegraph                       3%
```

## Context window (approximate)

- **Largest prompt sent:** ~585,280 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


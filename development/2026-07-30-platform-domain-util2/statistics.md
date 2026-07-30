# Session statistics

## Session metadata

- **Started:** 2026-07-30T17:12:37.273000+00:00
- **Ended:** 2026-07-30T20:42:56.590000+00:00
- **Duration:** 210 min
- **Model(s):** claude-opus-5
- **Assistant turns:** 223
- **Tool calls:** Bash × 162, Edit × 15, Read × 14, AskUserQuestion × 12, Write × 9, Skill × 4, Agent × 3, ToolSearch × 1, Monitor × 1

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-opus-5 | 415 | 387,248 | 89,550,994 | 1,164,029 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $80.75
   Total duration (API):  1h 54m 52s
   Total duration (wall): 3h 1m 8s
   Total code changes:    3349 lines added, 348 lines removed
   Usage by model:
          claude-opus-5:  55.7k input, 535.7k output, 116.0m cache read, 1.2m cache write ($80.75)

   Current session
   ████████████████▌                                  33% used
   Resets 6pm (America/Detroit)

   Current week (all models)
   ███████████████                                    30% used
   Resets Aug 4, 7pm (America/Detroit)
   +50% weekly limits promo through Aug 19 · clau.de/cc-50-promo

   Current week (Fable)
   ██████████████████████▌                            45% used
   Resets Aug 4, 7pm (America/Detroit)

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   91% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   74% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   17% of your usage came from subagents under "psh-reviewer"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   Skills                  % of usage
   /andrej-karpathy-skills:kar…    8%
   /archive-session                5%
   /code-review                    4%
   /superpowers:writing-plans      3%
   /mattpocock-skills:grilling     2%
   /superpowers:brainstorming      1%

   Subagents               % of usage
   psh-reviewer                   17%

   Plugins                 % of usage
   andrej-karpathy-skills          8%
   superpowers                     5%
   mattpocock-skills               2%

   MCP servers             % of usage
   cloudflare-docs                 2%
```

## Context window (approximate)

- **Largest prompt sent:** ~615,026 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


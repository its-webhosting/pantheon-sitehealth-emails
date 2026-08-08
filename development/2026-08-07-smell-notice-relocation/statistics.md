# Session statistics

## Session metadata

- **Started:** 2026-08-08T00:51:25.844000+00:00
- **Ended:** 2026-08-08T11:27:55.033000+00:00
- **Duration:** 636 min
- **Model(s):** claude-opus-5
- **Assistant turns:** 142
- **Tool calls:** Bash × 85, Edit × 19, Read × 15, Agent × 9, Write × 5, Skill × 4, AskUserQuestion × 3, SendMessage × 3, ToolSearch × 2

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format. Compare against the embedded `/usage` below, but do not assume it wins: its per-session block reports the window `/usage` itself ran in, so a capture taken after a resumed or re-entered session can read `$0.00 / 0 tokens` while this table is populated. Where they disagree, the larger non-zero source is the session._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-opus-5 | 267 | 150,023 | 34,900,382 | 973,981 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $82.43
   Total duration (API):  1h 50m 57s
   Total duration (wall): 10h 34m 0s
   Total code changes:    4934 lines added, 202 lines removed
   Usage by model:
       claude-haiku-4-5:  754 input, 16 output, 0 cache read, 0 cache write ($0.0008)
          claude-opus-5:  33.0k input, 409.1k output, 88.4m cache read, 2.7m cache write ($75.40)
        claude-sonnet-5:  1.1k input, 71.4k output, 11.9m cache read, 634.3k cache write ($7.03)

   Current session
   ██▌                                                5% used
   Resets 11:50am (America/Detroit)

   Current week (all models)
   █████████████▌                                     27% used
   Resets Aug 11, 7pm (America/Detroit)
   +50% weekly limits promo through Aug 19 · clau.de/cc-50-promo

   Current week (Fable)
   ███████████▌                                       23% used
   Resets Aug 11, 7pm (America/Detroit)

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   91% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   70% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   45% of your usage came from subagents under
   "superpowers:subagent-driven-development"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   55% of your usage came from plugin "superpowers"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   Skills                  % of usage
   /superpowers:subagent-drive…    8%
   /andrej-karpathy-skills:kar…    3%
   /code-review                    2%
   /superpowers:writing-plans      1%
   /superpowers:brainstorming      1%

   Subagents               % of usage
   superpowers:subagent-driven…   45%
   psh-implementer                17%
   psh-reviewer                    6%

   Plugins                 % of usage
   superpowers                    55%
   andrej-karpathy-skills          3%
```

## Context window (approximate)

- **Largest prompt sent:** ~380,299 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


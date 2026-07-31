# Session statistics

## Session metadata

- **Started:** 2026-07-31T12:16:22.662000+00:00
- **Ended:** 2026-07-31T14:22:16.673000+00:00
- **Duration:** 125 min
- **Model(s):** <synthetic>, claude-opus-5
- **Assistant turns:** 154
- **Tool calls:** Bash × 93, Edit × 32, Read × 22, Skill × 4, Write × 3, AskUserQuestion × 2, Agent × 2

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format. Compare against the embedded `/usage` below, but do not assume it wins: its per-session block reports the window `/usage` itself ran in, so a capture taken after a resumed or re-entered session can read `$0.00 / 0 tokens` while this table is populated. Where they disagree, the larger non-zero source is the session._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| <synthetic> | 0 | 0 | 0 | 0 |
| claude-opus-5 | 286 | 179,032 | 35,093,928 | 1,150,216 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $0.0000
   Total duration (API):  0s
   Total duration (wall): 26s
   Total code changes:    0 lines added, 0 lines removed
   Usage:                 0 input, 0 output, 0 cache read, 0 cache write

   Current session
   ████████                                           16% used
   Resets 1:10pm (America/Detroit)

   Current week (all models)
   ████████████████▌                                  33% used
   Resets Aug 4, 7pm (America/Detroit)
   +50% weekly limits promo through Aug 19 · clau.de/cc-50-promo

   Current week (Fable)
   ██████████████████████▌                            45% used
   Resets Aug 4, 7pm (America/Detroit)

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   100% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   83% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   15% of your usage came from subagents under "psh-reviewer"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   Skills                  % of usage
   /mattpocock-skills:tdd          4%
   /archive-session                4%
   /code-review                    3%
   /andrej-karpathy-skills:kar…    3%
   /superpowers:writing-plans      2%
   /superpowers:brainstorming      2%
   /mattpocock-skills:grilling     1%
   /mattpocock-skills:diagnosi…    1%

   Subagents               % of usage
   psh-reviewer                   15%
   mattpocock-skills:tdd           3%

   Plugins                 % of usage
   mattpocock-skills               9%
   superpowers                     4%
   andrej-karpathy-skills          3%
```

## Context window (approximate)

- **Largest prompt sent:** ~412,687 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


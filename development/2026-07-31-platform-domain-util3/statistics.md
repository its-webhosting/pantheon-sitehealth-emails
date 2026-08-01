# Session statistics

## Session metadata

- **Started:** 2026-07-31T16:15:39.017000+00:00
- **Ended:** 2026-08-01T11:46:06.232000+00:00
- **Duration:** 1170 min
- **Model(s):** claude-opus-5
- **Assistant turns:** 156
- **Tool calls:** Bash × 71, Agent × 28, TaskUpdate × 28, TaskCreate × 14, Edit × 14, AskUserQuestion × 7, SendMessage × 7, Read × 6, Write × 5, Skill × 4, ToolSearch × 2

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format. Compare against the embedded `/usage` below, but do not assume it wins: its per-session block reports the window `/usage` itself ran in, so a capture taken after a resumed or re-entered session can read `$0.00 / 0 tokens` while this table is populated. Where they disagree, the larger non-zero source is the session._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-opus-5 | 307 | 242,596 | 48,705,291 | 1,104,828 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $185.81
   Total duration (API):  4h 41m 45s
   Total duration (wall): 19h 27m 41s
   Total code changes:    12105 lines added, 554 lines removed
   Usage by model:
       claude-haiku-4-5:  84.3k input, 2.3k output, 0 cache read, 0 cache write ($0.0956)
          claude-opus-5:  70.6k input, 569.5k output, 108.0m cache read, 2.8m cache write ($90.39)
        claude-sonnet-5:  8.2k input, 783.3k output, 214.3m cache read, 5.1m cache write ($95.33)

   Current session
   ▌                                                  1% used
   Resets 12:40pm (America/Detroit)

   Current week (all models)
   ████████████████████                               40% used
   Resets Aug 4, 7pm (America/Detroit)
   +50% weekly limits promo through Aug 19 · clau.de/cc-50-promo

   Current week (Fable)
   ██████████████████████▌                            45% used
   Resets Aug 4, 7pm (America/Detroit)

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   97% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   77% of your usage came from sessions active for 8+ hours
    These are often background/loop sessions. Continuous usage can add up quickly
    so make sure it is intentional.

   76% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   38% of your usage came from subagents under "psh-implementer"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   Skills                  % of usage
   /mattpocock-skills:tdd          2%
   /code-review                    2%
   /superpowers:subagent-drive…    2%
   /archive-session                2%
   /superpowers:writing-plans      1%
   /superpowers:brainstorming      1%
   /andrej-karpathy-skills:kar…    1%

   Subagents               % of usage
   psh-implementer                38%
   psh-reviewer                   17%
   superpowers:subagent-driven…    3%
   mattpocock-skills:tdd           2%
   andrej-karpathy-skills:karp…    1%

   Plugins                 % of usage
   superpowers                     6%
   mattpocock-skills               4%
   andrej-karpathy-skills          1%
```

## Context window (approximate)

- **Largest prompt sent:** ~493,288 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


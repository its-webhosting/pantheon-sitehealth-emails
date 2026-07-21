# Session statistics

## Session metadata

- **Started:** 2026-07-21T00:01:20.739000+00:00
- **Ended:** 2026-07-21T00:59:36.272000+00:00
- **Duration:** 58 min
- **Model(s):** claude-fable-5
- **Assistant turns:** 51
- **Tool calls:** Bash × 28, Read × 9, Agent × 4, Skill × 3, Write × 3, mcp__codegraph__codegraph_explore × 2, ToolSearch × 1, Edit × 1

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format; the embedded `/usage` below is authoritative for tokens and cost._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-fable-5 | 94 | 86,298 | 8,668,918 | 235,585 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
   Session

   Total cost:            $29.46
   Total duration (API):  41m 26s
   Total duration (wall): 56m 54s
   Total code changes:    2184 lines added, 79 lines removed
   Usage by model:
       claude-haiku-4-5:  531 input, 14 output, 0 cache read, 0 cache write ($0.0006)
         claude-fable-5:  690 input, 85.2k output, 8.9m cache read, 234.2k cache write ($17.87)
        claude-sonnet-5:  318 input, 106.5k output, 20.3m cache read, 422.7k cache write ($9.28)
        claude-opus-4-8:  35 input, 12.3k output, 2.2m cache read, 140.7k cache write ($2.31)

   Current session
   ████▌                                              9% used
   Resets 12:49am (America/Detroit)

   Current week (all models)
   ███████                                            14% used
   Resets Jul 21, 6:59pm (America/Detroit)
   +50% weekly limits promo through Aug 19 · clau.de/cc-50-promo

   Current week (Fable)
   ███████▌                                           15% used
   Resets Jul 21, 6:59pm (America/Detroit)

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   96% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   61% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   33% of your usage came from subagents under
   "superpowers:subagent-driven-development"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   31% of your usage came from /superpowers:subagent-driven-development
    Heavy skills can be scoped down or run with a cheaper model via skill
    frontmatter.

   71% of your usage came from plugin "superpowers"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   12% of your usage came from MCP server "codegraph"
    MCP tool results stay in context for the rest of the session. /compact to flush
    them, or disable servers you don't need.

   Skills                  % of usage
   /superpowers:subagent-drive…   31%
   /andrej-karpathy-skills:kar…    9%
   /superpowers:writing-plans      7%
   /archive-session                6%

   Subagents               % of usage
   superpowers:subagent-driven…   33%
   psh-implementer                 2%
   psh-reviewer                    1%

   Plugins                 % of usage
   superpowers                    71%
   andrej-karpathy-skills          9%

   MCP servers             % of usage
   codegraph                      12%
```

## Context window (approximate)

- **Largest prompt sent:** ~257,057 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


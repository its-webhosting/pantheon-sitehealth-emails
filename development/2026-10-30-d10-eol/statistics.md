# Session statistics

## Session metadata

- **Started:** 2026-10-30T13:35:17.523000+00:00
- **Ended:** 2026-10-30T15:16:54.410000+00:00
- **Duration:** 101 min
- **Model(s):** claude-opus-5-5
- **Assistant turns:** 109
- **Tool calls:** Bash × 61, Agent × 10, Skill × 6, AskUserQuestion × 4, Edit × 3, WebFetch × 2, Write × 2, Read × 2, ToolSearch × 1, mcp__codegraph__codegraph_explore × 1, SendMessage × 1

## Token usage

_Per-model totals from the session JSONL, deduped per request. **Approximate** — the JSONL is Claude Code's internal format. Compare against the embedded `/usage` below, but do not assume it wins: its per-session block reports the window `/usage` itself ran in, so a capture taken after a resumed or re-entered session can read `$0.00 / 0 tokens` while this table is populated. Where they disagree, the larger non-zero source is the session._

| Model | Input | Output | Cache read | Cache write |
|---|--:|--:|--:|--:|
| claude-opus-5-5 | 262 | 85,124 | 23,959,585 | 292,049 |

## Cost — Claude Code `/usage`

_Captured from Claude Code's `/usage` at archive time; Claude Code estimates cost locally from token counts._

```
Session

Total cost:            $18.91
Total duration (API):  32m 47s
Total duration (wall): 1h 38m 56s
Total code changes:    381 lines added, 8 lines removed
Usage by model:
    claude-haiku-5-5:  48.9k input, 10.2k output, 726.4k cache read, 110.1k cache write ($0.0797)
     claude-opus-5-5:  50.3k input, 148.9k output, 42.8m cache read, 801.5k cache write ($16.62)
   claude-sonnet-5-5:  5.5k input, 23.8k output, 4.7m cache read, 594.9k cache write ($2.21)
Prompt cache (main):   106 requests · 99% of input tokens from cache · no misses · warm (1h TTL, last activity 30s ago)


Plugin skill-listing footprint
What each plugin's skill descriptions add to the system prompt (cached input after the first turn). Agents and MCP tools not yet counted.

claude-md-management        1 skill · ~30 tok/turn

Total                       ~30 tok/turn

Current session
█▌                                                 3% used
Resets 2:29pm (America/Detroit)

Current week (all models)
▌                                                  1% used
Resets Nov 3, 5:59pm (America/Detroit)

Current week (Fable)
                                                   0% used
Resets Nov 3, 6pm (America/Detroit)

What's contributing to your usage?
Approximate · sessions on this machine only

Last 24h · shares overlap

100% Give "psh-reviewer" subagents a cheaper model
55%  Start fresh when you switch tasks · run /clear
22%  Trim /workspace/CLAUDE.md · 33k tokens per request
17%  Review the "superpowers" plugin

Skills                  % of usage
/superpowers:subagent-drive…    5%
/superpowers:writing-plans      4%
/andrej-karpathy-skills:kar…    4%
/superpowers:brainstorming      3%
/superpowers:finishing-a-de…    1%

Subagents               % of usage
psh-reviewer                   43%
psh-implementer                 4%
superpowers:subagent-driven…    3%

Plugins                 % of usage
superpowers                    17%
andrej-karpathy-skills          4%

MCP servers             % of usage
codegraph                       2%
```

## Context window (approximate)

- **Largest prompt sent:** ~327,802 tokens (input + cache read + cache write on the biggest single turn)

_Approximate: reconstructed from the JSONL after the fact. The exact live `/context` breakdown by component can't be reproduced post-hoc._


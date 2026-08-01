#!/usr/bin/env bash
# UserPromptSubmit hook: run `codegraph prompt-hook`, but ONLY on prompts a human typed.
#
# WHY: the hook fires on every UserPromptSubmit, and a background task's completion report
# arrives through that same event.  Those reports are long, and they are full of identifier-
# shaped words -- so CodeGraph matches on them and injects a ~16 KB structural context block
# about code the turn has nothing to do with.  Measured over one 19-hour session: 10 of the
# injections overflowed the context limit and were spilled to disk (159 KB total), and the
# matches were things like `plan_costs` (from the word "plan"), `ApiSession` (from "session")
# and `FakeAddress` (from "address").  Zero were relevant.  Every one of those turns was a
# task notification, not a question.
#
# WHAT IS GATED, exhaustively: prompts carrying the task-notification envelope.  Slash-command
# output is deliberately NOT gated -- `/code-review`, `/usage` and friends are things the human
# actually invoked, and gating them would be a judgment call about content rather than about
# authorship.
#
# CONTRACT (verified by running the binary, not assumed):
#   * input  = JSON on STDIN; the prompt text is at `.prompt`.
#   * output = stdout is injected into the model's context verbatim.  Emitting nothing is how
#              a hook declines to contribute; `codegraph prompt-hook` already does this for a
#              prompt with no code content (measured: `{"prompt":"thanks"}` -> no output).
#   * exit   = always 0.  ADVISORY, like ruff-check.sh: a hook that failed loudly because its
#              own binary moved would block every prompt in the session.
#
# STDIN IS READ ONCE.  It is buffered into a variable and replayed, because a `tee`/pipeline
# form would consume it before the decision is made.
set -uo pipefail

payload=$(cat)

# `.prompt // ""` so a payload shape change degrades to "not a notification" -> hook still
# runs.  Failing OPEN is right here: the cost of a stray injection is tokens, while the cost
# of failing closed is silently disabling CodeGraph for the whole session.
prompt=$(printf '%s' "$payload" | jq -r '.prompt // ""' 2>/dev/null) || prompt=""

case "$prompt" in
  *'<task-notification>'*|*'[SYSTEM NOTIFICATION - NOT USER INPUT]'*)
    exit 0
    ;;
esac

printf '%s' "$payload" | codegraph prompt-hook || true

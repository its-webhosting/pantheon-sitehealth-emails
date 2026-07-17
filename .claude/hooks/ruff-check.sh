#!/usr/bin/env bash
# PostToolUse hook: lint the file Claude just edited, and hand any findings straight back.
#
# WHY: prompts/directives.md PD#2 forbids blind/bare excepts and PD#6 forbids hardcoded
# secrets.  Those used to be prose that a fresh-context subagent had to be told about;
# ruff detects them, and this hook delivers the detection at the moment of the mistake
# rather than at ./run-tests time.  It corrects a subagent without any standard needing to
# be injected.
#
# CONTRACT (read from the authority, not assumed -- an earlier draft of the spec got this
# wrong and would have printed into the void):
#   * input  = JSON on STDIN, with the path at .tool_input.file_path.  NOT argv.
#   * output = plain stdout on exit 0 is DISCARDED.  Returning text to the model requires
#              the hookSpecificOutput.additionalContext envelope below.
#   * exit   = always 0.  This is ADVISORY; ./run-tests is the gate.  A hook that blocked
#              on its own breakage would halt work over a broken instrument.
#
# SECURITY: file_path is model-controlled text.  It is never word-split, never eval'd, and
# never interpolated unquoted -- `ruff check -- "$FILE"` with the `--` separator, plus the
# repo-root containment check.  `ruff check $FILE` unquoted is command injection.
#
#     stdin JSON ──> jq .tool_input.file_path ──> nil? ─yes─> exit 0 (silent)
#                                                   │no
#                                                   ▼
#                                        *.py or the extension-less
#                                        main script? ─no─> exit 0 (silent)
#                                                   │yes
#                                                   ▼
#                                        inside repo root? ─no─> exit 0 (silent)
#                                                   │yes
#                                                   ▼
#                                        ruff check -- "$FILE"
#                                                   │
#                                    clean ─────────┴───────── findings
#                                      │                          │
#                                exit 0 (silent)      envelope -> exit 0
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Emit the ONLY thing the model actually receives.  jq builds it so the payload is escaped
# correctly no matter what ruff printed.
emit() {
    jq -n --arg ctx "$1" \
        '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $ctx}}' \
        2>/dev/null || true
    exit 0
}

command -v jq >/dev/null 2>&1 || exit 0   # no jq: cannot read input OR emit output.

# --- Nil shadow paths: no stdin, malformed JSON, no tool_input, no/empty/null file_path.
# `|| true` because set -e would otherwise kill us on a jq parse failure, which is a
# perfectly ordinary thing for a hook to be handed.
INPUT="$(cat 2>/dev/null || true)"
[ -n "$INPUT" ] || exit 0
FILE="$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)"
[ -n "$FILE" ] || exit 0

# --- Resolve and contain.  A path outside the repo is not ours to lint, and `..` traversal
# must not reach out of the tree.
case "$FILE" in
    /*) ABS="$FILE" ;;
    *)  ABS="$REPO_ROOT/$FILE" ;;
esac
ABS="$(realpath -m -- "$ABS" 2>/dev/null || true)"
[ -n "$ABS" ] || exit 0
[ -f "$ABS" ] || exit 0
case "$ABS" in
    "$REPO_ROOT"/*) ;;
    *) exit 0 ;;
esac

# --- Python only.  The main program is EXTENSION-LESS, so it needs its own arm; the
# committed pantheon-sitehealth-emails.py symlink is what ruff/pyright/CodeGraph resolve
# it through, but an edit lands on the real file.
case "$ABS" in
    *.py) ;;
    "$REPO_ROOT/pantheon-sitehealth-emails") ;;
    *) exit 0 ;;
esac

# --- Lint.  No --select here ON PURPOSE: ruff walks up from the file to /workspace's
# pyproject.toml, so the hook and ./run-tests share ONE rule set.  Duplicating the flags
# would be a second source of truth, and two sources drift.
# `ruff` is not on PATH in this environment; uvx is.
if command -v ruff >/dev/null 2>&1; then
    RUFF=(ruff)
elif command -v uvx >/dev/null 2>&1; then
    RUFF=(uvx ruff)
else
    exit 0   # Upstream error: no linter.  Advisory hook, so stay quiet and let ./run-tests gate.
fi

OUT="$("${RUFF[@]}" check --quiet --output-format concise -- "$ABS" 2>&1)" && STATUS=0 || STATUS=$?

[ "$STATUS" -eq 0 ] && exit 0   # clean: emit NOTHING.
[ -n "$OUT" ] || exit 0

emit "ruff findings in the file you just edited (project rule set; see pyproject.toml).
These mechanize prompts/directives.md PD#2 (every error has a name) and PD#6 (secrets never
hardcoded).  Fix them now, or add a noqa WITH AN INLINE REASON if the code is deliberate --
a bare noqa is a silent failure.

${OUT}"

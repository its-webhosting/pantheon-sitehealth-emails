# Implementation Standards

A **standards overlay** for the `superpowers:subagent-driven-development` skill. The skill
drives the *process* (read plan → dispatch a fresh implementer per task → task review →
fix loop → whole-branch review → finish the branch). This file defines the *bar* and the
*judgment* to apply inside that flow. Where they overlap, the skill owns the process; this
file owns the standards. Nothing here restates skill mechanics (model selection, the
review-package/task-brief scripts, the progress ledger, status handling) — read the skill
for those.

## Posture

You are a senior software architect (12+ years of Python CLI tooling, REST APIs, WebOps,
and WordPress/Drupal hosting) whose judgment produces better solutions and higher-quality
code than 99% of developers. During execution the bar is not "does the task pass its
reviewer" — it is **"would this survive adversarial review"** (`prompts/adversarial-review.md`).
Build to that bar the first time so the fix loop stays short.

## How this overlay is applied (read first)

You are the **controller**. Implementer and reviewer subagents have fresh context: they
never see this file, the spec conversation, or `CLAUDE.md` unless you put it in front of
them. **An un-injected standard does not exist.** Your job is to fold the standards each
task actually touches into that task's dispatch — not the whole file, only the relevant
subset (same curation principle the skill applies to context).

| Dispatch | What you inject from this file |
|---|---|
| **Implementer brief** | The house-style rules the task will trip (§ Fresh-context trap), the error/shadow/observability/security directives for the code paths it touches (§ Directives), the exact test tier and the load-bearing-tests rule (§ Test discipline), and the Definition of Done (§ DoD). |
| **Reviewer constraints-block** | The same binding requirements, stated as *what the code must do* — the reviewer's attention lens. Copy exact spec values verbatim. Do **not** tell the reviewer what to downgrade or ignore; that is the skill's rule and it holds. |
| **Fix-subagent dispatch** | Only the standard(s) the finding implicates, plus the covering test files. |

**Plan-vs-standards conflict.** If the plan mandates something this file treats as a defect
(a catch-all handler, a test that asserts nothing, `terminus` where a wrapper exists), that
is a human decision — surface the finding beside the plan text and ask which governs. Fold
it into the skill's pre-flight plan scan; don't silently "fix" the plan.

**TDD override.** The skill defaults subagents to `test-driven-development`. This project
does **not** — `CLAUDE.md` states tests *follow* the change. Tell each implementer so
explicitly. Test-first ordering is optional here; what is non-negotiable is that the change
ships **with** its tests in the same commit (§ DoD).

## Directives at implementation time

Your Prime Directives (`prompts/new-feature-standards.md`), re-expressed as what the
implementer does **in code** — inject the ones each task touches:

1. **Every error has a name — in code.** Raise a named exception (this codebase uses
   `TerminusError` and friends), add the test that trips it, and wire the operator-visible
   message at the right verbosity. `except Exception`/bare `except` is a review defect —
   call it out, don't write it.
2. **Zero silent failures.** A code path that can fail without the system, the operator, or
   the run's exit status showing it is a defect, not a smaller version of done.
3. **Shadow paths are written and tested.** For every new flow, implement and cover the
   three shadows beside the happy path: nil input, empty/zero-length input, upstream error.
4. **Runs are not atomic — code for partial state.** Idempotent DB writes (`ON CONFLICT DO
   NOTHING` / `INSERT IGNORE`), honor `--resume-from`, no partial-write-then-fail, and never
   weaken the `--for-real`/dry-run gate.
5. **Observability is code you write now.** `debug()` at the correct `-v`/`-vv`/`-vvv` level,
   actionable operator messages, dry-run visibility — not a follow-up task.
6. **Security is not optional.** Secrets flow through `<{secret env …}>` config
   substitutions — never read from the environment, never logged, never committed.
   Threat-model any new outbound HTTP/subprocess path; route it through the existing
   monkeypatchable seams.
7. **Update the diagram comment when you change the flow it describes.** A stale ASCII
   diagram in a docstring/comment is worse than none; updating it is part of the change.
8. **Everything deferred is written down** — as a `README.md` TODO or a named follow-up, in
   the same commit. Vague intentions are lies.
9. **Terminology stays consistent** with the surrounding code and the spec's glossary. Fix
   drift you introduce; flag drift you find.

## The fresh-context trap — house style a new subagent will get wrong

- **Use the wrappers, not the raw tools.** `run_terminus`/`terminus`/`terminus_data`,
  `wp`/`wp_eval`, `drush`/`drush_php_script` (all return 3-tuples); build failure notices
  with `wp_error`/`drush_error`. Never shell out to `terminus`/`wp`/`drush` directly.
- **Add notices/sections via the `SiteContext` methods** (`add_notice`, `add_section`,
  `add_attachment`) — the module-level free functions are gone. Every notice needs a `csv`
  key.
- **Wire new behavior through the `sc.PHASES` seams** and honor the per-phase data contract;
  don't reach across phases for data the contract doesn't guarantee yet.
- **Follow the local idioms even where non-idiomatic** — e.g. the `-> (str, str, bool)`
  tuple type hints. This is house style; don't "correct" it.
- **Prefer the Pantheon API over `terminus` for new code** unless `terminus` is clearly
  better (missing endpoint, materially simpler/cleaner, better result). State which and why.

## Definition of Done (per task)

The bar the task reviewer verifies against. A task is done only when **all** hold:

- Tests for the change added/adjusted in the same commit, at the right tier, and **run with
  the command and output pasted** — evidence, never "should pass" or a summarized "green."
- House style matched (§ Fresh-context trap); no unrequested scope, no gold-plating.
- Directives for the touched paths satisfied (§ Directives) — named errors, shadow paths,
  observability, secrets handled.
- Diagram comments and `README.md` TODO updated; memory updated with any non-obvious gotcha
  or decision.
- No debug cruft (stray prints, commented-out code, temp files) left behind.

## Test discipline

- **Tests are load-bearing.** Never weaken an assertion, add a `sleep`/retry, or loosen a
  matcher to turn a test green. A failing test is a signal to fix the code, not the test.
- **Right tier, `./run-tests --fast` as the inner loop.** Match the change to its tier
  (`unit`/`integration`/`e2e`/`render`/`email`/`live`); pure logic gets a unit/property test,
  a new report path gets a golden or e2e assertion.
- **Golden/fixture regeneration requires a reviewed diff.** `--update-goldens`/`--record` is
  never a reflex to make a test pass — inspect the diff and justify every changed byte.
- **Respect the safety interlock.** No `--all`/`-a`/`--for-real`, and no live/non-fixture
  `--create-tables`/`--import-older-metrics` in tests. Route new I/O through the existing
  mock seams (`run_terminus`, the `httpseam`/`egress` probes) so it stays offline-testable.

## Deviation & debugging discipline

- **No silent deviation.** If the plan is wrong or underspecified, the implementer surfaces
  it via the skill's `DONE_WITH_CONCERNS`/`BLOCKED`/`NEEDS_CONTEXT` status — it never
  quietly changes the plan's intent or invents scope.
- **Root cause, not symptom.** On a failure or surprising behavior, debug systematically
  (`superpowers:systematic-debugging`) to the actual cause. Never mask it with a catch-all,
  a retry-until-green, or a broadened exception.
- **Right-sized diff.** The smallest change that cleanly expresses the task — but don't
  compress a necessary rewrite into a minimal patch. If the foundation the task sits on is
  broken, raise it (Prime Directive #12) rather than building on it.

## Commit hygiene

- Atomic **conventional commits** (`feat:`/`fix:`/`docs:` — matching this repo's log), one
  logical change each, tests included in the same commit as the code they cover.
- End commit messages with the `Co-Authored-By` trailer this environment requires.
- Never commit secrets, `.env` contents, or unreviewed golden/fixture regenerations.

## This project's context

Read `CLAUDE.md` for the conventions every change must respect — the single-file core plus
self-registering `plugin/`/`check/` packages, the `sc.PHASES` seams and per-phase data
contract, the test harness and its interlock, the Pantheon-API preference, and keeping
institution-specific logic behind config flags / the `umich` packages so the tool stays
reusable by other institutions.

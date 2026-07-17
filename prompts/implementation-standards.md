# Implementation Standards

A **standards overlay** for the `superpowers:subagent-driven-development` skill. The skill
drives the *process* (read plan → dispatch a fresh implementer per task → task review →
fix loop → whole-branch review → finish the branch). This file defines the *bar* and the
*judgment* to apply inside that flow. Where they overlap, the skill owns the process; this
file owns the standards. Nothing here restates skill mechanics (model selection, the
review-package/task-brief scripts, the progress ledger, status handling) — read the skill
for those.

> **Read `prompts/directives.md` first** — the Spine. This file does not restate a rule from
> it; it says what those rules mean **in code**, and cites them by number.

## Posture — during execution

The bar is not "does the task pass its reviewer" — it is **"would this survive adversarial
review"** (`prompts/adversarial-review.md`). Build to that bar the first time so the fix
loop stays short.

## How this overlay is applied (read first)

You are the **controller**. Implementer and reviewer subagents have fresh context: they
never see this file, the spec conversation, or `CLAUDE.md` unless it reaches them somehow.
**An un-injected standard does not exist.**

**Dispatch every code-touching subagent as `psh-implementer`, and every reviewer as
`psh-reviewer`** (`.claude/agents/`). Those agent definitions carry the read list, so the
standards arrive as **configuration** rather than as prose you must remember to paste:

```
Before doing anything, read IN FULL:
  1. prompts/directives.md               (the standards spine)
  2. prompts/implementation-standards.md (implementation bar + house style)
  3. CLAUDE.md — the sections the task touches
  4. the task brief and the spec named in the dispatch
```

`superpowers:subagent-driven-development`'s template dispatches `Subagent
(general-purpose)`. **Override it**, here in the same way and place this file already
overrides the TDD default. Fix-subagents are code-touching and dispatch as
`psh-implementer` too.

> **Why not curate.** An earlier version of this file told the controller to inject "not the
> whole file, only the relevant subset." That makes standards delivery depend on the
> controller's judgment at the moment its context is fullest and momentum highest — which is
> exactly when standards got dropped. A fixed list removes the judgment. The Spine is small
> enough (≤9 KB) that reading it in full costs nothing worth optimizing: the whole read list
> is ~4.7k tokens per dispatch.

**Every task report MUST cite the Spine directives it applied — by number — and quote a
verbatim clause from each.** Grep the quotes against `prompts/directives.md`; a paraphrase
fails. This is the only observable that separates "read the standards" from "did not," and
PD#14 forbids an instrument that cannot go red.

**Do not tell a reviewer what to downgrade or ignore.** That is the skill's rule and it
holds regardless of how inconvenient a finding is.

**Plan-vs-standards conflict.** If the plan mandates something this file treats as a defect
(a catch-all handler, a test that asserts nothing, `terminus` where a wrapper exists), that
is a human decision — surface the finding beside the plan text and ask which governs. Fold
it into the skill's pre-flight plan scan; don't silently "fix" the plan.

**TDD override.** The skill defaults implementer subagents to
`superpowers:test-driven-development`. This project uses **`mattpocock-skills:tdd`** instead
— inject it by name in every implementer brief, because **the host's default wins silently if
you don't**. The two differ in ways that decide the work here:

- **Test only at pre-agreed seams.** Matt's skill forbids a test at an unconfirmed seam and
  tells the implementer to confirm seams *with the user* — an implementer subagent has fresh
  context and cannot. So **the spec declares the seams** (§ *Spec & internal-doc quality bar*
  in `new-feature-standards.md`) and you copy them into the brief verbatim. A task whose spec
  names no seam is `NEEDS_CONTEXT`, not a licence to pick one.
- **Refactoring is not part of the red→green loop.** It belongs to review
  (`prompts/adversarial-review.md`), not the implementer's cycle. Superpowers' TDD puts it
  inside the loop; here it doesn't go there.

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
7. **Where a diagram exists in a comment or docstring, updating it is part of changing the
   flow it describes** — a stale ASCII diagram is worse than none. Writing one in code is
   REQUIRED only where the flow is **non-local** (spans files, packages, or phase seams);
   the design/spec is where diagrams are mandatory (PD#8).
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

- Tests for the change **written first at the spec's declared seam, watched fail for the
  right reason**, then added/adjusted in the same commit at the right tier, and **run with
  the command and output pasted** — evidence, never "should pass" or a summarized "green."
  (Carve-outs in § Test discipline are the exhaustive exceptions.)
- House style matched (§ Fresh-context trap); no unrequested scope, no gold-plating.
- Directives for the touched paths satisfied (§ Directives) — named errors, shadow paths,
  observability, secrets handled.
- Diagram comments and `README.md` TODO updated; memory updated with any non-obvious gotcha
  or decision.
- No debug cruft (stray prints, commented-out code, temp files) left behind.
- **The report cites the Spine directives applied — by number, with a verbatim quote from
  each** (§ How this overlay is applied).
- **`CLAUDE.md` prose that existed to explain logic this task moved into a package is
  deleted in the same commit.** Report the line-count delta. **EXEMPT:** prose recording a
  shipped defect's root cause and its non-obvious repair — **unless a named test already
  guards that defect**, in which case it reduces to a one-line pointer at that test. Prose
  is not exempt merely for being old, long, or architectural. *Intent:* much of `CLAUDE.md`
  stands in for structure the code doesn't express, and retires with it; defect knowledge
  does not, and deleting a line of it re-opens a closed defect. Where a test guards the
  defect, the test is the durable record — it can go red; prose cannot.

## Test discipline

- **Test-first, at the seams the spec declares.** Write the failing test, **watch it fail for
  the right reason**, then write the minimal code to pass. A test that passes the moment you
  write it is testing existing behavior — fix the test, don't move on. One seam, one test,
  one minimal implementation per cycle (vertical slices, not all-tests-then-all-code).
- **No seam above the golden? Make one — or say why not, in the spec.** If a core `main()`
  change has no honest seam, extracting a pure module-level helper is **part of the change**;
  that is how `overage_blocks`, `plan_costs`, `sites_from_resume_point` and the rest came to
  exist, behavior-preserving with the goldens byte-identical. The escape hatch is explicit and
  lives in the spec ("no seam is worth making here, because…") — never a silent skip. If you
  discover mid-task that the seam the spec named doesn't hold, that is
  `DONE_WITH_CONCERNS`/`BLOCKED`, not an improvised seam.
- **Carve-outs from test-first — exhaustive, not illustrative.** These are the only places
  red→green is structurally impossible, because the expected value is derived from the code
  that just ran:
  1. **A new golden or syrupy snapshot** (`--update-goldens`) — written after, with the
     initial content reviewed byte-by-byte as if it were the assertion, because it is.
  2. **Recorded fixtures** (`--record`, `tests/tools/record.py`) — captured from live
     Pantheon; they are inputs, not tests.

  Nothing else is carved out. And the carve-out is *creation only*: **an existing golden going
  red is a signal**, never refreshed to green (see the load-bearing rule below).
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
- **Root cause, not symptom.** On a failure or surprising behavior, debug systematically to
  the actual cause — `/diagnosing-bugs`, under the standards in
  `prompts/debugging-standards.md`, which maps its feedback-loop gate onto this repo's real
  loops. Never mask a failure with a catch-all, a retry-until-green, or a broadened exception.
- **Right-sized diff.** The smallest change that cleanly expresses the task — but don't
  compress a necessary rewrite into a minimal patch. If the foundation the task sits on is
  broken, raise it (Prime Directive #12) rather than building on it.

## Commit hygiene

- Atomic **conventional commits** (`feat:`/`fix:`/`docs:` — matching this repo's log), one
  logical change each, tests included in the same commit as the code they cover.
- End commit messages with the `Co-Authored-By` trailer this environment requires.
- Never commit secrets, `.env` contents, or unreviewed golden/fixture regenerations.

## This project's context

Read `prompts/directives.md` for the standards and `CLAUDE.md` for the conventions every change must respect — the single-file core plus
self-registering `plugin/`/`check/` packages, the `sc.PHASES` seams and per-phase data
contract, the test harness and its interlock, the Pantheon-API preference, and keeping
institution-specific logic behind config flags / the `umich` packages so the tool stays
reusable by other institutions.

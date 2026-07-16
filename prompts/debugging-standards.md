# Debugging Standards

A **standards overlay** for the `/diagnosing-bugs` skill, in the same spirit as
`new-feature-standards.md` is an overlay for `superpowers:brainstorming`. The skill drives
the *process* (feedback loop → reproduce+minimise → hypothesise → instrument → fix+regression
test → cleanup+post-mortem). This file maps that process onto **this repo's actual loops**
and defines the bar. Where they overlap, the skill owns the process; this file owns the
standards.

Use this when something is **broken at runtime** — a failing test, a wrong report, a crashed
`--all` run, a slow gather. It is NOT for defects in a spec or plan document: those go to
`prompts/adversarial-review.md`, which interviews with `/grilling`. `/diagnosing-bugs` gates
on a command that goes red on the bug's code path, which cannot exist for a document.

## Posture

Read `CLAUDE.md` before theorising — **it is this repo's glossary and decision record**
(`docs/agents/domain.md` says the same). The *Architecture* and *Testing* sections already
name most of the traps: the phase seams and their data contract, the DB-resilience rules,
the two rich-console gotchas, the shim system. A hypothesis that contradicts one of those is
usually wrong, and several of the bugs this codebase has actually shipped are documented
there as settled findings — check before rediscovering one.

## Phase 1 — the feedback loop, in this repo

The skill's Phase 1 gate is non-negotiable: **one command, already run at least once, output
pasted, red-capable on the user's exact symptom, deterministic, fast, agent-runnable.** No
red-capable command, no Phase 2. Here is where those loops come from — roughly in order of
preference, because this list is ordered by tightness:

1. **`./run-tests --fast`, narrowed to one test** — the offline inner loop, seconds, fully
   deterministic. Always try this first.
2. **A new test at an existing seam.** All Pantheon/WP/Drush I/O funnels through
   `run_terminus()` — monkeypatch it. `dns_classify.resolve` is the one DNS seam.
   `check/cloudflare/httpseam.py` (`fetch`/`sleep`) and `egress.probe` are the HTTP seams.
   Prefer an existing seam to a new one; see `/codebase-design` for the vocabulary.
3. **The pure-helper seam.** `overage_blocks`, `contract_year_end`, `estimate_month_visits`,
   `plan_costs`, `build_plan_over_time`, `sites_from_resume_point`, `merge_prior_results`
   are module-level defs precisely so a bug in them is one function call away from a loop.
4. **A subprocess run via `run_program()`** with the PATH-shim fake `terminus` and the
   fixture config. The **only** sanctioned way to run the program in a subprocess — it fails
   closed on `--all`/`--for-real`/live `--create-tables`. Never bypass the interlock to get a
   repro; if the bug appears to need `--all`, that is a finding, not a licence.
5. **The subprocess shims** in `tests/shims/pyshim/` — `dbshim` (`DB_SHIM_FAIL`, simulates
   MySQL 2013 inside a `db_retry()` unit) and `dnsshim` (`DNS_SHIM_ZONE`). Add a new shim as
   **another module there**, never a second shim directory: two `sitecustomize.py` files means
   one silently never runs, and a `not in`-shaped assertion then passes green against a run
   that did nothing.
6. **A golden diff.** Four e2e goldens exist; a byte diff against one is a sharp signal for
   rendering and pipeline bugs.
7. **A property/fuzz loop** (Hypothesis is already in the suite) when the symptom is
   "sometimes wrong output".

### Loop-construction rules specific to this repo

- **Reproduce production's console, don't hide it.** `recording_console(monkeypatch, sc,
  width=…)` takes a `width` — production runs non-tty at **80 columns and hard-wraps**. The
  helper's wide default is what made the suite blind to the wrapped-resume-command bug. If
  the symptom is anything about operator output, set `width=80` or your loop is not
  red-capable.
- **Never point a loop at live sites or the production DB.** Tests use only
  `its-wws-test1`/`its-wws-test2`, read-only. A loop that needs live data is not
  agent-runnable and not deterministic — build a fixture instead.
- **Reaching for `-vvv` is not a loop.** It's instrumentation (Phase 4). A verbosity flag
  that shows you the bug still isn't a pass/fail signal.

## Phase 3–4 — hypothesise and instrument

- The skill wants **3–5 ranked falsifiable hypotheses before testing any**. Show me the list.
  I often know which one to promote.
- Tag every debug log with a unique prefix (`[DEBUG-a4f2]`) so cleanup is one grep. But note:
  **`sc.console` has markup enabled and silently deletes any `[lowercase…]` fragment** — your
  own tag will vanish, and an unmatched `[/…]` raises `MarkupError`. Use
  `rich.markup.escape()`, or log through a channel that isn't rich.
- Prime Directive #2 applies to diagnosis, not just design: **every error has a name**. Name
  the exception class, what raises it, what catches it, and what I see. "It throws" is not a
  finding.

## Phase 5 — fix + regression test

- **Write the regression test before the fix**, at a correct seam — one that exercises the
  real bug pattern *as it occurs at the call site*. The skill's warning applies sharply here:
  a unit test that can't replicate the chain that triggered the bug gives false confidence.
- **If no correct seam exists, that is the finding.** Say so. Several areas are known-thin:
  `abort_run()`/`finish_run()` and the artifacts are covered only by
  `tests/integration/test_finish_run.py`, `test_abort_run.py`, and `tests/e2e/test_abort_e2e.py`
  — the goldens cover neither stdout nor the artifacts.
- **Tests are load-bearing.** Never regenerate a golden or fixture to make a failure go away.
  A golden diff is a *result*: read it, and only refresh via `./run-tests --update-goldens`
  once you can say why every changed byte changed.
- `./run-tests --fast` for the loop; the **full suite once** before declaring done.

## Phase 6 — post-mortem

The skill's closing question is "what would have prevented this bug?" — and it hands off to
`/improve-codebase-architecture` when the answer is architectural (no good seam, tangled
callers, hidden coupling). That skill is **user-typed only**: I cannot invoke it. So when the
answer is architectural, state the specifics and recommend that I run it — don't try to call it.

Also required here:

1. **Update memory** with the finding (Prime Directive #13), especially when the bug's cause
   contradicts something a reasonable person would have assumed.
2. **Fix the class, not the instance.** When a defect has a class, grep for every instance of
   it before declaring done — the rich-markup and console-width bugs each shipped twice.
3. **Consider whether `CLAUDE.md` should absorb the finding.** Stable rules live there; this
   is how the DB-resilience and rich-console sections came to exist. Use
   `prompts/update-claude-md.md`.
4. **Archive the session** with `/archive-session` if the diagnosis was substantial enough to
   warrant a `development/` folder — scrubbed of secrets, raw JSONL never committed.

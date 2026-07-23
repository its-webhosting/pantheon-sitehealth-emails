# I14b — Ratchet Flip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every implementer dispatches as `psh-implementer`, every reviewer as `psh-reviewer`,
> and uses `mattpocock-skills:tdd` (NOT superpowers:test-driven-development) — the
> overrides in `prompts/implementation-standards.md` govern.

**Goal:** Un-grandfather every remaining tree from the broad ruff ratchet, then merge
`ruff-broad.toml` into `pyproject.toml` so ONE ruff pass + pyright replace today's three
gates — with zero behavior change anywhere.

**Architecture:** Four per-task commits against SPEC.md §2.1–§2.3 (same directory —
the implementer MUST read it in full; its §2 rules and §5 measured tables are the
requirements and are not repeated here). Flip before merge (D-i14b-1): each
un-grandfathering commit keeps BOTH existing configs green; the merge lands on a clean
tree as pure config mechanics.

**Tech Stack:** Python 3.12, pytest via `./run-tests`, ruff PINNED `uvx ruff@0.15.22`,
pyright 1.1.411 (pin lands in Task 4).

## Global Constraints

- ZERO behavior change (SPEC §3): `git diff 1fa1fa7 -- tests/e2e/__snapshots__/` empty
  AND `git diff 1fa1fa7 -- '*.ambr'` empty after EVERY task; collected count stays
  1021 passed / 1 skipped / 2 deselected (fast); stdout, csv, artifacts untouched.
- A lint fix that would touch any string literal, message text, csv value, assertion
  semantics, fixture value, or seam name is FORBIDDEN — `# noqa` + inline reason
  instead (SPEC §2.1 rule 1, §2.2 NEVER block).
- Every `# noqa` carries an inline reason (PD#1); per-file noqa inventory in the report.
- Use `uvx ruff@0.15.22` for every manual ruff invocation (matches the pinned gate).
- `./run-tests --fast` green at every commit.
- Commit messages: conventional, `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Task reports cite Spine directives by number with verbatim quotes, and MUST verify
  their own report file exists on disk after writing (a prior increment had a silent
  Write failure).

---

### Task 1: flip check/dns, check/pantheon_cdn_change, check/umich legacy pair (SPEC §2.1)

**Files:**
- Modify: `ruff-broad.toml` (delete the `check/dns/`, `check/pantheon_cdn_change/`,
  `check/umich/sitelens.py`, `check/umich/cloudflare_cms.py` exclude lines),
  `check/dns/**` (1 finding), `check/pantheon_cdn_change/**` (15),
  `check/umich/sitelens.py` + `check/umich/cloudflare_cms.py` (16).
- Test: no test-file edits — the cover is the existing suites + snapshots.

**Interfaces:**
- Consumes: baseline `8154823`.
- Produces: three more trees under the broad gate; `ruff-broad.toml` exclude list
  reduced to `check/cloudflare/`, `plugin/`, `tests/`, `development/`.

- [ ] **Step 1: Structural RED** — delete the four exclude lines, run
  `uvx ruff@0.15.22 check --config ruff-broad.toml check/dns check/pantheon_cdn_change check/umich/sitelens.py check/umich/cloudflare_cms.py`
  Expected: **32 findings** (per-rule mix in SPEC §5) — the gate now sees the trees.
- [ ] **Step 2: Disposition each finding** per SPEC §2.1's priority rules 1–6 and the
  tail rule (behavior first; pinned signatures noqa; module-state noqa — incl. the two
  `PLW0602` in `sitelens.py`; mechanical fixes only where no literal/seam involved).
- [ ] **Step 3: Verify zero behavior drift**
  Run: `./run-tests --fast` → green, 1021/1/2, 107 snapshots.
  Run: `git diff 1fa1fa7 -- tests/e2e/__snapshots__/ '*.ambr' | wc -l` → 0.
  Run: `uvx ruff@0.15.22 check --config ruff-broad.toml .` → All checks passed!
- [ ] **Step 4: Commit**
```bash
git add -A && git commit -m "feat(campaign-I14b): un-grandfather check/dns, cdn_change, umich legacy pair"
```

### Task 2: flip check/cloudflare + plugin/ (SPEC §2.1)

**Files:**
- Modify: `ruff-broad.toml` (delete the `check/cloudflare/` and `plugin/` lines),
  `check/cloudflare/**` (41 findings), `plugin/**` (39).
- Test: no test-file edits.

**Interfaces:**
- Consumes: Task 1's tree.
- Produces: exclude list reduced to `tests/`, `development/`.

- [ ] **Step 1: Structural RED** — delete the two lines; scoped ruff run shows **80
  findings** (SPEC §5 mix).
- [ ] **Step 2: Disposition** per SPEC §2.1 — note the two NAMED security dispositions
  (`cache.py` S311 seeded-RNG noqa; `egress.py` S104 seam noqa) and rule 6's seam
  surfaces (`httpseam.py`, `egress.py`, `get_env.py`); `PLW0603`/`PLW0602` in
  `get_secret.py`/`portal.py` noqa'd as the module-state idiom.
- [ ] **Step 3: Verify** — same three commands as Task 1 Step 3, same expectations.
- [ ] **Step 4: Commit**
```bash
git add -A && git commit -m "feat(campaign-I14b): un-grandfather check/cloudflare and plugin/"
```

### Task 3: flip tests/ (SPEC §2.2)

**Files:**
- Modify: `ruff-broad.toml` (delete the `tests/` exclude line; ADD the §2.2 idiom block
  verbatim under `[lint.per-file-ignores]` as `"tests/**" = [...]` with its
  justification comments), ~60 test files (the 195-finding remainder).
- Test: the suite itself is the instrument.

**Interfaces:**
- Consumes: Task 2's tree.
- Produces: exclude list reduced to `development/` only; the idiom block that Task 4
  carries into pyproject verbatim.

- [ ] **Step 1: Idiom block + structural RED** — add the block, delete the exclude
  line; `uvx ruff@0.15.22 check --config ruff-broad.toml tests` → **195 findings**
  (2,536 minus the 2,341 the block absorbs — if the number differs, STOP and reconcile
  against SPEC §5 before fixing anything).
- [ ] **Step 2: Autofix pass** — `uvx ruff@0.15.22 check --config ruff-broad.toml --fix tests`
  (safe fixes only; expect ~72: I001/PLR0402/C420/F541…), then re-run the suite BEFORE
  continuing: `./run-tests --fast` → 1021/1/2 (an autofix that breaks a test gets
  reverted and dispositioned by hand).
- [ ] **Step 3: Manual remainder** — per SPEC §2.2's fixed-list + the PLR0913/FBT002
  seam adjudications + the 32-finding tail; NEVER-block governs throughout.
- [ ] **Step 4: Verify** — `./run-tests --fast` → 1021/1/2, 107 snapshots;
  `git diff 1fa1fa7 -- tests/e2e/__snapshots__/ '*.ambr' | wc -l` → 0;
  `uvx ruff@0.15.22 check --config ruff-broad.toml .` → All checks passed!;
  collected-count arithmetic pinned in the report BEFORE the run.
- [ ] **Step 5: Commit**
```bash
git add -A && git commit -m "feat(campaign-I14b): un-grandfather tests/"
```

**Split escape hatch (CAMPAIGN §11):** if Step 3 proves oversized mid-session, commit
the completed portion green (idiom block + autofixes + finished files), report
DONE_WITH_CONCERNS naming the remaining files, and the controller ledgers the split.

### Task 4: the merge (SPEC §2.3 + §4)

**Files:**
- Modify: `pyproject.toml` (the merged `[tool.ruff]`/`[tool.ruff.lint]` per SPEC §2.3's
  snippet + supersession note; `pyright==1.1.411` in the test extra), `run-tests` (one
  ruff pass; `uvx pyright@1.1.411` fallback; banner/docstring updates),
  `.claude/hooks/ruff-check.sh` (one pass), `development/finalize-session.py` (24
  findings per SPEC §5 + the T201 per-file-ignore), `README.md` (the three TODOs,
  SPEC §1-D), `CLAUDE.md` (the two-gates § Testing accuracy edit ONLY).
- Delete: `ruff-broad.toml`.
- Test: the §4 red demonstrations (transcripts in the report).

**Interfaces:**
- Consumes: Task 3's fully-clean tree + its idiom block (carried verbatim).
- Produces: the campaign's final lint/type gate shape.

- [ ] **Step 1: Merge the configs** — pyproject gets `extend-exclude = ["development/2*"]`,
  `select = ["ALL"]`, the verbatim ignore list, the per-file-ignores (idiom block +
  finalize-session T201); the narrow block + old `"tests/*"` entry superseded per SPEC
  §2.3; delete `ruff-broad.toml`.
- [ ] **Step 2: Harness** — `run-tests`: single ruff invocation + pinned
  `uvx pyright@1.1.411` fallback + `pyright==1.1.411` in the test extra;
  `ruff-check.sh`: single pass, comments updated.
- [ ] **Step 3: Clean finalize-session.py** (24 findings, SPEC §5 table).
- [ ] **Step 4: The §4 red demonstrations** — all four PD rules red under the merged
  config (E722 in psh/ AND tests/; BLE001 in psh/; S105 + S106 in plugin/); the
  per-file-ignores scope checks (S101+S105 silent in nested tests/, S101 loud in
  plugin/); the exclusion boundary checks (E722 loud in finalize-session.py, silent in
  `development/2026-07-23-mod-I11-charts/charts-scratch-measured.py`); hook parity
  spot-check. Every offender reverted; every transcript pasted in the report.
- [ ] **Step 5: README TODOs + CLAUDE.md** — the three deferred-work TODOs (ruff
  upgrade + PLR0917; typed sc stubs + pyright widening; test repoint + conftest
  redesign); CLAUDE.md § Testing two-gates edit.
- [ ] **Step 6: Verify** — `./run-tests --fast` → green (TWO gates + pytest);
  `uvx ruff@0.15.22 check .` → All checks passed!; goldens/snapshots diff vs 1fa1fa7
  empty; `test ! -e ruff-broad.toml`.
- [ ] **Step 7: Commit**
```bash
git add -A && git commit -m "feat(campaign-I14b): merge the ratchet into pyproject; single ruff pass; pin pyright"
```

---

**Close (controller):** whole-branch review; full `./run-tests` (live tier if creds);
SPEC §8 acceptance run-and-pasted; LEDGER I14b entry; memory; archive; closing docs
commit.

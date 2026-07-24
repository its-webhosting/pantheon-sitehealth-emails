# SPEC — I14b: the global ratchet flip

**Increment:** I14b (Wave 4, second of four — CAMPAIGN.md §11 as amended 2026-07-23).
**Baseline commit:** `1fa1fa7` ("docs(campaign-I14a): archive the structural-finish session").
**Governing documents:** `CAMPAIGN.md` (§13 is this increment's charter; §8/§9 bind),
`LEDGER.md` (the I14a entry's Open-questions row is this increment's inbox), `CLAUDE.md`
(§ Testing), `prompts/directives.md`, `prompts/implementation-standards.md`. This spec
cites CAMPAIGN.md by section and re-derives nothing.

## Glossary (this spec only)

- **The flip** — deleting every remaining `ruff-broad.toml` `extend-exclude` entry
  (the `development/` entry is not deleted but REWRITTEN to `development/2*` at the
  merge — §2.3) and cleaning the exposed trees to the broad set.
- **The merge** — folding `ruff-broad.toml`'s settings into `pyproject.toml`
  `[tool.ruff.lint]` so ONE config and ONE ruff pass replace today's two (§13: "the two
  configs merge at I14").
- **Idiom block** — the per-file-ignores entry for `tests/**` listing rules that flag
  legitimate test idioms (user decision 2026-07-23: "idiom-ignore + fix rest").
- **Narrow gate / PD rules** — `E722`,`BLE001`,`S105`,`S106`: run EVERYWHERE today,
  mechanize PD#2/PD#6, never grandfathered (§13).
- **Archive folders** — `development/<YYYY-MM-DD-*>/` dated record folders; their `.py`
  files are verbatim measurement artifacts (e.g. `charts-scratch-measured.py`, I11), not
  maintained code.

MUST/NEVER/SHOULD/MAY per CAMPAIGN.md §Glossary.

## 1. Scope and non-scope

**In scope (exhaustive):**

- **A. Flip the five non-test trees** — delete `check/cloudflare/`, `check/dns/`,
  `check/pantheon_cdn_change/`, `check/umich/sitelens.py`, `check/umich/cloudflare_cms.py`,
  `plugin/` from `extend-exclude`; clean their **112 measured findings** (per-rule table
  §5, measured under pinned ruff 0.15.22 at `1fa1fa7`).
- **B. Flip `tests/`** — the idiom block + fix the remainder (**2,536 measured**, §5).
- **C. The merge** — one `[tool.ruff.lint]` in `pyproject.toml`; `ruff-broad.toml`
  deleted; `run-tests` and `.claude/hooks/ruff-check.sh` collapse to ONE ruff pass;
  `development/` exclusion redesigned (§2.3 — the archive folders excluded, the active
  `development/finalize-session.py` cleaned and fully gated); pyright pinned
  (`pyright==1.1.411` in the `test` extra + `uvx pyright@1.1.411` fallback — the
  I14a ruff-drift class, closed for the other tool).
- **D. Deferred-work records** — three README TODOs (user decisions 2026-07-23):
  (1) upgrade ruff past 0.15.22 + disposition the 9 `PLR0917` findings; (2) typed `sc`
  façade stubs, then widen pyright beyond `psh/`; (3) repoint tests off the `psh.<name>`
  re-export surface + the deeper conftest/TempDB redesign (D-i14a-3/8 disposed: deferred).
- **E. Increment close** — CLAUDE.md minimal accuracy edits (the § Testing gate
  description: the three gates — two ruff passes + pyright — become **two** gates,
  one merged ruff pass + pyright; every "three gates"/"both ruff passes" claim it
  touches updates consistently), LEDGER I14b entry, memory, archive.

**NOT in scope (exhaustive, with reasons):**

- Upgrading ruff or pyright versions (user decision — D2's bar holds; README TODO).
- Widening the pyright gate beyond `psh/` (needs typed `sc` stubs — README TODO).
- The test repoint / conftest redesign (README TODO; the re-export surface is stable).
- Cleaning archive-folder `.py` files (verbatim records; linting them is meaningless —
  they are excluded by design, §2.3).
- `Notice` retirement (I14c); docs/README/CLAUDE.md wholesale refresh, the
  `check/umich/__init__.py` stale message, and the §17 audit (I14d).
- ANY behavior change: **zero** on every §8 surface. Goldens byte-identical; ALL 107
  syrupy snapshots unchanged; `-notices.csv`/`-results.json`/`-run.json` untouched;
  stdout unchanged (this increment has no sanctioned stdout improvement — a lint fix
  that would alter output text gets a noqa instead).

## 2. Design

### 2.1 Deliverable A — the five non-test trees (112 findings)

Delete the five exclude lines; clean per the precedent disposition classes (LEDGER
I5–I13; "cleaned exactly once" D2). Binding rules, in priority order:

1. **Behavior first (§8/§9):** these trees build notice HTML/plaintext pinned by the
   integration `.ambr` snapshots (`test_cachecheck_notice_render`,
   `test_dns_notice_render`, `test_pantheon_cdn_change_notice_render`,
   `test_check_sitelens`-adjacent renders) and, for `check/pantheon_cdn_change/` +
   `check/dns/`, by two e2e goldens. **A fix that touches any string literal, message
   text, or csv value is FORBIDDEN — noqa with reason instead.** Snapshot diff must be
   empty (`git diff -- '*.ambr'`).
2. **Signatures pinned by tests stay** (`PLR0913`/`FBT001`/`FBT003` → noqa when the
   call sites/tests pin positional form — the I9 `check_wordpress_plugin` precedent).
3. **Module-state idiom stays** (`PLW0603`/`PLW0602` global statements — 8 in
   `plugin/aws/get_secret.py` / `plugin/umich/portal.py`, 2 in
   `check/umich/sitelens.py` — the plugin-context/module-state bag pattern is the
   design; noqa + reason, not a rewrite).
4. Mechanical, provably behavior-identical fixes are applied: `I001` (import order),
   `F541` (f-drops), `PLR0402` (import form), `RSE102`, `C420`, `PIE810`-class rewrites
   ONLY where no literal/message/seam is involved.
5. Verbatim-complexity noqa: `C901`/`PLR0912`/`PLR2004`/`ERA001`-adjudication
   (commented-out code: delete if debris [I5/I6 precedent], convert to prose if
   documentary), `PERF401`, `DTZ011`/`DTZ901` (naive-date semantics are load-bearing —
   the I5 DTZ precedent), `B007`.
6. **`check/cloudflare/httpseam.py`/`egress.py` seams and `plugin/env/get_env.py`'s
   `os.environ` access are design surfaces** — any finding there resolves by noqa +
   reason, never by restructuring (CLAUDE.md: get_env IS the `<{env}` engine). Two
   security-family findings get named dispositions, not implementer inference:
   `check/cloudflare/cache.py` `S311` → noqa + reason (the RNG is DELIBERATELY seeded
   `{site}:{report_date}` so re-runs test identical URLs — CLAUDE.md cachecheck note);
   `check/cloudflare/egress.py` `S104` → noqa + reason (the seam's bind-address
   constant, rule-6 surface).

The ~22-finding non-test tail outside the named rules (PTH family, SIM105/118/210/211,
UP015/UP032, RUF046, PLR0911/PLR0915/PLR1711/PLR1730, PLW2901) is dispositioned
per-site in the task report under the same priority order — behavior-identical fix
where no literal/seam is involved, else noqa + reason. Per-file `# noqa` inventory
goes in the task report; every noqa carries an inline reason (PD#1 — a bare noqa is a
silent failure).

### 2.2 Deliverable B — `tests/` (2,536 findings)

**The idiom block** (added to the config with one justification line per rule —
exhaustive; anything not listed here gets FIXED, not ignored):

```toml
"tests/**" = [
    "S101",     # pytest asserts ARE the mechanism (1,715 sites)
    "S105", "S106",  # fake fixture credentials (carried over from the narrow config's
                     # existing "tests/*" entry — verified 2026-07-16, re-verified I14b)
    "INP001",   # pytest collects without __init__.py; adding them changes import
                # semantics for zero gain (120 sites)
    "PLR2004",  # expected literals in assertions are the point (74)
    "ARG001", "ARG002", "ARG005",  # fixture params + seam-matching fake signatures
                # (monkeypatch fakes must accept the real seam's arity) (211)
    "FBT003",   # positional booleans at pinned call sites under test (68)
    "PLC0415",  # in-test imports are the suite's documented loading pattern
                # (checkload/SourceFileLoader style; I8 review adjudicated) (57)
    "PT018",    # composite asserts: splitting 70 sites churns load-bearing tests for
                # zero signal gain (user decision: no assertion churn)
    "SLF001",   # tests reach private seams by design (7)
    "S311",     # non-crypto RNG in test data (5)
    "S603",     # subprocess in sanctioned test harnesses: run_program, the shim
                # probe, and the real-php inliner call in test_css_inliner_encoding (3)
    "DTZ002",   # naive datetimes mirror the program's own date semantics (6)
]
```

**Fixed, not ignored** (the remainder: **195** = 2,536 − the 2,341 the idiom block
absorbs; the named rules below sum to 163, leaving a 32-finding tail each
dispositioned in the report):

> **Correction (I14b close).** The named rules below sum to **172**, leaving a
> **23**-finding tail (53+17+13+10+9+8+7+6+5+4+3+2+2+2+22+9 = 172; the drafting
> miscount excluded FBT002's 9 from the named sum). The binding 195 gate was
> unaffected — Task 3's structural RED matched it exactly. Confirmed independently
> by the Task 3 reviewer and the whole-branch review; ledgered. `I001` (53), `RUF059` (17), `PT006` (13), `PLR0402`
(10), `N806` (9), `RUF015` (8), `RSE102` (7), `E741` (6 — local renames only, never a
fixture key or seam name), `A002` (5), `E402` (4 — mid-file imports NOT of the
documented in-test style; if a file's mid-file import IS load-bearing order, noqa +
reason), `C420` (3), `C408` (2), `F541` (2), `F841` (2), and two seam-adjudicated
rules: `PLR0913` (22) and `FBT002` (9) — for BOTH, noqa + reason where the signature
mirrors a pinned seam's arity/positional form (fakes must match the real seam — the
ARG-family reasoning), fix where it's a test-local helper; adjudicate per-site.
**NEVER change an assertion's semantics, a fixture's value, an expected result, or a
seam name** — a rename is safe only for test-local variables.

**Gate:** collected-test count unchanged (1021 passed / 1 skipped / 2 deselected fast;
1023 full); 107 snapshots unchanged; goldens byte-identical.

### 2.3 Deliverable C — the merge

**Target `pyproject.toml` `[tool.ruff.lint]` (actual shape — merged with what the file
already contains):**

```toml
[tool.ruff]
# NO target-version (unchanged; PD#14 — pinning masks the 3.12 syntax detection).
# development/<dated archive folders> hold verbatim measurement artifacts (.py files
# that are records, not code) -- excluded by design; development/finalize-session.py
# stays FULLY gated (it is active tooling and sits above the dated folders).
extend-exclude = ["development/2*"]

[tool.ruff.lint]
# The campaign ratchet's final form (CAMPAIGN.md §13, merged at I14b): ONE pass,
# select = ALL minus the justified ignores below.  The four PD rules (E722, BLE001,
# S105, S106) are members of ALL and still run EVERYWHERE not excluded above --
# the merge MUST NOT weaken the old narrow gate (red-demonstrated, see §4).
select = ["ALL"]
# The ignore list is ruff-broad.toml's [lint] ignore, carried VERBATIM with its
# justification comments (COM812, ISC001, E501, Q000-Q003, ANN, TD002, TD003,
# FIX002, EM101, EM102, TRY003, D, CPY001 -- exhaustive; no additions, no drops).
ignore = [ ... ]

[tool.ruff.lint.per-file-ignores]
"tests/**" = [ ... ]  # the §2.2 idiom block, verbatim, incl. S105/S106
"development/finalize-session.py" = ["T201"]  # a CLI tool: print IS its output
```

This `[tool.ruff.lint]` SUPERSEDES the existing narrow block (`pyproject.toml:66–78`):
the four-rule `select` and its "NARROW BY DESIGN" comment are REPLACED by the merged
form (the four rules are members of `ALL` and keep running everywhere not excluded —
the §4 red demonstrations prove it); the existing `"tests/*" = ["S105","S106"]`
per-file-ignores entry and its fixture comment fold into the idiom block (its
"verified 2026-07-16" provenance is kept in the comment).

- The old `"tests/*" = ["S105", "S106"]` entry folds into the idiom block (same effect,
  one home). `ruff-broad.toml` is **deleted**; its header comment's rationale lands in
  pyproject. **`development/2*` exclusion analysis:** today the narrow gate lints
  `development/` and passes; post-merge the four PD rules stop running on archive-folder
  `.py` files only. Accepted and ledgered: those files are verbatim records
  (re-linting records is meaningless; a "fix" would falsify them), and
  `finalize-session.py` — the only active code under `development/` — is cleaned to the
  FULL broad set this increment (**24** findings measured: PTH ×13
  (PTH123 5, PTH118 4, PTH103/110/111/207 ×1), T201 ×3 → per-file-ignore, ARG005 ×2,
  C408 ×2, N806/PLW2901/RUF001/SIM105 ×1 each) and stays fully gated forever.
- **`run-tests`**: the two ruff invocations collapse to one (`ruff check .` with the
  merged config); gate banners/docstrings updated; **pyright pinned** — `pyright==1.1.411`
  in the `[project.optional-dependencies] test` extra AND the fallback becomes
  `uvx pyright@1.1.411` (mirroring the I14a ruff pin, same D2 reason, same
  PATH-installed-binary residual noted in a comment). `.claude/hooks/ruff-check.sh`:
  one pass, `--force-exclude` retained, comments updated.
- **CLAUDE.md**: minimal accuracy edit to § Testing's gate description (three gates —
  ruff merged single pass, pyright — replacing the two-pass prose); the wholesale
  rewrite stays I14d.
- **README TODOs added** (Deliverable D, exact wording drafted in the task): ruff
  upgrade + PLR0917; typed `sc` stubs + pyright widening; test repoint + conftest
  redesign.

### 2.4 Decisions (D-i14b-1…6, exhaustive)

1. **Flip before merge** (task order A → B → C): each un-grandfathering commit keeps
   BOTH existing configs green; the merge lands on an already-clean tree, so its diff
   is pure config mechanics — reviewable in isolation.
2. **`development/2*` exclusion, `finalize-session.py` fully gated** (§2.3) — the only
   design that avoids BOTH regressing the narrow gate on active code AND linting
   verbatim archives (an unresolvable conflict under a wholesale `development/`
   exclude, since ruff excludes are total, not per-rule).
3. **The idiom block is exhaustive and closed** — a future rule that fires on tests
  gets adjudicated then, not pre-ignored; anything outside the block is fixed now.
4. **No behavior change is sanctioned anywhere in this increment** — where a lint fix
   and byte-preservation conflict, noqa wins (this is the flip's prime directive).
5. **Version pins are campaign policy, not tool preference** — both tools pinned at
   their I0-era majors (ruff 0.15.22, pyright 1.1.411) until the post-campaign upgrade
   TODO; recorded in the merged config comments.
6. **`tests/` per-file-ignores use `tests/**`** (not `tests/*`) so nested tiers
   (`tests/unit/`, `tests/e2e/`, `tests/shims/pyshim/`, `tests/helpers/`) are all
   covered — the old narrow entry's `tests/*` worked only because ruff globs `*` across
   separators in per-file-ignores; `**` states the intent explicitly (verify against
   pinned-ruff behavior at implementation; if `tests/*` ≠ `tests/**` in 0.15.22, keep
   BOTH forms' effect by testing a nested offender red).

## 3. Behavior bar (CAMPAIGN.md §8, applied)

| Surface | This increment |
|---|---|
| 4 goldens | byte-identical — `git diff 1fa1fa7 -- tests/e2e/__snapshots__/` empty at every commit |
| 107 syrupy snapshots | byte-identical — `git diff 1fa1fa7 -- '*.ambr'` empty |
| Artifacts / csv / stdout / exit codes / config keys | unchanged (NO sanctioned change of any kind) |
| Collected tests | 1021/1/2 fast, 1023/1 full — unchanged |
| Lint gate semantics | narrow-gate coverage NEVER weakened on non-archive code (red-demonstrated, §4) |

## 4. Tests / instruments (no new test files; the instruments are the gates)

This increment changes no behavior, so its tests are PD#14 red-demonstrations that the
restructured gates still catch what they caught before (the I2 `ENVIRON_SCOPE`
precedent — instrument edits require showing red):

1. **Post-merge narrow-equivalence red check — ALL FOUR PD rules, each shown red under
   the merged config, transcripts pasted, offenders reverted:**
   (a) `E722`: a bare `except:` in a `psh/` file AND in a `tests/` file (E722 is not in
   the idiom block, so it must still fire in tests);
   (b) `BLE001`: an `except Exception:` handler in a `psh/` file;
   (c) `S105`: a `PASSWORD = "hunter2"` assignment in a `plugin/` file (note: in
   `tests/` S105 is legitimately idiom-ignored — that suppression is VERIFIED as part
   of check 2, not accidentally, so the fixture carve-over is proven deliberate);
   (d) `S106`: a `f(password="hunter2")` call-site in a `plugin/` file.
   Four red transcripts, each NAMING the offending file.
2. **Per-file-ignores scope check:** a temporary `S101` offender in a NESTED tests dir
   (e.g. `tests/shims/pyshim/`) must NOT fire, and a temporary `S105` in a nested
   tests dir must NOT fire (proves D-i14b-6 and the deliberate fixture carve-over);
   a temporary `S101` in `plugin/` MUST fire.
3. **Exclusion boundary check:** a temporary bare `except:` in
   `development/finalize-session.py` MUST fire; the same in
   `development/2026-07-23-mod-I11-charts/charts-scratch-measured.py` must NOT.
4. **The suite itself:** `./run-tests --fast` green at every commit; full suite at
   close; count/snapshot/golden gates per §3.
5. **Hook parity:** `.claude/hooks/ruff-check.sh` on an edited grandfathered-no-more
   file reports the same findings the gate does (spot-check one file, transcript in
   report).

## 5. Measured baselines (pinned ruff 0.15.22, at `1fa1fa7` — re-measure per-tree at
implementation; deltas recorded in reports, PD#14)

Totals: **2,648** = `tests/` 2,536 + `check/cloudflare` 41 + `plugin/` 39 +
`check/umich` legacy pair 16 + `check/pantheon_cdn_change` 15 + `check/dns` 1.

`tests/` per-rule (top): S101 1715, ARG001 140, INP001 120, PLR2004 74, PT018 70,
FBT003 68, PLC0415 57, ARG005 53, I001 53, PLR0913 22, ARG002 18, RUF059 17, PT006 13,
PLR0402 10, FBT002 9, N806 9, RUF015 8, RSE102 7, SLF001 7, DTZ002 6, E741 6, A002 5,
S105 5, S311 5, E402 4, C420 3, S603 3, C408 2, F541 2, F841 2 (+ tail — full
`--statistics` output re-captured in the task report).

Non-test per-rule: I001 18, PLR2004 15, FBT001 7, FBT003 6, PLR0913 6, PLW0603 6,
C901 5, PLW0602 4, C408 3, E741 3, ERA001 3, F541 3, PLR0912 3, PERF401 2, B007 1,
DTZ011 1, DTZ901 1, F401 1, PIE810 1, PLR0402 1 (+ tail).

`development/finalize-session.py`: ~23 (PTH123 5, PTH118 4, T201 3, ARG005 2, C408 2,
N806 1, PLW2901 1, PTH103 1, PTH110 1, PTH111 1, PTH207 1, RUF001 1, + tail).

pyright: gate scope unchanged (`psh/`, standard, 0 errors today) — this increment only
pins the version.

## 6. Task plan (per-task commits, each green)

1. **Task A1** — flip `check/dns/` + `check/pantheon_cdn_change/` + the `check/umich`
   pair (32 findings). Commit `feat(campaign-I14b): un-grandfather check/dns, cdn_change, umich legacy pair`.
2. **Task A2** — flip `check/cloudflare/` + `plugin/` (80 findings; the two largest,
   seam-dense trees). Commit `feat(campaign-I14b): un-grandfather check/cloudflare and plugin/`.
3. **Task B** — flip `tests/` (idiom block into `ruff-broad.toml`'s per-file-ignores
   first, then fix the remainder). Commit `feat(campaign-I14b): un-grandfather tests/`.
4. **Task C** — the merge (§2.3: pyproject rewrite, delete `ruff-broad.toml`,
   `run-tests` single pass + pyright pin, hook, `finalize-session.py` cleanup, README
   TODOs, CLAUDE.md minimal edit) + the §4 red demonstrations. Commit
   `feat(campaign-I14b): merge the ratchet into pyproject; single ruff pass; pin pyright`.
5. **Close** — whole-branch review; full `./run-tests` (live tier if creds); LEDGER
   I14b entry; memory; archive; closing docs commit.

## 7. Obligations discharged / created

**Discharged:** CAMPAIGN §13's merge; the I14a ledger's I14b inbox (ruff-version
decision, pyright pin, per-file-ignores block, D-i14a-3/8 disposition).
**Created:** the three README TODOs (§1-D); archive-folder `.py` files permanently
un-linted (D-i14b-2, ledgered); I14c/I14d unchanged.

## 8. Acceptance (run and pasted at close)

```
./run-tests                                          # full; TWO gates post-merge (one ruff pass + pyright)
git diff 1fa1fa7 -- tests/e2e/__snapshots__/         # MUST be empty
git diff 1fa1fa7 -- '*.ambr'                         # MUST be empty
test ! -e ruff-broad.toml && echo merged
uvx ruff@0.15.22 check .                             # the merged single pass, clean
grep -c "ruff@0.15.22\|pyright@1.1.411" run-tests .claude/hooks/ruff-check.sh  # pins present
grep -n "PLR0917\|sc façade stubs\|re-export surface" README.md   # the three TODOs landed
```

Results pasted here at close (an unrun acceptance suite is PD#14).

**ACCEPTANCE — run and pasted at close (2026-07-23, HEAD = 7ed4e92 + the close fixes):**

```
$ ./run-tests --llm            (full suite; live tier ran — terminus token present)
EXIT=0
LLM_SUMMARY passed=1023 failed=0 error=0 skipped=1 xfailed=0 xpassed=0
107 snapshots passed.
(TWO gates post-merge: the single merged ruff pass, then pyright — both ran, exit 0)
# 1023 = fast 1021 + 2 live; the skip is test_db_credentials.py's
# importorskip("MySQLdb"). Count unchanged across the whole increment.

$ git diff 1fa1fa7 -- tests/e2e/__snapshots__/
(empty)
$ git diff 1fa1fa7 -- '*.ambr'
(empty)
$ test ! -e ruff-broad.toml && echo merged
merged
$ uvx ruff@0.15.22 check .
All checks passed!
$ grep -c "ruff@0.15.22\|pyright@1.1.411" run-tests .claude/hooks/ruff-check.sh
run-tests:4
.claude/hooks/ruff-check.sh:1
$ grep -c "PLR0917" README.md ; grep -c "typed sc façade" README.md ; grep -c "re-export surface" README.md
2 / 1 / 2   (all three deferred-work TODOs present)
```

# SPEC — I14a: structural finish (B51 deletion, `psh/cli.py`, `psh/dns_classify.py`)

**Increment:** I14a (Wave 4, first of four — CAMPAIGN.md §11, amended 2026-07-23).
**Baseline commit:** `5902b76` ("docs(campaign-I13): archive the lifecycle session").
**Governing documents (read in full before implementing):** `CAMPAIGN.md`, `LEDGER.md`
(all entries; I13's Open-questions row is this increment's inbox), `BLOCKMAP.md` (rows
B50/B51 only — no other block moves), `CLAUDE.md`, `prompts/directives.md`,
`prompts/implementation-standards.md`. This spec cites CAMPAIGN.md by section number and
re-derives nothing (CAMPAIGN.md preamble).

## Glossary (this spec only; campaign terms in CAMPAIGN.md §Glossary)

- **The remnant** — `psh/_legacy.py` at baseline: 996 lines, holding `build_arg_parser`,
  `parse_args`, `fqdn_re`, the psh.* re-import blocks, the sc-exposure block,
  `no_primary_domain_notice`, `sort_notices_and_subject`, `main()`, and an inert
  `if __name__` tail.
- **The re-export surface** — the set of names tests reach as `psh.<name>` through the
  conftest `psh` fixture (today = attributes of `psh._legacy`).
- **B51** — the "annual bill in progress" notice: `build_annual_bill_in_progress_notice`
  + `check_annual_bill_in_progress` in `check/umich/annual_billing.py`, its hook
  registration, and the `annual_bill_in_progress` produced key.
- **Seam imports** — the three deliberately retained monkeypatch-seam imports in the
  remnant: `import signal`, `import subprocess`, `import sqlalchemy as db` (each
  `# noqa: F401` + inline reason; CLAUDE.md § Two mock seams).

MUST/NEVER/SHOULD/MAY per CAMPAIGN.md §Glossary.

## 1. Scope and non-scope

**In scope (exhaustive):**

- **A. B51 deletion** — user-approved early deletion (2026-07-23; CAMPAIGN.md §8 row
  "Notice csv values", amended; §11 row I14a). Its Aug-2026 marker date has NOT passed;
  the user chose deletion over carrying it post-campaign.
- **B. `dns_classify.py` → `psh/dns_classify.py`** — the §3.1 MAY, exercised (user
  decision 2026-07-23). Cleaned to the broad ruff set + pyright standard as it moves
  (§13, D2: cleaned exactly once, as it moves).
- **C. `main()`/argparse relocation** — everything in the remnant → `psh/cli.py`;
  `psh/_legacy.py` deleted; conftest `psh`-fixture repoint; D-i13-3 bridge discharge
  (corrected form, D-i14a-4); §17 Q5 symlink decision recorded (D-i14a-6).
- **D. Increment close** — minimal CLAUDE.md accuracy edits (only claims this increment
  falsifies — the wholesale rewrite is I14d), ledger entry (including the Wave-4 split
  amendment record and the B51 amendment record), memory, archive.

**NOT in scope (exhaustive, with reasons):**

- The global ratchet flip / `ruff-broad.toml` merge (I14b). I14a deletes only the two
  entries whose files it removes (`psh/_legacy.py`, `dns_classify.py`).
- Repointing tests off the re-export surface onto real `psh/*` module homes — the
  surface moves to `psh/cli.py` intact (D-i14a-3). Candidate for I14b (which
  un-grandfathers `tests/` wholesale) or post-campaign.
- `Notice` dict retirement (I14c), config-migration doc + docs/README/CLAUDE.md full
  refresh + §17 closing audit (I14d).
- Any behavior change beyond B51's removal. The four goldens stay byte-identical
  (Invariant 1); `-results.json`/`-notices.csv`/`-run.json` unchanged (§8).
- De-U-M-ifying templates/notice bodies (post-campaign; Invariant 1 blocks it).
- `resolve_recipients` empty-team guard (LEDGER I12) — README TODO disposition happens
  at I14d with the ledger-resolution sweep, not here.

## 2. Design

### 2.1 Deliverable A — B51 deletion

Delete, exhaustively (verified 2026-07-23 against baseline by the pre-spec survey AND
independently re-verified by the adversarial spec review — both greps recorded in this
increment's review report):

| Site | Edit |
|---|---|
| `check/umich/annual_billing.py:89–114` | delete `build_annual_bill_in_progress_notice` |
| `check/umich/annual_billing.py:134–140` | delete the TODO marker + `check_annual_bill_in_progress` |
| `check/umich/annual_billing.py:1–16` | module docstring: rewrite to describe ONE produced key (`annual_bill_upcoming`); keep the load-bearing history paragraph (csv rows never reach `-notices.csv`; front ordering) — it still governs the upcoming notice |
| `check/umich/annual_billing.py:117–121` | `_billing_inputs` **stays** (sole remaining caller: upcoming) |
| `check/umich/__init__.py:5–7, 42–45` | remove the import + the `check_annual_bill_in_progress` registration; the upcoming registration stays |
| `psh/_legacy.py:360–365` | delete the `annual_bill_in_progress` walrus-read + `insert(0, …)` in `sort_notices_and_subject` **and the four comment lines above them** — including the `:360` "TODO: remove this section at the beginning of August 2026" marker and the `:361–363` in-progress comment (a dangling TODO describing deleted code would survive otherwise); update the docstring (`:333, :336–337, :347`), the `:906` "two hooks" comment (→ one hook), and the `:910–911` plural "billing hooks' produced keys" comment (→ singular) |
| `tests/unit/test_annual_billing_notices.py` | delete `_in_progress` (`:21–22`), the code-uniqueness test (`:28` — its subject no longer exists), `test_in_progress_notice_shape` (`:39–42`) |
| `tests/integration/test_sort_notices_and_subject.py` | delete `test_in_progress_key_leads_but_never_touches_subject` (`:61`); **rewrite** `test_both_keys_render_in_progress_first_then_upcoming` (`:69`) into an upcoming-only front-order pin unless an existing test already pins it (implementer adjudicates; do not lose the upcoming front-order pin); **rewrite — NEVER delete —** `test_helper_does_not_mutate_site_context_notices` (`:78–82`): it is the non-mutation-of-`site_context["notices"]` pin CLAUDE.md § Testing names, its property survives B51 (the upcoming key is still inserted into the render-only list), so drive it through `annual_bill_upcoming` instead. Update the file docstring (`:4`) |
| `tests/integration/test_check_umich_annual_billing.py` | registration assertions (`:53, :62, :64`) become **exact-set**: only `check.umich.annual_billing.check_annual_bill_upcoming` registered at `site_pre_render` (this is the RED-first instrument — it fails against baseline, which registers two); delete `test_in_progress_always_produced_when_hook_runs` (`:99–105`) |
| `CLAUDE.md:352–359, 457` | minimal accuracy edit: the annual-billing prose describes one hook/one produced key; note B51 deleted at I14a (user-approved early) |

**Behavior consequence (the §8-amended sanction):** a U-M run in the in-progress window
loses that rendered email section and the `annual_bill_in_progress` key. Zero golden
impact — all four goldens run umich-disabled, and no `.ambr` contains
`annual-bill-in-progress` (inventory §7). No csv/artifact impact — the billing keys never
reach `-notices.csv` (load-bearing history, preserved for the surviving upcoming hook).

**Seam:** existing — the hook-registration seam (`checkload.py` + `reset_sc.hooks`) and
the pure-builder seam, both already under test in the three files above. No new seam.

### 2.2 Deliverable B — `dns_classify.py` → `psh/dns_classify.py`

`git mv dns_classify.py psh/dns_classify.py`, then repoint every live reference
(exhaustive; grep-verified twice — pre-spec survey + adversarial review):

- Imports: `psh/_legacy.py:30` (or `psh/cli.py` if C lands first — see §7 ordering),
  `check/pantheon_cdn_change/chain.py:37`, `tests/helpers/dnsfake.py:47`,
  `tests/unit/test_dns_classify.py` (`:7` + the **six** in-test imports at
  `:245, :259, :275, :303, :322, :336`), `tests/unit/test_contract_registry.py:8`,
  `tests/unit/test_pantheon_cdn_change_chain.py:76`.
- Import form (D-i14a-2): `import psh.dns_classify as dns_classify` — every call site
  keeps its qualified `dns_classify.<attr>` form, and the monkeypatch seam stays a
  single module object (**verified: no `from dns_classify import` exists anywhere**, so
  the `run_terminus` two-binding trap class does not arise).

  > **Correction (I14b Task 1).** D-i14a-2's binding invariant is a single shared module
  > object reached through a qualified `dns_classify.<attr>` call-site form — not the
  > specific `import psh.dns_classify as dns_classify` alias syntax. That syntax was the
  > correct choice pre-gate; once `check/pantheon_cdn_change/chain.py` came under the
  > broad ruff gate at I14b, `PLR0402` mandated `from psh import dns_classify` there
  > instead. Proof the invariant survives the syntax change: `import psh.dns_classify as
  > a; from psh import dns_classify as b; a is b` → `True` (both forms bind the same
  > `sys.modules` entry, so `tests/helpers/dnsfake.py`'s monkeypatch seam still
  > intercepts every call site). `check/pantheon_cdn_change/chain.py:37` now reads `from
  > psh import dns_classify`; every other site this deliverable touched is unaffected and
  > keeps the alias form. Ledgered at I14b.
- Config: `pyproject.toml:112` — drop `"*/dns_classify.py"` from
  `[tool.coverage.run] include` (now covered by `"*/psh/*"`); `ruff-broad.toml:15` —
  delete the `"dns_classify.py"` exclude line (the file is born-gated at its new home).
- House rules: `tests/unit/test_house_rules.py:31` (`ENVIRON_SCOPE`) and `:116`
  (`POPEN_SCOPE`) — drop the `"dns_classify.py"` entries; the `"psh"` entry (present in
  both since I2) now covers it. **The scope MUST NOT shrink**: implementer verifies the
  moved file is walked by both house rules after the edit (e.g. temporary-offender RED
  check, the I2 `ENVIRON_SCOPE` precedent).
- Docs (present-tense claims only): `docs/pantheon-cdn-change.md:174`,
  `prompts/directives.md:114`, `prompts/debugging-standards.md:34` — the "one DNS seam"
  path becomes `psh/dns_classify.py` / `psh.dns_classify.resolve`. `dns_classify.py`'s
  own docstring self-references (`:6, :39`) updated. `CLAUDE.md` narrative: minimal
  accuracy edits only (D-i14a-7); `check/dns/__init__.py:5`, `psh/modules.py:283`,
  `detect.py:38`, `dnsshim.py:4` comments repointed; `.claude/hooks/ruff-check.sh:101`
  (names `dns_classify.py` — and `psh/_legacy.py` — as current grandfather entries)
  updated alongside the exclude-list edits.
- Ratchet (§13): cleaned as it moves — 9 measured findings, §5 table. Enters
  `[tool.pyright]` scope automatically (`include = ["psh"]`); I0's whole-tree baseline
  measured 1 pyright error here — fix or scoped-ignore per the I13 precedent classes.
- The pyshim `dnsshim.py` is **unaffected** (it patches `dns.resolver.resolve`, the
  dnspython library — not our module).

**Seam:** existing — `dns_classify.resolve` (the one DNS seam) simply changes address;
`tests/helpers/dnsfake.py` retargets it. The dns unit/integration suites +
`test_golden_cdn_change` are the cover; no new seam.

### 2.3 Deliverable C — the remnant → `psh/cli.py`; `psh/_legacy.py` deleted

`psh/cli.py` (today a 9-line re-export) becomes the orchestrator module — CAMPAIGN.md
§3.1 row `psh/cli.py` reached at last. Contents, in order (the remnant's whole surface,
relocated verbatim except the named edits):

1. Module docstring (rewritten: it IS the orchestrator now; keep the shebang-less form —
   the extension-less shim stays the entry point).
2. All imports at top of file (resolves the remnant's 12× E402 + 2× I001): stdlib, the
   three **seam imports** with their `# noqa: F401` markers — **the inline reason texts
   themselves are rewritten** from `psh._legacy` phrasing to `psh.cli` phrasing (the
   `:19`/`:25` reasons name `psh._legacy.subprocess` / "THIS alias on the _legacy
   module"; §7 obligation 4 — verify every claim a move carries), and the referencing
   test docstrings/comments update likewise; the *mechanism* — patching shared module
   objects through the fixture module — is unchanged. Then rich imports,
   `import psh.dns_classify as dns_classify`, `import script_context as sc`, then the
   psh.* re-import blocks (the re-export surface, D-i14a-3).
3. `fqdn_re`.
4. The module-level `registry.register("no-domains", description=…)` statement
   (baseline `psh/_legacy.py:267` — pinned by `tests/unit/test_notice.py:46`) and the
   sc-exposure block (the 13 assignments at baseline `:274–286`: `sc.escape_url`,
   `sc.check_wordpress_plugin`, `sc.check_drupal_module`, `sc.umich_enabled`,
   `sc.cloudflare_enabled`, `sc.terminus`, `sc.wp_eval`, `sc.wp_error`,
   `sc.drush_php_script`, `sc.drush_error`, `sc.contract_year_end`, `sc.fqdn_re`,
   `sc.db_engine_args`) — moved verbatim; module-level statements, they run at first
   import exactly as today.
5. `build_arg_parser`, `parse_args`, `no_primary_domain_notice`,
   `sort_notices_and_subject` (its B51 lines already deleted by A), `main()` — bodies
   **verbatim** (Invariant 8 for any column-0 literal; the extracted-block self-diff
   evidence pattern of I2–I13 applies).
6. **No `if __name__` tail** (D-i14a-5): it has been inert since I0 (the shim owns
   `__main__`); deleted, not moved.

Then: `git rm psh/_legacy.py`; `psh/__init__.py` docstring updated (no longer "lives in
psh._legacy"); the shim's docstring line naming `psh/_legacy.py` updated;
`ruff-broad.toml:14` exclude line deleted; `pyproject.toml` — delete **only** the
`:92 exclude = ["psh/_legacy.py"]` line (the `:91 include = ["psh"]` line MUST survive)
and rewrite the `:87–90` comment (its ":88 psh/cli.py re-exports from the untyped legacy
module" claim becomes false; cli.py is now IN the type gate); `run-tests:56` and
`run-tests:119` — both say the pyright gate is "psh/ minus `_legacy.py`", false after
the deletion (operator-facing gate description); comment-accuracy pass over the
`psh/*.py` provenance comments (update present-tense ones only: `psh/charts.py:6`,
`psh/gather.py:22, :495`, `psh/cli.py:4`, and the baseline `psh/_legacy.py:41–44`
comment above `build_arg_parser` — it claims `parse_args()` "is only invoked from the
`__main__` block at the bottom of this file", false once D-i14a-5 deletes the tail (the
shim invokes it); past-tense "moved from" lines stay — they are history, still true).

**`psh/lifecycle.py` bridge (D-i14a-4, corrects LEDGER I13's wording):** the call-time
`from psh._legacy import build_arg_parser` (`:333`) retargets to
`from psh.cli import build_arg_parser` but **stays call-time** (`# noqa: PLC0415`, cycle
reason): `psh/cli.py` imports `psh.lifecycle` at module level, so the module-level form
LEDGER I13 named is a genuine import cycle — the same §2.1-cycle rule that keeps
`abort_reason`'s `psh.db` bridge call-time permanently. The lifecycle module docstring's
import diagram (PD#8) and the bridge's inline comment are updated; the ledger entry
records the wording correction.

**Conftest redesign (minimal, D-i14a-8):** `_load_main_module()` (`tests/conftest.py:89`)
imports `"psh.cli"`; the `psh` fixture docstring and the `:6`/`:88`/`:101` comments
update. `TempDB`, the seam patches (`psh.signal`, `psh.subprocess`, `psh.db.*`-alias),
`reset_sc`'s `psh.parse_args([])`/`psh.RunState()`, `PYSHIM_DIR`, `_CWD_ASSETS`,
`run_program` are **unchanged** — every one resolves through the fixture module's
attributes, which `psh/cli.py` preserves (D-i14a-3). The 26 `Path(psh.__file__)` sites
(24 files) are unaffected: in all but one, `psh` is the conftest fixture, so
`psh.__file__` is the fixture module's file — `psh/_legacy.py` today, `psh/cli.py`
after — and `.resolve().parents[1]` is the repo root either way (both live directly
under `psh/`); the one bare-`import psh` site (`tests/unit/test_php_eol_notice.py:9`)
resolves via `psh/__init__.py`, same result. Present-tense `_legacy` comments in the
test files are updated in place — exhaustive list: `tests/conftest.py` (`:6, :88,
:101`), `tests/unit/test_house_rules.py` (`:27, :62, :176, :180, :190`),
`tests/unit/test_traffic_aggregation.py:5`, `tests/unit/test_notice.py:45`,
`tests/integration/test_email_config.py:10`,
`tests/integration/test_drupal_notice_render.py:5`,
`tests/integration/test_check_drupal.py:7` (the past-tense
`tests/unit/test_smell_notices.py:47` stays). Comments only; **no assertion, input, or
expected value changes** outside the Deliverable-A test edits.

**Seams:** none new — this is a pure relocation with an explicit why-no-new-seam
statement (Spine spec bar): the cover is (a) the four byte-identical goldens driven
through the real shim→`psh.cli.main()` path by `run_program`, (b) the full existing
suite re-resolved through the repointed fixture (every `psh.<name>` reference exercises
the re-export surface at its new home), (c) the collected-test-count gate (§6), and
(d) `test_abort_e2e` / the artifact suites for the lifecycle path. A relocation-specific
new test would duplicate (b) without adding a failure mode it can catch.

### 2.4 Decisions (D-i14a-1…8, exhaustive)

1. **Task order A → B → C** (§7): B51 dies in the old homes first so C's relocation
   self-diff is clean; B is independent but lands before C so `psh/cli.py` is born
   importing `psh.dns_classify`.
2. **dns_classify import form** — `import psh.dns_classify as dns_classify` (§2.2): keeps
   every qualified call site and the single-object patch seam byte-compatible.

   > **Correction (I14b Task 1).** The decision's invariant is the single shared module
   > object + qualified `dns_classify.<attr>` call sites, not the specific alias
   > syntax — see the §2.2 correction note for the full proof and the one site (
   > `check/pantheon_cdn_change/chain.py:37`) where the PLR0402-mandated `from psh import
   > dns_classify` form now applies instead, once that file came under the broad ruff
   > gate at I14b. Equivalent for the monkeypatch seam: `import psh.dns_classify as a;
   > from psh import dns_classify as b; a is b` → `True`. Ledgered at I14b.
3. **The re-export surface moves intact to `psh/cli.py`.** The alternative — repointing
   every `psh.<name>` test reference to real module homes — touches hundreds of sites
   across the grandfathered `tests/` tree for zero behavior gain; that cleanup belongs
   with I14b's wholesale `tests/` un-grandfathering (ledgered as an I14b option).
   Consequence: the surviving F401s in `psh/cli.py` are **deliberate re-exports**; they
   carry a single block comment naming the contract + per-line `# noqa: F401` only where
   `main()` itself does not use the name (predicted split in §5).
4. **Lifecycle bridge stays call-time** (§2.3) — module-level is a cycle; LEDGER I13's
   "module-level" wording corrected by ledger entry.
5. **`if __name__` tail deleted** — inert since I0; deletion is behavior-free.
6. **§17 Q5 answered: the `pantheon-sitehealth-emails.py` symlink is KEPT** — its
   remaining purpose is ruff/pyright/CodeGraph coverage of the extension-less shim's own
   lines (the shim still assigns `sc.options` and calls `main()`), and it is
   fresh-clone-safe only as a committed file. Recorded here for I14d's audit; CLAUDE.md
   wording updates at I14d.
7. **CLAUDE.md gets minimal accuracy edits only** (A's billing prose; the § Two mock
   seams / conventions sentences that name `psh/_legacy.py` as a live file; the
   dns_classify path) — the wholesale rewrite is I14d's (§11). Every edited claim is
   listed in the task report.
8. **Conftest redesign is the one-line repoint plus comments** — the deeper fixture
   redesign (importing real homes, dropping the sqlalchemy-alias seam) is I14b/test-
   cleanup material, same reasoning as D-i14a-3.

## 3. Behavior bar (CAMPAIGN.md §8, applied)

| Surface | This increment |
|---|---|
| 4 goldens | byte-identical (NEVER) — `git diff 5902b76 -- tests/e2e/__snapshots__/` empty at close |
| `-results.json` / `-notices.csv` / `-run.json` | unchanged (B51 never reached them) |
| Rendered email, U-M in-window runs | loses the B51 section — the §8-amended sanction; not golden-covered |
| stdout/console | unchanged (no planned improvements) |
| Config | no key changes |
| Exit codes / resume / artifact gates | unchanged |
| Hook DAG | one fewer `site_pre_render` hook + produced key; `test_hook_dag.py` still green |

## 4. Tests (test-first at the seams named in §2; carve-outs none)

- **A (RED-first):** the exact-set registration assertion in
  `test_check_umich_annual_billing.py` fails against baseline (two hooks registered),
  passes after deletion. The deleted tests are removed in the same commit; the upcoming
  front-order pin survives (rewritten or pre-existing).
- **B:** the dns suites + `test_golden_cdn_change` pass with the retargeted seam. RED
  evidence: `tests/helpers/dnsfake.py` retargeted first makes the old-path import fail
  loudly (`ModuleNotFoundError: dns_classify`) — structural red, the I13 Task-1
  precedent (watched for the right reason).
- **C:** conftest repoint + relocation land atomically (a partial move cannot be green —
  the I5/I6/I11 single-commit precedent). Cover per §2.3's why-no-new-seam statement.
  The house-rule suite (`test_house_rules.py`) MUST stay green with scopes that still
  walk the moved files (§2.2 RED check for the scope edits).
- **Collected-count gate (§6):** the I0 instrument, reused.

## 5. Ratchet dispositions (measured 2026-07-23 at baseline; PD#14 — re-measure on the assembled files, record deltas)

`psh/cli.py` (from the remnant's 69): 32× F401 → split into (i) names `main()` uses —
plain imports, no noqa; (ii) re-export-surface-only names — `# noqa: F401` under the
D-i14a-3 block comment; (iii) the three seam imports — existing noqa+reasons move
verbatim. 12× E402 + 2× I001 → dissolved by top-of-file consolidation (§2.3 item 2).
6× B023 (loop-variable capture in `main()`'s per-site lambdas/closures) → noqa + inline
reason each (used-immediately-within-iteration; verbatim bodies, no redesign — §3.1
whole-file-coverage rule). 4× F541 → f-prefix drops (I6/I8 precedent). 1× each C408,
DTZ011, ERA001 (delete the dead line, I5/I6 precedent), PLR2004 (noqa, verbatim),
PTH103/PTH110/PTH123 ×2 (noqa — verbatim artifact IO, the I13 disposition; pathlib
migration is I14b+), SIM102/SIM118 (behavior-identical rewrites), C901/PLR0912/PLR0915
(noqa on `main()`'s def — verbatim ~620-line body, the I11/I13 quadruple precedent).
Any unpredicted finding: disposition per precedent classes, recorded in the report and
ledger (the I9/I10 rule — real tool output beats this prediction).

`psh/dns_classify.py` (9): 2× FBT001 (bool positional hints — keyword-only rewrite ONLY
if call-site-compatible, else noqa: signatures are pinned by the dns suites), 2× SIM118,
1× each C901/PLR0912/PLR0913 (noqa, verbatim), PERF203 (noqa — the try/except-in-loop IS
the per-name transient-vs-malformed design), RSE102 (drop parens, behavior-identical).

pyright: the widened `psh/` scope gains both files. I0 whole-tree baseline: `_legacy.py`
36, `dns_classify.py` 1 (LEDGER I0) — expect fewer on cli.py (I2–I13 moved the worst
offenders out). Disposition per the I13 classes: honest annotations first; scoped
`# pyright: ignore[…]` with reasons where the sanctioned widenings force it; **0 errors
at close** (the gate).

## 6. Measurements & gates

- Baseline (full suite, I13 close): **1028 passed / 1 skipped**, 107 snapshots.
- Collected-count arithmetic at close: 1028 + 1 skipped, **minus exactly** the
  Deliverable-A deletions — 2 unit tests (`test_annual_billing_notices.py`), 1 sort
  test deleted + 2 rewritten-in-place (`test_sort_notices_and_subject.py` — rewrites
  don't change the count; ±1 if the §2.1 front-order adjudication deletes rather than
  rewrites), 1 billing-integration test — **plus** any tests this spec adds (expected:
  0 new files). The exact expected number is computed and pinned in the task report
  BEFORE the close run (PD#14 — predicted, then observed).
- All three `./run-tests` gates green; goldens diff empty (§3); pyright **0 errors** on
  the widened scope; both ruff passes clean.

## 7. Task plan (per-task commits, each green — CAMPAIGN.md §12 as amended at I0)

1. **Task A** — B51 deletion (§2.1), RED-first on the exact-set registration pin.
   Commit `feat(campaign-I14a): delete the B51 annual-bill-in-progress notice`.
2. **Task B** — dns_classify move (§2.2), atomic. Commit
   `feat(campaign-I14a): move dns_classify into psh/`.
3. **Task C** — the remnant → `psh/cli.py` + deletion + conftest + config edits (§2.3),
   atomic. Commit `feat(campaign-I14a): relocate main() to psh/cli.py, delete _legacy`.
4. **Close** — whole-branch `/code-review`; full `./run-tests` (live tier if credentials
   present, else `--fast` + ledger note); CLAUDE.md minimal edits if not already in A–C;
   the I14a ledger entry (the split/B51 **amendment records were already appended at
   spec time** — review finding 11; the close entry adds D-i14a-1…8 + discharge
   records: D-i13-1, D-i13-3-corrected, §17 Q5); memory; `/archive-session`; closing
   docs commit with this folder.

Spec committed before implementation (prompts/new-feature-standards.md §Where the spec
goes); adversarial review (`psh-reviewer`, fresh context) precedes the plan.

## 8. Obligations discharged / created

**Discharged here:** D-i13-1 (`main()` address-final); D-i13-3 (bridge — corrected
form); LEDGER I0's fixture-redesign note (minimal form, D-i14a-8); the §3.1
`dns_classify` MAY (exercised); B51 (deleted, §8 amendment); §17 Q5 (answered, recorded
for I14d).

**Created / carried:** re-export-surface repoint + deeper conftest redesign → I14b
option (D-i14a-3/8); `check/umich/__init__.py` stale disabled-branch message → still
I14d (unchanged); everything already ledgered to I14b–I14d.

## 9. Acceptance (run and pasted at close — commands exact)

```
./run-tests                       # all three gates; count per §6; live tier if creds
git diff 5902b76 -- tests/e2e/__snapshots__/         # MUST be empty
uvx ruff check .                                     # narrow set, whole tree
uvx ruff check --config ruff-broad.toml .            # broad set, post-exclude-edits
test ! -e psh/_legacy.py && test ! -e dns_classify.py && echo gone
python -c "import psh.cli, psh.dns_classify; print('import ok')"
./pantheon-sitehealth-emails --help | head -3        # shim → psh.cli.main() alive
```

Results are pasted into this section at close (an unrun acceptance suite is PD#14).

**ACCEPTANCE — run and pasted at close (2026-07-23, HEAD = b39e435 + the two
whole-branch-review doc fixes):**

```
$ ./run-tests --llm            (full suite; live tier ran — terminus token present)
EXIT=0
LLM_SUMMARY passed=1023 failed=0 error=0 skipped=1 xfailed=0 xpassed=0
107 snapshots passed.
1023 passed, 1 skipped, 4 warnings in 39.71s
(three gates: narrow ruff, broad ruff, pyright — all ran, exit 0)
# 1023 = the fast tier's 1021 + the 2 live-marked tests; the 1 skip is
# test_db_credentials.py's importorskip("MySQLdb") on a sqlite-only install.
# Fast-tier count 1021/1/2 = I13 baseline 1026/1/2 minus the 5 Deliverable-A
# test deletions (predicted before observed — task-1-report.md).

$ git diff 5902b76 -- tests/e2e/__snapshots__/
(empty)

$ uvx ruff@0.15.22 check .
All checks passed!

$ uvx ruff@0.15.22 check --config ruff-broad.toml .
All checks passed!

$ test ! -e psh/_legacy.py && test ! -e dns_classify.py && echo gone
gone

$ python -c "import psh.cli, psh.dns_classify; print('import ok')"
import ok

$ ./pantheon-sitehealth-emails --help | head -3
usage: pantheon-sitehealth-emails [-h] [--all] [--resume-from SITE_NAME]
                                  [--date DATE] [--update] [--for-real]
                                  [--config CONFIG] [--only-warn]
```

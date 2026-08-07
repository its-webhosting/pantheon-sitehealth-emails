# LEDGER — Modularization Campaign

Append-only. One entry per completed increment, plus one per CAMPAIGN.md amendment.
This file is how increment N learns what N−1 actually did; if a deviation, discovered
task, or decision is not recorded here (or in the README TODO list), it does not exist.
Entry template: CAMPAIGN.md §12.

## Campaign planning (2026-07-17)

- Produced: `CAMPAIGN.md` (frozen architecture), `BLOCKMAP.md` (B1–B60 map),
  `/workspace/CONTEXT.md` (domain glossary, new), this ledger.
- Baselines: fast tier 727 passed / 1 skipped / 2 deselected; ruff `--isolated` 45
  findings; pyright unmeasured (no binary in container — I0 scope).
- Discovered during planning, dispositioned:
  - Five bugs + dead code → I1 (CAMPAIGN.md §10, BLOCKMAP §Bugs).
  - README's "~55 ruff / 39 pyright" figures stale/unverified → I0 re-measures.
  - B51 second annual-bill notice: marked "remove Aug 2026" — code split in I1,
    deletion decision in I12.
  - WordPress/Drupal duplication + update-table HTML duplication (BLOCKMAP §Bugs 7–8)
    → addressed structurally by I9/I10 (shared gather + `check/addon_updates/`).
- Open questions for I0: exact ruff rule list; pyright strictness per environment;
  whether `dns_classify.py` moves under `psh/` (deferred to I14, MAY).
- Amendment (2026-07-17, user spec review): added the "Whole-file coverage" paragraph to
  CAMPAIGN.md §3.1 — clarification only, no scope change; the module map already
  assigned every top-level def.

## I0 — bootstrap (2026-07-17, closing commit `docs(campaign-I0): close the bootstrap increment`)

Commits (per-task, each green): `b1ccc72` (package move + shim + conftest + coverage),
`d0e3027` (lint/type ratchet), `5b536fa` + `239955d` (README/CLAUDE.md docs), plus this
closing docs commit (ledger + CAMPAIGN amendments + SPEC acceptance + README pyright number).

- **Moved:** the whole 4,752-line program → `psh/_legacy.py` (`git mv`, **zero logic
  changes**; the `__main__` tail is inert in a module, left for I13). New: `psh/__init__.py`
  (docstring), `psh/cli.py` (`from psh._legacy import main, parse_args` re-export), and a new
  7-line thin shim at `./pantheon-sitehealth-emails` calling `psh.cli.main()`. No blocks
  (B-map) moved — I0 moves the file, not logic (§11 row I0).

- **Deviations from CAMPAIGN.md (three amendments, all applied to the document this commit):**
  1. **No console-script entry point** (amends §11 row I0 / D10). The program is repo-rooted
     by design (`find_modules`, templates, `inline-styles.php`, `vendor/`, config symlink are
     all CWD-relative); a pip entry point would need a data-file overhaul serving no campaign
     goal. D10's real benefits (normal imports; native ruff/pyright/CodeGraph coverage; no
     `SourceFileLoader`) all arrive via the package + shim without installation. `pyproject.toml`
     stays deps-only (`py-modules = []`, `packages = []` to stop setuptools auto-discovery
     installing a stale shadow copy — PD#1). §11 row I0 now reads "thin shim (console-script
     dropped — see LEDGER I0 amendment)".
  2. **Grandfather is `psh/_legacy.py` via `ruff-broad.toml` `extend-exclude`** (amends §13,
     which named `pantheon-sitehealth-emails.py` and "per-file-ignores" — both written before
     the legacy-module + two-config mechanics were settled). The shipped mechanism is TWO ruff
     configs, not per-file-ignores: `pyproject.toml` `[tool.ruff.lint]` carries the narrow
     PD-rule set (`E722`/`BLE001`/`S105`/`S106`) that runs EVERYWHERE including `_legacy.py`;
     `ruff-broad.toml` carries `select = ["ALL"]` minus the ignore list and grandfathers the
     remnant via `extend-exclude`. `./run-tests` and `.claude/hooks/ruff-check.sh` run BOTH
     passes; the two files merge into `pyproject.toml` at I14. §13 now names `psh/_legacy.py`
     and "ruff-broad.toml exclude".
  3. **Per-task commits, each green** (amends §12's "one commit (code + dev folder)"). Each I0
     task committed independently once its gates were green; this increment's final (closing)
     commit includes the `development/` folder. Rationale: finer checkpoints serve the campaign
     prompt's revert/inspect intent, and SDD review packages diffs as commit ranges. §12 now
     reads "per-task commits, each green; the increment's final commit includes the dev folder".

- **Ratchet as pinned.** pyright runs in `./run-tests` at **standard** mode, not strict
  (DECISION): `psh/cli.py` re-exports from the untyped legacy module, so strict would fail on
  re-export; strictness ratchets up as increments move typed code in. Scope `[tool.pyright]`
  = `include = ["psh"]`, `exclude = ["psh/_legacy.py"]`. Ruff-broad ignore list (pinned; each
  justified in `ruff-broad.toml`): `COM812`, `ISC001`, `E501`, `Q000`, `Q001`, `Q002`, `Q003`,
  `ANN`, `TD002`, `TD003`, `FIX002`, `EM101`, `EM102`, `TRY003`, `D`, `CPY001`. `CPY001` is a
  **preview** rule in ruff 0.15.22 (cannot fire under non-preview `select=["ALL"]`); ruff
  accepts it in `ignore` with no warning, so it is kept verbatim to document the intent
  (no per-file copyright headers). `D` (docstring convention) is undecided → README TODO.

- **pyright whole-tree baseline (informational; replaces README's unverified "39").**
  **220 errors, 0 warnings, 0 informations** across 118 first-party files, standard mode,
  pyright 1.1.411 (SPEC ACCEPTANCE §Task 5 has the command + breakdown). Measured OUTSIDE the
  scoped gate config via a repo-root config (pyright roots a project at the config's directory
  and ignores includes outside it; a config's `exclude` still drops CLI-passed paths — so
  neither a scratchpad-rooted config nor CLI args can re-include `_legacy.py`, and a repo-root
  temp config is the reproducible form). By area: `tests/` 139, `psh/_legacy.py` 36, `check/`
  21, `plugin/` 18, `script_context.py` 5, `dns_classify.py` 1 (`check/`+`plugin/` = 39, the
  origin of the old figure). The gated scope (`psh/` minus `_legacy.py`) is `0 errors`.

- **Contract/config/sc additions:** none (I0 moves no logic; no `[Check.*]` sections, no new
  contract keys, no `sc` names added or removed).

- **Discovered tasks:**
  - **`Path(psh.__file__).parent` as a repo-root proxy** — 25 sites across 23 files: 22 test files (plus
    `tests/helpers/checkload.py`) anchored repo paths on the program file's parent, which the
    move shifted from repo root to `psh/`. Fixed here, mechanically and minimally:
    `→ Path(psh.__file__).resolve().parents[1]` at exactly those sites. Proper cleanup lands
    when later increments un-grandfather those test files; the `psh` fixture itself is
    redesigned when `_legacy` dies (I13/I14). Disposition: **fixed here**, further cleanup **I13/I14**.
  - **ruff lints explicitly-passed files even when excluded** — passing a path on ruff's
    command line overrides `extend-exclude`, so the edit hook (which passes the just-edited
    file) would lint `_legacy.py` against the broad set. Fixed by giving the broad-pass
    invocation `--force-exclude` and running it from repo-root cwd; documented in
    `.claude/hooks/ruff-check.sh`. Disposition: **fixed here**.

- **Open questions for I1/I2:**
  - I1 (bug fixes) touches `_legacy.py` in place (fixes retire as code moves); it must keep
    the narrow PD set green there (broad set stays grandfathered) and the four goldens
    byte-identical (§10 verified the fixed codes appear in zero goldens).
  - I2 (gateway) is the first real logic move: as it un-grandfathers the wrapper functions it
    deletes them from `ruff-broad.toml` `extend-exclude` and must clean them to the broad set
    + pyright standard in the same change (§13 ratchet; §6 house-style tuple hints replaced).
  - `dns_classify.py` under `psh/` remains a MAY for I14 (unchanged from planning).
- Amendment (2026-07-17, post-Task-5 review): CAMPAIGN.md §13 mechanism paragraph
  rewritten to describe the SHIPPED two-config mechanism (it still said "pyproject gets
  extend-select" and "executionEnvironments", both superseded by amendment 2 above);
  ledger reanchor note corrected to "22 test files plus checkload.py" (23 files total).
  Both changes doc-accuracy only.
- Amendment (2026-07-17, final I0 code review, spec axis): D10's Decision cell still said
  "console-script" after amendment 1 changed only §11 row I0 — CAMPAIGN.md briefly
  self-contradicted. D10 cell now matches. Doc-accuracy only.

## I1 — known-bug fixes (2026-07-17, commits `5518de7..1ff9153` + closing docs commit)

Spec/plan: `development/2026-07-17-mod-I1-bug-fixes/` (SPEC.md carries the pasted
acceptance results). Six per-task commits, each green; full suite at close = 751 passed /
1 skipped **including the live tier**, 27 snapshots, all three gates; four goldens
byte-identical across the whole range (`git diff aa8afd1 -- tests/e2e/__snapshots__/`
empty).

- **Moved:** no blocks (fixes land in place in `psh/_legacy.py` per I0's open-question
  note). Extracted five pure notice-builder helpers as consecutive module-level defs
  above `main()` (preserved-bug-extraction pattern; every literal interior byte-verified
  against the pre-move original by task reviewers AND the final review):
  `build_smell_notices`, `build_php_eol_notice`, `build_annual_bill_upcoming_notice`,
  `build_annual_bill_in_progress_notice`, `build_plan_recommendation_notice`. These
  travel later: smells → I10, php-eol → I8, annual-bill → I12, plan-rec → I7.
- **Fixed (CAMPAIGN §10 / BLOCKMAP §Bugs, all test-first with RED shown on old
  behavior):** (1) B48 composer-smell nesting + wrong interpolated variable;
  (2) B41 shared `php-eol` csv code → `php-eol-warning` (7.4/8.1) / `php-eol-alert`
  (<8.2), following the `updates-*` suffix pattern; (3) B36 unknown-framework sites now
  get a `site_results` entry (`version: "unknown"`, same 3-key row shape) — covered by a
  new offline e2e (`tests/e2e/test_unknown_framework_e2e.py`) asserting the
  `finish_run()` stdout pprint, since `-results.json` is written only on `--all` runs the
  interlock bans; (4) B47 un-gated U-M portal URLs — two of the four named URL sites
  (`extra_message`/`extra_text`) were **dead stores** (assigned, never read; §10's
  4240/4248 refined — bug partially lived in dead code), deleted; the live
  `its-recommends-plan` notice now selects U-M vs generic copy via `umich_enabled()`
  (generic drops the portal anchor AND the June-16-30 downgrade-window sentence — U-M
  billing policy, factually wrong elsewhere); both variants pinned by syrupy snapshots
  (`test_plan_recommendation_notice_render`); (5) B50/B51 duplicate `annual-bill` code —
  B51 now emits `annual-bill-in-progress`; B50 keeps `annual-bill`; B51's Aug-2026
  deletion decision remains I12's; (6) dead code deleted (B40 Gen2 block, overage debug
  query, `# plt.show()`, redundant second `plt.close(fig)` with its stale memory claim).
- **Deviations from CAMPAIGN.md:** none.
- **Contract/config/sc additions:** none. Sanctioned notice-csv value changes (§8 I1
  exception): the three codes above. New **hand-maintained** fixture dir
  `tests/fixtures/terminus-unknownfw/` (copy of `terminus/`, one framework value →
  `"mystery"`, README states `--record` never refreshes it — Invariant 10, cdnchange
  precedent) + conftest constant `TERMINUS_FIXTURES_UNKNOWNFW`.
- **Discovered tasks (dispositions):**
  - Template `email_template.{html,txt}` portal URLs render `sites/0/` in every non-U-M
    run including the non-U-M golden (SPEC Obs. 1) → I12/I14 (goldens freeze it now;
    already on CLAUDE.md's still-hardcoded-U-M list).
  - `php_version < "8.2"` string comparison + KeyError if key absent (Obs. 2) → I8.
  - B47 downgrade path: owner gets NO notice (dead `extra_message` was presumably meant
    for this) and a non-Basic downgrade appends no `site_savings` entry (Obs. 3) → I7
    decides intended behavior.
  - Composer-smell literals carry baked-in 8-space indentation (Obs. 4) → I10.
  - `its-recommends-plan` csv embeds `{savings:,.2f}` — thousands comma inside a
    comma-separated field, variable column count (Obs. 5) → I7, or I3's `Notice`
    class/code-registry work.
  - Residual test gap (final-review triage): `main()`'s umich-only annual-bill call
    sites have no runtime test (goldens are umich-disabled; interlock bans a U-M run) —
    I12's spec author MUST cover this when relocating annual billing to `check/umich/`
    at `site_pre_render`.
- **Process note (PD#14 instance):** one implementer's report Write silently failed
  against a stale `.superpowers/sdd/` report file from I0 and was misreported as
  success; caught by the task reviewer (report content was for the wrong task). Stale
  scratch reports are now purged before dispatch; future increments should start by
  clearing `.superpowers/sdd/task-*-report.md` leftovers.
- **Open questions for I2:** none new — proceed per I0's notes (un-grandfather the
  wrapper functions from `ruff-broad.toml`, clean to broad set + pyright standard,
  replace house-style tuple hints, `GatewayResult`, façade test).

## I2 — gateway extraction (2026-07-17, commits `7044b12` (Task 1), `0141f76` (Task 2), house-rule-scope fix + closing docs commit)

Spec/plan: `development/2026-07-17-mod-I2-gateway/` (SPEC.md carries the pasted acceptance
results). Two per-task code commits, each green, plus a whole-branch-review follow-up commit
(the `ENVIRON_SCOPE` widening below) and this closing docs commit (CLAUDE.md / tests/README.md /
gateway docstrings / memory / this ledger entry). Full suite (live tier present) at close =
**755 passed / 1 skipped** (the 1 skip is `test_db_credentials.py`'s `importorskip("MySQLdb")`
on a sqlite-only install), all three gates; four goldens byte-identical across the increment
(`git diff 8b1466b -- tests/e2e/__snapshots__/` empty).

- **Moved:** the eleven Terminus/WP/Drush subprocess-facing wrapper defs (the 302–597 wrapper
  region of `psh/_legacy.py` **minus** `escape_url`, which §3.1 assigns to `psh/render.py`/I12) →
  `psh/gateway.py`: `run_terminus`, `TerminusError`, `terminus`, `terminus_data`, `wp`, `wp_eval`,
  `wp_error`, `fix_drush_output`, `drush`, `drush_php_script`, `drush_error`. `psh/_legacy.py`
  re-imports all eleven (plus `GatewayResult`), so its ~54 call sites and the `sc` exposure block
  resolve unchanged. Logic and the two column-0 `f"""` notice literals (`wp_error`/`drush_error`)
  moved byte-for-byte (Invariant 8; extracted-block diff pasted empty in the Task 1 report).
- **Deviations from CAMPAIGN.md:** the SPEC's §Broad-ruff-findings table enumerated **seven**
  findings on the moved code; the actual count was **EIGHT**. Wrapping `run_terminus`'s literal
  `return … True`/`return … False` statements in the `GatewayResult(...)` constructor introduced an
  `FBT003` (Boolean-positional-value-in-function-call) the spec did not foresee. Resolved
  **behavior-preservingly** by constructing with the `fatal=` keyword (`GatewayResult(output,
  errors, fatal=True)`) — no `ruff-broad.toml` ignore-list change (that would be a §13 amendment)
  and no `# noqa`. The other seven dispositions landed exactly as specced.
- **Ratchet (§13):** nothing was deleted from `ruff-broad.toml`'s `extend-exclude` this increment.
  The wrappers moved to a **new** file (`psh/gateway.py`), which is gated by the broad ruff set +
  pyright standard from birth (it was never in the exclude list). So LEDGER I0's "un-grandfather the
  wrapper functions from `ruff-broad.toml`" open-question was a **no-op for the exclude list** — its
  premise (functions cleaned in place inside an excluded file) didn't apply once they moved to a
  fresh gated file; the cleaning obligation is discharged by gateway.py being born under the full
  gate (`uvx ruff check --config ruff-broad.toml psh/gateway.py` → All checks passed!; pyright 0
  errors). Recorded per SPEC §Ratchet.
- **Contract/config/sc additions:** `GatewayResult` NamedTuple `(result, errors, fatal)` introduced
  in `psh/gateway.py`, re-exported via the `_legacy` import. **No new `sc` name** (no check/plugin
  references the type — it is unpacked positionally; adding it would be dead façade surface,
  CAMPAIGN.md §17 Q4). **No new contract keys.** New `gateway` conftest fixture and two house-rule
  instruments (no-`subprocess.Popen`-outside-gateway; documented-`sc`-façade-names-exist).
- **Discovered tasks (dispositions):**
  - The `wp`/`wp_eval`/`drush`/`drush_php_script` docstrings said "Returns a 3-tuple" after the
    move → **fixed here** (Task 3): updated to "Returns a GatewayResult (result, errors, fatal)".
    Doc-accuracy only, no logic change; gateway.py re-passed ruff-broad + pyright with 0 findings.
  - **`ENVIRON_SCOPE` house-rule was blind to the program body** (whole-branch review finding).
    `tests/unit/test_house_rules.py`'s PD#6 `os.environ` guard scoped to `check`/`plugin`/
    `dns_classify.py`/`script_context.py`/the 17-line shim — but **not** `psh/`, where the program
    body has lived since campaign I0. A direct `os.environ` read added to `psh/_legacy.py` or
    `psh/gateway.py` (the largest feature-code files) would have passed silently (PD#1/PD#6/PD#14 —
    an instrument blind to what it guards). Latent (grep found no offender) and **pre-existing**
    (introduced at I0's file move, not by I2's tasks), but I2 owns this test file and I2's own
    `_scoped_sources(scope)` parameterization made the fix one word → **fixed here**: added `"psh"`
    to `ENVIRON_SCOPE`, with the new red demonstration (adding `os.environ` to `psh/_legacy.py`
    fails naming it) observed, reverted, and recorded in the test docstring. Suite stayed green.
- **Open questions for I3:** none new — proceed per CAMPAIGN.md §11 row I3 (`psh/configuration.py`;
  `Notice` class + code-uniqueness registry test).

## I3 — configuration module + `Notice` class (2026-07-17, commits `ed2698f` (Task 1), `d21a1d2` (Task 2), plus this closing docs commit)

Spec/plan: `development/2026-07-17-mod-I3-config-notice/` (`SPEC.md` cites CAMPAIGN.md by
section; task reports under `.superpowers/sdd/task-{1,2}-report.md` carry the pasted
red/green evidence and pre-suppression ruff findings). Two per-task code commits, each
green, plus this closing docs commit (CLAUDE.md / CAMPAIGN.md §3.1 amendment / this ledger
entry). Full suite at close (`--fast`; **no live credentials in this environment**, so the
live tier did not run — same caveat as prior increments where noted) = **761 passed / 1
skipped / 2 deselected**, all three gates green, 27 snapshots; four goldens byte-identical
across the increment (`git diff 45b8a88 -- tests/e2e/__snapshots__/` empty).

- **Moved:** `config_substitution`, the DEFER machinery (`_DEFER_TAG` + the two compiled
  regexes), `process_config`, `gate_disabled_sections`, `load_news_items`, `umich_enabled`,
  and `cloudflare_enabled` (the six defs + DEFER machinery named in SPEC §Deliverable A) from
  `psh/_legacy.py` into a new `psh/configuration.py`, re-imported back into `_legacy.py` (I2
  gateway precedent — the ~11 existing tests calling `psh.process_config` etc. needed no
  repoint). **New:** `psh/notice.py` (`Severity` StrEnum, frozen `Notice` dataclass,
  `NoticeRegistry`, `DuplicateNoticeCodeError`, module `registry`) — pure, stdlib-only, no
  `script_context` dependency. `SiteContext.add_notice` (`script_context.py`) now accepts a
  `Notice` or the legacy dict via a new `_notice_to_dict` projection. The `no-domains` notice
  (`psh/_legacy.py`, B29) was converted to construct a `Notice` end-to-end, with its code
  registered once at module scope; its `html`/`text` f-string interiors (including the
  pre-existing "the ste" typo) moved byte-for-byte.

- **Deviations from CAMPAIGN.md:**
  1. **New module `psh/notice.py`** — §3.1's module map is exhaustive and named no home for
     the `Notice` type (§6 introduces the type without pinning a module). Handled as a
     CAMPAIGN.md **amendment**, not a ledger-note-only, per §Preamble ("edit the document
     *and* append a ledger entry"): this closing commit adds the one-row `psh/notice.py`
     entry to §3.1 (`Notice`, `Severity`, `NoticeRegistry`, `DuplicateNoticeCodeError`,
     `registry`) between the `psh/gateway.py` and `psh/db.py` rows.
  2. **PoC converts `no-domains` (B29), out of I3's declared block scope** (§11 row I3 lists
     only the config functions). Deliberate — §6 says the class is "adopted per increment",
     the user chose `no-domains` as a PoC, and it is core-and-staying-core (CLAUDE.md: "remain
     in core") so no later increment re-touches it. The notice's *home* is unchanged, only its
     representation, so this is a **ledger note**, not a §3.1/architecture change.
  3. **`sc.Notice`/`sc.Severity` reach `sc` via a module-level `from psh.notice import Notice,
     Severity` import at the top of `script_context.py`, NOT the `sc.Notice = Notice` /
     `sc.Severity = Severity` assignment pair the SPEC's §sc re-exports section showed** (added
     "near the existing `sc.umich_enabled = …` lines" in `_legacy.py`). Task 2's dispatch
     carried an explicit correction (surfaced by the Task 2 review, folded into the task
     brief before implementation): a plain module-level import makes both names module
     attributes automatically, so the assignment pair would have been a same-observable-effect
     duplicate of the import — the DRY Engineering Preference favors the single mechanism. The
     façade surface is identical either way (`hasattr(sc, "Notice")` etc. — pinned by
     `test_documented_sc_facade_names_exist`), so this is a mechanism choice, not a behavior
     change; recorded here because the SPEC's illustrative code block, read literally, would
     have produced dead/duplicate assignment lines.

- **Contract/config/sc additions:** `sc.Notice`, `sc.Severity` (mechanism above). **No new
  contract keys** — no phase, `site_context` key, or config section was added; `Notice`
  is a producer-side representation change only. `sc.register_notice_code`/`sc.registry` were
  **NOT** added (SPEC §sc re-exports, D — deferred until a `check`/`plugin` package first
  adopts `Notice`; the PoC imports `registry` from `psh.notice` directly, being core code).

- **`script_context.py` typing fix:** `options`/`config` module globals, previously untyped
  `= {}`, are now `options: argparse.Namespace = argparse.Namespace()` and
  `config: dict[str, Any] = {}` (new `argparse`/`Any` imports) — the minimal fix pyright
  standard mode needed to resolve `sc.options.verbose`/`sc.options.config` inside the moved
  `psh/configuration.py`. No other name in `script_context.py` was retyped (it stays
  grandfathered from the broad ruff ratchet; this is an out-of-gate, minimal, honest fix per
  the SPEC's own instruction).

- **Ratchet (§13):** both new files gated from birth — neither is nor was in
  `ruff-broad.toml`'s `extend-exclude`. `uvx ruff check --config ruff-broad.toml
  psh/configuration.py psh/notice.py` → "All checks passed!"; pyright standard mode over
  `psh/` minus `_legacy.py` → 0 errors. Nothing deleted from `extend-exclude` (same as I2 —
  the moved/new code lands in fresh gated files, not an un-grandfathered old one).

- **Ruff/pyright dispositions actually applied (corrections to the SPEC's finding table,
  both confirmed against real ruff/pyright output by the Task 1 implementer, not assumed):**
  - **`PLR2004` lands on only the two `sc.options.verbose >= 2` comparisons**, not the
    `> 1` one the SPEC's illustrative table also listed: ruff's default magic-value
    allowlist already covers `-1, 0, 1`, so `> 1` never triggers the rule, and a `# noqa:
    PLR2004` there is a live `RUF100` (unused-noqa) finding. Dropped from that line; kept
    (with the SPEC's inline reason) on both `>= 2` lines.
  - **`S101` (`Use of assert detected`) on both `best_match is not None` asserts** — a real
    finding the SPEC's ruff-findings table didn't enumerate (that table covered the
    moved-as-is code; the pyright-findings section separately *mandates* the asserts, but
    neither section flagged the S101 the asserts themselves introduce). Resolved inline:
    `# noqa: S101` with a reason (pyright type-narrowing only, not a security check).
  - **`glob` and `Any` were in fact orphaned** in `psh/_legacy.py` by the move — the SPEC's
    "expect none" prediction for orphaned imports was wrong for these two (`load_news_items`
    was their only user); `tomllib`/`re`/`shlex`/`sys`/`escape`/`pprint` all had other live
    users as predicted. Removed per the SPEC's own fallback instruction ("remove only what
    this change orphans").
  - All other dispositions (the `C901`/`PLR0912`/`PLR0915` triple noqa on
    `config_substitution`, the `FBT002` keyword-only fix, `SIM118`, `PTH207`/`PTH123`) landed
    exactly as the SPEC specified.

- **Discovered tasks (dispositions):**
  - **Extra-csv-field `Notice` modeling is deferred** (SPEC §Notice field set, by design —
    not newly discovered here, but re-flagging its disposition for I4+): `Notice` currently
    carries `severity, code, html, text, short, icon, order` — no `csv`/`csv_extra`. A notice
    whose csv needs extra fields (e.g. `turned-off,{name}`, the `its-recommends-plan`
    savings figure) stays a dict until the first increment that converts one, which MUST
    amend CAMPAIGN.md §6 (add the field) via its own ledger entry — not silently widen
    `Notice` here. Disposition: **first adopting increment** (candidates per LEDGER I1:
    `check/addon_updates/` smells, I10; `annual-bill`/`annual-bill-in-progress`, I12; the
    `its-recommends-plan` comma-in-csv issue, I7).
  - No other discovered tasks — Task 1/Task 2's own reports found no further gaps beyond the
    three ruff/pyright corrections recorded above.

- **Open questions for I4:** none new beyond CAMPAIGN.md §11 row I4 (`psh/modules.py`:
  `find_modules`, the hook engine, and the `consumes`/`produces` DAG additions §4 describes).
  I4's spec author should note that `psh.notice.registry` is import-time-once metadata (same
  contract as `sc.substitutions`/`sc.hooks`, per `psh/notice.py`'s own "Reload constraint"
  docstring) — relevant if the DAG work touches module reload/re-registration semantics.

## I4 — hooks + DAG + contract registry (2026-07-20, commits `82d62ff..1f2a6af` + closing docs commit)

Spec/plan: `development/2026-07-20-mod-I4-hooks-dag/` (SPEC.md carries the pasted acceptance
results; task reports under `.superpowers/sdd/task-{1..6}-report.md` carry the red/green
evidence). Six per-task code commits plus one review-fix commit, each green, plus this
closing docs commit (CLAUDE.md / memory / this ledger entry / the dev folder). Full suite at
close **including the live tier** (Terminus token present) = **782 passed / 1 skipped**
(the skip is `test_db_credentials.py`'s `importorskip("MySQLdb")`), all three gates, 27
snapshots; four goldens byte-identical across the increment
(`git diff d46f56d -- tests/e2e/__snapshots__/` empty).

- **Moved:** `find_modules` (from `psh/_legacy.py`) and the hook engine — `PHASES`,
  `_valid_hook_name`, `add_hook`, `invoke_hooks` (from `script_context.py`) — into the new
  `psh/modules.py` (gated from birth). `script_context.py` re-exports
  `PHASES`/`add_hook`/`invoke_hooks` via a top-of-file `from psh.modules import …` (the I3
  `Notice`/`Severity` mechanism), so every `sc.*` call site resolves unchanged; `_legacy.py`
  re-imports `find_modules` + the new names. **New:** mandatory `consumes`/`produces`
  declarations (§4 condition 5, enforced at `add_hook` — nothing enters `sc.hooks`
  undeclared); `validate_hooks()` (§4 conditions 1–4 as named `HookDagError` subclasses:
  `UnproducedKeyError`, `DuplicateProducerError`, `HookCycleError`, `LaterPhaseKeyError`),
  called in `main()` after the check-import loop; `ordered_hooks()` (Kahn, registration-order
  tie-break) used by `invoke_hooks`; the authoritative `CONTRACT` registry +
  `stuff_traffic_contract`/`stuff_gather_contract` extracted from `main()`'s B28/B37 stuffing
  lines (registry-pinned by `tests/unit/test_contract_registry.py`, alongside
  `dns_classify.stuff_dns_contract`); the **`run_finish`** phase (first statement of
  `finish_run()`, completed AND aborted runs). All 11 in-repo `add_hook` registrations
  retrofitted with code-verified declarations; permanent
  `tests/integration/test_hook_dag.py` loads every real check/plugin package and validates.

- **Deviations from CAMPAIGN.md (all ledger notes, no amendments — each stays within §4's
  observable contract; rationale in SPEC D-i4-1…7):**
  1. The mutable `hooks` dict **stays in `script_context.py`** (§3.1 moves the engine
     functions; §3.4 bars new module-level mutable state in `psh/`, and `reset_sc` rebinds
     `sc.hooks` — a second home would silently desync, PD#14). Engine functions read it via
     a call-time `import script_context as sc` (cycle-avoidance; module docstring diagram).
  2. **Dotted events must declare `consumes`/`produces` BOTH empty** — §4's "dotted events
     unchanged" read as invocation semantics, not registration schema; a non-empty
     declaration on a phase-less event is unvalidatable and therefore fatal.
  3. **Condition 5 enforces at `add_hook` time** (stricter placement than §4's
     "module-load completion"; conditions 1–4 validate at load completion as written).
  4. **Invoke order is computed per invocation** by pure `ordered_hooks()` rather than
     stored at validation (§4 diagram says "stored") — same inputs, same order; removes the
     stale-cache mode for tests that register without validating.
  5. **`run_finish` fires with no arguments until I13's `RunState`** (§4 says "receiving
     the RunState", a type that does not exist until I13; no consumer exists, so the
     signature change then is safe).
  6. **B2/B4 module-import loops stay in `main()`** (§3.1 assigns them to `psh/modules.py`
     eventually; §11 row I4 does not list them — they move with `main()`'s final form, I13).

- **Contract/config/sc additions:** `run_finish` phase (registry entry `()` — CLAUDE.md
  table row added). **No new contract keys, no config keys, no new `sc` names** (the
  re-exported engine names already existed on `sc`). SPEC §6 correction during Task 3:
  `check.cloudflare.cache` consumes `['fqdns_behind_cloudflare', 'primary_domain']` — the
  spec-time grep pattern (`site_context[`) missed the `.get("primary_domain")` read at
  `cache.py:233`; the brief's mandated code re-verification caught it (PD#14 working as
  designed).

- **Ratchet (§13):** `psh/modules.py` born gated (broad ruff + pyright standard, 0
  findings). **`script_context.py` un-grandfathered** — deleted from `ruff-broad.toml`
  `extend-exclude`; findings fixed: `I001`, 2× `SIM401` (`.get` rewrites), 2× `PLR1714`
  (tuple-membership rewrites, deliberately tuples not ruff's suggested set literals — no new
  hashability assumption), all equivalence-argued in the Task 6 report. No ignore-list
  changes; noqa inventory in `psh/modules.py`: `PLC0415` (call-time sc imports, cycle
  reason), `PTH116`/`PTH118` (find_modules keeps str paths for its `.split("/")`),
  `PLR0913` (stuff_gather_contract's spec-pinned 7-arg signature).

- **Discovered tasks (dispositions):**
  - **Pre-existing raw hook-dict write** in `tests/integration/test_plugin_umich_portal.py`
    (`sc.hooks[...] = [...]` bypassing `add_hook`) broke under `ordered_hooks`' unconditional
    key indexing → **fixed here** (Task 5), converted to a declared `add_hook` call;
    repo-wide grep confirmed it was the only instance (fix-the-class rule).
  - `tests/helpers/checkload.py` gained a backward-compatible `base=` param so the DAG test
    can load `plugin/` packages standalone → **fixed here** (Task 5).
  - The two pre-existing unknown-phase fatals interpolated `hook_name` unescaped
    (Invariant 6 gap, latent since the engine's script_context days) → **fixed here**
    (Task 5, §8 sanctions stdout improvement).
  - `main()`'s `except HookDagError` → print + exit glue is untested (every condition is
    proven red at the `validate_hooks` seam; the goldens prove the success path through
    `main()`) → accepted, **noted here** (PD#14: the glue rests on inspection).
  - `run_finish` abort-path firing is covered transitively (shared unconditional first line
    + `test_abort_run.py` proves `finish_run` runs on abort) → accepted per SPEC §9;
    a direct probe in the abort tests is a cheap add if `finish_run`'s call structure ever
    changes → **noted here**.
  - **Runtime-registered hooks bypass DAG conditions 1–4** (validation runs once,
    post-import; only `add_hook`'s declaration check fires later). No in-repo hook registers
    dynamically; import-time registration is the assumed model → **I13** (lifecycle) should
    make the assumption explicit when `main()` reaches final form.
- **Open questions for I5:** none new — proceed per CAMPAIGN.md §11 row I5 (`psh/db.py`;
  DB test suites relocated intact; note the resume helpers stay behind for I13).

## I5 — DB-layer move (2026-07-20, commit `c291a26` (Task 1) + this closing docs commit)

Spec/plan: `development/2026-07-20-mod-I5-db/` (`SPEC.md` carries the pasted acceptance
results, corrected — see below). One code commit (Deliverables A–D landed atomically:
partial application cannot be green), plus this closing docs commit (CLAUDE.md / memory /
this ledger entry / SPEC §9 acceptance). Full suite at close **including the live tier**
(Terminus credentials present in this environment) = **782 passed / 1 skipped**, all three
gates, 27 snapshots; four goldens byte-identical across the increment
(`git diff 1cf37d3 -- tests/e2e/__snapshots__/` empty).

- **Moved:** exactly the §3.1 `psh/db.py` row — `Base`, `PantheonTraffic`,
  `PantheonOverageProtection`, `TrafficRow`, `OverageProtectionRow`,
  `DatabaseUnavailableError`, `record_db_reconnect`, `db_retryable`, `db_retry`,
  `update_traffic_rows`, `insert_traffic_rows`, `load_traffic_rows`,
  `load_overage_protection_window`, `db_engine_args` — into the new `psh/db.py`, gated
  from birth, re-imported into `psh/_legacy.py` (I2/I3 pattern) so call sites, the `psh.*`
  test references, and the `sc.db_engine_args` exposure line all resolve unchanged.

- **Deviations from CAMPAIGN.md:** none (all of the below are SPEC-level decisions or
  ledger notes within §11 row I5's own scope, not amendments to CAMPAIGN.md):
  1. **D-i5-1 — the two reconnect counters move to `script_context.py`, not `psh/db.py`.**
     §3.1's `psh/db.py` row names `record_db_reconnect` (the function) but neither counter
     dict; §3.4 bars new module-level mutable state in `psh/` (the same rule that kept
     `sc.hooks` in `script_context.py`, LEDGER I4). The deciding defect class: the writer
     (`db_retry`, now in `psh/db.py`) and the remnant readers (`finish_run`/`abort_run`,
     staying in `psh/_legacy.py` until I13) would otherwise hold **separately rebindable
     bindings of the same name** across two modules — the exact I2 `psh.gateway.run_terminus`
     seam lesson (PD#14: a stale-namespace patch silently fails to intercept). One owning
     namespace dissolves it: `script_context.py` defines `db_reconnects_by_site: dict[str,
     int] = {}` / `db_reconnect_failures_by_site: dict[str, int] = {}` (829–838's contract
     comments moved verbatim), `db_retry` writes `sc.db_reconnect[s|_failures]_by_site`, the
     remnant readers read the same `sc.` names. **§6 already schedules "the reconnect
     counters" into I13's `RunState`** — this is their scheduled interim home, not a new
     permanent surface.
  2. **D-i5-3 — "DB test suites relocated intact" (§11 row I5) reads as: targets relocate,
     files don't.** The suites already lived in their tier-named homes
     (`tests/unit/test_db_resilience.py`, `tests/integration/test_db_roundtrip.py`,
     `tests/integration/test_db_credentials.py`, plus `test_traffic_table_rows.py`,
     `test_abort_run.py`, `test_finish_run.py` for the counter seam specifically) and stayed
     there; the *only* mandatory edit was the counter-seam repoint (every
     `monkeypatch.setattr(psh, "db_reconnect[s|_failures]_by_site", …)` and every
     `psh.db_reconnect[s|_failures]_by_site` assertion, 56 sites across 5 files,
     retargeted to `script_context`/`sc`). No assertion weakened, no test dropped,
     collected count unchanged (see the acceptance figures above).
  3. **B10/B11 stay in `main()`** (`db.create_engine`/sessionmaker/`create_all`,
     `_legacy.py:1651–1665`) — §3.1 assigns them no module and §11 row I5 lists defs only;
     per CAMPAIGN.md §11 row I5's own text, they move with `main()`'s final form at I13.
  4. **Remnant blank-line collapse, disclosed by the implementer, whitespace only,
     reviewer-verified.** The brief's line-range deletions, applied to non-contiguous
     regions of `psh/_legacy.py`, left runs of up to 8 blank lines where deleted blocks
     abutted (around `ResumeSiteNotFoundError`/`sites_from_resume_point`/
     `merge_prior_results`, which stayed for I13). Collapsed to the file's standard 2 blank
     lines — no code line touched, confirmed by task review as formatting debris cleanup
     (Definition of Done's "no debug cruft" line), not a scope violation of "verbatim except
     the named edits" (that rule binds the *moved* bodies in `db.py`, not the remnant's
     leftover whitespace runs).
  5. **SPEC finding-table correction (PD#14).** SPEC §5's finding table enumerated
     `db_retry(…, site: str = None)` → `site: str | None = None` but not
     `record_db_reconnect`'s own `site: str` parameter, which `db_retry` passes `site`
     straight into. Running the type gate on the real moved assembly caught this as
     `reportArgumentType` at all four call sites (watched red, then fixed — PD#14: the
     instrument was allowed to prove itself before being trusted). Disposed the same way as
     the sibling edit: retyped `site: str | None` — the body already treats `None` as
     `"(no site)"` (`key = site if site is not None else "(no site)"`), so this is an honest
     annotation fix, not a behavior change. Task reviewer confirmed the disposition correct.
  6. **SPEC §7/§9 baseline correction (PD#14, this closing task).** Both sections originally
     stated the `--fast`-tier collected-count baseline as "782 passed / 1 skipped" — that
     figure is LEDGER I4's **full**-tier count (`--fast` plus the live tier, credentials
     present at I4 close). The actual `--fast`-tier baseline is **780 passed / 1 skipped / 2
     deselected**. Both SPEC spots corrected; 782 is never pasted as a `--fast`-tier
     expectation anywhere in this increment's documents.

- **Contract/config/sc additions:** two new `script_context.py` module attributes,
  `db_reconnects_by_site` / `db_reconnect_failures_by_site` (D-i5-1 above) — process-global
  mutable state like `sc.hooks`, **not** check-facing API, so they do NOT join
  `test_documented_sc_facade_names_exist` (§11 row I5 / SPEC §1 non-scope, explicit). No new
  contract keys, no config keys.

- **Ratchet (§13):** `psh/db.py` born gated (broad ruff + pyright standard, 0 findings from
  birth); `script_context.py` (already un-grandfathered since I4) stayed clean after the two
  counter additions. Nothing deleted from `ruff-broad.toml`'s `extend-exclude` this
  increment (same as I2/I3 — the moved code lands in a fresh gated file, not an
  un-grandfathered old one; `psh/_legacy.py` stays grandfathered). Dispositions: ERA001
  dead-schema comment deleted (`PantheonTraffic`'s `# id: Mapped[int]…` line); RUF013/
  pyright on `db_retry`'s `site` param → `str | None`; DTZ007 on `update_traffic_rows`'s
  naive `strptime` → `# noqa: DTZ007` with an inline reason (Pantheon's `env:metrics`
  timestamps are naive date markers; attaching a tzinfo risks an off-by-one-day shift, a
  behavior change a move may not make); pyright on `db_engine_args` → `-> tuple[str, dict]`
  (§6 house-style replacement); pyright `reportAttributeAccessIssue` on `sc.db_reconnect…`
  resolved by Deliverable B's typed module-level definitions. Plus the one
  ledger-recorded correction above: `record_db_reconnect`'s own `site` param, also
  `str | None`.

- **Discovered tasks (dispositions):**
  - `record_db_reconnect`'s untyped-Optional `site` param, not named by SPEC §5's finding
    table → **fixed here** (Task 1; see Deviation 5 above).
  - Blank-line debris from the non-contiguous line-range deletions → **fixed here**
    (Task 1; see Deviation 4 above).
  - SPEC §7/§9's "782" `--fast`-tier baseline, actually the I4 full-tier figure →
    **fixed here** (Task 2; see Deviation 6 above).
  - No other discovered tasks — Task 1's report found no further gaps beyond the two
    ruff/pyright corrections and the whitespace cleanup recorded above.

- **Open questions for I6:** none new — proceed per CAMPAIGN.md §11 row I6
  (`psh/traffic.py`: `get_old_metrics`, `estimate_month_visits`,
  `build_traffic_table_rows`, the `traffic_table_columns` global, the metrics
  gather + DB update/load flow B22–B26, and the visits-by-month aggregation B43;
  source lines 598–671 and 977–1127 per §11's table). I6's spec author should note that
  `build_traffic_table_rows` (staying in `_legacy.py` until I6, currently `:510`) is one of
  `db_retry`'s five named idempotent units (CLAUDE.md § Database) — it is passed to
  `db_retry(session, unit, …)` as a `lambda` from the call site in `_legacy.py` (`:3460`),
  not imported by `psh/db.py` itself (`db_retry` is a generic retry wrapper around any
  callable, with no compile-time dependency on the unit's home module). So no import needs
  re-verifying at I6 — the coupling is call-site-only — but I6 should keep `db_retry`'s
  docstring/CLAUDE.md's "five named idempotent units" list in sync once
  `build_traffic_table_rows` moves to `psh/traffic.py`.

## I6 — traffic-layer move (2026-07-20, commit cb01934 + closing docs commit)

Spec/plan: `development/2026-07-20-mod-I6-traffic/` (`SPEC.md` cites CAMPAIGN.md by section;
`.superpowers/sdd/task-1-report.md` carries the combined RED/GREEN evidence for both plan
tasks). One code commit (`cb01934`), plus this closing docs commit (CLAUDE.md / memory /
this ledger entry / SPEC §9 acceptance). Full suite at close **including the live tier**
(Terminus credentials present in this environment) = **790 passed / 1 skipped**, all three
gates, 27 snapshots; four goldens byte-identical across the increment
(`git diff 5de11a4 -- tests/e2e/__snapshots__/` empty).

- **Moved:** exactly the §3.1 `psh/traffic.py` row — `traffic_table_columns`,
  `get_old_metrics`, `estimate_month_visits`, `build_traffic_table_rows` — plus four **new**
  flow functions extracted from `main()`'s per-site loop body: `update_site_traffic`
  (B22+B23), `import_older_site_metrics` (B24), `load_site_traffic` (B26), and
  `aggregate_visits_by_month` (the B43 aggregation loop only). All re-imported into
  `psh/_legacy.py` (I2/I3/I5 pattern), so `main()`'s call sites and the tests' `psh.<name>`
  references resolve unchanged.

- **Deviations from CAMPAIGN.md:** none (all of the below are SPEC-level decisions or ledger
  notes within §11 row I6's own scope, not amendments to CAMPAIGN.md):
  1. **D-i6-1 — loop control, option gating, and B25 stay in `main()`; the flow functions
     signal via return values, never `continue`.** A `continue` cannot cross a function
     boundary, and §3.3 names the site-loop skeleton (B25 included) as staying in `main()`,
     while §11 row I6 assigns the B22–B26/B43 flow to `psh/traffic.py` — read as: the flow
     *bodies* move, loop control does not (resolves the §11-row-I6-vs-§3.3 tension).
     `update_site_traffic` returns `bool` (`main()`: `if not update_site_traffic(...):
     continue`); `import_older_site_metrics` returns `None` under `main()`'s existing
     `sc.options.import_older_metrics` gate + `continue`; B25 (the `--update` continue)
     stays verbatim between the two call sites, exactly where it is today.
  2. **D-i6-2 — `overage_blocks` bridges via a call-time import.**
     `build_traffic_table_rows` calls `overage_blocks`, which §3.1 assigns to `psh/plans.py`
     (I7) but which must stay in `_legacy.py` this increment (`plan_costs` and the
     `psh.overage_blocks` test references still live there); a module-level import would be a
     cycle (`_legacy` imports `psh.traffic` for the re-exports). Resolved with a call-time
     `from psh._legacy import overage_blocks` at the top of the function body
     (`# noqa: PLC0415`, the I4 `psh/modules.py` precedent). **Temporary until I7**, which
     moves `overage_blocks` into `psh/plans.py` and MUST replace this with a module-level
     `from psh.plans import overage_blocks` (**I7 obligation** — repeated under Open
     questions below).
  3. **D-i6-3 — the `psh.db` re-imports in `_legacy.py` stay**, even though `main()` no
     longer calls `update_traffic_rows`/`insert_traffic_rows`/`load_traffic_rows` directly
     (those calls now live in `psh/traffic.py`): 22 test references across
     `tests/conftest.py`, `test_traffic_table_rows.py`, and `test_db_resilience.py` resolve
     `psh.update_traffic_rows`/`psh.insert_traffic_rows`/`psh.load_traffic_rows`/
     `psh.PantheonOverageProtection` through the `psh` fixture — not orphaned, so the "remove
     only what this change orphans" rule's negative case applies, same as I5's D-i5-3.
  4. **D-i6-4 — B43 moves as a pure function; its consumers stay.**
     `aggregate_visits_by_month(rows, start_date, end_date) -> tuple[dict, dict]` is the
     seed-every-month-to-0 + sum-visits + last-row-wins `plan_on_day` loop, pure (no `sc`, no
     I/O, per §3.4). The verbose `pprint` diagnostics block (wired to `sc.options.verbose`,
     not aggregation), the empty-`plan_on_day` synthetic-day guard, and the
     `build_plan_over_time` call + its date/chart prep all stay in `main()` for I7/I11 — §3.1's
     "visits-by-month aggregation (B43)" is read as the aggregation loop only.

- **Process note:** the PLAN's Task 1 (RED) and Task 2 (the move + GREEN) ran as **one
  dispatch and one atomic commit** — a partially applied move cannot be green (Deliverables
  A–C land together or not at all), so red tests could not themselves be committed. The
  plan's task split was SPEC §7's; the commit-discipline rule ("per-task commits, each
  green") held — the single commit is that task's green checkpoint, same shape as I5's one
  atomic Deliverables-A–D commit.

- **Contract/config/sc additions:** none. No new contract keys, no config keys, no new `sc`
  names (nothing in the move set is on `sc`; grep-verified per SPEC §1 non-scope).

- **Ratchet (§13):** `psh/traffic.py` born gated (broad ruff + pyright standard), 0 findings
  after dispositions. Measured: 2× `DTZ007` noqa (naive-date `strptime` calls —
  `get_old_metrics`'s fetch-timestamp parse and `build_traffic_table_rows`'s month-label
  re-parse; attaching tzinfo risks an off-by-one-day shift, a behavior change a move may not
  make — the I5 precedent); 2× `PLR2004` noqa (`estimate_month_visits`'s 25-/15-day
  extrapolation-weighting thresholds); a quadruple `C901`/`PLR0912`/`PLR0915`/`PLR0913` noqa
  on `build_traffic_table_rows`'s def (moved verbatim, no algorithmic redesign per §3.1's
  whole-file-coverage rule; the 12-arg signature is pinned by `test_traffic_table_rows.py`
  and the `main()` call site); one call-time-import `PLC0415` (the D-i6-2 bridge); `SIM118` +
  `PLC0206` resolved by rewriting `for month in visits_by_month.keys():` to
  `for month, month_visits in visits_by_month.items():`; 3× `PLR1730` + `FURB136` resolved by
  rewriting `if`-guard clamps to `max()`/`min()` (equivalent on totally-ordered dates); 2×
  `F541` resolved by dropping unnecessary `f`-prefixes; one `ERA001` (commented-out debug
  pair in the B26 region) resolved by **deletion**, not carry-forward (ratchet disposition
  "cleaned exactly once, as it moves" — I5's `# id:` precedent). Nothing removed from
  `ruff-broad.toml`'s `extend-exclude` this increment (fresh gated file — I2/I3/I5 precedent;
  `psh/_legacy.py` stays grandfathered).

- **Discovered tasks (dispositions):**
  - **Fixture-shadowing defect in the plan's own integration-test code.** All four
    `psh.traffic.*`-calling tests in `tests/integration/test_traffic_flow.py` (written
    verbatim per the brief) initially went **red for the wrong reason**
    (`AttributeError: module 'psh._legacy' has no attribute 'traffic'`), not the specced
    seam. Root cause: each test function declares `psh` as a fixture parameter (the `psh`
    fixture returns `psh._legacy`), which shadows the file's module-level `import psh.traffic`
    inside the function body — `psh.traffic.update_site_traffic(...)` then resolved as
    attribute access on `_legacy` (which has no `traffic` attribute), not on the top-level
    `psh` package. **Fixed here**, per PD#14 (never weaken a test to make it green): three of
    the four affected functions were converted to `from psh.traffic import
    import_older_site_metrics, load_site_traffic, update_site_traffic` at module level,
    called unqualified — the existing `test_contract_registry.py`/`test_hook_dag.py`
    local-reimport pattern didn't transplant cleanly because one test also needs
    `psh.TrafficRow`, which only resolves through the fixture's `psh` binding. No assertion,
    input, or expected value changed in any test.
  - The commented-out `# for row in results:` / `#    sc.debug(row, level=2)` debug pair in
    the B26 region — **deleted, not moved** (ERA001; see Ratchet above).
  - **Observation, no action:** `traffic_table_columns` opens with `month`/`visitors` listed
    twice (entries 1–2 = 3–4); both templates render the full list
    (`email_template.html:359`) and `[1:]` (`:374`, `email_template.txt:105`), so the
    duplication is rendered and golden-frozen. Whether it's a deliberate responsive-layout
    device or a latent bug is unresolved; disposition: **leave**, a post-campaign question —
    any change now would violate Invariant 1.
  - **Review minor:** increment SPECs for pure-move increments (I5, I6) carry no PD#8 flow
    diagram even though the moved flow is non-local (crosses function/phase boundaries) —
    noted here for future increment spec authors; no action this increment.

- **Open questions for I7:** proceed per CAMPAIGN.md §11 row I7 (`psh/plans.py`; `PlanInfo`;
  D7 `--only-warn` plan recommendation; plan/cost contract keys) **plus** the D-i6-2
  obligation above (replace `build_traffic_table_rows`'s call-time
  `from psh._legacy import overage_blocks` with a module-level
  `from psh.plans import overage_blocks` once `overage_blocks` lands in `psh/plans.py`)
  **plus** LEDGER I1's carried items for I7 (B47 downgrade-path behavior decision; the
  `its-recommends-plan` comma-in-csv issue).

## I7 — plans-layer move + D7 (2026-07-21, commits `b74b5a6`, `641db2f`, `24c5892`, `1d32b9f`, `8053f8e`, `15fb36d` + closing docs commit)

Spec/plan: `development/2026-07-20-mod-I7-plans/` (`SPEC.md` §9 carries the pasted
acceptance; task reports + reviews under `.superpowers/sdd/`, incl. the whole-branch
review at `i7-final-review.md` and its fix report). Four per-task code commits + one
docs-fix commit + one final-review fix commit, each green, plus this closing docs commit.
Full suite at close **including the live tier** (Terminus credentials present) =
**810 passed / 1 skipped**, all three gates, 27 snapshots; four goldens byte-identical
across the increment (`git diff 3195c81 -- tests/e2e/__snapshots__/` empty).

- **Moved:** exactly the §3.1 `psh/plans.py` row — `cost_table_columns`,
  `overage_blocks`, `contract_year_end`, `plan_costs`, `build_plan_over_time`, plus the
  I1-extracted `build_plan_recommendation_notice` — into the new `psh/plans.py` (gated
  from birth), re-imported into `psh/_legacy.py` (I2/I3/I5/I6 pattern). **New:**
  `PlanInfo`/`PlanCatalog` (§6's I7 type; `from_config` performs B12's `"-"`→`None`
  normalization mutating the config sub-dict in place, carries B9's overage constants as
  fields — the two B9 reads stay verbatim in `main()` per §3.3 and feed `from_config`),
  `resolve_plan_name` (B17 body incl. the Elite check as its early return; `main()`
  keeps `continue` + tail inits), `recommend_plan` + frozen `PlanRecommendation` (the
  B47 core; fields `months_until_recommendations`/`median_visitors`/`cost_same`/
  `costs_median`/`costs_best`/`cost_table_rows`/`current_plan`/`recommended_plan`/both
  indexes/`savings`/`estimate_start_date`/`estimate_end_date`/`savings_entry` — `main()`
  unpacks and appends `savings_entry` to `site_savings`), and `stuff_plans_contract`.
  **D7 shipped:** the recommendation flow runs before the `--only-warn` gate, so
  warning-only runs emit `its-recommends-plan` csv rows (the B42 TODO retired).
  **D-i6-2 discharged:** `psh/traffic.py` now has a module-level
  `from psh.plans import overage_blocks`; the call-time bridge and its docstring note
  are gone.

- **CRITICAL found by the whole-branch review, fixed in `15fb36d` (design
  human-approved).** SPEC D-i7-6 originally argued the reorder safe on the claim that
  nothing writes `pantheon_overage_protection` in the per-site flow — **false**:
  `build_traffic_table_rows` (B46) persists+commits that window's OP rows (BLOCKMAP's
  B46 row said "DB read + commit"; corrected this commit to say read/WRITE). The initial
  D7 reorder therefore put recommend_plan's op-window read before the write: a
  first-of-month full report rendered different costs than a re-run (empirically:
  `$2,005.00` then `$1,925.00`; baseline `$1,925.00` both). Fix: `main()` hoists
  `first_plan_day`/`last_plan_day`/`site_plan_start` and the whole B46 block above
  `recommend_plan` on both paths, restoring write-commit-then-read; full-report output
  back to baseline-identical and deterministic. Consequences, both deliberate:
  `--only-warn` now also runs the table build and persists OP rows (it already wrote
  traffic rows), making its recommendation values equal the full report's — which moved
  the only-warn e2e savings pin `2755.00`→`4995.00` (re-derived from a **baseline**
  full-report run at the same seed: `$4,995.00`/`Performance Large`; the 2755.00 value
  was an artifact of the OP-less simulation branch, so the new pin is stronger, not
  weakened). New instrument (PD#14):
  `test_recommendation_is_deterministic_across_reruns` renders twice and pins the
  OP-affected `$1,925.00` cell — shown red on the broken ordering before the fix.

- **Deviations from CAMPAIGN.md:** none of architecture; SPEC-level notes: D-i7-1
  (bodies move, B9 reads/loop control/tail inits stay — the I6 D-i6-1 reading of the
  §11-vs-§3.3 tension), `site_name`→`site["name"]` in two moved error prints
  (identical value, I6 precedent), and the SPEC's own two corrected spots (D-i7-1
  prose vs the shipped D-i7-3 seam; D-i7-6's false no-writes claim + stale diagram,
  both rewritten to the shipped design).

- **Sanctioned csv change (§8 amendment, applied in `1d32b9f`):** `its-recommends-plan`'s
  savings field is now `{savings:.2f}` (comma-free, fixed 5-column row; HTML/text bodies
  keep `{savings:,.2f}`). §8's row now names I7 alongside I1/I12. LEDGER I1 Obs. 5
  discharged; the `Notice`-class adoption route for this notice (LEDGER I3 candidates)
  is NOT taken — extra csv fields remain, dict form stays until the §6 csv-field
  amendment (candidates now I10/I12).

- **D-i7-4 (LEDGER I1 Obs. 3 discharged):** no owner-facing downgrade notice (new
  report content is a §1 non-goal → README TODO added); the non-Basic-downgrade
  `site_savings` omission IS fixed (stdout-only surface): every surviving downgrade
  recommendation now produces a savings entry, shown red-first at the seam.

- **Contract/config/sc additions:** `CONTRACT["site_pre_render"]` gains
  `current_plan`, `recommended_plan`, `plan_costs` (`{"same"/"median"/"best": {plan:
  float}}`, `{}` when ≤4 in-window months), `savings` — stuffed by `main()` from the
  `PlanRecommendation` just before the phase fires; still no consumer (the seam is now
  key-bearing). CLAUDE.md table row updated + pinned by `test_contract_registry.py`.
  No config keys; no new `sc` façade names.

- **Ratchet (§13):** `psh/plans.py` born gated (broad ruff + pyright standard, 0
  findings after dispositions). Measured dispositions: `SIM118` (`.keys()` iteration →
  `.items()`-free `in`-form rewrite), `PLR1730` (`if`-clamp → `max()`), 2× `PLR2004`
  noqa (magic thresholds, moved verbatim), `PLR0913`+`C901`/`PLR0912` noqa on
  `plan_costs`/`recommend_plan` (pinned signature / verbatim move), 2×
  `min(d, key=d.get)` → `key=lambda plan: d[plan]` (pyright overload; provably
  identical selection + tie-break), `costs_best = {}` prologue init (NameError guard on
  the ≤4-month return — mirrors the sibling inits), and the three SPEC-mandated
  annotations. SPEC §5's predicted `PLR0915`/`FBT001` did NOT fire (recorded, no noqa
  added). Nothing removed from `ruff-broad.toml` `extend-exclude` (fresh gated file,
  I2–I6 precedent; `psh/_legacy.py` stays grandfathered).

- **Discovered tasks (dispositions):**
  - **BLOCKMAP B46 mislabel** ("DB read + commit" for a unit that WRITES OP rows) —
    the root of the Critical above; **fixed this commit** in BLOCKMAP.md (correction
    note on the B46 row), so no later increment re-derives the false premise.
  - **Dead tail inits in `psh/_legacy.py`** (post-rec-unpack): `site_recommended_plan`
    and both index inits are now always overwritten before use on every path that
    reaches the template — dead stores. **`site_current_plan` is NOT dead** (the
    empty-`plan_on_day` guard and the annual-billing blocks read it). Left in place
    (plan-mandated verbatim preservation); → **I13** deletes the three dead lines with
    `main()`'s final form — and only those three.
  - `import copy` orphaned in `_legacy.py` by the B47 move → removed (the I3
    only-what-this-change-orphans rule; `copy` now imported by `psh/plans.py`).
- **Open questions for I8:** proceed per CAMPAIGN.md §11 row I8 (`check/pantheon/` +
  `[Check.pantheon]` config section — the first `[Check.*]` section, §5 shape; `envs`
  contract key at `site_pre`; B19/B21/B38/B41) **plus** LEDGER I1's carried item for
  I8: the `php_version < "8.2"` string comparison and the KeyError when the key is
  absent (Obs. 2) — B41 moves into `check/pantheon/` this increment, so fix it there
  test-first. Note the php-eol builder (`build_php_eol_notice`) still lives in
  `psh/_legacy.py` (I1 extraction) and travels to `check/pantheon/` at I8.

## I8 — check/pantheon (2026-07-21, commits dd9aac2/3ea3491/ab3c97b + closing docs commit)

Spec/plan: `development/2026-07-21-mod-I8-check-pantheon/` (`SPEC.md` §9 carries the
pasted acceptance; task reports + reviews under `.superpowers/sdd/`, incl. the RED
evidence for the three named fixes in `task-3-report.md`). Three per-task code commits
(`dd9aac2` Task 1 — `envs` contract key; `3ea3491` Task 2 — package + frozen/live-env;
`ab3c97b` Task 3 — updates/php-eol + the named fixes), each green, plus this closing
docs commit (CLAUDE.md / memory / this ledger entry / the dev folder). Full suite at
close **including the live tier** (Terminus credentials present — the 2 live-marked
tests ran and passed) = **846 passed / 1 skipped** (the skip is `test_db_credentials.py`'s
`importorskip("MySQLdb")` on a sqlite-only install), all three gates, 48 snapshots; four
goldens byte-identical across the increment (`git diff 6ce3416 --
tests/e2e/__snapshots__/` empty). This is the campaign's **first Tier-2 check package**
and the **first `[Check.*]` config section**.

- **Moved:** exactly the §11-row-I8 move set (B19, B21's notice half, B38, B41) out of
  `main()` into the new `check/pantheon/` package (one module per check, D-i8-1), plus
  the I1-extracted `build_php_eol_notice`:
  - **B19** (frozen console print + `frozen` notice) → `check/pantheon/frozen.py`, hook
    `check.pantheon.frozen.check_frozen_site` at `site_pre` (consumes `[]`).
  - **B21's initialized-False branch** (console ERROR + `no-live-env-but-paid-plan`
    notice) → `check/pantheon/live_env.py`, hook `check.pantheon.live_env.check_live_env`
    at `site_pre` (consumes `['envs']`). The `env:list` fetch, the fatal/undecodable
    `continue`, and the missing-live `sys.exit` guards stay in `main()` (SPEC §3.3 /
    D-i8-2 — core fetches `envs` because core gates on it, then stuffs it).
  - **B38** (banner print + `upstream:updates:list` fetch + `updates-info`/`-warning`/
    `-alert` notices + non-list error print) → `check/pantheon/updates.py`, hook
    `check.pantheon.updates.check_upstream_updates` at `site_post_gather` (consumes `[]`;
    fetches its own data via `sc.terminus` — the CAMPAIGN §3.2 check-specific-fetch case;
    one call edit `terminus(...)` → `sc.terminus(...)`).
  - **B41 + `build_php_eol_notice`** → `check/pantheon/php_eol.py` (pure module, imports
    only `sc`), hook `check.pantheon.php_eol.check_php_eol` at `site_post_gather`
    (consumes `['envs']`). The builder left `psh/_legacy.py` with **no re-import** (unlike
    I2–I7's moves — nothing in `_legacy.py` calls it after the move; the hook does), and
    `tests/unit/test_php_eol_notice.py` repointed to the new standalone-loaded home.
  Column-0 `f"""` notice-literal interiors (incl. the no-live-env literal's 12-space
  interior indentation) moved byte-for-byte (Invariant 8; extracted-block diff pasted
  empty in the task reports, I2 precedent). Registration order (D-i8-3): frozen, live_env
  at `site_pre`; updates, php_eol at `site_post_gather` — preserves the within-package
  notice order.

- **Named fixes shipped (all red-first; RED evidence in `.superpowers/sdd/task-3-report.md`):**
  1. **D-i8-4.1** (LEDGER I1 Obs. 2 discharge, half 1): `php_version < "8.2"`
     lexicographic string compare → int-tuple compare (`(major, minor…) < (8, 2)`), so
     `"8.10"` no longer draws a false September-30 alert (`"8.10" < "8.2"` was `True`).
     Bonus inside scope: `""` no longer false-alerts (parse failure → `None`). RED:
     `build_php_eol_notice("s", "8.10")` returned an alert dict on the old code, `None`
     on the new.
  2. **D-i8-4.2** (Obs. 2 discharge, half 2): the hook reads
     `envs["live"].get("php_version")` (was an unguarded `["php_version"]` that would
     KeyError and abort the **whole run** — the guards check `live`/`initialized` but
     never `php_version`); the builder returns `None` for `None`/unparseable input (one
     mechanism covers both). RED: `build_php_eol_notice("s", None)` raised `TypeError`
     (`None < "8.2"`) on the old code; the hook-seam test shows a `php_version`-less
     `envs` adds no notice and raises nothing. **LEDGER I1 Obs. 2 is now fully
     discharged.**
  3. **D-i8-5** (discovered this increment, §12 fix-now disposition): the updates-alert
     branch's singular `short` lacked its `f`-prefix and rendered the literal
     `"{oldest_update_days} days old"`; the `f` was added, pinned by
     `test_single_old_update_short_is_interpolated` (one 45-day-old update →
     `"needs maintenance: 1 Pantheon update, 45 days old"`). Not a csv value (§8 csv row
     untouched); no golden renders any `updates-*` notice.

- **Contract/config/sc additions:** `CONTRACT["site_pre"] = ("envs",)` +
  `psh.modules.stuff_envs_contract` (a core-produced key beside
  `stuff_traffic_contract`/`stuff_gather_contract` per D-i8-2), called by `main()`
  directly above the `site_pre` invoke; `PHASES`' `site_pre` comment updated; CLAUDE.md
  contract-table row added; pinned by `tests/unit/test_contract_registry.py`. `envs` =
  the `terminus env:list` JSON dict keyed by environment id (fields `id, created, domain,
  connection_mode, locked, initialized, php_version, php_runtime_generation`); `main()`'s
  guards guarantee `envs["live"]` with an `initialized` key before any site phase fires,
  **`php_version` NOT guaranteed present** (the D-i8-4 defect class). `[Check.pantheon]`
  — the **first `[Check.*]` config section** (§5 shape), `enabled` **default TRUE**
  (absent section/key → registered, so relocating a check that ran unconditionally does
  not silently disable it); documented in `sample-pantheon-sitehealth-emails.toml` after
  the last `[Pantheon.*]` table. **No new `sc` façade names** (hooks use the existing
  `sc.console`/`sc.terminus`).

- **Deviations / prediction corrections (all ledger notes, none amend CAMPAIGN.md):**
  1. **D-i8-3 ordering consequence (spec-documented).** At `site_post_gather` three pairs
     flip: today's add order is umich.cloudflare_cms → B38 updates → B39 addons → B41
     php-eol; after the move it is pantheon.updates → pantheon.php_eol →
     umich.cloudflare_cms → B39 addons. So updates/php-eol now precede cloudflare_cms
     notices and php-eol precedes the still-inline B39 add-on notice (php-eol was
     previously added after both; updates previously after cloudflare_cms). For a
     production site where such notices co-occur at equal severity, the rendered
     within-tier order and that site's `-notices.csv` row order shift; row content, keys,
     and shape unchanged (§8's structure bar holds). **Zero golden impact, proven**: no
     moved notice code renders in any golden (fixture `upstream:updates:list` returns
     `[]`, fixture PHP is 8.2, sites are unfrozen with initialized live envs). `site_pre`
     order is preserved exactly (frozen before live_env, both before umich.sitelens). The
     asymmetry vs B39 dissolves at I10 when addons becomes a hook.
  2. **`__init__.py` blank-line collapse.** The Task 2 brief's `__init__.py` skeleton
     showed two blank lines between the import and the guard; ruff-broad `I001` required
     one — collapsed (behavior-identical, the born-gated requirement governs).
  3. **PLAN Step-5 prediction correction (PD#14).** The plan predicted both
     `["8.10", "9.0"]` params would red pre-fix — only `"8.10"` reds; `"9.0" < "8.2"` is
     already `False` lexicographically, so `"9.0"` is a green boundary pin, not a
     regression case.

- **Ratchet (§13):** `check/pantheon/` **born gated** (broad ruff + the D-i8-6 config
  gate; `uvx ruff check --config ruff-broad.toml check/pantheon/` clean, `psh/modules.py`
  clean, pyright gate 0 errors). `ruff-broad.toml`'s wholesale `"check/"` exclude was
  replaced by the **four enumerated grandfathered packages** (`check/cloudflare/`,
  `check/dns/`, `check/pantheon_cdn_change/`, `check/umich/`) so the new package is not
  swept in — the first time the campaign narrowed the check exclusion. Dispositions
  (confirmed against real ruff output, PD#14): **F541 ×3** f-prefix drops (live_env
  `"no live environment"`, php_eol 2× `"Upgrade PHP"` — all behavior-identical, I6
  precedent); **PLR2004 noqa ×2** (the `<=7`/`<=30` age thresholds, verbatim B38 move);
  **T203 noqa ×1** (the `pprint(updates)` operator diagnostic on the non-list error
  path). SPEC §5's predicted-possible `C901`/`PLR0915` on `check_upstream_updates` did
  **NOT** fire (under thresholds; recorded, no noqa added). **Pyright scope UNCHANGED**
  (`psh/` minus `_legacy.py`) — deliberate (D-i8-7): the checks call runtime-assigned
  `sc` attributes (`sc.terminus`/`sc.console`) that pyright cannot see on
  `script_context`, and declaring typed façade stubs was not I8 scope. **I9/I10 inherit
  this decision consciously.** Nothing else deleted from `extend-exclude` (`psh/_legacy.py`
  stays grandfathered).

- **Discovered tasks (dispositions):**
  - **D-i8-5** (updates-alert singular `short` missing `f`-prefix) — discovered during
    scope verification; §12 "fits scope and <~30 min → fix now, note in ledger" →
    **fixed here** (Task 3; see Named fixes above).
  - **Test hardening** (Task 3 review minor): `test_disabled_registers_nothing_and_says_so`
    now also asserts `not reset_sc.hooks.get("site_post_gather")` (was asserting only
    `site_pre`) → **fixed here** (this closing task).
  - Mid-file imports in the two `check/pantheon/` integration test files
    (`test_check_pantheon_init.py`, `test_check_pantheon.py`) — grandfathered test style
    (the `tests/` tree stays excluded from the broad ruff set) → **left** (Task 3 review
    adjudicated).
  - No other discovered tasks — the task reports found no further gaps beyond the ruff
    dispositions and the prediction corrections recorded above.

- **Open questions for I9:** proceed per CAMPAIGN.md §11 row I9 (`psh/gather.py` WP half;
  `check/wordpress/`; U-M WP checks → `check/umich/`; `add_on_updates` + smell contract
  keys). **Note for I9's spec author:** `check.pantheon`'s two `site_post_gather` hooks
  now run before `check.umich`'s and before any new `check/wordpress/` hooks whose
  package name sorts after `"pantheon"` — new packages' notice-order consequences must be
  analyzed the D-i8-3 way. The **pyright-scope decision (D-i8-7) is inherited**. LEDGER
  I3's `Notice`-adoption candidates for extra-csv notices remain I10/I12 (the `updates-*`
  csv rows carry extra fields, which `Notice` cannot hold without the reserved §6
  amendment).

## I9 — wordpress (2026-07-21, commits 5a6654d/309ebcf+0873c3a/717e21f/fb92e9d/d5c4bf8 + closing docs commit)

Spec/plan: `development/2026-07-21-mod-I9-wordpress/` (`SPEC.md` §9 carries the pasted
acceptance; task reports + reviews under `.superpowers/sdd/`). Per-task code commits,
each green: `5a6654d` (Task 1 — the four `site_post_gather` contract keys + B48 repoint),
`309ebcf` + review fix `0873c3a` (Task 2 — `check/wordpress/` package + `sc.wp_eval`/
`sc.wp_error`), `717e21f` (Task 3 — U-M WP checks → `check/umich/` + ratchet narrowing),
`fb92e9d` (Task 4 — `psh/gather.py`), `d5c4bf8` (the carried I8 rich-pprint fix, below),
plus this closing docs commit (CLAUDE.md / CAMPAIGN.md §8 amendment / memory / this
entry / the dev folder) and `ea55efc` (whole-branch-review fix, after the closing
commit: two comment-level corrections — the stale `WordPressGather.wordpress_version`
field comment in `psh/gather.py`, and `test_house_rules.py`'s façade quote repointed at
the updated CLAUDE.md sentence; verdict then unqualified PASS/PASS). Full suite at close **including the live tier** (Terminus
credentials present — `ls ~/.terminus/cache/tokens/` shows one token; the 2 live-marked
tests ran) = **910 passed / 1 skipped** (the skip is `test_db_credentials.py`'s
`importorskip("MySQLdb")` on a sqlite-only install), all three gates (`All checks
passed!` ×2, pyright `0 errors`), 72 snapshots; four goldens
byte-identical across the increment (`git diff ecb4420 -- tests/e2e/__snapshots__/`
empty — the new syrupy files live under `tests/integration/__snapshots__/`).

- **Moved:** exactly the §11-row-I9 move set (B32–B34; baseline `check_wordpress_plugin`
  lines 672–739), split three ways per D-i9-1:
  - **Gather core → `psh/gather.py`** (Tier 1, born gated): `check_wordpress_plugin`
    (signature unchanged; papc/sessions/cloudflare_cms call it via
    `sc.check_wordpress_plugin`), `wordpress_network_url` (B32), `gather_wordpress`
    (B34 gather core: version/plugin-list/theme-list fetches, add-on collection
    plugins-then-themes, must-use print) returning the new `WordPressGather` NamedTuple
    (`wordpress_version`/`plugins`/`add_on_updates`/`wp_smell`/`results_entry`) —
    **a §6-unlisted supporting return type, the I7 `PlanRecommendation` precedent
    (ledger note, no amendment)**. Re-imported by `_legacy.py` (I2–I7 pattern);
    `main()` threads the fields per D-i9-2, preserving the last-wins smell overwrite
    (an empty returned smell never clears an earlier one). The failed-gather `wp_error`
    notices moved with the fetches (they describe the gather, not a check).
    `escape_url` is reached via a call-time bridge import from `psh._legacy`
    (`# noqa: PLC0415`, D-i6-2 precedent) — **I12 obligation: replace with a
    module-level `from psh.render import escape_url` when I12 moves it there.**
  - **Generic checks → `check/wordpress/`** (Tier 2, born gated): `papc.py`,
    `sessions.py`, `ocp.py`, `favicon.py`, four `site_post_gather` hooks registered
    PAPC → sessions → OCP → favicon (D-i9-5) under `[Check.wordpress].enabled`
    (**default true**, D-i8-6 shape; documented in the sample toml). `ocp`/`favicon`
    probe via `sc.wp_eval`, build failure notices via `sc.wp_error`, and rebind
    `site_context["wp_smell"]` on non-fatal stderr (D-i9-3). The favicon notice body's
    un-gated its.umich.edu links moved verbatim (Invariant 8; recorded in CLAUDE.md's
    still-hardcoded-U-M list, the I8 check/pantheon precedent).
  - **U-M checks → `check/umich/`**: `oidc_login.py` + `hummingbird.py`, two
    `site_post_gather` hooks registered after `cloudflare_cms` under the existing
    `[UMich].enabled` gate.
  Notice-dict literals moved byte-verbatim (extracted-block diff evidence in the task
  reports; every difference is a named, sanctioned substitution). All moved notices
  keep the legacy dict form — several carry extra csv fields (`not-installed,{name}`,
  `turned-off,{name}`), so `Notice`-class adoption stays deferred (LEDGER I3 → I10/I12).

- **CAMPAIGN.md §8 AMENDMENT (D-i9-4), applied in this closing commit:** the notice-csv
  *values* row gains "I9 (wp-smell precedence when theme-list and OCP-probe stderr
  co-occur without favicon stderr — see LEDGER I9)". The smell overwrite order changed
  from version → plugins → OCP → themes → favicon (inline) to version → plugins →
  themes (gather) → OCP → favicon (hooks); the final `wp_smell` — embedded in the
  `wp-smell` notice csv — differs ONLY when theme-list and OCP-probe stderr are both
  non-empty and favicon stderr is empty (today themes won; after I9 OCP wins). In
  practice wp-cli stderr is identical across a run's calls, making the divergent case
  value-identical too; exact preservation would need per-source smell slots §4's fixed
  key set does not admit. The new precedence is pinned deliberately by
  `test_ocp_stderr_beats_earlier_theme_smell_when_favicon_clean` (Task 2).

- **D-i9-6 gating change (deliberate, this is the record):** the umich-oidc-login and
  Hummingbird-fork checks previously ran **un-gated** — a non-U-M run with
  `umich-oidc-login` installed got U-M-specific advice. After I9 they run only when
  `[UMich].enabled` (proof: `test_umich_disabled_registers_neither_wp_check`). For a
  non-U-M run the `umich-oidc-login-reinstall`/`unsupported-turned-off`/`unsupported`
  notices and csv rows no longer occur — NOT a §8 csv-value change (rows appear/
  disappear with config, the cachecheck precedent); zero golden impact (goldens run
  umich-disabled and their fixtures fire neither check). Invariant 3 moves in its
  intended direction.

- **D-i9-7 ordering as shipped:** post-I9 `site_post_gather` registration order is
  `pantheon.updates`, `pantheon.php_eol`, `umich.cloudflare_cms`, `umich.oidc_login`,
  `umich.hummingbird` (module name is `hummingbird`, not the SPEC sketch's
  `hummingbird_fork`; hook name `check.umich.hummingbird.check_hummingbird_fork`),
  then `wordpress.papc`, `wordpress.sessions`, `wordpress.ocp`, `wordpress.favicon` —
  no DAG edges among them, so registration order holds. The six moved checks' notices
  are now added during the phase (after `pantheon.*`/`cloudflare_cms` output) and the
  U-M pair precedes the wordpress four (inline order was PAPC, sessions, oidc, OCP,
  hummingbird, favicon). Equal-severity co-occurring notices shift within-tier render
  and `-notices.csv` row order; content/keys/shape unchanged (§8 structure bar holds).
  Zero golden impact, proven (SPEC §6 + empty snapshot diff). Between Tasks 2 and 3 an
  interim state existed (wordpress hooks in-phase, U-M pair still inline); it resolved
  at Task 3 and never shipped outside the increment.

- **Contract/config/sc additions:** `CONTRACT["site_post_gather"]` += `add_on_updates`
  (list of pending add-on-update dicts, plugins then themes in list order; `[]` when
  none/not that framework/gather failed; stuffed as the SAME list object `main()`'s B39
  table still reads) and `wp_smell`/`drush_smell`/`composer_smell` (str, `""` when
  none; **`wp_smell` MAY be rebound in place during the phase** by
  `check.wordpress.ocp`/`check.wordpress.favicon` — the one sanctioned
  mutate-during-phase key; hooks do NOT declare `produces: ['wp_smell']`, which would
  be a duplicate-producer fatal). `stuff_gather_contract` grew the four params; B48's
  `build_smell_notices` call repoints to the `site_context` reads (B39 keeps reading
  the local — same object, asymmetry dissolves at I10). `[Check.wordpress]` (`enabled`,
  default true) added to the sample toml. `sc.wp_eval`/`sc.wp_error` façade lines
  added (D-i9-9; `sc.wp` deliberately NOT added — no relocated check calls `wp()`),
  pinned by `test_documented_sc_facade_names_exist`.

- **Deviations / prediction corrections (PD#14 — real tool output vs. SPEC §5/§7):**
  1. **T203 did NOT fire in `psh/gather.py`** — the diagnostics use `rich.pretty.pprint`
     (what the inline code used; SPEC §3's "stdlib `pprint`" was wrong on that name),
     which T203 (stdlib-only) does not cover; pre-added noqas were RUF100-flagged and
     removed. This exposed an **I8 silent divergence**: `check/pantheon/updates.py` had
     imported stdlib `pprint` where inline B38 used `rich.pretty.pprint`, changing the
     non-list error path's diagnostic rendering — **fixed here** (`d5c4bf8`: rich
     import restored, unused `noqa: T203` dropped, `ruff-broad` clean,
     `test_check_pantheon.py` 14 passed).
  2. `C901` + `PLR0912` fired on `gather_wordpress` (noqa'd, moved verbatim);
     `PLR0915` did NOT (under threshold). Unpredicted: `PLR0913` on
     `check_wordpress_plugin` (noqa — signature unchanged is a requirement), `E713`
     (`not "status" in plugin` — fixed in place, the D-i8 disposition), `PERF401` on
     the theme add-on loop (noqa, verbatim move). `PLC0415` fired as predicted but the
     brief's single-line noqa tripped `I001`; the I6 two-line precedent form was used.
  3. **F541 fired in Task 2** on four placeholder-free single-line notice literals
     (SPEC §5 predicted none) — initially noqa'd citing Invariant 8; review found the
     citation wrong (Invariant 8 governs column-0 triple-quoted literals) and the fix
     (`0873c3a`) dropped the extraneous f-prefixes instead (behavior-identical, I6/I8
     precedent). Task 3's newly-gated files: `I001` fixed, an unused
     `import script_context as sc` in `oidc_login.py` removed (F401 — the moved body
     uses no `sc.*`), `SIM102` noqa'd (collapsing would re-indent a byte-locked dict).
  4. **SPEC §7 expected-value corrections:** through the gateway seam `wp_eval` always
     returns a str, so a fatal version fetch yields `""` (its stripped stdout), NOT
     `"unknown"` — the `"unknown"` fallback moved verbatim but is unreachable for
     WordPress (Drupal's `"unknown"` on failure is real); and a fatal
     `wordpress_network_url` yields `("", "")`, not `(None, "")` — `main()` then sets
     `site_url = ""`, exactly the old inline behavior. Tests pin reality; CLAUDE.md's
     contract-table row now words this accurately.
  5. **D-i9-10 fixed as specced:** the Hummingbird ATTENTION print now interpolates
     `site['name']`, not the whole site dict (stdout MAY improve freely, §8); pinned
     via `recording_console`.
  6. `semver` orphaned from `_legacy.py` and removed (Task 3, grep-verified);
     `html`/`pprint` retained (other users). `wp` also stays imported in `_legacy.py` —
     NOT orphaned (`tests/integration/test_wrappers.py` calls `psh.wp(...)`); it is now
     a pure re-export there.

- **Ratchet (§13):** `psh/gather.py` + `check/wordpress/` **born gated** (broad ruff +,
  for `psh/gather.py`, the pyright gate — all clean). `ruff-broad.toml`'s
  `"check/umich/"` exclude narrowed one level deeper to `"check/umich/sitelens.py"` +
  `"check/umich/cloudflare_cms.py"` (the I8 enumeration precedent), so the package
  `__init__.py` and the two new modules are gated; the two legacy siblings stay
  grandfathered until I14. **Pyright scope UNCHANGED** (`psh/` minus `_legacy.py`) —
  D-i8-7 inherited (D-i9-8): the checks call runtime-assigned `sc` attributes (now
  including `sc.wp_eval`/`sc.wp_error`) pyright cannot see on `script_context`.
  **I10 inherits both decisions.**

- **Discovered tasks (dispositions):**
  - The I8 stdlib-vs-rich `pprint` divergence in `check/pantheon/updates.py`
    (Task 4 review finding) → **fixed here** (`d5c4bf8`, §12 fix-now disposition; see
    Deviations 1).
  - `stuff_gather_contract`'s docstring still says the `*_version` values are
    `"unknown"` on a failed fetch — accurate for Drupal, not for WordPress (the `""`
    reality above); a docs-only closing task cannot edit `psh/modules.py` → **ledgered
    to I10**, which extends that stuffer's Drupal half anyway. CLAUDE.md's table (the
    authoritative prose rendering) is already corrected.
  - `semver.compare` emits a `PendingDeprecationWarning` (semver 3 deprecates the free
    function for `Version.compare`) — surfaced by the moved oidc check, pre-existing
    behavior moved verbatim → **post-campaign cleanup** (noted, not a campaign item).
  - No others — the task reports found no further gaps beyond the ruff dispositions
    and prediction corrections above.

- **Open questions for I10:** the Drupal gather half mirrors this shape
  (`gather_drupal` → `WordPressGather`-style NamedTuple; `check_drupal_module` moves to
  `psh/gather.py` beside its sibling). **B39 (add-on table) and B48 (smell notice
  bodies) move at I10** with their `site_context` reads already in place — B48 was
  repointed at I9; B39 still reads the `add_on_updates` local, which is the same object
  the stuffer publishes, so the repoint is free when it becomes a hook. The
  `escape_url` bridge in `psh/gather.py` is an **I12 obligation** (module-level
  `psh.render` import when it moves). The **pyright-scope decision (D-i8-7/D-i9-8) is
  inherited**. `Notice`-adoption for extra-csv notices remains I10/I12. The
  `stuff_gather_contract` docstring correction above is I10's. drush/composer smells:
  `drush_smell`/`composer_smell` are published but still fed only by `main()`'s inline
  Drupal/composer code — I10 decides whether its relocated checks get the same
  sanctioned-rebind treatment as `wp_smell` (analyze the D-i9-4 way if the overwrite
  order changes).

## I10 — drupal + addon_updates (2026-07-22, commits 8034780/eedd60c/03c81c0/edafe0d + closing docs commit)

Spec/plan: `development/2026-07-22-mod-I10-drupal/` (`SPEC.md` §9 carries the pasted
acceptance; task reports + reviews under `.superpowers/sdd/`). Four per-task code commits,
each green: `8034780` (Task 1 — Drupal UA check → `check/umich/` + drush façade names),
`eedd60c` (Task 2 — `check/drupal/` package + `main()` post-dns rewiring + hook-DAG test
repair), `03c81c0` (Task 3 — `check/addon_updates/` package), `edafe0d` (Task 4 —
`psh/gather.py` Drupal half + smell builder + the two named fixes), plus this closing docs
commit (CLAUDE.md / CAMPAIGN.md amendments / README TODO / this entry / the dev
folder; **auto-memory was NOT updated in this commit** — the whole-branch review caught the
original wording claiming it was (its one Important finding, PD#13/PD#14): the controller
had reserved memory for itself and skipped it. Memory was then updated post-final-review
(`modularization-campaign` + `gateway-extraction` notes, incl. the two-binding
`psh.gather.run_terminus` seam trap) and this sentence corrected in the same follow-up
commit). Full suite at close **including the live tier** (Terminus credentials present —
`ls ~/.terminus/cache/tokens/` shows one token, network to Pantheon reachable, the 2
live-marked tests ran and passed) = **991 passed / 1 skipped** (the skip is
`test_db_credentials.py`'s `importorskip("MySQLdb")` on a sqlite-only install), all three
gates (`All checks passed!` ×2, pyright `0 errors`), 107 snapshots; four goldens
byte-identical across the increment (`git diff eff1b40 -- tests/e2e/__snapshots__/` empty).

- **Moved:** exactly the §11-row-I10 move set (B30, B35, B39, B48 *builder*; baseline
  740–791 = `check_drupal_module`), split by block:
  - **B30 multisite probe → `check/drupal/multisite.py`**, hook
    `check.drupal.multisite.check_multisite` at `site_post_dns`, consumes
    `['custom_domains', 'primary_domain']`, **produces `['drupal_multisite',
    'drupal_multisite_smell']`** — the **campaign's first hook-produced (DAG-declared,
    not registry-owned) contract keys** (D-i10-3; amendment 2). `main()` reads them with
    `.get()` right after `invoke_hooks("site_post_dns")` to seed `drush_smell` (if the
    probe smell is non-empty) and to gate the still-core `no-primary-domain` notice.
  - **B35 checks → `check/drupal/` + `check/umich/`**: `papc.py` (PAPC module) and
    `d7_eol.py` (`drupal7-eol` notice + tag1_d7es check, one hook) at `site_post_gather`,
    registered multisite → papc → d7_eol (D-i10-5); the Drupal UA check →
    `check/umich/drupal_ua.py` at `site_post_gather`, after `hummingbird` (D-i10-6).
  - **B35 gather core → `psh/gather.gather_drupal`** returning the new **`DrupalGather`**
    NamedTuple (`drupal_version`/`modules`/`add_on_updates`/`drush_smell`/`composer_smell`/
    `results_entry`; a §6-unlisted supporting return type — the I7 `PlanRecommendation` /
    I9 `WordPressGather` precedent, ledger note not amendment), plus `check_drupal_module`
    beside its WP sibling. `main()`'s Drupal branch collapses to the D-i10-2 threading
    (last-wins smell overwrite preserved; the D7-vs-D8+ branch stays *inside*
    `gather_drupal` — it selects gather strategies, not checks).
  - **B39 add-on table → `check/addon_updates/table.py`**, hook
    `check.addon_updates.table.check_add_on_updates` at `site_post_gather`, consumes
    `['add_on_updates']`, reading the SAME list object the stuffer publishes; the stray
    `rt-plan""` doubled quote moved byte-verbatim (golden-rendered, do NOT fix).
  - **B48 smell-notice *builder* → `psh/gather.build_smell_notices`; its emission stays
    in `main()`** (amendment 1). The `no_primary_domain_notice(site, custom_domains,
    primary_domain, is_multisite) -> dict | None` pure helper was extracted into
    `psh/_legacy.py` (the Spine's named-extraction rule — no seam above the golden; its
    final home is I13's call, ledger-noted like the I1 builders).
  Column-0 `f"""` notice-literal interiors moved byte-for-byte (Invariant 8;
  extracted-block diffs pasted in the four task reports — every difference a named,
  sanctioned substitution class).

- **Two CAMPAIGN.md amendments (user-approved 2026-07-22, applied to the document this
  closing commit — the preamble's edit-the-document-AND-ledger rule):**
  1. **B48's emission stays in `main()`; only its builder moves** (D-i10-1). Edited §3.1's
     `psh/gather.py` row (+`build_smell_notices`), §3.2's `check/addon_updates/` row (B39
     only + a B48-not-a-hook paragraph), §3.3's stays-in-`main()` list (+the B48 emission
     call), and §11 row I10. Reason: a `site_post_gather` smells hook cannot be ordered
     after the `wp_smell`/`drush_smell` in-place mutators — a `produces: ['wp_smell']`
     declaration is a §4-condition-2 fatal against the core registry (D-i9-3), and
     alphabetical registration puts `check/addon_updates` FIRST in the phase — and
     relocation would also add smell rows to `--only-warn` csv output (B48 sits after that
     gate today), a §8 surface change. The `mutates` hook declaration that would dissolve
     this class is **post-campaign work → README TODO** (user decision).
  2. **§4 gains the hook-produced-key definition** (one paragraph). Hooks MAY produce keys
     of their own — validated by conditions 1–4 — but such keys are DAG-declared, present
     only when the producing hook ran, `.get()`-read, and NOT part of the guaranteed
     per-phase contract (whose new-keys list stays exhaustive for registry-owned keys).
     Reason (D-i10-3): the multisite probe ships the campaign's first such keys; without
     the edit CAMPAIGN.md's glossary ("guaranteed keys") and §4's exhaustive list would
     silently contradict shipped code.

- **D-i10-6 gating change (deliberate, the D-i9-6 precedent — this is the record):** the
  Drupal UA check previously ran **un-gated** — a non-U-M Drupal 8+ site was told to
  configure a `…; UMich; …` user agent, factually wrong off-campus. After I10 it runs only
  when `[UMich].enabled` (proof: `test_check_umich_drupal_ua.py`'s umich-disabled
  registers-nothing case). For a non-U-M run the `drupal-ua`/`drupal-ua-check` notices and
  csv rows no longer occur — NOT a §8 csv-*value* change (rows appear/disappear with
  config, the cachecheck precedent); Invariant 3 moves in its intended direction. **Golden
  consequence:** the Drupal golden (`its-wws-test2`, umich-disabled) runs the un-gated UA
  check *today* with a compliant fixture UA → zero notice; post-I10 `drupal_ua` is not
  registered, so that `drush php:script` call + its `=== Checking for Drupal user agent`
  banner disappear from the run — stdout-only (§8-free), the `.eml` unaffected, the goldens
  byte-identical (verified empty diff). The now-unused fixture
  `tests/fixtures/terminus-drupal/c17e10215ba09beb.json` is **kept, not deleted**
  (Invariant 10 posture; the replay shim is argv-keyed so an unused fixture is harmless).

- **D-i10-4 (smell precedence — the D-i9-4 analysis; NO §8 amendment):** `drush_smell`
  joins `wp_smell` as a **sanctioned mutate-during-phase key** (mutator:
  `check.umich.drupal_ua`, which does NOT declare `produces: ['drush_smell']` — the D-i9-3
  rule); B48's emission already reads `site_context["drush_smell"]` (I9 repoint), so the
  rebind reaches it. Post-I10 write order (probe → core-status → pm:list → UA) is
  **identical in every co-occurrence** to today's — no pair of writers swapped relative
  order, unlike I9's theme/OCP flip — so no notice-csv value can diverge and §8 needs no
  amendment. Both `psh/modules.py` "one sanctioned mutate-during-phase key" occurrences and
  CLAUDE.md's contract row now say two (`wp_smell`, `drush_smell`).

- **Named fixes shipped (both red-first; RED evidence in the task reports):**
  1. **D-i10-7** (updatestatus `type in u` builtin bug): `"type": u["type"] if type in u
     else "package"` tested whether the **`type` builtin** is a dict key — always False, so
     every D7 pm:updatestatus row rendered `package`. Fixed in the moved `gather_drupal` to
     `u.get("type", "package")` (the `"type" in u` fix + ruff's immediate SIM401
     simplification; behavior-identical). Notice-body value only (csv carries
     `updates-addons,{num}`); zero golden impact (the Drupal golden's rows come from the
     D8+ composer-audit path). RED: `task-4-report.md` §3.3 (`'package' == 'module'`
     asserted on the moved-but-unfixed function, both runs quoted in Task 4's single
     commit).
  2. **D-i10-8** (composer-smell baked-in indentation — **LEDGER I1 Obs. 4 discharged**):
     `build_smell_notices`' composer `message`/`text` literals carried 8 spaces of
     accidental leading indentation on every interior line; de-indented to column 0 as the
     builder moved, matching the wp/drush siblings. NOT an Invariant-8 violation (that locks
     *deliberate* column-0 literals; this is the ledgered bug), NOT a csv change, zero
     golden impact (no golden renders any smell). RED: `task-4-report.md` §3.1
     (`assert not composer["message"].startswith("\n        ")` failing on the pre-move
     builder).

- **Contract/config/sc additions:** **no new core-stuffed CONTRACT keys** (I10 adds only
  hook-produced keys, above — the multisite probe's, which live in the hook's `produces`,
  not the registry). `[Check.drupal]` and `[Check.addon_updates]` config sections, `enabled`
  **default TRUE** (D-i8-6 shape — absent section/key still registers; documented in
  `sample-pantheon-sitehealth-emails.toml` after `[Check.wordpress]`). **Documented disable
  consequences:** `[Check.drupal].enabled = false` → the multisite probe never runs, so a
  Drupal *multisite* with >1 custom domains and no primary domain now gets the
  info-severity `no-primary-domain` notice (the operator opted out of the probe that
  suppressed it — D-i10-3, ledgered not guarded); `[Check.addon_updates].enabled = false`
  → the `updates-addons` notice leaves reports AND `--only-warn` output. `sc.drush_php_script`
  / `sc.drush_error` façade lines added (D-i10-10; `sc.drush` deliberately NOT — no relocated
  check calls `drush()`, the I9 `sc.wp` reasoning), pinned by
  `test_documented_sc_facade_names_exist`. `stuff_gather_contract`'s docstring corrected
  (D-i10-11, the LEDGER I9 obligation — WP `*_version` is `""` on failure, Drupal
  `"unknown"`; doc-only, no `CONTRACT` change).

- **Deviations / discovered tasks (dispositions):**
  - **`test_hook_dag.py` `ALL_PACKAGES` drift** (spec-review finding, PD#14): the list was
    last touched at I4 and silently missed `check/pantheon` (I8) and `check/wordpress`
    (I9), so CLAUDE.md's "loads every real check/plugin package" had been **false for two
    increments** — I8/I9 shipped the drift silently. → **fixed at Task 2** (`eedd60c`):
    added `pantheon`, `wordpress`, `drupal`, `addon_updates`; the per-phase `got == names`
    assertion still holds (DAG stays edgeless — nothing consumes the probe keys). CLAUDE.md's
    sentence restored + annotated with the false-window note.
  - **The two-binding `run_terminus` seam trap** (Task 4 discovery, PD#14): `psh/gather.py`
    binds `run_terminus` in its OWN namespace (`from psh.gateway import run_terminus`) for
    `gather_drupal`'s composer dry-run direct call; the `gateway` fixture repoints only
    `psh.gateway.run_terminus`, so a gather test patching just it makes **real** Terminus
    subprocess calls (a mock that looks installed but isn't — the first RED run of
    `test_gather_drupal.py` did exactly this). → **fixed in-test** (patch BOTH
    `psh.gateway.run_terminus` and `psh.gather.run_terminus`, documented in the test's module
    docstring) **+ a durable CLAUDE.md § Two mock seams note** (this closing commit).
  - **Task 4's §8.3 sanctioned-class additions** (opus review, real tool output over the
    prediction): **E713 ×2** in `check_drupal_module` (`not X in Y` → `X not in Y`, surfaced
    only once the code left the grandfathered `_legacy.py`), the D-i10-7 fix expressed as
    `u.get("type", "package")` (**SIM401**, behavior-identical to the conditional form), and
    an `advisory = None` init + scoped `# pyright: ignore[reportOptionalSubscript]` in the
    composer-audit loop (an empty `advisory_list` is unreachable in practice, but
    `psh/gather.py` is pyright-gated where `_legacy.py` was not; `None["link"]` would still
    raise loudly — PD#1-preserving). All behavior-preserving; the controller **amended SPEC
    §8.3 in place** to list them. Also `import html` was genuinely orphaned in `_legacy.py`
    by the move and removed (Karpathy #3); `drush`/`run_terminus`/`drush_php_script`/
    `drush_error` are NOT orphaned (kept for the `psh.*` re-export contract the wrapper tests
    rely on — the fix-the-class lesson: zero internal call sites ≠ orphan when other files
    import through the namespace).
  - **The two probe-smell seeding lines in `main()` rest on inspection** (D-i10-3): they
    have no seam above the golden and are not golden-exercised (every golden site has ≤1
    custom domain, so the probe never runs); accepted and ledger-noted (the I4
    `HookDagError`-glue precedent). The halves they join are pinned separately
    (`test_check_drupal.py`'s produced-key pins; D-i10-4's smell pins).
  - **D-i10-12 subject-line consequence** (informational, ledgered to make it deliberate —
    I9 shipped the same class without comment): the subject takes the FIRST sorted notice's
    `short`, so for a production site with **no alert** whose first *warning* changes under
    the within-tier notice-insertion shifts (e.g. `updates-addons` now sorts first in
    `site_post_gather` where it used to run last), the email subject can change. Content of
    every notice unchanged; **zero golden impact** (each golden's leading notice is unmoved —
    `updates-addons` is the only warning-tier notice in all four goldens, so its within-tier
    position is render-identical wherever inserted; the `Action Required` subjects come from
    the `no-domains` alert / the cdn golden's from `updates-addons` itself).
  - **D-i10-13 `Notice`-class adoption stays deferred to I12/I14** (PD#9, re-ledgered at
    close): every notice I10 touched carries extra csv fields (`not-installed,{name}`,
    `turned-off,{name}`, `updates-addons,{num}`, `drupal-ua,{ua}`, the three smell csvs),
    which `Notice` cannot hold without the reserved §6 field-set amendment; taking it here
    would widen the campaign's second-largest increment for zero behavioral gain. I12's spec
    author inherits it with the annual-bill candidates.
  - No others — the four task reports found no further gaps beyond the ruff/pyright
    dispositions and the items above.

- **Ratchet (§13):** `check/drupal/`, `check/addon_updates/`, `check/umich/drupal_ua.py`
  **born gated** — new files never in `ruff-broad.toml`'s `extend-exclude` (the
  `check/umich/` entry was narrowed to the two legacy siblings at I9); `psh/gather.py`
  already gated. **I10 deletes NOTHING from and adds nothing to the exclude list** (I2–I9
  precedent — the moved/new code lands in fresh gated files; `psh/_legacy.py` stays
  grandfathered). Dispositions confirmed against real tool output (PD#14): on
  `gather_drupal` — `C901`/`PLR0912`/`PLR0915` noqa (verbatim ~200-line body); on
  `check_drupal_module` — `PLR0913` noqa (signature unchanged, the I9
  `check_wordpress_plugin` precedent) + E713 ×2 rewrite; in the composer-audit region —
  `PLW2901`/`PLR2004` noqa, `F541` f-drop on `"fix composer error"`, ERA001 commented
  `drush_smell` line → prose; `F541` f-drop on `"Migrate off Drupal 7 ASAP"` and `E712`
  (`== True` → `is True`) in `multisite.py`; `PLC0415` two-line noqa on the two new
  `escape_url` bridges. **PLC0206 did NOT fire** (predicted-possible; recorded, no rewrite).
  `check/addon_updates/table.py` needed **zero** suppressions. **Pyright scope UNCHANGED**
  (`psh/` minus `_legacy.py`) — D-i8-7/D-i9-8 inherited (D-i10-9): the hooks call
  runtime-assigned `sc` attributes (now including `sc.drush_php_script`/`sc.drush_error`)
  pyright cannot see on `script_context`. **I11 inherits both decisions.**

- **Open questions for I11:** proceed per CAMPAIGN.md §11 row I11 (`psh/charts.py`; B13 cap
  geometry + B44–B45 chart data-prep + matplotlib build → PNG bytes). **Note for I11's spec
  author:** B43's `pprint` diagnostics, the empty-`plan_on_day` synthetic-day guard, and the
  `build_plan_over_time` call + its date/chart prep all stay in `main()` (LEDGER I6 D-i6-4
  and I7 — I6 moved only the aggregation loop, I7 moved the plan-cost bodies but not the
  chart call sites); the chart region consumes `main()` locals that the traffic (I6) and
  plans (I7) moves already shaped, so I11 threads shaped data rather than re-deriving it.
  `Notice`-adoption for extra-csv notices remains I12/I14; the `escape_url` bridges in
  `psh/gather.py` (now two Drupal ones beside the WP one) are all the I12 obligation
  (module-level `from psh.render import escape_url` when it moves).

## I11 — charts (2026-07-23, commits f55e13d/7392d9f + closing docs commit)

Spec/plan: `development/2026-07-23-mod-I11-charts/` (`SPEC.md` §9 carries the pasted
acceptance; the measured scratch assembly is archived there as
`charts-scratch-measured.py`, and the byte-preservation hash records as
`chart-hashes-{before,after}.txt`; task report + review under `.superpowers/sdd/`).
One atomic code commit `f55e13d` (Tasks 1+2 — RED tests + the move; a partial move
cannot be green, the I5/I6 single-commit precedent), one review-fix commit `7392d9f`
(the relocated SVG-chart TODO marker, below), plus this closing docs commit
(CLAUDE.md / memory / this entry / SPEC §9 / the dev folder). Full suite at close
**including the live tier** (`terminus auth:login` succeeded from the cached machine
token; the 2 live-marked tests ran) = **996 passed / 1 skipped** (the skip is
`test_db_credentials.py`'s `importorskip("MySQLdb")` on a sqlite-only install), all
three gates (`All checks passed!` ×2, pyright `0 errors`), 107 snapshots; four goldens
byte-identical across the increment (`git diff 2c79b05 -- tests/e2e/__snapshots__/`
empty).

- **Moved:** exactly the §11-row-I11 move set (B13's cap geometry + B44's
  post-`--only-warn` chart data prep + B45's matplotlib build) → the new
  `psh/charts.py`, one public function `build_chart(...) -> bytes` (PNG), re-imported
  by `psh/_legacy.py` (I2–I10 pattern). `main()`'s chart region collapsed to a single
  call threading the 13 shaped locals (`site`, `site_url`, `visits_by_month`,
  `plan_on_day`, `plan_info`, `plan_over_time`, `dates`, `estimate`,
  `first_plan_day`, `last_plan_day`, `start_date`, `end_date`, `plot_right_date`) —
  the LEDGER-I10 "threads shaped data rather than re-deriving" instruction, honored.
  Eight imports orphaned from `_legacy.py` and removed (`io`, `numpy`, all six
  matplotlib forms) — grep-verified chart-only before deletion. CLAUDE.md delta for
  the closing commit: +20/−5 (no chart logic-prose block existed to delete — the
  chart region had almost no CLAUDE.md prose standing in for it).

- **Deviations from CAMPAIGN.md:** none of architecture; SPEC-level ledger notes:
  1. **D-i11-2 — cap geometry became the function prologue**, recomputed per call
     (was a once-per-run pre-loop precompute). §3.4 bars new module-level mutable
     state in `psh/` and module-level numpy arrays would be exactly that; the
     recompute is pure constant math (~µs vs a ~1 s chart build), values identical.
  2. **D-i11-3 — the chart-only `end_date_yyyy_mm`/`visits` derivations moved
     inside** `build_chart` and their `main()` lines were deleted (orphan-removal;
     value-identity verified — nothing mutates `visits_by_month` after aggregation).
     `dates` IS passed (shared with the pre-gate `estimate_month_visits` call).
     `end_date_yyyy_mm` is read as chart-only formatting, not §3.3's "date window".
  3. **D-i11-4 — `estimates = []` prologue init** (the I7 `costs_best = {}`
     precedent) for pyright; the other conditionally-bound names (`ax_surge`,
     `est_bars`, `bars`) keep scoped ignores instead — a `None` init would trade
     unbound-errors for optional-member errors and a fabricated default would
     silently draw on the wrong axes (PD#1); the loud NameError is the correct
     failure mode.
  4. **D-i11-7 — the `plan_on_day` precondition is documented, not handled** (every
     clamped month midpoint must be a key; production data always satisfies it; a
     violation KeyErrors exactly as pre-move — the D-i6-4 posture).

- **D-i11-6 — behavior evidence (the increment's load-bearing finding): the chart PNG
  is NOT golden-pinned.** The goldens snapshot only the normalized HTML/txt; the chart
  bytes live in the `.eml`, which has no byte golden. So the goldens prove `main()`
  still drives the chart path, but not byte-preservation. Evidence shipped instead:
  (a) before/after sha256 of the chart payload extracted from the offline golden
  pipeline's `.eml` — byte-identical (`2bca16a2…9afcb`), with the task reviewer
  independently reproducing the pre-move hash from a `2c79b05` worktree; records
  committed in the dev folder. (b) Permanent seam tests
  (`tests/integration/test_charts.py`, 5 tests): PNG validity, surge-vs-plain IHDR
  height (proves the GridSpec branch ran), estimate-visibility byte difference,
  determinism across calls, zero leaked figures. **No committed image golden, by
  design**: it would freeze matplotlib's exact rendering and trap post-campaign
  matplotlib/font upgrades against Invariant 1's no-refresh rule.

- **Contract/config/sc additions:** none. No new contract keys, no config keys, no new
  `sc` façade names (the region's only `sc` use is `sc.debug`; grep-verified per SPEC
  §1 non-scope).

- **Ratchet (§13):** `psh/charts.py` born gated (broad ruff + pyright standard, 0
  findings after dispositions; measured on the archived assembly before implementation,
  then re-verified on the shipped file). Ruff dispositions (17 measured):
  ICN001 → `import matplotlib as mpl` (+ the one `rcParams` site); B905 →
  `zip(..., strict=True)` (provably equal-length linspace outputs); quadruple
  `C901`/`PLR0912`/`PLR0913`/`PLR0915` noqa on the def (verbatim ~360-line move,
  pinned 13-arg set — the I6 precedent); SIM118 ×3 / PLC0206 / PLR1730 ×3 / SIM210 /
  C408 / ISC003 rewrites (each behavior-identical, I6/I7 precedents); DTZ007 noqa +
  reason (naive month-label bin edges); I001 canonical import order. Pyright (25
  measured → 0): the D-i11-4 init; `kwargs: dict[str, Any]` on the axes-caps literal
  (dissolves 6 `Axes.plot(**kwargs)` findings honestly); 14 scoped
  `# pyright: ignore` lines in exactly two families — matplotlib-stub
  `reportArgumentType` on runtime-valid dynamic API use, and
  `reportPossiblyUnboundVariable` on surge-conditional locals — both families
  documented once in the module docstring. Nothing added to or removed from
  `ruff-broad.toml` (fresh gated file; `_legacy.py` stays grandfathered). **Pyright
  scope UNCHANGED** (`psh/` minus `_legacy.py`) — D-i8-7/D-i9-8/D-i10-9 inherited;
  **I12 inherits it.**

- **Discovered tasks (dispositions):**
  - **The `# TODO: Create SVG chart` marker was dropped instead of relocated** (task
    review, Minor; PD#9) → **fixed here** (`7392d9f`). Process note for future
    relocations: the implementer's Invariant-8 raw-extract self-diff structurally
    could not catch it — the extract range ended at `plt.close(fig)` and the marker
    lived two lines below, so "every hunk accounted for" had a blind spot at trailing
    relocated markers (PD#14: the instrument was blind exactly where the defect was).
  - SPEC §Observations, recorded for post-campaign, no action: the `estimates`
    def/use guard mismatch (`!= -1` vs `>= 0`, equivalent today); `est_bars`/`bars`
    loop-variable leakage past the axes loop (deliberate; scoped ignores record it);
    the hand-tuned `x + w - 0.00001` vlines epsilon.
  - No others — the task report and review found no further gaps.

- **Open questions for I12:** proceed per CAMPAIGN.md §11 row I12 (`psh/render.py` +
  `psh/mail.py`; B49–B57 minus sort/subject core; annual billing → `check/umich/` at
  `site_pre_render`; B51 deletion if past its Aug-2026 date). Inherited obligations,
  all previously ledgered: the three `escape_url` call-time bridges in `psh/gather.py`
  become a module-level `from psh.render import escape_url` (LEDGER I9/I10); the
  `main()` umich-only annual-bill call sites have NO runtime test — I12's spec author
  MUST cover them when relocating (LEDGER I1); `Notice`-class adoption for extra-csv
  notices remains I12/I14 (needs the reserved §6 field-set amendment); the B55 MIME
  assembly consumes `chart_image` (bytes) and `wordmark_image` — both plain locals,
  no charts coupling beyond the one call. Note for I12's spec author: `psh/charts.py`
  imports nothing from the gateway, so the two-binding seam trap does not extend to
  it; and the `.eml` chart-payload hash procedure in SPEC I11 §6 is reusable as-is if
  I12's MIME move needs the same evidence class.

## I12 — render + mail + annual billing (2026-07-23, commits abd4763/8dbaf75/b972192/f0bab1c/79eee7a + closing docs commit)

Spec/plan: `development/2026-07-23-mod-I12-render-mail/` (`SPEC.md` §9 carries the pasted
acceptance; task reports + reviews under `.superpowers/sdd/`). Five code commits, each
green: `abd4763` (Task 1 — `psh/render.py`: `escape_url` + `render_report`, gather bridge
consolidation, house-rule comment), `8dbaf75` (Task 1 review-fix — the non-vacuous
`!important`-pass assertion via an `@media` block, a PD#14 instance below), `b972192`
(Task 2 — `psh/mail.py`: `smtp_login` + `resolve_recipients` + `assemble_message`,
`test_email_config` seam repoint), `f0bab1c` (Task 3 — `check/umich/annual_billing.py` +
the `sort_notices_and_subject` helper + `sc.contract_year_end` façade), `79eee7a` (Task 3
review-fix — the `_billing_inputs` return annotation, a Minor below), plus this closing
docs commit (CLAUDE.md / memory / this entry / SPEC §9 correction + §5 correction / the
dev folder). Full suite at close **including the live tier** (`ls ~/.terminus/cache/tokens/`
→ `markmont@umich.edu`; `tests/live/test_live_smoke.py ..` ran and passed) = **1021 passed
/ 1 skipped** (the skip is `test_db_credentials.py`'s `importorskip("MySQLdb")` on a
sqlite-only install), all three gates (`All checks passed!` ×2, pyright `0 errors`), 107
snapshots; four goldens byte-identical across the increment (`git diff 786822b --
tests/e2e/__snapshots__/` empty).

- **Moved:** exactly the §11-row-I12 move set (B49, B50/B51 billing, B53, B54,
  B55-assembly, `smtp_login`, `escape_url`), split by destination:
  - **B53 Jinja render + B54 PHP inline → `psh/render.py` `render_report(site_name,
    template_dict) -> tuple[str, str]`** (verbatim bodies; returns the `-inline2` HTML
    actually attached + the rendered text). `escape_url` moved here too — the one-line
    `urllib.parse.quote` wrapper — which **discharges the I9/I10 bridge obligation**: the
    three call-time `from psh._legacy import escape_url` bridges in `psh/gather.py` became
    one module-level `from psh.render import escape_url` (no cycle; render imports only
    stdlib + jinja2 + `sc`).
  - **B49 recipient resolution + `smtp_login` + B55 MIME assembly → `psh/mail.py`**:
    `resolve_recipients(site, site_id) -> tuple[str, str] | None` (`None` on a fatal team
    fetch, D-i6-1 `continue` pattern; the U-M `lsa-disko-project`/`umma-inside-wp` special
    case rides along inside the `umich_enabled()` branch), `smtp_login() -> SMTP_SSL`
    (verbatim, `sys.exit` on missing creds), `assemble_message(...) -> EmailMessage` (the
    B55 build **and** the `build/{site}.eml` write). `main()`'s per-site tail collapses to
    three calls.
  - **B50 billing branch + B51 + both builders → `check/umich/annual_billing.py`**, two
    `site_pre_render` hooks (`check_annual_bill_upcoming`, `check_annual_bill_in_progress`)
    + a shared `_billing_inputs` derivation helper (DRY, deletion-friendly for B51). The
    B50-minus-billing **sort/subject core → the pure `sort_notices_and_subject(site_context,
    report)` helper in `psh/_legacy.py`** (I13 absorbs into final `main()`; the I10
    `no_primary_domain_notice` extraction precedent). Column-0 `f"""` billing-notice
    interiors byte-for-byte (Invariant 8, verified); B49/B53/B54/B55 bodies verbatim
    modulo the disclosed PTH123/UP015 behavior-identical rewrites and the
    noqa/pyright-ignore trailers (extracted-block diffs pasted in the task reports).
  Both `psh/render.py` and `psh/mail.py` re-imported by `psh/_legacy.py` (I2–I11 pattern).

- **Produced-keys mechanism (the increment's one non-move design, I10 `drupal_multisite`
  precedent):** the billing hooks do **NOT** call `add_notice`. Each **produces** a
  DAG-declared contract key — `annual_bill_upcoming` (iff `sc.contract_year_end(end_date)`)
  and `annual_bill_in_progress` (unconditionally when it runs) — read with `.get()` by
  `sort_notices_and_subject` after the phase. These are the increment's **two new
  hook-produced keys, NOT registry-owned** (not in `CONTRACT`, not in
  `test_contract_registry.py`; present only when `[UMich].enabled` registered the hooks and
  the window condition held). This preserves load-bearing history: the billing rows never
  enter `site_context["notices"]`, so they never reach `all_warnings`/`-notices.csv`, and
  the in-progress notice (inserted last so it renders first) still never influences the
  subject. An `add_notice` hook would have broken both — rejected in SPEC §2.2.

- **Deviations from CAMPAIGN.md:** none of architecture; SPEC-level ledger notes (the
  D-i6-1 "bodies move, glue stays" family, verbatim SPEC §2.6):
  1. **D-i12-1 — loop control** stays in `main()`: the `resolve_recipients` `None` →
     `continue`.
  2. **D-i12-2 — the `make_msgid` CID pair and the `template_dict` literal stay in
     `main()`.** Moving the dict build would create a ~25-parameter function strictly worse
     than the dict literal (I11 threaded 13 and was already the campaign's widest); the
     dict is `main()`-local data-shaping, I13 material.
  3. **D-i12-3 — the `report`/`subject` strings and the `sort_notices_and_subject` call
     stay in `main()`** (the helper lives in `_legacy.py` as a module-level def — the I10
     `no_primary_domain_notice` precedent).
  4. **D-i12-4 — the send block (B57) does NOT move.** Its five statements interleave the
     B14 accumulator writes (`emails_sent += 1`, `site_emailed = True`) between
     `send_message()` and `quit()`; hoisting them into `psh/mail.py` would put the counter
     updates after `quit()` returns, reopening the documented Ctrl-C-during-`quit()`
     duplicate-email window (Invariant 4: resume-point next-site-after-email; CLAUDE.md §
     Database, notices-before-send paragraph). The accumulators are §11-row-I13 scope;
     B57's residue moves with them. `psh/mail.py` ships `smtp_login` and `main()` keeps
     calling it.

- **Seam improvement, ledgered (SPEC §3, §8 last row):** the sort/subject region moved
  **below** `invoke_hooks("site_pre_render")` (nothing between its old position and the
  phase read `sorted_notices`/`subject`). So a FUTURE `site_pre_render` hook's `add_notice`
  would now render — the deliberate improvement the I1 MUST flagged. **No in-repo consumer
  exists today** (I7: "still no consumer"), so no observable change now; the billing hooks
  use produced keys, not `add_notice`, precisely to keep the artifacts unchanged. The
  `invoke_hooks("site_pre_render")` "No consumer yet" comment was rewritten (Task 3, the
  Directives-#7 stale-diagram rule).

- **B51 KEPT, not deleted (SPEC §1 NOT-in-scope):** the "annual bill in progress" section's
  marker says "remove at the beginning of August 2026"; today is 2026-07-23, the date has
  **not** passed, so per §11 ("B51 deletion if past its date") B51 relocated intact, TODO
  comment included. **I14 re-evaluates** (its Aug-2026 date will have passed). Consequently
  the **§8-sanctioned I12 csv change goes UNUSED** (SPEC §3 behavior bar: `-notices.csv`
  NONE — the only sanctioned change was B51's deletion, which did not happen).

- **`Notice`-class adoption re-deferred to I14** (PD#9, re-ledgered — the I3/I10/I11
  candidate list): every notice I12 touched (the two billing notices) carries extra csv
  fields, which `psh/notice.py`'s `Notice` cannot hold without the reserved §6 field-set
  amendment. Taking it here would widen the increment for zero behavioral gain. I14
  inherits it with the accumulated candidates.

- **Contract/config/sc additions:** **no new core-stuffed CONTRACT keys** (I12 adds only
  the two hook-produced billing keys, above — DAG-declared, not registry-owned). No new
  config keys (billing stays under existing `[UMich]`). One new façade line
  **`sc.contract_year_end`** (`SC_FACADE_NAMES` += it; needed by the relocated billing
  hooks, which cannot import `psh.plans.contract_year_end` directly, Invariant 9), pinned
  by `test_documented_sc_facade_names_exist` (RED demonstration in the Task 3 report).

- **Ratchet (§13):** `psh/render.py`, `psh/mail.py`, `check/umich/annual_billing.py`
  **born gated** — new files never in `ruff-broad.toml`'s `extend-exclude`. **I12 deletes
  NOTHING from and adds nothing to the exclude list** (I2–I11 precedent — moved/new code
  lands in fresh gated files; `psh/_legacy.py` stays grandfathered until I14). Dispositions
  confirmed against real tool output (PD#14), from the three task reports: on
  `psh/render.py` — S603/S607 noqa + reasons on the `subprocess.run(["php", …])` call
  (fixed argv, no shell, the sanctioned non-gateway subprocess; the
  `test_house_rules.py:114` inliner-home comment repointed `psh/_legacy.py` →
  `psh/render.py`), PTH123 ×6 + UP015 ×3 behavior-identical rewrites; `C901`/`PLR0915`/
  `PLR0913` did NOT fire (predicted-possible, recorded absent). On `psh/mail.py` — PLR0913
  noqa on `assemble_message` (11 args, pinned signature, I6/I11 precedent) + PTH123 noqa on
  the verbatim `.eml` write (both proven load-bearing — RUF100 passed clean), and **3
  `add_related` pyright ignores** (`get_payload()[1].add_related(...)`: the `[1]` index +
  `add_related` attr — a real ratchet consequence, the inline `_legacy` original was
  pyright-exempt; the one unpredicted-but-real finding). On `annual_billing.py` — **zero
  `noqa`** (only an I001 autofix on `__init__.py`); `_billing_inputs` uses a real
  annotation. **Pyright scope UNCHANGED** (`psh/` minus `_legacy.py`) — D-i8-7/D-i9-8/
  D-i10-9/I11 inherited; **I13 inherits it.**

- **Discovered tasks (dispositions):**
  - **`subprocess` is NOT orphaned in `_legacy.py`** (Task 1, PD#14 grep-verify): SPEC §5's
    orphan-prediction list named it, but `psh.subprocess.Popen` is a documented monkeypatch
    seam (`test_terminus_contract.py`, `test_run_terminus_markup.py` — the shared-module-
    object seam). The grep-verify rule (which SPEC §5 itself mandated) kept it, with a
    `# noqa: F401` + inline reason. The five other named imports (`urllib.parse`,
    `jinja2.Template`, `EmailMessage`, `email.policy.SMTP`, `SMTP_SSL`) were genuinely
    orphaned and removed. → **SPEC §5 corrected in place** (this closing commit, "correction
    (Task 1)").
  - **jinja2 `keep_trailing_newline` test-literal correction** (Task 1): a brief-provided
    test literal `"report for testsite\n"` was wrong — Jinja2's default
    `keep_trailing_newline=False` strips the trailing newline, and `render_report`
    reproduces the original bare `Template(f.read())` verbatim. The authoritative oracle for
    a verbatim move is the original code + the empty golden diff, not a hand-written literal
    (PD#14). → **fixed in the test** (`abd4763`), annotated inline; `render_report` was NOT
    changed to satisfy the wrong literal.
  - **Vacuous `!important`-pass assertion** (Task 1 review, Important, PD#14): the test's
    `<style>p { color: red; }</style>` is fully inlinable, so Emogrifier deletes the
    `<style>` block and the guarded `assert "color: red !important;"` line never executed —
    a green run proved nothing. → **fixed** (`8dbaf75`): a retained `@media` block gives the
    B54 regex pass a real target, the assertion is unconditional, plus a guard-of-the-guard
    and a before/after contrast assertion; red-capability demonstrated.
  - **`_billing_inputs` return annotation** (Task 3 review, Minor): `-> tuple[dict, str,
    float]` — the middle element `portal_site` is a **dict**, not `str` (both call sites
    subscript it). → **fixed** (`79eee7a`, this task's Step 0).
  - **`resolve_recipients` empty-team → silent `""` recipients** (Task 2, a PD#3
    empty/zero-length shadow): when the U-M team list resolves empty, the recipients string
    is `""` and the report addresses nobody without an error — **pre-existing behavior moved
    byte-verbatim**, not introduced here. Recorded for post-campaign consideration (no §8
    surface change, no scope in this increment); I14/post-campaign may add an explicit
    empty-team guard.
  - **`check/umich/__init__.py`'s disabled-branch message is stale** (final-review find):
    it still prints `'Skipping check.umich.sitelens because UMich plugin is not enabled'`,
    but the guard it lives in now skips eight modules, including the two I12 billing hooks —
    **pre-existing**, not introduced here. Ledgered to **I14's sweep**. Disposition: I14.
  - No others beyond the item above — the three task reports found no further gaps beyond
    the ruff/pyright dispositions and the items above.

- **Open questions for I13:** proceed per CAMPAIGN.md §11 row I13. Inherited obligations,
  all ledgered (SPEC §8): **absorb `sort_notices_and_subject` into the final `main()`**;
  **move the B56 csv append + the B57 send block's residue with the B14 accumulators** (the
  D-i12-4 coupling — the accumulators land in I13's `RunState`); the **three I7 dead tail
  inits**. Note for I13's spec author: `psh/mail.py` binds `SMTP_SSL` in its own namespace,
  so a test exercising `smtp_login()` patches `psh.mail.SMTP_SSL` (not `psh.SMTP_SSL`) — the
  same two-binding seam trap as `run_terminus`/`psh.gather.run_terminus`.

## I13 — lifecycle + RunState + main() final form (2026-07-23, commits 6f5c282/3681100 + closing docs commit)

Spec/plan: `development/2026-07-23-mod-I13-lifecycle/` (`SPEC.md` §9 carries the pasted
acceptance; task reports + reviews under `.superpowers/sdd/`). Two code commits, each green:
`6f5c282` (Task 1 — `psh/lifecycle.py`: `RunState` + `record_site_notices` + the ten
lifecycle defs moved verbatim, the `psh/db.py` counter-write retarget, the `script_context.py`
attr swap, `reset_sc` rework, the counter-seam repoint, seam tests §4.1–§4.7), `3681100`
(Task 2 — `main()` final form: `import_packages`, `open_database`, the three dead inits, the
B56/B57 retarget, the §2.8/§2.9 doc edits, seam tests §4.8–§4.9), plus this closing docs
commit (CLAUDE.md / memory / this entry / SPEC §9 acceptance + §2.9 in-place correction / the
dev folder). Both task reviews clean (spec PASS, quality Approved). Full suite at close
**including the live tier** (`ls ~/.terminus/cache/tokens/` → `markmont@umich.edu`;
`tests/live/test_live_smoke.py` → 2 passed) = **1028 passed / 1 skipped** (the skip is
`test_db_credentials.py`'s `importorskip("MySQLdb")` on a sqlite-only install), all three
gates (`All checks passed!` ×2, pyright `0 errors`), 107 snapshots; four goldens
byte-identical across the increment (`git diff 268696c -- tests/e2e/__snapshots__/` empty —
`268696c` is the I12 archive commit, the last before I13 work).

- **Moved:** exactly the §11-row-I13 move set (the B14 accumulators, B56, B59–B60, the resume
  helpers I5 left behind), into the new **`psh/lifecycle.py`** (born gated, re-imported by
  `psh/_legacy.py` — the I2–I12 pattern):
  - **The `RunState` dataclass** (§6's exhaustive six-field set: `emails_sent`, `site_savings`,
    `all_warnings`, `site_results`, `db_reconnects_by_site`, `db_reconnect_failures_by_site`;
    the two counter-dict contract comments moved onto the fields verbatim) + its
    **`record_site_notices(notices, contacts)`** method (the B56 append loop, moved with its
    load-bearing before-the-send comment intact).
  - **The ten lifecycle defs** relocated verbatim (modulo the §5/§6 annotation fixes and the
    §2.2/§2.4 edits): `ResumeSiteNotFoundError`, `sites_from_resume_point`,
    `merge_prior_results`, `finish_run`, `resume_point`, `option_strings_taking_a_value`,
    `resume_command`, `rerun_command`, `abort_reason`, `abort_run`. `finish_run`/`abort_run`
    now take `run_state: RunState`; every accumulator read/write in `main()`, `psh/db.py`
    (`db_retry`), and the two moved targets retargets it. The extracted-block self-diff (Task 1
    report) confirmed every residual hunk is a sanctioned edit.
  - **`main()` final form** (Task 2, still hosted in `psh/_legacy.py` — D-i13-1): B2/B4
    import loops → `psh.modules.import_packages(kind)`; B10 engine+sessionmaker →
    `psh.db.open_database(db_config, *, echo=False)`; the three I7 dead tail inits deleted
    (`site_recommended_plan`/`site_current_plan_index`/`site_recommended_plan_index`;
    `site_current_plan` kept); B56 loop → `run_state.record_site_notices(...)`; B57's
    `emails_sent += 1` → `run_state.emails_sent += 1`.

- **`run_finish` receives the `RunState`** (the I4 deviation-5 discharge): `finish_run`'s
  first statement is `sc.invoke_hooks("run_finish", run_state)`. `CONTRACT["run_finish"]`
  stays `()` — the `RunState` is the hook *argument*, not a contract key. The one in-repo
  test with a `run_finish` probe (`test_finish_run.py`) gained the `run_state` parameter; the
  stale "no arguments until I13" comments (invoke site + `psh/modules.py` `PHASES`) were
  rewritten (PD#7).

- **New two-binding seam trap (spec-review finding 2):** `abort_run` calls `finish_run`
  internally, so after the move that call resolves in `psh.lifecycle`'s namespace — a test
  faking the flush patches **`psh.lifecycle.finish_run`**, NOT `psh.finish_run`. Joins the
  documented trap family (CLAUDE.md § Two mock seams — entry added this closing commit).
  `abort_run`'s SIGINT guard is unaffected (`psh/lifecycle.py` imports the shared `signal`
  module object).

- **Deviations from CAMPAIGN.md:** none of architecture; SPEC-level ledger notes (the
  D-i6-1 "bodies move, glue stays" family):
  1. **D-i13-1 (user-approved 2026-07-23 in the I13 session)** — `psh/_legacy.py` continues to
     host `main()` + `build_arg_parser`/`parse_args` this increment; "`main()` reaches final
     form" is read as *content*-final, not *address*-final. The verbatim relocation to
     `psh/cli.py`, `_legacy.py` deletion, and `psh` fixture redesign are an I0-style zero-logic
     move deferred to **I14** (LEDGER I0 left the timing "I13/I14"). Keeps I13 — the increment
     that rewires `db_retry`, the abort flush path, and Invariant 4 — within session limits
     (D4, split-never-compress).
  2. **D-i13-2** — the one shared home for the accumulators is `sc.run_state` (a single
     `RunState` instance), not parameter threading: `db_retry` (the counter writer) is reached
     from `psh/traffic.py`/`psh/plans.py`/`main()`'s lambda, so threading a `RunState` param
     would widen five already-pinned signatures for no observable gain (the D-i5-1 rule, one
     level up). §3.4 honored — the accumulators *live in* `RunState`; `sc` holds the pointer,
     exactly as it holds `hooks`. Construction (finding 8): `sc.run_state = RunState()` placed
     **before `invoke_hooks("setup")`**, so a future setup hook using `db_retry` can't write
     into a default `RunState` `main()` then discards (a latent PD#1 shape). The
     `script_context.py` counter attrs are **deleted** (finding 7's loud-failure property, one
     level up — pinned by `tests/unit/test_run_state.py`). This does not conflict with §3.5's
     NEVER ("NEVER remove or rename an `sc` attribute mid-campaign"): that clause is scoped to
     the check-facing façade names ("`sc` keeps every name listed in CLAUDE.md's runtime-exposed
     block"), and the two counters were never façade names (absent from both that block and
     `test_documented_sc_facade_names_exist`) — their removal was scheduled at I5 (D-i5-1,
     "scheduled interim home") and in CAMPAIGN §6's `RunState` row, so this deletion discharges a
     standing obligation rather than breaking Invariant 9.
  3. **D-i13-3** — the two call-time bridges in `psh/lifecycle.py`: `abort_reason`'s
     `from psh.db import DatabaseUnavailableError, db_retryable` (§2.1 cycle rule) and
     `option_strings_taking_a_value`'s `from psh._legacy import build_arg_parser` (both
     `# noqa: PLC0415` two-line form, the I6 precedent). The latter is an **I14 obligation** —
     replace with a module-level `from psh.cli import build_arg_parser` when the argparse pair
     moves (recorded at the bridge and in Open questions below).
  4. **D-i13-4** — B10 (engine + sessionmaker + session construction, with the load-bearing
     `expire_on_commit=False` comment) moved into `psh.db.open_database`, finally making
     CLAUDE.md's "`psh/db.py` holds every DB touch this program makes" true.
  5. **D-i13-5 (spec-review finding 4)** — the B11 `--create-tables` short-circuit
     (`Base.metadata.create_all` + `sys.exit`) **stays in `main()`**: it is option gating on
     the orchestrator's control flow (`sys.exit` cannot cross a function boundary usefully —
     the D-i6-1 loop-control reading), preserving today's B10→B11 order. A ledger note, not an
     amendment (the D-i5-3 interim precedent).
  Spec-review (APPROVE-WITH-FIXES) findings 1–9 were **all folded into the SPEC
  pre-implementation** (finding 1 the run_finish probe arity; 2 the two-binding trap; 3
  excluding the 7 `-run.json` artifact-key hits from the counter repoint; 4 the D-i13-5
  disposition ledgered here; 5 the corrected raw `main()` figure; 7 the `sc.debug` location
  stamps at `-v` are §8-sanctioned; 8 the pre-`setup` construction point; 9 the `B904`
  `from None` + the `import psh.db`-first `ImportError` cycle mode) — no post-implementation
  surprises from them.

- **Contract/config/sc additions:** **`sc.run_state`** (the current run's `RunState`; a
  process-global pointer like `sc.hooks`, rebound by `reset_sc` and by `main()` before
  `setup` — **not** check-facing API, so it does NOT join `test_documented_sc_facade_names_exist`,
  the D-i5-1 precedent for the counters it absorbs). **No new contract keys**
  (`CONTRACT["run_finish"]` stays `()`). **No config keys.** Two `script_context.py` module
  attributes **deleted** (`db_reconnects_by_site`/`db_reconnect_failures_by_site` — their
  I5–I12 interim home). New functions `psh.modules.import_packages(kind)` and
  `psh.db.open_database(db_config, *, echo=False)`.

- **`main()` final-form measurement (§6, §17-Q1 honesty clause):** `def main()` at
  `psh/_legacy.py:370`; body spans 370–991. Measured this session:
  `sed -n '370,991p' psh/_legacy.py | wc -l` → **622 raw**;
  `… | grep -vc '^\s*$\|^\s*#'` → **445 logic**. This is **ABOVE** §3.3's 250–400 target, as
  §6 predicts and attributes to the ledgered "stays"-list call-site decisions (D-i6-1,
  D-i8-2, D-i12-2/3/4) plus the file's comment density — the 250–400 figure was a planning
  estimate that did not price those stays. **Flagged for I14's §17 Q1 audit** (the line-count
  delta adjudication). Per PD#14 the spec did NOT invent extra extractions to game the number
  — each §3.3 "stays" line would be the thing extracted, contradicting the frozen architecture.

- **Ratchet (§13):** `psh/lifecycle.py` **born gated** (broad ruff + pyright standard, 0
  findings after dispositions), never in `ruff-broad.toml`'s `extend-exclude`; **I13 deletes
  nothing from and adds nothing to** the exclude list (`psh/_legacy.py` stays grandfathered
  until I14 — I2–I12 precedent). `psh/db.py`/`psh/modules.py`/`script_context.py` stayed
  0-findings. Dispositions confirmed against real tool output (PD#14): predicted §5 findings
  applied as predicted (the `-> str | None`/`-> set[str]`/`-> list[str]` house-style
  annotations + RUF013; `SLF001` on `build_arg_parser()._actions`; `DTZ002` on
  `datetime.today()`; `PLC0415` ×2 on the bridges; `B904` `from None`;
  `C901`/`PLR0912`/`PLR0915`/`PLR0913` on the two verbatim large bodies; `PTH110`/`PTH123`
  **noqa** — verbatim artifact-path IO kept byte-identical, pathlib migration left to I14
  de-grandfathering). **Unpredicted findings**, dispositioned per the §3.1 "moves get no
  algorithmic redesign" precedent (noqa + inline reason, body byte-verbatim): `TRY004`+`TRY301`
  (`merge_prior_results`' `raise ValueError`), `FURB122` (`finish_run`'s `f.write` loop),
  `F541`, `FBT001` (`resume_point`'s `emailed: bool`), `RUF005` (`resume_command`'s list
  concat), `RET505` (`abort_reason`'s `elif`-after-return) — the real cleanup rides with the
  bodies' eventual I14 rewrite. Two **unpredicted pyright ignores** — a consequence of the
  sanctioned `site_name: str | None`/`resume_point -> str | None` widenings surfaced now that
  `psh/lifecycle.py` is in scope: `reportArgumentType`/`reportCallIssue` on
  `site_results.pop(site_name, None)` and `resume_command(sys.argv, resume_site)`, both guarded
  at runtime (the `psh/gather.py` "unreachable in practice" precedent). Pyright scope
  **UNCHANGED** (`psh/` minus `_legacy.py`) — the D-i8-7 lineage; **I14 inherits it**.

- **Discovered tasks (dispositions):**
  - **`import sqlalchemy as db` in `psh/_legacy.py` is now a pure test seam** (Task 2): removing
    B10's in-file `db.create_engine`/`db.orm.sessionmaker` left it with zero in-file uses, but
    `tests/conftest.py`'s `TempDB` reaches `psh.db.create_engine`/`psh.db.orm.sessionmaker`
    through THIS alias (the `db` attribute of `_legacy`), not the `psh/db.py` package. **Kept**,
    `# noqa: F401` + inline reason in the adjacent seam-import house style, so a future cleanup
    can't mistake it for dead code (PD#1). → **fixed/documented here** (Task 2).
  - **SPEC §2.9 was wrong about `no_primary_domain_notice`** (Task 2): verified at `6f5c282^`,
    that function's docstring never carried a "final home I13's call" note — only
    `sort_notices_and_subject` had one. The implementer rewrote `sort_notices_and_subject`'s
    note and **added** the ride-to-`psh/cli.py` note to `no_primary_domain_notice` to honor
    §2.9's intent. → **SPEC §2.9 corrected in place** (this closing commit, "correction
    (Task 3)" — the I12 precedent).
  - **Task-1 review Notes** (all no-action, adjudicated correct): (1) the two new unit tests
    went red only via a collection-error `ModuleNotFoundError` — structural for a brand-new
    module, watched for the right reason; (2) the transient B56-duplication window is
    by-design and the Task-2 reviewer confirmed the `main()` call-site swap; (3) the brief's
    file list omitted `psh/modules.py` but its edit (the stale `PHASES` comment) was in-scope.
  - **Whole-branch-review Note** (no-action): the whole moved family now resolves internally in
    `psh.lifecycle`'s own namespace (`finish_run` → `merge_prior_results`; `abort_run` →
    `resume_point`/`resume_command`/`rerun_command`; `rerun_command` →
    `option_strings_taking_a_value`), so a future test faking any of them must patch
    `psh.lifecycle.<name>`, not `psh.<name>` — nothing patches them today (grep-verified by the
    whole-branch review); CLAUDE.md documents the `finish_run` case and the general lesson.
  - No others — the two task reports found no further gaps beyond the items above.

- **Open questions for I14:** the §2.4 `build_arg_parser` bridge → a module-level
  `from psh.cli import build_arg_parser` when the argparse pair moves; the
  `main()`/argparse relocation to `psh/cli.py` + `psh/_legacy.py` deletion + the `psh`
  conftest-fixture redesign (D-i13-1); the §6 622/445-line delta adjudication (§17 Q1); plus
  every item I12 already carried (Notice dict retirement + the §6 field-set amendment for
  extra-csv notices; `check/umich/__init__.py`'s stale disabled-branch message; the B51
  Aug-2026 "annual bill in progress" deletion, whose date will have passed; config renames).

## Amendments — Wave-4 split + B51 early deletion (2026-07-23, user-approved; applied to CAMPAIGN.md at I14a spec time)

Two CAMPAIGN.md amendments, both user-approved 2026-07-23 in the I14a session (via an
explicit four-option decision round), applied to the document the same day per the
preamble's edit-the-document-AND-ledger rule. Appended at I14a **spec** time — before
implementation — so CAMPAIGN.md's "LEDGER I14a" citations resolve for the whole
increment (adversarial spec-review finding 11); the full I14a increment entry follows
separately at its close.

1. **Wave 4 split into four ordered sub-increments** (§11 wave diagram + row I14 →
   rows I14a–I14d). The closing sweep's measured scope — the `psh/cli.py` relocation,
   a **2,729-finding** ratchet flip (measured 2026-07-23: tests 2,540 of which 1,727
   S101; `psh/_legacy.py` 69; `check/cloudflare` 41; `plugin/` 39; `check/umich`
   legacy pair 16; `check/pantheon_cdn_change` 14; `dns_classify.py` 9; `check/dns` 1),
   the `Notice` retirement, and the full docs refresh — is several sessions of work;
   the §11 split-never-compress rule applied at spec time rather than mid-session.
   I14a = structural finish; I14b = ratchet flip; I14c = Notice retirement;
   I14d = closing (config-migration doc, docs refresh, §17 audit, retrospective).
2. **B51 deleted at I14a, ahead of its date** (§8 "Notice csv values" row; §14 risk
   row). The "annual bill in progress" notice's marker says "remove at the beginning
   of August 2026"; I12/I13 assumed I14 would run after that date, but I14a runs
   2026-07-23 — the date has NOT passed. Per §11's frozen rule ("deletion if past its
   date") B51 would be kept; the user chose early deletion over carrying it
   post-campaign. Zero golden/artifact impact (goldens run umich-disabled; the billing
   produced-keys never reach `-notices.csv` — LEDGER I12).

Related decisions locked the same round: **no config renames at I14d**
(`docs/config-migration.md` will record "no key changes required" with its audit
trail — the schema survey found every section already in final shape), and the
**§3.1 `dns_classify.py` MAY is exercised** (→ `psh/dns_classify.py`, I14a).

## I14a — structural finish (2026-07-23, commits cd084e9/745967e/d94c31a/f22950e/9b1fe35/b39e435 + closing docs commit)

Spec/plan: `development/2026-07-23-mod-I14a-structural/` (`SPEC.md` §9 carries the pasted
acceptance; spec committed BEFORE implementation at `7e7e803` with the Wave-4-split/B51
amendment records appended to this ledger at spec time — see the Amendments entry above;
plan at `d1d3d1a`; task reports under `.superpowers/sdd/`). Adversarial spec review:
APPROVE-WITH-FIXES round 1, all 11 findings folded pre-implementation (incl. the
non-mutation-pin rescue and the six-import-site count correction). Per-task commits, each
green; whole-branch review (fable): **STANDARDS PASS-WITH-FIXES** (two one-line
doc-accuracy fixes, applied in the closing commit) + **SPEC PASS**. Full suite at close
**including the live tier** (`ls ~/.terminus/cache/tokens/` → `markmont@umich.edu`) =
**1023 passed / 1 skipped** (the skip is `test_db_credentials.py`'s
`importorskip("MySQLdb")`), 107 snapshots, all three gates, EXIT=0; four goldens
byte-identical across the increment (`git diff 5902b76 -- tests/e2e/__snapshots__/`
empty). Fast-tier count 1021/1/2 = I13's 1026/1/2 − the 5 sanctioned B51 test deletions.

- **Delivered (SPEC §2.1–§2.3, exhaustively verified by per-task + whole-branch review):**
  - **B51 DELETED** (`cd084e9`+`745967e`+`f22950e`) — the user-approved early deletion
    (§8 amendment; the Aug-2026 date had NOT passed). `build_annual_bill_in_progress_notice`,
    `check_annual_bill_in_progress`, its registration, and the `annual_bill_in_progress`
    produced key are gone; `_billing_inputs` + the upcoming hook stay; the
    non-mutation-of-`site_context["notices"]` pin was REWRITTEN onto `annual_bill_upcoming`
    (never deleted); `test_both_keys_render_in_progress_first_then_upcoming` was DELETED
    not rewritten (its unique content was the two-key interaction, now unreachable; the
    single-key property stays pinned by `test_upcoming_key_overrides_subject_and_leads` —
    reviewer-verified, the SPEC §6 ±1 adjudication).
  - **`dns_classify.py` → `psh/dns_classify.py`** (`9b1fe35`) — the §3.1 MAY, exercised.
    All import sites now `import psh.dns_classify as dns_classify` (call sites qualified;
    single-module-object patch seam preserved — no `from … import` form exists). Born
    gated: 9 ruff findings + 1 pyright `reportInvalidTypeForm` (the house-style tuple
    hint) dispositioned. House-rule scopes: `dns_classify.py` entries dropped from
    `ENVIRON_SCOPE`/`POPEN_SCOPE` (`"psh"` covers it) with the temporary-offender RED
    check recorded. Coverage include entry dropped (`*/psh/*` covers it).
  - **The remnant → `psh/cli.py`; `psh/_legacy.py` DELETED** (`b39e435`, D-i13-1
    discharged) — `build_arg_parser`, `parse_args`, `fqdn_re`, the psh.* re-import blocks
    (the re-export surface: 111 module-level names, baseline-identical, AST-verified),
    `registry.register("no-domains")`, the 13-assignment sc-exposure block (verbatim),
    `no_primary_domain_notice`, `sort_notices_and_subject`, `main()` — bodies verbatim
    (self-diff reproduced independently by the task reviewer AND the whole-branch review:
    zero unaccounted hunks). The inert `if __name__` tail deleted (D-i14a-5). conftest:
    `importlib.import_module("psh.cli")` one-line repoint + comment updates; TempDB, the
    seam patches, reset_sc, run_program unchanged. pyright now gates ALL of `psh/`
    (the `exclude = ["psh/_legacy.py"]` line is gone); `ruff-broad.toml` lost both
    file entries. cli.py chmod 644 (EXE002); shim stays 755.

- **Deviations from CAMPAIGN.md:** none of architecture. SPEC-level decisions
  D-i14a-1…8 (SPEC §2.4) all landed as specced, plus two SPEC §5 disposition
  deviations adjudicated REQUIRED by both reviews: **SIM102 → noqa not rewrite** (the
  nested-if body is the golden-pinned column-16 `no-domains` Notice literal — ruff's
  merge dedents it, an Invariant-8 violation) and **C408 → noqa** (28-kwarg `dict()` in
  a verbatim-moved block). **D-i13-3's "module-level" wording was WRONG and is hereby
  corrected**: `psh/cli.py` imports `psh.lifecycle` at module level, so the lifecycle
  bridge CANNOT become module-level — it stays call-time, retargeted to
  `from psh.cli import build_arg_parser` (`psh/lifecycle.py:337`, noqa PLC0415 + cycle
  reason; docstring diagram updated). **§17 Q5 answered: the `pantheon-sitehealth-emails.py`
  symlink is KEPT** — it still buys ruff/pyright/CodeGraph coverage of the extension-less
  shim's own lines; I14d records it in the rewritten CLAUDE.md.

- **Discovered tasks (dispositions):**
  - **`uvx ruff` drift** — mid-session, unpinned `uvx ruff` began resolving 0.16.0, which
    graduated `PLR0917` from preview: 9 findings in six UNTOUCHED `psh/` files,
    reproduced at baseline in a throwaway worktree. Root cause: the gate's fallback was
    version-unpinned, violating D2's fixed-bar premise. → **fixed here** (`d94c31a`):
    `run-tests` + `.claude/hooks/ruff-check.sh` pin `uvx ruff@0.15.22`. Residual
    exposure, **ledgered to I14b** (which owns the ratchet flip/config merge): a
    PATH-installed ruff is not version-checked, `uvx pyright` is likewise unpinned, and
    upgrading ruff (and dispositioning PLR0917 deliberately) is I14b's call.
  - **`time` is a FOURTH seam import** (Task 3 discovery): 13 tests patch
    `psh.time.sleep`; retained in `psh/cli.py` with noqa+reason beside
    signal/subprocess/sqlalchemy-as-db (whose reason texts were rewritten to `psh.cli`
    phrasing).
  - **Task-1's report Write failed silently** (the LEDGER I1 class, again) — caught by
    the task reviewer (report file absent); rewritten with full evidence, then
    re-review verified content + spot-grepped the directive quotes. Later dispatches
    carried an explicit verify-the-report-exists instruction.
  - **Blame caveat**: `psh/cli.py` pre-existed (the 9-line re-export), so git records
    delete+modify, not a rename — `git log --follow` won't chain across `b39e435`;
    `git blame -M -C` still finds the verbatim blobs.
  - **Report-text corrections** (whole-branch triage, scratch-file only, no committed
    artifact): task-3-report cited `psh/mail.py:144` as a C408 precedent (it is PTH123 —
    principle right, label wrong) and its ratchet table omitted the applied DTZ011.
  - **CLAUDE.md retains ~22 stale `psh/_legacy.py` narrative mentions** — sanctioned
    deferral (D-i14a-7) to **I14d's wholesale rewrite**; in-document warnings added at
    the top of both architecture subsections. The one falsified *config claim* (the
    exclude-list description still naming `psh/_legacy.py`) was fixed at close per the
    whole-branch review, as were the two future-tense "rides to psh/cli.py" docstrings
    in `psh/cli.py` itself.

- **Contract/config/sc additions:** none. No new contract keys, no config keys, no new
  `sc` façade names; one produced key REMOVED with its hook (`annual_bill_in_progress` —
  hook-produced, never registry-owned, so `CONTRACT` is untouched).

- **Ratchet (§13):** `psh/cli.py` and `psh/dns_classify.py` born gated;
  `ruff-broad.toml`'s `extend-exclude` lost `psh/_legacy.py` and `dns_classify.py` (the
  first exclude-list deletions of the campaign — every prior increment moved code into
  fresh files instead). pyright scope is now genuinely `psh/` entire. Remaining
  grandfathered: the check/plugin/tests/development entries — I14b's flip.

- **Open questions for I14b:** proceed per CAMPAIGN.md §11 row I14b (un-grandfather the
  remaining trees; merge `ruff-broad.toml` into `pyproject.toml`; pyright-scope decision).
  Inherited: the ruff version pin (upgrade + PLR0917 disposition is I14b's deliberate
  call, plus pinning `uvx pyright`); the D-i14a-3/8 option (repointing tests off the
  `psh.<name>` re-export surface onto real module homes, and the deeper conftest/TempDB
  redesign) — take it or re-ledger it; the I14b baseline measurements in the Amendments
  entry above (2,540 findings in `tests/`, 1,727 of them S101 → the reserved
  per-file-ignores block; ~120 in the non-test trees).

## I14b — the global ratchet flip (2026-07-23, commits 82f0511/03e7ac2/13a0577/e70c1e3/7ed4e92 + closing docs commit)

Spec/plan: `development/2026-07-23-mod-I14b-ratchet/` (`SPEC.md` §8 carries the pasted
acceptance; spec committed before implementation at `8154823`, plan at `e334a0a`; task
reports under `.superpowers/sdd/`). Adversarial spec review (fable): APPROVE-WITH-FIXES
round 1, all ten findings folded pre-implementation (incl. extending the red-demo
protocol to all four PD rules and the FBT002 disposition). Per-task commits, each green;
whole-branch review (fable): **STANDARDS PASS-WITH-FIXES + SPEC PASS** (all fixes
applied at close — this commit). Full suite at close **including the live tier**
(`ls ~/.terminus/cache/tokens/` → token present) = **1023 passed / 1 skipped**, 107
snapshots, **TWO gates** (the merged single ruff pass + pyright), EXIT=0; four goldens
AND all 107 `.ambr` snapshots byte-identical across the increment
(`git diff 1fa1fa7 -- tests/e2e/__snapshots__/` and `-- '*.ambr'` both empty). Collected
count unchanged (1024; fast tier 1021/1/2). ZERO behavior change on every §8 surface —
the increment's prime rule, held.

- **Delivered (SPEC §1 A–E, verified per-task + whole-branch):**
  - **Task 1 (`82f0511`+`03e7ac2`):** `check/dns/`, `check/pantheon_cdn_change/`,
    `check/umich/sitelens.py`+`cloudflare_cms.py` un-grandfathered (32 findings
    dispositioned).
  - **Task 2 (`13a0577`):** `check/cloudflare/` + `plugin/` un-grandfathered (80
    findings: 58 noqa'd + 22 fixed). One REAL regression caught red-first and reverted:
    ruff's I001 autofix reordered `check/cloudflare/__init__.py`'s load-bearing
    `try/except ImportError` import order (two tests pin which sibling's ImportError
    surfaces) — noqa'd with reason. **Lesson ledgered: SPEC §2.1 rule 4's blanket "I001
    mechanical" sanction has a gap for imports inside try/except blocks; treat every
    import reorder as guilty until the file's tests prove it innocent.** Named security
    dispositions landed (cache.py S311 seeded-RNG; egress.py S104 egress-source
    constant). Rule-6 whole-file noqa reading for the seam files adjudicated CORRECT by
    the task reviewer.
  - **Task 3 (`e70c1e3`):** `tests/` un-grandfathered — the idiom block (15 rules, each
    with a justification comment) absorbs 2,341 of 2,536 findings; the 195-finding
    remainder fixed (154) or seam-noqa'd (41; the 22 PLR0913 + FBT002 fakes mirror
    pinned seam arities). NO assertion semantics, fixture value, expected result, or
    seam name changed (reviewer-audited hunk-by-hunk incl. the conftest SIM114
    interlock-branch merge — proven equivalent, fail-closed, 18 interlock + 21 shim
    tests green; Invariant 7 intact).
  - **Task 4 (`7ed4e92`):** THE MERGE — one `[tool.ruff.lint]` in `pyproject.toml`
    (ignore list + idiom block carried char-for-char, whole-branch-verified);
    `ruff-broad.toml` DELETED; `run-tests` + `.claude/hooks/ruff-check.sh` collapse to
    ONE ruff pass (the gates are now TWO: ruff + pyright); **pyright pinned 1.1.411**
    (test extra `pyright==1.1.411` + `uvx pyright@1.1.411` fallback — closing the
    I14a ruff-drift class for the other tool); `extend-exclude = ["development/2*"]`
    (D-i14b-2: dated archive folders hold verbatim measurement artifacts, permanently
    un-linted — while `development/finalize-session.py` was cleaned (24 findings) and
    stays FULLY gated); the §4 red demonstrations ALL ran (four PD rules each shown red
    under the merged config; nested-tests suppression + plugin/ firing; the
    archive-boundary checks; hook parity — transcripts in the task report,
    whole-branch-review reproduced one per family).

- **The increment's load-bearing discovery (PD#14): the old two-config design linted
  `select=ALL` at ruff's default py310 target for the entire campaign.**
  `ruff-broad.toml`, being a separate config file, had no `requires-python` to infer
  `target-version` from — so the broad pass ran two minor versions below the real
  py3.12, masking UP017 ×3, FURB162, RUF100, and two `import tomllib` I001s (tomllib is
  third-party at py310, stdlib at 3.11+). The merge into pyproject restores correct
  inference; the 7 masked findings were fixed behavior-identically in 6 files (goldens/
  snapshots byte-identical); **no genuine finding is lost at py312** (FA102 requires
  py<3.10 — its absence is also the proof the old target was py310, not py39; PERF203
  is disabled ≥3.11). The pyproject "NO target-version" comment was always right where
  it lived — the defect was that the OTHER config file could never benefit from it.

- **D-i14a-2 reconciliation (`03e7ac2`):** Task 1's PLR0402 fix
  (`import psh.dns_classify as dns_classify` → `from psh import dns_classify` in
  `check/pantheon_cdn_change/chain.py`) initially shipped undisclosed against I14a's
  D-i14a-2, which mandated the alias syntax — caught by the task reviewer (spec FAIL on
  disclosure), adjudicated option (b): the decision's INVARIANT is the single shared
  module object + qualified call sites, not the syntax (proof: `a is b` → True; 21 seam
  tests green); both I14a SPEC spots corrected in place with blockquotes. Gated files
  use the PLR0402-mandated form; the seam is unaffected.

- **Deviations from CAMPAIGN.md:** none of architecture. SPEC-level corrections applied
  in place at close (the I12/I13 precedent): the §2.2 named/tail split was a drafting
  miscount (correct: **172 named / 23 tail**; the binding 195 gate matched exactly —
  Task 3 reviewer + whole-branch both confirmed).

- **Contract/config/sc additions:** no new contract keys, no `sc` names. Config-FILE
  changes (not report-visible keys): the merged `[tool.ruff]`/`[tool.ruff.lint]`
  (§13's final form), `pyright==1.1.411` in the test extra, the ignore-governance
  clause restored into pyproject (whole-branch finding 4), the `D`-convention README
  TODO finally written (promised at I0, delivered at I14b close — PD#9), the E501/D
  ignore-comment pointers de-staled.

- **Discovered tasks (dispositions):** the py310 target defect → **fixed here** (the
  merge itself is the fix; 7 findings). The orphaned `psh/dns_classify.py` comment
  fragment (RUF100 autofix ate the noqa sentence head) → **fixed at close**. Report-text
  corrections (task-2 tally 58/22; task-4 §6 py39→py310 + tomllib-I001 mechanism +
  §9.1 residual) → **fixed in the scratch reports** (audit record accuracy; PD#14
  applies to the explanation of a lying instrument too). `README.md:275`'s present-tense
  `ruff-broad.toml` prose + CLAUDE.md's architecture-body references to the two-pass
  design → **I14d's wholesale refresh** (named here so its inventory is complete).
  `tests/tools/record.py` + `tests/shims/pyshim/dnsshim.py` edits are not
  suite-executed — assessed by reading in both reviews (trivial-mechanical; shim
  indirectly covered by `test_shim_composability.py`).

- **Open questions for I14c:** proceed per CAMPAIGN.md §11 row I14c (`Notice` dict form
  retired: the reserved §6 csv-field amendment + every producer converted; artifacts
  byte-identical). Inherited context: every notice with extra csv fields
  (`not-installed,{name}`, `turned-off,{name}`, `updates-addons,{num}`,
  `drupal-ua,{ua}`, the smell csvs, `its-recommends-plan`'s savings field,
  `annual-bill,{amount},{shortcode}`) needs the §6 field-set amendment BEFORE
  conversion (the I3→I7→I10→I12→I14 deferral chain ends here); `add_notice`'s
  `_notice_to_dict` normalization is the byte-identity mechanism; the whole tree is now
  gated, so new/edited files carry no grandfather escape. The three post-campaign README
  TODOs (ruff upgrade + PLR0917; typed sc stubs + pyright widening; test repoint) are
  NOT I14c/I14d scope.

## Amendment — §6 `Notice` csv field set (2026-07-24, applied to CAMPAIGN.md at I14c spec time)

One CAMPAIGN.md amendment, appended at I14c **spec** time — before implementation, so the
spec's "§6 as amended" citations resolve for the whole increment (the I14a precedent).
The full I14c increment entry follows separately at its close.

**§6 types table, `Notice` row:** the field set gains **`csv_extra: tuple[str, ...] = ()`**,
joined after `site,code` to build the notices-csv row. This is the amendment the row itself
reserved at I3 ("a notice whose csv needs extra fields stays a dict until the first
increment that converts one, which MUST amend CAMPAIGN.md §6") and that I7, I10 and I12 each
deferred; I14c is that increment, because §11 row I14c requires **every** producer converted
and 22 of the 37 carry extra csv fields (`turned-off,{name}`, `updates-info,{n},{days}`,
`wp-error,{operation},{json}`, the dns `",".join(hostnames)` forms, `annual-bill,{amount},
{shortcode}`, `its-recommends-plan,{cur},{rec},{savings:.2f}`, `cloudflare-cache,{fqdns},
{ids}`, and `no-primary-domain,` — whose trailing **empty** field is real and is expressed as
`csv_extra=("",)`).

Shape chosen (user decision round, 2026-07-24) over two alternatives: a `csv_suffix: str`
(keeps comma-joining scattered across 22 producers, models nothing) and a full `csv: str`
override (re-admits the free-form string the type exists to retire, and hands the site name
back to producers). A tuple — not a list — because `Notice` is `frozen=True`.

The same row's "dict form retired in I14" now reads **I14c** explicitly. Related decisions
locked in the same round, both recorded in `development/2026-07-24-mod-I14c-notice/SPEC.md`
(§2.3, §2.7): every notice code is **registered at import** (making `NoticeRegistry`'s
duplicate-code guard load-bearing rather than dead façade surface — §17 Q4), with a
`snapshot()`/`restore()` test seam driven by the autouse `reset_sc` fixture, because the
suite loads `check/` modules standalone once per test and a second `register()` of the same
code would otherwise raise; and I14c stays **one increment** of six tasks under §11's
split-never-compress backstop.

**Correction (2026-07-24, I14c adversarial spec review round 1).** The paragraph above says
"22 of the 37 carry extra csv fields". The measured figure is **28** (9 producers use the plain
two-field `{site},{code}` form; 37 − 9 = 28), reproduced by
`development/2026-07-24-mod-I14c-notice/tools/notice_inventory.py`, which the review's finding 7
required and which now produces every such figure in the I14c SPEC. The amendment's substance is
unaffected — the field set still gains `csv_extra` for the same reason — but a ratified campaign
document does not carry a wrong number silently (CAMPAIGN.md §7 obligation 4).

## I14c — the `Notice` dict-form retirement (2026-07-24, commits `b3ffd29`…`b619b7d` + closing docs commit)

Spec/plan: `development/2026-07-24-mod-I14c-notice/` (`SPEC.md` §8 carries the pasted
acceptance; spec committed BEFORE implementation at `982589f`, its adversarial-review fold at
`b3ffd29`, plan at `7affff8`; task reports under `.superpowers/sdd/`). Adversarial spec review
(fresh-context `psh-reviewer`): APPROVE-WITH-FIXES round 1, **all 14 findings folded
pre-implementation**. Per-task commits, each green, with per-task reviews after Tasks 1 and 2
and a batched review of Tasks 3–5 (both PASS-WITH-FIXES; every finding folded in a labelled
follow-up commit). Whole-branch review (fresh context): **SPEC PASS-WITH-FIXES + STANDARDS PASS-WITH-FIXES**, 12
findings — the five pre-close ones fixed in the closing commit (below), the other seven
ledgered to I14d (below). Full suite at close
**including the live tier** (`ls ~/.terminus/cache/tokens/` → `markmont@umich.edu`) =
**1055 passed / 1 skipped**, 107 snapshots, both gates, EXIT=0.

- **Delivered (SPEC §1.1 A–F):** all **37** dict-form notice producers across 20 files now
  construct a `psh.notice.Notice`; `SiteContext.add_notice` accepts nothing else (a dict raises
  a named `TypeError`); the six-key **render dict** stays the storage form, built by the one
  public projection `SiteContext.notice_to_dict`. The reserved §6 field-set amendment landed as
  **`csv_extra: tuple[str, ...]`** (28 of the 37 producers carry extra csv fields), joined after
  `site,code` by the projection — so **the site name now comes from the `SiteContext`, never
  from the producer**. All **36** roster codes are registered at import through `NOTICE_*`
  constants and pinned by the new `tests/integration/test_notice_roster.py`.

- **Byte-identity (the increment's prime rule, held):** the four e2e goldens are byte-identical
  across the whole increment (`git diff 982589f -- tests/e2e/__snapshots__/` empty), and the
  ONLY snapshot change anywhere is the **7 sanctioned added `'icon'` lines** in
  `tests/integration/__snapshots__/test_dns_notice_render.ambr` (SPEC §3, enumerated in advance:
  those five builders omit `icon`, and the test snapshotted the builder return *before*
  `add_notice` would fill it; it now snapshots the projection, which always emits it). Zero
  deletions in that diff. No notice csv value changed.

- **Deviations from CAMPAIGN.md:** one, amended in the document this commit — **§3.5's
  "checks and plugins import only `sc`" gains a single sanctioned exception**:
  `check/pantheon_cdn_change/notices.py` imports `Notice`/`Severity`/`registry` directly from
  `psh.notice`. That module is deliberately pure and
  `tests/unit/test_pantheon_cdn_change_notices.py::test_notices_module_is_pure` asserts its
  namespace holds exactly one module object; measured, `import psh.notice` adds 18 stdlib
  modules where `import script_context` adds 276 (sqlalchemy, rich, html2text, all of `psh`).
  `psh/notice.py` is itself pure, so the exception introduces no cycle. Every other `check/`
  module uses `sc.Notice`/`sc.Severity`/`sc.registry`. Extending it needs its own amendment.
  SPEC-level decisions D-i14c-1…11 all landed as specced.

- **Contract/config/sc additions:** **`sc.registry`** (via the top-of-`script_context.py`
  `from psh.notice import Notice, Severity, registry` import — the I3 mechanism; added to
  CLAUDE.md's façade list and to `test_house_rules.py`'s `SC_FACADE_NAMES`, which is what can
  actually go red). No new contract keys, no config keys. `annual_bill_upcoming` keeps its
  render-dict type — the builder returns a `Notice` and the hook publishes
  `site_context.notice_to_dict(...)`, so `sort_notices_and_subject` and its tests are untouched
  (SPEC §2.5).

- **What the increment fixed on the way through:**
  - `check_drupal_module`'s hand-rolled `level`→icon map (a duplicate of `sc.icon` that would
    have shipped a warning triangle on an `alert`) is gone; `Severity(level)` derives it from
    the one map and raises `ValueError` on an unknown level. Both reachable levels
    (`warning`, and `info` via `check/umich/cloudflare_cms.py:31`) are byte-preserved.
  - **26 explicit icon literals deleted** (measured equal to the severity default); exactly one
    custom icon survives, the 💵 on `annual-bill`, and now has its own pin.
  - `wp_error`/`drush_error`'s second parameter renamed `code` → `operation`: after conversion
    it sat next to `Notice.code` meaning something else entirely (PD#11).
  - `tests/unit/test_php_eol_notice.py` loaded a producing module at **module import**, which
    registers before `reset_sc` snapshots the registry and so cannot be undone — moved into a
    function-scoped fixture. That is now a stated invariant: **no producing module may be
    executed outside a function-scoped fixture or test body.**
  - `sitelens-url-paths` had no csv assertion anywhere in the suite (and no severity
    assertion); both now exist.
  - A stale test fake in `tests/integration/test_check_umich_cloudflare_cms.py` had been
    returning a dict where the real builder returns `Notice`s — green but wrong-shaped for four
    tasks; caught by the retirement.
  - `check/cloudflare/notices.py`'s `build_cache_notices` lost its now-dead `site_name`
    parameter, and with it a line-scoped `# noqa: ARG001` that was silently covering two other
    parameters as well.

- **Instruments (PD#14), both committed under
  `development/2026-07-24-mod-I14c-notice/tools/`:** `notice_inventory.py` produced every
  measured figure in the SPEC (the drafted "34 icons"/"22 extra-field csvs" were both wrong and
  were corrected from it), and its `--gate` is the close gate — AST-based because a
  `grep '"csv":'` is quote-blind and would have missed `check/umich/sitelens.py`.
  `literal_equality.py` is the Invariant-8 proof: an `ast.dump` multiset over notice-body
  literals, with a built-in `--self-test` that re-indents a real literal in memory and asserts
  the comparison goes red (after an unparse/reparse control). **Both instruments were found
  defective mid-increment and fixed** — the first version could not see `sc.Notice(...)` calls
  (an `ast.Name`-only match), so it reported "identical" for every converted `check/` file while
  seeing zero literals in it; and a zero-literal file counted toward the `N/N` pass tally. Final
  state: 20/20 converted files byte-identical from the increment base, 2 files reported
  separately as having no literals.

- **Discovered tasks (dispositions):**
  - `uvx pyright@1.1.411` (the `./run-tests` fallback when no pyright is on PATH) runs in an
    isolated environment with none of the project's dependencies and reports **34 false
    `reportMissingImports`**. The venv binary the gate normally resolves is correct. Loud, not
    silent, so not a defect in the gate — but the fallback is useless in practice.
    → **README TODO / I14d** (it belongs with the pinned-tool discussion I14b started).
  - Five now-unused `site_name` parameters were reviewed; four in `check/dns/notices.py` are
    **kept** deliberately (a five-builder family called at one seam, one of which genuinely uses
    it, keeps a uniform signature — `# noqa: ARG001` with the reason at the first) and the
    cloudflare one was dropped. → **done here**.
  - `pyproject.toml`'s `[tool.pyright]` still includes only `psh/`, so the 24 converted `check/`
    producers are un-type-checked; `Notice.__post_init__`'s `csv_extra` element check is the
    runtime stand-in. → the existing post-campaign README TODO (typed `sc` stubs + pyright
    widening) already covers it; **no new item**.

- **Whole-branch review findings fixed at close (5):**
  1. **The convergence finding, and the increment's own lesson.** The Tasks-3–5 review found
     that `sitelens-url-paths` had no severity assertion; Task 6 pinned that one and its comment
     declared it "the only notice code" in that state. It was not: the whole-branch review
     measured **six more** (`composer-update`, the three smells, `no-primary-domain`,
     `drupal7-eol`) whose severity this increment rewrote with nothing asserting it, none of
     them in any golden. Severity drives `sort_notices_and_subject`, so a silent demotion
     changes a real report's notice order **and its email subject prefix** ("Action Required" →
     "Action Recommended") with every test green. Root cause: SPEC §4 measured "every other code
     appears in at least one test file" — *appearing in* is not *asserted by* (PD#14 exactly).
     All six pinned, each shown red by flipping the producer's severity; the false comment
     corrected. This is the `fix-the-class-not-the-instance` memory note, missed by a review
     that had itself just named the class.
  2. SPEC §2.2's "those parameters stay: the builders' console messages use them" was falsified
     by the Tasks-3–5 fold (which dropped `build_cache_notices`'s `site_name`) — corrected
     **in place with the correction recorded**, per `prompts/adversarial-review.md`, not
     silently rewritten.
  3. SPEC §8 promised pasted acceptance output and carried a stale pre-run expectation
     (`1023`); the real seven-command output is now pasted there.
  4. `notice_inventory.py --gate` did not enforce the contract its own docstring states — it
     excluded *every* dict in `script_context.py` rather than requiring **exactly one**, so a
     second hand-built render dict in the very file that owns the projection would have passed
     silently. **The third defect found in this increment's two instruments**, and the same
     failure mode each time: a tool printing a verdict it had not actually checked.
  5. `psh/notice.py`'s module docstring stated "checks/plugins reach Notice/Severity via sc"
     without the sanctioned exception — a reader arriving at the type's definition was told a
     rule the tree violates.

- **Ledgered to I14d (7 whole-branch findings, none blocking):**
  - `Notice.__post_init__` validates `csv_extra` element types but not `severity`, on identical
    reasoning (an ungated `check/` module passing `severity="warn"` surfaces as an anonymous
    `KeyError: 'warn'` from the projection). Latent today — every producer passes an enum member.
  - Nothing structurally requires a `Notice.code` to be **registered**: the roster test compares
    the registry against the roster, and an unregistered code never enters the registry, so a
    future producer writing `code="whatever"` passes everything. CLAUDE.md states the rule as if
    it were enforced.
  - The registration comment block is 17 near-identical copies (~75 lines) now that CLAUDE.md
    carries the rationale, with two visible drifts (a sentence present in two Task-4 single-code
    modules but not the nine other single-code ones; every `check/` copy ending "added at I14c
    Task 6" on files whose block landed at Task 3/4/5). Collapse with the CLAUDE.md rewrite.
  - CLAUDE.md's "every producing module registers … through `NOTICE_* = sc.registry.register(...)`"
    is wrong for five modules (the four in `psh/`, which cannot use the façade, plus the
    cdn-change exception).
  - Three stale test comments describing a fill `add_notice` no longer performs, and one section
    banner naming `multisite-check` as a notice code when it is the `operation` argument — the
    exact collision D-i14c-8 renamed the parameter to prevent.
  - `tests/unit/test_cachecheck_consolidation.py`'s `_CACHED` executes a producing module once
    per **session** while satisfying the §2.3 invariant literally. Fails loud if it ever
    collides, but the invariant as stated is necessary, not sufficient — restate it as "and no
    producing module may be cached across tests", or drop `_CACHED`.
  - `Severity(level)`'s new named `ValueError` has no test; SPEC §5(1)'s "exhaustive" list
    over-included two files that correctly needed no change; and `literal_equality.py`'s
    disclosed blind spot ("field renames are invisible") is narrower than the truth — the
    multiset is per file across `html|text|short` combined, so a producer whose `html` and
    `text` bodies were *swapped* also compares equal (covered in practice by the `.ambr`
    pins, but the tool should say so).

- **Open questions for I14d:** proceed per CAMPAIGN.md §11 row I14d (config-migration doc
  recording "no key changes required" with its audit trail; sample-toml refresh; the wholesale
  docs/README/CLAUDE.md rewrite; ledger fully resolved; retrospective + the §17 closing audit).
  Inherited specifically: **§17 Q4 is now answerable for `NoticeRegistry`** — it is load-bearing,
  not dead façade surface; CLAUDE.md's "Notices vs. news" bullet was rewritten factually here but
  is I14d's to re-integrate; the two `tools/` instruments are increment artifacts under
  `development/2*` (ruff-excluded) and I14d should decide whether anything in them deserves to
  become a permanent test.

## I14d — closing the campaign (2026-07-24, commits `55964fc`…`4893046` + this closing commit)

Spec/plan: `development/2026-07-24-mod-I14d-closing/` (`SPEC.md` §8 carries the pasted
acceptance; spec committed BEFORE implementation at `6d405f7` = **increment base `$BASE`**,
plan at `96dfdf0`; task reports + reviews under `.superpowers/sdd/`). This is the campaign's
**final increment** — it makes the documentation true and answers the closing audit; it is
documentation-only save one production edit (finding 1's `Notice.severity` validation, §2.5).
Per-task commits, each green (Task 5 the seven findings `5962d3e` ran early per the SPEC's
"T5 MAY move earlier"; then Task 2 CLAUDE.md `e371d03`, Task 3 docs `1378cf8`, Task 4 config
`0a65eb5`, Task-5-review fold `4893046`). Full suite at close **including the live tier**
(`ls ~/.terminus/cache/tokens/` → `markmont@umich.edu`) = **1060 passed / 1 skipped**, 107
snapshots, both gates (merged ruff + pyright), EXIT=0; four goldens AND all 107 `.ambr`
snapshots byte-identical across the increment (`git diff 6d405f7 -- tests/e2e/__snapshots__/`
and `-- '*.ambr'` both empty).

- **Delivered (SPEC §1.1 A–F):**
  - **A — the claim instrument + inventory** (`55964fc`): `tools/claim_check.py`
    (dependency-free; decides path/symbol/test-node/`sc.<name>`/count claims, marks everything
    else `PROSE`, `--self-test` proves each decision kind can go red — PD#14) + the committed
    `CLAIMS.md` disposition table (mechanizable rows decided by the tool, `PROSE` rows
    dispositioned by a fresh-context `psh-reviewer`).
  - **B — CLAUDE.md rewritten to final state** (`e371d03` + review fold `c04b87c`): no `I<n>`
    archaeology, the 22-row Keep list intact (each load-bearing warning kept with the bug it
    prevents), the campaign section replaced by a short pointer to this folder. `claim_check.py
    --gate CLAUDE.md` green.
  - **C — README / docs/ / prompts/ / tests/README.md / CONTEXT.md / memory refreshed**
    (`1378cf8`): the two-config ruff prose → the merged single pass; pyright scope → all of
    `psh/`; the campaign-in-progress banner → complete, pointing at `CLOSING-AUDIT.md` +
    `RETROSPECTIVE.md`; the nine memory files' `psh/_legacy.py`/`ruff-broad.toml`/top-level
    `dns_classify.py` mentions → final state.
  - **D — `docs/config-migration.md`** (`0a65eb5` + review fold `4893046`): headline **no key
    changes required**, with the audit trail (section inventory vs. every reader; why each new
    key needed no rename; what an operator MAY add, all defaulting to today's behavior); the
    sample toml verified key-by-key.
  - **E — the seven findings LEDGER I14c ledgered here** (`5962d3e`) — see Discovered tasks.
  - **F — ledger fully resolved + `CLOSING-AUDIT.md` (nine §17 answers) + `RETROSPECTIVE.md` +
    this entry** (this closing commit).

- **Deviations from CAMPAIGN.md:** none of architecture. One amendment landed at I14a **spec**
  time and is *executed* here — the **Wave-4 split** completes: I14d is the fourth and last of
  the four sub-increments the "I14 closing sweep" was split into (LEDGER "Amendments — Wave-4
  split", 2026-07-23). This closing commit adds the **CAMPAIGN.md `**Completed:**` status
  line** under the existing `**Status:**` line (the frozen document gains one amendment marking
  it done, per its preamble's edit-the-document-AND-ledger rule; the architecture below stays
  frozen). SPEC-level decisions D-i14d-1…11 all landed as specced.

- **The seven I14c-ledgered findings (§2.5) — dispositions:**
  1. `Notice.__post_init__` now validates `severity` with a strict `isinstance(self.severity,
     Severity)` → named `TypeError` (validate, never coerce — the `csv_extra` posture, D-i14d-9).
     **Precondition measured and stated** (D-i14d-9): every current producer and test fake
     passes a `Severity` member, so no call site needed correcting. Red first:
     `tests/unit/test_notice.py::test_severity_must_be_a_severity_member` — a bare string
     constructed fine before.
  2. **New permanent `tests/integration/test_notice_registration.py`** (AST over `psh/` +
     `check/` + `plugin/`, D-i14d-3): every `Notice(...)`/`sc.Notice(...)` passes `code=` a
     module-level `NOTICE_*` constant, and every `NOTICE_*` is a `registry.register(...)`
     result. **The two red demonstrations:** shown red by a temporary literal-code producer
     AND a temporary non-registering constant, each reverted after recording. This makes
     `NoticeRegistry` load-bearing — §17 Q4(a).
  3. **Registration-comment-block count correction.** LEDGER I14c stated **17**; the measured
     figure at spec time was **19 files carry a block**, and `psh/cli.py` registered
     `no-domains` with **no** block — so the collapse produced **20** files each reading alike
     (the 19 + `psh/cli.py`, which gained the one-liner: `psh/cli.py | 1 +` in `5962d3e`). A
     ratified document does not carry a wrong number silently (§7 obligation 4). **Distinct
     from that block count**, the Task-2 review confirmed only **2 STALE COMMENT sites** (part
     of finding 5): the `add_notice`-fills comment at
     `tests/integration/test_check_pantheon_cdn_change.py:57` and the `multisite-check` section
     banner at `tests/integration/test_drupal_notice_render.py:63` — finding 5's "three stale
     `add_notice` comments" estimate was high; only these two were real, both corrected in
     place. The two counts (20 blocks collapsed; 2 stale comments corrected) are independent.
  4. CLAUDE.md's "every producing module registers through `NOTICE_* = sc.registry.register(...)`"
     — corrected in the §2.2 rewrite: `psh/` uses `registry` directly (cannot use the façade),
     `check/`/`plugin/` use `sc.registry`, with `check/pantheon_cdn_change/notices.py` named as
     the one sanctioned direct importer.
  5. Stale test comments / the `multisite-check`-as-code banner — the 2 sites above, corrected.
  6. `_CACHED` **dropped** from `tests/unit/test_cachecheck_consolidation.py` (D-i14d-11): the
     file's 33 tests load the small pure module per test now; the invariant is simultaneously
     restated in CLAUDE.md Keep-list #15 as "and never cached across tests".
  7. `Severity(level)`'s named `ValueError` gained a test at `psh.gather.check_drupal_module`
     (`tests/integration/test_gather_drupal.py`; red demo: temporarily restore a plain-string
     severity, showing the test passes without the conversion, then revert). Both I14c SPEC
     over-statements (§5(1)'s two over-included files; `literal_equality.py`'s narrower-than-
     truth blind spot) corrected in place with the correction recorded, per
     `prompts/adversarial-review.md`.

- **`literal_equality.py` stays an archive artifact** (D-i14d-6, not promoted to a permanent
  test): it compares a file against a git baseline commit, so it would need a moving reference
  point and would go red on every legitimate notice-copy edit; its Invariant-8 guarantee is
  already held permanently by the four e2e goldens + the 107 `.ambr` snapshots. **Disclosed
  blind spot:** its `ast.dump` multiset is per file across `html|text|short` *combined*, so a
  producer whose `html` and `text` bodies were *swapped* also compares equal (covered in
  practice by the `.ambr` pins). It stays a committed increment artifact under `development/2*`
  (ruff-excluded); `test_notice_registration.py`'s registration guarantee is what earned
  permanence instead (finding 2).

- **Contract/config/sc additions:** none. No new contract keys, no config keys, no new `sc`
  façade names. The only production-code edit in the whole increment is finding 1's
  `Notice.severity` validation in `psh/notice.py`; everything else is documents, comments, and
  tests. Every §8 behavior surface unchanged (goldens/`.ambr`/csv/stdout/config byte-identical).

- **Final test count with arithmetic:** I14c closed at **1055 passed / 1 skipped**; I14d adds
  **5** tests — `test_severity_must_be_a_severity_member` (1) + `test_notice_registration.py`
  (3) + the `Severity(level)` `ValueError` pin (1) — so **1055 + 5 = 1060 passed / 1 skipped**,
  107 snapshots. Matches the SPEC §5 expectation exactly; no unexplained delta.

- **Discovered tasks (dispositions):**
  - **The whole ledger-resolution walk** (Step 1 / §17 Q6): every "Discovered tasks" and "Open
    questions" item in entries I0…I14c given exactly one terminal disposition (done / README
    TODO / declined) — the table is in `CLOSING-AUDIT.md` Q6; nothing resolves to "carried".
    Two items surfaced as genuine **README TODO** additions during the walk: the semver-3
    `PendingDeprecationWarning` (LEDGER I9) folds into the pre-existing "dependency updates"
    item (CAMPAIGN §15), and the **stale `check/umich/__init__.py` disabled-branch message**
    (LEDGER I12, ledgered to "I14's sweep", never fixed I14a–c) is added to README's
    post-campaign list — a stdout-only accuracy fix outside I14d's documentation-only scope
    (SPEC §3 permits only finding 1's production edit).
  - **Four post-campaign README TODOs created** (SPEC §7, none executed here): further `main()`
    extraction toward §3.3's target (D-i14d-1, §17 Q1); the useless `uvx pyright@1.1.411`
    fallback (LEDGER I14c); the declined docs path-guard with its reasoning (D-i14d-7); the
    stale-umich-message reword above. The Q4 scan found **no dead `sc` name** to add
    (§17 Q4(b) — all 16 façade names have live `check/`/`plugin/` consumers; reported not
    deleted per D-i14d-10 / Invariant 9).
  - No others — the six task reports and their reviews found no further gaps.

- **Ratchet (§13):** no code moved; the merged single ruff pass + pyright (all of `psh/`) stay
  as I14a/I14b left them. `tools/claim_check.py` lives under `development/2*` (ruff-excluded,
  D-i14b-2), like I14c's two instruments. Both gates green at close.

- **Open questions: none.** This is the campaign's last increment; everything unresolved is a
  **README TODO** by now, and this entry says which (the four post-campaign items above, plus
  the standing four from before — ruff upgrade + PLR0917; typed `sc` stubs + pyright widening;
  repoint tests off the `psh.<name>` re-export surface; the `mutates` hook declaration). The
  campaign is **complete**: CAMPAIGN.md carries its `**Completed:**` status line, the closing
  audit and retrospective are written, and the ledger is fully resolved.

## 2026-08-07 — post-campaign: six stage bodies out of `main()` (commits `5f58192`…`ecae81a` + this docs commit)

**Not `I<N>`-numbered: the campaign is closed.** CAMPAIGN.md has carried its
`**Completed:** 2026-07-24 at I14d` line since I14d, and this increment neither reopens it
nor adds an increment to it. It is recorded here because it discharges a campaign artifact
(post-campaign TODO **D-i14d-1**, CLOSING-AUDIT.md Q1) and because it amends CAMPAIGN.md
§3.3, which by that document's preamble *requires* a ledger entry. Spec:
`development/2026-08-07-main-extraction/SPEC.md` (which cites CAMPAIGN.md by section and
re-derives nothing, per §12's protocol). Run through
`superpowers:subagent-driven-development` under `prompts/implementation-standards.md`: one
implementer per task, each adversarially reviewed by a separate fresh-context agent that
re-ran the suite, byte-diffed the moved code against its pre-extraction source, and proved
each new instrument red-capable by fault injection.

- **Moved** (six extractions, one commit each, all behavior-preserving; block IDs per
  `BLOCKMAP.md`):

  | Commit | Extraction | Blocks | From → to |
  |---|---|---|---|
  | `b106f80` | `build_traffic_window` + `TrafficWindow` | B43, B44 (residue) | `main()` → `psh/traffic.py` |
  | `9f44959` | `gather_framework` + `FrameworkGather` | B33, B34 (residue), B35 (residue), B36 | `main()` → `psh/gather.py` |
  | `51cf48a` | `no_domains_notice`, `fetch_site_domains` + `SiteDomains`, `resolve_site_url` + `SiteUrlFacts` | B29, B30 (residue), B32 (residue), B31's `site_url` derivation | `main()` → `psh/cli.py` |
  | `d5063dd` | `resolve_site_roster` + `SiteRoster` | B14 (roster half) | `main()` → `psh/cli.py` |
  | `c47807b` | `resolve_site_plan` | B17 (residue), B18's Sandbox skip, B20 | `main()` → `psh/plans.py` |
  | `ecae81a` | `validate_options` | B5 (guard bodies) | `main()` → `psh/cli.py` |

  `5f58192` + `284a8f9` are the SPEC and its review-fix round. **`main()`: 622 raw / 445
  logic → 454 raw / 318 logic** (`psh/cli.py:618-1071`), re-measured with CLOSING-AUDIT.md
  Q1's AST snippet on the post-increment tree — **inside §3.3's 250–400 target on the logic
  measure**, which is what discharges D-i14d-1.

- **Deviations from CAMPAIGN.md:** **five §3.3 stay-list amendments**, all applied to
  CAMPAIGN.md in this same commit and ledgered in the entry immediately below (A1 B5, A2
  B14, A3 B17, A4 B18-split + B20, A5 B31-narrowed). Nothing else: no module boundary,
  phase, hook, contract key, invariant, or §8 behavior surface changed. Two spec-level
  deviations, both recorded in the increment SPEC rather than applied silently: extraction 3
  gained a **third** function (`no_domains_notice`, SPEC §10 item 6 — the pure builder that
  makes the Invariant-8 assertion writable at all), and Task 3 **strengthened** SPEC §8.3's
  prescribed assertion (SPEC §10a row n).

- **Contract/config/`sc` additions:** **none.** No new contract key, no config key, no new
  `sc` façade name. The four e2e goldens and all 107 `.ambr` snapshots stayed
  **byte-identical** through all six commits — the increment's central gate, never once
  refreshed (`--update-goldens` was never run; Invariant 1).

- **Tests: 1743 → 1818 passed** (3 skipped, 107 snapshots), **+75 across 7 new files** —
  `tests/unit/test_traffic_window.py` (5), `tests/unit/test_no_domains_notice.py` (11),
  `tests/unit/test_validate_options.py` (14), `tests/integration/test_gather_framework.py`
  (12), `tests/integration/test_site_domains.py` (19),
  `tests/integration/test_site_roster.py` (7),
  `tests/integration/test_resolve_site_plan.py` (7). 5+11+14+12+19+7+7 = 75; no unexplained
  delta. Several regions got their **first** test at any tier: the `no_domains_notice`
  non-dict-payload guard, `site_count`-before-the-resume-filter, the
  `--update-cloudflare-fqdns` guard, the zero-traffic `plan_on_day` synthetic seed, and
  `gather_framework`'s unknown-framework branch. `gather_framework` also carries the first
  **mechanical** check of CAMPAIGN.md §3.4's parallel-ready criterion (it runs with no
  `sc.run_state` bound at all), which was a review criterion and nothing else for the whole
  campaign.

- **New rule, R-G4 (recorded in CLAUDE.md):** no extracted helper may be the sole assigner
  of `site_name` or `site_emailed`. Both are read by the `except BaseException` handler
  ~450 lines away; a helper owning the per-iteration `site_emailed = False` reset would let
  `abort_run(..., emailed=True)` advance the resume point **past** a site that never got its
  email, and drop that site's `site_results` cleanup — invisible to all four goldens
  (PD#1). The two bindings three characters apart (`psh/cli.py`'s pre-loop binding vs. the
  per-iteration reset) are the concrete trap.

- **Discovered tasks (dispositions):**
  1. **A pre-existing defect, pinned but NOT fixed → README TODO** (added this commit): for
     a `wordpress_network` site whose `network_home_url` eval is **fatal**,
     `wordpress_network_url` (`psh/gather.py:246-249`) returns `("", "")` rather than
     `(None, "")` — `run_terminus` yields `""` and `"".strip()` is a `str` — so
     `resolve_site_url`'s `if network_url is not None:` overwrites a good
     `https://{main_fqdn}/` with `""` and the report renders with an empty `site_url`.
     Verified pre-existing at base commit `9f44959`; today's behavior is pinned by
     `tests/integration/test_site_domains.py::test_a_fatal_network_url_fetch_blanks_the_site_url_and_notices_the_failure`.
     Not fixed here: this increment is behavior-preserving, and the fix changes a rendered
     email.
  2. **The orphaned pathlib deferral → README TODO** (added this commit): four `noqa`
     comments in `main()` (`psh/cli.py:621, 660, 661, 693`) say *"pathlib migration is
     I14b+"*, but I14b's ledger entry never touched PTH and neither README.md nor CLAUDE.md
     mentioned it. PD#9 — a deferral nobody can find is a vague intention.
  3. **A decorative `monkeypatch`** in
     `tests/integration/test_site_domains.py::test_the_plugin_context_bag_is_never_read_when_the_gate_is_off`:
     the test stays green with the patch removed, because the real `cloudflare_enabled()` is
     already falsy under the test config. **Not a coverage hole** — its sibling is a
     verified S5 instrument — but it reads as double-covering the seam. Triage in a later
     test pass.
  4. `tests/integration/test_site_domains.py::test_an_undecodable_payload_returns_the_skip_sentinel`
     asserts the skip sentinel but **not** the operator console message its sibling asserts
     (PD#1 — the message is the visible half of the failure). Small, additive; deferred.
  5. **A pre-existing ruff warning fires on every gate run**: *"Invalid `# noqa` directive
     on `psh/cli.py:879`: expected code to consist of uppercase letters followed by digits
     only"* — the prose `# noqa: B023` *reference* inside an explanatory comment, which ruff
     parses as a directive. It was at `:748` before this increment and is not this
     increment's; it is noise on every `./run-tests` and every edit-time hook run, and the
     fix is one word of comment rewording.

- **Open questions for a future increment:** SPEC §11's four closing-audit questions are
  the queue — (1) does every new helper have a test that reaches it independently of
  `main()`; (2) is R-G4 mechanically checkable (an AST assertion over `main()`'s source is
  the candidate; PD#14 asks whether it can go red) or does it stay prose; (3) with the six
  locals-groups now objects, does D-i12-2's *"a ~25-parameter function"* objection to
  extracting `template_dict` still hold; (4) is `main()`'s 454/318 remainder all stay-list
  content. (4) is answered in CLOSING-AUDIT.md Q1's correction; (1)-(3) are open.

## Amendments — §3.3 stay-list (2026-08-07, post-campaign; applied to CAMPAIGN.md by the entry above)

Five amendments, one per stay-list claim the main-extraction increment made false. Each is
written into CAMPAIGN.md §3.3 as **what is true now**; the "changed after close, and why"
narrative is here, which is the split the amendment mechanism exists to keep — §3.3
describes the shipped architecture in the present tense, the ledger holds the history.
**No architecture changed**: every one of these moves a block *residue* out of `main()`
into a module §3.1 already owns.

1. **A1 — B5.** Before: *"Config/arg bootstrap ordering (B1–B8 — the two-pass substitution
   order is the program)"*, with B5's four argument guards inline. After: the guard
   **bodies** live in `psh.cli.validate_options()` and `main()` keeps the **call sequence**.
   Why the claim survives: §3.3's stated reason for keeping B1–B8 is the substitution
   *order*, which is a property of where the call sits, not of the guard bodies;
   `validate_options()` is invoked from the exact position the guards occupied (after
   `validate_hooks()`, before the verbose banner, after `process_config()` pass 1 — the
   fourth guard reads `sc.config`). The 399-402 sequencing comment stayed at the call site
   for the same reason. §3.1's `psh/cli.py` row already read *"arg validation (B5)"*, so the
   destination needed no amendment — only §3.3's inline-ness did.
2. **A2 — B14.** Before: B14 named in the `B14–B18` stay-range as part of *"the site-loop
   skeleton (skips, banner, sorted order, resume filter)"*. After: roster **resolution**
   (the `org:site:list` fetch, the name→id map, the sort, the `sites_from_resume_point`
   filter, and both `sys.exit` paths) lives in `psh.cli.resolve_site_roster()`; the loop
   skeleton it feeds stays. Why: "sorted order, resume filter" named the *result* the
   skeleton consumes, not the fetch-and-sort that computes it. B14's run accumulators had
   already left at I13 (`RunState`); `smtp_enabled` was **hoisted, not extracted** (SPEC
   §5.4 R5.4.1 — a zero-data-dependency statement move that reorders two `sc.debug` banners
   ahead of `org:site:list`'s own debug line and spinner on every `-v` run; §8 sanctions
   console-text changes freely). `site_count` stays `len(sites)` **before** the resume
   filter — it is the denominator of both the per-site banner and `finish_run`'s "Email sent
   for N of M sites", and it now has a test that goes red if it is "tidied" to
   `len(site_names)`.
3. **A3 — B17.** Before: B17 inside the `B14–B18` stay-range. After: **B17 is off the
   stay-list entirely** — the `resolve_plan_name` call site and the `site["plan_name"]`
   write-back moved into `psh.plans.resolve_site_plan()`, so no B17 content remains in
   `main()`. **This closes a pre-existing internal tension in CAMPAIGN.md rather than
   creating one**, and that is the whole reason it is worth ledgering: §3.1 has assigned
   *"SKU resolution (B17)"* to `psh/plans.py` since the campaign was written, while §3.3
   listed B17 among the IDs staying in `main()`. I7 moved the body and left the call site
   **without amending §3.3** (this ledger's I7 entry: *"`resolve_plan_name` (B17 body incl.
   the Elite check as its early return; `main()` keeps `continue` + tail inits)"*). The two
   sections have disagreed since I7; they agree now. Had this amendment been skipped, §3.3
   would have been false *by definition* after `c47807b` — asserting that a block stays in a
   function no part of it is in.
4. **A4 — B18 (split) + B20.** Before: both inside the stay-range (`BLOCKMAP.md` pairs
   *"Sandbox skip; `SiteContext` creation"* under B18; B20 is the unknown-plan
   `sys.exit`). After: the **Sandbox skip** and **B20** moved into `resolve_site_plan()`;
   the **`SiteContext` creation** stays. Why the split falls exactly there: the skip is
   plan-domain — it reads the plan name the same helper just resolved — whereas the
   constructor's **position** is a documented invariant *of the loop* (CLAUDE.md: *"as far
   up the per-site loop as possible (after the portal/not-requested/Sandbox skips)"*).
   Burying the constructor in a helper hides that invariant from the only code that can
   honor it, and the next skip added would have no local signal about which side of the line
   it belongs on. Folding B20 in also moves the unknown-plan guard **above** the
   constructor; that is behavior-identical, verified at implementation time (not assumed):
   `SiteContext.__init__` is exactly `super().__init__(site=site, notices=[], sections=[],
   attachments=[])` at `script_context.py:115-116` — no console output, no `sc` write, no
   `run_state` write — and on the bail path the object is discarded unread.
5. **A5 — B31 (narrowed).** Before: B31 named under *"phase firing and contract stuffing"*.
   After: B31 on the stay-list means its `stuff_dns_contract` + `invoke_hooks("site_post_dns")`
   **seam**, which stayed inline; the `site_url` derivation that shares B31's baseline line
   range moved into `psh.cli.resolve_site_url()`. Why: `BLOCKMAP.md` lists three things under
   one ID (*"`stuff_dns_contract`; `invoke_hooks("site_post_dns")`; `site_url`"*), and only
   the first two are "phase firing and contract stuffing" — the reason §3.3 keeps B31 at all.
   R-G2 (the stage spine never moves, so `main()` still reads as *fetch → stuff → fire
   phase*) is preserved: `resolve_site_url` is called **after** the phase fires, which is why
   it can read `drupal_multisite_smell` at all.

**Also corrected, in CLOSING-AUDIT.md Q1 — a correction of that document's prose, NOT a
§3.3 amendment.** Q1's stay-list walk discharged the *"Phase firing + contract stuffing
(B27, B28, B31, B37, B52)"* row partly with *"the gather threading + `stuff_gather_contract`
+ `invoke_hooks("site_post_gather")"`* — but the §3.3 row names only **B37**; the gather
threading is B33/B34 (residue)/B35 (residue)/B36 and was never stay-list content. The same
walk lumped `classify_domains` (**B29**, not on the list) together with `stuff_dns_contract`
(**B31**, on it). Both were wrong when written; §3.3 was right. Q1's "NO on the line count"
answer is also superseded there, with the re-measured 454/318 and the D-i14d-1 discharge.

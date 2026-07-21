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

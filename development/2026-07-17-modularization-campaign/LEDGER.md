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

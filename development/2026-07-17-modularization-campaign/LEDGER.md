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

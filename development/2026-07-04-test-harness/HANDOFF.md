# Handoff notes — test-harness implementation (2026-07-04)

What was implemented against `SPEC.md`, and where reality deviated from the plan. This is the
inter-stage record the next stage (the full test suite, then the modularization refactor) should
read together with the code.

## Delivered
- Importability seam refactor (`build_arg_parser()`/`parse_args()`, `sc.options` set in `__main__`).
- pytest harness under `tests/`: conftest (module loader, `reset_sc`, `temp_db`, config fixtures,
  `run_program` interlock, `--llm` reporter), record/replay `terminus` shim, `minimal.toml`/
  `full.toml`, recorded+scrubbed terminus fixtures, golden snapshots, the `./run-tests` wrapper,
  and `tests/tools/record.py`.
- One smoke test per tier plus the bug regressions and the interlock test. `./run-tests --fast`
  and the `live` tier are green; `email` is a skipped scaffold; `render` runs when Chromium is
  installed and otherwise skips with the setup command.
- Docs: README "Testing" section, CLAUDE.md "Testing" section, `tests/README.md`, and the two
  maintenance prompt templates in this folder.

## Deviations from SPEC (decisions taken during implementation)
1. **Two additional bugs fixed beyond the two in §3.1**, both on the non-UMich (reusable) render
   path that production never exercises because U-M always runs with the UMich plugin enabled:
   - `contacts = contacts.replace(",", "")` used `contacts` before assignment (UnboundLocalError)
     in the non-UMich branch → changed to derive from `recipients`.
   - The `# TODO: remove this section in August 2027` block was an unconditional `if True:` that
     read `sc.config["UMich"]` → KeyError for any plugin-disabled/non-U-M run. Guarded it behind
     the `[UMich].enabled` flag (behavior-preserving for U-M). This is the kind of U-M-specific
     coupling the later refactor should move out of the core script wholesale.
   Both were fix-with-tests per the standing decision; the offline e2e is their regression (it
   renders under the plugin-disabled config, which crashed on the pre-fix code).
2. **Offline e2e uses `--date 2026-03-31`** (mid-year). The `end_of_contract_year` path
   (`end_of_contract_year`, June 16–29) is another U-M-specific block; it too read
   `sc.config["UMich"]` unconditionally and was guarded behind `[UMich].enabled` during the
   post-implementation code review (see below), so non-U-M June-dated runs no longer crash. The
   mid-year date is kept for the e2e regardless (deterministic, no annual-billing branch). Traffic
   is seeded deterministically.
3. **`domain:list` fixture reduced to the platform domain** so replay makes no live DNS calls
   (its-wws-test1 has custom domains that would otherwise resolve during "offline" runs).
4. **Coverage subprocess plumbing not wired** (SPEC allowed this as optional). `--coverage` reports
   the in-process tiers only (~10% of the script, since `main()` runs in a subprocess). Documented
   in README/tests-README.
5. **Render tier needs Chromium system libraries** (`libatk`, `libdbus`, …) that require sudo to
   install; not available non-interactively in this container. The render test skips with the
   command `python -m playwright install --with-deps chromium` until they're installed. Everything
   else is green.

## §10 seam-refactor verification (behavior-preserving)
The byte-identity gate was satisfied by: `--help` output byte-identical before vs. after the
refactor; the module now imports cleanly with arbitrary `sys.argv` (previously argparse ran at
import); and `parse_args([...])` yields the same namespace it did before. A full live before/after
`build/` diff was not run because the "before" state predates the refactor and the change touches
only argument parsing (no effect on report generation); the live tier passing end-to-end confirms
downstream behavior.

## Post-implementation code review (high effort)
A `/code-review high` pass over the diff surfaced 10 findings, all fixed:
- **Safety:** the `run_program` interlock only matched exact tokens, so argparse abbreviations
  (`--fo`/`--al`) and short bundles (`-av`) bypassed it. Fixed by adding `allow_abbrev=False` to the
  program's parser and making the interlock check abbreviations + bundles (with tests).
- **Correctness:** the sibling `end_of_contract_year` U-M block was still unguarded (June-date
  non-U-M crash) — now guarded (deviation #2).
- **Cleanup:** `tests/tools/record.py` now imports conftest's helpers and routes through
  `run_program` (no duplication, no un-guarded invoker); a tautological property test was replaced
  with one that exercises the split path; dead fixtures and a hardcoded UUID removed; a
  module-scoped fixture made session-scoped; docstring/assertion fixes.

## Open follow-ups (for the refactor / full-suite stages)
- Move the remaining U-M-specific logic behind `[UMich].enabled` / the umich packages wholesale
  (the two annual-billing blocks are guarded now, but the coupling should be designed out).
- Consider the `recommend_plan(...)` extraction (SPEC §5.10) during the refactor to enable direct
  property tests of the cost model (currently pinned only via the seeded-traffic e2e).
- Wire `COVERAGE_PROCESS_START` if subprocess coverage becomes useful.
- Broaden the golden to a `full.toml`/UMich render once the portal DB / SiteLens can be mocked
  (exercises the SiteLens-gauge CID normalization, deferred per SPEC §9).
- Add a Drupal (`its-wws-test2`) e2e/golden alongside the WordPress one.

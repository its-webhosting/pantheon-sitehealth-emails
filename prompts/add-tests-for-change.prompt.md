# Prompt: add tests for a change

Reusable prompt for keeping the suite current (this project adds tests *with* each change, not
TDD-first). Run this after making a code change, or fold it into the change's own prompt.

---

I just changed `<describe the change / paste the diff>`.

Design and implement the appropriate tests for it, following the existing harness in `tests/`
(see `tests/README.md` and `development/2026-07-04-test-harness/SPEC.md`):

1. Pick the right tier(s) by what changed:
   - pure/in-process logic → `tests/unit/` (add a Hypothesis property test if the function is
     pure and has an invariant worth fuzzing);
   - anything going through `run_terminus`/WP/Drush, the DB, or a check hook → `tests/integration/`
     (monkeypatch `run_terminus`, use `temp_db`);
   - a change visible in the rendered report or the full pipeline → extend the `e2e` run and the
     `golden` snapshot; if it changes real Pantheon interaction, add/adjust a `live` case;
   - a rendering/CSS/template change → the `render` tier.
2. Reuse the existing fixtures (`psh`, `reset_sc`, `temp_db`, `program_runner`, `rendered_report`,
   `minimal_config`). Never invoke the program except via `run_program` (the `--all`/`--for-real`
   interlock), and never run `--create-tables` or `--import-older-metrics` against the live
   database.
3. If the change alters Pantheon responses the offline e2e depends on, refresh fixtures with
   `./run-tests --record` and review the diff. If it intentionally changes rendered output, run
   `./run-tests --update-goldens` and review the snapshot diff.
4. Run `./run-tests --fast` (and the relevant `live` cases) and confirm green. Show the output.

Keep any institution-specific logic behind config flags / the `umich` plugin+check packages so the
non-UMich path keeps working.

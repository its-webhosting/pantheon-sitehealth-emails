# Prompt: backfill tests for existing untested code

Reusable prompt for **covering code that has no tests** — code written before this project
adopted test-first development, or otherwise inherited. CodeGraph reports "no covering tests
found" across much of the core program; this prompt is how that debt gets paid down.

**This is NOT the path for new work.** New work is test-first at the seams the spec declares
(`mattpocock-skills:tdd`, see `prompts/implementation-standards.md`) — tests that "didn't get
added during development" are a mandate violation to fix at the source, not to launder through
this prompt. Writing tests in bulk against code that already exists is
[horizontal slicing](../prompts/implementation-standards.md): the tests verify what the code
*does* rather than what it *should* do, and they never had a chance to catch the bug. That is
an acceptable price for covering untested legacy code, and not for anything else.

Because these tests cannot go red first, be adversarial in the one way that's still available:
for every assertion, ask whether it would **fail** if the behavior were wrong, and derive the
expected value from an independent source of truth — the spec, a worked example, a known-good
literal — never by rerunning the code and pasting what it printed.

---

I want to backfill tests for `<name the untested function/module/path>`.

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

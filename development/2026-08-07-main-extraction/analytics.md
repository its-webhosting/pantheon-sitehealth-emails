# Analytics — main() extraction (2026-08-07)

_Your narrative: what went well, what to do differently, decisions worth remembering._

Factual anchors, so they aren't lost when the session is (see `statistics.md` for the
machine-generated numbers, and `LEDGER.md` for the campaign record):

- `main()` 622 raw / 445 logic → 462 raw / 318 logic; six helpers across four modules;
  tests 1743 → 1824; four e2e goldens byte-identical across all 11 commits.
- Run as 8 SDD tasks + 1 final fix wave. Reviews found real defects, not style: the SPEC's own
  prescribed Invariant-8 assertion (`startswith(" " * 16)`) passes on 17 spaces and would have
  shipped the golden-literal instrument green against the defect it exists to catch; and the
  composition glue left in `main()` had no instrument at all — two injections left 1818 tests
  green.
- Three findings were only catchable across task boundaries (stale `CLAUDE.md` prose, the
  mis-triaged ruff warning, the uninstrumented glue), which is the argument for the
  whole-branch review existing at all.
- A "swept, found N" claim undercounted **three separate times** in this increment.

Open questions worth a view:

- Was the per-task adversarial review worth its cost here (`/usage`: $136, 70% of it subagents
  under `subagent-driven-development`)? Tasks 5 and 6 drew zero findings; Tasks 0, 3 and 7 drew
  substantive ones.
- Model mix: implementers ran sonnet except Tasks 0/3/7 (opus); reviewers sonnet except Tasks
  0/3 and the final (opus). Did the cheaper tier miss anything the expensive tier caught?

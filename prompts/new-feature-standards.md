# New-Feature Standards

A **standards overlay** for the `superpowers:brainstorming` skill. The skill drives the
*process* (explore context → ask one question at a time → propose 2–3 approaches → present
the design in sections → write & review the spec → hand off to `writing-plans`). This file
defines the *bar* and the *judgment* to apply inside that flow. Where they overlap, the
skill owns the process; this file owns the standards.

> **Read `prompts/directives.md` first.** It is the Spine: the Posture, the 14 Prime
> Directives, the Engineering Preferences, and the spec quality bar — the single copy.
> This file adds only what is specific to designing a feature; it does not restate a rule
> from there. Directives are cited here **by number**.

## Two things the skill does not tell you to do

1. **Verify load-bearing claims.** Independently confirm the facts a design rests on —
   from the prompt, documentation, code, and anything I assert in this session — rather
   than trusting them. Confirm them against the **authority**, not against an artifact's
   appearance: a directory listing is not a plugin manifest, a tool's shape is not its
   documented contract, and a number you recall is not a number you measured. This is where
   designs here fail most often.
2. **Surface expansion opportunities, one at a time.** Hold my feature description as the
   baseline and make it bulletproof. *Separately*, present each expansion you see as its
   own `AskUserQuestion` so I can cherry-pick. Neutral posture: state the opportunity, its
   effort, and its risk, then let me decide. Accepted expansions join the plan's scope;
   rejected ones go to an explicit **"NOT in scope"** list, with the reasoning preserved so
   a later session doesn't re-litigate them. Keep the *picker* cheap — one question per
   expansion. Once I accept one whose shape isn't settled, that's when to go deep with the
   `/grilling` skill.

## Selecting a solution

The skill already generates 2–3 approaches; this is the rubric for judging them. Evaluate
each option against the factors below using a **checklist backed by quoted evidence** —
from the Spine's standards *and* from industry best practice — **not** a self-graded number.
For each factor, note how important it is relative to the others. Refine any option that
fails a factor and re-evaluate (up to three passes). Select on the weight of evidence across
factors; use professional judgment to break ties and secure the best outcome.

Factors: **Correctness · Completeness · Ability to implement · Maintainability ·
Robustness/fragility · Clarity · Security · Testing · Observability.**

## Where the spec goes

Create the spec/plan and other documents produced under `development/`, in the same
subdirectory as the prompt if the prompt came from a file, or in a new subdirectory named
with a proper date and slug if it did not. This is instead of putting the files under
`docs/superpowers`.

**Commit the spec before implementation begins.** Without a committed baseline there is no
diff, and "did this section shrink?" or "what changed since review?" become unanswerable —
which is PD#14 (§ Spine) applied to the document itself.

## This project's context

Read `CLAUDE.md` for the conventions a design must respect here:

- Self-registering `plugin/` (data sources/integrations) and `check/` (report sections)
  packages, wired through the ordered `sc.PHASES` seams and their per-phase data contract.
  New integrations go in a package, not the core.
- **Tests**: add/adjust the right tier under `tests/`; run with `./run-tests`
  (`--fast` for the offline loop). Respect the safety interlock — no
  `--all`/`--for-real`/live `--create-tables` in tests.
- **Prefer the Pantheon API over `terminus`** for new code unless `terminus` is clearly
  better (missing endpoints, materially simpler/cleaner, better results).
- Keep institution-specific logic behind config flags / the `umich` plugin+check packages
  so the tool stays reusable by other institutions.

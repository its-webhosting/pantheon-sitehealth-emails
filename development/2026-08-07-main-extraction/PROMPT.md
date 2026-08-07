# Prompts — 2026-08-07 main() extraction

The two prompts that drove this session, verbatim. Both were typed in-session rather than
supplied as files, so they are transcribed here for the record.

## 01 — the question that started it (plan mode)

> Read the function `main()` in `psh/cli.py`. Is there any code in that funciton that software
> engineering best practices dictate be refactored into their own functions, files, modules, or
> packages?  The goal is to have the code be understandable, properly structured, and
> maintainable; we **are not** trying to hit any arbitrary function-length or file size target.

Answered with the analysis that became `PLAN.md`, after three `AskUserQuestion` rounds that
settled: **Tier 1 + 2** scope (six extractions, not the `template_dict` stretch), **`main()`
keeps the phase-firing spine** (bodies move, `stuff_*_contract`/`invoke_hooks` stay inline), and
a **full campaign increment** (SPEC + CAMPAIGN.md amendment + LEDGER entry) rather than a
lighter change.

## 02 — the implementation instruction

> Use the superpowers:subagent-driven-development skill in auto mode to implement everything in
> the plan while adhering to everything in prompts/implementation-standards.md.

One further decision was taken before dispatch, via `AskUserQuestion`: CLAUDE.md says *"Only
branch if explicitly directed to do so"* while the SDD skill says *"Never start implementation
on a main/master branch without your human partner's explicit consent."* The user chose **work
directly on `main`**, which is the explicit consent the skill requires.

## Not supplied as prompts

No `design-notes/` were produced. The eight per-task briefs and the review/fix findings live in
the session's gitignored SDD workspace
(`.superpowers/sdd/read-the-function-main-fancy-kahan/`); the durable half of that record was
landed into `LEDGER.md`, `CLOSING-AUDIT.md`, `README.md` and `SPEC.md` §10a by Task 7 and the
final fix wave.

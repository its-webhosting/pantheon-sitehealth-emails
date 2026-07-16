# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`CLAUDE.md`** at the repo root — **always, and first**. This is the source of truth for *how the program is built*: the `sc.PHASES` seams and their per-phase data contract, `SiteContext`, notices vs. news, the plugin/check packages, the DB-resilience and rich-console rules. Read it before exploring and use its terms exactly.
- **`CONTEXT.md`** at the repo root — the **domain glossary**, once it exists (see the split below).
- **`CONTEXT-MAP.md`** at the repo root if it exists — it points at one `CONTEXT.md` per context. Read each one relevant to the topic.
- **`docs/adr/`** — read ADRs that touch the area you're about to work in. In multi-context repos, also check `src/<context>/docs/adr/` for context-scoped decisions.

## The split: CLAUDE.md vs. CONTEXT.md

They do not overlap, and neither replaces the other:

| | Holds | Owner |
| --- | --- | --- |
| **`CLAUDE.md`** | Implementation and architecture — seams, contracts, gotchas, conventions, house style | Hand-maintained; `prompts/update-claude-md.md` |
| **`CONTEXT.md`** | Domain vocabulary **only** — what a *Site*, *Plan*, *Notice*, *News item*, or *Report* **is**, in the language the team speaks | `/domain-modeling`, lazily |

`/domain-modeling` is explicit that `CONTEXT.md` is "totally devoid of implementation details... a glossary and nothing else" — so a phase table, a data contract, or a retry rule **never** goes there; it belongs in `CLAUDE.md`. Conversely, when a *term* gets sharpened or challenged, that lands in `CONTEXT.md`, not `CLAUDE.md`.

**`CLAUDE.md` is not optional and its absence is not silent.** A skill that says "read `CONTEXT.md` to get a mental model of the modules" means `CLAUDE.md` here — the modules are documented there. Skills that "proceed silently" on a missing glossary would otherwise skip the whole architecture.

For `CONTEXT.md`, `CONTEXT-MAP.md`, and `docs/adr/` specifically: if they don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. `/domain-modeling` creates them lazily when a term or decision actually gets resolved — see Prime Directive #11 in `prompts/new-feature-standards.md`, which is what triggers it under this repo's `superpowers` host.

## File structure

This repo is **single-context**:

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-example-decision.md
│   └── 0002-another-decision.md
└── ...
```

Multi-context layout, for reference (signalled by a `CONTEXT-MAP.md` at the root):

```
/
├── CONTEXT-MAP.md
├── docs/adr/                          ← system-wide decisions
└── src/
    ├── ordering/
    │   ├── CONTEXT.md
    │   └── docs/adr/                  ← context-specific decisions
    └── billing/
        ├── CONTEXT.md
        └── docs/adr/
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (event-sourced orders) — but worth reopening because…_

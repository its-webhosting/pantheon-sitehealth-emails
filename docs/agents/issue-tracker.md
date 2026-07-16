# Issue tracker: Local Markdown

Issues for this repo live as markdown files in `.scratch/`.

## Specs do NOT live here — read this first

**`development/<YYYY-MM-DD-slug>/` is the canonical home for specs and plans**, per `prompts/new-feature-standards.md` ("Create the spec/plan and other documents produced under `development/`"). That convention predates this file, is a committed historical record with its own rules (scrubbed transcripts, `development/finalize-session.py`, committed in the same commit as the code it documents — see `development/README.md`), and **takes precedence**.

So where a skill says "write the spec to the issue tracker," write it to `development/<YYYY-MM-DD-slug>/SPEC.md` instead. `.scratch/` holds working state only: ticket files and wayfinding maps, which are ephemeral and gitignored. When an effort concludes, its durable output belongs in `development/`.

The split, stated once:

| Artifact | Home | Committed? |
| --- | --- | --- |
| Spec / plan | `development/<YYYY-MM-DD-slug>/` | Yes — it's the archive |
| Tickets, wayfinding maps | `.scratch/<feature-slug>/` | No — gitignored working state |

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- Implementation issues are one file per ticket at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01` — never a single combined tickets file
- Triage state is recorded as a `Status:` line near the top of each issue file (see `triage-labels.md` for the role strings)
- Comments and conversation history append to the bottom of the file under a `## Comments` heading

## When a skill says "publish to the issue tracker"

Create a new file under `.scratch/<feature-slug>/` (creating the directory if needed) — **unless the artifact is a spec or plan**, which goes to `development/<YYYY-MM-DD-slug>/` as above.

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path or the issue number directly.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a file with one **child** file per ticket.

- **Map**: `.scratch/<effort>/map.md` — the Notes / Decisions-so-far / Fog body.
- **Child ticket**: `.scratch/<effort>/issues/NN-<slug>.md`, numbered from `01`, with the question in the body. A `Type:` line records the ticket type (`research`/`prototype`/`grilling`/`task`); a `Status:` line records `claimed`/`resolved`.
- **Blocking**: a `Blocked by: NN, NN` line near the top. A ticket is unblocked when every file it lists is `resolved`.
- **Frontier**: scan `.scratch/<effort>/issues/` for files that are open, unblocked, and unclaimed; first by number wins.
- **Claim**: set `Status: claimed` and save before any work.
- **Resolve**: append the answer under an `## Answer` heading, set `Status: resolved`, then append a context pointer (gist + link) to the map's Decisions-so-far in `map.md`.

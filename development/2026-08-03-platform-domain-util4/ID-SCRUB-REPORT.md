# Cloudflare id scrubbing in `development/finalize-session.py`

**Status:** DONE
**Commit:** `fb973ee5241680bcd0f59ee500d84a17e13cfb5e` — `feat(finalize-session): scrub Cloudflare
zone and record ids from transcripts` (on `main`, not pushed)
**Files changed:** `/workspace/development/finalize-session.py` (+68),
`/workspace/tests/unit/test_finalize_session.py` (+118)

## What shipped

Two module-level constants and one function in `development/finalize-session.py`, called as the
first statement of `scrub()`:

- `_CF_ID_ANCHORS` — six `(kind, pattern)` pairs, one per observed anchor, each with a single
  capture group holding the 32-lowercase-hex id. Three classify as `zone` (`zone <id>` in the
  applier's per-entry report line, `"zone_id": "<id>"`, `/zones/<id>/`), three as `record`
  (`"record_id": "<id>"`, `"id": "<id>"` in a batch `deletes` item, `id=<id>` from SDK output).
- `_CF_ID_PLACEHOLDER` — `«cf-{}-id-{:02d}»`, matching the scheme
  `development/2026-08-03-platform-domain-util4/transcript.md` was hand-scrubbed with.
- `_scrub_cloudflare_ids(text)` — pass 1 walks every anchor with `re.finditer`, sorts the hits by
  the **position of group 1** and builds `{id -> placeholder}`, numbering from 01 per kind by
  first appearance (first-seen wins if one id reaches both kinds); pass 2 replaces every
  occurrence of each mapped id anywhere in the text with one alternation `re.sub`.

Design points worth restating because they were constraints, not choices:

- **The anchored hole is deliberate.** 32-lowercase-hex is the class the existing high-entropy
  rule spares on purpose (its own comment: "it excludes git SHAs (all-lowercase hex), which a
  development transcript must keep readable"). A blanket `\b[0-9a-f]{32}\b` would destroy the
  md5sum `b68ec92d16467c767152ac42a085acfe` that this very session's transcript quotes as a
  digest. So the rule is anchored to the six measured contexts and generalized no further.
- **Two passes.** An id that appears under an anchor once and in bare prose twice ("the record id
  was X, is now Y") must go in all three places; a single anchored `re.sub` leaves the prose
  behind. Mutation M8 below shows exactly that.
- **Idempotence** falls out of the placeholder shape: `«cf-zone-id-01»` contains no 32-hex, so a
  second `scrub()` finds nothing to map and returns the text unchanged.
- **Known and accepted, documented in the code comment:** a *synthetic* id sitting under a real
  anchor inside a quoted code snippet (`"record_id": "9f1c0000000000000000000000000000"`) will be
  scrubbed. Over-scrubbing invented data costs a little transcript fidelity; under-scrubbing a
  real id publishes infrastructure on a public repo.

Placement: inside `scrub()`, i.e. "wherever `scrub()` is already applied" — the committed
`transcript.md` and `statistics.md`. `transcript.raw.md` is written from the unscrubbed text and
stays raw. No separate pass was added anywhere else.

## Tests — 16 added, all watched red first

`/workspace/tests/unit/test_finalize_session.py`, new section
`--- scrub(): Cloudflare zone / record ids ---`, plus three entries appended to the existing
`test_scrub_leaves_readable_text_alone` parametrize.

Expected values are hand-derived from the placeholder scheme the committed transcript already
uses — never from running the script, per that file's backfill header convention.

| Test | Covers |
|---|---|
| `test_scrub_replaces_a_cloudflare_id_under_each_anchor` (6 cases) | each anchor, positively; zone-vs-record classification |
| `test_scrub_replaces_a_mapped_id_in_bare_prose_on_both_sides_of_its_anchor` | the two-pass property |
| `test_scrub_gives_one_id_one_placeholder_and_two_ids_two_placeholders` | stability + distinctness |
| `test_scrub_numbers_zone_and_record_ids_on_separate_counters` | one counter per kind |
| `test_scrub_settles_an_id_matching_two_anchor_kinds_on_the_one_seen_first` | first-seen wins |
| `test_scrub_is_idempotent_over_cloudflare_ids` | idempotence over the new rule specifically |
| `test_scrub_treats_a_credential_and_a_cloudflare_id_in_the_same_text` | interaction: both treated, md5sum untouched |
| `test_every_cloudflare_id_anchor_compiles_with_one_capture_group_and_a_known_kind` | the anchor table's shape |
| `test_scrub_leaves_readable_text_alone` (+3 cases) | negatives: md5sum, 40-char git SHA after `zone`, prose field name |

Red-first evidence: with the tests written and no implementation,
`python -m pytest tests/unit/test_finalize_session.py` reported **13 failed, 70 passed** — the 13
being all new positive tests, failing on "the id survived" and `AttributeError: module ... has no
attribute '_CF_ID_ANCHORS'`, i.e. for the right reason. The three appended negatives could not go
red before the implementation existed (they guard against over-reach), which is why M9 and M10
below exist.

## Mutation verification (PD#14)

Each mutation applied to the production code alone, full file suite run, code restored (verified
byte-identical to the pre-mutation backup afterwards).

- **M1** removed the `zone <id>` anchor → RED: `…under_each_anchor`, `…one_placeholder…`,
  `…separate_counters`, `…seen_first`
- **M2** removed the `"zone_id": "…"` anchor → RED: `…under_each_anchor`
- **M3** removed the `/zones/<id>/` anchor → RED: `…under_each_anchor`
- **M4** removed the `"record_id": "…"` anchor → RED: `…under_each_anchor`, `…bare_prose…`,
  `…separate_counters`
- **M5** removed the `"id": "…"` batch-deletes anchor → RED: `…under_each_anchor`,
  `…is_idempotent_over_cloudflare_ids`
- **M6** removed the `id=<id>` SDK anchor → RED: `…under_each_anchor`
- **M7** made numbering unstable (dropped the `if cf_id in mapping: continue` dedupe) → RED:
  `…one_placeholder…`, `…is_idempotent…`, `…seen_first`, `…credential_and_a_cloudflare_id…`
- **M8** dropped the second pass (replaced only at the anchors) → RED:
  `…replaces_a_mapped_id_in_bare_prose_on_both_sides_of_its_anchor`
- **M9** widened the first anchor to bare `\b([0-9a-f]{32})\b` → RED:
  `test_scrub_leaves_readable_text_alone` (the md5sum case), plus `…under_each_anchor`,
  `…bare_prose…`, `…one_placeholder…`, `…separate_counters`, `…is_idempotent…`,
  `…credential_and_a_cloudflare_id…`
- **M10** dropped the trailing `\b` from the `zone <id>` anchor → RED:
  `test_scrub_leaves_readable_text_alone` (the 40-char git SHA after `zone`)

No mutation stayed green.

## Verification

```
$ ./run-tests --fast
All checks passed!                      # ruff 0.15.22, merged config
0 errors, 0 warnings, 0 informations    # pyright 1.1.411
...
107 snapshots passed.
========= 1741 passed, 3 skipped, 2 deselected, 15 warnings in 41.60s ==========
EXIT=0
```

Baseline was 1725 passed / 3 skipped / 2 deselected; +16 is exactly the number of tests added.

## Directives applied

- **PD#14 — "Your instruments can lie."** *"A green check is a claim, not evidence, until it has
  been shown capable of going red on the condition it guards."* Every new test was watched fail
  first, and the three negatives — which structurally cannot fail before the feature exists — were
  pinned by mutations M9 and M10 instead.
- **PD#6 — "Security is not optional."** *"New code paths get threat-modeled."* The threat here is
  publication, not authentication: this repo is public and the transcript is the publication
  channel, so the rule is written to fail toward over-scrubbing (a synthetic fixture id under a
  real anchor is scrubbed) rather than toward a leak.
- **PD#1 — "Zero silent failures."** *"A failure that can happen silently is a critical defect."*
  The failure mode this closes is silent by construction — an unscrubbed id ships green — so the
  cover is the mutation set above, not a runtime check.
- **PD#3 — "Data flows have shadow paths."** *"Every flow has a happy path plus three shadows: nil
  input, empty/zero-length input, and upstream error."* Empty/no-match input returns the text
  unchanged via the `if not mapping` early return (exercised by every pre-existing negative and by
  the whole rest of the suite, which passes text with no ids through `scrub()`); there is no
  upstream-error shadow because the function is pure string work over already-read text.
- **PD#8 / implementation-standards §7 — diagrams.** No diagram added: the flow is local to one
  function in one file, and the standard requires one in code only "where the flow is non-local
  (spans files, packages, or phase seams)". The two-pass structure is documented in the docstring
  instead.
- **Engineering Preferences — "Explicit over clever."** The anchor table is six literal patterns
  with a comment each naming the tool output it was observed in, not one generalized regex.
- **Karpathy §2, "Minimum code that solves the problem. Nothing speculative."** No flag, no config
  key, no way to turn it off; two constants and one function.

## Concerns

1. **`development/README.md`'s manual-grep backstop is now incomplete, but not wrong.** That grep
   is keyed to credential names (`AKIA…`, env-var names) and says nothing about infrastructure
   ids. Nothing it states became false, so per the dispatch I did not edit it — but an operator
   following it will not catch an id the anchors missed. If you want a backstop for this rule, the
   grep to add is `grep -nE '\b[0-9a-f]{32}\b' transcript.md` reviewed by eye (it will hit
   md5sums, which is the point of reviewing rather than scrubbing).
2. **Anchors are a denylist, and the spec quality bar prefers exhaustive lists.** These six are
   exhaustive *of what was observed*, not of what Cloudflare output can look like. A future
   utility printing an id in a seventh shape publishes it. Concern 1's grep is the honest
   mitigation; widening the rule is not, for the md5sum reason.
3. **`ID-SCRUB-REPORT.md` is written but deliberately not committed.** The commit contains only
   the scrubber and its tests; `development/2026-08-03-platform-domain-util4/` is the session
   archive I was told not to disturb, and sweeping this file into the same commit as a code change
   would mix the two. Commit it with the archive if you want it tracked.

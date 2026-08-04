# Fix pass 2 — `apply-platform-domains-cloudflare`, review findings 3–11

**Status: DONE.** All nine findings addressed: seven fixed, two documented as the reviewer asked,
none silently skipped and none declined outright. Every behavioral change was written test-first,
watched fail for the right reason, and mutation-verified. Four commits on `main` (no branch, not
pushed):

| Commit | Findings | Kind |
|---|---|---|
| `3022585` | 3, 11 | behavioral + the SPEC/CLAUDE.md that govern them |
| `6e4b350` | 5, 10 | behavioral + SPEC/CLAUDE.md |
| `1d7274d` | 7, 8 | behavioral + SPEC |
| `a77c3a2` | 4, 6, 9 | documentation only |

No `--for-real` invocation and **no live Cloudflare API call of any kind**. The two offline
acceptance items that run the script (§15 items 4 and 5) were executed; §15 item 6 is a live dry run
and was deliberately **not** re-run — see finding 6 below. The
`apply-platform-domains-cloudflare.py` symlink was not touched; only the extension-less real file
was edited. Nothing was imported from `psh/`, `check/`, `plugin/` or `script_context`, and nothing
was modularized. Both sibling scripts and both sibling test files are byte-identical
(`git diff --stat` empty against the working tree **and** against `33b2ba8..HEAD`).

---

## Finding 3 (IMPORTANT) — `proxied` invisible to `verify_records` and to `already-applied`

**Fixed.** This was the centerpiece and the only finding with production consequence.

### The design, and why this one

`record_key` is `(TYPE, normalize(name), canonical_content)` and **must stay that narrow**: it is
compared against `delete_match`, whose items are `{type, name, content}` only, because Cloudflare's
batch `deletes` accepts nothing but `{"id": …}`. The reviewer's "do not widen `record_key`" is
right, and I adopted it. But the consequence nobody had traced is stronger than "a field is
missing": narrowing the key for a structural reason left `proxied` **homeless** — read by no code
at all — which is why both instruments agreed a DNS-only replacement was correct.

So the check sits **beside** the key, as one pure helper `proxy_status_mismatches(posts, rows)`
returning a list of human-readable disagreements, called from exactly the two places that compare
**R against P**:

| Place | On disagreement |
|---|---|
| `verdict_for`'s `have == want_post` row | new **invalid** verdict `proxy-status-drift` → the whole run aborts at exit 2, nothing changed |
| `verify_records` (R6.1) | `False` → `VerifyError` → outcome `unverified` → **exit 3** |

**The delete side is deliberately not checked**, and that is stated in the code, the SPEC and
CLAUDE.md: a `ready` verdict means R == D, those records are about to be deleted, and
`delete_match` carries no `proxied` to compare against. So `record_key`'s other three consumers —
the ambiguity, partially-applied and unexpected-records rows — are untouched, which was the blast
radius to protect.

**Why a new verdict rather than demoting to `records-missing`.** PD#2: the operator's only
instrument here is the `ATTENTION: <fqdn> <verdict>: <detail>` line, and `records-missing` would
tell them Cloudflare does not hold the records when it holds exactly them. `proxy-status-drift`
names the actual state and its detail names *which* record and *which* direction. It needed no new
code path: `abort_on_invalid_entries` and `apply_all` both test `not in ("ready",
"already-applied")`, so a new verdict is invalid by construction.

**Why `unverified` and not `failed` on the verification side.** The batch returned, so Cloudflare
committed something; the something is not what the file asked for. That is exactly what R6.3's
`unverified` outcome and exit 3 exist for. The message is a **separate sentence** from the content
mismatch — "does not hold the expected records" would be false when it holds precisely those
records, and would send an operator hunting a content difference that is not there.

**`None` is a mismatch, not a pass.** `proxied` is `Optional[bool]` on every SDK record model and
the sibling excludes a null swept status as `unknown-proxy-status` because *"guessing either way is
unsafe"*. It gets its own wording — "has an UNKNOWN (null) proxy status" — because rendering it as
"DNS-only" would be a claim this script cannot make. Asserted both ways: the drift detail for a null
must contain the UNKNOWN sentence and must **not** contain "DNS-only".

**Two mechanical extractions were forced, and are part of the change, not gold-plating.** Adding
row 3a pushed `verdict_for` to C901 11 > 10 and PLR0911 7 > 6, both hard lint gates. The duplicate
block became `duplicate_key_detail(present, keys)` and rows 4–6 became `mismatch_verdict(have,
want_delete, want_post)`; every message is unchanged, and what remains in `verdict_for` is exactly
"which set does R equal", which is what SPEC §7.2 says the decision is.

### Fixture work (the failure class SPEC §22 names)

The test file's `row()` helper had **no `proxied` attribute at all**, so no fixture in 215 tests
could distinguish a proxied record from a DNS-only one. It now carries `proxied=True` by default
(matching `plan_entry()`'s posts and what the SDK really returns) and the new tests vary it
deliberately:

- **one of two records DNS-only** — the detail must name the AAAA and must **not** name the A, so a
  "flag the whole entry from the first record you look at" implementation fails;
- **both drift directions** — a revert file's DNS-only post against a proxied live record, so a
  one-way `if want and not held` test fails;
- **`None`**, parametrized alongside `False` on the verification side.

### Red first

```
FAILED …test_verdict_already_applied_requires_every_records_proxy_status_to_match
FAILED …test_verdict_proxy_status_drift_on_an_unknown_null_proxy_status
FAILED …test_verdict_proxy_status_drift_when_the_file_asks_for_dns_only
FAILED …test_verify_records_rejects_a_replacement_in_the_wrong_proxy_status[False]
FAILED …test_verify_records_rejects_a_replacement_in_the_wrong_proxy_status[None]
FAILED …test_verify_records_rejects_a_proxied_record_where_the_file_asks_for_dns_only
FAILED …test_a_batch_that_leaves_the_records_dns_only_is_unverified_never_applied
FAILED …test_a_rerun_over_an_unproxied_record_refuses_instead_of_reporting_already_applied
8 failed, 217 passed
```

The end-to-end re-run test failed with `assert 1 == 2` — i.e. the run really did exit **1**,
"already applied", over a record someone had un-proxied. That is the finding's scenario (a),
reproduced through `main()`.

---

## Finding 4 (IMPORTANT) — `max_retries=0` recorded in no governing document

**Documented** (no code change; the property is already correct and already tested).

Verified against the **installed** SDK rather than any docstring:

```
.venv/lib/python3.13/site-packages/cloudflare/_constants.py:10:DEFAULT_MAX_RETRIES = 2
.venv/lib/python3.13/site-packages/cloudflare/_base_client.py:815: def _should_retry(self, response)
    -> 408, 409, 429, >=500, plus the x-should-retry header.  NO HTTP-method check.
```

So the SDK's default is 2 retries and it will retry a `POST .../dns_records/batch` exactly as it
retries a `GET`. Recorded in:

- **SPEC §17** — the table row now says "**Two** deliberate divergences", and a new *Divergence 1*
  paragraph carries the measurement, the non-idempotency reasoning, why losing retries on pass-1
  reads is the safe direction of the same change, and the two tests that pin it (the constructor
  assertion **and** the real `httpx.MockTransport` one-POST-on-a-429/500 test). The two "status of
  the other copies" rows now say explicitly that neither sibling pins retries, and why not.
- **CLAUDE.md** — a new paragraph beside the "only copy that performs writes" sentence, plus an
  explicit statement that **the three `build_client()` copies are no longer identical** and what
  each one does differently, so the "three places to check" note is actionable rather than
  misleading.

---

## Finding 5 (IMPORTANT) — `generated.zones_swept`/`zones_total` ignored

**Fixed.** Field names and semantics confirmed against the sibling's `provenance()`
(`find-platform-domains-cloudflare:900-929`) and its `Sweep` NamedTuple: two integers,
`zones` (actually swept) and `zones_total`, emitted *"so an applier can verify the assumptions the
file was built under"*.

### Warn, not refuse — and the justification against SPEC's under-reporting posture

The brief asked me to decide and justify. **Loud unconditional stderr `ATTENTION` plus both numbers
in the run record; no refusal.** The distinction I drew, and wrote into SPEC §6a:

> This script refuses what is wrong about **this invocation** — an `--only` name matching nothing,
> an `-excluded.json` — because those are typos an operator fixes by retyping, and a typo that
> silently narrows a destructive run is the under-reporting failure R7.3 exists to prevent. A
> partial or elderly file is a **valid artifact** whose correct use is the operator's judgment;
> CLAUDE.md documents `-o /tmp/one-zone engin.umich.edu` as a workflow, so refusing it would need an
> override flag — more surface on a script scheduled for deletion, and one more thing to pass by
> reflex. What this script owes the operator is that the judgment cannot be made **unknowingly**.

The cross-zone-duplicate hazard the brief flagged is named **in the warning text itself**, because
it is the part an operator would not otherwise infer from "1 of 187 zones".

Coverage that **cannot be verified** (fields absent, or not integers — a `bool` is deliberately not
an integer here, since `zones_swept = true` must not read as one zone) gets its own warning. Silence
there would be ambiguous between "complete sweep" and "no idea", which is PD#1's shape exactly.

`run.source_zones_swept` / `run.source_zones_total` are written on **every** run, not only the
alarming one — a field recorded only when it is alarming cannot be audited for the case it exists to
prove — and there is a separate test for the complete-sweep case for exactly that reason.

---

## Finding 6 (IMPORTANT) — stale acceptance evidence

**Fixed by re-running, not by editing numbers.** SPEC §15's results block is replaced wholesale and
now names the commit it was run at (`1d7274d`) and the eight code commits that had landed since the
old block was pasted.

Items 1–5 were run and pasted verbatim. Item 3 was run twice (working tree and `33b2ba8..HEAD`),
both empty. Item 5 was previously *summarized* ("Documents `FILE`, `--only` …"); it is now the real
`--help` output.

**Item 6 could not be run offline, and that is stated rather than papered over.** It is a live dry
run against the real 217-entry baseline: read-only, but it makes real Cloudflare API calls, which
this brief forbids without exception. The old result is retained, **dated, and attributed to
`250e517`**, with the three things now known to be false of it spelled out — notably that its 217
`ready` verdicts predate §7.1a, so a `proxy-status-drift` entry among them would have validated
`ready`. Re-running it is the cheapest available check of the new code against production state and
is read-only; I have flagged it as a concern rather than doing it.

§22 answer 7's four numbers were re-measured with the commands it quotes: **2082** script lines,
**65** top-level defs/classes, **3794** test lines, **247** tests.

---

## Finding 7 (MINOR) — a raise from `finish()`'s prologue exits 1

**Fixed.** The reviewer's reproduction is exact, and the fix needed **two** guards, not one: the
prologue is only half the exposure. `main()`'s `except` clauses evaluate `failure_code(state)`
*before* calling `finish()`, and `failure_code` calls `tally` too — so the same `InvariantError`
escapes from the argument expression, before `finish` is even entered.

- `finish()`'s whole body is enclosed (delegating to `finish_reporting()` so the existing sequence
  needs no re-indentation) and returns `code` unchanged on anything unrecognised. `code` was
  computed by the caller, so it is the honest answer: **a bookkeeping failure while reporting a run
  does not change what the run did.**
- `except BaseException`, not `Exception`, and deliberately: SIGINT is `SIG_IGN` by the first
  statement, so the only `KeyboardInterrupt` that can reach the guard arrives in that
  one-statement window — swallowing it is precisely what the `SIG_IGN` line exists to do.
- `failure_code()` is now total, falling back to `state["for_real"]` rather than a flat code. That
  is the one fact still trustworthy when the tally is not: there is exactly one
  `dns.records.batch` call site and it sits behind the `--for-real` branch, so a dry run
  **structurally** cannot have changed anything (2 is true of it) while a for-real run may have (3).
  A flat `3` would lie about a dry run; a flat `2` would lie about the run that had just POSTed.

Red first, and the traceback was the reviewer's own:

```
/workspace/apply-platform-domains-cloudflare:1191: in failure_code
    return 3 if changed_count(tally(state["outcomes"])) else 2
E   InvariantError: contrived bookkeeping defect
```

— raised inside `except StartupError`, escaping `main()`.

---

## Finding 8 (MINOR) — `report_entries`' `continue` unpinned

**Fixed.** The existing mixed-document test now asserts the §11.4 change line is **absent** for the
already-applied entry and **present** for the ready one (an absence assertion is the only shape that
can catch an *extra* line), and a new `-v` variant covers the same document. Under `-v` the missing
`continue` additionally reaches `merge_body(entry, [])` — an already-applied verdict resolves no
delete ids — and turns an exit-1 run into an `InvariantError` at exit 2, so the `-v` test asserts
the exit code and both `POST` lines by zone id.

These two tests pass the moment they are written, which is structural for a regression guard over
correct behavior; their red demonstration is mutation M13 below.

---

## Finding 9 (MINOR) — "three real subprocess tests"; there are four

**Documented.** Counted directly (`run_apc_in_a_subprocess` call sites plus the `1>&-` shell test):
four. CLAUDE.md now says four and names
`test_a_doomed_stdout_during_the_flush_still_exits_a_named_code_not_crashing`, with one sentence on
why it is a distinct instance of the class — a doomed stdout first hit **inside `finish()`**, itself
called from inside one of `main()`'s own `except` clauses — and how it is reproduced (a nonexistent
`FILE`, so `finish()`'s summary print is the first stdout write attempted).

---

## Finding 10 (MINOR) — nothing warns on a stale plan

**Partly accepted, and the declined part is recorded.** The reviewer explicitly is *not* asking for
re-resolution and concedes §20 declined it deliberately. I decline re-resolution **again** — the
DNS-dependency reasoning in §20 and §16 is unchanged and I found nothing to weaken it — and I accept
the narrower argument, which I think is correct:

> Validation compares R against **D** (the CNAME), so a plan whose **P** addresses have gone stale
> validates perfectly `ready` and then writes the wrong addresses.

That is true of the code as written, and the project's own recorded knowledge is that Pantheon
rotates those address sets. So §11.3's claim that printing `generated.at` is a sufficient staleness
signal was overstated, and the age is **free** to read — no dependency, no API call, no DNS.

Implemented as an unconditional stderr `ATTENTION` over `STALE_PLAN_HOURS = 24`, alongside finding
5's coverage check in the same pure helper, before the Cloudflare client is built. **The threshold
is not invented**: 24 h is this repository's existing staleness convention (`fqdns.json` is
refreshed when *"stale (>24h)"*), and CLAUDE.md already tells the operator to regenerate the
baseline *immediately* before any rewrite, so anything older than a day is a file the documented
workflow did not intend to apply. Two shadow paths come with it: a stamp **in the future** (clock
skew — treating it as fresh would disable the signal for exactly the file most likely to be wrong)
and an **unreadable** stamp both get their own warnings.

**Declined within the finding:** the reviewer's fallback suggestion of rendering the age in the
summary's `source:` line. The summary is a tally printed *after* the whole report; putting the age
there as well would place one fact in two places that can drift, and the raw stamp already gives it
at full precision for the audit trail. Recorded in SPEC §11.3.

SPEC §20's row now carries the counter-argument, what was done instead, and that it was
re-litigated on 2026-08-04 — so the next reviewer finds it weighed rather than untouched.

---

## Finding 11 (MINOR) — `InvariantError` for a property of the input file

**Fixed, and Critical 1 is not re-opened.** I read fix pass 1's concern 1 first. Its exemption rests
on `merge_body` being `apply_entry`'s only **pre-batch** `InvariantError` raiser. `describe_change`
is called from `report_entries` — **pass 2** — and never from `apply_entry` (verified by reading
every call site), so moving its guard cannot touch that reasoning. No `InvariantError` was added or
removed anywhere inside `apply_entry` or `apply_all`.

The check moved into `check_entry_contract` as §6 **check 9** (`check_post_flags`), raising
`PlanFileError` before any Cloudflare call. That fixes both halves of the finding: the class now
names the operator's file, and the placement is before ~217 read calls instead of after them.

`describe_change` **keeps** its guard, and there the class is now correct rather than merely
retained: with check 9 upstream the condition is unreachable through the run's own path, so reaching
it means the gate has a bug — which is what `InvariantError` is defined as. That is the same
public-helper discipline `verify_records` already applies to a shape `merge_body` guards first
("fix the class, not the instance"). Its existing test is untouched and unweakened.

The placement half has its own test, asserted on the fake client's **recorded list calls** rather
than inferred from the exit code. Before the fix it failed showing one list call already made and
the old `describe_change` `InvariantError` on stderr.

---

## Mutation results (PD#14)

Every mutation applied to the production file one at a time from a byte-copy, reverted immediately
after, `git diff --stat` checked between batches. One line each:

| # | Mutation | Result |
|---|---|---|
| M1 | the §6 check 9 call deleted from `check_entry_contract` | **RED, 2 failed / 215 passed** — the two finding-11 tests only |
| M2 | `verdict_for`'s `drift` forced empty (row 3a never fires) | **RED, 4 failed / 221 passed** — the three drift-verdict tests + the end-to-end re-run test |
| M3 | `verify_records` returns `True` without the proxy check | **RED, 4 failed / 221 passed** — the three `verify_records` proxy tests + the DNS-only-batch end-to-end |
| M4 | a live `proxied` of `None` treated as a match (`if False:`) | **RED, 1 failed / 224 passed** — the null-status test, which asserts the UNKNOWN wording, not just the verdict |
| M5 | only the DNS-only direction flagged (`elif want and not held`) | **RED, 2 failed / 223 passed** — both symmetry tests; proves the one-way version is caught |
| M6 | `proxy_status_mismatches` reports only `posts[:1]` | **RED, 1 failed / 224 passed** — the mixed fixture; proves the varied fixture is non-vacuous |
| M7 | the provenance warnings never printed | **RED, 2 failed / 242 passed** — the partial-sweep and stale end-to-end tests |
| M8 | `elif swept != total:` → `elif False:` | **RED, 3 failed / 241 passed** — partial-sweep unit, both-problems unit, end-to-end |
| M9 | the staleness line's `ATTENTION:` prefix changed to `IGNORED:` | **RED, 1 failed / 243 passed** — proves the prefix, not just the text, is pinned |
| M10 | the run record drops `source_zones_swept`/`source_zones_total` | **RED, 3 failed / 241 passed** — including the byte-exact whole-document record test |
| M11 | `finish()`'s whole-body enclosure removed | **RED, 2 failed / 244 passed** — both finding-7 tests |
| M12 | `failure_code` back to the non-total one-liner | **RED, 2 failed / 244 passed** — both finding-7 tests; proves both guards are load-bearing, not one covering the other |
| M13 | `report_entries`' `continue` deleted | **RED, 2 failed / 245 passed** — the mixed dry-run test and the new `-v` variant (this is the mutation the reviewer measured GREEN at 211 tests) |

---

## Verification

```
$ ./run-tests --fast
All checks passed!                       (ruff, campaign ratchet)
0 errors, 0 warnings, 0 informations     (pyright, standard mode)
========= 1725 passed, 3 skipped, 2 deselected, 15 warnings in 37.70s ==========
EXIT=0
```

1693 → **1725**, +32, exactly the tests added to this file (215 → 247). 3 skipped and 2 deselected
unchanged. Both gates run **before** the tests and gate on their own result.

The suite stays fully offline: every new end-to-end test drives `main()` through `run_main`'s
`FakeCloudflareClient`, and this file's autouse `refuse_real_network` teardown guard would have
fired otherwise. No new test monkeypatches `apc.signal`, so nothing leaves SIGINT at `SIG_IGN`; the
autouse `_restore_sigint_handler` fixture is untouched.

---

## Documents amended

**`development/2026-08-03-platform-domain-util4/SPEC.md`**

- **§6** — nine checks, not eight; check 9 added to the table with its intent and its provenance.
- **§6a** (new) — the provenance checks: the five warning shapes in one table, the warn-not-refuse
  intent, and why the age check does not reopen §20.
- **§7.1a** (new) — the proxy status checked beside the key, never inside it; the two places; why
  the D side is exempt; why `None` is a mismatch; the measurement.
- **§7.3** — row 3a (`proxy-status-drift`) added; row 3's condition extended.
- **§7.4** — a fifth shadow row for the nil proxy status.
- **R6.1** — verification includes the proxy status, with its own message.
- **R6.3.2a** (new) — `finish()` and `failure_code()` MUST be total, with the exit-1 reasoning.
- **§11.2** — the §6a stderr row; the `already-applied` intent gains the absence-assertion rule.
- **§11.3** — `generated.at` is no longer the only staleness signal; why the two are not merged.
- **§12.2** — `source_zones_swept`/`source_zones_total` in the `run` block.
- **§13** — five new pure helpers listed; `verify_records`' contract updated.
- **§14** — group 3 now names the seven rows and the fixture variation required.
- **§15** — results block replaced, dated, commit-attributed; item 6 marked not-re-run with reasons.
- **§17** — "Two deliberate divergences"; Divergence 1 is `max_retries=0` with the SDK measurement;
  both other-copy rows say they do not pin retries.
- **§20** — the re-resolution row records finding 10's counter-argument, the decision to decline
  again, and what was added instead.
- **§22 answer 7** — four numbers re-measured with pasted commands.

**`/workspace/CLAUDE.md`** — the `apply-platform-domains-cloudflare` subsection: seven verdicts not
six; a new paragraph on `proxy-status-drift` and why the check sits beside the key; a new paragraph
on the nine-check contract; a new paragraph on the provenance checks; the `max_retries=0` pin and an
explicit statement that the three `build_client()` copies now differ; three → **four** subprocess
tests with the fourth named.

**Memory (PD#13)** — new entry `comparison-key-cannot-carry-every-field.md`, linked from
`MEMORY.md`, generalizing finding 3's lesson beyond this script (a key narrowed for a structural
reason makes a field *homeless*, not unimportant; a nullable field's `None` is a mismatch; a fixture
missing the field cannot detect the defect).

**Not committed:** `REVIEW-2026-08-04.md` is left untracked, as fix pass 1 left it.

---

## Spine directives applied

**PD#1 — Zero silent failures.** *"Every failure mode must be visible — to the system, the team, and
the user. A failure that can happen silently is a critical defect."* Finding 3 is this exactly: a
hostname taken out of certificate service, reported as `applied`/exit 0 by the very instrument R6.1
calls "the evidence". Finding 5 (a partial-sweep baseline applied with no signal), finding 7 (a
defect that exits 1, indistinguishable from a healthy run), and the "unverifiable coverage" warning
(silence would be ambiguous between complete and unknown) are the same rule.

**PD#2 — Every error has a name.** *"Never 'handle errors.' Name the specific exception class, what
triggers it, what catches it, what the operator/user sees, and whether it's tested."* Finding 11 is
a naming defect and is fixed by naming: `PlanFileError` for the operator's file, `InvariantError`
retained only where the caller really is the one at fault. Finding 3's new state is a **named**
verdict rather than a demotion to `records-missing`, so the operator's ATTENTION line says what is
actually wrong. The two deliberate catch-alls added for finding 7 carry `# noqa: BLE001` with an
inline reason and name the class in the message.

**PD#3 — Data flows have shadow paths.** *"Every flow has a happy path plus three shadows: nil
input, empty/zero-length input, and upstream error. Trace all four for every new flow."* The proxy
comparison's nil shadow is a live `proxied` of `None` — a real SDK shape, not a hypothetical — and
it is traced, tested and given its own wording. The provenance reader's shadows are traced too:
absent fields, a non-integer (`bool`) field, an absent stamp, an unreadable stamp, and a stamp in
the future.

**PD#5 — Observability is scope, not an afterthought.** *"New code paths need structured logging at
the right verbosity (`-v`/`-vv`/`-vvv`), failures surfaced actionably to the operator, and clear
dry-run visibility."* Findings 5 and 10 are entirely this, and the placement is part of the fix:
both warnings print **before the Cloudflare client is built**, unconditional and never `-v`-gated,
and both numbers land in the run record an operator attaches to a change ticket. Finding 11 moved a
message from after ~217 read calls to before the first one. Finding 3's verification message is a
separate sentence precisely so the dry-run/apply report stays actionable.

**PD#7 — Runs are not atomic.** *"A run can die partway… Plan for partial states: idempotent DB
writes, resumability (`--resume-from`), safe re-runs, and the `--for-real`/dry-run gate as the
primary blast-radius control."* Finding 3's scenario (a) is a **safe re-run** that stopped being
safe: R4.2's `already-applied` carve-out exists so a re-run is cheap and correct, and it was
answering "nothing to do" about a drifted record. The `--for-real` gate was not weakened — finding
7's `failure_code` fallback actually *leans* on it, since the single `batch` call site behind that
branch is what makes "a dry run changed nothing" a structural fact rather than an assumption.

**PD#8 — Diagrams/docstrings.** *"Where a diagram exists in a comment or docstring, updating it is
part of changing the flow it describes; a stale diagram is worse than none."* The module docstring's
verdict enumeration, `check_file_contract`'s post-condition paragraph, `PlanFileError`'s "eight
checks", `describe_change`'s and `verify_records`' reasoning, and `apply_all`'s handler-arm prose
were each updated in the same commit as the code. Finding 9 is the same rule applied to a count in
`CLAUDE.md`.

**PD#9 — Everything deferred is written down.** *"Vague intentions are lies."* Finding 4 is exactly
this: a real deviation living only in a docstring and one test. Finding 10's declined half is
written into §20 rather than left for the next reviewer to re-derive, and the not-re-run acceptance
item is stated with its reason rather than quietly left stale.

**PD#11 — Terminology stays clear and consistent.** *"Terminology stays clear and consistent — within
the new design and across the existing codebase."* `proxy-status-drift` follows the existing
verdict family (a noun phrase describing Cloudflare's state), and the operator-facing words
"proxied" / "DNS-only" / "UNKNOWN (null) proxy status" match the sibling's own vocabulary
(`unknown-proxy-status`) rather than inventing a third spelling.

**PD#14 — Your instruments can lie.** *"A test, golden, fixture, shim, counter, log line, or metric
is code, and can be silently wrong. A green check is a claim, not evidence, until it has been shown
capable of going red on the condition it guards."* Thirteen mutations, table above, each reverted;
M5 and M6 exist specifically to prove the *varied* fixtures are non-vacuous, and M12 proves finding
7's two guards are independently load-bearing rather than one covering the other. Finding 6 is the
same rule applied to an acceptance suite, and the fix was to **run** it, not to edit the numbers.

**Engineering Preferences — right-sized diff.** *"Favor the smallest design diff that cleanly
expresses the change, but don't compress a necessary rewrite into a minimal alteration."*
`record_key` is untouched, so the ambiguity/partially-applied/unexpected-records rows keep every
existing assertion; one new pure helper, one new verdict, one new contract check, one new provenance
reader. The two `verdict_for` extractions were forced by the lint gate, not chosen.

---

## Concerns

1. **§15 item 6 is the one acceptance item this pass could not run, and it is now the most valuable
   one to run.** It is a **read-only** live dry run against the real 217-entry baseline. Its last
   result predates §7.1a entirely, so its "all 217 validated `ready`" says nothing about whether any
   of those 217 FQDNs is currently in a proxy status the plan does not expect — and a
   `proxy-status-drift` verdict now **aborts the whole run**, so an operator who has not re-run the
   dry run could discover it at the worst moment. Running `./apply-platform-domains-cloudflare -v
   platform-domains-cloudflare-plan.json` (no `--for-real`) is cheap, safe, and would either
   confirm the fix changes nothing in practice or find a real drift.
2. **The staleness warning now fires on the real baseline.** `platform-domains-cloudflare-plan.json`
   in the repo root is dated 2026-08-01, so any run against it emits the 24-hour ATTENTION. That is
   the intended behavior, but it means the *next* live dry run will look noisier than the pasted
   §15 item 6 block — worth knowing before someone reads it as a regression.
3. **`STALE_PLAN_HOURS = 24` is a judgment.** It is defended (the repo's own `fqdns.json`
   convention, and CLAUDE.md's "immediately before any rewrite"), but it is a threshold and
   thresholds are arguable. It is a single named constant with its reasoning attached, so moving it
   is a one-line change; I did not add a flag for it.
4. **`--fast` only.** The live tier was not run, per the standing "never against real Cloudflare"
   constraint. The offline suite plus both gates are green.
5. **A fixture-level side effect worth naming:** `plan_doc()` now emits the staleness ATTENTION in
   roughly sixty main()-driving tests. I judged that a feature (a mutation removing the warning has
   that much stderr to survive, and the fixture is realistic), but it does mean stderr in this
   file's test output is noisier than before, and a future test asserting on *whole* stderr content
   rather than substrings would need to account for it.

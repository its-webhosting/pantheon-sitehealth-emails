# `apply-platform-domains-cloudflare` — the applier

**Spec.** A new, temporary, standalone utility that reads a **plan** or **revert** file produced by
`find-platform-domains-cloudflare` and performs the Cloudflare DNS batch calls it describes. The
prompt is `PROMPT.md` in this folder. This script is the **applier** whose normative contract was
written, but not implemented, as §5.4 of
`development/2026-07-31-platform-domain-util3/SPEC.md` (hereafter **util3 SPEC**).

Prior increments, in order: `development/2026-07-28-platform-domain-util/` (the
`find-platform-domains-dns` sibling), `development/2026-07-30-platform-domain-util2/` (this
utility's Cloudflare-side sibling, plus `research.md`, the record-level mechanics research), and
`development/2026-07-31-platform-domain-util3/` (the plan/revert/excluded file formats).

> **Read `prompts/directives.md` first** — the Spine. This spec cites Prime Directives by number
> and restates none of them.

---

## Requirement vocabulary

| Word | Meaning |
|---|---|
| **MUST** / **MUST NOT** | An absolute requirement. A violation is a defect, and there is a test. |
| **SHOULD** | Strong recommendation; a deviation requires a stated reason in code. |
| **MAY** | Genuinely optional. |
| **NEVER** | Same force as MUST NOT, used where the negative reads more clearly. |

Every list in this document is marked **exhaustive** or **illustrative**. An unmarked list is a
defect in this spec.

---

## Glossary

Terms carried from the util3 SPEC keep their meaning exactly; new terms are marked **(new)**.
Each term is used once per concept, here and in the code.

| Term | Meaning |
|---|---|
| **platform domain** | A hostname ending in `.pantheonsite.io`. **Nothing else.** |
| **FQDN** | The custom hostname a Pantheon site is served on; the key of every entry in every file. |
| **inventory** | `<basename>.json` — the record of Cloudflare state. **This script never reads it.** |
| **plan** | `<basename>-plan.json`. Forward rewrite: platform CNAME → A/AAAA. |
| **revert** | `<basename>-revert.json`. Reverse rewrite: A/AAAA → platform CNAME. |
| **excluded** | `<basename>-excluded.json`. Carries no `body`; this script refuses it by name. |
| **input file** **(new)** | The one plan-or-revert file this run was given. |
| **direction** | `generated.direction` in the input file: `plan` or `revert`. |
| **entry** | One FQDN's object inside the input file. |
| **applier** | This script. |
| **match block** | `delete_match` — the record identity resolved to record ids at apply time. |
| **D** **(new)** | The set of records an entry's `delete_match` describes. |
| **P** **(new)** | The set of records an entry's `body.posts` would create. |
| **R** **(new)** | The set of records Cloudflare currently holds at that FQDN **whose type is CNAME, A or AAAA** (§7.1). |
| **verdict** **(new)** | The classification of one entry against R: `ready`, `already-applied`, or one of four invalid reason codes (§7.3). |
| **outcome** **(new)** | What actually happened to one entry in this run (§12): one of `applied`, `already-applied`, `planned`, `failed`, `unverified`, `unknown`, `not-attempted`. |
| **run record** **(new)** | `<input-stem>-run-<timestamp>.json`, written on every exit path (§12). |
| **dry run** **(new)** | The default: validate, report, change nothing. |
| **for-real run** **(new)** | `--for-real` was given: validate, report, and perform the calls. |

**Verdict and outcome are different words on purpose.** A verdict is what pass 1 decided about
Cloudflare's state; an outcome is what this run did. `already-applied` is deliberately both — the
verdict determines that outcome with no further action.

---

## 1. What this is and why

`find-platform-domains-cloudflare` writes a plan file and a revert file, and **never calls the
Cloudflare API to write anything**. This script is the other half: it takes one of those files and
performs the batch calls, or — by default — reports exactly what it would perform and stops.

The change being applied is the Pantheon Fastly → Pantheon-Cloudflare CDN migration: for each
FQDN, swap a proxied CNAME pointing at a `*.pantheonsite.io` platform domain for the A/AAAA
records that platform domain resolves to. The record-level mechanics, the certificate analysis,
and the reason a single batch call is the right instrument are
`development/2026-07-30-platform-domain-util2/research.md`.

**Two properties define this script, and everything below serves them:**

1. **Nothing is written until everything has been checked.** A run either passes validation
   entirely and then applies, or fails validation and changes nothing at all.
2. **A run that dies partway is loud about exactly where.** Every entry's outcome is printed, and
   written to a file, on every exit path — including the fatal and interrupted ones.

---

## 2. Global constraints

1. **Standalone.** The script MUST import nothing from `psh/`, `check/`, `plugin/` or
   `script_context`. Code needed from the main program or from the siblings is **copied into the
   script**, not imported and not modularized (§17). `PROMPT.md`: *"Prefer copying code written
   for the main script into the … script … in order to make deletion/cleanup easy."*
2. **Temporary.** Delete after Pantheon's CDN migration. The checklist delta is §19.
3. **No performance work.** `PROMPT.md`: *"Do not put any significant amount of work into making
   this script fast or efficient."*
4. **Test-first**, at the seams named in §13, per `prompts/implementation-standards.md` and
   `mattpocock-skills:tdd`.
5. **It reads exactly one file.** Not the inventory, not both directions, not a config-driven set.

---

## 3. Requirements

### R1 — Scope (exhaustive)

R1.1 The script MUST act only on entries in the input file, and only on records whose `type` is
`CNAME`, `A` or `AAAA`. Records of any other type at the same FQDN MUST be ignored entirely —
never read as state, never deleted, never counted (§7.1).

R1.2 The script MUST NEVER create, modify or delete a record the input file did not name.

R1.3 The script MUST NEVER write to any Cloudflare API other than
`POST /zones/{zone_id}/dns_records/batch`, and MUST NEVER read any Cloudflare API other than the
DNS record list. *Intent:* the blast radius is stated as a requirement so that widening it is a
visible spec change, not an implementation detail.

### R2 — Command-line surface

```
usage: apply-platform-domains-cloudflare [-h] [-c CONFIG] [--only FQDN] [--for-real] [-v] FILE
```

R2.1 `FILE` is the one positional argument: a plan or revert file.

R2.2 `--only FQDN` is **repeatable** (`action="append"`), NOT `nargs="+"`.

*Intent:* the sibling documents in its own `--help` that `ZONE` names must be given *after* the
options because argparse cannot interleave positionals with a variadic option. With one positional
`FILE` and a variadic `--only`, `--only a b file.json` would silently swallow the filename into the
option. A repeatable single-value option has no such ambiguity, at the cost of typing `--only`
twice. **Explicit over clever.**

R2.3 `allow_abbrev=False` MUST be set, so `--for` is an error rather than an abbreviation of
`--for-real`. *Intent:* the same foot-gun the main program's parser documents; here the
abbreviation would turn a dry run into a production rewrite.

R2.4 `-c/--config` defaults to `pantheon-sitehealth-emails.toml` and is read **only** for
`[Cloudflare]` credentials, exactly as the sibling reads it.

R2.5 `-v/--verbose` adds the API method, path and exact request body per entry (§11).

R2.6 **Without `--for-real`, the run MUST NOT perform any batch call.** This is the primary
blast-radius control, and §14 group 5 asserts it against the fake client rather than inferring it.

### R3 — Three passes, in this order, with no interleaving

R3.1 **Pass 1 (validate)** MUST complete for every selected entry before pass 3 begins. It
performs only DNS record **list** calls.

R3.2 If **any** selected entry's verdict is invalid, the run MUST report every invalid entry and
exit 2 having performed no write. `PROMPT.md`: *"if there are problems with any entry, the script
should exit with a fatal error without doing anything."*

R3.3 **Pass 2 (report)** MUST run identically in both modes, from the same data pass 1 produced.
*Intent:* the dry run is a rehearsal of the real run, not a parallel implementation of it. Any
divergence between what a dry run prints and what a for-real run does is a defect of the first
order for a destructive tool.

R3.4 **Pass 3 (apply)** runs only with `--for-real`, processes entries **in the input file's key
order** (sorted, since the file is written with sorted keys), and stops at the first failure.
`PROMPT.md`: *"If any API call fails, the script should exit immediately with a fatal error; it
should not attempt to revert any changes it has already made, and it should not attempt to make
the remaining changes specified in the file."*

R3.4.1 **Every one of pass 3's stop paths MUST have a test that goes red when that path alone stops
stopping** — a `three_entry_doc()`-shaped run failing on the *second* entry, asserting on the fake
client's **recorded batch calls** that the third was never posted. *Intent (fix-pass review,
Important 2, PD#14):* the `failed` arm was pinned that way and the `unverified` and `unknown` arms
were not — every test reaching them used a one-entry document, where `return` and `continue` are
indistinguishable. Measured: `return` → `continue` in either arm left all 211 tests green while the
mutated run went on to rewrite a third production zone past an entry whose fate was unknown. An
assertion on the outcome *labels* is not a substitute: a `continue` leaves the later entries with
plausible-looking outcomes.

R3.5 Pass 3 MUST NOT re-decide anything pass 1 decided. It sends the merged body built from pass
1's resolved record ids, and verifies. An entry reaching pass 3 without a `ready` verdict is an
`InvariantError` (§10.1).

### R4 — Deviation from util3 SPEC §5.4, stated explicitly

util3 SPEC §5.4 step 3 says a `delete_match` with **zero** matches means the entry *"is already
applied, or Cloudflare drifted. **Skip the entry and report it.** Do not partially apply."* and
that **more than one** match means *"refuse the entry and report it"* — i.e. per-entry tolerance
with the rest of the file still applied.

This spec **supersedes** that, on `PROMPT.md`'s explicit instruction, in one direction and one
only:

R4.1 A zero-match entry is skipped **only** when it is affirmatively `already-applied` (§7.3
row 3) — R == P exactly. Every other zero-match state is invalid and aborts the whole run.

R4.2 Every other invalid verdict, including the multi-match case §5.4 would have skipped, aborts
the whole run before anything is written.

*Intent:* §5.4's per-entry tolerance means a file that is half-stale gets half-applied, and the
operator discovers which half afterwards. The prompt's all-or-nothing rule is stronger. The
`already-applied` carve-out is what keeps it usable: without it, a run that died at entry 12 of
217 could never be re-run at all, because entries 1–11 would now fail validation — the operator
would have to hand-edit a 217-entry JSON file, and a hand-edited file is an unreviewed input to a
destructive change. With it, re-running the same file finishes the job and plan→plan is a verified
no-op.

R4.3 `already-applied` MUST be established affirmatively (R == P), never inferred from the absence
of D. *Intent:* PD#1. "The records I meant to delete are missing" and "the records I meant to
create are present" are different claims, and only the second one licenses skipping.

### R5 — What is applied

R5.1 The request body MUST be `{"deletes": [{"id": …}, …], "posts": <entry body posts verbatim>}`
— the entry's `body.posts` passed through **unmodified**, with a `deletes` array built from the
record ids pass 1 resolved.

R5.2 `delete_match` lives outside `body` in the input file (util3 R5.3) and MUST stay there; the
merged body is constructed in memory and never written back.

R5.3 The call MUST be made through the SDK's typed entry point,
`client.dns.records.batch(zone_id=…, deletes=…, posts=…)`, after asserting the entry's `method`
and `path` (§6 checks 5). *Intent:* the typed method is the documented, supported surface and
parses the response. It ignores the file's `path`, which would make that field decorative and a
hand-edited path silently ineffective — the assertion turns "ignored" into "checked".

**Measured, cloudflare 5.4.0:** the SDK's `maybe_transform` against
`record_batch_params.RecordBatchParams` returned a test body **byte-identical**, including a key
its schema does not define. The typed path therefore does not rewrite, drop or rename anything in
`posts`. This was verified rather than assumed, because the whole value of the plan file is that
its `body` is *"the exact JSON body to be used for the API call"* (util3 `PROMPT.md` 1(c)).

R5.4 Cloudflare executes batch operations in the documented order **Deletes → Patches → Puts →
Posts** inside one database transaction. The applier relies on this ordering and MUST NOT split a
batch into separate calls. *Intent:* it is what keeps an FQDN from ever being record-less, and
what lets a CNAME and its replacement A records — which cannot coexist — be swapped in one step.

### R6 — Post-apply verification

R6.1 After each successful batch call, the applier MUST re-list the FQDN and require R == P
exactly (§7.1's governed-type rule applies).

R6.2 On mismatch, the applier MUST wait `VERIFY_RETRY_SLEEP` (2.0 s, through the `sleep` seam)
and re-list **once** before failing.

*Intent:* PD#14 — *"a green check is a claim, not evidence."* A 200 from the batch endpoint is
Cloudflare's claim; the record list is the evidence. The single retry exists because Cloudflare's
own batch documentation warns that *"Cloudflare's distributed KV store must treat each record
change as a single key-value pair. This means that the propagation of changes is not atomic"* — a
read served before the change lands would otherwise be a false mismatch on a healthy run.

R6.3 A mismatch surviving the retry MUST raise **`VerifyError`** — the `ApplyError` subclass, never
a bare `ApplyError` — and stop the run. The entry's outcome is **`unverified`**, not `failed`, and
the run exits 3, because the batch returned and therefore committed.

A verification **read** that fails outright takes the same outcome, for the same reason: the write
already happened, and only our confirmation of it did not. That covers a
`cloudflare.CloudflareError` from the re-list **and** a bare `TimeoutError`/`OSError` from the same
call — the transport failing is not evidence the batch did not commit, and routing it to `unknown`
would have the run assert the call never completed when it returned 200.

R6.3.1 **The whole post-batch section MUST be enclosed, and every exception raised in it that is
not already an `ApplyError` MUST become a `VerifyError` naming the original class** — not only the
three enumerated above. *Intent (fix-pass review, Critical 1):* an enumerated list is a list of the
failures somebody thought of, and the exit-2 guarantee cannot rest on it being complete. What every
exception raised past the batch call has in common is that the batch already returned, which is the
whole of R6.3's reasoning. **Measured:** the SDK calls `response.json()` unguarded
(`cloudflare/_response.py:266`), so a truncated or non-JSON 200 on the verification read raises
`json.JSONDecodeError` — a `ValueError`, neither a `CloudflareError` nor an `OSError` — which
escaped every clause, left the entry at its `not-attempted` seed, and produced **exit 2** for an
FQDN the run had just rewritten. An `AttributeError`/`KeyError` from an SDK shape change while
reading the listed rows (the scenario §8.3 names) has the identical shape.

The enclosure MUST catch `Exception`, **never** `BaseException`: a `KeyboardInterrupt` here has to
keep reaching `apply_all`'s own arm, which §9.3 pins to `unknown`.

R6.3.2 By contrast, the **batch call's own** clauses stay open-ended: an unrecognised exception
there propagates unwrapped, because it cannot be placed relative to the commit. §9.1's writer-side
rule is what records it.

*Intent, and why the class is named explicitly here:* `apply_all` catches `VerifyError` **before**
the broader `ApplyError` clause, so a bare `ApplyError` raised in this position is recorded as
`failed` — "rejected, nothing committed" — for a batch that committed, which collapses to **exit 2,
"nothing in Cloudflare was changed."** That is verbatim the defect §8.1 records having already
shipped once, and an earlier revision of this very sentence said `ApplyError`, which is how it
would have shipped a second time.

### R7 — Entry selection

R7.1 With no `--only`, every entry in the file is selected.

R7.2 With `--only`, only the named FQDNs are selected. Names are compared after `normalize()`
(lowercase, trailing dot stripped) against the file's keys, which util3 §5.1 states are already
normalized.

R7.2a **Unselected entries are never validated and never counted as anything but "in the file".**
They appear only in the summary's `entries in file` number. *Intent:* validating an entry the run
will not touch would let an unrelated FQDN's drift abort a deliberately narrow, safe run — the
opposite of what `--only` is for.

R7.3 An `--only` value matching no key in the file is **fatal (exit 2), and every miss is named**.
*Intent:* the sibling applies exactly this rule to unmatched `ZONE` names, for exactly this reason
— a typo that silently narrows a destructive run is the under-reporting failure this family of
scripts refuses to have.

R7.4 A subset run MUST print an unconditional `ATTENTION:` line stating how many of the file's
entries it covers.

### R8 — Reporting (`PROMPT.md`, verbatim requirement)

R8.1 On every exit path — normal, fatal, or interrupted — the run MUST print the summary block
(§11.3): the number of entries in the file, the number selected, and the count of each outcome.

R8.2 The summary counts **entries (FQDNs)**, and says so in its own wording.

*Intent:* `PROMPT.md` asks for *"the total number of sites specified by the plan."* The plan file
contains no site information — util3's glossary defines an entry as one FQDN's object, several
FQDNs can belong to one Pantheon site, and nothing in the file can tell which. Printing an FQDN
count under the word "sites" would be a wrong number in an operator's incident notes. This is a
**deliberate deviation from the prompt's wording**, not from its intent.

### R9 — The run record

R9.1 Every run MUST write a run record (§12) beside the input file, on every exit path.

R9.1a **One documented exception, exhaustive, shared with R8.1:** argparse's own `--help` and
usage-error exits happen inside `parse_args`, **before** `main()`'s `try` and before `options.file`
exists — so neither the summary block nor the run record is produced on those two paths, and
structurally cannot be. This is the same boundary §8.3 already records for the exit-120 case, and
it is stated here so a reader does not take "every exit path" as a promise the program cannot
keep.

R9.2 A dry run writes one too, with `"for_real": false`. *Intent:* it is the validation report,
and it is the thing an operator can attach to a change ticket before the change.

R9.3 A failure to write the run record MUST NOT cause the process to claim nothing was changed
(§9.2).

---

## 4. Data flow

```
argv ─► parse ─► read FILE ─► §6 file contract (8 checks)  ──fail──► ERROR, exit 2
                                  │
                                  ├─ --only ─► unmatched name ──────► ERROR naming every miss, exit 2
                                  ▼
                    ┌──────────────────────────────────────────┐
                    │ PASS 1 — VALIDATE  (read-only)           │
                    │  for each selected entry:                │
                    │    R = records_at_name(zone_id, fqdn)    │  dns.records.list(
                    │        keep type in {CNAME, A, AAAA}     │    name={"exact": fqdn})
                    │    verdict_for(entry, R) ──►             │
                    │      ready | already-applied | invalid   │
                    └──────────────────┬───────────────────────┘
                                       │
                         any invalid? ─┴─yes─► ATTENTION per entry, exit 2   [NOTHING CHANGED]
                                       │ no
                                       ▼
                    ┌──────────────────────────────────────────┐
                    │ PASS 2 — REPORT  (identical both modes)  │
                    │  per entry: one change line              │
                    │  -v: METHOD PATH + exact merged body     │
                    └──────────────────┬───────────────────────┘
                                       │
                         --for-real? ──┴─no──► summary + run record ─► exit 0 / 1
                                       │ yes
                                       ▼
                    ┌──────────────────────────────────────────┐
                    │ PASS 3 — APPLY, in key order, one at a   │
                    │ time:                                    │
                    │   batch(zone_id, deletes=ids, posts=…)   │
                    │   re-list; R == P?  ─no─► sleep 2s, once │
                    │                          ─still no─► fail│
                    │   record outcome                         │
                    │   failure ─► STOP; rest = not-attempted  │
                    └──────────────────┬───────────────────────┘
                                       ▼
                    ALWAYS: summary + run record  ─► exit 0 / 1 / 3 / 130
```

---

## 5. Copied, not imported

See §17 for the full inventory. The shape to note here: this script is a **third independent
copy** of `build_client()`'s environment pin. CLAUDE.md currently states there are **two** places
to check on a Cloudflare SDK upgrade; after this increment there are **three**, each with its own
real-built-request test (§14 group 13). That sentence in CLAUDE.md MUST be updated (§18).

---

## 6. File contract — the eight fatal checks

Evaluated in this order, before any Cloudflare call. Each is fatal: `PlanFileError`, exit 2.
This list is **exhaustive**.

| # | Condition | Message names |
|---|---|---|
| 1 | File unreadable, not valid JSON, or not a JSON object | the path and the underlying error class |
| 2 | `generated.direction` absent, or not `"plan"` / `"revert"` | the value found; an `"excluded"` direction is refused **by name** with a sentence saying an excluded file carries no `body` |
| 3 | `entries` absent, not an object, or empty | the path |
| 4 | An entry missing any of `zone_id`, `method`, `path`, `body`, `delete_match` | the FQDN key and the missing field |
| 5 | `method != "POST"`, or `path != "/zones/{zone_id}/dns_records/batch"` built from that entry's own `zone_id` | the FQDN key, the expected and the found value |
| 6 | `body` contains a `deletes` key | the FQDN key, and why (util3 R5.3: ids are resolved at apply time, so a baked-in `deletes` cannot be correct) |
| 7 | `body.posts` absent or empty; a post missing `type`/`name`/`content`; a post `type` outside `{CNAME, A, AAAA}` | the FQDN key and the offending post index |
| 8 | `delete_match` absent, empty, or an item missing `type`/`name`/`content`, or an item `type` outside `{CNAME, A, AAAA}` | the FQDN key and the offending item index |

Check 5 is what makes R5.3's typed call honest. Checks 7 and 8 are what make R1.1's governed-type
rule total: after them, D and P contain only governed types by construction.

*Intent for "fatal, not skipped":* every one of these means the file is not what this script knows
how to apply. A file that is malformed in one entry is a file whose provenance is in question, and
partially applying it is the outcome §3's property 1 exists to prevent.

---

## 7. The verdict — the single canonical gate table

### 7.1 What is compared

**R** is every record Cloudflare currently returns at the entry's FQDN whose `type` is `CNAME`,
`A` or `AAAA`. A `TXT`, `MX`, `CAA` or any other record at the same name is **not** in R and
blocks nothing (R1.1).

Records are compared by **`record_key` = `(TYPE, normalize(name), canonical_content)`**, where:

| Type | `canonical_content` |
|---|---|
| `A`, `AAAA` | `str(ipaddress.ip_address(content))` |
| `CNAME` | `normalize(content)` |

*Intent:* `2620:12a:8000::4` and `2620:12A:8000:0:0:0:0:4` are one address written two ways, and a
string comparison would call them two records — inventing a `partially-applied` verdict on a
healthy zone. Names and CNAME targets are compared case-insensitively with a trailing dot ignored,
matching `normalize()` in both siblings. The API's own `name` and `content` filters are documented
**case-insensitive**, so what the filter returns is re-checked in code regardless.

### 7.2 The comparison

Pass 1 computes `R`, `D` (from `delete_match`) and `P` (from `body.posts`) as **sets of
`record_key`**, then asks which set R equals.

### 7.3 Gate table (exhaustive; evaluated in this order; every entry gets exactly one verdict)

| # | Verdict | Condition | Valid? | Effect |
|---|---|---|---|---|
| 1 | `record-ambiguous` | some `record_key` occurs more than once in R | **invalid** | abort |
| 2 | **`ready`** | R == D | valid | applied in pass 3 |
| 3 | **`already-applied`** | R == P | valid | skipped, reported, counted; contributes exit 1 |
| 4 | `partially-applied` | R contains at least one member of D **and** at least one member of P | **invalid** | abort |
| 5 | `unexpected-records` | R ⊃ D, or R ⊃ P (a proper superset — every expected record plus extra governed records) | **invalid** | abort |
| 6 | `records-missing` | anything else (R is a strict subset of D or of P, R is empty, or R holds unrelated governed records) | **invalid** | abort |

Note rows 2 and 3 are mutually exclusive in practice: D and P differ in type by construction (a
plan's D is a CNAME and its P is A/AAAA; a revert's is the reverse), and CNAME cannot coexist with
A/AAAA at one name. Row 1 is evaluated first so a duplicated key can never make a set comparison
accidentally succeed.

**Row 5 is what closes util3 §5.4's "known and accepted" hazard.** That section accepted that if
an unrelated fourth A record appears at a name after a plan is applied, the revert's `POST`
collides and Cloudflare rolls the batch back with an error. Here that state is `unexpected-records`
at validation time, named on stderr, hours earlier, with nothing written.

**Detail strings.** Every invalid verdict carries a human-readable `detail` naming what was found
versus what was expected, in `record_key` terms. It is the only thing the operator has to work
from, so it is not optional and it is not `-v`-gated (§11).

**`record-ambiguous` is the one exception, and it MUST also name the colliding record ids.**
*Intent:* by construction the two records share a `record_key` — that is what makes the FQDN
ambiguous — so a detail in `record_key` terms alone **cannot tell them apart**, and this verdict
aborts the entire run and hands the operator a manual Cloudflare cleanup. The id is the only field
that distinguishes the rows in the dashboard or the API. This does **not** widen `record_key`,
which stays deliberately id-less for the set comparison (§7.1): `verdict_for` already holds the
raw rows as a local, so the ids are a same-scope lookup, not a signature change.

### 7.4 Shadow paths for the validation flow (PD#3), all four traced

| Shadow | Condition | Outcome |
|---|---|---|
| happy | R == D | `ready` |
| **nil** | `delete_match` or `posts` absent/empty | **unreachable** — §6 checks 7 and 8 made it fatal before pass 1. Asserted in code (`InvariantError`), not assumed. |
| **empty** | R is empty — no governed record at the name at all | `records-missing`; abort. *Not* silently treated as already-applied. |
| **upstream error** | the list call raises `cloudflare.CloudflareError` | `CloudflareReadError`, exit 2, nothing changed |

---

## 8. Exit codes

| Code | Meaning |
|---|---|
| 0 | Completed; every selected entry applied, or a dry run that validated clean |
| 1 | Completed; ≥1 entry was `already-applied`; nothing failed |
| 2 | Could not complete, and **nothing in Cloudflare was changed** |
| 3 | **Failed mid-apply — Cloudflare was left partially changed** |
| 130 | Interrupted |

### 8.1 The rule that makes 2 and 3 trustworthy

Define `changed` = the number of entries whose outcome is `applied`, `unverified` **or** `unknown`.

- `changed == 0` and the run failed → **2**.
- `changed > 0` and the run failed → **3**.

*Intent:* PD#1. Each of the three terms is a state in which Cloudflare **may or does** hold a
change, and calling any of them "unchanged" would let the process print "nothing was changed"
about a production DNS rewrite it cannot account for.

**The four post-call states are distinct, and conflating any two of them loses an operator
action.** A batch call ends in exactly one of:

| Outcome | What is true of Cloudflare | What the operator must do |
|---|---|---|
| `applied` | the batch returned **and** the records read back as expected | nothing |
| `unverified` | the batch **returned** (so it committed), but the records do **not** read back as expected after §R6.2's retry, or could not be read at all | **inspect this FQDN by hand** — Cloudflare changed, but not verifiably into the intended state |
| `failed` | the batch was **rejected** — a batch is one transaction, so nothing committed for this entry | fix the cause and re-run; this entry is untouched |
| `unknown` | the call did not complete (dropped connection, timeout), **or it failed in a way this script does not recognise and cannot place relative to the commit**, so whether it committed is **not known** | inspect this FQDN by hand before re-running |

**One known overstatement in `unverified`, measured and accepted.** The SDK raises only on HTTP
status — verified against cloudflare 5.4.0, where neither `_base_client` nor `_response` inspects a
`success` field — so a hypothetical `200` carrying `"success": false` would reach R6's verification,
fail it, and be labelled `unverified` ("the batch returned, so it committed") for a call that
committed nothing. The operator action that label implies (*inspect this FQDN by hand*) is the safe
one and the exit code (3) is the conservative one, so this is a labelling overstatement rather than
a hazard. Recorded rather than mitigated: distinguishing it would mean parsing a response envelope
the SDK does not expose.

*Intent for `unverified` specifically (added after Task 8 surfaced the contradiction):* R6.3 says a
surviving verification mismatch exits 3 because Cloudflare was changed, while an earlier version of
this section derived `changed` from `applied + unknown` only — so a lone mismatch produced
`{failed: 1}`, `changed == 0`, and **exit 2, the code that means "nothing was changed."** The
formula was wrong, not R6.3: the batch returned 200, so it committed. `failed` must mean "rejected,
nothing committed", and the committed-but-unconfirmed state needs its own name.

`exit_code_for(outcome)` is a **pure function of the outcome tally** and is unit-tested against a
full truth table (§14 group 11). *Intent:* it is the most consequential logic in the script and
would otherwise be reachable only through a full end-to-end run.

### 8.2 Deviation from the sibling family, stated

Both siblings use `0 / 1 / 2 / 130`. This script adds **3**. *Intent:* after a destructive run the
first question is "did it change anything?", and folding a half-finished rewrite into 2 makes it
indistinguishable from a clean refusal to an operator's `case $?`. CLAUDE.md's description of the
pair's shared taxonomy MUST record that this third script differs (§18).

### 8.3 The last line of defence

`main()` MUST end its handler chain with the sibling's guard, verbatim in reasoning:

```python
    except SystemExit:
        raise
    except BaseException as e:  # noqa: BLE001 -- deliberate last line of defence, see the docstring: ...
        report_line(f"ERROR: unexpected {type(e).__name__}: {e}")
        return failure_code(state)   # 3 if changed_count > 0 else 2 -- see §9.1
```

**The `return` here is `failure_code(state)`, NOT a literal 2**, and the same applies to the
`OSError` arm. *Intent:* §9.1's rule — no exit path may report 2 once `changed_count > 0` — names
this arm explicitly, and an earlier version of this snippet showing a bare `return 2` is what led
an implementer to read the two sections as contradictory and leave the catch-all reporting
"nothing was changed" after a partial rewrite. An `AttributeError` or `KeyError` from an SDK shape
change is precisely what this arm exists to catch, and it can land after entries have applied. One
helper, used by all three failure arms, is the only shape that keeps them from drifting apart
again.

CPython exits **1** on any uncaught traceback, and 1 here means "completed with already-applied
skips". Without this guard a crashed run and a healthy run are indistinguishable. The catch-all
NEVER swallows — the class is always named on stderr (PD#2).

**The one documented exception, exhaustive:** argparse writes its usage, error and `--help` text
before any stream guard exists and outside every handler, so `--help >/dev/full` and
`--bogus 2>/dev/full` still exit **120**. Identical to both siblings; declined for the same reason.

---

## 9. Error handling

### 9.1 Named exceptions (exhaustive)

| Exception | Raised by | Caught by | Operator sees | Exit |
|---|---|---|---|---|
| `StartupError` | argv, config file, credential resolution, stream guards — copied from the sibling | `main()` | `ERROR: …` via `report_line` | 2 |
| `PlanFileError` (subclass of `StartupError`) | the eight §6 checks | `main()` | `ERROR: …` naming the file, the FQDN key and the field | 2 |
| `InvariantError` (subclass of `StartupError`) | an entry reaching pass 3 without a `ready` verdict; a delete id pass 1 never resolved; a `delete_match`/`posts` shape §6 should have rejected | `main()` | `ERROR: …`, named as a defect in this script's own reasoning (PD#2) | **2, or 3 if `changed_count > 0`** — see below |
| `CloudflareReadError` (subclass of `StartupError`) | a record-list call in **pass 1** | `main()` | `ERROR: …` with the Cloudflare error codes | 2 |
| `ApplyError` | a batch call the API **rejected** — one transaction, so nothing committed for that entry | `main()` | `ERROR: …` naming the FQDN and the Cloudflare error codes | outcome `failed`; 2 or 3 per §8.1 |
| `VerifyError` (subclass of `ApplyError`) | the batch **returned**, but the post-apply verification did not match after §R6.2's retry, **or** the verification record-list call itself failed, **or** anything else was raised after the batch returned (R6.3.1) | `main()` | `ERROR: …` naming the FQDN and what Cloudflare actually holds — or, for R6.3.1, the unexpected class | outcome **`unverified`**; 3 per §8.1 |
| `OutputWriteError` (subclass of `StartupError`) | the run record write | `main()` | `ERROR: cannot write <path>: <class>: <message>` | §9.2 |
| `KeyboardInterrupt` | anywhere | `main()` | the summary, then the interrupt notice | 130 |
| `OSError` | report/record writes | `main()` | `ERROR: …` | **2, or 3 if `changed_count > 0`** |
| anything else | inside `main()`'s try | `main()`'s `except BaseException` (§8.3) | `ERROR: unexpected <class>: <message>` | **2, or 3 if `changed_count > 0`** |

**No exit path may report 2 once `changed_count(counts) > 0`.** Exit 2 means *"could not complete,
and **nothing in Cloudflare was changed**"* (§8). Any exception escaping mid-run — an
`InvariantError` from a defect, or anything reaching §8.3's last line of defence — must therefore
be routed through the same `changed`-aware computation as the ordinary failure paths, yielding **3**
when entries have already applied. *Intent:* this is the third face of one bug. §8.1's `unverified`
amendment closed it for verification mismatches; this closes it for exceptions. A defect in this
script's own reasoning is exactly when an operator most needs the exit code to be honest about
whether production DNS was touched, and "the code crashed" is not a reason to claim it did not.
Rows above that can only fire **before** the first write (`StartupError`, `PlanFileError`,
`CloudflareReadError` in pass 1) keep a flat 2, because for them the claim is true.

**That rule has a reader half and a writer half, and BOTH are required.** Routing every failure arm
through one `changed`-aware helper (`failure_code(state)`) is the reader half, and it is not
sufficient on its own: the tally can only report an entry as changed if something *recorded* that
the entry was in flight.

- **Reader:** every exit path computes 2-vs-3 from `changed_count(counts)`, never from a literal.
- **Writer:** `apply_all` MUST record an outcome for the in-flight entry on **every** way out of
  `apply_entry`, including exceptions no clause names. Its handler chain therefore ends in a
  catch-all that sets the entry's outcome to **`unknown`**, writes its result line, and
  **re-raises** (so §8.3's last line of defence still names the class, and so R3.4's "attempt
  nothing further" holds without a `return`).

*Intent (fix-pass review, Critical 1):* review round 1 fixed the reader half for a `RuntimeError`
out of `apply_entry` and left the writer half blind. **Reproduced:** a one-entry plan whose batch
call returned and whose verification read then raised `ValueError` made 1 batch call, recorded the
entry as `not-attempted`, and exited **2** — "nothing in Cloudflare was changed" — with a `mode:`
line reading `0 of 1 entries changed`. Enumerating classes in that catch-all is exactly what failed
the first time; whatever the exception is, an entry `apply_entry` was in the middle of is not an
entry that was never attempted.

**The one exception, and it is exhaustive:** `InvariantError` propagates through that arm
**unrelabelled**, leaving the entry `not-attempted`. The only `InvariantError` `apply_entry` can
raise is `merge_body`'s, which runs *before* the batch call (`verify_records`' is post-batch and
R6.3.1 converts it to `VerifyError` first), so for that one class "nothing committed for this
entry" is a true claim — and relabelling it `unknown` would turn a truthful 2 into a false 3,
"Cloudflare was left partially changed", PD#1 in the other direction.

**Validation failure is deliberately NOT an exception.** It is a tally of verdicts that `main()`
returns 2 on. *Intent:* an invalid file is an expected outcome of a read-only pass, not an error
condition, and modelling it as a raise would make §3's "nothing was changed" guarantee depend on
an exception path rather than on control flow.

**One deliberate, NARROWED reversal of a sibling rule.** The sibling's `api_error_text()` states
that API error text **never** includes a response body, and CLAUDE.md repeats it. Its stated
reasons are two, and only one of them is about usefulness: *"a DNS-record body echoes record
contents **and an auth-failure body can echo the credential**."* Here the operator needs
Cloudflare's own diagnosis of a failed write ("record already exists", "content for A record is
invalid"), so `ApplyError` and `CloudflareReadError` re-admit it — under three rules, which
together are exhaustive:

1. **Only the SDK's structured `errors[].code` and `errors[].message` fields.** Never `str(e)`,
   never the raw body, never response headers, never `error_chain` or any other nested member.
2. **Never on an authentication or authorization failure.** On HTTP **401 or 403** the message is
   the class and the status code alone, exactly as `api_error_text()` produces today. *Intent:*
   this is precisely the response class the sibling's docstring warns can echo the credential, and
   an auth failure needs no per-record diagnosis — the run is misconfigured, not drifted.
3. **Each admitted `message` is truncated to 200 characters** and the count of errors is reported,
   so an unexpectedly large or repeating error array cannot turn an operator's terminal or log
   into a dump of arbitrary server-supplied text.

*Intent:* the first record-content reason is not a concern here — this script's operator already
holds the file describing those exact records. The credential reason is real, and rule 2 is what
keeps it closed. The copied `api_error_text()` therefore gains a *branch*, and its docstring must
say so; it is not replaced.

### 9.2 Run-record write failure — precedence rule

If the run record cannot be written, the error is named on stderr, and then:

| Situation | Exit |
|---|---|
| The run changed something (§8.1 `changed > 0`) | the earned code (0, 1 or 3) **stands** |
| The run changed nothing (a dry run, or an `already-applied`-only run) | **2** |

*Intent:* PD#1 in both directions. Exiting 2 after a for-real run that rewrote 200 FQDNs would
assert "nothing was changed" about production DNS, which is the worse lie; but a dry run whose only
deliverable was the record has genuinely failed to deliver it.

### 9.3 Interruption

A `KeyboardInterrupt` during pass 3 leaves the in-flight entry's outcome **`unknown`** — never
`failed`, never `not-attempted` — and every later entry `not-attempted`. The summary and the run
record are written, then exit 130. This holds at **every** stage inside `apply_entry`, including
after the batch call returned, which is why R6.3.1's enclosure catches `Exception` and not
`BaseException`.

During that final flush, SIGINT MUST be set to `SIG_IGN`, the same guard `abort_run()` uses in the
main program, so a second Ctrl-C cannot truncate the only record of what a destructive run did.

**Test caveat, load-bearing:** an in-process test of that path MUST
`monkeypatch.setattr(<module>.signal, "signal", …)`, or the rest of the pytest session silently
stops honoring Ctrl-C. CLAUDE.md records this as a live trap.

### 9.4 Interactions mapped (PD#4)

| Interaction | Behavior |
|---|---|
| Ctrl-C during pass 1 | nothing changed; summary + record; exit 130 |
| Ctrl-C between two entries in pass 3 | in-flight = none; applied so far recorded; rest `not-attempted`; exit 130 |
| Ctrl-C during a batch call | that entry `unknown`; exit 130; the record names it |
| Cloudflare rate limit / 5xx in pass 1 | `CloudflareReadError`, exit 2, nothing changed |
| Cloudflare rate limit / 5xx in pass 3 | `ApplyError`; earlier entries stay applied; exit 3 |
| The file was applied already, in full | every entry `already-applied`; exit 1; no call made |
| A record vanished between pass 1 and pass 3 | its id is stale; Cloudflare rejects the batch; `ApplyError`. **Assumption to falsify on the live canary (§15).** If a stale id is instead ignored silently, R6's post-apply verification is what catches it, and this row is rewritten. |
| Two runs of the same file concurrently | out of scope and unguarded; the second run's pass 1 sees the first's writes and aborts with `partially-applied` or `already-applied`. Stated so it is not mistaken for a designed property. |

---

## 10. What the script never does

Stated as flow, because absence is hard to review. **Exhaustive.**

1. It never performs a write call in a dry run (R2.6).
2. It never performs a write call before every selected entry has a valid verdict (R3.2).
3. It never continues past a failed write call (R3.4).
4. It never attempts to revert what it already applied (`PROMPT.md`, quoted in R3.4).
5. It never modifies the input file, or writes any file other than the run record.
6. It never reads a credential from the environment; credentials come from `[Cloudflare]` in the
   TOML through the copied `<{env …}` / `<{secret env …}` resolver, and the client is pinned
   against the ambient environment (§16).

---

## 11. Observability (PD#5)

### 11.1 Streams

`stdout` carries the report: the per-entry change lines, the `-v` bodies, and the summary block.
`stderr` carries `ERROR:` and `ATTENTION:` lines only. *Intent:* `> apply.log` then captures the
account of the change while problems still reach a watching operator.

Both streams get the sibling's guards, ported: `require_usable_streams()` refuses a closed stderr,
and the writers detach **only** a stream a real write has proven doomed — never unconditionally,
which discards a buffered line and, under pytest's fd-level capture, repoints the session's own
stream at `/dev/null`.

**Every stdout write MUST go through a guarded writer, not a bare `print`.** `report_line` covers
stderr; stdout needs its counterpart, and the moment the program writes its first stdout byte it
owes one. *Intent:* CPython's shutdown flush covers **both** std streams and turns a failure of
either into exit **120**, overriding whatever `main()` returned — so an `except OSError` arm that
correctly returns 2 is silently overridden by the interpreter unless the doomed stream has been
detached first. This is the **third** appearance of this class in this script family; CLAUDE.md
records the other two. **An in-process test cannot pin it** — pytest never tears the interpreter
down, so the shutdown flush never runs. The cover MUST be a real subprocess test, copying
`test_a_doomed_stdout_exits_2_not_120_in_a_real_subprocess` in
`tests/unit/test_find_platform_domains_cloudflare.py`, and it MUST redirect at something that
really fails (`/dev/full`), never `subprocess.DEVNULL`, which accepts every write.

### 11.2 Message table (exhaustive)

| Message | Verbosity | Stream |
|---|---|---|
| `FOR REAL -- changes WILL be made to Cloudflare` banner, before the first call | always | stderr |
| pass-1 progress: `<fqdn>: <verdict>` — the verdict word **only**, never the detail | `-v` | stdout |
| per-entry change line (§11.4) | always, both modes | stdout |
| `POST /zones/<id>/dns_records/batch` + the exact merged JSON body | `-v` | stdout |
| per-entry result in pass 3: `<fqdn>  applied`, or `<fqdn>  FAILED -- <reason>` / `<fqdn>  UNVERIFIED -- <reason>` / `<fqdn>  UNKNOWN -- <reason>` | always | stdout |
| per-entry, when the verdict is `already-applied`: `<fqdn>  already applied -- nothing to do` | always, both modes | stdout |
| every invalid verdict: `ATTENTION: <fqdn> <code>: <detail>` | **always, never `-v`-gated** | stderr |
| the validation-failure abort: `ERROR: N of M selected entries did not match Cloudflare's current state; NOTHING was changed. …` | always (that path only) | stderr |
| `--only` subset coverage: `ATTENTION: applying N of M entries in this file` | always | stderr |
| the summary block (§11.3) | always, every exit path | stdout |
| the run record's path | always | stdout |

*Intent for the `already-applied` row:* it is what tells an operator which entries a re-run skipped
— the affordance R4.2's carve-out exists to provide. It is deliberately **not** the §11.4 change
line, because there is no change to describe.

*Intent for the reason appearing on **both** streams:* a failing entry's reason is written to stdout
as part of its result line **and** to stderr as the `ERROR:` line. This is the one deliberate
duplication in this table, and it is not an oversight. §11.1's stated purpose for stdout is that
`> apply.log` captures the account of the change — a log recording *that* an entry failed and never
*why*, for a run that left production DNS partially rewritten, is not an account of anything. The
stderr copy exists for the different audience §11.1 names: the operator watching a terminal, who
must not have to scroll a 217-entry report to find out something broke.

### 11.3 The summary block

```
apply-platform-domains-cloudflare: direction=plan
  source: platform-domains-cloudflare-plan.json (generated 2026-08-01T00:22:23Z)
  mode:   DRY RUN -- no changes were made
  entries in file: 217   selected: 217   (entries are FQDNs, not Pantheon sites)
  applied 0   already applied 0   planned 217   failed 0   unverified 0   unknown 0   not attempted 0
  record: platform-domains-cloudflare-plan-run-20260803T142211Z.json
```

The `source` line prints the input file's own `generated.at`. *Intent:* the plan pins addresses
resolved at sweep time, and this spec deliberately does not re-resolve them (§20). The age of the
file is therefore the operator's only staleness signal, so it is printed on every run rather than
left to the file's mtime, which survives neither a copy nor `git add`.

**The `mode:` line MUST be derived from the tally, never from `--for-real` alone.** A dry run reads
`DRY RUN -- no changes were made`; a for-real run reads
`FOR REAL -- N of M entries changed`, where N is `applied + unverified + unknown` (§8.1's
`changed`) and M is the number selected. *Intent:* `FOR REAL -- changes were made` is a claim about
production DNS, and a for-real run that reached no entry — because every one was `already-applied`,
or because it aborted in validation — would assert a rewrite that never happened. Deriving it from
the tally makes the line true on every path.

### 11.4 The per-entry change line

```
a.umich.edu  zone abc123  CNAME live-umich-x.pantheonsite.io -> A 23.185.0.4 + AAAA 2620:12a:8000::4, 2620:12a:8001::4  (proxied, ttl 1)
```

Derived **entirely from the entry** — `delete_match` gives the left side, `body.posts` the right,
`zone_id` the zone. It shows the zone **id**, not the zone name: util3 §5.3's plan/revert entry
carries `zone_id` and nothing else about the zone (`zone_name` exists only in the *inventory*,
which this script never reads, per Global Constraint 5). Recorded explicitly so an implementer does
not add a zone-name lookup — that would be a second Cloudflare read per entry for cosmetics.

---

## 12. The run record

### 12.1 Name and location

`<input-stem>-run-<YYYYMMDDThhmmssZ>.json`, in the input file's directory. For
`platform-domains-cloudflare-plan.json` that is
`platform-domains-cloudflare-plan-run-20260803T142211Z.json`.

Named `-run-`, not `-applied-`, because a dry run writes one too. The timestamp is from the
`now_utc()` seam and makes a run incapable of clobbering a previous one.

The repository's existing `.gitignore` line `/platform-domains-cloudflare*.json` **already covers**
records written next to the conventional baseline, so no new ignore entry is required (§19).

### 12.2 Format

```jsonc
{
  "run": {
    "at": "2026-08-03T14:22:11Z",
    "tool": "apply-platform-domains-cloudflare",
    "direction": "plan",
    "source": "platform-domains-cloudflare-plan.json",
    "source_generated_at": "2026-08-01T00:22:23Z",
    "for_real": true,
    "argv": ["--for-real", "platform-domains-cloudflare-plan.json"],
    "exit_code": 3,
    "entries_in_file": 217,
    "selected": 217,
    "counts": {"applied": 12, "already-applied": 0, "planned": 0, "failed": 1,
               "unverified": 0, "unknown": 0, "not-attempted": 204}
  },
  "entries": {
    "a.umich.edu": {"outcome": "applied", "at": "2026-08-03T14:22:13Z",
                    "deleted_ids": ["9f1c…"], "created_ids": ["a1b2…", "c3d4…", "e5f6…"]},
    "b.umich.edu": {"outcome": "failed", "at": "2026-08-03T14:22:14Z",
                    "error": "batch rejected: 81058 An identical record already exists."},
    "c.umich.edu": {"outcome": "not-attempted"}
  }
}
```

`outcome` is exhaustively one of `applied`, `already-applied`, `planned`, `failed`, `unverified`,
`unknown`, `not-attempted`. `created_ids` come from the post-apply verification listing (the authoritative
read), not from the batch response. Serialization goes through one `dump_json()` copied from the
sibling — sorted keys, 4-space indent, trailing newline — and the file is written with
`write_json_atomic()` (temp file + `os.replace`).

### 12.3 Determinism note (PD#14)

`run.at`, each entry's `at`, and the filename are non-deterministic. Tests MUST monkeypatch
`now_utc()` rather than normalizing after the fact, so a golden compares real bytes.

---

## 13. Seams under test — named and agreed, before implementation

Named **here** because implementation is test-first and an implementer subagent runs with fresh
context and cannot ask. The test file loads the script fresh per test via `SourceFileLoader`, the
idiom `tests/unit/test_find_platform_domains_cloudflare.py` already uses, which is what makes
monkeypatching module attributes safe and leak-free.

| Seam | Kind | Covers |
|---|---|---|
| `FakeCloudflareClient` | test fixture, adapted from the sibling's | **all** Cloudflare I/O: `dns.records.list` (honoring the `name`/`type` filters) and `dns.records.batch`, recording every call with its arguments |
| `now_utc()` | module attribute | every timestamp and the run-record filename |
| `sleep` | module attribute | R6.2's verification retry — no test may take 2 real seconds |
| an autouse **teardown-asserted** guard | module-level in `tests/unit/test_apply_platform_domains_cloudflare.py` (this module only — it makes no promise about any other test file) | fails the test if any **real outbound HTTP request** is attempted |

*Intent for the teardown-asserted guard:* the sibling shipped two tests that were green while
silently reaching real DNS, and then a replacement guard that could be satisfied by accident once
`main()` grew a catch-all. Asserting at teardown, not inside the run, is the shape that survived.
**Measured here, and it is why teardown is not a stylistic choice:** the Cloudflare SDK's own retry
loop (`cloudflare/_base_client.py`, `except Exception as err:`) swallows an inline `AssertionError`
and retries — three times — before converting it to an `APIConnectionError`. An in-run assertion is
eaten by the library under test.

*Intent for narrowing to outbound requests only:* the earlier wording also banned **constructing** a
real `Cloudflare` object. That is deliberately permitted. A constructed-but-unused client performs
no I/O, so banning it buys nothing the request interception does not already buy — and §16 requires
a real client to assert the environment pin against a real built request, which is the one thing a
construction ban would make impossible. The guard MUST additionally carry a **self-test** proving it
can still fire: it hooks the SDK's transport, so a transport change would otherwise make it
**silently inert**, which is CLAUDE.md's two-`sitecustomize.py` failure exactly.

**Pure helpers to extract** (no I/O, unit-testable directly — the discipline that produced
`overage_blocks`, `plan_costs`, `sites_from_resume_point` in the main program and `classify`,
`record_body`, `plan_entry` in the sibling):

| Helper | Returns |
|---|---|
| `read_apply_file(path)` | the parsed document; raises `PlanFileError` |
| `check_file_contract(doc, path)` | the **direction** (`"plan"` or `"revert"`); raises `PlanFileError` on any §6 check. Returning it rather than `None` avoids re-deriving what §11.3 and §12.2 both require |
| `select_entries(entries, only)` | the selected `{fqdn: entry}`; raises `StartupError` naming every miss (R7.3) |
| `normalize(name)` | copied from the sibling |
| `record_key(rtype, name, content)` | the §7.1 comparison key |
| `governed_records(rows)` | the subset of a list response that forms R |
| `verdict_for(entry, rows)` | `(verdict, detail)` per §7.3 |
| `merge_body(entry, delete_ids)` | the postable batch body (R5.1) |
| `describe_change(fqdn, entry)` | the §11.4 line |
| `verify_records(entry, rows)` | `True` when R == P (R6.1) |
| `outcome_document(...)` | the §12.2 document |
| `outcome_path(input_path, at)` | the §12.1 path |
| `summary_lines(*, direction, source, source_generated_at, for_real, entries_in_file, selected, counts, record_path)` | the §11.3 block. All **keyword-only** |
| `changed_count(counts)` | §8.1's `changed` — `applied + unverified + unknown`. **One definition**, called by both `exit_code_for` and `summary_lines`, which each computed it separately until the Task 8 review |
| `exit_code_for(counts)` | §8's code, from the tally alone. **One argument** — there is no `failed` parameter; the failure terms are in `counts` |

`apply_entry(client, fqdn, entry, delete_ids)` and `records_at_name(client, zone_id, fqdn)` are
the only I/O functions; they are listed here so the extraction list is complete, and are covered
through the fake client.

---

## 14. Test plan

All offline, `unit` tier, in `tests/unit/test_apply_platform_domains_cloudflare.py`.

| # | Group | Cases |
|---|---|---|
| 1 | file contract | one test per §6 check (8), including an `-excluded.json` refused by name and a `deletes`-in-body refusal |
| 2 | `--only` | selection; an unmatched name is fatal and **every** miss is named; the subset ATTENTION line; `--only` matching after `normalize()` |
| 3 | `verdict_for` | one test per §7.3 row (6); plus: an IPv6 address written two ways is one record; a trailing dot and a case difference do not split a key; an unrelated `TXT` at the name blocks nothing; row 1 evaluated before the set comparisons |
| 4 | `merge_body` | `deletes` built from the resolved ids; `posts` passed through **byte-identical** to the file; nothing else added |
| 5 | dry run | **zero** batch calls, asserted against the fake client's recorded calls; the report is printed; exit 0; a `planned` tally |
| 6 | for-real happy path | `batch()` called once per entry with exactly the expected `zone_id`/`deletes`/`posts`; post-verify runs; exit 0 |
| 7 | failure mid-apply | entry 3 fails → 1–2 `applied`, 3 `failed`, 4..N `not-attempted`, exit **3**; entry 1 fails → `changed == 0` → exit **2** |
| 8 | unknown outcome | a connection error on entry 2 → outcome `unknown` → exit **3** (never 2) |
| 9 | post-apply verification | mismatch → one `sleep` + one re-list (asserted), then **`VerifyError`**; a mismatch that resolves on the retry succeeds; a bare `ApplyError` in the same position yields `failed`/exit 2 while a `VerifyError` yields `unverified`/exit 3 — assert **both**, since that pair is the whole reason the subclass exists; a `TimeoutError`/`OSError` from the verification **read** yields `unverified`, never `unknown` (R6.3) |
| 10 | interruption | Ctrl-C in pass 1 → exit 130, nothing changed; Ctrl-C during a batch → that entry `unknown`, rest `not-attempted`, summary and record still written; `signal.signal` monkeypatched (§9.3) |
| 11 | `exit_code_for` | the full truth table: clean, already-applied-only, dry run, failure with and without prior applies, unknown-only |
| 12 | run record | written on every exit path (success, validation failure, apply failure, interrupt); dry-run variant with `for_real: false`; both branches of the §9.2 precedence rule |
| 13 | credentials | the copied `build_client()` pin asserted against a **real built request**: an ambient `CLOUDFLARE_BASE_URL`, `CLOUDFLARE_EMAIL` and `CLOUDFLARE_CUSTOM_HEADERS` are all ignored; the configured credential alone is sent |
| 14 | streams and exit taxonomy | a doomed stdout and a doomed stderr each produce a named exit 2, not 120; `--help` still documents `--for-real` and `--only` |
| 15 | error text (§9.1) | a 401 and a 403 report the class and status **only**, with no `errors[]` content; a 400 reports `errors[].code` and a truncated `message`; a 300-character message is truncated to 200; `str(e)` never appears in any message |

**NEVER-block — tests are load-bearing (PD#14).** Every new test MUST be observed failing for the
**right reason** before its implementation is written. NEVER weaken an assertion to make it pass,
NEVER delete a test to make a suite green, and NEVER regenerate a golden without a reviewed diff.
Group 5's "zero batch calls" and group 13's pin are the two assertions most likely to be green for
the wrong reason; each MUST be shown red under a deliberate mutation (make the dry run call
`batch()`; drop one of the three pins) and the red output pasted into the task report.

`tests/unit/test_find_platform_domains_cloudflare.py` and
`tests/unit/test_find_platform_domains_dns.py` MUST stay untouched and green. If either moves,
something was modularized that Global Constraint 1 forbids.

---

## 15. Acceptance criteria

Exact commands. To be **run and their real output pasted into this section** before the work is
submitted; an unrun acceptance suite is PD#14 exactly.

### Offline (no gate)

```bash
# 1. Full suite, offline tier.  Expected: the pre-change count + this file's tests, 0 failed;
#    ruff and pyright clean.
./run-tests --fast

# 2. This utility's own file.
./run-tests --fast tests/unit/test_apply_platform_domains_cloudflare.py

# 3. Both siblings MUST be untouched.
git diff --stat find-platform-domains-dns find-platform-domains-cloudflare \
    tests/unit/test_find_platform_domains_dns.py \
    tests/unit/test_find_platform_domains_cloudflare.py
#    Expected: empty output.

# 4. An excluded file is refused by name.
./apply-platform-domains-cloudflare platform-domains-cloudflare-excluded.json ; echo "exit=$?"
#    Expected: ERROR naming the direction, exit=2, no Cloudflare call made.

# 5. --help documents FILE, --only, --for-real and the exit codes.
./apply-platform-domains-cloudflare --help

# 6. A dry run against the real baseline plan file makes NO write call (and needs credentials
#    only for reads).  Expected: the full report, the summary, a run record, exit 0 or 1 or 2.
./apply-platform-domains-cloudflare -v platform-domains-cloudflare-plan.json ; echo "exit=$?"
```

### Live canary — gated behind STOP 2 (§21)

Follows `development/2026-07-30-platform-domain-util2/research.md`'s own verification procedure
rather than inventing one. **One throwaway hostname**, chosen with the human, referred to below as
`$FQDN`.

```bash
# 7. Refresh the baseline immediately before the rewrite (the sibling; ~2 minutes).
./find-platform-domains-cloudflare -o /tmp/canary

# 8. BEFORE: certificate pack and served leaf certificate.
#    (zone id from the inventory entry for $FQDN)
#    GET /zones/{zone_id}/ssl/certificate_packs?status=all   -- record id, status, hosts
openssl s_client -connect "$FQDN:443" -servername "$FQDN" </dev/null 2>/dev/null \
  | openssl x509 -noout -serial -dates -subject

# 9. Apply the plan for that one hostname.
./apply-platform-domains-cloudflare -v --only "$FQDN" --for-real /tmp/canary-plan.json
echo "exit=$?"

# 10. AFTER (immediately, then again at ~15 min): repeat 8 and diff.  Expect an identical pack
#     id, status active, and an IDENTICAL certificate serial -- the same certificate, not a
#     re-issued one.  Confirm the DNS answer changed and HTTPS still serves.
dig +short A "$FQDN" ; dig +short AAAA "$FQDN" ; curl -sSI "https://$FQDN" | head -1

# 11. Re-run the SAME plan file.  Expected: every selected entry already-applied, exit 1,
#     zero batch calls.  This is the R4.2 property, live.
./apply-platform-domains-cloudflare --only "$FQDN" --for-real /tmp/canary-plan.json ; echo "exit=$?"

# 12. Revert the same hostname and repeat 8/10, proving the round trip.
./apply-platform-domains-cloudflare -v --only "$FQDN" --for-real /tmp/canary-revert.json
echo "exit=$?"

# 13. The assumption in §9.4's stale-id row, falsified deliberately: apply the plan, then
#     apply the SAME plan a second time with a hand-edited stale delete id, and observe
#     whether Cloudflare rejects the batch loudly.  Record the real answer here.
```

Item 13 is the one place this design rests on an unverified claim. Cloudflare's documentation
search returned nothing on batch error semantics for a non-existent delete id, so the claim is
carried as an assumption and falsified here. If a stale id is silently ignored, §9.4's row is
rewritten and R6's post-apply verification becomes the sole guard — which it already is in
practice.

### Results — items 1–6, run 2026-08-04 after Task 10

**Item 1 — full offline suite.**

```
107 snapshots passed.
========= 1639 passed, 3 skipped, 2 deselected, 15 warnings in 39.39s ==========
Linting (ruff, campaign ratchet) ...
Type-checking (pyright, campaign ratchet) ...
exit=0
```

**Item 2 — this utility's own file.** `164 passed`, ruff and pyright clean.

**Item 3 — both siblings untouched.** `git diff --stat` over the whole branch for
`find-platform-domains-dns`, `find-platform-domains-cloudflare` and both their test files:
**empty output**.

**Item 4 — an excluded file is refused by name.** Note that the summary block and the run record
are produced on this fatal path too (R8.1/R9.1):

```
ERROR: platform-domains-cloudflare-excluded.json is an EXCLUDED file (generated.direction is
'excluded'), not a plan or a revert.  An excluded file records why FQDNs got no rewrite
instructions; it carries no request body and there is nothing to apply.
apply-platform-domains-cloudflare: direction=unknown
  source: platform-domains-cloudflare-excluded.json (generated unknown)
  mode:   DRY RUN -- no changes were made
  entries in file: 0   selected: 0   (entries are FQDNs, not Pantheon sites)
  applied 0   already applied 0   planned 0   failed 0   unverified 0   unknown 0   not attempted 0
  record: platform-domains-cloudflare-excluded-run-20260804T020342Z.json
exit=2
```

**Item 5 — `--help`.** Documents `FILE`, `--only`, `--for-real` ("WITHOUT THIS FLAG NOTHING IS
CHANGED") and all five exit codes.

**Item 6 — a live dry run against the real 217-entry baseline plan.** Read-only; **zero batch
calls**, by construction and by R2.6's test. Exit **0**:

```
apply-platform-domains-cloudflare: direction=plan
  source: platform-domains-cloudflare-plan.json (generated 2026-08-01T00:22:23Z)
  mode:   DRY RUN -- no changes were made
  entries in file: 217   selected: 217   (entries are FQDNs, not Pantheon sites)
  applied 0   already applied 0   planned 217   failed 0   unverified 0   unknown 0   not attempted 0
  record: platform-domains-cloudflare-plan-run-20260804T020610Z.json
```

**stderr was empty — all 217 entries validated `ready` against live Cloudflare state**, three days
after the plan was generated. This is the strongest end-to-end signal available without STOP 2:
217 real FQDNs across 187 zones, each read back through `records_at_name` and compared by
`record_key`, with no `record-ambiguous`, `partially-applied`, `unexpected-records` or
`records-missing` verdict anywhere.

The run record it wrote carries all eleven `run` fields, `for_real: false`, `exit_code: 0`,
`entries_in_file: 217`, `selected: 217`, a zero-filled seven-key `counts` with `planned: 217`, and
one entry per FQDN. `git check-ignore -v` confirms §12.1's claim on the real filename:

```
.gitignore:11:/platform-domains-cloudflare*.json  platform-domains-cloudflare-plan-run-20260804T020610Z.json
```

**Items 7–13 remain unrun** — they are destructive and gated behind STOP 2 (§21), which requires
the exact phrase `RUN LIVE` **and** a named throwaway hostname.

---

## 16. Security (PD#6)

- **No new credential path.** `[Cloudflare]` resolution and the `build_client()` environment pin
  are copied unchanged from the sibling. The pin closes four routes by which ambient environment
  values reach the wire — `auth_headers` credential precedence, `default_headers`,
  `$CLOUDFLARE_CUSTOM_HEADERS`, and `$CLOUDFLARE_BASE_URL` redirecting a configured credential to
  an arbitrary host. Group 13 asserts it against a **real built request**, not against the
  attribute assignments that implement it.
- **This is the ONLY one of the three copies that performs writes**, which raises the stakes of the
  `$CLOUDFLARE_BASE_URL` route from "credential disclosure" to "credential disclosure plus a
  rewrite aimed at an attacker-chosen host." The pin is therefore load-bearing here in a way it is
  not in the read-only siblings, and §14 group 13 is not optional.
- **No credential reaches a file.** The run record contains record ids, FQDNs, outcomes and
  `argv`; `argv` carries a config **path** and FQDN names, never a secret, because credentials are
  only ever read from the config file.
- **Error text is narrowed, not widened.** §9.1's reversal admits exactly two structured fields
  from a Cloudflare error response, truncated, and **nothing at all on an HTTP 401/403** — the
  response class the sibling's own docstring identifies as able to echo the credential. §14
  group 15 tests that a 401 and a 403 report the status code alone.
- **No new outbound channel.** Unlike the sibling, this script performs **no DNS resolution at
  all** (§20). Its only network peer is the Cloudflare API.

---

## 17. Copied code inventory (Global Constraint 1)

From `find-platform-domains-cloudflare`, copied verbatim or near-verbatim:

| What | Why |
|---|---|
| `point_at_devnull`, `report_line`, `require_usable_streams` | the doomed-stream guards that keep the exit taxonomy from being hijacked by a failed shutdown flush |
| `normalize` | the FQDN comparison rule, shared with the file format |
| `StartupError`, `InvariantError`, `OutputWriteError` | the exception spine |
| `MARKER_RE`, `resolve_env_marker`, `resolve_config_value` | the `<{env …}` / `<{secret env …}` resolver |
| `build_client`, `cloudflare_client` | credentials and the environment pin. **One deliberate divergence from the sibling** — see below |
| `api_error_text` | narrowed per §9.1 |
| `dump_json`, `write_json_atomic` | the run-record serializer and atomic write |
| `main()`'s handler-chain shape | the exit taxonomy (§8.3) |

**`build_client`'s credential-nulling test diverges from both other copies, deliberately.** This
copy nulls a field when `creds.get(field) is None`; the sibling and `plugin/cloudflare/client.py`
both null it only when `field not in creds`. Measured: an **explicit** `api_email=None` is *in*
`creds`, so the `not in` form leaves it for the SDK to back-fill, and an ambient
`CLOUDFLARE_EMAIL`/`CLOUDFLARE_API_KEY` reaches a real built request — routes 1 and 2 of the
four-route pin, reopened, on the one copy that performs writes.

**It was latent in all three, not live in any:** every caller guards
(`cloudflare_client` here, `build_client()` in the plugin) and exits before it can pass `None`. But
`build_client`'s own docstring claims it "uses EXACTLY the credentials the config supplied", and
under the `not in` form that claim is false for an explicit `None` — so the change makes the
docstring true rather than merely intended, and is what lets §14's new
`build_client(api_email=None, api_key=None)` test pin the idiom itself rather than the caller's
guard.

**Status of the other two copies, as of 2026-08-04:**

| Copy | Form | Why |
|---|---|---|
| `plugin/cloudflare/client.py` (`pinned_client`) | **fixed** — `creds.get(field) is None` | The main program's pin. Not scheduled for deletion, and it runs unattended against production monthly, so it got the same fix and its own real-SDK test (`test_pinned_client_nulls_an_explicit_none_credential`) |
| `find-platform-domains-cloudflare` (`build_client`) | still `field not in creds` | **Deliberately left.** That utility is read-only — it never writes to Cloudflare — and is deleted with this one after the CDN migration. Fixing it would mean touching a script three reviews have verified byte-identical to its original, for a hole its own caller already guards, on a path that cannot write. Recorded here so the divergence is a decision rather than an oversight (PD#9) |

**Not copied, deliberately:** `read_all`, `read_page_once`, `expected_record_count`, `ListTally`
and the completeness cross-check (~120 lines). They exist to survive paginating a whole zone;
this script lists one FQDN at a time and never paginates. *Intent:* recorded so a reviewer does
not read their absence as an oversight, and so nobody reintroduces whole-zone listing (§18's
rejected approach).

**Not copied:** `resolve`, `resolve_retrying`, `resolve_target`, `sorted_addresses`, `classify`
and the range constants. This script does no DNS work (§20).

---

## 18. Documentation to update, in the same change

| File | Change |
|---|---|
| `CLAUDE.md` | A new `### apply-platform-domains-cloudflare (temporary utility)` subsection: the three passes, the verdict table, the exit taxonomy **including that this script adds 3 and why**, the run record, `--for-real` as the blast-radius gate, and the deletion pointer. Also: the "**two** places to check on a Cloudflare SDK upgrade" sentence becomes **three** (§5); and the `find-platform-domains-cloudflare` subsection's "a separate, not-yet-written *applier* script" sentence now names this one. |
| the script's module docstring | the same, in brief, plus the copied-code inventory rationale |
| `development/2026-07-31-platform-domain-util3/SPEC.md` | a pointer at §5.4 to this spec, recording that §5.4's per-entry tolerance was superseded by R4 |
| `development/2026-07-30-platform-domain-util2/SPEC.md` §11 | the deletion checklist gains this script's share (§19) |
| this folder | `PROMPT.md`, `SPEC.md`, `PLAN.md`, and — at session end via `/archive-session` — the scrubbed transcript and statistics |

---

## 19. Deletion checklist delta

`development/2026-07-30-platform-domain-util2/SPEC.md` §11 remains the master checklist. This
script adds:

1. `git rm apply-platform-domains-cloudflare apply-platform-domains-cloudflare.py`
2. `git rm tests/unit/test_apply_platform_domains_cloudflare.py`
3. `pyproject.toml`: remove the two `[tool.ruff.lint.per-file-ignores]` entries
   (`"apply-platform-domains-cloudflare.py"` and the extension-less twin) and the
   `[tool.pyright].include` entry
4. `.claude/hooks/ruff-check.sh`: remove the `"$REPO_ROOT/apply-platform-domains-cloudflare"` case
   arm
5. `CLAUDE.md`: remove the subsection, and revert "three places" to "two" if the other two survive
   (they will not — all three go together)
6. **No `.gitignore` change is required** — `/platform-domains-cloudflare*.json` already covers the
   run records written beside the conventional baseline (§12.1)

**Deletion stays `git rm` of THREE files** (the script, its `.py` symlink, its test file) **plus three textual edits** (`pyproject.toml`, `.claude/hooks/ruff-check.sh`, `CLAUDE.md`). No new source module, no package,
nothing imported from `psh/`.

---

## 20. NOT in scope

Each with the reasoning preserved, so a later session does not re-litigate it.

| Item | Why not |
|---|---|
| **Re-resolving each plan entry's target to detect a stale plan** | Offered as an expansion and **declined** in the design conversation: the file is the authority. Mitigated by printing the input file's `generated.at` on every run (§11.3) and by the operator discipline CLAUDE.md already states — regenerate the baseline immediately before a rewrite. This also keeps the script free of any DNS dependency (§16). |
| Auto-reverting entries already applied when one fails | `PROMPT.md` forbids it: *"it should not attempt to revert any changes it has already made."* |
| Applying more than one file per invocation | One file, one direction, one decision (Global Constraint 5). |
| Interactive y/N confirmation | `--for-real` is the blast-radius gate, matching the main program's primary safety mechanism. An interactive prompt would also break any scripted use. |
| Concurrency, pacing, retry-on-rate-limit, batching entries together | `PROMPT.md`: no performance work. A rate-limit response is a named failure (§9.1), not something to smooth over. |
| Validating by re-walking each zone's full record list | Measurably worse: util3 measured **2 duplicates and 2 misses in one walk** of an 18,848-record zone, and a miss would produce a *false* validation failure. It also needs ~229 page fetches across 187 zones against ~217 single-name lists, and drags in the ~120 lines §17 deliberately does not copy. |
| Certificate-pack verification inside the script | `research.md`'s procedure is an operator runbook step (§15 items 8/10); automating it adds an SSL API surface to a script scheduled for deletion. |
| Editing, filtering or regenerating plan files | That is `find-platform-domains-cloudflare`'s job. `--only` selects; it never rewrites. |
| Guarding against two concurrent runs of the same file | Unguarded and stated in §9.4 rather than silently absent. |
| Requiring the operator to *declare* the direction (`--plan` / `--revert`) | util3 SPEC §5.4 step 1 says to refuse a file whose `generated.direction` is not *"the direction the operator asked for"*, which presumes the operator asks. Here the header is the authority: the direction is read from it, an `"excluded"` or absent value is fatal by name (§6 check 2), and the direction is printed as the first line of the summary and echoed in the run record. A redundant flag would add a way to be wrong without adding a way to detect it. |
| De-U-M-ifying anything | This utility is institution-neutral already; it reads a config file. |

---

## 21. Approval gates (structural STOPs)

**STOP 1 — spec approved.** Implementation MUST NOT begin until the human replies with the exact
phrase `SPEC APPROVED`. The spec MUST be committed before the first implementation commit, so
there is a baseline to diff against.

**STOP 2 — live canary.** §15 items 7–13 make **real, destructive changes to production DNS**.
They MUST NOT be run until the human replies with the exact phrase `RUN LIVE` **and** has named
the throwaway hostname to use. Items 1–6 are offline (item 6 needs read-only credentials) and need
no gate.

**STOP 3 — adversarial review.** A `psh-reviewer` subagent with **fresh context**, seeing only this
spec and the diff, reviews before merge, per `prompts/adversarial-review.md`.

---

## 22. Closing audit questions — ANSWERED 2026-08-04

Evidence: the ten per-task reports and reviews in `.superpowers/sdd/PLAN/`, the whole-branch review
and its fix wave (`final-fix-report.md`), the ledger (`progress.md`), and the code at `HEAD`
(`a039384..250e517`, 36 commits, no branch created per `CLAUDE.md`).

**The dominant finding across all ten tasks: the production code was almost always right, and the
tests proving it were repeatedly wrong.** Every Critical and Important finding on this branch —
without exception — was located by a reviewer mutating the implementation and watching the suite
stay green. Two sub-shapes recurred often enough to be named as classes: a fixture whose entries
are homogeneous or whose two numbers are equal (so a transposition or an early loop exit is
undetectable), and an assertion on a failure path that can be deleted with the suite green. The
second appeared in seven of the ten tasks.

1. **Was every new test observed failing for the right reason before its implementation existed?**

   Yes for every task's initial submission — each report pastes the RED run, and the reviewers
   re-ran a sample rather than trusting the paste. **Two disclosed exceptions, neither papered
   over.** Task 1's honest RED was a collection error (the script did not exist yet), stated as such
   rather than dressed as a per-assertion failure. And the ~40 tests added during *fix* rounds were
   necessarily written after the code they cover — for those the discipline was inverted and
   arguably stronger: each was proven by re-applying the reviewer's own mutation, watching the new
   test go red, and pasting it. Several fix rounds existed *only* because a test could not fail.

2. **Was group 5's "a dry run makes zero write calls" shown red under a deliberate mutation?**

   Yes, three times by three parties: the Task 7 implementer (mandatory Step 6), the Task 7
   reviewer (which additionally ran the gate *inverted* and the gate *correct*, and swept `--only`
   on already-applied, ready, mixed, `-v`, invalid-beside-ready, plan and revert — `batch_calls ==
   []` in every one), and the final reviewer. The property holds structurally too: there is exactly
   one `dns.records.batch` call site in 1560 lines.

3. **Was each of the three environment pins mutation-tested independently?**

   Yes — and the first attempt was a **dead instrument**, which is the substantive answer. Task 3
   shipped attribute-state assertions (`client._custom_headers == {}` asserted immediately after the
   line that assigns it). The reviewer simulated the SDK refactor `build_client`'s docstring warns
   about and showed **all four assertions green while `x-auth-email: attacker@evil.example` reached
   the wire**. The replacement asserts a real built request; each pin was then reddened
   independently, twice more in later rounds. The email+key branch was wire-asserted only in the
   final fix wave (finding M7).

4. **Does `exit_code_for` have a test per row of §8, each with a distinct tally?**

   Yes, verified by the Task 6 reviewer running a mutation per return value and by the final
   reviewer. The `unknown`-only row exists and is distinct. Note §8 grew a row *during*
   implementation: `unverified` (§8.1), added after Task 8's implementer escalated a contradiction
   between R6.3 and the old `changed` formula — a lone verification mismatch produced `{failed: 1}`,
   `changed == 0`, and **exit 2, the code meaning "nothing was changed", for a batch that had
   returned 200 and therefore committed.** `failed` was carrying two opposite meanings.

5. **Did the live canary confirm or refute the stale-delete-id assumption (§9.4)?**

   **Unanswered — blocked on STOP 2, which has not been unlocked.** §15 items 7–13 are unrun. The
   assumption stands as written, with R6's post-apply verification as the actual guard. This is the
   one place the design still rests on an unverified claim, and it is disclosed rather than closed.

6. **Is the script free of any DNS resolution (§20)?**

   Yes — but **the evidence originally pasted here was not what the quoted command produces**, and
   that is worth recording rather than quietly correcting: this answer claimed "three matches, all
   prose" where the command returns **eight**, three of them live code. The conclusion was right and
   the audit trail was wrong, in the one section whose entire job is to be auditable. §22's own
   preamble names "the tests proving it were repeatedly wrong" as this branch's dominant failure
   class; this is that class landing in the audit itself (PD#14 — *"applies at design time too — to
   a new counter, artifact, or notice — not only in tests"*). Found by the post-merge review.

   The real output, re-run at HEAD:

   ```
   $ git grep -c "dns\.\|resolve(" -- apply-platform-domains-cloudflare
   8
   ```

   All eight are one of two things, and neither is name resolution:

   - **Five are prose** — docstring references to the sibling `find-platform-domains-dns`, the
     `# Path.resolve() follows symlinks` comment on `write_json_atomic`, and two docstrings
     describing the SDK's pagination and its typed batch entry point.
   - **Three are live code**, and all three are the **Cloudflare SDK's own `dns.records.*`
     namespace** — `records_at_name`'s `client.dns.records.list(...)`, and `apply_entry`'s
     `client.dns.records.batch(...)` and its verification `list(...)`. That is Cloudflare's
     resource path for DNS *records*, not a resolver.

   No `dns.resolver` import, no `dnspython` dependency, no lookup of any kind. The script's only
   network peer is the Cloudflare API — which is what §20 requires and what makes the sibling's
   whole resolver layer (`resolve`, `resolve_retrying`, `resolve_target`, `sorted_addresses`,
   `classify`) correctly absent from §17's copy inventory.

7. **Line count, and did "copy, don't modularize" start costing more than it saves?**

   `apply-platform-domains-cloudflare` is **1560** lines with 53 top-level defs/classes; its test
   file is **2449** lines / 164 tests. For scale, the sibling it copies from is **1620** lines. So
   the third copy did not make the rule more expensive than it already was — the shared surface is
   eight small helpers (§17), each verified byte-identical in behavior by the final reviewer, and
   deletion stays `git rm` of three files plus three textual edits. **Recorded, not acted on, per the
   question's own instruction.** The one real cost is that an SDK upgrade now has three pin sites to
   re-verify instead of two; `CLAUDE.md` says so explicitly.

8. **Did any test in the two sibling test files change?**

   No. `git diff --stat 33b2ba8..HEAD` over `find-platform-domains-dns`,
   `find-platform-domains-cloudflare` and both their test files is **empty** — byte-identical across
   all 37 commits, checked at every task boundary and again at merge.

### Closing audit questions (original list, for reference)

1. Was every new test observed failing for the **right reason** before its implementation existed?
   Which ones were not, and why — quoted from the task reports, not summarized?
2. Group 5 asserts a dry run makes zero write calls. Was that assertion shown red under a
   deliberate mutation (a dry run that calls `batch()`)? Paste the red output.
3. Group 13 asserts the environment pin against a real built request. Was each of the three pins
   mutation-tested independently? A set-intersection version of that assertion silently missed the
   `_custom_headers` route in the sibling.
4. Does `exit_code_for` have a test for every row of §8, including the `unknown`-only row, and does
   each test use a **distinct** tally rather than one fixture with the expectation edited?
5. Did the live canary (§15 item 13) confirm or refute the stale-delete-id assumption in §9.4?
   Record the real answer and update that row.
6. Is `git grep -n "resolve\|dns\." apply-platform-domains-cloudflare` free of any DNS resolution?
   (§20 — this script must have no DNS dependency at all.)
7. How many lines did the script reach, and did the "copy, don't modularize" rule start costing
   more than it saves across three scripts now sharing `build_client`, `report_line` and
   `normalize`? Record the number; do not act on it.
8. Did any test in the two sibling test files change? `git diff --stat` them; expected empty.

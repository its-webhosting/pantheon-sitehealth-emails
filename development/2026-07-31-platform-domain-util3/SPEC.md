# `find-platform-domains-cloudflare` — rewrite plan & revert files

**Spec & implementation plan.** Third increment on the temporary
`find-platform-domains-cloudflare` utility. The prompt is `PROMPT.md` in this folder; the two
prior increments are `development/2026-07-30-platform-domain-util2/` (this script's origin) and
`development/2026-07-28-platform-domain-util/` (its `find-platform-domains-dns` sibling).

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

Each term is used exactly once per concept, here and in the code.

| Term | Meaning |
|---|---|
| **platform domain** | A hostname ending in `.pantheonsite.io`. **Nothing else.** `*.pantheon.io` and `*.gotpantheon.com` are explicitly out of scope (R1). |
| **platform CNAME** | A Cloudflare DNS CNAME record whose `content` is a platform domain. The only record type this utility ever reads, plans, or touches. |
| **FQDN** | The `name` of a platform CNAME — the custom hostname a site is served on. |
| **target** | The platform domain a platform CNAME points at, e.g. `live-umich-x.pantheonsite.io`. |
| **resolution** | The A and AAAA rrsets obtained by resolving a *target* through DNS, following CNAME chains. |
| **inventory** | `<basename>.json`, or the JSON on stdout. The record of Cloudflare state. |
| **plan** | `<basename>-plan.json`. Forward rewrite: platform CNAME → A/AAAA. |
| **revert** | `<basename>-revert.json`. Reverse rewrite: A/AAAA → platform CNAME. |
| **excluded** | `<basename>-excluded.json`. Every FQDN that got no plan entry, with a reason code. |
| **entry** | One FQDN's object inside any of the four files. |
| **exclusion** | The act of denying an FQDN a plan entry. Always carries one **reason code** (§6). |
| **ambiguous** | An FQDN with more than one platform CNAME, in one zone or across two zones. |
| **applier** | The separate, **not-yet-written** script that reads a plan or revert file and calls the Cloudflare API. Out of scope here; §5.4 is its normative contract. |
| **basename mode** | `-o/--output-basename` was given. Four files are written. |
| **stdout mode** | No `-o`. The inventory goes to stdout; no other file is produced. |
| **provenance header** | The `generated` object at the top of the plan, revert and excluded files (§5.5). |
| **match block** | `delete_match` — the record identity an applier resolves to a record id at apply time (§5.4). |

---

## 1. What this is and why

The utility today sweeps Cloudflare and writes an **inventory** of every platform CNAME. This
increment makes it also emit the **rewrite instructions**: for each FQDN, the exact Cloudflare
batch call that swaps its platform CNAME for the A/AAAA records the target actually resolves to,
and the exact call that undoes it.

**Why the swap is needed at all** is Pantheon's Fastly → Pantheon-Cloudflare CDN migration; the
research behind the record-level mechanics is
`development/2026-07-30-platform-domain-util2/research.md`, whose "Recommended mechanics: one
batch call" section this spec implements.

**Why the replacement addresses are resolved rather than constant.** `research.md` shows a single
address set (`23.185.0.4` / `2620:12a:8000::4` / `2620:12a:8001::4`). That is one of several.
Measured live on 2026-07-31:

```
live-bus-occb.pantheonsite.io.            600 IN CNAME fe4.edge.pantheon.io.
fe4.edge.pantheon.io.                     300 IN A     23.185.0.4
fe4.edge.pantheon.io.                     300 IN AAAA  2620:12a:8001::4
fe4.edge.pantheon.io.                     300 IN AAAA  2620:12a:8000::4

live-umich-its-wws-test1.pantheonsite.io. 3600 IN A    23.185.0.1
live-umich-its-wws-test1.pantheonsite.io. 3600 IN AAAA 2620:12a:8000::1
live-umich-its-wws-test1.pantheonsite.io. 3600 IN AAAA 2620:12a:8001::1
```

Two distinct sets, and two distinct *shapes* — one target is itself a CNAME into
`fe4.edge.pantheon.io`, the other answers address records directly. A hardcoded constant would be
wrong for most FQDNs. **Per-FQDN resolution is therefore load-bearing, not an optimization.**

Note also that the AAAA rrset came back **in a different order** on the two queries. §5.2's
sort rule exists because of this, not on principle.

**This utility NEVER calls the Cloudflare API to write anything.** It reads Cloudflare, reads
DNS, and writes files. Applying them is the applier's job (§5.4).

---

## 2. Global constraints

Carried forward from `development/2026-07-30-platform-domain-util2/SPEC.md` and restated here
only because they bound every task below.

1. **Standalone.** The script MUST import nothing from `psh/`, `check/`, `plugin/` or
   `script_context`. Code needed from the main program is **copied into the script**, not
   imported and not modularized, so deletion stays `git rm` of three files.
2. **Temporary.** Delete after Pantheon's CDN migration. The checklist is §13.
3. **No performance work.** Per `PROMPT.md`: "Do not put any significant amount of work into
   making this script fast or efficient."
4. **Test-first**, at the seams named in §7, per `prompts/implementation-standards.md` and
   `mattpocock-skills:tdd`.

---

## 3. Requirements

### R1 — Scope (exhaustive)

The utility MUST consider **only** Cloudflare CNAME records whose `content` ends in
`.pantheonsite.io`. It MUST NOT read, plan, revert, exclude, or mention records pointing at
`*.pantheon.io` or `*.gotpantheon.com`, or records of any other type.

*Intent:* stated as a requirement because the existing `PLATFORM_SUFFIX` constant already
enforces it and nothing must silently widen it later. No code change; a test pins it.

### R2 — `--output-basename`

R2.1 `-o/--output PATH` is **replaced** by `-o/--output-basename BASENAME`. `--output` becomes
an argparse error; `allow_abbrev=False` is already set, so no prefix match rescues it.

R2.2 A BASENAME whose **final path component contains a `.`** is fatal (exit 2) with a message
naming the offending value and showing a corrected example. Directory components MAY contain
dots.

| BASENAME | Result |
|---|---|
| `engin-zone` | OK → `engin-zone.json`, `-plan.json`, `-revert.json`, `-excluded.json` |
| `out/v1.2/engin-zone` | OK — the dot is in a directory component |
| `engin-zone.json` | **fatal** |
| `engin.umich.edu` | **fatal** — use `engin-umich-edu` |
| `.hidden` | **fatal** |
| `out/` (empty final component) | **fatal** |

*Intent:* the old `-o platform-domains-cloudflare.json` invocation is muscle memory. Under the
new option it would produce `platform-domains-cloudflare.json.json`. A literal reading of "file
extension" is the only rule that needs no judgment and fits in one `--help` sentence.

R2.3 The conventional organization-wide baseline invocation becomes:

```bash
./find-platform-domains-cloudflare -o platform-domains-cloudflare
```

`OUTPUT_FILE = "platform-domains-cloudflare.json"` becomes
`OUTPUT_BASENAME = "platform-domains-cloudflare"`, and the epilog's redirect-vs-`-o` guidance is
rewritten (it currently recommends an invocation that R2.2 makes fatal).

R2.4 **Startup writability probe.** Before the first Cloudflare API call, basename mode MUST
verify the parent directory exists and is writable, by creating and removing a probe temp file
in it. Failure is fatal (exit 2).

*Intent:* the sweep takes ~2 minutes and today's write failure surfaces only after it. This does
not make a late `ENOSPC` impossible — it makes the common case fail at second zero.

### R3 — Resolution

R3.1 Every non-ambiguous entry's **target** MUST be resolved for both A and AAAA, through the
single seam `resolve(hostname, rrtype)` (§7). CNAME chains are followed by the resolver.

R3.1a **One exception, exhaustive:** when the **A** lookup is indeterminate, the AAAA lookup is
skipped and both halves are `None`.

*Intent:* the entry is already excluded as `resolution-failed` (§6 row 8) whatever AAAA returns,
so the second lookup buys nothing and costs a resolver timeout on a target that is already not
answering. This is **not** listed in §11, which records changes to *shipped behavior*; no prior
version of this utility resolved anything.

R3.2 Resolution MUST happen in **both modes**, not only basename mode.

*Intent:* the inventory carries `resolved_a`/`resolved_aaaa` (R4.2). If resolution were
basename-mode only, those keys would be absent on stdout and the two outputs would diverge for
the same sweep — the exact failure `dump_json()`'s docstring exists to prevent ("the ONE
serialization of the output mapping, so the -o file and stdout are byte-identical").

R3.3 A `Timeout` or `NoNameservers` MUST be retried **once** before being treated as
indeterminate, copying `find-platform-domains-dns:139`'s `resolve_cname_retrying`.

R3.4 Results MAY be cached by target name within a run (two custom domains on one Pantheon site
share a target). This is a convenience, not a requirement.

### R4 — The inventory

R4.1 Ambiguous entries MUST be omitted from the inventory, in **both modes**, and the run MUST
exit 1 (§8).

*Intent:* an ambiguous entry's inventory row keeps the *first* `record_id` of two and presents it
as if it were actionable. `select_zones()`'s existing docstring already calls this "one more
reason the organization-wide baseline is what a rewrite must be driven from". Omitting is the
honest form. This is a **deliberate change to today's output** (§11).

R4.2 Each inventory entry gains three fields:

| Field | Source | Why |
|---|---|---|
| `name` | the raw `record.name` | The batch `POST` body's `name` MUST be exactly what Cloudflare holds. The inventory key is `normalize()`d, so without this a consumer must reconstruct it. Cloudflare stores names in Punycode — *"Domain names are always represented in Punycode, even if Unicode characters were used when creating the record."* |
| `zone_name` | `zone.name` | Human filtering. The API needs only `zone_id`. |
| `resolved_a`, `resolved_aaaa` | R3 | The evidence behind every plan entry, and what an operator needs to investigate an exclusion. |

R4.4 **`resolved_a`/`resolved_aaaa` distinguish "definitively none" from "we do not know."** A
definitive empty answer (NXDOMAIN, NoAnswer) is `[]`. An **indeterminate** one — the
`resolution-failed` path of R3.3 — is `null`.

*Intent:* PD#1. `[]` and `null` are the same shape to a careless reader and mean opposite things;
an indeterminate lookup rendered as `[]` tells an operator the target has no addresses, which is
a claim the run never established. This mirrors the utility's existing refusal to flatten a null
`proxied` to `false`.

R4.3 The complete field list of a Cloudflare CNAME record was checked against the spec-generated
SDK models in `.venv/lib/python3*/site-packages/cloudflare/types/dns/cname_record.py`. The
writable fields are **exactly** (exhaustive): `name`, `type`, `content`, `ttl`, `proxied`,
`settings`, `tags`, `comment`. `private_routing` is **A/AAAA only** and does not exist on a
CNAME. `priority` and `data` do not exist on A/AAAA/CNAME at all. Read-only fields (`id`,
`created_on`, `modified_on`, `proxiable`, `meta`, `comment_modified_on`, `tags_modified_on`)
MUST NEVER be sent in a body. The inventory already captures every writable field except
`name`, which R4.2 adds. **Nothing else is missing** — this closes `PROMPT.md` item 1(d).

### R5 — The plan and revert files

Canonical formats are §5. The rules:

R5.1 One entry per FQDN, keyed by the normalized FQDN, so a human or a script can filter the
file before applying (`PROMPT.md` 1(b)).

R5.2 Each entry MUST carry everything needed to make the call except credentials: `zone_id`,
`method`, `path`, the postable `body`, and the `delete_match` block.

R5.3 `delete_match` MUST live **outside** `body`.

*Intent:* `body` is then a real, valid batch body at all times. A shape like
`{"deletes": [{"match": …}]}` looks postable and is not; someone would post it.

R5.4 Applying **plan → revert → plan → revert** any number of times MUST leave Cloudflare
functionally unchanged, with deviations only in record `id`, `created_on`, `modified_on` and
equivalents.

*Intent and the constraint that forces §5.4's design:* batch `deletes` items are exactly
`{"id": …}`, `required: ["id"]` — there is **no** name/type/content delete form. The plan's
`posts` mint new ids that do not exist until the plan is applied, so a pre-generated revert
cannot name them. Worse, if the plan hardcoded the swept `record_id`, the *second* apply would
fail: the revert re-creates the CNAME with a **new** id. Resolving deletes at apply time is the
only shape that round-trips.

R5.5 Both files MUST carry a provenance header (§5.5) including `direction`, so an applier can
refuse to apply the wrong file.

### R6 — Field carry-over (`PROMPT.md` 1(d))

Each rule with its evidence. This table is **exhaustive** for the fields a body may contain.

| Field | Forward (CNAME → A/AAAA) | Revert (A/AAAA → CNAME) | Why |
|---|---|---|---|
| `name` | swept raw `name` | same | R4.2 |
| `type` | `A` / `AAAA` | `CNAME` | — |
| `content` | each resolved address | the single swept origin | Multi-origin entries are ambiguous and excluded, so `origins` has exactly one element here. This is an **invariant asserted in code**, not assumed. |
| `proxied` | swept value, **always emitted** | same | The API default is `false`. *"Cloudflare can only serve an SSL/TLS certificate for a DNS record when you set the record's proxy status to Proxied."* A silently DNS-only replacement takes the hostname out of certificate service. A null swept `proxied` never reaches here in practice — `classify()` excludes it as `unknown-proxy-status` (§6) — but this is an **invariant asserted in code**, not assumed: `record_body` raises `InvariantError` (§9.1) rather than silently emitting `"proxied": null`. |
| `ttl` | `1` when `proxied` is true, **or** when the swept `ttl` is null/zero; else the swept value verbatim | same | *"all proxied records have a time to live (TTL) of Auto … This value cannot be edited."* Whether the API rejects or coerces a non-1 TTL on a proxied record is **documented silence**; we do not build on it. A swept proxied TTL that is not 1 raises an ATTENTION (it should be impossible). The null/zero case is defensive: `ttl` is a required field (R4.3) and should always be present, but `collect_entries()` reads it via a defaulting `getattr`, and a missing value has no better answer than the same `1` ("automatic"). |
| `settings.flatten_cname` | **dropped** | restored from the swept CNAME verbatim | Not a member of the A/AAAA `settings` schema, and already inert on the source: *"This setting is unavailable for proxied records, since they are always flattened."* |
| `settings.ipv4_only`, `settings.ipv6_only` | carried | carried | Valid on **all three** types, not A/AAAA-specific as one might assume: *"this option only applies to proxied records"* — which is exactly our case. Dropping them would change which address families Cloudflare advertises at the edge. |
| `comment` | carried; omitted when null | same | *"This field has no effect on DNS responses"* but it is the only human record of why a record exists. |
| `tags` | carried; omitted when empty | same | If the source record has tags, the zone's plan already supports them, so carrying them within the same zone is safe by construction. |
| `private_routing` | never emitted | never emitted | A/AAAA-only, so there is no CNAME value to carry forward; and our revert is built from the original CNAME, so nothing needs carrying back. |

R6.1 **Null/empty omission:** `comment: null`, `tags: []`, and null-valued keys inside `settings`
are **omitted** from a body rather than sent as nulls. A swept `settings` that is `null`, or that
becomes empty after `flatten_cname` and null-valued keys are removed, means the `settings` key is
omitted from the body entirely. `proxied` is exempt — always emitted.

*Intent:* the API's own defaults then produce the same state, and the file stays readable. The
exemption exists because `proxied`'s default is the dangerous value.

### R7 — Exclusions

R7.1 An FQDN matching any condition in §6's table MUST be excluded: it gets **no** plan and
**no** revert entry, it gets an entry in the excluded file, an **unconditional** stderr
ATTENTION naming the FQDN, the reason code and the detail, and the run exits 1.

R7.2 Ambiguous FQDNs are additionally omitted from the **inventory** (R4.1). Every other reason
code leaves the entry in the inventory.

R7.3 The stderr ATTENTION for an exclusion is NEVER `-v`-gated.

*Intent:* PD#1. The whole design is organized against a file that drives a destructive rewrite
while the warnings about it go nowhere — `require_usable_streams()`'s docstring already says so.

---

## 4. Data flow

```
                          ┌──────────────────────────────┐
                          │  Cloudflare sweep (UNCHANGED)│
                          │  accounts → zones → records  │
                          └──────────────┬───────────────┘
                                         │ platform CNAMEs only (R1)
                                         ▼
                              ┌──────────────────────┐
                              │  collect_entries()   │
                              │  first-record-wins   │
                              └──────────┬───────────┘
                                         │
                     ambiguous? ─────────┤
                     (>1 origin, or      │
                      2 zones)           │
                          │              │ no
                          │              ▼
                          │   ┌────────────────────────────┐
                          │   │ resolve target A + AAAA    │   ← resolve() seam
                          │   │ one retry on Timeout (R3.3)│
                          │   └────────────┬───────────────┘
                          │                │
                          │        classify() ──► reason code, or None
                          │                │
                          │      ┌─────────┴──────────┐
                          │      │ None               │ reason code
                          │      ▼                    │
                          │  plan_entry()             │
                          │  revert_entry()           │
                          │      │                    │
                          ▼      ▼                    ▼
   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
   │ -excluded    │  │  INVENTORY   │  │  -plan.json  │  │ -revert.json │
   │  .json       │◄─┤ <base>.json  │  └──────────────┘  └──────────────┘
   │ (all reasons)│  │ or stdout    │
   └──────────────┘  └──────┬───────┘
          ▲                 │ ambiguous NEVER appears here (R4.1)
          └─────────────────┘
```

**Mode difference, and it is the only one:** stdout mode writes the inventory to stdout and
produces no other file. Resolution, classification and exclusion all still happen (R3.2), so
the inventory is byte-identical between the two modes and the exit code is the same.

---

## 5. File formats (canonical)

### 5.1 `<basename>.json` — the inventory

Keyed by the normalized FQDN. Sorted keys, 4-space indent, trailing newline — the existing
`dump_json()` is the **single** serializer for every one of the four files.

```jsonc
{
  "a.umich.edu": {
    "name": "a.umich.edu",
    "zone_id": "abc123",
    "zone_name": "umich.edu",
    "record_id": "9f1c0000000000000000000000000000",
    "origins": ["live-umich-x.pantheonsite.io"],
    "proxied": true,
    "ttl": 1,
    "comment": null,
    "tags": [],
    "settings": {"flatten_cname": false, "ipv4_only": false, "ipv6_only": false},
    "resolved_a": ["23.185.0.4"],
    "resolved_aaaa": ["2620:12a:8000::4", "2620:12a:8001::4"]
  }
}
```

`proxied`, `ttl`, `comment`, `tags`, `settings` remain **verbatim** — never coerced. A null
`proxied` stays null (§6, `unknown-proxy-status`).

### 5.2 Address ordering

`resolved_a`, `resolved_aaaa`, and the order of `posts` MUST be sorted by
`ipaddress.ip_address()` **value**, not lexically.

*Intent:* two things. Lexically, `23.185.0.10` sorts before `23.185.0.4`. And DNS rrsets rotate —
§1's two live queries returned the AAAA pair in opposite orders — so without a sort, two
identical sweeps produce diffing files and no golden is stable. `posts` order is A records first,
then AAAA, each set sorted.

### 5.3 `<basename>-plan.json`

```jsonc
{
  "generated": { /* §5.5 */ "direction": "plan" },
  "entries": {
    "a.umich.edu": {
      "zone_id": "abc123",
      "method": "POST",
      "path": "/zones/abc123/dns_records/batch",
      "delete_match": [
        {"type": "CNAME", "name": "a.umich.edu", "content": "live-umich-x.pantheonsite.io"}
      ],
      "body": {
        "posts": [
          {"type": "A",    "name": "a.umich.edu", "content": "23.185.0.4",
           "proxied": true, "ttl": 1,
           "settings": {"ipv4_only": false, "ipv6_only": false}},
          {"type": "AAAA", "name": "a.umich.edu", "content": "2620:12a:8000::4",
           "proxied": true, "ttl": 1,
           "settings": {"ipv4_only": false, "ipv6_only": false}},
          {"type": "AAAA", "name": "a.umich.edu", "content": "2620:12a:8001::4",
           "proxied": true, "ttl": 1,
           "settings": {"ipv4_only": false, "ipv6_only": false}}
        ]
      }
    }
  }
}
```

### 5.4 `<basename>-revert.json`, and the applier contract

```jsonc
{
  "generated": { /* §5.5 */ "direction": "revert" },
  "entries": {
    "a.umich.edu": {
      "zone_id": "abc123",
      "method": "POST",
      "path": "/zones/abc123/dns_records/batch",
      "delete_match": [
        {"type": "A",    "name": "a.umich.edu", "content": "23.185.0.4"},
        {"type": "AAAA", "name": "a.umich.edu", "content": "2620:12a:8000::4"},
        {"type": "AAAA", "name": "a.umich.edu", "content": "2620:12a:8001::4"}
      ],
      "body": {
        "posts": [
          {"type": "CNAME", "name": "a.umich.edu", "content": "live-umich-x.pantheonsite.io",
           "proxied": true, "ttl": 1,
           "settings": {"flatten_cname": false, "ipv4_only": false, "ipv6_only": false}}
        ]
      }
    }
  }
}
```

**Applier contract (normative for the not-yet-written applier; nothing here is implemented in
this increment).** For each entry:

1. Refuse the file unless `generated.direction` is the direction the operator asked for.
2. List the zone's DNS records.
3. For each `delete_match` item, find records matching **exactly** on `(type, name, content)`.
   - **exactly one** match → take its `id`
   - **zero** matches → the entry is already applied, or Cloudflare drifted. **Skip the entry and
     report it.** Do not partially apply.
   - **more than one** match → **refuse the entry and report it.**
4. Build `body["deletes"] = [{"id": …}, …]` from the ids found, keeping `body["posts"]` as-is.
5. `POST` the merged body to `path`.

**Superseded note (added by `apply-platform-domains-cloudflare`, 2026-08-03).** Step 3's
per-entry tolerance — a zero-match entry is skipped and reported, a multi-match entry is refused
and reported, and the rest of the file still applies — is **superseded** by
`development/2026-08-03-platform-domain-util4/SPEC.md` R4, on that increment's `PROMPT.md`'s
explicit instruction. R4 replaces "skip and report, keep going" with all-or-nothing: a zero-match
entry is skipped **only** when it is affirmatively `already-applied` (R == P, not merely D
absent); every other zero-match state, and every multi-match state, aborts the **whole run**
before anything is written. *Why:* per-entry tolerance means a file that is half-stale gets
half-applied, and the operator discovers which half only afterwards — a run that died at entry 12
of 217 could otherwise never be safely re-run at all. This paragraph is left in place as the
historical record of what was originally specified; the implemented behavior is util4 R4.

Cloudflare's documented execution order is Deletes → Patches → Puts → Posts inside one database
transaction, which is what keeps the name from ever being record-less: *"Although Cloudflare will
execute the batched operations in a single database transaction, Cloudflare's distributed KV
store must treat each record change as a single key-value pair. This means that the propagation
of changes is not atomic."* The residual exposure is a brief authoritative-DNS window bounded by
the 300 s proxied Auto TTL, never a TLS window — `research.md` establishes that the Universal
edge certificate is unaffected in both directions.

Per-FQDN batches contain 1–3 records, far below the Free-plan limit of 200 records per batch, so
**chunking never arises**.

**Known and accepted:** if an unrelated fourth A record is created at the same name after the
plan is applied, the revert deletes its three, the CNAME `POST` then collides with the leftover
(*"A/AAAA records cannot exist on the same name as CNAME records"*), and Cloudflare rolls the
whole batch back with an error. That is a loud, safe failure and is preferred over a revert that
deletes records it was never told about.

### 5.5 The provenance header

Present in the plan, revert and excluded files. **Not** in the inventory — the inventory must
stay byte-identical between stdout mode and basename mode, and stdout mode has no header.

```jsonc
"generated": {
  "at": "2026-07-31T14:02:11Z",
  "tool": "find-platform-domains-cloudflare",
  "direction": "plan",
  "argv": ["-o", "engin-zone", "engin.umich.edu"],
  "zones_swept": 1,
  "zones_total": 187,
  "entries": 12,
  "platform_suffix": ".pantheonsite.io",
  "required_a_range": "23.185.0.0/24",
  "required_aaaa_range": "2620:12a::/32"
}
```

`at` is UTC ISO-8601 with a `Z` suffix, from the `now_utc()` seam (§7). `zones_swept` and
`zones_total` are two integers, never a `"1 of 187"` string — a machine reads this. `entries` is
the number of entries **in this file**, so the plan's and the excluded file's counts differ and
together account for **every** FQDN the sweep found — the ambiguous ones included, since R7.1 gives
every reason code an excluded-file entry and R4.1 removes only the two ambiguous codes from the
*inventory*.

*Intent:* the plan pins addresses resolved at sweep time. If Pantheon migrates a site between
sweep and apply, those addresses become wrong, and the file's mtime — today's only freshness
signal — survives neither a copy nor `git add`. The ranges and suffix are recorded so an applier
can verify the assumptions the file was built under.

**Determinism note (PD#14):** `at` makes the three files non-deterministic across runs. Tests
MUST monkeypatch `now_utc()` rather than normalizing after the fact, so a golden compares real
bytes.

### 5.6 `<basename>-excluded.json`

```jsonc
{
  "generated": { /* §5.5 */ "direction": "excluded" },
  "entries": {
    "a.umich.edu": {
      "reason": "ambiguous-multiple-zones",
      "detail": "platform CNAME in zones abc123 and def456; kept record_id 9f1c…",
      "zone_ids": ["abc123", "def456"],
      "origins": ["live-umich-x.pantheonsite.io", "live-umich-y.pantheonsite.io"]
    },
    "b.umich.edu": {
      "reason": "platform-a-out-of-range",
      "detail": "live-umich-z.pantheonsite.io resolved to A 104.18.2.7, not in 23.185.0.0/24",
      "resolved_a": ["104.18.2.7"],
      "resolved_aaaa": []
    }
  }
}
```

`reason` is one of §6's codes. `detail` is human-readable. The remaining keys are
reason-dependent and illustrative; the only **exhaustive** contract is that `reason` and `detail`
are always present.

---

## 6. Gate table — every exclusion condition

The single canonical table. No negation chains anywhere else in this document.

| # | Reason code | Condition | Detected | In inventory? | Exit |
|---|---|---|---|---|---|
| 1 | `ambiguous-multiple-origins` | >1 platform CNAME for the FQDN in one zone | sweep | **no** | 1 |
| 2 | `ambiguous-multiple-zones` | platform CNAME for the FQDN in ≥2 zones | sweep | **no** | 1 |
| 3 | `unknown-proxy-status` | `proxied` is `null` (not `false`) | sweep | yes | 1 |
| 4 | `no-a` | target returned zero A records (NXDOMAIN / NoAnswer — definitive) | resolution | yes | 1 |
| 5 | `platform-a-out-of-range` | ≥1 A record, but **not every** A is in `23.185.0.0/24` | resolution | yes | 1 |
| 6 | `no-aaaa` | target returned zero AAAA records | resolution | yes | 1 |
| 7 | `platform-aaaa-out-of-range` | ≥1 AAAA record, but **not every** AAAA is in `2620:12a::/32` | resolution | yes | 1 |
| 8 | `resolution-failed` | Timeout / NoNameservers (after one retry), `MalformedNameError`, or any OTHER `dns.exception.DNSException` (e.g. `YXDOMAIN`, `NoResolverConfiguration`) | resolution | yes | 1 |

This list is **exhaustive**, and each FQDN carries exactly one reason code. **Evaluation order is
1, 2, 3, 8, 4, 5, 6, 7** — not the table's row order, which is grouped for reading.

*Intent:* `resolution-failed` (8) MUST be tested **before** `no-a` (4). R4.4 makes `resolved_a`
`null` on an indeterminate lookup, and a `not resolved_a` test treats `null` and `[]` alike — so
checking 4 first would report a timeout as "the target definitively has no A records", which is
precisely the definitive-vs-indeterminate confusion R4.4 exists to prevent.

**Post-merge fix (independent review, finding 1).** The first shipped `resolve_one_rrset` caught
only `Timeout`/`NoNameservers`/`MalformedNameError`; any OTHER `dns.exception.DNSException` (e.g.
`YXDOMAIN`, `NoResolverConfiguration`) escaped `resolve_target` → `process_one_entry` → `main()`'s
last line of defence, aborting the WHOLE sweep and discarding every other FQDN's work over one bad
record — reproduced live: a single `YXDOMAIN` on a 1-entry run printed `ERROR: unexpected
YXDOMAIN: ...` and returned 2 instead of excluding that one FQDN. The catch is now
`dns.exception.DNSException` generically (`MalformedNameError` stays named explicitly beside it —
it is a plain `Exception`, not a `DNSException`), with the `NoAnswer`/`NXDOMAIN` arm kept strictly
ABOVE it so a definitive absence can never fall into the broadened arm and read as indeterminate.

**Codes 1 and 2** are the only ones detectable without DNS. Conditions 3–8 require resolution,
which R3.2 makes unconditional, so **all eight apply in both modes**.

**A DNS-only entry (`proxied: false`) is NOT excluded.** The swap is type-only and preserves
`proxied: false`; 5 of 218 entries in the last live sweep were DNS-only.

**Codes 5 and 7 are a deliberate tightening of `PROMPT.md`.** The prompt asks that the target
"must have an A record for an IP address in the range 23.185.0.0/24" — i.e. ≥1. This spec
requires that **every** resolved address be in range. *Intent:* under a ≥1 rule a target
resolving to `[23.185.0.4, 104.18.2.7]` passes, and the plan then posts the foreign address as a
proxied origin. On real data the rules are indistinguishable — Pantheon returns exactly one A.
The AAAA half (code 7) was not in the prompt and was added by explicit decision in the design
conversation; `2620:12a::/32` covers both observed prefixes, `2620:12a:8000::` and
`2620:12a:8001::`.

---

## 7. Seams under test — named and agreed

Named **here, before implementation**, because implementation is test-first and an implementer
subagent runs with fresh context and cannot ask.

The test file loads the script fresh per test via `SourceFileLoader`
(`tests/unit/test_find_platform_domains_cloudflare.py:37`), which is what makes monkeypatching
module attributes safe and leak-free.

| Seam | Kind | Covers | Notes |
|---|---|---|---|
| `resolve(hostname, rrtype)` | module attribute | **every** DNS answer | Copied from `find-platform-domains-dns:62`. **NOTHING in the suite may touch real DNS.** |
| `now_utc()` | module attribute | `generated.at` | Makes all three headed files byte-deterministic under test (§5.5). |
| `FakeCloudflareClient` | existing fixture, `tests/unit/test_find_platform_domains_cloudflare.py:397` | the sweep | Unchanged. |
| `sys.stdout` / `sys.stderr` | existing guards | doomed-stream handling | Unchanged; §9. |

**Pure helpers to extract** (no I/O, unit-testable directly — the discipline that produced
`overage_blocks`, `plan_costs` and `sites_from_resume_point` in the main program):

| Helper | Returns |
|---|---|
| `check_basename(value)` | the validated basename; raises `StartupError` (R2.2, R2.4) |
| `output_paths(basename)` | a `NamedTuple` of the four paths |
| `sorted_addresses(values)` | addresses sorted by `ipaddress.ip_address()` value (§5.2) |
| `resolve_one_rrset(target, rrtype)` | `(addresses, problem)` for one rrset |
| `resolve_target(target)` | a `Resolution` NamedTuple `(a, aaaa, problem)` |
| `classify(entry, resolution)` | `(reason_code, detail)`; `(None, "")` when the entry qualifies |
| `clean_settings(settings, *, drop_cname_only)` | the `settings` value for a body, or `None` |
| `record_body(entry, rtype, content, settings)` | one `posts` item, applying every R6 rule |
| `proxied_ttl_anomaly(entry)` | `True` when a proxied record's swept TTL is not 1 |
| `plan_entry(entry, resolution)` | the §5.3 entry. **No `fqdn` parameter** — `entry["name"]` carries it |
| `revert_entry(entry, resolution)` | the §5.4 entry |
| `provenance(argv, sweep, direction, count)` | the §5.5 header |

`write_outputs(paths, …)` is **not** a pure helper — it does I/O and is specified in §9.3. It is
listed here only so the extraction list is complete.

---

## 8. Exit codes

| Code | Meaning | Change |
|---|---|---|
| 0 | Completed; nothing excluded | — |
| **1** | **Completed with exclusions** (≥1 FQDN carries a §6 reason code) | **NEW** |
| 2 | Could not complete | — |
| 130 | Interrupted | — |

Exit 1 is new. The prior spec states "There is deliberately no exit 1"; that reasoning
(a Cloudflare list call either returns or raises) no longer holds now that the run also does DNS
work and can partially succeed. The sibling `find-platform-domains-dns` already uses exit 1 for
"completed with indeterminates", so the taxonomy stays consistent across the pair.

**Reserving exit 1 requires porting the sibling's last line of defence** (added by the
whole-branch review, finding 2). CPython exits 1 on **any** uncaught traceback, so giving 1 a
"completed" meaning without routing every other outcome away from it leaves a crashed run and a
healthy-with-exclusions run indistinguishable to an operator's `case $?` — and the
consistency-with-the-sibling justification above false, since the sibling's `main()` carries the
guard precisely for this reason. `main()` MUST therefore end its handler chain with:

```python
    except SystemExit:
        raise
    except BaseException as e:  # noqa: BLE001 -- deliberate last line of defence, see the docstring: ...
        report_line(f"ERROR: unexpected {type(e).__name__}: {e}")
        return 2
```

The `except SystemExit: raise` arm keeps a deliberate exit's own code. The catch-all NEVER
swallows — the class is always named on stderr (PD#2) — and carries its `# noqa: BLE001` with an
inline reason, per `prompts/implementation-standards.md`. The only `return 1` in the program is
the exclusion branch on `main()`'s last line.

**The one documented exception, exhaustive and unchanged:** argparse writes its usage, error and
`--help` text before any stream guard exists and outside every handler, so `--help >/dev/full`
and `--bogus 2>/dev/full` still exit **120**.

---

## 9. Error handling

### 9.1 Named exceptions (exhaustive)

| Exception | Raised by | Caught by | Operator sees | Exit |
|---|---|---|---|---|
| `StartupError` | existing sites, plus `check_basename` (R2.2/R2.4) | `main()` | `ERROR: …` on stderr via `report_line` | 2 |
| `InvariantError` (subclass of `StartupError`) | `sole_origin`, `known_proxied` — a mid-sweep INTERNAL invariant violated: an entry reached a read that `classify()`/`collect_entries()` should already have excluded (an ambiguous `origins` list, or an unknown `proxied` status). Named separately from `StartupError` because this is a defect in the script's own reasoning, not an operator/environment error (PD#2), even though it is caught and reported identically. **Post-merge fix (independent review, finding 3):** `sole_origin` is now called from `process_one_entry` (the FIRST read of `origins`, before any resolution) and from `classify`'s four detail-string reads, not only from the batch-body builders (`plan_entry`/`revert_entry`/`record_body`) — defense-in-depth, so a regressed ambiguity gate is caught at the earliest read rather than three call frames later. | `main()` (the existing `StartupError` handler — no new catch site) | `ERROR: …` on stderr via `report_line` | 2 |
| `MalformedNameError` | `resolve()` — copied from `find-platform-domains-dns:51` | `resolve_target` | exclusion `resolution-failed` | 1 |
| `dns.resolver.NXDOMAIN`, `NoAnswer` | `resolve()` | `resolve_target` | exclusion `no-a` / `no-aaaa` | 1 |
| `dns.resolver.Timeout`, `NoNameservers` (after one retry), or any OTHER `dns.exception.DNSException` (e.g. `YXDOMAIN`, `NoResolverConfiguration`) | `resolve()` | `resolve_target` | exclusion `resolution-failed` | 1 |
| `cloudflare.CloudflareError` | the sweep | existing handlers | existing message, body never echoed | 2 |
| `KeyboardInterrupt` | anywhere | `main()` | `interrupt_message()` (§9.4) | 130 |
| `OSError` | file writes, operator-stream writes | `main()`'s existing arms | `ERROR: …` | 2 |
| `OutputWriteError` (subclass of `StartupError`) | `write_outputs` — one of the four files could not be written or could not be serialized | `main()` (the existing `StartupError` handler — no new catch site) | `ERROR: cannot write <path>: <class>: <message>.  Already replaced before this failure (fresh): …  NOT written by this run (unchanged or absent): …` | 2 |
| anything else | anywhere inside `main()`'s try | `main()`'s `except BaseException` last line of defence (§8) | `ERROR: unexpected <class>: <message>` | 2 |

**One** deliberate catch-all is introduced — `main()`'s last line of defence (§8), carrying
`# noqa: BLE001` with an inline reason. It is the mechanism that makes exit 1 mean what §8 says
it means. Ruff's `BLE001`/`E722` gate every other one mechanically (PD#2).

### 9.2 Shadow paths for the resolution flow (PD#3), all four traced

| Shadow | Condition | Outcome |
|---|---|---|
| happy | A and AAAA present and in range | plan + revert entry |
| **nil** | target is `None` or empty | **unreachable** — `collect_entries` already requires non-`None`, platform-suffixed content. Asserted in code, not assumed. |
| **empty** | zero A or zero AAAA | reason code `no-a` / `no-aaaa`; excluded; exit 1 |
| **upstream error** | dnspython raises after one retry | reason code `resolution-failed`; excluded; exit 1 |

### 9.3 Multi-file write

`write_outputs()` MUST build **all four documents in memory** before writing any of them, so a
construction error writes nothing. It then writes four temp files and `os.replace()`s each, reusing
the existing `write_json_atomic()`.

A failure on any of the four MUST raise `OutputWriteError` naming **which** file failed, which
were already replaced (fresh), and which this run never touched. The caught set is **exhaustive**:
`OSError`, `TypeError`, `ValueError`. *Intent (whole-branch review, finding 3):* the last two are
what `json.dump` raises on an unserializable value or a circular reference, and `plain()` passes
through anything without `model_dump`, so an SDK shape change putting a non-JSON type into
`settings` reaches it. Catching only `OSError` left the exact partial set this section exists to
make detectable arriving with the detection disabled.

**Accepted residual:** `os.replace` is atomic per file, not across four. A crash between replaces
leaves a mixed set. Mitigation: all four share one `generated.at`, so the mismatch is detectable,
and this paragraph is the disclosure rather than a silence. *Not* mitigated further because the
alternative (a single container file) contradicts `PROMPT.md`'s four-file requirement.

### 9.4 Interruption

`interrupt_message()` is rewritten to describe four files. Its existing distinction between "the
write returned" and "it may or may not have" is preserved: `wrote` is a reliable YES and an
unreliable NO, so the not-wrote branch states only what is always true.

### 9.5 The subset-sweep warning gets sharper

`select_zones()`'s docstring already records that a subset sweep cannot see a cross-zone
duplicate. Under this increment that stops being merely informational: **a subset sweep can emit
a plan entry for an FQDN that a full sweep would have excluded as ambiguous** — pointing a
destructive rewrite at one of two records with no warning. The existing subset ATTENTION MUST be
extended to name all four files and to state this consequence explicitly.

---

## 10. Observability (PD#5)

| Message | Verbosity | Content |
|---|---|---|
| per-zone progress | `-v` | unchanged |
| per-target resolution | `-v` | `live-umich-x.pantheonsite.io -> A 23.185.0.4 \| AAAA 2620:12a:8000::4, 2620:12a:8001::4` |
| every exclusion | **always** (R7.3) | `ATTENTION: <fqdn> excluded (<reason>): <detail>` |
| summary | always | existing lines, plus a count of exclusions **by reason code** |
| destination | always | names all four paths in basename mode |
| subset warning | always | §9.5 |

---

## 11. Deliberate behavior changes

Every one of these is a change to shipped behavior, decided in the design conversation, and each
must appear in the commit message and in `CLAUDE.md`.

1. **Ambiguous entries are omitted from the inventory** (R4.1), in both modes. `PROMPT.md` says
   stdout mode "should function as it does today"; this overrides that, on the reasoning in R4.1.
2. **Every run does DNS work** (R3.2), including stdout mode.
3. **The inventory gains `name`, `zone_name`, `resolved_a`, `resolved_aaaa`** (R4.2).
4. **Exit 1 exists** (§8).
5. **`-o` takes a basename, not a path**, and the old argument form is fatal (R2).

---

## 12. NOT in scope

Each with the reasoning preserved, so a later session does not re-litigate it.

| Item | Why not |
|---|---|
| The **applier** script | `PROMPT.md` 1(a): "We will write another script, later". §5.4 is its contract. |
| Calling `terminus domain:dns` / the Pantheon API for required records | Rejected in the design conversation in favour of resolving the target. Pantheon's answer differs for migrated vs. unmigrated sites and would need a full API client copied in; resolution is authoritative for the addresses actually in service. |
| Changing a record's `type` in place via batch `puts` | **Documented silence** — Cloudflare neither permits nor forbids it. And one `put` cannot become three records, so it does not help. |
| Chunking batches | Per-FQDN batches are 1–3 records; the Free-plan limit is 200. |
| Performance work | `PROMPT.md`: "Do not put any significant amount of work into making this script fast or efficient." |
| IDN/Punycode normalization | Cloudflare stores and returns Punycode; we compare Cloudflare names to Cloudflare names and resolve the Punycode target. No conversion is needed. |
| De-U-M-ifying anything | This utility is institution-neutral already; it reads a config file. |
| A `--verify` mode that re-resolves and diffs an existing plan | Genuinely useful, genuinely separate. Not requested. Belongs to the applier if anywhere. |

---

## 13. Deletion checklist delta

`development/2026-07-30-platform-domain-util2/SPEC.md` §11 remains the checklist. Two items
change:

- Item 6, `.gitignore`: the entry `/platform-domains-cloudflare.json` MUST become
  `/platform-domains-cloudflare*.json` in this increment, so the three new baseline files are
  ignored too. Removing it at deletion time is unchanged.
- Item 7, `CLAUDE.md`: the subsection is larger after this increment; still one subsection.

Nothing else changes. No new source files, no new `pyproject.toml` entries, no new
`ruff-check.sh` arm. **Deletion stays `git rm` of three files.**

---

## 14. Test plan

All offline, `unit` tier, added to `tests/unit/test_find_platform_domains_cloudflare.py`.
Baseline before this increment: **96 passed**, lint and types clean.

| # | Group | Cases |
|---|---|---|
| 1 | `check_basename` | accepts `engin-zone`, `out/v1.2/engin-zone`; rejects `engin-zone.json`, `engin.umich.edu`, `.hidden`, `out/`; rejects an unwritable parent directory (R2.4) |
| 2 | `sorted_addresses` | `23.185.0.10` sorts **after** `23.185.0.4`; both live rrset orders from §1 produce identical output |
| 3 | `classify` | one case per §6 reason code, plus the pass case; the every-address-in-range rule for codes 5 and 7; a DNS-only entry is **not** excluded |
| 4 | `resolve_target` | NXDOMAIN/NoAnswer → definitive empty; Timeout retried **once** then indeterminate; `MalformedNameError` → indeterminate; the retry is asserted to happen exactly once |
| 5 | `record_body` | `flatten_cname` dropped forward; `ipv4_only`/`ipv6_only` carried both ways; settings restored verbatim on revert; null/empty omission; `proxied` always present; `ttl: 1` forced when proxied, verbatim when not; ATTENTION when a swept proxied TTL is not 1 |
| 6 | `plan_entry` / `revert_entry` | full round-trip — the revert `posts` reproduces every writable field of the swept CNAME; `delete_match` is outside `body`; `body` alone is a valid batch body |
| 7 | provenance | `now_utc()` seam honored; `direction` correct per file; `zones_swept`/`zones_total` are ints |
| 8 | four-file write | all four written; one shared `generated.at`; a construction failure writes **nothing**; the inventory is byte-identical to stdout mode's output |
| 9 | `main()` | exit 0 / 1 / 2 / 130; stdout mode omits ambiguous entries and exits 1; `-plan`/`-revert`/`-excluded` exist only in basename mode; the subset ATTENTION names four files |
| 10 | rewritten existing tests | the ones asserting the old inventory shape and ambiguous-entry **inclusion** |

**NEVER-block — tests are load-bearing (PD#14).** Group 10's tests will go red. That is a
**signal of the intended behavior change**, and each MUST be rewritten to assert the new
behavior with its reason stated. NEVER weaken an assertion to make it pass, NEVER delete a test
to make a suite green, and NEVER regenerate a golden without a reviewed diff. Every new test MUST
be observed failing for the **right reason** before its implementation is written.

`tests/unit/test_find_platform_domains_dns.py` MUST stay untouched and green. If it moves,
something was modularized that this spec's Global Constraint 1 forbids.

---

## 15. Acceptance criteria

Exact commands. To be **run and their real output pasted into this section** before the work is
submitted; an unrun acceptance suite is PD#14 exactly.

```bash
# 1. Full suite, offline tier.  Expected: >= 96 passed, 0 failed; ruff and pyright clean.
#    (Group 10 REWRITES existing tests, so the count is not simply 96 + N.)
./run-tests --fast

# 2. The utility's own file.
./run-tests --fast tests/unit/test_find_platform_domains_cloudflare.py

# 3. The sibling MUST be untouched.
git diff --stat find-platform-domains-dns tests/unit/test_find_platform_domains_dns.py
#    Expected: empty output.

# 4. The extension rule.
./find-platform-domains-cloudflare -o platform-domains-cloudflare.json ; echo "exit=$?"
#    Expected: ERROR naming the value, a corrected example, exit=2, no API call made.

# 5. --help still describes the new option and the four files.
./find-platform-domains-cloudflare --help

# 6. Live, one zone (requires credentials).  Expected: four files, exit 0 or 1.
./find-platform-domains-cloudflare -v -o /tmp/one-zone engin.umich.edu
ls -l /tmp/one-zone*.json ; echo "exit=$?"

# 7. Live, organization-wide baseline (~2 minutes).
./find-platform-domains-cloudflare -o platform-domains-cloudflare
jq -r '.generated | "\(.direction) \(.entries) entries, \(.zones_swept)/\(.zones_total) zones"' \
   platform-domains-cloudflare-plan.json

# 8. The round-trip property, by inspection: for one FQDN, every writable field of the inventory
#    entry appears in the revert body.
jq '.entries["<one fqdn>"].body.posts[0]' platform-domains-cloudflare-revert.json
jq '.["<one fqdn>"]' platform-domains-cloudflare.json
```

### Results — items 6–8, run live 2026-08-01 after `RUN LIVE` was given

**Item 6 — one zone.** Exit **1**, four files written. Abridged (the `-v` per-target lines are one
per record):

```
[1/1] zone engin.umich.edu -- 635 records
live-engin-depts.pantheonsite.io -> A 23.185.0.4 | AAAA 2620:12a:8000::4, 2620:12a:8001::4
live-engin-rws.pantheonsite.io -> A 185.178.196.2 | AAAA 2a0a:6c80::2
ATTENTION: rws.engin.umich.edu excluded (platform-a-out-of-range):
  live-engin-rws.pantheonsite.io resolved to A 185.178.196.2, which is not in 23.185.0.0/24
Wrote 55 platform-domain CNAMEs (0 DNS-only, invisible to fqdns.json) from 635 records
  in 1 of 187 zones in 5 account(s) to:
  /tmp/one-zone.json (55 entries)
  /tmp/one-zone-plan.json (54 entries)
  /tmp/one-zone-revert.json (54 entries)
  /tmp/one-zone-excluded.json (1 entries)
Completeness cross-check: 7 of 7 paginated lists verified complete, 0 short, 0 unverifiable.
Excluded from the rewrite plan: 1 platform-a-out-of-range
ATTENTION: /tmp/one-zone.json, /tmp/one-zone-plan.json, /tmp/one-zone-revert.json and
  /tmp/one-zone-excluded.json cover 1 of 187 zones -- this is NOT an organization-wide sweep
  and MUST NOT be used as the baseline for a rewrite. ...
exit=1
```

**Item 7 — organization-wide baseline.** Exit **1**, `real 2m21.217s`:

```
ATTENTION: rws.engin.umich.edu excluded (platform-a-out-of-range): ...
Wrote 218 platform-domain CNAMEs (5 DNS-only, invisible to fqdns.json) from 22298 records
  in 187 zones in 5 account(s) to:
  platform-domains-cloudflare.json (218 entries)
  platform-domains-cloudflare-plan.json (217 entries)
  platform-domains-cloudflare-revert.json (217 entries)
  platform-domains-cloudflare-excluded.json (1 entries)
Completeness cross-check: 193 of 193 paginated lists verified complete, 0 short, 0 unverifiable.
Excluded from the rewrite plan: 1 platform-a-out-of-range
```

Consistent with the 2026-07-30 baseline (218 CNAMEs, 5 DNS-only, 2m 17s).

**Item 8 — the round-trip property.** Run over **all 217 plan entries**, not the single FQDN the
command above sketches:

```
shared generated.at: {'2026-08-01T00:22:23Z'} | directions: ['plan', 'revert', 'excluded']
zones: 187 of 187 | counts: 217 217 1
plan/revert cover identical FQDN sets: 217
round-trip: revert restores every writable field for 217 of 217 entries; failures: []
plan body invariants:  OK          # proxied always explicit, ttl 1 when proxied,
                                   # no flatten_cname leaked, every A in 23.185.0.0/24,
                                   # every AAAA in 2620:12a::/32, no deletes inside body
AAAA-count distribution: Counter({2: 217})
DNS-only entries in the plan: 5
```

**Three findings from the live run, none of them defects:**

1. **The 23.185.0.0/24 safety check fired on real data, first run.** `rws.engin.umich.edu` →
   `live-engin-rws.pantheonsite.io` → `A 185.178.196.2` / `AAAA 2a0a:6c80::2`. That is not
   Pantheon's range at all, so the FQDN is excluded from the plan and named on stderr. Under
   `PROMPT.md`'s literal "≥1 in range" rule this would still have been excluded (there is no
   in-range A at all) — but it is exactly the shape §6's tightening exists for.
2. **A fifth address set is live, where four were expected.** `PROMPT.md` says "at least 5
   different sets … although in practice we only see 4". The sweep found **five**:
   `23.185.0.1` (27), `.2` (26), `.3` (79), `.4` (84) and **`.253` (1)** —
   `firearminjury.umich.edu` → `dev-umor-ifip.pantheonsite.io` → `23.185.0.253` /
   `2620:12a:8000::253` / `2620:12a:8001::253`, a **dev** environment target. This is the
   decisive vindication of R3/§1: a hardcoded constant would have written the wrong addresses
   for this hostname.
3. **Every planned FQDN returned exactly two AAAA records**, and all five DNS-only records
   reached the plan with `proxied: false` preserved.

### Results — items 1–5, run 2026-07-31 after the whole-branch review fix wave

```
$ ./run-tests --fast                                                       # item 1
107 snapshots passed.
========= 1465 passed, 3 skipped, 2 deselected, 15 warnings in 30.86s ==========
Linting (ruff, campaign ratchet) ...
Type-checking (pyright, campaign ratchet) ...
exit=0

$ ./run-tests --fast tests/unit/test_find_platform_domains_cloudflare.py   # item 2
============================= 195 passed in 2.40s ==============================
Linting (ruff, campaign ratchet) ...
Type-checking (pyright, campaign ratchet) ...

$ git diff --stat find-platform-domains-dns \                              # item 3
      tests/unit/test_find_platform_domains_dns.py
                                        <no output -- the sibling is byte-identical>

$ ./find-platform-domains-cloudflare -o platform-domains-cloudflare.json   # item 4
ERROR: --output-basename 'platform-domains-cloudflare.json' contains a file extension; give the
basename WITHOUT one (for example 'engin-zone', not 'engin-zone.json').  The four output files get
.json, -plan.json, -revert.json and -excluded.json appended.
exit=2
                       (no Cloudflare API call is made -- check_basename runs before the client)

$ ./find-platform-domains-cloudflare --help                                # item 5
usage: find-platform-domains-cloudflare [-h] [-c CONFIG] [-o BASENAME] [-v]
                                        [ZONE ...]

Write every Cloudflare CNAME record pointing at a Pantheon platform domain as
JSON, with the Cloudflare batch calls that would rewrite it to the addresses
its target resolves to, and the calls that would undo that. With -o/--output-
basename: four files. Without it: the inventory alone, on standard output.

positional arguments:
  ZONE                  sweep only these Cloudflare zones, by name (e.g.
                        engin.umich.edu); case and a trailing dot are ignored,
                        and a name that matches no zone is an error. Give ZONE
                        names AFTER the options -- argparse cannot interleave
                        them

options:
  -h, --help            show this help message and exit
  -c, --config CONFIG   TOML file to read [Cloudflare] credentials from
                        (default: pantheon-sitehealth-emails.toml)
  -o, --output-basename BASENAME
                        write four JSON files -- BASENAME.json, BASENAME-
                        plan.json, BASENAME-revert.json and BASENAME-
                        excluded.json -- instead of writing the inventory to
                        standard output. BASENAME must have NO file extension
  -v, --verbose         print each zone to stderr as it is scanned

With no ZONE, every zone in every visible account is swept. To refresh the
organization-wide baseline before a rewrite, use -o rather than a redirect:
`-o platform-domains-cloudflare` replaces each file atomically and only on
success, where `> platform-domains-cloudflare.json` truncates it before the
sweep even starts and so destroys the previous baseline on any failed run.
```

---

## 16. Security (PD#6)

- **No new credential path.** The `[Cloudflare]` credential resolution and the `build_client()`
  environment pin are untouched. The pin closes four routes by which ambient environment values
  reach the wire, including `$CLOUDFLARE_BASE_URL` redirecting a configured credential to an
  arbitrary host; it is measured against cloudflare 5.4.0 and asserted against a **real built
  request**. This increment must not disturb it, and the existing test proves it did not.
- **No credential reaches a file.** The four output files contain Cloudflare record data and DNS
  results only. The provenance header records `argv`, which carries a config **path** and zone
  names — never a secret, because credentials are only ever read from the config file.
- **DNS is a new outbound channel.** It queries only hostnames that came from Cloudflare record
  contents and already matched `.pantheonsite.io`, so no attacker-chosen name is resolved.
- **API error text never includes a response body** — unchanged (`api_error_text()`).

---

## 17. Documentation to update, in the same change

| File | Change |
|---|---|
| `CLAUDE.md` | The `### find-platform-domains-cloudflare (temporary utility)` subsection: the new option, the four files, the eight reason codes, exit 1, and the §11 behavior changes |
| the script's module docstring | Same, in brief |
| `.gitignore` | §13 |
| `development/2026-07-30-platform-domain-util2/SPEC.md` | A pointer at §11 to this spec, so the deletion checklist stays findable |
| this folder | `PROMPT.md`, `SPEC.md`, and — at session end via `/archive-session` — the scrubbed transcript and statistics |

---

## 18. Approval gates (structural STOPs)

**STOP 1 — spec approved.** Implementation MUST NOT begin until the human replies with the exact
phrase `SPEC APPROVED`. The spec MUST be committed before the first implementation commit, so
there is a baseline to diff against.

**STOP 2 — live verification.** Acceptance items 6–8 touch real Cloudflare credentials. They MUST
NOT be run until the human replies with the exact phrase `RUN LIVE`. Items 1–5 are offline and
need no gate.

**STOP 3 — adversarial review.** A `psh-reviewer` subagent with **fresh context**, seeing only
this spec and the diff, reviews before merge, per `prompts/adversarial-review.md`.

---

## 19. Closing audit questions (answered after implementation)

Evidence: the seven per-task reports/reviews (`.superpowers/sdd/PLAN/task-{1..7}-report.md` /
`task-{1,3,4,5,6,7}-review.md`), the whole-branch review (`final-review.md`), the two fix waves
(`final-fix-report.md`, `regression-fix-report.md`), the ledger (`progress.md`), and the code and
history at `HEAD` (`c3deb27..103ca41`, 27 commits, no branch created per `CLAUDE.md`).

1. **Did any test in group 10 get weakened rather than rewritten? Show each diff.**

   No. Group 10 was 12 tests, all rewritten in Task 3, plus 3 more retired-warning tests rewritten
   in Task 6 under a separate controller decision (decision A) — 15 total, none weakened.

   The Task 3 review (`task-3-review.md`) walked all 12 individually in a table ("The 12 rewritten
   tests, one at a time") and its verdict: *"none is a weakening. Every rewrite replaces an
   inclusion assertion with an exclusion assertion of equal-or-greater specificity (exact `==` on a
   reason code, not an `in` that would pass either way), no test was deleted, no matcher loosened,
   no `assert True`."* Two representative diffs, quoted verbatim from `task-3-report.md` §3:

   - `test_collect_entries_is_first_record_wins_across_zones_and_warns` — before: asserted the
     cross-zone duplicate **stayed** in `entries` (`zone_id == "zone-a"`, `record_id == "rec-1"`,
     `origins` accumulating both contents). After: `entries == {}`;
     `excluded["www.example.edu"]["reason"] == "ambiguous-multiple-zones"`; `origins` == both;
     `zone_ids == ["zone-a", "zone-b"]`; **`len(warnings) == 1` and all three substring checks kept
     verbatim.** The operator-visible warning assertion — the one thing R4.1 requires to survive —
     was not touched.
   - `test_collect_entries_warns_for_two_matches_in_one_zone` — before: entry **kept**, asserted
     `"rec-1" in warnings[0]`. After: `entries == {}`; `reason == "ambiguous-multiple-origins"`;
     `len(warnings) == 1`; three substring checks including `"omitted from the inventory"`,
     replacing the now-meaningless `"rec-1"` check (there is no longer a kept record to name).

   Task 6's 3 additional rewrites (`test_collect_entries_is_first_record_wins_across_zones_and_warns`,
   `test_collect_entries_warns_for_two_matches_in_one_zone`, and
   `test_collect_entries_excludes_a_name_with_two_platform_cnames_in_one_zone`) exist because
   decision A retired `collect_entries`' own ATTENTION text (the uniform R7.1 line in `main()` had
   made it a duplicate of the same fact). Each went from `assert len(warnings) == 1` + substrings to
   `assert warnings == []` — again not "assert True": it pins a real, specific new fact
   (`collect_entries` no longer warns), and the retired assertion's *intent* — the operator must
   still be told — is re-covered by a new, independent test at the `main()` seam,
   `test_an_ambiguous_exclusion_produces_exactly_one_operator_line`, which drives the real
   `fetch_platform_cnames()` → `main()` path (not a canned `SweepResult`) and was watched failing
   pre-fix (`task-6-report.md`: *"ATTENTION: ... a.example.edu ... assert err.count("a.example.edu")
   == 1 ... AssertionError: assert 2 == 1"*). Both the Task 3 reviewer and the whole-branch reviewer
   independently confirmed (via `git diff | grep '^-def test'`) that zero tests were deleted across
   the branch — only rewritten or added.

2. **Was every new test observed failing for the right reason before its implementation existed?**

   With two disclosed, honest exceptions — neither papered over by the implementer or the reviewer:

   - **Task 4 — `test_main_exits_0_when_nothing_was_excluded`.** This brief-supplied test asserts
     `fpc.main([]) == 0` on a healthy, in-range entry. The implementer verified directly (restoring
     the pre-Task-4 script byte-for-byte and running the test alone) that it **already passed
     against the pre-implementation code**: pre-Task-4 `main()` had no exit-1 concept and
     unconditionally `return 0`s on the success path, so the assertion held with or without
     `classify()`/resolution existing. `task-4-report.md`: *"This means
     `test_main_exits_0_when_nothing_was_excluded` did not fail for the right reason at Step 2 — it
     did not fail at all."* The reviewer independently confirmed this is not a defect — it is a
     **live instrument**, not a dead one — by mutating `return 1 if excluded else 0` to `return 1`
     and observing it (and 14 others) go red (`task-4-review.md`, "It goes red on a mutation of the
     behavior it claims to guard, so it is **not** a dead instrument and this is **not** a
     finding"). It is a legitimate regression test going forward; it simply was never independently
     falsified by Task 4's own code, because the pre-existing behavior happened to coincide with the
     new contract's success case.
   - **Task 6 fix round 2 — `test_a_ctrl_c_mid_write_outputs_leaves_only_fully_written_files_behind`.**
     Added to close a reviewer-named coverage **gap** (no test existed for a Ctrl-C mid-`write_outputs`),
     not a behavior defect. Run against the stashed-back pre-fix script alongside three genuinely
     red siblings, it was the one that **passed both before and after**: `task-6-report.md`
     (fix-round-2 section): *"The 4th test ... passed even against the pre-fix code ... This is
     expected and is called out here rather than hidden ... `write_json_atomic`'s existing per-file
     atomicity and `main()`'s existing `except KeyboardInterrupt` handling were already correct
     before this round ... This test is coverage for a previously-untested-but-already-correct path
     ... it is not a red→green pair and I am not claiming otherwise."*

   Two smaller, related notes surfaced by the same discipline but not full exceptions: Task 4's
   two subprocess-driver tests were found — by the implementer, then independently reproduced by
   the reviewer — to have been passing green while silently reaching **real DNS** (a live instrument
   that could not report the SPEC §7 violation it was already committing); fixed with an autouse
   `resolve`-raising guard, and that guard itself was later found (regression-fix-report.md,
   Defect 1) to be satisfiable by accident once `main()` grew a catch-all — fixed by moving its
   assertion to fixture teardown. Every other new test across all seven tasks and both whole-branch
   fix waves was watched failing for its stated reason before the implementation existed (each
   task's report pastes the red run; the reviewers independently re-ran the reviewer-supplied
   mutations and pasted the red output themselves rather than trusting the report).

3. **Is the inventory byte-identical between stdout mode and basename mode on the same fixture?
   Which test proves it, and has that test been shown capable of going red?**

   Yes. The test is `test_the_inventory_is_byte_identical_between_the_two_modes`
   (`tests/unit/test_find_platform_domains_cloudflare.py:2116`): it runs the same planned sweep
   twice, once through `main([])` (stdout, captured) and once through `main(["-o", "engin-zone"])`,
   and asserts `(tmp_path / "engin-zone.json").read_text() == from_stdout` — a real byte
   comparison, not a shape comparison.

   It has been shown capable of going red, in two independent ways: (a) Task 6's report
   (`task-6-report.md`, "Watching every new/changed test fail for the right reason") shows it in the
   pasted list of 17 tests that failed when the script was reverted to its pre-Task-6 state via
   `git stash push -- find-platform-domains-cloudflare` — i.e. it was observed red before the
   feature it guards (both modes doing resolution/classification identically) existed; (b) the
   whole-branch reviewer explicitly declined to take the test's green status on faith
   (`final-review.md`, "Attacks that found nothing"): *"Byte-identical inventory (R3.2). I did not
   trust the test."* — and independently re-derived the same property by reading every function in
   the `entry`-mutation path for aliasing, then driving a **richer**, hand-built three-entry sweep
   (mixed-case name, non-null `settings` with a null-valued key, `tags`, `comment`, a DNS-only entry,
   one excluded entry) through both modes and diffing the bytes directly: `"BYTE IDENTICAL: True,
   both modes exit 1."` No reviewer performed a targeted mutation of production code specifically
   designed to make *this test* diverge (e.g. gating resolution on `paths is not None`); the
   stash-revert red run and the independent hand-driven re-derivation are the two pieces of evidence
   that exist, and together they satisfy PD#14's bar without a third, narrower mutation having been
   run.

4. **Does `git grep -n "pantheon.io\|gotpantheon" find-platform-domains-cloudflare` return only
   `.pantheonsite.io` matches (R1)?**

   Run 2026-07-31 at `HEAD` (`103ca41`):

   ```
   $ git grep -n "pantheon.io\|gotpantheon" -- find-platform-domains-cloudflare
   find-platform-domains-cloudflare:375:    fe4.edge.pantheon.io, while live-umich-its-wws-test1.pantheonsite.io answers A/AAAA directly
   ```

   One match, and it is not `.pantheonsite.io`. It is prose inside `resolve_target()`'s docstring,
   explaining *why* the resolver follows CNAME chains uniformly — quoting SPEC §1's live example
   verbatim (`fe4.edge.pantheon.io` is the real target one platform CNAME's chain terminates at,
   per the two live DNS queries §1 records). It is not code that reads, plans, reverts, or excludes
   a `*.pantheon.io` record: R1 governs which Cloudflare CNAME records the utility **acts on**
   (`PLATFORM_SUFFIX = ".pantheonsite.io"`, checked by `is_platform_domain()` before any record ever
   reaches `collect_entries`), and this line is commentary about DNS *resolution* behavior for a
   target that already passed that filter. **Not an R1 violation.**

5. **Did the script's line count grow enough that the "copy, don't modularize" rule is now costing
   more than it saves? Record the number; do not act on it.**

   ```
   $ git show c3deb27:find-platform-domains-cloudflare | wc -l
   856
   $ wc -l find-platform-domains-cloudflare
   1593 find-platform-domains-cloudflare
   ```

   856 → 1593 lines (+737, +86%). The test file grew from 96 tests to 197 (2556 lines). Recorded;
   not acted on, per the question's own instruction. (For scale: the sibling `find-platform-domains-dns`,
   the precedent SPEC §8 leans on for the exit-1 taxonomy, is a comparable size and has not needed
   modularizing either.)

6. **Was `build_client()`'s environment pin disturbed? Which test proves it was not?**

   No. `git diff c3deb27..HEAD -- find-platform-domains-cloudflare | grep -n "def build_client"`
   returns nothing — the function has zero lines touched across all 27 commits; the only new
   reference to it anywhere in the diff is one comment (`API_BASE_URL = "..." # pinned; see
   build_client`, unrelated code added by Task 1 for the writability-probe/basename work). The test
   file has one single-line diff near the `build_client` test block (a non-UTF8-file startup-error
   test), unrelated to the pin itself.

   The test that asserts the pin against a **real built request** is
   `test_cloudflare_client_ignores_an_ambient_base_url`
   (`tests/unit/test_find_platform_domains_cloudflare.py:227`), part of the pre-existing block also
   covering `test_cloudflare_client_prefers_the_api_token`,
   `test_cloudflare_client_sends_only_the_configured_credential`, and
   `test_cloudflare_client_falls_back_to_email_and_key` — none of which changed in this branch. All
   of them pass unmodified in the final `./run-tests --fast` run (1467 passed).

7. **Are all eight reason codes reachable in the test suite, and is each asserted on a distinct
   condition rather than on the same fixture with a changed expectation?**

   Yes to both. Each of the 8 `classify()` tests constructs its own distinct `Resolution`/`swept()`
   input (not a shared fixture with only the expected value edited):

   | Code | Test | Distinguishing input |
   |---|---|---|
   | `ambiguous-multiple-origins` | `test_collect_entries_excludes_a_name_with_two_platform_cnames_in_one_zone` | two records, same zone |
   | `ambiguous-multiple-zones` | `test_collect_entries_excludes_a_name_present_in_two_zones` | two records, different zones |
   | `unknown-proxy-status` | `test_classify_excludes_an_unknown_proxy_status` | `swept(proxied=None)` |
   | `resolution-failed` | `test_classify_excludes_an_indeterminate_resolution_before_testing_for_no_a` | `Resolution(None, None, "Timeout...")` |
   | `no-a` | `test_classify_excludes_a_target_with_no_a_records` | `Resolution([], [...], "")` |
   | `platform-a-out-of-range` | `test_classify_excludes_an_a_record_outside_the_pantheon_range` (+ the mixed-rrset variant) | `Resolution(["104.18.2.7"], ...)` |
   | `no-aaaa` | `test_classify_excludes_a_target_with_no_aaaa_records` | `Resolution([...], [], "")` |
   | `platform-aaaa-out-of-range` | `test_classify_excludes_an_aaaa_record_outside_the_pantheon_range` | `Resolution([...], ["2606:4700::1111"], "")` |

   Each also has a `main()`-level counterpart proving the code reaches `-excluded.json`/the
   summary/exit 1 end to end (e.g. `test_the_summary_names_all_four_files_with_per_file_entry_counts`,
   `test_the_summary_counts_exclusions_by_reason` for a two-reason-code sweep). The evaluation-order
   requirement (`resolution-failed` before `no-a`) has its own dedicated test rather than being
   inferred from the pass/fail table, and the reviewer independently confirmed it
   (`final-review.md`: *"Evaluation order matches SPEC §6 and
   `test_classify_excludes_an_indeterminate_resolution_before_testing_for_no_a` genuinely guards
   it"*).

---

### Parked findings

Every finding raised across the seven task reviews and the whole-branch review that was
**deliberately not fixed**, with the ruling that parked it. The whole-branch review's "Ruling on
every deferred Minor in the ledger" (`final-review.md`) is the authority; items it marked **MUST
FIX** were fixed in the final fix wave and are omitted here (they are closed, not parked). This
list is the complement: everything ruled **Leave**.

| Finding | Ruling |
|---|---|
| `plan_entry` shares one `settings` dict object across every post it builds (aliasing) — `record_body` already copies `tags` for the same reason but not `settings` | **Leave.** Harmless today (nothing mutates a post after construction; JSON output is unaffected); a one-word fix (`dict(settings)`) if anyone is in that code again. |
| SPEC §5.2's `posts` address ordering is correct only because it inherits sorted order from `resolve_one_rrset`; `plan_entry`'s own docstring does not name the owner | **Leave.** Not a live bug — the inheritance is real and tested — but the ownership should be named in the docstring if the code is touched again. |
| `SweepResult.warnings` is permanently `[]` after Task 6's decision A retired its only producer; `main()`'s `for message in sweep.warnings` loop is now dead | **Leave.** PD#9 ("Everything deferred is written down") is satisfied — a named `README.md` TODO item exists — so this is a decision, not an oversight. ~6-line deletion in a script whose whole purpose is to be deleted. |
| Three test fixtures hand-build an `entry` dict rather than routing through the `swept(**overrides)` factory, so a data-contract field (`zone_name`) is missing from two of them and was already caught missing once (the `run_main_in_a_subprocess` driver, Task 6) | **Leave** (the surviving two instances). Harmless today — `zone_name` is read by no code path, and the other hand-built entry is excluded before any body-builder reads its missing fields — but it is an instance fix where a class fix exists ("fix the class, not the instance"); worth doing if the branch is touched again. |
| No progress output during the resolution phase at default verbosity (218 entries × up to 2 lookups × up to 2 retries can mean ~40 minutes of silence under a resolver outage, vs. ~2 minutes normally) | **Leave.** SPEC §2 forbids performance work, and this is an observability gap, not a performance one, but was judged not worth a mid-branch spec amendment. A single "resolving N targets…" line before the loop would close it. |
| `-excluded.json` has two disjoint entry shapes (codes 1–2 carry `zone_ids`/`origins`/`record_id`/`record_ids`; codes 3–8 carry `resolved_a`/`resolved_aaaa`), with `reason` as the only discriminator | **Leave.** Contract-legal — SPEC §5.6 marks the non-`reason`/`detail` keys illustrative, not exhaustive — but an applier/triage-tooling author should be told explicitly in one added sentence. |
| R3.1a (AAAA is skipped, not resolved, when A is indeterminate) is invisible to the operator: both the module docstring and `CLAUDE.md` say every run resolves "both A and AAAA" with no caveat | **Leave.** Cheap to add (one clause in each), but not blocking; an operator investigating a `resolution-failed` entry cannot currently tell "AAAA never attempted" from "AAAA attempted and failed," both render as `null`. |
| SPEC §15 acceptance item 4's pasted error text is hard-wrapped across two lines in the document where the program actually emits one line | **Leave.** A transcription artifact of pasting into a Markdown table cell, not a behavior claim; the real single-line output was independently confirmed during the final fix wave. |

Two smaller items were raised and closed (not parked) during the branch and are recorded here only
so they are not mistaken for open: the duplicate ambiguous-exclusion ATTENTION line (both the Task
4 implementer and reviewer flagged it; the controller made a binding decision in Task 6 to keep the
uniform R7.1 line and retire `collect_entries`' own warning — closed, not deferred) and the dead
`GOOD = None` test-file placeholder from the Task 4 brief (deleted; `grep -n GOOD` on the test file
now returns nothing).

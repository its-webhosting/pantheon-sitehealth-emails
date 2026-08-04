# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`pantheon-sitehealth-emails` is a standalone Python script that pulls traffic and
site-health data from [Pantheon](https://pantheon.io/) hosting (via the Terminus CLI,
WP-CLI, and Drush), stores traffic history in a database, and emails each site owner a
monthly report with a plan-cost recommendation. It is used by University of Michigan ITS
Web Hosting Services and is written to be reusable by other institutions via a config file.

## Commands

The whole tool is invoked through one executable, `./pantheon-sitehealth-emails` (run it
directly; it has a `#!/usr/bin/env python` shebang and expects the venv active). It is a
thin (~17-line) shim that calls `psh.cli.main()`; the program body lives in the `psh` package
(`psh/cli.py` holds `main()`, the argparse pair, and the per-site pipeline; the gateway/config/
db/traffic/plans/gather/charts/render/mail/lifecycle/dns layers are sibling `psh/` modules —
see **Architecture**). There is no build step; for the test suite see **Testing** below.

```bash
# Environment (see README.md for full first-time setup with uv/PHP/mysql/aws)
source .venv/bin/activate
uv pip install .[mysql,aws,cloudflare]   # Python deps; drop features you don't use
composer install                          # installs the PHP Emogrifier CSS inliner

# One-time: create database tables (uses [Database] section of the .toml)
./pantheon-sitehealth-emails --create-tables

# Weekly: refresh visitor counts in the DB without generating reports
./pantheon-sitehealth-emails --update --all

# Monthly report run (--date should be the LAST day of the reporting month):
./pantheon-sitehealth-emails --date 20240731 its-wws-test1   # single site, safe test
./pantheon-sitehealth-emails --date 20240731 --all           # dry run: emails go to YOU
./pantheon-sitehealth-emails --date 20240731 --all --for-real # sends to site owners

./pantheon-sitehealth-emails --help
```

Key flags (the parser sets `allow_abbrev=False`, so no `--for` → `--for-real` foot-gun):
`--all` vs. an explicit `SITE` list are mutually exclusive (one is required
unless `--create-tables`); `--config`/`-c` picks the TOML file (default
`pantheon-sitehealth-emails.toml`). **Without `--for-real`, mail is addressed to the logged-in
user, not to owners — this is the primary safety mechanism and the run's blast-radius control;
always dry-run first.** `--update`
only refreshes traffic data; `--only-warn` checks sites for warnings — including the plan
recommendation, which is computed before the gate so a warning-only run also gets an
`its-recommends-plan` row — without generating
reports or sending mail; `--import-older-metrics` backfills Pantheon's weekly/monthly
aggregates (and is mutually exclusive with `--create-tables`); `-v`/`-vv`/`-vvv` increase
verbosity (`--create-tables` forces `-vvv`). `--update-cloudflare-fqdns` /
`--no-update-cloudflare-fqdns` (mutually exclusive) force / suppress the `fqdns.json` refresh
(Cloudflare plugin; see the fqdns note under Architecture). `--allow-any-source-ip` skips the
`[Cloudflare.cachecheck]` egress-IP allowlist test (see the cachecheck note under Architecture).
`--resume-from SITE_NAME` (requires `--all`) starts the sorted site loop at that site, inclusive
— for resuming an interrupted `--all` run (see the resume note under Architecture).

### `find-platform-domains-dns` (temporary utility)

A standalone, deletable script — **not** part of the main program and importing nothing from
`psh/`/`check/`/`plugin/` — that lists every custom domain in the organization whose DNS still
reaches a Pantheon platform domain (`*.pantheonsite.io`) by CNAME, as CSV on stdout:
`site_name,site_env,custom_domain,dns_record,platform_domain` — that same line is written as a
**header row**, flushed before the first site is swept, so a hit-free sweep still names its
columns and a doomed stdout (`> /dev/full`) aborts at second zero instead of at the first hit;
appending a re-run to an existing CSV therefore appends a second header along with the interrupted
site's duplicate rows. `dns_record` is the FQDN owning
the hitting CNAME record, which is what a downstream rewriter must change. Operator messages and
a `sites=… indeterminate=…` summary go to stderr; exit 0 = clean sweep, 1 = completed with
indeterminates, 2 = could not complete, 130 = interrupted. There is no `--resume-from`; instead,
an aborted sweep prints the last site it completed (or, if the very first site was interrupted,
which one it was mid-processing) and the **names** of every site not yet reached, as a
paste-able re-run command **rebuilt from the argv the dead run received** (so `-c CONFIG` and
`-v` survive — dropping `-c` handed the operator a command reading a different config file) —
the names are the point, since "137 sites not reached" gives the operator no way to reconstruct
which 137 they were. Resuming re-sweeps the interrupted site, so appending to the same CSV
duplicates that site's rows. `-c` is read **only** on the whole-organization path: a
`SITE`-argument sweep never uses `[Pantheon].org_id` and does not require the file to exist.
**Those four codes cover everything the program itself writes, and holding that line takes
explicit work**: CPython's shutdown flush covers **both** std streams and turns a failure of
either into exit **120**, so a run redirected at a full disk (`> /dev/full`, `2>>sweep.log` on a
filesystem that fills) escaped the taxonomy entirely until each stream got a "detach only a stream
a real write/flush has proven doomed" guard — never an unconditional one, which discards a
buffered CSV row and, under pytest's fd-level capture, repoints the session's own stream at
`/dev/null`. Guarded by `test_a_healthy_stdout_is_never_detached_on_an_abort` /
`test_a_healthy_stderr_is_never_detached_on_an_abort` and their doomed-stream twins.
**The stated exception, measured and deliberately left open**: argparse writes its own usage and
`--help` text before that guard exists and outside every handler, so `--bogus 2>/dev/full` and
`--help >/dev/full` still exit 120. Pre-existing, and declined rather than overlooked — SPEC
§2.2's G0-ordering row records why wrapping `parse_args` was judged not worth it here.

```bash
./find-platform-domains-dns its-wws-test1     # one site
./find-platform-domains-dns > domains.csv     # the whole org, ~38 minutes
```

`find-platform-domains-dns.py` is a committed symlink to the script above, same convention as
`pantheon-sitehealth-emails.py`: ruff, pyright, and CodeGraph key off the `.py` extension and
would otherwise be blind to the extension-less real file. It uses the Pantheon API (machine
token from `$PANTHEON_MACHINE_TOKEN` or `~/.terminus/cache/tokens/`), and its DNS walk is a
**copy** of `check/pantheon_cdn_change/chain.py` plus `psh/dns_classify.py`'s resolver seam —
copied, not imported, so most of deleting this feature is `git rm` of those three files (the
full checklist, including **three** `pyproject.toml` entries — two `[tool.ruff.lint.per-file-
ignores]` lines plus the `[tool.pyright].include` one — and a `ruff-check.sh` case arm, is
`development/2026-07-28-platform-domain-util/SPEC.md` §14). Note the API's site-list cursor has
a silent failure mode (it can return page 1 again instead of the next page); the script detects
it and exits 2 rather than sweeping a truncated site list. **Delete this script after Pantheon's
CDN migration** — checklist in `development/2026-07-28-platform-domain-util/SPEC.md` §14.

### `find-platform-domains-cloudflare` (temporary utility)

A standalone, deletable script — **not** part of the main program and importing nothing from
`psh/`/`check/`/`plugin/` — that writes every Cloudflare DNS **CNAME whose target ends in
`.pantheonsite.io`** as an inventory, plus the batch calls that would rewrite each one to the
addresses its target resolves to and the batch calls that would undo that rewrite. It is the
Cloudflare-side counterpart to `find-platform-domains-dns`: that one reads public DNS and is blind
to a proxied record's target; `fqdns.json` is built with `proxied=True` and is blind to a DNS-only
record. This considers **all** records in **all** zones of every account the credentials can see,
unless **zone names are given as positional arguments**, which narrows the record sweep to those
zones. Legacy `*.gotpantheon.com` targets are out of scope. Full spec:
`development/2026-07-31-platform-domain-util3/SPEC.md`.

**A subset run (naming `ZONE`s) narrows the sweep but not the hazard.** The account and zone
*lists* are still read in full — that is the cheap half (187 zones vs. 22,911 records) — and it
keeps the completeness cross-check, the zero-zone scope guard, and the account count; only the
record fetch is skipped for an unselected zone. **Zone matching is exact** on the same
`normalize()` (case and a trailing dot ignored); a name matching no zone is **fatal (exit 2) and
every miss is named**, because a typo yielding a short sweep is exactly the under-reporting
failure the design refuses to have. A subset also **cannot see a cross-zone duplicate** living in
an unselected zone, so an entry can look unambiguous when it is not — one more reason a rewrite is
driven from a full sweep. Writing a subset to a file with `-o` is still byte-shape-identical to a
full sweep, so a narrowed run written that way emits a loud `ATTENTION: … covers N of M zones …
MUST NOT be used as the baseline for a rewrite`; the redirect form (`… engin.umich.edu > file`) is
invisible to the program and cannot be caught at all.

**`-o/--output-basename BASENAME` writes four files; without it, only the inventory goes to
stdout.** A `.` anywhere in BASENAME's **final path component** is fatal (directory components may
contain dots — `out/v1.2/engin-zone` is fine, `engin-zone.json` is not); the old `-o PATH` form is
gone, so the muscle-memory `-o platform-domains-cloudflare.json` invocation from before this
increment is now a startup error naming the mistake. Before the first Cloudflare API call, the
parent directory of BASENAME is probed for writability (a temp file created and removed there), so
an unwritable destination is caught at second zero, not after the ~2-minute sweep. The four files:

| File | Contents |
|---|---|
| `<basename>.json` (or stdout) | The **inventory**: every non-ambiguous platform CNAME, keyed by normalized FQDN |
| `<basename>-plan.json` | The **forward rewrite**: one Cloudflare batch call per FQDN, platform CNAME → resolved A/AAAA |
| `<basename>-revert.json` | The **reverse** of that same batch call, built from the swept CNAME |
| `<basename>-excluded.json` | Every FQDN that got **no** plan/revert entry, with a reason code and detail |

Only the inventory exists in stdout mode — resolution, classification and exclusion still run in
both modes, so the inventory is byte-identical between them and only its destination differs.
**This utility NEVER calls the Cloudflare API to write anything.**
`apply-platform-domains-cloudflare` (below) is the applier that reads a plan or revert file and
performs the actual batch calls (SPEC §5.4 is its normative contract, superseded in one respect by
the applier's own SPEC R4 — see that subsection).

**Two traps when comparing the inventory to `fqdns.json`:** that file keys by the **raw**
`record.name` (normalize both sides, or you invent phantom entries), and its `origins` means
something **wider** — every proxied record's content at that name, IP addresses included — where
this file's holds only matching platform-CNAME targets. `settings` is `.model_dump()`ed (it is a
pydantic model and is otherwise unserializable). The inventory is **produced in full on every
run**, whatever the age of anything on disk; a run that matches nothing emits `{}` loudly rather
than leaving a stale file. It drives a *destructive* rewrite, so **regenerate the baseline
immediately before any rewrite** — the inventory's mtime is its only freshness signal (the
plan/revert/excluded files instead carry a `generated.at` timestamp, SPEC §5.5).

**Every run now resolves each entry's target** — the `*.pantheonsite.io` hostname the platform
CNAME points at — for both A and AAAA, following CNAME chains, through the one DNS seam
`resolve()`; this happens in stdout mode too (SPEC R3.2), which is why the inventory is identical
between modes. A `Timeout`/`NoNameservers` is retried once before being treated as indeterminate.

The inventory gained four fields over the pre-this-increment shape: `name` (the **raw**
`record.name` — the JSON key is `normalize()`d, and a batch POST's `name` must be exactly what
Cloudflare holds, Punycode included), `zone_name`, `resolved_a` and `resolved_aaaa`.
**`resolved_a`/`resolved_aaaa` are `[]` for a definitive absence (NXDOMAIN/NoAnswer) and `null` for
an indeterminate lookup** — collapsing the two would tell an operator a target has no addresses
when the run never established that, the same distinction the sweep already keeps between a null
and a false `proxied`. The rest of the shape is unchanged: `{zone_id, origins, record_id, proxied,
ttl, comment, tags, settings}`, every scalar first-record-wins. **`origins` in the inventory always
has exactly one element** — `collect_entries` accumulates every match while folding, but a second
one makes the FQDN ambiguous and R4.1 then removes it from the inventory outright, so no
multi-origin entry can survive; `sole_origin()` raises `InvariantError` if one ever reaches a body
builder. Do not write an applier loop over `origins` expecting more than one, and do not read the
inventory as able to express ambiguity — it deliberately cannot; `-excluded.json` is where an
ambiguous FQDN's `origins` list (and its `zone_ids`/`record_ids`) lives.
**Ambiguous FQDNs** (more than one platform CNAME for the same name, in one zone or across two) are
**omitted from the inventory entirely, in both modes** — a deliberate change from before this
increment, when the first record_id of two stayed in and was presented as if it were actionable.

**`delete_match` lives OUTSIDE `body` in every plan and revert entry.** Cloudflare's batch
`deletes` items are exactly `{"id": …}` — there is no name/type/content delete form — and a plan's
`posts` mint ids that do not exist until the plan is applied, so the ids to delete on a revert (or
a re-applied plan) cannot be known until an applier resolves `delete_match` against the zone's
records at apply time. Keeping it outside `body` means `body` alone is always a real, postable
batch body and can never be mistaken for a complete request.

**Eight reason codes**, listed here in the order they are checked: `ambiguous-multiple-origins`,
`ambiguous-multiple-zones`, `unknown-proxy-status`, `resolution-failed`, `no-a`,
`platform-a-out-of-range`, `no-aaaa`, `platform-aaaa-out-of-range`. **Only the two ambiguous codes
also remove the FQDN from the inventory**; the other six leave it in the inventory but out of the
plan and revert. `resolution-failed` MUST be tested before `no-a`: an indeterminate lookup is
`null`, not `[]`, and a `not resolved_a` test cannot tell the two apart. Every exclusion prints an
unconditional (never `-v`-gated) stderr `ATTENTION:` line naming the FQDN, the code and the
detail.

**Exit 1 is new: "completed with exclusions"** (≥1 FQDN carries a reason code). The taxonomy is
now 0 = nothing excluded, 1 = completed with exclusions, 2 = could not complete, 130 =
interrupted. Giving 1 that meaning is only trustworthy because `main()` ends with the sibling's
last line of defence (`except SystemExit: raise` / `except BaseException` → `ERROR: unexpected
<class>: <msg>`, exit 2): CPython exits 1 on **any** uncaught traceback, so without it a
crashed run and a healthy run with exclusions are indistinguishable to a `case $?`. The only
`return 1` in the program is the exclusion branch. A doomed stdout or stderr is likewise a
named exit 2, NOT the interpreter's 120 — the sibling's guards are ported
(`require_usable_streams` refuses a closed stderr, whose `print` fallback would interleave
operator messages into the JSON; `write_json_stdout` and `report_line` detach only a stream a
**real** write has proven doomed, never unconditionally). **The stated exception, same as the
sibling's and exhaustive:** argparse writes its usage, error and `--help` text before those
guards exist and outside every handler, so both `--help >/dev/full` and `--bogus 2>/dev/full`
still exit 120.

**Pagination is the subtle part, and the first live sweep is why.** All three list endpoints
paginate by page *number*, so when rows shift between page fetches — routine in a zone being
actively written — the same record comes back on two pages while another is stepped over.
Measured on an 18,848-record zone: 2 duplicates and 2 misses in one walk. So every list is
**de-duplicated by record id** (a duplicate reaching the fold would append one origin twice and
raise a *false* duplicate-name warning), and the completeness check compares the **unique** count
against Cloudflare's `total_count`. Raw item count fails both ways — it produced a false
"truncated" abort on one read and a false *pass* on another, where the duplicates and misses
cancelled exactly. A shortfall triggers one re-read unioned with the first, and is then a **loud
warning, not an abort**: a paginated walk of a continuously-written zone may never be exactly
complete, and aborting meant the utility produced nothing at all. The run reports
`Completeness cross-check: N of M paginated lists verified complete, X short, Y unverifiable`.
stdout carries the JSON result (or nothing, with `-o`); every operator message is stderr, and
error text **never** includes an API response body.

Credentials come from `[Cloudflare]` in the same TOML the main program reads, via a **copied**
resolver handling only the `<{env NAME}` / `<{secret env NAME}` forms; any other substitution, and
any non-string value, is a named error rather than a silent passthrough. `enabled` is not
consulted. **`build_client()` pins the client against the ambient environment**, closing the same
four routes, by the same mechanism, as the main program's `pinned_client()` — see **Cloudflare
auth + shared client** under *Architecture* for the one full description of what those routes are
and why the pin is load-bearing. This is a **second, independent copy** of that pin (the utility
imports nothing from `plugin/`, so it can be deleted with `git rm`), and both are measured against
cloudflare 5.4.0 while `pyproject` declares the dependency unpinned — so an SDK upgrade has
**three** places to check (the main program's `pinned_client()`, this utility's `build_client()`,
and `apply-platform-domains-cloudflare`'s own copy, below), each with its own real-built-request
test. **This third copy is the only one of the three that performs writes** — an upgrade that
silently breaks the pin here is a credential-disclosure-plus-rewrite risk, not just a
disclosure risk (see that subsection's Security note).

```bash
# refresh the org-wide baseline (~2 minutes) -- do this immediately before any rewrite.
# Use -o with a BASENAME (no extension), NOT `> file`: the shell truncates a redirect target
# BEFORE the sweep starts, so any failed run (bad config, API error) leaves a zero-byte file
# where the baseline was; -o writes each of the four files to a temp file and os.replace()s it,
# only on success.
./find-platform-domains-cloudflare -o platform-domains-cloudflare
# -> platform-domains-cloudflare.json, -plan.json, -revert.json, -excluded.json

# ZONE names go AFTER the options -- argparse cannot interleave positionals with flags:
./find-platform-domains-cloudflare -v -o /tmp/one-zone engin.umich.edu seas.umich.edu
./find-platform-domains-cloudflare -v | jq 'keys'   # every zone, inventory only, to stdout
```

First live run (2026-07-30, before this increment added DNS resolution and the plan/revert/excluded
files): 4 accounts, 187 zones, 22,911 records, 218 platform-domain CNAMEs of which 5 DNS-only, in
2m 17s — 192 of 192 lists verified complete, and 0 discrepancies against a 50-hour-old
`fqdns.json`.

`find-platform-domains-cloudflare.py` is a committed symlink to the script above, same convention
as `pantheon-sitehealth-emails.py` and `find-platform-domains-dns.py`: ruff, pyright, and
CodeGraph key off the `.py` extension and would otherwise be blind to the extension-less real
file. **Delete this script after Pantheon's CDN migration** — checklist in
`development/2026-07-30-platform-domain-util2/SPEC.md` §11 (amended, glob only, by
`development/2026-07-31-platform-domain-util3/SPEC.md` §13).

### `apply-platform-domains-cloudflare` (temporary utility)

A standalone, deletable script — **not** part of the main program and importing nothing from
`psh/`/`check/`/`plugin/` — that reads the **one** plan-or-revert file
`find-platform-domains-cloudflare` writes and performs the Cloudflare DNS batch calls it
describes, or — by default — reports exactly what it would do and changes nothing. It is the
**applier** whose contract was written but not implemented as §5.4 of
`development/2026-07-31-platform-domain-util3/SPEC.md` (that section's per-entry tolerance is now
**superseded** — see below). Full spec: `development/2026-08-03-platform-domain-util4/SPEC.md`.

**It takes exactly one file: a `<basename>-plan.json` or `<basename>-revert.json`.** Not the
inventory (`<basename>.json` — this script never reads it, only the sibling writes it), not both
directions, not a config-driven set. An `-excluded.json` is **refused by name**: it carries no
`body` at all (`generated.direction` is `"excluded"`, not `"plan"`/`"revert"`), and the file
contract's check 2 names that explicitly rather than failing on a missing key several checks
later.

**Three passes, strictly ordered, no interleaving: validate → report → apply.** Pass 1 lists each
selected entry's live Cloudflare records (read-only) and classifies it into one of seven verdicts
(below). If **any** selected entry is invalid, the run reports every invalid one and exits 2
having written nothing — **the whole file**, not just the bad entries. Pass 2 (the report) runs
**identically in both modes**, from the same data pass 1 produced, so a dry run is a rehearsal of
the real run rather than a second implementation of it — any divergence between what a dry run
prints and what `--for-real` does would be a first-order defect in a destructive tool. Pass 3
(apply) runs only with `--for-real`, processes entries in the file's own sorted key order, and
stops at the **first** failure — it never reverts what it already applied and never continues past
a failure to the remaining entries. This is the **all-or-nothing property**: a run either passes
validation entirely and then applies, or fails validation and touches nothing at all.

**Seven verdicts; two are valid.** `ready` (records match what's meant to be deleted — applied in
pass 3) and `already-applied` (records already match the target state — skipped, reported, and
counted, contributing to exit 1) are valid. `record-ambiguous`, `partially-applied`,
`unexpected-records`, `records-missing` and `proxy-status-drift` are invalid and abort the whole
run. This is a
**deliberate narrowing** of util3 SPEC §5.4's original applier contract, on `PROMPT.md`'s explicit
instruction: §5.4 said a zero-match `delete_match` should be *skipped and reported*, and a
multi-match one *refused and reported*, with the rest of the file still applied — per-entry
tolerance. Here a zero-match entry is skipped **only** when it is affirmatively `already-applied`
(records equal what would be posted, never merely inferred from what's missing); every other
invalid state, including the multi-match case, aborts the **entire** run before anything is
written. Without the `already-applied` carve-out a run that died at entry 12 of 217 could never be
safely re-run — re-running the same file to finish an interrupted job, and applying a file that is
already fully applied, are both meant to be safe, cheap, and call zero Cloudflare write endpoints.

**`proxy-status-drift`, and why the proxy status is checked BESIDE the comparison key rather than
inside it.** `record_key` is `(TYPE, normalize(name), canonical_content)` and carries no `proxied`
— it must stay comparable against `delete_match`, whose items are `{type, name, content}` only,
because Cloudflare's batch `deletes` has no name/type/content form. So `proxied` was read by nobody:
**measured**, with Cloudflare holding exactly the plan's A record but `proxied=False`, `verdict_for`
returned `already-applied` and `verify_records` returned `True` — a DNS-only replacement is out of
certificate service (an HTTPS outage plus origin-IP exposure), which is the migration's worst
outcome. `proxy_status_mismatches(posts, rows)` is now a second comparison made in the two places
that compare R against **P**: the `already-applied` row (a disagreement is `proxy-status-drift`,
invalid, abort) and the post-apply verification (a disagreement is a `VerifyError` → `unverified` →
exit 3). The **delete** side is deliberately unchecked — those records are about to be deleted and
`delete_match` carries no `proxied`. A live `proxied` of **`None` is a mismatch, not a pass**: it is
`Optional[bool]` on every SDK model and the sibling excludes a null swept status as
`unknown-proxy-status` because "guessing either way is unsafe"; it gets its own "UNKNOWN (null)"
wording, since "DNS-only" would be a claim the script cannot make.

**The file contract has nine checks, not eight.** Check 9 — every post in one entry must agree on
`proxied` and `ttl` — was `describe_change`'s second `InvariantError`, raised in *pass 2* after
every entry had already been read from Cloudflare. It is a property of the operator's file, so it is
a `PlanFileError` before the first API call; `InvariantError` is defined as "not an operator error".
`describe_change` keeps the guard, where the class is now correct: with check 9 upstream, reaching
it means the gate has a bug.

**The file's own `generated` header is checked, and warned about — never refused.** Immediately
after the file contract passes and **before the Cloudflare client is built**, `read_provenance()`
reads `zones_swept`/`zones_total` and `at` and writes an unconditional stderr `ATTENTION` when the
sweep was **partial** (`N of M zones` — the sibling writes those two integers exactly so an applier
can check them, and a narrowed sweep cannot see a cross-zone duplicate, so an entry can look
unambiguous when it is not), when the pair is **absent or non-integer** (unverifiable, treat as
partial), when the file is **older than 24 hours** (`STALE_PLAN_HOURS`, matching this repo's
`fqdns.json` staleness convention — validation compares R against the CNAME, so a plan whose
*addresses* went stale still validates `ready` and then writes the wrong ones), when the stamp is in
the **future** (clock skew), or when it **cannot be read**. Both numbers land in the run record as
`run.source_zones_swept`/`source_zones_total`, on every run, not only the alarming one. It warns
rather than refuses because a narrow sweep is a documented workflow (`-o /tmp/one-zone
engin.umich.edu`) — refusal would need an override flag, which is one more thing to pass by reflex;
what the script owes the operator is that the judgment cannot be made unknowingly.

**The exit taxonomy adds a code the siblings don't have.** Both siblings use `0 / 1 / 2 / 130`;
this script adds **3**: `0` completed clean (or a dry run that validated clean), `1` completed
with ≥1 `already-applied` skip, `2` could not complete and **nothing in Cloudflare was changed**,
`3` **failed mid-apply and Cloudflare was left partially changed**, `130` interrupted. The new code
exists because folding a half-finished rewrite into `2` would make it indistinguishable, to an
operator's `case $?`, from a clean refusal that touched nothing — after a destructive run the
first question is "did it change anything?", and `2` is a promise this script makes about
production DNS, not a generic failure bucket. `changed_count()` (one shared helper, read by both
`exit_code_for` and the summary's `mode:` line) counts an entry as changed when its outcome is
`applied`, `unverified` **or** `unknown` — every state where Cloudflare may or does hold a change
— and `failed` is deliberately excluded from it, because a batch is one transaction and a rejected
call commits nothing. No failure path — not a validation abort, not an `InvariantError` from this
script's own reasoning, not the `except BaseException` last line of defence — may report `2` once
anything has actually changed. **That takes a reader half AND a writer half, and shipping only the
reader half is how it was false once already.** The reader half is that every arm computes the code
from `changed_count()` rather than a literal; the writer half is that `apply_all`'s handler chain
ends in a **catch-all** that records the in-flight entry `unknown` and re-raises, so an exception no
clause names cannot leave an attempted entry at its `not-attempted` seed. Measured with only the
reader half in place: a one-entry plan whose batch call **returned** and whose verification read
then raised `ValueError` (the SDK calls `response.json()` unguarded, so a truncated 200 raises
`json.JSONDecodeError` — neither a `CloudflareError` nor an `OSError`) made one batch call and
exited **2**, "nothing in Cloudflare was changed", with a `mode:` line reading `0 of 1 entries
changed`. The one class deliberately exempt from that catch-all is `InvariantError`, which stays
`not-attempted`: `apply_entry`'s only pre-batch raiser is `merge_body`, so for it the "nothing
committed" claim is true, and relabelling would turn a truthful `2` into a false `3`. The
companion guard is in `apply_entry`: everything after the batch call returned sits inside one
`try` that converts any unrecognised `Exception` (never `BaseException` — a Ctrl-C must still
reach `apply_all`'s `unknown` arm, SPEC §9.3) into a `VerifyError` naming the original class,
because the one thing every exception raised past the batch call has in common is that the batch
already committed. Same documented exception as both siblings: argparse's own `--help`/usage-error text is written before
any stream guard exists and outside every handler, so `--help >/dev/full` and
`--bogus 2>/dev/full` still exit **120**.

There are **seven outcomes**, not six — `outcome` (what happened to one entry this run) is a
different axis from `verdict` (what pass 1 decided about it): `applied`, `already-applied`,
`planned` (the dry-run stand-in for `applied`), `failed` (the batch was rejected — nothing
committed), `unverified` (the batch **returned**, so Cloudflare committed, but the post-apply
re-list didn't confirm it after one 2-second retry, or the re-list itself failed, **or anything at
all was raised after the batch returned**), `unknown` (the call didn't complete at all — dropped
connection, timeout, a Ctrl-C mid-call, **or a failure this script cannot place relative to the
commit** — so whether it committed isn't known), and `not-attempted` (never reached, because an
earlier entry failed).
`unverified` and `unknown` both count toward `changed_count()`; `failed` does not. A `VerifyError`
(subclass of `ApplyError`) is what pass 3 raises on a surviving verification mismatch or a failed
verification read — it is what produces the `unverified` outcome and exit 3, never `failed`/exit
2, because the write already happened.

**Pass 3 stops at the first failure, and each of its four stop paths is pinned by its own
three-entry test** asserting on the fake client's *recorded batch calls* that the third entry was
never posted. The `failed` arm was pinned that way from the start and the `unverified`/`unknown`
arms were not: every test reaching them used a one-entry document, where `return` and `continue`
are indistinguishable, so `return` → `continue` in either left the whole suite green while the
mutated run rewrote a third production zone past an entry of unknown fate — the one behavior
`PROMPT.md` forbids most explicitly. Asserting outcome *labels* does not catch it; a `continue`
leaves the later entries looking plausible.

**`--for-real` is the blast-radius gate**, same role as the main program's own `--for-real`
(without it, mail goes to the operator, not to owners) — here, without it, no batch call is ever
made at all (asserted against the fake client's recorded calls, not inferred; neither sibling
needs an equivalent, since neither ever writes to Cloudflare). **`--only FQDN` is repeatable
(`action="append"`),
deliberately NOT `nargs="+"`**: with one positional `FILE` and a variadic `--only`,
`--only a b file.json` would silently swallow the filename into the option — the same
positional-vs-variadic ambiguity the Cloudflare sibling's `ZONE` arguments avoid by going *after*
the flags. A repeatable single-value option has no such ambiguity, at the cost of typing `--only`
twice. Explicit over clever. An `--only` name matching no key in the file is fatal (exit 2) and
every miss is named, same reasoning as the sibling's unmatched `ZONE` names — a typo that silently
narrows a destructive run is the under-reporting failure this script family refuses to have.
Unselected entries are never validated and never counted as anything but "in the file" — validating
an entry the run won't touch would let an unrelated FQDN's drift abort a deliberately narrow run.

**The run record is written on every exit path, dry runs included** —
`<input-stem>-run-<YYYYMMDDThhmmssZ>.json`, beside the input file, named `-run-` and not
`-applied-` for exactly that reason. It carries `for_real: false` on a dry run, because a dry run
*is* the validation report and the thing an operator attaches to a change ticket before the
change. A run-record write failure is reported on stderr but does not, by itself, downgrade an
earned exit code back to 2 once something was actually changed (same PD#1 reasoning as the exit
taxonomy above) — it only forces exit 2 when the run had changed nothing anyway. **One documented
exception, shared with the summary block:** argparse's `--help` and usage-error exits happen
inside `parse_args`, before `options.file` even exists, so neither the summary nor the run record
is produced on those two paths — structurally, not as an oversight.

**This is the third appearance, in this script family, of the exit-120 stream-guard class.** Both
siblings' subsections above record it once each — the `find-platform-domains-dns` one describes the
class without naming a function ("each stream got a 'detach only a stream a real write/flush has
proven doomed' guard"; the function is `report_line`, at `find-platform-domains-dns:1090`), and the
`find-platform-domains-cloudflare` one names `write_json_stdout` and `report_line`. CPython's
shutdown flush covers **both**
standard streams and turns a failure of *either* into exit 120, silently overriding whatever
`main()` returned, unless the doomed stream is detached **before** interpreter shutdown — never
unconditionally, which would discard a buffered line and, under pytest's fd-level capture, repoint
the session's own stream at `/dev/null`. This script's `write_report()` is the stdout counterpart
to its `report_line()`. **An in-process test cannot pin this at all** — pytest never tears the
interpreter down, so the shutdown flush this guards against never runs in-process, and a test that
only calls the function directly would stay green even if the guard were deleted. The cover is
**four** real subprocess tests, copying the pattern already in
`tests/unit/test_find_platform_domains_cloudflare.py`: `…doomed_stdout_exits_2_not_120…` and
`…doomed_stderr_exits_2_not_120…` redirect at `/dev/full` — never `subprocess.DEVNULL`, which
accepts every write and would prove nothing — `…stdout_truly_closed…` uses `1>&-`, which makes
`sys.stdout` **None**, where CPython's `print()` then silently does nothing and the whole report
would vanish with no error at all, and
**`test_a_doomed_stdout_during_the_flush_still_exits_a_named_code_not_crashing`** covers the
*flush* path — a doomed stdout hit for the first time **inside `finish()`**, itself called from
inside one of `main()`'s own `except` clauses, where a fresh exception is never redispatched to a
sibling `except`. It is reproduced with a nonexistent `FILE`, so `finish()`'s summary print is the
first stdout write the run attempts. That fourth one is the instance a future maintainer is least
likely to reconstruct, and it was omitted from this list until the 2026-08-04 review's finding 9.

Also **the only one of the family's three independent `build_client()`/environment-pin copies that
performs writes** (see the "three places to check" note in the `find-platform-domains-cloudflare`
subsection above) — an SDK upgrade that silently breaks the pin here is a
credential-disclosure-**plus**-rewrite-aimed-at-an-attacker-chosen-host risk, not just a
disclosure risk, because `$CLOUDFLARE_BASE_URL` redirects every request including the batch calls.

**Being the write copy, it also pins `max_retries=0` on the constructor — a second divergence, and
the one an SDK upgrade is most likely to reopen silently.** Measured against cloudflare 5.4.0:
`_constants.DEFAULT_MAX_RETRIES` is **2** and `BaseClient._should_retry` (`_base_client.py:815`)
retries 408/409/429/5xx with **no HTTP-method check** — a `POST …/dns_records/batch` exactly like a
`GET`. That POST is not idempotent (Cloudflare runs it as one transaction, Deletes then Posts), so a
"failed" response the SDK silently retried can mean the *first* attempt committed and the retry
landed on an already-changed state, answering with its own error (a duplicate-create 400) that this
script would read as `failed` — "rejected, nothing committed" — for a write that committed. Losing
retries on the pass-1 *reads* is the safe direction of the same change (a lost read is
`CloudflareReadError`, exit 2, nothing changed), so the pin is unconditional on the one client this
script builds. It is asserted by `test_build_client_pins_max_retries_to_zero` **and** by a real
`httpx.MockTransport` test proving exactly one POST on a 429/500.

**So the three `build_client()` copies are no longer identical, and an SDK upgrade must check all
three separately.** This one pins `max_retries=0` (the other two do not — neither writes) and nulls
a credential when `creds.get(field) is None`; `plugin/cloudflare/client.py` uses the same `is None`
idiom; `find-platform-domains-cloudflare` is **deliberately** still on the older
`field not in creds`, which only re-nulls an *omitted* keyword and leaves an explicit `None` for the
SDK's own ambient back-fill — left alone because that utility is read-only, its caller guards, and
it is deleted with this one (`development/2026-08-03-platform-domain-util4/SPEC.md` §17 records the
decision).

`apply-platform-domains-cloudflare.py` is a committed symlink to the script above, same convention
as its siblings: ruff, pyright, and CodeGraph key off the `.py` extension **and would otherwise be
blind to the extension-less real file**. **Delete this script after Pantheon's CDN migration** —
checklist in
`development/2026-07-30-platform-domain-util2/SPEC.md` §11 (this script's six-item delta is §11
item 9, added by `development/2026-08-03-platform-domain-util4/SPEC.md` §19).

## Required runtime credentials / external tools

Running against real sites needs, in the environment: `terminus` authenticated with a
Pantheon machine token; an SSH agent holding the Pantheon key (`ssh-add`); `SMTP_PASSWORD`
(U-M Kerberos password, referenced by `[SMTP].password = "<{secret env SMTP_PASSWORD}"`);
optionally `AWS_*` and `CLOUDFLARE_EMAIL`/`CLOUDFLARE_API_KEY` (or `CLOUDFLARE_API_TOKEN`),
referenced by the `[Cloudflare]` settings. **Credentials are never read from the environment
by feature code**: everything flows through config `<{env …}>` / `<{secret env …}>`
substitutions (see the config-substitution note under Architecture). The only direct
`os.environ` touches are `plugin/env/get_env.py` (which *is* the `<{env}` engine) and the
`AWS_PROFILE`/`AWS_DEFAULT_REGION` boto plumbing in `plugin/aws/__init__.py` — don't add more.
See `docs/env-and-smtp-configuration.md` and `docs/email-configuration.md`.
`php` + `composer` must be on PATH. **Note the README warning: Terminus does not work with
PHP 8.4 — use PHP 8.3 or earlier, or the toolchain is dead.**

## Architecture

### Core package + `script_context` shared state

The orchestrator — `main()`, the argparse pair (`build_arg_parser`/`parse_args`), and the
per-site pipeline — lives in **`psh/cli.py`**. The rest of the program body is carved into
sibling `psh/` modules, one layer each; `psh/cli.py` imports the names it calls (and re-imports
the pure helpers below), so it is the single module the test `psh` fixture exposes. Each module:

- **`psh/gateway.py`** — the gateway: every Terminus/WP-CLI/Drush subprocess flows through it
  (the eleven wrappers; the future Pantheon-API transport seam — see the **Terminus/WP/Drush
  wrappers** bullet).
- **`psh/configuration.py`** — the config engine: `process_config`/`config_substitution`/
  `gate_disabled_sections`/`load_news_items`/`umich_enabled`/`cloudflare_enabled` plus the DEFER
  machinery (see **Config substitutions**). `sc.umich_enabled`/`sc.cloudflare_enabled` are
  exposed on the façade.
- **`psh/notice.py`** — `Notice` (a frozen dataclass), `Severity` (a `StrEnum`),
  `NoticeRegistry`, and `DuplicateNoticeCodeError`: the typed notice model (see **Notices vs.
  news**). It imports nothing from `script_context`, so both `sc` and every `psh/` module can
  import it without a cycle.
- **`psh/modules.py`** — module discovery + the hook engine: `find_modules`, `PHASES`,
  `add_hook`/`invoke_hooks`, the consumes/produces DAG validation
  (`validate_hooks`/`ordered_hooks`, the `HookDagError` family), the authoritative `CONTRACT`
  registry, and the `stuff_traffic_contract`/`stuff_gather_contract`/`stuff_envs_contract`
  stuffers (see **Hooks** and the data-contract table). `script_context.py` re-exports
  `PHASES`/`add_hook`/`invoke_hooks` via a top-of-file `from psh.modules import …`, so
  `psh/modules.py` must NOT import `script_context` at module level — its engine functions
  import `sc` at call time (the module docstring carries the diagram). The mutable `sc.hooks`
  dict deliberately stays in `script_context.py`, because `reset_sc` rebinds it around every
  test and CAMPAIGN.md §3.4 bars module-level mutable state in `psh/`.
- **`psh/db.py`** — every DB touch this program makes: the SQLAlchemy models (`Base`,
  `PantheonTraffic`, `PantheonOverageProtection`), the row types (`TrafficRow`,
  `OverageProtectionRow`), the resilience layer (`db_retry`, `db_retryable`,
  `record_db_reconnect`, `DatabaseUnavailableError`), the read/write units
  (`update_traffic_rows`, `insert_traffic_rows`, `load_traffic_rows`,
  `load_overage_protection_window`), and `db_engine_args` (exposed as `sc.db_engine_args`). See
  **Database**. The two reconnect counters do NOT live here: they are fields of the `RunState`
  dataclass (`psh/lifecycle.py`), reached as
  `sc.run_state.db_reconnects_by_site`/`…failures…` — one shared, `reset_sc`-isolated namespace
  rather than two separately rebindable module bindings of the same name.
- **`psh/traffic.py`** — the traffic-metrics layer: `traffic_table_columns`,
  `get_old_metrics`, `estimate_month_visits`, `build_traffic_table_rows`, and four per-site flow
  functions (`update_site_traffic`, `import_older_site_metrics`, `load_site_traffic`,
  `aggregate_visits_by_month`).
- **`psh/plans.py`** — the plans layer: `cost_table_columns`, `overage_blocks`,
  `contract_year_end`, `plan_costs`, `build_plan_over_time`, `build_plan_recommendation_notice`;
  the typed `PlanCatalog`/`PlanInfo` view over `[Pantheon].plan_info` (`PlanCatalog.from_config`
  performs the `"-"` → `None` normalization **mutating the config sub-dict in place**, so
  `main()`'s `plan_info`/`plan_names` aliases and the chart/annual-billing regions keep reading
  the same object — a copy would fork two views of one config); `resolve_plan_name(site)` (the
  Elite-SKU lookup — `None` on a transient Terminus failure so `main()` can `continue`,
  `sys.exit` preserved on a missing/unknown SKU); `recommend_plan(...)` (returns a frozen
  `PlanRecommendation` and adds the upgrade notice to `site_context` itself); and
  `stuff_plans_contract()` (which nests `cost_same`/`costs_median`/`costs_best` into the single
  `plan_costs` **contract key** `{"same": …, "median": …, "best": …}`).
- **`psh/gather.py`** — the framework gather cores. WordPress: `check_wordpress_plugin` (the
  recommended-WordPress-plugin notice builder the papc/sessions/cloudflare_cms hooks call via
  `sc.check_wordpress_plugin`), `wordpress_network_url`, and `gather_wordpress` (version /
  plugin-list / theme-list fetches, add-on-update collection plugins-then-themes in list order,
  the must-use diagnostic print) returning a **`WordPressGather`** NamedTuple that `main()`
  threads into its locals with last-wins overwrite semantics (a later empty smell never clears
  an earlier one). Drupal: `check_drupal_module` (the recommended-module notice builder the
  Drupal siblings call via `sc.check_drupal_module`), `gather_drupal` (banner + core-status
  fetch + version derivation + `site_results` entry, pm:list, and the D7 pm:updatestatus **or**
  D8+ composer dry-run + composer audit add-on collection — the D7-vs-D8+ branch stays inside
  because it selects between two *gather* strategies, not between checks) returning a
  **`DrupalGather`** NamedTuple threaded last-wins like the WP branch, and `build_smell_notices`
  (the smell-notice *builder*; **its emission stays in `main()`** because it summarizes
  end-of-phase smell state no hook position can guarantee and must stay behind the `--only-warn`
  gate). The `wp_error`/`drush_error` notices for *failed gathers* stay with the fetches (they
  describe the gather, not a check); the notice-emitting checks that once interleaved here live
  in `check/wordpress/`, `check/drupal/`, and `check/umich/`. `gather_drupal`'s composer dry-run
  calls `run_terminus(...)` directly (composer output is human-readable text, not JSON), so this
  module binds `run_terminus` in its **own** namespace — see the two-binding seam note under
  Testing.
- **`psh/charts.py`** — the per-site traffic-chart build: one public function,
  `build_chart(...) -> bytes` (PNG), with the cap-shape geometry as its prologue (recomputed per
  call) plus the chart data prep and matplotlib build. `main()` threads 13 shaped locals into it
  and hands the returned bytes to the MIME assembly. The chart PNG is **not** golden-pinned (the
  `.eml` has no byte golden), so `tests/integration/test_charts.py` is the permanent cover
  (valid PNG, surge-vs-plain figure geometry, estimate visibility, byte determinism, no leaked
  figures); the module docstring records the `plan_on_day` precondition (every clamped month
  midpoint must be a key — production data always satisfies it).
- **`psh/render.py`** — the report-rendering step: `escape_url(url)` (the one-line
  `urllib.parse.quote` wrapper, here so `check/` modules and `psh/gather.py` reach it without a
  cycle) and `render_report(site_name, template_dict) -> tuple[str, str]` (Jinja render + PHP
  inline; see **Rendering**). The inliner's `check=True` failure raises the named
  `subprocess.CalledProcessError` into `main()`'s `except BaseException` abort path.
- **`psh/mail.py`** — the SMTP/MIME layer: `smtp_login() -> SMTP_SSL` (`sys.exit` on missing
  creds), `resolve_recipients(site, site_id) -> tuple[str, str] | None` (`(recipients,
  contacts)`, `None` on a fatal team fetch so `main()` `continue`s; the U-M
  `lsa-disko-project`/`umma-inside-wp` special case rides along inside the `umich_enabled()`
  branch), and `assemble_message(...) -> EmailMessage` (the MIME build — `[Email]`/dry-run
  addressing, related inline-image parts, attachment loop — which also **writes
  `build/{site}.eml`**). `SMTP_SSL` is bound in this module's own namespace — see the seam note
  under Testing. **The send block itself stays in `main()`, not here** — see the per-site
  pipeline.
- **`psh/lifecycle.py`** — the run-lifecycle layer: the **`RunState`** dataclass, the one home
  for `main()`'s run-scoped accumulators (`emails_sent`, `site_savings`, `all_warnings`,
  `site_results`, and the two reconnect counters), constructed once per run and bound to
  `sc.run_state` **before** `invoke_hooks("setup")` so the whole run is one instance, plus its
  `record_site_notices(notices, contacts)` method (the csv append, with its load-bearing
  before-the-send comment), and the run helpers `ResumeSiteNotFoundError`,
  `sites_from_resume_point`, `merge_prior_results`, `finish_run`, `resume_point`,
  `option_strings_taking_a_value`, `resume_command`, `rerun_command`, `abort_reason`, and
  `abort_run`. `finish_run`/`abort_run` take a `run_state: RunState` and read the accumulators
  from it; `finish_run`'s first statement is `sc.invoke_hooks("run_finish", run_state)`
  (`CONTRACT["run_finish"]` stays `()` — the `RunState` is the hook argument, not a contract
  key). It **NEVER imports `script_context`/`psh.db` at module level** (module-level imports are
  stdlib + `sqlalchemy.exc` + `rich` only) — `sc` is reached at call time, and one call-time
  bridge lives inside a function: `abort_reason`'s `from psh.db import
  DatabaseUnavailableError, db_retryable`. The module docstring carries the import-cycle diagram
  (PD#8).
- **`psh/dns_classify.py`** — the DNS engine: it resolves each domain's A/AAAA records and
  classifies them against the Cloudflare IP ranges (`classify_domains`, returning a `DnsFacts`
  NamedTuple), and `stuff_dns_contract()` publishes those facts into the `site_post_dns`
  data-contract keys. It is a pure data producer — presentation (notices) lives in `check/dns/`.

Cross-cutting state and helpers live in **`script_context.py`** (imported everywhere as `sc`):
`sc.options` (parsed argv), `sc.config` (parsed TOML), `sc.plugin`/`sc.check` (loaded modules),
`sc.news`, `sc.console` (rich), `sc.hooks`, `sc.run_state` (the current run's `RunState` —
rebound by `reset_sc` and by `main()` before `setup`), `sc.substitutions`, `sc.Notice`/
`sc.Severity`/`sc.registry` (reached via a plain top-of-file `from psh.notice import Notice,
Severity, registry`, which makes them module attributes automatically — so these are NOT among
the explicit `sc.<name> = <name>` exposure assignments, unlike `sc.umich_enabled`/
`sc.cloudflare_enabled`), and helpers `debug()`, `add_news_item()`, `html_to_text()`.
**`html_to_text()` builds a fresh `HTML2Text` per call** — never reintroduce a shared instance:
it is stateful, and sharing one made the first notice of a run render in a different link style
from every other (the module-level `sc.text_maker` it replaced is gone). The parser is built by
`build_arg_parser()` and `sc.options` is populated by the caller via `parse_args()` before other
functions run, so it is available to every function at call time.

### Plugin / check module system (`plugin/`, `check/`)

`find_modules()` (in `psh/modules.py`) walks `plugin/` and `check/` for **non-empty
`__init__.py`** files — the empty top-level `plugin/__init__.py` and `check/__init__.py` are
skipped — and imports each containing package (currently `plugin.aws`, `plugin.cloudflare`,
`plugin.env`, `plugin.umich`, `check.addon_updates`, `check.cloudflare`, `check.dns`,
`check.drupal`, `check.pantheon`, `check.pantheon_cdn_change`, `check.umich`, `check.wordpress`).
**The walk is CWD-relative and keys off a non-empty `__init__.py`**: a package with an empty
`__init__.py`, or a run whose CWD lacks the `check`/`plugin` trees, silently loads nothing
(this is why the e2e workdir symlinks them — see Testing). Each `__init__.py` self-registers at
import time — usually pulling in a sibling file with the actual logic (`aws/get_secret.py`,
`cloudflare/ips.py`, `env/get_env.py`, `umich/portal.py`, `check/umich/sitelens.py`) — guarded
by a check of `sc.config` (e.g. only register if `[Cloudflare].enabled`). **Exception:**
`plugin.env` (the `<{env NAME}` / `<{secret env NAME}` substitutions, with an optional trailing
default) registers **unconditionally** — no `[Env]` section — because it has no dependency and
core config (`[SMTP].username = "<{env USER}"`) needs it.

`plugin/` = integration plugins (data sources / service integrations: aws secrets, cloudflare
IPs, umich portal DB); `check/` = site-health checks that add report notices and sections.
Modules register by:

- **Hooks** — `sc.add_hook('<phase>', {'name': …, 'func': …, 'consumes': […], 'produces': […]})`.
  The `consumes`/`produces` declarations are **mandatory** (each a possibly-empty list of
  data-contract key names, table below; missing/malformed → fatal at registration, no legacy
  mode). Phases are the ordered `sc.PHASES` tuple: `setup` (once per run — **including
  `--create-tables`**, which exits later), then per site `site_pre`, `site_post_traffic`,
  `site_post_dns`, `site_post_gather`, `site_pre_render`, and per run `run_finish` (fired as the
  first statement of `finish_run()` — before any teardown or artifact write, on completed AND
  aborted runs; receives the run's `RunState`; no consumer yet). Each site phase receives the
  `SiteContext`; the per-phase guaranteed keys are the data-contract table below.
  **Bare names not in `PHASES` are a fatal error** in both `add_hook` and `invoke_hooks`;
  dotted names (e.g. `setup.umich.portal`) are plugin-defined events, allowed and invoked by
  whoever owns them — but they **MUST declare `consumes`/`produces` empty** (contract keys are
  phase-anchored; a dotted event has no phase position). After the import loops, `main()` runs
  `psh.modules.validate_hooks()`, which is **fatal** (named `HookDagError` subclasses) on
  **four** conditions: a consumed key nothing produces; two producers of one key (hooks or the
  core `CONTRACT` registry — one owner per key, so a silent overwrite of a contract key can
  never ship, PD#1); a consumes/produces cycle among same-phase hooks; and consuming a key
  first produced in a *later* phase (earlier is fine). The **fifth** CAMPAIGN.md §4 condition —
  a missing/malformed `consumes`/`produces` declaration — is enforced earlier, **at `add_hook`
  time**, as a loud exit, not a `HookDagError`: nothing undeclared ever enters `sc.hooks`. The
  bare/dotted-name check above is likewise an `add_hook`/`invoke_hooks`-time loud error, not one
  of `validate_hooks()`'s `HookDagError` conditions. Within a
  phase `invoke_hooks` runs producers before consumers (registration order breaks ties). The
  permanent `tests/integration/test_hook_dag.py` loads every real check/plugin package (via its
  `ALL_PACKAGES` list) and proves the DAG validates — **keep `ALL_PACKAGES` in sync when adding a
  package**, or the test silently stops covering it. Gating: phases through `site_post_gather`
  run on full-report and `--only-warn` paths; `site_pre_render` full-report only;
  `--update`/`--import-older-metrics` never reach any site phase (they DO reach `run_finish`,
  whose artifact writes are separately gated); a per-site fatal error (e.g. domain:list failure)
  skips that site's remaining phases.
- **Config substitutions** — appending to `sc.substitutions`. TOML string values containing
  `<{ ... }>` are resolved by `process_config()`/`config_substitution()` against these
  registered functions. `process_config()` is run twice: a pre-setup pass resolves everything,
  then a post-setup `deferred_pass=True` pass re-resolves **only** substitutions that deferred.
  A substitution whose backing data a `setup` hook populates (e.g. `plugin.umich`'s `plan_info`,
  which needs the portal DB) returns the `sc.DEFER` sentinel; `config_substitution` re-emits its
  marker with an invisible NUL tag that only the deferred pass matches. This lets pass 2 resolve
  deferrals **without** re-interpreting a pass-1 final value that merely contains a `<{…}>`
  sequence (e.g. a password) — so route secrets through substitutions freely. A substitution
  aborts the run by raising `sc.ConfigSubstitutionError` (caught in `config_substitution`, which
  prints the offending config *path* + message and exits) — this is how `plugin.env.get_env`
  (missing env var) and `plugin.aws.get_secret` (missing secret key) report failures. **Just
  before those substitutions run, `main()` calls `gate_disabled_sections()`**: any section **at
  any depth** with `enabled = false` (boolean identity; nested tables like
  `[Cloudflare.cachecheck]` included, and a disabled parent drops its children entirely) is
  reduced to just `{'enabled': False}`, dropping its other keys **before** substitution — so a
  disabled feature's `<{secret env …}>` values are never required to exist. For substitutions
  that take an optional trailing arg (like `env`), **register the shorter pattern before the
  longer one** (`['env','$name']` before `['env','$name','$default']`), or the best-match engine
  mis-binds and `KeyError`s.

Check and integration-plugin packages:

- `check/umich/` — the U-M checks: sitelens + `cloudflare_cms.py` (CMS-integration checks at
  `site_post_gather`), `oidc_login.py` and `hummingbird.py` (the umich-oidc-login reinstall and
  U-M Hummingbird-fork WordPress-plugin checks, both `site_post_gather`), `drupal_ua.py` (the
  Drupal user-agent check, consumes `framework`/`drupal_version`, a `site_post_gather` hook),
  and `annual_billing.py` (the U-M annual-billing notice for an upcoming contract-year rollover,
  a **`site_pre_render` hook**). `annual_billing` does **not** call `add_notice`: it **produces**
  a hook-declared contract key (`annual_bill_upcoming` iff `sc.contract_year_end(end_date)`),
  which `sort_notices_and_subject` reads with `.get()` after the phase — this is deliberate, so
  the billing row never enters `site_context["notices"]` and never reaches `-notices.csv`
  (load-bearing history, preserved). All of `check/umich/` is under the `[UMich].enabled` gate.
  **That gate is a deliberate behavior change** for the WordPress and Drupal-UA checks: they once
  ran un-gated, so a non-U-M run got U-M-specific advice (e.g. a non-U-M Drupal 8+ site was told
  to configure a `…; UMich; …` user agent) — now they run only for U-M.
- `check/cloudflare/` — the opt-in `[Cloudflare.cachecheck]` cache checks: egress-IP test at
  `setup` + per-FQDN HTTP checks at `site_post_dns`, see `docs/cloudflare-cachecheck.md`.
- `check/dns/` — DNS-resolution notices (`notices.py` builders + the `site_post_dns` `hook.py`),
  fed by the `psh/dns_classify.py` engine; `no-domains`/`no-primary-domain` remain in core.
- `check/pantheon/` — four Pantheon-platform checks (gated on `[Check.pantheon].enabled`,
  **default true**: an absent `[Check]`/`[Check.pantheon]`/`enabled` still registers, so
  relocating a check that ran unconditionally does not silently disable it), one module each:
  `frozen.py` and `live_env.py` (paid plan with no initialized live env; consumes `envs`) at
  `site_pre`; `updates.py` (`terminus upstream:updates:list` staleness, via `sc.terminus`) and
  `php_eol.py` (PHP end-of-life; consumes `envs`) at `site_post_gather`, registered in that
  order. The four notice bodies embed un-gated U-M links (see the still-hardcoded-U-M list under
  Testing).
- `check/wordpress/` — four generic WordPress checks (gated on `[Check.wordpress].enabled`,
  **default true**), all at `site_post_gather`, registered PAPC → sessions → OCP → favicon:
  `papc.py` and `sessions.py` (both delegating to `sc.check_wordpress_plugin`), `ocp.py` (Object
  Cache Pro config probe via `sc.wp_eval`; consumes `wordpress_plugins`) and `favicon.py`
  (favicon presence probe via `sc.wp_eval`; consumes `fqdns_not_behind_cloudflare`). Every hook
  early-returns unless `site_context["framework"].startswith("wordpress")`. The `ocp`/`favicon`
  probes rebind `site_context["wp_smell"]` on non-fatal stderr (one of the two sanctioned
  mutate-during-phase contract keys) and build failure notices with `sc.wp_error`. The favicon
  notice body embeds un-gated its.umich.edu links.
- `check/drupal/` — three generic Drupal checks (gated on `[Check.drupal].enabled`, **default
  true**): `multisite.py` (the multisite probe via `sc.drush_php_script`, a `site_post_dns` hook
  that consumes `custom_domains`/`primary_domain` and **produces** the hook-declared keys
  `drupal_multisite`/`drupal_multisite_smell`, read by `main()` with `.get()` after the phase to
  seed `drush_smell` and gate the core `no-primary-domain` notice), `papc.py` (delegating to
  `sc.check_drupal_module`) and `d7_eol.py` (the `drupal7-eol` notice + the tag1_d7es module
  check), the latter two at `site_post_gather`, registered multisite → papc → d7_eol; each
  early-returns unless the framework starts with `drupal`.
- `check/addon_updates/` — one `site_post_gather` hook, `table.py` (the pending-add-on updates
  table notice, consumes `add_on_updates`, reading the SAME list object the stuffer publishes;
  gated on `[Check.addon_updates].enabled`, **default true**); its `updates-addons` notice body
  embeds an un-gated its.umich.edu support link.
- `check/pantheon_cdn_change/` (`site_post_dns`, unconditional registration) flags custom
  domains still CNAME'd to the legacy Pantheon GCDN (Fastly) — in public DNS or in Cloudflare —
  and gets the replacement records Pantheon requires from `terminus domain:dns`. **Temporary**,
  delete once Pantheon's CDN migration is done — see `docs/pantheon-cdn-change.md`.

To add a check or integration plugin, create a new package dir with a non-empty `__init__.py`
that self-registers — no central registry to edit. Check modules cannot import the dash-named
main script; the helpers they need are exposed as `sc` attributes near the `cloudflare_enabled()`
def: `sc.escape_url`, `sc.check_wordpress_plugin`, `sc.check_drupal_module`, `sc.umich_enabled`,
`sc.cloudflare_enabled`, `sc.terminus`, `sc.fqdn_re`, `sc.wp_eval`/`sc.wp_error` (the OCP/favicon
checks), `sc.drush_php_script`/`sc.drush_error` (the multisite/UA checks), and
`sc.contract_year_end` (the annual-billing hook). Extend that block for new ones (tests
monkeypatch these when loading check modules standalone). A few façade names are exposed
**elsewhere**, not in that block: `sc.db_engine_args` (see § Database) and
`sc.Notice`/`sc.Severity`/`sc.registry` (which reach `sc` via the top-of-`script_context.py`
`from psh.notice import Notice, Severity, registry` import); all are pinned by the
`test_documented_sc_facade_names_exist` house-rule. `check/cloudflare/httpseam.py` holds the ONE
monkeypatchable HTTP seam (`fetch`/`sleep`) and `egress.py` its own `probe` seam — route any new
outbound HTTP in that package through them to stay offline-testable.

### Per-site report pipeline (in `main()`)

For each site: build a `site_context` (holds `notices`, `sections`, `attachments`, traffic data,
plan info), invoke the site phases (below) at their seams, gather Pantheon/WP/Drupal data,
compute the plan recommendation from `[Pantheon.plan_info]` in the config, then render. The
recommendation (`psh.plans.recommend_plan`) runs **before** the `--only-warn` gate, not after
it, so a warning-only run also gets an `its-recommends-plan` row when one applies.

**Normative per-phase data contract** — `main()` stuffs these `site_context` keys just before
invoking each phase; hooks code against this table (keys always exist, empty/None when the
source was disabled, malformed, or failed). **The machine-readable copy — `psh.modules.CONTRACT`
— is authoritative**; this table is its prose rendering, and `tests/unit/test_contract_registry.py`
pins the stuffers (`stuff_traffic_contract`/`stuff_gather_contract`/`stuff_envs_contract` in
`psh/modules.py`, `stuff_dns_contract` in `psh/dns_classify.py`) against it, so drift on either
side goes red:

| Phase | Guaranteed new keys (beyond `site`/`notices`/`sections`/`attachments`) |
|---|---|
| `site_pre` | `envs` (dict — the `terminus env:list` JSON keyed by environment id, each value carrying `id, created, domain, connection_mode, locked, initialized, php_version, php_runtime_generation`. `main()`'s guards ensure `envs["live"]` exists with an `initialized` key before any site phase fires; **`php_version` is NOT guaranteed present** — read it with `.get`. Never `None`/empty when a phase fires: a failed `env:list` fetch skips the site. Core-produced — fetched by `main()` where it gates on it, stuffed by `stuff_envs_contract`. The phase fires after the traffic gather and the `--update`/`--import-older-metrics` continues, just before `site_post_traffic` — NOT at SiteContext creation) |
| `site_post_traffic` | `traffic_rows` (`list[TrafficRow]` — plain `NamedTuple` data, attribute names matching the ORM model: `.site_id`, `.traffic_date`, `.site_plan`, `.visits`, `.pages_served`, `.cache_hits`; **not** live ORM rows, because a `db_retry` rollback expires every loaded ORM object, so a hook holding one would emit an unretried SELECT on the next attribute read), `start_date`, `end_date` |
| `site_post_dns` | `domains`, `custom_domains`, `primary_domain`, `main_fqdn`, `fqdns_behind_cloudflare`, `fqdns_not_behind_cloudflare`, `not_in_dns`, `behind_cloudflare_not_proxied`, `proxied_in_multiple_zones`, `dns_transient` (Cloudflare classification lists `[]` when `[Cloudflare]` disabled, the FQDN resolved to no address, or domains malformed. A FQDN resolving to nothing is `not_in_dns` when definitive else `dns_transient` (unknown) — neither runs Cloudflare checks; a FQDN with ≥1 resolved address is classified even if a sibling lookup was transient. Produced by `psh.dns_classify.classify_domains()`, published via `stuff_dns_contract()`. **Hook-produced keys (NOT registry-owned):** `check.drupal.multisite` additionally *produces* `drupal_multisite` (bool) / `drupal_multisite_smell` (str). They are DAG-declared in the hook's `produces`, present **only** when the probe actually ran (absent when its gate failed, the framework is not Drupal, or `[Check.drupal]` is disabled), so `main()` reads them with `.get(...)` after the phase — never assume they exist) |
| `site_post_gather` | `framework` (str), `site_url` (str, `""` when unknown), `wordpress_version` (str; on a failed fetch it is the fatal `wp eval`'s stdout — `""` in practice, since `wp_eval` always returns decoded-and-stripped stdout; the `"unknown"` fallback survives in `psh/gather.py` but is unreachable through the gateway, which never returns a non-str; None only when not that framework), `drupal_version` (str; `"unknown"` — NOT None — when the version fetch failed; None only when not that framework), `wordpress_plugins` (list\|None), `drupal_modules` (**dict**\|None — drush pm:list returns a dict keyed by module name); None on the plugins/modules keys = not that framework or the gather failed. `add_on_updates` (list of pending add-on-update dicts — `slug`/`name`/`type`/`current_version`/`new_version`; plugins then themes, list order; `[]` when none, not that framework, or the gather failed; stuffed as the SAME list object the `check.addon_updates.table` hook reads, not a copy), `wp_smell`/`drush_smell`/`composer_smell` (str, `""` when none — the stderr of the last non-fatal wp/drush/composer wrapper call that produced any. **`wp_smell` AND `drush_smell` MAY be rebound in place during the phase** — `wp_smell` by `check.wordpress.ocp`/`check.wordpress.favicon`, `drush_smell` by `check.umich.drupal_ua` — their probes' stderr participates in last-wins; these are the **two sanctioned mutate-during-phase keys**, so consumers reading after the phase (the smell emission) MUST read `site_context["wp_smell"]`/`site_context["drush_smell"]`, never a stale `main()` local; the hooks do NOT declare `produces: ['wp_smell']`/`['drush_smell']` — that would be a duplicate-producer fatal against the core `CONTRACT` registry) |
| `site_pre_render` | everything above, plus `current_plan` (str), `recommended_plan` (str; == `current_plan` when no change was recommended or the site had too few in-window months), `plan_costs` (dict `{"same": {plan: float}, "median": {plan: float}, "best": {plan: float}}`; `{}` when ≤4 in-window months), `savings` (float; `0.0` when no recommendation) — the plan-recommendation keys, published by `stuff_plans_contract()` (full-report path only; still no consumer — the documented seam for future report-shaping hooks). **Hook-produced keys (NOT registry-owned):** `check.umich.annual_billing`'s `site_pre_render` hook additionally *produces* `annual_bill_upcoming` (a render dict, built by `site_context.notice_to_dict`) — DAG-declared, present **only** when the hook ran (absent when `[UMich]` is disabled or `sc.contract_year_end(end_date)` was false), so `sort_notices_and_subject` reads it with `.get(...)` after the phase |
| `run_finish` | — (run-level, not per-site: receives no `SiteContext`; it receives the run's `RunState` — `finish_run`'s first statement is `invoke_hooks("run_finish", run_state)`, fired on completed and aborted runs, the seam for future run-level artifact hooks. `CONTRACT["run_finish"]` stays `()`: the `RunState` is the hook argument, not a contract key) |

**The send block stays in `main()`, not `psh/mail.py`.** The send sequence is `smtp_login()` …
`send_message()` … `quit()`, and the accumulator writes `run_state.emails_sent += 1` /
`site_emailed = True` sit **between** `send_message()` and `quit()`. Hoisting the block into
`psh/mail.py` would move those counter updates after `quit()` returns, reopening the
Ctrl-C-during-`quit()` duplicate-email window. `main()` keeps calling `smtp_login()` itself.

- **Notices vs. news**: `site_context` is a **`sc.SiteContext`** (a `dict` subclass, so
  `site_context['notices'|'sections'|'attachments'|'site']` access is unchanged) constructed once
  per processed site, as far up the per-site loop as possible (after the portal/not-requested/
  Sandbox skips). Add to it via its methods — `site_context.add_notice(notice)` /
  `.add_notices(list)` (builders: `wp_error`/`drush_error`/`check_wordpress_plugin`/
  `check_drupal_module`) / `.add_section(...)` / `.add_attachment(...)` — this is the
  **canonical** path; the old module-level `sc.add_notice`/`add_notices` free functions were
  removed. `add_notice` takes a **`Notice`** and **nothing else** — a frozen dataclass
  (`severity`/`code`/`html`/`short`/`text`/`icon`/`order`/`csv_extra`) from `psh/notice.py`,
  re-exported as `sc.Notice`/`sc.Severity`; anything else raises a named `TypeError`. **`Notice`
  validates both `severity` and `csv_extra` at construction** (`__post_init__` raises a named
  `TypeError` on a non-`Severity` severity — a string like `"warn"` would otherwise surface as an
  anonymous `KeyError` from the projection's icon map — and on a non-str `csv_extra` element,
  which would otherwise surface as the anonymous `sequence item N: expected str` from
  `",".join`). The six-key **render dict** (`type`/`icon`/`csv`/`short`/`message`/`text`) is the
  *storage* form in `site_context["notices"]` — what `email_template.{html,txt}`,
  `sort_notices_and_subject` and `RunState.record_site_notices` read — but producers no longer
  build one: **`SiteContext.notice_to_dict(notice)`** is the one projection that makes it, filling
  `icon` from `severity`, `text` via `html2text`, and the `csv` row as `site,code,*csv_extra`.
  **The site name comes from the `SiteContext`, never from the producer**, so it cannot be
  mismatched; `csv_extra` is the tuple of csv fields that follow `site,code` (e.g.
  `turned-off,{name}` → `csv_extra=(name,)`), and because the projection does not coerce, a
  format spec like `f"{savings:.2f}"`/`str(n)` stays visible at the producer. `order`
  (`prepend`/`first` → front) is honored by `add_notice` and is *not* stored in the render dict.

  **Notice-code registration.** `code` is enforced unique at import time by `psh.notice.registry`
  (`NoticeRegistry.register`, raising `DuplicateNoticeCodeError` on a repeat — the bug class that
  once let two independent notices share the `php-eol`/`annual-bill` codes). Every producing
  module registers each code once at import as a module-level `NOTICE_* = <register-call>`
  constant, and constructs notices as `Notice(code=NOTICE_*, …)` — so the code constructed cannot
  drift from the code registered. **`psh/` modules register through the bare `registry`**
  (`from psh.notice import registry`) — they cannot use the `sc.registry` façade, because
  `script_context` imports back through the same graph. **`check/` and `plugin/` modules register
  through `sc.registry`.** The **one sanctioned exception** is
  `check/pantheon_cdn_change/notices.py`, which imports `psh.notice` directly (bare `registry`) to
  keep its purity — `test_notices_module_is_pure` pins its imported-module set to exactly
  `{"html"}`, which `import script_context as sc` would blow past (276 transitive modules vs. 18
  stdlib). Two tests enforce all this: `tests/integration/test_notice_roster.py` pins the 36-code
  roster (registry vs. roster), and `tests/integration/test_notice_registration.py` walks the AST
  of `psh/` + `check/` + `plugin/` and fails a *named* offender when any `Notice(...)`/
  `sc.Notice(...)` passes a `code=` that is not a module-level `NOTICE_*` constant, or any
  `NOTICE_*` is not a `registry.register(...)` result — closing the gap where a literal
  `code="whatever"` registers nothing yet passes the roster test. Registration is import-time-once,
  so `tests/conftest.py`'s autouse `reset_sc` snapshots and restores the registry around every
  test; **that works only because no producing module is executed outside a function-scoped
  fixture or test body, nor cached across tests** — cache a producing module once per session and
  its second import raises `DuplicateNoticeCodeError`.
- `add_news_item()` (still an `sc` function, still dict-based — news items are operator-authored
  config data, not code-built notices) adds an organization-wide item to `sc.news`
  (config-inline `[News.<x>]` sub-tables + `*.toml` files in `[News].folder` are both loaded by
  `load_news_items()`). Site-phase hooks receive the `SiteContext` and call these methods
  directly (see `check/umich/sitelens.py`); tests build one with `sc.SiteContext({"name": ...})`.
- **Terminus/WP/Drush wrappers**: these ten defs live in **`psh/gateway.py`**. `run_terminus()`
  is the low-level subprocess call (5-min timeout, returns `(stdout, stderr, fatal)`).
  `terminus()` wraps it for JSON with a session-expiry retry and **returns `(result, errors,
  fatal)`** (`result` is `None` on a JSON decode failure). Call sites that index into the result
  use `terminus_data(...)`, which raises the named `TerminusError` when the command was fatal or
  returned no data (org-level calls abort; per-site calls skip that site). `wp()`/`wp_eval()` and
  `drush()`/`drush_php_script()` run WordPress and Drupal commands on a `site.env` remotely (all
  return 3-tuples too); `wp_error()`/`drush_error()` build alert notices from command failures.
  Prefer these wrappers over calling `terminus` directly.
  `run_terminus`/`terminus`/`wp`/`wp_eval`/`drush`/`drush_php_script` return a **`GatewayResult`**
  NamedTuple `(result, errors, fatal)` — still a `tuple` subclass, so positional unpacking and
  `== (a, b, c)` comparisons are unchanged.
- **Email/SMTP config**: sender identity and the mail server come from the optional
  `[Email]`/`[SMTP]` config sections (`from`/`reply_to`/`bcc`/`dry_run_to`/
  `dry_run_username_domain`/`msgid_domain`, `host`/`port`); when a key is absent the default is
  the original U-M literal, so U-M output is unchanged. `[SMTP]` also holds `enabled` (gates the
  send, below), `username` (default `<{env USER}`; the `sc.smtp_username()` helper resolves
  `--smtp-username` → `[SMTP].username` → `""`), and `password` (`<{secret env SMTP_PASSWORD}`).
  Keep new institution-specific behavior behind config / the `umich` packages — use the
  `umich_enabled()` helper (also exposed as `sc.umich_enabled`) to gate U-M-only checks.
- **Cloudflare auth + shared client**: the plugin builds **one** `Cloudflare` client from
  `[Cloudflare]` config (no direct-env fallback) — `api_token` if present (preferred), else
  `email` + `api_key`; missing creds while enabled → clear exit. `plugin/cloudflare/client.py`
  has `build_client()` (auth), **`pinned_client()`** (what makes "no direct-env fallback" *true*),
  and `get_client()` (**lazy** build-or-return, cached in
  `sc.plugin_context['plugin.cloudflare']['client']`).
  **The pin is load-bearing, and the docstring was false before it existed.** Measured on
  cloudflare 5.4.0: the SDK back-fills every credential left `None` from the environment, and
  ambient values reach the wire by **four** routes — `auth_headers` returns the *first* of
  email → key → token → user_service_key (so an ambient `CLOUDFLARE_EMAIL` beats a configured
  `api_token` and the token is never sent), `default_headers` adds `X-Auth-*` independently,
  `$CLOUDFLARE_CUSTOM_HEADERS` is merged *last* and overrides both, and **`$CLOUDFLARE_BASE_URL`
  redirects every request, sending the configured credential to an arbitrary host**. That last
  one mattered most: this program runs unattended against production monthly. `pinned_client()`
  closes all four (pin `base_url`, null the unsupplied credential fields, clear
  `_custom_headers`). **NOT closed, deliberately:** httpx's `trust_env=True` leaves `$HTTPS_PROXY`
  and `$SSL_CERT_FILE` in play — closing that would break legitimate proxied deployments
  (`development/2026-07-30-platform-domain-util2/SPEC.md` §8.13). The property is asserted
  against a **real** built request in `test_plugin_cloudflare_client.py`, not against the
  attribute assignments that implement it, and each of the three pins is mutation-tested — a
  set-intersection version of that assertion silently missed the `_custom_headers` route. `__init__.py` stashes a reference to
  `get_client` in the bag (`['get_client']`); `ips.py` and `fqdns.py` call
  `sc.plugin_context['plugin.cloudflare']['get_client']()` — so they import nothing from the
  plugin (stay standalone-loadable by the tests) and there is **no hook-ordering dependency** (the
  client builds on first use, whichever hook runs first). **Cred-resolution invariant:** the
  client is built at the setup-hook stage (after pass-1 substitution, before the deferred pass),
  so Cloudflare creds must be pass-1-resolvable (nothing today defers them; only `plugin.umich`
  returns `sc.DEFER`).
- **Cloudflare proxied-FQDN fetch (`plugin/cloudflare/fqdns.py`)**: a setup hook
  (`update_and_load_proxied_fqdns`) fetches every proxied FQDN (accounts → zones →
  `dns.records.list(proxied=True)`), **writes `fqdns.json` atomically** (temp + `os.replace`,
  replacing a symlink with a plain file), and loads it into
  `sc.plugin_context['plugin.cloudflare']['proxied_fqdns']`. The per-site loop does a keys-only
  membership test (`hostname not in …`), so `fqdns.json` values are `{zone_id, origins}` objects
  (old bare-array files still load). **`origins` is consumed** by `check/pantheon_cdn_change` (it
  walks each origin's CNAME chain looking for the legacy Pantheon GCDN); `zone_id` remains stored
  but unread. Refresh rules (see `docs/cloudflare-fqdns.md`): update if the file is missing, or
  stale (>24h) + processing multiple sites + not `--no-update-cloudflare-fqdns`, or
  `--update-cloudflare-fqdns` (forces; requires `[Cloudflare]` enabled). `--update` /
  `--import-older-metrics` / `--create-tables` skip the refresh entirely (they never consume
  fqdns — the missing-file rule does not override this). Any fetch error is fatal; **zero zones is
  fatal** (likely a DNS:Read scope problem), while zero FQDNs only warns.
- **`cloudflare_enabled` is read from config**, `bool(sc.config.get("Cloudflare",
  {}).get("enabled"))` (`.get` chains — a missing `[Cloudflare]` section must not `KeyError`),
  **not** `"plugin.cloudflare" in sc.plugin` (which is always True — every plugin package is
  imported regardless of `enabled`, so that test would always pass).
- **Cloudflare cache checks (`check/cloudflare/`, opt-in)**: gated on `[Cloudflare].enabled` AND
  `[Cloudflare.cachecheck].enabled` (default false); when enabled, `account_id`+`list_name` are
  required (fatal if missing) and all cachecheck values must be **pass-1-resolvable** (the egress
  setup hook runs before the deferred substitution pass). Registers the egress-IP allowlist test
  at `setup` (early-returns on `--update`/`--import-older-metrics`/`--create-tables`/
  `--allow-any-source-ip` — the create-tables return is REQUIRED, setup hooks run on that path;
  verifies BOTH IP families via the shared lazy SDK client + `client.rules.lists.*`, needs the
  "Account Filter Lists: Read" scope, and the list must cover every family the host egresses on)
  and the per-FQDN cache checks at `site_post_dns` (consumes `fqdns_behind_cloudflare`; RNG
  seeded `{site}:{report_date}` so re-runs test identical URLs; MISS-retry 2s/2s protocol only
  when headers say cacheable; cross-FQDN redirects drop the URL with NO result item; invalid cert
  → item then insecure re-fetch continues the checks). Notice language has U-M and generic
  variants selected via `sc.umich_enabled()`; consolidation merges FQDNs whose findings differ
  only by URL; every notice's csv key is `cloudflare-cache`. See `docs/cloudflare-cachecheck.md`
  and `development/2026-07-08-cloudflare-cache-configuration/`.
- **Resuming an interrupted `--all` run**: `--resume-from SITE_NAME` filters the already-sorted
  site-name list **before** the loop (via the pure helper `sites_from_resume_point`, which raises
  `ResumeSiteNotFoundError` on an unknown name → fatal), so skipped-over sites do zero work. It
  requires `--all` and is mutually exclusive with `--create-tables` (guards placed **before** the
  create-tables/sites-or-all chain in `main()`, or that chain shadows the precise messages). On a
  resumed run the two post-loop summary artifacts accumulate instead of truncating: `-notices.csv`
  opens in `"a"` mode and `-results.json` goes through `merge_prior_results()` (new wins on key
  collision; missing/malformed prior file → warn + this run's results only). See
  `docs/resuming-interrupted-runs.md`.
- **Rendering**: the Jinja render + PHP inline is `psh.render.render_report`. Templates
  `email_template.html` and `email_template.txt` are rendered per site into
  `build/<site>.{html,txt}`. The HTML is then run through `inline-styles.php` (PHP Emogrifier via
  `vendor/`) to inline CSS for email clients → `build/<site>-inline.html`, and a regex pass then
  appends `!important` to every inlined CSS declaration → `build/<site>-inline2.html`, **which is
  the HTML actually attached** (not `-inline.html`) — `render_report` returns that `-inline2`
  body. Charts (traffic surge bars, SiteLens gauges) are generated with matplotlib and attached
  as inline images (`make_msgid` CIDs) — the traffic chart via `psh.charts.build_chart`, the
  SiteLens gauges in `check/umich/sitelens.py`. The MIME `EmailMessage` is assembled by
  `psh.mail.assemble_message`, which also writes `build/<site>.eml`. **The SMTP send
  (`smtp_login()`/`send_message`) is live but gated on `[SMTP].enabled`**: when disabled (or
  `[SMTP]` absent) only the `.eml` files are written; when enabled the tool sends (to test
  addresses unless `--for-real`). `--for-real` selects the real `To`/`Bcc` recipients vs. the
  dry-run addressing; on a dry run the operator copy (`{username}@{domain}`) is only added to
  `To:` when a username is resolvable.

### Database

SQLAlchemy declarative models `PantheonTraffic` and `PantheonOverageProtection` live in
**`psh/db.py`**. Backend is chosen by the `[Database]` TOML section: `type` is `sqlite` or
`mysql` (anything else exits). Both `type` and `name` are read **unconditionally** — a
`[Database]` section without them is a `KeyError`, not a default; the `sqlite`/`database.db`
"default" lives in the sample config, not the code. `--create-tables` creates the schema; new
traffic rows are inserted while existing ones are skipped, not updated (`ON CONFLICT DO NOTHING`
on sqlite via the `sqlite_insert` import, `INSERT IGNORE` on mysql).

**Connection resilience.** The DB is remote (RDS) and the path crosses NAT/firewall middleboxes
that reap idle flows, so the engine sets `pool_pre_ping=True` / `pool_recycle=1800` (MySQL only;
sqlite kwargs stay `{}`) and the sessionmaker sets `expire_on_commit=False`. Both the URL and
those kwargs come from **`db_engine_args(db_config)`** — the one engine builder, also exposed as
`sc.db_engine_args` and used by `plugin/umich/portal.py`, so every database this program opens
gets the same pool settings. The load-bearing piece is the **commit after a read-only SELECT** in
`load_traffic_rows()` and `load_overage_protection_window()`: it releases the connection before
the multi-minute per-site gather, without which the session holds an idle in-transaction
connection that gets reaped and dies at the next query with MySQL error 2013 — **do not remove
it** (`test_load_traffic_rows_releases_the_connection` guards it). Both return plain data
(`TrafficRow` / `OverageProtectionRow` NamedTuples), not ORM rows, because a rollback expires
live ORM objects and a later read would emit an unretried SELECT.
`load_overage_protection_window()` snapshots the whole report window in **one** ranged query and
hands `plan_costs()` a dict-backed `op_lookup(month)`; the cost model is therefore DB-free, where
it used to do ~91 uncached per-month `Session.get()`s (each its own committed round trip over the
WAN, and a Basic-plan site — no rows at all — missed on every one).

DB work runs through `db_retry(session, unit, what=…, site=…)`, which retries **whole idempotent
units of work** (`update_traffic_rows`, `insert_traffic_rows`, `load_traffic_rows`,
`build_traffic_table_rows` — the last passed as a `lambda` from its `main()` call site — and
`load_overage_protection_window`) and **NEVER a statement with pending writes** — a rollback
discards them, so a statement-level retry would commit a partial write set. What it retries is
decided by **`db_retryable(e)`** = `isinstance(e, OperationalError) or e.connection_invalidated`,
**not** by an exception class list: SQLAlchemy's mysqldb dialect classifies a lost connection by
error *code*, so a reaped connection can arrive as an `InterfaceError` or a
`ProgrammingError(2014)` — siblings of `OperationalError` under `DBAPIError`, not subclasses — and
what they all share is `connection_invalidated`. `OperationalError` is retried on top of that (a
deadlock or lock-wait timeout does not invalidate the connection but is worth one retry).
Anything else (an `IntegrityError`, a real `ProgrammingError` bug) propagates untouched and stays
loud. On a second failure `db_retry()` raises `DatabaseUnavailableError`.

**`main()` wraps the site loop in a single `except BaseException:`** — enumerating classes is what
let an SMTP hiccup on site 250 of 300 discard 249 sites' work — and `abort_reason(e)` classifies
it into exactly three outcomes: `"database"` (a `DatabaseUnavailableError`, or any `DBAPIError`
`db_retryable()` would have retried, raised outside a unit) → exit 1; `"interrupted"`
(`KeyboardInterrupt`) → exit 130; `"fatal"` (everything else) → `abort_run()` **re-raises the
original error after the flush**, so a `SystemExit` keeps its own code and message and anything
else keeps its traceback. There is no `except SystemExit:` clause and nothing is swallowed. On
every one of the three, `abort_run()` drops the failed site from `site_results` (it is written
mid-gather, so it would otherwise ship as a success), flushes the artifacts via `finish_run()`,
and prints a command rebuilt from `sys.argv` (`--resume-from` for `--all`; a re-run command
listing the remaining sites otherwise). **A Ctrl-C that lands after a site's report was already
sent resumes at the NEXT site** and keeps that site's results entry — resuming inclusively would
mail its owner a duplicate report.

`finish_run()` also writes the run metadata — `aborted_at`, `reason`,
`sites_completed_this_run`, `db_reconnects_healed_this_run`, `db_reconnect_failures_this_run`,
`reconnects_by_site`, `reconnect_failures_by_site`, and on a resumed/aborted run the prior run's
whole block under `previous` — to its **own** artifact, `{ymd}-run.json`. It must **never** go
back into `{ymd}-results.json`: `monthly-report.txt` reads that file with `jq to_entries`, which
enumerates every key as a site, so a metadata key there becomes a bogus site row in the
operator's monthly stats (silently: off-by-one site count, phantom empty-framework CMS bucket).
**`-results.json` is site-keyed and nothing else.** Same write gate and accumulate/truncate rules
as the other two artifacts. The two reconnect counters are **healed vs. failed** and both are
printed (`Database reconnects: N healed, M failed`): `db_retry()` counts a heal only after the
retry *returns*, and counts a failure when the retry or the pre-retry rollback dies — an
attempt-counting version reported "1 reconnect" on the run that aborted *because* nothing
reconnected, and zero on the rollback failure, the most definite connection loss there is.
**Test seam:** the counters are two fields of the run's `RunState` (`psh/lifecycle.py`), reached
as `sc.run_state.db_reconnects_by_site`/`sc.run_state.db_reconnect_failures_by_site` — a test
patches or asserts against **`sc.run_state`** (e.g. `monkeypatch.setattr(sc.run_state,
"db_reconnects_by_site", {})`), or constructs a fresh `RunState` and passes it straight to
`finish_run`/`abort_run` (the preferred idiom). There are no `sc.db_reconnect[s|_failures]_by_site`
module attributes, so a stale patch or read fails loudly (`AttributeError`), not silently —
pinned by `tests/unit/test_run_state.py`.

**Two rich gotchas, both shipped as bugs once.** (1) `sc.console` has markup enabled, so **every
`sc.console.print()` interpolating text the program did not author must `rich.markup.escape()`
it** — exception text, terminus/WP/Drush stderr, anything from the outside. Rich reads any
`[lowercase…]` fragment as a style tag and silently *deletes* it: `[parameters: (…)]` (the tail
SQLAlchemy appends to every `DBAPIError`) and `[warning]`/`[notice]` from command stderr vanish
from the very message the operator has to debug — and an unmatched `[/…]` raises `MarkupError`,
which inside `abort_run()` fires after SIGINT is ignored and before the flush, losing every
artifact that function exists to save. (2) `sc.console` is a bare `Console()`, so on a **non-tty**
— cron, `nohup`, a redirect, i.e. how every multi-hour `--all` run is actually launched — rich
falls back to **width 80 and hard-wraps**, inserting a real newline. That silently broke the
copy-pasteable resume command: bash treats the newline as a command separator, and the wrapped
first line re-parsed as a complete `--all --for-real` run **without** `--resume-from` — pasting it
re-mailed every owner who already had their report. Use **`soft_wrap=True` on every print that
emits a command meant to be copied**. Tests must reproduce the production width, not hide the bug:
`recording_console(monkeypatch, sc, width=…)` takes a `width` for exactly that (its wide default
is what made the suite blind to this).

**The e2e goldens cover neither stdout nor the artifacts**, so
`tests/integration/test_finish_run.py`, `tests/integration/test_abort_run.py`, and
`tests/e2e/test_abort_e2e.py` (which drives a DB failure through the real `main()` via the
`dbshim`) are the only cover for that code. Note `abort_run()` sets SIGINT to `SIG_IGN` so a
second Ctrl-C cannot truncate the flush — an in-process test that calls it **must**
`monkeypatch.setattr(psh.signal, "signal", …)`, or the rest of the pytest session silently
ignores Ctrl-C. **In the site loop, a site's notices are appended to `all_warnings` before the
SMTP send, not after**: a Ctrl-C in the send→append window (which includes
`smtp_connection.quit()`, a network round-trip) set `emailed=True`, advancing the resume point
past the site, and its notices then never reached `-notices.csv` on any run. See
`development/2026-07-13-db-connection-resilience/SPEC.md`.

### Configuration (`pantheon-sitehealth-emails.toml`)

The active config is a symlink to `pantheon-sitehealth-emails-config/pantheon-sitehealth-emails.toml`
(a separate private repo); `sample-pantheon-sitehealth-emails.toml` is the documented template.
Institution-specific data (plan names, traffic limits, prices, overage costs, Pantheon org id,
DB, Cloudflare/AWS toggles) lives here — the report's recommendations are driven entirely by
`[Pantheon.plan_info]` and `[Pantheon.plan_sku_to_name]`. Keep U-M-only logic out of the core
script and behind config flags / `umich` plugin+check packages so the tool stays reusable by
other institutions.

## Conventions & gotchas

- **`pantheon-sitehealth-emails.py` is a committed symlink to `pantheon-sitehealth-emails`. It is
  NOT a second copy and NOT the file to edit, and it must not be deleted.** The extension-less
  `pantheon-sitehealth-emails` is a thin (~17-line) shim that calls `psh.cli.main()`; the program
  body lives in `psh/cli.py` and the sibling `psh/` modules — normal `.py` files that CodeGraph,
  pyright, and ruff index natively (all three key off the `.py` extension). The `.py` symlink is
  what keeps those three tools seeing the extension-less **shim** itself, which they would
  otherwise be blind to. It stays tracked (not git-ignored) on purpose — a git-ignored one would
  vanish on a fresh clone.
- Generated artifacts land in `build/` (git-ignored); `database.db`, `fqdns.json`, and the
  `.eml`/`.html`/`.txt` outputs are working data, not source. `fqdns.json` is **program-generated**
  by the cloudflare plugin; it is git-ignored yet still tracked (`git ls-files` shows it) —
  `git rm --cached fqdns.json` to stop tracking it.
- Type-hint tuples like `-> (str, str, bool)` appear throughout; these are the existing
  (technically non-idiomatic) house style — follow the surrounding code.
- There is an active TODO list in `README.md` describing planned work (daily traffic alerts,
  Cloudflare/security scoring, moving capture into the portal app, better error handling).
- **`git diff -w` is not proof a re-indent was whitespace-only.** `main()`'s per-site loop builds
  notice HTML/plaintext from multi-line `f"""..."""` literals whose continuation lines
  deliberately start at column 0, not at the surrounding code's indent (grep `f"""` in the loop
  body). A mechanical re-indent of a block containing one of these — e.g. wrapping the loop in a
  `try:` — must NOT shift those interior lines: doing so adds leading whitespace to the rendered
  email, a real behavior change, and `git diff -w` hides it completely, because a line that only
  gained leading whitespace is exactly what `-w` is designed to ignore. The goldens are what would
  actually catch it. Anyone re-indenting a block here should compare ASTs/token streams, or just
  trust the goldens — not eyeball `git diff -w`.

## Testing

**`./run-tests` lints and type-checks before it tests, and gates on all of it.** It runs **two
gates** in order, each aborting on the first failure so a later gate's green never hides an
earlier gate's red (PD#1):

1. **ruff** (`pyproject.toml` `[tool.ruff.lint]`: `select = ALL` minus a justified `ignore` list,
   one merged pass). The four PD rules (`E722`, `BLE001`, `S105`, `S106`) that each mechanize a
   directive in `prompts/directives.md` (PD#2, PD#6) are members of `ALL` and run **everywhere not
   excluded**. `[tool.ruff].extend-exclude = ["development/2*"]` excludes only the dated archive
   folders (verbatim measurement artifacts); `development/finalize-session.py` sits above them and
   stays fully gated. `[tool.ruff.lint.per-file-ignores]` carries the `tests/**` idiom block
   (rules that flag legitimate test idioms — `S101`, `S105`/`S106`, `INP001`, …) plus
   `development/finalize-session.py = ["T201"]` (a CLI tool: print IS its output).
2. **pyright, standard mode** over `psh/` (`[tool.pyright]`); a missing pyright binary is a **hard
   failure**, never a silent skip (PD#1/PD#14).

`[tool.ruff]` deliberately pins **no `target-version`**: ruff infers it from `requires-python`
(`>=3.12`), and pinning it *masks* the 3.12-only PEP 701 f-string syntax the program uses. Both
tool invocations in `./run-tests` are **version-pinned** (`uvx ruff@0.15.22`, `uvx
pyright@1.1.411`) so a `uvx` cache refresh cannot silently move the bar. `.claude/hooks/ruff-check.sh`
runs **the same single merged ruff pass** at edit time (advisory, via `PostToolUse`, with
`--force-exclude` and a repo-root `cd` so an edited excluded file honors the `extend-exclude`) but
**not** pyright (edit-time latency; `./run-tests` carries the type gate). No invocation passes
`--select` — the merged config is the single source of truth.

There is a pytest harness under `tests/` (design in `development/2026-07-04-test-harness/SPEC.md`).
Run it with `./run-tests` (wrapper over pytest): `./run-tests --fast` is the offline inner loop;
`./run-tests` adds the live tier; `--llm` gives terse machine-parseable output; `--coverage`,
`--update-goldens`, and `--record` do what they say. Any other argument is passed straight through
to pytest. `--record` short-circuits to `tests/tools/record.py` and forwards **no** arguments —
for Drupal fixtures call `python tests/tools/record.py --drupal` directly. Tiers are pytest marks:
`unit`, `integration`, `e2e`, `live`, `render`, `email`, `slow`.

**When you change the program, add/adjust the appropriate tests in the same change.**

**This project is test-first**, at seams agreed in the spec before implementation. The loop is
`mattpocock-skills:tdd` — *not* `superpowers:test-driven-development`, which
`superpowers:subagent-driven-development` would otherwise default implementer subagents to;
`prompts/implementation-standards.md` carries the override and must be injected, or the default
wins silently. Two consequences worth stating here: **refactoring is not part of the red→green
loop** (it belongs to review), and where a core `main()` change has no seam above the e2e golden,
**extracting a pure helper is part of the change** — that is where `overage_blocks`, `plan_costs`,
and `sites_from_resume_point` came from. **The exhaustive carve-outs from test-first are new
goldens/snapshots and recorded fixtures**, whose expected values are necessarily derived from a
run; **an existing golden going red is a signal and is never refreshed to green.** Backfilling
tests for already-untested code is a different job with a different prompt
(`prompts/add-tests-for-change.prompt.md`).

Non-obvious things the harness relies on:

- **The script is imported, not re-parsed.** `tests/conftest.py` imports the program as `psh.cli`
  via a normal `importlib.import_module("psh.cli")` (the repo root is on `sys.path` because the
  suite runs as `python -m pytest`, cwd = repo root); the `psh` fixture exposes that module.
  `SourceFileLoader` is used only for loading individual `check/`/`plugin/` modules standalone —
  used directly in the per-module test files (e.g. `tests/integration/test_check_sitelens.py`,
  `test_plugin_aws.py`), while the `tests/helpers/checkload.py` helper (for packages with relative
  imports) uses `importlib.util.spec_from_file_location` + `exec_module`. `sc.options` is set by
  the caller, so a test sets it (the `reset_sc` autouse fixture does) before calling functions.
  `MPLBACKEND=Agg` must be set before the load (conftest does this) because `psh/charts.py`
  imports `matplotlib.pyplot` at module level (reached transitively via `psh/cli.py`).
- **Two-binding mock seams.** All Pantheon/WP/Drush I/O funnels through `run_terminus()` —
  monkeypatch it for in-process tests at **`psh.gateway.run_terminus`** (via the `gateway` conftest
  fixture), NOT `psh.run_terminus`: the wrappers live in `psh/gateway.py` and resolve
  `run_terminus` in the gateway module's namespace, so patching `psh.cli`'s imported binding would
  not intercept them (a silent test defect, PD#14). Module-singleton patches are unaffected —
  `psh.time.sleep` and `psh.subprocess.Popen` mutate shared module objects, so they apply without
  repointing. **`psh/gather.py` binds `run_terminus` in its OWN namespace** for `gather_drupal`'s
  composer dry-run, so a test exercising `gather_drupal` must patch **BOTH**
  `psh.gateway.run_terminus` AND `psh.gather.run_terminus` — the `gateway` fixture repoints only
  the former, and a gather test that patches just it makes **real** Terminus subprocess calls, a
  mock that looks installed but isn't (see `tests/integration/test_gather_drupal.py`'s docstring).
  Or use the PATH-shim fake `terminus` (`tests/shims/terminus`, record/replay) for full subprocess
  e2e. The `php inline-styles.php` CSS inliner uses **real php**. **`psh/mail.py` binds `SMTP_SSL`
  in its OWN namespace**, so a test exercising `smtp_login()` patches **`psh.mail.SMTP_SSL`**, NOT
  `psh.SMTP_SSL` — a stale patch there fails loudly with `AttributeError`, the same two-binding
  lesson (`test_email_config.py` aliases `import psh.mail as psh_mail` and patches
  `psh_mail.SMTP_SSL` while invoking `psh.smtp_login()`). **`abort_run` calls `finish_run`
  internally** (both in `psh/lifecycle.py`), so that call resolves in **`psh.lifecycle`'s**
  namespace: a test faking the flush must patch **`psh.lifecycle.finish_run`**, NOT
  `psh.finish_run` (the fake's positional signature is the `run_state` shape). The `abort_run`
  SIGINT guard is unaffected: `psh/lifecycle.py` imports the shared `signal` module object, so
  `monkeypatch.setattr(psh.signal, "signal", …)` still reaches it.
- **The suite must stay green on a sqlite-only install.** `[mysql]` is an optional extra and the
  setup line above sanctions dropping it, so a test needing a real MySQL engine
  (`tests/integration/test_db_credentials.py`, which drives `db_retry()` against a URL that really
  contains a password) must `pytest.importorskip("MySQLdb")` at module level:
  `create_engine("mysql+mysqldb://…")` imports the DBAPI eagerly, so without the guard it is a
  hard ERROR in `--fast`, not a skip.
- **Safety interlock.** `run_program()` in conftest is the only sanctioned way to run the program
  in a subprocess; it raises `ForbiddenFlagError` if `--all`/`-a`/`--for-real` appear (including
  argparse abbreviations like `--fo` and short bundles like `-av` — it fails closed), and
  `ForbiddenLiveDataError` if `--create-tables`/`--import-older-metrics` would run live or against
  a non-fixture config (a config-**path** allowlist, not a backend-type test — the production
  default DB is also sqlite). **Never bypass it.** Tests use only `its-wws-test1`/`its-wws-test2`,
  read-only.
- **Pure-helper seam.** Pure functions extracted from `main()` as module-level defs so they're
  importable as `psh.<fn>` (the `psh` fixture is the `psh.cli` module, which re-imports them) and
  unit/property tested: `overage_blocks`, `contract_year_end`, `plan_costs` (the cost model —
  DB-free via an injected `op_lookup(month)`), and `build_plan_over_time` (returns `[]` for zero
  traffic; `main()` guards the empty case and skips the plan sections) live in `psh/plans.py`.
  Also extracted: `load_news_items`, and `sites_from_resume_point`/`merge_prior_results` (the
  `--resume-from` logic, which cannot be reached through the `--all`-banned subprocess interlock
  and so is only testable in-process). `estimate_month_visits` and `build_traffic_table_rows` live
  in `psh/traffic.py`, along with `aggregate_visits_by_month(rows, start_date, end_date) ->
  tuple[dict, dict]` (`tests/unit/test_traffic_aggregation.py`), covering seeding traffic-free
  months to 0 and the last-row-wins `plan_on_day` map. The extractions are behavior-preserving
  (goldens byte-identical). **`classify_hostname_dns` is NOT one of these** — it lives in
  `psh/dns_classify.py`; import it from there.
- **DNS tests.** The `psh/dns_classify.py` engine and `check/dns/` package have their own suite:
  `tests/unit/test_dns_classify.py` (classification + transient-vs-not-in-DNS, and
  `psh.dns_classify.MalformedNameError` — `resolve()` converts dnspython's syntax errors
  (`dns.exception.SyntaxError`, `dns.name.NameTooLong`) into this named exception at the single
  DNS seam, and `classify_hostname_dns` catches it and returns `(0, 0, False)`, so a malformed
  hostname — e.g. a Pantheon domain id like `a..b`, which `fqdn_re` accepts — can never escape and
  abort the whole run), `tests/unit/test_dns_notices.py` (notice builders),
  `tests/integration/test_check_dns.py` (the `site_post_dns` hook), and
  `tests/integration/test_dns_notice_render.py` (syrupy snapshots). `check/pantheon_cdn_change/`
  has its own parallel suite: `tests/unit/test_pantheon_cdn_change_chain.py`,
  `tests/unit/test_pantheon_cdn_change_pantheon.py`,
  `tests/unit/test_pantheon_cdn_change_detect.py`, `tests/unit/test_pantheon_cdn_change_notices.py`,
  `tests/integration/test_check_pantheon_cdn_change.py` (hook/phase registration),
  `tests/integration/test_pantheon_cdn_change_notice_render.py` (syrupy snapshots, where the
  U-M-before-cutoff copy is pinned), and the 4th e2e golden (below). **`psh.dns_classify.resolve`
  is the one monkeypatchable DNS seam** — patch it (as those tests do) so nothing hits real DNS;
  route any new resolution through it.
- **check/pantheon tests.** The `check/pantheon/` package (frozen/live-env/updates/php-eol) has
  its own suite: `tests/unit/test_php_eol_notice.py` (the `build_php_eol_notice` builder, at its
  `check/pantheon/php_eol.py` home — the lexicographic-compare and missing-`php_version` fixes are
  pinned here), `tests/integration/test_check_pantheon_init.py` (config gating + the four hooks'
  phase/`consumes`/`produces` declarations; default-true proof),
  `tests/integration/test_check_pantheon.py` (the four hook seams via `sc.SiteContext` and the
  `gateway` fixture, incl. the singular-`short` interpolation pin), and
  `tests/integration/test_pantheon_notice_render.py` (syrupy snapshots of all seven notice
  variants). The `envs` contract key and `stuff_envs_contract` are pinned by
  `tests/unit/test_contract_registry.py`, and `tests/integration/test_hook_dag.py` proves the
  `check.pantheon` declarations validate.
- **psh/gather + check/wordpress + U-M WP-check tests.** All integration tier:
  `tests/integration/test_gather_wordpress.py` (`psh.gather` via the `gateway` fixture +
  `sc.SiteContext` — happy path, fatal version/plugin/theme fetches, last-wins smell, the
  network-URL variants; its header note records why the defensive `"unknown"`/`None` branches are
  unreachable through the gateway seam), `tests/integration/test_check_wordpress_init.py` (config
  gating + the four hooks' declarations in order; default-true proof),
  `tests/integration/test_check_wordpress.py` (the four hook seams, incl. the ocp
  no-matching-plugin no-call pin, the `wp_smell`-rebind pins, and the precedence pin — theme
  stderr then OCP stderr with clean favicon → OCP wins), `tests/integration/test_check_umich_wp.py`
  (oidc / hummingbird seams, the `site['name']` print pin, and the gating-change proof:
  umich-disabled registers neither), and `tests/integration/test_wordpress_notice_render.py` +
  `tests/integration/test_umich_wp_notice_render.py` (syrupy snapshots of every relocated notice
  body). The four `site_post_gather` contract keys and the extended `stuff_gather_contract`
  (same-`add_on_updates`-object included) are pinned by `tests/unit/test_contract_registry.py`;
  `test_documented_sc_facade_names_exist` pins `sc.wp_eval`/`sc.wp_error`.
- **psh/gather Drupal half + check/drupal + check/addon_updates + Drupal-UA tests.** Integration
  tier: `tests/integration/test_gather_drupal.py` (`psh.gather.gather_drupal` via the `gateway`
  fixture + `sc.SiteContext` — D8+ composer-audit + D7 pm:updatestatus happy paths, the fatal
  core-status/pm:list/pm:updatestatus/composer-update notices, the last-wins smells, and the pin
  that a D7 `"type": "module"` row renders `module`; its docstring records the two-binding
  `run_terminus` seam trap — patch BOTH `psh.gateway.run_terminus` and `psh.gather.run_terminus`),
  `test_check_drupal_init.py`/`test_check_drupal.py` (config gating + declarations in order; the
  multisite gate/probe/key-absence + `multisite-check` notice, papc/d7_eol delegation),
  `test_check_addon_updates_init.py`/`test_check_addon_updates.py` (gating + the `updates-addons`
  table incl. the same-object read), `test_check_umich_drupal_ua.py` (the UA seams, the
  `drush_smell`-rebind pin, and the gating-change proof: umich-disabled registers no `drupal_ua`),
  and the syrupy render files `test_drupal_notice_render.py` / `test_addon_updates_notice_render.py`
  / `test_umich_drupal_ua_notice_render.py` / `test_smell_notice_render.py` (the last pins the
  composer literal at column 0). Unit tier: `tests/unit/test_no_primary_domain_notice.py` (the
  pure helper), and `tests/unit/test_smell_notices.py` (the column-0 assertions).
  `test_hook_dag.py`'s `ALL_PACKAGES` covers every package; `test_documented_sc_facade_names_exist`
  pins `sc.drush_php_script`/`sc.drush_error`.
- **psh/render + psh/mail + annual-billing tests.** Integration tier:
  `tests/integration/test_render_report.py` (the `render_report` I/O contract at its seam in a tmp
  workdir with the real templates + **real php** — `pytest.skip("php not on PATH")` when php is
  absent; incl. the non-vacuous `!important`-pass assertion using a retained `@media` block),
  `tests/integration/test_mail_recipients.py` (`psh.mail.resolve_recipients` via the `gateway`
  fixture + `recording_console` — the generic `None`-return, the U-M special cases),
  `tests/integration/test_check_umich_annual_billing.py` (the hook's gating/window
  boundaries/produced key/declarations via `checkload.py` + `sc.SiteContext`; the
  umich-disabled-registers-nothing symmetry pin), and
  `tests/integration/test_sort_notices_and_subject.py` (the pure `sort_notices_and_subject` helper
  — subject override + front order, and the non-mutation-of-`site_context["notices"]` pin). Unit
  tier: `tests/unit/test_annual_billing_notices.py`. `test_email_config.py` uses the
  `psh.mail.SMTP_SSL` seam; `test_documented_sc_facade_names_exist` pins `sc.contract_year_end`;
  the billing hook-produced key is NOT registry-owned, so it is not in
  `test_contract_registry.py`; `test_hook_dag.py` proves the `check.umich` hooks validate.
- **Notice-model tests.** `tests/unit/test_notice.py` covers `Notice.__post_init__`'s two named
  `TypeError`s (non-`Severity` severity; non-str `csv_extra` element) and
  `psh.gather.check_drupal_module` covers the `Severity(level)` named `ValueError`.
  `tests/integration/test_notice_roster.py` pins the 36-code roster and
  `tests/integration/test_notice_registration.py` enforces the registration rule by AST (see
  § Notices vs. news).
- **Shared test infrastructure (`tests/helpers/`).** `dnsfake.py` has the fake
  `psh.dns_classify.resolve` (`make_resolver`/`patch_resolve`, zone dict keyed `(name, rrtype)`)
  and `recording_console` (a `record=True` Console read back with `export_text()` — not `capsys`,
  which wraps at width 80 and breaks substring assertions as messages grow). `checkload.py` loads a
  `check/` package (or one module of it) standalone via a probe package registered in
  `sys.modules`, for packages using relative imports. Both take pytest's `request` (not
  `monkeypatch`) to register their cleanup: `monkeypatch.delitem(..., raising=False)` on a key that
  does not exist yet records no undo entry, so a package created later by `from . import chain`
  would leak into the next test's `sys.modules` — these purge by module-name prefix instead.
  `recording_console` also takes a **`width=`** — use it to reproduce production's 80-column
  non-tty console (see the rich wrap gotcha under Database).
- **Subprocess shims: ONE `sitecustomize`, in `tests/shims/pyshim/` (`conftest.PYSHIM_DIR`).**
  `run_program()` launches the real program in a subprocess, so an in-process `monkeypatch` cannot
  reach it; putting that directory on `PYTHONPATH` makes Python auto-import `sitecustomize` at
  interpreter startup, before the program imports anything. `site.py` imports **exactly one**
  module by that name (whichever dir wins on `sys.path`), so the shims are **modules inside**
  pyshim, each self-activating from its own env var and imported by the single `sitecustomize.py`
  — `dnsshim.py` (`DNS_SHIM_ZONE`, a JSON zone file; replaces `dns.resolver.resolve`; the 4th e2e
  golden needs it) and `dbshim.py` (`DB_SHIM_FAIL`; patches `sqlalchemy.orm.Session.get` to raise
  `OperationalError`, simulating MySQL 2013 inside whichever `db_retry()` unit calls it first — in
  practice `update_traffic_rows()`'s `session.merge()`, since `Session._merge()` calls `get()`
  internally). **Add a new shim as another module here, never as a second shim directory**: two
  `sitecustomize.py` files means one silently never runs — no error, no warning — and an e2e test
  whose assertions are `not in`-shaped then passes green against a run that did nothing.
  `tests/integration/test_shim_composability.py` fails if anyone reintroduces that shape (and
  proves both shims can be active at once). With neither env var set the directory is inert, which
  matters because `PYTHONPATH` is inherited by the PATH-based fake `terminus` (a Python script
  too). `tests/e2e/test_abort_e2e.py` is the only test that drives the DB shim through the real
  subprocess `main()`; it is not one of the byte-golden e2e tests below (no snapshot — it asserts
  exit code, stdout content, and the printed re-run command).
- **Offline e2e determinism.** The shim-backed run uses `tests/fixtures/config/minimal.toml`,
  seeded traffic, `--date 2026-03-31` (a mid-year date avoids the U-M contract-year-end path), and
  a `domain:list` fixture reduced to the platform domain (so no live DNS). Golden snapshots
  normalize the volatile `make_msgid` CIDs; refresh with `./run-tests --update-goldens`. There are
  **four** goldens: WordPress (`its-wws-test1`, fixtures in `tests/fixtures/terminus/`), Drupal
  (`its-wws-test2`, `tests/fixtures/terminus-drupal/`, selected via `run_program(fixtures_dir=…)`),
  a **non-U-M** golden (`test_golden_nonumich.py`, `minimal-nonumich.toml` with no `[UMich]`
  section + generic `[Email]`) that proves the config-driven email headers/msgid and that the
  U-M-guarded doc-URL checks don't appear for a non-U-M run, and the **Pantheon CDN-change** golden
  (`tests/e2e/test_golden_cdn_change.py`, `tests/fixtures/terminus-cdnchange/`, DNS shimmed via
  the `dnsshim` in `tests/shims/pyshim`) driving `check/pantheon_cdn_change` through the real
  `main()`. It has two deliberate scope limits, both asserted in the test: it covers only the
  public-DNS detection source (`[Cloudflare]` stays disabled, since enabling it would make a setup
  hook call the live Cloudflare API), and it pins the **generic** notice copy (`minimal.toml` has
  no `[UMich]` section) — the U-M copy is pinned instead by
  `tests/integration/__snapshots__/test_pantheon_cdn_change_notice_render.ambr`. **Its fixtures are
  hand-maintained**: `--record` refreshes only `terminus/` and `terminus-drupal/`, so
  `terminus-cdnchange/` will silently freeze at today's Pantheon JSON shape — see the README in
  that directory. The `.eml` identity headers have no byte golden (the `Date:` is volatile) —
  `test_eml_headers.py` asserts them explicitly. Refresh WordPress fixtures with `./run-tests
  --record`, Drupal with `python tests/tools/record.py --drupal` (both trim the org list to the
  one test site and scrub team emails).
- **`tests/conftest.py`'s `_CWD_ASSETS`** must include `check` and `plugin` (symlinked into the
  isolated e2e working directory alongside the template/PHP assets): `find_modules()` walks
  `check/`/`plugin/` **CWD-relative**, and the e2e workdir is a fresh temp directory — before this
  was fixed, **no e2e golden had ever loaded a single check or plugin package**, so every offline
  e2e run was silently testing a program with every check disabled. Anyone editing
  `make_workdir()` needs to preserve this or the e2e tier stops testing anything the check/plugin
  system does.
- **The offline golden only reaches the ≤4-month "not enough data" state** (its recorded metrics
  fall after the March report date), so the extracted `plan_costs` cost model is exercised
  end-to-end by `tests/e2e/test_recommendation_e2e.py` (seeds >4 in-window months) plus its
  unit/property tests — not by the golden. The render tier vendors axe-core locally
  (`tests/vendor/axe.min.js`) so it stays offline.
- **The reusable (non-UMich) path is only partly de-U-M-ified.** Bugs hide here because production
  always runs with the UMich plugin enabled, so the non-U-M golden is the only guard, and **it
  does NOT assert "no umich.edu anywhere"** — new leakage would ship green. **Still hardcoded U-M**
  in core (not yet relocated to the `umich` packages): the branding in `email_template.html`
  (its.umich.edu URLs, `webmaster@umich.edu`, `node/4705`). Also **hardcoded U-M but living in the
  generic check packages** (un-gated U-M links that moved verbatim when the checks relocated — the
  packages are generic because the platform checks belong there; de-U-M-ifying them is
  post-campaign work): in `check/pantheon/` the `frozen`, `no-live-env-but-paid-plan`, and
  `updates-*` notice bodies (its.umich.edu / procurement links), in `check/wordpress/` the
  `no-favicon` notice body (its.umich.edu documentation links), and in `check/addon_updates/` the
  `updates-addons` notice body (its.umich.edu support link). Keep institution-specific logic behind
  config flags / the `umich` plugin+check packages.
- **Cache-check tests.** The `check/cloudflare/` modules are loaded standalone (SourceFileLoader;
  for modules with relative imports, a probe package with `__path__`/`submodule_search_locations`
  is registered in `sys.modules` first — see `test_check_cloudflare_init.py`). Unit tier:
  `test_cachecheck_headers.py` / `test_cachecheck_pages.py` / `test_cachecheck_consolidation.py`
  (pure battery/extraction/consolidation + Hypothesis). Integration tier: `test_hooks_phases.py`
  (phase registry), `test_check_cloudflare_init.py` (gating/import guard),
  `test_check_cloudflare_egress.py` (`egress.probe` seam + fake lists client),
  `test_check_cloudflare_cache.py` (`httpseam.fetch`/`sleep` seams, canned FetchResults),
  `test_check_umich_cloudflare_cms.py` (relocation), and `test_cachecheck_notice_render.py` (syrupy
  snapshots of the notice HTML/plaintext — refresh with `--update-goldens`). The e2e goldens keep
  `[Cloudflare].enabled=false`, so the cache check must never alter them.

## Reusable prompts (`prompts/`)

`prompts/` holds the repo's own workflow prompts — read the relevant one before doing that kind of
work, and cite it by name rather than re-deriving the conventions.

**`prompts/directives.md` is the Spine** and comes first: the ONE copy of the Posture, the 14
Prime Directives, the Engineering Preferences, and the spec quality bar. Every other file in
`prompts/` is a *delta* that cites directives **by number** and restates none of them. This
matters because they used to live in two files and **drifted** — PD#11 gained a `/domain-modeling`
mandate in one copy and not the other, and the adversarial reviewer read the stale one.

The deltas: `new-feature-standards.md` (how features get specced), `implementation-standards.md`
(the standards layered on `superpowers:subagent-driven-development`; the intended invocation is
"implement everything per the spec doc(s), adhering to the standards in
`prompts/implementation-standards.md`"), `debugging-standards.md` (the standards layered on
`mattpocock-skills:diagnosing-bugs` — for **runtime** failures; document defects go to
`adversarial-review.md` instead), `adversarial-review.md`, `add-tests-for-change.prompt.md`,
`refresh-fixtures.prompt.md`, and `update-claude-md.md`. Note `development/2026-07-04-test-harness/`
contains **stale copies** of two of these — `prompts/` is the source of truth.

`prompts/` holds the *standards* (the bar to hold work to); **`docs/agents/`** holds the *wiring*
the installed skills read (where issues live, which glossary to read, the triage vocabulary). See
**Agent skills** below.

### Dispatching subagents

**Standing authorization: subagent dispatch, workflows, and deep research are pre-approved for all
development work in this repo — don't ask first, just say what you're launching.** That covers the
`Agent` tool (`psh-implementer`/`psh-reviewer`, and the read-only `Explore`/`Plan` agents), the
`Workflow` tool (including "ultracode"-scale fan-outs), and deep/background research
(`mattpocock-skills:research`, web-research agents). **The harness default is the opposite** — "do
not call the Agent tool unless the user requested it", "do not use workflows or deep-research
unless the user requested it" — and this file overrides it, per the `using-superpowers` precedence
rule (user instructions beat skills, which beat default behavior). Two things it does **not**
change: (1) it authorizes the *dispatch*, not the acts a subagent performs — commits, branches,
pushes, and destructive operations still follow the rules elsewhere in this file (**Other /
General**: commit only when asked, branch only when directed), and a subagent inherits that, so
say so in the brief; (2) the agent-type rule below still binds — a code-touching `Workflow` stage
must pass `agentType: 'psh-implementer'` (reviewers `'psh-reviewer'`), because `Workflow`'s default
subagent carries none of the standards, exactly like `general-purpose`.

**`.claude/agents/psh-implementer.md` and `psh-reviewer.md`** carry the read list
(`prompts/directives.md` + `prompts/implementation-standards.md` + `CLAUDE.md` + the brief), so
the standards reach a fresh-context subagent as **configuration** rather than as prose the
controller has to remember to paste. Dispatch every code-touching subagent (implementers and
fix-subagents) as `psh-implementer` and every reviewer as `psh-reviewer`;
`superpowers:subagent-driven-development`'s template says `general-purpose`, and
`prompts/implementation-standards.md` overrides it. **A dispatch that cannot use them must stop
and say so** — falling back to `general-purpose` restores the curation problem with none of the
signal. Note `.claude/agents/` is read at **session start**: a newly added agent is not
dispatchable until the session reloads.

Every task report must cite the directives it applied **by number and with a verbatim quote**,
grep-checkable against the Spine — that is the only observable separating "read the standards"
from "didn't".

## Agent skills

**`superpowers` is the host process; `mattpocock-skills` supplies tools, not a pipeline.**
The `prompts/` standards overlays are written against `superpowers:brainstorming` and
`superpowers:subagent-driven-development` — those own the flow. Matt's `grill-with-docs` →
`to-spec` → `to-tickets` → `implement` is a *competing* pipeline for the same span: don't run it
as the host, or the overlays end up layered on a process that isn't running. Two of its skills
conflict outright with rules here — `implement` ends "commit your work to the current branch"
(**Other / General** says commit only when asked), and `to-spec` writes the spec to the issue
tracker rather than to `development/` (see **Issue tracker** below).

Matt's skills split by frontmatter into ones I can invoke and ones only you can type:

- **Model-invocable** (a `prompts/` file may cite these as instructions): `/grilling`,
  `/diagnosing-bugs`, `/tdd`, `/codebase-design`, `/domain-modeling`, `/prototype`, `/research`,
  `/resolving-merge-conflicts`.
- **User-typed only** (`disable-model-invocation: true` — a repo file telling me to use one is a
  **no-op that reads like an instruction**, so never write one): `/grill-with-docs`, `/to-spec`,
  `/to-tickets`, `/implement`, `/improve-codebase-architecture`, `/triage`, `/wayfinder`,
  `/ask-matt`.

When to reach for the user-typed ones here:

- **`/improve-codebase-architecture`** — hunting expansion opportunities. Nothing else in this
  repo does this; it's the main reason Matt's set is installed.
- **`/grill-with-docs`** — sharpening a big feature before `superpowers:brainstorming`.
- **`/triage`**, **`/wayfinder`**, **`/to-tickets`** — no current use: there's no issue inflow,
  and this is a mature codebase rather than a foggy greenfield.

Two skill names are **ambiguous** — say which you mean:

- **`/tdd`** — `mattpocock-skills:tdd` is the one this project uses (see **Testing**);
  `superpowers:test-driven-development` is a different, stricter skill and is overridden here.
- **`/code-review`** — both Claude Code and `mattpocock-skills` define it. Or use
  `prompts/adversarial-review.md`.

### Issue tracker

Specs and plans live under `development/<YYYY-MM-DD-slug>/` per `prompts/new-feature-standards.md`
— that is canonical and takes precedence. `.scratch/<feature-slug>/` holds only ephemeral ticket
files, and only if you use Matt's tracker skills. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, each label string equal to its name. See
`docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root (`docs/adr/` does not exist yet;
`/domain-modeling` creates it lazily). See `docs/agents/domain.md`.

## How this architecture came to be

The core package + self-registering `check/`/`plugin/` layout was reached by the modularization
campaign, which is **complete**. It carved the several-thousand-line single-file script into the
`psh/` package, the `check/`/`plugin/` packages, and the `main()` orchestrator, across a sequence
of increments while the four e2e goldens stayed byte-identical. The record lives in
`development/2026-07-17-modularization-campaign/`: **`CAMPAIGN.md`** (the frozen architecture,
decisions, and invariants — amendments only, per its preamble), **`LEDGER.md`** (the append-only
cross-increment history — the one home for "which increment did what"), **`BLOCKMAP.md`** (the
functional map of the original `main()`), **`CLOSING-AUDIT.md`** (the closing-question answers),
and **`RETROSPECTIVE.md`** (the goal against the measured outcome and the failure classes worth
carrying forward). This `CLAUDE.md` describes the architecture as it **is**; the increment-numbered
narrative of how it got here lives in `LEDGER.md`.

## Development archive (`development/`)

`development/` is a committed, per-feature record of how features were built with Claude — one
`YYYY-MM-DD-slug/` folder per feature holding the prompts used, the generated+hand-edited
`SPEC.md`, a scrubbed `transcript.md`, and an auto-generated `statistics.md`. It is a **historical
record, not a primary source of documentation** — don't rely on it for how the code works (that's
the code, this file, and `docs/`). See `development/README.md` for the full convention. Two rules
matter when working here: transcripts must be **scrubbed of secrets** (run the `/archive-session`
skill, which invokes `development/finalize-session.py`) before committing, and the raw session
JSONL is **never committed** (gitignored). A feature's `development/` folder is committed **in the
same commit** as the code it documents.

## Dev container

`.devcontainer/` defines a sandboxed Node/Debian image (`Dockerfile`, `devcontainer.json`,
`container-start.sh`) that pre-installs uv+Python, PHP+Composer, Terminus, AWS CLI, mise, and
Claude Code, with SSH keys under `.devcontainer/ssh/` and a Terminus token cache under
`.devcontainer/terminus/`. **The egress firewall is currently disabled** — the script is checked
in as `DISABLED_init-firewall.sh`, so don't assume network lockdown. Secret handling here is still
a work in progress (see README TODO).

## Pantheon API

The script makes use of [`terminus`](https://docs.pantheon.io/terminus) to interface with
Pantheon.  However, Pantheon also has a public API that can be used either directly by
AI tools to do their work, or in the script. A goal is replace the script's use of
terminus with the Pantheon API, but only in the cases where it makes sense (equivalent
or better functionality, no significant downsides).

**GUIDANCE FOR IMPLEMENTING NEW FUNCTIONALTY OR FEATURES**: prefer using the Pantheon
API when adding new code to the script, unless using `terminus` would be better for some
reason (examples: the API lacks necessary endpoints, it would be significantly cleaner
or significantly simpler to use `terminus`, using `terminus` would give better results,
...).

The Pantheon's API schema is available at https://api.pantheon.io/docs/swagger.json
Fetch it as necessary.

As of July 3, 2026, there is no documentation or examples on https://docs.pantheon.io/ on
how to use the Pantheon API, so some information is below.  Freely adapt what's below to
Python or any other languages/environments where you would like to use the Pantheon API.

1. Get a machine token. A machine token is already available as a part of the configuration
for `terminus`.
```bash
PANTHEON_USERNAME=$(ls -1 ~/.terminus/cache/tokens/ | head -1)
MACHINE_TOKEN=$(jq -r .token < ~/.terminus/cache/tokens/"${PANTHEON_USERNAME}")
```

2. Use the machine token to get a session token:
```bash
SESSION_TOKEN=$(curl -s -X POST -H "Content-Type: application/json" https://api.pantheon.io/v0/authorize/machine-token -d "{ \"machine_token\": \"${MACHINE_TOKEN}\", \"client\": \"curl\" }" | jq -r .session)
```

3. Use the session token to call the API endpoints you want to use.  This example uses a site name to get the site ID, then uses the site ID to get the site info:
```bash
SITE_NAME="its-wws-test1"  # real example site that can always be used for read-only operations

# Use the site name to get the site ID:
SITE_ID=$(curl -s -H "Authorization: Bearer ${SESSION_TOKEN}" "https://api.pantheon.io/v0/site-names/${SITE_NAME}" | jq -r .id)

# Use the site ID to get the site info:
curl -s -H "Authorization: Bearer ${SESSION_TOKEN}" "https://api.pantheon.io/v0/sites/${SITE_ID}" | jq .
```

## Reference material

Fetch information as needed from the websites, using the HTTP request header
`Accept: text/markdown`. Follow links on the website pages as needed.

* Pantheon documentation: https://docs.pantheon.io
* Information about using the Cloudflare API: https://developers.cloudflare.com/fundamentals/api/
* Cloudflare API documentation: https://developers.cloudflare.com/api/
* Cloudflare products and services in general: https://developers.cloudflare.com/

## Other / General
* **Before writing, reviewing, or refactoring any code in this repo, invoke the
  `andrej-karpathy-skills:karpathy-guidelines` skill and follow it.** This is not optional and
  not a judgment call — do it even when the change looks trivial. (Skip it only for purely
  conversational turns that touch no code.)
* Avoid flattery as feedback, stick to facts that matter. For example, "Got it — that's a meaningful architecture upgrade, and a good one." doesn't add anything of value. But do give me feedback about things that are not good, could be improved, or could change what decisions get made.
* Commit only when asked. Only branch if explicitly directed to do so.

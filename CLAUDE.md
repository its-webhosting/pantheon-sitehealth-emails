# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`pantheon-sitehealth-emails` is a Python CLI tool that pulls traffic and
site-health data from [Pantheon](https://pantheon.io/) hosting (via the Terminus CLI,
WP-CLI, and Drush), stores traffic history in a database, and emails each site owner a
monthly report with a plan-cost recommendation. It is used by University of Michigan ITS
Web Hosting Services and is written to be reusable by other institutions via a config file.

## Commands

The whole tool is invoked through one executable, `./pantheon-sitehealth-emails` (run it
directly; it has a `#!/usr/bin/env python` shebang and expects the venv active). It is an
18-line shim that calls `parse_args()` into `sc.options` and then `psh.cli.main()` — **the shim,
not `main()`, is what populates `sc.options`**, and `main()`'s first statement reads it, so an
alternate entry point calling `main()` alone crashes. The program body lives in the `psh` package
(`psh/cli.py` holds `main()`, the argparse pair, and the per-site pipeline; the gateway/config/
db/traffic/plans/gather/charts/render/mail/lifecycle/dns_classify layers, plus the `modules`
(hooks) and `notice` engines, are sibling `psh/` modules — see **Architecture**). There is no
Python build step (the one-time `composer install` below populates `vendor/` for the PHP CSS
inliner); for the test suite see **Testing** below.

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
./pantheon-sitehealth-emails --date 20240731 --all           # dry run: to dry_run_to, not owners
./pantheon-sitehealth-emails --date 20240731 --all --for-real # sends to site owners

./pantheon-sitehealth-emails --help
```

Key flags (the parser sets `allow_abbrev=False`, so no `--for` → `--for-real` foot-gun):
`--all` vs. an explicit `SITE` list are mutually exclusive (one is required
unless `--create-tables`); `--config`/`-c` picks the TOML file (default
`pantheon-sitehealth-emails.toml` — the default is NOT shown in `--help`, and that help text
names a `pantheon-sitehealth-emails.toml.sample` file that does not exist).
**Without `--for-real`, mail goes to `[Email].dry_run_to` (default: a hardcoded U-M address —
set it for a non-U-M install) plus `{username}@{[Email].dry_run_username_domain}` when a username
resolves; never to owners. This is the primary safety mechanism and the run's blast-radius
control; always dry-run first.** `--date`/`-d` **defaults to today** — always pass it explicitly
for a report run, or you silently report on a partial current month. `--update`
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

### Platform-domain utilities (temporary — delete after Pantheon's CDN migration)

Three scripts at the repo root, built for the Pantheon CDN migration. **Delete all three when it
is done.** Facts common to all of them:

- **Standalone and deletable.** None is part of the main program; each imports nothing from
  `psh/`/`check/`/`plugin/`, so deleting one is a `git rm` of the script, its `.py` symlink and
  its test file, plus a few config entries. Checklists:
  `development/2026-07-30-platform-domain-util2/SPEC.md` §11 (amended, glob only, by
  `…/2026-07-31-platform-domain-util3/SPEC.md` §13; the applier's six-item delta is §11 item 9 via
  `…/2026-08-03-platform-domain-util4/SPEC.md` §19; the DNS one is
  `…/2026-07-28-platform-domain-util/SPEC.md` §14, which also names **three** `pyproject.toml`
  entries — two `[tool.ruff.lint.per-file-ignores]` lines plus the `[tool.pyright].include` one —
  and a `ruff-check.sh` case arm).
- **Each has a committed `.py` symlink**, same convention as `pantheon-sitehealth-emails.py`:
  ruff, pyright and CodeGraph key off the extension and are otherwise blind to the extension-less
  real file. **Query them by symbol name, never by path.**
- **The exit-120 stream-guard class.** CPython's shutdown flush covers **both** std streams and
  turns a failure of *either* into exit 120, silently overriding whatever `main()` returned. So
  each script detaches a stream **only after a real write/flush has proven it doomed** — never
  unconditionally, which discards a buffered line and, under pytest's fd-level capture, repoints
  the session's own stream at `/dev/null`. Guards: `detach_doomed_stdout` (flush probe) and
  `report_line`→`detach_doomed_stderr` (failed-**write** probe — a flush probe is blind on
  line-buffered stderr) in `find-platform-domains-dns`; `write_json_stdout`/`report_line` in
  `find-platform-domains-cloudflare`; `write_report`/`report_line` in the applier. **Exhaustive
  exception, measured in all three:** argparse writes usage/`--help` before any guard exists and
  outside every handler, so `--help >/dev/full` and `--bogus 2>/dev/full` still exit **120**
  (declined, not overlooked — util1 SPEC §2.2). **An in-process test cannot pin this** (pytest
  never tears the interpreter down); the cover is real subprocess tests redirecting at `/dev/full`
  — never `subprocess.DEVNULL`, which accepts every write — plus `1>&-` (`sys.stdout` becomes
  **None**, where `print()` silently does nothing) and one for a doomed stdout first hit *inside*
  the summary flush.
- **Three independent environment-pin copies, and they are no longer identical** — an SDK upgrade
  must check all three separately. They are `plugin/cloudflare/client.py`'s **`pinned_client()`**
  (NOT the `build_client()` in that same file, which is only the config reader) and the
  `build_client()` in each of the two Cloudflare utilities. See **Cloudflare auth + shared
  client** under *Architecture* for the one full description of the four ambient-environment
  routes they close. Divergences: the applier also pins `max_retries=0` and nulls a credential on
  `creds.get(field) is None`, while `find-platform-domains-cloudflare` deliberately stays on
  `field not in creds` (read-only, its caller guards — util4 SPEC §17). **Only the applier
  writes**, so there `$CLOUDFLARE_BASE_URL` is a credential-disclosure **plus**
  attacker-aimed-rewrite risk, not just a disclosure risk.

#### `find-platform-domains-dns`

Lists every custom domain in the organization whose DNS still reaches a Pantheon platform domain
(`*.pantheonsite.io`) by CNAME, as CSV on stdout:
`site_name,site_env,custom_domain,dns_record,platform_domain` — that line is also written as a
**header row** and flushed before the first site is swept, so a hit-free sweep still names its
columns and a doomed stdout aborts at second zero instead of at the first hit. `dns_record` is the
FQDN owning the hitting CNAME record, which is what a downstream rewriter must change. Operator
messages and a `sites=… indeterminate=…` summary go to stderr. **Exit 0** = clean sweep, **1** =
completed with indeterminates, **2** = could not complete, **130** = interrupted.

There is no `--resume-from`: an aborted sweep prints the last site it completed and the **names**
of every site not yet reached, as a paste-able re-run command **rebuilt from the argv the dead run
received** (so `-c CONFIG` and `-v` survive — dropping `-c` handed the operator a command reading a
different config file). Resuming re-sweeps the interrupted site, so appending to the same CSV
duplicates that site's rows and adds a second header. `-c` is read **only** on the
whole-organization path: a `SITE`-argument sweep never uses `[Pantheon].org_id` and does not
require the file to exist. It uses the Pantheon API (machine token from
`$PANTHEON_MACHINE_TOKEN` or `~/.terminus/cache/tokens/`); **the site-list cursor can silently
return page 1 again instead of the next page**, which the script detects and exits 2 on rather
than sweeping a truncated site list. Its DNS walk is a **copy** of
`check/pantheon_cdn_change/chain.py` plus `psh/dns_classify.py`'s resolver seam — copied, not
imported. **Those two files are live main-program code and stay.**

```bash
./find-platform-domains-dns its-wws-test1     # one site
./find-platform-domains-dns > domains.csv     # the whole org, ~38 minutes
```

#### `find-platform-domains-cloudflare`

Writes every Cloudflare DNS **CNAME whose target ends in `.pantheonsite.io`** as an inventory,
plus the batch calls that would rewrite each one to the addresses its target resolves to and the
batch calls that would undo that rewrite. It is the Cloudflare-side counterpart to
`find-platform-domains-dns`: that one reads public DNS and is blind to a proxied record's target;
`fqdns.json` is built with `proxied=True` and is blind to a DNS-only record. Considers **all**
records in **all** zones of every account the credentials can see, unless **zone names are given
as positional arguments**. Legacy `*.gotpantheon.com` targets are out of scope. Full spec:
`development/2026-07-31-platform-domain-util3/SPEC.md`. **This utility NEVER calls the Cloudflare
API to write anything.**

**A subset run (naming `ZONE`s) narrows the sweep but not the hazard.** The account and zone
*lists* are still read in full; only the record fetch is skipped for an unselected zone.
**Zone matching is exact** on `normalize()` (case and a trailing dot ignored); a name matching no
zone is **fatal (exit 2) and every miss is named** — a typo yielding a short sweep is the
under-reporting failure the design refuses to have. A subset **cannot see a cross-zone duplicate**
in an unselected zone, so an entry can look unambiguous when it is not — one more reason a rewrite
is driven from a full sweep. A subset written with `-o` is byte-shape-identical to a full sweep, so
it emits a loud `ATTENTION: … covers N of M zones … MUST NOT be used as the baseline for a
rewrite`; the redirect form (`… engin.umich.edu > file`) is invisible to the program and cannot be
caught at all.

**`-o/--output-basename BASENAME` writes four files; without it, only the inventory goes to
stdout.** A `.` anywhere in BASENAME's **final path component** is fatal (directory components may
contain dots — `out/v1.2/engin-zone` is fine, `engin-zone.json` is not); the old `-o PATH` form is
gone, so the muscle-memory `-o platform-domains-cloudflare.json` invocation is now a startup error
naming the mistake. Before the first Cloudflare API call the parent directory is probed for
writability, so an unwritable destination is caught at second zero, not after the ~2-minute sweep.

| File | Contents |
|---|---|
| `<basename>.json` (or stdout) | The **inventory**: every non-ambiguous platform CNAME, keyed by normalized FQDN |
| `<basename>-plan.json` | The **forward rewrite**: one Cloudflare batch call per FQDN, platform CNAME → resolved A/AAAA |
| `<basename>-revert.json` | The **reverse** of that same batch call, built from the swept CNAME |
| `<basename>-excluded.json` | Every FQDN that got **no** plan/revert entry, with a reason code and detail |

Resolution, classification and exclusion run in **both** modes, so the inventory is byte-identical
between them and only its destination differs. Every run resolves each entry's target for A and
AAAA, following CNAME chains, through the one DNS seam `resolve()`; a `Timeout`/`NoNameservers` is
retried once before being treated as indeterminate.

**Two traps when comparing the inventory to `fqdns.json`:** that file keys by the **raw**
`record.name` (normalize both sides, or you invent phantom entries), and its `origins` means
something **wider** — every proxied record's content at that name, IP addresses included — where
this file's holds only matching platform-CNAME targets. `settings` is `.model_dump()`ed (a
pydantic model, otherwise unserializable). The inventory is **produced in full on every run**,
whatever the age of anything on disk; a run that matches nothing emits `{}` loudly rather than
leaving a stale file. It drives a *destructive* rewrite, so **regenerate the baseline immediately
before any rewrite** — the inventory's mtime is its only freshness signal (plan/revert/excluded
instead carry a `generated.at` timestamp, SPEC §5.5, and `zones_swept`/`zones_total`).

Entry shape: `{name, zone_id, zone_name, origins, record_id, proxied, ttl, comment, tags,
settings, resolved_a, resolved_aaaa}`, every scalar first-record-wins. `name` is the **raw**
`record.name` (the JSON key is `normalize()`d, and a batch POST's `name` must be exactly what
Cloudflare holds, Punycode included). **`resolved_a`/`resolved_aaaa` are `[]` for a definitive
absence (NXDOMAIN/NoAnswer) and `null` for an indeterminate lookup** — collapsing the two would
tell an operator a target has no addresses when the run never established that. **`origins` always
has exactly one element**: a second match makes the FQDN ambiguous and R4.1 removes it from the
inventory outright, so `sole_origin()` raises `InvariantError` if a multi-origin entry ever reaches
a body builder. Do not write an applier loop over `origins` expecting more than one, and do not
read the inventory as able to express ambiguity — it deliberately cannot. **Ambiguous FQDNs** (more
than one platform CNAME for the same name, in one zone or across two) are **omitted from the
inventory entirely, in both modes**; `-excluded.json` is where their `origins`/`zone_ids`/
`record_ids` live.

**`delete_match` lives OUTSIDE `body` in every plan and revert entry.** Cloudflare's batch
`deletes` items are exactly `{"id": …}` — there is no name/type/content delete form — and a plan's
`posts` mint ids that do not exist until the plan is applied, so the ids to delete on a revert (or
a re-applied plan) cannot be known until an applier resolves `delete_match` against the zone's
records at apply time. Keeping it outside `body` means `body` alone is always a real, postable
batch body and can never be mistaken for a complete request.

**Eight reason codes, in the order they are checked**: `ambiguous-multiple-origins`,
`ambiguous-multiple-zones`, `unknown-proxy-status`, `resolution-failed`, `no-a`,
`platform-a-out-of-range`, `no-aaaa`, `platform-aaaa-out-of-range`. **Only the two ambiguous codes
also remove the FQDN from the inventory**; the other six leave it in the inventory but out of the
plan and revert. **`resolution-failed` MUST be tested before `no-a`**: an indeterminate lookup is
`null`, not `[]`, and a `not resolved_a` test cannot tell the two apart. Every exclusion prints an
unconditional (never `-v`-gated) stderr `ATTENTION:` line naming the FQDN, code and detail.

**Exit 0** = nothing excluded, **1** = completed with exclusions, **2** = could not complete,
**130** = interrupted. Exit 1 is only trustworthy because `main()` ends with a last line of defence
(`except SystemExit: raise` / `except BaseException` → named message, exit 2): CPython exits 1 on
**any** uncaught traceback, so without it a crashed run and a healthy run with exclusions are
indistinguishable to a `case $?`. The only `return 1` in the program is the exclusion branch.

**Pagination is the subtle part.** All three list endpoints paginate by page *number*, so rows
shifting between fetches — routine in a zone being actively written — return the same record twice
while stepping over another. So every list is **de-duplicated by record id** (a duplicate reaching
the fold would append one origin twice and raise a *false* duplicate-name warning), and the
completeness check compares the **unique** count against `total_count` — a raw item count failed
both ways, once as a false "truncated" abort and once as a false *pass*. A shortfall triggers one
unioned re-read and is then a **loud warning, not an abort**: a paginated walk of a
continuously-written zone may never be exactly complete, and aborting meant the utility produced
nothing at all. The run reports `Completeness cross-check: N of M paginated lists verified
complete, X short, Y unverifiable`. stdout carries the JSON result (or nothing, with `-o`); every
operator message goes to stderr, and error text **never** includes an API response body.

Credentials come from `[Cloudflare]` in the same TOML the main program reads, via a **copied**
resolver handling only the `<{env NAME}` / `<{secret env NAME}` forms; any other substitution, and
any non-string value, is a named error rather than a silent passthrough. `enabled` is not consulted.

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

#### `apply-platform-domains-cloudflare`

Reads the **one** plan-or-revert file the sibling writes and performs the Cloudflare DNS batch
calls it describes, or — by default — reports exactly what it would do and changes nothing. Full
spec: `development/2026-08-03-platform-domain-util4/SPEC.md` (it implements util3 SPEC §5.4, whose
per-entry tolerance it deliberately **supersedes** — see below).

**It takes exactly one file: a `<basename>-plan.json` or `<basename>-revert.json`.** Not the
inventory (`<basename>.json` — this script never reads it), not both directions, not a
config-driven set. An `-excluded.json` is **refused by name**: it carries no `body` at all
(`generated.direction` is `"excluded"`), and the file contract's check 2 names that explicitly
rather than failing on a missing key several checks later.

**Three passes, strictly ordered, no interleaving: validate → report → apply.** Pass 1 lists each
selected entry's live records (read-only) and classifies it. If **any** selected entry is invalid,
the run reports every invalid one and exits 2 having written nothing — **the whole file**, not just
the bad entries. Pass 2 (the report) runs **identically in both modes**, from the same data pass 1
produced, so a dry run is a rehearsal of the real run rather than a second implementation of it.
Pass 3 runs only with `--for-real`, processes entries in **sorted key order** (never the file's
insertion order), and stops at the **first** failure — it never reverts what it already applied and
never continues to the remaining entries. This is the **all-or-nothing property**.

**Seven verdicts; two are valid.** `ready` (records match what's meant to be deleted — applied) and
`already-applied` (records already match the target state — skipped, reported, counted, giving exit
1). `record-ambiguous`, `partially-applied`, `unexpected-records`, `records-missing` and
`proxy-status-drift` are invalid and abort the whole run — a deliberate narrowing of util3 §5.4's
per-entry tolerance. A zero-match entry is skipped **only** when affirmatively `already-applied`
(records equal what would be posted, never merely inferred from what's missing). Without that
carve-out a run that died at entry 12 of 217 could never be safely re-run — re-running to finish an
interrupted job, and applying an already-applied file, are both meant to be safe, cheap, and call
zero write endpoints.

**`proxy-status-drift`, and why `proxied` is checked BESIDE the comparison key rather than inside
it.** `record_key` is `(TYPE, normalize(name), canonical_content)` and carries no `proxied` — it
must stay comparable against `delete_match`, whose items are `{type, name, content}` only. That
left `proxied` read by nobody, and it shipped: with Cloudflare holding exactly the plan's A record
but `proxied=False`, the entry classified `already-applied` and verified `True` — a DNS-only
replacement is out of certificate service (HTTPS outage plus origin-IP exposure), the migration's
worst outcome. `proxy_status_mismatches(posts, rows)` is now a second comparison in the two places
that compare R against **P**: the `already-applied` row (disagreement → invalid, abort) and the
post-apply verification (→ `VerifyError` → `unverified` → exit 3). The **delete** side is
deliberately unchecked. A live `proxied` of **`None` is a mismatch, not a pass**.

**The file contract has nine checks.** Check 9 — every post in one entry must agree on `proxied`
and `ttl` — is a property of the operator's file, so it is a `PlanFileError` before the first API
call; `describe_change` keeps the same guard as an `InvariantError`, where reaching it means the
gate has a bug.

**The `generated` header is checked and warned about — never refused.** After the file contract
passes and **before the Cloudflare client is built**, `read_provenance()` writes an unconditional
stderr `ATTENTION` on five conditions: a **partial** sweep (`N of M zones`), an **absent or
non-integer** pair, a file **older than 24 hours** (`STALE_PLAN_HOURS` — validation compares R
against the CNAME, so a plan whose *addresses* went stale still validates `ready` and then writes
the wrong ones), a **future** stamp, or an **unreadable** one. Both numbers land in the run record
as `run.source_zones_swept`/`source_zones_total` on every run. It warns rather than refuses because
a narrow sweep is a documented workflow, and refusal would need an override flag — one more thing
to pass by reflex.

**Exit taxonomy — one code the siblings don't have.** `0` completed clean (or a dry run that
validated clean), `1` completed with ≥1 `already-applied` skip, `2` could not complete and
**nothing in Cloudflare was changed**, `3` **failed mid-apply and Cloudflare was left partially
changed**, `130` interrupted. `3` exists because folding a half-finished rewrite into `2` would be
indistinguishable, to an operator's `case $?`, from a clean refusal that touched nothing.
`changed_count()` (one shared helper, read by both `exit_code_for` and the summary's `mode:` line)
counts an entry as changed when its outcome is `applied`, `unverified` **or** `unknown`; `failed` is
excluded, because a batch is one transaction and a rejected call commits nothing. **No failure path
may report `2` once anything has changed — which needs a reader half AND a writer half:** every arm
computes the code from `changed_count()`, **and** `apply_all`'s handler chain ends in a catch-all
recording the in-flight entry `unknown` before re-raising, so nothing unnamed leaves an attempted
entry at its `not-attempted` seed. Shipping only the reader half made this false once.
`InvariantError` is the one exemption (provably pre-batch). Rationale and the mutation evidence:
util4 SPEC §8.1/§9.3.

**Seven outcomes** — a different axis from `verdict`: `applied`, `already-applied`, `planned` (the
dry-run stand-in), `failed` (batch rejected, nothing committed), `unverified` (the batch
**returned**, so Cloudflare committed, but the re-list didn't confirm it, **or anything at all was
raised after the batch returned**), `unknown` (the call didn't complete, or a failure that cannot be
placed relative to the commit), and `not-attempted`. `apply_entry` converts anything raised after
the batch returned into a `VerifyError` (never `BaseException` — a Ctrl-C must still reach
`apply_all`'s `unknown` arm), because every such exception shares one property: the batch already
committed. Pass 3's three `return` arms are each pinned by a **three-entry** test asserting the
third entry was never posted — a one-entry fixture cannot distinguish `return` from `continue`.

**`--for-real` is the blast-radius gate** (without it no batch call is ever made — asserted against
the fake client's recorded calls, not inferred). **`--only FQDN` is repeatable (`action="append"`),
deliberately NOT `nargs="+"`**: with one positional `FILE`, `--only a b file.json` would silently
swallow the filename into the option. An `--only` name matching no key is fatal (exit 2) and every
miss is named. Unselected entries are never validated and never counted as anything but "in the
file" — validating an entry the run won't touch would let an unrelated FQDN's drift abort a
deliberately narrow run.

**The run record is written on every exit path, dry runs included** —
`<input-stem>-run-<YYYYMMDDThhmmssZ>.json`, beside the input file, named `-run-` and not
`-applied-` for exactly that reason. It carries `for_real: false` on a dry run, because a dry run
*is* the validation report and the thing an operator attaches to a change ticket. A run-record write
failure is reported on stderr but does not downgrade an earned exit code back to 2 once something
was changed; it forces exit 2 only when the run had changed nothing anyway. **One documented
exception, shared with the summary block:** argparse's `--help` and usage-error exits happen inside
`parse_args`, before `options.file` exists, so neither the summary nor the run record is produced on
those two paths — structurally, not as an oversight.

## Required runtime credentials / external tools

Running against real sites needs, in the environment: `terminus` authenticated with a
Pantheon machine token; an SSH agent holding the Pantheon key (`ssh-add`); `SMTP_PASSWORD`
(U-M Kerberos password, referenced by `[SMTP].password = "<{secret env SMTP_PASSWORD}"`);
optionally `AWS_*` and `CLOUDFLARE_EMAIL`/`CLOUDFLARE_API_KEY` (or `CLOUDFLARE_API_TOKEN`),
referenced by the `[Cloudflare]` settings. **Credentials are never read from the environment
by feature code**: everything flows through config `<{env …}` / `<{secret env …}`
substitutions (see the config-substitution note under Architecture). **The marker ends at `}` —
the trailing `>` in the sample config's prose is decorative, NOT syntax**; the regex is
`<\{(.*?)(?<!\\)}`, so a value written `"<{env USER}>"` resolves with a literal `>` appended,
silently. The only direct `os.environ` touches are `plugin/env/get_env.py` (which *is* the
`<{env}` engine) and the `AWS_PROFILE`/`AWS_DEFAULT_REGION` boto plumbing in
`plugin/aws/__init__.py` — don't add more. That allowlist is scoped to
`psh/`/`check/`/`plugin/`/`script_context.py`/the shim and pinned by
`tests/unit/test_house_rules.py`; the three temporary `find-*`/`apply-*` utilities are
deliberately outside it and read `$PANTHEON_MACHINE_TOKEN` / `<{env …}` markers themselves.
See `docs/env-and-smtp-configuration.md` and `docs/email-configuration.md`.
`php` must be on PATH at runtime (the CSS inliner); `composer` is needed only for the one-time
`composer install` that populates `vendor/`. Every other `composer` in feature code is a
**Terminus subcommand run remotely on Pantheon**, not a local binary.

## Architecture

### Core package + `script_context` shared state

The orchestrator — `main()`, the argparse pair (`build_arg_parser`/`parse_args`), and the
per-site pipeline — lives in **`psh/cli.py`**. The rest of the program body is carved into
sibling `psh/` modules, one layer each; `psh/cli.py` imports the names it calls (and re-imports
the pure helpers below), so it is the single module the test `psh` fixture exposes.

`psh/cli.py` also owns its own stage helpers, extracted from `main()` so each stage is
reachable by a test without running the loop: `validate_options()` (the four argument guards, in
their shadowing order — see **Resuming an interrupted `--all` run**), `ensure_build_dir()` (the
`./build` creation guard — extracted because it runs **above** `main()`'s `try:` /
`except BaseException`, so a raise there reaches no handler and the operator gets a bare traceback
and CPython's exit 1, the code `abort_reason` reserves for a *database* failure; a non-directory
`build` and every other `OSError` now get their own named `sys.exit`, and
`tests/unit/test_ensure_build_dir.py` is the only seam that reaches this, since `main()` has no
in-process caller), `resolve_site_roster()` →
`SiteRoster` (the `org:site:list` fetch, name→id map, sort and resume filter; its `site_count` is
`len(sites)` **before** the filter — the denominator of the per-site banner and of `finish_run`'s
"Email sent for N of M sites", never `len(site_names)`), `fetch_site_domains()` → `SiteDomains`
(`None` = skip this site) and `resolve_site_url()` → `SiteUrlFacts` (which straddle the
`site_post_dns` seam and so must stay two functions), `sort_notices_and_subject()` (the notice
ordering + subject override, which reads the hook-produced `annual_bill_upcoming` with `.get()`),
and the pure notice builders `no_domains_notice` / `no_primary_domain_notice`. Each module:

- **`psh/gateway.py`** — the gateway: every Terminus/WP-CLI/Drush subprocess flows through it
  (the ten wrapper defs plus the named `TerminusError`; the future Pantheon-API transport seam —
  see the **Terminus/WP/Drush wrappers** bullet).
- **`psh/configuration.py`** — the config engine: `process_config`/`config_substitution`/
  `gate_disabled_sections`/`load_news_items`/`umich_enabled`/`cloudflare_enabled` plus the DEFER
  machinery (see **Config substitutions**). `sc.umich_enabled`/`sc.cloudflare_enabled` are
  exposed on the façade.
- **`psh/notice.py`** — `Notice` (a frozen dataclass), `Severity` (a `StrEnum`),
  `NoticeRegistry`, and `DuplicateNoticeCodeError`: the typed notice model (see **Notices vs.
  news**). It imports nothing from `script_context`, so both `sc` and every `psh/` module can
  import it without a cycle.
- **`psh/modules.py`** — module discovery + the hook engine: `find_modules`/`import_packages`
  (the walker and the two import loops `main()` runs), `PHASES`,
  `add_hook`/`invoke_hooks`, the consumes/produces DAG validation
  (`validate_hooks`/`ordered_hooks`, the `HookDagError` family), the authoritative `CONTRACT`
  registry, and the `stuff_traffic_contract`/`stuff_gather_contract`/`stuff_envs_contract`
  stuffers (see **Hooks** and the data-contract table). `script_context.py` re-exports
  `PHASES`/`add_hook`/`invoke_hooks` via a top-of-file `from psh.modules import …`, so
  `psh/modules.py` must NOT import `script_context` at module level — its engine functions
  import `sc` at call time (the module docstring carries the diagram). The mutable `sc.hooks`
  dict deliberately stays in `script_context.py`, because `reset_sc` rebinds it around every
  test and CAMPAIGN.md §3.4 bars module-level mutable state in `psh/`.
- **`psh/db.py`** — every DB touch the core report pipeline makes (the portal DB in
  `plugin/umich/portal.py` opens its own engine, through the shared `db_engine_args`): the
  SQLAlchemy models (`Base`,
  `PantheonTraffic`, `PantheonOverageProtection`), the row types (`TrafficRow`,
  `OverageProtectionRow`), the resilience layer (`db_retry`, `db_retryable`,
  `record_db_reconnect`, `DatabaseUnavailableError`), the read/write units
  (`update_traffic_rows`, `insert_traffic_rows`, `load_traffic_rows`,
  `load_overage_protection_window`), `db_engine_args` (exposed as `sc.db_engine_args`), and
  `open_database(db_config) -> (Engine, Session)` — the one engine/session opener `main()` calls.
  See
  **Database**. The two reconnect counters do NOT live here: they are fields of the `RunState`
  dataclass (`psh/lifecycle.py`), reached as
  `sc.run_state.db_reconnects_by_site`/`…failures…` — one shared, `reset_sc`-isolated namespace
  rather than two separately rebindable module bindings of the same name.
- **`psh/traffic.py`** — the traffic-metrics layer: `traffic_table_columns`,
  `get_old_metrics`, `estimate_month_visits`, `build_traffic_table_rows`, three per-site flow
  functions (`update_site_traffic`, `import_older_site_metrics`, `load_site_traffic`), the pure
  `aggregate_visits_by_month`, and `build_traffic_window(...) -> TrafficWindow` — the whole
  report-window assembly (aggregation, `build_plan_over_time`, the month-midpoint `dates`, the
  `estimate_month_visits` call, and the plan-day bounds) as one NamedTuple. `main()` unpacks all
  nine fields back into its **pre-existing local names** on purpose: the `db_retry` lambda below
  the call carries six per-line `# noqa: B023` suppressions, five of them keyed to those exact
  names (the sixth is the loop's `site`). The
  zero-traffic case returns a **synthetic seed** (`plan_on_day == {end_date: current_plan}`,
  `first_plan_day == last_plan_day == end_date`) rather than an empty map — `plan_on_day` is
  never empty, which is what keeps this helper's own `days[0]` / `plan_over_time[0]` off an
  `IndexError`. (`psh/charts.py`'s separate `plan_on_day[ymd]` midpoint lookup is a **`KeyError`**
  risk and is documented there as a precondition, NOT something the seed guards.)
- **`psh/plans.py`** — the plans layer: `cost_table_columns`, `overage_blocks`,
  `contract_year_end`, `plan_costs`, `build_plan_over_time`, `build_plan_recommendation_notice`;
  the typed `PlanCatalog`/`PlanInfo` view over `[Pantheon].plan_info` (`PlanCatalog.from_config`
  performs the `"-"` → `None` normalization **mutating the config sub-dict in place**, so
  `main()`'s `plan_info`/`plan_names` aliases and the chart/annual-billing regions keep reading
  the same object — a copy would fork two views of one config); `resolve_plan_name(site)` (the
  Elite-SKU lookup — `None` on a transient Terminus failure, which its **only** caller
  `resolve_site_plan` passes straight through as its own skip sentinel for `main()` to
  `continue` on; `sys.exit` preserved on a missing/unknown SKU); `resolve_site_plan(site,
  plan_names) -> str |
  None` (the caller-side wrapper around it: the SKU resolution, the `site["plan_name"]`
  **in-place** write-back, the Sandbox skip and the unknown-plan `sys.exit("Bailing out.")`
  postcondition. `None` is the **skip sentinel** for *two* conditions — a transient `plan:info`
  failure and the Sandbox plan — which is only acceptable because each prints its own operator
  message before returning; `main()` does the `continue`, never the helper); `recommend_plan(...)`
  (returns a frozen
  `PlanRecommendation` and adds the upgrade notice to `site_context` itself); and
  `stuff_plans_contract()` (which nests `cost_same`/`costs_median`/`costs_best` into the single
  `plan_costs` **contract key** `{"same": …, "median": …, "best": …}`).
- **`psh/gather.py`** — the framework gather cores. WordPress: `check_wordpress_plugin` (the
  recommended-WordPress-plugin notice builder the papc/sessions/cloudflare_cms hooks call via
  `sc.check_wordpress_plugin`), `wordpress_network_url` (**returns `None` for the URL when the
  eval was fatal, non-str, OR successful-but-empty** — never the `""` the gateway hands back on
  the fatal path, because `psh.cli.resolve_site_url` overrides `site_url` on `is not None`, so
  returning `""` blanked a perfectly good `https://{main_fqdn}/`; fixed 2026-08-07, pinned by
  `test_a_fatal_network_url_fetch_keeps_the_main_fqdn_url_and_notices_the_failure` and
  `test_an_empty_network_url_keeps_the_main_fqdn_url` in
  `tests/integration/test_site_domains.py`), and `gather_wordpress` (version /
  plugin-list / theme-list fetches, add-on-update collection plugins-then-themes in list order,
  the must-use diagnostic print) returning a **`WordPressGather`** NamedTuple that
  `gather_framework` (below) — **not** `main()` — threads into its branch locals; the
  last-wins-but-never-clearing semantics (a later empty smell never clears an earlier one)
  are `main()`'s, applied to the `FrameworkGather` smell *deltas* `gather_framework` returns.
  Drupal: `check_drupal_module` (the recommended-module notice builder the
  Drupal siblings call via `sc.check_drupal_module`), `gather_drupal` (banner + core-status
  fetch + version derivation + `site_results` entry, pm:list, and the D7 pm:updatestatus **or**
  D8+ composer dry-run + composer audit add-on collection — the D7-vs-D8+ branch stays inside
  because it selects between two *gather* strategies, not between checks) returning a
  **`DrupalGather`** NamedTuple threaded by `gather_framework` like the WP branch.
  The `wp_error`/`drush_error` notices for *failed gathers* stay with the fetches (they
  describe the gather, not a check); the notice-emitting checks that once interleaved here live
  in `check/wordpress/`, `check/drupal/`, `check/umich/`, and `check/smells/` — the last of
  which took `build_smell_notices` *and* its emission out of this module and out of `main()`
  on 2026-08-07 (`development/2026-08-07-smell-notice-relocation/SPEC.md`).
  `gather_drupal`'s composer dry-run calls `run_terminus(...)` directly (composer output is
  human-readable text, not JSON), so this module binds `run_terminus` in its **own** namespace
  — see the two-binding seam note under Testing.
  **`gather_framework(site, live_site, site_context) -> FrameworkGather`** is the branch
  selector above both gathers (WordPress / Drupal / the unknown-framework fallback with its
  `ATTENTION` print), returning versions, plugins/modules, `add_on_updates` (the **same list
  object**, never a copy — the contract publishes it by identity), the `site_results` entry, and
  the three **smell deltas**. The deltas are why `main()` keeps the merge: a returned `""` means
  *no NEW smell*, never *clear the previous one*, so the helper is deliberately never handed the
  caller's current values. It touches **no** `RunState` — pinned by a test that calls it with no
  `sc.run_state` bound at all, the one mechanical check of CAMPAIGN.md §3.4's parallel-ready
  constraint.
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
  from it; `finish_run`'s first action, before any teardown or artifact write, is
  `sc.invoke_hooks("run_finish", run_state)`
  (`CONTRACT["run_finish"]` stays `()` — the `RunState` is the hook argument, not a contract
  key). It **NEVER imports `script_context`/`psh.db` at module level** (module-level imports are
  stdlib + `sqlalchemy.exc` + `rich` only) — `sc` is reached at call time, and **two permanent**
  call-time bridges live inside functions: `abort_reason`'s `from psh.db import
  DatabaseUnavailableError, db_retryable`, and `option_strings_taking_a_value`'s `from psh.cli
  import build_arg_parser` (D-i14a-4 corrects LEDGER I13: that one is a permanent cycle, not a
  temporary obligation). The module docstring carries the import-cycle diagram (PD#8).
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
`sc.cloudflare_enabled`), plus `sc.SiteContext`, `sc.plugin_context`, `sc.DEFER`/
`sc.ConfigSubstitutionError`, `sc.icon`, and helpers `debug()`, `add_news_item()`,
`html_to_text()`, `msgid_domain()`, `smtp_username()`.
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
`check.drupal`, `check.pantheon`, `check.pantheon_cdn_change`, `check.smells`, `check.umich`,
`check.wordpress`).
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
  `<{ ... }` are resolved by `process_config()`/`config_substitution()` against these
  registered functions. `process_config()` is run twice: a pre-setup pass resolves everything,
  then a post-setup `deferred_pass=True` pass re-resolves **only** substitutions that deferred.
  A substitution whose backing data a `setup` hook populates (e.g. `plugin.umich`'s `plan_info`,
  which needs the portal DB) returns the `sc.DEFER` sentinel; `config_substitution` re-emits its
  marker with an invisible NUL tag that only the deferred pass matches. This lets pass 2 resolve
  deferrals **without** re-interpreting a pass-1 final value that merely contains a `<{…}`
  sequence (e.g. a password) — so route secrets through substitutions freely. A substitution
  aborts the run by raising `sc.ConfigSubstitutionError` (caught in `config_substitution`, which
  prints the offending config *path* + message and exits) — this is how `plugin.env.get_env`
  (missing env var) and `plugin.aws.get_secret` (missing secret key) report failures. **Just
  before those substitutions run, `main()` calls `gate_disabled_sections()`**: any section **at
  any depth** with `enabled = false` (boolean identity; nested tables like
  `[Cloudflare.cachecheck]` included, and a disabled parent drops its children entirely) is
  reduced to just `{'enabled': False}`, dropping its other keys **before** substitution — so a
  disabled feature's `<{secret env …}` values are never required to exist. For substitutions
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
  `frozen.py` (consumes nothing) and `live_env.py` (paid plan with no initialized live env;
  consumes `envs`) at `site_pre`; `updates.py` (`terminus upstream:updates:list` staleness, via
  `sc.terminus`) and `php_eol.py` (PHP end-of-life; consumes `envs`) at `site_post_gather`,
  registered in that order. **Two** of the four notice bodies — `frozen` and `updates-*` — embed
  un-gated U-M links (see the still-hardcoded-U-M list under Testing); `no-live-env-but-paid-plan`
  carries no URL at all and `php-eol` only `docs.pantheon.io` ones.
- `check/wordpress/` — four generic WordPress checks (gated on `[Check.wordpress].enabled`,
  **default true**), all at `site_post_gather`, registered PAPC → sessions → OCP → favicon:
  `papc.py` and `sessions.py` (both delegating to `sc.check_wordpress_plugin`), `ocp.py` (Object
  Cache Pro config probe via `sc.wp_eval`; consumes `framework`+`wordpress_plugins`) and
  `favicon.py` (favicon presence probe via `sc.wp_eval`; consumes
  `framework`+`fqdns_not_behind_cloudflare`). Every hook
  early-returns unless `site_context["framework"].startswith("wordpress")`. The `ocp`/`favicon`
  probes rebind `site_context["wp_smell"]` on non-fatal stderr (one of the two sanctioned
  mutate-during-phase contract keys) and build failure notices with `sc.wp_error`. The favicon
  notice body embeds un-gated its.umich.edu links.
- `check/drupal/` — three generic Drupal checks (gated on `[Check.drupal].enabled`, **default
  true**): `multisite.py` (the multisite probe via `sc.drush_php_script`, a `site_post_dns` hook
  that consumes `custom_domains`/`primary_domain` and **produces** the hook-declared keys
  `drupal_multisite`/`drupal_multisite_smell`, read by `psh.cli.resolve_site_url` with `.get()`
  after the phase to seed `drush_smell` and gate the core `no-primary-domain` notice), `papc.py` (delegating to
  `sc.check_drupal_module`) and `d7_eol.py` (the `drupal7-eol` notice + the tag1_d7es module
  check), the latter two at `site_post_gather`, registered multisite → papc → d7_eol; each
  early-returns unless the framework starts with `drupal`.
- `check/addon_updates/` — one `site_post_gather` hook, `table.py` (the pending-add-on updates
  table notice, consumes `add_on_updates`, reading the SAME list object the stuffer publishes;
  gated on `[Check.addon_updates].enabled`, **default true**); its `updates-addons` notice body
  embeds an un-gated its.umich.edu support link.
- `check/smells/` — the three "PHP code problems" notices (`wp-smell`/`drush-smell`/
  `composer-smell`: non-fatal wp/drush/composer stderr), `notices.py` (the
  `build_smell_notices` builder) + a `site_pre_render` `hook.py` consuming
  `wp_smell`/`drush_smell`/`composer_smell` and producing nothing; gated on
  `[Check.smells].enabled`, **default true**. **The phase is load-bearing and later than the
  other framework checks on purpose**: `site_pre_render` is unconditionally after the
  `site_post_gather` hooks that rebind `wp_smell`/`drush_smell` in place (so no ordering edge
  is needed) and it sits below `main()`'s `--only-warn` `continue` (so a warning-only run emits
  no smell rows, exactly as the pre-2026-08-07 inline emission did). Moved out of
  `psh/gather.py` + `main()` on 2026-08-07 —
  `development/2026-08-07-smell-notice-relocation/SPEC.md`.
- `check/pantheon_cdn_change/` (`site_post_dns`, unconditional registration) flags custom
  domains still CNAME'd to the legacy Pantheon GCDN (Fastly) — in public DNS or in Cloudflare —
  and gets the replacement records Pantheon requires from `terminus domain:dns`. **Temporary**,
  delete once Pantheon's CDN migration is done — see `docs/pantheon-cdn-change.md`.

To add a check or integration plugin, create a new package dir with a non-empty `__init__.py`
that self-registers — no central registry to edit. Check modules cannot import the dash-named
main script; the helpers they need are exposed as `sc` attributes in the block at
`psh/cli.py:151-163`: `sc.escape_url`, `sc.check_wordpress_plugin`, `sc.check_drupal_module`, `sc.umich_enabled`,
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
pins the **five** stuffers (`stuff_traffic_contract`/`stuff_gather_contract`/`stuff_envs_contract`
in `psh/modules.py`, `stuff_dns_contract` in `psh/dns_classify.py`, `stuff_plans_contract` in
`psh/plans.py`) against it, so drift on either side goes red:

| Phase | Guaranteed new keys (beyond `site`/`notices`/`sections`/`attachments`) |
|---|---|
| `setup` | — (run-level, fires once before any site; receives no `SiteContext`. `CONTRACT["setup"]` is `()`) |
| `site_pre` | `envs` (dict — the `terminus env:list` JSON keyed by environment id, each value carrying `id, created, domain, connection_mode, locked, initialized, php_version, php_runtime_generation`. `main()`'s guards ensure `envs["live"]` exists with an `initialized` key before any site phase fires; **`php_version` is NOT guaranteed present** — read it with `.get`. Never `None`/empty when a phase fires: a failed `env:list` fetch skips the site. Core-produced — fetched by `main()` where it gates on it, stuffed by `stuff_envs_contract`. The phase fires after the traffic gather and the `--update`/`--import-older-metrics` continues, just before `site_post_traffic` — NOT at SiteContext creation) |
| `site_post_traffic` | `traffic_rows` (`list[TrafficRow]` — plain `NamedTuple` data, attribute names matching the ORM model: `.site_id`, `.traffic_date`, `.site_plan`, `.visits`, `.pages_served`, `.cache_hits`; **not** live ORM rows, because a `db_retry` rollback expires every loaded ORM object, so a hook holding one would emit an unretried SELECT on the next attribute read), `start_date`, `end_date` |
| `site_post_dns` | `domains`, `custom_domains`, `primary_domain`, `main_fqdn`, `fqdns_behind_cloudflare`, `fqdns_not_behind_cloudflare`, `not_in_dns`, `behind_cloudflare_not_proxied`, `proxied_in_multiple_zones`, `dns_transient` (Cloudflare classification lists `[]` when `[Cloudflare]` disabled, the FQDN resolved to no address, or domains malformed. A FQDN resolving to nothing is `not_in_dns` when definitive else `dns_transient` (unknown) — neither runs Cloudflare checks; a FQDN with ≥1 resolved address is classified even if a sibling lookup was transient. Produced by `psh.dns_classify.classify_domains()`, published via `stuff_dns_contract()`. **Hook-produced keys (NOT registry-owned):** `check.drupal.multisite` additionally *produces* `drupal_multisite` (bool) / `drupal_multisite_smell` (str). They are DAG-declared in the hook's `produces`, present **only** when the probe actually ran (absent when its gate failed, the framework is not Drupal, or `[Check.drupal]` is disabled), so `psh.cli.resolve_site_url` — which `main()` calls **after** the phase, exactly so it can read them — reads them with `.get(...)` — never assume they exist) |
| `site_post_gather` | `framework` (str), `site_url` (str, `""` when unknown), `wordpress_version` (str; on a failed fetch it is the fatal `wp eval`'s stdout — `""` in practice, since `wp_eval` always returns decoded-and-stripped stdout; the `"unknown"` fallback survives in `psh/gather.py` but is unreachable through the gateway, which never returns a non-str; None only when not that framework), `drupal_version` (str; `"unknown"` — NOT None — when the version fetch failed; None only when not that framework), `wordpress_plugins` (list\|None), `drupal_modules` (**dict**\|None — drush pm:list returns a dict keyed by module name); None on the plugins/modules keys = not that framework or the gather failed. `add_on_updates` (list of pending add-on-update dicts — `slug`/`name`/`type`/`current_version`/`new_version`, plus an optional `new_version_url` on composer-audit rows; WordPress emits plugins then themes in list order, Drupal composer-audit rows carry `type: "package"`; `[]` when none, not that framework, or the gather failed; stuffed as the SAME list object the `check.addon_updates.table` hook reads, not a copy), `wp_smell`/`drush_smell`/`composer_smell` (str, `""` when none — the stderr of the last non-fatal wp/drush/composer wrapper call that produced any. **`wp_smell` AND `drush_smell` MAY be rebound in place during the phase** — `wp_smell` by `check.wordpress.ocp`/`check.wordpress.favicon`, `drush_smell` by `check.umich.drupal_ua` — their probes' stderr participates in last-wins; these are the **two sanctioned mutate-during-phase keys**, so consumers reading after the phase (the smell emission) MUST read `site_context["wp_smell"]`/`site_context["drush_smell"]`, never a stale `main()` local; the hooks do NOT declare `produces: ['wp_smell']`/`['drush_smell']` — that would be a duplicate-producer fatal against the core `CONTRACT` registry) |
| `site_pre_render` | everything above, plus `current_plan` (str), `recommended_plan` (str; == `current_plan` when no change was recommended or the site had too few in-window months), `plan_costs` (dict `{"same": {plan: float}, "median": {plan: float}, "best": {plan: float}}`; `{}` when ≤4 in-window months), `savings` (float; `0.0` when no recommendation) — the plan-recommendation keys, published by `stuff_plans_contract()` (full-report path only; still no consumer — the documented seam for future report-shaping hooks). **Hook-produced keys (NOT registry-owned):** `check.umich.annual_billing`'s `site_pre_render` hook additionally *produces* `annual_bill_upcoming` (a render dict, built by `site_context.notice_to_dict`) — DAG-declared, present **only** when the hook ran (absent when `[UMich]` is disabled or `sc.contract_year_end(end_date)` was false), so `sort_notices_and_subject` reads it with `.get(...)` after the phase. **A second hook runs in this phase and adds no key at all:** `check.smells.hook.emit_smell_notices` *consumes* `wp_smell`/`drush_smell`/`composer_smell` (read live off the `SiteContext`, never cached — they are the two sanctioned mutate-during-phase keys plus `composer_smell`) and `produces: []`; what it contributes is the three "PHP code problems" notices, appended to `site_context["notices"]` before `sort_notices_and_subject` runs, which is why the guaranteed-keys list above is unchanged |
| `run_finish` | — (run-level, not per-site: receives no `SiteContext`; it receives the run's `RunState` — `finish_run`'s first statement is `invoke_hooks("run_finish", run_state)`, fired on completed and aborted runs, the seam for future run-level artifact hooks. `CONTRACT["run_finish"]` stays `()`: the `RunState` is the hook argument, not a contract key) |

**The send block stays in `main()`, not `psh/mail.py`.** The send sequence is `smtp_login()` …
`send_message()` … `quit()`, and the accumulator writes `run_state.emails_sent += 1` /
`site_emailed = True` sit **between** `send_message()` and `quit()`. Hoisting the block into
`psh/mail.py` would move those counter updates after `quit()` returns, reopening the
Ctrl-C-during-`quit()` duplicate-email window. `main()` keeps calling `smtp_login()` itself.

**No extracted helper may be the sole assigner of `site_name` or `site_emailed`.** Python has no
block scope and the `except BaseException` handler reads both ~325 lines below where they are
bound, as `abort_run(db_session, db_engine, site_name, reason, e, emailed=site_emailed, …)`. Two
concrete failures, neither visible to any of the four goldens:

- **`site_emailed`.** There are *two* assignments three characters apart: the **pre-loop
  binding** (the handler's guarantee that the name exists before `try:` opens) and the
  **per-iteration reset** at the top of the loop body. A "per-site preamble" helper is the
  natural-looking boundary that swallows the reset — and then `main()`'s local, set `True` for
  site *N*, is never cleared for site *N+1*. Site *N+1* aborts at `domain:list`,
  `abort_run(..., emailed=True)` advances the resume point **past** it, and that owner silently
  never receives their monthly report (the `site_results.pop()` drop is skipped too, so the
  artifacts claim the site completed). PD#1 — a failure that can happen silently is a critical
  defect.
- **`site_name`.** If a helper became its sole assigner, `abort_run` raises `NameError` **inside
  the handler** — after SIGINT is set to `SIG_IGN` and before `finish_run()` — destroying every
  artifact the handler exists to save, and telling the operator nothing about the real failure.

`site_id` stays in `main()` for the same class of reason: it is read ~230 lines after it is
bound. This rule is prose, not an instrument — it is a queued question whether an AST assertion
over `main()`'s source can make it red-capable.

**The composition glue `main()` kept between the stage helpers has its own instruments, in
`tests/integration/test_regressions.py`.** Each helper's internals are well covered; the *wiring*
was not, and two invariants live only there. Measured on the branch that introduced them, both
violations left the whole suite green: collapsing a smell merge to an unconditional
`wp_smell = gather.wp_smell`, and hoisting the `resolve_site_url(...)` call above
`sc.invoke_hooks("site_post_dns", …)`. Both are now pinned by `inspect.getsource(psh.main)`
assertions — the same idiom and the same justification as
`test_site_notices_are_recorded_before_the_email_is_sent` in that file: `main()` has no
in-process caller (the subprocess interlock bans `--all`/`--for-real`) and no golden site is a
Drupal multisite or a `wordpress_network`, so the **order** and the **shape** are what can be
pinned. `test_resolve_site_url_runs_after_the_site_post_dns_phase` covers the ordering (the
helper reads the `drupal_multisite`/`drupal_multisite_smell` keys `check.drupal.multisite`
produces in that phase; run early, the multisite smell is lost *and* the `no-primary-domain`
suppression stops working); `test_each_smell_merge_stays_guarded` covers all five merges. Before
the extraction the ordering was structural — 25 lines physically below the phase firing — and it
is now one line away from being violated.

- **Notices vs. news**: `site_context` is a **`sc.SiteContext`** (a `dict` subclass, so
  `site_context['notices'|'sections'|'attachments'|'site']` access is unchanged) constructed once
  per processed site, as far up the per-site loop as possible (after the portal/not-requested/
  Sandbox skips). **That position is an invariant of the loop, which is why the constructor call
  stayed in `main()` when the skips around it moved into `psh.plans.resolve_site_plan`** (the
  Sandbox skip and the unknown-plan guard both went; the `sc.SiteContext(site)` line did not).
  Burying the constructor inside a helper would hide the invariant from the only code that can
  honor it — the next skip added would have no local signal about which side of the line it
  belongs on. Folding the unknown-plan guard into that helper does move it *above* the
  constructor, which is behavior-identical only because `SiteContext.__init__` is a bare
  `super().__init__(site=…, notices=[], sections=[], attachments=[])`: no console output, no `sc`
  write, no `run_state` write, and on the bail path the object is discarded unread. Adding a side
  effect to `__init__` would silently break that.

  Add to it via its methods — `site_context.add_notice(notice)` /
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
  and the per-FQDN cache checks at `site_post_dns` (consumes `fqdns_behind_cloudflare` +
  `primary_domain`; RNG
  seeded `{site}:{report_date}` so re-runs test identical URLs; MISS-retry 2s/2s protocol only
  when headers say cacheable; cross-FQDN redirects drop the URL with NO result item; invalid cert
  → item then insecure re-fetch continues the checks). Notice language has U-M and generic
  variants selected via `sc.umich_enabled()`; consolidation merges FQDNs whose findings differ
  only by URL; every notice's csv key is `cloudflare-cache`. See `docs/cloudflare-cachecheck.md`
  and `development/2026-07-08-cloudflare-cache-configuration/`.
- **Resuming an interrupted `--all` run**: `--resume-from SITE_NAME` filters the already-sorted
  site-name list **before** the loop (inside `resolve_site_roster`, via the pure helper
  `sites_from_resume_point`, which raises `ResumeSiteNotFoundError` on an unknown name → fatal),
  so skipped-over sites do zero work. It
  requires `--all` and is mutually exclusive with `--create-tables` (guards placed **first**
  inside `validate_options()`, before the create-tables/sites-or-all chain, or that chain shadows
  the precise messages — the four guards' order is the whole reason that helper exists). On a
  resumed run the two post-loop summary artifacts accumulate instead of truncating: `-notices.csv`
  opens in `"a"` mode and `-results.json` goes through `merge_prior_results()` (new wins on key
  collision; missing/malformed prior file → warn + this run's results only). See
  `docs/resuming-interrupted-runs.md`.
- **Rendering**: the Jinja render + PHP inline is `psh.render.render_report`. Templates
  `email_template.html` and `email_template.txt` are rendered per site into
  `build/<site>.{html,txt}`. **An empty `site_url` renders as the literal `(unknown URL)` in the
  "Main URL:" field of both templates** (2026-08-07) — the contract key itself stays `""`, so the
  `{%if site_url%}` guards elsewhere (the intro line, the traffic caption, the chart title) still
  omit their URL rather than emitting a non-URL string into an `href`; three of the four e2e
  goldens carry that literal, since their `domain:list` fixture leaves `main_fqdn` empty. The
  `.txt` traffic caption is one of those guards as of the same change — it printed a bare
  `{{site_url}}` and so left a stray blank line for a URL-less site; its `{%endif%}` sits on its
  own line on purpose, contributing the newline the URL line used to. The HTML is then run
  through `inline-styles.php` (PHP Emogrifier via
  `vendor/`) to inline CSS for email clients → `build/<site>-inline.html`, and a regex pass then
  appends `!important` to every declaration inside the `<style>` blocks Emogrifier **retained**
  — the rules it could NOT inline (`@media`, pseudo-classes); it never touches a `style="…"`
  attribute → `build/<site>-inline2.html`, **which is
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
`mysql` (anything else exits). Both `type` is read **unconditionally** and `name` on
both supported branches — a `[Database]` section missing either is a `KeyError`, not a default
(an unsupported `type` exits before `name` is read); the `sqlite`/`database.db` "default" lives in
the sample config, not the code. `--create-tables` creates the schema. **Two writers, with
different semantics:** the per-run daily refresh (`update_traffic_rows`) **upserts** via
`session.merge()`, overwriting an existing row — so a plan rename between runs rewrites
`site_plan` across the whole window; the `--import-older-metrics` backfill
(`insert_traffic_rows`) inserts-or-skips (`ON CONFLICT DO NOTHING` on sqlite via the
`sqlite_insert` import, `INSERT IGNORE` on mysql).

**Connection resilience.** The DB is remote (RDS) and the path crosses NAT/firewall middleboxes
that reap idle flows, so the engine sets `pool_size=10` / `max_overflow=20` /
`pool_pre_ping=True` / `pool_recycle=1800` (MySQL only;
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
every one of the three, `abort_run()` drops the failed site from `site_results` **and
`site_savings`** (both written mid-gather, so the site would otherwise ship as a success and be
counted in the epilogue's savings totals; both skipped when the report was already emailed),
flushes the artifacts via `finish_run()`,
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

Docs not referenced elsewhere in this file: `docs/config-migration.md` (moving an existing
config to the current schema), `docs/aws-credentials.md` / `docs/awscli-login.md`, and
`tests/README.md` (which `pyproject.toml` and `run-tests` both treat as canonical for the suite).

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
  by the cloudflare plugin; it is git-ignored (`.gitignore:10`) and untracked.
- Type-hint tuples like `-> (str, str, bool)` appear throughout; these are the existing
  (technically non-idiomatic) house style — follow the surrounding code.
- There is an active TODO list in `README.md` describing planned work (daily traffic alerts,
  Cloudflare/security scoring, moving capture into the portal app, better secrets handling).
- **`git diff -w` is not proof a re-indent was whitespace-only** — the leading whitespace inside a
  notice's `html=`/`text=` literal is string content that reaches the rendered email, and `-w` is
  designed to ignore exactly the line that only gained some. `main()`'s loop no longer holds such a
  literal; `psh/cli.py::no_domains_notice` does (interior at column **16**, not 0), and
  `tests/unit/test_no_domains_notice.py::test_the_literal_interior_stays_at_column_16` is what goes
  red — see the Invariant-8 sentinel comment above that `def`.

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
2. **pyright, standard mode** over `psh/` **plus the three temporary platform-domain utilities'
   `.py` symlinks** — `[tool.pyright].include` has four entries, not one (keep it in sync with the
   deletion checklists in the Commands section) — invoked as `[sys.executable, "-m",
   "pyright", "--pythonpath", sys.executable]` — **the venv's own pyright, resolving imports
   against the venv, never a PATH or `uvx` one**. Unlike ruff, pyright's verdict depends on the
   Python environment it resolves imports against: run against any other one it type-checks
   `psh/` with **none** of the project's dependencies installed and reports dozens of false
   `reportMissingImports` (34 from the dropped `uvx pyright@1.1.411` fallback, 46 from a
   non-activated venv). That is why the fallback went (2026-08-07) *and* why the
   `shutil.which("pyright")` branch went with it — a PATH pyright (an npm-global install, say) is
   the worse of the two, since it looks like the intended branch. **Both
   halves of the anchor are load-bearing**: `-m pyright` fixes which pyright runs (so the
   `[test]` extra's pin is the only thing deciding its version), and `--pythonpath` fixes which
   environment it reads — without it pyright finds the environment from the `python` on PATH, so
   `.venv/bin/python run-tests` without `source .venv/bin/activate` fails with 46 false findings
   through the *right* binary. pyright missing from that interpreter is a **hard failure** naming
   it, never a silent skip (PD#1/PD#14). **Its version is then verified before it runs**
   (`pyright_version_problem`): `--version` is measured against the `pyright==` pin *parsed out of*
   pyproject's `[test]` extra (derived, so the number has one home), and **every** way of failing
   to establish it — mismatch, missing pin, unparseable or unrunnable `--version` — aborts the
   gate. It reads the tool's own `--version` (0.3s) rather than `importlib.metadata`, which
   reports the pyright-**python wrapper's** version that `PYRIGHT_PYTHON_FORCE_VERSION` can move
   out from under the real checker. This closes the last drift route the mandatory-venv-binary
   change left open: a **stale venv**. `[tool.pyright]` additionally sets `venvPath = "."` /
   `venv = ".venv"`, which pins import resolution **for every pyright that is not `./run-tests`**
   — above all the `pyright-lsp` plugin, which launches `pyright-langserver` by **bare name from
   PATH**, so which environment the editor's diagnostics described used to be decided by process
   PATH order. Measured: with those two set, even a pyright from outside the venv reports 0
   errors with the venv off PATH.

`[tool.ruff]` deliberately pins **no `target-version`**: ruff infers it from `requires-python`
(`>=3.12`), and pinning it *masks* the 3.12-only PEP 701 f-string syntax the program uses. Each
gate is **version-pinned in exactly one place**: ruff by `uvx ruff@0.15.22` in `./run-tests` (so a
`uvx` cache refresh cannot silently move the bar; a PATH `ruff` is still trusted un-versioned — a
residual, accepted exposure recorded in `ruff_argv()`), pyright by `pyright==1.1.411` in
pyproject's `[test]` extra, which is now the **only** thing deciding its version (residual
exposure: a stale venv). `.claude/hooks/ruff-check.sh`
runs **the same single merged ruff pass** at edit time (advisory, via `PostToolUse`, with
`--force-exclude` and a repo-root `cd` so an edited excluded file honors the `extend-exclude`) but
**not** pyright (edit-time latency; `./run-tests` carries the type gate). No invocation passes
`--select` — the merged config is the single source of truth.

There is a pytest harness under `tests/` (design in `development/2026-07-04-test-harness/SPEC.md`).
Run it with `./run-tests` (wrapper over pytest): `./run-tests --fast` is the offline inner loop;
`./run-tests` adds the live tier; `--llm` gives terse machine-parseable output; `--coverage`,
`--update-goldens`, and `--record` do what they say. Any other argument is passed straight through
to pytest (the wrapper's own flags are the module-level `WRAPPER_FLAGS` set, and
`tests/unit/test_run_gates.py` pins that every member is actually read by a branch — a
listed-but-unread flag never reaches pytest either, which is how `--human` shipped as a silent
no-op). `--record` short-circuits to `tests/tools/record.py` and forwards **no** arguments —
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
  `monkeypatch.setattr(psh.signal, "signal", …)` still reaches it. **The same trap applies to
  `cloudflare_enabled`**: `psh/cli.py` does `from psh.configuration import cloudflare_enabled`, so
  a test gating `fetch_site_domains`' Cloudflare branch patches **`psh.cli.cloudflare_enabled`**,
  NOT `sc.cloudflare_enabled` — the façade attribute is what `check/`/`plugin/` modules call, and
  patching it leaves `psh/cli.py`'s own binding untouched (a patch that looks installed and
  isn't). Driving the gate through data instead — set `sc.config["Cloudflare"]["enabled"]` and
  populate `sc.plugin_context["plugin.cloudflare"]` — avoids the question entirely.
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
  DB-free via an injected `op_lookup(month)`), and `build_plan_over_time` (returns `[]` for an
  empty `plan_on_day`; its only production caller is `psh.traffic.build_traffic_window` — **not**
  `main()`, since `b106f80` — and the guard is that helper's synthetic zero-traffic seed, which
  makes `plan_on_day` never empty and so `plan_over_time[0]` never an `IndexError`, pinned by
  `tests/unit/test_traffic_window.py`) live in `psh/plans.py`.
  Also extracted: `load_news_items`, and `sites_from_resume_point`/`merge_prior_results` (the
  `--resume-from` logic, which cannot be reached through the `--all`-banned subprocess interlock
  and so is only testable in-process). `estimate_month_visits` and `build_traffic_table_rows` live
  in `psh/traffic.py`, along with `aggregate_visits_by_month(rows, start_date, end_date) ->
  tuple[dict, dict]` (`tests/unit/test_traffic_aggregation.py`), covering seeding traffic-free
  months to 0 and the last-row-wins `plan_on_day` map. The extractions are behavior-preserving
  (goldens byte-identical). **`classify_hostname_dns` is NOT one of these** — it lives in
  `psh/dns_classify.py`; import it from there.
- **Where the tests are.** By convention `tests/{unit,integration,e2e}/test_<subject>.py`, one set
  per `check/`/`plugin/` package: `test_<pkg>_init.py` = config gating + the hooks' phase/
  `consumes`/`produces` declarations; `test_<pkg>.py` = the hook seams via `sc.SiteContext` + the
  `gateway` fixture; `test_<pkg>_notice_render.py` = syrupy snapshots of the notice bodies
  (refresh with `--update-goldens`). **Each file's module docstring names its own seams and scope
  limits — read that, not a list here.** `codegraph affected <file>` finds static-import cover;
  for the standalone-loaded `check/`/`plugin/` modules it returns nothing (see `.claude/CLAUDE.md`'s
  measured blind-spot note), so fall back to the convention. Packages using relative imports load
  through `tests/helpers/checkload.py`; the rest use `SourceFileLoader` directly, and
  `check/cloudflare/` registers a probe package with `__path__` in `sys.modules` first.
- **A few cover facts the convention does not give you.** The `--resume-from` region is
  **permanently** unreachable at the subprocess tier (it requires the interlock-banned `--all`), so
  `tests/integration/test_site_roster.py` is its only cover. `psh.dns_classify.resolve` is the ONE
  monkeypatchable DNS seam — route any new resolution through it. `tests/integration/
  test_gather_wordpress.py`'s header records why `gather_wordpress`'s `"unknown"` fallback and the
  *isinstance* half of `wordpress_network_url`'s `None` return are unreachable through the gateway
  (the `fatal` half is reachable and load-bearing). **`test_hook_dag.py` cannot detect
  `check.smells`' hook being moved to an earlier phase** — the declarations validate there too — so
  `test_check_smells_init.py::test_no_smell_notice_exists_until_the_site_pre_render_phase` is the
  only cover for that phase choice, and it is behavioral (it drives every earlier phase and asserts
  no notice exists yet), not an assertion on the phase name.
- **The harness's own gates are tested** — `tests/unit/test_run_gates.py` loads the
  extension-less `run-tests` with the same `SourceFileLoader` idiom the other extension-less
  scripts use, and pins the two properties whose violation is **silent**: the type gate invokes
  *this* venv's pyright with `--pythonpath` (a reintroduced PATH/`uvx` branch still runs and
  still reports a verdict — a loud-but-useless 34–46 false `reportMissingImports`, which no
  "gate missing" check would catch), and pyright **never runs unverified** (that test asserts on
  the recorded `subprocess.call`s — exactly one, ruff's — because asserting the exit code alone
  stays green if the version check is moved *below* the pyright run). All five mutations were
  measured red, including the missing-pin one that was green until a test was added for it.
  `run-tests` is invisible to both ruff (which discovers by extension) and pytest, so this file
  is the only thing standing behind the instrument that decides "the suite is green".
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
  `terminus-cdnchange/` **and `terminus-unknownfw/`** will silently freeze at today's Pantheon
  JSON shape — each carries its own README. The `.eml` identity headers have no byte golden (the `Date:` is volatile) —
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
  post-campaign work): in `check/pantheon/` the `frozen` and
  `updates-*` notice bodies (its.umich.edu / procurement links — `no-live-env-but-paid-plan` and
  `php-eol` carry none, do not go looking), in `check/wordpress/` the
  `no-favicon` notice body (its.umich.edu documentation links), and in `check/addon_updates/` the
  `updates-addons` notice body (its.umich.edu support link). Keep institution-specific logic behind
  config flags / the `umich` plugin+check packages.

## Reusable prompts (`prompts/`)

`prompts/` holds the repo's own workflow prompts — read the relevant one before doing that kind of
work, and cite it by name rather than re-deriving the conventions.

**`prompts/directives.md` is the Spine** and comes first: the ONE copy of the Posture, the 14
Prime Directives, the Engineering Preferences, and the spec quality bar. Every other file in
`prompts/` is a *delta* that cites directives **by number**. This matters because they used to
live in two files and **drifted** — PD#11 gained a `/domain-modeling` mandate in one copy and not
the other, and the adversarial reviewer read the stale one.

**One exception, and it is a live trap:** `implementation-standards.md`'s *Directives at
implementation time* section re-expresses nine directives as code-level obligations **under its
own numbering, which does NOT match the Spine's** — its `1.` is "Every error has a name" (Spine
PD#**2**) and its `2.` is "Zero silent failures" (Spine PD#**1**), i.e. inverted on the two most
cited. Always resolve a `PD#n` citation against `prompts/directives.md`, never against that
section's list numbers.

The deltas: `new-feature-standards.md` (how features get specced), `implementation-standards.md`
(the standards layered on `superpowers:subagent-driven-development`; the intended invocation is
"implement everything per the spec doc(s), adhering to the standards in
`prompts/implementation-standards.md`"), `debugging-standards.md` (the standards layered on
`mattpocock-skills:diagnosing-bugs` — for **runtime** failures; document defects go to
`adversarial-review.md` instead), `adversarial-review.md`, `add-tests-for-change.prompt.md`,
`refresh-fixtures.prompt.md`, and `update-claude-md.md`. Note `development/2026-07-04-test-harness/`
contains **duplicate copies** of two of these (`add-tests-for-change.prompt.md` has already
drifted; `refresh-fixtures.prompt.md` is still byte-identical, which is more dangerous, not less —
it reads as authoritative) — `prompts/` is the source of truth.

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

Of the user-typed ones, **`/improve-codebase-architecture`** (hunting expansion opportunities) is
the main reason Matt's set is installed — nothing else here does that job; **`/grill-with-docs`**
sharpens a big feature before `superpowers:brainstorming`. `/triage`, `/wayfinder` and
`/to-tickets` have no current use (no issue inflow, mature codebase).

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

The core package + self-registering `check/`/`plugin/` layout came from the modularization
campaign, which is **complete**: it carved a several-thousand-line single-file script into the
`psh/` package, the `check/`/`plugin/` packages and the `main()` orchestrator, over a sequence of
increments while the four e2e goldens stayed byte-identical. Record:
`development/2026-07-17-modularization-campaign/` — **`CAMPAIGN.md`** (the frozen architecture and
invariants; amendments only), **`LEDGER.md`** (the one home for "which increment did what"), plus
`BLOCKMAP.md` / `CLOSING-AUDIT.md` / `RETROSPECTIVE.md`. This `CLAUDE.md` describes the
architecture as it **is**.

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

Fetch as needed, using the HTTP request header `Accept: text/markdown`, and follow links on the
pages: Pantheon docs (https://docs.pantheon.io) and Cloudflare docs
(https://developers.cloudflare.com/ — `/fundamentals/api/` and `/api/` for the API).

## Other / General
* **Before writing, reviewing, or refactoring any code in this repo, invoke the
  `andrej-karpathy-skills:karpathy-guidelines` skill and follow it.** This is not optional and
  not a judgment call — do it even when the change looks trivial. (Skip it only for purely
  conversational turns that touch no code.)
* Avoid flattery as feedback, stick to facts that matter. For example, "Got it — that's a meaningful architecture upgrade, and a good one." doesn't add anything of value. But do give me feedback about things that are not good, could be improved, or could change what decisions get made.
* Commit only when asked. Only branch if explicitly directed to do so.

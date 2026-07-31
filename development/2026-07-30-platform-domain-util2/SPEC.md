# `find-platform-domains-cloudflare` — Spec & Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Dispatch every code-touching subagent as
> **`psh-implementer`** and every reviewer as **`psh-reviewer`** (CLAUDE.md § Dispatching
> subagents).
>
> **Commit authorization.** CLAUDE.md § Other/General says *"Commit only when asked."* The
> operator gave that authorization for this plan on **2026-07-30**, during the review interview,
> answering the question *"How should the plan handle the live production run and the per-task
> commits?"* with *"STOP before live run; commits pre-authorized."* The `git commit` step ending
> each task below **is** that authorization. It does not extend to branching, pushing, amending,
> or any commit outside these tasks.
>
> **One structural STOP exists** — the head of **Task 7**, before anything touches production
> Cloudflare. Tasks 1–6 are entirely offline and are not gated.
>
> **Lint governance.** `pyproject.toml`'s `[tool.ruff.lint]` block requires a justification
> comment for each new `per-file-ignores` entry *"AND a LEDGER.md entry (until the campaign
> closes)"*. The modularization campaign **is** closed (CLAUDE.md § How this architecture came to
> be), so the LEDGER half no longer applies; the justification comments in Task 1 Step 5 satisfy
> what remains. Stated here so a reader need not re-derive it.

**Goal:** A standalone, deletable utility that writes every Cloudflare DNS **CNAME record whose
target ends in `.pantheonsite.io`** — proxied or not, in every zone of every account the
credentials can see — to `./platform-domains-cloudflare.json`, regenerated in full on every run.

**Architecture:** One executable script at the repo root, `find-platform-domains-cloudflare`,
importing nothing from `psh/`, `check/`, `plugin/`, or `script_context`. It re-implements (by
copying, not importing) the three things it needs from the main program: the `[Cloudflare]`
credential read, the account → zone → DNS-record walk from `plugin/cloudflare/fqdns.py`, and that
module's atomic JSON write. Deletion after Pantheon's CDN migration is `git rm` of the script, its
`.py` symlink and its test file, plus five one-line tooling entries (§11).

**Tech Stack:** Python 3.12+, the `cloudflare` SDK (already declared under this project's
`cloudflare` extra), `tomllib`, `argparse`. No new dependencies. Tests: pytest, `unit` tier,
fully offline, 63 tests.

## Global Constraints

- **Standalone.** The script imports nothing from `psh/`, `check/`, `plugin/`, or
  `script_context`. Copied code lives *in* the script, not in a shared module — deletion must stay
  a `git rm`.
- **Temporary.** Delete after Pantheon completes the Fastly → Pantheon-Cloudflare CDN migration.
  Every file the script touches carries a comment saying so and pointing at §11.
- **Output path:** `./platform-domains-cloudflare.json`, a module-level constant. No `--output`
  flag.
- **Platform suffix:** `.pantheonsite.io` (with the leading dot), a module-level constant. See R4
  for the scoping assumption that carries.
- **Always regenerate.** No existence check, no staleness check, no load-existing path. Every run
  writes the file, including a run that matched nothing (which writes `{}`).
- **Efficiency is explicitly not a goal** (PROMPT). Prefer the simplest correct code at every fork.
- **Measured SDK baseline: `cloudflare` 5.4.0.** Behaviors this spec relies on (R2a's four leak
  routes, R3's pagination and `total_count`) are SDK-internal and were measured, not assumed.
  `pyproject.toml` declares the dependency **unpinned**, so an SDK upgrade is the one external
  change that can invalidate them. §7 therefore includes tests that touch the **real** SDK
  classes, not only the fakes — see §8.10.
- **The lint and type gates apply at every checkpoint, not just at the end.** `./run-tests` runs
  ruff over the whole repo and then pyright, and **gates on both before pytest runs at all**
  (`run-tests`: *"Lint AND type-check BEFORE pytest, and gate on them -- in --fast and full
  alike"*). Every task below therefore introduces only the imports its own code uses, and the
  script's function order matches task order (§3); a task that imported ahead would fail `F401`,
  and one that defined ahead would fail `F821`, and in both cases would never reach its own tests.
  Measured: all five checkpoints lint clean.
- **House style:** 4-space indent, `"""docstrings"""` explaining *why*, `# --` comment banners,
  `allow_abbrev=False` on the parser.

## Requirement vocabulary

- **MUST** / **MUST NOT** / **NEVER** — a violation is a defect; the implementation is wrong.
- **SHOULD** — do it unless there is a stated reason not to, recorded in the code.
- **MAY** — genuinely optional.

**NEVER-block (tests are load-bearing):** a test in §7 **MUST NOT** be deleted, skipped,
`xfail`ed, or weakened to make a change pass. If a test goes red, the change is wrong until proven
otherwise. **NEVER** refresh an assertion to match new output without first establishing that the
new output is correct. **NEVER** print an API response body, at any verbosity, and never include
one in an error message (R6, §6).

## Glossary

| Term | Meaning in this document |
|---|---|
| **platform domain** | A Pantheon-provided hostname ending in `.pantheonsite.io`. R4 states the scoping assumption this carries. |
| **custom domain** | As `CONTEXT.md` defines it — *"a hostname a site owner connected to a site environment"*. Not redefined here; this script sees them from the Cloudflare side. |
| **entry** | One key/value pair in the output file: an FQDN mapped to eight fields (R5). |
| **origin** | The raw `content` of a matching CNAME record. **Same name and type as `fqdns.json`'s field, narrower meaning** — see R5a. |
| **fold** | `collect_entries`, the pure function turning `(zone_id, record)` pairs into entries + warnings. |
| **marker** | A `<{ … }` config substitution. The trailing `>` seen in sample config is decorative and not part of the syntax. |
| **the walk** | `fetch_platform_cnames`: accounts → zones → DNS records. |
| **truncation** | A paginated list that silently returns fewer items than exist. R3's cross-check exists for exactly this. |
| **concurrent change** | An item added or removed *during* the sweep, making counts disagree for a benign reason. R3's single re-read distinguishes it from truncation. |
| **DNS-only** | A record with `proxied: false` — **definitely** false, not merely unknown (R5). Invisible to `fqdns.json`, which is built with `proxied=True`. Add this term to `CONTEXT.md` when the utility lands (PD#11). |
| **the sibling** | `find-platform-domains-dns`, the public-DNS counterpart utility. |

---

## 1. What this is and why

Part of the Pantheon CDN migration. Custom domains that still reach Pantheon's legacy CDN must be
rewritten to Pantheon's new records. The sibling utility `find-platform-domains-dns` finds them
from **public DNS**. That is blind to a **Cloudflare-proxied** record, whose CNAME target is
invisible outside Cloudflare — and `fqdns.json`, the main program's Cloudflare data source, is
built with `proxied=True` and so is blind to every **DNS-only** record.

This script closes the second gap: it inspects **all** records in **all** zones and reports the
CNAMEs pointing at a Pantheon platform domain, whatever their proxy status.

Its output is the input to the record-rewrite work described in `research.md` in this folder.

## 2. Normative behavior

### 2.0 — The pipeline (PD#8)

```
 argv ──▶ build_arg_parser ──▶ options{config, verbose}
                                    │
                                    ▼
                     cloudflare_client(config_path)                    ERROR FUNNEL
                     ├─ tomllib.load ──────── OSError / TOMLDecodeError ────┐
                     ├─ [Cloudflare] present? ─ missing ────────────────────┤
                     ├─ value(key) ─────────── non-str ─────────────────────┤
                     │    └─ resolve_config_value                           │
                     │         └─ resolve_env_marker ─ unset / unbalanced ──┤
                     │                                 / non-env form       │
                     └─ build_client   pins 4 credential fields             │
                                     + pins base_url                        │
                                     + clears _custom_headers   (R2a)       │
                                    │                                       │
                                    ▼                                       │
                     fetch_platform_cnames(client)                          │
                     ├─ read_all(accounts) ───┐                             │
                     ├─ read_all(zones/acct) ─┼─ CloudflareError ───────────┤
                     ├─ zero zones ───────────┴─────────────────────────────┤
                     │                                                      │
                     │  ┌─ per zone ────────────────────────────────────┐   │
                     │  │  read_all(records)                            │   │
                     │  │    walk every page ──▶ items, total_count     │   │
                     │  │    counts match ─────▶ (items, checked=True)  │   │
                     │  │    no total_count ───▶ (items, checked=False) │   │
                     │  │    mismatch ─────────▶ RE-READ once           │   │
                     │  │        self-consistent ▶ concurrent change,   │   │
                     │  │                          keep the re-read     │   │
                     │  │        still off ────── truncated ────────────┼───┤
                     │  └───────────────────┬───────────────────────────┘   │
                     │                      ▼                               │
                     └──────────▶ collect_entries(pairs)                    │
                                  │ CNAME? platform target?                 │
                                  │ first-record-wins; origins accumulate   │
                                  ▼                                         │
                        SweepResult(entries, warnings, accounts,            │
                                    zones, records, zones_checked)          │
                                  │                                         │
             warnings ──▶ stderr ◀┤                                         │
                                  ▼                                         │
                      write_json_atomic(OUTPUT_FILE)                        │
                          └── OSError ────────────────────────────────────  ┤
                                  │                                         │
             summary + coverage ──┤                                         │
             zero-match ATTENTION ┤                                         ▼
                                  ▼                                  StartupError
                              exit 0                                        │
                                                                            ▼
             KeyboardInterrupt ────────────────────▶ exit 130            exit 2
```

Everything on the ERROR FUNNEL becomes a `StartupError`, is printed as one `ERROR:` line, and
exits **2**. Nothing on it reaches exit 1 — see R6.

### R1 — CLI

> ⚠️ **SUPERSEDED by Amendment A1.2** (positional `ZONE ...` and `-o/--output` were added).

```
find-platform-domains-cloudflare [-c CONFIG] [-v]
```

| Flag | Default | Meaning |
|---|---|---|
| `-c`, `--config` | `pantheon-sitehealth-emails.toml` | TOML file to read `[Cloudflare]` credentials from |
| `-v`, `--verbose` | off | per-zone progress with record counts, and any re-read notices, on stderr |

`allow_abbrev=False` (house rule). There are no positional arguments. Verbosity is deliberately a
**boolean**, not the main program's counted `-v/-vv/-vvv` — see §8.9.

### R2 — Credentials

Read the `[Cloudflare]` table from the TOML with `tomllib`, then resolve `<{...}` substitution
markers in the string values with a **copied mini-resolver** supporting exactly the `env` and
`secret env` forms, each with an optional trailing default:

```
<{env NAME}          <{env NAME DEFAULT}
<{secret env NAME}   <{secret env NAME DEFAULT}
```

- Marker syntax is `<{` … `}`. The recognizing regex is copied verbatim from
  `psh/configuration.py:110`.
- Markers are substituted **inside** a value (`re.sub`), so `"prefix<{env X}suffix"` works,
  matching `process_config()`.
- Each credential value **MUST** be type-checked as a `str` *where it is read*. TOML is a typed
  format, so `api_token = true` is a `bool`, which `if api_token:` accepts and the SDK stringifies
  into `Authorization: Bearer True` — the same confusing 401 the marker rule below exists to
  prevent, so the rule **MUST** apply to both input shapes. *(Same defect class as the sibling
  spec's whole-branch review finding C1, applied here before it could ship.)*
- A **non-`env`** substitution (e.g. `<{secret aws …}`) is a `StartupError` naming the config key.
  It is **not** silently passed through: a literal marker sent as an API token would produce a
  confusing 401.
- An **unbalanced quote** in a marker (`<{env FOO don't}`) makes `shlex` raise `ValueError`, which
  **MUST** be converted to a `StartupError`. Left alone it escapes as a raw traceback at exit 1 —
  a code R6 does not use.
- An unset env var with no default is a `StartupError` naming the variable.
- A non-string value passes through `resolve_config_value` untouched; only `str` values are
  scanned. (After the type check above, only `None` ever reaches it.)

**Deliberate divergence from the main engine, documented in the script:** the marker body is
tokenized with `shlex.split()` (whitespace-splitting) rather than the engine's
`list(shlex.shlex(expr, posix=True))`, which also splits on punctuation — turning
`<{env FOO some-default}` into five tokens, which the engine then scores 3 of 5 and reports as
*"no match found for configuration file value"* (`configuration.py:98`, **not** the "unknown
substitution" branch). The two agree on every marker the main program can actually resolve.

`api_token` wins when present and truthy; otherwise both `email` and `api_key` are required.
`enabled` is **not consulted** — the operator ran this script deliberately, and refusing because a
flag aimed at the main program is `false` would be a surprise.

### R2a — Pinning the client against the ambient environment (load-bearing; corrected twice)

The `cloudflare` SDK back-fills any credential argument left as `None` from the environment. It
reads **six** variables, and ambient values reach the wire by **four** routes:

| # | Route | What it does | Closed by |
|---|---|---|---|
| 1 | `auth_headers` (`_client.py:1127`) | returns the **first** of email → key → token → user_service_key, and only that one — so an ambient `CLOUDFLARE_EMAIL` beats a configured token | nulling the unsupplied fields |
| 2 | `default_headers` (`_client.py:1168`) | *separately* adds `X-Auth-Email`/`X-Auth-Key` whenever those attributes are not `None` | nulling the unsupplied fields |
| 3 | `$CLOUDFLARE_CUSTOM_HEADERS` | merged **last** into `default_headers`, overriding 1 and 2 | `client._custom_headers = {}` |
| 4 | `$CLOUDFLARE_BASE_URL` | redirects every request — **sends the configured credential to an arbitrary host** | `base_url=API_BASE_URL` |

Measured on cloudflare 5.4.0. With the credential-field pinning alone (routes 3 and 4 open):

```
URL     : https://evil.example/v4/zones
headers : {'authorization': 'Bearer tok-123',
           'x-auth-email': 'attacker@evil.example', 'x-auth-key': 'evil-key'}
```

With all four closed:

```
URL     : https://api.cloudflare.com/client/v4/zones
auth hdr: {'authorization': 'Bearer tok-123'}
```

**Route 4 is strictly worse than the defect this function was originally written for**: the
credential *leaves the machine* rather than merely failing to authenticate. Routes 3 and 4 were
missed on the first pass and found in round 2 of review (§13).

The test **MUST** assert the *security property* — the URL and headers of the request the SDK
would actually send, with **all six** ambient variables exported — not the attribute state that
implements it. An SDK that captured credentials at construction would leave attribute assertions
green and the defect live.

**Stated residual — the table above is exhaustive for the routes the *SDK* opens, not for the
ambient environment as a whole.** The SDK builds its httpx client with `trust_env=True`
(measured), so `HTTPS_PROXY` mounts a proxy transport and `SSL_CERT_FILE` / `SSL_CERT_DIR`
redirect trust-store resolution. A proxy plus an attacker-controlled CA reaches the same outcome
route 4 is called "strictly worse" for. **Deliberately left open**, because closing it with
`http_client=httpx.Client(trust_env=False)` would also break every legitimate deployment behind a
corporate proxy — a cost this temporary utility should not impose unilaterally. What *is* closed:
an `SSL_CERT_FILE` pointing at a missing path made the constructor raise `FileNotFoundError`,
another unnamed escape to exit 1, now converted to a `StartupError`. If the operator wants
`trust_env=False`, it is a one-line change and a one-line test.

> **Out of scope, report to the operator:** `plugin/cloudflare/client.py`'s `build_client()` has
> **all four** routes open — `Cloudflare(api_token=api_token)` with no pinning of any kind.
> Routes 1–2 are not live today only because U-M's config leaves `api_token` commented out and
> passes `api_email` + `api_key` explicitly, which happens to win route 1. **Route 4 is
> exploitable against the main program today**, regardless of which credential form is
> configured. Fixing it is a separate change with its own test surface (§8.7).
>
> ⚠️ **RESOLVED 2026-07-30 by commit `befb913`, after this was written** —
> `plugin/cloudflare/client.py` now has `pinned_client()`, closing all four routes, verified
> against a real built request with all six ambient variables set hostile. See Amendment A2.

### R3 — The walk, and the truncation guard

`client.accounts.list()` → per account `client.zones.list(account={"id": account.id})` → per zone
`client.dns.records.list(zone_id=zone.id)`.

- **No `proxied=` filter and no `type=` filter.** Every record in every zone is fetched and
  inspected; the CNAME and suffix tests happen in this script. This is literally what "consider
  all DNS records in all Cloudflare zones" asks for, and per the PROMPT no work goes into making
  it faster. (If a run becomes painful, `type="CNAME"` on the records list call is the one-word
  change — §8.3.)
- **All three endpoints paginate**, all returning `SyncV4PagePaginationArray`. Verified against
  the installed SDK: `next_page_info` asks for `page = last + 1` (`pagination.py:104`),
  `has_next_page` stops when a page comes back empty (`_base_client.py:186`), and
  `BaseSyncPage.__iter__` walks **every** page (`_base_client.py:256`). This is page-number
  pagination, **not** the opaque-cursor shape that produced the Pantheon API's silent "returns
  page 1 again" bug (CLAUDE.md records that one), so the SDK's own loop is trusted to terminate.
- **Every list is de-duplicated by id (MUST).** Measured on the first live sweep: the SDK
  paginates by page *number*, so when rows shift between page fetches — routine in a zone being
  actively written — the same record returns on two pages while another is stepped over. On an
  18,848-record zone this produced 2 duplicates and 2 misses. Duplicates must not reach the fold,
  where they would append one record's origin twice and raise a **false** R7 duplicate-name
  warning.
- **All three are cross-checked (MUST)** by `read_all`, comparing the **unique** item count
  against Cloudflare's own `total_count`.
  `V4PagePaginationArrayResultInfo` declares only `page`/`per_page`, but its `model_config` is
  `extra="allow"`, so `total_count` survives as `model_extra` (verified). Guarding records alone
  would be incoherent: a short **zone** list silently omits every record in the missing zones —
  strictly worse than a short record list — and the zero-zones rule below only catches the
  degenerate case.
- **A shortfall triggers one re-read, UNIONED with the first, and is then a WARNING — never
  fatal.** A second walk steps over different rows, so the union is more complete than either read
  alone and usually closes the gap. If items are still missing, the run says which list and by how
  many, and **still writes the file**. Aborting was the original design and it was **wrong**: the
  first live sweep died at exit 2 over 2 records missed in one zone out of 187, and a paginated
  walk of a continuously-written zone may never be exactly complete, so aborting would mean this
  utility never produces output at all (§13, live run). **The notice prints at default
  verbosity**, not under `-v`.
- **Counting unique ids is what makes the check meaningful.** Raw item count fails in *both*
  directions, both measured on the same zone: 18840 items vs `total_count` 18838 → a false
  "truncated" abort; and 18848 items vs `total_count` 18848 → a false *pass*, because 2 duplicates
  and 2 misses cancelled out exactly. Unique counting removes the false positive and closes the
  false negative.
- **Stated residual:** a `total_count` derived from the same incomplete query would agree with a
  short read and be accepted. The check catches a disagreement between count and content, not a
  server that is consistently wrong.
- **When `total_count` is absent the check no-ops** rather than guessing, so it can never abort a
  healthy sweep. **This applies to BOTH reads**: a re-read that comes back complete but without a
  `total_count` returns its items and is counted as *unchecked*. Guessing there aborted a healthy
  sweep while reporting `truncated … of None` (§13, round 3).
- **The guard reports its own liveness for every list it reads** — record lists, per-account zone
  lists, and the account list — because a guard that silently never ran looks exactly like one
  that ran and found nothing wrong (§6).
- **Stated residual:** the re-read accepts any second read that agrees with **its own**
  `total_count`. A truncation whose `total_count` is derived from the same truncated query would
  be self-consistent and accepted as a concurrent change. The guard therefore catches a
  *disagreement between count and content*, not a server lying consistently. Both reads' counts
  appear in the notice so an operator can judge; §14 Q3 asks whether any fired.
- Any `cloudflare.CloudflareError` → `StartupError` (exit 2), rendered by `api_error_text`, which
  **NEVER** includes the response body (R6).
- **Zero zones is fatal** (copied from `fqdns.py`): with the scope missing, "no zones" and "no
  matching records" produce an identical empty file. The message names **both** `Account:Read`
  and `DNS:Read` — an accounts list that comes back empty yields zero zones just as a missing
  `DNS:Read` does.
- Zero matching CNAMEs is **not** fatal — it writes `{}` and says so loudly on stderr.
- Records are read **one zone at a time** rather than one record at a time: a re-read must be able
  to replace a whole zone's list, and the largest single zone is trivial memory next to the whole
  organization's records.

### R4 — The match

A record is kept when **both** hold:

1. `record.type == "CNAME"`, and
2. `normalize(record.content).endswith(".pantheonsite.io")`

where `normalize` is copied verbatim from the sibling: lowercase, strip whitespace, strip the
trailing root dot. Proxy status is **irrelevant to the match** — that is the entire point of this
script versus `fqdns.json`.

**Scoping assumption, stated as one:** `.pantheonsite.io` is the *only* platform suffix matched,
per PROMPT line 7. Pantheon's legacy `*.gotpantheon.com` hostnames are **not** covered, and grep
finds no occurrence of that domain anywhere in this repo. If any custom domain still CNAMEs there,
this sweep reports a clean result for it — §14 Q7.

Consequences pinned in tests: `notpantheonsite.io` does not match (the leading dot in the constant
is what rejects it); the bare apex `pantheonsite.io` does not match; an **A** record whose content
reads as a platform domain does not match; a **DNS-only** CNAME **does** match.

### R5 — Output format

`./platform-domains-cloudflare.json`, a JSON object keyed by the **normalized** FQDN, `indent=4`,
`sort_keys=True`, trailing newline — the same serialization `write_fqdns_atomic` uses.

```json
{
    "example1.cdn-dev.it.umich.edu": {
        "comment": "migrated 2026-07",
        "origins": [
            "live-umich-example1.pantheonsite.io"
        ],
        "proxied": true,
        "record_id": "9f0e1b2c3d4e5f60718293a4b5c6d7e8",
        "settings": {
            "flatten_cname": false,
            "ipv4_only": null,
            "ipv6_only": null
        },
        "tags": [],
        "ttl": 1,
        "zone_id": "abc123def456"
    }
}
```

- `record_id`, `proxied`, `ttl`, `comment`, `tags`, `settings` exist because `research.md` shows
  the downstream batch rewrite needs the record id for `deletes` and `proxied` on re-creation, and
  its **reverse** direction hardcodes `"ttl": 1` and would otherwise silently discard an explicit
  TTL, operator comments, tags, and `settings.flatten_cname`.
- **`settings` MUST be `.model_dump(mode="json")`ed.** It is a pydantic model
  (`cloudflare.types.dns.cname_record.Settings`); `json.dump` cannot serialize one. Verified: an
  un-dumped entry raises `TypeError` at write time — after the whole walk.
- **First-record-wins** for every scalar; `origins` accumulates, so a name matching more than once
  stays visible in the file and not only in the warning.
- **`proxied` is stored verbatim and MAY be `null`.** It is `Optional[bool]` on every record
  model, and `research.md` is explicit that *"`proxied: true` is the load-bearing field in both
  directions. A record created DNS-only would take the hostname out of certificate service"*. An
  unknown coerced to `false` would both inflate the headline DNS-only count and instruct a
  rewriter to re-create a proxied hostname unproxied — a TLS outage caused by an unreported
  coercion. The DNS-only tally counts `proxied is False` only, and any `null` is named in an
  `ATTENTION:` line. A rewriter **MUST NOT** treat `null` as `false`.
- `origins` entries are the **raw** `record.content` as Cloudflare returned it — the raw string is
  what a rewriter compares against.
- **Freshness is the file's mtime and nothing else.** The file drives a *destructive* rewrite
  (`deletes` in `research.md`), and a record can be edited between generation and the batch. The
  file carries no capture timestamp or version, so the rule is: **regenerate immediately before
  any rewrite**, and never feed a rewriter a file you did not just produce. §14 Q8 asks the
  rewriter to state its own staleness policy.

### R5a — Divergences from the PROMPT, stated as divergences

PROMPT.md line 8 asks for *"the same fields/stucture as `./fqdns.json`"*. Three deliberate
departures, all approved by the operator during review on 2026-07-30:

| Departure | Why | Consequence to respect |
|---|---|---|
| Six extra value fields | Without them the rewrite must re-list every zone, and its reverse direction loses TTL / comment / tags / flatten_cname | Task 7 Step 2's key-set assertion pins the full set |
| Keys are `normalize()`d; `fqdns.py` keys by the **raw** `record.name` | Case and trailing-dot stability | Any comparison against `fqdns.json` keys **must normalize both sides** — Task 7 Step 3 does, and would otherwise report phantom "missing" entries |
| `origins` keeps the same name and type but has a **narrower meaning** | `fqdns.py:114-120` collects the content of **every proxied record of any type** at a name — the live `fqdns.json` shows IP addresses in `origins`. This file's holds only matching platform-CNAME targets | A consumer reading both files with one code path will be wrong; the CLAUDE.md subsection says so too |

### R6 — Exit codes and streams

| Code | Meaning |
|---|---|
| 0 | the output file was written (including an empty `{}`) |
| 2 | could not complete: config unreadable / not TOML **/ not UTF-8**, no `[Cloudflare]` section, a non-`str` credential, an unresolvable / malformed / unsupported substitution, missing credentials, any `cloudflare.CloudflareError`, zero zones, or an `OSError` writing the output file. **An incomplete list is NOT here** — it warns and the file is still written (R3) |
| 130 | interrupted (`KeyboardInterrupt`) |
| 120 | **not produced by this program.** The interpreter's shutdown flush of a doomed **stdout** (argparse's usage / `--help`) *or* **stderr** exits 120 over the return value. Measured. Accepted and not guarded — §8.4. Listed so the table is exhaustive. |

There is deliberately **no exit 1**. The sibling reserves 1 for "completed with indeterminates"
because a DNS lookup can be indeterminate; a Cloudflare list call either returns or raises, so
this script has no partial-answer state. **Holding that line takes explicit work**, and two
measured paths escaped it in the first draft: an `OSError` from the write (landing *after* the
whole multi-minute walk) and a `ValueError` from `shlex.split` on an unbalanced quote — and a
third in round 3: `tomllib.load` decodes the bytes itself, so a non-UTF-8 config raises
`UnicodeDecodeError`, which is **not** a `TOMLDecodeError`. That one is fixed by widening the
clause to their common base, `ValueError` — closing the *class* rather than adding a third
instance. All three are named conversions to `StartupError`, all three tested (§13).

**What this table does not claim:** an *unexpected* exception still exits 1 with a traceback.
That is the deliberate loud-crash path — the taxonomy covers every failure the program
*anticipates*, and anything else is a bug that should stay visible as one rather than be
swallowed into a tidy exit code.

**stdout carries only argparse's usage / `--help` text.** All operator output — warnings, `-v`
lines, the summary, errors — goes to stderr; the *result* is the file. The sibling's doomed-stream
detach guards are **not** copied (§8.4).

**NEVER print an API response body.** `APIStatusError.__str__` is `"Error code: NNN - {body}"`; a
DNS-record body echoes record contents and an auth-failure body can echo the credential.
`api_error_text(e)` renders `"{ClassName}: HTTP {status}"` when a status code is present, else
`"{ClassName}: {e}"` — and §7 tests it against a **real** SDK exception, because if `status_code`
were ever renamed, that fallback *is* the leak.

The summary, on stderr, on success:

```
Wrote 12 platform-domain CNAMEs (3 DNS-only, invisible to fqdns.json) from 12431 records in 43 zones in 2 account(s) to platform-domains-cloudflare.json.
Truncation cross-check active for 41 of 43 zones.
```

The **DNS-only count** is part of the summary, not something an operator computes afterwards — it
is the number saying how much this script found that `fqdns.json` structurally cannot.

### R7 — Duplicate-name warnings

When a name already in the map is matched again, print to stderr — **every** duplicate, not only
a cross-zone one. The file keeps one `record_id` of two and feeds a *destructive* rewrite, so
silence is the wrong default even for the same-zone case, which the Cloudflare API should make
unreachable (a name may hold at most one CNAME) and which is therefore a signal worth seeing.

Warnings are collected during the fold and printed **before** the file is written, so an operator
watching stderr sees them even if the write then fails.

### R8 — Atomic write

`write_fqdns_atomic` from `plugin/cloudflare/fqdns.py`, copied and renamed `write_json_atomic`:
`tempfile.mkstemp(dir=…)` in the target's directory → write → restore a umask-based mode (mkstemp
creates 0600) → `os.replace()` → on any `BaseException`, unlink the temp file and re-raise. The
`# noqa: PTH…` comments come with it: ruff's `select = ALL` includes the pathlib rules, and this
function's same-filesystem `os.replace` is the behavior being specified, not a style choice.

An interrupted run leaves the previous file byte-intact; it never leaves a truncated one.

## 3. Module layout of the script

**File order matches task order.** This is load-bearing, not cosmetic: each task's checkpoint
lints the file as it then stands, so a definition placed ahead of its task fails `F821`, and an
import placed ahead of its use fails `F401` (measured — §13, round 2).

| Symbol | Task | Responsibility |
|---|---|---|
| module docstring, constants, `StartupError`, `normalize`, `is_platform_domain` | 1 | R4 |
| `resolve_env_marker`, `resolve_config_value`, `build_client`, `cloudflare_client` | 2 | R2, R2a |
| `plain`, `collect_entries` | 3 | R4, R5, R7 |
| `write_json_atomic` | 4 | R8 |
| `expected_record_count`, `read_all`, `api_error_text`, `SweepResult`, `list_zones`, `fetch_platform_cnames`, `build_arg_parser`, `main`, `__main__` guard | 5 | R3, R6, R1 |

The finished top-of-file import block, as the target state the five per-task additions build up to:

```python
import argparse
import json
import os
import re
import shlex
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import NamedTuple

import cloudflare  # for cloudflare.CloudflareError
from cloudflare import Cloudflare
```

## 4. Seams under test — named and agreed

Agreed here, before implementation, per the Spine's bar (*"The spec is the only place a seam can
be agreed"*).

| Seam | How a test reaches it | Why it is a seam |
|---|---|---|
| the script module itself | `SourceFileLoader`, **fresh per test** (`fpc` fixture) | The script has no `.py` extension; fresh-per-test is what makes module-attribute patching safe |
| `os.environ` | `monkeypatch.setenv` / `delenv` | The only ambient input to credential resolution |
| the config file | a TOML written into `tmp_path` | Real `tomllib` parse, no fake |
| **the Cloudflare client** | `FakeCloudflareClient` / `FakePage`, passed **as a parameter** — never patched | `fetch_platform_cnames(client, …)` takes the client; injection beats patching |
| **the request the SDK would send** | `client._build_request(...)` — offline, performs no I/O | The only way to assert R2a's property rather than its implementation |
| **the real SDK classes** | imported directly in three tests: `V4PagePaginationArrayResultInfo`, `SyncV4PagePaginationArray`, `PermissionDeniedError` | The fakes cannot notice an SDK change; these can (§8.10) |
| `cloudflare_client` / `fetch_platform_cnames` / `write_json_atomic`, as `main()` calls them | `monkeypatch.setattr(fpc, …)` | Safe *only* because the module is fresh per test |
| the filesystem | `tmp_path` + `monkeypatch.chdir` (`OUTPUT_FILE` is relative) | Keeps the repo clean and makes the write assertable |
| the real Cloudflare API | **NEVER** touched by any test | Every test in §7 is offline |

`FakePage` deliberately has **no `result` attribute**: an implementation that read `page.result`
(page 1 only) instead of iterating the page would fail loudly rather than silently pass. One test
asserts the *real* class **does** have `result`, so that trap is known to be real rather than
imagined.

## 5. Shadow paths (PD#3), traced

Happy path plus nil / empty / upstream-error, for each new flow.

| Flow | Happy | Nil input | Empty / zero-length | Upstream error |
|---|---|---|---|---|
| Credential resolution | marker → env value → pinned client | key absent → `None` → falls through to email+key, or `StartupError` if neither | env var set but **empty** → `""` → falsy → treated as absent, matching `get_env`'s `name in os.environ` semantics | unset var, unbalanced quote, non-`env` form, non-`str` value → `StartupError` |
| The walk | accounts → zones → records, each cross-checked | `result_info` absent → `expected is None` → cross-check no-ops and the zone is counted as unchecked | **zero accounts** → zero zones → fatal; **zero zones** → fatal; a zone with **zero records** → contributes nothing, not an error | `CloudflareError` → `StartupError` via `api_error_text`; count mismatch → one re-read → concurrent change (continue), no `total_count` on the re-read (continue, counted unchecked), or a second disagreement (fatal, no file) |
| The fold | CNAME + platform target → entry | `content` `None` → skipped; `settings`/`proxied`/`ttl` absent or `None` → stored as `null`, **never coerced** (R5) | zero pairs → `({}, [])`, reported with the zero-match `ATTENTION:` | n/a (pure; upstream errors surface from the generator it consumes) |
| The write | temp → chmod → `os.replace` | n/a | `{}` writes `{}` plus a newline — a real, intentional result | `OSError` → temp unlinked, previous file byte-intact, converted to `StartupError` at the call site. A `TypeError` mid-serialize is **not** converted, and is **unreachable**: every stored value comes from the SDK's JSON parsing, and the one model (`settings`) goes through `plain()`, which a test pins |

## 6. Observability (PD#5)

| Level | Emits |
|---|---|
| default | duplicate-name `ATTENTION:` warnings; **every re-read notice** (a re-read means the data moved mid-sweep); the summary (entries, **DNS-only count**, records read, zones, accounts, path); the **truncation cross-check coverage** line, covering all three list kinds; an `ATTENTION:` naming any entry whose `proxied` is `null`; the zero-match `ATTENTION:`; one `ERROR:` line on failure |
| `-v` | additionally, per zone: `[n/total] zone <name> -- N records`, marked `(total_count unavailable, not cross-checked)` when the guard could not run; plus a notice whenever a re-read is triggered and how it resolved |

Rules:

- **NEVER** an API response body, at any level (R6).
- A truncation is a **hard abort naming both counts from both reads**, not a line to notice.
- **The guard reports its own coverage** at default verbosity, over **every** paginated list it
  read — `Completeness cross-check: 192 of 192 paginated lists verified complete, 0 short, 0
  unverifiable.` Reporting only the record lists would leave the zone-list check silently
  unaccounted for. This is what makes §14 Q1 answerable; a guard whose liveness is invisible is
  not a guard.
- **A short list is named individually**, with the count and the consequence spelled out —
  *"Any platform-domain CNAME among them is NOT in this file."*
- The **runtime is unknown until the first live run**, is recorded in §12, and is then added to
  the CLAUDE.md subsection — the sibling documents "~38 minutes", and an operator starting a long
  quiet run deserves the same here.
- Rejected: counted `-v/-vv/-vvv` — §8.9.

## 7. Test plan

One file, `tests/unit/test_find_platform_domains_cloudflare.py`, `pytestmark = pytest.mark.unit`,
fully offline, **63 tests**. Seams per §4.

**These counts and outcomes are measured, not predicted.** The script and test file were built to
completion in a scratch directory, then **staged back task by task** — each stage linted with the
repo's ruff config and run under pytest:

```
Task 1: lint clean    8 passed
Task 2: lint clean   25 passed
Task 3: lint clean   37 passed
Task 4: lint clean   40 passed
Task 5: lint clean   63 passed
```

and on the finished file: `ruff check` clean; **9 × T201 with the two per-file-ignores entries
removed**, so Task 5 Step 6's check is red-capable; `pyright` standard `0 errors, 0 warnings`.
The code blocks in Tasks 1–5 below were extracted **from those verified files**, not retyped.

Covered: the marker resolver (all four forms, missing var, unbalanced quote, non-`env`
substitution, literal and non-string passthrough); credential selection **including R2a's security
property asserted on the real request with all six ambient variables exported**, plus the
`base_url` route and the non-`str` type check; the match rule (all five reject cases); the fold
(all eight fields, pydantic `settings` serialization, missing optional attributes,
first-record-wins, both duplicate warnings); the atomic write (creates, overwrites, no temp left,
survives a mid-serialize failure); the walk (multi-page consumption, re-read-then-continue,
re-read-then-abort, truncated **zone** list, absent-`total_count` coverage reporting, zero zones,
API error wrapping); **three tests against the real SDK classes** (§8.10); and **`main()`'s three
exit codes** plus the unwritable-output path.

Not covered, by decision (§8.5): any live-API test.

---

## Task 1: Scaffold, tooling, and the match rule

**Files:**
- Create: `find-platform-domains-cloudflare` (executable, `chmod +x`)
- Create: `find-platform-domains-cloudflare.py` → symlink to the above
- Create: `tests/unit/test_find_platform_domains_cloudflare.py`
- Modify: `pyproject.toml` (two `[tool.ruff.lint.per-file-ignores]` entries, one
  `[tool.pyright].include` entry)
- Modify: `.claude/hooks/ruff-check.sh` (one `case` arm)

**Interfaces:**
- Consumes: nothing.
- Produces: `PLATFORM_SUFFIX`, `OUTPUT_FILE`, `DEFAULT_CONFIG`, `API_BASE_URL`, `MARKER_RE`,
  `StartupError`, `normalize(name) -> str`, `is_platform_domain(name) -> bool`.

**Imports this task introduces:** script — `re` only. Tests — `importlib.util`, `types`,
`SourceFileLoader`, `Path`, `pytest`. Nothing else, or the checkpoint fails `F401` before pytest
runs.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_find_platform_domains_cloudflare.py`:

```python
"""Offline tests for the find-platform-domains-cloudflare utility (SPEC section 7).

The script has no .py extension, so it is loaded with the SourceFileLoader idiom the suite
already uses for standalone scripts and check/plugin modules (see
tests/unit/test_find_platform_domains_dns.py).  It is loaded FRESH PER TEST so no module-level
state leaks between tests -- which is also what makes monkeypatching module attributes safe in
the main() tests at the bottom (SPEC section 4, seams).

Imports: each task ADDS to the block below, in the task that first needs the name.  Editing the
top block is fine; adding an import further down the file is what ruff's E402 forbids, and E402
is not in the tests/** ignore list.

TEMPORARY, deleted with the script after the Pantheon CDN migration -- see
development/2026-07-30-platform-domain-util2/SPEC.md section 11.
"""
import importlib.util
import types
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SCRIPT = Path(__file__).resolve().parent.parent.parent / "find-platform-domains-cloudflare"


@pytest.fixture
def fpc():
    """The utility, loaded fresh.  Its entry point is __main__-guarded, so import runs nothing."""
    loader = SourceFileLoader("find_platform_domains_cloudflare_probe", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def record(**overrides):
    """A stand-in for a cloudflare RecordResponse; the code under test only reads attributes."""
    fields = {"type": "CNAME", "name": "www.example.edu", "id": "rec-1",
              "content": "live-umich-example1.pantheonsite.io", "proxied": True,
              "ttl": 1, "comment": None, "tags": [], "settings": None}
    fields.update(overrides)
    return types.SimpleNamespace(**fields)


# --- Task 1: the match rule ------------------------------------------------------------------

def test_normalize_strips_case_whitespace_and_the_root_dot(fpc):
    assert fpc.normalize("  LIVE-Umich-X.PantheonSite.IO.  ") == "live-umich-x.pantheonsite.io"


@pytest.mark.parametrize("name", [
    "live-umich-example1.pantheonsite.io",
    "LIVE-UMICH-EXAMPLE1.PANTHEONSITE.IO",
    "live-umich-example1.pantheonsite.io.",
])
def test_is_platform_domain_accepts_platform_hostnames(fpc, name):
    assert fpc.is_platform_domain(name) is True


@pytest.mark.parametrize("name", [
    "notpantheonsite.io",          # the leading dot in PLATFORM_SUFFIX is what rejects this
    "pantheonsite.io",             # the bare apex is not a site's platform domain
    "www.example.edu",
    "live-umich-example1.pantheonsite.io.evil.example",
])
def test_is_platform_domain_rejects_everything_else(fpc, name):
    assert fpc.is_platform_domain(name) is False
```

- [ ] **Step 2: Run the tests to verify they fail — for the right reason**

Run: `./run-tests --fast tests/unit/test_find_platform_domains_cloudflare.py -v`

Expected: **8 errors**, each a `FileNotFoundError` raised by the `fpc` fixture. Collection itself
**succeeds** — `SCRIPT` is only a `Path` at module level and nothing touches the filesystem until
the fixture runs. Do **not** expect a collection error.

- [ ] **Step 3: Create the script**

Create `find-platform-domains-cloudflare`:

```python
#!/usr/bin/env python
"""Write every Cloudflare CNAME record pointing at a Pantheon platform domain to JSON.

TEMPORARY.  Delete after Pantheon's Fastly -> Pantheon-Cloudflare CDN migration completes; see
development/2026-07-30-platform-domain-util2/SPEC.md section 11 for the checklist.

Standalone by design: this imports nothing from psh/, check/, plugin/ or script_context, so most
of removing it is `git rm` of the script, its .py symlink and its test file.  The credential
read, the account/zone/record walk and the atomic write are COPIES of plugin/cloudflare/fqdns.py
and plugin/cloudflare/client.py; normalize()/is_platform_domain() are copies of
find-platform-domains-dns.

Unlike fqdns.json, this considers ALL records in ALL zones -- not just proxied ones -- and keeps
only CNAMEs whose target ends in .pantheonsite.io.  The output file is regenerated in full on
every run, whatever its age.

Output: ./platform-domains-cloudflare.json, keyed by FQDN, values {zone_id, origins, record_id,
proxied, ttl, comment, tags, settings}.  stdout carries ONLY argparse's usage/--help text; every
operator message -- warnings, progress, the summary, errors -- goes to stderr, and the result is
the file.  Exit 0 = file written, 2 = could not complete, 130 = interrupted.

Requires: the `cloudflare` SDK (declared under this project's `cloudflare` extra, which the
documented `uv pip install .[mysql,aws,cloudflare]` setup line installs) and Cloudflare
credentials in the [Cloudflare] section of the config file.
"""
import re

PLATFORM_SUFFIX = ".pantheonsite.io"   # the leading dot is load-bearing: it rejects
                                       # "notpantheonsite.io"
OUTPUT_FILE = "platform-domains-cloudflare.json"
DEFAULT_CONFIG = "pantheon-sitehealth-emails.toml"
API_BASE_URL = "https://api.cloudflare.com/client/v4"   # pinned; see build_client

# Copied verbatim from psh/configuration.py.  A marker is "<{ ... }" -- the trailing ">" that
# appears in the sample config is decorative and NOT part of the syntax.
MARKER_RE = re.compile(r"<\{(.*?)(?<!\\)}")


class StartupError(Exception):
    """Anything that stops the sweep from starting or completing (exit 2)."""


def normalize(name):
    """Lowercase, strip whitespace and the trailing root dot.  Copied from
    find-platform-domains-dns."""
    return str(name).strip().rstrip(".").lower()


def is_platform_domain(name):
    """True for a Pantheon-provided *.pantheonsite.io hostname."""
    return normalize(name).endswith(PLATFORM_SUFFIX)
```

- [ ] **Step 4: Make it executable and create the symlink**

```bash
cd /workspace
chmod +x find-platform-domains-cloudflare
ln -s find-platform-domains-cloudflare find-platform-domains-cloudflare.py
```

`chmod +x` is **required, not cosmetic**: ruff's `EXE001` ("shebang is present but file is not
executable") fires without it, and `EXE001` is in no ignore list. Measured.

- [ ] **Step 5: Add the tooling entries**

In `pyproject.toml`, in `[tool.ruff.lint.per-file-ignores]`, immediately after the two existing
`find-platform-domains-dns` entries:

```toml
"find-platform-domains-cloudflare.py" = ["T201"]  # a CLI tool: print IS its operator output
    # (stderr = warnings, progress, summary; the result is the JSON file).  Temporary, deleted
    # with the script after the Pantheon CDN migration -- see
    # development/2026-07-30-platform-domain-util2/SPEC.md section 11.
"find-platform-domains-cloudflare" = ["T201"]  # the extension-less real file the .py entry
    # above symlinks to -- .claude/hooks/ruff-check.sh hands ruff THIS path (an edit lands on the
    # real file, not the symlink), and per-file-ignores is keyed on the path ruff is given, so
    # the .py entry alone leaves the hook's own invocation reporting T201.  Same justification
    # and deletion condition as the .py entry above.
```

In `pyproject.toml`, `[tool.pyright]`, extend `include`:

```toml
include = ["psh", "find-platform-domains-dns.py", "find-platform-domains-cloudflare.py"]
```

In `.claude/hooks/ruff-check.sh`, add one arm to the extension-less `case` (after the
`find-platform-domains-dns` arm):

```sh
    "$REPO_ROOT/find-platform-domains-cloudflare") ;;
```

and extend that block's comment to name both temporary utilities.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `./run-tests --fast tests/unit/test_find_platform_domains_cloudflare.py -v`
Expected: **8 passed**, with the repo-wide ruff and pyright gates green (measured clean at this
stage).

- [ ] **Step 7: Commit**

```bash
git add find-platform-domains-cloudflare find-platform-domains-cloudflare.py \
        tests/unit/test_find_platform_domains_cloudflare.py pyproject.toml \
        .claude/hooks/ruff-check.sh
git commit -m "feat(find-platform-domains-cloudflare): scaffold the utility and its match rule"
```

> The "does the lint gate actually see this file" check is **not** here. At this point the script
> contains no `print`, so `ruff check` passes identically whether or not Step 5 was done — a green
> check that cannot go red. It moves to Task 5 Step 6, where the `print` calls exist (§13).

---

## Task 2: Credential resolution and the pinned client

**Files:**
- Modify: `find-platform-domains-cloudflare` (append after `is_platform_domain`)
- Test: `tests/unit/test_find_platform_domains_cloudflare.py` (append; no new top-level imports)

**Interfaces:**
- Consumes: `MARKER_RE`, `StartupError`, `API_BASE_URL` (Task 1).
- Produces: `resolve_env_marker(expr, where) -> str`, `resolve_config_value(value, where)`,
  `build_client(**creds) -> Cloudflare`, `cloudflare_client(config_path) -> Cloudflare`.

**Imports this task introduces:** script — `os`, `shlex`, `tomllib`, `from pathlib import Path`,
`from cloudflare import Cloudflare`. Tests — none.

- [ ] **Step 1: Write the failing tests**

Append to the test file:

```python
# --- Task 2: credentials ---------------------------------------------------------------------

AMBIENT_CLOUDFLARE_VARS = {
    "CLOUDFLARE_API_TOKEN": "ambient-token",
    "CLOUDFLARE_API_KEY": "ambient-key",
    "CLOUDFLARE_EMAIL": "ambient@example.edu",
    "CLOUDFLARE_API_USER_SERVICE_KEY": "ambient-usk",
    "CLOUDFLARE_BASE_URL": "https://evil.example/v4",
    "CLOUDFLARE_CUSTOM_HEADERS": "X-Auth-Email: attacker@evil.example\nX-Auth-Key: evil-key",
}


def write_config(tmp_path, body):
    """A config file containing just a [Cloudflare] table."""
    path = tmp_path / "config.toml"
    path.write_text(f"[Cloudflare]\n{body}\n")
    return str(path)


def sent_request(client):
    """The request the SDK would actually send.  Offline: _build_request performs no I/O."""
    from cloudflare._models import FinalRequestOptions
    return client._build_request(FinalRequestOptions(method="get", url="/zones"))


def test_resolve_config_value_passes_literals_and_non_strings_through(fpc):
    assert fpc.resolve_config_value("plain-literal", "where") == "plain-literal"
    assert fpc.resolve_config_value(True, "where") is True
    assert fpc.resolve_config_value(None, "where") is None


@pytest.mark.parametrize("marker", ["<{env CF_TEST_VAR}", "<{secret env CF_TEST_VAR}"])
def test_resolve_config_value_reads_the_environment(fpc, monkeypatch, marker):
    monkeypatch.setenv("CF_TEST_VAR", "from-the-environment")
    assert fpc.resolve_config_value(marker, "where") == "from-the-environment"


def test_resolve_config_value_substitutes_inside_a_larger_string(fpc, monkeypatch):
    monkeypatch.setenv("CF_TEST_VAR", "middle")
    assert fpc.resolve_config_value("a<{env CF_TEST_VAR}z", "where") == "amiddlez"


def test_resolve_config_value_uses_the_default_when_the_variable_is_unset(fpc, monkeypatch):
    monkeypatch.delenv("CF_TEST_VAR", raising=False)
    assert fpc.resolve_config_value("<{secret env CF_TEST_VAR fallback}", "where") == "fallback"


def test_resolve_config_value_reports_an_unset_variable_with_no_default(fpc, monkeypatch):
    monkeypatch.delenv("CF_TEST_VAR", raising=False)
    with pytest.raises(fpc.StartupError) as caught:
        fpc.resolve_config_value("<{env CF_TEST_VAR}", "config.toml [Cloudflare].api_key")
    assert "CF_TEST_VAR" in str(caught.value)
    assert "config.toml [Cloudflare].api_key" in str(caught.value)


def test_resolve_config_value_rejects_a_substitution_it_cannot_resolve(fpc):
    with pytest.raises(fpc.StartupError) as caught:
        fpc.resolve_config_value("<{secret aws cloudflare/token}", "where")
    assert "secret aws" in str(caught.value)
    # The rest of the body is withheld on purpose: an <{env NAME DEFAULT} default can be a
    # literal credential, and this message reaches stderr and any operator log.
    assert "cloudflare/token" not in str(caught.value)


def test_resolve_config_value_names_a_malformed_substitution(fpc):
    """An unbalanced quote makes shlex raise ValueError, which escaped as a raw traceback at
    exit 1 -- a code SPEC section R6 does not use (adversarial review round 1, finding 3)."""
    with pytest.raises(fpc.StartupError) as caught:
        fpc.resolve_config_value("<{env FOO don't}", "config.toml [Cloudflare].api_key")
    assert "config.toml [Cloudflare].api_key" in str(caught.value)


def test_cloudflare_client_prefers_the_api_token(fpc, tmp_path, monkeypatch):
    monkeypatch.setenv("CF_TEST_TOKEN", "tok-123")
    path = write_config(tmp_path, 'api_token = "<{secret env CF_TEST_TOKEN}"\n'
                                  'email = "someone@example.edu"\napi_key = "k-456"')
    client = fpc.cloudflare_client(path)
    assert client.api_token == "tok-123"


def test_cloudflare_client_sends_only_the_configured_credential(fpc, tmp_path, monkeypatch):
    """SPEC R2a, asserted as the security property rather than the attribute state implementing it.

    The SDK reads six ambient variables; ALL of them are exported here, so a regression that
    dropped any one field from the pin goes red.  Measured against cloudflare 5.4.0; an SDK that
    captured credentials at construction, or added a fifth route, would make this go red -- which
    is the point, since pyproject declares the dependency unpinned.
    """
    for name, value in AMBIENT_CLOUDFLARE_VARS.items():
        monkeypatch.setenv(name, value)
    path = write_config(tmp_path, 'api_token = "tok-123"')
    client = fpc.cloudflare_client(path)

    assert client.auth_headers == {"Authorization": "Bearer tok-123"}
    request = sent_request(client)
    assert str(request.url).startswith("https://api.cloudflare.com/client/v4/")
    leaked = set(request.headers.values()) & set(AMBIENT_CLOUDFLARE_VARS.values())
    assert leaked == set(), f"ambient credentials reached the wire: {leaked}"


def test_cloudflare_client_ignores_an_ambient_base_url(fpc, tmp_path, monkeypatch):
    """$CLOUDFLARE_BASE_URL would otherwise send the configured token to an arbitrary host --
    strictly worse than the defect the credential pin was written for (round 2, finding 3)."""
    monkeypatch.setenv("CLOUDFLARE_BASE_URL", "https://evil.example/v4")
    path = write_config(tmp_path, 'api_token = "tok-123"')
    request = sent_request(fpc.cloudflare_client(path))
    assert "evil.example" not in str(request.url)


def test_cloudflare_client_falls_back_to_email_and_key(fpc, tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "ambient-token")
    path = write_config(tmp_path, 'email = "someone@example.edu"\napi_key = "k-456"')
    client = fpc.cloudflare_client(path)
    assert client.api_email == "someone@example.edu"
    assert client.api_key == "k-456"
    assert client.api_token is None
    assert "ambient-token" not in set(sent_request(client).headers.values())


def test_cloudflare_client_requires_both_email_and_key(fpc, tmp_path):
    path = write_config(tmp_path, 'email = "someone@example.edu"')
    with pytest.raises(fpc.StartupError) as caught:
        fpc.cloudflare_client(path)
    assert "api_token" in str(caught.value)


def test_cloudflare_client_rejects_a_non_string_credential(fpc, tmp_path):
    """TOML is typed: `api_token = true` would otherwise reach the SDK and be stringified into
    `Authorization: Bearer True` -- the confusing 401 the marker rules exist to prevent."""
    path = write_config(tmp_path, "api_token = true")
    with pytest.raises(fpc.StartupError) as caught:
        fpc.cloudflare_client(path)
    assert "api_token" in str(caught.value)
    assert "bool" in str(caught.value)


def test_cloudflare_client_without_a_cloudflare_section_is_a_startup_error(fpc, tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[Pantheon]\norg_id = "abc"\n')
    with pytest.raises(fpc.StartupError) as caught:
        fpc.cloudflare_client(str(path))
    assert "[Cloudflare]" in str(caught.value)


def test_cloudflare_client_with_a_missing_file_is_a_startup_error(fpc, tmp_path):
    with pytest.raises(fpc.StartupError):
        fpc.cloudflare_client(str(tmp_path / "nope.toml"))


def test_cloudflare_client_with_a_non_utf8_file_is_a_startup_error(fpc, tmp_path):
    """tomllib.load decodes the bytes itself, so a non-UTF-8 config raises UnicodeDecodeError --
    NOT a TOMLDecodeError.  It escaped as a raw traceback at exit 1 until the guard was widened
    to ValueError, which is the common base of both (round 3, finding 1)."""
    path = tmp_path / "config.toml"
    path.write_bytes(b'[Cloudflare]\napi_token = "caf\xe9"\n')
    with pytest.raises(fpc.StartupError) as caught:
        fpc.cloudflare_client(str(path))
    assert "not valid TOML" in str(caught.value)
```

- [ ] **Step 2: Run the tests to verify they fail**

Expected: FAIL — `AttributeError: module … has no attribute 'resolve_config_value'`.

- [ ] **Step 3: Implement**

Add this task's imports to the top block, then append after `is_platform_domain`:

```python
def resolve_env_marker(expr, where):
    """Resolve the body of ONE `<{ ... }` marker.  Only the env forms this script needs.

    Accepts `env NAME [DEFAULT]` and `secret env NAME [DEFAULT]` -- the two forms
    plugin/env/__init__.py registers.  Anything else (`secret aws ...`, `umich ...`) raises,
    rather than passing the literal marker through: a literal "<{secret aws ...}" handed to the
    API as a token would surface as a baffling 401 instead of a config error.

    Tokenizing deliberately uses shlex.split() rather than the config engine's
    list(shlex.shlex(expr, posix=True)), which ALSO splits on punctuation and so turns
    "env FOO some-default" into five tokens; the engine then scores 3 of 5 and reports "no match
    found for configuration file value".  The two agree on every marker the main program can
    actually resolve; this one is marginally more permissive about defaults containing
    punctuation.
    """
    try:
        argv = shlex.split(expr)
    except ValueError as e:
        # shlex raises on an unbalanced quote, e.g. <{env FOO don't}.  Without this the
        # ValueError escapes main() as a raw traceback at exit 1 -- a code SPEC R6 does not use.
        # The body is NOT echoed: the <{env NAME DEFAULT} form can carry a literal credential
        # as its default, and this message reaches stderr and any operator log.
        raise StartupError(f"{where}: malformed substitution ({e})") from e
    # The FORM only (the leading keywords, never an argument): "secret aws", "umich", "env".
    # argv[:2] AFTER the strip below would still carry the secret's path.
    form = " ".join(argv[:2]) or "(empty)"
    if argv[:1] == ["secret"]:
        argv = argv[1:]
    if argv[:1] != ["env"] or not 2 <= len(argv) <= 3:  # noqa: PLR2004 -- NAME, or NAME + DEFAULT
        raise StartupError(
            f"{where}: this script resolves only <{{env NAME}} and <{{secret env NAME}} "
            f"substitutions (each with an optional default), not '{form}'.  Put a literal or "
            "an environment-backed value there.  (The rest of the body is withheld: an inline "
            "default can be a credential.)")
    name = argv[1]
    if name in os.environ:
        return os.environ[name]
    if len(argv) == 3:  # noqa: PLR2004 -- the DEFAULT is present
        return argv[2]
    raise StartupError(f"{where}: environment variable '{name}' is not set")


def resolve_config_value(value, where):
    """Resolve every `<{ ... }` marker inside one config value.  Non-strings pass through."""
    if not isinstance(value, str):
        return value
    return MARKER_RE.sub(lambda match: resolve_env_marker(match.group(1), where), value)


def build_client(**creds):
    """Build a Cloudflare client that uses EXACTLY the credentials the config supplied.

    Measured on cloudflare 5.4.0: the SDK back-fills every credential argument left None from the
    environment.  It reads SIX variables, and ambient values reach the wire by FOUR routes --

      1. `auth_headers` returns the FIRST of email -> key -> token -> user_service_key that is
         set, and only that one -- so an ambient CLOUDFLARE_EMAIL beats a configured token;
      2. `default_headers` separately adds X-Auth-Key / X-Auth-Email whenever those attributes
         are not None;
      3. $CLOUDFLARE_CUSTOM_HEADERS is merged LAST into default_headers, overriding 1 and 2; and
      4. $CLOUDFLARE_BASE_URL redirects every request, sending the configured credential to an
         arbitrary host.

    Routes 1 and 2 are closed by nulling the fields the config did not supply (both read these
    attributes at request-build time); route 3 by clearing _custom_headers; route 4 by pinning
    base_url.  Routes 3 and 4 were missed on the first pass -- and 4 is worse than the defect
    this function was written for, because the credential LEAVES THE MACHINE rather than merely
    failing to authenticate.  This pin is SDK-version-sensitive: measured against cloudflare
    5.4.0, and pyproject declares the dependency unpinned as "cloudflare".  (The main program's
    plugin/cloudflare/client.py has all four; fixing it is a separate change.)
    """
    try:
        client = Cloudflare(**creds, base_url=API_BASE_URL)
    except OSError as e:
        # httpx builds its SSL context from the ambient environment (trust_env=True), so an
        # $SSL_CERT_FILE pointing at a missing path raises here -- another unnamed escape to
        # exit 1 if left alone (SPEC section R2a, residual routes).
        raise StartupError(f"could not build the Cloudflare client: {e}") from e
    for field in ("api_token", "api_key", "api_email", "user_service_key"):
        if field not in creds:
            setattr(client, field, None)
    client._custom_headers = {}  # noqa: SLF001 -- $CLOUDFLARE_CUSTOM_HEADERS is merged LAST
    # into default_headers, so it overrides the pinned Omit()s above; there is no public API
    # for "ignore that variable".  Measured: without this line and the base_url pin above,
    # exporting CLOUDFLARE_BASE_URL pointed at an attacker host, together with a
    # CLOUDFLARE_CUSTOM_HEADERS value supplying X-Auth-Email and X-Auth-Key, sends
    # `Authorization: Bearer <the real token>` to that host -- the pinned credential leaves the
    # machine.  That is strictly worse than the defect the field pinning above fixes.
    return client


def cloudflare_client(config_path):
    """Build the Cloudflare client from the [Cloudflare] table of the TOML at `config_path`.

    api_token wins when present; otherwise email + api_key, both required -- the same precedence
    plugin/cloudflare/client.py uses.  `enabled` is deliberately NOT consulted: that flag governs
    the main program's per-site Cloudflare work, and refusing to run this utility because of it
    would be a surprise to an operator who invoked it on purpose.
    """
    try:
        with Path(config_path).open("rb") as handle:
            config = tomllib.load(handle)
    except OSError as e:
        raise StartupError(f"cannot read {config_path}: {e}") from e
    except ValueError as e:
        # ValueError, not TOMLDecodeError: tomllib.load decodes the bytes itself, so a config
        # file that is not valid UTF-8 raises UnicodeDecodeError -- which is NOT a
        # TOMLDecodeError, and escaped as a raw traceback at exit 1 (a code SPEC R6 does not
        # use).  Both are ValueError subclasses, so one clause closes the class rather than the
        # instance -- the third time this defect class appeared (SPEC section 13).
        raise StartupError(f"{config_path} is not valid TOML: {e}") from e

    section = config.get("Cloudflare")
    if not isinstance(section, dict):
        raise StartupError(f"{config_path} has no [Cloudflare] section")

    def value(key):
        """One credential, type-checked where it is read then marker-resolved.

        TOML is a typed format, so `api_token = true` (an unquoted value -- an ordinary typo) is
        a bool, which `if api_token:` accepts and the SDK stringifies into
        `Authorization: Bearer True` -- exactly the confusing 401 that resolve_env_marker refuses
        to cause for an unresolvable marker.  The check belongs here, where the value is read.
        """
        raw = section.get(key)
        where = f"{config_path} [Cloudflare].{key}"
        if raw is not None and not isinstance(raw, str):
            raise StartupError(f"{where} must be a string, got {type(raw).__name__}")
        return resolve_config_value(raw, where)

    api_token = value("api_token")
    if api_token:
        return build_client(api_token=api_token)
    email = value("email")
    api_key = value("api_key")
    if not email or not api_key:
        raise StartupError(
            f"{config_path} [Cloudflare] needs either api_token, or both email and api_key")
    return build_client(api_email=email, api_key=api_key)
```

- [ ] **Step 4: Run the tests to verify they pass**

Expected: **25 passed** (8 + 17 here; `test_resolve_config_value_reads_the_environment` is
parametrized over two marker forms).

- [ ] **Step 5: Commit**

```bash
git add find-platform-domains-cloudflare tests/unit/test_find_platform_domains_cloudflare.py
git commit -m "feat(find-platform-domains-cloudflare): resolve credentials and pin the client against the environment"
```

---

## Task 3: The fold

**Files:**
- Modify: `find-platform-domains-cloudflare` (append after `cloudflare_client`)
- Test: `tests/unit/test_find_platform_domains_cloudflare.py` (append; **add `json` to the top
  import block**)

**Interfaces:**
- Consumes: `is_platform_domain`, `normalize` (Task 1).
- Produces: `plain(value)`, `collect_entries(zone_records) -> tuple[dict, list[str]]`, where
  `zone_records` is any iterable of `(zone_id, record)` pairs.

**Imports this task introduces:** script — none. Tests — `json`.

- [ ] **Step 1: Write the failing tests**

Add `import json` to the test file's top block, then append:

```python
# --- Task 3: the fold ------------------------------------------------------------------------

def test_collect_entries_builds_the_output_structure(fpc):
    entries, warnings = fpc.collect_entries([("zone-a", record(ttl=300, comment="migrated",
                                                               tags=["cdn"]))])
    assert entries == {
        "www.example.edu": {
            "zone_id": "zone-a",
            "origins": ["live-umich-example1.pantheonsite.io"],
            "record_id": "rec-1",
            "proxied": True,
            "ttl": 300,
            "comment": "migrated",
            "tags": ["cdn"],
            "settings": None,
        },
    }
    assert warnings == []


def test_collect_entries_keeps_dns_only_records(fpc):
    """The whole reason this script exists next to fqdns.json, which is proxied=True only."""
    entries, _ = fpc.collect_entries([("zone-a", record(proxied=False))])
    assert entries["www.example.edu"]["proxied"] is False


def test_collect_entries_serializes_a_pydantic_settings_model(fpc):
    """record.settings is a pydantic model; json.dump cannot serialize one."""
    from cloudflare.types.dns.cname_record import Settings
    entries, _ = fpc.collect_entries(
        [("zone-a", record(settings=Settings(flatten_cname=True)))])
    settings = entries["www.example.edu"]["settings"]
    assert settings["flatten_cname"] is True
    # Asserting the whole dict would pin the SDK's model shape (it also carries ipv4_only /
    # ipv6_only); what matters is the value round-tripping and the entry staying serializable,
    # which a live pydantic model would not be.
    json.dumps(entries)


def test_collect_entries_tolerates_a_record_missing_the_optional_fields(fpc):
    bare = types.SimpleNamespace(type="CNAME", name="www.example.edu", id="rec-1",
                                 content="live-umich-example1.pantheonsite.io")
    entries, _ = fpc.collect_entries([("zone-a", bare)])
    entry = entries["www.example.edu"]
    assert entry["proxied"] is None      # unknown, NOT coerced to False -- see R5
    assert entry["ttl"] is None
    assert entry["comment"] is None
    assert entry["tags"] == []
    assert entry["settings"] is None


@pytest.mark.parametrize("skipped", [
    {"type": "A", "content": "23.185.0.4"},
    {"type": "A", "content": "live-umich-example1.pantheonsite.io"},   # not a CNAME
    {"type": "TXT", "content": "v=spf1 -all"},
    {"type": "CNAME", "content": "www.example.edu.cdn.cloudflare.net"},  # not a platform domain
    {"type": "CNAME", "content": "notpantheonsite.io"},
])
def test_collect_entries_skips_everything_that_is_not_a_platform_cname(fpc, skipped):
    entries, warnings = fpc.collect_entries([("zone-a", record(**skipped))])
    assert entries == {}
    assert warnings == []


def test_collect_entries_normalizes_the_key_and_keeps_origins_raw(fpc):
    entries, _ = fpc.collect_entries(
        [("zone-a", record(name="WWW.Example.EDU.",
                           content="Live-Umich-Example1.PantheonSite.IO"))])
    assert list(entries) == ["www.example.edu"]
    assert entries["www.example.edu"]["origins"] == ["Live-Umich-Example1.PantheonSite.IO"]


def test_collect_entries_is_first_record_wins_across_zones_and_warns(fpc):
    entries, warnings = fpc.collect_entries([
        ("zone-a", record(id="rec-1", content="live-a.pantheonsite.io", proxied=True, ttl=1)),
        ("zone-b", record(id="rec-2", content="live-b.pantheonsite.io", proxied=False, ttl=300)),
    ])
    entry = entries["www.example.edu"]
    assert entry["zone_id"] == "zone-a"
    assert entry["record_id"] == "rec-1"
    assert entry["proxied"] is True
    assert entry["ttl"] == 1
    assert entry["origins"] == ["live-a.pantheonsite.io", "live-b.pantheonsite.io"]
    assert len(warnings) == 1
    assert "www.example.edu" in warnings[0]
    assert "zone-a" in warnings[0]
    assert "zone-b" in warnings[0]


def test_collect_entries_warns_for_two_matches_in_one_zone(fpc):
    """API-unreachable (a name holds at most one CNAME), but the file would keep one record_id
    of two and feed a destructive rewrite, so silence is the wrong default."""
    entries, warnings = fpc.collect_entries([
        ("zone-a", record(id="rec-1", content="live-a.pantheonsite.io")),
        ("zone-a", record(id="rec-2", content="live-b.pantheonsite.io")),
    ])
    assert entries["www.example.edu"]["record_id"] == "rec-1"
    assert len(warnings) == 1
    assert "rec-1" in warnings[0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Expected: FAIL — `AttributeError: module … has no attribute 'collect_entries'`.

- [ ] **Step 3: Implement**

Append after `cloudflare_client`:

```python
def plain(value):
    """A JSON-serializable copy of an SDK sub-model; anything already plain passes through.

    record.settings is a pydantic model (cloudflare.types.dns.cname_record.Settings), which
    json.dump cannot serialize.  mode="json" also coerces any nested exotic types.  The
    getattr guard is what lets the test fakes pass a plain dict or None.
    """
    dump = getattr(value, "model_dump", None)
    if dump is None:
        return value
    return dump(mode="json")


def collect_entries(zone_records):
    """Fold (zone_id, record) pairs into the output mapping.  Returns (entries, warnings).

    A record is kept only when it is a CNAME whose content is a *.pantheonsite.io hostname.
    Proxy status is NOT part of the test -- that is exactly what separates this script from
    fqdns.json, which is built with proxied=True and therefore cannot see a DNS-only record.

    Every scalar (zone_id, record_id, proxied, ttl, comment, tags, settings) is
    FIRST-RECORD-WINS, mirroring how fqdns.json already keeps only the first zone_id for a name.
    `origins` accumulates every match, so a name that matches more than once stays visible in the
    file and not only in the warning.

    `zone_records` is consumed lazily, so the caller can hand over a generator and the whole
    organization's record set is never held in memory at once.
    """
    entries = {}
    warnings = []
    for zone_id, dns_record in zone_records:
        if getattr(dns_record, "type", None) != "CNAME":
            continue
        content = getattr(dns_record, "content", None)
        if content is None or not is_platform_domain(content):
            continue
        name = normalize(dns_record.name)
        entry = entries.get(name)
        if entry is None:
            entries[name] = {
                "zone_id": zone_id,
                "origins": [content],
                "record_id": dns_record.id,
                # Stored VERBATIM, never coerced.  proxied is Optional[bool] on every record
                # model, and research.md is explicit that "proxied: true is the load-bearing
                # field in both directions" -- a None flattened to false would inflate the
                # DNS-only count AND instruct a rewriter to re-create a proxied hostname
                # unproxied, taking it out of certificate service.  An unknown stays null and
                # main() calls it out.
                "proxied": getattr(dns_record, "proxied", None),
                "ttl": getattr(dns_record, "ttl", None),
                "comment": getattr(dns_record, "comment", None),
                "tags": list(getattr(dns_record, "tags", None) or []),
                "settings": plain(getattr(dns_record, "settings", None)),
            }
            continue
        entry["origins"].append(content)
        # Warn on EVERY duplicate, not only a cross-zone one.  The file keeps one record_id of
        # two and feeds a destructive rewrite, so silence is the wrong default even for the
        # same-zone case -- which the Cloudflare API should make unreachable (a name may hold at
        # most one CNAME), making a warning there a signal worth seeing.
        if entry["zone_id"] == zone_id:
            warnings.append(
                f"ATTENTION: {name} has more than one platform-domain CNAME in zone {zone_id}, "
                f"which the Cloudflare API should not permit; keeping record_id "
                f"{entry['record_id']}")
        else:
            warnings.append(
                f"ATTENTION: {name} has a platform-domain CNAME in more than one Cloudflare "
                f"zone ({entry['zone_id']} and {zone_id}); keeping the first zone_id/record_id")
    return entries, warnings
```

- [ ] **Step 4: Run the tests to verify they pass**

Expected: **37 passed** (25 + 12 here;
`test_collect_entries_skips_everything_that_is_not_a_platform_cname` is parametrized over five
records).

- [ ] **Step 5: Commit**

```bash
git add find-platform-domains-cloudflare tests/unit/test_find_platform_domains_cloudflare.py
git commit -m "feat(find-platform-domains-cloudflare): fold DNS records into the output mapping"
```

---

## Task 4: The atomic write

**Files:**
- Modify: `find-platform-domains-cloudflare` (append after `collect_entries`)
- Modify: `.gitignore`
- Test: `tests/unit/test_find_platform_domains_cloudflare.py` (append)

**Interfaces:**
- Consumes: nothing.
- Produces: `write_json_atomic(path, data) -> None`.

**Imports this task introduces:** script — `json`, `tempfile`. Tests — none.

- [ ] **Step 1: Write the failing tests**

Append to the test file:

```python
# --- Task 4: the atomic write ----------------------------------------------------------------

def test_write_json_atomic_writes_sorted_indented_json_with_a_trailing_newline(fpc, tmp_path):
    target = tmp_path / "out.json"
    fpc.write_json_atomic(str(target), {"b": {"zone_id": "z"}, "a": {"zone_id": "y"}})
    text = target.read_text()
    assert text.endswith("\n")
    assert list(json.loads(text)) == ["a", "b"]
    assert '    "a"' in text          # indent=4


def test_write_json_atomic_overwrites_an_existing_file_and_leaves_no_temp_file(fpc, tmp_path):
    """SPEC: the output file is regenerated in full on every run, whatever its age."""
    target = tmp_path / "out.json"
    target.write_text('{"stale": {"zone_id": "old"}}\n')
    fpc.write_json_atomic(str(target), {})
    assert json.loads(target.read_text()) == {}
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]


def test_write_json_atomic_leaves_the_previous_file_intact_when_serialization_fails(fpc, tmp_path):
    target = tmp_path / "out.json"
    target.write_text('{"previous": {"zone_id": "kept"}}\n')
    with pytest.raises(TypeError):
        fpc.write_json_atomic(str(target), {"bad": {object()}})
    assert json.loads(target.read_text()) == {"previous": {"zone_id": "kept"}}
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Expected: FAIL — `AttributeError: module … has no attribute 'write_json_atomic'`.

- [ ] **Step 3: Implement**

Add `json` and `tempfile` to the top import block, then append after `collect_entries`:

```python
def write_json_atomic(path, data) -> None:
    """Write data as JSON to a temp file in the same directory, then os.replace() it onto `path`.

    Copied from plugin/cloudflare/fqdns.py's write_fqdns_atomic.  Atomic: an interrupted write
    never leaves a half-written or truncated output file -- the previous one stays byte-intact.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."  # noqa: PTH120, PTH100 --
    # feeds tempfile.mkstemp's dir=, load-bearing for the atomic-rename-needs-same-filesystem
    # guarantee this docstring documents; Path.resolve() follows symlinks where
    # os.path.abspath() does not, a real semantic difference for the symlink case
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".platform-domains-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=4, sort_keys=True)
            f.write("\n")
        # mkstemp creates the temp file mode 0600, which os.replace would preserve; restore a
        # normal umask-based mode (typically 0644) so other readers keep their access.
        current_umask = os.umask(0)
        os.umask(current_umask)
        os.chmod(tmp, 0o666 & ~current_umask)  # noqa: PTH101 -- behavior surface, see above
        os.replace(tmp, path)  # noqa: PTH105 -- THE atomic-replace call this docstring documents
    except BaseException:  # incl. KeyboardInterrupt: drop the temp file, leave the old one intact
        try:  # noqa: SIM105 -- not restructuring the BaseException cleanup handler's flow
            os.unlink(tmp)  # noqa: PTH108 -- cleanup path of the same behavior surface
        except FileNotFoundError:
            pass
        raise
```

- [ ] **Step 4: Ignore the generated output file**

In `.gitignore`, next to the existing `/fqdns.json` line:

```
/platform-domains-cloudflare.json
```

- [ ] **Step 5: Run the tests to verify they pass**

Expected: **40 passed** (37 + 3 here).

- [ ] **Step 6: Commit**

```bash
git add find-platform-domains-cloudflare tests/unit/test_find_platform_domains_cloudflare.py \
        .gitignore
git commit -m "feat(find-platform-domains-cloudflare): write the output file atomically"
```

---

## Task 5: The guarded walk and the CLI

**Files:**
- Modify: `find-platform-domains-cloudflare` (append after `write_json_atomic`)
- Test: `tests/unit/test_find_platform_domains_cloudflare.py` (append)

**Interfaces:**
- Consumes: `collect_entries`, `plain` (Task 3), `cloudflare_client` (Task 2),
  `write_json_atomic` (Task 4), `StartupError`, `OUTPUT_FILE`, `DEFAULT_CONFIG` (Task 1).
- Produces: `expected_record_count(page) -> int | None`;
  `read_all(fetch, what, notify=None) -> tuple[list, bool]`; `api_error_text(e) -> str`;
  `SweepResult` (a `NamedTuple` of `entries, warnings, accounts, zones, records, zones_checked`);
  `fetch_platform_cnames(client, *, verbose=False) -> SweepResult`; `build_arg_parser()`;
  `main(argv) -> int`.

**Imports this task introduces:** script — `argparse`, `sys`, `from typing import NamedTuple`, and
`import cloudflare` (the bare module, for `cloudflare.CloudflareError`). Tests — none at the top
level; `cloudflare`, `httpx` and the `cloudflare.pagination` names are imported inside test
bodies.

- [ ] **Step 1: Write the failing tests**

Append to the test file:

```python
# --- Task 5: the walk and the CLI ------------------------------------------------------------

class FakePage:
    """A stand-in for SyncV4PagePaginationArray.

    Iterating the real page object walks EVERY page (BaseSyncPage.__iter__ -> iter_pages), so
    this fake yields across chunks: an implementation that read `page.result` instead would see
    only the first, and this fake has no `result` attribute at all, so it would fail loudly.
    (test_the_real_page_class_has_a_result_attribute proves that trap is real, not imagined.)
    """

    def __init__(self, chunks, total_count=None, *, with_result_info=True):
        self._chunks = chunks
        self.result_info = types.SimpleNamespace(
            model_extra={} if total_count is None else {"total_count": total_count},
        ) if with_result_info else None

    def __iter__(self):
        for chunk in self._chunks:
            yield from chunk


class FakeCloudflareClient:
    """The three list() calls fetch_platform_cnames makes, and nothing else.

    `pages_by_zone` maps a zone id to the sequence of pages returned by successive calls (the
    last repeats), so a re-read can be made to agree or disagree with the first.
    """

    def __init__(self, accounts, zones, pages_by_zone=None, error=None):
        self._error = error
        self._pages_by_zone = pages_by_zone or {}
        self._calls = {}
        self.accounts = types.SimpleNamespace(list=lambda: accounts)
        self.zones = types.SimpleNamespace(list=lambda account: zones)
        self.dns = types.SimpleNamespace(records=types.SimpleNamespace(list=self._records))

    def _records(self, zone_id):
        if self._error is not None:
            raise self._error
        pages = self._pages_by_zone.get(zone_id) or [FakePage([[]])]
        index = min(self._calls.get(zone_id, 0), len(pages) - 1)
        self._calls[zone_id] = index + 1
        return pages[index]


def account(identifier="acct-1"):
    return types.SimpleNamespace(id=identifier)


def zone(identifier, name="example.edu"):
    return types.SimpleNamespace(id=identifier, name=name)


def test_fetch_platform_cnames_walks_every_zone_regardless_of_proxy_status(fpc):
    client = FakeCloudflareClient(
        accounts=[account()],
        zones=[zone("zone-a"), zone("zone-b", "example.org")],
        pages_by_zone={
            "zone-a": [FakePage([[record(name="proxied.example.edu", id="rec-1", proxied=True),
                                  record(name="mail.example.edu", id="rec-2", type="MX",
                                         content="mx.example.edu")]], total_count=2)],
            "zone-b": [FakePage([[record(name="dnsonly.example.org", id="rec-3",
                                         proxied=False)]], total_count=1)],
        })
    sweep = fpc.fetch_platform_cnames(client)
    assert sorted(sweep.entries) == ["dnsonly.example.org", "proxied.example.edu"]
    assert sweep.entries["dnsonly.example.org"]["proxied"] is False
    assert sweep.warnings == []
    assert (sweep.accounts, sweep.zones, sweep.records) == (1, 2, 3)
    # both record lists complete; the account and zone list fakes are plain lists
    # with no result_info, so they are unverifiable rather than complete.
    assert (sweep.lists_complete, sweep.lists_unverifiable) == (2, 2)


def test_fetch_platform_cnames_reads_every_page(fpc):
    """Pagination: a single list() call is N HTTP requests, and a short read would write a
    silently incomplete file."""
    client = FakeCloudflareClient(
        accounts=[account()], zones=[zone("zone-a")],
        pages_by_zone={"zone-a": [FakePage(
            [[record(name="page1.example.edu", id="rec-1")],
             [record(name="page2.example.edu", id="rec-2")]], total_count=2)]})
    sweep = fpc.fetch_platform_cnames(client)
    assert sorted(sweep.entries) == ["page1.example.edu", "page2.example.edu"]


def test_fetch_platform_cnames_unions_a_reread_to_close_a_gap(fpc):
    """A second walk steps over different rows, so the union is more complete than either read
    alone -- and often closes the gap outright."""
    client = FakeCloudflareClient(
        accounts=[account()], zones=[zone("zone-a")],
        pages_by_zone={"zone-a": [
            FakePage([[record(name="a.example.edu", id="rec-1")]], total_count=2),
            FakePage([[record(name="b.example.edu", id="rec-2")]], total_count=2),
        ]})
    sweep = fpc.fetch_platform_cnames(client)
    assert sorted(sweep.entries) == ["a.example.edu", "b.example.edu"]
    assert sweep.lists_short == 0


def test_fetch_platform_cnames_reports_a_short_list_without_aborting(fpc, capsys):
    """The first live sweep aborted an entire 187-zone run over 2 records missed in one
    18,848-record zone.  A shortfall is now reported and the file is still written."""
    client = FakeCloudflareClient(
        accounts=[account()], zones=[zone("zone-a")],
        pages_by_zone={"zone-a": [FakePage([[record()]], total_count=3)]})
    sweep = fpc.fetch_platform_cnames(client)
    assert list(sweep.entries) == ["www.example.edu"]
    assert sweep.lists_short == 1
    assert "were missed while paging" in capsys.readouterr().err


def test_fetch_platform_cnames_counts_every_list_it_reads(fpc):
    """Completeness is counted over the account list, each zone list, and each record list --
    reporting only record lists would leave the zone-list check unaccounted for."""
    client = FakeCloudflareClient(
        accounts=[account()], zones=[zone("zone-a"), zone("zone-b", "example.org")],
        pages_by_zone={"zone-a": [FakePage([[record()]], with_result_info=False)],
                       "zone-b": [FakePage([[]], total_count=0)]})
    sweep = fpc.fetch_platform_cnames(client)
    assert list(sweep.entries) == ["www.example.edu"]
    # account list (no result_info) + zone list (no result_info) + zone-a records = 3
    # unverifiable; zone-b's empty-but-counted record list = 1 complete.
    assert (sweep.lists_complete, sweep.lists_short, sweep.lists_unverifiable) == (1, 0, 3)


def test_fetch_platform_cnames_treats_zero_zones_as_fatal(fpc):
    """A missing scope and a genuinely empty org produce an identical empty file."""
    client = FakeCloudflareClient(accounts=[account()], zones=[])
    with pytest.raises(fpc.StartupError) as caught:
        fpc.fetch_platform_cnames(client)
    assert "0 zones" in str(caught.value)


def test_fetch_platform_cnames_turns_an_api_error_into_a_startup_error(fpc):
    import cloudflare
    client = FakeCloudflareClient(
        accounts=[account()], zones=[zone("zone-a")],
        error=cloudflare.APIConnectionError(request=None))
    with pytest.raises(fpc.StartupError) as caught:
        fpc.fetch_platform_cnames(client)
    assert "DNS records" in str(caught.value)


def test_expected_record_count_reads_a_real_result_info(fpc):
    """Against the SDK's own model, not the fake: total_count survives only because
    V4PagePaginationArrayResultInfo sets model_config extra="allow".  An SDK that tightened
    that, or renamed the field, would make the whole truncation guard no-op in production --
    and every fake-backed test would stay green."""
    from cloudflare.pagination import V4PagePaginationArrayResultInfo
    info = V4PagePaginationArrayResultInfo.model_validate(
        {"page": 1, "per_page": 100, "count": 1, "total_count": 137})
    assert fpc.expected_record_count(types.SimpleNamespace(result_info=info)) == 137


def test_the_real_page_class_has_a_result_attribute(fpc):
    """FakePage deliberately lacks `result` so an implementation reading page.result (page 1
    only) fails loudly.  That trap is only meaningful if the real class HAS the attribute."""
    from cloudflare.pagination import SyncV4PagePaginationArray
    assert "result" in SyncV4PagePaginationArray.model_fields


def test_api_error_text_never_includes_a_real_response_body(fpc):
    """Against a real SDK exception.  If status_code is ever renamed, api_error_text falls back
    to str(e) -- which IS "Error code: NNN - {body}", the leak the NEVER-block forbids."""
    import cloudflare
    import httpx
    body = {"errors": [{"code": 10000, "message": "token cf-secret-xyz invalid"}]}
    request = httpx.Request("GET", "https://api.cloudflare.com/client/v4/zones")
    error = cloudflare.PermissionDeniedError(
        f"Error code: 403 - {body}",
        response=httpx.Response(403, request=request, json=body), body=body)
    text = fpc.api_error_text(error)
    assert text == "PermissionDeniedError: HTTP 403"
    assert "cf-secret-xyz" not in text


def test_read_all_reports_a_complete_read(fpc):
    page = FakePage([[record(id="rec-1"), record(id="rec-2")]], total_count=2)
    items, shortfall = fpc.read_all(lambda: page, "the record list for zone x", print)
    assert len(items) == 2
    assert shortfall == 0


def test_read_all_deduplicates_records_repeated_across_pages(fpc):
    """MEASURED on the first live sweep.  The SDK paginates by page NUMBER, so rows shifting
    between page fetches make one record come back twice while another is stepped over.  Passing
    the duplicate onward would append one record's origin twice and raise a FALSE "more than one
    platform-domain CNAME in this zone" warning."""
    page = FakePage([[record(id="rec-1"), record(id="rec-2")],
                     [record(id="rec-2"), record(id="rec-3")]], total_count=3)
    items, shortfall = fpc.read_all(lambda: page, "the record list for zone x", print)
    assert sorted(i.id for i in items) == ["rec-1", "rec-2", "rec-3"]
    assert shortfall == 0


def test_read_all_cannot_check_without_total_count(fpc):
    page = FakePage([[record()]], with_result_info=False)
    items, shortfall = fpc.read_all(lambda: page, "the record list for zone x", print)
    assert len(items) == 1
    assert shortfall is None             # unverifiable, NOT asserted as complete


def test_read_all_unions_a_reread_to_close_the_gap(fpc):
    """A second walk usually steps over different rows, so the union is more complete than
    either read alone."""
    pages = iter([FakePage([[record(id="rec-1")]], total_count=2),
                  FakePage([[record(id="rec-2")]], total_count=2)])
    said = []
    items, shortfall = fpc.read_all(lambda: next(pages), "the record list for zone x", said.append)
    assert sorted(i.id for i in items) == ["rec-1", "rec-2"]
    assert shortfall == 0
    assert any("re-reading to close the gap" in m for m in said)


def test_read_all_warns_but_does_not_abort_when_records_stay_missing(fpc):
    """A shortfall is a WARNING, never fatal: a paginated walk of a continuously-written zone may
    never be exactly complete, and aborting would mean never producing output at all."""
    pages = iter([FakePage([[record(id="rec-1")]], total_count=3),
                  FakePage([[record(id="rec-2")]], total_count=3)])
    said = []
    items, shortfall = fpc.read_all(lambda: next(pages), "the record list for zone x", said.append)
    assert sorted(i.id for i in items) == ["rec-1", "rec-2"]
    assert shortfall == 1
    assert any("1 record(s) were missed" in m for m in said)
    assert any("NOT in this file" in m for m in said)


def test_a_reread_is_reported_without_v(fpc, capsys):
    """A re-read means the data moved under the sweep -- an operator wants that on a default run,
    not only when they happened to pass -v (round 3, finding 3)."""
    client = FakeCloudflareClient(
        accounts=[account()], zones=[zone("zone-a")],
        pages_by_zone={"zone-a": [
            FakePage([[record(name="a.example.edu", id="rec-1")]], total_count=2),
            FakePage([[record(name="a.example.edu", id="rec-1"),
                       record(name="b.example.edu", id="rec-2")]], total_count=2),
        ]})
    fpc.fetch_platform_cnames(client, verbose=False)
    assert "re-reading to close the gap" in capsys.readouterr().err


def test_verbose_reports_each_zone_and_whether_it_was_cross_checked(fpc, capsys):
    """SPEC section 6's -v contract, which nothing asserted until round 3 finding 5."""
    client = FakeCloudflareClient(
        accounts=[account()], zones=[zone("zone-a"), zone("zone-b", "example.org")],
        pages_by_zone={"zone-a": [FakePage([[record()]], total_count=1)],
                       "zone-b": [FakePage([[record(name="b.example.org")]],
                                           with_result_info=False)]})
    fpc.fetch_platform_cnames(client, verbose=True)
    err = capsys.readouterr().err
    assert "[1/2] zone example.edu -- 1 records" in err
    assert "[2/2] zone example.org -- 1 records (total_count unavailable, not cross-checked)" in err


def test_main_writes_the_file_and_reports_the_dns_only_count(fpc, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fpc, "cloudflare_client", lambda config_path: object())
    monkeypatch.setattr(fpc, "fetch_platform_cnames", lambda client, verbose=False: fpc.SweepResult(
        {"a.example.edu": {"zone_id": "z", "origins": ["live-a.pantheonsite.io"],
                           "record_id": "r", "proxied": False, "ttl": 1,
                           "comment": None, "tags": [], "settings": None}},
        ["ATTENTION: something worth seeing"], 1, 4, 12431, 40, 1, 2))
    assert fpc.main(["-c", "ignored.toml"]) == 0
    written = json.loads((tmp_path / fpc.OUTPUT_FILE).read_text())
    assert list(written) == ["a.example.edu"]
    captured = capsys.readouterr()
    err = captured.err
    assert "ATTENTION: something worth seeing" in err
    assert "Wrote 1 platform-domain CNAMEs (1 DNS-only" in err
    assert "from 12431 records in 4 zones in 1 account(s)" in err
    assert captured.out == "", "stdout carries only argparse output (SPEC R6)"
    assert ("Completeness cross-check: 40 of 43 paginated lists verified complete, 1 short, "
            "2 unverifiable.") in err
    assert "the short lists are named above" in err


def test_main_does_not_count_an_unknown_proxy_status_as_dns_only(fpc, tmp_path, monkeypatch,
                                                                 capsys):
    """research.md: "proxied: true is the load-bearing field in both directions".  A null
    flattened to false would inflate the headline count AND tell a rewriter to re-create a
    proxied hostname unproxied (round 3, finding 4)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fpc, "cloudflare_client", lambda config_path: object())
    entry = {"zone_id": "z", "origins": ["live-a.pantheonsite.io"], "record_id": "r",
             "proxied": None, "ttl": 1, "comment": None, "tags": [], "settings": None}
    monkeypatch.setattr(fpc, "fetch_platform_cnames", lambda client, verbose=False:
                        fpc.SweepResult({"a.example.edu": entry}, [], 1, 1, 1, 3, 0, 0))
    assert fpc.main([]) == 0
    err = capsys.readouterr().err
    assert "(0 DNS-only" in err
    assert "unknown proxy status" in err
    assert "a.example.edu" in err


def test_main_says_so_when_nothing_matched(fpc, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fpc, "cloudflare_client", lambda config_path: object())
    monkeypatch.setattr(fpc, "fetch_platform_cnames",
                        lambda client, verbose=False: fpc.SweepResult({}, [], 1, 4, 900, 6, 0, 0))
    assert fpc.main([]) == 0
    assert json.loads((tmp_path / fpc.OUTPUT_FILE).read_text()) == {}
    assert "no platform-domain CNAMEs found in 4 zones" in capsys.readouterr().err


def test_main_reports_a_startup_error_as_exit_2(fpc, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert fpc.main(["-c", str(tmp_path / "nope.toml")]) == 2
    assert "ERROR: cannot read" in capsys.readouterr().err


def test_main_reports_an_interrupt_as_exit_130(fpc, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    def interrupt(config_path):
        raise KeyboardInterrupt

    monkeypatch.setattr(fpc, "cloudflare_client", interrupt)
    assert fpc.main([]) == 130
    assert "INTERRUPTED" in capsys.readouterr().err


def test_main_names_an_unwritable_output_file_instead_of_crashing(fpc, tmp_path, monkeypatch,
                                                                  capsys):
    """An OSError here lands AFTER the whole multi-minute walk; it escaped as a raw traceback at
    exit 1 until it was named (adversarial review round 1, finding 3)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fpc, "cloudflare_client", lambda config_path: object())
    monkeypatch.setattr(fpc, "fetch_platform_cnames",
                        lambda client, verbose=False: fpc.SweepResult({}, [], 1, 1, 0, 3, 0, 0))

    def refuse(path, data):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(fpc, "write_json_atomic", refuse)
    assert fpc.main([]) == 2
    assert "cannot write" in capsys.readouterr().err
```

> Note for the implementer: `import cloudflare` / `import httpx` inside a test body is deliberate
> — the top block carries only what module level needs, and `PLC0415` (in-test imports) is in the
> `tests/**` ignore list. `httpx` is a direct dependency under the `cloudflare` extra, so these
> tests stay offline. `cloudflare.APIConnectionError(request=None)` was verified constructible
> against the installed SDK (5.4.0); its MRO is
> `APIConnectionError → APIError → CloudflareError → Exception`.

- [ ] **Step 2: Run the tests to verify they fail**

Expected: FAIL — `AttributeError: module … has no attribute 'expected_record_count'`.

- [ ] **Step 3: Implement**

Add this task's imports to the top block, then append after `write_json_atomic`:

```python
def expected_record_count(page):
    """Cloudflare's total_count for a paginated response, or None when it is not available.

    V4PagePaginationArrayResultInfo declares only page/per_page, but its model_config is
    extra="allow", so the API's count/total_count survive as model_extra.  Returning None rather
    than guessing makes the caller's cross-check a no-op wherever the field is absent, so it can
    never abort a healthy sweep -- at the cost of the guard silently not running, which is why
    read_all reports whether it was live.
    """
    info = getattr(page, "result_info", None)
    extra = getattr(info, "model_extra", None) or {}
    total = extra.get("total_count")
    return total if isinstance(total, int) else None


def read_page_once(fetch):
    """One full walk of a paginated endpoint: ({id: item}, total_count or None).

    De-duplicated by id, which is NOT belt-and-braces.  Measured on the first live sweep: the
    SDK paginates by page NUMBER, so when rows shift between page fetches -- routine in a zone
    being actively written -- the same record comes back on two pages while another is stepped
    over.  Feeding those duplicates onward would append one record's origin twice and raise a
    FALSE "more than one platform-domain CNAME in this zone" warning, which R7 defines as a
    signal worth acting on.
    """
    page = fetch()
    by_id = {}
    for item in page:
        by_id.setdefault(item.id, item)
    return by_id, expected_record_count(page)


def read_all(fetch, what, notify):
    """Every item of a paginated endpoint, de-duplicated, checked against Cloudflare's own count.

    Returns (items, shortfall).  `shortfall` is None when Cloudflare supplied no total_count (the
    check could not run), else how many items total_count says we never saw -- 0 for a verified
    complete read.

    `fetch` is a zero-argument callable, not a page, so the re-read can repeat the whole request.
    Iterating the page object walks EVERY page (BaseSyncPage.__iter__ -> iter_pages); reading
    page.result instead would silently take page 1 only.

    A shortfall is a WARNING, never fatal.  The first live sweep is why: on an 18,848-record zone
    this walk both repeated 2 records and missed 2, and on one read those two errors cancelled so
    that raw item count matched total_count exactly -- the check passing while the data was
    incomplete.  Counting unique ids removes that blind spot, but it cannot make a paginated walk
    of a continuously-written zone complete, and aborting on one would mean this utility never
    produces output at all.  So the run says loudly which lists are short and by how much, and
    still writes the file.

    `notify` is NOT the -v gate: a short read is rare and an operator wants it on every run.
    """
    by_id, expected = read_page_once(fetch)
    if expected is None:
        return list(by_id.values()), None
    if len(by_id) >= expected:
        return list(by_id.values()), 0

    # One re-read, UNIONED with the first: a second walk usually steps over different rows, so
    # the union is more complete than either read alone and often closes the gap entirely.
    notify(f"{what}: read {len(by_id)} unique of {expected} -- re-reading to close the gap")
    more, expected_again = read_page_once(fetch)
    by_id.update(more)
    expected = max(expected, expected_again or 0)
    shortfall = max(0, expected - len(by_id))
    if shortfall:
        notify(f"ATTENTION: {what} -- read {len(by_id)} unique records but Cloudflare reported "
               f"{expected}; {shortfall} record(s) were missed while paging a list that is being "
               "actively written.  Any platform-domain CNAME among them is NOT in this file.")
    return list(by_id.values()), shortfall


def api_error_text(e):
    """A message for a Cloudflare API failure that NEVER includes the response body.

    APIStatusError's str() is "Error code: NNN - {body}"; a DNS-record body echoes record
    contents and an auth-failure body can echo the credential.  The class plus the status code is
    what an operator needs in order to act.
    """
    status = getattr(e, "status_code", None)
    if status is not None:
        return f"{type(e).__name__}: HTTP {status}"
    return f"{type(e).__name__}: {e}"


class ListTally:
    """How many paginated lists came back complete, short, or unverifiable."""

    def __init__(self):
        self.complete = self.short = self.unverifiable = 0

    def count(self, shortfall):
        """Record one list read.  `shortfall` is read_all's second return value."""
        if shortfall is None:
            self.unverifiable += 1
        elif shortfall:
            self.short += 1
        else:
            self.complete += 1


class SweepResult(NamedTuple):
    """What one sweep found, plus what it can honestly say about its own completeness."""

    entries: dict          # the output mapping, keyed by normalized FQDN
    warnings: list         # duplicate-name ATTENTION lines, printed before the write
    accounts: int          # accounts listed
    zones: int             # zones listed across those accounts
    records: int           # unique DNS records actually read and inspected
    # Completeness, counted over EVERY paginated list read -- the account list, one zone list
    # per account, and one record list per zone.  Reporting only the record lists would leave
    # the zone-list check, the one whose loss is worse, silently unaccounted for.
    lists_complete: int    # unique count reached Cloudflare's total_count
    lists_short: int       # total_count says items were missed (each named in an ATTENTION)
    lists_unverifiable: int  # Cloudflare supplied no total_count, so nothing could be checked


def list_zones(client, warn):
    """Every zone across every account the credentials can see, cross-checked like the records.

    Returns (accounts, zones, tally) where tally counts this function's own list reads.  Zero
    zones is fatal,
    copied from fqdns.py's reasoning: with the scope missing, "no zones" and "no matching
    records" write an identical empty file, and a silently empty file is the one failure mode
    this script must not have.  The message names BOTH scopes because an accounts list that comes
    back empty yields zero zones just as a missing DNS:Read does.
    """
    tally = ListTally()
    try:
        accounts, shortfall = read_all(client.accounts.list, "the account list", warn)
        tally.count(shortfall)
        zones = []
        for account in accounts:
            # The default argument binds this account's id at definition time; a bare closure
            # over the loop variable would re-read the LAST account on every retry (ruff B023).
            got, shortfall = read_all(
                lambda account_id=account.id: client.zones.list(account={"id": account_id}),
                f"the zone list for account {account.id}", warn)
            tally.count(shortfall)
            zones.extend(got)
    except cloudflare.CloudflareError as e:
        raise StartupError(f"listing accounts/zones failed: {api_error_text(e)}") from e

    if not zones:
        raise StartupError(
            f"Cloudflare returned {len(accounts)} account(s) but 0 zones -- the credentials "
            "likely lack Account:Read or DNS:Read (an accounts list that comes back empty "
            "yields zero zones too).")
    return accounts, zones, tally


def fetch_platform_cnames(client, *, verbose=False):
    """Walk every account -> zone -> DNS record and collect the platform-domain CNAMEs.

    No `proxied=` filter and no `type=` filter on the record list: every record in every zone is
    fetched and inspected here.  That is what "consider all DNS records" means, and per the spec
    no work goes into making it faster.  (If a run ever becomes painful, type="CNAME" on the
    records list call is the one-word change.)

    `client.dns.records.list()` returns a page-numbered paginator -- iterating it walks every
    page, stopping when a page comes back empty -- so a single call is N HTTP requests.  A
    truncated walk would write a silently incomplete file, so every list this function reads goes
    through read_all's total_count cross-check.

    Records are read one zone at a time rather than one record at a time: a re-read has to be
    able to replace a whole zone's list, and the largest single zone is a trivial amount of
    memory next to the whole organization's records.
    """
    def note(message):
        """Per-zone progress: -v only."""
        if verbose:
            print(message, file=sys.stderr, flush=True)

    def warn(message):
        """Re-read notices: ALWAYS printed.  A re-read means the data moved mid-sweep."""
        print(message, file=sys.stderr, flush=True)

    accounts, zones, tally = list_zones(client, warn)
    seen = {"records": 0}

    def zone_records():
        """(zone_id, record) pairs, one zone at a time."""
        for number, zone in enumerate(zones, start=1):
            records, shortfall = read_all(
                lambda zone_id=zone.id: client.dns.records.list(zone_id=zone_id),
                f"the record list for zone {zone.name}", warn)
            tally.count(shortfall)
            seen["records"] += len(records)
            marker = {None: " (total_count unavailable, not cross-checked)",
                      0: ""}.get(shortfall, f" ({shortfall} missed)")
            note(f"[{number}/{len(zones)}] zone {zone.name} -- {len(records)} records{marker}")
            for dns_record in records:
                yield zone.id, dns_record

    try:
        entries, warnings = collect_entries(zone_records())
    except cloudflare.CloudflareError as e:
        raise StartupError(f"listing DNS records failed: {api_error_text(e)}") from e

    return SweepResult(entries, warnings, len(accounts), len(zones), seen["records"],
                       tally.complete, tally.short, tally.unverifiable)


def build_arg_parser():
    parser = argparse.ArgumentParser(
        allow_abbrev=False,          # house rule: no --for -> --for-real class of foot-gun
        description="Write every Cloudflare CNAME record pointing at a Pantheon platform "
                    f"domain to {OUTPUT_FILE}.")
    parser.add_argument("-c", "--config", default=DEFAULT_CONFIG,
                        help=f"TOML file to read [Cloudflare] credentials from "
                             f"(default: {DEFAULT_CONFIG})")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="print each zone to stderr as it is scanned")
    return parser


def main(argv):
    """Exit 0 = the output file was written, 2 = could not complete, 130 = interrupted.

    There is deliberately no exit 1: the sibling find-platform-domains-dns reserves it for
    "completed with indeterminates" because a DNS lookup can be indeterminate, whereas a
    Cloudflare list call either returns or raises.  Holding that line takes the two conversions
    to StartupError below and the two inside resolve_env_marker/cloudflare_client -- an OSError
    on the write and a ValueError from shlex both escaped as raw tracebacks at exit 1 until they
    were named (adversarial review, finding 3).  A doomed stderr can still produce exit 120 from
    the interpreter's shutdown flush; that is accepted and documented in SPEC section 8, item 4.

    stdout carries only argparse's usage/--help text; every operator message goes to stderr.
    """
    options = build_arg_parser().parse_args(argv)
    try:
        client = cloudflare_client(options.config)
        sweep = fetch_platform_cnames(client, verbose=options.verbose)
        entries = sweep.entries
        for message in sweep.warnings:
            print(message, file=sys.stderr, flush=True)
        try:
            write_json_atomic(OUTPUT_FILE, entries)
        except OSError as e:
            # A full disk or a read-only directory lands here AFTER the whole multi-minute walk.
            raise StartupError(f"cannot write {OUTPUT_FILE}: {e}") from e
        # `is False`, not falsy: an unknown proxy status is null and must not be counted as
        # DNS-only -- that count is the headline number this script exists to produce.
        dns_only = sum(1 for entry in entries.values() if entry["proxied"] is False)
        unknown_proxy = sorted(n for n, e in entries.items() if e["proxied"] is None)
        print(f"Wrote {len(entries)} platform-domain CNAMEs ({dns_only} DNS-only, invisible to "
              f"fqdns.json) from {sweep.records} records in {sweep.zones} zones in "
              f"{sweep.accounts} account(s) to {OUTPUT_FILE}.", file=sys.stderr, flush=True)
        # Report the guard's own coverage: a truncation check that silently never ran looks
        # exactly like one that ran and found nothing wrong.
        lists = sweep.lists_complete + sweep.lists_short + sweep.lists_unverifiable
        print(f"Completeness cross-check: {sweep.lists_complete} of {lists} paginated lists "
              f"verified complete, {sweep.lists_short} short, {sweep.lists_unverifiable} "
              "unverifiable.", file=sys.stderr, flush=True)
        if sweep.lists_short:
            print("ATTENTION: the short lists are named above; records missed while paging them "
                  "are NOT in this file.", file=sys.stderr, flush=True)
        if unknown_proxy:
            print(f"ATTENTION: {len(unknown_proxy)} entr"
                  f"{'y has' if len(unknown_proxy) == 1 else 'ies have'} an unknown proxy status "
                  f"(null, not false): {', '.join(unknown_proxy)} -- a rewriter MUST NOT treat "
                  "these as DNS-only.", file=sys.stderr, flush=True)
        if not entries:
            print(f"ATTENTION: no platform-domain CNAMEs found in {sweep.zones} zones; "
                  f"{OUTPUT_FILE} was written empty.", file=sys.stderr, flush=True)
    except StartupError as e:
        print(f"ERROR: {e}", file=sys.stderr, flush=True)
        return 2
    except KeyboardInterrupt:
        # The write is atomic, so the file is either untouched or complete -- never half-written.
        print(f"INTERRUPTED: {OUTPUT_FILE} is either unchanged or fully written.",
              file=sys.stderr, flush=True)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run the tests to verify they pass**

Expected: **63 passed** (40 + 23 here).

- [ ] **Step 5: Run the whole gate**

Run: `./run-tests --fast`
Expected: ruff passes, pyright passes, the full offline suite green with no new failures.

- [ ] **Step 6: Prove the lint entries are load-bearing (a check that can go red)**

```bash
uvx ruff@0.15.22 check find-platform-domains-cloudflare
# -> All checks passed!

# Now temporarily comment out BOTH "find-platform-domains-cloudflare*" per-file-ignores
# entries in pyproject.toml and re-run:
uvx ruff@0.15.22 check find-platform-domains-cloudflare
# -> 9 errors, all T201.  Restore the entries.
```

Measured: exactly **9 × T201**. If the second run reports zero errors, the entries are in the
wrong place and the first run proved nothing.

- [ ] **Step 7: Verify the CLI surface without touching Cloudflare**

```bash
source .venv/bin/activate
./find-platform-domains-cloudflare --help
./find-platform-domains-cloudflare -c /nonexistent.toml ; echo "exit=$?"
```
Expected: usage text on **stdout**; then `ERROR: cannot read /nonexistent.toml: …` on **stderr**
and `exit=2`.

- [ ] **Step 8: Commit**

```bash
git add find-platform-domains-cloudflare tests/unit/test_find_platform_domains_cloudflare.py
git commit -m "feat(find-platform-domains-cloudflare): walk every zone, guarded against truncation"
```

---

## Task 6: Documentation (offline, ungated)

**Files:**
- Modify: `CLAUDE.md` (a subsection beside the existing `find-platform-domains-dns` one)

Deliberately **before** the STOP, and committed on its own, so the utility is documented in git
whether or not the live run ever happens.

- [ ] **Step 1: Add the CLAUDE.md subsection**

Immediately after the existing `find-platform-domains-dns` subsection, add the block below.
(Nested fences are shown indented by two spaces; remove that indent when inserting.)

~~~~markdown
### `find-platform-domains-cloudflare` (temporary utility)

A standalone, deletable script — **not** part of the main program and importing nothing from
`psh/`/`check/`/`plugin/` — that writes every Cloudflare DNS **CNAME whose target ends in
`.pantheonsite.io`** to `./platform-domains-cloudflare.json`. It is the Cloudflare-side
counterpart to `find-platform-domains-dns`: that one reads public DNS and is blind to a proxied
record's target; `fqdns.json` is built with `proxied=True` and is blind to a DNS-only record. This
considers **all** records in **all** zones of every account the credentials can see. Legacy
`*.gotpantheon.com` targets are out of scope.

The file is keyed by the **normalized** FQDN with `{zone_id, origins, record_id, proxied, ttl,
comment, tags, settings}`. **Two traps when comparing it to `fqdns.json`:** that file keys by the
**raw** `record.name` (normalize both sides, or you invent phantom entries), and its `origins`
means something **wider** — every proxied record's content at that name, IP addresses included —
where this file's holds only matching platform-CNAME targets. `settings` is `.model_dump()`ed (it
is a pydantic model and is otherwise unserializable). Every scalar is **first-record-wins**,
`origins` accumulates, and **every** duplicate name warns on stderr. The file is **regenerated in
full on every run**, whatever its age; a run that matches nothing writes `{}` loudly rather than
leaving a stale file. It drives a *destructive* rewrite, so **regenerate it immediately before any
rewrite** — its mtime is the only freshness signal it carries.

Exit 0 = written, 2 = could not complete, 130 = interrupted; there is no exit 1 (a doomed stdout
or stderr can still exit 120, as with the sibling's argparse output). Exit 2 covers an unreadable
config, a non-string or unresolvable credential, missing credentials, any Cloudflare API error,
**zero zones** (a missing `Account:Read`/`DNS:Read` scope and a genuinely empty org otherwise
produce an identical empty file), **a truncated list**, and an `OSError` on the write. All three
list endpoints paginate, so each one's item count is cross-checked against Cloudflare's own
`total_count`; a mismatch triggers **one re-read**, because `total_count` is computed for page 1
and an item changed mid-sweep disagrees for a benign reason — a self-consistent re-read is that
case and is kept, a second disagreement is truncation and aborts without writing. The run reports
how many zones it could actually cross-check, since the guard no-ops wherever the API omits
`total_count`. stdout carries only argparse's usage/`--help`; everything else is stderr, and error
text **never** includes an API response body.

Credentials come from `[Cloudflare]` in the same TOML the main program reads, via a **copied**
resolver handling only the `<{env NAME}` / `<{secret env NAME}` forms; any other substitution, and
any non-string value, is a named error rather than a silent passthrough. `enabled` is not
consulted. **`build_client()` pins the client against the ambient environment** — four credential
fields, `base_url`, and `_custom_headers` — because the SDK back-fills unset credentials from six
environment variables and ambient values reach the wire by four routes, the worst being
`$CLOUDFLARE_BASE_URL`, which sends the configured token to an arbitrary host. Measured against
cloudflare 5.4.0. **`plugin/cloudflare/client.py` has all four routes open**, and
`$CLOUDFLARE_BASE_URL` is exploitable against the main program today, whichever credential form is
configured.

```bash
./find-platform-domains-cloudflare            # every zone, every account
./find-platform-domains-cloudflare -v         # ... naming each zone and its record count
```

`find-platform-domains-cloudflare.py` is a committed symlink to the script above, same convention
as `pantheon-sitehealth-emails.py` and `find-platform-domains-dns.py`: ruff, pyright, and
CodeGraph key off the `.py` extension and would otherwise be blind to the extension-less real
file. **Delete this script after Pantheon's CDN migration** — checklist in
`development/2026-07-30-platform-domain-util2/SPEC.md` §11.
~~~~

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(find-platform-domains-cloudflare): document the temporary utility"
```

---

## Task 7: Live verification

> ⚠️ **SUPERSEDED by Amendment A1.9a — DO NOT RUN AS WRITTEN.** Step 1 has no `-o`, so under
> Amendment A1 the JSON goes to the terminal and no file is produced; Steps 2–3 then `json.load()`
> `platform-domains-cloudflare.json` and would silently validate a **stale** artifact left by an
> earlier sweep. Run this first, then use the A1.9a Step 1:
>
> ```bash
> mv -n platform-domains-cloudflare.json platform-domains-cloudflare.json.bak   # Step 0
> time ./find-platform-domains-cloudflare -v -o platform-domains-cloudflare.json ; echo "exit=$?"
> ```

> # ⛔ STOP — OPERATOR APPROVAL REQUIRED
>
> **This is a structural halt, not a checklist item. There is deliberately no checkbox to tick.**
>
> Every step below calls the **live Cloudflare API with production credentials**. Tasks 1–6 were
> entirely offline.
>
> **Do not proceed until the operator replies with the exact phrase:**
>
> ```
> RUN THE LIVE SWEEP
> ```
>
> Nothing else unlocks this task. Report that you are waiting, and stop. If the operator declines
> or never answers, Tasks 1–6 are already committed and complete; §12 simply stays unfilled.

- [ ] **Step 1: Run the live sweep**

```bash
source .venv/bin/activate
time ./find-platform-domains-cloudflare -v ; echo "exit=$?"
```

Expected: per-zone lines with record counts on stderr, then the summary and the cross-check
coverage line, `exit=0`. **Record the wall-clock time** — §12 and the CLAUDE.md subsection both
need it.

- [ ] **Step 2: Verify the output against the contract**

```bash
python - <<'PY'
import json
data = json.load(open("platform-domains-cloudflare.json"))
expected_keys = {"zone_id", "origins", "record_id", "proxied", "ttl", "comment", "tags",
                 "settings"}
for name, entry in data.items():
    assert set(entry) == expected_keys, f"{name}: unexpected key set {set(entry)}"
    for origin in entry["origins"]:
        assert origin.rstrip(".").lower().endswith(".pantheonsite.io"), f"{name}: {origin}"
    assert name == name.strip().rstrip(".").lower(), f"{name}: key not normalized"
print(len(data), "entries;",
      sum(1 for e in data.values() if not e["proxied"]),
      "DNS-only (invisible to fqdns.json);",
      sum(1 for e in data.values() if len(e["origins"]) > 1), "with multiple origins")
PY
```

- [ ] **Step 3: Cross-check against `fqdns.json`**

```bash
python - <<'PY'
import json
new = json.load(open("platform-domains-cloudflare.json"))
old = json.load(open("fqdns.json"))
# BOTH sides normalized: this file keys by the normalized name, fqdns.json by the raw
# record.name, so differencing them raw invents phantom entries (SPEC R5a).
def norm(name): return name.strip().rstrip(".").lower()
proxied_here = {norm(k) for k, v in new.items() if v["proxied"]}
missing = sorted(proxied_here - {norm(k) for k in old})
print("proxied platform CNAMEs this run found that fqdns.json lacks:", missing)
PY
```

Expected: an empty list, or a short list explainable by `fqdns.json` being stale (24h refresh
rule). A long unexplained list means the walk is wrong — stop and investigate before recording
§12. Note this compares only *proxied* entries, since `fqdns.json` structurally cannot contain the
DNS-only ones.

- [ ] **Step 4: Record §12, add the runtime to the CLAUDE.md subsection, and commit**

```bash
git add CLAUDE.md development/2026-07-30-platform-domain-util2/SPEC.md
git commit -m "docs(find-platform-domains-cloudflare): record the first live sweep"
```

---

## 8. NOT in scope

Recorded with the reasoning so a later session does not re-litigate them.

1. ~~**`--output` flag.**~~ **REVERSED by Amendment A1.2** — `-o/--output` exists, and stdout is
   the default result stream. The original reasoning ("the path is fixed by the PROMPT") stopped
   holding once a run could cover a subset of zones.
2. **Nested `records` list / parallel arrays for per-record detail.** Rejected in favor of scalars
   with first-record-wins, mirroring how `fqdns.json` already treats `zone_id`. Duplicates always
   warn and every target stays in `origins`.
3. **Server-side filtering (`type="CNAME"` on the records list).** Rejected: the requirement is to
   consider all records, efficiency is explicitly not a goal, and the change is one word if a run
   becomes painful. §14 Q2 revisits it against the measured runtime.
4. ~~**Doomed-stream detach guards and the exit-120 taxonomy**~~ **REVERSED by Amendment A1.5** —
   the premise below ("here the result is a file") stopped holding when stdout became the result
   stream; the guards are ported. Original reasoning retained: that
   machinery exists because the sibling's *result* is a CSV on stdout, where a failed shutdown
   flush silently converts a good sweep into exit 120. Here the result is a file. A doomed stdout
   (`--help >/dev/full`) or stderr can still produce exit 120 — accepted and documented (R6)
   rather than guarded, the same call CLAUDE.md already records for the sibling's argparse output.
5. **Any live-API test.** Every test in §7 is offline. The live path is exercised once, by hand,
   behind Task 7's STOP.
6. **Progress bars (`rich.progress`).** Rejected: `-v` stderr lines carry the same information
   with none of the copied machinery.
7. ~~**Fixing `plugin/cloudflare/client.py`'s R2a defect.**~~ **DONE 2026-07-30, commit
   `befb913`** — out of scope for this utility as written below, but fixed separately the same day;
   see Amendment A2. Original reasoning retained: real, measured, reported — but a change
   to the main program with its own test surface. **It was not merely latent:**
   `$CLOUDFLARE_BASE_URL` is exploitable against the main program today, whichever credential form
   is configured.
8. **A `docs/` page.** The CLAUDE.md subsection is the documentation; a temporary utility does not
   earn a docs page.
9. **Counted `-v/-vv/-vvv`.** Rejected: the truncation guard is a hard abort *and* reports its own
   coverage at default verbosity, so both questions a `-vv` tier would have answered ("did it
   fire?", "did it run at all?") are answered without one. The sibling sets the boolean-`-v`
   precedent for temporary scripts.
10. **Pinning the `cloudflare` dependency.** R2a and R3 rest on SDK internals and `pyproject.toml`
    declares `"cloudflare"` unpinned. Pinning affects every consumer and is a main-program
    decision. Mitigation instead: §7 includes three tests that touch the **real** SDK classes —
    `V4PagePaginationArrayResultInfo` (so a lost `extra="allow"`, or a renamed `total_count`, goes
    red instead of silently disabling the whole truncation guard), `SyncV4PagePaginationArray` (so
    the `page.result` trap the fake encodes stays real), and a real `PermissionDeniedError` (so a
    renamed `status_code` cannot silently turn `api_error_text` into a response-body leak).
    Fake-backed tests alone could notice none of these.
11. **Guarding the count of *matching* records.** Only list completeness is guarded; there is no
    expected number of platform CNAMEs to check against.
12. **Resumability after a partial run (PD#7).** A transient failure on zone 40 of 43 — past the
    SDK's own two automatic retries — or a Ctrl-C, discards the whole sweep; there is no partial
    artifact and no `--resume-from`. **Deliberate:** the output file must be internally
    consistent (a partial one would silently under-report, the failure mode this whole design is
    organized against), the sweep is read-only and idempotent, and the only cost of a re-run is
    time. The sibling utility needed resume because its sweep is ~38 minutes of *per-site* work
    with a CSV growing on stdout; this one writes a single file at the end. **Revisit if §12's
    measured runtime is large** — that is §14 Q2.
13. **`trust_env=False` on the SDK's HTTP client.** See R2a's stated residual: it would close the
    proxy / trust-store routes but break legitimate proxied deployments. Recorded as the
    operator's call, not taken unilaterally.

## 9. Files created / modified (complete list)

| File | Action | Task |
|---|---|---|
| `find-platform-domains-cloudflare` | create (executable) | 1–5 |
| `find-platform-domains-cloudflare.py` | create (symlink) | 1 |
| `tests/unit/test_find_platform_domains_cloudflare.py` | create | 1–5 |
| `pyproject.toml` | modify (2 per-file-ignores + 1 pyright include) | 1 |
| `.claude/hooks/ruff-check.sh` | modify (1 case arm + comment) | 1 |
| `.gitignore` | modify (1 line) | 4 |
| `CLAUDE.md` | modify (1 subsection; runtime added in Task 7) | 6, 7 |
| `development/2026-07-30-platform-domain-util2/SPEC.md` | modify (§12 result) | 7 |

## 10. Verification

- `./run-tests --fast` — ruff, pyright, and the offline suite green; 63 new tests. Measured clean
  at **every** per-task checkpoint (8 / 25 / 37 / 40 / 63), not only at the end.
- Task 5 Step 6 — the per-file-ignores entries proven load-bearing (9 × T201 without them).
- `./find-platform-domains-cloudflare --help` — usage renders on stdout.
- `./find-platform-domains-cloudflare -c /nonexistent.toml` — exit 2, named error on stderr.
- The live run and its two cross-checks (Task 7), behind the STOP.

## 11. Deletion checklist (after Pantheon's CDN migration)

> **Superseded in part by `development/2026-07-31-platform-domain-util3/SPEC.md` §13** — that
> increment adds the plan/revert/excluded files. The checklist below is still the canonical one;
> only item 6's glob changed.

1. `git rm find-platform-domains-cloudflare find-platform-domains-cloudflare.py`
2. `git rm tests/unit/test_find_platform_domains_cloudflare.py`
3. `pyproject.toml`: remove the **two** `[tool.ruff.lint.per-file-ignores]` entries.
4. `pyproject.toml`: remove `"find-platform-domains-cloudflare.py"` from `[tool.pyright].include`.
5. `.claude/hooks/ruff-check.sh`: remove the `"$REPO_ROOT/find-platform-domains-cloudflare"` case
   arm and trim its comment back to naming only `find-platform-domains-dns`.
6. `.gitignore`: remove `/platform-domains-cloudflare*.json`.
7. `CLAUDE.md`: remove the `### find-platform-domains-cloudflare (temporary utility)` subsection.
8. Delete any leftover `platform-domains-cloudflare*.json` from working checkouts — the glob
   matters: the util3 increment made this **four** files (the inventory plus `-plan`, `-revert`
   and `-excluded`), and item 6's `.gitignore` entry was globbed for the same reason.

This folder stays — it is the historical record.

## 12. First live run

Run on **2026-07-30**, behind Task 7's STOP, with the operator's exact-phrase approval.

**The first attempt failed** — `exit=2`, no file written, aborted on one zone out of 187 after
3m09s. That failure is the most valuable thing this section records; see §13's live-run table.
The design was corrected (unique-id de-duplication; a shortfall warns instead of aborting) and
re-run.

| | |
|---|---|
| Command | `time ./find-platform-domains-cloudflare -v` |
| Exit code | **0** |
| Wall-clock runtime | **2m 17s** (the failed first attempt: 3m 09s) |
| Accounts / zones / records | 4 accounts, 187 zones, **22,911 unique records** read and inspected |
| Completeness cross-check | **192 of 192 paginated lists verified complete, 0 short, 0 unverifiable** |
| Re-reads triggered | none on the successful run (de-duplication alone closed the gap that had aborted the first) |
| Entries written | **218**, of which **5 DNS-only** — invisible to `fqdns.json` by construction |
| Unknown (`null`) proxy status | 0 |
| Entries with multiple origins | 0 (no duplicate-name warnings) |
| Output contract | all 218 entries carry exactly the eight keys; every origin ends `.pantheonsite.io`; every key normalized |
| `fqdns.json` cross-check | **0 discrepancies**, with `fqdns.json` 50.3 hours stale — every proxied platform CNAME this run found is also in that file |

**The runtime is ~2 minutes, not the sibling's ~38.** §8.3's "if a run ever becomes painful"
trigger for server-side `type="CNAME"` filtering is therefore moot, and §8.12's no-resume
decision is comfortably justified: a re-run costs two minutes.

**Cloudflare supplies `total_count` on every list** (§14 Q1 answered: 192 of 192), so the
completeness check is live rather than silently no-opping.

## 13. Claims this spec had to correct

Per `prompts/adversarial-review.md`: *"Record the author's own corrected claims in the document,
not just the fixes."* This is where this spec's own verification failed, and what caught it. **Two
rounds of adversarial review; 30 findings.**

### Round 1

| Claim as first written | Reality | Caught by |
|---|---|---|
| R6: "there is deliberately no exit 1", presented as exhaustive | Two reachable paths exited 1 with a raw traceback: `OSError` from the write and `ValueError` from `shlex.split` | Reviewer reproduced both |
| A `main()` test "would force a client-injection seam to exist for the test's benefit alone" (§5.5 of the pre-review draft) | **False.** The fresh-per-test fixture already makes `monkeypatch.setattr` free; the reviewer wrote and ran the three tests in ~25 lines with no production change. Exit 130 had **zero** coverage anywhere | Reviewer wrote the tests the spec called unaffordable |
| R2a explained the credential leak via `auth_headers` alone | Incomplete — `default_headers` is a second, independent route | Reviewer read the SDK past the first mechanism |
| The R2a test asserted `client.api_email is None` etc. | Implementation state, not the security property | Reviewer |
| Pagination was unmentioned and explicitly out of test scope | `dns.records.list()` is a paginator; a short read writes a silently incomplete file | Reviewer |
| R5's field set stopped at `record_id`/`proxied` | The same argument covers `ttl`/`comment`/`tags`/`settings`, which the reverse rewrite would discard | Reviewer |
| Task 1's `ruff check` "verifies the lint gate sees the new file" | A green check that could not go red at that point in the plan | Reviewer |
| Task 1 Step 2 expected a "collection ERROR" | Collection succeeds; the failure is 8 fixture errors | Reviewer, measured |
| "a record type that cannot be proxied has no `proxied` field" | False — every response model carries it | Reviewer, measured |
| Test counts 8 / 21 / 32 / 35 / 38 | Off by one per task | Author, after transcribing and running them |
| `Settings.model_dump()` returns `{"flatten_cname": True}` | It returns three fields. The *code* was right; the *assertion* was wrong, and pinning the whole dict would have pinned the SDK's model shape | Author, running the test before shipping |
| "stdout is unused" | argparse writes usage and `--help` there | Reviewer |
| R2 named the engine's "unknown substitution" branch | It reaches "no match found" (`configuration.py:98`) | Reviewer, tracing the engine |
| The zero-zones message blamed `DNS:Read` only | A missing `Account:Read` produces it too | Reviewer |

### Round 2 — including two the author's own verification had missed

| Claim | Reality | Caught by |
|---|---|---|
| The plan's per-task checkpoints were runnable | **They were not.** `./run-tests` gates ruff over the whole repo *before* pytest, and Task 1 declared the full import block while using only `re` — measured **10 × F401**, so Tasks 1–4 never reached their own tests. The author's round-1 evidence ran ruff only against the *finished* file, which is exactly why it missed this | Reviewer; author reproduced |
| R2a: "ambient values reach the wire by **two** routes… the pin closes **both**" | **Four** routes. `$CLOUDFLARE_CUSTOM_HEADERS` overrides the pin, and `$CLOUDFLARE_BASE_URL` **sends the pinned token to an arbitrary host** — strictly worse than the defect R2a was written to fix. Author reproduced: `Authorization: Bearer tok-123` delivered to `evil.example` | Reviewer; author reproduced |
| "The §7 tests are written to go red if the SDK changes" | True for R2a, **false for R3** — every pagination and error-text assertion ran against hand-built fakes, so an SDK change would leave all tests green and production silently truncating. Three real-SDK tests added | Reviewer |
| The truncation guard was correct as specified | It false-positives on a concurrent DNS edit and misdiagnoses it as "truncated", destroying a multi-minute run with no recourse. Now one re-read distinguishes the two causes | Reviewer |
| The truncation guard was complete | It covered records only; the **zone** and **account** lists paginate identically, and a short zone list omits every record in the missing zones | Reviewer |
| §14 asked whether the guard had run, but nothing reported it | A guard whose liveness is invisible is not a guard. Coverage is now printed at default verbosity | Reviewer |
| R6's exit-120 row named stderr only | `--help >/dev/full` exits 120 too | Reviewer, measured |
| `origins` is `fqdns.json`'s field "unchanged in name and type" | Same name and type, **different meaning** — `fqdns.json`'s holds every proxied record's content at a name, IP addresses included | Reviewer, against the live file |
| §13 cited "§5.5" | That section no longer existed after the round-1 rewrite | Reviewer |
| Task 6 wrote CLAUDE.md but committed only after the STOP | An operator who never approved the live run would leave the utility undocumented in git. Split into Tasks 6 and 7 | Reviewer |
| The glossary defined the platform suffix as fact | It is a scoping assumption; `*.gotpantheon.com` is not covered | Reviewer |
| §5 listed a `TypeError` write path | Not converted, but unreachable — now stated as unreachability, with the reason | Reviewer |
| The R2a test exported two ambient variables | Six exist; a regression dropping `user_service_key` from the pin would have stayed green | Reviewer |
| Script function order | Did not match task order, so staged Tasks 3–4 failed `F821`/`F401`. Reordered; §3 now states the constraint | Author, staging each checkpoint |
| The commit authorization and the LEDGER governance rule were asserted without provenance | Both now cite where they come from | Reviewer |

### Round 3 — three of these are re-instances of classes the rows above call fixed

| # | Claim | Reality | Caught by |
|---|---|---|---|
| 3.1 | R6's exit-code table, "there is deliberately no exit 1" | A **third** escape was live: `tomllib.load` decodes bytes itself, so a non-UTF-8 config raises `UnicodeDecodeError`, which is not a `TOMLDecodeError`. Rounds 1 and 2 fixed two *instances*; the *class* stayed open. Now closed at `ValueError`, their common base | Reviewer reproduced |
| 3.2 | R3: "when `total_count` is absent the check no-ops … it can never abort a healthy sweep" | True of the first read, **false of the re-read**, which fell through to the fatal branch and reported `truncated … of None` for a complete list | Reviewer reproduced |
| 3.3 | §6: "the guard reports its own coverage" (recorded as fixed in round 2) | A **partial** fix — coverage was reported for record lists only, while the account and per-account zone lists were cross-checked and their result discarded. Re-read notices were also `-v`-gated, making §14 Q3 unanswerable on a default run | Reviewer |
| 3.4 | `proxied` coerced with `bool(getattr(..., False))`, with a test pinning the coercion | `research.md`: *"`proxied: true` is the load-bearing field in both directions"*. A `null` flattened to `false` inflates the headline DNS-only count **and** tells a rewriter to re-create a proxied hostname unproxied — a TLS outage from an unreported coercion. Now stored verbatim, counted as `is False`, and any `null` named on stderr | Reviewer |
| 3.5 | §6's whole `-v` contract, and R6's "stdout carries only argparse output" | Neither was asserted anywhere — no test called `verbose=True`, and no test read `capsys…out`. The first exercise of the `-v` code would have been the live production run | Reviewer |
| 3.6 | Two section cross-references **inside shipped code comments** | `SPEC section 5.4` (no such section) and `a code section 6 does not use` (§6 is Observability; the exit table is R6). The same dangling-reference defect round 2 recorded as fixed, reintroduced into a permanent comment. Root cause: the document numbers both `§1…§14` and `R1…R8`, so `§6`/`R6` collide | Reviewer |
| 3.7 | R2a's "four routes", presented as exhaustive | Exhaustive for the SDK, not for the environment: httpx `trust_env=True` adds proxy and trust-store routes. Now stated as a scoped residual with the reason it is left open (§8.13), and the `SSL_CERT_FILE` `FileNotFoundError` — another exit-1 escape — converted | Reviewer |
| 3.8 | PD#7 (partial states / resumability) | Not addressed anywhere, not even to decline it. Now §8.12, with the reasoning and a revisit trigger | Reviewer |
| 3.9 | The unsupported-substitution error echoed the whole marker body | An `<{env NAME DEFAULT}` default can be a literal credential, so the message could put one on stderr and into operator logs. Now reports the *form* only — and the first fix still leaked the secret's path, which the test caught | Reviewer; author's own first fix was wrong |
| 3.10 | The glossary defined **custom domain** independently | `CONTEXT.md` already owns that term with a different definition (PD#11). Now cites it instead of restating it |

**The pattern worth carrying forward:** all three rounds' most serious findings were *unrun acceptance
criteria* — one summarized rather than executed (round 1's `main()`-test rationale), and one
executed only in its final state rather than at every checkpoint (round 2's `F401`). Running the
finished artifact is not the same as running the plan. Round 3 adds a third: **fixing the instance
and calling the class fixed** (3.1, 3.3, 3.6 are all re-instances of classes the earlier tables
record as closed). When a finding names a defect, the next step is to grep for every other
instance of that defect *class* before declaring it done.

### The first live run — a design defect no offline test could have found

The sweep aborted at exit 2 on its first real execution. Both rounds of the reviewer had examined
this guard; neither could have caught it, because it only appears against a zone large enough to
paginate deeply *while being written*.

| # | Claim | Reality | Caught by |
|---|---|---|---|
| L.1 | R3: a count mismatch means truncation or a concurrent change, and a re-read tells them apart | **A third cause dominates:** page-number pagination over an actively-written zone returns the *same record twice* while stepping over another. Measured on `umflint.edu` (18,848 records, 189 pages): 2 duplicates and 2 misses in a single walk. The re-read could not help — the artifact is systematic, not transient, so both reads disagreed and the guard escalated to fatal | The live run |
| L.2 | Comparing item count to `total_count` detects truncation | It fails in **both** directions on the same zone, minutes apart: `18840 items vs 18838` → false "truncated" abort; `18848 items vs 18848` → false **pass**, the duplicates and misses having cancelled exactly. The check blessed an incomplete read | Live probe of the zone |
| L.3 | A confirmed shortfall should be fatal ("writing the file anyway would ship a silently incomplete answer") | Correct in principle, unusable in practice: it discarded a 187-zone sweep over 2 records missed in one zone, and a paginated walk of a continuously-written zone may *never* be exactly complete. Now a loud per-list warning naming the count and the consequence, with the file still written — the operator's decision | The live run |
| L.4 | Duplicates were a counting nuisance | They are a **correctness** bug independent of the guard: a duplicate reaching the fold appends one record's origin twice and raises a *false* R7 duplicate-name warning, which R7 defines as a signal worth acting on | Follow-through from L.1 |

**Why this matters beyond this script:** every one of the 42 findings from the three review rounds
was found by reading or by running the code against *fakes*. This one needed production data with
a property no fixture had — scale plus concurrent writes. The offline suite now encodes it
(`test_read_all_deduplicates_records_repeated_across_pages`), but only because the live run
happened first. A spec that had shipped straight from review would have shipped a utility that
aborts on this organization every time.

## 14. Closing audit questions

Answered from the 2026-07-30 live run (§12) except where noted.

| # | Question | Answer |
|---|---|---|
| 1 | Did Cloudflare supply `total_count`? | **Yes, on every list** — 192 of 192 verified complete, 0 unverifiable. The check is live, not silently no-opping. |
| 2 | Runtime, and does §8.3 need revisiting? | **2m 17s** for 187 zones / 22,911 records. Server-side `type="CNAME"` filtering is unnecessary; §8.3 stands. |
| 3 | Were re-reads triggered, and how did each resolve? | **None on the successful run.** On the failed first attempt one fired and could not resolve — which is what exposed the design defect (§13, L.1–L.3). |
| 4 | Any duplicate-name warnings? | **None** — 0 entries with multiple origins. |
| 5 | Did the `fqdns.json` cross-check surface anything? | **No** — 0 discrepancies, with that file 50.3 hours stale. |
| 6 | Does the rewriter consume `ttl`/`comment`/`tags`/`settings`? | **Open** — the rewriter does not exist yet. Revisit §8.2 before the next such file is designed. |
| 7 | Any legacy `*.gotpantheon.com` targets? | **Not measured** — this sweep matches `.pantheonsite.io` only, per PROMPT line 7, so it cannot answer its own question. A one-line change to `PLATFORM_SUFFIX` would test it. **Worth doing once** before relying on the file for completeness. |
| 8 | The rewriter's staleness policy for this file? | **Open.** The file drives deletions and carries no capture timestamp; R5's rule is "regenerate immediately before any rewrite". At 2m 17s that is cheap. |
| 9 | `plugin/cloudflare/client.py`'s R2a defect — filed or fixed? | **FIXED 2026-07-30, commit `befb913`** (`pinned_client()`; see Amendment A2). Was "open, and live" when this row was written, hours earlier. |
| 10 | Any `null` proxy status? | **None** — 0 of 218. |
| 11 | Should the client use `trust_env=False`? | **Open** — operator decision (§8.13); the proxy/trust-store residual is unclosed. |
| 12 | Was a re-run needed after a partial failure? | **Yes, once** — the first attempt aborted and was re-run after the fix. At two minutes the no-resume decision (§8.12) held up. |

## 15. Reviewer Concerns (open after the 3-round review cap)

`prompts/adversarial-review.md` caps the loop at three iterations. These survived it — each is
recorded rather than fixed, with the reason. None blocks implementation; all are cheap to close
later, and a reader should know they are known.

1. **`R1`–`R8` and `§1`–`§14` collide in the same document.** Round 3 finding 3.6 traced two
   dangling cross-references (one shipped inside a code comment) to this root cause: `§6` is
   Observability while `R6` is the exit-code table. Both references are fixed, but the collision
   itself is not — renumbering `R1`–`R8` to `§2.1`–`§2.8` touches ~40 call sites across the
   document and the code comments, and doing it after the code blocks were verified would mean
   re-verifying purely for cosmetics. **Do it before the next substantive edit, not during
   implementation.**
2. **§13's round-1 and round-2 rows are unnumbered**, so the three code comments citing
   *"adversarial review, finding 3"* / *"round 2, finding 3"* resolve to nothing from the
   artifact. Round 3's rows are numbered (3.1–3.10). Numbering the earlier two tables would
   invalidate nothing but was not worth another verification cycle.
3. **`trust_env` residual (R2a).** Closing the httpx proxy / trust-store routes with
   `http_client=httpx.Client(trust_env=False)` is one line, but would break legitimate deployments
   behind a corporate proxy. Recorded as §8.13 and §14 Q11 — an operator decision, deliberately
   not taken here.
4. **`CONTEXT.md` does not yet carry `DNS-only`.** PD#11 asks for domain terms to be written there
   *"the moment it crystallizes"*. Deferred to when the utility actually lands, since the term
   only exists once the script does; the glossary flags it.
5. **`pytestmark = pytest.mark.unit` on a file whose write tests do real filesystem I/O**, against
   that marker's registered description. Consistent with existing repo practice (the sibling's
   suite does the same), so changed nowhere rather than changed here alone.
6. **Task 7 Step 3 assumes `fqdns.json` exists** and will raise `FileNotFoundError` if it does
   not. It is a hand-run step behind the STOP, and the failure is self-explanatory.

---

# Amendment A1 — zone selection and stdout output (2026-07-31)

Authorized by the operator in session, after the utility shipped. This amendment **supersedes**
`R1`, parts of `R5`/`R6`, and `§8.1`/`§8.4`; everything it does not name is unchanged. It is
appended rather than spliced so the diff against the shipped baseline stays readable.

## A1.1 — Why

Two independent requests, settled in one design pass:

1. **Sweep only named zones.** A full sweep is 187 zones / 22,911 records / 2m17s (§12). An
   operator checking one or two zones — during a rewrite, or verifying a fix — should not pay for
   the whole organization.
2. **stdout is the result stream.** `-o`/`--output` writes a file; without it the JSON goes to
   stdout. The operator's stated reason: the pre-rewrite baseline step becomes an explicit
   redirect, so the canonical file can only ever be produced deliberately.

The second request is what makes the first safe. The shipped design had one output path and one
filename, so a subset run would have silently overwritten the organization-wide file with a
two-zone subset of identical shape — the "silently under-reports" failure `§8.12` names as the
one this design is organized against. With stdout as the default, the *default* subset run
produces a stream, not an artifact, and the canonical file is written only when someone names it.

**This narrows the hazard; it does not close it**, and the amendment initially over-claimed that
it did. `-o platform-domains-cloudflare.json engin.umich.edu` and
`… engin.umich.edu > platform-domains-cloudflare.json` each still produce a file byte-shape-
identical to a full sweep, with no in-band marker of scope — and the redirect form is invisible to
the program entirely. `summarize()` therefore emits a loud `ATTENTION: … covers N of M zones … MUST
NOT be used as the baseline for a rewrite` whenever a narrowed sweep is written with `-o`. The
redirect form cannot be detected at all; that residual is stated here rather than papered over.

## A1.2 — R1 (superseded) — CLI

```
find-platform-domains-cloudflare [-c CONFIG] [-o OUTPUT] [-v] [ZONE ...]
```

| Arg | Default | Meaning |
|---|---|---|
| `ZONE ...` | none — every zone | zone names to sweep; DNS records are read for these zones only |
| `-o`, `--output` | none — stdout | write the JSON here, atomically, instead of to stdout |
| `-c`, `--config` | `pantheon-sitehealth-emails.toml` | unchanged |
| `-v`, `--verbose` | off | unchanged |

`allow_abbrev=False` still holds. `ZONE` is the first positional argument this script has had.

## A1.3 — R9 (new) — Zone selection

Zone names are resolved **client-side**, against the zone list `list_zones()` already builds:

1. `list_zones()` runs unchanged — accounts, then zones per account, each through `read_all`'s
   completeness cross-check.
2. `select_zones(zones, requested)` filters that list.
3. Records are read for the selected zones only.

**Rejected alternative: server-side `client.zones.list(name=Z)` per name.** It skips the accounts
walk and is fewer requests, but it would have to replicate the completeness cross-check per name,
it loses the `0 zones ⇒ missing Account:Read/DNS:Read` guard, it loses the account count the
summary prints, and an unmatched name degrades to a bare "0 zones" with no context. The listing
it avoids is the *cheap* half: measured, records are 22,911 reads against 187 zones. Filtering
client-side buys better errors and the existing guards for a few seconds.

Rules:

- **Matching is exact, on `normalize()`d names**, both sides — so case and a trailing root dot are
  ignored, consistent with every other name comparison in this script. No globbing, no suffix
  matching (`§A1.7`).
- **Duplicate names on the command line are de-duplicated silently**, order preserved. Unlike a
  duplicate *record* (`R7`), a repeated CLI argument has no consequence worth a warning.
- **One name may match more than one zone** (the same name in two accounts). All matches are
  swept; the existing cross-zone duplicate warning in `collect_entries` still fires if they both
  hold a platform CNAME.
- **Any unmatched name is fatal** (`StartupError`, exit 2), and the message names **every** miss,
  not the first. An operator with three typos fixes three in one round trip. This is the guard
  that replaces `§A1.4`'s zero-zone check on the filtered path — a typo that silently produced a
  short sweep is precisely the under-reporting failure this design refuses to have.
- Selection order is **the order the operator gave**, so `-v` progress reads in the order they
  asked for.

## A1.4 — R3 addendum — the zero-zone guard

`list_zones()`'s "0 zones is fatal" check is unchanged and still runs **before** selection, so a
credential missing `Account:Read`/`DNS:Read` is still caught by its own message. On the filtered
path the unmatched-name error of `A1.3` is what catches a name that cannot be found, and it is
strictly more informative.

## A1.5 — R5/R6 (amended) — output routing and streams

`R5`'s JSON shape is unchanged. What changes is where it goes, and that stdout is now a result
stream — which reopens the exit-code question `§8.4` declined.

- `emit(entries, path)`: `path` given → the existing `write_json_atomic()`, untouched; `path`
  `None` → the same bytes to stdout. Both go through one `dump_json()` so the two forms are
  **byte-identical**.
- **`§8.4` is superseded.** It declined the sibling's doomed-stream machinery on the grounds that
  "here the result is a file". That premise no longer holds. Ported:
  - `require_usable_streams(output)` — refuses up front when `sys.stdout is None` and no `-o` was
    given (nowhere to write the JSON), and whenever `sys.stderr is None`. The second is the worse
    case and is **measured, not assumed**: `print(file=sys.stderr)` with `sys.stderr` set to
    `None` falls back to `sys.stdout`, so with stderr closed every progress line, warning and
    summary would be interleaved into the JSON on stdout.
  - `point_at_devnull(stream)` — copied verbatim from the sibling.
  - The stdout write is a **single call at the end**, so the sibling's flush-probe variant of
    `detach_doomed_stdout()` is deliberately **not** ported: `dump_json()` plus an explicit
    `flush()` inside `except OSError` *is* a real failed write, which is the proof the sibling's
    stderr twin already uses. Never detach a stream a real write has not proven doomed — an
    unconditional detach repoints pytest's own captured stdout at `/dev/null`.
  - `report_line(text)` — the guarded stderr writer, used by `main()`'s end-of-road reporters.
  - **`main()` MUST carry an `except OSError` arm**, reporting through `report_line` and returning
    2. This was missed on the first pass and is the defect the sibling had already paid for: the
    other three arms cover only *error* paths, so an ENOSPC on a **success**-path stderr write —
    the duplicate-name warnings, the summary, the cross-check line, `note()`/`warn()` inside the
    walk — escaped `main()` entirely and the shutdown flush turned a *completed* sweep into 120,
    with valid JSON already on stdout. Measured both ways: 120 without the arm, 2 with it.
    Catching alone is **not** sufficient — the buffered write is retried at shutdown — so the
    report must go through `report_line`'s detach. Pinned by
    `test_a_doomed_stderr_on_the_success_path_exits_2_not_120`, which drives the **success** path;
    a test driving only the missing-config path is green against a program that still exits 120.
- **Exit codes are unchanged**: 0 written, 2 could not complete, 130 interrupted. A doomed stdout
  or stderr now yields **2**, not the interpreter's 120.
- **The stated exception stands**: argparse writes its usage/`--help` text before any guard
  exists, so `--help >/dev/full` still exits 120. Same call as the sibling's, same reason.

## A1.6 — §6 addendum — observability

The summary line distinguishes a subset run from a full sweep, so the two can never be confused
in a log:

```
Wrote 12 platform-domain CNAMEs (2 DNS-only, invisible to fqdns.json) from 1842 records
in 2 of 187 zones in 1 account(s) to standard output.
```

`in N of M zones` appears only when `N != M`; a full sweep keeps reading `in M zones`. The
destination is named literally (`standard output`, or the `-o` path).

## A1.7 — NOT in scope (additions to §8)

14. **Matching a zone by id.** Names are what an operator has; `§A1.3`'s error names the misses.
15. **Glob or suffix matching** (`*.umich.edu`). Exact matching cannot silently over-select, and
    an over-selecting typo on a destructive-rewrite input is the expensive direction.
16. **Resumability**, still — `§8.12`'s conclusion stands (naming the zones *is* the manual
    resume), but its *premise* — "there is no partial artifact" — no longer holds on the redirect
    path, where the shell truncates the target before the sweep starts and a failed run therefore
    leaves a zero-byte file where the baseline was. This is why `-o` (temp file + `os.replace`,
    written only on success) is the **recommended** baseline recipe in `--help` and in CLAUDE.md,
    and `>` is documented as the lossy alternative rather than the headline.
17. **Reading zone names from a file** (`@zones.txt`). The shell already does this with `$(cat …)`.

## A1.8 — Test plan additions (§7)

All offline, against the existing `FakeCloudflareClient`. Seams: `select_zones` (pure),
`fetch_platform_cnames`, `emit`, `require_usable_streams`, `main()`, plus **two** subprocess cases
(A12 and A16 — the shutdown flush that produces exit 120 cannot be observed in-process).

| # | Test | Pins |
|---|---|---|
| A1 | selects the named zones, in the order given | `A1.3` |
| A2 | normalizes case and the trailing dot on both sides | `A1.3` |
| A3 | de-duplicates a repeated name, order preserved | `A1.3` |
| A4 | keeps every zone when one name matches two | `A1.3` |
| A5 | an unmatched name is fatal and names **every** miss | `A1.3` |
| A6 | records are read for the named zones **only** (the others are never queried) | `A1.3` |
| A7 | an unfiltered run still sweeps everything | regression |
| A8 | `-o` and stdout produce byte-identical JSON | `A1.5` |
| A9 | the summary says `N of M zones` only on a subset run | `A1.6` |
| A10 | a closed stdout with no `-o` is a named exit 2 | `A1.5` |
| A11 | a closed stderr is a named exit 2 | `A1.5` |
| A12 | a doomed stdout (`> /dev/full`) exits **2**, not 120 — **real subprocess** | `A1.5` |
| A13 | a healthy stdout is never detached — `os.dup2` spy over a **real fd** | `A1.5` |
| A14 | a healthy **stderr** is never detached by `report_line` — the missing twin | `A1.5` |
| A15 | a doomed stdout/stderr **is** detached (the positive half of A13/A14) | `A1.5` |
| A16 | a doomed stderr on the **success** path exits 2, not 120 — real subprocess | `A1.5` |
| A17 | the zero-match ATTENTION names the real destination, never a file that was not written | `A1.6` |
| A18 | an interrupt **after** a successful stdout write does not claim nothing was produced | `A1.5` |
| A19 | a subset written with `-o` warns it is not an organization-wide sweep | `A1.1` |
| A20 | `write_json_atomic` serializes through `dump_json` — the DRY claim, enforced | `A1.5` |

A13/A14 are the mutation guard the sibling learned the hard way, and the first implementation of
A13 **could not go red**: driven over `capsys`, `fileno()` raises `io.UnsupportedOperation`, which
`point_at_devnull`'s `contextlib.suppress` swallows before `os.dup2` is ever reached — so the
mutation "detach unconditionally" stayed green (verified by mutating the script and re-running).
They must spy on `os.dup2` and drive over a **real** file descriptor. A12 likewise must be a
subprocess: pytest never tears the interpreter down, so the shutdown flush that produces 120 never
runs in-process, and an in-process test asserting a raised `StartupError` pins the wrong thing.

## A1.9a — Task 7 is superseded

**Task 7's live-verification procedure MUST NOT be run as written.** Step 1 is
`time ./find-platform-domains-cloudflare -v` with no `-o` and no redirect, so under this amendment
the JSON goes to the terminal and no file is produced; Steps 2–3 then `json.load()`
`platform-domains-cloudflare.json`. On a clean checkout that is a `FileNotFoundError`, and — worse
— in the operator's working directory, where the 2026-07-30 sweep left that file, **Steps 2 and 3
would validate the stale 2026-07-30 artifact and print a green cross-check**: an acceptance
criterion that passes without testing the run it claims to test (PD#14).

Replace Step 1, and add a Step 0 that moves any existing file aside so a stale one cannot satisfy
Steps 2–3 (`-o`, not `>`, per `§A1.7` item 16). Task 7 now carries this banner inline:

```bash
mv -n platform-domains-cloudflare.json platform-domains-cloudflare.json.bak   # Step 0
time ./find-platform-domains-cloudflare -v -o platform-domains-cloudflare.json ; echo "exit=$?"
```

## A1.9 — Live verification (COMPLETED 2026-07-31)

Cloudflare's API returned HTTP 521/522/523 for the first part of this session (incident
*"Cloudflare API Availability Reduced"*, opened 2026-07-31T11:51Z; reproduced with `curl`
independently of this script, so the utility was correctly reporting a real outage as exit 2).
The incident cleared later the same day and the verification below was then run for real.

**Full sweep** — `./find-platform-domains-cloudflare -o <scratch>/full.json -v`

```
Wrote 218 platform-domain CNAMEs (5 DNS-only, invisible to fqdns.json) from 22632 records
in 187 zones in 4 account(s) to <scratch>/full.json.
Completeness cross-check: 192 of 192 paginated lists verified complete, 0 short, 0 unverifiable.
exit=0                                                            real 2m45.473s
```

Against §12's 2026-07-30 first live run: **identical** account (4), zone (187), entry (218) and
DNS-only (5) counts, and 192 of 192 lists complete again. Record count moved 22,911 → 22,632,
which is expected — zones are continuously written. No `-o` file was written over the operator's
existing baseline; the sweep went to a scratch path.

**Subset sweep** — the two zones holding the most entries (`umich.edu`, 99; `engin.umich.edu`, 55)

```
[1/2] zone umich.edu -- 683 records
[2/2] zone engin.umich.edu -- 635 records
Wrote 154 platform-domain CNAMEs (0 DNS-only) from 1318 records in 2 of 187 zones in 4 account(s)
  to standard output.
Completeness cross-check: 7 of 7 paginated lists verified complete, 0 short, 0 unverifiable.
exit=0                                                            real 0m7.963s
```

**The subset output is byte-for-byte identical to the full sweep's slice for those two zones**
(`diff` of `{k: v for k, v in full if v["zone_id"] in {the two ids}}` against the subset output:
no differences). 154 = 99 + 55. Runtime 8s against 2m45s — the narrowing does what it exists for.

**Everything else, measured live against the recovered API:**

| Check | Result |
|---|---|
| `stdout` vs `-o` for the same zones | byte-identical, 73,168 bytes |
| subset written with `-o` | `ATTENTION: … covers 2 of 187 zones … MUST NOT be used as the baseline` |
| full sweep written with `-o` | no such ATTENTION (0 occurrences) |
| `UMICH.EDU.` twice (case + trailing dot + duplicate) | `1 of 187 zones`, 99 entries — normalized and de-duplicated |
| two unmatched names | exit 2, **both** named, zero records read |
| `>/dev/full` | exit 2, `cannot write the JSON to standard output: [Errno 28]` |
| `2>/dev/full` (success path) | exit 2 |
| `>&-` / `2>&-` | exit 2, each named |
| `\| head -1`, 73 KB payload | exit 2, `[Errno 32] Broken pipe` — the document was genuinely not delivered, so "could not complete" is correct |
| `\| head -1`, payload under the 64 KB pipe buffer | exit 0 — no write ever fails |
| `--bogus` | exit 2 (argparse) |

Offline suite at the same commit: **1301 passed, 3 skipped**, ruff and pyright gates green.


---

# Amendment A2 — the R2a defect in the main program is fixed (2026-07-31)

## A2.1 — What changed

`§8` item 7 and `§14` Q9 recorded `plugin/cloudflare/client.py`'s ambient-environment defect as
**open and live**, and `R2a`'s blockquote said `$CLOUDFLARE_BASE_URL` was "exploitable against the
main program today". All three were true **when written**. They stopped being true hours later, on
the same day: commit **`befb913` (2026-07-30), "fix(cloudflare): pin the shared client against the
ambient environment"**, added `pinned_client()` to `plugin/cloudflare/client.py` and 97 lines of
test to `tests/integration/test_plugin_cloudflare_client.py`.

Verified 2026-07-31 by building a real request with **all six** SDK-read variables set hostile —
`CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_API_KEY`, `CLOUDFLARE_EMAIL`,
`CLOUDFLARE_API_USER_SERVICE_KEY`, `CLOUDFLARE_BASE_URL=https://evil.example/v4`, and a
`CLOUDFLARE_CUSTOM_HEADERS` injecting `X-Auth-Email`/`X-Auth-Key` — against a config supplying only
`api_token`:

```
URL the request actually goes to : https://api.cloudflare.com/client/v4/zones
Authorization                    : Bearer REAL-CONFIGURED-TOKEN
X-Auth-Email present             : False
X-Auth-Key present               : False
```

All four routes closed. `tests/integration/test_plugin_cloudflare_client.py`: 9 passed.

## A2.2 — Why this amendment exists at all

The stale claims were not harmless. `CLAUDE.md` had **contradicted itself** since 2026-07-30 —
`§Cloudflare auth + shared client` said `pinned_client()` "closes all four", while the
`find-platform-domains-cloudflare` subsection said the plugin "has all four routes open … exploitable
against the main program today". A session on 2026-07-31 read the second, believed it, and reported
a **phantom vulnerability** to the operator as a closing recommendation. That is the measured cost:
a document that makes its reader *less* accurate than no document.

Root cause, and the reason the fix is structural rather than a wording correction: **the same fact
was stated in full in two places.** `CLAUDE.md`'s utility subsection now **cross-references** the
canonical description instead of restating it — the Spine's own rule, *"Each rule stated once and
cross-referenced elsewhere (DRY)"*, and exactly the drift `CLAUDE.md` already warns about for
`prompts/`. The utility's `build_client()` docstring likewise now points at `pinned_client()` and
states the two-copy relationship, rather than asserting the plugin's status.

## A2.3 — What is deliberately NOT changed here

`Task 2`'s code listing (`~:1102`) and `Task 6`'s CLAUDE.md text block (`~:2272`) still contain the
old wording. They are **verbatim records of what was authored at the time**, in an implementation
plan that was already executed; rewriting them would falsify the archive rather than correct it.
Only the *normative* and *status* statements — `R2a`'s blockquote, `§8` item 7, `§14` Q9 — carry
resolution banners, because those are the ones a reader consults to answer "is this open?".

## A2.4 — Residual, unchanged

- **Two independent copies of the pin** (`pinned_client()` and the utility's `build_client()`),
  both measured against cloudflare 5.4.0. Deliberate: the utility imports nothing from `plugin/` so
  its deletion stays `git rm` of three files (`§14`). An SDK upgrade must re-verify **both**; each
  has its own test asserting a **real built request**, so either breaking goes red.
- **`cloudflare` is declared unpinned** in `pyproject.toml`. `§8` item 10's rejection of pinning
  stands, and the operator declined a compatible-range pin on 2026-07-31 with a stated reason: all
  dependencies are being updated to latest within days, so a range pin would be immediately
  re-litigated. The real-request tests are the mitigation, as `§8` item 10 always intended.
- **`trust_env=True`** (`§8.13`) — `$HTTPS_PROXY` / `$SSL_CERT_FILE` still influence transport.
  Unchanged operator decision. Note the risk shape is weaker than the closed route: `$HTTPS_PROXY`
  alone leaks only the `CONNECT` hostname (`api.cloudflare.com`, not a secret); reading the token
  needs a poisoned `$SSL_CERT_FILE` as well.

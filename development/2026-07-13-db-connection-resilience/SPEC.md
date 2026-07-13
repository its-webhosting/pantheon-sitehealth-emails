# Database Connection Resilience — Spec

**Status:** approved design, revised after two rounds of adversarial review
**Date:** 2026-07-13
**Prompt:** conversational (this folder is the record; see `prompts/new-feature-standards.md`
for the standards this spec was written against, and `prompts/adversarial-review.md` for the
review it went through)

---

## Glossary

Each term is used in exactly one sense throughout this document.

| Term | Meaning |
|---|---|
| **gather** | The per-site work between the traffic `SELECT` and the overage-protection lookup: `terminus`, WP-CLI, Drush, DNS resolution, Cloudflare cache checks, matplotlib rendering. Minutes per site; touches no database. |
| **idle window** | A period during which a MySQL connection is checked out of the SQLAlchemy pool, has an open transaction, and is sending no traffic. The bug. |
| **middlebox** | Any stateful network device between the container and RDS that keeps per-flow state: Docker Desktop's VM NAT, the U-M border NAT/firewall. |
| **unit of work** | An idempotent function that performs one database interaction from start to commit, and can be re-run from scratch after a rollback with identical results. The granularity at which retries happen. |
| **release** | Ending a transaction (`commit()`) so the `Session` returns its connection to the pool. **Not** the same as closing a socket — the pool keeps it open. |
| **reap** | A middlebox silently discarding an idle flow's state entry. |
| **epilogue** | The end-of-run work: close the session, print the totals, and on `--all` write `{ymd}-notices.csv` and `{ymd}-results.json`. Becomes `finish_run()`. |
| **abort** | A deliberate early exit: the database failed unrecoverably, or the operator pressed Ctrl-C. Flushes the epilogue, prints a re-run command, exits nonzero. |

**MUST / MUST NOT** — required; a violation is a defect.
**SHOULD** — required unless there is a stated reason not to.
**MAY** — optional.
**NEVER** — a prohibition that holds without exception.

---

## 1. The failure

Three separate `--all` runs died after >1 hour with:

```
sqlalchemy.exc.OperationalError: (MySQLdb.OperationalError)
(2013, 'Lost connection to server during query')
[SQL: SELECT ... FROM pantheon_overage_protection WHERE site_id = %s AND month = %s]
```

crashing at `pantheon-sitehealth-emails:3280`, `db_session.get(PantheonOverageProtection, …)`.

### 1.1 Root cause

The program holds **one `Session` for the entire run** (`pantheon-sitehealth-emails:1302`).
Inside the per-site loop:

| Line | What happens | Connection state |
|---|---|---|
| `:1579` | `db_session.commit()` after the metrics merge | released to pool |
| `:1625`–`:1632` | traffic `SELECT` for the report | **checked out; transaction opened** |
| `:1632`→`:3280` | **the gather** (minutes; no DB work) | **checked out, idle, in transaction** |
| `:3280` | `db_session.get(PantheonOverageProtection, …)` | first use of the idle connection |
| `:3380` | `db_session.commit()` | released to pool |

The connection is never released after the read, so it sits idle for the whole gather. A middlebox
reaps the flow; the program discovers this only when it next writes to the socket, at `:3280`.
Writing to a reaped flow yields error **2013 ("lost connection *during query*")** rather than
2006 ("server has gone away") — the signature of a middlebox dropping state, not of a server
closing a connection politely.

### 1.2 Facts verified (not assumed)

Independently re-verified across two adversarial review rounds, against the code and against
SQLAlchemy 2.0.51 as installed in `.venv`.

| Claim | How it was checked | Result |
|---|---|---|
| RDS is closing the connection | `SHOW VARIABLES LIKE '%timeout%'` on the production instance | **Refuted.** `wait_timeout = interactive_timeout = 28800` (8h). No gather runs for 8 hours. The database is exonerated. |
| The crash line is the first DB call after the gather | read `:1625`–`:3280` | **Confirmed.** No DB access occurs in between. |
| The host sleeping could explain it | operator confirmed | **Refuted.** Container on a host that never sleeps. |
| Network path crosses stateful devices | operator confirmed topology | **Confirmed.** Container (Docker Desktop, U-M network) → AWS RDS, us-east-1. At least two NAT/firewall hops, neither under our control. |
| `pool_pre_ping` fires **only at pool checkout** | `sqlalchemy/pool/base.py:265` — "emit a ping … **upon checkout**" | **Confirmed.** This is why pre-ping alone cannot fix the bug (§1.3). |
| `Session.commit()` releases the connection to the pool | empirical: `query().all()` → `in_transaction() is True`; after `commit()` → `False` | **Confirmed.** |
| `Session.rollback()` discards pending ORM changes | empirical | **Confirmed.** Forces unit-of-work retry granularity (§3.3.1). |
| **`Session.rollback()` also EXPIRES every loaded object**, regardless of `expire_on_commit` | empirical: after rollback, a loaded object reports `expired is True` | **Confirmed, and load-bearing.** See §3.3.2 — why `load_traffic_rows()` returns plain data. |
| A failed transaction raises `PendingRollbackError` until rolled back | empirical | **Confirmed.** |
| `expire_on_commit=False` is safe for these models | read `:96`, `:119` | **Confirmed.** Composite natural primary keys, no server defaults, no autoincrement, no triggers. It is not merely safe but **required**: the report reads those rows at `:2856`, after the new release commit. |
| `expire_on_commit=False` introduces no staleness | empirical: an out-of-band `UPDATE` followed by `query().all()` returned the **new** value — a query repopulates non-expired identity-map instances | **Confirmed.** |
| Only `traffic_table_rows` / `site_plan_start` escape the overage block | scanned every local of `:3278`–`:3380` against lines 3381–3969 | **Confirmed.** `d`, `plan`, `op`, `op_remaining`, `month`, `ymd` are all dead after the block; `site_plan_start` is read at `:3395`/`:3417`. |
| Wrapping the site loop in `try:` is semantically inert | `continue` binds to the `for`; `sys.exit` raises `SystemExit`, a `BaseException` | **Confirmed.** |
| The epilogue spans `:3932`–`:3967` | read it | **Confirmed** — **not** `:3931`–`:3963`, which truncates a `print(` mid-statement and omits both the non-`--all` `else:` branch and `sc.debug("Done!")`. An earlier draft got this wrong. |
| `visits_by_month` can be empty | read `:2848`–`:2853` | **Refuted.** Every month in the window is pre-seeded to `0`, so `{}` is unreachable. An earlier draft specified a shadow path for it; §3.7 now specifies the real zero-traffic case. |
| **The aborting site is absent from `site_results`** | read `:1833` (WordPress) and `:2152` (Drupal) | **REFUTED — and this refutes an earlier draft of this very spec.** `site_results[site["name"]]` is written **during the gather**, ~1,400 lines *before* the crash point. The failing site is therefore already in `site_results` (but **not** in `all_warnings`, which is appended at `:3922`, at the end of a successful site). §3.5 handles this explicitly; it is why `abort_run()` pops the site. |
| `--resume-from` works without `--all` | read `:1236`–`:1238` | **Refuted.** `main()` hard-exits: "`--resume-from can only be used together with --all.`" A resume hint printed on a non-`--all` abort would fail when pasted. §3.5.1 prints a *re-run* command instead. |
| The positional site list is `sc.options.sites` | read `:154`–`:158` (`nargs="*"`, dest `sites`) | **Confirmed.** |
| `site_name` (the loop variable) is the key `site_results` is written under | `site_name_to_id = {site["name"]: id}` (`:1367`), `site = sites[site_id]` (`:1389`), `site_results[site["name"]]` (`:1833`, `:2152`) | **Confirmed.** `site_results.pop(site_name)` targets the right key on every path. |
| The aborting site is always one the operator requested | read `:1402` — a non-`--all` run iterates **every org site** and `continue`s the unrequested ones | **Refuted.** A `KeyboardInterrupt` can land on a site the user never asked for (or before the loop body runs at all, leaving `site_name = None`). `abort_run()` MUST guard both — see §3.5.4. |
| Nothing inside the site loop swallows our exceptions | grepped `:1387`–`:3931` for `except` | **Confirmed.** No `except` clause exists in the loop body, so `OperationalError` / `DatabaseUnavailableError` / `KeyboardInterrupt` always reach the new handler. |
| `op_lookup`'s `session.get()` still emits SQL after the change | SQLAlchemy identity-map semantics with `expire_on_commit=False` | **Refuted — and this is *why* the goldens hold.** The commit at `:3380` leaves the just-written `PantheonOverageProtection` rows **un-expired** in the identity map, so `op_lookup` becomes an identity-map hit emitting no SQL for those months. The values are identical (the session just wrote them), and `plan_costs` (`:1001`–`:1003`) reads `op.used_this_month` immediately and never holds a row across a later retry. Fewer queries, same bytes. |
| A run that aborts has emailed every site before the failure and none after it | true for the database abort (it can only fire at `:3280`, before the send at `:3916`–`:3920`); **false for Ctrl-C**, which can land *after* `send_message()` | **Partially refuted.** See §3.5.3 — this is why the interrupt path tracks whether the site was emailed. |

### 1.3 Hypotheses considered and rejected

- **"The connection is open too long overall; recycle it every 10 sites."** (The operator's
  initial suspicion.) **Rejected:** the fatal idle window is *inside a single site*, so a
  site-boundary recycle never touches it. Additionally, `Session.close()` alone would not even
  reconnect — it returns the connection to the pool, which keeps the socket open and hands the
  same reaped connection back. Only `Engine.dispose()` drops it.
- **"`pool_pre_ping=True` fixes this."** **Rejected as a standalone fix.** Pre-ping validates a
  connection at **pool checkout** (verified, §1.2). Across the gather the session never checks its
  connection back in, so no checkout occurs and pre-ping never runs. It becomes effective *only*
  after §3.1 releases the connection — the two changes are a set, not alternatives.
- **"Retry on `OperationalError`."** **Rejected as a standalone fix** (kept as a second layer,
  §3.3): it leaves the idle window in place, pays a doomed round-trip on every slow site, and —
  at the wrong granularity — silently corrupts data (§3.3.1).

---

## 2. Scope

### 2.1 In scope

1. Eliminate the idle window (§3.1).
2. Make the pool self-healing (§3.2).
3. Retry lost connections at an idempotent unit-of-work granularity (§3.3), with no
   `OperationalError` able to escape un-named (§3.3.3).
4. On an unrecoverable database error **or a Ctrl-C**: flush the epilogue, print a command that
   re-runs exactly what is left, exit nonzero (§3.5).
5. Observability: every reconnect visible on the console *and* in the run's artifacts, attributed
   to the site that caused it (§3.6).
6. Tests at unit / integration / e2e (§5).

### 2.2 NOT in scope (decided, with rationale)

| Rejected | Why |
|---|---|
| TCP keepalive sysctls in `.devcontainer/devcontainer.json` | Operator decision: code fix only. A sysctl is environment-specific, protects no other institution running this tool, and silently does nothing if the container is launched another way — it would make the real fix look optional. (`libmysqlclient` already sets `SO_KEEPALIVE`; only the sysctl is missing, and MySQLdb exposes no per-connection way to set it.) |
| `[Database]` config keys for `pool_pre_ping` / `pool_recycle` / retry count | Operator decision: hardcode. YAGNI until a real operator hits a shorter middlebox timeout. |
| Per-site containment (skip a failing site, continue the run) | Operator decision: abort instead. A DB failure is worth a human's attention; `--resume-from` makes the lost work cheap to recover. |
| Distinguishing a disconnect from other `OperationalError`s (deadlock 1213, lock-wait 1205, too-many-connections 1040, access-denied 1045) | **Deliberate:** all are retried once and, on a second failure, abort. MySQLdb surfaces them through the same exception class, and error-code sniffing is a fragile denylist. The consequence is stated where it shows: the abort message says "a database operation failed and could not be retried" — **not** "the database is unavailable" — and always prints the underlying error, which names the real cause. |
| Session-per-unit-of-work restructuring of `main()` | The better long-term shape, but a materially larger diff than this bug justifies today. See §7 — the `TrafficRow` change (§3.3.2) is a deliberate down payment on it. |

---

## 3. Design

### 3.1 The invariant

> **MUST: no MySQL connection is held checked-out across non-DB work.**

This one sentence is the fix. Everything else supports it.

```
TODAY (broken)                          AFTER
──────────────                          ─────
:1579  commit  ── conn → pool           :1579  commit  ── conn → pool
:1625  SELECT  ── conn ← pool ┐         :1625  SELECT  ── conn ← pool
                              │                commit  ── conn → pool   ← NEW (§3.1)
  terminus / wp / drush       │           terminus / wp / drush
  DNS / cachecheck / sleeps   │ IDLE      DNS / cachecheck / sleeps       (no conn held)
  matplotlib                  │ 2-20m     matplotlib
                              │
:3280  get()   ── conn ✝ DEAD ┘         :3280  get()   ── conn ← pool  ← pre_ping validates
                                                                          and silently replaces
:3380  commit                           :3380  commit  ── conn → pool     a reaped connection
```

**The commit after the traffic `SELECT` MUST NOT be removed.** It reads like a redundant commit
of a read-only query; it is the bug fix. A code comment MUST say so, and
`test_load_traffic_rows_releases_the_connection` (§5) MUST fail if it is deleted.

`expire_on_commit=False` on the `sessionmaker` accompanies it: without it, that commit would
expire the just-loaded rows and the report's read at `:2856` would silently re-SELECT them.
Verified safe, necessary, and staleness-free in §1.2.

### 3.2 Pool settings

The MySQL branch of the engine kwargs (`pantheon-sitehealth-emails:1292`) gains
`pool_pre_ping=True` and `pool_recycle=1800`, with a comment stating why (the remote DB and the
reaping middleboxes). The sqlite branch **MUST** remain `{}` — these settings are meaningless for
a local file and would obscure the e2e goldens' behavior. The construction is extracted to a pure
helper `db_engine_args(db_config) -> (str, dict)` so the settings are unit-testable; behavior is
otherwise unchanged, including the `sys.exit()` on an unsupported `type` and the unconditional
`KeyError` on a missing `type`/`name` (documented in `CLAUDE.md`).

### 3.3 The retry layer

```python
class DatabaseUnavailableError(RuntimeError):
    """A database operation failed, was retried once, and failed again."""


def db_retry(session, unit, *, what: str, site: str = None):
    """Run `unit()`; on an OperationalError, roll back and re-run it exactly once."""
```

- Catches **`sqlalchemy.exc.OperationalError` only.** **NEVER** `except Exception`, **NEVER** a
  bare `except`. `ProgrammingError` (bad SQL) and `IntegrityError` (a real data bug) MUST
  propagate un-retried — retrying them would convert a loud bug into a slow, quiet one.
- Every `OperationalError` is treated alike — see the deliberate non-goal in §2.2.
- On catch: `session.rollback()` → count the reconnect against `site` (§3.6) → print a warning →
  `time.sleep(1)` → re-run `unit()` once.
- If the retry also raises `OperationalError`: raise `DatabaseUnavailableError`, chained (`from`)
  so the original MySQL error survives in the traceback.

#### 3.3.1 Why the granularity is unit-of-work and NEVER statement

When MySQLdb reports a lost connection, SQLAlchemy invalidates the connection and the `Session`'s
transaction enters a failed state: every further use raises `PendingRollbackError` until someone
calls `rollback()`. **`rollback()` discards every pending, uncommitted ORM change in the
session.**

A retry wrapped around the individual `db_session.get()` at `:3343` — inside the month loop —
would therefore roll back the `PantheonOverageProtection` rows already `add()`ed for *earlier
months of the same site*, re-run one `get()`, and then `commit()` a **partial write set**. The
run would report success while writing wrong overage-protection data.

> **NEVER wrap `db_retry` around a single statement that executes while the session holds pending
> writes.** Retry only whole units of work that can be re-run from scratch.

Units, and why each is idempotent:

| Unit | Current lines | Idempotent because | Retry |
|---|---|---|---|
| `update_traffic_rows()` | `:1551`–`:1579` | `Session.merge()` is upsert-by-primary-key | unit |
| `insert_traffic_rows()` | `:1589`–`:1616` | `ON CONFLICT DO NOTHING` (sqlite) / `INSERT IGNORE` (mysql) | unit |
| `load_traffic_rows()` | `:1625`–`:1632` | read-only | unit |
| `build_traffic_table_rows()` | `:3278`–`:3380` | recomputed from scratch on entry; rows are get-or-create by primary key | unit |
| `op_lookup()` | `:3402` | read-only, **and** no pending writes exist (the commit at `:3380` has already run). After this change it is usually an **identity-map hit that emits no SQL at all** (§1.2) — the retry is there for the months it does have to fetch | statement |

**The terminus calls MUST stay outside the units.** `get_old_metrics()` (`:1587`, `:1603`) is a
slow `terminus` call sitting between the DB writes of the `--import-older-metrics` path; it MUST
be hoisted out so a retried insert does not re-run it.

The idempotence claim is **tested, not asserted**: the retry test MUST fail the unit *while
overage rows for an earlier month are pending* (`session.new` non-empty at the raise), which is
the only position that would expose a partial write set (§5).

#### 3.3.2 Rollback expires loaded rows — so the traffic rows leave the ORM

`Session.rollback()` **expires every loaded object, regardless of `expire_on_commit`** (verified,
§1.2). So after any `db_retry` rollback, reading an attribute of an ORM row loaded earlier fires a
**fresh, unretried `SELECT`** from wherever that read happens to sit — outside every unit of work,
and therefore outside every retry.

Today that is latent: the report consumes its rows at `:2856`, before the first retryable unit
that can roll back (`:3278`). But `traffic_rows` is a **published data-contract key**
(`CLAUDE.md`, `site_post_traffic`, assigned at `:1646`), so any future `check/` package may hold
those rows and read them later — one rollback away from an unretried lazy SELECT that aborts the
run.

> **MUST: `load_traffic_rows()` returns plain data, not live ORM rows.**

```python
class TrafficRow(NamedTuple):
    site_id: str
    traffic_date: datetime.date
    site_plan: str
    visits: int
    pages_served: int
    cache_hits: int
```

The attribute names are identical to the model's, so **every existing consumer keeps working
unchanged** — verified exhaustively: `len(results)` (`:1635`), `site_context["traffic_rows"] =
results` (`:1646`), and `for row in results:` reading `.traffic_date`/`.visits`/`.site_plan`
(`:2856`). Nothing calls an ORM API on them, mutates them, or relies on their type or identity,
and no `check/` or `plugin/` package reads `traffic_rows` today. `CLAUDE.md`'s contract table MUST
be updated to say `traffic_rows` is a `list[TrafficRow]`.

#### 3.3.3 No `OperationalError` escapes un-named

`db_retry` converts a retried-and-still-failing `OperationalError` into
`DatabaseUnavailableError`. Three paths could still leak a raw `OperationalError`; each is closed:

| Leak | Why it can happen | Closed by |
|---|---|---|
| `session.rollback()` **inside `db_retry`'s own handler** | If SQLAlchemy did not classify the DBAPI error as a disconnect, the connection is not invalidated and the `ROLLBACK` is really emitted — and can itself raise | `db_retry` wraps its own `rollback()`; a failure there raises `DatabaseUnavailableError`, chained from the original error |
| `db_session.close()` / `db_engine.dispose()` in `finish_run()` — called **from the abort path**, on a session whose database is by definition sick | closing emits work against a dead connection | `finish_run()` wraps each of the two calls **separately** (so a failing `close()` cannot skip `dispose()`), catching **`(SQLAlchemyError, OSError)`** — narrow enough that a `TypeError` from a future edit stays loud. A failure is reported and **MUST NOT** prevent the artifacts from being written: artifacts beat a clean close. |
| Any `OperationalError` raised outside a unit of work (a future code path; an expired-row lazy load) | not every DB touch is inside `db_retry` | `main()` catches **`(DatabaseUnavailableError, OperationalError)`** around the site loop and routes both to `abort_run()` — so a database failure *anywhere* in the loop lands on the named path with artifacts flushed |

`--create-tables` (`:1305`–`:1306`) is **deliberately not retried**: it exits before the site loop,
it is interactive and cheap to re-run, and a failure there is unambiguous. Stated so the omission
is a decision, not an oversight.

### 3.4 The `build_traffic_table_rows()` extraction

`:3278`–`:3380` interleaves database writes with building the report's traffic table, and carries
loop-local state (`op_remaining`, `old_plan`, `traffic_table_rows`). It MUST become a function so
that re-entering it resets that state — which is exactly what makes it retryable. `site_plan_start`
is computed by `main()` (it is read again downstream at `:3395`/`:3417`) and passed in; the block's
other locals are internal (verified, §1.2).

### 3.5 The abort path: flush, then exit nonzero

Two conditions abort a run deliberately, and they share one handler:

```
site loop
   │
   ├── DatabaseUnavailableError ──┐
   │   (or a stray OperationalError, §3.3.3)
   │                              │
   ├── KeyboardInterrupt ─────────┤
   │   (Ctrl-C mid-site)          │
   │                              ▼
   │                        abort_run(site_name, reason, emailed)
   │                              │  ignore further SIGINT  ← a 2nd Ctrl-C must not
   │                              │                            truncate the flush
   │                              │  rollback the session
   │                              │  resume point = site_name, UNLESS the site was already
   │                              │                 emailed → the NEXT site      ← §3.5.3
   │                              │  DROP site_results[site_name] unless emailed ← §3.5.2
   │                              │  print: which site, why, the underlying error
   │                              │  finish_run(..., aborted_at=site, reason=…)
   │                              │  print the re-run command                    ← §3.5.1
   │                              │  sys.exit(1)   on a database failure
   │                              │  sys.exit(130) on Ctrl-C (conventional SIGINT code)
   │
   └── normal completion ─────────► finish_run(..., aborted_at=None)  ← same function
                                    (exit 0)
```

`finish_run()` is the epilogue (`:3932`–`:3967`) lifted into a function — **the whole epilogue**:
the `--all` branch that writes the artifacts, the `else:` branch that prints notices and results to
the console, the unconditional savings totals, and `sc.debug("Done!")`. **One epilogue, two
callers.**

An aborted run **MUST NOT** print `Email sent for N of M sites` in green as though it finished. It
reports what completed and names the site it stopped at.

#### 3.5.1 The re-run command is built from `sys.argv`, NEVER re-enumerated

The site loop is reached by `--update` (`:1620`), `--import-older-metrics` (`:1581`) and
`--only-warn` (`:2842`), and every run has a `--config` (`:1205`). A hint that re-enumerated flags
from `sc.options` would be a denylist-by-omission: the first flag someone adds next year is
silently dropped, and the operator — who pastes this command at the moment they are least careful
— gets a run that does something *different from the one that died*. An
`--all --import-older-metrics` run aborting would print a command that generates and (with
`--for-real`) **sends full reports**.

> **MUST: the command is rebuilt from the actual `sys.argv`.** It therefore cannot omit a flag it
> does not know about.

Two shapes, because `--resume-from` **requires `--all`** (`:1236`–`:1238`; verified §1.2) and a
printed command that fails when pasted is worse than none:

| Run | Printed command |
|---|---|
| `--all` | `resume_command(sys.argv, resume_site)` — argv with any existing `--resume-from` (space *and* `=` form) stripped, plus `--resume-from <resume_site>` |
| explicit `SITE` list | `rerun_command(sys.argv, original_sites, remaining_sites)` — argv with the original site **positionals** removed, plus the sites not yet processed |

Both are pure and unit-tested (§5). `allow_abbrev=False` (`CLAUDE.md`) guarantees only the exact
`--resume-from` / `--resume-from=` spellings exist, so the stripping cannot miss a variant.

> **MUST: `rerun_command()` only strips a site name that is in POSITIONAL position.** A naive
> `[a for a in argv if a not in original_sites]` also deletes a site name that happens to be an
> **option's value** — `-c its-wws-test1`, `--smtp-username its-wws-test1` — leaving `-c` to
> swallow the next token and handing the operator a mangled command. The set of value-taking
> options is **derived from the parser itself** (`build_arg_parser()._actions`, `nargs != 0`), not
> hardcoded: a hardcoded list would rot the first time an option is added, which is the same
> denylist-by-omission failure this whole subsection exists to prevent.

#### 3.5.2 The aborting site is removed from `site_results` (unless it was emailed)

`site_results[site["name"]]` is written **during the gather** (`:1833` WordPress, `:2152` Drupal) —
~1,400 lines *before* the crash point — while notices reach `all_warnings` only at the *end* of a
successful site (`:3922`). So on abort the artifacts disagree: the failed site is in
`-results.json` (as if it had succeeded, and it was never emailed) but absent from `-notices.csv`.

> **MUST: `abort_run()` removes the aborting site from `site_results` before calling
> `finish_run()` — unless that site's report was already emailed (§3.5.3).**

The artifacts then contain exactly the sites that completed end-to-end. The discarded gather data
costs nothing: `--resume-from` is **inclusive**, so the resumed run redoes that site from the top
and rewrites the entry.

An earlier draft of this spec asserted the opposite ("its entry reaches `site_results` only at the
end of a successful site") — that was **wrong**, and the `_run` metadata built on it reported a
false `sites_processed`. Recorded here because the wrong version is the one a reader would
otherwise reconstruct from the surrounding code's shape.

#### 3.5.3 Ctrl-C after the email was sent MUST NOT cause a duplicate report

The database abort cannot fire until `:3280`, which is long before the SMTP send at `:3916`–`:3920`
— so for that path, "a run that aborts has emailed every site before the failure and none after
it" holds, and resuming *at* the aborting site is exactly right.

**Ctrl-C is different.** A SIGINT can land *after* `send_message()` has already delivered that
site's report. Resuming inclusively at that site would then send its owner a **second copy of the
same monthly report** — a silent, outward-facing failure, and the precise thing Prime Directive #1
forbids.

> **MUST: the site loop records whether the current site's report was emailed. If an interrupt
> lands after the send, the resume point is the NEXT site, and the site's `site_results` entry is
> KEPT** (it really did complete).
>
> ```python
> def resume_point(site_names: list, site_name: str, emailed: bool) -> str:
>     """Where a resumed run must start.  Normally the aborting site itself (--resume-from is
>     inclusive, so it is redone from the top) -- but if the interrupt landed AFTER that site's
>     report was emailed, restarting there would send its owner a duplicate.  Returns None when
>     the emailed site was the last one, i.e. nothing remains to resume."""
> ```

Pure, and unit-tested for all three cases (not emailed; emailed mid-list; emailed last).

**Known, accepted gap** (narrower, and left alone deliberately): a Ctrl-C in the 6-line window
between `emails_sent += 1` (`:3919`) and the `all_warnings.append(...)` (`:3925`) counts that
site's email and keeps its results entry, but drops its **notices** from `-notices.csv`. A
transaction around six lines is not worth it; written down rather than left for someone to
discover.

Beyond that, the append-mode `-notices.csv` and `merge_prior_results()` for `-results.json`
accumulate the resumed run's artifacts onto the aborted run's. **No new recovery machinery is
needed.**

#### 3.5.4 `abort_run()` MUST NOT be able to crash

It runs when things are already broken; a traceback *inside the abort handler* costs the operator
the artifacts and the command they need. Two inputs are not guaranteed, and both **MUST** be
guarded:

| Input | Why it can be bad | Guard |
|---|---|---|
| `site_name is None` | the loop variable is pre-initialized to `None`, and an interrupt can land before the first site's body runs | print the abort without a site name; resume point = the run's start (no `--resume-from`) |
| `site_name not in sc.options.sites` (non-`--all` runs) | the loop iterates **every** org site and `continue`s the unrequested ones (`:1402`), so an interrupt can land on a site the operator never asked for | do not slice; re-run **all** the originally requested sites |

Without these, `sites_from_resume_point()` raises `ResumeSiteNotFoundError` — *after* SIGINT has
been ignored and `finish_run()` has run — and the operator gets a traceback instead of a command.

### 3.6 Observability

A silently-healed reconnect is a lost signal: it means a middlebox is still reaping flows and the
invariant has a hole. Reconnects are therefore **never quiet**, they are **attributed**, and they
**outlive the terminal**.

| Event | Verbosity | Output |
|---|---|---|
| A retry heals a lost connection | **default** (not behind `-v`) | `⚠ Lost the database connection during {what}; reconnecting and retrying.` — `what` names the unit **and the site** |
| Any run | default, in `finish_run()` | `Database reconnects: {total}` — 0 on a healthy run |
| The abort | default | the site, the reason, the underlying error, **and the re-run command** |
| Run outcome, durably | `--all`, in `{ymd}-results.json` | a `"_run"` key (below) |
| SQL statements | `-vv` | already covered by the existing `echo=True` (`:1298`); no new code |

```json
"_run": {
    "aborted_at": "its-wws-test2",         // null on a completed run
    "reason": "database",                   // "database" | "interrupted" | null
    "sites_completed_this_run": 47,
    "db_reconnects_this_run": 3,
    "reconnects_by_site": {"its-wws-test1": 3},
    "previous": { … }                       // only on a resumed run: the aborted run's _run
}
```

**Names say "this run" on purpose.** `merge_prior_results()` merges by key with new winning, so on
a resumed run the file accumulates *all* sites while `_run` describes only the resumed run — a
field called `sites_processed` in a file listing 205 sites would be read as a lie. Note also that
an `--only-warn` run emails nobody, so `sites_completed_this_run` counts sites *processed*, not
sites emailed; `emails_sent` is the console's number.

**A resumed run MUST NOT destroy the aborted run's `_run`.** Plain `merge_prior_results()` would
overwrite it — and the aborted run's block is exactly the one carrying the reconnect evidence that
§8's audit question asks about. The resumed run therefore nests the prior block under
`_run.previous`, so the forensic trail survives the resume that was prompted by it.

`reconnects_by_site` exists so that audit question ("the middleboxes are still reaping *something*
— what?") is answerable from the artifact instead of from memory.

**Risk, stated:** any consumer that iterates `results.json`'s keys as if all of them were site
names will now also see `_run`. No consumer in this repo does; the key is underscore-prefixed
precisely so it cannot collide with a Pantheon site name (lowercase alphanumeric-plus-hyphen).

After this ships, the failure the operator hit can produce only: *nothing* (healed), *a visible
warning plus a nonzero count in the artifacts* (healed — but tell someone), or *a named error, a
flushed set of artifacts, and a runnable command* (did not heal). It can no longer produce an hour
of lost work and a stack trace.

### 3.7 Shadow paths

| Flow | Happy | Nil | Empty | Upstream error |
|---|---|---|---|---|
| `load_traffic_rows()` | `list[TrafficRow]`, connection released | never returns `None` | a site with no traffic rows → `[]`. Reachable and already handled: `visits_by_month` is pre-seeded to `0` for every month (`:2848`–`:2853`), `plan_on_day` falls back to `{end_date: site_current_plan}` (`:2880`) | `OperationalError` → retry → `DatabaseUnavailableError` |
| `build_traffic_table_rows()` | rows built, overage rows committed | n/a | zero-traffic site → months before `site_plan_start` `continue` (`:3297`), one row survives. **`visits_by_month == {}` is unreachable** (`:2848`–`:2853`) and is NOT specified | as above |
| `insert_traffic_rows()` | rows inserted-or-ignored | n/a | `rows == []` → **MUST return without executing** (preserves the existing `if len(new_rows) > 0` guard) | as above |
| `db_retry()` | unit succeeds first try | `unit` is never `None` (call sites are literal) | n/a | non-`OperationalError` propagates un-retried; a failing `rollback()` becomes `DatabaseUnavailableError` (§3.3.3) |
| `finish_run()` | artifacts written | `aborted_at=None` on the normal path | zero sites completed → `-notices.csv` empty, `-results.json` holds only `_run` | a failing `close()`/`dispose()` is reported and **MUST NOT** block the artifact writes (§3.3.3) |
| `abort_run()` | flush, print, exit | — | the aborting site was never in `site_results` (e.g. it died before the gather wrote it) → the `pop` is a no-op (`pop(name, None)`) | a second Ctrl-C during the flush is **ignored** (SIGINT set to `SIG_IGN` on entry) |
| `resume_command()` / `rerun_command()` | full command echoed | n/a | no remaining sites → cannot occur (the aborting site is always remaining) | n/a — pure string work |

### 3.8 Security

No new secrets, no new network surface, no new external input. `pool_recycle`/`pool_pre_ping` are
literals. The MySQL password continues to flow through the existing config substitution
(`<{secret env …}>`); nothing in this change reads `os.environ`.

Two things are threat-modeled because they *print*:

1. **The abort message prints the underlying database error.** SQLAlchemy's
   `StatementError.__str__` renders the statement, the bound parameters, and a docs link — **not**
   the connection URL, which embeds the password. §5 pins this with a test that drives a **real**
   engine whose URL contains a password and asserts the password does not appear in the raised
   `DatabaseUnavailableError`. (An earlier draft asserted this against a hand-built error object
   that never contained a URL, which made the test vacuous.)
2. **The re-run command echoes `sys.argv`.** Credentials are **never** passed as flags in this tool
   (they arrive via config substitution), so `sys.argv` carries no secret. Stated explicitly
   because "echo the user's command line" leaks secrets in tools where credentials *are* flags — if
   a credential flag is ever added, `resume_command()`/`rerun_command()` become a leak and MUST be
   revisited.

---

## 4. Gates and preconditions (canonical table)

| Gate | Condition | Effect |
|---|---|---|
| Pool settings applied | `[Database].type == "mysql"` | `pool_pre_ping` / `pool_recycle` set; sqlite gets `{}` |
| `expire_on_commit=False` | always | both backends |
| Release commit after traffic read | always | both backends |
| `db_retry` wrapping | always | both backends (sqlite simply never raises `OperationalError` here) |
| Abort path engaged | `DatabaseUnavailableError`, a stray `OperationalError`, or `KeyboardInterrupt` escapes the loop | site popped from `site_results` (unless already emailed); `finish_run(aborted_at=…)`; command printed; exit 1 (database) / 130 (interrupted) |
| Resume point = the **next** site | `reason == "interrupted"` **and** the site's report was already emailed | prevents a duplicate report to a real site owner (§3.5.3); the site's `site_results` entry is kept |
| Resume point = the run's start (no `--resume-from` / all requested sites) | `site_name is None`, or `site_name not in sc.options.sites` on a non-`--all` run | `abort_run()` cannot crash on its own inputs (§3.5.4) |
| `-notices.csv` / `-results.json` written | `--all` | unchanged from today — including on the abort path |
| `_run` key written | `--all` | on both the normal and the abort path |
| Command printed on abort | `--all` | `resume_command()` → `--resume-from <site>` |
| Command printed on abort | explicit `SITE` list | `rerun_command()` → the sites not yet processed. **`--resume-from` is NEVER printed here**: it requires `--all` (`:1238`) and would fail when pasted |
| Further SIGINT during the flush | always | ignored (`SIG_IGN`), so the artifacts land intact |
| `--create-tables` retried | never | exits at `:1306`, before the site loop (§3.3.3) |

---

## 5. Testing

> **NEVER-block — tests are load-bearing.** The four e2e goldens are the regression net for the
> *rendered report*: they prove that releasing the connection, `expire_on_commit=False`, the
> `TrafficRow` change, and the extractions did not alter a single byte of report output. **If a
> golden shifts, the change is wrong.** Goldens **MUST NOT** be regenerated to accommodate this
> change; `./run-tests --update-goldens` is prohibited for this work.
>
> **But the goldens do NOT cover stdout or the artifact files.** `tests/e2e/test_golden.py`
> snapshots only `rendered_report["html"]` and `["txt"]`. Everything `finish_run()` prints or
> writes is covered **only** by `tests/integration/test_finish_run.py`, and the site-loop `try:`
> wrapper **only** by the e2e abort test below. Delete either and the riskiest edits in this change
> become untested.

**Unit** — `tests/unit/test_db_resilience.py`
- `db_engine_args()`: mysql carries `pool_pre_ping=True` / `pool_recycle=1800`; sqlite is `{}`; an
  unsupported `type` exits.
- `db_retry()`: heals a lost connection (rollback called, unit re-run, warning printed, the
  reconnect attributed to the site).
- `db_retry()`: a unit failing twice → `DatabaseUnavailableError`, original error chained.
- `db_retry()`: a failing `rollback()` also yields `DatabaseUnavailableError` (§3.3.3).
- `db_retry()`: an `IntegrityError` propagates **un-retried**.
- `load_traffic_rows()`: returns `TrafficRow` (not ORM rows) **and** leaves
  `session.in_transaction() is False`. *The regression test for the entire bug.*
- `resume_command()`: preserves `--config`/`--update`/`--import-older-metrics`/`--only-warn`/
  `--for-real`; replaces an existing `--resume-from` in both the space and the `=` form.
- `rerun_command()`: drops the original site **positionals**, keeps a site name sitting in an
  option's **value** slot (`-c its-wws-test1`), appends the remaining sites, and **never** emits
  `--resume-from`.
- `resume_point()`: the aborting site when it was not emailed; the **next** site when it was;
  `None` when the emailed site was the last (§3.5.3).

**Integration** — the credential-leak test (§3.8) lives here, **not in the unit tier**: it builds a
real engine and attempts a connection, and `pyproject.toml` defines `unit` as "pure/in-process
function tests, no I/O". It uses `connect_args={"connect_timeout": 1}` so a host that DROPs (rather
than refuses) loopback port 1 cannot hang the suite, and it asserts the **password** and the full
`str(engine.url)` are absent from the message — asserting only on the host would pass for the wrong
reason, since MySQLdb's own error text contains the host.

**Unit** — `tests/unit/test_traffic_table_rows.py` (in-memory sqlite)
- `build_traffic_table_rows()` produces the expected rows and overage-protection rows.
- **Idempotence under retry**, failing **while a prior month's overage row is pending**
  (`session.new` non-empty at the raise — asserted in the test, so the fixture cannot drift into a
  position that proves nothing). This is the only scenario that would expose the partial write set
  §3.3.1 exists to prevent.
- The **zero-traffic** site (all months `0`, §3.7) produces the expected single row.

**Integration**
- `tests/integration/test_finish_run.py`: the `--all` branch writes both artifacts and the `_run`
  key; the **non-`--all`** branch prints notices and results to the console; `aborted_at` suppresses
  the green success line; a failing `close()` still writes the artifacts, and `dispose()` still
  runs.
- `tests/integration/test_abort_run.py`: database abort → exit 1, site popped from `site_results`,
  `--resume-from` command on `--all`; Ctrl-C → exit 130; Ctrl-C **after the send** → resume point
  is the next site and the entry is **kept** (§3.5.3); an explicit-site run prints a
  `rerun_command()` and **never** `--resume-from`; `site_name=None` and an unrequested `site_name`
  both produce a command instead of a traceback (§3.5.4).

**E2E**
- All four existing goldens byte-identical.
- **`tests/e2e/test_abort_e2e.py` (new):** a real subprocess run of `main()` (single site — the
  interlock bans `--all`) with a `tests/shims/dbshim` `sitecustomize.py` that makes
  `sqlalchemy.orm.Session.get` raise `OperationalError`, following the established
  `tests/shims/dnsshim` pattern (on `PYTHONPATH` via `run_program(..., extra_env=…)`). Asserts exit
  code 1, `Database reconnects: 1`, and that a re-run command was printed. **This is the only test
  that proves `main()` actually wraps the loop in `try:`, catches, and still calls `finish_run()`**
  — `git diff -w` is an eyeball check, not a test.

**Test-harness rules — three, all learned the hard way:**
1. The reconnect counters live on the **session-scoped** `psh` module and `reset_sc` does not
   restore them. Tests **MUST** set them with `monkeypatch.setattr(psh, …)`, **never** by direct
   assignment. (Same failure class as the recorded `reset_sc` / `sc.escape_url` leak.)
2. `abort_run()` calls `signal.signal(SIGINT, SIG_IGN)`, which is **process-global and not undone
   by any fixture**. An in-process test that calls `abort_run()` without
   `monkeypatch.setattr(psh.signal, "signal", …)` makes **the rest of the pytest session ignore
   Ctrl-C**. Every abort test MUST patch it (and assert it was called with `SIGINT`/`SIG_IGN`).
3. `run_program()` is **imported from `conftest`**, not requested as a fixture, and its signature is
   `run_program(args, *, cwd, mode="replay", extra_env=None, timeout=300, fixtures_dir=None)` —
   `cwd` is required, there is no `check`/`shims`/`env` keyword, and it never raises on a nonzero
   exit. A new e2e test MUST follow `tests/e2e/test_zero_traffic_e2e.py`: `make_workdir()` →
   `--create-tables` with `MINIMAL_CONFIG` → optional `seed_traffic()` → the run. Skipping the
   workdir would let the subprocess inherit the repo CWD and the **production config symlink**.

**Not automatable:** the middlebox reap itself. Acceptance for that is empirical (§6).

---

## 6. Acceptance criteria

Exact commands; each MUST be run and its real output pasted into the PR/commit — never summarized.

```bash
./run-tests --fast          # all pass; zero golden diffs
./run-tests                 # all pass, incl. the live tier
git diff -w -- pantheon-sitehealth-emails   # only the try:/except lines from the loop body
./pantheon-sitehealth-emails --date 20240731 its-wws-test1   # completes; "Database reconnects: 0"

# Ctrl-C mid-run (safe: no --for-real).  Press Ctrl-C during the second site.
./pantheon-sitehealth-emails --date 20240731 --all
# Expected: exit 130; both artifacts written; the printed command carries every flag of the
# original invocation plus --resume-from <site>; pasting it resumes correctly.
```

**Empirical acceptance (the actual bug):** a real `--all` run survives past the point where the
last three died. Until that run completes, this change is *plausible*, not *verified* — say so in
those words.

---

## 7. Six-month view

The invariant in §3.1 is enforced today by a commit at one call site and a comment. In six months
someone adds a second long-running per-site step, or a `check/` package that queries the DB in a
`site_post_gather` hook, and the idle window comes back — the comment will not stop them.

The durable fix is session-per-unit-of-work (§2.2), which makes "no connection is held across
non-DB work" true *structurally* rather than by convention. This spec deliberately does not do it;
the bug does not justify the diff today. It does make a **down payment**: `load_traffic_rows()`
returning plain `TrafficRow` data (§3.3.2) removes the live-ORM-rows-outliving-the-session problem
that would otherwise be the hardest part of that refactor.

---

## 7.1 Reviewer concerns carried forward (accepted, not fixed)

Three rounds of adversarial review produced two findings that are **deliberately not closed**.
They are written down rather than left as intentions (Prime Directive #9):

1. **The SIG_IGN window.** `abort_run()` ignores SIGINT from its first line, so a second Ctrl-C in
   the microseconds between the `KeyboardInterrupt` being raised in the loop and the handler being
   entered can still truncate the flush. Closing it properly means an interrupt-safe SIGINT handler
   installed for the whole run — disproportionate to the risk it removes.
2. **The notices window** (§3.5.3): a Ctrl-C in the six lines between `emails_sent += 1` (`:3919`)
   and `all_warnings.append(...)` (`:3925`) keeps that site's results entry and its already-sent
   email, but loses its notices from `-notices.csv`.

---

## 8. Closing audit questions (answer after implementation)

1. Did the four goldens come out byte-identical without a single adjustment? If any needed one,
   what exactly changed, and why was it not a bug?
2. Did `git diff -w` confirm the loop-body re-indent introduced no semantic change?
3. Does any *other* code path hold a DB connection across slow work — does any `check/` or
   `plugin/` hook touch `db_session`? (Expected: none do today.)
4. After the first successful `--all` run: what was `Database reconnects:`, and what does
   `_run.reconnects_by_site` say? A nonzero value means the idle window is closed but the
   middleboxes are still reaping *something* — what?
5. Is `pool_recycle = 1800` actually shorter than the shortest middlebox idle timeout on this
   path? We inferred it; we never measured it.
6. Did anything downstream trip over the `_run` key in `-results.json`?
7. On the first real abort: was the printed command runnable, verbatim, with no edits?

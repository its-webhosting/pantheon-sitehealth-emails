# SPEC — Increment I5: `psh/db.py` (models, row types, resilience layer, engine args)

**Campaign:** `development/2026-07-17-modularization-campaign/` — this spec cites
`CAMPAIGN.md` by section number and re-derives nothing (CAMPAIGN.md preamble). Scope
authority: §11 row I5. Module map: §3.1 (`psh/db.py` row). Parallel-ready constraint:
§3.4. Per-increment obligations: §7. Behavior bar: §8. Invariants: §9 (Invariant 5 is
this increment's center of gravity). Ratchet: §13.

**Read first (per §7):** `CAMPAIGN.md`, `LEDGER.md` (through I4), `CLAUDE.md`
(§ Database in full), `BLOCKMAP.md` (DB session touches: B10, B11, B23, B24, B26, B46,
B47, B59, B60 — none of these *blocks* move; I5 moves module-level defs only),
`prompts/directives.md`, `prompts/implementation-standards.md`,
`development/2026-07-13-db-connection-resilience/SPEC.md` (the design the moved code
implements — its section numbers are cited throughout the moved docstrings and MUST keep
resolving).

## Glossary (delta over CAMPAIGN.md's)

- **Counters** — the two run-scoped reconnect-attribution dicts,
  `db_reconnects_by_site` (healed) and `db_reconnect_failures_by_site` (failed).
- **Remnant readers** — `finish_run()`/`abort_run()` (staying in `psh/_legacy.py` until
  I13), which read the counters at `_legacy.py:1210–1211` and `1296–1297`.
- **Move set** — the defs Deliverable A enumerates; "verbatim" means byte-identical
  bodies except the edits Deliverable A names per item.

## 1. Scope (exhaustive) and non-scope

In scope (§11 row I5 — its "95–178" / "1285–1575" are a47418c line ranges, drifted per
BLOCKMAP preamble; current-line equivalents below):

1. **Move** into a new `psh/db.py` (gated from birth): `Base`, `PantheonTraffic`,
   `PantheonOverageProtection`, `TrafficRow`, `OverageProtectionRow`
   (`psh/_legacy.py:93–167`), `DatabaseUnavailableError` (821–826),
   `record_db_reconnect` (841–844), `db_retryable` (847–862), `db_retry` (865–926),
   `update_traffic_rows` (929–961), `insert_traffic_rows` (964–980),
   `load_traffic_rows` (983–1021), `load_overage_protection_window` (1024–1061),
   `db_engine_args` (1079–1109). This is exactly §3.1's `psh/db.py` row.
2. **Move the counters to `script_context.py`** (D-i5-1) with their contract comments
   (829–838) verbatim; wire `reset_sc` isolation for them.
3. **Re-import** every moved name into `psh/_legacy.py` (I2/I3/I4 pattern) so its call
   sites, the tests' `psh.<name>` references, and the `sc.db_engine_args` exposure
   (`_legacy.py:1155`) resolve unchanged; repoint the remnant readers' four counter
   reads to `sc.`; remove only the imports the move orphans (verified, not assumed —
   LEDGER I3 precedent; pre-verified list in Deliverable C).
4. **Repoint the DB test suites' counter seams to `sc`** (D-i5-3) — suites otherwise
   intact (no assertion weakened, no test dropped; §11's "relocated intact" reading in
   D-i5-3).
5. **Ratchet** (§13): `psh/db.py` clean under broad ruff + pyright standard from birth;
   measured findings + dispositions in §5.
6. Docs/CLAUDE.md/memory/ledger updates (§7 obligations 6–8).

NOT in scope: the resume helpers `ResumeSiteNotFoundError` (817–818),
`sites_from_resume_point` (1064–1076), `merge_prior_results` (1112–1141) — §11 row I5
names them as staying for I13, even though they sit inside the moved region's line
range. B10/B11 (`db.create_engine`/sessionmaker/`create_all` in `main()`,
`_legacy.py:1997–2011`) stay — §3.1 assigns no module for them and §11 row I5 lists
defs only; they move with `main()`'s final form (I13; **ledger note**).
`build_traffic_table_rows`, `get_old_metrics` and the traffic flow → I6 (§3.1
`psh/traffic.py`). `finish_run`/`abort_run`/`abort_reason` → I13. No test-file
un-grandfathering (`tests/` stays wholesale in `ruff-broad.toml` `extend-exclude` —
I2–I4 precedent; the repoints in Deliverable D don't constitute the "cleaned alongside
their code" pass). No golden/fixture changes (Invariants 1, 10). No config keys, no
contract keys, no new `sc` façade *documentation* (the counters are shared state like
`sc.hooks`, not check-facing API — they do NOT join the documented-façade-names test).

## 2. Architecture decisions (each with why; deviations flagged for the ledger)

### D-i5-1: the counters move to `script_context.py`, accessed as `sc.` attributes

§3.1's `psh/db.py` row lists `record_db_reconnect` (the function) but names the two
dicts nowhere; §3.4 bars new module-level mutable state in `psh/` (the rule that kept
`sc.hooks` in `script_context.py` — LEDGER I4 deviation 1); §6 already schedules the
"reconnect counters" into I13's `RunState`, so this is their scheduled interim home,
not a new permanent surface. The deciding defect class: the writer (`db_retry`, moving)
and the remnant readers (`finish_run`/`abort_run`, staying until I13) would otherwise
hold **separately rebindable bindings of the same name** across two modules — ~40
existing `monkeypatch.setattr(psh, "db_reconnects_by_site", {})` sites rebind, so any
two-namespace aliasing scheme desyncs writer from readers the first time one side is
rebound and not the other (the I2 `psh.gateway.run_terminus` seam lesson, PD#14). One
owning namespace, attribute-accessed at call time by both sides, dissolves it:
`script_context.py` defines `db_reconnects_by_site: dict[str, int] = {}` and
`db_reconnect_failures_by_site: dict[str, int] = {}` (their 829–838 contract comments
moved verbatim); `db_retry` writes `sc.db_reconnect_failures_by_site` /
`sc.db_reconnects_by_site`; the remnant readers read `sc.`. The pyright probe confirms
`sc.`-access type-checks only with these module-level definitions (measured 2026-07-20).
**Ledger note, not an amendment.**

### D-i5-2: `psh/db.py` imports `script_context` at module level

`import script_context as sc` at top of module — the `psh/gateway.py`/
`psh/configuration.py` precedent. No cycle: `script_context` imports only
`psh.modules`/`psh.notice` (I4's call-time-import constraint was specific to those two
being imported *by* `script_context`; `psh.db` is not). Needed for `sc.console`,
`sc.config` (`insert_traffic_rows`' backend switch), and the counters.

### D-i5-3: test suites stay in place; only the counter seam repoints

§11's "DB test suites relocated intact" is read as: the moved code's suites keep their
full coverage; their *targets* relocate, the files do not (they already live in
tier-named homes: `tests/unit/test_db_resilience.py`,
`tests/integration/test_db_roundtrip.py`, `tests/integration/test_db_credentials.py`).
"Intact" = no assertion weakened, no test dropped, collected count preserved. The ONLY
mandatory edit class is the counter seam: every
`monkeypatch.setattr(psh, "db_reconnect[s|_failures]_by_site", …)` and every
`psh.db_reconnect*` assertion retargets the `script_context` module (the namespace
`db_retry` actually reads — patching the old `psh` binding would be the silent
non-intercepting patch of the I2 lesson, PD#14). Affected files (grep-verified
2026-07-20): `test_db_resilience.py`, `test_db_credentials.py`, `test_abort_run.py`,
`test_finish_run.py`, `test_traffic_table_rows.py`. Everything else keeps resolving
through the `psh` fixture via the re-imports: `psh.db_retry`, `psh.db_engine_args`,
`psh.TrafficRow`, `psh.PantheonTraffic`, … and `monkeypatch.setattr(psh.time, "sleep",
…)` still intercepts (`time` is a shared module object — CLAUDE.md § mock seams).
`tests/shims/pyshim/dbshim.py` patches `sqlalchemy.orm.Session.get` — location-independent,
untouched. `temp_db`/`TempDB` (conftest) resolves models via the `psh` fixture —
implementer verifies it needs no edit.

### D-i5-4: `reset_sc` owns counter isolation

The counters join `_SC_ATTRS` and get clean-slate assignments (`= {}`) in `reset_sc` —
they are exactly the "process-global mutable state" that fixture exists to restore.
The per-test `monkeypatch` zeroings stay (repointed): they are now redundant but
harmless, and deleting ~40 of them is churn "intact" forbids. (I13 collapses all of
this into `RunState`.)

## 3. Deliverable A — `psh/db.py` (new file; gated from birth)

Module docstring: names the module's role (every DB touch this program makes), cites
`development/2026-07-13-db-connection-resilience/SPEC.md` as the governing design and
CAMPAIGN.md I5 as the move, and carries the counter-location note (state in
`script_context`, D-i5-1) — the flow is non-local, so the note is REQUIRED
(implementation-standards § Directives 7).

| Item | From (`_legacy.py`) | Edits allowed (exhaustive — else verbatim) |
|---|---|---|
| `Base` | 93–94 | — |
| `PantheonTraffic` | 97–117 | delete the ERA001 commented-out `# id:` line (100) — dead schema remnant, §5 |
| `PantheonOverageProtection` | 120–134 | — |
| `TrafficRow` | 137–151 | — |
| `OverageProtectionRow` | 154–166 | — |
| `DatabaseUnavailableError` | 821–826 | — |
| `record_db_reconnect` | 841–844 | — |
| `db_retryable` | 847–862 | — |
| `db_retry` | 865–926 | `site: str = None` → `site: str | None = None` (§5 RUF013/pyright); the four `record_db_reconnect(db_reconnect…` calls gain the `sc.` prefix (D-i5-1) |
| `update_traffic_rows` | 929–961 | `# noqa: DTZ007` + inline reason on the `strptime` (§5) |
| `insert_traffic_rows` | 964–980 | — (`sc.config` read already spelled `sc.`) |
| `load_traffic_rows` | 983–1021 | — |
| `load_overage_protection_window` | 1024–1061 | — |
| `db_engine_args` | 1079–1109 | `-> (str, dict)` → `-> tuple[str, dict]` (§6 house-style replacement; pyright reportInvalidTypeForm) |

Imports (measured against the bodies): `datetime`, `sys`, `time`; `typing.NamedTuple`;
`rich.markup.escape`; `sqlalchemy` (`Boolean`, `Date`, `Integer`,
`PrimaryKeyConstraint`, `String`, `UniqueConstraint`, `insert`),
`sqlalchemy.dialects.sqlite.insert as sqlite_insert`, `sqlalchemy.exc` (`DBAPIError`,
`OperationalError`), `sqlalchemy.orm` (`DeclarativeBase`, `Mapped`, `mapped_column`),
`sqlalchemy.types.CHAR`; `import script_context as sc` (D-i5-2).

Docstrings move verbatim — every SPEC-section citation in them
(`SPEC 2.2/3.3.1/3.3.2/3.3.3/3.6`, the `development/2026-07-13-…/SPEC.md 3.1, 3.3.2`
pointer, CLAUDE.md references) was verified still-resolving on 2026-07-20 (§7
obligation 4). The "MUST NOT be removed" commit comments in the two loaders are part of
Invariant 5 and move byte-for-byte.

## 4. Deliverables B–D — the state move, the remnant, the tests

**B — `script_context.py`** (un-grandfathered since I4 — edits must keep the broad gate
green): add the two counter definitions with types (`dict[str, int]`) and the 829–838
comments verbatim, placed with the other mutable run state. No other change.

**C — `psh/_legacy.py`:** delete the move set + counters; add
`from psh.db import (…every moved name…)` in the import block (I2 pattern — all names,
so `psh.<name>` test references keep resolving); repoint the four remnant-reader
counter reads (1210, 1211, 1296, 1297) to `sc.`; the `sc.db_engine_args = db_engine_args`
exposure line (1155) stays — it resolves via the re-import, and the façade house-rule
test pins it (Invariant 9). Orphaned-import sweep, each removal verified by grep
(pre-verified 2026-07-20, implementer re-verifies): orphaned — the seven-name
`from sqlalchemy import (…)` block, `sqlite_insert`, `OperationalError`,
`DeclarativeBase`/`Mapped`/`mapped_column`, `CHAR`, `NamedTuple`; NOT orphaned —
`DBAPIError` (`abort_reason` 1409–1415), `SQLAlchemyError` (1199/1205/1463),
`sqlalchemy as db` (B10, 1997/2007), `time`, `escape`. `db_retryable` is still called
by `abort_reason` → covered by the re-import.

**D — tests:** the counter-seam repoints of D-i5-3 (each file gains
`import script_context as sc` if it lacks one; `monkeypatch.setattr(sc, …)` +
`sc.db_reconnect…` assertions), plus conftest's `_SC_ATTRS`/`reset_sc` additions
(D-i5-4). Nothing else — no new tests are owed: this increment adds no behavior, and
"behavior-preserving relocations [are] covered by the existing suite staying green"
(I4 SPEC §9 precedent, per implementation-standards § Test discipline's carve-out
logic — the moved code's seams are already the tested seams:
`test_load_traffic_rows_releases_the_connection`, the `db_retry` contract suite, the
roundtrip suite, `test_abort_e2e.py` through the real `main()`).

## 5. Ratchet (§13) — measured findings and dispositions

Broad ruff was run 2026-07-20 on a scratch assembly of the exact move (verbatim bodies
+ final imports); pyright standard on the same content at `psh/db.py`. Findings
(exhaustive — anything new at implementation time is disposed inline and
ledger-recorded, I3 precedent):

| Finding | Where | Disposition |
|---|---|---|
| ERA001 commented-out code | `# id: Mapped[int]…` in `PantheonTraffic` | **delete the line** — a considered-and-rejected surrogate key, documented by the composite `PrimaryKeyConstraint` right below it; ratchet D2 ("cleaned exactly once, as it moves") |
| RUF013 implicit Optional (+ pyright reportArgumentType) | `db_retry(…, site: str = None)` | `site: str | None = None` — §6's real-annotation replacement, behavior-preserving |
| DTZ007 naive strptime | `update_traffic_rows` | `# noqa: DTZ007` + reason: Pantheon's `env:metrics` timestamps are naive date markers, only `.date()` is taken; attaching a tzinfo risks an off-by-one-day shift — a behavior change a move may not make |
| pyright reportInvalidTypeForm | `db_engine_args -> (str, dict)` | `-> tuple[str, dict]` (§6 mandates this replacement per moved module) |
| pyright reportAttributeAccessIssue on `sc.db_reconnect…` | `db_retry` | resolved by Deliverable B's typed module-level definitions (measured: errors vanish once defined) |

No `ruff-broad.toml` `ignore` additions (would be a §13 amendment). No
`extend-exclude` deletion (the code lands in a fresh gated file — I2/I3 precedent;
`_legacy.py` stays grandfathered).

## 6. Behavior bar & invariants applied (§8/§9)

- Four goldens byte-identical (Invariant 1): the move renders nothing differently —
  same objects, same call graph, re-imports alias the same functions.
- Invariant 5 holds by construction and by its named guard:
  `test_load_traffic_rows_releases_the_connection` moves nothing and must stay green
  unweakened; `db_retryable`'s predicate and `db_retry`'s unit-granularity move
  byte-identically.
- Invariant 4: `abort_reason`/`finish_run`/`abort_run` logic untouched — only their
  counter reads re-spell to `sc.` (same dict objects at call time).
- Artifact structure (§8): `-run.json`'s `reconnects_by_site`/
  `reconnect_failures_by_site` blocks read the same dicts through the new spelling.
- Invariant 9: no `sc` name removed; `sc.db_engine_args` keeps resolving (façade test).
  New `sc` attributes (the counters) are additions — sanctioned by §3.5.
- Invariant 7: no interlock change; no new subprocess/network paths (§ directives 6).
- Exit codes/resume semantics/config keys: untouched.

## 7. Task shape (for the plan)

Task 1 — the move (Deliverables A–D in one atomic commit: the code, the state, the
re-imports, the test repoints — partial application cannot be green). Gates: full
`--fast` suite green with collected count unchanged (**780** passed / 1 skipped / 2
deselected baseline at I4 close; this increment adds/removes no tests), goldens diff
empty, broad ruff clean on `psh/db.py` + `script_context.py`, narrow ruff whole-tree
clean, pyright 0 errors. **Correction (Task 2, PD#14):** this section originally said
"782" — that is LEDGER I4's **full**-tier count (`--fast` plus the live tier, credentials
present at I4 close). The `--fast`-tier baseline is 780 passed / 1 skipped / 2 deselected;
782 must never be pasted as a `--fast`-tier expectation.
Task 2 — docs/memory/ledger (CLAUDE.md § Database rewrite for the new home + seam
note; the models-"near the top of the script" line; memory update; LEDGER I5 entry;
this SPEC's acceptance section filled).

## 8. Documentation & memory obligations (same change, §7)

- CLAUDE.md: § Database gains the `psh/db.py` home (models, row types, resilience
  layer, `db_engine_args` — re-imported by `_legacy`, same import-back pattern);
  counter location + `sc.` access noted; the "class defs near the top of the script"
  sentence corrected; test-seam guidance (counters patched at `script_context`, not
  `psh`). Delete prose the move obsoletes; report the line-count delta
  (implementation-standards § Definition of Done).
- Memory: update `modularization-campaign.md` progress; extend `db-idle-connection-reaped.md`
  (or add) with the new home + the counter-seam patching fact.
- `LEDGER.md`: I5 entry with ledger notes D-i5-1 (counters), B10/B11 stay (I13), the
  "relocated intact" reading (D-i5-3), ratchet dispositions, any finding-table
  corrections.

## 9. Acceptance (commands run and output pasted at close — never summarized)

Terminus credentials were present in this environment (`terminus auth:whoami` →
`markmont@umich.edu`), so item 2 ran the **full** suite including the live tier — no
`--fast`-only fallback was needed, and no ledger note about a skipped live tier applies.

**1 & 2. `./run-tests --llm`** (full run, live tier included; run 2026-07-20, Task 2 close):

```
$ ./run-tests --llm
All checks passed!
All checks passed!
0 errors, 0 warnings, 0 informations
................................s....................................... [  9%]
........................................................................ [ 18%]
........................................................................ [ 27%]
........................................................................ [ 36%]
........................................................................ [ 45%]
........................................................................ [ 55%]
........................................................................ [ 64%]
........................................................................ [ 73%]
........................................................................ [ 82%]
........................................................................ [ 91%]
...............................................................          [100%]
LLM_SUMMARY passed=782 failed=0 error=0 skipped=1 xfailed=0 xpassed=0
--------------------------- snapshot report summary ----------------------------
27 snapshots passed.
782 passed, 1 skipped in 31.66s
Linting (ruff, narrow PD set) ...
Linting (ruff-broad.toml, campaign ratchet) ...
Type-checking (pyright, campaign ratchet) ...
```

782 = the 780/1/2-deselected `--fast`-tier baseline plus the 2 live-tier tests the
credentials unlock — consistent with LEDGER I4's full-tier close count (also 782, before
this increment added or removed any test). Collected count unchanged; both ruff gates and
the pyright gate report clean/0 inline above ("All checks passed!" ×2, "0 errors, 0
warnings, 0 informations").

**3. Goldens byte-identical against the pre-I5 baseline (`1cf37d3`, = HEAD before Task 1's
commit `c291a26`):**

```
$ git diff 1cf37d3 -- tests/e2e/__snapshots__/ | wc -l
0
```

**4. Broad ruff on the moved/changed files:**

```
$ uvx ruff check --config ruff-broad.toml psh/db.py script_context.py
All checks passed!
```

**5. Narrow ruff, whole tree:**

```
$ uvx ruff check .
All checks passed!
```

**6. pyright gate:** 0 errors, 0 warnings, 0 informations (pasted inline in items 1 & 2
above, as part of `./run-tests`'s three-gate sequence).

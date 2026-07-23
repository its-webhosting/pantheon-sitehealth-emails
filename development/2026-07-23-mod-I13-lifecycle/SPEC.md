# SPEC — Campaign increment I13: `psh/lifecycle.py` + `RunState` + `main()` final form

**Campaign:** `development/2026-07-17-modularization-campaign/` (CAMPAIGN.md §11 row I13,
Wave 3). This spec cites CAMPAIGN.md by section and re-derives nothing (§Preamble).
Governing documents read in full this session: CAMPAIGN.md, LEDGER.md (all entries),
BLOCKMAP.md, CLAUDE.md, `prompts/directives.md` (the Spine), `prompts/new-feature-standards.md`.

**MUST/SHOULD/MAY/NEVER** per CAMPAIGN.md §Glossary.

## Glossary (this spec only; campaign terms in CAMPAIGN.md, domain terms in CONTEXT.md)

- **Accumulators** — the four B14 run-scoped locals of `main()` (`emails_sent`,
  `site_savings`, `all_warnings`, `site_results`) plus the two reconnect counter dicts
  currently living as `script_context.py` module attributes (D-i5-1's scheduled interim
  home).
- **`RunState`** — the §6 dataclass introduced this increment: the one home for the
  accumulators.
- **`sc.run_state`** — the `script_context` module attribute holding the current
  `RunState` instance (the one shared, `reset_sc`-isolated namespace joining the
  cross-module writer `psh/db.py` and readers `psh/lifecycle.py` — the D-i5-1 rule).
- **Lifecycle defs** — the ten moved defs listed in §1 Deliverable A.

## 1. Scope (§11 row I13: B14 accumulators, B56, B59–B60; baseline 1649–2107 + the resume helpers I5 left behind)

### Deliverable A — `psh/lifecycle.py` (new module, §3.1 row)

Move, verbatim except the sanctioned §5/§6 edits, from `psh/_legacy.py` (current lines in
parentheses):

| Def | Current lines | Notes |
|---|---|---|
| `ResumeSiteNotFoundError` | 259–264 | |
| `sites_from_resume_point` | 266–279 | |
| `merge_prior_results` | 281–310 | |
| `finish_run` | 333–499 | signature change, §2.2 |
| `resume_point` | 502–513 | annotation fix, §5 (returns `None` at end-of-list) |
| `option_strings_taking_a_value` | 516–528 | `build_arg_parser` bridge, §2.4 |
| `resume_command` | 531–552 | |
| `rerun_command` | 555–575 | |
| `abort_reason` | 578–597 | call-time `psh.db` import, §2.4 |
| `abort_run` | 600–792 | signature change, §2.2 |

**New in the module:** the `RunState` dataclass (§2.1) and its `record_site_notices`
method (the B56 move, §2.3).

`psh/_legacy.py` re-imports all ten defs plus `RunState` (the I2–I12 import-back pattern),
so the `psh.<name>` test references and `main()`'s call sites resolve unchanged.

### Deliverable B — `RunState` threading (B14 accumulators + B57 residue + counters)

`main()` constructs the run's `RunState`, binds it to `sc.run_state`, and every
accumulator read/write in `main()`, `psh/db.py` (`db_retry`), and the moved
`finish_run`/`abort_run` targets it (§2.1–§2.2). The two `script_context.py` counter
attributes are **deleted**. `invoke_hooks("run_finish", run_state)` — the I4 deviation-5
discharge (§2.2).

### Deliverable C — `main()` final form (still hosted in `psh/_legacy.py` — D-i13-1)

- B2/B4 module-import loops → `psh.modules.import_packages` (§2.5; the I4 deviation-6
  discharge).
- B10 engine+sessionmaker → `psh.db.open_database` (§2.6; the D-i5-3 disposition).
- The three I7 dead tail inits deleted (§2.7).
- B56 loop replaced by the `RunState.record_site_notices` call; B57's accumulator writes
  retarget `run_state` (§2.3; the D-i12-4 discharge).
- The import-time-registration assumption made explicit (§2.8; the I4 discovered-task
  discharge).
- Docstring notes on `no_primary_domain_notice` / `sort_notices_and_subject` updated
  (§2.9).

### Deliverable D — tests + docs in the same change (§7 obligations 5–6)

Counter-seam repoint (66 references), `reset_sc` rework, new seam tests (§4), CLAUDE.md /
memory / ledger updates.

### NOT in scope (exhaustive; reasoning preserved per PD#9)

- **Killing `psh/_legacy.py` / moving `main()`+`build_arg_parser`/`parse_args` to
  `psh/cli.py` / redesigning the `psh` conftest fixture** — **D-i13-1, user-approved
  2026-07-23 in this session**: §11 row I13's line scope (baseline 1649–2107) excludes
  `main()`'s own body and the argparse pair; "main() reaches final form" is read as
  *content*-final, not *address*-final. The verbatim relocation, `_legacy.py` deletion,
  and fixture redesign are an I0-style zero-logic file move and land in **I14's remnant
  cleanup** (LEDGER I0 left the timing open as "I13/I14"). Keeps I13 — the increment that
  rewires `db_retry`, the abort flush path, and Invariant 4 — within session limits (D4,
  split-never-compress).
- Parallel site processing (D8 — `RunState` is the design constraint's payoff, not its
  implementation).
- `Notice`-class adoption (re-deferred to I14 at I12; no notice is touched here).
- Any artifact/csv/golden change (§8: I13 has **no** sanctioned surface changes).
- `check/umich/__init__.py`'s stale disabled-branch message (ledgered to I14 at I12).
- The B51 Aug-2026 deletion decision (I14 re-evaluates).

## 2. Design

### 2.1 `RunState` and its one shared home (D-i13-2)

`psh/lifecycle.py` (§6's exhaustive field set — six fields, nothing more; widening needs
a CAMPAIGN §6 amendment):

```python
@dataclasses.dataclass
class RunState:
    """Run-scoped accumulators (CAMPAIGN.md section 6, introduced at I13). ..."""
    emails_sent: int = 0
    site_savings: list = dataclasses.field(default_factory=list)
    all_warnings: list = dataclasses.field(default_factory=list)
    site_results: dict = dataclasses.field(default_factory=dict)
    db_reconnects_by_site: dict = dataclasses.field(default_factory=dict)
    db_reconnect_failures_by_site: dict = dataclasses.field(default_factory=dict)
```

(Real element-type annotations — `list[str]`, `dict[str, int]`, etc. — per §6
house-style replacement; the sketch above shows fields, not final annotations. The two
counter-dict contract comments at `script_context.py:48–59` move onto the fields
verbatim.)

**The one shared home is `sc.run_state`.** Why not parameter threading: `db_retry` (the
counter writer, `psh/db.py`) is reached from `psh/traffic.py` (3 call sites inside
`update_site_traffic`/`import_older_site_metrics`/`load_site_traffic`), `psh/plans.py`
(1, inside `recommend_plan` → `load_overage_protection_window`), and `main()`'s
`build_traffic_table_rows` lambda — threading a `RunState` parameter would widen five
already-pinned signatures for no observable gain. D-i5-1 already named the rule: a writer
and readers in different modules need ONE shared, `reset_sc`-isolated namespace, and that
namespace is `script_context`. §3.4 is honored: the accumulators *live in* `RunState`
(one dataclass instance); `sc` holds the pointer, exactly as it holds `hooks`.

Wiring (the I3 `Notice` / I4 `PHASES` mechanism, plus its cycle rule):

```
script_context.py:  from psh.lifecycle import RunState     # top of file
                    run_state: RunState = RunState()        # module attr, reset_sc-rebound
psh/lifecycle.py:   NEVER imports script_context / psh.db / psh._legacy at module level
                    (call-time imports inside functions, the psh/modules.py precedent) —
                    module-level imports are stdlib + sqlalchemy.exc + rich only.
psh/db.py:          db_retry writes sc.run_state.db_reconnects_by_site /
                    sc.run_state.db_reconnect_failures_by_site
                    (sc reached exactly as it reaches the counters today).
main():             sc.run_state = RunState()   # fresh per run, BEFORE
                    run_state = sc.run_state    # invoke_hooks("setup") — see below
```

**Construction point (spec-review finding 8):** `sc.run_state = RunState()` is placed
**before `invoke_hooks("setup")`**, not at B14 where the four locals initialize today.
No current setup-phase code reaches `db_retry` (verified: all five reach sites are
inside the site loop), but a future setup hook using it would otherwise write into the
module-default `RunState` that `main()` then silently discards — a latent PD#1 shape.
Placing the rebind first makes the whole run one `RunState`, observably identical today.

Cycle proof (why lifecycle's module-level import set MUST stay as stated):
`script_context → psh.lifecycle` is the new top-level edge; `psh.db → script_context`
already exists (module-level, `psh/db.py:41`, attribute access at call time). If
`psh.lifecycle` imported `psh.db` at module level, the sharp failure is the
`import psh.db`-first order: `psh.db` line 41 → `script_context` → `psh.lifecycle` →
`from psh.db import DatabaseUnavailableError` against a `psh/db.py` paused at line 41,
before the class exists → `ImportError` at startup (spec-review finding 9's precise
mode). Call-time imports (documented in the module docstring with a diagram, PD#8)
dissolve every edge. `psh/lifecycle.py`'s docstring MUST carry this diagram.

The `script_context.py` attributes `db_reconnects_by_site` / `db_reconnect_failures_by_site`
are **deleted**. A stale test patch or read fails loudly (`monkeypatch.setattr` raises on
a missing attribute; so does a read) — the same loud-failure property the I5 move
established, one level up.

### 2.2 `finish_run` / `abort_run` / `run_finish` (B59–B60 + the I4 deviation-5 discharge)

Signatures change (a §8-free surface: both are internal defs; stdout and artifacts stay
byte-identical — the bodies read the same values from new names):

```python
def finish_run(db_session, db_engine, site_count: int, run_state: RunState,
               *, aborted_at: str | None = None, reason: str | None = None) -> None
def abort_run(db_session, db_engine, site_name: str | None, reason: str,
              error: BaseException, *, emailed: bool, site_names: list[str],
              site_count: int, run_state: RunState) -> None
```

Body edits are mechanical renames only: `emails_sent` → `run_state.emails_sent`,
`all_warnings` → `run_state.all_warnings`, `site_results` → `run_state.site_results`,
`site_savings` → `run_state.site_savings`, `sc.db_reconnects_by_site` →
`run_state.db_reconnects_by_site`, `sc.db_reconnect_failures_by_site` →
`run_state.db_reconnect_failures_by_site`. Every other line — the SIGINT ignore, the
rollback, the pop/filter drop rules, the escape() discipline, the soft_wrap prints, the
artifact write gates, `{ymd}-run.json` nesting, exit codes, the fatal re-raise — moves
**verbatim** (Invariant 4; §8 rows "artifacts", "exit codes, resume semantics" NEVER
change). `finish_run` reads the counters from its `run_state` parameter, not from `sc`
(one source; `main()` passes `sc.run_state`, so production sees the same object
`db_retry` wrote).

**`run_finish` fires with the `RunState`:** `finish_run`'s first statement becomes
`sc.invoke_hooks("run_finish", run_state)` — CAMPAIGN §4's "receiving the RunState",
deferred at I4 (deviation 5) because the type did not exist. **No in-repo check/plugin
registers a `run_finish` hook**, but ONE test does (spec-review finding 1, corrected):
`tests/integration/test_finish_run.py:59–62` registers a zero-arg probe lambda whose
arity the new invoke breaks (`TypeError`) — its lambda gains the `run_state` parameter
in the same change (§4 item 4 extends that very test). The phase-list pins
(`tests/unit/test_contract_registry.py:26`, `tests/integration/test_hooks_phases.py`)
are unaffected. `CONTRACT["run_finish"]` stays `()` — the `RunState` is the
hook *argument*, not a contract key. The stale "No arguments until I13's RunState"
comments (at the invoke site and in `psh/modules.py`'s `PHASES` comment, if present) are
rewritten (Directives #7-adjacent stale-diagram rule; grep for the phrase).

### 2.3 B56 + B57 residue (the D-i12-4 discharge)

The B56 append loop (current `_legacy.py:1476–1485`, including its load-bearing
"BEFORE the send" comment) becomes a `RunState` method, moved with comment intact:

```python
def record_site_notices(self, notices: list[dict], contacts: str) -> None:
    """Append a completed site's notice csv rows (with contacts inserted at field 2)
    to all_warnings.  Called BEFORE the SMTP send, never after: ...(comment verbatim)..."""
```

`main()` calls `run_state.record_site_notices(site_context["notices"], contacts)` at the
exact same position (before the `smtp_enabled` block — Invariant 4's
notices-before-send rule; the position is what the comment guards, so the call site keeps
a one-line pointer comment). The B42 `--only-warn` append
(`run_state.all_warnings.append(n["csv"])`) is a **different row shape** (no contacts
field) and B42 stays in `main()` per §3.3 — it is NOT routed through the method
(PD#1: silently inserting an empty contacts field would change `-notices.csv` rows, a §8
NEVER).

B57 residue: `emails_sent += 1` → `run_state.emails_sent += 1`; `site_emailed = True`
unchanged (a loop-local feeding `abort_run(emailed=…)`, not a §6 field). The B57 block
itself stays in `main()` — D-i12-4's reasoning (the accumulator write sits between
`send_message()` and `quit()`) applies at the new spelling identically.

### 2.4 The two call-time bridges in `psh/lifecycle.py` (D-i13-3)

- `abort_reason` needs `DatabaseUnavailableError` / `db_retryable` / (sqlalchemy's
  `DBAPIError` is module-level-safe): `from psh.db import DatabaseUnavailableError,
  db_retryable` at **call time** (§2.1 cycle rule; `# noqa: PLC0415` two-line form, the
  I6 precedent).
- `option_strings_taking_a_value` needs `build_arg_parser`, which stays in
  `psh/_legacy.py` until I14 (D-i13-1): call-time `from psh._legacy import
  build_arg_parser` (`# noqa: PLC0415`), the D-i6-2/I9 `escape_url` bridge pattern.
  **I14 obligation:** replace with a module-level `from psh.cli import build_arg_parser`
  when the argparse pair moves — recorded in the ledger entry's open questions AND as a
  comment at the bridge.

### 2.5 B2/B4 → `psh.modules.import_packages` (the I4 deviation-6 discharge)

New in `psh/modules.py` (§3.1 assigns "module loading (B2/B4)" there):

```python
def import_packages(kind: str) -> dict:
    """Import every kind ('plugin' or 'check') package find_modules discovers;
    returns {dotted_name: module} in discovery order."""
```

`main()` becomes `sc.plugin = import_packages("plugin")` … pass-1 `process_config` …
`sc.check = import_packages("check")` — the B2→B3→B4 *ordering* (the two-pass
substitution order, §3.3) stays visible in `main()`; only the loop mechanics move. The
banner/per-module `sc.debug` prints move inside, byte-identical. **Precondition to
verify at implementation (grep, PD#14):** no `plugin/`/`check/` package reads
`sc.plugin`/`sc.check` at import time (else the wholesale-assign timing would differ from
today's incremental fill; if any does, fall back to mutating the registry in place and
note it in the task report).

### 2.6 B10 → `psh.db.open_database` (D-i13-4; the D-i5-3 disposition)

```python
def open_database(db_config: dict, *, echo: bool = False) -> tuple[Engine, Session]
```

Moves `db_engine_args(...)` call + `create_engine` + `sessionmaker(expire_on_commit=False)`
+ session construction, with the load-bearing `expire_on_commit` comment, into
`psh/db.py` (making CLAUDE.md's "psh/db.py holds every DB touch this program makes"
finally true — today `create_engine` lives in `main()`). `main()`:
`db_engine, db_session = open_database(sc.config["Database"], echo=sc.options.verbose >= 2)`.
**D-i13-5 — the B11 `--create-tables` short-circuit (`Base.metadata.create_all` +
`sys.exit`) stays in `main()`.** §3.3's exhaustive stays-list names neither B10 nor B11;
this spec moves B10 (above) and keeps B11 because it is option gating on the
orchestrator's control flow (`sys.exit` cannot cross a function boundary usefully — the
D-i6-1 loop-control reading), preserving today's B10→B11 order. A ledger note, not an
amendment (the D-i5-3 precedent already recorded the interim; the ledger entry MUST name
this disposition — spec-review finding 4). The `sc.debug("=== Connecting …")` banner
stays in `main()` (orchestration narration).

### 2.7 The three I7 dead tail inits (LEDGER I7 discharge)

Delete `_legacy.py:1088–1090` (`site_recommended_plan = site["plan_name"]`,
`site_current_plan_index = 0`, `site_recommended_plan_index = 0`) — always overwritten by
the `rec` unpack on every path that reads them. **`site_current_plan` (1087) stays** —
read by the empty-`plan_on_day` guard and `stuff_plans_contract` (LEDGER I7: "only those
three").

### 2.8 Import-time registration made explicit (the I4 discovered-task discharge)

A short comment at `main()`'s `validate_hooks()` call site + one sentence in
`psh/modules.py`'s docstring: hooks register at package import time; `validate_hooks()`
runs once after the import loops, so a hook registered later (no in-repo case exists)
bypasses DAG conditions 1–4 and only `add_hook`'s declaration check fires. Doc-only.

### 2.9 Helper docstring notes

`no_primary_domain_notice` ("final home I13's call") and `sort_notices_and_subject`
("final home I13's main()") stay in `psh/_legacy.py` beside `main()` (D-i13-1) — their
notes are rewritten to "rides to `psh/cli.py` with `main()` at I14 (D-i13-1)". Doc-only.

> **Correction (Task 3).** This paragraph was wrong about `no_primary_domain_notice`:
> verified at `6f5c282^` (pre-Task-1), that function's docstring never carried a "final home
> I13's call" note — only `sort_notices_and_subject` had one ("final home I13's main()"). The
> Task 2 implementer rewrote `sort_notices_and_subject`'s note to the ride-to-`psh/cli.py`
> wording and, honoring §2.9's intent for both, **added** the same ride-note to
> `no_primary_domain_notice`'s docstring (it did not have one to rewrite). Doc-only; the
> discrepancy is recorded in the Task 2 report and here rather than silently absorbed.

### 2.10 Flow after I13 (PD#8)

```
main()                                   psh/lifecycle.py         psh/db.py
──────                                   ────────────────         ─────────
sc.run_state = RunState() ──────────────► RunState ◄───────────── db_retry writes
run_state = sc.run_state                  (the one instance)      sc.run_state.db_reconnects…
  │ per-site loop:
  │   run_state.site_results[…] = …
  │   run_state.site_savings.append(…)
  │   --only-warn: run_state.all_warnings.append(n["csv"])
  │   run_state.record_site_notices(notices, contacts)   # B56, before send
  │   smtp: run_state.emails_sent += 1                   # B57 residue
  ▼
except BaseException ─► abort_reason(e) ─► abort_run(…, run_state=run_state) ─┐
finish_run(db_session, db_engine, site_count, run_state) ◄────────────────────┘
  └─► sc.invoke_hooks("run_finish", run_state)   # first statement, both paths
```

## 3. Behavior bar (§8) analysis

| Surface | This increment |
|---|---|
| 4 goldens | byte-identical (nothing rendering-side changes; Invariant 1) |
| `-results.json` / `-notices.csv` / `-run.json` | byte-identical structure AND values (renames only; same dict objects reach the writers) |
| notice csv values | NONE (I13 has no §8 sanction and needs none) |
| stdout | identical modulo `console.log` location stamps at `-v` (`sc.debug` stamps the caller's `file:line`, which the B2/B4 and lifecycle relocations shift — §8-sanctioned, the I2/I6 precedent; spec-review finding 7) |
| config keys | none added, none touched |
| exit codes / resume semantics / write gates | unchanged verbatim (Invariant 4) |

## 4. Seams under test (exhaustive; agreed here per the Spine spec bar)

Existing seams that keep working unchanged **for callers** via the `_legacy` re-imports:
`psh.finish_run` / `psh.abort_run` / `psh.abort_reason` / `psh.resume_point` /
`psh.resume_command` / `psh.rerun_command` / `psh.option_strings_taking_a_value` /
`psh.sites_from_resume_point` / `psh.merge_prior_results` / `psh.ResumeSiteNotFoundError`
(files, exhaustive: `tests/unit/test_resume_from.py`, `tests/unit/test_abort_reason.py`,
`tests/unit/test_db_resilience.py`, `tests/integration/test_abort_run.py`,
`test_finish_run.py`, `test_regressions.py`,
`tests/e2e/test_unknown_framework_e2e.py`, `test_abort_e2e.py`).

**NEW two-binding trap (spec-review finding 2 — the I2 `run_terminus` lesson applies to
this very move):** `abort_run` calls `finish_run` internally; after the move that call
resolves in **`psh.lifecycle`'s** namespace, so `test_abort_run.py:58`'s
`monkeypatch.setattr(psh, "finish_run", …)` no longer intercepts it. The patch target
becomes **`psh.lifecycle.finish_run`** (and the fake's positional signature updates to
the new `run_state` shape). This joins the documented two-binding trap family
(CLAUDE.md § Two mock seams gains the entry at Task 3).

Mandatory repoints/reworks (mechanical; no assertion weakened — PD#14):

1. **Counter seam** (**59** references across 6 test files — conftest 4,
   test_finish_run 24, test_db_resilience 27, test_abort_run 2, test_db_credentials 1,
   test_traffic_table_rows 1): `sc.db_reconnects_by_site` →
   `sc.run_state.db_reconnects_by_site` (and failures likewise). Tests MAY instead
   construct a fresh `RunState` and pass it directly — the preferred new idiom for
   `finish_run`/`abort_run` tests. **Excluded from the repoint (spec-review finding 3):**
   the 7 hits on the `-run.json` artifact keys
   (`db_reconnects_healed_this_run`/`db_reconnect_failures_this_run` assertions in
   `test_finish_run.py` and a `test_db_resilience.py` comment) — those guard a §8 NEVER
   surface and MUST NOT be renamed.
2. **`reset_sc`** (`tests/conftest.py`): `_SC_ATTRS` gains `"run_state"`, drops the two
   counter names; the body sets `sc.run_state = RunState()` (import via the `psh`
   fixture's module or `from psh.lifecycle import RunState`).
3. **`finish_run`/`abort_run` call updates** in tests: accumulator args collapse into a
   constructed `RunState`; `test_abort_run.py`'s `fake_finish_run` signature likewise.
4. **`test_finish_run.py`'s existing `run_finish` probe** (lines 59–62): its zero-arg
   lambda gains the `run_state` parameter (§2.2; finding 1).

New tests (each red-first per `mattpocock-skills:tdd`):

5. **`run_finish` receives the `RunState`** — register a probe hook (declared
   `consumes=[]/produces=[]`), call `finish_run(...)`, assert the hook got the exact
   instance (extends the existing probe test per §2.2). (Red on the old zero-arg invoke.)
6. **`RunState.record_site_notices`** — unit: csv field-2 insertion + append order;
   red-first against a hand-rolled expected list.
7. **Deleted counter attrs fail loudly** — `hasattr(sc, "db_reconnects_by_site") is False`
   (guards the one-owning-namespace rule; red today).
8. **`import_packages`** — integration: returns discovery-ordered dict, `sc.debug` banner
   emitted (via `recording_console`); grep-precondition from §2.5 verified in-code where
   cheap.
9. **`open_database`** — integration: sqlite tmp path, engine echo flag wiring,
   `expire_on_commit=False` on the session (assert `session.expire_on_commit is False`).

Notes for implementers (two-binding traps, CLAUDE.md § Two mock seams): `abort_run`'s
SIGINT guard — in-process tests keep patching the **shared `signal` module object**
(`monkeypatch.setattr(psh.signal, "signal", …)` still works: `psh/lifecycle.py` imports
the same module singleton). `psh.mail.SMTP_SSL` and `psh.gateway.run_terminus`/
`psh.gather.run_terminus` traps unchanged by this increment.

The `main()`-final-form glue (RunState construction, the retargeted writes) has no seam
above the e2e goldens; it is covered by the four goldens + `test_abort_e2e.py` +
`test_unknown_framework_e2e.py` end-to-end (the artifacts and stdout those pin are
produced entirely from `RunState` fields after this change — a mis-thread goes red
there). No further pure-helper extraction is warranted (the writes are one-line
statements; the Spine's named-extraction rule applies to logic, not assignments).

## 5. Ratchet (§13) predictions

`psh/lifecycle.py` born gated (broad ruff + pyright standard; never in `extend-exclude`;
nothing deleted from the exclude list — I2–I12 precedent, `_legacy.py` stays
grandfathered until I14). Predicted findings on the moved bodies (implementer confirms
against real tool output, PD#14; unpredicted findings dispositioned per precedent and
recorded):

- House-style annotations (§6): `resume_point -> str` is WRONG (returns `None` at
  end-of-list) → `-> str | None`; `option_strings_taking_a_value() -> set` →
  `set[str]`; `sites_from_resume_point(... ) -> list` → `list[str]`; `finish_run`'s
  `aborted_at: str = None` / `reason: str = None` → `str | None` (RUF013).
- `SLF001` on `build_arg_parser()._actions` (private member; moved verbatim) → noqa +
  reason.
- `DTZ002` on `datetime.datetime.today()` in `finish_run` → noqa + reason (naive local
  date names the artifact files; tz-attaching risks a date shift at midnight UTC — the
  I5/I6 DTZ posture).
- `PTH110`/`PTH123` (`os.path.exists`/`open`) → rewrite or noqa per I12's disposition
  pattern (artifact writes moved verbatim: noqa where rewriting alters bytes-on-disk
  risk surface, rewrite where provably identical).
- `PLC0415` ×2 (the §2.4 call-time bridges) → two-line noqa, I6 form.
- `B904` on `sites_from_resume_point`'s `raise ResumeSiteNotFoundError(resume_from)`
  inside `except ValueError:` (B904 is NOT in `ruff-broad.toml`'s ignore list;
  spec-review finding 9) → `from None` (the original `ValueError` is an implementation
  detail of `.index()`, not context worth chaining) — behavior-identical for every
  caller that catches the named error.
- `C901`/`PLR0912`/`PLR0915`/`PLR0913` on `finish_run`/`abort_run` (verbatim large
  bodies; `abort_run` keyword-heavy signature) → noqa on the defs, I6/I11 precedent.
- `B008`? No. `EM101`/`TRY003` ignored repo-wide. `S603`? No subprocess here.
- pyright: `run_state` field annotations resolve; `sc.*` access is call-time (D-i8-7
  posture inherited — pyright scope UNCHANGED, `psh/` minus `_legacy.py`; **I14 inherits**).

`psh/db.py`, `psh/modules.py`, `script_context.py` edits: all already gated; MUST stay
0-findings. `tests/` stays excluded from the broad set (grandfathered tree).

## 6. `main()` final-form measurement (§3.3 / §17 Q1 honesty clause)

Today: 652 raw (874–1525 inclusive; `main()`'s last statement is 1523) / 470 logic lines
(measured this session: `sed -n '874,1525p' psh/_legacy.py | wc -l` → 652; `… | grep -vc
'^\s*$\|^\s*#'` → 470; spec-review finding 5 corrected the raw figure). This increment
removes from `main()`: the B2/B4 loop bodies (~10), B10 (~15), the three dead inits,
B56's loop (~8) — landing (estimate) at **~615 raw / ~440 logic**. That is **above** §3.3's 250–400 target. Position: §3.3's stays-list plus the
ledgered call-site decisions (D-i6-1, D-i8-2, D-i12-2/3/4 kept fetch guards, threading,
and `template_dict` in `main()`) IS what `main()` now contains — the 250–400 figure was
a planning estimate that did not price those ledgered stays or the file's comment
density. **The closing task MUST paste the measured numbers into the ledger entry** and
flag the delta for I14's §17 Q1 audit; this spec does NOT invent extra extractions to
game the number (each §3.3 "stays" line would be the thing extracted, contradicting the
frozen architecture — PD#14: measure, don't massage).

## 7. Task decomposition (for the plan; each test-first per `mattpocock-skills:tdd`)

1. **Task 1 — the lifecycle move + RunState + counter rewire** (atomic; a partial move
   cannot be green — I5/I6/I11 single-commit precedent): Deliverables A+B, `psh/db.py`
   write retarget, `script_context.py` attr swap, `reset_sc` rework, the 66-reference
   repoint, seam tests §4.1–§4.6.
2. **Task 2 — `main()` final form**: Deliverable C (`import_packages`, `open_database`,
   dead inits, B56/B57 retarget in `main()`, §2.8/§2.9 doc edits), seam tests §4.7–§4.8.
3. **Task 3 — closing docs**: CLAUDE.md rewrite of the moved regions (+ the run_finish
   table row's "no arguments" note), memory updates, LEDGER entry, SPEC §9 acceptance
   paste, measurement per §6.

Dispatch per `prompts/implementation-standards.md`: implementers as `psh-implementer`,
reviewers as `psh-reviewer`; reports cite directives by number with verbatim quotes.

## 8. Open questions carried forward (PD#9)

- **I14**: the §2.4 `build_arg_parser` bridge → `psh.cli` module-level import; the
  `main()`/argparse relocation + `_legacy.py` deletion + `psh` fixture redesign
  (D-i13-1); the §6 line-count delta adjudication; plus every item I12 already carried
  (Notice dict retirement, `check/umich/__init__.py` message, B51, config renames).

## 9. Acceptance (§16; run and pasted at close — 2026-07-23, closing task)

Environment had a Terminus token (`ls ~/.terminus/cache/tokens/` → `markmont@umich.edu`),
so `./run-tests` ran the **full** suite including the live tier.

```
$ ./run-tests
...
107 snapshots passed.
================= 1028 passed, 1 skipped, 4 warnings in 43.31s =================
Linting (ruff, narrow PD set) ...
Linting (ruff-broad.toml, campaign ratchet) ...
Type-checking (pyright, campaign ratchet) ...
RUNTESTS_EXIT=0
```

All three gates green (run-tests aborts on the first failing gate, so `EXIT=0` == pytest +
both ruff passes + pyright standard all green). The 1 skip is `test_db_credentials.py`'s
`importorskip("MySQLdb")` on a sqlite-only install. Live tier ran and passed:

```
$ python -m pytest tests/live/test_live_smoke.py -v
tests/live/test_live_smoke.py::test_real_terminus_self_info_parses PASSED [ 50%]
tests/live/test_live_smoke.py::test_real_read_only_site_info PASSED      [100%]
============================== 2 passed in 1.99s ===============================
```

Goldens byte-identical across the whole increment (Invariant 1), against the pre-I13
baseline `268696c` (the I12 archive commit, last before I13 work):

```
$ git diff 268696c -- tests/e2e/__snapshots__/
   (empty)
```

Born-gated files clean under the broad ruff set:

```
$ uvx ruff check --config ruff-broad.toml psh/lifecycle.py psh/db.py psh/modules.py script_context.py
All checks passed!
```

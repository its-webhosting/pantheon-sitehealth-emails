# Campaign I13 Implementation Plan — `psh/lifecycle.py` + `RunState` + `main()` final form

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Dispatch implementers as `psh-implementer` and reviewers as `psh-reviewer`
> (`prompts/implementation-standards.md` overrides the skill's `general-purpose` default).
> The TDD loop is `mattpocock-skills:tdd`, NOT `superpowers:test-driven-development`.

**Goal:** Move the run-lifecycle layer (finish/abort/resume, ten defs) into a new
`psh/lifecycle.py`, introduce the `RunState` dataclass as the one home for the run
accumulators and reconnect counters, and bring `main()` to its final I13 form — with the
four e2e goldens byte-identical and every artifact/exit-code surface unchanged.

**Architecture:** SPEC.md in this directory (adversarially reviewed, committed `4c1ad88`);
it cites CAMPAIGN.md by section. The one shared mutable home is `sc.run_state`
(SPEC §2.1); `psh/lifecycle.py` keeps `script_context`/`psh.db`/`psh._legacy` imports
call-time only (cycle rule). `main()` stays hosted in `psh/_legacy.py` until I14
(D-i13-1, user-approved — NOT reviewable).

**Tech Stack:** Python 3.12, dataclasses, SQLAlchemy (exception types only here), rich,
pytest (`./run-tests`), ruff two-config ratchet + pyright standard.

## Global Constraints (CAMPAIGN.md; every task implicitly includes these)

- **Invariant 1:** the four e2e goldens are byte-identical; `--update-goldens` is FORBIDDEN.
- **Invariant 4:** abort/flush semantics verbatim — exit 1 database / 130 interrupt /
  re-raise fatal; notices-before-send; resume-point next-site-after-email; soft_wrap on
  every copy-pasteable command.
- **Invariant 8:** column-0 `f"""` literals move byte-for-byte (none are in this
  increment's move set, but `main()` edits are adjacent to several — do not re-indent).
- **§8:** artifacts (`-notices.csv`/`-results.json`/`-run.json`) NEVER change in structure
  OR values this increment; stdout may shift only in `console.log` file:line stamps.
- **§13 ratchet:** `psh/lifecycle.py` born gated (broad ruff + pyright standard, 0
  findings); `psh/db.py`/`psh/modules.py`/`script_context.py`/`tests/conftest.py` edits keep
  their existing gates green. Nothing added to or removed from `ruff-broad.toml`.
- **§3.4:** no new module-level mutable state in `psh/`; `sc.run_state` lives in
  `script_context.py`.
- Safety interlock: tests never run `--all`/`--for-real`; only `run_program()` launches
  the program.
- Every task report cites directives by number with a verbatim quote.
- Full file paths in this plan are repo-root-relative (`/workspace`).

---

### Task 1: `psh/lifecycle.py` — the move, `RunState`, and the counter rewire

Atomic (a partial move cannot be green — I5/I6/I11 precedent): one commit at the end.

**Files:**
- Create: `psh/lifecycle.py`
- Create: `tests/unit/test_run_state.py`
- Modify: `psh/_legacy.py` (delete moved defs at 259–310 and 333–792; add re-imports)
- Modify: `script_context.py` (RunState import + `run_state` attr; delete the two counter attrs at ~48–59)
- Modify: `psh/db.py` (4 counter-write sites in `db_retry`)
- Modify: `tests/conftest.py` (`_SC_ATTRS` + `reset_sc` body)
- Modify: `tests/integration/test_finish_run.py`, `tests/integration/test_abort_run.py`,
  `tests/unit/test_db_resilience.py`, `tests/integration/test_db_credentials.py`,
  `tests/integration/test_traffic_table_rows.py` (counter-seam repoints + signature updates)

**Interfaces (Produces — Task 2 and the tests rely on these exact names):**
- `psh.lifecycle.RunState` — dataclass, fields exactly:
  `emails_sent: int = 0`, `site_savings: list[dict]`, `all_warnings: list[str]`,
  `site_results: dict[str, dict]`, `db_reconnects_by_site: dict[str, int]`,
  `db_reconnect_failures_by_site: dict[str, int]` (all mutable ones
  `field(default_factory=…)`), plus method
  `record_site_notices(self, notices: list[dict], contacts: str) -> None`.
- `psh.lifecycle.finish_run(db_session, db_engine, site_count: int, run_state: RunState, *, aborted_at: str | None = None, reason: str | None = None) -> None`
- `psh.lifecycle.abort_run(db_session, db_engine, site_name: str | None, reason: str, error: BaseException, *, emailed: bool, site_names: list[str], site_count: int, run_state: RunState) -> None`
- The other eight defs keep their exact current signatures (modulo §5 annotation fixes).
- `sc.run_state: RunState` (module attribute of `script_context`).
- `psh/_legacy.py` re-imports ALL of: `RunState, ResumeSiteNotFoundError,
  sites_from_resume_point, merge_prior_results, finish_run, resume_point,
  option_strings_taking_a_value, resume_command, rerun_command, abort_reason, abort_run`
  — so `psh.<name>` keeps resolving for every existing test.

- [ ] **Step 1: Write the failing seam tests** (`tests/unit/test_run_state.py`, new file):

```python
"""RunState seam tests (campaign I13, SPEC section 4 items 5-7).

RunState is the one home for the run accumulators (CAMPAIGN.md section 6); the two
reconnect-counter attributes it absorbs are DELETED from script_context, so a stale
patch/read fails loudly (the I5 loud-failure property, one level up).
"""
import pytest

import script_context as sc
from psh.lifecycle import RunState


@pytest.mark.unit
def test_run_state_defaults_are_fresh_per_instance():
    a, b = RunState(), RunState()
    a.all_warnings.append("x")
    a.db_reconnects_by_site["s"] = 1
    assert b.all_warnings == [] and b.db_reconnects_by_site == {}  # no shared mutable defaults
    assert (b.emails_sent, b.site_savings, b.site_results,
            b.db_reconnect_failures_by_site) == (0, [], {}, {})


@pytest.mark.unit
def test_record_site_notices_inserts_contacts_at_field_two():
    rs = RunState()
    rs.all_warnings.append("pre-existing,row")
    rs.record_site_notices(
        [{"csv": "its-wws-test1,no-domains,"}, {"csv": "its-wws-test1,frozen,extra"}],
        "owner@example.edu",
    )
    assert rs.all_warnings == [
        "pre-existing,row",
        "its-wws-test1,owner@example.edu,no-domains,",
        "its-wws-test1,owner@example.edu,frozen,extra",
    ]


@pytest.mark.unit
def test_stale_counter_attributes_are_gone_from_script_context():
    # Guards the one-owning-namespace rule (SPEC 2.1): a test still patching the old
    # sc attributes must fail loudly, not silently miss the counters.
    assert not hasattr(sc, "db_reconnects_by_site")
    assert not hasattr(sc, "db_reconnect_failures_by_site")


@pytest.mark.unit
def test_reset_sc_provides_a_fresh_run_state(reset_sc):
    assert isinstance(sc.run_state, RunState)
    assert sc.run_state.all_warnings == [] and sc.run_state.emails_sent == 0
```

- [ ] **Step 2: Run them to verify they fail for the right reason**

Run: `.venv/bin/python -m pytest tests/unit/test_run_state.py -v`
Expected: collection ERROR — `ModuleNotFoundError: No module named 'psh.lifecycle'`.
(That IS the right reason at this stage; the per-test reds are re-verified in Step 5.)

- [ ] **Step 3: Extend the existing `run_finish` probe test red-first**
  (`tests/integration/test_finish_run.py` — SPEC §4 item 5 / finding 1). Change the
  probe registration in `test_run_finish_phase_fires_before_artifacts_are_written` to:

```python
    seen = []
    received = []
    ymd = datetime.datetime.today().strftime("%Y%m%d")
    reset_sc.add_hook("run_finish", {
        "name": "probe", "consumes": [], "produces": [],
        # CAMPAIGN.md section 4: run_finish hooks receive the RunState (since I13).
        "func": lambda run_state: (seen.append(os.path.exists(f"{ymd}-notices.csv")),
                                   received.append(run_state)),
    })
```

and after the `run(...)` call add:

```python
    assert received == [sc.run_state]   # the hook got THE run's RunState instance
```

Do NOT yet touch the `run(...)` helper: on the current code this test fails with
`TypeError: <lambda>() missing 1 required positional argument: 'run_state'` — record
that RED (it proves the arity change is observable).

- [ ] **Step 4: The move.** All bodies verbatim except the edits named here (extracted-block
  self-diff evidence in the task report, I2 precedent):

  4a. Create `psh/lifecycle.py`: module docstring (MUST carry the cycle diagram —
  SPEC §2.1 quotes the accurate ImportError mode), then module-level imports
  **exactly** stdlib (`dataclasses`, `datetime`, `json`, `os`, `shlex`, `signal`,
  `sys`) + `from sqlalchemy.exc import SQLAlchemyError, DBAPIError` + `from rich.markup
  import escape` + `from rich.pretty import pprint`. NEVER `script_context`, `psh.db`,
  or `psh._legacy` at module level. Then, in order: `RunState` (code below),
  `ResumeSiteNotFoundError`, `sites_from_resume_point`, `merge_prior_results`,
  `finish_run`, `resume_point`, `option_strings_taking_a_value`, `resume_command`,
  `rerun_command`, `abort_reason`, `abort_run` — moved from `psh/_legacy.py:259–310,
  333–792`.

```python
@dataclasses.dataclass
class RunState:
    """Run-scoped accumulators (CAMPAIGN.md section 6, introduced at campaign I13).

    ONE instance per run, created by main() BEFORE invoke_hooks("setup") and bound to
    sc.run_state -- the shared, reset_sc-isolated namespace joining the cross-module
    writer (psh/db.py's db_retry, which reaches it via sc) and the readers
    (finish_run/abort_run, which take it as a parameter).  Widening this field set
    requires a CAMPAIGN.md section 6 amendment.
    """

    emails_sent: int = 0
    site_savings: list[dict] = dataclasses.field(default_factory=list)
    all_warnings: list[str] = dataclasses.field(default_factory=list)
    site_results: dict[str, dict] = dataclasses.field(default_factory=dict)
    # <the two counter contract comments from script_context.py:48-59, moved verbatim,
    #  one block above each field>
    db_reconnects_by_site: dict[str, int] = dataclasses.field(default_factory=dict)
    db_reconnect_failures_by_site: dict[str, int] = dataclasses.field(default_factory=dict)

    def record_site_notices(self, notices: list[dict], contacts: str) -> None:
        """Append a completed site's notice csv rows, contacts inserted at field 2.

        <the B56 "BEFORE the send, not after" comment block from _legacy.py:1476-1481,
         moved verbatim as the rest of this docstring>
        """
        for n in notices:
            fields = n["csv"].split(",")
            fields.insert(1, contacts)
            self.all_warnings.append(",".join(fields))
```

  4b. Named edits to the moved bodies (exhaustive; everything else byte-verbatim):
  - `finish_run`/`abort_run` signatures per **Interfaces** above; body renames ONLY:
    `emails_sent`→`run_state.emails_sent`, `all_warnings`→`run_state.all_warnings`,
    `site_results`→`run_state.site_results`, `site_savings`→`run_state.site_savings`,
    `sc.db_reconnects_by_site`→`run_state.db_reconnects_by_site`,
    `sc.db_reconnect_failures_by_site`→`run_state.db_reconnect_failures_by_site`;
    `abort_run`'s internal `finish_run(...)` call collapses its seven accumulator args
    to `run_state` accordingly.
  - `finish_run` first statement: `sc.invoke_hooks("run_finish")` →
    `sc.invoke_hooks("run_finish", run_state)`; rewrite the stale "No arguments until
    I13's RunState" comment (grep the phrase repo-wide — also in `psh/modules.py`).
  - Every function body that touches `sc.*` gets the call-time
    `import script_context as sc  # noqa: PLC0415` (two-line noqa, I6 form; one per
    function, the `psh/modules.py` precedent).
  - `abort_reason`: call-time `from psh.db import DatabaseUnavailableError, db_retryable
    # noqa: PLC0415`; `DBAPIError` from the module-level sqlalchemy import.
  - `option_strings_taking_a_value`: call-time `from psh._legacy import build_arg_parser
    # noqa: PLC0415` with the I14-obligation comment (SPEC §2.4).
  - §5 ratchet fixes: `resume_point -> str | None`; `option_strings_taking_a_value ->
    set[str]`; `sites_from_resume_point(sorted_site_names: list[str], resume_from: str)
    -> list[str]`; `finish_run` keyword types `str | None`; `raise
    ResumeSiteNotFoundError(resume_from) from None` (B904); `SLF001` noqa on
    `._actions`; `DTZ002` noqa + reason on `datetime.datetime.today()`; PTH/other
    findings per SPEC §5 dispositions — confirm every one against real ruff/pyright
    output, record unpredicted ones (PD#14).

  4c. `script_context.py`: add `from psh.lifecycle import RunState` beside the existing
  `from psh.notice import Notice, Severity`; replace the two counter definitions
  (and move their comments into `RunState`, 4a) with:

```python
# The current run's accumulators (psh/lifecycle.py RunState; campaign I13).  ONE shared
# home for the cross-module writer psh/db.py (db_retry) and the lifecycle readers;
# main() rebinds it fresh per run, reset_sc rebinds it around every test (D-i5-1 rule).
run_state: RunState = RunState()
```

  4d. `psh/db.py`: the four `record_db_reconnect(sc.db_reconnect…_by_site, site)` calls
  (lines ~187, ~203, ~205, ~211) → `record_db_reconnect(sc.run_state.db_reconnect…_by_site,
  site)`; update the module docstring's counter-home sentence (lines ~15–16).

  4e. `psh/_legacy.py`: delete the moved defs; add to the re-import block:

```python
from psh.lifecycle import (
    RunState,
    ResumeSiteNotFoundError,
    abort_reason,
    abort_run,
    finish_run,
    merge_prior_results,
    option_strings_taking_a_value,
    rerun_command,
    resume_command,
    resume_point,
    sites_from_resume_point,
)
```

  Then update `main()`'s two call sites minimally so the file still runs (full final-form
  rework is Task 2 — this task changes ONLY what the new signatures force):
  `sc.run_state = RunState()` + `run_state = sc.run_state` inserted immediately before
  `sc.invoke_hooks("setup")` (SPEC §2.1 construction point); the four B14 accumulator
  locals deleted and every read/write in `main()` retargeted to `run_state.<field>`
  (`emails_sent`, `site_savings`, `all_warnings`, `site_results` — grep each name within
  874–1523); the `abort_run(...)`/`finish_run(...)` call-site args collapse to
  `run_state=run_state` / `run_state`. Orphan check: remove only imports this change
  orphans (grep-verify each candidate — `signal`, `shlex` etc. may still be used by
  remaining code; `json`/`os` are).

- [ ] **Step 5: Test repoints** (mechanical; NO assertion weakened — PD#14):

  5a. `tests/conftest.py`: in `_SC_ATTRS` replace `"db_reconnects_by_site",
  "db_reconnect_failures_by_site"` with `"run_state"`; in `reset_sc`'s body replace the
  two dict resets with:

```python
    sc.run_state = psh.RunState()
```

  5b. Counter-seam repoint, 59 references (SPEC §4 item 1 lists the per-file counts;
  locate with `grep -rn "sc\.db_reconnect" tests/ ; grep -rn 'sc, "db_reconnect' tests/`).
  Two transformation shapes, applied everywhere:

```python
# BEFORE                                                   # AFTER
monkeypatch.setattr(sc, "db_reconnects_by_site", {})       monkeypatch.setattr(sc, "run_state", psh.RunState())
monkeypatch.setattr(sc, "db_reconnect_failures_by_site", {})   # (the one setattr covers BOTH dicts; drop the second line)
assert sc.db_reconnects_by_site == {"s1": 1}               assert sc.run_state.db_reconnects_by_site == {"s1": 1}
```

  **EXCLUDED (SPEC §4 item 1):** the 7 hits on the artifact keys
  `db_reconnects_healed_this_run`/`db_reconnect_failures_this_run` in
  `test_finish_run.py` (+ the `test_db_resilience.py` comment) — those pin `-run.json`
  structure, a §8 NEVER surface. Leave byte-identical.

  5c. `tests/integration/test_finish_run.py` `run(...)` helper — collapse to the new
  signature:

```python
def run(psh, monkeypatch, reset_sc, argv, engine=None, session=None, run_state=None, **kwargs):
    console = recording_console(monkeypatch, reset_sc)
    reset_sc.options = psh.parse_args(argv)
    rs = run_state or psh.RunState(
        emails_sent=2,
        all_warnings=["its-wws-test1,some-notice,detail"],
        site_results={"its-wws-test1": {"plan": "Basic"}},
    )
    monkeypatch.setattr(sc, "run_state", rs)   # what db_retry/the probe hook see
    psh.finish_run(session or FakeSession(), engine or FakeEngine(), 2, rs, **kwargs)
    return console
```

  Tests that seeded counters via `monkeypatch.setattr(sc, "db_reconnects_by_site",
  {...})` now build `psh.RunState(db_reconnects_by_site={...}, ...)` and pass it as
  `run_state=` — value-identical inputs, same expected artifacts (do not change any
  expected JSON/CSV content).

  5d. `tests/integration/test_abort_run.py` `abort(...)` helper: patch target and fake
  signature (SPEC §4, finding 2):

```python
    import psh.lifecycle as psh_lifecycle

    def fake_finish_run(_session, _engine, _site_count, run_state, *_a, **kw):
        captured.update(kw)
        captured["site_results"] = run_state.site_results
        captured["site_savings"] = run_state.site_savings
        captured["ran"] = True

    # abort_run calls finish_run in psh.lifecycle's namespace now -- patching psh.finish_run
    # would silently not intercept (the I2 two-binding lesson; CLAUDE.md § Two mock seams).
    monkeypatch.setattr(psh_lifecycle, "finish_run", fake_finish_run)
    with pytest.raises(expect) as excinfo:
        psh.abort_run(
            FakeSession(), FakeEngine(), site_name, reason, error,
            emailed=emailed, site_names=SITE_NAMES, site_count=10,
            run_state=psh.RunState(
                emails_sent=4,
                site_results=site_results if site_results is not None else {},
                site_savings=site_savings if site_savings is not None else [],
            ),
        )
```

  (The two counter `monkeypatch.setattr(sc, …)` lines in this helper follow shape 5b.)
  Keep `monkeypatch.setattr(psh.signal, "signal", …)` — the shared-module-object seam
  still intercepts (`psh/lifecycle.py` imports the same `signal` singleton).

  5e. `tests/unit/test_db_resilience.py` / `test_db_credentials.py` /
  `test_traffic_table_rows.py`: shape-5b repoints only.

- [ ] **Step 6: Run the moved-seam suites**

Run: `.venv/bin/python -m pytest tests/unit/test_run_state.py tests/unit/test_resume_from.py tests/unit/test_abort_reason.py tests/unit/test_db_resilience.py tests/integration/test_finish_run.py tests/integration/test_abort_run.py tests/integration/test_regressions.py tests/integration/test_traffic_table_rows.py -v`
Expected: ALL PASS (incl. the Step-1 and Step-3 tests now green).

- [ ] **Step 7: Gates + full fast tier**

Run: `uvx ruff check --config ruff-broad.toml psh/lifecycle.py psh/db.py script_context.py`
Expected: `All checks passed!`
Run: `./run-tests --fast --llm`
Expected: 0 failed / 0 error; goldens untouched (`git diff -- tests/e2e/__snapshots__/` empty).

- [ ] **Step 8: Commit**

```bash
git add psh/lifecycle.py psh/_legacy.py psh/db.py script_context.py tests/
git commit -m "feat(campaign-I13): move the run lifecycle into psh/lifecycle.py with RunState"
```

---

### Task 2: `main()` final form — `import_packages`, `open_database`, dead inits, B56/B57

**Files:**
- Modify: `psh/modules.py` (add `import_packages`)
- Modify: `psh/db.py` (add `open_database`)
- Modify: `psh/_legacy.py` (`main()` edits; §2.8/§2.9 doc edits)
- Test: `tests/integration/test_import_packages.py` (create),
  `tests/integration/test_open_database.py` (create)

**Interfaces:**
- Consumes: `RunState` wiring from Task 1 (`run_state` local already in `main()`).
- Produces: `psh.modules.import_packages(kind: str) -> dict[str, ModuleType]`;
  `psh.db.open_database(db_config: dict, *, echo: bool = False) -> tuple[Engine, Session]`.

- [ ] **Step 1: Failing tests** (`tests/integration/test_import_packages.py`):

```python
"""import_packages seam (campaign I13, SPEC 2.5 -- the I4 deviation-6 discharge)."""
import pytest

import script_context as sc
from psh.modules import find_modules, import_packages
from tests.helpers.dnsfake import recording_console  # existing helper, width-defaulted


@pytest.mark.integration
def test_import_packages_returns_discovery_ordered_modules(psh, monkeypatch, reset_sc):
    console = recording_console(monkeypatch, reset_sc)
    loaded = import_packages("plugin")
    assert list(loaded) == find_modules("plugin")          # discovery order preserved
    assert all(m.__name__ == name for name, m in loaded.items())
    # The banner + per-module lines moved inside (byte-identical text, SPEC 2.5) --
    # visible only at -v; reset_sc's default namespace has verbose=0, so force it:
    sc.options.verbose = 1
    console2 = recording_console(monkeypatch, reset_sc)
    import_packages("plugin")
    out = console2.export_text()
    assert "=== Loading plugins:" in out and "Loading plugin: plugin.env" in out
```

(`tests/integration/test_open_database.py`):

```python
"""open_database seam (campaign I13, SPEC 2.6 -- every DB touch now in psh/db.py)."""
import pytest

from psh.db import open_database


@pytest.mark.integration
def test_open_database_builds_engine_and_session(tmp_path):
    engine, session = open_database({"type": "sqlite", "name": str(tmp_path / "t.db")})
    try:
        assert engine.echo is not True
        # REQUIRED, not tuning (SPEC 2.6): load_traffic_rows commits to release the
        # connection; with expiry on, that commit would silently re-SELECT every row.
        assert session.expire_on_commit is False
        assert session.get_bind() is engine
    finally:
        session.close()
        engine.dispose()


@pytest.mark.integration
def test_open_database_echo_flag(tmp_path):
    engine, session = open_database({"type": "sqlite", "name": str(tmp_path / "t.db")}, echo=True)
    try:
        assert engine.echo is True
    finally:
        session.close()
        engine.dispose()
```

- [ ] **Step 2: Verify both fail**

Run: `.venv/bin/python -m pytest tests/integration/test_import_packages.py tests/integration/test_open_database.py -v`
Expected: `ImportError: cannot import name 'import_packages'` / `'open_database'`.

- [ ] **Step 3: Implement.**

  3a. `psh/modules.py` (beside `find_modules`; PRECONDITION first — grep
  `plugin/ check/` for import-time reads of `sc.plugin`/`sc.check`; expected none
  (verified at spec time); if any exist, STOP and mutate-in-place per SPEC §2.5,
  recording it in the task report):

```python
def import_packages(kind: str) -> dict:
    """Import every `kind` ('plugin' or 'check') package find_modules() discovers.

    Returns {dotted_name: module} in discovery order; main() assigns the result to
    sc.plugin / sc.check between the two substitution passes (B2/B3/B4 order, CAMPAIGN.md
    section 3.3 -- the loop mechanics live here, the ordering stays visible in main()).
    """
    import script_context as sc  # noqa: PLC0415 -- call-time import; see the module docstring

    label = "plugins" if kind == "plugin" else "checks"
    sc.debug(f"[bold magenta]=== Loading {label}:")
    loaded = {}
    for name in find_modules(kind):
        sc.debug(f"Loading {kind}: {name}")
        loaded[name] = importlib.import_module(name)
    return loaded
```

  (`import importlib` joins `psh/modules.py`'s module-level imports. The two debug
  strings are byte-identical to `_legacy.py:884/886/893/895` — "Loading plugins:" /
  "Loading plugin: {name}" / "Loading checks:" / "Loading check: {name}".)

  3b. `psh/db.py` (below `db_engine_args`), moving the `expire_on_commit` comment from
  `_legacy.py:971–975` verbatim:

```python
def open_database(db_config: dict, *, echo: bool = False) -> tuple:
    """Build the traffic-DB engine + session (B10; every DB touch lives in this module).

    db_engine_args() supplies the URL and the pool settings (pre-ping/recycle on MySQL);
    echo wires -vv SQL logging.
    """
    conn_str, conn_kwargs = db_engine_args(db_config)
    engine = db.create_engine(conn_str, echo=echo, **conn_kwargs)
    # <the expire_on_commit=False REQUIRED comment, verbatim>
    session = db.orm.sessionmaker(bind=engine, expire_on_commit=False)()
    return engine, session
```

  (Match the actual import spelling in `psh/db.py` — it may import `create_engine`/
  `sessionmaker` directly rather than `db.*`; use whatever is already there. Annotate the
  return `tuple[Engine, Session]` with the types `psh/db.py` already imports, per §6
  house-style replacement.)

  3c. `psh/_legacy.py` `main()` edits (each hunk minimal, adjacent lines untouched):
  - B2/B4 loops (884–888, 893–897) → `sc.plugin = import_packages("plugin")` /
    `sc.check = import_packages("check")` (pass-1 `process_config` stays between them).
  - B10 (960–977) → the banner `sc.debug` line stays, then
    `db_engine, db_session = open_database(sc.config["Database"], echo=sc.options.verbose >= 2)`.
    B11 (979–981) stays verbatim (D-i13-5).
  - Delete dead inits 1088–1090 (`site_recommended_plan = …`, `site_current_plan_index = 0`,
    `site_recommended_plan_index = 0`); KEEP `site_current_plan` (1087).
  - B56 loop (1482–1485) → `run_state.record_site_notices(site_context["notices"], contacts)`
    with a one-line pointer comment replacing the moved block comment
    ("# BEFORE the send -- see RunState.record_site_notices (Invariant 4).").
  - Add the §2.8 import-time-registration comment at the `validate_hooks()` call; one
    matching sentence in `psh/modules.py`'s docstring.
  - §2.9: update the two helper docstring notes (`no_primary_domain_notice`,
    `sort_notices_and_subject`) to "rides to psh/cli.py with main() at I14 (D-i13-1)".
  - Orphan check: `importlib` in `_legacy.py` (B2/B4 were likely its only users;
    grep before removing).
  - Re-import additions to `_legacy.py`: `from psh.modules import import_packages` /
    `from psh.db import open_database` only if tests/`main()` reference them via `psh.` —
    otherwise plain module-qualified calls; follow the existing re-import block style.

- [ ] **Step 4: Verify green + goldens**

Run: `.venv/bin/python -m pytest tests/integration/test_import_packages.py tests/integration/test_open_database.py -v`
Expected: PASS.
Run: `./run-tests --fast --llm`
Expected: 0 failed; `git diff -- tests/e2e/__snapshots__/` empty.

- [ ] **Step 5: Measure `main()` (SPEC §6 — paste into the task report for the ledger)**

Run: `grep -n "^def main" psh/_legacy.py` then with its range `sed -n '<start>,<end>p' psh/_legacy.py | wc -l` and `… | grep -vc '^\s*$\|^\s*#'`
Expected: ~615 raw / ~440 logic (record the ACTUAL numbers).

- [ ] **Step 6: Commit**

```bash
git add psh/modules.py psh/db.py psh/_legacy.py tests/integration/test_import_packages.py tests/integration/test_open_database.py
git commit -m "feat(campaign-I13): bring main() to final form (import_packages, open_database, B56/B57 residue)"
```

---

### Task 3: Closing — docs, ledger, memory, acceptance

**Files:**
- Modify: `CLAUDE.md` (the moved-region prose: new `psh/lifecycle.py` paragraph in
  § Single-module core; § Database counter-seam note → `sc.run_state`; § Two mock seams
  gains the `psh.lifecycle.finish_run` patch-target entry; the contract table's
  `run_finish` row drops "no arguments until I13" for "receives the RunState")
- Modify: `development/2026-07-17-modularization-campaign/LEDGER.md` (append the I13
  entry per §12 template: moved set, D-i13-1…5 + review findings, contract/config/sc
  additions (`sc.run_state`; no new contract keys/config), the §6 measured line count,
  discovered tasks, open questions for I14 incl. the `build_arg_parser` bridge)
- Modify: `/home/node/.claude/projects/-workspace/memory/` (update
  `modularization-campaign.md`; the counter-seam location in any note that names it)
- Modify: `development/2026-07-23-mod-I13-lifecycle/SPEC.md` §9 (paste real acceptance
  output)

- [ ] **Step 1:** Apply the doc edits above (verify every claim against the shipped code
  — Directive #7's stale-diagram rule applies to CLAUDE.md's prose).
- [ ] **Step 2:** Full acceptance: `./run-tests` (all three gates; live tier if
  `ls ~/.terminus/cache/tokens/` shows a token, else `--fast` + ledger note), plus
  `git diff <increment-start-sha> -- tests/e2e/__snapshots__/` (must be empty). Paste
  into SPEC §9.
- [ ] **Step 3:** Commit:

```bash
git add CLAUDE.md development/ 
git commit -m "docs(campaign-I13): close the lifecycle increment"
```

(Memory files live outside the repo — write them, don't `git add` them.)

---

## Self-review (run against SPEC)

- **Coverage:** §1 Deliverables A (Task 1 Step 4a), B (Steps 4b–4e), C (Task 2 Step 3),
  D (Task 1 Steps 1/3/5, Task 2 Step 1, Task 3). §2.1–§2.10 each land in a named step;
  §4 items 1–9 all present (1→5b, 2→5a, 3→5c/5d, 4→Step 3, 5→Step 3, 6/7→Step 1,
  8/9→Task 2 Step 1). §5 in Task 1 Step 4b. §6 in Task 2 Step 5. §8 carried to Task 3
  ledger step.
- **No placeholders:** the verbatim-move bodies are named by exact source line ranges
  (the campaign's established brief form — the source IS the content); all new code is
  shown in full.
- **Type consistency:** `RunState` field names match SPEC §2.1 and are used identically
  in Steps 4b/5c/5d and Task 2's B56 call; `import_packages`/`open_database` signatures
  match between Interfaces and Step 3.

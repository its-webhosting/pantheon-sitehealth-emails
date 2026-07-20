# I4 — Hook engine, DAG, contract registry — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch
> every code-touching task as `psh-implementer`, every review as `psh-reviewer`; TDD via
> `mattpocock-skills:tdd` (NOT superpowers TDD). The authoritative design is `SPEC.md` in this
> folder — read it in full; this plan is the step sequence, the SPEC carries rationale,
> decisions (D-i4-1…7), and invariants.

**Goal:** Move `find_modules` + the hook engine into a new gated `psh/modules.py`, add the
`run_finish` phase, require `consumes`/`produces` on every hook, validate the per-phase hook
DAG fatally at startup, and ship the machine-readable contract registry — four e2e goldens
byte-identical throughout.

**Architecture:** Import-back move (I2/I3 precedent). Engine *functions* move; the mutable
`sc.hooks` dict STAYS in `script_context.py` (SPEC D-i4-1). `script_context.py` re-exports
`PHASES`/`add_hook`/`invoke_hooks` via a module-level from-import (I3 Notice precedent);
`psh/modules.py` therefore must NOT import `script_context` at module level — engine functions
use a function-level `import script_context as sc` (SPEC D-i4-2). The DAG is edgeless today
(no hook produces), so invoke order is observably unchanged.

**Tech Stack:** Python 3.12+, ruff (`ruff-broad.toml` `select=ALL`), pyright (standard),
pytest, syrupy.

## Global Constraints

- **Four e2e goldens byte-identical** (Invariant 1). `--update-goldens` FORBIDDEN. Verify
  `git diff d46f56d HEAD -- tests/e2e/__snapshots__/` is empty at each task end.
- **`psh/modules.py` passes the full gate from birth**: `uvx ruff check --config
  ruff-broad.toml psh/modules.py` → "All checks passed!"; pyright standard → 0 errors.
- **Run pyright via `./run-tests`, NOT `uv run pyright`** (uv.lock churn; `git checkout --
  uv.lock` if it shows modified).
- **No `sc` name removed** (Invariant 9): `sc.PHASES`, `sc.add_hook`, `sc.invoke_hooks`,
  `sc.hooks` must keep resolving. No config keys added. No contract keys added/renamed.
- **Safety interlock**: no `--all`/`--for-real`/live `--create-tables` in tests.
- **Escape untrusted text** in every new `console.print` interpolation (Invariant 6) —
  hook names/messages via `rich.markup.escape`.
- Clear stale `.superpowers/sdd/task-*-report.md` before each dispatch (LEDGER I1 note).
- Baseline commit (I4 start) = `d46f56d`.
- Every task report cites Spine directives by number with a verbatim quote (agent config).
- The inner loop is `./run-tests --fast --llm`; run it at every task end.

---

### Task 1: Pure move — `psh/modules.py` (engine + `find_modules`)

Behavior-preserving relocation; no new behavior, so no new tests — the existing suite
(`test_hooks_phases.py`, e2e goldens) is the guard and must stay green **unchanged**.

**Files:**
- Create: `psh/modules.py`
- Modify: `script_context.py` (delete `PHASES` literal + `_valid_hook_name`/`add_hook`/
  `invoke_hooks` defs; add the re-export import)
- Modify: `psh/_legacy.py` (delete `find_modules` def at lines 526–539; add re-import)

**Interfaces:**
- Produces: `psh.modules.PHASES` (tuple), `psh.modules.find_modules(module_type: str) ->
  list[str]`, `psh.modules.add_hook(hook_name: str, target: dict) -> None`,
  `psh.modules.invoke_hooks(hook_name: str, *args, **kwargs) -> None` — all re-exported as
  `sc.*`; later tasks extend this module.

- [ ] **Step 1: Create `psh/modules.py`**

```python
"""Module discovery and the hook engine (campaign I4; CAMPAIGN.md sections 3.1 and 4).

find_modules() moved from psh/_legacy.py; PHASES/add_hook/invoke_hooks moved from
script_context.py, which re-exports them so sc.add_hook et al. keep resolving for every
check/plugin package (Invariant 9).

Import direction (do not reverse either leg -- see SPEC D-i4-2):

        script_context.py --(module-level from-import: PHASES/add_hook/invoke_hooks)--> psh/modules.py
                ^                                                                          |
                +--------(function-level import, call-time only: hooks/console/debug)------+

script_context imports THIS module at its top, so a module-level `import script_context`
here would make first-import order decide between a working program and an ImportError on a
partially-initialized module.  Engine functions import it at call time instead; by then both
modules are fully initialized.  The mutable hook registry itself (sc.hooks) deliberately
STAYS in script_context: it is cross-cutting run state (CLAUDE.md), psh/ modules add no
module-level mutable state (CAMPAIGN.md section 3.4), and tests/conftest.py::reset_sc
rebinds sc.hooks around every test -- a second copy here would silently desync from it.
"""

import os
import stat
import sys


# Ordered lifecycle phases.  'setup' runs once per run (NOTE: including --create-tables,
# which exits later); the site_* phases run once per processed site, in this order, each
# receiving the SiteContext -- but a per-site fatal error (e.g. a domain:list failure) skips
# that site's remaining phases, so hooks must not assume a later phase always follows an
# earlier one.  Phases through site_post_gather run on full-report and --only-warn paths;
# site_pre_render only on the full-report path; --update and --import-older-metrics never
# reach any site_* phase.  Dotted names (e.g. 'setup.umich.portal') are plugin-defined
# events: allowed, not ordered here.  The per-phase site_context data contract lives in
# CLAUDE.md ("Per-site report pipeline").
PHASES = (
    'setup',
    'site_pre',            # first per-site seam (rename of the old 'check' seam; fires
                           # after the traffic gather, just before site_post_traffic --
                           # no per-phase keys guaranteed)
    'site_post_traffic',
    'site_post_dns',
    'site_post_gather',
    'site_pre_render',
)


def find_modules(module_type: str) -> list[str]:
    modules = []
    # find all non-empty regular files in/under the directory f"{type}" that are named "__init__.py":
    for dirpath, dirs, files in os.walk(module_type, followlinks=True):
        for file in files:
            if file == "__init__.py":
                target = os.path.join(dirpath, file)
                st = os.stat(target)
                if stat.S_ISREG(st.st_mode) and st.st_size != 0:
                    parts = target.split("/")[:-1]
                    target_name = ".".join(parts)
                    modules.append(target_name)
    modules.sort()  # ensure a consistent order when importing to simplify troubleshooting
    return modules


def _valid_hook_name(hook_name: str) -> bool:
    return hook_name in PHASES or '.' in hook_name


def add_hook(hook_name: str, target: dict) -> None:
    import script_context as sc  # noqa: PLC0415 -- call-time import; see the module docstring

    if not _valid_hook_name(hook_name):
        sc.console.print(f'[bold red]ERROR: add_hook: unknown phase "{hook_name}" '
                         f'(known phases: {", ".join(PHASES)}; dotted names are plugin events)')
        sys.exit(1)
    sc.hooks.setdefault(hook_name, []).append(target)


def invoke_hooks(hook_name: str, *args, **kwargs) -> None:
    import script_context as sc  # noqa: PLC0415 -- call-time import; see the module docstring

    if not _valid_hook_name(hook_name):
        sc.console.print(f'[bold red]ERROR: invoke_hooks: unknown phase "{hook_name}"')
        sys.exit(1)
    sc.debug(f'[bold magenta]=== Calling hooks for {hook_name}:')
    for hook in sc.hooks.get(hook_name, []):
        sc.debug(f'Invoking {hook_name} hook target {hook["name"]}')
        hook['func'](*args, **kwargs)
```

Notes for the implementer: the `PHASES` comment block, `find_modules` body (including its
comments), and the error/debug strings are **verbatim** moves — do not reword. ruff-broad
will demand cleanups on the moved code (e.g. `dirs` unused in `find_modules` → rename to
`_dirs`; possible `PTH` findings on `os.path.join`/`os.walk` — `PTH` is NOT ignored, so
convert to `pathlib` ONLY if ruff flags it AND the conversion is behavior-identical
(`os.walk`→`Path.walk` keeps `followlinks` semantics via `follow_symlinks`); otherwise
`# noqa` with an inline reason and record the disposition in the task report for the
ledger). pyright standard must be 0 errors: if it cannot infer `sc.hooks`, annotate in
`script_context.py`: `hooks: dict[str, list[dict[str, Any]]] = {phase: [] for phase in
PHASES}` (minimal out-of-gate fix, I3 precedent — record in report).

- [ ] **Step 2: Edit `script_context.py`**

Delete the `PHASES = (...)` literal with its comment block, and the `_valid_hook_name`,
`add_hook`, `invoke_hooks` defs. Directly below the existing `from psh.notice import
Notice, Severity` line add:

```python
from psh.modules import PHASES, add_hook, invoke_hooks   # noqa: F401 -- add_hook/invoke_hooks re-exported as sc.* for check/plugin packages
```

The `hooks = {phase: [] for phase in PHASES}` line stays exactly where it is (now consuming
the imported `PHASES`).

- [ ] **Step 3: Edit `psh/_legacy.py`**

Delete the `find_modules` def (lines 526–539). Add to the re-import block (next to line
327's `from psh.notice import ...`):

```python
from psh.modules import find_modules
```

- [ ] **Step 4: Full fast suite + gates**

Run: `./run-tests --fast --llm`
Expected: same pass count as baseline (761 passed / 1 skipped / 2 deselected), 27
snapshots; ruff both passes green; pyright 0 errors.

Run: `uvx ruff check --config ruff-broad.toml psh/modules.py`
Expected: `All checks passed!`

Run: `git diff d46f56d -- tests/e2e/__snapshots__/`
Expected: empty output.

- [ ] **Step 5: Commit**

```bash
git add psh/modules.py script_context.py psh/_legacy.py
git commit -m "refactor(campaign-I4): move find_modules + the hook engine into psh/modules.py"
```

---

### Task 2: `run_finish` phase, fired at the top of `finish_run()`

**Files:**
- Modify: `psh/modules.py` (PHASES gains `'run_finish'`)
- Modify: `psh/_legacy.py` (`finish_run()`, def at line 1169 — invoke as first statement)
- Test: `tests/integration/test_finish_run.py` (new test),
  `tests/integration/test_hooks_phases.py` (EXPECTED_PHASES)

**Interfaces:**
- Consumes: Task 1's `psh.modules.PHASES`/`invoke_hooks`.
- Produces: the `run_finish` phase name; `finish_run()` fires it with **no arguments**
  (SPEC D-i4-7; I13 adds `RunState`).

- [ ] **Step 1: Write the failing tests**

In `tests/integration/test_hooks_phases.py`, change `EXPECTED_PHASES` to end with
`"run_finish"`:

```python
EXPECTED_PHASES = (
    "setup",
    "site_pre",
    "site_post_traffic",
    "site_post_dns",
    "site_post_gather",
    "site_pre_render",
    "run_finish",
)
```

In `tests/integration/test_finish_run.py` add (adapt the fixture/arg spelling to the
file's existing `finish_run` call pattern — read the file first; the probe must use the
same reset_sc/options/tmp-cwd harness its neighbors use):

```python
def test_run_finish_phase_fires_before_artifacts_are_written(psh, reset_sc, tmp_path, monkeypatch):
    """run_finish is the seam for future run-level artifact hooks (CAMPAIGN.md section 4):
    it must fire before {ymd}-notices.csv / {ymd}-results.json / {ymd}-run.json exist."""
    sc = reset_sc
    monkeypatch.chdir(tmp_path)
    sc.options = psh.parse_args(["--all", "--date", "20260331"])
    seen = []
    ymd = datetime.datetime.today().strftime("%Y%m%d")
    sc.add_hook("run_finish", {
        "name": "probe", "consumes": [], "produces": [],
        "func": lambda: seen.append(os.path.exists(f"{ymd}-notices.csv")),
    })
    db = ...  # the file's existing temp session/engine pattern
    psh.finish_run(db_session, db_engine, 1, 1, ["site,ok"], {"s": {}}, [])
    assert seen == [False]  # fired exactly once, before any artifact existed
```

NOTE: until Task 3 lands, `add_hook` does not require `consumes`/`produces` — including
them here already is deliberate (they are inert extra dict keys today) so this test does
not need touching in Task 3. `sc.options` construction: `--all` is safe in-process (the
interlock guards subprocess `run_program()` only — existing `test_finish_run.py` tests do
the same; follow them).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/integration/test_finish_run.py::test_run_finish_phase_fires_before_artifacts_are_written tests/integration/test_hooks_phases.py -v`
Expected: the new probe test FAILS with SystemExit ("unknown phase") from `add_hook`;
`test_phases_order_and_content` FAILS on the tuple mismatch.

- [ ] **Step 3: Implement**

`psh/modules.py`: append to `PHASES` (comment included):

```python
    'site_pre_render',
    'run_finish',          # once per run, inside finish_run(), before any artifact is
                           # written -- on completed AND aborted runs (both call finish_run).
                           # Fired with no arguments until I13 introduces RunState
                           # (CAMPAIGN.md section 4); no consumer yet, like site_pre_render
                           # at its introduction.
)
```

`psh/_legacy.py` `finish_run()`: first statement after the docstring (before the
`db_session.close()` try-block):

```python
    # Run-level seam (CAMPAIGN.md section 4): fire before ANY teardown or artifact write so
    # future hooks see the run intact.  No arguments until I13's RunState.
    sc.invoke_hooks("run_finish")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/integration/test_finish_run.py tests/integration/test_abort_run.py tests/integration/test_hooks_phases.py -v`
Expected: ALL PASS (abort-path tests prove the no-consumer invoke is harmless there too).

- [ ] **Step 5: Full fast suite, goldens diff, commit**

Run: `./run-tests --fast --llm` → green; `git diff d46f56d -- tests/e2e/__snapshots__/` → empty.

```bash
git add psh/modules.py psh/_legacy.py tests/integration/test_finish_run.py tests/integration/test_hooks_phases.py
git commit -m "feat(campaign-I4): add the run_finish phase, fired inside finish_run()"
```

---

### Task 3: Required `consumes`/`produces` declarations + full in-repo retrofit

**Files:**
- Modify: `psh/modules.py` (`add_hook` enforcement)
- Modify (retrofit, per SPEC §6 table): `plugin/cloudflare/__init__.py`,
  `plugin/umich/__init__.py`, `check/cloudflare/__init__.py`, `check/dns/__init__.py`,
  `check/pantheon_cdn_change/__init__.py`, `check/umich/__init__.py`
- Modify (test callers): `tests/integration/test_hooks_phases.py`,
  `tests/integration/test_terminus_seam.py`, plus any caller found by
  `grep -rn "add_hook(" tests/ check/ plugin/ psh/ script_context.py`
- Test: `tests/integration/test_hooks_phases.py` (new fatal tests)

**Interfaces:**
- Consumes: Task 1's `add_hook`.
- Produces: every hook dict now carries `consumes: list[str]` and `produces: list[str]`;
  Task 5's validator and `ordered_hooks` index these keys unconditionally.

- [ ] **Step 1: Write the failing tests** (append to `test_hooks_phases.py`)

```python
def test_add_hook_missing_declarations_is_fatal(reset_sc):
    """CAMPAIGN.md section 4 condition 5: no legacy mode -- a hook without consumes/produces
    (or with a non-list / non-str member) must die loudly at registration."""
    sc = reset_sc
    with pytest.raises(SystemExit):
        sc.add_hook("site_pre", {"name": "probe", "func": lambda: None})
    with pytest.raises(SystemExit):
        sc.add_hook("site_pre", {"name": "probe", "func": lambda: None, "consumes": []})
    with pytest.raises(SystemExit):
        sc.add_hook("site_pre", {"name": "probe", "func": lambda: None,
                                 "consumes": "traffic_rows", "produces": []})
    with pytest.raises(SystemExit):
        sc.add_hook("site_pre", {"name": "probe", "func": lambda: None,
                                 "consumes": [42], "produces": []})


def test_add_hook_dotted_event_must_declare_empty(reset_sc):
    """Contract keys are phase-anchored; a dotted event has no phase position, so a non-empty
    declaration is unvalidatable (SPEC D-i4-3)."""
    sc = reset_sc
    with pytest.raises(SystemExit):
        sc.add_hook("setup.custom.event", {"name": "probe", "func": lambda: None,
                                           "consumes": ["traffic_rows"], "produces": []})
    sc.add_hook("setup.custom.event", {"name": "probe", "func": lambda: None,
                                       "consumes": [], "produces": []})  # empty is fine
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/integration/test_hooks_phases.py -v`
Expected: both new tests FAIL (no SystemExit raised — add_hook currently accepts anything).

- [ ] **Step 3: Implement enforcement in `psh/modules.py`**

Replace `add_hook`'s body-tail (`sc.hooks.setdefault...` stays last):

```python
def add_hook(hook_name: str, target: dict) -> None:
    """Register a hook.  `target` MUST carry `name`, `func`, and the data-contract
    declarations `consumes` and `produces` (each a possibly-empty list of contract-key
    names, CLAUDE.md per-phase table; CAMPAIGN.md section 4).  Dotted plugin events must
    declare both empty.  Violations exit loudly here -- nothing enters sc.hooks
    undeclared, which is what lets validate_hooks()/ordered_hooks() index the keys
    unconditionally."""
    import script_context as sc  # noqa: PLC0415 -- call-time import; see the module docstring

    if not _valid_hook_name(hook_name):
        sc.console.print(f'[bold red]ERROR: add_hook: unknown phase "{hook_name}" '
                         f'(known phases: {", ".join(PHASES)}; dotted names are plugin events)')
        sys.exit(1)
    hook_label = escape(str(target.get("name", "<unnamed>")))
    for entry in ("consumes", "produces"):
        value = target.get(entry)
        if not isinstance(value, list) or not all(isinstance(key, str) for key in value):
            sc.console.print(
                f'[bold red]ERROR: add_hook: hook "{hook_label}" for "{escape(hook_name)}" must '
                f'declare "{entry}" as a list of contract-key names ([] when none) -- '
                f'see the per-phase data contract in CLAUDE.md')
            sys.exit(1)
    if '.' in hook_name and (target["consumes"] or target["produces"]):
        sc.console.print(
            f'[bold red]ERROR: add_hook: dotted event "{escape(hook_name)}" hook "{hook_label}" '
            f'must declare empty consumes/produces (contract keys are phase-anchored)')
        sys.exit(1)
    sc.hooks.setdefault(hook_name, []).append(target)
```

Add `from rich.markup import escape` to the module imports (gateway.py precedent).

- [ ] **Step 4: Retrofit every in-repo registration** (SPEC §6 table is normative — but
  **re-verify each `consumes` list against the hook body before writing it**; if a list
  differs from the SPEC table, STOP and report `DONE_WITH_CONCERNS` naming the difference):

`plugin/cloudflare/__init__.py`:
```python
    sc.add_hook('setup', {'name': 'plugin.cloudflare.ips.get_cloudflare_ips',
                          'func': get_cloudflare_ips,
                          'consumes': [], 'produces': []})
    sc.add_hook('setup', {'name': 'plugin.cloudflare.fqdns.update_and_load_proxied_fqdns',
                          'func': update_and_load_proxied_fqdns,
                          'consumes': [], 'produces': []})
```

`plugin/umich/__init__.py`:
```python
    sc.add_hook('setup', {'name': 'plugin.umich.portal.setup_portal_db', 'func': setup_portal_db,
                          'consumes': [], 'produces': []})
```

`check/cloudflare/__init__.py`:
```python
    sc.add_hook('setup', {'name': 'check.cloudflare.egress.check_egress_ip',
                          'func': check_egress_ip,
                          'consumes': [], 'produces': []})
    sc.add_hook('site_post_dns', {'name': 'check.cloudflare.cache.check_cloudflare_cache',
                                  'func': check_cloudflare_cache,
                                  'consumes': ['fqdns_behind_cloudflare'], 'produces': []})
```

`check/dns/__init__.py`:
```python
sc.add_hook('site_post_dns', {'name': 'check.dns.hook.emit_dns_notices',
                              'func': emit_dns_notices,
                              'consumes': ['dns_transient', 'fqdns_not_behind_cloudflare',
                                           'behind_cloudflare_not_proxied',
                                           'proxied_in_multiple_zones', 'not_in_dns'],
                              'produces': []})
```

`check/pantheon_cdn_change/__init__.py`:
```python
sc.add_hook('site_post_dns',
            {'name': 'check.pantheon_cdn_change.hook.check_pantheon_cdn_change',
             'func': check_pantheon_cdn_change,
             'consumes': ['custom_domains'], 'produces': []})
```

`check/umich/__init__.py`:
```python
    sc.add_hook('setup.umich.portal', {'name': 'check.umich.sitelens.setup_sitelens', 'func': setup_sitelens,
                                       'consumes': [], 'produces': []})
    sc.add_hook('site_pre', {'name': 'check.umich.sitelens.check_sitelens_urls', 'func': check_sitelens_urls,
                             'consumes': [], 'produces': []})
    sc.add_hook('site_pre', {'name': 'check.umich.sitelens.check_sitelens_scores', 'func': check_sitelens_scores,
                             'consumes': [], 'produces': []})
    sc.add_hook('site_post_gather', {'name': 'check.umich.cloudflare_cms.check_cloudflare_cms_integrations',
                                     'func': check_cloudflare_cms_integrations,
                                     'consumes': ['fqdns_behind_cloudflare', 'framework',
                                                  'wordpress_plugins', 'drupal_version',
                                                  'drupal_modules'],
                                     'produces': []})
```

Test callers — every remaining `add_hook(` call in `tests/` gains `"consumes": [],
"produces": []` (grep-driven; known: `test_hooks_phases.py`'s dotted/order/unknown-phase
tests, `test_terminus_seam.py:54`). `test_plugin_cloudflare_init.py`'s monkeypatch wrapper
passes `target` through unchanged — no edit needed, but run its file to confirm.

- [ ] **Step 5: Run the full fast suite**

Run: `./run-tests --fast --llm`
Expected: green (any add_hook caller missed → loud SystemExit failure names it — fix and
re-run). `git diff d46f56d -- tests/e2e/__snapshots__/` → empty.

- [ ] **Step 6: Commit**

```bash
git add psh/modules.py plugin/ check/ tests/
git commit -m "feat(campaign-I4): require consumes/produces declarations on every hook"
```

---

### Task 4: Contract registry + stuffer extraction

**Files:**
- Modify: `psh/modules.py` (add `CONTRACT`, `stuff_traffic_contract`, `stuff_gather_contract`)
- Modify: `psh/_legacy.py` (B28/B37 stuffing lines → stuffer calls; extend the
  `from psh.modules import ...` re-import)
- Test: `tests/unit/test_contract_registry.py` (new)

**Interfaces:**
- Consumes: Task 1's module; `sc.SiteContext`; `dns_classify.stuff_dns_contract`/`DnsFacts`.
- Produces: `psh.modules.CONTRACT: dict[str, tuple[str, ...]]` (keys FIRST guaranteed per
  phase — Task 5's validator consumes it);
  `stuff_traffic_contract(site_context, traffic_rows, start_date, end_date) -> None`;
  `stuff_gather_contract(site_context, framework, site_url, wordpress_version, plugins,
  drupal_version, mods) -> None`.

- [ ] **Step 1: Write the failing tests** — `tests/unit/test_contract_registry.py`:

```python
"""The machine-readable per-phase contract (psh.modules.CONTRACT) vs the code that stuffs it.

CONTRACT is authoritative (CAMPAIGN.md section 4); CLAUDE.md's table is its prose rendering.
These tests are registry-driven -- set(keys a stuffer writes) == set(CONTRACT[phase]) -- so
adding a key to one side and not the other goes red."""
import pytest

import dns_classify

pytestmark = pytest.mark.unit

BASE_KEYS = {"site", "notices", "sections", "attachments"}


def _fresh_ctx(reset_sc):
    return reset_sc.SiteContext({"name": "test-site"})


def test_contract_phases_match_engine_phases(psh, reset_sc):
    import psh.modules
    assert tuple(psh.modules.CONTRACT) == psh.modules.PHASES


def test_contract_empty_phases(psh):
    import psh.modules
    for phase in ("setup", "site_pre", "site_pre_render", "run_finish"):
        assert psh.modules.CONTRACT[phase] == ()


def test_traffic_stuffer_writes_exactly_the_registry_keys(psh, reset_sc):
    import psh.modules
    ctx = _fresh_ctx(reset_sc)
    psh.modules.stuff_traffic_contract(ctx, [("row",)], "2026-03-01", "2026-03-31")
    assert set(ctx) - BASE_KEYS == set(psh.modules.CONTRACT["site_post_traffic"])
    assert ctx["traffic_rows"] == [("row",)]
    assert ctx["start_date"] == "2026-03-01"
    assert ctx["end_date"] == "2026-03-31"


def test_gather_stuffer_writes_exactly_the_registry_keys(psh, reset_sc):
    import psh.modules
    ctx = _fresh_ctx(reset_sc)
    psh.modules.stuff_gather_contract(ctx, "wordpress", "https://x/", "6.5",
                                      ["a-plugin"], None, None)
    assert set(ctx) - BASE_KEYS == set(psh.modules.CONTRACT["site_post_gather"])
    assert ctx["wordpress_plugins"] == ["a-plugin"]
    assert ctx["drupal_modules"] is None


def test_gather_stuffer_normalizes_non_list_plugins_and_non_dict_mods(psh, reset_sc):
    """The isinstance guards moved verbatim from main(): a failed gather leaves plugins/mods
    as a non-list/non-dict sentinel and the contract promises None for those."""
    import psh.modules
    ctx = _fresh_ctx(reset_sc)
    psh.modules.stuff_gather_contract(ctx, "drupal8", "", "unknown",
                                      None, "10.2", {"mod": {}})
    assert ctx["wordpress_plugins"] is None
    assert ctx["drupal_modules"] == {"mod": {}}


def test_dns_stuffer_writes_exactly_the_registry_keys(psh, reset_sc):
    import psh.modules
    ctx = _fresh_ctx(reset_sc)
    facts = dns_classify.DnsFacts([], [], "", [], [], [], [], [], [])
    dns_classify.stuff_dns_contract(ctx, {}, facts)
    assert set(ctx) - BASE_KEYS == set(psh.modules.CONTRACT["site_post_dns"])
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/unit/test_contract_registry.py -v`
Expected: FAIL with `AttributeError: module 'psh.modules' has no attribute 'CONTRACT'`.

- [ ] **Step 3: Implement in `psh/modules.py`**

```python
# The machine-readable form of CLAUDE.md's per-phase data-contract table -- THIS is
# authoritative (CAMPAIGN.md section 4); the CLAUDE.md table is its prose rendering.
# Keys FIRST guaranteed at each phase; availability is cumulative (site_pre_render
# guarantees everything above it and adds nothing).  The base SiteContext keys
# (site/notices/sections/attachments) are construction, not contract, and hooks do not
# declare them.  validate_hooks() reads this to resolve consumed keys (SPEC section 4).
CONTRACT: dict[str, tuple[str, ...]] = {
    "setup": (),
    "site_pre": (),
    "site_post_traffic": ("traffic_rows", "start_date", "end_date"),
    "site_post_dns": (
        "domains", "custom_domains", "primary_domain", "main_fqdn",
        "fqdns_behind_cloudflare", "fqdns_not_behind_cloudflare", "not_in_dns",
        "behind_cloudflare_not_proxied", "proxied_in_multiple_zones", "dns_transient",
    ),
    "site_post_gather": (
        "framework", "site_url", "wordpress_version", "drupal_version",
        "wordpress_plugins", "drupal_modules",
    ),
    "site_pre_render": (),
    "run_finish": (),
}


def stuff_traffic_contract(site_context, traffic_rows, start_date, end_date) -> None:
    """Publish the site_post_traffic contract keys (CONTRACT above).  Pure dict writes,
    extracted from main() (campaign I4) so the stuffing is registry-testable -- the
    dns_classify.stuff_dns_contract precedent."""
    site_context["traffic_rows"] = traffic_rows
    site_context["start_date"] = start_date
    site_context["end_date"] = end_date


def stuff_gather_contract(site_context, framework, site_url, wordpress_version,
                          plugins, drupal_version, mods) -> None:
    """Publish the site_post_gather contract keys (CONTRACT above).  NOTE: the *_version
    values are the string "unknown" (not None) when the version fetch failed -- None only
    means "not that framework".  Only the plugins/modules keys use None for "gather
    failed"."""
    site_context["framework"] = framework
    site_context["site_url"] = site_url
    site_context["wordpress_version"] = wordpress_version
    site_context["wordpress_plugins"] = plugins if isinstance(plugins, list) else None
    site_context["drupal_version"] = drupal_version
    # NOTE: drush pm:list returns a DICT keyed by module name (unlike wp plugin list,
    # which returns a list) -- check_drupal_module requires the dict shape.
    site_context["drupal_modules"] = mods if isinstance(mods, dict) else None
```

(The two NOTE comments move verbatim from `main()`.) Exact annotations for the untyped
params: `site_context` is `sc.SiteContext` but typing it would import script_context —
use the same treatment `dns_classify.stuff_dns_contract` uses (untyped param is fine
there because `dns_classify` is ungated; here pyright standard runs — annotate
`site_context: MutableMapping[str, Any]` from `collections.abc`/`typing` if pyright or
ruff demand; otherwise plain names, matching the ANN-ignored ruff config).

- [ ] **Step 4: Wire `main()`** — in `psh/_legacy.py`:

Extend the re-import: `from psh.modules import find_modules, stuff_traffic_contract,
stuff_gather_contract`.

Replace (B28, near line 2305 — keep the surrounding blank lines):
```python
            # Per-phase data contract (see CLAUDE.md "Per-site report pipeline"): the traffic
            # window is guaranteed populated from site_post_traffic onward.
            site_context["traffic_rows"] = results
            site_context["start_date"] = start_date
            site_context["end_date"] = end_date
            sc.invoke_hooks("site_post_traffic", site_context)
```
with:
```python
            # Per-phase data contract (see CLAUDE.md "Per-site report pipeline"): the traffic
            # window is guaranteed populated from site_post_traffic onward.
            stuff_traffic_contract(site_context, results, start_date, end_date)
            sc.invoke_hooks("site_post_traffic", site_context)
```

Replace (B37, near line 3117 — the six assignments AND their two NOTE comments, which
moved into the stuffer):
```python
            # Per-phase data contract (see CLAUDE.md): WP/Drush gather results are guaranteed
            # present from site_post_gather onward.  NOTE: the *_version values are the string
            # "unknown" (not None) when the version fetch failed -- None only when not that
            # framework.  Only the plugins/modules keys use None for "gather failed".
            stuff_gather_contract(site_context, site["framework"], site_url,
                                  wordpress_version, plugins, drupal_version, mods)
            sc.invoke_hooks("site_post_gather", site_context)
```
(Read the current block first and preserve any wording difference in the surviving
lead comment exactly; only the assignment lines and the comments that moved are removed.)

- [ ] **Step 5: Run tests to verify they pass + full suite**

Run: `python -m pytest tests/unit/test_contract_registry.py -v` → ALL PASS.
Run: `./run-tests --fast --llm` → green; `git diff d46f56d -- tests/e2e/__snapshots__/` → empty.

- [ ] **Step 6: Commit**

```bash
git add psh/modules.py psh/_legacy.py tests/unit/test_contract_registry.py
git commit -m "feat(campaign-I4): contract registry + traffic/gather stuffer extraction"
```

---

### Task 5: DAG validation + topological invoke order

**Files:**
- Modify: `psh/modules.py` (`HookDagError` + 4 subclasses, `ordered_hooks`,
  `validate_hooks`; `invoke_hooks` uses `ordered_hooks`)
- Modify: `psh/_legacy.py` (validate call after the check-import loop, ~line 1937)
- Test: `tests/unit/test_hook_dag_validation.py` (new),
  `tests/integration/test_hook_dag.py` (new, permanent)

**Interfaces:**
- Consumes: Task 3's declaration guarantee (`hook["consumes"]`/`hook["produces"]` always
  present); Task 4's `CONTRACT`.
- Produces: `psh.modules.validate_hooks() -> None` (raises), `psh.modules.ordered_hooks
  (hooks_list: list[dict]) -> list[dict]` (pure), exceptions `HookDagError`,
  `UnproducedKeyError`, `DuplicateProducerError`, `HookCycleError`, `LaterPhaseKeyError`.

- [ ] **Step 1: Write the failing unit tests** — `tests/unit/test_hook_dag_validation.py`:

```python
"""Each CAMPAIGN.md section-4 fatal condition demonstrated red (PD#14), plus the
topological invoke order with registration-order tie-breaking."""
import pytest

pytestmark = pytest.mark.unit


def _hook(name, consumes=(), produces=(), fired=None):
    return {"name": name, "consumes": list(consumes), "produces": list(produces),
            "func": (lambda *a, **k: fired.append(name)) if fired is not None else (lambda *a, **k: None)}


def test_condition_1_unproduced_consumed_key_is_fatal(psh, reset_sc):
    import psh.modules as m
    reset_sc.add_hook("site_pre", _hook("a", consumes=["no-such-key"]))
    with pytest.raises(m.UnproducedKeyError, match="no-such-key"):
        m.validate_hooks()


def test_condition_2_two_hook_producers_is_fatal(psh, reset_sc):
    import psh.modules as m
    reset_sc.add_hook("site_pre", _hook("a", produces=["shared"]))
    reset_sc.add_hook("site_pre", _hook("b", produces=["shared"]))
    with pytest.raises(m.DuplicateProducerError, match="shared"):
        m.validate_hooks()


def test_condition_2_hook_producing_a_core_registry_key_is_fatal(psh, reset_sc):
    import psh.modules as m
    reset_sc.add_hook("site_pre", _hook("a", produces=["traffic_rows"]))
    with pytest.raises(m.DuplicateProducerError, match="traffic_rows"):
        m.validate_hooks()


def test_condition_3_same_phase_cycle_is_fatal(psh, reset_sc):
    import psh.modules as m
    reset_sc.add_hook("site_pre", _hook("a", consumes=["x"], produces=["y"]))
    reset_sc.add_hook("site_pre", _hook("b", consumes=["y"], produces=["x"]))
    with pytest.raises(m.HookCycleError):
        m.validate_hooks()


def test_condition_4_key_first_produced_in_a_later_phase_is_fatal(psh, reset_sc):
    import psh.modules as m
    reset_sc.add_hook("site_pre", _hook("a", consumes=["framework"]))  # owned by site_post_gather
    with pytest.raises(m.LaterPhaseKeyError, match="framework"):
        m.validate_hooks()


def test_earlier_phase_key_is_legal(psh, reset_sc):
    """The check.umich.cloudflare_cms shape: consuming a site_post_dns key at site_post_gather."""
    import psh.modules as m
    reset_sc.add_hook("site_post_gather", _hook("a", consumes=["fqdns_behind_cloudflare"]))
    m.validate_hooks()  # must not raise


def test_hook_produced_key_consumed_same_phase_is_legal_and_ordered(psh, reset_sc):
    import psh.modules as m
    fired = []
    reset_sc.add_hook("site_pre", _hook("consumer", consumes=["made"], fired=fired))
    reset_sc.add_hook("site_pre", _hook("producer", produces=["made"], fired=fired))
    m.validate_hooks()  # must not raise
    reset_sc.invoke_hooks("site_pre")
    assert fired == ["producer", "consumer"]  # producer first despite later registration


def test_edgeless_hooks_keep_registration_order(psh, reset_sc):
    import psh.modules as m
    fired = []
    for tag in ("a", "b", "c"):
        reset_sc.add_hook("site_pre", _hook(tag, fired=fired))
    m.validate_hooks()
    reset_sc.invoke_hooks("site_pre")
    assert fired == ["a", "b", "c"]


def test_validate_clean_on_empty_registry(psh, reset_sc):
    import psh.modules as m
    m.validate_hooks()  # a run with no hooks at all is valid
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/unit/test_hook_dag_validation.py -v`
Expected: FAIL with `AttributeError` (`validate_hooks`/error classes don't exist).

- [ ] **Step 3: Implement in `psh/modules.py`**

```python
class HookDagError(Exception):
    """Base for the fatal hook-DAG validation conditions (CAMPAIGN.md section 4).
    main() catches this, prints the message, and exits 1."""


class UnproducedKeyError(HookDagError):
    """Condition 1: a hook consumes a contract key that neither the core registry
    (CONTRACT) nor any hook produces."""


class DuplicateProducerError(HookDagError):
    """Condition 2: two producers of one key (hook+hook, or a hook claiming a key the
    core registry already owns) -- one owner per key, a silent overwrite is a silent
    failure (PD#1)."""


class HookCycleError(HookDagError):
    """Condition 3: a consumes/produces cycle among same-phase hooks."""


class LaterPhaseKeyError(HookDagError):
    """Condition 4: a hook consumes a key first produced in a LATER phase."""


def ordered_hooks(hooks_list: list) -> list:
    """The hooks in invocation order: producers before consumers (Kahn's algorithm),
    registration order breaking ties -- so an edgeless list (every in-repo hook today)
    keeps exactly its registration order.  Pure; raises HookCycleError on a cycle.
    Deliberately re-computed per invoke_hooks call rather than cached at validation
    (SPEC D-i4-6): same inputs give the same order, and tests register hooks without
    running validate_hooks()."""
    producers = {}
    for hook in hooks_list:
        for key in hook["produces"]:
            producers.setdefault(key, hook["name"])
    consumed_from = {
        hook["name"]: {producers[key] for key in hook["consumes"] if key in producers}
        for hook in hooks_list
    }
    ordered = []
    done = set()
    remaining = list(hooks_list)
    while remaining:
        progressed = False
        for hook in list(remaining):
            if consumed_from[hook["name"]] <= done:
                ordered.append(hook)
                done.add(hook["name"])
                remaining.remove(hook)
                progressed = True
        if not progressed:
            names = ", ".join(sorted(h["name"] for h in remaining))
            raise HookCycleError(
                f"consumes/produces cycle among same-phase hooks: {names}")
    return ordered


def validate_hooks() -> None:
    """Validate the whole hook DAG at module-load completion (CAMPAIGN.md section 4
    conditions 1-4; condition 5 is enforced at add_hook time -- nothing enters sc.hooks
    undeclared).  Raises a named HookDagError subclass; main() turns it into a fatal
    exit.  Dotted plugin events carry (enforced-)empty declarations, so only bare
    phases participate."""
    import script_context as sc  # noqa: PLC0415 -- call-time import; see the module docstring

    owner_phase = {}   # key -> (phase index, producer label)
    for index, phase in enumerate(PHASES):
        for key in CONTRACT[phase]:
            owner_phase[key] = (index, "core")
    for phase in PHASES:
        index = PHASES.index(phase)
        for hook in sc.hooks.get(phase, []):
            for key in hook["produces"]:
                if key in owner_phase:
                    raise DuplicateProducerError(
                        f'"{key}" has two producers: {owner_phase[key][1]} and hook '
                        f'"{hook["name"]}" ({phase}) -- one owner per key')
                owner_phase[key] = (index, f'hook "{hook["name"]}"')
    for phase in PHASES:
        index = PHASES.index(phase)
        for hook in sc.hooks.get(phase, []):
            for key in hook["consumes"]:
                if key not in owner_phase:
                    raise UnproducedKeyError(
                        f'hook "{hook["name"]}" ({phase}) consumes "{key}", which nothing '
                        f'produces (neither the core contract nor any hook)')
                if owner_phase[key][0] > index:
                    raise LaterPhaseKeyError(
                        f'hook "{hook["name"]}" ({phase}) consumes "{key}", first produced '
                        f'in the later phase "{PHASES[owner_phase[key][0]]}"')
        ordered_hooks(sc.hooks.get(phase, []))  # condition 3, per phase
```

`invoke_hooks`: change the loop line to
`for hook in ordered_hooks(sc.hooks.get(hook_name, [])):` — for a dotted event the
declarations are enforced empty, so `ordered_hooks` returns registration order (one
uniform path, no special case).

- [ ] **Step 4: Run the unit tests to verify they pass**

Run: `python -m pytest tests/unit/test_hook_dag_validation.py tests/integration/test_hooks_phases.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Write + run the permanent integration test** — `tests/integration/test_hook_dag.py`:

```python
"""Load EVERY real check/ and plugin/ package with everything enabled, then prove the
hook DAG validates -- the permanent 'future changes can never make the DAG impossible'
guarantee (CAMPAIGN.md section 4).  If this test fails after you added a hook, your
declarations (or a duplicate producer) are the cause -- read psh/modules.py."""
import pytest

from tests.helpers.checkload import load_check_package  # adapt to the helper's real API

pytestmark = pytest.mark.integration

EVERYTHING_ENABLED = {
    "UMich": {"enabled": True},
    "Cloudflare": {
        "enabled": True,
        "cachecheck": {"enabled": True, "account_id": "acct", "list_name": "egress"},
    },
}

ALL_PACKAGES = (
    "check/cloudflare", "check/dns", "check/pantheon_cdn_change", "check/umich",
    "plugin/aws", "plugin/cloudflare", "plugin/env", "plugin/umich",
)


def test_all_real_hooks_validate(psh, reset_sc, monkeypatch, request):
    sc = reset_sc
    sc.config = EVERYTHING_ENABLED
    for package in ALL_PACKAGES:
        load_check_package(request, package)   # adapt: whatever loads a package standalone
    import psh.modules
    psh.modules.validate_hooks()               # must not raise
    bare = {phase: [h["name"] for h in sc.hooks.get(phase, [])] for phase in sc.PHASES}
    # Edgeless today: validated order == registration order for every phase.
    for phase, names in bare.items():
        got = [h["name"] for h in psh.modules.ordered_hooks(sc.hooks.get(phase, []))]
        assert got == names
    # The retrofit reached everything: at least the known 11 bare+dotted registrations.
    total = sum(len(v) for v in sc.hooks.values())
    assert total >= 11
```

The loading mechanics MUST reuse `tests/helpers/checkload.py` (or the probe-package
pattern from `test_check_cloudflare_init.py` / `test_plugin_cloudflare_init.py`) — read
those first and follow them; do NOT invent a new loader. If a package needs extra config
to register (read each `__init__.py`), extend `EVERYTHING_ENABLED` — the test's point is
that **every** in-repo registration is present when validation runs. Sitelens setup may
require `[UMich].portal`-shaped config: check `check/umich/__init__.py` (it gates only on
`UMich.enabled` — the deeper config is read at hook run time, not registration).

Run: `python -m pytest tests/integration/test_hook_dag.py -v`
Expected: PASS (if a consumes list in the retrofit was wrong, THIS is where it fails —
report, don't patch the test).

- [ ] **Step 6: Wire `main()`** — in `psh/_legacy.py`, immediately after the check-import
  loop (after line ~1937 `sc.check[check_name] = module`):

```python
    # All modules are loaded; every hook is registered.  Validate the consumes/produces
    # DAG before anything runs (CAMPAIGN.md section 4) -- a bad declaration is a startup
    # fatal, not a mid-run surprise.
    try:
        validate_hooks()
    except HookDagError as e:
        sc.console.print(f"[bold red]ERROR: hook validation failed: {escape(str(e))}")
        sys.exit(1)
```

Extend the re-import: `from psh.modules import (find_modules, stuff_traffic_contract,
stuff_gather_contract, validate_hooks, HookDagError)`. (`escape` is already imported in
`_legacy.py` — verify, else import it.)

- [ ] **Step 7: Full fast suite + goldens diff**

Run: `./run-tests --fast --llm` → green. `git diff d46f56d -- tests/e2e/__snapshots__/` →
empty (the four goldens run the real `main()` through the new validate call — this is the
proof the retrofit declarations validate in production shape).

- [ ] **Step 8: Commit**

```bash
git add psh/modules.py psh/_legacy.py tests/unit/test_hook_dag_validation.py tests/integration/test_hook_dag.py
git commit -m "feat(campaign-I4): validate the hook consumes/produces DAG at startup"
```

---

### Task 6: Un-grandfather `script_context.py` (ratchet, §13)

**Files:**
- Modify: `ruff-broad.toml` (delete the `script_context.py` exclude line + its comment)
- Modify: `script_context.py` (fix the findings)

**Interfaces:** none new — behavior-preserving cleanups only.

- [ ] **Step 1: Delete the exclude line, measure**

Remove `"script_context.py",    # facade; cleaned when I4 moves the hook engine` from
`ruff-broad.toml` `extend-exclude`.

Run: `uvx ruff check --config ruff-broad.toml script_context.py`
Expected findings (measured 2026-07-20 pre-move; re-measure — the engine's departure and
Task 1's re-export import may shift them): `I001` (import block), 2× `SIM401`, 2×
`PLR1714`, possibly `F401`/`RUF100` interactions on the re-export noqa.

- [ ] **Step 2: Fix each finding, behavior-preservingly**

- `I001`: reorder the import block per ruff's fix (`ruff check --config ruff-broad.toml
  --fix script_context.py` is acceptable for I001 only; inspect the diff).
- `SIM401` ×2: in `SiteContext.add_notice` and `add_news_item`, replace
  `order = notice['order'] if 'order' in notice else 'append'` with
  `order = notice.get('order', 'append')` (and the `news_item` twin).
- `PLR1714` ×2: replace `if order == 'prepend' or order == 'first':` with
  `if order in ('prepend', 'first'):` (both sites).
- Anything else ruff reports: fix if mechanical and behavior-identical; otherwise
  `# noqa` with an inline reason and record for the ledger (I3 disposition precedent).
  NO change to `ruff-broad.toml`'s ignore list (that would be a §13 amendment).

- [ ] **Step 3: Verify clean + full suite + goldens**

Run: `uvx ruff check --config ruff-broad.toml script_context.py psh/modules.py` →
`All checks passed!`
Run: `./run-tests --fast --llm` → green (add_notice/add_news_item behavior pinned by
existing notice/news tests + goldens).
Run: `git diff d46f56d -- tests/e2e/__snapshots__/` → empty.

- [ ] **Step 4: Commit**

```bash
git add ruff-broad.toml script_context.py
git commit -m "refactor(campaign-I4): un-grandfather script_context.py from the broad ruff ratchet"
```

---

### Task 7 (controller, at close — not a subagent dispatch): docs, ledger, archive

Per CAMPAIGN.md §7 obligations 6–10 and the I2/I3 closing-commit pattern: CLAUDE.md
updates (engine home, declaration requirement + fatal table pointer, `run_finish`,
registry-authoritative line, obsolete-prose deletion with line-count delta), memory
updates, `LEDGER.md` I4 entry (the seven flagged notes from SPEC §2/§10), SPEC.md
acceptance results pasted, `/code-review`, full `./run-tests`, closing commit including
this folder, `/archive-session`.

## Self-review (done at write time)

- Spec coverage: SPEC §1 items 1–8 map to Tasks 1–6 + Task 7 (docs). D-i4-1…7 each
  land in a named task step. ✔
- Placeholders: the two "adapt to the file's existing pattern" notes in Task 2/Task 5
  are deliberate read-the-file-first instructions with the target files named, not
  unwritten design. ✔
- Type consistency: `ordered_hooks(hooks_list) -> list`, `validate_hooks() -> None`,
  stuffer signatures match between Interfaces blocks and code. ✔

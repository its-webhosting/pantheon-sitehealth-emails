# I8 — `check/pantheon/` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move B19 (frozen), B21's notice half (no-live-env), B38 (upstream updates), and
B41 (PHP EOL, with its I1-carried bug fixes) out of `main()` into the new config-gated
`check/pantheon/` package, publishing the new `envs` contract key at `site_pre`.

**Architecture:** SPEC.md in this directory (D-i8-1…7); CAMPAIGN.md §3.2/§4/§5.
Core keeps the `env:list` fetch + guards and stuffs `envs`; four hooks emit the notices.

**Tech Stack:** Python 3.12, pytest (+syrupy), ruff two-config ratchet, pyright.

## Global Constraints

- Four e2e goldens byte-identical; NO golden/fixture refreshes (Invariants 1, 10).
- Moved notice-literal interiors (`f"""…"""`) move **byte-for-byte** — statement code
  re-indents, but every line *inside* a triple-quoted literal keeps its exact bytes,
  including the no-live-env literal's 12-space interior indentation (Invariant 8;
  `git diff -w` is not acceptable evidence).
- Checks import ONLY `script_context as sc` (Invariant 9); no module-level mutable
  state (§3.4).
- `check/pantheon/` is born gated: `uvx ruff check --config ruff-broad.toml
  check/pantheon/` must be clean at every commit that touches it. Pyright scope
  unchanged (`psh/` minus `_legacy.py`) per SPEC D-i8-7.
- Test-first (`mattpocock-skills:tdd` — NOT superpowers:test-driven-development);
  every named fix shows RED on the old behavior before the fix.
- Notice csv codes unchanged: `frozen`, `no-live-env-but-paid-plan`,
  `updates-info`/`updates-warning`/`updates-alert` (with `,{num},{days}` extra
  fields), `php-eol-warning`, `php-eol-alert`.
- Commit per task, each green (`./run-tests --fast` minimum; full suite at close).
- Current `psh/_legacy.py` line numbers below were verified 2026-07-21 for Task 1/2's
  starting state; Tasks 2–3 shift them. **Locate every edit by the quoted anchor text,
  never by a stale number.**

---

### Task 1: `envs` contract key + stuffer

**Files:**
- Modify: `psh/modules.py` (CONTRACT, PHASES comment, new stuffer)
- Modify: `psh/_legacy.py` (stuff call before the `site_pre` invoke; import line)
- Test: `tests/unit/test_contract_registry.py`

**Interfaces:**
- Produces: `psh.modules.stuff_envs_contract(site_context, envs) -> None`;
  `CONTRACT["site_pre"] == ("envs",)`. Tasks 2/3's hooks declare
  `'consumes': ['envs']` against this.

- [ ] **Step 1: Write the failing tests** — in `tests/unit/test_contract_registry.py`:
  - In `test_contract_empty_phases`, remove `"site_pre"` from the phase tuple (it is
    no longer key-less): `for phase in ("setup", "run_finish"):`.
  - Add:

```python
def test_site_pre_contract_key(psh):
    import psh.modules
    assert psh.modules.CONTRACT["site_pre"] == ("envs",)


def test_envs_stuffer_writes_exactly_the_registry_keys(psh, reset_sc):
    import psh.modules
    ctx = _fresh_ctx(reset_sc)
    envs = {"live": {"initialized": True, "php_version": "8.2"}}
    psh.modules.stuff_envs_contract(ctx, envs)
    assert set(ctx) - BASE_KEYS == set(psh.modules.CONTRACT["site_pre"])
    assert ctx["envs"] is envs
```

- [ ] **Step 2: Run to verify RED**
  `python -m pytest tests/unit/test_contract_registry.py -v` — the two new tests FAIL
  (`CONTRACT["site_pre"]` is `()`; `stuff_envs_contract` undefined).

- [ ] **Step 3: Implement** — in `psh/modules.py`:
  - `CONTRACT` entry: `"site_pre": ("envs",),`
  - `PHASES` tuple `site_pre` comment: change `no per-phase keys guaranteed` to
    `guarantees "envs" (campaign I8)` keeping the timing sentence.
  - Below `stuff_gather_contract`:

```python
def stuff_envs_contract(site_context: MutableMapping[str, Any], envs) -> None:
    """Publish the site_pre contract key (CONTRACT above).  `envs` is the terminus
    env:list JSON dict keyed by environment id; main()'s guards ensure envs["live"]
    exists with an "initialized" key before any site phase fires.  "php_version" is
    NOT guaranteed present (check/pantheon/php_eol.py tolerates its absence)."""
    site_context["envs"] = envs
```

  In `psh/_legacy.py`: extend the existing `from psh.modules import …` line (grep for
  `stuff_traffic_contract` near the top imports) with `stuff_envs_contract`, and at the
  anchor `sc.invoke_hooks("site_pre", site_context)` insert directly above it:

```python
            stuff_envs_contract(site_context, envs)
```

- [ ] **Step 4: Run to verify GREEN**
  `python -m pytest tests/unit/test_contract_registry.py tests/integration/test_hook_dag.py -v` → all PASS.
  Then `./run-tests --fast` → green (goldens untouched — the new key has no consumer yet).
  `uvx ruff check --config ruff-broad.toml psh/modules.py` → clean; pyright gate clean
  (`./run-tests` runs it; or `npx -y pyright` per pyproject scope).

- [ ] **Step 5: Commit**
  `git add -A psh/modules.py psh/_legacy.py tests/unit/test_contract_registry.py && git commit -m "feat(campaign-I8): publish the envs contract key at site_pre"`

---

### Task 2: package skeleton + gating + ratchet + frozen & live-env hooks

**Files:**
- Create: `check/pantheon/__init__.py`, `check/pantheon/frozen.py`,
  `check/pantheon/live_env.py`
- Modify: `psh/_legacy.py` (delete B19 + the initialized-False branch),
  `ruff-broad.toml`, `sample-pantheon-sitehealth-emails.toml`
- Test: `tests/integration/test_check_pantheon_init.py`,
  `tests/integration/test_check_pantheon.py`,
  `tests/integration/test_pantheon_notice_render.py`

**Interfaces:**
- Consumes: Task 1's `envs` contract key (`site_context["envs"]`).
- Produces: `frozen.check_frozen_site(site_context)`,
  `live_env.check_live_env(site_context)`; the `[Check.pantheon].enabled` guard shape
  Task 3 extends.

- [ ] **Step 1: Write the failing tests.**
  `tests/integration/test_check_pantheon_init.py`:

```python
"""check/pantheon registration + [Check.pantheon] gating (campaign I8, SPEC D-i8-6).

Default is ENABLED: relocating code must not silently disable a check that ran
unconditionally before (CAMPAIGN.md section 5)."""
import pytest

from helpers.checkload import load_check_package
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration


def test_registers_hooks_when_config_is_silent(psh, reset_sc, request):
    reset_sc.config = {}
    load_check_package(psh, "pantheon", "pantheon_init_probe", request)
    assert [h["name"] for h in reset_sc.hooks["site_pre"]] == [
        "check.pantheon.frozen.check_frozen_site",
        "check.pantheon.live_env.check_live_env",
    ]


def test_declarations_match_the_spec_table(psh, reset_sc, request):
    reset_sc.config = {"Check": {"pantheon": {"enabled": True}}}
    load_check_package(psh, "pantheon", "pantheon_decl_probe", request)
    hooks = {h["name"]: h for h in reset_sc.hooks["site_pre"]}
    assert hooks["check.pantheon.frozen.check_frozen_site"]["consumes"] == []
    assert hooks["check.pantheon.live_env.check_live_env"]["consumes"] == ["envs"]
    assert all(h["produces"] == [] for h in hooks.values())


def test_disabled_registers_nothing_and_says_so(psh, reset_sc, request, monkeypatch):
    console = recording_console(monkeypatch, reset_sc)
    reset_sc.config = {"Check": {"pantheon": {"enabled": False}}}
    load_check_package(psh, "pantheon", "pantheon_off_probe", request)
    assert not reset_sc.hooks.get("site_pre")
    assert "Skipping check.pantheon" in console.export_text()
```

  `tests/integration/test_check_pantheon.py` (Task 3 appends to this file):

```python
"""check/pantheon hook seams (campaign I8): each module loaded standalone, driven with a
real SiteContext -- the check/pantheon_cdn_change test pattern."""
import pytest

from helpers.checkload import load_check_module
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration

SITE_ID = "9cf2c790-c7b8-4f2f-a6f1-27385b8f958e"
SITE_NAME = "bus-occb"


def _ctx(reset_sc, **site_extra):
    return reset_sc.SiteContext({"name": SITE_NAME, "id": SITE_ID, **site_extra})


@pytest.fixture
def frozen_mod(psh, request):
    return load_check_module(psh, "pantheon", "frozen", "pantheon_frozen_probe", request)


@pytest.fixture
def live_env_mod(psh, request):
    return load_check_module(psh, "pantheon", "live_env", "pantheon_live_probe", request)


def test_frozen_site_gets_the_alert(frozen_mod, reset_sc, monkeypatch):
    console = recording_console(monkeypatch, reset_sc)
    ctx = _ctx(reset_sc, frozen=True)
    frozen_mod.check_frozen_site(ctx)
    assert [n["csv"] for n in ctx["notices"]] == [f"{SITE_NAME},frozen"]
    assert ctx["notices"][0]["type"] == "alert"
    assert "is frozen!" in console.export_text()


def test_unfrozen_site_gets_nothing(frozen_mod, reset_sc):
    ctx = _ctx(reset_sc, frozen=False)
    frozen_mod.check_frozen_site(ctx)
    assert ctx["notices"] == []


def test_uninitialized_live_env_gets_the_alert(live_env_mod, reset_sc, monkeypatch):
    console = recording_console(monkeypatch, reset_sc)
    ctx = _ctx(reset_sc)
    ctx["envs"] = {"live": {"initialized": False}}
    live_env_mod.check_live_env(ctx)
    assert [n["csv"] for n in ctx["notices"]] == [f"{SITE_NAME},no-live-env-but-paid-plan"]
    assert ctx["notices"][0]["type"] == "alert"
    assert "live environment is not initialized" in console.export_text()


def test_initialized_live_env_gets_nothing(live_env_mod, reset_sc):
    ctx = _ctx(reset_sc)
    ctx["envs"] = {"live": {"initialized": True, "php_version": "8.2"}}
    live_env_mod.check_live_env(ctx)
    assert ctx["notices"] == []
```

  `tests/integration/test_pantheon_notice_render.py` (dict-level byte pins; Task 3
  appends the other five variants):

```python
"""Syrupy pins of the check/pantheon notice bodies -- the forward byte-identity guard for
the verbatim move (campaign I8; move-time evidence is the extracted-block diff in the
task report, the I2 precedent)."""
import pytest

from helpers.checkload import load_check_module
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration

SITE = "bus-occb"


def _notice(reset_sc, mod_func, ctx):
    mod_func(ctx)
    assert len(ctx["notices"]) == 1
    return ctx["notices"][0]


def test_frozen_notice_snapshot(psh, reset_sc, request, monkeypatch, snapshot):
    recording_console(monkeypatch, reset_sc)
    mod = load_check_module(psh, "pantheon", "frozen", "pantheon_frozen_snap", request)
    ctx = reset_sc.SiteContext({"name": SITE, "frozen": True})
    n = _notice(reset_sc, mod.check_frozen_site, ctx)
    assert n["message"] == snapshot
    assert n["text"] == snapshot
    assert n["short"] == snapshot


def test_no_live_env_notice_snapshot(psh, reset_sc, request, monkeypatch, snapshot):
    recording_console(monkeypatch, reset_sc)
    mod = load_check_module(psh, "pantheon", "live_env", "pantheon_live_snap", request)
    ctx = reset_sc.SiteContext({"name": SITE})
    ctx["envs"] = {"live": {"initialized": False}}
    n = _notice(reset_sc, mod.check_live_env, ctx)
    assert n["message"] == snapshot
    assert n["text"] == snapshot
    assert n["short"] == snapshot
```

- [ ] **Step 2: RED** — `python -m pytest tests/integration/test_check_pantheon_init.py
  tests/integration/test_check_pantheon.py tests/integration/test_pantheon_notice_render.py -v`
  → all FAIL (`check/pantheon/` does not exist).

- [ ] **Step 3: Create the package.** `check/pantheon/__init__.py`:

```python
"""Generic Pantheon site-health checks (campaign I8, CAMPAIGN.md section 3.2): frozen
site + uninitialized live environment at site_pre; unapplied upstream updates + PHP EOL
at site_post_gather (added in the same increment).  Gated by [Check.pantheon].enabled,
default TRUE -- these checks ran unconditionally before the relocation (section 5)."""

import script_context as sc


if sc.config.get('Check', {}).get('pantheon', {}).get('enabled', True) is not False:
    from . import frozen, live_env
    sc.add_hook('site_pre', {'name': 'check.pantheon.frozen.check_frozen_site',
                             'func': frozen.check_frozen_site,
                             'consumes': [], 'produces': []})
    sc.add_hook('site_pre', {'name': 'check.pantheon.live_env.check_live_env',
                             'func': live_env.check_live_env,
                             'consumes': ['envs'], 'produces': []})
else:
    sc.console.print('[bold yellow] Skipping check.pantheon because it is disabled in the config')
```

  `check/pantheon/frozen.py` — header below, then **cut** (not retype) the whole B19
  block from `psh/_legacy.py` (anchor: `if site["frozen"] is not False:` through the
  `add_notice` call's closing `)`, currently `:1403–1430`), de-indent statements to
  function depth, add `site = site_context["site"]` above it. Every line inside the two
  `f"""` literals keeps its exact bytes (they are column-0):

```python
"""The frozen-site check (campaign I8, BLOCKMAP B19): a paid-plan site should never be
frozen -- Pantheon freezes inactive Sandbox-tier sites."""

import script_context as sc


def check_frozen_site(site_context):
    site = site_context["site"]
    # ... B19 body moved verbatim ...
```

  `check/pantheon/live_env.py` — same procedure for the initialized-False branch
  (anchor: `if envs["live"]["initialized"] is False:` through the `add_notice` closing
  `)`, currently `:1461–1485`); the condition becomes
  `if site_context["envs"]["live"]["initialized"] is False:`. **This literal's interior
  lines are indented ~12 spaces inside the string — keep those bytes exactly.** The
  `"short": f"no live environment"` line drops its `f` (F541, behavior-identical):

```python
"""The live-environment check (campaign I8, BLOCKMAP B21's notice half): a paid plan
whose live environment was never initialized is wasted money.  The env:list fetch and
its fatal guards stay in main() (SPEC D-i8-2)."""

import script_context as sc


def check_live_env(site_context):
    site = site_context["site"]
    # ... initialized-False branch moved verbatim ...
```

  In `psh/_legacy.py`, delete both moved regions (leave the guards `:1449–1460`, the
  `# Metrics for an uninitialized live environment…` comment, and B20 untouched;
  collapse leftover blank runs to 2, the I5 precedent).

- [ ] **Step 4: Ratchet + config.** In `ruff-broad.toml` replace the `"check/",` line with:

```toml
    "check/cloudflare/",           # untouched tenant; cleaned at I14
    "check/dns/",                  # untouched tenant; cleaned at I14
    "check/pantheon_cdn_change/",  # temporary check; deleted or cleaned at I14
    "check/umich/",                # grows at I9/I10/I12; cleaned then
```

  In `sample-pantheon-sitehealth-emails.toml`, after the last `[Pantheon.*]` sub-table
  (grep `plan_sku_to_name`), add:

```toml
[Check.pantheon]
# Generic Pantheon site-health checks: frozen site, uninitialized live environment on
# a paid plan, unapplied upstream updates, PHP end-of-life.  Enabled by default; set
# to false to disable all four.
enabled = true
```

- [ ] **Step 5: GREEN + byte evidence.**
  `python -m pytest tests/integration/test_pantheon_notice_render.py --snapshot-update`
  (new snapshots only), then
  `python -m pytest tests/integration/test_check_pantheon_init.py tests/integration/test_check_pantheon.py tests/integration/test_pantheon_notice_render.py -v` → PASS.
  Paste into the task report a diff of each moved `f"""` interior (old file via
  `git show HEAD:psh/_legacy.py`) proving byte identity.
  `uvx ruff check --config ruff-broad.toml check/pantheon/` → clean.
  `./run-tests --fast` → green, goldens byte-identical.

- [ ] **Step 6: Commit**
  `git add -A check/pantheon tests ruff-broad.toml sample-pantheon-sitehealth-emails.toml psh/_legacy.py && git commit -m "feat(campaign-I8): check/pantheon package with the frozen and live-env checks"`

---

### Task 3: upstream-updates & PHP-EOL hooks (+ the three named fixes)

**Files:**
- Create: `check/pantheon/updates.py`, `check/pantheon/php_eol.py`
- Modify: `check/pantheon/__init__.py`, `psh/_legacy.py` (delete B38, B41, the
  builder def)
- Test: `tests/unit/test_php_eol_notice.py` (repointed),
  `tests/integration/test_check_pantheon.py` (append),
  `tests/integration/test_pantheon_notice_render.py` (append)

**Interfaces:**
- Consumes: `envs` (Task 1); the Task 2 `__init__.py` guard block; `sc.terminus`.
- Produces: `updates.check_upstream_updates(site_context)`,
  `php_eol.build_php_eol_notice(site_name, php_version)`,
  `php_eol.check_php_eol(site_context)`.

- [ ] **Step 1: Document the old behavior (RED evidence for D-i8-4).** Run and paste:

```bash
python -c "import psh._legacy as m; print(m.build_php_eol_notice('s','8.10')['csv'])"
# -> s,php-eol-alert        (the lexicographic bug, live)
python -c "import psh._legacy as m; m.build_php_eol_notice('s', None)"
# -> TypeError              (None < '8.2')
```

- [ ] **Step 2: Repoint + extend the unit tests.** Rewrite
  `tests/unit/test_php_eol_notice.py`: load the builder from its new home, keep every
  existing case with identical expectations (drop the `psh` fixture param), add the new
  cases:

```python
"""build_php_eol_notice unit tests (campaign I1 SPEC F2; builder moved to
check/pantheon/php_eol.py at I8, where SPEC D-i8-4 fixed the version comparison and
None handling, red-first)."""
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

import psh

pytestmark = pytest.mark.unit

_PATH = Path(psh.__file__).resolve().parents[1] / "check" / "pantheon" / "php_eol.py"
build_php_eol_notice = SourceFileLoader(
    "php_eol_for_unit_tests", str(_PATH)).load_module().build_php_eol_notice


@pytest.mark.parametrize("version", ["7.4", "8.1"])
def test_deprecated_versions_warn(version):
    n = build_php_eol_notice("s", version)
    assert n["type"] == "warning"
    assert n["csv"] == "s,php-eol-warning"
    assert version in n["message"] and version in n["text"]


@pytest.mark.parametrize("version,fallback", [("8.0", "8.1"), ("7.0", "7.4")])
def test_older_versions_alert_with_fallback(version, fallback):
    n = build_php_eol_notice("s", version)
    assert n["type"] == "alert"
    assert n["csv"] == "s,php-eol-alert"
    assert f"PHP {fallback}" in n["message"] and f"PHP {fallback}" in n["text"]


@pytest.mark.parametrize("version", ["8.2", "8.3"])
def test_current_versions_need_no_notice(version):
    assert build_php_eol_notice("s", version) is None


def test_warning_and_alert_codes_are_distinct():
    warn = build_php_eol_notice("s", "8.1")["csv"]
    alert = build_php_eol_notice("s", "8.0")["csv"]
    assert warn != alert


@pytest.mark.parametrize("version", ["8.10", "9.0"])
def test_high_versions_are_not_lexicographically_eol(version):
    # RED pre-fix (D-i8-4.1): "8.10" < "8.2" is True as STRINGS -> false alert.
    assert build_php_eol_notice("s", version) is None


def test_missing_php_version_needs_no_notice():
    # RED pre-fix (D-i8-4.2): None < "8.2" raised TypeError (and the old main() call
    # site KeyError'd before the builder was even reached).
    assert build_php_eol_notice("s", None) is None


def test_unparseable_version_needs_no_notice():
    assert build_php_eol_notice("s", "banana") is None   # old behavior, preserved


def test_single_component_version_still_alerts():
    assert build_php_eol_notice("s", "8")["type"] == "alert"   # old behavior, preserved
```

  Append to `tests/integration/test_check_pantheon.py`:

```python
import datetime


def _update(days_ago, now):
    dt = now - datetime.timedelta(days=days_ago)
    return {"datetime": dt.isoformat(), "message": "Update WordPress to 6.6",
            "author": "Pantheon"}


@pytest.fixture
def updates_mod(psh, request):
    return load_check_module(psh, "pantheon", "updates", "pantheon_updates_probe", request)


@pytest.fixture
def php_eol_mod(psh, request):
    return load_check_module(psh, "pantheon", "php_eol", "pantheon_phpeol_probe", request)


def test_no_updates_no_notice(updates_mod, reset_sc, monkeypatch):
    recording_console(monkeypatch, reset_sc)
    monkeypatch.setattr(reset_sc, "terminus", lambda *a: ([], "", False))
    ctx = _ctx(reset_sc)
    updates_mod.check_upstream_updates(ctx)
    assert ctx["notices"] == []


def test_fetches_the_live_environment_of_the_site_id(updates_mod, reset_sc, monkeypatch):
    recording_console(monkeypatch, reset_sc)
    calls = []
    monkeypatch.setattr(reset_sc, "terminus",
                        lambda *a: (calls.append(a), ([], "", False))[1])
    updates_mod.check_upstream_updates(_ctx(reset_sc))
    assert calls == [("upstream:updates:list", f"{SITE_ID}.live")]


@pytest.mark.parametrize("days_ago,code,severity", [
    (4, "updates-info", "info"),
    (20, "updates-warning", "warning"),
    (45, "updates-alert", "alert"),
])
def test_age_tiers(updates_mod, reset_sc, monkeypatch, days_ago, code, severity):
    recording_console(monkeypatch, reset_sc)
    now = datetime.datetime.now(datetime.UTC)
    data = [_update(days_ago, now), _update(2, now)]   # the OLDEST update sets the tier
    monkeypatch.setattr(reset_sc, "terminus", lambda *a: (data, "", False))
    ctx = _ctx(reset_sc)
    updates_mod.check_upstream_updates(ctx)
    assert [n["csv"] for n in ctx["notices"]] == [f"{SITE_NAME},{code},2,{days_ago}"]
    assert ctx["notices"][0]["type"] == severity


def test_single_old_update_short_is_interpolated(updates_mod, reset_sc, monkeypatch):
    # RED on the verbatim-moved body (D-i8-5): the alert branch's singular arm lacked
    # its f-prefix and rendered the literal "{oldest_update_days} days old".
    recording_console(monkeypatch, reset_sc)
    now = datetime.datetime.now(datetime.UTC)
    monkeypatch.setattr(reset_sc, "terminus", lambda *a: ([_update(45, now)], "", False))
    ctx = _ctx(reset_sc)
    updates_mod.check_upstream_updates(ctx)
    assert ctx["notices"][0]["short"] == "needs maintenance: 1 Pantheon update, 45 days old"


def test_unfetchable_updates_prints_error_and_adds_nothing(updates_mod, reset_sc, monkeypatch):
    console = recording_console(monkeypatch, reset_sc)
    monkeypatch.setattr(reset_sc, "terminus", lambda *a: (None, "boom", True))
    ctx = _ctx(reset_sc)
    updates_mod.check_upstream_updates(ctx)
    assert ctx["notices"] == []
    assert "unable to check updates" in console.export_text()


def test_eol_php_adds_the_warning(php_eol_mod, reset_sc):
    ctx = _ctx(reset_sc)
    ctx["envs"] = {"live": {"initialized": True, "php_version": "8.1"}}
    php_eol_mod.check_php_eol(ctx)
    assert [n["csv"] for n in ctx["notices"]] == [f"{SITE_NAME},php-eol-warning"]


def test_current_php_adds_nothing(php_eol_mod, reset_sc):
    ctx = _ctx(reset_sc)
    ctx["envs"] = {"live": {"initialized": True, "php_version": "8.2"}}
    php_eol_mod.check_php_eol(ctx)
    assert ctx["notices"] == []


def test_missing_php_version_adds_nothing_and_does_not_raise(php_eol_mod, reset_sc):
    # RED against the old call-site semantics (D-i8-4.2): envs["live"]["php_version"]
    # was an unguarded KeyError that aborted the whole run as "fatal".
    ctx = _ctx(reset_sc)
    ctx["envs"] = {"live": {"initialized": True}}
    php_eol_mod.check_php_eol(ctx)
    assert ctx["notices"] == []
```

  Append to `tests/integration/test_pantheon_notice_render.py` (frozen time so the
  age-dependent bodies are stable):

```python
import datetime
import types


class _FrozenNow(datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 7, 1, 12, 0, tzinfo=tz)


@pytest.mark.parametrize("iso,variant", [
    ("2026-06-28T00:00:00+00:00", "info"),
    ("2026-06-15T00:00:00+00:00", "warning"),
    ("2026-05-01T00:00:00+00:00", "alert"),
])
def test_updates_notice_snapshots(psh, reset_sc, request, monkeypatch, snapshot, iso, variant):
    recording_console(monkeypatch, reset_sc)
    mod = load_check_module(psh, "pantheon", "updates", f"pantheon_upd_snap_{variant}", request)
    monkeypatch.setattr(mod, "datetime", types.SimpleNamespace(
        datetime=_FrozenNow, UTC=datetime.UTC))
    monkeypatch.setattr(reset_sc, "terminus", lambda *a: (
        [{"datetime": iso, "message": "Update WordPress to 6.6", "author": "Pantheon"}],
        "", False))
    ctx = reset_sc.SiteContext({"name": SITE, "id": "9cf2c790-c7b8-4f2f-a6f1-27385b8f958e"})
    mod.check_upstream_updates(ctx)
    n = _notice(reset_sc, lambda c: None, ctx)
    assert n["message"] == snapshot
    assert n["text"] == snapshot
    assert n["short"] == snapshot


@pytest.mark.parametrize("version,variant", [("8.1", "warning"), ("8.0", "alert")])
def test_php_eol_notice_snapshots(psh, reset_sc, request, snapshot, version, variant):
    mod = load_check_module(psh, "pantheon", "php_eol", f"pantheon_php_snap_{variant}", request)
    n = mod.build_php_eol_notice(SITE, version)
    assert n["message"] == snapshot
    assert n["text"] == snapshot
    assert n["short"] == snapshot
```

  Also update `test_check_pantheon_init.py::test_registers_hooks_when_config_is_silent`
  to additionally assert the `site_post_gather` order (updates BEFORE php_eol,
  D-i8-3), and `test_declarations_match_the_spec_table` to cover
  `check.pantheon.php_eol.check_php_eol` consuming `["envs"]` and
  `check.pantheon.updates.check_upstream_updates` consuming `[]`.

- [ ] **Step 3: RED** — the unit file fails at import (no `check/pantheon/php_eol.py`);
  the appended integration tests fail (no modules; init asserts 2 phases' hooks).

- [ ] **Step 4: Move VERBATIM (no fixes yet).**
  - `check/pantheon/php_eol.py`: header docstring (SPEC D-i8-4 wording) + **cut** the
    `build_php_eol_notice` def from `psh/_legacy.py` unchanged + append:

```python
def check_php_eol(site_context):
    # April 2026 - September 2026:
    # Check to see if a PHP version upgrade is needed
    php_eol_notice = build_php_eol_notice(
        site_context["site"]["name"], site_context["envs"]["live"].get("php_version"))
    if php_eol_notice is not None:
        site_context.add_notice(php_eol_notice)
```

  (No imports at all — the module is pure.) Delete the def AND the B41 call block
  (anchor: the `# April 2026 - September 2026:` comment through
  `site_context.add_notice(php_eol_notice)`) from `psh/_legacy.py`.
  - `check/pantheon/updates.py`: header + **cut** the whole B38 region (anchor:
    `# Check for un-applied site updates:` through the `pprint(updates)` line of the
    `else:` arm — STOP before `if sc.options.verbose:`, which is B39's and stays):

```python
"""The unapplied-upstream-updates check (campaign I8, BLOCKMAP B38): fetches
upstream:updates:list for the live environment itself (the check-specific-fetch case,
CAMPAIGN.md section 3.2) and emits an age-tiered notice with the update table."""

import datetime
from pprint import pprint

import script_contex as sc


def check_upstream_updates(site_context):
    site = site_context["site"]
    live_site = site["id"] + ".live"
    # ... B38 body moved verbatim; the ONE call edit: terminus(...) -> sc.terminus(...) ...
```

    (Fix the deliberate typo above when writing the real file: `import script_context
    as sc`.) De-indent statements; every `f"""` interior line keeps its exact bytes
    (all are column-0 here).
  - `__init__.py`: extend the guard block —
    `from . import frozen, live_env, php_eol, updates` and append the two
    registrations after the existing pair:

```python
    sc.add_hook('site_post_gather', {'name': 'check.pantheon.updates.check_upstream_updates',
                                     'func': updates.check_upstream_updates,
                                     'consumes': [], 'produces': []})
    sc.add_hook('site_post_gather', {'name': 'check.pantheon.php_eol.check_php_eol',
                                     'func': php_eol.check_php_eol,
                                     'consumes': ['envs'], 'produces': []})
```

- [ ] **Step 5: Show the three REDs, then fix.**
  `python -m pytest tests/unit/test_php_eol_notice.py tests/integration/test_check_pantheon.py -v`:
  expect FAILURES on exactly `test_high_versions_are_not_lexicographically_eol` (both
  params), `test_missing_php_version_needs_no_notice` (builder TypeError),
  `test_single_old_update_short_is_interpolated` (literal braces) — paste the output.
  Then apply the fixes:
  - In `build_php_eol_notice`, replace `if php_version < "8.2":` with:

```python
    try:
        parsed = tuple(int(part) for part in php_version.split("."))
    except (AttributeError, ValueError):
        return None
    if parsed < (8, 2):
```

  - In `updates.py`, add the missing `f` to the alert branch's
    `else "needs maintenance: 1 Pantheon update, {oldest_update_days} days old"`.

- [ ] **Step 6: GREEN.**
  `python -m pytest tests/integration/test_pantheon_notice_render.py --snapshot-update`,
  then the three test files → all PASS. Byte-diff evidence for the moved B38/B41
  literal interiors and the untouched builder dicts pasted in the task report
  (`git show` the pre-task file). `uvx ruff check --config ruff-broad.toml
  check/pantheon/` → clean (expected dispositions per SPEC §5: `PLR2004` noqa on the
  `<= 7`/`<= 30` thresholds, possible `C901`/`PLR0915` noqa on
  `check_upstream_updates`, `T203` noqa on the `pprint` diagnostic — confirm against
  real output, correct SPEC §5's table in the report if reality differs).
  `./run-tests --fast` → green, goldens byte-identical
  (`git diff -- tests/e2e/__snapshots__/` empty). Verify orphan imports in
  `psh/_legacy.py`: `pprint`/`datetime`/`escape` all have surviving users
  (grep; remove ONLY what this change orphaned).

- [ ] **Step 7: Commit**
  `git add -A check/pantheon tests psh/_legacy.py && git commit -m "feat(campaign-I8): move the upstream-updates and PHP-EOL checks into check/pantheon"`

---

### Task 4: docs + ledger + close

**Files:**
- Modify: `CLAUDE.md`, `development/2026-07-17-modularization-campaign/LEDGER.md`,
  `/home/node/.claude/projects/-workspace/memory/modularization-campaign.md`,
  `development/2026-07-21-mod-I8-check-pantheon/SPEC.md` (§9 acceptance)

- [ ] **Step 1: CLAUDE.md** — (a) contract table `site_pre` row: `envs` (dict — the
  `terminus env:list` JSON keyed by environment id with fields `id, created, domain,
  connection_mode, locked, initialized, php_version, php_runtime_generation`; `live` +
  its `initialized` key guaranteed by `main()`'s guards; `php_version` NOT guaranteed),
  keeping the timing note; (b) `find_modules` package list gains `check.pantheon`;
  (c) a `check/pantheon/` sentence in the Plugin/check section (four checks, phases,
  `[Check.pantheon]` default-true gate); (d) the still-hardcoded-U-M list gains the
  frozen/no-live-env/updates bodies now in `check/pantheon/`; (e) Testing section:
  ruff-broad exclude list wording (enumerated check packages) + the new test files
  listed with the DNS/cdn-change suites; (f) key-flags/`--only-warn` text needs no
  change (verify).
- [ ] **Step 2: Ledger entry** per §12 template (moved blocks; D-i8-3 ordering note;
  D-i8-5 discovered-task fix; D-i8-7 pyright decision; contract/config additions
  `envs` + `[Check.pantheon]`; discovered tasks with dispositions).
- [ ] **Step 3: Memory** — update the campaign memory file's progress line (I8 done,
  first `[Check.*]` section exists).
- [ ] **Step 4: Full close** — `/code-review` (per campaign flow), then full
  `./run-tests` (live tier if credentials present), paste results into SPEC §9.
- [ ] **Step 5: Commit** — closing docs commit includes this dev folder:
  `git add -A CLAUDE.md development /home/node/.claude/projects/-workspace/memory && git commit -m "docs(campaign-I8): close the check/pantheon increment"`

---

## Self-Review (done at write time)

- Spec coverage: D-i8-1/3 → Tasks 2–3 (registration order asserted); D-i8-2 → Task 1;
  D-i8-4 → Task 3 steps 1/2/5; D-i8-5 → Task 3 steps 2/5; D-i8-6 → Task 2 (init tests
  + sample toml); D-i8-7 → Task 2 step 4; SPEC §7 test list → Tasks 1–3; SPEC §8
  acceptance → Task 4.
- Types/names consistent: `check_frozen_site`/`check_live_env`/
  `check_upstream_updates`/`check_php_eol`/`build_php_eol_notice`/
  `stuff_envs_contract` used identically across tasks.
- Known judgment points left to the implementer WITH bounds: exact noqa set (must match
  real ruff output, report corrections), blank-line collapse in `_legacy.py`, sample-
  toml placement (after the last `[Pantheon.*]` table).

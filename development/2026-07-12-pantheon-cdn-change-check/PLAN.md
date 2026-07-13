# Pantheon CDN Change Check — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Warn each site owner, once per site, when any of the site's Pantheon **live** custom
domains still reaches a `*.pantheonsite.io` name through a CNAME record — in public DNS or in
U-M Cloudflare — and tell them the exact A/AAAA records Pantheon requires instead.

**Architecture:** A new self-registering check package `check/pantheon_cdn_change/` with one
hook at the `site_post_dns` phase. **Detection** walks each custom domain's CNAME chain through
the existing `dns_classify.resolve` seam (source ①, public DNS) and through the Cloudflare
`origins` already loaded from `fqdns.json` by the `plugin.cloudflare` setup hook (source ②).
**The replacement addresses come from Pantheon** — one lazy `terminus domain:dns <site>.live`
per *affected* site — never from resolving the legacy target ourselves (SPEC §4.1: that target
can belong to a different Pantheon site). One `info` notice per site, containing a table.

**Tech Stack:** Python 3, dnspython (only via `dns_classify.resolve`), terminus (only via the
existing `terminus()` wrapper), rich, pytest + syrupy.

**Read first:** `development/2026-07-12-pantheon-cdn-change-check/SPEC.md`. It is the source of
truth for copy, gates, and failure modes F1–F13, all referenced below. This plan incorporates
two rounds of adversarial review (2026-07-12).

**Note on style:** each task below is written test-first because the seams already exist and it
is cheap here. That is a convenience, not a mandate — this project's convention is "tests follow
the change, in the same commit" (CLAUDE.md). What is non-negotiable is that the tests and the
code land **together**.

## Global Constraints

- **Package name** is `check/pantheon_cdn_change` — underscores (it is imported as a Python
  package by `find_modules()`).
- **All DNS resolution MUST go through `dns_classify.resolve`**; all Pantheon calls MUST go
  through `sc.terminus`. New code NEVER calls `dns.resolver` or `subprocess` directly.
- **The addresses shown to an owner MUST come from `terminus domain:dns`.** Resolving a
  `*.pantheonsite.io` name to get addresses is FORBIDDEN (SPEC §4.1) — a stale target belongs to
  a *different Pantheon site*, and we would email its IP addresses to the wrong owner.
- **NEVER** `except Exception` or bare `except`. The exceptions caught anywhere in this feature
  are exactly and exhaustively: `dns.resolver.NoAnswer`, `dns.resolver.NXDOMAIN`,
  `dns.resolver.NoNameservers`, `dns.resolver.Timeout`, and the new
  `dns_classify.MalformedNameError` (Task 2) — which is where `dns.exception.SyntaxError` and
  `dns.name.NameTooLong` are converted, inside the seam, once, so no caller can forget them.
  `terminus()` reports failure by return value (`fatal`), not by exception.
- **Escaping, at every boundary:** `html.escape` for HTML text nodes; `rich.markup.escape` for
  console strings that embed a remotely-derived name — **including the ones embedded inside an
  exception message**. The CSV boundary has NO escaping, which is why domain ids are validated
  against `sc.fqdn_re` before they can reach it (F13).
- **Terminology, verbatim:** `legacy Pantheon GCDN (Fastly)` / `new Pantheon GCDN Beta
  (Pantheon Cloudflare)` (may shorten to `legacy GCDN` / `new GCDN Beta` after first use);
  `U-M Cloudflare` when `sc.umich_enabled()`, else `our (non-Pantheon) Cloudflare`.
- **Notice contract:** exactly ONE notice per site; ONE row per affected FQDN; `type` `info`;
  `csv` = `"{site},pantheon-cdn-change,{fqdn1},{fqdn2}…"`; `short` = `Pantheon CDN change:
  replace CNAME records`; the notice supplies its own `text`.
- **The notice explains nothing beyond the required change** — no Orange-to-Orange, no
  Pantheon process, no Pantheon-versus-our-Cloudflare discussion.
- **Console assertions in tests** use the recording-Console pattern
  (`tests/integration/test_plugin_cloudflare_fqdns.py:73-75`), NOT `capsys`: rich wraps at
  width 80 on a non-tty, so substring assertions on `capsys` output are one word away from
  flaking.
- **Tests are load-bearing.** A golden or snapshot is NEVER regenerated to make a failing test
  pass. If output changes, read the diff and justify it in the commit message first.
- **The three pre-existing e2e goldens MUST stay byte-identical.** Task 11 adds a fourth.

---

### Task 1: Shared test helpers

**Files:**
- Create: `tests/helpers/__init__.py`, `tests/helpers/dnsfake.py`, `tests/helpers/checkload.py`

**Interfaces:**
- Produces (used by Tasks 5–11): `dnsfake.FakeCname`, `dnsfake.FakeAddress`,
  `dnsfake.make_resolver(zone, calls=None)`, `dnsfake.patch_resolve(monkeypatch, zone,
  calls=None)`, `dnsfake.recording_console(monkeypatch, sc)`;
  `checkload.load_check_package(psh, package, probe, request)`,
  `checkload.load_check_module(psh, package, module, probe, request)`.

`tests/` is already on `sys.path` (e2e tests do `from conftest import …`; there is no
`tests/__init__.py`), so these import as `from helpers.dnsfake import …`. `helpers/__init__.py`
is not collected by pytest (`python_files = test_*.py`).

**Scope limit (deliberate):** these helpers serve the **new** test files. The existing
`check/dns` / `check/cloudflare` / `test_dns_classify` suites keep their own fixtures — porting
them is an unrelated mechanical refactor that would inflate this diff and put working tests at
risk. `tests/helpers/` is where they go when someone next touches them. SPEC §12 says the same;
do not let the two drift.

- [ ] **Step 1: Create `tests/helpers/__init__.py`**

```python
"""Shared test helpers (fake DNS resolver, recording console, standalone check loader)."""
```

- [ ] **Step 2: Create `tests/helpers/dnsfake.py`**

```python
"""The offline DNS seam used by the new DNS-touching tests, plus a capturable console.

dns_classify.resolve is the ONE monkeypatchable DNS seam (CLAUDE.md); patching it here keeps
the offline tier off the network.  A zone maps (name, rrtype) -> a list of values, or an
exception INSTANCE to raise.  An absent key raises NoAnswer -- the definitive "no such record"
answer, which is what the healthy path looks like.
"""
import io

import dns.resolver
from rich.console import Console


class FakeCname:
    def __init__(self, target):
        self.target = target


class FakeAddress:
    def __init__(self, address):
        self.address = address


def make_resolver(zone, calls=None):
    """Build a stand-in for dns_classify.resolve over `zone`.

    `calls`, if given, records every (name, rrtype) looked up -- so a test can assert an IP
    literal was never resolved, or that a clean site issued no lookups at all.
    """
    def _resolve(name, rrtype):
        key = (str(name).rstrip(".").lower(), rrtype)
        if calls is not None:
            calls.append(key)
        value = zone.get(key)
        if value is None:
            raise dns.resolver.NoAnswer
        if isinstance(value, Exception):
            raise value
        if rrtype == "CNAME":
            return [FakeCname(v) for v in value]
        return [FakeAddress(v) for v in value]
    return _resolve


def patch_resolve(monkeypatch, zone, calls=None):
    """Point dns_classify.resolve at `zone` for the duration of one test."""
    import dns_classify
    monkeypatch.setattr(dns_classify, "resolve", make_resolver(zone, calls))


def recording_console(monkeypatch, sc):
    """Replace sc.console with a wide recording Console; read it back with export_text().

    NOT capsys: rich wraps at width 80 on a non-tty, so a substring assertion on capsys output
    breaks as soon as a message grows and the wrap lands mid-phrase.  width=200 + record=True is
    the pattern the repo already uses (tests/integration/test_plugin_cloudflare_fqdns.py:73-75).
    """
    console = Console(file=io.StringIO(), record=True, width=200)
    monkeypatch.setattr(sc, "console", console)
    return console
```

- [ ] **Step 3: Create `tests/helpers/checkload.py`**

```python
"""Load a check/ package (or one module of it) standalone, without importing the dash-named
main script.

A check module that uses relative imports (`from . import chain`) cannot be loaded with a bare
SourceFileLoader: Python needs a parent package with a __path__ first.  These helpers register a
probe package in sys.modules, then load under it -- the pattern established by
tests/integration/test_check_cloudflare_init.py.
"""
import importlib.util
import sys
from pathlib import Path


def _package_dir(psh, package):
    return Path(psh.__file__).parent / "check" / package


def _purge(probe):
    """Remove the probe package AND every submodule the import machinery created under it.

    monkeypatch.delitem(..., raising=False) on a key that does not exist yet records NO undo
    entry -- so submodules created later by `from . import chain` would survive teardown and be
    "restored" into the next test under a parent that no longer exists.  Purge by prefix instead
    of guessing a submodule list.  (This is the same class of bug as the reset_sc escape_url leak
    already recorded in this repo.)
    """
    for name in [m for m in sys.modules if m == probe or m.startswith(probe + ".")]:
        del sys.modules[name]


def load_check_package(psh, package, probe, request):
    """Execute check/<package>/__init__.py as `probe` -- i.e. RUN its hook registration."""
    pkg_dir = _package_dir(psh, package)
    _purge(probe)
    request.addfinalizer(lambda: _purge(probe))
    spec = importlib.util.spec_from_file_location(
        probe, str(pkg_dir / "__init__.py"), submodule_search_locations=[str(pkg_dir)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[probe] = module
    spec.loader.exec_module(module)
    return module


def load_check_module(psh, package, module, probe, request):
    """Load ONE module out of check/<package>/ WITHOUT running the package __init__.py (so no
    hooks are registered).  Relative imports inside it resolve against the real directory: a
    package shell with __path__ set (and NOT exec_module'd) is enough for `from . import chain,
    pantheon` and `from .model import Finding`.
    """
    pkg_dir = _package_dir(psh, package)
    _purge(probe)
    request.addfinalizer(lambda: _purge(probe))
    pkg_spec = importlib.util.spec_from_file_location(
        probe, str(pkg_dir / "__init__.py"), submodule_search_locations=[str(pkg_dir)])
    pkg = importlib.util.module_from_spec(pkg_spec)
    pkg.__path__ = [str(pkg_dir)]          # a package shell: __path__ WITHOUT exec_module
    sys.modules[probe] = pkg
    spec = importlib.util.spec_from_file_location(
        f"{probe}.{module}", str(pkg_dir / f"{module}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"{probe}.{module}"] = mod
    spec.loader.exec_module(mod)
    return mod
```

**Both loaders take `request` (the pytest fixture), not `monkeypatch`** — teardown is an explicit
finalizer, because `monkeypatch` cannot undo a `sys.modules` entry it never saw created. Every
test fixture below therefore reads `(psh, reset_sc, request, monkeypatch)`.

- [ ] **Step 4: Confirm the suite is green before building on it**

Run: `./run-tests --fast`
Expected: PASS (nothing has changed yet — this is the baseline).

- [ ] **Step 5: Commit**

```bash
git add tests/helpers/
git commit -m "test: shared fake-DNS resolver, recording console, and check-package loader"
```

---

### Task 2: Core fix — name the malformed-name failure (F10)

**This is a live bug in core today, not new work.** `fqdn_re`
(`pantheon-sitehealth-emails:89`) matches `a..b`; `dns.resolver.resolve("a..b", "CNAME")` raises
`dns.name.EmptyLabel`, which derives from `dns.exception.SyntaxError` — a class no
`dns.resolver.*` except clause catches. The per-site loop has no `try`/`except`, so one
malformed Pantheon domain id **aborts an entire `--all` run**. Verified 2026-07-12:

```
dns.resolver.resolve("a..b", "CNAME")            -> dns.name.EmptyLabel    (dns.exception.SyntaxError)
dns.resolver.resolve("x"*70 + ".example.org",…)  -> dns.name.LabelTooLong  (dns.exception.SyntaxError)
dns.name.NameTooLong                             -> dns.exception.FormError  -- catch BOTH bases
```

**Files:**
- Modify: `dns_classify.py`
- Test: `tests/unit/test_dns_classify.py` (existing file — append)

**Interfaces:**
- Produces (used by Tasks 5, 7): `dns_classify.MalformedNameError`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_dns_classify.py` (it already imports `pytest`; add `import re` if
absent):

```python
def test_resolve_converts_a_malformed_name_into_a_named_exception(psh, reset_sc):
    # F10: dns.name.EmptyLabel derives from dns.exception.SyntaxError, which no dns.resolver.*
    # except clause catches -- unconverted, it aborts the whole run from inside the per-site loop.
    import dns_classify
    with pytest.raises(dns_classify.MalformedNameError):
        dns_classify.resolve("a..b", "CNAME")
    with pytest.raises(dns_classify.MalformedNameError):
        dns_classify.resolve("x" * 70 + ".example.org", "A")


def test_classify_hostname_dns_survives_a_malformed_name(psh, reset_sc, monkeypatch):
    # The caller must NOT see the exception: a bad domain id skips that host, it does not kill
    # the run.  A name that cannot exist in DNS is definitively unresolvable -> (0, 0, False),
    # which the caller aggregates into the existing not_in_dns alert (whose remedy -- "remove
    # these domains from the Pantheon live environment, or add them to DNS" -- is correct here).
    import dns_classify

    def boom(name, rrtype):
        raise dns_classify.MalformedNameError(f"{name}: EmptyLabel")

    monkeypatch.setattr(dns_classify, "resolve", boom)
    assert dns_classify.classify_hostname_dns("a..b", False, [], []) == (0, 0, False)


def test_malformed_domain_id_does_not_abort_classify_domains(psh, reset_sc, monkeypatch):
    # End of the shadow path: a malformed id in a real domain:list must not raise out of
    # classify_domains (which runs inside the per-site loop, which has no try/except).
    import re

    import dns_classify

    def boom(name, rrtype):
        raise dns_classify.MalformedNameError(f"{name}: EmptyLabel")

    monkeypatch.setattr(dns_classify, "resolve", boom)
    domains = {"a..b": {"id": "a..b", "type": "custom", "primary": True}}
    facts = dns_classify.classify_domains(
        domains, False, [], [], {}, {}, re.compile(r"^_?[a-z0-9-]+\.[a-z0-9.-]+$", re.I))
    assert facts.not_in_dns == ["a..b"]      # definitive: it cannot be in DNS
    assert facts.dns_transient == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./run-tests --fast tests/unit/test_dns_classify.py`
Expected: FAIL — `AttributeError: module 'dns_classify' has no attribute 'MalformedNameError'`.

- [ ] **Step 3: Implement in `dns_classify.py`**

Add the imports (next to `import dns.resolver`) and the exception:

```python
import dns.exception
import dns.name


class MalformedNameError(Exception):
    """`hostname` is not a syntactically valid DNS name.

    dnspython raises dns.name.EmptyLabel / LabelTooLong / BadEscape (all dns.exception.
    SyntaxError) and dns.name.NameTooLong (a dns.exception.FormError) for these.  None derive
    from dns.resolver.*, so no resolver-exception handler catches them -- and the per-site loop
    in the main script has no try/except, so an escaped one aborts the entire run (a single
    malformed Pantheon domain id would take down an --all run).  resolve() converts them here,
    ONCE, at the single DNS seam, so no caller can forget them.
    """
```

Wrap the seam:

```python
def resolve(hostname: str, rrtype: str):
    """The one seam over dns.resolver.resolve; tests monkeypatch dns_classify.resolve.

    Raises MalformedNameError for a syntactically invalid name (see that class).  Every other
    dnspython exception (NoAnswer/NXDOMAIN/NoNameservers/Timeout) propagates unchanged to the
    caller, which knows what each one means.
    """
    try:
        return dns.resolver.resolve(hostname, rrtype)
    except (dns.exception.SyntaxError, dns.name.NameTooLong) as e:
        raise MalformedNameError(f"{hostname}: {type(e).__name__}") from e
```

Catch it in `classify_hostname_dns`, inside the `for rrtype, nets in (…)` loop, alongside the
existing handlers. It returns immediately — if the *name* is malformed the second rrtype lookup
fails identically, and one ATTENTION line is enough. **`rich_escape` the exception too**: `e`'s
message embeds the raw hostname, so escaping only `hostname` and then interpolating `e` would
put the unescaped name straight back into a rich-markup string:

```python
        except MalformedNameError as e:
            sc.console.print(
                f":exclamation: [bold red] ATTENTION: {rich_escape(str(hostname))} is not a "
                f"valid DNS name ({rich_escape(str(e))}); it cannot be in DNS",
                style="red")
            return 0, 0, False       # definitive -- the caller aggregates this into not_in_dns
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./run-tests --fast tests/unit/test_dns_classify.py tests/integration/test_check_dns.py`
Expected: all PASS (new tests green, no regression in the existing DNS suite).

- [ ] **Step 5: Commit**

```bash
git add dns_classify.py tests/unit/test_dns_classify.py
git commit -m "fix(dns): name the malformed-hostname failure so a bad domain id cannot abort a run

dns.name.EmptyLabel/LabelTooLong/NameTooLong derive from dns.exception, not
dns.resolver, so nothing caught them; the per-site loop has no try/except, so a
single malformed Pantheon domain id aborted the whole --all run.  resolve() now
converts them to a named MalformedNameError at the one DNS seam."
```

---

### Task 3: One better sentence on the `fqdns.json` staleness warning (F12)

Source ② answers from `fqdns.json`, which a **single-site run does not refresh**
(`decide_fqdns_update`, `plugin/cloudflare/fqdns.py:66`, only refreshes a stale file when
`multi_site`). The consequence — a newly-proxied FQDN missed, or an already-fixed one still
nagged — needs to be visible.

**It already is.** `plugin/cloudflare/fqdns.py:219-223` warns exactly when the file is stale AND
the run will consume it. And a *missing* file on a consuming run is auto-refreshed
(`decide_fqdns_update:64`), so "fqdns.json is absent" is unreachable from a site phase.

So this task is one sentence, not a subsystem. An earlier draft of this plan added a
`plugin_context` freshness contract, a module-level `_fqdns_warned` flag in the check, and seven
tests — all of it to re-print a warning that exists, plus one branch that can never run. It was
cut in review. **Do not reintroduce it.**

**Files:**
- Modify: `plugin/cloudflare/fqdns.py` (the staleness message; the stale header comment)
- Test: `tests/integration/test_plugin_cloudflare_fqdns.py` (existing staleness test — update
  the asserted message)

- [ ] **Step 1: Update the staleness warning**

At `plugin/cloudflare/fqdns.py:219-223`, replace the message:

```python
        if not does_not_consume and exists and age_seconds > STALE_SECONDS:
            sc.console.print(
                f":exclamation: [bold red] ATTENTION: {FQDNS_FILE} is more than a day old; "
                "Cloudflare-side CNAME checks may be answering from stale data -- run "
                "--update-cloudflare-fqdns for current data"
            )
```

- [ ] **Step 2: Fix the now-false header comment (`plugin/cloudflare/fqdns.py:17-20`)**

It currently claims the origins are unread. Replace with:

```python
# `fqdns.json` maps every Cloudflare-*proxied* website FQDN to the zone it lives in and its DNS
# origins:  { "<fqdn>": { "zone_id": "<uuid>", "origins": [ "<ip-or-cname>", ... ] }, ... }
# The per-site loop consumes the KEYS (a membership test: "is this hostname proxied?"), and
# check/pantheon_cdn_change consumes the ORIGINS (to find CNAMEs to the legacy Pantheon GCDN --
# invisible in public DNS for a proxied FQDN).  zone_id is stored but not read yet.
```

- [ ] **Step 3: Update the existing test's assertion**

`tests/integration/test_plugin_cloudflare_fqdns.py` already asserts on this message (e.g.
`assert "more than a day old" not in sc.console.export_text()` at `:307`). That substring still
holds, so no test breaks — but add one positive assertion that the new guidance is present:

```python
def test_stale_warning_names_the_consequence(fqdns, psh, monkeypatch, tmp_path):
    # A single-site run does NOT refresh a stale fqdns.json, so the Cloudflare half of the
    # CDN-change check may answer from stale data.  The operator must be told what to do.
    module, sc, _cf = fqdns
    monkeypatch.chdir(tmp_path)
    (tmp_path / "fqdns.json").write_text(
        json.dumps({"x.edu": {"zone_id": "z", "origins": ["live-x.pantheonsite.io"]}}))
    stale = time.time() - 2 * 24 * 3600
    os.utime(tmp_path / "fqdns.json", (stale, stale))
    client = _client_with_one_fqdn()
    sc.config = {"Cloudflare": {"enabled": True}}
    sc.plugin_context = {"plugin.cloudflare": {"get_client": lambda: client}}
    sc.options = psh.parse_args(["its-wws-test1"])          # single site -> no refresh

    module.update_and_load_proxied_fqdns()

    out = sc.console.export_text()
    assert client.calls["accounts"] == 0                    # confirms: it did NOT refresh
    assert "more than a day old" in out
    assert "--update-cloudflare-fqdns" in out
```

- [ ] **Step 4: Run the tests**

Run: `./run-tests --fast tests/integration/test_plugin_cloudflare_fqdns.py tests/unit/test_fqdns_decision.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add plugin/cloudflare/fqdns.py tests/integration/test_plugin_cloudflare_fqdns.py
git commit -m "feat(cloudflare): stale-fqdns warning names the consequence for CNAME checks"
```

---



### Task 4: Expose `sc.terminus` and `sc.fqdn_re` to check packages

Check modules cannot import the dash-named main script; CLAUDE.md's documented mechanism is the
`sc`-exposure block ("extend that block for new ones"). This check needs `terminus` (for
`domain:dns`, SPEC §4.1) and `fqdn_re` (to validate domain ids before they reach the CSV, F13).

**Files:**
- Modify: `pantheon-sitehealth-emails:1194-1198`
- Test: `tests/integration/test_terminus_contract.py` (existing file — append)

**Interfaces:**
- Produces (used by Tasks 6, 7): `sc.terminus`, `sc.fqdn_re`.

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/test_terminus_contract.py`:

```python
def test_check_helpers_are_exposed_on_sc(psh, reset_sc):
    # Check packages cannot import the dash-named script; these are the documented seam
    # (CLAUDE.md).  check/pantheon_cdn_change calls sc.terminus("domain:dns", ...) and validates
    # domain ids with sc.fqdn_re before they reach -notices.csv (which has no escaping).
    assert reset_sc.terminus is psh.terminus
    assert reset_sc.fqdn_re is psh.fqdn_re
    assert reset_sc.fqdn_re.match("occb.bus.umich.edu")
    assert not reset_sc.fqdn_re.match("has,comma.example.org")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./run-tests --fast tests/integration/test_terminus_contract.py`
Expected: FAIL — `AttributeError: module 'script_context' has no attribute 'terminus'`.

- [ ] **Step 3: Implement**

In `pantheon-sitehealth-emails`, extend the existing block (currently lines 1194–1198):

```python
sc.escape_url = escape_url
sc.check_wordpress_plugin = check_wordpress_plugin
sc.check_drupal_module = check_drupal_module
sc.umich_enabled = umich_enabled
sc.cloudflare_enabled = cloudflare_enabled
sc.terminus = terminus      # check packages: Pantheon calls (e.g. domain:dns) go through this
sc.fqdn_re = fqdn_re        # check packages: validate remote domain ids with the SAME regex
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./run-tests --fast tests/integration/test_terminus_contract.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pantheon-sitehealth-emails tests/integration/test_terminus_contract.py
git commit -m "feat: expose sc.terminus and sc.fqdn_re to check packages"
```

---

### Task 5: `model.py` + `chain.py` — the CNAME-chain walker (DETECTION only)

**Files:**
- Create: `check/pantheon_cdn_change/__init__.py` (docstring only for now — Task 9 replaces it
  with the real registration. It MUST be non-empty: `find_modules()` skips empty `__init__.py`
  files, and a docstring-only file registers no hook, so nothing runs yet.)
- Create: `check/pantheon_cdn_change/model.py`, `check/pantheon_cdn_change/chain.py`
- Test: `tests/unit/test_pantheon_cdn_change_chain.py`

**Interfaces:**
- Consumes: `dns_classify.resolve` + `dns_classify.MalformedNameError` (Task 2), `sc`,
  `helpers.dnsfake` / `helpers.checkload` (Task 1).
- Produces (used by Task 7): `model.Finding(fqdn, where, target, a, aaaa)`;
  `chain.LEGACY_GCDN_SUFFIX`, `chain.MAX_CNAME_DEPTH`, `chain.ChainResult(target, transient)`,
  `chain.normalize`, `chain.is_legacy_gcdn`, `chain.is_hostname`, `chain.walk`.

**`chain.py` does DETECTION ONLY.** There is deliberately no `addresses()` here: resolving a
legacy-GCDN name to get replacement addresses is forbidden (SPEC §4.1). Addresses come from
Pantheon, in Task 6.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_pantheon_cdn_change_chain.py`:

```python
import dns.resolver
import pytest

from helpers.checkload import load_check_module
from helpers.dnsfake import patch_resolve

pytestmark = pytest.mark.unit


@pytest.fixture
def chain(psh, reset_sc, request):
    return load_check_module(psh, "pantheon_cdn_change", "chain", "pcc_chain_probe", request)


def test_normalize_and_predicates(chain):
    assert chain.normalize("LIVE-X.PantheonSite.io.") == "live-x.pantheonsite.io"
    assert chain.is_legacy_gcdn("LIVE-X.PantheonSite.io.") is True
    assert chain.is_legacy_gcdn("x.cdn.cloudflare.net") is False
    # A name that merely CONTAINS the string is not a legacy-GCDN name.
    assert chain.is_legacy_gcdn("pantheonsite.io.evil.example") is False
    assert chain.is_hostname("live-x.pantheonsite.io") is True
    assert chain.is_hostname("23.185.0.4") is False
    assert chain.is_hostname("2620:12a:8000::4") is False


def test_start_is_already_legacy_gcdn_no_queries(chain, monkeypatch):
    calls = []
    patch_resolve(monkeypatch, {}, calls)
    assert chain.walk("live-x.pantheonsite.io") == chain.ChainResult(
        "live-x.pantheonsite.io", False)
    assert calls == []          # a hit at depth 0 issues NO DNS query


def test_hit_at_depth_one(chain, monkeypatch):
    patch_resolve(monkeypatch,
                  {("occb.bus.umich.edu", "CNAME"): ["live-bus-occb.pantheonsite.io."]})
    assert chain.walk("occb.bus.umich.edu") == chain.ChainResult(
        "live-bus-occb.pantheonsite.io", False)


def test_hit_at_depth_three(chain, monkeypatch):
    patch_resolve(monkeypatch, {
        ("a.example.org", "CNAME"): ["b.example.org."],
        ("b.example.org", "CNAME"): ["c.example.org."],
        ("c.example.org", "CNAME"): ["live-x.pantheonsite.io."],
    })
    assert chain.walk("a.example.org").target == "live-x.pantheonsite.io"


def test_no_cname_is_no_hit(chain, monkeypatch):
    patch_resolve(monkeypatch, {})                       # missing key -> NoAnswer
    assert chain.walk("a.example.org") == chain.ChainResult("", False)


def test_nxdomain_is_no_hit(chain, monkeypatch):
    patch_resolve(monkeypatch, {("a.example.org", "CNAME"): dns.resolver.NXDOMAIN()})
    assert chain.walk("a.example.org") == chain.ChainResult("", False)


def test_chain_ending_off_pantheon_is_no_hit(chain, monkeypatch):
    # The real backstage.its.umich.edu shape: public DNS shows only the Cloudflare CNAME.
    patch_resolve(monkeypatch, {
        ("backstage.its.umich.edu", "CNAME"): ["backstage.its.umich.edu.cdn.cloudflare.net."],
    })
    assert chain.walk("backstage.its.umich.edu") == chain.ChainResult("", False)


@pytest.mark.parametrize("exc", [dns.resolver.Timeout(), dns.resolver.NoNameservers()])
def test_transient_is_unknown_not_a_hit(chain, monkeypatch, exc):
    patch_resolve(monkeypatch, {("a.example.org", "CNAME"): exc})
    assert chain.walk("a.example.org") == chain.ChainResult("", True)


def test_malformed_name_is_no_hit_and_does_not_raise(chain, monkeypatch):
    # F10: the named exception from the dns_classify seam (Task 2) must not escape the check.
    import dns_classify
    patch_resolve(monkeypatch,
                  {("a..b", "CNAME"): dns_classify.MalformedNameError("a..b: EmptyLabel")})
    assert chain.walk("a..b") == chain.ChainResult("", False)


def test_loop_is_no_hit_and_terminates(chain, monkeypatch):
    patch_resolve(monkeypatch, {
        ("a.example.org", "CNAME"): ["b.example.org."],
        ("b.example.org", "CNAME"): ["a.example.org."],
    })
    assert chain.walk("a.example.org") == chain.ChainResult("", False)


def test_depth_cap_is_no_hit_and_terminates(chain, monkeypatch):
    zone = {(f"h{i}.example.org", "CNAME"): [f"h{i + 1}.example.org."] for i in range(20)}
    patch_resolve(monkeypatch, zone)
    assert chain.walk("h0.example.org") == chain.ChainResult("", False)


def test_chain_does_not_resolve_addresses(chain):
    # SPEC §4.1: replacement addresses come from Pantheon (domain:dns), NEVER from resolving the
    # legacy-GCDN name -- a stale target belongs to a DIFFERENT Pantheon site.  Guard the rule.
    assert not hasattr(chain, "addresses")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./run-tests --fast tests/unit/test_pantheon_cdn_change_chain.py`
Expected: fixture error — `check/pantheon_cdn_change/chain.py` does not exist.

- [ ] **Step 3: Create `check/pantheon_cdn_change/__init__.py` (placeholder)**

```python
"""Pantheon CDN-change check (site_post_dns).  Hook registration lands in Task 9."""
```

- [ ] **Step 4: Create `check/pantheon_cdn_change/model.py`**

```python
"""The Finding NamedTuple: the one type shared by detect.py (which produces them) and
notices.py (which renders them).

It lives in its own module so notices.py stays PURE -- importing it from detect.py would drag
chain.py and dnspython into the notice builder for no reason.
"""
from typing import NamedTuple


class Finding(NamedTuple):
    fqdn: str          # the site's custom domain (CSV-safe: see detect.is_safe_domain_id, F13)
    where: str         # machine value: "dns" | "cloudflare" | "both"  (canonical -- SPEC §5)
    target: str        # the legacy-GCDN name the record's chain reaches (operator context only)
    a: list            # Pantheon's required A records     -- all three empty when domain:dns
    aaaa: list         # Pantheon's required AAAA records     failed or had no row (F4)
    cname: list        # Pantheon's required CNAME values  -- non-empty only for a site already
                       #                                      on the new GCDN Beta (F14)
```

- [ ] **Step 5: Create `check/pantheon_cdn_change/chain.py`**

```python
"""CNAME-chain walking for the Pantheon CDN-change check.  DETECTION ONLY.

There is deliberately NO address lookup in this module.  Replacement addresses come from
Pantheon (check/pantheon_cdn_change/pantheon.py -> terminus domain:dns), never from resolving
the legacy-GCDN name a broken record happens to point at: when that name is STALE it belongs to
a DIFFERENT Pantheon site, and we would email its addresses to the wrong owner (SPEC §4.1).

Every lookup goes through dns_classify.resolve -- the one monkeypatchable DNS seam (CLAUDE.md).
dns.resolver is imported ONLY for its exception classes.

walk() checks `start` itself before resolving anything, so a Cloudflare origin that already IS
a legacy-GCDN name is a hit with zero queries:

     start ---> [ legacy-GCDN name? ] -- yes --> HIT(name)
                        | no
                        v
             [ resolve(name, "CNAME") ]
              |      |       |               |
   NoAnswer / |      | CNAME | Timeout /     | MalformedNameError
   NXDOMAIN   |      | target| NoNameservers | (not a valid DNS name at all)
              v      v       v               v
          NO-HIT  (loop   TRANSIENT       NO-HIT + ATTENTION
                   back)  (UNKNOWN;        (F10 -- MUST NOT escape: the
                          ATTENTION;        per-site loop has no try/except,
                          caller must NOT   so an escaped exception aborts
                          report the FQDN)  the whole run)
                        |
       depth > MAX_CNAME_DEPTH, or the name was already seen (CNAME loop)
                        `--> NO-HIT + ATTENTION
"""
import ipaddress
from typing import NamedTuple

import dns.resolver                       # exception classes only; resolution goes via the seam
from rich.markup import escape as rich_escape

import dns_classify
import script_context as sc

LEGACY_GCDN_SUFFIX = ".pantheonsite.io"   # the legacy Pantheon GCDN (Fastly) edge names
MAX_CNAME_DEPTH = 8


class ChainResult(NamedTuple):
    target: str        # the legacy-GCDN name reached; "" when none was
    transient: bool    # True: a transient resolver error stopped the walk -> result UNKNOWN


def normalize(name: str) -> str:
    """Lowercase, strip whitespace and the trailing root dot dnspython includes."""
    return str(name).strip().rstrip(".").lower()


def is_legacy_gcdn(name: str) -> bool:
    return normalize(name).endswith(LEGACY_GCDN_SUFFIX)


def is_hostname(value: str) -> bool:
    """False for an IPv4/IPv6 literal (a proxied A/AAAA record's content), True for a name.

    Load-bearing, not theoretical: 1003 of the 2323 origins in the current fqdns.json are IP
    literals.  Resolving one would be a pointless query at best.
    """
    name = normalize(value)
    if not name:
        return False
    try:
        ipaddress.ip_address(name)
    except ValueError:
        return True
    return False


def walk(start: str) -> ChainResult:
    """Follow the CNAME chain from `start`, looking for a legacy-GCDN name.  See the diagram."""
    name = normalize(start)
    seen = set()
    for hop in range(MAX_CNAME_DEPTH + 1):
        if is_legacy_gcdn(name):
            return ChainResult(name, False)
        if hop == MAX_CNAME_DEPTH:
            break
        if name in seen:
            sc.console.print(
                ":exclamation: [bold red] ATTENTION: CNAME chain for "
                f"{rich_escape(normalize(start))} loops at {rich_escape(name)}")
            return ChainResult("", False)
        seen.add(name)
        try:
            answer = dns_classify.resolve(name, "CNAME")
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            return ChainResult("", False)          # definitive: no CNAME here, chain ends
        except (dns.resolver.NoNameservers, dns.resolver.Timeout) as e:
            sc.console.print(
                ":exclamation: [bold red] ATTENTION: could not check "
                f"{rich_escape(normalize(start))} for a legacy-GCDN CNAME "
                f"(transient DNS error at {rich_escape(name)}: {type(e).__name__})")
            return ChainResult("", True)           # UNKNOWN -- never reported as a finding
        except dns_classify.MalformedNameError as e:
            # F10.  A name that is not syntactically valid cannot be in DNS, so it cannot be
            # CNAME'd to the legacy GCDN -- and this MUST NOT escape (the per-site loop has no
            # try/except).  rich_escape the exception: its message embeds the raw name.
            sc.console.print(
                ":exclamation: [bold red] ATTENTION: not a valid DNS name, skipping the "
                f"legacy-GCDN check for it: {rich_escape(str(e))}")
            return ChainResult("", False)
        targets = [normalize(rdata.target) for rdata in answer]
        if not targets:
            return ChainResult("", False)
        sc.debug(f"{rich_escape(name)} is a CNAME to {rich_escape(targets[0])}", level=2)
        name = targets[0]
    sc.console.print(
        ":exclamation: [bold red] ATTENTION: CNAME chain for "
        f"{rich_escape(normalize(start))} exceeds {MAX_CNAME_DEPTH} hops")
    return ChainResult("", False)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `./run-tests --fast tests/unit/test_pantheon_cdn_change_chain.py`
Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add check/pantheon_cdn_change/ tests/unit/test_pantheon_cdn_change_chain.py
git commit -m "feat(pantheon-cdn-change): CNAME-chain walker (detection)"
```

---

### Task 6: `pantheon.py` — Pantheon's required records per domain

**Files:**
- Create: `check/pantheon_cdn_change/pantheon.py`
- Test: `tests/unit/test_pantheon_cdn_change_pantheon.py`

**Interfaces:**
- Consumes: `sc.terminus` (Task 4).
- Produces (used by Task 7): `Required(a: list, aaaa: list, cname: list)`, `EMPTY`,
  `required_records(site_id: str, site_name: str = "") -> dict` mapping normalized FQDN →
  `Required`.

Real shape of the data, verified live 2026-07-12 — a **list** of rows:

```
$ terminus domain:dns bus-occb.live --format=json          # NOT yet migrated
{"domain":"occb.bus.umich.edu","type":"A","value":"23.185.0.4","detected_value":"",
 "status":"action_required","status_message":"Add this required record"}
{"domain":"occb.bus.umich.edu","type":"AAAA","value":"2620:12a:8000::4", …}
{"domain":"occb.bus.umich.edu","type":"AAAA","value":"2620:12a:8001::4", …}
{"domain":"occb.bus.umich.edu","type":"CNAME","value":"",                 # <- no requirement
 "detected_value":"live-bus-occb.pantheonsite.io","status_message":"Remove this detected record"}

$ terminus domain:dns its-wws-test1.live --format=json     # ALREADY on the new GCDN Beta
{"domain":"wws-test1.cdn-dev.it.umich.edu","type":"CNAME","value":"fe.cfp2c.edge.pantheon.io",
 "detected_value":"fe.cfp2c.edge.pantheon.io","status":"okay","status_message":"Correct value detected"}
# ... and NO A/AAAA rows at all.
```

**That second shape is F14 and it is the whole reason `Required` carries `cname`.** A CNAME-only
answer is an *answer*; collapsing it into the same empty result as a terminus failure would tell
the owner "unavailable — please contact us" for a domain Pantheon answered perfectly well, and
tell the operator nothing. Keep A, AAAA **and** CNAME; drop only rows whose `value` is empty.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_pantheon_cdn_change_pantheon.py`:

```python
import pytest

from helpers.checkload import load_check_module
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.unit


# Verbatim shape of `terminus domain:dns bus-occb.live --format=json` (verified 2026-07-12).
OCCB_ROWS = [
    {"domain": "occb.bus.umich.edu", "type": "A", "value": "23.185.0.4",
     "detected_value": "", "status": "action_required",
     "status_message": "Add this required record"},
    {"domain": "occb.bus.umich.edu", "type": "AAAA", "value": "2620:12a:8000::4",
     "detected_value": "", "status": "action_required",
     "status_message": "Add this required record"},
    {"domain": "occb.bus.umich.edu", "type": "AAAA", "value": "2620:12a:8001::4",
     "detected_value": "", "status": "action_required",
     "status_message": "Add this required record"},
    {"domain": "occb.bus.umich.edu", "type": "CNAME", "value": "",
     "detected_value": "live-bus-occb.pantheonsite.io", "status": "action_required",
     "status_message": "Remove this detected record"},
]

# An already-migrated site (its-wws-test1, verified live): CNAME only, NO A/AAAA rows.
MIGRATED_ROWS = [
    {"domain": "wws-test1.cdn-dev.it.umich.edu", "type": "CNAME",
     "value": "fe.cfp2c.edge.pantheon.io", "detected_value": "fe.cfp2c.edge.pantheon.io",
     "status": "okay", "status_message": "Correct value detected"},
]


@pytest.fixture
def pantheon(psh, reset_sc, request):
    return load_check_module(
        psh, "pantheon_cdn_change", "pantheon", "pcc_pantheon_probe", request)


def _fake_terminus(reset_sc, monkeypatch, result, errors="", fatal=False, calls=None):
    def _terminus(*args):
        if calls is not None:
            calls.append(args)
        return result, errors, fatal
    monkeypatch.setattr(reset_sc, "terminus", _terminus)


def test_parses_required_a_and_aaaa(pantheon, reset_sc, monkeypatch):
    calls = []
    _fake_terminus(reset_sc, monkeypatch, OCCB_ROWS, calls=calls)
    # In production site_id is a UUID; the call shape is what matters here.
    out = pantheon.required_records("9cf2c790-c7b8-4f2f-a6f1-27385b8f958e", "bus-occb")
    assert calls == [("domain:dns", "9cf2c790-c7b8-4f2f-a6f1-27385b8f958e.live")]  # LIVE env
    assert out == {"occb.bus.umich.edu": pantheon.Required(
        ["23.185.0.4"], ["2620:12a:8000::4", "2620:12a:8001::4"], [])}


def test_valueless_remove_rows_are_skipped(pantheon, reset_sc, monkeypatch):
    _fake_terminus(reset_sc, monkeypatch, OCCB_ROWS)
    out = pantheon.required_records("s", "s")
    # The "Remove this detected record" CNAME row has an empty `value` -- no requirement.
    assert out["occb.bus.umich.edu"].cname == []
    assert "live-bus-occb.pantheonsite.io" not in str(out)


def test_cname_only_answer_is_kept(pantheon, reset_sc, monkeypatch):
    # F14: an already-migrated site.  This is an ANSWER, not a failure -- it must NOT come back
    # as {} (which is what a terminus failure returns) and must NOT render as "unavailable".
    _fake_terminus(reset_sc, monkeypatch, MIGRATED_ROWS)
    out = pantheon.required_records("s", "its-wws-test1")
    got = out["wws-test1.cdn-dev.it.umich.edu"]
    assert got.a == [] and got.aaaa == []
    assert got.cname == ["fe.cfp2c.edge.pantheon.io"]
    assert got != pantheon.EMPTY               # distinguishable from "no answer at all"


def test_multiple_domains_per_site(pantheon, reset_sc, monkeypatch):
    rows = [
        {"domain": "backstage.its.umich.edu", "type": "A", "value": "23.185.0.2"},
        {"domain": "news.backstage.its.umich.edu", "type": "A", "value": "23.185.0.2"},
        {"domain": "news.backstage.its.umich.edu", "type": "AAAA", "value": "2620:12a:8000::2"},
    ]
    _fake_terminus(reset_sc, monkeypatch, rows)
    out = pantheon.required_records("s", "its-backstage")
    assert set(out) == {"backstage.its.umich.edu", "news.backstage.its.umich.edu"}
    assert out["news.backstage.its.umich.edu"].aaaa == ["2620:12a:8000::2"]


def test_order_is_pantheons_order_not_ours(pantheon, reset_sc, monkeypatch):
    # Records are NEVER re-sorted: a sort key over remote strings (ipaddress.ip_address) would
    # raise on garbage.  Pantheon's order is already deterministic.
    rows = [
        {"domain": "x.example.org", "type": "AAAA", "value": "2620:12a:8001::4"},
        {"domain": "x.example.org", "type": "AAAA", "value": "2620:12a:8000::4"},
    ]
    _fake_terminus(reset_sc, monkeypatch, rows)
    assert pantheon.required_records("s", "s")["x.example.org"].aaaa == [
        "2620:12a:8001::4", "2620:12a:8000::4"]


@pytest.mark.parametrize(
    "result,fatal",
    [(None, True), (None, False), ("not a list", False), ([{"junk": 1}], False)],
    ids=["fatal", "undecodable", "wrong-type", "malformed-rows"])
def test_failure_yields_empty_map_and_never_raises(
        pantheon, reset_sc, monkeypatch, result, fatal):
    # F4: domain:dns is an ENRICHMENT call.  Its failure must never abort the site -- the
    # findings are still reported, with the records rendered "unavailable".
    console = recording_console(monkeypatch, reset_sc)
    _fake_terminus(reset_sc, monkeypatch, result, errors="boom", fatal=fatal)
    assert pantheon.required_records("9cf2c790-c7b8-4f2f-a6f1-27385b8f958e", "bus-occb") == {}
    if fatal or not isinstance(result, list):
        out = console.export_text()
        assert "ATTENTION" in out
        assert "bus-occb" in out                    # the NAME, never the UUID
        assert "9cf2c790" not in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./run-tests --fast tests/unit/test_pantheon_cdn_change_pantheon.py`
Expected: fixture error — `check/pantheon_cdn_change/pantheon.py` does not exist.

- [ ] **Step 3: Write the implementation**

Create `check/pantheon_cdn_change/pantheon.py`:

```python
"""Pantheon's AUTHORITATIVE required records for a site's custom domains (domain:dns).

Why not resolve the legacy-GCDN name ourselves (SPEC §4.1): when a record points at a STALE
legacy name -- the site was renamed on Pantheon, a Cloudflare origin was never updated, a domain
moved between sites -- that name belongs to a DIFFERENT Pantheon site, and resolving it returns
THAT site's edge addresses.  Publishing them to an owner would be confidently wrong.  Pantheon
answers per-domain, is never stale, and auto-follows its own migration.

Why terminus and not the Pantheon API: the API has the same endpoint
(GET /v0/sites/{id}/environments/{env}/domains/dns), and CLAUDE.md prefers the API for new code
-- but the script has NO API client.  Building machine-token -> session-token auth, a session
cache, an HTTP seam and new fixtures, for a check that gets deleted after the migration, is not
worth it; terminus() is the established wrapper and run_terminus() is the harness's mock seam, so
this rides the existing offline test machinery.  CLAUDE.md allows terminus when it is
"significantly simpler" -- it is.  When the API client is built, this module is a one-function swap.

Shape of `terminus domain:dns <site>.live --format=json` (both verified live, 2026-07-12):

    NOT migrated (bus-occb):
      {"domain": "occb.bus.umich.edu", "type": "A",     "value": "23.185.0.4",  ...}
      {"domain": "occb.bus.umich.edu", "type": "AAAA",  "value": "2620:12a:8000::4", ...}
      {"domain": "occb.bus.umich.edu", "type": "CNAME", "value": "",            # <- no requirement
       "detected_value": "live-bus-occb.pantheonsite.io", "status_message": "Remove this detected record"}

    ALREADY migrated (its-wws-test1) -- CNAME only, NO A/AAAA rows:
      {"domain": "wws-test1.cdn-dev.it.umich.edu", "type": "CNAME",
       "value": "fe.cfp2c.edge.pantheon.io", "status": "okay", ...}

A row with an empty `value` states no requirement and is skipped.  Everything else -- A, AAAA and
CNAME -- is kept: the CNAME-only answer is F14, an ANSWER rather than a failure, and it must stay
distinguishable from {} (which is what a terminus failure returns).
"""
from typing import NamedTuple

from rich.markup import escape as rich_escape

import script_context as sc


class Required(NamedTuple):
    a: list            # Pantheon's required A records,     IN PANTHEON'S ORDER
    aaaa: list         # Pantheon's required AAAA records,  IN PANTHEON'S ORDER
    cname: list        # Pantheon's required CNAME values (an already-migrated site -- F14)


EMPTY = Required([], [], [])


def required_records(site_id: str, site_name: str = "") -> dict:
    """{normalized fqdn: Required} for the site's LIVE environment.

    `site_id` is what the command needs (it is a UUID in production -- core builds live_site the
    same way, pantheon-sitehealth-emails:1540).  `site_name` is for the OPERATOR message: an
    ATTENTION reading "could not fetch ... for 9cf2c790-..." is not actionable.

    NEVER fatal: this is an enrichment call.  A terminus failure, an undecodable result, or a
    malformed row yields {} (or simply omits that domain) plus a console ATTENTION -- the caller
    still reports every finding, with the records shown as "unavailable" (F4).  A missing record
    must never hide a CNAME that has to be fixed.

    Records are NEVER re-sorted (a sort key over remote strings is a crash class; Pantheon's own
    order is deterministic and is what its dashboard shows).
    """
    label = site_name or site_id
    rows, errors, fatal = sc.terminus("domain:dns", f"{site_id}.live")
    if fatal or rows is None:
        sc.console.print(
            ":exclamation: [bold red] ATTENTION: could not fetch Pantheon's required DNS "
            f"records for {rich_escape(str(label))}: {rich_escape(str(errors))}")
        return {}
    if not isinstance(rows, list):
        sc.console.print(
            ":exclamation: [bold red] ATTENTION: unexpected domain:dns result for "
            f"{rich_escape(str(label))} (expected a list, got {type(rows).__name__})")
        return {}

    buckets = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        domain = str(row.get("domain", "")).strip().rstrip(".").lower()
        rrtype = row.get("type")
        value = str(row.get("value", "")).strip()
        if not domain or not value or rrtype not in ("A", "AAAA", "CNAME"):
            continue          # an empty `value` ("Remove this detected record") is no requirement
        buckets.setdefault(domain, {"A": [], "AAAA": [], "CNAME": []})[rrtype].append(value)

    records = {d: Required(v["A"], v["AAAA"], v["CNAME"]) for d, v in buckets.items()}
    sc.debug(f"Pantheon requires records for {len(records)} domain(s) of {label}", level=2)
    return records
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./run-tests --fast tests/unit/test_pantheon_cdn_change_pantheon.py`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add check/pantheon_cdn_change/pantheon.py tests/unit/test_pantheon_cdn_change_pantheon.py
git commit -m "feat(pantheon-cdn-change): fetch Pantheon's required records via domain:dns"
```

---


### Task 7: `detect.py` — findings from the two sources

**Files:**
- Create: `check/pantheon_cdn_change/detect.py`
- Test: `tests/unit/test_pantheon_cdn_change_detect.py`

**Interfaces:**
- Consumes: `chain.walk` / `is_hostname` / `normalize` (Task 5), `model.Finding` (Task 5),
  `pantheon.required_records` / `EMPTY` (Task 6), `sc.fqdn_re` (Task 4).
- Produces (used by Task 9): `cloudflare_origins(fqdn, proxied_fqdns) -> list`;
  `is_safe_domain_id(fqdn) -> bool`;
  `find_findings(site_id, site_name, custom_domains, proxied_fqdns, cloudflare_on) -> list[Finding]`.

**F13, stated precisely** (an earlier draft got this wrong and its test would have failed):
`fqdn_re` **matches** `a..b`, and its `$` even matches a trailing newline — but it **rejects a
comma** (all three verified 2026-07-12). The guard here is for **CSV integrity only**, so it is
`fqdn_re` **plus** an explicit reject of `,`, `\r`, `\n`. A malformed-but-comma-free name like
`a..b` is F10's job (the `MalformedNameError` seam), not this one.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_pantheon_cdn_change_detect.py`:

```python
import re

import dns.resolver
import pytest

from helpers.checkload import load_check_module
from helpers.dnsfake import patch_resolve, recording_console

pytestmark = pytest.mark.unit

FQDN_RE = re.compile(r"^_?[a-z0-9-]+\.[a-z0-9.-]+$", re.IGNORECASE)   # core's regex (:89)

OCCB_ZONE = {("occb.bus.umich.edu", "CNAME"): ["live-bus-occb.pantheonsite.io."]}
BACKSTAGE_ZONE = {
    ("backstage.its.umich.edu", "CNAME"): ["backstage.its.umich.edu.cdn.cloudflare.net."],
}
BACKSTAGE_PROXIED = {
    "backstage.its.umich.edu": {
        "zone_id": "1f39", "origins": ["live-its-backstage.pantheonsite.io"]},
}


@pytest.fixture
def detect(psh, reset_sc, request, monkeypatch):
    monkeypatch.setattr(reset_sc, "fqdn_re", FQDN_RE)
    return load_check_module(
        psh, "pantheon_cdn_change", "detect", "pcc_detect_probe", request)


def _pantheon_says(detect, monkeypatch, mapping, calls=None):
    """Patch pantheon.required_records on the module `detect` actually imported.

    `mapping` is {fqdn: (a, aaaa, cname)}.
    """
    def _required(site_id, site_name=""):
        if calls is not None:
            calls.append(site_id)
        return {fqdn: detect.pantheon.Required(a, aaaa, cname)
                for fqdn, (a, aaaa, cname) in mapping.items()}
    monkeypatch.setattr(detect.pantheon, "required_records", _required)


def test_dns_only_finding(detect, monkeypatch):
    patch_resolve(monkeypatch, OCCB_ZONE)
    _pantheon_says(detect, monkeypatch, {
        "occb.bus.umich.edu": (["23.185.0.4"], ["2620:12a:8000::4", "2620:12a:8001::4"], [])})
    assert detect.find_findings(
        "uuid", "bus-occb", ["occb.bus.umich.edu"], {}, True) == [
            detect.Finding("occb.bus.umich.edu", "dns", "live-bus-occb.pantheonsite.io",
                           ["23.185.0.4"], ["2620:12a:8000::4", "2620:12a:8001::4"], [])]


def test_cloudflare_only_finding(detect, monkeypatch):
    patch_resolve(monkeypatch, BACKSTAGE_ZONE)
    _pantheon_says(detect, monkeypatch, {
        "backstage.its.umich.edu": (["23.185.0.2"], ["2620:12a:8000::2"], [])})
    findings = detect.find_findings(
        "uuid", "its-backstage", ["backstage.its.umich.edu"], BACKSTAGE_PROXIED, True)
    assert findings[0].where == "cloudflare"
    assert findings[0].a == ["23.185.0.2"]         # Pantheon's answer, not a resolved target


def test_both_sources_same_target_is_one_row(detect, monkeypatch):
    patch_resolve(monkeypatch, OCCB_ZONE)
    _pantheon_says(detect, monkeypatch, {"occb.bus.umich.edu": (["23.185.0.4"], [], [])})
    proxied = {"occb.bus.umich.edu": {"origins": ["live-bus-occb.pantheonsite.io"]}}
    findings = detect.find_findings("uuid", "bus-occb", ["occb.bus.umich.edu"], proxied, True)
    assert len(findings) == 1
    assert findings[0].where == "both"


def test_split_targets_warn_but_emit_one_row(detect, reset_sc, monkeypatch):
    # F11: the two sources reach DIFFERENT legacy names.  Pantheon's per-domain answer is correct
    # for BOTH records, so it is one row -- but the disagreement is an operator signal.
    console = recording_console(monkeypatch, reset_sc)
    patch_resolve(monkeypatch, {("x.example.org", "CNAME"): ["live-aaa.pantheonsite.io."]})
    _pantheon_says(detect, monkeypatch, {"x.example.org": (["23.185.0.9"], [], [])})
    proxied = {"x.example.org": {"origins": ["live-bbb.pantheonsite.io"]}}
    findings = detect.find_findings("uuid", "s", ["x.example.org"], proxied, True)
    assert len(findings) == 1
    assert findings[0].where == "both"
    assert findings[0].a == ["23.185.0.9"]        # Pantheon's, NOT live-aaa's or live-bbb's
    out = console.export_text()
    assert "DIFFERENT" in out and "live-aaa" in out and "live-bbb" in out


def test_cname_only_finding_warns(detect, reset_sc, monkeypatch):
    # F14: Pantheon answers with a CNAME and no A/AAAA (an already-migrated site).  The finding
    # carries the CNAME, and the operator is told -- it must NOT look like a failed lookup.
    console = recording_console(monkeypatch, reset_sc)
    patch_resolve(monkeypatch, OCCB_ZONE)
    _pantheon_says(detect, monkeypatch,
                   {"occb.bus.umich.edu": ([], [], ["fe.cfp2c.edge.pantheon.io"])})
    findings = detect.find_findings("uuid", "bus-occb", ["occb.bus.umich.edu"], {}, True)
    assert findings[0].cname == ["fe.cfp2c.edge.pantheon.io"]
    assert findings[0].a == [] and findings[0].aaaa == []
    out = console.export_text()
    assert "no A/AAAA" in out and "fe.cfp2c.edge.pantheon.io" in out


def test_clean_site_makes_no_pantheon_call(detect, monkeypatch):
    # The domain:dns call is LAZY: a clean site must cost nothing on an --all run.
    calls = []
    patch_resolve(monkeypatch, BACKSTAGE_ZONE)
    _pantheon_says(detect, monkeypatch, {}, calls=calls)
    assert detect.find_findings(
        "uuid", "its-backstage", ["backstage.its.umich.edu"], {}, True) == []
    assert calls == []


def test_cloudflare_disabled_skips_source_two(detect, monkeypatch):
    patch_resolve(monkeypatch, BACKSTAGE_ZONE)
    _pantheon_says(detect, monkeypatch, {})
    assert detect.find_findings(
        "uuid", "its-backstage", ["backstage.its.umich.edu"], BACKSTAGE_PROXIED, False) == []


def test_transient_dns_is_never_a_finding(detect, monkeypatch):
    patch_resolve(monkeypatch, {("a.example.org", "CNAME"): dns.resolver.Timeout()})
    _pantheon_says(detect, monkeypatch, {})
    assert detect.find_findings("uuid", "s", ["a.example.org"], {}, True) == []


def test_legacy_array_form_of_fqdns_json(detect, monkeypatch):
    patch_resolve(monkeypatch, BACKSTAGE_ZONE)
    _pantheon_says(detect, monkeypatch, {"backstage.its.umich.edu": (["23.185.0.2"], [], [])})
    proxied = {"backstage.its.umich.edu": ["live-its-backstage.pantheonsite.io"]}   # old format
    assert detect.find_findings(
        "uuid", "its-backstage", ["backstage.its.umich.edu"], proxied,
        True)[0].where == "cloudflare"


def test_ip_origin_is_skipped_without_a_query(detect, monkeypatch):
    calls = []
    patch_resolve(monkeypatch, BACKSTAGE_ZONE, calls)
    _pantheon_says(detect, monkeypatch, {})
    proxied = {"backstage.its.umich.edu": {"origins": ["23.185.0.2", "2620:12a:8000::2"]}}
    assert detect.find_findings(
        "uuid", "its-backstage", ["backstage.its.umich.edu"], proxied, True) == []
    assert ("23.185.0.2", "CNAME") not in calls    # an IP literal is never resolved


def test_finding_without_records_still_reported(detect, monkeypatch):
    # F4: domain:dns failed (or has no row for this FQDN).  The CNAME still has to be fixed.
    patch_resolve(monkeypatch, OCCB_ZONE)
    _pantheon_says(detect, monkeypatch, {})
    findings = detect.find_findings("uuid", "bus-occb", ["occb.bus.umich.edu"], {}, True)
    assert findings[0].where == "dns"
    assert findings[0].a == [] and findings[0].aaaa == [] and findings[0].cname == []


def test_is_safe_domain_id(detect):
    # F13 is a CSV-integrity guard.  fqdn_re REJECTS a comma (that is the one that matters), but
    # it ACCEPTS a..b and a trailing newline -- hence the explicit control-character reject.
    assert detect.is_safe_domain_id("occb.bus.umich.edu") is True
    assert detect.is_safe_domain_id("has,comma.example.org") is False
    assert detect.is_safe_domain_id("trailing.newline.example.org\n") is False
    assert detect.is_safe_domain_id("with space.example.org") is False


def test_invalid_domain_id_skipped(detect, monkeypatch):
    # A comma in a domain id would shift every column of -notices.csv (no escaping there).
    calls = []
    patch_resolve(monkeypatch, {}, calls)
    _pantheon_says(detect, monkeypatch, {})
    assert detect.find_findings(
        "uuid", "s", ["has,comma.example.org", "bad.example.org\n"], {}, True) == []
    assert calls == []            # never even resolved


def test_order_follows_custom_domains(detect, monkeypatch):
    zone = dict(OCCB_ZONE)
    zone[("aaa.bus.umich.edu", "CNAME")] = ["live-bus-occb.pantheonsite.io."]
    patch_resolve(monkeypatch, zone)
    _pantheon_says(detect, monkeypatch, {})
    findings = detect.find_findings(
        "uuid", "bus-occb", ["occb.bus.umich.edu", "aaa.bus.umich.edu"], {}, True)
    assert [f.fqdn for f in findings] == ["occb.bus.umich.edu", "aaa.bus.umich.edu"]


def test_no_custom_domains(detect, monkeypatch):
    patch_resolve(monkeypatch, {})
    _pantheon_says(detect, monkeypatch, {})
    assert detect.find_findings("uuid", "s", [], {}, True) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./run-tests --fast tests/unit/test_pantheon_cdn_change_detect.py`
Expected: fixture error — `check/pantheon_cdn_change/detect.py` does not exist.

- [ ] **Step 3: Write the implementation**

Create `check/pantheon_cdn_change/detect.py`:

```python
"""Findings for the Pantheon CDN-change check: which custom domains still reach the legacy
Pantheon GCDN (Fastly) through a CNAME record, and what Pantheon says to use instead.

DETECTION -- two independent, NON-redundant sources per custom domain (SPEC §2):

  (1) PUBLIC DNS         walk the CNAME chain from the FQDN itself.  The ONLY source that can see
                         an unproxied (grey-cloud) Cloudflare CNAME.
  (2) CLOUDFLARE ORIGINS the `origins` of the FQDN's Cloudflare-PROXIED records, already fetched
                         into fqdns.json by plugin/cloudflare/fqdns.py.  The ONLY source that can
                         see a proxied FQDN's CNAME -- public DNS shows only
                         *.cdn.cloudflare.net -> Cloudflare anycast addresses.

REQUIRED RECORDS -- from Pantheon, per domain, ONE lazy `terminus domain:dns` call for the whole
site, made only if detection found at least one candidate (a clean site costs nothing on --all).
NEVER by resolving the legacy-GCDN name: a stale target belongs to a DIFFERENT Pantheon site and
we would email its addresses to the wrong owner (SPEC §4.1).

If the two sources reach DIFFERENT legacy names (F11), that is one row -- Pantheon's answer is
correct for both records -- plus an operator ATTENTION, because the disagreement itself means
something on the site is misconfigured.
"""
from rich.markup import escape as rich_escape

import script_context as sc

from . import chain, pantheon
from .model import Finding

# Characters that would corrupt -notices.csv, which is split/re-joined on commas with NO escaping
# (pantheon-sitehealth-emails:3924-3926).  fqdn_re rejects a comma but its `$` accepts a trailing
# newline, so reject these explicitly rather than trusting the regex (F13).
CSV_HOSTILE = (",", "\r", "\n")


def is_safe_domain_id(fqdn: str) -> bool:
    """True when the id is safe to resolve, display, and write to the CSV (F13).

    NOT a DNS-validity check: fqdn_re ACCEPTS `a..b` (that case is F10's -- dns_classify.resolve
    raises the named MalformedNameError and chain.walk swallows it).  This guards ONE thing: a
    remote domain id must not be able to inject a column break into the ITS work list.
    """
    text = str(fqdn)
    if any(bad in text for bad in CSV_HOSTILE):
        return False
    return bool(sc.fqdn_re.match(text))


def cloudflare_origins(fqdn: str, proxied_fqdns: dict) -> list:
    """The proxied-record origins for `fqdn` from fqdns.json.

    Tolerates BOTH file formats (CLAUDE.md): the current object form
    {"fqdn": {"zone_id": ..., "origins": [...]}} and the legacy bare-array form
    {"fqdn": ["origin", ...]}.  Anything else -> [] (never a KeyError, never a TypeError).
    fqdns.json keys are Cloudflare-normalized (lowercase, no trailing dot), so the lookup
    normalizes too.
    """
    entry = (proxied_fqdns or {}).get(chain.normalize(fqdn))
    if isinstance(entry, dict):
        origins = entry.get("origins") or []
    elif isinstance(entry, list):
        origins = entry
    else:
        origins = []
    return [str(origin) for origin in origins]


def _cloudflare_target(fqdn: str, proxied_fqdns: dict) -> str:
    """The first legacy-GCDN name reached from any of the FQDN's Cloudflare origins ("" = none)."""
    for origin in cloudflare_origins(fqdn, proxied_fqdns):
        if not chain.is_hostname(origin):          # a proxied A/AAAA record's IP literal (F8)
            continue
        sc.debug(f"{rich_escape(str(fqdn))} has Cloudflare origin {rich_escape(origin)}", level=2)
        result = chain.walk(origin)
        if result.target:
            return result.target
    return ""


def _candidates(custom_domains: list, proxied_fqdns: dict, cloudflare_on: bool) -> list:
    """[(fqdn, where, target)] in custom_domains order -- detection only, no Pantheon call."""
    found = []
    for fqdn in custom_domains or []:
        if not is_safe_domain_id(fqdn):
            sc.debug(f"skipping invalid domain id {rich_escape(str(fqdn))}")
            continue

        sc.debug(f"checking {rich_escape(str(fqdn))} for legacy-GCDN CNAMEs")
        dns_target = chain.walk(fqdn).target       # transient/malformed -> "" -> never a finding
        cloudflare_target = _cloudflare_target(fqdn, proxied_fqdns) if cloudflare_on else ""

        if not dns_target and not cloudflare_target:
            continue

        if dns_target and cloudflare_target:
            if dns_target != cloudflare_target:
                # F11.  ONE row (Pantheon's records are right for both), but the operator needs to
                # know the two records point at different Pantheon sites.
                sc.console.print(
                    f":exclamation: [bold red] ATTENTION: {rich_escape(str(fqdn))} reaches "
                    f"DIFFERENT legacy-GCDN names in DNS ({rich_escape(dns_target)}) and "
                    f"Cloudflare ({rich_escape(cloudflare_target)}) -- the records disagree; "
                    "check the site")
            where = "both"
        elif dns_target:
            where = "dns"
        else:
            where = "cloudflare"

        target = dns_target or cloudflare_target
        sc.debug(f"{rich_escape(str(fqdn))} reaches {rich_escape(target)} via {where}")
        found.append((fqdn, where, target))
    return found


def find_findings(site_id: str, site_name: str, custom_domains: list, proxied_fqdns: dict,
                  cloudflare_on: bool) -> list:
    """Detect candidates, then enrich them with Pantheon's required records (lazily).

    site_id is the UUID the terminus command needs; site_name is what operator messages print.
    """
    candidates = _candidates(custom_domains, proxied_fqdns, cloudflare_on)
    if not candidates:
        return []      # a clean site issues NO domain:dns call

    required = pantheon.required_records(site_id, site_name)   # {} on failure -- never fatal (F4)
    findings = []
    for fqdn, where, target in candidates:
        records = required.get(chain.normalize(fqdn), pantheon.EMPTY)
        if not records.a and not records.aaaa and records.cname:
            # F14: an already-migrated site -- Pantheon requires a CNAME, not addresses.  This is
            # an ANSWER, not a failure; say so, and let the notice show what Pantheon requires.
            sc.console.print(
                ":exclamation: [bold red] ATTENTION: Pantheon requires no A/AAAA for "
                f"{rich_escape(str(fqdn))} -- it requires CNAME "
                f"{rich_escape(', '.join(records.cname))}; the site may already be on the new "
                "GCDN Beta")
        findings.append(
            Finding(fqdn, where, target, records.a, records.aaaa, records.cname))
    return findings
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./run-tests --fast tests/unit/test_pantheon_cdn_change_detect.py`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add check/pantheon_cdn_change/detect.py tests/unit/test_pantheon_cdn_change_detect.py
git commit -m "feat(pantheon-cdn-change): detect legacy-GCDN CNAMEs; enrich with Pantheon's records"
```

---


### Task 8: `notices.py` — the single owner-facing notice

**Files:**
- Create: `check/pantheon_cdn_change/notices.py`
- Test: `tests/unit/test_pantheon_cdn_change_notices.py`

**Interfaces:**
- Consumes: `model.Finding` (Task 5). **Nothing else** — `notices.py` imports only `html` and
  `.model`, never `detect`/`chain`/`pantheon`, so it stays pure and never pulls in dnspython.
- Produces (used by Task 9): `DOCS_URL`, `where_label(where, *, umich)` (raises `ValueError` on
  an unknown `where`), `cdn_change_notice(site_name, findings, *, umich, before_cutoff) -> dict`.

The exact copy is specified in SPEC §8 — do not paraphrase it.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_pantheon_cdn_change_notices.py`:

```python
import pytest

from helpers.checkload import load_check_module

pytestmark = pytest.mark.unit


@pytest.fixture
def notices(psh, reset_sc, request):
    return load_check_module(
        psh, "pantheon_cdn_change", "notices", "pcc_notices_probe", request)


@pytest.fixture
def findings(notices):
    F = notices.Finding
    return [
        F("occb.bus.umich.edu", "dns", "live-bus-occb.pantheonsite.io",
          ["23.185.0.4"], ["2620:12a:8000::4", "2620:12a:8001::4"], []),
        F("backstage.its.umich.edu", "cloudflare", "live-its-backstage.pantheonsite.io",
          ["23.185.0.2"], ["2620:12a:8000::2", "2620:12a:8001::2"], []),
    ]


def test_notice_shape(notices, findings):
    n = notices.cdn_change_notice("s", findings, umich=True, before_cutoff=True)
    assert n["type"] == "info"
    assert n["csv"] == "s,pantheon-cdn-change,occb.bus.umich.edu,backstage.its.umich.edu"
    assert n["short"] == "Pantheon CDN change: replace CNAME records"
    assert n["text"]                                    # bespoke plaintext, not html2text'd
    assert notices.DOCS_URL in n["message"] and notices.DOCS_URL in n["text"]


def test_notices_module_is_pure(notices):
    # It must not drag dnspython or terminus into the notice builder.  Assert on the MODULE
    # objects it actually imported -- `"dns.resolver" not in str(vars(notices))` looks like a
    # test and is vacuous (vars() keys are attribute NAMES).
    import types
    imported = {v.__name__ for v in vars(notices).values() if isinstance(v, types.ModuleType)}
    assert imported == {"html"}
    assert not hasattr(notices, "chain") and not hasattr(notices, "pantheon")


def test_where_label_matrix(notices):
    assert notices.where_label("dns", umich=True) == "DNS"
    assert notices.where_label("dns", umich=False) == "DNS"
    assert notices.where_label("cloudflare", umich=True) == "U-M Cloudflare"
    assert notices.where_label("cloudflare", umich=False) == "our (non-Pantheon) Cloudflare"
    assert notices.where_label("both", umich=True) == "DNS and U-M Cloudflare"
    assert notices.where_label("both", umich=False) == "DNS and our (non-Pantheon) Cloudflare"


def test_where_label_rejects_an_unknown_value(notices):
    # A silent fall-through would print a WRONG instruction ("DNS and ...") to a site owner.
    with pytest.raises(ValueError):
        notices.where_label("elsewhere", umich=True)


def test_addresses_and_domains_appear_in_both_renderings(notices, findings):
    n = notices.cdn_change_notice("s", findings, umich=True, before_cutoff=True)
    for body in (n["message"], n["text"]):
        assert "occb.bus.umich.edu" in body
        assert "23.185.0.4" in body
        assert "2620:12a:8001::4" in body
        assert "backstage.its.umich.edu" in body
        assert "23.185.0.2" in body


def test_umich_before_cutoff_promises_maintenance(notices, findings):
    n = notices.cdn_change_notice("s", findings, umich=True, before_cutoff=True)
    assert "ITS will make these changes for you" in n["message"]
    assert "ITS will make these changes for you" in n["text"]
    # The internal cutoff DATE is never disclosed to owners.
    assert "September" not in n["message"] and "2026-09-15" not in n["message"]


def test_umich_on_or_after_cutoff_gets_generic_instruction(notices, findings):
    n = notices.cdn_change_notice("s", findings, umich=True, before_cutoff=False)
    assert "ITS will make these changes" not in n["message"]
    assert "Please replace each CNAME record above" in n["message"]
    assert "U-M Cloudflare" in n["message"]             # still U-M terminology


def test_generic_has_no_umich_leakage(notices, findings):
    n = notices.cdn_change_notice("s", findings, umich=False, before_cutoff=True)
    assert "our (non-Pantheon) Cloudflare" in n["message"]
    for body in (n["message"], n["text"]):
        assert "U-M" not in body
        assert "ITS" not in body


def test_notice_does_not_explain_the_transition(notices, findings):
    n = notices.cdn_change_notice("s", findings, umich=True, before_cutoff=True)
    for forbidden in ("Orange to Orange", "Orange-to-Orange", "Fastly to Cloudflare"):
        assert forbidden not in n["message"]


def test_missing_records_render_as_unavailable(notices):
    # F4: domain:dns failed or had no row for this FQDN.
    F = notices.Finding
    f = [F("x.example.org", "dns", "live-x.pantheonsite.io", [], [], [])]
    umich = notices.cdn_change_notice("s", f, umich=True, before_cutoff=True)
    generic = notices.cdn_change_notice("s", f, umich=False, before_cutoff=True)
    assert "unavailable" in umich["message"] and "please contact us" in umich["message"]
    assert "unavailable" in generic["message"]
    assert "x.example.org" in generic["message"]        # the finding is STILL reported


def test_cname_only_records_render_as_a_cname_not_unavailable(notices):
    # F14: an already-migrated site.  Pantheon HAS an answer -- show it.  Rendering "unavailable"
    # here would tell the owner we failed when we did not.
    F = notices.Finding
    f = [F("x.example.org", "dns", "live-x.pantheonsite.io", [], [],
           ["fe.cfp2c.edge.pantheon.io"])]
    for umich in (True, False):
        n = notices.cdn_change_notice("s", f, umich=umich, before_cutoff=True)
        for body in (n["message"], n["text"]):
            assert "fe.cfp2c.edge.pantheon.io" in body
            assert "CNAME" in body
            assert "unavailable" not in body


def test_fqdn_html_escaped(notices):
    F = notices.Finding
    f = [F("a<b>.example.org", "dns", "live-x.pantheonsite.io", ["1.2.3.4"], [], [])]
    n = notices.cdn_change_notice("s", f, umich=False, before_cutoff=False)
    assert "&lt;b&gt;" in n["message"]
    assert "<b>" not in n["message"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./run-tests --fast tests/unit/test_pantheon_cdn_change_notices.py`
Expected: fixture error — `check/pantheon_cdn_change/notices.py` does not exist.

- [ ] **Step 3: Write the implementation**

Create `check/pantheon_cdn_change/notices.py`:

```python
"""The single owner-facing notice for the Pantheon CDN-change check (SPEC §8).

PURE: Findings in, one notice dict out.  Imports ONLY html + .model -- never detect/chain/
pantheon, so this module pulls in neither dnspython nor terminus.  Four copy variants from two
independent booleans -- umich (terminology) x before_cutoff (who does the work).  The notice
states ONLY what the owner must change; it deliberately does not explain Pantheon's migration,
Orange-to-Orange, or Pantheon-versus-our-Cloudflare.

Every hostname and address here is remotely derived -> html.escape on every text node.  The one
href is the constant DOCS_URL, so sc.escape_url is not needed; if a per-domain link is ever added
it MUST go through sc.escape_url (the check/dns/notices.py convention).

The HTML table reuses the markup the core's existing notices use (pantheon-sitehealth-emails
:2521), so it inherits email_template.html's mobile-stacking styles and survives the Emogrifier +
!important passes.  Plaintext uses an indented block per domain rather than an ASCII table --
three addresses per row do not survive a text table legibly.

ONE row per affected FQDN: the addresses are Pantheon's per-domain required records, so they are
correct for the DNS record and the Cloudflare record alike (SPEC §4.1).
"""
import html

from .model import Finding    # noqa: F401  -- re-exported for callers/tests; model is pure

DOCS_URL = "https://docs.pantheon.io/guides/global-cdn/global-cdn-beta#setup"

INTRO_HTML = (
    '<p>Pantheon is <a href="{docs}">making a change to their CDN</a>, from the legacy '
    "Pantheon GCDN (Fastly) to the new Pantheon GCDN Beta (Pantheon Cloudflare).  Before "
    "<strong>{site}</strong> can move to the new GCDN Beta, each of its custom domains must "
    "resolve through A and AAAA records instead of a CNAME record.</p>\n"
    "<p>These domains for <strong>{site}</strong> still use a CNAME record:</p>")

INTRO_TEXT = (
    "Pantheon is making a change to their CDN <{docs}>, from the legacy Pantheon\n"
    "GCDN (Fastly) to the new Pantheon GCDN Beta (Pantheon Cloudflare).  Before\n"
    "{site} can move to the new GCDN Beta, each of its custom domains must resolve\n"
    "through A and AAAA records instead of a CNAME record.\n\n"
    "These domains for {site} still use a CNAME record:")

MAINTENANCE_HTML = (
    "<p>ITS will make these changes for you during an upcoming maintenance, which we will "
    "schedule and announce.  If you would rather make the changes yourself before then, you "
    "are welcome to.</p>")

MAINTENANCE_TEXT = (
    "ITS will make these changes for you during an upcoming maintenance, which we\n"
    "will schedule and announce.  If you would rather make the changes yourself\n"
    "before then, you are welcome to.")

SELF_SERVE_HTML = (
    "<p>Please replace each CNAME record above with the A and AAAA records shown.</p>")

SELF_SERVE_TEXT = (
    "Please replace each CNAME record above with the A and AAAA records shown.")


def _cloudflare_label(umich: bool) -> str:
    return "U-M Cloudflare" if umich else "our (non-Pantheon) Cloudflare"


def where_label(where: str, *, umich: bool) -> str:
    """The 'Change it in' cell.  `where` is a Finding's machine value (SPEC §8).

    Raises ValueError on anything else: a silent fall-through would print a wrong instruction to
    a site owner, which is the class of failure this feature exists to prevent.
    """
    if where == "dns":
        return "DNS"
    if where == "cloudflare":
        return _cloudflare_label(umich)
    if where == "both":
        return f"DNS and {_cloudflare_label(umich)}"
    raise ValueError(f"unknown Finding.where: {where!r}")


def _records(finding) -> list:
    """[(rrtype, value)] -- Pantheon's required records for this domain, in Pantheon's order.

    Normally A/AAAA.  A CNAME appears only for a site already on the new GCDN Beta (F14), whose
    domain:dns answer has no A/AAAA at all -- that is an ANSWER, and it must be shown rather than
    reported as "unavailable".
    """
    return ([("A", ip) for ip in finding.a]
            + [("AAAA", ip) for ip in finding.aaaa]
            + [("CNAME", name) for name in finding.cname])


def _records_html(finding, umich: bool) -> str:
    records = _records(finding)
    if not records:      # F4: no answer at all
        return "unavailable &mdash; please contact us" if umich else "unavailable"
    return "<br>".join(f"{rrtype} {html.escape(value)}" for rrtype, value in records)


def _records_text(finding, umich: bool) -> str:
    records = _records(finding)
    if not records:
        return "      unavailable -- please contact us" if umich else "      unavailable"
    return "\n".join(f"      {rrtype:<6s} {value}" for rrtype, value in records)


def cdn_change_notice(site_name: str, findings: list, *, umich: bool, before_cutoff: bool) -> dict:
    """ONE info notice covering every affected custom domain for the site."""
    site = html.escape(site_name)
    rows = "\n".join(
        f"<tr><td>{html.escape(f.fqdn)}</td>"
        f"<td>{html.escape(where_label(f.where, umich=umich))}</td>"
        f"<td>{_records_html(f, umich)}</td></tr>"
        for f in findings)
    blocks = "\n\n".join(
        f"  {f.fqdn}  (change it in {where_label(f.where, umich=umich)})\n"
        f"{_records_text(f, umich)}"
        for f in findings)

    closing_html = MAINTENANCE_HTML if (umich and before_cutoff) else SELF_SERVE_HTML
    closing_text = MAINTENANCE_TEXT if (umich and before_cutoff) else SELF_SERVE_TEXT

    message = (
        f"{INTRO_HTML.format(docs=DOCS_URL, site=site)}\n"
        '<div class="container">\n'
        '<table class="responsive-table site-updates">\n'
        '<thead><th class="rt-plan">Domain</th><th class="rt-plan">Change it in</th>'
        '<th class="rt-plan">Replace the CNAME record with</th></thead>\n'
        f"<tbody>\n{rows}\n</tbody>\n"
        "</table>\n"
        "</div>\n"
        f"{closing_html}")

    text = (
        f"{INTRO_TEXT.format(docs=DOCS_URL, site=site_name)}\n\n"
        f"{blocks}\n\n"
        f"{closing_text}\n")

    return {
        "type": "info",
        "csv": f"{site_name},pantheon-cdn-change," + ",".join(f.fqdn for f in findings),
        "short": "Pantheon CDN change: replace CNAME records",
        "message": message,
        "text": text,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./run-tests --fast tests/unit/test_pantheon_cdn_change_notices.py`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add check/pantheon_cdn_change/notices.py tests/unit/test_pantheon_cdn_change_notices.py
git commit -m "feat(pantheon-cdn-change): owner-facing notice (U-M / generic, pre / post cutoff)"
```

---

### Task 9: `hook.py` + `__init__.py` — wire the check into the pipeline

**Files:**
- Create: `check/pantheon_cdn_change/hook.py`
- Modify: `check/pantheon_cdn_change/__init__.py` (replace the Task-5 placeholder)
- Modify: `pantheon-sitehealth-emails` (delete the now-implemented TODO at 1655-1657)
- Test: `tests/integration/test_check_pantheon_cdn_change.py`

**Interfaces:**
- Consumes: `find_findings` (Task 7), `cdn_change_notice` (Task 8), `sc.cloudflare_enabled()`,
  `sc.umich_enabled()`, `sc.plugin_context["plugin.cloudflare"]["proxied_fqdns"]`,
  `site_context["custom_domains"]`, `site_context["site"]["name"]` and `["site"]["id"]` (the
  `site_post_dns` data contract). **`site["id"]` is a UUID** — it is what the core builds
  `live_site` from (`pantheon-sitehealth-emails:1540`) and what `domain:dns` needs; `["name"]` is
  what operator messages print.
- Produces: `UMICH_MAINTENANCE_CUTOFF`, `today()`, `check_pantheon_cdn_change(site_context)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/integration/test_check_pantheon_cdn_change.py`:

```python
import datetime
import re

import pytest

from helpers.checkload import load_check_package
from helpers.dnsfake import patch_resolve, recording_console

pytestmark = pytest.mark.integration

FQDN_RE = re.compile(r"^_?[a-z0-9-]+\.[a-z0-9.-]+$", re.IGNORECASE)

# Production site ids are UUIDs (pantheon-sitehealth-emails:1540 builds `<id>.live`); use one, so
# the tests do not bake in a false mental model.
SITE_ID = "9cf2c790-c7b8-4f2f-a6f1-27385b8f958e"
SITE_NAME = "bus-occb"

ZONE = {("occb.bus.umich.edu", "CNAME"): ["live-bus-occb.pantheonsite.io."]}
DNS_ROWS = [
    {"domain": "occb.bus.umich.edu", "type": "A", "value": "23.185.0.4"},
    {"domain": "occb.bus.umich.edu", "type": "AAAA", "value": "2620:12a:8000::4"},
    {"domain": "occb.bus.umich.edu", "type": "AAAA", "value": "2620:12a:8001::4"},
]


@pytest.fixture
def check(psh, reset_sc, request, monkeypatch):
    patch_resolve(monkeypatch, ZONE)
    monkeypatch.setattr(reset_sc, "cloudflare_enabled", lambda: True)
    monkeypatch.setattr(reset_sc, "umich_enabled", lambda: True)
    monkeypatch.setattr(reset_sc, "fqdn_re", FQDN_RE)
    monkeypatch.setattr(reset_sc, "terminus", lambda *args: (DNS_ROWS, "", False))
    reset_sc.plugin_context["plugin.cloudflare"] = {"proxied_fqdns": {}}
    return load_check_package(psh, "pantheon_cdn_change", "pcc_init_probe", request)


def _ctx(reset_sc, custom_domains):
    ctx = reset_sc.SiteContext({"name": SITE_NAME, "id": SITE_ID})
    ctx["custom_domains"] = custom_domains
    return ctx


def test_registers_one_hook_unconditionally(psh, reset_sc, request):
    reset_sc.config = {}                       # no [Cloudflare], no [UMich]
    load_check_package(psh, "pantheon_cdn_change", "pcc_reg_probe", request)
    assert [h["name"] for h in reset_sc.hooks["site_post_dns"]] == \
        ["check.pantheon_cdn_change.hook.check_pantheon_cdn_change"]


def test_hook_adds_exactly_one_notice(check, reset_sc, monkeypatch):
    monkeypatch.setattr(check.hook, "today", lambda: datetime.date(2026, 8, 1))
    ctx = _ctx(reset_sc, ["occb.bus.umich.edu"])
    check.hook.check_pantheon_cdn_change(ctx)
    assert len(ctx["notices"]) == 1
    notice = ctx["notices"][0]
    assert notice["type"] == "info"
    assert notice["csv"] == "bus-occb,pantheon-cdn-change,occb.bus.umich.edu"
    assert notice["icon"] == reset_sc.icon["info"]      # add_notice fills the magnifying glass
    assert "23.185.0.4" in notice["message"]           # Pantheon's answer reached the notice
    assert "ITS will make these changes for you" in notice["message"]   # U-M, before the cutoff


def test_terminus_is_called_with_the_live_environment_of_the_site_id(check, reset_sc, monkeypatch):
    # The command takes the UUID, not the site name (core: live_site = site["id"] + ".live").
    calls = []
    monkeypatch.setattr(reset_sc, "terminus",
                        lambda *args: (calls.append(args), (DNS_ROWS, "", False))[1])
    monkeypatch.setattr(check.hook, "today", lambda: datetime.date(2026, 8, 1))
    check.hook.check_pantheon_cdn_change(_ctx(reset_sc, ["occb.bus.umich.edu"]))
    assert calls == [("domain:dns", f"{SITE_ID}.live")]


def test_on_or_after_cutoff_umich_gets_the_generic_instruction(check, reset_sc, monkeypatch):
    monkeypatch.setattr(check.hook, "today", lambda: datetime.date(2026, 9, 15))  # cutoff DAY
    ctx = _ctx(reset_sc, ["occb.bus.umich.edu"])
    check.hook.check_pantheon_cdn_change(ctx)
    assert "ITS will make these changes" not in ctx["notices"][0]["message"]
    assert "Please replace each CNAME record above" in ctx["notices"][0]["message"]


def test_no_custom_domains_no_notice(check, reset_sc, monkeypatch):
    monkeypatch.setattr(check.hook, "today", lambda: datetime.date(2026, 8, 1))
    check.hook.check_pantheon_cdn_change(_ctx(reset_sc, []))
    assert _ctx(reset_sc, [])["notices"] == []


def test_clean_site_no_notice(check, reset_sc, monkeypatch):
    monkeypatch.setattr(check.hook, "today", lambda: datetime.date(2026, 8, 1))
    ctx = _ctx(reset_sc, ["clean.example.org"])        # no CNAME in ZONE -> NoAnswer -> no hit
    check.hook.check_pantheon_cdn_change(ctx)
    assert ctx["notices"] == []


def test_missing_plugin_context_does_not_raise(check, reset_sc, monkeypatch):
    # F6: [Cloudflare] enabled but the plugin bag absent.
    monkeypatch.setattr(check.hook, "today", lambda: datetime.date(2026, 8, 1))
    reset_sc.plugin_context.pop("plugin.cloudflare", None)
    ctx = _ctx(reset_sc, ["occb.bus.umich.edu"])
    check.hook.check_pantheon_cdn_change(ctx)
    assert len(ctx["notices"]) == 1                    # the DNS source still works


def test_findings_are_announced_at_verbosity_zero(check, reset_sc, monkeypatch):
    # Observability (SPEC §9): -notices.csv is only written under --all, so on a single-site run
    # the console is the operator's ONLY channel.  The message names the SITE, not the UUID.
    console = recording_console(monkeypatch, reset_sc)
    monkeypatch.setattr(check.hook, "today", lambda: datetime.date(2026, 8, 1))
    check.hook.check_pantheon_cdn_change(_ctx(reset_sc, ["occb.bus.umich.edu"]))
    out = console.export_text()
    assert "ATTENTION" in out and SITE_NAME in out
    assert SITE_ID not in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./run-tests --fast tests/integration/test_check_pantheon_cdn_change.py`
Expected: FAIL — `check/pantheon_cdn_change/hook.py` does not exist.

- [ ] **Step 3: Write `hook.py`**

```python
"""site_post_dns hook for the Pantheon CDN-change check.

Owns the two run-time decisions the pure modules cannot make: which detection sources are
available (sc.cloudflare_enabled + the plugin.cloudflare bag), and which copy variant applies
(sc.umich_enabled + the cutoff).

There is deliberately NO fqdns.json staleness warning here.  The plugin already warns, once per
run, exactly when the file is stale and the run will consume it (plugin/cloudflare/fqdns.py
:219-223), and a missing file on a consuming run is auto-refreshed (decide_fqdns_update:64).  A
per-site copy of that warning -- and the module-level "already warned" flag it would need -- was
designed, reviewed, and cut.  Do not reintroduce it.
"""
import datetime

from rich.markup import escape as rich_escape

import script_context as sc

from .detect import find_findings
from .notices import cdn_change_notice

# The ONE dated constant in this feature.  TWO future edits are expected:
#   (a) once the ITS maintenance is scheduled, change this date to the real one;
#   (b) once that date has passed, DELETE this constant, today(), the before_cutoff argument,
#       and the U-M branch of cdn_change_notice() -- leaving only the generic copy.
# The date itself is NEVER shown to site owners; it only selects the copy variant.
UMICH_MAINTENANCE_CUTOFF = datetime.date(2026, 9, 15)


def today() -> datetime.date:
    """The one date seam: tests monkeypatch hook.today so the copy variant is deterministic."""
    return datetime.date.today()


def check_pantheon_cdn_change(site_context) -> None:
    site = site_context["site"]
    site_name = site["name"]
    # site["id"] is a UUID -- it is what terminus needs (core builds live_site the same way,
    # pantheon-sitehealth-emails:1540).  site["name"] is what the operator reads.
    site_id = site["id"]

    cloudflare_on = sc.cloudflare_enabled()
    # .get chains: a run without the Cloudflare plugin bag must not KeyError (F6).
    proxied_fqdns = {}
    if cloudflare_on:
        proxied_fqdns = sc.plugin_context.get("plugin.cloudflare", {}).get("proxied_fqdns") or {}

    findings = find_findings(
        site_id, site_name, site_context["custom_domains"], proxied_fqdns, cloudflare_on)
    if not findings:
        return

    # Verbosity 0 (SPEC §9): -notices.csv is only written under --all, so on a single-site run the
    # console is the operator's only channel.  Every other DNS/Cloudflare problem in this codebase
    # announces itself here; this one does too.  rich_escape even though Pantheon site names are
    # [a-z0-9-]: the rule is "escape every remote string", so nobody has to re-derive that.
    sc.console.print(
        f":exclamation: [bold red] ATTENTION: {rich_escape(str(site_name))} has "
        f"{len(findings)} custom domain(s) still CNAME'd to the legacy Pantheon GCDN")

    site_context.add_notice(cdn_change_notice(
        site_name,
        findings,
        umich=sc.umich_enabled(),
        before_cutoff=today() < UMICH_MAINTENANCE_CUTOFF,
    ))
```

- [ ] **Step 4: Replace `__init__.py`**

```python
"""Pantheon CDN-change check (site_post_dns): custom domains that still reach the legacy
Pantheon GCDN (Fastly) through a CNAME record, in public DNS or in Cloudflare.

TEMPORARY.  Delete this whole package (`git rm -r check/pantheon_cdn_change` plus its tests)
once Pantheon's migration to the new GCDN Beta is complete.  See docs/pantheon-cdn-change.md.

Registers UNCONDITIONALLY (like check/dns): every site this tool reports on is a Pantheon site,
so the check always applies.  The Cloudflare-origins source self-gates on sc.cloudflare_enabled(),
so an institution with no Cloudflare still gets the public-DNS half.
"""
import script_context as sc

from .hook import check_pantheon_cdn_change

sc.add_hook('site_post_dns',
            {'name': 'check.pantheon_cdn_change.hook.check_pantheon_cdn_change',
             'func': check_pantheon_cdn_change})
```

- [ ] **Step 5: Delete the obsolete core TODO**

In `pantheon-sitehealth-emails`, remove these three comment lines (currently 1655–1657) — this
check now implements them. Keep the `# Query Pantheon for the site's domains` line above them:

```python
        # TODO: check domains for site
        #   - In Cloudflare, do they all point at the correct Pantheon IPs?
        #   - If not in Cloudflare, are they all A / AAAA records?  We need to get rid of CNAMEs to live-${site_name}.pantheonsite.io.
```

- [ ] **Step 6: Run the tests**

Run: `./run-tests --fast tests/integration/test_check_pantheon_cdn_change.py`
Expected: all PASS.

Run: `./run-tests --fast` then `git status --short tests/e2e/`
Expected: the whole offline suite passes and **no golden is modified** (the three existing
`domain:list` fixtures have no custom domains, so the check emits nothing). If a golden changed,
STOP and fix the code — never the golden.

- [ ] **Step 7: Commit**

```bash
git add check/pantheon_cdn_change/ pantheon-sitehealth-emails \
        tests/integration/test_check_pantheon_cdn_change.py
git commit -m "feat(pantheon-cdn-change): register the site_post_dns hook; drop the obsolete TODO"
```

---

### Task 10: Render the notice through the REAL template

**Files:**
- Test: `tests/integration/test_pantheon_cdn_change_notice_render.py`
- Create (generated): `tests/integration/__snapshots__/test_pantheon_cdn_change_notice_render.ambr`

This is where the **U-M before-cutoff copy** — the variant production will send for the next two
months — is pinned. The 4th golden (Task 11) cannot do it: `minimal.toml` has no `[UMich]`
section, so it renders the generic copy.

- [ ] **Step 1: Write the test**

```python
"""Syrupy snapshots of the CDN-change notice as rendered content.

Built by the real notices.py, added through the real SiteContext.add_notice, and pushed through
the real email_template.html Jinja render in-process -- the test_cachecheck_notice_render.py
precedent.  A dict-level snapshot alone would not prove the table survives the template.

This file pins the U-M copy variants; the 4th e2e golden pins the GENERIC one (its config has no
[UMich] section).  Between them, every variant that can be sent is frozen.
"""
from pathlib import Path

import pytest
from jinja2 import Template

from helpers.checkload import load_check_module

pytestmark = pytest.mark.integration

SITE = "bus-occb"


@pytest.fixture
def notices(psh, reset_sc, request):
    return load_check_module(
        psh, "pantheon_cdn_change", "notices", "pcc_render_probe", request)


@pytest.fixture
def findings(notices):
    F = notices.Finding
    return [
        F("occb.bus.umich.edu", "dns", "live-bus-occb.pantheonsite.io",
          ["23.185.0.4"], ["2620:12a:8000::4", "2620:12a:8001::4"], []),
        F("backstage.its.umich.edu", "cloudflare", "live-its-backstage.pantheonsite.io",
          ["23.185.0.2"], ["2620:12a:8000::2", "2620:12a:8001::2"], []),
        F("both.example.org", "both", "live-x.pantheonsite.io", ["23.185.0.9"], [], []),
        # F14: an already-migrated site -- Pantheon requires a CNAME, not addresses.
        F("migrated.example.org", "dns", "live-m.pantheonsite.io", [], [],
          ["fe.cfp2c.edge.pantheon.io"]),
        # F4: domain:dns had no row at all for this one -> "unavailable", still reported.
        F("unresolvable.example.org", "dns", "live-y.pantheonsite.io", [], [], []),
    ]


@pytest.mark.parametrize(
    "umich,before_cutoff",
    [(True, True), (True, False), (False, False)],
    ids=["umich-before-cutoff", "umich-after-cutoff", "generic"])
def test_notice_message_and_text_snapshot(
        notices, findings, reset_sc, snapshot, umich, before_cutoff):
    built = notices.cdn_change_notice(SITE, findings, umich=umich, before_cutoff=before_cutoff)
    ctx = reset_sc.SiteContext({"name": SITE})
    ctx.add_notice(dict(built))
    notice = ctx["notices"][0]
    assert notice["icon"] == "&#x1F50E;"      # magnifying glass, from the info type default
    assert notice["message"] == snapshot
    assert notice["text"] == snapshot         # the bespoke plaintext, NOT html2text output


def test_notice_renders_through_the_real_template(psh, notices, findings, reset_sc):
    built = notices.cdn_change_notice(SITE, findings, umich=True, before_cutoff=True)
    ctx = reset_sc.SiteContext({"name": SITE})
    ctx.add_notice(dict(built))
    template = Template((Path(psh.__file__).parent / "email_template.html").read_text())
    html_body = template.render(site_name=SITE, notices=ctx["notices"], sections=[], news=[])
    assert 'class="responsive-table site-updates"' in html_body     # the table survived
    assert "occb.bus.umich.edu" in html_body and "23.185.0.4" in html_body
    assert notices.DOCS_URL in html_body
    assert "unavailable" in html_body                               # the F4 row survived
    assert "CNAME fe.cfp2c.edge.pantheon.io" in html_body           # the F14 row survived


def test_injected_markup_cannot_escape_the_table_cell(notices, reset_sc):
    F = notices.Finding
    evil = 'a.example.org"><script>alert(1)</script>'
    built = notices.cdn_change_notice(
        SITE, [F(evil, "dns", "live-x.pantheonsite.io", ["1.2.3.4"], [], [])],
        umich=False, before_cutoff=False)
    assert "<script>" not in built["message"]
    assert "&lt;script&gt;" in built["message"]
```

- [ ] **Step 2: Run the test — the snapshots do not exist yet**

Run: `./run-tests --fast tests/integration/test_pantheon_cdn_change_notice_render.py`
Expected: the two non-snapshot tests PASS; the three snapshot tests FAIL ("snapshot does not
exist").

- [ ] **Step 3: Create the snapshots and READ the diff**

Run: `./run-tests --update-goldens tests/integration/test_pantheon_cdn_change_notice_render.py`
Then: `git diff tests/integration/__snapshots__/`

Read every line against SPEC §8. Confirm: `umich-before-cutoff` promises the ITS maintenance;
`umich-after-cutoff` and `generic` do not; `generic` contains no `U-M` and no `ITS`;
`unresolvable.example.org` reads `unavailable`; `migrated.example.org` reads `CNAME
fe.cfp2c.edge.pantheon.io` and NOT "unavailable" (F14); the table markup is `responsive-table
site-updates`; every FQDN appears exactly once.

Run: `./run-tests --fast tests/integration/test_pantheon_cdn_change_notice_render.py`
Expected: all PASS against the committed snapshot.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_pantheon_cdn_change_notice_render.py \
        tests/integration/__snapshots__/
git commit -m "test(pantheon-cdn-change): snapshot the notice through the real email template"
```

---

### Task 11: The 4th e2e golden — drive the check through `main()`

Every test so far hand-builds a `SiteContext`. Nothing proves that **`main()` populates
`custom_domains` with the strings the hook consumes**, that the `domain:dns` call is really wired
through `terminus()`, or that the notice survives Jinja → Emogrifier → the `!important` pass →
the `.eml`. The three existing goldens can only prove the check stays *silent*.

**Two scope limits, stated rather than hidden:**
1. **Source ① only.** `[Cloudflare]` stays disabled: enabling it makes a setup hook call the live
   Cloudflare API (`plugin/cloudflare/ips.py:17`, `cloudflare.ips.list()`), which the offline
   tier forbids. Source ② keeps its unit + integration coverage (Tasks 7 and 9). *(If someone
   later wants source ② here, the `sitecustomize` shim below could also stub the `cloudflare`
   SDK — deliberately out of scope now.)*
2. **Generic copy only.** `tests/fixtures/config/minimal.toml` has **no `[UMich]` section**, so
   `umich_enabled()` is False and this golden pins the **generic** notice. The U-M copy is pinned
   by Task 10's snapshots. The test asserts which variant it is, so this cannot rot silently.

**Files:**
- Create: `tests/shims/dnsshim/sitecustomize.py`
- Create: `tests/fixtures/terminus-cdnchange/` (copy of the WordPress fixtures + an edited
  `domain:list` + a new `domain:dns`)
- Modify: `tests/conftest.py` — `build_rendered_report(work, *, site=…, site_id=…,
  fixtures_dir=None, extra_env=None)` gains `extra_env` and forwards it to `run_program`. The
  golden needs a subprocess env; hand-rolling a private copy of `build_rendered_report` in the
  test file would duplicate the create-tables/seed/render sequence for one keyword argument.
- Create: `tests/e2e/test_golden_cdn_change.py`
- Create (generated): `tests/e2e/__snapshots__/test_golden_cdn_change.ambr`

**Why a subprocess shim:** goldens run the program via `run_program()` (`tests/conftest.py:394`,
`subprocess.run([str(PROGRAM), *args])`), so an in-process `monkeypatch.setattr(dns_classify,
"resolve", …)` cannot reach it. Python imports `sitecustomize` at interpreter startup if it is
importable, so putting a directory on `PYTHONPATH` replaces `dns.resolver.resolve` **before** the
program imports anything. `dns_classify.resolve` calls `dns.resolver.resolve(...)` by attribute at
call time (`dns_classify.py:19`), so patching the module attribute intercepts every lookup. No
production code learns about tests. (Verified: no `sitecustomize` is currently importable in this
venv, so nothing is shadowed.)

- [ ] **Step 1: Write the DNS shim**

Create `tests/shims/dnsshim/sitecustomize.py`:

```python
"""Offline DNS for the subprocess-based e2e goldens.

run_program() launches the real program in a subprocess, so an in-process monkeypatch of
dns_classify.resolve cannot reach it.  Python imports `sitecustomize` at interpreter startup if it
is importable, so putting this directory on PYTHONPATH replaces dnspython's resolver BEFORE the
program imports anything -- the same philosophy as the PATH-based fake `terminus` shim.

Zone file (JSON, named by the DNS_SHIM_ZONE env var):

    { "name|RRTYPE": ["value", ...], ... }
    e.g. {"x.example.edu|CNAME": ["live-x.pantheonsite.io."]}

An absent key raises NoAnswer -- the definitive "no such record" answer.  With no DNS_SHIM_ZONE
set this module does nothing, so the directory can sit on PYTHONPATH harmlessly (the terminus
shim subprocess inherits PYTHONPATH too, and must not break).
"""
import json
import os

_zone_path = os.environ.get("DNS_SHIM_ZONE")
if _zone_path:
    import dns.resolver

    with open(_zone_path) as _f:
        _ZONE = json.load(_f)

    class _Rdata:
        def __init__(self, value):
            self.target = value        # CNAME answers read .target
            self.address = value       # A/AAAA answers read .address

    def _fake_resolve(name, rrtype, *args, **kwargs):
        key = f"{str(name).rstrip('.').lower()}|{rrtype}"
        values = _ZONE.get(key)
        if values is None:
            raise dns.resolver.NoAnswer
        return [_Rdata(v) for v in values]

    dns.resolver.resolve = _fake_resolve
```

- [ ] **Step 2: Build the fixtures directory**

```bash
cp -r tests/fixtures/terminus tests/fixtures/terminus-cdnchange
```

The shim keys each fixture by `sha1(json.dumps(argv-without-ignored-flags))[:16]`
(`tests/shims/terminus:37-44`), and each fixture's payload is a **JSON string inside the
`"stdout"` field** — not raw JSON. Two edits:

**(a) `domain:list`** — find the fixture whose `argv` is the `domain:list` call and add a custom
domain to the domains dict encoded in its `"stdout"` string, keeping the existing platform
entry:

```json
"cdn-change.example.edu": {"id": "cdn-change.example.edu", "type": "custom", "primary": true, "status": "ok"}
```

That fixture also carries `"_scrubbed": "custom domains removed so replay makes no live DNS
calls; platform domain kept"`. In this copy that note is now false — replace it with:
`"_scrubbed": "one synthetic custom domain ADDED for the CDN-change golden; DNS is shimmed (tests/shims/dnsshim)"`.

**(b) `domain:dns`** — a new fixture. Compute its filename with the shim's own key function:

```bash
python - <<'PY'
import hashlib, json
# The program passes the site UUID, NOT the site name: live_site = site["id"] + ".live"
# (pantheon-sitehealth-emails:1540).  Confirm the UUID against the EXISTING domain:list
# fixture's "argv" field in tests/fixtures/terminus/ -- do not guess it.
site_id = "9cf2c790-c7b8-4f2f-a6f1-27385b8f958e"      # == conftest.E2E_SITE_ID
argv = ["--no-ansi", "--no-interaction", "domain:dns", site_id + ".live", "--format=json"]
ignored = {"--no-ansi", "--no-interaction"}          # tests/shims/terminus:_IGNORED_FLAGS
key_args = [a for a in argv if a not in ignored]
print(hashlib.sha1(json.dumps(key_args, ensure_ascii=False).encode()).hexdigest()[:16])
PY
```

**Verify the argv against the shim before trusting it** — read `tests/shims/terminus` for
`_IGNORED_FLAGS` and confirm how `run_terminus()` assembles the command
(`pantheon-sitehealth-emails:273`) plus where `--format=json` is appended. Then write
`tests/fixtures/terminus-cdnchange/<key>.json` in the same shape as the other fixtures, whose
`"stdout"` is the JSON-encoded string of:

```json
[{"domain": "cdn-change.example.edu", "type": "A", "value": "23.185.0.4", "detected_value": "", "status": "action_required", "status_message": "Add this required record"},
 {"domain": "cdn-change.example.edu", "type": "AAAA", "value": "2620:12a:8000::4", "detected_value": "", "status": "action_required", "status_message": "Add this required record"},
 {"domain": "cdn-change.example.edu", "type": "AAAA", "value": "2620:12a:8001::4", "detected_value": "", "status": "action_required", "status_message": "Add this required record"},
 {"domain": "cdn-change.example.edu", "type": "CNAME", "value": "", "detected_value": "live-its-wws-test1.pantheonsite.io", "status": "action_required", "status_message": "Remove this detected record"}]
```

**This is the single most likely thing to go wrong in this task.** A wrong key means the shim
finds no fixture, `terminus()` returns `None`, `required_records` returns `{}`, and the golden
renders "unavailable" — a *plausible-looking* golden that silently tests the wrong thing. The
shim reports the expected key and argv when a fixture is missing (`tests/shims/terminus:76-80`);
use its message rather than guessing.

- [ ] **Step 3: Write the golden test**

Create `tests/e2e/test_golden_cdn_change.py`:

```python
"""4th golden: the Pantheon CDN-change check driven through the REAL main().

The other three goldens have platform-only domain:list fixtures, so they can only prove this
check stays SILENT.  This one gives its-wws-test1 a CUSTOM domain that is CNAME'd to the legacy
Pantheon GCDN, and shims DNS in the subprocess (tests/shims/dnsshim), so the whole path runs:

    main() -> terminus domain:list -> dns_classify.classify_domains -> stuff_dns_contract
           -> invoke_hooks("site_post_dns") -> check.pantheon_cdn_change
           -> terminus domain:dns (Pantheon's required records) -> notice
           -> email_template.html -> inline-styles.php (Emogrifier) -> !important pass -> .eml

SCOPE (deliberate, see PLAN Task 11):
  * source (1) (public DNS) only -- [Cloudflare] stays disabled because enabling it makes
    plugin/cloudflare/ips.py call the live Cloudflare API.  Source (2) is covered by
    tests/unit/test_pantheon_cdn_change_detect.py and tests/integration/test_check_pantheon_cdn_change.py.
  * the GENERIC copy -- minimal.toml has no [UMich] section.  The U-M copy is pinned by
    tests/integration/test_pantheon_cdn_change_notice_render.py.
"""
import email
import email.policy
import json

import pytest

from conftest import (
    E2E_DATE,
    E2E_SITE,
    E2E_SITE_ID,
    E2E_SMTP_USERNAME,
    MINIMAL_CONFIG,
    REPO_ROOT,
    make_workdir,
    run_program,
    seed_traffic,
)

pytestmark = pytest.mark.e2e

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "terminus-cdnchange"
DNS_SHIM = REPO_ROOT / "tests" / "shims" / "dnsshim"

CUSTOM = "cdn-change.example.edu"
TARGET = "live-its-wws-test1.pantheonsite.io"

# The custom domain is CNAME'd to the legacy GCDN (the occb.bus.umich.edu shape) and resolves to
# the Pantheon edge addresses -- so classify_domains sees real addresses (no not-in-dns alert)
# while the CDN-change check sees the CNAME.
ZONE = {
    f"{CUSTOM}|CNAME": [f"{TARGET}."],
    f"{CUSTOM}|A": ["23.185.0.4"],
    f"{CUSTOM}|AAAA": ["2620:12a:8000::4", "2620:12a:8001::4"],
}


@pytest.fixture(scope="module")
def cdn_change_render(tmp_path_factory):
    work = make_workdir(tmp_path_factory.mktemp("cdnchange"))
    zone_file = work / "zone.json"
    zone_file.write_text(json.dumps(ZONE))

    run_program(["--create-tables", "--config", MINIMAL_CONFIG], cwd=work,
                fixtures_dir=FIXTURES)
    seed_traffic(work / "test.db", site_id=E2E_SITE_ID)
    proc = run_program(
        [E2E_SITE, "--date", E2E_DATE, "--smtp-username", E2E_SMTP_USERNAME,
         "--config", MINIMAL_CONFIG],
        cwd=work,
        fixtures_dir=FIXTURES,
        extra_env={"PYTHONPATH": str(DNS_SHIM), "DNS_SHIM_ZONE": str(zone_file)},
    )
    build = work / "build"
    return {"proc": proc, "html": build / f"{E2E_SITE}.html",
            "txt": build / f"{E2E_SITE}.txt", "eml": build / f"{E2E_SITE}.eml",
            "inline2": build / f"{E2E_SITE}-inline2.html"}


def test_render_succeeds(cdn_change_render):
    assert cdn_change_render["proc"].returncode == 0, cdn_change_render["proc"].stderr
    assert "Traceback" not in cdn_change_render["proc"].stderr


def test_main_wires_custom_domains_into_the_check(cdn_change_render):
    # The thing NO other test can prove: main() feeds the hook the domain strings it expects, the
    # domain:dns call goes through terminus(), and the notice reaches the rendered report with
    # PANTHEON's replacement addresses.
    html = cdn_change_render["html"].read_text()
    assert CUSTOM in html
    assert "23.185.0.4" in html
    assert "2620:12a:8000::4" in html and "2620:12a:8001::4" in html
    assert "making a change to their CDN" in html


def test_golden_pins_the_generic_copy(cdn_change_render):
    # minimal.toml has no [UMich] section -> umich_enabled() is False.  Assert the variant
    # explicitly so the distinction cannot rot into "we thought we were testing the U-M copy".
    html = cdn_change_render["html"].read_text()
    assert "Please replace each CNAME record above" in html
    assert "ITS will make these changes" not in html


def test_notice_survives_the_inline_css_pipeline(cdn_change_render):
    # build/<site>-inline2.html is what actually gets attached to the message.
    inline2 = cdn_change_render["inline2"].read_text()
    assert CUSTOM in inline2 and "23.185.0.4" in inline2


def test_notice_reaches_the_eml(cdn_change_render):
    msg = email.message_from_bytes(cdn_change_render["eml"].read_bytes(),
                                   policy=email.policy.default)
    bodies = [p.get_content() for p in msg.walk() if p.get_content_maintype() == "text"]
    assert any(CUSTOM in b for b in bodies)


def test_html_matches_golden(cdn_change_render, normalize_html, snapshot):
    assert normalize_html(cdn_change_render["html"].read_text()) == snapshot


def test_txt_matches_golden(cdn_change_render, snapshot):
    assert cdn_change_render["txt"].read_text() == snapshot
```

- [ ] **Step 4: Run it, create the golden, and READ the golden**

Run: `./run-tests --fast tests/e2e/test_golden_cdn_change.py`
Expected: the non-snapshot tests PASS; the two snapshot tests FAIL ("snapshot does not exist").

Run: `./run-tests --update-goldens tests/e2e/test_golden_cdn_change.py`

Read the new `.ambr` in full. Confirm, explicitly:
- the CDN-change notice appears **once**, with the magnifying-glass icon, the table,
  `cdn-change.example.edu`, `DNS` in the "Change it in" cell, and the three addresses;
- it is the **generic** copy ("Please replace each CNAME record above", no "ITS");
- **three expected deltas versus the other goldens**, all correct: the `no-domains` alert is
  **gone** (it fires on `len(custom_domains) == 0`, `pantheon-sitehealth-emails:1686-1704`); the
  "Main URL" / `site_url` is now **populated** (`:1773-1774`); and the traffic chart's title now
  carries that URL (`:3240-3241`), so the chart PNG bytes differ from the other goldens' (not
  snapshotted — the CIDs are normalized — but do not be alarmed by it).

Deltas that MUST NOT appear (verified: they are Cloudflare-gated or need >1 custom domain, and
this golden has `[Cloudflare]` disabled and one domain): the favicon / "put this site behind
Cloudflare" notice, and `no-primary-domain`. If either shows up, something is wrong — do not
accept the golden.

A golden you have not read is not a test.

Run: `./run-tests --fast tests/e2e/test_golden_cdn_change.py`
Expected: PASS.

- [ ] **Step 5: Confirm the other three goldens are byte-identical**

Run: `./run-tests --fast`
Run: `git status --short tests/e2e/__snapshots__/`
Expected: only the NEW `test_golden_cdn_change.ambr` is added; the other three `.ambr` files are
unmodified.

- [ ] **Step 6: Commit**

```bash
git add tests/shims/dnsshim/ tests/fixtures/terminus-cdnchange/ \
        tests/e2e/test_golden_cdn_change.py tests/e2e/__snapshots__/
git commit -m "test(pantheon-cdn-change): 4th golden -- drive the check through the real main()"
```

---

### Task 12: Documentation, live verification, and the closing audit

**Files:**
- Create: `docs/pantheon-cdn-change.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Write `docs/pantheon-cdn-change.md`**

Cover, with no placeholders:
- What the check reports and why (Pantheon's move from the legacy Pantheon GCDN (Fastly) to the
  new Pantheon GCDN Beta (Pantheon Cloudflare)), with the two worked examples from SPEC §2.
- The two **detection** sources and why both are needed: a proxied FQDN's CNAME is invisible in
  public DNS; an unproxied Cloudflare CNAME is absent from `fqdns.json`.
- **Where the addresses come from and why** (SPEC §4.1): `terminus domain:dns <site>.live`, one
  lazy call per affected site. Resolving the legacy target ourselves would print a *different
  Pantheon site's* addresses whenever that target is stale. The addresses in a sent email are
  therefore **Pantheon's recommendation at send time** — they track Pantheon's own state, so
  whoever performs the maintenance re-runs the report rather than trusting a months-old email.
- That "A and AAAA, not CNAME" is Pantheon's **pre-migration** rule; the target-state record type
  is Pantheon's to define (`its-wws-test1`, already migrated, is offered a CNAME to
  `fe.cfp2c.edge.pantheon.io`).
- **The `fqdns.json` freshness dependency (F12):** a single-site run does not refresh the file, so
  the Cloudflare half answers from whatever is on disk. Use `--update-cloudflare-fqdns` when the
  answer must be current; the check warns once per run when the file is stale or absent.
- The `UMICH_MAINTENANCE_CUTOFF` constant: where it is (`check/pantheon_cdn_change/hook.py`), how
  to change the date once maintenance is scheduled, how to remove the U-M branch after it passes.
- How to delete the whole check when Pantheon's migration is done:
  ```bash
  git rm -r check/pantheon_cdn_change \
            tests/unit/test_pantheon_cdn_change_*.py \
            tests/integration/test_check_pantheon_cdn_change.py \
            tests/integration/test_pantheon_cdn_change_notice_render.py \
            tests/e2e/test_golden_cdn_change.py \
            tests/fixtures/terminus-cdnchange
  # then drop the matching snapshot files and the CLAUDE.md references.
  # KEEP: dns_classify.MalformedNameError, the fqdns.json freshness keys, sc.terminus/sc.fqdn_re,
  # tests/helpers/, and tests/shims/dnsshim -- those are general fixes and infrastructure, not
  # part of this temporary check.
  ```

- [ ] **Step 2: Update `CLAUDE.md`**

Five edits, no others:
1. "Plugin / check module system": add `check.pantheon_cdn_change` to the list of packages
   `find_modules()` imports.
2. The `check/` description: add the Pantheon CDN-change check (`site_post_dns`) — flags custom
   domains that still reach `*.pantheonsite.io` via a CNAME, in public DNS or in Cloudflare, and
   gets its replacement records from `terminus domain:dns`; see `docs/pantheon-cdn-change.md`.
3. The sc-exposure list (`sc.escape_url`, `sc.check_wordpress_plugin`, …): add `sc.terminus` and
   `sc.fqdn_re`.
4. The `fqdns.json` note currently says the values' `origins` are unread and `zone_id` is "for a
   future feature". **`origins` is consumed now** (by `check/pantheon_cdn_change`) — correct it.
5. Testing section: record `dns_classify.MalformedNameError` as part of the DNS-seam contract
   (`resolve` converts dnspython's syntax errors so a malformed hostname cannot abort a run); add
   the new test files; note `tests/helpers/` (shared fake resolver, recording console, check
   loader) and `tests/shims/dnsshim` (the subprocess DNS shim the 4th golden needs, because
   `run_program` is a subprocess and cannot be monkeypatched).

- [ ] **Step 3: Run the full suite, including the live tier**

Run: `./run-tests`
Expected: PASS. Paste the summary line into the final report (do not summarize it).

- [ ] **Step 4: Live verification against the two known-affected sites**

Read-only single-site runs (no `--all`, no `--for-real`). `--update-cloudflare-fqdns` is
REQUIRED, not optional: a single-site run does not refresh `fqdns.json` (F12), so without it the
`its-backstage` case would be validated against a possibly-stale file.

```bash
./pantheon-sitehealth-emails --date 20260630 --update-cloudflare-fqdns bus-occb
./pantheon-sitehealth-emails --date 20260630 --update-cloudflare-fqdns its-backstage
```

Expected in `build/bus-occb.txt`: a row `occb.bus.umich.edu` / `DNS` / A `23.185.0.4`, AAAA
`2620:12a:8000::4`, AAAA `2620:12a:8001::4`.
Expected in `build/its-backstage.txt`: rows for `backstage.its.umich.edu` (and
`news.backstage.its.umich.edu`, if it too still has a CNAME) / `U-M Cloudflare` / A `23.185.0.2`,
AAAA `2620:12a:8000::2`, AAAA `2620:12a:8001::2`. Cross-check against
`terminus domain:dns its-backstage.live --format=json`.

- [ ] **Step 5: Answer the closing audit questions (SPEC §15) with evidence**

```bash
git status --short tests/e2e/__snapshots__/                      # (1) only the NEW golden added
grep -rn "U-M\|ITS\|umich" check/pantheon_cdn_change/notices.py  # (2) only inside the umich branch
grep -rn "dns.resolver\|import dns" check/pantheon_cdn_change/   # (3) only the caught exceptions
grep -rn "except Exception\|except:" check/pantheon_cdn_change/ dns_classify.py   # (4) nothing
grep -n "UMICH_MAINTENANCE_CUTOFF" check/pantheon_cdn_change/hook.py   # (5) one line + comment
python -c "import dns_classify as d; print(d.classify_hostname_dns('a..b', False, [], []))"  # (6) (0,0,False)
grep -n "^import\|^from" check/pantheon_cdn_change/notices.py    # (7) only html + .model
grep -rn "addresses" check/pantheon_cdn_change/chain.py          # (8) MUST return nothing
grep -n "required_records" check/pantheon_cdn_change/detect.py  # (9) called only after candidates
grep -c "unavailable" tests/e2e/__snapshots__/test_golden_cdn_change.ambr  # (11) MUST be 0
grep -n "ITS will make" tests/e2e/__snapshots__/test_golden_cdn_change.ambr  # (10) MUST be absent
```

- [ ] **Step 6: Commit**

```bash
git add docs/pantheon-cdn-change.md CLAUDE.md development/2026-07-12-pantheon-cdn-change-check/
git commit -m "docs(pantheon-cdn-change): document the check, the cutoff, and its removal"
```

---

## Self-review (against SPEC, after three rounds of adversarial review)

- **Spec coverage:** §4 architecture → Tasks 5–9; §4.1 record sourcing → Task 6; §5 interfaces →
  each task's Interfaces block; §6 gates → Tasks 7, 9; §7 failure modes → F1/F2/F3 Task 5, F4
  Tasks 6–8, F5/F6 Task 9, F7/F8 Task 7, F9 Tasks 8+10, F10 Tasks 2+5+7, F11 Tasks 7+8, F12
  Task 3, F13 Tasks 4+7, F14 Tasks 6+7+8+10; §8 copy → Task 8; §9 observability → Tasks 5, 7, 9;
  §12 testing → Tasks 1, 5–11; §13 acceptance → Task 12 Steps 3–4; §14 docs → Task 12 Steps 1–2;
  §15 audit → Task 12 Step 5. No gaps.
- **Round-2 issues:** #1 (DNS-derived addresses) → the design change, Tasks 4+6+7; #2 (golden
  pinned the wrong copy) → Task 11 scope note + `test_golden_pins_the_generic_copy`; #3
  (`custom_domains` unvalidated) → Task 4 + F13; #4 (DRY promise) → Task 1 scope limit, SPEC §12
  amended to match; #5 (placeholder tests) → real code; #6 (F12 duplication) → **Task 3 cut down
  to one sentence**; #7 (unescaped exception) → Task 2; #8 (`capsys` fragility) →
  `recording_console`; #9 (csv/console mismatch) → moot, one row per FQDN; #10 (fixture
  mechanics) → Task 11 Step 2; #11 (TDD vs house convention) → noted in the preamble.
- **Round-3 issues:** #1 (F13 built on a false premise — `fqdn_re` MATCHES `a..b`; its test would
  have failed) → F13 redefined as a CSV-integrity guard with an explicit `,\r\n` reject, and
  `is_safe_domain_id` + its test rewritten; #2 (fixture key used the site NAME; the program sends
  the **UUID**) → Task 11 Step 2 fixed, plus a warning that a wrong key yields a plausible-but-
  wrong golden; #3 (a migrated site's CNAME-only answer rendered as "unavailable", silently) →
  F14: `Required.cname`, an operator ATTENTION, and the notice shows Pantheon's actual answer;
  #4 (Task 3 duplicated an existing warning + had a dead branch) → **cut to one sentence in
  `fqdns.py`**; the `plugin_context` contract, the module global, and seven tests are gone;
  #5 (`checkload` leaked `sys.modules`) → explicit prefix purge + finalizer, both loaders take
  `request`; #6 (vacuous purity assertion) → asserts on imported module objects; #7 (unescaped
  `site_name`; UUID in operator messages) → `rich_escape` + `site_name` threaded into
  `required_records`; #8 (`fqdn_re`'s `$` admits a trailing newline) → the explicit reject covers
  it; #9 (SPEC numbering) → §4.1/§4.2/§4.3, F-rows in order, "three changes"; #10 (`extra_env`,
  dead `OCCB_ADDRS`, chart delta) → conftest gains `extra_env`, the dead constant is gone, the
  third golden delta is documented.
- **Type consistency:** `ChainResult(target, transient)`, `Required(a, aaaa, cname)`,
  `Finding(fqdn, where, target, a, aaaa, cname)`, and the `where` machine values `"dns"` /
  `"cloudflare"` / `"both"` are used identically in every task and every test.

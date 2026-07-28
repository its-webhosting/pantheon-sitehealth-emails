# `find-platform-domains-dns` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Dispatch every code-touching subagent as
> **`psh-implementer`** and every reviewer as **`psh-reviewer`** (CLAUDE.md § Dispatching
> subagents); a dispatch that cannot use them must stop and say so.

**Goal:** A standalone, deletable utility that lists every Pantheon custom domain, across every
site and environment in the organization, whose DNS still reaches a platform domain by CNAME —
as CSV on stdout, with every indeterminate lookup reported on stderr and counted.

**Architecture:** One self-contained executable at the repo root (`find-platform-domains-dns`)
plus a committed `.py` symlink for tooling, and one offline unit-test file. It imports nothing
from `psh/`, `check/`, `plugin/`, or `script_context`; the DNS walk and resolver seam are
**copied** from `check/pantheon_cdn_change/chain.py` and `psh/dns_classify.py` so deletion after
the CDN migration is a `git rm` of three paths plus two `pyproject.toml` lines. Pantheon data
comes from the Pantheon API over one reused `httpx` connection; DNS goes through a single
monkeypatchable `resolve()` seam.

**Tech Stack:** Python 3.12+, `httpx` (already a project dependency), `dnspython`, stdlib
`argparse`/`csv`/`tomllib`/`json`. Tests: pytest, `httpx.MockTransport`,
`tests/helpers/dnsfake.make_resolver`.

**Spec:** `development/2026-07-28-platform-domain-util/SPEC.md` — read it first. Section
references below (§4.1, §7, …) are to that file. Where this plan and the spec disagree, the
spec wins; stop and report the discrepancy.

## Global Constraints

- **Standalone.** The script MUST NOT import `psh`, `check`, `plugin`, or `script_context`.
- **No `rich`.** All operator output is `print(…, file=sys.stderr)` (SPEC §8).
- **stdout is CSV only.** Never print anything else there (SPEC §5).
- **`csv.writer(…, lineterminator="\n")`** — the default is `\r\n`.
- **Every failure has a name** (PD#2): `PantheonApiError`, `MachineTokenError`,
  `MalformedNameError`, `SiteListingError`. No bare `except`, no `except Exception`
  (ruff `E722`/`BLE001` enforce this and the gate is `select = ALL`).
- **Exit codes:** `0` clean sweep, `1` completed with ≥1 indeterminate, `2` could not complete.
- **Never name a variable `*token*` and assign it a string literal** — ruff `S105` flags it.
  Inline `os.environ.get("PANTHEON_MACHINE_TOKEN")` rather than hoisting the name to a constant.
- **`allow_abbrev=False`** on the argument parser (house rule).
- **Entry point guarded** by `if __name__ == "__main__":` — the test file imports the module.
- **`./run-tests --fast` must stay green after every task.** It runs ruff (`select = ALL`) and
  pyright before pytest and gates on both.
- **Tests are load-bearing.** NEVER weaken an assertion, delete a case, or relax a fake to make
  a test pass. A red test is a finding about the code.
- **Commit after each task** (the repo commits only when asked — this plan is the ask, and each
  task's final step is the commit).

## File Structure

| Path | Responsibility |
|---|---|
| `find-platform-domains-dns` | The entire program: DNS walk, API session, enumeration, sweep, CLI. ~350 lines. Created in Task 1, grown by Tasks 2–5. |
| `find-platform-domains-dns.py` | Committed symlink → the above. Exists solely so ruff, pyright, and CodeGraph see the file (they key off the extension). Created in Task 1. |
| `tests/unit/test_find_platform_domains_dns.py` | The one test file, `pytest.mark.unit`, fully offline. Created in Task 1, grown by Tasks 2–5. |
| `pyproject.toml` | Two additions in Task 1: a `[tool.ruff.lint.per-file-ignores]` entry for `T201`, and the script in `[tool.pyright].include`. |
| `CONTEXT.md` | Three glossary terms in Task 1 (PD#11). |
| `CLAUDE.md` | One paragraph in Task 5 describing the utility and its deletion condition. |
| `development/2026-07-28-platform-domain-util/ACCEPTANCE.md` | Task 6: the pasted output of every SPEC §13 command. |

Single file by instruction (PROMPT.md: copied code stays in the script rather than being
modularized, so cleanup is trivial). Within it, keep functions small and single-purpose — ruff's
`PLR0913` (>5 args) and `C901`/`PLR0912` (complexity) are active, which is why the sweep is a
small class holding its collaborators rather than functions with long parameter lists.

---

### Task 1: Scaffolding, tooling wiring, and the DNS chain walk

**Files:**
- Create: `find-platform-domains-dns` (executable, `chmod +x`)
- Create: `find-platform-domains-dns.py` (symlink → `find-platform-domains-dns`)
- Create: `tests/unit/test_find_platform_domains_dns.py`
- Modify: `pyproject.toml` (`[tool.ruff.lint.per-file-ignores]`, `[tool.pyright].include`)
- Modify: `CONTEXT.md` (glossary)

**Interfaces:**
- Consumes: nothing.
- Produces: `normalize(name) -> str`; `is_platform_domain(name) -> bool`;
  `MalformedNameError`; `resolve(hostname, rrtype)`; `resolve_cname_retrying(name)`;
  `WalkResult` (`NamedTuple` with fields `dns_record: str`, `platform_domain: str`,
  `problem: str`); `walk(custom_domain) -> WalkResult`;
  module constants `PLATFORM_SUFFIX = ".pantheonsite.io"`, `MAX_CNAME_DEPTH = 8`.

- [ ] **Step 1: Create the script skeleton, the symlink, and the tooling entries**

`find-platform-domains-dns` (first version — the walk layer only):

```python
#!/usr/bin/env python
"""List Pantheon custom domains whose DNS still reaches a platform domain by CNAME.

TEMPORARY.  Delete after Pantheon's Fastly -> Pantheon-Cloudflare CDN migration completes;
see development/2026-07-28-platform-domain-util/SPEC.md section 14 for the checklist.

Standalone by design: this imports nothing from psh/, check/, plugin/ or script_context, so
removing it is `git rm` of the script, its .py symlink and its test file.  The DNS walk and the
resolver seam are COPIES of check/pantheon_cdn_change/chain.py and psh/dns_classify.py.

Output: CSV on stdout, `site_name,site_env,custom_domain,dns_record,platform_domain`, no header.
Operator messages, including every indeterminate lookup, go to stderr.  Exit 0 = clean sweep,
1 = completed with indeterminates, 2 = could not complete.

Requires: dnspython and httpx (httpx is declared under this project's `cloudflare` extra, which
the documented `uv pip install .[mysql,aws,cloudflare]` setup line installs) and a Pantheon
machine token, from $PANTHEON_MACHINE_TOKEN or ~/.terminus/cache/tokens/.
"""
import struct
import sys
from typing import NamedTuple

import dns.exception
import dns.name
import dns.resolver

PLATFORM_SUFFIX = ".pantheonsite.io"
MAX_CNAME_DEPTH = 8


class MalformedNameError(Exception):
    """`hostname` is not a syntactically valid DNS name.

    Copied from psh/dns_classify.py.  dnspython raises four unrelated exception types for a bad
    name -- dns.exception.SyntaxError subclasses, dns.name.NameTooLong, dns.name.IDNAException,
    and the stdlib struct.error for an out-of-range byte escape -- none of which derive from
    dns.resolver.*, so no resolver handler catches them.  resolve() converts them here, ONCE, so
    no caller can forget them and abort a whole sweep on one malformed Pantheon domain id.
    """


def resolve(hostname, rrtype):
    """The one seam over dns.resolver.resolve; tests monkeypatch this module attribute.

    Copied from psh/dns_classify.py, including the struct.error split: the name is parsed FIRST,
    in its own try, so only a parse-time struct.error is reported as a malformed name.  dnspython
    ALSO raises struct.error from its TCP length-prefix unpack -- i.e. from garbled wire data on a
    perfectly valid name -- and that must surface as transient (NoNameservers), never as "not a
    valid DNS name".
    """
    try:
        dns.name.from_text(hostname)
    except (dns.exception.SyntaxError, dns.name.NameTooLong, dns.name.IDNAException,
            struct.error) as e:
        raise MalformedNameError(f"{hostname}: {type(e).__name__}") from e

    try:
        return dns.resolver.resolve(hostname, rrtype)
    except (dns.exception.SyntaxError, dns.name.NameTooLong, dns.name.IDNAException) as e:
        raise MalformedNameError(f"{hostname}: {type(e).__name__}") from e
    except struct.error as e:
        raise dns.resolver.NoNameservers from e


def attention(message):
    """Every operator-visible finding goes through here: stderr, unbuffered, never stdout."""
    print(f"ATTENTION: {message}", file=sys.stderr, flush=True)


def normalize(name):
    """Lowercase, strip whitespace and the trailing root dot dnspython includes."""
    return str(name).strip().rstrip(".").lower()


def is_platform_domain(name):
    """True for a Pantheon-provided *.pantheonsite.io hostname."""
    return normalize(name).endswith(PLATFORM_SUFFIX)


class WalkResult(NamedTuple):
    dns_record: str       # FQDN owning the hitting CNAME record; "" when there was no hit
    platform_domain: str  # the *.pantheonsite.io target reached;   "" when there was no hit
    problem: str          # "" for a definitive answer (hit or clean); else why it is indeterminate


def resolve_cname_retrying(name):
    """resolve(name, "CNAME") with ONE immediate retry on a transient resolver failure.

    No sleep between attempts: dnspython has already spent its own ~5s lifetime on the query,
    so an added delay buys nothing.
    """
    try:
        return resolve(name, "CNAME")
    except (dns.resolver.NoNameservers, dns.resolver.Timeout):
        return resolve(name, "CNAME")


def walk(custom_domain):
    """Follow the CNAME chain from `custom_domain`, looking for a platform domain.

    Adapted from check/pantheon_cdn_change/chain.py.  THE ADAPTATION MATTERS: chain.py tests the
    CURRENT name at the top of each hop, because its caller starts from a Cloudflare origin that
    may already be a platform domain.  This utility must report the OWNER of the hitting record
    (`dns_record`, the record the downstream rewriter replaces), so the platform test moves to
    the RESOLVED TARGET and the hit carries the name that was resolved.

        name := normalize(custom_domain)
        name is itself a platform domain? -- yes --> INDETERMINATE (no CNAME record to replace)
              | no
              v
        +-> already seen? -- yes --> INDETERMINATE (chain loops)
        |       | no
        |       v
        |   resolve(name, "CNAME")
        |       |-- NoAnswer / NXDOMAIN --------> NO HIT (definitive: chain ends here)
        |       |-- Timeout / NoNameservers ----> INDETERMINATE (transient)
        |       |-- MalformedNameError ---------> INDETERMINATE (not a valid DNS name)
        |       `-- target t:
        |             t is a platform domain? -- yes --> HIT(dns_record=name, platform=t)
        `------- name := t                          (after MAX_CNAME_DEPTH hops: INDETERMINATE)
    """
    name = normalize(custom_domain)
    if is_platform_domain(name):
        return WalkResult("", "", "is itself a platform domain; no CNAME record to replace")
    seen = set()
    for _hop in range(MAX_CNAME_DEPTH):
        if name in seen:
            return WalkResult("", "", f"CNAME chain loops at {name}")
        seen.add(name)
        try:
            answer = resolve_cname_retrying(name)
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            return WalkResult("", "", "")
        except (dns.resolver.NoNameservers, dns.resolver.Timeout) as e:
            return WalkResult("", "", f"transient DNS error at {name}: {type(e).__name__}")
        except MalformedNameError as e:
            return WalkResult("", "", f"not a valid DNS name: {e}")
        # No empty-answer guard: resolve() either raises (every case is handled above) or returns
        # a non-empty rdata set -- an empty CNAME answer surfaces as NoAnswer, never as an empty
        # iterable.  A guard here would be untestable dead code.
        target = normalize(next(iter(answer)).target)
        if is_platform_domain(target):
            return WalkResult(name, target, "")
        name = target
    return WalkResult("", "", f"CNAME chain exceeds {MAX_CNAME_DEPTH} hops")
```

Then:

```bash
cd /workspace
chmod +x find-platform-domains-dns
ln -s find-platform-domains-dns find-platform-domains-dns.py
git add find-platform-domains-dns find-platform-domains-dns.py
```

In `pyproject.toml`, add to `[tool.ruff.lint.per-file-ignores]` (after the
`development/finalize-session.py` line), keeping the required justification comment that the
governance note in that file demands:

```toml
"find-platform-domains-dns.py" = ["T201"]  # a CLI tool: print IS its output (stdout = the CSV,
    # stderr = operator messages).  Temporary, deleted with the script after the Pantheon CDN
    # migration -- see development/2026-07-28-platform-domain-util/SPEC.md section 14.
```

and extend `[tool.pyright]`:

```toml
include = ["psh", "find-platform-domains-dns.py"]
```

Verified 2026-07-28: ruff 0.15.22 lints files reached through a `.py` symlink, and pyright
1.1.411 analyzes one, so both entries take effect.

- [ ] **Step 2: Add the three glossary terms to `CONTEXT.md`**

Append to the `## Language` section, keeping the file's existing style (bold term, definition,
optional `_Avoid_:` line). These describe Pantheon, not this script, so they stay after the
script is deleted (PD#11):

```markdown
**Environment**:
One deployable instance of a site — `dev`, `test`, `live`, or a multidev (`test-mark`,
`autopilot`, …). Each environment has its own domain list.

**Custom domain**:
A hostname a site owner connected to a site environment (`example.umich.edu`). Pantheon
labels these `type: custom`. Primary domains are custom domains.

**Platform domain**:
The Pantheon-provided hostname for a site environment, ending in `.pantheonsite.io`
(`live-bus-occb.pantheonsite.io`). Pantheon labels these `type: platform`.
_Avoid_: Pantheon domain, pantheonsite name
```

- [ ] **Step 3: Write the failing tests for the walk layer**

Create `tests/unit/test_find_platform_domains_dns.py`:

```python
"""Offline tests for the find-platform-domains-dns utility (SPEC section 10).

The script has no .py extension, so it is loaded with the SourceFileLoader idiom the suite
already uses for standalone check/plugin modules (tests/integration/test_plugin_aws.py).  It is
loaded FRESH PER TEST so no module-level state leaks between tests.

Seams (SPEC section 9): `resolve` is monkeypatched on the loaded module; the API getter is
INJECTED as a parameter, never patched; httpx.MockTransport backs the ApiSession tests.
"""
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

import dns.resolver
import pytest
from helpers.dnsfake import make_resolver

pytestmark = pytest.mark.unit

SCRIPT = Path(__file__).resolve().parent.parent.parent / "find-platform-domains-dns"


@pytest.fixture
def fpd():
    """The utility, loaded fresh.  Its entry point is __main__-guarded, so import runs no sweep."""
    loader = SourceFileLoader("find_platform_domains_dns_probe", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def patch_dns(monkeypatch, fpd, zone, calls=None):
    """Point the script's own `resolve` seam at a fake zone (helpers.dnsfake shape)."""
    monkeypatch.setattr(fpd, "resolve", make_resolver(zone, calls))


def test_normalize_and_is_platform_domain(fpd):
    assert fpd.normalize("  LIVE-X.PantheonSite.io. ") == "live-x.pantheonsite.io"
    assert fpd.is_platform_domain("LIVE-X.PantheonSite.io.") is True
    # A name that merely CONTAINS the suffix text is not a platform domain.
    assert fpd.is_platform_domain("pantheonsite.io.evil.example") is False
    assert fpd.is_platform_domain("fe.cfp2c.edge.pantheon.io") is False


def test_direct_hit_reports_the_custom_domain_as_the_dns_record(fpd, monkeypatch):
    patch_dns(monkeypatch, fpd,
              {("occb.bus.umich.edu", "CNAME"): ["live-bus-occb.pantheonsite.io."]})
    assert fpd.walk("occb.bus.umich.edu") == fpd.WalkResult(
        "occb.bus.umich.edu", "live-bus-occb.pantheonsite.io", "")


def test_mid_chain_hit_reports_the_owner_of_the_hitting_record(fpd, monkeypatch):
    # THE point of the dns_record column: the record to rewrite is alias.umich.edu, not the
    # custom domain the site owner connected.
    patch_dns(monkeypatch, fpd, {
        ("www.example.umich.edu", "CNAME"): ["alias.umich.edu."],
        ("alias.umich.edu", "CNAME"): ["live-y.pantheonsite.io."],
    })
    assert fpd.walk("www.example.umich.edu") == fpd.WalkResult(
        "alias.umich.edu", "live-y.pantheonsite.io", "")


def test_no_cname_is_a_clean_no_hit(fpd, monkeypatch):
    patch_dns(monkeypatch, fpd, {})          # absent key -> NoAnswer, the healthy shape
    assert fpd.walk("apex.umich.edu") == fpd.WalkResult("", "", "")


def test_nxdomain_is_a_clean_no_hit(fpd, monkeypatch):
    patch_dns(monkeypatch, fpd, {("gone.umich.edu", "CNAME"): dns.resolver.NXDOMAIN()})
    assert fpd.walk("gone.umich.edu") == fpd.WalkResult("", "", "")


def test_migrated_domain_is_a_no_hit(fpd, monkeypatch):
    # Verified live: a migrated domain CNAMEs to the NEW CDN, which is not *.pantheonsite.io.
    patch_dns(monkeypatch, fpd,
              {("wws-test1.cdn-dev.it.umich.edu", "CNAME"): ["fe.cfp2c.edge.pantheon.io."]})
    assert fpd.walk("wws-test1.cdn-dev.it.umich.edu") == fpd.WalkResult("", "", "")


def test_transient_error_is_indeterminate_and_retried_once(fpd, monkeypatch):
    calls = []
    patch_dns(monkeypatch, fpd, {("x.umich.edu", "CNAME"): dns.resolver.Timeout()}, calls)
    result = fpd.walk("x.umich.edu")
    assert result.dns_record == ""
    assert "transient DNS error at x.umich.edu" in result.problem
    assert calls == [("x.umich.edu", "CNAME"), ("x.umich.edu", "CNAME")]  # retried exactly once


def test_malformed_name_is_indeterminate_not_a_crash(fpd, monkeypatch):
    patch_dns(monkeypatch, fpd,
              {("a..b", "CNAME"): fpd.MalformedNameError("a..b: EmptyLabel")})
    assert "not a valid DNS name" in fpd.walk("a..b").problem


def test_cname_loop_is_indeterminate(fpd, monkeypatch):
    patch_dns(monkeypatch, fpd, {
        ("a.umich.edu", "CNAME"): ["b.umich.edu."],
        ("b.umich.edu", "CNAME"): ["a.umich.edu."],
    })
    assert "loops at" in fpd.walk("a.umich.edu").problem


def test_chain_longer_than_the_hop_limit_is_indeterminate(fpd, monkeypatch):
    zone = {(f"h{i}.umich.edu", "CNAME"): [f"h{i + 1}.umich.edu."] for i in range(20)}
    assert "exceeds 8 hops" in fpd.walk("h0.umich.edu").problem


def test_custom_domain_that_is_itself_a_platform_domain_is_indeterminate(fpd, monkeypatch):
    calls = []
    patch_dns(monkeypatch, fpd, {}, calls)
    result = fpd.walk("live-x.pantheonsite.io")
    assert "itself a platform domain" in result.problem
    assert calls == []          # decided without a single DNS query
```

- [ ] **Step 4: Run the tests and watch them fail for the right reason**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_dns.py -v
```

Expected before Step 1's code exists: collection errors / `AttributeError`. After Step 1 they
should pass. **Verify at least one test can go red for its own reason** (PD#14): temporarily
change `MAX_CNAME_DEPTH` to 20 and confirm
`test_chain_longer_than_the_hop_limit_is_indeterminate` fails, then restore it.

- [ ] **Step 5: Run the whole fast suite**

```bash
./run-tests --fast
```

Expected: ruff clean (`select = ALL` — the new file is linted through the symlink), pyright
clean, all tests pass.

Two contingencies, both with a prescribed fix — do **not** improvise around either:

- If ruff reports `INP001` on the script, add it to the same per-file-ignores entry **with a
  justification comment**; never a bare `noqa` (a bare one is a silent failure per `./run-tests`'
  own message).
- If pyright objects to `next(iter(answer)).target` (dnspython's `Rdata` has no declared
  `target`), append `# pyright: ignore[reportAttributeAccessIssue]` **with an inline reason**,
  matching the house style already used in `psh/cli.py`. Do not widen the ignore to the file.

- [ ] **Step 6: Commit**

```bash
git add find-platform-domains-dns find-platform-domains-dns.py \
        tests/unit/test_find_platform_domains_dns.py pyproject.toml CONTEXT.md
git commit -m "feat(find-platform-domains-dns): the CNAME chain walk + tooling scaffolding"
```

---

### Task 2: Pantheon API session — auth, retry, re-authentication

**Files:**
- Modify: `find-platform-domains-dns` (append; imports move to the top of the file)
- Modify: `tests/unit/test_find_platform_domains_dns.py` (append)

**Interfaces:**
- Consumes: `attention` from Task 1.
- Produces: `PantheonApiError`; `MachineTokenError`; `machine_token() -> str`;
  `ApiSession(client, machine_token)` with `.get(path) -> Any` and `.token`;
  constants `API_BASE = "https://api.pantheon.io/v0"`, `RETRY_SLEEP = 2.0`,
  `HTTP_TIMEOUT = 30.0`, `USER_AGENT = "find-platform-domains-dns"`.

- [ ] **Step 1: Write the failing tests**

Append to the test file:

```python
import httpx


def make_session(fpd, handler):
    """An ApiSession whose transport is a MockTransport running `handler`."""
    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)
    return fpd.ApiSession(client, "fake-machine-token")


def test_session_authenticates_once_at_construction(fpd):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json={"session": "sess-1"})

    session = make_session(fpd, handler)
    assert session.token == "sess-1"
    assert seen == ["https://api.pantheon.io/v0/authorize/machine-token"]


def test_get_returns_decoded_json(fpd):
    def handler(request):
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": "sess-1"})
        assert request.headers["Authorization"] == "Bearer sess-1"
        return httpx.Response(200, json={"ok": True})

    assert make_session(fpd, handler).get("/sites/abc") == {"ok": True}


def test_401_reauthenticates_once_then_succeeds(fpd):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": f"sess-{calls.count('/v0/authorize/machine-token')}"})
        if calls.count("/v0/sites/abc") == 1:
            return httpx.Response(401, json={"error": "expired"})
        return httpx.Response(200, json={"ok": True})

    session = make_session(fpd, handler)
    assert session.get("/sites/abc") == {"ok": True}
    assert calls.count("/v0/authorize/machine-token") == 2   # re-authenticated exactly once
    assert session.token == "sess-2"


def test_401_twice_raises_named_error(fpd):
    def handler(request):
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": "sess"})
        return httpx.Response(401, json={"error": "nope"})

    with pytest.raises(fpd.PantheonApiError, match="401"):
        make_session(fpd, handler).get("/sites/abc")


def test_500_is_retried_once_then_succeeds(fpd, monkeypatch):
    monkeypatch.setattr(fpd, "RETRY_SLEEP", 0)    # the seam that keeps the suite fast
    calls = []

    def handler(request):
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": "sess"})
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(503, text="unavailable")
        return httpx.Response(200, json={"ok": True})

    assert make_session(fpd, handler).get("/sites/abc") == {"ok": True}
    assert len(calls) == 2


def test_500_twice_raises_named_error(fpd, monkeypatch):
    monkeypatch.setattr(fpd, "RETRY_SLEEP", 0)

    def handler(request):
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": "sess"})
        return httpx.Response(500, text="boom")

    with pytest.raises(fpd.PantheonApiError, match="500"):
        make_session(fpd, handler).get("/sites/abc")


def test_429_is_retried_like_a_5xx(fpd, monkeypatch):
    monkeypatch.setattr(fpd, "RETRY_SLEEP", 0)
    calls = []

    def handler(request):
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": "sess"})
        calls.append(1)
        return httpx.Response(429 if len(calls) == 1 else 200, json={"ok": True})

    assert make_session(fpd, handler).get("/x") == {"ok": True}
    assert len(calls) == 2


def test_connect_error_is_retried_once_then_raises_named_error(fpd, monkeypatch):
    monkeypatch.setattr(fpd, "RETRY_SLEEP", 0)
    calls = []

    def handler(request):
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": "sess"})
        calls.append(1)
        raise httpx.ConnectError("no route")

    with pytest.raises(fpd.PantheonApiError, match="no route"):
        make_session(fpd, handler).get("/x")
    assert len(calls) == 2


def test_undecodable_body_raises_named_error(fpd):
    def handler(request):
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": "sess"})
        return httpx.Response(200, text="<html>not json</html>")

    with pytest.raises(fpd.PantheonApiError):
        make_session(fpd, handler).get("/x")


def test_machine_token_prefers_the_environment(fpd, monkeypatch):
    monkeypatch.setenv("PANTHEON_MACHINE_TOKEN", "from-env")
    assert fpd.machine_token() == "from-env"


def test_machine_token_reads_the_single_terminus_cache_file(fpd, monkeypatch, tmp_path):
    monkeypatch.delenv("PANTHEON_MACHINE_TOKEN", raising=False)
    cache = tmp_path / ".terminus" / "cache" / "tokens"
    cache.mkdir(parents=True)
    (cache / "someone@umich.edu").write_text('{"token": "from-cache", "email": "x"}')
    monkeypatch.setattr(fpd.Path, "home", staticmethod(lambda: tmp_path))
    assert fpd.machine_token() == "from-cache"


def test_machine_token_refuses_to_guess_between_several_cache_files(fpd, monkeypatch, tmp_path):
    monkeypatch.delenv("PANTHEON_MACHINE_TOKEN", raising=False)
    cache = tmp_path / ".terminus" / "cache" / "tokens"
    cache.mkdir(parents=True)
    (cache / "a@umich.edu").write_text('{"token": "a"}')
    (cache / "b@umich.edu").write_text('{"token": "b"}')
    monkeypatch.setattr(fpd.Path, "home", staticmethod(lambda: tmp_path))
    with pytest.raises(fpd.MachineTokenError, match="2"):
        fpd.machine_token()


def test_machine_token_missing_cache_directory_is_named(fpd, monkeypatch, tmp_path):
    monkeypatch.delenv("PANTHEON_MACHINE_TOKEN", raising=False)
    monkeypatch.setattr(fpd.Path, "home", staticmethod(lambda: tmp_path))
    with pytest.raises(fpd.MachineTokenError):
        fpd.machine_token()
```

- [ ] **Step 2: Run them and confirm they fail**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_dns.py -v
```

Expected: `AttributeError: module has no attribute 'ApiSession'` (and friends).

- [ ] **Step 3: Implement the session layer**

Add these imports to the top of `find-platform-domains-dns` (keep the block alphabetized; ruff
`I001` enforces import order): `import json`, `import os`, `import time`,
`from pathlib import Path`, `import httpx`. Then append:

```python
API_BASE = "https://api.pantheon.io/v0"
HTTP_TIMEOUT = 30.0
RETRY_SLEEP = 2.0            # monkeypatched to 0 by the tests -- see SPEC section 9
USER_AGENT = "find-platform-domains-dns"


class PantheonApiError(Exception):
    """A Pantheon API call failed after its one retry, or returned an undecodable body."""


class MachineTokenError(Exception):
    """No Pantheon machine token could be resolved without guessing (SPEC section 3)."""


def machine_token():
    """$PANTHEON_MACHINE_TOKEN, else the single JSON file in ~/.terminus/cache/tokens/.

    Zero files, several files, an unreadable file or a missing `token` key is an error, never a
    guess: picking one of several would silently sweep the wrong Pantheon account (PD#1).
    """
    from_env = os.environ.get("PANTHEON_MACHINE_TOKEN")   # inlined: a module constant named
    if from_env:                                          # *_TOKEN holding a literal trips S105
        return from_env
    cache = Path.home() / ".terminus" / "cache" / "tokens"
    if not cache.is_dir():
        raise MachineTokenError(
            f"no machine token: {cache} does not exist and $PANTHEON_MACHINE_TOKEN is unset. "
            "Authenticate terminus, or set the environment variable.")
    files = sorted(p for p in cache.iterdir() if p.is_file())
    if len(files) != 1:
        raise MachineTokenError(
            f"no machine token: expected exactly one file in {cache}, found {len(files)}"
            f" ({', '.join(p.name for p in files) or 'none'}). "
            "Set $PANTHEON_MACHINE_TOKEN to choose one.")
    try:
        data = json.loads(files[0].read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise MachineTokenError(f"could not read {files[0]}: {e}") from e
    if "token" not in data:
        raise MachineTokenError(f"{files[0]} has no 'token' key")
    return data["token"]


class ApiSession:
    """One authenticated Pantheon API session over one reused httpx connection.

    Retry policy (SPEC section 7.1): ONE retry, RETRY_SLEEP apart, on a transport failure, 5xx,
    or 429.  ONE re-authentication on a 401, which does NOT consume the transport retry -- a
    session that expires 15 minutes into a 20-minute sweep must not also spend the retry budget.
    """

    def __init__(self, client, token_value):
        self._client = client
        self._machine_token = token_value
        self.token = self._authenticate()

    def _authenticate(self):
        try:
            response = self._client.post(
                f"{API_BASE}/authorize/machine-token",
                json={"machine_token": self._machine_token, "client": USER_AGENT})
        except httpx.HTTPError as e:
            raise PantheonApiError(f"could not authenticate to Pantheon: {e}") from e
        if response.status_code != 200:
            raise PantheonApiError(
                f"could not authenticate to Pantheon: HTTP {response.status_code}")
        try:
            return response.json()["session"]
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise PantheonApiError(f"authentication response had no session token: {e}") from e

    def get(self, path):
        """GET {API_BASE}{path} and return the decoded JSON, or raise PantheonApiError."""
        transport_attempts = 0
        reauthed = False
        while True:
            try:
                response = self._client.get(
                    f"{API_BASE}{path}",
                    headers={"Authorization": f"Bearer {self.token}",
                             "User-Agent": USER_AGENT})
            except httpx.HTTPError as e:
                transport_attempts += 1
                if transport_attempts > 1:
                    raise PantheonApiError(f"{path}: {e}") from e
                time.sleep(RETRY_SLEEP)
                continue
            if response.status_code == 401 and not reauthed:
                reauthed = True
                self.token = self._authenticate()
                continue
            if response.status_code == 429 or response.status_code >= 500:  # noqa: PLR2004 -- HTTP status literals
                transport_attempts += 1
                if transport_attempts > 1:
                    raise PantheonApiError(f"{path}: HTTP {response.status_code}")
                time.sleep(RETRY_SLEEP)
                continue
            if response.status_code != 200:  # noqa: PLR2004 -- HTTP status literal
                raise PantheonApiError(f"{path}: HTTP {response.status_code}")
            try:
                return response.json()
            except json.JSONDecodeError as e:
                raise PantheonApiError(f"{path}: undecodable response body: {e}") from e
```

- [ ] **Step 4: Run the tests**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_dns.py -v
```

Expected: PASS. Then `./run-tests --fast` for the gates.

- [ ] **Step 5: Commit**

```bash
git add find-platform-domains-dns tests/unit/test_find_platform_domains_dns.py
git commit -m "feat(find-platform-domains-dns): Pantheon API session with retry and re-auth"
```

---

### Task 3: Enumeration — sites (with the ignored-cursor detector), environments, domains

**Files:**
- Modify: `find-platform-domains-dns` (append)
- Modify: `tests/unit/test_find_platform_domains_dns.py` (append)

**Interfaces:**
- Consumes: `PantheonApiError`, `RETRY_SLEEP`, `attention` from Tasks 1–2.
- Produces: `SiteListingError`; `org_sites(get, org_id) -> list[dict]` (each `{"id", "name"}`);
  `named_sites(get, names) -> list[dict]`; `site_environments(get, site_id) -> dict`;
  `partition_domains(entries) -> tuple[list[str], set[str]]` (custom domains, platform domains);
  constants `PAGE_LIMIT = 100`, `MAX_PAGES = 100`, `CURSOR_ATTEMPTS = 3`.

- [ ] **Step 1: Write the failing tests**

Append to the test file:

```python
def fake_site(n):
    return {"id": f"id-{n:04d}", "site": {"id": f"id-{n:04d}", "name": f"site-{n:04d}"}}


def paged_get(pages):
    """A fake `get` returning canned site-list pages in order; records the cursors it saw."""
    seen_cursors = []

    def get(path):
        cursor = path.split("start=")[1] if "start=" in path else None
        seen_cursors.append(cursor)
        return pages.pop(0)

    get.cursors = seen_cursors
    return get


def test_org_sites_walks_every_page(fpd):
    pages = [[fake_site(n) for n in range(100)],
             [fake_site(n) for n in range(100, 200)],
             [fake_site(n) for n in range(200, 208)]]
    get = paged_get(pages)
    sites = fpd.org_sites(get, "org-1")
    assert len(sites) == 208
    assert sites[0] == {"id": "id-0000", "name": "site-0000"}
    assert sites[-1]["name"] == "site-0207"
    # The cursor is the LAST id of the previous FULL page (SPEC section 4.1).
    assert get.cursors == [None, "id-0099", "id-0199"]


def test_org_sites_stops_on_a_short_first_page(fpd):
    get = paged_get([[fake_site(n) for n in range(3)]])
    assert len(fpd.org_sites(get, "org-1")) == 3
    assert get.cursors == [None]


def test_org_sites_handles_an_empty_organization(fpd):
    get = paged_get([[]])
    assert fpd.org_sites(get, "org-1") == []


def test_org_sites_handles_a_site_count_that_is_an_exact_multiple_of_the_page_size(fpd):
    # SPEC section 4.1: the FINAL boundary cursor really does return [] (verified live, 7/7).
    # An organization with exactly 200 sites therefore ends on an empty page, which must
    # terminate the loop normally -- NOT trip the zero-new-ids reset detector, which would
    # turn a perfectly good listing into a fatal error.
    pages = [[fake_site(n) for n in range(100)],
             [fake_site(n) for n in range(100, 200)],
             []]
    get = paged_get(pages)
    sites = fpd.org_sites(get, "org-1")
    assert len(sites) == 200
    assert get.cursors == [None, "id-0099", "id-0199"]


def test_org_sites_retries_an_ignored_cursor_then_succeeds(fpd, monkeypatch):
    # SPEC section 4.1: the API sometimes ignores `start` and returns page 1 again.  The loop must
    # notice (zero new ids) and retry the SAME cursor -- not spin, not truncate.
    monkeypatch.setattr(fpd, "RETRY_SLEEP", 0)
    page1 = [fake_site(n) for n in range(100)]
    pages = [page1, list(page1), [fake_site(n) for n in range(100, 105)]]
    get = paged_get(pages)
    sites = fpd.org_sites(get, "org-1")
    assert len(sites) == 105
    assert get.cursors == [None, "id-0099", "id-0099"]     # same cursor, retried


def test_org_sites_gives_up_loudly_when_the_cursor_stays_ignored(fpd, monkeypatch):
    monkeypatch.setattr(fpd, "RETRY_SLEEP", 0)
    page1 = [fake_site(n) for n in range(100)]
    get = paged_get([page1, list(page1), list(page1), list(page1)])
    with pytest.raises(fpd.SiteListingError, match="cursor"):
        fpd.org_sites(get, "org-1")
    assert len(get.cursors) == 4      # first page + CURSOR_ATTEMPTS retries, then it stops


def test_org_sites_caps_the_page_loop(fpd, monkeypatch):
    monkeypatch.setattr(fpd, "MAX_PAGES", 3)
    counter = {"n": 0}

    def get(path):
        counter["n"] += 1
        base = counter["n"] * 100
        return [fake_site(n) for n in range(base, base + 100)]

    with pytest.raises(fpd.SiteListingError, match="page"):
        fpd.org_sites(get, "org-1")


def test_named_sites_resolves_each_name(fpd):
    def get(path):
        assert path.startswith("/site-names/")
        return {"id": "uuid-" + path.rsplit("/", 1)[1]}

    assert fpd.named_sites(get, ["alpha", "beta"]) == [
        {"id": "uuid-alpha", "name": "alpha"},
        {"id": "uuid-beta", "name": "beta"},
    ]


def test_partition_domains_splits_custom_from_platform(fpd):
    entries = [
        {"id": "live-its-wws-test1.pantheonsite.io", "type": "platform"},
        {"id": "WWS-test1.cdn-dev.it.umich.edu", "type": "custom", "primary": True},
        {"id": "www.wws-test1.cdn-dev.it.umich.edu", "type": "custom", "primary": False},
    ]
    custom, platform = fpd.partition_domains(entries)
    # Primary domains ARE included, and everything is normalized.
    assert custom == ["wws-test1.cdn-dev.it.umich.edu", "www.wws-test1.cdn-dev.it.umich.edu"]
    assert platform == {"live-its-wws-test1.pantheonsite.io"}


def test_partition_domains_of_an_uninitialized_environment(fpd):
    entries = [{"id": "live-vpao-accopp.pantheonsite.io", "type": "platform"}]
    assert fpd.partition_domains(entries) == ([], {"live-vpao-accopp.pantheonsite.io"})


def test_site_environments_returns_every_environment(fpd):
    def get(path):
        assert path == "/sites/abc/environments"
        return {"dev": {"initialized": True}, "live": {"initialized": False},
                "test-mark": {"initialized": True}}

    assert sorted(fpd.site_environments(get, "abc")) == ["dev", "live", "test-mark"]
```

- [ ] **Step 2: Run them and confirm they fail**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_dns.py -v
```

Expected: `AttributeError: module has no attribute 'org_sites'` (and friends).

- [ ] **Step 3: Implement the enumeration layer**

```python
PAGE_LIMIT = 100          # the API's documented maximum
MAX_PAGES = 100           # runaway guard: 10,000 sites is far beyond any real organization
CURSOR_ATTEMPTS = 3       # how many times one ignored cursor is retried before giving up


class SiteListingError(Exception):
    """The organization's site list could not be enumerated completely (SPEC G4a/G4b)."""


def org_sites(get, org_id):
    """Every site in the organization, as [{"id", "name"}], in the API's ascending-id order.

    The cursor has a SILENT failure mode, characterized in full in this directory's
    pantheon-api-pagination-bug-report.txt (SPEC section 4.1): `start` is honored ONLY when the
    id is the last element of a page the API has already computed.  Any other id returns the
    FIRST page again, with HTTP 200 and no error.  Three rules follow, all load-bearing:

      * Pass the last id of the page just received, and nothing else.  That is always a
        boundary, which is why this pattern works where arbitrary cursors do not.
      * Stop on a SHORT page, never on an empty one.  An empty page is legitimate (an
        organization holding an exact multiple of PAGE_LIMIT sites ends on one, verified live),
        but an UNRECOGNIZED cursor returns a full first page rather than [], so "loop until
        empty" never terminates once the loop leaves the boundaries.
      * A non-empty page that contributes zero new ids means the cursor was ignored.  Retry the
        SAME cursor; if it keeps happening, raise -- a short list here is a silent truncation of
        the whole sweep, which the CSV cannot reveal.
    """
    collected = {}
    cursor = None
    ignored = 0
    for _page in range(MAX_PAGES):
        path = f"/organizations/{org_id}/memberships/sites?limit={PAGE_LIMIT}"
        if cursor is not None:
            path += f"&start={cursor}"
        page = get(path)
        fresh = [entry for entry in page if entry["site"]["id"] not in collected]
        if page and not fresh:
            ignored += 1
            if ignored >= CURSOR_ATTEMPTS:
                raise SiteListingError(
                    f"the site-list cursor {cursor} was ignored {ignored} times "
                    f"(the API kept returning the first page); only {len(collected)} sites "
                    "were listed, so the sweep would be silently incomplete")
            attention(
                f"site listing cursor {cursor} was ignored (page repeated); retrying "
                f"({ignored}/{CURSOR_ATTEMPTS - 1})")
            time.sleep(RETRY_SLEEP)
            continue
        ignored = 0
        for entry in fresh:
            site = entry["site"]
            collected[site["id"]] = {"id": site["id"], "name": site["name"]}
        if len(page) < PAGE_LIMIT:
            return list(collected.values())
        cursor = page[-1]["site"]["id"]
    raise SiteListingError(
        f"the site list did not end after {MAX_PAGES} pages ({len(collected)} sites so far)")


def named_sites(get, names):
    """Resolve explicit SITE arguments to [{"id", "name"}] without paging the organization."""
    return [{"id": get(f"/site-names/{name}")["id"], "name": name} for name in names]


def site_environments(get, site_id):
    """Every environment of a site, keyed by environment id -- multidevs included."""
    return get(f"/sites/{site_id}/environments")


def partition_domains(entries):
    """Split one environment's domain list into (custom domains, platform domains).

    Primary domains are custom domains and are IN scope.  The platform set is returned because
    the cross-site check (SPEC G13) compares each hit against it -- at zero extra API cost.
    """
    custom = [normalize(e["id"]) for e in entries if e.get("type") == "custom"]
    platform = {normalize(e["id"]) for e in entries if e.get("type") == "platform"}
    return custom, platform
```

- [ ] **Step 4: Prove the pagination tests can go red (PD#14)**

The multi-page and ignored-cursor tests are the only guards against a silently truncated sweep,
so they MUST be shown capable of failing:

```bash
# 1. Temporarily replace the body of org_sites' loop with a single un-cursored request
#    (return the first page and stop).  Run:
./run-tests --fast tests/unit/test_find_platform_domains_dns.py -k "walks_every_page" -v
#    Expected: FAIL (208 != 100).  Restore the code.

# 2. Temporarily delete the `if page and not fresh:` block.  Run:
./run-tests --fast tests/unit/test_find_platform_domains_dns.py -k "cursor" -v
#    Expected: FAIL (the retry test sees the wrong cursor sequence; the give-up test does not
#    raise).  Restore the code.
```

Record both observed failures in the task report — an unproven guard is not a guard.

- [ ] **Step 5: Run the tests, then the gates**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_dns.py -v
./run-tests --fast
```

- [ ] **Step 6: Commit**

```bash
git add find-platform-domains-dns tests/unit/test_find_platform_domains_dns.py
git commit -m "feat(find-platform-domains-dns): site/env/domain enumeration with cursor-reset detection"
```

---

### Task 4: The sweep — CSV rows, integrity checks, counters

**Files:**
- Modify: `find-platform-domains-dns` (append)
- Modify: `tests/unit/test_find_platform_domains_dns.py` (append)

**Interfaces:**
- Consumes: everything from Tasks 1–3.
- Produces: `Counters` (dataclass: `sites`, `envs`, `custom_domains`, `rows`, `indeterminate`);
  `platform_domain_is_dead(name) -> bool`; `Sweeper(get, writer, *, verbose=False)` with
  `.counters`, `.sweep(sites)`, `.sweep_site(site)`, `.sweep_env(site, env_id)`,
  `.check_domain(site, env_id, custom_domain, platform_domains)`.

- [ ] **Step 1: Write the failing tests**

Append to the test file:

```python
import csv
import io


def make_sweeper(fpd, get=None, verbose=False):
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    sweeper = fpd.Sweeper(get or (lambda path: {}), writer, verbose=verbose)
    return sweeper, out


def test_clean_hit_writes_exactly_the_five_fields(fpd, monkeypatch, capsys):
    patch_dns(monkeypatch, fpd, {
        ("occb.bus.umich.edu", "CNAME"): ["live-bus-occb.pantheonsite.io."],
        ("live-bus-occb.pantheonsite.io", "A"): ["23.185.0.4"],
    })
    sweeper, out = make_sweeper(fpd)
    sweeper.check_domain({"id": "uuid", "name": "bus-occb"}, "live", "occb.bus.umich.edu",
                         {"live-bus-occb.pantheonsite.io"})
    assert out.getvalue() == (
        "bus-occb,live,occb.bus.umich.edu,occb.bus.umich.edu,live-bus-occb.pantheonsite.io\n")
    assert sweeper.counters.rows == 1
    assert sweeper.counters.indeterminate == 0
    assert "ATTENTION" not in capsys.readouterr().err


def test_csv_uses_unix_line_endings(fpd, monkeypatch):
    patch_dns(monkeypatch, fpd, {
        ("a.umich.edu", "CNAME"): ["live-x.pantheonsite.io."],
        ("live-x.pantheonsite.io", "A"): ["23.185.0.4"],
    })
    sweeper, out = make_sweeper(fpd)
    sweeper.check_domain({"id": "u", "name": "s"}, "live", "a.umich.edu",
                         {"live-x.pantheonsite.io"})
    assert "\r" not in out.getvalue()


def test_indeterminate_domain_reports_and_counts_but_writes_no_row(fpd, monkeypatch, capsys):
    patch_dns(monkeypatch, fpd, {("a.umich.edu", "CNAME"): dns.resolver.Timeout()})
    sweeper, out = make_sweeper(fpd)
    sweeper.check_domain({"id": "u", "name": "s"}, "live", "a.umich.edu", set())
    assert out.getvalue() == ""
    assert sweeper.counters.indeterminate == 1
    err = capsys.readouterr().err
    assert "ATTENTION" in err and "s.live" in err and "a.umich.edu" in err


def test_dead_platform_domain_warns_but_still_writes_the_row(fpd, monkeypatch, capsys):
    patch_dns(monkeypatch, fpd, {("a.umich.edu", "CNAME"): ["live-gone.pantheonsite.io."]})
    #  ^ no A or AAAA for live-gone -> NoAnswer for both -> definitively dead
    sweeper, out = make_sweeper(fpd)
    sweeper.check_domain({"id": "u", "name": "s"}, "live", "a.umich.edu",
                         {"live-gone.pantheonsite.io"})
    assert out.getvalue().strip().endswith("live-gone.pantheonsite.io")
    assert sweeper.counters.rows == 1
    assert sweeper.counters.indeterminate == 0        # a warning, NOT an indeterminate
    assert "does not resolve" in capsys.readouterr().err


def test_transient_lookup_of_the_platform_domain_does_not_warn(fpd, monkeypatch, capsys):
    # The dead-target check exists to warn; it must never cry wolf on a blip (SPEC G12).
    patch_dns(monkeypatch, fpd, {
        ("a.umich.edu", "CNAME"): ["live-x.pantheonsite.io."],
        ("live-x.pantheonsite.io", "A"): dns.resolver.Timeout(),
    })
    sweeper, out = make_sweeper(fpd)
    sweeper.check_domain({"id": "u", "name": "s"}, "live", "a.umich.edu",
                         {"live-x.pantheonsite.io"})
    assert sweeper.counters.rows == 1
    assert "does not resolve" not in capsys.readouterr().err


def test_cross_site_target_warns_but_still_writes_the_row(fpd, monkeypatch, capsys):
    patch_dns(monkeypatch, fpd, {
        ("a.umich.edu", "CNAME"): ["live-other.pantheonsite.io."],
        ("live-other.pantheonsite.io", "A"): ["23.185.0.4"],
    })
    sweeper, out = make_sweeper(fpd)
    sweeper.check_domain({"id": "u", "name": "s"}, "live", "a.umich.edu",
                         {"live-s.pantheonsite.io"})
    assert sweeper.counters.rows == 1
    assert sweeper.counters.indeterminate == 0
    err = capsys.readouterr().err
    assert "different site" in err and "live-s.pantheonsite.io" in err


def test_sweep_site_counts_environments_and_domains(fpd, monkeypatch):
    patch_dns(monkeypatch, fpd, {})     # every domain is a clean no-hit
    responses = {
        "/sites/uuid/environments": {"dev": {}, "live": {}},
        "/sites/uuid/environments/dev/domains": [
            {"id": "dev-s.pantheonsite.io", "type": "platform"}],
        "/sites/uuid/environments/live/domains": [
            {"id": "live-s.pantheonsite.io", "type": "platform"},
            {"id": "a.umich.edu", "type": "custom"}],
    }
    sweeper, out = make_sweeper(fpd, get=lambda path: responses[path])
    sweeper.sweep_site({"id": "uuid", "name": "s"})
    assert (sweeper.counters.sites, sweeper.counters.envs, sweeper.counters.custom_domains) == (1, 2, 1)
    assert out.getvalue() == ""


def test_failed_environment_listing_counts_once_and_continues(fpd, monkeypatch, capsys):
    patch_dns(monkeypatch, fpd, {})

    def get(path):
        raise fpd.PantheonApiError("HTTP 500")

    sweeper, _ = make_sweeper(fpd, get=get)
    sweeper.sweep([{"id": "u1", "name": "s1"}, {"id": "u2", "name": "s2"}])
    assert sweeper.counters.indeterminate == 2        # once per site, and it kept going
    assert sweeper.counters.sites == 2
    assert "could not list environments" in capsys.readouterr().err


def test_failed_domain_listing_counts_once_and_continues_to_the_next_environment(fpd, monkeypatch, capsys):
    patch_dns(monkeypatch, fpd, {})

    def get(path):
        if path.endswith("/environments"):
            return {"dev": {}, "live": {}}
        if "/dev/" in path:
            raise fpd.PantheonApiError("HTTP 503")
        return [{"id": "live-s.pantheonsite.io", "type": "platform"}]

    sweeper, _ = make_sweeper(fpd, get=get)
    sweeper.sweep_site({"id": "u", "name": "s"})
    assert sweeper.counters.indeterminate == 1
    assert sweeper.counters.envs == 2
    assert "could not list domains" in capsys.readouterr().err
```

- [ ] **Step 2: Run them and confirm they fail**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_dns.py -v
```

Expected: `AttributeError: module has no attribute 'Sweeper'`.

- [ ] **Step 3: Implement the sweep**

Add `import dataclasses` to the imports, then append:

```python
@dataclasses.dataclass
class Counters:
    """What the summary line reports, and what the exit code is derived from."""
    sites: int = 0
    envs: int = 0
    custom_domains: int = 0
    rows: int = 0
    indeterminate: int = 0

    def summary(self):
        return (f"sites={self.sites} envs={self.envs} custom_domains={self.custom_domains} "
                f"rows={self.rows} indeterminate={self.indeterminate}")


def platform_domain_is_dead(name):
    """True only when `name` DEFINITIVELY resolves to no address (SPEC G12).

    A transient or malformed outcome counts as alive: this check exists to warn that the
    downstream rewriter will find no addresses, and a warning that fires on a blip is worse
    than no warning at all.
    """
    for rrtype in ("A", "AAAA"):
        try:
            if list(resolve(name, rrtype)):
                return False
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            continue
        except (dns.resolver.NoNameservers, dns.resolver.Timeout, MalformedNameError):
            return False
    return True


class Sweeper:
    """Walks sites -> environments -> custom domains, writing CSV rows and counting outcomes.

    Holds its collaborators (the API getter, the CSV writer, the counters) rather than threading
    them through five-parameter functions.
    """

    def __init__(self, get, writer, *, verbose=False):
        self._get = get
        self._writer = writer
        self._verbose = verbose
        self.counters = Counters()

    def _progress(self, message):
        if self._verbose:
            print(message, file=sys.stderr, flush=True)

    def sweep(self, sites):
        for number, site in enumerate(sites, start=1):
            self._progress(f"[{number}/{len(sites)}] {site['name']}")
            self.sweep_site(site)

    def sweep_site(self, site):
        self.counters.sites += 1
        try:
            environments = site_environments(self._get, site["id"])
        except PantheonApiError as e:
            attention(f"{site['name']}: could not list environments: {e}")
            self.counters.indeterminate += 1
            return
        for env_id in sorted(environments):
            self.sweep_env(site, env_id)

    def sweep_env(self, site, env_id):
        self.counters.envs += 1
        try:
            entries = self._get(f"/sites/{site['id']}/environments/{env_id}/domains")
        except PantheonApiError as e:
            attention(f"{site['name']}.{env_id}: could not list domains: {e}")
            self.counters.indeterminate += 1
            return
        custom_domains, platform_domains = partition_domains(entries)
        for custom_domain in custom_domains:
            self.counters.custom_domains += 1
            self.check_domain(site, env_id, custom_domain, platform_domains)

    def check_domain(self, site, env_id, custom_domain, platform_domains):
        where = f"{site['name']}.{env_id} {custom_domain}"
        result = walk(custom_domain)
        if result.problem:
            attention(f"{where}: {result.problem}")
            self.counters.indeterminate += 1
            return
        if not result.platform_domain:
            return
        if result.platform_domain not in platform_domains:
            attention(
                f"{where}: points at {result.platform_domain}, which belongs to a different "
                f"site/environment (expected one of: "
                f"{', '.join(sorted(platform_domains)) or 'none listed'})")
        if platform_domain_is_dead(result.platform_domain):
            attention(
                f"{where}: platform domain {result.platform_domain} does not resolve; the "
                "downstream rewrite has no addresses to use")
        self._writer.writerow([site["name"], env_id, custom_domain,
                               result.dns_record, result.platform_domain])
        sys.stdout.flush()
        self.counters.rows += 1
```

- [ ] **Step 4: Run the tests, then the gates**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_dns.py -v
./run-tests --fast
```

- [ ] **Step 5: Commit**

```bash
git add find-platform-domains-dns tests/unit/test_find_platform_domains_dns.py
git commit -m "feat(find-platform-domains-dns): the sweep, CSV output and integrity checks"
```

---

### Task 5: CLI, `main()`, exit codes, and the CLAUDE.md entry

**Files:**
- Modify: `find-platform-domains-dns` (append)
- Modify: `tests/unit/test_find_platform_domains_dns.py` (append)
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: everything from Tasks 1–4.
- Produces: `build_arg_parser() -> argparse.ArgumentParser`; `org_id_from_config(path) -> str`;
  `main(argv) -> int`.

- [ ] **Step 1: Write the failing tests**

Append to the test file:

```python
def test_org_id_is_read_from_the_config(fpd, tmp_path):
    config = tmp_path / "c.toml"
    config.write_text('[Pantheon]\norg_id = "org-uuid"\nplan_info = {}\n')
    assert fpd.org_id_from_config(config) == "org-uuid"


def test_missing_org_id_is_a_named_error(fpd, tmp_path):
    config = tmp_path / "c.toml"
    config.write_text("[Database]\ntype = \"sqlite\"\n")
    with pytest.raises(KeyError):
        fpd.org_id_from_config(config)


def test_parser_rejects_abbreviations(fpd):
    parser = fpd.build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--verb"])          # allow_abbrev=False


def test_parser_accepts_site_arguments(fpd):
    options = fpd.build_arg_parser().parse_args(["-v", "alpha", "beta"])
    assert (options.verbose, options.site) == (True, ["alpha", "beta"])


def test_main_returns_2_when_the_config_has_no_org_id(fpd, tmp_path, capsys):
    config = tmp_path / "c.toml"
    config.write_text("[Database]\n")
    assert fpd.main(["-c", str(config)]) == 2
    assert "org_id" in capsys.readouterr().err


def test_main_returns_2_when_the_config_is_missing(fpd, tmp_path, capsys):
    assert fpd.main(["-c", str(tmp_path / "nope.toml")]) == 2
    assert "nope.toml" in capsys.readouterr().err


def test_main_returns_1_when_the_sweep_had_an_indeterminate(fpd, monkeypatch, tmp_path, capsys):
    config = tmp_path / "c.toml"
    config.write_text('[Pantheon]\norg_id = "org-uuid"\n')
    monkeypatch.setattr(fpd, "machine_token", lambda: "mt")
    monkeypatch.setattr(fpd, "build_session", lambda: _StubSession(indeterminate=True))
    assert fpd.main(["-c", str(config)]) == 1
    assert "indeterminate=1" in capsys.readouterr().err


def test_main_returns_0_on_a_clean_sweep(fpd, monkeypatch, tmp_path, capsys):
    config = tmp_path / "c.toml"
    config.write_text('[Pantheon]\norg_id = "org-uuid"\n')
    monkeypatch.setattr(fpd, "machine_token", lambda: "mt")
    monkeypatch.setattr(fpd, "build_session", lambda: _StubSession(indeterminate=False))
    assert fpd.main(["-c", str(config)]) == 0
    assert "indeterminate=0" in capsys.readouterr().err
```

and, above them, the stub the last two use:

```python
class _StubSession:
    """Stands in for ApiSession: an organization of one site with one environment.

    `indeterminate=True` makes the domains call fail, which is the shortest path to a counted
    indeterminate without touching DNS.
    """

    def __init__(self, *, indeterminate):
        self._indeterminate = indeterminate

    def get(self, path):
        if "/memberships/sites" in path:
            return [{"id": "u1", "site": {"id": "u1", "name": "s1"}}]
        if path.endswith("/environments"):
            return {"live": {}}
        if self._indeterminate:
            raise RuntimeError("unused")     # replaced below by the module's own error type
        return [{"id": "live-s1.pantheonsite.io", "type": "platform"}]
```

> **Implementer note:** `_StubSession.get` must raise the module's `PantheonApiError`, which is
> only reachable through the `fpd` fixture. Make `_StubSession` take the module as its first
> argument (`_StubSession(fpd, indeterminate=True)`) and raise `fpd.PantheonApiError("HTTP 500")`.
> Adjust the two `monkeypatch.setattr(..., lambda: _StubSession(...))` lines accordingly. Do not
> leave a `RuntimeError` in the final test file.

- [ ] **Step 2: Run them and confirm they fail**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_dns.py -v
```

Expected: `AttributeError: module has no attribute 'build_arg_parser'`.

- [ ] **Step 3: Implement the CLI and `main()`**

Add `import argparse` and `import tomllib` to the imports, then append:

```python
def build_arg_parser():
    parser = argparse.ArgumentParser(
        allow_abbrev=False,          # house rule: no --for -> --for-real class of foot-gun
        description="List Pantheon custom domains whose DNS still reaches a platform domain.")
    parser.add_argument("-c", "--config", default="pantheon-sitehealth-emails.toml",
                        help="TOML file to read [Pantheon].org_id from")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="per-site progress on stderr")
    parser.add_argument("site", nargs="*", metavar="SITE",
                        help="site names to sweep; default is the whole organization")
    return parser


def org_id_from_config(path):
    """[Pantheon].org_id from the TOML file.

    Deliberately NOT the main program's config engine: org_id is a literal, so tomllib is the
    whole requirement, and depending on script_context would defeat this script's standalone,
    delete-in-one-commit design.
    """
    with Path(path).open("rb") as handle:
        return tomllib.load(handle)["Pantheon"]["org_id"]


def build_session():
    """The production ApiSession, over one reused connection.  Monkeypatched by the CLI tests."""
    client = httpx.Client(timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT})
    return ApiSession(client, machine_token())


def main(argv):
    """Exit 0 = clean sweep, 1 = completed with indeterminates, 2 = could not complete."""
    options = build_arg_parser().parse_args(argv)
    try:
        org_id = org_id_from_config(options.config)
    except (OSError, tomllib.TOMLDecodeError) as e:
        print(f"ERROR: could not read {options.config}: {e}", file=sys.stderr)
        return 2
    except KeyError as e:
        print(f"ERROR: {options.config} has no [Pantheon].org_id ({e})", file=sys.stderr)
        return 2

    try:
        session = build_session()
    except (MachineTokenError, PantheonApiError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    try:
        sites = (named_sites(session.get, options.site) if options.site
                 else org_sites(session.get, org_id))
    except (PantheonApiError, SiteListingError) as e:
        print(f"ERROR: could not list sites: {e}", file=sys.stderr)
        return 2

    sweeper = Sweeper(session.get, csv.writer(sys.stdout, lineterminator="\n"),
                      verbose=options.verbose)
    sweeper.sweep(sites)
    print(sweeper.counters.summary(), file=sys.stderr)
    return 1 if sweeper.counters.indeterminate else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

Add `import csv` to the imports.

- [ ] **Step 4: Run the tests, then the gates**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_dns.py -v
./run-tests --fast
```

- [ ] **Step 5: Document the utility in `CLAUDE.md`**

Add a subsection at the end of the `## Commands` section, before `## Required runtime
credentials`:

```markdown
### `find-platform-domains-dns` (temporary utility)

A standalone, deletable script — **not** part of the main program and importing nothing from
`psh/`/`check/`/`plugin/` — that lists every custom domain in the organization whose DNS still
reaches a Pantheon platform domain (`*.pantheonsite.io`) by CNAME, as CSV on stdout:
`site_name,site_env,custom_domain,dns_record,platform_domain`. `dns_record` is the FQDN owning
the hitting CNAME record, which is what a downstream rewriter must change. Operator messages and
a `sites=… indeterminate=…` summary go to stderr; exit 0 = clean sweep, 1 = completed with
indeterminates, 2 = could not complete.

```bash
./find-platform-domains-dns its-wws-test1     # one site
./find-platform-domains-dns > domains.csv     # the whole org, ~21 minutes
```

It uses the Pantheon API (machine token from `$PANTHEON_MACHINE_TOKEN` or
`~/.terminus/cache/tokens/`), and its DNS walk is a **copy** of
`check/pantheon_cdn_change/chain.py` plus `psh/dns_classify.py`'s resolver seam — copied, not
imported, so the whole feature is three files. Note the API's site-list cursor has a silent
failure mode (it can return page 1 again instead of the next page); the script detects it and
exits 2 rather than sweeping a truncated site list. **Delete this script after Pantheon's CDN
migration** — checklist in `development/2026-07-28-platform-domain-util/SPEC.md` §14.
```

- [ ] **Step 6: Commit**

```bash
git add find-platform-domains-dns tests/unit/test_find_platform_domains_dns.py CLAUDE.md
git commit -m "feat(find-platform-domains-dns): CLI, exit codes and documentation"
```

---

### Task 6: Live verification and acceptance evidence

**Files:**
- Create: `development/2026-07-28-platform-domain-util/ACCEPTANCE.md`

**Interfaces:**
- Consumes: the finished script.
- Produces: the pasted evidence SPEC §13 requires.

- [ ] **Step 1: Run every SPEC §13 command and capture the real output**

```bash
./run-tests --fast
./run-tests tests/unit/test_find_platform_domains_dns.py -v
./find-platform-domains-dns --help
./find-platform-domains-dns its-wws-test1; echo "exit=$?"
./find-platform-domains-dns bus-occb; echo "exit=$?"
./find-platform-domains-dns its-wws-test1 bus-occb > /tmp/pd.csv 2>/tmp/pd.err
echo "exit=$?"; cat /tmp/pd.csv; cat /tmp/pd.err
./find-platform-domains-dns -c /dev/null; echo "exit=$?"
```

Expected, from live verification on 2026-07-28: `its-wws-test1` produces **zero** rows (its
custom domains CNAME to `fe.cfp2c.edge.pantheon.io`, the new CDN — already migrated);
`bus-occb` produces the row
`bus-occb,live,occb.bus.umich.edu,occb.bus.umich.edu,live-bus-occb.pantheonsite.io`.

**If `bus-occb` produces no row, STOP** — either the site migrated since 2026-07-28 (verify with
`dig +short occb.bus.umich.edu CNAME`, which should print `live-bus-occb.pantheonsite.io.`) or
the walk is broken. Do not adjust the test to match a wrong result.

- [ ] **Step 2: Write `ACCEPTANCE.md` with the pasted output**

One section per command: the exact command, then its **verbatim** output in a fenced block, then
the exit code. Summarized or predicted output is a PD#14 violation and fails review.

- [ ] **Step 3: Answer the SPEC §15 closing-audit questions that a targeted run can answer**

Questions 1–2 need a full-organization sweep, which is an operational run, not an acceptance
step; note them as open. Question 3 (a custom domain on an uninitialized environment) and
question 5 (a short non-final page) can be answered from a full sweep whenever one is run.
Record the answers, or "open — needs a full sweep", in `ACCEPTANCE.md`.

- [ ] **Step 4: Commit**

```bash
git add development/2026-07-28-platform-domain-util/ACCEPTANCE.md
git commit -m "docs(find-platform-domains-dns): acceptance evidence"
```

---

## Self-review notes (completed while writing this plan)

- **Spec coverage.** §3 CLI → Task 5. §4 data sources → Tasks 2–3. §4.1 cursor → Task 3
  (implementation + the red-proof step). §5 output contract → Task 4. §6 algorithm → Task 1
  (walk) + Task 4 (sweep). §7 taxonomy: G1/G2/G3 → Task 5 + Task 2; G4/G4a/G4b → Tasks 3, 5;
  G5/G6 → Task 4; G7 → Task 2; G8–G11 → Task 1 + Task 4; G12/G13/G14 → Task 4. §8 observability
  → `attention()` (Task 1), `_progress` and the summary (Tasks 4–5). §9 seams → honored
  throughout. §10 test list → Tasks 1–5, one-to-one. §13 acceptance → Task 6. §14 deletion
  checklist → recorded in CLAUDE.md (Task 5) and the SPEC.
- **Type consistency.** `WalkResult(dns_record, platform_domain, problem)` is constructed and
  destructured identically in Tasks 1 and 4. `Sweeper.check_domain(site, env_id, custom_domain,
  platform_domains)` matches its call in `sweep_env` and in every test. `org_sites`/`named_sites`
  both return `[{"id", "name"}]`, which is what `Sweeper.sweep_site` reads.
- **Known rough edge, deliberately flagged rather than hidden:** the `_StubSession` sketch in
  Task 5 Step 1 needs the module reference to raise `PantheonApiError`; the implementer note
  under it says exactly what to change. Every other code block is complete as written.

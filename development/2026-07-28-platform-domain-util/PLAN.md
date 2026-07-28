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
- **Every failure has a name** (PD#2): `PantheonApiError`, `PantheonApiShapeError`,
  `SessionExpiredError`, `MachineTokenError`, `MalformedNameError`, `SiteListingError`,
  `StartupError` — seven. No bare
  `except`, no `except Exception` (ruff `E722`/`BLE001` enforce this and the gate is
  `select = ALL`). The single deliberate exception is `main()`'s last-line-of-defence handler,
  which carries an inline `noqa: BLE001` **with its reason** — see Task 5.
- **Exit 1 is reserved.** The only `return 1` in the program is "completed with ≥1
  indeterminate" (SPEC §7). Python exits 1 on any uncaught traceback, so every other outcome
  must be routed to 0, 2, or 130.
- **The ruff findings this code really produces**, all confirmed by materializing the plan and
  running `uvx ruff@0.15.22`: `PLR0911` on `walk` (7 returns), `PLR2004` on each of the four
  HTTP-status literals, `C901`/`PLR0911` if `get()` or `main()` grows (which is why `_renew`
  and `prepare_sweep` are split out), and `SIM105` on a `try/except/pass`; in the test file,
  `E402` if any task appends an import mid-file, `FBT002` on a boolean positional default,
  `RUF059` on an unused unpacked variable, and `F841` on an unused local. Each is handled where
  it arises below. The `tests/**` per-file-ignores block **does** cover `PLR2004` but does
  **not** cover `E402`, `FBT002`, `RUF059` or `F841` — read the block rather than assuming.
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
| `find-platform-domains-dns` | The entire program: DNS walk, API session, enumeration, sweep, CLI. **~700 lines** — measured by materializing this plan's own code blocks, not estimated. Created in Task 1, grown by Tasks 2–5. |
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
import time
from typing import NamedTuple

import dns.exception
import dns.name
import dns.resolver

PLATFORM_SUFFIX = ".pantheonsite.io"
MAX_CNAME_DEPTH = 8
DNS_RETRY_SLEEP = 1.0     # before retrying a NoNameservers only -- see resolve_cname_retrying


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


def skipped(message):
    """A finding that produced NO row and was counted as indeterminate (SPEC section 8)."""
    print(f"SKIPPED: {message}", file=sys.stderr, flush=True)


def warning(message):
    """A finding that still produced its row -- G12, G13, G13a (SPEC section 8).

    Two prefixes rather than one: with a single ATTENTION: prefix an operator reading
    `indeterminate=17` at the end of a sweep cannot grep out those 17, because the
    row-producing warnings are interleaved and look identical.  The count and the log have to
    be reconcilable (PD#5).
    """
    print(f"WARNING: {message}", file=sys.stderr, flush=True)


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
    """resolve(name, "CNAME") with ONE retry on a transient resolver failure.

    The delay depends on which failure it was, and the difference is measured, not assumed
    (SPEC section 6.2): a Timeout has already consumed dnspython's own ~5s lifetime, so
    retrying immediately is right; NoNameservers (SERVFAIL/REFUSED) comes back in ~0.3s, and
    the likeliest cause of a burst of those during a ~1,600-lookup sweep is the recursive
    resolver rate-limiting us -- so an immediate retry just re-fires into the same condition
    and turns every affected domain into an indeterminate for nothing.
    """
    try:
        return resolve(name, "CNAME")
    except dns.resolver.Timeout:
        return resolve(name, "CNAME")
    except dns.resolver.NoNameservers:
        time.sleep(DNS_RETRY_SLEEP)
        return resolve(name, "CNAME")


def walk(custom_domain):  # noqa: PLR0911 -- 7 returns, one per documented outcome in the diagram below; collapsing them into a result variable would hide which branch produced which outcome
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
import csv
import importlib.util
import io
import struct
from importlib.machinery import SourceFileLoader
from pathlib import Path

import dns.resolver
import httpx
import pytest
from helpers.dnsfake import make_resolver

pytestmark = pytest.mark.unit

# EVERY import for EVERY task in this file belongs in this block.  Later tasks append tests, not
# imports: ruff's E402 (module-level import not at top of file) is not in the tests/** ignore
# list, so an `import httpx` half way down the file fails the gate.

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
    # A name that merely CONTAINS the suffix is not a platform domain.  BOTH forms matter:
    # the first has no leading dot, so it defeats only a naive endswith("pantheonsite.io");
    # the second embeds ".pantheonsite.io" exactly, so it is the one that catches a suffix
    # check wrongly written as a substring check.  This pair is the Task 1 red-proof target.
    assert fpd.is_platform_domain("pantheonsite.io.evil.example") is False
    assert fpd.is_platform_domain("x.pantheonsite.io.evil.example") is False
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
    # patch_dns is NOT optional here: without it this test queries real DNS for h0.umich.edu,
    # returns a clean no-hit, and fails for a reason that has nothing to do with the hop limit.
    zone = {(f"h{i}.umich.edu", "CNAME"): [f"h{i + 1}.umich.edu."] for i in range(20)}
    patch_dns(monkeypatch, fpd, zone)
    assert "exceeds 8 hops" in fpd.walk("h0.umich.edu").problem


def test_custom_domain_that_is_itself_a_platform_domain_is_indeterminate(fpd, monkeypatch):
    calls = []
    patch_dns(monkeypatch, fpd, {}, calls)
    result = fpd.walk("live-x.pantheonsite.io")
    assert "itself a platform domain" in result.problem
    assert calls == []          # decided without a single DNS query


# -- The copied resolve() itself (SPEC section 10 item 9).  Every test above monkeypatches the
# -- seam, so without these two the copied code is never executed -- and copied code with its
# -- safety net removed is exactly where a transcription slip ships green (PD#14).  Ported from
# -- tests/unit/test_dns_classify.py, which covers the original.

def test_resolve_converts_a_malformed_name_into_the_named_exception(fpd):
    # An out-of-range byte escape: dns.name.from_text raises the stdlib struct.error, which is
    # not a DNSException at all, so nothing downstream would catch it.
    with pytest.raises(fpd.MalformedNameError):
        fpd.resolve("\\300.com", "CNAME")


def test_wire_level_struct_error_is_transient_not_a_malformed_name(fpd, monkeypatch):
    # THE distinction SPEC section 6.3 calls load-bearing: dnspython also raises struct.error
    # from its TCP length-prefix unpack -- i.e. from garbled wire data on a perfectly valid
    # name.  Reporting that as "not a valid DNS name" would make the walk call it a definitive
    # answer, when it is a transient one.
    def boom(*_args, **_kwargs):
        raise struct.error("unpack requires a buffer of 2 bytes")

    monkeypatch.setattr(fpd.dns.resolver, "resolve", boom)
    with pytest.raises(dns.resolver.NoNameservers):
        fpd.resolve("valid.umich.edu", "CNAME")
```

- [ ] **Step 4: Run the tests and watch them fail for the right reason**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_dns.py -v
```

Expected before Step 1's code exists: collection errors / `AttributeError`. After Step 1 they
should pass.

**Verify a test can go red for its own reason** (PD#14): temporarily change
`is_platform_domain`'s body to `return PLATFORM_SUFFIX in normalize(name)` and confirm
`test_normalize_and_is_platform_domain` fails on the **`x.pantheonsite.io.evil.example`**
assertion, then restore it. That name is the one that discriminates: it embeds
`.pantheonsite.io` exactly, so a substring check wrongly accepts it, while
`pantheonsite.io.evil.example` (no leading dot) does **not** discriminate — verified, the
mutation leaves that assertion green. Proving the wrong assertion is how a red-proof becomes
theatre.

Do **not** use the hop-limit test for this proof. An earlier draft of this plan did, and that
test was itself broken (it never installed its DNS fake), so the "proof" would have observed a
red test that was red for an unrelated reason — a lying instrument proving another instrument.

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
- Produces: `PantheonApiError`; `PantheonApiShapeError`; `SessionExpiredError`;
  `MachineTokenError`; `machine_token() -> str`;
  `ApiSession(client, machine_token, notify=None)` with `.get(path) -> Any` and `.token`;
  constants `API_BASE = "https://api.pantheon.io/v0"`, `RETRY_SLEEP = 2.0`,
  `HTTP_TIMEOUT = 30.0`, `USER_AGENT = "find-platform-domains-dns"`.

- [ ] **Step 1: Write the failing tests**

Append to the test file:

```python
def make_session(fpd, handler, notify=None):
    """An ApiSession whose transport is a MockTransport running `handler`.

    No `import httpx` here -- it is in the import block at the top of the file (Task 1).
    """
    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)
    return fpd.ApiSession(client, "fake-machine-token", notify=notify)


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


def test_401_twice_raises_session_expired_not_a_plain_api_error(fpd):
    # SPEC G7a.  It must NOT be a PantheonApiError: the sweep catches those per site, so a
    # revoked token would otherwise turn into ~400 indeterminates instead of an abort.
    def handler(request):
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": "sess"})
        return httpx.Response(401, json={"error": "nope"})

    with pytest.raises(fpd.SessionExpiredError, match="expired or revoked"):
        make_session(fpd, handler).get("/sites/abc")
    assert not issubclass(fpd.SessionExpiredError, fpd.PantheonApiError)


def test_failure_to_reauthenticate_is_also_session_expired(fpd):
    calls = []

    def handler(request):
        if request.url.path.endswith("/authorize/machine-token"):
            calls.append(1)
            # The first (constructor) authentication succeeds; the mid-sweep one fails.
            return httpx.Response(200, json={"session": "sess"}) if len(calls) == 1 \
                else httpx.Response(403, text="revoked")
        return httpx.Response(401, json={"error": "expired"})

    with pytest.raises(fpd.SessionExpiredError, match="could not re-authenticate"):
        make_session(fpd, handler).get("/sites/abc")


def test_reauthentication_notifies_the_caller(fpd):
    # SPEC section 8: the G7 note is the operator's only sign that the session expired.
    notes = []
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": f"sess-{calls.count('/v0/authorize/machine-token')}"})
        if calls.count("/v0/sites/abc") == 1:
            return httpx.Response(401, json={"error": "expired"})
        return httpx.Response(200, json={"ok": True})

    assert make_session(fpd, handler, notify=notes.append).get("/sites/abc") == {"ok": True}
    assert notes == ["session expired; re-authenticated"]


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


def test_machine_token_undecodable_cache_file_is_named(fpd, monkeypatch, tmp_path):
    monkeypatch.delenv("PANTHEON_MACHINE_TOKEN", raising=False)
    cache = tmp_path / ".terminus" / "cache" / "tokens"
    cache.mkdir(parents=True)
    (cache / "someone@umich.edu").write_text("this is not json")
    monkeypatch.setattr(fpd.Path, "home", staticmethod(lambda: tmp_path))
    with pytest.raises(fpd.MachineTokenError, match="could not read"):
        fpd.machine_token()


def test_machine_token_cache_file_without_a_token_key_is_named(fpd, monkeypatch, tmp_path):
    monkeypatch.delenv("PANTHEON_MACHINE_TOKEN", raising=False)
    cache = tmp_path / ".terminus" / "cache" / "tokens"
    cache.mkdir(parents=True)
    (cache / "someone@umich.edu").write_text('{"email": "someone@umich.edu"}')
    monkeypatch.setattr(fpd.Path, "home", staticmethod(lambda: tmp_path))
    with pytest.raises(fpd.MachineTokenError, match="no 'token' key"):
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


class PantheonApiShapeError(PantheonApiError):
    """A Pantheon API response decoded as JSON but did not have the documented shape.

    A subclass of PantheonApiError on purpose: the sweep already treats an API failure for one
    site or environment as G5/G6 (report, count one indeterminate, carry on), and an
    unexpected shape deserves exactly that treatment rather than a traceback at exit 1
    (SPEC G17).
    """


class SessionExpiredError(Exception):
    """Re-authentication failed, or the retried request 401'd again (SPEC G7a).

    Deliberately NOT a subclass of PantheonApiError: the sweep catches PantheonApiError per
    site and per environment, so if this were one, a revoked machine token 5 minutes into a
    38-minute sweep would degrade into one indeterminate per remaining site -- ~400 ATTENTION
    lines, exit 1, and 33 more minutes of pointless work -- instead of stopping. It must
    propagate to main() and abort with exit 2.
    """


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

    def __init__(self, client, token_value, notify=None):
        self._client = client
        self._machine_token = token_value
        # notify(message) is called when the session is re-authenticated mid-sweep (G7).  main()
        # passes a function that prints under -v; without it a session expiry is invisible at
        # every verbosity, which SPEC section 8 explicitly promises it is not.
        self._notify = notify or (lambda _message: None)
        self.token = self._authenticate()

    def _authenticate(self):
        try:
            response = self._client.post(
                f"{API_BASE}/authorize/machine-token",
                json={"machine_token": self._machine_token, "client": USER_AGENT})
        except httpx.HTTPError as e:
            raise PantheonApiError(f"could not authenticate to Pantheon: {e}") from e
        if response.status_code != 200:  # noqa: PLR2004 -- HTTP status literal
            raise PantheonApiError(
                f"could not authenticate to Pantheon: HTTP {response.status_code}")
        try:
            return response.json()["session"]
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise PantheonApiError(f"authentication response had no session token: {e}") from e

    def _renew(self, path, *, reauthed):
        """Re-authenticate after a 401, or raise SessionExpiredError (SPEC G7a).

        Split out of get() to keep that method under ruff's C901 complexity limit -- and it
        reads better anyway: get() dispatches on status, this owns the session lifecycle.
        """
        if reauthed:
            # A second 401 on a session we just minted means the machine token itself is
            # revoked or expired.  Retrying forever, or counting it as one site's
            # indeterminate, both waste the rest of a 38-minute sweep.
            raise SessionExpiredError(
                f"{path}: HTTP 401 again after re-authenticating -- the machine token is "
                "expired or revoked")
        try:
            self.token = self._authenticate()
        except PantheonApiError as e:
            raise SessionExpiredError(f"could not re-authenticate mid-sweep: {e}") from e
        self._notify("session expired; re-authenticated")

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
            if response.status_code == 401:  # noqa: PLR2004 -- HTTP status literal
                self._renew(path, reauthed=reauthed)
                reauthed = True
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
- Produces: `SiteListingError`; `_require(payload, key, where)`;
  `org_sites(get, org_id) -> list[dict]` (each `{"id", "name"}`);
  `named_sites(get, names) -> list[dict]` (name from the API response, path percent-encoded); `site_environments(get, site_id) -> dict`;
  `partition_domains(entries) -> tuple[list[str], set[str]]` (custom domains, platform domains);
  constants `PAGE_LIMIT = 100`, `MAX_PAGES = 100`, `CURSOR_ATTEMPTS = 3`.

- [ ] **Step 1: Write the failing tests**

Append to the test file:

```python
def fake_site(n):
    # The membership id deliberately DIFFERS from the site id.  In production they are equal for
    # all 408 sites, but SPEC section 4.1 says that equality "is an observation, not a contract"
    # and requires the cursor to be site.id -- so the fixture must be able to tell them apart,
    # or the one decision that section argues for has no red-capable test (PD#14).
    return {"id": f"mem-{n:04d}", "site": {"id": f"id-{n:04d}", "name": f"site-{n:04d}"}}


def paged_get(pages):
    """A fake `get` returning canned site-list pages in order; records the cursors it saw."""
    seen_cursors = []

    def get(path):
        cursor = path.split("start=")[1] if "start=" in path else None
        seen_cursors.append(cursor)
        assert pages, "the code requested more pages than this test provided"
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
    # The cursor is the LAST *site* id of the previous FULL page -- "id-0099", never the
    # membership id "mem-0099" (SPEC section 4.1).
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


def test_org_sites_retries_an_ignored_cursor_then_succeeds(fpd, monkeypatch, capsys):
    # SPEC section 4.1: the API sometimes ignores `start` and returns page 1 again.  The loop must
    # notice (zero new ids) and retry the SAME cursor -- not spin, not truncate.
    monkeypatch.setattr(fpd, "RETRY_SLEEP", 0)
    page1 = [fake_site(n) for n in range(100)]
    pages = [page1, list(page1), [fake_site(n) for n in range(100, 105)]]
    get = paged_get(pages)
    sites = fpd.org_sites(get, "org-1")
    assert len(sites) == 105
    assert get.cursors == [None, "id-0099", "id-0099"]     # same cursor, retried
    # The ATTENTION line is the ONLY thing that distinguishes a detector-driven retry from a
    # loop that blunders into repeating the same cursor by accident -- both produce the cursor
    # sequence above, so without this assertion the test passes with the detector deleted.
    assert "cursor id-0099 was ignored" in capsys.readouterr().err


def test_org_sites_gives_up_loudly_when_the_cursor_stays_ignored(fpd, monkeypatch):
    monkeypatch.setattr(fpd, "RETRY_SLEEP", 0)
    page1 = [fake_site(n) for n in range(100)]
    # A fifth, short page is provided deliberately.  With the detector the loop never reaches
    # it (it raises after the third ignored page).  WITHOUT the detector the loop consumes it
    # and returns normally -- so the failure is a clean "DID NOT RAISE" rather than an
    # IndexError from a test fixture running out of canned pages.
    get = paged_get([page1, list(page1), list(page1), list(page1),
                     [fake_site(n) for n in range(100, 105)]])
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


def test_named_sites_resolves_each_name_and_prefers_the_canonical_name(fpd):
    def get(path):
        assert path.startswith("/site-names/")
        slug = path.rsplit("/", 1)[1]
        # The real endpoint returns the canonical name alongside the id (verified live).
        return {"id": "uuid-" + slug, "name": slug.lower()}

    assert fpd.named_sites(get, ["Alpha", "beta"]) == [
        {"id": "uuid-Alpha", "name": "alpha"},   # canonical name wins over the argv casing
        {"id": "uuid-beta", "name": "beta"},
    ]


def test_named_sites_percent_encodes_the_site_name(fpd):
    seen = []

    def get(path):
        seen.append(path)
        return {"id": "uuid", "name": "x"}

    fpd.named_sites(get, ["we#ird/name?x"])
    # Unencoded, '#' would truncate the path and '?' would start a query string, silently
    # requesting a different resource instead of failing.
    assert seen == ["/site-names/we%23ird%2Fname%3Fx"]


def test_unexpected_response_shapes_raise_the_named_error(fpd):
    # SPEC G17: a bare KeyError here would be an uncaught traceback exiting 1, which section 7
    # reserves for "completed with indeterminates".
    with pytest.raises(fpd.PantheonApiShapeError):
        fpd.org_sites(lambda _path: {"not": "a list"}, "org-1")
    with pytest.raises(fpd.PantheonApiShapeError):
        fpd.org_sites(lambda _path: [{"no_site_key": 1}], "org-1")
    with pytest.raises(fpd.PantheonApiShapeError):
        fpd.site_environments(lambda _path: ["dev", "live"], "abc")
    with pytest.raises(fpd.PantheonApiShapeError):
        fpd.partition_domains({"not": "a list"})
    with pytest.raises(fpd.PantheonApiShapeError):
        fpd.named_sites(lambda _path: {"no": "id"}, ["alpha"])
    # The keys the SWEEP reads later, not just the ones the listing reads: a bare KeyError on
    # site["name"] escapes main() entirely and exits 1 (SPEC section 10 item 16).
    with pytest.raises(fpd.PantheonApiShapeError):
        fpd.org_sites(lambda _path: [{"site": {"id": "u1"}}], "org-1")
    with pytest.raises(fpd.PantheonApiShapeError):
        fpd.named_sites(lambda _path: {"id": "uuid"}, ["alpha"])
    with pytest.raises(fpd.PantheonApiShapeError):
        fpd.partition_domains(["a-string-not-an-object"])


def test_partition_domains_splits_custom_from_platform(fpd):
    entries = [
        {"id": "live-its-wws-test1.pantheonsite.io", "type": "platform"},
        {"id": "WWS-test1.cdn-dev.it.umich.edu", "type": "custom", "primary": True},
        {"id": "www.wws-test1.cdn-dev.it.umich.edu", "type": "custom", "primary": False},
    ]
    custom, platform, unknown = fpd.partition_domains(entries)
    # Primary domains ARE included, and everything is normalized.
    assert custom == ["wws-test1.cdn-dev.it.umich.edu", "www.wws-test1.cdn-dev.it.umich.edu"]
    assert platform == {"live-its-wws-test1.pantheonsite.io"}
    assert unknown == []


def test_partition_domains_of_an_uninitialized_environment(fpd):
    entries = [{"id": "live-vpao-accopp.pantheonsite.io", "type": "platform"}]
    assert fpd.partition_domains(entries) == ([], {"live-vpao-accopp.pantheonsite.io"}, [])


def test_partition_domains_reports_an_unknown_type_instead_of_dropping_it(fpd):
    # SPEC G6a.  `custom`/`platform` is an observation, not a documented enumeration, and a
    # silently dropped domain is the one failure the CSV cannot reveal (SPEC section 1).
    entries = [
        {"id": "live-s.pantheonsite.io", "type": "platform"},
        {"id": "something.umich.edu", "type": "brand-new-type"},
    ]
    custom, _platform, unknown = fpd.partition_domains(entries)
    assert custom == []
    assert unknown == [("something.umich.edu", "brand-new-type")]


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

Add `from urllib.parse import quote` to the imports at the top of the script, then append:

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
        if not isinstance(page, list):
            raise PantheonApiShapeError(f"{path}: expected a JSON array of memberships")
        for entry in page:
            site = _require(entry, "site", path)
            _require(site, "id", path)
            _require(site, "name", path)      # read later by the sweep; a bare KeyError there
                                              # escapes main() entirely and exits 1
        fresh = [entry for entry in page if entry["site"]["id"] not in collected]
        if page and not fresh:
            ignored += 1
            if ignored >= CURSOR_ATTEMPTS:
                raise SiteListingError(
                    f"the site-list cursor {cursor} was ignored {ignored} times "
                    f"(the API kept returning the first page); only {len(collected)} sites "
                    "were listed, so the sweep would be silently incomplete. "
                    "Run 'terminus org:site:list --format=json | jq length' to check whether "
                    f"{len(collected)} is the true site count (SPEC section 4.1)")
            skipped(
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
    """Resolve explicit SITE arguments to [{"id", "name"}] without paging the organization.

    quote(..., safe="") is not decoration: an argument containing '#' truncates the path and an
    argument containing '?' starts a query string, so an unencoded name would silently request a
    DIFFERENT resource instead of failing.  The name in the returned dict comes from the API
    response, not from argv, so a differently-cased argument cannot produce CSV rows whose
    site_name the downstream script fails to match (SPEC section 3).
    """
    resolved = []
    for name in names:
        where = f"/site-names/{name}"
        answer = get(f"/site-names/{quote(name, safe='')}")
        # BOTH keys go through _require.  An `answer.get("name", name)` fallback would silently
        # reinstate the argv spelling -- the exact mismatch SPEC section 3 requires be avoided.
        resolved.append({"id": _require(answer, "id", where),
                         "name": _require(answer, "name", where)})
    return resolved


def _require(payload, key, where):
    """payload[key], or a named PantheonApiShapeError naming what was missing (SPEC G17).

    Without this, an unexpected response shape is a bare KeyError -- an uncaught traceback whose
    exit code is 1, which SPEC section 7 reserves for "completed with indeterminates".
    """
    if not isinstance(payload, dict) or key not in payload:
        raise PantheonApiShapeError(f"{where}: response has no '{key}'")
    return payload[key]


def site_environments(get, site_id):
    """Every environment of a site, keyed by environment id -- multidevs included."""
    path = f"/sites/{site_id}/environments"
    environments = get(path)
    if not isinstance(environments, dict):
        # sorted() over a list would silently iterate strings, and the domains calls built from
        # them would 404 one by one -- a whole site quietly mis-swept (SPEC G17).
        raise PantheonApiShapeError(f"{path}: expected a JSON object keyed by environment id")
    return environments


def partition_domains(entries):
    """Split one environment's domain list into (custom domains, platform domains).

    Primary domains are custom domains and are IN scope.  The platform set is returned because
    the cross-site check (SPEC G13) compares each hit against it -- at zero extra API cost.
    """
    if not isinstance(entries, list):
        raise PantheonApiShapeError("domains: expected a JSON array")
    custom, platform, unknown = [], set(), []
    for entry in entries:
        if not isinstance(entry, dict):
            # A JSON array of strings would otherwise reach entry.get() and raise a bare
            # AttributeError, which escapes as an exit-1 traceback.
            raise PantheonApiShapeError(f"domains: expected objects, got {type(entry).__name__}")
        name = normalize(_require(entry, "id", "domains"))
        kind = entry.get("type")
        if kind == "custom":
            custom.append(name)
        elif kind == "platform":
            platform.add(name)
        else:
            # G6a.  `type` is custom|platform in every entry observed, but that is an
            # observation and not a documented enumeration -- so an unrecognized value is
            # reported and counted, never silently dropped (SPEC section 1: the expensive
            # failure is a missing row that the CSV cannot reveal).
            unknown.append((name, kind))
    return custom, platform, unknown
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
  `platform_domain_is_dead(name) -> bool`; `Sweeper(get, writer, stream, *, verbose=False)`
  with `.counters`, `.last_site`, `.remaining`, `.sweep(sites)`, `.sweep_site(site)`,
  `.sweep_env(site, env_id)`, `.check_domain(site, env_id, custom_domain, platform_domains)`.

- [ ] **Step 1: Write the failing tests**

Append to the test file:

```python
def make_sweeper(fpd, get=None, *, verbose=False):
    """A Sweeper writing into an in-memory stream.

    `verbose` is keyword-only: ruff's FBT002 rejects a boolean positional default, and the
    tests/** per-file-ignores block covers FBT003 (positional bools at call sites), not FBT002.
    No `import csv`/`import io` here -- they are in the top-of-file import block (Task 1).
    """
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    sweeper = fpd.Sweeper(get or (lambda path: {}), writer, out, verbose=verbose)
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
    assert capsys.readouterr().err == ""      # a clean hit says nothing at all


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
    # SKIPPED:, not WARNING: -- this domain produced no row and WAS counted (SPEC section 8).
    assert err.startswith("SKIPPED:")
    assert "s.live" in err and "a.umich.edu" in err


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
    sweeper, _out = make_sweeper(fpd)
    sweeper.check_domain({"id": "u", "name": "s"}, "live", "a.umich.edu",
                         {"live-x.pantheonsite.io"})
    assert sweeper.counters.rows == 1
    assert "does not resolve" not in capsys.readouterr().err


def test_cross_site_target_warns_but_still_writes_the_row(fpd, monkeypatch, capsys):
    patch_dns(monkeypatch, fpd, {
        ("a.umich.edu", "CNAME"): ["live-other.pantheonsite.io."],
        ("live-other.pantheonsite.io", "A"): ["23.185.0.4"],
    })
    sweeper, _out = make_sweeper(fpd)
    sweeper.check_domain({"id": "u", "name": "s"}, "live", "a.umich.edu",
                         {"live-s.pantheonsite.io"})
    assert sweeper.counters.rows == 1
    assert sweeper.counters.indeterminate == 0
    err = capsys.readouterr().err
    assert "different site" in err and "live-s.pantheonsite.io" in err


def test_mid_chain_hit_warns_that_the_record_is_an_alias(fpd, monkeypatch, capsys):
    # SPEC G13a.  Rewriting alias.umich.edu moves every other name pointing at it.
    patch_dns(monkeypatch, fpd, {
        ("www.example.umich.edu", "CNAME"): ["alias.umich.edu."],
        ("alias.umich.edu", "CNAME"): ["live-s.pantheonsite.io."],
        ("live-s.pantheonsite.io", "A"): ["23.185.0.4"],
    })
    sweeper, out = make_sweeper(fpd)
    sweeper.check_domain({"id": "u", "name": "s"}, "live", "www.example.umich.edu",
                         {"live-s.pantheonsite.io"})
    assert out.getvalue().split(",")[3] == "alias.umich.edu"
    err = capsys.readouterr().err
    assert "the record to change is alias.umich.edu" in err
    assert sweeper.counters.rows == 1


def test_direct_hit_does_not_warn_about_an_alias(fpd, monkeypatch, capsys):
    patch_dns(monkeypatch, fpd, {
        ("a.umich.edu", "CNAME"): ["live-s.pantheonsite.io."],
        ("live-s.pantheonsite.io", "A"): ["23.185.0.4"],
    })
    sweeper, _out = make_sweeper(fpd)
    sweeper.check_domain({"id": "u", "name": "s"}, "live", "a.umich.edu",
                         {"live-s.pantheonsite.io"})
    assert "the record to change is" not in capsys.readouterr().err


def test_each_row_is_flushed_as_it_is_written(fpd, monkeypatch):
    # SPEC section 5: a 38-minute sweep must be watchable with tail -f.  Testable only because
    # the stream is injected (SPEC section 9).
    flushes = []
    patch_dns(monkeypatch, fpd, {
        ("a.umich.edu", "CNAME"): ["live-s.pantheonsite.io."],
        ("live-s.pantheonsite.io", "A"): ["23.185.0.4"],
    })
    sweeper, out = make_sweeper(fpd)
    monkeypatch.setattr(out, "flush", lambda: flushes.append(len(out.getvalue())))
    sweeper.check_domain({"id": "u", "name": "s"}, "live", "a.umich.edu",
                         {"live-s.pantheonsite.io"})
    assert len(flushes) == 1
    assert flushes[0] > 0        # flushed AFTER the row was written, not before


def test_verbose_reports_per_site_counts(fpd, monkeypatch, capsys):
    patch_dns(monkeypatch, fpd, {})
    responses = {
        "/sites/uuid/environments": {"dev": {}, "live": {}},
        "/sites/uuid/environments/dev/domains": [
            {"id": "dev-s.pantheonsite.io", "type": "platform"}],
        "/sites/uuid/environments/live/domains": [
            {"id": "live-s.pantheonsite.io", "type": "platform"},
            {"id": "a.umich.edu", "type": "custom"}],
    }
    sweeper, _out = make_sweeper(fpd, get=lambda path: responses[path], verbose=True)
    sweeper.sweep_site({"id": "uuid", "name": "s"})
    assert "s: 2 environments, 1 custom domains" in capsys.readouterr().err


def test_a_session_expiry_aborts_the_sweep_instead_of_counting_indeterminates(fpd, monkeypatch):
    # SPEC G7a.  If SessionExpiredError were caught per site, a revoked token 5 minutes into a
    # 38-minute sweep would emit ~400 ATTENTION lines and exit 1 instead of stopping.
    patch_dns(monkeypatch, fpd, {})

    def get(path):
        raise fpd.SessionExpiredError("token revoked")

    sweeper, _out = make_sweeper(fpd, get=get)
    with pytest.raises(fpd.SessionExpiredError):
        sweeper.sweep([{"id": "u1", "name": "s1"}, {"id": "u2", "name": "s2"}])
    assert sweeper.counters.indeterminate == 0


def test_a_malformed_domains_payload_is_one_environments_indeterminate(fpd, monkeypatch, capsys):
    # SPEC G17 + section 10 item 17.  partition_domains sits INSIDE sweep_env's try; outside
    # it, one malformed payload aborted every remaining site of a 38-minute sweep.
    patch_dns(monkeypatch, fpd, {})

    def get(path):
        if path.endswith("/environments"):
            return {"live": {}}
        return {"not": "a list"} if "/u1/" in path else []

    sweeper, _out = make_sweeper(fpd, get=get)
    sweeper.sweep([{"id": "u1", "name": "s1"}, {"id": "u2", "name": "s2"}])
    assert sweeper.counters.sites == 2          # it kept going
    assert sweeper.counters.indeterminate == 1
    assert "SKIPPED: s1.live: could not list domains" in capsys.readouterr().err


def test_sweep_records_where_it_stopped(fpd, monkeypatch):
    # SPEC section 7.3: without this an aborted 38-minute sweep gives the operator no way to
    # resume except starting over.
    patch_dns(monkeypatch, fpd, {})
    sweeper, _out = make_sweeper(
        fpd, get=lambda path: {} if path.endswith("environments") else [])
    sweeper.sweep([{"id": "u1", "name": "s1"}, {"id": "u2", "name": "s2"}])
    assert sweeper.last_site == "s2"
    assert sweeper.remaining == []


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

    def __init__(self, get, writer, stream, *, verbose=False):
        self._get = get
        self._writer = writer
        # The stream is INJECTED rather than reaching for sys.stdout, so that the "flush after
        # every row" requirement (SPEC section 5) is testable: in a test the writer and
        # sys.stdout are unrelated objects, so nothing would pin the flush (SPEC section 9).
        self._stream = stream
        self._verbose = verbose
        self.counters = Counters()
        # SPEC section 7.3's "where did it stop" line.  Initialized here, not only in sweep(),
        # so report_stop() cannot raise AttributeError while reporting some other failure.
        self.last_site = ""       # the last site that COMPLETED
        self.current_site = ""     # the site in flight, for "Stopped during <site>"
        self.remaining = []

    def _progress(self, message):
        if self._verbose:
            print(message, file=sys.stderr, flush=True)

    def sweep(self, sites):
        self.remaining = list(sites)
        for number, site in enumerate(sites, start=1):
            self._progress(f"[{number}/{len(sites)}] {site['name']}")
            self.current_site = site["name"]
            self.sweep_site(site)
            self.last_site = site["name"]
            self.remaining = list(sites[number:])

    def sweep_site(self, site):
        self.counters.sites += 1
        before = (self.counters.envs, self.counters.custom_domains)
        try:
            environments = site_environments(self._get, site["id"])
        except PantheonApiError as e:
            # PantheonApiShapeError is a PantheonApiError, so an unexpected shape lands here too
            # (SPEC G17).  SessionExpiredError deliberately is NOT one -- it must propagate.
            skipped(f"{site['name']}: could not list environments: {e}")
            self.counters.indeterminate += 1
            return
        for env_id in sorted(environments):
            self.sweep_env(site, env_id)
        self._progress(f"    {site['name']}: {self.counters.envs - before[0]} environments, "
                       f"{self.counters.custom_domains - before[1]} custom domains")

    def sweep_env(self, site, env_id):
        self.counters.envs += 1
        try:
            entries = self._get(f"/sites/{site['id']}/environments/{env_id}/domains")
            # INSIDE the try on purpose: partition_domains raises PantheonApiShapeError on a
            # malformed payload, and SPEC G17 says a shape error is reported "exactly like
            # G4/G5/G6 depending on which call produced it" -- i.e. one environment's
            # indeterminate, not the end of a 38-minute sweep.  Outside the try, one bad
            # payload aborted everything after it.
            custom_domains, platform_domains, unknown = partition_domains(entries)
        except PantheonApiError as e:
            skipped(f"{site['name']}.{env_id}: could not list domains: {e}")
            self.counters.indeterminate += 1
            return
        for name, kind in unknown:          # G6a
            skipped(f"{site['name']}.{env_id} {name}: unknown domain type {kind!r}; "
                    "not examined")
            self.counters.indeterminate += 1
        for custom_domain in custom_domains:
            self.counters.custom_domains += 1
            self.check_domain(site, env_id, custom_domain, platform_domains)

    def check_domain(self, site, env_id, custom_domain, platform_domains):
        where = f"{site['name']}.{env_id} {custom_domain}"
        result = walk(custom_domain)
        if result.problem:
            skipped(f"{where}: {result.problem}")
            self.counters.indeterminate += 1
            return
        if not result.platform_domain:
            return
        if result.dns_record != custom_domain:
            # SPEC G13a.  The record the downstream rewriter must change is a mid-chain alias,
            # not this site's own domain -- so rewriting it moves every other name pointing at
            # it, possibly in a zone this team does not control.
            warning(
                f"{where}: the record to change is {result.dns_record}, not the custom domain; "
                "verify who else points at it before rewriting")
        if result.platform_domain not in platform_domains:
            warning(
                f"{where}: points at {result.platform_domain}, which belongs to a different "
                f"site/environment (expected one of: "
                f"{', '.join(sorted(platform_domains)) or 'none listed'})")
        if platform_domain_is_dead(result.platform_domain):
            warning(
                f"{where}: platform domain {result.platform_domain} does not resolve; the "
                "downstream rewrite has no addresses to use")
        self._writer.writerow([site["name"], env_id, custom_domain,
                               result.dns_record, result.platform_domain])
        self._stream.flush()      # so a 38-minute sweep can be watched with tail -f
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
  `build_session(notify=None) -> ApiSession`; `StartupError`;
  `prepare_sweep(options, note) -> tuple[ApiSession, list[dict]]`; `report_stop(sweeper, reason)`;
  `main(argv) -> int` (0 / 1 / 2 / 130 per SPEC §7).

- [ ] **Step 1: Write the failing tests**

Append to the test file:

```python
def test_org_id_is_read_from_the_config(fpd, tmp_path):
    config = tmp_path / "c.toml"
    config.write_text('[Pantheon]\norg_id = "org-uuid"\nplan_info = {}\n')
    assert fpd.org_id_from_config(config) == "org-uuid"


def test_missing_org_id_raises_out_of_the_low_level_helper(fpd, tmp_path):
    # org_id_from_config is deliberately thin; prepare_sweep is what converts this into a
    # StartupError.  The exit-code contract is pinned by the main() tests below, which is where
    # it matters -- a bare KeyError reaching an operator would be the defect (PD#2).
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


def test_main_returns_2_for_a_config_whose_pantheon_is_not_a_table(fpd, tmp_path, capsys):
    # SPEC section 10 item 15.  ["Pantheon"]["org_id"] subscripts a str -> TypeError, which was
    # uncaught and therefore exit 1 -- the code reserved for a COMPLETED sweep.
    config = tmp_path / "c.toml"
    config.write_text('Pantheon = "not-a-table"\n')
    assert fpd.main(["-c", str(config)]) == 2
    assert "no usable [Pantheon].org_id" in capsys.readouterr().err


def test_main_returns_2_for_a_config_that_is_not_utf8(fpd, tmp_path, capsys):
    # UnicodeDecodeError is not an OSError, so it escaped the original handler.
    config = tmp_path / "c.toml"
    config.write_bytes(b'[Pantheon]\norg_id = "x"\n\xff\xfe garbage\n')
    assert fpd.main(["-c", str(config)]) == 2
    assert "could not read" in capsys.readouterr().err


def test_verbose_prints_the_reauthentication_note_and_quiet_does_not(fpd, monkeypatch, tmp_path,
                                                                     capsys):
    """SPEC section 10 item 11 -- driven through main(), where the verbosity gate lives."""
    config = tmp_path / "c.toml"
    config.write_text('[Pantheon]\norg_id = "org-uuid"\n')
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": "sess"})
        if calls.count(request.url.path) == 1 and request.url.path.endswith("/environments"):
            return httpx.Response(401, json={"error": "expired"})
        if request.url.path.endswith("/environments"):
            return httpx.Response(200, json={"live": {}})
        if "/memberships/sites" in request.url.path:
            return httpx.Response(200, json=[{"id": "m1", "site": {"id": "u1", "name": "s1"}}])
        return httpx.Response(200, json=[{"id": "live-s1.pantheonsite.io", "type": "platform"}])

    def build(**kwargs):
        return fpd.ApiSession(httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0),
                              "mt", **kwargs)

    monkeypatch.setattr(fpd, "machine_token", lambda: "mt")
    monkeypatch.setattr(fpd, "build_session", build)
    fpd.main(["-c", str(config), "-v"])
    assert "session expired; re-authenticated" in capsys.readouterr().err
    calls.clear()
    fpd.main(["-c", str(config)])
    assert "session expired; re-authenticated" not in capsys.readouterr().err


def test_main_returns_1_when_the_sweep_had_an_indeterminate(fpd, monkeypatch, tmp_path, capsys):
    config = tmp_path / "c.toml"
    config.write_text('[Pantheon]\norg_id = "org-uuid"\n')
    monkeypatch.setattr(fpd, "machine_token", lambda: "mt")
    monkeypatch.setattr(fpd, "build_session",
                        lambda **_kwargs: _StubSession(fpd, indeterminate=True))
    assert fpd.main(["-c", str(config)]) == 1
    assert "indeterminate=1" in capsys.readouterr().err


def test_main_returns_0_on_a_clean_sweep(fpd, monkeypatch, tmp_path, capsys):
    config = tmp_path / "c.toml"
    config.write_text('[Pantheon]\norg_id = "org-uuid"\n')
    monkeypatch.setattr(fpd, "machine_token", lambda: "mt")
    monkeypatch.setattr(fpd, "build_session",
                        lambda **_kwargs: _StubSession(fpd, indeterminate=False))
    assert fpd.main(["-c", str(config)]) == 0
    assert "indeterminate=0" in capsys.readouterr().err


def _main_with_sweep_raising(fpd, monkeypatch, tmp_path, error):
    """Run main() against a stub whose sweep raises `error` on the first domains call."""
    config = tmp_path / "c.toml"
    config.write_text('[Pantheon]\norg_id = "org-uuid"\n')

    class Boom(_StubSession):
        def get(self, path):
            if path.endswith("/domains"):
                raise error
            return super().get(path)

    monkeypatch.setattr(fpd, "machine_token", lambda: "mt")
    monkeypatch.setattr(fpd, "build_session", lambda **_kwargs: Boom(fpd, indeterminate=False))
    return fpd.main(["-c", str(config)])


def test_an_abort_names_the_completed_site_and_the_unreached_ones(fpd, monkeypatch, tmp_path,
                                                                  capsys):
    """SPEC section 7.3: the names, not just a count -- they are the resume instruction."""
    config = tmp_path / "c.toml"
    config.write_text('[Pantheon]\norg_id = "org-uuid"\n')

    class TwoSites(_StubSession):
        def get(self, path):
            if "/memberships/sites" in path:
                return [{"id": "m1", "site": {"id": "u1", "name": "s1"}},
                        {"id": "m2", "site": {"id": "u2", "name": "s2"}}]
            if path.endswith("/environments"):
                if "/u2/" in path:
                    raise KeyboardInterrupt
                return {"live": {}}
            return [{"id": "live-s1.pantheonsite.io", "type": "platform"}]

    monkeypatch.setattr(fpd, "machine_token", lambda: "mt")
    monkeypatch.setattr(fpd, "build_session", lambda **_k: TwoSites(fpd, indeterminate=False))
    assert fpd.main(["-c", str(config)]) == 130
    err = capsys.readouterr().err
    assert "Stopped after s1." in err
    assert "find-platform-domains-dns s2" in err      # paste-able resume command


def test_ctrl_c_returns_130_and_says_where_it_stopped(fpd, monkeypatch, tmp_path, capsys):
    # SPEC G15 + section 7.3.  130 matches the main program's abort_reason convention; the
    # default (an uncaught KeyboardInterrupt) would exit 1, which section 7 reserves for a
    # COMPLETED sweep with indeterminates.
    assert _main_with_sweep_raising(fpd, monkeypatch, tmp_path, KeyboardInterrupt()) == 130
    err = capsys.readouterr().err
    assert "did not complete (interrupted)" in err
    assert "sites=" in err                       # the summary is printed on an abort too


def test_broken_pipe_returns_2_and_reports_like_every_other_abort(fpd, monkeypatch, tmp_path,
                                                                  capsys):
    # SPEC G16 + section 8: `| head` must not produce a traceback at exit 1, AND stderr is
    # unaffected by a closed stdout, so the summary and position line are printed here too.
    assert _main_with_sweep_raising(fpd, monkeypatch, tmp_path, BrokenPipeError()) == 2
    err = capsys.readouterr().err
    assert "broken pipe" in err
    assert "sites=" in err          # the summary, which this path used to omit
    assert "Stopped" in err


def test_session_expiry_returns_2_not_1(fpd, monkeypatch, tmp_path, capsys):
    # SPEC G7a: the whole point is that this is distinguishable from a completed sweep.
    error = fpd.SessionExpiredError("token revoked")
    assert _main_with_sweep_raising(fpd, monkeypatch, tmp_path, error) == 2
    assert "session expired" in capsys.readouterr().err


def test_an_unexpected_error_returns_2_never_1(fpd, monkeypatch, tmp_path, capsys):
    # SPEC G18.  Exit 1 must mean ONLY "completed with indeterminates".
    assert _main_with_sweep_raising(fpd, monkeypatch, tmp_path, ValueError("surprise")) == 2
    assert "unexpected ValueError" in capsys.readouterr().err


def test_no_token_ever_reaches_stdout_or_stderr(fpd, monkeypatch, tmp_path, capsys):
    """SPEC section 3, threat-model property (a) -- instrumented rather than asserted.

    An unmeasured security claim is PD#14 in its design-time form: "Applies at design time too
    -- to a new counter, artifact, or notice -- not only in tests."
    """
    config = tmp_path / "c.toml"
    config.write_text('[Pantheon]\norg_id = "org-uuid"\n')
    secrets = ("MACHINE-TOKEN-e7f2a1", "SESSION-TOKEN-9b4c3d")

    def handler(request):
        # The two paths SPEC section 3 names: a per-site G5 (environments 500) and, after it,
        # an authentication failure that survives re-authentication (G7a).  A test that only
        # failed the site listing would traverse neither.
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": secrets[1]})
        if "/memberships/sites" in request.url.path:
            return httpx.Response(200, json=[{"id": "m1", "site": {"id": "u1", "name": "s1"}},
                                             {"id": "m2", "site": {"id": "u2", "name": "s2"}}])
        if "/u1/" in request.url.path:
            return httpx.Response(500, text="boom")            # G5
        return httpx.Response(401, json={"error": "expired"})  # -> G7a on retry

    monkeypatch.setattr(fpd, "machine_token", lambda: secrets[0])
    monkeypatch.setattr(fpd, "RETRY_SLEEP", 0)
    monkeypatch.setattr(fpd, "build_session", lambda **kwargs: fpd.ApiSession(
        httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0), secrets[0], **kwargs))
    assert fpd.main(["-c", str(config), "-v"]) == 2     # G7a aborts; -v is the noisiest mode
    captured = capsys.readouterr()
    for secret in secrets:
        assert secret not in captured.out
        assert secret not in captured.err
```

and, above them, the stub the last two use:

```python
class _StubSession:
    """Stands in for ApiSession: an organization of one site with one environment.

    Takes the loaded module so it can raise the module's OWN PantheonApiError -- the sweep
    catches that class by identity, so a stand-in raising anything else would not exercise the
    G6 path at all.  `indeterminate=True` makes the domains call fail, which is the shortest
    path to a counted indeterminate without touching DNS.
    """

    def __init__(self, fpd, *, indeterminate):
        self._fpd = fpd
        self._indeterminate = indeterminate

    def get(self, path):
        if "/memberships/sites" in path:
            return [{"id": "mem-1", "site": {"id": "u1", "name": "s1"}}]
        if path.endswith("/environments"):
            return {"live": {}}
        if self._indeterminate:
            raise self._fpd.PantheonApiError("HTTP 500")
        return [{"id": "live-s1.pantheonsite.io", "type": "platform"}]
```

- [ ] **Step 2: Run them and confirm they fail**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_dns.py -v
```

Expected: `AttributeError: module has no attribute 'build_arg_parser'`.

- [ ] **Step 3: Implement the CLI and `main()`**

Add `import argparse`, `import contextlib`, `import io` and `import tomllib` to the imports, then append:

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


def build_session(notify=None):
    """The production ApiSession, over one reused connection.  Monkeypatched by the CLI tests.

    follow_redirects is left at httpx's default of False ON PURPOSE (SPEC section 3, threat
    model property (c)): the Authorization header must never be replayed to a redirect target.
    """
    client = httpx.Client(timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT})
    return ApiSession(client, machine_token(), notify=notify)


def main(argv):
    """Exit 0 = clean sweep, 1 = completed with indeterminates, 2 = could not complete,
    130 = interrupted (SPEC section 7).

    The exit-code discipline is the point of the structure below.  Python exits 1 on ANY
    uncaught traceback, and section 7 reserves 1 for "completed with indeterminates" -- so a
    Ctrl-C, a broken pipe, or an unexpected API shape leaking out of here would be
    indistinguishable from a healthy sweep that had a few DNS timeouts.  Every other outcome is
    routed away from 1, and the only `return 1` in the program is the indeterminate branch.
    """
    options = build_arg_parser().parse_args(argv)

    def note(message):                       # the G7 re-authentication note, -v only
        if options.verbose:
            print(message, file=sys.stderr, flush=True)

    try:
        session, sites = prepare_sweep(options, note)
    except StartupError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    sweeper = Sweeper(session.get, csv.writer(sys.stdout, lineterminator="\n"), sys.stdout,
                      verbose=options.verbose)
    try:
        sweeper.sweep(sites)
    except KeyboardInterrupt:
        report_stop(sweeper, "interrupted")
        return 130
    except SessionExpiredError as e:
        report_stop(sweeper, f"session expired: {e}")
        return 2
    except BrokenPipeError:
        # `find-platform-domains-dns | head` is the natural first thing an operator types.
        # stderr is unaffected by a closed stdout, so the abort report is printed here too --
        # SPEC section 8 says the summary appears on EVERY path that entered the site loop.
        report_stop(sweeper, "stdout closed (broken pipe)")
        # The dup2 is REQUIRED, not tidiness (verified: without it this exits 120, not 2).
        # CPython flushes sys.stdout again during interpreter shutdown; on a closed pipe that
        # flush ALSO raises, and a failed final flush is converted into exit code 120 plus an
        # "Exception ignored on flushing sys.stdout" message -- overriding the 2 returned here
        # and reintroducing exactly the ambiguous exit code SPEC section 7 exists to prevent.
        # This is the recipe from Python's own "Note on SIGPIPE" (library/signal docs).
        # suppress(), not try/except/pass: ruff SIM105.  sys.stdout may not be backed by a
        # real file descriptor -- pytest's capture object raises io.UnsupportedOperation from
        # fileno() -- and in that case there is no shutdown-flush hazard to defend against.
        # Named exceptions only (PD#2); suppressing broadly would hide a real dup2 failure.
        with contextlib.suppress(OSError, ValueError, io.UnsupportedOperation):
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
            os.close(devnull)
        return 2
    except SystemExit:
        raise
    except BaseException as e:  # noqa: BLE001 -- deliberate last line of defence, see the docstring: an uncaught exception here would exit 1, which section 7 reserves for a COMPLETED sweep.  It is re-reported by name, never swallowed silently (PD#2)
        report_stop(sweeper, f"unexpected {type(e).__name__}: {e}")
        return 2
    print(sweeper.counters.summary(), file=sys.stderr)
    return 1 if sweeper.counters.indeterminate else 0


class StartupError(Exception):
    """The sweep could not be started: SPEC G1-G4b, or a listing-time G7a. Always exit 2."""


def prepare_sweep(options, note):
    """Config -> session -> site list, or StartupError with an operator-ready message.

    Split out of main() so that main() is a readable dispatch of exit codes: with this inline,
    main() carried 9 returns and a cyclomatic complexity of 12, over ruff's PLR0911/C901 limits.
    Every failure here means the same thing to the caller -- the sweep never started, exit 2 --
    so collapsing them into one named error loses nothing.
    """
    try:
        org_id = org_id_from_config(options.config)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        # UnicodeDecodeError is NOT an OSError: a config that is not valid UTF-8 raised it
        # uncaught, which exits 1 -- the code SPEC section 7 reserves for a COMPLETED sweep.
        raise StartupError(f"could not read {options.config}: {e}") from e
    except (KeyError, TypeError) as e:
        # TypeError covers `Pantheon = "not-a-table"`, where ["Pantheon"]["org_id"] subscripts
        # a string.  Verified: without it, exit 1 with a traceback.
        raise StartupError(f"{options.config} has no usable [Pantheon].org_id ({e!r})") from e
    try:
        session = build_session(notify=note)
    except (MachineTokenError, PantheonApiError) as e:
        raise StartupError(str(e)) from e
    try:
        sites = (named_sites(session.get, options.site) if options.site
                 else org_sites(session.get, org_id))
    except (PantheonApiError, SiteListingError, SessionExpiredError) as e:
        raise StartupError(f"could not list sites: {e}") from e
    return session, sites


def report_stop(sweeper, reason):
    """SPEC section 7.3: an aborted sweep MUST say where it stopped, or the operator has no way
    to resume except starting the 38-minute sweep over.

    Unconditional on purpose.  An earlier draft printed the position only `if sweeper.last_site`
    -- i.e. never, when the very first site was the one interrupted, which is precisely when an
    operator most needs to know where they are.  And it printed a COUNT of unreached sites
    rather than their names, which is not a recovery instruction: the order is ascending by site
    UUID and the operator has no copy of that list.  The names are already in hand.
    """
    print(f"ERROR: sweep did not complete ({reason})", file=sys.stderr)
    print(sweeper.counters.summary(), file=sys.stderr)
    if sweeper.last_site:
        print(f"Stopped after {sweeper.last_site}.", file=sys.stderr)
    else:
        print(f"Stopped during {sweeper.current_site or 'startup'}.", file=sys.stderr)
    if sweeper.remaining:
        names = " ".join(site["name"] for site in sweeper.remaining)
        count = len(sweeper.remaining)
        print(f"{count} site{'' if count == 1 else 's'} not reached. Resume with:\n"
              f"  find-platform-domains-dns {names}", file=sys.stderr)


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
indeterminates, 2 = could not complete, 130 = interrupted. An aborted sweep prints the last
site it processed and how many remain, which is the whole resume story (there is no
`--resume-from`).

```bash
./find-platform-domains-dns its-wws-test1     # one site
./find-platform-domains-dns > domains.csv     # the whole org, ~38 minutes
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

Every question in SPEC §15 needs a full-organization sweep, which is an operational run rather
than an acceptance step. Record each as "open — needs a full sweep" in `ACCEPTANCE.md`, **by
number, checked against SPEC §15 as you write them**: the list grew during review, so Q1 is
the mid-chain/duplicate-`dns_record` question, Q4 is the uninitialized-environment one and Q6
is the short-non-final-page one.

- [ ] **Step 4: Commit**

```bash
git add development/2026-07-28-platform-domain-util/ACCEPTANCE.md
git commit -m "docs(find-platform-domains-dns): acceptance evidence"
```

---

## Self-review notes (completed while writing this plan)

- **Spec coverage.** §3 CLI → Task 5. §4 data sources → Tasks 2–3. §4.1 cursor → Task 3
  (implementation + the red-proof step). §5 output contract → Task 4. §6 algorithm → Task 1
  (walk) + Task 4 (sweep); §6.2's measured retry delays → Task 1's `resolve_cname_retrying`.
  §7 taxonomy, every gate: G1/G2/G3 → Task 5 (`prepare_sweep`) + Task 2; G4/G4a/G4b → Task 3;
  G5/G6/G6a → Task 4; G7/G7a → Task 2 (`_renew`); G8–G11 → Task 1 + Task 4;
  G12/G13/G13a/G14 → Task 4; **G15/G16/G17/G18 → Task 5** (`main`'s handler chain,
  `report_stop`, and `PantheonApiShapeError` raised from Task 3). §7.3 → Task 5
  (`report_stop`) + Task 4 (`last_site`/`current_site`/`remaining`). §8 observability →
  `skipped()`/`warning()` (Task 1), `_progress` and the per-site counts (Task 4), the summary
  and the `-v` re-auth note (Task 5). §9 seams → honored throughout, including the five
  test-only seams §9 now declares. §10 test list, items 1–18 → Tasks 1–5. §13 acceptance →
  Task 6. §14 deletion checklist → recorded in CLAUDE.md (Task 5) and the SPEC.
- **Type consistency.** `WalkResult(dns_record, platform_domain, problem)` is constructed and
  destructured identically in Tasks 1 and 4. `Sweeper.check_domain(site, env_id, custom_domain,
  platform_domains)` matches its call in `sweep_env` and in every test. `org_sites`/`named_sites`
  both return `[{"id", "name"}]`, which is what `Sweeper.sweep_site` reads.
- **Corrections applied after round 1 of adversarial review** (`prompts/adversarial-review.md`
  asks that the author's own corrected claims be recorded, not just the fixes). An earlier
  draft of this plan asserted "every other code block is complete as written". That was false,
  and the review proved it by materializing the plan and running the gates:
  - `test_chain_longer_than_the_hop_limit_is_indeterminate` never called `patch_dns`, so it
    failed **and** queried real DNS — while Task 1's PD#14 red-proof was built on that very
    test, which would have "proved" a test could go red for a reason unrelated to what it
    guards. Both fixed.
  - The plan's code failed ruff in 10 places. The two contingencies the plan did prescribe
    (`INP001`, a pyright ignore for `.target`) were the two that never fire.
  - `_StubSession` shipped a `raise RuntimeError("unused")` with a prose note telling the
    implementer to fix it. It is now written correctly.
  - The `-v` contract in SPEC §8 (the G7 re-auth note, per-site counts) had no implementation
    at all; a mid-sweep session expiry degraded into ~400 indeterminates.
  The lesson worth carrying: a plan whose code blocks have never been executed is an
  unverified instrument, exactly like an unrun test (PD#14). **Materialize and run the gates
  before claiming a plan is complete.**
- **Corrections applied after round 2 of adversarial review.** Round 1's fixes were themselves
  incomplete, in a pattern worth naming: each fix patched the *instances* the reviewer cited
  rather than the *class*.
  - Exit 1 was still reachable. The round-1 fix guarded the sweep; `prepare_sweep` still let a
    `TypeError` (`Pantheon = "not-a-table"`) and a `UnicodeDecodeError` (a non-UTF-8 config)
    escape as tracebacks — both verified to exit 1.
  - `_require` was introduced and then applied to three of the seven response-key reads.
    `site["name"]`, the `/site-names/` `name`, and both keys inside `partition_domains` still
    raised bare `KeyError`/`AttributeError`.
  - `partition_domains` sat *outside* `sweep_env`'s `try`, so a malformed domains payload
    aborted the whole sweep instead of costing one environment — the opposite of what SPEC G17
    specifies.
  - Three of the four abort paths gained `report_stop`; the broken-pipe path did not. And the
    position line was conditional on `last_site`, so it never printed when the first site was
    the one interrupted.
  - The G4a message told the operator to run `terminus org:site:list --format=json`, which
    fails: the organization is a required positional argument.
  Two round-2 findings were **declined**, because they re-open decisions already put to the
  user and answered: an automatic `terminus` site-count cross-check (D15) and promoting the
  duplicate-`dns_record` audit question into a warning (D16).

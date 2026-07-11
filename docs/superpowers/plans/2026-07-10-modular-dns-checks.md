# Modular Site-Level DNS Checks — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move site-level DNS resolution + notices out of the `pantheon-sitehealth-emails` core script into a pure engine module (`dns_classify.py`) and a `check/dns/` package, fixing two latent bugs and gating U-M wording — with byte-identical goldens.

**Architecture:** Core fetches `domain:list`, calls `dns_classify.classify_domains()` to produce the `site_post_dns` contract facts, stuffs them onto the `SiteContext`, then fires `site_post_dns`. The new `check/dns` hook consumes those facts and emits the DNS-resolution notices. See the design/spec: `docs/superpowers/specs/2026-07-10-modular-dns-checks-design.md`.

**Tech Stack:** Python 3, `dnspython` (`dns.resolver`), the project's self-registering `check/` framework + `sc.PHASES` hooks, pytest (`./run-tests`), Hypothesis.

## Global Constraints

- **Engine purity:** `dns_classify.py` MUST import only `script_context as sc`, `ipaddress`, `dns.resolver`, `typing` (`NamedTuple`), and `rich.markup` (`escape`). It MUST NOT import the dash-named `pantheon-sitehealth-emails` script. (`fqdn_re` is passed in, so `re` is not imported.)
- **No new config; DNS checks are not disable-able.** `check/dns/__init__.py` registers unconditionally. The three Cloudflare notices key off `sc.cloudflare_enabled()`.
- **Goldens are load-bearing (NEVER-block):** the offline e2e goldens MUST stay byte-identical. Regenerating a golden requires a reviewed diff + written reason. Cloudflare is disabled and fixture domains are platform-only, so no DNS-resolution notice appears in any golden.
- **No catch-all `except`.** Catch only `dns.resolver.NoAnswer`, `dns.resolver.NXDOMAIN`, `dns.resolver.NoNameservers`, `dns.resolver.Timeout`.
- **Every notice dict carries a `csv` key** (`site,code,...`); several report paths read `n["csv"]`.
- **Commit after each task.** Branch first if on `main` (this repo's convention: commit/branch only as directed — the executor will branch before Task 1).

---

### Task 1: DNS engine — `resolve` seam + `classify_hostname_dns`

**Files:**
- Create: `dns_classify.py`
- Test: `tests/unit/test_dns_classify.py`

**Interfaces:**
- Produces: `dns_classify.resolve(hostname, rrtype)`; `dns_classify.classify_hostname_dns(hostname, cloudflare_enabled: bool, cf_v4_nets: list, cf_v6_nets: list) -> (int, int, bool)` returning `(points_at_cloudflare, points_elsewhere, transient)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_dns_classify.py
import ipaddress

import dns.resolver
import pytest

import dns_classify

pytestmark = pytest.mark.unit


class _RData:
    def __init__(self, address):
        self.address = address


def _raise(exc):
    def _fn(hostname, rrtype):
        raise exc
    return _fn


def test_nxdomain_is_definitive_not_transient(reset_sc, monkeypatch):
    monkeypatch.setattr(dns_classify, "resolve", _raise(dns.resolver.NXDOMAIN()))
    cf, elsewhere, transient = dns_classify.classify_hostname_dns("example.org", False, [], [])
    assert (cf, elsewhere) == (0, 0)
    assert transient is False


def test_timeout_is_transient(reset_sc, monkeypatch):
    monkeypatch.setattr(dns_classify, "resolve", _raise(dns.resolver.Timeout()))
    cf, elsewhere, transient = dns_classify.classify_hostname_dns("example.org", False, [], [])
    assert (cf, elsewhere) == (0, 0)
    assert transient is True


def test_cloudflare_ip_counted(reset_sc, monkeypatch):
    def fake(hostname, rrtype):
        if rrtype == "A":
            return [_RData("104.16.0.1")]
        raise dns.resolver.NoAnswer()
    monkeypatch.setattr(dns_classify, "resolve", fake)
    cf, elsewhere, transient = dns_classify.classify_hostname_dns(
        "example.org", True, [ipaddress.ip_network("104.16.0.0/12")], [])
    assert cf == 1 and elsewhere == 0 and transient is False


def test_non_cloudflare_ip_is_elsewhere(reset_sc, monkeypatch):
    def fake(hostname, rrtype):
        if rrtype == "A":
            return [_RData("203.0.113.5")]
        raise dns.resolver.NoAnswer()
    monkeypatch.setattr(dns_classify, "resolve", fake)
    cf, elsewhere, transient = dns_classify.classify_hostname_dns(
        "example.org", True, [ipaddress.ip_network("104.16.0.0/12")], [])
    assert cf == 0 and elsewhere == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./run-tests --fast -- tests/unit/test_dns_classify.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'dns_classify'`.

- [ ] **Step 3: Write minimal implementation**

```python
# dns_classify.py
"""Site-level DNS engine: A/AAAA resolution + Cloudflare classification.

Pure data producer for the site_post_dns contract (see CLAUDE.md and
docs/superpowers/specs/2026-07-10-modular-dns-checks-design.md).  Imports only sc +
stdlib + dnspython; NEVER the dash-named core script.  Presentation (notices) lives in
check/dns/, not here.  Named dns_classify (not dns) to avoid shadowing dnspython's `dns`.
"""
import ipaddress
from typing import NamedTuple

import dns.resolver
from rich.markup import escape as rich_escape

import script_context as sc


def resolve(hostname: str, rrtype: str):
    """The one seam over dns.resolver.resolve; tests monkeypatch dns_classify.resolve."""
    return dns.resolver.resolve(hostname, rrtype)


def classify_hostname_dns(
    hostname: str,
    cloudflare_enabled: bool,
    cf_v4_nets: list,
    cf_v6_nets: list,
) -> (int, int, bool):
    """Resolve hostname A/AAAA and count addresses inside/outside the Cloudflare ranges.

    Returns (points_at_cloudflare, points_elsewhere, transient).  Timeout/NoNameservers ->
    transient=True (NOT reported as "not in DNS", P4).  NXDOMAIN/NoAnswer are definitive and
    leave both counts 0 with transient=False (the caller aggregates "not in DNS").
    """
    points_at_cloudflare = 0
    points_elsewhere = 0
    transient = False

    for rrtype, nets in (("A", cf_v4_nets), ("AAAA", cf_v6_nets)):
        try:
            answer = resolve(hostname, rrtype)
            for rdata in answer:
                address = ipaddress.ip_address(rdata.address)
                if cloudflare_enabled and any(address in net for net in nets):
                    points_at_cloudflare += 1
                    sc.console.print(
                        f"{hostname} has [green]Cloudflare IP address {rdata.address}[/green]")
                else:
                    points_elsewhere += 1
                    sc.console.print(
                        f"{hostname} has IP address [red]{rdata.address}[/red]")
        except dns.resolver.NoAnswer:
            sc.console.print(f"No {rrtype} record for {hostname}", style="red")
        except dns.resolver.NXDOMAIN:
            sc.console.print(f"NXDOMAIN for {hostname} ({rrtype})", style="red")
        except (dns.resolver.NoNameservers, dns.resolver.Timeout) as e:
            transient = True
            sc.console.print(
                f"Transient DNS error resolving {hostname} ({rrtype}): {type(e).__name__}",
                style="red")

    return points_at_cloudflare, points_elsewhere, transient
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./run-tests --fast -- tests/unit/test_dns_classify.py`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add dns_classify.py tests/unit/test_dns_classify.py
git commit -m "feat(dns): add dns_classify engine — resolve seam + classify_hostname_dns"
```

---

### Task 2: DNS engine — `DnsFacts` + `classify_domains`

**Files:**
- Modify: `dns_classify.py`
- Test: `tests/unit/test_dns_classify.py`

**Interfaces:**
- Consumes: `classify_hostname_dns` (Task 1).
- Produces: `dns_classify.DnsFacts` (NamedTuple) and `dns_classify.classify_domains(domains, cloudflare_enabled: bool, cf_v4_nets: list, cf_v6_nets: list, proxied_fqdns, fqdn_zone_conflicts: dict, fqdn_re) -> DnsFacts`. Fields: `custom_domains, primary_domain, main_fqdn, not_in_dns, fqdns_behind_cloudflare, fqdns_not_behind_cloudflare, behind_cloudflare_not_proxied, proxied_in_multiple_zones, dns_transient`. Also `dns_classify.stuff_dns_contract(site_context, domains, facts: DnsFacts) -> None` (pure mapping of `facts` → the ten `site_post_dns` contract keys; called by `main()` in Task 5).

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_dns_classify.py`)

```python
def _domains(spec):
    """spec: name -> (type, primary). Mirrors the terminus domain:list dict shape."""
    return {name: {"id": name, "type": t, "primary": p} for name, (t, p) in spec.items()}


def _resolver(mapping):
    """mapping: hostname -> "cf" | "elsewhere" | "missing" | "transient"."""
    def fake(hostname, rrtype):
        kind = mapping.get(hostname, "missing")
        if rrtype != "A":
            raise dns.resolver.NoAnswer()
        if kind == "cf":
            return [_RData("104.16.0.1")]
        if kind == "elsewhere":
            return [_RData("203.0.113.5")]
        if kind == "transient":
            raise dns.resolver.Timeout()
        raise dns.resolver.NXDOMAIN()
    return fake


CF_V4 = [ipaddress.ip_network("104.16.0.0/12")]


def test_classify_domains_skips_platform_and_invalid(psh, reset_sc, monkeypatch):
    monkeypatch.setattr(dns_classify, "resolve", _resolver({"www.example.org": "elsewhere"}))
    domains = _domains({
        "example.pantheonsite.io": ("platform", False),   # skipped
        "BAD HOST": ("custom", False),                     # fails fqdn_re -> skipped
        "www.example.org": ("custom", True),
    })
    facts = dns_classify.classify_domains(
        domains, False, [], [], proxied_fqdns={}, fqdn_zone_conflicts={}, fqdn_re=psh.fqdn_re)
    assert facts.custom_domains == ["BAD HOST", "www.example.org"]  # keys, unfiltered (unchanged)
    assert facts.primary_domain == ["www.example.org"]
    assert facts.main_fqdn == "www.example.org"


def test_transient_excluded_from_not_in_dns_and_cf(psh, reset_sc, monkeypatch):
    monkeypatch.setattr(dns_classify, "resolve", _resolver({"t.example.org": "transient"}))
    domains = _domains({"t.example.org": ("custom", True)})
    facts = dns_classify.classify_domains(
        domains, True, CF_V4, [], proxied_fqdns={}, fqdn_zone_conflicts={}, fqdn_re=psh.fqdn_re)
    assert facts.dns_transient == ["t.example.org"]
    assert facts.not_in_dns == []                       # P4: transient != not-in-dns
    assert facts.fqdns_not_behind_cloudflare == []      # classification skipped on transient


def test_bug1_zone_conflict_list_populated_when_all_behind_cloudflare(psh, reset_sc, monkeypatch):
    monkeypatch.setattr(dns_classify, "resolve", _resolver({"w.example.org": "cf"}))
    domains = _domains({"w.example.org": ("custom", True)})
    facts = dns_classify.classify_domains(
        domains, True, CF_V4, [],
        proxied_fqdns={"w.example.org": {}},
        fqdn_zone_conflicts={"w.example.org": ["z1", "z2"]},
        fqdn_re=psh.fqdn_re)
    assert facts.fqdns_not_behind_cloudflare == []
    assert facts.fqdns_behind_cloudflare == ["w.example.org"]
    assert facts.proxied_in_multiple_zones == ["w.example.org"]


def test_non_dict_domains_returns_empty_facts(psh, reset_sc):
    facts = dns_classify.classify_domains(
        None, True, CF_V4, [], proxied_fqdns={}, fqdn_zone_conflicts={}, fqdn_re=psh.fqdn_re)
    assert facts == dns_classify.DnsFacts([], [], "", [], [], [], [], [], [])


def test_stuff_dns_contract_maps_each_field(reset_sc):
    # Distinct sentinel per field: any facts.X -> site_context["Y"] value-swap fails here.
    facts = dns_classify.DnsFacts(
        custom_domains=["cd"], primary_domain=["pd"], main_fqdn="mf", not_in_dns=["nid"],
        fqdns_behind_cloudflare=["fbc"], fqdns_not_behind_cloudflare=["fnbc"],
        behind_cloudflare_not_proxied=["bcnp"], proxied_in_multiple_zones=["pmz"],
        dns_transient=["dt"])
    ctx = reset_sc.SiteContext({"name": "s"})
    dns_classify.stuff_dns_contract(ctx, {"raw": "domains"}, facts)
    assert ctx["domains"] == {"raw": "domains"}
    assert ctx["custom_domains"] == ["cd"]
    assert ctx["primary_domain"] == ["pd"]
    assert ctx["main_fqdn"] == "mf"
    assert ctx["fqdns_behind_cloudflare"] == ["fbc"]
    assert ctx["fqdns_not_behind_cloudflare"] == ["fnbc"]
    assert ctx["not_in_dns"] == ["nid"]
    assert ctx["behind_cloudflare_not_proxied"] == ["bcnp"]
    assert ctx["proxied_in_multiple_zones"] == ["pmz"]
    assert ctx["dns_transient"] == ["dt"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `./run-tests --fast -- tests/unit/test_dns_classify.py -k "classify_domains or transient_excluded or bug1 or non_dict"`
Expected: FAIL — `AttributeError: module 'dns_classify' has no attribute 'DnsFacts'`.

- [ ] **Step 3: Implement** (append to `dns_classify.py`)

```python
class DnsFacts(NamedTuple):
    custom_domains: list
    primary_domain: list
    main_fqdn: str
    not_in_dns: list
    fqdns_behind_cloudflare: list
    fqdns_not_behind_cloudflare: list
    behind_cloudflare_not_proxied: list
    proxied_in_multiple_zones: list
    dns_transient: list


def classify_domains(
    domains,
    cloudflare_enabled: bool,
    cf_v4_nets: list,
    cf_v6_nets: list,
    proxied_fqdns,
    fqdn_zone_conflicts: dict,
    fqdn_re,
) -> DnsFacts:
    """Iterate the terminus domain:list result and produce the site_post_dns contract facts.

    Non-dict `domains` -> all-empty DnsFacts (preserves the core's isinstance guard).  Console
    prints are observability only (not captured by goldens).  Cloudflare classification is
    skipped for a host whose lookup was transient (P4), so a config that never changed is not
    reported as "not behind Cloudflare".
    """
    main_fqdn = ""
    not_in_dns = []
    fqdns_behind_cloudflare = []
    fqdns_not_behind_cloudflare = []
    behind_cloudflare_not_proxied = []
    proxied_in_multiple_zones = []
    dns_transient = []
    custom_domains = []
    primary_domain = []

    if isinstance(domains, dict):
        for d in domains.keys():
            domain = domains[d]
            if domain["type"] == "platform":
                continue
            hostname = domain["id"]
            if not fqdn_re.match(hostname):
                # rich_escape the un-validated hostname: it failed fqdn_re, so it is arbitrary
                # and a bracket sequence would otherwise be parsed as rich markup (matches the
                # rich_escape convention in check/cloudflare/cache.py). Console-only.
                sc.console.log(f"[bold red]ERROR: Invalid domain: {rich_escape(hostname)}")
                continue
            if domain["primary"] or main_fqdn == "":
                main_fqdn = hostname

            points_at_cf, points_elsewhere, transient = classify_hostname_dns(
                hostname, cloudflare_enabled, cf_v4_nets, cf_v6_nets)
            if transient:
                dns_transient.append(hostname)

            if points_at_cf == 0 and points_elsewhere == 0 and not transient:
                sc.console.print(
                    f":exclamation: [bold red] ATTENTION: {hostname} is not in DNS")
                not_in_dns.append(hostname)

            if cloudflare_enabled and not transient:
                if points_at_cf == 0 or points_elsewhere != 0:
                    sc.console.print(
                        f":exclamation: [bold red] ATTENTION: {hostname} is not behind Cloudflare")
                    fqdns_not_behind_cloudflare.append(hostname)
                if points_at_cf > 0:
                    if hostname not in proxied_fqdns:
                        sc.console.print(
                            f":exclamation: [bold red] ATTENTION: {hostname} is behind "
                            "Cloudflare but not proxied")
                        behind_cloudflare_not_proxied.append(hostname)
                    else:
                        fqdns_behind_cloudflare.append(hostname)
                        if hostname in fqdn_zone_conflicts:
                            sc.console.print(
                                f":exclamation: [bold red] ATTENTION: {hostname} is proxied "
                                "through more than one Cloudflare zone")
                            proxied_in_multiple_zones.append(hostname)

        custom_domains = [d for d in domains.keys() if domains[d]["type"] == "custom"]
        primary_domain = [d for d in custom_domains if domains[d]["primary"]]

    return DnsFacts(
        custom_domains, primary_domain, main_fqdn, not_in_dns, fqdns_behind_cloudflare,
        fqdns_not_behind_cloudflare, behind_cloudflare_not_proxied, proxied_in_multiple_zones,
        dns_transient)


def stuff_dns_contract(site_context, domains, facts: DnsFacts) -> None:
    """Publish every site_post_dns data-contract key from a DnsFacts (see CLAUDE.md).

    Pure mapping (dict writes only), extracted from main() so a value-swap mis-map is
    unit-testable — main() itself is not callable in isolation.  main() calls this immediately
    before invoke_hooks('site_post_dns').
    """
    site_context["domains"] = domains
    site_context["custom_domains"] = facts.custom_domains
    site_context["primary_domain"] = facts.primary_domain
    site_context["main_fqdn"] = facts.main_fqdn
    site_context["fqdns_behind_cloudflare"] = facts.fqdns_behind_cloudflare
    site_context["fqdns_not_behind_cloudflare"] = facts.fqdns_not_behind_cloudflare
    site_context["not_in_dns"] = facts.not_in_dns
    site_context["behind_cloudflare_not_proxied"] = facts.behind_cloudflare_not_proxied
    site_context["proxied_in_multiple_zones"] = facts.proxied_in_multiple_zones
    site_context["dns_transient"] = facts.dns_transient
```

- [ ] **Step 4: Run to verify it passes**

Run: `./run-tests --fast -- tests/unit/test_dns_classify.py`
Expected: PASS (all cases).

- [ ] **Step 5: Add the Hypothesis property test** (append)

```python
from hypothesis import given, strategies as st


@given(hosts=st.dictionaries(
    st.from_regex(r"[a-z]{1,6}\.example\.org", fullmatch=True),
    st.sampled_from(["cf", "elsewhere", "missing", "transient"]),
    max_size=6))
def test_property_transient_never_in_not_in_dns(psh, reset_sc, monkeypatch, hosts):
    monkeypatch.setattr(dns_classify, "resolve", _resolver(hosts))
    domains = _domains({h: ("custom", False) for h in hosts})
    facts = dns_classify.classify_domains(
        domains, True, CF_V4, [], proxied_fqdns={}, fqdn_zone_conflicts={}, fqdn_re=psh.fqdn_re)
    assert set(facts.dns_transient).isdisjoint(facts.not_in_dns)
```

- [ ] **Step 6: Run + commit**

Run: `./run-tests --fast -- tests/unit/test_dns_classify.py`
Expected: PASS.

```bash
git add dns_classify.py tests/unit/test_dns_classify.py
git commit -m "feat(dns): classify_domains + DnsFacts (contract facts, offline-pure)"
```

---

### Task 3: DNS check — pure notice builders

**Files:**
- Create: `check/dns/__init__.py` (empty-ish placeholder in this task — just the module docstring + `import script_context as sc`; the hook registration lands in Task 4 so the package is importable now)
- Create: `check/dns/notices.py`
- Test: `tests/unit/test_dns_notices.py`

> NOTE: create `check/dns/__init__.py` with content in this task so the package imports, but DO NOT register the hook yet (registration + `find_modules` wiring is Task 4). A non-empty `__init__.py` is required for `find_modules` to pick the package up.

**Interfaces:**
- Produces (all in `check/dns/notices.py`, all return a notice dict with `type`/`csv`/`short`/`message`/`text`, NO `icon` — `add_notice` fills it from `type`):
  - `transient_notice(site_name, hostnames)`
  - `not_in_dns_notice(site_name, hostnames)`
  - `not_behind_cloudflare_notice(site_name, hostnames, *, umich)`
  - `behind_cloudflare_not_proxied_notice(site_name, hostnames, *, umich)`
  - `proxied_in_multiple_zones_notice(site_name, hostnames)`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_dns_notices.py
import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def notices(psh, reset_sc):
    # Load check/dns/notices.py standalone (it only needs sc.escape_url).
    reset_sc.escape_url = lambda u: u
    path = Path(psh.__file__).parent / "check" / "dns" / "notices.py"
    spec = importlib.util.spec_from_file_location("dns_notices_probe", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_notice_has_csv(notices):
    n = notices.not_in_dns_notice("s", ["a.example.org"])
    assert n["csv"].startswith("s,not-in-dns,")
    assert "a.example.org" in n["message"]


def test_transient_aggregates_all_hosts(notices):
    n = notices.transient_notice("s", ["a.example.org", "b.example.org"])
    assert n["type"] == "warning"
    assert n["csv"] == "s,dns-lookup-failed,a.example.org,b.example.org"
    assert "a.example.org" in n["message"] and "b.example.org" in n["message"]


def test_not_behind_cloudflare_umich_vs_generic(notices):
    umich = notices.not_behind_cloudflare_notice("s", ["a.example.org"], umich=True)
    generic = notices.not_behind_cloudflare_notice("s", ["a.example.org"], umich=False)
    assert "its.umich.edu" in umich["message"]
    assert "umich.edu" not in generic["message"] and "umich.edu" not in generic["text"]


def test_bug2_not_proxied_plaintext_lists_correct_hosts(notices):
    # Regression: the plaintext body must list behind_cloudflare_not_proxied, not the other list.
    n = notices.behind_cloudflare_not_proxied_notice("s", ["np.example.org"], umich=True)
    assert "np.example.org" in n["text"]
    assert n["csv"].startswith("s,behind-cloudflare-not-proxied,")


def test_hostname_html_escaped_in_display(notices):
    # Owner-facing HTML: the hostname text node must be html.escape'd (the href separately uses
    # sc.escape_url). Guards against markup injection via a remotely-derived domain id.
    n = notices.not_in_dns_notice("s", ["a<b>.example.org"])
    assert "&lt;b&gt;" in n["message"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `./run-tests --fast -- tests/unit/test_dns_notices.py`
Expected: FAIL — no `check/dns/notices.py`.

- [ ] **Step 3: Implement `check/dns/__init__.py`** (importable package; hook added in Task 4)

```python
# check/dns/__init__.py
"""Site-level DNS-resolution notices (site_post_dns).

Registers unconditionally: DNS checks are not disable-able.  The three Cloudflare notices
self-gate on sc.cloudflare_enabled(); U-M wording is chosen via sc.umich_enabled().  The
resolution FACTS are produced by dns_classify.classify_domains() in core before the phase
fires (see docs/superpowers/specs/2026-07-10-modular-dns-checks-design.md).
"""
import script_context as sc  # noqa: F401  (hook registration added in Task 4)
```

- [ ] **Step 4: Implement `check/dns/notices.py`**

```python
# check/dns/notices.py
"""PURE DNS notice builders (HTML + plaintext), U-M and generic variants.

Each builder returns a notice dict with type/csv/short/message/text; add_notice fills `icon`
from `type`.  Every remotely-derived hostname is html.escape'd for display and sc.escape_url'd
for hrefs.  U-M variants link its.umich.edu / documentation.its.umich.edu; generic variants
use no U-M links.  csv codes: dns-lookup-failed, not-in-dns, not-behind-cloudflare,
behind-cloudflare-not-proxied, proxied-in-multiple-cloudflare-zones.
"""
import html

import script_context as sc


def _html_list(hostnames):
    return "\n".join(
        f'<li><a href="https://{sc.escape_url(n)}/">{html.escape(n)}</a></li>'
        for n in hostnames)


def _text_list(hostnames):
    return "\n".join(f"  * {n}" for n in hostnames)


def transient_notice(site_name, hostnames):
    return {
        "type": "warning",
        "csv": f"{site_name},dns-lookup-failed," + ",".join(hostnames),
        "short": "DNS lookup failed (transient)",
        "message": (
            "<p>The DNS lookup for the following domains failed with a transient resolver "
            "error, so their DNS status could not be checked. This does not necessarily mean "
            "they are misconfigured &mdash; re-run the report to retry.</p>\n"
            f'<ul style="list-style-type: none;">\n{_html_list(hostnames)}\n</ul>'),
        "text": (
            "The DNS lookup for the following domains failed with a transient resolver error,\n"
            "so their DNS status could not be checked. Re-run the report to retry.\n\n"
            f"{_text_list(hostnames)}\n"),
    }


def not_in_dns_notice(site_name, hostnames):
    return {
        "type": "alert",
        "csv": f"{site_name},not-in-dns," + ",".join(hostnames),
        "short": "add domains to DNS",
        "message": (
            f"<p><strong>{html.escape(site_name)}</strong> has domains that are not in DNS.  "
            f"Please either remove these domains from the Pantheon live environment for "
            f"<strong>{html.escape(site_name)}</strong>, or add them to DNS.</p>\n"
            f'<ul style="list-style-type: none;">\n{_html_list(hostnames)}\n</ul>'),
        "text": (
            f"{site_name} has domains that are not in DNS.  Please either\n"
            f"remove these domains from the Pantheon live environment for\n"
            f"{site_name}, or add them to DNS.\n\n{_text_list(hostnames)}\n"),
    }


def not_behind_cloudflare_notice(site_name, hostnames, *, umich):
    if umich:
        intro_html = (
            "<p>ITS strongly recommends you put the following domains behind Cloudflare to "
            "reduce Pantheon traffic and improve security.  Please refer to the "
            '<a href="https://its.umich.edu/computing/web-mobile/cloudflare/getting-started">'
            "Cloudflare at U-M documentation</a>.</p>")
        intro_text = (
            "ITS strongly recommends you put the following domains behind\n"
            "Cloudflare to reduce Pantheon traffic and improve security.\n"
            "Please refer to the Cloudflare at U-M documentation\n"
            "<https://its.umich.edu/computing/web-mobile/cloudflare/getting-started>")
    else:
        intro_html = (
            "<p>We strongly recommend you put the following domains behind Cloudflare to "
            "reduce origin traffic and improve security.</p>")
        intro_text = (
            "We strongly recommend you put the following domains behind Cloudflare\n"
            "to reduce origin traffic and improve security.")
    return {
        "type": "warning",
        "csv": f"{site_name},not-behind-cloudflare," + ",".join(hostnames),
        "short": "put domains behind Cloudflare",
        "message": f'{intro_html}\n<ul style="list-style-type: none;">\n{_html_list(hostnames)}\n</ul>',
        "text": f"{intro_text}\n\n{_text_list(hostnames)}\n",
    }


def behind_cloudflare_not_proxied_notice(site_name, hostnames, *, umich):
    if umich:
        intro_html = (
            "<p>The following domains point to Cloudflare but are not benefitting from "
            "Cloudflare's caching and security features because proxying for these FQDNs is "
            "turned off in Cloudflare.  Please follow steps 3 and 4 of the "
            '<a href="https://documentation.its.umich.edu/node/4237">U-M Cloudflare: Website '
            "Migration Steps</a> to ensure the site is configured to work with Cloudflare and "
            "to turn on proxying.</p>")
        intro_text = (
            "The following domains point to Cloudflare but are not benefitting from\n"
            "Cloudflare's caching and security features because proxying for these\n"
            "FQDNs is turned off in Cloudflare.\n\n"
            "Please follow steps 3 and 4 of the U-M Cloudflare: Website Migration\n"
            "Steps <https://documentation.its.umich.edu/node/4237> to ensure the\n"
            "site is configured to work with Cloudflare and to turn on proxying.")
    else:
        intro_html = (
            "<p>The following domains point to Cloudflare but are not benefitting from "
            "Cloudflare's caching and security features because proxying (the orange cloud) is "
            "turned off for these DNS records.  Turn on proxying for these records in your "
            "Cloudflare dashboard.</p>")
        intro_text = (
            "The following domains point to Cloudflare but are not benefitting from\n"
            "Cloudflare's caching and security features because proxying (the orange\n"
            "cloud) is turned off for these DNS records.  Turn on proxying for these\n"
            "records in your Cloudflare dashboard.")
    return {
        "type": "warning",
        "csv": f"{site_name},behind-cloudflare-not-proxied," + ",".join(hostnames),
        "short": "turn on Cloudflare proxying for domains",
        "message": f'{intro_html}\n<ul style="list-style-type: none;">\n{_html_list(hostnames)}\n</ul>',
        "text": f"{intro_text}\n\n{_text_list(hostnames)}\n",   # bug #2 fix: lists THESE hosts
    }


def proxied_in_multiple_zones_notice(site_name, hostnames):
    return {
        "type": "warning",
        "csv": f"{site_name},proxied-in-multiple-cloudflare-zones," + ",".join(hostnames),
        "short": "domain in multiple Cloudflare zones",
        "message": (
            "<p>The following domains are configured (proxied) in more than one Cloudflare "
            "zone.  Serving a domain from multiple zones can cause inconsistent caching, TLS, "
            "and security settings.  Please consolidate each domain into a single Cloudflare "
            "zone.</p>\n"
            f'<ul style="list-style-type: none;">\n{_html_list(hostnames)}\n</ul>'),
        "text": (
            "The following domains are configured (proxied) in more than one\n"
            "Cloudflare zone.  Serving a domain from multiple zones can cause\n"
            "inconsistent caching, TLS, and security settings.  Please consolidate\n"
            f"each domain into a single Cloudflare zone.\n\n{_text_list(hostnames)}\n"),
    }
```

- [ ] **Step 5: Run to verify it passes**

Run: `./run-tests --fast -- tests/unit/test_dns_notices.py`
Expected: PASS.

- [ ] **Step 6: Add syrupy render snapshots** (guards the moved HTML/plaintext copy — these
notices never appear in the e2e goldens, so substring asserts alone would miss a wording/markup
regression. This snapshots the builder's returned dict — NOT a full `email_template.html` Jinja
render (unlike `test_cachecheck_notice_render.py`); the dict carries the `message` HTML + `text`
plaintext, which is what we need to guard.)

```python
# tests/integration/test_dns_notice_render.py
import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def dns_notices(psh, reset_sc):
    reset_sc.escape_url = lambda u: u
    path = Path(psh.__file__).parent / "check" / "dns" / "notices.py"
    spec = importlib.util.spec_from_file_location("dns_notices_render_probe", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


HOSTS = ["a.example.org", "b.example.org"]


def test_transient_render(dns_notices, snapshot):
    assert dns_notices.transient_notice("s", HOSTS) == snapshot


def test_not_in_dns_render(dns_notices, snapshot):
    assert dns_notices.not_in_dns_notice("s", HOSTS) == snapshot


def test_multiple_zones_render(dns_notices, snapshot):
    assert dns_notices.proxied_in_multiple_zones_notice("s", HOSTS) == snapshot


@pytest.mark.parametrize("umich", [True, False], ids=["umich", "generic"])
def test_not_behind_cloudflare_render(dns_notices, snapshot, umich):
    assert dns_notices.not_behind_cloudflare_notice("s", HOSTS, umich=umich) == snapshot


@pytest.mark.parametrize("umich", [True, False], ids=["umich", "generic"])
def test_not_proxied_render(dns_notices, snapshot, umich):
    assert dns_notices.behind_cloudflare_not_proxied_notice("s", HOSTS, umich=umich) == snapshot
```

- [ ] **Step 7: Generate the snapshots and run**

Run: `./run-tests --update-goldens -- tests/integration/test_dns_notice_render.py`
Then: `./run-tests --fast -- tests/integration/test_dns_notice_render.py`
Expected: the first writes `tests/integration/__snapshots__/test_dns_notice_render.ambr`; the
second PASSes. **Review the generated `.ambr` diff by eye** — it is the human-checked record of
the U-M and generic copy (tests-are-load-bearing NEVER-block).

- [ ] **Step 8: Commit**

```bash
git add check/dns/__init__.py check/dns/notices.py tests/unit/test_dns_notices.py \
        tests/integration/test_dns_notice_render.py \
        tests/integration/__snapshots__/test_dns_notice_render.ambr
git commit -m "feat(check/dns): pure DNS notice builders (U-M + generic, bug #2 fixed) + render snapshots"
```

---

### Task 4: DNS check — `emit_dns_notices` hook + registration

**Files:**
- Modify: `check/dns/__init__.py`
- Create: `check/dns/hook.py`
- Test: `tests/integration/test_check_dns.py`

**Interfaces:**
- Consumes: `check/dns/notices.py` builders (Task 3); the `site_post_dns` contract keys on `SiteContext`; `sc.cloudflare_enabled()` (added in Task 5 — the hook calls it at runtime; tests set `sc.cloudflare_enabled`).
- Produces: `check.dns.hook.emit_dns_notices(site_context)`, registered on `site_post_dns`.

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_check_dns.py
import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _load_init(psh, monkeypatch, probe_name="dns_check_probe"):
    pkg_dir = Path(psh.__file__).parent / "check" / "dns"
    spec = importlib.util.spec_from_file_location(
        probe_name, str(pkg_dir / "__init__.py"),
        submodule_search_locations=[str(pkg_dir)])
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, probe_name, module)
    for sub in ("hook", "notices"):
        monkeypatch.delitem(sys.modules, f"{probe_name}.{sub}", raising=False)
    spec.loader.exec_module(module)
    return module


def _facts(reset_sc, **overrides):
    ctx = reset_sc.SiteContext({"name": "s"})
    base = dict(domains={}, custom_domains=[], primary_domain=[], main_fqdn="",
                not_in_dns=[], fqdns_behind_cloudflare=[], fqdns_not_behind_cloudflare=[],
                behind_cloudflare_not_proxied=[], proxied_in_multiple_zones=[], dns_transient=[])
    base.update(overrides)
    ctx.update(base)
    return ctx


def test_registers_unconditionally(psh, reset_sc, monkeypatch):
    reset_sc.config = {}                       # no [Cloudflare], no [UMich]
    _load_init(psh, monkeypatch)
    assert [h["name"] for h in reset_sc.hooks["site_post_dns"]] == \
        ["check.dns.hook.emit_dns_notices"]


def test_emits_universal_notices(psh, reset_sc, monkeypatch):
    reset_sc.cloudflare_enabled = lambda: False
    reset_sc.umich_enabled = lambda: False
    reset_sc.escape_url = lambda u: u
    mod = _load_init(psh, monkeypatch)
    ctx = _facts(reset_sc, not_in_dns=["x.example.org"], dns_transient=["t.example.org"])
    mod.hook.emit_dns_notices(ctx)
    codes = [n["csv"].split(",")[1] for n in ctx["notices"]]
    assert "not-in-dns" in codes and "dns-lookup-failed" in codes
    assert codes.count("dns-lookup-failed") == 1     # aggregated: ONE notice for all hosts


def test_cloudflare_notices_gated_off_when_disabled(psh, reset_sc, monkeypatch):
    reset_sc.cloudflare_enabled = lambda: False
    reset_sc.umich_enabled = lambda: False
    reset_sc.escape_url = lambda u: u
    mod = _load_init(psh, monkeypatch)
    ctx = _facts(reset_sc, fqdns_not_behind_cloudflare=["a.example.org"],
                 behind_cloudflare_not_proxied=["b.example.org"],
                 proxied_in_multiple_zones=["c.example.org"])
    mod.hook.emit_dns_notices(ctx)
    assert ctx["notices"] == []                # all three are Cloudflare-gated


def test_bug1_notices_independent(psh, reset_sc, monkeypatch):
    # Fully behind Cloudflare (fqdns_not_behind_cloudflare empty) but a zone conflict + a
    # not-proxied host: both notices MUST still fire (old code nested them and suppressed them).
    reset_sc.cloudflare_enabled = lambda: True
    reset_sc.umich_enabled = lambda: False
    reset_sc.escape_url = lambda u: u
    mod = _load_init(psh, monkeypatch)
    ctx = _facts(reset_sc, fqdns_not_behind_cloudflare=[],
                 behind_cloudflare_not_proxied=["np.example.org"],
                 proxied_in_multiple_zones=["mz.example.org"])
    mod.hook.emit_dns_notices(ctx)
    codes = {n["csv"].split(",")[1] for n in ctx["notices"]}
    assert "behind-cloudflare-not-proxied" in codes
    assert "proxied-in-multiple-cloudflare-zones" in codes


def test_transient_emitted_before_cloudflare_warnings(psh, reset_sc, monkeypatch):
    # Subject-line stability (design §7 note b): transient must precede the Cloudflare warnings
    # so a warning-only site keeps its "DNS lookup failed (transient)" email subject.
    reset_sc.cloudflare_enabled = lambda: True
    reset_sc.umich_enabled = lambda: False
    reset_sc.escape_url = lambda u: u
    mod = _load_init(psh, monkeypatch)
    ctx = _facts(reset_sc, dns_transient=["t.example.org"],
                 fqdns_not_behind_cloudflare=["a.example.org"])
    mod.hook.emit_dns_notices(ctx)
    codes = [n["csv"].split(",")[1] for n in ctx["notices"]]
    assert codes.index("dns-lookup-failed") < codes.index("not-behind-cloudflare")
```

- [ ] **Step 2: Run to verify it fails**

Run: `./run-tests --fast -- tests/integration/test_check_dns.py`
Expected: FAIL — `check.dns.hook` missing / no registration.

- [ ] **Step 3: Implement `check/dns/hook.py`**

```python
# check/dns/hook.py
"""site_post_dns hook: build DNS-resolution notices from the contract facts.

Emission order: the aggregated transient warning FIRST, then the three Cloudflare notices (each
from its own independent guard — bug #1 fix), then not-in-dns. Transient-first keeps a
warning-only site's email subject as "DNS lookup failed (transient)" (the renderer takes the
subject from the first notice after a type sort), matching the pre-refactor loop. See design §7
note (b) for the one accepted residual (an enabled Cloudflare-cache check's warnings now precede
the transient notice).
"""
import script_context as sc

from .notices import (behind_cloudflare_not_proxied_notice, not_behind_cloudflare_notice,
                      not_in_dns_notice, proxied_in_multiple_zones_notice, transient_notice)


def emit_dns_notices(site_context) -> None:
    umich = sc.umich_enabled()
    site = site_context["site"]["name"]

    if site_context["dns_transient"]:
        site_context.add_notice(transient_notice(site, site_context["dns_transient"]))

    if sc.cloudflare_enabled():
        if site_context["fqdns_not_behind_cloudflare"]:
            site_context.add_notice(not_behind_cloudflare_notice(
                site, site_context["fqdns_not_behind_cloudflare"], umich=umich))
        if site_context["behind_cloudflare_not_proxied"]:
            site_context.add_notice(behind_cloudflare_not_proxied_notice(
                site, site_context["behind_cloudflare_not_proxied"], umich=umich))
        if site_context["proxied_in_multiple_zones"]:
            site_context.add_notice(proxied_in_multiple_zones_notice(
                site, site_context["proxied_in_multiple_zones"]))

    if site_context["not_in_dns"]:
        site_context.add_notice(not_in_dns_notice(site, site_context["not_in_dns"]))
```

- [ ] **Step 3b: Expose `cloudflare_enabled` on `sc` (needed at registration time)**

The hook calls `sc.cloudflare_enabled()` at runtime, so the exposure MUST land no later than
this task (moved here from Task 5 to keep this commit green — otherwise a full/e2e run at this
commit would raise `AttributeError: module 'script_context' has no attribute 'cloudflare_enabled'`).
In `pantheon-sitehealth-emails`, just after `sc.umich_enabled = umich_enabled`, add:

```python
sc.cloudflare_enabled = cloudflare_enabled
```

> Transitional-state note (Prime Directive #9): between this task and Task 5, the OLD inline
> DNS notice blocks in core still coexist with the new hook, so a full pipeline run would emit
> the DNS notices twice. This is harmless for the tests and goldens (Cloudflare is disabled and
> fixture domains are platform-only, so zero DNS-resolution notices appear either way) and is
> resolved in Task 5 Step 5 when the old blocks are deleted.

- [ ] **Step 4: Register the hook in `check/dns/__init__.py`**

Replace the placeholder body from Task 3 with:

```python
# check/dns/__init__.py
"""Site-level DNS-resolution notices (site_post_dns).

Registers unconditionally: DNS checks are not disable-able.  The three Cloudflare notices
self-gate on sc.cloudflare_enabled(); U-M wording is chosen via sc.umich_enabled().  The
resolution FACTS are produced by dns_classify.classify_domains() in core before the phase
fires (see docs/superpowers/specs/2026-07-10-modular-dns-checks-design.md).
"""
import script_context as sc

from .hook import emit_dns_notices

sc.add_hook('site_post_dns', {'name': 'check.dns.hook.emit_dns_notices',
                              'func': emit_dns_notices})
```

- [ ] **Step 5: Run to verify it passes**

Run: `./run-tests --fast -- tests/integration/test_check_dns.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add check/dns/__init__.py check/dns/hook.py tests/integration/test_check_dns.py
git commit -m "feat(check/dns): emit_dns_notices site_post_dns hook (bug #1 fixed)"
```

---

### Task 5: Wire core to the engine + check; remove moved code

**Files:**
- Modify: `pantheon-sitehealth-emails` (core script)
- Delete: `tests/integration/test_dns.py` (cases ported to `tests/unit/test_dns_classify.py`)

**Interfaces:**
- Consumes: `dns_classify.classify_domains` (Task 2); `check.dns` auto-discovered by `find_modules`.

- [ ] **Step 1: Verify `sc.cloudflare_enabled` exposure**

Confirm the `sc.cloudflare_enabled = cloudflare_enabled` line (added in Task 4 Step 3b) is
present in the `sc.*` exposure block. If Tasks 4 and 5 were merged into one session, add it
here instead:

```bash
git grep -n "sc.cloudflare_enabled = cloudflare_enabled" pantheon-sitehealth-emails
```
Expected: one match. If zero, add the line just after `sc.umich_enabled = umich_enabled`.

- [ ] **Step 2: Import the engine**

Near the top of `pantheon-sitehealth-emails`, alongside the other top-level imports, add:

```python
import dns_classify
```

- [ ] **Step 3: Replace the inline DNS block in `main()`**

Locate the domain block that begins with `site_url = ""` / `main_fqdn = ""` (after the
`domains, errors, fatal = terminus("domain:list", live_site)` fetch) and runs through
`primary_domain = [d for d in custom_domains if domains[d]["primary"]]`. Replace the
initializers + the `if isinstance(domains, dict):` resolution loop **up to and including** the
`custom_domains`/`primary_domain` comprehensions with:

```python
        site_url = ""
        facts = dns_classify.classify_domains(
            domains,
            cloudflare_enabled(),
            sc.plugin_context["plugin.cloudflare"]["cloudflare_ipv4_nets"]
            if cloudflare_enabled() else [],
            sc.plugin_context["plugin.cloudflare"]["cloudflare_ipv6_nets"]
            if cloudflare_enabled() else [],
            sc.plugin_context["plugin.cloudflare"]["proxied_fqdns"]
            if cloudflare_enabled() else {},
            sc.plugin_context["plugin.cloudflare"].get("fqdn_zone_conflicts", {})
            if cloudflare_enabled() else {},
            fqdn_re,
        )
        main_fqdn = facts.main_fqdn
        custom_domains = facts.custom_domains
        primary_domain = facts.primary_domain
        fqdns_not_behind_cloudflare = facts.fqdns_not_behind_cloudflare  # used by favicon check
```

**CRITICAL — re-wrap the retained notices.** In the current code there is exactly ONE
`if isinstance(domains, dict):` block (`pantheon-sitehealth-emails:1749`), and it contains the
resolution loop, the `custom_domains`/`primary_domain` comprehensions, AND the `no-domains` /
`no-primary-domain` domain-config notices — all indented inside that single `if`. The
replacement above consumes that `if` header (it replaced "up to and including the
comprehensions"), so the retained `no-domains`/`no-primary-domain` code would be left
**unguarded**. It MUST be re-wrapped in its own `if isinstance(domains, dict):`, or the
non-dict/malformed shadow path breaks: with `facts.custom_domains == []`, `no-domains` would
fire where today the whole block is skipped (spec §10 requires "isinstance guard preserved").
So the retained block becomes:

```python
        if isinstance(domains, dict):
            if len(custom_domains) == 0:
                site_context.add_notice({ ...no-domains, unchanged... })
            if (len(custom_domains) > 1 and len(primary_domain) == 0
                    and site["framework"] != "wordpress_network"):
                ...no-primary-domain drush multisite check, unchanged...
```

Keep the `no-domains` / `no-primary-domain` notice bodies byte-for-byte as they are today; only
their `if isinstance(...)` wrapper is re-introduced. They read `custom_domains`/`primary_domain`,
now sourced from `facts`.

- [ ] **Step 4: Publish the contract keys via the helper + fire the phase**

Replace the `site_context["..."] = ...` block (the `# Per-phase data contract` block) with a call
to the extracted helper (defined in Task 2) plus the hook invocation. The helper publishes all
ten contract keys from `facts`; the local `main_fqdn`/`custom_domains`/`primary_domain`/
`fqdns_not_behind_cloudflare` set in Step 3 remain for the downstream core code (`site_url`,
`no-domains`/`no-primary-domain`, favicon check):

```python
        # Per-phase data contract (see CLAUDE.md): publish the DnsFacts via the pure helper
        # (unit-tested against value-swaps in test_dns_classify.py), then fire the phase. The
        # check.dns hook consumes these keys to emit the DNS-resolution notices.
        dns_classify.stuff_dns_contract(site_context, domains, facts)
        sc.invoke_hooks("site_post_dns", site_context)
```

- [ ] **Step 5: Delete the moved notice blocks**

Delete the `if len(fqdns_not_behind_cloudflare) > 0:` notice block and its nested
`behind-cloudflare-not-proxied` / `proxied-in-multiple-zones` blocks, and the following
`if len(not_in_dns) > 0:` block (the whole span emitting `not-behind-cloudflare`,
`behind-cloudflare-not-proxied`, `proxied-in-multiple-cloudflare-zones`, `not-in-dns`).
These now live in `check/dns/`. Do NOT delete the favicon check that follows.

- [ ] **Step 6: Delete `classify_hostname_dns` from core**

Delete the entire `def classify_hostname_dns(...)` definition (the one that returns a 4-tuple
with a notices list) from `pantheon-sitehealth-emails` — it now lives in `dns_classify.py`.

- [ ] **Step 7: Remove now-unused imports**

Run and inspect:

```bash
git grep -n "classify_hostname_dns" pantheon-sitehealth-emails
git grep -nE "\bdns\.|dns\.resolver" pantheon-sitehealth-emails
git grep -nE "\bipaddress\b" pantheon-sitehealth-emails
```

- `classify_hostname_dns` MUST have zero matches. If `dns.`/`dns.resolver` has zero matches,
  remove `import dns.resolver` from the core. If `ipaddress` has zero matches, remove
  `import ipaddress`. If a symbol is still referenced elsewhere, leave its import.

- [ ] **Step 8: Verify no dangling references to moved locals**

```bash
git grep -nE "\bnot_in_dns\b|\bbehind_cloudflare_not_proxied\b|\bproxied_in_multiple_zones\b|\bfqdns_behind_cloudflare\b|\bdns_transient_fqdns\b" pantheon-sitehealth-emails
```

Expected: only the contract-stuffing lines from Step 4 reference these (via `facts.` or the
`site_context[...]` keys). `fqdns_not_behind_cloudflare` may also appear in the favicon check
(kept). Any other bare reference is a dangling local — fix it to read from `facts`.

- [ ] **Step 9: Delete the superseded integration test**

```bash
git rm tests/integration/test_dns.py
```

- [ ] **Step 10: Run the offline suite — goldens MUST be byte-identical**

Run: `./run-tests --fast`
Expected: PASS, including the WordPress, Drupal, and non-U-M goldens, with NO golden diff. If a
golden changed, STOP — investigate; do NOT `--update-goldens` without a reviewed reason
(NEVER-block).

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "refactor(dns): route core through dns_classify + check.dns; drop inline DNS"
```

---

### Task 6: Docs + full verification

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update `CLAUDE.md`**

- In the `find_modules` inventory sentence, add `check.dns` to the imported-packages list.
- In the `check/` description, add one line: DNS-resolution notices live in `check/dns/`
  (`notices.py` builders + the `site_post_dns` `hook.py`), fed by the `dns_classify.py` engine;
  `no-domains`/`no-primary-domain` remain in core.
- Add `dns_classify.py` to the single-module/architecture description as the DNS engine, and
  note `sc.cloudflare_enabled` is now exposed for check packages (alongside `sc.umich_enabled`).
- The `site_post_dns` data-contract table is unchanged (same keys) — no edit needed there beyond
  noting the producer is `dns_classify.classify_domains`.

- [ ] **Step 2: Full test run**

Run: `./run-tests`
Expected: PASS across all tiers (unit, integration, e2e, render). Paste the summary line.

- [ ] **Step 3: Acceptance checks (paste actual output)**

```bash
git grep -n "classify_hostname_dns" pantheon-sitehealth-emails   # expect: no matches
./run-tests --fast                                               # expect: pass, goldens unchanged
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(dns): document dns_classify engine + check.dns package"
```

---

## Self-Review (completed against the spec)

- **Spec coverage:** engine (Tasks 1–2), check builders + hook (Tasks 3–4), core rewiring +
  import cleanup (Task 5), bug #1 (Task 2 list + Task 4 notice-independence), bug #2 (Task 3),
  U-M gating (Task 3), transient aggregation (Task 3), unconditional registration (Task 4),
  `sc.cloudflare_enabled` (Task 5), goldens NEVER-block (Task 5 Step 10), docs (Task 6). All spec
  sections map to a task.
- **Placeholder scan:** none — every code step shows complete code; every run step shows the
  command + expected result.
- **Type consistency:** `DnsFacts` field names are identical in the NamedTuple (Task 2), the
  core stuffing (Task 5), and the hook reads (Task 4). Builder names match between `notices.py`
  (Task 3) and `hook.py` (Task 4). `classify_domains` signature is identical in Task 2 and its
  Task 5 call site.
- **Deviation from spec §13 (noted):** bug #1 has coverage in BOTH tiers — the engine test
  asserts the list is populated (Task 2), the check test asserts the notice fires independently
  (Task 4), because the original bug was in notice emission, not list computation.

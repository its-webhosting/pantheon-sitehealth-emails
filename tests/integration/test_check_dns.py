import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _load_init(psh, monkeypatch, probe_name="dns_check_probe"):
    pkg_dir = Path(psh.__file__).resolve().parents[1] / "check" / "dns"
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
    monkeypatch.setattr(reset_sc, "cloudflare_enabled", lambda: False)
    monkeypatch.setattr(reset_sc, "umich_enabled", lambda: False)
    monkeypatch.setattr(reset_sc, "escape_url", lambda u: u)
    mod = _load_init(psh, monkeypatch)
    ctx = _facts(reset_sc, not_in_dns=["x.example.org"], dns_transient=["t.example.org"])
    mod.hook.emit_dns_notices(ctx)
    codes = [n["csv"].split(",")[1] for n in ctx["notices"]]
    assert "not-in-dns" in codes and "dns-lookup-failed" in codes
    assert codes.count("dns-lookup-failed") == 1     # aggregated: ONE notice for all hosts


def test_cloudflare_notices_gated_off_when_disabled(psh, reset_sc, monkeypatch):
    monkeypatch.setattr(reset_sc, "cloudflare_enabled", lambda: False)
    monkeypatch.setattr(reset_sc, "umich_enabled", lambda: False)
    monkeypatch.setattr(reset_sc, "escape_url", lambda u: u)
    mod = _load_init(psh, monkeypatch)
    ctx = _facts(reset_sc, fqdns_not_behind_cloudflare=["a.example.org"],
                 behind_cloudflare_not_proxied=["b.example.org"],
                 proxied_in_multiple_zones=["c.example.org"])
    mod.hook.emit_dns_notices(ctx)
    assert ctx["notices"] == []                # all three are Cloudflare-gated


def test_bug1_notices_independent(psh, reset_sc, monkeypatch):
    # Fully behind Cloudflare (fqdns_not_behind_cloudflare empty) but a zone conflict + a
    # not-proxied host: both notices MUST still fire (old code nested them and suppressed them).
    monkeypatch.setattr(reset_sc, "cloudflare_enabled", lambda: True)
    monkeypatch.setattr(reset_sc, "umich_enabled", lambda: False)
    monkeypatch.setattr(reset_sc, "escape_url", lambda u: u)
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
    monkeypatch.setattr(reset_sc, "cloudflare_enabled", lambda: True)
    monkeypatch.setattr(reset_sc, "umich_enabled", lambda: False)
    monkeypatch.setattr(reset_sc, "escape_url", lambda u: u)
    mod = _load_init(psh, monkeypatch)
    ctx = _facts(reset_sc, dns_transient=["t.example.org"],
                 fqdns_not_behind_cloudflare=["a.example.org"])
    mod.hook.emit_dns_notices(ctx)
    codes = [n["csv"].split(",")[1] for n in ctx["notices"]]
    assert codes.index("dns-lookup-failed") < codes.index("not-behind-cloudflare")

"""Integration tier: psh.cli.fetch_site_domains and psh.cli.resolve_site_url, the two halves
of main()'s domains/DNS stage (development/2026-08-07-main-extraction/SPEC.md section 5.3 --
B29, and B30 (residue) + B31's site_url derivation + B32 (residue)).

They are TWO functions and not one because the stage spine sits between them: main() calls
fetch_site_domains, then dns_classify.stuff_dns_contract + sc.invoke_hooks("site_post_dns")
inline (R-G2), then resolve_site_url -- which is why resolve_site_url can read the
hook-produced drupal_multisite_smell / drupal_multisite keys at all.

Seams (SPEC section 6 row 3b, all pre-existing):

* psh.gateway.run_terminus -- the `gateway` conftest fixture.  terminus() and wp_eval()
  both resolve run_terminus in psh.gateway's OWN namespace (CLAUDE.md "Two mock seams"), so
  patching psh.cli's imported binding would not intercept them.
* psh.dns_classify.resolve -- tests/helpers/dnsfake.patch_resolve.  The ONE DNS seam; without
  it classify_domains makes real A/AAAA lookups.
* psh.cli.cloudflare_enabled -- **NOT** sc.cloudflare_enabled (SPEC S5).  psh/cli.py does
  `from psh.configuration import cloudflare_enabled`, so the bare call inside
  fetch_site_domains resolves in psh.cli's own namespace and a monkeypatch of the sc facade
  never reaches it.  Both failure modes of getting this wrong are silent-or-confusing rather
  than loud: patching sc and expecting DISABLED passes while testing nothing (the real
  cloudflare_enabled() is also falsy under a config with no [Cloudflare] section), and
  patching sc and expecting ENABLED raises a bare KeyError on
  sc.plugin_context["plugin.cloudflare"].  test_the_cloudflare_gate_is_read_through_psh_cli_s
  _own_binding is the instrument that makes the seam itself go red.
  The existing monkeypatch.setattr(reset_sc, "cloudflare_enabled", ...) calls in
  tests/integration/test_check_dns.py are not a counter-example: those drive check/ modules,
  whose consumer genuinely calls the sc facade.
"""
import ipaddress
import json

import pytest
from helpers.dnsfake import patch_resolve, recording_console

import psh.cli

pytestmark = pytest.mark.integration

SITE = {
    "id": "test-site-id",
    "name": "its-wws-test1",
    "framework": "wordpress",
    "plan_name": "Performance Small",
}
SITE_NETWORK = {**SITE, "framework": "wordpress_network"}
LIVE = "test-site-id.live"

PLATFORM = {"id": "live-its-wws-test1.pantheonsite.io", "type": "platform", "primary": False}
CUSTOM = {"id": "www.example.com", "type": "custom", "primary": True}
PLATFORM_ONLY = {PLATFORM["id"]: PLATFORM}
WITH_CUSTOM = {PLATFORM["id"]: PLATFORM, CUSTOM["id"]: CUSTOM}

# A definitive non-Cloudflare answer, so classify_domains takes its "resolved >= 1 address"
# branch without any transient/NXDOMAIN noise.
ZONE = {("www.example.com", "A"): ["203.0.113.10"]}


def _ctx(reset_sc, site=SITE):
    return reset_sc.SiteContext(dict(site))


def _terminus_returning(monkeypatch, gateway, payload, *, stderr="", fatal=False):
    """Point run_terminus at one canned domain:list response."""
    def fake(command, input_data=None):
        assert "domain:list" in command, f"unexpected command: {command}"
        return (payload, stderr, fatal)
    monkeypatch.setattr(gateway, "run_terminus", fake)


# ── fetch_site_domains: happy path ───────────────────────────────────────────────────
def test_a_dict_payload_returns_the_raw_domains_and_the_classified_facts(
    gateway, reset_sc, monkeypatch
):
    patch_resolve(monkeypatch, ZONE)
    _terminus_returning(monkeypatch, gateway, json.dumps(WITH_CUSTOM))
    ctx = _ctx(reset_sc)
    fetched = psh.cli.fetch_site_domains(SITE, LIVE, ctx)
    assert fetched is not None
    domains, facts = fetched
    assert domains == WITH_CUSTOM          # the RAW payload, not the facts
    assert facts.custom_domains == ["www.example.com"]
    assert facts.primary_domain == ["www.example.com"]
    assert facts.main_fqdn == "www.example.com"
    assert ctx["notices"] == []            # a site WITH a custom domain gets no alert


# ── fetch_site_domains: the skip sentinel (R3.1 / R-G3) ──────────────────────────────
def test_a_fatal_domain_list_returns_the_skip_sentinel_and_names_the_site(
    gateway, reset_sc, monkeypatch
):
    console = recording_console(monkeypatch, reset_sc, width=80)
    _terminus_returning(monkeypatch, gateway, "", stderr="boom", fatal=True)
    ctx = _ctx(reset_sc)
    assert psh.cli.fetch_site_domains(SITE, LIVE, ctx) is None
    # PD#1: the skip must be visible to the operator, not silent.  main() does the continue.
    assert "could not fetch domains for its-wws-test1" in console.export_text()


def test_an_undecodable_payload_returns_the_skip_sentinel(gateway, reset_sc, monkeypatch):
    # terminus() returns result=None on a JSONDecodeError; `fatal` stays False, so the
    # `domains is None` half of the guard is the only thing that catches this.
    _terminus_returning(monkeypatch, gateway, "not json at all")
    ctx = _ctx(reset_sc)
    assert psh.cli.fetch_site_domains(SITE, LIVE, ctx) is None


# ── fetch_site_domains: the no-domains alert (R3.7 shadow paths) ─────────────────────
def test_a_paid_site_with_no_custom_domains_gets_the_alert(gateway, reset_sc, monkeypatch):
    _terminus_returning(monkeypatch, gateway, json.dumps(PLATFORM_ONLY))
    ctx = _ctx(reset_sc)
    fetched = psh.cli.fetch_site_domains(SITE, LIVE, ctx)
    assert fetched is not None
    assert fetched.facts.custom_domains == []
    assert [n["csv"] for n in ctx["notices"]] == ["its-wws-test1,no-domains"]


def test_an_empty_dict_payload_gets_the_alert(gateway, reset_sc, monkeypatch):
    # PD#3 empty-input shadow: {} is a dict, so the guard passes and the alert fires.
    _terminus_returning(monkeypatch, gateway, json.dumps({}))
    ctx = _ctx(reset_sc)
    fetched = psh.cli.fetch_site_domains(SITE, LIVE, ctx)
    assert fetched is not None
    assert fetched.domains == {}
    assert [n["csv"] for n in ctx["notices"]] == ["its-wws-test1,no-domains"]


def test_a_non_dict_payload_is_returned_but_raises_no_alert(gateway, reset_sc, monkeypatch):
    # PD#3 upstream-error shadow (R3.6b): a JSON list decodes fine, so neither the fatal nor
    # the None guard fires; the isinstance guard inside no_domains_notice is the only thing
    # that stops a false "downgrade your plan" ALERT reaching the owner.
    _terminus_returning(monkeypatch, gateway, json.dumps(["www.example.com"]))
    ctx = _ctx(reset_sc)
    fetched = psh.cli.fetch_site_domains(SITE, LIVE, ctx)
    assert fetched is not None
    assert fetched.domains == ["www.example.com"]
    assert fetched.facts.custom_domains == []   # all-empty DnsFacts for a non-dict payload
    assert ctx["notices"] == []


# ── fetch_site_domains: the Cloudflare gate (SPEC S5) ────────────────────────────────
def test_the_cloudflare_gate_is_read_through_psh_cli_s_own_binding(
    gateway, reset_sc, monkeypatch
):
    """S5: the gate MUST be reachable at psh.cli.cloudflare_enabled.

    Recording the call is what makes the seam itself an instrument: if fetch_site_domains
    were rewritten to call sc.cloudflare_enabled() (the facade -- the shape four existing
    check/ tests use), this patch would no longer intercept it and `calls` would stay empty.
    Asserting only on the classification result could not tell the two apart, because the
    real cloudflare_enabled() also returns falsy under reset_sc's empty config."""
    calls = []
    monkeypatch.setattr(psh.cli, "cloudflare_enabled", lambda: calls.append("cf") or True)
    reset_sc.plugin_context["plugin.cloudflare"] = {
        # ip_network objects, not strings: that is what plugin/cloudflare/ips.py puts in the
        # bag, and classify_hostname_dns does `address in net` with an IPv4Address on the left.
        "cloudflare_ipv4_nets": [ipaddress.ip_network("203.0.113.0/24")],
        "cloudflare_ipv6_nets": [],
        "proxied_fqdns": {"www.example.com": {"zone_id": "z", "origins": []}},
        # fqdn_zone_conflicts deliberately ABSENT: the call site reads it with .get(), and a
        # bag written by an older fqdns.json refresh does not carry the key (R3.4).
    }
    patch_resolve(monkeypatch, ZONE)
    _terminus_returning(monkeypatch, gateway, json.dumps(WITH_CUSTOM))
    fetched = psh.cli.fetch_site_domains(SITE, LIVE, _ctx(reset_sc))
    assert calls == ["cf"]
    assert fetched is not None
    # 203.0.113.10 is inside the net above and the FQDN is proxied -> behind Cloudflare.
    assert fetched.facts.fqdns_behind_cloudflare == ["www.example.com"]
    assert fetched.facts.proxied_in_multiple_zones == []


def test_the_plugin_context_bag_is_never_read_when_the_gate_is_off(
    gateway, reset_sc, monkeypatch
):
    # The bag exists only when [Cloudflare] is enabled; reading it unconditionally would be a
    # KeyError on every run of a non-Cloudflare institution.  reset_sc leaves plugin_context {}.
    monkeypatch.setattr(psh.cli, "cloudflare_enabled", lambda: False)
    patch_resolve(monkeypatch, ZONE)
    _terminus_returning(monkeypatch, gateway, json.dumps(WITH_CUSTOM))
    fetched = psh.cli.fetch_site_domains(SITE, LIVE, _ctx(reset_sc))
    assert fetched is not None
    assert fetched.facts.fqdns_behind_cloudflare == []


# ── resolve_site_url ─────────────────────────────────────────────────────────────────
def _facts(**overrides):
    """A DnsFacts built as plain data -- resolve_site_url reads only three of its fields."""
    from psh import dns_classify
    base = {
        "custom_domains": [], "primary_domain": [], "main_fqdn": "", "not_in_dns": [],
        "fqdns_behind_cloudflare": [], "fqdns_not_behind_cloudflare": [],
        "behind_cloudflare_not_proxied": [], "proxied_in_multiple_zones": [],
        "dns_transient": [],
    }
    return dns_classify.DnsFacts(**{**base, **overrides})


def test_the_main_fqdn_becomes_the_site_url(reset_sc):
    result = psh.cli.resolve_site_url(
        SITE, LIVE, _ctx(reset_sc), _facts(main_fqdn="www.example.com"))
    assert result.site_url == "https://www.example.com/"
    assert result.wp_smell == ""
    assert result.drush_smell == ""


def test_no_main_fqdn_leaves_the_site_url_empty(reset_sc):
    # PD#3 empty-input shadow.  site_url's `= ""` pre-binding moved INTO the helper (R3.3),
    # so a site with no resolvable main FQDN must still get "" and not a NameError.
    result = psh.cli.resolve_site_url(SITE, LIVE, _ctx(reset_sc), _facts())
    assert result.site_url == ""


def test_the_multisite_probe_smell_comes_back_as_a_drush_delta(reset_sc):
    ctx = _ctx(reset_sc)
    ctx["drupal_multisite_smell"] = "PHP Notice: undefined index"
    result = psh.cli.resolve_site_url(SITE, LIVE, ctx, _facts())
    assert result.drush_smell == "PHP Notice: undefined index"
    assert result.wp_smell == ""


def test_an_absent_multisite_key_is_read_with_get_not_indexed(reset_sc):
    """R3.5: drupal_multisite_smell / drupal_multisite are HOOK-produced, not registry-owned.

    They are absent whenever the probe did not run -- a non-Drupal site, [Check.drupal]
    disabled, or the gate failing -- which is every WordPress site in the org.  An index read
    would be a KeyError on the common path."""
    result = psh.cli.resolve_site_url(SITE, LIVE, _ctx(reset_sc), _facts())
    assert result.drush_smell == ""


def test_an_empty_probe_smell_is_not_propagated_as_a_delta(reset_sc):
    # R-G5: "" means "no NEW smell", never "clear the previous one".  main()'s merge is
    # `if != ""`, so the helper must return "" rather than something falsy-but-different.
    ctx = _ctx(reset_sc)
    ctx["drupal_multisite_smell"] = ""
    assert psh.cli.resolve_site_url(SITE, LIVE, ctx, _facts()).drush_smell == ""


def test_the_no_primary_domain_notice_is_emitted_here(reset_sc):
    ctx = _ctx(reset_sc)
    psh.cli.resolve_site_url(
        SITE, LIVE, ctx,
        _facts(custom_domains=["a.example.com", "b.example.com"], primary_domain=[]))
    assert [n["csv"] for n in ctx["notices"]] == ["its-wws-test1,no-primary-domain,"]


def test_a_multisite_suppresses_the_no_primary_domain_notice(reset_sc):
    ctx = _ctx(reset_sc)
    ctx["drupal_multisite"] = True
    psh.cli.resolve_site_url(
        SITE, LIVE, ctx,
        _facts(custom_domains=["a.example.com", "b.example.com"], primary_domain=[]))
    assert ctx["notices"] == []


# ── resolve_site_url: the wordpress_network branch (B32 residue) ─────────────────────
def test_a_wordpress_network_url_overrides_the_main_fqdn_url(gateway, reset_sc, monkeypatch):
    # wp_eval returns raw stripped stdout, NOT parsed JSON (psh/gateway.py) -- so the fake
    # yields the bare URL, not json.dumps of it.
    monkeypatch.setattr(
        gateway, "run_terminus",
        lambda command, input_data=None: ("https://network.example.com/\n", "", False))
    result = psh.cli.resolve_site_url(
        SITE_NETWORK, LIVE, _ctx(reset_sc, SITE_NETWORK), _facts(main_fqdn="www.example.com"))
    assert result.site_url == "https://network.example.com/"


def test_a_wordpress_network_probe_smell_comes_back_as_a_wp_delta(
    gateway, reset_sc, monkeypatch
):
    monkeypatch.setattr(
        gateway, "run_terminus",
        lambda command, input_data=None: ("https://network.example.com/",
                                          "PHP Warning: deprecated", False))
    result = psh.cli.resolve_site_url(
        SITE_NETWORK, LIVE, _ctx(reset_sc, SITE_NETWORK), _facts())
    assert result.wp_smell == "PHP Warning: deprecated"
    assert result.drush_smell == ""


def test_a_fatal_network_url_fetch_blanks_the_site_url_and_notices_the_failure(
    gateway, reset_sc, monkeypatch
):
    """PD#3 upstream-error shadow, pinning the behavior AS MOVED -- which is not the obvious one.

    wordpress_network_url returns (None, smell) only when the eval produced a non-str; on a
    FATAL eval run_terminus still yields "" and `"".strip()` is a str, so it returns ("", "")
    -- and `if network_url is not None` then overwrites the main_fqdn URL with "".  A
    wordpress_network site whose network_home_url eval dies therefore loses its site_url
    entirely, despite having a perfectly good main FQDN.  That is pre-existing behavior
    (psh/cli.py before this extraction, psh/gather.py:247-249), preserved verbatim here and
    pinned so a later change to it is a deliberate one rather than a silent one."""
    monkeypatch.setattr(
        gateway, "run_terminus", lambda command, input_data=None: ("", "boom", True))
    ctx = _ctx(reset_sc, SITE_NETWORK)
    result = psh.cli.resolve_site_url(
        SITE_NETWORK, LIVE, ctx, _facts(main_fqdn="www.example.com"))
    assert result.site_url == ""
    assert result.wp_smell == ""   # a FATAL fetch produces a notice, not a smell
    assert any(n["csv"].startswith("its-wws-test1,wp-error,version-check,") for n in ctx["notices"])


def test_a_non_network_site_makes_no_subprocess_call(gateway, reset_sc, monkeypatch):
    calls = []
    monkeypatch.setattr(
        gateway, "run_terminus",
        lambda command, input_data=None: calls.append(command) or ("", "", True))
    psh.cli.resolve_site_url(SITE, LIVE, _ctx(reset_sc), _facts(main_fqdn="www.example.com"))
    assert calls == []

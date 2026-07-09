"""Syrupy snapshots of the cache-check notice as rendered content (SPEC D8).

A representative consolidated notice (several item types, two FQDNs) is built by the real
notices.py, added through the real SiteContext.add_notice (which generates the plaintext
via html2text), and pushed through the real email_template.html Jinja render in-process.
Snapshots freeze the U-M and generic language variants; a separate assertion proves
remotely-derived strings cannot inject HTML.
"""
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

SITE = "its-wws-test1"
DOC = "https://documentation.its.umich.edu/cloudflare-cache-report"

_CACHED = {}


def _notices_module(psh):
    if "m" not in _CACHED:
        path = Path(psh.__file__).parent / "check" / "cloudflare" / "notices.py"
        loader = SourceFileLoader("cachecheck_notices_render_probe", str(path))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        _CACHED["m"] = module
    return _CACHED["m"]


def _item(item_id, url, kind="page", **params):
    # Production always attaches the cookie names to set-cookie items; mirror that.
    if item_id in ("set-cookie", "set-cookie-bypass") and "cookies" not in params:
        params["cookies"] = "sessionid"
    if "cookies" in params and "cookie_count" not in params:
        params["cookie_count"] = len(params["cookies"].split(", "))
    return {"id": item_id, "kind": kind, "url": url, "params": params}


def _representative_items(fqdn):
    return [
        _item("set-cookie-bypass", f"https://{fqdn}/"),
        _item("short-cache-time", f"https://{fqdn}/about", seconds=3600),
        _item("miss-persistent", f"https://{fqdn}/js/app.js", kind="asset"),
        _item("invalid-cert", f"https://{fqdn}/img/logo.png", kind="asset"),
    ]


def _build(psh, *, umich):
    notices = _notices_module(psh)
    return notices.build_cache_notices(
        SITE,
        {"www.example.edu": _representative_items("www.example.edu"),
         "www2.example.edu": _representative_items("www2.example.edu")},
        umich=umich, doc_url=DOC, framework="wordpress",
        sample_by_fqdn={"www.example.edu": {"pages": 3, "asset_pages": 3},
                        "www2.example.edu": {"pages": 3, "asset_pages": 3}})


@pytest.mark.parametrize("umich", [True, False], ids=["umich", "generic"])
def test_notice_message_and_text_snapshot(psh, reset_sc, snapshot, umich):
    out = _build(psh, umich=umich)
    assert len(out) == 1  # both FQDNs consolidated
    ctx = reset_sc.SiteContext({"name": SITE})
    ctx.add_notice(dict(out[0]))
    notice = ctx["notices"][0]
    assert notice["icon"]  # add_notice filled in the warning icon
    assert notice["message"] == snapshot
    assert notice["text"] == snapshot  # html2text plaintext derived from the HTML


def test_notice_renders_through_the_real_template(psh, reset_sc):
    out = _build(psh, umich=True)
    ctx = reset_sc.SiteContext({"name": SITE})
    ctx.add_notice(dict(out[0]))
    from jinja2 import Template
    template = Template((Path(psh.__file__).parent / "email_template.html").read_text())
    html_body = template.render(site_name=SITE, notices=ctx["notices"], sections=[],
                                news=[])
    assert "Cloudflare caching:" in html_body
    assert "www.example.edu" in html_body and "www2.example.edu" in html_body
    assert f"{DOC}#set-cookie-bypass" in html_body


def test_injection_via_remote_strings_is_escaped_everywhere(psh, reset_sc):
    notices = _notices_module(psh)
    evil = 'https://a.example.edu/"><script>alert(1)</script>'
    out = notices.build_cache_notices(
        SITE, {"a.example.edu": [_item("request-failed", evil,
                                       reason="<script>alert(2)</script>")]},
        umich=False, doc_url=DOC, framework="",
        sample_by_fqdn={"a.example.edu": {"pages": 3, "asset_pages": 3}})
    message = out[0]["message"]
    assert "<script>" not in message
    assert "alert(2)" not in message or "&lt;script&gt;" in message

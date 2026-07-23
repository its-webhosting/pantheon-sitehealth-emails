# Campaign I12 Implementation Plan — `psh/render.py` + `psh/mail.py` + annual billing → `check/umich/`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Implementers dispatch as `psh-implementer`, reviewers as `psh-reviewer`
> (`prompts/implementation-standards.md`). TDD skill override: `mattpocock-skills:tdd`.

**Goal:** Move B49–B57 (minus the sort/subject core and the send block) out of `main()`
into `psh/render.py` and `psh/mail.py`, and relocate the two annual-billing notices to
`check/umich/` as `site_pre_render` hooks — goldens byte-identical.

**Architecture:** Verbatim moves (Invariant 8) with the SPEC's named substitutions;
billing becomes hook-produced keys (`annual_bill_upcoming`/`annual_bill_in_progress`)
read by a new pure helper `sort_notices_and_subject` in `psh/_legacy.py`. See
`development/2026-07-23-mod-I12-render-mail/SPEC.md` — the spec governs; this plan
sequences it.

**Tech Stack:** Python 3.12, jinja2, PHP Emogrifier (subprocess), smtplib, pytest.

## Global Constraints

- **Line numbers below are against commit `786822b`** (the spec commit). Verify each
  range's content before cutting; if drifted, re-anchor by content, never blind-cut.
- Four e2e goldens NEVER change (`git diff 786822b -- tests/e2e/__snapshots__/` empty).
- Moved bodies are byte-verbatim except the substitutions each task names (exhaustive).
  Evidence: paste the extracted-block diff (old region vs new body) in the task report.
- New files born gated: `uvx ruff check --config ruff-broad.toml <file>` clean + pyright
  gate clean (`./run-tests` runs both). Measure findings, dispose per I2–I11 precedent
  (noqa **with inline reason** for verbatim-move bulk rules; behavior-identical trivial
  rewrites otherwise), list every disposition in the task report.
- Tests test-first at the seams SPEC §4 declares; watch each fail for the right reason.
- `./run-tests --fast` green before every commit (baseline 994 passed / 1 skipped /
  2 deselected, 107 snapshots). Conventional commits ending with the
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` trailer.
- No new `sc` names except `sc.contract_year_end` (Task 3). No config keys. No contract
  registry changes.

---

### Task 1: `psh/render.py` — `escape_url` + `render_report`, gather bridge consolidation

**Files:**
- Create: `psh/render.py`
- Create: `tests/integration/test_render_report.py`
- Modify: `psh/_legacy.py` (delete `escape_url` def at 176–177; delete B53-render/B54
  region 1597–1635; add re-imports; remove orphaned imports `urllib.parse`, `subprocess`,
  `jinja2.Template`)
- Modify: `psh/gather.py` (three call-time `escape_url` bridges → one module-level import)
- Modify: `tests/unit/test_house_rules.py:112–115` (comment only: the inliner's home)

**Interfaces:**
- Produces: `psh.render.escape_url(url: str) -> str`;
  `psh.render.render_report(site_name: str, template_dict: dict) -> tuple[str, str]`
  (returns `(html_body, text_body)`, `html_body` = the `-inline2.html` content).
  `psh._legacy` re-imports both, so `psh.escape_url` and `sc.escape_url` still resolve.
- Consumes: nothing from other tasks.

- [ ] **Step 1: Write the failing tests** — `tests/integration/test_render_report.py`:

```python
"""psh.render.render_report: Jinja -> build files -> php inline -> !important pass (campaign I12).

The e2e goldens prove byte-identity of the whole pipeline through main(); this file pins the
function's own I/O contract at its seam (SPEC I12 §4).  Uses the real php inliner, like
tests/integration/test_css_inliner_encoding.py (skip when php is absent).
"""
import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# A style block whose declaration lacks !important, so the B54 regex pass must add it,
# plus one Jinja placeholder per body so rendering is proven.
HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<style>p { color: red; }</style></head>
<body><p>{{ site_name }}</p></body></html>
"""
TXT_TEMPLATE = "report for {{ site_name }}\n"


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    if shutil.which("php") is None:
        pytest.skip("php not on PATH")
    (tmp_path / "email_template.html").write_text(HTML_TEMPLATE, encoding="utf-8")
    (tmp_path / "email_template.txt").write_text(TXT_TEMPLATE, encoding="utf-8")
    for asset in ("inline-styles.php", "vendor"):
        (tmp_path / asset).symlink_to(REPO_ROOT / asset)
    (tmp_path / "build").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_render_report_writes_all_four_build_files(workdir):
    import psh.render
    psh.render.render_report("testsite", {"site_name": "testsite"})
    for name in ("testsite.html", "testsite.txt", "testsite-inline.html", "testsite-inline2.html"):
        assert (workdir / "build" / name).exists(), name


def test_render_report_returns_inline2_html_and_rendered_text(workdir):
    import psh.render
    html_body, text_body = psh.render.render_report("testsite", {"site_name": "testsite"})
    assert html_body == (workdir / "build" / "testsite-inline2.html").read_text(encoding="utf-8")
    assert text_body == "report for testsite\n"
    assert "testsite" in html_body


def test_render_report_appends_important_to_inlined_css(workdir):
    import psh.render
    html_body, _ = psh.render.render_report("testsite", {"site_name": "testsite"})
    # Emogrifier inlines p{color:red} onto the <p>; the retained <style> block (if any)
    # gets !important appended to declarations that lack it.  The observable contract:
    # no "<style>" declaration in the returned body ends bare when it ended bare in the
    # template -- assert on the file the regex pass actually rewrites.
    inline1 = (workdir / "build" / "testsite-inline.html").read_text(encoding="utf-8")
    if "<style" in inline1 and "color: red;" in inline1:
        assert "color: red !important;" in html_body
```

- [ ] **Step 2: Run to verify failure**: `python -m pytest tests/integration/test_render_report.py -v`
  → FAIL/ERROR: `ModuleNotFoundError: No module named 'psh.render'` (right reason).

- [ ] **Step 3: Create `psh/render.py`.** Module docstring notes the campaign move + that
  a php failure raises `CalledProcessError` into `main()`'s abort path (unchanged).
  Contents (bodies verbatim from `psh/_legacy.py` — `escape_url` 176–177, render region
  1597–1635 — with EXACTLY these substitutions: `site["name"]`/`site['name']` →
  `site_name`; the `html_template`/`text_body` locals become function-scoped; a `return
  html_body, text_body` tail is added; real annotations per §6):

```python
"""Per-site report rendering (campaign I12, from main()'s B53/B54 regions).

escape_url lives here so psh/, check/ (via sc.escape_url), and the notice builders share
one URL-escaping rule.  render_report is CWD-relative (templates, inline-styles.php,
build/) like the rest of the program; a php inliner failure raises
subprocess.CalledProcessError into main()'s except-BaseException abort path, exactly as
the inline original did.
"""
import re
import subprocess
import sys
import urllib.parse

from jinja2 import Template


def escape_url(url: str) -> str:
    return urllib.parse.quote(url, safe=":/?#&=", encoding="utf-8", errors="strict")


def render_report(site_name: str, template_dict: dict) -> tuple[str, str]:
    """Render build/{site}.html/.txt, inline CSS via php, add !important; return bodies.

    Returns (html_body, text_body): html_body is the build/{site}-inline2.html content --
    the HTML actually attached to the message (CLAUDE.md § Rendering); text_body is the
    rendered text template.
    """
    ...  # lines 1597-1635 verbatim, substitutions above; keep every comment byte-for-byte
```

  (The `...` is the verbatim cut — do not retype it; cut/paste from `_legacy.py` and
  apply only the named substitutions. Paste the extract diff in the report.)

- [ ] **Step 4: Rewire `psh/_legacy.py`.** Delete the `escape_url` def (176–177) and the
  1597–1635 region; in the B53 position insert:

```python
            html_body, text_body = render_report(site["name"], template_dict)
```

  Add to the import block (after the `psh.plans` import group, matching style):

```python
from psh.render import escape_url, render_report
```

  Remove now-orphaned imports — grep-verify each is otherwise unused first (I3 rule):
  `urllib.parse` (line 26), `subprocess` (line 22), `from jinja2 import Template`
  (line 33). `re` stays (`fqdn_re`, line 42). The `sc.escape_url = escape_url` exposure
  line (340) stays — it now re-exports the render binding.

- [ ] **Step 5: Consolidate the gather bridges.** In `psh/gather.py` delete the three
  call-time bridge pairs (comment + import at 74–76, 147–149, 356–358 — each reads
  `# Cycle: _legacy imports this module.  escape_url moves to psh.render at I12` /
  `from psh._legacy import escape_url  # noqa: PLC0415`) and add at module level with
  the other imports:

```python
from psh.render import escape_url
```

- [ ] **Step 6: Update the house-rule comment.** `tests/unit/test_house_rules.py:114`
  says the PHP CSS inliner lives in `psh/_legacy.py` — change to `psh/render.py`
  (comment only; `POPEN_SCOPE`/`POPEN_ALLOWLIST` unchanged — `subprocess.run` is not
  `Popen`).

- [ ] **Step 7: Gates.** Run and paste:
  `python -m pytest tests/integration/test_render_report.py tests/integration/test_css_inliner_encoding.py tests/integration/test_gather_wordpress.py tests/integration/test_gather_drupal.py -v` → PASS;
  `uvx ruff check --config ruff-broad.toml psh/render.py psh/gather.py` → clean after
  dispositions (predicted: S603/S607 noqa with reason on the php call; possibly UP015/
  PTH123 — dispose per precedent, record);
  `./run-tests --fast` → 994+3 passed, goldens unchanged.

- [ ] **Step 8: Commit** — `feat(campaign-I12): move escape_url and the render pipeline into psh/render.py`

---

### Task 2: `psh/mail.py` — `smtp_login`, `resolve_recipients`, `assemble_message`

**Files:**
- Create: `psh/mail.py`
- Create: `tests/integration/test_mail_recipients.py`
- Modify: `psh/_legacy.py` (delete `smtp_login` 266–279, B49 1486–1504, B55 1637–1698;
  add re-imports + call sites; remove orphaned imports `EmailMessage`,
  `email.policy.SMTP`, `SMTP_SSL`)
- Modify: `tests/integration/test_email_config.py` (SMTP seam repoint)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `psh.mail.smtp_login() -> SMTP_SSL`;
  `psh.mail.resolve_recipients(site: dict, site_id: str) -> tuple[str, str] | None`
  (`(recipients, contacts)`; `None` after printing the fatal team-fetch error);
  `psh.mail.assemble_message(subject, recipients, text_body, html_body, wordmark_image,
  chart_image, banner_cid, chart_cid, attachments, site_name, end_date) -> EmailMessage`
  (also writes `build/{site_name}.eml`). `psh._legacy` re-imports all three.

- [ ] **Step 1: Write the failing tests** — `tests/integration/test_mail_recipients.py`:

```python
"""psh.mail.resolve_recipients: the B49 recipient/contact resolution (campaign I12).

Seam: psh.gateway.run_terminus via the gateway fixture (generic branch); sc.config via
reset_sc (U-M branch).  The fatal-fetch path returns None (main() continues) -- the
D-i6-1 return-value pattern.
"""
import json

import pytest

from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration


def _site(name):
    return {"name": name}


def _umich_config(owner_group):
    return {"UMich": {"enabled": True, "portal": {"sites": {
        "its-wws-test1": {"owner_group": owner_group}}}}}


def test_umich_recipients_owner_group_and_owners_alias(psh, reset_sc):
    import psh.mail
    reset_sc.config = _umich_config("web team")
    got = psh.mail.resolve_recipients(_site("its-wws-test1"), "SITE_ID")
    assert got == ("web.team@umich.edu, web.team-owners@umich.edu", "web.team@umich.edu")


def test_umich_special_case_sites_get_single_recipient(psh, reset_sc):
    import psh.mail
    reset_sc.config = {"UMich": {"enabled": True, "portal": {"sites": {
        "lsa-disko-project": {"owner_group": "disko group"}}}}}
    got = psh.mail.resolve_recipients(_site("lsa-disko-project"), "SITE_ID")
    assert got == ("disko.group@umich.edu", "disko.group@umich.edu")


def test_generic_recipients_from_site_team_list(psh, reset_sc, gateway, monkeypatch):
    import psh.mail
    reset_sc.config = {}
    team = {"m1": {"email": "a@example.edu"}, "m2": {"email": "b@example.edu"}}
    monkeypatch.setattr(gateway, "run_terminus",
                        lambda *a, **k: (json.dumps(team), "", False))
    got = psh.mail.resolve_recipients(_site("s"), "SITE_ID")
    assert got == ("a@example.edu, b@example.edu", "a@example.edu b@example.edu")


def test_generic_fatal_team_fetch_returns_none_and_prints(psh, reset_sc, gateway, monkeypatch):
    import psh.mail
    reset_sc.config = {}
    console = recording_console(monkeypatch, reset_sc)
    monkeypatch.setattr(gateway, "run_terminus",
                        lambda *a, **k: ("", "boom", True))
    assert psh.mail.resolve_recipients(_site("s"), "SITE_ID") is None
    assert "could not fetch team for s" in console.export_text()
```

- [ ] **Step 2: Run to verify failure**: `python -m pytest tests/integration/test_mail_recipients.py -v`
  → `ModuleNotFoundError: No module named 'psh.mail'`.

- [ ] **Step 3: Create `psh/mail.py`.** Docstring notes the campaign move and that the
  B57 send block deliberately stays in `main()` (SPEC D-i12-4: its accumulator writes sit
  between `send_message()` and `quit()`; hoisting them would reopen the documented
  Ctrl-C duplicate-email window — Invariant 4). Imports: `datetime`, `sys`,
  `email.message.EmailMessage`, `email.policy.SMTP`, `smtplib.SMTP_SSL`,
  `rich.markup.escape`, `script_context as sc`, `from psh.configuration import
  umich_enabled`, `from psh.gateway import terminus`. Bodies verbatim from `_legacy.py`
  (`smtp_login` 266–279 unchanged; B49 1486–1504 with substitutions: `site_name` →
  `site["name"]`, the `continue` → `return None`, tail `return recipients, contacts`;
  B55 1637–1698 with substitutions: `site["name"]`/`site['name']` → `site_name`,
  `site_context["attachments"]` → `attachments`, `sc.options.for_real` reads unchanged,
  tail `return msg`). Real annotations per §6. Paste the extract diffs in the report.

- [ ] **Step 4: Rewire `psh/_legacy.py`.** Import block addition:

```python
from psh.mail import assemble_message, resolve_recipients, smtp_login
```

  B49 position (1486–1504) becomes:

```python
            resolved = resolve_recipients(site, site_id)
            if resolved is None:
                continue
            recipients, contacts = resolved
```

  B55 position (1637–1698) becomes:

```python
            msg = assemble_message(
                subject, recipients, text_body, html_body, wordmark_image, chart_image,
                banner_cid, chart_cid, site_context["attachments"], site["name"], end_date,
            )
```

  The B57 send block (1711–1717) stays byte-identical (it calls the re-imported
  `smtp_login`). Remove orphaned imports after grep-verify: `from email.message import
  EmailMessage`, `from email.policy import SMTP`, `from smtplib import SMTP_SSL`.
  `make_msgid` and `datetime` stay (CIDs / other users).

- [ ] **Step 5: Repoint the SMTP seam** in `tests/integration/test_email_config.py`: every
  `monkeypatch.setattr(psh, "SMTP_SSL", …)` becomes `monkeypatch.setattr(psh.mail,
  "SMTP_SSL", …)` (add `import psh.mail` at module top). Reason in a one-line comment:
  after I12 `smtp_login` resolves `SMTP_SSL` in `psh.mail`'s namespace — patching the
  remnant's binding would silently not intercept (the I2/I10 two-binding lesson).
  Calls may stay `psh.smtp_login(...)` (re-imported) — do not weaken any assertion.

- [ ] **Step 6: Gates.** Run and paste:
  `python -m pytest tests/integration/test_mail_recipients.py tests/integration/test_email_config.py tests/integration/test_mime_structure.py tests/e2e/test_eml_headers.py -v` → PASS;
  `uvx ruff check --config ruff-broad.toml psh/mail.py` → clean after dispositions
  (predicted: PLR0913 noqa on `assemble_message`, pinned-signature precedent);
  `./run-tests --fast` → green, goldens unchanged.

- [ ] **Step 7: Commit** — `feat(campaign-I12): move recipients, MIME assembly, and smtp_login into psh/mail.py`

---

### Task 3: annual billing → `check/umich/annual_billing.py` + `sort_notices_and_subject`

**Files:**
- Create: `check/umich/annual_billing.py`
- Create: `tests/integration/test_check_umich_annual_billing.py`
- Create: `tests/integration/test_sort_notices_and_subject.py`
- Modify: `check/umich/__init__.py` (two `site_pre_render` registrations)
- Modify: `psh/_legacy.py` (delete builders 855–948 and the billing/sort/subject inline
  region; add the pure helper + `sc.contract_year_end` façade line; rewire `main()`)
- Modify: `tests/unit/test_annual_billing_notices.py` (repoint to the relocated builders)
- Modify: `tests/unit/test_house_rules.py` (`SC_FACADE_NAMES` += `"contract_year_end"`)

**Interfaces:**
- Consumes: nothing from Tasks 1–2 (touches a disjoint `main()` region — but run after
  Task 2 so the region's line numbers are re-anchored once).
- Produces: hook-produced `site_context` keys `annual_bill_upcoming` /
  `annual_bill_in_progress` (legacy notice dicts, absent unless produced);
  `psh.sort_notices_and_subject(site_context, report) -> tuple[list, str]`;
  `sc.contract_year_end`.

- [ ] **Step 1: Write the failing hook tests** —
  `tests/integration/test_check_umich_annual_billing.py`:

```python
"""check/umich annual-billing hooks (campaign I12, from B50/B51).

The two billing notices are HOOK-PRODUCED site_context keys (CAMPAIGN.md §4, the I10
drupal_multisite precedent), NOT add_notice calls: main()'s sort_notices_and_subject pins
them to the front of the *rendered* list and they never enter site_context["notices"] --
so no -notices.csv rows, the pre-campaign behavior (SPEC I12 §2.2).  This file is the
runtime cover LEDGER I1 required for the previously-untested umich-only call sites.
"""
import datetime

import pytest

from helpers.checkload import load_check_module, load_check_package
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration

SITE = "its-wws-test1"

CONFIG = {
    "UMich": {"enabled": True, "portal": {"sites": {
        SITE: {"shortcode": "SC123", "id": 42, "owner_group": "web team"}}}},
    "Pantheon": {"plan_info": {"Performance Small": {"cost": 500}}},
}


@pytest.fixture
def billing(psh, request):
    return load_check_module(psh, "umich", "annual_billing", "umich_billing_probe", request)


def _ctx(reset_sc, *, end_date):
    ctx = reset_sc.SiteContext({"name": SITE, "plan_name": "Performance Small"})
    ctx["end_date"] = end_date
    ctx["current_plan"] = "Performance Small"
    return ctx


def _wire_facade(psh, monkeypatch, reset_sc):
    # reset_sc does not restore runtime-exposed sc callables; monkeypatch, never assign
    # (the recorded reset_sc escape_url lesson).
    monkeypatch.setattr(reset_sc, "contract_year_end", psh.contract_year_end, raising=False)


# --- registration ------------------------------------------------------------------

def test_umich_enabled_registers_both_billing_hooks_in_block_order(psh, reset_sc, request):
    reset_sc.config = {"UMich": {"enabled": True}}
    load_check_package(psh, "umich", "umich_billing_reg_probe", request)
    names = [h["name"] for h in reset_sc.hooks["site_pre_render"]]
    assert names == [
        "check.umich.annual_billing.check_annual_bill_upcoming",
        "check.umich.annual_billing.check_annual_bill_in_progress",
    ]


def test_billing_declarations(psh, reset_sc, request):
    reset_sc.config = {"UMich": {"enabled": True}}
    load_check_package(psh, "umich", "umich_billing_decl_probe", request)
    hooks = {h["name"]: h for h in reset_sc.hooks["site_pre_render"]}
    up = hooks["check.umich.annual_billing.check_annual_bill_upcoming"]
    ip = hooks["check.umich.annual_billing.check_annual_bill_in_progress"]
    assert up["consumes"] == ["end_date", "current_plan"] and up["produces"] == ["annual_bill_upcoming"]
    assert ip["consumes"] == ["current_plan"] and ip["produces"] == ["annual_bill_in_progress"]


def test_umich_disabled_registers_no_billing_hooks(psh, reset_sc, request, monkeypatch):
    recording_console(monkeypatch, reset_sc)
    reset_sc.config = {"UMich": {"enabled": False}}
    load_check_package(psh, "umich", "umich_billing_reg_off_probe", request)
    assert not reset_sc.hooks.get("site_pre_render")


# --- upcoming (B50 window) ---------------------------------------------------------

@pytest.mark.parametrize("day,expected", [(15, False), (16, True), (29, True), (30, False)])
def test_upcoming_produced_only_inside_contract_year_end_window(
        psh, reset_sc, billing, monkeypatch, day, expected):
    reset_sc.config = CONFIG
    _wire_facade(psh, monkeypatch, reset_sc)
    ctx = _ctx(reset_sc, end_date=datetime.date(2026, 6, day))
    billing.check_annual_bill_upcoming(ctx)
    assert ("annual_bill_upcoming" in ctx) is expected


def test_upcoming_notice_content_comes_from_config(psh, reset_sc, billing, monkeypatch):
    reset_sc.config = CONFIG
    _wire_facade(psh, monkeypatch, reset_sc)
    ctx = _ctx(reset_sc, end_date=datetime.date(2026, 6, 20))
    billing.check_annual_bill_upcoming(ctx)
    n = ctx["annual_bill_upcoming"]
    assert n["csv"] == f"{SITE},annual-bill,500.0,SC123"
    assert "/sites/42/plan/" in n["message"]
    assert ctx["notices"] == []          # produced key, never a notice (SPEC §2.2)


# --- in progress (B51) -------------------------------------------------------------

def test_in_progress_always_produced_when_hook_runs(psh, reset_sc, billing, monkeypatch):
    reset_sc.config = CONFIG
    _wire_facade(psh, monkeypatch, reset_sc)
    ctx = _ctx(reset_sc, end_date=datetime.date(2026, 3, 31))
    billing.check_annual_bill_in_progress(ctx)
    n = ctx["annual_bill_in_progress"]
    assert n["csv"] == f"{SITE},annual-bill-in-progress,500.0,SC123"
    assert ctx["notices"] == []
```

- [ ] **Step 2: Write the failing helper tests** —
  `tests/integration/test_sort_notices_and_subject.py`:

```python
"""psh.sort_notices_and_subject: B50's sort/subject core + billing-key wiring (campaign I12).

This pure helper is the runtime seam for the previously-untested umich-only billing call
sites (LEDGER I1 obligation).  Pins the preserved quirks: the in-progress notice renders
first but NEVER influences the subject (it is inserted after the subject computation),
and billing dicts never enter site_context["notices"].
"""
import pytest

pytestmark = pytest.mark.integration

REPORT = "Pantheon Traffic Report, Mar 31, 2026"


def _notice(ntype, short="s"):
    return {"type": ntype, "short": short, "csv": f"x,{ntype}"}


def _ctx(reset_sc, notices=(), **keys):
    ctx = reset_sc.SiteContext({"name": "mysite"})
    for n in notices:
        ctx["notices"].append(n)
    for k, v in keys.items():
        ctx[k] = v
    return ctx


def test_default_subject_and_empty_notices(psh, reset_sc):
    sorted_notices, subject = psh.sort_notices_and_subject(_ctx(reset_sc), REPORT)
    assert sorted_notices == [] and subject == f"mysite: {REPORT}"


def test_sorts_alert_warning_info_and_prefixes_action_required(psh, reset_sc):
    ns = [_notice("info"), _notice("alert", "bad"), _notice("warning")]
    ctx = _ctx(reset_sc, notices=ns)
    sorted_notices, subject = psh.sort_notices_and_subject(ctx, REPORT)
    assert [n["type"] for n in sorted_notices] == ["alert", "warning", "info"]
    assert subject == f"Action Required: mysite: bad | {REPORT}"


def test_warning_first_prefixes_action_recommended(psh, reset_sc):
    ctx = _ctx(reset_sc, notices=[_notice("warning", "meh")])
    _, subject = psh.sort_notices_and_subject(ctx, REPORT)
    assert subject == f"Action Recommended: mysite: meh | {REPORT}"


def test_info_only_keeps_default_subject(psh, reset_sc):
    ctx = _ctx(reset_sc, notices=[_notice("info")])
    _, subject = psh.sort_notices_and_subject(ctx, REPORT)
    assert subject == f"mysite: {REPORT}"


def test_upcoming_key_overrides_subject_and_leads(psh, reset_sc):
    up = {"type": "alert", "short": "bill", "csv": "x,annual-bill"}
    ctx = _ctx(reset_sc, notices=[_notice("alert", "other")], annual_bill_upcoming=up)
    sorted_notices, subject = psh.sort_notices_and_subject(ctx, REPORT)
    assert subject == "Time Sensitive: mysite annual billing"
    assert sorted_notices[0] is up


def test_in_progress_key_leads_but_never_touches_subject(psh, reset_sc):
    ip = {"type": "alert", "short": "billing", "csv": "x,annual-bill-in-progress"}
    ctx = _ctx(reset_sc, notices=[_notice("warning", "meh")], annual_bill_in_progress=ip)
    sorted_notices, subject = psh.sort_notices_and_subject(ctx, REPORT)
    assert sorted_notices[0] is ip
    assert subject == f"Action Recommended: mysite: meh | {REPORT}"   # the preserved quirk


def test_both_keys_render_in_progress_first_then_upcoming(psh, reset_sc):
    up = {"type": "alert", "short": "u", "csv": "x,annual-bill"}
    ip = {"type": "alert", "short": "i", "csv": "x,annual-bill-in-progress"}
    ctx = _ctx(reset_sc, annual_bill_upcoming=up, annual_bill_in_progress=ip)
    sorted_notices, subject = psh.sort_notices_and_subject(ctx, REPORT)
    assert sorted_notices[0] is ip and sorted_notices[1] is up
    assert subject == "Time Sensitive: mysite annual billing"


def test_helper_does_not_mutate_site_context_notices(psh, reset_sc):
    ip = {"type": "alert", "short": "i", "csv": "x,annual-bill-in-progress"}
    ctx = _ctx(reset_sc, notices=[_notice("info")], annual_bill_in_progress=ip)
    psh.sort_notices_and_subject(ctx, REPORT)
    assert ctx["notices"] == [_notice("info")]   # billing keys never join the csv source
```

- [ ] **Step 3: Run both to verify failure** (right reasons: no
  `check/umich/annual_billing.py`; `AttributeError: … no attribute
  'sort_notices_and_subject'`).

- [ ] **Step 4: Create `check/umich/annual_billing.py`.** Module docstring per SPEC §2.2
  (produced keys, why not add_notice, csv-absence is deliberate). Move both builders
  (`_legacy.py` 855–948) byte-verbatim (their docstring block-references stay accurate).
  Then:

```python
def _billing_inputs(site_context) -> tuple[dict, str, float]:
    site = site_context["site"]
    portal_site = sc.config["UMich"]["portal"]["sites"][site["name"]]
    annual_bill = float(sc.config["Pantheon"]["plan_info"][site_context["current_plan"]]["cost"])
    return site, portal_site, annual_bill


def check_annual_bill_upcoming(site_context) -> None:
    """B50's billing half: the June-window "will be billed July 1" alert, as a produced key."""
    if not sc.contract_year_end(site_context["end_date"]):
        return
    site, portal_site, annual_bill = _billing_inputs(site_context)
    site_context["annual_bill_upcoming"] = build_annual_bill_upcoming_notice(
        site["name"], site["plan_name"], annual_bill, portal_site["shortcode"], portal_site["id"]
    )


# TODO: remove this check at the beginning of August 2026 (BLOCKMAP B51; I14 re-evaluates).
def check_annual_bill_in_progress(site_context) -> None:
    """B51: the "ITS is in the process of billing" alert, as a produced key."""
    site, portal_site, annual_bill = _billing_inputs(site_context)
    site_context["annual_bill_in_progress"] = build_annual_bill_in_progress_notice(
        site["name"], site["plan_name"], annual_bill, portal_site["shortcode"]
    )
```

  Register in `check/umich/__init__.py` inside the existing guard, after the
  `drupal_ua` registration (upcoming then in_progress — B50-before-B51 block order):

```python
    from .annual_billing import check_annual_bill_in_progress, check_annual_bill_upcoming
    sc.add_hook('site_pre_render', {'name': 'check.umich.annual_billing.check_annual_bill_upcoming',
                                    'func': check_annual_bill_upcoming,
                                    'consumes': ['end_date', 'current_plan'],
                                    'produces': ['annual_bill_upcoming']})
    sc.add_hook('site_pre_render', {'name': 'check.umich.annual_billing.check_annual_bill_in_progress',
                                    'func': check_annual_bill_in_progress,
                                    'consumes': ['current_plan'],
                                    'produces': ['annual_bill_in_progress']})
```

  (Import line joins the existing relative-import block at the top of the guard.)

- [ ] **Step 5: Rewire `psh/_legacy.py`.**
  1. Delete the two builders (855–948).
  2. Add the façade line at the end of the exposure block (~349):
     `sc.contract_year_end = contract_year_end  # check packages: U-M billing-window test (check/umich annual_billing)`
  3. Add the pure helper `sort_notices_and_subject(site_context, report)` as a
     module-level def near `no_primary_domain_notice` (same precedent, final home I13),
     body = SPEC §2.3's code verbatim (sort lines 1507–1511, subject line, billing-key
     `.get()` wiring, elif chain, in-progress insert; f-strings byte-identical with
     `site['name']` → the `site_name` local).
  4. In `main()`: delete the inline region 1506–1546 (sort, subject, both billing
     branches); after `sc.invoke_hooks("site_pre_render", site_context)` insert:

```python
            # Sort + subject AFTER the phase (campaign I12): hooks that add notices now
            # render, and the billing hooks' produced keys are wired in by the helper.
            report = f"Pantheon Traffic Report, {end_date.strftime('%b %e, %Y')}"
            sorted_notices, subject = sort_notices_and_subject(site_context, report)
```

     (`report` keeps its exact f-string; `end_of_contract_year` stays where it is —
     `template_dict` still reads it.)

- [ ] **Step 6: Repoint `tests/unit/test_annual_billing_notices.py`** to the relocated
  builders (I8 `php_eol` precedent — no `_legacy` re-import exists for them):

```python
from helpers.checkload import load_check_module

@pytest.fixture
def billing(psh, request):
    return load_check_module(psh, "umich", "annual_billing", "umich_billing_unit_probe", request)
```

  and `_upcoming(psh)`/`_in_progress(psh)` become `_upcoming(billing)` etc. calling
  `billing.build_annual_bill_*`. No assertion changes.

- [ ] **Step 7: Façade pin.** `tests/unit/test_house_rules.py` `SC_FACADE_NAMES` +=
  `"contract_year_end"`. RED demonstration per that file's convention: comment out the
  new façade line in `_legacy.py`, watch the test fail naming it, restore, record in the
  task report.

- [ ] **Step 8: Gates.** Run and paste:
  `python -m pytest tests/integration/test_check_umich_annual_billing.py tests/integration/test_sort_notices_and_subject.py tests/unit/test_annual_billing_notices.py tests/unit/test_house_rules.py tests/integration/test_hook_dag.py tests/integration/test_check_umich_wp.py -v` → PASS;
  `uvx ruff check --config ruff-broad.toml check/umich/annual_billing.py check/umich/__init__.py` → clean after dispositions;
  `./run-tests --fast` → green, goldens byte-identical
  (`git diff 786822b -- tests/e2e/__snapshots__/` empty).

- [ ] **Step 9: Commit** — `feat(campaign-I12): relocate annual billing to check/umich as site_pre_render hooks`

---

### Task 4: Closing — docs, ledger, memory, acceptance

**Files:**
- Modify: `CLAUDE.md`, `development/2026-07-17-modularization-campaign/LEDGER.md`,
  `development/2026-07-23-mod-I12-render-mail/SPEC.md` (§9 acceptance paste),
  memory files.

- [ ] **Step 1: CLAUDE.md** — § Single-module core: add `psh/render.py` + `psh/mail.py`
  entries (function lists per SPEC §2.4/§2.5, the send-block-stays note, the
  helper's interim home) and update the `psh/gather.py` sentence about the
  `escape_url` bridge (now a module-level `from psh.render import escape_url`);
  § Rendering: repoint prose at the new functions; § check/umich list: add
  `annual_billing.py` (D-i12 produced-keys mechanism, B51's Aug-2026 marker);
  contract-table `site_pre_render` row: note the two hook-produced billing keys
  (`.get()`-read, the multisite precedent); still-hardcoded-U-M list: the
  annual-billing notices LEAVE it (relocated, U-M-gated — the drupal_ua precedent);
  § Testing: add the three new test files + the `psh.mail.SMTP_SSL` seam note;
  exposure-block list: add `sc.contract_year_end`. Delete prose that stood in for the
  moved logic; report the line delta.
- [ ] **Step 2: LEDGER.md** — append the I12 entry per CAMPAIGN §12 template: moves,
  D-i12-1…4 ledger notes, the produced-keys mechanism, the sort-after-phase seam
  improvement, B51 kept (date not passed — I14 re-evaluates), `Notice`-adoption
  re-deferred to I14, discovered tasks with dispositions, open questions for I13.
- [ ] **Step 3: Memory** — update `modularization-campaign` note (I12 done, I13 next);
  note the `psh.mail.SMTP_SSL` two-binding seam alongside the existing
  gateway-extraction note.
- [ ] **Step 4: Acceptance** — run full `./run-tests` (live tier if credentials
  present), paste results + golden diff + born-gated ruff/pyright output into SPEC §9.
- [ ] **Step 5: Commit** — `docs(campaign-I12): close the render+mail increment`, then
  `/archive-session` per the campaign flow.

---

## Self-review (run against SPEC)

- Spec coverage: §1 moves → Tasks 1–3; §2.2/2.3 → Task 3; §2.4 → Task 1; §2.5 → Task 2;
  §4 seam table → each test file above; §5 ratchet → per-task gate steps; §6
  decomposition honored; §7 acceptance → Task 4. Gaps: none.
- Type consistency: `render_report -> tuple[str, str]`, `resolve_recipients -> tuple[str,
  str] | None`, `assemble_message -> EmailMessage`, helper `-> tuple[list, str]` — used
  identically in every task.
- No placeholders except the two sanctioned verbatim-cut markers (`...` in Task 1 Step 3
  and the Task 2 Step 3 body list), which are deliberate: retyping byte-locked regions in
  a plan risks silent drift; the line ranges + named substitutions + extract-diff
  evidence requirement are the stronger contract (Invariant 8, the I2–I11 brief pattern).

# SPEC — I14c: retiring the `Notice` dict form

**Increment:** I14c (Wave 4, third of four). **Date:** 2026-07-24.
**Governing documents** (read in full before implementing; this spec cites them by section
and re-derives nothing): `development/2026-07-17-modularization-campaign/CAMPAIGN.md`
(frozen architecture), `LEDGER.md` (through the I14b entry and the `§6 Notice csv field set`
amendment appended at this spec's time), `/workspace/CLAUDE.md`,
`/workspace/prompts/directives.md` (the Spine; PD#n citations are to it).

**CAMPAIGN.md §11 row I14c, verbatim:** "`Notice` dict form retired: the reserved §6
csv-field amendment + every producer converted; artifacts byte-identical."

**Review record.** Adversarial spec review (fresh context, `psh-reviewer`) round 1 against
commit `982589f`: **APPROVE-WITH-FIXES**, 14 findings. All 14 are folded into this revision —
the corrections to the measured figures (§2.1, §2.4), the snapshot-impact analysis (§3), the
registry hazard's real escape (§2.3), the orphaned producer #14 (§6), the incomplete test
inventory (§5), the quote-blind close gate (§8), the two diagrams (below), and the two
instruments now written as runnable tools (§4). Every figure in this document is now produced
by `tools/notice_inventory.py`, not asserted.

## Glossary (this spec only; domain terms live in `CONTEXT.md`)

- **Producer** — a place in `psh/`, `check/` or `plugin/` that hands `add_notice` (or a
  hook-produced key) a **hand-built dict**. There are **37**, exhaustively listed in §2.4 and
  reproduced by `python development/2026-07-24-mod-I14c-notice/tools/notice_inventory.py`.
  They carry **35 distinct notice codes** (`not-installed` and `turned-off` each have a
  WordPress and a Drupal producer inside `psh/gather.py`).
- **Notice site** — any place a notice is constructed, dict-form or not. There are **38**: the
  37 producers plus `psh/cli.py:663`'s `no-domains`, which has been `Notice`-based since I3
  and is **not** converted by this increment. The **roster** is therefore **36 codes**.
- **Render dict** — the six-key `{type, icon, csv, short, message, text}` mapping stored in
  `site_context["notices"]`, read by `email_template.{html,txt}`
  (`notice.type|icon|message|text`), by `sort_notices_and_subject` (`["type"]`, `["short"]`)
  and by `RunState.record_site_notices` (`["csv"]`). **This form is NOT retired** (D-i14c-2).
- **Dict form** — a producer building a render dict by hand. This is what I14c retires.
- **Projection** — `SiteContext.notice_to_dict(notice)`: the one function turning a `Notice`
  into a render dict (§2.2).

MUST / NEVER / SHOULD / MAY per CAMPAIGN.md §Glossary.

## 0. The two flows this increment changes (PD#8)

Notice construction and consumption, before → after. `*` marks what I14c changes:

```
  BEFORE                                          AFTER
  producer builds render dict ──┐                 producer builds Notice ──┐          *
   {type,icon,csv,short,         │                  (severity, code,        │
    message,text}                │                   csv_extra, html, …)    │
                                 ▼                                          ▼
                    SiteContext.add_notice                     SiteContext.add_notice     *
                     · fills icon from type                     · TypeError unless Notice
                     · fills text via html2text                 · notice_to_dict(notice)  *
                     · order → front/back                         (icon/text/csv filled)
                                 │                                 · order → front/back
                                 ▼                                          ▼
                    site_context["notices"]  ── render dict list (UNCHANGED shape) ──┐
                                                                                     │
        ┌────────────────────────────┬───────────────────────────────────────────────┘
        ▼                            ▼                              ▼
  email_template.{html,txt}   sort_notices_and_subject     RunState.record_site_notices
  notice.type|icon|           ["type"], ["short"]          ["csv"] → {ymd}-notices.csv
  message|text                      ▲
                                    │  annual_bill_upcoming (hook-produced key):
                                    │  check/umich/annual_billing.py publishes
                                    └─ site_context.notice_to_dict(Notice)  ── never  *
                                       enters site_context["notices"], so never
                                       reaches -notices.csv (load-bearing, LEDGER I12)
```

Code registration and its test-time lifecycle (§2.3):

```
  import time (once per process in production; once per LOAD in tests)
        module body:  NOTICE_FROZEN = registry.register("frozen", description=…)
                                              │
                      second registration of the same code ──► DuplicateNoticeCodeError (fatal, loud)
                                              │
  ── tests ─────────────────────────────────  ▼  ────────────────────────────────────────
  reset_sc (autouse, FUNCTION scope)   snapshot() ──► test body loads check module ──► restore()
        ▲                                                                                │
        └──── the invariant that makes this work: every producing module is executed ─────┘
              INSIDE a function-scoped fixture or test body, never at module import
              of a test file and never in a module/session-scoped fixture.
```

## 1. Scope

### 1.1 In scope (exhaustive)

| # | Deliverable | Where |
|---|---|---|
| A | `Notice` gains `csv_extra: tuple[str, ...]` — the reserved CAMPAIGN.md §6 field-set amendment (deferred I3 → I7 → I10 → I12 → here) | `psh/notice.py` |
| B | The projection made public and complete: `SiteContext.notice_to_dict` | `script_context.py` |
| C | Import-time registration of all **36** roster codes (35 converted + `no-domains`, already registered) + the registry test-reset seam | producers, `psh/notice.py`, `tests/conftest.py` |
| D | All **37** producers converted to construct `Notice` | 20 files (§2.4) |
| E | The dict form retired: `add_notice` accepts **only** a `Notice` | `script_context.py` |
| F | Docs: CLAUDE.md notice sections, the CAMPAIGN.md §6 amendment (landed at spec time) + its correction (§2.1), ledger entry, memory | docs |

### 1.2 NOT in scope (reasoning preserved so it is not re-litigated)

- **News items** (`sc.add_news_item`, `sc.news`, the `[News.*]` TOML tables). News items are
  operator-authored data read from config, not code-built notices; they have no `csv`, no
  code, and no registry. `add_news_item` keeps its dict path unchanged.
- **`sections` / `attachments` dicts** — different shapes, different consumers, unrelated to §6.
- **Notice content, csv values, severities, ordering, or which notices exist.** I14c changes
  *representation only* (§3).
- **The render dict itself.** Replacing it with an object (so templates read attributes) would
  touch `email_template.{html,txt}` and every golden — outside CAMPAIGN.md §8's "rendered
  emails NEVER change" bar, and buying nothing this increment needs.
- **`no-domains`** (`psh/cli.py:663`) — already `Notice`-based since I3; untouched except that
  its `registry.register` call at `psh/cli.py:140` joins the roster test.
- **The three post-campaign README TODOs** (ruff upgrade + PLR0917, typed `sc` stubs + pyright
  widening, test repoint off the `psh.<name>` surface) — LEDGER I14b says explicitly they are
  not I14c/I14d scope.
- **`docs/config-migration.md`, the docs/README/CLAUDE.md wholesale refresh, the §17 closing
  audit** — I14d.

## 2. Design

### 2.1 Deliverable A — the `csv_extra` field (CAMPAIGN.md §6 amendment)

```python
@dataclasses.dataclass(frozen=True)
class Notice:
    severity: Severity
    code: str
    html: str
    short: str = ""
    text: str = ""
    icon: str = ""
    order: str = "append"
    csv_extra: tuple[str, ...] = ()   # NEW (I14c)
```

The projection builds the csv row as `",".join([site_name, code, *csv_extra])`. **28 of the
37** producers carry extra csv fields; 9 are the plain two-field form (measured by
`tools/notice_inventory.py`; the LEDGER amendment's "22 of the 37" is corrected to 28 — see
§7). Every current shape reproduces byte-for-byte:

| Current literal | `code` | `csv_extra` |
|---|---|---|
| `f"{site['name']},frozen"` | `"frozen"` | `()` |
| `f"{site['name']},no-primary-domain,"` | `"no-primary-domain"` | `("",)` — the trailing empty field is real and preserved |
| `f"{site},wp-error,{operation},{json.dumps(errors).replace(',', '\\,')}"` | `"wp-error"` | `(operation, json.dumps(errors).replace(",", "\\,"))` |
| `f"{site_name},not-in-dns," + ",".join(hostnames)` | `"not-in-dns"` | `tuple(hostnames)` — see the precondition below |
| `f"{site_name},cloudflare-cache,{'+'.join(fqdns)},{'+'.join(ids)}"` | `"cloudflare-cache"` | `("+".join(fqdns), "+".join(ids))` |
| `f"{site_name},its-recommends-plan,{current_plan},{recommended_plan},{savings:.2f}"` | `"its-recommends-plan"` | `(current_plan, recommended_plan, f"{savings:.2f}")` |

`csv_extra` is a **tuple**, not a list: `Notice` is `frozen=True` and a list field would make
it unhashable and mutably shared. Elements MUST already be strings — the projection does not
coerce, so a format spec (`f"{savings:.2f}"`, `str(num_updates)`) is the producer's job and
stays visible at the producer.

**Empty-input precondition (PD#3's zero-length shadow).** For the six join-shaped producers
(`check/dns/notices.py` ×5, `check/pantheon_cdn_change/notices.py`) today's expression is
`f"{site},{code}," + ",".join(xs)`, which yields a **trailing comma** when `xs == []`;
`csv_extra=tuple(xs)` yields no trailing comma. The two forms are therefore byte-identical
**iff `xs` is non-empty**, which every call site guarantees today
(`check/dns/hook.py:26,30,33,36,40` each gate on a non-empty list; `check/pantheon_cdn_change/
hook.py:50` returns early on `not findings`). MUST: state the precondition in each builder's
docstring and add one unit test per shape pinning the empty-input result, so the divergence is
**pinned rather than latent** — these builders are pure and directly unit-tested, so a future
caller could reach the empty case. The alternative (`csv_extra=(",".join(xs),)`, byte-identical
even when empty) is rejected: it models the whole hostname list as one opaque field, hiding the
structure the csv row actually has, to protect a branch no caller reaches.

**Why not the other shapes** (both rejected in the design round): a `csv_suffix: str` keeps the
comma-joining scattered across 28 producers and models nothing; a full `csv: str` override
re-admits the free-form string the type exists to retire and hands the site name back to
producers.

### 2.2 Deliverable B — the projection

Today `SiteContext._notice_to_dict` is private, builds only the two-field csv, and leaves
`icon`/`text` to `add_notice`'s fill logic. I14c makes it public and complete:

```python
    def notice_to_dict(self, notice: Notice) -> dict:
        """Project a Notice onto the render dict this site's report consumes."""
        return {
            "type": str(notice.severity),
            "icon": notice.icon or icon[notice.severity],
            "csv": ",".join([self["site"]["name"], notice.code, *notice.csv_extra]),
            "short": notice.short,
            "message": notice.html,
            "text": notice.text or html_to_text(notice.html),
        }

    def add_notice(self, notice: Notice) -> None:
        if not isinstance(notice, Notice):
            raise TypeError(...)                      # §2.6
        d = self.notice_to_dict(notice)
        if notice.order in ("prepend", "first"):
            self["notices"].insert(0, d)
        else:
            self["notices"].append(d)
```

Three consequences, each deliberate:

1. **The site name comes from the `SiteContext`, never from the producer.** Verified for all
   37 producers (spec review re-verified independently): every builder that takes a
   `site`/`site_name` parameter is called with the processed site's name — `psh/gather.py` ×7,
   `check/wordpress/ocp.py:29`, `check/wordpress/favicon.py:25`, `check/drupal/multisite.py:30`,
   `check/umich/drupal_ua.py:50,65`, `check/umich/cloudflare_cms.py:36`,
   `check/cloudflare/cache.py:276`, `check/pantheon_cdn_change/hook.py:37`,
   `check/pantheon/php_eol.py:75`, `check/umich/sitelens.py:88`, `psh/cli.py:874`. Those
   parameters stay: the builders' console messages use them.
2. **`order` is no longer stored in the render dict.** `add_notice` was its only reader (the
   other two `'order'` hits in the tree are `add_news_item`'s and the projection's), and no
   producer sets a non-default order today.
3. **`icon` and `text` are always present**, with the same values `add_notice` fills today. Key
   *order* within the dict changes. No consumer reads a notice dict positionally or serializes
   it, with **one observable exception**: `psh/cli.py:879`'s `sc.debug("===== Notices:\n",
   site_context["notices"])` pretty-prints the dicts at `-v`, in insertion order — so for the 8
   producers that omit `icon` today (5 in `check/dns/notices.py`, plus
   `check/cloudflare/notices.py:397`, `check/pantheon_cdn_change/notices.py:197`,
   `check/umich/sitelens.py:106`) that debug dump's key order changes. Sanctioned by
   CAMPAIGN.md §8 ("stdout / console / error messages MAY improve freely"); named here rather
   than claimed absent (PD#5).

### 2.3 Deliverable C — code registration and the test-reset seam

Each producing module registers its codes at import, through a module-level constant:

```python
NOTICE_FROZEN = registry.register("frozen", description="site frozen by Pantheon for inactivity")
...
    site_context.add_notice(Notice(severity=Severity.ALERT, code=NOTICE_FROZEN, ...))
```

A constant, not a bare `register(...)` call plus a literal at the construction site, so the
code used **cannot** drift from the code registered (PD#1). Registration is **per code, not per
producer**: `psh/gather.py` registers `not-installed` and `turned-off` **once** each even though
its WordPress and Drupal builders both emit them — registering twice is exactly the
`DuplicateNoticeCodeError` the registry exists to raise.

**The re-import hazard.** `NoticeRegistry.register` is import-time-once metadata, but the test
suite loads `check/` modules standalone under fresh probe names (`tests/helpers/checkload.py`,
and direct `SourceFileLoader`/`spec_from_file_location` in the cloudflare/dns/sitelens/plugin/
php_eol test files) — so a module body re-executes once per load and the second `register()` of
a given code raises. Fix, in three parts:

```python
class NoticeRegistry:
    def snapshot(self) -> dict[str, str]:   # test seam (tests/conftest.py reset_sc)
        return dict(self._codes)
    def restore(self, snapshot: dict[str, str]) -> None:
        self._codes = dict(snapshot)
```

1. The **autouse, function-scoped** `reset_sc` fixture saves/restores the registry around every
   test, alongside the `script_context` globals it already deep-copies.
2. **The invariant this depends on** (restated correctly after spec-review finding 2, whose
   original wording — "no test loads the same module twice in one function" — was blind to
   loads that happen *outside* a test): **no producing module may be executed outside a
   function-scoped fixture or test body.** A load at a test module's import time, or in a
   module/session-scoped fixture, happens **before** `reset_sc`'s snapshot, so `restore()`
   cannot undo it and the next load of that module raises. There is exactly **one** violation
   today, and Task 3 MUST fix it: `tests/unit/test_php_eol_notice.py:13-15` loads
   `check/pantheon/php_eol.py` (2 codes) at module level via `SourceFileLoader(...).load_module()`
   — move it into a function-scoped fixture, the pattern `tests/unit/test_annual_billing_notices.py:12`
   already uses. Without that fix, `tests/integration/test_check_pantheon.py:74`,
   `test_pantheon_notice_render.py:72` and the roster test itself would all error.
   The one module-scoped loader fixture in the suite (`tests/unit/test_cachecheck_headers.py:21`)
   loads `check/cloudflare/headers.py`, which produces no notices — it stays as is, and the
   rule above is what keeps that fact load-bearing rather than lucky.
3. **This hazard is fail-loud, not silent** (`DuplicateNoticeCodeError` at collection or test
   time, naming the code), so no permanent guard test is specified beyond the roster test —
   PD#1 is satisfied by the error itself.

**Roster test gating.** `check/umich/` and `check/cloudflare/` import their producing submodules
only inside their `enabled` guards, so the roster test (§4 I4) MUST load every package with
everything enabled — `tests/integration/test_hook_dag.py`'s existing all-enabled config and its
`ALL_PACKAGES` list are the mechanism.

Import-time registration is what makes the duplicate-code guard real: it is the bug class I1
fixed by hand twice (`php-eol`, `annual-bill`; CAMPAIGN.md §10) and the reason `NoticeRegistry`
was built at I3. It also answers §17 Q4 for this façade surface.

### 2.4 Deliverable D — the 37 producers (exhaustive)

Reproduce this table with `python development/2026-07-24-mod-I14c-notice/tools/notice_inventory.py`.
`icon` column: **default** = explicit and equal to `sc.icon[type]` (deleted by the conversion);
**derived** = no `icon` key today; **local map** = `check_drupal_module`'s variable;
**CUSTOM** = kept. `text`: own = the literal supplies it; derived = html2text fills it.

| # | Producer | severity | csv today | icon | text |
|---|---|---|---|---|---|
| 1 | `psh/cli.py:301` | info | `{site},no-primary-domain,` | default | own |
| 2 | `psh/gateway.py:218` | alert | `{site},wp-error,{operation},{json}` | default | own |
| 3 | `psh/gateway.py:300` | alert | `{site},drush-error,{operation},{json}` | default | own |
| 4 | `psh/gather.py:86` | warning | `{site},not-installed,{name}` | default | own |
| 5 | `psh/gather.py:102` | info | `{site},multiple-installed,{name}` | default | own |
| 6 | `psh/gather.py:122` | warning | `{site},turned-off,{name}` | default | own |
| 7 | `psh/gather.py:157` | `level` | `{site},not-installed,{name}` | local map | own |
| 8 | `psh/gather.py:174` | `level` | `{site},turned-off,{name}` | local map | own |
| 9 | `psh/gather.py:446` | alert | `{site},composer-update` | default | own |
| 10 | `psh/gather.py:581` | info | `{site},wp-smell,{json}` | default | own |
| 11 | `psh/gather.py:606` | info | `{site},drush-smell,{json}` | default | own |
| 12 | `psh/gather.py:631` | info | `{site},composer-smell,{json}` | default | own |
| 13 | `psh/plans.py:185` | info | `{site},its-recommends-plan,{cur},{rec},{savings:.2f}` | default | own |
| 14 | `check/addon_updates/table.py:66` | warning | `{site},updates-addons,{num}` | default | own |
| 15 | `check/cloudflare/notices.py:397` | info | `{site},cloudflare-cache,{fqdns},{ids}` | derived | derived |
| 16–20 | `check/dns/notices.py:25,42,77,113,123` | warning/alert | `{site},{code},` + `",".join(hostnames)` | derived | own |
| 21 | `check/drupal/d7_eol.py:13` | alert | `{site},drupal7-eol` | default | own |
| 22 | `check/pantheon/frozen.py:14` | alert | `{site},frozen` | default | own |
| 23 | `check/pantheon/live_env.py:16` | alert | `{site},no-live-env-but-paid-plan` | default | own |
| 24 | `check/pantheon/php_eol.py:12` | warning | `{site},php-eol-warning` | default | own |
| 25 | `check/pantheon/php_eol.py:39` | alert | `{site},php-eol-alert` | default | own |
| 26–28 | `check/pantheon/updates.py:59,93,129` | info/warning/alert | `{site},updates-{sev},{num},{days}` | default | own |
| 29 | `check/pantheon_cdn_change/notices.py:197` | info | `{site},pantheon-cdn-change,` + joined fqdns | derived | own |
| 30 | `check/umich/annual_billing.py:23` | alert | `{site},annual-bill,{amount},{shortcode}` | **CUSTOM 💵** | own |
| 31 | `check/umich/drupal_ua.py:79` | info | `{site},drupal-ua,{result}` | default | own |
| 32 | `check/umich/hummingbird.py:36` | info | `{site},unsupported-turned-off,{name}` | default | own |
| 33 | `check/umich/hummingbird.py:47` | alert | `{site},unsupported,{name}` | default | own |
| 34 | `check/umich/oidc_login.py:23` | warning | `{site},umich-oidc-login-reinstall` | default | own |
| 35 | `check/umich/sitelens.py:106` | info | `{site},sitelens-url-paths,{num}` | derived | derived |
| 36 | `check/wordpress/favicon.py:40` | warning | `{site},no-favicon` | default | own |
| 37 | `check/wordpress/ocp.py:41` | alert | `{site},ocp-config-fix-needed` | default | own |

**Icon arithmetic (measured, D-i14c-5):** 29 producers carry an explicit `icon`; **26** are
literals equal to `sc.icon[type]`, 2 are `check_drupal_module`'s local variable, 1 is the
custom 💵. The conversion therefore deletes **28** icon entries and keeps exactly **one** — and
with the 26 literals go 26 chances of a silent typo in an HTML entity that no `.ambr` snapshot
and only one test assert.

**#7/#8 lose a hand-rolled severity→icon map.** `check_drupal_module` builds
`icon = "&#x26A0;"; if level == "info": icon = "&#x1F50E;"` — a duplicate of `sc.icon` that is
*wrong* for `level="alert"` (a warning triangle on an alert notice). After conversion,
`severity=Severity(level)` derives the icon from the one map and an unknown level raises
`ValueError` at the producer instead of shipping a wrong icon (PD#1, PD#2). **The `level`
parameter and both of its reachable values are LIVE** — spec-review finding 3 corrected an
earlier claim here: there are **three** callers, and `check/umich/cloudflare_cms.py:31` passes
`level="info"` for `purge_processor_cron`, pinned by
`tests/integration/test_check_umich_cloudflare_cms.py:127`
(`["info", "warning", "warning", "warning"]`). `Severity(level)` reproduces both reachable
icons exactly; only the unreachable `alert` case changes, from wrong to correct.

**Terminology (PD#11).** `wp_error(site, code, message, errors)` / `drush_error(...)` take a
parameter named `code` that is **not** a notice code — it is the failing operation
(`"version-check"`, `"plugin-list"`, `"ocp-config-check"`, …) and becomes `csv_extra[0]`, while
the notice code is `wp-error`. Two different things named `code` in one call is the collision
PD#11 forbids: rename the parameter to **`operation`**. All **12** call sites (7 in
`psh/gather.py`; `check/wordpress/ocp.py:28`, `check/wordpress/favicon.py:24`,
`check/drupal/multisite.py:29`, `check/umich/drupal_ua.py:49,64`) and both test call sites
(`tests/integration/test_wrappers.py:85,96`) pass it **positionally** (verified), so the rename
costs no call-site churn beyond the two definitions.

### 2.5 The two producers that do not go through `add_notice`

1. **`check/umich/annual_billing.py`** publishes the hook-produced key `annual_bill_upcoming`,
   read by `sort_notices_and_subject` and inserted straight into the render-only
   `sorted_notices` list — never into `site_context["notices"]`, so it never reaches
   `-notices.csv` (load-bearing, LEDGER I12). The builder returns a `Notice`; the **hook**
   publishes `site_context.notice_to_dict(notice)`, so the key's documented type (a render
   dict) and every consumer stay unchanged. This is why the projection is public.
2. **`psh/cli.py:no_primary_domain_notice`** returns a notice or `None`; `main()` passes the
   non-`None` result to `add_notice`. It returns `Notice | None` after conversion; the `None`
   branch and the call site are untouched.

### 2.6 Deliverable E — retiring the dict form

`add_notice` becomes `Notice`-only:

- A non-`Notice` argument raises **`TypeError`**, naming the offending value's type and
  pointing at `psh.notice.Notice` (PD#2: a named error, not a bare exit).
- The `if 'message' not in notice: console.print(...); sys.exit(1)` guard is **deleted** — it
  guards a dict that can no longer arrive, and `Notice.html` is a required constructor
  argument. Its test (`tests/unit/test_site_context.py:89`,
  `test_add_notice_missing_message_exits`, asserting `SystemExit`) is **rewritten** to assert
  the `TypeError` on a dict argument; see §5(4).
- `add_notices(notices: list[Notice])` is unchanged apart from its docstring/annotation.
- `Notice.order` keeps its `"prepend"`/`"first"` semantics in `add_notice` even though no
  producer uses them today: it is part of the §6 field set, and `add_news_item` shows the
  behavior is live for the sibling collection.

### 2.7 Decisions (D-i14c-1…11, exhaustive)

| # | Decision | Why |
|---|---|---|
| D-i14c-1 | `csv_extra: tuple[str, ...] = ()`, joined after `site,code` | §2.1; user-selected over `csv_suffix`/`csv` override |
| D-i14c-2 | The render dict stays the storage form; only the *producer* dict form is retired | Templates/sort/csv all read it; replacing it would move goldens (§3 bar) |
| D-i14c-3 | The projection becomes public `SiteContext.notice_to_dict` with full normalization | One projection for both the `add_notice` path and the billing produced key (DRY); the site name cannot be mismatched because it comes from the context |
| D-i14c-4 | `order` is dropped from the stored render dict | `add_notice` was its only reader; no producer sets it |
| D-i14c-5 | Explicit `icon=` kept only on `annual-bill` (#30); 26 literal defaults and `check_drupal_module`'s 2-entry local map are deleted | Measured equal to the default by `tools/notice_inventory.py`; removes 26 unasserted literals and one latent wrong-icon bug |
| D-i14c-6 | All 36 roster codes registered at import through module-level constants | Makes the duplicate-code guard real; a constant cannot drift from what was registered |
| D-i14c-7 | `NoticeRegistry.snapshot()/restore()` + autouse `reset_sc` restore, plus the §2.3 no-load-outside-a-function-scoped-fixture rule (one test file fixed) | Standalone module loads re-execute module bodies; user-selected over an idempotent `register()`, which would silently allow a genuine duplicate |
| D-i14c-8 | `wp_error`/`drush_error` parameter `code` → `operation` | PD#11: two different things named `code` in one call after conversion |
| D-i14c-9 | `add_notice` raises `TypeError` on a non-`Notice`; the missing-`message` exit guard is deleted and its test rewritten | PD#1/PD#2; the guard becomes unreachable |
| D-i14c-10 | The two whole-dict snapshot files keep their dict-level pins by snapshotting `ctx.notice_to_dict(builder(...))` | Preserves 2 of the 9 entries byte-identically and limits the other 7 to one added `'icon'` line each — a smaller, more reviewable diff than restructuring 9 entries into 27 string snapshots, and it pins *more* than before (§3) |
| D-i14c-11 | The join-shaped builders take `csv_extra=tuple(xs)`, with the empty-input precondition documented and pinned by tests | §2.1; the byte-identical-when-empty alternative hides the row's real field structure to protect an unreachable branch |

## 3. Behavior bar (CAMPAIGN.md §8, applied)

| Surface | I14c rule |
|---|---|
| Rendered emails (4 e2e goldens) | **Byte-identical. No exception is claimed.** `git diff <base> -- tests/e2e/__snapshots__/` MUST be empty |
| `.ambr` snapshots — 100 of 107 | **Byte-identical.** No exception claimed |
| `.ambr` snapshots — the 7 whole-dict entries in `tests/integration/__snapshots__/test_dns_notice_render.ambr` | **Each gains exactly one `'icon': …` line** and changes in no other byte. Cause: those builders omit `icon` today and are snapshotted *before* `add_notice` fills it; under D-i14c-10 they are snapshotted through the projection, which always emits it. The diff MUST be pasted in the task report and the ledger entry, and MUST show only added `'icon'` lines. (`test_plan_recommendation_notice_render.ambr`'s 2 whole-dict entries already carry all six keys, so they stay byte-identical — measured.) |
| Notice csv **values** | **Unchanged.** I14c is NOT one of §8's sanctioned-change increments (I1, I7, I9, I14a) |
| `-results.json` / `-notices.csv` / `-run.json` | Unchanged (structure and values) |
| stdout / console | One change, sanctioned by §8: key order in the `-v` notices dump (`psh/cli.py:879`) for the 8 icon-less producers (§2.2 consequence 3) |
| Config keys | None added, renamed, or removed |
| Exit codes, resume semantics, artifact gates | Unchanged |
| Invariants 1–11 (CAMPAIGN.md §9) | All preserved. **Invariant 8** (column-0 `f"""` literals move verbatim) is this increment's top risk — instrument I2a (§4) is its mechanical proof |

## 4. Seams under test and instruments (the Spine's seam bar)

**Existing seams, unchanged and reused** (no new mocking mechanism is introduced):
`psh.gateway.run_terminus` + `psh.gather.run_terminus` (the `gateway` fixture), `sc.SiteContext`
for hook-level tests, `tests/helpers/checkload.py` and `spec_from_file_location` for standalone
`check/` modules, `psh.dns_classify.resolve`, `httpseam.fetch`/`sleep`, and — named explicitly
because six render tests use it and the first spec draft did not name it — **the pure builders
called directly** (`build_php_eol_notice`, `build_smell_notices`,
`build_plan_recommendation_notice`, `build_annual_bill_upcoming_notice`,
`no_primary_domain_notice`, `check_wordpress_plugin`, `check_drupal_module`, the
`check/dns/notices.py` and `check/cloudflare/notices.py` builders).

**New seams (two, both named here so implementer subagents may test at them):**

1. `SiteContext.notice_to_dict(notice) -> dict` — the public projection (§2.2).
2. `psh.notice.registry.snapshot()/restore()` — driven by the autouse `reset_sc` fixture (§2.3).

**Instruments** (PD#14 — a green check is a claim until it has failed on the condition it
guards). The two scanning instruments are **committed, runnable tools**, not prose:

| # | Instrument | Guards | Red demonstration |
|---|---|---|---|
| I1 | The 4 e2e goldens + the 107 `.ambr` snapshots | Rendered bytes | Long-proven in this repo's history; each task pastes `git diff <base> -- tests/e2e/__snapshots__/` (MUST be empty) and `-- '*.ambr'` (MUST be empty except the 7 §3 entries at Task 4) |
| I2a | `tools/literal_equality.py <baseline-rev> <files…>` — multiset comparison of `ast.dump` for every notice-body literal node (dict `message`/`text`/`short` **and** `Notice(html=/text=/short=)`), so a field *rename* is invisible but any change to a literal's interior is not | **Invariant 8** | Built in: `--self-test <rev> <file>` re-indents one real literal in memory and asserts the comparison reports it; it first runs an unparse/reparse **control**, so a red result is attributable to the re-indent and not to unparse noise. Verified working before this spec was finalized (`psh/gather.py`: 27 literals, self-test red on 2) |
| I2b | `tools/notice_inventory.py` | Every measured figure in §2.1/§2.4 (37 producers, 29 explicit icons, 26 defaults, 9 two-field/28 extra-field csvs) | Not a regression instrument — it is a one-shot measurement, and after conversion its producer list goes to zero. Its regression successor is I6 |
| I3 | One test per code asserting the exact csv row | csv byte-identity for all 35 converted codes | Each task pastes one deliberately-broken-csv failure |
| I3g | `tools/notice_inventory.py --gate` — AST-based, quote-independent | That **no** dict producer survives Task 6 | Exits 1 today (37 remaining) — the red state is the current tree; the green state is the close gate. A plain `grep '"csv":'` MUST NOT be used: `check/umich/sitelens.py:108` uses single quotes and would slip through |
| I4 | Roster test: load every `check/`/`plugin/` package with everything enabled (`tests/integration/test_hook_dag.py`'s `ALL_PACKAGES` + all-enabled config) and assert `registry.codes()` equals the **36**-code roster | That every code is registered exactly once, and none is invented or lost | Add a bogus code to the expected roster and show it red |
| I5 | `tests/unit/test_add_notice_from_notice.py`: `add_notice(Notice(...))` produces a **frozen expected dict literal** | The projection end-to-end | Change one projected field and show it red. NOTE: the current mechanism (comparing against a second `add_notice` call fed a dict) **cannot survive Deliverable E** and MUST be restated this way |
| I6 | New unit test: `notice_to_dict` yields `sc.icon['info'\|'warning'\|'alert']` for each `Severity`, and honors the 💵 override | The severity→icon mapping after the 26 literals are deleted (no `.ambr` asserts an icon; only `tests/integration/test_check_pantheon_cdn_change.py:57` does) | Change one expected icon and show it red |

**`sitelens-url-paths` is the one code with zero csv coverage** in the suite today (measured:
every other code appears in at least one test file). Task 5 MUST add that pin — an existing gap
closed where the change lands.

## 5. Test plan

Changes are of four kinds. Lists marked exhaustive were produced by scanning, not by memory.

**(1) Builder-level tests repointed** from dict subscripts to `Notice` attributes
(`n["message"]` → `n.html`, `n["type"]` → `n.severity`, `n["csv"]` → `n.code`/`n.csv_extra`) —
**exhaustive**: `tests/unit/test_dns_notices.py`, `test_php_eol_notice.py`,
`test_smell_notices.py`, `test_annual_billing_notices.py`, `test_plan_recommendation_notice.py`,
`test_no_primary_domain_notice.py`, `test_pantheon_cdn_change_notices.py`,
`test_cachecheck_consolidation.py`; `tests/integration/test_wrappers.py` (wp_error/drush_error),
`test_gather_wordpress.py`, `test_gather_drupal.py`. **Assertion semantics MUST NOT change** —
same values, read through the new field names (the I14b Task-3 rule).

**(2) Render/snapshot tests.** Split by where the notice comes from — **exhaustive**:

| File | Notice source | Action |
|---|---|---|
| `test_addon_updates_notice_render.py`, `test_pantheon_notice_render.py` (frozen/live-env/updates), `test_umich_wp_notice_render.py`, `test_umich_drupal_ua_notice_render.py`, `test_wordpress_notice_render.py` (ocp/favicon), `test_check_*` hook tests | `site_context["notices"][…]` | **Untouched.** `.ambr` byte-identical |
| `test_smell_notice_render.py`, `test_drupal_notice_render.py`, `test_wordpress_notice_render.py:70-100`, `test_pantheon_notice_render.py:74-78` | builder return → `["message"]`/`["text"]`/`["short"]` | Repoint to `.html`/`.text`/`.short`. Snapshot **values** unchanged → `.ambr` byte-identical |
| `test_cachecheck_notice_render.py:70,81`, `test_pantheon_cdn_change_notice_render.py:52,62` | `ctx.add_notice(dict(built))` — the `dict()` copy exists because `add_notice` mutates its argument | `ctx.add_notice(built)`; a frozen `Notice` needs no copy. `.ambr` byte-identical |
| `test_plan_recommendation_notice_render.py` (2 entries) | whole-dict snapshot of the builder return | Snapshot `ctx.notice_to_dict(builder(...))` (D-i14c-10). All six keys already present → `.ambr` byte-identical |
| `test_dns_notice_render.py` (7 entries) | whole-dict snapshot of the builder return | Same treatment; each entry gains one `'icon'` line — the only sanctioned `.ambr` diff (§3) |

**(3) New tests** (exhaustive): the `csv_extra` join including the trailing-empty-field case
(`no-primary-domain`) and the empty-`csv_extra` case for each join-shaped builder (D-i14c-11);
projection completeness (icon default per severity — I6 — text default, order handling);
`add_notice` rejecting a dict with `TypeError`; registry `snapshot`/`restore` round-trip; the
roster test (I4); the `sitelens-url-paths` csv pin.

**(4) Tests deleted or semantically rewritten** (exhaustive — nothing else in the suite changes
meaning): `tests/unit/test_site_context.py:89` `test_add_notice_missing_message_exits`
(`SystemExit` → `TypeError` on a dict argument; the guard it pinned is deleted by D-i14c-9), and
`tests/unit/test_add_notice_from_notice.py:9-21` `test_notice_projects_to_legacy_dict` (its
dict-fed comparison arm is impossible after Deliverable E — restated per instrument I5).
`tests/unit/test_site_context.py`'s remaining `_n()`-dict `add_notice` calls (lines 31, 36, 40,
55, 75, 83, 92, 97, 98, 104) and `test_cachecheck_consolidation.py:243,460,466` are mechanical
repoints to `Notice(...)`, kind (1).

**Test-load rule (D-i14c-7):** `tests/unit/test_php_eol_notice.py`'s module-level
`SourceFileLoader(...).load_module()` moves into a function-scoped fixture (§2.3).

Implementation is test-first per `prompts/implementation-standards.md`
(`mattpocock-skills:tdd`); the carve-out is the mechanical repointing in kinds (1)/(2), which
edits existing passing tests rather than adding behavior.

## 6. Task plan (per-task commits, each green)

Producer numbers refer to §2.4. The union of tasks 2–5 is **all 37**, verified by addition:
13 + 11 + 7 + 6 = 37.

| Task | Scope | Gate |
|---|---|---|
| 1 | Deliverables A + B + the registry seam: `csv_extra`, public `notice_to_dict`, `snapshot`/`restore`, the `reset_sc` restore, the new projection/registry unit tests (I5, I6). **`add_notice` still accepts dicts** — nothing is converted yet | `./run-tests --fast`; goldens + all 107 `.ambr` byte-identical |
| 2 | Producers **1–13** (`psh/cli.py`, `psh/gateway.py` incl. D-i14c-8, `psh/gather.py`, `psh/plans.py`) + their 13 codes + kind-(1)/(2) test repoints | + I2a and I3 evidence pasted |
| 3 | Producers **14, 21–28, 36, 37** (`check/addon_updates/`, `check/pantheon/`, `check/wordpress/`, `check/drupal/` = 11) + the `test_php_eol_notice.py` load fix (§2.3) | + I2a, I3 evidence |
| 4 | Producers **15–20, 29** (`check/cloudflare/`, `check/dns/`, `check/pantheon_cdn_change/` = 7) incl. the D-i14c-11 empty-input pins and the §3 seven-entry `.ambr` diff | + I2a, I3 evidence; the `.ambr` diff pasted and shown to be added-`'icon'`-lines only |
| 5 | Producers **30–35** (`check/umich/` = 6) incl. the §2.5 billing wiring and the `sitelens-url-paths` pin | + I2a, I3 evidence |
| 6 | Deliverable E (retirement + `TypeError`) + the roster test (I4) + `tools/notice_inventory.py --gate` green + docs (CLAUDE.md, ledger entry, memory) | Full `./run-tests` incl. the live tier if credentials are present; §8 acceptance pasted |

Tasks 2–5 are independent of each other and each leaves the tree green (the dict path is still
accepted until Task 6), so an overrun splits cleanly. **If the increment proves oversized
mid-session: split, never compress** (CAMPAIGN.md §11) — Task 6 plus any unconverted package
becomes I14c′ with its own ledger entry.

## 7. Obligations discharged / created

**Discharged:** CAMPAIGN.md §6's "dict form retired in I14" reservation; the I3 ledger's
extra-csv-field deferral (I3 → I7 → I10 → I12 → I14c, five increments); `psh/notice.py`'s
docstring promise; §17 Q4's dead-façade concern for `NoticeRegistry`.

**Correction owed to the ledger (§7 obligation 4, "verify — not assume"):** the `§6 Notice csv
field set` amendment entry appended at spec time says "22 of the 37 carry extra csv fields"; the
measured figure is **28** (`tools/notice_inventory.py`). Task 6's ledger entry MUST carry the
correction explicitly rather than silently — the amendment is a ratified campaign document.

**Created for I14d:** CLAUDE.md's notices-vs-news section still describes the dict form as
canonical-alongside-`Notice`; I14c updates it factually, I14d rewrites it wholesale.

## 8. Acceptance (commands + output pasted here at close, never summarized)

```
./run-tests                                            # or --fast + a ledger note if no live creds
git diff <spec-commit> -- tests/e2e/__snapshots__/     # MUST be empty
git diff <spec-commit> -- '*.ambr'                     # MUST show ONLY the 7 added 'icon' lines
uvx ruff@0.15.22 check .                               # merged config, single pass
uvx pyright@1.1.411                                    # standard mode over psh/
python development/2026-07-24-mod-I14c-notice/tools/notice_inventory.py --gate   # MUST exit 0
python development/2026-07-24-mod-I14c-notice/tools/literal_equality.py <spec-commit> \
    $(git diff --name-only <spec-commit> -- 'psh/*.py' 'check/*.py')             # MUST exit 0
python development/2026-07-24-mod-I14c-notice/tools/literal_equality.py --self-test \
    <spec-commit> psh/gather.py                                                  # the I2a red demo
```

Expected at close: the I14b close counts (**1023 passed / 1 skipped** with the live tier; fast
tier 1021/1/2) **plus** the new tests of §5(3); zero golden bytes changed; exactly seven
`.ambr` lines added; both gates green; `--gate` reporting `0` surviving dict producers.

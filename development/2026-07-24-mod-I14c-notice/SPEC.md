# SPEC — I14c: retiring the `Notice` dict form

**Increment:** I14c (Wave 4, third of four). **Date:** 2026-07-24.
**Governing documents** (read in full before implementing; this spec cites them by section
and re-derives nothing): `development/2026-07-17-modularization-campaign/CAMPAIGN.md`
(frozen architecture), `LEDGER.md` (through the I14b entry), `/workspace/CLAUDE.md`,
`/workspace/prompts/directives.md` (the Spine; PD#n citations are to it).

**CAMPAIGN.md §11 row I14c, verbatim:** "`Notice` dict form retired: the reserved §6
csv-field amendment + every producer converted; artifacts byte-identical."

## Glossary (this spec only; domain terms live in `CONTEXT.md`)

- **Producer** — a place in `psh/` or `check/` that constructs one notice. There are
  **37** (§2.4 table, exhaustive), yielding **35 distinct notice codes** (`not-installed`
  and `turned-off` each have a WordPress and a Drupal producer in `psh/gather.py`).
- **Render dict** — the six-key `{type, icon, csv, short, message, text}` mapping stored in
  `site_context["notices"]`, read by `email_template.{html,txt}`
  (`notice.type|icon|message|text`), by `sort_notices_and_subject` (`["type"]`, `["short"]`)
  and by `RunState.record_site_notices` (`["csv"]`). **This form is NOT retired** (§2.2).
- **Dict form** — a producer *handing `add_notice` a hand-built dict*. This is what I14c
  retires.
- **Projection** — `SiteContext.notice_to_dict(notice)`: the one function turning a `Notice`
  into a render dict (§2.2).
- **Roster** — the exhaustive set of registered notice codes (§2.3).

MUST / NEVER / SHOULD / MAY per CAMPAIGN.md §Glossary.

## 1. Scope

### 1.1 In scope (exhaustive)

| # | Deliverable | Where |
|---|---|---|
| A | `Notice` gains `csv_extra: tuple[str, ...]` — the reserved CAMPAIGN.md §6 field-set amendment (deferred I3 → I7 → I10 → I12 → here) | `psh/notice.py` |
| B | The projection made public and complete: `SiteContext.notice_to_dict` | `script_context.py` |
| C | Notice-code registration for all 35 codes + the registry test-reset seam | producers, `psh/notice.py`, `tests/conftest.py` |
| D | All 37 producers converted to construct `Notice` | 20 files (§2.4) |
| E | The dict form retired: `add_notice` accepts **only** a `Notice` | `script_context.py` |
| F | Docs: CLAUDE.md notice sections, CAMPAIGN.md §6 amendment, ledger entry, memory | docs |

### 1.2 NOT in scope (reasoning preserved so it is not re-litigated)

- **News items** (`sc.add_news_item`, `sc.news`, the `[News.*]` TOML tables). News items are
  operator-authored data read from config, not code-built notices; they have no `csv`, no
  code, and no registry. `add_news_item` keeps its dict path unchanged.
- **`sections` / `attachments` dicts** — different shapes, different consumers, unrelated to
  §6.
- **Notice content, csv values, severities, ordering, or which notices exist.** I14c changes
  *representation only* (§3).
- **The render dict itself.** Replacing it with an object (so templates read attributes)
  would touch `email_template.{html,txt}` and every golden — outside CAMPAIGN.md §8's
  "rendered emails NEVER change" bar, and buying nothing this increment needs.
- **The three post-campaign README TODOs** (ruff upgrade + PLR0917, typed `sc` stubs +
  pyright widening, test repoint off the `psh.<name>` surface) — LEDGER I14b says explicitly
  they are not I14c/I14d scope.
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

The projection builds the csv row as `",".join([site_name, code, *csv_extra])`. Every
current csv shape reproduces byte-for-byte:

| Current literal | `code` | `csv_extra` |
|---|---|---|
| `f"{site['name']},frozen"` | `"frozen"` | `()` |
| `f"{site['name']},no-primary-domain,"` | `"no-primary-domain"` | `("",)` — the trailing empty field is real and preserved |
| `f"{site},wp-error,{code},{json.dumps(errors).replace(',', '\\,')}"` | `"wp-error"` | `(operation, json.dumps(errors).replace(",", "\\,"))` |
| `f"{site_name},not-in-dns," + ",".join(hostnames)` | `"not-in-dns"` | `tuple(hostnames)` |
| `f"{site_name},cloudflare-cache,{'+'.join(fqdns)},{'+'.join(ids)}"` | `"cloudflare-cache"` | `("+".join(fqdns), "+".join(ids))` |
| `f"{site_name},its-recommends-plan,{current_plan},{recommended_plan},{savings:.2f}"` | `"its-recommends-plan"` | `(current_plan, recommended_plan, f"{savings:.2f}")` |

`csv_extra` is a **tuple**, not a list: `Notice` is `frozen=True` and a list field would make
it unhashable and mutably shared. Elements MUST already be strings — the projection does not
coerce, so a format spec (`f"{savings:.2f}"`, `str(num_updates)`) is the producer's job and
stays visible at the producer.

**Why not the alternatives** (both rejected in the design round): a `csv_suffix: str` keeps
the comma-joining scattered across 22 producers and models nothing; a full `csv: str`
override re-admits the free-form string the type exists to retire and hands the site name
back to producers.

### 2.2 Deliverable B — the projection

Today `SiteContext._notice_to_dict` is private, builds only the two-field csv, and leaves
`icon`/`text` defaulting to `add_notice`'s fill logic. I14c makes it public and complete:

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
   37 producers: every one is called with the site name of the site being processed (the
   builders that take a `site`/`site_name` parameter — `wp_error`, `drush_error`,
   `check_wordpress_plugin`, `check_drupal_module`, `build_smell_notices`,
   `build_php_eol_notice`, `build_plan_recommendation_notice`, the dns/cachecheck/cdn-change
   builders — are all called with `site["name"]` / the context's site name at every call
   site). Those parameters stay: the console messages inside the builders use them.
2. **`order` is no longer stored in the render dict.** Nothing downstream reads it
   (`add_notice` was its only reader; verified by grep — the other two `order` hits are
   `add_news_item`'s and the projection's), and no producer sets a non-default order today.
3. **`icon` and `text` are always present** in the stored dict, with the same values
   `add_notice`'s fill logic produces today. Key *order* within the dict changes; nothing
   reads a notice dict positionally or serializes it (templates and consumers are all
   by-key — verified), so this is unobservable.

### 2.3 Deliverable C — code registration and the test-reset seam

Each producing module registers its codes at import, via a module-level constant:

```python
NOTICE_FROZEN = registry.register("frozen", description="site frozen by Pantheon for inactivity")
...
    site_context.add_notice(Notice(severity=Severity.ALERT, code=NOTICE_FROZEN, ...))
```

Registration is **per code, not per producer**: `psh/gather.py` registers `not-installed` and
`turned-off` **once** each even though the WordPress and Drupal builders both emit them —
registering twice is exactly the `DuplicateNoticeCodeError` the registry exists to raise.

**The re-import hazard, and its fix.** `NoticeRegistry.register` is import-time-once
metadata, but the test suite loads `check/` modules standalone under fresh probe names
(`tests/helpers/checkload.py`, and direct `spec_from_file_location` in the cloudflare/dns/
sitelens/plugin test files) — so a module body re-executes once per test, and the second
`register()` of the same code would raise. Fix:

```python
class NoticeRegistry:
    def snapshot(self) -> dict[str, str]:   # test seam (tests/conftest.py reset_sc)
        return dict(self._codes)
    def restore(self, snapshot: dict[str, str]) -> None:
        self._codes = dict(snapshot)
```

and the **autouse** `reset_sc` fixture saves/restores it around every test, alongside the
`script_context` globals it already deep-copies. This is safe because **no test loads the
same check module or package twice within one test function** (verified by AST scan over
`tests/`: zero functions with more than one `load_check_package`/`load_check_module`/
`exec_module` call). Production is unaffected: `find_modules()` imports each package once
per process.

Import-time registration is what makes the duplicate-code guard real — it is the bug class
I1 fixed by hand twice (`php-eol`, `annual-bill`; CAMPAIGN.md §10) and the reason
`NoticeRegistry` was built at I3.

### 2.4 Deliverable D — the 37 producers (exhaustive)

Severity/csv/icon/text as they are **today**; `icon` column = does the literal's icon equal
`sc.icon[type]`? `text` column = does the literal supply its own `text`, or is it derived by
html2text?

| # | Producer | severity | csv today | icon | text |
|---|---|---|---|---|---|
| 1 | `psh/cli.py:301` | info | `{site},no-primary-domain,` | default | own |
| 2 | `psh/gateway.py:218` | alert | `{site},wp-error,{code},{json}` | default | own |
| 3 | `psh/gateway.py:300` | alert | `{site},drush-error,{code},{json}` | default | own |
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

**Explicit `icon=` survives on exactly one producer** (#30, the 💵 annual-bill notice). All
other literals either omit `icon` already or set it to the severity default — measured
mechanically, not by eye (the AST scan in §4, instrument I2b). So the conversion **deletes 34
icon literals**, and with them 34 chances of a silent typo in an HTML entity no test asserts.

**#7/#8 lose a hand-rolled severity→icon map.** `check_drupal_module` builds
`icon = "&#x26A0;"; if level == "info": icon = "&#x1F50E;"` — a duplicate of `sc.icon` that
is *wrong* for `level="alert"` (it would ship a warning triangle on an alert notice). After
conversion, `severity=Severity(level)` derives the icon from the one map, and an unknown
level raises `ValueError` at the producer instead of shipping a wrong icon (PD#1, PD#2). The
`level` parameter itself stays (public builder signature); no in-tree caller passes it today
— both callers take the `"warning"` default, so the `info` branch is dead and dies as an
orphan of this change, not as unrelated cleanup.

**Terminology (PD#11).** `wp_error(site, code, message, errors)` / `drush_error(...)` take a
parameter named `code` that is **not** a notice code — it is the failing operation
(`"version-check"`, `"plugin-list"`, `"ocp-config-check"`, …) and becomes `csv_extra[0]`,
while the notice code is `wp-error`. Two different things named `code` in one call is exactly
the collision PD#11 forbids: rename the parameter to **`operation`**. All 10 call sites (7 in
`psh/gather.py`, 3 in `check/`) and both test call sites pass it positionally (verified), so
this is a rename with no call-site churn beyond the definition.

### 2.5 The two producers that do not go through `add_notice`

1. **`check/umich/annual_billing.py`** publishes the hook-produced key
   `annual_bill_upcoming`, read by `sort_notices_and_subject` and inserted straight into the
   render-only `sorted_notices` list (never into `site_context["notices"]`, so it never
   reaches `-notices.csv` — load-bearing, LEDGER I12). The builder returns a `Notice`; the
   **hook** publishes `site_context.notice_to_dict(notice)`, so the key's documented type (a
   render dict) and every consumer stay unchanged. This is why the projection is public.
2. **`psh/cli.py:no_primary_domain_notice`** returns a notice or `None`; `main()` passes the
   non-`None` result to `add_notice`. It returns a `Notice | None` after conversion; the
   `None` branch and the call site are untouched.

### 2.6 Deliverable E — retiring the dict form

`add_notice` becomes `Notice`-only:

- A non-`Notice` argument raises **`TypeError`** with a message naming the offending value
  and pointing at `psh.notice.Notice` (PD#2: named error, not a bare `except`/exit).
- The `if 'message' not in notice: console.print(...); sys.exit(1)` guard is **deleted** — it
  guards a dict that can no longer arrive, and `Notice.html` is a required constructor
  argument, so the failure it detected is now a `TypeError` at construction.
- `add_notices(notices: list[Notice])` is unchanged apart from its docstring/annotation.
- `Notice.order` keeps its `"prepend"`/`"first"` semantics in `add_notice` even though no
  producer uses them today: it is part of the §6 field set and `add_news_item` shows the
  behavior is live for the sibling collection.

### 2.7 Decisions (D-i14c-1…9, exhaustive)

| # | Decision | Why |
|---|---|---|
| D-i14c-1 | `csv_extra: tuple[str, ...] = ()`, joined after `site,code` | §2.1; user-selected in the design round over `csv_suffix`/`csv` override |
| D-i14c-2 | The render dict stays the storage form; only the *producer* dict form is retired | Templates/sort/csv all read it; replacing it would move goldens (§8 bar) |
| D-i14c-3 | The projection becomes public `SiteContext.notice_to_dict` and does the full normalization | One projection for both the `add_notice` path and the billing produced key (DRY); site name can't be mismatched because it comes from the context |
| D-i14c-4 | `order` is dropped from the stored render dict | `add_notice` was its only reader; no producer sets it |
| D-i14c-5 | Explicit `icon=` kept only on `annual-bill`; the other 34 derive from severity, and `check_drupal_module`'s local map dies | Measured equal to the default (§4 I2b); removes 34 unasserted literals and one latent wrong-icon bug |
| D-i14c-6 | All 35 codes registered at import through module-level constants | Makes the duplicate-code guard real; a constant cannot drift from what was registered |
| D-i14c-7 | `NoticeRegistry.snapshot()/restore()` + autouse `reset_sc` restore | Standalone module loads in tests re-execute module bodies (§2.3); user-selected over an idempotent `register()`, which would silently allow a genuine duplicate |
| D-i14c-8 | `wp_error`/`drush_error` parameter `code` → `operation` | PD#11: two different things named `code` in one call after conversion |
| D-i14c-9 | `add_notice` raises `TypeError` on a non-`Notice`; the missing-`message` exit guard is deleted | PD#1/PD#2; the guard becomes unreachable |

## 3. Behavior bar (CAMPAIGN.md §8, applied)

| Surface | I14c rule |
|---|---|
| Rendered emails (4 e2e goldens) | **Byte-identical.** No exception is claimed. |
| All 107 `.ambr` snapshots | **Byte-identical.** No exception is claimed. |
| Notice csv **values** | **Unchanged** — I14c is NOT one of the §8 sanctioned-change increments (I1, I7, I9, I14a) |
| `-results.json` / `-notices.csv` / `-run.json` | Unchanged (structure and values) |
| stdout / console | Unchanged in practice (no console line is touched); MAY improve per §8 |
| Config keys | None added, renamed, or removed |
| Exit codes, resume semantics, artifact gates | Unchanged |
| Invariants 1–11 (§9) | All preserved; **Invariant 8** (column-0 `f"""` literals move verbatim) is this increment's top risk — see §4 |

## 4. Seams under test and instruments (the Spine's seam bar)

**Existing seams, unchanged and reused** (no new mocking mechanism is introduced):
`psh.gateway.run_terminus` + `psh.gather.run_terminus` (the `gateway` fixture),
`sc.SiteContext` for hook-level tests, `tests/helpers/checkload.py` and
`spec_from_file_location` for standalone `check/` modules, `psh.dns_classify.resolve`,
`httpseam.fetch`/`sleep`, the pure builders (`build_php_eol_notice`, `build_smell_notices`,
`build_plan_recommendation_notice`, `build_annual_bill_upcoming_notice`,
`no_primary_domain_notice`, the `check/dns/notices.py` builders) called directly.

**New seams (two, both named here so implementer subagents may test at them):**

1. `SiteContext.notice_to_dict(notice) -> dict` — public projection (§2.2).
2. `psh.notice.registry.snapshot()/restore()` — the registry test seam, driven by the autouse
   `reset_sc` fixture (§2.3).

**Instruments, and how each is shown able to go red** (PD#14 — a green check is a claim until
it has failed on the condition it guards):

| # | Instrument | Guards | Red demonstration (MUST be run and pasted in the task report) |
|---|---|---|---|
| I1 | The 4 e2e goldens + 107 `.ambr` snapshots | Rendered bytes | Already proven capable: the suite's history. No new demo required; a diff of `tests/e2e/__snapshots__/` MUST be pasted empty at each task and at close |
| I2a | Per-producer AST equality check: `ast.dump` of the old `"message"`/`"text"`/`"short"` value node vs. the new `html=`/`text=`/`short=` keyword node | **Invariant 8** — that no notice literal was re-indented or otherwise altered while being re-keyed | Re-indent one literal by one space in a scratch copy and show the check reporting that producer as changed |
| I2b | AST scan comparing each literal's `icon` to `sc.icon[type]` | D-i14c-5's claim that 34 icons equal the default | Change one expected icon in the scratch script and show it reporting a mismatch |
| I3 | One test per code asserting the exact csv row | csv byte-identity for all 35 codes | Per §5, each task pastes one deliberately-broken-csv failure |
| I4 | Roster test: load every `check/`/`plugin/` package (the `ALL_PACKAGES` list in `tests/integration/test_hook_dag.py`) and assert `registry.codes()` equals the 35-code roster + `no-domains` | That every code is registered exactly once and no code is invented or lost | Add a bogus code to the expected roster and show it red |
| I5 | `tests/unit/test_add_notice_from_notice.py` full-dict equality (`Notice`-projected == the pre-change literal) extended to a `csv_extra` notice and a derived-icon/derived-text notice | The projection itself | Change one projected field and show it red |

**`sitelens-url-paths` is the one code with zero csv coverage** in the suite today (measured:
every other code appears in at least one test file). Task 5 MUST add that pin — an existing
gap closed where the change lands, not a new one created.

## 5. Test plan

No test file is deleted. Changes are of three kinds:

1. **Builder-level tests repointed** from dict subscripts to `Notice` attributes
   (`n["message"]` → `n.html`, `n["csv"]` → `n.code` / `n.csv_extra`, `n["type"]` →
   `n.severity`): `tests/unit/test_dns_notices.py`, `test_php_eol_notice.py`,
   `test_smell_notices.py`, `test_annual_billing_notices.py`,
   `test_plan_recommendation_notice.py`, `test_no_primary_domain_notice.py`,
   `test_pantheon_cdn_change_notices.py`, `test_cachecheck_consolidation.py`,
   `tests/integration/test_wrappers.py` (`wp_error`/`drush_error`), plus the
   `psh/gather.py` builder tests. **Assertion semantics MUST NOT change** — same values,
   read through the new field names (the I14b Task-3 rule).
2. **Hook-level and snapshot tests untouched.** They read `site_context["notices"][…]`, which
   is still a render dict. This is the single biggest reason for D-i14c-2: ~24 test files and
   all 107 `.ambr` files need no edit and therefore keep their full evidentiary value.
3. **New tests** (exhaustive): the `csv_extra` join incl. the trailing-empty-field case
   (`no-primary-domain`); projection completeness (icon default, text default, order
   handling); `add_notice` rejecting a dict with `TypeError`; registry `snapshot`/`restore`;
   the roster test (I4); the `sitelens-url-paths` csv pin.

Implementation is test-first per `prompts/implementation-standards.md`
(`mattpocock-skills:tdd`); the carve-outs are the mechanical repoints in kind (1), which are
edits to existing passing tests, not new behavior.

## 6. Task plan (per-task commits, each green)

| Task | Scope | Gate |
|---|---|---|
| 1 | Deliverables A + B + the registry seam (C's infrastructure): `csv_extra`, public `notice_to_dict`, `snapshot`/`restore`, `reset_sc` restore, the new unit tests (I5). **`add_notice` still accepts dicts** — nothing is converted yet | Full `./run-tests --fast`; goldens/snapshots byte-identical |
| 2 | Producers 1–13 (`psh/cli.py`, `psh/gateway.py` incl. D-i14c-8, `psh/gather.py`, `psh/plans.py`) + their codes + their test repoints | + I2a/I2b/I3 evidence pasted |
| 3 | Producers 21–28, 36, 37 (`check/pantheon/`, `check/wordpress/`, `check/drupal/`, `check/addon_updates/` = 11 literals) | + I2a/I3 evidence |
| 4 | Producers 15–20, 29 (`check/dns/`, `check/cloudflare/`, `check/pantheon_cdn_change/` = 7 literals) | + I2a/I3 evidence |
| 5 | Producers 30–35 (`check/umich/`, 6 literals) incl. the §2.5 billing wiring and the `sitelens-url-paths` pin | + I2a/I3 evidence |
| 6 | Deliverable E (retirement + `TypeError`) + the roster test (I4) + docs (CLAUDE.md, CAMPAIGN.md §6 amendment already landed at spec time, ledger entry, memory) | Full `./run-tests` incl. live tier if credentials are present; §8 acceptance pasted |

Tasks 2–5 are independent of each other and each leaves the tree green (the dict path is
still accepted until Task 6), so an overrun splits cleanly. **If the increment proves
oversized mid-session: split, never compress** (CAMPAIGN.md §11) — Task 6 plus any unconverted
package becomes I14c′ with its own ledger entry.

## 7. Obligations discharged / created

**Discharged:** the CAMPAIGN.md §6 "dict form retired in I14" reservation; the I3 ledger's
extra-csv-field deferral (I3 → I7 → I10 → I12 → I14c, five increments); the `psh/notice.py`
docstring's "the dict form is retired in I14"; §17 Q4's dead-façade concern for
`NoticeRegistry` (it becomes load-bearing).

**Created for I14d:** CLAUDE.md's notices-vs-news section describes the dict form as
canonical-alongside-`Notice`; I14c updates it factually, I14d rewrites it wholesale.

## 8. Acceptance (commands + output pasted here at close, never summarized)

```
./run-tests                      # or --fast + a ledger note if no live credentials
git diff <spec-commit> -- tests/e2e/__snapshots__/     # MUST be empty
git diff <spec-commit> -- '*.ambr'                     # MUST be empty
uvx ruff@0.15.22 check .                               # merged config, single pass
uvx pyright@1.1.411                                    # standard mode over psh/
python - <<'…'  # instrument I2a over the whole conversion, plus its red demo
```

Expected at close: the I14b close counts (**1023 passed / 1 skipped** with the live tier,
fast tier 1021/1/2) **plus** the new tests of §5(3); zero `.ambr`/golden bytes changed; both
gates green; and `grep -rn '"csv":' psh/ check/ plugin/ script_context.py` returning
**exactly one** hit — `script_context.py`'s projection (the mechanical proof that no producer
still builds a notice dict).

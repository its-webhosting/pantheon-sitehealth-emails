# I14c — `Notice` Dict-Form Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every
> code-touching dispatch is a **`psh-implementer`**; every task review is a **`psh-reviewer`**
> (CLAUDE.md § Dispatching subagents — a dispatch that cannot use them MUST stop and say so).

**Goal:** Every notice in the program is constructed as a typed `psh.notice.Notice`; the
hand-built notice dict is retired as a producer form, with the rendered emails and the notices
CSV byte-identical.

**Architecture:** `Notice` gains `csv_extra` (the CAMPAIGN.md §6 amendment). One public
projection, `SiteContext.notice_to_dict`, turns a `Notice` into the six-key render dict that
templates, `sort_notices_and_subject` and `record_site_notices` already consume — so the storage
form does not change and hook/snapshot tests keep their evidentiary value. Each producing module
registers its notice codes at import through module-level constants, making
`NoticeRegistry`'s duplicate-code guard load-bearing.

**Tech Stack:** Python 3.12, pytest + syrupy, ruff 0.15.22 / pyright 1.1.411 (both pinned;
`./run-tests` gates on them), `dataclasses`, `enum.StrEnum`.

**Read before starting any task** (CAMPAIGN.md §7 obligation 1): this plan's SPEC
(`development/2026-07-24-mod-I14c-notice/SPEC.md`), `prompts/directives.md`,
`prompts/implementation-standards.md`, `CLAUDE.md`, and
`development/2026-07-17-modularization-campaign/CAMPAIGN.md` §§3.5, 6, 8, 9.

## Global Constraints

- **Invariant 8 (CAMPAIGN.md §9):** notice `f"""` literals move **verbatim** — never
  re-indented. `git diff -w` is NOT acceptable evidence. The proof is
  `python development/2026-07-24-mod-I14c-notice/tools/literal_equality.py <base> <files…>`.
- **Invariant 1:** the four e2e goldens are byte-identical. `git diff <base> --
  tests/e2e/__snapshots__/` MUST be empty at every task.
- **`.ambr` snapshots:** byte-identical at every task **except** Task 4, which adds exactly one
  `'icon': …` line to each of the 7 entries in
  `tests/integration/__snapshots__/test_dns_notice_render.ambr` (SPEC §3). No other `.ambr`
  byte may change, and `--update-goldens` MUST NOT be run for any other reason.
- **Notice csv values never change** (SPEC §3). I14c is not a §8 sanctioned-change increment.
- **Test-first** (`mattpocock-skills:tdd`, per `prompts/implementation-standards.md`, which
  overrides `superpowers:test-driven-development`). Carve-out: mechanically repointing an
  existing passing test from `n["message"]` to `n.html` is an edit, not new behavior.
- **Assertion semantics never change** when repointing a test: same values, new field names.
- **Every task ends green:** `./run-tests --fast` (offline inner loop) plus the evidence block
  named in the task. Task 6 runs the full `./run-tests`.
- **Every task report cites the directives it applied by number with a verbatim quote**
  (CLAUDE.md § Dispatching subagents).
- Before dispatching, purge stale reports: `rm -f .superpowers/sdd/task-*-report.md`
  (LEDGER I1 process note — a stale report was once misreported as success).
- **Run the type gate as `./run-tests` does: `pyright`, the venv binary** (pinned to 1.1.411 by
  the test extra). A bare `uvx pyright@1.1.411` runs in an isolated environment with none of the
  project's dependencies and reports ~34 false `reportMissingImports` — measured at Task 1.

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `psh/notice.py` | `Notice` (+ `csv_extra`), `Severity`, `NoticeRegistry` (+ `snapshot`/`restore`), `registry` | 1 |
| `script_context.py` | `SiteContext.notice_to_dict` (public projection), `add_notice` | 1, 6 |
| `tests/conftest.py` | `reset_sc` also snapshots/restores `psh.notice.registry` | 1 |
| `psh/gateway.py`, `psh/gather.py`, `psh/plans.py`, `psh/cli.py` | producers 1–13 + their codes | 2 |
| `check/addon_updates/`, `check/pantheon/`, `check/wordpress/`, `check/drupal/` | producers 14, 21–28, 36, 37 | 3 |
| `check/cloudflare/notices.py`, `check/dns/notices.py`, `check/pantheon_cdn_change/notices.py` | producers 15–20, 29 | 4 |
| `check/umich/` (annual_billing, drupal_ua, hummingbird, oidc_login, sitelens) | producers 30–35 | 5 |
| `tests/unit/test_notice.py`, `test_add_notice_from_notice.py`, `test_site_context.py` | the type, the projection, the registry | 1, 6 |
| `tests/integration/test_notice_roster.py` (new) | the 36-code roster | 6 |

---

### Task 1: `csv_extra`, the public projection, and the registry test seam

**Files:**
- Modify: `psh/notice.py` (add `csv_extra`; add `snapshot`/`restore`)
- Modify: `script_context.py:117-153` (`add_notice` + `_notice_to_dict` → `notice_to_dict`)
- Modify: `tests/conftest.py:126-151` (`reset_sc`)
- Test: `tests/unit/test_notice.py`, `tests/unit/test_add_notice_from_notice.py`,
  `tests/unit/test_site_context.py`

**Interfaces:**
- Produces (tasks 2–6 rely on these exact names):
  - `Notice(severity=…, code=…, html=…, short=…, text=…, icon=…, order=…, csv_extra=…)`
    with `csv_extra: tuple[str, ...] = ()`
  - `SiteContext.notice_to_dict(notice: Notice) -> dict` — public
  - `NoticeRegistry.snapshot() -> dict[str, str]`, `NoticeRegistry.restore(snapshot) -> None`
- Consumes: nothing (first task).
- **Not yet:** `add_notice` still accepts a legacy dict. Retirement is Task 6, so tasks 2–5 can
  land one package at a time with the tree green.

- [ ] **Step 1: Write the failing tests for `csv_extra` and the projection**

Append to `tests/unit/test_notice.py`:

```python
def test_csv_extra_defaults_to_empty_and_is_a_tuple():
    n = Notice(severity=Severity.ALERT, code="frozen", html="<p>x</p>")
    assert n.csv_extra == ()


def test_registry_snapshot_and_restore_round_trip():
    r = NoticeRegistry()
    r.register("a")
    saved = r.snapshot()
    r.register("b")
    assert r.codes() == frozenset({"a", "b"})
    r.restore(saved)
    assert r.codes() == frozenset({"a"})
    r.register("b")          # restore must make a re-registration legal again
    assert r.codes() == frozenset({"a", "b"})
```

Append to `tests/unit/test_add_notice_from_notice.py`:

```python
def test_csv_extra_fields_are_joined_after_site_and_code():
    ctx = sc.SiteContext({"name": "s1"})
    ctx.add_notice(Notice(severity=Severity.ALERT, code="wp-error", html="<p>x</p>",
                          csv_extra=("version-check", 'boom')))
    assert ctx["notices"][0]["csv"] == "s1,wp-error,version-check,boom"


def test_csv_extra_preserves_a_trailing_empty_field():
    # psh/cli.py's no-primary-domain csv ends in a comma; the empty field is real.
    ctx = sc.SiteContext({"name": "s1"})
    ctx.add_notice(Notice(severity=Severity.INFO, code="no-primary-domain", html="<p>x</p>",
                          csv_extra=("",)))
    assert ctx["notices"][0]["csv"] == "s1,no-primary-domain,"


def test_projection_fills_the_icon_from_the_severity():
    ctx = sc.SiteContext({"name": "s1"})
    for severity, expected in (
        (Severity.INFO, "&#x1F50E;"),
        (Severity.WARNING, "&#x26A0;"),
        (Severity.ALERT, "&#x1F6A8;"),
    ):
        d = ctx.notice_to_dict(Notice(severity=severity, code=f"c-{severity}", html="<p>x</p>"))
        assert d["icon"] == expected


def test_projection_honors_an_explicit_icon():
    ctx = sc.SiteContext({"name": "s1"})
    d = ctx.notice_to_dict(Notice(severity=Severity.ALERT, code="annual-bill",
                                  html="<p>x</p>", icon="&#x1F4B5;"))
    assert d["icon"] == "&#x1F4B5;"


def test_projection_emits_exactly_the_six_render_keys():
    ctx = sc.SiteContext({"name": "s1"})
    d = ctx.notice_to_dict(Notice(severity=Severity.INFO, code="c", html="<p>x</p>",
                                  order="first"))
    assert set(d) == {"type", "icon", "csv", "short", "message", "text"}   # no 'order'
```

`tests/unit/test_notice.py` already imports `Notice`, `Severity`, `NoticeRegistry`, `registry`;
add nothing to its imports but `NoticeRegistry` if absent.

- [ ] **Step 2: Run them and watch them fail for the right reason**

```bash
./run-tests --fast tests/unit/test_notice.py tests/unit/test_add_notice_from_notice.py
```
Expected: `TypeError: Notice.__init__() got an unexpected keyword argument 'csv_extra'`,
`AttributeError: 'NoticeRegistry' object has no attribute 'snapshot'`, and
`AttributeError: 'SiteContext' object has no attribute 'notice_to_dict'` — **not** a collection
error (PD#14: fail for the right reason).

- [ ] **Step 3: Add `csv_extra` and the registry seam to `psh/notice.py`**

In the `Notice` dataclass, after `order`:

```python
    csv_extra: tuple[str, ...] = ()
```

and extend the class docstring's last sentence with:
`` `csv_extra` holds the notices-CSV fields that follow `site,code` (CAMPAIGN.md §6 as amended
at I14c); elements MUST already be strings — the projection does not coerce, so a format spec
like f"{savings:.2f}" stays visible at the producer. ``

In `NoticeRegistry`, after `codes()`:

```python
    def snapshot(self) -> dict[str, str]:
        """Copy the registered codes.  TEST SEAM: tests/conftest.py's autouse reset_sc fixture
        snapshots before each test and restores after, because the suite loads check/ modules
        standalone once per test and a module body re-executing would otherwise re-register its
        codes and raise DuplicateNoticeCodeError.  Production imports each module once."""
        return dict(self._codes)

    def restore(self, snapshot: dict[str, str]) -> None:
        """Restore a snapshot() result.  See snapshot() for why this exists."""
        self._codes = dict(snapshot)
```

Update the module docstring's last line from "the dict form is retired in I14" to
"the dict form is retired at I14c (this module's `csv_extra` field is that increment's
CAMPAIGN.md §6 amendment)".

- [ ] **Step 4: Make the projection public and complete in `script_context.py`**

Replace `add_notice` + `_notice_to_dict` (lines 117–153) with:

```python
    def add_notice(self, notice) -> None:      # notice: Notice | dict (dict retired at I14c Task 6)
        """Add a notice, honoring order ('prepend'/'first' -> front).  A Notice is projected to
        the render dict by notice_to_dict; a legacy dict still gets the historical icon/text
        fill (that path is deleted in I14c Task 6, CAMPAIGN.md §6)."""
        if isinstance(notice, Notice):
            d = self.notice_to_dict(notice)
            order = notice.order
        else:
            d = notice
            if 'message' not in d:
                console.print(f'[bold red]ERROR: Notice is missing the "message" key: {d}')
                sys.exit(1)
            if 'icon' not in d:
                d['icon'] = icon[d['type']]
            if 'text' not in d:
                d['text'] = html_to_text(d['message'])
            order = d.get('order', 'append')
        if order in ('prepend', 'first'):
            self['notices'].insert(0, d)
        else:
            self['notices'].append(d)

    def notice_to_dict(self, notice: Notice) -> dict:
        """Project a Notice onto the render dict the report consumes.

        The render dict -- {type, icon, csv, short, message, text} -- is what
        email_template.{html,txt} (notice.type|icon|message|text), sort_notices_and_subject
        (['type'], ['short']) and RunState.record_site_notices (['csv']) read, so it stays the
        storage form (SPEC I14c D-i14c-2).  The csv row is site + code + csv_extra: the site
        name comes from THIS context, never from the producer, so it cannot be mismatched.
        `order` is not stored -- add_notice is its only reader.
        """
        return {
            "type": str(notice.severity),
            "icon": notice.icon or icon[notice.severity],
            "csv": ",".join([self['site']['name'], notice.code, *notice.csv_extra]),
            "short": notice.short,
            "message": notice.html,
            "text": notice.text or html_to_text(notice.html),
        }
```

- [ ] **Step 5: Extend `reset_sc` in `tests/conftest.py`**

Inside the fixture, after `saved = {name: copy.deepcopy(...)}`:

```python
    from psh.notice import registry as notice_registry

    saved_codes = notice_registry.snapshot()
```

and in the `finally:` block, after the `setattr` loop:

```python
        notice_registry.restore(saved_codes)
```

Extend the fixture docstring with:

```
    Also restores psh.notice.registry: producing modules register their notice codes at import,
    and the suite loads check/ modules standalone once per test, so without this the second load
    of a module raises DuplicateNoticeCodeError.  This only works because no producing module is
    executed outside a function-scoped fixture or test body (SPEC I14c §2.3) -- a module-level
    load in a test file, or a module/session-scoped loader fixture, registers BEFORE this
    snapshot and cannot be undone.
```

- [ ] **Step 6: Run the new tests, then the whole fast tier**

```bash
./run-tests --fast tests/unit/test_notice.py tests/unit/test_add_notice_from_notice.py tests/unit/test_site_context.py
./run-tests --fast
```
Expected: the new tests PASS; the fast tier is 1021 passed / 1 skipped / 2 deselected **plus the
7 new tests** = 1028 passed / 1 skipped / 2 deselected; 107 snapshots pass.

- [ ] **Step 7: Evidence and commit**

```bash
git diff HEAD -- tests/e2e/__snapshots__/     # MUST be empty
git diff HEAD -- '*.ambr'                     # MUST be empty
uvx ruff@0.15.22 check psh/notice.py script_context.py tests/conftest.py
git add psh/notice.py script_context.py tests/conftest.py tests/unit/
git commit -m "feat(campaign-I14c): Notice.csv_extra, the public projection, the registry seam"
```

---

### Task 2: convert the 13 `psh/` producers

**Files:**
- Modify: `psh/gateway.py:215-320` (`wp_error`, `drush_error`), `psh/gather.py` (7 producers in
  `check_wordpress_plugin`/`check_drupal_module`, `gather_drupal`'s composer-update, the 3 smell
  builders), `psh/plans.py:150-195`, `psh/cli.py:291-330`
- Modify (call sites of the renamed parameter): `psh/gather.py:203,232,261,310,358,382,403`,
  `check/wordpress/ocp.py:28`, `check/wordpress/favicon.py:24`, `check/drupal/multisite.py:29`,
  `check/umich/drupal_ua.py:49,64`
- Test: `tests/integration/test_wrappers.py`, `tests/unit/test_smell_notices.py`,
  `tests/unit/test_no_primary_domain_notice.py`, `tests/unit/test_plan_recommendation_notice.py`,
  `tests/integration/test_smell_notice_render.py`, `test_drupal_notice_render.py`,
  `test_wordpress_notice_render.py`, `test_plan_recommendation_notice_render.py`,
  `tests/integration/test_gather_wordpress.py`, `test_gather_drupal.py`

**Interfaces:**
- Consumes: `Notice(..., csv_extra=…)`, `SiteContext.notice_to_dict`, `registry.register` (Task 1).
- Produces: the builders now return `Notice` / `list[Notice]` —
  `wp_error(site, operation, message, errors) -> list[Notice]`,
  `drush_error(site, operation, message, errors) -> list[Notice]`,
  `check_wordpress_plugin(...) -> list[Notice]`, `check_drupal_module(...) -> list[Notice]`,
  `build_smell_notices(...) -> list[Notice]`,
  `build_plan_recommendation_notice(...) -> Notice`,
  `no_primary_domain_notice(...) -> Notice | None`. Tasks 3–5 call none of these except through
  `sc.wp_error` / `sc.drush_error` / `sc.check_wordpress_plugin` / `sc.check_drupal_module`,
  which keep their names.

**Codes to register in this task** (module-level constants, in the module that builds them):

| Module | Constant | Code | Description argument |
|---|---|---|---|
| `psh/gateway.py` | `NOTICE_WP_ERROR` | `wp-error` | `"wp-cli command failed"` |
| `psh/gateway.py` | `NOTICE_DRUSH_ERROR` | `drush-error` | `"drush command failed"` |
| `psh/gather.py` | `NOTICE_NOT_INSTALLED` | `not-installed` | `"recommended plugin/module not installed"` |
| `psh/gather.py` | `NOTICE_MULTIPLE_INSTALLED` | `multiple-installed` | `"plugin installed more than once"` |
| `psh/gather.py` | `NOTICE_TURNED_OFF` | `turned-off` | `"recommended plugin/module installed but inactive"` |
| `psh/gather.py` | `NOTICE_COMPOSER_UPDATE` | `composer-update` | `"composer update dry run failed"` |
| `psh/gather.py` | `NOTICE_WP_SMELL` | `wp-smell` | `"wp-cli wrote to stderr"` |
| `psh/gather.py` | `NOTICE_DRUSH_SMELL` | `drush-smell` | `"drush wrote to stderr"` |
| `psh/gather.py` | `NOTICE_COMPOSER_SMELL` | `composer-smell` | `"composer wrote to stderr"` |
| `psh/plans.py` | `NOTICE_ITS_RECOMMENDS_PLAN` | `its-recommends-plan` | `"a cheaper plan fits this site's traffic"` |
| `psh/cli.py` | `NOTICE_NO_PRIMARY_DOMAIN` | `no-primary-domain` | `"multiple custom domains, none primary"` |

`not-installed` and `turned-off` are registered **once** in `psh/gather.py` even though the
WordPress and Drupal builders both emit them — a second `register()` of either raises.

- [ ] **Step 1: Repoint one builder's test first (red), starting with the smells**

In `tests/unit/test_smell_notices.py` change the reads (values stay identical):

```python
    (n,) = psh.build_smell_notices("s", "boom", "", "")
    assert n.code == "wp-smell"
    assert n.csv_extra == (json.dumps("boom").replace(",", "\\,"),)
    assert n.severity == "info"
    assert n.html.startswith("\n<p>")        # was n["message"]
```

Run `./run-tests --fast tests/unit/test_smell_notices.py` — expected: `TypeError: 'dict' object
has no attribute 'code'` (or `AttributeError`), i.e. red because the builder still returns dicts.

- [ ] **Step 2: Convert that builder, keeping the literal untouched**

Mechanical recipe, applied to every producer in this task (worked example =
`psh/gather.py`'s `check_drupal_module` "not installed" notice):

```python
# BEFORE
        notices.append(
            {
                "type": level,
                "icon": icon,
                "csv": f"{site},not-installed,{name}",
                "short": f"install module {name}",
                "message": f'<p>The <a href="{escape_url(url)}">…</a> …</p>',
                "text": f"The {display_name} Drupal module\n<{url}>\n…",
            }
        )

# AFTER  -- the html/text/short VALUES are moved unchanged; only keys and the csv split change
        notices.append(
            Notice(
                severity=Severity(level),
                code=NOTICE_NOT_INSTALLED,
                csv_extra=(name,),
                short=f"install module {name}",
                html=f'<p>The <a href="{escape_url(url)}">…</a> …</p>',
                text=f"The {display_name} Drupal module\n<{url}>\n…",
            )
        )
```

Rules for the recipe:
1. `"type"` → `severity=Severity.ALERT|WARNING|INFO` (or `Severity(level)` for the two
   `check_drupal_module` producers). **Delete** `icon` unless the value differs from
   `sc.icon[type]` — in this task every icon is the default, so all 13 `icon` entries go, and
   `check_drupal_module`'s local `icon = "&#x26A0;" … if level == "info"` map is deleted with
   them (SPEC §2.4).
2. `"csv"` → `code=<CONSTANT>` + `csv_extra=(…)` with the same field values in the same order.
   For `wp_error`/`drush_error`: `csv_extra=(operation, json.dumps(errors).replace(",", "\\,"))`.
   For `psh/plans.py`: `csv_extra=(current_plan, recommended_plan, f"{savings:.2f}")`.
   For `psh/cli.py`'s no-primary-domain: `csv_extra=("",)`.
3. `"message"` → `html=`, `"short"` → `short=`, `"text"` → `text=` — **paste the literal, do not
   retype or re-wrap it**; several are column-0 `f"""` bodies (Invariant 8).
4. Add `from psh.notice import Notice, Severity, registry` (or extend the existing import) at
   the top of each module. `psh/cli.py` already imports `Notice`/`Severity`/`registry`.
5. Rename `wp_error`/`drush_error`'s second parameter `code` → `operation` in both definitions
   (`psh/gateway.py:215`, `:297`) and update the docstrings. All 12 call sites pass it
   positionally — verify with
   `grep -rn 'wp_error(\|drush_error(' psh/ check/ tests/` that none uses `code=`.

- [ ] **Step 3: Green that builder, then repeat Steps 1–2 for the other 12 producers**

Convert in this order (each is a red-then-green cycle): the 3 smell builders →
`check_wordpress_plugin` (3 producers) → `check_drupal_module` (2) → `gather_drupal`'s
composer-update → `wp_error` → `drush_error` → `psh/plans.py` → `psh/cli.py`.

- [ ] **Step 4: Repoint the remaining consumers of these builders' returns**

- `tests/integration/test_wrappers.py:85,96` — `notices[0]["csv"]` → `notices[0].code` /
  `.csv_extra`; `["message"]` → `.html`.
- `tests/integration/test_smell_notice_render.py`, `test_drupal_notice_render.py`,
  `test_wordpress_notice_render.py:70-100`, `tests/unit/test_no_primary_domain_notice.py`,
  `tests/unit/test_plan_recommendation_notice.py` — `n["message"]` → `n.html`,
  `n["text"]` → `n.text`, `n["short"]` → `n.short`. **Snapshot values are unchanged, so these
  `.ambr` files MUST NOT change.**
- `tests/integration/test_plan_recommendation_notice_render.py:8-11` — snapshot the projection
  so the whole-dict pin survives (SPEC D-i14c-10):

```python
def test_plan_recommendation_render(psh, reset_sc, snapshot, umich):
    ctx = reset_sc.SiteContext({"name": "s"})
    assert ctx.notice_to_dict(psh.build_plan_recommendation_notice(
        "s", "Performance Medium", "Performance Small", 1234.5, 42, umich
    )) == snapshot
```
  Its 2 `.ambr` entries already carry all six render keys, so they stay **byte-identical**.
- `tests/integration/test_gather_wordpress.py`, `test_gather_drupal.py` — any assertion reading
  a returned notice's dict keys.

- [ ] **Step 5: Full fast tier + the Invariant-8 proof**

```bash
./run-tests --fast
python development/2026-07-24-mod-I14c-notice/tools/literal_equality.py <task-1-commit> \
    psh/gateway.py psh/gather.py psh/plans.py psh/cli.py
python development/2026-07-24-mod-I14c-notice/tools/literal_equality.py --self-test \
    <task-1-commit> psh/gather.py
git diff <task-1-commit> -- tests/e2e/__snapshots__/   # MUST be empty
git diff <task-1-commit> -- '*.ambr'                   # MUST be empty
python development/2026-07-24-mod-I14c-notice/tools/notice_inventory.py | tail -1
```
Expected: fast tier green at the Task-1 count; `literal_equality` prints `identical` for all four
files and `4/4`; `--self-test` prints `SELF-TEST PASSED`; both diffs empty; the inventory's
producer count drops from 37 to 24.

- [ ] **Step 6: Paste one deliberately-broken-csv failure (instrument I3)**

Temporarily change one `csv_extra` (e.g. drop `name` from `not-installed`), run the test that
pins it, paste the failure into the task report, revert. This is the evidence that the csv
assertions can go red (PD#14).

- [ ] **Step 7: Commit**

```bash
git add psh/ check/ tests/
git commit -m "feat(campaign-I14c): convert the 13 psh/ notice producers to Notice"
```

---

### Task 3: convert the 11 generic `check/` producers

**Files:**
- Modify: `check/addon_updates/table.py:66`, `check/pantheon/frozen.py:14`,
  `check/pantheon/live_env.py:16`, `check/pantheon/php_eol.py:12,39`,
  `check/pantheon/updates.py:59,93,129`, `check/wordpress/favicon.py:40`,
  `check/wordpress/ocp.py:41`, `check/drupal/d7_eol.py:13`
- Modify: `tests/unit/test_php_eol_notice.py:13-15` — move the module-level
  `SourceFileLoader(...).load_module()` into a **function-scoped fixture** (SPEC §2.3; without
  this, every later load of `php_eol.py` raises `DuplicateNoticeCodeError`)
- Test: `tests/unit/test_php_eol_notice.py`, `tests/integration/test_check_pantheon.py`,
  `test_pantheon_notice_render.py`, `test_check_wordpress.py`, `test_check_drupal.py`,
  `test_check_addon_updates.py`, `test_addon_updates_notice_render.py`

**Interfaces:**
- Consumes: `Notice`, `Severity`, `registry` (Task 1); `sc.wp_error` etc. already return
  `Notice`s after Task 2 — these hooks pass them straight to `add_notices`, unchanged.
- Produces: `build_php_eol_notice(site_name, php_version) -> Notice | None` (the only builder
  here called from outside its module — by `check/pantheon/php_eol.py`'s own hook and by
  `tests/unit/test_php_eol_notice.py`).

**Codes to register** (in the module that builds them):

| Module | Constant | Code |
|---|---|---|
| `check/addon_updates/table.py` | `NOTICE_UPDATES_ADDONS` | `updates-addons` |
| `check/pantheon/frozen.py` | `NOTICE_FROZEN` | `frozen` |
| `check/pantheon/live_env.py` | `NOTICE_NO_LIVE_ENV` | `no-live-env-but-paid-plan` |
| `check/pantheon/php_eol.py` | `NOTICE_PHP_EOL_WARNING`, `NOTICE_PHP_EOL_ALERT` | `php-eol-warning`, `php-eol-alert` |
| `check/pantheon/updates.py` | `NOTICE_UPDATES_INFO`, `NOTICE_UPDATES_WARNING`, `NOTICE_UPDATES_ALERT` | `updates-info`, `updates-warning`, `updates-alert` |
| `check/wordpress/favicon.py` | `NOTICE_NO_FAVICON` | `no-favicon` |
| `check/wordpress/ocp.py` | `NOTICE_OCP_CONFIG` | `ocp-config-fix-needed` |
| `check/drupal/d7_eol.py` | `NOTICE_DRUPAL7_EOL` | `drupal7-eol` |

Check modules import the type via the façade — `sc.Notice`, `sc.Severity` — per CAMPAIGN.md
§3.5 ("checks and plugins import **only** `sc`"). The registry is reached the same way:
**Task 6 adds `sc.registry`**, so in this task use `from psh.notice import registry` **only if**
`sc.registry` does not yet exist; otherwise `sc.registry.register(...)`. Decide once, in Task 3,
and use the same mechanism in Tasks 4 and 5 — see the note in Task 6, Step 1.

- [ ] **Step 1: Fix the module-level load in `tests/unit/test_php_eol_notice.py` (red first)**

Replace lines 13–15 with a function-scoped fixture:

```python
_PATH = Path(psh.__file__).resolve().parents[1] / "check" / "pantheon" / "php_eol.py"


@pytest.fixture
def build_php_eol_notice(reset_sc):     # function-scoped: the module registers notice codes at
    """Load check/pantheon/php_eol.py fresh per test.  MUST stay function-scoped and inside a
    test's reset_sc window -- a module-level load registers its codes before reset_sc snapshots
    the registry, and the next load then raises DuplicateNoticeCodeError (SPEC I14c §2.3)."""
    return SourceFileLoader("php_eol_for_unit_tests", str(_PATH)).load_module().build_php_eol_notice
```

and add `build_php_eol_notice` as a parameter to each test in the file. Run
`./run-tests --fast tests/unit/test_php_eol_notice.py tests/integration/test_check_pantheon.py`
— green before any conversion (this step is pure isolation-hardening).

- [ ] **Step 2: For each of the 11 producers — repoint its test to `Notice` fields (red)**

Only `build_php_eol_notice` is asserted through a builder return; the other 10 are asserted
through `site_context["notices"]` and need **no test change** (their `.ambr` and csv assertions
keep working). For `php_eol`, in `tests/unit/test_php_eol_notice.py`:

```python
    n = build_php_eol_notice("s", "8.1")
    assert n.code == "php-eol-warning"
    assert n.csv_extra == ()
    assert n.severity == "warning"
    assert "8.1" in n.html
```
and in `tests/integration/test_pantheon_notice_render.py:74-78`, `n["message"]` → `n.html` etc.

- [ ] **Step 3: Convert the 11 producers with the Task-2 recipe**

Every icon in this task is the severity default → **delete all 11 `icon` entries**. csv splits:

| Producer | `code=` | `csv_extra=` |
|---|---|---|
| `check/addon_updates/table.py` | `NOTICE_UPDATES_ADDONS` | `(str(num_updates),)` |
| `check/pantheon/frozen.py` | `NOTICE_FROZEN` | `()` |
| `check/pantheon/live_env.py` | `NOTICE_NO_LIVE_ENV` | `()` |
| `check/pantheon/php_eol.py` ×2 | `NOTICE_PHP_EOL_WARNING` / `_ALERT` | `()` |
| `check/pantheon/updates.py` ×3 | `NOTICE_UPDATES_INFO`/`_WARNING`/`_ALERT` | `(str(num_updates), str(oldest_update_days))` |
| `check/wordpress/favicon.py` | `NOTICE_NO_FAVICON` | `()` |
| `check/wordpress/ocp.py` | `NOTICE_OCP_CONFIG` | `()` |
| `check/drupal/d7_eol.py` | `NOTICE_DRUPAL7_EOL` | `()` |

`str(...)` on the numeric fields is required — `csv_extra` elements MUST already be strings
(SPEC §2.1). Confirm each `str()` reproduces today's f-string rendering exactly (integers do).

- [ ] **Step 4: Fast tier + evidence**

```bash
./run-tests --fast
python development/2026-07-24-mod-I14c-notice/tools/literal_equality.py <task-2-commit> \
    check/addon_updates/table.py check/pantheon/frozen.py check/pantheon/live_env.py \
    check/pantheon/php_eol.py check/pantheon/updates.py check/wordpress/favicon.py \
    check/wordpress/ocp.py check/drupal/d7_eol.py
git diff <task-2-commit> -- tests/e2e/__snapshots__/ '*.ambr'    # MUST be empty
```
Expected: green; `8/8 files with byte-identical notice literals`; both diffs empty; the
inventory's producer count drops 24 → 13. Paste one broken-csv red demo as in Task 2 Step 6.

- [ ] **Step 5: Commit**

```bash
git add check/ tests/
git commit -m "feat(campaign-I14c): convert the generic check/ notice producers to Notice"
```

---

### Task 4: convert the 7 dns / cloudflare / cdn-change producers

**Files:**
- Modify: `check/dns/notices.py:25,42,77,113,123`, `check/cloudflare/notices.py:397`,
  `check/pantheon_cdn_change/notices.py:197`
- Test: `tests/unit/test_dns_notices.py`, `tests/integration/test_dns_notice_render.py`,
  `tests/unit/test_cachecheck_consolidation.py`,
  `tests/integration/test_cachecheck_notice_render.py`,
  `tests/unit/test_pantheon_cdn_change_notices.py`,
  `tests/integration/test_pantheon_cdn_change_notice_render.py`,
  `tests/integration/test_check_dns.py`, `test_check_pantheon_cdn_change.py`
- Snapshot: `tests/integration/__snapshots__/test_dns_notice_render.ambr` — **the only sanctioned
  `.ambr` change in this increment** (7 entries, one added `'icon'` line each)

**Interfaces:**
- Consumes: `Notice`, `Severity`, the registry mechanism chosen in Task 3.
- Produces: `check/dns/notices.py`'s five builders and
  `check/pantheon_cdn_change/notices.py:build_cdn_change_notice` return `Notice`;
  `check/cloudflare/notices.py:build_cache_notices` returns `list[Notice]`.

**Codes to register:** `check/dns/notices.py` — `NOTICE_DNS_LOOKUP_FAILED`
(`dns-lookup-failed`), `NOTICE_NOT_IN_DNS` (`not-in-dns`), `NOTICE_NOT_BEHIND_CLOUDFLARE`
(`not-behind-cloudflare`), `NOTICE_BEHIND_CLOUDFLARE_NOT_PROXIED`
(`behind-cloudflare-not-proxied`), `NOTICE_PROXIED_IN_MULTIPLE_ZONES`
(`proxied-in-multiple-cloudflare-zones`); `check/cloudflare/notices.py` —
`NOTICE_CLOUDFLARE_CACHE` (`cloudflare-cache`); `check/pantheon_cdn_change/notices.py` —
`NOTICE_PANTHEON_CDN_CHANGE` (`pantheon-cdn-change`).

- [ ] **Step 1: Pin the empty-input behavior first (D-i14c-11), red**

Add to `tests/unit/test_dns_notices.py` (and the analogue to
`tests/unit/test_pantheon_cdn_change_notices.py`):

```python
def test_hostname_fields_become_separate_csv_fields(notices):
    n = notices.not_in_dns_notice("s", ["a.example.org", "b.example.org"])
    assert n.csv_extra == ("a.example.org", "b.example.org")


def test_empty_hostname_list_yields_no_csv_fields(notices):
    # Documented precondition (SPEC I14c §2.1): every call site guards a non-empty list
    # (check/dns/hook.py:26,30,33,36,40), so this case is unreachable today.  Pinned so the
    # divergence from the pre-I14c trailing comma is explicit rather than latent (PD#3).
    assert notices.not_in_dns_notice("s", []).csv_extra == ()
```

- [ ] **Step 2: Convert the 7 producers**

`csv_extra=tuple(hostnames)` for the five dns builders;
`csv_extra=tuple(f.fqdn for f in findings)` for cdn-change;
`csv_extra=("+".join(fqdns), "+".join(ids))` for cloudflare-cache. None of these seven sets an
`icon` today, so none sets one now. Add the precondition sentence to each builder's docstring:

```
    csv_extra is the hostname list as separate csv fields; callers guard against an empty list
    (check/dns/hook.py), and the empty case yields no trailing field -- unlike the pre-I14c
    string concatenation (SPEC I14c §2.1, D-i14c-11).
```

- [ ] **Step 3: Repoint the two `dict(...)`-copy call sites**

`tests/integration/test_cachecheck_notice_render.py:70,81` and
`test_pantheon_cdn_change_notice_render.py:52,62` do `ctx.add_notice(dict(built))` — the copy
existed because `add_notice` mutated its dict argument. A `Notice` is frozen, so:
`ctx.add_notice(built)`. Their `.ambr` files MUST NOT change.

- [ ] **Step 4: Convert the 7 whole-dict dns snapshots to the projection**

In `tests/integration/test_dns_notice_render.py`, each assertion becomes:

```python
def test_not_in_dns_render(dns_notices, reset_sc, snapshot):
    ctx = reset_sc.SiteContext({"name": "s"})
    assert ctx.notice_to_dict(dns_notices.not_in_dns_notice("s", HOSTS)) == snapshot
```

Run `./run-tests --fast tests/integration/test_dns_notice_render.py` — expect 7 snapshot
mismatches, each **only** an added `'icon'` line. Inspect the diff, then refresh **only this
file**:

```bash
./run-tests --update-goldens tests/integration/test_dns_notice_render.py
git diff -- tests/integration/__snapshots__/test_dns_notice_render.ambr
```
The diff MUST be exactly 7 added lines, all of the form `    'icon': '&#x…;',`. Paste it into the
task report. **If any other line changes, STOP** — that is a defect, not a refresh (Invariant 1's
rule applied to the sanctioned exception).

- [ ] **Step 5: Fast tier + evidence + commit**

```bash
./run-tests --fast
python development/2026-07-24-mod-I14c-notice/tools/literal_equality.py <task-3-commit> \
    check/dns/notices.py check/cloudflare/notices.py check/pantheon_cdn_change/notices.py
git diff <task-3-commit> -- tests/e2e/__snapshots__/     # MUST be empty
git diff <task-3-commit> -- '*.ambr'                     # MUST be the 7 icon lines only
git add check/ tests/ && git commit -m "feat(campaign-I14c): convert the dns/cloudflare/cdn-change notice producers"
```
Producer count: 13 → 6.

---

### Task 5: convert the 6 `check/umich/` producers

**Files:**
- Modify: `check/umich/annual_billing.py:23` (+ its hook at `:101`), `check/umich/drupal_ua.py:79`,
  `check/umich/hummingbird.py:36,47`, `check/umich/oidc_login.py:23`, `check/umich/sitelens.py:106`
- Test: `tests/unit/test_annual_billing_notices.py`,
  `tests/integration/test_check_umich_annual_billing.py`, `test_check_umich_wp.py`,
  `test_check_umich_drupal_ua.py`, `test_check_sitelens.py`, and the three `*_notice_render.py`
  files for umich

**Interfaces:**
- Consumes: `Notice`, `Severity`, the registry mechanism from Task 3, and
  `SiteContext.notice_to_dict` (Task 1) — used by the billing hook.
- Produces: `build_annual_bill_upcoming_notice(...) -> Notice`; the
  `annual_bill_upcoming` **site_context key keeps its render-dict type** (SPEC §2.5), so
  `sort_notices_and_subject` and every consumer are untouched.

**Codes to register:** `NOTICE_ANNUAL_BILL` (`annual-bill`), `NOTICE_DRUPAL_UA` (`drupal-ua`),
`NOTICE_UNSUPPORTED_TURNED_OFF` (`unsupported-turned-off`), `NOTICE_UNSUPPORTED` (`unsupported`),
`NOTICE_UMICH_OIDC_LOGIN_REINSTALL` (`umich-oidc-login-reinstall`), `NOTICE_SITELENS_URL_PATHS`
(`sitelens-url-paths`).

- [ ] **Step 1: Add the missing `sitelens-url-paths` csv pin (red)**

`sitelens-url-paths` is the only code in the program with **no** csv assertion anywhere in the
suite (SPEC §4). Add to `tests/integration/test_check_sitelens.py`, beside the existing
`test_urls_notice_when_too_few_paths`:

```python
def test_urls_notice_csv_row(sitelens, reset_sc):
    ctx = reset_sc.SiteContext({"name": "bus-occb"})
    sitelens.check_url_paths(ctx, _score(90, 90, 90, 90, cfg_id=7), num_paths_configured=1)
    assert ctx["notices"][0]["csv"] == "bus-occb,sitelens-url-paths,1"
```
(Adjust the call to match the module's actual entry point and arguments — read
`check/umich/sitelens.py:88-110` first; the assertion on the csv row is what matters.) Run it
against the **unconverted** module first: it MUST pass, establishing the pre-conversion value.

- [ ] **Step 2: Convert the 6 producers**

`csv_extra` per producer: annual-bill `(f"{annual_bill}", shortcode)` — **check the current
f-string's rendering of `annual_bill` and reproduce it exactly** (`{annual_bill}` today, so
`str(annual_bill)`); drupal-ua `(ua["result"],)`; hummingbird ×2 `(name,)`; oidc `()`;
sitelens `(str(num_paths_configured),)`.
**`annual_billing.py` is the one producer that KEEPS `icon="&#x1F4B5;"`** (SPEC §2.4 #30) —
every other icon here is the severity default and is deleted.

- [ ] **Step 3: Wire the billing hook through the projection**

`check/umich/annual_billing.py:101` becomes:

```python
    site_context["annual_bill_upcoming"] = site_context.notice_to_dict(
        build_annual_bill_upcoming_notice(site_name, plan_name, annual_bill, shortcode,
                                          portal_site_id))
```
and the module docstring gains one sentence: *"The builder returns a Notice; the hook publishes
the PROJECTED render dict, so the produced key's type and every consumer
(`sort_notices_and_subject`) are unchanged (SPEC I14c §2.5)."* `tests/unit/
test_annual_billing_notices.py` repoints to `Notice` fields; `tests/integration/
test_check_umich_annual_billing.py` (which reads the produced key) MUST need **no** change —
that is the proof the wiring is right.

- [ ] **Step 4: Fast tier + evidence + commit**

```bash
./run-tests --fast
python development/2026-07-24-mod-I14c-notice/tools/literal_equality.py <task-4-commit> \
    check/umich/annual_billing.py check/umich/drupal_ua.py check/umich/hummingbird.py \
    check/umich/oidc_login.py check/umich/sitelens.py
git diff <task-4-commit> -- tests/e2e/__snapshots__/ '*.ambr'    # MUST be empty
python development/2026-07-24-mod-I14c-notice/tools/notice_inventory.py --gate; echo "exit=$?"
git add check/ tests/ && git commit -m "feat(campaign-I14c): convert the check/umich notice producers"
```
Expected: `--gate` now exits **0** (zero dict producers left) — the first time in the increment.

---

### Task 6: retire the dict form, pin the roster, update the docs

**Files:**
- Modify: `script_context.py` (`add_notice` → `Notice`-only; `add_notices` annotation)
- Modify: `psh/notice.py` (docstring: the dict form is gone), `tests/unit/test_site_context.py`,
  `tests/unit/test_add_notice_from_notice.py`
- Create: `tests/integration/test_notice_roster.py`
- Modify: `CLAUDE.md` (the Notices-vs-news bullet + the `sc` façade list),
  `development/2026-07-17-modularization-campaign/LEDGER.md` (the I14c entry, including the
  "22 → 28" correction owed by SPEC §7)

**Interfaces:**
- Consumes: everything from Tasks 1–5.
- Produces: `add_notice(notice: Notice) -> None` raising `TypeError` on anything else;
  `sc.registry` if Task 3 chose the façade mechanism.

- [ ] **Step 1: Decide and land the façade name for the registry**

If Tasks 3–5 used `from psh.notice import registry` inside `check/` modules, add
`registry` to `script_context.py`'s top-of-file `from psh.notice import Notice, Severity`
import (making it `sc.registry` automatically, the I3 mechanism — LEDGER I3 deviation 3) and
repoint those check modules to `sc.registry.register(...)`, so CAMPAIGN.md §3.5's
"checks and plugins import **only** `sc`" holds. Add `sc.registry` to CLAUDE.md's documented
façade list, which `test_documented_sc_facade_names_exist` pins.

- [ ] **Step 2: Write the roster test (red)**

`tests/integration/test_notice_roster.py`:

```python
"""The notice-code roster: every code the program can emit, registered exactly once.

Codes are registered at module import (campaign I14c), so this test loads every check/ and
plugin/ package with everything enabled -- check/umich and check/cloudflare import their
producing submodules only inside their `enabled` guards -- and compares the registry against
the frozen roster.  A new notice code MUST be added here deliberately; a duplicate cannot get
this far, because registry.register() raises DuplicateNoticeCodeError at import.
"""
ROSTER = frozenset({
    "no-domains", "no-primary-domain", "wp-error", "drush-error", "not-installed",
    "multiple-installed", "turned-off", "composer-update", "wp-smell", "drush-smell",
    "composer-smell", "its-recommends-plan", "updates-addons", "cloudflare-cache",
    "dns-lookup-failed", "not-in-dns", "not-behind-cloudflare", "behind-cloudflare-not-proxied",
    "proxied-in-multiple-cloudflare-zones", "drupal7-eol", "frozen", "no-live-env-but-paid-plan",
    "php-eol-warning", "php-eol-alert", "updates-info", "updates-warning", "updates-alert",
    "pantheon-cdn-change", "annual-bill", "drupal-ua", "unsupported-turned-off", "unsupported",
    "umich-oidc-login-reinstall", "sitelens-url-paths", "no-favicon", "ocp-config-fix-needed",
})


def test_roster_is_exactly_the_registered_codes(psh, reset_sc, request):
    reset_sc.config = EVERYTHING_ENABLED          # same shape test_hook_dag.py uses
    for base, package, probe in ALL_PACKAGES:     # import it from tests/integration/test_hook_dag.py
        load_check_package(psh, package, probe, request, base=base)
    assert registry.codes() == ROSTER
```
Expected count: **36**. Run it — it must fail if you got the roster wrong, which is the point.

- [ ] **Step 3: Retire the dict form**

```python
    def add_notice(self, notice: Notice) -> None:
        """Add a Notice, honoring order ('prepend'/'first' -> front).

        Notice-only since campaign I14c (CAMPAIGN.md §6): the legacy hand-built dict is gone
        from every producer, so a dict here is a programming error, not a supported form.
        """
        if not isinstance(notice, Notice):
            raise TypeError(
                f"add_notice() takes a psh.notice.Notice, not {type(notice).__name__}: {notice!r}"
            )
        d = self.notice_to_dict(notice)
        if notice.order in ('prepend', 'first'):
            self['notices'].insert(0, d)
        else:
            self['notices'].append(d)

    def add_notices(self, notices: list[Notice]) -> None:
        """Add each Notice returned by a builder (wp_error/drush_error/check_*module)."""
```

`sys` may become unused in `script_context.py` — check (`add_news_item` still calls
`sys.exit`, so it most likely stays) and remove only what this change orphans.

- [ ] **Step 4: Rewrite the two tests the retirement invalidates**

`tests/unit/test_site_context.py:89`:

```python
def test_add_notice_rejects_a_dict(reset_sc):
    ctx = reset_sc.SiteContext({"name": "x"})
    with pytest.raises(TypeError, match="psh.notice.Notice"):
        ctx.add_notice({"type": "info", "message": "<p>x</p>"})
```
and its remaining `_n()`-dict `add_notice` calls (lines 31, 36, 40, 55, 75, 83, 92, 97, 98, 104)
become `Notice(...)` constructions with the same values.

`tests/unit/test_add_notice_from_notice.py:9-21` — replace the dict-fed comparison arm with a
frozen expected dict (instrument I5):

```python
def test_notice_projects_to_the_render_dict():
    ctx = sc.SiteContext({"name": "s1"})
    ctx.add_notice(Notice(severity=Severity.ALERT, code="no-domains",
                          short="no domains connected", html="<p>hi</p>", text="hi"))
    assert ctx["notices"][0] == {
        "type": "alert", "icon": "&#x1F6A8;", "csv": "s1,no-domains",
        "short": "no domains connected", "message": "<p>hi</p>", "text": "hi",
    }
```

- [ ] **Step 5: Full suite, both gates, and the close gates**

```bash
./run-tests                       # live tier if ~/.terminus/cache/tokens/ has a token
python development/2026-07-24-mod-I14c-notice/tools/notice_inventory.py --gate; echo "exit=$?"
python development/2026-07-24-mod-I14c-notice/tools/literal_equality.py 982589f \
    $(git diff --name-only 982589f -- 'psh/*.py' 'check/**/*.py')
git diff 982589f -- tests/e2e/__snapshots__/    # MUST be empty
git diff 982589f -- '*.ambr'                    # MUST be the 7 dns icon lines only
```
Expected: full suite green (1023 + the new tests); `--gate` exit 0; `literal_equality` reporting
every touched file identical; goldens untouched.

- [ ] **Step 6: Docs, ledger, memory**

- `CLAUDE.md` — the "Notices vs. news" bullet: `add_notice` takes a `Notice` **only**; the render
  dict is the storage form produced by `SiteContext.notice_to_dict`; `csv_extra` carries the
  extra csv fields; codes are registered at import and pinned by
  `tests/integration/test_notice_roster.py`; drop the "a notice with extra csv fields stays a
  dict until the increment that adopts it" sentence, which I14c discharges. Add `sc.registry` to
  the façade list if Step 1 added it.
- `LEDGER.md` — the I14c entry per CAMPAIGN.md §12's template, including: the 7-line `.ambr`
  diff (pasted), the "22 → 28" correction to the §6 amendment entry, the `test_php_eol_notice.py`
  load-isolation fix, and the `check_drupal_module` alert-icon latent bug closed.
- Memory — update `config-and-notice-modules.md` (or add a `notice-dict-retired.md`) with the
  durable fact: producers construct `Notice`; `add_notice` rejects dicts; codes are registered at
  import and the registry is restored per test by `reset_sc`.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(campaign-I14c): retire the notice dict form; pin the 36-code roster"
```

---

## Self-review against the SPEC

- **Deliverable A** → Task 1 Steps 1–3. **B** → Task 1 Steps 1, 4. **C** → Task 1 Steps 3, 5 +
  the per-task code tables + Task 6 Steps 1–2. **D** → Tasks 2–5 (13 + 11 + 7 + 6 = 37).
  **E** → Task 6 Steps 3–4. **F** → Task 6 Step 6.
- **Instruments:** I1 every task; I2a Tasks 2–5 + Task 6 Step 5; I3 Tasks 2–5 (red demo);
  I3g Tasks 4–6; I4 Task 6 Step 2; I5 Task 6 Step 4; I6 Task 1 Step 1.
- **SPEC §5(4)** (deleted/rewritten tests) → Task 6 Step 4. **SPEC §2.3's load rule** →
  Task 3 Step 1. **SPEC §2.5** → Task 5 Step 3. **D-i14c-11** → Task 4 Step 1.
  **SPEC §4's `sitelens-url-paths` gap** → Task 5 Step 1. **SPEC §7's ledger correction** →
  Task 6 Step 6.
- **Names used consistently across tasks:** `notice_to_dict`, `csv_extra`, `snapshot`/`restore`,
  `NOTICE_<CODE>` constants, `operation` (the renamed `wp_error`/`drush_error` parameter).

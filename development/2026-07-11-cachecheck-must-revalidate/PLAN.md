# Cachecheck must-revalidate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the Cloudflare cache check's handling of `must-revalidate` / `proxy-revalidate` — neither prevents caching, so replace the three places that assume they do with one accurate result item.

**Architecture:** `check/cloudflare/headers.py` is the pure per-URL header battery (no I/O); `check/cloudflare/notices.py` turns its result items into owner-facing HTML with U-M and generic language variants. Detection changes in the former, wording in the latter, and the two registries (`_MISS_RETRY_BLOCKERS`, `_CONSOLE`) lose their `cc-proxy-revalidate` entry. The item id `cc-must-revalidate` is kept and now carries the directive actually seen in `params["directive"]`.

**Tech Stack:** Python 3.13, pytest (marks: `unit`, `integration`), Hypothesis, syrupy snapshots. Run tests with `./run-tests --fast`.

**Read `SPEC.md` in this folder first** — in particular the "Cloudflare-specific verification" section, which is what makes the notice text defensible, and the exhaustive 7-rule detection list.

## Global Constraints

- Both modules are loaded **standalone** by the tests via `SourceFileLoader` — they MUST NOT import the dash-named main script. Do not add imports to either file.
- **Tests are load-bearing.** The e2e goldens run with `[Cloudflare].enabled = false` (`tests/fixtures/config/minimal.toml:86`), so they MUST remain byte-identical. If `./run-tests --fast` shows a golden diff, something is wrong — **never** regenerate a golden to make a failure go away. Snapshot regeneration (`--update-goldens`) applies only to `tests/integration/__snapshots__/` here, and its diff must be read before committing.
- Consolidation identity is `(id, kind, params)` (`notices.py:304-306`). Putting the directive in `params` is what keeps the two directives' findings from merging into each other.
- Notice text is identical for U-M and generic; the variants differ **only in links**.
- The removal advice is **unconditional**. NEVER write "unless this page has a strict freshness requirement".
- Every notice's csv key stays `cloudflare-cache`. Do not add a new one.
- `params["directive"]` is always one of two **code literals** — never the raw header value. Do not "fix" this by passing the header through.

---

### Task 1: Detection — one directive-agnostic item, and fix the MISS-retry blockers

**Files:**
- Modify: `check/cloudflare/headers.py:18-19` (the two docstring lines), `:33-39` (`_MISS_RETRY_BLOCKERS` + its comment), `:129` (the `is_main_page` note), `:153-162` (the directive checks)
- Test: `tests/unit/test_cachecheck_headers.py:92-103` (replace), `:230-241` (extend)

**Interfaces:**
- Consumes: `_item(item_id, kind, **params)` and `evaluate_headers(headers, *, is_main_page, kind, now, status_code) -> list` — both already exist in `headers.py`.
- Produces: result item `{"id": "cc-must-revalidate", "kind": ..., "params": {"directive": "must-revalidate" | "proxy-revalidate"}}`. Task 2 renders it and depends on that exact params key always being present. The id `cc-proxy-revalidate` is **retired** and MUST NOT be emitted.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_cachecheck_headers.py`, **replace** `test_bad_directives_each_flagged` (currently :92-96) and `test_must_revalidate_ok_on_main_page_flagged_elsewhere` (currently :99-103) with:

```python
def _directive(items):
    return [i["params"].get("directive") for i in items if i["id"] == "cc-must-revalidate"]


def test_bad_directives_each_flagged(hdrs):
    # proxy-revalidate is NOT bucketed with the caching-hostile directives any more, and the
    # revalidate item is suppressed here because the response is already uncacheable.
    headers = {"cf-cache-status": "HIT",
               "cache-control": f"private, no-cache, no-store, proxy-revalidate, {YEAR}"}
    assert ids(run(hdrs, headers)) == ["cc-no-cache", "cc-no-store", "cc-private"]


def test_must_revalidate_flagged_everywhere_including_main_page(hdrs):
    headers = {"cf-cache-status": "HIT", "cache-control": f"must-revalidate, {YEAR}"}
    for kwargs in ({"main": True}, {"main": False}, {"kind": "asset"}):
        items = run(hdrs, headers, **kwargs)
        assert ids(items) == ["cc-must-revalidate"], kwargs
        assert _directive(items) == ["must-revalidate"], kwargs


def test_proxy_revalidate_shares_the_item_and_names_itself(hdrs):
    headers = {"cf-cache-status": "HIT", "cache-control": f"proxy-revalidate, {YEAR}"}
    items = run(hdrs, headers)
    assert ids(items) == ["cc-must-revalidate"]
    assert _directive(items) == ["proxy-revalidate"]


def test_both_revalidate_directives_yield_one_item_naming_must_revalidate(hdrs):
    headers = {"cf-cache-status": "HIT",
               "cache-control": f"must-revalidate, proxy-revalidate, {YEAR}"}
    items = run(hdrs, headers)
    assert ids(items) == ["cc-must-revalidate"]
    assert _directive(items) == ["must-revalidate"]


def test_must_revalidate_flagged_without_max_age(hdrs):
    # Previously silent: the directive check sat inside the max-age branch.
    items = run(hdrs, {"cf-cache-status": "HIT", "cache-control": "must-revalidate"})
    assert ids(items) == ["cc-must-revalidate", "no-max-age"]


@pytest.mark.parametrize("blocker", ["private", "no-cache", "no-store"])
def test_revalidate_item_suppressed_on_an_uncacheable_response(hdrs, blocker):
    # Content Cloudflare never caches cannot go stale, so the stale-content risk the notice
    # describes cannot arise.
    items = run(hdrs, {"cf-cache-status": "HIT",
                       "cache-control": f"{blocker}, must-revalidate, {YEAR}"})
    assert ids(items) == [f"cc-{blocker}"]


def test_suppression_keys_off_the_header_not_the_emitted_item(hdrs):
    # cc-private is only emitted once a max-age parses, so here NEITHER directive produces an
    # item.  Suppression still applies: the page is uncacheable whether or not we emitted a
    # finding saying so, and no-max-age already tells the owner to configure caching.
    items = run(hdrs, {"cf-cache-status": "HIT", "cache-control": "private, must-revalidate"})
    assert ids(items) == ["no-max-age"]
```

Finally, fix a now-false comment at `:75-76`, which currently reads:

```python
    # no-max-age fires and the remaining CC rules are skipped (note: 'private' present
    # but not flagged -- the directive rules only run once a cache time parses).
```

Replace with:

```python
    # no-max-age fires and the private/no-cache/no-store rules are skipped (they only run
    # once a cache time parses).  The revalidate rule is the exception -- it runs regardless;
    # see test_must_revalidate_flagged_without_max_age.
```

Then in `test_retry_miss_matrix` (at :230), **add** this immediately after the existing `must-revalidate` assertion at :237-239:

```python
    # Neither revalidate directive prevents caching, so neither explains a MISS -- both must
    # still be retried (cc-proxy-revalidate in _MISS_RETRY_BLOCKERS used to wrongly suppress
    # this):
    assert check({"cf-cache-status": "MISS",
                  "cache-control": f"proxy-revalidate, {YEAR}"}) is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `rtk proxy python -m pytest tests/unit/test_cachecheck_headers.py -q`

Expected: FAIL. Specifically — `test_bad_directives_each_flagged` fails because old code also emits `cc-proxy-revalidate`; `test_must_revalidate_flagged_everywhere_including_main_page` fails on `main=True` (old code returns `[]`); `test_proxy_revalidate_shares_the_item_and_names_itself` fails with `["cc-proxy-revalidate"]`; `test_must_revalidate_flagged_without_max_age` fails with `["no-max-age"]` only; `test_revalidate_item_suppressed_on_an_uncacheable_response` fails (old code emits `cc-must-revalidate` alongside `cc-private`); `test_retry_miss_matrix` fails on the new assertion (old code returns `False`).

**One exception:** `test_suppression_keys_off_the_header_not_the_emitted_item` **passes against the old code too** — old code skipped every directive rule without a `max-age`, so it also produced just `["no-max-age"]`. It is a *characterization* test, pinning behavior the change must preserve, not a red test. Do not "fix" it when it fails to fail.

- [ ] **Step 3: Fix the MISS-retry blocker set**

In `check/cloudflare/headers.py`, replace the `_MISS_RETRY_BLOCKERS` set (currently :35-39, including its preceding comment at :33-34):

```python
# Items that make a MISS expected rather than mysterious; any of these suppresses the
# MISS-retry protocol (http-error because testing already stopped on that URL).
# NOTE: no revalidate directive belongs here -- must-revalidate/proxy-revalidate do not
# prevent Cloudflare from caching, so they never explain a MISS.
_MISS_RETRY_BLOCKERS = {
    "http-error", "no-cache-control", "no-max-age", "short-cache-time",
    "cc-private", "cc-no-cache", "cc-no-store",
    "set-cookie", "set-cookie-bypass",
}
```

- [ ] **Step 4: Replace the directive checks**

The directive checks currently sit **inside** the `else:` branch of the `cc_value is None` / `seconds is None` chain (:153-162). Only the **revalidate** check moves out — `private`/`no-cache`/`no-store` stay inside the branch, exactly as today. (Hoisting those too would be a real behavior change this spec did not approve: `Cache-Control: no-store` with no `max-age` would start reporting `cc-no-store` where today it reports only `no-max-age`. Arguably a bug; out of scope — leave it.)

Replace lines :153-162 with:

```python
    else:
        if seconds < MIN_CACHE_SECONDS:
            items.append(_item("short-cache-time", kind, seconds=seconds))
        for directive in ("private", "no-cache", "no-store"):   # proxy-revalidate removed
            if directive in cc:
                items.append(_item(f"cc-{directive}", kind))

    # Outside the max-age branch on purpose: these directives matter whenever they are
    # present, even with no parseable cache time (that case used to be silent).
    #
    # must-revalidate and proxy-revalidate are the same thing to Cloudflare (a shared cache).
    # Neither prevents caching; both mean that once the content is stale and the origin is
    # unreachable, visitors get an error instead of a stale copy.  must-revalidate is the
    # superset, so when both are present we report it alone rather than emitting two
    # near-identical items for one URL.  Suppressed on an uncacheable response: content
    # Cloudflare never caches cannot go stale, so the risk cannot arise.
    uncacheable = any(d in cc for d in ("private", "no-cache", "no-store"))
    revalidate = ("must-revalidate" if "must-revalidate" in cc
                  else "proxy-revalidate" if "proxy-revalidate" in cc
                  else None)
    if revalidate and not uncacheable:
        items.append(_item("cc-must-revalidate", kind, directive=revalidate))
```

No `cc_value is not None` guard is needed: `parse_cache_control(None)` returns an empty dict (`headers.py:82-83`), so every `in cc` test is already False when the header is absent.

- [ ] **Step 5: Mark `is_main_page` as reserved**

`is_main_page` is now **unused by the battery** — `headers.py:159` was its only reader, and `cache.py:120,147,185,199,218` merely thread it. Keeping the parameter is a deliberate right-sized-diff call, so say so or a linter will delete it.

The parameter sits mid-signature (`def evaluate_headers(headers: dict, *, is_main_page: bool, kind: str,` at `headers.py:129`), so the note cannot go "above" it. Put it as the **first lines of the function body**, immediately after the existing docstring that ends at `:132`, before `items = []`:

```python
    # is_main_page is a reserved seam: no rule currently consults it.  (The must-revalidate
    # main-page carve-out that used to read it was retired -- see
    # development/2026-07-11-cachecheck-must-revalidate/SPEC.md.)  Removing it end-to-end
    # through cache.py is a separate cleanup.
```

- [ ] **Step 6: Update the module docstring**

In `check/cloudflare/headers.py`, the docstring contains these two lines at :18-19:

```
                       private/no-cache/no-store/proxy-revalidate → one item each
                       must-revalidate → item on non-main pages only
```

Replace those two lines with:

```
                       private/no-cache/no-store → one item each
                       must-revalidate/proxy-revalidate → one cc-must-revalidate item naming
                       the directive seen, on every page and asset, but suppressed when the
                       response is already uncacheable (private/no-cache/no-store)
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `rtk proxy python -m pytest tests/unit/test_cachecheck_headers.py -q`
Expected: PASS (whole file).

- [ ] **Step 8: Commit**

```bash
git add check/cloudflare/headers.py tests/unit/test_cachecheck_headers.py
git commit -m "fix(cachecheck): revalidate directives do not prevent caching

must-revalidate and proxy-revalidate are the same thing to Cloudflare (a
shared cache) and neither stops it caching -- they change only what happens
once content is stale.  Emit one directive-agnostic cc-must-revalidate item
naming the directive seen, on every page and asset (the main-page exemption
existed only because the notice wrongly said to remove it), firing whenever
the directive is present rather than only when a max-age parsed, and
suppressed when the response is already uncacheable.

Retire cc-proxy-revalidate, including its entry in _MISS_RETRY_BLOCKERS: a
MISS alongside proxy-revalidate is genuinely unexplained, so it must be
retried, not suppressed."
```

---

### Task 2: Notice text

**Files:**
- Modify: `check/cloudflare/notices.py:56-77` (`_CONSOLE`), `:209-233` (the `_item_html` branches)
- Test: `tests/unit/test_cachecheck_consolidation.py:277-279` and `:321-328` (both loops), `:296-318` (replace the test); `tests/integration/test_cachecheck_notice_render.py` (snapshots)

**Interfaces:**
- Consumes: result items from Task 1 — `{"id": "cc-must-revalidate", "params": {"directive": ...}}`.
- Produces: no new symbols. `_CONSOLE["cc-must-revalidate"]` gains a `{directive}` format field; it is rendered via `_CONSOLE[item["id"]].format(**item["params"])` (`notices.py:81`), so the params key must match exactly. The branch reads `p["directive"]` **without a default** — a missing key MUST raise, not silently degrade.

- [ ] **Step 1: Fix ALL FOUR existing item-id tables**

**The invariant:** `cc-must-revalidate` now has a required format field. Any table that enumerates item ids and supplies params **must** supply `{"directive": ...}` for it, or both `console_line` (`_CONSOLE[...].format(**params)`, `notices.py:81`) and `_item_html` (`p["directive"]`, no default) raise `KeyError`. This is deliberate — a missing key is a broken item contract and must fail loudly, not silently degrade. Two of the four tables below iterate `for item_id in notices._CONSOLE`, so they pick up the new field automatically and **will** break unless fixed.

There are **four** such tables in `tests/unit/test_cachecheck_consolidation.py` — at `:277`, `:321`, `:370`, and `:436`. Fix all four; missing any one leaves a red suite.

**Table 3 — `_all_item_messages` (`:368-378`)** and **table 4 — `test_every_item_id_has_console_and_html_language` (`:436-445`)** both build `params_by_id` and then loop over `notices._CONSOLE`. In **each** of those two `params_by_id` dicts, add the entry:

```python
        "cc-must-revalidate": {"directive": "must-revalidate"},
```

(Leave the rest of both dicts alone. These two tables are what make `test_notice_html_has_no_raw_non_ascii_characters`, `test_console_lines_are_pure_ascii`, `test_plaintext_conversion_decodes_entities_for_screen_readers`, and `test_every_item_id_has_console_and_html_language` pass.)

**Table 1 — the site-wide-suffix loop (`:277-279`)** currently reads:

```python
    params_by_id = {"short-cache-time": {"seconds": 60}}
    for item_id in ("no-cache-control", "no-max-age", "short-cache-time", "cc-private",
                    "cc-no-cache", "cc-no-store", "cc-proxy-revalidate", "expires-short"):
```

Replace with (retire `cc-proxy-revalidate`; `cc-must-revalidate` now **carries** the suffix):

```python
    params_by_id = {"short-cache-time": {"seconds": 60},
                    "cc-must-revalidate": {"directive": "must-revalidate"}}
    for item_id in ("no-cache-control", "no-max-age", "short-cache-time", "cc-private",
                    "cc-no-cache", "cc-no-store", "cc-must-revalidate", "expires-short"):
```

**Table 2 — `test_location_specific_items_are_not_given_the_site_wide_direction` (`:321-328`)** currently reads:

```python
def test_location_specific_items_are_not_given_the_site_wide_direction(notices):
    # cc-must-revalidate is deliberately about WHERE the directive appears (intentional on
    # the home page), and the transport/status items are about the listed URLs themselves.
    for item_id, params in (("cc-must-revalidate", {}), ("http-error", {"status": 404}),
                            ("timeout", {"timeout": 5}), ("invalid-cert", {})):
```

Replace the comment and drop `cc-must-revalidate` (it is now a site-config item, not a location-specific one — that whole rationale is what this change retires):

```python
def test_location_specific_items_are_not_given_the_site_wide_direction(notices):
    # The transport/status items are about the listed URLs themselves, not about a site-wide
    # configuration, so they must not carry the "apply this site-wide" direction.
    for item_id, params in (("http-error", {"status": 404}),
                            ("timeout", {"timeout": 5}), ("invalid-cert", {})):
```

- [ ] **Step 2: Write the failing tests**

In the same file, **replace** `test_must_revalidate_umich_names_its_referent_and_trails_the_home_page_caveat` (currently :296-318) with:

```python
def test_must_revalidate_states_the_stale_risk_and_says_remove_it(notices):
    def message(count, kind="page", directive="must-revalidate", umich=True):
        items = [_item("cc-must-revalidate", f"https://a.example.edu/p{i}", kind=kind,
                       directive=directive)
                 for i in range(count)]
        return _build(notices, {"a.example.edu": items}, umich=umich)[0]["message"]

    one = message(1)
    assert "<code>must-revalidate</code>" in one
    assert "You should remove it" in one
    assert "no effect until this page goes stale" in one
    assert "visitors will get errors rather than a stale copy of this page." in one

    # Number agreement with the URL list rendered below the sentence:
    two = message(2)
    assert "no effect until these pages go stale" in two
    assert "visitors will get errors rather than stale copies of these pages." in two
    assert "these static assets" in message(2, kind="asset")

    # The notice names the directive actually seen.  NOTE: assert on the <code> span, not the
    # bare string -- the U-M variant's "How to fix this" link is {doc_url}#cc-must-revalidate,
    # so the raw substring "must-revalidate" appears in EVERY U-M message.
    proxy = message(1, directive="proxy-revalidate")
    assert "<code>proxy-revalidate</code>" in proxy
    assert "<code>must-revalidate</code>" not in proxy

    # The old, wrong language is gone from BOTH variants:
    for msg in (one, message(1, umich=False)):
        assert "defeats caching" not in msg
        assert "reduces caching benefit" not in msg
        assert "strict freshness requirement" not in msg
        assert "home page" not in msg
        assert "emergency" not in msg


def test_revalidate_directives_do_not_consolidate_into_each_other(notices):
    # Consolidation identity is (id, kind, params), so the differing directive keeps them
    # apart even though they share an item id.
    items = [_item("cc-must-revalidate", "https://a.example.edu/a", directive="must-revalidate"),
             _item("cc-must-revalidate", "https://a.example.edu/b", directive="proxy-revalidate")]
    message = _build(notices, {"a.example.edu": items})[0]["message"]
    assert "<code>must-revalidate</code>" in message
    assert "<code>proxy-revalidate</code>" in message
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `rtk proxy python -m pytest tests/unit/test_cachecheck_consolidation.py -q`
Expected: FAIL — `test_must_revalidate_states_the_stale_risk_and_says_remove_it` fails on `"You should remove it"` (old text: "which defeats caching. Configure your site to remove it from …"), and the site-wide loop fails for `cc-must-revalidate` (old text has no `sitewide` suffix).

- [ ] **Step 4: Update the console summary map**

In `check/cloudflare/notices.py` `_CONSOLE` (:56-77), **delete**:

```python
    "cc-proxy-revalidate": "Cache-Control contains proxy-revalidate",
```

and **replace**:

```python
    "cc-must-revalidate": "Cache-Control contains must-revalidate (non-main page)",
```

with:

```python
    "cc-must-revalidate": "Cache-Control contains {directive}",
```

- [ ] **Step 5: Rewrite the notice branches**

Line :209 currently reads:

```python
    elif item_id in ("cc-private", "cc-no-cache", "cc-no-store", "cc-proxy-revalidate"):
```

Change it to:

```python
    elif item_id in ("cc-private", "cc-no-cache", "cc-no-store"):
```

Then **replace** the whole `cc-must-revalidate` branch (:216-233 — both the U-M and generic arms) with:

```python
    elif item_id == "cc-must-revalidate":
        # Same text for both variants; only the link differs.  No "unless you have a strict
        # freshness requirement" escape hatch: a real freshness requirement is met by purging
        # the stale copy, never by must-revalidate.  p["directive"] is always supplied by
        # headers.py -- a KeyError here means a caller broke the item contract.
        directive = html.escape(str(p["directive"]))
        text = (f"{possessive} <code>Cache-Control</code> {contains_hdr} "
                f"<code>{directive}</code>. You should remove it since it has no effect "
                f"until {object_} {'go' if many else 'goes'} stale, and if Cloudflare "
                f"can't reach your web server at that time, visitors will get errors "
                f"rather than {'stale copies' if many else 'a stale copy'} of {object_}."
                + sitewide)
        links = [learn] if umich else [_a(MDN_CACHE_CONTROL, "About the Cache-Control header")]
```

- [ ] **Step 6: Run the unit tests to verify they pass**

Run: `rtk proxy python -m pytest tests/unit/test_cachecheck_consolidation.py -q`
Expected: PASS (whole file).

- [ ] **Step 7: Add render cases for BOTH directives and refresh the snapshots**

**There is currently no revalidate item in the render tier at all** (`grep -rn revalidate tests/integration/` returns zero hits), so this step *adds* coverage rather than editing an existing case. The snapshotted items come from one shared list — `tests/integration/test_cachecheck_notice_render.py:43-49`:

```python
def _representative_items(fqdn):
    return [
        _item("set-cookie-bypass", f"https://{fqdn}/"),
        _item("short-cache-time", f"https://{fqdn}/about", seconds=3600),
        _item("miss-persistent", f"https://{fqdn}/js/app.js", kind="asset"),
        _item("invalid-cert", f"https://{fqdn}/img/logo.png", kind="asset"),
    ]
```

Append both directives so the snapshots cover the U-M and generic wording of each:

```python
        _item("cc-must-revalidate", f"https://{fqdn}/news", directive="must-revalidate"),
        _item("cc-must-revalidate", f"https://{fqdn}/events", directive="proxy-revalidate"),
```

Refresh: `./run-tests --update-goldens`

Then **read** the diff — do not accept it blind:

```bash
git diff tests/integration/__snapshots__/
```

**The rendered text here is PLURAL, not the singular form quoted in the SPEC.** `_build` (`:52-60`) passes **two** FQDNs with identical item signatures, so they consolidate into one notice carrying one URL from each — `count=2`, hence `many=True`. (This is why the existing snapshot reads "These pages are only cached for 1 hour", not "This page…".) Expect exactly:

> These pages' `Cache-Control` headers contain `must-revalidate`. You should remove it since it has no effect until these pages go stale, and if Cloudflare can't reach your web server at that time, visitors will get errors rather than stale copies of these pages. Apply this to all pages site-wide — the ones listed below are only what we sampled.

Expected diff, exactly: **both** snapshots (U-M and generic) gain two new notice blocks — one naming `must-revalidate`, one naming `proxy-revalidate` — in both the HTML and the plaintext rendering. The U-M ones link `…#cc-must-revalidate`; the generic ones link MDN. **No pre-existing snapshot text may change** — if any unrelated block moves or rewords, stop and investigate.

(The singular form is already pinned in the unit tier by `test_must_revalidate_states_the_stale_risk_and_says_remove_it`, so it needs no render-tier case.)

(There is nothing to *remove* from these snapshots: the old "defeats caching" wording was never snapshotted, because the render tier had no revalidate case.)

- [ ] **Step 8: Run the full fast suite**

Run: `./run-tests --fast`
Expected: all pass, and **`git status` shows no change under `tests/e2e/__snapshots__/`** — those goldens run with Cloudflare disabled and must be byte-identical.

- [ ] **Step 9: Commit**

```bash
git add check/cloudflare/notices.py tests/unit/test_cachecheck_consolidation.py \
        tests/integration/test_cachecheck_notice_render.py tests/integration/__snapshots__/
git commit -m "fix(cachecheck): accurate must-revalidate/proxy-revalidate notice

The old text said must-revalidate 'defeats caching' and bucketed
proxy-revalidate with the directives that prevent caching.  Neither is true.
State what the directive actually does -- nothing until the content is stale,
at which point an unreachable origin means visitors get an error instead of a
stale copy -- and say to remove it, unconditionally.

The notice now carries the site-wide suffix every other Cache-Control item
has: the directive comes from a theme/plugin/server config, and we sample
only a handful of URLs."
```

---

### Task 3: Documentation

**Files:**
- Modify: `docs/cloudflare-cachecheck.md:48-50` (the MISS-retry sentence), `:114-115` (the item table)

- [ ] **Step 1: Update the item table**

Rows :114-115 currently read:

```markdown
| `cc-private` / `cc-no-cache` / `cc-no-store` / `cc-proxy-revalidate` | Caching-hostile directives on public content |
| `cc-must-revalidate` | `must-revalidate` anywhere except the main page (allowed there for emergency alerts) |
```

Replace with:

```markdown
| `cc-private` / `cc-no-cache` / `cc-no-store` | Caching-hostile directives on public content |
| `cc-must-revalidate` | `must-revalidate` or `proxy-revalidate` on any page or asset (the directive seen is in `params["directive"]`). Neither prevents caching; both mean that once the content is stale and the origin is unreachable, visitors get an error instead of a stale copy. Suppressed when the response is already uncacheable. |
```

- [ ] **Step 2: Update the MISS-retry sentence**

The doc has **no list** of MISS-retry blockers — only this sentence, which ends mid-line at :50 and is followed by two more sentences in the same wrapped paragraph:

> When a response is a cacheable `MISS`, it is re-requested up to twice (2-second pauses) to distinguish "not cached *yet*" from "never caches"; only a persistent `MISS` is reported.

Insert this immediately after "…only a persistent `MISS` is reported." and **reflow the paragraph** (do not leave a long line):

> No revalidate directive suppresses this retry — neither `must-revalidate` nor `proxy-revalidate` prevents Cloudflare from caching, so neither explains a `MISS`.

- [ ] **Step 3: Verify no stale claims remain**

Run: `grep -n "revalidate" docs/cloudflare-cachecheck.md`
Expected: no remaining claim that either directive prevents, defeats, or is hostile to caching; no surviving reference to `cc-proxy-revalidate` as an emitted item.

- [ ] **Step 4: Commit**

```bash
git add docs/cloudflare-cachecheck.md
git commit -m "docs(cachecheck): correct the revalidate-directive item and MISS-retry note"
```

---

## Out of scope (written down, not forgotten)

- **U-M documentation page (out of repo).** This change orphans the `#cc-proxy-revalidate` anchor and inverts the meaning of `#cc-must-revalidate`. Owner: the maintainer; should land before the next `--for-real` run. See SPEC "Consequences".
- **`no-stale-if-error` item.** Removing `must-revalidate` does not by itself make Cloudflare serve a stale copy on error — that needs `stale-if-error`, and Always Online overrides it. A future item could flag sites with no serve-stale path. Deliberately not in this change.
- **`is_main_page` end-to-end removal** through `cache.py` and the test helpers.
- **`private`/`no-cache`/`no-store` not firing without a `max-age`** (they sit inside the max-age branch). Arguably the same class of bug; not approved in this spec.

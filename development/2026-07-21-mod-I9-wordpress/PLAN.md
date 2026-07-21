# I9 — `psh/gather.py` (WP half) + `check/wordpress/` + U-M WP checks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move B32–B34 out of `main()` — gather core to the new `psh/gather.py`, the
four generic WP checks to the new `check/wordpress/` package, the two U-M WP checks to
`check/umich/` — publishing the `add_on_updates` + `wp_smell`/`drush_smell`/
`composer_smell` contract keys at `site_post_gather`.

**Architecture:** SPEC.md in this directory (D-i9-1…10); CAMPAIGN.md §3.1/§3.2/§4/§5.
Task order is load-bearing: contract keys land first (so hook smell-writes are never
lost), then the checks leave B34 (slimming it in place), then the remaining gather core
moves. Every task's commit leaves the suite green and the goldens byte-identical.

**Tech Stack:** Python 3.12, pytest (+syrupy), ruff two-config ratchet, pyright.

## Global Constraints

- Four e2e goldens byte-identical at every commit; NO golden/fixture refreshes
  (Invariants 1, 10). The WP golden's `2 pending add-on updates` table is fed by the
  moving code — `add_on_updates` content/order (plugins then themes, list order) is
  golden-load-bearing.
- Moved notice-literal interiors move **byte-for-byte** (Invariant 8; `git diff -w` is
  not acceptable evidence). **This plan deliberately does not retype the literal
  bodies** — copy them from the quoted anchors in `psh/_legacy.py`; retyping is how
  bytes drift. Statement-level code may re-indent; lines *inside* triple-quoted
  literals may not.
- Checks import ONLY `script_context as sc` (Invariant 9); no module-level mutable
  state (§3.4). `psh/gather.py` may import `psh.gateway` (Tier-1).
- Born-gated: `uvx ruff check --config ruff-broad.toml <new files>` clean at every
  commit that touches them; pyright scope unchanged (`psh/` minus `_legacy.py`,
  SPEC D-i9-8).
- Test-first (`mattpocock-skills:tdd` — NOT superpowers:test-driven-development).
  For pure moves, RED = the module/hook does not exist yet (I8 precedent).
- Notice csv codes unchanged (exhaustive for this increment): `version-check`,
  `plugin-list`, `not-installed,{name}`, `multiple-installed,{name}`,
  `turned-off,{name}`, `umich-oidc-login-reinstall`, `ocp-config-fix-needed`,
  `unsupported-turned-off,{name}`, `unsupported,{name}`, `no-favicon`, `wp-smell`,
  `drush-smell`, `composer-smell`, `updates-addons,{num}`.
- Commit per task, each green (`./run-tests --fast` minimum; full suite at close).
- Line numbers below were verified 2026-07-21 against the Task-1 starting state; later
  tasks shift them. **Locate every edit by the quoted anchor text, never by a stale
  number.**
- Purge stale `.superpowers/sdd/task-*-report.md` files before the first dispatch
  (LEDGER I1 process note).

---

### Task 1: the four `site_post_gather` contract keys + B48 repoint

**Files:**
- Modify: `psh/modules.py` (CONTRACT, `stuff_gather_contract`)
- Modify: `psh/_legacy.py` (stuff call args; the `build_smell_notices` call)
- Test: `tests/unit/test_contract_registry.py`

**Interfaces:**
- Produces: `stuff_gather_contract(site_context, framework, site_url,
  wordpress_version, plugins, drupal_version, mods, add_on_updates, wp_smell,
  drush_smell, composer_smell) -> None`;
  `CONTRACT["site_post_gather"]` = existing 6 keys + `("add_on_updates", "wp_smell",
  "drush_smell", "composer_smell")`. Tasks 2's hooks rebind
  `site_context["wp_smell"]`; Task 4 threads gather results into this call.

- [ ] **Step 1: Write the failing tests** — in `tests/unit/test_contract_registry.py`,
  extend the `site_post_gather` expectations (find the existing key-tuple pin and the
  gather-stuffer test; update both) and add same-object + default pins:

```python
def test_gather_stuffer_new_keys(psh, reset_sc):
    import psh.modules
    ctx = _fresh_ctx(reset_sc)
    addons = [{"slug": "x", "name": "X", "type": "plugin",
               "current_version": "1", "new_version": "2"}]
    psh.modules.stuff_gather_contract(ctx, "wordpress", "https://x/", "6.9", [],
                                      None, None, addons, "warn-w", "warn-d", "warn-c")
    assert ctx["add_on_updates"] is addons          # same object, not a copy
    assert ctx["wp_smell"] == "warn-w"
    assert ctx["drush_smell"] == "warn-d"
    assert ctx["composer_smell"] == "warn-c"
    assert set(ctx) - BASE_KEYS == set(psh.modules.CONTRACT["site_post_gather"])
```

- [ ] **Step 2: RED** — `python -m pytest tests/unit/test_contract_registry.py -v`:
  new test fails (`TypeError: stuff_gather_contract() takes 7 positional arguments`);
  the existing key-tuple test fails on the extended expectation.

- [ ] **Step 3: Implement** — `psh/modules.py`:
  - `CONTRACT["site_post_gather"]` tuple gains `"add_on_updates", "wp_smell",
    "drush_smell", "composer_smell"` after `"drupal_modules"`.
  - `stuff_gather_contract` gains the four parameters (keep the `# noqa: PLR0913`
    with the reason updated to "one param per site_post_gather contract key (10)").
    Body additions:

```python
    site_context["add_on_updates"] = add_on_updates
    # str values; "" when none.  wp_smell MAY be rebound during the phase by
    # check.wordpress.ocp/favicon (their probe stderr participates in last-wins,
    # SPEC D-i9-3) -- the one sanctioned mutate-during-phase key.  Consumers read
    # site_context, never a stale local.
    site_context["wp_smell"] = wp_smell
    site_context["drush_smell"] = drush_smell
    site_context["composer_smell"] = composer_smell
```

  Docstring: note the three smell keys + `add_on_updates` semantics (SPEC D-i9-3).
  - `psh/_legacy.py` stuff call (anchor `stuff_gather_contract(site_context,`): append
    `add_on_updates, wp_smell, drush_smell, composer_smell` to the args.
  - B48 repoint (anchor `build_smell_notices(site["name"], wp_smell, drush_smell,
    composer_smell)`):

```python
                build_smell_notices(site["name"], site_context["wp_smell"],
                                    site_context["drush_smell"],
                                    site_context["composer_smell"])
```

- [ ] **Step 4: GREEN** — `python -m pytest tests/unit/test_contract_registry.py -v`
  all pass; `./run-tests --fast` green; `git diff -- tests/e2e/__snapshots__/` empty.

- [ ] **Step 5: Gates + commit**

```bash
uvx ruff check --config ruff-broad.toml psh/modules.py     # clean
git add psh/modules.py psh/_legacy.py tests/unit/test_contract_registry.py
git commit -m "feat(campaign-I9): publish add_on_updates + smell contract keys at site_post_gather"
```

---

### Task 2: `check/wordpress/` package (PAPC, sessions, OCP, favicon)

**Files:**
- Create: `check/wordpress/__init__.py`, `check/wordpress/papc.py`,
  `check/wordpress/sessions.py`, `check/wordpress/ocp.py`, `check/wordpress/favicon.py`
- Modify: `psh/_legacy.py` (four region deletions; two `sc` façade lines)
- Modify: `sample-pantheon-sitehealth-emails.toml` (`[Check.wordpress]` block)
- Test: create `tests/integration/test_check_wordpress_init.py`,
  `tests/integration/test_check_wordpress.py`,
  `tests/integration/test_wordpress_notice_render.py`;
  modify `tests/unit/test_house_rules.py` (façade names)

**Interfaces:**
- Consumes: Task 1's `wp_smell` contract key (the OCP/favicon hooks rebind it).
- Produces: the four hooks named in SPEC D-i9-5's table; `sc.wp_eval`, `sc.wp_error`
  façade names (Task 3/4 do not use them, but the façade test pins them from here on).

- [ ] **Step 1: façade lines** — `psh/_legacy.py`, in the exposure block (anchor
  `sc.terminus = terminus`), add:

```python
sc.wp_eval = wp_eval        # check packages: WP-CLI eval probes (check/wordpress ocp, favicon)
sc.wp_error = wp_error      # check packages: WP command-failure notices
```

  and add both names to the documented-names list in
  `tests/unit/test_house_rules.py::test_documented_sc_facade_names_exist` (write the
  test edit first, watch it fail on the missing attributes, then add the two lines).

- [ ] **Step 2: Write the failing init/gating tests** —
  `tests/integration/test_check_wordpress_init.py`, modeled line-for-line on
  `tests/integration/test_check_pantheon_init.py` (standalone package load via
  `tests/helpers/checkload.py`): absent `[Check]` → 4 hooks at `site_post_gather`
  named `check.wordpress.papc.check_papc`,
  `check.wordpress.sessions.check_native_php_sessions`,
  `check.wordpress.ocp.check_ocp_config`, `check.wordpress.favicon.check_favicon`, in
  that order, with consumes exactly as SPEC D-i9-5's table and produces `[]`;
  `enabled = false` → no hooks + the skip message; `[Check.wordpress]` present with
  `enabled = true` → registered. RED: package doesn't exist.

- [ ] **Step 3: Create the package** — `check/wordpress/__init__.py`:

```python
"""Generic WordPress site-health checks (campaign I9, CAMPAIGN.md section 3.2):
PAPC + native-PHP-sessions + OCP-config + favicon at site_post_gather.  Gated by
[Check.wordpress].enabled, default TRUE -- these checks ran unconditionally before
the relocation (section 5)."""

import script_context as sc

if sc.config.get('Check', {}).get('wordpress', {}).get('enabled', True) is not False:
    from . import favicon, ocp, papc, sessions
    sc.add_hook('site_post_gather', {'name': 'check.wordpress.papc.check_papc',
                                     'func': papc.check_papc,
                                     'consumes': ['framework', 'wordpress_plugins'],
                                     'produces': []})
    sc.add_hook('site_post_gather', {'name': 'check.wordpress.sessions.check_native_php_sessions',
                                     'func': sessions.check_native_php_sessions,
                                     'consumes': ['framework', 'wordpress_plugins'],
                                     'produces': []})
    sc.add_hook('site_post_gather', {'name': 'check.wordpress.ocp.check_ocp_config',
                                     'func': ocp.check_ocp_config,
                                     'consumes': ['framework', 'wordpress_plugins'],
                                     'produces': []})
    sc.add_hook('site_post_gather', {'name': 'check.wordpress.favicon.check_favicon',
                                     'func': favicon.check_favicon,
                                     'consumes': ['framework', 'fqdns_not_behind_cloudflare'],
                                     'produces': []})
else:
    sc.console.print('[bold yellow] Skipping check.wordpress because it is disabled in the config')
```

  `papc.py` (sessions.py is identical modulo plugin slug/display/url/reason — copy the
  argument literals byte-for-byte from the anchors `"pantheon-advanced-page-cache",`
  and `"wp-native-php-sessions",` in `psh/_legacy.py`):

```python
"""The Pantheon Advanced Page Cache recommended-plugin check (campaign I9, from B34)."""

import script_context as sc


def check_papc(site_context):
    if not site_context["framework"].startswith("wordpress"):
        return
    site = site_context["site"]
    site_context.add_notices(
        sc.check_wordpress_plugin(
            site["name"],
            site_context["wordpress_plugins"],
            "pantheon-advanced-page-cache",
            ...  # display name / url / reason copied byte-for-byte from the anchor
        )
    )
```

  `ocp.py` — framework gate, `plugins = site_context["wordpress_plugins"]`; `if
  plugins is None: return`; `live_site = site_context["site"]["id"] + ".live"`; then
  the loop shape below with the probe/notice bodies copied from the anchor
  `# Special check for Object Cache Pro upgrade` (`:1734–1764`), with `wp_eval(` →
  `sc.wp_eval(`, `wp_error(` → `sc.wp_error(`, and the smell write becoming
  `site_context["wp_smell"] = errors`:

```python
    for p in plugins:
        if p["name"] == "object-cache-pro" and p["status"] != "inactive":
            ...  # probe + notice, copied verbatim from the anchor
```

  `favicon.py` — framework gate, `live_site` as above, body copied from the anchor
  `# This isn't a plugin, but here is a good place to check for it.` at `:1845–1875`
  (the favicon one — the OCP block has the same comment sentence inside it, so anchor
  on `'echo is_file("favicon.ico") ? "true": "false";'`), with the same three
  substitutions plus `fqdns_not_behind_cloudflare` read as
  `site_context["fqdns_not_behind_cloudflare"]`.

- [ ] **Step 4: Delete the four regions from `psh/_legacy.py`** — PAPC
  (`site_context.add_notices(\n                    check_wordpress_plugin(` first
  call, `:1608–1617`), sessions (second call, `:1618–1627`), OCP (`:1734–1764`),
  favicon (`:1845–1875`). The surrounding gather code (update collection, must-use
  print, hummingbird, theme list) stays. Keep the relocated-comment breadcrumb style
  used at `:1628` (`# The umich-cloudflare plugin check moved to …`) — one line per
  relocated check.

- [ ] **Step 5: Hook-seam + precedence tests** —
  `tests/integration/test_check_wordpress.py` (pattern:
  `tests/integration/test_check_pantheon.py`, `gateway` fixture +
  `sc.SiteContext({"site": {...}, "framework": ..., "wordpress_plugins": ...,
  "wp_smell": "", "fqdns_not_behind_cloudflare": [...]})`): the SPEC §7 case list for
  papc/sessions/ocp/favicon, including: ocp with no matching plugin makes **no**
  gateway call; ocp stderr rebinds `site_context["wp_smell"]`; favicon on
  `framework="drupal"` makes no call; **the D-i9-4 precedence pin** (context
  `wp_smell="theme-stderr"`, OCP probe returns stderr, favicon clean → final is OCP's).
  `tests/integration/test_wordpress_notice_render.py`: syrupy snapshots of the OCP
  alert and no-favicon warning HTML/text (`--update-goldens` creates them; review the
  initial content byte-by-byte against the old source).

- [ ] **Step 6: GREEN + gates** — targeted files pass; `./run-tests --fast` green;
  `git diff -- tests/e2e/__snapshots__/` **empty** (the new syrupy `.ambr` files land
  under `tests/integration/__snapshots__/`, never in the e2e goldens dir);
  `uvx ruff check --config ruff-broad.toml check/wordpress/` clean.

- [ ] **Step 7: sample config** — after the `[Check.pantheon]` block:

```toml
[Check.wordpress]
enabled = true          # PAPC, native-PHP-sessions, OCP-config, favicon checks
```

- [ ] **Step 8: Commit**

```bash
git add check/wordpress/ psh/_legacy.py sample-pantheon-sitehealth-emails.toml tests/
git commit -m "feat(campaign-I9): check/wordpress package with the PAPC/sessions/OCP/favicon checks"
```

---

### Task 3: U-M WP checks → `check/umich/` (+ ratchet narrowing)

**Files:**
- Create: `check/umich/oidc_login.py`, `check/umich/hummingbird.py`
- Modify: `check/umich/__init__.py` (two registrations, after `cloudflare_cms`)
- Modify: `psh/_legacy.py` (two region deletions; `semver` orphan check)
- Modify: `ruff-broad.toml` (narrow the `check/umich/` exclude)
- Test: create `tests/integration/test_check_umich_wp.py`,
  `tests/integration/test_umich_wp_notice_render.py`; check
  `tests/integration/test_check_umich_cloudflare_cms.py` for hook-count pins

**Interfaces:**
- Produces: hooks `check.umich.oidc_login.check_oidc_login` and
  `check.umich.hummingbird.check_hummingbird_fork`, both `site_post_gather`,
  `consumes ['framework', 'wordpress_plugins']`, `produces []`.

- [ ] **Step 1: Write the failing registration/seam tests** —
  `tests/integration/test_check_umich_wp.py` (standalone load of `check/umich/` with a
  umich-enabled fake config, `checkload.py`): umich-enabled → both hooks registered
  after `check.umich.cloudflare_cms…` at `site_post_gather` with the declarations
  above; umich-disabled → neither (the D-i9-6 gating-change proof). Seam cases per
  SPEC §7 (oidc `1.2.99`→warning / `1.3.0`→none / inactive→none / plugins None→none;
  hummingbird active-umich→alert / inactive-umich→info / plain version→none; the
  D-i9-10 print pin via `recording_console` — line contains `its-wws-test1`, not
  `{'name':`). RED: modules don't exist.

- [ ] **Step 2: Create the modules** — `oidc_login.py`:

```python
"""The umich-oidc-login reinstall check (campaign I9, from B34; U-M-gated since I9)."""

import semver

import script_context as sc


def check_oidc_login(site_context):
    if not site_context["framework"].startswith("wordpress"):
        return
    plugins = site_context["wordpress_plugins"]
    if plugins is None:
        return
    site = site_context["site"]
    for p in plugins:
        if p["name"] == "umich-oidc-login" and p["status"] != "inactive":
            if semver.compare(p["version"], "1.2.99") <= 0:
                site_context.add_notice(
                    ...  # the umich-oidc-login-reinstall dict, copied byte-for-byte
                         # from the anchor `# Special check for umich-oidc-login upgrade`
                )
```

  `hummingbird.py` — same skeleton; body from the anchor
  `# Special check for our fork of Hummingbird` (`:1765–1810`) with `escape_url(` →
  `sc.escape_url(`, the D-i9-10 fix (`{site}` → `{site['name']}` in the ATTENTION
  print), and `import html` at top. Notice dicts byte-for-byte.
  `check/umich/__init__.py`: `from .oidc_login import check_oidc_login` /
  `from .hummingbird import check_hummingbird_fork` inside the existing gate, and two
  `sc.add_hook('site_post_gather', …)` calls appended **after** the `cloudflare_cms`
  registration, declarations as above.

- [ ] **Step 3: Delete the two regions from `psh/_legacy.py`** — oidc (anchor
  `# Special check for umich-oidc-login upgrade, December 2025`, `:1647–1733`),
  hummingbird (anchor `# Special check for our fork of Hummingbird`, `:1765–1810`).
  Leave one-line relocation breadcrumbs. Then `grep -n "semver" psh/_legacy.py` —
  expected: only the top import remains → remove it (I3 orphan rule); if other users
  exist, leave it and note in the report.

- [ ] **Step 4: Ratchet narrowing** — in `ruff-broad.toml` `extend-exclude`, replace
  `"check/umich/"` with `"check/umich/sitelens.py", "check/umich/cloudflare_cms.py"`.
  Then `uvx ruff check --config ruff-broad.toml check/umich/` and fix what fires in
  `__init__.py`/the two new modules only (expected: `I001`-class; registration
  behavior unchanged). The two grandfathered siblings must not be edited.

- [ ] **Step 5: GREEN + gates** — new tests pass;
  `tests/integration/test_check_umich_cloudflare_cms.py` still green (adjust any
  hook-count pin, never assertion substance); `./run-tests --fast` green; goldens
  unchanged; snapshot file additions only.

- [ ] **Step 6: Commit**

```bash
git add check/umich/ psh/_legacy.py ruff-broad.toml tests/
git commit -m "feat(campaign-I9): U-M WP plugin checks move to check/umich (now UMich-gated)"
```

---

### Task 4: `psh/gather.py` — the WP gather core moves

**Files:**
- Create: `psh/gather.py`
- Modify: `psh/_legacy.py` (delete `check_wordpress_plugin` def, B32, B34 remainder;
  re-import; threading)
- Test: create `tests/integration/test_gather_wordpress.py`; syrupy additions in
  `tests/integration/test_wordpress_notice_render.py` (papc-builder variants)

**Interfaces:**
- Consumes: Task 1's extended stuff call (the threading feeds it).
- Produces: `psh.gather.check_wordpress_plugin` (signature unchanged),
  `psh.gather.wordpress_network_url(site, live_site, site_context) ->
  tuple[str | None, str]`, `psh.gather.gather_wordpress(site, live_site, site_context)
  -> WordPressGather` (fields per SPEC D-i9-2). `_legacy.py` re-imports all three +
  `WordPressGather`, so `sc.check_wordpress_plugin` and tests' `psh.<name>` resolve.

- [ ] **Step 1: Write the failing tests** —
  `tests/integration/test_gather_wordpress.py` per SPEC §7's case list (the `gateway`
  fixture routes `wp`/`wp_eval`; pattern `tests/integration/test_traffic_flow.py` for
  importing `from psh.gather import gather_wordpress, wordpress_network_url` at module
  level — NOT via the `psh` fixture attribute, the I6 fixture-shadowing lesson).
  Illustrative core case (the others follow the same shape):

```python
def test_gather_happy_path_collects_addons_in_order(gateway, reset_sc):
    # gateway fixture returns: version eval -> "6.9.4", plugin list -> two plugins
    # with update=="available" (order A,B), theme list -> one theme with update
    result = gather_wordpress(SITE, "id.live", make_ctx())
    assert result.wordpress_version == "6.9.4"
    assert [u["slug"] for u in result.add_on_updates] == ["a-plugin", "b-plugin", "the-theme"]
    assert result.add_on_updates[0]["new_version"] == "2.0"
    assert result.wp_smell == ""
    assert result.results_entry == {"framework": "wordpress", "version": "6.9.4",
                                    "plan_name": "Basic"}
```

  RED: `psh.gather` does not exist.

- [ ] **Step 2: Create `psh/gather.py`** — module docstring (I6 register: what moved,
  which SPEC, loop control stays in `main()`), imports per SPEC §3, `WordPressGather`
  NamedTuple (SPEC D-i9-2 verbatim), then the three defs: `check_wordpress_plugin`
  moved from `psh/_legacy.py:265–330` (with the call-time bridge
  `from psh._legacy import escape_url  # noqa: PLC0415 -- escape_url stays in _legacy
  until I12's psh/render.py move (D-i6-2 precedent)` at the top of the function body),
  `wordpress_network_url` (B32 body from anchor
  `=== Getting WordPress network URL for`), `gather_wordpress` (B34 remainder from
  anchor `=== Getting WordPress version for` through the theme-collection loop end).
  Fetch/notice/pprint/must-use code byte-preserved except: `wp(`/`wp_eval(`/`wp_error(`
  resolve via the module's own gateway imports (same names — zero call-site edits);
  local smell writes become the function-local last-wins var returned in the tuple;
  `site_results[...] = {...}` becomes the `results_entry` construction.

- [ ] **Step 3: Edit `psh/_legacy.py`** — delete the `check_wordpress_plugin` def
  (`:265–330`) and the B32/B34-remainder regions; add
  `from psh.gather import (WordPressGather, check_wordpress_plugin, gather_wordpress,
  wordpress_network_url)` to the re-import block; replace the deleted regions with the
  threading code from SPEC D-i9-2 **exactly** (the `if network_smell != "":` /
  `if gather.wp_smell != "":` guards are the last-wins preservation — do not
  "simplify" them to unconditional assignment).

- [ ] **Step 4: papc-builder snapshots** — in
  `tests/integration/test_wordpress_notice_render.py`, add syrupy snapshots for the
  three `check_wordpress_plugin` variants (not-installed / multiple-installed /
  turned-off) via `psh.gather.check_wordpress_plugin` directly, plus unit-style
  assertions: active plugin → `[]`, non-list input → `[]`.

- [ ] **Step 5: GREEN + gates** — new tests pass; `./run-tests --fast` green;
  **`python -m pytest tests/e2e -x -q` and `git diff -- tests/e2e/__snapshots__/`
  empty** (the add-on table is the live golden proof);
  `uvx ruff check --config ruff-broad.toml psh/gather.py` clean; pyright gate 0 errors.
  Paste the extracted-region byte-diff evidence (moved literals vs old source) in the
  task report.

- [ ] **Step 6: Commit**

```bash
git add psh/gather.py psh/_legacy.py tests/
git commit -m "feat(campaign-I9): move the WordPress gather core into psh/gather.py"
```

---

### Task 5: docs, amendment, ledger, acceptance

**Files:**
- Modify: `CLAUDE.md`, `development/2026-07-17-modularization-campaign/CAMPAIGN.md`
  (§8 row), `development/2026-07-17-modularization-campaign/LEDGER.md` (I9 entry),
  `development/2026-07-21-mod-I9-wordpress/SPEC.md` (§9 acceptance paste),
  auto-memory (`/home/node/.claude/projects/-workspace/memory/`)

**Interfaces:** none (docs close-out; no code edits).

- [ ] **Step 1: CLAUDE.md** — contract table `site_post_gather` row gains the four
  keys with D-i9-3 semantics (incl. the wp_smell hook-rebind note); § Single-module
  core gains the `psh/gather.py` paragraph (move set + `WordPressGather` + the
  escape_url bridge + re-import pattern); `find_modules` package list gains
  `check.wordpress`; check-package descriptions gain `check/wordpress/` and the two
  U-M WP checks under `check/umich/`; the runtime-exposed `sc` block list gains
  `sc.wp_eval`/`sc.wp_error`; still-hardcoded-U-M list: **remove** oidc/Hummingbird
  (now gated), **add** the favicon notice's its.umich.edu links (generic
  `check/wordpress/` package); Testing section: the new test files; delete any prose
  that existed only to describe the moved inline logic (report the line delta).
- [ ] **Step 2: CAMPAIGN.md §8 amendment** — the csv-values row gains
  "I9 (wp-smell precedence when theme-list and OCP-probe stderr co-occur without
  favicon stderr — see LEDGER I9)" (D-i9-4).
- [ ] **Step 3: LEDGER I9 entry** — §12 template: moved set, deviations, the §8
  amendment, contract/config/sc additions (`add_on_updates` + 3 smells,
  `[Check.wordpress]`, `sc.wp_eval`/`sc.wp_error`), the D-i9-6 gating change, the
  D-i9-7 order analysis, discovered tasks + dispositions, **Open questions for I10**
  (Drupal half mirrors this shape; the escape_url bridge is I12's; D-i8-7 pyright
  decision still inherited; B39/B48 bodies move at I10 and their `site_context` reads
  are already in place).
- [ ] **Step 4: memory** — update the modularization-campaign memory file (I9 done,
  key facts: gather module, gating change, smell keys).
- [ ] **Step 5: Acceptance** — full `./run-tests` (live tier if credentials present;
  else `--fast` + ledger note); paste results into SPEC §9 per SPEC §8's checklist
  (incl. `git diff <start-sha> -- tests/e2e/__snapshots__/` **empty** — new syrupy
  files live under `tests/integration/__snapshots__/`).
- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md development/ /home/node/.claude/projects/-workspace/memory/ 2>/dev/null || true
git add CLAUDE.md development/
git commit -m "docs(campaign-I9): close the wordpress increment"
```

(Memory lives outside the repo — update it, but only repo files go in the commit.)

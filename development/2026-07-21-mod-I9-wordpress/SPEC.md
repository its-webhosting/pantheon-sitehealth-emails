# SPEC — Increment I9: `psh/gather.py` (WP half) + `check/wordpress/` + U-M WP checks → `check/umich/`

**Campaign:** `development/2026-07-17-modularization-campaign/` — this spec cites
`CAMPAIGN.md` by section number and re-derives nothing (CAMPAIGN.md preamble). Scope
authority: §11 row I9 (B32–B34; baseline lines 672–739 = `check_wordpress_plugin`,
verified against `git show a47418c` — `check_drupal_module` starts at 741 and is I10's).
Tier-1 assignment: §3.1 row `psh/gather.py` ("Slimmed framework gathers feeding the
`site_post_gather` contract (from B32–B35), `check_wordpress_plugin`/`check_drupal_module`
helpers" — this increment delivers the WP half). Tier-2 assignments: §3.2 row
`check/wordpress/` ("PAPC + native-sessions checks, OCP config probe, favicon (from B34)"
at `site_post_gather`) and §3.2 row `check/umich/` ("umich-oidc-login, Hummingbird fork
(B34)"). Contract keys: §4 ("`add_on_updates` + `wp_smell`/`drush_smell`/`composer_smell`
(I9/I10, at `site_post_gather`)" — I9 adds all four; I10 repoints its Drupal half onto
them). Config: §5 (`[Check.wordpress]`, default **true**). What stays in `main()`: §3.3.
Obligations: §7. Behavior bar: §8 (one amendment, D-i9-4). Invariants: §9 (esp. 1, 3, 8,
9). Ratchet: §13.

**Carried notes this spec honors** (LEDGER I8 "Open questions for I9"): the
`site_post_gather` notice-order consequences are analyzed the D-i8-3 way (D-i9-7); the
pyright-scope decision **D-i8-7 is inherited** (D-i9-8); `Notice`-class adoption for
extra-csv notices stays deferred to I10/I12 (every notice moved here keeps its legacy
dict form — several carry extra csv fields: `unsupported-turned-off,{name}`,
`not-installed,{name}`).

**Read first (per §7):** `CAMPAIGN.md`, `LEDGER.md` (through I8), `CLAUDE.md`
(§ Plugin / check module system, § Per-site report pipeline, § Testing), `BLOCKMAP.md`
rows B32–B39, B48, `prompts/directives.md`, `prompts/implementation-standards.md`.

## Glossary (delta over CAMPAIGN.md's)

- **Gather core** — the data-fetching part of B32–B34 that feeds contract keys and
  `site_results`: network URL (B32), WP version fetch, plugin-list fetch, add-on-update
  collection + must-use print, theme-list fetch. Moves to `psh/gather.py`.
- **The checks** — the notice-emitting probes interleaved in B34 today: PAPC,
  native-sessions, OCP config, favicon (→ `check/wordpress/`) and umich-oidc-login,
  Hummingbird fork (→ `check/umich/`).
- **Smell** — the stderr of the last non-fatal wp/drush wrapper call that produced any;
  today a `main()` local per family (`wp_smell`/`drush_smell`/`composer_smell`), fed to
  `build_smell_notices` (B48, full-report path only, stays inline until I10).
- **`WordPressGather`** — the new NamedTuple `gather_wordpress()` returns (D-i9-2).

## 1. Scope (exhaustive) and non-scope

In scope (current `psh/_legacy.py` lines, verified 2026-07-21):

1. **New module `psh/gather.py`** (born gated): `check_wordpress_plugin` (`:265–330`,
   moved verbatim modulo ratchet dispositions), `wordpress_network_url` (B32 body,
   `:1523–1543`), `gather_wordpress` (B34 gather core: version fetch + `site_results`
   entry data `:1559–1585`, plugin-list fetch `:1586–1607`, add-on collection +
   must-use print `:1630–1646`, theme-list fetch + add-on collection `:1811–1844`),
   returning `WordPressGather`. Re-imported into `psh/_legacy.py` (I2–I7 pattern) so
   `main()`'s call sites and the `sc.check_wordpress_plugin` exposure line resolve
   unchanged.
2. **New package `check/wordpress/`** (born gated): `__init__.py` (config-gated
   registration, default true) + `papc.py`, `sessions.py`, `ocp.py`, `favicon.py` —
   four `site_post_gather` hooks (D-i9-5), bodies verbatim from B34
   (`:1608–1617` PAPC, `:1618–1627` sessions, `:1734–1764` OCP, `:1845–1875` favicon).
3. **`check/umich/` grows**: `oidc_login.py` (`:1647–1733`) + `hummingbird.py`
   (`:1765–1810`), two `site_post_gather` hooks registered under the existing
   `[UMich].enabled` gate (D-i9-6 — a deliberate gating change, documented).
4. **Contract keys** (§4): `CONTRACT["site_post_gather"]` gains `add_on_updates`,
   `wp_smell`, `drush_smell`, `composer_smell`; `stuff_gather_contract` extended
   (D-i9-3); B48's `build_smell_notices` call (`:2760`) repoints to `site_context`
   reads; CLAUDE.md table row updated; `test_contract_registry.py` pins.
5. **`sc` façade additions**: `sc.wp_eval`, `sc.wp_error` (D-i9-9) — needed by the
   relocated OCP/favicon checks; added to the exposure block (`:459–466`), CLAUDE.md's
   documented-names list, and `test_documented_sc_facade_names_exist`.
6. **Config**: `[Check.wordpress]` with `enabled` defaulting **true** (§5);
   documented block added to `sample-pantheon-sitehealth-emails.toml` beside
   `[Check.pantheon]`.
7. **Ratchet** (§13): `psh/gather.py` + `check/wordpress/` born gated;
   `ruff-broad.toml`'s `"check/umich/"` exclude narrowed to
   `"check/umich/sitelens.py"` + `"check/umich/cloudflare_cms.py"` so
   `check/umich/__init__.py` (edited here) and the two new modules are gated (D-i9-8).
8. **CAMPAIGN.md §8 amendment** (D-i9-4): the smell-precedence edge case, applied to
   the document + ledgered in the same closing commit.
9. **New tests** per §7-Tests (test-first, `mattpocock-skills:tdd`, at the named seams).
10. **Docs**: CLAUDE.md (contract table, package lists, sc-façade block,
    still-hardcoded-U-M list — oidc/Hummingbird leave it, favicon's its.umich.edu links
    join it as "living in the generic `check/wordpress/` package"), ledger entry,
    auto-memory.

NOT in scope:

- **B35 (Drupal branch), B36 (unknown framework), B30's multisite probe** — I10. The
  `check_drupal_module` helper (`:333–430`) stays in `_legacy.py` (baseline 741+ is
  I10's range).
- **B39 (add-on updates table) and B48 (smell notice bodies)** stay inline in `main()`
  — I10 (`check/addon_updates/`). Only B48's *reads* repoint (scope item 4); B39 keeps
  reading the `add_on_updates` local (same list object the stuffer publishes — no hook
  mutates it in I9, so repointing it is pure churn; asymmetry dissolves at I10).
- **`escape_url` stays in `_legacy.py`** (§3.1 assigns it to `psh/render.py`, I12).
  `check_wordpress_plugin` needs it → call-time bridge import in `psh/gather.py`
  (`from psh._legacy import escape_url  # noqa: PLC0415`), the D-i6-2 precedent.
  **I12 obligation**: replace with a module-level `from psh.render import escape_url`
  when it moves (repeated in the ledger's Open questions).
- **B33 init** (`:1548–1558`) stays in `main()` — it serves both framework branches and
  the unconditional contract stuffing (the I6 D-i6-1 loop-skeleton reading).
- **`Notice`-class adoption**: none (see Carried notes).
- **De-U-M-ifying moved notice bodies**: the favicon body's its.umich.edu links and the
  oidc/Hummingbird U-M copy move **verbatim** (Invariant 8; not NEW un-gated U-M
  content). Favicon lands in the generic package with its U-M links intact (the I8
  check/pantheon precedent; post-campaign work), and CLAUDE.md's still-hardcoded-U-M
  list records it.
- No golden/fixture refreshes (Invariants 1, 10); no artifact-structure change (§8);
  no `_legacy.py` import removals beyond what this change orphans (I3 rule —
  expectation: `semver` IS orphaned (only the oidc check uses it — implementer
  grep-verifies); `html`/`pprint` have other users).

## 2. Architecture decisions

### D-i9-1: the three-way split of B32–B34

Per §3.1/§3.2: data gathering that feeds the contract is Tier-1 (`psh/gather.py`);
notice-emitting probes are Tier-2 checks. The gather core keeps everything the contract
and `site_results`/B39 need (version, plugins, themes→add-ons, network URL, smells from
those fetches, the must-use diagnostic print, and the `wp_error` notices for *failed
gathers* — they describe the gather, not a check). The six checks leave for hook
packages. `main()` keeps the framework branch dispatch, the B33 init, and the
accumulator writes (§3.3; I6 D-i6-1: flow bodies move, loop control and accumulators
stay).

Flow (PD#8) — where each moved region lands relative to today:

```
main() per site (post site_post_dns):
   site_url from main_fqdn (stays)
   if framework == "wordpress_network":
       wordpress_network_url() ◄─[B32 moves]      → site_url/wp_smell threading in main()
   debug prints (stay) ─ B33 init (stays)
   if framework.startswith("wordpress"):
       gather_wordpress() ◄─[B34 gather core moves]
         = version + plugin list + add-on collect + must-use print + theme list
       main(): wordpress_version/plugins/add_on_updates/wp_smell/site_results ← WordPressGather
   elif drupal: B35 (stays, I10)     else: B36 (stays)
   stuff_gather_contract(…, add_on_updates, wp_smell, drush_smell, composer_smell)  ◄── 4 NEW keys
   invoke_hooks("site_post_gather")
     ──► pantheon.updates → pantheon.php_eol
         → umich.cloudflare_cms → umich.oidc_login ◄─[moves]  → umich.hummingbird ◄─[moves]
         → wordpress.papc ◄─[moves] → wordpress.sessions ◄─[moves]
         → wordpress.ocp ◄─[moves]  → wordpress.favicon ◄─[moves]
              (ocp/favicon update site_context["wp_smell"] in place)
   B39 addons (stays, reads the add_on_updates local) → B42 --only-warn gate
   … chart/plan … B48 smells (stays, now reads site_context["wp_smell"/"drush_smell"/"composer_smell"])
```

### D-i9-2: `psh/gather.py` shapes (the I6 flow-function pattern)

```python
class WordPressGather(NamedTuple):
    wordpress_version: str          # "unknown" when the fetch failed (never None here)
    plugins: object                 # raw wp plugin list result (list | None | junk)
    add_on_updates: list            # plugin updates then theme updates, list order
    wp_smell: str                   # last-wins stderr across version/plugins/themes; "" if none
    results_entry: dict             # {"framework", "version", "plan_name"} for site_results


def wordpress_network_url(site, live_site, site_context) -> tuple[str | None, str]:
    # B32 verbatim: banner print, wp_eval("echo network_home_url();"), wp_error notice
    # on fatal/None, smell on stderr, debug line; returns (stripped URL | None, smell).

def gather_wordpress(site, live_site, site_context) -> WordPressGather:
    # B34 gather core verbatim: the three fetches + wp_error notices on failure,
    # verbose pprint dumps, add-on collection (plugins then themes), must-use print.
```

`main()` threading (exact semantics — preserves today's last-wins overwrite rules,
where a later empty smell never clears an earlier one):

```python
if site["framework"] == "wordpress_network":
    network_url, network_smell = wordpress_network_url(site, live_site, site_context)
    if network_smell != "":
        wp_smell = network_smell
    if network_url is not None:
        site_url = network_url
...
if site["framework"].startswith("wordpress"):
    gather = gather_wordpress(site, live_site, site_context)
    wordpress_version = gather.wordpress_version
    plugins = gather.plugins
    add_on_updates = gather.add_on_updates
    if gather.wp_smell != "":
        wp_smell = gather.wp_smell
    site_results[site["name"]] = gather.results_entry
```

`WordPressGather` is a supporting return type not in §6's table — the I7
`PlanRecommendation` precedent (ledger note, no amendment). Imports:
`import script_context as sc`, `from psh.gateway import wp, wp_eval, wp_error`, stdlib
`html`/`pprint`, and the call-time `escape_url` bridge (§1 non-scope). No module-level
mutable state (§3.4). Column-0 `f"""` interiors (the `check_wordpress_plugin` notice
bodies have none — its notices are single-line f-strings — but the moved hook bodies
do) move byte-for-byte (Invariant 8).

### D-i9-3: the four new contract keys; `wp_smell` is hook-updatable

`stuff_gather_contract` grows four parameters (noqa reason updated — one param per
contract key remains the rule):

```python
stuff_gather_contract(site_context, site["framework"], site_url,
                      wordpress_version, plugins, drupal_version, mods,
                      add_on_updates, wp_smell, drush_smell, composer_smell)
```

Contract semantics (CLAUDE.md table row + `CONTRACT` registry):

- `add_on_updates` — list of pending add-on updates, dicts with
  `slug`/`name`/`type`/`current_version`/`new_version` (Drupal entries, I10, may add
  `new_version_url` and a list-valued `name`); `[]` when none, not that framework, or
  the gather failed. Stuffed with the same list object `main()`'s B39 still reads.
- `wp_smell`/`drush_smell`/`composer_smell` — str, `""` when none; the stderr of the
  last non-fatal wrapper call that produced any. **`wp_smell` MAY be rebound in place
  during the phase** by `check.wordpress.ocp`/`check.wordpress.favicon` (their probes'
  stderr participates in last-wins, as it did inline) — the one sanctioned
  mutate-during-phase key; consumers reading after the phase (B48 today,
  `check/addon_updates/` at I10) see the updated value. This is why B48's
  `build_smell_notices` call MUST repoint to `site_context["wp_smell"]` (etc.): a
  hook's rebind of an immutable str never reaches the `main()` local.

Not a producers-conflict: hooks do not *declare* `produces: ['wp_smell']` (that would
be a §4-condition-2 fatal against the core registry); the mutation is documented here,
in the `CONTRACT` comment, and in the two hooks' docstrings.

### D-i9-4: smell-precedence edge — CAMPAIGN.md §8 amendment

Today's `wp_smell` overwrite order is version → plugins → OCP → themes → favicon.
After the split it is version → plugins → themes (gather) → OCP → favicon (hooks).
The final value differs **only** when the theme-list stderr and the OCP-probe stderr
are both non-empty and the favicon stderr is empty — today themes wins, after I9 OCP
wins. Since the `wp-smell` notice csv embeds the smell text
(`{site},wp-smell,{json.dumps(wp_smell)…}`), this is a notice-csv *value* change in
that co-occurrence, which §8 reserves to I1/I7/I12 — so this ships as a **§8
amendment** (the I7 savings-field precedent): the csv-values row gains
"I9 (wp-smell precedence when theme-list and OCP-probe stderr co-occur without favicon
stderr — see LEDGER I9)". Applied to CAMPAIGN.md + ledgered in the closing commit.
Why acceptable: wp-cli stderr (PHP deprecation spew) is in practice identical across
all five calls in a run, making the divergent case value-identical too; engineering
exact preservation would need per-source smell slots — a structure §4's fixed key set
does not admit. An integration test pins the *new* precedence so it is deliberate,
not accidental (§7-Tests).

### D-i9-5: `check/wordpress/` package shape

One module per check (D-i8-1 convention); `__init__.py` registers in this order
(preserves today's intra-set notice order — PAPC, sessions, OCP, favicon):

| Phase | Name | consumes | produces |
|---|---|---|---|
| `site_post_gather` | `check.wordpress.papc.check_papc` | `['framework', 'wordpress_plugins']` | `[]` |
| `site_post_gather` | `check.wordpress.sessions.check_native_php_sessions` | `['framework', 'wordpress_plugins']` | `[]` |
| `site_post_gather` | `check.wordpress.ocp.check_ocp_config` | `['framework', 'wordpress_plugins']` | `[]` |
| `site_post_gather` | `check.wordpress.favicon.check_favicon` | `['framework', 'fqdns_not_behind_cloudflare']` | `[]` |

Every hook early-returns unless `site_context["framework"].startswith("wordpress")`
(the branch condition the code sat inside). `papc`/`sessions` call
`sc.check_wordpress_plugin(site["name"], site_context["wordpress_plugins"], …)` — the
contract's None (non-list) is handled by the builder's existing non-list early return,
same outcome as today's raw-value pass. `ocp` iterates `wordpress_plugins` (early
return on None) exactly as the old loop did — per matching `object-cache-pro` entry,
active only — and probes via `sc.wp_eval(live_site, …)`; `favicon` probes
unconditionally (for WP frameworks) via `sc.wp_eval` and notices only on
`startswith("false")` + non-empty `fqdns_not_behind_cloudflare`. Both build failure
notices with `sc.wp_error` and rebind `site_context["wp_smell"]` on non-fatal stderr
(D-i9-3). `live_site` is derived as `site_context["site"]["id"] + ".live"` (the I8
`updates.py` precedent). Config gate (§5, D-i8-6 shape):

```python
if sc.config.get("Check", {}).get("wordpress", {}).get("enabled", True) is not False:
    …imports + 4 add_hook calls…
else:
    sc.console.print("[bold yellow] Skipping check.wordpress because it is disabled in the config")
```

Sample-config block (added after `[Check.pantheon]`):

```toml
[Check.wordpress]
enabled = true          # PAPC, native-PHP-sessions, OCP-config, favicon checks
```

### D-i9-6: `check/umich/` gains the two WP plugin checks — a deliberate gating change

`oidc_login.py` (`check_oidc_login`) and `hummingbird.py` (`check_hummingbird_fork`),
both `site_post_gather`, `consumes ['framework', 'wordpress_plugins']`, registered
after `cloudflare_cms` under the existing `[UMich].enabled` gate. Both gate on
WP framework + non-None plugins, iterate/filter exactly as the old loop did (oidc:
per matching active entry with `semver.compare(v, "1.2.99") <= 0`; hummingbird:
`"umich" in p["version"]` filter, inactive→info / else alert). `semver` is imported by
`oidc_login.py`; `hummingbird.py` uses `sc.escape_url` + stdlib `html`.

**Behavior change (deliberate, ledgered):** today these run **un-gated** — a non-U-M
run with `umich-oidc-login` installed gets U-M-specific advice. §3.2 assigns them to
`check/umich/`, §5 says U-M-only checks require `[UMich].enabled`, and CLAUDE.md's
standing rule is that institution-specific behavior lives behind the umich packages —
so after I9 they run only for U-M. Consequences: for a non-U-M run, the
`umich-oidc-login-reinstall`/`unsupported-turned-off`/`unsupported` notices and their
`-notices.csv` rows no longer occur. NOT a §8 csv-*value* change (no value changes;
rows appear/disappear with config, like every gated check — the cachecheck precedent)
and NOT golden-affecting (proof in §6: the goldens run umich-disabled AND their fixture
data fires neither check; the checks make no subprocess calls, so fixture traffic is
identical). Invariant 3 moves in its intended direction (U-M content becomes gated).
CLAUDE.md's still-hardcoded-U-M list drops the oidc/Hummingbird entries.

### D-i9-7: notice ordering — the D-i8-3 analysis

`find_modules` sorts: `check.umich` imports before `check.wordpress`. Post-I9
`site_post_gather` registration order: `pantheon.updates`, `pantheon.php_eol`,
`umich.cloudflare_cms`, `umich.oidc_login`, `umich.hummingbird_fork`,
`wordpress.papc`, `wordpress.sessions`, `wordpress.ocp`, `wordpress.favicon` (no DAG
edges among them — consumes are all core-produced — so registration order holds, §4).

Today the six moved checks' notices are added **before** the phase fires; after I9
they are added during it, after `pantheon.*`/`umich.cloudflare_cms` output, and the
U-M pair now precedes the wordpress four (today: PAPC, sessions, oidc, OCP,
hummingbird, favicon, interleaved by plugin-list order for oidc/OCP). For a production
site where such notices co-occur **at equal severity**, the rendered within-tier order
and `-notices.csv` row order shift (row content, keys, shape unchanged — §8 structure
bar holds; B50's severity sort is stable, so cross-tier placement is unaffected).
Zero golden impact — proven in §6. Ledger-recorded, same as D-i8-3.

### D-i9-8: ratchet — born gated; `check/umich/` exclude narrowed; pyright inherited

`psh/gather.py` and `check/wordpress/` are new files, never in the exclude list —
born under broad ruff + (for `psh/gather.py`) the pyright gate. `ruff-broad.toml`'s
`"check/umich/"` entry is replaced by `"check/umich/sitelens.py"` and
`"check/umich/cloudflare_cms.py"` (the I8 enumeration precedent, one level deeper), so
the edited `__init__.py` and the two new U-M modules are gated; the two legacy siblings
stay grandfathered until I14. **Pyright scope stays `psh/` minus `_legacy.py`**
(D-i8-7 inherited: check hooks call runtime-assigned `sc` attributes — now including
`sc.wp_eval`/`sc.wp_error` — which pyright cannot see on `script_context`; typed façade
stubs remain out of campaign scope). I10 inherits both decisions.

### D-i9-9: `sc.wp_eval` + `sc.wp_error` façade additions

The relocated OCP/favicon checks need the wp_eval wrapper and the wp_error
notice-builder; checks import only `sc` (Invariant 9). Two lines in the exposure block
(`_legacy.py:459–466`, with the block's comment style), documented in CLAUDE.md's
runtime-exposed list, pinned by `test_documented_sc_facade_names_exist`. §3.5:
additions are fine; nothing is removed. `sc.wp` is NOT added — no relocated check
calls `wp()` (the plugin/theme list fetches stay in the gather core); adding it would
be dead façade surface (§17 Q4, the I2 `GatewayResult` reasoning).

### D-i9-10: discovered fix — the Hummingbird ATTENTION print interpolates the site dict

`_legacy.py:1776–1778` prints `f"… ATTENTION: {site} has {display_name} installed."`
— `{site}` is the whole site **dict**, spraying the full site record into the console
where every sibling print uses `site['name']`. stdout MAY improve freely (§8); §12
"fits scope, <30 min → fix now, note in ledger". The moved `hummingbird.py` uses
`site['name']`; the hook-seam test asserts the printed line contains the name and not
a dict rendering.

## 3. Module shapes (imports; no cycles)

- `psh/gather.py`: `import script_context as sc`; `from psh.gateway import wp, wp_eval,
  wp_error`; stdlib `html`, `pprint`, `typing.NamedTuple`; call-time `escape_url`
  bridge (§1). `_legacy.py` re-imports `check_wordpress_plugin`,
  `wordpress_network_url`, `gather_wordpress`, `WordPressGather` (no cycle: `_legacy` →
  `psh.gather` → `psh.gateway`).
- `check/wordpress/*`: `import script_context as sc` only (+ nothing else — `html` is
  not needed: the OCP/favicon notice bodies contain no `html.escape` call; implementer
  verifies against the moved bodies). No module-level mutable state (§3.4).
- `check/umich/oidc_login.py`: `sc` + `semver`. `check/umich/hummingbird.py`: `sc` +
  `html`.
- `psh/modules.py`: `CONTRACT` + `stuff_gather_contract` edits only.

## 4. Deliverables

- **A** — `psh/gather.py` + `_legacy.py` gather-region deletions, re-imports, and the
  D-i9-2 threading; `sc.wp_eval`/`sc.wp_error` exposure lines.
- **B** — `psh/modules.py` contract edits (D-i9-3); B48 repoint (`:2760`).
- **C** — `check/wordpress/` package (D-i9-5) + sample-toml block.
- **D** — `check/umich/` additions (D-i9-6) + `__init__.py` registrations.
- **E** — ratchet edit (D-i9-8).
- **F** — tests per §7.
- **G** — docs: CLAUDE.md, CAMPAIGN.md §8 amendment (D-i9-4), ledger entry,
  auto-memory.

## 5. Ratchet (§13) — expected findings, MUST be confirmed against real tool output

Predictions (PD#14 — run the tools; correct in the task report where reality differs):

- `T203` on the two verbose `pprint(plugins)`/`pprint(themes)` dumps and the must-use
  `pprint(p)` in `psh/gather.py` → `noqa` with reason (operator diagnostics, I8
  precedent).
- `C901`/`PLR0912`/`PLR0915` likely on `gather_wordpress` (~120-line body moves whole)
  → `noqa`, no algorithmic redesign (§3.1 whole-file-coverage rule).
- `PLC0415` on the `escape_url` bridge → `noqa` with the D-i6-2-style reason + I12
  pointer.
- `E741`/`F841`: none expected in the moved bodies; `FBT` n/a (no boolean params).
- `check/umich/__init__.py` newly gated: expect `I001` (import sorting) and possibly
  quote/format findings the ignore list doesn't cover → fix in place (registration
  behavior unchanged; the D-i8 blank-line-collapse precedent).
- `semver` orphan check in `_legacy.py` (expected orphaned → removed); `html`/`pprint`
  retained (other users).

## 6. Behavior bar (§8) application — golden-impact evidence

Verified 2026-07-21 against `tests/e2e/__snapshots__/*.ambr` and the fixture data:

- `grep` for `not-installed`/`turned-off`/`multiple-installed`/`no-favicon`/
  `umich-oidc`/`ocp-config`/`unsupported`/`version-check`/`plugin-list`/
  `favicon-check` over all four goldens → **0 hits** (none of the moved checks' notices
  render in any golden).
- Fixture facts (`tests/fixtures/terminus/231ebb47d4481445.json` +
  `d29a1d37be57a8ed.json` + the two eval fixtures): PAPC and native-sessions are
  installed+active (no notice); `umich-oidc-login` is active at a version >1.2.99 (no
  notice — and post-I9 the check doesn't even run, umich-disabled); no
  `object-cache-pro`; no umich Hummingbird; favicon eval returns `"false"` but
  `fqdns_not_behind_cloudflare` is `[]` (Cloudflare disabled) → no notice; framework is
  `wordpress` (not network) → B32 never fires.
- What the WP golden DOES render from this region: the **B39 add-on updates table**
  (`2 pending add-on updates`: `broken-link-notifier` + `umich-cloudflare`, plugin-list
  order) — so `add_on_updates` content and order (plugins then themes, list order) are
  golden-load-bearing and MUST be byte-preserved by the gather move.
- Subprocess traffic: identical fixture calls (same argv set; the replay shim is keyed
  by argv, not order). The six moved checks make no new calls; OCP probe fires only
  when `object-cache-pro` is present (not in fixtures); favicon eval still fires once
  per WP site (fixture exists).

Therefore the four goldens MUST stay byte-identical (Invariant 1). stdout ordering and
content changes (banner/debug timing under hooks, D-i9-10) are §8-free. `-notices.csv`
per-site row order may shift per D-i9-7; structure may not; values only per D-i9-4.

## 7. Tests (test-first at these seams)

**Seams (named per the Spine's spec bar):** the `gateway` conftest fixture
(`psh.gateway.run_terminus` — reaches `wp`/`wp_eval` inside `psh/gather.py` AND
`sc.wp_eval` inside hooks, since both resolve in the gateway module), `sc.SiteContext`
construction + direct hook invocation (the I8 `test_check_pantheon.py` pattern),
standalone module loading via `tests/helpers/checkload.py` / SourceFileLoader, syrupy
snapshots for notice bodies, and the four e2e goldens as the end-to-end pin. No new
mock surface is introduced.

Integration tier (new files; patterns: `test_traffic_flow.py`,
`test_check_pantheon*.py`):

- `test_gather_wordpress.py` — `psh.gather` via the `gateway` fixture +
  `sc.SiteContext`: happy path (version string stripped; plugins passed through;
  add-on updates plugins-then-themes in list order incl. `update_version` mapping;
  `results_entry` shape; smell `""`); version fatal → `version-check` notice +
  `"unknown"` + entry still written; plugin-list fatal → `plugin-list` notice +
  plugins None-equivalent; theme fatal → `plugin-list` notice (the existing csv code,
  moved verbatim); stderr on multiple fetches → last-wins smell;
  `wordpress_network_url` happy (stripped URL) / fatal (notice, `(None, "")`) /
  stderr (smell) / non-str result (None). RED comes free: the module doesn't exist
  until the move lands (I8 precedent for pure moves).
- `test_check_wordpress_init.py` — gating: section absent → 4 hooks at
  `site_post_gather` with the D-i9-5 declarations in order; `enabled = false` →
  nothing + skip message; default-true proof (`[Check]` absent entirely).
- `test_check_wordpress.py` — hook seams with `sc.SiteContext` + `gateway` fixture:
  papc/sessions (delegation to `sc.check_wordpress_plugin` with the contract values;
  non-WP framework → no call; plugins None → builder's early return); ocp (no
  matching plugin → **no wp_eval call**; active + config-true → `ocp-config-fix-needed`
  alert; config-false → none; inactive → no probe; fatal → `ocp-config-check` notice;
  stderr → `site_context["wp_smell"]` rebound); favicon (false + non-empty
  fqdns list → `no-favicon` warning; true → none; false + empty list → none; fatal →
  `favicon-check` notice; non-WP → no call); **the D-i9-4 precedence pin**: theme
  stderr in `wp_smell` at stuffing + OCP stderr + clean favicon → final
  `site_context["wp_smell"]` is OCP's (documents the new order deliberately).
- `test_check_umich_wp.py` — oidc (active + `1.2.99` → `umich-oidc-login-reinstall`
  warning; active + `1.3.0` → none; inactive → none; non-WP/None-plugins → none);
  hummingbird (active umich-fork → `unsupported,{name}` alert; inactive umich-fork →
  `unsupported-turned-off,{name}` info; non-umich version → none; **D-i9-10 pin**: the
  ATTENTION line prints `site['name']`, not a dict, via `recording_console`);
  registration: umich-enabled config registers both after `cloudflare_cms`,
  umich-disabled registers neither (the gating-change proof).
- `test_wordpress_notice_render.py` + `test_umich_wp_notice_render.py` — syrupy
  snapshots of every relocated notice body (papc builder's three variants via
  `psh.gather.check_wordpress_plugin`, ocp alert, no-favicon warning, oidc-reinstall,
  hummingbird alert + info): the Invariant-8 byte pins going forward (new snapshot
  files, not golden refreshes; move-time evidence is the extracted-block diff in the
  task report, I2 precedent).

Unit tier:

- `tests/unit/test_contract_registry.py` — the four new `site_post_gather` keys +
  extended `stuff_gather_contract` pin (including: stuffs the same `add_on_updates`
  object, not a copy).
- `test_house_rules.py` — `wp_eval`/`wp_error` join the documented-façade-names pin.

Existing suites, no weakening (implementer verifies): `test_hook_dag.py` (auto-loads
the new packages — proves the declarations validate), `test_check_umich_cloudflare_cms.py`
(may pin umich hook counts — adjust counts only, never assertions' substance), the four
goldens + `test_only_warn_e2e.py` + `test_unknown_framework_e2e.py` +
`test_recommendation_e2e.py` unchanged and green.

## 8. Acceptance (pasted at close, §16)

1. Full `./run-tests` (live tier if credentials present; else `--fast` + ledger note),
   all three gates, goldens byte-identical (`git diff <start-sha> --
   tests/e2e/__snapshots__/` empty).
2. `uvx ruff check --config ruff-broad.toml psh/gather.py check/wordpress/
   check/umich/__init__.py check/umich/oidc_login.py check/umich/hummingbird.py` →
   clean; `psh/modules.py` stays clean; pyright gate 0 errors.
3. Extracted-block byte-diff evidence for every moved literal region (the six check
   bodies + the gather fetch regions), pasted in the task reports.
4. The D-i9-4 §8 amendment applied to CAMPAIGN.md; ledger entry appended (§12
   template); CLAUDE.md/memory updated; sample-toml block present.
5. The D-i9-4 precedence pin and D-i9-10 pin green; `test_check_umich_wp.py` proves
   the gating change (umich-disabled → not registered).

## 9. Acceptance results

Run 2026-07-21 at close (Task 5), tree = the closing commit's content, increment base
`ecb4420`. Commits: `5a6654d` (Task 1), `309ebcf`+`0873c3a` (Task 2), `717e21f`
(Task 3), `fb92e9d` (Task 4), `d5c4bf8` (carried I8 rich-pprint fix), + the closing
docs commit.

**1. Full `./run-tests` — live tier RAN** (Terminus credentials present:
`ls ~/.terminus/cache/tokens/` → `markmont@umich.edu`); exit 0, all three gates:

```
$ ./run-tests --llm ; echo "exit=$?"
All checks passed!
All checks passed!
0 errors, 0 warnings, 0 informations
LLM_SUMMARY passed=910 failed=0 error=0 skipped=1 xfailed=0 xpassed=0
72 snapshots passed.
910 passed, 1 skipped, 4 warnings in 44.16s
exit=0
```

(The `--fast` baseline before Task 5 was 908 passed / 1 skipped / 2 deselected; the
full run's 910 = 908 + the 2 live-marked tests. The 1 skip is `test_db_credentials.py`'s
`importorskip("MySQLdb")` on this sqlite-only install. The `PendingDeprecationWarning`
from `semver.compare` in `check/umich/oidc_login.py` is pre-existing behavior moved
verbatim — ledgered as post-campaign cleanup.)

Goldens byte-identical across the whole increment:

```
$ git diff ecb4420 -- tests/e2e/__snapshots__/ | wc -l
0
```

(The new syrupy files live under `tests/integration/__snapshots__/`, as required.)

**2. Ratchet spot-checks** (plus `check/pantheon/` after the `d5c4bf8` fix):

```
$ uvx ruff check --config ruff-broad.toml psh/gather.py check/wordpress/ \
    check/umich/__init__.py check/umich/oidc_login.py check/umich/hummingbird.py \
    psh/modules.py check/pantheon/
All checks passed!
$ .venv/bin/pyright        # psh/ minus _legacy.py, per [tool.pyright]
0 errors, 0 warnings, 0 informations
```

**3. Extracted-block byte-diff evidence** — pasted in the task reports
(`.superpowers/sdd/task-2-report.md` § Byte-diff evidence, `task-3-report.md`
§ Byte-verbatim evidence, `task-4-report.md` § Extracted-region byte-diff evidence);
every difference is a named, sanctioned substitution.

**4. Docs:** the D-i9-4 §8 amendment applied to CAMPAIGN.md (csv-values row); LEDGER I9
entry appended (§12 template); CLAUDE.md updated (module map, package lists, contract
row incl. the Task-4 `""`-not-`"unknown"` accuracy fix, sc-façade list, ratchet
description, still-hardcoded-U-M list, Testing section); auto-memory updated (not
committed — lives outside the repo); `[Check.wordpress]` block present in
`sample-pantheon-sitehealth-emails.toml`.

**5. Named pins green** (inside the 910 above): the D-i9-4 precedence pin
(`test_ocp_stderr_beats_earlier_theme_smell_when_favicon_clean`), the D-i9-10 print pin
(ATTENTION line interpolates `site['name']`), and the D-i9-6 gating-change proof
(`test_umich_disabled_registers_neither_wp_check` /
`test_umich_enabled_registers_both_wp_checks_after_cloudflare_cms`).

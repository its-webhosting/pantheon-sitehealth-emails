# BLOCKMAP — functional map of `main()` (baseline a47418c)

The block-by-block map of `pantheon-sitehealth-emails` `main()` (lines 2108–4752) that the
campaign's increment assignments are built on. Line numbers are against commit `a47418c`
("prepare for modularization campaign") and will drift as increments land — **the block IDs
(B1–B60), not the line numbers, are the stable references** used by `CAMPAIGN.md` and the
increment specs. An increment that moves a block records it in `LEDGER.md` by block ID.

Produced 2026-07-17 by a very-thorough read of `main()`; bug claims in B40/B47/B48/B51 were
independently re-verified against the source before this file was written.

Helper functions called by `main()` but defined elsewhere in the same file: `build_traffic_table_rows`
(1002), `plan_costs` (1128), `update_traffic_rows` (1393), `load_traffic_rows` (1447),
`insert_traffic_rows` (1428), `load_overage_protection_window` (1488), `finish_run` (1649),
`abort_run` (1913). The two report table-column globals are module-level:
`traffic_table_columns` (68), `cost_table_columns` (85).

Already extracted before this campaign (NOT in main()): SiteLens, DNS-resolution notices,
umich-cloudflare CMS checks, Cloudflare FQDN loading — all hook packages.

## Pre-loop setup (runs once)

| ID | Lines | What it does | Classification | Config read |
|---|---|---|---|---|
| B1 | 2110–2116 | Config load (tomllib) + `gate_disabled_sections()` | generic | whole file |
| B2 | 2118–2122 | Import `plugin/` packages → `sc.plugin` | generic | — |
| B3 | 2124–2125 | Pass-1 `process_config()` substitution | generic | — |
| B4 | 2127–2131 | Import `check/` packages → `sc.check` | generic | — |
| B5 | 2133–2162 | Arg validation (`--resume-from` guards, sites-or-all, fqdns flag) | generic | `[Cloudflare].enabled` |
| B6 | 2164–2168 | Verbose banner; `terminus("self:info")` | generic | — |
| B7 | 2170–2174 | `build/` dir; `invoke_hooks("setup")` | generic | — |
| B8 | 2176–2180 | Deferred-pass `process_config()` | generic | — |
| B9 | 2182–2183 | Overage constants | generic-Pantheon | `[Pantheon].overage_*` |
| B10 | 2185–2202 | DB engine + sessionmaker (`expire_on_commit=False`) | generic | `[Database]` |
| B11 | 2204–2206 | `--create-tables` short-circuit (`create_all`, exit) | generic | — |
| B12 | 2208–2228 | Wordmark image read; `load_news_items()`; `plan_info` normalization (`"-"`→None), `plan_names` | generic-Pantheon | `[Pantheon].plan_info`, `[News]` |
| B13 | 2230–2246 | Date window (`end_date`, `start_date`, `contract_year_end`); numpy chart-cap geometry | generic (cap geometry chart-specific) | — |
| B14 | 2248–2285 | `terminus_data("org:site:list")`; run accumulators (`emails_sent`, `site_savings`, `all_warnings`, `site_results`); `smtp_enabled`; sorted site names; `sites_from_resume_point` | generic | `[Pantheon].org_id`, `[SMTP].enabled` |

## Per-site loop (2289–2720 body refs; wrapped in `try`/`except BaseException`)

| ID | Lines | What it does | Classification | Emits notices (csv code) |
|---|---|---|---|---|
| B15 | 2290–2304 | Smell resets; U-M portal gate (`[UMich].portal.sites`), `portal_site_id` | **U-M** | — |
| B16 | 2306–2321 | Site-selection skip + banner | generic | — |
| B17 | 2323–2349 | Elite plan SKU → name via `terminus("plan:info")`, `plan_sku_to_name` | generic-Pantheon | — |
| B18 | 2351–2358 | Sandbox skip; `SiteContext` creation | generic | — |
| B19 | 2360–2387 | Frozen-site notice | generic (U-M link in body) | `frozen` (alert) |
| B20 | 2389–2394 | Unknown-plan guard (`sys.exit`) | generic | — |
| B21 | 2396–2442 | `terminus("env:list")` → `envs`; live-env validation | generic-Pantheon | `no-live-env-but-paid-plan` (alert) |
| B22 | 2444–2452 | `terminus("env:metrics")` traffic gather | generic-Pantheon | — |
| B23 | 2454–2460 | `db_retry(update_traffic_rows)` — DB WRITE | generic | — |
| B24 | 2462–2476 | `--import-older-metrics`: `get_old_metrics` + `insert_traffic_rows`, `continue` | generic | — |
| B25 | 2478–2480 | `--update` early `continue` | generic | — |
| B26 | 2482–2497 | `db_retry(load_traffic_rows)` → `results` (commit releases conn) | generic | — |
| B27 | 2499 | `invoke_hooks("site_pre")` | seam | — |
| B28 | 2501–2506 | Stuff `traffic_rows`/`start_date`/`end_date`; `invoke_hooks("site_post_traffic")` | seam | — |
| B29 | 2508–2561 | `terminus("domain:list")`; `dns_classify.classify_domains` → `facts` | generic, CF-aware | `no-domains` (alert) |
| B30 | 2562–2621 | Primary-domain check; Drupal multisite probe (`drush_php_script`) | framework-branching | `no-primary-domain` (info); `multisite-check` (error path) |
| B31 | 2623–2630 | `stuff_dns_contract`; `invoke_hooks("site_post_dns")`; `site_url` | seam | — |
| B32 | 2632–2655 | WP-network `network_home_url()` via `wp_eval` | WordPress | `version-check` (error path) |
| B33 | 2657–2667 | Gather init (`plugins`/`mods`/versions None; `add_on_updates=[]`) | generic | — |
| B34 | 2668–2984 | WordPress branch: version, plugin list, PAPC + native-sessions checks, per-plugin loop (updates; **umich-oidc-login**; **object-cache-pro** probe; **Hummingbird fork**), theme list, favicon | WordPress; oidc+Hummingbird **U-M** | `umich-oidc-login-reinstall` (warn), `ocp-config-fix-needed` (alert), `unsupported-turned-off`/`unsupported`, `no-favicon` (warn); error paths `version-check`, `plugin-list`, `ocp-config-check`, `favicon-check` |
| B35 | 2986–3302 | Drupal branch: core-status, pm:list, PAPC module check, **D7 EOL** + tag1_d7es, pm:updatestatus (D7) / composer dry-run+audit (D8+), **Drupal UA check** | Drupal; UA check **U-M** | `drupal7-eol` (alert), `composer-update` (alert), `drupal-ua` (info); error paths `core-status`, `pm-list`, `pm-updatestatus`, `drupal-ua-check` |
| B36 | 3303–3306 | Unknown-framework fallback (print only; **no `site_results` entry** — see Bugs) | generic | — |
| B37 | 3308–3320 | Stuff gather contract keys; `invoke_hooks("site_post_gather")` | seam | — |
| B38 | 3322–3489 | `terminus("upstream:updates:list")` → update table + age-tiered notice | generic-Pantheon | `updates-info`/`updates-warning`/`updates-alert` |
| B39 | 3491–3566 | Add-on updates table from `add_on_updates` | generic | `updates-addons` (warn) |
| B40 | 3568–3634 | **DEAD**: commented-out PHP-runtime-Gen2 notice (pre-SiteContext idiom) | dead | — |
| B41 | 3636–3694 | PHP EOL check on `envs["live"]["php_version"]` | generic-Pantheon | `php-eol` (**same code for warn and alert branches** — see Bugs) |
| B42 | 3696–3702 | `--only-warn`: dump csv codes to `all_warnings`, `continue` (TODO at 3698: run plan rec first) | generic | — |
| B43 | 3704–3742 | `visits_by_month`, `plan_on_day`, `build_plan_over_time` | generic | — |
| B44 | 3744–3801 | Chart data prep (`estimate_month_visits`, surge threshold, ymax) | generic-Pantheon | — |
| B45 | 3803–4113 | Matplotlib chart build → `chart_image` (BytesIO PNG) | generic-Pantheon | — |
| B46 | 4117–4156 | `db_retry(build_traffic_table_rows)` — DB read + commit | generic-Pantheon | — |
| B47 | 4158–4333 | Cost model: `load_overage_protection_window` → `plan_costs` → recommendation, savings, cost table. **Un-gated U-M portal URLs at 4240/4275** — see Bugs | generic-Pantheon (**U-M leak**) | `its-recommends-plan` (info) |
| B48 | 4335–4408 | Smell notices (`wp_smell`, `drush_smell`, `composer_smell`). **composer block nested in drush block + interpolates `drush_smell`** — see Bugs | generic | `wp-smell`/`drush-smell`/`composer-smell` (info) |
| B49 | 4410–4431 | Recipients: U-M portal owner groups OR `terminus("site:team:list")` | **U-M** branch + generic | — |
| B50 | 4433–4520 | Notice sort (alert→warn→info); subject; **annual-billing notice** on contract-year end | **U-M** (annual billing) | `annual-bill` (alert) |
| B51 | 4522–4555 | Second annual-billing notice, marked "remove Aug 2026" (**duplicate `annual-bill` csv code**) | **U-M**, temporary | `annual-bill` (alert) |
| B52 | 4557–4559 | `invoke_hooks("site_pre_render")` | seam | — |
| B53 | 4561–4608 | `make_msgid` CIDs; template dict; Jinja render → `build/{name}.html`/`.txt` | generic | — |
| B54 | 4610–4633 | PHP Emogrifier inline + `!important` regex → `-inline.html`/`-inline2.html` | generic | — |
| B55 | 4635–4696 | MIME assembly (`[Email]` config, dry-run addressing, banner/chart CIDs, attachments) → `.eml` | generic (U-M defaults) | — |
| B56 | 4698–4707 | Notice rows → `all_warnings` (deliberately BEFORE send — resume safety) | generic | — |
| B57 | 4709–4715 | SMTP send (gated `[SMTP].enabled`) | generic | — |
| B58 | 4717–4720 | `plt.close(fig)` (redundant — already closed at 4113); TODO markers | generic | — |

## Loop exit / finish (runs once)

| ID | Lines | What it does |
|---|---|---|
| B59 | 4721–4737 | `except BaseException` → `abort_reason` → `abort_run` (single flush path) |
| B60 | 4739–4747 | `finish_run` (sole writer of run artifacts) |

## Wrapper usage by block

- `terminus` (raw): B6, B17, B21, B22, B29, B35 (composer audit), B38, B49; inside `get_old_metrics` (B24)
- `terminus_data`: B14 · `run_terminus` (list form): B35 (composer dry-run)
- `wp`: B34 (plugin list, theme list) · `wp_eval`: B32, B34 (version, OCP probe, favicon)
- `drush`: B35 (core-status, pm:list, pm:updatestatus) · `drush_php_script`: B30, B35 (UA check)

DB session touches (all through `db_retry` except schema): B10, B11, B23, B24, B26, B46, B47, B59, B60.

## Bugs and smells found during mapping (all re-verified in source)

1. **B48 composer-smell double bug (4385–4408):** the `if composer_smell != "":` block is
   nested inside `if drush_smell != "":`, so composer smells are only reported when a drush
   smell also exists; and the HTML `message` interpolates `{drush_smell}` (4395) where
   `{composer_smell}` is meant. (The plaintext `text` uses the right variable.)
2. **B41 shared `php-eol` csv code:** warning (7.4/8.1) and alert (<8.2) branches emit the
   identical `csv={name},php-eol`, so the notices CSV cannot distinguish severity.
3. **B36 `site_results` omission:** only the framework branches (B34 at 2690, B35 at 3009)
   create a site's `site_results` entry; an unknown-framework site silently vanishes from
   the results artifact (and from `monthly-report.txt`'s stats).
4. **B47 un-gated U-M URLs (4240, 4275):** the Basic-alternative and recommendation notice
   bodies embed `admin.webservices.umich.edu/sites/{portal_site_id}/plan/` without a
   `umich_enabled()` guard; non-U-M runs would render a broken U-M URL with
   `portal_site_id = 0`.
5. **B50/B51 duplicate `annual-bill` code:** both notices emit the same csv code and both
   `insert(0, …)`; on a contract-year U-M run a site gets two `annual-bill` rows that the
   CSV cannot tell apart. B51 is marked for removal August 2026.
6. **Dead code:** B40 (3568–3634) entire commented-out Gen2 notice (uses the removed
   `site_notices.append` idiom, cannot be revived as-is); commented overage debug query
   (4124–4133); redundant second `plt.close(fig)` (4717, already closed at 4113);
   commented `plt.show()` (4107).
7. **WordPress/Drupal duplication:** version-fetch→`site_results`, add-on-update
   collection, and the `*_error`/`*_smell` pattern are re-implemented per framework; the
   PAPC recommended-add-on check exists as both `check_wordpress_plugin(…)` and
   `check_drupal_module(…)` calls.
8. **Update-table HTML duplication:** B38 and B39 each build near-identical responsive
   update tables; B38's three severity bodies largely overlap.
9. **In-code TODO markers** (seams for extracted modules, not dead code): no-Autopilot
   warning (3696), plan-rec before `--only-warn` (3698), SVG chart (4115), traffic-table
   icons/coloring (4119–4122), Basic-plan performance-feature detection (4220–4221),
   %-pages-cached + CSV attachment (4719–4720).

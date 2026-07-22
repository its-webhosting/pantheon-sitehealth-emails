# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`pantheon-sitehealth-emails` is a standalone Python script that pulls traffic and
site-health data from [Pantheon](https://pantheon.io/) hosting (via the Terminus CLI,
WP-CLI, and Drush), stores traffic history in a database, and emails each site owner a
monthly report with a plan-cost recommendation. It is used by University of Michigan ITS
Web Hosting Services and is written to be reusable by other institutions via a config file.

## Commands

The whole tool is invoked through one executable, `./pantheon-sitehealth-emails` (run it
directly; it has a `#!/usr/bin/env python` shebang and expects the venv active). It is now a
thin shim that calls `psh.cli.main()`; the program body lives in the `psh` package
(`psh/_legacy.py` until the modularization campaign finishes carving it into `psh/` modules —
see **Modularization campaign** under Architecture). Invocation is unchanged. There is no build
step; for the test suite see **Testing** below.

```bash
# Environment (see README.md for full first-time setup with uv/PHP/mysql/aws)
source .venv/bin/activate
uv pip install .[mysql,aws,cloudflare]   # Python deps; drop features you don't use
composer install                          # installs the PHP Emogrifier CSS inliner

# One-time: create database tables (uses [Database] section of the .toml)
./pantheon-sitehealth-emails --create-tables

# Weekly: refresh visitor counts in the DB without generating reports
./pantheon-sitehealth-emails --update --all

# Monthly report run (--date should be the LAST day of the reporting month):
./pantheon-sitehealth-emails --date 20240731 its-wws-test1   # single site, safe test
./pantheon-sitehealth-emails --date 20240731 --all           # dry run: emails go to YOU
./pantheon-sitehealth-emails --date 20240731 --all --for-real # sends to site owners

./pantheon-sitehealth-emails --help
```

Key flags (the parser sets `allow_abbrev=False`, so no `--for` → `--for-real` foot-gun):
`--all` vs. an explicit `SITE` list are mutually exclusive (one is required
unless `--create-tables`); `--config`/`-c` picks the TOML file (default
`pantheon-sitehealth-emails.toml`). Without `--for-real`, mail is addressed to the logged-in user,
not to owners — this is the primary safety mechanism, always dry-run first. `--update`
only refreshes traffic data; `--only-warn` checks sites for warnings — including the plan
recommendation, computed before the gate since D7 (campaign I7) — without generating
reports or sending mail; `--import-older-metrics` backfills Pantheon's weekly/monthly
aggregates (and is mutually exclusive with `--create-tables`); `-v`/`-vv`/`-vvv` increase
verbosity (`--create-tables` forces `-vvv`). `--update-cloudflare-fqdns` /
`--no-update-cloudflare-fqdns` (mutually exclusive) force / suppress the `fqdns.json` refresh
(Cloudflare plugin; see the fqdns note under Architecture). `--allow-any-source-ip` skips the
`[Cloudflare.cachecheck]` egress-IP allowlist test (see the cachecheck note under Architecture).
`--resume-from SITE_NAME` (requires `--all`) starts the sorted site loop at that site, inclusive
— for resuming an interrupted `--all` run (see the resume note under Architecture).

## Required runtime credentials / external tools

Running against real sites needs, in the environment: `terminus` authenticated with a
Pantheon machine token; an SSH agent holding the Pantheon key (`ssh-add`); `SMTP_PASSWORD`
(U-M Kerberos password, referenced by `[SMTP].password = "<{secret env SMTP_PASSWORD}"`);
optionally `AWS_*` and `CLOUDFLARE_EMAIL`/`CLOUDFLARE_API_KEY` (or `CLOUDFLARE_API_TOKEN`),
referenced by the `[Cloudflare]` settings. **Credentials are never read from the environment
by feature code**: everything flows through config `<{env …}>` / `<{secret env …}>`
substitutions (see the config-substitution note under Architecture). The only direct
`os.environ` touches are `plugin/env/get_env.py` (which *is* the `<{env}` engine) and the
`AWS_PROFILE`/`AWS_DEFAULT_REGION` boto plumbing in `plugin/aws/__init__.py` — don't add more.
See `docs/env-and-smtp-configuration.md` and `docs/email-configuration.md`.
`php` + `composer` must be on PATH. Note the
README warning: Terminus does not work with PHP 8.4 — use PHP 8.3 or earlier.

## Architecture

### Modularization campaign (in progress)

The several-thousand-line main script is being modularized into a `psh/` core package,
self-registering `check/`/`plugin/` packages, and a ~250–400-line `main()` orchestrator, across
15 increments (I0–I14), while the four e2e goldens stay byte-identical. Until it completes, the
program body lives in `psh/_legacy.py` and the sections below describe the **pre-campaign** layout
(this file is rewritten wholesale at I14, not incrementally). Anyone starting an increment session
reads, in full, that increment's governing documents in
`development/2026-07-17-modularization-campaign/`: **`CAMPAIGN.md`** (the frozen architecture,
decisions, and invariants — increment specs cite it by section number and re-derive nothing),
**`LEDGER.md`** (append-only cross-increment record — how each increment learns what the last one
actually did), **`BLOCKMAP.md`** (the B1–B60 functional map of `main()` that all scope
assignments reference), plus this `CLAUDE.md`. Architecture changes are amendments: edit
`CAMPAIGN.md` *and* append a `LEDGER.md` entry — never a silent divergence.

### Single-module core + `script_context` shared state

Nearly all logic lives in the top-level `pantheon-sitehealth-emails` script (~3900 lines).
Seven modules are carved out. **`psh/gateway.py`** is the gateway: every Terminus/WP-CLI/Drush
subprocess flows through it (the eleven wrappers moved there in I2; the future Pantheon-API
transport seam — see the **Terminus/WP/Drush wrappers** bullet). **`psh/configuration.py`**
(moved in I3) is the config engine — `process_config`/`config_substitution`/
`gate_disabled_sections`/`load_news_items`/`umich_enabled`/`cloudflare_enabled` plus the DEFER
machinery (see **Config substitutions** below) — re-imported by `psh/_legacy.py`, so call
sites and the `sc.umich_enabled`/`sc.cloudflare_enabled` exposure assignments resolve
unchanged (same import-back pattern I2 used for the gateway). **`psh/notice.py`** (new in I3)
holds `Notice` (a frozen dataclass), `Severity` (a `StrEnum`), `NoticeRegistry`, and
`DuplicateNoticeCodeError` — the typed replacement for the ad-hoc notice dict (see **Notices
vs. news** below); it imports nothing from `script_context`, so both `sc` and every `psh/`
module can import it without a cycle. **`psh/modules.py`** (new in I4) is module discovery +
the hook engine: `find_modules`, `PHASES`, `add_hook`/`invoke_hooks`, the consumes/produces
DAG validation (`validate_hooks`/`ordered_hooks`, the `HookDagError` family), the
authoritative `CONTRACT` registry, and the `stuff_traffic_contract`/`stuff_gather_contract`
stuffers (see **Hooks** and the data-contract table below). Its import direction is the
inverse of the notice module's: `script_context.py` re-exports `PHASES`/`add_hook`/
`invoke_hooks` via a top-of-file `from psh.modules import …`, so `psh/modules.py` must NOT
import `script_context` at module level — its engine functions import `sc` at call time
(the module docstring carries the diagram; the mutable `sc.hooks` dict deliberately stays
in `script_context.py`, because `reset_sc` rebinds it around every test and CAMPAIGN.md
§3.4 bars new module-level mutable state in `psh/`). **`psh/db.py`** (moved in I5) holds
every DB touch this program makes: the SQLAlchemy models (`Base`, `PantheonTraffic`,
`PantheonOverageProtection`), the row types (`TrafficRow`, `OverageProtectionRow`), the
resilience layer (`db_retry`, `db_retryable`, `record_db_reconnect`,
`DatabaseUnavailableError`), the read/write units (`update_traffic_rows`,
`insert_traffic_rows`, `load_traffic_rows`, `load_overage_protection_window`), and
`db_engine_args` — re-imported by `psh/_legacy.py`, same import-back pattern as the
gateway/configuration modules, so call sites and the `sc.db_engine_args` exposure
assignment resolve unchanged. The two reconnect counters (`db_reconnects_by_site`,
`db_reconnect_failures_by_site`) do NOT live in `psh/db.py`: they're `script_context.py`
module-level attributes (`sc.db_reconnects_by_site`/`sc.db_reconnect_failures_by_site`),
because `db_retry` (now in `psh/db.py`) and the remnant readers `finish_run`/`abort_run` (staying in
`psh/_legacy.py` until I13) need one shared, `reset_sc`-isolated namespace rather than two
separately rebindable module bindings of the same name (the I2 `run_terminus`-seam lesson
— see § Database's test-seam note below). This is their scheduled interim home; I13's
`RunState` is where they finally land. **`psh/traffic.py`** (moved in I6) holds the
traffic-metrics layer: the move set (`traffic_table_columns`, `get_old_metrics`,
`estimate_month_visits`, `build_traffic_table_rows`) plus four flow functions extracted from
`main()`'s per-site loop (`update_site_traffic`, `import_older_site_metrics`,
`load_site_traffic`, `aggregate_visits_by_month`) — re-imported by `psh/_legacy.py`, same
import-back pattern as the gateway/configuration/db modules, so `main()`'s call sites and the
`psh.<name>` test references resolve unchanged. `build_traffic_table_rows` calls
`overage_blocks` via a module-level `from psh.plans import overage_blocks` (the I6 bridge —
a call-time import guarded by `# noqa: PLC0415` — discharged at I7 per its own obligation).
**`psh/plans.py`** (moved in I7) holds the plans layer: the move set
(`cost_table_columns`, `overage_blocks`, `contract_year_end`, `plan_costs`,
`build_plan_over_time`, `build_plan_recommendation_notice`) plus the new typed
`PlanCatalog`/`PlanInfo` view over `[Pantheon].plan_info` (`PlanCatalog.from_config`
performs the legacy `"-"` → `None` normalization **mutating the config sub-dict in
place**, so `main()`'s `plan_info`/`plan_names` aliases and the chart/annual-billing
regions keep reading the same object — a copy would fork two views of one config),
`resolve_plan_name(site)` (the B17 Elite-SKU lookup, `None` on a transient Terminus
failure so `main()` can `continue`, `sys.exit` preserved on a missing/unknown SKU), and
`recommend_plan(...)` (the B47 recommendation core, returning a frozen
`PlanRecommendation` — `current_plan`/`recommended_plan`/`cost_same`/`costs_median`/
`costs_best`/`cost_table_rows`/`savings`/`savings_entry` fields, the last appended to
`main()`'s `site_savings` accumulator when not `None` — and adding the upgrade notice to
`site_context` itself, the I6 flow-function pattern) plus `stuff_plans_contract()` (which
`main()` calls with the `cost_same`/`costs_median`/`costs_best` fields nested into the
single `plan_costs` **contract key** — `{"same": ..., "median": ..., "best": ...}` — not a
`PlanRecommendation` field of that name) (the `dns_classify.stuff_dns_contract` producer-
module precedent, publishing the four `site_pre_render` contract keys below) — all
re-imported by `psh/_legacy.py`, same import-back pattern as the other moved modules, so
`main()`'s call sites and the `psh.<name>` test references resolve unchanged.
**`psh/gather.py`** (new in I9, Drupal half added in I10) holds the framework gather cores.
The WordPress side (I9): `check_wordpress_plugin`
(the recommended-plugin notice builder the papc/sessions/cloudflare_cms hooks call via
`sc.check_wordpress_plugin`), `wordpress_network_url` (the B32 network-URL fetch), and
`gather_wordpress` (the B34 gather core: version / plugin-list / theme-list fetches,
add-on-update collection plugins-then-themes in list order, the must-use diagnostic
print) returning a **`WordPressGather`** NamedTuple (`wordpress_version` / `plugins` /
`add_on_updates` / `wp_smell` / `results_entry`) that `main()` threads into its locals —
the returned smells participate in `main()`'s last-wins overwrite semantics (a later
empty smell never clears an earlier one, so `main()` rebinds `wp_smell` only when the
returned smell is non-empty). The Drupal side (I10): `check_drupal_module` (the
recommended-module notice builder its Drupal siblings call via `sc.check_drupal_module`),
`gather_drupal` (the B35 gather core: banner + core-status fetch + version derivation +
`site_results` entry, pm:list, and the D7 pm:updatestatus **or** D8+ composer dry-run +
composer audit add-on collection — the D7-vs-D8+ branch stays inside because it selects
between two *gather* strategies, not between checks) returning a **`DrupalGather`**
NamedTuple (`drupal_version` / `modules` / `add_on_updates` / `drush_smell` /
`composer_smell` / `results_entry`; `main()` threads it last-wins exactly like the WP
branch), and `build_smell_notices` (the B48 smell-notice *builder*; **its emission stays
in `main()`** — LEDGER I10 amendment 1 — because it summarizes end-of-phase smell state no
hook position can guarantee and must stay behind the `--only-warn` gate; the I10 move also
de-indented its composer literal to column 0, matching the wp/drush siblings — the LEDGER
I1 Obs. 4 fix, D-i10-8). The `wp_error`/`drush_error` notices for *failed gathers* stay
with the fetches (they describe the gather, not a check); the notice-emitting checks that
used to be interleaved here live in `check/wordpress/`, `check/drupal/`, and `check/umich/`
(below). `escape_url`
is reached via a call-time bridge import from `psh._legacy` (`# noqa: PLC0415`, the
D-i6-2 precedent — replaced by a module-level `from psh.render import escape_url` when
I12 moves it there). Re-imported by `psh/_legacy.py`, same import-back pattern, so
`main()`'s call sites and the `sc.check_wordpress_plugin`/`sc.check_drupal_module`
exposure lines resolve
unchanged. The last is
**`dns_classify.py`**, the DNS engine: it resolves each
domain's A/AAAA records and classifies them against the Cloudflare IP ranges
(`classify_domains`, returning a `DnsFacts` NamedTuple), and `stuff_dns_contract()` publishes
those facts into the `site_post_dns` data-contract keys (below). It is a pure data producer —
presentation (notices) lives in `check/dns/`, not here. Cross-cutting state and helpers live
in **`script_context.py`** (imported everywhere as
`sc`): `sc.options` (parsed argv), `sc.config` (parsed TOML), `sc.plugin`/`sc.check`
(loaded modules), `sc.news`, `sc.console` (rich), `sc.hooks`, `sc.substitutions`,
`sc.Notice`/`sc.Severity` (the `Notice`/`Severity` names reach `sc` via a plain module-level
`from psh.notice import Notice, Severity` at the **top** of `script_context.py` — a
module-level import makes both names module attributes automatically, so this is NOT one of
the explicit `sc.<name> = <name>` assignments in `_legacy.py`'s sc-exposure block, unlike
`sc.umich_enabled`/`sc.cloudflare_enabled` above), and
helpers `debug()`, `add_news_item()`, `html_to_text()` (notice-adding
is now a `SiteContext` method, below; `add_hook()`/`invoke_hooks()` moved to `psh/modules.py`
in I4 and reach `sc` via the same top-of-file import mechanism as `Notice`/`Severity`). **`html_to_text()` builds a fresh `HTML2Text` per call** —
never reintroduce a shared instance: it is stateful, and sharing one made the first notice of a run
render in a different link style from every other (the module-level `sc.text_maker` it replaced is
gone). The parser is built by `build_arg_parser()` and `sc.options`
is populated by the caller via `parse_args()` before other functions run, so it is
available to every function at call time.

### Plugin / check module system (`plugin/`, `check/`)

`find_modules()` (in `psh/modules.py` since I4) walks `plugin/` and `check/` for **non-empty `__init__.py`** files (the
empty top-level `plugin/__init__.py` and `check/__init__.py` are skipped) and imports each
containing package (currently `plugin.aws`, `plugin.cloudflare`, `plugin.env`, `plugin.umich`,
`check.addon_updates`, `check.cloudflare`, `check.dns`, `check.drupal`, `check.pantheon`,
`check.pantheon_cdn_change`, `check.umich`,
`check.wordpress`). Each `__init__.py` self-registers at import time — usually pulling in a
sibling file with the actual logic (`aws/get_secret.py`, `cloudflare/ips.py`, `env/get_env.py`,
`umich/portal.py`, `check/umich/sitelens.py`) — guarded by a check of `sc.config` (e.g.
only register if `[Cloudflare].enabled`). **Exception:** `plugin.env` (the `<{env NAME}` /
`<{secret env NAME}` substitutions, with an optional trailing default) registers
**unconditionally** — no `[Env]` section — because it has no dependency and core config
(`[SMTP].username = "<{env USER}"`) needs it. Modules register by:
- **Hooks** — `sc.add_hook('<phase>', {'name': …, 'func': …, 'consumes': […], 'produces': […]})`.
  The `consumes`/`produces` declarations are **mandatory** (each a possibly-empty list of
  data-contract key names, table below; missing/malformed → fatal at registration, no legacy
  mode — CAMPAIGN.md §4 condition 5). Phases are the ordered
  `sc.PHASES` tuple: `setup` (once per run — **including `--create-tables`**, which exits
  later), then per site `site_pre` (rename of the old `check` seam), `site_post_traffic`,
  `site_post_dns`, `site_post_gather`, `site_pre_render`, and per run `run_finish` (fired as
  the first statement of `finish_run()` — before any teardown or artifact write, on completed
  AND aborted runs; no arguments until I13's `RunState`; no consumer yet). Each site phase
  receives the `SiteContext`; the per-phase guaranteed keys are the data-contract table below.
  Bare names not in `PHASES` are a **fatal error** in both `add_hook` and `invoke_hooks`;
  dotted names (e.g. `setup.umich.portal`) are plugin-defined events, allowed and
  invoked by whoever owns them — but they MUST declare `consumes`/`produces` **empty**
  (contract keys are phase-anchored; a dotted event has no phase position). After the module
  import loops, `main()` runs `psh.modules.validate_hooks()`, which is **fatal** (named
  `HookDagError` subclasses) on: a consumed key nothing produces; two producers of one key
  (hooks or the core `CONTRACT` registry — one owner per key); a consumes/produces cycle among
  same-phase hooks; consuming a key first produced in a *later* phase (earlier is fine).
  Within a phase `invoke_hooks` runs producers before consumers (registration order breaks
  ties, so today's edgeless DAG — the `check.drupal.multisite` produced keys have no hook
  consumer — preserves registration order exactly); the permanent
  `tests/integration/test_hook_dag.py` loads every real check/plugin package (via its
  `ALL_PACKAGES` list) and proves the
  DAG validates. **This claim was FALSE I8→I10:** `ALL_PACKAGES` was last touched at I4 and
  silently missed `check/pantheon` (I8) and `check/wordpress` (I9); I10 restored it (adding
  `pantheon`, `wordpress`, `drupal`, `addon_updates`), so it again loads every package —
  keep it in sync when adding a package. Gating: phases through `site_post_gather` run on
  full-report and `--only-warn` paths; `site_pre_render` full-report only; `--update`/
  `--import-older-metrics` never reach any site phase (they DO reach `run_finish`, whose
  artifact writes are separately gated); a per-site fatal error (e.g.
  domain:list failure) skips that site's remaining phases.
- **Config substitutions** — appending to `sc.substitutions`. TOML string values
  containing `<{ ... }>` are resolved by `process_config()`/`config_substitution()`
  against these registered functions. `process_config()` is run twice: a pre-setup pass resolves
  everything, then a post-setup `deferred_pass=True` pass re-resolves **only** substitutions that
  deferred. A substitution whose backing data a `setup` hook populates (e.g. `plugin.umich`'s
  `plan_info`, which needs the portal DB) returns the `sc.DEFER` sentinel; `config_substitution`
  re-emits its marker with an invisible NUL tag that only the deferred pass matches. This is what
  lets pass 2 resolve deferrals **without** re-interpreting a pass-1 final value that merely
  contains a `<{…}>` sequence (e.g. a password) — so route secrets through substitutions freely.
  A substitution function aborts the run by raising `sc.ConfigSubstitutionError` (caught in
  `config_substitution`, which prints the offending config *path* + message and exits) — this is
  how `plugin.env.get_env` (missing env var) and `plugin.aws.get_secret` (missing secret key) both
  report failures. Just before those substitutions run,
  `main()` calls `gate_disabled_sections()`: any section **at any depth** with `enabled = false`
  (boolean identity; nested tables like `[Cloudflare.cachecheck]` included, and a disabled
  parent drops its children entirely) is reduced to just `{'enabled': False}`, dropping its
  other keys **before**
  substitution — so a disabled feature's `<{secret env …}>` values are never required to exist.
  For substitutions that take an optional trailing arg (like `env`), register the shorter
  pattern **before** the longer one (`['env','$name']` before `['env','$name','$default']`), or
  the best-match engine mis-binds and `KeyError`s.

`plugin/` = data sources / integrations (aws secrets, cloudflare IPs, umich portal DB);
`check/` = site-health checks that add report sections (`check/umich/` — sitelens +
`cloudflare_cms.py`, the relocated U-M CMS-integration checks at `site_post_gather`, plus
`oidc_login.py` and `hummingbird.py` (I9) — the U-M WordPress plugin checks
(umich-oidc-login reinstall; the U-M Hummingbird fork), both `site_post_gather`,
registered after `cloudflare_cms`, plus `drupal_ua.py` (I10) — the Drupal user-agent check
(consumes `framework`/`drupal_version`), a `site_post_gather` hook registered after
`hummingbird` — all under the existing `[UMich].enabled` gate. That gate is
a **deliberate behavior change** (D-i9-6 for the two WP checks, D-i10-6 for the Drupal UA
check): these checks previously ran un-gated,
so a non-U-M run got U-M-specific advice (e.g. a non-U-M Drupal 8+ site was told to
configure a `…; UMich; …` user agent) — now they run only for U-M; and `check/cloudflare/` — the opt-in `[Cloudflare.cachecheck]`
cache checks, egress-IP test at
`setup` + per-FQDN HTTP checks at `site_post_dns`, see `docs/cloudflare-cachecheck.md`).
DNS-resolution notices live in `check/dns/` (`notices.py` builders + the `site_post_dns`
`hook.py`), fed by the `dns_classify.py` engine; `no-domains`/`no-primary-domain` remain in
core. `check/pantheon/` (I8; the first Tier-2 check package, gated on `[Check.pantheon].enabled`
— **default true**: an absent `[Check]`/`[Check.pantheon]`/`enabled` still registers, so
relocating a check that ran unconditionally does not silently disable it) holds four
Pantheon-platform checks, one module each: `frozen.py` (frozen-site notice) and `live_env.py`
(paid plan with no initialized live env; consumes `envs`) at `site_pre`, `updates.py`
(`terminus upstream:updates:list` staleness — the §3.2 check-fetches-its-own-data case, via
`sc.terminus`) and `php_eol.py` (PHP end-of-life warning/alert; consumes `envs`) at
`site_post_gather`, registered in that order (D-i8-3). The four notice bodies still embed
un-gated U-M links (moved verbatim — see the still-hardcoded-U-M list under Testing).
`check/wordpress/` (I9; gated on `[Check.wordpress].enabled` — **default true**, the same
absent-section-still-registers shape as `check/pantheon/`) holds four generic WordPress
checks, one module each, all at `site_post_gather`, registered PAPC → sessions → OCP →
favicon (D-i9-5): `papc.py` and `sessions.py` (Pantheon Advanced Page Cache /
native-PHP-sessions, both delegating to `sc.check_wordpress_plugin`), `ocp.py` (the
Object Cache Pro config probe, via `sc.wp_eval`; consumes `wordpress_plugins`) and
`favicon.py` (favicon presence probe via `sc.wp_eval`; consumes
`fqdns_not_behind_cloudflare`). Every hook early-returns unless
`site_context["framework"].startswith("wordpress")`. The `ocp`/`favicon` probes rebind
`site_context["wp_smell"]` on non-fatal stderr — one of the two sanctioned mutate-during-phase
contract keys (`wp_smell`, `drush_smell`; see the table below) — and build failure notices
with `sc.wp_error`. The
favicon notice body embeds un-gated its.umich.edu links (moved verbatim — see the
still-hardcoded-U-M list under Testing).
`check/drupal/` (I10; gated on `[Check.drupal].enabled` — **default true**, the same
absent-section-still-registers shape as `check/pantheon/`) holds three generic Drupal
checks: `multisite.py` (the B30 multisite probe via `sc.drush_php_script`, a
`site_post_dns` hook that consumes `custom_domains`/`primary_domain` and **produces** the
hook-declared keys `drupal_multisite`/`drupal_multisite_smell` — the campaign's first
hook-produced keys, read by `main()` with `.get()` after the phase to seed `drush_smell`
and gate the core `no-primary-domain` notice), `papc.py` (Pantheon Advanced Page Cache
module check, delegating to `sc.check_drupal_module`) and `d7_eol.py` (the `drupal7-eol`
notice + the tag1_d7es module check, one hook), the latter two at `site_post_gather`,
registered multisite → papc → d7_eol; each early-returns unless the framework starts with
`drupal`. `check/addon_updates/` (I10; gated on `[Check.addon_updates].enabled` —
**default true**) holds one `site_post_gather` hook, `table.py` (the B39 pending-add-on
updates table notice, consumes `add_on_updates`), reading the SAME list object the stuffer
publishes; its `updates-addons` notice body embeds an un-gated its.umich.edu support link
(moved verbatim — see the still-hardcoded-U-M list under Testing). The B48 smell notices
are **not** in this package: their builder (`build_smell_notices`) lives in `psh/gather.py`
and their emission stays in `main()` (LEDGER I10 amendment 1).
`check/pantheon_cdn_change/` (`site_post_dns`, unconditional registration) flags
custom domains still CNAME'd to the legacy Pantheon GCDN (Fastly) — in public DNS or in
Cloudflare — and gets the replacement records Pantheon requires from `terminus domain:dns`;
**temporary**, delete once Pantheon's CDN migration is done — see
`docs/pantheon-cdn-change.md`.
To add a check or integration, create a new package dir with a non-empty `__init__.py`
that self-registers — no central registry to edit. Check modules cannot import the
dash-named main script; the helpers they need are exposed as `sc` attributes near the
`cloudflare_enabled()` def (`sc.escape_url`, `sc.check_wordpress_plugin`,
`sc.check_drupal_module`, `sc.umich_enabled`, `sc.cloudflare_enabled`, `sc.terminus`,
`sc.fqdn_re`, since I9 `sc.wp_eval`/`sc.wp_error` — needed by the relocated
OCP/favicon checks — and since I10 `sc.drush_php_script`/`sc.drush_error` — needed by the
relocated multisite/UA checks) — extend that block for new ones (tests
monkeypatch these when loading check modules standalone). A few façade names are exposed
**elsewhere**, not in that block: `sc.db_engine_args` (assigned in `_legacy.py`, see § Database)
and `sc.Notice`/`sc.Severity` (which reach `sc` via a top-of-`script_context.py`
`from psh.notice import Notice, Severity` import — see § Notices vs. news); all are pinned by
the `test_documented_sc_facade_names_exist` house-rule. `check/cloudflare/httpseam.py`
holds the ONE monkeypatchable HTTP seam (`fetch`/`sleep`) and `egress.py` its own `probe`
seam — route any new outbound HTTP in that package through them to stay offline-testable.

### Per-site report pipeline (in `main()`)

For each site: build a `site_context` dict (holds `notices`, `sections`, `attachments`,
traffic data, plan info), invoke the site phases (below) at their seams, gather
Pantheon/WP/Drupal data, compute the plan recommendation from `[Pantheon.plan_info]` in
the config, then render. Since D7 (campaign I7), the recommendation (`psh.plans.
recommend_plan`) runs before the `--only-warn` gate, not after it, so a warning-only run
also gets an `its-recommends-plan` row when one applies.

**Normative per-phase data contract** — main() stuffs these `site_context` keys just
before invoking each phase; hooks code against this table (keys always exist, empty/None
when the source was disabled, malformed, or failed). **The machine-readable copy —
`psh.modules.CONTRACT` — is authoritative**; this table is its prose rendering, and
`tests/unit/test_contract_registry.py` pins the stuffers (`stuff_traffic_contract`/
`stuff_gather_contract` in `psh/modules.py`, `stuff_dns_contract` in `dns_classify.py`)
against it, so drift on either side goes red:

| Phase | Guaranteed new keys (beyond `site`/`notices`/`sections`/`attachments`) |
|---|---|
| `site_pre` | `envs` (I8, at `site_pre`; dict — the `terminus env:list` JSON keyed by environment id, each value carrying `id, created, domain, connection_mode, locked, initialized, php_version, php_runtime_generation`. `main()`'s guards ensure `envs["live"]` exists with an `initialized` key before any site phase fires; **`php_version` is NOT guaranteed present** — read it with `.get`. Never `None`/empty when a phase fires: a failed `env:list` fetch skips the site. Core-produced — fetched by `main()` where it gates on it, stuffed by `stuff_envs_contract` in `psh/modules.py`. The phase fires after the traffic gather and the `--update`/`--import-older-metrics` continues, just before `site_post_traffic` — NOT at SiteContext creation) |
| `site_post_traffic` | `traffic_rows` (`list[TrafficRow]` — plain `NamedTuple` data, attribute names matching the ORM model: `.site_id`, `.traffic_date`, `.site_plan`, `.visits`, `.pages_served`, `.cache_hits`; **not** live ORM rows, because a `db_retry` rollback expires every loaded ORM object, so a hook holding one would emit an unretried SELECT on the next attribute read), `start_date`, `end_date` |
| `site_post_dns` | `domains`, `custom_domains`, `primary_domain`, `main_fqdn`, `fqdns_behind_cloudflare`, `fqdns_not_behind_cloudflare`, `not_in_dns`, `behind_cloudflare_not_proxied`, `proxied_in_multiple_zones`, `dns_transient` (Cloudflare classification lists `[]` when `[Cloudflare]` disabled, the FQDN resolved to no address, or domains malformed. A FQDN resolving to nothing is `not_in_dns` when definitive else `dns_transient` (unknown) — neither runs Cloudflare checks; a FQDN with ≥1 resolved address is classified even if a sibling lookup was transient. Produced by `dns_classify.classify_domains()`, published via `stuff_dns_contract()`. **Hook-produced keys (I10, NOT registry-owned):** `check.drupal.multisite` additionally *produces* `drupal_multisite` (bool) / `drupal_multisite_smell` (str) — the campaign's first hook-declared produced keys. They are DAG-declared (in the hook's `produces`), present **only** when the probe actually ran (absent when its gate failed, the framework is not Drupal, or `[Check.drupal]` is disabled), so `main()` reads them with `.get(...)` after the phase — never assume they exist) |
| `site_post_gather` | `framework` (str), `site_url` (str, `""` when unknown), `wordpress_version` (str; on a failed fetch it is the fatal `wp eval`'s stdout — `""` in practice, since `wp_eval` always returns decoded-and-stripped stdout; the legacy `"unknown"` fallback survives in `psh/gather.py` but is unreachable through the gateway, which never returns a non-str; None only when not that framework), `drupal_version` (str; `"unknown"` — NOT None — when the version fetch failed; None only when not that framework), `wordpress_plugins` (list\|None), `drupal_modules` (**dict**\|None — drush pm:list returns a dict keyed by module name); None on the plugins/modules keys = not that framework or the gather failed. **I9 keys:** `add_on_updates` (list of pending add-on-update dicts — `slug`/`name`/`type`/`current_version`/`new_version`; plugins then themes, list order; `[]` when none, not that framework, or the gather failed; stuffed as the SAME list object the `check.addon_updates.table` hook reads, not a copy — the B39 table became a `site_post_gather` hook at I10, `main()` no longer reads it), `wp_smell`/`drush_smell`/`composer_smell` (str, `""` when none — the stderr of the last non-fatal wp/drush/composer wrapper call that produced any. **`wp_smell` AND `drush_smell` MAY be rebound in place during the phase** — `wp_smell` by `check.wordpress.ocp`/`check.wordpress.favicon`, `drush_smell` by `check.umich.drupal_ua` (I10) — their probes' stderr participates in last-wins; these are the **two sanctioned mutate-during-phase keys**, so consumers reading after the phase (B48's smell emission today) MUST read `site_context["wp_smell"]`/`site_context["drush_smell"]`, never a stale `main()` local; the hooks do NOT declare `produces: ['wp_smell']`/`['drush_smell']` — that would be a duplicate-producer fatal against the core `CONTRACT` registry. Smell precedence is provably unchanged by I10 — no pair of writers swapped relative order, so no notice-csv value diverges, D-i10-4) |
| `site_pre_render` | everything above, plus `current_plan` (str), `recommended_plan` (str; == `current_plan` when no change was recommended or the site had too few in-window months), `plan_costs` (dict `{"same": {plan: float}, "median": {plan: float}, "best": {plan: float}}`; `{}` when ≤4 in-window months), `savings` (float; `0.0` when no recommendation) — the I7 plan-recommendation keys, published by `stuff_plans_contract()` (full-report path only; still no consumer — the documented seam for future report-shaping hooks) |
| `run_finish` | — (run-level, not per-site: receives no `SiteContext` and no arguments until I13's `RunState`; fired first thing in `finish_run()` on completed and aborted runs — the seam for future run-level artifact hooks) |

- **Notices vs. news**: `site_context` is a **`sc.SiteContext`** (a `dict` subclass, so
  `site_context['notices'|'sections'|'attachments'|'site']` access is unchanged) constructed once
  per processed site, as far up the per-site loop as possible (after the portal/not-requested/
  Sandbox skips). Add to it via its methods — `site_context.add_notice(notice)` /
  `.add_notices(list)` (builders: `wp_error`/`drush_error`/`check_wordpress_plugin`/`check_drupal_module`) / `.add_section(...)` /
  `.add_attachment(...)` — this is the **canonical** path (the old module-level
  `sc.add_notice`/`add_notices` free functions were removed). `add_notice` accepts either a
  **`Notice`** (a frozen dataclass — `severity`/`code`/`html`/`text`/`short`/`icon`/`order`,
  from `psh/notice.py`, re-exported as `sc.Notice`/`sc.Severity`) or the legacy notice dict; a
  `Notice` is normalized to the exact legacy dict (`_notice_to_dict`) before the existing
  fill logic runs unchanged, so both forms end up byte-identical for a notice whose csv is
  the plain two-field form (`{site},{code}`) — a notice with *extra* csv fields (e.g.
  `turned-off,{name}`) stays a dict until the increment that adopts it amends the field set
  (`psh/notice.py`'s `Notice` carries no `csv`/`csv_extra` field yet). `code` is enforced
  unique at import time by `psh.notice.registry` (`NoticeRegistry.register`, raising
  `DuplicateNoticeCodeError` on a repeat — the bug class that once let two independent
  notices share the `php-eol`/`annual-bill` codes, I1). The dict form is retired at I14;
  I3 converts `no-domains` as the first (and, so far, only) `Notice`-based producer,
  end-to-end through the three goldens that render it. `add_notice` fills in
  `icon` (from `type`), plaintext `text` (via `html2text`), and honors `order`
  (`prepend`/`first` → front). `add_news_item()` (still an `sc` function) adds an org-wide item to
  `sc.news` (config-inline `[News.<x>]` sub-tables + `*.toml` files in `[News].folder` are both
  loaded by `load_news_items()`). Notice dicts carry their own bespoke `text`, so `add_notice`'s
  defaults are no-ops for them; every notice needs a `csv` key (`site,code,...`) — several report
  paths read `n["csv"]`. Site-phase hooks receive the `SiteContext` and call these methods directly
  (see `check/umich/sitelens.py`); tests build one with `sc.SiteContext({"name": ...})`.
- **Terminus/WP/Drush wrappers**: these eleven defs live in **`psh/gateway.py`** (moved there in
  I2; `psh/_legacy.py` re-imports them, so call sites and the `sc` exposure block resolve
  unchanged). `run_terminus()` is the low-level subprocess call (5-min
  timeout, returns `(stdout, stderr, fatal)`). `terminus()` wraps it for JSON with a
  session-expiry retry and **returns `(result, errors, fatal)`** (`result` is `None` on a JSON
  decode failure). Call sites that index into the result use `terminus_data(...)`, which raises
  the named `TerminusError` when the command was fatal or returned no data (org-level calls
  abort; per-site calls skip that site). `wp()`/`wp_eval()` and `drush()`/`drush_php_script()`
  run WordPress and Drupal commands on a `site.env` remotely (all return 3-tuples too);
  `wp_error()`/`drush_error()` build alert notices from command failures. Prefer these wrappers
  over calling `terminus` directly. `run_terminus`/`terminus`/`wp`/`wp_eval`/`drush`/
  `drush_php_script` return a **`GatewayResult`** NamedTuple `(result, errors, fatal)` — still a
  `tuple` subclass, so positional unpacking and `== (a, b, c)` comparisons are unchanged.
- **Email/SMTP config**: sender identity and the mail server come from the optional
  `[Email]`/`[SMTP]` config sections (`from`/`reply_to`/`bcc`/`dry_run_to`/
  `dry_run_username_domain`/`msgid_domain`, `host`/`port`); when a key is absent the default is
  the original U-M literal, so U-M output is unchanged. `[SMTP]` also holds `enabled` (gates the
  send, below), `username` (default `<{env USER}`; the `sc.smtp_username()` helper resolves
  `--smtp-username` → `[SMTP].username` → `""`), and `password` (`<{secret env SMTP_PASSWORD}`).
  Keep new institution-specific behavior behind config / the `umich` packages — use the
  `umich_enabled()` helper (also exposed as `sc.umich_enabled`) to gate U-M-only checks.
- **Cloudflare auth + shared client**: the plugin builds **one** `Cloudflare` client from
  `[Cloudflare]` config (no direct-env fallback) — `api_token` if present (preferred), else
  `email` + `api_key` (renamed from the old `member_email`/`member_api_key`); missing creds while
  enabled → clear exit. `plugin/cloudflare/client.py` has `build_client()` (auth) and
  `get_client()` (**lazy** build-or-return, cached in
  `sc.plugin_context['plugin.cloudflare']['client']`). `__init__.py` stashes a reference to
  `get_client` in the bag (`['get_client']`); `ips.py` and `fqdns.py` call
  `sc.plugin_context['plugin.cloudflare']['get_client']()` — so they import nothing from the plugin
  (stay standalone-loadable by the tests) and there is **no hook-ordering dependency** (the client
  builds on first use, whichever hook runs first). **Cred-resolution invariant:** the client is
  built at the setup-hook stage (after pass-1 substitution, before the deferred pass), so Cloudflare
  creds must be pass-1-resolvable (nothing today defers them; only `plugin.umich` returns
  `sc.DEFER`).
- **Cloudflare proxied-FQDN fetch (`plugin/cloudflare/fqdns.py`)**: a setup hook
  (`update_and_load_proxied_fqdns`) fetches every proxied FQDN (accounts → zones →
  `dns.records.list(proxied=True)`), **writes `fqdns.json` atomically** (temp + `os.replace`,
  replacing a symlink with a plain file), and loads it into
  `sc.plugin_context['plugin.cloudflare']['proxied_fqdns']`. This replaces the old per-site file
  read; the per-site loop still does its keys-only membership test (`hostname not in …`), so
  `fqdns.json` values are now `{zone_id, origins}` objects (was bare arrays) — old array-format
  files still load. **`origins` is now consumed**, by `check/pantheon_cdn_change` (it walks each
  origin's CNAME chain looking for the legacy Pantheon GCDN); `zone_id` remains stored but unread.
  Refresh rules (see `docs/cloudflare-fqdns.md`): update if the file is missing, or
  stale (>24h) + processing multiple sites + not `--no-update-cloudflare-fqdns`, or
  `--update-cloudflare-fqdns` (forces; requires `[Cloudflare]` enabled). `--update` /
  `--import-older-metrics` / `--create-tables` skip the refresh entirely (they never consume
  fqdns — the missing-file rule does not override this). Any fetch error is fatal;
  **zero zones is fatal** (likely a DNS:Read scope problem), while zero FQDNs only warns.
- **`cloudflare_enabled` is read from config**, `bool(sc.config.get("Cloudflare", {}).get("enabled"))`
  (`.get` chains — a missing `[Cloudflare]` section must not `KeyError`), **not**
  `"plugin.cloudflare" in sc.plugin` (which is always True — every plugin package is imported
  regardless of `enabled`).
- **Cloudflare cache checks (`check/cloudflare/`, opt-in)**: gated on `[Cloudflare].enabled` AND
  `[Cloudflare.cachecheck].enabled` (default false); when enabled, `account_id`+`list_name` are
  required (fatal if missing) and all cachecheck values must be **pass-1-resolvable** (the egress
  setup hook runs before the deferred substitution pass). Registers the egress-IP allowlist test
  at `setup` (early-returns on `--update`/`--import-older-metrics`/`--create-tables`/
  `--allow-any-source-ip` — the create-tables return is REQUIRED, setup hooks run on that path;
  verifies BOTH IP families via the shared lazy SDK client + `client.rules.lists.*`, needs the
  "Account Filter Lists: Read" scope, and the list must cover every family the host egresses on)
  and the per-FQDN cache checks at `site_post_dns` (consumes `fqdns_behind_cloudflare` from the
  data contract; RNG seeded `{site}:{report_date}` so re-runs test identical URLs; MISS-retry
  2s/2s protocol only when headers say cacheable; cross-FQDN redirects drop the URL with NO
  result item; invalid cert → item then insecure re-fetch continues the checks). Notice language
  has U-M and generic variants selected via `sc.umich_enabled()`; consolidation merges FQDNs
  whose findings differ only by URL; every notice's csv key is `cloudflare-cache`. See
  `docs/cloudflare-cachecheck.md` and `development/2026-07-08-cloudflare-cache-configuration/`.
- **Resuming an interrupted `--all` run**: `--resume-from SITE_NAME` filters the already-sorted
  site-name list **before** the loop (via the pure helper `sites_from_resume_point`, which raises
  `ResumeSiteNotFoundError` on an unknown name → fatal), so skipped-over sites do zero work. It
  requires `--all` and is mutually exclusive with `--create-tables` (guards placed **before** the
  create-tables/sites-or-all chain in `main()`, or that chain shadows the precise messages). On a resumed run the two post-loop summary artifacts
  accumulate instead of truncating: `-notices.csv` opens in `"a"` mode and `-results.json` goes
  through `merge_prior_results()` (new wins on key collision; missing/malformed prior file →
  warn + this run's results only). The old commented-out manual site-exclusion hack this
  replaced is gone. See `docs/resuming-interrupted-runs.md`.
- **Rendering**: Jinja2 templates `email_template.html` and `email_template.txt` are
  rendered per site into `build/<site>.{html,txt}`. The HTML is then run through
  `inline-styles.php` (PHP Emogrifier via `vendor/`) to inline CSS for email clients →
  `build/<site>-inline.html`, and a regex pass then appends `!important` to every inlined CSS
  declaration → `build/<site>-inline2.html`, which is the HTML actually attached to the
  message (not `-inline.html`). Charts
  (traffic surge bars, SiteLens gauges) are generated with matplotlib and attached as inline
  images (`make_msgid` CIDs). Everything is assembled into a MIME `EmailMessage` and written
  to `build/<site>.eml`. **The SMTP send (`smtp_login()`/`send_message`) is live but gated on
  `[SMTP].enabled`**: when disabled (or `[SMTP]` absent) only the `.eml` files are written; when
  enabled the tool sends (to test addresses unless `--for-real`). `--for-real` selects the real
  `To`/`Bcc` recipients vs. the dry-run addressing; on a dry run the operator copy
  (`{username}@{domain}`) is only added to `To:` when a username is resolvable.

### Database

SQLAlchemy declarative models `PantheonTraffic` and `PantheonOverageProtection` live in
**`psh/db.py`** (moved in I5, along with every other DB touch — see § Single-module core
above), re-imported by `psh/_legacy.py`. Backend is chosen by the `[Database]` TOML section:
`type` is `sqlite` or `mysql` (anything else exits). Both `type` and `name` are read
**unconditionally** — a `[Database]` section without them is a `KeyError`, not a default; the
`sqlite`/`database.db` "default" lives in the sample config, not the code.
`--create-tables` creates the schema;
new traffic rows are inserted while existing ones are skipped, not updated (`ON CONFLICT DO
NOTHING` on sqlite via the `sqlite_insert` import, `INSERT IGNORE` on mysql).

**Connection resilience.** The DB is remote (RDS) and the path crosses NAT/firewall middleboxes
that reap idle flows, so the engine sets `pool_pre_ping=True` / `pool_recycle=1800` (MySQL only;
sqlite kwargs stay `{}`) and the sessionmaker sets `expire_on_commit=False`. Both the URL and those
kwargs come from **`db_engine_args(db_config)`** — the one engine builder, also exposed as
`sc.db_engine_args` and used by `plugin/umich/portal.py`, so every database this program opens gets
the same pool settings. The load-bearing piece
is the **commit after a read-only SELECT** in `load_traffic_rows()` and
`load_overage_protection_window()`: it releases the connection before the multi-minute per-site
gather, without which the session holds an idle in-transaction connection
that gets reaped and dies at the next query with MySQL error 2013 — **do not remove it**
(`test_load_traffic_rows_releases_the_connection` guards it). Both return plain data
(`TrafficRow` / `OverageProtectionRow` NamedTuples), not ORM rows, because a rollback expires live
ORM objects and a later read would emit an unretried
SELECT. `load_overage_protection_window()` snapshots the whole report window in **one** ranged
query and hands `plan_costs()` a dict-backed `op_lookup(month)`; the cost model is therefore
DB-free, where it used to do ~91 uncached per-month `Session.get()`s (each its own committed
round trip over the WAN, and a Basic-plan site — no rows at all — missed on every one).
DB work runs through `db_retry(session, unit, what=…, site=…)`, which retries **whole
idempotent units of work** (`update_traffic_rows`, `insert_traffic_rows`, `load_traffic_rows`,
`build_traffic_table_rows` — moved to `psh/traffic.py` at I6, still passed to `db_retry` as a
`lambda` from its `psh/_legacy.py` call site — and `load_overage_protection_window`) and NEVER
a statement with pending writes — a rollback discards them,
so a statement-level retry would commit a partial write set. What it retries is decided by
**`db_retryable(e)`** = `isinstance(e, OperationalError) or e.connection_invalidated`, **not** by an
exception class list: SQLAlchemy's mysqldb dialect classifies a lost connection by error *code*, so
a reaped connection can arrive as an `InterfaceError` or a `ProgrammingError(2014)` — siblings of
`OperationalError` under `DBAPIError`, not subclasses — and what they all share is
`connection_invalidated`. `OperationalError` is retried on top of that (a deadlock or lock-wait
timeout does not invalidate the connection but is worth one retry). Anything else (an
`IntegrityError`, a real `ProgrammingError` bug) propagates untouched and stays loud.
On a second failure `db_retry()` raises
`DatabaseUnavailableError`. **`main()` wraps the site loop in a single `except BaseException:`** —
enumerating classes is what let an SMTP hiccup on site 250 of 300 discard 249 sites' work — and
`abort_reason(e)` classifies it into exactly three outcomes: `"database"` (a
`DatabaseUnavailableError`, or any `DBAPIError` `db_retryable()` would have retried, raised outside
a unit) → exit 1; `"interrupted"` (`KeyboardInterrupt`) → exit 130; `"fatal"` (everything else) →
`abort_run()` **re-raises the original error after the flush**, so a `SystemExit` keeps its own code
and message and anything else keeps its traceback. There is no `except SystemExit:` clause and
nothing is swallowed. On every one of the three, `abort_run()` drops the failed site from
`site_results` (it is written mid-gather, so it
would otherwise ship as a success), flushes the artifacts via `finish_run()`, and prints a command
rebuilt from `sys.argv` (`--resume-from` for `--all`; a re-run command listing the remaining sites
otherwise, since `--resume-from` requires `--all`). **A
Ctrl-C that lands after a site's report was already sent resumes at the NEXT site** and keeps that
site's results entry — resuming inclusively would mail its owner a duplicate report.
`finish_run()` also writes the run metadata — `aborted_at`, `reason`, `sites_completed_this_run`,
`db_reconnects_healed_this_run`, `db_reconnect_failures_this_run`, `reconnects_by_site`,
`reconnect_failures_by_site`, and on a resumed/aborted run the prior run's whole block under
`previous` — to its **own** artifact, `{ymd}-run.json`. It must **never** go back into
`{ymd}-results.json`: `monthly-report.txt` reads that file with `jq to_entries`, which enumerates
every key as a site, so a metadata key there becomes a bogus site row in the operator's monthly
stats (silently: off-by-one site count, phantom empty-framework CMS bucket). **`-results.json` is
site-keyed and nothing else.** Same write gate and accumulate/truncate rules as the other two
artifacts. The two reconnect counters are **healed vs. failed** and both are printed
(`Database reconnects: N healed, M failed`): `db_retry()` counts a heal only after the retry
*returns*, and counts a failure when the retry or the pre-retry rollback dies — an attempt-counting
version reported "1 reconnect" on the run that aborted *because* nothing reconnected, and zero on
the rollback failure, the most definite connection loss there is. **Test seam:** the counters are
`script_context.py` module attributes (`sc.db_reconnects_by_site`/
`sc.db_reconnect_failures_by_site`), not `psh/db.py` or `psh/_legacy.py` state — a test patches or
asserts against **`script_context`** (e.g. `monkeypatch.setattr(sc, "db_reconnects_by_site", {})`).
The old `psh.db_reconnect[s|_failures]_by_site`-shaped binding no longer exists, so a stale
`psh`-targeted patch fails loudly (`AttributeError`), not silently — there is nothing on `psh`
left to shadow.

**Two rich gotchas, both shipped as bugs once.** (1) `sc.console` has markup enabled, so **every
`sc.console.print()` interpolating text the program did not author must
`rich.markup.escape()` it** — exception text, terminus/WP/Drush stderr, anything from the outside.
Rich reads any `[lowercase…]` fragment as a style tag and silently *deletes* it: `[parameters: (…)]`
(the tail SQLAlchemy appends to every `DBAPIError`) and `[warning]`/`[notice]` from command stderr
vanish from the very message the operator has to debug — and an unmatched `[/…]` raises
`MarkupError`, which inside `abort_run()` fires after SIGINT is ignored and before the flush,
losing every artifact that function exists to save. (2) `sc.console` is a bare `Console()`, so on a
**non-tty** — cron, `nohup`, a redirect, i.e. how every multi-hour `--all` run is actually
launched — rich falls back to **width 80 and hard-wraps**, inserting a real newline. That silently
broke the copy-pasteable resume command: bash treats the newline as a command separator, and the
wrapped first line re-parsed as a complete `--all --for-real` run **without** `--resume-from` —
pasting it re-mailed every owner who already had their report. Use **`soft_wrap=True` on every
print that emits a command meant to be copied**. Tests must reproduce the production width, not
hide the bug: `recording_console(monkeypatch, sc, width=…)` takes a `width` for exactly that (its
wide default is what made the suite blind to this).

**The e2e goldens cover neither stdout nor the
artifacts**, so `tests/integration/test_finish_run.py`, `tests/integration/test_abort_run.py`, and
`tests/e2e/test_abort_e2e.py` (which drives a DB failure through the real `main()` via the
`dbshim`) are the only cover for that code. Note `abort_run()` sets SIGINT to
`SIG_IGN` so a second Ctrl-C cannot truncate the flush — an in-process test that calls it **must**
`monkeypatch.setattr(psh.signal, "signal", …)`, or the rest of the pytest session silently ignores
Ctrl-C. In the site loop, a site's notices are appended to `all_warnings` **before** the SMTP
send, not after: a Ctrl-C in the send→append window (which includes `smtp_connection.quit()`, a
network round-trip) set `emailed=True`, advancing the resume point past the site, and its notices
then never reached `-notices.csv` on any run. See
`development/2026-07-13-db-connection-resilience/SPEC.md`.

### Configuration (`pantheon-sitehealth-emails.toml`)

The active config is a symlink to `pantheon-sitehealth-emails-config/pantheon-sitehealth-emails.toml`
(a separate private repo); `sample-pantheon-sitehealth-emails.toml` is the documented
template. Institution-specific data (plan names, traffic limits, prices, overage costs,
Pantheon org id, DB, Cloudflare/AWS toggles) lives here — the report's recommendations are
driven entirely by `[Pantheon.plan_info]` and `[Pantheon.plan_sku_to_name]`. Keep U-M-only
logic out of the core script and behind config flags / `umich` plugin+check packages so the
tool stays reusable by other institutions.

## Conventions & gotchas

- **`pantheon-sitehealth-emails.py` is a committed symlink to `pantheon-sitehealth-emails`. It is
  NOT a second copy and NOT the file to edit.** Since the modularization campaign's I0, the
  extension-less `pantheon-sitehealth-emails` is a thin (~17-line) shim that calls `psh.cli.main()`;
  the program body lives in **`psh/_legacy.py`**, a normal `.py` file that **CodeGraph, pyright, and
  ruff index natively** (all three key off the `.py` extension). So the symlink's original reason —
  three tools blind to the several-thousand-line *extension-less* core program — is dissolved for
  the program body; the symlink now only keeps those three tools seeing the extension-less **shim**
  itself. It stays tracked (not git-ignored) on purpose — a git-ignored one would vanish on a fresh
  clone. Do not delete it. **Verified 2026-07-17** via `codegraph explore "psh/_legacy.py main"`:
  CodeGraph now indexes `psh/_legacy.py`'s symbols natively (42 symbols, verbatim line-numbered
  source returned) — the old "117 files, zero symbols from the core program" blindness is gone. One
  limitation persists: `main` (`psh/_legacy.py:2108`) still reports "no covering tests found", but
  **not** for the reason the old note gave. Tests no longer load the program via `SourceFileLoader`
  on the dash name (that mechanism is gone — `tests/conftest.py` now does a normal
  `importlib.import_module("psh._legacy")`); the cause now is that this dynamic import happens
  inside a conftest fixture, which is not a static import edge CodeGraph can follow. The symbol
  index and call graph are unaffected.
- Generated artifacts land in `build/` (git-ignored); `database.db`, `fqdns.json`, and the
  `.eml`/`.html`/`.txt` outputs are working data, not source. `fqdns.json` is now **program-
  generated** by the cloudflare plugin (was produced by a standalone script); it is git-ignored
  yet still tracked (`git ls-files` shows it) — `git rm --cached fqdns.json` to stop tracking it.
- Type-hint tuples like `-> (str, str, bool)` appear throughout; these are the existing
  (technically non-idiomatic) house style — follow the surrounding code.
- There is an active TODO list in `README.md` describing planned work (daily traffic alerts,
  Cloudflare/security scoring, moving capture into the portal app, better error handling).
- **`git diff -w` is not proof a re-indent of this file was whitespace-only.** `main()`'s per-site
  loop builds notice HTML/plaintext from multi-line `f"""..."""` literals whose continuation lines
  deliberately start at column 0, not at the surrounding code's indent (grep `f"""` in the loop
  body). A mechanical re-indent of a block containing one of these — e.g. wrapping the loop in a
  `try:` — must NOT shift those interior lines: doing so adds leading whitespace to the rendered
  email, a real behavior change, and `git diff -w` hides it completely, because a line that only
  gained leading whitespace is exactly what `-w` is designed to ignore. The goldens are what would
  actually catch it. Anyone re-indenting a block here should compare ASTs/token streams, or just
  trust the goldens — not eyeball `git diff -w`.

## Testing

**`./run-tests` lints and type-checks before it tests, and gates on all of it.** It runs **three
gates** in order, each aborting on the first failure so a later gate's green never hides an
earlier gate's red (PD#1):

1. **ruff, narrow PD set** (`pyproject.toml`: `E722`, `BLE001`, `S105`, `S106`) — each mechanizes
   a directive in `prompts/directives.md` (PD#2, PD#6) rather than adding new policy; runs over the
   **whole tree**, including the files the campaign grandfathers.
2. **ruff, broad campaign ratchet** (`ruff-broad.toml`: `select = ALL` minus a grandfathered
   exclude list — `psh/_legacy.py`, `dns_classify.py`, the still-grandfathered check
   packages enumerated individually (`check/cloudflare/`, `check/dns/`,
   `check/pantheon_cdn_change/` — the wholesale `check/` was replaced by this
   enumeration at I8 so `check/pantheon/` is born gated; at I9 the `check/umich/` entry
   was narrowed one level deeper, to `check/umich/sitelens.py` +
   `check/umich/cloudflare_cms.py`, so the package `__init__.py` and the two new I9
   modules are gated while the two legacy siblings stay grandfathered), `plugin/`,
   `tests/`, `development/`;
   CAMPAIGN.md §13). Each increment un-grandfathers its files by deleting them from that list
   (`script_context.py` was un-grandfathered in I4).
3. **pyright, standard mode** over `psh/` minus `_legacy.py` (`[tool.pyright]`); a missing pyright
   binary is a **hard failure**, never a silent skip (PD#1/PD#14).

Both `[tool.ruff]` and `ruff-broad.toml` deliberately pin **no `target-version`**: ruff infers it
from `requires-python`, and pinning it *masks* the 3.12-only PEP 701 f-string syntax the program
actually uses. `.claude/hooks/ruff-check.sh` runs **both** ruff passes at edit time (advisory, via
`PostToolUse`, with `--force-exclude` and a repo-root `cd` so an edited grandfathered file honors
the exclude list) but **not** pyright (edit-time latency; `./run-tests` carries the type gate). No
pass passes `--select` — the config files are the single source of truth.

There is a pytest harness under `tests/` (built 2026-07; design in
`development/2026-07-04-test-harness/SPEC.md`). Run it with `./run-tests` (wrapper over
pytest): `./run-tests --fast` is the offline inner loop; `./run-tests` adds the live tier;
`--llm` gives terse machine-parseable output; `--coverage`, `--update-goldens`, and
`--record` do what they say. Any other argument is passed straight through to pytest.
`--record` short-circuits to `tests/tools/record.py` and forwards **no** arguments — for Drupal
fixtures call `python tests/tools/record.py --drupal` directly. Tiers are pytest marks: `unit`,
`integration`, `e2e`, `live`, `render`, `email`, `slow`.

**When you change the program, add/adjust the appropriate tests in the same change**

**This project is test-first**, at seams agreed in the spec before implementation. The loop is
`mattpocock-skills:tdd` — *not* `superpowers:test-driven-development`, which
`superpowers:subagent-driven-development` would otherwise default implementer subagents to;
`prompts/implementation-standards.md` carries the override and must be injected, or the default
wins silently. Two consequences worth stating here: **refactoring is not part of the red→green
loop** (it belongs to review), and where a core `main()` change has no seam above the e2e
golden, **extracting a pure helper is part of the change** — that is where `overage_blocks`,
`plan_costs`, and `sites_from_resume_point` came from. The exhaustive carve-outs from
test-first are new goldens/snapshots and recorded fixtures, whose expected values are
necessarily derived from a run; an *existing* golden going red is a signal and is never
refreshed to green. Backfilling tests for already-untested code is a different job with a
different prompt (`prompts/add-tests-for-change.prompt.md`).

Non-obvious things the harness relies on:
- **The script is imported, not re-parsed.** `tests/conftest.py` imports the program as
  `psh._legacy` via a normal `importlib.import_module("psh._legacy")` (the repo root is on
  `sys.path` because the suite runs as `python -m pytest`, cwd = repo root); the `psh` fixture
  exposes that module. `SourceFileLoader` is **no longer** used for the program; it survives in
  the suite only for loading individual `check/`/`plugin/` modules standalone — used directly in
  the per-module test files (e.g. `tests/integration/test_check_sitelens.py`, `test_plugin_aws.py`),
  while the `tests/helpers/checkload.py` helper (for packages with relative imports) uses
  `importlib.util.spec_from_file_location` + `exec_module` instead. Argparse was
  refactored into `build_arg_parser()`/`parse_args()`; `sc.options` is set by the caller, so a
  test sets it (the `reset_sc` autouse fixture does) before calling functions. `MPLBACKEND=Agg`
  must be set before the load (conftest does this) because the module imports `matplotlib.pyplot`
  at the top.
- **Two mock seams.** All Pantheon/WP/Drush I/O funnels through `run_terminus()` — monkeypatch it
  for in-process tests at **`psh.gateway.run_terminus`** (via the `gateway` conftest fixture), NOT
  `psh.run_terminus`: since I2 the wrappers live in `psh/gateway.py` and resolve `run_terminus` in
  the gateway module's namespace, so patching the remnant's imported binding would not intercept
  them (a silent test defect, PD#14). Module-singleton patches are unaffected — `psh.time.sleep`
  and `psh.subprocess.Popen` mutate shared module objects both gateway and `_legacy` import, so
  they apply without repointing. **`psh/gather.py` binds `run_terminus` in its OWN namespace**
  (`from psh.gateway import run_terminus`) for `gather_drupal`'s composer dry-run, which calls
  `run_terminus(...)` directly (composer's dry-run output is human-readable text, not JSON, so it
  can't go through the JSON-decoding `terminus()` wrapper) — the same two-binding gotcha as the
  wrappers. So a test exercising `gather_drupal` must patch **BOTH** `psh.gateway.run_terminus`
  AND `psh.gather.run_terminus` (the `gateway` fixture repoints only the former; a gather test
  that patches just it makes **real** Terminus subprocess calls — a mock that looks installed but
  isn't, I10 Task 4). See `tests/integration/test_gather_drupal.py`'s module docstring.
  Or use the PATH-shim fake `terminus` (`tests/shims/terminus`,
  record/replay) for full subprocess e2e. The `php inline-styles.php` CSS inliner uses **real php**.
- **The suite must stay green on a sqlite-only install.** `[mysql]` is an optional extra and the
  setup line above sanctions dropping it, so a test needing a real MySQL engine
  (`tests/integration/test_db_credentials.py`, which drives `db_retry()` against a URL that really
  contains a password) must `pytest.importorskip("MySQLdb")` at module level:
  `create_engine("mysql+mysqldb://…")` imports the DBAPI eagerly, so without the guard it is a hard
  ERROR in `--fast`, not a skip.
- **Safety interlock.** `run_program()` in conftest is the only sanctioned way to run the program
  in a subprocess; it raises `ForbiddenFlagError` if `--all`/`-a`/`--for-real` appear (including
  argparse abbreviations like `--fo` and short bundles like `-av` — it fails closed), and
  `ForbiddenLiveDataError` if `--create-tables`/`--import-older-metrics` would run live or against
  a non-fixture config (a config-**path** allowlist, not a backend-type test — the production
  default DB is also sqlite). Never bypass it. Tests use only `its-wws-test1`/`its-wws-test2`,
  read-only.
- **Pure-helper seam.** Pure functions extracted from `main()` as module-level defs so they're
  importable as `psh.<fn>` and unit/property tested: `overage_blocks`, `contract_year_end`,
  `plan_costs` (the cost model — DB-free via an injected `op_lookup(month)`), and
  `build_plan_over_time` (returns `[]` for zero traffic; `main()` guards the empty case
  and skips the plan sections) now live in `psh/plans.py` (moved at I7, born gated under
  the broad ruff set + pyright standard) — still importable as `psh.overage_blocks`/
  `psh.contract_year_end`/`psh.plan_costs`/`psh.build_plan_over_time` via `_legacy.py`'s
  re-import, same seam as before the move. Also extracted: `load_news_items`, and
  `sites_from_resume_point`/`merge_prior_results` (the `--resume-from` logic, which cannot be
  reached through the `--all`-banned subprocess interlock and so is only testable in-process). The
  extractions are behavior-preserving (goldens byte-identical). `estimate_month_visits` and
  `build_traffic_table_rows` live in `psh/traffic.py` (moved at I6, born gated under the
  broad ruff set + pyright standard) — still importable as `psh.estimate_month_visits`/
  `psh.build_traffic_table_rows` via `_legacy.py`'s re-import, same seam as before the move. The
  B43 visits-by-month aggregation is its own pure function there too,
  `psh.traffic.aggregate_visits_by_month(rows, start_date, end_date) -> tuple[dict, dict]`
  (`tests/unit/test_traffic_aggregation.py`), covering seeding traffic-free months to 0 and the
  last-row-wins `plan_on_day` map; the `pprint` diagnostics, the empty-`plan_on_day` guard, and
  `build_plan_over_time`'s call stay in `main()` (loop control/ordering — I7's `psh/plans.py`
  move took the bodies, not the call sites; I11 is the chart-region increment still to come).
  **`classify_hostname_dns` is NOT one of these** — it moved out of the script into
  `dns_classify.py`; import it from there.
- **DNS tests.** The `dns_classify.py` engine and `check/dns/` package have their own suite:
  `tests/unit/test_dns_classify.py` (classification + transient-vs-not-in-DNS, and
  `dns_classify.MalformedNameError` — `resolve()` converts dnspython's syntax errors
  (`dns.exception.SyntaxError`, `dns.name.NameTooLong`) into this named exception at the single
  DNS seam, and `classify_hostname_dns` catches it and returns `(0, 0, False)`, so a malformed
  hostname — e.g. a Pantheon domain id like `a..b`, which `fqdn_re` accepts — can never escape and
  abort the whole run), `tests/unit/test_dns_notices.py` (notice builders),
  `tests/integration/test_check_dns.py` (the `site_post_dns` hook), and
  `tests/integration/test_dns_notice_render.py` (syrupy snapshots). `check/pantheon_cdn_change/`
  has its own parallel suite: `tests/unit/test_pantheon_cdn_change_chain.py`,
  `tests/unit/test_pantheon_cdn_change_pantheon.py`,
  `tests/unit/test_pantheon_cdn_change_detect.py`, `tests/unit/test_pantheon_cdn_change_notices.py`,
  `tests/integration/test_check_pantheon_cdn_change.py` (hook/phase registration),
  `tests/integration/test_pantheon_cdn_change_notice_render.py` (syrupy snapshots, and where the
  U-M-before-cutoff copy is pinned), and the 4th e2e golden (below).
  **`dns_classify.resolve` is the one monkeypatchable DNS seam** — patch it (as those tests do) so
  nothing hits real DNS; route any new resolution through it.
- **check/pantheon tests (I8).** The `check/pantheon/` package (frozen/live-env/updates/php-eol)
  has its own suite: `tests/unit/test_php_eol_notice.py` (the `build_php_eol_notice` builder,
  repointed to its `check/pantheon/php_eol.py` home at I8 — the D-i8-4 lexicographic-compare and
  missing-`php_version` fixes are pinned here), `tests/integration/test_check_pantheon_init.py`
  (config gating + the four hooks' phase/`consumes`/`produces` declarations; default-true proof),
  `tests/integration/test_check_pantheon.py` (the four hook seams via `sc.SiteContext` and the
  `gateway` fixture, incl. the D-i8-5 singular-`short` interpolation pin), and
  `tests/integration/test_pantheon_notice_render.py` (syrupy snapshots of all seven notice
  variants). The `envs` contract key and `stuff_envs_contract` are pinned by
  `tests/unit/test_contract_registry.py`, and `tests/integration/test_hook_dag.py` proves the
  `check.pantheon` declarations validate.
- **psh/gather + check/wordpress + U-M WP-check tests (I9).** All integration tier:
  `tests/integration/test_gather_wordpress.py` (`psh.gather` via the `gateway` fixture +
  `sc.SiteContext` — happy path, fatal version/plugin/theme fetches, last-wins smell, the
  network-URL variants; its header note records why the defensive `"unknown"`/`None`
  branches are unreachable through the gateway seam),
  `tests/integration/test_check_wordpress_init.py` (config gating + the four hooks'
  declarations in order; default-true proof), `tests/integration/test_check_wordpress.py`
  (the four hook seams, incl. the ocp no-matching-plugin no-call pin, the
  `wp_smell`-rebind pins, and the D-i9-4 precedence pin — theme stderr then OCP stderr
  with clean favicon → OCP wins), `tests/integration/test_check_umich_wp.py` (oidc /
  hummingbird seams, the D-i9-10 `site['name']` print pin, and the D-i9-6 gating-change
  proof: umich-disabled registers neither), and
  `tests/integration/test_wordpress_notice_render.py` +
  `tests/integration/test_umich_wp_notice_render.py` (syrupy snapshots of every relocated
  notice body — the Invariant-8 forward byte pins). The four new `site_post_gather`
  contract keys and the extended `stuff_gather_contract` (same-`add_on_updates`-object
  included) are pinned by `tests/unit/test_contract_registry.py`;
  `test_documented_sc_facade_names_exist` pins `sc.wp_eval`/`sc.wp_error`.
- **psh/gather Drupal half + check/drupal + check/addon_updates + Drupal-UA tests (I10).**
  Integration tier: `tests/integration/test_gather_drupal.py` (`psh.gather.gather_drupal`
  via the `gateway` fixture + `sc.SiteContext` — D8+ composer-audit + D7 pm:updatestatus
  happy paths, the fatal core-status/pm:list/pm:updatestatus/composer-update notices, the
  last-wins smells, and the **D-i10-7 pin** that a D7 `"type": "module"` row renders
  `module`; its module docstring records the two-binding `run_terminus` seam trap — patch
  BOTH `psh.gateway.run_terminus` and `psh.gather.run_terminus`, see § Two mock seams),
  `test_check_drupal_init.py`/`test_check_drupal.py` (config gating + declarations in order;
  the multisite gate/probe/key-absence + `multisite-check` notice, papc/d7_eol delegation),
  `test_check_addon_updates_init.py`/`test_check_addon_updates.py` (gating + the
  `updates-addons` table incl. the same-object read), `test_check_umich_drupal_ua.py` (the
  UA seams, the **D-i10-4** `drush_smell`-rebind pin, and the **D-i10-6** gating-change proof:
  umich-disabled registers no `drupal_ua`), and the syrupy render files
  `test_drupal_notice_render.py` / `test_addon_updates_notice_render.py` /
  `test_umich_drupal_ua_notice_render.py` / `test_smell_notice_render.py` (Invariant-8 byte
  pins; the last pins the **D-i10-8** composer de-indent). Unit tier:
  `tests/unit/test_no_primary_domain_notice.py` (the D-i10-3 pure helper), and
  `tests/unit/test_smell_notices.py` gained the D-i10-8 column-0 assertions.
  `test_hook_dag.py`'s `ALL_PACKAGES` gained all four then-missing packages (I8/I9 drift
  repair); `test_documented_sc_facade_names_exist` pins `sc.drush_php_script`/`sc.drush_error`.
- **Shared DNS-test infrastructure (`tests/helpers/`).** `dnsfake.py` has the fake
  `dns_classify.resolve` (`make_resolver`/`patch_resolve`, zone dict keyed `(name, rrtype)`) and
  `recording_console` (a wide `record=True` Console, read back with `export_text()` — not `capsys`,
  which wraps at width 80 and breaks substring assertions as messages grow). `checkload.py` loads a
  `check/` package (or one module of it) standalone via a probe package registered in
  `sys.modules`, for packages using relative imports. Both take pytest's `request` (not
  `monkeypatch`) to register their cleanup: `monkeypatch.delitem(..., raising=False)` on a key that
  does not exist yet records no undo entry, so a package created later by `from . import chain`
  would leak into the next test's `sys.modules` — these purge by module-name prefix instead.
  `recording_console` also takes a **`width=`** — use it to reproduce production's 80-column
  non-tty console (see the rich wrap gotcha under Database).
- **Subprocess shims: ONE `sitecustomize`, in `tests/shims/pyshim/` (`conftest.PYSHIM_DIR`).**
  `run_program()` launches the real program in a subprocess, so an in-process `monkeypatch` cannot
  reach it; putting that directory on `PYTHONPATH` makes Python auto-import `sitecustomize` at
  interpreter startup, before the program imports anything. `site.py` imports **exactly one** module
  by that name (whichever dir wins on `sys.path`), so the shims are **modules inside** pyshim, each
  self-activating from its own env var and imported by the single `sitecustomize.py` — `dnsshim.py`
  (`DNS_SHIM_ZONE`, a JSON zone file; replaces `dns.resolver.resolve`; the 4th e2e golden needs it)
  and `dbshim.py` (`DB_SHIM_FAIL`; patches `sqlalchemy.orm.Session.get` to raise `OperationalError`,
  simulating MySQL 2013 inside whichever `db_retry()` unit calls it first — in practice
  `update_traffic_rows()`'s `session.merge()`, since `Session._merge()` calls `get()` internally,
  not `build_traffic_table_rows()` as the name suggests). **Add a new shim as another module here,
  never as a second shim directory**: two `sitecustomize.py` files means one silently never runs —
  no error, no warning — and an e2e test whose assertions are `not in`-shaped then passes green
  against a run that did nothing. `tests/integration/test_shim_composability.py` fails if anyone
  reintroduces that shape (and proves both shims can be active at once). With neither env var set
  the directory is inert, which matters because `PYTHONPATH` is inherited by the PATH-based fake
  `terminus` (a Python script too). `tests/e2e/test_abort_e2e.py` is the only test that drives the
  DB shim through the real subprocess `main()`; it is not one of the byte-golden e2e tests below (no
  snapshot — it asserts exit code, stdout content, and the printed re-run command).
- **Offline e2e determinism.** The shim-backed run uses `tests/fixtures/config/minimal.toml`,
  seeded traffic, `--date 2026-03-31` (a mid-year date avoids the U-M contract-year-end path),
  and a `domain:list` fixture reduced to the platform domain (so no live DNS). Golden snapshots
  normalize the volatile `make_msgid` CIDs; refresh with `./run-tests --update-goldens`. There are
  **four** goldens: WordPress (`its-wws-test1`, fixtures in `tests/fixtures/terminus/`), Drupal
  (`its-wws-test2`, `tests/fixtures/terminus-drupal/`, selected via `run_program(fixtures_dir=…)`),
  a **non-U-M** golden (`test_golden_nonumich.py`, `minimal-nonumich.toml` with no
  `[UMich]` section + generic `[Email]`) that proves the P8 config-driven email headers/msgid and that the
  U-M-guarded doc-URL checks don't appear for a non-U-M run, and the **Pantheon CDN-change**
  golden (`tests/e2e/test_golden_cdn_change.py`, `tests/fixtures/terminus-cdnchange/`, DNS shimmed
  via the `dnsshim` in `tests/shims/pyshim`) driving `check/pantheon_cdn_change` through the real `main()`. It has
  two deliberate scope limits, both asserted in the test rather than left implicit: it covers only
  the public-DNS detection source (`[Cloudflare]` stays disabled, since enabling it would make a
  setup hook call the live Cloudflare API), and it pins the **generic** notice copy
  (`minimal.toml` has no `[UMich]` section) — the U-M copy is pinned instead by
  `tests/integration/__snapshots__/test_pantheon_cdn_change_notice_render.ambr`. **Its fixtures are
  hand-maintained**: `--record` refreshes only `terminus/` and `terminus-drupal/`, so
  `terminus-cdnchange/` will silently freeze at today's Pantheon JSON shape — see the README in
  that directory. The `.eml`
  identity headers have no
  byte golden (the `Date:` is volatile) — `test_eml_headers.py` asserts them explicitly. Refresh
  WordPress fixtures with `./run-tests --record`, Drupal with `python tests/tools/record.py
  --drupal` (both trim the org list to the one test site and scrub team emails).
- **`tests/conftest.py`'s `_CWD_ASSETS`** must include `check` and `plugin` (symlinked into the
  isolated e2e working directory alongside the template/PHP assets): `find_modules()` walks
  `check/`/`plugin/` **CWD-relative**, and the e2e workdir is a fresh temp directory — before this
  was fixed, **no e2e golden had ever loaded a single check or plugin package**, so every offline
  e2e run was silently testing a program with every check disabled. Anyone editing `make_workdir()`
  needs to preserve this or the e2e tier stops testing anything the check/plugin system does.
- **The offline golden only reaches the ≤4-month "not enough data" state** (its recorded metrics
  fall after the March report date), so the extracted `plan_costs` cost model is exercised
  end-to-end by `tests/e2e/test_recommendation_e2e.py` (seeds >4 in-window months) plus its
  unit/property tests — not by the golden. The render tier vendors axe-core locally
  (`tests/vendor/axe.min.js`) so it stays offline.
- **The reusable (non-UMich) path is only partly de-U-M-ified.** Bugs hide here because production
  always runs with the UMich plugin enabled, so the non-U-M golden is the only guard. **Still
  hardcoded U-M** in core (not yet relocated to the `umich` packages): the date-driven
  annual-billing notices (until I12), and the
  branding in `email_template.html` (its.umich.edu URLs, `webmaster@umich.edu`, `node/4705`).
  (The Drupal user-agent check LEFT this list at I10: it relocated to
  `check/umich/drupal_ua.py` and is now `[UMich].enabled`-gated — U-M content living in the
  U-M package where it belongs, the umich-oidc-login/Hummingbird I9 precedent.)
  Also **hardcoded U-M but living in the generic check packages** (un-gated U-M links moved
  verbatim when the checks relocated — the packages are generic because §3.2 assigns these
  platform checks there; de-U-M-ifying them is post-campaign/I14 work): in `check/pantheon/`
  (I8) the `frozen`, `no-live-env-but-paid-plan`, and `updates-*` notice bodies (its.umich.edu /
  procurement links), in `check/wordpress/` (I9) the `no-favicon` notice body
  (its.umich.edu documentation links), and in `check/addon_updates/` (I10) the `updates-addons`
  notice body (its.umich.edu support link). The
  non-U-M golden does **not** assert "no umich.edu anywhere", so it will not catch new leakage —
  keep institution-specific logic behind config flags / the `umich` plugin+check packages.
- **Cache-check tests.** The `check/cloudflare/` modules are loaded standalone (SourceFileLoader;
  for modules with relative imports, a probe package with `__path__`/`submodule_search_locations`
  is registered in `sys.modules` first — see `test_check_cloudflare_init.py`). Unit tier:
  `test_cachecheck_headers.py` / `test_cachecheck_pages.py` / `test_cachecheck_consolidation.py`
  (pure battery/extraction/consolidation + Hypothesis). Integration tier:
  `test_hooks_phases.py` (phase registry), `test_check_cloudflare_init.py` (gating/import guard),
  `test_check_cloudflare_egress.py` (`egress.probe` seam + fake lists client),
  `test_check_cloudflare_cache.py` (`httpseam.fetch`/`sleep` seams, canned FetchResults),
  `test_check_umich_cloudflare_cms.py` (relocation), and
  `test_cachecheck_notice_render.py` (syrupy snapshots of the notice HTML/plaintext — refresh with
  `--update-goldens`). The e2e goldens keep `[Cloudflare].enabled=false`, so the cache check must
  never alter them.

## Reusable prompts (`prompts/`)

`prompts/` holds the repo's own workflow prompts — read the relevant one before doing that kind of
work, and cite it by name rather than re-deriving the conventions.

**`prompts/directives.md` is the Spine** and comes first: the ONE copy of the Posture, the 14
Prime Directives, the Engineering Preferences, and the spec quality bar. Every other file in
`prompts/` is a *delta* that cites directives **by number** and restates none of them. This
matters because they used to live in two files and **drifted** — PD#11 gained a `/domain-modeling`
mandate in one copy and not the other, and the adversarial reviewer read the stale one.

The deltas: `new-feature-standards.md` (how features get specced),
`implementation-standards.md` (the standards layered on `superpowers:subagent-driven-development`;
the intended invocation is "implement everything per the spec doc(s), adhering to the standards in
`prompts/implementation-standards.md`"), `debugging-standards.md` (the standards layered on
`mattpocock-skills:diagnosing-bugs` — for **runtime** failures; document defects go to
`adversarial-review.md` instead), `adversarial-review.md`, `add-tests-for-change.prompt.md`,
`refresh-fixtures.prompt.md`, and `update-claude-md.md`. Note
`development/2026-07-04-test-harness/` contains **stale copies** of two of these — `prompts/` is
the source of truth.

`prompts/` holds the *standards* (the bar to hold work to); **`docs/agents/`** holds the *wiring*
the installed skills read (where issues live, which glossary to read, the triage vocabulary). See
**Agent skills** below.

### Dispatching subagents

**`.claude/agents/psh-implementer.md` and `psh-reviewer.md`** carry the read list
(`prompts/directives.md` + `prompts/implementation-standards.md` + `CLAUDE.md` + the brief), so
the standards reach a fresh-context subagent as **configuration** rather than as prose the
controller has to remember to paste. Dispatch every code-touching subagent (implementers and
fix-subagents) as `psh-implementer` and every reviewer as `psh-reviewer`;
`superpowers:subagent-driven-development`'s template says `general-purpose`, and
`prompts/implementation-standards.md` overrides it. **A dispatch that cannot use them must stop
and say so** — falling back to `general-purpose` restores the curation problem with none of the
signal. Note `.claude/agents/` is read at **session start**: a newly added agent is not
dispatchable until the session reloads.

Every task report must cite the directives it applied **by number and with a verbatim quote**,
grep-checkable against the Spine — that is the only observable separating "read the standards"
from "didn't".

## Agent skills

**`superpowers` is the host process; `mattpocock-skills` supplies tools, not a pipeline.**
The `prompts/` standards overlays are written against `superpowers:brainstorming` and
`superpowers:subagent-driven-development` — those own the flow. Matt's `grill-with-docs` →
`to-spec` → `to-tickets` → `implement` is a *competing* pipeline for the same span: don't
run it as the host, or the overlays end up layered on a process that isn't running.
Two of its skills conflict outright with rules here — `implement` ends "commit your work to
the current branch" (**Other / General** says commit only when asked), and `to-spec` writes
the spec to the issue tracker rather than to `development/` (see **Issue tracker** below).

Matt's skills split by frontmatter into ones I can invoke and ones only you can type:

- **Model-invocable** (a `prompts/` file may cite these as instructions): `/grilling`,
  `/diagnosing-bugs`, `/tdd`, `/codebase-design`, `/domain-modeling`, `/prototype`,
  `/research`, `/resolving-merge-conflicts`.
- **User-typed only** (`disable-model-invocation: true` — a repo file telling me to use one
  is a **no-op that reads like an instruction**, so never write one): `/grill-with-docs`,
  `/to-spec`, `/to-tickets`, `/implement`, `/improve-codebase-architecture`, `/triage`,
  `/wayfinder`, `/ask-matt`.

When to reach for the user-typed ones here:

- **`/improve-codebase-architecture`** — hunting expansion opportunities. Nothing else in
  this repo does this; it's the main reason Matt's set is installed.
- **`/grill-with-docs`** — sharpening a big feature before `superpowers:brainstorming`.
- **`/triage`**, **`/wayfinder`**, **`/to-tickets`** — no current use: there's no issue
  inflow, and this is a mature codebase rather than a foggy greenfield.

Two skill names are **ambiguous** — say which you mean:

- **`/tdd`** — `mattpocock-skills:tdd` is the one this project uses (see **Testing**);
  `superpowers:test-driven-development` is a different, stricter skill and is overridden here.
- **`/code-review`** — both Claude Code and `mattpocock-skills` define it. Or use
  `prompts/adversarial-review.md`.

### Issue tracker

Specs and plans live under `development/<YYYY-MM-DD-slug>/` per
`prompts/new-feature-standards.md` — that is canonical and takes precedence.
`.scratch/<feature-slug>/` holds only ephemeral ticket files, and only if you use Matt's
tracker skills. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, each label string equal to its name.
See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root (neither exists yet;
`/domain-modeling` creates them lazily). See `docs/agents/domain.md`.

## Development archive (`development/`)

`development/` is a committed, per-feature record of how features were built with Claude —
one `YYYY-MM-DD-slug/` folder per feature holding the prompts used, the generated+hand-edited
`SPEC.md`, a scrubbed `transcript.md`, and an auto-generated `statistics.md`. It is a
**historical record, not a primary source of documentation** — don't rely on it for how the
code works (that's the code, this file, and `docs/`). See `development/README.md` for the full
convention. Two rules matter when working here: transcripts must be **scrubbed of secrets**
(run the `/archive-session` skill, which invokes `development/finalize-session.py`) before
committing, and the raw session JSONL is **never committed** (gitignored). A feature's
`development/` folder is committed **in the same commit** as the code it documents.

## Dev container

`.devcontainer/` defines a sandboxed Node/Debian image (`Dockerfile`, `devcontainer.json`,
`container-start.sh`) that pre-installs uv+Python, PHP+Composer, Terminus, AWS CLI, mise, and
Claude Code, with SSH keys under `.devcontainer/ssh/` and a Terminus token cache under
`.devcontainer/terminus/`. **The egress firewall is currently disabled** — the script is checked
in as `DISABLED_init-firewall.sh`, so don't assume network lockdown. Secret handling here is
still a work in progress (see README TODO).

## Pantheon API

The script makes use of [`terminus`](https://docs.pantheon.io/terminus) to interface with
Pantheon.  However, Pantheon also has a public API that can be used either directly by
AI tools to do their work, or in the script. A goal is replace the script's use of
terminus with the Pantheon API, but only in the cases where it makes sense (equivalent
or better functionality, no significant downsides).

**GUIDANCE FOR IMPLEMENTING NEW FUNCTIONALTY OR FEATURES**: prefer using the Pantheon
API when adding new code to the script, unless using `terminus` would be better for some
reason (examples: the API lacks necessary endpoints, it would be significantly cleaner
or significantly simpler to use `terminus`, using `terminus` would give better results,
...).

The Pantheon's API schema is available at https://api.pantheon.io/docs/swagger.json
Fetch it as necessary.

As of July 3, 2026, there is no documentation or examples on https://docs.pantheon.io/ on
how to use the Pantheon API, so some information is below.  Freely adapt what's below to
Python or any other languages/environments where you would like to use the Pantheon API.

1. Get a machine token. A machine token is already available as a part of the configuration
for `terminus`.
```bash
PANTHEON_USERNAME=$(ls -1 ~/.terminus/cache/tokens/ | head -1)
MACHINE_TOKEN=$(jq -r .token < ~/.terminus/cache/tokens/"${PANTHEON_USERNAME}")
```

2. Use the machine token to get a session token:
```bash
SESSION_TOKEN=$(curl -s -X POST -H "Content-Type: application/json" https://api.pantheon.io/v0/authorize/machine-token -d "{ \"machine_token\": \"${MACHINE_TOKEN}\", \"client\": \"curl\" }" | jq -r .session)
```

3. Use the session token to call the API endpoints you want to use.  This example uses a site name to get the site ID, then uses the site ID to get the site info:
```bash
SITE_NAME="its-wws-test1"  # real example site that can always be used for read-only operations

# Use the site name to get the site ID:
SITE_ID=$(curl -s -H "Authorization: Bearer ${SESSION_TOKEN}" "https://api.pantheon.io/v0/site-names/${SITE_NAME}" | jq -r .id)

# Use the site ID to get the site info:
curl -s -H "Authorization: Bearer ${SESSION_TOKEN}" "https://api.pantheon.io/v0/sites/${SITE_ID}" | jq .
```

## Reference material

Fetch information as needed from the websites, using the HTTP request header
`Accept: text/markdown`. Follow links on the website pages as needed.

* Pantheon documentation: https://docs.pantheon.io
* Information about using the Cloudflare API: https://developers.cloudflare.com/fundamentals/api/
* Cloudflare API documentation: https://developers.cloudflare.com/api/
* Cloudflare products and services in general: https://developers.cloudflare.com/

## Other / General
* **Before writing, reviewing, or refactoring any code in this repo, invoke the
  `andrej-karpathy-skills:karpathy-guidelines` skill and follow it.** This is not optional and
  not a judgment call — do it even when the change looks trivial. (Skip it only for purely
  conversational turns that touch no code.)
* Avoid flattery as feedback, stick to facts that matter. For example, "Got it — that's a meaningful architecture upgrade, and a good one." doesn't add anything of value. But do give me feedback about things that are not good, could be improved, or could change what decisions get made.
* Commit only when asked. Only branch if explicitly directed to do so.


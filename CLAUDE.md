# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`pantheon-sitehealth-emails` is a standalone Python script that pulls traffic and
site-health data from [Pantheon](https://pantheon.io/) hosting (via the Terminus CLI,
WP-CLI, and Drush), stores traffic history in a database, and emails each site owner a
monthly report with a plan-cost recommendation. It is used by University of Michigan ITS
Web Hosting Services and is written to be reusable by other institutions via a config file.

## Commands

The whole tool is one executable script, `./pantheon-sitehealth-emails` (run it directly;
it has a `#!/usr/bin/env python` shebang and expects the venv active). There is no build
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
only refreshes traffic data; `--only-warn` checks sites for warnings without generating
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

### Single-module core + `script_context` shared state

Nearly all logic lives in the top-level `pantheon-sitehealth-emails` script (~3900 lines).
The one carved-out exception is **`dns_classify.py`**, the DNS engine: it resolves each
domain's A/AAAA records and classifies them against the Cloudflare IP ranges
(`classify_domains`, returning a `DnsFacts` NamedTuple), and `stuff_dns_contract()` publishes
those facts into the `site_post_dns` data-contract keys (below). It is a pure data producer —
presentation (notices) lives in `check/dns/`, not here. Cross-cutting state and helpers live
in **`script_context.py`** (imported everywhere as
`sc`): `sc.options` (parsed argv), `sc.config` (parsed TOML), `sc.plugin`/`sc.check`
(loaded modules), `sc.news`, `sc.console` (rich), `sc.hooks`, `sc.substitutions`, and
helpers `debug()`, `add_hook()`/`invoke_hooks()`, `add_news_item()`, `html_to_text()` (notice-adding
is now a `SiteContext` method, below). **`html_to_text()` builds a fresh `HTML2Text` per call** —
never reintroduce a shared instance: it is stateful, and sharing one made the first notice of a run
render in a different link style from every other (the module-level `sc.text_maker` it replaced is
gone). The parser is built by `build_arg_parser()` and `sc.options`
is populated by the caller via `parse_args()` before other functions run, so it is
available to every function at call time.

### Plugin / check module system (`plugin/`, `check/`)

`find_modules()` walks `plugin/` and `check/` for **non-empty `__init__.py`** files (the
empty top-level `plugin/__init__.py` and `check/__init__.py` are skipped) and imports each
containing package (currently `plugin.aws`, `plugin.cloudflare`, `plugin.env`, `plugin.umich`,
`check.cloudflare`, `check.dns`, `check.pantheon_cdn_change`, `check.umich`). Each `__init__.py` self-registers at import time — usually pulling in a
sibling file with the actual logic (`aws/get_secret.py`, `cloudflare/ips.py`, `env/get_env.py`,
`umich/portal.py`, `check/umich/sitelens.py`) — guarded by a check of `sc.config` (e.g.
only register if `[Cloudflare].enabled`). **Exception:** `plugin.env` (the `<{env NAME}` /
`<{secret env NAME}` substitutions, with an optional trailing default) registers
**unconditionally** — no `[Env]` section — because it has no dependency and core config
(`[SMTP].username = "<{env USER}"`) needs it. Modules register by:
- **Hooks** — `sc.add_hook('<phase>', {'name': …, 'func': …})`. Phases are the ordered
  `sc.PHASES` tuple: `setup` (once per run — **including `--create-tables`**, which exits
  later), then per site `site_pre` (rename of the old `check` seam), `site_post_traffic`,
  `site_post_dns`, `site_post_gather`, `site_pre_render`. Each site phase receives the
  `SiteContext`; the per-phase guaranteed keys are the data-contract table below. Bare
  names not in `PHASES` are a **fatal error** in both `add_hook` and `invoke_hooks`;
  dotted names (e.g. `setup.umich.portal`) are plugin-defined events, allowed and
  invoked by whoever owns them. Gating: phases through `site_post_gather` run on
  full-report and `--only-warn` paths; `site_pre_render` full-report only; `--update`/
  `--import-older-metrics` never reach any site phase; a per-site fatal error (e.g.
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
`cloudflare_cms.py`, the relocated U-M CMS-integration checks at `site_post_gather`; and
`check/cloudflare/` — the opt-in `[Cloudflare.cachecheck]` cache checks, egress-IP test at
`setup` + per-FQDN HTTP checks at `site_post_dns`, see `docs/cloudflare-cachecheck.md`).
DNS-resolution notices live in `check/dns/` (`notices.py` builders + the `site_post_dns`
`hook.py`), fed by the `dns_classify.py` engine; `no-domains`/`no-primary-domain` remain in
core. `check/pantheon_cdn_change/` (`site_post_dns`, unconditional registration) flags
custom domains still CNAME'd to the legacy Pantheon GCDN (Fastly) — in public DNS or in
Cloudflare — and gets the replacement records Pantheon requires from `terminus domain:dns`;
**temporary**, delete once Pantheon's CDN migration is done — see
`docs/pantheon-cdn-change.md`.
To add a check or integration, create a new package dir with a non-empty `__init__.py`
that self-registers — no central registry to edit. Check modules cannot import the
dash-named main script; the helpers they need are exposed as `sc` attributes near the
`cloudflare_enabled()` def (`sc.escape_url`, `sc.check_wordpress_plugin`,
`sc.check_drupal_module`, `sc.umich_enabled`, `sc.cloudflare_enabled`, `sc.terminus`,
`sc.fqdn_re`) — extend that block for new ones (tests
monkeypatch these when loading check modules standalone). `check/cloudflare/httpseam.py`
holds the ONE monkeypatchable HTTP seam (`fetch`/`sleep`) and `egress.py` its own `probe`
seam — route any new outbound HTTP in that package through them to stay offline-testable.

### Per-site report pipeline (in `main()`)

For each site: build a `site_context` dict (holds `notices`, `sections`, `attachments`,
traffic data, plan info), invoke the site phases (below) at their seams, gather
Pantheon/WP/Drupal data, compute the plan recommendation from `[Pantheon.plan_info]` in
the config, then render.

**Normative per-phase data contract** — main() stuffs these `site_context` keys just
before invoking each phase; hooks code against this table (keys always exist, empty/None
when the source was disabled, malformed, or failed):

| Phase | Guaranteed new keys (beyond `site`/`notices`/`sections`/`attachments`) |
|---|---|
| `site_pre` | — (fires after the traffic gather and the `--update`/`--import-older-metrics` continues, just before `site_post_traffic` — NOT at SiteContext creation) |
| `site_post_traffic` | `traffic_rows` (`list[TrafficRow]` — plain `NamedTuple` data, attribute names matching the ORM model: `.site_id`, `.traffic_date`, `.site_plan`, `.visits`, `.pages_served`, `.cache_hits`; **not** live ORM rows, because a `db_retry` rollback expires every loaded ORM object, so a hook holding one would emit an unretried SELECT on the next attribute read), `start_date`, `end_date` |
| `site_post_dns` | `domains`, `custom_domains`, `primary_domain`, `main_fqdn`, `fqdns_behind_cloudflare`, `fqdns_not_behind_cloudflare`, `not_in_dns`, `behind_cloudflare_not_proxied`, `proxied_in_multiple_zones`, `dns_transient` (Cloudflare classification lists `[]` when `[Cloudflare]` disabled, the FQDN resolved to no address, or domains malformed. A FQDN resolving to nothing is `not_in_dns` when definitive else `dns_transient` (unknown) — neither runs Cloudflare checks; a FQDN with ≥1 resolved address is classified even if a sibling lookup was transient. Produced by `dns_classify.classify_domains()`, published via `stuff_dns_contract()`) |
| `site_post_gather` | `framework` (str), `site_url` (str, `""` when unknown), `wordpress_version`/`drupal_version` (str; `"unknown"` — NOT None — when that framework's version fetch failed; None only when not that framework), `wordpress_plugins` (list\|None), `drupal_modules` (**dict**\|None — drush pm:list returns a dict keyed by module name); None on the plugins/modules keys = not that framework or the gather failed |
| `site_pre_render` | everything above (full-report path only; no consumer yet — the documented seam for future report-shaping hooks) |

- **Notices vs. news**: `site_context` is a **`sc.SiteContext`** (a `dict` subclass, so
  `site_context['notices'|'sections'|'attachments'|'site']` access is unchanged) constructed once
  per processed site, as far up the per-site loop as possible (after the portal/not-requested/
  Sandbox skips). Add to it via its methods — `site_context.add_notice(notice)` /
  `.add_notices(list)` (builders: `wp_error`/`drush_error`/`check_wordpress_plugin`/`check_drupal_module`) / `.add_section(...)` /
  `.add_attachment(...)` — this is the **canonical** path (the old module-level
  `sc.add_notice`/`add_notices` free functions were removed). `add_notice` fills in
  `icon` (from `type`), plaintext `text` (via `html2text`), and honors `order`
  (`prepend`/`first` → front). `add_news_item()` (still an `sc` function) adds an org-wide item to
  `sc.news` (config-inline `[News.<x>]` sub-tables + `*.toml` files in `[News].folder` are both
  loaded by `load_news_items()`). Notice dicts carry their own bespoke `text`, so `add_notice`'s
  defaults are no-ops for them; every notice needs a `csv` key (`site,code,...`) — several report
  paths read `n["csv"]`. Site-phase hooks receive the `SiteContext` and call these methods directly
  (see `check/umich/sitelens.py`); tests build one with `sc.SiteContext({"name": ...})`.
- **Terminus/WP/Drush wrappers**: `run_terminus()` is the low-level subprocess call (5-min
  timeout, returns `(stdout, stderr, fatal)`). `terminus()` wraps it for JSON with a
  session-expiry retry and **returns `(result, errors, fatal)`** (`result` is `None` on a JSON
  decode failure). Call sites that index into the result use `terminus_data(...)`, which raises
  the named `TerminusError` when the command was fatal or returned no data (org-level calls
  abort; per-site calls skip that site). `wp()`/`wp_eval()` and `drush()`/`drush_php_script()`
  run WordPress and Drupal commands on a `site.env` remotely (all return 3-tuples too);
  `wp_error()`/`drush_error()` build alert notices from command failures. Prefer these wrappers
  over calling `terminus` directly.
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

SQLAlchemy declarative models `PantheonTraffic` and `PantheonOverageProtection` (see class
defs near the top of the script). Backend is chosen by the `[Database]` TOML section:
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
`build_traffic_table_rows`, `load_overage_protection_window`) and NEVER a statement with pending
writes — a rollback discards them,
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
the rollback failure, the most definite connection loss there is.

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

- **`pantheon-sitehealth-emails.py` is a committed symlink to `pantheon-sitehealth-emails`, and
  exists only so CodeGraph can index the main program.** It is NOT a second copy and NOT the file
  to edit — edit `pantheon-sitehealth-emails`. CodeGraph picks a parser by file extension
  (`path.extname()`), so an extension-less file is silently skipped: before this symlink existed,
  the index held 117 files and **zero symbols from the ~4,600-line core program**, so every
  `codegraph_explore` answered from `check/`/`plugin/`/`tests/` while blind to the file being
  edited. The symlink is tracked (not git-ignored) on purpose — a git-ignored one would vanish on
  a fresh clone and the blindness would return silently. Known limitation that remains: the tests
  import the program via `SourceFileLoader` on the **dash** name, so CodeGraph cannot link tests
  to its symbols and reports "no covering tests found" for them; the symbol index and call graph
  are unaffected.
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
- **The script is imported, not re-parsed.** `tests/conftest.py` loads the extension-less
  `pantheon-sitehealth-emails` via `importlib`/`SourceFileLoader` (fixture `psh`). Argparse was
  refactored into `build_arg_parser()`/`parse_args()`; `sc.options` is set by the caller, so a
  test sets it (the `reset_sc` autouse fixture does) before calling functions. `MPLBACKEND=Agg`
  must be set before the load (conftest does this) because the module imports `matplotlib.pyplot`
  at the top.
- **Two mock seams.** All Pantheon/WP/Drush I/O funnels through `run_terminus()` — monkeypatch it
  for in-process tests, or use the PATH-shim fake `terminus` (`tests/shims/terminus`, record/replay)
  for full subprocess e2e. The `php inline-styles.php` CSS inliner uses **real php**.
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
  `estimate_month_visits`, `plan_costs` (the cost model — DB-free via an injected
  `op_lookup(month)`), plus `load_news_items`, `build_plan_over_time` (returns `[]` for
  zero traffic; `main()` guards the empty case and skips the plan sections), and
  `sites_from_resume_point`/`merge_prior_results` (the `--resume-from` logic, which cannot be
  reached through the `--all`-banned subprocess interlock and so is only testable in-process). The
  extractions are behavior-preserving (goldens byte-identical). **`classify_hostname_dns` is NOT
  one of these** — it moved out of the script into `dns_classify.py`; import it from there.
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
  annual-billing notices, the `umich-oidc-login`/Hummingbird/Drupal user-agent checks, and the
  branding in `email_template.html` (its.umich.edu URLs, `webmaster@umich.edu`, `node/4705`). The
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
work, and cite it by name rather than re-deriving the conventions:
`new-feature-standards.md` (how features get specced),
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


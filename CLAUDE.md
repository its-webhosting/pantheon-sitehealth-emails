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
step and no test suite.

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

Key flags: `--all` vs. an explicit `SITE` list are mutually exclusive (one is required
unless `--create-tables`). Without `--for-real`, all mail is sent to the logged-in user,
not to owners — this is the primary safety mechanism, always dry-run first. `--update`
only refreshes traffic data; `--import-older-metrics` backfills Pantheon's weekly/monthly
aggregates; `-v`/`-vv`/`-vvv` increase verbosity (`--create-tables` forces `-vvv`).

## Required runtime credentials / external tools

Running against real sites needs, in the environment: `terminus` authenticated with a
Pantheon machine token; an SSH agent holding the Pantheon key (`ssh-add`); `SMTP_PASSWORD`
(U-M Kerberos password for `smtp.mail.umich.edu:465`, hardcoded in `smtp_login()`);
optionally `AWS_*` and `CLOUDFLARE_EMAIL`/`CLOUDFLARE_API_KEY`. `php` + `composer` must be
on PATH. Note the README warning: Terminus does not work with PHP 8.4 — use PHP 8.3 or
earlier.

## Architecture

### Single-module core + `script_context` shared state

Nearly all logic lives in the top-level `pantheon-sitehealth-emails` script (~3700 lines).
Cross-cutting state and helpers live in **`script_context.py`** (imported everywhere as
`sc`): `sc.options` (parsed argv), `sc.config` (parsed TOML), `sc.plugin`/`sc.check`
(loaded modules), `sc.news`, `sc.console` (rich), `sc.hooks`, `sc.substitutions`, and
helpers `debug()`, `add_hook()`/`invoke_hooks()`, `add_notice()`, `add_news_item()`.
Because argparse runs at import time (module scope, not inside `main()`), `sc.options` is
available to every function.

### Plugin / check module system (`plugin/`, `check/`)

`find_modules()` walks `plugin/` and `check/` for **non-empty `__init__.py`** files (the
empty top-level `plugin/__init__.py` and `check/__init__.py` are skipped) and imports each
containing package (currently `plugin.aws`, `plugin.cloudflare`, `plugin.umich`,
`check.umich`). Each `__init__.py` self-registers at import time — usually pulling in a
sibling file with the actual logic (`aws/get_secret.py`, `cloudflare/ips.py`,
`umich/portal.py`, `check/umich/sitelens.py`) — guarded by a check of `sc.config` (e.g.
only register if `[Cloudflare].enabled`). Modules register by:
- **Hooks** — `sc.add_hook('setup', {...})` or appending to `sc.hooks['check']`. `setup`
  hooks run once (DB connections, fetching Cloudflare IPs, etc.); `check` hooks run once
  per site with the site's `site_context`. Invoked via `sc.invoke_hooks(name, ...)`.
- **Config substitutions** — appending to `sc.substitutions`. TOML string values
  containing `<{ ... }>` are resolved by `process_config()`/`config_substitution()`
  against these registered functions. `process_config()` is run twice: once before `setup`
  hooks and once after (so hooks can populate data that later substitutions consume).

`plugin/` = data sources / integrations (aws secrets, cloudflare IPs, umich portal DB);
`check/` = site-health checks that add report sections (e.g. `check/umich/sitelens.py`).
To add a check or integration, create a new package dir with a non-empty `__init__.py`
that self-registers — no central registry to edit.

### Per-site report pipeline (in `main()`)

For each site: build a `site_context` dict (holds `notices`, `sections`, `attachments`,
traffic data, plan info), run `check` hooks against it, gather Pantheon/WP/Drupal data,
compute the plan recommendation from `[Pantheon.plan_info]` in the config, then render.

- **Notices vs. news**: `add_notice()` adds a per-site alert to `site_context['notices']`;
  `add_news_item()` adds an org-wide item to `sc.news`. Both take `type` (`info`/`warning`/
  `alert`, which maps to an emoji `icon`) and an HTML `message`; the plaintext `text` is
  auto-generated via `html2text` if absent. News items also come from `*.toml` files in the
  `[News].folder` dir (`./news`); see `sample-news/` for the format.
- **Terminus/WP/Drush wrappers**: `run_terminus()` is the low-level subprocess call (5-min
  timeout, returns `(stdout, stderr, fatal)`). `terminus()` wraps it for JSON with a
  session-expiry retry. `wp()`/`wp_eval()` and `drush()`/`drush_php_script()` run WordPress
  and Drupal commands on a `site.env` remotely; `wp_error()`/`drush_error()` build alert
  notices from command failures. Prefer these wrappers over calling `terminus` directly.
- **Rendering**: Jinja2 templates `email_template.html` and `email_template.txt` are
  rendered per site into `build/<site>.{html,txt}`. The HTML is then run through
  `inline-styles.php` (PHP Emogrifier via `vendor/`) to inline CSS for email clients. Charts
  (traffic surge bars, SiteLens gauges) are generated with matplotlib and attached as inline
  images (`make_msgid` CIDs). Everything is assembled into a MIME `EmailMessage` and sent
  via `SMTP_SSL`.

### Database

SQLAlchemy declarative models `PantheonTraffic` and `PantheonOverageProtection` (see class
defs near the top of the script). Backend is chosen by the `[Database]` TOML section:
`sqlite` (default, `database.db` in repo) or `mysql`. `--create-tables` creates the schema;
traffic rows are upserted (note the `sqlite_insert` import for dialect-specific upsert).

### Configuration (`pantheon-sitehealth-emails.toml`)

The active config is a symlink to `pantheon-sitehealth-emails-config/pantheon-sitehealth-emails.toml`
(a separate private repo); `sample-pantheon-sitehealth-emails.toml` is the documented
template. Institution-specific data (plan names, traffic limits, prices, overage costs,
Pantheon org id, DB, Cloudflare/AWS toggles) lives here — the report's recommendations are
driven entirely by `[Pantheon.plan_info]` and `[Pantheon.plan_sku_to_name]`. Keep U-M-only
logic out of the core script and behind config flags / `umich` plugin+check packages so the
tool stays reusable by other institutions.

## Conventions & gotchas

- The core script is deliberately one big file; match that style rather than splitting it,
  and put institution- or integration-specific code in `plugin/`/`check/` packages.
- Generated artifacts land in `build/` (git-ignored); `database.db`, `fqdns.json`, and the
  `.eml`/`.html`/`.txt` outputs are working data, not source.
- Type-hint tuples like `-> (str, str, bool)` appear throughout; these are the existing
  (technically non-idiomatic) house style — follow the surrounding code.
- There is an active TODO list in `README.md` describing planned work (daily traffic alerts,
  Cloudflare/security scoring, moving capture into the portal app, better error handling).

## Testing

There is a pytest harness under `tests/` (built 2026-07; design in
`development/2026-07-04-test-harness/SPEC.md`). Run it with `./run-tests` (wrapper over
pytest): `./run-tests --fast` is the offline inner loop; `./run-tests` adds the live tier;
`--llm` gives terse machine-parseable output; `--coverage`, `--update-goldens`, and
`--record` do what they say. Tiers are pytest marks: `unit`, `integration`, `e2e`, `live`,
`render`, `email`, `slow`. **When you change the program, add/adjust the appropriate tests in
the same change** (this project does not do TDD — tests follow the change).

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
- **Safety interlock.** `run_program()` in conftest is the only sanctioned way to run the program
  in a subprocess; it raises `ForbiddenFlagError` if `--all`/`-a`/`--for-real` appear, and
  `ForbiddenLiveDataError` if `--create-tables`/`--import-older-metrics` would run live or against
  a non-fixture config (a config-**path** allowlist, not a backend-type test — the production
  default DB is also sqlite). Never bypass it. Tests use only `its-wws-test1`/`its-wws-test2`,
  read-only.
- **Pure-helper seam.** Four pure functions were extracted from `main()` as module-level defs so
  they're importable as `psh.<fn>` and unit/property tested: `overage_blocks`, `contract_year_end`,
  `estimate_month_visits`, and `plan_costs` (the cost model — DB-free via an injected
  `op_lookup(month)`; the U-M downgrade guardrails/notices remain inline in `main()` for the later
  de-monolith stage). The extraction is behavior-preserving (WordPress golden byte-identical).
- **Offline e2e determinism.** The shim-backed run uses `tests/fixtures/config/minimal.toml`,
  seeded traffic, `--date 2026-03-31` (a mid-year date avoids the U-M contract-year-end path),
  and a `domain:list` fixture reduced to the platform domain (so no live DNS). Golden snapshots
  normalize the volatile `make_msgid` CIDs; refresh with `./run-tests --update-goldens`. There are
  two goldens: WordPress (`its-wws-test1`, fixtures in `tests/fixtures/terminus/`) and Drupal
  (`its-wws-test2`, `tests/fixtures/terminus-drupal/`, selected via `run_program(fixtures_dir=…)`).
  Refresh WordPress fixtures with `./run-tests --record`, Drupal with `python tests/tools/record.py
  --drupal` (both trim the org list to the one test site and scrub team emails).
- **The offline golden only reaches the ≤4-month "not enough data" state** (its recorded metrics
  fall after the March report date), so the extracted `plan_costs` cost model is exercised
  end-to-end by `tests/e2e/test_recommendation_e2e.py` (seeds >4 in-window months) plus its
  unit/property tests — not by the golden. The render tier vendors axe-core locally
  (`tests/vendor/axe.min.js`) so it stays offline.
- **The reusable (non-UMich) path had latent bugs** that production never hit because U-M always
  runs with the UMich plugin enabled. Several U-M-specific code paths in the core script are not
  yet behind the `[UMich].enabled` flag; the planned refactor should move them out. When adding
  code, keep institution-specific logic behind config flags / the `umich` plugin+check packages.

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

`.devcontainer/` defines a sandboxed Node/Debian image (`Dockerfile`, `devcontainer.json`)
that pre-installs uv+Python, PHP+Composer, Terminus, AWS CLI, mise, and Claude Code, with a
locked-down firewall (`init-firewall.sh`) and SSH keys under `.devcontainer/ssh/`. Secret
handling here is still a work in progress (see README TODO).

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
* Avoid flattery as feedback, stick to facts that matter. For example, "Got it — that's a meaningful architecture upgrade, and a good one." doesn't add anything of value. But do give me feedback about things that are not good, could be improved, or could change what decisions get made.
* Commit only when asked. Only branch if explicitly directed to do so.


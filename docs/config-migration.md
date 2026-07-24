# Configuration migration across the modularization campaign

## Headline: no key changes are required

The modularization campaign (I0–I14, `development/2026-07-17-modularization-campaign/`)
moved the several-thousand-line main script into the `psh/` core package and the
self-registering `check/` / `plugin/` packages **without changing the configuration
schema**. An existing `pantheon-sitehealth-emails.toml` that worked before the campaign
keeps working, unedited, after it. There are **no renames**, no removed keys, and no keys
whose meaning changed. **An operator has nothing to migrate.**

This document records *why* that is a verified finding rather than a hope, lists what the
config carries today, shows the optional sections an operator MAY now add, and states the
production-config instruction.

## Audit trail: why "no migration" is a finding, not a hope

The claim "no key changes are required" would be worthless as an assurance and merely
convenient as a wish. It is neither: it follows from a rule the campaign held itself to from
the start, plus a key-by-key audit of the sample config against the code that reads it.

### 1. Every campaign-introduced key landed in final shape when introduced

`CAMPAIGN.md` §5 required: *"New keys land in final shape as introduced (I3 onward)."* An
increment that introduced a config key introduced it in the shape it holds today — there was
never an interim shape that a later increment renamed or reshaped. **Because no key ever had
an interim shape, there is nothing to migrate from.**

The campaign introduced exactly four config keys, all of the same family — an `enabled` flag
under a `[Check.<name>]` section, one per relocated check package. Each was introduced
`enabled = true` and remains so:

| Key | Increment introduced | Commit |
|---|---|---|
| `[Check.pantheon].enabled` | I8 | `3ea3491` |
| `[Check.wordpress].enabled` | I9 | `309ebcf` |
| `[Check.drupal].enabled` | I10 | `eedd60c` |
| `[Check.addon_updates].enabled` | I10 | `03c81c0` |

Every other section and key the config can carry — `[Pantheon]`, `[Database]`,
`[Cloudflare]`, `[Cloudflare.cachecheck]`, `[SMTP]`, `[Email]`, `[AWS]`, `[UMich]`,
`[News]` — **predates** the campaign. The campaign relocated the code that reads them
(for example, the SMTP/MIME layer moved into `psh/mail.py`, the DB layer into `psh/db.py`)
but changed neither the key names nor their semantics. The four offline e2e goldens are
byte-identical across the whole campaign, which is the empirical proof that no config-driven
behavior changed (see [Empirical proof](#empirical-proof-the-goldens) below).

### 2. Every sample key still has a live reader in the same code path

`sample-pantheon-sitehealth-emails.toml` was audited key-by-key against the code that reads
each key (verified 2026-07-24). Every active (uncommented) sample key resolves to a reader,
and no reader depends on a key the sample omits without reason:

| Key | Reader (`file:line`) |
|---|---|
| `[Pantheon].org_id` | `psh/cli.py:496`, `psh/cli.py:523` |
| `[Pantheon].overage_block_size` | `psh/cli.py:455` → `psh/plans.py:34,76,110` |
| `[Pantheon].overage_block_cost` | `psh/cli.py:456` → `psh/plans.py:76,111` |
| `[Pantheon.plan_info]` (table) | `psh/plans.py:233` (`PlanCatalog.from_config`) |
| `[Pantheon.plan_info.*].upgrade_at` | `psh/plans.py:245`, `psh/charts.py:109,300` |
| `[Pantheon.plan_info.*].upgrade_to` | `psh/plans.py:235,246` |
| `[Pantheon.plan_info.*].downgrade_to` | `psh/plans.py:236,247`, `psh/charts.py:334` |
| `[Pantheon.plan_info.*].traffic_limit` | `psh/plans.py:74,244`, `psh/charts.py:75,299` |
| `[Pantheon.plan_info.*].cost` | `psh/plans.py:66,109` |
| `[Pantheon.plan_sku_to_name].*` | `psh/plans.py:280,285` (written by `plugin/umich/portal.py:60`) |
| `[Check.pantheon].enabled` | `check/pantheon/__init__.py:8` |
| `[Check.wordpress].enabled` | `check/wordpress/__init__.py:8` |
| `[Check.drupal].enabled` | `check/drupal/__init__.py:13` |
| `[Check.addon_updates].enabled` | `check/addon_updates/__init__.py:12` |
| `[Database].type` | `psh/db.py:260,360,362,383` |
| `[Database].name` | `psh/db.py:361,365` |
| `[Database].host` / `.port` / `.user` / `.password` (commented) | `psh/db.py:364,365` |
| `[Cloudflare].enabled` | `psh/cli.py:425`, `plugin/cloudflare/__init__.py:8` |
| `[Cloudflare].email` | `plugin/cloudflare/client.py:28` |
| `[Cloudflare].api_key` | `plugin/cloudflare/client.py:29` |
| `[Cloudflare].api_token` (commented) | `plugin/cloudflare/client.py:25` |
| `[Cloudflare.cachecheck].enabled` | `check/cloudflare/__init__.py:16` |
| `[Cloudflare.cachecheck].account_id` / `.list_name` (commented) | `check/cloudflare/egress.py:129,130` |
| `[Cloudflare.cachecheck].user_agent` / `.timeout` / `.report_doc_url` (commented) | `check/cloudflare/cfg.py:11–19` |
| `[AWS].enabled` | `plugin/aws/__init__.py:6` |
| `[AWS].profile` | `plugin/aws/__init__.py:10` |
| `[AWS].default_region` | `plugin/aws/__init__.py:12` |
| `[Email].from` / `.reply_to` / `.bcc` / `.dry_run_to` / `.dry_run_username_domain` (commented) | `psh/mail.py:88–109` |
| `[Email].msgid_domain` (commented) | `script_context.py:175` |
| `[SMTP].enabled` | `psh/cli.py:505` |
| `[SMTP].host` / `.port` / `.password` | `psh/mail.py:29,30,32` |
| `[SMTP].username` | `script_context.py:186` |
| `[News].folder` | `psh/configuration.py` (`load_news_items`) |
| `[News.<item>].order` / `.icon` / `.message` | `script_context.py:190–197` (`add_news_item`) |

**Orphan keys (in the sample, read by nobody): none.**

**Keys read by code but absent from the sample:** the `[UMich]` family — `[UMich].enabled`,
`[UMich.portal].sites`, `[UMich.portal.db]` — is read by the `plugin/umich/` package and by
`psh/cli.py:542,547`. Its absence from the sample is **by design, not a gap**: the sample is a
generic, reusable template, and the University-of-Michigan sections live only in the private
production config repo. This is the same posture the whole codebase takes — institution-specific
data stays out of the shipped template.

**Sample comment corrections:** none were required. The campaign was behavior-preserving, so no
sample comment describes superseded behavior; every comment still describes what the reader in
the table above actually does. (Finding no correction is itself consistent with the headline:
had a comment gone stale, some behavior would have changed.)

## The section inventory (production config, verified 2026-07-24)

The live production config is the symlink
`pantheon-sitehealth-emails.toml` → `pantheon-sitehealth-emails-config/pantheon-sitehealth-emails.toml`
(a separate private repo). Its sections, in file order:

- `[Pantheon]`
- `[Pantheon.plan_info]` and the per-plan `[Pantheon.plan_info."<plan>"]` sub-tables
- `[Pantheon.plan_sku_to_name]`
- `[Database]`
- `[Cloudflare]`
- `[Cloudflare.cachecheck]`
- `[SMTP]`
- `[AWS]`
- `[UMich]`
- `[UMich.portal]`
- `[UMich.portal.db]`
- `[News]`

It carries **no `[Check.*]` sections and no `[Email]` section** — and **both default
correctly** without them: each `[Check.<name>]` defaults to `enabled = true` (an absent
section still registers the check, see below), and an absent `[Email]` falls back to the
original University-of-Michigan literals. So the production config gets exactly today's
behavior from every key it already has, and today's behavior from the two families it omits.

## What an operator MAY now add

This section is about the config an operator actually edits: their **production**
`pantheon-sitehealth-emails.toml`. Everything here is **optional**, and every default reproduces
today's behavior — add a section only to change a default; omitting it is not a downgrade.

**Which config are you editing?** The answer decides whether "add" even applies:

- **A production config that lacks these sections** — as U-M's does; the [section inventory](#the-section-inventory-production-config-verified-2026-07-24)
  above shows it carries no `[Check.*]` and no `[Email]`. Such a config MAY *add* them, appended
  to the file it already has. The merged example below is that case.
- **A config that already declares them** — as the shipped template
  `sample-pantheon-sitehealth-emails.toml` does — must **NOT** add a second copy. TOML forbids
  declaring a table twice: pasting a fresh `[Check.pantheon]` (or `[Email]`) into a file that
  already has one makes `tomllib` raise `Cannot declare ('Check', 'pantheon') twice`. The sample
  already ships these tables, active (not commented out) — verbatim from
  `sample-pantheon-sitehealth-emails.toml`:

  ```toml
  [Check.pantheon]
  # Generic Pantheon site-health checks: frozen site, uninitialized live environment on
  # a paid plan, unapplied upstream updates, PHP end-of-life.  Enabled by default; set
  # to false to disable all four.
  enabled = true


  [Check.wordpress]
  enabled = true          # PAPC, native-PHP-sessions, OCP-config, favicon checks


  [Check.drupal]
  enabled = true          # PAPC-module, Drupal-7-EOL/tag1_d7es, multisite-probe checks


  [Check.addon_updates]
  enabled = true          # pending add-on (plugin/theme/package) updates table notice
  ```

  and, further down, a live `[Email]` header (its keys all commented out):

  ```toml
  [Email]
  # Identity of the report emails.  All keys are optional; if omitted, the University of
  # Michigan defaults are used (the tool's original hardcoded values), so existing U-M runs
  # are unaffected.  Set these for a non-U-M deployment.
  ```

  For a config that already has these tables, the only thing "MAY" describes is flipping an
  existing `enabled = true` to `false` (or uncommenting an `[Email]` key) — **not inserting a
  new table.**

### What each addition does

- **Turning individual check packages off.** Each relocated check package is gated by an
  `enabled` flag under `[Check.<name>]`, **default `true`**. An absent `[Check]` section, an
  absent `[Check.<name>]` section, or an absent `enabled` key all leave the check registered —
  the gate is `sc.config.get('Check', {}).get('<name>', {}).get('enabled', True) is not False`
  (verified in each package's `__init__.py`), so only an explicit `enabled = false` disables one.
  A production config (which has none of these sections) adds one only to turn a check *off*.
- **Overriding the sender identity (`[Email]`).** Absent, `[Email]` falls back to the
  University-of-Michigan literals the tool originally shipped with (see
  `docs/email-configuration.md`). A non-U-M deployment adds it to send from its own addresses.
  Note the mail *server* section `[SMTP]` already exists in the production config, so only
  `[Email]` is new — do not re-add `[SMTP]`.

### The merged addition, in a production-shaped file

Shown appended to the tail of a production config — the file that has **no `[Check.*]` and no
`[Email]` sections today**, so nothing below collides with a table it already declares. This
whole snippet parses (verified with `tomllib`); the doc-authored comments below the marker are
this document's own explanation, not quotes from the sample:

```toml
# ... the production config's existing tail (it already has [SMTP], but no [Check.*]/[Email]) ...
[AWS]
enabled = true
default_region = "us-east-1"

[UMich]
enabled = true

[News]
folder = "./pantheon-sitehealth-emails-config/news"

# --- appended below: optional opt-outs and sender identity, all defaulting to today's behavior ---

[Check.pantheon]
enabled = false          # turn OFF the frozen-site / live-env / upstream-updates / PHP-EOL checks

[Check.wordpress]
enabled = false          # turn OFF PAPC / native-PHP-sessions / OCP-config / favicon checks

[Check.drupal]
enabled = false          # turn OFF PAPC-module / Drupal-7-EOL / multisite-probe checks

[Check.addon_updates]
enabled = false          # turn OFF the pending add-on updates table notice

[Email]
# Omitted keys fall back to the U-M literals, so a U-M run is unaffected; set these for a non-U-M deployment.
from         = "Example Web Team <webteam@example.edu>"   # the From: header
reply_to     = "webteam@example.edu"                       # the Reply-to: header
msgid_domain = "reports.example.edu"                       # domain for inline-image Content-IDs
bcc          = "ops@example.edu"                           # Bcc:, only with --for-real
dry_run_to   = "ops@example.edu"                           # extra dry-run recipient
dry_run_username_domain = "example.edu"                    # {smtp-username}@<this> added to To:
```

## Production-config instruction: no edits required

**The production `pantheon-sitehealth-emails.toml` needs no changes for the campaign.** This is
the answer to closing-audit §17 Q7.

The instruction is produced by two checks, both recorded above:

1. **Every key the production config carries is still read by the same code path.** The
   key→reader audit (verified 2026-07-24) traces every production key to a live reader; the
   campaign relocated those readers between modules but renamed and re-semanticized nothing.
2. **Every key the campaign introduced defaults to the pre-campaign behavior when absent.** The
   only campaign-introduced keys are the four `[Check.<name>].enabled` flags, each defaulting
   `true` — the exact behavior of the code before it was relocated, since relocating a check
   MUST NOT silently disable a check that ran unconditionally (`CAMPAIGN.md` §5). The production
   config omits all four and therefore keeps running all four checks, as it always did.

An operator who wants the new opt-out granularity MAY add the `[Check.*]` sections; an operator
who wants no change does nothing.

## Empirical proof: the goldens

The offline e2e goldens run against `tests/fixtures/config/minimal.toml` and
`tests/fixtures/config/minimal-nonumich.toml`, **neither of which the campaign edited**. That
they still render byte-identically is the evidence that no config shape or config-driven
behavior changed:

```bash
./run-tests -m e2e
git diff <campaign-base> -- tests/e2e/__snapshots__/   # empty
```

The e2e tier is green and the snapshot diff is empty across the campaign; the run performed at
the close of this increment is pasted in the I14d task report.

**Scope of what the goldens prove here.** Both fixture configs carry **no `[Check.*]` section**,
so the goldens exercise only the absent-section → default-`true` path — not the explicit
`enabled = true` / `enabled = false` toggling the sample and the snippets above show. The
goldens therefore support the narrower claim they actually cover — *no config shape or
config-driven behavior regressed* — and nothing wider. The default-`true` gate under explicit
toggling is proved instead by the per-package init tests, one each for the four `[Check.*]`
packages: `tests/integration/test_check_pantheon_init.py`,
`tests/integration/test_check_wordpress_init.py`, `tests/integration/test_check_drupal_init.py`,
and `tests/integration/test_check_addon_updates_init.py`.

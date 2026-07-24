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

Everything below is **optional**, and every default reproduces today's behavior. Add a section
only to change a default; omitting it is not a downgrade. The snippets are shown **merged into
their surrounding config context** — they are not fragments to paste over an existing file.

### Turning individual check packages off

Each relocated check package is gated by an `enabled` flag under `[Check.<name>]`, **default
`true`**. An absent `[Check]` section, an absent `[Check.<name>]` section, or an absent
`enabled` key all leave the check registered — the gate is
`sc.config.get('Check', {}).get('<name>', {}).get('enabled', True) is not False`
(verified in each package's `__init__.py`), so only an explicit `enabled = false` disables one.
Add these sections only if you want to turn a check *off*:

```toml
[AWS]
enabled = false
profile = "webhosting"
default_region = "us-east-1"

# Optional.  Each check package is enabled by default; set false to turn one off.
# Omitting the section entirely is identical to enabled = true.
[Check.pantheon]
enabled = true          # frozen-site, live-env, upstream-updates, PHP-EOL checks

[Check.wordpress]
enabled = true          # PAPC, native sessions, Object Cache Pro, favicon

[Check.drupal]
enabled = true          # multisite probe, PAPC module, D7 EOL

[Check.addon_updates]
enabled = true          # the pending plugin/theme/module updates table

[SMTP]
enabled  = false
host     = "smtp.mail.umich.edu"
port     = 465
```

### Overriding the sender identity (`[Email]`)

Absent, `[Email]` falls back to the University-of-Michigan literals the tool originally
shipped with (see `docs/email-configuration.md`). A non-U-M deployment adds it to send from its
own addresses. Merged next to the mail server section it belongs with:

```toml
[Email]
# All keys optional; omitted keys fall back to the U-M literals, so existing U-M runs are
# unaffected.  Set these for a non-U-M deployment.
from         = "Example Web Team <webteam@example.edu>"   # the From: header
reply_to     = "webteam@example.edu"                       # the Reply-to: header
msgid_domain = "reports.example.edu"                       # domain for inline-image Content-IDs
bcc          = "ops@example.edu"                           # Bcc:, only with --for-real
dry_run_to   = "ops@example.edu"                           # extra dry-run recipient
dry_run_username_domain = "example.edu"                    # {smtp-username}@<this> added to To:

[SMTP]
enabled  = true
host     = "smtp.example.edu"
port     = 465
username = "<{env USER}"
password = "<{secret env SMTP_PASSWORD}"
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

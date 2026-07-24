# CLAIMS.md — the I14d claim inventory and disposition table

The disposition table Tasks 2–5 are written from (SPEC §2.1). A load-bearing warning can only
leave a document through an explicit `drop-with-reason` row here; a stale claim leaves through a
`fix` row that states its correction.

**How this table was produced.** `tools/claim_check.py` extracts the mechanizable claims from
each in-scope document and decides each (PASS / FAIL / PROSE / ERROR). The command:

```bash
python development/2026-07-24-mod-I14d-closing/tools/claim_check.py \
    CLAUDE.md README.md CONTEXT.md tests/README.md docs/*.md prompts/*.md \
    ~/.claude/projects/-workspace/memory/*.md
```

Run 2026-07-24 in the venv (`script_context` importable, so `sc.*` claims decide, not ERROR):
**591 mechanizable claims** — 549 PASS, 21 FAIL, 21 PROSE. The 21 FAIL are the residue the
brief's Step 3 table enumerates; `--gate --allow claims-allow.txt` leaves **15** (the 6 allowed
dead-name mentions suppressed). `--self-test` → `SELF-TEST PASS  8 verdicts + COUNT both ways
(registered codes = 36)`.

**Disposition legend** (SPEC §2.1, extended for this task per the dispatch):

- `keep-verified` — verdict PASS; the claim survives the rewrite unchanged.
- `fix -> <corrected claim>` — verdict FAIL; the correction is stated so Tasks 2–5 write it
  rather than re-derive it.
- `drop-with-reason` — the claim leaves the document; the reason is in the row. (None in this
  run: every FAIL is a fixable correction or an allowed deliberate mention.)
- `allowed (see claims-allow.txt)` — a deliberate mention of something that no longer exists,
  matching an entry in `claims-allow.txt` with its reason.
- `PROSE - verify by hand` — the tool could not decide the claim with confidence (a basename-only
  path, a URL fragment, an artifact template). Resolved by the controller's fresh-context
  `psh-reviewer` prose-verification pass (SPEC §2.1 hybrid; brief Step 5, run by the controller),
  whose findings are folded back into these rows.

**PROSE rows the reviewer should prioritize** (obviously-stale, will be resolved by the rewrite):
`_legacy.py` and `ruff-broad.toml` recur as basename-only tokens in CLAUDE.md / README /
`modularization-campaign.md` — `_legacy.py` was deleted at I14a and `ruff-broad.toml` merged away
at I14b. The tool marks them PROSE only because they lack a directory component; they are the same
dead names the FAIL rows above catch in their full-path form.

---

## Keep list (SPEC §2.2, exhaustive — every one is a shipped bug already paid for)

Task 2's audit checklist: every row MUST appear in the rewritten CLAUDE.md. The **Section** column
is the section of the rewrite that will carry it (Task 2 finalizes placement).

| # | Warning | Bug it prevents | Section |
|---|---|---|---|
| 1 | `pantheon-sitehealth-emails.py` is a committed symlink; do not delete | ruff/pyright/CodeGraph blindness to the extension-less shim | Conventions & gotchas |
| 2 | Column-0 `f"""` notice literals move verbatim; `git diff -w` is not evidence | leading whitespace in rendered email, invisible to `-w` | Conventions & gotchas |
| 3 | `sc.console`: escape untrusted text; `soft_wrap=True` on copy-pasteable commands; tests reproduce width 80 | deleted `[parameters: …]`/`[notice]` fragments; the wrapped resume command that re-mailed every owner | Database (rich gotchas) |
| 4 | DB: read-release commit in the loaders; `db_retryable` predicate; whole-unit retry only; counters count *healed*, not attempted | MySQL 2013 on the reaped idle connection; partial write sets; the "1 reconnect" on a run that reconnected zero times | Database |
| 5 | `-results.json` is site-keyed and nothing else | metadata keys becoming phantom site rows in `monthly-report.txt` | Database |
| 6 | Two-binding seams: `psh.gateway.run_terminus` **and** `psh.gather.run_terminus`; `psh.mail.SMTP_SSL`; `psh.lifecycle.finish_run`; `psh.dns_classify.resolve`; `httpseam.fetch`/`sleep`; `egress.probe` | a mock that looks installed but isn't — real Terminus subprocess calls from a "mocked" test | Testing (mock seams) |
| 7 | Exactly ONE `sitecustomize.py`, in `tests/shims/pyshim/` | a second one means one silently never runs; `not in` assertions pass against a run that did nothing | Testing (subprocess shims) |
| 8 | `conftest._CWD_ASSETS` must include `check` and `plugin` | every e2e golden ran with every check disabled | Testing |
| 9 | `html_to_text()` builds a fresh `HTML2Text` per call | first notice of a run rendering in a different link style | Single-module core + script_context |
| 10 | Register the shorter substitution pattern before the longer one | best-match mis-binding → `KeyError` | Plugin / check module system (config substitutions) |
| 11 | `find_modules()` walks for **non-empty** `__init__.py`, CWD-relative | silently loading nothing | Plugin / check module system |
| 12 | `run_program()` safety interlock: `--all`/`--for-real`/live `--create-tables` refused | Invariant 7 | Testing (safety interlock) |
| 13 | Goldens are never refreshed to green; `terminus-cdnchange/` fixtures are hand-maintained | Invariants 1, 10 | Testing |
| 14 | `cloudflare_enabled` is read from config, never from `"plugin.cloudflare" in sc.plugin` | always-true test | Plugin / check module system |
| 15 | `reset_sc` snapshots/restores the notice registry; **no producing module may be executed outside a function-scoped fixture or test body, nor cached across tests** | `DuplicateNoticeCodeError` on the second load | Per-site report pipeline (Notices vs. news) |
| 16 | `Notice`/`csv_extra` rules: elements MUST already be strings; the site name comes from the `SiteContext` | the anonymous `sequence item N: expected str`; a producer/site mismatch | Per-site report pipeline (Notices vs. news) |
| 17 | `gate_disabled_sections()` runs **before** substitution; the DEFER two-pass order | a disabled feature's secrets being required to exist | Plugin / check module system (config substitutions) |
| 18 | Hook DAG: the five fatal conditions; dotted events MUST declare empty `consumes`/`produces` | silent overwrite of a contract key (PD#1) | Plugin / check module system (hooks) |
| 19 | The still-hardcoded-U-M inventory, and that the non-U-M golden does **not** assert "no umich.edu anywhere" | new leakage shipping green | Testing (reusable-path) |
| 20 | Terminus does not work with PHP 8.4 | a dead toolchain | Required runtime credentials / external tools |
| 21 | The B57 send block stays in `main()`: accumulator writes sit between `send_message()` and `quit()` | the Ctrl-C-during-`quit()` duplicate-email window | Per-site report pipeline |
| 22 | A site's notices are appended to the run accumulator **before** the SMTP send | notices never reaching `-notices.csv` for an emailed site | Database (site-loop end) |

---

## Per-document dispositions (every mechanizable claim from the Step 3 run)

Rows are the raw `claim_check.py` output with a **disposition** column appended. The `detail`
column is the tool's own reason string.

### CLAUDE.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `psh.cli.main` | SYMBOL | PASS |  | keep-verified |
| `psh/cli.py` | PATH | PASS |  | keep-verified |
| `psh/` | PATH | PASS |  | keep-verified |
| `pantheon-sitehealth-emails.toml` | PATH | PASS |  | keep-verified |
| `fqdns.json` | PATH | PASS |  | keep-verified |
| `plugin/env/get_env.py` | PATH | PASS |  | keep-verified |
| `plugin/aws/__init__.py` | PATH | PASS |  | keep-verified |
| `docs/env-and-smtp-configuration.md` | PATH | PASS |  | keep-verified |
| `docs/email-configuration.md` | PATH | PASS |  | keep-verified |
| `check/` | PATH | PASS |  | keep-verified |
| `plugin/` | PATH | PASS |  | keep-verified |
| `psh/_legacy.py` | PATH | FAIL | path does not exist | fix -> `psh/cli.py` (orchestrator relocated at I14a; the `psh/_legacy.py` re-import/back-import shim was DELETED - modules are imported directly) |
| `development/2026-07-17-modularization-campaign/` | PATH | PASS |  | keep-verified |
| `CAMPAIGN.md` | PATH | PASS |  | keep-verified |
| `LEDGER.md` | PATH | PASS |  | keep-verified |
| `BLOCKMAP.md` | PATH | PASS |  | keep-verified |
| `CLAUDE.md` | PATH | PASS |  | keep-verified |
| `psh/gateway.py` | PATH | PASS |  | keep-verified |
| `psh/configuration.py` | PATH | PASS |  | keep-verified |
| `sc.umich_enabled` | SC | PASS |  | keep-verified |
| `sc.cloudflare_enabled` | SC | PASS |  | keep-verified |
| `psh/notice.py` | PATH | PASS |  | keep-verified |
| `psh/modules.py` | PATH | PASS |  | keep-verified |
| `script_context.py` | PATH | PASS |  | keep-verified |
| `sc.hooks` | SC | PASS |  | keep-verified |
| `psh/db.py` | PATH | PASS |  | keep-verified |
| `sc.db_engine_args` | SC | PASS |  | keep-verified |
| `psh/lifecycle.py` | PATH | PASS |  | keep-verified |
| `sc.run_state.db_reconnects_by_site` | SC | PASS |  | keep-verified |
| `sc.run_state` | SC | PASS |  | keep-verified |
| `psh/traffic.py` | PATH | PASS |  | keep-verified |
| `psh/plans.py` | PATH | PASS |  | keep-verified |
| `psh.dns_classify.stuff_dns_contract` | SYMBOL | PASS |  | keep-verified |
| `psh/gather.py` | PATH | PASS |  | keep-verified |
| `sc.check_wordpress_plugin` | SC | PASS |  | keep-verified |
| `sc.check_drupal_module` | SC | PASS |  | keep-verified |
| `check/wordpress/` | PATH | PASS |  | keep-verified |
| `check/drupal/` | PATH | PASS |  | keep-verified |
| `check/umich/` | PATH | PASS |  | keep-verified |
| `psh/render.py` | PATH | PASS |  | keep-verified |
| `psh/charts.py` | PATH | PASS |  | keep-verified |
| `tests/integration/test_charts.py` | PATH | PASS |  | keep-verified |
| `email_template.html` | PATH | PASS |  | keep-verified |
| `psh/mail.py` | PATH | PASS |  | keep-verified |
| `psh.db` | SYMBOL | PASS |  | keep-verified |
| `psh._legacy` | SYMBOL | FAIL | psh/__init__.py defines no '_legacy' | fix -> `psh.cli` (`psh/_legacy.py` deleted at I14a) |
| `psh/dns_classify.py` | PATH | PASS |  | keep-verified |
| `check/dns/` | PATH | PASS |  | keep-verified |
| `sc.options` | SC | PASS |  | keep-verified |
| `sc.config` | SC | PASS |  | keep-verified |
| `sc.plugin` | SC | PASS |  | keep-verified |
| `sc.check` | SC | PASS |  | keep-verified |
| `sc.news` | SC | PASS |  | keep-verified |
| `sc.console` | SC | PASS |  | keep-verified |
| `sc.substitutions` | SC | PASS |  | keep-verified |
| `sc.Notice` | SC | PASS |  | keep-verified |
| `sc.Severity` | SC | PASS |  | keep-verified |
| `_legacy.py` | PATH | PROSE | not resolvable as a repo path -- verify by hand | PROSE - verify by hand |
| `sc.text_maker` | SC | FAIL | sc has no 'text_maker' | allowed (see claims-allow.txt) |
| `__init__.py` | PATH | PASS |  | keep-verified |
| `plugin/__init__.py` | PATH | PASS |  | keep-verified |
| `check/__init__.py` | PATH | PASS |  | keep-verified |
| `plugin.aws` | SYMBOL | PASS |  | keep-verified |
| `plugin.cloudflare` | SYMBOL | PASS |  | keep-verified |
| `plugin.env` | SYMBOL | PASS |  | keep-verified |
| `plugin.umich` | SYMBOL | PASS |  | keep-verified |
| `check.addon_updates` | SYMBOL | PASS |  | keep-verified |
| `check.cloudflare` | SYMBOL | PASS |  | keep-verified |
| `check.dns` | SYMBOL | PASS |  | keep-verified |
| `check.drupal` | SYMBOL | PASS |  | keep-verified |
| `check.pantheon` | SYMBOL | PASS |  | keep-verified |
| `check.pantheon_cdn_change` | SYMBOL | PASS |  | keep-verified |
| `check.umich` | SYMBOL | PASS |  | keep-verified |
| `check.wordpress` | SYMBOL | PASS |  | keep-verified |
| `aws/get_secret.py` | PATH | PASS |  | keep-verified |
| `cloudflare/ips.py` | PATH | PASS |  | keep-verified |
| `env/get_env.py` | PATH | PASS |  | keep-verified |
| `umich/portal.py` | PATH | PASS |  | keep-verified |
| `check/umich/sitelens.py` | PATH | PASS |  | keep-verified |
| `sc.PHASES` | SC | PASS |  | keep-verified |
| `psh.modules.validate_hooks` | SYMBOL | PASS |  | keep-verified |
| `check.drupal.multisite` | SYMBOL | PASS |  | keep-verified |
| `tests/integration/test_hook_dag.py` | PATH | PASS |  | keep-verified |
| `check/pantheon` | PATH | PASS |  | keep-verified |
| `check/wordpress` | PATH | PASS |  | keep-verified |
| `sc.DEFER` | SC | PASS |  | keep-verified |
| `sc.ConfigSubstitutionError` | SC | PASS |  | keep-verified |
| `plugin.env.get_env` | SYMBOL | PASS |  | keep-verified |
| `plugin.aws.get_secret` | SYMBOL | PASS |  | keep-verified |
| `cloudflare_cms.py` | PATH | PASS |  | keep-verified |
| `oidc_login.py` | PATH | PASS |  | keep-verified |
| `hummingbird.py` | PATH | PASS |  | keep-verified |
| `drupal_ua.py` | PATH | PASS |  | keep-verified |
| `annual_billing.py` | PATH | PASS |  | keep-verified |
| `sc.contract_year_end(end_date)` | SC | PASS |  | keep-verified |
| `check/cloudflare/` | PATH | PASS |  | keep-verified |
| `docs/cloudflare-cachecheck.md` | PATH | PASS |  | keep-verified |
| `notices.py` | PATH | PASS |  | keep-verified |
| `hook.py` | PATH | PASS |  | keep-verified |
| `check/pantheon/` | PATH | PASS |  | keep-verified |
| `frozen.py` | PATH | PASS |  | keep-verified |
| `live_env.py` | PATH | PASS |  | keep-verified |
| `updates.py` | PATH | PASS |  | keep-verified |
| `sc.terminus` | SC | PASS |  | keep-verified |
| `php_eol.py` | PATH | PASS |  | keep-verified |
| `papc.py` | PATH | PASS |  | keep-verified |
| `sessions.py` | PATH | PASS |  | keep-verified |
| `ocp.py` | PATH | PASS |  | keep-verified |
| `sc.wp_eval` | SC | PASS |  | keep-verified |
| `favicon.py` | PATH | PASS |  | keep-verified |
| `sc.wp_error` | SC | PASS |  | keep-verified |
| `multisite.py` | PATH | PASS |  | keep-verified |
| `sc.drush_php_script` | SC | PASS |  | keep-verified |
| `d7_eol.py` | PATH | PASS |  | keep-verified |
| `check/addon_updates/` | PATH | PASS |  | keep-verified |
| `table.py` | PATH | PASS |  | keep-verified |
| `check/pantheon_cdn_change/` | PATH | PASS |  | keep-verified |
| `docs/pantheon-cdn-change.md` | PATH | PASS |  | keep-verified |
| `sc.escape_url` | SC | PASS |  | keep-verified |
| `sc.fqdn_re` | SC | PASS |  | keep-verified |
| `sc.drush_error` | SC | PASS |  | keep-verified |
| `sc.contract_year_end` | SC | PASS |  | keep-verified |
| `sc.registry` | SC | PASS |  | keep-verified |
| `check/cloudflare/httpseam.py` | PATH | PASS |  | keep-verified |
| `egress.py` | PATH | PASS |  | keep-verified |
| `psh.modules.CONTRACT` | SYMBOL | PASS |  | keep-verified |
| `tests/unit/test_contract_registry.py` | PATH | PASS |  | keep-verified |
| `psh.dns_classify.classify_domains` | SYMBOL | PASS |  | keep-verified |
| `check.addon_updates.table` | SYMBOL | PASS |  | keep-verified |
| `check.wordpress.ocp` | SYMBOL | PASS |  | keep-verified |
| `check.wordpress.favicon` | SYMBOL | PASS |  | keep-verified |
| `check.umich.drupal_ua` | SYMBOL | PASS |  | keep-verified |
| `check.umich.annual_billing` | SYMBOL | PASS |  | keep-verified |
| `sc.SiteContext` | SC | PASS |  | keep-verified |
| `sc.add_notice` | SC | FAIL | sc has no 'add_notice' | allowed (see claims-allow.txt) |
| `psh.notice.registry` | SYMBOL | PASS |  | keep-verified |
| `tests/integration/test_notice_roster.py` | PATH | PASS |  | keep-verified |
| `check/pantheon_cdn_change/notices.py` | PATH | PASS |  | keep-verified |
| `psh.notice` | SYMBOL | PASS |  | keep-verified |
| `tests/conftest.py` | PATH | PASS |  | keep-verified |
| `sc.smtp_username` | SC | PASS |  | keep-verified |
| `plugin/cloudflare/client.py` | PATH | PASS |  | keep-verified |
| `sc.plugin_context['plugin.cloudflare']['client']` | SC | PASS |  | keep-verified |
| `ips.py` | PATH | PASS |  | keep-verified |
| `fqdns.py` | PATH | PASS |  | keep-verified |
| `sc.plugin_context['plugin.cloudflare']['get_client']` | SC | PASS |  | keep-verified |
| `plugin/cloudflare/fqdns.py` | PATH | PASS |  | keep-verified |
| `sc.plugin_context['plugin.cloudflare']['proxied_fqdns']` | SC | PASS |  | keep-verified |
| `check/pantheon_cdn_change` | PATH | PASS |  | keep-verified |
| `docs/cloudflare-fqdns.md` | PATH | PASS |  | keep-verified |
| `development/2026-07-08-cloudflare-cache-configuration/` | PATH | PASS |  | keep-verified |
| `docs/resuming-interrupted-runs.md` | PATH | PASS |  | keep-verified |
| `psh.render.render_report` | SYMBOL | PASS |  | keep-verified |
| `email_template.txt` | PATH | PASS |  | keep-verified |
| `inline-styles.php` | PATH | PASS |  | keep-verified |
| `vendor/` | PATH | PASS |  | keep-verified |
| `psh.charts.build_chart` | SYMBOL | PASS |  | keep-verified |
| `psh.mail.assemble_message` | SYMBOL | PASS |  | keep-verified |
| `plugin/umich/portal.py` | PATH | PASS |  | keep-verified |
| `monthly-report.txt` | PATH | PASS |  | keep-verified |
| `sc.run_state.db_reconnect_failures_by_site` | SC | PASS |  | keep-verified |
| `tests/unit/test_run_state.py` | PATH | PASS |  | keep-verified |
| `sc.console.print` | SC | PASS |  | keep-verified |
| `tests/integration/test_finish_run.py` | PATH | PASS |  | keep-verified |
| `tests/integration/test_abort_run.py` | PATH | PASS |  | keep-verified |
| `tests/e2e/test_abort_e2e.py` | PATH | PASS |  | keep-verified |
| `development/2026-07-13-db-connection-resilience/SPEC.md` | PATH | PASS |  | keep-verified |
| `pantheon-sitehealth-emails-config/pantheon-sitehealth-emails.toml` | PATH | PASS |  | keep-verified |
| `sample-pantheon-sitehealth-emails.toml` | PATH | PASS |  | keep-verified |
| `pantheon-sitehealth-emails.py` | PATH | PASS |  | keep-verified |
| `build/` | PATH | PASS |  | keep-verified |
| `README.md` | PATH | PASS |  | keep-verified |
| `pyproject.toml` | PATH | PASS |  | keep-verified |
| `ruff-broad.toml` | PATH | PROSE | not resolvable as a repo path -- verify by hand | PROSE - verify by hand |
| `prompts/directives.md` | PATH | PASS |  | keep-verified |
| `development/finalize-session.py` | PATH | PASS |  | keep-verified |
| `tests/` | PATH | PASS |  | keep-verified |
| `development/2026-07-04-test-harness/SPEC.md` | PATH | PASS |  | keep-verified |
| `tests/tools/record.py` | PATH | PASS |  | keep-verified |
| `prompts/implementation-standards.md` | PATH | PASS |  | keep-verified |
| `prompts/add-tests-for-change.prompt.md` | PATH | PASS |  | keep-verified |
| `psh.cli` | SYMBOL | PASS |  | keep-verified |
| `tests/integration/test_check_sitelens.py` | PATH | PASS |  | keep-verified |
| `test_plugin_aws.py` | PATH | PASS |  | keep-verified |
| `tests/helpers/checkload.py` | PATH | PASS |  | keep-verified |
| `psh.gateway.run_terminus` | SYMBOL | PASS |  | keep-verified |
| `psh.run_terminus` | SYMBOL | PASS | re-export | keep-verified |
| `psh.time.sleep` | SYMBOL | PASS | re-export | keep-verified |
| `psh.subprocess.Popen` | SYMBOL | PASS | re-export | keep-verified |
| `psh.gather.run_terminus` | SYMBOL | PASS |  | keep-verified |
| `tests/integration/test_gather_drupal.py` | PATH | PASS |  | keep-verified |
| `tests/shims/terminus` | PATH | PASS |  | keep-verified |
| `psh.mail.SMTP_SSL` | SYMBOL | PASS |  | keep-verified |
| `psh.SMTP_SSL` | SYMBOL | FAIL | psh/__init__.py defines no 'SMTP_SSL' | allowed (see claims-allow.txt) |
| `test_email_config.py` | PATH | PASS |  | keep-verified |
| `psh.lifecycle` | SYMBOL | PASS |  | keep-verified |
| `psh.lifecycle.finish_run` | SYMBOL | PASS |  | keep-verified |
| `psh.finish_run` | SYMBOL | PASS | re-export | keep-verified |
| `tests/integration/test_db_credentials.py` | PATH | PASS |  | keep-verified |
| `psh.overage_blocks` | SYMBOL | PASS | re-export | keep-verified |
| `psh.contract_year_end` | SYMBOL | PASS | re-export | keep-verified |
| `psh.plan_costs` | SYMBOL | PASS | re-export | keep-verified |
| `psh.build_plan_over_time` | SYMBOL | PASS | re-export | keep-verified |
| `psh.estimate_month_visits` | SYMBOL | PASS | re-export | keep-verified |
| `psh.build_traffic_table_rows` | SYMBOL | PASS | re-export | keep-verified |
| `tests/unit/test_traffic_aggregation.py` | PATH | PASS |  | keep-verified |
| `tests/unit/test_dns_classify.py` | PATH | PASS |  | keep-verified |
| `psh.dns_classify.MalformedNameError` | SYMBOL | PASS |  | keep-verified |
| `tests/unit/test_dns_notices.py` | PATH | PASS |  | keep-verified |
| `tests/integration/test_check_dns.py` | PATH | PASS |  | keep-verified |
| `tests/integration/test_dns_notice_render.py` | PATH | PASS |  | keep-verified |
| `tests/unit/test_pantheon_cdn_change_chain.py` | PATH | PASS |  | keep-verified |
| `tests/unit/test_pantheon_cdn_change_pantheon.py` | PATH | PASS |  | keep-verified |
| `tests/unit/test_pantheon_cdn_change_detect.py` | PATH | PASS |  | keep-verified |
| `tests/unit/test_pantheon_cdn_change_notices.py` | PATH | PASS |  | keep-verified |
| `tests/integration/test_check_pantheon_cdn_change.py` | PATH | PASS |  | keep-verified |
| `tests/integration/test_pantheon_cdn_change_notice_render.py` | PATH | PASS |  | keep-verified |
| `psh.dns_classify.resolve` | SYMBOL | PASS |  | keep-verified |
| `tests/unit/test_php_eol_notice.py` | PATH | PASS |  | keep-verified |
| `check/pantheon/php_eol.py` | PATH | PASS |  | keep-verified |
| `tests/integration/test_check_pantheon_init.py` | PATH | PASS |  | keep-verified |
| `tests/integration/test_check_pantheon.py` | PATH | PASS |  | keep-verified |
| `tests/integration/test_pantheon_notice_render.py` | PATH | PASS |  | keep-verified |
| `tests/integration/test_gather_wordpress.py` | PATH | PASS |  | keep-verified |
| `psh.gather` | SYMBOL | PASS |  | keep-verified |
| `tests/integration/test_check_wordpress_init.py` | PATH | PASS |  | keep-verified |
| `tests/integration/test_check_wordpress.py` | PATH | PASS |  | keep-verified |
| `tests/integration/test_check_umich_wp.py` | PATH | PASS |  | keep-verified |
| `tests/integration/test_wordpress_notice_render.py` | PATH | PASS |  | keep-verified |
| `tests/integration/test_umich_wp_notice_render.py` | PATH | PASS |  | keep-verified |
| `psh.gather.gather_drupal` | SYMBOL | PASS |  | keep-verified |
| `test_check_drupal_init.py` | PATH | PASS |  | keep-verified |
| `test_check_drupal.py` | PATH | PASS |  | keep-verified |
| `test_check_addon_updates_init.py` | PATH | PASS |  | keep-verified |
| `test_check_addon_updates.py` | PATH | PASS |  | keep-verified |
| `test_check_umich_drupal_ua.py` | PATH | PASS |  | keep-verified |
| `test_drupal_notice_render.py` | PATH | PASS |  | keep-verified |
| `test_addon_updates_notice_render.py` | PATH | PASS |  | keep-verified |
| `test_umich_drupal_ua_notice_render.py` | PATH | PASS |  | keep-verified |
| `test_smell_notice_render.py` | PATH | PASS |  | keep-verified |
| `tests/unit/test_no_primary_domain_notice.py` | PATH | PASS |  | keep-verified |
| `tests/unit/test_smell_notices.py` | PATH | PASS |  | keep-verified |
| `test_hook_dag.py` | PATH | PASS |  | keep-verified |
| `tests/integration/test_render_report.py` | PATH | PASS |  | keep-verified |
| `tests/integration/test_mail_recipients.py` | PATH | PASS |  | keep-verified |
| `psh.mail.resolve_recipients` | SYMBOL | PASS |  | keep-verified |
| `tests/integration/test_check_umich_annual_billing.py` | PATH | PASS |  | keep-verified |
| `checkload.py` | PATH | PASS |  | keep-verified |
| `tests/integration/test_sort_notices_and_subject.py` | PATH | PASS |  | keep-verified |
| `tests/unit/test_annual_billing_notices.py` | PATH | PASS |  | keep-verified |
| `test_contract_registry.py` | PATH | PASS |  | keep-verified |
| `check/umich` | PATH | PASS |  | keep-verified |
| `tests/helpers/` | PATH | PASS |  | keep-verified |
| `dnsfake.py` | PATH | PASS |  | keep-verified |
| `tests/shims/pyshim/` | PATH | PASS |  | keep-verified |
| `site.py` | PATH | PROSE | not resolvable as a repo path -- verify by hand | PROSE - verify by hand |
| `sitecustomize.py` | PATH | PASS |  | keep-verified |
| `dnsshim.py` | PATH | PASS |  | keep-verified |
| `dbshim.py` | PATH | PASS |  | keep-verified |
| `tests/integration/test_shim_composability.py` | PATH | PASS |  | keep-verified |
| `tests/fixtures/config/minimal.toml` | PATH | PASS |  | keep-verified |
| `tests/fixtures/terminus/` | PATH | PASS |  | keep-verified |
| `tests/fixtures/terminus-drupal/` | PATH | PASS |  | keep-verified |
| `test_golden_nonumich.py` | PATH | PASS |  | keep-verified |
| `minimal-nonumich.toml` | PATH | PASS |  | keep-verified |
| `tests/e2e/test_golden_cdn_change.py` | PATH | PASS |  | keep-verified |
| `tests/fixtures/terminus-cdnchange/` | PATH | PASS |  | keep-verified |
| `tests/shims/pyshim` | PATH | PASS |  | keep-verified |
| `minimal.toml` | PATH | PASS |  | keep-verified |
| `tests/integration/__snapshots__/test_pantheon_cdn_change_notice_render.ambr` | PATH | PASS |  | keep-verified |
| `terminus/` | PATH | PASS |  | keep-verified |
| `terminus-drupal/` | PATH | PROSE | not resolvable as a repo path -- verify by hand | PROSE - verify by hand |
| `terminus-cdnchange/` | PATH | PROSE | not resolvable as a repo path -- verify by hand | PROSE - verify by hand |
| `test_eml_headers.py` | PATH | PASS |  | keep-verified |
| `tests/e2e/test_recommendation_e2e.py` | PATH | PASS |  | keep-verified |
| `tests/vendor/axe.min.js` | PATH | PASS |  | keep-verified |
| `node/4705` | PATH | PROSE | not resolvable as a repo path -- verify by hand | PROSE - verify by hand |
| `check/umich/annual_billing.py` | PATH | PASS |  | keep-verified |
| `check/umich/drupal_ua.py` | PATH | PASS |  | keep-verified |
| `test_check_cloudflare_init.py` | PATH | PASS |  | keep-verified |
| `test_cachecheck_headers.py` | PATH | PASS |  | keep-verified |
| `test_cachecheck_pages.py` | PATH | PASS |  | keep-verified |
| `test_cachecheck_consolidation.py` | PATH | PASS |  | keep-verified |
| `test_hooks_phases.py` | PATH | PASS |  | keep-verified |
| `test_check_cloudflare_egress.py` | PATH | PASS |  | keep-verified |
| `test_check_cloudflare_cache.py` | PATH | PASS |  | keep-verified |
| `test_check_umich_cloudflare_cms.py` | PATH | PASS |  | keep-verified |
| `test_cachecheck_notice_render.py` | PATH | PASS |  | keep-verified |
| `prompts/` | PATH | PASS |  | keep-verified |
| `new-feature-standards.md` | PATH | PASS |  | keep-verified |
| `implementation-standards.md` | PATH | PASS |  | keep-verified |
| `debugging-standards.md` | PATH | PASS |  | keep-verified |
| `adversarial-review.md` | PATH | PASS |  | keep-verified |
| `add-tests-for-change.prompt.md` | PATH | PASS |  | keep-verified |
| `refresh-fixtures.prompt.md` | PATH | PASS |  | keep-verified |
| `update-claude-md.md` | PATH | PASS |  | keep-verified |
| `development/2026-07-04-test-harness/` | PATH | PASS |  | keep-verified |
| `docs/agents/` | PATH | PASS |  | keep-verified |
| `psh-reviewer.md` | PATH | PASS |  | keep-verified |
| `development/` | PATH | PASS |  | keep-verified |
| `prompts/adversarial-review.md` | PATH | PASS |  | keep-verified |
| `prompts/new-feature-standards.md` | PATH | PASS |  | keep-verified |
| `docs/agents/issue-tracker.md` | PATH | PASS |  | keep-verified |
| `docs/agents/triage-labels.md` | PATH | PASS |  | keep-verified |
| `CONTEXT.md` | PATH | PASS |  | keep-verified |
| `docs/adr/` | PATH | PROSE | not resolvable as a repo path -- verify by hand | PROSE - verify by hand |
| `docs/agents/domain.md` | PATH | PASS |  | keep-verified |
| `SPEC.md` | PATH | PASS |  | keep-verified |
| `transcript.md` | PATH | PASS |  | keep-verified |
| `statistics.md` | PATH | PASS |  | keep-verified |
| `docs/` | PATH | PASS |  | keep-verified |
| `development/README.md` | PATH | PASS |  | keep-verified |
| `devcontainer.json` | PATH | PASS |  | keep-verified |
| `container-start.sh` | PATH | PASS |  | keep-verified |
| `DISABLED_init-firewall.sh` | PATH | PASS |  | keep-verified |
| `622 raw` | COUNT | PASS |  | keep-verified |

### README.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `pantheon-sitehealth-emails.toml` | PATH | PASS |  | keep-verified |
| `docs/email-configuration.md` | PATH | PASS |  | keep-verified |
| `sample-pantheon-sitehealth-emails.toml` | PATH | PASS |  | keep-verified |
| `docs/env-and-smtp-configuration.md` | PATH | PASS |  | keep-verified |
| `fqdns.json` | PATH | PASS |  | keep-verified |
| `tests/` | PATH | PASS |  | keep-verified |
| `tests/README.md` | PATH | PASS |  | keep-verified |
| `development/2026-07-17-modularization-campaign/CAMPAIGN.md` | PATH | PASS |  | keep-verified |
| `LEDGER.md` | PATH | PASS |  | keep-verified |
| `check.wordpress.ocp` | SYMBOL | PASS |  | keep-verified |
| `check.umich.drupal_ua` | SYMBOL | PASS |  | keep-verified |
| `check/addon_updates/` | PATH | PASS |  | keep-verified |
| `pyproject.toml` | PATH | PASS |  | keep-verified |
| `prompts/directives.md` | PATH | PASS |  | keep-verified |
| `ruff-broad.toml` | PATH | PROSE | not resolvable as a repo path -- verify by hand | PROSE - verify by hand |
| `prompts/implementation-standards.md` | PATH | PASS |  | keep-verified |
| `psh/` | PATH | PASS |  | keep-verified |
| `_legacy.py` | PATH | PROSE | not resolvable as a repo path -- verify by hand | PROSE - verify by hand |
| `check/` | PATH | PASS |  | keep-verified |
| `plugin/` | PATH | PASS |  | keep-verified |
| `psh/_legacy.py` | PATH | FAIL | path does not exist | fix -> `psh/cli.py` (orchestrator relocated at I14a; the `psh/_legacy.py` re-import/back-import shim was DELETED - modules are imported directly) |
| `script_context.py` | PATH | PASS |  | keep-verified |
| `dns_classify.py` | PATH | PASS |  | keep-verified |
| `sc.options` | SC | PASS |  | keep-verified |
| `pantheon-sitehealth-emails.py` | PATH | PASS |  | keep-verified |
| `sc.escape_url` | SC | PASS |  | keep-verified |
| `sc.check_wordpress_plugin` | SC | PASS |  | keep-verified |
| `sc.terminus` | SC | PASS |  | keep-verified |
| `sc.wp_eval` | SC | PASS |  | keep-verified |
| `psh.cli` | SYMBOL | PASS |  | keep-verified |
| `psh.overage_blocks` | SYMBOL | PASS | re-export | keep-verified |
| `psh.plan_costs` | SYMBOL | PASS | re-export | keep-verified |
| `psh.build_chart` | SYMBOL | PASS | re-export | keep-verified |
| `psh.plans.overage_blocks` | SYMBOL | PASS |  | keep-verified |
| `psh.charts.build_chart` | SYMBOL | PASS |  | keep-verified |
| `development/2026-07-20-mod-I7-plans/SPEC.md` | PATH | PASS |  | keep-verified |

### CONTEXT.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `CLAUDE.md` | PATH | PASS |  | keep-verified |

### tests/README.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `sc.options` | SC | PASS |  | keep-verified |
| `psh.gateway` | SYMBOL | PASS |  | keep-verified |
| `psh.run_terminus` | SYMBOL | PASS | re-export | keep-verified |
| `psh.overage_blocks` | SYMBOL | PASS | re-export | keep-verified |
| `psh.contract_year_end` | SYMBOL | PASS | re-export | keep-verified |
| `psh.estimate_month_visits` | SYMBOL | PASS | re-export | keep-verified |
| `psh.plan_costs` | SYMBOL | PASS | re-export | keep-verified |
| `unit/` | PATH | PROSE | not resolvable as a repo path -- verify by hand | PROSE - verify by hand |
| `minimal.toml` | PATH | PASS |  | keep-verified |
| `fixtures/terminus-drupal/` | PATH | PROSE | not resolvable as a repo path -- verify by hand | PROSE - verify by hand |

### docs/aws-credentials.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `aws-policy.json` | PATH | PROSE | not resolvable as a repo path -- verify by hand | PROSE - verify by hand |
| `aws/secretsmanager` | PATH | PROSE | not resolvable as a repo path -- verify by hand | PROSE - verify by hand |

### docs/awscli-login.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|

### docs/cloudflare-cachecheck.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `security.txt` | PATH | PROSE | not resolvable as a repo path -- verify by hand | PROSE - verify by hand |
| `check/cloudflare/headers.py` | PATH | PASS |  | keep-verified |

### docs/cloudflare-fqdns.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `fqdns.json` | PATH | PASS |  | keep-verified |

### docs/email-configuration.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `pantheon-sitehealth-emails.toml` | PATH | PASS |  | keep-verified |
| `env-and-smtp-configuration.md` | PATH | PASS |  | keep-verified |

### docs/env-and-smtp-configuration.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `pantheon-sitehealth-emails.toml` | PATH | PASS |  | keep-verified |
| `email-configuration.md` | PATH | PASS |  | keep-verified |

### docs/pantheon-cdn-change.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `check/pantheon_cdn_change/` | PATH | PASS |  | keep-verified |
| `fqdns.json` | PATH | PASS |  | keep-verified |
| `check/pantheon_cdn_change/chain.py` | PATH | PASS |  | keep-verified |
| `plugin/cloudflare/fqdns.py` | PATH | PASS |  | keep-verified |
| `sc.cloudflare_enabled` | SC | PASS |  | keep-verified |
| `check/pantheon_cdn_change/pantheon.py` | PATH | PASS |  | keep-verified |
| `check/pantheon_cdn_change/hook.py` | PATH | PASS |  | keep-verified |
| `sc.umich_enabled` | SC | PASS |  | keep-verified |
| `check/pantheon_cdn_change/notices.py` | PATH | PASS |  | keep-verified |
| `psh.dns_classify.MalformedNameError` | SYMBOL | PASS |  | keep-verified |
| `psh.dns_classify.resolve` | SYMBOL | PASS |  | keep-verified |
| `sc.terminus` | SC | PASS |  | keep-verified |
| `sc.fqdn_re` | SC | PASS |  | keep-verified |
| `tests/helpers/` | PATH | PASS |  | keep-verified |
| `dnsfake.py` | PATH | PASS |  | keep-verified |
| `checkload.py` | PATH | PASS |  | keep-verified |
| `tests/shims/pyshim/dnsshim.py` | PATH | PASS |  | keep-verified |

### docs/resuming-interrupted-runs.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `run.json` | PATH | PROSE | not resolvable as a repo path -- verify by hand | PROSE - verify by hand |
| `CLAUDE.md` | PATH | PASS |  | keep-verified |
| `results.json` | PATH | PROSE | not resolvable as a repo path -- verify by hand | PROSE - verify by hand |
| `monthly-report.txt` | PATH | PASS |  | keep-verified |

### prompts/add-tests-for-change.prompt.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `prompts/implementation-standards.md` | PATH | PASS |  | keep-verified |
| `tests/` | PATH | PASS |  | keep-verified |
| `tests/README.md` | PATH | PASS |  | keep-verified |
| `development/2026-07-04-test-harness/SPEC.md` | PATH | PASS |  | keep-verified |
| `tests/unit/` | PATH | PASS |  | keep-verified |
| `tests/integration/` | PATH | PASS |  | keep-verified |

### prompts/adversarial-review.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `prompts/directives.md` | PATH | PASS |  | keep-verified |
| `prompts/debugging-standards.md` | PATH | PASS |  | keep-verified |

### prompts/debugging-standards.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `new-feature-standards.md` | PATH | PASS |  | keep-verified |
| `prompts/adversarial-review.md` | PATH | PASS |  | keep-verified |
| `CLAUDE.md` | PATH | PASS |  | keep-verified |
| `docs/agents/domain.md` | PATH | PASS |  | keep-verified |
| `psh.dns_classify.resolve` | SYMBOL | PASS |  | keep-verified |
| `check/cloudflare/httpseam.py` | PATH | PASS |  | keep-verified |
| `tests/shims/pyshim/` | PATH | PASS |  | keep-verified |
| `sitecustomize.py` | PATH | PASS |  | keep-verified |
| `sc.console` | SC | PASS |  | keep-verified |
| `tests/integration/test_finish_run.py` | PATH | PASS |  | keep-verified |
| `test_abort_run.py` | PATH | PASS |  | keep-verified |
| `tests/e2e/test_abort_e2e.py` | PATH | PASS |  | keep-verified |
| `prompts/update-claude-md.md` | PATH | PASS |  | keep-verified |
| `development/` | PATH | PASS |  | keep-verified |

### prompts/directives.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `prompts/` | PATH | PASS |  | keep-verified |
| `CONTEXT.md` | PATH | PASS |  | keep-verified |
| `CLAUDE.md` | PATH | PASS |  | keep-verified |
| `docs/agents/domain.md` | PATH | PASS |  | keep-verified |
| `sitecustomize.py` | PATH | PASS |  | keep-verified |
| `prompts/implementation-standards.md` | PATH | PASS |  | keep-verified |
| `psh.dns_classify.resolve` | SYMBOL | PASS |  | keep-verified |

### prompts/implementation-standards.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `prompts/directives.md` | PATH | PASS |  | keep-verified |
| `prompts/adversarial-review.md` | PATH | PASS |  | keep-verified |
| `CLAUDE.md` | PATH | PASS |  | keep-verified |
| `README.md` | PATH | PASS |  | keep-verified |
| `sc.PHASES` | SC | PASS |  | keep-verified |
| `tests/tools/record.py` | PATH | PASS |  | keep-verified |
| `prompts/debugging-standards.md` | PATH | PASS |  | keep-verified |
| `plugin/` | PATH | PASS |  | keep-verified |
| `check/` | PATH | PASS |  | keep-verified |

### prompts/new-feature-standards.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `prompts/directives.md` | PATH | PASS |  | keep-verified |
| `development/` | PATH | PASS |  | keep-verified |
| `docs/superpowers` | PATH | PROSE | not resolvable as a repo path -- verify by hand | PROSE - verify by hand |
| `CLAUDE.md` | PATH | PASS |  | keep-verified |
| `plugin/` | PATH | PASS |  | keep-verified |
| `check/` | PATH | PASS |  | keep-verified |
| `sc.PHASES` | SC | PASS |  | keep-verified |
| `tests/` | PATH | PASS |  | keep-verified |

### prompts/refresh-fixtures.prompt.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `tests/tools/record.py` | PATH | PASS |  | keep-verified |

### prompts/update-claude-md.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|

### /home/node/.claude/projects/-workspace/memory/MEMORY.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|

### /home/node/.claude/projects/-workspace/memory/askuserquestion-stepped-away.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|

### /home/node/.claude/projects/-workspace/memory/browser-devtools-setup.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|

### /home/node/.claude/projects/-workspace/memory/cloudflare-origin-cache-control.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `check/cloudflare/` | PATH | PASS |  | keep-verified |

### /home/node/.claude/projects/-workspace/memory/codegraph-blind-to-main-script.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `check/` | PATH | PASS |  | keep-verified |
| `plugin/` | PATH | PASS |  | keep-verified |
| `tests/` | PATH | PASS |  | keep-verified |
| `script_context.py` | PATH | PASS |  | keep-verified |
| `pantheon-sitehealth-emails.py` | PATH | PASS |  | keep-verified |
| `codegraph.json` | PATH | PROSE | not resolvable as a repo path -- verify by hand | PROSE - verify by hand |
| `psh/cli.py` | PATH | PASS |  | keep-verified |
| `psh/_legacy.py` | PATH | FAIL | path does not exist | fix -> `psh/cli.py` (orchestrator relocated at I14a; the `psh/_legacy.py` re-import/back-import shim was DELETED - modules are imported directly) |

### /home/node/.claude/projects/-workspace/memory/config-and-notice-modules.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `psh/configuration.py` | PATH | PASS |  | keep-verified |
| `psh/_legacy.py` | PATH | FAIL | path does not exist | fix -> `psh/cli.py` (orchestrator relocated at I14a; the `psh/_legacy.py` re-import/back-import shim was DELETED - modules are imported directly) |
| `psh.process_config` | SYMBOL | PASS | re-export | keep-verified |
| `sc.umich_enabled` | SC | PASS |  | keep-verified |
| `sc.cloudflare_enabled` | SC | PASS |  | keep-verified |
| `psh/notice.py` | PATH | PASS |  | keep-verified |
| `psh/` | PATH | PASS |  | keep-verified |
| `sc.substitutions` | SC | PASS |  | keep-verified |
| `sc.hooks` | SC | PASS |  | keep-verified |
| `check/dns/notices.py` | PATH | PASS |  | keep-verified |
| `check/` | PATH | PASS |  | keep-verified |
| `tests/integration/test_notice_roster.py` | PATH | PASS |  | keep-verified |
| `psh.notice.registry` | SYMBOL | PASS |  | keep-verified |
| `sc.Notice` | SC | PASS |  | keep-verified |
| `sc.Severity` | SC | PASS |  | keep-verified |
| `sc.registry` | SC | PASS |  | keep-verified |
| `check/pantheon_cdn_change/notices.py` | PATH | PASS |  | keep-verified |
| `psh.notice` | SYMBOL | PASS |  | keep-verified |

### /home/node/.claude/projects/-workspace/memory/db-idle-connection-reaped.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `development/2026-07-13-db-connection-resilience/` | PATH | PASS |  | keep-verified |
| `psh/db.py` | PATH | PASS |  | keep-verified |
| `psh/_legacy.py` | PATH | FAIL | path does not exist | fix -> `psh/cli.py` (orchestrator relocated at I14a; the `psh/_legacy.py` re-import/back-import shim was DELETED - modules are imported directly) |
| `script_context.py` | PATH | PASS |  | keep-verified |
| `sc.db_reconnects_by_site` | SC | FAIL | sc has no 'db_reconnects_by_site' | fix -> `sc.run_state.db_reconnects_by_site` (moved onto RunState at I13; the interim script_context attribute no longer exists) |
| `sc.db_reconnect_failures_by_site` | SC | FAIL | sc has no 'db_reconnect_failures_by_site' | fix -> `sc.run_state.db_reconnect_failures_by_site` (moved onto RunState at I13) |
| `development/2026-07-20-mod-I5-db/SPEC.md` | PATH | PASS |  | keep-verified |
| `psh/lifecycle.py` | PATH | PASS |  | keep-verified |
| `sc.run_state` | SC | PASS |  | keep-verified |
| `tests/unit/test_run_state.py` | PATH | PASS |  | keep-verified |
| `sc.run_state.db_reconnects_by_site` | SC | PASS |  | keep-verified |

### /home/node/.claude/projects/-workspace/memory/dns-modularization.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `feature/modular-dns-checks` | PATH | PROSE | not resolvable as a repo path -- verify by hand | PROSE - verify by hand |
| `docs/superpowers/specs/2026-07-10-modular-dns-checks-design.md` | PATH | FAIL | path does not exist | fix -> `development/2026-07-10-modular-dns-checks/SPEC.md` (repo convention is `development/<slug>/`) |
| `docs/superpowers/plans/2026-07-10-modular-dns-checks.md` | PATH | FAIL | path does not exist | fix -> `development/2026-07-10-modular-dns-checks/PLAN.md` (repo convention is `development/<slug>/`) |
| `dns_classify.py` | PATH | PASS |  | keep-verified |
| `check/dns/` | PATH | PASS |  | keep-verified |
| `check/dns` | PATH | PASS |  | keep-verified |
| `sc.cloudflare_enabled` | SC | PASS |  | keep-verified |
| `sc.umich_enabled` | SC | PASS |  | keep-verified |

### /home/node/.claude/projects/-workspace/memory/e2e-goldens-never-loaded-checks.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `check/` | PATH | PASS |  | keep-verified |
| `plugin/` | PATH | PASS |  | keep-verified |
| `check/umich` | PATH | PASS |  | keep-verified |
| `check/cloudflare` | PATH | PASS |  | keep-verified |
| `check/dns` | PATH | PASS |  | keep-verified |

### /home/node/.claude/projects/-workspace/memory/fix-the-class-not-the-instance.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|

### /home/node/.claude/projects/-workspace/memory/gateway-extraction.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `psh/_legacy.py` | PATH | FAIL | path does not exist | fix -> `psh/cli.py` (orchestrator relocated at I14a; the `psh/_legacy.py` re-import/back-import shim was DELETED - modules are imported directly) |
| `psh/gateway.py` | PATH | PASS |  | keep-verified |
| `psh.gateway.run_terminus` | SYMBOL | PASS |  | keep-verified |
| `psh.run_terminus` | SYMBOL | PASS | re-export | keep-verified |
| `psh.time.sleep` | SYMBOL | PASS | re-export | keep-verified |
| `psh.subprocess.Popen` | SYMBOL | PASS | re-export | keep-verified |
| `psh/gather.py` | PATH | PASS |  | keep-verified |
| `psh.gather.run_terminus` | SYMBOL | PASS |  | keep-verified |
| `tests/integration/test_gather_drupal.py` | PATH | PASS |  | keep-verified |
| `psh/mail.py` | PATH | PASS |  | keep-verified |
| `psh.SMTP_SSL` | SYMBOL | FAIL | psh/__init__.py defines no 'SMTP_SSL' | allowed (see claims-allow.txt) |
| `test_email_config.py` | PATH | PASS |  | keep-verified |
| `psh.smtp_login` | SYMBOL | PASS | re-export | keep-verified |
| `psh/lifecycle.py` | PATH | PASS |  | keep-verified |
| `psh.lifecycle` | SYMBOL | PASS |  | keep-verified |
| `psh.lifecycle.finish_run` | SYMBOL | PASS |  | keep-verified |
| `psh.finish_run` | SYMBOL | PASS | re-export | keep-verified |

### /home/node/.claude/projects/-workspace/memory/git-index-lock-race.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|

### /home/node/.claude/projects/-workspace/memory/hook-phase-ordering-invariant.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `psh.modules.stuff_traffic_contract` | SYMBOL | PASS |  | keep-verified |
| `psh.modules.CONTRACT` | SYMBOL | PASS |  | keep-verified |
| `tests/unit/test_contract_registry.py` | PATH | PASS |  | keep-verified |
| `sc.add_hook` | SC | PASS |  | keep-verified |
| `psh.modules.validate_hooks` | SYMBOL | PASS |  | keep-verified |
| `tests/integration/test_hook_dag.py` | PATH | PASS |  | keep-verified |

### /home/node/.claude/projects/-workspace/memory/modularization-campaign.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `psh/_legacy.py` | PATH | FAIL | path does not exist | fix -> `psh/cli.py` (orchestrator relocated at I14a; the `psh/_legacy.py` re-import/back-import shim was DELETED - modules are imported directly) |
| `ruff-broad.toml` | PATH | PROSE | not resolvable as a repo path -- verify by hand | PROSE - verify by hand |
| `psh/gateway.py` | PATH | PASS |  | keep-verified |
| `psh/configuration.py` | PATH | PASS |  | keep-verified |
| `psh/notice.py` | PATH | PASS |  | keep-verified |
| `psh/modules.py` | PATH | PASS |  | keep-verified |
| `script_context.py` | PATH | PASS |  | keep-verified |
| `psh/db.py` | PATH | PASS |  | keep-verified |
| `_legacy.py` | PATH | PROSE | not resolvable as a repo path -- verify by hand | PROSE - verify by hand |
| `sc.db_reconnects_by_site` | SC | FAIL | sc has no 'db_reconnects_by_site' | fix -> `sc.run_state.db_reconnects_by_site` (moved onto RunState at I13; the interim script_context attribute no longer exists) |
| `sc.db_reconnect_failures_by_site` | SC | FAIL | sc has no 'db_reconnect_failures_by_site' | fix -> `sc.run_state.db_reconnect_failures_by_site` (moved onto RunState at I13) |
| `psh/traffic.py` | PATH | PASS |  | keep-verified |
| `psh/plans.py` | PATH | PASS |  | keep-verified |
| `check/pantheon/` | PATH | PASS |  | keep-verified |
| `php_eol.py` | PATH | PASS |  | keep-verified |
| `sc.terminus` | SC | PASS |  | keep-verified |
| `sc.console` | SC | PASS |  | keep-verified |
| `check/` | PATH | PASS |  | keep-verified |
| `psh/gather.py` | PATH | PASS |  | keep-verified |
| `psh._legacy` | SYMBOL | FAIL | psh/__init__.py defines no '_legacy' | fix -> `psh.cli` (`psh/_legacy.py` deleted at I14a) |
| `psh.render` | SYMBOL | PASS |  | keep-verified |
| `check/wordpress/` | PATH | PASS |  | keep-verified |
| `check/umich/` | PATH | PASS |  | keep-verified |
| `sc.wp_eval` | SC | PASS |  | keep-verified |
| `sc.wp_error` | SC | PASS |  | keep-verified |
| `check/pantheon/updates.py` | PATH | PASS |  | keep-verified |
| `check/drupal/` | PATH | PASS |  | keep-verified |
| `check/addon_updates/` | PATH | PASS |  | keep-verified |
| `check/umich/drupal_ua.py` | PATH | PASS |  | keep-verified |
| `check.umich.drupal_ua` | SYMBOL | PASS |  | keep-verified |
| `test_hook_dag.py` | PATH | PASS |  | keep-verified |
| `check/pantheon` | PATH | PASS |  | keep-verified |
| `check/wordpress` | PATH | PASS |  | keep-verified |
| `sc.drush_php_script` | SC | PASS |  | keep-verified |
| `sc.drush_error` | SC | PASS |  | keep-verified |
| `psh.no_primary_domain_notice` | SYMBOL | PASS | re-export | keep-verified |
| `psh/charts.py` | PATH | PASS |  | keep-verified |
| `tests/integration/test_charts.py` | PATH | PASS |  | keep-verified |
| `psh/render.py` | PATH | PASS |  | keep-verified |
| `check/umich/annual_billing.py` | PATH | PASS |  | keep-verified |
| `sc.contract_year_end` | SC | PASS |  | keep-verified |
| `psh/mail.py` | PATH | PASS |  | keep-verified |
| `psh.mail.SMTP_SSL` | SYMBOL | PASS |  | keep-verified |
| `psh.SMTP_SSL` | SYMBOL | FAIL | psh/__init__.py defines no 'SMTP_SSL' | allowed (see claims-allow.txt) |
| `psh/lifecycle.py` | PATH | PASS |  | keep-verified |
| `sc.run_state.db_reconnects_by_site` | SC | PASS |  | keep-verified |
| `tests/unit/test_run_state.py` | PATH | PASS |  | keep-verified |
| `psh.lifecycle.finish_run` | SYMBOL | PASS |  | keep-verified |
| `psh.finish_run` | SYMBOL | PASS | re-export | keep-verified |
| `psh.db` | SYMBOL | PASS |  | keep-verified |
| `psh.cli` | SYMBOL | PASS |  | keep-verified |
| `psh.db.create_engine` | SYMBOL | PASS |  | keep-verified |
| `dns_classify.py` | PATH | PASS |  | keep-verified |
| `psh/dns_classify.py` | PATH | PASS |  | keep-verified |
| `psh/cli.py` | PATH | PASS |  | keep-verified |
| `psh.signal` | SYMBOL | PASS | re-export | keep-verified |
| `psh.subprocess` | SYMBOL | PASS | re-export | keep-verified |
| `psh.time` | SYMBOL | PASS | re-export | keep-verified |
| `psh.time.sleep` | SYMBOL | PASS | re-export | keep-verified |
| `psh/` | PATH | PASS |  | keep-verified |
| `check/umich/__init__.py` | PATH | PASS |  | keep-verified |
| `development/2026-07-17-modularization-campaign/CAMPAIGN.md` | PATH | PASS |  | keep-verified |
| `BLOCKMAP.md` | PATH | PASS |  | keep-verified |
| `LEDGER.md` | PATH | PASS |  | keep-verified |
| `622 raw` | COUNT | PASS |  | keep-verified |

### /home/node/.claude/projects/-workspace/memory/no-flattery-feedback.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|

### /home/node/.claude/projects/-workspace/memory/pantheon-cdn-change-check.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `check/pantheon_cdn_change/` | PATH | PASS |  | keep-verified |
| `development/2026-07-12-pantheon-cdn-change-check/` | PATH | PASS |  | keep-verified |
| `fqdns.json` | PATH | PASS |  | keep-verified |

### /home/node/.claude/projects/-workspace/memory/reset-sc-escape-url-leak.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `tests/conftest.py` | PATH | PASS |  | keep-verified |
| `check/cloudflare` | PATH | PASS |  | keep-verified |
| `tests/integration/test_check_umich_cloudflare_cms.py` | PATH | PASS |  | keep-verified |
| `sc.text_maker` | SC | FAIL | sc has no 'text_maker' | allowed (see claims-allow.txt) |
| `sc.html_to_text` | SC | PASS |  | keep-verified |

### /home/node/.claude/projects/-workspace/memory/rich-console-pitfalls.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `sc.console` | SC | PASS |  | keep-verified |
| `tests/helpers/dnsfake.py` | PATH | PASS |  | keep-verified |

### /home/node/.claude/projects/-workspace/memory/shared-sdk-client-preference.md
| claim | kind | verdict | detail | disposition |
|---|---|---|---|---|
| `__init__.py` | PATH | PASS |  | keep-verified |
| `plugin/cloudflare/ips.py` | PATH | PASS |  | keep-verified |

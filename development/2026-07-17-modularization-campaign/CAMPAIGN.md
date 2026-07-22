# CAMPAIGN.md — Modularization Campaign (frozen architecture)

**Status:** approved design, 2026-07-17. Brainstormed and approved section-by-section in
the campaign planning session (see `transcript.md` once archived); prompt in `PROMPT.md`.

This is the **one** copy of the campaign's architecture, decisions, invariants, and
increment plan. Increment specs **cite this document and re-derive nothing** — the
campaign-level brainstorm and adversarial review run once, here; increments inherit that
scrutiny and do not repeat it. Any change to this document is an **amendment**: edit the
document *and* append a ledger entry (`LEDGER.md`) saying what changed and why. An
increment spec that contradicts this document without a ledger amendment is wrong by
definition.

Related documents (all in this directory unless pathed): `PROMPT.md` (the campaign
request), `BLOCKMAP.md` (the B1–B60 functional map of `main()` all scope assignments
reference), `LEDGER.md` (append-only cross-increment record), `/workspace/CONTEXT.md`
(domain glossary — created by this campaign), `/workspace/prompts/directives.md` (the
Spine; PD#n citations below refer to it).

## Glossary (campaign terms — domain terms live in `CONTEXT.md`)

- **Campaign** — this whole program of work: one architecture, N increments.
- **Increment** — one unit of work with its own session, spec, implementation, review,
  commit, and archive. Numbered I0–I14.
- **Wave** — an ordered group of increments (0–4); increments within a wave may be
  reordered if the ledger records why, waves may not.
- **Block** — a `Bnn` region of `main()` per `BLOCKMAP.md`; the stable unit of scope
  assignment.
- **Core package** — the new importable `psh/` package holding infrastructure (Tier 1).
- **Gateway** — `psh/gateway.py`, the single module through which every Terminus/WP-CLI/
  Drush subprocess flows; the future Pantheon-API replacement seam.
- **Façade** — `script_context.py` (`sc`), the stable API surface that checks and plugins
  import; implementations move, the façade's names do not break.
- **Contract** — the per-phase guaranteed `site_context` keys (CLAUDE.md table), which
  this campaign turns into a machine-readable **contract registry**.
- **Hook DAG** — the per-phase topological ordering of hooks derived from declared
  `consumes`/`produces` keys, validated fatally at startup.
- **Ratchet** — the lint/type regime: broad ruff+pyright rules applied as a hard gate to
  moved/new modules immediately, the remnant grandfathered until I14.
- **Remnant** — whatever remains of the original script at any point mid-campaign.
- **Shim** — the thin committed `./pantheon-sitehealth-emails` entry script that calls
  `psh.cli.main()` after I0.
- **Ledger** — `LEDGER.md`; how increment N learns what N−1 actually did.
- **Behavior bar** — the tiered definition of which observable behavior may change (§8).
- **Invariant** — a named property no increment may alter (§9).

**MUST** = required, violation fails review. **NEVER** = prohibited, violation fails
review. **SHOULD** = required unless the increment spec states why not. **MAY** =
allowed, at the implementer's judgment.

## 1. Goal and non-goals

**Goal.** Modularize the 4,752-line main script into (a) a `psh/` core package of
infrastructure modules, (b) self-registering `check/` packages for every notice/section
emitter, and (c) the existing `plugin/` integrations — taking full advantage of the hook
system — while the four e2e goldens stay byte-identical, the per-phase contract is
honored, and the non-U-M path keeps working. End state: `main()` is a ~250–400-line
orchestrator; every U-M-specific behavior lives in `umich` packages; the whole tree
passes the broadened ruff+pyright configuration.

**Non-goals** (exhaustive; each is either declined or deferred with reasoning in §15):
replacing terminus with the Pantheon API; implementing parallel site processing; any new
report content (CSV attachment, cached-% column, env-lock section); SendGrid; refreshing
goldens or recorded fixtures; changing what any check reports (except the named bug
fixes in I1).

## 2. Decision record (exhaustive — from the approved brainstorm)

| # | Decision | Choice | Why |
|---|---|---|---|
| D1 | Pantheon API | **Seam only**: gateway module now, transport swap post-campaign | Swapping transports mid-campaign invalidates terminus fixtures + goldens in every touched increment |
| D2 | Lint/type broadening | **Ratchet in-campaign** (§13) | Code is cleaned exactly once, as it moves; bar fixed in I0 so it never shifts |
| D3 | Behavior bar | **Tiered, config renames allowed** (§8) | Cleanest final schema; production config edited once, at I14, with a migration table |
| D4 | Increment granularity | **Fine: 15 increments** | Safest for session/context limits; split-never-compress backstop (§12) |
| D5 | Target architecture | **Three-tier split** (§3) | Infrastructure ≠ report content ≠ data source; fulfills "full advantage of the frameworks" |
| D6 | Hook flexibility | **Phases stay; hooks declare consumes/produces; per-phase DAG validated at startup** (§4) | Keeps every existing hook/test valid; a phase-less key scheduler rewrites everything for no added power |
| D7 | `--only-warn` plan rec | **In campaign** (I7) | Small, no golden impact, existing TODO |
| D8 | Parallel-ready | **Design constraint only** (§3.4) | Near-free now; actual parallelism stays a README TODO |
| D9 | CSV attachment / cached-% / env-lock | **README TODO** | Each changes rendered email → golden churn mid-campaign |
| D10 | Packaging | **Real package + thin shim** (I0; console-script dropped — see LEDGER I0 amendment 1) | Dissolves the extension-less-script problem; normal imports for tests/pyright/ruff |

## 3. Target architecture

```
                 ./pantheon-sitehealth-emails  (thin shim)
                                │
                        psh.cli.main()  ── orchestrator: bootstrap, site loop,
                                │           phase firing, lifecycle dispatch
        ┌───────────────────────┼──────────────────────────┐
        ▼ Tier 1: psh/ core     ▼ seams (sc façade)        ▼
  configuration  modules   ┌─────────────────────┐   Tier 3: plugin/
  gateway        db        │  hook phases + DAG  │   aws  cloudflare
  traffic        plans     │  contract registry  │   env  umich
  gather         charts    └─────────┬───────────┘   (unchanged roles)
  render         mail                ▼
  lifecycle                Tier 2: check/  (all notice/section emitters)
                           pantheon  wordpress  drupal  addon_updates
                           dns  cloudflare  pantheon_cdn_change  umich
```

### 3.1 Tier 1 — `psh/` core package (exhaustive module map)

| Module | Receives (functions / blocks) |
|---|---|
| `psh/cli.py` | `build_arg_parser`, `parse_args`, arg validation (B5), `main()` orchestrator |
| `psh/configuration.py` | `process_config`, `config_substitution`, `gate_disabled_sections`, DEFER machinery, `load_news_items`, `umich_enabled`, `cloudflare_enabled` |
| `psh/modules.py` | `find_modules`, module loading (B2/B4), hook engine (`add_hook`/`invoke_hooks`/`PHASES`), DAG build/validation, contract registry |
| `psh/gateway.py` | `run_terminus`, `terminus`, `terminus_data`, `wp`, `wp_eval`, `drush`, `drush_php_script`, `fix_drush_output`, `wp_error`, `drush_error`, `TerminusError` |
| `psh/notice.py` | `Notice`, `Severity`, `NoticeRegistry`, `DuplicateNoticeCodeError`, `registry` (added I3; §6 Notice type + code registry) |
| `psh/db.py` | ORM models, `TrafficRow`/`OverageProtectionRow`, `db_engine_args`, `db_retry`/`db_retryable`/`record_db_reconnect`, `update_traffic_rows`, `insert_traffic_rows`, `load_traffic_rows`, `load_overage_protection_window`, `DatabaseUnavailableError` |
| `psh/traffic.py` | `get_old_metrics`, `estimate_month_visits`, `build_traffic_table_rows`, the `traffic_table_columns` global, metrics gather + DB update/load flow (B22–B26), visits-by-month aggregation (B43) |
| `psh/plans.py` | plan_info normalization (B12 part), SKU resolution (B17), `overage_blocks`, `contract_year_end`, `plan_costs`, `build_plan_over_time`, the `cost_table_columns` global, recommendation flow (B47) |
| `psh/gather.py` | Slimmed framework gathers feeding the `site_post_gather` contract (from B32–B35), `check_wordpress_plugin`/`check_drupal_module` helpers, `build_smell_notices` (the B48 smell-notice *builder*; its emission stays in `main()` — LEDGER I10 amendment 1) |
| `psh/charts.py` | Cap geometry (B13 part), chart data prep + matplotlib build (B44–B45) — returns PNG bytes |
| `psh/render.py` | Jinja render (B53), PHP inline + `!important` pass (B54), `escape_url` |
| `psh/mail.py` | Recipient resolution (B49), MIME assembly (B55), `smtp_login`, send (B57) |
| `psh/lifecycle.py` | `RunState`, `finish_run`, `abort_run`, `abort_reason`, `resume_point`, `resume_command`, `rerun_command`, `option_strings_taking_a_value`, `sites_from_resume_point`, `merge_prior_results`, `ResumeSiteNotFoundError` |

`dns_classify.py` stays a top-level module (already extracted; moving it into `psh/` is
MAY-scope for I14, decided by ledger state then).

**Whole-file coverage.** The campaign modularizes the entire script, not just `main()`:
every top-level def and module-level global in `pantheon-sitehealth-emails` (lines
1–2107 included) is assigned to a `psh/` module in this table and appears in exactly one
increment's scope (§11). End state: the original file is the thin shim and nothing else
— a top-level def still there at I14 is a defect the closing audit (§17) catches. Moved
helpers get the full §7 treatment (types, ratchet, verified docs, tests); they do NOT
get algorithmic redesign — moves are behavior-preserving except where §8 says otherwise
(I1, I7's D7, I12's B51).

### 3.2 Tier 2 — new/changed `check/` packages (exhaustive)

| Package | Contents (blocks) | Phase(s) |
|---|---|---|
| `check/pantheon/` (new) | frozen site (B19), no-live-env (B21), upstream updates (B38), PHP EOL (B41) | `site_pre` (frozen, no-live-env), `site_post_gather` (updates, PHP EOL) |
| `check/wordpress/` (new) | PAPC + native-sessions checks, OCP config probe, favicon (from B34) | `site_post_gather` |
| `check/drupal/` (new) | PAPC module check, D7 EOL + tag1_d7es, multisite probe (from B30/B35) | `site_post_dns` (multisite), `site_post_gather` |
| `check/addon_updates/` (new) | add-on updates table notice (B39) | `site_post_gather` |
| `check/umich/` (existing, grows) | umich-oidc-login, Hummingbird fork (B34), Drupal UA check (B35), annual-billing notices (B50/B51), portal-URL text for the recommendation notice (B47's U-M half) | `site_post_gather`, `site_pre_render` (billing) |

`check/dns/`, `check/cloudflare/`, `check/pantheon_cdn_change/` are untouched tenants.
A check MAY fetch its own data through `sc` gateway wrappers when the data is
check-specific (e.g. `upstream:updates:list`); data used by core *and* checks is
published through the contract instead (e.g. `envs`).

The B48 smell notices are **not** a `check/addon_updates/` hook (LEDGER I10 amendment 1):
their *builder* (`build_smell_notices`) moves to `psh/gather.py`, but the *emission* stays
in `main()`. A `site_post_gather` smells hook cannot be ordered after the
`wp_smell`/`drush_smell` in-place mutators — a `produces: ['wp_smell']` declaration is a
condition-2 fatal against the core registry (D-i9-3), and alphabetical registration puts
`check/addon_updates` first in the phase — and relocation would also add smell rows to
`--only-warn` csv output (B48 sits after that gate today), a §8 surface change. The
`mutates` hook declaration that would dissolve this class is post-campaign work (README TODO).

### 3.3 What stays in `main()` (exhaustive, with why)

Config/arg bootstrap ordering (B1–B8 — the two-pass substitution *order* is the
program); overage constants + date window (B9, B13 part); the site-loop skeleton (skips,
banner, sorted order, resume filter — B14–B18, B20, B25, B42); phase firing and contract
stuffing (B27, B28, B31, B37, B52); the B48 smell-notice *emission* call (the builder
moved to `psh/gather.py` at I10, but the emission summarizes end-of-phase smell state no
hook position can guarantee under the D-i9-3 rebind design, and it must stay behind the
`--only-warn` gate — LEDGER I10 amendment 1); notice sort + subject (B50 minus billing);
the `try`/`except BaseException` lifecycle dispatch (B59–B60 call sites). Everything else
leaves. Target: 250–400 lines.

### 3.4 Parallel-ready constraint (D8)

Per-site work MUST be a function of `(site, config, db_session, site_context)`: no new
module-level mutable state; run-scoped accumulators live only in `RunState`. This is a
review criterion from I2 onward, not a parallelism implementation.

### 3.5 The `sc` façade

Checks and plugins import **only** `sc` (and their own package). `sc` keeps every name
listed in CLAUDE.md's runtime-exposed block, re-exporting from `psh/` modules as they
move. NEVER remove or rename an `sc` attribute mid-campaign; additions are fine. The
house-rules test suite gains an assertion that every documented `sc` name exists (I2).

## 4. Phases, hooks, and the DAG

Phases stay the coarse spine: `setup`, `site_pre`, `site_post_traffic`, `site_post_dns`,
`site_post_gather`, `site_pre_render`, plus **new** `run_finish` (fired inside
`finish_run` before artifacts are written, receiving the `RunState`; for future run-level
artifact hooks — no consumer at introduction, like `site_pre_render` was). Dotted
plugin-defined events are unchanged.

From I4, `add_hook` requires two new entries per hook: `consumes` and `produces` — each
a (possibly empty) list of contract-key names. Validation at module-load completion
(exhaustive fatal conditions):

1. A consumed key that nothing produces (neither core's registry for that phase or an
   earlier phase, nor another hook) → fatal.
2. Two producers of the same key → fatal (one owner per key; PD#1 — a silent overwrite
   is a silent failure).
3. A cycle among same-phase hooks → fatal.
4. A hook consuming a key first produced in a *later* phase → fatal.
5. A missing `consumes`/`produces` entry on any hook → fatal (no legacy mode; I4
   retrofits all in-repo hooks in the same change).

`invoke_hooks` orders same-phase hooks topologically (producers before consumers;
registration order breaks ties, so existing behavior is preserved where no edges exist).
The permanent test `tests/integration/test_hook_dag.py` loads **all** real check/plugin
packages and asserts the DAG builds — the "future changes can never make the DAG
impossible" guarantee — and a unit suite proves each fatal condition actually fires
(PD#14: the validator must be shown able to go red).

```
 module load ──► collect hooks ──► per phase: build edges (produces→consumes)
                                        │
                              cycle? unknown key? dup producer? ──► fatal exit (named error)
                                        │ ok
                                topo order stored ──► invoke_hooks uses it
```

**Contract registry.** `psh/modules.py` holds the machine-readable registry: phase →
keys core stuffs (today's CLAUDE.md table, verbatim). Core's stuffing code is checked
against it in tests; CLAUDE.md's table gains a line saying the registry is authoritative.
New contract keys added by increments (exhaustive for this campaign): `envs` (I8, at
`site_pre`), `add_on_updates` + `wp_smell`/`drush_smell`/`composer_smell` (I9/I10, at
`site_post_gather`), plan/cost keys `current_plan`, `recommended_plan`, `plan_costs`,
`savings` (I7, at `site_pre_render`). Each addition updates registry + CLAUDE.md table +
ledger in the same increment.

**Hook-produced keys (I10).** A hook MAY produce keys of its own — declared in its
`produces`, validated for duplicate producers, cycles, and phase position by the same
conditions 1–4 above. Such keys are **DAG-declared, not registry-owned**: they are present
only when the producing hook actually ran (absent when its gate failed or its package is
disabled), so consumers read them with `.get()`, and they are **NOT** part of the
guaranteed per-phase contract (the "new contract keys" list above stays exhaustive for
registry-owned keys only). The campaign's first are `drupal_multisite` /
`drupal_multisite_smell`, produced by `check.drupal.multisite` at `site_post_dns` and read
by `main()` after the phase (I10; see LEDGER I10 amendment 2).

## 5. Configuration

Principles: one section per feature, named for the operator's mental model; every
relocated check gets an `enabled` flag under `[Check.<name>]`, **default true** —
relocating code MUST NOT silently disable a check that runs unconditionally today.
U-M-only checks additionally require `[UMich].enabled` (existing `umich_enabled()`
rule). `gate_disabled_sections()` semantics (nested `enabled`, children dropped) apply to
`[Check.*]` unchanged.

Example (actual TOML, the shape I8 introduces — illustrative of the family, exhaustive
for `check/pantheon/`):

```toml
[Check.pantheon]
enabled = true          # frozen-site, live-env, upstream-updates, PHP-EOL checks
```

New keys land in final shape as introduced (I3 onward). Renames/moves of *existing* keys
happen once, in I14, which MUST deliver: the old→new migration table in
`docs/config-migration.md`, a rewritten `sample-pantheon-sitehealth-emails.toml`, and
exact edit instructions for the production config repo. Until I14, every existing
production key keeps working unchanged.

## 6. Types

Reused as-is: `TrafficRow`, `OverageProtectionRow`, `DnsFacts`, `FetchResult`,
`SiteContext`. Introduced (exhaustive):

| Type | Increment | Shape |
|---|---|---|
| `GatewayResult` | I2 | NamedTuple `(result, errors, fatal)` replacing the anonymous 3-tuples |
| `Notice` | I3 (class) → adopted per increment | frozen dataclass: `severity` (StrEnum alert/warning/info), `code` (unique — registry test), `html`, `text`, `short`, `icon`, `order`; `SiteContext.add_notice` accepts `Notice` or legacy dict; dict form retired in I14 |
| `PlanInfo` / `PlanCatalog` | I7 | typed view over `[Pantheon.plan_info]` |
| `RunState` | I13 | dataclass holding `all_warnings`, `site_results`, `site_savings`, `emails_sent`, reconnect counters |

House-style tuple annotations (`-> (str, str, bool)`) are replaced with real annotations
in every module as it moves — never fixed in place in the remnant (one pass per line,
D2). CLAUDE.md's house-style note is updated in I14 when the last one dies.

## 7. Per-increment obligations

Every increment MUST (this list is exhaustive and lives only here; increment specs cite
it): (1) start by reading `CAMPAIGN.md`, `LEDGER.md`, `CLAUDE.md`, `BLOCKMAP.md` rows in
scope; (2) follow `prompts/implementation-standards.md` (subagent-driven, test-first,
`psh-implementer`/`psh-reviewer`); (3) replace house styles in moved code (§6);
(4) verify — not assume — every claim in comments/docs it moves or writes;
(5) update tests in the same change; (6) update README/docs/CLAUDE.md for what moved;
(7) update auto-memory where a durable fact changed; (8) append its ledger entry
(§12); (9) preserve every invariant (§9); (10) end with `/code-review`, a full
`./run-tests`, and one checkpoint commit including its `development/` folder.

## 8. Behavior bar (canonical gate table)

| Surface | Rule | Until |
|---|---|---|
| Rendered emails (4 goldens) | NEVER change (byte-identical) | end of campaign |
| `-results.json` / `-notices.csv` / `-run.json` structure (keys, row shape) | NEVER change | end of campaign |
| Notice csv *values* | MAY change only in I1 (named bug fixes), I12 (scheduled B51 deletion), I7 (`its-recommends-plan` savings-field format, D-i7-5 — amendment), and I9 (wp-smell precedence when theme-list and OCP-probe stderr co-occur without favicon stderr — see LEDGER I9) | — |
| stdout / console / error messages | MAY improve freely | — |
| Config: existing keys | NEVER break | I14 (renames with migration table) |
| Config: new keys | MUST land in final schema shape | — |
| Exit codes, resume semantics, artifact write gates | NEVER change | end of campaign |

## 9. Named invariants (exhaustive; NEVER violated by any increment)

1. Four e2e goldens byte-identical (`./run-tests` proves it; refresh is forbidden — an
   existing golden going red is a defect in the increment, PD#14).
2. Per-phase data contract: existing keys never removed/renamed/retyped; additions only.
3. Non-U-M path works: non-U-M golden green; no new un-gated U-M content (I1 *removes*
   the one known leak).
4. Run lifecycle: single `except BaseException` flush path; `abort_reason`'s three
   outcomes; artifacts dropped-site rule; notices appended before send; resume-point
   next-site-after-email rule; soft-wrapped copy-pasteable commands.
5. DB: `db_retry` retries whole idempotent units only; `db_retryable` predicate
   unchanged; the read-release commit in the loaders stays (guarded by
   `test_load_traffic_rows_releases_the_connection`).
6. Rich console rules: escape untrusted text; production width reproduced in tests.
7. Test safety interlock (`run_program` forbidden flags) never bypassed or weakened.
8. Column-0 `f"""` notice literals move **verbatim** — never re-indented; `git diff -w`
   is not acceptable evidence for any change touching them.
9. Checks/plugins import only `sc`; `sc` names never removed mid-campaign (§3.5).
10. Recorded fixtures are not regenerated (`terminus-cdnchange/` is hand-maintained and
    `--record` must not run).
11. `--create-tables`/`--update`/`--import-older-metrics` phase-gating rules (CLAUDE.md
    table) unchanged.

## 10. Known-bug inventory → I1

The five bugs and the dead code listed in `BLOCKMAP.md` §Bugs (composer-smell
nesting+variable; shared `php-eol` code; `site_results` omission; un-gated U-M portal
URLs; duplicate `annual-bill` code — B51 handled as: distinct code now, scheduled
deletion when its Aug-2026 date passes, ledgered to I12; dead code deleted). Each fix is
test-first with the test shown red on the old behavior. **Verified 2026-07-17**: the
goldens contain zero `php-eol`/`wp-smell`/`drush-smell`/`composer-smell`/`annual-bill`
occurrences and the golden fixtures report PHP 8.2, so none of these fixes can touch a
golden:

```
$ grep -c 'php-eol\|composer-smell\|wp-smell\|drush-smell\|annual-bill' tests/e2e/__snapshots__/*.ambr
tests/e2e/__snapshots__/test_golden.ambr:0
tests/e2e/__snapshots__/test_golden_cdn_change.ambr:0
tests/e2e/__snapshots__/test_golden_drupal.ambr:0
tests/e2e/__snapshots__/test_golden_nonumich.ambr:0
```

## 11. The increments

Wave dependency structure (increments within a wave are ordered but MAY be resequenced
with a ledger entry; waves MUST NOT be reordered):

```
Wave 0: I0 bootstrap ──► I1 bug fixes
Wave 1: I2 gateway ──► I3 config ──► I4 hooks+DAG ──► I5 DB
Wave 2: I6 traffic ──► I7 plans ──► I8 check/pantheon ──► I9 wordpress ──► I10 drupal
Wave 3: I11 charts ──► I12 render+mail ──► I13 lifecycle
Wave 4: I14 closing sweep
```

| Inc | Scope (blocks / functions) | Delivers |
|---|---|---|
| **I0** | — (no logic moves) | `psh/` skeleton + thin shim (console-script dropped — see LEDGER I0 amendment); conftest `import psh` rework (same collected-test count gate); ratchet config (§13) with rule sets pinned; pyright baseline measured; `LEDGER.md` started; README TODO edits (§15 dispositions); CLAUDE.md pointer to campaign |
| **I1** | B36, B40, B41, B47 (URLs), B48, B50/B51 (codes), dead code | §10 fixes, each test-first |
| **I2** | 302–597 wrappers | `psh/gateway.py`, `GatewayResult`, sc re-exports + façade test; no-subprocess-outside-gateway house rule |
| **I3** | 792–934, 1209–1253, 1608–1648 (`umich_enabled`/`cloudflare_enabled`) | `psh/configuration.py`; `Notice` class + code-uniqueness registry test |
| **I4** | 935–950, hook engine from `script_context.py` | `psh/modules.py`; consumes/produces on all in-repo hooks; DAG validation + fatal-condition tests; `run_finish` phase; contract registry |
| **I5** | 95–178; DB defs within 1285–1575 (`DatabaseUnavailableError` through `db_engine_args`; the resume helpers `ResumeSiteNotFoundError`, `sites_from_resume_point`, `merge_prior_results` stay for I13) | `psh/db.py`; DB test suites relocated intact |
| **I6** | B22–B26, B43; 598–671, 977–1127 | `psh/traffic.py` |
| **I7** | B9, B12 (plans), B17, B47; 967–976, 1128–1208, 1254–1280 | `psh/plans.py`; `PlanInfo`; D7 (`--only-warn` runs recommendation); plan/cost contract keys |
| **I8** | B19, B21, B38, B41 | `check/pantheon/` + `[Check.pantheon]`; `envs` contract key |
| **I9** | B32–B34; 672–739 | `psh/gather.py` (WP half); `check/wordpress/`; U-M WP checks → `check/umich/`; `add_on_updates` + smell contract keys |
| **I10** | B30, B35, B39; B48 *builder* only (emission stays in `main()` — LEDGER I10 amendment 1); 740–791 | gather (Drupal half) + `build_smell_notices`; `check/drupal/`; `check/addon_updates/`; UA check → `check/umich/` |
| **I11** | B13 (caps), B44–B45 | `psh/charts.py` |
| **I12** | B49–B57 minus sort/subject core | `psh/render.py`, `psh/mail.py`; annual billing → `check/umich/` at `site_pre_render`; B51 deletion if past its date |
| **I13** | B14 (accumulators), B56, B59–B60; 1649–2107 plus the resume helpers I5 left behind (1281–1284, 1528–1542, 1576–1607) | `psh/lifecycle.py`; `RunState`; `main()` reaches final form |
| **I14** | — | Config renames + migration doc + sample rewrite + production-config instructions; global ratchet flip + remnant cleanup; docs/README/CLAUDE.md full refresh; `Notice` dict form retired; ledger fully resolved; retrospective + closing audit (§17) |

Sizing note: the largest moves are I9 (~330 main-loop lines + helpers) and I10 (~320 +
helpers). If any increment proves oversized mid-session: **split, never compress** —
commit nothing partial, ledger the split, the second half becomes its own increment.

## 12. Coordination protocol

**Ledger entry template** (append per increment, and for any amendment):

```markdown
## I<N> — <slug> (<date>, commit <sha>)
- Moved: <blocks/functions actually moved>
- Deviations from CAMPAIGN.md: <none | what + why>
- Contract/config/sc additions: <keys/names>
- Discovered tasks: <each with disposition: fixed here | I<M> | README TODO>
- Open questions for next increment: <…>
```

**Discovered-task disposition rules** (canonical): fits current increment's scope and
<~30 min → fix now, note in ledger; belongs to a later increment → ledger it against
that increment (the increment's spec author MUST read these); major/risky/scope-widening
→ README TODO with a sentence of context. Nothing is carried in memory or chat — if it
is not in the ledger or README, it does not exist (PD#9).

**Session flow per increment:** read the §7 documents → write the increment SPEC.md in
`development/<date>-mod-I<N>-<slug>/` citing CAMPAIGN.md sections by number →
`superpowers:writing-plans` → subagent-driven implementation → `/code-review` → full
`./run-tests` → per-task commits, each green; the increment's final commit includes the dev
folder → `/archive-session` → ledger entry.

## 13. Lint/type ratchet

Mechanism (as shipped by I0; see LEDGER I0 amendment 2): TWO ruff configs —
`pyproject.toml` `[tool.ruff.lint]` keeps the narrow PD-rule set running everywhere
including the remnant, and `ruff-broad.toml` carries `select = ["ALL"]` minus a
justified ignore list, with `extend-exclude` grandfathering exactly the remnant
(`psh/_legacy.py`) and not-yet-moved files; each increment deletes its
files from the grandfather list, and the two configs merge at I14. pyright runs in
`./run-tests` from I0 via `[tool.pyright]` (standard mode, `psh/` minus `_legacy.py`),
ratcheting toward strict as typed code moves in. The four existing narrow rules (`E722`, `BLE001`, `S105`, `S106`) remain global
throughout — they mechanize PD#2/PD#6 and are never grandfathered. No
`target-version` pin (CLAUDE.md: it masks the 3.12-only syntax detection).

Baselines measured 2026-07-17 (I0 re-measures and pins both in its spec):

```
$ ./run-tests --fast --llm   (tail)
LLM_SUMMARY passed=727 failed=0 error=0 skipped=1 xfailed=0 xpassed=0
25 snapshots passed.

$ uvx ruff check --isolated --statistics .
26  F541  f-string-missing-placeholders
 8  E741  ambiguous-variable-name
 4  E713  not-in-test
 3  F841  unused-variable
 2  F401  unused-import
 1  E402  module-import-not-at-top-of-file
 1  E712  true-false-comparison
Found 45 errors.
```

(README's "~55" ruff and "39" pyright figures are stale/unverified claims; I0 replaces
them with measured numbers. pyright was not measured in planning — no pyright binary in
the dev container yet; installing it is I0 scope.)

## 14. Risk / control table

| Risk | Control |
|---|---|
| Re-indented column-0 notice literals silently change emails | Invariant 8; goldens as tripwire; AST/token comparison, never `git diff -w` |
| conftest rework silently drops tests | I0 gate: identical collected-test count (727 passed / 1 skipped / 2 deselected baseline) before and after |
| Long-range `main()` local coupling breaks a move | BLOCKMAP produces/consumes; each increment spec lists exactly which locals cross its boundary |
| Session/context overrun mid-increment | Fine granularity (D4); split-never-compress; commits only at increment completion |
| Architecture drift across 15 sessions | This document frozen; amendments only via ledger; specs cite section numbers |
| Hidden hook-order dependencies surface in I4 | I4 audits every hook; real dependencies become explicit DAG edges |
| Ratchet churn on moved code | Rules fixed at I0; cleaning is part of each move |
| Goldens blind to stdout/artifacts | Invariants 4–5 name the artifact/abort test suites as the cover; artifact structure frozen until campaign end |
| Implementer sessions lack context | `psh-implementer`/`psh-reviewer` carry the read list; specs name seams (Spine spec bar); §7 reading list |
| Two annual-bill notices / removal date passes mid-campaign | Explicitly scheduled: codes split in I1, deletion decision in I12, ledger tracks |

## 15. NOT in scope (reasoning preserved so it is never re-litigated)

- **Terminus → Pantheon API swap** — D1; post-campaign project against `psh/gateway.py`.
- **Parallel site processing** — D8; constraint only; README TODO remains.
- **CSV data attachment, cached-% column, env-lock section** — D9; each becomes a small
  post-campaign change (env-lock: a ~50-line `check/` package) once goldens may move.
- **SendGrid, secrets-handling completion, portal traffic capture, daily alerts,
  accessibility/security/Cloudflare scores, AI recommendations, dependency updates,
  terraform-infra** — pre-existing README TODOs, untouched by this campaign.
- **Approach B (library-only) and C (everything-is-a-hook)** — rejected in brainstorm:
  B fails the "full advantage of the frameworks" goal; C forces infrastructure into
  optional-content clothing.
- **Golden/fixture refreshes** — forbidden (Invariants 1, 10).

## 16. Acceptance baseline

§13 outputs are the campaign-start baseline (run and pasted 2026-07-17). Every
increment's definition of done re-runs `./run-tests` at increment end — the full suite
when the live tier's credentials are available in the session, otherwise `--fast` with a
ledger note saying the live tier was skipped — and MUST reproduce goldens
byte-identically. I0 additionally records the collected-test count gate.

## 17. Closing audit (queued for I14; exhaustive)

1. Is `main()` within 250–400 lines, and does everything left match §3.3?
2. Has every DAG fatal condition been demonstrated red at least once?
3. Do the contract registry and CLAUDE.md table agree (test-enforced)?
4. Is any `sc` re-export now consumed by nobody (dead façade surface)?
5. Is the `.py` symlink still needed for anything beyond the shim? If not, note in
   CLAUDE.md; if yes, say for what.
6. Are all ledger items resolved (done, scheduled, or README TODO)?
7. Has the production config repo received and applied the migration instructions?
8. Do README, CLAUDE.md, docs/, and memory reflect the final architecture (no stale
   line-number or module references)?
9. Were any invariants amended mid-campaign, and is each amendment ledgered?

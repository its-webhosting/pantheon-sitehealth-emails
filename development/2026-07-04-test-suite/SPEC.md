# SPEC: Test suite for `pantheon-sitehealth-emails`

**Status:** design, ready to implement. **Do not implement from this file until the owner
approves it** (they may hand-edit first). This is the permanent in-repo design record for the
test-suite work; it is **not** primary documentation of how the program works (that's the code +
`CLAUDE.md` + `docs/`).

Companion files in this folder: `PROMPT.md` (the driving request), `PROBLEMS-DISCOVERED.md`
(program bugs found during design). Prior work: `../2026-07-04-test-harness/SPEC.md` (the harness
this suite extends) and `/workspace/tests/README.md`.

---

## 1. Purpose & guiding principles

The pytest **harness** exists and its smoke tests pass. This spec defines the **real test
suite** that pins the program's *current* behavior, so the upcoming stages — re-enabling SMTP +
adding SendGrid, new features, de-monolithing `main()`, and moving logic into the plugin/config
frameworks — have an early-warning net.

- **Pragmatic coverage, not 100%.** Test all meaningful/practical functionality; deliberately
  leave documented gaps (see §9 Coverage map). Do not chase the coverage metric.
- **Extend the harness; never fork it.** Reuse its fixtures, marks, mock seams, and the
  `run_program()` safety interlock. No parallel testing approach.
- **Tests follow the change (no TDD going forward).** These are the initial characterization
  tests; future tests land alongside features (see `prompts/add-tests-for-change.prompt.md`).
- **Robustness over volume.** Prefer tests that survive unrelated edits (behavioral assertions,
  normalized goldens) over brittle ones (raw string matching, pixel diffs).

## 2. Scope

### In scope
- Behavior-preserving extraction of four pure helpers from `main()` (§5 Part A).
- The one blocking bug fix, folded into that extraction (§5 Part B, `PROBLEMS-DISCOVERED.md` P1).
- Safety-interlock hardening for `--create-tables` / `--import-older-metrics` (§5 Part C).
- Test inventory across `unit`, `integration`, `e2e`, `render`, plus Hypothesis property tests,
  mock-based plugin/check tests, and MIME structural checks (§6).
- A Drupal (`its-wws-test2`) recorded-fixture path + second golden (§7).
- Doc updates: `README.md`, `CLAUDE.md`, `tests/README.md` (§10). No new `docs/` files.

### Out of scope (explicit — so nothing is silently dropped)
- `--all` aggregation/CSV/JSON post-loop path (L3674–3695) — unreachable without `--all`.
- Any real SMTP/SendGrid send; the commented-out `smtp_login()` send path.
- GMail rendering/deliverability tests; the `email` tier stays a skipped scaffold.
- CI, mutation testing, pixel/visual-regression screenshots.
- Full de-monolithing of `main()` (only the four extractions are pulled forward).
- **Live `--create-tables` / live `--import-older-metrics`** (production-data risk).

## 3. Hard safety constraints (design-time and every run, forever)

1. **NEVER** `--all` / `-a`; **NEVER** `--for-real`. Enforced by `run_program()` →
   `ForbiddenFlagError` (`tests/conftest.py`).
2. **NEVER** run `--create-tables` or `--import-older-metrics` against the real config /
   production DB. Only against a throwaway temp SQLite DB in offline mode. Enforced structurally
   by §5 Part C.
3. Only `its-wws-test1` (WordPress) and `its-wws-test2` (Drupal), read-only.
4. No SMTP re-enable; no SMTP/SendGrid/GMail tests this round.

## 4. Decisions (locked with owner)

| Decision | Choice |
|---|---|
| Refactor for testability | Extract 4 pure helpers, behavior-preserving, golden-pinned |
| Discovered bugs | Fix only the blocking one (P1) now; log the rest |
| Drupal coverage | Yes — record `its-wws-test2` + second golden |
| Render tier depth | Functional + zero-console-error + axe-core a11y smoke (no pixel diffs) |
| Plugin tests | AWS `get_secret`, Cloudflare `ips`, UMich portal + SiteLens (all mock-based) |
| Extras | MIME/.eml structural, config-substitution engine, argparse contract, Hypothesis |
| CI | No (local `./run-tests` only) |
| Mutation testing | No |

---

## 5. Diagrams

### 5.1 Per-site report pipeline (what the tests exercise)

```
 TOML ─► process_config (pass 1) ─► find_modules(plugin) ─► invoke_hooks("setup")
   │                                                              │
   │                                              plugins register substitutions + hooks
   ▼                                                              ▼
 find_modules(check) ─► process_config (pass 2) ─► DB connect ─► [--create-tables? exit]
   │                                                              │
   │                                               news load (config* + files)  (*P2: dead)
   ▼                                                              ▼
 sites = terminus("org:site:list", org_id) ───────────► FOR each selected site:
                                                          ├─ metrics fetch → PantheonTraffic upsert (temp DB)
                                                          ├─ invoke_hooks("check", site_context)  ◄─ SiteLens gauges
                                                          ├─ domain/DNS/Cloudflare checks (P4)
                                                          ├─ WP/Drupal plugin/module checks
                                                          ├─ traffic aggregate ─► recommend_plan(...)  ◄─ EXTRACTED (A/B)
                                                          ├─ surge bar chart (matplotlib → chart_cid)
                                                          ├─ render Jinja html+txt → build/<site>.{html,txt}
                                                          ├─ inline-styles.php (real PHP) → *-inline2.html
                                                          └─ MIME assemble → build/<site>.eml   ◄─ MIME test (§6)
                                                          (SMTP send: DISABLED / commented)
```

### 5.2 Mock-seam map (how each tier intercepts I/O)

```
 layer                unit          integration        e2e (offline)     live
 ───────────────────  ───────────   ────────────────   ───────────────   ──────────────
 Pantheon/WP/Drush    call helper   monkeypatch        PATH-shim fake    real terminus
   (run_terminus)     directly      run_terminus/      terminus          (read-only,
                                    terminus           (replay JSON)     test sites only)
 Database             n/a           temp_db (sqlite)   temp sqlite       real config DB
                                                       (minimal.toml)    → NEVER schema/import
 CSS inliner          n/a           n/a                real php          real php
 (inline-styles.php)
 Browser render       n/a           n/a                Playwright        (n/a)
 AWS / Cloudflare /   mock client   mock client /      disabled in       (not exercised)
   portal DB          (stub)        temp sqlite        minimal.toml
```

### 5.3 Interlock decision tree (`run_program` / `_assert_flags_allowed`)

```
 run_program(args, mode)
   │
   ├─ any of {--all, -a, --for-real} (incl. = -forms, abbrevs, bundled -a)? ─► raise ForbiddenFlagError
   │
   ├─ any of {--create-tables, --import-older-metrics}?
   │      │
   │      ├─ mode == "live"?                              ─► raise ForbiddenLiveDataError
   │      └─ resolved --config NOT in fixture-path allowlist ─► raise ForbiddenLiveDataError
   │         (allowlist = realpath under tests/fixtures/config/ or the tmp workdir;
   │          NEVER a backend-type test — the production default DB is also sqlite)
   │
   └─ otherwise ─► exec program
```

---

## 6. Part A — Behavior-preserving extractions

Define these as **module-level functions in the main `pantheon-sitehealth-emails` script**
(preserve the "one big file" convention; do **not** create a new module). Tests import them as
`psh.<fn>`. `main()` is edited to call them. The existing >4-month golden must stay
byte-identical after extraction (the only intended output change is the new ≤4-month path, P1).

| Fn | Source range | Signature (proposed) | Purity |
|---|---|---|---|
| `overage_blocks` | L3123–3125, L3165 | `overage_blocks(overage: float, block_size: float) -> int` | pure |
| `contract_year_end` | L903–905 | `contract_year_end(report_date: datetime.date) -> bool` | pure |
| `estimate_month_visits` | L2617–2633 (exclude the L2634+ chart-array build) | `estimate_month_visits(...) -> float` (finalize args from the block: partial-month visits, day-of-month, days-in-month) | pure |
| `recommend_plan` | L3105–3295 | see below | pure once DB is injected |

**`recommend_plan` contract.**
```
recommend_plan(
    plan_info: dict,               # config [Pantheon.plan_info]
    plan_names: list[str],         # ordered cheapest→most expensive
    current_plan_name: str,
    visits_by_month: dict[str,int],# "YYYY-MM" -> visits
    estimate: float,               # current-month projection; only `estimate > 0` matters here.
                                   # The "no estimate" sentinel is -1 and its handling (incl. the
                                   # template's `estimate >= 0` display at L3553) stays in main();
                                   # do NOT normalize -1→0 inside recommend_plan or the golden breaks.
    end_date_yyyy_mm: str,
    site_plan_start,               # date
    overage_block_size: float,
    overage_block_cost: float,
    op_lookup: Callable[[str], OP|None] | dict[str, OP],  # month "YYYY-MM" -> PantheonOverageProtection|None
) -> dict  # keys: recommended_plan, median_visitors, cost_same, costs_median, costs_best,
           #       current_plan_index, recommended_plan_index, months_until_recommendations,
           #       cost_table_rows
```
`main()` gathers the `PantheonOverageProtection` rows it needs (currently `db_session.get(...)`
inside the loop, L3128–3134) into `op_lookup` **before** calling, so the function is DB-free and
unit-testable. Keep the conservative selection (`costs_best = max(cost_same, costs_median)`;
`recommended = min(costs_best)`) and the downgrade guardrails (Basic special-case, "Performance
Small" floor, intermediate-plan search) exactly as-is.

**Extraction gotchas (must-do, or the refactor breaks at runtime).**
- **Name-shadow / `UnboundLocalError`.** `recommend_plan`'s body currently binds a **local**
  `overage_blocks` (the result of the rounding at L3123, reused at L3165). If the extracted
  module-level helper is also named `overage_blocks` and the body calls it, Python treats
  `overage_blocks` as a local for the whole function → `UnboundLocalError` at the call site.
  **Rename the local** (e.g. `n_blocks = overage_blocks(overage, overage_block_size)`) at L3123
  and L3165 as part of the extraction.
- **NumPy formatting parity.** The helpers operate on `np.float64` values today; keep them so the
  `f"{…:,.2f}"` / `f"{…:,.0f}"` formatting is byte-identical against the golden. Don't cast to
  Python `float` mid-computation.

**Acceptance (Part A).**
- `./run-tests --fast` green.
- `./run-tests -m e2e` golden unchanged for the >4-month `its-wws-test1` case
  (`git diff tests/e2e/__snapshots__/test_golden.ambr` empty).
- `python -c "import importlib.util,...; psh.recommend_plan"` importable (covered by the unit
  tests below actually calling it).

## 6b. Part B — Blocking bug fix (folded into `recommend_plan`)

`recommend_plan` returns a **complete dict even when `len(visits) ≤ 4`**: `median_visitors = 0`
(committed value — the unit/property tests hard-assert `== 0`), `current_plan_index =
recommended_plan_index = plan_names.index(current_plan_name)`, `cost_same = costs_median =
costs_best = {}`, `cost_table_rows = {}`, `months_until_recommendations = 5 - len(visits)`,
`recommended_plan = current_plan_name`. `main()` reads these instead of the current inline
locals, eliminating the `NameError` (`PROBLEMS-DISCOVERED.md` P1).

**Acceptance (Part B).** New e2e case: `its-wws-test1` seeded with ≤4 months renders with exit 0
and the HTML contains the "not enough data yet" state (assert on the
`months_until_recommendations`-driven copy in `email_template.html`); no `NameError` in stderr.

## 6c. Part C — Interlock hardening (`tests/conftest.py`)

- Add `class ForbiddenLiveDataError(RuntimeError)` (named; fail-closed) exported like
  `ForbiddenFlagError`.
- In `_assert_flags_allowed` (or a sibling `_assert_offline_data_flags`), detect
  `--create-tables` / `--import-older-metrics` (exact, `=`-form, and abbrev-prefix forms, mirror
  the existing `_FORBIDDEN_LONG` logic). If present and either `mode == "live"` **or** the
  resolved `--config` is not on the fixture-path allowlist → raise `ForbiddenLiveDataError`.
- **The allowlist is a path check, NOT a backend-type check.** `os.path.realpath(--config)` must
  resolve to a file under `tests/fixtures/config/` (or the per-test tmp workdir). Do **not** infer
  "safe" from `[Database].type == "sqlite"`: the program's production default `[Database]` is also
  SQLite (`database.db` in the repo), so a backend-type test would fail *open* and let live
  `--create-tables` through. Define the allowlist roots as module constants in `conftest.py`
  (`CONFIG_DIR` already exists) and resolve both sides with `realpath` before comparing.
- `run_program(...)` calls it for every invocation.
- Add a `forbidden_live_data_error` fixture returning the class (mirrors
  `forbidden_flag_error`, avoids the double-import identity trap).

**Acceptance (Part C).** Parametrized `tests/unit/test_interlock.py` cases:
`--create-tables` / `--import-older-metrics` (and `--create` / `--import` abbrev forms) with
`mode="live"` raise `ForbiddenLiveDataError`; the same flags in offline mode with the minimal
fixture config do **not** raise. `./run-tests -m unit -k interlock` green.

---

## 7. Test inventory (per file, per test, with acceptance criteria)

Conventions for every test: `pytestmark = pytest.mark.<tier>` at module top; reuse fixtures
`psh`, `reset_sc`, `temp_db`, `program_runner`/`run_program`, `rendered_report`, `normalize_html`,
`forbidden_flag_error`, `forbidden_live_data_error`; import constants `from conftest import …`.
"Done" = the stated command passes and the stated observable holds.

### 7.1 unit — pure, in-process (`tests/unit/`, mark `unit`)

**`test_plan_math.py`**
- `overage_blocks` (formula `round((overage + block/2)/block)`, Python `round` = banker's):
  `(0, 10000) == 0` (`round(0.5)→0`); `(5000, 10000) == 1` (`round(1.0)→1`);
  `(10000, 10000) == 2` (`round(1.5)→2`, banker's rounds the .5 up here); `(15000, 10000) == 2`
  (`round(2.0)→2`). Pin these exact observed values; large overage scales roughly linearly.
- `contract_year_end` (verified L903–905: `end_date.month == 6 and 16 <= end_date.day < 30`):
  `date(2026,6,16)`→True … `date(2026,6,29)`→True; `6/15` and `6/30`→False; any non-June→False.
- `estimate_month_visits`: mid-month partial → proportional projection; day 1 and last-day edges.
- **Acceptance:** `./run-tests -m unit -k plan_math` green.

**`test_recommend_plan.py`** — parametrized over crafted `plan_info` (use the minimal fixture's
tables) + synthetic `visits_by_month` + an in-memory `op_lookup` dict:
- All months below every `traffic_limit` → recommends the cheapest adequate plan.
- Sustained overage beyond current plan → recommends an upgrade.
- `op_lookup` returning a `used_this_month=True` record → that month's overage cost zeroed.
- Retroactive OP (no record, month endswith `-01`) → 4-month waiver window applied.
- Downgrade guardrails: never below "Performance Small" via the median path; Basic special-case;
  intermediate-plan search excludes Basic.
- ≤4-month input → the P1 default dict (recommended == current, `median_visitors == 0`,
  `months_until_recommendations == 5 - len`).
- **Acceptance:** `./run-tests -m unit -k recommend_plan` green; every branch above has ≥1 case.

**`test_config_substitution.py`** — feed synthetic `sc.substitutions`:
- `<{ secret aws foo bar }>`-style resolves to the registered func's return.
- `shlex` tokenizing (quoted args with spaces); `$`-wildcard scoring picks the most-specific match.
- Two-pass semantics: a substitution registered during a (simulated) setup hook resolves on the
  second `process_config` pass but not the first.
- Unknown expr / no match / func returns `None` → `pytest.raises(SystemExit)`.
- **Acceptance:** `./run-tests -m unit -k config_substitution` green.

**`test_argparse_contract.py`** — `psh.build_arg_parser()` / `psh.parse_args`:
- `--create-tables` + `--import-older-metrics` together → parser/`main` rejects (assert the
  actual mechanism: if argparse mutual-exclusion, `SystemExit`; if checked in `main`, test via
  `run_program` expecting nonzero exit — pick per the code at L797–807).
- Neither sites nor `--all` → rejected (offline, via `run_program`, nonzero exit + message).
- `--date 2026-13-40` → `SystemExit` (fromisoformat failure); `--date 2026-03-31` parses to
  `datetime.date`.
- `allow_abbrev=False`: `--fo`, `--al` → `SystemExit` (unknown option).
- Defaults: `--smtp-username` falls back to `$USER`; `--config` default filename; `-vvv` →
  `verbose == 3`.
- **Acceptance:** `./run-tests -m unit -k argparse` green.

**`test_interlock.py`** (extend) — add Part C cases (§6c). **Acceptance:** as §6c.

**`test_pure_functions.py`, `test_property.py`** (existing) — keep `escape_url`, `fix_drush_output`.

### 7.2 property — Hypothesis (`tests/unit/test_property_plan.py`, mark `unit`)
- `overage_blocks`: `@given` non-negative floats — result is a non-negative int, non-decreasing in
  `overage`, and `overage == 0 → 0`.
- `recommend_plan`: `@given` 0…N months of arbitrary non-negative visits — never raises; returns a
  `recommended_plan ∈ plan_names`; `costs_best[p] == max(cost_same[p], costs_median[p])` for all p
  in the >4-month case; recommended has the min `costs_best`.
- **Acceptance:** `./run-tests -m unit -k property` green (Hypothesis default example budget).

### 7.3 integration (`tests/integration/`, mark `integration`) — monkeypatch `run_terminus`, `temp_db`

**`test_wrappers.py`**
- `terminus()` session-expiry retry: monkeypatch `run_terminus` to return the expired-session
  error once then success; monkeypatch `psh.time.sleep`; assert exactly one retry and final
  success (mirror existing regression idiom).
- `terminus()` JSON-decode failure → returns `""` (pins current contract, P3); add a
  **strict-xfail** asserting the desired `(result, errors, fatal)` contract.
- `wp`/`wp_eval`/`drush`/`drush_php_script` return `(result, errors, fatal)` 3-tuples (documents
  reality vs the stale docstrings, P6).
- `wp_error`/`drush_error` produce the expected notice dict-list shape (html+text+csv keys).
- **Acceptance:** `./run-tests -m integration -k wrappers` green.

**`test_db_roundtrip.py`** — `temp_db`:
- `PantheonTraffic` merge/upsert is idempotent (same `(site_id, traffic_date)` re-merged updates,
  doesn't duplicate); unique constraint holds.
- `PantheonOverageProtection` get/add/update on `(site_id, month)`.
- **Acceptance:** `./run-tests -m integration -k db_roundtrip` green.

**`test_mime_structure.py`** — parse `rendered_report['eml']` with `email.parser`:
- Top level `multipart/alternative` with a non-empty `text/plain` part and an HTML part.
- HTML part carries `related` images; **every `cid:` in the HTML has a matching `Content-ID`
  related part and every related part is referenced** (bidirectional integrity).
- `From`/`To`/`Subject` headers present; dry-run `To` is the logged-in user (not an owner).
- **Acceptance:** `./run-tests -m integration -k mime` green.

### 7.4 plugin/check tests (`tests/integration/`, mark `integration`) — mock-based, no live calls

**`test_plugin_aws.py`** — `botocore.Stubber` (or `moto`) around the boto3 Secrets Manager client:
- `get_secret(name, key)` returns the parsed JSON value; `SecretString` and base64 `SecretBinary`
  both decode; second call hits the module cache (stub asserts one API call); missing key →
  `KeyError`. Load `plugin/aws/get_secret.py` in isolation (its own `SourceFileLoader`, like
  `test_regressions.py`) with a minimal `sc.config['AWS']`.
- **Acceptance:** `./run-tests -m integration -k plugin_aws` green.

**`test_plugin_cloudflare.py`** — mock the `Cloudflare` client (`ips.list()` returns synthetic
CIDR lists):
- v4/v6 CIDR strings become `ipaddress.ip_network` objects stored in `sc.plugin_context`.
- Client raising → `pytest.raises(SystemExit)` (the `sys.exit('ERROR: Unable to get lists…')`).
- **Acceptance:** `./run-tests -m integration -k plugin_cloudflare` green.

**`test_plugin_umich_portal.py`** — temp SQLite engine standing in for the portal MySQL DB:
create `sites_site` / `sites_pantheonplan` tables, insert rows, monkeypatch the plugin's engine
creation to point at the temp engine:
- `plan_sku_to_name` in `sc.config` is overridden from `sites_pantheonplan`.
- `sc.config['UMich']['portal']['sites']` populated keyed by `site_slug`.
- Hook ordering: `setup` fires `setup_portal_db`, which fires `setup.umich.portal` (SiteLens
  setup) before the per-site `check` hooks.
- **Acceptance:** `./run-tests -m integration -k umich_portal` green.

**`test_check_sitelens.py`**:
- Gauge color thresholds (pure): `>=90 → GOOD (#00CC66)`, `>=50 → OK (#FFAA33)`, else red
  (`#FF3333`) — test the boundary values 89/90 and 49/50.
- `check_sitelens_scores(site_context)` with mocked `sitelens_scores` adds a "SiteLens" section
  and one inline PNG attachment per score with a `cid` and `disposition:'inline'`.
- `check_sitelens_urls(site_context)` with <4 configured paths adds the "add paths" info notice.
- **Acceptance:** `./run-tests -m integration -k sitelens` green.

### 7.5 e2e (`tests/e2e/`, mark `e2e`) — shim/replay, offline, temp SQLite

**`test_shim_e2e.py`, `test_golden.py`** (existing WordPress) — keep. **Add** to `test_golden.py`
(or a new `test_golden_newsite.py`) the **≤4-month** case (Part B) with its own seed and, if the
copy differs enough, its own snapshot.

**`test_golden_drupal.py`** + `tests/e2e/__snapshots__/test_golden_drupal.ambr` — Drupal golden
for `its-wws-test2` (drush path): render via `run_program` with recorded Drupal fixtures + seeded
traffic + `--date 2026-03-31`; assert `normalize_html(html) == snapshot` and raw `.txt ==
snapshot`.
- **Acceptance:** `./run-tests -m e2e` green; both goldens reproduce deterministically; snapshots
  only change via `./run-tests --update-goldens`.

### 7.6 render (`tests/render/test_render.py`, mark `render`) — Playwright, skips if no Chromium
Rework the existing test (keep the graceful skip-with-hint if Chromium can't launch):
- Rewrite `cid:` image sources in the rendered HTML to `data:` URIs (from the `.eml` related
  parts) so images actually load; load via `sync_playwright`.
- Assert **zero console errors** (collect `page.on("console")`, fail on `error`-level).
- Assert structural elements: `<title>`, `img.banner_image` with `naturalWidth > 0`,
  `img.chart_image`, and presence of notices/news/traffic/cost sections across an
  empty-notices and a populated case.
- Inject **axe-core** from a **vendored** local `tests/vendor/axe.min.js` (no CDN — keeps `--fast`
  hermetic) and assert no `serious`/`critical` violations (allowlist any known-benign rule ids
  explicitly, with a comment).
- Add a Drupal-report render case.
- **Acceptance:** `./run-tests -m render` green where Chromium is installed; cleanly **skips**
  (not fails) otherwise with the `playwright install` hint.

### 7.7 email (`tests/email/test_email_roundtrip.py`, mark `email`) — unchanged
Stays a single `@pytest.mark.skip` scaffold. **Acceptance:** collected + skipped, never errors.

---

## 8. Fixtures, recording, determinism

- **Drupal recording:** extend `tests/tools/record.py` (or add a sibling entry) so
  `./run-tests --record` also records `its-wws-test2` read-only, reusing the existing scrub/trim
  (org list → test site; `domain:list` → `type=="platform"` only, so replay makes no live DNS;
  team emails → `test-owner{1,2}@umich.edu`). Never `--all`/`--for-real`/live schema/import.
- **Seeds:** reuse `seed_traffic`; add a `seed_traffic_short` (≤4 months) helper for the P1 case.
- **axe-core:** vendor a pinned `axe.min.js` under `tests/vendor/` with its version recorded in
  `tests/README.md`. Offline-only; no network fetch at test time.
- **Determinism:** pin `--date 2026-03-31` (mid-year avoids the June contract-year-end path);
  reuse `normalize_report_html` for CID normalization on both goldens; `fqdns.json = {}` keeps
  DNS offline.

## 9. Coverage map (intentionally uncovered — gaps are explicit, not silent)

Run `./run-tests --coverage` (measured, **no gate**). Known-and-accepted uncovered regions:
- `--all` aggregation + CSV/JSON output (L3674–3695) — forbidden flag.
- Real SMTP/SendGrid send + `smtp_login()` (commented) — deferred.
- Live `--create-tables` / `--import-older-metrics` — forbidden by §6c.
- DNS-failure branches (L1252–1289) — stubbed offline; logged as P4.
- Some U-M-only branches proven present but not proven reusable (P8) until a non-U-M golden exists.
- Coverage is measured for in-process tiers only (subprocess e2e not counted without
  `COVERAGE_PROCESS_START` plumbing, which is out of scope).

Implementation must **`log`/note these** in the coverage summary or `tests/README.md` so a reader
doesn't mistake the gaps for "everything covered."

## 10. Documentation updates (part of implementation)

- **`README.md`** Testing section: Drupal golden; render tier does console-error + axe a11y
  smoke; new live-refusal rule for `--create-tables`/`--import-older-metrics`.
- **`CLAUDE.md`** Testing section (non-obvious-only): the four extracted pure helpers are the
  unit/property seam and `recommend_plan` is importable; the interlock now also blocks live
  schema/import flags (`ForbiddenLiveDataError`); the ≤4-month path is now defined (P1 fixed).
- **`tests/README.md`**: per-tier "how to add a test" for the new files, the Drupal golden, the
  plugin mocks, `seed_traffic_short`, and the vendored axe version.
- **`docs/`**: none (developer-facing; `docs/` is end-user only).
- **`prompts/add-tests-for-change.prompt.md`**: already matches; no change.

## 11. Global acceptance criteria

1. `./run-tests --fast` green offline (no network, no Terminus auth): unit + integration + e2e +
   golden + render (or skip) + property.
2. `./run-tests` green where live is available; the `live` tier uses no forbidden flag and no live
   schema/import flag.
3. `./run-tests --coverage` runs and the coverage map (§9) is reflected in output/`tests/README.md`.
4. Interlock: `--create-tables`/`--import-older-metrics` refused live (new tests prove it);
   `--all`/`-a`/`--for-real` still refused.
5. Both goldens reproduce byte-for-byte; the >4-month WordPress golden is unchanged by the Part A
   extraction; changes only via `--update-goldens`.
6. `PROBLEMS-DISCOVERED.md` P1 fixed (new-site renders); P2/P3/P6 have strict-xfail guards; the
   rest logged.
7. `git status` shows only intended new/edited files; no stray `build/`, `database.db`, `.eml`.

## 12. Quality-control self-assessment (per the prompt; refine if any < 0.9)

| Test group | Correctness | Completeness | Implementable | Maintainable | Clarity |
|---|---|---|---|---|---|
| plan math / recommend_plan (unit+property) | 0.95 | 0.93 | 0.92 | 0.95 | 0.94 |
| config-substitution / argparse | 0.95 | 0.92 | 0.95 | 0.95 | 0.95 |
| interlock hardening (Part C) | 0.96 | 0.95 | 0.94 | 0.96 | 0.95 |
| wrappers / db / MIME (integration) | 0.94 | 0.92 | 0.93 | 0.93 | 0.93 |
| plugin/check mocks | 0.92 | 0.90 | 0.90 | 0.91 | 0.92 |
| e2e goldens (WP + Drupal + new-site) | 0.94 | 0.93 | 0.91 | 0.92 | 0.93 |
| render (console + axe) | 0.92 | 0.91 | 0.90 | 0.90 | 0.92 |

Lowest scores (plugin mocks, render) are held ≥0.90 by: isolating each plugin via its own
`SourceFileLoader`, injecting mock clients rather than patching deep internals, vendoring axe for
hermeticity, and the graceful Chromium skip.

## 13. Assumptions to confirm at implementation time (don't block the spec)

- Exact `estimate_month_visits` argument list (finalize from L2617–2633; exclude the L2634+
  chart-array build).
- Whether `--create-tables`/`--import-older-metrics` mutual-exclusion/validation is in argparse or
  in `main()` (L797–807) — dictates whether `test_argparse_contract.py` asserts `SystemExit` or a
  nonzero `run_program` exit.
- The portal plugin's engine-creation seam for `test_plugin_umich_portal.py` (may need a small,
  behavior-preserving injection point if the engine is constructed inline).

(Resolved during review: `contract_year_end` bounds `month==6 and 16<=day<30` (L903–905);
`overage_blocks` banker's-rounding values pinned in §7.1; the interlock uses a fixture-path
allowlist, not a backend-type test; the `estimate` sentinel stays -1 in `main()`.)

## 14. As-built deviations (implementation, 2026-07-05)

Reading the real code during implementation changed three things from the design above. Each was
confirmed with the owner or by test:

1. **`recommend_plan` → `plan_costs`.** The L3175–3295 block is entangled with U-M-specific side
   effects (appends to `site_notices`/`site_savings`, portal-URL "before June 30" messaging,
   `extra_message`/`extra_text`). Extracting a pure function returning the *whole* dict would
   have dragged that U-M messaging into it. Per the owner's decision, only the genuinely-pure
   **cost model** was extracted as `plan_costs(...) -> (cost_same, costs_median, costs_best,
   median_visitors)`; the raw selection + downgrade guardrails + notices stay in `main()` for the
   later de-monolith stage (still covered by the golden + the new recommendation e2e). Unit tests
   are `test_plan_costs.py` (not `test_recommend_plan.py`).

2. **P1 is not a bug.** The ≤4-month `NameError` does not occur — the variables are initialized
   at L985–988 / L3097 (missed at design time). No code fix was made. The offline golden already
   renders the ≤4-month state; `test_recommendation_e2e.py` adds an explicit assertion on it and
   a >4-month case that exercises `plan_costs` end-to-end (the golden never reaches >4 months).
   See PROBLEMS-DISCOVERED.md P1.

3. **Drupal fixtures live in a separate dir.** To avoid disturbing the WordPress fixtures/golden,
   `its-wws-test2` was recorded into `tests/fixtures/terminus-drupal/` (via
   `python tests/tools/record.py --drupal`) and `run_program(..., fixtures_dir=...)` selects it.
   Two new bugs were found while running the code: P9 (`link-name` a11y, allowlisted in the render
   tier) and P10 (zero-traffic `IndexError`, worked around in the recorder by seeding). Both are
   logged in PROBLEMS-DISCOVERED.md, not fixed.

Everything else was implemented as specified. Final state: `./run-tests --fast` is green
(unit/integration/e2e/golden/property + render where Chromium is present); WordPress + Drupal
goldens both reproduce; the extraction kept the WordPress golden byte-identical.

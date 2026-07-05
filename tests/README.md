# Test harness for `pantheon-sitehealth-emails`

Design and rationale: [`../development/2026-07-04-test-harness/SPEC.md`](../development/2026-07-04-test-harness/SPEC.md).
This README is the practical, day-to-day reference.

## Running

Use the `./run-tests` wrapper (from the repo root):

| Command | What it does |
|---|---|
| `./run-tests` | All tiers, including `live` (needs Terminus auth + network). |
| `./run-tests --fast` | Offline subset: `-m "not live and not slow"`. The inner loop. |
| `./run-tests --llm` | Terse, machine-parseable summary (`LLM_SUMMARY …` + `FAILED <nodeid>`). |
| `./run-tests --coverage` | Report coverage (no gate; **in-process tiers only**, see below). |
| `./run-tests --update-goldens` | Refresh the rendered-report snapshots after an intended change. |
| `./run-tests --record` | Re-record the terminus fixtures from the live test site (read-only). |

Extra args pass through to pytest: `./run-tests -m e2e`, `./run-tests -k drush`, `./run-tests tests/unit`.

First-time setup:

```bash
uv pip install .[test]
python -m playwright install --with-deps chromium   # render tier; --with-deps needs sudo
```

If Chromium isn't installed, the `render` test **skips** with the exact setup command (it does
not fail).

## Layout

```
tests/
  conftest.py        # fixtures + the run_program() safety interlock (start here)
  fixtures/
    config/          # minimal.toml (plugins off) + full.toml (plugins on); self-contained
    terminus/        # recorded terminus responses (WordPress its-wws-test1), keyed by argv hash
    terminus-drupal/ # recorded terminus responses (Drupal its-wws-test2)
  vendor/axe.min.js  # pinned axe-core for the offline a11y smoke (no CDN at test time)
  shims/terminus     # fake terminus (record/replay) put on PATH for e2e
  tools/record.py    # re-records + trims/scrubs the terminus fixtures (--drupal for test2)
  e2e/__snapshots__/ # syrupy goldens: test_golden.ambr (WP) + test_golden_drupal.ambr (Drupal)
  unit/              # pure/in-process helpers (plan math, plan_costs, config subst, argparse) + Hypothesis + interlock
  integration/       # monkeypatched run_terminus, temp DB, wrappers, MIME, plugin/check mocks, regressions
  e2e/               # full subprocess run via the shim; artifact + golden + recommendation assertions
  live/              # real terminus, read-only (marked live+slow)
  render/            # headless-browser render: structure + no console errors + axe a11y smoke
  email/             # deferred GMail round-trip scaffold (skipped)
```

## Marks / tiers

`unit`, `integration`, `e2e`, `live`, `render`, `email`, `slow`. `--fast` excludes `live` and
`slow`. Choose the relevant subset for a change (e.g. a Drupal-check edit → `-m "unit or integration" -k drush`
plus the Drupal live/e2e cases).

## Writing a test

- Get the program module from the `psh` fixture (it's imported once; don't import it yourself).
- `sc.options` is pre-set by the autouse `reset_sc` fixture (which also isolates `sc` global
  state between tests). Request `reset_sc` if you need the `sc` module object.
- For in-process Pantheon calls, `monkeypatch.setattr(psh, "run_terminus", fake)`.
- To run the whole program, use the `program_runner` fixture (or the session-scoped
  `rendered_report` / `rendered_report_drupal` fixtures, which run the offline pipeline once per
  site and expose the artifacts). **Never** invoke the program except through `run_program` — it
  raises `ForbiddenFlagError` on `--all`/`-a`/`--for-real` and `ForbiddenLiveDataError` on a
  live-or-non-fixture `--create-tables`/`--import-older-metrics`. Pass `fixtures_dir=` to select
  the WordPress vs Drupal recorded fixtures.
- Temp DB: the `temp_db` fixture gives a fresh sqlite engine + session + the ORM models.
- The extracted pure helpers (`psh.overage_blocks`, `psh.contract_year_end`,
  `psh.estimate_month_visits`, `psh.plan_costs`) are called directly in `unit/` — no fixtures
  beyond `psh`.

## Determinism notes

- The offline e2e uses `minimal.toml`, seeded traffic, and `--date 2026-03-31` (mid-year, to
  avoid the U-M contract-year-end code path). The `domain:list` fixture is reduced to the platform
  domain so replay makes **no live DNS** calls.
- Golden snapshots normalize the volatile `make_msgid` CIDs (`cid:…` → `cid:NORMALIZED`). The
  matplotlib chart/gauge PNGs are attached by CID and not byte-compared. `MPLBACKEND=Agg` is
  forced before the module loads.
- Regenerate golden snapshots only deliberately: `./run-tests --update-goldens`, then review the diff.

## Recording / refreshing terminus fixtures

`./run-tests --record` runs the program live against `its-wws-test1` (read-only, WordPress) with
the shim in record mode, then trims `org:site:list` to the test site, reduces `domain:list` to the
platform domain, and scrubs `site:team:list` emails to `test-owner{1,2}@umich.edu`. For the Drupal
site (`its-wws-test2`, into `fixtures/terminus-drupal/`), run `python tests/tools/record.py
--drupal`. The recorder seeds a month of traffic before the live run so a zero-traffic site
doesn't `IndexError` mid-capture (only terminus responses are recorded; replay re-seeds its own
data). Review the diff before committing; each fixture carries a `recorded` date.

## Coverage

`--coverage` measures the **in-process** tiers (unit/integration). The e2e/live tiers run the
program in a subprocess that pytest-cov does not see unless `COVERAGE_PROCESS_START` +
`coverage.process_startup()` plumbing is added (not wired yet). So the reported number reflects
in-process code, not whole-program coverage. There is no coverage gate by design.

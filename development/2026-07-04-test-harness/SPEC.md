# SPEC — Test Harness for `pantheon-sitehealth-emails`

> **Status:** Design approved 2026-07-04. This document specifies the test *harness* (plus
> initial smoke tests). It is a decision record and an implementation brief for a later
> session — **not** primary documentation of how the program works.
>
> **Scope of the implementation this spec authorizes:** build the harness (runner, fixtures,
> mocking utilities, shims, marks, the `run-tests` wrapper), apply one minimal
> importability refactor, fix the confirmed bugs with regressions, and ship one smoke test
> per tier. It does **not** authorize the full test suite (a later stage), re-enabling SMTP,
> or implementing SendGrid.

---

## 1. Purpose

The program has **zero tests, zero CI, no test tooling** (confirmed: no `tests/`, no
`conftest.py`, no `pytest` dependency, no `.github/`; `README.md`'s top two TODOs are "test
harness" and "test suite"). Major changes are queued next — a large modularization of the
~3,700-line monolith, moving logic into the plugin/config framework, and re-enabling SMTP +
adding SendGrid.

The harness is the **safety net built first**, so those changes are made against a suite that
proves the code still works as designed. The immediate intent (verbatim from the task): *ensure
that all code works as designed and continues to work as designed even in the face of other,
major planned future changes and the addition of new features.*

---

## 2. Hard constraints (govern design and every run, now and forever)

| # | Constraint | Enforcement |
|---|---|---|
| C1 | **NEVER** run the program with `--all` / `-a` (can take ~6 h). | A `run_program()` interlock raises before exec if `--all`/`-a` appears; covered by a test. |
| C2 | **NEVER** run the program with `--for-real` (can email real customers). | Same interlock also refuses `--for-real`; covered by a test. |
| C3 | Tests target only `its-wws-test1` (WordPress), `its-wws-test2` (Drupal), or a deliberately chosen real site — all **read-only**. | Live-tier fixtures hardcode these site names; no write/deploy Terminus verbs are ever issued. |
| C4 | Do **not** re-enable the disabled SMTP send block (lines 3627-3631). | No test un-comments it; the email round-trip tier stays skipped until SMTP/SendGrid lands. |
| C5 | Do **not** touch the `fqdns.json` 24-h staleness check. | Only reachable under `--all`, which C1 forbids; irrelevant to tests. |

These constraints are accepted to produce coverage gaps (e.g. the `--all` aggregation path and
real email delivery are untestable now). The gaps are listed in §13.

---

## 3. Current state (facts verified against source on 2026-07-04)

All line numbers are in the main script `pantheon-sitehealth-emails` (3,673 lines, shebang
`#!/usr/bin/env python`, **no `.py` extension**) unless noted.

- **One golden subprocess seam.** Every Pantheon/WP/Drush interaction funnels through
  `run_terminus(command, input_data=None) -> (str, str, bool)` (`:226`), which uses
  `subprocess.Popen` in argument-list form (no `shell=True`), with a 300 s
  `communicate(timeout=…)`. Above it: `terminus()` (`:316`), `wp()`/`wp_eval()` (`:342`/`:356`),
  `drush()`/`drush_php_script()` (`:413`/`:428`). WP and Drush are dispatched *as* Terminus
  subcommands (`terminus wp …`, `terminus drush …`), so a single fake `terminus` covers all three.
- **Second, independent subprocess seam.** The CSS inliner
  `subprocess.run(["php", "inline-styles.php", <in>, <out>], check=True)` (`:3554`). `php` is
  local, deterministic, fast → tests use **real php**, no shim.
- **No direct HTTP to Pantheon.** No `requests`/`httpx`/`urllib.request` for Pantheon; auth is
  delegated to the Terminus binary. The only auth logic in-script is the (broken) session-expiry
  retry in `terminus()`.
- **Other genuine network seams** (only when their plugin is enabled in config):
  `dns.resolver.resolve` (`:1218`/`:1248`) in the FQDN/Cloudflare check; the Cloudflare SDK
  `Cloudflare(...).ips.list()` (`plugin/cloudflare/ips.py`); boto3 Secrets Manager
  (`plugin/aws/get_secret.py`). Test configs disable these plugins unless a test targets them.
- **Email send is disabled.** Lines 3627-3631 are commented out; the program's only email output
  today is `build/<site>.eml` (written unconditionally at `:3624`) plus `build/<site>.{html,txt}`
  and the inlined `-inline2.html`. **Tests assert on artifacts, never on SMTP.**
- **Import-time side effects.** The arg-parser construction + `parse_args()` run at module scope
  (`:142-219`, ending `sc.options = args_parser.parse_args()`); the file has no `.py` extension.
  Importing it today parses live `sys.argv`. SQLAlchemy models (`Base`, `PantheonTraffic`,
  `PantheonOverageProtection`) are defined at import (`:93-135`). (The `build/` output dir is a
  separate thing, created inside `main()` at `:800` — not a module-scope effect.)
- **DB is config-injectable.** Engine built at `:818-836` purely from `sc.config["Database"]`
  (`sqlite:///{name}` or `mysql+mysqldb://…`). `--create-tables` runs
  `Base.metadata.create_all` then `sys.exit`.
- **Global mutable state** in `script_context.py` (imported everywhere as `sc`):
  `options, config, plugin, check, news, substitutions, hooks, plugin_context` are mutable and
  must be reset between in-process tests; `console`, `icon`, and the configured `text_maker`
  (html2text) are effectively immutable and are **not** reset (see §5.2).
- **Directly unit-testable today (given `sc.options` is set):** `escape_url` (`:222`),
  `fix_drush_output` (`:391`), `wp_error` (`:365`), `drush_error` (`:443`),
  `check_wordpress_plugin` (`:533`, logic + stdout), `check_drupal_module` (`:601`, logic +
  stdout), and `sc.add_notice`/`sc.add_news_item` (`script_context.py:65`/`:80`). Note: these are
  not literally *pure* — `fix_drush_output` and the `check_*` helpers call `sc.debug()`/
  `sc.console.print()`, so `sc.options` must be populated (with a `verbose` attribute) by the
  sc-reset fixture or they raise `AttributeError` on `sc.options.verbose`.
- **Tooling on hand:** Python 3.13 via uv (`pyproject.toml requires-python >=3.11`; deps `rich,
  SQLAlchemy, matplotlib, Jinja2, dnspython, html2text, semver`; extras `mysql/aws/cloudflare`);
  Node 24; PHP + Composer (`pelago/emogrifier ^7.2`); Terminus authenticated; **dev-container
  firewall is OFF and will stay off** (network + Pantheon auth always available).

### 3.1 Confirmed bugs to fix now (with regressions) — re-verified against source

1. **`terminus()` session-expiry retry is doubly broken (`:320-337`).** `*args` is a *tuple*, yet
   the retry path does `del args["pshe-no-retry"]` (indexing a tuple with a `str` → `TypeError`)
   and `args.push("pshe-no-retry")` (`.push` is not a tuple/list method → `AttributeError`). Any
   time Pantheon returns `Invalid or expired session header: X-Pantheon-Session`, this path is
   entered and **crashes** instead of retrying.
2. **`check/umich/__init__.py:11`** `else` branch calls `sc.console('…')` — `sc.console` is a
   rich `Console` instance; the callable form raises `TypeError`. Should be `sc.console.print(…)`.
   Reached whenever the `[UMich]` plugin is loaded but not `enabled`.

Both are fixed as part of harness implementation, each pinned by a regression test (§9).

---

## 4. Approaches considered and evaluated

Three approaches were weighed. Scores are 0–1 on Correctness, Completeness, Ability-to-implement,
Maintainability, Clarity (the task's quality-control axes). "Correctness" here = *does the
approach actually catch the regressions we care about*; "Completeness" = *coverage breadth
achievable*.

### Approach A — Black-box only (zero source changes)
Run the script as a subprocess with a fake `terminus` on PATH; assert on `build/` artifacts,
exit codes, stdout. No code touched before a suite exists.

| Axis | Score | Note |
|---|---|---|
| Correctness | 0.80 | Catches end-to-end breakage but blind to internal-logic regressions. |
| Completeness | 0.55 | Cannot unit-test pure functions, fault-inject `run_terminus`, or exercise the retry/error paths deterministically. |
| Ability-to-implement | 0.95 | Simplest; no refactor risk. |
| Maintainability | 0.70 | Every test pays subprocess cost; failures are coarse ("artifact differs") and hard to localize. |
| Clarity | 0.85 | Simple mental model. |

**Rejected:** Completeness 0.55 — the upcoming modularization refactor will move internal logic
around, and a black-box-only net can't localize what broke.

### Approach B — Full unit-test refactor now
Aggressively split the monolith into importable modules, then unit-test broadly.

| Axis | Score | Note |
|---|---|---|
| Correctness | 0.75 | The large diff *before* a safety net risks introducing the very regressions we're trying to prevent. |
| Completeness | 0.95 | Highest achievable coverage. |
| Ability-to-implement | 0.55 | Large, risky diff; contradicts "don't break things before tests." |
| Maintainability | 0.90 | Clean long-term. |
| Clarity | 0.80 | Big conceptual change up front. |

**Rejected:** Ability-to-implement 0.55 and Correctness 0.75 — it inverts the plan's ordering
(net first, refactor second) and front-loads the biggest risk.

### Approach C — Hybrid: minimal importability seam + both mock styles ✅ SELECTED
One tiny, behavior-preserving change makes the module importable (§5.1). Then: monkeypatch
`run_terminus`/`terminus` for fast in-process unit/integration tests, **and** a PATH-shim fake
`terminus` for deterministic full-script e2e, **and** live tiers that run real Terminus read-only
against the test sites (the default per the live-first decision).

| Axis | Score (pre-refine) | Refined | Note |
|---|---|---|---|
| Correctness | 0.90 | **0.95** | Localizes regressions at unit + integration level; live tier catches real API drift. |
| Completeness | 0.88 | **0.92** | Covers pure logic, error/edge injection, full pipeline, rendering, and real integration. Gaps only where C1–C4 forbid. |
| Ability-to-implement | 0.90 | **0.93** | A single mechanical wrap of the existing ~77-line arg-parser block is the only source change (behavior-preserving, covered by the byte-identity gate); everything else is additive test code. |
| Maintainability | 0.88 | **0.92** | Fast inner loop (monkeypatch) + realistic outer loop (live/shim); golden/fixture refresh scripted. |
| Clarity | 0.90 | **0.94** | Explicit tiers and one sanctioned invocation path. |

**Refinements applied to reach ≥0.90 on every axis:** (a) added the `run_program()` safety
interlock so C1/C2 can never be violated even by a mistaken test; (b) added golden-output
normalization rules (§5.9) so rendering snapshots are stable despite volatile CIDs/dates; (c)
scoped property testing honestly to pure/extractable functions (§5.10); (d) specified `sc`-state
reset (§5.2) so in-process tests don't leak global state; (e) pinned a byte-identity verification
gate for the seam refactor (§5.1) so "behavior-preserving" is *proven*, not asserted.

**Selected: Approach C (Hybrid).**

---

## 5. Architecture

### 5.0 Framework choices (and why, over alternatives)
- **pytest** — the spine. Fixtures, marks, `parametrize`, and the richest plugin ecosystem.
  *Rejected:* `unittest` (verbose, weak fixtures/parametrization), `nose2` (unmaintained).
- **syrupy** — golden/snapshot assertions for rendered reports, with `--snapshot-update`.
- **Hypothesis** — property-based tests for pure math.
- **pytest-cov** — coverage measurement (reported, **no gate**). It measures the **in-process**
  tiers (unit/integration) by default. The e2e/live tiers run `main()` in a *subprocess* via
  `run_program()`, which pytest-cov does **not** see unless `COVERAGE_PROCESS_START` +
  `coverage.process_startup()` plumbing is wired in (specified optional in §12). So the reported
  number reflects in-process code unless that plumbing is enabled — the docs state this so the
  figure is never read as whole-program coverage.
- **pytest-playwright** (Python Playwright) — the browser render tier. One language, one runner;
  it manages its own Chromium (`playwright install chromium`); firewall is off so the download
  works. *Rejected:* a separate Node/Puppeteer toolchain (second language + second runner for
  no gain).
- **PHP:** no PHP test framework. `inline-styles.php` is a pure file-in/file-out transform,
  exercised via subprocess with sample HTML and a golden output.

### 5.1 The minimal seam refactor (the only source change, behavior-preserving)
Make the module importable without executing argparse at import:

```python
def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(...)
    ...   # every existing add_argument call, unchanged
    return p

def parse_args(argv=None):
    return build_arg_parser().parse_args(argv)

# bottom of file:
if __name__ == "__main__":
    sc.options = parse_args()
    main()
```

- Functions read `sc.options` at *call* time, so relocating the `parse_args()` call into the
  `__main__` guard is safe: a test imports the module (no argv parsing), sets `sc.options` to a
  parsed namespace or a fake, then calls functions or `main()`.
- **No rename.** `./pantheon-sitehealth-emails` still runs exactly as documented. The
  extension-less file is loaded in tests via `importlib.util.spec_from_file_location` +
  `SourceFileLoader`, once, cached by a session-scoped fixture (§5.2) to avoid re-registering the
  SQLAlchemy models.
- **Verification gate (proves "behavior-preserving"):** for `its-wws-test1` at a fixed `--date`,
  the pre-refactor and post-refactor `build/` artifacts must be identical after normalizing the
  known-volatile bits (§5.9). This diff is run once during implementation and recorded in the
  handoff notes; it is not a standing test (it needs a live run).

```
   argv ──► build_arg_parser() ──► parse_args(argv) ──► sc.options
                                          ▲                  │
   test: import module (no parse) ────────┘                  ▼
   test: sc.options = fake/parsed ───────────────────► call any function / main()
```

### 5.2 Global-state isolation
`script_context.py` holds process-global mutable state. A `conftest.py` autouse fixture
snapshots and restores, per test: `sc.options, sc.config, sc.news, sc.hooks, sc.substitutions,
sc.plugin, sc.check, sc.plugin_context`. The snapshot must **deep-copy** (`copy.deepcopy`) the
mutable containers — `sc.hooks` is a dict-of-lists and `add_hook`/`add_notice`/`add_news_item`
mutate `sc.hooks`/`sc.news`/`sc.substitutions` **in place** (`script_context.py:41`/`:77`/
`:90-92`), so a shallow snapshot would not isolate nested mutation between tests. The module-load
fixture is **session-scoped** (import
once); the state-reset fixture is **function-scoped** (fresh state each test). Plugin/check
self-registration is an import side effect gated by config flags — tests that need a plugin
registered import the relevant package *after* setting a config that enables it, inside an
isolated `sc` state.

### 5.3 Directory layout
```
tests/
  conftest.py          # module-load fixture, sc-reset, temp cwd+build, temp sqlite,
                       #   config-fixture loader, run_program() interlock, --llm reporter hook
  README.md            # dev-facing testing docs (NOT docs/, which is end-user only)
  fixtures/
    config/            # minimal.toml, full.toml — self-contained; NEVER depend on the private config symlink
    terminus/          # recorded JSON keyed by argv: org:site:list, env:info, env:metrics, wp plugin list, drush pm:list …
    db/                # seed PantheonTraffic / PantheonOverageProtection rows
    html/              # committed sample build/*.html for the render tier (no live run needed)
  shims/
    terminus           # fake executable: maps argv → fixtures/terminus/<key>.json, prints it
  __snapshots__/       # syrupy golden baselines (rendered reports, normalized)
  unit/                # pure funcs: fix_drush_output, escape_url, notices, config_substitution, plan-rec math
  integration/         # in-process; run_terminus monkeypatched (or live); temp DB; check hooks; the 2 bug regressions
  e2e/                 # full-script subprocess runs: shim-backed (deterministic) + live (default)
  render/              # pytest-playwright: load a report HTML with cid: image refs rewritten to local PNGs; assert DOM structure
  email/               # GMail round-trip — scaffolded, @pytest.mark.skip(reason=…), see §11
run-tests              # thin wrapper over pytest (executable)
```

### 5.4 Test tiers & marks
Registered marks: `unit`, `integration`, `e2e`, `live`, `render`, `email`, `slow`.

- **Default `./run-tests` includes live tiers** (live-first decision: real Terminus read-only
  against the test sites is the primary confidence signal).
- **`./run-tests --fast`** selects the offline subset `-m "not live and not slow"` for the inner
  loop (unit + shim-backed integration/e2e + render on committed HTML) — fully offline,
  deterministic.
- Claude Code selects the relevant subset per change (e.g. a Drupal-check edit → `unit` +
  `integration` + the Drupal `e2e`/`live` cases via `-k drupal`).
- **Hermeticity tradeoff (accepted):** because live is the default, a bare `./run-tests` requires
  live Terminus auth + network and can fail on unrelated Pantheon API drift or a test-site
  outage. That is the point of the live tier (it catches real drift), but the **hermetic,
  offline inner loop is `./run-tests --fast`** — that is what Claude Code and pre-commit checks
  run for fast, deterministic feedback; the full `./run-tests` is the higher-confidence pass.

```
                 ▲ realism / cost
      live       │  real terminus, read-only, its-wws-test1/2   (default; slow; catches API drift)
      e2e        │  full subprocess run, shim terminus + real php (deterministic pipeline)
      integration│  in-process, run_terminus monkeypatched, temp DB, check hooks (fault injection)
      render     │  Playwright over report HTML (cid: refs → local PNGs)  (rendering correctness)
      unit       │  pure functions, no I/O                        (fast; many; localizes bugs)
                 ▼ speed / count
```

### 5.5 External-tool interception (both styles)
- **Monkeypatch (unit/integration):** patch `run_terminus` (and/or `terminus`) on the loaded
  module to return canned `(stdout, stderr, fatal)` or raise/inject faults — the deterministic
  way to exercise error paths: `fatal=True` timeouts, malformed JSON (`json.JSONDecodeError`),
  and the expired-session retry. This is the primary seam because all Pantheon I/O funnels
  through it.
- **PATH-shim fake `terminus` (e2e):** `tests/shims/terminus` is prepended to `PATH`; it reads a
  manifest mapping the invoked argv to a `fixtures/terminus/*.json` file and prints it. Real
  `php` is used (local, fast). This exercises the *real* subprocess/argument-building path and
  the full render→MIME→`.eml` pipeline without network.
- **Live (default):** no interception — real `terminus` runs read-only against `its-wws-test1/2`.

### 5.6 DB fixtures
A `temp_db` fixture points `sc.config["Database"]` at `type="sqlite", name=<tmp file>`, runs
`Base.metadata.create_all`, and seeds rows from `fixtures/db/`. In-process tests of DB-touching
helpers get a live SQLAlchemy session bound to that temp engine. No test touches the repo's real
`database.db`.

### 5.7 Config fixtures
`fixtures/config/minimal.toml` (plan_info, plan_sku_to_name, `[Database]` sqlite, `[News]` →
temp folder, **all plugins disabled**) and `full.toml` (umich/cloudflare/aws enabled, with those
external calls mocked) let tests run without the private, symlinked production config. **No test
depends on the symlinked `pantheon-sitehealth-emails.toml`.**

### 5.8 The `run-tests` wrapper (thin)
Executable wrapping pytest. Flags:

| Flag | Effect |
|---|---|
| (none) | `--human`: default rich pytest output, all tiers incl. live. |
| `--llm` | terse, `-q`, `--tb=short`, no color, failures-first, plus a machine-parseable summary line emitted by a conftest `pytest_terminal_summary` hook (counts + `FAILED <nodeid>` list, no fluff). |
| `--fast` | offline subset (`-m "not live and not slow"`). |
| `--record` | refresh `fixtures/terminus/` from the live test sites (read-only). |
| `--update-goldens` | pass `--snapshot-update` to syrupy. |
| `--coverage` | enable pytest-cov (reported, no gate). |
| passthrough | `-m`, `-k`, and paths forwarded to pytest. |

```
        ./run-tests
             │
   ┌─────────┼───────────┬───────────┬──────────────┬───────────┐
 default   --llm       --fast     --record      --update-       --coverage
 (human)  (terse,    (offline   (real         goldens          (pytest-cov,
  all      machine    subset)   terminus,     (syrupy           no gate)
 tiers)    summary)             read-only)     update)
```

### 5.9 Determinism / golden normalization
Before snapshotting `build/<site>.{html,txt}` and `-inline2.html`, normalize volatile content:
- **`make_msgid` CIDs** → regex-normalize **all** `make_msgid`-generated CIDs to a stable
  placeholder, not just the banner/chart CIDs at `:3505-3506` — the per-attachment SiteLens
  gauge CIDs created under `full.toml` are also random and appear in the HTML as `cid:` refs.
- **`Date:` header** in the `.eml` → strip/normalize.
- **matplotlib PNG bytes** (chart, SiteLens gauges) → do **not** byte-compare; assert the inline
  image parts *exist* with the expected CIDs/content-types. Matplotlib output is not byte-stable
  across versions/backends, so the module-load fixture sets `MPLBACKEND=Agg` in the environment
  **before** the `importlib` load — `matplotlib.pyplot` is imported at the target's top (`:42`),
  so a later `matplotlib.use("Agg")` would be too late.
- Fix `--date` and seed the DB so all traffic-derived text is stable.

### 5.10 Property-based testing (honest scope)
Hypothesis targets deterministic functions with `sc.options` set: `fix_drush_output`
(string→(str,str)), `escape_url`, and the day/month **traffic aggregation** helper. The
**plan-recommendation cost model is currently inline in `main()` (`:3095-3211`)** and is not
directly callable. SPEC records two options, chosen at implementation time:
- **(default) pin the math via `parametrize`d e2e cases** with fixed traffic fixtures, no source
  change. This is the safer default and needs no refactor.
- (optional) a pure extraction `recommend_plan(...)` that `main()` then calls, enabling direct
  property tests. **Caveat:** a behavior-preserving extraction is *not* the "small" 3-arg
  function it might seem — the inline model also consumes `plan_info`, the current plan, per-month
  `PantheonOverageProtection` lookups (`db_session.get`), `overage_block_size`/`overage_block_cost`,
  the current-month `estimate`, and `site_plan_start`. Because that pulls real refactor surface
  forward, it is **deferred to the refactor stage** unless it proves genuinely small; the
  parametrized-e2e default covers this math in the meantime.

### 5.11 Safety interlock (Prime Directive #1: zero silent failures)
`run_program(args: list[str], **kw)` in `conftest.py` is the **only** sanctioned way tests invoke
the program. Before exec it asserts none of `--all`, `-a`, `--for-real` is present and **raises
`ForbiddenFlagError`** (a named exception, not a bare assert, not a silent skip) otherwise. It is
itself covered by a test that feeds it each forbidden flag and asserts the raise. When the email
tier activates, an analogous guard asserts the recipient is the GMail test identity, never a
customer address.

---

## 6. Shadow-path & edge-case analysis (Prime Directives #2–#4)

For each **new** data flow the harness introduces, the happy path plus three shadow paths
(nil / empty / upstream-error) are traced; named exceptions are specified.

| New flow | Happy | Nil input | Empty input | Upstream error |
|---|---|---|---|---|
| Fake `terminus` shim reads manifest | argv → fixture JSON printed | argv not in manifest → exit non-zero + stderr `no fixture for: <argv>` (never silent empty) | empty fixture file → shim prints `{}`; test asserts caller handles empty JSON | corrupt fixture → shim exits 1; e2e test sees non-zero exit and fails loudly |
| Monkeypatched `run_terminus` | returns seeded `(out,"",False)` | `out=None` → `json.loads(None)` raises **`TypeError`**, which is **not** caught by `except json.JSONDecodeError` at `:328` → `terminus()` crashes. A real latent gap; a test **pins current behavior** (documented, not fixed here — behavior changes belong to the refactor). | `out=""` → `json.loads("")` raises `JSONDecodeError`, caught at `:328`, `result=""` (current behavior) — pinned by test | inject `fatal=True` → assert caller treats as fatal |
| `terminus()` retry (post-fix) | expired-session once → retry → success | — | — | expired-session twice → no infinite loop (sentinel honored); asserted |
| `temp_db` seed | rows inserted, queried | no rows → report path with zero traffic renders without crash (asserts empty-traffic handling) | empty seed file → create_all only, no rows | bad DSN → `create_engine` raises; test asserts named failure |
| Golden snapshot | normalized HTML matches baseline | missing baseline → syrupy reports "snapshot not found" (run `--update-goldens`) | empty render → test fails (report must have content) | template error → Jinja2 raises; test asserts render fails loudly |
| Render tier (Playwright) | HTML (cid: refs rewritten to local PNGs) loads, key DOM selectors present | missing HTML file → test fails with path | empty HTML → assertion on required elements fails | browser launch failure → pytest-playwright errors (not skipped silently) |

**Interaction edge cases (Prime Directive #4):** user interrupts a live run (Ctrl-C) → pytest
reports KeyboardInterrupt, no partial artifact is asserted as success; slow Pantheon → live tests
inherit the program's 300 s Terminus timeout and are marked `slow`; stale fixture → `--record`
refreshes, and a fixture's provenance/date is recorded in a header comment so staleness is visible.

**Catch-all smell (Prime Directive #2):** the harness itself uses **named** exceptions
(`ForbiddenFlagError`, `FixtureNotFoundError`); it must not wrap test bodies in bare
`except Exception`. The program's own broad handling (e.g. `terminus()` swallowing
`JSONDecodeError` into `result=""`) is *documented and pinned* by tests, not "fixed" here beyond
the two confirmed bugs — behavior changes belong to the later refactor.

---

## 7. Best practices baked in
- **Test pyramid** (many fast unit, fewer integration, fewest e2e/live) — §5.4.
- **One sanctioned invocation path** with a fail-closed safety interlock — §5.11.
- **Golden/snapshot testing** with explicit volatile-field normalization — §5.9.
- **Fixtures recorded from reality, refreshable by one command** (`--record`), with provenance
  headers so they don't rot silently — §5.8, §6.
- **Dual-audience output** (human default, `--llm` terse/parseable) — §5.5/§5.8; both are
  LLM-friendly (a human pasting a failure into Claude Code gets clean, localizable output).
- **CI-portable by construction:** everything is pytest + marks; adding GitHub Actions later is a
  workflow file that runs `run-tests --fast` (offline) plus, optionally, a credentialed live job.
  (CI itself is out of scope — §13.)
- **Coverage measured, never chased** (no gate) — §5.0.

---

## 8. Maintenance strategy (keep tests relevant as the program changes)
- **Standing policy** (added to CLAUDE.md): every change designs + implements appropriate tests
  at the time the change is made (the program is not adopting TDD; tests follow the change).
- **Fixture provenance + refresh:** each recorded fixture carries a `// recorded <date> from
  <site> via <terminus argv>` header; `run-tests --record` regenerates the set; a fixture older
  than a chosen horizon prints a notice when used in a live-diff check.
- **Goldens updated deliberately:** rendering changes require `--update-goldens` and show up as a
  reviewable snapshot diff — unintended rendering drift fails loudly.
- **Reusable prompt templates** (stored in this feature folder for later stages, not executed
  now): `add-tests-for-change.prompt.md` (design+add tests for a diff) and
  `refresh-fixtures.prompt.md` (re-record + update goldens, review the diff). These make routine
  test maintenance a repeatable Claude Code task.

---

## 9. Smoke tests the harness ships with (prove the harness works — NOT the suite)
| Tier | Smoke test | Asserts |
|---|---|---|
| unit | `fix_drush_output` / `escape_url` | pure input→output; no I/O. |
| integration | monkeypatched `run_terminus` + `temp_db` + a `check` hook | in-process pipeline step works; state isolated. |
| e2e | shim `terminus`, full subprocess run for one site + fixed `--date` | `build/<site>.eml`, `.html`, `.txt` produced; exit 0. |
| golden | normalized `build/<site>.html` from the shim e2e (under **minimal.toml**) → syrupy snapshot | rendering pinned; `--update-goldens` regenerates and an immediate re-run is green (proves the golden pipeline + acceptance #9). This exercises the banner/chart CID normalization; the SiteLens-gauge CID path (needs `full.toml` + mocked umich data) is deferred to the suite stage — the normalization regex is written generally so it already covers those CIDs. |
| property | Hypothesis over `fix_drush_output` (with `sc.options` set) | the `(str, str)` invariants hold across generated inputs (this is what proves the Hypothesis wiring). |
| live | real `terminus self:info` (or read-only `env:info` on `its-wws-test1`) | Terminus auth + JSON parse work end-to-end. |
| render | Playwright loads a committed report HTML (cid: refs rewritten to local PNGs) | key DOM elements present; page renders without load errors. |
| email | scaffolded round-trip | `@pytest.mark.skip("email send disabled until SMTP/SendGrid")` — imports/collects cleanly. |
| regression | `terminus()` expired-session retry | with the fix, one retry then success; no crash, no infinite loop. |
| regression | `check/umich` `else` branch | with the fix, prints via `sc.console.print`, no `TypeError`. |
| interlock | `run_program(["--all"])`, `["-a"]`, `["--for-real"]` | each raises `ForbiddenFlagError`. |

The two bug **fixes** land with their regressions (the tests would fail on today's code and pass
after the fix).

---

## 10. (reserved)

---

## 11. GMail email round-trip tier — design (deferred, scaffolded, skipped)
Cannot run today (C4: send is disabled; SendGrid unimplemented). Scaffolded now so it activates
the moment email sending lands.

- **Auth:** Gmail API + an OAuth refresh token (or a service account with domain-wide delegation)
  stored as a secret (env var / AWS Secrets Manager, matching the program's own secret story).
  No account password in the harness. Scopes: read + search (to detect bounce/rejection/
  undeliverable notices) — send happens via the program under test, not the harness.
- **Identity:** sender and recipient are the **same** GMail test account, so delivery *and* error
  notices land in one inbox. A guard asserts the recipient is that test identity (never a
  customer), mirroring §5.11.
- **Flow (when active):** program sends → poll the inbox by a unique per-run subject/token for a
  few minutes → assert receipt → scan for error notices (unknown sender / undeliverable /
  rejected / spam) → optionally load the received HTML in Playwright to check GMail rendering
  (GMail strips a subset of HTML/CSS/JS and may gate remote content / truncate long messages —
  handle those states before asserting content).
- **State today:** the test file exists and imports cleanly but is `@pytest.mark.skip`ped with a
  reason pointing at the SMTP/SendGrid milestone.

```
 [program under test] --send--> (GMail test acct) <--search-- [harness, Gmail API]
                                       │                          │
                                 error notices ──────────────► assert receipt + no errors
                                       │
                                 received HTML ─► Playwright ─► GMail-render assertions
```

---

## 12. Documentation updates (performed during implementation)
- **README.md:** add a **Testing** section — install (`uv pip install .[test]` +
  `playwright install chromium`), `run-tests` modes/tiers, live vs `--fast`, `--record`,
  `--update-goldens`, `--coverage`; **retire the two TODO bullets** ("test harness", "test
  suite") or mark the harness done.
- **CLAUDE.md:** add testing conventions that aren't obvious from the code — the importability
  seam (module loads via `importlib`, `sc.options` set by caller), the two mock seams
  (`run_terminus`, the `php` inliner), the `--all`/`--for-real` `run_program` interlock, the
  fixture/golden refresh commands, and the standing "tests accompany every change" policy.
- **tests/README.md** (new, dev-facing): layout, marks, how to write a new test in each tier,
  how to record fixtures, determinism/normalization rules.
- **docs/:** **no** testing docs added — `docs/` is end-user-only per the repo convention.
- **pyproject.toml:** add `[project.optional-dependencies] test = ["pytest", "syrupy",
  "hypothesis", "pytest-cov", "pytest-playwright"]`; `[tool.pytest.ini_options]` (markers,
  `testpaths = ["tests"]`); `[tool.coverage.run]` using `include = ["*/pantheon-sitehealth-emails"]`
  (an `include` glob, **not** `source` — the target is a single extension-less file, and `source`
  expects package names/dirs). Validate it actually reports non-zero for the in-process tiers.
  Optionally wire `COVERAGE_PROCESS_START` + `coverage.process_startup()` so the e2e/live
  subprocess runs also contribute; otherwise `--coverage` reflects in-process tiers only, which
  README/tests-README must state.

---

## 13. Acceptance criteria (the "done" bar — exact commands + observable outcomes)
1. `uv pip install .[test] && playwright install chromium` → exits 0.
2. `./run-tests --fast` → green, **no network** (unit + shim e2e + render on committed HTML).
3. `./run-tests` → green, including live read-only smoke against `its-wws-test1/2`; a grep of the
   run + the interlock test **prove** `--all`/`--for-real` were never used.
4. One passing smoke test per row of the §9 table exists (unit, integration, e2e, **golden**,
   **property**, live, render); `email` collects but is skipped.
5. The two bug fixes are in place; both regressions pass (and fail on the pre-fix code).
6. The interlock test passes: `run_program` raises `ForbiddenFlagError` for `--all`, `-a`,
   `--for-real`.
7. `./run-tests --llm` emits terse, machine-parseable output (summary counts + `FAILED` nodeids,
   no boilerplate).
8. `./run-tests --coverage` reports coverage with **no threshold gate** (in-process tiers by
   default; subprocess e2e/live coverage only if the optional `COVERAGE_PROCESS_START` plumbing
   is enabled — §5.0/§12).
9. `./run-tests --update-goldens` regenerates the §9 golden smoke snapshot; an immediate re-run
   is green.
10. Seam-refactor byte-identity check passed for `its-wws-test1` at a fixed `--date` (volatile
    bits normalized) and is recorded in the handoff notes.
11. README/CLAUDE.md/tests-README/pyproject updates present (§12).

---

## 14. Deferred / explicitly NOT in scope (Prime Directive #7: written down)
- The **full test suite** (only smoke-per-tier ships now).
- **Re-enabling SMTP; implementing SendGrid; activating the GMail email tier** (C4).
- The **large modularization refactor** and plugin/config migration (later stages). Only the
  §5.1 importability seam — and, if kept tiny, the §5.10 `recommend_plan` extraction — may be
  pulled forward, and only as necessary for testing.
- **CI/CD** — next year; the design keeps everything CI-portable so it's a workflow file later.
- **`fqdns.json` regeneration / 24-h staleness** (C5).
- **Performance / parallel-check testing.**
- **Coverage gaps accepted by C1–C4:** the `--all` aggregation + CSV/results-JSON path, real
  SMTP delivery, and any customer-facing send path are untested by design.

---

## 15. Reviewer Concerns
_(Populated only if the adversarial review leaves unresolved items after the iteration cap or a
convergence stop. Empty means the spec passed clean.)_

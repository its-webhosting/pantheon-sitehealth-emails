# RETROSPECTIVE — Modularization Campaign (I0–I14d)

Written at I14d close, 2026-07-24. Two halves: the **outcome** (§1's goal against measured
reality) and the **failure classes worth carrying forward** (each already ledgered, here
generalized so the next campaign inherits the lesson and not just the fix).

---

## Part 1 — Outcome: the goal against measured reality

CAMPAIGN.md §1's goal: modularize the 4,752-line main script into (a) a `psh/` core package,
(b) self-registering `check/` packages for every notice/section emitter, and (c) the existing
`plugin/` integrations — while the four e2e goldens stay byte-identical, the per-phase
contract is honored, and the non-U-M path keeps working. End state target: `main()` a
~250–400-line orchestrator; every U-M behavior in `umich` packages; the whole tree under the
broadened ruff+pyright gate.

### The script, before → after

**Before (I0):** one 4,752-line extension-less program. At I0 it was `git mv`-d verbatim to
`psh/_legacy.py` and re-exported, so tooling could see it; every subsequent increment carved
a slice out of `_legacy.py` into a gated `psh/` module, until I14a moved the remnant into
`psh/cli.py` and **deleted `psh/_legacy.py`**.

**After (I14d):** an 18-line thin shim (`./pantheon-sitehealth-emails`) calling
`psh.cli.main()`, plus a `psh/` core package and the `check/`/`plugin/` trees. Measured:

```
$ wc -l psh/*.py script_context.py
     7 psh/__init__.py
    69 psh/render.py
   101 psh/notice.py
   147 psh/mail.py
   201 script_context.py
   230 psh/configuration.py
   269 psh/dns_classify.py
   332 psh/gateway.py
   332 psh/modules.py
   357 psh/traffic.py
   400 psh/db.py
   433 psh/charts.py
   502 psh/plans.py
   611 psh/lifecycle.py
   668 psh/gather.py
   991 psh/cli.py
  5650 total
```

The line total is *higher* than the 4,752-line monolith, and that is expected, not
regression: the move added real type annotations (replacing the `-> (str, str, bool)`
house-style tuples), module docstrings carrying the import-cycle and seam diagrams, and the
per-module boilerplate fifteen files need that one file did not — plus the notice/section
emitters left `main()` entirely for `check/` packages, which this total does not even count.
The win the goal names is **structure**, not fewer bytes: infrastructure (`psh/`), report
content (`check/`), and data sources (`plugin/`) are now separable, importable, and
independently gated, where before they were one straight-line body.

### The `psh/` module map (Tier 1, 15 modules + `__init__`)

`cli` (orchestrator + argparse), `configuration`, `modules` (hook engine + DAG + contract
registry), `gateway`, `notice`, `db`, `traffic`, `plans`, `gather`, `charts`, `render`,
`mail`, `lifecycle` (`RunState`), `dns_classify` (the §3.1 MAY, exercised at I14a). Every
top-level def and global of the original script is now in exactly one of these (or in a
`check/`/`plugin/` package) — CAMPAIGN.md §3.1's whole-file-coverage promise.

### The check packages

Four **new** at Tier 2 (`check/pantheon` I8, `check/wordpress` I9, `check/drupal` and
`check/addon_updates` I10); `check/umich` grew (WordPress checks, the Drupal UA check, the
annual-billing hooks); `check/dns`, `check/cloudflare`, `check/pantheon_cdn_change` rode
through as untouched tenants that the ratchet flip (I14b) un-grandfathered. Eight check
packages, four plugin packages, all self-registering — no central registry to edit.

### The test count

**727** at campaign start (CAMPAIGN.md §13/§16 baseline, `./run-tests --fast`) → **1060
passed / 1 skipped** at I14d close (full suite incl. live tier), **107 snapshots**. The
growth is real coverage the moves earned: DAG fatal-condition tests, contract-registry pins,
per-check hook-seam tests, syrupy notice-render snapshots, chart-geometry tests, the
`RunState` seam tests, and — at I14c/I14d — the notice-registration AST test that made
`NoticeRegistry`'s guard load-bearing.

### The ratchet's end state

Started as **two** ruff configs (a narrow always-on PD set in `pyproject.toml`; a broad
`select=ALL` set in `ruff-broad.toml` grandfathering the remnant) plus pyright standard over
`psh/` minus `_legacy.py`. Ended (I14b/I14a) as **one** merged `[tool.ruff.lint]` in
`pyproject.toml` (`select=ALL` minus a justified ignore list, plus the `tests/**` idiom
block), `ruff-broad.toml` deleted, and pyright standard over **all of `psh/`**. Two gates,
both version-pinned (`ruff@0.15.22`, `pyright@1.1.411`) so a `uvx` cache refresh cannot move
the bar. The four PD rules (`E722`, `BLE001`, `S105`, `S106`) ran everywhere, all campaign.

### The one target missed: `main()` size

`main()` closed at **622 raw / 445 logic** lines against the **250–400** target — a *recorded
deviation* (CLOSING-AUDIT Q1), not a silent overrun. The reason: the 250–400 figure was a
planning estimate made before §3.3's stay-list was measured, and every line remaining is
stay-list content — loop control, the `continue`-crossing seams whose bodies moved but whose
control flow cannot cross a function boundary (D-i6-1, D-i8-2, D-i12-2/3/4), phase firing +
contract stuffing, and the single `except BaseException` lifecycle dispatch — plus this
file's deliberately high comment density. The honest close was to *record* the number, not to
amend the target so the answer became "yes", and not to invent extractions that would each
remove a §3.3 "stays" line and contradict the frozen architecture (PD#14). Further extraction
is a post-campaign README TODO (D-i14d-1).

**Everything else in §1 was met:** four goldens byte-identical across all fifteen increments;
the per-phase contract only ever gained keys; the non-U-M path stayed green (its own golden);
U-M behavior moved into the `umich` packages (the annual-billing and Drupal-UA relocations
even *closed* a leak — a non-U-M site no longer gets U-M advice, LEDGER I9/I10); the whole
tree is under the merged gate.

---

## Part 2 — Failure classes worth carrying forward

Each was caught and fixed inside the campaign; each is stated here as a *class*, because the
instance is closed but the pattern will recur in the next multi-session refactor.

### 1. An instrument prints a verdict it has not actually checked (PD#14)

I14c alone produced **three** of these in its own tooling: `literal_equality.py` matched
`ast.Name` only, so it never saw a `sc.Notice(...)` call and reported "identical" for every
converted `check/` file while seeing zero literals in it; a **zero-literal file counted
toward the `N/N` pass tally**; and `notice_inventory.py --gate` *excluded* every dict in
`script_context.py` rather than *requiring exactly one*, so a second hand-built render dict in
the very file that owns the projection would have passed. Same shape each time: a green check
is a claim, not evidence, until it has been shown able to go red on the condition it guards.
**Carry forward:** every instrument ships a `--self-test` that runs it against a deliberately
false input and asserts the red — the discipline `claim_check.py` was built to (its
`--self-test` runs each decision kind against a false claim and exits non-zero unless it
FAILs). An instrument that cannot be shown going red is itself an unverified claim.

### 2. A test's coverage list drifts silently

`test_hook_dag.py`'s `ALL_PACKAGES` was last touched at I4 and silently missed
`check/pantheon` (I8) and `check/wordpress` (I9), so CLAUDE.md's "loads every real
check/plugin package" was **false for three increments** and two packages' DAG declarations
went unvalidated by the test that exists to validate them. **Carry forward:** a coverage list
that must enumerate a growing set is a latent lie the moment the set grows — derive it
(walk the directory) or add a test that the enumerated list equals the discovered set. A
hand-maintained "all of X" is guilty until a test proves it complete.

### 3. A second config file cannot inherit `requires-python`

The broad ruff pass ran at ruff's **default py310 target for the entire campaign**, because
`ruff-broad.toml` — a separate file — had no `requires-python` to infer `target-version`
from, masking seven findings (UP017 ×3, FURB162, RUF100, two `tomllib` I001s) that only
surface at py312. The `pyproject.toml` "no target-version" comment was right where it lived;
the defect was that the *other* config could never benefit from it. **Carry forward:** a
duplicated configuration is a duplicated source of truth, and the two drift — here on an
invisible axis (the inferred language version) that no one reads. Prefer one config; if two
are unavoidable, pin the shared axis explicitly in both and test that they agree.

### 4. The two-binding seam trap

A module that does `from X import f` binds its **own** name, so a test patching `X.f` does not
intercept the module's call. It bit three times: `run_terminus` (patch
`psh.gateway.run_terminus` **and** `psh.gather.run_terminus`), `SMTP_SSL` (`psh.mail.SMTP_SSL`,
not `psh.SMTP_SSL`), and `finish_run` (`psh.lifecycle.finish_run`, because `abort_run` calls
it internally). Each first surfaced as a "mock that looked installed but wasn't" — a gather
test making **real** Terminus subprocess calls while appearing mocked. **Carry forward:** when
extracting a function that another module imports by name, the patch target moves with it;
grep every `from <moved-module> import <name>` and repoint or document each. The seam is where
the name is *bound*, not where it is *defined*.

### 5. A subagent's report `Write` can fail silently

Twice (I1, I14a) an implementer's report `Write` failed against a stale scratch file and was
misreported as success; both times the *task reviewer* caught it because the report content
was for the wrong task. **Carry forward:** a subagent's "done, report written" is not evidence
the file exists — verify it does, and purge stale `.superpowers/sdd/task-*-report.md`
leftovers before every dispatch. A report that was never written is the same failure class as
a test that never ran.

### 6. "Appears in a test file" is not "asserted by a test"

I14c rewrote **six** notice severities (`composer-update`, three smells, `no-primary-domain`,
`drupal7-eol`) with **nothing asserting them** — the SPEC had measured "every code appears in
at least one test file", and *appearing in* is not *asserted by*. Severity drives
`sort_notices_and_subject`, so a silent demotion reorders a real report and changes its email
subject prefix ("Action Required" → "Action Recommended") with every test green. The bitter
part: the review that finally caught it had *itself* just named the class one finding earlier
(`fix-the-class-not-the-instance`). **Carry forward:** coverage measured by grep is coverage
of the *token*, not the *behavior*; when a change touches a value that drives output, the
test must assert the value, and the proof is the test going red when the value is flipped —
not the token being present somewhere in `tests/`.

---

*The architecture that shipped is the architecture CLAUDE.md describes in present tense;
`LEDGER.md` holds how it was reached, and `CLOSING-AUDIT.md` holds the evidence it is done.*

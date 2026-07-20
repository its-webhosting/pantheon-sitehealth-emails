# SPEC — Increment I4: `psh/modules.py` (hook engine, DAG, contract registry, `run_finish`)

**Campaign:** `development/2026-07-17-modularization-campaign/` — this spec cites
`CAMPAIGN.md` by section number and re-derives nothing (CAMPAIGN.md preamble). Scope
authority: §11 row I4. Design authority for the DAG: §4. Module map: §3.1. Per-increment
obligations: §7. Behavior bar: §8. Invariants: §9. Ratchet: §13.

**Read first (per §7):** `CAMPAIGN.md`, `LEDGER.md` (through I3), `CLAUDE.md`,
`BLOCKMAP.md` rows B2/B4/B7/B27/B28/B31/B37/B52/B59/B60, `prompts/directives.md`,
`prompts/implementation-standards.md`.

## Glossary (delta over CAMPAIGN.md's; terms used exactly once per concept)

- **Engine** — the hook machinery: `PHASES`, `_valid_hook_name`, `add_hook`,
  `invoke_hooks` (today in `script_context.py`), plus the new DAG validation.
- **Registry** — the machine-readable per-phase contract: phase → the `site_context`
  keys core stuffs *first at that phase* (§4 "Contract registry").
- **Declaration** — a hook's `consumes` and `produces` entries (each a possibly-empty
  list of contract-key names).
- **Stuffer** — a pure helper that writes exactly one phase's registry keys onto the
  `SiteContext` (existing precedent: `dns_classify.stuff_dns_contract`).
- **Bare phase** — a name in `PHASES`. **Dotted event** — a plugin-defined `a.b.c` name
  (unchanged semantics, §4).

## 1. Scope (exhaustive) and non-scope

In scope (§11 row I4):

1. **Move** `find_modules` (14 lines, `psh/_legacy.py:526–539`; the "935–950" in §11 is
   the pre-campaign line range, drifted per BLOCKMAP preamble) and the engine (from
   `script_context.py`) into a new `psh/modules.py`. Re-import pattern as I2/I3.
2. **`run_finish` phase** appended to `PHASES`; fired inside `finish_run()` before
   anything is torn down or written.
3. **Declarations required on every hook**; retrofit all 12 in-repo registrations.
4. **DAG validation** with the five fatal conditions of §4, each a named error, each
   demonstrably red in tests (PD#14).
5. **Topological invoke order** (producers before consumers; registration order breaks
   ties — today's DAG is edgeless, see §5 below, so observed order is unchanged).
6. **Contract registry** in `psh/modules.py` + stuffer extraction so core's stuffing is
   registry-checked in tests (§4; extraction sanctioned by
   `prompts/implementation-standards.md` § Test discipline).
7. **Ratchet:** `psh/modules.py` gated from birth; **un-grandfather `script_context.py`**
   (delete from `ruff-broad.toml` `extend-exclude` — its own comment assigns this to I4).
8. Docs/CLAUDE.md/memory/ledger updates (§7 obligations 6–8).

NOT in scope: B2/B4 module-loading loops stay in `main()` (§11 row I4 does not list
them; §3.1 assigns them to `psh/modules.py` eventually — they move with `main()`'s
final form, I13; **ledger note**). No `[Check.*]` config sections (I8+). No new §6
type for hooks — targets remain dicts (a `Hook` dataclass would amend §6's exhaustive
table for no consumer benefit; registration call sites stay minimal-churn). No pyright
scope widening (stays `psh/` minus `_legacy.py`). No golden/fixture changes (Invariants
1, 10).

## 2. Architecture decisions (each with why; deviations flagged for the ledger)

### D-i4-1: the mutable `hooks` dict STAYS in `script_context.py`

§3.1 moves the engine *functions*; it names `PHASES` but not the `hooks` state dict.
The dict stays put because: (a) CLAUDE.md defines `script_context` as the home of
cross-cutting mutable state; (b) §3.4 forbids new module-level mutable state in `psh/`
modules (review criterion since I2); (c) `tests/conftest.py::reset_sc` **rebinds**
`sc.hooks` around every test — a second home in `psh.modules` would desync engine from
tests the first time anything rebound one and not the other, a silent instrument defect
(PD#14). The engine reads it as `sc.hooks` at call time. **Ledger note, not an
amendment** — §3.1's engine list is satisfied; state placement follows existing §3.4 +
CLAUDE.md rules.

### D-i4-2: import direction and the cycle

`script_context.py` re-exports `PHASES`, `add_hook`, `invoke_hooks` via a top-of-file
`from psh.modules import PHASES, add_hook, invoke_hooks` (module-level import → names
become module attributes automatically; the I3 amendment-3 precedent for
`Notice`/`Severity`, recorded in LEDGER I3 deviation 3). Therefore `psh/modules.py`
MUST NOT import `script_context` at module level (importing `psh.modules` first would
hit a partially-initialized from-import and die with `ImportError`; `psh.notice`'s
docstring states the same rule for itself). Engine functions do a **function-level**
`import script_context as sc` (`# noqa: PLC0415` with this reason inline) to reach
`sc.hooks`, `sc.console`, `sc.debug`. `find_modules`, the registry, the validator's
pure core, and the stuffers need no `sc` at all.

```
        script_context.py  ──(module-level from-import: PHASES/add_hook/invoke_hooks)──►  psh/modules.py
                ▲                                                                            │
                └────────────(function-level import, call-time only: hooks/console/debug)────┘
   checks/plugins import ONLY sc (Invariant 9); sc.add_hook etc. keep resolving unchanged
```

### D-i4-3: declarations required on ALL hooks, dotted events declare empty

`consumes`/`produces` are required on **every** registration — §4 condition 5 says "any
hook", "no legacy mode". For dotted events the *semantics* stay unchanged (§4: not
ordered, invoked by their owner) but the schema is uniform: a dotted-event hook MUST
declare `consumes=[]` and `produces=[]`, and a **non-empty** declaration on a dotted
event is fatal (contract keys are phase-anchored; a dotted event has no phase position,
so a non-empty declaration is unvalidatable and therefore a lie — PD#1). **Ledger
note** (interprets "unchanged" as invocation semantics, not registration schema).

### D-i4-4: condition 5 enforces at `add_hook` time; conditions 1–4 at validation

`add_hook` already owns registration-time fatals (unknown phase → `console.print` +
`sys.exit(1)`). A missing/malformed declaration (absent key, non-list, non-str member,
or non-empty on a dotted event) fails there, in the same style — the error names the
offending hook at its registration site, the loudest possible locality. This is
*stricter placement* of §4's condition 5, not a relaxation (nothing can enter `sc.hooks`
undeclared; `tests/integration/test_plugin_cloudflare_init.py` already pins that
registration goes through `add_hook`, not raw dict appends). Conditions 1–4 need the
complete producer set and run in `validate_hooks()` at module-load completion. **Ledger
note.**

### D-i4-5: `validate_hooks()` raises named errors; `main()` catches and exits

`psh/modules.py` defines `HookDagError(Exception)` and four named subclasses (PD#2), one
per condition 1–4 — see the canonical table in §4 below. `main()` calls
`validate_hooks()` immediately after the check-import loop (B4) inside
`try/except HookDagError` → `sc.console.print` (with `rich.markup.escape` on the
message — hook names come from module authors, Invariant 6) + `sys.exit(1)`. Raising
named classes keeps the validator a pure, precisely testable unit; the catch site keeps
the operator experience a clean fatal line, matching every other startup fatal.

### D-i4-6: invoke order is computed per invocation by a pure helper

`invoke_hooks` calls a pure `ordered_hooks(hook_name, hooks_list) -> list` each time:
Kahn's algorithm over produces→consumes edges among same-phase hooks, ready-queue in
registration order (deterministic, explicit — no `graphlib.TopologicalSorter`, whose
tie order is not contractually registration-stable). §4's diagram shows "topo order
stored"; computing per call is behaviorally identical (same inputs → same order),
removes a stale-cache failure mode (tests register hooks without running validation),
and costs O(hooks²) on lists of ≤4. **Ledger note** (mechanism choice within §4's
observable contract). Dotted events and edgeless phases yield registration order —
byte-identical behavior today.

### D-i4-7: `run_finish` fires with no arguments until I13

§4 says the phase receives the `RunState` — a type I13 introduces (§6). I4 fires
`sc.invoke_hooks("run_finish")` as the **first statement** of `finish_run()` (before the
session close/engine dispose teardown and all artifact writes — the §4 placement rule,
applied to the earliest point so future hooks see the run still intact). No consumer
exists (like `site_pre_render` at its introduction); I13 adds the `RunState` argument
before any consumer appears, so the signature change is safe. **Ledger note.**

## 3. Deliverable A — `psh/modules.py` (new file; gated from birth)

Contents (exhaustive):

| Item | From | Notes |
|---|---|---|
| `find_modules(module_type)` | `psh/_legacy.py:526–539` | verbatim move; `os`/`stat` imports; `_legacy` re-imports it |
| `PHASES` | `script_context.py:46–55` | tuple gains `'run_finish'` as its last element; move the phase-semantics comment block with it and extend it (run_finish: once per run, inside `finish_run`, before artifacts; fired on completed AND aborted runs — both call `finish_run`) |
| `_valid_hook_name` | `script_context.py:73–74` | verbatim |
| `add_hook(hook_name, target)` | `script_context.py:77–82` | + declaration enforcement (D-i4-4); state via `sc.hooks` (D-i4-1/2) |
| `invoke_hooks(hook_name, *args, **kwargs)` | `script_context.py:85–92` | + `ordered_hooks` ordering (D-i4-6); keeps the two `debug` lines verbatim (levels unchanged) |
| `ordered_hooks` | new | pure; Kahn + registration-order ready queue |
| `validate_hooks()` | new | conditions 1–4 (§4 table below) over `sc.hooks` + `CONTRACT` |
| `HookDagError` + 4 subclasses | new | §4 table below |
| `CONTRACT` | new | §5 below |
| `stuff_traffic_contract`, `stuff_gather_contract` | extracted from `main()` (B28/B37 stuffing lines) | §5 below |

`script_context.py` keeps: `hooks = {phase: [] for phase in PHASES}` (rebuilt from the
imported `PHASES`), and everything else it has today. The engine defs and the `PHASES`
literal are **deleted** from it (moved, not copied — one copy, PD's DRY preference).

Module docstring MUST carry the D-i4-2 import-direction diagram (PD#8: the flow spans
`script_context` ↔ `psh.modules`, non-local by definition).

## 4. Deliverable B — DAG validation (canonical fatal-condition table)

Phase-position notation: `pos(phase)` = index in `PHASES`; a key's **owner phase** =
the phase where the registry lists it, or the phase of the hook that produces it.

| # (§4) | Condition | Where enforced | Error (all in `psh.modules`) |
|---|---|---|---|
| 1 | a consumed key no registry phase and no hook produces | `validate_hooks()` | `UnproducedKeyError(HookDagError)` |
| 2 | two producers of one key — hook+hook, or hook producing a registry key | `validate_hooks()` | `DuplicateProducerError(HookDagError)` |
| 3 | cycle among same-phase hooks | `validate_hooks()` | `HookCycleError(HookDagError)` |
| 4 | consumed key's owner phase is later than the hook's phase | `validate_hooks()` | `LaterPhaseKeyError(HookDagError)` |
| 5 | missing/malformed declaration (incl. non-empty on dotted event) | `add_hook` | `console.print` + `sys.exit(1)` (house style of its sibling unknown-phase fatal, D-i4-4) |

Every error message names the offending hook(s) by their `name` entry, the phase, and
the key(s) — the operator must be able to act without reading source (PD#1/#5).
Consuming a key owned by an **earlier** phase than the hook's is legal (the
`check.umich.cloudflare_cms` case: consumes `fqdns_behind_cloudflare`, owned by
`site_post_dns`, from `site_post_gather`).

`main()` wiring (the only `_legacy.py` edits, all small): the `except HookDagError`
call site after B4 (D-i4-5); the B28/B37 stuffing lines replaced by the two stuffer
calls; `sc.invoke_hooks("run_finish")` opening `finish_run()`; the `find_modules` def
deleted and re-imported.

## 5. Deliverable C — contract registry + stuffers

```python
# psh/modules.py — authoritative machine-readable form of CLAUDE.md's per-phase table.
# Keys FIRST guaranteed at each phase; availability is cumulative (site_pre_render
# guarantees everything above it and adds nothing).
CONTRACT: dict[str, tuple[str, ...]] = {
    "setup": (),
    "site_pre": (),
    "site_post_traffic": ("traffic_rows", "start_date", "end_date"),
    "site_post_dns": (
        "domains", "custom_domains", "primary_domain", "main_fqdn",
        "fqdns_behind_cloudflare", "fqdns_not_behind_cloudflare", "not_in_dns",
        "behind_cloudflare_not_proxied", "proxied_in_multiple_zones", "dns_transient",
    ),
    "site_post_gather": (
        "framework", "site_url", "wordpress_version", "drupal_version",
        "wordpress_plugins", "drupal_modules",
    ),
    "site_pre_render": (),
    "run_finish": (),
}
```

(Verbatim from CLAUDE.md's table per §4; the base `site`/`notices`/`sections`/
`attachments` keys are `SiteContext` construction, not contract keys, and hooks do not
declare them.)

Stuffers (extracted so "core's stuffing code is checked against it in tests", §4 —
without them the only cover is the goldens, which cannot name a missing key):

- `stuff_traffic_contract(site_context, traffic_rows, start_date, end_date)` — the
  three B28 assignments, verbatim.
- `stuff_gather_contract(site_context, framework, site_url, wordpress_version, plugins,
  drupal_version, mods)` — the six B37 assignments **including** the
  `isinstance(plugins, list)` / `isinstance(mods, dict)` normalizations and their
  comments, verbatim.
- `dns_classify.stuff_dns_contract` already exists and is NOT moved; a test pins its
  key set against `CONTRACT["site_post_dns"]`.

Registry-vs-stuffer tests are registry-driven (`set(written keys) ==
set(CONTRACT[phase])`) so adding a key in one place and not the other goes red.

## 6. Deliverable D — declaration retrofit (exhaustive; all 12 in-repo registrations)

The implementer MUST re-verify each `consumes` list against the hook body before
writing it (spec-time verification below was by direct read on 2026-07-20; §7
obligation 4). `produces=[]` for every hook — **no in-repo hook publishes a contract
key today**, hence the edgeless DAG and unchanged invoke order (D-i4-6).

| Registration (file) | Phase | `consumes` |
|---|---|---|
| `plugin/cloudflare/__init__.py` ips | `setup` | `[]` |
| `plugin/cloudflare/__init__.py` fqdns | `setup` | `[]` |
| `plugin/umich/__init__.py` portal | `setup` | `[]` |
| `check/cloudflare/__init__.py` egress | `setup` | `[]` |
| `check/cloudflare/__init__.py` cache | `site_post_dns` | `["fqdns_behind_cloudflare", "primary_domain"]` *(corrected during Task 3: the spec-time grep pattern `site_context[` missed the `.get("primary_domain")` read at `cache.py:233`; the implementer's mandated re-verification caught it — ledger-recorded)* |
| `check/dns/__init__.py` emit_dns_notices | `site_post_dns` | `["dns_transient", "fqdns_not_behind_cloudflare", "behind_cloudflare_not_proxied", "proxied_in_multiple_zones", "not_in_dns"]` |
| `check/pantheon_cdn_change/__init__.py` | `site_post_dns` | `["custom_domains"]` |
| `check/umich/__init__.py` sitelens setup | `setup.umich.portal` (dotted) | `[]` |
| `check/umich/__init__.py` sitelens urls | `site_pre` | `[]` |
| `check/umich/__init__.py` sitelens scores | `site_pre` | `[]` |
| `check/umich/__init__.py` cloudflare_cms | `site_post_gather` | `["fqdns_behind_cloudflare", "framework", "wordpress_plugins", "drupal_version", "drupal_modules"]` |
| *(no 12th `add_hook` — the 12th registration surface is `plugin/umich`'s `sc.substitutions.append`, which is not a hook and is untouched)* | | |

Test-side registrations updated in the same change (condition 5 has no legacy mode):
`tests/integration/test_hooks_phases.py`, `tests/integration/test_terminus_seam.py`,
`tests/integration/test_plugin_cloudflare_init.py` (assertions only — the package's own
retrofitted declarations flow through its `_load_init`), and any other `add_hook`
caller a repo-wide grep finds at implementation time.

## 7. Deliverable E — ratchet (§13)

- `psh/modules.py`: born gated. `uvx ruff check --config ruff-broad.toml psh/modules.py`
  → clean; pyright standard (already `include=["psh"]`) → 0 errors.
- **Un-grandfather `script_context.py`**: delete its line (and its comment) from
  `ruff-broad.toml` `extend-exclude`. Findings measured 2026-07-20 on the current file:
  `I001` (import sort), 2× `SIM401` (`.get` for the `order` lookups in
  `add_notice`/`add_news_item`), 2× `PLR1714` (`order in ('prepend', 'first')` merges)
  — all mechanical and behavior-preserving; none touch the engine (which leaves the
  file anyway). Expected post-move additions: `F401` on the re-exported
  `add_hook`/`invoke_hooks` (noqa with re-export reason, exactly like line 9's
  `Severity` noqa). Disposition-corrections, if any, go in the ledger (I3 precedent).
- Expected out-of-gate minimal typing fix (I3 precedent, ledger-recorded):
  `script_context.hooks` gains the annotation `dict[str, list[dict[str, Any]]]` if
  pyright standard needs it to check `psh/modules.py`'s call-time access; nothing else
  in `script_context.py` is retyped.
- No `ruff-broad.toml` `ignore` additions (that would be a §13 amendment). `# noqa`
  only with inline reasons (`PLC0415` cycle note, `F401` re-exports, `S101` if pyright
  narrowing needs an assert — same set I3 sanctioned).

## 8. Behavior bar & invariants applied (§8/§9 — what this increment may and may not change)

- Goldens: byte-identical (Invariant 1). Nothing in this increment renders differently:
  declarations are inert metadata, the DAG is edgeless (order unchanged), stuffers are
  verbatim extractions, `run_finish` has no consumer, and `invoke_hooks`'s only output
  is pre-existing `debug` lines at unchanged levels.
- Artifact structure: unchanged (§8 row 2) — `run_finish` fires before writes and
  writes nothing.
- stdout MAY improve (§8): the new fatal messages are new output on new failure paths
  only.
- Contract: additions none; existing keys untouched (Invariant 2). `run_finish` is a
  phase addition, sanctioned by §4 explicitly.
- Invariants 4 (lifecycle), 6 (escape untrusted text in the new fatals), 9 (no `sc`
  name removed — `sc.PHASES`/`sc.add_hook`/`sc.invoke_hooks`/`sc.hooks` all keep
  resolving) hold by construction; the façade test pins them.
- Config keys: none added/changed (§5 of CAMPAIGN.md — `[Check.*]` starts at I8).

## 9. Seams under test (named and agreed here — exhaustive; PD spec bar)

| Behavior | Seam | Tier |
|---|---|---|
| `add_hook`/`invoke_hooks`/ordering/declaration fatals | `psh.modules` functions directly (pure state via `reset_sc`'s `sc.hooks`) | unit/integration (`test_hooks_phases.py` grows; SystemExit + `recording_console`) |
| Each DAG fatal condition 1–4 red | `psh.modules.validate_hooks` with synthetic `sc.hooks` contents | unit (`tests/unit/test_hook_dag_validation.py`, new) |
| Topo order + registration tie-break | `psh.modules.ordered_hooks` (pure) | unit (same file) |
| "future changes can never make the DAG impossible" (§4) | load ALL real check/plugin packages (checkload probe-package pattern + enabling config: `[UMich].enabled`, `[Cloudflare].enabled` + `[Cloudflare.cachecheck]` with `account_id`/`list_name`) then `validate_hooks()` | integration (`tests/integration/test_hook_dag.py`, new, permanent) |
| Registry ↔ stuffers agree | `psh.modules.stuff_traffic_contract`/`stuff_gather_contract`, `dns_classify.stuff_dns_contract` vs `CONTRACT` | unit (`tests/unit/test_contract_registry.py`, new) |
| `run_finish` fires before artifacts, on normal and abort paths | `finish_run()` in-process (existing `tests/integration/test_finish_run.py` harness; probe hook registered via `add_hook`) | integration |
| Retrofitted packages still register (with declarations) | existing per-package init tests (`test_plugin_cloudflare_init.py` etc.) | integration (updated) |
| Whole-program unchanged | the four e2e goldens | e2e (untouched, must stay green) |

No new subprocess/network/DNS paths → no new shims. `find_modules` keeps its existing
behavior; its move is covered by the e2e tier (which fails loudly if module discovery
breaks — the `_CWD_ASSETS` lesson) plus a small unit test if one exists already
(implementer greps; none is required to be added for a verbatim move).

Test-first applies to every new behavior (declaration fatals, each validator condition,
ordering, registry tests, `run_finish` firing); the moves themselves are
behavior-preserving relocations covered by the existing suite staying green.

## 10. Documentation & memory obligations (same change, §7)

- CLAUDE.md: hook-engine location (`psh/modules.py`, import-back + re-export mechanics),
  `add_hook` declaration requirement + fatal conditions, `run_finish` in the phase list,
  registry-is-authoritative line on the contract table ("the machine-readable copy in
  `psh/modules.py` `CONTRACT` is authoritative; this table is its prose rendering"),
  prose that this task obsoletes deleted (report the line-count delta).
- `ruff-broad.toml` comment for `script_context.py` removed with its exclude line.
- Memory: update `modularization-campaign.md` progress note; new/updated memory for the
  engine's new home + declaration requirement.
- `LEDGER.md`: the I4 entry with the seven ledger notes flagged above (D-i4-1, D-i4-3,
  D-i4-4, D-i4-6, D-i4-7, B2/B4 deferral, ratchet dispositions/corrections).

## 11. Acceptance (commands run and output pasted into this file at close — never summarized)

Run 2026-07-20 at increment close (HEAD = `1f2a6af`, base `d46f56d`):

1. `./run-tests --fast --llm`:

```
LLM_SUMMARY passed=780 failed=0 error=0 skipped=1 xfailed=0 xpassed=0
27 snapshots passed.
```

(Baseline at I3 close was 761 passed — I4 added 19 tests: run_finish probe + EXPECTED_PHASES,
2 declaration fatals, 6 contract-registry tests, 9 DAG-validation/ordering tests, plus the
permanent `test_hook_dag.py`, net of the `test_plugin_umich_portal.py` registration rework.)

2. `./run-tests --llm` — **live tier ran** (Terminus token present in this environment):

```
All checks passed!
All checks passed!
0 errors, 0 warnings, 0 informations
LLM_SUMMARY passed=782 failed=0 error=0 skipped=1 xfailed=0 xpassed=0
27 snapshots passed.
782 passed, 1 skipped in 36.53s
```

(The 1 skip is `test_db_credentials.py`'s `importorskip("MySQLdb")` on this sqlite-only
install — same as I2.)

3. `git diff d46f56d -- tests/e2e/__snapshots__/ | wc -l` → `0` (four goldens
byte-identical, Invariant 1).

4. `uvx ruff check --config ruff-broad.toml psh/modules.py script_context.py` →
`All checks passed!`

5. `uvx ruff check .` (narrow set, whole tree) → `All checks passed!`

6. pyright via the `./run-tests` gate → `0 errors, 0 warnings, 0 informations` (line 3 of
the item-2 output above).

7. Red-demonstration evidence for conditions 1–5: task reports
`.superpowers/sdd/task-3-report.md` (condition 5: two `DID NOT RAISE SystemExit` reds,
independently reproduced by the Task 3 reviewer) and `task-5-report.md` (conditions 1–4:
`AttributeError` red before `validate_hooks` existed, then per-condition
`pytest.raises(<named error>)` green; the Task 5 reviewer re-derived the reds from
`git show`). The Task 2 reviewer additionally mutation-tested the run_finish
before-artifacts probe (moved the invoke after the writes → `assert [True] == [False]`).

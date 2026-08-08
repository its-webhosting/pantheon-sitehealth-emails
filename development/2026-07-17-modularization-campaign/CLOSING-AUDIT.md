# CLOSING-AUDIT — Modularization Campaign (I0–I14d)

Answers to CAMPAIGN.md §17's nine closing-audit questions. Each answer pastes the command
that produced it — an unrun audit is a claim, not evidence (PD#14). Run 2026-07-24 at I14d
close, from the repo root, on the tree that becomes the closing commit.

> Governing: CAMPAIGN.md §17 (the nine questions, verbatim), SPEC §2.6 (the expected answer
> shapes). An unexpected answer is a finding reported here, not smoothed over.

---

## Q1 — Is `main()` within 250–400 lines, and does everything left match §3.3?

**Answer: NO on the line count — a *recorded deviation*, not an oversight — and YES on the
stay-list.** `main()` closed at **622 raw / 445 logic** lines, above §3.3's 250–400 target.
Everything remaining is §3.3 stay-list content; no un-extracted work sits in it. This is
recorded, not amended (the target is a planning estimate that did not price the ledgered
"stays"-list call-site decisions — D-i6-1, D-i8-2, D-i12-2/3/4 — plus this file's comment
density; LEDGER I13 flagged it for this audit). Further extraction is a post-campaign
README TODO (D-i14d-1), not a close-time task: extracting during the increment specced as
*closing* re-opens golden risk for a target estimated before §3.3's stay-list was measured.

**Measurement (the SPEC §2.6 / brief AST snippet):**

```
$ python - <<'PY'
import ast, pathlib
t = ast.parse(pathlib.Path("psh/cli.py").read_text())
m = next(n for n in t.body if isinstance(n, ast.FunctionDef) and n.name == "main")
raw = m.end_lineno - m.lineno + 1
body = pathlib.Path("psh/cli.py").read_text().splitlines()[m.lineno-1:m.end_lineno]
logic = sum(1 for line in body if line.strip() and not line.strip().startswith("#"))
print(f"main() at psh/cli.py:{m.lineno}-{m.end_lineno}  raw={raw} logic={logic}")
PY
main() at psh/cli.py:370-991  raw=622 logic=445
```

**Stay-list walk (§3.3, exhaustive) — every item present in `main()`, nothing else is:**

| §3.3 item | Present in `main()` as |
|---|---|
| Config/arg bootstrap ordering (B1–B8, the two-pass substitution *order*) | verbatim config read; `import_packages("plugin"/"check")`; `validate_hooks()`; the resume-from / create-tables / sites-or-all arg guards; `--update-cloudflare-fqdns` guard; verbose setup; `build/` setup |
| Overage constants + date window (B9, B13 part) | the overage-constant reads feeding `PlanCatalog.from_config`; the B46 op-window hoist above `recommend_plan` (D-i7-6) |
| Site-loop skeleton (skips, banner, sorted order, resume filter — B14–B18, B20, B25, B42) | `for site_name in site_names`; the portal / not-requested / Sandbox / unknown-plan skips; `sites_from_resume_point`; the `envs` guard; `--update` / `--import-older-metrics` continues |
| Phase firing + contract stuffing (B27, B28, B31, B37, B52) | `stuff_envs_contract` + `invoke_hooks("site_pre")`; `stuff_traffic_contract` + `invoke_hooks("site_post_traffic")`; `classify_domains` + `stuff_dns_contract` + `invoke_hooks("site_post_dns")`; the gather threading + `stuff_gather_contract` + `invoke_hooks("site_post_gather")`; `stuff_plans_contract` + `invoke_hooks("site_pre_render")` |
| The B48 smell-notice **emission** call | `build_smell_notices(site["name"], site_context["wp_smell"], …)` (builder in `psh/gather.py`; emission stays behind the `--only-warn` gate — LEDGER I10 amendment 1) |
| Notice sort + subject (B50 minus billing) | `sort_notices_and_subject(site_context, report)` |
| The `try` / `except BaseException` lifecycle dispatch (B59–B60 call sites) | the single `except BaseException` flush → `abort_reason` / `abort_run` / `finish_run` |

Every heavy body it *calls* lives in a `psh/` module (`update_site_traffic`,
`load_site_traffic`, `resolve_plan_name`, `recommend_plan`, `gather_wordpress` /
`gather_drupal`, `build_chart`, `render_report`, `resolve_recipients`,
`assemble_message`, `open_database`, `import_packages`) — `main()` threads shaped locals
and controls the loop, which is exactly the §3.3 orchestrator role. The overage is
stay-list content, not un-extracted logic.

**Post-campaign TODO (D-i14d-1):** `README.md` "Extract further from `main()` toward
CAMPAIGN.md §3.3's 250–400-line target **(post-campaign)**".

### Corrections and discharge (2026-08-07, post-campaign)

Four items. Items **1 and 4** are **discharges** — answers that were true at I14d and have
since been overtaken. Items **2 and 3** are **corrections of this document's own prose**: they
were wrong when written, never true, and are not changes to CAMPAIGN.md §3.3, which was
right. (The §3.3 amendments the same increment did
make are listed in CAMPAIGN.md §3.3 A1–A5 and in LEDGER "Amendments — §3.3 stay-list
(2026-08-07, post-campaign)".)

**1. D-i14d-1 is DISCHARGED, and the "NO on the line count" answer is superseded.** The
2026-08-07 main-extraction increment (`development/2026-08-07-main-extraction/SPEC.md`) —
**eight code+spec commits** (`5f58192`, `284a8f9`, `b106f80`, `9f44959`, `51cf48a`,
`d5063dd`, `c47807b`, `ecae81a`) **plus the documentation commits that amend these campaign
records** (`0d749ce`, `f069f70`, and the final-review fix wave that followed them) — moved
six stage bodies out of `main()`, goldens byte-identical. Re-measured with
this section's own snippet, on the post-increment tree:

```
$ python - <<'PY'
import ast, pathlib
t = ast.parse(pathlib.Path("psh/cli.py").read_text())
m = next(n for n in t.body if isinstance(n, ast.FunctionDef) and n.name == "main")
raw = m.end_lineno - m.lineno + 1
body = pathlib.Path("psh/cli.py").read_text().splitlines()[m.lineno-1:m.end_lineno]
logic = sum(1 for line in body if line.strip() and not line.strip().startswith("#"))
print(f"main() at psh/cli.py:{m.lineno}-{m.end_lineno}  raw={raw} logic={logic}")
PY
main() at psh/cli.py:618-1071  raw=454 logic=318
```

622 raw / 445 logic → **454 raw / 318 logic**. **318 is inside the 250–400 target on the
logic measure**; 454 is still 54 above it on the raw measure. The 454 breaks down as
**318 logic, 72 comment, 64 blank** — comments are the larger share of the gap between
the two measures, though not all of it, and they are the same thing this answer named as
the overage's cause at close. The README TODO was struck in commit `5b92ee1` (2026-08-07 06:54, before the
increment's own commits), so the discharge is recorded here and in the ledger rather than in
`README.md`. Verification that the TODO is gone greps its **prose**, not its decision ID —
`grep -n 'D-i14d-1' README.md` returns nothing **before** the strike too, and a check that
answers the same before and after the event it checks for is not a check (PD#14):

```
$ grep -n 'Extract further from' README.md            # no match  (the TODO is gone)
$ git show 5b92ee1^:README.md | grep -c 'Extract further from'
1                                                     # it was there
```

**2. The stay-list walk's "Phase firing + contract stuffing" row over-claimed twice.** Its
§3.3 row names **B27, B28, B31, B37, B52**, and the walk discharged it partly with *"the
gather threading + `stuff_gather_contract` + `invoke_hooks("site_post_gather")"`*. The
**gather threading was never stay-list content**: it is B33 / B34 (residue) / B35 (residue)
/ B36, none of which §3.3 lists. Only `stuff_gather_contract` + `invoke_hooks` — i.e. B37 —
belongs in that cell. The threading has since moved to `psh.gather.gather_framework`
(commit `9f44959`) and needed no §3.3 amendment for exactly this reason.

**3. The same row lumped `classify_domains` in with `stuff_dns_contract`.**
`classify_domains` is **B29**, which is *not* on the stay-list; `stuff_dns_contract` +
`invoke_hooks("site_post_dns")` is **B31**, which is. B29 has since moved into
`psh.cli.fetch_site_domains` (commit `51cf48a`) with no §3.3 amendment; B31 got one (A5),
narrowing it to the seam. Writing the two under one bullet is what made a moved block look
like a stay-list violation and an amended one look untouched.

**4. The stay-list walk's B48 smell-notice *emission* row is DISCHARGED — that emission is no
longer in `main()` at all.** The row reads *"The B48 smell-notice **emission** call |
`build_smell_notices(site["name"], site_context["wp_smell"], …)` (builder in `psh/gather.py`;
emission stays behind the `--only-warn` gate — LEDGER I10 amendment 1)"*. Every clause of it was
true at I14d and none of the first three is true now. On 2026-08-07, post-campaign, the three
smell notices moved into a new `check/smells/` package
(`development/2026-08-07-smell-notice-relocation/SPEC.md`, commit `8bc6dff`): the builder is
`check/smells/notices.py::build_smell_notices`, the emission is
`check/smells/hook.py::emit_smell_notices` registered at **`site_pre_render`** with
`consumes: ['wp_smell', 'drush_smell', 'composer_smell']` / `produces: []`, and `main()` calls
neither:

```
$ grep -c build_smell_notices psh/cli.py psh/gather.py
psh/cli.py:0
psh/gather.py:0
```

The one clause that survives is the `--only-warn` exclusion, and it survives **for a different
reason**: it is now a property of the *phase* rather than of the call's position — `main()`
`continue`s for `--only-warn` above the `site_pre_render` firing, so a warning-only run still
emits no smell rows, identically and not merely similarly. CAMPAIGN.md was amended in the same
increment (§3.2 rewritten, §3.3's stay-list item removed, §3.1's module map row corrected);
the narrative, the reason the `mutates` edge kind was **not** built, and the `sc.debug`
observability delta found during implementation are in LEDGER *"2026-08-07 — post-campaign:
the B48 smell-notice emission → `check/smells/`"*. Discharged here rather than rewritten in
place, per the rule the next paragraph states.

**Everything else in the walk stands *as a record of the I14d tree*** — including the
answer's substantive claim, that the remainder of `main()` is stay-list content and not
un-extracted logic. Read in the present tense it would mislead: several of its cells name
code the 2026-08-07 **main-extraction** increment has since moved into helpers `main()` calls (the arg guards
→ `validate_options`; the Sandbox and unknown-plan skips → `resolve_site_plan`;
`sites_from_resume_point` → `resolve_site_roster`). This whole document is a dated
snapshot — *"Run 2026-07-24 at I14d close"* — and is corrected, never rewritten;
`CLAUDE.md` is where the architecture is described in the present tense.

---

## Q2 — Has every DAG fatal condition been demonstrated red at least once?

**Answer: YES — all five.** Conditions 1–4 are `validate_hooks()`'s named
`HookDagError` subclasses (`tests/unit/test_hook_dag_validation.py`); condition 5 (a
missing/malformed `consumes`/`produces` declaration) is enforced at **`add_hook`** time,
not `validate_hooks` — CLAUDE.md was corrected on this in Task 3 — so its demonstration
lives in `tests/integration/test_hooks_phases.py`.

| Fatal condition (CAMPAIGN §4) | Enforced at | Test |
|---|---|---|
| 1. Consumed key nothing produces | `validate_hooks` (`UnproducedKeyError`) | `test_hook_dag_validation.py::test_condition_1_unproduced_consumed_key_is_fatal` |
| 2. Two producers of one key | `validate_hooks` (`DuplicateProducerError`) | `test_hook_dag_validation.py::test_condition_2_two_hook_producers_is_fatal` and `::test_condition_2_hook_producing_a_core_registry_key_is_fatal` |
| 3. Same-phase cycle | `validate_hooks` (`HookCycleError`) | `test_hook_dag_validation.py::test_condition_3_same_phase_cycle_is_fatal` |
| 4. Key first produced in a later phase | `validate_hooks` (`LaterPhaseKeyError`) | `test_hook_dag_validation.py::test_condition_4_key_first_produced_in_a_later_phase_is_fatal` |
| 5. Missing/malformed `consumes`/`produces` | **`add_hook`** (fatal `SystemExit`; no legacy mode) | `test_hooks_phases.py::test_add_hook_missing_declarations_is_fatal` |

```
$ python -m pytest tests/unit/test_hook_dag_validation.py \
      tests/integration/test_hooks_phases.py::test_add_hook_missing_declarations_is_fatal -v
tests/unit/test_hook_dag_validation.py::test_condition_1_unproduced_consumed_key_is_fatal PASSED [ 10%]
tests/unit/test_hook_dag_validation.py::test_condition_2_two_hook_producers_is_fatal PASSED [ 20%]
tests/unit/test_hook_dag_validation.py::test_condition_2_hook_producing_a_core_registry_key_is_fatal PASSED [ 30%]
tests/unit/test_hook_dag_validation.py::test_condition_3_same_phase_cycle_is_fatal PASSED [ 40%]
tests/unit/test_hook_dag_validation.py::test_condition_4_key_first_produced_in_a_later_phase_is_fatal PASSED [ 50%]
tests/unit/test_hook_dag_validation.py::test_earlier_phase_key_is_legal PASSED [ 60%]
tests/unit/test_hook_dag_validation.py::test_hook_produced_key_consumed_same_phase_is_legal_and_ordered PASSED [ 70%]
tests/unit/test_hook_dag_validation.py::test_edgeless_hooks_keep_registration_order PASSED [ 80%]
tests/unit/test_hook_dag_validation.py::test_validate_clean_on_empty_registry PASSED [ 90%]
tests/integration/test_hooks_phases.py::test_add_hook_missing_declarations_is_fatal PASSED [100%]
============================== 10 passed in 0.72s ==============================
```

Each condition test carries its own red demonstration in its docstring
(`test_hook_dag_validation.py`'s module docstring: "Each CAMPAIGN.md section-4 fatal
condition demonstrated red"). The permanent `tests/integration/test_hook_dag.py` separately
proves every real check/plugin package's declarations validate (its `ALL_PACKAGES` loads
all twelve — the I8→I10 drift that once blinded it is closed, LEDGER I10).

---

## Q3 — Do the contract registry and CLAUDE.md table agree (test-enforced)?

**Answer: YES, and a test pins it both ways** — `psh.modules.CONTRACT` is authoritative and
`tests/unit/test_contract_registry.py` pins the stuffers (`stuff_traffic_contract`,
`stuff_gather_contract`, `stuff_envs_contract`, `stuff_dns_contract`) against it, so drift
on either side goes red.

```
$ python -m pytest tests/unit/test_contract_registry.py tests/integration/test_hook_dag.py -q
............                                                              [100%]
12 passed in 1.00s
```

CLAUDE.md's per-phase contract table names `psh.modules.CONTRACT` as "authoritative" and
labels the prose table its "prose rendering", so the registry is the single source of truth
and the table is derived from it — the arrangement Q3 asks for.

---

## Q4 — Is any `sc` re-export now consumed by nobody (dead façade surface)?

**Two halves.**

### (a) `NoticeRegistry` is load-bearing, not dead façade surface.

At I14c every notice code became registered at import through a module-level `NOTICE_*`
constant, which makes `NoticeRegistry.register`'s `DuplicateNoticeCodeError` guard the thing
that actually fires (it once let two notices share the `php-eol` / `annual-bill` codes, I1).
Two permanent tests hold it:

- `tests/integration/test_notice_roster.py` — the registered codes are exactly the pinned 36.
- `tests/integration/test_notice_registration.py` — the new I14d finding-2 test (AST over
  `psh/` + `check/` + `plugin/`): every `Notice(...)` / `sc.Notice(...)` passes `code=` a
  module-level `NOTICE_*` constant, and every `NOTICE_*` is a `registry.register(...)` result.
  A literal code is now a named failure — so CLAUDE.md's "registry-enforced" is finally true.

```
$ python -m pytest tests/integration/test_notice_roster.py \
      tests/integration/test_notice_registration.py -v
tests/integration/test_notice_roster.py::test_roster_is_exactly_the_registered_codes PASSED [ 20%]
tests/integration/test_notice_roster.py::test_the_roster_is_the_documented_size PASSED [ 40%]
tests/integration/test_notice_registration.py::test_every_notice_code_is_a_registered_constant PASSED [ 60%]
tests/integration/test_notice_registration.py::test_every_notice_constant_comes_from_register PASSED [ 80%]
tests/integration/test_notice_registration.py::test_static_codes_match_the_runtime_roster PASSED [100%]
============================== 5 passed in 1.38s ==============================
```

### (b) Dead-`sc`-name scan — REPORTED, NOT DELETED (Invariant 9 / D-i14d-10).

For each of the 16 documented façade names (`SC_FACADE_NAMES`,
`tests/unit/test_house_rules.py:162`), a grep of `check/` and `plugin/` for `sc.<name>`:

```
$ for n in escape_url check_wordpress_plugin check_drupal_module umich_enabled \
    cloudflare_enabled terminus fqdn_re db_engine_args Notice Severity registry \
    wp_eval wp_error drush_php_script drush_error contract_year_end; do
    printf "%-24s %s\n" "$n" "$(grep -rn "sc\.$n\b" check/ plugin/ --include=*.py | wc -l)"
  done
escape_url               11
check_wordpress_plugin   4
check_drupal_module      4
umich_enabled            5
cloudflare_enabled       5
terminus                 2
fqdn_re                  1
db_engine_args           1
Notice                   26
Severity                 24
registry                 24
wp_eval                  2
wp_error                 2
drush_php_script         2
drush_error              3
contract_year_end        1
```

**No dead façade names: every one of the 16 has at least one live consumer in `check/` or
`plugin/`.** The four lowest-count names are all genuine single-consumers, verified:

```
$ grep -rn "sc\.\(db_engine_args\|fqdn_re\|contract_year_end\)\b" check/ plugin/ --include=*.py
plugin/umich/portal.py:22:    conn_str, engine_kwargs = sc.db_engine_args({**db_info, 'type': 'mysql'})
check/pantheon_cdn_change/detect.py:45:    return bool(sc.fqdn_re.match(text))
check/umich/annual_billing.py:114:    if not sc.contract_year_end(site_context["end_date"]):
```

Nothing is deleted here regardless: CAMPAIGN.md §3.5 / Invariant 9 forbid removing an `sc`
name, and the standalone check-module tests monkeypatch that surface. Had the scan found a
dead name, its deletion would be a reviewed post-campaign README TODO (D-i14d-10) — it did
not, so there is nothing to add.

---

## Q5 — Is the `.py` symlink still needed for anything beyond the shim?

**Answer: KEPT (answered at I14a).** `pantheon-sitehealth-emails.py` is a committed symlink
to the extension-less shim `pantheon-sitehealth-emails`. What it buys, per the rewritten
CLAUDE.md: ruff, pyright, and CodeGraph key off the `.py` extension, so the symlink keeps
all three seeing the **shim's own lines**. The symlink's original, larger reason — the same
three tools blind to the several-thousand-line extension-less *core program* — dissolved
once the program body moved into `psh/cli.py` (a normal `.py` file the tools index
natively). It stays tracked (not git-ignored) on purpose: a git-ignored symlink would
vanish on a fresh clone. **Do not delete it** — this is Keep-list #1 in the rewritten
CLAUDE.md.

```
$ ls -l pantheon-sitehealth-emails.py
lrwxrwxrwx ... pantheon-sitehealth-emails.py -> pantheon-sitehealth-emails
```

---

## Q6 — Are all ledger items resolved (done, scheduled, or README TODO)?

**Answer: YES.** Every "Discovered tasks" and "Open questions" item in `LEDGER.md` entries
I0…I14c has exactly one terminal disposition below — **done** (with commit/artifact),
**README TODO** (with the item's text), or **declined** (with the reason). Nothing resolves
to "carried". Enumerated via:

```
$ grep -n "Discovered tasks\|Open questions" development/2026-07-17-modularization-campaign/LEDGER.md
```

which returns 39 matching lines (35 bolded `**Discovered tasks**`/`**Open questions**`
headings, plus 4 in-prose mentions), whose items are walked below. "Open questions for I<N+1>" rows that read
"proceed per CAMPAIGN.md §11 row I<N+1>" are terminally **done** because every increment
I0…I14d completed; only their *named inherited obligations* are itemised.

### Planning (2026-07-17)

| Item | Disposition |
|---|---|
| Five bugs + dead code → I1 | **done** — I1 (`5518de7..1ff9153`), each test-first |
| README "~55 ruff / 39 pyright" stale figures → I0 re-measures | **done** — I0 pinned measured baselines |
| B51 second annual-bill notice ("remove Aug 2026") | **done** — split I1, deleted early at I14a (`cd084e9`/`745967e`/`f22950e`, user-approved; §8 amendment) |
| WordPress/Drupal + update-table HTML duplication → I9/I10 | **done** — shared gather (`psh/gather.py`) + `check/addon_updates/` |
| Open Qs for I0 (ruff rule list; pyright strictness; `dns_classify.py` under `psh/` MAY) | **done** — ruff/pyright pinned at I0; `dns_classify.py` → `psh/dns_classify.py` at I14a |

### I0 — bootstrap

| Item | Disposition |
|---|---|
| `Path(psh.__file__).parent` repo-root proxy, 25 sites | **done** — fixed I0; the deeper conftest/`psh`-fixture redesign completed at I14a |
| ruff lints explicitly-passed excluded files | **done** — `--force-exclude` + repo-root cwd in the edit hook (I0) |
| Open Qs for I1/I2 (in-place fixes; un-grandfather wrappers; `dns_classify` MAY) | **done** — I1, I2, I14a respectively |

### I1 — known-bug fixes

| Item | Disposition |
|---|---|
| Template `sites/0/` U-M portal URLs render in non-U-M runs (Obs. 1) | **declined** — post-campaign de-U-M-ification; golden-frozen; recorded in CLAUDE.md's still-hardcoded-U-M inventory (Keep-list #19); CAMPAIGN §1 keeps new report content a non-goal |
| `php_version < "8.2"` string compare + KeyError (Obs. 2) | **done** — I8 (D-i8-4.1/4.2), Obs. 2 fully discharged |
| B47 downgrade path: no owner notice; non-Basic downgrade appends no `site_savings` (Obs. 3) | **done** (savings omission fixed I7, D-i7-4) + **README TODO** (owner-facing downgrade notice — `README.md`: "Notify site owners directly of downgrade plan recommendations (post-campaign)") |
| Composer-smell baked-in indentation (Obs. 4) | **done** — I10 (D-i10-8), Obs. 4 discharged |
| `its-recommends-plan` csv `{savings:,.2f}` thousands-comma (Obs. 5) | **done** — I7 (`1d32b9f`, `{savings:.2f}`), Obs. 5 discharged |
| Residual test gap: `main()` umich-only annual-bill call sites untested | **done** — I12 (`tests/integration/test_sort_notices_and_subject.py`) |
| Process note: implementer report `Write` silently failed | **done** — process fix (purge scratch reports before dispatch); recurred + re-caught at I14a |
| Open Qs for I2 | **done** — none new; I2 proceeded |

### I2 — gateway

| Item | Disposition |
|---|---|
| `wp`/`wp_eval`/`drush`… docstrings said "Returns a 3-tuple" | **done** — fixed I2 Task 3 (→ `GatewayResult`) |
| `ENVIRON_SCOPE` house-rule blind to the program body | **done** — fixed I2 (added `"psh"`, red demo recorded) |
| Open Qs for I3 | **done** — none new |

### I3 — configuration + `Notice`

| Item | Disposition |
|---|---|
| Extra-csv-field `Notice` modeling deferred to first adopter | **done** — I14c (`csv_extra` §6 amendment + all 37 producers converted) |
| Open Qs for I4 (registry import-time-once note) | **done** — I4 |

### I4 — hooks + DAG

| Item | Disposition |
|---|---|
| Raw hook-dict write in `test_plugin_umich_portal.py` | **done** — fixed I4 Task 5 (→ declared `add_hook`) |
| `checkload.py` needs a `base=` param | **done** — fixed I4 Task 5 |
| Two unknown-phase fatals interpolated `hook_name` unescaped | **done** — fixed I4 Task 5 (Invariant 6) |
| `main()`'s `except HookDagError` glue untested | **declined** — accepted (SPEC §9): every condition proven red at the `validate_hooks` seam; the glue is print+exit and the goldens prove the success path |
| `run_finish` abort-path direct probe "cheap add" | **done** — I13's `test_finish_run.py` gained a `run_finish` probe with `run_state` |
| Runtime-registered hooks bypass conditions 1–4 | **declined** — import-time registration is the assumed and documented model; no in-repo hook registers dynamically |
| Open Qs for I5 | **done** — none new |

### I5 — DB layer

| Item | Disposition |
|---|---|
| `record_db_reconnect`'s untyped `site` param | **done** — fixed I5 (`str \| None`) |
| Blank-line debris from non-contiguous deletions | **done** — fixed I5 (whitespace-only) |
| SPEC §7/§9 "782" `--fast`-tier baseline mislabel | **done** — corrected in place I5 |
| Open Qs for I6 (five-idempotent-units list sync) | **done** — I6 kept the list in sync |

### I6 — traffic layer

| Item | Disposition |
|---|---|
| Fixture-shadowing defect in the plan's own test code | **done** — fixed I6 (module-level imports; no assertion changed) |
| Commented-out `# for row in results` debug pair | **done** — deleted I6 (ERA001) |
| `traffic_table_columns` duplicates `month`/`visitors` | **declined** — golden-frozen; a post-campaign question; changing now violates Invariant 1 |
| Pure-move SPECs carry no PD#8 flow diagram | **declined** — advisory note for future spec authors; no action |
| Open Qs for I7 (D-i6-2 `overage_blocks` bridge; LEDGER I1 carried) | **done** — D-i6-2 discharged at I7 (module-level `from psh.plans import overage_blocks`) |

### I7 — plans + D7

| Item | Disposition |
|---|---|
| CRITICAL: D-i7-6 op-window ordering rendered non-deterministic costs | **done** — fixed `15fb36d`; `test_recommendation_is_deterministic_across_reruns` pins it |
| BLOCKMAP B46 mislabel ("read + commit" for a WRITE unit) | **done** — fixed I7 in `BLOCKMAP.md` |
| Dead tail inits in `_legacy.py` (post-rec-unpack) | **done** — I13 deleted the three dead inits (`site_current_plan` kept) |
| `import copy` orphaned | **done** — removed I7 |
| Open Qs for I8 (LEDGER I1 Obs. 2) | **done** — I8 |

### I8 — check/pantheon

| Item | Disposition |
|---|---|
| D-i8-5 updates-alert singular `short` missing `f`-prefix | **done** — fixed I8 Task 3 (pinned) |
| Test hardening: `test_disabled_registers_nothing` also asserts `site_post_gather` | **done** — fixed I8 close |
| Mid-file imports in the two `check/pantheon/` test files | **done** — resolved I14b (tests un-grandfathered; idiom block) |
| Open Qs for I9 (pyright-scope decision inherited) | **done** — I9 |

### I9 — wordpress

| Item | Disposition |
|---|---|
| I8 stdlib-vs-`rich` `pprint` divergence in `updates.py` | **done** — fixed I9 (`d5c4bf8`) |
| `stuff_gather_contract` docstring says `"unknown"` for `*_version` | **done** — I10 (D-i10-11) corrected it |
| `semver.compare` `PendingDeprecationWarning` | **README TODO** — folds into the pre-existing "dependency updates" post-campaign item (CAMPAIGN §15); pre-existing behavior moved verbatim |
| Open Qs for I10 | **done** — I10 |

### I10 — drupal + addon_updates

| Item | Disposition |
|---|---|
| D-i10-7 (`type in u` builtin bug) / D-i10-8 (composer indentation) | **done** — fixed I10 (both red-first) |
| `test_hook_dag.py` `ALL_PACKAGES` drift (blind I8→I10) | **done** — fixed I10 Task 2 (all four packages added; note annotated) |
| Two-binding `run_terminus` seam trap | **done** — fixed in-test + durable CLAUDE.md note |
| Task-4 §8.3 sanctioned-class ruff/pyright additions | **done** — SPEC §8.3 amended in place |
| Two probe-smell seeding lines in `main()` rest on inspection | **declined** — accepted; no seam above the golden; the halves are pinned separately |
| D-i10-12 subject-line consequence | **done** — informational; zero golden impact, ledgered |
| D-i10-13 `Notice`-class adoption deferred | **done** — I14c |
| Open Qs for I11 | **done** — I11 |

### I11 — charts

| Item | Disposition |
|---|---|
| `# TODO: Create SVG chart` marker dropped not relocated | **done** — fixed `7392d9f` |
| SPEC observations (`estimates` guard mismatch; `est_bars`/`bars` leakage; vlines epsilon) | **declined** — post-campaign observations; equivalent today; no action |
| Open Qs for I12 (escape_url bridges; annual-bill test coverage) | **done** — I12 discharged both |

### I12 — render + mail + annual billing

| Item | Disposition |
|---|---|
| `subprocess` not orphaned (a documented seam) | **done** — SPEC §5 corrected in place; kept with reason |
| jinja2 `keep_trailing_newline` test literal wrong | **done** — fixed in test (code unchanged) |
| Vacuous `!important`-pass assertion | **done** — fixed `8dbaf75` (real `@media` target; red-capable) |
| `_billing_inputs` return annotation | **done** — fixed `79eee7a` |
| `resolve_recipients` empty-team → silent `""` recipients | **declined** — pre-existing, moved byte-verbatim; no §8 surface change; recorded in LEDGER I12 for post-campaign; an explicit empty-team guard is a post-campaign PD#3 item |
| `check/umich/__init__.py` stale disabled-branch message (names only `sitelens`, guard now skips eight modules) | **README TODO** — ledgered to "I14's sweep"; not fixed I14a–c; I14d is docs-only (SPEC §3 permits only finding 1's production edit), so a stdout-only accuracy fix is deferred; added to `README.md` post-campaign list |
| Open Qs for I13 | **done** — I13 |

### I13 — lifecycle + RunState + `main()` final form

| Item | Disposition |
|---|---|
| `import sqlalchemy as db` now a pure test seam | **done** — kept, `# noqa: F401` + reason |
| SPEC §2.9 wrong about `no_primary_domain_notice` | **done** — corrected in place |
| Task-1 review Notes; whole-branch-review Note (no-action) | **declined** — adjudicated correct; documented; no action |
| Open Qs for I14 (argparse bridge; relocation; 622/445 delta) | **done** — I14a relocated `main()`/argparse to `psh/cli.py`, deleted `_legacy.py`, discharged the bridge; the delta is this Q1 |

### I14a — structural finish

| Item | Disposition |
|---|---|
| `uvx ruff` drift (unpinned, resolved 0.16.0) | **done** — pinned `ruff@0.15.22` (`d94c31a`); the residual ruff-upgrade + PLR0917 disposition is a **README TODO** ("Upgrade ruff past 0.15.22 and disposition the PLR0917 findings (post-campaign)") |
| `time` is a fourth seam import | **done** — retained with noqa + reason |
| Task-1 report `Write` silently failed | **done** — re-caught; later dispatches verify the report exists |
| Blame caveat (`git log --follow` won't chain) | **declined** — informational; `git blame -M -C` finds the blobs; no action |
| Report-text corrections (scratch only) | **done** — corrected in scratch reports |
| CLAUDE.md retains ~22 (measured 28) stale `_legacy.py` mentions | **done** — I14d wholesale CLAUDE.md rewrite (`e371d03`) |
| Open Qs for I14b | **done** — I14b |

### I14b — the global ratchet flip

| Item | Disposition |
|---|---|
| py310-target defect (broad config linted at py310 all campaign) | **done** — the merge is the fix; 7 masked findings fixed behavior-identically |
| Orphaned `psh/dns_classify.py` comment fragment | **done** — fixed at close |
| Report-text corrections (scratch) | **done** |
| `README.md:275` `ruff-broad.toml` prose + CLAUDE.md two-pass references | **done** — I14d refresh (`1378cf8`/`e371d03`) |
| `record.py` / `dnsshim.py` edits not suite-executed | **declined** — assessed by reading (trivial-mechanical); `dnsshim` indirectly covered by `test_shim_composability.py` |
| Open Qs for I14c | **done** — I14c |

### I14c — the `Notice` dict-form retirement

| Item | Disposition |
|---|---|
| `uvx pyright@1.1.411` fallback → 34 false `reportMissingImports` | **README TODO** — `README.md`: "Fix or drop the `uvx pyright@1.1.411` fallback (post-campaign)" |
| Five now-unused `site_name` params (four kept, one dropped) | **done** — resolved I14c |
| `pyproject.toml` `[tool.pyright]` only `psh/` | **README TODO** — existing "Widen the pyright gate beyond `psh/` (post-campaign)" |
| The seven whole-branch findings ledgered to I14d | **done** — I14d Task 5 (`5962d3e`) — see the §2.5 dispositions in the I14d ledger entry |
| The two I14c open questions (Q4 answerability; instruments' disposition) | **done** — Q4(a) above; `literal_equality.py` stays an archive artifact (D-i14d-6), `test_notice_registration.py` earns permanence (finding 2) |
| Open Qs for I14d | **done** — this increment |

**No item resolves to "carried".**

---

## Q7 — Has the production config repo received and applied the migration instructions?

**Answer: NO edits are required — that is the finding, not a hope.** The decision
(2026-07-23, ledgered) was **no key renames**: CAMPAIGN §5 required every campaign-introduced
key to land in final shape as introduced (I3 onward), so there is no interim shape to migrate
from. `docs/config-migration.md` records this with its audit trail: the section inventory of
the live production config versus every reader in code, why each new key needed no rename,
what an operator MAY now add (all optional, all defaulting to today's behavior), and the
production-config instruction — **no edits required**.

```
$ ls docs/config-migration.md
docs/config-migration.md
$ head -6 docs/config-migration.md
```
```
# Configuration migration across the modularization campaign

## Headline: no key changes are required

The modularization campaign (I0–I14, `development/2026-07-17-modularization-campaign/`)
moved the several-thousand-line main script into the `psh/` core package and the
```

The production config carries `[Pantheon]`, `[Pantheon.plan_info*]`,
`[Pantheon.plan_sku_to_name]`, `[Database]`, `[Cloudflare]`, `[Cloudflare.cachecheck]`,
`[SMTP]`, `[AWS]`, `[UMich]`, `[UMich.portal]`, `[UMich.portal.db]`, `[News]` — no `[Check.*]`
and no `[Email]`, both of which default correctly (`enabled` true; the U-M literals). So the
instruction the migration doc gives the operator is: apply nothing.

---

## Q8 — Do README, CLAUDE.md, docs/, and memory reflect the final architecture?

**Answer: YES, machine-verified.** `claim_check.py --gate` (whose `--self-test` proves it can
go red — PD#14) decides every mechanizable claim in each document and exits non-zero on any
unallowed `FAIL`/`ERROR`. The three claims a document deliberately makes about a name that no
longer exists (`sc.text_maker`, `sc.add_notice`, `psh.SMTP_SSL`) are in `claims-allow.txt`,
each with its reason.

```
$ python development/2026-07-24-mod-I14d-closing/tools/claim_check.py --self-test
SELF-TEST PASS  8 verdicts + COUNT both ways (registered codes = 36)

$ python development/2026-07-24-mod-I14d-closing/tools/claim_check.py --gate \
    --allow development/2026-07-24-mod-I14d-closing/claims-allow.txt \
    CLAUDE.md README.md CONTEXT.md tests/README.md docs/*.md \
    ~/.claude/projects/-workspace/memory/*.md
    ... (per-document tables) ...
0 unallowed FAIL/ERROR verdict(s)
        # gate exit status: 0
```

The full per-document output is pasted in `SPEC.md §8`. The gate is green over `CLAUDE.md`,
`README.md`, `CONTEXT.md`, `tests/README.md`, every `docs/*.md`, and the nine memory files.

---

## Q9 — Were any invariants amended mid-campaign, and is each amendment ledgered?

**Answer: YES — four amendments, each with its own ledger entry.** (CAMPAIGN.md's preamble:
an amendment edits the document *and* appends a ledger entry.)

| Amendment | What changed | Ledger entry |
|---|---|---|
| **Wave-4 split** | §11 wave diagram + row I14 → rows I14a–d (the closing sweep was several sessions of work; split-never-compress applied at spec time) | LEDGER "Amendments — Wave-4 split + B51 early deletion (2026-07-23)" |
| **B51 early deletion** | §8 "Notice csv values" row + §14 risk row: the "annual bill in progress" notice deleted at I14a ahead of its Aug-2026 date (user-approved) | same entry; executed in the I14a entry |
| **§6 `csv_extra`** | §6 types table `Notice` row gains `csv_extra: tuple[str, ...]` (the field the row reserved at I3) | LEDGER "Amendment — §6 `Notice` csv field set (2026-07-24)" |
| **§3.5 sanctioned exception** | §3.5 "checks/plugins import only `sc`" gains the one exception: `check/pantheon_cdn_change/notices.py` imports `Notice`/`Severity`/`registry` directly from `psh.notice` (purity + 18-vs-276 stdlib-module cost) | LEDGER I14c entry (Deviations) |

Two further mid-campaign amendments were ledgered as part of I9 and I10 (the §8 wp-smell
precedence row, LEDGER I9; the §3.1/§3.2 B48-emission-stays-in-`main()` and §4
hook-produced-key definition, LEDGER I10 amendments 1–2) — every one edits CAMPAIGN.md and
carries a ledger entry, so no invariant drifted silently.

No **named invariant (§9 items 1–11)** was ever *weakened*: the goldens stayed byte-identical
across every increment, the contract only gained keys, the `sc` façade only gained names, and
the safety interlock was never bypassed. The amendments above touched the behavior bar (§8),
the module/phase architecture (§3–§4), and the type set (§6) — not the §9 invariants.

# Extract six stage bodies from `psh/cli.py::main()`

**Spec.** A post-campaign refactor increment. Six contiguous *stage bodies* move out of
`psh.cli.main()` into named module-level helpers in `psh/traffic.py`, `psh/gather.py`,
`psh/plans.py`, and `psh/cli.py` itself. `main()` keeps the loop control, the phase spine, and
the lifecycle dispatch. **No behavior changes**: the four e2e goldens stay byte-identical.

The approved design is `/home/node/.claude/plans/read-the-function-main-fancy-kahan.md`
(2026-08-07, reviewed and approved by the user). This document is the normative rendering of it
for implementation, and supersedes it wherever the two disagree — every disagreement is recorded
in §10.

Prior art this increment sits on: `development/2026-07-17-modularization-campaign/` —
**`CAMPAIGN.md`** (the frozen architecture; amendments only), **`LEDGER.md`** (the append-only
history), **`BLOCKMAP.md`** (the block-ID ↔ line-range table), **`CLOSING-AUDIT.md`** (the closing
answers, of which Q1 is corrected here).

> **Read `prompts/directives.md` first** — the Spine. This spec cites Prime Directives by number
> and restates none of them.

---

## Requirement vocabulary

| Word | Meaning |
|---|---|
| **MUST** / **MUST NOT** | An absolute requirement. A violation is a defect, and there is a test or a gate. |
| **SHOULD** | Strong recommendation; a deviation requires a stated reason in code. |
| **MAY** | Genuinely optional. |
| **NEVER** | Same force as MUST NOT, used where the negative reads more clearly. |

Every list in this document is marked **exhaustive** or **illustrative**. An unmarked list is a
defect in this spec.

---

## Glossary

Campaign terms keep their `CAMPAIGN.md` §Glossary meaning exactly. New terms are marked **(new)**.
Each term is used once per concept, here and in the code.

| Term | Meaning |
|---|---|
| **block ID** | `B1`–`B60`, the stable references from `BLOCKMAP.md`. Line numbers drift; block IDs do not. |
| **residue** **(new)** | The part of a block still in `main()` after an earlier increment moved that block's core elsewhere. Written `B34 (residue)`. **`B34r`/`B35r` are NOT block IDs** — that notation appears in the plan but exists in no campaign document; this spec uses `B34 (residue)`. |
| **stage body** **(new)** | A contiguous run of `main()` statements that computes one named result set and whose scratch locals die inside it. The unit this increment extracts. |
| **stage spine** **(new)** | The `stuff_*_contract(...)` and `sc.invoke_hooks(...)` call pairs. NEVER moves (§3 R-G2). |
| **delta** | A returned smell string where `""` means *no new smell*, NEVER *clear the previous smell*. See §3 R-G5. |
| **skip sentinel** | The `None`/`False` return by which a helper tells `main()` to `continue`. Loop control stays in `main()` (D-i6-1). |
| **stay-list** | `CAMPAIGN.md` §3.3's exhaustive list of what stays in `main()`, written in block IDs. |
| **amendment** | A `CAMPAIGN.md` edit recorded in `LEDGER.md` per §12's template. `CAMPAIGN.md` is frozen except by amendment. |
| **raw / logic lines** | `main()`'s `end_lineno - lineno + 1`, and the subset that is neither blank nor comment-only. The measurement snippet is `CLOSING-AUDIT.md` Q1's, reproduced in §9. |

---

## 1. Context and motivation

### 1.1 The argument is not length

`main()` already contains function boundaries it is not using. Three groups of locals have a
lifetime entirely inside one contiguous block, which is the definition of a function's local:

- `main_fqdn` / `custom_domains` / `primary_domain` are born at `psh/cli.py:664-666` and dead by
  718 (last reads: 702, 707, 717 — **verified**).
- `plugins` / `mods` / `wordpress_version` / `drupal_version` / `add_on_updates` are all dead at
  the `stuff_gather_contract` call on 763-765; the four `= None` declarations at 725-728 exist
  only to make that one call unconditional (**verified**).
- `last_day` (779) and `days` (796) are pure scratch: `last_day` is read only at 780 and 804,
  `days` only at 806-807 — every reference inside a 39-line span (**verified**).

Both the domains group and the gather group also carry a live hazard **today**: `wp_smell` exists
as a `main()` local **and** as `site_context["wp_smell"]`, and `CLAUDE.md` already has to warn
readers that consumers after the phase must read the contract key, "never a stale `main()` local".
Extraction deletes the duplicate representation at the sites where it is most confusing.

### 1.2 The second argument is coverage

`main()` has **no in-process caller anywhere in the suite** — the only reference is
`inspect.getsource(psh.main)` at `tests/integration/test_regressions.py:79` (**verified**; the
`fs.main()` calls in `tests/unit/test_finalize_session.py` are `development/finalize-session.py`'s
own `main`). The subprocess interlock bans `--all`/`-a`/`--for-real`
(`tests/conftest.py:60 FORBIDDEN_FLAGS`, **verified**), so entire regions of `main()` are
untestable at any tier *by construction*:

| Region | Why it is unreachable today |
|---|---|
| The `--resume-from` filter + resume banner | `--resume-from` requires `--all`, which is a forbidden flag. **Permanently unreachable at the subprocess tier, by design.** |
| The five per-site skip gates | Reached only through a full site loop. |
| The `--update-cloudflare-fqdns` guard (`psh/cli.py:425`) | Not interlock-blocked, merely never exercised: **no file under `tests/` contains its exit message** (verified — see §10 item 4). |
| The `isinstance(domains, dict)` guard (667) | No test at any tier. |
| The unknown-plan `sys.exit("Bailing out.")` (586) | Needs a hand-authored terminus fixture plus a subprocess run that must abort. |
| The zero-traffic seed's postconditions (781-793) | Only witness is a whole `run_program` run (`tests/e2e/test_zero_traffic_e2e.py`). |

Each extraction converts an unreachable region into a millisecond unit or integration test. This
is PD#14 applied to the program rather than to a test: *"A green check is a claim, not evidence,
until it has been shown capable of going red on the condition it guards."* Nothing today would go
red if someone "tidied" `site_count` to `len(site_names)` (§5.4).

### 1.3 What the campaign recorded

`main()` closed the modularization campaign at **622 raw / 445 logic** lines against
`CAMPAIGN.md` §3.3's 250-400 target — a *recorded deviation*, answered as `CLOSING-AUDIT.md` Q1
and deferred to a post-campaign README TODO, **D-i14d-1**.

> **Correction (PD#14; the plan's claim is now stale).** The plan cites `README.md:260-267` as
> the live home of D-i14d-1. That TODO was **struck from `README.md` earlier the same day**, in
> commit `5b92ee1` ("start post-modularization-campaign cleanup", 2026-08-07 06:54). No occurrence
> of D-i14d-1 remains in `README.md`; the surviving references are in `CLOSING-AUDIT.md:20,57`,
> `RETROSPECTIVE.md:104`, `LEDGER.md:2339`, and `development/2026-07-24-mod-I14d-closing/SPEC.md`.
> Consequence for Task 7: the amendment table row "strike the D-i14d-1 TODO" is **already
> discharged** and MUST NOT be re-performed — see §7 R7.6.

The struck TODO named three candidate extractions: *"the config/arg bootstrap sequence, the
per-site skip/banner preamble, and the phase-firing + contract-stuffing spine."* This increment
takes the **first** (§5.6, `validate_options`) and **declines the other two**: the skip/banner
preamble and the phase spine are §3.3 stay-list content verbatim, and moving them would violate
the stay-list rather than amend it. §5.4 and §5.5 extract only the *non*-skeleton parts adjacent
to them.

### 1.4 Shape of the change (PD#8)

```
BEFORE — main()'s per-site loop                AFTER
─────────────────────────────────────────      ─────────────────────────────────────────
  validate args (30 lines, inline)  ──6──▶     validate_options()                [psh/cli.py]
  org:site:list + roster (34 lines) ──4──▶     resolve_site_roster(org_id)       [psh/cli.py]
  for site_name in site_names:                 for site_name in site_names:
    plan + Sandbox + unknown-plan   ──5──▶       resolve_site_plan(site, names)  [psh/plans.py]
    sc.SiteContext(site)                 ✋      sc.SiteContext(site)      (STAYS, §5.5 R5.6)
    env:list guards / traffic            ✋      (unchanged)
    stuff_envs + site_pre                ✋      (stage spine — NEVER moves)
    stuff_traffic + site_post_traffic    ✋      (stage spine — NEVER moves)
    domain:list + classify (52 lines) ──3a─▶     fetch_site_domains(...)         [psh/cli.py]
    stuff_dns + site_post_dns            ✋      (stage spine — NEVER moves)
    primary-domain + site_url (25 l.) ──3b─▶     resolve_site_url(...)           [psh/cli.py]
    framework gather threading (40 l.)──2──▶     gather_framework(...)           [psh/gather.py]
    stuff_gather + site_post_gather      ✋      (stage spine — NEVER moves)
    traffic window (39 lines)         ──1──▶     build_traffic_window(...)       [psh/traffic.py]
    db_retry / recommend_plan            ✋      (unchanged)
    --only-warn gate                     ✋      (STAYS — §3 R-G6)
    chart / smell emission / send        ✋      (STAYS — §3 R-G6)
  except BaseException: abort_run        ✋      (STAYS — §3 R-G6)
```

✋ = does not move. The numbers are the extraction numbers of §5, which are also the
implementation order (§2.3).

---

## 2. Scope

### 2.1 In scope (exhaustive)

Exactly six extractions, §5.1 through §5.6, each landing as **its own commit** with a full
`./run-tests`, plus the Task 7 documentation increment (§7). Nothing else.

### 2.2 NOT in scope (exhaustive; reasoning preserved so it is not re-litigated)

| Item | Why not |
|---|---|
| `template_dict` (`psh/cli.py:918-947`) | D-i12-2 declined it as *"a ~25-parameter function"*. That objection weakens once these six group the locals into objects, so it is worth revisiting **after** this increment — not during. |
| The `recommend_plan` 8-local unpack (858-865) | Same class as `template_dict`; same disposition. |
| The pathlib migration | Four `noqa` comments in `main()` (`psh/cli.py:373, 437, 438, 470` — **verified**) say *"pathlib migration is I14b+"*, but I14b's ledger entry never touched PTH and neither `README.md` nor `CLAUDE.md` mentions it. The deferral is **orphaned** (PD#9: *"Everything deferred is written down. Vague intentions are lies."*). Task 7 gives it a home as a `README.md` TODO (§7 R7.7); the migration itself is not this increment's business. |
| Any algorithmic redesign of moved code | `CAMPAIGN.md` §3.1: *"Moved helpers … do NOT get algorithmic redesign — moves are behavior-preserving."* This increment is post-campaign but adopts the same rule; the only sanctioned statement moves are §5.4 R5.4.1/R5.4.2 and §5.5 R5.5.4, each individually justified. |

### 2.3 Implementation order is NORMATIVE

The six extractions MUST be implemented in the order §5.1 → §5.6. This is not a presentation
choice:

1. **§5.1 is first because it is the cheapest correct start.** It needs **no `CAMPAIGN.md`
   amendment** (§5.1 R1.7), carries **no column-pinned notice literal** (Invariant 8 does not
   bind it), shares **no locals with the smell merges**, and is the largest single win (39 raw
   lines). It establishes the extraction pattern — NamedTuple return, unpack into the pre-existing
   local names, loop control untouched — against the lowest possible risk.
2. **§5.6 is last because it is the only one that can change startup behavior for every other
   task's tests.** `validate_options()` moves four `sys.exit` guards; a defect there fails every
   subsequent task's `./run-tests` in a way that looks like that task's fault.
3. **§5.3 must land as one commit** even though it is two functions (§5.3 R3.9).
4. The middle four are ordered by ascending amendment surface: §5.2 (no amendment) → §5.3
   (narrow one) → §5.4 (one) → §5.5 (a split plus one).

An implementer who finds their task's predecessor not yet landed MUST report `BLOCKED`, not
re-order.

---

## 3. Global invariants and constraints (exhaustive)

These bind **every** task. They are restated here because implementer subagents have fresh
context and read only this spec and their brief.

**R-G1 — Invariant 1: the four e2e goldens are byte-identical.**
`tests/e2e/__snapshots__/test_golden.ambr`, `test_golden_drupal.ambr`,
`test_golden_nonumich.ambr`, `test_golden_cdn_change.ambr`. `CAMPAIGN.md` §9.1: a golden going
red *"is a defect in the increment, PD#14"*. **`./run-tests --update-goldens` MUST NOT be run at
any point in this increment.** This is the same rule as
`prompts/implementation-standards.md` § Test discipline: *"an existing golden going red is a
signal, never refreshed to green."*

**R-G2 — the stage spine never moves.** Every `stuff_*_contract(...)` and `sc.invoke_hooks(...)`
line stays inline in `main()`, so `main()` still reads as *fetch → stuff → fire phase*. Only
stage **bodies** move. Exhaustive list of the spine lines that stay: 627-628, 632-633, 691-692,
763-766, 894-908 (`stuff_plans_contract` + `site_pre_render`).

**R-G3 — loop control stays in `main()` (D-i6-1).** A helper NEVER executes `continue` or `break`
on `main()`'s behalf and NEVER contains the site loop. Helpers signal a skip by returning a
**skip sentinel** and `main()` performs the `continue`. Precedents in this codebase (illustrative):
`update_site_traffic -> bool`, `resolve_plan_name -> None`, `resolve_recipients -> tuple | None`.

**R-G4 — NEW RULE: no extracted helper may be the sole assigner of `site_name` or
`site_emailed`.** Python has no block scope, and the `except BaseException` handler reads both at
`psh/cli.py:981-982` (**verified**: `abort_run(db_session, db_engine, site_name, reason, e,
emailed=site_emailed, ...)`).

- **Failure scenario if violated for `site_emailed`:** `site_emailed = False` at line 534 is the
  **per-iteration reset**, distinct from the pre-loop binding at 531. If a helper owned it,
  `main()`'s local would never reset. Site *N* emails (`site_emailed = True` at 964); site *N+1*
  aborts at `domain:list`; `abort_run(..., emailed=True)` advances the resume point **past**
  *N+1* — **that site's owner silently never receives their monthly report**, and the
  `site_results.pop()` drop is skipped so the artifacts claim it completed. Invisible to all four
  goldens. (PD#1: *"A failure that can happen silently is a critical defect."*)
- **Failure scenario if violated for `site_name`:** `site_name = None` / `site_emailed = False` at
  530-531 sit two lines below §5.4's extraction end. If a helper became their sole assigner,
  `abort_run` raises `NameError` **inside the handler** — after SIGINT is set to `SIG_IGN` and
  before `finish_run()` — destroying every artifact the handler exists to save.

  `site_id` (535) also stays in `main()`: it is read 354 lines later at 889.

**R-G5 — smell merges stay in `main()`; helpers return deltas.** `psh/gather.py`'s module
docstring is the authority (**verified at `psh/gather.py:11-13`**): *"main() only rebinds
wp_smell/drush_smell when the returned smell is non-empty."* A returned `""` means **no new
smell**, NEVER *clear the previous one*. Every helper that can produce a smell returns it as a
separate field and `main()` writes `if <helper>.wp_smell != "": wp_smell = <helper>.wp_smell`.
A helper MUST NOT be handed the current smell value to merge internally.

**R-G6 — the no-move list (exhaustive).** These stay in `main()` in their current position:

| What | Lines | Why |
|---|---|---|
| The SMTP send block | 959-965 | D-i12-4. `run_state.emails_sent += 1` / `site_emailed = True` sit **between** `send_message()` and `quit()`; hoisting the block moves them after `quit()` returns, reopening the Ctrl-C-during-`quit()` duplicate-email window. |
| `run_state.record_site_notices(...)` | 956-957 | Invariant 4: notices are recorded **before** the send. |
| The smell **emission** | 880-884 | `CAMPAIGN.md` §3.3 / LEDGER I10 amendment 1: it summarizes end-of-phase smell state no hook position can guarantee, and must stay behind the `--only-warn` gate. |
| The `--only-warn` gate | 869-872 | §3.3 stay-list (B42). |
| `try:` / `except BaseException` / `finish_run` | 532, 969-984, 986-991 | §3.3 stay-list (B59-B60 call sites); Invariant 4's single flush path. |
| `sc.SiteContext(site)` | 579 | §5.5 R5.6 — its *position* is a documented invariant of the loop. |
| The per-site loop header and all five skip `continue`s | 533-534, 546, 554, 568, 574, 603, 615, 619, 623, 646, 872, 891 | D-i6-1 / R-G3. |

**R-G7 — Invariant 8: column-pinned literals move verbatim.** `CAMPAIGN.md` §9.8: *"Column-0
`f\"\"\"` notice literals move **verbatim** — never re-indented; `git diff -w` is not acceptable
evidence for any change touching them."* This binds §5.3 concretely (see §5.3 R3.6) and binds
every other task by prohibition: no other extraction range contains a notice literal
(**verified**).

**R-G8 — parallel-ready constraint (`CAMPAIGN.md` §3.4).** Per-site work MUST be a function of
`(site, config, db_session, site_context)`. No new module-level mutable state. Run-scoped
accumulators (`run_state.site_results`, `run_state.site_savings`, `run_state.all_warnings`,
`run_state.emails_sent`) are written **only by `main()`**; a helper returns the value and `main()`
performs the accumulator write. §5.2 R2.6 makes this mechanically checkable for the first time.

**R-G9 — house style.** `prompts/implementation-standards.md` § *The fresh-context trap*: use the
wrappers (`run_terminus`/`terminus`/`terminus_data`, `wp`/`wp_eval`, `drush`/`drush_php_script`),
add notices via `SiteContext` methods, and **follow local idioms even where non-idiomatic** — the
`-> (str, str, bool)` tuple hints are house style and MUST NOT be "corrected". New helpers use
modern hints (`-> TrafficWindow`, `-> str | None`) matching the surrounding `psh/` module they
land in.

**R-G10 — scalars, not `site`, where a hook could mutate.** Where a helper needs a value that is
also reachable through `site_context["site"]` (which hooks hold), the value MUST be passed as a
**scalar parameter**, not re-derived from `site` inside the helper. Concretely: §5.1's
`current_plan` and `site_name`. Re-deriving `site["plan_name"]` inside `build_traffic_window`
would newly expose the zero-traffic seed value to hook mutation — a behavior change with no test
that could see it.

**R-G11 — named errors (PD#2).** No new `except Exception` / bare `except`. Ruff's `BLE001`/`E722`
gate this and `./run-tests` blocks on them. `main()`'s existing `except BaseException` keeps its
`# noqa: BLE001` and its reason comment verbatim.

**R-G12 — `noqa` comments travel with the code they suppress.** `main()`'s `# noqa: C901,
PLR0912, PLR0915` on the `def main()` line (370) stays; the implementer MUST NOT remove it even if
the extraction drops the branch count below the threshold, because ruff's `RUF100` (unused-noqa)
is not selected in a way that would flag it and removing it is a judgment call outside this
increment. If ruff *does* flag it, that is a finding to report, not to silently act on.

---

## 4. The two traps that look like natural boundaries and are not

**This section is the highest-value content in this document.** Both traps are invisible to all
four e2e goldens, which is why they need to be written down rather than caught.

### 4.1 Trap 1 — `site_emailed = False` at 534 is the per-iteration reset, not the pre-loop binding

```python
    site_name = None
    site_emailed = False          # 531  <- PRE-LOOP binding (for the handler)
    try:
        for site_name in site_names:
            site_emailed = False  # 534  <- PER-ITERATION reset (the trap)
```

A "per-site preamble" helper is the natural-looking boundary that swallows 534. If it did,
`main()`'s `site_emailed` would be set to `True` at 964 for site *N* and **never reset** for site
*N+1*. The full failure chain is in R-G4. The two lines are three characters apart and do
completely different jobs; the only defense is knowing that.

### 4.2 Trap 2 — `site_name = None` / `site_emailed = False` at 530-531 must not be swallowed by the roster extraction

§5.4's extraction ends at line 528. Lines 530-531 sit **two lines below it** and look like part of
the same pre-loop block. They are not: they are the handler's guarantee that both names are bound
before `try:` opens. If a helper became their sole assigner, `abort_run` raises `NameError`
**inside** the `except BaseException` handler — after `signal.signal(SIGINT, SIG_IGN)` and before
`finish_run()` — and every artifact that handler exists to save is lost. The exception would also
be a `NameError` about a local, giving the operator no signal about the real failure that started
the abort.

**Both traps are the same defect class**: a name whose *binding site* is load-bearing for a
handler 450 lines away. R-G4 is the rule that generalizes them.

---

## 5. The six extractions

Each subsection gives: the exact `psh/cli.py:370-991` line range **verified against the working
tree at commit `c01e77b`**, the BLOCKMAP block IDs, the destination module with its rationale, the
full signature and return type with per-field trailing comments, **what `main()` keeps** as
literal replacement code, and whether a `CAMPAIGN.md` §3.3 amendment is required.

> **On the literal "what `main()` keeps" blocks.** They are illustrative of *shape and naming*,
> normative in *what is present and what is absent*. An implementer MAY reflow them to satisfy
> ruff; an implementer MUST NOT add, drop, or rename a bound local, and MUST NOT move a line that
> R-G6 lists as staying.

---

### 5.1 `build_traffic_window` — `psh/cli.py:770-808` → `psh/traffic.py`

**Range (verified).** 770 = `visits_by_month, plan_on_day = aggregate_visits_by_month(`;
808 = `site_plan_start = plan_over_time[0]["start"].replace(day=1)`. 39 raw / 23 logic lines.

**Block IDs.** **B43** (`visits_by_month`, `plan_on_day`, `build_plan_over_time`) plus the
**residue of B44** — the single `estimate_month_visits` call at 804, all that is left of B44 in
`main()` after I11 moved chart data prep to `psh/charts.py`.

**Destination rationale.** `CAMPAIGN.md` §3.1 already assigns **both** to `psh/traffic.py`: the
`psh/traffic.py` row reads *"`get_old_metrics`, `estimate_month_visits`, `build_traffic_table_rows`,
the `traffic_table_columns` global, metrics gather + DB update/load flow (B22–B26), visits-by-month
aggregation (B43)"*. Only `aggregate_visits_by_month` made the trip at I6; the caller-side
assembly stayed behind.

**No import cycle (verified).** `psh/traffic.py:27` already reads `from psh.plans import
overage_blocks`, so adding `build_plan_over_time` to that existing import introduces **no new
edge**. The module also already imports `calendar` (12) and `datetime` (13). It will need one new
import: `from rich.pretty import pprint` (for the two verbose dumps at 774-776).

**Signature and return type.**

```python
class TrafficWindow(NamedTuple):
    visits_by_month: dict[str, int]        # every "%Y-%m" in the window, 0-seeded
    plan_on_day: dict[datetime.date, str]  # {end_date: current_plan} synthetic seed when the site has NO rows; never empty
    plan_over_time: list[dict]             # contiguous {"start","end","plan"} spans; never []
    dates: list[datetime.date]             # month midpoints indexing visits_by_month, in key order
    estimate: int                          # -1 when the month is complete or too early to extrapolate
    first_plan_day: datetime.date          # == end_date on the synthetic seed
    last_plan_day: datetime.date           # == end_date on the synthetic seed
    site_plan_start: datetime.date         # first-of-month of plan_over_time[0]["start"]
    plot_right_date: datetime.date         # last day of end_date's month -- the chart's right edge


def build_traffic_window(rows, start_date, end_date, current_plan: str,
                         site_name: str) -> TrafficWindow: ...
```

**R1.1** `current_plan` and `site_name` MUST be scalars, per R-G10.

**R1.2** `last_day` and `days` MUST NOT appear in the return type. They are pure scratch: every
reference to `last_day` is at 779/780/804 and every reference to `days` is at 796/806/807, all
inside the range (**verified by grep over the whole file**).

**R1.3** The zero-traffic `sc.console.print` at 789-792 and the two verbose `pprint`s at 773-776
and `sc.debug(plan_over_time)` at 798 move **into** the helper. They are observability, not
loop control (PD#5), and are not golden-covered.

**R1.4** `main()` MUST unpack all nine fields into the **pre-existing local names**. It MUST NOT
rewrite the `db_retry` lambda at 817-835 to `window.x`: that lambda carries **six** per-line
`# noqa: B023` suppressions keyed to those exact names (`site`, `visits_by_month`, `plan_on_day`,
`site_plan_start`, `first_plan_day`, `last_plan_day` — **verified; the plan said seven**).

**What `main()` keeps:**

```python
            window = build_traffic_window(
                results, start_date, end_date, site_current_plan, site_name
            )
            # Unpacked into the pre-existing local names on purpose: the db_retry lambda below
            # carries six per-line `# noqa: B023` suppressions keyed to these exact names.
            visits_by_month = window.visits_by_month
            plan_on_day = window.plan_on_day
            plan_over_time = window.plan_over_time
            dates = window.dates
            estimate = window.estimate
            first_plan_day = window.first_plan_day
            last_plan_day = window.last_plan_day
            site_plan_start = window.site_plan_start
            plot_right_date = window.plot_right_date
```

**R1.5 — new tests (impossible today).** At minimum, all five zero-traffic-seed postconditions:
`plan_on_day == {end_date: current_plan}`, `first_plan_day == last_plan_day == end_date`,
`len(plan_over_time) == 1`, `site_plan_start == end_date.replace(day=1)`, and `estimate == -1`;
plus a Hypothesis property that `plan_on_day` is **never empty** for any input — the direct guard
on the P10 `IndexError` that the synthetic seed exists to prevent. Today the only witness is a
whole `run_program` run.

**R1.6 — shadow paths (PD#3).** Trace and test all three beside the happy path: `rows == []`
(the zero-traffic seed), `rows` covering only months outside `[start_date, end_date]`, and a
`current_plan` that is the empty string.

**R1.7 — CAMPAIGN.md amendment: NONE.** Neither B43 nor B44 appears on §3.3's stay-list
(*"Config/arg bootstrap ordering (B1–B8 …); overage constants + date window (B9, B13 part); the
site-loop skeleton (… B14–B18, B20, B25, B42); phase firing and contract stuffing (B27, B28, B31,
B37, B52); the B48 smell-notice emission call; notice sort + subject (B50 minus billing); the
try/except BaseException lifecycle dispatch (B59–B60 call sites)"* — **verified**).

---

### 5.2 `gather_framework` — `psh/cli.py:720-759` → `psh/gather.py`

**Range (verified).** 720 = `# Check the site's plugins/modules`; 759 = the `}` closing the
unknown-framework `site_results` literal. 40 raw / 32 logic lines.

**Block IDs.** **B33** (gather init: the four `= None` plus `add_on_updates = []`), **B34
(residue)** (the WordPress threading branch), **B35 (residue)** (the Drupal threading branch),
**B36** (the unknown-framework fallback, including the `site_results` entry added by I1's bug fix
3). Lines 761-766 (**B37**: `stuff_gather_contract` + `invoke_hooks("site_post_gather")`) stay —
they are the stage spine (R-G2) and §3.3 names B37 explicitly.

**Destination rationale.** `CAMPAIGN.md` §3.1 assigns `psh/gather.py`: *"Slimmed framework gathers
feeding the `site_post_gather` contract (from B32–B35) …"*. `gather_wordpress` and `gather_drupal`
already live there; this is their caller-side threading rejoining them. No new imports are needed
beyond what the module already has (`sc`, `pprint`, the gateway wrappers).

**Signature and return type.**

```python
class FrameworkGather(NamedTuple):
    wordpress_version: str | None  # None = not WordPress; "" when the version fetch failed
    plugins: object                # None = not WP, or the gather failed
    drupal_version: str | None     # None = not Drupal; "unknown" when core-status failed
    modules: object                # None = not Drupal, or the gather failed
    add_on_updates: list           # [] = none pending, unknown framework, or gather failed
    wp_smell: str                  # "" = no NEW smell -- a delta, merged by main()
    drush_smell: str               # "" = no NEW smell -- a delta, merged by main()
    composer_smell: str            # "" = no NEW smell -- a delta, merged by main()
    results_entry: dict            # main() writes it into run_state.site_results


def gather_framework(site, live_site, site_context) -> FrameworkGather: ...
```

**R2.1** `gather_framework` MUST return on every framework branch, including the unknown one. On
the unknown branch the `results_entry` is the literal
`{"framework": site["framework"], "version": "unknown", "plan_name": site["plan_name"]}` moved
verbatim, and the `ATTENTION: unknown framework` console print goes with it.

**R2.2** The three smells are **deltas** (R-G5). `gather_framework` MUST NOT receive the caller's
current smell values.

**R2.3** The extraction deletes the four `= None` declarations (725-728) and the
`add_on_updates = []` (730) from `main()`; the NamedTuple's defaults-by-branch replace them.
`main()` keeps the *unpack*, so the `stuff_gather_contract` call at 763-765 remains unconditional
and unchanged.

**R2.4** `add_on_updates` MUST be threaded as the **same list object** the gather returned, not a
copy: `CLAUDE.md`'s contract table records that `stuff_gather_contract` publishes *"the SAME list
object the `check.addon_updates.table` hook reads, not a copy"*.

**What `main()` keeps:**

```python
            # Check the site's plugins/modules
            gather = gather_framework(site, live_site, site_context)
            wordpress_version = gather.wordpress_version
            plugins = gather.plugins
            drupal_version = gather.drupal_version
            mods = gather.modules
            add_on_updates = gather.add_on_updates
            # Smell merges stay in main() (D-i9-2/D-i10-2): a returned "" means "no NEW smell",
            # never "clear the previous one".
            if gather.wp_smell != "":
                wp_smell = gather.wp_smell
            if gather.drush_smell != "":
                drush_smell = gather.drush_smell
            if gather.composer_smell != "":
                composer_smell = gather.composer_smell
            run_state.site_results[site["name"]] = gather.results_entry
```

**R2.5 — shadow paths (PD#3).** Three branches × the failure modes each `gather_*` already
signals: a WordPress site whose version fetch was fatal, a Drupal site whose `pm:list` was fatal,
and an unknown framework. The `add_on_updates == []` path is the empty-input shadow.

**R2.6 — the D8 mechanical check, new here.** `gather_framework` touches **no** `RunState`. There
MUST be a test that calls it with **no `sc.run_state` bound at all** (`monkeypatch.delattr(sc,
"run_state", raising=False)`, or a `reset_sc` variant) and gets a clean return. This is the first
time `CAMPAIGN.md` §3.4's parallel-ready criterion has had a mechanical check rather than a review
criterion, and it is exactly PD#14 — an instrument that can go red.

**R2.7 — CAMPAIGN.md amendment: NONE.** None of B33, B34, B35, B36 appears on §3.3's stay-list
(**verified**). B37 stays and is on the list; it is untouched.

---

### 5.3 `fetch_site_domains` + `resolve_site_url` — `psh/cli.py:635-686` and `694-718` → `psh/cli.py`

**Ranges (verified).** 635 = `# The set of Cloudflare-proxied FQDNs (fqdns.json) is …`;
686 = the `)` closing `site_context.add_notice(`. 694 = `# The Drupal multisite probe (was B30,
inline here) moved to`; 718 = `sc.debug(f"Site URL for {site['name']}:    {site_url}")`.
52 raw / 44 logic and 25 raw / 18 logic.

**Block IDs.** First range: **B29** (`terminus("domain:list")`; `classify_domains` → `facts`; the
`no-domains` alert). Second range: **B30 (residue)** (the multisite-smell pickup and the
`no_primary_domain_notice` emission, after I10 moved the probe to `check/drupal/multisite.py`),
the **`site_url` derivation part of B31**, and **B32 (residue)** (the WP-network URL threading,
after I9 moved `wordpress_network_url` to `psh/gather.py`). Lines 688-692 (**B31**'s
`stuff_dns_contract` + `invoke_hooks("site_post_dns")`) stay — stage spine (R-G2).

**R3.9 — one commit, two functions.** The two ranges MUST land in **one commit**, because the
first deletes the three aliases (`main_fqdn`/`custom_domains`/`primary_domain`, 664-666) that the
second consumes. They MUST remain **two functions**, because the stage spine at 688-692 sits
between them and stays in `main()`.

**Destination rationale.** `psh/cli.py`, **not** `psh/dns_classify.py`. That module's docstring
bars it (**verified at `psh/dns_classify.py:1-9`**): *"Pure data producer for the site_post_dns
contract … Presentation (notices) lives in check/dns/, not here."* `fetch_site_domains` both makes
a `terminus` call and emits a `Notice`. `NOTICE_NO_DOMAINS` is registered at **`psh/cli.py:141`**
(**verified**) and `no_primary_domain_notice` — the same shape of helper — already lives at
`psh/cli.py:295-334` (**verified**).

**Signatures and return types.**

```python
class SiteDomains(NamedTuple):
    domains: object               # raw domain:list payload; never None (a fatal fetch returns None instead)
    facts: dns_classify.DnsFacts  # all-empty when `domains` is not a dict


def fetch_site_domains(live_site, site, site_name, site_context) -> SiteDomains | None:
    """None = fatal/undecodable fetch; the caller SKIPS the site."""


class SiteUrlFacts(NamedTuple):
    site_url: str      # "" when there is no main_fqdn and no WP-network URL
    wp_smell: str      # "" = no NEW smell -- a delta
    drush_smell: str   # "" = no NEW smell -- a delta


def resolve_site_url(site, live_site, site_context, facts) -> SiteUrlFacts:
    """Never None -- this region has no skip path."""
```

**R3.1** `fetch_site_domains` returns the **skip sentinel** `None` on a fatal or undecodable
`domain:list`; `main()` does the `continue` (R-G3).

**R3.2** The three aliases at 664-666 are **deleted**, not returned. `main()` holds `facts` for
line 691 anyway, and `facts.main_fqdn` / `facts.custom_domains` / `facts.primary_domain` read fine
at the three surviving sites inside the second helper.

**R3.3** `site_url = ""` at line 650 is **deleted** (it becomes dead once `resolve_site_url`
returns the value). `resolve_site_url` initializes it internally. Net across both helpers: **five**
locals eliminated from `main()` (`site_url`'s early binding, the three aliases, and `cf_on`/`cf_ctx`
which move wholly inside — counting the pair as one).

**R3.4** The Cloudflare gate resolution at 653-654 (`cf_on = cloudflare_enabled()`,
`cf_ctx = sc.plugin_context["plugin.cloudflare"] if cf_on else {}`) moves **inside**
`fetch_site_domains` unchanged. The `.get("fqdn_zone_conflicts", {})` defensive read at 661 moves
verbatim.

**R3.5** `resolve_site_url` returns **two** smell deltas (R-G5): `wp_smell` from
`wordpress_network_url` (712-713) and `drush_smell` from the `drupal_multisite_smell` contract-key
pickup (698-700). The `.get(...)` reads at 698 and 702 MUST stay `.get(...)` — those keys are
hook-produced, not registry-owned, and are absent when the probe did not run.

**R3.6 — Invariant 8, itemized. This is the single highest-risk paragraph in the increment.**

The `NOTICE_NO_DOMAINS` html/text literal appears in **3 of the 4** e2e goldens — `test_golden`,
`test_golden_drupal`, `test_golden_nonumich`, and **not** `test_golden_cdn_change` (**verified by
grep for `is on a paid plan but does not have` across `tests/e2e/__snapshots__/`**). The tripwire is
therefore **live** — strictly better cover than the `no_primary_domain_notice` precedent, whose
literal is in **zero** goldens.

What must not change (**measured, not estimated**): every interior line of `html=` and `text=`
keeps exactly **16 leading spaces, including both closing `"""`**. Today, inside `main()`, the
`html=`/`text=` keywords sit at column **28** and their continuation lines at **16** — already
*less* indented than the keyword. Measured line-by-line:

```
psh/cli.py  col  content
   674       28  html=f"""
   675       16      <p>{site["name"]} is on a paid plan but does not have any custom …
   676       16      a domain through which people will access the site or downgrade …
   677       16      money.</p>
   678       16      """,
   679       28  text=f"""
   680-683    16      (four text lines)
   684       16      """,
```

In a module-level helper the frame shifts: `Notice(` lands at column 16, its keyword arguments at
column **20**, and the interior lines **MUST still be 16** — one column *less* than the keyword.
That looks wrong and is required. The precedent is `no_primary_domain_notice` at
`psh/cli.py:313-332`, where `html=`/`text=` sit at column **12** inside a frame whose `return
Notice(` is at 8, and every interior line sits at **20** (**verified**).

**R3.6a** The implementer MUST add a sentinel comment at the new `def` naming Invariant 8 and the
three goldens, so the next formatter run cannot silently re-indent the block and re-email every
site owner a differently-indented alert.

**R3.6b** The two `if`s at 667-668 stay **nested**, with the `# noqa: SIM102` and its full reason
comment verbatim. The outer `isinstance(domains, dict)` guard is **load-bearing, not defensive**:
`facts.custom_domains` is `[]` for *any* non-dict payload, so removing the guard emits a false
"paid plan with no custom domains" **alert** to the owner. That branch has **no test at any tier**
and MUST get one here (a non-dict `domains` payload → no notice added).

**R3.6c — evidence beyond the goldens (PD#14).** See §8 R8.3: the new unit test MUST assert
`all(line.startswith(" " * 16) for line in notice.html.splitlines()[1:] if line.strip())` and the
task MUST compare the pre/post `ast.get_source_segment` of the `Notice(...)` call. **`git diff -w`
is not acceptable evidence** — `CLAUDE.md` § Conventions & gotchas: a line that only gained leading
whitespace is exactly what `-w` is designed to ignore.

**What `main()` keeps:**

```python
            fetched = fetch_site_domains(live_site, site, site_name, site_context)
            if fetched is None:
                continue  # fatal/undecodable domain:list -- skip this site (D-i6-1)
            domains, facts = fetched

            # Per-phase data contract (see CLAUDE.md): publish the DnsFacts via the pure helper
            # (unit-tested against value-swaps in test_dns_classify.py), then fire the phase. The
            # check.dns hook consumes these keys to emit the DNS-resolution notices.
            dns_classify.stuff_dns_contract(site_context, domains, facts)
            sc.invoke_hooks("site_post_dns", site_context)

            url_facts = resolve_site_url(site, live_site, site_context, facts)
            site_url = url_facts.site_url
            if url_facts.wp_smell != "":
                wp_smell = url_facts.wp_smell
            if url_facts.drush_smell != "":
                drush_smell = url_facts.drush_smell
```

**R3.7 — shadow paths (PD#3).** Nil: a fatal `domain:list` → `None` → skip. Empty: `domains == {}`
→ `facts.custom_domains == []` → the `no-domains` alert fires. Upstream error: `domains` is a
non-dict (a JSON list, a string) → the `isinstance` guard suppresses the alert (R3.6b).

**R3.8 — CAMPAIGN.md amendment: ONE, narrowing B31.** B29, B30, B32 are **not** on §3.3's
stay-list (**verified**). **B31 is** ("phase firing and contract stuffing (B27, B28, **B31**,
B37, B52)"). The amendment narrows B31 to mean its `stuff_dns_contract` + `invoke_hooks` seam
only; the `site_url` derivation that also lives in B31's baseline range moves. See §7 R7.4.

---

### 5.4 `resolve_site_roster` — `psh/cli.py:495-499` + `510-528` → `psh/cli.py`

**Ranges (verified).** 495 = `try:` (wrapping `terminus_data("org:site:list", …)`);
499 = `site_count = len(sites)`. 510 = `site_name_to_id = {site["name"]: site_id for …}`;
528 = the `)` closing the resume `sc.console.print`. 5 + 19 raw, 5 + 15 logic.

**Block IDs.** **B14** in full (*"`terminus_data("org:site:list")`; run accumulators; `smtp_enabled`;
sorted site names; `sites_from_resume_point`"* — the run accumulators moved to `RunState` at I13,
so what is left is the roster plus `smtp_enabled`).

**The proposed range is not contiguous; two statement moves make it so.**

**R5.4.1 — hoist 501-509.** The Cloudflare/SMTP `sc.debug` banners and the `smtp_enabled`
assignment move to **immediately after line 493** (`sc.debug(f"Generating report for …")`). This
is a zero-data-dependency statement move: neither line reads `sites`, `site_count`, or
`site_name_to_id`. Its **only** observable effect is console ordering on one failure path — if
`org:site:list` fails, the two banners now print *before* the `Could not list organization sites`
exit instead of not at all. Both are `sc.debug`, so both are invisible without `-v`.
`CAMPAIGN.md` §8 sanctions this explicitly: *"stdout / console / error messages | MAY improve
freely"*.

**R5.4.2 — relocate `current_site_number = 1` (line 500)** down to the pre-loop prologue, beside
`site_name = None` / `site_emailed = False` at 530-531 and **before** `try:`. It MUST NOT go
inside the loop (it increments once per processed site at 564).

**Destination rationale.** `psh/cli.py`, **not** `psh/lifecycle.py`. That module's docstring pins
its module-level imports (**verified at `psh/lifecycle.py:36-37`**): *"Module-level imports here
are stdlib + sqlalchemy.exc + rich only."* Importing `psh.gateway` there would need a third
call-time `# noqa: PLC0415` bridge. `psh/cli.py` already imports all four names this helper uses
(`terminus_data`, `TerminusError`, `sites_from_resume_point`, `ResumeSiteNotFoundError`) — zero
import churn.

**Signature and return type.**

```python
class SiteRoster(NamedTuple):
    sites: dict                  # org:site:list payload keyed by site id
    name_to_id: dict[str, str]
    site_names: list[str]        # sorted, resume-filtered
    site_count: int              # len(sites) BEFORE the filter -- the banner/finish_run denominator, NEVER len(site_names)


def resolve_site_roster(org_id: str) -> SiteRoster: ...
```

**R5.4.3** `site_count` is `len(sites)` **before** the resume filter. It is the denominator of both
the per-site banner (`Pantheon site N of M`) and `finish_run`'s `Email sent for N of M sites`.
There MUST be a test that fails if it is "tidied" to `len(site_names)`.

**R5.4.4** `resolve_site_roster` reads `sc.options.resume_from` and `sc.config` at call time (the
house rule); `org_id` is a parameter because the error message at 523 interpolates it and passing
it keeps the helper's contract legible.

**R5.4.5** The two `sys.exit` paths move with the code: the `TerminusError` exit (498) and the
`ResumeSiteNotFoundError` exit (521-524). Both keep their exact messages (PD#2 — every error has
a name; both are already named exception classes).

**What `main()` keeps:**

```python
    sc.debug(f"Generating report for {start_date} through {end_date}")

    sc.debug(
        "Cloudflare is "
        + ("[bold green]enabled" if cloudflare_enabled() else "[bold red]DISABLED")
    )
    smtp_enabled = bool(sc.config.get("SMTP", {}).get("enabled"))
    sc.debug(
        "SMTP sending is "
        + ("[bold green]enabled" if smtp_enabled else "[bold red]DISABLED")
    )

    roster = resolve_site_roster(sc.config["Pantheon"]["org_id"])
    sites = roster.sites
    site_name_to_id = roster.name_to_id
    site_names = roster.site_names
    site_count = roster.site_count  # len(sites) BEFORE the resume filter -- never len(site_names)

    site_name = None
    site_emailed = False
    current_site_number = 1
    try:
        for site_name in site_names:
            site_emailed = False
            ...
```

**R5.4.6 — coverage; the strongest case of the six.** `--resume-from` requires `--all`, which is
in `tests/conftest.py`'s `FORBIDDEN_FLAGS`, so the whole resume-filter region is unreachable at
the subprocess tier **permanently, by design**. Nothing today would go red if `site_count` were
changed to `len(site_names)`, which silently changes both the resume banner and `finish_run`'s
"Email sent for N of M sites" on **every** resumed run.

**R5.4.7 — shadow paths (PD#3).** Nil: `org:site:list` raises `TerminusError` → `sys.exit`.
Empty: `sites == {}` → `site_names == []`, `site_count == 0`, no resume banner. Upstream error:
`resume_from` names a site not in the roster → `ResumeSiteNotFoundError` → `sys.exit` with the
count in the message.

**R5.4.8 — CAMPAIGN.md amendment: ONE.** B14 is on §3.3's stay-list (*"the site-loop skeleton
(skips, banner, sorted order, resume filter — **B14**–B18, B20, B25, B42)"*). See §7 R7.2.

---

### 5.5 `resolve_site_plan` — `psh/cli.py:566-574` + `581-586` → `psh/plans.py`

**Ranges (verified).** 566 = `plan_name = resolve_plan_name(site)`; 574 = the Sandbox-skip
`continue`. 581 = `if site["plan_name"] not in plan_names:`; 586 = `sys.exit("Bailing out.")`.
9 + 6 raw, 8 + 6 logic.

**Block IDs.** **B17 (residue)** (the `resolve_plan_name` call site and the `site["plan_name"]`
write-back; the SKU logic itself moved to `psh/plans.resolve_plan_name` at I7), the **Sandbox-skip
half of B18**, and **B20** (the unknown-plan guard).

**R5.5.1 — this is deliberately two-thirds smaller than "the per-site preamble."** Lines 537-564
(smell resets, the U-M portal gate, the site-selection skip, the banner) are §3.3 stay-list content
verbatim — *"the site-loop skeleton (**skips, banner**, sorted order, resume filter)"* is precisely
the thing §3.3 exists to keep. They stay.

**Destination rationale.** `psh/plans.py`. `resolve_plan_name` (which this wraps) already lives
there (**verified at `psh/plans.py`**), the module already imports `sys`, `sc`, `terminus`, and
`escape` — every name this helper needs — and §3.1 assigns *"SKU resolution (B17)"* to it.

**Signature.**

```python
def resolve_site_plan(site: dict, plan_names: list[str]) -> str | None:
    """Plan name, or None when the site must be SKIPPED (transient plan:info failure, or
    Sandbox).  Both skip paths print their own message.  sys.exit("Bailing out.") on a plan
    absent from the catalog -- a POSTCONDITION, not a caller concern.  Writes
    site["plan_name"] in place."""
```

**R5.5.2** The return is the **skip sentinel** `None` for **two** distinct conditions — a transient
`plan:info` failure (which `resolve_plan_name` already reports) and the Sandbox plan (which prints
its own `is on the Sandbox plan, skipping it.` line). `main()` does the `continue` for both
(R-G3). Collapsing two skip reasons into one sentinel is acceptable **because each prints its own
operator message before returning** (PD#1 — the failure is visible); the docstring says so.

**R5.5.3** `sys.exit("Bailing out.")` on an unknown plan is a **postcondition of the helper**, not
something the caller checks. It keeps its exact `ATTENTION: {name} is on an unknown plan: {plan}`
console line.

**R5.5.4 — B20 moves above `sc.SiteContext(site)`, and this is provably identical.** Today the
unknown-plan guard (581-586) runs **after** `site_context = sc.SiteContext(site)` (579). Folding
B20 into the helper moves it **before**. **Verified** at `script_context.py:115-116`:
`SiteContext.__init__` is exactly `super().__init__(site=site, notices=[], sections=[],
attachments=[])` — no console output, no `sc` write, no `run_state` write — and on the bail path
the object is discarded unread. The implementer MUST re-confirm this against `script_context.py`
at implementation time and say so in the task report (PD#14: verify, do not assume — the class
may have gained a side effect since this spec was written).

**R5.5.5** The helper **writes `site["plan_name"]` in place**, exactly as line 569 does today.
Hooks reach the same `site` object through `site_context["site"]`, but no hook has fired for this
site yet at this point in the loop, so no hook can observe the pre-write value.

**R5.6 — `sc.SiteContext(site)` STAYS in `main()`.** Its position is a documented invariant *of
the loop* — `CLAUDE.md`: *"constructed once per processed site, as far up the per-site loop as
possible (after the portal/not-requested/Sandbox skips)"*. Burying the constructor in a helper
hides that from the only code that can honor it, and the next skip added would have no local
signal about which side of the line it belongs on. `BLOCKMAP.md` pairs the Sandbox skip and the
`SiteContext` creation as B18, but they have **different owners**; splitting B18 along that line is
what keeps the amendment narrow.

**What `main()` keeps:**

```python
            plan_name = resolve_site_plan(site, plan_names)
            if plan_name is None:
                continue
            site_current_plan = plan_name

            # This site will be processed: build its context as far up as possible (past the
            # portal / not-requested / Sandbox skips above).  notices/sections/attachments
            # accumulate into it through the pipeline below.
            site_context = sc.SiteContext(site)
```

**R5.5.6 — coverage.** The unknown-plan `sys.exit("Bailing out.")` is untested; reaching it today
needs a hand-authored terminus fixture plus a subprocess run that must abort.

**R5.5.7 — shadow paths (PD#3).** Nil: `resolve_plan_name` returns `None` → helper returns `None`.
Empty: `plan_names == []` → every plan is unknown → `sys.exit`. Upstream error: an Elite site whose
`plan:info` is fatal → `None` → skip.

**R5.5.8 — CAMPAIGN.md amendment: a SPLIT plus one.** **B18** and **B20** are both on §3.3's
stay-list. B18 splits (Sandbox skip moves; `SiteContext` creation stays); B20 moves entirely. See
§7 R7.3.

---

### 5.6 `validate_options` — `psh/cli.py:399-428` → `psh/cli.py`

**Range (verified).** 399 = `# Validate and process arguments.  The --resume-from guards come
first: …`; 428 = the `)` closing the `--update-cloudflare-fqdns` `sys.exit`. 30 raw / 21 logic
lines.

**Block ID.** **B5** (*"Arg validation (`--resume-from` guards, sites-or-all, fqdns flag)"*).

**Destination rationale.** `psh/cli.py`. `CAMPAIGN.md` §3.1's `psh/cli.py` row already names it:
*"`build_arg_parser`, `parse_args`, **arg validation (B5)**, `main()` orchestrator"* — the block is
assigned to this module; it has simply never been a separate def.

**Signature.**

```python
def validate_options() -> None:
    """B5: the four argument guards, in their shadowing order.  Each guard calls
    sys.exit(<message>).  NOT pure: the --create-tables branch sets sc.options.verbose = 3.
    Reads sc.options/sc.config at call time, so main() must call it AFTER process_config()."""
```

**R6.1 — no parameters.** `sc.options`/`sc.config` at call time is the house rule and is exactly
how `tests/unit/test_argparse_contract.py` already drives `sc.smtp_username()` (**verified at
`tests/unit/test_argparse_contract.py:42-48`**).

**R6.2 — the call site does not move.** `validate_options()` is called from the exact position the
guards occupy today: after `validate_hooks()` (393-397) and before the verbose banner (430). It
MUST be after `process_config()` pass 1 (383), because the fourth guard reads `sc.config`.

**R6.3 — the four guards keep their shadowing order** (exhaustive, in order):
1. `--resume-from` + `--create-tables` are mutually exclusive.
2. `--resume-from` requires `--all`.
3. `--create-tables` + `--import-older-metrics` are mutually exclusive; **else** the
   sites-or-`--all` check. (Note the `elif`: the `--create-tables` branch also sets
   `sc.options.verbose = 3`.)
4. `--update-cloudflare-fqdns` requires `[Cloudflare].enabled`.

Guards 1 and 2 come first because 3's `sys.exit` would otherwise shadow their more precise
messages.

**R6.4 — the 399-402 comment.** It stays at the **call site** (it documents a sequencing decision
of `main()`), and the helper's docstring states the shadowing order. The implementer **MAY**
rewrite the comment's two occurrences of the word "below" to name `validate_options()`, because a
comment pointing at code that is no longer beneath it is a stale pointer (PD#8's *"a stale diagram
is worse than none"*, applied by analogy). This is a MAY, not a MUST: it is wording only.

**What `main()` keeps:**

```python
    # Validate and process arguments.  The --resume-from guards come first: the create-tables and
    # sites-or-all checks below both exit before they would be reached, shadowing these more
    # precise messages.  --create-tables never runs the site loop, so a --resume-from on it would
    # be silently dropped; reject it instead.
    validate_options()
```

**R6.5 — coverage.** The `--update-cloudflare-fqdns` guard has **no test at any tier**: no file
under `tests/` contains its exit message (**verified**; the flag *string* does appear in
`tests/integration/test_plugin_cloudflare_fqdns.py`, but those tests drive the plugin's refresh
rules, never `main()`'s guard). It is not interlock-blocked — merely never exercised.
`sc.options.verbose == 3` after `--create-tables` is likewise unobservable today. The shadowing
order becomes a **table-driven `pytest.mark.parametrize`** over the flag combinations instead of
eight subprocess boots.

**R6.6 — shadow paths (PD#3).** Nil: no flags at all → `sys.exit("You must specify either at least
one site or the --all option.")`. Empty: `sc.config` with no `[Cloudflare]` section → the `.get`
chain MUST NOT `KeyError` (this is why the guard is written `sc.config.get("Cloudflare",
{}).get("enabled")`). Upstream error: `--create-tables` with `--import-older-metrics` → the
mutual-exclusion exit.

**R6.7 — CAMPAIGN.md amendment: ONE.** B5 is on §3.3's stay-list, and `CLOSING-AUDIT.md` Q1's
stay-list walk names the guards explicitly. See §7 R7.1.

---

## 6. DECLARED SEAMS — normative, one line per task

`prompts/implementation-standards.md` § *TDD override*: *"**the spec declares the seams** … A task
whose spec names no seam is `NEEDS_CONTEXT`, not a licence to pick one."* This section is that
declaration. Each row is written so a fresh implementer can copy it into a test without further
judgment. **Every seam named here already exists in this codebase**; this increment creates no new
mock seam.

| Task | Seam under test | Tier | How to reach it |
|---|---|---|---|
| **1** | `psh.traffic.build_traffic_window` — called directly | `unit` | Pure data in: a `list[TrafficRow]`, two `datetime.date`s, two `str`s. **No I/O, no monkeypatching.** `sc.options`/`sc.console` come from the autouse `reset_sc` fixture. Add `tests/unit/test_traffic_window.py`. Hypothesis is available (see `tests/unit/test_traffic_aggregation.py` for the house idiom). |
| **2** | `psh.gather.gather_framework` — called with an `sc.SiteContext` | `integration` | Patch **BOTH** `psh.gateway.run_terminus` (the `gateway` conftest fixture) **AND** `psh.gather.run_terminus` — `psh/gather.py` binds `run_terminus` in its own namespace for `gather_drupal`'s composer dry-run, and a test that patches only the former makes **real** Terminus subprocess calls. See `tests/integration/test_gather_drupal.py`'s docstring. Add `tests/integration/test_gather_framework.py`. |
| **3** | `psh.cli.fetch_site_domains` and `psh.cli.resolve_site_url` — called with an `sc.SiteContext` | `integration` (+ one `unit` file for the notice literal) | Two existing seams: `psh.gateway.run_terminus` (the `gateway` fixture) for `domain:list` and the WP-network `wp_eval`, and **`psh.dns_classify.resolve`** for every A/AAAA lookup (`tests/helpers/dnsfake.py`'s `make_resolver`/`patch_resolve`). `cloudflare_enabled` is monkeypatched on `sc`, never assigned directly (see the `reset_sc` note in `CLAUDE.md`). Add `tests/integration/test_site_domains.py`; put the Invariant-8 column assertion in `tests/unit/test_no_domains_notice.py`. |
| **4** | `psh.cli.resolve_site_roster` — called directly | `integration` | `psh.gateway.run_terminus` (the `gateway` fixture) reaches `terminus_data("org:site:list", …)` through `psh.gateway`'s own `terminus`. `sc.options.resume_from` is set via `reset_sc.options = psh.parse_args([...])`. Use `recording_console(monkeypatch, sc, width=80)` for the resume banner — production's non-tty width, per `CLAUDE.md`'s rich gotcha. Add `tests/integration/test_site_roster.py`. |
| **5** | `psh.plans.resolve_site_plan` — called directly | `integration` | `psh.gateway.run_terminus` (the `gateway` fixture) for the Elite-SKU `plan:info` call inside `resolve_plan_name`; a non-Elite `site` makes **no** subprocess call at all. `sc.config["Pantheon"]["plan_sku_to_name"]` from `reset_sc`. Add `tests/integration/test_resolve_site_plan.py`. |
| **6** | `psh.cli.validate_options` — called directly | `unit` | `sc.options = psh.parse_args([...])` plus a minimal `sc.config` dict, then `pytest.raises(SystemExit)` on the message. This is the exact idiom of `tests/unit/test_argparse_contract.py`. **No subprocess, no `run_program`.** Add to `tests/unit/test_argparse_contract.py` or a sibling `tests/unit/test_validate_options.py`. |

**Seam rules that bind every row (exhaustive):**

- **S1.** The two-binding trap is real and silent: `from X import f` binds the *importer's* name.
  Row 2's double patch is not optional.
- **S2.** No test in this increment may call `main()`. It has no in-process caller today (§1.2) and
  this increment does not add one.
- **S3.** No test may pass `--all`, `-a`, or `--for-real` to `run_program()`, or run a live
  `--create-tables`/`--import-older-metrics`. `run_program()` fails closed; **NEVER bypass it.**
- **S4.** If an implementer discovers mid-task that the declared seam does not hold, that is
  `DONE_WITH_CONCERNS`/`BLOCKED` — **never** an improvised seam.

---

## 7. Documentation amendments — the normative brief for Task 7

Task 7 is a **documentation-only** increment. It MUST NOT be performed by Tasks 1-6, and Tasks 1-6
MUST NOT edit `CAMPAIGN.md`, `LEDGER.md`, `CLOSING-AUDIT.md`, or `README.md`.

**R7.1 — `CAMPAIGN.md` §3.3, B5.** Amend so the **bootstrap call *sequence*** stays and the
**guard bodies** move. The two-pass substitution order — which is what §3.3 says "is the program"
— is unaffected: `validate_options()` is still called from the same position.

**R7.2 — `CAMPAIGN.md` §3.3, B14.** Amend so **roster resolution moves** and the **loop skeleton
stays**. B14's `smtp_enabled` and the accumulator bindings are not part of the move (the
accumulators already left at I13; `smtp_enabled` is hoisted, not extracted — §5.4 R5.4.1).

**R7.3 — `CAMPAIGN.md` §3.3, B18 split + B20.** Amend so **B18 splits**: the Sandbox skip moves,
the `SiteContext` creation stays (with §5.5 R5.6's reasoning recorded, because it is the
non-obvious half). **B20 moves** entirely.

**R7.4 — `CAMPAIGN.md` §3.3, B31 narrowed.** Amend so B31 means its `stuff_dns_contract` +
`invoke_hooks("site_post_dns")` **seam**; the `site_url` derivation that shares its baseline range
moves.

**R7.5 — `LEDGER.md`.** One entry per amendment plus the increment entry, using §12's template
verbatim (`## I<N> — <slug> (<date>, commit <sha>)` with `Moved:` / `Deviations from CAMPAIGN.md:`
/ `Contract/config/sc additions:` / `Discovered tasks:` / `Open questions for next increment:`).
This increment is **post-campaign**, so it is not `I<N>`-numbered; use a dated heading and say so
in the entry.

**R7.6 — `CLOSING-AUDIT.md` Q1: a CORRECTION, not an amendment.** Q1's stay-list walk contains two
errors, both **verified** in this task:

1. Its "Phase firing + contract stuffing (B27, B28, B31, B37, B52)" row is discharged in part by
   *"the gather threading + `stuff_gather_contract` + `invoke_hooks("site_post_gather")"`* — but
   the §3.3 row it is walking names only **B37**. "The gather threading" is B33/B34 (residue)/B35
   (residue)/B36, which is **not** stay-list content.
2. The same row lumps *"`classify_domains`"* (**B29**, not on the list) in with
   *"`stuff_dns_contract` + `invoke_hooks("site_post_dns")"`* (**B31**, on the list).

Record **D-i14d-1 as discharged**, with the re-measured raw/logic count from §9.

**R7.6a — `README.md`: the D-i14d-1 TODO is ALREADY STRUCK.** Commit `5b92ee1` (2026-08-07 06:54)
removed it. Task 7 MUST verify this (`grep -n 'D-i14d-1' README.md` returns nothing) and MUST NOT
re-add or re-strike it. Recording the discharge lives in `CLOSING-AUDIT.md` (R7.6) and `LEDGER.md`
(R7.5) instead.

**R7.7 — `README.md`: give the orphaned pathlib deferral a home.** Add a TODO recording that four
`noqa` comments in `main()` (`psh/cli.py:373, 437, 438, 470`) defer a pathlib migration to
"I14b+", that I14b's ledger entry never touched PTH, and that neither `README.md` nor `CLAUDE.md`
mentions it. PD#9: *"Everything deferred is written down. Vague intentions are lies."*

**R7.8 — `CLAUDE.md`.** Three additions:
1. The new helper roster per module — `psh/traffic.py` gains `build_traffic_window`/`TrafficWindow`;
   `psh/gather.py` gains `gather_framework`/`FrameworkGather`; `psh/plans.py` gains
   `resolve_site_plan`; `psh/cli.py` gains `validate_options`, `resolve_site_roster`/`SiteRoster`,
   `fetch_site_domains`/`SiteDomains`, `resolve_site_url`/`SiteUrlFacts`.
2. **Why `SiteContext` construction did *not* move** (§5.5 R5.6).
3. The **new rule**: no extracted helper may be the sole assigner of `site_name` or `site_emailed`
   (R-G4), with the concrete failure scenario.

Task 7 is also bound by `prompts/implementation-standards.md` § Definition of Done: *"`CLAUDE.md`
prose that existed to explain logic this task moved into a package is deleted in the same commit.
Report the line-count delta."* The `wp_smell`-vs-`main()`-local warning in the contract table is
the candidate — but it is **EXEMPT** prose (it records a shipped defect's root cause) *unless* a
named test already guards it, in which case it reduces to a one-line pointer at that test. Task 7
MUST make that determination explicitly rather than by default.

---

## 8. Verification

### 8.1 Per commit, in order (exhaustive)

1. **`./run-tests --fast`** — the new unit/integration tests go **red before** the extraction and
   **green after**. `mattpocock-skills:tdd`, **not** `superpowers:test-driven-development`.
   Refactoring is **not** part of the red→green loop; it belongs to review. **Watch the test fail
   for the right reason** — a test that passes the moment it is written is testing existing
   behavior (PD#14).
2. **`./run-tests`** (full) — **the four e2e goldens MUST be byte-identical.** A golden going red
   is a defect in the increment, never a refresh (Invariant 1). `--update-goldens` MUST NOT run.
3. **ruff + pyright** are gates *inside* `./run-tests` and abort before pytest. A missing pyright
   binary is a hard failure, never a silent skip.
4. The command **and its output** are pasted in the task report — evidence, never "should pass" or
   a summarized "green" (`prompts/implementation-standards.md` § Definition of Done).

### 8.2 Never run

`./run-tests --record` (Invariant 10 — `tests/fixtures/terminus-cdnchange/` is hand-maintained)
and `./run-tests --update-goldens` (Invariant 1).

### 8.3 Extraction 3 only — Invariant 8 evidence beyond the goldens

Both are required, and **`git diff -w` is not acceptable for either**:

```python
# in the new unit test
assert all(
    line.startswith(" " * 16)
    for line in notice.html.splitlines()[1:]
    if line.strip()
)
```

and a pre/post comparison of `ast.get_source_segment(source, notice_call_node)` for the
`Notice(...)` call, proving the literal's interior bytes are unchanged.

### 8.4 Whole-increment gate

1. `/code-review` (or `prompts/adversarial-review.md`) over the whole branch, with fresh context.
2. A full `./run-tests` on the final state, output pasted.
3. A **re-measure** of `main()`'s raw/logic line count using §9's snippet, pasted into the ledger
   entry. The number is recorded, not gated (§9).

---

## 9. Measurement baseline (PD#14 — measured, not recalled)

Measured against `psh/cli.py` at commit `c01e77b`, using `CLOSING-AUDIT.md` Q1's snippet:

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

Per-extraction removal, measured:

| # | Range(s) | raw | logic |
|---|---|---|---|
| 1 | 770-808 | 39 | 23 |
| 2 | 720-759 | 40 | 32 |
| 3 | 635-686 + 694-718 | 77 | 62 |
| 4 | 495-499 + 510-528 | 24 | 20 |
| 5 | 566-574 + 581-586 | 15 | 14 |
| 6 | 399-428 | 30 | 21 |
| **Total removed** | | **225** | **172** |

`main()` after removal but before the replacement call sites: **397 raw / 273 logic**. The §5
replacement blocks add back roughly **60 raw / 55 logic**, projecting `main()` at **≈455 raw /
≈330 logic**. The plan estimated 437/345.

**None of these numbers is a gate.** §3.3's 250-400 target was answered as a recorded deviation at
close; this increment moves toward it and records the measured result (§8.4 item 3). An
implementer MUST NOT compress a replacement block, or skip a comment, to hit a number.

---

## 10. Corrections to the plan (verified; PD#14 / `prompts/new-feature-standards.md`)

Every claim below was re-verified against the authority named. Where the plan is wrong, **this
spec is written to the truth** and the implementer follows this spec.

1. **`README.md:260-267` no longer holds D-i14d-1.** The TODO was struck in commit `5b92ee1`
   earlier the same day. Lines 260-267 of `README.md` now hold the `uvx pyright@1.1.411` TODO.
   Consequence: §7 R7.6a.
2. **"seven per-line `# noqa: B023` suppressions" is six.** Measured at `psh/cli.py:817-835`:
   `site`, `visits_by_month`, `plan_on_day`, `site_plan_start`, `first_plan_day`, `last_plan_day`.
   `plan_info` (824) carries none. Consequence: §5.1 R1.4 says six. The rule is unchanged.
3. **`B34r` / `B35r` are not block IDs.** No campaign document defines them (grep across
   `development/2026-07-17-modularization-campaign/*.md` returns nothing). This spec writes
   `B34 (residue)` / `B35 (residue)` and defines *residue* in the Glossary.
4. **"the `--update-cloudflare-fqdns` guard … grep finds it only at `psh/cli.py:425` and
   `plugin/cloudflare/fqdns.py:205`" is imprecise but the substantive claim holds.** The flag
   *string* also appears in `tests/integration/test_plugin_cloudflare_fqdns.py:231,268,329` and in
   the parser definition at `psh/cli.py:264-276`. The *guard's exit message* appears in **no** file
   under `tests/`. Consequence: §5.6 R6.5 states it precisely.
5. **Everything else in the plan verified true**, specifically: the six line ranges all still match
   `psh/cli.py` exactly; the `NOTICE_NO_DOMAINS` literal is in exactly 3 of the 4 goldens;
   `psh/traffic.py` already imports from `psh.plans` (line 27), so extraction 1 adds no cycle;
   `NOTICE_NO_DOMAINS` is registered at `psh/cli.py:141`; `no_primary_domain_notice`'s literal sits
   at column 20 inside a frame at 8/12 while the `no-domains` literal sits at 16 inside a frame at
   28, exactly as the plan describes; `main()` has no in-process caller in the suite;
   `psh/lifecycle.py`'s docstring pins its module-level imports to stdlib + `sqlalchemy.exc` +
   `rich`; `psh/dns_classify.py`'s docstring bars presentation; `psh/gather.py:11-13` is the
   smell-merge authority; `main()` is 622 raw / 445 logic; the block-ID → §3.3 stay-list membership
   is as the plan states for all six extractions.

---

## 11. Closing audit questions (queued for after implementation)

1. Did any of the six extractions produce a helper that `main()` calls but that no test reaches
   independently of `main()`? (If so, the extraction bought nothing.)
2. Is R-G4 (the `site_name`/`site_emailed` sole-assigner rule) mechanically checkable, or does it
   remain prose? A `tests/integration/test_regressions.py`-style AST assertion over `main()`'s
   source is the candidate instrument; PD#14 asks whether it can go red.
3. With the six locals-groups now objects, does D-i12-2's *"a ~25-parameter function"* objection to
   extracting `template_dict` still hold? (§2.2 defers this deliberately.)
4. Did the measured post-increment raw/logic count land inside §3.3's 250-400 target, and if not,
   is the remainder stay-list content?

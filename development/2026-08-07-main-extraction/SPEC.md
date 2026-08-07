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
| The five per-site skip gates | **Reached but never asserted on.** `tests/e2e/test_unknown_framework_e2e.py` and the four goldens each run a single named site through `run_program`, so the loop *is* entered and the portal / not-in-list / Sandbox gates *are* evaluated — no test asserts on their outcome, and no test reaches the not-taken branch of any of them. |
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
3. **§5.3 must land as one commit** even though it is three functions (§5.3 R3.9).
4. The middle four are ordered by ascending amendment surface: §5.2 (no amendment) → §5.3
   (one, narrowing B31) → §5.4 (one, B14) → §5.5 (**three** — B17, the B18 split, and B20).

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
stage **bodies** move.

**Line-range convention, used identically everywhere in this spec:** a spine range names the
`stuff_*`/`invoke_hooks` statements **together with the explanatory comment immediately above
them**, because the comment travels with the call. Exhaustive list of the spine ranges that stay:
**627-628** (`stuff_envs_contract` + `site_pre`), **630-633** (`stuff_traffic_contract` +
`site_post_traffic`), **688-692** (`stuff_dns_contract` + `site_post_dns`), **761-766**
(`stuff_gather_contract` + `site_post_gather`), **894-908** (`stuff_plans_contract` +
`site_pre_render`). §5.2 and §5.3 use these same numbers.

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

**R-G6 — the no-move list (exhaustive).** These stay in `main()`. **Two sub-rules, because they
are different claims:** the rows in the first table stay *in their current position* (their line
numbers are pinned relative to what surrounds them); the rows in the second table stay *in
`main()`* but their line positions necessarily shift as ranges above and around them are replaced.

**R-G6a — position-pinned (exhaustive):**

| What | Lines | Why |
|---|---|---|
| The SMTP send block | 959-965 | D-i12-4. `run_state.emails_sent += 1` / `site_emailed = True` sit **between** `send_message()` and `quit()`; hoisting the block moves them after `quit()` returns, reopening the Ctrl-C-during-`quit()` duplicate-email window. |
| `run_state.record_site_notices(...)` | 956-957 | Invariant 4: notices are recorded **before** the send. |
| The smell **emission** | 880-884 | `CAMPAIGN.md` §3.3 / LEDGER I10 amendment 1: it summarizes end-of-phase smell state no hook position can guarantee, and must stay behind the `--only-warn` gate. |
| The `--only-warn` gate | 869-872 | §3.3 stay-list (B42). |
| `try:` / `except BaseException` / `finish_run` | 532, 969-984, 986-991 | §3.3 stay-list (B59-B60 call sites); Invariant 4's single flush path. |
| `sc.SiteContext(site)` | 579 | §5.5 R5.6 — its *position* is a documented invariant of the loop. |
| The pre-loop bindings `site_name = None` / `site_emailed = False` | 530-531 | §4.2 / R-G4 — the handler's guarantee that both names are bound before `try:`. |
| The per-iteration reset `site_emailed = False` | 534 | §4.1 / R-G4 — the trap. |

**R-G6b — stays in `main()`, but its line position changes (exhaustive):**

| What | Lines today | What happens |
|---|---|---|
| The loop header `for site_name in site_names:` | 533 | Unchanged text; shifts upward as ranges above it are replaced. |
| The portal / not-in-list skip `continue`s | 546, 554 | Unchanged text and position **relative to their guards**; absolute line numbers shift. |
| The plan/Sandbox skip | 568, 574 | **Replaced** by §5.5's single `if plan_name is None: continue`. The `continue` stays in `main()` (R-G3); the two guards it replaces do not. |
| The `envs` / traffic / `--import-older-metrics` / `--update` `continue`s | 603, 615, 619, 623 | Unchanged text; absolute line numbers shift. |
| The `domain:list` skip | 646 | **Replaced** by §5.3's `if fetched is None: continue`. Same note as the plan/Sandbox row. |
| The `--only-warn` and `resolve_recipients` `continue`s | 872, 891 | Unchanged text; absolute line numbers shift. |

The point of R-G6b is R-G3, not the line numbers: **every `continue` is executed by `main()`**,
before and after. A helper never executes one.

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

**R-G12 — `main()`'s complexity `noqa` stays, and here is the measured reason.** `main()`'s
`# noqa: C901, PLR0912, PLR0915` on the `def main()` line (370) stays.

> **Correction (this replaces a false claim in the first draft of this spec).** The first draft
> justified this with *"ruff's `RUF100` (unused-noqa) is not selected in a way that would flag
> it."* **That is false and was recalled rather than measured** — exactly the failure §10 exists to
> catch, committed inside §10's own document. `pyproject.toml` `[tool.ruff.lint]` is
> `select = ["ALL"]` and the `ignore` list contains **no** `RUF` entry at all, so `RUF100` **is**
> selected. Demonstrated red on a probe file (PD#14 — an instrument shown capable of going red):
>
> ```
> $ uvx ruff@0.15.22 check --force-exclude _ruf100_probe.py
> RUF100 [*] Unused `noqa` directive (unused: `C901`, `PLR0912`, `PLR0915`)
>  --> _ruf100_probe.py:1:19
> Found 1 error.
> ```

**The measured reason the suppression stays required.** With no `max-statements` /
`max-branches` / `max-complexity` overrides in `pyproject.toml`, ruff's defaults apply:
`PLR0915` = 50 statements, `PLR0912` = 12 branches, `C901` = 10 complexity. Measured by AST over
`psh/cli.py` at `c01e77b`:

| | statements | branch/loop/try/with nodes |
|---|---|---|
| `main()` today | **255** | **58** |
| `main()` with all six ranges deleted (a *lower* bound — the §5 replacement blocks add back) | **143** | **25** |

143 ≫ 50 and 25 ≫ 12, so **all three suppressions remain load-bearing after the extraction and
`RUF100` cannot fire.** The implementer MUST NOT remove the `noqa`. If ruff nonetheless flags it,
that measurement was wrong and it is a finding to **report**, not to silently act on.

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

**R3.9 — one commit, THREE functions.** The two ranges MUST land in **one commit**, because the
first deletes the three aliases (`main_fqdn`/`custom_domains`/`primary_domain`, 664-666) that the
second consumes. `fetch_site_domains` and `resolve_site_url` MUST remain **two separate
functions**, because the stage spine at 688-692 sits between them and stays in `main()`. The
**third** is the pure notice builder `no_domains_notice` required by R3.6d.

**Destination rationale.** `psh/cli.py`, **not** `psh/dns_classify.py`. That module's docstring
bars it (**verified at `psh/dns_classify.py:1-9`**): *"Pure data producer for the site_post_dns
contract … Presentation (notices) lives in check/dns/, not here."* `fetch_site_domains` both makes
a `terminus` call and emits a `Notice`, and `no_domains_notice` (R3.6d) is presentation outright.
`NOTICE_NO_DOMAINS` is registered at **`psh/cli.py:141`** (**verified**) and
`no_primary_domain_notice` — the exact shape `no_domains_notice` copies — already lives at
`psh/cli.py:295-334` (**verified**). All three land in `psh/cli.py`.

**Signatures and return types.**

```python
def no_domains_notice(site, domains, custom_domains) -> Notice | None:
    """The `no-domains` alert, or None when it does not apply (B29's notice half).

    PURE -- no I/O, no sc.console, no SiteContext.  Deliberately mirrors
    no_primary_domain_notice (psh/cli.py:295): same file, same shape, same
    `-> Notice | None` contract, so both notice builders in this module are
    unit-testable at the same seam.  Carries the golden-pinned column-16
    literal (R3.6) and the load-bearing isinstance guard (R3.6b).
    """


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

**R3.3** The `site_url = ""` **pre-binding** at line 650 is deleted; `resolve_site_url` initializes
it internally and `main()` rebinds `site_url` from the return value. **`site_url` itself is NOT
eliminated** — it is read at 763, 875 and 922, well past both helpers. What is eliminated from
`main()`, exhaustively: the three aliases (`main_fqdn`, `custom_domains`, `primary_domain`,
664-666) and the two Cloudflare-gate locals (`cf_on`, `cf_ctx`, 653-654) — **five locals**, plus
one dead pre-binding.

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

**The rule is ABSOLUTE, and the frame is irrelevant.** Every interior line — and both closing
`"""` — sits at **column 16, counted from the start of the line**, whatever enclosing function,
`if`, or indent level the `Notice(...)` call ends up in. State it that way and it cannot be got
wrong; state it as a *relationship* to the keyword column and it changes with every reframing.
For the record, the three frames involved differ:

| Where | `Notice(` at | keyword (`html=`) at | interior lines at |
|---|---|---|---|
| `main()` today (674-684) | 24 | 28 | **16** (12 *less* than the keyword) |
| `no_primary_domain_notice` precedent (313-332) | 8 | 12 | 20 (8 *more* than the keyword) |
| `no_domains_notice` after R3.6d | 8 | 12 | **16** (4 *more* than the keyword) |

All three are correct for their literal. Only the third row is a constraint on this increment:
**16, absolutely.**

**R3.6a** The implementer MUST add a sentinel comment at the new `def` naming Invariant 8 and the
three goldens, so the next formatter run cannot silently re-indent the block and re-email every
site owner a differently-indented alert.

**R3.6b** The two `if`s at 667-668 stay **nested**, with the `# noqa: SIM102` and its full reason
comment verbatim — now inside `no_domains_notice` (R3.6d). The outer `isinstance(domains, dict)`
guard is **load-bearing, not defensive**: `facts.custom_domains` is `[]` for *any* non-dict
payload, so removing the guard emits a false "paid plan with no custom domains" **alert** to the
owner. That branch has **no test at any tier** and MUST get one here (a non-dict `domains`
payload → `no_domains_notice` returns `None`).

**R3.6d — the notice half is extracted as a PURE builder, and this is a deviation from the plan.**
The plan put the `Notice(...)` construction inline in `fetch_site_domains`. **That makes the
Invariant-8 assertion R3.6c requires impossible to write**, for two independent reasons, both
**verified**:

1. **Nothing at that seam returns a `Notice`.** `fetch_site_domains` calls
   `site_context.add_notice(Notice(...))`, and `SiteContext.add_notice`
   (`script_context.py:118-133`) immediately projects through `notice_to_dict`, storing the
   six-key render dict `{type, icon, csv, short, message, text}`. `notice.html` becomes
   `site_context["notices"][0]["message"]`. There is no `notice` object to bind, so the assertion
   as first drafted references a name that cannot exist.
2. **The tier is wrong.** `fetch_site_domains` makes a `terminus("domain:list")` call, so it can
   never be unit-pure; the first draft nonetheless assigned the column assertion to the `unit`
   tier. The `no_primary_domain_notice` precedent has a unit test precisely *because* it is a pure
   builder.

**Therefore:** extract `no_domains_notice(site, domains, custom_domains) -> Notice | None` as a
module-level pure builder in `psh/cli.py`, immediately beside `no_primary_domain_notice`. The
column-pinned literal, the nested `if`s, and the `# noqa: SIM102` all live in it.
`fetch_site_domains` reduces to:

```python
            notice = no_domains_notice(site, domains, facts.custom_domains)
            if notice is not None:
                site_context.add_notice(notice)
```

which is the **identical** call shape `main()` already uses for `no_primary_domain_notice` at
`psh/cli.py:701-705`. This is sanctioned scope, not creep:
`prompts/implementation-standards.md` § Test discipline — *"If a core `main()` change has no honest
seam, extracting a pure module-level helper is **part of the change**"* — and it matches the I1
preserved-bug-extraction pattern (`LEDGER.md:125-127`). Recorded as a deviation in §10 item 6.

**R3.6c — evidence beyond the goldens (PD#14).** Against the `no_domains_notice` seam, where a real
`Notice` **is** returned, the new unit test MUST assert

```python
notice = no_domains_notice(SITE, DOMAINS, [])
assert notice is not None
assert all(
    line.startswith(" " * 16)
    for line in notice.html.splitlines()[1:]
    if line.strip()
)
```

and the same for `notice.text`. The task MUST additionally compare the pre/post
`ast.get_source_segment` of the `Notice(...)` call. **`git diff -w` is not acceptable evidence** —
`CLAUDE.md` § Conventions & gotchas: a line that only gained leading whitespace is exactly what
`-w` is designed to ignore.

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
`site_name_to_id`.

**Its console effect is broader than one failure path**, and the spec says so precisely because
this sentence will be restated in six task reports. `run_terminus` emits its own output before the
call returns — `psh/gateway.py:46` is `sc.debug("Running Terminus command:\n", commandline)` and
`:48` opens `sc.console.status(f"[bold green]Running: …")` (**verified**). So the hoist moves the
two banners ahead of the `org:site:list` command's own debug line **and its spinner** on **every**
`-v` run, not only when the call fails. Two consequences, both benign:

- **Every `-v` run:** the Cloudflare/SMTP banners now precede the `org:site:list` debug line and
  spinner instead of following them.
- **The failure path:** if `org:site:list` raises `TerminusError`, the banners now print before the
  `Could not list organization sites` exit instead of not at all.

Everything moved is `sc.debug`, so all of it is invisible without `-v`, and none of it is
golden-covered. `CAMPAIGN.md` §8 sanctions the class explicitly: *"stdout / console / error
messages | MAY improve freely"*.

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

**R5.5.8 — CAMPAIGN.md amendment: THREE block IDs, not two.** §3.3's stay-list reads *"the
site-loop skeleton (skips, banner, sorted order, resume filter — **B14–B18**, B20, B25, B42)"*.
`B14–B18` is a **five-ID range**, and `BLOCKMAP.md` confirms B15/B16/B17/B18 all exist
(*"| B17 | 2323–2349 | Elite plan SKU → name via `terminus("plan:info")`, `plan_sku_to_name` |"*).
Extraction 5 moves **B17 (residue)**, **the Sandbox half of B18**, and **B20** — all three on the
stay-list, all three needing an amendment.

> **This corrects the first draft of this spec, which named only B18 and B20.** The omission was
> not a judgment that B17's residue is exempt — it was an oversight, and it is the one that would
> have left `CAMPAIGN.md` **wrong by definition** after Task 5 landed: §3.3 would still assert that
> B17 stays in `main()` when nothing of B17 remained there. The decision rule this spec already
> applies elsewhere is dispositive: B14 and B20 are neither "skips, banner, sorted order, nor
> resume filter" either, and both were given amendments on **ID-list membership alone**. B17 gets
> the same treatment.

**B17's history, which the amendment must record.** `CAMPAIGN.md` §3.1 assigns *"SKU resolution
(B17)"* to `psh/plans.py`, while §3.3 lists B17 among the IDs staying in `main()` — a **pre-existing
internal tension in `CAMPAIGN.md`**, not something this increment creates. I7 resolved it in
practice without amending §3.3: `LEDGER.md:684-685` records *"`resolve_plan_name` (B17 body incl.
the Elite check as its early return; `main()` keeps `continue` + tail inits)"*. So the **body** left
at I7 and the **call site plus the `site["plan_name"]` write-back** stayed. This increment moves
that residue, after which **no B17 content remains in `main()` at all** and the §3.1/§3.3 tension is
closed rather than carried. See §7 R7.3a.

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
judgment. **Every *mock* seam named here already exists in this codebase**; this increment creates
no new monkeypatch seam. (It does create one new *pure-function* seam, `no_domains_notice` — R3.6d
— which is a test target, not a mock point.)

| Task | Seam under test | Tier | How to reach it |
|---|---|---|---|
| **1** | `psh.traffic.build_traffic_window` — called directly | `unit` | Pure data in: a `list[TrafficRow]`, two `datetime.date`s, two `str`s. **No I/O, no monkeypatching.** `sc.options`/`sc.console` come from the autouse `reset_sc` fixture. Add `tests/unit/test_traffic_window.py`. Hypothesis is available (see `tests/unit/test_traffic_aggregation.py` for the house idiom). |
| **2** | `psh.gather.gather_framework` — called with an `sc.SiteContext` | `integration` | Patch **BOTH** `psh.gateway.run_terminus` (the `gateway` conftest fixture) **AND** `psh.gather.run_terminus` — `psh/gather.py` binds `run_terminus` in its own namespace for `gather_drupal`'s composer dry-run, and a test that patches only the former makes **real** Terminus subprocess calls. See `tests/integration/test_gather_drupal.py`'s docstring. Add `tests/integration/test_gather_framework.py`. |
| **3a** | `psh.cli.no_domains_notice` — called directly (R3.6d) | `unit` | **Pure.** `no_domains_notice(site_dict, domains_payload, custom_domains_list)` → `Notice \| None`. No I/O, no monkeypatching, no `SiteContext`. This is where the Invariant-8 column assertion (R3.6c) and the non-dict-`domains` guard test (R3.6b) live, because it is the only seam that returns a real `Notice`. Add `tests/unit/test_no_domains_notice.py`, modelled on the `no_primary_domain_notice` unit test. |
| **3b** | `psh.cli.fetch_site_domains` and `psh.cli.resolve_site_url` — called with an `sc.SiteContext` | `integration` | Three existing seams: `psh.gateway.run_terminus` (the `gateway` fixture) for `domain:list` and the WP-network `wp_eval`; **`psh.dns_classify.resolve`** for every A/AAAA lookup (`tests/helpers/dnsfake.py`'s `make_resolver`/`patch_resolve`); and **`psh.cli.cloudflare_enabled`** for the Cloudflare gate — see S5, this is NOT `sc.cloudflare_enabled`. Add `tests/integration/test_site_domains.py`. |
| **4** | `psh.cli.resolve_site_roster` — called directly | `integration` | `psh.gateway.run_terminus` (the `gateway` fixture) reaches `terminus_data("org:site:list", …)` through `psh.gateway`'s own `terminus`. `sc.options.resume_from` is set via `reset_sc.options = psh.parse_args([...])`. Use `recording_console(monkeypatch, sc, width=80)` for the resume banner — production's non-tty width, per `CLAUDE.md`'s rich gotcha. Add `tests/integration/test_site_roster.py`. |
| **5** | `psh.plans.resolve_site_plan` — called directly | `integration` | `psh.gateway.run_terminus` (the `gateway` fixture) for the Elite-SKU `plan:info` call inside `resolve_plan_name`; a non-Elite `site` makes **no** subprocess call at all. `sc.config["Pantheon"]["plan_sku_to_name"]` from `reset_sc`. Add `tests/integration/test_resolve_site_plan.py`. |
| **6** | `psh.cli.validate_options` — called directly | `unit` | `sc.options = psh.parse_args([...])` plus a minimal `sc.config` dict, then `pytest.raises(SystemExit)` on the message. This is the exact idiom of `tests/unit/test_argparse_contract.py`. **No subprocess, no `run_program`.** Add to `tests/unit/test_argparse_contract.py` or a sibling `tests/unit/test_validate_options.py`. |

**Seam rules that bind every row (exhaustive):**

- **S1.** The two-binding trap is real and silent: `from X import f` binds the *importer's* name.
  Row 2's double patch is not optional.
- **S5 — `cloudflare_enabled` MUST be patched at `psh.cli.cloudflare_enabled`, NEVER at
  `sc.cloudflare_enabled`.** This is S1 applied to row 3b, and the first draft of this spec got it
  wrong. `psh/cli.py:38-45` does `from psh.configuration import (cloudflare_enabled, …)`, so the
  bare call at line 653 resolves in **`psh.cli`'s own namespace**; `monkeypatch.setattr(sc,
  "cloudflare_enabled", …)` never reaches it. **Both failure modes are bad and neither is loud:**
  patching `sc` and expecting *disabled* yields a silent green (the real `cloudflare_enabled()`
  also returns falsy under a test config with no `[Cloudflare]` section, so the test passes while
  testing nothing); patching `sc` and expecting *enabled* yields a confusing `KeyError` on
  `sc.plugin_context["plugin.cloudflare"]` rather than a message naming the seam.
  **Precedent for the correct form:** `tests/integration/test_plugin_cloudflare.py:136`. The
  existing `monkeypatch.setattr(reset_sc, "cloudflare_enabled", …)` calls
  (`tests/integration/test_check_dns.py:41,53,67,83`; `test_check_pantheon_cdn_change.py:28`) are
  **not** counter-examples — they are `check/` tests whose consumer genuinely calls
  `sc.cloudflare_enabled()`, which is the façade route. Copying them here is the trap.
  An equally acceptable alternative, if the implementer prefers no monkeypatch at all: drive the
  gate through data by setting `sc.config["Cloudflare"]["enabled"]` and populating
  `sc.plugin_context["plugin.cloudflare"]` with the four keys line 653-661 reads.
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

**R7.3a — `CAMPAIGN.md` §3.3, B17.** Amend so **B17 leaves the stay-list entirely**: the SKU
resolution *call site* and the `site["plan_name"]` write-back move into
`psh.plans.resolve_site_plan`, and the loop skeleton around them stays. §3.3's `B14–B18` range must
be rewritten so it no longer asserts that B17 stays — after Task 5, **no B17 content remains in
`main()`**, and leaving the range as written would make §3.3 false by definition.

The amendment MUST also record that this **closes a pre-existing §3.1/§3.3 tension rather than
creating one**: §3.1 has always assigned *"SKU resolution (B17)"* to `psh/plans.py` while §3.3
listed B17 among the IDs staying in `main()`. I7 moved the body and left the call site without
amending §3.3 (`LEDGER.md:684-685`: *"`resolve_plan_name` (B17 body incl. the Elite check as its
early return; `main()` keeps `continue` + tail inits)"*). This increment moves the residue, so the
two sections agree for the first time. See §5.5 R5.5.8.

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
removed it. Task 7 MUST NOT re-add or re-strike it; the discharge is recorded in `CLOSING-AUDIT.md`
(R7.6) and `LEDGER.md` (R7.5) instead.

**The verification MUST grep the TODO's own text, not its decision ID (PD#14).**

```
$ grep -n 'Extract further from' README.md      # expect: no match  (the TODO is gone)
$ git show 5b92ee1^:README.md | grep -c 'Extract further from'   # expect: 1  (it was there)
```

> The first draft of this spec prescribed `grep -n 'D-i14d-1' README.md` as the proof. **That
> instrument cannot go red**: the string `D-i14d-1` never appeared in `README.md` at all —
> `git show 5b92ee1^:README.md | grep -n 'D-i14d-1'` returns **no match** on the pre-strike file
> too. The ID lives only in `CLOSING-AUDIT.md`, `RETROSPECTIVE.md`, `LEDGER.md` and the I14d SPEC.
> A check that returns the same answer before and after the event it is checking for is not a
> check. The two-command form above is red-capable in both directions.

**R7.7 — `README.md`: give the orphaned pathlib deferral a home.** Add a TODO recording that four
`noqa` comments in `main()` (`psh/cli.py:373, 437, 438, 470`) defer a pathlib migration to
"I14b+", that I14b's ledger entry never touched PTH, and that neither `README.md` nor `CLAUDE.md`
mentions it. PD#9: *"Everything deferred is written down. Vague intentions are lies."*

**R7.8 — `CLAUDE.md`.** Three additions:
1. The new helper roster per module — `psh/traffic.py` gains `build_traffic_window`/`TrafficWindow`;
   `psh/gather.py` gains `gather_framework`/`FrameworkGather`; `psh/plans.py` gains
   `resolve_site_plan`; `psh/cli.py` gains `validate_options`, `resolve_site_roster`/`SiteRoster`,
   `fetch_site_domains`/`SiteDomains`, `resolve_site_url`/`SiteUrlFacts`, and the pure builder
   `no_domains_notice` (recorded **beside** `no_primary_domain_notice`, since `CLAUDE.md` already
   names that one and the pair is now the module's notice-builder convention).
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

   **What "the right reason" is for these six tasks, stated once so six fresh implementers do not
   each decide it alone.** These are **behavior-preserving extractions**: the behavior under test
   already works inside `main()`, so there is no wrong-answer red available. The **only** legitimate
   first red is the helper not existing yet:

   ```
   AttributeError: module 'psh.traffic' has no attribute 'build_traffic_window'
   ```
   (or `ImportError` / `NameError` for the same cause, depending on the import form).

   That is sufficient and is what the implementer MUST paste. What it does **not** license: writing
   the test *after* the helper and asserting it was red "in principle". Two reds are therefore
   required in sequence for each task — first the `AttributeError` above, then, once the helper
   exists as a stub, a **substantive** failure (a wrong return value, a missing field) before the
   body is filled in. A task whose report shows only the `AttributeError` has not demonstrated that
   its assertions can go red on anything but a typo in the module name.
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

Both are required, and **`git diff -w` is not acceptable for either**. The assertion is written
against the **`psh.cli.no_domains_notice`** seam (§6 row 3a), which is the only seam that returns a
real `Notice` — see R3.6d for why the first draft's version of this block could not be written at
all:

```python
# tests/unit/test_no_domains_notice.py
notice = psh.no_domains_notice(SITE, DOMAINS_PAYLOAD, [])
assert notice is not None
for body in (notice.html, notice.text):
    assert all(
        line.startswith(" " * 16)
        for line in body.splitlines()[1:]
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

### 9.0 The suite is green NOW — the baseline every task compares against

The whole increment's gate (§8) presumes the four goldens are green before Task 1 starts. That is a
claim, so it is measured and pasted here, per the Spine's *"Acceptance criteria = exact commands +
expected output, **run and pasted**, never summarized."* **Run at commit `c01e77b`, immediately
before this spec was committed:**

```
$ ./run-tests
...
--------------------------- snapshot report summary ----------------------------
107 snapshots passed.
================ 1743 passed, 3 skipped, 15 warnings in 40.89s =================
Linting (ruff, campaign ratchet) ...
Type-checking (pyright, campaign ratchet) ...
$ echo $?
0
```

Exit 0, so **both gates passed** — `run-tests` calls `run_gates()` and returns its non-zero code
before pytest is ever invoked (`./run-tests:143-149`), so a red ruff or pyright could not have
produced this. (The two gate banners appear *after* the pytest summary only because the run was
piped through `tail` with `2>&1`, interleaving two streams; the gates genuinely run first.)

**Task 1's implementer: if your first `./run-tests` does not start from `1743 passed, 3 skipped`
and `107 snapshots passed`, something is red that this increment did not cause.** Say so rather
than absorbing it.

### 9.1 `main()`'s size

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

1. **`README.md:260-267` no longer holds the D-i14d-1 TODO.** It was struck in commit `5b92ee1`
   earlier the same day; lines 260-267 now hold the `uvx pyright@1.1.411` TODO. **Precision the
   first draft of this spec got wrong:** the *string* `D-i14d-1` was never in `README.md` at all —
   what was there is the TODO's prose, *"Extract further from `main()` toward CAMPAIGN.md §3.3's
   250–400-line target"*. The decision ID lives only in `CLOSING-AUDIT.md`, `RETROSPECTIVE.md`,
   `LEDGER.md` and the I14d SPEC. Consequence: §7 R7.6a, whose verification greps the prose (which
   can go red) rather than the ID (which cannot).
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
5. **The plan's stay-list membership is right for five of six extractions and INCOMPLETE for
   extraction 5.** The plan named B18 and B20; §3.3's `B14–B18` is a five-ID range and
   **B17** — which the plan itself puts in extraction 5's range as "B17 (residue)" — is inside it.
   Consequence: §5.5 R5.5.8 and the new §7 R7.3a. This is the one correction that would have left
   `CAMPAIGN.md` **false by definition** after Task 5.
6. **DEVIATION from the plan, deliberate and sanctioned: extraction 3 gains a third function.**
   The plan constructs the `no-domains` `Notice` inline inside `fetch_site_domains`. That makes the
   plan's *own* Invariant-8 assertion unwritable — `SiteContext.add_notice` projects the `Notice`
   away immediately, and `fetch_site_domains` makes a `terminus` call so it cannot carry a unit
   test. §5.3 R3.6d therefore extracts the pure builder `no_domains_notice(site, domains,
   custom_domains) -> Notice | None` beside `no_primary_domain_notice`. Sanctioned by
   `prompts/implementation-standards.md` § Test discipline (*"extracting a pure module-level helper
   is **part of the change**"*) and matching the I1 pattern at `LEDGER.md:125-127`. Recorded here
   rather than applied silently, per `prompts/implementation-standards.md` § Deviation discipline.
7. **Everything else in the plan verified true**, specifically: the six line ranges all still match
   `psh/cli.py` exactly; the `NOTICE_NO_DOMAINS` literal is in exactly 3 of the 4 goldens;
   `psh/traffic.py` already imports from `psh.plans` (line 27), so extraction 1 adds no cycle;
   `NOTICE_NO_DOMAINS` is registered at `psh/cli.py:141`; `no_primary_domain_notice`'s literal sits
   at column 20 inside a frame at 8/12 while the `no-domains` literal sits at 16 inside a frame at
   24/28, materially as the plan describes; `main()` has no in-process caller in the suite;
   `psh/lifecycle.py`'s docstring pins its module-level imports to stdlib + `sqlalchemy.exc` +
   `rich`; `psh/dns_classify.py`'s docstring bars presentation; `psh/gather.py:11-13` is the
   smell-merge authority; `main()` is 622 raw / 445 logic.

### 10a. Corrections to the FIRST DRAFT of this spec (review round 1)

Recorded separately from the plan's errors, because a spec that claims *"every number was
measured"* and then ships four recalled ones has committed the defect it exists to prevent. All
were found by adversarial review of the committed baseline and are fixed above.

| # | First draft said | Truth | Fixed in |
|---|---|---|---|
| a | B18 + B20 need amendments | **B17** too — `B14–B18` is a five-ID range | §5.5 R5.5.8, §7 R7.3a |
| b | Patch `sc.cloudflare_enabled` | `psh/cli.py` imports the name, so patch **`psh.cli.cloudflare_enabled`** — this spec's own S1 trap | §6 row 3b, S5 |
| c | Assert on `notice.html` at the `fetch_site_domains` seam, `unit` tier | Nothing there returns a `Notice`, and it makes a `terminus` call | §5.3 R3.6d, §6 row 3a, §8.3 |
| d | `RUF100` "is not selected in a way that would flag it" | `select = ["ALL"]`, no `RUF` ignore; **demonstrated red on a probe**. The real reason is 143 statements vs a max of 50 | R-G12 |
| e | Hoisting 501-509 affects "one failure path" | Also reorders against `run_terminus`'s own debug line and spinner on **every** `-v` run | §5.4 R5.4.1 |
| f | Verify with `grep 'D-i14d-1' README.md` | That returns nothing **before** the strike too — an instrument that cannot go red | §7 R7.6a |
| g | R-G6 "stay in their current position" incl. lines §5.3/§5.5 replace | Split into position-pinned (R-G6a) vs. stays-but-moves (R-G6b) | R-G6 |
| h | No baseline `./run-tests` output | Pasted: `1743 passed, 3 skipped`, 107 snapshots, exit 0 | §9.0 |
| i | Spine ranges given three ways (627-628/632-633/691-692/763-766 vs 761-766 vs 688-692) | One convention: call + the comment above it | R-G2 |
| j | "five locals eliminated" incl. `site_url` | `site_url` survives; only its `= ""` pre-binding goes | §5.3 R3.3 |
| k | "the right reason" left to the implementer | Stated once: `AttributeError`, then a substantive red | §8.1 item 1 |
| l | Skip gates "reached only through a full site loop" | Reached by every single-site e2e run; **never asserted on** | §1.2 |

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

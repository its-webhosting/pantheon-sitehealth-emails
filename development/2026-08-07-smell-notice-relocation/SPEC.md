# SPEC — Relocate the smell-notice emission to a `check/smells/` `site_pre_render` hook

**Status:** approved design, 2026-08-07. Brainstormed under `superpowers:brainstorming` with
`prompts/new-feature-standards.md` as the standards overlay; PD#n citations refer to
`/workspace/prompts/directives.md` (the Spine).

**Discharges:** README's first post-campaign TO DO item ("Add a `mutates` hook declaration to the
DAG"), created by LEDGER I10 amendment 1 as a user decision. This spec **does not implement that
item as worded** — §2 shows the item's premise is false — and §11 records the disposition that
replaces it.

**Not `I<N>`-numbered.** The modularization campaign is closed
(`development/2026-07-17-modularization-campaign/CAMPAIGN.md` carries `**Completed:** 2026-07-24 at
I14d`). This increment neither reopens it nor adds an increment to it. It is nevertheless recorded
in that campaign's `LEDGER.md` because it amends `CAMPAIGN.md` §3.2 and §3.3, which that document's
preamble *requires* (edit the document **and** append a ledger entry) — the same protocol the
2026-08-07 `main()`-extraction increment followed.

---

## 1. Glossary

Terms of art used in this document. Domain terms live in `/workspace/CONTEXT.md`; campaign terms
(increment, block ID `B<n>`, decision ID `D-i<n>-<m>`) live in CAMPAIGN.md §Glossary. This section
adds only what is specific to this change.

- **Smell** — non-fatal text a `wp`, `drush`, or `composer` invocation wrote to **stderr** while
  still succeeding. Carried per site in the three contract keys `wp_smell` / `drush_smell` /
  `composer_smell` (str, `""` when none), reported to the site owner as "PHP code problems". This
  term is internal vocabulary only; it never appears in a report. **New CONTEXT.md entry** —
  see §9.4.
- **Smell notice** — one of the three `Notice`s built from a non-empty smell: codes `wp-smell`,
  `drush-smell`, `composer-smell`, all `Severity.INFO`. Collectively **BLOCKMAP B48**.
- **The emission** — the call site that adds the smell notices to a site's
  `site_context["notices"]`. Today `psh/cli.py:975-979`, inline in `main()`. Relocating **the
  emission** is this change; the **builder** (`build_smell_notices`) already moved out of `main()`
  at campaign I10.
- **In-place mutator** — a `site_post_gather` hook that rebinds an already-stuffed contract key
  rather than producing a new one. Exhaustively (this is the complete in-repo set, from CLAUDE.md's
  contract table): `check.wordpress.ocp` and `check.wordpress.favicon` rebind `wp_smell`;
  `check.umich.drupal_ua` rebinds `drush_smell`. They deliberately do **not** declare
  `produces: ['wp_smell']` — that is a DAG condition-2 fatal against the core `CONTRACT` registry
  (D-i9-3).
- **Phase index** — the 0-based position of a phase in `psh.modules.PHASES`. `site_post_gather` is
  4, `site_pre_render` is 5. DAG condition 4 compares these.

## 2. Normative language

- **MUST** — required; a violation is a defect that blocks the increment.
- **MUST NOT / NEVER** — prohibited; same weight.
- **SHOULD** — required unless a reviewer accepts a written reason in the task report.
- **MAY** — genuinely optional; the implementer chooses.

## 3. The finding that reshaped the TO DO

### 3.1 What the TO DO claimed

The README item asserts that a `mutates` edge kind is "what would let B48's smell notices become a
`check/addon_updates/` hook". CAMPAIGN.md §3.2 gives the three reasons, all of them scoped — though
the text does not say so — to a **`site_post_gather`** hook:

| # | Campaign's stated obstacle | Verified against | True? |
|---|---|---|---|
| 1 | A smells hook cannot be ordered after the in-place mutators | `psh/modules.py::ordered_hooks` — intra-phase order comes from `produces`/`consumes` edges, then registration order | Yes, **within one phase** |
| 2 | `produces: ['wp_smell']` is a condition-2 fatal against the core registry | `psh/modules.py::_claim_hook_producers`; `wp_smell` ∈ `CONTRACT["site_post_gather"]` | Yes |
| 3 | Relocation adds smell rows to `--only-warn` csv output (a §8 surface change) | `psh/cli.py:964-967` — `--only-warn` `continue`s before the emission at `:975` | Yes, **for a phase at or before `site_post_gather`** |

### 3.2 What a later phase changes

Every obstacle is a consequence of choosing `site_post_gather`. At **`site_pre_render`** all three
dissolve, with no engine change:

```
  psh/cli.py                                  site_context["wp_smell"] etc.
  ──────────────────────────────────────────  ─────────────────────────────
  :882  stuff_gather_contract(...)            ← core writes the 3 smell keys
  :883  invoke_hooks("site_post_gather") ─┐
             check.wordpress.ocp          │   ← MAY rebind wp_smell    (in-place
             check.wordpress.favicon      │   ← MAY rebind wp_smell     mutators;
             check.umich.drupal_ua        │   ← MAY rebind drush_smell  DAG-invisible)
        ... every other site_post_gather ─┘
  :941  recommend_plan(...)                   → appends its notice
  :964  if only_warn: record csv; CONTINUE ═══════════ --only-warn runs END here
  :975  build_smell_notices(...)  ◄────────── TODAY: the emission, inline
  :981  sc.debug("===== Notices:", ...)       READS the list (see below)
  :984  resolve_recipients(...)               (appends no notice)
  :989  stuff_plans_contract(...)             (appends no notice)
  :1003 invoke_hooks("site_pre_render")  ◄─── PROPOSED: the emission, as a hook
  :1008 sort_notices_and_subject(...)         reads site_context["notices"]
  :1052 record_site_notices(...)              writes -notices.csv, in list order
```

| Obstacle | Why it does not apply at `site_pre_render` | Verification |
|---|---|---|
| 1 — ordering vs. the mutators | The mutators are all `site_post_gather` (phase index 4); a phase-5 hook is unconditionally after every phase-4 hook. No intra-phase edge, and therefore no `mutates` edge, is involved. | `psh.modules.PHASES` order; `main()` fires phases in that order |
| 2 — duplicate producer | The hook produces nothing. It **consumes** `wp_smell` / `drush_smell` / `composer_smell`, which the core registry already owns at phase 4. Condition 4 raises only when `owner_phase[key][0] > index`, i.e. `4 > 5` — false. | `psh/modules.py::_check_hook_consumers`, `_registry_owners` |
| 3 — `--only-warn` csv | `main()` `continue`s at `:964`, which is *above* `:1003`. `site_pre_render` is documented full-report-only (`psh/modules.py::PHASES` comment, CLAUDE.md). Gating is therefore **identical to today's**, not merely similar. | `psh/cli.py:964-967`, `:1003` |

**Amended 2026-08-07, during implementation.** The obstacle-1 row above asks what *appends* to
`site_context["notices"]` between the old call site and the phase, and the answer is "nothing".
That question was too narrow: `sc.debug("===== Notices:\n", site_context["notices"])` at `:981`
**reads and prints** the list, so relocating the emission below it silently emptied the smell
notices out of every `-v` run's dump — an observability regression (PD#5) invisible to every test,
since no tier asserts on the dump. The fix, applied in this increment on the user's ruling and
superseding PLAN.md Task 1 step 14's "leave the `sc.debug` lines in place": both `sc.debug` lines
move **below** the `site_pre_render` firing. The dump is then strictly more accurate than before
the relocation — it reports every notice the report will contain, including any future
`site_pre_render` hook's. **The general lesson, worth more than the fix:** when relocating a
producer past a seam, enumerate the *readers* on both sides of it, not only the other producers.

### 3.3 Consequence for the TO DO

The relocation the TO DO wants is reachable today at zero engine cost. A general `mutates` edge
kind — one that orders a *same-phase* consumer after the in-place mutators — would then have **no
consumer in this repo**, which is precisely the "engine surface no move needs" the campaign
declined it as. Adding it anyway is a speculative abstraction (Spine § Engineering Preferences,
"engineered enough"; `andrej-karpathy-skills:karpathy-guidelines` §2).

`mutates` is therefore **NOT in scope** (§4.2), and the README item is deleted with this reasoning
recorded in LEDGER (§9.3) rather than silently dropped (PD#9).

## 4. Scope

### 4.1 In scope (exhaustive)

1. New `check/smells/` package: gate, hook, builder, three notice-code registrations.
2. Removal of the emission from `main()` and of the builder + its three codes from `psh/gather.py`.
3. `[Check.smells]` in `sample-pantheon-sitehealth-emails.toml`.
4. Test moves, new tests, and the `ALL_PACKAGES` / `ROSTER` updates they force.
5. Documentation: this spec, the CAMPAIGN.md amendment, the LEDGER entry, CLAUDE.md, CONTEXT.md,
   and the README TO DO deletion.

### 4.2 NOT in scope (exhaustive, with the reasoning preserved so it is not re-litigated)

- **A `mutates` hook declaration, in any form.** §3.3. If a *same-phase* consumer of an in-place
  mutator is ever genuinely needed, this spec is the record of why the edge kind was not built
  pre-emptively, and it can be reconsidered then with a real consumer in hand.
- **Making the three in-place mutators DAG-visible by some other means** (e.g. a documentation-only
  `mutates` key that `add_hook` stores but nothing reads). That is the same speculative surface with
  a weaker justification.
- **Changing what a smell notice says, its severity, its code, or its csv shape.** The builder moves
  **byte-verbatim** (§5.2). Changing any of it would make the syrupy snapshot diff unreviewable and
  break the byte-identity guarantee that is this increment's whole safety argument.
- **Emitting smell notices on `--only-warn` runs.** It is arguably useful — an operator triaging
  warnings might want to see PHP noise — but it is a `-notices.csv` surface change (campaign §8),
  and this increment's value rests on being observably behavior-neutral. Raise it as its own change
  if wanted.
- **De-U-M-ifying anything.** The three smell notices carry no institution-specific content
  (verified: no `umich` string in `psh/gather.py:673-752`), so this increment neither adds to nor
  removes from CLAUDE.md's still-hardcoded-U-M list.
- **Touching the other four post-campaign README TO DO items.**

## 5. Design

### 5.1 Files

| Path | Action | Content |
|---|---|---|
| `check/smells/__init__.py` | **new** | Gate + registration (§5.3) |
| `check/smells/notices.py` | **new** | The three `NOTICE_*` constants + `build_smell_notices` (§5.2) |
| `check/smells/hook.py` | **new** | `emit_smell_notices(site_context)` (§5.4) |
| `psh/gather.py` | edit | Delete `build_smell_notices` (`:673-752`, to EOF), the three `NOTICE_*` constants (`:65-68`), the orphaned `import json` (`:37`), and the `build_smell_notices` paragraph of the module docstring |
| `psh/cli.py` | edit | Delete the emission (`:975-979`) and `build_smell_notices` from the `from psh.gather import (...)` block (`:80`) |
| `sample-pantheon-sitehealth-emails.toml` | edit | Add `[Check.smells]` (§5.5) |

The two-module split (`notices.py` builders + `hook.py` emitter) follows `check/dns/`, the existing
package with exactly this shape, and is what lets the two existing pure-builder test files
(§6.1) move with their assertions unchanged.

### 5.2 `check/smells/notices.py`

`build_smell_notices(site_name, wp_smell, drush_smell, composer_smell) -> list[Notice]` moves from
`psh/gather.py:673-752`. Its **signature MUST NOT change** — the hook (§5.4) supplies `site_name`
from `site_context["site"]["name"]`, exactly as `main()` does today, and the two moving test files
call it directly.

The move is **byte-verbatim in the notice bodies**. Campaign **Invariant 8** applies: the leading
whitespace inside each `html=` / `text=` f-string literal is string content that reaches the
rendered email, and `git diff -w` is designed to ignore exactly the line that only gained some. The
composer literal sits at **column 0** (D-i10-8) and `tests/unit/test_smell_notices.py` asserts that.
The implementer MUST paste the pre-move and post-move literal blocks into the task report and state
that every difference is zero.

Exactly four **sanctioned substitutions** are permitted, and NEVER any other:

| Before (in `psh/gather.py`) | After (in `check/smells/notices.py`) | Why |
|---|---|---|
| `from psh.notice import Notice, Severity, registry` | `import script_context as sc` | `check/` packages import only `sc` (Invariant 9) |
| `registry.register(...)` | `sc.registry.register(...)` | `psh/` registers through the bare `registry`; `check/` through the façade (CLAUDE.md § Notices vs. news) |
| `Notice(` / `Severity.INFO` | `sc.Notice(` / `sc.Severity.INFO` | same convention |
| `import html`, `import json` | same, re-declared in the new module | both are used by the moved body |

The three registrations MUST keep their exact code strings **and** descriptions, so
`tests/integration/test_notice_roster.py`'s frozen 36-code roster stays a 36-code roster:

```python
NOTICE_WP_SMELL = sc.registry.register("wp-smell", description="wp-cli wrote to stderr")
NOTICE_DRUSH_SMELL = sc.registry.register("drush-smell", description="drush wrote to stderr")
NOTICE_COMPOSER_SMELL = sc.registry.register(
    "composer-smell", description=...)   # description copied verbatim from psh/gather.py:67-68
```

### 5.3 `check/smells/__init__.py`

```python
"""..."""
import script_context as sc

if sc.config.get('Check', {}).get('smells', {}).get('enabled', True) is not False:
    from .hook import emit_smell_notices
    sc.add_hook('site_pre_render', {'name': 'check.smells.hook.emit_smell_notices',
                                    'func': emit_smell_notices,
                                    'consumes': ['wp_smell', 'drush_smell', 'composer_smell'],
                                    'produces': []})
else:
    sc.console.print('[bold yellow] Skipping check.smells because it is disabled in the config')
```

The `.get(...).get(...).get('enabled', True) is not False` chain and the disabled-branch message are
copied from `check/addon_updates/__init__.py` — the default-**true** idiom, so an absent `[Check]`,
absent `[Check.smells]`, or absent `enabled` all still register (relocating a check that ran
unconditionally MUST NOT silently disable it).

The module docstring MUST state **why the phase is `site_pre_render`** — that the phase choice is
simultaneously the `--only-warn` gate and the ordering guarantee against the in-place mutators — and
cite this spec. A future maintainer tidying it into `site_post_gather` beside its siblings would
otherwise be making a silent behavior change; the docstring plus the test in §6.2 are the two things
standing between that edit and shipped `--only-warn` csv drift (PD#1).

### 5.4 `check/smells/hook.py`

```python
def emit_smell_notices(site_context):
    site_context.add_notices(
        notices.build_smell_notices(site_context["site"]["name"],
                                    site_context["wp_smell"],
                                    site_context["drush_smell"],
                                    site_context["composer_smell"])
    )
```

It MUST read all three smells off `site_context` and NEVER cache them — `wp_smell` and
`drush_smell` are the two sanctioned mutate-during-phase keys, and reading a stale value is the
exact defect the contract table warns about. This is a straight transcription of `psh/cli.py:975-979`,
which already reads `site_context["wp_smell"]` and not `main()`'s local.

No framework gate: the builder is framework-agnostic, and today's inline emission has no gate either.

### 5.5 Config surface (merged with the file as it stands)

`sample-pantheon-sitehealth-emails.toml` currently ends its check block with `[Check.addon_updates]`
at line 119. The new section goes after it, matching the surrounding one-line-comment style:

```toml
[Check.addon_updates]
enabled = true          # pending add-on (plugin/theme/package) updates table notice


[Check.smells]
enabled = true          # "PHP code problems" notices from wp/drush/composer stderr


[Database]
```

This is a **new operator-visible config key**: setting it to `false` silences three notices that
were previously unconditional. That is the intended, documented consequence of giving the check its
own gate rather than borrowing `[Check.addon_updates]`'s.

## 6. Test plan

Every test below MUST be shown **red-capable** on the condition it guards (PD#14): the task report
MUST paste the failing output produced by a deliberate fault injection, not merely the passing run.
`mattpocock-skills:tdd` governs the loop (`prompts/implementation-standards.md`), so each new test
is written and seen red before its implementation exists.

### 6.1 Moved tests (assertions unchanged)

| File | Change |
|---|---|
| `tests/unit/test_smell_notices.py` | Repoint from the `psh` fixture (`psh.build_smell_notices`) onto the standalone-loaded module via `tests/helpers/checkload.py::load_check_module`. Assertions, test names, and file name unchanged. |
| `tests/integration/test_smell_notice_render.py` | Same repoint. |

The file names and test names MUST NOT change, because syrupy keys snapshots by both:
`tests/integration/__snapshots__/test_smell_notice_render.ambr` MUST come out **byte-identical**.
A diff there is the signal that a literal moved wrong, and MUST NEVER be resolved with
`--update-goldens` (Spine, "an existing golden going red is a signal").

`load_check_module` (not `load_check_package`) is the right helper for these two: it loads one
module **without** running `__init__.py`, so no hook is registered and no config gate is consulted —
these are pure-builder tests and should stay pure.

### 6.2 New: `tests/integration/test_check_smells_init.py`

Modelled on `tests/integration/test_check_addon_updates_init.py`. Cases:

1. **Default-true** — absent `[Check]` registers the hook. *(Red-capable: flip the gate default.)*
2. **Explicit `enabled = false`** — registers nothing, and prints the skip message.
3. **Declarations** — the registered entry's phase is exactly `"site_pre_render"`, its `consumes`
   is exactly `['wp_smell', 'drush_smell', 'composer_smell']`, and its `produces` is `[]`.

Case 3 is the **ordering instrument**. Its docstring MUST record what the phase string is load-
bearing for (§5.3), so a reader who sees it fail understands they have moved the emission across the
`--only-warn` gate rather than merely renamed a phase. *(Red-capable: change the registration to
`site_post_gather` — the assertion fails, and `test_hook_dag.py` stays green, which is exactly why
this assertion has to exist.)*

### 6.3 New: `tests/integration/test_check_smells.py`

The hook seam, driven through `sc.SiteContext` with the package loaded by `load_check_package`:

1. **All three smells non-empty** → three notices appended, in the builder's order.
2. **No smells** → nothing appended (the shadow path: empty-string input, PD#3).
3. **Reads the mutated key** — build a `SiteContext` whose `wp_smell` was stuffed as `""` and then
   **rebound** to a non-empty string (simulating `check.wordpress.ocp`), and assert the notice
   carries the rebound value. *(Red-capable: make `emit_smell_notices` cache the three smells into
   locals before the phase — this is the only test that would catch it.)*

### 6.4 Updated: registry and roster tests

| File | Change | Why |
|---|---|---|
| `tests/integration/test_hook_dag.py` | Add `("check", "smells", "hookdag_check_smells")` to `ALL_PACKAGES`, in alphabetical position | It is a hand-maintained "all of X" list; omitting the entry silently drops the package from both this test **and** `test_notice_roster.py`, which imports the same tuple. This is the enumerated-list drift trap. |
| `tests/integration/test_notice_roster.py` | Move `"wp-smell"`, `"drush-smell"`, `"composer-smell"` from the `# psh/gather.py` comment group to a new `# check/smells/notices.py` group. Set membership and `len(ROSTER) == 36` are **unchanged**. | The roster is grouped by owning module so a reader can trace a code to its `register()` call; leaving them under `psh/gather.py` would make the grouping a lie. |

`tests/integration/test_notice_registration.py` (the AST walk) needs no change: it already walks
`check/`, and the new module follows the `NOTICE_* = <register call>` rule.

### 6.5 Seams under test (named and agreed here, per the Spine's seam rule)

Exhaustive for this increment:

| Behavior | Seam | Existing? |
|---|---|---|
| Notice bodies / csv shape | `build_smell_notices` (pure function, direct call) | Existing — both moving test files already use it |
| Gate + declarations | `tests/helpers/checkload.py::load_check_package` + `sc.hooks` | Existing |
| Emission reads live contract keys | `check.smells.hook.emit_smell_notices(site_context)` with a hand-built `sc.SiteContext` | New, and it is the seam the relocation creates |
| Whole-run behavior neutrality | The four e2e goldens | Existing |

**No new seam is created in `main()`, and none is needed.** The change to `main()` is a pure
deletion of five lines whose behavior moves to a seam that *is* directly testable — the opposite of
the "no seam above the e2e golden" case the Spine's rule is written for.

### 6.6 Shadow paths (PD#3) and edge cases (PD#4)

| Path | Behavior | Covered by |
|---|---|---|
| Happy | all three smells non-empty → three notices | §6.3 case 1 |
| Empty input | all three `""` → no notices | §6.3 case 2, `test_smell_notices.py` |
| Nil input | Not reachable: the three keys are core-stuffed `str` at `site_post_gather` and the phase cannot fire without them. A hook running with them absent would `KeyError` loudly — acceptable, and preferable to a `.get(..., "")` that would silently emit nothing if the contract ever broke (PD#1). | Stated, not tested |
| Upstream error | A *fatal* wp/drush/composer call produces a `wp-error`/`drush-error` notice, not a smell; smells come only from non-fatal stderr. Unchanged by this increment. | Existing gather tests |
| Site skipped after the emission | Today the notices are added at `:975` and the site can still be skipped at `:986` (`resolve_recipients` → `None`), in which case they are never recorded. After the move the hook runs at `:1003`, i.e. after that skip — so a skipped site now builds *fewer* objects and records the same nothing. No observable difference. | Reasoned; no test |
| Ctrl-C mid-site | `abort_run` drops the site's `site_results` entry; notices reach `-notices.csv` only via `record_site_notices` at `:1052`, which is after both the old and the new emission point. Unchanged. | Existing `test_abort_run.py` |
| `--update` / `--import-older-metrics` | Never reach any site phase; previously also never reached `:975`. Unchanged. | Existing |
| `--create-tables` | Runs `setup` only. Unchanged. | Existing |

### 6.7 Observability (PD#5)

The relocation adds one operator-visible line and removes none: with `[Check.smells].enabled =
false`, the skip message prints at load time like every other disabled check. Hook invocation is
already traced at `-vvv` by `invoke_hooks`' `Invoking site_pre_render hook target
check.smells.hook.emit_smell_notices` debug line — which is *more* visibility than the inline
emission had, since an inline call logs nothing.

### 6.8 Security (PD#6)

No new credential, network call, subprocess, or file write. The moved code interpolates
command stderr into notice bodies; it already `html.escape()`s it for the HTML body and
`json.dumps()`es it for the csv field, and both move verbatim. No `sc.console.print` is added, so
the rich-markup escaping gotcha does not arise.

## 7. What MUST stay byte-identical

This increment's safety argument is that it is observably behavior-neutral. The following are the
claims a reviewer MUST check, not take on trust:

1. **All four e2e goldens.** No golden renders a smell notice — verified by grepping
   `tests/e2e/__snapshots__/` for `smell`, `WP CLI REPORTED`, `DRUSH REPORTED`, and
   `COMPOSER REPORTED`: zero hits. (CAMPAIGN.md §10's grep found the same.)
2. **`tests/integration/__snapshots__/test_smell_notice_render.ambr`** (§6.1).
3. **`-notices.csv` row values and order** on a full-report run: the info bucket is unchanged
   because nothing between `psh/cli.py:975` and `:1003` appends to `site_context["notices"]`
   (verified: `resolve_recipients` and `stuff_plans_contract` append none), and
   `sort_notices_and_subject` is a stable three-bucket partition, so within-bucket order is
   insertion order.
4. **`--only-warn` output**: no smell rows, before and after (§3.2 obstacle 3).
5. **`len(ROSTER) == 36`** and the registry set (§6.4).

## 8. Risks

| Risk | Mitigation |
|---|---|
| A literal loses or gains indentation in the move, changing a rendered email invisibly to `git diff -w` | Invariant 8; the pasted before/after blocks in the task report; the byte-identical `.ambr` |
| The new package is added to `check/` but not to `ALL_PACKAGES`, silently dropping it from two tests | §6.4 makes it an explicit deliverable; `test_notice_roster.py` goes **red** if it is missed, because the three codes would then be unregistered — so this one fails loudly, by construction |
| A later maintainer moves the hook to `site_post_gather` "beside its siblings" | §5.3 docstring + §6.2 case 3 |
| `[Check.smells]` is set to `false` in the U-M production config by copy-paste | Default is true and the sample config ships `true`; the disabled branch prints a skip message on every run |

## 9. Documentation deliverables

### 9.1 `CLAUDE.md`

- Add `check/smells/` to the `find_modules()` package list and to the `check/` package
  descriptions, stating the phase and the reason for it.
- Update the `psh/gather.py` bullet: `build_smell_notices` no longer lives there, and the sentence
  asserting the emission "stays in `main()`" is now false.
- Update the "Per-site report pipeline" prose that says the recommendation and smell emission run
  inline, and the `site_pre_render` contract row (which today says the phase has no notice-adding
  consumer beyond annual-billing).
- Update the Testing section's smell-test references (`test_smell_notice_render.py`,
  `test_smell_notices.py`) to their new load mechanism, and add the two new test files.

### 9.2 `CAMPAIGN.md` amendment

Per that document's preamble, amend and ledger. Two edits:

- **§3.2** — replace the "The B48 smell notices are **not** a `check/addon_updates/` hook"
  paragraph with one recording that the emission moved to `check/smells/` at `site_pre_render` on
  2026-08-07, that the three obstacles were `site_post_gather`-specific, and that `mutates` was
  consequently not built.
- **§3.3** — remove "the B48 smell-notice *emission* call" from the exhaustive
  what-stays-in-`main()` list, with the same cross-reference.

### 9.3 `LEDGER.md`

Append a post-campaign entry (not `I<N>`-numbered), modelled on the 2026-08-07 main-extraction
entry: what moved, the §3 finding, the two CAMPAIGN.md amendments, the disposition of the README TO
DO, and the byte-identity evidence.

### 9.4 `CONTEXT.md` (PD#11)

Add a **Smell** entry to the glossary. The term is now a package name, which elevates it from an
internal variable prefix to vocabulary a reader meets in the directory listing; and the report-facing
phrase differs from it, which is exactly the kind of split the glossary exists to record:

```markdown
**Smell**:
Non-fatal text a `wp`, `drush`, or `composer` command wrote to stderr while still
succeeding — reported to the site owner as "PHP code problems". Internal vocabulary:
the word never appears in a report.
_Avoid_: warning (that is a notice severity), error (a smell is not a failure)
```

### 9.5 `README.md`

Delete the first TO DO item (the `mutates` one) in its entirety. Nothing replaces it; §3.3 and the
LEDGER entry carry the reasoning.

## 10. Acceptance criteria

### 10.1 Baseline — run 2026-08-07, before any change, pasted verbatim

```
$ source .venv/bin/activate && ./run-tests --fast
All checks passed!
0 errors, 0 warnings, 0 informations
============================= test session starts ==============================
platform linux -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0
rootdir: /workspace
configfile: pyproject.toml
testpaths: tests
plugins: syrupy-5.4.0, hypothesis-6.156.1, cov-7.1.0, playwright-0.8.0, base-url-2.1.0, anyio-4.14.1
collected 1846 items / 2 deselected / 1844 selected
...
--------------------------- snapshot report summary ----------------------------
107 snapshots passed.
========= 1841 passed, 3 skipped, 2 deselected, 15 warnings in 42.33s ==========
```

```
$ grep -rl "smell\|WP CLI REPORTED\|DRUSH REPORTED\|COMPOSER REPORTED" tests/e2e/__snapshots__/
(no output — no golden renders a smell notice)
```

### 10.2 After the change — exact commands and required outputs

| # | Command | Required result |
|---|---|---|
| 1 | `./run-tests --fast` | ruff `All checks passed!`; pyright `0 errors, 0 warnings, 0 informations`; **0 failed**; snapshot summary reports **`107 snapshots passed`** plus any snapshots the new test files add (none are planned, so 107 is the expected number) |
| 2 | `git diff --stat tests/integration/__snapshots__/` | **empty** — §7.2 |
| 3 | `git diff --stat tests/e2e/__snapshots__/` | **empty** — §7.1 |
| 4 | `./run-tests --fast tests/e2e` | all e2e tests pass with no `--update-goldens` |
| 5 | `grep -c build_smell_notices psh/cli.py psh/gather.py` | `0` in both files |
| 6 | `./run-tests --fast -k smell` | the moved + new tests pass |

Test counts MUST go **up** by the number of new cases (§6.2 three, §6.3 three) and MUST NOT go down:
a moved test that silently stopped being collected (a rename, a lost `pytestmark`) is PD#14 exactly.
The task report MUST paste the final `passed / skipped / deselected` line and state the delta.

### 10.3 Tests are load-bearing — NEVER block

- NEVER delete, skip, `xfail`, or weaken a test to make this increment green.
- NEVER regenerate `tests/integration/__snapshots__/test_smell_notice_render.ambr` or any e2e
  golden. If one goes red, the move is wrong; fix the move. A golden regeneration in this increment
  requires a reviewed diff and an explicit approval recorded in the task report — and §7 says the
  correct diff is empty, so there is nothing to approve.
- NEVER lower a gate (ruff, pyright) to pass.

## 11. Disposition of the README TO DO (PD#9)

| Item | Disposition |
|---|---|
| "Add a `mutates` hook declaration to the DAG" | **Superseded, not deferred.** Its stated payoff (relocating B48 out of `main()`) is delivered here without it; §3 records why the edge kind is not needed and §4.2 records what would make it worth reconsidering. The README item is deleted (§9.5); the reasoning lives in this spec, the LEDGER entry, and the CAMPAIGN.md amendment. |

## 12. Closing audit questions (answer after implementation, in the task report)

1. Did the `.ambr` and all four e2e goldens come out byte-identical, and was the diff actually run
   rather than assumed?
2. Was every new test shown red on the condition it guards, with the failing output pasted?
3. Did `psh/gather.py` lose exactly the orphaned `import json` — and nothing else that was still
   used? (`html` MUST remain: it has 12 `html.escape` call sites in that file, only 3 of which are
   in the moved builder.)
4. Is `check/smells/` present in **both** `ALL_PACKAGES` and the `ROSTER` comment grouping?
5. Does any documentation still claim the smell emission stays in `main()`? (Grep `CLAUDE.md`,
   `CAMPAIGN.md`, `psh/gather.py`, `psh/cli.py`, `check/addon_updates/__init__.py` — the last of
   which carries a "CAMPAIGN.md amendment 1 (D-i10-1)" paragraph asserting it.)

# SPEC — Campaign increment I12: `psh/render.py` + `psh/mail.py` + annual billing → `check/umich/`

**Increment of:** `development/2026-07-17-modularization-campaign/CAMPAIGN.md` (the frozen
architecture; cited below by section number, re-deriving nothing). Read with `LEDGER.md`
(through I11) and `BLOCKMAP.md` rows B49–B57.

**Scope sentence (CAMPAIGN §11 row I12):** "B49–B57 minus sort/subject core |
`psh/render.py`, `psh/mail.py`; annual billing → `check/umich/` at `site_pre_render`;
B51 deletion if past its date."

## Glossary (this spec only; campaign terms in CAMPAIGN.md, domain terms in CONTEXT.md)

- **Billing keys** — the two hook-produced `site_context` keys this increment introduces:
  `annual_bill_upcoming`, `annual_bill_in_progress` (each a legacy notice dict, present
  only when its producing hook ran and its condition held; §4's hook-produced-key class,
  the I10 `drupal_multisite` precedent).
- **Sort/subject helper** — `sort_notices_and_subject`, the pure module-level def this
  increment extracts into `psh/_legacy.py` (final home: I13's `main()`), carrying the B50
  sort/subject core *plus* the billing-key wiring.
- **The send block** — B57's five statements in `main()` (`smtp_login()` … `quit()`),
  which do NOT move (see D-i12-4).

MUST / SHOULD / MAY / NEVER as defined in CAMPAIGN.md preamble.

## 1. Scope

**Moves (exhaustive):**

| What (block / def) | From | To |
|---|---|---|
| `escape_url` | `psh/_legacy.py:176` | `psh/render.py` |
| B53 Jinja render + B54 PHP inline + `!important` pass (`_legacy.py:1597–1635`) | `main()` | `psh/render.py` `render_report()` |
| B49 recipient resolution (`_legacy.py:1486–1504`) | `main()` | `psh/mail.py` `resolve_recipients()` |
| `smtp_login` | `psh/_legacy.py:266` | `psh/mail.py` |
| B55 MIME assembly + `.eml` write (`_legacy.py:1637–1698`) | `main()` | `psh/mail.py` `assemble_message()` |
| B50 billing branch (`_legacy.py:1517–1526`) + B51 (`_legacy.py:1538–1546`) + both builders (`_legacy.py:855–948`) | `main()` / module level | `check/umich/annual_billing.py`, two `site_pre_render` hooks |
| B50-minus-billing sort/subject core (`_legacy.py:1507–1532` minus billing lines) | inline in `main()` | pure helper `sort_notices_and_subject` in `psh/_legacy.py` (I13 absorbs) |

**Also in scope (exhaustive):** the three `escape_url` call-time bridges in
`psh/gather.py` become one module-level `from psh.render import escape_url` (LEDGER
I9/I10 obligation, discharged here); new façade name `sc.contract_year_end` (§3.5,
additions allowed); orphaned-import removal in `_legacy.py`; test repoints forced by the
moves; docs/ledger/memory updates (§7 obligations).

**NOT in scope (exhaustive, with why):**
- **B56 and the send block's counter writes** — §3.3/§11 assign B56 and the B14
  accumulators to I13.
- **B51 deletion** — its marker says "remove at the beginning of August 2026"; today is
  2026-07-23, the date has NOT passed, so per §11 ("deletion if past its date") B51
  relocates intact, TODO comment included. I14 re-evaluates (ledger entry will carry this).
- **`Notice`-class adoption** (LEDGER I3/I10 candidates) — every notice touched here
  carries extra csv fields; adoption needs the reserved §6 field-set amendment. Deferred
  to I14 (re-ledgered).
- **Template `sites/0/` portal URLs for non-U-M runs** (LEDGER I1 Obs. 1) — any template
  edit moves goldens (Invariant 1). I14/post-campaign.
- **§3.2's "portal-URL text for the recommendation notice (B47's U-M half)"** — already
  handled: I1 gated the copy on `umich_enabled()` and I7 moved it into
  `psh/plans.build_plan_recommendation_notice`. No further relocation is scheduled by §11
  row I12; noted so nobody re-derives it.
- **Template-dict construction and the `make_msgid` CID lines** — stay in `main()`
  (D-i12-2 below).

## 2. Design

### 2.1 Flow after I12 (PD#8)

```
main() per-site tail (full-report path):
  recipients ── psh.mail.resolve_recipients(site, site_id) ──► (recipients, contacts)
      │            └─ None on fatal team fetch ──► main(): continue   (unchanged skip)
      ▼
  stuff_plans_contract(...)                                   (unchanged)
  sc.invoke_hooks("site_pre_render", site_context)  ◄── check.umich.annual_billing:
      │                                                  upcoming hook ── produces
      │                                                    annual_bill_upcoming iff
      │                                                    sc.contract_year_end(end_date)
      │                                                  in-progress hook ── produces
      │                                                    annual_bill_in_progress always
      ▼                                                  (both: only when [UMich].enabled
  sorted_notices, subject =                               registered the hooks)
      sort_notices_and_subject(site_context, report)   ← pure helper, reads the two
      │                                                   billing keys with .get()
      ▼
  banner_cid / chart_cid = make_msgid(...)                    (stays, D-i12-2)
  template_dict = dict(...)                                   (stays, D-i12-2)
  html_body, text_body = psh.render.render_report(site["name"], template_dict)
      │        (Jinja → build/{s}.html/.txt → php inline-styles.php → !important
      │         pass → build/{s}-inline.html/-inline2.html; returns final bodies)
      ▼
  msg = psh.mail.assemble_message(subject, recipients, text_body, html_body,
                                  wordmark_image, chart_image, banner_cid, chart_cid,
                                  site_context["attachments"], site["name"], end_date)
      │        (EmailMessage + [Email] config + dry-run addressing + related parts;
      │         writes build/{s}.eml)
      ▼
  B56 csv append (stays) ──► if smtp_enabled: send block (stays, D-i12-4)
```

### 2.2 The annual-billing relocation (the increment's one non-move design)

Today (baseline AND current — verified against `a47418c`): the two billing notices are
inserted into the `sorted_notices` local, NEVER into `site_context["notices"]`, so their
csv rows never reach `all_warnings` / `-notices.csv`, and the in-progress notice —
inserted after the subject computation — never influences the subject even though it
renders first. Both quirks are load-bearing history and MUST be preserved.

Mechanism: **hook-produced keys** (§4, I10 `drupal_multisite` precedent), NOT
`add_notice`. A `site_pre_render` hook that called `add_notice` would (a) add billing
rows to `-notices.csv` (a §8 artifact-content change beyond the sanctioned B51 deletion)
and (b) lose the pinned-to-front ordering. Rejected.

`check/umich/annual_billing.py` (one module, two hooks, shared derivation helper —
deletion-friendly for B51's scheduled removal, DRY for the shortcode/annual-bill lines):

- `check_annual_bill_upcoming` — consumes `['end_date', 'current_plan']`, produces
  `['annual_bill_upcoming']`. Early-returns unless `sc.contract_year_end(end_date)`
  (the B50 `end_of_contract_year` condition; `umich_enabled` is subsumed by the
  `__init__.py` registration gate, exactly like `oidc_login`/`drupal_ua`). Sets
  `site_context["annual_bill_upcoming"] = build_annual_bill_upcoming_notice(...)`.
- `check_annual_bill_in_progress` — consumes `['current_plan']`, produces
  `['annual_bill_in_progress']`. Sets its key unconditionally when it runs (matches
  today's bare `if umich_enabled():`). Carries the verbatim "TODO: remove this section at
  the beginning of August 2026" marker.

Data sources inside the hooks (all reachable without new contract keys):
`site_context["site"]` (name, `plan_name`), `site_context["current_plan"]` (I7 registry
key, stuffed before the phase), `sc.config["UMich"]["portal"]["sites"][name]`
(`shortcode`, `id` → `portal_site_id`; guaranteed present — B15 `continue`s any site not
in the portal on a U-M run), and `sc.config["Pantheon"]["plan_info"][current_plan]["cost"]`
— the SAME object `main()`'s `plan_info` alias reads (`PlanCatalog.from_config` mutates
in place; CLAUDE.md § Single-module core). `end_of_contract_year` derivation needs
`psh.plans.contract_year_end`, which checks cannot import (Invariant 9) → new façade
line `sc.contract_year_end = contract_year_end` in `_legacy.py`'s exposure block.

Registration (in `check/umich/__init__.py`, inside the existing `[UMich].enabled` guard,
after `drupal_ua`): upcoming, then in_progress (mirrors B50-before-B51 block order; no
DAG edges between them, registration order preserved).

DAG validation: both consume registry-owned keys from earlier phases (`end_date`,
`site_post_traffic`) or the same phase's core registry (`current_plan`) — conditions 1–4
hold; the produced keys have one owner each and no consumer hook (edgeless, like
`drupal_multisite`).

### 2.3 The sort/subject helper (the seam discharging LEDGER I1's MUST)

The sort/subject region MOVES BELOW `invoke_hooks("site_pre_render")` (nothing between
its current position and the phase reads `sorted_notices`/`subject` — verified:
only `stuff_plans_contract` and the invoke sit between). Extracted verbatim as:

```python
def sort_notices_and_subject(site_context, report):
    """B50 sort/subject core + billing-key wiring (pure; final home I13's main())."""
    # -> (sorted_notices, subject)
```

Body = today's lines 1507–1546 with exactly these substitutions (exhaustive):
`site_context["notices"]` reads unchanged; `site["name"]` → `site_context["site"]["name"]`
(same object); the B50 condition `end_of_contract_year and umich_enabled()` becomes
`(upcoming := site_context.get("annual_bill_upcoming")) is not None` — equivalent by
construction (the key exists iff the hook was registered [umich] AND its window condition
held [end_of_contract_year]); the two builder calls + config reads become the produced
dicts; B51's `if umich_enabled():` becomes the `annual_bill_in_progress` `.get()`. The
`elif` chain, insert positions (`insert(0, …)` upcoming-at-subject-time,
in-progress-last-so-it-renders-first), and all f-strings stay byte-identical.

This helper is the runtime-testable seam for the umich-only billing call sites that
LEDGER I1 flagged as never-tested (goldens are umich-disabled; the interlock bars a
U-M run). Tests build a `sc.SiteContext` with/without the billing keys directly.

### 2.4 `psh/render.py`

- `escape_url(url)` — verbatim (one-line quote wrapper).
- `render_report(site_name: str, template_dict: dict) -> tuple[str, str]` — verbatim
  B53-render + B54: reads `email_template.html`/`.txt`, renders, writes
  `build/{site}.html`/`.txt`, runs `php inline-styles.php` (`subprocess.run`,
  `check=True` — a failure raises `CalledProcessError` into `main()`'s
  `except BaseException` abort path, unchanged), applies the `!important` regex pass,
  writes `-inline.html`/`-inline2.html`, returns `(html_body, text_body)` where
  `html_body` is the `-inline2` content actually attached to the message.

`psh/gather.py`'s three call-time `from psh._legacy import escape_url` bridges are
replaced by ONE module-level `from psh.render import escape_url` (no cycle: render
imports only stdlib + jinja2 + `sc`; gather ← render is acyclic). The D-i6-2-style
bridge comments are deleted with the bridges.

### 2.5 `psh/mail.py`

- `smtp_login() -> SMTP_SSL` — verbatim (including the `sys.exit` on missing creds).
- `resolve_recipients(site, site_id) -> tuple[str, str] | None` — verbatim B49; returns
  `(recipients, contacts)`; the generic branch returns `None` after printing the fatal
  team-fetch error (D-i6-1 pattern: `main()` does `if resolved is None: continue`).
  The `lsa-disko-project`/`umma-inside-wp` special case moves verbatim (already
  inside the `umich_enabled()` branch; TDx tickets cited in the comment).
- `assemble_message(subject, recipients, text_body, html_body, wordmark_image,
  chart_image, banner_cid, chart_cid, attachments, site_name, end_date)
  -> EmailMessage` — verbatim B55 including the `[Email]` config reads, dry-run
  addressing (`sc.smtp_username()`), the `Reply-to` header spelling, related-part
  attachment loop, and the `build/{site}.eml` write (docstring states the write).

### 2.6 What stays in `main()` (D-i12 ledger notes, the D-i6-1 "bodies move, glue stays" family)

- **D-i12-1**: loop control — the `resolve_recipients` `None` → `continue`.
- **D-i12-2**: the `make_msgid` CID pair and the `template_dict` literal. Moving the dict
  build would create a ~25-parameter function strictly worse than the dict literal
  (I11 threaded 13 and was already the campaign's widest). §3.1's B53 row is read as
  "the render bodies move"; the dict is `main()`-local data-shaping, I13 material.
- **D-i12-3**: `report`/`subject` strings and the sort/subject helper call (§3.3:
  "notice sort + subject (B50 minus billing)" stays; the helper lives in `_legacy.py`
  as a module-level def — the I10 `no_primary_domain_notice` precedent).
- **D-i12-4**: **the send block (B57) does not move.** Its five statements interleave the
  B14 accumulator writes between `send_message()` and `quit()`; hoisting them into a
  `psh/mail.py` function would put the counter updates after `quit()` returns, reopening
  the documented Ctrl-C-during-`quit()` duplicate-email window (Invariant 4: resume-point
  next-site-after-email; CLAUDE.md § Database, notices-before-send paragraph). The
  accumulators are §11-row-I13 scope; B57's residue moves with them. `psh/mail.py` ships
  `smtp_login` (§3.1 row) and `main()` keeps calling it.

## 3. Behavior bar (§8) analysis

| Surface | Effect |
|---|---|
| Four goldens | NONE (byte-identical required; all moves verbatim; goldens run umich-disabled and exercise render+mail end-to-end) |
| `-notices.csv` / `-results.json` / `-run.json` | NONE (billing keys never enter `site_context["notices"]`; B56 untouched) |
| Notice csv values | NONE (B51 not deleted — date not passed; §8's I12 sanction goes unused) |
| Rendered emails, U-M June runs | NONE (subject override + [in-progress, upcoming, …] front order preserved by construction; pinned by new helper tests) |
| stdout | NONE intended (error prints move verbatim) |
| Config | no new keys, no renames (billing stays under existing `[UMich]`) |
| Exit codes / abort paths | NONE (`CalledProcessError`, `SystemExit` from `smtp_login`, team-fetch `continue` all unchanged) |
| `site_pre_render` seam semantics | Deliberate improvement, ledgered: sort now runs AFTER the phase, so a FUTURE hook's `add_notice` would render. No in-repo consumer exists today (I7: "still no consumer"), so no observable change now. |

## 4. Seams under test (exhaustive; agreed here per the Spine spec bar)

| Behavior | Seam | Tier |
|---|---|---|
| Billing hooks: gating, window boundaries, produced keys, notice content, declarations | standalone package load (`tests/helpers/checkload.py`) + `sc.SiteContext`; `sc.contract_year_end`/config via `reset_sc` + monkeypatch | integration (new `test_check_umich_annual_billing.py`) |
| Builders' notice shape (existing pins) | direct call on the relocated defs (standalone module load) | unit (`test_annual_billing_notices.py`, repointed — I8 `php_eol` precedent) |
| Sort/subject core + billing wiring (the I1 MUST) | `psh.sort_notices_and_subject` pure helper | integration (new `test_sort_notices_and_subject.py`) |
| Recipient resolution | `psh.mail.resolve_recipients` via the `gateway` fixture (`psh.gateway.run_terminus`) + `recording_console` | integration (new `test_mail_recipients.py`) |
| SMTP login | `psh.mail.smtp_login`, patching **`psh.mail.SMTP_SSL`** (the I2/I10 two-binding lesson: after the move, patching `psh.SMTP_SSL` would silently not intercept — `test_email_config.py` MUST be repointed) | integration (existing, repointed) |
| render_report I/O contract | `psh.render.render_report` in a tmp workdir with the real templates + real php (the css-inliner test's precedent) | integration (new `test_render_report.py`) |
| MIME assembly + headers | existing `test_eml_headers.py` (e2e) + `test_mime_structure.py` — must stay green unchanged | e2e / integration |
| Everything end-to-end | the four goldens, byte-identical | e2e |
| Façade | `SC_FACADE_NAMES` += `contract_year_end` | unit (house rules) |
| DAG with the new hooks | `test_hook_dag.py` (`check/umich` already in `ALL_PACKAGES`) | integration |

New-golden/snapshot carve-out: none anticipated — no new rendered output exists (the
billing notices' HTML/text are pinned by the existing builder unit tests, which assert
content directly; no syrupy snapshot needed since the bodies move verbatim under
Invariant 8 with extract-diff evidence).

## 5. Ratchet (§13) predictions

`psh/render.py`, `psh/mail.py`, `check/umich/annual_billing.py` born gated (broad ruff +
pyright standard for the `psh/` two; pyright scope UNCHANGED — D-i8-7/D-i9-8/D-i10-9/I11
inherited). Predicted findings (implementer MUST confirm against real tool output, PD#14;
dispositions follow I2–I11 precedent):

- `S603`/`S607` on the `subprocess.run(["php", …])` call → noqa with reasons (fixed
  argv, no shell, repo-relative script — the sanctioned non-gateway subprocess; the
  house-rule comment at `tests/unit/test_house_rules.py:114` naming `psh/_legacy.py` as
  the inliner's home is updated to `psh/render.py` in the same change).
- `PLR0913` on `assemble_message` (11 args) → noqa, pinned-signature precedent (I6/I11).
- Possible `C901`/`PLR0915` on `render_report`/`assemble_message` (verbatim ~60-line
  bodies) → noqa if they fire; record if they don't.
- House-style `-> (str, str)`-shape hints in moved code → real annotations (§6).
- Orphans in `_legacy.py` after the moves (grep-verify each before removal, I3 rule):
  `urllib.parse`, `subprocess`, `jinja2.Template`, `EmailMessage`, `email.policy.SMTP`,
  `SMTP_SSL` orphan; `re` (fqdn_re), `make_msgid` (CIDs stay), `datetime` etc. do NOT.
  **Correction (Task 1):** `subprocess` is NOT orphaned — `psh.subprocess.Popen` is a
  documented monkeypatch seam (`test_terminus_contract.py`, `test_run_terminus_markup.py`,
  the shared-module-object seam in § Two mock seams), so the grep-verify rule (which this
  bullet already mandates) kept it, with a `# noqa: F401` + inline reason. The five other
  named imports were genuinely orphaned and removed.
- `Invariant 8`: the two billing builders' f-string literals and B49/B53/B54/B55 bodies
  move byte-for-byte; extracted-block diff evidence pasted in task reports (I2 pattern).

## 6. Task decomposition (for the plan; each test-first per `mattpocock-skills:tdd`)

1. **`psh/render.py`** — `escape_url` + `render_report`; gather bridge consolidation;
   `_legacy` re-imports + orphan removal (`urllib.parse`, `Template`, `subprocess`);
   house-rule comment update; new `test_render_report.py`.
2. **`psh/mail.py`** — `smtp_login` + `resolve_recipients` + `assemble_message`;
   `_legacy` re-imports + orphan removal (`EmailMessage`, `email.policy.SMTP`,
   `SMTP_SSL`); `test_email_config.py` seam repoint; new `test_mail_recipients.py`;
   `main()` rewired to the three calls.
3. **`check/umich/annual_billing.py`** — builders + two hooks + registration;
   `sc.contract_year_end` façade line + `SC_FACADE_NAMES`; `main()` rewiring (sort/subject
   relocation below the phase + `sort_notices_and_subject` extraction + billing-block
   removal); repoint `test_annual_billing_notices.py`; new
   `test_check_umich_annual_billing.py` + `test_sort_notices_and_subject.py`.
4. **Closing** — CLAUDE.md (module map, § Rendering, check/umich list, contract-table
   site_pre_render note for the billing keys, still-hardcoded-U-M list: billing leaves it,
   testing section), ledger entry, memory, SPEC §9 acceptance paste, archive.

Tasks 1 and 2 are independent; Task 3 depends on neither but touches the same `main()`
region as Task 2's rewiring — sequence 1 → 2 → 3 to keep each diff reviewable.

## 7. Acceptance (§16; run and pasted at close — placeholders until then)

```
./run-tests            # all three gates + full suite (live tier if credentials present)
git diff <start-sha> -- tests/e2e/__snapshots__/   # MUST be empty (Invariant 1)
uvx ruff check --config ruff-broad.toml psh/render.py psh/mail.py check/umich/annual_billing.py
# → All checks passed!
```

Baseline at spec time: fast tier 994 passed / 1 skipped / 2 deselected (LEDGER I11 full
count 996 = fast + 2 live). Expected at close: prior counts + new tests, zero snapshot
churn (107 snapshots unchanged).

## 8. Open questions carried to I13/I14 (written down per PD#9)

- I13: absorb `sort_notices_and_subject` into final `main()`; move B56/B57 residue with
  the accumulators; the three I7 dead tail inits.
- I14: B51 deletion re-check (its Aug-2026 date will have passed); `Notice`-class csv
  amendment; template `sites/0/` portal URLs; the `[UMich].portal.sites` schema docs.

## 9. Acceptance results (pasted at close)

Run 2026-07-23 (Task 4). Terminus credentials present (`ls ~/.terminus/cache/tokens/` →
`markmont@umich.edu`), so the **live tier ran** (`tests/live/test_live_smoke.py ..` — 2
tests passed, not deselected).

### `./run-tests` (all three gates + full suite, EXIT=0)

Gate order (each aborts on first failure — the gates run before pytest):

```
All checks passed!                       (ruff, narrow PD set)
All checks passed!                       (ruff-broad.toml, campaign ratchet)
0 errors, 0 warnings, 0 informations     (pyright, standard)
```

```
tests/live/test_live_smoke.py ..                                         [ 46%]
...
--------------------------- snapshot report summary ----------------------------
107 snapshots passed.
================= 1021 passed, 1 skipped, 4 warnings in 46.68s =================
Linting (ruff, narrow PD set) ...
Linting (ruff-broad.toml, campaign ratchet) ...
Type-checking (pyright, campaign ratchet) ...
```

`1021 passed / 1 skipped` (the skip is `test_db_credentials.py`'s
`importorskip("MySQLdb")` on a sqlite-only install). Baseline at spec time was fast-tier
994 passed; the increment added the new render/mail/billing/sort tests (Task 1 +3, Task 2
+4, Task 3 +17) and the full run includes the 2 live tests: fast tier closed at 1019
passed / 2 deselected, and the full run = 1019 + 2 live = **1021 passed**. Zero snapshot
churn (107 unchanged). The 4 warnings are the pre-existing `semver.compare`
PendingDeprecationWarning (`check/umich/oidc_login.py`) and the `load_module`
DeprecationWarning — both unrelated to this increment.

### `git diff 786822b -- tests/e2e/__snapshots__/` (MUST be empty — Invariant 1)

```
(empty — 0 lines; the four e2e goldens are byte-identical across the whole increment)
```

### `uvx ruff check --config ruff-broad.toml psh/render.py psh/mail.py check/umich/annual_billing.py`

```
All checks passed!
```

The three born-gated files (broad ruff + pyright standard) pass with the dispositions
recorded in the task reports (`psh/render.py`: S603/S607 + PTH123/UP015 rewrites;
`psh/mail.py`: PLR0913 + PTH123 noqa, 3 `add_related` pyright ignores; `annual_billing.py`:
no `noqa`, `_billing_inputs` real annotation `-> tuple[dict, dict, float]` after the Task 3
review fix). Pyright scope UNCHANGED (`psh/` minus `_legacy.py`) — D-i8-7 lineage inherited.

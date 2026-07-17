# SPEC — Increment I1: known-bug fixes (modularization campaign)

**Campaign:** `development/2026-07-17-modularization-campaign/` — this spec cites
`CAMPAIGN.md` by section number and re-derives nothing (CAMPAIGN preamble). Governing
inputs read in full before this spec was written: `CAMPAIGN.md`, `LEDGER.md`,
`BLOCKMAP.md`, `CLAUDE.md`, `prompts/directives.md`, `prompts/implementation-standards.md`.

**Scope (CAMPAIGN §11, row I1):** B36, B40, B41, B47 (URLs), B48, B50/B51 (codes), dead
code — the CAMPAIGN §10 known-bug inventory, each fix test-first with the test shown red
on the old behavior. All fixes land **in place in `psh/_legacy.py`** (LEDGER "Open
questions for I1/I2"): the narrow PD ruff set stays green there; the broad set stays
grandfathered; no file leaves `ruff-broad.toml`'s exclude list this increment.

MUST / SHOULD / MAY / NEVER as defined in CAMPAIGN.md (glossary tail). Block IDs (Bnn)
per `BLOCKMAP.md`. Line numbers below are against `psh/_legacy.py` at commit `aa8afd1`
(verified 2026-07-17 to still match BLOCKMAP's a47418c numbering) and will drift as
fixes land — content anchors are given for each.

## Glossary (increment-specific terms only)

- **Dead store** — a variable assigned and never read (`extra_message`/`extra_text`).
- **Preserved-bug extraction** — the TDD sequence used where a fix has no seam above the
  e2e goldens: (1) extract the code into a pure module-level helper **byte-preserving the
  bug and every literal interior**, suite green; (2) write the unit test that exposes the
  bug at the new seam and watch it fail; (3) minimal fix, green. This is the campaign's
  established pattern (`prompts/implementation-standards.md` § Test discipline:
  "extracting a pure module-level helper is part of the change").
- **Generic variant** — notice copy rendered when `umich_enabled()` is false (the
  precedent is `check/cloudflare/`'s U-M/generic split, CLAUDE.md § cachecheck).

## Canonical gate table (CAMPAIGN §8, restricted to what I1 touches)

| Gate | Rule | Source |
|---|---|---|
| Four e2e goldens | NEVER change, byte-identical | Invariant 1 |
| `-results.json` row **shape** (keys per entry) | NEVER change | §8 |
| `-results.json` **coverage** (which sites appear) | F3 adds previously-missing entries — that is the named bug | §10 bug 3 |
| Notice csv **values** | MAY change in I1 only, for the named fixes (F2, F5) | §8 |
| Notice **copy** (html/text bodies) | MAY change only for the F4 generic variant; U-M copy stays byte-identical | §8 (emails: only reachable copy is golden-covered; these notices are in zero goldens — §10 grep) |
| stdout | MAY improve; none planned | §8 |
| Config keys | none added, none touched | §5 |
| Contract keys / `sc` names / hook phases | none added, none touched | Invariants 2, 9 |
| Recorded fixtures | NEVER regenerated; F3's new dir is hand-derived, never `--record`ed | Invariant 10 |
| Column-0 `f"""` literal interiors | move verbatim, never re-indented | Invariant 8 |

## The fixes (exhaustive)

### F1 — B48 composer-smell double bug (BLOCKMAP §Bugs 1)

At 4335–4408: the `if composer_smell != "":` block is nested inside
`if drush_smell != "":`, so a composer smell is silently dropped unless a drush smell
coexists (PD#1); and the composer notice's **html** body interpolates
`{html.escape(drush_smell)}` (4395) where `composer_smell` is meant (the plaintext body
is correct).

**Fix.** Preserved-bug extraction of all three smell-notice blocks into ONE pure helper:

```python
def build_smell_notices(site_name, wp_smell, drush_smell, composer_smell):
    """Return the list of smell notice dicts (possibly empty) for one site."""
```

module-level in `psh/_legacy.py`; `main()` replaces the three inline blocks with
`site_context.add_notices(build_smell_notices(site["name"], wp_smell, drush_smell,
composer_smell))`. Then fix: (a) composer block dedented to sibling of the drush block;
(b) `drush_smell` → `composer_smell` in the html body. Every f-string literal interior is
byte-identical to today — including the composer block's baked-in 8-space indentation
(pre-existing cosmetic wart; normalizing it is I10's business, see Observations 4).

**Seam & tests** — `tests/unit/test_smell_notices.py`, unit tier, seam =
`psh.build_smell_notices` (via the `psh` fixture):
- composer smell alone → exactly one notice, code `composer-smell` (**red pre-fix**: old
  behavior returns `[]`);
- composer + drush both → composer html body contains the composer text and NOT the drush
  text (**red pre-fix**);
- wp only / drush only → one notice each, codes `wp-smell` / `drush-smell`;
- all empty → `[]` (shadow: empty input);
- all three → three notices, order wp, drush, composer (today's emission order).

csv codes and all copy unchanged (the csv comma-escaping `json.dumps(...).replace`
moves verbatim).

### F2 — B41 shared `php-eol` csv code (BLOCKMAP §Bugs 2)

At 3636–3694: the warning branch (PHP 7.4/8.1) and alert branch (< 8.2) both emit
`csv=f"{site['name']},php-eol"` — the notices CSV cannot distinguish severity.

**Fix.** Preserved-bug extraction into:

```python
def build_php_eol_notice(site_name, php_version):
    """Return the PHP-EOL notice dict, or None when php_version needs no notice."""
```

`main()` calls it with `envs["live"]["php_version"]` and `add_notice`s a non-None result.
Then fix the codes: warning branch → **`php-eol-warning`**, alert branch →
**`php-eol-alert`**. *Why these names:* the B38 updates notices already use the
`-info`/`-warning`/`-alert` suffix pattern (`updates-warning`, `updates-alert`); PD#11
says follow the established vocabulary. No in-repo consumer greps `php-eol` (verified:
zero hits outside campaign docs), and §8 licenses the value change in I1.

**Seam & tests** — `tests/unit/test_php_eol_notice.py`, unit tier, seam =
`psh.build_php_eol_notice`:
- `"7.4"` and `"8.1"` → type `warning`, csv code `php-eol-warning`;
- `"8.0"` → type `alert`, code `php-eol-alert`, body names fallback PHP `8.1`;
- `"7.0"` → alert, body names fallback `7.4`;
- `"8.2"`, `"8.3"` → `None` (shadow: no-notice path);
- warning and alert csv codes differ (**red pre-fix** — both `php-eol` after the
  preserved extraction).

Preserved as-is, on purpose (behavior-preserving move; Observations 2): the
`< "8.2"` **string** comparison, and KeyError propagation if `php_version` were absent.

### F3 — B36 unknown-framework `site_results` omission (BLOCKMAP §Bugs 3)

At 3303–3306: only the WordPress (2690) and Drupal (3009) branches write
`site_results[site["name"]]`; an unknown-framework site gets the console warning but
silently vanishes from `{ymd}-results.json` and hence from `monthly-report.txt`'s stats
(PD#1: a silent failure).

**Fix.** In the `else` branch, after the existing console print, add:

```python
site_results[site["name"]] = {
    "framework": site["framework"],
    "version": "unknown",
    "plan_name": site["plan_name"],
}
```

Same three keys as the framework branches (§8: row shape NEVER changes); `"unknown"` is
the codebase's existing failed-version sentinel (CLAUDE.md contract table).

**Seam & tests** — no seam above the goldens reaches this `else` (the fix is a missing
statement in `main()`, and a helper returning a 3-key dict literal would be a test of a
dict literal — no honest unit seam exists). The seam is **e2e stdout**, per the
`test_abort_e2e.py` precedent (asserts run output, not goldens). Note the
`{ymd}-results.json` artifact itself is written only under `sc.options.all`
(`finish_run`, 1706), which the test interlock bans — but the non-`--all` path of
`finish_run` **pprints the same `site_results` dict to stdout** (1798), so the fix is
observable from a sanctioned single-site run:
- New hand-derived fixture dir `tests/fixtures/terminus-unknownfw/`: a copy of
  `tests/fixtures/terminus/` with the `org:site:list` fixture's `framework` value for
  `its-wws-test1` changed to `"mystery"` (short, so the pprinted fragment cannot straddle
  the 80-column non-tty wrap), plus a README stating it is hand-maintained and `--record`
  never refreshes it (the `terminus-cdnchange/` precedent, Invariant 10).
- New `tests/e2e/test_unknown_framework_e2e.py`: `make_workdir` + `--create-tables` +
  `seed_traffic` + `run_program([E2E_SITE, "--date", E2E_DATE, ...],
  fixtures_dir=TERMINUS_FIXTURES_UNKNOWNFW)`; assert returncode 0, no `Traceback` in
  stderr, and `"'framework': 'mystery'"` plus `"'version': 'unknown'"` in stdout — the
  pprinted `site_results` entry (**red pre-fix**: the dict pprints `{}`; the ATTENTION
  banner alone contains `mystery` but not the quoted-key fragment). This also gives the
  unknown-framework path its first end-to-end cover (it must render a report without any
  framework section and exit 0).

### F4 — B47 un-gated U-M portal URLs (BLOCKMAP §Bugs 4)

Two of the four URL interpolations named in the bug (4240, 4248) sit in **dead stores**:
`extra_message`/`extra_text` are assigned (4214–4215 init, 4236–4250 f-strings) and read
nowhere — verified by grep, exactly four occurrences in the file. The only *live* leak is
the `its-recommends-plan` notice (4275, 4284), which a non-U-M run renders with the
broken `https://admin.webservices.umich.edu/sites/0/plan/` URL (`portal_site_id = 0`).

**Fix, part A (dead code).** Delete the `extra_message`/`extra_text` inits (4214–4215)
and assignments (4236–4250). The surrounding alt-plan computation (`bc`, `alt`, the
`savings`/`site_recommended_plan` reassignments at 4251–4257, and the console prints) is
live and stays.

**Fix, part B (the live notice).** Preserved-bug extraction into:

```python
def build_plan_recommendation_notice(site_name, current_plan, recommended_plan,
                                     savings, portal_site_id, umich):
    """Return the its-recommends-plan notice dict.  umich selects U-M vs generic copy."""
```

`main()` passes `umich_enabled()`. `umich=True` → today's copy **byte-identical**
(portal link with `portal_site_id`). `umich=False` → generic variant:

- html: first paragraph loses the anchor — `<p>Moving <strong>{site_name}</strong> to
  Pantheon's <strong>{recommended_plan}</strong> plan may save you up to
  <strong>${savings:,.2f}</strong> over the coming year if the site's traffic for the
  next 12 months is similar to the previous 12.</p>`; second paragraph keeps its first
  sentence and **drops** "Sites can move to higher plans any time, but can only be moved
  to a lower plan between June 16 - 30 each year." — that window is U-M's portal billing
  policy, factually wrong for any other institution (leaving it would trade a broken URL
  for a false claim; PD#1's spirit). text body: same two edits.
- csv unchanged in both variants: `{site},its-recommends-plan,{current},{recommended},{savings:,.2f}`.

**Seam & tests** — unit: `tests/unit/test_plan_recommendation_notice.py`, seam =
`psh.build_plan_recommendation_notice`:
- `umich=True` → html and text contain `admin.webservices.umich.edu/sites/{id}/plan/`
  with the passed id;
- `umich=False` → `admin.webservices` appears **nowhere** in the returned dict, and
  neither does `June 16` (**red pre-fix** after preserved extraction);
- csv identical across both variants; type/icon/short identical.

Integration render pin: `tests/integration/test_plan_recommendation_notice_render.py`,
syrupy snapshots of both variants' html + text (creation carve-out — written after,
reviewed byte-by-byte; U-M snapshot must equal today's copy, generic must differ only by
the two named edits).

*Why not e2e:* every non-U-M e2e already renders `admin.webservices` URLs from
`email_template.{html,txt}` (`{{portal_site_id}}` → `sites/0/`) — the known template
branding leak (CLAUDE.md § reusable path; Observations 1) — so a whole-artifact `not in`
assertion is impossible until the templates are de-U-M'd, and goldens forbid touching
them now (Invariant 1).

### F5 — B50/B51 duplicate `annual-bill` csv code (BLOCKMAP §Bugs 5)

At 4444–4514 (B50, contract-year-end "will be billed July 1") and 4522–4555 (B51,
"is being billed", marked remove-Aug-2026): both emit
`csv=f"{site['name']},annual-bill,..."` and both `insert(0, …)` — on a June-dated U-M run
a site gets two indistinguishable `annual-bill` CSV rows. CAMPAIGN §10 disposition:
distinct code now; the deletion decision is I12's (scheduled), NOT this increment's.

**Fix.** Preserved-bug extraction of the two notice dicts into:

```python
def build_annual_bill_upcoming_notice(site_name, plan_name, annual_bill, shortcode,
                                      portal_site_id):   # B50 dict
def build_annual_bill_in_progress_notice(site_name, plan_name, annual_bill, shortcode):  # B51 dict
```

`main()` keeps the conditions, the subject line, the shortcode/`annual_bill` lookups, and
the `insert(0, …)` calls; the `TODO: remove this section at the beginning of August 2026`
comment and both explanatory comments stay with the call sites. Then fix: B51's csv code →
**`annual-bill-in-progress`** (B50 keeps `annual-bill`). *Why this name:* B51's own copy
says "ITS is in the process of billing" — the code states which notice produced the row.
§8 licenses the value change; no in-repo consumer matches the string (verified).

**Seam & tests** — `tests/unit/test_annual_billing_notices.py`, unit tier, seams = the
two helpers:
- the two builders' csv codes differ (**red pre-fix** after preserved extraction);
- upcoming: code `annual-bill`, type `alert`, csv carries `annual_bill` and `shortcode`,
  html contains both portal URLs (`/plan/`, `/edit/`) with the passed id;
- in-progress: code `annual-bill-in-progress`, type `alert`, csv carries `annual_bill`
  and `shortcode`, body contains "in the process of billing".

Copy is unchanged in both notices (only B51's csv code changes); literal interiors move
verbatim.

### F6 — dead code (BLOCKMAP §Bugs 6)

Delete, with **no** replacement (exhaustive list):
1. B40, lines 3568–3634: the entire commented-out PHP-runtime-Gen2 notice (uses the
   removed `site_notices.append` idiom; cannot be revived as-is).
2. Lines 4124–4133: the commented-out overage-protection debug query.
3. Line 4107: `# plt.show()`.
4. Line 4717: the second `plt.close(fig)` **and its trailing comment** — the comment's
   memory claim is stale: `fig` is already closed at 4113 (BLOCKMAP re-verified), and no
   figure is created between.
5. F4 part A's dead stores (listed there).

**Tests: none — carve-out, stated per the standards' "say why not, in the spec" rule.**
Deleting comments and never-executed statements has no observable behavior to pin; the
four byte-identical goldens plus the full suite are the regression evidence, and a test
asserting the *absence of source text* would be a grep with no behavioral value. (This is
a deletion-only carve-out; it does not extend to F1–F5, which are all test-first.)

## Task order

F6 first (it shrinks and stabilizes the regions the other fixes edit), then F1, F2, F3,
F5, F4 — each an independent per-task commit, each green (LEDGER I0 amendment 3). F4 last
because it is the only fix with copy decisions a reviewer may want to revisit.

## Per-increment obligations checklist (CAMPAIGN §7 — tracked to done)

1. Governing documents read in full — done before this spec.
2. `prompts/implementation-standards.md` flow: subagent-driven, `mattpocock-skills:tdd`
   (not superpowers' TDD), `psh-implementer`/`psh-reviewer` dispatches, Spine citations
   by number + verbatim quote in every task report.
3. House styles in moved code: the new helpers are remnant code (`_legacy.py`, still
   grandfathered) — match surrounding style; full §6 typing happens when their target
   modules move (F1/F2 → I8–I10, F4/F5 → I7/I12).
4. Every comment/doc claim moved or written is verified (the stale `plt.close` memory
   claim is *deleted*, not moved).
5. Tests in the same change — per fix, above.
6. Docs: CLAUDE.md needs no architecture edits (fixed code is remnant-internal); the §10
   bug list stays historical (CAMPAIGN is frozen; the ledger records the fixes).
7. Memory: update only if implementation surfaces a durable non-obvious fact.
8. Ledger entry per §12 template, including the Observations below.
9. Invariants §9 — see gate table.
10. End: `/code-review`, full `./run-tests` (fast + live tier if credentials present,
    else `--fast` + ledger note), per-task commits, final commit includes this folder,
    `/archive-session`, ledger entry.

## Observations — found while writing this spec, out of I1 scope (exhaustive; → ledger)

1. `email_template.html`/`.txt` embed `admin.webservices.umich.edu/sites/{{portal_site_id}}/…`
   un-gated — every non-U-M run (and the non-U-M golden) renders `sites/0/` URLs. Already
   on CLAUDE.md's still-hardcoded-U-M list; goldens freeze it until the template work
   (I12/I14). Not fixable in I1 by Invariant 1.
2. B41 compares PHP versions as **strings** (`envs["live"]["php_version"] < "8.2"`) — a
   hypothetical "10.x" would misorder; and a missing `php_version` key would KeyError.
   Preserved by F2's extraction; candidates for I8 (B41's target increment).
3. B47's downgrade path adds **no notice** (the owner is never told; only the operator's
   `site_savings` records it), and a non-Basic downgrade recommendation appends no
   `site_savings` entry at all (the append at 4259 sits inside the Basic branch). The
   dead `extra_message` was presumably meant to surface this. I7 (B47's target) should
   decide the intended behavior.
4. The composer-smell literals carry baked-in 8-space indentation (renders indented
   plaintext); normalizes when B48 moves (I10).
5. The `its-recommends-plan` csv embeds `{savings:,.2f}` — a thousands separator inside a
   comma-separated field (`…,1,234.50`), so the row's column count varies with the amount.
   The smell notices escape embedded commas (`.replace(',', '\\,')`); this one does not.
   Pre-existing; candidate for I7 (B47's target increment) or the I3 `Notice` class work.

## Acceptance (commands run at increment end; outputs pasted below before closing)

```
./run-tests --fast --llm     # all green; collected count grows only by the new tests
./run-tests --llm            # if live-tier credentials are present in the session
git diff aa8afd1 -- tests/e2e/__snapshots__/   # MUST be empty (goldens untouched)
grep -c "annual-bill,\|,php-eol," build test artifacts as applicable per-fix evidence
```

ACCEPTANCE RESULTS (run 2026-07-17 at increment close, HEAD = 1ff9153):

```
$ ./run-tests --llm     (full suite, live tier included; tail)
All checks passed!
0 errors, 0 warnings, 0 informations
LLM_SUMMARY passed=751 failed=0 error=0 skipped=1 xfailed=0 xpassed=0
27 snapshots passed.
751 passed, 1 skipped in 28.42s
(gates run: ruff narrow PD set, ruff-broad campaign ratchet, pyright campaign ratchet)

$ git diff aa8afd1 -- tests/e2e/__snapshots__/
(empty — the four goldens are byte-identical)

$ git log --oneline aa8afd1..1ff9153
1ff9153 fix(campaign-I1): gate the U-M portal URL out of the generic plan-recommendation notice
fce225d fix(campaign-I1): give the transitional annual-billing notice its own csv code
fe7a037 fix(campaign-I1): record unknown-framework sites in site_results
2eda0dd fix(campaign-I1): distinguish php-eol warning vs alert in the notices CSV
6d05d5a fix(campaign-I1): report composer smells without a drush smell, with the right text
5518de7 fix(campaign-I1): delete dead code (Gen2 notice block, dead stores, stale plt calls)
```

Test-count arithmetic: fast tier 727 → 749 (+6 F1, +7 F2, +1 F3, +3 F5, +5 F4; F6 none
by carve-out); full run adds the live tier (751 total). Final whole-increment review
(two-axis, psh-reviewer): Standards PASS, Spec PASS, all three deferred Minor findings
ACCEPTed (triage recorded in the ledger entry).

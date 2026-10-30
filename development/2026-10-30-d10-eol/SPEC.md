# Drupal 10 end-of-life notice — SPEC

Status: approved in brainstorming 2026-10-30; revised after adversarial review round 1. Path: **bounded** (one new module in the existing
`check/drupal/` package, same shape as `d7_eol.py`); a spec is written anyway because
`prompts/new-feature-standards.md` requires one under `development/`.

## Glossary and keywords

- **Report date / `end_date`** — `site_context["end_date"]`, the `--date` the run was given (by
  convention the last day of the report month). Never the wall clock.
- **EOL** — 2026-12-09, the day Drupal 10 stops receiving security updates (D1).
- **Baseline drift** — the 11 tests `98ffa40` left red on HEAD (§0, §2).
- **MUST / NEVER** — mandatory; violating one stops the work. **SHOULD** — expected, deviations
  stated with a reason.

**Tests are load-bearing.** An implementer NEVER weakens, deletes, skips, or refreshes-to-green an
existing test or golden to make this feature pass. The ONLY sanctioned snapshot change in this
feature is the pre-declared Drupal golden refresh in §5, and only after its diff is verified. A
red test this spec does not predict is a STOP-and-report.

## 0. Prerequisite — must land first, as a SEPARATE change

The baseline drift left red by `98ffa40` ("email improvements from doughb@umich.edu") MUST be
resolved in its own change. It is **11 tests, exhaustive**:

- 8 e2e golden snapshots (`test_golden.py`, `test_golden_drupal.py`, `test_golden_nonumich.py`,
  `test_golden_cdn_change.py`, html + txt each) and 2 snapshots in
  `tests/integration/test_cachecheck_notice_render.py` (`[umich]`, `[generic]`) — **snapshot
  refreshes**;
- `tests/unit/test_cachecheck_consolidation.py::test_url_list_is_a_child_of_its_header` — **not a
  snapshot**: a hand-written literal (line ~234) expecting `…</a> (page)</li>` where `98ffa40`
  renders `<li>page: <a href=…>`. Either the literal is edited or the code is reverted; **the user
  decides which**, since only the user can say the new URL-list format is intended.

That change is made outside this feature's diff, **with the user reviewing that rendered diff on its
own** (it is a colleague's template change; only the user can say the rendered output is
intended). Folding it into this feature's "notice-only" golden refresh would bury an unreviewed
852-line template change — PD#14's "an existing golden going red is a signal" (user decision
2026-10-30, adversarial review round 1, issue 1). **Entry condition for implementation** (checked by PLAN Task 0): the §0 change is **committed**
(the working tree has no changes under `tests/`, `email_template.html`, `check/cloudflare/`), and
`./run-tests --fast` reports 0 failed. If either fails, implementation does not start.

**The spec and plan are committed (user-authorized) before Task 1** (`prompts/new-feature-standards.md`:
"Commit the spec before implementation begins").

## 1. Request (verbatim)

> I want to add a new check and notification for all sites running Drupal 10. There is already a
> similar check+notification for sites running Drupal 7, in case you want to use that as a
> starting point. The notification should use severity `sc.Severity.WARNING` before December 7,
> 2026, and switch to `sc.Severity.ALERT` after December 7. "Drupal 10 stops getting security
> updates on December 7, 2026. All Drupal 10 sites should upgrade to Drupal 11. For details, see
> Pantheon's [Drupal 10 End of Life Date, Risks and Next Steps](https://pantheon.io/learning-center/drupal/10-end-of-life)."

## 2. Verified facts (load-bearing claims, checked against the authority)

| Claim | Authority | Result |
|---|---|---|
| Drupal 10 EOL date | drupal.org core release schedule (`/about/core/policies/core-release-cycles/schedule`): *"Drupal 10 will reach end of life on December 9, 2026."* Release-week-of-Dec-7 row: *"End of security support for 11.3.x and 10.6.x."* | **December 9, 2026**, not Dec 7 (Dec 7 is the Monday of that release week) |
| Linked page title + date | https://pantheon.io/learning-center/drupal/10-end-of-life, fetched 2026-10-30: title *"Drupal 10 End of Life Date, Risks and Next Steps"*; *"Drupal 10 reaches end of life on December 9, 2026."* | URL resolves; title matches; date agrees with drupal.org |
| Report date available to a `site_post_gather` hook | `psh.modules.CONTRACT["site_post_traffic"]` = `("traffic_rows", "start_date", "end_date")`; `end_date` is `sc.options.date`, a `datetime.date` (`--date` `type=datetime.date.fromisoformat`) | `site_context["end_date"]` is a `datetime.date`, guaranteed from `site_post_traffic` onward |
| `drupal_version` shape | CLAUDE.md data-contract table: str; `"unknown"` when the fetch failed; `None` only when not Drupal | Prefix test `startswith("10.")` after a framework guard is safe |
| Suite baseline on HEAD (`98ffa40`) | `python -m pytest -p no:cacheprovider tests/e2e/ tests/integration/test_cachecheck_notice_render.py -q` (run 2026-10-30): `10 failed, 29 passed` — all 8 e2e golden tests + both `test_cachecheck_notice_render` cases. Reviewer's full non-live run: `11 failed, 1856 passed` (the 11th is in `tests/unit/test_cachecheck_consolidation.py`). Cause: `98ffa40` changed `email_template.html` (852 lines) and `check/cloudflare/notices.py` without refreshing snapshots | **The baseline is red** — see §0 prerequisite |
| Drupal e2e golden site | `tests/fixtures/terminus-drupal/d69d85e3cd0aab89.json`: `"drupal-version": "10.4.3"`; e2e `--date 2026-03-31` | The Drupal golden **will** gain this notice, as a WARNING |

## 3. Decisions

- **D1 — EOL date is 2026-12-09** (user, 2026-10-30, over the request's Dec 7): it matches the
  page the notice links to and drupal.org. The notice text says "December 9, 2026".
- **D2 — Severity is decided by the report date**, `site_context["end_date"]`, not wall-clock
  (user, 2026-10-30): deterministic, testable without a clock seam, same basis as
  `check/umich/annual_billing.py`. `end_date < 2026-12-09` → `Severity.WARNING`;
  `end_date >= 2026-12-09` → `Severity.ALERT` (the EOL day itself is ALERT).
- **D3 — Separate module** `check/drupal/d10_eol.py`, not folded into `d7_eol.py`: one module per
  check is the package convention, and d7_eol also carries the tag1_d7es module check.
- **D4 — Generic, not U-M-gated**: the text and link carry nothing institution-specific. Gated
  only by the existing `[Check.drupal].enabled` (default true).
- **D5 — Tense follows the same predicate as severity** (user, 2026-10-30, review issue 5): the
  first ALERT appears in the December report, mailed in January, so future tense would describe a
  past date in every ALERT. WARNING says "stops getting"; ALERT says "stopped getting". Nothing
  else in the body differs.
- **D6 — Default notice position** (user, 2026-10-30, review issue 7): no `order="first"`. Within
  its severity group it renders in hook order — as a WARNING, measured in the golden, after the
  `updates-addons` table; as an ALERT, after earlier alerts, so the subject line keeps naming the
  first alert. Same treatment as `drupal7-eol`. **Subject consequence (intended):** the subject is
  taken from the first sorted notice (`sort_notices_and_subject`, `psh/cli.py:640-644`), so a D10
  site with no other warning gets `Action Recommended: <site>: Upgrade to Drupal 11 | …` before
  EOL, and one with no other alert gets `Action Required: <site>: Upgrade to Drupal 11 | …` from
  the December report on. Not pinned by a test (no in-process seam above the golden for the
  subject; the Drupal golden site has a prior alert).
- **D7 — Operator stats line** (user, 2026-10-30, review issue 6): `monthly-report.txt` gains a
  "Drupal 10 EOL sites" block (count + list) below the Drupal 7 one.

## 4. Behavior

New `check/drupal/d10_eol.py`:

- Registers code **`drupal10-eol`** at import as `NOTICE_DRUPAL10_EOL = sc.registry.register(
  "drupal10-eol", description="Drupal 10 security support ends December 9, 2026")`.
- Module constant `DRUPAL10_EOL = datetime.date(2026, 12, 9)`.
- `check_d10_eol(site_context) -> None`:
  - return unless `site_context["framework"].startswith("drupal")`;
  - return unless `site_context["drupal_version"].startswith("10.")` (illustrative non-matches:
    `"unknown"`, 7.x, 9.x, 11.x, `"1.0"`, `"100.1"` — the last catches a `"10"`-without-dot bug);
  - add exactly one `sc.Notice(severity=…, code=NOTICE_DRUPAL10_EOL, short="Upgrade to Drupal 11",
    html=…, text=…)`, severity per D2.
- Body, with `{verb}` = `stops` (WARNING) or `stopped` (ALERT) per D5:
  - html: `<p><b>Drupal 10 {verb} getting security updates on December 9, 2026.</b> All Drupal 10
    sites should upgrade to Drupal 11. For details, see Pantheon's <a href="https://pantheon.io/learning-center/drupal/10-end-of-life">Drupal
    10 End of Life Date, Risks and Next Steps</a>.</p>`
  - text: the same sentences, the link rendered as `Drupal 10 End of Life Date, Risks and Next
    Steps (https://pantheon.io/learning-center/drupal/10-end-of-life)`.

`check/drupal/__init__.py` registers it at `site_post_gather` directly **after** `d7_eol`:
`{'name': 'check.drupal.d10_eol.check_d10_eol', 'func': d10_eol.check_d10_eol,
'consumes': ['framework', 'drupal_version', 'end_date'], 'produces': []}`.

## 5. Tests (test-first)

**Seam:** each test loads `check/drupal/d10_eol.py` standalone with
`tests/helpers/checkload.load_check_module` and drives `check_d10_eol` with a real
`reset_sc.SiteContext` carrying the three consumed contract keys. No gateway seam is needed (the
check does no I/O). **`--only-warn`:** `site_post_gather` runs on that path, so a warning-only run
also writes a row to `-notices.csv` — intended, as for `drupal7-eol`. **Row shape:**
`RunState.record_site_notices` inserts contacts at field 2, so the row is
`site,contacts,drupal10-eol` (cf. a real row `bus-paton,Paton.Web.Admins@umich.edu,drupal7-eol`).

- `tests/integration/test_check_drupal.py` (new test names all start `test_d10_` so `-k test_d10_`
  selects exactly them): D10 at 2026-03-31 and 2026-12-08 → one
  `drupal10-eol` notice, `type == "warning"`; at 2026-12-09 and 2026-12-10 → `type == "alert"`
  (both values asserted, so flipping either branch goes red); the WARNING text contains
  "stops getting" and the ALERT text "stopped getting" (D5); `7.1`, `9.5`, `11.1`, `unknown`, `1.0`,
  `100.1`, and a non-Drupal framework with a `10.x` version → no notice.
- `tests/integration/test_check_drupal_init.py`: hook order and declarations.
- `tests/integration/test_drupal_notice_render.py`: syrupy snapshots of html/text/short at **both**
  severities (2026-03-31 WARNING, 2026-12-10 ALERT) — new snapshots, a test-first carve-out.
- `tests/integration/test_notice_roster.py`: roster gains `drupal10-eol`; size 36 → 37.
- `tests/integration/test_notice_registration.py:100`: static-literal count 36 → 37 (the second
  roster-count pin; missed in the first draft, caught by adversarial review round 1).
- `tests/integration/test_hook_dag.py`: unchanged, must stay green (proves `end_date` is
  produced in an earlier phase).
- **Drupal e2e golden (`tests/e2e/test_golden_drupal.py`) — a deliberate, pre-declared
  refresh, on top of the §0 baseline.** It goes red; before refreshing, the diff must be shown to
  be **only** the new `drupal10-eol` WARNING notice ("stops getting") in the html and txt bodies.
  Any other difference stops the work. The other three goldens must not change (their fixtures
  are `wordpress`/`mystery`).
- **Final gate:** `./run-tests` fully green (possible only because of §0).

## 6. Docs

CLAUDE.md: the `check/drupal/` bullet (three → four checks, `d10_eol.py`, registration order) and
the "36-code roster" mention → 37.

`monthly-report.txt` (D7), directly below the `# Drupal 7 EOL sites:` block:

```
# Drupal 10 EOL sites:
grep ,drupal10-eol ${TODAY}-notices.csv | wc -l
grep ,drupal10-eol ${TODAY}-notices.csv | sort | perl -a -n -F, -e 'printf("%-30s %-65s\n", $F[0], $F[1]);'
```

The printed second column is the **contacts** field (row shape in §5), matching the Drupal 7 block.
The count is rows, not distinct sites; a resumed run can in principle duplicate a row
(`record_site_notices`: "at worst a duplicate CSV row on a re-run") — accepted, as for every other
count in that file (none measured in the two real CSVs).

That file carries an unrelated uncommitted edit (`TODAY` 20260901 → 20261101): stage only the new
block, **non-interactively** (`git add -p` is unavailable to agents here) — PLAN Task 2 Step 6
builds a patch and uses `git apply --cached`. NEVER stage the whole file.

## 7. NOT in scope (exhaustive for this feature)

- **Immediate ALERT / extra sentence for 10.x minors already out of security support (< 10.5).**
  Declined 2026-10-30: requires a hard-coded supported-minor cutoff that goes stale when the
  schedule moves, and is moot after 2026-12-09 when every 10.x is ALERT.
- **Wall-clock date basis.** Declined in favor of the report date (D2): nondeterministic output and
  goldens dependent on when they run.
- **`order="first"` for either severity** (D6). Declined 2026-10-30: it would take the subject
  line from alerts that may be more urgent (e.g. `no domains connected`, a billing problem), and
  would be the first producer of an otherwise-unexercised `order` path.
- **Refreshing the `98ffa40` template-drift snapshots in this change.** Declined (§0): separate,
  separately reviewed prerequisite.
- **More urgent ALERT wording** ("must upgrade … as soon as possible"). Declined with D5: only the
  tense changes.
- Removing the check after EOL, or a Drupal 11 EOL check — future work if wanted.

## 8. The author's own corrected claims

What the first draft got wrong and what caught it — the record of where verification failed here:

1. **The EOL date.** The request said December 7; drupal.org and the linked Pantheon page both say
   December 9. Caught at brainstorming by fetching both authorities; confirmed independently by the
   round-1 reviewer.
2. **"The suite is green."** Implicitly assumed by the plan's golden step and final gate; HEAD was
   already 10–11 tests red. Caught by the round-1 reviewer running a baseline; confirmed by the
   author (`10 failed, 29 passed`, §2).
3. **One roster-count pin.** The plan updated `test_notice_roster.py` but missed
   `test_notice_registration.py:100` (`== 36`), which CLAUDE.md names beside it. Caught by the
   reviewer applying the plan to a scratch copy and running it.
4. **Unrun acceptance criteria.** The red step's `-k d10` selected zero tests (exit 5, not a red);
   the snapshot step expected 1 snapshot where 3 are generated; the lint step expected a clean pass
   where ruff flags SIM300. All three were expected outputs written without running them — caught
   by the reviewer running each one.
5. **Body tense.** "Identical for both severities" put every ALERT in the future tense about a past
   date. Caught by the reviewer reasoning from `--date` = last day of month.

6. **Prerequisite scope.** Round 2 found §0 called all 11 baseline failures "snapshots"; one is a
   hand-written assertion that no `--snapshot-update` can fix. Also round 2: the Step 4a
   stats-line check used a two-field CSV row production never writes (contacts is field 2), and
   the plan staged `monthly-report.txt` with `git add -p`, which agents cannot run here.

## 9. Closing-audit questions (answer after implementation)

1. Did any test go red that this spec did not predict? (If yes, how was it resolved — never by
   refreshing to green.)
2. Is the Drupal golden diff in the feature commit exactly the one WARNING block (html ~489, txt
   ~835), and does the commit contain no other snapshot?
3. Does the feature commit's `monthly-report.txt` hunk contain the D10 block and no `TODAY=` line?
4. Did each of the six mutations in PLAN's run log go red against the final code?
5. Is `development/2026-10-30-d10-eol/` (after `/archive-session`) in the same commit as the code?

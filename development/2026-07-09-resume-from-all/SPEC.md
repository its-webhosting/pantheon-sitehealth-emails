# SPEC: `--resume-from <SITE_NAME>` for `pantheon-sitehealth-emails`

## Context

`--all` report runs iterate every site in the Pantheon org. A run can die partway
through (a per-site fatal, a Terminus session blowup, a crash) or the operator can
Ctrl-C it. Today the *only* way to pick up where it left off is a hand-edited,
**commented-out hack** that lives in the script itself:

```
pantheon-sitehealth-emails:1441-1445
    # The following gets uncommented (with the list of site names to skip) if we have to resume
    # this script after it gets interrupted partway through.
    # if site_name in ('aaum-alumni-association', 'advance-advanceprogram'):
    #     sc.console.print(f'... Skipping site {site_name} (on exclusion list)')
    #     continue
```

Editing source to resume is error-prone and un-testable. This feature replaces that hack
with a first-class CLI option: `--resume-from <SITE_NAME>` starts the per-site loop at the
position of `SITE_NAME` and processes it plus everything after it, in the loop's existing
order. Outcome: resume an interrupted `--all` run with one flag, no source edits.

**Key enabling fact (verified in code):** the loop iterates
`for site_name in sorted(site_name_to_id.keys())` (`pantheon-sitehealth-emails:1372`), i.e.
**alphabetical by site name**. Ordering is deterministic and stable across runs as long as
org membership is unchanged, so "resume from a named site" is well-defined and reproducible.

## Requirements & decisions (from the interview)

| # | Decision | Choice |
|---|----------|--------|
| Semantics | Inclusive: process `SITE_NAME` **and** every site after it in sorted order. | Fixed by request |
| Coupling | `--resume-from` requires `--all` (which already forbids a positional `SITE` list). | Fixed by request |
| Mode scope | Allowed with **any `--all` loop mode** — full report run, `--update`, `--only-warn`, `--import-older-metrics`. It is orthogonal: it only moves the loop's start point. | Interview |
| Unknown site | Passing a `SITE_NAME` not in the org list is a **fatal error, nonzero exit**, before any site is processed (typo must not silently skip everything). | Interview |
| Summary artifacts | On a resumed run, **append/merge** into today's `YYYYMMDD-notices.csv` and `YYYYMMDD-results.json` instead of overwriting, so the combined files accumulate across the original + resumed runs. | Interview |
| Auto-checkpoint | Out of scope — manual `--resume-from <SITE>` only. | Interview |

## Recommended approach

Smallest design that cleanly expresses the change: **a pre-loop filter on the already-sorted
site-name list**, driven by a new argparse option, plus a named-error pure helper for
testability, plus append/merge semantics on the two post-loop summary files.

### 1. New CLI option — `build_arg_parser()` (`pantheon-sitehealth-emails:146-253`)

Add after the `--all` block (`:161-167`):

```python
args_parser.add_argument(
    "--resume-from",
    metavar="SITE_NAME",
    action="store",
    default=None,
    help="with --all, start the site loop at SITE_NAME (processing it and every site "
         "after it in sorted order); use to resume an --all run that died or was interrupted",
)
```

`allow_abbrev=False` is already set, so no abbreviation of `--resume-from` is accepted.
Attribute is `sc.options.resume_from` (default `None`).

### 2. Validation — main() argument block (`pantheon-sitehealth-emails:1241-1259`)

Add the guard **before** the existing `create_tables`/`elif` sites-or-all chain (`:1242-1251`),
not after it. Placement matters: the sites-or-all `elif` at `:1248-1251` already `sys.exit`s
on `not all and no sites`, so a guard placed *after* it would be shadowed for the bare
`--resume-from X` case (no positional site, no `--all`) — the user would get the generic
"must specify … or --all" message instead of the precise one. Putting it first makes
`--resume-from X` alone yield the exact resume message:

```python
if sc.options.resume_from is not None:
    if sc.options.create_tables:
        sys.exit("The --resume-from and --create-tables options are mutually exclusive.")
    if not sc.options.all:
        sys.exit("--resume-from can only be used together with --all.")

if sc.options.create_tables:
    ...
elif (sc.options.all and len(sc.options.sites) != 0) or (
    not sc.options.all and len(sc.options.sites) == 0
):
    sys.exit("You must specify either at least one site or the --all option.")
```

`sys.exit("message")` is the house pattern for CLI validation (see `:1244`, `:1251`, `:1257`)
— exits status 1, message to stderr.  The create-tables message mirrors the existing
`--import-older-metrics`/`--create-tables` mutual-exclusion wording at `:1244`.

Cases covered by this placement:
- `--resume-from X` alone (no `--all`, no positional) → precise resume message (guard fires first). ✓
- `--resume-from X site1` (no `--all`) → precise resume message (guard fires before the elif). ✓
- `--resume-from X --all site1` → guards pass (`--all` set, no `--create-tables`); the sites-or-all
  elif then rejects it (`--all` + positional `site1`) with its own message. ✓
- `--create-tables --resume-from X` (with or without `--all`) → mutually-exclusive message. ✓

**Revised after implementation review.** This spec originally proposed treating
`--create-tables --all --resume-from X` as a "low-value edge, documented not coded": the
create-tables branch exits early at `:1308`, so `--resume-from` would be silently dropped,
which was argued to be consistent with create-tables' "ignoring all other command line options"
contract. A post-implementation code review rejected that reasoning — a flag that is accepted
and then has no effect is worse than one that errors, and `--create-tables` already refuses
`--import-older-metrics` rather than ignoring it. The create-tables check is therefore coded as
a mutual exclusion, checked before the `--all` requirement so the message names the real
conflict, and it fires before the database is touched.

### 3. Named error + pure helper (new module-level defs, near the other extracted helpers)

```python
class ResumeSiteNotFoundError(Exception):
    """--resume-from named a site not present in the org site list."""

def sites_from_resume_point(sorted_site_names, resume_from):
    """Return the suffix of sorted_site_names starting at resume_from (inclusive).

    Pure. sorted_site_names is the already-sorted list of org site names; resume_from is the
    --resume-from value. Raises ResumeSiteNotFoundError if resume_from is absent (a typo must
    not degrade into 'skip everything')."""
    try:
        i = sorted_site_names.index(resume_from)
    except ValueError:
        raise ResumeSiteNotFoundError(resume_from)
    return sorted_site_names[i:]
```

This follows the harness's **pure-helper seam** (like `classify_hostname_dns`,
`overage_blocks`): importable as `psh.sites_from_resume_point` and unit-testable in-process,
which is required because `--all` cannot run through the test subprocess interlock.

### 4. Loop filter placement (`pantheon-sitehealth-emails:1369-1374`)

Replace the inline `for site_name in sorted(...)` with a pre-computed, filtered list so
skipped-over sites do **zero** work (no banner, no `plan:info`, no `SiteContext`):

```python
site_name_to_id = {site["name"]: site_id for (site_id, site) in sites.items()}
sc.debug(site_name_to_id)

site_names = sorted(site_name_to_id.keys())
if sc.options.resume_from is not None:
    try:
        site_names = sites_from_resume_point(site_names, sc.options.resume_from)
    except ResumeSiteNotFoundError:
        sys.exit(
            f"--resume-from: site '{sc.options.resume_from}' was not found among the "
            f"{len(site_names)} sites for org {sc.config['Pantheon']['org_id']}."
        )
    sc.console.print(
        f"[bold magenta]=== Resuming from [bold]{sc.options.resume_from}[/bold] "
        f"({len(site_names)} of {site_count} sites remaining)"
    )

for site_name in site_names:
    ...
```

`site_count = len(sites)` (`:1354`, total org count) is left unchanged, so the per-site
banner keeps reading "Pantheon site N of M" with M = total org sites — informative on a
resumed run (N is position among *processed* sites, M is the full org). No change to
`current_site_number`.

### 5. Delete the commented-out manual hack

Remove `pantheon-sitehealth-emails:1441-1445` — this feature is its replacement.

### 6. Append/merge summary artifacts — post-loop block (`pantheon-sitehealth-emails:4121-4131`)

The two summary files are written **after** the loop completes; a crashed/interrupted run
never reaches this block, so there is no partial file from the crash — but a *resumed* run's
files would otherwise cover only the resumed subset. Gate append/merge on
`sc.options.resume_from`:

- **`YYYYMMDD-notices.csv`** — raw CSV lines, no header. Open mode `"a"` when resuming
  (`"w"` otherwise). `"a"` creates the file if absent.
- **`YYYYMMDD-results.json`** — a dict keyed by `site["name"]` (verified: written at
  `:2018` and `:2337` as `site_results[site["name"]] = {...}`). Merge via a helper:

```python
def merge_prior_results(path, new_results):
    """Return existing JSON at path merged with new_results (new_results wins on key
    collision, since a resumed site supersedes any earlier partial entry).

    Missing file -> returns dict(new_results). Malformed existing file -> WARN loudly and
    return dict(new_results) rather than crash at the very end of a completed run, and rather
    than silently dropping data (Prime Directive #1). "Malformed" must include valid JSON that
    is not an object (a hand-edited `[]` or `null`), which would otherwise sail past the decode
    guard and raise AttributeError on merged.update() below."""
    merged = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                merged = json.load(f)
            if not isinstance(merged, dict):
                raise ValueError(f"expected a JSON object, found {type(merged).__name__}")
        # json.JSONDecodeError is a ValueError, so this catches an unparseable file too.
        except (ValueError, OSError) as e:
            sc.console.print(
                f":warning: [bold yellow]--resume-from: could not read existing {path} "
                f"({e}); writing only this run's results."
            )
            merged = {}
    merged.update(new_results)
    return merged
```

Post-loop block becomes:

```python
if sc.options.all:
    resuming = sc.options.resume_from is not None
    sc.console.print(
        f"\n[bold green]Email sent for {emails_sent} of {site_count} sites"
        + (f" (resumed from {sc.options.resume_from})." if resuming else ".") + "\n"
    )
    ymd = datetime.datetime.today().strftime("%Y%m%d")
    with open(f"{ymd}-notices.csv", "a" if resuming else "w", encoding="utf-8") as f:
        for n in all_warnings:
            f.write(n + "\n")
    results_path = f"{ymd}-results.json"
    payload = merge_prior_results(results_path, site_results) if resuming else site_results
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4)
```

Overlap caveat (documented, not coded): if the operator resumes from a site *earlier* than
where the previous run stopped, the CSV gets duplicate rows for the overlapped sites (raw
lines are not deduped) and the JSON keeps one entry per site (new wins). Resuming from at-or-
after the interruption point avoids overlap.

Not merged (documented): the **console-only** end-of-run printouts — "Email sent for N of M
sites" and the `site_savings` / "Total savings: $…" block (`:4137-4142`) — reflect only the
resumed subset; they are not persisted, so nothing accumulates them. Only the two on-disk
summary files (`-notices.csv`, `-results.json`) are append/merged. Also note these summary
files are only *meaningful* on the full report run; `--update`/`--import-older-metrics` reach
the same post-loop block and will append near-empty files (pre-existing behavior for those
modes, harmless).

## Data-flow & decision diagrams

### Argument → loop decision

```
parse_args
   │
   ▼
[resume_from set?] ──no──────────────────────────► normal --all / SITE flow (unchanged)
   │yes
   ▼
[--create-tables set?] ──yes──► sys.exit "--resume-from and --create-tables … mutually exclusive."
   │no
   ▼
[--all set?] ──no──► sys.exit "--resume-from can only be used together with --all."
   │yes
   ▼
build sites (org:site:list)  ── TerminusError ──► sys.exit "Could not list organization sites"
   │
   ▼
site_names = sorted(names)
   │
   ▼
sites_from_resume_point(site_names, resume_from)
   │                         │
   │ found                   └─ ResumeSiteNotFoundError ─► sys.exit "site '…' not found among N sites"
   ▼
loop over suffix  ───────────────────────────────► per-site pipeline (unchanged)
```

### Summary-artifact write (post-loop)

```
                       resume_from set?
                        │            │
                  no ◄──┘            └──► yes
                  │                       │
   notices.csv:  open "w"            open "a" (create-if-absent, append rows)
   results.json: dump site_results   merge_prior_results(path, site_results) then dump
                                          │
                            ┌─────────────┼──────────────┐
                       missing file   valid JSON    malformed JSON
                            │             │               │
                       new only     existing∪new     WARN + new only
```

## Error catalog (named, no silent failures)

| Trigger | Name / mechanism | Caught by | User sees | Exit |
|---|---|---|---|---|
| `--resume-from` with `--create-tables` | `sys.exit` guard (`main`) | n/a | "The --resume-from and --create-tables options are mutually exclusive." | 1 |
| `--resume-from` without `--all` | `sys.exit` guard (`main`) | n/a | "--resume-from can only be used together with --all." | 1 |
| `SITE_NAME` not in org list | `ResumeSiteNotFoundError` raised by `sites_from_resume_point` | `main` try/except → `sys.exit` | "--resume-from: site 'X' was not found among the N sites for org …" | 1 |
| `org:site:list` fails | existing `TerminusError` | existing `sys.exit` (`:1352`) | "Could not list organization sites: …" | 1 |
| Existing `results.json` unreadable/unparseable on resume | `OSError`/`json.JSONDecodeError` in `merge_prior_results` | that function | ":warning: could not read existing …; writing only this run's results." | 0 (warn, continue) |
| Existing `results.json` is valid JSON but not an object on resume | `ValueError` raised by `merge_prior_results`' `isinstance` check | that function | ":warning: could not read existing … (expected a JSON object, found list); …" | 0 (warn, continue) |

**Shadow paths traced for `sites_from_resume_point`:** nil `resume_from` → helper not called
(guarded by `is not None`); empty `sorted_site_names` (org has zero eligible sites) →
`.index()` raises → `ResumeSiteNotFoundError` → fatal (correct: nothing to resume); upstream
error (org:site:list) → handled before the helper.

## Files to modify

| File | Change |
|---|---|
| `pantheon-sitehealth-emails` | Add `--resume-from` arg (`~:167`); add requires-`--all` + mutually-exclusive-with-`--create-tables` guards (`~:1259`); add `ResumeSiteNotFoundError` + `sites_from_resume_point` + `merge_prior_results` (module-level, near other extracted helpers); pre-loop filter (`:1369-1374`); delete commented hack (`:1441-1445`); append/merge post-loop block (`:4121-4131`). |
| `tests/unit/test_argparse_contract.py` | Parser default/value for `--resume-from`; requires-`--all` and mutually-exclusive-with-`--create-tables` validation via `program_runner`. |
| `tests/unit/test_resume_from.py` (new) | Pure-helper unit + Hypothesis property tests for `sites_from_resume_point`; `merge_prior_results` cases (tmp_path). |
| `README.md` | Document `--resume-from` in the flags/usage section; note requires `--all`, append/merge summary behavior, and the resume-an-interrupted-run use case. |
| `docs/resuming-interrupted-runs.md` (new) | Short end-user guide: when/how to resume, choosing `SITE_NAME`, the append/overlap caveat. |
| `CLAUDE.md` | One-line addition to the "Key flags" paragraph and a short Architecture note (pre-loop sorted-list filter, `sites_from_resume_point` pure-helper seam, requires `--all`, append/merge summary artifacts, hack removed). |

## Tests (extend the existing harness; honor its safety constraints)

Rationale: `--all` is banned in the `run_program`/`program_runner` subprocess interlock
(`tests/conftest.py:52`, `:300-320`), so the happy-path resume logic **cannot** run via
subprocess. It is exercised in-process through the pure helper (the harness's sanctioned
approach for `--all`-gated logic), and the validation error is exercised via `program_runner`
(no `--all` present, so the interlock stays clear).

**Unit tier (`tests/unit/`, `pytestmark = pytest.mark.unit`):**
- `test_argparse_contract.py`:
  - `psh.parse_args([]).resume_from is None`; `psh.parse_args(["--resume-from","its-wws-test2"]).resume_from == "its-wws-test2"`.
  - `program_runner(["--resume-from","x","--config",str(MINIMAL_CONFIG),"--date","2026-03-31"])`
    (no `--all`) → `returncode != 0` and "can only be used together with --all" in output.
    (Mirrors `test_requires_sites_or_all`.)
- `test_resume_from.py` (new):
  - `sites_from_resume_point` found at first/middle/last position returns the correct
    inclusive suffix; result[0] == resume_from.
  - not-found and empty-list both raise `ResumeSiteNotFoundError`.
  - Hypothesis property: for any nonempty sorted unique list and any member `r`, the result
    is a contiguous suffix, `result[0] == r`, every element is in the input, and order is
    preserved (`input[input.index(r):] == result`).
  - `merge_prior_results` (tmp_path): missing file → equals new; valid existing → union with
    new winning on key collision; malformed existing → warns (capture via `capsys`/console)
    and returns new only; valid-JSON-but-not-an-object existing (`[]`, `null`, `5`, `"x"`) →
    same warn-and-return-new path, never an AttributeError.

**E2E / golden tier:** No change expected — the offline golden uses a single-site trimmed
`org:site:list` fixture and never runs `--all` (`tests/tools/record.py:44-53`), so
`--resume-from` cannot touch the three goldens. **Acceptance requires the goldens to remain
byte-identical** (no `--update-goldens`, no `--record`). State this explicitly in the PR.

**Not added:** a live-tier case (no new Pantheon interaction; the feature only reorders
existing calls).

## Documentation updates

- **README.md**: add `--resume-from SITE_NAME` to the options list with the requires-`--all`
  constraint, the append/merge note, and a one-line "resume a died/interrupted run" example:
  `./pantheon-sitehealth-emails --date 20240731 --all --resume-from its-wws-test1 --for-real`.
- **docs/resuming-interrupted-runs.md** (end-user only): how to read the console to find the
  last-completed site, pick `SITE_NAME` at-or-after it, the append/overlap caveat, and that
  it works with `--update`/`--only-warn`/`--import-older-metrics` too.
- **CLAUDE.md**: extend the "Key flags" paragraph (`--resume-from <SITE_NAME>` requires
  `--all`, starts the sorted loop at that site) and add to Architecture: the pre-loop filter,
  `sites_from_resume_point`/`ResumeSiteNotFoundError`, `merge_prior_results` append/merge for
  summary artifacts, and that the old commented-out manual hack was removed.

## Acceptance criteria (exact commands → observable outcomes)

1. `./run-tests --fast` → all green, including the new `test_resume_from.py` and the two new
   `test_argparse_contract.py` cases.
2. `./pantheon-sitehealth-emails --resume-from its-wws-test1` (no `--all`) → exits nonzero,
   prints "--resume-from can only be used together with --all."
3. In-process (or a scratch run against the org): `--all --resume-from <name-not-in-org>` →
   exits nonzero with "…was not found among the N sites for org …".
4. `git grep -n "on exclusion list"` returns nothing (commented hack removed).
5. `./run-tests` (full, incl. live) → green; the three e2e goldens are **byte-identical**
   (no golden/fixture refresh in the diff).
6. Manual smoke against a safe single site is not possible (needs `--all`); instead confirm
   via the helper unit tests and a dry `--all` run in a real environment where authorized,
   verifying the "Resuming from … (K of M sites remaining)" banner and that
   `YYYYMMDD-results.json` merges rather than truncates on a second resumed run.

## NOT in scope

- Auto-checkpoint / bare `--resume` (persisting last-completed site). Explicitly deferred.
- `--stop-before` / resume-to-a-range / exclusion sets.
- De-duplicating overlapped rows in `-notices.csv` on an overlapping resume (documented caveat).
- Changing the loop ordering or the "site N of M" counter semantics.

## Archival

This spec lives at `development/2026-07-09-resume-from-all/SPEC.md` per the repo's
`development/` convention (CLAUDE.md → "Development archive") and must be committed **in the
same commit as the code** it documents (not in `prompts/`, despite the generic prompt
template's default). Run `/archive-session` at implementation time to add the scrubbed
transcript and statistics alongside it.

## Adversarial review

Survived 1 round of independent adversarial review (fresh-context reviewer subagent, all
code line-numbers verified against source). **Quality score: 8/10.** One load-bearing defect
caught and fixed:

- **Consistency (fixed):** the requires-`--all` guard was originally specified *after* the
  existing sites-or-all `elif`, which would shadow the bare `--resume-from X` case and make
  the proposed test + Acceptance #2 fail. **Fix applied:** guard is now placed *before* the
  create-tables/sites-or-all block (§2), so `--resume-from` without `--all` always yields the
  precise message; the error catalog and decision diagram are now consistent with this.

Two minor notes also folded in: console-only "Total savings"/"N of M" printouts are not
merged on a resumed run (§6), and the summary files are only meaningful in report mode.

No unresolved concerns at spec time.

### Post-implementation review (after the code landed)

A high-effort multi-angle review of the implementation commit overturned two of this spec's
decisions. Both are now reflected in §2, §3/§6, the decision diagram, the error catalog, and the
test list above:

- **`--create-tables` + `--resume-from` (was "documented not coded"):** silently dropping an
  accepted flag is worse than erroring, and `--create-tables` already refuses
  `--import-older-metrics` rather than ignoring it. Now a coded mutual exclusion.
- **`merge_prior_results` malformed-file guard was too narrow:** catching only
  `json.JSONDecodeError`/`OSError` let valid-but-non-object JSON (`[]`, `null`) through to
  `merged.update()`, raising `AttributeError` at the very end of an otherwise-complete run —
  precisely the crash the function's docstring promised to prevent. Now `isinstance`-checked.

One reviewer finding is **knowingly left unfixed**: the summary artifacts are named from
wall-clock `datetime.today()`, not the report date, so a resume that crosses midnight writes to a
new dated file and the documented accumulation silently does not happen. Fixing it would change
filenames for all runs, resumed or not; deferred as a separate decision.

Findings the review raised and verification **refuted**, recorded so they are not re-litigated:
always-merge instead of gating on the flag (a non-resumed `--all` writes a complete snapshot, so
truncating is correct and merging would resurrect stale entries); duplicate `-notices.csv` rows on
the normal resume path (an interrupted run writes no CSV at all, so the resumed run creates it
fresh); reusing `plugin/cloudflare/fqdns.py:_load_existing` (a private symbol in an optional
plugin, architecturally unreachable from the core script, and it exits fatally where this must
warn); the Cloudflare fqdns refresh firing on every resume (the >24h staleness AND-term blocks
it); and the "site N of M" banner misleading the operator (the docs direct them to the site
*name*, and accurately describe the counter).

# Extract six stage bodies from `psh/cli.py::main()`

## Context

You asked whether anything in `main()` (`psh/cli.py:370-991`) should be refactored on
software-engineering grounds. **Yes — six blocks qualify.** The argument is not length.
It is that `main()` already contains function boundaries it isn't using:

- `main_fqdn` / `custom_domains` / `primary_domain` are born at 664-666 and dead by 718.
- `plugins` / `mods` / `wordpress_version` / `drupal_version` / `add_on_updates` are all
  dead at the `stuff_gather_contract` call on 763-765 — the four `= None` declarations at
  725-728 exist only to make that one call unconditional.
- `last_day` (779) and `days` (796) are pure scratch inside a 39-line span.

A local whose entire lifetime sits inside one contiguous block *is* a function's local. Both
groups also carry a live hazard today: `wp_smell` exists as a `main()` local **and** as
`site_context["wp_smell"]`, and CLAUDE.md already has to warn readers that consumers after
the phase must read the contract key, "never a stale `main()` local". Extraction deletes the
duplicate representation.

The second argument is coverage. `main()` has **no in-process caller anywhere in the suite**
(`tests/integration/test_regressions.py:79` only reads its source text), and the subprocess
interlock bans `--all`/`--for-real`, so entire regions are untestable at any tier *by
construction* — the whole resume-filter block, all five per-site skip gates, the
`--update-cloudflare-fqdns` guard, the `isinstance(domains, dict)` guard, the unknown-plan
`sys.exit`, and the zero-traffic seed's postconditions. Each extraction converts an
unreachable region into a millisecond unit test.

The campaign anticipated this: `README.md:260-267` records it as post-campaign TODO
**D-i14d-1**, naming three of these six as candidates. `main()` closed at 622 raw / 445 logic
against §3.3's 250-400 target; this lands it at roughly **437 raw / 345 logic**.

## Decisions already made

1. **Tier 1 + 2.** Six extractions. `template_dict` (918-947) and the `recommend_plan`
   8-local unpack are **out of scope**.
2. **`main()` keeps the phase spine.** Every `stuff_*_contract(...)` and
   `sc.invoke_hooks(...)` line stays inline, so `main()` still reads as
   *fetch → stuff → fire phase*. Only stage **bodies** move.
3. **Full increment.** `development/2026-08-07-main-extraction/SPEC.md`, a CAMPAIGN.md §3.3
   amendment + LEDGER.md entry, test-first per `prompts/implementation-standards.md`,
   `psh-implementer` / `psh-reviewer` subagents, ending with `/code-review` and a full
   `./run-tests`.

## Non-negotiable constraints

- **Loop control stays in `main()`** (D-i6-1). Helpers signal skip by returning a sentinel;
  `main()` does the `continue`. Precedents: `update_site_traffic -> bool`,
  `resolve_plan_name -> None`, `resolve_recipients -> tuple | None`.
- **No helper may be the sole assigner of `site_name` or `site_emailed`.** Python has no
  block scope; the `except BaseException` handler reads both at 981-982. This is a new rule
  to record, and it kills two boundaries that look natural — see "Two traps" below.
- **Smell merges stay in `main()`.** `psh/gather.py`'s module docstring is the authority
  ("main() only rebinds wp_smell/drush_smell when the returned smell is non-empty" —
  verified at `psh/gather.py:11-13`). Helpers return **deltas**; `""` means *no new smell*,
  never *clear the previous one*.
- **Does not move:** the send block (958-965, D-i12-4), the smell emission (880-884), the
  `--only-warn` gate (869-872), the `try`/`except BaseException` (969-991), and
  `sc.SiteContext(site)` (579).
- **Invariant 1** (4 goldens byte-identical) is the gate. **Invariant 8**: `git diff -w` is
  not acceptable evidence.

## The six extractions

Order is the implementation order. Each lands as its own commit with a full `./run-tests`.

### 1. `build_traffic_window` — `cli.py:770-808` → `psh/traffic.py`

Start here: no amendment needed (§3.1 already assigns B43 to `psh/traffic.py`; only
`aggregate_visits_by_month` made the trip at I6), no notice literal, no shared locals with
the smell merge, largest single win.

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

`current_plan`/`site_name` are passed as **scalars**, not derived from `site` — hooks hold
the same `site` object via `site_context["site"]`, so reading `site["plan_name"]` here would
newly expose the seed value to hook mutation.

`main()` unpacks all nine into the existing local names — do **not** rewrite the `db_retry`
lambda at 819-832 to `window.x`; it carries seven per-line `# noqa: B023` suppressions keyed
to those exact names.

*New tests (impossible today):* the zero-traffic seed's five postconditions
(`plan_on_day == {end_date: plan}`, `first_plan_day == last_plan_day == end_date`,
`len(plan_over_time) == 1`, `site_plan_start == end_date.replace(day=1)`, `estimate == -1`),
plus a Hypothesis property that `plan_on_day` is never empty — the direct guard on the P10
`IndexError`. Today the only witness is a whole `run_program` run.

### 2. `gather_framework` — `cli.py:720-759` → `psh/gather.py`

763-766 (`stuff_gather_contract` + `invoke_hooks` = B37) stay. B33/B34r/B35r/B36 are **not**
on §3.3's stay-list (verified against BLOCKMAP), so **no amendment**.

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

Touches **no** `RunState` — it returns `results_entry` and `main()` performs the accumulator
write (the `recommend_plan`/`savings_entry` precedent, and CAMPAIGN §3.4's parallel-ready
criterion). This is the one new mechanical check that D8 has ever had: call it with no
`sc.run_state` bound at all and get a clean return.

Deletes four `= None` declarations and the unknown-framework `site_results` literal from
`main()`.

### 3. `fetch_site_domains` + `resolve_site_url` — `cli.py:635-686` and `694-718` → `psh/cli.py`

**Must land in one commit** (4a deletes the aliases 4b consumes), but as **two functions**,
because `stuff_dns_contract` + `invoke_hooks` (691-692) sit between them and stay in `main()`.

```python
class SiteDomains(NamedTuple):
    domains: object              # raw domain:list payload; never None (a fatal fetch returns None instead)
    facts: dns_classify.DnsFacts # all-empty when `domains` is not a dict

def fetch_site_domains(live_site, site, site_name, site_context) -> SiteDomains | None:
    """None = fatal/undecodable fetch; the caller SKIPS the site."""

class SiteUrlFacts(NamedTuple):
    site_url: str     # "" when there is no main_fqdn and no WP-network URL
    wp_smell: str     # "" = no NEW smell -- a delta
    drush_smell: str  # "" = no NEW smell -- a delta

def resolve_site_url(site, live_site, site_context, facts) -> SiteUrlFacts:
    """Never None -- this region has no skip path."""
```

Destination is `psh/cli.py`, not `psh/dns_classify.py`: that module's docstring bars it
("pure data producer… presentation lives in `check/dns/`"), and 4a both makes a terminus call
and emits a `Notice`. `NOTICE_NO_DOMAINS` is registered at `psh/cli.py:141` and
`no_primary_domain_notice` — the same shape of helper — already lives there.

Also: delete `site_url = ""` (650, dead once 4b returns it) and the three aliases at 664-666
(`main()` holds `facts` anyway for line 691; `facts.main_fqdn` reads fine at the three
surviving sites). Five locals eliminated.

**Invariant 8, itemized.** The `NOTICE_NO_DOMAINS` literal appears in 3 of the 4 goldens
(verified: `test_golden`, `test_golden_drupal`, `test_golden_nonumich`), so the tripwire is
live — better cover than the `no_primary_domain_notice` precedent, which is in zero goldens.
What must not change: every interior line of `html=`/`text=` keeps exactly **16 leading
spaces, including both closing `"""`**. In a module-level helper `html=` lands at column 20
while its continuation lines sit at 16 — *less* indented than the keyword. That looks wrong
and is required; the precedent at `psh/cli.py:313-332` sits at column 20 inside a frame at
8/12. Add a sentinel comment at the `def`, or the next formatter run silently re-emails every
site owner a differently-indented alert. The two `if`s stay nested with the `# noqa: SIM102`
verbatim — the outer `isinstance(domains, dict)` guard is load-bearing, not defensive:
`facts.custom_domains` is `[]` for *any* non-dict payload, so removing it emits a false "paid
plan with no custom domains" **alert** to the owner. That branch has no test at any tier and
gets one here.

### 4. `resolve_site_roster` — `cli.py:495-499 + 510-528` → `psh/cli.py`

The proposed 495-528 is not contiguous. Hoist 501-509 (the Cloudflare/SMTP `sc.debug`
banners + `smtp_enabled`) to just after 493 — a zero-data-dependency statement move whose
only observable effect is console ordering on a failure path, both lines `sc.debug`. Relocate
`current_site_number = 1` (500) down to the loop prologue at ~530.

```python
class SiteRoster(NamedTuple):
    sites: dict                  # org:site:list payload keyed by site id
    name_to_id: dict[str, str]
    site_names: list[str]        # sorted, resume-filtered
    site_count: int              # len(sites) BEFORE the filter -- the banner/finish_run denominator, NEVER len(site_names)

def resolve_site_roster(org_id: str) -> SiteRoster: ...
```

Destination `psh/cli.py`, not `psh/lifecycle.py`: that module's docstring pins its
module-level imports to stdlib + `sqlalchemy.exc` + `rich`, so importing `psh.gateway` there
would need a third call-time `# noqa: PLC0415`. `psh/cli.py` already imports all four names
this uses — zero import churn.

*Coverage — the strongest of the six.* `--resume-from` requires `--all`, which is in
`conftest.FORBIDDEN_FLAGS`, so this is unreachable at the subprocess tier **permanently, by
design**. Nothing today would go red if someone "tidied" `site_count` to `len(site_names)`,
which silently changes both the resume banner and `finish_run`'s "Email sent for N of M
sites" on every resumed run.

### 5. `resolve_site_plan` — `cli.py:566-574 + 581-586` → `psh/plans.py`

Two-thirds smaller than "the per-site preamble". 537-564 (smell resets, portal gate,
selection skip, banner) is §3.3 stay-list content verbatim — *"the site-loop skeleton
(**skips, banner**, sorted order, resume filter)"* is the thing §3.3 exists to keep.

```python
def resolve_site_plan(site: dict, plan_names: list[str]) -> str | None:
    """Plan name, or None when the site must be SKIPPED (transient plan:info failure, or
    Sandbox).  Both skip paths print their own message.  sys.exit("Bailing out.") on a plan
    absent from the catalog -- a POSTCONDITION, not a caller concern.  Writes
    site["plan_name"] in place."""
```

Folding B20 into the helper moves it above `sc.SiteContext(site)` (579). Provably identical:
`SiteContext.__init__` is a `dict` `super().__init__` — no console, no `sc` write, no
`run_state` write, and on the bail path the object is discarded unread.

**`sc.SiteContext(site)` stays in `main()`.** Its position is a documented invariant *of the
loop* — CLAUDE.md: "constructed once per processed site, as far up the per-site loop as
possible (after the portal/not-requested/Sandbox skips)". Burying the constructor in a helper
hides that from the only code that can honor it, and the next skip added would have no local
signal about which side of the line it belongs on. BLOCKMAP pairs the Sandbox skip and the
`SiteContext` creation as B18, but they have different owners; splitting B18 along that line
is what keeps the amendment narrow.

*Coverage:* the unknown-plan `sys.exit("Bailing out.")` is untested — reaching it today needs
a hand-authored terminus fixture plus a subprocess run that must abort.

### 6. `validate_options` — `cli.py:399-428` → `psh/cli.py`

```python
def validate_options() -> None:
    """B5: the four argument guards, in their shadowing order.  Each guard calls
    sys.exit(<message>).  NOT pure: the --create-tables branch sets sc.options.verbose = 3.
    Reads sc.options/sc.config at call time, so main() must call it AFTER process_config()."""
```

No parameters — `sc.options`/`sc.config` at call time is the house rule and is exactly how
`tests/unit/test_argparse_contract.py` already drives `smtp_username`. The 399-402 ordering
comment stays at the **call site**: it documents a sequencing decision of `main()`.

*Coverage:* the `--update-cloudflare-fqdns` guard has **zero** tests at any tier (grep finds
it only at `psh/cli.py:425` and `plugin/cloudflare/fqdns.py:205`), and it is not
interlock-blocked — merely never exercised. `sc.options.verbose == 3` after `--create-tables`
is unobservable today. The shadowing order becomes a table-driven parametrize over all eight
flag combinations instead of eight subprocess boots.

## Two traps that look like natural boundaries and are not

1. **`site_emailed = False` at 534 is the per-iteration reset**, not the pre-loop binding at
   531. If a preamble helper owned it, `main()`'s local would never reset: site *N* emails
   (`site_emailed = True` at 964), site *N+1* aborts at `domain:list`, `abort_run(...,
   emailed=True)` advances the resume point past *N+1* — **its owner silently never receives
   their monthly report**, and `site_results.pop()` is skipped so the artifacts claim it
   completed. Invisible to all four goldens.
2. **`site_name = None` / `site_emailed = False` at 530-531 must not be swallowed** by the
   roster extraction; they sit two lines below its end. If a helper became their sole
   assigner, `abort_run` raises `NameError` *inside the handler* — after SIGINT is set to
   `SIG_IGN` and before `finish_run()`, destroying every artifact the handler exists to save.

`site_id` (535) also stays: it is read 350 lines later at 889.

## Documentation changes required

| Doc | Change |
|---|---|
| `CAMPAIGN.md` §3.3 | **B5** — bootstrap *call sequence* stays; guard bodies move |
| `CAMPAIGN.md` §3.3 | **B14** — roster resolution moves; loop skeleton stays |
| `CAMPAIGN.md` §3.3 | **B18 split** — Sandbox skip moves, `SiteContext` creation stays; **B20** moves |
| `CAMPAIGN.md` §3.3 | **B31 narrowed** — means its `stuff_dns_contract`+`invoke_hooks` seam; the `site_url` derivation inside its range moves |
| `LEDGER.md` | One entry per amendment (§12 template) + the increment entry |
| `CLOSING-AUDIT.md` Q1 | **Correction, not amendment**: its stay-list walk wrote "the gather threading + `stuff_gather_contract`" against a §3.3 row naming only **B37**, and lumped B29 (not on the list) with B31 (on it). Record D-i14d-1 discharged with the re-measured raw/logic count. |
| `README.md` | Strike the D-i14d-1 TODO |
| `CLAUDE.md` | New helper roster per module; why `SiteContext` construction did *not* move; the "no helper may be the sole assigner of `site_name`/`site_emailed`" rule |

## Verification

Per commit, in order:

1. `./run-tests --fast` — the new unit/integration tests go red before the extraction, green
   after (`mattpocock-skills:tdd`; refactoring is not part of the red→green loop).
2. `./run-tests` — **the four e2e goldens must be byte-identical.** A golden going red is a
   defect in the increment, never a refresh (Invariant 1). `--update-goldens` must not run.
3. For extraction 3 only, Invariant 8 evidence beyond the goldens: assert in the new unit
   test that `all(line.startswith(" " * 16) for line in notice.html.splitlines()[1:])`, and
   compare the pre/post `ast.get_source_segment` of the `Notice(...)` call. `git diff -w` is
   not acceptable.
4. ruff + pyright gates are inside `./run-tests` and abort before pytest.
5. Final: `/code-review` (or `prompts/adversarial-review.md`) over the whole branch, plus a
   re-measure of `main()`'s raw/logic line count for the ledger.

**Never run:** `./run-tests --record` (Invariant 10 — `terminus-cdnchange/` is hand-maintained).

## Out of scope (noted, not done)

- `template_dict` (918-947) and the `recommend_plan` 8-local unpack. D-i12-2 declined the
  former as "a ~25-parameter function"; that objection weakens once these six group the
  locals into objects, so it is worth revisiting **after** — not during.
- **Incidental finding:** the pathlib deferral is orphaned. Four `noqa` comments in `main()`
  (`cli.py:373,437,438,470`) say "pathlib migration is I14b+", but I14b's ledger entry never
  touched PTH and neither README.md nor CLAUDE.md mentions it. Not this change's business,
  but it should become a README TODO so the deferral has a home.

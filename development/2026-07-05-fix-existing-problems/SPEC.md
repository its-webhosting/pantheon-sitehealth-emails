# Fix existing problems P1–P10

## Context

`development/2026-07-04-test-suite/PROBLEMS-DISCOVERED.md` logged ten issues found while building
the test harness. Per that work's ground rule, program bugs were **logged, not fixed** — they are
fixed here. This spec designs each fix, its tests (extending the existing `tests/` harness and its
hard safety interlock — no parallel test approach), and the doc updates, then implements them.

**Verification done during planning (findings differ from the problems doc in three ways):**
- Line numbers drifted after the Part-A extraction; all numbers below are *current* (re-verified),
  treat as starting points and re-locate by symptom.
- **P1 needs no code change** (disproven at design time — every `template_dict` var is
  pre-initialized; the ≤4-month state already renders). Existing e2e pins it. Leave as-is.
- The "strict-xfail tests" the problems doc claims exist for **P2/P3 were never written.** P2 has
  **zero** coverage. P3's existing regression tests (`tests/integration/test_regressions.py`) pin
  the *current single-value* contract and **will break** when P3 is fixed — they must be rewritten,
  not "flipped." P6's `tests/integration/test_wrappers.py` already pins the real 3-tuple and stays
  green.
- `emails_sent` **is** initialized (`= 0`, current L1033), so no `NameError` under `--all`; the
  counter is simply never incremented.
- `sc.add_notice()` currently has **zero call sites**; the core script appends raw dicts to a local
  `site_notices` list (L1048, wired into `site_context` at L1289).

## Decisions (from interview)

| Topic | Decision |
|---|---|
| **P3** terminus error handling | **Full contract change** — return `(result, errors, fatal)`, `None` on decode failure, named `TerminusError`, update all 10 call sites. |
| **P8** U-M logic relocation | **Pragmatic subset** — email headers/msgid/SMTP → new `[Email]`/`[SMTP]` config (defaults byte-identical); **guard** the fqdns-gated Cloudflare/doc-URL checks behind `[UMich].enabled` **in-place** (relocation into the `umich` package deferred — the existing check hook fires too early). Leave the already-guarded date-driven billing notices. |
| **P4** DNS observability | **Distinguish + notice both** — definitive (NXDOMAIN/NoAnswer) → alert notice; transient (Timeout/NoNameservers) → distinct warning notice, NOT counted as "not in DNS". |
| **P5** dead counter | **Defer** — documented only (behind `--all`, untestable in-harness). No code change; keep entry in the problems doc. |
| Linter/formatter | **None** — no ruff/black added; acceptance rests on the pytest suite + review. |
| Non-U-M golden | **Add** — a 3rd golden with `[UMich].enabled=false` proving a non-U-M run emits no U-M content (validates P8). |
| Notice API | **Adopt `sc.add_notice()` as canonical** — use it for P4 AND migrate the 25 live raw appends + 4 builder helpers, byte-identical to goldens. |

## Scope summary

| # | Problem | Action | Golden risk | Primary test tier |
|---|---|---|---|---|
| P1 | ≤4-month path | none (already correct) | — | existing e2e (no change) |
| P2 | dead `[News]` config loop | fix loop; extract `load_news_items()` | none | unit + integration |
| P3 | `terminus()` swallows errors | full tuple contract + `TerminusError` | none* | integration (rewrite) + unit |
| P4 | DNS failures console-only | classify + structured notices | none* | integration (monkeypatch resolver) |
| P5 | dead `emails_sent` | **defer** (documented) | — | none |
| P6 | stale wrapper docstrings | fix annotations/docstrings | none | existing `test_wrappers.py` |
| P7 | wrong-option comment | fix comment | none | none |
| P8 | U-M logic not behind config | pragmatic subset → config + `umich` pkg | **high** | integration + non-UM golden |
| P9 | WCAG `link-name` | add alt/aria; drop allowlist entry | render only | render tier |
| P10 | `IndexError` on zero traffic | guard; extract `build_plan_over_time()` | none | unit + integration |
| — | `add_notice` canonical migration | 25 live appends + 4 builders → `add_notice` | **high** | goldens byte-identical |

\* golden-neutral in the offline e2e (terminus responses are well-formed; DNS is stubbed via
`fqdns.json = {}` + platform-only `domain:list`), but both U-M goldens are re-verified after each.

## NOT in scope

- **P5** (dead counter / SMTP re-enable) — deferred by decision; SMTP send stays disabled.
- **P8 full move** — the large date-driven annual-billing notice blocks (current L3466–3585) stay in
  core behind their existing `[UMich].enabled` guard; the hardcoded site names `lsa-disko-project` /
  `umma-inside-wp` (L3444) stay (already guarded). Only the reusability-breaking items are addressed.
- **Full relocation of the fqdns-gated Cloudflare/doc-URL checks into the `umich` check package** —
  deferred to the later P8 stage. The existing `check` hook fires at L1293, **before**
  `fqdns_behind_cloudflare` (init L1325, populated L1421) and the WP-plugin / Drupal-module data the
  checks consume (L1665+, L2011+) exist, so a clean relocation needs a **new post-gather per-site
  hook seam** — out of scope this round. We only *guard* the checks in-place (see P8b).
- **The email template's hardcoded U-M branding** — `email_template.html` hardcodes ~7 U-M URLs
  (L262 `its.umich.edu`, L289/290/334/336/340/342, L422 `documentation.its.umich.edu/node/4705`) and
  literal `webmaster@umich.edu` (L289, L435). These are **not** `<{ }>` substitutions and P8's
  pragmatic subset does **not** touch them. Templating them is a separate future effort; the non-U-M
  golden asserts only the strings P8 actually removes (see its test spec).
- **`{smtp_username}@umich.edu` dry-run domain** — made configurable (`[Email].dry_run_username_domain`,
  default `umich.edu`) as part of P8a so it isn't a lingering hardcode; noted here for visibility.
- Linter/formatter adoption.
- Re-enabling SMTP / SendGrid; any `--all` / `--for-real` / live `--create-tables` path.

---

## Detailed fix designs

### P1 — no change
Every variable `template_dict` consumes is pre-initialized before `if len(v) > 4:`. The existing
`tests/e2e/test_recommendation_e2e.py::test_new_site_shows_not_enough_data` pins the ≤4-month state.
Leave as-is; keep the problems-doc entry.

### P2 — config-inline `[News]` never added (current L977–993)
The guard `if not isinstance(news_item_name, dict): continue` tests a dict **key** (always a str),
so the `add_news_item` call is dead. Fix by iterating `.items()` and skipping non-dict **values**
(the scalar `folder` directive), then adding each `[News.<x>]` subtable.

**Extraction for testability:** move both loaders (config-inline + `*.toml` files) into a
module-level `load_news_items()` that reads `sc.config` / `sc.options` and populates `sc.news`
(behavior-preserving for the file path). `main()` calls `psh.load_news_items()`.

```python
def load_news_items() -> None:
    if "News" in sc.config:
        for name, value in sc.config["News"].items():
            if not isinstance(value, dict):   # skip 'folder' and other scalar directives
                continue
            sc.add_news_item(value, f"{name} in configuration file {sc.options.config}")
    folder = sc.config.get("News", {}).get("folder")
    if folder:
        for filename in sorted(glob.glob(f"{folder}/*.toml")):
            ...  # unchanged file loader
```
Shadow paths: no `[News]` table → no-op; only `folder` key → nothing added; `[News.<x>]` missing
`message` → existing `add_news_item` `sys.exit` fires (unchanged).

### P3 — `terminus()` returns `(result, errors, fatal)` + `TerminusError` (current L327–353)

Adopt the in-code TODO. `None` (not `""`) on decode failure; return the 3-tuple; a named exception
so a malformed response fails *at the call site with the real cause* instead of a `TypeError`
(`""["timeseries"]`) far away.

```
run_terminus(cmd) ── (output, errors, fatal) ─┐
                                              json.loads(output)
                            ┌──────────────────┴──────────────────┐
                          ok                                   JSONDecodeError
                           │                                       │
                     result=parsed                     result=None; errors += output+exc
                           └──────────────────┬──────────────────┘
                                    errors != "" ?
                          ┌──────────yes───────┴────────no─────────┐
                 session-expired & retry?                     (fall through)
                    │yes            │no
              sleep+retry once   (kept)
                                    └────────────► return (result, errors, fatal)
                                                          │
   caller:  result, errors, fatal = terminus(...)
            if fatal or result is None:  raise TerminusError(command, errors)
```

- **New exception** `class TerminusError(RuntimeError)` — carries the command + captured stderr;
  message the user sees: `Terminus command '<cmd>' failed: <errors>`. Triggered by: `fatal` True or
  `result is None` at a call site that needs data. Caught: at top of `main()`'s per-site loop it is
  logged as a per-site alert and the site is skipped (no whole-run abort); for org-level calls
  (`org:site:list`, `self:info`) it aborts with a clear message. Tested: yes (integration).
- **10 call sites** (current L487, 925, 1030, 1084, 1153, 1193, 1318, 2130, 2276, 3449) each become
  `x, errors, fatal = terminus(...)`. Data-indexing sites (1084 `["sku"]`, 487/1193 `["timeseries"]`,
  1318 `domains`, 3449 `site_team`, 1153 `envs`, 2276 `updates`, 2130 `audit`) check `fatal`/`None`
  before indexing; the L925 `pprint` site just unpacks.
- Shadow paths: `None` (decode fail) → `TerminusError`; valid-but-empty `{}`/`[]` → callers already
  loop/`in`-check, now with an explicit "empty response" debug log so zero-row runs aren't silent;
  upstream error → `fatal`/`errors` propagate.

**Note:** `wp()`/`drush()` already return 3-tuples with `None`-on-decode + captured errors, so they
are *not* changed by P3 (only their P6 docstrings are). `TerminusError` is terminus-only.

### P4 — classify DNS outcomes into structured notices (current L1341–1407)

Definitive vs transient must be distinguished, and both must reach the report (not console-only).

**Extraction for testability + observability:** `classify_hostname_dns(hostname, cloudflare_enabled,
cf_v4_nets, cf_v6_nets) -> (points_at_cloudflare: int, points_elsewhere: int, notices: list, transient: bool)`.
`main()` calls it, adds the returned notices via `sc.add_notice(...)`, and only emits the existing
`ATTENTION: … is not in DNS` alert when both counts are 0 **and** `transient` is False.

```
resolve(host, A) / resolve(host, AAAA)
  ├─ answers ──────► classify each IP: Cloudflare net? → points_at_cloudflare++ else points_elsewhere++
  ├─ NXDOMAIN / NoAnswer      ► DEFINITIVE : notice(type=alert,   "<host> is not in DNS")
  └─ Timeout / NoNameservers  ► TRANSIENT  : notice(type=warning, "DNS lookup for <host> failed
                                             (transient) — rerun the report"); transient=True
after both records (unchanged aggregation):
  if points_at_cloudflare==0 and points_elsewhere==0 and not transient:
        not_in_dns.append(host)          # KEEP: the single aggregated "not in DNS" notice
  if transient:  do NOT append to not_in_dns, do NOT claim "not in DNS"
```
**Aggregation preserved.** The existing code emits ONE aggregated `not_in_dns` notice over all hosts
(current L1592–1611) — that notice is **unchanged**. P4 does not switch to per-host "not in DNS"
notices; it only (a) keeps hosts out of `not_in_dns` when the failure was transient, and (b) adds
*diagnostic* notices: a `warning` transient notice per transiently-failing host, and (optionally) an
`info` note for definitive per-host failures — via `sc.add_notice()`. This keeps the offline golden
byte-identical (no `not_in_dns` hosts there) and does not restructure the aggregated notice.
Also fixes the incidental missing `style="red"` on the AAAA `NoAnswer` console line.
Shadow paths: both records NXDOMAIN → host lands in `not_in_dns` (as today); A transient + AAAA
answer → resolved, no transient notice; resolver import/None → treated as transient.

### P5 — deferred
No change. Keep the problems-doc entry; the `--all` summary and SMTP send remain as-is.

### P6 — correct wrapper docstrings/annotations (current L356, 370, 427, 442)
`wp()`, `wp_eval()`, `drush()`, `drush_php_script()` are annotated `-> (Any, str)` / `-> (str, str)`
but return 3-tuples `(result, errors, fatal)`. Correct each annotation to the real 3-tuple and fix
`wp()`'s docstring (it says "wp eval / return JSON" but runs a generic `wp` command). No runtime
change; `tests/integration/test_wrappers.py` already pins the truth and stays green.

### P7 — correct misleading comment (current L3720)
`plt.close(fig)  # needed to free up memory when sc.options.all_sites is True` → the real option is
`sc.options.all`. Comment-only.

### P8 — pragmatic-subset relocation of U-M logic

**8a. Email/SMTP → config (new keys; defaults reproduce current literals byte-for-byte).**
```
[Email]
  from        = "University of Michigan Webmaster Team <webmaster@umich.edu>"
  reply_to    = "webmaster@umich.edu"
  bcc         = "januside@go.mail.umich.edu, its-webmaster@go.mail.umich.edu"   # for_real only
  dry_run_to  = "januside@go.mail.umich.edu"        # joined with {smtp_username}@<dry_run_username_domain>
  dry_run_username_domain = "umich.edu"             # domain appended to smtp_username in dry-run To
  msgid_domain = "webservices.umich.edu"
[SMTP]
  host = "smtp.mail.umich.edu"
  port = 465
```
- `make_msgid(domain=...)` at core L3587–3588 and `check/umich/sitelens.py` L207 read
  `[Email].msgid_domain`.
- MIME headers (core L3661–3671) read `[Email].from/reply_to/bcc/dry_run_to` +
  `dry_run_username_domain`. **Preserve the exact `Reply-to` capitalization** (not RFC `Reply-To`) —
  `EmailMessage` preserves header-name case, so reading from config reproduces the exact byte.
- `smtp_login()` (L769–773) reads `[SMTP].host/port` (dormant — only called from commented send).
- When a key is absent, the default IS the current literal → U-M output unchanged.
- **Verification (no `.eml` golden exists today):** goldens are HTML (CID-normalized) + TXT only; the
  `.eml`'s `Date:` (L3672, `datetime.now(UTC)`) is volatile, which is why there is no byte `.eml`
  golden — so the moved MIME headers are currently **unguarded**. **Before P8a**, add a targeted
  header-assertion test (`tests/e2e/test_eml_headers.py`) rendering the `.eml` and asserting the exact
  `From` / `Reply-to` / `Bcc` / dry-run `To` / `Message-ID`-domain bytes (scrubbing only `Date:` and
  the `make_msgid` CID left-hand side). Only then is "byte-identical headers" a checkable claim.

**8b. Guard the fqdns-gated Cloudflare/doc-URL checks behind `[UMich].enabled` (in-place).** The WP
`umich-cloudflare` check (L1665–1689 region) and the Drupal cloudflare-module checks (L2010–2043)
are gated only by `len(fqdns_behind_cloudflare) > 0`, so they emit U-M `node/5114`/`node/4242`
doc-URL notices on *any* institution. Wrap each in the existing
`"UMich" in sc.config and … ["enabled"]` guard **in place**. This is NOT a package relocation — a
clean relocation needs a new post-gather per-site hook seam because the existing `check` hook fires
at L1293, before `fqdns_behind_cloudflare` (L1325/L1421) and the plugin/module data exist (deferred;
see NOT-in-scope). Result: **U-M golden unchanged** (guard true), **non-U-M run emits none of these
notices** (guard false). The `umich-oidc-login` / Hummingbird / Drupal user-agent notices carry U-M
specifics too but stay this round (NOT-in-scope) unless an in-place guard is trivially byte-identical.

```
[Email]/[SMTP] config ──default──► exact U-M literals (output unchanged)
core main() ─ headers/msgid/smtp ─► read config (+ header-assertion test as the guard)
core loop ─ fqdns-gated CF checks ─► wrapped in [UMich].enabled guard (silent on non-U-M)
```

**Riskiest to keep byte-identical:** the `.eml` MIME block + msgid domain; guarded by the new
header-assertion test. Do 8a and 8b as separate, separately-verified commits.

### P9 — WCAG `link-name` (render tier flags it on both reports)
**Do not assume the culprit.** Both obvious candidates already have accessible names — the static
banner anchor (`email_template.html` L262) has a non-empty `alt`, and the SiteLens gauge anchor
(`check/umich/sitelens.py` L219–220) wraps an `<img … alt="{label}: {value} / 100">`. The real
offending node is elsewhere. **Implementation MUST first reproduce** (`./run-tests -m render`,
inspect the exact axe `link-name` node/target) to identify the flagged anchor, then give it
discernible text — a non-empty `img alt` or `aria-label`. Then remove `link-name` from
`_AXE_ALLOWLIST` (`tests/render/test_render.py` L34) so the a11y smoke enforces it. Verify with
`./run-tests -m render` green.

### P10 — `IndexError` on zero traffic (current L2654–2698)
`plan_on_day` is populated only inside `for row in results:`. Zero in-window rows → `plan_on_day={}`
→ `days = sorted(plan_on_day.keys())` `[]` → `plan_on_day[days[0]]` raises `IndexError`.

**Extraction for testability (scoped to the span computation only).** `plan_on_day` feeds several
consumers, not just span-building — `days[0]`/`days[-1]` (L2677–2698) **and** a later
`plan = plan_on_day[d]` loop (~L3106). So the extraction covers **only** the span computation:
`build_plan_over_time(plan_on_day, plot_right_date) -> list` (pure; returns `[]` for empty input).
The empty-guard stays **inline** in `main()`: if `not plan_on_day`, `sc.add_notice(type=info,
"No traffic recorded yet for this site.")` and skip the plan/recommendation + traffic-graph sections
gracefully (same "new site" clean state as P1) so the later `plan_on_day[d]` consumer is never
reached either. Do not index `days[0]`.
Shadow paths: empty (zero traffic) → notice + skip *all* plan_on_day consumers; single day → one
span; normal → unchanged.

### `add_notice` canonical migration (golden-sensitive)
- Adapt `sc.add_notice(notice, notices_list)` (or keep `site_context` but ensure it targets the same
  `site_notices` list) so it is usable **before** `site_context` is built (many appends precede
  L1289) and **inside** the builder helpers (which have no `site_context`).
- Route the **25 live** direct `site_notices.append({...})` sites through `add_notice` (the append at
  L2546 is inside a fully commented-out block — dead — so it is NOT counted/migrated).
- The 4 builders (`wp_error`, `drush_error`, `check_wordpress_plugin`, `check_drupal_module`)
  **return `list[dict]`**; callers do `site_notices += builder(...)`. They do not append, so "route
  through `add_notice`" means: keep the builders returning lists, and at each `+=` call site loop the
  returned dicts through `add_notice` (`for n in builder(...): sc.add_notice(n, notices)`). (Equally
  valid: pass the target list into the builder. Either is byte-identical since the dicts are complete.)
- **Preserve every notice dict's existing keys** — verified: all 25 live dicts + all 4 builders
  already carry `type`/`icon`/`text`/`message` and none carry `order`, so `add_notice`'s
  `icon`/`text`/`order` defaults are genuine no-ops → byte-identical append. Any golden diff means a
  dict relied on a default differently; investigate before proceeding. Do this as an isolated commit
  verified by both U-M goldens; if a given site cannot migrate byte-identically, leave it raw and note it.

---

## Tests (extend the existing harness; honor the interlock)

Reuse fixtures `psh`, `reset_sc`, `temp_db`, `program_runner`/`run_program`, `rendered_report`,
`rendered_report_drupal`, module consts `MINIMAL_CONFIG`/`seed_traffic`. Never invoke the program
except via `run_program` (the `--all`/`--for-real` + live-data interlock). Only `its-wws-test1`
(WordPress) / `its-wws-test2` (Drupal), read-only.

- **P2 — `tests/unit/test_news.py`** (new): `load_news_items()` with a config carrying `folder` +
  two `[News.<x>]` subtables → both added, `folder` skipped; empty `[News]` → no-op; **no `[News]`
  section at all → no-op, NOT a crash** (the current L986 folder glob is *outside* the `if "News"`
  guard → `KeyError` today; `load_news_items` uses `sc.config.get("News", {}).get("folder")` which
  fixes this latent bug — call it out as an intended behavior change, not a golden regression); missing
  `message` → `SystemExit`. Property/edge: order preserved.
- **P3 — rewrite ALL tests pinning the old single-value / `""` contract, then add new coverage.**
  Rewrite: `tests/integration/test_regressions.py` (2 session-retry tests → `result, errors, fatal =
  terminus(...)`), `tests/integration/test_terminus_seam.py` (L16 `== {...}` and L22 `== ""`), and
  `tests/live/test_live_smoke.py` (L14/L19 single-value unpacks). Add
  **`tests/integration/test_terminus_contract.py`** (new): well-formed → `(dict, "", False)`;
  `JSONDecodeError` → `(None, errors≠"", …)`; a call site (`plan:info` / `env:metrics`) with a
  malformed `run_terminus` monkeypatch raises `TerminusError` (not `TypeError`); session-expiry still
  retries once then stops.
- **P4 — `tests/integration/test_dns.py`** (new): monkeypatch `dns.resolver.resolve` to raise
  `NXDOMAIN` → one `alert` notice, `not_in_dns` set; `Timeout` → one `warning` transient notice,
  NOT in `not_in_dns`; a Cloudflare IP → `points_at_cloudflare` counted, no "not in DNS".
- **P6** — no new test (`test_wrappers.py` already pins the 3-tuple).
- **P8 — `tests/e2e/test_eml_headers.py`** (new, **write FIRST, before P8a**): render the `.eml` and
  assert the exact `From` / `Reply-to` / `Bcc` / dry-run `To` / `Message-ID`-domain bytes (scrub only
  `Date:` and the `make_msgid` CID left-hand side). This is the guard the moved MIME headers lack today.
- **P8 — `tests/integration/test_email_config.py`** (new): headers/msgid/smtp come from `[Email]`/
  `[SMTP]` (override values appear; absent → U-M defaults). **Cloudflare-check guard:** with
  `[UMich].enabled=false`, the fqdns-gated Cloudflare notices are absent; enabled → present.
  **Non-U-M golden — `tests/e2e/test_golden_nonumich.py`** (new) + snapshot: a new
  `tests/fixtures/config/minimal-nonumich.toml` (`[UMich].enabled=false`, generic `[Email]`) run
  through the WordPress fixtures. **Assertion scoped to what P8 actually removes** — the render must
  NOT contain the P8-guarded CF doc URLs (`node/5114`, `node/4242`) NOR the moved MIME-header values
  (generic `From`/`Reply-to`/`Bcc`/msgid-domain instead of the U-M ones). It **will** still contain
  the template's hardcoded U-M branding (`its.umich.edu`, `documentation.its.umich.edu/node/4705`,
  literal `webmaster@umich.edu` at template L289/L435) — that is deferred template debt (NOT-in-scope),
  so do NOT assert "no `umich.edu` anywhere." Create with `./run-tests --update-goldens`; review.
- **P9 — `tests/render/test_render.py`**: remove `link-name` from `_AXE_ALLOWLIST`; add an assert in
  `tests/integration/test_check_sitelens.py` that each gauge image/anchor has a non-empty
  `alt`/`aria-label`.
- **P10 — `tests/unit/test_plan_over_time.py`** (new): `build_plan_over_time({}, …) == []`;
  single-day and multi-plan spans. **`tests/e2e` or integration:** a run against an empty
  `temp_db` (zero in-window rows) renders a clean "no traffic yet" report and does **not** raise
  `IndexError`.
- **Regression guard:** both U-M goldens (`test_golden.py`, `test_golden_drupal.py`) stay
  **byte-identical** through every step — they are the primary guard for the `add_notice` migration
  and P8.

## Acceptance criteria (exact commands + observable outcomes)

1. `./run-tests --fast` → all green (unit + integration + e2e + render, offline). Show output.
2. `./run-tests -m e2e` → both U-M goldens pass **without** `--update-goldens` (byte-identical);
   the new non-U-M golden passes.
3. `./run-tests -m render` → green **with `link-name` removed** from `_AXE_ALLOWLIST` (P9 enforced).
4. `./run-tests` (full, incl. `slow`) → green. `live` tier is manual (needs Terminus auth +
   network); run the P3/P4-relevant live cases if credentials are present, else note as skipped.
5. Targeted reproductions pass: zero-traffic run renders instead of `IndexError` (P10); malformed
   terminus response raises `TerminusError` not `TypeError` (P3); `NXDOMAIN` vs `Timeout` produce
   distinct notices (P4); config-inline `[News.<x>]` appears (P2).
6. No linter step (per decision).

## Documentation updates

- **`sample-pantheon-sitehealth-emails.toml`** — add documented `[Email]` and `[SMTP]` sections with
  institution-neutral example values + comments (this is the template other institutions copy).
- **`README.md`** — document `[Email]`/`[SMTP]` config; note `terminus()` now returns
  `(result, errors, fatal)` and raises `TerminusError`; note DNS failures now surface as report
  notices. Update the TODO list (mark "terminus() → return tuple" / "better error handling" done).
- **`CLAUDE.md`** — update the `terminus()` description (3-tuple + `TerminusError`); note
  `sc.add_notice()` is now the canonical notice path; note new `[Email]`/`[SMTP]` config; update the
  "reusable (non-UMich) path had latent bugs" and Testing paragraphs (now **three** goldens: WP,
  Drupal, non-U-M); list the new extracted helpers (`load_news_items`, `classify_hostname_dns`,
  `build_plan_over_time`).
- **`docs/`** — new end-user page: configuring sender identity / SMTP for a non-U-M deployment
  (`[Email]`/`[SMTP]` keys, what each controls). End-user instructions only — no internals.
- **`development/2026-07-04-test-suite/PROBLEMS-DISCOVERED.md`** — mark P1–P4, P6–P10 fixed (with
  the resolving commit/section) and P5 explicitly deferred.

## Implementation order (golden-neutral first; golden-sensitive isolated + verified)

1. **Cosmetic** — P6 docstrings/annotations, P7 comment, `wp()` docstring content. Run `--fast`.
2. **P2** — extract `load_news_items()` + fix loop + unit test. Goldens unchanged (no inline news in
   `minimal.toml`). Verify.
3. **P10** — extract `build_plan_over_time()` + empty-guard + notice + tests. Verify goldens.
4. **P3** — `TerminusError` + tuple contract + update 10 call sites + rewrite the 3 contract-pinning
   test files (`test_regressions.py`, `test_terminus_seam.py`, `test_live_smoke.py`) + add
   `test_terminus_contract.py`. Verify.
5. **`add_notice` API adaptation** (signature usable pre-`site_context` / in builders), no behavior
   change yet.
6. **P4** — `classify_hostname_dns()` + diagnostic notices via `add_notice` (aggregated `not_in_dns`
   notice kept) + tests. Verify.
7. **`add_notice` migration** — 25 live appends + 4 builders → `add_notice`, isolated commit, **both
   U-M goldens byte-identical**.
8. **`test_eml_headers.py`** — add the header-assertion guard FIRST (goldens have no `.eml` guard).
9. **P8a** — `[Email]`/`[SMTP]` config + defaults; verify via `test_eml_headers.py` + both goldens.
10. **P8b** — wrap fqdns-gated Cloudflare checks in the `[UMich].enabled` guard in-place; verify goldens.
11. **Non-U-M golden** — fixture + snapshot (`--update-goldens`, review diff; scoped assertion).
12. **P9** — reproduce via render tier, identify the flagged node, add alt/aria, drop `link-name`
    from allowlist, assert green.
13. **Docs** — sample TOML, README, CLAUDE.md, `docs/`, PROBLEMS-DISCOVERED.md.
14. **Full `./run-tests`**; capture output for acceptance.

## Verification (end-to-end)

- Drive both goldens through the offline shim pipeline (`rendered_report`,
  `rendered_report_drupal`) and confirm byte-identical `.html`/`.txt`; assert the `.eml` headers via
  `test_eml_headers.py` (no byte `.eml` golden — `Date:` is volatile).
- Run the new non-U-M golden and confirm it lacks the P8-removed strings (CF doc URLs + moved MIME
  headers); the template's hardcoded U-M branding is expected to remain (deferred).
- Reproduce each fixed defect with a targeted test (P2/P3/P4/P10 above) and confirm the pre-fix
  symptom is gone.
- `./run-tests --fast`, `-m render`, then full `./run-tests`; paste results into the final report.

## Adversarial review outcome

Round 1: independent reviewer (fresh context, code-verified) scored the draft **6/10 — NOT PASS**,
3 blocking + 5 non-blocking issues (non-U-M golden assertion impossible; P8b hook fires too early;
no `.eml` golden exists; P3 rewrite missed test files; dry-run domain hardcoded; builder-routing/count
unclear; P4 aggregation unstated; P9 hypothesis falsified). All resolved. Round 2 re-review verified
all 3 blockers genuinely fixed against the code and scored **8/10 — PASS**, no blockers remaining.

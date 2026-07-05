# Problems discovered while designing/implementing the test suite

Logged during the 2026-07-04 test-suite work (see `PROMPT.md` / `SPEC.md` in this folder). Per
the driving prompt, program bugs are **logged here and fixed in a later session**. P1 below was
originally believed to be a blocking bug; during implementation it was **disproven** (see its
corrected entry). P9/P10 were found while *running* the code during implementation.

Line numbers refer to the working revision (`pantheon-sitehealth-emails`). After the Part A
extraction the file shifted; treat line numbers as starting points and re-locate by symptom.

Most entries were found by **reading** the code; P9/P10 were **reproduced** during
implementation (render tier / live Drupal recording). The constraints still forbid
`--all` / `--for-real` / live `--create-tables` / live `--import-older-metrics`.

---

## P1 — NOT A BUG (disproven during implementation): the ≤4-month path already renders

**Original claim (design time).** That a site with ≤4 months of traffic would `NameError` on
`median_visitors` / `site_current_plan_index` / `site_recommended_plan_index` while building
`template_dict`, because those are assigned only inside `if len(v) > 4:`.

**Why it is wrong.** The design-time check missed the **earlier default initializers**:
- `median_visitors = 0`, `cost_same = {}`, `costs_median = {}`, `cost_table_rows = {}` are set
  **before** the `if len(v) > 4:` block (originally L3097–3100).
- `site_current_plan`, `site_recommended_plan`, `site_current_plan_index = 0`,
  `site_recommended_plan_index = 0` are all initialized right after plan resolution (L985–988).

So every variable `template_dict` consumes is defined for a ≤4-month site, and the "not enough
data yet" state renders fine.

**Confirmed empirically.** The offline e2e for `its-wws-test1` has only one in-window month (the
recorded metrics fall after the March report date), so it **already renders the ≤4-month state**
("needs 4 months more data", "Cost estimates will be available once the site has five months…").
`tests/e2e/test_recommendation_e2e.py::test_new_site_shows_not_enough_data` pins this. No code
fix was made (there was nothing to fix); the "fix blocking bug now" decision is moot.

**Coverage note.** Because the offline golden only ever hits the ≤4-month state, the extracted
`plan_costs` cost model is exercised end-to-end by a dedicated e2e that seeds >4 in-window months
(`test_recommendation_e2e.py::test_recommendation_path_exercises_plan_costs`) plus the
`plan_costs` unit/property tests.

---

## P2 — Config-defined `[News]` items are never added (dead loop)

**Symptom.** News items written inline in the config file's `[News]` table never appear in
reports. Only news loaded from `*.toml` files in `[News].folder` works.

**Root cause (L863–870).**
```python
if "News" in sc.config:
    for news_item_name in sc.config["News"].keys():
        if not isinstance(news_item_name, dict):
            continue  # skip News configuration directives
        sc.add_news_item(sc.config["News"][news_item_name], ...)
```
`news_item_name` is a **dict key (a string)**, so `isinstance(news_item_name, dict)` is always
`False` and the `continue` always fires — the `add_news_item` call is unreachable. The guard was
presumably meant to test the *value* (`sc.config["News"][news_item_name]`) and skip scalar
directives like `folder`.

**Fix (later).** Iterate items and skip non-table values, e.g.
`for name, value in sc.config["News"].items(): if not isinstance(value, dict): continue`. Confirm
the `folder` key (a string) is correctly skipped and only `[News.<x>]` sub-tables are added.

**Test coverage now.** A strict-`xfail` unit/integration test documents the intended behavior
(config-inline news item shows up) and will flip to passing when fixed. The file-based news path
is tested normally.

---

## P3 — `terminus()` swallows `errors`/`fatal` and returns `""` on JSON-decode failure

**Root cause (L338–353).** `terminus()` returns **only `result`** (the `return result, errors, fatal`
line is commented at L352). On a `json.JSONDecodeError` it sets `result = ""` (L343, self-marked
`# TODO: set to None`) and continues. For non-session errors it prints `Terminus error: …`
(L346) but neither raises, exits, nor signals the caller.

**Consequences.**
- Callers index directly into the result: `terminus("plan:info", …)["sku"]` (~L972),
  `terminus(...)["timeseries"]` (~L490/L1081/L1095). When `result == ""`, `""["sku"]` raises
  `TypeError: string indices must be integers` — a crash far from the real cause (a malformed
  Terminus response), with the original stderr already discarded.
- Empty-but-valid decode (`result == {}` / `[]`) silently produces zero rows with no signal.

**Fix (later).** Adopt the TODO: return `(result, errors, fatal)` (and `None`, not `""`, on
decode failure); update call sites to check `fatal` / `None`. This is entangled with the broader
"`terminus()` → return tuple" item already in the README TODO list.

**Test coverage now.** Integration tests around the `run_terminus` seam pin the *current* return
contract (single value) and the session-expiry retry; a strict-`xfail` documents the desired
`(result, errors, fatal)` contract so the later change is guarded.

---

## P4 — DNS resolution failures are console-only and conflated with "not in DNS"

**Root cause (L1252–1259 for A, L1282–1289 for AAAA).** `NoAnswer` / `NXDOMAIN` /
`NoNameservers` / `Timeout` are each caught and only `sc.console.print(...)`ed. Control then falls
through; `dns_points_at_cloudflare` / `dns_points_elsewhere` remain 0, so L1291 emits
`ATTENTION: {hostname} is not in DNS` — i.e. a **transient resolver timeout is reported
identically to a genuinely-unregistered hostname**, and neither becomes a structured
`site_context` notice (only console output). Observability gap: the report can't distinguish
"DNS is broken right now" from "this domain doesn't exist."

**Fix (later).** Distinguish transient (`Timeout` / `NoNameservers`) from definitive
(`NXDOMAIN` / `NoAnswer`) outcomes; surface at least the definitive ones as a report notice via
`sc.add_notice(...)` rather than console-only.

**Test coverage now.** Not directly tested this round (DNS is stubbed out in offline e2e via
`fqdns.json = {}` and platform-only `domain:list`). Logged for the later observability pass.

---

## P5 — `emails_sent` counter is dead; `--all` summary line is misleading

**Root cause (L3658, L3676).** `emails_sent += 1` is commented out (SMTP send is disabled), so
the counter is never incremented. The only reader is L3676 `f"Email sent for {emails_sent} of
{site_count} sites."`, inside the `if sc.options.all:` branch.

**Consequences.**
- The summary always says "Email sent for 0 of N sites" even after a successful dry run.
- If `emails_sent` is not initialized before the loop, L3676 would `NameError` under `--all`
  (needs confirmation — this path is **out of test scope** because `--all` is forbidden).

**Fix (later, together with SMTP re-enable).** Restore the increment when send is re-enabled and
initialize `emails_sent = 0` before the loop; make the dry-run summary count intended-recipients
rather than sent.

**Test coverage now.** None (lives behind `--all`, which is never run). Logged only.

---

## P6 — Stale docstring return signatures on Terminus wrappers

**Root cause.** `wp()` (L356), `wp_eval()` (L370), and `drush()` (L427) are annotated/documented
as returning 2-tuples (`-> (Any, str)` / `-> (str, str)`) but actually return **3-tuples**
`(result, errors, fatal)`; call sites unpack three (e.g. `ocp_config, errors, fatal = wp_eval(...)`
~L1685). Cosmetic/maintainability, not a runtime bug, but misleads readers and future callers.

**Fix (later).** Correct the annotations/docstrings to the real 3-tuple contract.

**Test coverage now.** Integration `test_wrappers.py` asserts the *actual* 3-tuple shape, which
documents the truth regardless of the stale annotations.

---

## P7 — Misleading comment references a non-existent option

**Root cause (L3666).** `plt.close(fig)  # needed to free up memory when sc.options.all_sites is
True`. The parsed option is `all` (`--all/-a`), not `all_sites`; `sc.options.all_sites` does not
exist. Comment-only; no runtime effect.

**Fix (later).** Correct the comment to `sc.options.all`.

---

## P8 — Institution-specific (U-M) logic in the core script not behind `[UMich].enabled`

**Not a bug for U-M runs**, but a **reusability defect**: for any non-U-M deployment these paths
either hardcode U-M specifics or risk `KeyError`. Two in-code comments (≈L3410–3411, L3494–3497)
already document that previous `if True:` blocks here crashed non-U-M runs with
`KeyError('UMich')` and were retrofitted with a guard — evidence the guarding is incomplete.

Catalogue (re-verify lines at fix time) of U-M specifics **not** behind the
`"UMich" in sc.config and sc.config["UMich"]["enabled"]` guard:
- `smtp_login()` — hardcoded `smtp.mail.umich.edu:465` + `SMTP_PASSWORD` (L771).
- `umich-cloudflare` cache check + `documentation.its.umich.edu/node/5114` (L1569–1577), gated
  only by `len(fqdns_behind_cloudflare) > 0`.
- `umich-oidc-login` reinstall special-case (semver, GitHub release URLs, U-M shortcode text)
  inside the generic plugins loop (L1595–1650).
- Drupal user-agent check → `documentation.its.umich.edu/node/4242`, `ifconfig.me/ua`
  (L2093, L2137–2150).
- Support-URL notice strings `its.umich.edu/computing/web-mobile/pantheon/support`
  (L1014, L1024) and Cloudflare "at U-M" doc URLs (L1429–1471).
- `make_msgid(domain="webservices.umich.edu")` — unconditional (L3533–3534).
- MIME headers unconditional (L3607–3617): `From: … <webmaster@umich.edu>`, dry-run `To:` /
  `Bcc:` `@umich.edu` / `@go.mail.umich.edu`, `Reply-to: webmaster@umich.edu`.
- Hardcoded site-name special cases `lsa-disko-project`, `umma-inside-wp` (L3390–3392) — inside
  the guard, but still string-literal site names.

**Fix (later — this is the planned "move institution logic into plugins/config" stage).** Move
each behind `[UMich].enabled` and/or into the `umich` plugin/check packages, or drive from config
(`[Email].from`, `[Email].reply_to`, doc-URL map, `make_msgid` domain). Add non-U-M-config e2e
coverage once guarded.

**Test coverage now.** Not fixed this round. The offline e2e runs *with* U-M behavior baked in
(the golden reflects it), so these paths are exercised but not proven reusable. A future
non-U-M-config golden would prove the guarding.

---

## P9 — Report HTML has links without discernible text (WCAG "link-name"), reproduced

**Found by** the render tier's axe-core accessibility smoke (`tests/render/test_render.py`),
which flags one **serious** violation, `link-name` ("Ensure links have discernible text"), on
**both** the WordPress and Drupal reports. This is a real WCAG 2 A / Section 508 issue: at least
one anchor in `email_template.html` (and/or a runtime-injected section such as the SiteLens
gauges) wraps only a non-text element without an accessible name (empty/again-missing `alt`, or
an icon-only link).

**Status.** Allowlisted in the render test (`_AXE_ALLOWLIST` includes `link-name`) with an
explicit comment, so the a11y smoke still fails on *new* serious/critical issues while
acknowledging this pre-existing debt. **Fix later** by giving every anchor discernible text
(link text or a non-empty `img alt` / `aria-label`), then remove `link-name` from the allowlist.

**Verify at fix time.** `./run-tests -m render` passes after removing `link-name` from
`_AXE_ALLOWLIST`.

---

## P10 — `IndexError` when a site has zero traffic history

**Symptom (reproduced).** Running the report for a site with **no** `pantheon_traffic` rows
crashes: `main()` does `days = sorted(plan_on_day.keys())` then `plan = plan_on_day[days[0]]`
(around L2678 post-refactor). With no traffic, `plan_on_day` is empty and `days[0]` raises
`IndexError: list index out of range`.

**How it surfaced.** Recording Drupal fixtures against `its-wws-test2` (a fresh site with no
live traffic) crashed here until the recording flow was changed to **seed a month of traffic
before the live run** (`tests/tools/record.py`). The harness already sidesteps this in the
offline e2e by seeding traffic (see the `seed_traffic` note in `conftest.py`).

**Fix later.** Guard the aggregation: if `plan_on_day` is empty, emit a notice / skip the plan
sections gracefully rather than indexing `days[0]`. This is the same class of "a genuinely new
site" robustness gap as P1's (non-)issue, but here it is a real crash.

**Verify at fix time.** A site (or seeded DB) with zero in-window traffic renders a report (or a
clean "no traffic yet" message) instead of raising `IndexError`.

---

## Non-issues considered and dismissed
- `terminus()` retry list-mutation (L331–337) — previously a real crash on a `*args` tuple; the
  code now converts to a list first and is correct. Regression already exists in the harness.
- `check/umich/__init__.py` `sc.console('…')`-as-callable — already fixed; regression exists.

# SPEC — `find-platform-domains-dns`: give HTTP 429 its own escalating retry budget

**Status:** implemented 2026-09-10. PD#n citations refer to `/workspace/prompts/directives.md`
(the Spine).

**Amends:** `development/2026-07-28-platform-domain-util/SPEC.md` (util1) **§7.1**, the retry
policy for API calls, and the `Retry` column of that document's §7 rows **G5** and **G6**. §7.1's
original text is left in place with a superseded note, per the precedent set at
`development/2026-07-31-platform-domain-util3/SPEC.md` §5.4 (superseded by util4 R4).

**Written after implementation, deliberately recorded as such.** This inverts
`prompts/new-feature-standards.md`'s spec → plan → implement flow. The change is ~40 lines in one
method of a temporary utility, the design was settled in the session's second turn as a
recommendation, and the user approved it before any code was written. The **tests** were still
written first and measured red (§8). This document exists to amend the archive, not to pretend the
order was different — see `PROMPT.md`.

**Temporary, like its subject.** `find-platform-domains-dns` is deleted after Pantheon's CDN
migration (util1 SPEC §14). This amendment adds nothing to that checklist — §10.

---

## 1. Glossary

Terms specific to this change. Domain terms live in `/workspace/CONTEXT.md`.

- **Throttle** — an HTTP **429** response from the Pantheon API. Distinguished throughout from a
  **transport failure** (an `httpx.HTTPError`/`httpx.InvalidURL`) and from a **5xx**: a 429 is not
  a failure at all, it is the server stating that the client's *rate* is too high and that the
  same request will succeed later.
- **Budget** — the number of attempts one `ApiSession.get()` call may spend on one condition
  before raising `PantheonApiError`. Before this change there was **one** budget shared by all
  three conditions above.
- **Schedule** — the tuple `THROTTLE_SLEEPS`, giving the wait before each throttle retry. Its
  **length is the budget**: `len(THROTTLE_SLEEPS) + 1` attempts.
- **Indeterminate** — util1 §8's counter: a site, environment or domain that produced no CSV row
  and could not be established either way. The `indeterminate=N` figure in the summary line.

## 2. Normative language

- **MUST** — required; a violation is a defect.
- **MUST NOT / NEVER** — prohibited; same weight.
- **SHOULD** — required unless a reviewer accepts a written reason.
- **MAY** — genuinely optional.

---

## 3. The measurement

A full organization sweep, run 2026-09-10, pasted verbatim from the operator's terminal:

```
$ ./find-platform-domains-dns
site_name,site_env,custom_domain,dns_record,platform_domain
SKIPPED: vpcomm-mc-multisite-test: could not list environments: /sites/1eb1c700-c095-47cf-ad5b-84765e12397f/environments: HTTP 429
SKIPPED: umor-micde: could not list environments: /sites/529684b8-9ad8-46e2-a32a-c44d6c803141/environments: HTTP 429
SKIPPED: pres-ccrt: could not list environments: /sites/54dbc4ea-97bf-46da-97c8-ffc6dd246ea5/environments: HTTP 429
SKIPPED: seas-kwhyte: could not list environments: /sites/54ed47ce-9dd2-421a-9827-cbfecd82f9b8/environments: HTTP 429
umihpi,live,www.healthyagingpoll.org,www.healthyagingpoll.org,live-umihpi.pantheonsite.io
SKIPPED: dsa-sltechsolutions.live: could not list domains: /sites/82215af3-2e54-4f71-a720-6cf75b921614/environments/live/domains: HTTP 429
SKIPPED: engin-engineering-news: could not list environments: /sites/90fb8c75-f687-4e84-9253-8eeae6e00b14/environments: HTTP 429
sites=417 envs=1662 custom_domains=530 rows=1 indeterminate=6
```

Four facts read off it, each load-bearing for the design:

1. **Six sites and environments were lost to a rate limit**, in a run whose entire purpose is to
   not under-report. Five of the six are whole *sites* — the `environments` call is per site, so a
   throttle there costs every environment and every custom domain beneath it. That is the exact
   failure mode util1 §2.2 rejected resumability *in order to avoid* being invisible.
2. **The retry did not clear the condition.** Under the old policy each of these six had already
   been retried once, 2 seconds later, and got a second 429. A 2-second pause is not enough.
3. **The throttles are scattered through the sweep, not bunched at its start.** The sweep visits
   sites in ascending site-UUID order, and the six ids ascend across the whole range
   (`1eb1…`, `5296…`, `54db…`, `54ed…`, `8221…`, `90fb…`). So this is not one burst that
   exhausts a bucket once; it is a sustained request rate that tips the limiter repeatedly.
4. **The rate is high.** 417 sites + 1662 environments ≈ **2,100 API calls** over roughly 38
   minutes, issued back-to-back over one reused connection with no pacing. Six failures is a
   ~0.3% loss rate.

## 4. What the old policy was, and why it failed

util1 §7.1, verbatim:

> `ApiSession.get()` retries **once**, after a 2-second sleep, on: an `httpx.HTTPError`
> (timeout, connection failure, protocol error), HTTP `>= 500`, or HTTP `429`. It
> re-authenticates **once** on HTTP `401` and retries the request immediately (a re-auth does
> not consume the transport retry). Any other non-200, a second failure, or an undecodable JSON
> body raises the named `PantheonApiError`, which the caller turns into G4/G5/G6.

Two defects, both visible in §3:

**D1 — one retry, 2 seconds, is the wrong shape for a rate limit.** A transport failure and a 5xx
are *failures*: retrying immediately is reasonable and retrying more is usually pointless. A 429 is
a *rate statement*: it says nothing is broken and the call will succeed once the client slows
down. Treating the two identically means the one condition that is guaranteed to be transient gets
the least patient handling. The retry re-fired into the same limiter and burned the budget.

**D2 — the budgets were shared.** `transport_attempts` was incremented by the transport arm and by
the combined `429 or >= 500` arm alike, so a throttle followed by a connection reset **on the same
call** exhausted the budget on the second event, having actually retried each condition zero times.
Nothing in §3 proves this fired, and nothing would: it is silent, and PD#1 counts a failure that
can happen silently as a defect regardless.

---

## 5. Scope

### 5.1 In scope (exhaustive)

1. A dedicated, escalating retry budget for HTTP 429 in `ApiSession.get()`.
2. Separating that budget from the transport/5xx one.
3. Naming the `Retry-After` response header in the give-up message.
4. **The same budget on the authentication POST**, `ApiSession._authenticate()` — added after
   adversarial review, see §6 R6 and §5.3.
5. **A `-v` note before each throttle wait** — added with it, see R7.
6. Tests for all five, plus mutation evidence that each can go red.
7. This amendment, and the superseded note on util1 §7.1.

### 5.2 NOT in scope (exhaustive, with reasoning preserved so it is not re-litigated)

1. **Pacing the request rate** (a small sleep between every call). This attacks §3 fact 3 at its
   root, and is the correct next lever if this change proves insufficient. It is rejected *now*
   because it taxes all ~2,100 calls of every sweep to fix 6: at 0.1s it adds ~3.5 minutes to a
   38-minute run whether or not the limiter is anywhere near tipping, where a retry costs only
   when the program is actually being throttled. Lowest-impact was the explicit ask.
2. **Honoring `Retry-After` as the wait.** It is the principled fix and it is deliberately
   deferred, because **nobody has established that Pantheon sends the header**: no code in this
   repo reads it, and it is absent from the API docs. Guessing a parser (it has two wire forms,
   delta-seconds and an HTTP-date) for a header that may never arrive is speculative code (PD#3's
   shadow-path rule cuts the other way here — an untestable branch against an unobserved input).
   R3 instead makes the next throttled sweep *report* the header, which settles the question for
   one line of code and no parser.
3. **Retrying a non-429 authentication failure.** `_authenticate()` still does not retry a
   transport error or a 5xx on the auth POST, and never did (util1 G3 → exit 2). Only the 429
   arm is added. *Why the asymmetry:* a 429 is the condition this increment measured in
   production and the one guaranteed to clear by itself; extending the transport retry to the
   auth path is a separate change with no evidence behind it.
4. **Changing 5xx or transport handling.** Neither appears in §3. R2 keeps them byte-identical.
5. **The two Cloudflare siblings** (`find-platform-domains-cloudflare`,
   `apply-platform-domains-cloudflare`). They talk to a different API through a different SDK with
   its own retry handling; the three utilities share no transport code (CLAUDE.md records the
   three environment-pin copies as *already* divergent).
6. **The main program** (`psh/gateway.py`). It reaches Pantheon through `terminus`, not the API,
   and has no 429 path.
7. **An unbounded or configurable budget.** A fixed literal schedule is one line, has no config
   surface to document, and a temporary utility does not earn a knob.

### 5.3 Scope changed after review, on the record

§5.1 items 4 and 5 were **not** in the approved change. `/code-review high`, run against the
finished diff in the same session, found both; the user approved folding them in rather than
deferring them. They are recorded here rather than backdated into the original scope:

- **The authentication 429 (R6).** §8.1's shadow-path table had explicitly disposed of this as
  "unchanged and deliberately not covered", while §5.2 claimed to be an *exhaustive* list of what
  was out of scope and did not name it — an internal contradiction. The review then supplied the
  argument the disposition lacked: the outcome on the auth path is **worse**, not equal. A
  throttled GET costs one indeterminate; a throttled re-authentication raises
  `SessionExpiredError` → util1 G7a → **exit 2**, ending the sweep. Deferring a fix on the
  grounds that it had "never been observed" was weak, since neither had the GET throttle until
  the sweep that prompted this whole increment.
- **The silent stall (R7).** R5 as first written said the retry "stays silent", and justified it
  with util1 §8's `grep -c SKIPPED` ⇄ `indeterminate=N` reconciliation. That justification was
  **wrong**: `ApiSession._notify` is a `-v`-only seam that emits no `RETRY:` or `SKIPPED:` prefix,
  so it cannot affect that identity at all. The real question was PD#5, and the answer is that a
  14-second stall with nothing on stderr reads as a hang.

---

## 6. Design

**R1 — the schedule is the budget.**

```python
THROTTLE_SLEEPS = (2.0, 4.0, 8.0)   # the wait before each 429 retry; its LENGTH is the budget
```

A module-level tuple beside `RETRY_SLEEP`. The attempt count MUST be derived as
`len(THROTTLE_SLEEPS) + 1` wherever it is needed, never written as a second constant.
*Intent:* PD#11 and the same reasoning as `option_strings_taking_a_value` in `psh/lifecycle.py` —
a count that has one home cannot drift out of step with the schedule it counts. A tuple also gives
the test a per-entry seam (§8), which an arithmetic `RETRY_SLEEP * 2 ** n` form cannot.

**R2 — 429 gets its own arm and its own counter.** The combined
`if response.status_code == 429 or response.status_code >= 500:` branch MUST split in two. The
5xx arm keeps `transport_attempts`, `RETRY_SLEEP`, and its single retry, unchanged. The 429 arm
uses a separate `throttle_attempts`, which MUST NOT be incremented by any other condition, and
which no other condition may read.
*Intent:* D2. Two different conditions, two budgets, so neither can spend the other's.

**R3 — the give-up message names `Retry-After`, present or absent.** On budget exhaustion:

```
<path>: HTTP 429 after 4 attempts (Retry-After: 17)
<path>: HTTP 429 after 4 attempts (Retry-After: absent)
```

The literal string `absent` MUST be used when the header is missing — never an empty value after
the colon, which reads as "Pantheon sent an empty header" and answers the wrong question.
*Intent:* PD#5. This message is the only evidence a future sweep will carry about whether
honoring the header (§5.2 item 2) is even possible.

**R4 — the wait-out logic lives in a helper method.** `ApiSession._throttled(path, response,
attempts)` sleeps, or raises `PantheonApiError` when the budget is exhausted; `get()` calls it and
increments its own counter.
*Intent:* not a design flourish — adding a second branch to `get()` tripped ruff's `C901`
(11 > 10), and the gate is not negotiable. `_renew()` was split out of the same method for the
same reason, so this follows an existing local precedent rather than inventing a shape.

**R5 — nothing else changes.** No new exception type (a throttle that outlives its budget is
still a `PantheonApiError`, so G5/G6 route it exactly as before), no new exit code, no new stderr
**prefix**, and no change to the summary line. In particular the throttle retry MUST NOT emit
`RETRY:`: util1 §8's `grep -c SKIPPED` ⇄ `indeterminate=N` reconciliation depends on that prefix
being emitted by exactly one site in the program (`retrying()`, the ignored-cursor path), and this
is not it. **Amended after review:** as first written this requirement said the retry stays
*silent*, which overshot — see R7.

**R6 — the authentication POST gets the same budget** (added after review; §5.3). A 429 from
`POST /authorize/machine-token` MUST be retried on the `THROTTLE_SLEEPS` schedule, in both of
`_authenticate()`'s roles: the constructor's first authentication and `_renew()`'s mid-sweep
re-authentication. On exhaustion the error MUST carry **both** causes —
`could not authenticate to Pantheon: /authorize/machine-token: HTTP 429 after 4 attempts
(Retry-After: absent)`. *Intent:* util1 G3's contract is a message naming authentication as what
failed; an operator reading only `HTTP 429 after 4 attempts` would go looking at the machine
token. Non-429 auth failures are unchanged (§5.2 item 3). `_throttled` is defined **above**
`_authenticate` in the class body for this reason.

**R7 — each throttle wait is announced under `-v`** (added after review; §5.3):

```
rate limited (/sites/<id>/environments); waiting before retry 1 of 3
```

It MUST ride the existing `self._notify` seam — the `-v`-only one `_renew()` already uses — and
so carries no `RETRY:`/`SKIPPED:` prefix and cannot disturb R5's reconciliation. The wait
**duration** is deliberately not interpolated: it is a source constant an operator can read, and
formatting it would render the test spies (§8) as object reprs.
*Intent:* PD#5. Up to 14 seconds per throttled call with nothing on stderr at any verbosity is
indistinguishable from a hang, and under a sustained limiter that becomes the operator's whole
experience of the sweep.

### 6.1 Cost

Worst case per throttled call: 2 + 4 + 8 = **14 seconds**. Against §3's six throttles that is
≤84 seconds added to a ~38-minute sweep, and **zero** added to a sweep that is never throttled.

### 6.2 Expected effect, stated as a prediction and not as a result

This recovers a throttle that clears within ~14 seconds. It does **not** make the utility immune
to rate limiting: if Pantheon's limiter uses a window longer than that, sites will still be lost —
but the give-up message will then carry the `Retry-After` evidence needed to choose between
honoring the header and pacing the sweep (§5.2 items 1–2). Whether 4 attempts is enough is a
claim only the next live sweep can settle.

---

## 7. The amendment to util1 §7.1

§7.1 is replaced, for the purpose of describing implemented behavior, by:

> `ApiSession.get()` retries **once**, after a `RETRY_SLEEP` (2-second) sleep, on an
> `httpx.HTTPError`/`httpx.InvalidURL` (timeout, connection failure, protocol error, malformed
> URL) or HTTP `>= 500`. HTTP **429** is handled separately: it has its own independent budget of
> one retry per `THROTTLE_SLEEPS` entry — `(2.0, 4.0, 8.0)`, i.e. four attempts in total — waiting
> that long before each, because a rate limit is not a failure and a single 2-second pause does
> not clear it. Neither budget is consumed by the other. `get()` re-authenticates **once** on HTTP
> `401` and retries the request immediately (a re-auth consumes neither budget). Any other
> non-200, an exhausted budget, or an undecodable JSON body raises the named `PantheonApiError`,
> which the caller turns into G4/G5/G6. A budget-exhausted 429 additionally names the
> `Retry-After` header, or the literal `absent`.

The §7 table's `Retry` column changes only in that G4, G5 and G6's "1" now means "1, or per §7.1's
throttle schedule when the response was a 429". No row's `Operator sees`, `CSV row`,
`Counted indeterminate` or `Run continues` cell changes: an exhausted throttle budget is still a
`PantheonApiError`, still one `SKIPPED:` line, still one indeterminate, and the run still
continues.

The original §7.1 paragraph stays in place in that document as the historical record of what was
specified on 2026-07-28, with a superseded note pointing here.

---

## 8. Test plan, and the evidence it can go red

All four in `tests/unit/test_find_platform_domains_dns.py`, beside the existing `ApiSession`
tests, using that file's `make_session(fpd, handler)` MockTransport helper. **Written before the
implementation and measured red** (`AttributeError: … has no attribute 'THROTTLE_SLEEPS'`).

| Test | Pins |
|---|---|
| `test_429_is_retried` | renamed from `test_429_is_retried_like_a_5xx`, whose name is now false: one 429 then a 200 still succeeds in two calls |
| `test_429_escalates_then_raises_naming_retry_after` | the attempt **count** (4), that every schedule entry is consumed exactly once and **in ascending order**, and that the message names `Retry-After: 17` |
| `test_429_absent_retry_after_is_named_not_blank` | R3's `absent` literal |
| `test_a_429_does_not_consume_the_transport_retry` | R2: 429 → connect error → 200 succeeds in three calls |
| `test_a_throttled_authentication_is_retried_not_fatal` | R6: two 429s on the auth POST, then a 200 |
| `test_a_mid_sweep_reauthentication_survives_a_throttle` | R6 in the shape the review named: 401 → throttled re-auth → sweep continues on the new token |
| `test_an_unclearable_authentication_throttle_names_both_causes` | R6's message carries `could not authenticate` **and** the 429/`Retry-After` detail |
| `test_a_throttle_wait_is_announced_under_verbose` | R7: the exact `-v` notes, one per wait |

**No `time.sleep` is patched**, per util1 SPEC §9. The escalation test monkeypatches
`THROTTLE_SLEEPS` to a tuple of **one spy per entry**, each returning 0 from `__index__` so
nothing actually sleeps.

**The spy pins the order, not merely the count — and the first version of it did not.** As first
written this test used three `_RetrySleepSpy` instances (the existing class, reused rather than
re-invented) and asserted `[spy.times_slept for spy in spies] == [1, 1, 1]`. Adversarial review
(`/code-review high`, same session) found that assertion satisfied by **any** permutation touching
each entry once, because three counting spies are indistinguishable, and measured the hole:
mutating the wait to `THROTTLE_SLEEPS[len(THROTTLE_SLEEPS) - 1 - attempts]` — an **8/4/2
descending** backoff, the exact opposite of the escalation this change exists to provide — left
all four 429 tests green. The test now uses a local `_OrderedSleepSpy` that appends its own index
to a shared ledger, and asserts `slept == [0, 1, 2]`. Both the descending and the flat mutation are
measured red against the corrected instrument (§8 table below).

*Recorded rather than quietly fixed* because it is this repo's own recurring lesson (PD#14, and
the `instrument-must-prove-it-can-go-red` note): a test that names a property in its docstring but
does not assert it reads exactly like cover, and the SPEC section documenting it asserted the same
false claim.

**Mutation evidence (PD#14 — an instrument that has not been shown going red is a claim).** Three
mutations applied to the implemented code, each measured, each reverted:

| Mutation | Result |
|---|---|
| `time.sleep(THROTTLE_SLEEPS[0])` — flatten the escalation | `test_429_escalates…` FAILED |
| `time.sleep(THROTTLE_SLEEPS[len(THROTTLE_SLEEPS) - 1 - attempts])` — reverse it to 8/4/2 | `test_429_escalates…` FAILED (green before the instrument was corrected — see above) |
| fold 429 back into the shared `transport_attempts` arm | 3 of the 4 FAILED |
| drop `Retry-After` from the give-up message | 2 of the 4 FAILED |
| `_authenticate` breaks out of its loop unconditionally (R6 removed) | 3 FAILED |
| drop the `self._notify` call (R7 removed) | `test_a_throttle_wait_is_announced…` FAILED |
| `_authenticate` re-raises the throttle error unprefixed | `test_an_unclearable_authentication…` FAILED |

`test_429_is_retried` survives mutation 2 by design — a single 429 clears under either policy. It
is not the instrument for the split, and is not expected to be.

### 8.1 Shadow paths (PD#3)

| Input | Behavior |
|---|---|
| 429 on the very first call of a sweep | identical: the budget is per `get()` call, not per run |
| 429 during `POST /authorize/machine-token` | **covered** (R6, added after review — this row previously deferred it; see §5.3). Retried on the same schedule; on exhaustion, G3 at startup or G7a mid-sweep, with both causes named |
| A **non-429** failure of that POST | unchanged: no retry, G3/G7a → exit 2 (§5.2 item 3) |
| 429 then 401 then 200 | succeeds; the re-auth consumes neither budget (R2 + the pre-existing `reauthed` flag) |
| 429 on every attempt | `PantheonApiError` after 4 attempts → G5/G6 → one `SKIPPED:` line, one indeterminate, sweep continues → exit 1 |
| An empty `THROTTLE_SLEEPS` | the first 429 raises immediately. Not guarded: it is a source literal, not an input, and a guard against a value no caller can supply is the speculative error handling §5.2 item 6 rejects |

---

## 9. What MUST stay unchanged

1. **The 5xx and transport arms**, byte-for-byte. `test_500_is_retried_once_then_succeeds` and
   `test_500_twice_raises_named_error` MUST pass unmodified — they are the instrument for that.
2. **The exit taxonomy** (util1 §7): 0 / 1 / 2 / 130, unchanged.
3. **`RETRY:` is emitted by exactly one call site**, `retrying()`, for the ignored-cursor path
   only (util1 §8). The throttle retry emits no prefix at all — R7's note goes through the `-v`
   `notify` seam.
4. **The `SKIPPED:` ⇄ `indeterminate=N` reconciliation.**
5. **The CSV contract**: header row, five columns, one row per hit.

## 10. Deletion checklist delta

**None.** util1 SPEC §14 remains the checklist and is unchanged: no new file, no new
`pyproject.toml` entry, no new `ruff-check.sh` arm. `THROTTLE_SLEEPS` and `_throttled` live inside
the script that gets `git rm`'d. Per §14 item 5, this folder — like every `development/` folder —
stays.

## 11. Risks and residuals

| Risk | Disposition |
|---|---|
| 4 attempts is still not enough for Pantheon's actual limiter | Accepted, and instrumented: R3's `Retry-After` in the give-up message is how the next sweep tells us. §5.2 items 1–2 are the two follow-ups |
| A sustained throttle now costs 14s per affected call instead of 2s | Accepted. §6.1: ≤84s on the observed run, 0s when not throttled |
| The real fix is pacing, and this defers it | Stated openly in §5.2 item 1 rather than hidden. This is the lowest-impact change that addresses most cases, which is what was asked |
| `Retry-After` may never appear, leaving `absent` forever | That **is** the finding, and it is worth one line to establish |
| A throttled sweep now takes materially longer before failing, on both the GET and the auth path | Accepted, and now visible: R7 puts a `-v` note before every wait |
| Post-review additions (R6, R7) widened a change specified as minimal | Accepted deliberately, and recorded in §5.3 rather than backdated. Both are in the same method-pair as the original change; neither adds a file, a flag, a config key or an exit code |

## 12. Documentation deliverables

| Target | Change |
|---|---|
| `find-platform-domains-dns` | `ApiSession`'s class docstring states the two independent budgets; `_throttled`'s docstring carries the §3 measurement and the C901 rationale |
| `development/2026-07-28-platform-domain-util/SPEC.md` §7.1 | a superseded note pointing at this spec, following the util3 §5.4 precedent |
| `CLAUDE.md` | **none.** Its `find-platform-domains-dns` subsection documents the sweep's behavior, exit codes and the pagination trap; it has never described the retry policy, and a temporary utility's internal backoff schedule does not earn a line in the file that has to stay readable |
| this folder | `PROMPT.md`, `SPEC.md`, and — at session end via `/archive-session` — the scrubbed transcript and statistics |

## 13. Acceptance criteria

Measured 2026-09-10, after implementation:

```
$ ./run-tests --fast --llm
0 errors, 0 warnings, 0 informations
LLM_SUMMARY passed=1867 failed=0 error=0 skipped=3 xfailed=0 xpassed=0
```

(1863 before the post-review additions; 1867 after their four tests.) Both gates pass — ruff
(`select = ALL` minus the ignore list, merged pass) and pyright standard mode over
`[tool.pyright].include`'s four entries, which include this utility's `.py` symlink. The one
intermediate lint failure, `C901 get is too complex (11 > 10)`, is what produced R4.

The live criterion cannot be met in this session: **the next full organization sweep MUST show a
lower `indeterminate=` count than §3's 6**, and any surviving `HTTP 429 after 4 attempts` line MUST
be read for its `Retry-After` value before choosing between §5.2 items 1 and 2.

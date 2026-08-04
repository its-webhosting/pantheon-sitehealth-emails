# Fix pass 1 — `apply-platform-domains-cloudflare`, review findings 1 and 2

**Status: DONE.** Both findings fixed, test-first, mutation-verified. Commits `5e4b4fd` (finding 1)
and `3240466` (finding 2), both on `main`, not pushed. Findings 3–11 were not read and not touched.

No `--for-real` invocation was made and no live Cloudflare API call of any kind. The
`apply-platform-domains-cloudflare.py` symlink was not touched; only the extension-less real file
was edited. Nothing was imported from `psh/`, `check/`, `plugin/` or `script_context`, and nothing
was modularized.

---

## Finding 1 (CRITICAL) — exit 2 could lie after a committed write

### Diagnosis, confirmed independently

`apply_all`'s handler chain named four cases (`KeyboardInterrupt`; the transport tuple;
`VerifyError`; `ApplyError`). Anything else propagated with the entry still at its `not-attempted`
seed, so `changed_count()` saw 0 and `failure_code(state)` returned **2** — SPEC §8's "could not
complete, and **nothing in Cloudflare was changed**".

The review's framing is the load-bearing part and I adopted it: round 1's fix (one shared
`failure_code` for all three of `main()`'s failure arms) corrected **the reader of the tally and
left the writer blind**. A tally-derived guarantee needs both halves — every reader computing the
code from one place, *and* every exit path from the work loop writing an entry into the tally. A
shared helper answers only the first question.

I confirmed the reviewer's non-trigger note before writing anything: `record_key` does catch
`ValueError` from `ipaddress.ip_address()` on unparseable content, so no test claims that path.

### The design, and why this one

Two guards, because the two positions differ in what is knowable:

**1. `apply_entry` — the post-batch section, enclosed.** The `for attempt in (1, 2)` loop and the
`held = describe_keys(...)` line are now inside one `try`. `except ApplyError: raise` lets the two
deliberate `VerifyError`s through unchanged; `except Exception as e` converts anything else into a
`VerifyError` naming the original class. This is SPEC R6.3's own reasoning — *"the transport
failing is not evidence the batch did not commit"* — generalized from three enumerated classes to
everything, on the observation that what they share is **where** they were raised, not what class
they are. Enumerating classes is precisely what failed here twice.

`Exception`, deliberately **not** `BaseException`: a `KeyboardInterrupt` must keep reaching
`apply_all`'s own arm, which SPEC §9.3 pins to `unknown`. That is stated in the code comment, in
the amended SPEC, and it is why the existing interrupt tests are untouched.

The final mismatch `raise VerifyError(...)` sits **outside** the `try` (ruff TRY301): the mismatch
is the verification step's *result*, not an unexpected failure of it, and `held` — the last thing
in that block that can raise an SDK-shape error — is still inside.

**2. `apply_all` — a trailing catch-all that records before it re-raises.** It sets the in-flight
entry's outcome to `unknown`, writes the `<fqdn>  UNKNOWN -- …` result line, and **re-raises**, so
`main()`'s last line of defence still names the class on stderr (SPEC §8.3) — and the re-raise is
itself the stop, so R3.4's "attempt nothing further" needs no `return`.

`unknown` rather than `unverified` here because the batch call's own clauses re-raise unrecognised
exceptions untouched, so this arm genuinely cannot tell a request built badly (nothing sent) from a
response parsed badly (committed). `unknown` is the conservative label and its operator action
("inspect this FQDN by hand") is the safe one.

**The one exemption, and why it is not a hole.** `except InvariantError: raise` sits *above* the
catch-all and leaves the entry `not-attempted`. The only `InvariantError` `apply_entry` can raise is
`merge_body`'s, which runs *before* the batch call — `verify_records`' is post-batch and guard 1
converts it to `VerifyError` first, and `verdict_for`'s/`validate_entries`' are pass-1 and
unreachable from here (checked: the nine `raise InvariantError` sites in the file). For that one
class "nothing committed for this entry" is a **true** claim, and relabelling it `unknown` would
turn a truthful exit 2 into a false exit **3** — "Cloudflare was left partially changed" — which is
PD#1 in the other direction. This is also why the pre-existing
`test_a_mid_run_invariant_error_after_an_applied_entry_exits_three_not_two` keeps its
`b == "not-attempted"` assertion unweakened; the arm is mutation-proven load-bearing by it (M6).

I considered and rejected the reviewer's other named option (a "batch returned" flag `apply_entry`
hands the caller): it would have to be a mutable out-parameter, since `apply_entry` signals by
raising, and it buys nothing the enclosure does not — the enclosure *is* the flag, expressed as
control flow.

### Red first

Both new tests use a **one-entry** plan, as required, so no earlier `applied` can mask the
arithmetic, and both raise from *inside* the real `apply_entry` (via the fake client) rather than
instead of it, so something really committed:

```
>       assert code == 3
E       assert 2 == 3
tests/unit/test_apply_platform_domains_cloudflare.py:2598  (post-batch ValueError)

>       assert code == 3
E       assert 2 == 3
tests/unit/test_apply_platform_domains_cloudflare.py:2639  (ValueError from the batch call)
```

Failing on the exit code, with `len(client.batch_calls) == 1` already asserted and passing above
it — i.e. failing for exactly the reason the finding names, not for a fixture error.

---

## Finding 2 (IMPORTANT) — "stop at the first failure" unpinned for two of three arms

No production change: the behavior is correct, the *instrument* was missing. Both new tests drive a
three-entry plan failing on the **second** entry and assert on the fake client's **recorded batch
calls** that the third was never posted — plus the zone ids of the two calls made, since
`three_entry_doc()` gives each entry a distinct zone. Asserting outcome labels would not catch a
`continue`, which leaves later entries looking plausible.

These two tests pass the moment they are written, and that is structural, not a defect: a
regression guard for existing correct behavior cannot go red on unmutated code. Its red
demonstration is the mutation, so I ran that **before** the fix as well as after — see M3/M4 below,
first executed against unmodified HEAD (211 tests) exactly as the reviewer measured.

---

## Mutation results (PD#14)

Every mutation applied to the production file one at a time, each reverted from a byte-copy
immediately after. `git diff --stat apply-platform-domains-cloudflare` verified empty/expected
after each batch.

| # | Mutation | Result |
|---|---|---|
| M1 | `apply_entry`'s post-batch catch-all narrowed to `ZeroDivisionError` | **RED, 1 failed / 214 passed** — only `…after_the_batch_returned_is_unverified_never_exit_two` |
| M2 | `apply_all`'s catch-all narrowed to `ZeroDivisionError` | **RED, 1 failed / 214 passed** — only `…from_the_batch_call_itself_is_unknown_never_exit_two` |
| M3 | `apply_all` UNKNOWN arm `return` → `continue` | **RED, 1 failed / 214 passed** — only `…unknown_fate_on_the_second_entry_leaves_the_third_never_posted` |
| M4 | `apply_all` UNVERIFIED arm `return` → `continue` | **RED, 1 failed / 214 passed** — only `…unverified_entry_on_the_second_entry_leaves_the_third_never_posted` |
| M5 | `apply_all` FAILED arm `return` → `continue` (control) | **RED, 2 failed / 213 passed** — the two pre-existing tests only; proves the three arms are independent and my new tests are not accidentally covering it |
| M6 | `apply_all`'s `except InvariantError:` passthrough removed | **RED, 1 failed / 214 passed** — the pre-existing mid-run-InvariantError test; proves the exemption is load-bearing and covered |

Pre-fix run of M3/M4 against HEAD reproduced the reviewer's measurement exactly: both GREEN at
211 passed, with the mutated run's own output showing `applied 2 … unknown 1 … not attempted 0`
and a third zone POSTed.

Every mutation was reverted; the committed file is the fixed version.

---

## Verification

```
$ ./run-tests --fast
All checks passed!                       (ruff, campaign ratchet)
0 errors, 0 warnings, 0 informations     (pyright, standard mode)
========= 1693 passed, 3 skipped, 2 deselected, 15 warnings in 41.65s ==========
EXIT=0
```

1689 → **1693**, +4, exactly the number of tests added. 3 skipped and 2 deselected unchanged. Run
again after commit 1 alone (1691) and after commit 2 (1693), both green with both gates clean.

The suite is fully offline: every new test drives `main()` through `run_main`'s
`FakeCloudflareClient`, and this file's autouse `refuse_real_network` teardown guard would have
fired otherwise. The autouse `_restore_sigint_handler` fixture is untouched and none of the new
tests monkeypatch `apc.signal`, so no path leaves SIGINT at `SIG_IGN`.

---

## Documents amended

**`development/2026-08-03-platform-domain-util4/SPEC.md`**

- **R3.4.1** (new) — every one of pass 3's stop paths MUST have a three-entry test asserting on
  recorded batch calls that the later entry was never posted; records the measurement.
- **R6.3.1** (new) — the post-batch section MUST be enclosed and every non-`ApplyError` exception
  in it MUST become a `VerifyError` naming the original class; `Exception`, never `BaseException`.
- **R6.3.2** (new) — the batch call's own clauses stay open-ended, by contrast, and §9.1's
  writer-side rule is what records them.
- **§8.1** — the four-state table's `unknown` row now covers "failed in a way this script does not
  recognise and cannot place relative to the commit".
- **§9.1** — the `VerifyError` row extended; the "no exit path may report 2 once
  `changed_count > 0`" rule now states its **reader half and writer half** explicitly, with the
  reproduction and the exhaustive `InvariantError` exemption.
- **§9.3** — states that the interrupt rule holds at every stage inside `apply_entry`, which is
  why R6.3.1 catches `Exception` and not `BaseException`.

§12.2 needed no change: the outcome vocabulary is unchanged — this fix moves entries *between*
existing outcomes, it adds none.

**`/workspace/CLAUDE.md`** — the sentence the review falsified ("No failure path … may report `2`
once anything has actually changed; every one of them is routed through `changed_count()` first")
now states the reader/writer split that makes it true, names the measurement, names the
`InvariantError` exemption, and describes the `apply_entry` enclosure. A second paragraph records
that pass 3's four stop paths are each pinned by a three-entry test and why a one-entry fixture
cannot do it.

**Memory (PD#13)** — new entry `tally-needs-a-writer-and-a-reader.md`, linked from `MEMORY.md`,
generalizing the reader/writer rule beyond this script.

**Not committed:** `REVIEW-2026-08-04.md` is left untracked — it is the reviewer's artifact and
findings 3–11 belong to a separate pass.

---

## Spine directives applied

**PD#1 — Zero silent failures.** *"Every failure mode must be visible — to the system, the team,
and the user. A failure that can happen silently is a critical defect."* An exception class nobody
enumerated made a committed production DNS rewrite invisible to the exit code, the `mode:` line and
the run record simultaneously. It also governs the `InvariantError` exemption: relabelling a
provably untouched entry `unknown` would be the same defect pointed the other way.

**PD#2 — Every error has a name.** *"Never 'handle errors.' Name the specific exception class, what
triggers it, what catches it, what the operator/user sees, and whether it's tested."* Both new
handlers are catch-alls by deliberate design, so the naming moved into the message and the
comments: the wrapping `VerifyError` carries `type(e).__name__` and `str(e)`, the `apply_all` arm
re-raises so §8.3's `ERROR: unexpected <class>: <msg>` still fires, and each is pinned by an
assertion (`"ValueError" in out`, `"ERROR: unexpected ValueError:" in err`). Neither swallows.

**PD#3 — Data flows have shadow paths.** *"Every flow has a happy path plus three shadows: nil
input, empty/zero-length input, and upstream error. Trace all four for every new flow."* The
upstream-error shadow is the whole finding: the enumerated tuple covered the shadows somebody
listed, and the fix covers the shadow class itself — anything raised after the commit.

**PD#4 — Interactions have edge cases.** *"Map them: interrupted run (Ctrl-C mid-site), slow or
failing Terminus/WP/Drush/API/SMTP calls…"* This is why the enclosure catches `Exception` and not
`BaseException`: a Ctrl-C landing inside the verification retry must keep reaching `apply_all`'s
`unknown` arm per SPEC §9.3, not be relabelled `unverified`.

**PD#7 — Runs are not atomic.** *"A run can die partway… Plan for partial states: idempotent DB
writes, resumability (`--resume-from`), safe re-runs, and the `--for-real`/dry-run gate as the
primary blast-radius control."* Exit 3 vs 2 is exactly this script's partial-state signal, and
finding 2's two arms are the "attempt nothing further" half of it. The `--for-real` gate was not
weakened and no test invokes it against anything but the fake client.

**PD#8 — Diagrams/docstrings.** *"updating it is part of changing the flow it describes"*
(of a diagram in a comment or docstring; the sentence continues "a stale diagram is
worse than none" across the line break). `apply_entry`'s and
`apply_all`'s docstrings both enumerate their handler arms as normative prose; both were updated in
the same commit as the code, and `apply_all`'s now names the fourth stop and the exemption.

**PD#14 — Your instruments can lie.** *"A green check is a claim, not evidence, until it has been
shown capable of going red on the condition it guards."* Six mutations, table above, each reverted;
finding 2 exists only because two `return`s were green claims. The M5 control was run specifically
to prove my new tests are not accidentally covering the arm that was already pinned.

**Engineering Preferences — right-sized diff.** *"favor the smallest design diff that cleanly
expresses the change, but don't compress a necessary rewrite into a minimal alteration."* Two
guards and one exemption arm; no new exception classes, no new helpers, no signature changes, so
every existing test kept its assertions unweakened.

---

## Concerns

1. **`merge_body`'s `InvariantError` is the exemption's only justification, and it is documented
   unreachable** ("section 6 check 7 should already have made this fatal before pass 1 ever ran").
   If a future change adds a *second* pre-batch `InvariantError` raiser inside `apply_entry` that
   is genuinely reachable, the exemption still holds; but if one is ever added **after** the batch
   call outside the enclosure, it would silently inherit `not-attempted` and re-open Critical 1 for
   that one class. The enclosure makes that hard to do accidentally, and both the code comment and
   SPEC §9.1 state the invariant, but no test can assert "nobody added a post-batch raiser".
2. **`write_report` inside the new `apply_all` arm precedes the `raise`.** On a doomed stdout it
   raises `StartupError` and that becomes the propagating exception instead of the original. The
   outcome is already recorded by then, so the exit code stays honest (3 via `failure_code`), and
   this matches what the three pre-existing arms already do — but the original class would be named
   only as `__context__`. Pre-existing shape, not introduced here; flagged rather than changed.
3. **`--fast` only.** The live tier was not run, per the standing "never against real Cloudflare"
   constraint. The offline suite plus both gates are green.

# Analytics — cachecheck must-revalidate

_Your narrative: what went well, what to do differently, decisions worth remembering._

---

## Notes from the session (edit/replace freely — this file is yours)

**The ask was small; the bug was systemic.** The request was to fix one notice about
`must-revalidate`. The interview and reviews found the same underlying misconception —
*"these directives prevent Cloudflare from caching"* — baked into **five** places:

1. the `must-revalidate` notice text ("defeats caching"),
2. `proxy-revalidate` bucketed with the caching-hostile directives,
3. `cc-proxy-revalidate` in `_MISS_RETRY_BLOCKERS`, suppressing a diagnostic retry it had no
   business suppressing,
4. the `no-cache`/`private`/`no-store` notice ("prevents Cloudflare from caching") — found only
   by the post-implementation `/code-review`, one `elif` away from the code we had just spent
   three review rounds fixing,
5. the suppression rule keyed only on the header, not on `Cf-Cache-Status`.

**Reasoning from the RFC was not enough.** The first spec justified the new notice purely from
RFC 9111. The adversarial reviewer caught that Cloudflare is not an RFC-conformant shared cache by
default: with Origin Cache Control **disabled**, `must-revalidate` is *ignored and stale is
served*. The notice is only true because U-M's zones have OCC **enabled** (confirmed, and now
recorded in `SPEC.md`). Lesson: for owner-facing claims about cache directives, check Cloudflare's
OCC behavior table, not the RFC.

**...and the docs contradict themselves.** For `no-cache` with OCC on, the cache-control table
says *"Caches and always revalidates"* while the BYPASS page and Conditions table say
`cacheStatus=bypass`. The maintainer's instinct — describe the **consequence** (every request
reaches the origin: latency + billable Pantheon requests) rather than the mechanism — sidesteps
the ambiguity and is true under both readings. Worth remembering as a general technique for
owner-facing text.

**Adversarial review earned its keep, and its own critique landed.** Three rounds, scores 5 → 6 →
8. Round 2's verdict was the sharpest feedback of the session: *"the author fixed the instances
round 1 named instead of sweeping for the class."* Round 1 named one test table that would
`KeyError`; there were four. Two of them enumerate `notices._CONSOLE`, so they pick up any new
item field automatically. The plan would have left a red suite.

**The "flaky test" was a production bug.** `test_plaintext_indents_the_header_under_its_finding`
failed in isolation and passed in the full suite. The obvious fix — have `reset_sc` restore
`sc.text_maker` — would have made it fail *permanently*. Root cause: `sc.text_maker` was one
shared, stateful `HTML2Text`; `inline_links` (the flag html2text actually honors) flips
`True→False` during the first `handle()`, so **the first notice of every run was rendered in a
link style nobody configured**, and the reference counter then climbed across the whole run. The
test was the only thing that ever saw "call 1". General signal: *"passes only in the full suite"*
is the inverse of a normal leak, and points at production state, not test hygiene.

**Two of my recommendations were wrong, and were caught by doing rather than thinking.**
- I recommended inline plaintext links to fix the duplicate-`[1]` problem. Implementing it showed
  inline links either stop wrapping (252-char lines) or split URLs mid-string. Reference links
  were right all along; the duplicate labels are now an accepted, documented trade-off.
- A stray `** :` in the plaintext (from `</strong>:`) was caught only by *reading the rendered
  email*, not by any assertion.

## Open items

- **Finding #6 (deliberately unfixed):** left at the maintainer's request.
- `cc-must-revalidate` still co-occurs with `cf-status-uncacheable` in one edge case — accepted,
  noted in `SPEC.md`.
- The U-M documentation page (out of repo) still needs its `#cc-must-revalidate` anchor rewritten
  and `#cc-proxy-revalidate` retired/redirected, before the next `--for-real` run.

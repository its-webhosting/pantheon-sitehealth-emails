# Prompts used

The feature began from a single observation by the maintainer, and the design was settled
through interview rather than up-front spec. The prompts, in order:

## 1. The original request (brainstorming)

> I designed the Cloudflare cache check test for "must-invalidate" incorrectly. For **all pages
> and assets tested**, if `must-invalidate` is in the `Cache-Control` response header, a result
> item should be added saying `must-revalidate` has no effect unless the content is already
> stale, in which case it forces a check with the web server; if the web server doesn't respond,
> this directive results in the user getting an error message instead of getting a stale version
> of the page. (This new functionality should replace all of the existing `must-revalidate`
> test). Check what I say here and interview me if I've misstated anything or if the test or
> result item language could be better in any way.

The "check what I say / interview me" clause is what made this work: `must-invalidate` is not a
real Cache-Control directive (the maintainer meant `must-revalidate`), and the interview surfaced
three further instances of the same misconception that were never in the original ask.

## 2. Notice wording (supplied during the interview)

> This page's Cache-Control header contains must-revalidate. You should remove it since it has no
> effect until the page goes stale, and if Cloudflare can't reach your web server at that time,
> the visitors will get errors rather than a stale copy of the page.
>
> Do not mention freshness requirement since if there is one the site should purge the old copy
> (good) and/or use a shorter s-maxage (not good).

## 3. Planning

> This looks good. Use the superpowers:writing-plans skill to turn this into a plan in
> `development/2026-07-11-cachecheck-must-revalidate/`.

## 4. Adversarial review

> Follow the instructions in `prompts/adversarial-review.md` to perform an adversarial review on
> the plan/spec doc(s).

Three rounds. See `analytics.md` — this is where most of the value was created.

## 5. Implementation

> Use the superpowers:subagent-driven-development skill to implement everything per the plan/spec
> doc(s), adhering to everything in `prompts/implementation-standards.md`

## 6. Post-implementation review

`/code-review` (high effort), then:

> fix #1 and audit the other Cache-Control notices against the OCC table, but make it clear to
> owners that `no-cache` always results in Cloudflare contacting the origin server, which adds
> latency and also can count as a billable Pantheon request. (These things are also what happens
> if Cloudflare does not cache the request.) Challenge me on this if I'm incorrect. Then fix all
> the other findings, except #6 (leave #6 unfixed).

## 7. A separate bug found along the way

> fix the flaky test in reset_sc

Which turned out not to be a test problem at all. See `analytics.md`.

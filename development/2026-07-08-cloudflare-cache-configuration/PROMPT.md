# Task

Overall goal: Add a new check to the program to detect and warn website owners about Cloudflare cache configuration problems.

## Prerequisite (foundational) work

In order to be able to implement the new check (described in the "New check" section below), generalize the existing 2-phase system (setup/check is already a phase system) into an ordered list of named phases whose names describe the data guaranteed available at that point:

```
 setup            (global, once)         ← Cloudflare egress-IP / um_networks list check
 ── per site ──────────────────────────
 site_pre         (site_context created) ← today's existing `check` seam (SiteLens etc.)
 site_post_traffic
 site_post_dns    (domain:list + DNS class + proxied_fqdns ready)  ← Cloudflare cache check
 site_post_gather (WP/Drush/plan data ready)
 site_pre_render
```

Concretely:
- Replace the hardcoded sc.hooks = {'setup':[], 'check':[]} with an ordered phase registry; sc.invoke_hooks('site_post_dns', site_context) gets dropped in after the domain loop exits and custom_domains/primary_domain are computed, the other markers at their natural points. main() gains a handful of one-line invoke_hooks calls, nothing more.
- Introduce named ordered phases + one new site_post_dns phase; document the per-phase data contract. Small diff, immediately unblocks this check, and gives every future check a place to land.
- Keep "multiple hooks per check" (already supported) and use it here.
- Within a phase, the modules are ordered deterministically by module name (by filesystem path order, not in an order humans might expect).
- The real deliverable is the documented phase contract: for each phase, exactly what site_context / plugin_context keys are guaranteed populated. That contract is what every future check-mover codes against, and it's what makes the de-monolith safe.
- The site_post_dns hook should receive the already-computed custom_domains / fqdns_behind_cloudflare lists via site_context, and the check below should use them rather than re-deriving which FQDNs to test.

Register the Cloudflare check as: egress-IP/list test → setup; per-site caching tests → site_post_dns.

## New check

The long-term plan for the program is to move checks out of the main script and into modularized tests under the `./check` directory. Right now, this is just a proof of concept, with the `./check` directory containing only umich-specific checks for SiteLens URLs and scores. Feel free to improve the way the check system (directory, contents, API/contract/interfaces/seams, and other things) works **if and only if** it will help with the new check we're adding in this task **and** those improvements will also benefit other, future tasks that will be moved from the main script under `./check`.

Create a new directory under `./check` for Cloudflare checks.  Checks in this directory should only be run if Cloudflare is enabled in the program's configuration file.

For each check, make sure the console displays ephermerally (so it doesn't make the output excessively long) what check is being run and the significant high-level actions or steps that the check is performing, even when the program is not in verbose mode. At verbosity level 1, the messages should not be ephermeral, and verbosity level 3 should display full information necessary for debugging problems and failed tests (including the HTTP requests made, HTTP status codes, and all HTTP response headers).

This check will only check public websites / pages, skipping anything that requires authentication.

If it's not a problem, the new config settings for this check should be in a subsection under the `Cloudflare` section to differentiate the settings for cache configuration problems from general Cloudflare plugin configuration as well as from other Cloudflare checks that will be added in the future.

This check should:
1. **Only** if the `--allow-any-source-ip` command line option **is not** given (add it to the program) **and** running in the report path (including `--only-warn`, but not including `--update`, `--import-older-metrics`, or `--create-tables`), query the list of U-M IP addresses / CIDR ranges (cloudflare list name `um_networks`, add a config setting for this) in Cloudflare account `b6a4063d6fa89fba31cf8bf99540d7e5` (add a config setting for this), and if the IP address the program is running at does not fall under any of the list items (assume the list contains all allow-listed IPv4 and IPv6 addresses and ranges), exit with a fatal error. This query and test should only be done once per run, outside the site loop. This will necessitate listing all the lists in the account and then mapping the list name to a list ID before querying the list contents; use the `cloudflare` Python SDK for all this. To determine external IP address, use a GET request to https://1.1.1.1/cdn-cgi/trace (returns key=value lines, look for the line `ip=`), fall back to  https://ip-check-perf.radar.cloudflare.com/ (returns JSON with a field named `ip_address`) if necessary, fall back to https://ifconfig.me/ (returns just the IP address) if necessary, and if all three fail exit with a fatal error. NOTE: this query should be used for other, non-UMich institutions, too, but they will have to supply a Cloudflare account ID and a list name (creating a list, if they don't already have an appropriate one) in the configuration file.
2. Inside the site loop, for each **custom domain** (FQDN) the site has in its live environment that is in DNS, for which DNS points to Cloudflare, and for which there is a proxy record in Cloudflare (in `fqdns.json`):
    a. The steps below (and the steps they "call" by references to other parts in this document) should collect all results that are to be included in the report for the specific FQDN in a single array and add a single "Cloudflare caching" notice (level: warning) for each non-empty list of results.  These are separate from notices for other checks/tests the program already adds.  Notices generated by this check that are not FQDN-specific should remain as separate/standalone notices added by the check to the site report.
    b. All test result items should result in **immediate** output to the console as soon as they occur, regardless of verbosity level.  Use more concise, technical wording than you use in test result items and do not include links to documentation or other resources (only URLs for the page or static assset in question).  All other (non test result item) test/check warnings, errors, failures, and other negative results should also be logged to the console similarly.
    c. Request the main page (`/`) for that FQDN that the site has.
    d. Perform the page-specific caching tests below for the main page.
    e. From the main page content, identify any/all links (`a` element href attributes) that are relative or that are for the same FQDN. Exclude any links that are for other FQDNs, any protocol other than `https:`, any links that go to the main page (including to fragments/anchors on the main page), and links with paths starting with known authentication or API prefixes (including "/api/", "/wp-admin", "/wp-login", "/login", "/logout", "/user/login", "/account/", "/auth/", "/profile", ".authorize", "/token", "/userinfo", "/callback", "/end_session", "/register", "/signup").  Deduplicate the list, sort it lexicographically (to make a seeded RNG test run reproducible), then select up to three at random (it's OK if there are less than 3; if there are zero, then just skip sub-step (f) below.
    f. For each page selected in sub-step (e) above, request the page (be sure to use the FQDN that we're currently handling), perform the page-specifc caching tests below.
3. For a site, if multiple FQDNs have the same notice varying only in which URLs were tested, consolidate these into a single notice containing all the URLs tested for all the FQDNs.

For each page (steps 2c and 2f above),
* Do the "For each page or static asset requested" tests below.
* Identify any/all static assets references in the page HTML markup that are relative or for the FQDN that the page load used, including but not limited to ones referenced `script`, `link`, and `img` tags. Select at random from the list at up to one JavaScript asset, up to one CSS asset, and up to one image asset. Not all pages will have all types of assets.  For any asssets that were selected, do the "For each page or static asset requested" tests below.

For each page or static asset requested,
* Examine the response header `Cf-Cache-Status`.  If the header does not exist or the cache status is anything other than `HIT`, `MISS`, `EXPIRED`, `STALE`, `REVALIDATED`, or `UPDATING`, add an item to the result array. Include cache status and say that the site owner should investigate the problem in order to ensure their site is fully protected by Cloudflare and that they get the maximum cost savings and performance boosts from Cloudflare.  Cache statuses that should be flagged in result items include, but are not limited to, `NONE`, `UNKNOWN`, `DYNAMIC`, and `BYPASS`.
* Examine the response header `Cache-Control`.  Add an item to the result array if any of the following are true:
    * If the header doesn't exist, add a result item and skip the rest of the `Cache-Control` tests below.
    * Compute the cache time as the maximum of `max-age` and `s-maxage`.  If both are missing, recommend that the site owner configure their site to cache the page or static asset (specify which) for 31536000 seconds (1 year) and skip the rest of the `Cache-Control` tests below.
    * If the computed cache time is less than 3 days, recommend that the site owner configure their site to cache the page or static asset (specify which) for 31536000 seconds (1 year).
    * If `private`, `no-cache`, `proxy-revalidate`, or `no-store` are present in the header, recommend the site owner configure their site to remove these (in addition to other `Cache-Control` test results).
    * If `must-revalidate` is in the header,
        * if the page is the main page, this is OK (it is used to ensure emergency alerts are seen in a timely manner on the main page)
        * for any other page or asset, add a result item to recommend the site owner configure their site to remove it
* Examine the response header `Expires`, if one exists, **and** the `Cache-Control` header is either not present or contains neither `max-age` nor `s-maxage`, check the value and if the value is less than 3 days in the future, add an item to the result array recommending they add a `Cache-Control` header instead and configure their site to cache the page or static asset (specify which) for 31536000 seconds (1 year).
* If a `Set-Cookie` response header is present,
    * If `Cf-Cache-Status` is `BYPASS`, modify or replace the result item `Cf-Cache-Status` to explain that the cache status problem is due to a cookie being set and recommend the site not set cookies for public content since that will prevent the page/asset from being cached.
    * Otherwise, and add an item to the result array recommending the site not set cookies for public content since that will prevent the page/asset from being cached.

When making HTTP/HTTPS requests:
* Requests are made sequentially (no concurrency) within each proxied FQDN, with the proxied FQDNs also being tested sequentially. No rate limit, budget, or de-dup.
* Create a new configuration setting for the user agent string to send in all HTTP request headers made by this check to any Pantheon site; the default should be `pantheon-sitehealth-emails (Linux; UMich WWS 0.1) webmaster@umich.edu`. This will enable site owners to identify pantheon-sitehealth-email requests in their webserver log files.
* Do not send any cookies in the request.
* Use a 5 second timeout (add a config setting to control this). If a response is not received within that time, add an item to the test result and move on to the next request.
* Add a result item if the certificate is invalid.  Make the request anyway (insecurely) in these situations, and perform the checks on the response normally.
* If the request fails without an HTTP status code for any other reason (including but not limited to connection refused, connection reset by peer, DNS lookup faire, non-certificate-validity TLS handshake failures, ...), add an item to the test result and move on to the next request.
* If the response to the request has the response header `cf-mitigated: challenge`, regardless of HTTP status code, then the request encountered a Cloudflare challenge. Add a result item to the report, do not check anything else, and move on to the next request.
* If any request results in a redirect, accept http->https upgrades for the same URL, accept redirects (replace the initial URL with the new one and re-request a maximum of 5 times per original FQDN) that go to another page with the same FQDN component of the URL, but for everythying else, note it in the console output and move on to the next request (do not add a result item). All redirects to other FQDNs (even apex<->www) should stop further consideration for the originally requested URL and move on to the next request (do not add a result item).
* If a request results in an any other non-2xx status code, add a result item, do not check anything else, move on to the next request.
* When requesting pages and static assets, prefer a lightweight solution; avoid browser based testing (headless or otherwise) unless there is a clear need for that.

When logging response headers problems to the console or adding a result item, always include the URL and whether the request was for a page or static asset, and what specific test triggered the problem and what the problem is.

Also, for **all notices and result items** (response header problems or anything other type of problem), make them easy to understand by site owners who may not be very technical. Keep them fairly short (to avoid overwhelming site owners) and include links as appropriate to let the site owner find out more. Make sure each notice or result item is actionable: it should include a link to documentation that tells them how to fix the problem, or the shortest, most concise steps with supporting links if no suitable documentation exists.  Take full advantage of HTML for clarity and readability in presentation. Where possible, use fragments to link directly to the relevant part of pages/documentation. Documentation resources you can use in notices and result items includes:

* U-M specific documentation:
    * [Installing the umich-cloudflare plugin for WordPress](https://documentation.its.umich.edu/node/5114) (only use if the site is WordPress). This documentation requires login, so I've put a copy in `wordpress-plugin.html` in the prompt directory.
    * [Installing the Cloudflare Module for Drupal 10 or 11](https://documentation.its.umich.edu/node/4242) (only use if the site is Drupal). This documentation requires login, so I've put a copy in `drupal-module.html` in the prompt directory.
    * [Managing Cloudflare Caching](https://documentation.its.umich.edu/node/4241). This documentation requires login, so I've put a copy in `managing-caching.html` in the prompt directory.
    * [U-M Managed Cloudflare Cache Rules](https://documentation.its.umich.edu/node/5110). This documentation requires login, so I've put a copy in `cache-rules.html` in the prompt directory.
* Specific Pantheon documentation pages from the site https://docs.pantheon.io/
* Specific Cloudflare documentation pages from the site https://developers.cloudflare.com/
* MDN
* Wikipedia

When writing the code that produces the notice and result item language in this check, always select the most specific, useful documentation from the list above under the assumption that the notices and result items will be for umich sites (that is, the umich gated config is on). Include multiple links only as necessary to explain/clarify.  For "U-M specific documentation" only, you can and should suggest edits/additions to specific pages that will help site owners act on notices and result items.  You can also draft additional U-M specific documentation pages.  I will make any edits (including creating new pages) on the documentation.its.umich.edu website.  Because this will be additional manual work for me, only suggest making changes/additions to U-M specific documentation when it is more than a trivial benefit to site owners (makes things easier for them, saves them steps, avoids confusion, avoids other problems).

Then produce alternate, more generic versions of the language for each notice and result item in this check for use by non-umich institutions. For non-umich insitutions, you can borrow some content from the U-M specific documentation when it is useful to do so, but otherwise lean more heavily on documentation from Pantheon, Cloudflare, MDN, and Wikipedia. For non-umich institutions, do not make any assumptions about which specific WordPress plugin or Drupal module might be in use.

The program should never try to fetch any of the documentation resources to validate them; it should just provide appropriate links in its notices and result items language.

**IMPORTANT**: Never suggest in any notice or report item that the user disable or bypass caching for a page or asset, nor that they disable any caching rule or configuration for their site or zone in the Cloudflare dashboard.

For all notices added by this check (both standalone non-FQDN notices as well as per-FQDN ones), the CSV id/key should be `cloudflare-cache`.

Make sure all data fetched remotely is properly escaped (reuse escape_url and other existing HTML escaping rather than inventing new ones) and cannot be used in any sort of injection, particularly when added to a notice as notices are HTML that gets displayed as HTML for the site owner in reports.

Add a config setting `[Cloudflare.cachecheck].enabled` so an adopter can run the Cloudflare plugin without this specific check.

In tests:
* Seed the RNG deterministically to ensure reproducibility.
* The check must expose a single monkeypatchable HTTP function to stay offline-testable.

Prefer the `httpx` package for HTTP/HTTPS requests and `beautifulsoup4` for HTML/DOM parsing unless you have better recommendations.  Put all dependencies for this check in the pyproject.toml `cloudflare` extra, and use an import guard to provide a clear messasge if Cloudflare is enabled for the program but a dependency specific to this Cloudflare check is missing.

# Methodology

You are a senior software architect with 12 years of experience with Python command line tool development, using REST APIs, WebOps, and WordPress/Drupal website hosting.  Your experience and judgement enable you to produce better solutions and higher quality code than 99% of other developers.

You are not here to rubber-stamp this task or its plan. You are here to make them extraordinary, catch every landmine before it explodes, and ensure that when code gets written and ships, it ships at the highest possible standard.

Hold the current description in the "Task" section above as your baseline — make it bulletproof. But, separately, surface every expansion opportunity you see and present each one individually as an AskUserQuestion (as a part of step 4, below) so I can cherry-pick. Neutral recommendation posture — present the opportunity, state effort and risk, let me decide. Accepted expansions become part of the plan's scope for the remaining steps. Rejected ones go to "NOT in scope."

Take a deep breath and work through the task step by step:
1. Consider the fundamental requirements documented in the "Task" section above.
2. Gather any additional information necessary to gain a solid understanding of the current version of the software and create an implementation plan for the design.
3. **Independently verify load-bearing factual claims from the requirements, documentation, and code rather than trusting them.**
4. Interview me relentlessly and in detail using the AskUserQuestion tool until we reach a shared understanding.  Ask about technical implementation, expansion opportunities, edge cases, concerns, tradeoffs, gaps in the requirements, inconsistencies/contradictions in the requirements, and other potential problems/issues/oversights. Don't ask obvious questions, dig into the hard parts I might not have considered.
5. After the interview, ask me if there is anything else I want to add or modify before you come up with an implementation plan.
6. Using the requirements, information you gathered on your own, the results of the interview, and other factors you deem helpful, come up with at least three different approaches (solutions) that should accomplish the task.
7. Do any additional investigation, interviewing, and validation that is needed to properly evaluate each solution and compare it to the others.
8. Evaluate each solution against the criteria in the "Quality control" section below.
9. Select the best solution out of those you evaluated.
10. For the best solution, if any of the quality control scores are under 0.9, refine and improve the solution until each score is 0.9 or above.
11. Write the complete specfications for how to implement the resulting solution to the file SPEC.md (put it in the same directory as the file for this prompt), optimized for Claude Code to use it to implement the code when I'm ready for you to do that (don't implement the solution yet). I may hand-edit the file before asking you to implement the solution described in the specifications.  This file will also serve as a record for both Claude Code and humans for what was decided and why, but it will not be a primary source of documentation.  The file should include:
    * Per the "Test creation" section below, what tests should be written and exercised as a part of the implementation to ensure the functionality implemented in the stage is correct and doesn't break in the future. Include all types of tests that are appropriate for what the current stage implements (e2e, integration, support, unit, other) and what each one should test. The tests must **extend the existing harness and honor its hard safety constraints** -- do not invent a parallel testing approach.
    * Concrete, verifiable acceptance criteria that mark the implementation complete: the exact commands to run and the observable outcomes that mean "done". Also include a full test suite run via `./run-tests`.
    * Any updates that should be made to README.md or existing documentation in the repo as a part of implmentation
    * Any updates that should be made to CLAUDE.md as a result of what was implemented/changed. Keep CLAUDE.md focused on things that you can't easily learn by looking at the code, as well as anything that is necessary to prevent you from making mistakes during future sessions.
    * Any new documentation that should be created for end users in the `./docs` directory during implementation (do not document internal functioning of the program in docs/, only end-user instructions).
12. Before presenting the SPEC.md for approval, run an adverserial review as described in the "Adverserial review" section below.
13. Present the plan to me for approval.
14. Upon approval, perform the implementation as described in SPEC.md.


# Prime Directives
1. Zero silent failures. Every failure mode must be visible — to the system, to the team, to the user. If a failure can happen silently, that is a critical defect in the plan.
2. Every error has a name. Don't say "handle errors." Name the specific exception class, what triggers it, what catches it, what the user sees, and whether it's tested. Catch-all error handling (e.g., catch Exception, rescue StandardError, except Exception) is a code smell — call it out.
3. Data flows have shadow paths. Every data flow has a happy path and three shadow paths: nil input, empty/zero-length input, and upstream error. Trace all four for every new flow.
4. Interactions have edge cases. Every user-visible interaction has edge cases: user interrupts program, slow connection, stale state. Map them.
5. Observability is scope, not afterthought. New reports, alerts, and runbooks are first-class deliverables, not post-launch cleanup items.
6. Diagrams are mandatory. No non-trivial flow goes undiagrammed. ASCII art for every new data flow, state machine, processing pipeline, dependency graph, and decision tree.
7. Everything deferred must be written down. Vague intentions are lies.
8. Optimize for the 6-month future, not just today. If this plan solves today's problem but creates next quarter's nightmare, say so explicitly.
9. You have permission to say "scrap it and do this instead." If there's a fundamentally better approach, table the problematic part(s) of the original design, or even the whole original design. I'd rather hear it now.

# Engineering Preferences (use these to guide every recommendation)
* DRY is important — flag repetition aggressively.
* Well-tested code is non-negotiable; I'd rather have too many tests than too few.
* I want code that's "engineered enough" — not under-engineered (fragile, hacky) and not over-engineered (premature abstraction, unnecessary complexity).
* I err on the side of handling more edge cases, not fewer; thoughtfulness > speed.
* Bias toward explicit over clever.
* Right-sized diff: favor the smallest design diff that cleanly expresses the change ... but don't compress a necessary rewrite into a minimal alteration. If the existing foundation is broken, invoke prime directive #9 and say "scrap it and do this instead."
* Observability is not optional — new codepaths need logs, metrics, or traces.
* Security is not optional — new codepaths need threat modeling.
* Deployments are not atomic — plan for partial states, rollbacks, and feature flags.
* ASCII diagrams in code comments for complex designs — Models (state transitions), Services (pipelines), Controllers (request flow), Concerns (mixin behavior), Tests (non-obvious setup).
* Diagram maintenance is part of the change — stale diagrams are worse than none.

# Quality control

When evaluating a solution to compare it to other solutions, rate the solution using a scale of 0-1 on each of the following:
- Correctness
- Completeness
- Ability to implement
- Maintainability
- Clarity

If any score is below 0.9, refine your solution.

# Test creation

Design and include specifications for the appropriate tests to create for the change(s)
described above, following the existing harness in `tests/` (see `tests/README.md` and 
`development/2026-07-04-test-harness/SPEC.md`):

1. Pick the right tier(s) by what changed:
   - pure/in-process logic → `tests/unit/` (add a Hypothesis property test if the function is
     pure and has an invariant worth fuzzing);
   - anything going through `run_terminus`/WP/Drush, the DB, or a check hook → `tests/integration/`
     (monkeypatch `run_terminus`, use `temp_db`);
   - a change visible in the rendered report or the full pipeline → extend the `e2e` run and the
     `golden` snapshot; if it changes real Pantheon interaction, add/adjust a `live` case;
   - a rendering/CSS/template change → the `render` tier.
2. Reuse the existing fixtures (`psh`, `reset_sc`, `temp_db`, `program_runner`, `rendered_report`,
   `minimal_config`). Never invoke the program except via `run_program` (the `--all`/`--for-real`
   interlock), and never run `--create-tables` or `--import-older-metrics` against the live
   database.
3. If the change alters Pantheon responses the offline e2e depends on, refresh fixtures with
   `./run-tests --record` and review the diff. If it intentionally changes rendered output, run
   `./run-tests --update-goldens` and review the snapshot diff.
4. Run `./run-tests --fast` (and the relevant `live` cases) and confirm green. Show the output.

Keep any institution-specific logic behind config flags / the `umich` plugin+check packages so the
non-UMich path keeps working.


# Adversarial Review

**Step 1: Dispatch reviewer subagent**

Use the Agent tool to dispatch an independent reviewer. The reviewer has fresh context and cannot see the brainstorming conversation — only the document. This ensures genuine adversarial independence.

Prompt the subagent with:
- The file path of the document just written
- "Read this document and review it on 5 dimensions. For each dimension, note PASS or list specific issues with suggested fixes. At the end, output a quality score (1-10) across all dimensions."

**Dimensions:**
1. **Completeness** — Are all requirements addressed? Missing edge cases?
2. **Consistency** — Do parts of the document agree with each other? Contradictions?
3. **Clarity** — Could an engineer implement this without asking questions? Ambiguous language?
4. **Scope** — Does the document creep beyond the original problem? YAGNI violations?
5. **Feasibility** — Can this actually be built with the stated approach? Hidden complexity?

The subagent should return:
- A quality score (1-10)
- PASS if no issues, or a numbered list of issues with dimension, description, and fix

**Step 2: Fix and re-dispatch**

If the reviewer returns issues:
1. For each simple issue with an obvious and low-risk/low-impact solution, fix the in the document on disk (use Edit tool)
2. For other issues, interview me relentlessly and in detail using the AskUserQuestion tool until we reach a shared understanding on how to fix each issue.  Present multiple options for fixing the issue, ask about technical implementation, expansion opportunities, edge cases, concerns, tradeoffs, and other potential problems/issues/oversights. Don't ask obvious questions, dig into the hard parts I might not have considered.
3. Re-dispatch the reviewer subagent with the updated document
4. Maximum 3 iterations total

**Convergence guard:** If the reviewer returns the same issues on consecutive iterations (the fix didn't resolve them or the reviewer disagrees with the fix), stop the loop and persist those issues as "Reviewer Concerns" in the document rather than looping further.

If the subagent fails, times out, or is unavailable — skip the review loop entirely.  Tell me: "Spec review unavailable — presenting unreviewed doc." The document is already written to disk; the review is a quality bonus, not a gate.

**Step 3: Report**

After the loop completes (PASS, max iterations, or convergence guard):

1. Tell me the result:
   a. Summary: "Your doc survived N rounds of adversarial review. M issues caught and fixed.  Quality score: X/10."
   b. Show the full reviewer output.

2. If issues remain after max iterations or convergence, add a "## Reviewer Concerns" section to the document listing each unresolved issue.


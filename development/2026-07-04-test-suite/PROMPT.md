# Task

Implement appropriate tests to ensure everything in this repository functions properly both now and also as we do additional development in the future. We just created a test harness for the code which includes basic smoke tests to verify the harness' functionality, so now it is time to determine what tests to implement, how to implement the tests (which will run in the existing test harness), implement the tests, and then verify that both the tests and test coverage are correct. Seek to implement an appropriate level of test coverage from a pragmatic viewpoint; we are not concerned with 100% coverage for its own sake, and future development will not use Test Driven Development (after these inital tests are created, future tests will be developed at the same time features/code are implemented).

There are two constraints that apply both during design as well as during all test runs both now and in the future:
* **NEVER** run the program with the `--all` option that can take up to 6 hours.  Instead, test using the specific sites `its-wws-test1` (a test WordPress website), `its-wws-test2` (a test Drupal website), or a specific real site you choose out of the list of all sites (one way to get a list of all sites is by running `terminus org:site:list 23c7208e-5f2a-4388-9fc4-5c3a038ef8b9`
* **NEVER** run the program with the `--for-real` option since that can result in unexpected emails being sent to real customers, which will confuse them and create support problems.
Adhere to these constraints even though doing so will result in gaps in the test coverage.

Right now, we're creating a test suite to cover the program's existing functionality.  It is important to have this test suite in place and know all the tests pass before we proceed to the next stages, below. That way, if one of the next stages introduces a problem or breaks something, the test suite can detect it early, when it is easiest to fix.  The next major stages -- later on -- will be:
  * We will re-enable the code that sends email via SMTP, and also add support for sending emails via the SendGrid API.
  * We will add several other new features.
  * We will refactor the program so the main script no longer contains most of the functionality.  The goal is to make the code more modular and easier to understand, modify, and maintain.
  * We will refactor the program to take the most advatage of the program's plugin framework and configuration framework, moving checks, capabilities (such as fetching secrets from AWS versus another source), and other funtionality into plugins wherever it is appropriate (but keeping things out of plugins if there's no advantage/reason). Similarly, we will modify all parts of the program to modify the program's configuration framework.

The stages above are not completely independent: for example, modularizing some or all of the program may be necessary in order to implement the test suite. You have permission to move some of the work from later stages into earlier ones, but only as necessary for the work being done at the time -- the goal is to avoid unneccessary changes that could break things ahead of getting a test suite running that can tell us both what already may be broken as well as what we break when we do the work in the later stages.

**DO NOT** do the following things yet, as we'll do them in a future session: Do not design or implement tests that use GMail, do not re-enable the commented-out SMTP code (leave SMTP disabled), do not design or implement tests for SMTP sending, do not design any GMail related tests.

We **do not** need or want 100% test coverage of the program code. There are some gaps in coverage that result from never running the program with the `--all` or `--for-real` options. Beyond that, ensure **appropriate** (not necessarily full) coverage. Test coverage should ensure that all meaningful and practical functionality is tested, without covering things that don't really need tests. We don't want to pursue / increase the coverage metric just for its own sake.

* Include the following types of tests.  For each type, consider the entire codebase and determine what tests of the type in question are needed to ensure current program functionality gets tested and validated, and that any breakage from future changes get detected.
  * Unit testing
  * Integration testing
  * End to end testing
  * Headless Browser testing

Performance testing is not important.

Headless browser testing should be used for loading the HTML version of the report into the browser to ensure the report HTML/CSS/JavaScript renders properly, looks good (no visual defects, no problems with report formatting), and complies with basic web standards (no unanticipated console errors).  In a **future session** (not now), we will add tests to the test suite for testing email sending functionality email sending functionality (no email errors received by the sending email account),and also making sure the email displays properly in GMail (no GMail-specific issues).

When writing individual tests, factor in the effort and cost of test maintenance and implement anything that will make the tests more robust and reduce maintenance costs as the program continues to receive changes and new features.

What other things beyond the requirements above would make the test suite for this program exceptional and awesome?  Propose enhancements/expansions to make the test suite as good as reasonably possible.

**IMPORTANT**: If you discover any problems with the existing code for the program itself, log the problems, any details you have about the problems, and things that need to be investigated before creating a plan to fix the problem to the file PROBLEMS-DISCOVERED.md in the same directory as the current prompt. We'll come back and fix problems with the program after we have finished implementing tests.  If you discover any problems with the test harness, fix those problems immediately and check to make sure that they problems are fully solved and do not affect any of the tests that run in the test harness.

**IMPORTANT**: do not implement the tests yet, just decide what tests to create, how to create them, and create a specification/plan per the steps below.


# Methodology

You are a senior software architect with 12 years of experience with Python command line tool development, using REST APIs, WebOps, and WordPress/Drupal website hosting.  Your experience and judgement enable you to produce better solutions and higher quality code than 99% of other developers.

You are not here to rubber-stamp this task or its plan. You are here to make them extraordinary, catch every landmine before it explodes, and ensure that when code gets written and ships, it ships at the highest possible standard.

Hold the current description in the "Task" section above as your baseline — make it bulletproof. But, separately, surface every expansion opportunity you see and present each one individually as an AskUserQuestion (as a part of step 4, below) so I can cherry-pick. Neutral recommendation posture — present the opportunity, state effort and risk, let me decide. Accepted expansions become part of the plan's scope for the remaining steps. Rejected ones go to "NOT in scope."

Take a deep breath and work through the task step by step:
1. Consider the fundamental requirements documented in the "Task" section above.
2. Gather any additional information necessary to gain a solid understanding of the current version of the software and create an implementation plan for the design. Look at the source code, the test harness specifiction in `development/2026-07-04-test-harness/SPEC.md`, test-related prompts in the `prompts` directory, and everything under the `tests` directory.
3. **Independently verify load-bearing factual claims from the requirements, documentation, and code rather than trusting them.**
4. Interview me relentlessly and in detail using the AskUserQuestion tool until we reach a shared understanding.  Ask about all questions in the "Task" sectino above, technical implementation, expansion opportunities, edge cases, concerns, tradeoffs, gaps in the requirements, inconsistencies/contradictions in the requirements, and other potential problems/issues/oversights. Don't ask obvious questions, dig into the hard parts I might not have considered.
5. Determine what tests to include in the test suite, per the requirements in the "Test" section.
6. For each test you include in the test suite, evaluate your proposed implementation for the test against the criteria in the "Quality control" section below.  If any of the quality control scores are under 0.9, refine and improve the solution until each score is 0.9 or above.
7. Write the complete specfications for how to implement all the tests for the test suite to the file SPEC.md (put it in the same directory as the file for this prompt), optimized for Claude Code to use it to implement the code when I'm ready for you to do that (don't implement the solution yet). I may hand-edit the file before asking you to implement the solution described in the specifications.  This file will also serve as a record for both Claude Code and humans for what was decided and why, but it will not be a primary source of documentation.  The file should include:
    * What tests should be written and exercised as a part of the test suite implementation. The tests must **use and extend the existing harness and honor its hard safety constraints** -- do not invent a parallel testing approach.
    * Concrete, verifiable acceptance criteria that mark the implementation for each test in the test suite complete: the exact commands to run and the observable outcomes that mean "done".
    * Any updates that should be made to README.md or existing documentation in the repo as a part of test suite implementation.
    * Any updates that should be made to CLAUDE.md as a result of what was implemented/changed. Keep CLAUDE.md focused on things that you can't easily learn by looking at the code, as well as anything that is necessary to prevent you from making mistakes during future sessions.
    * Any new documentation that should be created for end users in the `./docs` directory during implementation (do not document internal functioning of the program in docs/, only end-user instructions).
8. Before presenting the SPEC.md for approval, run an adverserial review as described in the "Adverserial review" section below.


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

When evaluating the proposed implementation of a new test in the test suite, rate the implementation using a scale of 0-1 on each of the following:
- Correctness
- Completeness
- Ability to implement
- Maintainability
- Clarity

If any score is below 0.9, refine your solution.

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
1. Fix each issue in the document on disk (use Edit tool)
2. Re-dispatch the reviewer subagent with the updated document
3. Maximum 3 iterations total

**Convergence guard:** If the reviewer returns the same issues on consecutive iterations (the fix didn't resolve them or the reviewer disagrees with the fix), stop the loop and persist those issues as "Reviewer Concerns" in the document rather than looping further.

If the subagent fails, times out, or is unavailable — skip the review loop entirely.  Tell me: "Spec review unavailable — presenting unreviewed doc." The document is already written to disk; the review is a quality bonus, not a gate.

**Step 3: Report**

After the loop completes (PASS, max iterations, or convergence guard):

1. Tell me the result:
   a. Summary: "Your doc survived N rounds of adversarial review. M issues caught and fixed.  Quality score: X/10."
   b. Show the full reviewer output.

2. If issues remain after max iterations or convergence, add a "## Reviewer Concerns" section to the document listing each unresolved issue.


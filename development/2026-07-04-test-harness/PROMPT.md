# Task

Work with me to design a test harness and test suite for the program in the current project repository.  The only deliverable right now is a plan that can be used to implement the test harness later.  Consider what specific tests the harness may need to run and how they will run, but do not design or implement any tests at this stage beyond smoke tests necessary to ensure proper functioning of the test harness. **The immediate intent is to ensure that all code works as designed and continues to work as designed even in the face of other, major planned future changes and the addition of new features.**

There are two constraints that apply both during design as well as during all test runs both now and in the future:
* **NEVER** run the program with the `--all` option that can take up to 6 hours.  Instead, test using the specific sites `its-wws-test1` (a test WordPress website), `its-wws-test2` (a test Drupal website), or a specific real site you choose out of the list of all sites (one way to get a list of all sites is by running `terminus org:site:list 23c7208e-5f2a-4388-9fc4-5c3a038ef8b9`
* **NEVER** run the program with the `--for-real` option since that can result in unexpected emails being sent to real customers, which will confuse them and create support problems.
Adhere to these constraints even though doing so will result in gaps in the test coverage.

This is a very large, complex task. **If** doing so is likely to produce better results, you can choose to break the task into multiple sub-tasks and complete each sub-task in a separate prompt and Claude session (you can still run sub-agents as needed without breaking the task into sub-tasks on disk). If you do this, keep all the files related to the sub-tasks in the same directory as this prompt file.  If you break the task into sub-tasks, number them and also create a `00-overview.md` index file that lists all the sub-tasks and is continuously updated to indicate the current state of each one together with cross-cutting conventions (so they do not need to be repeated in each sub-task description/specification file), dependencies between sub-tasks, and inter-sub-task handoff record: each subtask, on completion, records in the file the deviations from the overall design that occurred during the sub-task's execution, decisions the sub-task took, and follow-ups it left open; the next sub-tasks's discovery step consults that record together with the code itself.

Right now, we're designing (and, then, after review and approval, implementing) a test harness. The next major stages are:
  * Implement a test suite that covers all neccessary aspects of the program. It is important to have this test suite and know all the tests pass before we proceed to the next stages, below. That way, if one of the next stages introduces a problem or breaks something, the test suite can detect it early, when it is easiest to fix.
  * We will refactor the program so the main script no longer contains most of the functionality.  The goal is to make the code more modular and easier to understand, modify, and maintain.
  * We will refactor the program to take the most advatage of the program's plugin framework and configuration framework, moving checks, capabilities (such as fetching secrets from AWS versus another source), and other funtionality into plugins wherever it is appropriate (but keeping things out of plugins if there's no advantage/reason). Similarly, we will modify all parts of the program to modify the program's configuration framework.
  * We will re-enabled the code that sends email via SMTP, and also add support for sending emails via the SendGrid API.
These stages are not completely independent: for example, modularizing some or all of the program may be necessary in order to implement the test harness or the test suite. You have permission to move some of the work from later stages into earlier ones, but only as necessary for the work being done at the time -- the goal is to avoid unnecssary changes that could break things ahead of getting a test suite running that can tell us both what already may be broken as well as what we break when we do the work in the later stages.

Things to **not** change yet:
  * The code to send email via SMTP is temporarily disabled. Don't re-enable (uncomment) it yet.
  * There is a check to ensure that `fqdns.json` is less than 24 hours old, but this should not matter because you should never run the program with the `--all` option. We'll add funtionality to the program **later** to regenerate this file as needed.

Right now, our main focus is on tests for local development.  There currently is only one human working on this program, so CI/CD testing is not a priority, although we will want to add CI/CD testing next year.  Also, we are not doing releases of this program yet (but we will next year); the program is currently used only in-house by doing a `git clone` of the repository's `main` branch.

We **are not** going to utilize Test Driven Development.  Initially, tests will be added for the code that already exists.  After that, each Claude Code prompt (and.or the CLAUDE.md file) will include instructions for designing and implementing appropriate tests for each change at the time the change is designed and implemented.

We **do not** need or want 100% test coverage. In addition to the gaps in coverage that result from never running the program with the `--all` or `--for-real` options. After the test harness is planned/designed (now) and implemented (later), a separate project will be started to design and implement tests for the test harness to ensure **appropriate** (not necessarily full) coverage. Test coverage should ensure that all meaningful and practical functionality is tested, without covering things that don't really need tests. We don't want to pursue / increase the coverage metric just for its own sake. 

Test use cases for local development include:
  * Claude Code deciding which test(s) should be run to verify that a change made by Claude Code are functioning properly and that the change did not introduce new problems, skipping tests that are clearly not relevant.
    * The output of tests (both per-test as well as for runs of many tests) when run by Claude Code should be optimized for LLMs to understand and act on.  All useful information should be included in an easy-to-parse format without boilerplate or, fluff, or other extraneous output.
  * A human running all tests, all tests of a particular type, or all tests related to a command, module, or area of functionality.
    * The output of tests (both per-test as well as for runs of many tests) when run by humans should be easy for humans to read and clear/understandable.  Anticipate that humans will often copy and paste the output of a failing test into Claude Code and ask Claude Code to analyze/investigate the failure and fix the problem; therefore, the output for humans should also be friendly to LLMs.

What are the best practices for testing this sort of program? Make sure to take those into account in your test harness and test design.

* Include test harness support for:
  * Unit testing
  * Integration testing
  * End to end testing
  * Headless Browser testing

Performance testing is not important, although far-off future work will include doing checks for a single site in parallel where possible while ensuring we do not overload or abuse Pantheon's infrastructure/capacity.

Headless browser testing should be used for:
* Testing email sending functionality email sending functionality (via SMTP, once-uncommented in the future, and via SendGrid, once implemented). Right now, the emails are being sent to a GMail account. The email sending test should ensure the email gets received within a few minutes of being sent and also look for email error messages (unknown sender, undeliverable, rejected, ...) that appear in the same GMail account. Figure out how test harness authentication to GMail will work. We will also need to ensure that the sending and recipient identities for email testing are the same so the same email account that receives the emails also receives email errors.
* Ensuring that the reports emailed by the script render appropriately in the browser. There are two ways to test report rendering:
  * Have a browser load the report and all associated files from disk. This is a quick and good to ensure that the HTML, CSS, and JavaScript in the template comply with basic web standards and find and correct basic problems with report formatting.
  * Have the script send email and then use GMail to check to be sure the email displays correctly in GMail. This is much more time consuming and tricky. GMail allows only a subset of HTML, CSS, and JavaScript in email messages. GMail does not always implement/follow all web standards. GMail may display various messages that need to be handled before content (or full content) will display, such as for messages that appear to be dangerous, spam, contains remote content, or the display being truncated due to being too long.

If there are other types of testing that would be good (or best practice) to include, interview me about what they are, why they would be good, and whether to include them in the design.

Consider how to anticipate and optimize the effort and cost of test maintenance to ensure tests stay relevant and up-to-date as the program continues to receive changes and new features.

If it makes sense and the advantages are compelling, you can write prompts for yourself that are later run multiple times for various testing related tasks, whether it is keeping the harness up to date, implementing new tests, keeping tests up to date, or something else.  It's also OK to leverage testing frameworks/tools as needed that in turn make use of Claude Code, if the advantages are compelling.

What other test harness and test suite design elements, behaviors, features, and functionality beyond the requirements above would make the test harness/functionality for this program exceptional and awesome?

Propose design enhancements to make the test harness and test suite as good as reasonably possible.

What are the choices for test framework(s)?  Which framework(s) or other software should we use for the test harness and why should we use them in preference to the others?


**IMPORTANT**: do not implement the solution yet, just design it and create the specification/plan per the steps below.


# Steps to Perform (how to accomplish the task above) / Methodology

You are a senior software architect with 12 years of experience with Python command line tool development, using REST APIs, WebOps, and WordPress/Drupal website hosting.  Your experience and judgement enable you to produce better solutions and higher quality code than 99% of other developers.

You are not here to rubber-stamp this task or its plan. You are here to make them extraordinary, catch every landmine before it explodes, and ensure that when code gets written and ships, it ships at the highest possible standard.

Hold the current description in the "Task" section above as your baseline — make it bulletproof. But, separately, surface every expansion opportunity you see and present each one individually as an AskUserQuestion (as a part of step 4, below) so I can cherry-pick. Neutral recommendation posture — present the opportunity, state effort and risk, let me decide. Accepted expansions become part of the plan's scope for the remaining steps. Rejected ones go to "NOT in scope."

Take a deep breath and work through the task step by step:
1. Consider the fundamental requirements documented in the "Task" section above.
2. Gather any additional information necessary to gain a solid understanding of the current version of the software and create an implementation plan for the design.
3. **Independently verify load-bearing factual claims from the requirements, documentation, and code rather than trusting them.**
4. Interview me relentlessly and in detail using the AskUserQuestion tool until we reach a shared understanding.  Ask about technical implementation, expansion opportunities, edge cases, concerns, tradeoffs, gaps in the requirements, inconsistencies/contradictions in the requirements, and other potential problems/issues/oversights. Don't ask obvious questions, dig into the hard parts I might not have considered.
5. Using the requirements, information you gathered on your own, the results of the interview, and other factors you deem helpful, come up with at least three different approaches (solutions) that should accomplish the task.
6. Do any additional investigation, interviewing, and validation that is needed to properly evaluate each solution and compare it to the others.
7. Evaluate each solution against the criteria in the "Quality control" section below.
8. Select the best solution out of those you evaluated.
9. For the best solution, if any of the quality control scores are under 0.9, refine and improve the solution until each score is 0.9 or above.
10. Write the complete specfications for how to implement the resulting solution to the file SPEC.md (put it in the same directory as the file for this prompt), optimized for Claude Code to use it to implement the code when I'm ready for you to do that (don't implement the solution yet). I may hand-edit the file before asking you to implement the solution described in the specifications.  This file will also serve as a record for both Claude Code and humans for what was decided and why, but it will not be a primary source of documentation.  The file should include:
    * Concrete, verifiable acceptance criteria that mark the implementation complete: the exact commands to run and the observable outcomes that mean "done".
    * Any updates that should be made to README.md or existing documentation in the repo as a part of implmentation
    * Any updates that should be made to CLAUDE.md as a result of what was implemented/changed. Keep CLAUDE.md focused on things that you can't easily learn by looking at the code, as well as anything that is necessary to prevent you from making mistakes during future sessions.
    * Any new documentation that should be created for end users in the docs/ directory during implementation (do not document internal functioning of the program in docs/, only end-user instructions).
11. Before presenting the SPEC.md for approval, run an adverserial review as described in the "Adverserial review" section below.


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


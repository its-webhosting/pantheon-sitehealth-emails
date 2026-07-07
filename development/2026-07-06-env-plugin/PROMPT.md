# Task

The pantheon-sitehealth-email configuration file currently supports invoking a plugin to retrive the value for an AWS Secrets Manager secret.  Here is an example of how that plugin is used in the configuration file::

```
password = "<{secret aws webinfo db_pass}"
```

Create a new plugin, named `env`, that will make a configuration setting value available from the process environment.  For example, the following would set the configuration setting "password" to whatever the value of the environment variable "DATABASE_PASSWORD" is currently set to.

```
password = "<{secret env DATABASE_PASSWORD}"
```

There should be a second convenience method to invoke the same functionality that omits the first argument, `secret` but has the same result:

```
password = "<{env DATABASE_PASSWORD}"
```

Also change any code in the program itself (but not PyPI/vendor packages) that retrieves configuration information from the process environment variables directly to instead use configuration file settings, adding settings to the configuration files where needed for this.  That should include all of the following:

* Add a `[SMTP]` section to the configuraton file:
    * add settings to the configuration file that are already used by the current code:
        * `host` with the value `smtp.mail.umich.edu`
        * `port` with the value `465`
    * add a setting named `enabled` with the value `false`, and change existing code to use this
    * add a setting `password` with the value `<{secret env SMTP_PASSWORD}`, and change existing code to use this
    * add a setting `username` with the value `<{env USER}`, and change existing code to use this but keep it overridable via the `--smtp-username` command line option
* Add support to the script/plugins for using CLOUDFLARE_API_TOKEN (preferred, if present/configured) with the `cloudflare` package, falling back to CLOUDFLARE_API_KEY + CLOUDFLARE_EMAIL.
* In the `[Cloudflare]` section,
    * rename the `member_email` setting to `email` and set the value to `<{secret env CLOUDFLARE_EMAIL}`, changing existing code to use the new name
    * rename the `member_api_key` setting to `api_key`, and set the value to `<{secret env CLOUDFLARE_API_KEY}`, changing existing code to use the new name
    * add a commented-out setting named `api_token` that defaults to the value `<{secret env CLOUDFLARE_API_TOKEN}` when uncommented, to be used by the new support for CLOUDFLARE_API_TOKEN above.

For a configuration section that has an `enabled` setting with the value `false`, populate only the value for `enabled` in the processed configuration, skipping all other settings in that section. Otherwise (if there is no `enabled` setting in the section or if its value is anything other than `false`), handle the section's settings normally. For settings that are handled normally, if a setting's value attempts to reference an environment varaible that does not exist, exit immediately with a helpful error message.

Is it easy and reasonable to add an optional default last argument for the `env` plugin (both forms of the substitution)?  If so, propose 2-3 ways to do that (in this case, an reference to an environment variable that is unset would use the default rather than exiting with an error); if not, then mark this idea as "not in scope".

NOTE: I have re-enabled (uncommented) the previously commented out SMTP code. The script should send email (to just the test addresses unless the `--for-real` command line option is included) if SMTP is enabled and configured in the configuration file. Don't write tests for SMTP sending yet; we'll do that in a later session.  I have set the `SMTP_PASSWORD` environment variable to the script can run and send emails.

# Methodology

You are a senior software architect with 12 years of experience with Python command line tool development, using REST APIs, WebOps, and WordPress/Drupal website hosting.  Your experience and judgement enable you to produce better solutions and higher quality code than 99% of other developers.

You are not here to rubber-stamp this task or its plan. You are here to make them extraordinary, catch every landmine before it explodes, and ensure that when code gets written and ships, it ships at the highest possible standard.

Hold the current description in the "Task" section above as your baseline — make it bulletproof. But, separately, surface every expansion opportunity you see and present each one individually as an AskUserQuestion (as a part of step 4, below) so I can cherry-pick. Neutral recommendation posture — present the opportunity, state effort and risk, let me decide. Accepted expansions become part of the plan's scope for the remaining steps. Rejected ones go to "NOT in scope."

Take a deep breath and work through the task step by step:
1. Consider the fundamental requirements documented in the "Task" section above.
2. Gather any additional information necessary to gain a solid understanding of the current version of the software and create an implementation plan for the design.
3. **Independently verify load-bearing factual claims from the requirements, documentation, and code rather than trusting them.**
4. Interview me relentlessly and in detail using the AskUserQuestion tool until we reach a shared understanding.  Ask about technical implementation, expansion opportunities, edge cases, concerns, tradeoffs, gaps in the requirements, inconsistencies/contradictions in the requirements, and other potential problems/issues/oversights. Don't ask obvious questions, dig into the hard parts I might not have considered.
5. Come up with an implementation plan.  Evaluate the plan against the "Quality control" section below. If any of the quality control scores are under 0.9, refine and improve the plan until each score is 0.9 or above.
6. Write the complete specfications for for the implementation to the file SPEC.md (put it in the same directory as the file for this prompt), optimized for Claude Code to use it to implement the code when I'm ready for you to do that (don't implement the solution yet). I may hand-edit the file before asking you to implement the solution described in the specifications.  This file will also serve as a record for both Claude Code and humans for what was decided and why, but it will not be a primary source of documentation.  The file should include:
    * Per the "Test creation" section below, what tests should be written and exercised as a part of the implementation to ensure the functionality implemented in the stage is correct and doesn't break in the future. Include all types of tests that are appropriate for what the current stage implements (e2e, integration, support, unit, other) and what each one should test. The tests must **extend the existing harness and honor its hard safety constraints** -- do not invent a parallel testing approach.
    * Concrete, verifiable acceptance criteria that mark the implementation complete: the exact commands to run and the observable outcomes that mean "done". Also include a full test suite run via `./run-tests`.
    * Any updates that should be made to README.md or existing documentation in the repo as a part of implmentation
    * Any updates that should be made to CLAUDE.md as a result of what was implemented/changed. Keep CLAUDE.md focused on things that you can't easily learn by looking at the code, as well as anything that is necessary to prevent you from making mistakes during future sessions.
    * Any new documentation that should be created for end users in the `./docs` directory during implementation (do not document internal functioning of the program in docs/, only end-user instructions).
7. Before presenting the SPEC.md for approval, run an adverserial review as described in the "Adverserial review" section below.
8. Present the plan to me for approval.
9. Upon approval, perform the implementation as described in SPEC.md.


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


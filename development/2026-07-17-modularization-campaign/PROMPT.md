
Plan a campaign to modularize and refactor/clean-up/improve the 4,752 line long main script, `./pantheon-sitehealth-emails` with the intent of taking full advantage of the program's checks and plugin frameworks.

The campaign should break this work into several increments (separate pieces) focused around specific sub-areas of functionality (for example, WordPress plugin checks in one increment, Pantheon platform configuration checks in another increment, repeating until the main script has been fully modularized).  The purposes of breaking the work into increments is to have each increment be easier to plan, implement, and test; to make the entire campaign as well as each increment easier to manage and reason about; to ensure Claude session size/context/tokens/usage do not exceed plan limits; and to git commit each increment separately as checkpoints in case we need to inspect or revert to a prior checkpoint for any reason.

The campaign is one architectural program in N similar increments, not N unrelated features. Re-brainstorming the target architecture per increment **must not** happen since it re-derives the same boundaries N times and lets them drift.  Each Increment should get a spec that references the archtecture/design/decisions made for the overall camaign and does not re-derive them. Increments touch `main()` by construction, so each still gets the full implementation treatment — subagent-driven-development, `/code-review`, archive. What they do **not** repeat is the design scrutiny already performed and passed at the campaign level: the brainstorm and the adversarial review ran **once**, on the campaign, where an error is cheapest to fix and most expensive to miss. All increments inherit the campain design scrutiny.

Across all increments, campaign planning should include:
* What are the appropriate increments?
* How will work be coordinated across the entire capaign and between increments?
    * How and when will additional necessary/desireable tasks that are discovered during one increment be addressed?
    * How will an increment know what changes or deviations from the orignal plan happened in previous increments?
* What new checks (under the `check/` directory) should be created, and which increments should use them?
* What new plugins (under the `plugins/` directory) should be created, and which increments should use them?
* What new modules or packages should be created, and which increments should use them?
* What new program hooks/phases should be created for checks, plugins, and other code to use?
* Add producer/consumer dependencies and DAG ordering for all program hooks/phases. This will ensure that hooks/phases are not rigid and that future checks and plugins can be added wherever needed.  Create tests to ensure that changes made to the program now and in the future never make it impossible to create the DAG (no circular depenencies, mutually exclusive requirements, or conflicts).
* What new sections and items should be added to the configuration file?  Design these to be logical, organized, and make sense to the end user of the program.
* Introduce types/classes as needed for following best practices. Reuse existing types/classes already introduced where appropriate instead of creating new ones.
* What are module boundaries?
* What are the new seams?
* What new tests are needed?
* What stays in the main script, and why?
* What is the order of the increments, and why?

Every increment must do the following work:
* Necessary prep work (for example, read documents common to all campaigns)
* Get rid of house styles and adopt best practices.
* Modularize the code that falls within the scope of the increment.
* Switch to the new types/classes.
* Make full use of checks, plugins, and the configuration system.
* Add in-code comments and documentation per best practices.
* **VERIFY** all claims made in both existing and new comments/documentation -- **do not assume claims or facts are correct**.
* Update existing tests and create new tests: insure appropriate coverage, types of tests exist for everything affected by the increment.
* Update documentation and `README.md`.
* Update `CLAUDE.md` and other Claude memories.
* Carry forward any unexpected changes/deviations from the original plan, unresolved issues, and other necessary/desirable tasks to be addessed at the appropriate time (between increments, in a future increment, after the last increment when wrapping up the campaign, ...)
* **MUST PRESERVE**:
    * the four e2e goldens stay byte-identical
    * the per-phase data contract is honored
    * the non-UMich path keeps working
* A code review after the end of the full implementation of the increment.

In case it affects how you create the plan and specs, Opus 4.8 will be the agent used for all implementation work.

Issues that are identified during the planning of the campaign should be fixed in an appropriate increment or other phase of the campaign unless they are major/risky changes or would make the campaign overly broad and complicated, in which case they should be added to the to-do list in `README.md` to be researched/decided/fixed after the campaign is over.

Identify expansion opportunities that will make the program better in terms of implementation, functionality, or features. For each expansion opportunity, include your recommendation and reasoning and ask me if it should be included in the campaign, added to the to-do list in `README.md`, or declined.

My intent is to ultimately broaden the ruff and pyright configuration to include all best-practice rules, and fix all the issues those tools raise. Investigate and determine if there are any parts of this work that should be included in this campaign, and, if so, include them as appropriate. If it would be best for all or certain parts of broadening the ruff and pyright configuration to be done after the campaign is over, record the details in the to-do list in `README.md`.

My intent is to defer the replacement any `terminus` invocations with calls to the Pantheon API until after the campaign is completed. But, if it makes sense to do some or all of that work as a part of this campaign, ask me, including what you recommend and the reasons why.

What factors could cause problems that make the campaign, increments in general, or particular increments difficult to implement, require multiple rounds of testing and fixed, or extra/duplicate work? Come up with a plan to avoid/control these factors and make sure everything stays on track and that all implementation is done right the first time.

Focus on **excellence** in all aspects of this campaign planning and implementation.

Adhere to everything in `prompts/new-feature-standards.md`. Let's brainstorm this.


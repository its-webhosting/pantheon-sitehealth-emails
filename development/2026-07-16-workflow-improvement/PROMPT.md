# Task

In the next few days, I will be asking you to modularize the 4,752 line long main script, `./pantheon-sitehealth-emails` and create new checks, plugins, and modules/packages. I will likely break this work down into several smaller efforts focused around specific sub-areas of functionality (for example, WordPress plugin checks in one effort, Pantheon platform configuration checks in another effort, repeating until the main script has been fully modularized).

**BEFORE** starting that effort, I want to be sure that my Claude configuration and workflow are solid and accomplish my intended goals in terms of style, prime directives, engineering preferences, quality control, expansion/improvement opportunities, and overall excellence. I want to make my workflow easier and more automated, but only as a secondary objective to the other goals, and I want to remain in the loop at key junctures to be sure I am consulted on substantial/significant decisions and that everything proceeds in the overall direction I intend.

Please read and understand:
* all Claude plugins, skills, MCP servers and other add-ons, extensions, and configurations that are installed (repo and user level); and the documentation on how to use each of them
* my current workflow in the "Current workflow" section below
* all of the files in the `prompts/` directory
* `CLAUDE.md`, `docs/agents/*`, `development/README.md`, and any other relevant files

Propose changes that will make my use of Claude Code more effective, including:
* what tools (Claude plugins / skills / MCP servers / other software or pacakges) I have installed and how they are configured, including installing new tools
* what tools I should uninstall to avoid having tools installed that are unutilized or dramatically underutilized, especially tools that consume context with minimal to no benefit
* the files under `prompts/`
* my workflow (feel free to create something new from scratch if doing so will provide a substantial benefit)
* how the repo is structured, especially to resolve conflicts or tension between tools
* how to make more effective use of the final set of tools you recommend

State the reason(s) why you recommend each change and how to ensure each change results in the intended benefits.

Adhere to everything in `prompts/new-feature-standards.md`. Let's brainstorm this.

# Current workflow

```
development_dir="development/$(date +%Y%m%d)-PUT-NAME-OF-SESSION-HERE/"
mkdir -p "$development_dir"
codegraph sync
claude

  /clear
  /model opus
  /effort high

  I want to design a feature that does <DESCRIPTION_OF_FEATURE>. Here are the requirements and constraints I already know: <REQUIREMENT_X>, <CONSTRAINT_Y>. Adhere to everything in `prompts/new-feature-standards.md`. Let's brainstorm it.
  <WORK WITH CLAUDE>

  This looks good. Use the superpowers:writing-plans skill to turn this into a plan in the directory `./development/<YYYY-MM-DD-slug/`.
  <WORK WITH CLAUDE, THEN READ AND POSSIBLY MAKE FURTHER REVISIONS TO THE PLAN BY HAND>

  Follow the instructions in `prompts/adversarial-review.md` to perform an adversarial review on the plan/spec doc(s).
  <WORK WITH CLAUDE>

  Use the superpowers:subagent-driven-development skill to implement everything per the plan/spec doc(s), adhering to everything in `prompts/implementation-standards.md`
  <WORK WITH CLAUDE>

  /code-review high
  <WORK WITH CLAUDE>

  /context
  /usage   # (copy and paste the result into the session)
  /archive-session

  Commit everything directly to main.   # yes, I should be doing PRs, but I'm the only dev working on this, and Claude deliberately does not have write access to the repo

  /clear
  /exit
codegraph sync
```

Do the following 2-3 times per week:
```
/improve-codebase-architecture
@prompts/update-claude-md.md
```

# Prompt: update the CLAUDE.md file

For each thing in CLAUDE.md that describes the program functionality/implementation/behavior, check it against the actual code to verify that the description in CLAUDE.md is correct.  Update CLAUDE.md as necessary to fix any discrepencies, add information that should be included to help Claude Code perform better in future rules, and remove information from the file that is not beneficial (to save tokens).

* Keep it concise. For each line, ask: “Would removing this cause Claude to make mistakes?” If not, cut it.
    * Include / keep / add:
        * Bash commands Claude can’t guess
        * Code style rules that differ from defaults
        * Testing instructions and preferred test runners (currently none, but we will add a test harness and tests soon)
        * Repository etiquette (branch naming, PR conventions) (currently everything is done directly on main)
        * Architectural decisions specific to the project
        * Developer environment quirks (required env vars)
        * Common gotchas or non-obvious behaviors
    * Exclude / remove:
        * Anything Claude can figure out by reading code
        * Standard language conventions Claude already knows
        * Detailed API documentation (link to docs instead) -- but keep (and expand, if needed) the documentation/information about the Pantheon API.
        * Information that changes frequently
        * Long explanations or tutorials
        * File-by-file descriptions of the codebase
        * Self-evident practices like “write clean code”

Use the /claude-md-improver skill (plus other skills as appropriate) for this work.  The guidance and lists above are not exhaustive.

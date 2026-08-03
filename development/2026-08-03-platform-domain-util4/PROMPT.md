I want to design a feature as follows:

Create a new utility script named `apply-pantheon-domains-cloudflare.py` in this repo that can be run separately from `pantheon-sitehealth-emails`.

This script should take either a plan file or a revert file as a command line argument and make the changes in Cloudflare specified in the file.  The script should check the contents of the file against Cloudflare to ensure they are valid (for example, that Cloudflare is in the state anticipated by the file); if there are problems with any entry, the script should exit with a fatal error without doing anything. After the check, the script should default to a dry run mode where it reports on the changes it will make (if run with `--verbose`, it should also print the Cloudflare API calls, including request bodies, it would make).  If the `--for-real` command line option is given, the script should still report but should additionally go ahead and make each API call.  If any API call fails, the script should exit immediately with a fatal error; it should not attempt to revert any changes it has already made, and it should not attempt to make the remaining changes specified in the file.

When the script exits, regardless of if it exits normally or with a fatal error, the script should report the total number of sites specified by the plan, how many suceeded, how many failed, and how many were not attempted.

For additional details and requirements, read the files in `development/2026-07-31-platform-domain-util3`, especially `PROMPT.md`, `PLAN.md`, and (most importantly) `SPEC.md`.

Do not put any significant amount of work into making this script fast or efficient.

This script will only be used for a few months.  After Pantheon completes their migration from their old CDN (Pantheon Fastly) to their new CDN (Pantheon Cloudflare, which is separate from U-M Cloudflare), we will delete this script.

You can import code written for the main `pantheon-sitehealth-emails` script where it makes sense, but only if it does not need to be significantly modified (no more than a few lines changed). Prefer copying code written for the main script into the new `apply-platform-domains-cloudflare.py` script; code that is copied should be in the `apply-platform-domains-cloudflare.py` script rather than modularized in order to make deletion/cleanup easy after the CDN migration has been completed later this year.

Adhere to everything in `prompts/new-feature-standards.md`.

Let's brainstorm this.

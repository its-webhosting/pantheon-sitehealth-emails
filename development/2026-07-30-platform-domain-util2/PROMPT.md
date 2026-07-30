I want to design a feature as follows:

Create a new utility script named `find-platform-domains-cloudflare` in this repo that can be run separately from `pantheon-sitehealth-emails`.

The script should do the same thing the code that generates `fqdns.json` does, with the following differences:
    1. It should consider **all** DNS records in all Cloudflare zones, not just proxied records.
    2. It should only include in its output CNAME records that point to a target that ends in ".pantheonsite.io"
    3. The output should be written to the file `./platform-domains-cloudflare.json`. (The JSON should contain the same fields/stucture as `./fqdns.json`)
    4. It should always regnerate its output file each time it is run, regardless of the age of the existing file if it exists.

Do not put any significant amount of work into making this script fast or efficient.

This script will only be used for a few months.  After Pantheon completes their migration from their old CDN (Pantheon Fastly) to their new CDN (Pantheon Cloudflare, which is separate from U-M Cloudflare), we will delete this script.

You can import code written for the main `pantheon-sitehealth-emails` script where it makes sense, but only if it does not need to be significantly modified (no more than a few lines changed). Prefer copying code written for the main script into the new `find-platform-domains-cloudflare` script; code that is copied should be in the `find-platform-domains-cloudflare` script rather than modularized in order to make deletion/cleanup easy after the CDN migration has been completed later this year.

Adhere to everything in `prompts/new-feature-standards.md` except as noted above (do not worry about maintainability or modularity).

Let's brainstorm this.

I want to design a feature as follows:

Modify the a utility script named `find-platform-domains-cloudflare`

The `--output` option should be changed to `--output-basename`.  Instead of being given an argument such as `platform-domains-cloudflare.json`, it should be given the same argument without any file extension.  If a file extension is provided, that is a fatal error.  Example: `./find-platform-domains-cloudflare -v --output-basename engin-zone engin.umich.edu` would sweep only the zone engin.umich.edu and save the script's regular/current output in a file named `engin-zone.json` (constructed by appending `.json` to the output basename).

If the `--output-basename` option **is not** provided, the script should then function as it does today, producing the same output as it currently does on stdout and then exiting.

If the `--output-basename` option **is** provided, then in addition to writing its regular/currently output to the basename file with `.json` appended (as described above), the script should **also** do the following things:

1. The script should write a second output file with the name `<basename>-plan.json`.  This file should contain a set of Cloudflare DNS record batch update records as outlined in the section named `Recommended mechanics: one batch call` in the document development/2026-07-30-platform-domain-util2/research.md.
    a. We will write another script, later, that will read the `<basename>-plan.json` and make the API calls.  The `find-platform-domains-cloudflare` script will not do this work.
    b. The `<basename>-plan.json` file should contain a separate update object for each FQDN so a human or another script can filter the file before applying the updates to Cloudflare.
    c. Each update object in the file should contain everything needed to make the Cloudflare DNS record batch update call for the FQDN in question.  At a minimum, it must contain the exact JSON body to be used for the API call. It should also contain any other information (other than credentials) that is needed to make that API call; if there is no such information, then the update object can be exactly the API call JSON body.
    d. When the API call is made to update the FQDN record(s), all meaningful data and configuration must be carried over and preserved between the original and new record(s). At a minimum, this should include whether the original record is proxied, any comment that may be present, any tags that may be present, TTL, and other settings (excluding any settings that are definitively irrelevant/inappropriate based on the nature of the update).  If any of this data is missing from the main output file `<basename>.json`, add it.  Research what can be in a Cloudflare DNS record in order to make these detminations.
2. The script should write a third output file with the name `<basename>-revert.json`. This file should contain a set of Cloudflare DNS batch update records, in the same format as for `<basename>-plan.json` (with differences only as necessary to support the revert operation) that the to-be-written script from 1(a) can use to undo an API application of the plan file.  To the greatest extent possible have the files include all necessary information to ensure that applying the plan file followed by the revert file results in a state as close as possible/feasible to the original state (deviations that are not meaningful, including as object IDs, last-modified times, revisions/version are OK). Ideally, we would be able to apply plan / revert / plan / revert multiple times without harming or breaking anything in Cloudflare, for the DNS records/configuration in Cloudflare (as queried by clients via DNS for non-proxied records), and for websites that are proxied through Cloudflare.

Do not put any significant amount of work into making this script fast or efficient.

This script will only be used for a few months.  After Pantheon completes their migration from their old CDN (Pantheon Fastly) to their new CDN (Pantheon Cloudflare, which is separate from U-M Cloudflare), we will delete this script.

You can import code written for the main `pantheon-sitehealth-emails` script where it makes sense, but only if it does not need to be significantly modified (no more than a few lines changed). Prefer copying code written for the main script into the new `find-platform-domains-cloudflare` script; code that is copied should be in the `find-platform-domains-cloudflare` script rather than modularized in order to make deletion/cleanup easy after the CDN migration has been completed later this year.

I may have not through through everything fully here, so look at everything critically and deeply to identify gaps, contradictions, and other problems.

Adhere to everything in `prompts/new-feature-standards.md`.

Let's brainstorm this.

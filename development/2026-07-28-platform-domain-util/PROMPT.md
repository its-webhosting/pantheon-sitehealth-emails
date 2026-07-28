I want to design a feature that does the following:

A utility script named `find-platform-domains-dns` in this repo that can be run separately from `pantheon-sitehealth-emails` that lists all the sites in the org (including sites on the sandbox plan) and, for each one,
1. For each environment the site has (including multidev environments)
   a. Lists all the custom domains in the environment
   b. For each domain
       i. look up the domain in DNS, following all CNAMES until a non-CNAME record is reached
       ii. if any record in the chain is a CNAME pointing to a target ending in `.pantheonsite.io`, write a CSV row to stdout.  The format of the row should be: `site_name,site_env,custom_domain,platform_domain` where `custom_domain` and `platform_domains` are both FQDNs and `platform_domain` is the CNAME target that ends in `.pantheonsite.io`.

Do include primary domains.

Do not worry about any custom domains that point to Cloudflare. Another team is writing a script that will handle custom domains that are behind Cloudflare for which Cloudflare is using a platform domain CNAME as its origin.

Do not put any significant amount of work into making this script fast or efficient (but do have the script save time/work where it is cheap and easy to do so).

This script will only be used for a few months.  After Pantheon completes their migration from their old CDN (Pantheon Fastly) to their new CDN (Pantheon Cloudflare, which is separate from U-M Cloudflare), we will delete this script.

You can import code written for the main `pantheon-sitehealth-emails` script where it makes sense, but only if it does not need to be significantly modified (no more than a few lines changed). Prefer copying code written for the main script into the new `find-platform-domains-dns` script; code that is copied should be in the `find-platform-domains-dns` script rather than modularized in order to make deletion/cleanup easy after the CDN migration has been completed later this year.

Adhere to everything in `prompts/new-feature-standards.md` except as noted above (do not worry about maintainability or modularity).

Let's brainstorm this.

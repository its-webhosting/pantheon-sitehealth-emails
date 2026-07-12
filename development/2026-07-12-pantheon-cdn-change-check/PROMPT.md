Add new test(s) to existing or new checks under `./check/` based on best practices in terms of stucture and modularity as well as practicality.

Pantheon is moving from an old CDN (Fastly) to a new CDN (Cloudflare, but a separate instance from the Cloudflare instance UMich uses; UMich will use Cloudflare Orange to Orange to layer our Cloudflare in front of Pantheon's new Cloudflare).  In order for a site to be migrated from the old Pantheon CDN to the new one, there must be no CNAMEs pointing at targets ending in `.pantheonsite.io` in either DNS or Cloudflare.

Records under the domain pantheonsite.io point to the old CDN that Pantheon will be moving away from.  DNS and Cloudflare records that point to FQDNs under pantheonsite.io need to be changed to be A/AAAA records instead.

If DNS or Cloudflare have CNAMEs with a target that ends in something other than `.pantheonsite.io`, resolve the CNAME and repeat as needed. If any CNAME in the chain ends in `.pantheonsite.io`, add the notice. If no CNAME in the chain ends in `.pantheonsite.io`, then the original Pantheon custom domain FQDN is fine (but check all Pantheon custom domain FQDNs).

Pantheon custom domains that are not Primary domains should not be handled specially, nor should Primary domains be handled specially.

For a site's **live environment only**, if a site has a Pantheon custom domain with an FQDN that is a CNAME (in DNS or in Cloudflare) pointing at a target ending in `.pantheonsite.io` (or another CNAME target in the chain for this FQDN does, see below), add an info-level (magnifying glass) notice that says [Pantheon is making a change to their CDN](https://docs.pantheon.io/guides/global-cdn/global-cdn-beta#setup) (include this link in the notice) that requires all custom domains to resolve (in DNS and Cloudflare) via A and AAAA records, **not** via CNAME records.

In language for the notice, when refering to Pantheon's old CDN, use the phrase "legacy Pantheon GCDN (Fastly)"; when referring to Pantheon's new CDN, use the phrase "new Pantheon GCDN Beta (Pantheon Cloudflare)". Once these terms are established, you can use them or shorten them to "legacy GCDN" and "new GCDN Beta" as needed to make the notice language as readable as possible without introducing confusion.  In the notice, always use the phrase "U-M Cloudflare" (if `umich_enabled()`) when talking about existing non-Pantheon Cloudflare, or "our (non-Pantheon) Cloudflare" (if not `umich_enabled()`).

Keep the notice concise and very clear. Other than saying Pantheon is making a change to their CDN (including the link above), the notice **should not** explain the overall Pantheon CDN transition or Pantheon's process, Pantheon versus non-Pantheon Cloudflare, Orange to Orange, or other things beyond what changes the site owner needs to make in (non-Pantheon) Cloudflare and/or DNS.

For a site, there should be only a single notice for this check, covering all affected Pantheon customer domain FQDNs for the site.

Look up the DNS record ending in `.pantheonsite.io` that the CNAME for the Panthone custom domain FQDN in question is pointing to in DNS or Cloudflare to determine the A and AAAA records that they should use to replace the CNAME record in question.  Note that the DNS record ending in `.pantheonsite.io` will be a CNAME which will in turn resolve to A and AAAA records. Note a single Pantheon site will have the same A and AAAA values for all its Pantheon custom domains FQDNs.

You **should not** detect whether Cloudflare is handling DNS for the site FQDN (versus non-Cloudflare DNS); assume the site owner knows that.

In the notice language, provide, in table form, which of the site's Pantheon custome domain FQDNs need to be changed, whether the change for each FQDN is in DNS (which may or may not be Cloudflare DNS) or in Cloudflare (if DNS points to Cloudflare), and the A and AAAA values the site owner should use.
Note: for a single site, some FQDNs could need to be changed in DNS while others need to be changed in Cloudflare.

For the generic message for non-UMich institutions, direct the site owners to make any necessary changes themselves.

For UMich (`umich_enabled()`) sites, if the current date is before September 15, 2026, the notice should say ITS will handle the changes during an upcoming maintenance that will be scheduled, but that site owners can choose to make the changes themselves before then if they prefer. **DO NOT** include September 15 in the notice, this is an internal date that is only used by the program and I will change this date in the program to be the actual date once I have scheduled the maintenance.
On or after this date, UMich sites should get the generic notice message.
Do not make the date configurable, it will be changed one time after I schedule the maintenance, and then after the date passes I will have you remove the date and UMich specific notice language entirely, leaving only the generic notice language.

Example sites that should get notices under this new check:
  * site name `bus-occb`, Pantheon custom domain occb.bus.umich.edu, DNS points to live-bus-occb.pantheonsite.io, add a notice, the CNAME in DNS should be replaced with an A record for 23.185.0.4 and AAAA records for 2620:12a:8000::4 and 2620:12a:8001::4.
  * site name `its-backstage`, Pantheon custom domain backstage.its.umich.edu, DNS points at Cloudflare, but Cloudflare points at live-its-backstage.pantheonsite.io, looking up live-its-backstage.pantheonsite.io in DNS, the CNAME record in Cloudflare should be replaced with an A record for 23.185.0.2 and AAAA records for 2620:12a:8000::2 and 2620:12a:8001::2.

Adhere to everything in `prompts/new-feature-standards.md`.

Let's brainstorm this.


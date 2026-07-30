# Research findings: swapping a proxied CNAME for proxied A/AAAA records without disturbing the Universal edge certificate

## Context

Part of the Pantheon CDN migration work. Custom domains such as
`example1.cdn-dev.it.umich.edu` currently sit in Cloudflare DNS as **proxied CNAME**
records pointing at `live-umich-example1.pantheonsite.io`. Pantheon's replacement
records are A/AAAA (`23.185.0.4`, `2620:12a:8001::4`, `2620:12a:8000::4`), so the
rewrite must delete one CNAME and create three A/AAAA records at the same name — and
later reverse that. Each such hostname has a Cloudflare **Universal** edge certificate
whose `commonName` is the hostname itself. The question is whether the record swap
invalidates that certificate or forces re-issuance.

**No changes were made to any Cloudflare account.** This is research only.

## Answer

**No.** In both directions, provided two conditions hold:

1. the replacement records are **Proxied** (orange cloud), and
2. the **hostname string does not change**.

Nothing in Cloudflare's DNS-record API path deletes, revokes, or re-validates an edge
certificate. A Universal certificate is bound to a **hostname**, not to a DNS-record
object, and certificate selection at the edge is driven by SNI/hostname plus proxy
status — never by record type. `A`, `AAAA`, and `CNAME` are all proxiable types and are
interchangeable as far as TLS termination is concerned.

### Why the certificate is unaffected

- Certificate selection is hostname/SNI-based: exact SNI match first, then wildcard,
  ranked by certificate type and recency. Record type is not an input.
  → <https://developers.cloudflare.com/ssl/reference/certificate-and-hostname-priority/>
- The only DNS-side precondition is proxy status: *"Cloudflare can only serve an
  SSL/TLS certificate for a DNS record when you set the record's proxy status to
  **Proxied**."*
  → <https://developers.cloudflare.com/ssl/edge-certificates/universal-ssl/limitations/>
- The documented events that **do** remove a Universal certificate are all
  zone-/setting-level, not record-level:
  - disabling Universal SSL (`PATCH /zones/{zone_id}/ssl/universal/settings`)
  - converting the zone setup — *"If you are using Universal SSL, converting to a CNAME
    setup will delete your existing Universal SSL certificates."*
    → <https://developers.cloudflare.com/dns/zone-setups/conversions/convert-full-to-partial/>
  - the certificate-pack `DELETE` endpoint is scoped to **Advanced** Certificate Manager
    packs ("Delete Advanced Certificate Manager Certificate Pack"), so it cannot be used
    to drop a Universal pack.
    → <https://developers.cloudflare.com/api/resources/ssl/subresources/certificate_packs/methods/delete/>
- A certificate is a signed artifact with a fixed validity window (Universal = 90 days,
  auto-renewal starts 30 days out). DNS edits neither shorten it nor trigger reissuance.
  → <https://developers.cloudflare.com/ssl/reference/certificate-validity-periods/>

### Which certificate covers this hostname

The certificate's `commonName` being the full `example1.cdn-dev.it.umich.edu` indicates
a **per-hostname Universal certificate**, which is what a **partial (CNAME setup)** zone
produces:

- *"On Partial zones, Universal SSL is provisioned per proxied hostname regardless of
  subdomain depth."*
  → <https://developers.cloudflare.com/ssl/edge-certificates/advanced-certificate-manager/>
- *"On a CNAME setup zone, each subdomain (regardless of level) has its own Universal
  SSL certificate…"*
  → <https://developers.cloudflare.com/ssl/edge-certificates/universal-ssl/limitations/>
- Partial-setup provisioning trigger: *"Provisioned once the DNS record is proxied
  through Cloudflare."*
  → <https://developers.cloudflare.com/ssl/edge-certificates/universal-ssl/enable-universal-ssl/>

Consequence for a partial zone: the hostname's continuous **proxied** state is what
keeps automatic DCV (and therefore automatic renewal) working — *"When every hostname on
a non-wildcard certificate is proxying traffic through Cloudflare and the DCV method is
HTTP, Cloudflare can automatically complete DCV on your behalf."*
→ <https://developers.cloudflare.com/ssl/edge-certificates/changing-dcv-method/>
A proxied A/AAAA record satisfies this exactly as a proxied CNAME does.

(If the zone were instead a *full* setup with `cdn-dev.it.umich.edu` as the apex, the
hostname would be covered by the zone's `*.cdn-dev.it.umich.edu` Universal certificate
and the conclusion is the same — but the `commonName` would be the apex, not the
hostname.)

## Constraint that forces the delete-then-create shape

A CNAME cannot coexist with other types at the same name — *"queries for other record
types on the same name are not supported."*
→ <https://developers.cloudflare.com/dns/manage-dns-records/reference/dns-record-types/>

So the CNAME must be gone before the A/AAAA records exist (and vice versa on the
reverse). There is no in-place "change the type" operation.

## Recommended mechanics: one batch call

Use the batch endpoint rather than separate DELETE + POST calls. Its documented
execution order is **Deletes → Patches → Puts → Posts**, all inside a single database
transaction, so the name is never left without a record in Cloudflare's control plane:

- <https://developers.cloudflare.com/dns/manage-dns-records/how-to/batch-record-changes/>
- <https://developers.cloudflare.com/api/resources/dns/subresources/records/methods/batch/>
  (`POST /zones/{zone_id}/dns_records/batch`)

Caveat to respect, quoted from that endpoint's own description: *"Although Cloudflare
will execute the batched operations in a single database transaction, Cloudflare's
distributed KV store must treat each record change as a single key-value pair. This
means that the propagation of changes is not atomic."* Propagation is sub-second in
practice, and the edge certificate is unaffected regardless — the only exposure is a
brief authoritative-DNS window, not a TLS window.

Forward direction (scenario 1) — shape only, not to be run yet:

```jsonc
{
  "deletes": [ { "id": "<cname_record_id>" } ],
  "posts": [
    { "type": "A",    "name": "example1.cdn-dev.it.umich.edu", "content": "23.185.0.4",         "proxied": true, "ttl": 1 },
    { "type": "AAAA", "name": "example1.cdn-dev.it.umich.edu", "content": "2620:12a:8000::4",   "proxied": true, "ttl": 1 },
    { "type": "AAAA", "name": "example1.cdn-dev.it.umich.edu", "content": "2620:12a:8001::4",   "proxied": true, "ttl": 1 }
  ]
}
```

Reverse direction (scenario 2): the three A/AAAA ids in `deletes`, one proxied CNAME to
`live-umich-example1.pantheonsite.io` in `posts`.

`proxied: true` is the load-bearing field in both directions. A record created
DNS-only would take the hostname out of certificate service (and, on a partial zone,
out of automatic DCV).

## Verification (read-only, one throwaway hostname first)

1. Before: `GET /zones/{zone_id}/ssl/certificate_packs?status=all` — record the pack
   `id`, `status`, `hosts`, and `primary_certificate` for the hostname.
   → <https://developers.cloudflare.com/api/resources/ssl/subresources/certificate_packs/methods/list/>
2. Before: capture the served leaf certificate's serial and validity —
   `openssl s_client -connect example1.cdn-dev.it.umich.edu:443 -servername example1.cdn-dev.it.umich.edu </dev/null | openssl x509 -noout -serial -dates -subject`
3. Run the batch swap on that one hostname.
4. After (immediately, then again at ~15 min): repeat steps 1 and 2 and diff. Expect an
   identical pack id, `status: active`, and an identical certificate serial — i.e. the
   same certificate, not a re-issued one.
5. Confirm the DNS answer changed as intended (`dig +short A/AAAA` against Cloudflare's
   authoritative NS for the zone, or the record list API) and that HTTPS still serves.
6. Reverse the swap on the same hostname and repeat, to prove scenario 2 symmetrically.

## What would break it

- Creating the replacement records **DNS-only** instead of proxied.
- Any change to the hostname itself (a different label is a different certificate).
- Disabling Universal SSL, or converting the zone between full and partial setup.
- Leaving the hostname unproxied long enough on a partial zone that automatic HTTP DCV
  cannot complete during a renewal window (30 days before expiry) — not a risk for a
  swap measured in seconds.

## Documented silence worth stating plainly

Cloudflare's docs do not contain an explicit sentence of the form "editing or deleting a
DNS record does not affect your edge certificate." The conclusion above is built from
the documented mechanism (hostname/SNI-based selection + proxy-status precondition) and
from the fact that every documented certificate-removal path is zone- or
setting-scoped. Step 4 of the verification section is what turns that into a measured
fact for this specific zone; do it on one disposable hostname before touching anything
that matters.

## Sources

- <https://developers.cloudflare.com/ssl/edge-certificates/universal-ssl/>
- <https://developers.cloudflare.com/ssl/edge-certificates/universal-ssl/limitations/>
- <https://developers.cloudflare.com/ssl/edge-certificates/universal-ssl/enable-universal-ssl/>
- <https://developers.cloudflare.com/ssl/edge-certificates/advanced-certificate-manager/>
- <https://developers.cloudflare.com/ssl/edge-certificates/changing-dcv-method/>
- <https://developers.cloudflare.com/ssl/reference/certificate-and-hostname-priority/>
- <https://developers.cloudflare.com/ssl/reference/certificate-validity-periods/>
- <https://developers.cloudflare.com/ssl/reference/certificate-rotation/>
- <https://developers.cloudflare.com/dns/zone-setups/partial-setup/setup/>
- <https://developers.cloudflare.com/dns/zone-setups/conversions/convert-full-to-partial/>
- <https://developers.cloudflare.com/dns/manage-dns-records/reference/dns-record-types/>
- <https://developers.cloudflare.com/dns/manage-dns-records/how-to/batch-record-changes/>
- <https://developers.cloudflare.com/api/resources/dns/subresources/records/methods/batch/>
- <https://developers.cloudflare.com/api/resources/ssl/subresources/certificate_packs/methods/list/>
- <https://developers.cloudflare.com/api/resources/ssl/subresources/certificate_packs/methods/delete/>

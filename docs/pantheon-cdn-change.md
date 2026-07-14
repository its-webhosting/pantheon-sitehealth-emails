# Pantheon CDN-change check (`check/pantheon_cdn_change/`)

**This check is temporary.** It exists only to help sites move off Pantheon's legacy CDN
before Pantheon's migration deadline. Once that migration is complete for every site this
tool reports on, delete the whole package — see "Deleting this check" below.

## What it reports, and why

Pantheon is migrating every site from the **legacy Pantheon GCDN (Fastly)** — whose edge
names live under `pantheonsite.io` — to the **new Pantheon GCDN Beta (Pantheon
Cloudflare)**. See <https://docs.pantheon.io/guides/global-cdn/global-cdn-beta#setup>. A
site cannot be migrated while **any** of its custom domains still reaches a legacy-GCDN
name through a CNAME record — in public DNS, or in our (non-Pantheon) Cloudflare. Those
CNAME records must be replaced with A and AAAA records before Pantheon will move the site.

This check runs at the `site_post_dns` phase, looks at every `type == "custom"` domain on
the site's **live** environment, and — for any that still CNAME to a legacy-GCDN name —
emails the owner one `info` notice listing the affected domains, where to fix each one,
and the records Pantheon says to use instead. It never looks at non-live environments, and
it treats the primary domain the same as every other custom domain.

Two worked examples (both verified live, 2026-07-12), showing why a single check has to
cover two different situations:

- **`occb.bus.umich.edu`** (site `bus-occb`): public DNS shows `occb.bus.umich.edu` →
  CNAME `live-bus-occb.pantheonsite.io` → CNAME `fe4.edge.pantheon.io` → A `23.185.0.4`,
  AAAA `2620:12a:8000::4` and `2620:12a:8001::4`. The legacy-GCDN CNAME is visible by
  simply resolving the domain — no Cloudflare involved.
- **`backstage.its.umich.edu`** (site `its-backstage`): public DNS shows only a CNAME to
  `backstage.its.umich.edu.cdn.cloudflare.net`, resolving to Cloudflare's anycast
  addresses. The legacy-GCDN name is invisible there — it only shows up as the **origin**
  Cloudflare proxies to, which `fqdns.json` already records:
  `{"origins": ["live-its-backstage.pantheonsite.io"], "zone_id": "…"}`, resolving to A
  `23.185.0.2`, AAAA `2620:12a:8000::2` and `2620:12a:8001::2`.

## Two detection sources — and why both are required

The check runs two independent detection sources per custom domain, neither of which is
sufficient on its own:

1. **Public DNS.** Walk the CNAME chain starting at the FQDN itself
   (`check/pantheon_cdn_change/chain.py`). This is the *only* source that sees an
   **unproxied** (grey-cloud) Cloudflare CNAME, or a domain with no Cloudflare involvement
   at all — like `occb.bus.umich.edu` above.
2. **Cloudflare origins.** For a **proxied** FQDN, its Cloudflare CNAME target is invisible
   in public DNS — visitors and this check alike see only
   `*.cdn.cloudflare.net` and Cloudflare's anycast addresses. The origin Cloudflare
   actually proxies to is recorded in `fqdns.json` (fetched by
   `plugin/cloudflare/fqdns.py`), so the check reads each FQDN's `origins` there and walks
   the CNAME chain from each hostname origin (IP-literal origins are skipped — they cannot
   be a CNAME to anything) — like `backstage.its.umich.edu` above.

Because a proxied FQDN's real target is invisible in DNS, and an unproxied FQDN's CNAME is
absent from `fqdns.json` (which lists only proxied records), running only one source would
silently miss whichever category it doesn't cover. Together they cover every case, and the
check never needs to determine who operates DNS for a domain — it only needs the domain
owner to already know that (source ② self-gates on `sc.cloudflare_enabled()`, so an
institution with no Cloudflare configured still gets full coverage from source ①).

When both sources fire on the same FQDN but reach **different** legacy-GCDN names — the
site was renamed on Pantheon, a Cloudflare origin was never updated, a domain moved between
Pantheon sites — the check still emits exactly one row (see below for why the row is
identical either way) but also prints an operator `ATTENTION` naming both targets, because
the disagreement itself signals something is misconfigured on the site.

## Where the replacement records come from — and why

The addresses shown to the owner come from **Pantheon**, per domain, via one call to
`terminus domain:dns <site>.live`, made lazily — only for a site that has at least one
detected candidate. A clean site issues no extra `terminus` call at all.

The obvious alternative — resolve the legacy-GCDN name the broken CNAME points at, and show
whatever A/AAAA it currently has — is deliberately **not** what this check does, because it
is wrong in exactly the cases this check exists to catch. When a CNAME points at a **stale**
legacy-GCDN name (the site was renamed on Pantheon, a Cloudflare origin was never updated, a
domain moved between Pantheon sites), that name belongs to a **different Pantheon site**.
Resolving it would return that other site's edge addresses, and the check would email the
owner someone else's IP addresses with total confidence. Asking Pantheon directly, per
domain, avoids this: Pantheon's answer is authoritative for *this* domain regardless of what
any DNS record currently points at, and it is never stale.

This also means the addresses in a sent email are **Pantheon's recommendation at send
time** — they track Pantheon's own state, not a snapshot frozen into the check's code.
Whoever performs the maintenance should re-run the report close to when they do the work
rather than trusting the addresses in a months-old email, because Pantheon's answer can
change (an edge migration, or the site itself moving onto the new GCDN Beta) between when a
report was sent and when someone acts on it.

`terminus` is used here rather than the Pantheon API (which has the equivalent endpoint,
`GET /v0/sites/{id}/environments/{env}/domains/dns`) even though this codebase generally
prefers the API for new code: the script has no Pantheon API client today, and building
one — machine-token → session-token auth, a session cache, an HTTP seam, new offline
fixtures — is not worthwhile for a check that gets deleted once Pantheon's migration is
done. `terminus()` is the established wrapper and `run_terminus()` is the test harness's
mock seam, so this rides the existing offline test machinery at no extra cost. When an API
client is eventually built for other reasons, `check/pantheon_cdn_change/pantheon.py` is a
one-function swap.

## "A and AAAA, not CNAME" is a pre-migration rule, not a permanent one

Before a site migrates, Pantheon's `domain:dns` requires A and AAAA records for a custom
domain — that is what `required_records()` normally returns. But the *target-state* record
type is Pantheon's to define, not this check's, and Pantheon's own answer already reflects
that: a site already on the new GCDN Beta is offered a **CNAME**, not addresses. Verified
live on `its-wws-test1` (2026-07-12): `domain:dns` returns `status: okay` and a single
CNAME row to `fe.cfp2c.edge.pantheon.io`, with **no A/AAAA rows at all**. The check treats
this as an answer, not a failure — the notice's "Replace the CNAME record with" cell shows
`CNAME fe.cfp2c.edge.pantheon.io` verbatim, and an operator `ATTENTION` notes that the site
may already be on the new GCDN Beta. Whatever record type Pantheon requires for a given
domain at the time of the call is what the check renders; it never assumes A/AAAA is the
only valid answer.

## The `fqdns.json` freshness dependency

Source ② (Cloudflare origins) reads `fqdns.json` from whatever is currently on disk. A
**single-site** run does **not** refresh that file — `decide_fqdns_update()` only refreshes
a stale file automatically when multiple sites are being processed
(`--all`, or more than one site named on the command line). So a single-site run's
Cloudflare-side detection can answer from data that is more than 24 hours old: a
newly-proxied FQDN can be missed, or an already-fixed one can still be nagged about.

When the answer needs to be current — for example, spot-checking one site before or after
maintenance — pass `--update-cloudflare-fqdns` to force a refresh first. The
`plugin/cloudflare/fqdns.py` setup hook already warns, once per run, whenever `[Cloudflare]`
is enabled and the file is stale and about to be consumed; that warning names this check's
consequence explicitly, so a stale-data run is never silent about it. (A **missing**
`fqdns.json` is not a concern here: any run that reaches a site phase auto-refreshes a
missing file regardless of `--all`/single-site.)

## The U-M maintenance cutoff

`check/pantheon_cdn_change/hook.py` defines:

```python
UMICH_MAINTENANCE_CUTOFF = datetime.date(2026, 9, 15)
```

Before this date, a U-M site (`sc.umich_enabled()` true) gets copy saying ITS will make the
CNAME-to-A/AAAA change during an upcoming, to-be-scheduled maintenance. On or after this
date — and for every non-U-M run regardless of date — the notice instead tells the owner to
replace the records themselves. `hook.today()` is the seam tests monkeypatch to select
either branch deterministically.

Two edits are expected over this check's lifetime:

1. **Once the ITS maintenance is actually scheduled**, change `UMICH_MAINTENANCE_CUTOFF` to
   the real date.
2. **Once that date has passed**, delete the constant, the `today()` seam, the
   `before_cutoff` parameter, and the U-M branch of `cdn_change_notice()` in
   `check/pantheon_cdn_change/notices.py` — leaving only the generic self-serve copy. The
   date itself is never shown to site owners; it only selects which copy variant they see.

## Deleting this check

Once Pantheon's migration to the new GCDN Beta is complete for every site this tool reports
on, remove the whole feature:

```bash
git rm -r check/pantheon_cdn_change \
          tests/unit/test_pantheon_cdn_change_*.py \
          tests/integration/test_check_pantheon_cdn_change.py \
          tests/integration/test_pantheon_cdn_change_notice_render.py \
          tests/e2e/test_golden_cdn_change.py \
          tests/fixtures/terminus-cdnchange
# then drop the matching snapshot files (tests/e2e/__snapshots__/test_golden_cdn_change.ambr
# and the pantheon-cdn-change entries in
# tests/integration/__snapshots__/test_pantheon_cdn_change_notice_render.ambr) and remove this
# doc's references from CLAUDE.md.
```

**Keep** everything below — these are general fixes and shared infrastructure this check
depended on, not part of the temporary check itself:

- `dns_classify.MalformedNameError` and the `dns_classify.resolve` seam that raises it —
  this is a standing core bug fix (a malformed Pantheon domain id could otherwise abort an
  entire `--all` run), unrelated to CDN migration.
- `sc.terminus` / `sc.fqdn_re` in the core sc-exposure block — the documented, general way
  a check package reaches those core helpers; other checks may come to depend on them.
- `tests/helpers/` (`dnsfake.py`, `checkload.py`) — the shared fake DNS resolver, recording
  console, and standalone check-package loader are reusable by any future check.
- `tests/shims/pyshim/dnsshim.py` — the subprocess DNS shim, useful for any future e2e test that needs
  deterministic DNS answers in a subprocess run.
- The `plugin/cloudflare/fqdns.py` comment correction (that `origins` are consumed, not just
  `zone_id` reserved for later) — leave it corrected even after this check is gone, since a
  future consumer of `origins` may exist by then; if not, that's a separate cleanup.

# `find-platform-domains-dns` — closing audit

Answers to SPEC §15's six questions, from the first full-organization sweep.

**The run.** `./find-platform-domains-dns -v` (no `SITE` arguments — whole organization), CSV
to one file, stderr to another, 2026-07-28.

```
sites=409 envs=1644 custom_domains=513 rows=31 indeterminate=0
exit=0
```

Prefix tally on the stderr log: `SKIPPED:` 0, `WARNING:` 2, `RETRY:` 0. Zero `\r` bytes in the
CSV. `grep -c SKIPPED` (0) equals the reported `indeterminate=0`, so SPEC §8's reconciliation
property holds on real data.

The 31 rows span **16 distinct sites** and these environments: live 18, dev 5, test 5, stage 1,
autopilot 1, wip 1 — so the decision to sweep every environment rather than just `live` (SPEC
§2.2) earned 13 of the 31 rows, 42%.

---

## Q1 — mid-chain hits, and repeated `dns_record` values

**Two rows have `dns_record != custom_domain`** (2 of 31, 6.5%):

```
stamps-ipd,live,www.ipd.umich.edu,ipd.umich.edu,live-stamps-ipd.pantheonsite.io
med-mship,live,www.shipping.umich.edu,shipping.umich.edu,live-med-mship.pantheonsite.io
```

Verified against public DNS:

```
www.ipd.umich.edu       -> ipd.umich.edu.
ipd.umich.edu           -> live-stamps-ipd.pantheonsite.io.
www.shipping.umich.edu  -> shipping.umich.edu.
shipping.umich.edu      -> live-med-mship.pantheonsite.io.
```

The `dns_record` column is doing exactly the job it was added for: the record that must be
rewritten is the apex, not the `www` custom domain the row is keyed on.

**Yes — two `dns_record` values each appear in more than one row.** 29 distinct `dns_record`
values across 31 rows:

```
ipd.umich.edu        stamps-ipd,live,ipd.umich.edu,ipd.umich.edu,…
                     stamps-ipd,live,www.ipd.umich.edu,ipd.umich.edu,…
shipping.umich.edu   med-mship,live,shipping.umich.edu,shipping.umich.edu,…
                     med-mship,live,www.shipping.umich.edu,shipping.umich.edu,…
```

The §15 sample of 30 sites found 0 of 7 — the full sweep finds 2 of 31. **Both duplicate pairs
are within a single site**, so no rewrite crosses a site boundary, which is the more dangerous
shape the question anticipated. The pattern in both cases is identical: the apex is a custom
domain in its own right *and* the target of the `www` alias, so it appears once as a direct hit
and once as a mid-chain hit.

**Action for the downstream rewriter:** de-duplicate on the `dns_record` column before acting.
Processing these rows naively rewrites `ipd.umich.edu` twice; the second pass would find A/AAAA
records where it expected a CNAME. This is a real operational note, not a defect in this tool —
the CSV reports what it found, one row per custom domain, as specified.

## Q2 — rows and indeterminates

**31 rows, 0 indeterminates**, across 513 custom domains on 1644 environments. Nothing to
diagnose: no resolver limit was hit, no API pattern produced a skip, and no domain failed to
resolve in a way that needed a second look. The 2-second `DNS_RETRY_SLEEP` and the retry
asymmetry were never exercised on this run.

## Q3 — did G13 (cross-site targets) fire?

**No.** The two `WARNING:` lines are both **G13a** (mid-chain alias), not G13:

```
WARNING: stamps-ipd.live www.ipd.umich.edu: the record to change is ipd.umich.edu, not the
  custom domain; verify who else points at it before rewriting
WARNING: med-mship.live www.shipping.umich.edu: the record to change is shipping.umich.edu,
  not the custom domain; verify who else points at it before rewriting
```

No row's platform-domain target belonged to a different site or environment. Both rows are safe
to hand to the rewriter subject to the Q1 de-duplication note — and the warning text already
tells the operator to check who else points at the record, which is precisely the Q1 hazard.

## Q4 — custom domains on uninitialized environments?

**No.** Every environment that produced a row is `initialized: true`. Checked directly against
the Pantheon API for all nine non-`live` site/environment pairs that produced rows
(`dsa-studentlife` dev+test, `obp-michigan-metrics` stage, `phar-wordpress`
autopilot+dev+test+wip, `soe-grip-themat-v` dev+test) — all `initialized=true`. The 25-site
sample in §2.2 is not contradicted, and the decision not to skip uninitialized environments cost
nothing on this run.

## Q5 — did the G4a ignored-cursor detector fire?

**No.** Zero `RETRY:` lines in the log. §4.1's boundary model holds on a real 409-site,
5-page walk: because the loop only ever passes the last id of a page the API itself returned,
every cursor it sends is a page boundary and is honored. No change to the site-listing strategy
is needed, and `reproduce-pagination-bug.sh` does not need re-running.

## Q6 — did the loop ever see a short non-final page?

**No.** Cross-check:

```
$ terminus org:site:list 23c7208e-5f2a-4388-9fc4-5c3a038ef8b9 --format=json | jq length
409
```

The sweep reported `sites=409`. Four full pages of 100 plus a final page of 9 — the stop
condition (`len(page) < PAGE_LIMIT`) fired on the genuinely final page. D15's accepted exposure
(a short *non-final* page, which the detector cannot catch) did not materialize.

Note the organization grew from 408 to 409 between the bug report (2026-07-28, earlier) and this
sweep, which is incidentally a useful confirmation that the count is live rather than cached.

---

## Summary

All six questions are closed. The two that could have changed the design — Q5 (the cursor model)
and Q6 (short non-final pages) — both came back clean, so the API-plus-detector decision (D11)
stands and the site listing does not need to move to `terminus org:site:list`.

The one finding with downstream consequences is **Q1's repeated `dns_record`**: 2 of 31 rows
share a record with another row. Whoever runs the rewrite must de-duplicate on column 4.

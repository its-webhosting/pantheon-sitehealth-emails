# Resuming an interrupted `--all` run

A full `--all` run walks every site in the Pantheon organization and can take a long time. If it
dies partway through — a Terminus session blowup, a network failure, a crash, or a Ctrl-C —
`--resume-from SITE_NAME` lets you pick up where it stopped instead of starting over.

```bash
./pantheon-sitehealth-emails --date 20240731 --all --resume-from mysite-example --for-real
```

The site loop always processes sites in alphabetical order by site name, so "start at this site"
is well defined and reproducible as long as the organization's membership has not changed.
`--resume-from` is **inclusive**: the named site is processed, along with every site after it.

## Choosing SITE_NAME

Each site's report begins with a banner on the console:

```
  Pantheon site 214 of 507: mysite-example
```

Find the last such banner in the output of the interrupted run. That site may or may not have
finished, so resume **from that site** (not from the one after it) — it will simply be processed
again. Anything earlier in the alphabet is skipped entirely: no banner, no Pantheon calls, no
email.

On startup the resumed run confirms what it is doing:

```
=== Resuming from mysite-example (294 of 507 sites remaining)
```

The per-site banner still counts against the full organization size, so on a resumed run the
first site reads "Pantheon site 1 of 507".

## Which modes it works with

`--resume-from` only moves the loop's starting point, so it is available with any `--all` mode:
the full report run, `--update`, `--only-warn`, and `--import-older-metrics`. It requires `--all`
— using it with an explicit list of site names, or with no site selection at all, is an error:

```
--resume-from can only be used together with --all.
```

`--create-tables` never reaches the site loop, so combining it with `--resume-from` is also an
error rather than a silently ignored flag:

```
The --resume-from and --create-tables options are mutually exclusive.
```

Naming a site that is not in the organization is also a fatal error, raised before any site is
processed, so a typo can never quietly skip the entire run:

```
--resume-from: site 'mystie-example' was not found among the 507 sites for org ...
```

## Aborting mid-run

A run can also end deliberately, before the loop reaches the last site: an unrecoverable database
error (one that survives a single automatic retry) or a Ctrl-C now aborts the run on purpose
instead of dying with a traceback or silently discarding completed work. When that happens the run:

- writes `-notices.csv`/`-results.json`/`-run.json` for exactly the sites that finished (the site it was
  processing when it died is dropped from the results — that entry is written mid-gather and would
  otherwise look like a success; a Ctrl-C that lands *after* that site's report was already emailed
  is the one exception, since dropping it there would just make you re-send the same report);
- prints the exact command to continue, rebuilt from the original invocation so it carries the same
  flags (`--resume-from SITE_NAME` for an `--all` run — see above; a re-run command listing the
  remaining sites for an explicit-`SITE` run, since `--resume-from` requires `--all`); and
- exits 1 for a database failure, 130 for Ctrl-C.

**Any other** error that escapes the site loop — an SMTP failure on site 250 of 300, unexpected
Terminus JSON — gets the same flush and the same continue command, and is then re-raised with its
traceback (and, for a deliberate bail-out, its own exit code and message) intact. Nothing is
swallowed: `run.json`'s `reason` records which of the three it was (`"database"`, `"interrupted"`,
`"fatal"`).

See `CLAUDE.md`'s **Database** section for the mechanism (`db_retry`, `DatabaseUnavailableError`,
`abort_run()`, `finish_run()`).

## Summary artifacts and the overlap caveat

A full report run writes three summary files at the end, named for today's date:

| File | Contents |
|---|---|
| `YYYYMMDD-notices.csv` | one raw line per notice, per site |
| `YYYYMMDD-results.json` | **site-keyed and nothing else** — one entry per site that completed |
| `YYYYMMDD-run.json` | how the run itself went (see below) |

`YYYYMMDD-run.json` records `aborted_at`, `reason` (`null`, `"database"`, `"interrupted"` or
`"fatal"`), `sites_completed_this_run`, and the database-reconnect counters:
`db_reconnects_healed_this_run` / `reconnects_by_site` (a lost connection the automatic retry got
back) and `db_reconnect_failures_this_run` / `reconnect_failures_by_site` (one it did not — the
retry, or the rollback before it, failed too). The same two numbers are printed at the end of every
run as `Database reconnects: N healed, M failed`.

This metadata lives in its **own** file, not in `results.json`, because `results.json` is consumed
by iterating its keys as site names (`jq to_entries` in `monthly-report.txt`): a metadata key there
would silently show up as an extra "site" in the monthly stats.

Normally these files are written once, after the loop
completes — but the deliberate abort above also triggers this same write on its way out, so neither
a database failure nor a Ctrl-C leaves the run with *no* files at all. A resumed run's own files
would otherwise cover only the sites it processed: when `--resume-from` is given, the resumed run
instead **appends** its rows to the CSV, **merges** its entries into the results JSON, and nests
the earlier run's metadata under `previous` in `run.json`, so the combined files describe both runs.

An **aborted** run appends and merges too, whether or not it was resumed. Otherwise a run that dies
partway would truncate the files of a run that *completed* earlier the same day — destroying the
record of what was actually mailed. Only a run that reaches the end truncates.

Two consequences worth knowing:

- **Resume from at or after the point of interruption.** If you resume from a site *earlier* than
  where the previous run stopped, the CSV will contain duplicate rows for the overlapping sites
  (its raw lines are not de-duplicated). The same is true of a site that was interrupted after its
  report went out but before the run ended: its notices are recorded before the email is sent, so
  a re-run can duplicate those rows rather than lose them. The results JSON is keyed by site name,
  so it keeps one entry per site, with the resumed run's entry winning.
- **The console totals cover only the resumed run.** The "Email sent for N of M sites" line and
  the "Total savings" block at the end of the run are not persisted anywhere and are not
  accumulated across runs.

If the existing `YYYYMMDD-results.json` cannot be read or is not valid JSON, the resumed run
prints a warning and writes only its own results rather than failing at the very end of an
otherwise-complete run.

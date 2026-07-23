"""The run lifecycle: the run-scoped accumulators and the start/finish/abort epilogue.

Holds RunState (the one home for a run's accumulators, campaign I13), the --resume-from
pure helpers (ResumeSiteNotFoundError / sites_from_resume_point / merge_prior_results /
resume_point / option_strings_taking_a_value / resume_command / rerun_command), and the
two end-of-run entry points (finish_run, abort_run) plus abort_reason.

Moved from psh/_legacy.py at campaign increment I13 (CAMPAIGN.md section 3.1;
development/2026-07-23-mod-I13-lifecycle/SPEC.md).  The governing design for the abort/flush
path is development/2026-07-13-db-connection-resilience/SPEC.md, which the docstrings below
cite by bare section number.

Import direction (CAMPAIGN.md section 3.4; SPEC section 2.1 cycle proof).  The new top-level
edge is `script_context -> psh.lifecycle` (script_context.py imports RunState at the top of
the file).  `psh.db -> script_context` already exists (module-level).  So this module MUST
NOT import script_context, psh.db, or psh._legacy at MODULE level:

    script_context.py  ── imports RunState ──►  psh/lifecycle.py
          ▲                                           │
          │ (call time)          (call time)          │ (call time)
    psh/db.py  ◄──────────────────────────────────────┤
    psh/_legacy.py  ◄─────────────────────────────────┘

If psh.lifecycle imported psh.db at module level, the `import psh.db`-first order fails
sharply: psh.db (module level) -> script_context -> psh.lifecycle -> `from psh.db import
DatabaseUnavailableError` against a psh/db.py paused before the class exists -> ImportError at
startup.  Call-time imports (below, `# noqa: PLC0415`) dissolve every edge.  Module-level
imports here are stdlib + sqlalchemy.exc + rich only.
"""
import dataclasses
import datetime
import json
import os
import shlex
import signal
import sys

from rich.markup import escape
from rich.pretty import pprint
from sqlalchemy.exc import DBAPIError, SQLAlchemyError


@dataclasses.dataclass
class RunState:
    """Run-scoped accumulators (CAMPAIGN.md section 6, introduced at campaign I13).

    ONE instance per run, created by main() BEFORE invoke_hooks("setup") and bound to
    sc.run_state -- the shared, reset_sc-isolated namespace joining the cross-module
    writer (psh/db.py's db_retry, which reaches it via sc) and the readers
    (finish_run/abort_run, which take it as a parameter).  Widening this field set
    requires a CAMPAIGN.md section 6 amendment.
    """

    emails_sent: int = 0
    site_savings: list[dict] = dataclasses.field(default_factory=list)
    all_warnings: list[str] = dataclasses.field(default_factory=list)
    site_results: dict[str, dict] = dataclasses.field(default_factory=dict)
    # Reconnects HEALED by db_retry() -- the retry ran and succeeded -- attributed to the site that
    # caused them.  Counted only after the second attempt returns: counting the attempt instead would
    # let an aborted run report a reconnect it never actually made.
    db_reconnects_by_site: dict[str, int] = dataclasses.field(default_factory=dict)
    # Connection losses db_retry() could NOT heal, attributed the same way: the retry failed, or the
    # rollback before it did.  The counterpart of the dict above, and the reason it can be trusted --
    # every lost connection lands in exactly one of the two, so "0 healed" never means "nothing
    # happened".  Both are reported on the console and in {ymd}-run.json
    # (development/2026-07-13-db-connection-resilience/SPEC.md 3.6).  Written by psh.db.db_retry;
    # read by finish_run/abort_run; absorbed into RunState at campaign I13.
    db_reconnect_failures_by_site: dict[str, int] = dataclasses.field(default_factory=dict)

    def record_site_notices(self, notices: list[dict], contacts: str) -> None:
        """Append a completed site's notice csv rows, contacts inserted at field 2.

        BEFORE the send, not after: a Ctrl-C between send_message() and this loop -- a window
        that includes smtp_connection.quit(), a network round-trip -- used to set
        site_emailed=True and so advance the resume point PAST this site, and its notices
        then never reached {ymd}-notices.csv on any run, even though its owner had the email
        describing them.  Appending first downgrades that to at worst a duplicate CSV row on
        a re-run, which docs/resuming-interrupted-runs.md already documents as tolerable.
        """
        for n in notices:
            fields = n["csv"].split(",")
            fields.insert(1, contacts)
            self.all_warnings.append(",".join(fields))


class ResumeSiteNotFoundError(Exception):
    """--resume-from named a site not present in the org site list."""


def sites_from_resume_point(sorted_site_names: list[str], resume_from: str) -> list[str]:
    """
    Return the suffix of sorted_site_names starting at resume_from (inclusive).

    sorted_site_names is the already-sorted list of org site names; resume_from is the
    --resume-from value.  Raises ResumeSiteNotFoundError if resume_from is absent, so that a
    typo becomes a fatal error rather than degrading into "silently skip every site".
    """
    try:
        i = sorted_site_names.index(resume_from)
    except ValueError:
        raise ResumeSiteNotFoundError(resume_from) from None
    return sorted_site_names[i:]


def merge_prior_results(path: str, new_results: dict, *, what: str = "results") -> dict:
    """
    Return the JSON dict already at path merged with new_results, which wins on key collision
    (a site processed by the resumed run supersedes any earlier entry for it).

    A missing file yields new_results alone.  A malformed existing file warns loudly and yields
    new_results alone, rather than crashing at the very end of an otherwise-complete run.
    "Malformed" covers valid JSON that is not an object (a hand-edited `[]` or `null`) as well as
    unparseable or unreadable content: both would otherwise blow up on merged.update() below.

    `what` names, in the warning, the kind of content being merged/read -- this helper reads
    both {ymd}-results.json ("results") and {ymd}-run.json ("run metadata"; see finish_run()),
    and the warning must name whichever file actually failed to read.
    """
    import script_context as sc  # noqa: PLC0415 -- call-time import; see the module docstring

    merged = {}
    if os.path.exists(path):  # noqa: PTH110 -- verbatim artifact-path IO moved at I13; pathlib migration is I14 de-grandfathering
        try:
            with open(path, encoding="utf-8") as f:  # noqa: PTH123 -- verbatim artifact-path IO moved at I13
                merged = json.load(f)
            if not isinstance(merged, dict):
                raise ValueError(f"expected a JSON object, found {type(merged).__name__}")  # noqa: TRY004, TRY301 -- moved verbatim; the ValueError (not TypeError) is deliberate, caught together with JSONDecodeError by the except below, and inlining the raise is the point
        # json.JSONDecodeError is a ValueError, so this catches an unparseable file too.
        except (ValueError, OSError) as e:
            sc.console.print(
                f":warning: [bold yellow]could not read existing {path} "
                f"({escape(str(e))}); writing only this run's {what}."
            )
            merged = {}
    merged.update(new_results)
    return merged


def finish_run(  # noqa: C901, PLR0913, PLR0915 -- moved verbatim (CAMPAIGN.md section 3.1: moves get no algorithmic redesign); the epilogue is one straight-line body, the 6-arg signature is the abort_run/main() call sites
    db_session,
    db_engine,
    site_count: int,
    run_state: RunState,
    *,
    aborted_at: str | None = None,
    reason: str | None = None,
) -> None:
    """Close out a run: release the DB, print the totals, write the summary artifacts.

    Called from two places -- normal completion, and abort_run() (SPEC 3.5).  One epilogue with
    two callers is what makes an aborted run's artifacts identical in shape to a completed run's.

    `aborted_at` / `reason` are None on a normal run.  When set, the totals say so instead of
    claiming success, and both are recorded in {ymd}-run.json so the outcome outlives the terminal
    (SPEC 3.6).

    The run metadata gets its OWN artifact rather than a `_run` key inside {ymd}-results.json:
    results.json is consumed (monthly-report.txt) with `jq to_entries`, which enumerates every key
    as a site -- a metadata key there silently becomes a bogus site row in the operator's monthly
    stats.  {ymd}-results.json is site-keyed and nothing else.
    """
    import script_context as sc  # noqa: PLC0415 -- call-time import; see the module docstring

    # Run-level seam (CAMPAIGN.md section 4): fire before ANY teardown or artifact write so
    # future hooks see the run intact.  Receives the run's RunState (since campaign I13).
    sc.invoke_hooks("run_finish", run_state)
    # Two separate try blocks, deliberately: a failing close() must not skip dispose().  The
    # catches are narrow -- (SQLAlchemyError, OSError), not Exception -- so a TypeError from a
    # future edit still crashes loudly.  Neither failure may cost the operator the artifacts:
    # finish_run() is called from the abort path, on a session whose database is already sick
    # (SPEC 3.3.3).
    # escape() on every interpolated exception, here and everywhere else this file prints one:
    # rich parses `[parameters: (...)]` -- a lowercase-initial bracket, exactly what SQLAlchemy
    # appends to a DBAPIError -- as a style tag and DELETES it, and an unmatched `[/x]` raises
    # MarkupError from inside the very handler that exists so nothing is lost.
    try:
        db_session.close()
    except (SQLAlchemyError, OSError) as e:
        sc.console.print(
            f":warning: [yellow]Could not close the database session: {escape(str(e))}"
        )
    try:
        db_engine.dispose()
    except (SQLAlchemyError, OSError) as e:
        sc.console.print(
            f":warning: [yellow]Could not dispose the database engine: {escape(str(e))}"
        )

    reconnects = sum(run_state.db_reconnects_by_site.values())
    reconnect_failures = sum(run_state.db_reconnect_failures_by_site.values())

    # --update and --import-older-metrics `continue` before a report is ever built, so they have no
    # notices and no results to write.  Writing anyway would open {ymd}-notices.csv in "w" mode with
    # an empty list and overwrite {ymd}-results.json with an empty object -- DESTROYING the
    # artifacts of a report run made earlier the same day.  Print the totals, write nothing.
    write_artifacts = not (sc.options.update or sc.options.import_older_metrics)

    if sc.options.all:
        # On a resumed run these two on-disk summaries accumulate across the original and the
        # resumed run instead of being truncated to just the resumed subset.  (The console-only
        # totals printed here and below still cover only this run's sites.)
        resuming = sc.options.resume_from is not None
        # An ABORTED run accumulates too, for the same reason it flushes at all: the artifacts on
        # disk may belong to an earlier, COMPLETED run of the same day (the monthly --all --for-real
        # run in the morning, a Ctrl-C'd dry run in the afternoon).  Truncating them would destroy
        # a good run's record to make room for a partial one's.  Only a run that reaches the end
        # legitimately truncates; the worst case here is duplicate rows on a re-run, which
        # docs/resuming-interrupted-runs.md already documents as tolerable.
        accumulating = resuming or reason is not None
        if reason is None:
            sc.console.print(
                f"\n[bold green]Email sent for {run_state.emails_sent} of {site_count} sites"
                + (f" (resumed from {sc.options.resume_from}).\n" if resuming else ".\n")
            )
        elif aborted_at is None:
            # An interrupt landing before the first site's body ran passes aborted_at=None --
            # there is no "at X" to report (SPEC 3.5.4).
            sc.console.print(
                f"\n[bold yellow]Email sent for {run_state.emails_sent} sites before aborting.\n"
            )
        else:
            sc.console.print(
                f"\n[bold yellow]Email sent for {run_state.emails_sent} sites before aborting at "
                f"{aborted_at}.\n"
            )
        if write_artifacts:
            ymd = datetime.datetime.today().strftime("%Y%m%d")  # noqa: DTZ002 -- moved verbatim; the naive local date names the artifact files ({ymd}-*.json), and attaching a tzinfo risks an off-by-one-day shift at midnight UTC (a behavior change a move may not make)
            with open(  # noqa: PTH123 -- verbatim artifact write; the plain open() keeps bytes-on-disk identical
                f"{ymd}-notices.csv", "a" if accumulating else "w", encoding="utf-8"
            ) as f:
                for n in run_state.all_warnings:  # noqa: FURB122 -- moved verbatim; per-row write, writelines is I14 cleanup
                    f.write(n + "\n")

            results_path = f"{ymd}-results.json"
            # merge_prior_results() rather than a hand-rolled {**prior, **site_results}: it owns
            # the "new wins" rule AND the malformed-prior-file handling, and that logic must live
            # in one place.
            payload = (
                merge_prior_results(results_path, run_state.site_results)
                if accumulating
                else run_state.site_results
            )
            # A results.json written by an older version carries a "_run" metadata key, which is
            # exactly the bogus-site-row bug this split exists to remove.  Drop it on the way
            # through; nothing writes it any more -- but keep it: if this run is the FIRST since
            # the upgrade (no {ymd}-run.json yet), this legacy key is the ONLY copy of the prior
            # run's reconnect evidence, and dropping it here would silently lose the exact thing
            # "previous" exists to preserve.  Migrated into run_meta["previous"] below.
            legacy_run = payload.pop("_run", None)
            with open(results_path, "w", encoding="utf-8") as f:  # noqa: PTH123 -- verbatim artifact write
                json.dump(payload, f, indent=4)

            run_path = f"{ymd}-run.json"
            run_json_existed = os.path.exists(run_path)  # noqa: PTH110 -- verbatim artifact-path IO moved at I13
            # Read the prior metadata first so this run's block can NEST the earlier run's under
            # "previous" -- an aborted run's block carries the reconnect evidence that prompted
            # the resume in the first place.  merge_prior_results() is just the reader here (with
            # its malformed-file handling); the file is then overwritten, not merged, because the
            # nesting IS the accumulation.
            prior_run = (
                merge_prior_results(run_path, {}, what="run metadata") if accumulating else {}
            )
            # "this_run" in the names, not "processed": the artifacts on disk describe the original
            # run plus this one, while these numbers describe only this one.  (An --only-warn run
            # emails nobody, so this counts sites processed, not sites emailed.)
            run_meta = {
                "aborted_at": aborted_at,
                "reason": reason,
                "sites_completed_this_run": len(run_state.site_results),
                # Healed vs. failed, never one ambiguous "reconnects" number: a run that aborted
                # on the database healed NOTHING, and saying otherwise misleads the operator about
                # the one thing this counter exists to answer.
                "db_reconnects_healed_this_run": reconnects,
                "db_reconnect_failures_this_run": reconnect_failures,
                "reconnects_by_site": dict(run_state.db_reconnects_by_site),
                "reconnect_failures_by_site": dict(run_state.db_reconnect_failures_by_site),
            }
            if prior_run:
                run_meta["previous"] = prior_run
            elif legacy_run is not None and not run_json_existed:
                # First run since the upgrade: {ymd}-run.json didn't exist yet, so the only
                # record of the prior run's reconnect evidence was the "_run" key we just popped
                # out of results.json above.  Carry it forward instead of discarding it.
                run_meta["previous"] = legacy_run
            with open(run_path, "w", encoding="utf-8") as f:  # noqa: PTH123 -- verbatim artifact write
                json.dump(run_meta, f, indent=4)
    else:
        for n in run_state.all_warnings:
            sc.console.print(n)
        pprint(run_state.site_results)

    sc.console.print(f"\n[bold green]Site savings:\n")  # noqa: F541 -- moved verbatim; the f-prefix is byte-preserved from _legacy.py
    pprint(run_state.site_savings)
    sc.console.print(f"Sites with savings: {len(run_state.site_savings)}")
    sc.console.print(
        f"Total savings: ${sum([s['savings'] for s in run_state.site_savings]):,.2f}"
    )
    # Both numbers, always: "Database reconnects: 1" used to mean "one retry was attempted",
    # printed identically whether the connection came back or the run died of it.
    sc.console.print(
        f"Database reconnects: {reconnects} healed, {reconnect_failures} failed"
    )

    sc.debug("Done!")


def resume_point(site_names: list, site_name: str, emailed: bool) -> str | None:  # noqa: FBT001 -- moved verbatim; the bool positional is pinned by the abort_run call site and resume_point tests
    """Where a resumed run must start.

    Normally the aborting site itself: --resume-from is inclusive, so it is redone from the top.
    But if the interrupt landed AFTER that site's report was emailed, restarting there would send
    its owner a SECOND copy of the same monthly report, so the resume point is the next site.
    Returns None when the emailed site was the last one (nothing remains).  See SPEC 3.5.3.
    """
    if not emailed:
        return site_name
    i = site_names.index(site_name)
    return site_names[i + 1] if i + 1 < len(site_names) else None


def option_strings_taking_a_value() -> set[str]:
    """Every option string that consumes a following argument, derived from the parser itself.

    Derived rather than hardcoded: a hardcoded list rots the first time an option is added, and
    rerun_command() would then mistake that option's VALUE for a site name and delete it.  Same
    denylist-by-omission failure that SPEC 3.5.1 exists to prevent.
    """
    # I14 obligation: replace with a module-level `from psh.cli import build_arg_parser` when the
    # argparse pair relocates out of psh/_legacy.py (D-i13-1/D-i13-3); the D-i6-2 escape_url bridge
    # precedent.
    from psh._legacy import (  # noqa: PLC0415 -- call-time bridge; see the module docstring
        build_arg_parser,
    )

    return {
        opt
        for action in build_arg_parser()._actions  # noqa: SLF001 -- argparse exposes value-taking options only via the private _actions list
        if action.option_strings and action.nargs != 0
        for opt in action.option_strings
    }


def resume_command(argv: list, site_name: str) -> str:
    """Rebuild an --all invocation with --resume-from <site_name>.

    Built from argv rather than from sc.options on purpose.  Re-enumerating flags would be a
    denylist by omission -- the first flag added next year would silently vanish from the hint, and
    an operator pasting the command would get a run that does something DIFFERENT from the one that
    died (e.g. a full report-and-send instead of an --import-older-metrics backfill).
    allow_abbrev=False guarantees only these two spellings exist.  See SPEC 3.5.1.
    """
    args = []
    skip_next = False
    for arg in argv:
        if skip_next:
            skip_next = False
            continue
        if arg == "--resume-from":
            skip_next = True  # drop its value too
            continue
        if arg.startswith("--resume-from="):
            continue
        args.append(arg)
    return shlex.join(args + ["--resume-from", site_name])  # noqa: RUF005 -- moved verbatim; list concat is byte-preserved from _legacy.py


def rerun_command(argv: list, original_sites: list, remaining_sites: list) -> str:
    """Rebuild an explicit-SITE invocation with only the sites that were not processed.

    NOT --resume-from: that flag requires --all (main() exits otherwise), so printing it here would
    hand the operator a command that fails the moment they paste it.

    Only POSITIONAL site names are dropped.  A site name sitting in an option's value slot
    (`-c its-wws-test1`) must survive, or `-c` swallows the next token and the command is mangled.
    See SPEC 3.5.1.
    """
    value_opts = option_strings_taking_a_value()
    args = []
    previous = None
    for arg in argv:
        is_option_value = previous in value_opts
        if not is_option_value and arg in original_sites:
            previous = arg
            continue  # a site positional: dropped here, re-appended below if still pending
        args.append(arg)
        previous = arg
    return shlex.join(args + list(remaining_sites))


def abort_reason(error: BaseException) -> str:
    """Classify an exception escaping the site loop into an abort reason.

    "database" -> exit 1;  "interrupted" -> exit 130;  "fatal" -> re-raise the original error.

    A DBAPIError is a database abort only when it is one db_retry() would have retried
    (db_retryable() is the single source of truth for that -- SPEC 2.2); an IntegrityError or
    other non-retryable DBAPIError is a data bug and belongs on the fatal path, with its
    traceback.
    """
    from psh.db import (  # noqa: PLC0415 -- call-time import; see the module docstring
        DatabaseUnavailableError,
        db_retryable,
    )

    if isinstance(error, DatabaseUnavailableError) or (
        isinstance(error, DBAPIError) and db_retryable(error)
    ):
        # A database failure raised OUTSIDE a unit of work (a future code path, an expired-row
        # lazy load) must still land on the named abort path (SPEC 3.3.3).
        return "database"
    elif isinstance(error, KeyboardInterrupt):  # noqa: RET505 -- moved verbatim; the if/elif/else classifier is byte-preserved from _legacy.py
        return "interrupted"
    else:
        return "fatal"


def abort_run(  # noqa: C901, PLR0913, PLR0912 -- moved verbatim (CAMPAIGN.md section 3.1: moves get no algorithmic redesign); the branches are the SPEC 3.5 exit cases and the 9-arg signature is the main() call site
    db_session,
    db_engine,
    site_name: str | None,
    reason: str,
    error: BaseException,
    *,
    emailed: bool,
    site_names: list[str],
    site_count: int,
    run_state: RunState,
) -> None:
    """Report an aborted run, flush its artifacts, print how to finish it, and exit.  Never returns.

    `reason` is "database" (exit 1), "interrupted" (exit 130, the conventional SIGINT code), or
    "fatal" -- anything else that escaped the site loop (a SystemExit("Bailing out."), an SMTP
    hiccup on site 250 of 300, a KeyError from changed terminus JSON).  A fatal RE-RAISES the
    original exception after the flush, so its traceback -- or a SystemExit's own code and message
    -- reaches the operator unchanged.  Nothing is swallowed.

    This is the ONE flush path, so every exit has the same invariants: the aborting site is popped
    from the results unless its report was already emailed, and a runnable continuation command is
    printed.  `emailed` says whether that report went out; every caller passes the real value,
    because a report that has gone out must never be re-sent by the resumed run.

    This function runs when things are ALREADY broken, so it must not be able to crash: every input
    it slices on is guarded (SPEC 3.5.4).
    """
    import script_context as sc  # noqa: PLC0415 -- call-time import; see the module docstring

    # A second Ctrl-C must not truncate the flush -- losing the artifacts is exactly the failure
    # this function exists to prevent.  The flush is sub-second (SPEC 3.5).
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    try:
        db_session.rollback()
    except (SQLAlchemyError, OSError) as e:  # the database is already sick; see finish_run()
        sc.console.print(
            f":warning: [yellow]Could not roll back the database session: {escape(str(e))}"
        )

    if not emailed:
        # site_results[site] is written DURING the gather, ~1400 lines before the failure point --
        # so the aborting site is already in there, while its notices (appended at the END of a
        # successful site) are not.  Drop it, so the artifacts contain exactly the sites that
        # completed end-to-end.  --resume-from is inclusive, so the resumed run redoes this site
        # and rewrites the entry.  See SPEC 3.5.2.
        run_state.site_results.pop(site_name, None)  # pyright: ignore[reportArgumentType, reportCallIssue] -- pop(None, None) is a harmless miss (None is never a results key); site_name is None only before any site ran
        # site_savings is appended to just as early, so the same rule applies to it: leaving the
        # aborting site in would make the epilogue's "Sites with savings" / "Total savings" count
        # the very site it is telling the operator to redo -- and the resumed run would count it
        # again.  A list of dicts, not a dict, hence the filter rather than a pop.
        run_state.site_savings[:] = [s for s in run_state.site_savings if s.get("site") != site_name]

    # escape() every interpolated exception.  A SQLAlchemy DBAPIError's message ends with
    # `[SQL: ...]` and `[parameters: (...)]`; rich's markup parser reads the lowercase-initial
    # `[parameters: ...]` as a style tag and DELETES it from the output -- silently dropping the
    # bound values from the very message the operator has to debug.  An unmatched `[/...]` in an
    # error is worse: it raises MarkupError HERE, after SIGINT was ignored and BEFORE finish_run(),
    # losing every artifact this function exists to save.  The [bold] markup around the site name
    # is ours and stays live.
    if reason == "database":
        if site_name is None:
            # Reached before any site's body ran -- there is no "processing X" to name, and
            # interpolating site_name here would render the literal word "None" (SPEC 3.5.4).
            sc.console.print(
                f"\n:exclamation: [bold red]FATAL: a database operation failed and could not "
                f"be retried before any site was processed:\n{escape(str(error))}"
            )
        else:
            sc.console.print(
                f"\n:exclamation: [bold red]FATAL: a database operation failed and could not be "
                f"retried.  Aborting while processing [bold]{escape(site_name)}[/bold]:\n"
                f"{escape(str(error))}"
            )
    elif reason == "fatal":
        # The traceback (or the SystemExit message) follows when we re-raise below; this line is
        # what ties it to the site that was in flight and tells the operator the artifacts are safe.
        detail = escape(f"{type(error).__name__}: {error}")
        if site_name is None:
            sc.console.print(
                f"\n:exclamation: [bold red]FATAL: the run failed before any site was "
                f"processed:\n{detail}"
            )
        else:
            sc.console.print(
                f"\n:exclamation: [bold red]FATAL: aborting while processing "
                f"[bold]{escape(site_name)}[/bold]:\n{detail}"
            )
    elif site_name is None:
        sc.console.print("\n:hand: [bold yellow]Interrupted before any site was processed.")
    else:
        sc.console.print(
            f"\n:hand: [bold yellow]Interrupted while processing [bold]{escape(site_name)}[/bold]."
            + (
                "  Its report had already been sent, so resuming will start at the next site."
                if emailed
                else ""
            )
        )

    finish_run(
        db_session,
        db_engine,
        site_count,
        run_state,
        aborted_at=site_name,
        reason=reason,
    )

    # Everything below is guarded: an interrupt can land before the first site's body runs
    # (site_name is None), or -- on a non---all run, which iterates every org site and `continue`s
    # the ones it was not asked for -- on a site the operator never requested.  Slicing on either
    # would raise INSIDE this handler, after SIGINT was ignored and the artifacts were written, and
    # the operator would get a traceback instead of a command.  See SPEC 3.5.4.
    resume_site = (
        resume_point(site_names, site_name, emailed)
        if site_name in site_names
        else None
    )

    if resume_site is None and emailed:
        sc.console.print("\n[bold]Every site was processed; nothing remains to resume.\n")
    elif sc.options.all:
        if site_name is None:
            # The interrupt landed before any site was processed -- there is no "sites before X"
            # to report, and {resume_site or site_name} would render as the literal word "None".
            # soft_wrap=True on EVERY print that emits a copy-pasteable command.  sc.console is a
            # bare Console(), so on a non-tty -- cron, nohup, a redirect, i.e. exactly how a
            # multi-hour --all run is launched -- rich falls back to width 80 and puts a REAL
            # newline in the output.  These commands are longer than that, and bash treats the
            # newline as a command separator: the operator pastes it and the first line re-parses
            # as a complete `--all --for-real` run with no --resume-from, re-mailing every owner
            # who already got their report.
            sc.console.print(
                "\n[bold]No sites were processed.  Continue this run with:\n\n"
                f"    {shlex.join(sys.argv)}\n",
                soft_wrap=True,
            )
        else:
            # resume_site is necessarily set here: an --all run only ever aborts on a site the
            # loop is iterating, so site_name is in site_names and resume_point() returned None
            # only if the emailed site was the last one -- which the "nothing remains" branch
            # above already consumed.  There is deliberately NO shlex.join(sys.argv) fallback: a
            # command without --resume-from would re-process and, on --for-real, re-mail every
            # owner who already has their report.
            sc.console.print(
                f"\n[bold]The sites before {resume_site} were processed and their "
                "results written.  Continue this run with:\n\n"
                f"    {resume_command(sys.argv, resume_site)}\n",  # pyright: ignore[reportArgumentType] -- resume_site is necessarily str in this else-branch (an --all run only aborts on a site it is iterating; see the comment above)
                soft_wrap=True,  # never wrap a command; see above
            )
    else:
        # --resume-from requires --all, so an explicit-SITE run gets a re-run command listing the
        # sites it never reached.  The site loop iterates every ORG site (site_names) and `continue`s
        # the ones not requested, so slicing the requested list at resume_site (an org site name) is
        # wrong -- it is frequently not even a member of the requested list.  Instead, compute what
        # the loop actually walked past in ORG order and drop that from the requested list: this is
        # correct whether or not the aborting site was requested, and whether or not it was emailed.
        if site_name in site_names:
            i = site_names.index(site_name) + (1 if emailed else 0)
            done = set(site_names[:i])  # every org site the loop already walked past
            remaining = [s for s in sorted(sc.options.sites) if s not in done]
        else:
            # site_name is not a known org site -- in practice this means None (the interrupt
            # landed before any site was processed).  Kept general, not assumed-None-only: this
            # handler must not crash on any input (SPEC 3.5.4), and the guard above this whole
            # if/elif/else already treats "not in site_names" as the general case, not a
            # None-only one.
            remaining = sorted(sc.options.sites)

        # The org list being exhausted (resume_site is None and emailed, above) is the --all
        # check for "nothing remains"; here the equivalent signal is an empty explicit-SITE
        # remaining list -- e.g. the requested SITE was the last one processed before the abort.
        if not remaining:
            sc.console.print("\n[bold]Every site was processed; nothing remains to resume.\n")
        else:
            sc.console.print(
                "\n[bold]Continue this run with:\n\n"
                f"    {rerun_command(sys.argv, sc.options.sites, remaining)}\n",
                soft_wrap=True,  # never wrap a command; see above
            )

    if reason == "fatal":
        # Re-raise, do not exit: a SystemExit keeps its own code and message, and anything else
        # keeps its traceback.  The flush above is all this path adds.
        raise error

    sys.exit(1 if reason == "database" else 130)

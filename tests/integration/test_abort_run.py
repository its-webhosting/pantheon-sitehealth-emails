"""The abort path: flush the artifacts, drop the failed site, print a RUNNABLE command, exit
nonzero.  In-process, because the subprocess safety interlock bans --all (CLAUDE.md).

See development/2026-07-13-db-connection-resilience/SPEC.md sections 3.5.1-3.5.4.
"""

import re
import signal

import pytest

import script_context as sc
from helpers.dnsfake import recording_console

SITE_NAMES = ["its-wws-test1", "its-wws-test2", "its-wws-test3"]


class FakeSession:
    def rollback(self):
        pass

    def close(self):
        pass


class FakeEngine:
    def dispose(self):
        pass


def abort(
    psh, monkeypatch, reset_sc, argv, reason, error, *,
    emailed=False, site_results=None, site_savings=None, site_name="its-wws-test2",
    expect=SystemExit, width=200,
):
    console = recording_console(monkeypatch, reset_sc, width=width)
    reset_sc.options = psh.parse_args(argv[1:])
    monkeypatch.setattr(psh.sys, "argv", argv)
    monkeypatch.setattr(sc, "db_reconnects_by_site", {})
    monkeypatch.setattr(sc, "db_reconnect_failures_by_site", {})

    # abort_run() sets SIGINT to SIG_IGN, which is PROCESS-GLOBAL and restored by no fixture:
    # without this patch, the rest of the pytest session would silently ignore Ctrl-C
    # (SPEC 5, harness rule 2).
    signals_set = []
    monkeypatch.setattr(psh.signal, "signal", lambda sig, handler: signals_set.append((sig, handler)))

    captured = {}

    def fake_finish_run(
        _session, _engine, _site_count, _emails_sent, _warnings, results, savings, *_a, **kw
    ):
        captured.update(kw)
        captured["site_results"] = results
        captured["site_savings"] = savings
        captured["ran"] = True

    monkeypatch.setattr(psh, "finish_run", fake_finish_run)
    with pytest.raises(expect) as excinfo:
        psh.abort_run(
            FakeSession(), FakeEngine(), site_name, reason, error,
            emailed=emailed, site_names=SITE_NAMES,
            site_count=10, emails_sent=4, all_warnings=[],
            site_results=site_results if site_results is not None else {},
            site_savings=site_savings if site_savings is not None else [],
        )
    assert (signal.SIGINT, signal.SIG_IGN) in signals_set  # the flush is protected
    captured["raised"] = excinfo.value          # the fatal path re-raises rather than exiting
    return console, captured, getattr(excinfo.value, "code", None)


@pytest.mark.integration
def test_database_abort_flushes_and_prints_a_resume_command(psh, monkeypatch, reset_sc):
    argv = ["./pantheon-sitehealth-emails", "--date", "2026-03-31", "--all", "--only-warn"]
    console, captured, code = abort(
        psh, monkeypatch, reset_sc, argv, "database",
        psh.DatabaseUnavailableError("loading traffic rows: (2013, 'Lost connection')"),
    )
    assert code == 1
    assert captured["ran"] is True                  # artifacts flushed BEFORE exiting
    assert captured["aborted_at"] == "its-wws-test2"
    output = console.export_text()
    assert "--resume-from its-wws-test2" in output
    assert "--only-warn" in output                  # the run's real flags survive (SPEC 3.5.1)


@pytest.mark.integration
def test_abort_drops_the_failed_site_from_the_results(psh, monkeypatch, reset_sc):
    # site_results[site] is written DURING the gather, long before the crash -- so without this
    # pop, results.json would ship the failed site as though it had succeeded, with no matching
    # notices (SPEC 3.5.2).
    argv = ["./pantheon-sitehealth-emails", "--date", "2026-03-31", "--all"]
    _console, captured, _code = abort(
        psh, monkeypatch, reset_sc, argv, "database", psh.DatabaseUnavailableError("boom"),
        site_results={
            "its-wws-test1": {"framework": "wordpress"},
            "its-wws-test2": {"framework": "wordpress"},  # the site that died
        },
    )
    assert list(captured["site_results"].keys()) == ["its-wws-test1"]


def savings(*sites):
    return [{"site": s, "savings": 100.0, "current_plan": "P", "recommended_plan": "B"}
            for s in sites]


@pytest.mark.integration
def test_abort_drops_the_failed_site_from_the_savings(psh, monkeypatch, reset_sc):
    # site_savings.append() happens well before the send, like site_results -- so without the same
    # drop, the epilogue's "Sites with savings" / "Total savings" would count the very site the
    # abort is telling the operator to redo, and the resumed run would count it AGAIN.
    argv = ["./pantheon-sitehealth-emails", "--date", "2026-03-31", "--all"]
    _console, captured, _code = abort(
        psh, monkeypatch, reset_sc, argv, "database", psh.DatabaseUnavailableError("boom"),
        site_savings=savings("its-wws-test1", "its-wws-test2"),  # test2 is the site that died
    )
    assert [s["site"] for s in captured["site_savings"]] == ["its-wws-test1"]


@pytest.mark.integration
def test_abort_keeps_the_savings_of_a_site_whose_report_was_emailed(psh, monkeypatch, reset_sc):
    # Same rule as site_results: an emailed site really did complete, so its savings stay counted.
    argv = ["./pantheon-sitehealth-emails", "--date", "2026-03-31", "--all"]
    _console, captured, _code = abort(
        psh, monkeypatch, reset_sc, argv, "interrupted", KeyboardInterrupt(),
        emailed=True,
        site_savings=savings("its-wws-test1", "its-wws-test2"),
    )
    assert [s["site"] for s in captured["site_savings"]] == ["its-wws-test1", "its-wws-test2"]


@pytest.mark.integration
def test_ctrl_c_flushes_artifacts_and_exits_130(psh, monkeypatch, reset_sc):
    # Prime Directive #7: a run is not atomic.  Before this, Ctrl-C at hour two lost every
    # artifact of the run -- while a DB failure at hour two kept them.
    argv = ["./pantheon-sitehealth-emails", "--date", "2026-03-31", "--all"]
    console, captured, code = abort(
        psh, monkeypatch, reset_sc, argv, "interrupted", KeyboardInterrupt(),
    )
    assert code == 130                             # conventional SIGINT exit code
    assert captured["ran"] is True
    assert "--resume-from its-wws-test2" in console.export_text()


@pytest.mark.integration
def test_ctrl_c_after_the_email_was_sent_resumes_at_the_next_site(psh, monkeypatch, reset_sc):
    # The report for its-wws-test2 was already DELIVERED when the interrupt landed.  Resuming
    # there (--resume-from is inclusive) would send that owner a second copy of the same monthly
    # report -- a silent, outward-facing failure.  Resume at the next site instead, and KEEP the
    # site's results entry, because it really did complete (SPEC 3.5.3).
    argv = ["./pantheon-sitehealth-emails", "--date", "2026-03-31", "--all"]
    console, captured, code = abort(
        psh, monkeypatch, reset_sc, argv, "interrupted", KeyboardInterrupt(),
        emailed=True,
        site_results={"its-wws-test2": {"framework": "wordpress"}},
    )
    assert code == 130
    assert "--resume-from its-wws-test3" in console.export_text()   # the NEXT site
    assert "its-wws-test2" in captured["site_results"]              # entry kept, not popped


@pytest.mark.integration
def test_database_abort_after_the_email_was_sent_resumes_at_the_next_site(
    psh, monkeypatch, reset_sc,
):
    # The database handler in main() used to hardcode emailed=False ("the DB abort fires long
    # before the send") while deliberately catching failures raised OUTSIDE a unit of work -- i.e.
    # anywhere, including after the send.  Should a DB touch ever land after the send, the resumed
    # run would mail that owner a DUPLICATE monthly report.  abort_run() must honor `emailed` for
    # every reason, not just an interrupt.
    argv = ["./pantheon-sitehealth-emails", "--date", "2026-03-31", "--all"]
    console, captured, code = abort(
        psh, monkeypatch, reset_sc, argv, "database", psh.DatabaseUnavailableError("boom"),
        emailed=True,
        site_results={"its-wws-test2": {"framework": "wordpress"}},
    )
    assert code == 1
    assert "--resume-from its-wws-test3" in console.export_text()   # the NEXT site
    assert "its-wws-test2" in captured["site_results"]              # its report really did go out


@pytest.mark.integration
def test_explicit_site_abort_prints_a_rerun_command_not_resume_from(psh, monkeypatch, reset_sc):
    argv = [
        "./pantheon-sitehealth-emails", "--date", "2026-03-31",
        "its-wws-test1", "its-wws-test2", "its-wws-test3",
    ]
    console, _captured, code = abort(
        psh, monkeypatch, reset_sc, argv, "database", psh.DatabaseUnavailableError("boom"),
    )
    assert code == 1
    output = console.export_text()
    assert "--resume-from" not in output           # it requires --all; would fail when pasted
    assert "its-wws-test2 its-wws-test3" in output # the sites not yet processed


@pytest.mark.integration
def test_explicit_site_abort_with_nothing_remaining_prints_no_rerun_command(
    psh, monkeypatch, reset_sc,
):
    # Org is [test1, test2, test3]; the operator only requested test1.  The abort lands AFTER
    # test1's report was emailed, so the "nothing remains" guard (which only tests exhaustion of
    # the ORG list, i.e. --all) does not fire, and the old code fell into the explicit-SITE branch
    # with an empty `remaining` -- printing a bare "--date ... " command with no sites and no
    # --all, which main() rejects the moment it's pasted.
    argv = ["./pantheon-sitehealth-emails", "--date", "2026-03-31", "its-wws-test1"]
    console, _captured, code = abort(
        psh, monkeypatch, reset_sc, argv, "interrupted", KeyboardInterrupt(),
        emailed=True, site_name="its-wws-test1",
        site_results={"its-wws-test1": {"framework": "wordpress"}},
    )
    assert code == 130
    output = console.export_text()
    assert "Every site was processed; nothing remains to resume" in output
    assert "Continue this run with" not in output  # no re-run command line at all


@pytest.mark.integration
def test_abort_on_an_unrequested_site_does_not_crash(psh, monkeypatch, reset_sc):
    # A non---all run iterates EVERY org site and `continue`s the unrequested ones, so a Ctrl-C
    # can land on a site the operator never asked for.  Slicing the requested list at that name
    # would raise ResumeSiteNotFoundError -- inside the abort handler, after SIGINT was ignored
    # and the artifacts were flushed.  The operator would get a traceback instead of a command
    # (SPEC 3.5.4).
    argv = ["./pantheon-sitehealth-emails", "--date", "2026-03-31", "its-wws-test9"]
    console, _captured, code = abort(
        psh, monkeypatch, reset_sc, argv, "interrupted", KeyboardInterrupt(),
    )
    assert code == 130
    # ONE export_text() call: rich's export_text(clear=True) is the default, so a second call
    # would come back empty and silently pass any `not in` assertion made against it.
    output = console.export_text()
    assert "Traceback" not in output
    assert "its-wws-test9" in output  # re-run what was actually requested


@pytest.mark.integration
def test_all_abort_before_any_site_does_not_say_none(psh, monkeypatch, reset_sc):
    # site_name is None when the interrupt lands before the first site's body runs.  The old
    # message interpolated `resume_site or site_name` unconditionally, which rendered the literal
    # word "None" for the operator to paste nowhere.
    argv = ["./pantheon-sitehealth-emails", "--date", "2026-03-31", "--all"]
    console, _captured, code = abort(
        psh, monkeypatch, reset_sc, argv, "interrupted", KeyboardInterrupt(),
        site_name=None,
    )
    assert code == 130
    output = console.export_text()
    assert "None" not in output  # the whole abort path, not just the one message fixed before
    assert "No sites were processed" in output
    assert "--all" in output  # the plain invocation, rebuilt from sys.argv


@pytest.mark.integration
def test_explicit_site_rerun_command_excludes_an_already_completed_site(
    psh, monkeypatch, reset_sc,
):
    # Regression test: the site loop iterates every ORG site (its-wws-test1..3 here) and
    # `continue`s the ones not requested, so the aborting site name is an ORG-order position, not
    # an index into the requested list.  The old code fell into `else: remaining = requested`
    # whenever the aborting site wasn't itself in the requested list's resume-point slice, which
    # re-listed sites that had already completed -- including one whose report was JUST emailed.
    # Org site list is SITE_NAMES = [test1, test2, test3]; only test1 and test3 were requested
    # (test2 is a real org site the operator did not ask for -- the shape that triggers the bug).
    argv = [
        "./pantheon-sitehealth-emails", "--date", "2026-03-31",
        "its-wws-test1", "its-wws-test3",
    ]
    console, _captured, code = abort(
        psh, monkeypatch, reset_sc, argv, "interrupted", KeyboardInterrupt(),
        emailed=True, site_name="its-wws-test1",
        site_results={"its-wws-test1": {"framework": "wordpress"}},
    )
    assert code == 130
    output = console.export_text()
    match = re.search(r"Continue this run with:\n\n {4}(.+)\n", output)
    assert match, f"no rerun command found in:\n{output}"
    command = match.group(1)
    assert "its-wws-test1" not in command  # already emailed -- must not be re-mailed
    assert "its-wws-test3" in command


@pytest.mark.integration
def test_resume_command_is_never_wrapped_on_a_narrow_console(psh, monkeypatch, reset_sc):
    # sc.console is a bare Console(), so on a NON-TTY -- cron, nohup, systemd, any redirect, i.e.
    # exactly how a multi-hour --all run is launched -- rich falls back to width 80 and inserts a
    # REAL newline into the output.  This command is longer than 80 columns, and bash treats that
    # newline as a command separator: the first line re-parses as a complete, valid
    # `--all --for-real` run with NO --resume-from, so an operator pasting it restarts from the
    # first site and re-emails every owner who already received their report.  Print it soft-wrapped.
    argv = [
        "./pantheon-sitehealth-emails", "-v", "--config", "pantheon-sitehealth-emails.toml",
        "--date", "20260731", "--all", "--for-real", "--resume-from", "its-wws-test1",
    ]
    console, _captured, code = abort(
        psh, monkeypatch, reset_sc, argv, "database", psh.DatabaseUnavailableError("boom"),
        width=80,   # production's real width on a non-tty
    )
    assert code == 1
    expected = psh.resume_command(argv, "its-wws-test2")
    assert len(expected) > 80                      # the case the wrap would have broken
    output = console.export_text()
    assert any(expected in line for line in output.splitlines()), (
        f"the resume command was wrapped across lines:\n{output}"
    )


@pytest.mark.integration
def test_rerun_command_is_never_wrapped_on_a_narrow_console(psh, monkeypatch, reset_sc):
    # The explicit-SITE branch prints a command too, and it is the one that grows with every site
    # left to redo -- so it wraps even sooner than the --resume-from one.
    argv = [
        "./pantheon-sitehealth-emails", "--config", "pantheon-sitehealth-emails.toml",
        "--date", "20260731", "--for-real",
        "its-wws-test1", "its-wws-test2", "its-wws-test3",
    ]
    console, _captured, _code = abort(
        psh, monkeypatch, reset_sc, argv, "interrupted", KeyboardInterrupt(), width=80,
    )
    expected = psh.rerun_command(argv, ["its-wws-test1", "its-wws-test2", "its-wws-test3"],
                                 ["its-wws-test2", "its-wws-test3"])
    assert len(expected) > 80
    output = console.export_text()
    assert any(expected in line for line in output.splitlines()), (
        f"the re-run command was wrapped across lines:\n{output}"
    )


@pytest.mark.integration
def test_fatal_systemexit_flushes_pops_the_site_and_keeps_its_exit_code(psh, monkeypatch, reset_sc):
    # sys.exit("Bailing out.") inside the loop (an unknown plan SKU, a missing live environment)
    # and smtp_login()'s sys.exit() both fire AFTER site_results[site] was written mid-gather.  The
    # old handler called finish_run() directly and skipped the pop, shipping the failed site in
    # results.json as a success.  One flush path, one set of invariants: pop, flush, re-raise.
    argv = ["./pantheon-sitehealth-emails", "--date", "2026-03-31", "--all"]
    console, captured, code = abort(
        psh, monkeypatch, reset_sc, argv, "fatal", SystemExit("Bailing out."),
        site_results={
            "its-wws-test1": {"framework": "wordpress"},
            "its-wws-test2": {"framework": "wordpress"},  # the site that died
        },
    )
    assert code == "Bailing out."                       # the ORIGINAL exit code/message survives
    assert captured["ran"] is True                      # artifacts flushed
    assert captured["reason"] == "fatal"
    assert list(captured["site_results"].keys()) == ["its-wws-test1"]   # aborting site popped
    assert "--resume-from its-wws-test2" in console.export_text()


@pytest.mark.integration
def test_fatal_exception_is_reraised_after_the_flush(psh, monkeypatch, reset_sc):
    # An SMTPServerDisconnected on site 250 of 300, a CalledProcessError from the php inliner, a
    # KeyError from changed terminus JSON: all used to escape main() with no handler at all, losing
    # every completed site's artifacts.  Flush -- and then re-raise, so the traceback still reaches
    # the operator.  Nothing is swallowed.
    argv = ["./pantheon-sitehealth-emails", "--date", "2026-03-31", "--all"]
    error = RuntimeError("the php inliner died")
    _console, captured, _code = abort(
        psh, monkeypatch, reset_sc, argv, "fatal", error,
        expect=RuntimeError,
        site_results={"its-wws-test2": {"framework": "wordpress"}},
    )
    assert captured["raised"] is error                  # the original exception, re-raised
    assert captured["ran"] is True
    assert captured["site_results"] == {}               # the aborting site was popped


@pytest.mark.integration
def test_fatal_after_the_email_was_sent_keeps_the_site_in_the_results(psh, monkeypatch, reset_sc):
    # The pop-unless-emailed rule holds on the fatal path too: a site whose report really went out
    # completed, and the resumed run must start at the NEXT site or its owner gets a second copy.
    argv = ["./pantheon-sitehealth-emails", "--date", "2026-03-31", "--all"]
    console, captured, _code = abort(
        psh, monkeypatch, reset_sc, argv, "fatal", SystemExit(1),
        emailed=True,
        site_results={"its-wws-test2": {"framework": "wordpress"}},
    )
    assert "its-wws-test2" in captured["site_results"]
    assert "--resume-from its-wws-test3" in console.export_text()


# A real SQLAlchemy DBAPIError's str() ends like this: the statement, then the bound values.
SQLALCHEMY_TAIL = (
    "(MySQLdb.OperationalError) (2013, 'Lost connection to MySQL server during query')\n"
    "[SQL: SELECT pantheon_overage_protection.site_id FROM pantheon_overage_protection "
    "WHERE site_id = %s AND month = %s]\n"
    "[parameters: ('abc-123-def', datetime.date(2025, 6, 1))]"
)


@pytest.mark.integration
def test_the_database_error_is_printed_with_its_parameters_intact(psh, monkeypatch, reset_sc):
    # rich's markup tag regex is r"\[([a-z#/@][^[]*?)]", so `[parameters: (...)]` -- lowercase
    # initial -- parses as a STYLE TAG, resolves to nothing, and rich DELETES the text.  The
    # operator got the SQL (capital S in `[SQL:` saves it) with the bound values silently gone,
    # from exactly the single-execute SELECT most likely to hit a stale connection.  escape() it.
    argv = ["./pantheon-sitehealth-emails", "--date", "2026-03-31", "--all"]
    console, _captured, code = abort(
        psh, monkeypatch, reset_sc, argv, "database",
        psh.DatabaseUnavailableError(f"loading overage protection: {SQLALCHEMY_TAIL}"),
        width=300,
    )
    assert code == 1
    output = console.export_text()
    assert "[parameters: ('abc-123-def', datetime.date(2025, 6, 1))]" in output
    assert "[SQL: SELECT pantheon_overage_protection.site_id" in output
    assert "its-wws-test2" in output      # our own [bold] markup around the site name still works


@pytest.mark.integration
def test_a_markup_hostile_error_does_not_crash_the_flush(psh, monkeypatch, reset_sc):
    # An unmatched closing tag in interpolated text (`[/param]`) makes rich raise MarkupError --
    # INSIDE abort_run(), after SIGINT was set to SIG_IGN and BEFORE finish_run() ran.  The one
    # thing this function is documented to be incapable of: the operator gets a traceback and NO
    # artifacts at all.  The same applies on the fatal path, which interpolates any exception at
    # all, so both are covered.
    for reason, error, fragment in (
        (
            "database",
            psh.DatabaseUnavailableError("loading rows: [/parameters] [bad"),
            "[/parameters] [bad",
        ),
        ("fatal", SystemExit("Bailing out: [/bold] unterminated"), "[/bold] unterminated"),
    ):
        console, captured, _code = abort(
            psh, monkeypatch, reset_sc,
            ["./pantheon-sitehealth-emails", "--date", "2026-03-31", "--all"],
            reason, error, width=300,
        )
        assert captured["ran"] is True             # no MarkupError: the artifacts were flushed
        assert fragment in console.export_text()   # ... and the error is printed verbatim

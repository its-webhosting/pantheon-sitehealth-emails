"""finish_run() -- the end-of-run epilogue, now called from two places (normal completion and the
abort path).  The e2e goldens snapshot only the rendered report, so NOTHING else covers what this
function prints or writes.  See SPEC section 5.
"""

import datetime
import json

import pytest

from helpers.dnsfake import recording_console


class FakeSession:
    def __init__(self, close_raises=False):
        self.close_raises = close_raises

    def close(self):
        if self.close_raises:
            raise OSError("connection already dead")


class FakeEngine:
    def __init__(self):
        self.disposed = False

    def dispose(self):
        self.disposed = True


def run(psh, monkeypatch, reset_sc, argv, engine=None, session=None, **kwargs):
    console = recording_console(monkeypatch, reset_sc)
    reset_sc.options = psh.parse_args(argv)
    psh.finish_run(
        session or FakeSession(),
        engine or FakeEngine(),
        2,                                              # site_count
        2,                                              # emails_sent
        ["its-wws-test1,some-notice,detail"],           # all_warnings
        {"its-wws-test1": {"plan": "Basic"}},           # site_results
        [],                                             # site_savings
        **kwargs,
    )
    return console


@pytest.mark.integration
def test_finish_run_all_writes_the_artifacts(psh, tmp_path, monkeypatch, reset_sc):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
    run(psh, monkeypatch, reset_sc, ["--date", "2026-03-31", "--all"])

    assert "its-wws-test1,some-notice,detail" in list(tmp_path.glob("*-notices.csv"))[0].read_text()
    results = json.loads(list(tmp_path.glob("*-results.json"))[0].read_text())
    # results.json is SITE-KEYED AND NOTHING ELSE.  monthly-report.txt reads it with
    # `jq to_entries`, which enumerates every key as a site: the run metadata used to live here
    # under "_run" and became a bogus `_run,,,` row in the operator's monthly stats, throwing off
    # the site count and inventing an empty-framework CMS bucket.  Silently.
    assert results == {"its-wws-test1": {"plan": "Basic"}}

    # The run's outcome must still outlive the terminal scrollback (SPEC 3.6) -- in its own file.
    # Names say "this run" because the artifacts describe both runs on a resume while these
    # numbers describe only this one.
    run_meta = json.loads(list(tmp_path.glob("*-run.json"))[0].read_text())
    assert run_meta == {
        "aborted_at": None,
        "reason": None,
        "sites_completed_this_run": 1,
        "db_reconnects_healed_this_run": 0,
        "db_reconnect_failures_this_run": 0,
        "reconnects_by_site": {},
        "reconnect_failures_by_site": {},
    }


@pytest.mark.integration
def test_finish_run_without_all_prints_to_the_console(psh, tmp_path, monkeypatch, reset_sc):
    # The non---all branch of the epilogue.  No golden covers it; without this test it could be
    # deleted wholesale and the suite would stay green.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
    console = run(psh, monkeypatch, reset_sc, ["--date", "2026-03-31", "its-wws-test1"])

    output = console.export_text()
    assert "its-wws-test1,some-notice,detail" in output   # notices printed
    assert "Site savings" in output
    assert list(tmp_path.glob("*-results.json")) == []    # and nothing written


@pytest.mark.integration
def test_finish_run_aborted_does_not_claim_success(psh, tmp_path, monkeypatch, reset_sc):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {"its-wws-test2": 3})
    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {"its-wws-test2": 1})
    console = run(
        psh, monkeypatch, reset_sc, ["--date", "2026-03-31", "--all"],
        aborted_at="its-wws-test2", reason="database",
    )

    output = console.export_text()
    assert "aborting" in output.lower()
    # Healed vs. failed, spelled out: a bare "Database reconnects: 4" cannot tell the operator
    # whether the connection came back or the run died of it -- and this run died of it.
    assert "Database reconnects: 3 healed, 1 failed" in output
    results = json.loads(list(tmp_path.glob("*-results.json"))[0].read_text())
    assert list(results) == ["its-wws-test1"]   # no metadata key leaks into the site-keyed file
    run_meta = json.loads(list(tmp_path.glob("*-run.json"))[0].read_text())
    assert run_meta["aborted_at"] == "its-wws-test2"
    assert run_meta["reason"] == "database"
    assert run_meta["db_reconnects_healed_this_run"] == 3
    assert run_meta["db_reconnect_failures_this_run"] == 1
    assert run_meta["reconnects_by_site"] == {"its-wws-test2": 3}
    assert run_meta["reconnect_failures_by_site"] == {"its-wws-test2": 1}


@pytest.mark.integration
def test_finish_run_aborted_before_any_site_does_not_claim_success(
    psh, tmp_path, monkeypatch, reset_sc,
):
    # An interrupt landing before the first site's body runs passes aborted_at=None (site_name is
    # None), but reason is always set on an abort.  Branching on aborted_at is None (the old code)
    # misreads this as a clean completion: it prints the green success line and writes a null
    # `reason` into run.json, even though the process is about to exit 130/1.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
    console = run(
        psh, monkeypatch, reset_sc, ["--date", "2026-03-31", "--all"],
        aborted_at=None, reason="interrupted",
    )

    output = console.export_text()
    assert "Email sent for 2 of 2 sites" not in output   # the green success line
    assert "None" not in output   # aborted_at=None must not leak into the printed totals
    run_meta = json.loads(list(tmp_path.glob("*-run.json"))[0].read_text())
    assert run_meta["aborted_at"] is None
    assert run_meta["reason"] == "interrupted"


@pytest.mark.integration
def test_finish_run_update_all_writes_no_artifacts(psh, tmp_path, monkeypatch, reset_sc):
    # --update (and --import-older-metrics) `continue` before a report is ever built, so they have
    # no notices and no results.  Now that an aborted run flushes through finish_run(), a Ctrl-C'd
    # weekly `--update --all` would open {ymd}-notices.csv in "w" mode with an empty list and
    # overwrite {ymd}-results.json with an empty object -- DESTROYING the artifacts of the
    # monthly report run made earlier the same day.  Write nothing; still print the totals.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {"its-wws-test1": 2})
    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
    ymd = datetime.datetime.today().strftime("%Y%m%d")
    (tmp_path / f"{ymd}-notices.csv").write_text("its-wws-test9,from-the-report-run\n")
    (tmp_path / f"{ymd}-results.json").write_text('{"its-wws-test9": {"plan": "Basic"}}')

    console = run(
        psh, monkeypatch, reset_sc, ["--all", "--update"],
        aborted_at="its-wws-test1", reason="interrupted",
    )

    # The report run's artifacts are untouched, byte for byte.
    assert (tmp_path / f"{ymd}-notices.csv").read_text() == "its-wws-test9,from-the-report-run\n"
    assert json.loads((tmp_path / f"{ymd}-results.json").read_text()) == {
        "its-wws-test9": {"plan": "Basic"}
    }
    assert list(tmp_path.glob("*-run.json")) == []              # not even the metadata artifact
    assert "Database reconnects: 2 healed, 0 failed" in console.export_text()  # totals still print


@pytest.mark.integration
def test_finish_run_import_older_metrics_all_writes_no_artifacts(
    psh, tmp_path, monkeypatch, reset_sc,
):
    # The other report-less mode: same rule, and it must not depend on --update alone.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
    run(psh, monkeypatch, reset_sc, ["--all", "--import-older-metrics"])

    assert list(tmp_path.glob("*-notices.csv")) == []
    assert list(tmp_path.glob("*-results.json")) == []


@pytest.mark.integration
def test_finish_run_writes_artifacts_even_if_the_close_fails(psh, tmp_path, monkeypatch, reset_sc):
    # finish_run() is called FROM the abort path, on a session whose DB is by definition sick.  A
    # failing close() must cost neither the artifacts nor the engine dispose() (SPEC 3.3.3).
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
    engine = FakeEngine()
    run(
        psh, monkeypatch, reset_sc, ["--date", "2026-03-31", "--all"],
        engine=engine, session=FakeSession(close_raises=True),
    )
    assert list(tmp_path.glob("*-results.json")) != []
    assert engine.disposed is True


@pytest.mark.integration
def test_finish_run_abort_does_not_truncate_an_earlier_runs_artifacts(
    psh, tmp_path, monkeypatch, reset_sc,
):
    # The monthly `--all --for-real` run completes in the morning; that afternoon the operator
    # Ctrl-Cs a fresh (non-resumed) `--all` dry run after two sites.  The abort path used to decide
    # append-vs-truncate on --resume-from alone, so it opened {ymd}-notices.csv in "w" mode and
    # overwrote {ymd}-results.json -- DESTROYING the morning's record of what was actually mailed.
    # Before the abort path flushed at all, an interrupt wrote nothing and was harmless; it must
    # stay harmless.  An abort ACCUMULATES; only a run that reaches the end truncates.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
    ymd = datetime.datetime.today().strftime("%Y%m%d")
    (tmp_path / f"{ymd}-notices.csv").write_text("its-wws-morning,some-notice,detail\n")
    # A results.json left by an OLDER version still carries the "_run" key.  It must not survive
    # into the file this run writes: that key is the bogus-site-row bug (jq to_entries).
    (tmp_path / f"{ymd}-results.json").write_text(
        '{"its-wws-morning": {"plan": "Performance Small"}, "_run": {"reason": null}}'
    )
    (tmp_path / f"{ymd}-run.json").write_text('{"reason": null, "sites_completed_this_run": 1}')

    run(
        psh, monkeypatch, reset_sc, ["--date", "2026-03-31", "--all"],
        aborted_at="its-wws-test1", reason="interrupted",
    )

    notices = (tmp_path / f"{ymd}-notices.csv").read_text().splitlines()
    assert notices == [
        "its-wws-morning,some-notice,detail",       # the completed run's rows SURVIVE
        "its-wws-test1,some-notice,detail",         # ... and this run's are appended
    ]
    results = json.loads((tmp_path / f"{ymd}-results.json").read_text())
    assert results == {
        "its-wws-morning": {"plan": "Performance Small"},    # not overwritten
        "its-wws-test1": {"plan": "Basic"},                  # ... and merged with, site keys only
    }
    run_meta = json.loads((tmp_path / f"{ymd}-run.json").read_text())
    assert run_meta["reason"] == "interrupted"
    # The earlier run's block is nested, not lost: it carries the reconnect evidence that
    # prompted the resume in the first place.
    assert run_meta["previous"] == {"reason": None, "sites_completed_this_run": 1}


@pytest.mark.integration
def test_finish_run_completed_run_still_truncates(psh, tmp_path, monkeypatch, reset_sc):
    # The other half of the rule: a run that reaches the end owns the day's artifacts outright.
    # Without this, a re-run of the whole month would silently double every row.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
    ymd = datetime.datetime.today().strftime("%Y%m%d")
    (tmp_path / f"{ymd}-notices.csv").write_text("its-wws-stale,old-notice,detail\n")
    (tmp_path / f"{ymd}-results.json").write_text('{"its-wws-stale": {"plan": "Basic"}}')
    (tmp_path / f"{ymd}-run.json").write_text('{"reason": "database"}')

    run(psh, monkeypatch, reset_sc, ["--date", "2026-03-31", "--all"])

    assert (tmp_path / f"{ymd}-notices.csv").read_text() == "its-wws-test1,some-notice,detail\n"
    assert "its-wws-stale" not in json.loads((tmp_path / f"{ymd}-results.json").read_text())
    # The metadata artifact truncates on the same rule -- a completed run does not carry the
    # earlier aborted run's block forward under "previous".
    run_meta = json.loads((tmp_path / f"{ymd}-run.json").read_text())
    assert run_meta["reason"] is None
    assert "previous" not in run_meta

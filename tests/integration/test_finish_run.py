"""finish_run() -- the end-of-run epilogue, now called from two places (normal completion and the
abort path).  The e2e goldens snapshot only the rendered report, so NOTHING else covers what this
function prints or writes.  See SPEC section 5.
"""

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
    run(psh, monkeypatch, reset_sc, ["--date", "2026-03-31", "--all"])

    assert "its-wws-test1,some-notice,detail" in list(tmp_path.glob("*-notices.csv"))[0].read_text()
    results = json.loads(list(tmp_path.glob("*-results.json"))[0].read_text())
    assert results["its-wws-test1"] == {"plan": "Basic"}
    # The run's outcome must outlive the terminal scrollback (SPEC 3.6).  Names say "this run"
    # because merge_prior_results() makes the FILE describe both runs while _run describes one.
    assert results["_run"] == {
        "aborted_at": None,
        "reason": None,
        "sites_completed_this_run": 1,
        "db_reconnects_this_run": 0,
        "reconnects_by_site": {},
    }


@pytest.mark.integration
def test_finish_run_without_all_prints_to_the_console(psh, tmp_path, monkeypatch, reset_sc):
    # The non---all branch of the epilogue.  No golden covers it; without this test it could be
    # deleted wholesale and the suite would stay green.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    console = run(psh, monkeypatch, reset_sc, ["--date", "2026-03-31", "its-wws-test1"])

    output = console.export_text()
    assert "its-wws-test1,some-notice,detail" in output   # notices printed
    assert "Site savings" in output
    assert list(tmp_path.glob("*-results.json")) == []    # and nothing written


@pytest.mark.integration
def test_finish_run_aborted_does_not_claim_success(psh, tmp_path, monkeypatch, reset_sc):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {"its-wws-test2": 3})
    console = run(
        psh, monkeypatch, reset_sc, ["--date", "2026-03-31", "--all"],
        aborted_at="its-wws-test2", reason="database",
    )

    output = console.export_text()
    assert "aborting" in output.lower()
    assert "Database reconnects: 3" in output
    results = json.loads(list(tmp_path.glob("*-results.json"))[0].read_text())
    assert results["_run"]["aborted_at"] == "its-wws-test2"
    assert results["_run"]["reason"] == "database"
    assert results["_run"]["reconnects_by_site"] == {"its-wws-test2": 3}


@pytest.mark.integration
def test_finish_run_aborted_before_any_site_does_not_claim_success(
    psh, tmp_path, monkeypatch, reset_sc,
):
    # An interrupt landing before the first site's body runs passes aborted_at=None (site_name is
    # None), but reason is always set on an abort.  Branching on aborted_at is None (the old code)
    # misreads this as a clean completion: it prints the green success line and writes a null
    # `reason` into results.json, even though the process is about to exit 130/1.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    console = run(
        psh, monkeypatch, reset_sc, ["--date", "2026-03-31", "--all"],
        aborted_at=None, reason="interrupted",
    )

    output = console.export_text()
    assert "Email sent for 2 of 2 sites" not in output   # the green success line
    results = json.loads(list(tmp_path.glob("*-results.json"))[0].read_text())
    assert results["_run"]["aborted_at"] is None
    assert results["_run"]["reason"] == "interrupted"


@pytest.mark.integration
def test_finish_run_writes_artifacts_even_if_the_close_fails(psh, tmp_path, monkeypatch, reset_sc):
    # finish_run() is called FROM the abort path, on a session whose DB is by definition sick.  A
    # failing close() must cost neither the artifacts nor the engine dispose() (SPEC 3.3.3).
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    engine = FakeEngine()
    run(
        psh, monkeypatch, reset_sc, ["--date", "2026-03-31", "--all"],
        engine=engine, session=FakeSession(close_raises=True),
    )
    assert list(tmp_path.glob("*-results.json")) != []
    assert engine.disposed is True

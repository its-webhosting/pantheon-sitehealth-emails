"""run_terminus() must never let raw command stderr reach sc.console.print() unescaped.

rich (markup=True, the default on sc.console) parses a bracketed, lowercase-initial fragment
like "[warning] ..." or "[parameters: (1, 2)]" as a style tag and silently DELETES it -- and an
unmatched closing tag like "[/parameters]" raises rich.errors.MarkupError.  Terminus stderr
routinely contains exactly this shape (the existing filter in run_terminus() special-cases
"[warning] There are no available updates", proving the pattern is real traffic, not a
hypothetical).  Since main()'s `except BaseException:` handler re-raises everything, a
MarkupError from one site's stderr would abort an entire --all run.

subprocess.Popen is monkeypatched so this exercises the REAL run_terminus() console-printing
code, not just the terminus()/wp()/drush() wrappers (which monkeypatch run_terminus itself and
so never touch this code path).
"""
import pytest

from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration


def _fake_popen(stdout: bytes, stderr: bytes, returncode: int):
    class _FakeProcess:
        def __init__(self, *args, **kwargs):
            self.returncode = returncode

        def communicate(self, input=None, timeout=None):
            return stdout, stderr

        def kill(self):
            pass

    return _FakeProcess


def test_run_terminus_prints_bracketed_stderr_fragments_uncorrupted(psh, monkeypatch, reset_sc):
    console = recording_console(monkeypatch, reset_sc)
    stderr = b"[warning] plugin update available\n[parameters: (1, 2)]"
    monkeypatch.setattr(psh.subprocess, "Popen", _fake_popen(b"ok", stderr, 0))

    output, errors, fatal = psh.run_terminus(["site:info", "its-wws-test1"])

    assert fatal is False
    printed = console.export_text()
    # Un-escaped, rich would parse "[warning]"/"[parameters: ...]" as (unknown) style tags and
    # drop them from the printed text entirely.
    assert "[warning] plugin update available" in printed
    assert "[parameters: (1, 2)]" in printed


def test_run_terminus_survives_an_unmatched_closing_tag_in_stderr(psh, monkeypatch, reset_sc):
    console = recording_console(monkeypatch, reset_sc)
    stderr = b"err: [/parameters]"
    monkeypatch.setattr(psh.subprocess, "Popen", _fake_popen(b"", stderr, 1))

    # Must not raise rich.errors.MarkupError.
    output, errors, fatal = psh.run_terminus(["site:info", "its-wws-test1"])

    assert fatal is True
    assert "[/parameters]" in console.export_text()


def test_run_terminus_timeout_path_escapes_stdout_and_stderr(psh, monkeypatch, reset_sc):
    # The TimeoutExpired branch prints stdout/stderr too, and takes the SAME kind of untrusted
    # text -- it must be escaped just like the normal-completion path above.
    import subprocess as real_subprocess

    console = recording_console(monkeypatch, reset_sc)

    class _TimeoutThenDone:
        def __init__(self, *args, **kwargs):
            self.returncode = -9
            self._calls = 0

        def communicate(self, input=None, timeout=None):
            self._calls += 1
            if self._calls == 1:
                raise real_subprocess.TimeoutExpired(cmd="terminus", timeout=300)
            return b"partial [notice] output", b"[warning] slow response"

        def kill(self):
            pass

    monkeypatch.setattr(psh.subprocess, "Popen", _TimeoutThenDone)

    output, errors, fatal = psh.run_terminus(["site:info", "its-wws-test1"])  # must not raise

    assert fatal is True
    printed = console.export_text()
    assert "[notice] output" in printed
    assert "[warning] slow response" in printed

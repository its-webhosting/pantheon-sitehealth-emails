"""psh.cli.ensure_build_dir -- the ./build creation guard.

Extracted from main()'s straight-line body (the overage_blocks / sites_from_resume_point
precedent) because the statement it wraps sits ABOVE main()'s try: / except BaseException
lifecycle dispatch: a raise there escapes every handler, so the operator gets a bare traceback
and CPython's exit 1 -- the code abort_reason reserves for a database failure -- instead of a
named message (PD#1, PD#2).  main() has no in-process caller (the subprocess interlock bans
--all/--for-real), so the helper is the only seam that reaches this.
"""
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_creates_the_directory_when_it_is_absent(psh, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    psh.ensure_build_dir()
    assert (tmp_path / "build").is_dir()


def test_is_a_no_op_when_the_directory_already_exists(psh, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "keep.txt").write_text("prior run's artifact")
    psh.ensure_build_dir()
    assert (tmp_path / "build" / "keep.txt").read_text() == "prior run's artifact"


def test_a_non_directory_build_exits_with_a_named_message_not_a_traceback(psh, tmp_path,
                                                                         monkeypatch):
    # The reviewed scenario: a stray regular file named "build" in the CWD.  mkdir(exist_ok=True)
    # suppresses FileExistsError only when the target IS a directory, so this raises -- and the
    # raise happens above main()'s handler.  RED before the guard: FileExistsError, not SystemExit.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "build").write_text("not a directory")
    with pytest.raises(SystemExit) as excinfo:
        psh.ensure_build_dir()
    message = str(excinfo.value)
    assert "build" in message
    assert "not a directory" in message, (
        'the message must say WHY it failed -- FileExistsError\'s own text is "[Errno 17] File '
        'exists: \'build\'", which does not tell an operator that the name is taken by a file')


def test_a_dangling_symlink_named_build_is_reported_the_same_way(psh, tmp_path, monkeypatch):
    # Same operator-facing condition, different errno path: the name exists in the directory but
    # resolves to nothing, so is_dir() is False and mkdir still raises FileExistsError.  This is
    # why the message says "is not a directory" rather than "a file named build exists".
    monkeypatch.chdir(tmp_path)
    (tmp_path / "build").symlink_to(tmp_path / "nowhere")
    with pytest.raises(SystemExit) as excinfo:
        psh.ensure_build_dir()
    assert "not a directory" in str(excinfo.value)


def test_any_other_oserror_also_exits_named_and_carries_the_cause(psh, tmp_path, monkeypatch):
    # An unwritable CWD, a read-only filesystem, ENOSPC -- all the same operator condition
    # ("cannot create build/") and all OSError.  Injected rather than staged with permission bits,
    # which root ignores inside the dev container.  RED before the guard: PermissionError escapes.
    monkeypatch.chdir(tmp_path)

    def boom(*_a, **_k):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "mkdir", boom)
    with pytest.raises(SystemExit) as excinfo:
        psh.ensure_build_dir()
    message = str(excinfo.value)
    assert "build" in message
    assert "Permission denied" in message, "the underlying error must survive into the message"

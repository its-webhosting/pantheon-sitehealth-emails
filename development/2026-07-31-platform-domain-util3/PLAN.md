# `find-platform-domains-cloudflare` plan/revert files — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.
>
> **Every code-touching subagent MUST be dispatched as `psh-implementer`, every reviewer as
> `psh-reviewer`** (CLAUDE.md § Dispatching subagents). `general-purpose` carries none of this
> repo's standards; a dispatch that cannot use them must stop and say so.

**Goal:** Make `find-platform-domains-cloudflare` emit, alongside its inventory, a Cloudflare DNS
batch **plan** that swaps each platform CNAME for the A/AAAA records its target actually resolves
to, a **revert** that undoes it, and a reasoned list of every FQDN **excluded** from both.

**Architecture:** One standalone script, no new modules. `-o/--output` becomes
`-o/--output-basename`; basename mode writes four files, stdout mode writes the inventory only.
Per-FQDN DNS resolution of the `*.pantheonsite.io` target supplies the replacement addresses.
Because Cloudflare's batch `deletes` accepts only record ids — which the plan's `posts` have not
minted yet — each entry carries a `delete_match` block **outside** the postable `body`, resolved
to ids by a later, separate applier script.

**Tech Stack:** Python 3.12+, `cloudflare` 5.4.0 SDK (unpinned in `pyproject.toml`), `dnspython`
(already a core dependency, `pyproject.toml:13`), stdlib `ipaddress`/`tempfile`/`json`, pytest.

**Spec:** `development/2026-07-31-platform-domain-util3/SPEC.md`. Every requirement reference
below (`R1`, `§5.3`, …) is to that document. **Read it before Task 1.**

---

## Global Constraints

Copied verbatim from SPEC §2 and CLAUDE.md. Every task's requirements implicitly include these.

- **Standalone.** The script MUST import nothing from `psh/`, `check/`, `plugin/` or
  `script_context`. Code needed from the main program is **copied into the script**, never
  imported and never modularized. Deletion must stay `git rm` of three files.
- **No new files.** No new source file, no new `pyproject.toml` entry, no new
  `.claude/hooks/ruff-check.sh` arm. All code lands in `find-platform-domains-cloudflare`; all
  tests land in `tests/unit/test_find_platform_domains_cloudflare.py`.
- **`tests/unit/test_find_platform_domains_dns.py` and `find-platform-domains-dns` MUST stay
  byte-identical.** `git diff --stat` on them must be empty at every commit.
- **Scope (R1).** Only CNAME records whose `content` ends in `.pantheonsite.io`.
  `*.pantheon.io` and `*.gotpantheon.com` are out of scope and must not be mentioned in new code.
- **No performance work.** PROMPT.md: "Do not put any significant amount of work into making this
  script fast or efficient."
- **Test-first**, per `prompts/implementation-standards.md` and `mattpocock-skills:tdd`. Refactor
  is **not** part of the red→green loop; it belongs to review.
- **NEVER weaken an assertion to make it pass. NEVER delete a test to make a suite green. NEVER
  regenerate a golden without a reviewed diff.** Every new test MUST be observed failing for the
  **right reason** before its implementation exists (PD#14).
- **Ruff runs `select = ALL`.** `os.path` calls need `# noqa: PTH…` with a justification, matching
  the style already in `write_json_atomic`. `print` is already excused for this file via
  `[tool.ruff.lint.per-file-ignores]`.
- **Commit only what the task names.** Do not commit the whole tree. Do not create a branch.
- **Every task report MUST cite the Prime Directives it applied by number with a verbatim quote**
  from `prompts/directives.md`.

**Existing baseline:** `./run-tests --fast tests/unit/test_find_platform_domains_cloudflare.py`
→ **96 passed**, ruff and pyright clean.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `find-platform-domains-cloudflare` | The whole utility. Currently 856 lines. | Modified in Tasks 1–6 |
| `find-platform-domains-cloudflare.py` | Committed symlink to the above, so ruff/pyright/CodeGraph see it. | **Untouched. Do not delete.** |
| `tests/unit/test_find_platform_domains_cloudflare.py` | All tests. Currently 1123 lines. | Modified in Tasks 1–6 |
| `CLAUDE.md` | The `### find-platform-domains-cloudflare (temporary utility)` subsection | Task 7 |
| `.gitignore` | The baseline-file ignore | Task 7 |
| `development/2026-07-30-platform-domain-util2/SPEC.md` | §11 deletion checklist | Task 7 |

**Import block.** Tasks add to the script's existing top-of-file import block. New imports across
the whole plan, exhaustive: `datetime`, `ipaddress`, `struct`, `time`, `dns.exception`,
`dns.name`, `dns.resolver`. Ruff's `E402` forbids adding an import lower in the file.

**Test file convention**, quoted from its own docstring: *"Imports: each task ADDS to the block
below, in the task that first needs the name. Editing the top block is fine; adding an import
further down the file is what ruff's E402 forbids."* Each task appends a
`# --- Task N: <name> ---` banner section, matching the existing Task 1–5 banners.

---

## Task 1: `--output-basename`, path derivation, and the startup writability probe

Implements **R2**. After this task the script still writes exactly one file — the inventory — but
via the new option and the new path helper.

**Files:**
- Modify: `find-platform-domains-cloudflare` (imports; `OUTPUT_FILE` constant at :57;
  `require_usable_streams` :111; `destination_name` :688; `interrupt_message` :695;
  `summarize` :719; `build_arg_parser` :767; `main` :792)
- Test: `tests/unit/test_find_platform_domains_cloudflare.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `OUTPUT_BASENAME: str = "platform-domains-cloudflare"` (replaces `OUTPUT_FILE`)
  - `class OutputPaths(NamedTuple)` with fields `inventory: str`, `plan: str`, `revert: str`,
    `excluded: str`
  - `output_paths(basename: str) -> OutputPaths`
  - `check_basename(basename: str) -> str` — returns the basename, raises `StartupError`
  - `options.output_basename` replaces `options.output` throughout

---

- [ ] **Step 1: Write the failing tests for `check_basename` and `output_paths`**

Append to `tests/unit/test_find_platform_domains_cloudflare.py`:

```python
# --- Task 1: the output basename -------------------------------------------------------------

def test_output_paths_appends_the_four_suffixes(fpc):
    paths = fpc.output_paths("engin-zone")
    assert paths == ("engin-zone.json", "engin-zone-plan.json",
                     "engin-zone-revert.json", "engin-zone-excluded.json")
    assert paths.inventory == "engin-zone.json"
    assert paths.excluded == "engin-zone-excluded.json"


@pytest.mark.parametrize("basename", ["engin-zone", "out/engin-zone", "out/v1.2/engin-zone"])
def test_check_basename_accepts_a_dotless_final_component(fpc, tmp_path, basename):
    """A dot in a DIRECTORY component is fine; only the filename component is checked (R2.2)."""
    target = tmp_path / basename
    target.parent.mkdir(parents=True, exist_ok=True)
    assert fpc.check_basename(str(target)) == str(target)


@pytest.mark.parametrize("basename", ["engin-zone.json", "engin.umich.edu", ".hidden",
                                      "report.txt"])
def test_check_basename_rejects_an_extension(fpc, tmp_path, basename):
    """The old `-o platform-domains-cloudflare.json` is muscle memory and would otherwise
    produce platform-domains-cloudflare.json.json (R2.2)."""
    with pytest.raises(fpc.StartupError) as excinfo:
        fpc.check_basename(str(tmp_path / basename))
    assert basename in str(excinfo.value)
    assert "extension" in str(excinfo.value)


def test_check_basename_rejects_a_directory_with_no_filename_component(fpc, tmp_path):
    """Path('out/').name is 'out', so a Path-based check would ACCEPT this; os.path.basename
    returns '' and catches it (R2.2)."""
    with pytest.raises(fpc.StartupError) as excinfo:
        fpc.check_basename(f"{tmp_path}/")
    assert "no filename component" in str(excinfo.value)


def test_check_basename_rejects_an_unwritable_directory(fpc, tmp_path):
    """R2.4: the sweep takes ~2 minutes and today's write failure surfaces only after it."""
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        with pytest.raises(fpc.StartupError) as excinfo:
            fpc.check_basename(str(locked / "engin-zone"))
    finally:
        locked.chmod(0o700)
    assert "cannot write output files" in str(excinfo.value)


def test_check_basename_leaves_no_probe_file_behind(fpc, tmp_path):
    """The probe proves writability; leaving it would litter the operator's directory."""
    fpc.check_basename(str(tmp_path / "engin-zone"))
    assert list(tmp_path.iterdir()) == []
```

- [ ] **Step 2: Run them and confirm they fail for the right reason**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_cloudflare.py -k "output_paths or check_basename"
```

Expected: every test ERRORs with `AttributeError: module ... has no attribute 'output_paths'` /
`'check_basename'`. **If any test fails for a different reason, stop and report it** — a test that
fails for the wrong reason proves nothing (PD#14).

- [ ] **Step 3: Implement `OutputPaths`, `output_paths` and `check_basename`**

In `find-platform-domains-cloudflare`, replace the `OUTPUT_FILE` constant (:57–59) with:

```python
OUTPUT_BASENAME = "platform-domains-cloudflare"   # the CONVENTIONAL basename of the
                                       # organization-wide baseline, named in --help; the script
                                       # writes it only when the operator asks, via -o
```

Add after `is_platform_domain` (:154), keeping the existing `NamedTuple` import:

```python
class OutputPaths(NamedTuple):
    """The four files basename mode writes.  ONE definition, so no call site can invent a
    different suffix -- the same reason dump_json() is the one serializer."""

    inventory: str
    plan: str
    revert: str
    excluded: str


def output_paths(basename):
    """The four paths derived from BASENAME (SPEC R2.1)."""
    return OutputPaths(f"{basename}.json", f"{basename}-plan.json",
                       f"{basename}-revert.json", f"{basename}-excluded.json")


def check_basename(basename):
    """Validate -o's BASENAME and prove its directory is writable, BEFORE the sweep starts.

    Two refusals, both SPEC R2.2/R2.4:

      * A dot anywhere in the FINAL path component is an extension.  The old interface took a
        path, so `-o platform-domains-cloudflare.json` is muscle memory -- under the new one it
        would produce platform-domains-cloudflare.json.json.  A literal reading of "file
        extension" is the only rule that needs no judgment and fits in one --help sentence.
        Directory components MAY contain dots.
      * The parent directory must be writable.  The sweep takes ~2 minutes and the previous
        interface discovered an unwritable destination only AFTER it.  The probe does not make a
        late ENOSPC impossible; it makes the common case fail at second zero.

    os.path.basename, NOT Path().name: Path("out/").name is "out", so a Path-based check ACCEPTS
    a directory with no filename component.  os.path.basename returns "" and catches it.
    """
    final = os.path.basename(basename)   # noqa: PTH119 -- see the docstring: Path().name has
                                         # different semantics for a trailing separator, which is
                                         # one of the two cases this function exists to reject
    if not final:
        raise StartupError(
            f"--output-basename {basename!r} has no filename component; give a basename such as "
            "'engin-zone', not a directory")
    if "." in final:
        raise StartupError(
            f"--output-basename {basename!r} contains a file extension; give the basename "
            "WITHOUT one (for example 'engin-zone', not 'engin-zone.json').  The four output "
            "files get .json, -plan.json, -revert.json and -excluded.json appended.")
    directory = os.path.dirname(os.path.abspath(basename)) or "."  # noqa: PTH120, PTH100 --
    # matches write_json_atomic's existing idiom; Path.resolve() follows symlinks where
    # os.path.abspath() does not, a real semantic difference for the symlink case
    try:
        handle, probe = tempfile.mkstemp(dir=directory, prefix=".platform-domains-probe-")
    except OSError as e:
        raise StartupError(f"cannot write output files next to {basename}: {e}") from e
    os.close(handle)
    os.unlink(probe)  # noqa: PTH108 -- cleanup of the same os.path/tempfile surface above
    return basename
```

- [ ] **Step 4: Run the tests and confirm they pass**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_cloudflare.py -k "output_paths or check_basename"
```

Expected: 11 passed.

- [ ] **Step 5: Write the failing test for the renamed option**

```python
def test_the_output_option_takes_a_basename_not_a_path(fpc, tmp_path, monkeypatch, capsys):
    """R2.1: -o/--output-basename replaces -o/--output."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": ENTRY}, [], 1, 2, 5, 1, 0, 0, 2))
    assert fpc.main(["-o", "engin-zone"]) == 0
    assert json.loads((tmp_path / "engin-zone.json").read_text()) == {"a.example.edu": ENTRY}


def test_the_old_output_path_form_is_rejected_before_any_api_call(fpc, tmp_path, monkeypatch,
                                                                  capsys):
    """The probe must fire BEFORE cloudflare_client, or an operator waits ~2 minutes to learn
    they mistyped the destination (R2.4)."""
    monkeypatch.chdir(tmp_path)

    def explode(config_path):
        raise AssertionError("cloudflare_client must not be reached")

    monkeypatch.setattr(fpc, "cloudflare_client", explode)
    assert fpc.main(["-o", "platform-domains-cloudflare.json"]) == 2
    assert "contains a file extension" in capsys.readouterr().err


def test_bare_double_dash_output_is_not_accepted(fpc, capsys):
    """allow_abbrev=False, so no prefix match rescues the removed spelling."""
    with pytest.raises(SystemExit):
        fpc.build_arg_parser().parse_args(["--output", "engin-zone"])
```

- [ ] **Step 6: Run them and confirm they fail**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_cloudflare.py -k "output_option or old_output_path or bare_double_dash"
```

Expected, and **all three must fail** — a test that passes the moment you write it is testing
existing behavior:

| Test | Fails because |
|---|---|
| `..._takes_a_basename_not_a_path` | the old `-o` writes to the literal path `engin-zone`, so `engin-zone.json` does not exist |
| `..._old_output_path_form_is_rejected...` | the old `-o` accepts the `.json` path, so `main` returns 0, not 2, and `cloudflare_client` **is** reached — the injected `explode` fires |
| `..._bare_double_dash_output_is_not_accepted` | `--output` is still a valid option, so `parse_args` succeeds and no `SystemExit` is raised |

If any of the three passes before the implementation, **stop and report it** — the test is not
covering what it claims to (PD#14).

- [ ] **Step 7: Rename the option and thread `output_basename` through**

In `build_arg_parser` (:785), replace the `-o` argument and update the epilog:

```python
    parser.add_argument("-o", "--output-basename", default=None, metavar="BASENAME",
                        help="write four JSON files -- BASENAME.json, BASENAME-plan.json, "
                             "BASENAME-revert.json and BASENAME-excluded.json -- instead of "
                             "writing the inventory to standard output.  BASENAME must have NO "
                             "file extension")
```

and the epilog's closing sentence:

```python
        epilog=f"With no ZONE, every zone in every visible account is swept.  To refresh the "
               f"organization-wide baseline before a rewrite, use -o rather than a redirect: "
               f"`-o {OUTPUT_BASENAME}` replaces each file atomically and only on success, where "
               f"`> {OUTPUT_BASENAME}.json` truncates it before the sweep even starts and so "
               f"destroys the previous baseline on any failed run.")
```

Then rename every `options.output` to `options.output_basename`, and in `main` compute the paths
immediately after the stream check:

```python
        require_usable_streams(options.output_basename)
        paths = (output_paths(check_basename(options.output_basename))
                 if options.output_basename else None)
```

`emit`, `destination_name`, `interrupt_message` and `summarize` now take `paths` (an
`OutputPaths` or `None`) instead of a path string. For this task, minimally:

```python
def destination_name(paths):
    """Where the inventory went, for an operator message.  ONE definition, because naming the
    wrong destination is how the zero-match ATTENTION came to tell operators that a baseline file
    they still had on disk "was written empty" when nothing had been written at all."""
    return "standard output" if paths is None else paths.inventory


def emit(entries, paths) -> None:
    """Send the inventory to its destination: the basename file, or stdout when there is none."""
    if paths is None:
        write_json_stdout(entries)
    else:
        write_json_atomic(paths.inventory, entries)
```

In `interrupt_message` and `summarize`, replace the `output` parameter with `paths` and the
`output is not None` tests with `paths is not None`, using `paths.inventory` wherever the old
code interpolated `output`.

- [ ] **Step 8: Run the whole file**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_cloudflare.py
```

Expected: all pass. Existing tests that pass `-o out.json` must be updated to `-o out` in this
step — that is a **rename, not a weakening**; state each one in the task report.

- [ ] **Step 9: Confirm the sibling is untouched, then commit**

```bash
git diff --stat find-platform-domains-dns tests/unit/test_find_platform_domains_dns.py
# Expected: empty output.
git add find-platform-domains-cloudflare tests/unit/test_find_platform_domains_cloudflare.py
git commit -m "feat(find-platform-domains-cloudflare): -o takes a basename, not a path

--output-basename derives four paths and is validated before the sweep starts: a dot
in the final path component is fatal (the old -o argument form would have produced
platform-domains-cloudflare.json.json), and the parent directory is probed for
writability so an unwritable destination fails at second zero rather than after the
~2-minute walk.  SPEC R2."
```

---

## Task 2: The DNS layer

Implements **R3** and **§5.2**. Pure addition — nothing calls it yet.

**Files:**
- Modify: `find-platform-domains-cloudflare` (imports; new code after `is_platform_domain`)
- Test: `tests/unit/test_find_platform_domains_cloudflare.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class MalformedNameError(Exception)`
  - `resolve(hostname: str, rrtype: str)` — **the one DNS seam**; returns a dnspython answer
  - `DNS_RETRY_SLEEP: float = 1.0`
  - `resolve_retrying(hostname: str, rrtype: str)` — `resolve` with one retry
  - `sorted_addresses(values: Iterable[str]) -> list[str]`
  - `class Resolution(NamedTuple)` with `a: list | None`, `aaaa: list | None`, `problem: str`
  - `resolve_target(target: str) -> Resolution`

---

- [ ] **Step 1: Write the failing tests**

```python
# --- Task 2: the DNS layer -------------------------------------------------------------------

def fake_dns(fpc, monkeypatch, answers):
    """Patch the ONE DNS seam.  `answers` maps (hostname, rrtype) to a list of address strings,
    or to an exception INSTANCE to raise.  Nothing in this suite may touch real DNS (SPEC 7)."""
    calls = []

    def fake(hostname, rrtype):
        calls.append((hostname, rrtype))
        answer = answers[(hostname, rrtype)]
        if isinstance(answer, BaseException):
            raise answer
        return answer

    monkeypatch.setattr(fpc, "resolve", fake)
    return calls


def test_sorted_addresses_orders_by_value_not_lexically(fpc):
    """23.185.0.10 sorts BEFORE 23.185.0.4 as a string.  A lexical sort would make the plan
    file's post order depend on nothing meaningful (SPEC 5.2)."""
    assert fpc.sorted_addresses(["23.185.0.10", "23.185.0.4", "23.185.0.2"]) == [
        "23.185.0.2", "23.185.0.4", "23.185.0.10"]


def test_sorted_addresses_normalizes_rotating_rrset_order(fpc):
    """Measured 2026-07-31: two live AAAA queries returned the pair in OPPOSITE orders, so
    without this no two sweeps produce identical bytes (SPEC 1, SPEC 5.2)."""
    one = fpc.sorted_addresses(["2620:12a:8001::4", "2620:12a:8000::4"])
    two = fpc.sorted_addresses(["2620:12a:8000::4", "2620:12a:8001::4"])
    assert one == two == ["2620:12a:8000::4", "2620:12a:8001::4"]


def test_resolve_target_returns_both_sorted_rrsets(fpc, monkeypatch):
    fake_dns(fpc, monkeypatch, {
        ("live-a.pantheonsite.io", "A"): ["23.185.0.4"],
        ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8001::4", "2620:12a:8000::4"],
    })
    assert fpc.resolve_target("live-a.pantheonsite.io") == (
        ["23.185.0.4"], ["2620:12a:8000::4", "2620:12a:8001::4"], "")


def test_resolve_target_reports_a_definitive_absence_as_empty_not_null(fpc, monkeypatch):
    """R4.4: [] means "definitively none", null means "we do not know"."""
    fake_dns(fpc, monkeypatch, {
        ("live-a.pantheonsite.io", "A"): dns.resolver.NoAnswer(),
        ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8000::4"],
    })
    result = fpc.resolve_target("live-a.pantheonsite.io")
    assert result.a == []
    assert result.problem == ""


def test_resolve_target_reports_an_indeterminate_lookup_as_null(fpc, monkeypatch):
    """R4.4 again, the other half: a timeout must never be rendered as "no records"."""
    fake_dns(fpc, monkeypatch, {("live-a.pantheonsite.io", "A"): dns.resolver.Timeout()})
    result = fpc.resolve_target("live-a.pantheonsite.io")
    assert result.a is None
    assert result.aaaa is None
    assert "Timeout" in result.problem


def test_resolve_target_keeps_a_good_a_when_only_aaaa_is_indeterminate(fpc, monkeypatch):
    """The A answer was definitive and is still evidence; only the unknown half goes null."""
    fake_dns(fpc, monkeypatch, {
        ("live-a.pantheonsite.io", "A"): ["23.185.0.4"],
        ("live-a.pantheonsite.io", "AAAA"): dns.resolver.NoNameservers(),
    })
    result = fpc.resolve_target("live-a.pantheonsite.io")
    assert result.a == ["23.185.0.4"]
    assert result.aaaa is None
    assert "NoNameservers" in result.problem


def test_resolve_target_reports_a_malformed_name_as_indeterminate(fpc, monkeypatch):
    fake_dns(fpc, monkeypatch,
             {("a..b.pantheonsite.io", "A"): fpc.MalformedNameError("a..b: SyntaxError")})
    assert fpc.resolve_target("a..b.pantheonsite.io").problem.startswith("MalformedNameError")


def test_resolve_retrying_retries_a_timeout_exactly_once(fpc, monkeypatch):
    """R3.3.  Exactly once: a retry loop would multiply a whole sweep's wall time by the
    resolver's timeout on a systemic failure."""
    attempts = []

    def flaky(hostname, rrtype):
        attempts.append(rrtype)
        if len(attempts) == 1:
            raise dns.resolver.Timeout
        return ["23.185.0.4"]

    monkeypatch.setattr(fpc, "resolve", flaky)
    assert fpc.resolve_retrying("live-a.pantheonsite.io", "A") == ["23.185.0.4"]
    assert attempts == ["A", "A"]


def test_resolve_retrying_gives_up_after_the_second_failure(fpc, monkeypatch):
    attempts = []

    def always_down(hostname, rrtype):
        attempts.append(rrtype)
        raise dns.resolver.Timeout

    monkeypatch.setattr(fpc, "resolve", always_down)
    monkeypatch.setattr(fpc.time, "sleep", lambda seconds: None)
    with pytest.raises(dns.resolver.Timeout):
        fpc.resolve_retrying("live-a.pantheonsite.io", "A")
    assert attempts == ["A", "A"]


def test_resolve_retrying_sleeps_before_retrying_a_nonameservers(fpc, monkeypatch):
    """Copied reasoning from find-platform-domains-dns:139 -- a Timeout has already consumed
    dnspython's ~5s lifetime, but NoNameservers returns in ~0.3s and is most often the recursive
    resolver rate-limiting us, so an immediate retry re-fires into the same condition."""
    slept = []
    monkeypatch.setattr(fpc.time, "sleep", slept.append)
    attempts = []

    def flaky(hostname, rrtype):
        attempts.append(rrtype)
        if len(attempts) == 1:
            raise dns.resolver.NoNameservers
        return ["23.185.0.4"]

    monkeypatch.setattr(fpc, "resolve", flaky)
    assert fpc.resolve_retrying("live-a.pantheonsite.io", "A") == ["23.185.0.4"]
    assert slept == [fpc.DNS_RETRY_SLEEP]
```

Add `import dns.resolver` to the test file's top import block.

- [ ] **Step 2: Run them and confirm they fail**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_cloudflare.py -k "sorted_addresses or resolve_target or resolve_retrying"
```

Expected: `AttributeError` for each new name. Any other failure — stop and report.

- [ ] **Step 3: Implement the DNS layer**

Add to the script's import block: `import datetime`, `import ipaddress`, `import struct`,
`import time`, `import dns.exception`, `import dns.name`, `import dns.resolver` (alphabetical
within the stdlib and third-party groups, matching the existing block).

Add after `is_platform_domain`:

```python
DNS_RETRY_SLEEP = 1.0     # before retrying a NoNameservers only -- see resolve_retrying


class MalformedNameError(Exception):
    """`hostname` is not a syntactically valid DNS name.

    Copied from find-platform-domains-dns, which copied it from psh/dns_classify.py.  dnspython
    raises four unrelated exception types for a bad name -- dns.exception.SyntaxError subclasses,
    dns.name.NameTooLong, dns.name.IDNAException, and the stdlib struct.error for an out-of-range
    byte escape -- none of which derive from dns.resolver.*, so no resolver handler catches them.
    resolve() converts them here, ONCE, so no caller can forget them and abort a whole sweep on
    one malformed record content.
    """


def resolve(hostname, rrtype):
    """The one seam over dns.resolver.resolve; tests monkeypatch this module attribute.

    Copied from find-platform-domains-dns:62, including the struct.error split: the name is
    parsed FIRST, in its own try, so only a parse-time struct.error is reported as a malformed
    name.  dnspython ALSO raises struct.error from its TCP length-prefix unpack -- i.e. from
    garbled wire data on a perfectly valid name -- and that must surface as transient
    (NoNameservers), never as "not a valid DNS name".
    """
    try:
        dns.name.from_text(hostname)
    except (dns.exception.SyntaxError, dns.name.NameTooLong, dns.name.IDNAException,
            struct.error) as e:
        raise MalformedNameError(f"{hostname}: {type(e).__name__}") from e

    try:
        return dns.resolver.resolve(hostname, rrtype)
    except (dns.exception.SyntaxError, dns.name.NameTooLong, dns.name.IDNAException) as e:
        raise MalformedNameError(f"{hostname}: {type(e).__name__}") from e
    except struct.error as e:
        raise dns.resolver.NoNameservers from e


def resolve_retrying(hostname, rrtype):
    """resolve() with ONE retry on a transient resolver failure (SPEC R3.3).

    The delay depends on which failure it was, and the difference is measured rather than
    assumed (find-platform-domains-dns:139): a Timeout has already consumed dnspython's own ~5s
    lifetime, so retrying immediately is right; NoNameservers (SERVFAIL/REFUSED) comes back in
    ~0.3s, and the likeliest cause of a burst of those during a sweep is the recursive resolver
    rate-limiting us -- so an immediate retry just re-fires into the same condition.

    ONE retry, not a loop: on a systemic resolver failure a loop multiplies the whole sweep's
    wall time by the resolver timeout, for an answer that is not coming.
    """
    try:
        return resolve(hostname, rrtype)
    except dns.resolver.Timeout:
        return resolve(hostname, rrtype)
    except dns.resolver.NoNameservers:
        time.sleep(DNS_RETRY_SLEEP)
        return resolve(hostname, rrtype)


def sorted_addresses(values):
    """Addresses sorted by ip_address() VALUE, never lexically (SPEC 5.2).

    Two reasons, both real.  Lexically "23.185.0.10" sorts before "23.185.0.4".  And DNS rrsets
    rotate -- two live AAAA queries on 2026-07-31 returned the same pair in opposite orders -- so
    without a stable sort two identical sweeps produce diffing files and no golden is stable.
    """
    return [str(address) for address in sorted(ipaddress.ip_address(str(v)) for v in values)]


class Resolution(NamedTuple):
    """What one platform-domain target resolved to.

    `a`/`aaaa` are [] for a DEFINITIVE absence and None when the lookup was INDETERMINATE
    (SPEC R4.4).  Collapsing the two would tell an operator a target has no addresses when the
    run never established that -- the same distinction the sweep already keeps between a null
    and a false `proxied`.
    """

    a: list | None
    aaaa: list | None
    problem: str          # "" for a definitive answer; else why it is indeterminate


def resolve_one_rrset(target, rrtype):
    """(addresses, problem) for one rrset.  ([], "") when definitively absent."""
    try:
        answer = resolve_retrying(target, rrtype)
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        return [], ""
    except (dns.resolver.Timeout, dns.resolver.NoNameservers, MalformedNameError) as e:
        return None, f"{type(e).__name__} resolving {rrtype} for {target}"
    return sorted_addresses(str(rdata) for rdata in answer), ""


def resolve_target(target):
    """The A and AAAA records a platform domain resolves to, following CNAME chains.

    dnspython follows the chain itself and returns the terminal rrset, which is what makes both
    live shapes work uniformly -- live-bus-occb.pantheonsite.io is a CNAME into
    fe4.edge.pantheon.io, while live-umich-its-wws-test1.pantheonsite.io answers A/AAAA directly
    (SPEC section 1).

    An indeterminate A leaves BOTH halves None: with the A answer unknown there is nothing the
    AAAA answer alone can be used for, and spending a second lookup to enrich a row that is
    already excluded is wasted.  An indeterminate AAAA keeps the good A, which is still evidence.
    """
    a, problem = resolve_one_rrset(target, "A")
    if problem:
        return Resolution(None, None, problem)
    aaaa, problem = resolve_one_rrset(target, "AAAA")
    if problem:
        return Resolution(a, None, problem)
    return Resolution(a, aaaa, "")
```

- [ ] **Step 4: Run the tests and confirm they pass**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_cloudflare.py
```

Expected: all pass.

- [ ] **Step 5: Prove nothing in the suite touches real DNS**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_cloudflare.py -p no:cacheprovider
```

Then, as an explicit PD#14 check, temporarily add `raise AssertionError("real DNS")` as the first
line of the script's `resolve()`, re-run the file, confirm **every test still passes**, and remove
it. Record the result in the task report. If any test fails, a test is reaching real DNS and must
be fixed before commit.

- [ ] **Step 6: Commit**

```bash
git add find-platform-domains-cloudflare tests/unit/test_find_platform_domains_cloudflare.py
git commit -m "feat(find-platform-domains-cloudflare): add the DNS resolution layer

resolve() is the one monkeypatchable seam, copied from find-platform-domains-dns
along with MalformedNameError and the one-retry wrapper.  resolve_target() returns
both rrsets sorted by ip_address() value -- measured 2026-07-31, two live AAAA
queries returned the same pair in opposite orders -- and distinguishes a definitive
absence ([]) from an indeterminate lookup (null).  SPEC R3, 5.2, R4.4.

Nothing calls it yet."
```

---

## Task 3: `zone_name`, the raw `name`, and ambiguity exclusion

Implements **R4.1**, **R4.2** (the `name`/`zone_name` half) and gate-table rows **1–2**. This is
the task that changes the inventory's meaning, so it is also where the existing tests in test
group 10 get rewritten.

**Files:**
- Modify: `find-platform-domains-cloudflare` (`collect_entries` :316; `SweepResult` :539;
  `fetch_platform_cnames` :627)
- Test: `tests/unit/test_find_platform_domains_cloudflare.py`

**Interfaces:**
- Consumes: nothing from Tasks 1–2.
- Produces:
  - `collect_entries(zone_records)` now consumes `(zone_id, zone_name, dns_record)` **triples**
    and returns `(entries, warnings, excluded)` — a **3-tuple**, was a 2-tuple
  - each entry gains `"name"` (raw `record.name`) and `"zone_name"`
  - `SweepResult` gains a **tenth** field, `excluded: Mapping = MappingProxyType({})`
  - excluded values are `{"reason": str, "detail": str, "zone_ids": list, "origins": list}`

---

- [ ] **Step 1: Write the failing tests**

```python
# --- Task 3: zone_name, the raw name, and ambiguity exclusion --------------------------------

def test_collect_entries_records_the_raw_name_and_the_zone_name(fpc):
    """The inventory key is normalize()d, but a batch POST body's `name` must be exactly what
    Cloudflare holds -- Punycode included (R4.2)."""
    entries, warnings, excluded = fpc.collect_entries(
        [("zone-a", "example.edu", record(name="WWW.Example.edu"))])
    assert list(entries) == ["www.example.edu"]
    assert entries["www.example.edu"]["name"] == "WWW.Example.edu"
    assert entries["www.example.edu"]["zone_name"] == "example.edu"
    assert (warnings, excluded) == ([], {})


def test_collect_entries_excludes_a_name_with_two_platform_cnames_in_one_zone(fpc):
    """R4.1: the entry would keep the FIRST record_id of two and present it as actionable."""
    entries, warnings, excluded = fpc.collect_entries([
        ("zone-a", "example.edu", record(name="a.example.edu", id="rec-1",
                                         content="live-one.pantheonsite.io")),
        ("zone-a", "example.edu", record(name="a.example.edu", id="rec-2",
                                         content="live-two.pantheonsite.io")),
    ])
    assert entries == {}
    assert excluded["a.example.edu"]["reason"] == "ambiguous-multiple-origins"
    assert excluded["a.example.edu"]["origins"] == ["live-one.pantheonsite.io",
                                                   "live-two.pantheonsite.io"]
    assert excluded["a.example.edu"]["zone_ids"] == ["zone-a"]
    assert warnings, "the operator must still get the ATTENTION line"


def test_collect_entries_excludes_a_name_present_in_two_zones(fpc):
    entries, warnings, excluded = fpc.collect_entries([
        ("zone-a", "example.edu", record(name="a.example.edu", id="rec-1")),
        ("zone-b", "example.org", record(name="a.example.edu", id="rec-2")),
    ])
    assert entries == {}
    assert excluded["a.example.edu"]["reason"] == "ambiguous-multiple-zones"
    assert excluded["a.example.edu"]["zone_ids"] == ["zone-a", "zone-b"]


def test_a_cross_zone_duplicate_outranks_a_same_zone_duplicate(fpc):
    """One FQDN carries exactly one reason code (SPEC 6).  Cross-zone is the more serious
    finding -- it means two Cloudflare zones both answer for the name -- so it wins."""
    entries, _warnings, excluded = fpc.collect_entries([
        ("zone-a", "example.edu", record(name="a.example.edu", id="rec-1",
                                         content="live-one.pantheonsite.io")),
        ("zone-a", "example.edu", record(name="a.example.edu", id="rec-2",
                                         content="live-two.pantheonsite.io")),
        ("zone-b", "example.org", record(name="a.example.edu", id="rec-3")),
    ])
    assert entries == {}
    assert excluded["a.example.edu"]["reason"] == "ambiguous-multiple-zones"


def test_an_unambiguous_neighbour_survives_an_ambiguous_entry(fpc):
    """Exclusion is per-FQDN, never per-zone or per-run."""
    entries, _warnings, excluded = fpc.collect_entries([
        ("zone-a", "example.edu", record(name="a.example.edu", id="rec-1")),
        ("zone-b", "example.org", record(name="a.example.edu", id="rec-2")),
        ("zone-a", "example.edu", record(name="b.example.edu", id="rec-3")),
    ])
    assert list(entries) == ["b.example.edu"]
    assert list(excluded) == ["a.example.edu"]


def test_fetch_platform_cnames_carries_the_excluded_map_on_the_sweep_result(fpc):
    client = FakeCloudflareClient(
        accounts=[account()],
        zones=[zone("zone-a"), zone("zone-b", "example.org")],
        pages_by_zone={
            "zone-a": [FakePage([[record(name="a.example.edu", id="rec-1")]], total_count=1)],
            "zone-b": [FakePage([[record(name="a.example.edu", id="rec-2")]], total_count=1)],
        })
    sweep = fpc.fetch_platform_cnames(client)
    assert sweep.entries == {}
    assert sweep.excluded["a.example.edu"]["reason"] == "ambiguous-multiple-zones"


def test_the_sweep_result_excluded_default_cannot_be_mutated(fpc):
    """A shared mutable default on a NamedTuple is a cross-test contamination bug waiting to
    happen; MappingProxyType makes an attempted write loud (PD#14)."""
    sweep = fpc.SweepResult({}, [], 1, 2, 5, 1, 0, 0, 187)
    with pytest.raises(TypeError):
        sweep.excluded["oops"] = {}
```

- [ ] **Step 2: Run them and confirm they fail**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_cloudflare.py -k "collect_entries or cross_zone or unambiguous_neighbour or excluded_map or excluded_default"
```

Expected: the `collect_entries` tests fail on `ValueError: too many values to unpack` (it returns
a 2-tuple) or `ValueError: not enough values to unpack` (it consumes pairs); the `SweepResult`
tests fail on `AttributeError: 'SweepResult' object has no attribute 'excluded'`.

- [ ] **Step 3: Rewrite `collect_entries`**

Replace the body of `collect_entries` (:316–373). Keep the existing docstring's first three
paragraphs and add the ambiguity paragraph:

```python
def collect_entries(zone_records):
    """Fold (zone_id, zone_name, record) triples into the inventory.

    Returns (entries, warnings, excluded).

    A record is kept only when it is a CNAME whose content is a *.pantheonsite.io hostname.
    Proxy status is NOT part of the test -- that is exactly what separates this script from
    fqdns.json, which is built with proxied=True and therefore cannot see a DNS-only record.

    Every scalar (zone_id, zone_name, record_id, proxied, ttl, comment, tags, settings) is
    FIRST-RECORD-WINS.  `origins` accumulates every match.

    AMBIGUITY (SPEC R4.1): an FQDN with more than one platform CNAME -- in one zone or across
    two -- is REMOVED from `entries` entirely and reported in `excluded`.  It used to stay, with
    the FIRST record_id of two, which presented an unrewritable entry as if it were actionable;
    select_zones()'s docstring already records that a rewriter pointed at one of two records has
    no way to know.  A cross-zone duplicate outranks a same-zone one: it is the more serious
    finding, and one FQDN carries exactly one reason code.

    `zone_records` is consumed lazily, so the caller can hand over a generator and the whole
    organization's record set is never held in memory at once.
    """
    entries = {}
    warnings = []
    reasons = {}            # fqdn -> reason code; the detail is built from `entries` below
    zone_ids = {}           # fqdn -> [zone_id, ...] in first-seen order
    for zone_id, zone_name, dns_record in zone_records:
        if getattr(dns_record, "type", None) != "CNAME":
            continue
        content = getattr(dns_record, "content", None)
        if content is None or not is_platform_domain(content):
            continue
        name = normalize(dns_record.name)
        entry = entries.get(name)
        if entry is None:
            entries[name] = {
                # The RAW record name, not the normalized key: a batch POST body's `name` must
                # be exactly what Cloudflare holds, Punycode included (SPEC R4.2).
                "name": str(dns_record.name),
                "zone_id": zone_id,
                "zone_name": zone_name,
                "origins": [content],
                "record_id": dns_record.id,
                # Stored VERBATIM, never coerced.  proxied is Optional[bool] on every record
                # model, and research.md is explicit that "proxied: true is the load-bearing
                # field in both directions" -- a None flattened to false would inflate the
                # DNS-only count AND instruct a rewriter to re-create a proxied hostname
                # unproxied, taking it out of certificate service.  An unknown stays null and
                # classify() excludes it.
                "proxied": getattr(dns_record, "proxied", None),
                "ttl": getattr(dns_record, "ttl", None),
                "comment": getattr(dns_record, "comment", None),
                "tags": list(getattr(dns_record, "tags", None) or []),
                "settings": plain(getattr(dns_record, "settings", None)),
            }
            zone_ids[name] = [zone_id]
            continue
        entry["origins"].append(content)
        if zone_id not in zone_ids[name]:
            zone_ids[name].append(zone_id)
        # Warn on EVERY duplicate, not only a cross-zone one.  The same-zone case is one the
        # Cloudflare API should make unreachable (a name may hold at most one CNAME), which makes
        # a warning there a signal worth seeing rather than noise.
        if entry["zone_id"] == zone_id:
            reasons.setdefault(name, "ambiguous-multiple-origins")
            warnings.append(
                f"ATTENTION: {name} has more than one platform-domain CNAME in zone {zone_id}, "
                "which the Cloudflare API should not permit; it is omitted from the inventory "
                "and gets no rewrite plan")
        else:
            reasons[name] = "ambiguous-multiple-zones"   # NOT setdefault: cross-zone outranks
            warnings.append(
                f"ATTENTION: {name} has a platform-domain CNAME in more than one Cloudflare "
                f"zone ({entry['zone_id']} and {zone_id}); it is omitted from the inventory and "
                "gets no rewrite plan")

    excluded = {}
    for name, reason in reasons.items():
        entry = entries.pop(name)
        excluded[name] = {
            "reason": reason,
            "detail": (f"{len(entry['origins'])} platform-domain CNAMEs in zone(s) "
                       f"{', '.join(zone_ids[name])}; the record to rewrite is ambiguous, so "
                       "this FQDN is omitted from the inventory, the plan and the revert"),
            "zone_ids": zone_ids[name],
            "origins": entry["origins"],
        }
    return entries, warnings, excluded
```

- [ ] **Step 4: Extend `SweepResult` and `fetch_platform_cnames`**

Add `from types import MappingProxyType` to the import block. Append one field to `SweepResult`,
after `zones_total`:

```python
    # Ambiguous FQDNs, keyed by normalized name (SPEC R4.1).  They are NOT in `entries`.
    # MappingProxyType, not {}: a NamedTuple default is a single shared instance, and a mutable
    # one would leak between runs and between tests.  An attempted write raises (PD#14).
    excluded: Mapping = MappingProxyType({})
```

Add `from collections.abc import Mapping` to the import block.

In `fetch_platform_cnames`, yield triples and unpack three values:

```python
            for dns_record in records:
                yield zone.id, zone.name, dns_record
```

```python
    try:
        entries, warnings, excluded = collect_entries(zone_records())
    except cloudflare.CloudflareError as e:
        raise StartupError(f"listing DNS records failed: {api_error_text(e)}") from e

    return SweepResult(entries, warnings, len(accounts), len(zones), seen["records"],
                       tally.complete, tally.short, tally.unverifiable, zones_total, excluded)
```

- [ ] **Step 5: Run the whole file and rewrite what goes red**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_cloudflare.py
```

Existing tests that will fail, and the **only** sanctioned response to each:

| Failing test | Response |
|---|---|
| any `collect_entries` test passing 2-tuples | Update the call to pass `(zone_id, zone_name, record)` triples and unpack 3 values. A rename, not a weakening. |
| tests asserting an ambiguous entry **appears** in `entries` with accumulated `origins` | **Rewrite** to assert it appears in `excluded` and is absent from `entries`, and keep an assertion that the warning is still produced. Add a comment naming SPEC R4.1 as the reason the expectation changed. |
| tests asserting the exact `ATTENTION:` wording for a duplicate | Update the expected substring to the new wording. |
| `ENTRY` / `ENTRY`-shaped fixtures compared with `==` against a written file | Add `"name"` and `"zone_name"` to the fixture. |

**NEVER** delete one of these tests, and **NEVER** loosen an assertion to `assert True` or to a
`in` test that would pass either way. If a test cannot be rewritten to assert the new behavior,
stop and report it rather than removing it.

- [ ] **Step 6: Confirm green, then commit**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_cloudflare.py
git diff --stat find-platform-domains-dns tests/unit/test_find_platform_domains_dns.py
# Expected: empty output.
git add find-platform-domains-cloudflare tests/unit/test_find_platform_domains_cloudflare.py
git commit -m "feat(find-platform-domains-cloudflare)!: omit ambiguous FQDNs from the inventory

An FQDN with more than one platform CNAME -- in one zone or across two -- used to stay
in the inventory carrying the FIRST record_id of two, presenting an entry no rewriter
can safely act on as if it were actionable.  It is now removed and reported in a new
SweepResult.excluded map, with a cross-zone duplicate outranking a same-zone one.

Entries also gain the raw record name (a batch POST body's \`name\` must be exactly what
Cloudflare holds) and the zone name (for human filtering).

BREAKING: the inventory's contents and shape both change.  SPEC R4.1, R4.2."
```

---

## Task 4: `classify`, the reason codes, and the resolution wiring

Implements the rest of **R4.2**, **R4.4**, **R7** and gate-table rows **3–8**, plus exit **1**
(§8). After this task the inventory carries `resolved_a`/`resolved_aaaa`, exclusions are reported,
and the exit code reflects them — but no plan file exists yet.

**Files:**
- Modify: `find-platform-domains-cloudflare` (new `classify`; `main` :792; `summarize` :719)
- Test: `tests/unit/test_find_platform_domains_cloudflare.py`

**Interfaces:**
- Consumes: `Resolution`, `resolve_target` (Task 2); `SweepResult.excluded` (Task 3).
- Produces:
  - `PLATFORM_A_RANGE = ipaddress.ip_network("23.185.0.0/24")`
  - `PLATFORM_AAAA_RANGE = ipaddress.ip_network("2620:12a::/32")`
  - `classify(entry: dict, resolution: Resolution) -> tuple[str | None, str]` —
    `(reason_code, detail)`; `(None, "")` when the entry qualifies for a plan
  - `main` returns `1` when anything was excluded

---

- [ ] **Step 1: Write the failing tests**

```python
# --- Task 4: classify and the reason codes ---------------------------------------------------

def swept(**overrides):
    """An inventory entry as collect_entries builds one."""
    entry = {"name": "a.example.edu", "zone_id": "zone-a", "zone_name": "example.edu",
             "origins": ["live-a.pantheonsite.io"], "record_id": "rec-1", "proxied": True,
             "ttl": 1, "comment": None, "tags": [], "settings": None}
    entry.update(overrides)
    return entry


GOOD = None   # placeholder rebound in each test via fpc.Resolution


def test_classify_passes_a_healthy_proxied_entry(fpc):
    resolution = fpc.Resolution(["23.185.0.4"], ["2620:12a:8000::4"], "")
    assert fpc.classify(swept(), resolution) == (None, "")


def test_classify_passes_a_dns_only_entry(fpc):
    """5 of 218 in the last live sweep.  The swap is type-only and preserves proxied=false,
    so a DNS-only entry is NOT excluded (SPEC 6)."""
    resolution = fpc.Resolution(["23.185.0.4"], ["2620:12a:8000::4"], "")
    assert fpc.classify(swept(proxied=False), resolution) == (None, "")


def test_classify_excludes_an_unknown_proxy_status(fpc):
    resolution = fpc.Resolution(["23.185.0.4"], ["2620:12a:8000::4"], "")
    reason, detail = fpc.classify(swept(proxied=None), resolution)
    assert reason == "unknown-proxy-status"
    assert "null" in detail


def test_classify_excludes_an_indeterminate_resolution_before_testing_for_no_a(fpc):
    """SPEC 6, evaluation order: resolution-failed (8) MUST be tested before no-a (4).  With
    `a` null, a `not a` test treats "we do not know" and "definitively none" alike, and would
    report a timeout as "the target has no A records" (R4.4)."""
    resolution = fpc.Resolution(None, None, "Timeout resolving A for live-a.pantheonsite.io")
    reason, detail = fpc.classify(swept(), resolution)
    assert reason == "resolution-failed"
    assert "Timeout" in detail


def test_classify_excludes_a_target_with_no_a_records(fpc):
    resolution = fpc.Resolution([], ["2620:12a:8000::4"], "")
    assert fpc.classify(swept(), resolution)[0] == "no-a"


def test_classify_excludes_an_a_record_outside_the_pantheon_range(fpc):
    resolution = fpc.Resolution(["104.18.2.7"], ["2620:12a:8000::4"], "")
    reason, detail = fpc.classify(swept(), resolution)
    assert reason == "platform-a-out-of-range"
    assert "104.18.2.7" in detail
    assert "23.185.0.0/24" in detail


def test_classify_excludes_a_mixed_a_rrset_even_though_one_address_is_in_range(fpc):
    """SPEC 6: EVERY resolved A must be in range, not merely one.  Under a >=1 rule the plan
    would post 104.18.2.7 as a proxied origin."""
    resolution = fpc.Resolution(["23.185.0.4", "104.18.2.7"], ["2620:12a:8000::4"], "")
    assert fpc.classify(swept(), resolution)[0] == "platform-a-out-of-range"


def test_classify_excludes_a_target_with_no_aaaa_records(fpc):
    resolution = fpc.Resolution(["23.185.0.4"], [], "")
    assert fpc.classify(swept(), resolution)[0] == "no-aaaa"


def test_classify_excludes_an_aaaa_record_outside_the_pantheon_range(fpc):
    resolution = fpc.Resolution(["23.185.0.4"], ["2606:4700::1111"], "")
    reason, detail = fpc.classify(swept(), resolution)
    assert reason == "platform-aaaa-out-of-range"
    assert "2620:12a::/32" in detail


def test_classify_accepts_both_live_observed_address_sets(fpc):
    """Measured 2026-07-31 against live DNS; a range that rejected either would be wrong."""
    for a, aaaa in ((["23.185.0.4"], ["2620:12a:8000::4", "2620:12a:8001::4"]),
                    (["23.185.0.1"], ["2620:12a:8000::1", "2620:12a:8001::1"])):
        assert fpc.classify(swept(), fpc.Resolution(a, aaaa, "")) == (None, "")
```

And the `main()`-level tests:

```python
def test_main_records_the_resolved_addresses_on_each_inventory_entry(fpc, tmp_path, monkeypatch,
                                                                     capsys):
    """R4.2/Expansion 2: the inventory carries the evidence behind every plan entry."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": swept()}, [], 1, 2, 5, 1, 0, 0, 2))
    fake_dns(fpc, monkeypatch, {
        ("live-a.pantheonsite.io", "A"): ["23.185.0.4"],
        ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8000::4", "2620:12a:8001::4"],
    })
    assert fpc.main([]) == 0
    written = json.loads(capsys.readouterr().out)
    assert written["a.example.edu"]["resolved_a"] == ["23.185.0.4"]
    assert written["a.example.edu"]["resolved_aaaa"] == ["2620:12a:8000::4", "2620:12a:8001::4"]


def test_main_resolves_in_stdout_mode_too(fpc, tmp_path, monkeypatch, capsys):
    """R3.2: if resolution were basename-mode only, the two modes would produce different
    inventories for the same sweep -- the divergence dump_json() exists to prevent."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": swept()}, [], 1, 2, 5, 1, 0, 0, 2))
    calls = fake_dns(fpc, monkeypatch, {
        ("live-a.pantheonsite.io", "A"): ["23.185.0.4"],
        ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8000::4"],
    })
    assert fpc.main([]) == 0
    assert calls == [("live-a.pantheonsite.io", "A"), ("live-a.pantheonsite.io", "AAAA")]


def test_main_exits_1_and_names_every_exclusion_on_stderr(fpc, tmp_path, monkeypatch, capsys):
    """R7.1/R7.3: unconditional, not -v-gated.  A file that drives a destructive rewrite while
    the warnings about it go nowhere is the failure this design is organized against."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": swept()}, [], 1, 2, 5, 1, 0, 0, 2))
    fake_dns(fpc, monkeypatch, {("live-a.pantheonsite.io", "A"): ["104.18.2.7"],
                                ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8000::4"]})
    assert fpc.main([]) == 1
    err = capsys.readouterr().err
    assert "a.example.edu" in err
    assert "platform-a-out-of-range" in err


def test_main_exits_1_for_an_ambiguous_entry_in_stdout_mode(fpc, tmp_path, monkeypatch, capsys):
    """The one exclusion detectable without DNS, and the one that also leaves the inventory."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult(
        {}, [], 1, 2, 5, 1, 0, 0, 2,
        {"a.example.edu": {"reason": "ambiguous-multiple-zones", "detail": "two zones",
                           "zone_ids": ["z1", "z2"], "origins": ["live-a.pantheonsite.io"]}}))
    assert fpc.main([]) == 1
    assert json.loads(capsys.readouterr().out) == {}


def test_main_exits_0_when_nothing_was_excluded(fpc, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": swept()}, [], 1, 2, 5, 1, 0, 0, 2))
    fake_dns(fpc, monkeypatch, {("live-a.pantheonsite.io", "A"): ["23.185.0.4"],
                                ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8000::4"]})
    assert fpc.main([]) == 0


def test_an_indeterminate_lookup_leaves_null_in_the_inventory_not_an_empty_list(
        fpc, tmp_path, monkeypatch, capsys):
    """R4.4 end to end: [] would tell an operator the target has no addresses."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult({"a.example.edu": swept()}, [], 1, 2, 5, 1, 0, 0, 2))
    fake_dns(fpc, monkeypatch, {("live-a.pantheonsite.io", "A"): dns.resolver.Timeout()})
    assert fpc.main([]) == 1
    written = json.loads(capsys.readouterr().out)
    assert written["a.example.edu"]["resolved_a"] is None
    assert written["a.example.edu"]["resolved_aaaa"] is None
```

- [ ] **Step 2: Run them and confirm they fail**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_cloudflare.py -k "classify or resolved_addresses or stdout_mode_too or exits_1 or exits_0 or indeterminate_lookup"
```

Expected: `AttributeError: ... 'classify'` for the first group; the `main()` group fails on the
missing `resolved_a` key or on `assert 0 == 1`.

- [ ] **Step 3: Implement `classify`**

Add near `PLATFORM_SUFFIX` (:55):

```python
# Pantheon's edge address ranges.  Measured live 2026-07-31 across two sites: 23.185.0.1 and
# 23.185.0.4, 2620:12a:8000::1/::4 and 2620:12a:8001::1/::4.  A replacement record outside these
# is not Pantheon's, and a plan MUST NOT post it as a proxied origin (SPEC 6, rows 5 and 7).
PLATFORM_A_RANGE = ipaddress.ip_network("23.185.0.0/24")
PLATFORM_AAAA_RANGE = ipaddress.ip_network("2620:12a::/32")
```

Add after `resolve_target`:

```python
def outside(addresses, network):
    """The addresses that are NOT in `network`, in the order given."""
    return [a for a in addresses if ipaddress.ip_address(a) not in network]


def classify(entry, resolution):
    """(reason_code, detail) for an entry that must be excluded, else (None, "").

    THE ORDER IS LOAD-BEARING and is SPEC section 6's: unknown-proxy-status, then
    resolution-failed, then the four resolution outcomes.  resolution-failed MUST come before
    no-a: `resolution.a` is None for an indeterminate lookup and [] for a definitive absence
    (SPEC R4.4), and a `not resolution.a` test cannot tell them apart -- so testing no-a first
    would report a timeout as "the target definitively has no A records", a claim the run never
    established.

    Both range tests require EVERY address to be in range, not merely one.  SPEC section 6 records
    why: under a >=1 rule a target resolving to [23.185.0.4, 104.18.2.7] passes and the plan then
    posts the foreign address as a proxied origin.
    """
    if entry["proxied"] is None:
        return ("unknown-proxy-status",
                "proxied is null, not false -- whether the replacement records must be created "
                "proxied cannot be determined, and guessing either way is unsafe")
    if resolution.problem:
        return "resolution-failed", resolution.problem
    if not resolution.a:
        return "no-a", f"{entry['origins'][0]} resolved to no A records"
    stray = outside(resolution.a, PLATFORM_A_RANGE)
    if stray:
        return ("platform-a-out-of-range",
                f"{entry['origins'][0]} resolved to A {', '.join(stray)}, which is not in "
                f"{PLATFORM_A_RANGE}")
    if not resolution.aaaa:
        return "no-aaaa", f"{entry['origins'][0]} resolved to no AAAA records"
    stray = outside(resolution.aaaa, PLATFORM_AAAA_RANGE)
    if stray:
        return ("platform-aaaa-out-of-range",
                f"{entry['origins'][0]} resolved to AAAA {', '.join(stray)}, which is not in "
                f"{PLATFORM_AAAA_RANGE}")
    return None, ""
```

- [ ] **Step 4: Wire resolution into `main`**

Replace `main`'s body between the sweep and `emit` with:

```python
        sweep = fetch_platform_cnames(client, verbose=options.verbose,
                                      zone_names=options.zones)
        for message in sweep.warnings:
            print(message, file=sys.stderr, flush=True)
        excluded = dict(sweep.excluded)
        for fqdn, entry in sorted(sweep.entries.items()):
            target = entry["origins"][0]
            resolution = resolve_target(target)
            entry["resolved_a"] = resolution.a
            entry["resolved_aaaa"] = resolution.aaaa
            if options.verbose:
                print(f"{fqdn} -> {target} -> A {resolution.a} | AAAA {resolution.aaaa}",
                      file=sys.stderr, flush=True)
            reason, detail = classify(entry, resolution)
            if reason is not None:
                excluded[fqdn] = {"reason": reason, "detail": detail,
                                  "resolved_a": resolution.a, "resolved_aaaa": resolution.aaaa}
        for fqdn, item in sorted(excluded.items()):
            # NEVER -v-gated (SPEC R7.3): these are the only signal that the result is narrower
            # than it looks, and this run's exit code is the only other one.
            print(f"ATTENTION: {fqdn} excluded ({item['reason']}): {item['detail']}",
                  file=sys.stderr, flush=True)
        try:
            emit(sweep.entries, paths)
        except OSError as e:
            raise StartupError(f"cannot write {destination_name(paths)}: {e}") from e
        wrote = True
        summarize(sweep, excluded, paths)
```

Initialize `excluded = {}` immediately after `wrote = False`, so the final return is never
reached with it unbound, and change the function's last line to:

```python
    return 1 if excluded else 0
```

Update `main`'s docstring exit-code paragraph to name exit 1:

```python
    """Exit 0 = the output was produced with nothing excluded, 1 = produced with exclusions,
    2 = could not complete, 130 = interrupted.

    Exit 1 is new in this increment.  The prior spec stated there was deliberately no exit 1
    because a Cloudflare list call either returns or raises; that reasoning no longer holds now
    that the run also does DNS work and can partially succeed.  The sibling
    find-platform-domains-dns already uses 1 for "completed with indeterminates", so the pair
    stays consistent.
    ...
    """
```

Add an `excluded` parameter to `summarize(sweep, excluded, paths)` and append, before the
zero-match ATTENTION:

```python
    if excluded:
        by_reason = collections.Counter(item["reason"] for item in excluded.values())
        print("Excluded from the rewrite plan: "
              + ", ".join(f"{count} {reason}" for reason, count in sorted(by_reason.items())),
              file=sys.stderr, flush=True)
```

Add `import collections` to the import block.

- [ ] **Step 5: Run the tests and confirm they pass**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_cloudflare.py
```

Existing `main()` tests will need a `fake_dns(...)` call added, since every entry now gets
resolved. Adding the DNS fake to an existing test is **setup**, not a weakening — but any test
whose *assertion* changes must be handled by Step 5's table in Task 3 and reported.

- [ ] **Step 6: Prove exit 1 can go red**

Temporarily change `return 1 if excluded else 0` to `return 0` and re-run:

```bash
./run-tests --fast tests/unit/test_find_platform_domains_cloudflare.py -k "exits_1"
```

Expected: those tests **fail**. Restore the line. Record the observed failure in the task report —
a green check is a claim, not evidence, until it has been shown capable of going red (PD#14).

- [ ] **Step 7: Commit**

```bash
git diff --stat find-platform-domains-dns tests/unit/test_find_platform_domains_dns.py
git add find-platform-domains-cloudflare tests/unit/test_find_platform_domains_cloudflare.py
git commit -m "feat(find-platform-domains-cloudflare): resolve targets and classify exclusions

Every entry's *.pantheonsite.io target is now resolved, in BOTH modes, and the
inventory records what it resolved to.  classify() applies the six resolution-time
gate conditions; resolution-failed is tested before no-a because an indeterminate
lookup is null and a definitive absence is [], and a truthiness test cannot tell them
apart.  Both range checks require EVERY address to be in range: under a >=1 rule a
target resolving to [23.185.0.4, 104.18.2.7] would have the foreign address posted as
a proxied origin.

Exit 1 (\"completed with exclusions\") joins the taxonomy.  SPEC R3, R4.2, R4.4, R7, 6, 8."
```

---

## Task 5: `record_body`, `plan_entry`, `revert_entry`

Implements **R5.1–R5.3**, **R6** and **§5.3/§5.4**. Pure functions; nothing writes them yet.

**Files:**
- Modify: `find-platform-domains-cloudflare` (new code after `classify`)
- Test: `tests/unit/test_find_platform_domains_cloudflare.py`

**Interfaces:**
- Consumes: `Resolution` (Task 2), the entry shape (Task 3), `swept()` test helper (Task 4).
- Produces:
  - `CNAME_ONLY_SETTINGS: tuple[str, ...] = ("flatten_cname",)`
  - `clean_settings(settings, *, drop_cname_only: bool) -> dict | None`
  - `record_body(entry: dict, rtype: str, content: str, settings) -> dict`
  - `plan_entry(entry: dict, resolution: Resolution) -> dict`
  - `revert_entry(entry: dict, resolution: Resolution) -> dict`
  - `proxied_ttl_anomaly(entry: dict) -> bool`

---

- [ ] **Step 1: Write the failing tests**

```python
# --- Task 5: the batch bodies ----------------------------------------------------------------

FULL_SETTINGS = {"flatten_cname": False, "ipv4_only": True, "ipv6_only": None}


def test_clean_settings_drops_flatten_cname_going_forward(fpc):
    """flatten_cname is not a member of the A/AAAA settings schema, and is already inert on a
    proxied CNAME: "unavailable for proxied records, since they are always flattened" (R6)."""
    assert fpc.clean_settings(FULL_SETTINGS, drop_cname_only=True) == {"ipv4_only": True}


def test_clean_settings_keeps_flatten_cname_going_back(fpc):
    assert fpc.clean_settings(FULL_SETTINGS, drop_cname_only=False) == {
        "flatten_cname": False, "ipv4_only": True}


def test_clean_settings_returns_none_when_nothing_survives(fpc):
    """R6.1: an empty settings object is omitted from the body, not sent as {}."""
    assert fpc.clean_settings({"flatten_cname": True}, drop_cname_only=True) is None
    assert fpc.clean_settings(None, drop_cname_only=True) is None
    assert fpc.clean_settings({}, drop_cname_only=False) is None


def test_record_body_always_emits_proxied(fpc):
    """R6: the API default is false, and a silently DNS-only replacement takes the hostname out
    of certificate service."""
    body = fpc.record_body(swept(proxied=False, ttl=300), "A", "23.185.0.4", None)
    assert body["proxied"] is False


def test_record_body_forces_ttl_1_when_proxied(fpc):
    """Cloudflare forces a proxied record's TTL to Auto regardless, and whether the API rejects
    or coerces a non-1 ttl is documented silence we do not build on (R6)."""
    assert fpc.record_body(swept(proxied=True, ttl=300), "A", "23.185.0.4", None)["ttl"] == 1


def test_record_body_carries_a_dns_only_ttl_verbatim(fpc):
    assert fpc.record_body(swept(proxied=False, ttl=300), "A", "23.185.0.4", None)["ttl"] == 300


def test_record_body_omits_a_null_comment_and_empty_tags(fpc):
    body = fpc.record_body(swept(), "A", "23.185.0.4", None)
    assert "comment" not in body
    assert "tags" not in body
    assert "settings" not in body


def test_record_body_carries_a_comment_and_tags(fpc):
    body = fpc.record_body(swept(comment="owned by ITS", tags=["team:wws"]),
                           "A", "23.185.0.4", {"ipv4_only": True})
    assert body["comment"] == "owned by ITS"
    assert body["tags"] == ["team:wws"]
    assert body["settings"] == {"ipv4_only": True}


def test_record_body_uses_the_raw_record_name(fpc):
    assert fpc.record_body(swept(name="WWW.Example.edu"), "A", "23.185.0.4", None)["name"] == \
        "WWW.Example.edu"


def test_proxied_ttl_anomaly_flags_a_proxied_record_whose_ttl_is_not_1(fpc):
    assert fpc.proxied_ttl_anomaly(swept(proxied=True, ttl=300)) is True
    assert fpc.proxied_ttl_anomaly(swept(proxied=True, ttl=1)) is False
    assert fpc.proxied_ttl_anomaly(swept(proxied=False, ttl=300)) is False


def test_plan_entry_deletes_the_cname_and_posts_the_addresses(fpc):
    resolution = fpc.Resolution(["23.185.0.4"],
                                ["2620:12a:8000::4", "2620:12a:8001::4"], "")
    entry = fpc.plan_entry(swept(settings=FULL_SETTINGS), resolution)
    assert entry["zone_id"] == "zone-a"
    assert entry["method"] == "POST"
    assert entry["path"] == "/zones/zone-a/dns_records/batch"
    assert entry["delete_match"] == [
        {"type": "CNAME", "name": "a.example.edu", "content": "live-a.pantheonsite.io"}]
    assert [p["type"] for p in entry["body"]["posts"]] == ["A", "AAAA", "AAAA"]
    assert [p["content"] for p in entry["body"]["posts"]] == [
        "23.185.0.4", "2620:12a:8000::4", "2620:12a:8001::4"]
    assert all(p["settings"] == {"ipv4_only": True} for p in entry["body"]["posts"])


def test_plan_entry_keeps_delete_match_outside_the_body(fpc):
    """R5.3: `body` must be a real, postable batch body at all times.  A shape like
    {"deletes": [{"match": ...}]} looks postable and is not."""
    entry = fpc.plan_entry(swept(), fpc.Resolution(["23.185.0.4"], ["2620:12a:8000::4"], ""))
    assert set(entry["body"]) == {"posts"}
    assert "deletes" not in entry["body"]


def test_revert_entry_deletes_the_addresses_and_restores_the_cname(fpc):
    resolution = fpc.Resolution(["23.185.0.4"],
                                ["2620:12a:8000::4", "2620:12a:8001::4"], "")
    entry = fpc.revert_entry(swept(settings=FULL_SETTINGS, comment="note", tags=["t:1"]),
                             resolution)
    assert entry["delete_match"] == [
        {"type": "A", "name": "a.example.edu", "content": "23.185.0.4"},
        {"type": "AAAA", "name": "a.example.edu", "content": "2620:12a:8000::4"},
        {"type": "AAAA", "name": "a.example.edu", "content": "2620:12a:8001::4"}]
    post, = entry["body"]["posts"]
    assert post["type"] == "CNAME"
    assert post["content"] == "live-a.pantheonsite.io"
    assert post["settings"] == {"flatten_cname": False, "ipv4_only": True}


def test_the_revert_reproduces_every_writable_field_of_the_swept_cname(fpc):
    """R5.4, the round-trip property.  The writable CNAME fields are exactly name, type, content,
    ttl, proxied, settings, tags, comment (SPEC R4.3)."""
    entry = swept(settings={"flatten_cname": True, "ipv4_only": False, "ipv6_only": False},
                  comment="owned by ITS", tags=["team:wws"], proxied=False, ttl=300)
    post, = fpc.revert_entry(entry, fpc.Resolution(["23.185.0.4"], ["2620:12a:8000::4"], "")
                             )["body"]["posts"]
    assert post == {"type": "CNAME", "name": "a.example.edu",
                    "content": "live-a.pantheonsite.io", "proxied": False, "ttl": 300,
                    "settings": {"flatten_cname": True, "ipv4_only": False, "ipv6_only": False},
                    "comment": "owned by ITS", "tags": ["team:wws"]}


def test_plan_entry_refuses_an_entry_with_more_than_one_origin(fpc):
    """An ambiguous entry never reaches here (Task 3 removes it).  The invariant is asserted
    rather than assumed, because a silent [0] would rewrite one of two records."""
    with pytest.raises(fpc.StartupError):
        fpc.plan_entry(swept(origins=["live-a.pantheonsite.io", "live-b.pantheonsite.io"]),
                       fpc.Resolution(["23.185.0.4"], ["2620:12a:8000::4"], ""))
```

- [ ] **Step 2: Run them and confirm they fail**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_cloudflare.py -k "clean_settings or record_body or plan_entry or revert_entry or proxied_ttl_anomaly or writable_field"
```

Expected: `AttributeError` for each new name.

- [ ] **Step 3: Implement the body builders**

Add after `classify`:

```python
# Settings keys that exist on a CNAME record but NOT on an A/AAAA record.  Verified against the
# spec-generated SDK models in cloudflare/types/dns/{a,aaaa,cname}_record.py: A and AAAA carry
# ipv4_only and ipv6_only; CNAME carries those PLUS flatten_cname.  Whether an out-of-type key is
# rejected or ignored is documented silence, so it is stripped client-side (SPEC R6).
CNAME_ONLY_SETTINGS = ("flatten_cname",)


def clean_settings(settings, *, drop_cname_only):
    """The `settings` value for a batch body, or None when the key should be omitted.

    ipv4_only/ipv6_only are carried BOTH ways.  They look CNAME-irrelevant and are not: they are
    valid on all three types, and "this option only applies to proxied records" -- which is
    precisely the case here.  Dropping them would change which address families Cloudflare
    advertises at the edge for that hostname.

    Null-valued keys are dropped (SPEC R6.1): the SDK's model_dump emits every declared field,
    so an unset setting arrives as None, and sending it back adds nothing the API's own default
    does not already do.
    """
    if not isinstance(settings, dict):
        return None
    kept = {key: value for key, value in settings.items()
            if value is not None and not (drop_cname_only and key in CNAME_ONLY_SETTINGS)}
    return kept or None


def proxied_ttl_anomaly(entry):
    """True when a PROXIED record's swept ttl is not 1 -- which should be impossible.

    Cloudflare forces a proxied record's TTL to Auto, so a stored value other than 1 means an
    assumption behind record_body's ttl rule is wrong and the operator should hear about it.
    """
    return bool(entry["proxied"]) and entry["ttl"] not in (None, 1)


def record_body(entry, rtype, content, settings):
    """One `posts` item, applying every carry-over rule in SPEC R6.

    `proxied` is ALWAYS emitted: its API default is false, and a replacement created DNS-only
    would take the hostname out of certificate service ("Cloudflare can only serve an SSL/TLS
    certificate for a DNS record when you set the record's proxy status to Proxied").

    `ttl` is forced to 1 for a proxied record.  Cloudflare forces it to Auto regardless ("all
    proxied records have a time to live (TTL) of Auto ... This value cannot be edited"), and
    whether the API rejects or silently coerces a non-1 value is documented silence.  A DNS-only
    record's ttl is carried verbatim; a missing one falls back to 1 ("automatic"), because ttl is
    a required field and there is no better answer.
    """
    body = {"type": rtype,
            # the RAW name Cloudflare holds, never the normalized inventory key (SPEC R4.2)
            "name": entry["name"],
            "content": content,
            "proxied": entry["proxied"],
            "ttl": 1 if entry["proxied"] or not entry["ttl"] else entry["ttl"]}
    if settings is not None:
        body["settings"] = settings
    if entry["comment"] is not None:
        body["comment"] = entry["comment"]
    if entry["tags"]:
        body["tags"] = list(entry["tags"])
    return body


def sole_origin(entry):
    """The entry's one platform-domain target.

    An entry reaching a body builder has exactly one origin: collect_entries removes every
    ambiguous FQDN (SPEC R4.1).  Asserted rather than assumed -- a silent origins[0] would aim a
    destructive rewrite at one of two records, which is the exact failure that exclusion exists
    to prevent.
    """
    if len(entry["origins"]) != 1:
        raise StartupError(
            f"internal invariant violated: {entry['name']} reached a batch-body builder with "
            f"{len(entry['origins'])} origins; ambiguous entries must have been excluded")
    return entry["origins"][0]


def batch_envelope(entry, delete_match, posts):
    """The fields every plan and revert entry shares (SPEC 5.3, 5.4).

    `delete_match` lives OUTSIDE `body` on purpose: batch `deletes` items are exactly {"id": ...}
    and the ids of records the plan has not created yet cannot be known, so an applier resolves
    the match to ids at apply time.  Keeping it out of `body` means `body` is a real, postable
    batch body at all times and cannot be mistaken for a complete request (SPEC R5.3).
    """
    return {"zone_id": entry["zone_id"],
            "method": "POST",
            "path": f"/zones/{entry['zone_id']}/dns_records/batch",
            "delete_match": delete_match,
            "body": {"posts": posts}}


def plan_entry(entry, resolution):
    """Forward rewrite: delete the platform CNAME, create the resolved A/AAAA records."""
    origin = sole_origin(entry)
    settings = clean_settings(entry["settings"], drop_cname_only=True)
    posts = [record_body(entry, "A", address, settings) for address in resolution.a]
    posts += [record_body(entry, "AAAA", address, settings) for address in resolution.aaaa]
    return batch_envelope(
        entry,
        [{"type": "CNAME", "name": entry["name"], "content": origin}],
        posts)


def revert_entry(entry, resolution):
    """Reverse rewrite: delete the A/AAAA records, restore the platform CNAME verbatim.

    The restored settings are the ORIGINAL CNAME's, flatten_cname included -- it is what the API
    itself returned for that record, so posting it back is what round-trips (SPEC R5.4).
    """
    origin = sole_origin(entry)
    settings = clean_settings(entry["settings"], drop_cname_only=False)
    delete_match = [{"type": "A", "name": entry["name"], "content": address}
                    for address in resolution.a]
    delete_match += [{"type": "AAAA", "name": entry["name"], "content": address}
                     for address in resolution.aaaa]
    return batch_envelope(entry, delete_match,
                          [record_body(entry, "CNAME", origin, settings)])
```

- [ ] **Step 4: Run the tests and confirm they pass**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_cloudflare.py
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git diff --stat find-platform-domains-dns tests/unit/test_find_platform_domains_dns.py
git add find-platform-domains-cloudflare tests/unit/test_find_platform_domains_cloudflare.py
git commit -m "feat(find-platform-domains-cloudflare): build the batch plan and revert bodies

plan_entry/revert_entry produce the Cloudflare DNS batch bodies for the swap and its
undo.  delete_match lives OUTSIDE body because batch deletes identify records by id
alone and the plan's posts have not minted theirs yet -- and because a body that is
always postable cannot be mistaken for a complete request.

Carry-over follows SPEC R6: flatten_cname is dropped going forward (not an A/AAAA
field, and inert on a proxied CNAME) and restored going back; ipv4_only/ipv6_only are
carried both ways because they are valid on all three types and apply precisely to
proxied records; proxied is always explicit; a proxied ttl is forced to 1.

Nothing writes them yet."
```

---

## Task 6: The four files, provenance, and the operator report

Implements **R2** (the four-file half), **R5.5**, **§5.5**, **§5.6**, **§9.3–§9.5** and **§10**.

**Files:**
- Modify: `find-platform-domains-cloudflare` (new `now_utc`/`provenance`/`write_outputs`;
  `emit`; `interrupt_message`; `summarize`; `main`)
- Test: `tests/unit/test_find_platform_domains_cloudflare.py`

**Interfaces:**
- Consumes: everything from Tasks 1–5.
- Produces:
  - `now_utc()` — **the one clock seam**
  - `provenance(argv, sweep, direction, count) -> dict`
  - `write_outputs(paths, inventory, plan, revert, excluded) -> None`
  - `emit(inventory, paths, plan, revert, excluded) -> None`

---

- [ ] **Step 1: Write the failing tests**

```python
# --- Task 6: the four files ------------------------------------------------------------------

def freeze_clock(fpc, monkeypatch, stamp="2026-07-31T14:02:11Z"):
    """Pin the ONE clock seam, so all three headed files are byte-deterministic (SPEC 5.5)."""
    monkeypatch.setattr(fpc, "now_utc", lambda: stamp)
    return stamp


def planned_run(fpc, monkeypatch, tmp_path):
    """A one-entry sweep that resolves cleanly, plus a frozen clock."""
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch,
               fpc.SweepResult({"a.example.edu": swept()}, [], 1, 2, 5, 1, 0, 0, 187))
    fake_dns(fpc, monkeypatch, {
        ("live-a.pantheonsite.io", "A"): ["23.185.0.4"],
        ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8000::4", "2620:12a:8001::4"],
    })
    return freeze_clock(fpc, monkeypatch)


def test_basename_mode_writes_all_four_files(fpc, tmp_path, monkeypatch, capsys):
    planned_run(fpc, monkeypatch, tmp_path)
    assert fpc.main(["-o", "engin-zone"]) == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "engin-zone-excluded.json", "engin-zone-plan.json",
        "engin-zone-revert.json", "engin-zone.json"]


def test_stdout_mode_writes_no_other_file(fpc, tmp_path, monkeypatch, capsys):
    planned_run(fpc, monkeypatch, tmp_path)
    assert fpc.main([]) == 0
    assert list(tmp_path.iterdir()) == []


def test_the_inventory_is_byte_identical_between_the_two_modes(fpc, tmp_path, monkeypatch,
                                                               capsys):
    """R3.2's whole point: `-o x` and `> x.json` must not diverge for the same sweep."""
    planned_run(fpc, monkeypatch, tmp_path)
    assert fpc.main([]) == 0
    from_stdout = capsys.readouterr().out
    planned_run(fpc, monkeypatch, tmp_path)
    assert fpc.main(["-o", "engin-zone"]) == 0
    assert (tmp_path / "engin-zone.json").read_text() == from_stdout


def test_all_three_headed_files_share_one_generated_at(fpc, tmp_path, monkeypatch, capsys):
    """SPEC 9.3: os.replace is atomic per file, not across four.  A shared timestamp is what
    makes a mixed set detectable."""
    stamp = planned_run(fpc, monkeypatch, tmp_path)
    assert fpc.main(["-o", "engin-zone"]) == 0
    for suffix, direction in (("plan", "plan"), ("revert", "revert"), ("excluded", "excluded")):
        header = json.loads((tmp_path / f"engin-zone-{suffix}.json").read_text())["generated"]
        assert header["at"] == stamp
        assert header["direction"] == direction
        assert header["zones_swept"] == 2
        assert header["zones_total"] == 187
        assert header["required_a_range"] == "23.185.0.0/24"
        assert header["required_aaaa_range"] == "2620:12a::/32"


def test_the_header_entry_count_is_per_file(fpc, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch, fpc.SweepResult(
        {"a.example.edu": swept(), "b.example.edu": swept(name="b.example.edu",
                                                          origins=["live-b.pantheonsite.io"])},
        [], 1, 2, 5, 1, 0, 0, 187))
    fake_dns(fpc, monkeypatch, {
        ("live-a.pantheonsite.io", "A"): ["23.185.0.4"],
        ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8000::4"],
        ("live-b.pantheonsite.io", "A"): ["104.18.2.7"],
        ("live-b.pantheonsite.io", "AAAA"): ["2620:12a:8000::4"],
    })
    freeze_clock(fpc, monkeypatch)
    assert fpc.main(["-o", "engin-zone"]) == 1
    plan = json.loads((tmp_path / "engin-zone-plan.json").read_text())
    excluded = json.loads((tmp_path / "engin-zone-excluded.json").read_text())
    assert plan["generated"]["entries"] == 1
    assert excluded["generated"]["entries"] == 1
    assert list(plan["entries"]) == ["a.example.edu"]
    assert excluded["entries"]["b.example.edu"]["reason"] == "platform-a-out-of-range"


def test_the_plan_and_revert_hold_the_same_fqdns(fpc, tmp_path, monkeypatch, capsys):
    planned_run(fpc, monkeypatch, tmp_path)
    assert fpc.main(["-o", "engin-zone"]) == 0
    plan = json.loads((tmp_path / "engin-zone-plan.json").read_text())["entries"]
    revert = json.loads((tmp_path / "engin-zone-revert.json").read_text())["entries"]
    assert list(plan) == list(revert) == ["a.example.edu"]


def test_an_excluded_fqdn_gets_no_plan_or_revert_entry(fpc, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch,
               fpc.SweepResult({"a.example.edu": swept(proxied=None)}, [], 1, 2, 5, 1, 0, 0, 187))
    fake_dns(fpc, monkeypatch, {("live-a.pantheonsite.io", "A"): ["23.185.0.4"],
                                ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8000::4"]})
    freeze_clock(fpc, monkeypatch)
    assert fpc.main(["-o", "engin-zone"]) == 1
    assert json.loads((tmp_path / "engin-zone-plan.json").read_text())["entries"] == {}
    assert json.loads((tmp_path / "engin-zone-revert.json").read_text())["entries"] == {}
    assert "unknown-proxy-status" in (tmp_path / "engin-zone-excluded.json").read_text()


def test_a_construction_failure_writes_nothing(fpc, tmp_path, monkeypatch, capsys):
    """SPEC 9.3: all four documents are built in memory BEFORE any of them is written."""
    planned_run(fpc, monkeypatch, tmp_path)
    monkeypatch.setattr(fpc, "plan_entry",
                        lambda entry, resolution: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        fpc.main(["-o", "engin-zone"])
    assert list(tmp_path.iterdir()) == []


def test_the_subset_warning_names_all_four_files(fpc, tmp_path, monkeypatch, capsys):
    """SPEC 9.5: a subset sweep cannot see a cross-zone duplicate, so it can emit a PLAN entry
    for an FQDN a full sweep would have excluded as ambiguous."""
    planned_run(fpc, monkeypatch, tmp_path)
    assert fpc.main(["-o", "engin-zone", "example.edu"]) in (0, 1)
    err = capsys.readouterr().err
    assert "2 of 187 zones" in err
    assert "engin-zone-plan.json" in err
    assert "MUST NOT be used as the baseline" in err


def test_the_summary_counts_exclusions_by_reason(fpc, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    fake_sweep(fpc, monkeypatch,
               fpc.SweepResult({"a.example.edu": swept(proxied=None)}, [], 1, 2, 5, 1, 0, 0, 187))
    fake_dns(fpc, monkeypatch, {("live-a.pantheonsite.io", "A"): ["23.185.0.4"],
                                ("live-a.pantheonsite.io", "AAAA"): ["2620:12a:8000::4"]})
    freeze_clock(fpc, monkeypatch)
    assert fpc.main([]) == 1
    assert "1 unknown-proxy-status" in capsys.readouterr().err
```

- [ ] **Step 2: Run them and confirm they fail**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_cloudflare.py -k "four_files or no_other_file or byte_identical or generated_at or entry_count_is_per_file or same_fqdns or no_plan_or_revert or construction_failure or all_four_files or by_reason"
```

Expected: `AttributeError: ... 'now_utc'` from `freeze_clock`, and missing-file errors.

- [ ] **Step 3: Implement the clock, the header and the writer**

Add after `dump_json` (:376):

```python
def now_utc():
    """The one clock seam, as an ISO-8601 Z-suffixed string; tests monkeypatch it (SPEC 7).

    A seam rather than a post-hoc normalization: a golden that strips the timestamp before
    comparing is no longer comparing the bytes the program wrote (PD#14).
    """
    return datetime.datetime.now(tz=datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def provenance(argv, sweep, direction, count):
    """The `generated` header (SPEC 5.5).

    The plan pins addresses resolved at SWEEP time.  If Pantheon migrates a site between the
    sweep and the rewrite those addresses are wrong, and the file's mtime -- the only freshness
    signal it used to carry -- survives neither a copy nor a `git add`.  The ranges and the
    suffix are recorded so an applier can verify the assumptions the file was built under, and
    `direction` so it can refuse the wrong file outright.

    zones_swept/zones_total are two integers rather than a "1 of 187" string: a machine reads
    this.
    """
    return {"at": now_utc(),
            "tool": "find-platform-domains-cloudflare",
            "direction": direction,
            "argv": list(argv),
            "zones_swept": sweep.zones,
            "zones_total": sweep.zones_total,
            "entries": count,
            "platform_suffix": PLATFORM_SUFFIX,
            "required_a_range": str(PLATFORM_A_RANGE),
            "required_aaaa_range": str(PLATFORM_AAAA_RANGE)}


def write_outputs(paths, inventory, plan, revert, excluded) -> None:
    """Write the four files, each atomically (SPEC 9.3).

    Every document is fully built by the caller before this is entered, so a construction error
    writes nothing at all.

    ACCEPTED RESIDUAL: os.replace is atomic per file, not across four, so a crash between
    replaces leaves a mixed set.  All three headed files share one generated.at, which makes such
    a set detectable.  A single container file would close it and is ruled out by the four-file
    requirement.
    """
    for path, data in ((paths.inventory, inventory), (paths.plan, plan),
                       (paths.revert, revert), (paths.excluded, excluded)):
        write_json_atomic(path, data)
```

Replace `emit`:

```python
def emit(inventory, paths, plan, revert, excluded) -> None:
    """Send the results to their destination: four files, or the inventory alone on stdout."""
    if paths is None:
        write_json_stdout(inventory)
    else:
        write_outputs(paths, inventory, plan, revert, excluded)
```

- [ ] **Step 4: Wire it into `main`**

Extend the per-entry loop from Task 4 to build the plan and revert maps, and warn on a TTL
anomaly:

```python
        plan, revert = {}, {}
        for fqdn, entry in sorted(sweep.entries.items()):
            ...
            reason, detail = classify(entry, resolution)
            if reason is not None:
                excluded[fqdn] = {...}
                continue
            if proxied_ttl_anomaly(entry):
                print(f"ATTENTION: {fqdn} is proxied but its stored ttl is {entry['ttl']}, not "
                      "1; the rewrite bodies use 1, which is what Cloudflare enforces anyway",
                      file=sys.stderr, flush=True)
            plan[fqdn] = plan_entry(entry, resolution)
            revert[fqdn] = revert_entry(entry, resolution)
```

then, replacing the Task 4 `emit` call:

```python
        documents = None
        if paths is not None:
            documents = (
                {"generated": provenance(argv, sweep, "plan", len(plan)), "entries": plan},
                {"generated": provenance(argv, sweep, "revert", len(revert)), "entries": revert},
                {"generated": provenance(argv, sweep, "excluded", len(excluded)),
                 "entries": excluded},
            )
        try:
            emit(sweep.entries, paths, *(documents or (None, None, None)))
        except OSError as e:
            raise StartupError(f"cannot write {destination_name(paths)}: {e}") from e
```

Update `summarize`'s destination line and the subset ATTENTION:

```python
    if paths is not None and sweep.zones != sweep.zones_total:
        print(f"ATTENTION: {paths.inventory}, {paths.plan}, {paths.revert} and {paths.excluded} "
              f"cover {sweep.zones} of {sweep.zones_total} zones -- this is NOT an "
              "organization-wide sweep and MUST NOT be used as the baseline for a rewrite.  A "
              "subset cannot see a platform CNAME for the same FQDN in an UNSELECTED zone, so "
              f"{paths.plan} may contain an entry a full sweep would have excluded as ambiguous.",
              file=sys.stderr, flush=True)
```

Update `interrupt_message` to take `paths` and describe four files:

```python
def interrupt_message(*, wrote, paths):
    """What a Ctrl-C actually left behind -- reported as a fact, never as an assumption.

    Each -o write is atomic (temp file + os.replace), so no single file is ever partial.  stdout
    has no such guarantee.  `wrote` is set AFTER emit() returns, so it is a reliable YES and an
    unreliable NO: a SIGINT landing between the last os.replace() and that assignment leaves
    wrote=False with the files already in place.  The not-wrote branch therefore states only what
    is ALWAYS true.
    """
    if paths is not None:
        return (f"INTERRUPTED: all four files ({paths.inventory} and its -plan/-revert/-excluded "
                "siblings) were fully written." if wrote else
                "INTERRUPTED: each of the four output files is unchanged or fully written, never "
                "partial -- every write is atomic.  A mixed set is possible; the three headed "
                "files share one generated.at, so compare them.")
    return ("INTERRUPTED: a complete JSON document was already written to standard output."
            if wrote else "INTERRUPTED: no complete JSON document was produced.")
```

`main` passes `argv` into `provenance`, so keep the parameter name available; `main(argv)` already
has it.

- [ ] **Step 5: Run the whole file**

```bash
./run-tests --fast tests/unit/test_find_platform_domains_cloudflare.py
```

- [ ] **Step 6: Prove the atomicity guard can go red**

Temporarily move `write_json_atomic(paths.inventory, inventory)` in `write_outputs` to before the
loop and make `plan_entry` raise (as `test_a_construction_failure_writes_nothing` does) — confirm
that test **fails**. Restore. Record the observed failure in the task report (PD#14).

- [ ] **Step 7: Run the full offline suite and commit**

```bash
./run-tests --fast
git diff --stat find-platform-domains-dns tests/unit/test_find_platform_domains_dns.py
git add find-platform-domains-cloudflare tests/unit/test_find_platform_domains_cloudflare.py
git commit -m "feat(find-platform-domains-cloudflare): write the plan, revert and excluded files

Basename mode now writes four files.  All three headed files carry a provenance block
naming the run's time, argv, zone coverage and the ranges it enforced -- the plan pins
addresses resolved at sweep time, and mtime survives neither a copy nor a git add.
They share one generated.at, which is what makes a partially-written set detectable:
os.replace is atomic per file, not across four.

The subset ATTENTION now names all four files and states the consequence that
exclusion introduced: a narrowed sweep cannot see a platform CNAME for the same FQDN
in an unselected zone, so its plan may contain an entry a full sweep would exclude.

SPEC R5.5, 5.5, 5.6, 9.3, 9.4, 9.5, 10."
```

---

## Task 7: Documentation

Implements **§13** and **§17**. No code, no tests.

**Files:**
- Modify: `find-platform-domains-cloudflare` (module docstring, :1–38)
- Modify: `CLAUDE.md` (the `### find-platform-domains-cloudflare (temporary utility)` subsection)
- Modify: `.gitignore`
- Modify: `development/2026-07-30-platform-domain-util2/SPEC.md` (§11)

**Interfaces:** consumes everything; produces nothing.

---

- [ ] **Step 1: Update the script's module docstring**

Rewrite the output paragraph to describe the four files, `-o BASENAME`, the eight reason codes and
exit 1. Keep the existing paragraphs on standalone-ness, the stream guards and the argparse-120
exception verbatim — they are unchanged and were expensive to get right.

- [ ] **Step 2: Update `.gitignore`**

```bash
grep -n "platform-domains-cloudflare" .gitignore
```

Change `/platform-domains-cloudflare.json` to `/platform-domains-cloudflare*.json` so the three
new baseline files are ignored too.

- [ ] **Step 3: Update `development/2026-07-30-platform-domain-util2/SPEC.md` §11**

Amend item 6 to name the glob, and add a pointer line under the §11 heading:

```markdown
> **Superseded in part by `development/2026-07-31-platform-domain-util3/SPEC.md` §13** — that
> increment adds the plan/revert/excluded files. The checklist below is still the canonical one;
> only item 6's glob changed.
```

- [ ] **Step 4: Update `CLAUDE.md`**

In the `### find-platform-domains-cloudflare (temporary utility)` subsection, update: the option
(`-o BASENAME`, extension fatal), the four files and what each is for, `delete_match` and why it
sits outside `body`, the eight reason codes and which of them also leave the inventory, exit 1,
that every run now does DNS work, and the new inventory fields. Update the two example command
blocks. Keep the existing paragraphs on pagination, the credential resolver and the client pin —
they are unchanged.

- [ ] **Step 5: Verify the docs match the code**

```bash
./find-platform-domains-cloudflare --help
git grep -n "output-basename\|-o BASENAME" CLAUDE.md find-platform-domains-cloudflare
git grep -c "pantheon.io\|gotpantheon" find-platform-domains-cloudflare
# Expected: only .pantheonsite.io matches (R1).
```

- [ ] **Step 6: Full suite, then commit**

```bash
./run-tests --fast
git add find-platform-domains-cloudflare CLAUDE.md .gitignore \
        development/2026-07-30-platform-domain-util2/SPEC.md
git commit -m "docs(find-platform-domains-cloudflare): document the plan/revert/excluded files

CLAUDE.md, the module docstring, the .gitignore glob, and a pointer from the util2
deletion checklist to this increment's SPEC section 13."
```

---

## Task 8: Acceptance run and spec update

**Files:** Modify `development/2026-07-31-platform-domain-util3/SPEC.md` (§15 only).

- [ ] **Step 1: Run the offline acceptance commands from SPEC §15, items 1–5**

Paste the **real output** of each into SPEC §15, replacing the "to be run" note. An unrun
acceptance suite is PD#14 exactly.

- [ ] **Step 2: STOP — request the live gate**

SPEC §18 STOP 2: acceptance items 6–8 touch real Cloudflare credentials and MUST NOT run until
the human replies with the exact phrase `RUN LIVE`. **Ask, then wait.** Do not run them, do not
assume approval, and do not substitute a dry run.

- [ ] **Step 3: After `RUN LIVE`, run items 6–8 and paste the real output**

- [ ] **Step 4: Answer SPEC §19's closing audit questions in the spec**

- [ ] **Step 5: Commit**

```bash
git add development/2026-07-31-platform-domain-util3/SPEC.md
git commit -m "docs(platform-domain-util3): record the acceptance run and the closing audit"
```

- [ ] **Step 6: STOP — adversarial review**

SPEC §18 STOP 3: dispatch a `psh-reviewer` subagent with **fresh context**, seeing only
`development/2026-07-31-platform-domain-util3/SPEC.md` and the full branch diff, per
`prompts/adversarial-review.md`. Do not merge before it reports.

---

## Self-Review

**Spec coverage.** Every numbered requirement maps to a task:

| Spec | Task | | Spec | Task |
|---|---|---|---|---|
| R1 (scope) | 7 (verified; no code change) | | §5.5 (header) | 6 |
| R2.1–R2.4 | 1 | | §5.6 (excluded file) | 4, 6 |
| R3.1–R3.4 | 2, 4 | | §6 (gate table) | 3, 4 |
| R4.1 | 3 | | §7 (seams) | 2, 6 |
| R4.2 | 3 (`name`/`zone_name`), 4 (`resolved_*`) | | §8 (exit 1) | 4 |
| R4.3 | 3 (nothing else was missing) | | §9.1–§9.2 | 2, 4 |
| R4.4 | 2, 4 | | §9.3 (write) | 6 |
| R5.1–R5.3 | 5 | | §9.4 (interrupt) | 6 |
| R5.4 (round-trip) | 5 | | §9.5 (subset) | 6 |
| R5.5 | 6 | | §10 (observability) | 4, 6 |
| R6, R6.1 | 5 | | §13, §17 (docs) | 7 |
| R7.1–R7.3 | 4 | | §15, §19 | 8 |

**Placeholder scan.** No "TBD", no "add error handling", no "similar to Task N". Every code step
carries the literal code. Task 7's steps describe prose edits rather than showing them, which is
correct for documentation — the *content* to write is enumerated.

**Type consistency, checked across tasks.** `OutputPaths` field names (`inventory`/`plan`/
`revert`/`excluded`) are identical in Tasks 1 and 6. `Resolution` is `(a, aaaa, problem)`
everywhere. `classify` returns `(reason, detail)` in Tasks 4 and 6. `collect_entries` returns a
3-tuple in Task 3 and is consumed as one in `fetch_platform_cnames`. `plan_entry`/`revert_entry`
take `(entry, resolution)` — the fqdn is unused because `entry["name"]` carries it.

**Two divergences found during review, both closed by amending SPEC §7** (commit
`<spec-amend>`), so the two documents cannot drift:

1. §7 sketched `plan_entry(fqdn, entry, resolution)`; the signature is `(entry, resolution)`.
2. §7 listed `resolve_target(target)` but the implementation needs a per-rrset helper too. §7 now
   names `resolve_one_rrset`, `clean_settings` and `proxied_ttl_anomaly` as well, with their real
   signatures, so a task's implementer reading only the spec finds them.

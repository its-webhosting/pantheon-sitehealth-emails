# I14a — Structural Finish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every implementer dispatches as `psh-implementer`, every reviewer as `psh-reviewer`,
> and uses `mattpocock-skills:tdd` (NOT superpowers:test-driven-development) — the
> overrides in `prompts/implementation-standards.md` govern.

**Goal:** Delete B51, move `dns_classify.py` to `psh/dns_classify.py`, relocate the whole
remnant (`psh/_legacy.py`) into `psh/cli.py`, and delete `psh/_legacy.py` — goldens
byte-identical throughout.

**Architecture:** Three atomic per-task commits against SPEC.md §2.1–§2.3 (same
directory as this plan — the implementer MUST read it in full; its tables are the
exhaustive edit lists and are not repeated here). Pure relocation + one sanctioned
deletion; no algorithmic redesign (CAMPAIGN.md §3.1 whole-file-coverage rule).

**Tech Stack:** Python 3.12, pytest via `./run-tests`, ruff (two configs), pyright.

## Global Constraints

- Four e2e goldens byte-identical: `git diff 5902b76 -- tests/e2e/__snapshots__/` MUST
  be empty after every task (SPEC §3; CAMPAIGN §9 Invariant 1).
- Moved bodies verbatim except SPEC-named edits; column-0 `f"""` literals byte-for-byte
  (Invariant 8) — self-diff evidence pasted in the task report.
- `./run-tests --fast` green at every commit; both ruff passes + pyright green.
- No test assertion weakened; the B51 test edits are exactly SPEC §2.1's table.
- Commit messages: conventional, `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Task reports cite Spine directives by number with verbatim quotes.

---

### Task 1: B51 deletion (SPEC §2.1)

**Files:**
- Modify: `check/umich/annual_billing.py`, `check/umich/__init__.py`,
  `psh/_legacy.py:333–365, :906–911`, `CLAUDE.md` (billing prose only)
- Test: `tests/integration/test_check_umich_annual_billing.py`,
  `tests/integration/test_sort_notices_and_subject.py`,
  `tests/unit/test_annual_billing_notices.py`

**Interfaces:**
- Consumes: baseline state at `7e7e803`.
- Produces: `check/umich/annual_billing.py` exporting only
  `build_annual_bill_upcoming_notice`, `_billing_inputs`,
  `check_annual_bill_upcoming`; `sort_notices_and_subject` reading only
  `annual_bill_upcoming`. Task 3 relocates that function as-is.

- [ ] **Step 1: Write the RED instrument** — in
  `test_check_umich_annual_billing.py`, make the registration assertions exact-set:

```python
def test_umich_enabled_registers_exactly_the_upcoming_hook(psh, reset_sc):
    _load_package(reset_sc)  # existing loader helper in this file
    names = [h["name"] for h in reset_sc.hooks.get("site_pre_render", [])
             if h["name"].startswith("check.umich.annual_billing.")]
    assert names == ["check.umich.annual_billing.check_annual_bill_upcoming"]
```

  (Adapt the loader-helper call to the file's existing pattern; replace the old
  two-hook assertions at `:53`/`:62`/`:64` rather than adding a duplicate test.)

- [ ] **Step 2: Watch it fail for the right reason**
  Run: `./run-tests --fast tests/integration/test_check_umich_annual_billing.py -x`
  Expected: FAIL — the list contains BOTH hook names (in_progress registered second).

- [ ] **Step 3: Apply the deletion** — every row of SPEC §2.1's table: the builder
  (`annual_billing.py:89–114`), the TODO + hook (`:134–140`), the module-docstring
  rewrite (one produced key; keep the load-bearing history paragraph), the
  `__init__.py` import + registration, `psh/_legacy.py:360–365` (walrus + insert +
  the four comment lines incl. the `:360` TODO), its docstring/comment updates
  (`:333, :336–337, :347, :906, :910–911`).

- [ ] **Step 4: Apply the test edits** — SPEC §2.1's three test-file rows verbatim,
  including the two REWRITES (upcoming-only front-order; non-mutation pin driven
  through `annual_bill_upcoming` — NEVER deleted).

- [ ] **Step 5: Green + count** —
  Run: `./run-tests --fast`
  Expected: green; collected count = baseline − 4 (or −5 per the §2.1 adjudication —
  pin the predicted number in the report BEFORE running).
  Run: `git diff 5902b76 -- tests/e2e/__snapshots__/`  Expected: empty.

- [ ] **Step 6: CLAUDE.md billing prose** — one hook / one produced key; note B51
  deleted at I14a (user-approved early). Report the line-count delta.

- [ ] **Step 7: Commit**
```bash
git add -A && git commit -m "feat(campaign-I14a): delete the B51 annual-bill-in-progress notice"
```

### Task 2: `dns_classify.py` → `psh/dns_classify.py` (SPEC §2.2)

**Files:**
- Move: `dns_classify.py` → `psh/dns_classify.py` (via `git mv`)
- Modify: `psh/_legacy.py:30`, `check/pantheon_cdn_change/chain.py:37`,
  `tests/helpers/dnsfake.py:47`, `tests/unit/test_dns_classify.py` (7 import sites),
  `tests/unit/test_contract_registry.py:8`,
  `tests/unit/test_pantheon_cdn_change_chain.py:76`, `pyproject.toml:112`,
  `ruff-broad.toml:15`, `tests/unit/test_house_rules.py:31, :116`,
  `.claude/hooks/ruff-check.sh:101`, plus the SPEC-listed doc/comment repoints.

**Interfaces:**
- Consumes: Task 1's tree (independent of its edits).
- Produces: importable `psh.dns_classify` with unchanged public surface
  (`classify_domains`, `stuff_dns_contract`, `resolve`, `MalformedNameError`,
  `DnsFacts`, `classify_hostname_dns`). Task 3's `psh/cli.py` imports it as
  `import psh.dns_classify as dns_classify`.

- [ ] **Step 1: Move** — `git mv dns_classify.py psh/dns_classify.py`

- [ ] **Step 2: Structural RED** —
  Run: `./run-tests --fast tests/unit/test_dns_classify.py -x`
  Expected: collection error `ModuleNotFoundError: No module named 'dns_classify'`
  (the right reason: old import path gone).

- [ ] **Step 3: Repoint every reference** — SPEC §2.2's bullets, exhaustively. All
  import sites become `import psh.dns_classify as dns_classify` (call sites stay
  qualified; `dnsfake.py`'s `monkeypatch.setattr(dns_classify, "resolve", …)` keeps
  working — single module object).

- [ ] **Step 4: Ratchet clean** — the 9 measured findings per SPEC §5 dispositions;
  pyright on the widened scope. Re-measure and record deltas.
  Run: `uvx ruff check --config ruff-broad.toml psh/dns_classify.py` → All checks passed!
  Run: `uvx pyright` (via `./run-tests`'s gate) → 0 errors.

- [ ] **Step 5: House-rule scope RED check** — temporarily add
  `_x = os.environ["HOME"]` to `psh/dns_classify.py`, run
  `./run-tests --fast tests/unit/test_house_rules.py -x`, watch the ENVIRON rule
  fail **naming the moved file**, revert. Record in the report (I2 precedent).

- [ ] **Step 6: Green** —
  Run: `./run-tests --fast`  Expected: green, count unchanged from Task 1.
  Run: `git diff 5902b76 -- tests/e2e/__snapshots__/`  Expected: empty.

- [ ] **Step 7: Commit**
```bash
git add -A && git commit -m "feat(campaign-I14a): move dns_classify into psh/"
```

### Task 3: remnant → `psh/cli.py`; delete `psh/_legacy.py` (SPEC §2.3)

**Files:**
- Move: `psh/_legacy.py` → `psh/cli.py` (delete the 9-line `psh/cli.py` first, then
  `git mv` — preserves blame), restructure per SPEC §2.3 items 1–6.
- Modify: `psh/lifecycle.py:333` (+ docstring diagram), `psh/__init__.py`,
  `pantheon-sitehealth-emails` (shim docstring line), `pyproject.toml` (`:92` delete,
  `:87–90` comment rewrite — `include = ["psh"]` MUST survive), `ruff-broad.toml:14`,
  `run-tests:56, :119`, `.claude/hooks/ruff-check.sh:101` (if not done in Task 2),
  `tests/conftest.py:6, :88–89, :101`, the SPEC-listed comment-accuracy files,
  `CLAUDE.md` (minimal — only claims this task falsifies).

**Interfaces:**
- Consumes: Task 2's `psh.dns_classify`.
- Produces: `psh.cli` exposing the full re-export surface (every current
  `psh._legacy` public attribute), `main()`, `parse_args`, `build_arg_parser`;
  conftest `psh` fixture returning `psh.cli`.

- [ ] **Step 1: Assemble** — `git rm psh/cli.py && git mv psh/_legacy.py psh/cli.py`,
  then restructure exactly per SPEC §2.3 items 1–6 (top-of-file imports incl. seam
  imports with REWRITTEN reason texts; `fqdn_re`; `registry.register("no-domains", …)`
  + the 13-line sc-exposure block verbatim; the four defs verbatim; NO `__main__`
  tail).

- [ ] **Step 2: Bridge retarget** — `psh/lifecycle.py:333`:
```python
        from psh.cli import build_arg_parser  # noqa: PLC0415 -- call-time: psh.cli imports psh.lifecycle at module level; a module-level import here is a cycle (SPEC I14a D-i14a-4)
```
  and update the module docstring's import diagram (PD#8).

- [ ] **Step 3: Structural RED** — before touching conftest:
  Run: `./run-tests --fast tests/unit/test_notice.py -x`
  Expected: collection/fixture error `ModuleNotFoundError: No module named
  'psh._legacy'` (conftest still imports the old name — the right reason).

- [ ] **Step 4: Conftest repoint** — `tests/conftest.py:89` →
  `importlib.import_module("psh.cli")`; docstring/comment updates (`:6, :88, :101`).

- [ ] **Step 5: Config + doc edits** — the SPEC §2.3 "Then:" list and the
  comment-accuracy pass (exhaustive lists in SPEC; includes `run-tests:56/:119`,
  pyproject pyright lines, ruff-broad exclude, shim + `psh/__init__.py` docstrings,
  the 11-file test-comment list, `psh/*.py` present-tense provenance comments).

- [ ] **Step 6: Ratchet clean to born-gated** — the 69-finding dispositions per SPEC
  §5 (F401 three-way split with the D-i14a-3 block comment; E402/I001 dissolved;
  B023 noqa + reasons; the rest per table). Re-measure; record deltas. pyright on
  `psh/` (now incl. cli.py) → 0 errors, dispositions per the I13 classes.

- [ ] **Step 7: Verbatim evidence** — structural self-diff of the moved defs:
```bash
git show 5902b76:psh/_legacy.py > /tmp/claude-501/-workspace/962264a2-e739-4787-b547-17ba34ffcd5d/scratchpad/legacy-baseline.py
diff <(sed -n '/^def no_primary_domain_notice/,/^def main/p' /tmp/claude-501/-workspace/962264a2-e739-4787-b547-17ba34ffcd5d/scratchpad/legacy-baseline.py) \
     <(sed -n '/^def no_primary_domain_notice/,/^def main/p' psh/cli.py)
```
  (and the `main()` body range similarly). Every hunk MUST be a SPEC-named edit
  (Task 1's B51 lines, noqa trailers, comment rewrites); paste the accounting in the
  report.

- [ ] **Step 8: Collected-count gate + full green** —
  Run: `python -m pytest --collect-only -q 2>/dev/null | tail -1` — count identical
  to Task 2's close.
  Run: `./run-tests --fast`  Expected: green.
  Run: `git diff 5902b76 -- tests/e2e/__snapshots__/`  Expected: empty.
  Run: `./pantheon-sitehealth-emails --help | head -3`  Expected: usage text (shim
  alive through `psh.cli.main`).
  Run: `test ! -e psh/_legacy.py && test ! -e dns_classify.py && echo gone` → `gone`.

- [ ] **Step 9: Commit**
```bash
git add -A && git commit -m "feat(campaign-I14a): relocate main() to psh/cli.py, delete _legacy"
```

---

**Close (controller, not a dispatched task):** whole-branch `/code-review`; full
`./run-tests` (live tier if credentials present); SPEC §9 acceptance run-and-pasted;
LEDGER I14a entry; memory; `/archive-session`; closing docs commit.

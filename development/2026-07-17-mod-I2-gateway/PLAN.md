# I2 — Gateway extraction — PLAN

Executable plan for `SPEC.md` (same folder). Baseline (I2 start) = **`8b1466b`** (I1 closing/archive).
Use it for the golden-diff acceptance check. Subagent-driven per `prompts/implementation-standards.md`
(`psh-implementer` / `psh-reviewer`, TDD = `mattpocock-skills:tdd`). Per-task commits, each green.

## Task 1 — Gateway move + `GatewayResult` + seam repoint

1. **RED** (test-first): add the `GatewayResult` return-type test to
   `tests/integration/test_terminus_contract.py` — `run_terminus` and `terminus` return a
   `GatewayResult` with `.result/.errors/.fatal`. Run it; watch it fail with
   `AttributeError: … 'GatewayResult'` (type does not exist yet). Paste the red.
2. Create `psh/gateway.py`: move the eleven defs (SPEC §Scope table) with logic + the two column-0
   `f"""` literals byte-for-byte; wrap returns in `GatewayResult(...)`; replace tuple hints with
   real annotations; apply the SPEC §Broad-ruff dispositions (fix `F541`×2 / `E713` / `PLW2901`;
   `# noqa: C901, PLR0912` on `run_terminus`'s `def` and `# noqa: S603` on its `Popen`, each with an
   inline reason). Add gateway's own import block (SPEC §Move mechanics).
3. In `psh/_legacy.py` remove the eleven defs and add the `from psh.gateway import (…)` block. Verify
   no import is orphaned (SPEC says none are).
4. Add the `gateway` fixture to `tests/conftest.py` (SPEC §Seams).
5. Repoint the four test files' `run_terminus` patches from `psh` to `gateway` (SPEC §Seams table).
   **Leave every `psh.time.sleep` / `psh.subprocess.Popen` patch untouched.**
6. → verify: `ruff check --config ruff-broad.toml psh/gateway.py` → "All checks passed!"; pyright
   0 errors on `psh/gateway.py`; `./run-tests --fast` green; `git diff 8b1466b -- tests/e2e/__snapshots__/`
   empty; the extracted-literal diff of the two `f"""` blocks (pre vs post) empty. Paste all.

## Task 2 — House-rule instruments

1. Add to `tests/unit/test_house_rules.py`: (a) no-`subprocess.Popen`-outside-gateway test
   (scope/allowlist per SPEC §New tests #2; RED via temporary reintroduction, pasted, then revert);
   (b) documented-`sc`-façade-names test (SPEC §New tests #3; RED demo via temporarily removing one
   `sc.<name>` assignment, documented in the docstring, then revert).
2. → verify: `./run-tests --fast` green; both new tests present and passing; red demos pasted.

## Task 3 — Docs, memory, ledger

1. `CLAUDE.md`: add gateway to the carved-out modules; wrapper bullet → `psh/gateway.py` home +
   `GatewayResult`; Testing "Two mock seams" → `psh.gateway.run_terminus` in-process seam + `gateway`
   fixture. Report the line-count delta.
2. `tests/README.md:63`: seam line → `gateway`.
3. Auto-memory: gateway extraction + seam move (`psh.gateway.run_terminus`).
4. `LEDGER.md`: append the I2 entry (template CAMPAIGN.md §12), including the ratchet-no-op reasoning
   (SPEC §Ratchet).
5. → verify: `./run-tests --fast` green.

## Close

`/code-review` (or `prompts/adversarial-review.md`) whole-branch → fix loop → full `./run-tests`
(live tier if credentialed, else `--fast` + ledger note) → paste acceptance block into SPEC §Acceptance
→ `/archive-session` → closing commit incl. this `development/` folder.

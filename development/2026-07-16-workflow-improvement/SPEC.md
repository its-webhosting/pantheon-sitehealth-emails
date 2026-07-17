# SPEC — Workflow & Configuration Consolidation

**Status:** survived **3 rounds** of adversarial review (the maximum `prompts/adversarial-review.md` permits) — scores 6/10 → 7/10 → 7/10. **39 issues raised, 39 resolved.** No unresolved Reviewer Concerns. Round 3's verdict: *SHIP WITH NOTED CONCERNS*, blockers F1–F4 fixed; round 3 also advised against a 4th round ("the marginal return is exhausted, and a fourth round of prose-polishing on an 813-line document is itself the ceremony §1c is about").
**Awaiting:** §14 Gate 1 (`SPEC APPROVED — BEGIN IMPLEMENTATION`)
**Prompt:** `development/2026-07-16-workflow-improvement/PROMPT.md`
**Standards:** `prompts/new-feature-standards.md`

---

## Glossary

Each term is used in exactly this sense throughout this document.

| Term | Meaning |
|---|---|
| **Spine** | `prompts/directives.md` (new) — the single copy of Posture, Prime Directives, Engineering Preferences, and the spec quality bar. |
| **Delta** | What remains of an overlay file once the Spine is factored out: only the material specific to the skill that overlay wraps. |
| **Overlay** | A `prompts/*.md` file layering this project's *bar* onto a skill's *process*. Existing overlays: `new-feature-standards.md`, `implementation-standards.md`, `debugging-standards.md`. |
| **Read list** | The fixed, non-negotiable set of files a subagent brief instructs the subagent to read before acting. Replaces *curation*. |
| **Curation** | The current mechanism (`implementation-standards.md` § "How this overlay is applied"): the controller selects a *subset* of standards per dispatch. Being removed. |
| **Instrument** | Any code whose purpose is to report on other code: a test, golden, fixture, shim, counter, log line, or metric. Subject of PD#14. |
| **Red-capable** | An instrument demonstrated to fail on the condition it guards, by observation, not by argument. |
| **Increment** | One modularization effort: a single sub-area moved out of the core script, with its own thin spec. |
| **Campaign** | The whole modularization program: `CAMPAIGN.md` plus its Increments. |
| **Narrow ruff** | Exactly the rule set in §4.1. Not ruff's defaults. |

**Normative keywords.** **MUST** = required; a violation is a defect. **MUST NEVER** = prohibited; a violation is a defect. **SHOULD** = required absent a stated, written reason. **MAY** = permitted, no expectation.

---

## 1. Problem

The configuration and standards grew organically across ~13 development efforts and are now internally inconsistent. Three classes of problem, each verified rather than asserted:

**1a. The standards have forked.** 55 lines are duplicated across three files. **53 of them** — the entire Prime Directives block, Engineering Preferences, and the spec quality bar — exist verbatim in both `prompts/new-feature-standards.md` and `prompts/adversarial-review.md` (35.6% of `new-feature-standards.md`, 40.2% of `adversarial-review.md`). **The copies have already drifted**: `new-feature-standards.md`'s PD#11 mandates `/domain-modeling` and names `CONTEXT.md`; `adversarial-review.md`'s PD#11 is the older, shorter text. Neither file states which governs. The adversarial reviewer — dispatched with fresh context specifically to be independent — reads the stale copy.

The remaining **2** duplicated lines are the Posture persona, shared by `new-feature-standards.md` and `implementation-standards.md`. Recorded because §11 acceptance #5 expects **0**, which is unreachable unless the Spine also absorbs Posture from `implementation-standards.md` (§5.1).

This violates the project's own Engineering Preference ("**DRY** — flag repetition aggressively") and its own quality bar ("Each rule stated once and cross-referenced elsewhere (DRY)").

**1b. Standards do not reach subagents.** `prompts/implementation-standards.md` states the failure mode exactly — "**An un-injected standard does not exist**" — and then adopts the mechanism that produces it: the controller hands each subagent "not the whole file, only the relevant subset." That selection happens mid-session, at the point where the controller's context is fullest and momentum highest. Reported symptom: *"Subagents ignore standards."*

**1c. One ceremony for all work.** The pipeline (brainstorm → plan → adversarial review → subagent-driven-development → code-review → archive) runs identically for a 20-line core edit and a self-contained new package. Reported symptom: *"Too much ceremony for small work."*

> **1c is PARTIALLY addressed — by §7.2, not by a tier table.** §7.2's scrutiny inheritance (one brainstorm + one adversarial review, amortized across N increments) genuinely reduces ceremony for the imminent work. What is **deferred to §8** is the *general* mechanism. A risk-tier model (`FULL`/`LIGHT`/`DIRECT`) was designed and then **dropped** under PD#12. Reason: §7.2 establishes that Campaign increments touch `main()` **by construction** — they touch `main()` — so the tier model would have classified nearly all imminent work as maximum ceremony, delivering ~nothing for the very pain it was built for, while adding a model to maintain and no way to validate it against work that does not yet exist. **The Campaign is what creates LIGHT work**, by building the seams that let a new check live entirely inside a package. Revisit when there is LIGHT work in volume to triage.
>
> Stated precisely: the *tier table* is the wrong instrument for today's work — **not** that §1c is unaddressed.

### 1d. What the repo already proves

`run_program()`'s safety interlock has never needed a prompt reminding anyone not to use `--all` in a test — it raises `ForbiddenFlagError`. `tests/integration/test_shim_composability.py` guards the two-`sitecustomize` trap mechanically. **The standards that are never violated are the ones that are code.** This is the design principle the spec generalizes.

### 1e. Evidence that prose-only enforcement misses real defects

Running a linter against this repo for the first time, restricted to rules that merely restate standards already written in `prompts/`:

```
$ uvx ruff check --target-version py312 --select E722,BLE001,S105,S106 --statistics \
    check/ plugin/ dns_classify.py script_context.py tests/ pantheon-sitehealth-emails.py
5	S105  	hardcoded-password-string
2	BLE001	blind-except
Found 7 errors.
```

Seven findings, and **one bug the standards could never have caught** (§4.2): `pyproject.toml` declares `requires-python = ">=3.11"`, but the program uses PEP 701 backslash-in-f-string syntax, which requires Python **3.12+**. It is a `SyntaxError` at import on 3.11 — invisible to every runtime shadow-path analysis, because it is not a runtime path.

---

## 2. Goals, in the priority order stated by the user

1. **PRIMARY — Values, behavior, quality, excellence.** The standards must be *right* and must actually *hold*. Consolidation is a means, never the end.
2. **SECONDARY — Less mass; evertying utilized; nothing at cross-purposes.**
3. **TERTIARY — Efficiency.** Less context, fewer tokens, smoother and more automated — **without** giving up being consulted on substantial decisions.

> **Intent.** This ordering is recorded because the design was initially mis-derived against goal 2 and corrected. A future session MUST NOT re-optimize this work for token savings at the expense of goal 1.

---

## 3. Directive changes (PRIMARY)

### 3.1 PD#8 — scope it to designs; make the code half conditional

**Finding (measured).** PD#8 currently reads: "Diagrams are mandatory… ASCII art for every new data flow, state machine, processing pipeline, dependency graph, and decision tree, **in the design and in code comments**."

- **In the design: 9 of 11 specs under `development/*/SPEC.md` contain a diagram.** (The two without: `2026-07-06-env-plugin`, `2026-07-11-cachecheck-must-revalidate`.) This half works.
- **In code comments: zero.** The only four matches in the entire codebase are section dividers in `check/cloudflare/notices.py` (e.g. `# ── Documentation links ───`). No flow diagram exists in `main()`, the phase pipeline, `db_retry`, or anywhere else.

Consequently `prompts/implementation-standards.md` directive #7 — "Update the diagram comment when you change the flow it describes. A stale ASCII diagram in a docstring/comment is worse than none" — governs a population of approximately zero. It is vacuous prose.

> **Intent.** A mandatory rule with 0% compliance and no consequence teaches that the directive list is aspirational, which discounts PD#1–#7 — the ones that *are* followed and carry real weight. The fix makes the directive **true**.

**PD#8 MUST be replaced with:**

> **8. Diagrams are mandatory in the design.** No non-trivial flow ships undiagrammed in the spec — ASCII art for every new data flow, state machine, processing pipeline, dependency graph, and decision tree. **In code, a diagram is REQUIRED only where the flow is non-local** (spans files, packages, or phase seams). Where a diagram exists in a comment or docstring, updating it is part of changing the flow it describes; a stale diagram is worse than none.

`prompts/implementation-standards.md` directive #7 MUST be restated as conditional ("*where* a diagram exists…"), matching the above.

### 3.2 PD#14 — add "Your instruments can lie"

**Derivation.** Taken from this repo's actual shipped-defect history as recorded in `CLAUDE.md`, not from general principle. Six defects share one thread:

| Defect (from `CLAUDE.md`) | What lied |
|---|---|
| e2e goldens never loaded any check/plugin (`find_modules` walks CWD-relative; `make_workdir` didn't symlink them) | The **test suite** reported green while testing a program with every check disabled |
| Two `sitecustomize.py` → one silently never runs | The **shim** did nothing; a `not in`-shaped assertion passed green |
| `db_retry` attempt-counting reported "1 reconnect" on the run that aborted *because* nothing reconnected, and zero on a rollback failure | The **counter** |
| `recording_console`'s wide default hid the 80-column non-tty wrap that re-mailed every owner | The **test's console** was not production's |
| Run metadata in `-results.json` → phantom site rows in the operator's monthly stats | The **artifact** |
| `[lowercase]` rich markup silently deleted from the very message needed to debug | The **log line** |

PD#5 ("Observability is scope") does not cover this: it treats instruments as *deliverables*, not as *code that can be silently wrong*. The lesson currently survives only as repo trivia in `CLAUDE.md` § Testing and one bullet in `implementation-standards.md` § Test discipline — the weakest position in the standards for the most expensively-learned lesson.

**PD#14 MUST be added:**

> **14. Your instruments can lie.** A test, golden, fixture, shim, counter, log line, or metric is code, and can be silently wrong. **A green check is a claim, not evidence, until it has been shown capable of going red on the condition it guards.** Corollaries this generalizes: watch the test fail for the *right reason*; reproduce production's console width rather than a comfortable one; prove every shim actually runs; count what *healed*, not what was *attempted*; an existing golden going red is a signal, never refreshed to green.

> **Intent.** Stated as a directive rather than a test-discipline bullet so it applies at **design** time (to a new counter, artifact, or notice) and so a fresh-context subagent can apply it to an instrument this repo has never seen.

### 3.3 NOT in scope — directives considered and rejected

Recorded per PD#9 so a future session does not re-litigate them.

| Rejected | Rationale offered | Decision |
|---|---|---|
| **Scale/cost directive** ("everything multiplies by 300") | `plan_costs` was doing ~91 uncached per-month `Session.get()`s per site over a WAN; no PD or Engineering Preference covers N+1 or per-run cost; every hook the Campaign adds runs 300× | **Rejected** — user: "13 is enough"; adding directives dilutes the ones that matter |
| **Reusability directive** ("production is not the only configuration") | `CLAUDE.md`: "Bugs hide here because production always runs with the UMich plugin enabled, so the non-U-M golden is the only guard" — and that golden does not assert absence of `umich.edu` leakage | **Rejected** — same rationale; covered by "This project's context" and engineering judgment |

---

## 4. Mechanization (PRIMARY — makes standards non-ignorable)

### 4.1 Narrow ruff

Every rule MUST trace to a standard already written in prose. No rule is admitted that is not already a stated standard; ruff's default rule set is **NOT** adopted (§8).

```toml
# pyproject.toml

[tool.ruff]
# NO target-version.  Ruff infers it from `requires-python` (§4.2), and that is
# load-bearing: pinning target-version = "py312" here MASKS the §4.2 bug
# entirely -- verified, the 10 invalid-syntax errors vanish -- so a future
# session reverting requires-python to ">=3.11" would get SILENCE.
# The instrument must stay red-capable (PD#14).  See §9 #8.

[tool.ruff.lint]
# Each rule mechanizes a standard that exists in prose today.  Nothing here is new
# policy.  Broadening this set is deferred — see §8.
select = [
    "E722",    # bare except        <- new-feature-standards.md PD#2
    "BLE001",  # blind except       <- new-feature-standards.md PD#2
    "S105",    # hardcoded password <- new-feature-standards.md PD#6
    "S106",    # hardcoded password <- new-feature-standards.md PD#6
]

[tool.ruff.lint.per-file-ignores]
# Intent: test fixtures deliberately carry fake credentials.  All 5 current S105
# hits are fixtures; none is a real secret.  Verified 2026-07-16.
"tests/*" = ["S105", "S106"]
```

**Disposition of the current 7 findings — exhaustive:**

| Finding | Disposition | Intent |
|---|---|---|
| `pantheon-sitehealth-emails:4721` — `except BaseException` | `# noqa: BLE001` **with the reason inline**, citing `CLAUDE.md` | Deliberate and documented: "enumerating classes is what let an SMTP hiccup on site 250 of 300 discard 249 sites' work." The `noqa` **improves** matters — the deliberate choice becomes explicit at the call site instead of only in a doc ~4,000 lines away |
| `plugin/cloudflare/ips.py:18` — `except Exception as e: sys.exit(...)` | **Fix**: `except cloudflare.CloudflareError as e:` | Real defect under PD#2 ("Every error has a name"). Loud, but unnamed. **The class is named here because the implementer runs `mattpocock-skills:tdd` with fresh context and cannot ask** — PD#2 binds this spec, not just the code. Verified against the installed SDK: `CloudflareError` is the base of all 14 SDK exceptions (`APIError` → `CloudflareError`), covering both `APIConnectionError` (network) and `APIStatusError` (4xx/5xx). |
| `plugin/cloudflare/ips.py:21` — `'Cloudfare IPs:'` typo | **Fix** | PD#11 (terminology). Found incidentally; in scope because the file is already being edited |
| 5× `S105` in `tests/` | **Suppress** via `per-file-ignores` | All fixtures; verified individually |

**MUST NEVER:** add a `noqa` without an inline reason. A bare `noqa` is a silent failure (PD#1).

### 4.2 Fix `requires-python`

```toml
# pyproject.toml
requires-python = ">=3.12"   # was ">=3.11"
```

> **Intent.** The program uses PEP 701 backslash escapes inside f-strings at 5 sites (e.g. `pantheon-sitehealth-emails:496`, `:578`, `:4340`), which parse only on Python 3.12+. On 3.11 the program raises `SyntaxError` at import. The venv runs 3.13, so this has never been hit; anyone following `README.md`'s setup on 3.11 hits it immediately. `README.md` MUST also be checked for a Python-version claim and corrected to match.

### 4.3 `tests/unit/test_house_rules.py`

Pins invariants `CLAUDE.md` currently states in prose only. Initial content — **exhaustive** for this change:

1. **The `os.environ` two-file invariant.** `CLAUDE.md`: "The only direct `os.environ` touches are `plugin/env/get_env.py` … and the `AWS_PROFILE`/`AWS_DEFAULT_REGION` boto plumbing in `plugin/aws/__init__.py` — don't add more."

   **SCOPE — literal and exhaustive.** The invariant governs **feature code only**:
   ```
   check/  plugin/  dns_classify.py  script_context.py  pantheon-sitehealth-emails
   ```
   **Allowlist:** `plugin/env/get_env.py`, `plugin/aws/__init__.py`. **Any other file in scope with an `os.environ` touch = FAIL.**

   `tests/` is **NOT** in scope and MUST NOT be globbed.

   > **Intent.** `CLAUDE.md`'s rule is about feature code — it is the `<{secret env …}>` substitution boundary (PD#6). `tests/` legitimately holds **19** `os.environ` touches across **six** files (exhaustive: `conftest.py`, `shims/pyshim/dbshim.py`, `shims/pyshim/dnsshim.py`, `unit/test_env_plugin.py`, `integration/test_shim_composability.py`, `shims/terminus`) that set up shims and fixtures. An implementer who globs the repo gets red immediately and "fixes" it by loosening the assertion — turning the instrument into a lie (PD#14). Verified 2026-07-16: at this scope the invariant holds exactly, and the main script itself has **zero** touches.
2. **Exactly one `sitecustomize.py` exists** under `tests/`. `CLAUDE.md`: "two `sitecustomize.py` files means one silently never runs — no error, no warning." (`test_shim_composability.py` covers composability; this covers the count directly.)

> **Intent.** These are the two prose invariants whose violation is silent and whose check is trivial. Other `CLAUDE.md` rules are judgment, not assertions, and are deliberately left as prose.

**PD#14 applies to this file, and this is a structural requirement, not advice.** These tests pass the moment they are written, which `implementation-standards.md` § Test discipline correctly calls testing existing behavior. Each test is an **Instrument** and MUST be demonstrated **red-capable** before it counts as done:

```
For each assertion:
  1. Introduce the violation it guards (add a third os.environ touch;
     add a second sitecustomize.py).
  2. Run the test. Observe it FAIL, and read the failure to confirm it
     failed for the RIGHT reason — not an import error, not a path bug.
  3. Revert.
  4. Paste both outputs (red, then green) in the task report.
```

A house-rules test whose red state was never observed is **NOT** done. It is exactly the instrument PD#14 describes.

### 4.4 Edit-time ruff hook

```json
// .claude/settings.json  (project scope, committed) -- PostToolUse goes INSIDE the
// existing "hooks" object, beside UserPromptSubmit.  NOT at the top level.
{
  "permissions": { "...": "unchanged" },
  "enabledMcpjsonServers": ["..."],
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command", "command": "codegraph prompt-hook" }] }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit|NotebookEdit",
        "hooks": [{ "type": "command", "command": ".claude/hooks/ruff-check.sh" }]
      }
    ]
  },
  "enabledPlugins": { "...": "see §6.1" }
}
```

> **Intent (nesting).** A top-level `"PostToolUse"` key is **accepted and does nothing** — no error, no warning — and §11 #4 pipes into the script directly, so it **cannot** detect the misregistration. §11 #4e asserts the registration itself. §9 #15.

> **Intent (matcher).** Matchers are **full-match**, not substring: `"Edit|Write"` does NOT match `MultiEdit` or `NotebookEdit`. Verified against the working example still on disk — `security-guidance`'s `hooks.json` enumerates all four explicitly for this reason. A hole at `MultiEdit` would be a hole precisely where subagents do bulk edits, which is the case this hook exists to cover.

**The hook input contract — read from the authority, not assumed.** Claude Code delivers hook input as **JSON on stdin** (the tool's `tool_input.file_path`), **not** as argv, and a hook's plain stdout on exit 0 is **not** delivered to the model. Returning text to the model requires the envelope:

```json
{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"..."}}
```

> **Verified** against `~/.claude/plugins/cache/claude-plugins-official/security-guidance/2.0.6/hooks/security_reminder_hook.py`, a working PostToolUse hook: it reads `raw_input = sys.stdin.read()` and emits `out["hookSpecificOutput"] = {..., "additionalContext": ...}`.
>
> **Intent.** A hook that assumes argv, or prints bare stdout, **prints into the void** — silently. §9 #3.

`.claude/hooks/ruff-check.sh` MUST:
- begin `set -euo pipefail`;
- read JSON from **stdin** and extract `.tool_input.file_path` with `jq -r`;
- exit 0 silently when the path is absent, empty, or `null`;
- exit 0 silently when the file is not Python (`*.py`, or the extension-less `pantheon-sitehealth-emails`);
- **resolve the path and confirm it is inside the repo root**; exit 0 silently otherwise;
- run `ruff check` with the §4.1 rule set on **only** that file, passing the path **double-quoted** and after a `--` separator;
- emit findings **inside the `hookSpecificOutput.additionalContext` envelope**; emit **nothing** when clean;
- exit 0 always — it is advisory, and `./run-tests` (§4.5) is the gate.

**MUST NEVER:** interpolate `file_path` unquoted. It is model-controlled text; `ruff check $FILE` unquoted is command injection. The `--` separator, the double quotes, and the repo-root containment check are each required, not stylistic.

> **Intent.** This delivers §4.1 at the moment of the mistake rather than at `./run-tests` time, and — critically — **corrects a fresh-context subagent without any standard needing to be injected**. It is §5's principle (mechanize, don't curate) applied to *delivery*.
>
> **Tension acknowledged.** `security-guidance` is being removed (§6) partly for hook surface. The distinguishing properties, which any future hook MUST also satisfy: this hook is **narrow** (one linter, one file, four rules), **synchronous** (never re-wakes the model out-of-band), **silent when clean**, **advisory** (never blocks), and **small enough to read in full**. `security-guidance`'s `Stop` hook satisfied none of these.

### 4.5 `./run-tests` runs ruff

`./run-tests` MUST run the §4.1 ruff check and fail the run on a finding, in **both** `--fast` and full modes.

> **Intent.** The hook (§4.4) is advisory and can be bypassed; the gate must live where the evidence is produced. Consistent with `implementation-standards.md`: evidence is "the command and output pasted."

### 4.6 Prose SHOULD not restate what a check now detects

Once §4.1–§4.5 land, prose asserting **detection** of what ruff now detects SHOULD be reduced to a pointer. PD#2's *judgment* ("name the exception, say what catches it, what the operator sees, whether it's tested") **stays** — it is not mechanizable.

> **Intent.** **Not a token argument** — the read list is ~279 lines (`directives.md` ~108 + `implementation-standards.md` 171) ≈ 18.9 KB ≈ 4.7k tokens per dispatch, affordable either way, and this is **not** a §13 prerequisite. §9 #18.
>
> **The true rationale is DRY**, and it is enough: once ruff detects `E722`, prose that *also* asserts detection is a second source of truth, and two sources drift — exactly as PD#11 drifted between two files (§1a).
>
> **The observable is the outcome, not the mechanism**: §11 caps the Spine's length and requires `prompts/` duplication to be 0. Those are checkable; "did you subtract enough prose?" is not.

---

## 5. `prompts/` restructure (PRIMARY + SECONDARY)

### 5.1 Spine + deltas

```
                       BEFORE                                   AFTER

  new-feature-standards.md (149 ln) ──┐          ┌── directives.md  (NEW, ~108 ln)
    Posture ............. copy A      │          │     Posture               ← one copy
    PD 1-13 ............. copy A      │          │     PD 1-14 (rev. 8, +14) ← one copy
    Eng. Preferences .... copy A      │  53 ln   │     Engineering Prefs     ← one copy
    Spec quality bar .... copy A      │ verbatim │     Spec quality bar      ← one copy
    Selecting a solution              │  dup'd,  │            ▲
    This project's context            │  already │            │ read by all
                                      │  DRIFTED │            │
  adversarial-review.md (132 ln) ─────┤  (PD#11) │  ┌─────────┼─────────┬──────────────┐
    Posture ............. copy B      │          │  │         │         │              │
    PD 1-13 ............. copy B ◄────┘ STALE    │  new-      advers-   implementation-  debugging-
    Eng. Preferences .... copy B                 │  feature-  ial-      standards.md     standards.md
    Spec quality bar .... copy B                 │  standards review.md  (~171 ln)       (110 ln)
    Review process (unique)                      │  (~60 ln)  (~50 ln)   amended*        UNCHANGED
                                                 │   delta     delta                     (0% dup)
                                                 │
  NOTE: adversarial-review.md's Posture is a differently-worded VARIANT, not a
  verbatim duplicate ("12 years of experience with Python command line tool
  development" vs. the Spine's "12+ years of Python CLI tooling").  It is
  REPLACED by the Spine, not deduplicated -- so it is not among the 53.
                                                 └─ * except §5.2 (read list) + §3.1 (PD#7)
```

**Changes — exhaustive:**

| File | Action | Note |
|---|---|---|
| `prompts/directives.md` | **CREATE** | Posture; PD#1–14 (PD#8 revised per §3.1, PD#14 added per §3.2); Engineering Preferences; spec quality bar. The single copy. |
| `prompts/new-feature-standards.md` | **REDUCE** to delta | Keeps: the two things the skill doesn't do (verify claims; expansions one at a time), *Selecting a solution*, spec location, *This project's context*. Links to the Spine. |
| `prompts/adversarial-review.md` | **REDUCE** to delta | Keeps the review process only. Fixes §5.3. Links to the Spine. |
| `prompts/implementation-standards.md` | **AMEND** | §5.2 (read list + `subagent_type`), §3.1 (directive #7 conditional), §7.3 (DoD lines). **Posture: strip ONLY the two duplicated sentences** (lines 13–14, the persona) — **RETAIN lines 15–17 verbatim**, they are unique. Structure otherwise unchanged. |
| `prompts/debugging-standards.md` | **UNCHANGED** | Measured 0% duplication. |
| `prompts/add-tests-for-change.prompt.md`, `refresh-fixtures.prompt.md`, `update-claude-md.md` | **UNCHANGED** | Measured 0% duplication. |

**MUST NEVER:** restate a Spine rule in an overlay. An overlay MAY cite a directive by number.

### 5.2 Fixed read list replaces curation

`prompts/implementation-standards.md` § "How this overlay is applied" MUST be rewritten. The per-dispatch curation table is **removed**. Every implementer and reviewer brief MUST open with:

```
Before doing anything, read in full:
  1. prompts/directives.md              (the standards spine)
  2. prompts/implementation-standards.md (implementation bar + house style)
  3. <the spec for this increment>
```

> **Intent.** Curation makes standards delivery depend on the controller's judgment at the moment its context is fullest — the reported failure (§1b). A fixed list removes the judgment.

**But a read list is still prose the controller pastes**, which §1d says is the losing category ("the standards that are never violated are the ones that are code"). Two additions close that gap — the first reduces the failure, the second makes it *visible*:

**(a) A repo-local implementer agent carries the read list as config.** Create `.claude/agents/psh-implementer.md`:

```markdown
---
name: psh-implementer
description: Implementer for pantheon-sitehealth-emails. Carries this repo's standards.
---
Before doing anything else, read IN FULL:
  1. prompts/directives.md               (the standards spine)
  2. prompts/implementation-standards.md (implementation bar + house style)
Then read the task brief and the spec named in your dispatch.
Your report MUST cite, by number, the Spine directives you applied.
```

**A sibling `.claude/agents/psh-reviewer.md` MUST be created**, carrying the same read list plus the reviewer persona, and `prompts/adversarial-review.md` MUST dispatch it by `subagent_type` instead of pasting the persona into a prompt.

> **Intent.** §1a's *proven* failure is that the adversarial reviewer — dispatched with fresh context precisely to be independent — reads the **stale** PD#11. It is the one role whose standards-blindness is demonstrated rather than suspected. §5.1's consolidation removes the stale *copy*; the agent removes the *pasted persona* that has to be got right every time. §9 #13.

`prompts/implementation-standards.md` MUST document dispatching with `subagent_type: "psh-implementer"`, in the same section that already overrides the TDD default — the established place this project changes a skill's default.

> **REGISTRATION (MUST).** `.claude/agents/` is read at **session start**. An agent file created or renamed mid-session is **not dispatchable until the session reloads** — `subagent_type: "psh-implementer"` errors with *"Agent type not found."* §11 #4d greps the file, which proves only that the text exists; **registration is the evidence** (PD#14). §11 #4d-ii asserts it. Discovered by hitting it: the first dispatch after creating the agents failed. See §9 #22.
>
> **The dangerous failure is not the error — it is the fallback.** A controller that hits "not found" and quietly reverts to `general-purpose` gets the old curation problem with none of the signal. A dispatch that cannot use `psh-implementer` MUST stop and say so, never silently substitute.

> **Honest limit.** `superpowers:subagent-driven-development`'s own template dispatches `Subagent (general-purpose)`, so the controller must still *choose* the custom type. That is a single uniform parameter, not a per-task curation judgment — a large reduction in failure surface, **not zero**. This is "less prose," not "code." Claiming otherwise would repeat §9's pattern.

**(b) The report must cite the Spine *and quote it verbatim* — which makes "did it read?" observable.** Added to § Definition of Done (§7.3):

> The task report MUST cite, **by number**, each Spine directive applied to this task and how — and MUST **quote a verbatim clause** from each directive it cites.

Verified by §11 #5c, which **normalizes whitespace on both sides** before comparing.

> **Intent.** Citation **by number alone is not an observable** — numbers and gists are quotable from the brief and from this spec, and nothing checks the citation is accurate. A **byte-exact clause is not reconstructible from a gist**. That is the difference between an instrument with a red state and a claim about one. §9 #12, #17.

**Retained from the current text — exhaustive.** These are judgment or standing rules, **not** curation, and MUST survive the rewrite:

1. **The execution-bar rule** — `implementation-standards.md:15–17`, verbatim: *"During execution the bar is not 'does the task pass its reviewer' — it is 'would this survive adversarial review'… Build to that bar the first time so the fix loop stays short."* **Unique to this file** — it is absent from the Spine's design-time Posture, and §11 #5 (which counts only *duplicated* lines) would report green after deleting it. See §9 #16.
2. **The plan-vs-standards conflict rule** — surface the finding beside the plan text and ask which governs; never silently "fix" the plan.
3. **The TDD override** — `mattpocock-skills:tdd`, injected **by name**, because "the host's default wins silently if you don't."
4. **The reviewer anti-gaming rule** — from the removed curation table: *"Do **not** tell the reviewer what to downgrade or ignore; that is the skill's rule and it holds."* A standing rule, not a selection judgment.
5. **Fix-subagents are a third role.** The removed table gave them guidance; the read list names only implementers and reviewers. Fix-subagents MUST also dispatch as `psh-implementer`.

**Superseded:** "An un-injected standard does not exist" is retained as *rationale for the read list*, not as a justification for curation.

### 5.3 Fix the reviewer's contradictory instruction

`prompts/adversarial-review.md` line 14 instructs the reviewer to "review the document(s) on **5 dimensions**" and then lists **10** (Correctness, Completeness, Consistency, Clarity, Feasibility, Maintainability, Robustness/fragility, Security, Testing, Observability). MUST be corrected to 10.

> **Intent.** The reviewer runs with fresh context and cannot ask. Facing "5" above a list of 10, it silently picks — and which 5 it picks is unobservable. A quality gate whose scope is nondeterministic is PD#1 and PD#14 in one.

---

## 6. Tools (SECONDARY)

### 6.1 Canonical disposition table

`always_on` = tokens loaded into every session, from the plugin catalog (`~/.claude/plugins/plugin-catalog-cache.json`).

> **Caveat.** The catalog publishes figures for `claude-opus-4-7` and `claude-sonnet-4-6` only; this project runs **opus-4-8**. The numbers are therefore a **proxy**, not the operative model's exact cost. They are used only for *relative* comparison (cloudflare 1765 vs. superpowers 720), which is robust to a uniform tokenizer difference. No decision here turns on an absolute value.

| Tool | always_on | Decision | Reason |
|---|---|---|---|
| `superpowers` | 720 | **KEEP** | The host. Overlays are written against it. |
| `mattpocock-skills` | — | **KEEP** | `/improve-codebase-architecture` (used 2–3×/week), `/tdd`, `/grilling`, `/diagnosing-bugs`, `/codebase-design`, `/domain-modeling`. |
| `andrej-karpathy-skills` | — | **KEEP** | Mandated by `CLAUDE.md` § Other/General. |
| `claude-md-management` | 180 | **KEEP** | `/claude-md-improver` is invoked by `prompts/update-claude-md.md`, run 2–3×/week. |
| `pyright-lsp` | **0** | **KEEP — no change** | **Correction (§9).** Functional. LSP plugins register via the *marketplace* manifest (`lspServers: ["pyright"]`), not the plugin dir; a cache dir holding only a README is the expected shape (cf. `clangd-lsp`, `csharp-lsp`). `pyright` is on PATH. |
| `codegraph` (MCP) | — | **KEEP** | Mandated by `.claude/CLAUDE.md`; `UserPromptSubmit` hook. |
| `chrome-devtools` (MCP) | ~0 (deferred) | **KEEP — no change** | ~30 tools, but deferred via ToolSearch, not resident. Render tier drives `pytest-playwright` directly; this is ad-hoc debugging only. |
| `cloudflare` | **1765** | **UNINSTALL — lift 2 MCP servers out first** | **Correction (§9 #5).** The single largest consumer in the inventory — **2.5× `superpowers`**, and **5.7×** what both other uninstalls save combined (312). The 1765 is **the 11 skills** — its 2 commands contribute 150 of 4516 always-on chars (~3%), and none of the 11 reaches this codebase; its MCP servers cost **0** (deferred), so the originally-planned "trim MCP" would have saved nothing. None of the 11 skills reaches this codebase: `plugin/cloudflare/` calls `dns.records.list`, `zones`, `ips.list`, `rules.lists` via the Python SDK; the skills cover Workers/Pages/Durable Objects/Wrangler/Turnstile/Sandbox/Agents SDK/Zero Trust/Email. **Capability is preserved at zero cost** by lifting the two useful servers into `/workspace/.mcp.json` (§6.2). Deliberately given up: `web-perf` (473 **chars** ≈ 118 tokens — the catalog reports per-skill cost in chars, per-plugin in tokens) — real Core Web Vitals capability via `chrome-devtools` MCP, unused here; reinstall is one command. |
| `feature-dev` | **243** | **UNINSTALL** | **Cross-purposes.** `/feature-dev` runs "Discovery → clarifying questions → design architecture → implement" — the same span as `brainstorming` → `writing-plans` → `subagent-driven-development`. `CLAUDE.md` § Agent skills warns about exactly this conflict for Matt's pipeline but never mentions `feature-dev`. Its 3 agents (`code-explorer`, `code-architect`, `code-reviewer`) sit in the dispatch listing where a subagent call could select a standards-blind reviewer. |
| `security-guidance` | **0** | **UNINSTALL** | **Behavioral cost, not token cost (§9).** A `Stop` hook `asyncRewake`s the model with an unsupervised LLM diff review after **every response**; `PostToolUse` does the same on `git commit`/`git push`. A third reviewer, uninvited, mid-flow, duplicating `/code-review high` and `prompts/adversarial-review.md`. Coverage retained: built-in `/security-review`, PD#6, ruff `S105`/`S106` (§4.1). |
| `code-simplifier` | 69 | **UNINSTALL** | Never invoked. Overlaps built-in `/simplify`. |

### 6.2 Lifting the Cloudflare MCP servers out of the plugin

The plugin's servers are plain HTTP URLs with no plugin-provided auth, so they survive its removal verbatim. Add to `/workspace/.mcp.json` **before** uninstalling:

**The MERGED document — `/workspace/.mcp.json` already contains `codegraph` and `chrome-devtools`.** Shown in full because the quality bar requires "config shown as an actual file snippet," and because a fragment here would be read as a replacement:

```json
{
  "mcpServers": {
    "codegraph": {
      "type": "stdio",
      "command": "codegraph",
      "args": ["serve", "--mcp"]
    },
    "chrome-devtools": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest", "--headless", "--isolated",
               "--executablePath",
               "/usr/local/share/ms-playwright/chrome-current/chrome-linux/chrome",
               "--chromeArg=--no-sandbox"]
    },
    "cloudflare-api":  { "type": "http", "url": "https://mcp.cloudflare.com/mcp" },
    "cloudflare-docs": { "type": "http", "url": "https://docs.mcp.cloudflare.com/mcp" }
  }
}
```

> **MUST NEVER** write this file as a two-server document. A `{"mcpServers": {…}}` wrapper holding only the two new entries **deletes `codegraph`**, which `.claude/CLAUDE.md` mandates ("reach for it BEFORE grep/find"). §11 #7a asserts the **exact set** of four for this reason, not "includes". §9 #14.

Also add both to `enabledMcpjsonServers` in `.claude/settings.json`, beside `codegraph` and `chrome-devtools`.

**NOT lifted (exhaustive):** `cloudflare-bindings`, `cloudflare-builds`, `cloudflare-observability` — OAuth-gated and Workers-deployment-oriented; no path to this codebase.

> **Intent.** Order matters: lift first, verify the servers resolve, then uninstall. Uninstalling first leaves a window with no Cloudflare API access.

### 6.3 NOT installing

| Candidate | always_on | Why not |
|---|---|---|
| `context7` | 0 | **Considered and rejected.** Case for: `CLAUDE.md` § Database documents subtle SQLAlchemy behavior that training data gets wrong (mysqldb classifies a lost connection by error *code*; it surfaces as `InterfaceError`/`ProgrammingError(2014)`, siblings of `OperationalError` under `DBAPIError`, unified only by `connection_invalidated`). Case against: the `## Reference material` convention already fetches docs on demand, and it is unproven here. **User rejected.** |
| `pr-review-toolkit` | 2038 | No PRs; work goes directly to `main`. |
| `github`, `playwright` (MCP) | 0 | No PRs; render tier uses `pytest-playwright` directly. |
| `claude-code-setup` | 144 | Does once what this session is doing. |
| `skill-creator`, `commit-commands`, `ralph-loop`, `frontend-design` | various | No applicable use. |

### 6.4 `CLAUDE.md` — the `.py` symlink now serves two tools

`CLAUDE.md` § Conventions & gotchas currently justifies the committed `pantheon-sitehealth-emails.py` symlink by CodeGraph alone. It MUST also record that **`pyright-lsp` binds to `.py`/`.pyi`**, so the extension-less main program was invisible to the LSP for the identical reason, and the symlink fixes both.

> **Intent.** The symlink is tracked-not-ignored on purpose. Its rationale is now load-bearing for two tools; a future session that deletes it would silently blind both. Also add `ruff` (§4.1 `target-version`) as a third consumer.

---

## 7. Process changes

### 7.1 Session structure — unchanged

One session, `superpowers:subagent-driven-development`, as today.

> **Intent.** Splitting design from implementation was considered. Its main argument was that the controller's context is full by implementation time — which is precisely the curation dependency §5.2 removes. With curation gone, the split buys little and would re-point `implementation-standards.md` at `executing-plans`, a skill it was not written for. **Rejected; recorded per PD#9.**

### 7.2 Campaign structure

```
development/<YYYY-MM-DD>-modularization/
├── CAMPAIGN.md          ← ONE adversarial review, run HARD
│     • target module boundaries
│     • which seam each new package uses
│     • what stays in the core, and why
│     • invariants EVERY increment preserves:
│         - the four e2e goldens stay byte-identical
│         - the per-phase data contract is honored
│         - the non-UMich path keeps working
│     • the increment order, and why
└── <NN>-<sub-area>/
      └── SPEC.md        ← thin; references CAMPAIGN.md; NOT re-derived
```

> **Intent.** The Campaign is one architectural program in N similar increments, not N unrelated features. Re-brainstorming the target architecture per increment re-derives the same boundaries N times and lets them drift. The concentration of scrutiny on `CAMPAIGN.md` is deliberate: that is where an error is cheapest to fix and most expensive to miss.

Each Increment gets a **thin** spec that references `CAMPAIGN.md` and does not re-derive it. Increments touch `main()` by construction, so each still gets the full implementation treatment — subagent-driven-development, `/code-review`, archive. What they do **not** repeat is the design scrutiny `CAMPAIGN.md` already passed: the brainstorm and the adversarial review ran **once**, on the campaign, where an error is cheapest to fix and most expensive to miss.

> **Intent.** This is where the Campaign's ceremony reduction actually comes from — inheritance of design scrutiny, not a tier table. §1c's tier model was dropped precisely because this covers the imminent work and a tier table would not.

### 7.3 `CLAUDE.md` shrinkage joins the per-increment Definition of Done

Added to `prompts/implementation-standards.md` § Definition of Done:

> **`CLAUDE.md` prose that existed to explain logic this increment moved into a package MUST be deleted in the same commit.** Report the line-count delta.

**EXEMPT — by predicate, not by section name:**

> Prose that records a **shipped defect's root cause and its non-obvious repair** is EXEMPT — **unless a named test already guards that defect.** Where a test guards it, the prose reduces to a **one-line pointer at that test**.

Prose is **NOT** exempt merely for being old, long, architectural, or hard to write.

**Example of the discharge:**

```
BEFORE (CLAUDE.md, § Database):
  The load-bearing piece is the commit after a read-only SELECT in
  load_traffic_rows() ... without which the session holds an idle
  in-transaction connection that gets reaped and dies at the next query
  with MySQL error 2013 - do not remove it
  (test_load_traffic_rows_releases_the_connection guards it).

AFTER:
  The commit after the read-only SELECT in load_traffic_rows() /
  load_overage_protection_window() is load-bearing; guarded by
  test_load_traffic_rows_releases_the_connection.
```

> **The discharge condition is what bounds it, and it follows from §1d**: "the standards that are never violated are the ones that are code." Where a named test guards the defect, **the test is the durable record** — it can go red; prose cannot. CLAUDE.md keeps a pointer, the knowledge survives in the instrument that enforces it, and §15 Q2 finally has something to measure. Where **no** test guards the defect, the prose is the only record and stays in full — and that gap is itself a finding worth raising.

> **Intent.** Two earlier formulations were both over-broad; this one is bounded by a discharge condition. §9 #19.
>
> The rule's basis: much of `CLAUDE.md` is documentation standing in for structure the code doesn't express. As logic moves into packages, that prose retires with it. **Defect knowledge is the opposite** — no amount of modularization makes it re-derivable, and deleting one line of it re-opens a closed defect. A session applying this rule MUST NOT trade defect knowledge for a line-count win.

**Worked examples — this is the distinction, so both are load-bearing:**

| Prose | Verdict | Why |
|---|---|---|
| § "Single-module core + `script_context` shared state"; the narration of what `main()` does internally | **RETIRES** | It exists because the core is a 4,752-line monolith. Once the logic is packages with names and boundaries, the code says it. |
| § Database — the two rich gotchas; the `db_retry`/`db_retryable` classification; the reconnect-counter semantics | **EXEMPT** | Each records a shipped defect's root cause. Two of them shipped **twice**. |
| **The per-phase data contract table** | **EXEMPT — and it gets MORE load-bearing** | Packages are the contract's *consumers*, so modularization makes it more central, not less — §7.2's invariant list says "the per-phase data contract is honored." **This is the row to read twice**: it is the example this rule most invites getting backwards. §9 #20. |

---

## 8. Deferred — written down per PD#9

| Deferred | Why now is wrong | Revisit |
|---|---|---|
| **Broaden ruff** to `E,F,W,I,UP,B` | Hundreds of findings on first run; a triage-and-fix effort of its own, on the file the Campaign is about to restructure | After the Campaign |
| **pyright in `./run-tests`** | Not narrow: **39 errors** on `check/` + `plugin/` alone, and they are pyright disagreeing with three *documented* choices — the `-> (str, str, bool)` house style ("Tuple expression not allowed in type expression"), the runtime-exposed `sc.*` callables ("`umich_enabled` is not a known attribute of module `script_context`"), and `sc.options` being a dict. Resolving them means annotating `script_context.py` or blanket-ignoring — on soon-to-move code. **The LSP half needs no work and is already active at 0 tokens.** | After the Campaign |
| **`README.md` TODO entries** for all deferrals | PD#9: vague intentions are lies | In this change |
| **Reconcile `README.md:265`** — the existing TODO *"Add ruff for linting+formatting, switch from 'house styles' to best-practice/standard Python styles"* | It predates this spec and **conflicts with it**: §4.1 adopts ruff *narrowly*, §8 defers broadening, and `implementation-standards.md` § Fresh-context trap **retains** the `-> (str, str, bool)` house style the TODO proposes to abolish. Leaving both is a standard at cross-purposes with itself (goal 2) | **In this change**: rewrite the TODO to say ruff is adopted narrowly, broadening is deferred, and the house-style question is a **separate, undecided** call — or delete it |
| **A risk-tier model for §1c** (`FULL`/`LIGHT`/`DIRECT`, triaged once up front) | Designed, then **dropped under PD#12**. Campaign increments touch `main()` by construction, so it would classify nearly all imminent work as maximum ceremony — delivering ~nothing for the pain it was built for, while adding a model to maintain and no way to validate it against work that does not exist yet | **Trigger, not a date:** when the Campaign has produced LIGHT-eligible work (new checks living entirely inside a package, behind existing seams) in enough volume to triage. §15 Q8 |

---

## 9. Claims corrected during design

Recorded because `new-feature-standards.md` § "Two things the skill does not tell you to do" #1 requires load-bearing claims be independently verified, and two of mine failed.

| # | Claim I made | Reality | How it was caught |
|---|---|---|---|
| 1 | "`pyright-lsp` is broken — its cache dir has only a README and LICENSE, no `plugin.json`" | **Functional.** LSP plugins register via the marketplace manifest (`lspServers: ["pyright"]`), not the plugin dir. A README-only cache dir is the expected shape. | Checking `plugin-catalog-cache.json` instead of inferring from directory contents |
| 2 | "`security-guidance` is your heaviest always-on surface" | **0 always-on tokens.** Its cost is behavioral (`Stop`-hook `asyncRewake`), not contextual. Removal still correct; the reason is different. | The catalog's per-plugin `always_on` counts |
| 3 | §4.4: the hook receives the file path as **argv** and its stdout reaches the model | **False.** Input is **JSON on stdin** (`.tool_input.file_path`); exit-0 stdout is discarded; returning text requires the `hookSpecificOutput.additionalContext` envelope. A hook built to the original text would have printed **into the void, silently**. | Adversarial review; then reading `security-guidance`'s working hook (`raw_input = sys.stdin.read()`) |
| 4 | §4.4: `matcher: "Edit\|Write"` covers the edit tools | **False.** Matchers are full-match: it misses `MultiEdit` and `NotebookEdit` — a hole exactly where subagents bulk-edit. | Adversarial review; `security-guidance`'s `hooks.json` enumerates all four |
| 5 | §6.1: `cloudflare` always-on cost "—"; the fix is to trim its MCP servers | **False on both counts.** `always_on = 1765` — **2.5× `superpowers`**, and the single largest consumer in the inventory. Its MCP servers cost **0** (deferred via ToolSearch), so the prescribed action saves ~nothing. See §6.2. | Adversarial review; the catalog's per-component token table |
| 6 | §1a: duplication is between **two** files | **Incomplete.** 55 lines across **three**: 53 (new-feature↔adversarial) + 2 Posture lines (new-feature↔implementation-standards). | Adversarial review — **though the original measurement in this session printed the 2-line pair and it was overlooked** |
| 7 | §1a "40% and 36% … respectively"; §3.1 "8 of 10 specs" | Reversed (35.6% / 40.2%); and it is **9 of 11**. Conclusions survive; the numbers didn't. | Adversarial review |
| 8 | §4.1: pin `target-version = "py312"` | **Actively harmful.** Ruff infers the target from `requires-python`, so pinning it **masks §4.2 entirely** — verified: the 10 invalid-syntax errors *vanish*. §4.1 would have silenced the bug §4.2 exists to fix, and §11 #2b existed only to work around the masking §4.1 chose. A future session reverting `requires-python` would get silence. | Adversarial review round 2; then running both commands |
| 9 | §11 #4/#4b: hook fixtures in `/tmp` | **Unreachable / vacuous.** Round 1 added §4.4's repo-root containment rule, which makes a *correct* hook emit nothing for `/tmp/x.py` — so #4 could never pass, and #4b's injection test passed at the containment check, leaving **quoting untested forever**. Two round-1 fixes collided and §11 was never re-run against the merged text. | Adversarial review round 2 |
| 10 | §11 #4c: Spine cap "≤ 100 lines" | **Unreachable and gameable.** Source material measures **102 lines** before PD#14 and headers (~108 assembled). And a line cap is satisfiable by *reflowing paragraphs* — passing while changing nothing. Now capped in **bytes**. | Adversarial review round 2; then measuring `prompts/new-feature-standards.md` |
| 11 | §11 #2: "BEFORE = 17" for `ruff check .`; §11 #2b's `grep` | **Both wrong.** Bare `ruff check .` uses ruff's *default* set — which contains neither `S105` nor `BLE001` — and reports **55**, not 17. And #2b's `grep` was case-sensitive, so it **reported green against `README.md:12`**, the exact stale claim it existed to catch. | Adversarial review round 2; then **running §11** |

| 12 | §5.2(b): "a subagent that did not read **cannot cite**, so the read list acquires a red state" | **False.** Numbers and gists are quotable from the brief and from this spec (which cites nine PDs by number and gist). Red-capability asserted **by argument** — what the Glossary's "Red-capable" entry forbids. Now requires a **byte-exact clause**, grep-verified (§11 #5c). | Adversarial review round 2 |
| 13 | §5.2: "every implementer **and reviewer** brief MUST open with…" | **Overclaimed.** Only `psh-implementer` was created. The **reviewer** is the one role whose standards-blindness §1a *proves*, and it was the one left unmechanized. `psh-reviewer` added. | Adversarial review round 2 |

| 14 | §6.2: showed `.mcp.json` as a two-server document | **Destructive.** The real file already holds `codegraph` and `chrome-devtools`; an implementer following it literally **deletes the CodeGraph MCP that `.claude/CLAUDE.md` mandates** — and §11 #7a's "includes" check passed on the clobbered file. Now shows the merged 4-server document; #7a asserts the exact set. | Adversarial review round 3 |
| 15 | §4.4: showed `"PostToolUse"` as a top-level `settings.json` key | **Silently inert.** Hooks nest under `"hooks"`, beside `UserPromptSubmit`. A top-level key is accepted and does nothing — no error, no warning — and §11 #4 pipes into the script directly, so it **cannot** detect the misregistration. Now shown nested; #4e asserts the registration. | Adversarial review round 3 |
| 16 | §5.1: "strip the Posture paragraph — it is the remaining 2 duplicated lines" | **Would have deleted a standard.** That Posture is 5 lines; only 13–14 are duplicated. Lines 15–17 are unique and carry the **execution-bar rule** ("would this survive adversarial review"). §11 #5 counts only *duplicated* lines, so it would have reported **green** after the deletion. | Adversarial review round 3 |
| 17 | §5.2(b): verify the verbatim quote with `grep -qF` | **Broken in both directions** — and it was round 2's own fix, shipped unexecuted. `directives.md` hard-wraps and grep is line-oriented, so an **honest** quote spanning a wrap exits 1 (false red); a multi-line `-F` pattern matches if **any** line matches, so a clause with one real line and two invented ones exits 0 (false green). Both reproduced. Now normalizes whitespace on both sides. | Adversarial review round 3 |
| 22 | §5.2: creating `.claude/agents/psh-*.md` makes them dispatchable | **Not until the session reloads.** `.claude/agents/` is read at session start; the first dispatch after creating them failed with *"Agent type 'psh-implementer' not found."* §11 #4d greps the file — a claim — and would never have caught it; **registration is the evidence**. Same defect as #15 (`settings.json` nesting): I wrote a criterion for that instance and did not generalize the class. §11 #4d-ii added. | Hitting it — the first dispatch through the new mechanism errored |
| 21 | §13: "§4 … Lands first because §11's 'before' numbers are pinned to today's tree" | **Reason does not hold.** §5 edits only markdown and cannot move a ruff count, so §4-first was not required — and it had an unnamed cost: §5 creates `psh-implementer`, so §4's subagents would have been dispatched by the curation mechanism §5 replaces. Order revised to §3+§5 → §4, authorized before implementation. | Caught at implementation start, checking §13's stated reason against what §5 actually touches |
| 19 | §7.3: exempt a **named list of CLAUDE.md sections** (draft 1), then a **bare predicate** (draft 2) | **Both over-broad.** The list measured **~288 of 728 lines (~40%)** and was unbounded (it must grow with every new section). The bare predicate was plausibly *wider still* — it covers both rich gotchas, `db_retryable`, the SELECT commit, `expire_on_commit`, `TrafficRow`-not-ORM, the two-`sitecustomize` trap, the goldens trap, the `.py` symlink, `html_to_text`, the re-indent trap, the `-results.json` metadata; 2 of 3 worked examples were EXEMPT. Now bounded by a **discharge condition**: exempt *unless a named test already guards the defect*. | Adversarial review rounds 1 and 2 |
| 20 | §7.3: used the **per-phase data contract table** as the example of prose that retires | **Backwards.** Packages are the contract's *consumers*, so modularization makes it **more** load-bearing — §7.2's invariant list already says "the per-phase data contract is honored." It is now the table's cautionary EXEMPT row. | Adversarial review round 1 |
| 18 | §4.6: "~271 lines … ≈ 11k tokens" | Wrong three ways (95+171=266; `directives.md` is ~108 per §5.1; the real total is ~4.7k tokens) — in the paragraph whose whole rhetorical weight is *"that rationale is arithmetically false."* | Adversarial review round 3 |

> **The pattern in 8–11 is one thing: §11 was written and never executed.** Every one of them would have surfaced in five minutes by doing what §11's own preamble demands — "run and paste the **real** output, never summarized, never 'should pass'." The spec whose central contribution is PD#14 ("a green check is a claim, not evidence, until shown capable of going red") shipped an acceptance suite that had never been run. **§11 has now been executed against the real tree**; its recorded BEFORE values are observed output, not estimates.

> **Intent.** Every one of these shares a shape: **inferring a fact from an artifact's appearance rather than reading the authority.** #3 is the sharpest — the section *introducing* PD#14 specified an instrument that would fail silently, which is precisely what PD#14 exists to prevent. #6 is the most instructive: the correct data was produced during design and not read. PD#14 is the general form, and this table is the evidence it earns its place.
>
> **This table MUST be retained in the archived spec.** It is the only record that this design's own verification discipline had to be applied to itself, twice.

---

## 10. Seams under test

Required by the quality bar: named and agreed **before** implementation, because implementers run test-first (`mattpocock-skills:tdd`) at pre-agreed seams and cannot ask.

| Change | Seam | Tier | Test-first? |
|---|---|---|---|
| §4.1 ruff config | `./run-tests` — the command itself | e2e (manual) | No — config. Acceptance = §11. |
| §4.2 `requires-python` | `uvx ruff check` default target derived from `requires-python` | — | No — config. Acceptance = §11. |
| §4.3 house rules | `tests/unit/test_house_rules.py` — the file is the seam | unit | **No — and this is the point.** These are Instruments (PD#14): they pass on creation. The requirement is the **red demonstration** in §4.3, not red→green. |
| §4.4 ruff hook | `.claude/hooks/ruff-check.sh` — a shell script, run directly | manual | No. Acceptance = §11. |
| §4.5 ruff in `./run-tests` | `./run-tests --fast` exit status | e2e (manual) | No. Acceptance = §11. |
| §4.1 `ips.py` fix | `run_terminus` is **not** the seam. The Cloudflare SDK call is reached via `sc.plugin_context['plugin.cloudflare']['get_client']()` — monkeypatch the client, as `tests/integration/test_plugin_cloudflare_client.py` does | integration | **Yes.** Test asserting the named exception surfaces; watch it fail against the current `except Exception`. |
| §3, §5, §6, §7 | **None — no seam is worth making.** | — | These are prose, config, and plugin-inventory changes with no runtime surface. Stated explicitly rather than silently skipped, per the quality bar: "Silence is not an option a reviewer should accept." |

**No pure helper is extracted by this change**, because no change here touches `main()`.

### NEVER — tests are load-bearing

Tests MUST NEVER be weakened, `sleep`-padded, or matcher-loosened to go green. A failing test is a signal to fix the code. Golden/fixture regeneration (`--update-goldens`, `--record`) requires a reviewed diff with every changed byte justified. **This change touches no golden; if a golden moves, that is a defect in this change, not a golden to refresh.**

---

## 11. Acceptance criteria

Exact commands with expected output. Every one MUST be run and its **real** output pasted into the completion report — never summarized, never "should pass."

```bash
# 1. Ruff clean at the narrow rule set, across everything.
$ ./run-tests --fast
#    EXPECT: ruff step runs and reports 0 findings; full --fast suite green.

# 2. requires-python fixed: no invalid-syntax at the DECLARED target.
$ uvx ruff check --select E722,BLE001,S105,S106 .
#    EXPECT: "All checks passed!"
#    BEFORE (RUN 2026-07-16, real output):
#        10  invalid-syntax        <- §4.2: requires-python says 3.11, code is 3.12+
#         5  S105                  <- test fixtures; §4.1 per-file-ignores
#         2  BLE001                <- :4721 (noqa) and ips.py:18 (fix)
#        Found 17 errors.
#    With §4.1's rule set, requires-python ALONE drives the syntax check -- so this
#    single command tests §4.1 AND §4.2.  That is why §4.1 pins no target-version.
#
#    NOTE: `ruff check .` resolves the .py symlink and skips the extension-less twin.
#    Do NOT run BARE `ruff check .` here: its default rule set has neither S105 nor
#    BLE001, and it reports 55 unrelated findings -- that is §8's deferred
#    broadening, not this change.  §9 #11.

# 2b. The README's Python claim is not merely stale -- it is FALSE and says so.
#     README.md:12 reads "It should work with Python 3.11 but that has not been
#     tested."  It does not work; §4.2 proves it.  Correct the line.
$ python3 -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['requires-python'])"
#    EXPECT: >=3.12
$ grep -niE '(should work with|works with) python[^0-9]*3\.11' README.md
#    EXPECT: no output.
#    Intent: match the CLAIM, not the digits.  Two traps:
#      (a) -i is load-bearing: without it this MISSES README.md:12 ("...Python
#          3.11...") and reports green on the unfixed tree.  §9 #11.
#      (b) matching bare '3.11' would forbid the CORRECT fix -- "It will not work
#          with Python 3.11 or earlier" must stay legal.  A criterion that goes
#          red on the right answer is worse than none.

# 3. The house-rules instruments are red-capable (PD#14, §4.3).
#    Paste FOUR outputs: red+green for each of the two assertions.
$ ./run-tests --fast tests/unit/test_house_rules.py
#    EXPECT green; and a pasted red run per §4.3, each failing for the RIGHT reason.

# 4. The hook fires, emits the ENVELOPE, and is silent when clean.
#    Input is JSON on stdin -- NOT argv (see §4.4).
#    Fixtures live in build/ (git-ignored) -- INSIDE the repo root.  §4.4 mandates
#    containment, so a /tmp fixture makes a CORRECT hook emit nothing and this
#    criterion unreachable.  §9 #9.
$ printf 'try: pass\nexcept: pass\n' > build/x.py
$ echo '{"tool_input":{"file_path":"build/x.py"}}' | .claude/hooks/ruff-check.sh
#    EXPECT: JSON on stdout whose .hookSpecificOutput.additionalContext names
#            E722, the file, and the line. Assert the SHAPE, not just presence:
$ echo '{"tool_input":{"file_path":"build/x.py"}}' | .claude/hooks/ruff-check.sh \
    | jq -e '.hookSpecificOutput.hookEventName=="PostToolUse"
             and (.hookSpecificOutput.additionalContext|test("E722"))'
#    EXPECT: true

$ echo '{"tool_input":{"file_path":"README.md"}}' | .claude/hooks/ruff-check.sh
#    EXPECT: no output, exit 0.
$ echo '{"tool_input":{}}' | .claude/hooks/ruff-check.sh
#    EXPECT: no output, exit 0.   (nil path -- §12)
$ echo '{}' | .claude/hooks/ruff-check.sh
#    EXPECT: no output, exit 0.   (no tool_input at all -- §12)

# 4b. Injection: metacharacters MUST NOT execute -- and this must test QUOTING,
#     not containment.  The fixture is INSIDE the repo, so the containment check
#     passes and the path reaches ruff; only the quoting + `--` separator stand
#     between it and execution.  A /tmp fixture would exit at containment and the
#     test would pass for the WRONG reason, leaving quoting untested forever.
$ touch 'build/pwn;touch $HOME/PWNED.py'
$ echo '{"tool_input":{"file_path":"build/pwn;touch $HOME/PWNED.py"}}' \
    | .claude/hooks/ruff-check.sh; ls ~/PWNED.py 2>&1
#    EXPECT: "No such file or directory" -- the marker was NOT created.

# 4e. The hook is actually REGISTERED (§4.4) -- a top-level "PostToolUse" key is
#     silently ignored, so the script working proves nothing about the wiring.
$ python3 -c "import json;print(list(json.load(open('.claude/settings.json'))['hooks']))"
#    EXPECT: ['UserPromptSubmit', 'PostToolUse']

# 4b-ii. Containment, tested SEPARATELY (§4.4): a path outside the repo is ignored.
$ printf 'try: pass\nexcept: pass\n' > /tmp/outside.py
$ echo '{"tool_input":{"file_path":"/tmp/outside.py"}}' | .claude/hooks/ruff-check.sh
#    EXPECT: no output, exit 0.  (A real E722 the hook MUST decline to report.)

# 4c. The Spine stays a spine, not a second standards file (DRY -- §4.6's REAL
#     observable).  NOT an affordability check: §4.6 retracts that rationale.
$ wc -c prompts/directives.md
#    EXPECT: <= 9000 bytes.
#    MEASURED SOURCE (2026-07-16), from prompts/new-feature-standards.md:
#        Posture 10 + Prime Directives 39 + Eng. Preferences 14 + quality bar 39
#        = 102 lines BEFORE PD#14 and section headers -> ~108 lines assembled.
#    HEADROOM: measured source 6387 B -> ~7.3 KB assembled, ~19% under the cap.
#    A future PD#15 may legitimately exceed 9000: RE-BASELINE the cap and say why.
#    Reflowing or trimming standards to fit a number is the instrument lying (PD#14).
#    Intent: BYTES, not lines.  A LINE cap is gameable by reflow -- rejoin the
#    paragraphs and the count drops while nothing changes; a cap satisfiable
#    without doing the thing is an instrument that lies (PD#14).  §9 #10.

# 4d. The implementer agent exists and carries the read list (§5.2a).
$ grep -c "prompts/directives.md" .claude/agents/psh-implementer.md .claude/agents/psh-reviewer.md
#    EXPECT: >= 1 for BOTH (§5.2a, and the reviewer gap).

# 4d-ii. The agents are REGISTERED, not merely present (§5.2).  #4d greps a file --
#        that is a claim.  Dispatchability is the evidence (PD#14).  .claude/agents/
#        is read at SESSION START, so this MUST be checked in a session that began
#        after the files landed:
#          dispatch a trivial task with subagent_type: "psh-implementer"
#    EXPECT: it runs.  "Agent type not found" means the session predates the files.
#    A controller that cannot dispatch psh-implementer MUST STOP -- never fall back
#    to general-purpose, which is the curation problem with no signal.

# 5. prompts/ duplication is gone.
$ python3 - <<'EOF'
from collections import defaultdict; import pathlib
files = sorted(pathlib.Path('prompts').glob('*.md'))
# Nil guard: a missing dir globs to nothing and this script would print 0 -- GREEN,
# having read no files.  That is the vacuous pass §12 forbids for §4.3, applied to
# the criterion that checks this spec's headline claim.
assert len(files) >= 5, f"read {len(files)} files -- wrong cwd? run from repo root"
idx = defaultdict(set)
for p in files:
    for line in p.read_text().splitlines():
        s = ' '.join(line.split())
        if len(s) > 40: idx[s].add(p.name)
print(sum(1 for v in idx.values() if len(v) > 1), "lines duplicated across prompts/")
EOF
#    EXPECT: 0.
#    BEFORE (recorded 2026-07-16): 55.

# 5c. The citation requirement is REAL, not asserted (§5.2b).
#      MUST NOT use `grep -qF` -- it is broken in BOTH directions here (§9 #17):
#        FALSE RED  : directives.md hard-wraps (max ~98 col); grep is line-oriented,
#                     so an HONEST quote spanning a wrap exits 1.
#        FALSE GREEN: a multi-line -F pattern matches if ANY line matches, so a
#                     clause with one real line and two INVENTED ones exits 0.
#      Normalize whitespace on both sides -- the trick #5 already uses:
$ python3 - "<clause C from the report>" <<'EOF'
import sys, pathlib
c = ' '.join(sys.argv[1].split())
t = ' '.join(pathlib.Path('prompts/directives.md').read_text().split())
sys.exit(0 if c in t else 1)
EOF
#    EXPECT: exit 0 for every quoted clause.
#    RED DEMONSTRATION (REQUIRED -- this criterion is itself an Instrument, PD#14):
#      paste a plausible-but-invented clause; it MUST exit 1.

# 5b. §7's text insertions landed (§7 had NO acceptance criteria before -- F10).
$ grep -c 'MUST cite, by number' prompts/implementation-standards.md
#    EXPECT: >= 1   (the §5.2b DoD line)
$ grep -c 'CLAUDE.md prose that existed to explain' prompts/implementation-standards.md
#    EXPECT: >= 1   (the §7.3 shrinkage DoD line)

# 6. The full suite, once, before done.
$ ./run-tests
#    EXPECT: green.

# 7. Plugins removed; kept ones intact.
$ cat ~/.claude/plugins/installed_plugins.json | python3 -c \
    "import json,sys; print(sorted(json.load(sys.stdin)['plugins']))"
#    EXPECT: feature-dev, security-guidance, code-simplifier, cloudflare ABSENT.
#            superpowers, mattpocock-skills, andrej-karpathy-skills,
#            claude-md-management, pyright-lsp PRESENT.

# 7a. §6.2's lift landed -- and this MUST pass BEFORE the cloudflare uninstall.
$ python3 -c "import json;d=json.load(open('.mcp.json'))['mcpServers'];print(sorted(d))"
#    EXPECT (EXACT set, not "includes" -- a subset means the lift clobbered a server):
#      ['chrome-devtools', 'cloudflare-api', 'cloudflare-docs', 'codegraph']
$ python3 -c "import json;print(json.load(open('.claude/settings.json'))['enabledMcpjsonServers'])"
#    EXPECT: includes cloudflare-api and cloudflare-docs
#    THEN, in a NEW session, confirm both servers RESOLVE before Gate 2 (§14).
#    Intent: §6.2 mandates lift -> verify -> uninstall.  Uninstalling first leaves
#    a window with no Cloudflare API access.  Config is a claim; resolution is the
#    evidence (PD#14).

# 7b. BOTH registries, or dangling entries remain (§6.1).
$ python3 -c "import json;print(sorted(json.load(open('.claude/settings.json'))['enabledPlugins']))"
#    EXPECT: no feature-dev, security-guidance, code-simplifier, or cloudflare entry.

# 7c. The uninstalls actually removed their surface -- verify the EFFECT, not the
#     config (PD#14: a config edit is a claim; the absent agent is the evidence).
#     In a NEW session, /context MUST show:
#       - Custom agents: feature-dev:* and code-simplifier:* ABSENT
#       - no Stop / PostToolUse hook from security-guidance
```

**Observability check (PD#5).** The ruff step in `./run-tests` MUST name the file, line, and rule on a finding — not "lint failed."

---

## 12. Shadow paths (PD#3)

Traced for each new flow.

**§4.4 — the ruff hook**

| Path | Behavior |
|---|---|
| Happy | Python file edited, findings exist → emit the `hookSpecificOutput.additionalContext` envelope, exit 0 |
| **Nil** | stdin JSON has no `tool_input`, no `file_path`, or `file_path: null` → exit 0 silently. MUST NOT error; `PostToolUse` fires on tools whose payload shape varies |
| **Nil (stdin)** | stdin is empty or not valid JSON → exit 0 silently. `jq` failure MUST NOT propagate through `set -euo pipefail` — trap it |
| **Empty** | Edited file is empty / zero-length → ruff reports nothing → silent, exit 0 |
| **Upstream error** | `ruff` or `jq` not on PATH, or ruff crashes → **exit 0 and emit one envelope line naming the failure** |
| **Hostile** | `file_path` contains shell metacharacters, or points outside the repo root → no execution, no traversal; exit 0 silently (§4.4, acceptance §11 #4b) |

> **Intent (upstream error).** The hook is advisory; `./run-tests` (§4.5) is the gate. A hook that blocked on its own breakage would halt work over a broken instrument. But failing *silently* would let the tool rot unnoticed — PD#1 and PD#14 together. So: don't block, but say so.

**§4.3 — the house-rules tests**

| Path | Behavior |
|---|---|
| Happy | Invariant holds → green |
| **Nil** | Glob matches no files (dir renamed/moved) → **MUST FAIL**, not pass vacuously |
| **Empty** | No `os.environ` matches at all → **MUST FAIL** — zero matches means the search broke, not that the invariant strengthened |
| **Upstream error** | File unreadable → error, loudly |

> **Intent.** A pass-on-zero-matches assertion is exactly the e2e-goldens-never-loaded-checks defect (§3.2): green while testing nothing. This is PD#14 applied at the moment of writing rather than after the postmortem.

---

## 13. Order of work

Prerequisites are real, not stylistic.

**Revised 2026-07-16, authorized by the user before implementation began.** The original
order put §4 first, reasoning that §11's "before" numbers are pinned to today's tree. That
reason does not hold: **§5 edits only markdown and cannot move a ruff count.** The two are
independent on that axis, and §4-first had a cost the spec never named — §5 is what creates
`psh-implementer`, so §4's subagents would have been dispatched by the very curation
mechanism §5 exists to replace. §9 #21.

```
  §3 Directives         PD#8 revised, PD#14 added.
        │               MUST land WITH §5 -- the overlays cite directives
        │               BY NUMBER, so a split leaves dangling references.
        ▼
  §5 prompts/           Spine + deltas + read list + .claude/agents/.
        │               Depends on §3 (content).  Real dependency.
        │
        │  The mechanism now EXISTS, so everything after this point is
        │  implemented THROUGH it -- dogfooded on real work before
        │  anything depends on it.
        ▼
  §4 Mechanize          ruff, requires-python, README, house rules, hook,
  (dispatched via       run-tests.  §11's before-numbers (17 ruff findings,
   psh-implementer)     55 dup lines) remain valid: §3/§5 touch no Python,
        │               and §5's own effect on the dup count is what §11 #5
        │               measures.
        ▼
  §7 Process            §7.3's DoD cites §5's Spine and §3's PD#14 by
        │               name.  Must follow both.
        ▼
  §6 Tools              LAST, and deliberately so: §6.2 (lift the MCP
                        servers) MUST complete and be verified BEFORE the
                        cloudflare uninstall, and no plugin removal should
                        confound a test result from §4.  Gate 2 (§14)
                        applies here.
```

---

## 14. Human approval gates

> ### STOP — Gate 1
> Implementation MUST NOT begin until the user has reviewed this spec and replied with the exact phrase:
> **`SPEC APPROVED — BEGIN IMPLEMENTATION`**

> ### STOP — Gate 2
> Plugin uninstalls (§6.1) MUST NOT be executed until the user replies with the exact phrase:
> **`UNINSTALL APPROVED`**
>
> **Intent.** Uninstalls alter the user's environment outside this repo and are not revertible by `git`. `feature-dev`, `security-guidance`, and `code-simplifier` were each chosen individually and the user MUST re-confirm at execution time.

---

## 15. Closing audit questions — queued for AFTER implementation

Per the quality bar. Not to be answered now.

1. Did the Spine's line count actually let §5.2's full read stay affordable in practice, or did briefs start truncating it?
2. After Increment 1 of the Campaign: did `CLAUDE.md` actually shrink (§7.3), or did the exemption predicate absorb everything?
3. Did the ruff hook (§4.4) ever catch something `./run-tests` would have missed — or is it pure latency?
4. Did any subagent still ignore a standard after §5.2? If so, the read list is not the whole cause and §1b needs re-diagnosis.
5. Is PD#14 being applied to *new* instruments, or only recited about the known ones?
6. Was removing `security-guidance` felt at all — did `/security-review` + PD#6 + ruff `S105/S106` cover it?
7. Was uninstalling `cloudflare` (§6.1) felt? Did the two lifted MCP servers (§6.2) cover `plugin/cloudflare/` and `check/cloudflare/` work, or was a skill missed?
8. **§4 was implemented inline, not through `psh-implementer`** — the agents could not register mid-session (§9 #22), and re-running the phase through them was judged not worth a session restart. So the mechanism shipped **un-dogfooded**: its first real use will be increment 1 of the Campaign. Watch that closely; §15 Q4 is the check.
9. **§1c is only partially addressed** (§7.2 covers the Campaign; nothing covers the general case). Once the Campaign has produced LIGHT-eligible work in volume, does a tier model earn its place — or did thin increment specs (§7.2) already absorb the pain?

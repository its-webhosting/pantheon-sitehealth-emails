# SPEC — I14d: closing the modularization campaign

**Increment:** I14d (Wave 4, fourth and last). **Date:** 2026-07-24.
**Governing documents** (read in full before implementing; this spec cites them by section
and re-derives nothing): `development/2026-07-17-modularization-campaign/CAMPAIGN.md`
(frozen architecture), `LEDGER.md` (through the I14c entry), `/workspace/CLAUDE.md`,
`/workspace/prompts/directives.md` (the Spine; PD#n citations are to it).

**CAMPAIGN.md §11 row I14d, verbatim:** "Closing: config migration doc (decision 2026-07-23:
**no renames** — the schema is already in final shape, the doc records that with its audit
trail) + sample-toml refresh + production-config instructions; docs/README/CLAUDE.md full
refresh; ledger fully resolved; retrospective + closing audit (§17)."

This is the increment that makes the repository's documentation true. Every other increment
was judged against code; this one is judged against **claims** — which is why §2.1's
instrument exists before §2.2's rewrite, and why the acceptance in §8 is a claim table, not
a test count.

## Glossary (this spec only; domain terms live in `CONTEXT.md`)

- **Claim** — a checkable factual assertion in a repository document: a file path, a symbol's
  module home, a test file or node id, an `sc.<name>`, a count, or a stated behavior.
- **Mechanizable claim** — a claim `tools/claim_check.py` (§2.1) can decide by executing
  something: path existence, symbol resolution, pytest collection, attribute presence,
  recomputed count. Everything else is a **prose claim**, dispositioned by review (§2.1).
- **Archaeology** — increment-numbered narrative in a living document ("moved in I6", "at
  I5–I12 they were interim", "since I13"). Its permanent home is `LEDGER.md`.
- **Load-bearing warning** — a documented fact whose loss would let a known bug return. The
  exhaustive inventory is §2.2's Keep list; each entry names the bug it prevents.
- **Recorded deviation** — a §17 answer of "no, and here is the measurement and the reason",
  as distinct from amending the target so the answer becomes yes (D-i14d-1).

MUST / NEVER / SHOULD / MAY per CAMPAIGN.md §Glossary.

## 0. The two flows this increment changes (PD#8)

Documentation truth, before → after. `*` marks what I14d changes:

```
  BEFORE                                       AFTER
  CLAUDE.md: architecture + campaign           CLAUDE.md: architecture as it IS      *
  archaeology interleaved (99 lines               (no I<n> narrative; every
  carry an I<n> reference; 28 name                 load-bearing warning kept
  psh/_legacy.py, deleted at I14a)                 with its REASON)
        │                                                  ▲
        │  reader must date-sort prose                     │ written FROM the
        │  to learn today's truth                          │ verified inventory   *
        ▼                                                  │
  LEDGER.md (history, permanent) ───────────────────► LEDGER.md (unchanged role:
                                                       the one home for history)

  verification path (new):                             *
        every claim in the document
              │
      ┌───────┴────────┐
      ▼                ▼
  mechanizable      prose claim
      │                │
  tools/claim_check.py  psh-reviewer, fresh context, reads the code
   (--self-test proves   │
    it can go red)       │
      └───────┬──────────┘
              ▼
      CLAIMS.md — disposition per claim: keep-verified | fix | drop-with-reason
              │
              ▼   the rewrite is written from this table, not from the old file
```

Notice-code registration, before → after (§2.5 finding 2):

```
  BEFORE                                       AFTER
  producer: NOTICE_X = registry.register("x")  same producer code, unchanged
  producer: Notice(code=NOTICE_X, …)                        │
                                                            ▼
  a producer writing Notice(code="whatever")   tests/integration/test_notice_registration.py *
  registers nothing, enters no registry,        walks the AST of psh/ + check/ + plugin/:
  and passes EVERY test today —                 every Notice(...)/sc.Notice(...) must pass
  including test_notice_roster.py, which        code=<a module-level NOTICE_* constant>, and
  compares the registry against the roster      every NOTICE_* must be a registry.register()
  and so cannot see a code that never           result.  A literal code is a NAMED failure.
  reached it.                                              │
                                                            ▼
                                              CLAUDE.md's "registry-enforced" becomes true
```

## 1. Scope

### 1.1 In scope (exhaustive)

| # | Deliverable | Where |
|---|---|---|
| A | Claim inventory: `tools/claim_check.py` + the committed `CLAIMS.md` disposition table | this increment's folder |
| B | CLAUDE.md rewritten as a final-state document | `/workspace/CLAUDE.md` |
| C | README, `docs/`, `prompts/`, `tests/README.md`, `CONTEXT.md`, auto-memory refreshed | those files |
| D | `docs/config-migration.md` (no renames, with audit trail) + `sample-pantheon-sitehealth-emails.toml` verified + the production-config instruction | `docs/`, repo root |
| E | The seven findings LEDGER I14c ledgered to I14d, incl. the permanent registration test | `psh/notice.py`, `tests/`, 19 comment blocks |
| F | Ledger fully resolved + `CLOSING-AUDIT.md` (§17, nine answers) + `RETROSPECTIVE.md` + the I14d ledger entry | campaign folder |

### 1.2 NOT in scope (reasoning preserved so it is not re-litigated)

- **Further `main()` extraction.** `main()` is `psh/cli.py:369–990` = **622 raw / 445 logic**
  lines against §3.3's 250–400 target. §17 Q1 is answered as a **recorded deviation** with the
  measurement, and further extraction becomes a post-campaign README TODO (D-i14d-1). Extracting
  now would re-open implementation, and golden risk, in the increment specced as closing.
- **Config key renames.** None are required, and that is a verified finding, not a survey
  (§2.4). Amending the schema at close would invalidate the migration doc it is meant to justify.
- **A docs path-guard test** (a test asserting every path named in a document exists). Declined
  2026-07-24: it catches only *deleted paths*, while every stale claim this campaign actually
  shipped — the two-config ruff description, the wrong `sc.registry` sentence, the false
  "`ALL_PACKAGES` loads every package" claim (false I8→I10) — was prose about a file that still
  existed. It also needs an allowlist for illustrative paths (`build/{site}.eml`,
  `check/<name>/`, a doc written later in the same change), which is the kind of list that rots.
  Recorded in README with this reasoning (D-i14d-7).
- **Promoting `literal_equality.py`** (I14c's Invariant-8 instrument) to a permanent test. It
  compares a file against a git baseline commit, so it would need a moving reference point and
  would go red on every legitimate notice-copy edit; its guarantee is already held permanently
  by the four e2e goldens plus the 107 `.ambr` snapshots. It stays a committed increment
  artifact; the ledger records this and its disclosed blind spot (D-i14d-6).
- **Deleting dead `sc` façade names.** §17 Q4's scan reports them; deletion is a reviewed
  post-campaign change, because CAMPAIGN.md §3.5/Invariant 9 forbids removing an `sc` name and
  standalone check-module tests monkeypatch that surface (D-i14d-10).
- **Golden or recorded-fixture refresh** — Invariants 1 and 10.
- **The four existing post-campaign README TODOs** (ruff upgrade + PLR0917 disposition; typed
  `sc` stubs + pyright widening; repointing tests off the `psh.<name>` re-export surface; the
  `mutates` hook declaration). I14d adds items to that list; it does not execute them.

## 2. Design

### 2.1 Deliverable A — the claim inventory and its instrument

**Why an instrument.** CAMPAIGN.md §7 obligation 4 requires every claim a document moves or
writes to be *verified, not assumed*. I14c found **three** of its own instruments printing
verdicts they had not checked (PD#14). A subagent reporting "verified" is the same failure
mode with no artifact. So: mechanize what can be mechanized, disposition the rest by review,
and commit the table either way.

`development/2026-07-24-mod-I14d-closing/tools/claim_check.py` — a single-file, dependency-free
script run from the repo root. It extracts candidate claims from a document and decides each:

| Claim kind | Extraction | Decision |
|---|---|---|
| Repo path | backticked token matching a path shape | `Path(tok).exists()` |
| Symbol home ("`X` lives in `psh/y.py`") | backticked `name` adjacent to a backticked `.py` path | `ast` parse of that file defines `name` at module level |
| Test file / node id | backticked `tests/**` path, optionally `::node` | file exists; node collects under `pytest --collect-only` |
| `sc.<name>` | `sc.` prefixed token | present in `tests/unit/test_house_rules.py`'s documented-façade list AND on the loaded `script_context` |
| Count | a number adjacent to a countable noun this tool knows (roster codes, `PHASES`, check packages, `psh/` modules, `main()` lines) | recomputed from the tree |

Everything else is emitted as `PROSE` — **not** silently passed. `--self-test` MUST prove the
tool can go red: it runs each decision kind against a deliberately false claim and asserts a
failure verdict, after a control run on the true form (the `literal_equality.py --self-test`
precedent). A `--gate` mode exits non-zero on any `FAIL`.

Output: `CLAIMS.md` in this increment's folder, one row per claim — `claim | kind | verdict |
disposition`, where disposition ∈ {`keep-verified`, `fix`, `drop-with-reason`}. The `PROSE`
rows are dispositioned by a fresh-context `psh-reviewer` reading the code, whose findings are
folded into the same table. **The rewrite in §2.2 is written from this table**, so a
load-bearing warning can only leave the document by an explicit `drop-with-reason` row.

### 2.2 Deliverable B — the CLAUDE.md rewrite

Final-state document: it describes the architecture **as it is**, and history lives in
`LEDGER.md`. Measured starting point: **1,239 lines / 12,654 words**, of which **99 lines**
carry an increment reference and **28** name `psh/_legacy.py`, deleted at I14a.

**Rules (exhaustive).**

1. NEVER state a fact by its provenance. "`psh/gather.py` holds the framework gather cores" —
   not "new in I9, Drupal half added in I10". A campaign reference survives only where a reader
   *acting on the file today* needs it (the `development/` archive pointer, the ledger pointer).
2. Every load-bearing warning keeps its **reason** — the bug it prevents — because the reason
   is what makes a reader obey it. The Keep list below is exhaustive; each entry MUST appear in
   the rewrite.
3. Every retained claim traces to a `keep-verified` row in `CLAIMS.md`.
4. Terminology per PD#11: one term per concept, matching `CONTEXT.md`.
5. Target ~600–750 lines. This is a *consequence* of rules 1–3, never a goal to hit by cutting
   a warning — if the verified content lands outside the range, the range yields.

**Keep list (exhaustive — every one is a shipped bug this repo has already paid for).**

| # | Warning | Bug it prevents |
|---|---|---|
| 1 | `pantheon-sitehealth-emails.py` is a committed symlink; do not delete | ruff/pyright/CodeGraph blindness to the extension-less shim (§17 Q5, answered KEEP at I14a) |
| 2 | Column-0 `f"""` notice literals move verbatim; `git diff -w` is not evidence | leading whitespace in rendered email, invisible to `-w` (Invariant 8) |
| 3 | `sc.console`: escape untrusted text; `soft_wrap=True` on copy-pasteable commands; tests reproduce width 80 | deleted `[parameters: …]`/`[notice]` fragments; the wrapped resume command that **re-mailed every owner** |
| 4 | DB: read-release commit in the loaders; `db_retryable` predicate; whole-unit retry only; counters count *healed*, not attempted | MySQL 2013 on the reaped idle connection; partial write sets; the "1 reconnect" on a run that reconnected zero times |
| 5 | `-results.json` is site-keyed and nothing else | metadata keys becoming phantom site rows in `monthly-report.txt` |
| 6 | Two-binding seams: `psh.gateway.run_terminus` **and** `psh.gather.run_terminus`; `psh.mail.SMTP_SSL`; `psh.lifecycle.finish_run`; `psh.dns_classify.resolve`; `httpseam.fetch`/`sleep`; `egress.probe` | a mock that looks installed but isn't — real Terminus subprocess calls from a "mocked" test |
| 7 | Exactly ONE `sitecustomize.py`, in `tests/shims/pyshim/` | a second one means one silently never runs; `not in` assertions pass against a run that did nothing |
| 8 | `conftest._CWD_ASSETS` must include `check` and `plugin` | every e2e golden ran with every check disabled |
| 9 | `html_to_text()` builds a fresh `HTML2Text` per call | first notice of a run rendering in a different link style |
| 10 | Register the shorter substitution pattern before the longer one | best-match mis-binding → `KeyError` |
| 11 | `find_modules()` walks for **non-empty** `__init__.py`, CWD-relative | silently loading nothing |
| 12 | `run_program()` safety interlock: `--all`/`--for-real`/live `--create-tables` refused | Invariant 7 |
| 13 | Goldens are never refreshed to green; `terminus-cdnchange/` fixtures are hand-maintained | Invariants 1, 10 |
| 14 | `cloudflare_enabled` is read from config, never from `"plugin.cloudflare" in sc.plugin` | always-true test |
| 15 | `reset_sc` snapshots/restores the notice registry; **no producing module may be executed outside a function-scoped fixture or test body, nor cached across tests** | `DuplicateNoticeCodeError` on the second load; §2.5 finding 6 broadens the wording |
| 16 | `Notice`/`csv_extra` rules: elements MUST already be strings; the site name comes from the `SiteContext` | the anonymous `sequence item N: expected str` from `",".join`; a producer/site mismatch |
| 17 | `gate_disabled_sections()` runs **before** substitution; the DEFER two-pass order | a disabled feature's secrets being required to exist |
| 18 | Hook DAG: the five fatal conditions; dotted events MUST declare empty `consumes`/`produces` | silent overwrite of a contract key (PD#1) |
| 19 | The still-hardcoded-U-M inventory, and that the non-U-M golden does **not** assert "no umich.edu anywhere" | new leakage shipping green |
| 20 | Terminus does not work with PHP 8.4 | a dead toolchain |
| 21 | The B57 send block stays in `main()`: accumulator writes sit between `send_message()` and `quit()` | the Ctrl-C-during-`quit()` duplicate-email window |
| 22 | A site's notices are appended to the run accumulator **before** the SMTP send | notices never reaching `-notices.csv` for an emailed site |

The **Modularization campaign (in progress)** section is replaced by a short "how this
architecture came to be" pointer to `development/2026-07-17-modularization-campaign/`
(CAMPAIGN.md frozen, LEDGER.md history, CLOSING-AUDIT.md, RETROSPECTIVE.md), stating the
campaign is complete.

### 2.3 Deliverable C — README, docs/, prompts/, CONTEXT.md, memory

Measured stale surface (this is the *known* set; `claim_check.py` runs over each file and may
add rows — the list is therefore **illustrative of the class, exhaustive of what is measured
today**):

| File | Stale claim | Action |
|---|---|---|
| `README.md:275` | present-tense `ruff-broad.toml` two-config prose | rewrite to the merged single-pass gate (I14b) |
| `README.md:281` | pyright scope "`psh/` minus `_legacy.py`" | pyright gates all of `psh/` (I14a) |
| `README.md` TO DO head | "Modularization campaign in progress" | campaign complete; point to CLOSING-AUDIT + RETROSPECTIVE |
| `README.md` TO DO | — | ADD: further `main()` extraction (D-i14d-1); the useless `uvx pyright@1.1.411` fallback (LEDGER I14c); the declined docs path-guard with its reasoning (D-i14d-7) |
| `tests/README.md` | verify tiers/seams/interlock against the tree | fix what `claim_check.py` fails |
| `CONTEXT.md` | verify the glossary against final module names | fix what `claim_check.py` fails |
| memory: `MEMORY.md`, `modularization-campaign.md`, `gateway-extraction.md`, `config-and-notice-modules.md`, `codegraph-blind-to-main-script.md`, `hook-phase-ordering-invariant.md`, `db-idle-connection-reaped.md`, `dns-modularization.md`, `pantheon-cdn-change-check.md` | 9 files name `psh/_legacy.py`, `ruff-broad.toml`, or a top-level `dns_classify.py` | update to final state (PD#13, §7 obligation 7) |

**Verified NOT stale** (checked 2026-07-24, so the rewrite does not "fix" them into being
wrong): `docs/pantheon-cdn-change.md:174`, `prompts/directives.md:114` and
`prompts/debugging-standards.md:34` already say `psh.dns_classify`; `docs/awscli-login.md:19`'s
`cli_legacy_plugin_path` is an AWS CLI setting, not this repo's `_legacy`.

### 2.4 Deliverable D — configuration

`docs/config-migration.md` states, as its headline, that **no key changes are required**, and
carries the audit trail that makes that a finding rather than a hope:

1. The section inventory of the live production config versus every reader in code.
2. Why each campaign-introduced key needed no rename: CAMPAIGN.md §5 required new keys to land
   in final shape as introduced (I3 onward), so there is no interim shape to migrate from.
3. **What an operator MAY now add** (all optional, all defaulting to today's behavior):
   `[Check.pantheon]`, `[Check.wordpress]`, `[Check.drupal]`, `[Check.addon_updates]` — each
   `enabled` defaulting **true**; `[Email]` — defaulting to the U-M literals.
4. The production-config instruction: **no edits required**, with the check that produced it.
   That is §17 Q7's answer.

Measured baseline for (1): production carries `[Pantheon]`, `[Pantheon.plan_info*]`,
`[Pantheon.plan_sku_to_name]`, `[Database]`, `[Cloudflare]`, `[Cloudflare.cachecheck]`,
`[SMTP]`, `[AWS]`, `[UMich]`, `[UMich.portal]`, `[UMich.portal.db]`, `[News]` — no `[Check.*]`
and no `[Email]`, both of which default correctly.

`sample-pantheon-sitehealth-emails.toml` is verified key-by-key against the code that reads
each key; comments are corrected where the campaign changed behavior. Per the Spine's bar, any
snippet quoted in the migration doc is shown **merged with what the file already contains**,
never as a fragment to paste over the real thing.

### 2.5 Deliverable E — the seven findings LEDGER I14c ledgered here

| # | Finding | Fix | Seam / test |
|---|---|---|---|
| 1 | `Notice.__post_init__` validates `csv_extra` element types but not `severity`; `severity="warn"` surfaces as an anonymous `KeyError: 'warn'` from the projection | strict `isinstance(self.severity, Severity)` check raising a **named** `TypeError` — validate, never coerce, matching the `csv_extra` posture (D-i14d-9) | `psh.notice.Notice` constructor; `tests/unit/test_notice.py`. Red first: today `Notice(severity="warning", …)` constructs fine |
| 2 | Nothing requires a `Notice.code` to be **registered**; `code="whatever"` passes every test, and the roster test cannot see a code that never entered the registry | new permanent `tests/integration/test_notice_registration.py` (AST over `psh/`, `check/`, `plugin/`) — every `Notice(...)`/`sc.Notice(...)` passes `code=` a module-level `NOTICE_*` constant, and every `NOTICE_*` is a `registry.register(...)` result (D-i14d-3) | source AST, no runtime seam. Red first: a temporary producer with a literal code, and a temporary `NOTICE_X = "x"` that never registers |
| 3 | The registration comment block is **19** near-identical copies (LEDGER I14c says 17; measured 2026-07-24 at spec time: **19 files carry it**, and `psh/cli.py` registers `no-domains` with **no** block — correction recorded here and in the I14d ledger entry, per §7 obligation 4) with two visible drifts (a sentence in two modules but not the other single-code ones; every `check/` copy ending "added at I14c Task 6" on files whose block landed at Task 3/4/5) | collapse to one short line per module + the rationale in CLAUDE.md (which now carries it); `psh/cli.py` gains the same one-liner so the 20 registering files read alike | no test; `claim_check.py` re-run over CLAUDE.md |
| 4 | CLAUDE.md's "every producing module registers … through `NOTICE_* = sc.registry.register(...)`" is wrong for five modules — the four in `psh/`, which cannot use the façade, plus the `check/pantheon_cdn_change/notices.py` exception | fixed in the §2.2 rewrite, stated as: `psh/` uses `registry` directly, `check/`/`plugin/` use `sc.registry`, with the one sanctioned direct importer named | `CLAIMS.md` row |
| 5 | Three stale test comments describing a fill `add_notice` no longer performs, and one section banner naming `multisite-check` as a notice code when it is the `operation` argument — the exact collision D-i14c-8 renamed the parameter to prevent | correct in place. Known: `tests/integration/test_check_pantheon_cdn_change.py:57` ("add_notice fills the magnifying glass") and `tests/integration/test_drupal_notice_render.py:63` (the banner). The implementer MUST locate the remainder by searching test comments for `add_notice` fills and for notice-code names used as `operation` values, and report the count found | comments only; suite must stay green |
| 6 | `tests/unit/test_cachecheck_consolidation.py`'s `_CACHED` executes a producing module once per **session** while satisfying the §2.3 invariant literally | **drop `_CACHED`** (D-i14d-11): the file has 33 tests and the module is small and pure, so per-test loading is trivial; the invariant is simultaneously restated in CLAUDE.md as "and never cached across tests" (Keep-list #15) | existing 33 tests stay green |
| 7 | `Severity(level)`'s named `ValueError` has no test; I14c SPEC §5(1)'s "exhaustive" list over-included two files; `literal_equality.py`'s disclosed blind spot is narrower than the truth | add the test at `psh.gather.check_drupal_module` (`level="bogus"` → `ValueError`); correct both I14c SPEC statements **in place with the correction recorded** per `prompts/adversarial-review.md`, never silently | `tests/integration/test_gather_drupal.py` (or the module's existing test home). Red demo: temporarily restore a plain string severity, showing the test passes without the conversion |

### 2.6 Deliverable F — ledger resolution, closing audit, retrospective

**Ledger resolution.** Every "Discovered tasks" and "Open questions" item in `LEDGER.md`
entries I0…I14c is walked and given one of three terminal dispositions — `done` (with the
commit or artifact), `README TODO` (with the item's text), `declined` (with the reason). The
table lands in the I14d ledger entry. §17 Q6 is answered *from* that table, not asserted
beside it.

**Closing audit** — `development/2026-07-17-modularization-campaign/CLOSING-AUDIT.md`, one
section per §17 question, each with the command run and its output pasted:

| Q | Expected answer shape |
|---|---|
| 1 | **Recorded deviation**: 622 raw / 445 logic vs. 250–400, plus a stay-list check that everything left matches §3.3, plus the post-campaign TODO (D-i14d-1) |
| 2 | Each DAG fatal condition shown red at least once — cite the test that demonstrates it |
| 3 | Registry ↔ CLAUDE.md table agreement, test-enforced — cite `tests/unit/test_contract_registry.py` |
| 4 | Two halves: `NoticeRegistry` is load-bearing (I14c, and §2.5 finding 2 strengthens it); plus a dead-`sc`-name scan, **reported not deleted** (D-i14d-10) |
| 5 | Symlink KEPT (answered at I14a); the rewritten CLAUDE.md records what it buys |
| 6 | The §2.6 resolution table |
| 7 | **No edits required** (§2.4) |
| 8 | `claim_check.py --gate` green over README, CLAUDE.md, `docs/`, `tests/README.md`, `CONTEXT.md`, memory |
| 9 | The amendment list: Wave-4 split, B51 early deletion, §6 `csv_extra`, §3.5 exception — each with its ledger entry |

**Retrospective** — `RETROSPECTIVE.md` in the campaign folder: the §1 goal against the
measured outcome, and the failure classes worth carrying forward (each already ledgered, here
generalized): instruments printing unchecked verdicts (three in I14c alone); `ALL_PACKAGES`
drift blinding the DAG test I8→I10; the second ruff config silently linting at py310 for the
whole campaign; the two-binding seam trap; silently-failed subagent report writes.

### 2.7 Decisions (D-i14d-1…11, exhaustive)

1. **D-i14d-1** — §17 Q1 answered as a recorded deviation + post-campaign README TODO; no
   further `main()` extraction here. Extraction at close re-opens golden risk for a target that
   was estimated before §3.3's stay-list was measured.
2. **D-i14d-2** — all seven I14c-ledgered findings land in I14d; §17 Q6's "ledger fully
   resolved" is only true if they do.
3. **D-i14d-3** — code registration is enforced by a permanent AST test, **not** by
   `Notice.__post_init__` (which would couple the frozen type to a module-level singleton and
   break five legitimate test fakes: `code="x"`, `code="c"`, `code=f"c-{severity}"`), and not by
   merely restating the doc.
4. **D-i14d-4** — CLAUDE.md is rewritten to final state; history stays in `LEDGER.md`.
5. **D-i14d-5** — one increment, with §11 split-never-compress as the backstop: if it runs long,
   nothing partial is committed, the split is ledgered, and the remainder becomes **I14e**.
6. **D-i14d-6** — `literal_equality.py` stays an archive artifact (reasoning + blind spot in the
   ledger); `notice_inventory.py`'s registration guarantee is what earns permanence, as §2.5
   finding 2.
7. **D-i14d-7** — the docs path-guard test is declined, with the reasoning recorded in README.
8. **D-i14d-8** — claim verification is hybrid: instrument for mechanizable claims, fresh-context
   `psh-reviewer` for prose, one committed table.
9. **D-i14d-9** — `severity` validation is strict `isinstance`, not coercion, matching
   `csv_extra`. A producer passing the string `"warning"` is a defect to name, not to fix
   silently. **Precondition, MUST be measured before implementing:** every current producer and
   test fake passes a `Severity` member; if any passes a bare string, that call site is corrected
   in the same task and reported.
10. **D-i14d-10** — dead `sc` names are reported by the Q4 scan, never deleted here.
11. **D-i14d-11** — `_CACHED` is dropped rather than the invariant merely restated; the
    restatement happens too (Keep-list #15), because the invariant as written is necessary but
    not sufficient.

## 3. Behavior bar (CAMPAIGN.md §8, applied)

| Surface | I14d effect |
|---|---|
| Rendered emails (4 goldens) | **NEVER change.** Nothing in this increment touches a notice body, template, or chart |
| `-results.json` / `-notices.csv` / `-run.json` | unchanged |
| Notice csv values | unchanged — no producer's `code`, `csv_extra`, or severity is edited |
| `.ambr` snapshots (107) | unchanged — byte-identical, asserted at close |
| stdout / console | unchanged (no new print sites) |
| Config: existing keys | unchanged — §2.4 is documentation of the existing schema |
| Exit codes, resume semantics, artifact gates | unchanged |

The only production-code edit in the whole increment is finding 1's validation in
`psh/notice.py`. Everything else is documents, comments, and tests.

## 4. Seams under test (the Spine's seam bar)

No new seam is invented. Each new test attaches to an existing one:

| Behavior | Seam | Why this one |
|---|---|---|
| `severity` validation | the `psh.notice.Notice` constructor | highest seam that reaches the behavior; already the home of `tests/unit/test_notice.py`'s `csv_extra` sibling test |
| Code registration | the **source AST** of `psh/`, `check/`, `plugin/` | the property is static — no runtime path can observe an unregistered code, which is exactly the defect |
| `Severity(level)` `ValueError` | `psh.gather.check_drupal_module` | the producer that performs the conversion; testing `Severity("bogus")` alone would pin `enum`, not this code |
| Claim verification | `tools/claim_check.py` + its `--self-test` | PD#14: the instrument must be shown able to go red |

## 5. Test plan

**Red-first, per `mattpocock-skills:tdd`** (`prompts/implementation-standards.md` overrides
`superpowers:test-driven-development`):

1. `tests/unit/test_notice.py::test_severity_must_be_a_severity_member` — red today (a bare
   string constructs fine), green after finding 1.
2. `tests/integration/test_notice_registration.py` — three tests: (a) every construction uses a
   `NOTICE_*` constant; (b) every `NOTICE_*` is a `register()` result; (c) the registry roster is
   still exactly the pinned 36. Red demonstrated by a temporary literal-code producer **and** a
   temporary non-registering constant, each reverted after the demonstration is recorded.
3. `Severity(level)` `ValueError` test — a pin; red demonstrated by temporarily reverting the
   conversion to a plain string, verified, reverted.
4. `_CACHED` removal — the 33 existing tests in that file are the cover; they must stay green
   with no other edit.
5. `claim_check.py --self-test` — the instrument's own red demonstration, output pasted in the
   task report.

**No golden or snapshot may be refreshed.** An existing golden going red is a defect in this
increment (Invariant 1, PD#14).

Baseline to preserve: **1055 passed / 1 skipped, 107 snapshots** (I14c close, live tier
included). Expected at I14d close: 1055 + 5 new tests = **1060 passed / 1 skipped**, 107
snapshots. A different number MUST be explained in the ledger entry, not absorbed.

## 6. Task plan (per-task commits, each green)

| T | Task | Done when |
|---|---|---|
| 1 | `tools/claim_check.py` + `--self-test` + the `CLAIMS.md` inventory over CLAUDE.md, README, `docs/`, `tests/README.md`, `CONTEXT.md`, memory; prose rows dispositioned by a fresh-context `psh-reviewer` | `CLAIMS.md` committed; `--self-test` output pasted in the task report |
| 2 | CLAUDE.md rewritten from `CLAIMS.md` per §2.2, Keep list intact | `claim_check.py --gate CLAUDE.md` green; every Keep-list row locatable in the new file |
| 3 | README, `docs/`, `prompts/`, `tests/README.md`, `CONTEXT.md`, memory refreshed (§2.3) | `--gate` green over all of them |
| 4 | `docs/config-migration.md`, sample-toml verification, production instruction (§2.4) | every sample key traced to its reader; §17 Q7 answerable |
| 5 | The seven findings (§2.5), test-first | suite green at the new baseline; goldens + 107 snapshots byte-identical |
| 6 | Ledger resolution table, `CLOSING-AUDIT.md`, `RETROSPECTIVE.md`, the I14d ledger entry | all nine §17 answers carry pasted evidence |

Task order is fixed: T1 produces the table T2 and T3 are written from. T5 is independent of
T1–T4 and MAY move earlier if it unblocks anything. T6 MUST be last — it reports on the rest.

## 7. Obligations discharged / created

**Discharged by this increment:** CAMPAIGN.md §11 row I14d in full; §17 all nine questions;
LEDGER I14c's seven ledgered findings and its two open questions (Q4 answerability; the
instruments' disposition); LEDGER I14b's "README's `ruff-broad.toml` prose + CLAUDE.md's
two-pass references → I14d's wholesale refresh"; LEDGER I14a's "CLAUDE.md retains ~22 stale
`psh/_legacy.py` narrative mentions" (measured today: **28**).

**Created (all post-campaign README TODOs, none executed here):** further `main()` extraction
toward §3.3's target; the useless `uvx pyright@1.1.411` fallback; the declined docs path-guard
with its reasoning; any dead `sc` name the Q4 scan reports.

**Campaign closure:** after T6, CAMPAIGN.md gains a status line marking the campaign complete
with the closing commit; the document itself stays frozen (amendments only, per its preamble).

## 8. Acceptance (commands + output pasted here at close, never summarized)

Run before submitting — an unrun acceptance suite is PD#14 exactly. **Increment base** = the
commit this spec is committed at; its sha is recorded in the I14d ledger entry and substituted
for `$BASE` below.

```bash
./run-tests                       # full suite incl. live tier if credentials are present
git diff $BASE -- tests/e2e/__snapshots__/     # MUST be empty
git diff $BASE -- '*.ambr'                     # MUST be empty
python development/2026-07-24-mod-I14d-closing/tools/claim_check.py --self-test
python development/2026-07-24-mod-I14d-closing/tools/claim_check.py --gate \
    CLAUDE.md README.md CONTEXT.md tests/README.md docs/*.md \
    ~/.claude/projects/-workspace/memory/*.md
git status --porcelain            # MUST be clean at close
```

The memory files live outside the repository; `claim_check.py` therefore resolves every
repo-relative claim against the repo root regardless of where the containing document sits.

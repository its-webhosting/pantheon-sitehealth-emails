# I3 — Configuration module + `Notice` class (`psh/configuration.py`, `psh/notice.py`)

**Increment I3 of the modularization campaign.** Governing documents (read in full before
implementing, CAMPAIGN.md §7 obligation 1): `../2026-07-17-modularization-campaign/CAMPAIGN.md`,
`../2026-07-17-modularization-campaign/LEDGER.md`,
`../2026-07-17-modularization-campaign/BLOCKMAP.md`, `/workspace/CLAUDE.md`. This spec cites
CAMPAIGN.md by section number and re-derives nothing from it.

## Glossary (this increment)

- **Configuration module** — `psh/configuration.py`, the new module receiving the config-
  substitution / section-gating / news-loading / feature-flag functions (CAMPAIGN.md §3.1
  `psh/configuration.py` row).
- **DEFER machinery** — the module-level `_DEFER_TAG` NUL sentinel and the two compiled regexes
  (`config_substitution_re`, `config_substitution_deferred_re`) that implement the two-pass
  substitution (CLAUDE.md § "Config substitutions"). Moves with `config_substitution`/
  `process_config`.
- **`Notice`** — the frozen dataclass introduced here (CAMPAIGN.md §6), the typed replacement for
  the ad-hoc notice dict. Lives in the new **`psh/notice.py`** (§Notice module home).
- **`Severity`** — the `StrEnum` (`alert`/`warning`/`info`) that types `Notice.severity`
  (CAMPAIGN.md §6).
- **Notice-code registry** — the `NoticeRegistry` mechanism that rejects a re-used notice code with
  the named `DuplicateNoticeCodeError` (CAMPAIGN.md §6 "code (unique — registry test)").
- **PoC notice** — the one existing notice this increment converts to `Notice` end-to-end to prove
  the producer→render path stays golden-identical: **`no-domains`** (§PoC).
- **Remnant** — `psh/_legacy.py`, whatever of the original program has not yet moved.
- **Façade** — `script_context.py` (`sc`), the stable import surface for `check/`/`plugin/`
  packages (CAMPAIGN.md §3.5).

MUST / NEVER / SHOULD / MAY per CAMPAIGN.md §Glossary.

## Scope (exhaustive)

I3 has **two deliverables**. Nothing else changes.

### Deliverable A — `psh/configuration.py` (the config-machinery move)

Move exactly these six module-level defs plus the DEFER machinery from `psh/_legacy.py` to a new
`psh/configuration.py` (CAMPAIGN.md §3.1 `psh/configuration.py` row is authoritative; the
"792–934, 1209–1253, 1608–1648" spans in §11 row I3 are the pre-campaign baseline regions):

| Item | Current `_legacy` line | Notes |
|---|---|---|
| `config_substitution` | 516 | best-match substitution scorer; self-contained |
| `_DEFER_TAG` + the two regexes | 603–608 | DEFER machinery; used only by the two funcs below |
| `process_config` | 611 | two-pass driver; calls `config_substitution` |
| `gate_disabled_sections` | 637 | recursive `enabled = false` pruning |
| `load_news_items` | 933 | `[News]` inline + folder loading |
| `umich_enabled` | 1332 | `[UMich].enabled` feature flag (exposed as `sc.umich_enabled`) |
| `cloudflare_enabled` | 1347 | `[Cloudflare].enabled` feature flag (exposed as `sc.cloudflare_enabled`) |

### Deliverable B — `psh/notice.py` + the `no-domains` PoC (CAMPAIGN.md §6, §11 row I3)

- New `psh/notice.py`: `Severity` (StrEnum), `Notice` (frozen dataclass), `NoticeRegistry`,
  `DuplicateNoticeCodeError`, and a module-level default `registry` instance.
- `SiteContext.add_notice` (in `script_context.py`) accepts a `Notice` **or** a legacy dict
  (CAMPAIGN.md §6: "SiteContext.add_notice accepts Notice or legacy dict; dict form retired in I14").
- Re-export `Notice` and `Severity` on `sc` (user decision — §Notice module home).
- **PoC:** convert the `no-domains` notice (`_legacy` line 2551) to construct a `Notice` and register
  its code, end-to-end, with the three goldens that render it staying byte-identical.

**Explicitly out of scope:** every other config-adjacent function (`find_modules` is I4, `smtp_login`
is I12, `db_engine_args` is I5); converting any notice *other* than `no-domains`; adding a `csv`/
`csv_extra` field to `Notice` (deferred — §Notice field set); adding `register_notice_code` to `sc`
(deferred until a `check/` package first adopts — §sc re-exports); every other block.

## Why these two together (CAMPAIGN.md §11 row I3)

§11 assigns both to I3. The config move is the mechanical half; the `Notice` class is the design
half. They share no code, but the PoC (`no-domains`) exercises `SiteContext.add_notice`, and the
increment is small enough that splitting would fragment one session's context for no benefit (D4
sizing note applies in reverse: this is comfortably under one session).

## Diagrams (PD#8)

**Module dependency graph after I3** (arrows = "imports"; no cycle — `psh/__init__.py` is empty and
`psh/notice.py` imports only stdlib):

```
        psh/_legacy.py  ──imports──►  psh/configuration.py ──┐
              │  │                          │                 │
              │  └──imports──►  psh/notice.py ◄──imports──────┘ (via sc, below)
              │                     ▲
              └──imports──►  script_context.py (sc) ──imports──►  psh/notice.py
                                    ▲                                  │
     check/ + plugin/  ──sc.Notice / sc.Severity──┘        (stdlib only; no sc/psh imports)
```

Layering (lowest first): `psh/notice.py` (pure, stdlib only) → `script_context.py` (imports notice;
re-exports `sc.Notice`/`sc.Severity`) → `psh/configuration.py` (imports `sc`) → `psh/_legacy.py`
(imports configuration, notice, sc). Acyclic.

**Notice producer→render data flow (the PoC path):**

```
 main() loop: Notice(severity=ALERT, code="no-domains", html=…, text=…, short=…)
        │
        ▼  site_context.add_notice(notice)
 SiteContext.add_notice ──isinstance(Notice)?──► _notice_to_dict ──► legacy notice dict
        │                                             (type/csv/short/message [+text])
        ▼  (existing, unchanged) fill icon-from-type, fill text-from-html2text-if-absent, order-place
 site_context['notices'] += dict  ──► Jinja template (message/text) + subject (short) ──► golden bytes
                                  └─► -notices.csv (n["csv"])   ──► "site,no-domains" (unchanged)
```

Both flows are local to two files each and simple; the diagrams exist to satisfy PD#8's categorical
"dependency graph … in the spec" and to make the no-cycle claim checkable at a glance.

---

## Deliverable A: move mechanics

### The import-back strategy (identical to I2 gateway; keeps the remnant working)

`psh/configuration.py` holds the six defs + DEFER machinery with their **logic preserved
byte-for-byte** except the enumerated ruff/pyright dispositions below. `psh/_legacy.py` re-imports
them so its call sites (`main()` lines 2124/2133/2185/2219) and the `sc`-exposure block
(`sc.umich_enabled`/`sc.cloudflare_enabled`, `_legacy` 1365–1366) keep resolving unchanged:

```python
# psh/_legacy.py, replacing the removed defs:
from psh.configuration import (
    cloudflare_enabled,
    config_substitution,
    gate_disabled_sections,
    load_news_items,
    process_config,
    umich_enabled,
)
```

`psh/configuration.py`'s own import block (the moved bodies require exactly these):

```python
import re
import shlex
import sys
import tomllib
from pathlib import Path        # for the PTH207/PTH123 fixes below
from typing import Any

from rich.markup import escape
from rich.pretty import pprint

import script_context as sc
```

**`import glob` is dropped on purpose** — after the `PTH207` fix (`glob.glob` → `Path(folder).glob`)
`glob` has no remaining user in the moved set, and an unused `import glob` is an `F401` under
`select = ["ALL"]` (not in `ruff-broad.toml`'s ignore list), which would fail the gate this increment
requires. `Path.glob` covers the one former use.

Consequences, all to be re-verified by the implementer:

- `psh._legacy.process_config` / `config_substitution` / `gate_disabled_sections` /
  `load_news_items` / `umich_enabled` / `cloudflare_enabled` still exist (bound to the
  configuration-module objects), so `psh.<name>` through the test `psh` fixture keeps resolving —
  **the ~11 existing tests that call `psh.process_config` / `psh.config_substitution` /
  `psh.gate_disabled_sections` / `psh.load_news_items` need no change** (§Seams explains why no
  repoint is needed, unlike I2).
- `sc.umich_enabled = umich_enabled` / `sc.cloudflare_enabled = cloudflare_enabled` (`_legacy`
  1365–1366) still assign the re-imported (configuration-module) functions, so the `sc` façade and
  `test_documented_sc_facade_names_exist` are unchanged.
- **No `_legacy` imports are orphaned by the move.** Every import the moved code used has other live
  users in `_legacy`: `glob`/`tomllib` (other loaders), `re` (`fqdn_re`, many), `shlex`, `sys`,
  `Any`, `escape` (~50 sites), `pprint`. The implementer re-verifies with grep and removes only what
  its change actually orphans (expect none).

### `no other module references the DEFER internals` (verified)

`_DEFER_TAG`, `config_substitution_re`, `config_substitution_deferred_re` are referenced **only**
inside `config_substitution`/`process_config` (grep-verified: `_legacy` 585, 619 — both interior).
No test imports them. They move as a private unit with the two functions; they are **not** re-imported
into `_legacy` (nothing there needs them).

### Broad-ruff findings on the moved code (decided here, not left to the implementer)

Under `ruff-broad.toml` (`select = ["ALL"]`), the moved code trips the findings below. Each has a
**decided** disposition so a fresh-context implementer never chooses (CAMPAIGN.md §Spec quality bar).
None changes `ruff-broad.toml`'s frozen ignore list (that would be a §13 amendment) — all are inline
`# noqa` (with an inline reason — a bare `noqa` is itself a silent failure, PD#1) or behavior-
preserving edits. Verified 2026-07-17 by running `ruff check --config ruff-broad.toml` on the
extracted bodies:

| Rule | Where | Disposition |
|---|---|---|
| `C901` (18>10), `PLR0912` (18>12), `PLR0915` (57>50) | `config_substitution` def | **`# noqa: C901, PLR0912, PLR0915`** on the def, inline reason: the best-match scorer is moved behavior-preserving; restructuring it is a review activity, not part of a move (I2 `run_terminus` precedent, `prompts/implementation-standards.md` §Test discipline). It is well covered by `tests/unit/test_config_substitution.py` (10 cases). |
| `PLR2004` ×2 | `sc.options.verbose > 1` / `>= 2` in `config_substitution` | **`# noqa: PLR2004`** inline, reason: `-v`/`-vv`/`-vvv` verbosity thresholds are raw domain constants used identically across the (grandfathered) remnant; introducing a named constant only in the moved file would diverge from that idiom. |
| `FBT002` | `process_config(data, path="", deferred_pass=False)` | **Fix**: make the flag keyword-only — `def process_config(data, path="", *, deferred_pass=False)` — and update the **two recursive positional calls** (`_legacy` 623, 627) to `deferred_pass=deferred_pass`. Behavior-preserving: `main()` (2133/2185) and all tests already call it by keyword or use the default. |
| `SIM118` | `n["News"].keys()` in `load_news_items` | **Fix**: `for news_item_name in n["News"]:`. Provably identical iteration. |
| `PTH207` | `glob.glob(f"{folder}/*.toml")` in `load_news_items` | **Fix**: `sorted(Path(folder).glob("*.toml"))`. `Path.glob` returns `Path`s; `sorted()` orders same-directory files by filename identically to the string sort (both compare the trailing `*.toml` name). Guarded by a NEW 2-file ordering test (§New tests). |
| `PTH123` | `open(filename, "rb")` in `load_news_items` | **Fix**: `filename.open("rb")` (`filename` is now a `Path` from the PTH207 fix). The subsequent `f"...{filename}"` interpolations appear **only** in the `sys.exit`/`debug` message strings, which §8 permits to change (stdout/error, not golden or artifact); for the common case (no trailing slash on `folder`) `str(Path)` equals the old glob string anyway, and `Path` collapses a `folder/` trailing slash — a benign message-only difference, never rendered. |

`I001` (import sorting) appeared only as an artifact of the spec-writing extraction; the real file's
import block is authored sorted, so it does not arise.

**`RUF100` (unused-noqa) guard.** `RUF100` is in `select = ["ALL"]` and not ignored, so a `# noqa`
whose code ruff does *not* actually flag on that line becomes a hard error. The `PLR2004`/`C901`/
`PLR0912`/`PLR0915` suppressions above MUST land on exactly the lines ruff flags. The disposition list
was produced by running `ruff check --config ruff-broad.toml` on the extracted bodies (2026-07-17);
the implementer MUST re-run it against the real `psh/configuration.py` and **paste the pre-suppression
finding list in the task report** (PD#14), then confirm "All checks passed!" after — proving each
`# noqa` code matches a real finding rather than silently masking a mismatch.

### Pyright findings on the moved code (decided here)

Standard-mode pyright over `psh/` gates `psh/configuration.py`. The moved bodies trip these, all from
`sc.options`/`sc.config`/`best_match` being loosely typed at their definition. Verified 2026-07-17:

1. **`sc.options.<attr>` "Cannot access attribute" (×N: `.verbose`, `.config`).** Root cause:
   `script_context.py` declares `options = {}` (inferred `dict`), so `sc.options.verbose` /
   `sc.options.config` fail. **Fix in `script_context.py`** (the façade this increment already edits
   for `Notice`): annotate the two module globals honestly —
   ```python
   import argparse            # NEW import
   from typing import Any     # NEW import
   ...
   options: argparse.Namespace = argparse.Namespace()  # parsed CLI options; set by parse_args() caller
   config: dict[str, Any] = {}                          # parsed pantheon-sitehealth-emails.toml
   ```
   **Both imports are required and MUST be added.** `script_context.py` has no
   `from __future__ import annotations`, so these module-level variable annotations are **evaluated at
   runtime**: `config: dict[str, Any] = {}` raises `NameError: name 'Any' is not defined` at import
   (crashing the whole program) if `Any` is not imported, and `argparse.Namespace()` needs `argparse`.
   `argparse.Namespace.__getattr__` returns `Any` (typeshed), so `sc.options.verbose` resolves — and
   this is the *true* runtime type (tests set `sc.options = parse_args([])`, `main()` sets it from the
   real parser; `conftest.py:137`). The empty-`Namespace()` default raises `AttributeError` on an
   unset attribute exactly as `{}.verbose` did, so no runtime path changes. `config` stays a dict.
   *Verified*: a pyright probe with these annotations resolves `options.verbose`/`config.get(...)` at
   0 errors. **This is the minimal honest fix; it is NOT a licence to retype anything else in
   `script_context.py`.**
2. **`best_match["…"]` "Object of type None is not subscriptable" (×2).** `best_match` is
   initialised `= None` and only set when `best_match_score` rises above 0; pyright can't correlate
   the two. **Fix in `psh/configuration.py`**: annotate `best_match: dict[str, Any] | None = None`
   and add `assert best_match is not None` immediately inside `if best_match_score == argc:` (before
   the `func_args` build) and before the final `best_match['args']` print. Both asserts are provably
   true (`best_match_score > 0` ⇒ `best_match` was assigned) and behavior-preserving.

### Seams — no repoint needed (contrast with I2)

The canonical in-process patch point for the config engine stays **`psh.process_config` /
`psh.config_substitution`** (the re-imported `_legacy` bindings). Unlike I2's `run_terminus`, **no
test patches `config_substitution` or `process_config` and then calls the other**: the existing
tests call them directly and register `sc.substitutions` on the façade, which resolves the same
regardless of which module the functions live in. `process_config`→`config_substitution` is an
internal call within `configuration.py`, but nothing intercepts it, so there is no gateway-style
namespace trap. Grep-verified against `tests/`: every reference is a direct `psh.<fn>(...)` call or a
`reset_sc.substitutions`/`reset_sc.config` setup. **No `configuration` conftest fixture is added**
(none is needed — YAGNI, §3.4/PD engineering-preferences).

---

## Deliverable B: `psh/notice.py`, `add_notice`, and the PoC

### Notice module home (user decision)

`Notice`/`Severity`/registry live in a **new `psh/notice.py`** with **no dependency on
`script_context`**, so both the `sc` façade and `psh/` modules import it without a cycle
(`configuration.py`→`sc`→`psh.notice`→nothing). This mirrors the gateway precedent: a new file is
gated by broad-ruff + pyright from birth (never in `ruff-broad.toml`'s `extend-exclude`). `script_context.py`
imports `Notice` for the `add_notice` isinstance check and re-exports `sc.Notice`/`sc.Severity`.

Rejected alternatives (recorded so they are not re-litigated): putting it in `configuration.py`
(circular import — `configuration` imports `sc`, `sc` would import back); putting it in
`script_context.py` (grandfathered from the ratchet, so the new typed code would escape the gate).

### `psh/notice.py` (the whole module — exhaustive)

```python
"""The Notice type and its code registry (CAMPAIGN.md §6).

A typed, frozen replacement for the ad-hoc notice dicts.  Pure: it imports nothing from
script_context, so the sc facade and every psh/ module can import it without a cycle; checks and
plugins reach Notice/Severity via sc.  Adoption is per-increment (CAMPAIGN.md §6); the dict form is
retired in I14.
"""
import dataclasses
from enum import StrEnum


class Severity(StrEnum):
    ALERT = "alert"
    WARNING = "warning"
    INFO = "info"


@dataclasses.dataclass(frozen=True)
class Notice:
    """One report notice.  `code` is the stable, unique short slug (registry-enforced); it maps to
    the notices-CSV code field.  `html` is the report-body HTML; `text` its plaintext (left empty to
    let SiteContext.add_notice derive it via html2text, exactly as the dict form does); `short` is
    the one-line summary; `icon` is left empty to be filled from `severity`; `order` places the
    notice ('prepend'/'first' -> front)."""
    severity: Severity
    code: str
    html: str
    short: str = ""
    text: str = ""
    icon: str = ""
    order: str = "append"


class DuplicateNoticeCodeError(RuntimeError):
    """Raised when a notice code is registered twice.  A shared code across two notice *types* is
    the exact class of bug I1 fixed by hand (BLOCKMAP §Bugs 2/5: shared `php-eol`, duplicate
    `annual-bill`); the registry makes it a loud import-time failure instead."""


class NoticeRegistry:
    """Declare-once registry of notice codes.  Each notice type registers its code once at import;
    a re-used code raises DuplicateNoticeCodeError.  NOT a per-instance registry (a code recurs
    across sites at runtime); registration is import-time metadata, like sc.substitutions/sc.hooks
    (CAMPAIGN.md §3.4: this is not run-scoped mutable state)."""

    def __init__(self) -> None:
        self._codes: dict[str, str] = {}

    def register(self, code: str, *, description: str = "") -> str:
        if code in self._codes:
            raise DuplicateNoticeCodeError(
                f"notice code {code!r} is already registered "
                f"(existing: {self._codes[code]!r}); codes must be unique."
            )
        self._codes[code] = description
        return code

    def codes(self) -> frozenset[str]:
        return frozenset(self._codes)


registry = NoticeRegistry()
```

**Reload constraint (NIT, acknowledged):** the module-level `registry` is a process-global singleton
that producers `register()` into at import. Registration is once-per-process; a deliberate
`importlib.reload()` of a module that registers a code would re-run its `register()` and raise
`DuplicateNoticeCodeError`. This is acceptable — the suite imports `psh._legacy` once (cached, via
`importlib.import_module`, CLAUDE.md § Testing) and never reloads it — and is the same
import-time-once contract `sc.substitutions`/`sc.hooks` already live under.

**Notice field set (deferred modeling, ledgered).** CAMPAIGN.md §6 freezes the fields as `severity,
code, html, text, short, icon, order` — **no `csv`**. The current notice dict's `csv` is
`"{site},{code}[,{extra}]"`; the *site* is supplied by `add_notice` (below), and the *extra* fields
(e.g. `turned-off,{name}`, the `its-recommends-plan` savings) exist only on a handful of notices. I3
follows §6 literally — `Notice` carries `code` only — so it can convert notices whose csv is exactly
`"{site},{code}"` (like `no-domains`). A notice with extra csv fields stays a **dict** until the
increment that adopts it, which will amend §6 (add a `csv_extra` field) via a ledger entry then. This
keeps I3 faithful to the frozen spec and defers the extra-field modeling to a concrete consumer
(engineering-preference "engineered enough"; PD#10 the amendment is written down, not silent).

### `SiteContext.add_notice` accepts a `Notice` (`script_context.py`)

`add_notice` gains `Notice` support by **normalizing a `Notice` to the exact legacy dict** it already
processes, then running its unchanged existing logic (icon-from-type / text-from-html2text / order).
Normalization is the only new code:

```python
from psh.notice import Notice, Severity   # at top of script_context.py

    def add_notice(self, notice) -> None:      # notice: Notice | dict
        if isinstance(notice, Notice):
            notice = self._notice_to_dict(notice)
        # ...existing dict logic unchanged (message-required check, icon fill, text fill, order)...

    def _notice_to_dict(self, notice: "Notice") -> dict:
        """Project a Notice onto the legacy notice dict.  csv is built from the site name + code
        (the two-field form); notices with extra csv fields are not yet Notices (SPEC §Notice field
        set).  icon/text/order are left absent when they equal the value the dict path would default,
        so the stored dict is byte-identical to the legacy one and add_notice's fill logic supplies
        icon/text identically."""
        d = {
            "type": str(notice.severity),                       # StrEnum -> plain "alert"/"warning"/"info"
            "csv": f"{self['site']['name']},{notice.code}",
            "short": notice.short,
            "message": notice.html,
        }
        if notice.icon:
            d["icon"] = notice.icon
        if notice.text:
            d["text"] = notice.text
        if notice.order != "append":                            # add_notice defaults absent order to "append"
            d["order"] = notice.order
        return d
```

`str(notice.severity)` yields the plain `"alert"` string (StrEnum), so every downstream consumer
(`icon[notice['type']]`, the Jinja templates, `n["csv"]`) sees byte-identical values. Leaving
`icon`/`text` absent when the `Notice` doesn't set them routes them through the **same** fill code the
dict path uses — so an unset `text` becomes `html_to_text(html)` exactly as before. **`order` is
included only when it is non-default (`!= "append"`)**: `add_notice` reads `notice['order']` for the
insert position but **never stores it** (`script_context.py:155-159`), and the legacy `no-domains`
dict has **no `order` key** — so an unconditional `"order": "append"` would make the projected dict a
seven-key dict that is *not* byte-identical to the six-key legacy one (invisible to goldens, but the
round-trip test below would catch it). `add_notices` (the list helper) is unchanged; it already
delegates to `add_notice`, which now accepts either form.

### The PoC — convert `no-domains` (CAMPAIGN.md §6 "adopted per increment"; user decision)

`no-domains` (`_legacy` B29, line 2551) is the PoC because it is (a) **simple** — csv is exactly
`"{site['name']},no-domains"`, no extra fields; (b) **core and staying core** (CLAUDE.md: "no-domains/
no-primary-domain remain in core"), so no later increment re-touches it; (c) **rendered in three of
the four goldens** (`test_golden`, `test_golden_drupal`, `test_golden_nonumich` — their subjects are
"…: no domains connected"), so the producer→render path is proven byte-identical **including the
non-U-M path** (Invariant 3).

Change (behavior-preserving representation swap):

1. Register the code once, at module scope in `_legacy.py` (import-time; the registration travels
   with the notice-producer, so when a later increment relocates a producer into a `check/` package
   the `register()` call goes with it):
   ```python
   from psh.notice import Notice, Severity, registry
   ...
   registry.register("no-domains", description="paid plan with no custom domains connected")
   ```
2. Replace the `add_notice({...})` dict at line 2551 with:
   ```python
   site_context.add_notice(
       Notice(
           severity=Severity.ALERT,
           code="no-domains",
           short="no domains connected",
           html=f"""
   <p>{site["name"]} is on a paid plan ...</p>
   """,          # <-- the EXACT existing "message" f-string, interior bytes unchanged
           text=f"""
   {site["name"]} is on a paid plan but does not have ...
   """,          # <-- the EXACT existing "text" f-string, interior bytes unchanged
       )
   )
   ```
   The `html`/`text` values are the existing `message`/`text` f-string literals (`_legacy`
   **2557–2567**) **moved verbatim**. Their continuation lines carry deliberate leading whitespace that
   becomes part of the rendered output; the implementer MUST preserve those interior bytes (Invariant
   8's principle — interior notice-literal bytes never shift). **The `text` literal contains a typo —
   "which people will access the ste or downgrade" (`_legacy:2565`) — present verbatim in all three
   goldens; copy it byte-for-byte, typo included. Do NOT "correct" `ste`→`site`: that breaks all three
   goldens** (Invariant 1). The `icon` is dropped from the call and supplied by
   `add_notice` from `severity` (`icon["alert"] == "&#x1F6A8;"`, the exact value the dict set
   explicitly). The `f` prefix that the old `"short"` carried (`f"no domains connected"`, an `F541`)
   is dropped — `short` is a plain string on the `Notice`.

**Tripwire:** unlike I2's `wp_error`/`drush_error` (no golden covered them), the three goldens above
render `no-domains` and are the primary end-to-end tripwire; `--update-goldens` is forbidden
(Invariant 1). The unit round-trip test (§New tests) is the seam that proves the projection *before*
the goldens run.

### `sc` re-exports (Invariant 9 / §3.5)

Add to the `sc`-exposure block in `_legacy.py` (near the existing `sc.umich_enabled = …` lines) — and
document in CLAUDE.md's runtime-exposed block:

```python
sc.Notice = Notice        # check/plugin packages construct notices as Notice(...)
sc.Severity = Severity    # the severity enum for those notices
```

`register_notice_code`/`registry` are **NOT** added to `sc` this increment: no `check`/`plugin`
package adopts `Notice` in I3, so exposing the registration entry point now would be dead façade
surface (I2's `GatewayResult` precedent, CAMPAIGN.md §17 Q4). The first `check/` adoption adds it. The
PoC (`no-domains`) is core and imports `registry` from `psh.notice` directly.

---

## Seams (declared before implementation — CAMPAIGN.md §Spec quality bar)

| Behavior | Seam | Test tier |
|---|---|---|
| Config funcs after the move | `psh.process_config` / `psh.config_substitution` / `psh.gate_disabled_sections` / `psh.load_news_items` (re-imported bindings; **no repoint** — §Seams above) | unit (existing, unchanged) |
| `Notice`/`Severity`/`NoticeRegistry`/`DuplicateNoticeCodeError` | direct import `from psh.notice import …` | unit (new) |
| `add_notice(Notice)` projection | `sc.SiteContext(...).add_notice(Notice(...))` → assert equal to the dict path | unit (new) |
| `no-domains` PoC end-to-end | the three e2e goldens (byte-identical) | e2e (existing) |
| `sc.Notice`/`sc.Severity` present | `test_documented_sc_facade_names_exist` (extended) | unit (existing, extended) |

No `main()` change here lacks a seam: the config move is behind the existing unit tests; the PoC's
honest seam is the `add_notice(Notice)` unit round-trip (proves equivalence) plus the three goldens
(prove end-to-end). This satisfies `prompts/implementation-standards.md` §Test discipline ("no seam
above the golden? make one") — the round-trip unit test is that seam.

## New tests (instruments — CAMPAIGN.md §7, PD#14)

Each names its red demonstration; an instrument that cannot be shown to go red is not evidence.

1. **`tests/unit/test_notice.py`** (new; tier `unit`):
   - `test_notice_is_frozen` — `dataclasses.replace(n, short="x")` works; `n.short = "x"` raises
     `dataclasses.FrozenInstanceError`. RED if `frozen=True` is dropped.
   - `test_severity_is_str_enum` — `Severity.ALERT == "alert"`, `str(Severity.ALERT) == "alert"`,
     and `{s.value for s in Severity} == {"alert", "warning", "info"}`. RED if a member is renamed
     or a plain Enum is used.
   - `test_registry_rejects_duplicate_code` — a **fresh** `NoticeRegistry()`; `reg.register("x")`
     then `reg.register("x")` raises `DuplicateNoticeCodeError`. **This is the core registry test.**
     Genuinely red-capable: without the `if code in self._codes` guard the second call returns
     silently. (Uses a fresh instance, never the global `registry`, so it neither pollutes nor
     depends on import-time state — the reset_sc-escape-url-leak lesson, MEMORY.md.)
   - `test_registry_registers_distinct_codes` — `reg.register("a"); reg.register("b")`;
     `reg.codes() == {"a", "b"}`.
   - `test_global_registry_has_the_poc_code` — after importing the program, `psh.notice.registry`
     `codes()` contains `"no-domains"` (proves the PoC registered at import). RED if the PoC
     registration is dropped.

2. **`tests/unit/test_add_notice_from_notice.py`** (new; tier `unit`): the round-trip seam.
   - `test_notice_projects_to_legacy_dict` — build a `SiteContext({"name": "s1"})`; call
     `.add_notice(Notice(severity=Severity.ALERT, code="no-domains", short="no domains connected",
     html="<p>hi</p>", text="hi"))`; assert the stored notice dict equals what the **equivalent
     legacy dict** (`{"type": "alert", "csv": "s1,no-domains", "short": "no domains connected",
     "message": "<p>hi</p>", "text": "hi"}`) produces through `.add_notice({...})` on a second
     `SiteContext` — assert **full dict equality** of the two stored notices (neither has an `order`
     key in the append case — §add_notice; the equality covers `type`/`icon`/`csv`/`short`/`message`/
     `text`). RED if `_notice_to_dict` drops, adds, or mistranslates a field (e.g. an unconditional
     `order` key makes the dicts unequal — Finding folded in). **Test-first**: written before
     `add_notice` handles `Notice`, so the first run RED is `TypeError`/missing-`message` (a `Notice`
     has no `["message"]`).
   - `test_notice_text_defaults_via_html2text` — a `Notice` with `text=""` yields a stored
     `text == html_to_text(html)`, identical to the dict path with no `text`. RED if
     `_notice_to_dict` sets `text=""` instead of leaving it for the fill logic.

3. **`tests/unit/test_house_rules.py`** (extend `SC_FACADE_NAMES`): add `"Notice"`, `"Severity"`.
   Pins Invariant 9 for the two new façade names. RED demonstration (per the file's convention):
   temporarily comment out `sc.Notice = Notice` in `_legacy.py`, observe the test fail naming
   `Notice`, revert — recorded in the assertion's docstring/comment.

4. **`tests/unit/test_news.py`** (extend): `test_folder_items_sorted_by_filename` — write **at least
   three** files in a **non-lexical creation order** (e.g. `c.toml`, then `a.toml`, then `b.toml`)
   into `tmp_path` with distinguishable messages; assert the loaded order is lexical `a`, `b`, `c`.
   **Guards the `PTH207` glob→`Path.glob` conversion** (Deliverable A) — without the `sorted()` wrapper
   `Path.glob` yields OS readdir order, which for a non-lexical creation order is very unlikely to
   coincidentally equal lexical, so a dropped sort fails (a 2-file test could pass by chance — NIT
   folded in). Written test-first against the *pre-conversion* code (passes on
   `sorted(glob.glob(...))`, must still pass on `sorted(Path(...).glob(...))`), i.e. it pins behavior
   the conversion must preserve. (A *pinning*/regression test for existing behavior, not red→green of
   new behavior — noted explicitly per §Test discipline.)

The existing `test_config_substitution.py` / `test_news.py` / `test_section_gating.py` cases keep
passing unchanged (they call `psh.<fn>` — re-import keeps them resolving).

## Ratchet (CAMPAIGN.md §13)

`psh/configuration.py` and `psh/notice.py` are **new** files, so they are **not** in
`ruff-broad.toml`'s `extend-exclude` (only `psh/_legacy.py` etc. are) and are gated by the broad ruff
set + pyright standard mode from birth. Both MUST pass `ruff check --config ruff-broad.toml` with "All
checks passed!" and pyright with 0 errors (§7 obligation 3, D2 — cleaned as they move). Nothing is
deleted from `extend-exclude` this increment (the functions move to fresh gated files, same as I2 — no
un-grandfathering of an excluded file). `script_context.py` stays grandfathered; the two annotation
fixes there are outside both gates but are the minimal honest change (§Pyright findings). Record this
in the ledger.

## Behavior bar & invariants preserved (CAMPAIGN.md §8, §9)

- **Four e2e goldens byte-identical** (Invariant 1). The PoC touches three of them and MUST leave them
  byte-identical; `--update-goldens` forbidden. Artifact structure unchanged (§8): the PoC's csv
  string is identical (`"{site},no-domains"`), so `-notices.csv` is unchanged too.
- Per-phase contract untouched — no phase code moves (Invariant 2). `no-domains` is still added at the
  same point in the loop.
- Non-U-M golden green; no U-M content added (Invariant 3) — `no-domains` is generic; the non-U-M
  golden is one of the three tripwires.
- Run lifecycle untouched (Invariant 4). No lifecycle code moves.
- Rich-console rules untouched (Invariant 6) — `config_substitution` already `escape()`s its dynamic
  text (`escape(str(e))` at the moved line 575); moved verbatim.
- Test safety interlock untouched (Invariant 7).
- Column-0/indented notice-literal bytes preserved (Invariant 8) — the PoC's `html`/`text` f-strings
  move verbatim; the three goldens are the tripwire.
- Checks/plugins import only `sc`; `sc` names only **added** (`Notice`, `Severity`), never removed
  (Invariant 9 / §3.5).
- Recorded fixtures not regenerated; `--record` not run (Invariant 10).
- `--create-tables`/`--update`/`--import-older-metrics` gating unchanged (Invariant 11) — no
  phase-gating code moves.
- **§3.4 parallel-ready**: the notice registry is import-time metadata (like `sc.substitutions`), not
  run-scoped mutable state; no new per-run module-level mutable state is added.

## Deviations from CAMPAIGN.md (declared; ledgered at close)

1. **New module `psh/notice.py`** — §3.1's module map is labeled *exhaustive* and the §3 diagram
   enumerates the `psh/` modules, but neither names a home for the `Notice` type (§6 introduces the
   type without pinning a module). Because §3.1 is exhaustive and the §17 closing audit reads it,
   introducing a new core module is handled as a **CAMPAIGN.md amendment, not a ledger-note-only**
   (CAMPAIGN.md §Preamble: "edit the document *and* append a ledger entry"): Task 3 adds a
   one-row `psh/notice.py` entry to §3.1 (`Notice`, `Severity`, `NoticeRegistry`,
   `DuplicateNoticeCodeError`, `registry`) **and** records it in the ledger. This removes the
   ambiguity the reviewer flagged rather than leaving the module discoverable only via the ledger.
2. **PoC converts `no-domains` (B29), out of I3's declared block scope** (§11 row I3 lists the config
   functions). Deliberate: §6 says the class is "adopted per increment", the user chose to convert one
   builder as a PoC, and `no-domains` is core-and-staying-core so no later increment re-touches it.
   The notice's *home* is unchanged (only its representation), so this is representation-preserving, not
   a block move → a **ledger note** (no §3.1/architecture change; recorded in the I3 ledger entry).

## Tasks (subagent-driven — CAMPAIGN.md §12, `prompts/implementation-standards.md`)

Dispatch every code-touching task as `psh-implementer`, every review as `psh-reviewer`; TDD via
`mattpocock-skills:tdd`. Each task ends green (`./run-tests --fast` minimum; four goldens byte-
identical). Per-task commits. Clear any stale `.superpowers/sdd/task-*-report.md` before dispatch
(LEDGER I1 process note).

- **Task 1 — `psh/configuration.py` move.** Create `psh/configuration.py` with the six defs + DEFER
  machinery moved per §Move mechanics (logic verbatim except the enumerated ruff/pyright
  dispositions: the three `# noqa`d complexity findings + two `PLR2004` with inline reasons; the
  `FBT002` keyword-only fix + two recursive-call updates; `SIM118`; `PTH207`/`PTH123`; the two
  `best_match` asserts). Import them back into `psh/_legacy.py`. Apply the `script_context.py`
  `options`/`config` annotation fix. Add the `test_news.py` folder-ordering pin test **first**
  (guards the PTH conversion). Gates: `ruff check --config ruff-broad.toml psh/configuration.py` →
  "All checks passed!"; pyright 0 errors on `psh/`; full `./run-tests --fast` green; four goldens
  byte-identical.
- **Task 2 — `psh/notice.py` + `add_notice` + PoC.** Create `psh/notice.py` (§that module).
  Add `test_notice.py` and `test_add_notice_from_notice.py` **test-first** (the round-trip test RED
  before `add_notice` handles `Notice`). Wire `add_notice`/`_notice_to_dict` in `script_context.py`;
  import `Notice`/`Severity` there. Convert the `no-domains` notice + register its code in `_legacy.py`
  (interior literal bytes verbatim). Add `sc.Notice`/`sc.Severity` re-exports; extend
  `SC_FACADE_NAMES` (with the RED-then-revert demonstration pasted). Gates: both new files pass
  broad-ruff + pyright 0; full `./run-tests --fast` green; **four goldens byte-identical** (the diff
  against the increment baseline pasted empty).
- **Task 3 — Docs, memory, ledger.** Update `CLAUDE.md`: config functions now in
  `psh/configuration.py`; `Notice`/`Severity` added to the runtime-exposed `sc` block and the "Notices
  vs. news" bullet (mention `SiteContext.add_notice` accepts a `Notice`; `psh/notice.py` is the type
  home; dict form retired I14); the Testing façade-names note gains `Notice`/`Severity`. **Amend
  `CAMPAIGN.md` §3.1**: add a one-row `psh/notice.py` entry to the Tier-1 module map (`Notice`,
  `Severity`, `NoticeRegistry`, `DuplicateNoticeCodeError`, `registry`) — §Deviations 1. Report the
  CLAUDE.md line-count delta (DoD). Add an auto-memory for the configuration move + the
  `psh/notice.py` Notice type/registry. Append the LEDGER.md I3 entry (template CAMPAIGN.md §12),
  recording the §3.1 amendment (Deviation 1) and the PoC out-of-block ledger note (Deviation 2).

Then: `/code-review` (or `prompts/adversarial-review.md`) whole-branch; full `./run-tests` (live tier
if credentialed, else `--fast` with a ledger note); `/archive-session`; closing commit including this
`development/` folder.

## Acceptance criteria (commands + pasted output — CAMPAIGN.md §16)

Baseline (I3 start) = `45b8a88` (I2 closing commit). **Run and pasted at close** (commits
`ed2698f` config move, `d21a1d2` notice+PoC, `672866e` docs; live tier NOT run — no live
credentials in this environment, same caveat as prior increments):

```
# 1. Full suite, all three gates, goldens byte-identical:
$ ./run-tests --fast    (tail)
  27 snapshots passed.
  761 passed, 1 skipped, 2 deselected in 28.05s
  Linting (ruff, narrow PD set) ...
  Linting (ruff-broad.toml, campaign ratchet) ...
  Type-checking (pyright, campaign ratchet) ...          # all three gates green
  # (the 1 skip is test_db_credentials.py's importorskip("MySQLdb") on a sqlite-only install)

# 2. Goldens unchanged across the increment (the load-bearing check for the PoC):
$ git diff 45b8a88 HEAD -- tests/e2e/__snapshots__/    →  0 lines (four goldens byte-identical)

# 3. New files under the full gate, zero findings:
$ uvx ruff check --config ruff-broad.toml psh/configuration.py psh/notice.py  →  All checks passed!
$ pyright  (./run-tests scope psh minus _legacy)                              →  0 errors, 0 warnings, 0 informations

# 4. New instruments, shown RED then GREEN (task reports .superpowers/sdd/task-{1,2}-report.md carry
#    the pasted red states; the Task-2 review independently reproduced all three):
#  - test_registry_rejects_duplicate_code: GREEN; red demo = drop the `if code in self._codes` guard
#    -> "DID NOT RAISE DuplicateNoticeCodeError" (reviewer-reproduced).
#  - test_notice_projects_to_legacy_dict: RED before add_notice handles Notice
#    (TypeError: argument of type 'Notice' is not iterable) -> GREEN after _notice_to_dict; forcing an
#    unconditional `order` key re-reds it (reviewer-reproduced).
#  - SC_FACADE_NAMES: RED (remove Severity from the script_context import) "missing ['Severity']" -> GREEN.
#  - test_folder_items_sorted_by_filename: passes on old glob AND new Path.glob; unsorted Path.glob
#    yields non-lexical readdir order (reviewer-reproduced) -> a dropped sorted() would red it.
```

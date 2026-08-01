<!-- CODEGRAPH_START -->
## CodeGraph

In repositories indexed by CodeGraph (a `.codegraph/` directory exists at the repo root), reach for it BEFORE grep/find or reading files when you need to understand or locate code:

- **MCP tool** (when available): `codegraph_explore` answers most code questions in one call — the relevant symbols' verbatim source plus the call paths between them, including dynamic-dispatch hops grep can't follow. Name a file or symbol in the query to read its current line-numbered source. If it's listed but deferred, load it by name via tool search.
- **Shell** (always works): `codegraph explore "<symbol names or question>"` prints the same output.

If there is no `.codegraph/` directory, skip CodeGraph entirely — indexing is the user's decision.
<!-- CODEGRAPH_END -->

## CodeGraph is MANDATORY, not advisory

> Written **outside** the `CODEGRAPH_START`/`END` markers on purpose: `codegraph install` and
> `codegraph init` regenerate that block, and anything inside it is silently lost on the next run.

**While `.codegraph/` exists, querying CodeGraph FIRST is REQUIRED — not preferred — for every
row below, using the command named in that row.**

**All eight MCP tools are exposed in this repo** — `.mcp.json` sets `CODEGRAPH_MCP_TOOLS`, so
the focused tools (`codegraph_node`, `codegraph_search`, `codegraph_callers`,
`codegraph_callees`, `codegraph_impact`, `codegraph_files`, `codegraph_status`) are available
alongside `codegraph_explore`, not just the CLI (they may be deferred — load by name via tool
search). Prefer the MCP tool; the CLI column is the always-works fallback. The ONE exception:
`codegraph affected` has **no MCP form** — the shell is the only way to reach it.

| You are about to… | Tool (MUST, before grep/find/Read/Glob) |
|---|---|
| Ask how something works, survey an area, or answer anything spanning 2+ files | `codegraph_explore` (MCP) **or** `codegraph explore "<names or question>"` |
| Locate a symbol — "where is X" | `codegraph_search` (MCP) or `codegraph query <name>` |
| Read one symbol's source with its caller/callee trail | `codegraph_node` (MCP) or `codegraph node <name>` |
| **Edit a symbol** — find out what breaks | `codegraph_impact` (MCP) or `codegraph impact <name>` — this is the blast radius, and `explore` is not a substitute |
| Find who calls / what is called | `codegraph_callers` / `codegraph_callees` (MCP) or `codegraph callers|callees <name>` |
| Find which tests cover code you changed | `codegraph affected <files…>` (CLI ONLY) — **see the blind spot below** |
| See project structure from the index | `codegraph_files` (MCP) or `codegraph files` |

**`codegraph affected` has a blind spot in THIS repo — measured, not theoretical.** It follows
static imports only. `codegraph affected psh/plans.py` correctly returns 9 test files; `codegraph
affected find-platform-domains-cloudflare.py` returns **none**, despite that file having 205
tests, because the suite reaches it through `SourceFileLoader` at runtime. The same is true of
every standalone-loaded `check/`/`plugin/` module (`tests/helpers/checkload.py`). For those,
"no test files affected" means "no static edge", **never** "untested" — fall back to
`tests/unit/test_<name>.py` by convention.

**Exemptions — this list is EXHAUSTIVE. Anything not on it is covered by the table above:**

1. **Non-code targets** — Markdown, TOML, JSON, `.gitignore`, fixtures, goldens, `development/`.
2. **Content rather than structure** — a string literal, a comment, a config value, a `noqa`
   code. CodeGraph indexes symbols, not arbitrary text; grep is the correct tool.
3. **A file already fully in context this turn.**
4. **Outside the repo or outside the index** — git history, test output, live DNS, vendor docs,
   `.venv/`.
5. **No `.codegraph/` directory** — skip it entirely; indexing is the user's decision.

**The index is not the repo.** CodeGraph indexes symbols in supported languages; a miss on
anything below means "outside the index", **never** "doesn't exist" — grep/Read is the correct
tool there:

- **Non-code text** — Markdown, TOML, JSON, INI, fixtures, goldens: not indexed at all.
- **Shell scripts** — codegraph 1.5.0 has **no shell grammar** (verified against the installed
  language registry, not just the docs): every `.sh` file (`run-tests`' helpers,
  `.claude/hooks/*.sh`, `.devcontainer/*.sh`) is fully invisible. Revisit a
  `codegraph.json` `extensions: {".sh": …}` mapping if a future release adds a shell ID.
- **Extension-less files without a committed `.py` symlink** (see the trap below).
- **Gitignored files, files over 1 MB, and `development/2*/`** — the last excluded on purpose
  by `codegraph.json`, mirroring ruff's exclusion of the frozen archive folders.
- **Content inside indexed files** — string literals, comments, config values: symbols only.
- **YAML** — file-level entry only, zero symbols extracted.

**If you skip it where the table applies, say so in the turn, and say why.** *Intent:* an
unstated skip is how this rule stops existing. Measured over the 2026-07-31 session: **zero**
CodeGraph queries against **25** hand-rolled `grep`/`sed` searches, and it was never mentioned —
the rule was being violated continuously and invisibly, which is exactly the shape PD#14 warns
about applied to an instruction instead of a test.

**Repo-specific trap:** the extension-less executables (`pantheon-sitehealth-emails`,
`find-platform-domains-dns`, `find-platform-domains-cloudflare`) are indexed **only** through
their committed `.py` symlinks. Query them **by symbol name**. An extension-less path returning
nothing means the indexer keyed off the extension — never that the code is unindexed.

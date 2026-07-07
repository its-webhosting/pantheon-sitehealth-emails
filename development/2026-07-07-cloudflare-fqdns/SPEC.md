# Plan / Spec: Move `get_proxied_fqdns` into the program (Cloudflare plugin)

> This document is the implementation spec. It was produced in plan mode, so it also
> serves as the SPEC.md the PROMPT asks for: on approval, copy it to
> `development/2026-07-07-cloudflare-fqdns/SPEC.md` (committed with the code) before/at
> the start of implementation.

## Context

The program currently reads a `fqdns.json` file (a map of every Cloudflare‑proxied website
FQDN) that must be generated **out of band** by the standalone script
`development/2026-07-07-cloudflare-fqdns/get_proxied_fqdns`. Operators have to remember to
run that script before a report run; if the file is stale and `--all` is used, the program
**hard‑exits** telling them to regenerate it.

The goal is to fold that generation into the program's existing `cloudflare` plugin so the
data is fetched from the Cloudflare API on demand, and to enrich the file format with the
Cloudflare **zone ID** each FQDN came from (needed by a near‑future feature). The manual
step disappears; the file self‑refreshes under clear rules.

### Verified facts (independently checked against the code, not just the prompt)

- **`fqdns.json` is consumed in exactly one place** — `pantheon-sitehealth-emails:1652`,
  `if hostname not in proxied_fqdns:`. Only the **dict keys** are used; values are never
  read/indexed/iterated. → Changing values from `[origins]` to `{zone_id, origins}` breaks
  **nothing**, and old array‑format files still load fine (keys unchanged).
- The read block (`:1563–1579`) sits **inside the per‑site loop** and is **not** gated on
  Cloudflare being enabled, so today the file is required on *every* run even when Cloudflare
  is disabled — a latent bug this change removes. The *use* at `:1652` already sits under
  `if cloudflare_enabled and not dns_transient:`.
- The old stale‑file behavior (`:1570–1577`): warn always, and `sys.exit` if `--all`. The new
  auto‑update replaces the exit.
- Plugin/hook plumbing: `script_context.py` `hooks={'setup':[],'check':[]}`, `add_hook`,
  `invoke_hooks`; setup hooks run once at `pantheon-sitehealth-emails:1198`
  (`sc.invoke_hooks("setup")`), **before** the per‑site loop (`:1300`). The cloudflare plugin
  already registers one setup hook and a `sc.plugin_context['plugin.cloudflare']` bag
  (`plugin/cloudflare/__init__.py:9–13`).
- Arg parser (`build_arg_parser`, `:146–232`): `allow_abbrev=False`; boolean flags use
  `action="store_true", default=False`. Multi‑site detection = `sc.options.all or
  len(sc.options.sites) > 1` (consistent with the validation at `:1184–1187`).
- `--update` / `--import-older-metrics` `continue` at `:1537/1541`, **before** the fqdns
  block → they never consume fqdns. `--only-warn` short‑circuits later (`:2928`) → it **does**
  consume fqdns.
- Cloudflare SDK `5.4.0` exposes `client.accounts.list()`, `client.zones.list(account=…)`,
  `client.dns.records.list(zone_id=…, proxied=True)` (introspected). Zone objects have
  `.id`/`.name`; records have `.name`/`.content`.
- `fqdns.json` is **tracked in git *and*** listed in `.gitignore` (`/fqdns.json`). Writes will
  show as modifications to the tracked file.

### Decisions locked with the user

| # | Decision | Choice |
|---|----------|--------|
| 1 | Cloudflare account source | **Enumerate accounts via the SDK** (`accounts.list()`), scan zones per account. **No hardcoded ID, no new config key.** |
| 2 | Fetch failure | **Always fatal** — named exception, clear message, abort the run. No fallback. |
| 3 | Write target | **Replace with a plain file** via atomic temp‑write + `os.replace` (drops the symlink/dated‑file convention). |
| 4 | Traffic‑only runs | **Skip** auto‑update during `--update` and `--import-older-metrics`; `--only-warn` still updates. |
| 5 | File path | **Hardcoded `"fqdns.json"`** (no config key). |
| 6 | Staleness window | **Hardcoded 24 h** (86400 s). |
| 7 | Concurrency | **Serial** zone scan (port as‑is). |
| 8 | `no-certcheck` tag | **Include all proxied records** (do not port the filter). |

### NOT in scope (explicitly deferred/rejected)

- Configurable output path / staleness threshold (decisions 5–6).
- Concurrent/threaded zone scanning (decision 7).
- Porting `--no-certcheck` tag filtering (decision 8).
- Touching the standalone `development/.../get_proxied_fqdns` (it stays as the archived
  original; an external ITS inventory script still uses it — out of our repo's scope).
- The `zone_id` value is **stored but not consumed** yet (future feature); no code reads it.
- Untracking `fqdns.json` from git (`git rm --cached`) — noted as an optional operator cleanup,
  not done here.

---

## Design

### New/changed files

```
plugin/cloudflare/client.py   NEW  — build_client() (auth) + init_cloudflare_client() setup hook
plugin/cloudflare/fqdns.py    NEW  — fetch/decide/write/load proxied FQDNs (the feature)
plugin/cloudflare/ips.py      EDIT — read the shared client from plugin_context (stop building its own)
plugin/cloudflare/__init__.py EDIT — build the bag; register 3 setup hooks in order (when enabled)
pantheon-sitehealth-emails    EDIT — 2 new flags; fix cloudflare_enabled detection; remove
                                     per-site file read; read from plugin_context; disabled+flag guard
```

### One shared `Cloudflare` instance, built once, reused by the whole plugin

Per the user's directive: the `Cloudflare` SDK client is constructed **exactly once** for the
plugin, and every part (`ips`, `fqdns`) uses the **same instance**. It lives in
`sc.plugin_context['plugin.cloudflare']['client']`. This is also more efficient (one auth +
one HTTP session) than the previous per‑hook construction.

**Why a setup hook, not `__init__.py` import time:** `main()` imports plugin packages at
`:1163–1166`, but the **pre‑setup config‑substitution pass runs *after* that** (`process_config`
at `:1168`). So at `__init__.py` import time the Cloudflare creds are still unresolved
`<{secret env …}>` / `<{secret aws …}>` strings — building the client there would use literal
placeholder strings. Setup hooks run later (`:1198`), after substitutions, when creds are real.
So the client is built by a setup hook registered **first**, ahead of the ips and fqdns hooks.

**Why this cleanly dodges the earlier relative‑import hazard:** `ips.py` and `fqdns.py` now
**read** the client from `plugin_context` — they do **not** import a client factory — so they keep
**no relative imports** and stay standalone‑`SourceFileLoader`‑loadable by the test harness. Only
`client.py` holds the builder, imported solely by `__init__.py` (`from .client import …`), which
is always loaded with real package context (`importlib.import_module("plugin.cloudflare")`), never
standalone‑loaded by tests. `client.py` itself has **no relative imports** (`from cloudflare import
Cloudflare`, `import script_context as sc`), so it is standalone‑loadable for its own auth tests.

```python
# plugin/cloudflare/client.py
import sys
from cloudflare import Cloudflare
import script_context as sc

def build_client() -> Cloudflare:
    """Construct the client from [Cloudflare] config: api_token (preferred) else email+api_key.
    No direct-environment fallback.  Missing creds while enabled -> sys.exit (config error)."""
    cf = sc.config['Cloudflare']
    api_token = cf.get('api_token')
    if api_token:
        return Cloudflare(api_token=api_token)
    email = cf.get('email'); api_key = cf.get('api_key')
    if not email or not api_key:
        sys.exit('ERROR: [Cloudflare] is enabled but needs either api_token, '
                 'or both email and api_key.')
    return Cloudflare(api_email=email, api_key=api_key)

def init_cloudflare_client():
    """setup hook (registered FIRST): build the one shared client, stash it in plugin_context.
    setdefault so the hook is robust if the bag wasn't pre-created (e.g. in isolated tests)."""
    sc.plugin_context.setdefault('plugin.cloudflare', {})['client'] = build_client()
```

**Cred‑resolution invariant (document it):** `build_client` runs at the setup‑hook stage
(`:1198`), which is **after** the pass‑1 substitution (`:1169`) but **before** the deferred pass
(`:1201`). So Cloudflare creds must be **pass‑1‑resolvable** — i.e. backed by `<{env …}>` /
`<{secret env …}>` / `<{secret aws …}>`, all of which resolve in pass‑1 (verified: only
`plugin/umich/portal.py` returns `sc.DEFER`; AWS `get_secret` is a substitution that resolves
eagerly). This is **not** a regression — the client was already built at setup‑hook time inside
`get_cloudflare_ips` — but centralizing the builder makes it worth stating so a future adopter
doesn't back a Cloudflare cred with a deferring substitution.

**`ips.py` change** (scope expansion, explicitly approved): `get_cloudflare_ips` drops its inline
`Cloudflare(...)` construction and the token/email selection (now in `build_client`), and instead
does `cloudflare = sc.plugin_context['plugin.cloudflare']['client']` before `cloudflare.ips.list()`.
The `ips.list()` try/except and the CIDR→`ip_network` computation are unchanged. `ips.py` no longer
imports `from cloudflare import Cloudflare`. **Also delete the adjacent dead code** while here:
`get_cloudflare_ipv4_nets()`/`get_cloudflare_ipv6_nets()` (`ips.py:39–44`) reference module globals
`cloudflare_ipv4_nets`/`cloudflare_ipv6_nets` that `get_cloudflare_ips` never assigns (it writes
`plugin_context`), so they'd `NameError` if called — confirm nothing calls them (grep), then remove.

**Imports in `fqdns.py`:** `import cloudflare` (so `except cloudflare.CloudflareError` resolves).
It reads the shared client from `plugin_context` (no `Cloudflare` construction, no inline builder).
Also `os, sys, json, time, tempfile`, `rich.progress`, `import script_context as sc`.

### The feature (`fqdns.py`)

```python
FQDNS_FILE = "fqdns.json"
STALE_SECONDS = 24 * 60 * 60   # 86400

class CloudflareFqdnsError(Exception):
    """A Cloudflare API failure while fetching proxied FQDNs (always fatal)."""

def decide_fqdns_update(*, exists, age_seconds, multi_site, force, suppress, traffic_only):
    """Pure decision function → (should_update: bool, reason: str). No I/O."""
    if force:
        return True, "--update-cloudflare-fqdns requested"
    if traffic_only:
        return False, "traffic-only run (--update/--import-older-metrics); fqdns not consumed"
    if not exists:
        return True, "fqdns.json does not exist"
    if age_seconds > STALE_SECONDS and multi_site and not suppress:
        return True, "fqdns.json older than 24h and processing multiple sites"
    return False, "fqdns.json present (fresh, single-site, or update suppressed)"

def fetch_proxied_fqdns(client) -> dict:
    """accounts -> zones -> proxied DNS records -> {fqdn: {zone_id, origins:[...]}}.
    Ports get_proxied_fqdns' progress bars (CFProgress + progress_bar).
    Wraps cloudflare.CloudflareError -> CloudflareFqdnsError.
    Owns its own observability + empty-result policy:
      - counts accounts / zones / proxied FQDNs; prints a summary line
        (e.g. "Fetched 812 proxied FQDNs across 640 zones in 1 account").
      - **zero zones found -> raise CloudflareFqdnsError** (an authenticated token that
        sees no zones is a scope/permission problem, not a legitimately empty org).
      - zones found but **zero proxied FQDNs -> loud warning**, return {} (a DNS-only org
        is legitimate; the warning makes the 'everything not-proxied' consequence visible).
    IMPLEMENTATION NOTE: put the `if zone_count == 0: raise CloudflareFqdnsError(...)` check
    OUTSIDE/AFTER the try that converts `cloudflare.CloudflareError` -> `CloudflareFqdnsError`,
    so the deliberate zero-zone raise is never re-wrapped/swallowed."""

def _load_existing(path) -> dict:
    """json.load(path). FileNotFoundError -> {} (only reachable on the traffic-only skip,
    which never consumes fqdns).  json.JSONDecodeError -> sys.exit(
      'fqdns.json is not valid JSON; run --update-cloudflare-fqdns to regenerate it.').
    Tolerates both old array-value and new object-value formats (only keys are used)."""

def write_fqdns_atomic(path, data):
    """tempfile.mkstemp in the target dir -> json.dump(indent=4, sort_keys=True) ->
    os.replace(tmp, path).  Cleans up tmp on any exception (incl. KeyboardInterrupt).
    Replacing onto a symlink path replaces the symlink with the plain file."""

def update_and_load_proxied_fqdns():
    """setup-hook entry point (registered only when [Cloudflare].enabled)."""
```

**`update_and_load_proxied_fqdns()` orchestration:**

```
exists      = os.path.exists(FQDNS_FILE)
age_seconds = (time.time() - os.path.getmtime(FQDNS_FILE)) if exists else None
multi_site  = sc.options.all or len(sc.options.sites) > 1
force       = sc.options.update_cloudflare_fqdns
suppress    = sc.options.no_update_cloudflare_fqdns
traffic_only= sc.options.update or sc.options.import_older_metrics

should, reason = decide_fqdns_update(exists=exists, age_seconds=age_seconds or 0,
                                     multi_site=multi_site, force=force,
                                     suppress=suppress, traffic_only=traffic_only)
sc.debug(f"Cloudflare fqdns update decision: {should} ({reason})")

if should:
    sc.console.print(f"[bold green]Updating {FQDNS_FILE} from Cloudflare ({reason}) ...")
    client = sc.plugin_context["plugin.cloudflare"]["client"]   # the one shared instance
    try:
        data = fetch_proxied_fqdns(client)   # prints its own summary; zero-zones -> raises
    except CloudflareFqdnsError as e:
        sys.exit(f"ERROR: could not fetch proxied FQDNs from Cloudflare: {e}")  # decision 2: fatal
    write_fqdns_atomic(FQDNS_FILE, data)
    sc.console.print(f"[bold green]Wrote {len(data)} proxied FQDNs to {FQDNS_FILE}.")
    proxied = data
else:
    if exists and age_seconds > STALE_SECONDS:
        sc.console.print(f":exclamation: [bold red] ATTENTION: {FQDNS_FILE} is more than a day old!")
    proxied = _load_existing(FQDNS_FILE)   # {} if missing (only reachable in traffic-only)

sc.plugin_context["plugin.cloudflare"]["proxied_fqdns"] = proxied
```

`CloudflareFqdnsError` (raised by `fetch_proxied_fqdns` on any `cloudflare.CloudflareError` **or**
zero zones) is caught here → `sys.exit(...)` (decision 2: always fatal). `_load_existing` tolerates
old array‑format and new object‑format (keys only).

### Registration (`__init__.py`, inside the existing `if …enabled:` block)

Create the bag, then register **three** setup hooks **in order** — the client must exist before
the ips/fqdns hooks read it:

```python
from .client import init_cloudflare_client
from .ips import get_cloudflare_ips
from .fqdns import update_and_load_proxied_fqdns

sc.plugin_context['plugin.cloudflare'] = {}
for name, func in (
    ('plugin.cloudflare.client.init_cloudflare_client',        init_cloudflare_client),
    ('plugin.cloudflare.ips.get_cloudflare_ips',               get_cloudflare_ips),
    ('plugin.cloudflare.fqdns.update_and_load_proxied_fqdns',  update_and_load_proxied_fqdns),
):
    sc.hooks['setup'].append({'name': name, 'func': func})
```

(Setup hooks run in registration order — `sc.invoke_hooks("setup")` at `:1198` — so
`init_cloudflare_client` populates `plugin_context['plugin.cloudflare']['client']` before
`get_cloudflare_ips` and `update_and_load_proxied_fqdns` read it.)

### All Cloudflare/`fqdns.json` work happens ONCE, outside the per‑site loop

Both the fetch‑or‑load of `fqdns.json` **and** the client build run in setup hooks
(`sc.invoke_hooks("setup")`, `:1198`) — strictly **before** the per‑site loop (`:1300`). The old
per‑site file read (`:1563–1579`, re‑opening + re‑stat'ing the file for every site) is **deleted**;
the loop only does the keys‑only membership test against the in‑memory
`plugin_context['plugin.cloudflare']['proxied_fqdns']`. No per‑site I/O, no repeated staleness
checks, one API scan per run.

### Main‑script edits (`pantheon-sitehealth-emails`)

1. **`build_arg_parser()`** — add a mutually‑exclusive group (so contradiction is an argparse
   error, a *named* failure):
   ```python
   cf_group = args_parser.add_mutually_exclusive_group()
   cf_group.add_argument("--update-cloudflare-fqdns", action="store_true", default=False,
       help="force-refresh fqdns.json from Cloudflare before this run (requires [Cloudflare] enabled)")
   cf_group.add_argument("--no-update-cloudflare-fqdns", action="store_true", default=False,
       help="suppress the automatic stale-file refresh of fqdns.json")
   ```
   → `sc.options.update_cloudflare_fqdns` / `sc.options.no_update_cloudflare_fqdns`.

2. **Fix `cloudflare_enabled` detection (pre‑existing latent bug, surfaced by review).**
   `:1287` currently reads `cloudflare_enabled = "plugin.cloudflare" in sc.plugin`. But
   `main()` imports **every** plugin package unconditionally (`:1163–1166`) — the enabled‑gating
   lives *inside* `__init__.py` (whether the hook registers), not in whether the package is
   imported. Verified empirically: with `[Cloudflare] enabled=false`, `"plugin.cloudflare" in
   sc.plugin` is **True** while `sc.plugin_context` is **empty**. So the current expression is
   **always True**, and a disabled adopter with a custom domain would `KeyError` on
   `sc.plugin_context["plugin.cloudflare"]["cloudflare_ipv4_nets"]` (`:1623`) — masked today only
   because U‑M always enables Cloudflare and the offline e2e uses platform‑only domains. Replace:
   ```python
   cloudflare_enabled = bool(sc.config.get("Cloudflare", {}).get("enabled"))
   ```
   This fixes the latent bug **and** makes both the existing net access and the new
   `proxied_fqdns` access safe (they only run under `if cloudflare_enabled`). Enabled behavior is
   unchanged (both old and new expressions are True when enabled).

3. **Disabled‑plugin guard for the flag** (after validation, ~`:1177–1192`, before
   `invoke_hooks`) — gate on **config**, not `sc.plugin` (per the bug above):
   ```python
   if sc.options.update_cloudflare_fqdns and not sc.config.get("Cloudflare", {}).get("enabled"):
       sys.exit("--update-cloudflare-fqdns requires the [Cloudflare] section to be enabled in the config.")
   ```
   (`--no-update-…` on a disabled config is a harmless no‑op.)

4. **Remove the per‑site file read** (delete `:1563–1579`) and change the consumption at
   `:1652` to read from plugin context:
   ```python
   if hostname not in sc.plugin_context["plugin.cloudflare"]["proxied_fqdns"]:
   ```
   This line runs only under `if cloudflare_enabled and not dns_transient:`; with the fixed
   detection (item 2), `cloudflare_enabled` ⇒ the `plugin.cloudflare` bag and its `proxied_fqdns`
   key exist (both set when enabled — the bag in `__init__.py`'s registration block, the
   `client` and `proxied_fqdns` keys by the `init_cloudflare_client` and
   `update_and_load_proxied_fqdns` setup hooks).

### Diagrams

**Update‑decision flow (in `decide_fqdns_update`)**

```
                      ┌───────────────────────────┐
   --update-cloudflare-fqdns? ─yes─────────────────┼──► UPDATE ("forced")
                      │no                          │
   --update / --import-older-metrics? ─yes─────────┼──► SKIP  ("traffic-only")
                      │no                          │
   fqdns.json missing? ─yes────────────────────────┼──► UPDATE ("missing")
                      │no                          │
   age>24h AND multi-site AND not --no-update? ─yes─┼──► UPDATE ("stale+multi")
                      │no                          │
                      └────────────────────────────┴──► SKIP  (use existing; warn if stale)
```

**Data flow (three setup hooks, run once in order before the per‑site loop)**

```
[Cloudflare] enabled   ── sc.invoke_hooks("setup")  (pantheon-sitehealth-emails:1198)
   │
   ├─ hook 1  init_cloudflare_client()
   │     build_client()  ─►  plugin_context['plugin.cloudflare']['client']   (ONE shared instance)
   │
   ├─ hook 2  get_cloudflare_ips()
   │     client.ips.list()  ─►  plugin_context[...]['cloudflare_ipv4_nets' / 'cloudflare_ipv6_nets']
   │
   └─ hook 3  update_and_load_proxied_fqdns()
         decide_fqdns_update(...)
            │ update?  client.accounts.list() ─► for each account:
            │            client.zones.list(account) ─► for each zone (progress bar):
            │              client.dns.records.list(zone_id, proxied=True)
            │          {fqdn: {zone_id, origins:[content,…]}}
            │          write_fqdns_atomic(tmp → os.replace → fqdns.json)   (plain file)
            │ skip?    _load_existing(fqdns.json)   (warn if stale)
            ▼
         plugin_context['plugin.cloudflare']['proxied_fqdns']
                              │
                              ▼  per-site loop (:1652) — keys-only membership test, no I/O
   `hostname not in proxied_fqdns`  ─► behind_cloudflare_not_proxied / fqdns_behind_cloudflare
```

### Shadow paths & edge cases (Prime Directives 1–4)

- **Zero zones** (0 accounts, or accounts with no zones): `fetch_proxied_fqdns` raises
  `CloudflareFqdnsError` → fatal. An authenticated token that sees no zones is almost certainly a
  DNS:Read scope/permission problem; failing loud beats persisting `{}` that marks every domain
  "not proxied."
- **Zones present but zero proxied FQDNs**: `fetch_proxied_fqdns` prints a **loud warning** and
  returns `{}` (a DNS‑only Cloudflare org is legitimate). The warning makes the
  "everything not‑proxied" consequence visible (Prime Directive 1).
- **API error** (auth/network/rate‑limit) → `cloudflare.CloudflareError` wrapped as
  `CloudflareFqdnsError` → caught in the hook → `sys.exit` (fatal). Catch the SDK base
  `cloudflare.CloudflareError` **specifically**, not bare `Exception` (verify the exact class at
  implementation; 5.4.0 base is `CloudflareError`).
- **Missing credentials while enabled** → `_cloudflare_client()` `sys.exit` (mirrors `ips.py`).
  This is a **config‑time** exit (a plain `sys.exit` string), distinct from the API‑failure
  `CloudflareFqdnsError`; both are visible and fatal.
- **User interrupts (Ctrl‑C) mid‑fetch/write** → temp file cleaned up in `write_fqdns_atomic`'s
  `except`; existing `fqdns.json` untouched; `KeyboardInterrupt` propagates and the run exits.
- **Same FQDN in ≥2 zones / ≥2 records**: append `content` to `origins`; **keep the first
  zone_id**; if a *different* zone_id is seen for the same FQDN, `sc.console.print` a warning
  (visible, first‑zone‑wins is deterministic).
- **Old array‑format file on disk**: `_load_existing` loads it; only keys are used, so it
  works until the next update rewrites it in the new format.
- **`fqdns.json` symlink present on first run**: `os.path.getmtime` follows it for the age
  check; `os.replace` replaces the symlink itself with the new plain file (decision 3).
- **Disabled Cloudflare**: hook never registers; nothing fetched/read; consumption skipped.
  Fixes the old "file required even when disabled" bug.
- **Enabled but a genuinely empty account (0 zones)**: per decision 2 this is **fatal** — such an
  adopter cannot run the tool until they fix the token's DNS:Read scope (or add zones). Called out
  in the operator doc so it isn't a surprise.
- **`--create-tables --update-cloudflare-fqdns` (enabled)**: setup hooks run (`:1198`) before
  `--create-tables` exits (`:1235`), so the fetch/write happens during a schema‑creation run.
  Harmless (the operator explicitly asked to force‑refresh); documented, not special‑cased.

---

## Testing (extends the existing harness — no parallel approach)

Follow `tests/integration/test_plugin_cloudflare.py`'s pattern: fake `cloudflare` in
`sys.modules` before loading the module via `SourceFileLoader`, monkeypatch `Cloudflare`,
set `sc.config`/`sc.plugin_context` by hand, use `tmp_path` as cwd for file writes. Reuse
`psh`, `reset_sc`, `monkeypatch`. Never run the program except via `run_program`; never use
`--all`/`--for-real`/live `--create-tables`.

### Unit — `tests/unit/test_fqdns_decision.py` (`pytest.mark.unit`)
- Load `plugin/cloudflare/fqdns.py` (fake `cloudflare` module first, like the sibling).
- **Table test** of `decide_fqdns_update` covering every branch: force→update; traffic_only
  (no force)→skip; force beats traffic_only; missing (non‑traffic)→update; stale+multi+not‑suppress
  →update; stale+multi+suppress→skip; stale+single→skip; fresh+multi→skip.
- **Hypothesis property**: `force ⇒ update`; `traffic_only ∧ ¬force ⇒ ¬update`; result is always
  a `(bool, str)` with a non‑empty reason. (Pure function, no I/O — good fuzz target.)

### Integration — `tests/integration/test_plugin_cloudflare_client.py` (`pytest.mark.integration`)
The **auth‑selection** logic moved from `ips.py` into `client.py`'s `build_client()`, so its tests
move with it (tests follow the code). Load `plugin/cloudflare/client.py` standalone (fake
`cloudflare` module first, monkeypatch the loaded module's `Cloudflare`, capture ctor kwargs via
`seen_kwargs`):
- `api_token` preferred; `email`+`api_key` used otherwise; missing creds → `SystemExit`.
- `init_cloudflare_client()` stores the built client at
  `sc.plugin_context['plugin.cloudflare']['client']` — the test may start from an empty
  `sc.plugin_context` because the hook uses `setdefault` (no pre‑seeding required).
These are the same three assertions the current `test_plugin_cloudflare.py` auth tests make —
relocated, not lost.

### Integration — `tests/integration/test_plugin_cloudflare.py` (EDIT existing)
`get_cloudflare_ips` no longer builds a client; it reads the shared one. **Fixture change:** the
`load_ips` fixture (`:38–55`) currently fakes `cloudflare` in `sys.modules` and each test
monkeypatches `module.Cloudflare` — but after the refactor `ips.py` no longer defines
`Cloudflare`, so that monkeypatch target is gone (leaving it → `AttributeError`). Remove the
`Cloudflare` monkeypatch scaffolding; instead each test **seeds a fake client** into
`sc.plugin_context['plugin.cloudflare']['client']` (with a fake `.ips.list()`), calls
`get_cloudflare_ips`, and asserts the CIDR→`ip_network` results land in `plugin_context`. The
`ips.list()`‑failure → `SystemExit` test stays (the fake client's `ips.list` raises). The three
**auth** tests here are **removed** (relocated to the client test above). This is the churn the
user approved by OK'ing the `ips.py` change.

### Integration — `tests/integration/test_plugin_cloudflare_fqdns.py` (`pytest.mark.integration`)
Fake SDK exposing `accounts.list()`, `zones.list(account=…)`, `dns.records.list(zone_id=…,
proxied=…)` returning `SimpleNamespace`/lists with `.id`/`.name`/`.content`. The fake
`cloudflare` module **must** also define a real exception class
(`fake_pkg.CloudflareError = type("CloudflareError", (Exception,), {})`) so `fqdns.py`'s
`except cloudflare.CloudflareError` resolves and the "fetch raises → SystemExit" test can raise it.
The shared client is provided by **seeding** `sc.plugin_context['plugin.cloudflare']['client']`
with the fake (the fqdns hook reads it from there — no monkeypatch of a builder needed).
- **`fetch_proxied_fqdns(fake_client)`** builds `{fqdn: {zone_id, origins}}` correctly: single
  record; multiple records for one FQDN merge origins; **same FQDN across two zones** keeps the
  first `zone_id` and emits the conflict warning; multiple accounts are all scanned; **zero zones →
  `CloudflareFqdnsError`**; **zones but zero proxied → `{}` + warning** (assert on captured console
  output).
- **`write_fqdns_atomic`** into `tmp_path`: writes valid JSON (indent/sort), and when the target
  is a pre‑existing **symlink**, the result is a **plain file** (`os.path.islink` is False) with
  the data.
- **`_load_existing`**: missing → `{}`; malformed JSON → `SystemExit`; old array‑format file →
  loads (keys usable).
- **`update_and_load_proxied_fqdns`** in‑process, cwd=`tmp_path`, `sc.config['Cloudflare']`
  enabled, `sc.plugin_context={'plugin.cloudflare':{'client': fake_client}}`, `sc.options` via
  `psh.parse_args([...])`:
  - `--update-cloudflare-fqdns` → writes file + populates `plugin_context['plugin.cloudflare']['proxied_fqdns']`.
  - missing file (report run, single site) → fetches; **fresh single‑site** existing file → no
    fetch (assert the fake client's list methods were **not** called), loads existing.
  - **fetch raises** `cloudflare.CloudflareError` → `SystemExit` (fatal).

### Integration — `cloudflare_enabled` fix (`pytest.mark.integration`)
- Add a focused test that with `[Cloudflare] enabled=false` the detection is False:
  build `sc.config` disabled + `sc.plugin={'plugin.cloudflare':<module>}` + empty
  `sc.plugin_context`, evaluate the same expression the program now uses
  (`bool(sc.config.get("Cloudflare", {}).get("enabled"))`), assert False. This locks the
  latent‑bug fix (the old `"plugin.cloudflare" in sc.plugin` returned True). *Note:* the full
  disabled‑path‑with‑custom‑domain flow isn't reachable from the offline goldens (domain:list is
  platform‑only), so this expression‑level assertion is the pragmatic guard; a full e2e for that
  path is a deferred gap, called out here.

### e2e / golden — no new golden; assert non‑regression
- All offline e2e configs have `[Cloudflare] enabled = false` (`minimal.toml`,
  `minimal-nonumich.toml`) → the new hook never registers, the removed per‑site read changes
  nothing observable → **goldens must stay byte‑identical without `--update-goldens`.**
  Verify: `grep -n 'enabled' tests/fixtures/config/minimal*.toml` shows Cloudflare false; run
  `./run-tests --fast` and confirm goldens pass unchanged.
- **Keep** `make_workdir`'s fresh `fqdns.json = "{}"` stub (`conftest.py:154–167`) but update its
  comment **honestly**: with all offline subprocess configs Cloudflare‑*disabled*, the per‑site
  read is gone and the hook never registers, so the stub is **not read** on any current run — it
  is now effectively vestigial, retained only as a defensive belt‑and‑suspenders (a fresh empty
  file would also make `decide_fqdns_update` return "skip" *if* a Cloudflare‑enabled subprocess
  config were ever added). Do **not** frame it as an active safeguard. Confirm no `run_program(...)`
  call uses a Cloudflare‑enabled config: `grep -rn 'full.toml' tests/` should show only in‑process
  loads, not `run_program`.

### Acceptance criteria (exact commands → observable outcomes)
1. `./run-tests --fast` → **green**, goldens unchanged (no `--update-goldens` needed).
2. `./run-tests -m "unit or integration" -k fqdns` → new tests **green**.
3. `./run-tests` (full, incl. `live`) → **green**.
4. `./pantheon-sitehealth-emails --update-cloudflare-fqdns --no-update-cloudflare-fqdns …`
   → argparse error "not allowed with argument".
5. With `[Cloudflare] enabled=false`: `./pantheon-sitehealth-emails --date 20240731
   its-wws-test1 --update-cloudflare-fqdns` → exits "requires the [Cloudflare] section to be
   enabled".
6. **Live (needs Cloudflare creds + a Pantheon test site)** — dry run:
   `./pantheon-sitehealth-emails --date <last-of-month> its-wws-test1 --update-cloudflare-fqdns`
   → shows the zone progress bars, writes `fqdns.json` whose values are
   `{"zone_id": "<uuid>", "origins": [...]}`, and the report run completes using it
   (`python -c "import json; d=json.load(open('fqdns.json')); k=next(iter(d)); assert 'zone_id' in d[k] and 'origins' in d[k]"`).

---

## Documentation updates (part of implementation)

- **README.md**: remove/mark‑done the TODO line 228 (`fqdns.json (get direct from Cloudflare…)`);
  in "Key flags" document `--update-cloudflare-fqdns` / `--no-update-cloudflare-fqdns` and the
  auto‑refresh rules; drop the "must run `get_proxied_fqdns` first" expectation; note the new
  `fqdns.json` value shape `{zone_id, origins}`.
- **sample‑pantheon‑sitehealth‑emails.toml**: add a one‑line comment under `[Cloudflare]` that,
  when enabled, `fqdns.json` is auto‑refreshed from Cloudflare (no new keys).
- **docs/** (end‑user/operator): new `docs/cloudflare-fqdns.md` — what `fqdns.json` is now, when
  it auto‑refreshes, the two flags, that fetching needs `[Cloudflare]` enabled + DNS:Read
  credentials, and that a fetch returning **zero zones is a fatal error** (fix the token's
  DNS:Read scope). Operator‑facing only (no internal design).
- **CLAUDE.md**:
  - Under the Cloudflare‑auth note: the plugin now builds **one shared `Cloudflare` client** in
    `plugin/cloudflare/client.py` (`build_client()` + the `init_cloudflare_client` setup hook,
    registered FIRST), stored at `sc.plugin_context['plugin.cloudflare']['client']` and reused by
    `ips.py` and the new `fqdns.py`. `fqdns.py` fetches proxied FQDNs (accounts→zones→proxied
    records) and writes `fqdns.json` in a setup hook (runs once, before the per‑site loop). Note
    the cred‑resolution invariant (client built after pass‑1 substitution, before the deferred
    pass).
  - Note the `cloudflare_enabled` detection now reads config
    (`sc.config["Cloudflare"]["enabled"]`), not `"plugin.cloudflare" in sc.plugin` (which is
    always True because every plugin package is imported regardless of `enabled`).
  - Note `fqdns.json` values are now `{zone_id, origins}` (was bare arrays) and the program reads
    **only the keys**, so both formats load; `zone_id` is stored for a future feature, unused now.
  - Document the two flags + the update decision rules and that `--update`/`--import-older-metrics`
    skip the refresh.
  - Update the "generated artifacts" line: `fqdns.json` is now program‑generated (still git‑ignored,
    still tracked — optional `git rm --cached`).

---

## Adversarial review & SPEC.md

Per the PROMPT: before final approval, dispatch an independent reviewer subagent against this
document (5 dimensions), fix issues (≤3 iterations / convergence guard), and report the score.
On approval, write `development/2026-07-07-cloudflare-fqdns/SPEC.md` from this document (it is
committed alongside the code), then implement in the order: `client.py` → `ips.py` (read shared
client) → `fqdns.py` → `__init__.py` (bag + 3 ordered hooks) → main‑script edits (flags,
`cloudflare_enabled` fix, guard, consumption) → tests (relocate auth tests to
`test_plugin_cloudflare_client.py`, edit `test_plugin_cloudflare.py` to inject the shared client,
add fqdns tests) → docs → `./run-tests`.

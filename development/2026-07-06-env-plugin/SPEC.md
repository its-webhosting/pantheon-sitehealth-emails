# SPEC: `env` config-substitution plugin + route all env reads through config

Status: approved plan, pre-implementation. This document is the implementation contract and the
"what/why" record. It is not primary documentation (the code, `CLAUDE.md`, and `docs/` are).

## 1. Problem & goal

`pantheon-sitehealth-emails` resolves `<{ ... }>` substitutions in TOML config values against
plugin-registered functions (e.g. `<{secret aws webinfo db_pass}` → AWS Secrets Manager). The
program **also** reads process environment variables directly in a handful of places, bypassing the
config file, which makes "where does this value come from" inconsistent and undiscoverable.

Goal: add an **`env`** substitution plugin so any setting can be sourced from an environment
variable, then convert every direct env read in the program's own code to a config setting that
uses it. The config file becomes the single source of truth for where values come from. As part of
this, the (now-live) SMTP send is gated + fully configured, and Cloudflare auth becomes
config-driven with API-token support.

## 2. Verified facts (independently confirmed against the code)

- Substitution delimiter is `<{ ... }` — a **single** closing `}` (regex
  `config_substitution_re = re.compile(r"<\{(.*?)(?<!\\)}")`, `pantheon-sitehealth-emails:786`).
  The PROMPT examples (`<{env DATABASE_PASSWORD}`) are correct as written.
- `config_substitution(expr, path)` (`:721-783`): `shlex`-splits the inner text (POSIX; honors
  quoting), then a **best-match scoring** loop picks the registered `sc.substitutions` entry whose
  `args` pattern matches most tokens (literal token → +1; `$name` token → +1 and captured). The
  chosen function is called with **positional string args**, one per `$var` named in `func_args`.
  - Return `None` → framework does `sys.exit(1)`.
  - Raising an exception propagates (aws's `get_secret` uses this).
  - `best_match_score == 0` or partial-but-imperfect → framework prints a `[bold red]` error and
    `sys.exit(1)`.
- `process_config(data, path)` (`:789-804`) recurses dicts/lists and regex-substitutes strings. It
  runs **twice** in `main()`: pre-setup (`:1105`, right after plugin import at `:1099-1102`) and
  post-setup (`:1137`, after `sc.invoke_hooks("setup")`). ⟹ a substitution must be registered at
  plugin **import** time to be usable in the pre-setup pass.
- Config load: `sc.config = tomllib.load(f)` at `:1094-1096`.
- Plugins self-register in `plugin/<name>/__init__.py`, discovered by `find_modules()` (`:807-820`,
  non-empty `__init__.py`), imported in **sorted** order: `plugin.aws` < `plugin.cloudflare` <
  `plugin.env` < `plugin.umich`. Existing plugins gate on
  `'<Sec>' in sc.config and 'enabled' in sc.config['<Sec>'] and sc.config['<Sec>']['enabled']`.
- **Exactly 6 direct env reads** in the program's own code (excluding `.venv`/vendor):
  | # | site | var | disposition |
  |---|------|-----|-------------|
  | 1 | `pantheon-sitehealth-emails:204` | `USER` | **change** — `--smtp-username` default |
  | 2 | `pantheon-sitehealth-emails:829` | `SMTP_PASSWORD` | **change** — `smtp_login()` |
  | 3 | `plugin/cloudflare/__init__.py:9-10` | `CLOUDFLARE_EMAIL` | **remove** — config-only |
  | 4 | `plugin/cloudflare/__init__.py:11-12` | `CLOUDFLARE_API_KEY` | **remove** — config-only |
  | 5 | `plugin/aws/__init__.py:10-11` | `AWS_PROFILE` | **leave** — boto plumbing |
  | 6 | `plugin/aws/__init__.py:12-13` | `AWS_DEFAULT_REGION` | **leave** — boto plumbing |
  Items 5-6 configure the boto3 SDK (not application logic) and are explicitly out of scope.
- **SMTP send is LIVE** (not commented out): `smtp_login()` + `send_message()` at `:3923-3926`;
  the empty-username guard at `:1176-1177`; dry-run `To:` built at `:3884`.
- `cloudflare` SDK **accepts `api_token`** (verified: `Cloudflare.__init__` exposes
  `api_token`, `api_key`, `api_email`, ...).
- e2e/golden runs always pass `--smtp-username testuser` (`conftest.py:238`, `E2E_SMTP_USERNAME`),
  so changing the `--smtp-username` **default** does not disturb goldens. Only
  `tests/unit/test_argparse_contract.py:24` asserts the old `USER` default and must change.
- **Current baseline is RED.** Because the SMTP send was unconditionally re-enabled (commit
  `8c5fc01`) with no `enabled` gate, `./run-tests --fast` currently has **6 e2e failures**: each
  subprocess run reaches `smtp_login()` and dies with `SMTPAuthenticationError(535)` against
  `smtp.mail.umich.edu:465`. The unit/integration tiers and the rendered snapshots are green
  (only the e2e subprocess exit codes are non-zero). **Step D's `smtp_enabled` gate is what
  restores the e2e tier to green** — it is a prerequisite, not a neutral change (see §9).

## 3. Design decisions (confirmed with the user)

1. **`env` plugin is always-on.** Registered unconditionally at import (no `[Env]` section),
   because `env` has no external dependency or setup cost and core config values use it (e.g.
   `[SMTP].username = "<{env USER}"`, resolved whenever `[SMTP]` is enabled). Gating `env` behind
   its own `enabled` flag would create a chicken-and-egg problem (a disabled `[Env]` would break
   every `<{env …}>` in the file). This is a deliberate, documented exception to the "gate every
   plugin on an `enabled` flag" convention.
2. **SMTP dry-run username precedence: CLI → config → omit.** When `[SMTP]` is disabled (its keys
   are stripped, §4.3) and no `--smtp-username` is given, drop the `{user}@{domain}` operator copy
   from the dry-run `To:` rather than reading `USER` directly. No direct env read remains.
3. **Optional default arg: yes**, trailing form `<{env NAME default}` and
   `<{secret env NAME default}` (quote for spaces: `<{env NAME "a b"}`). Unset var → default;
   empty-but-set var → `""` (unset ≠ empty).
4. **Cloudflare auth is config-only, no fallback.** Remove the `os.getenv` override block; the code
   always uses the resolved `[Cloudflare]` settings (the operator decides in the config where the
   values come from — a literal, `<{secret env …}>`, `<{secret aws …}>`, etc.). `api_token` is
   preferred over `email`+`api_key` when present and truthy.
5. **Update the live private config repo** (`pantheon-sitehealth-emails-config/`, the symlink
   target), committed **separately** in that repo. Prod `[SMTP].enabled = true`; prod
   `[Cloudflare]` stays `enabled = true`.

## 4. Implementation

### 4.1 New plugin `plugin/env/` (§decision 1, 3)

`plugin/env/get_env.py`:
```python
import os

import script_context as sc

_UNSET = object()  # distinguishes "no default supplied" from an empty-string default


def get_env(name, default=_UNSET):
    """Return the value of environment variable `name`.

    An env var that is set but empty returns "" (set != unset). If the var is unset:
    return `default` when one was supplied, else raise ConfigSubstitutionError so the
    framework aborts with a path-annotated message (see config_substitution).
    """
    if name in os.environ:
        return os.environ[name]
    if default is not _UNSET:
        return default
    raise sc.ConfigSubstitutionError(f"environment variable '{name}' is not set")
```

`plugin/env/__init__.py` (**always-on**; 4 registrations, 2-arg forms **before** their 3-arg
counterparts — see §4.5 for why order is load-bearing):
```python
import script_context as sc

from .get_env import get_env

# The `env` substitution has no external dependency and is needed by core [SMTP] config
# (`<{env USER}`), so it is registered unconditionally rather than gated on an `enabled` flag.
# Order matters: the 2-arg (no-default) pattern must precede the 3-arg ($default) pattern so the
# best-match engine's perfect-match short-circuit binds `<{env NAME}` to the no-default form.
sc.substitutions.append({'args': ['env', '$name'],
                         'func': get_env, 'func_args': ['$name']})
sc.substitutions.append({'args': ['env', '$name', '$default'],
                         'func': get_env, 'func_args': ['$name', '$default']})
sc.substitutions.append({'args': ['secret', 'env', '$name'],
                         'func': get_env, 'func_args': ['$name']})
sc.substitutions.append({'args': ['secret', 'env', '$name', '$default'],
                         'func': get_env, 'func_args': ['$name', '$default']})
```

### 4.2 Named-exception error path (`script_context.py` + engine)

`script_context.py` — add near the top (after imports):
```python
class ConfigSubstitutionError(Exception):
    """Raised by a config-substitution function to abort the run with a helpful,
    config-path-annotated message (caught in config_substitution)."""
```

`config_substitution()` (`pantheon-sitehealth-emails`, ~`:761-769`) — two edits inside the
`if best_match_score == argc:` branch. (1) Guard the `func_args` build so a malformed substitution
that matches a `$var` count but leaves a `$var` uncaptured — e.g. the zero-name `<{env}` /
`<{secret env}` forms, which dispatch with `best_match_score == argc` but an empty `args_map` —
fails cleanly with a path-annotated message instead of a bare `KeyError`. (2) Wrap the call to
catch `ConfigSubstitutionError`:
```python
        try:
            func_args = [best_match_args_map[arg] for arg in best_match["func_args"]]
        except KeyError:
            sc.console.print(
                f"[bold red]ERROR: configuration value for {path}: malformed substitution: {expr}"
            )
            sys.exit(1)
        ...
        try:
            result = best_match["func"](*func_args)
        except sc.ConfigSubstitutionError as e:
            sc.console.print(
                f"[bold red]ERROR: configuration value for {path}: {e}"
            )
            sys.exit(1)
        if result is None:
            sys.exit(1)
        return str(result)
```
Only `ConfigSubstitutionError` is caught around the call; any other exception (e.g. aws
`get_secret`'s `KeyError`) still propagates unchanged. Yields, e.g.:
`ERROR: configuration value for SMTP.password: environment variable 'SMTP_PASSWORD' is not set`,
and for `<{env}`: `ERROR: configuration value for <path>: malformed substitution: env`. This
`func_args` guard hardens **all** substitutions, not just `env`.

### 4.3 `enabled = false` section stripping (§PROMPT rule)

New helper near `process_config` in the main script:
```python
def gate_disabled_sections(config: dict) -> dict:
    """For every top-level section whose `enabled` is the boolean False, keep only
    {'enabled': False} and drop the section's other settings. Done BEFORE substitution
    resolution so a disabled feature never forces its `<{secret env ...}>` values to
    exist. Sections without an `enabled` key, or with any non-False value, are untouched.
    """
    for name, value in list(config.items()):
        if isinstance(value, dict) and value.get('enabled') is False:
            sc.debug(f"Section [{name}] is disabled; keeping only 'enabled', dropping other keys")
            config[name] = {'enabled': False}
    return config
```
Call in `main()` immediately after the config load (`:1096`), **before** the plugin-import loop and
both `process_config` passes:
```python
    with open(sc.options.config, "rb") as f:
        sc.config = tomllib.load(f)
    sc.config = gate_disabled_sections(sc.config)
```
Scope notes: top-level tables only (nested tables like `[Pantheon.plan_info]` are unaffected);
trigger is strictly the TOML boolean `false` (`value.get('enabled') is False`), so a string
`enabled = "false"` does **not** strip (documented as boolean-only).

### 4.4 SMTP: env → config, gate the send (§decision 2)

- `build_arg_parser` (`:200-206`): change `--smtp-username` default from
  `os.environ.get("USER", "")` to `None`.
- `script_context.py` — add helper (mirrors the existing `msgid_domain()` helper):
```python
def smtp_username() -> str:
    """Effective SMTP/dry-run username: CLI --smtp-username, else [SMTP].username, else ''."""
    if options.smtp_username is not None:
        return options.smtp_username
    return config.get('SMTP', {}).get('username', '') or ''
```
- `smtp_login()` (`:823-830`):
```python
def smtp_login() -> SMTP_SSL:
    smtp_cfg = sc.config.get("SMTP", {})
    host = smtp_cfg.get("host", "smtp.mail.umich.edu")
    port = smtp_cfg.get("port", 465)
    username = sc.smtp_username()
    password = smtp_cfg.get("password")
    if not username or not password:
        sys.exit("SMTP is enabled but username or password is not configured "
                 "(set [SMTP].username/[SMTP].password or pass --smtp-username).")
    smtp_connection = SMTP_SSL(host, port=port)
    smtp_connection.login(username, password)
    return smtp_connection
```
- Gate the send block (`:3923-3926`) on `smtp_enabled`; when false, skip
  `smtp_login()`/`send_message()` (the `.eml` is still written). Compute
  `smtp_enabled = bool(sc.config.get("SMTP", {}).get("enabled"))` **once before the per-site loop
  begins** (the loop that contains `:3923`), not inside it, and reference it in the `if` that wraps
  the two send lines. This restores the e2e tier to green (§2, current-baseline note).
- Dry-run `To:` (`:3884`): build from non-empty parts so the operator copy is omitted when no
  username is resolvable:
```python
        u = sc.smtp_username()
        parts = [dry_run_to]
        if u:
            parts.append(f"{u}@{dry_run_domain}")
        msg["To"] = ", ".join(p for p in parts if p)
```
- Remove the unconditional empty-username `sys.exit` guard at `:1176-1177` (superseded by the
  omit-operator behavior for dry runs and the explicit guard inside `smtp_login`).

### 4.5 Why the 2-arg-before-3-arg registration order is required

The engine keeps the first pattern at the highest score (`if match_score > best_match_score`) and
short-circuits only on a *perfect* match (`match_score == argc and match_score == match_args_len`).

- `<{env FOO}` (argc 2): the 2-arg pattern scores 2 == argc == len → perfect, breaks immediately →
  `get_env("FOO")`. It never reaches the 3-arg pattern. ✔
- `<{env FOO bar}` (argc 3): 2-arg scores 2 (inner loop breaks at the extra token), then 3-arg
  scores 3 == argc == len → replaces and breaks → `get_env("FOO", "bar")`. ✔
- If the 3-arg pattern were registered first, `<{env FOO}` would match it with score 2 (not
  perfect, no break); the later 2-arg pattern ties (2, not `>`) and does not replace it, so the
  3-arg pattern wins and `func_args=['$name','$default']` → `best_match_args_map['$default']`
  `KeyError`. Hence the fixed order. (Same reasoning for the `secret env` pair.)

No cross-family collisions: `secret env X` scores 1 against aws's `['secret','aws','$name','$key']`
(breaks at `aws≠env`) and 3 against `['secret','env','$name']`; `secret aws …` scores 1 against the
env `secret` patterns. The `env` plugin sorts/imports after `aws`, so aws's `secret` pattern is
registered first — irrelevant to correctness given the disjoint second token.

### 4.6 Cloudflare: config-only auth + rename + token (§decision 4)

`plugin/cloudflare/__init__.py` — drop `import os` and the `os.getenv` override block; keep the
enabled-gated hook registration:
```python
import script_context as sc

if 'Cloudflare' in sc.config and 'enabled' in sc.config['Cloudflare'] and sc.config['Cloudflare']['enabled']:
    from .ips import get_cloudflare_ips
    sc.plugin_context['plugin.cloudflare'] = {}
    sc.hooks['setup'].append({'name': 'plugin.cloudflare.ips.get_cloudflare_ips', 'func': get_cloudflare_ips})
```

`plugin/cloudflare/ips.py` (`get_cloudflare_ips`, client construction):
```python
    cf = sc.config['Cloudflare']
    api_token = cf.get('api_token')
    if api_token:
        cloudflare = Cloudflare(api_token=api_token)
    else:
        email = cf.get('email')
        api_key = cf.get('api_key')
        if not email or not api_key:
            sys.exit("ERROR: [Cloudflare] is enabled but needs either api_token, or both "
                     "email and api_key.")
        cloudflare = Cloudflare(api_email=email, api_key=api_key)
```
(Renames `member_email` → `email`, `member_api_key` → `api_key`; adds preferred `api_token`. Uses
`.get` + a clear `sys.exit` rather than a bare `KeyError` if the config repo wasn't renamed in
lockstep — see §8.)

### 4.7 Config files (§decision 5)

`sample-pantheon-sitehealth-emails.toml`:
- `[Cloudflare]`: `email = "<{secret env CLOUDFLARE_EMAIL}"`,
  `api_key = "<{secret env CLOUDFLARE_API_KEY}"`, and commented
  `# api_token = "<{secret env CLOUDFLARE_API_TOKEN}"  # preferred when uncommented`. Update the
  surrounding comments (no more "if the env var is not set" fallback wording).
- `[SMTP]` (rewrite the currently-commented block):
  ```toml
  [SMTP]
  enabled  = false
  host     = "smtp.mail.umich.edu"
  port     = 465
  username = "<{env USER}"                    # overridable with --smtp-username
  password = "<{secret env SMTP_PASSWORD}"
  ```
- Add a short comment block documenting the `env` plugin forms
  (`<{env NAME}`, `<{secret env NAME}`, optional trailing default) and the "disabled section keeps
  only `enabled`" rule.

Live repo `pantheon-sitehealth-emails-config/pantheon-sitehealth-emails.toml` (separate commit):
same `[Cloudflare]` rename + commented `api_token`; add `[SMTP]` with **`enabled = true`**, `host`,
`port`, `username = "<{env USER}"`, `password = "<{secret env SMTP_PASSWORD}"`.

Test fixtures (`tests/fixtures/config/`): rename the Cloudflare keys in `minimal.toml` and
`minimal-nonumich.toml` to `email`/`api_key` (both have `[Cloudflare].enabled = false`, so the
strip rule removes them regardless — the rename is for schema consistency and has no golden
impact). `minimal-nonumich.toml` **already has an `[SMTP]` section** (`host`/`port`, no `enabled`
key); leave it that way — it must **not** gain `enabled = true`. Its missing `enabled` key makes
`smtp_enabled = bool(...get("enabled"))` False, which is exactly what keeps the non-U-M e2e run
from attempting a send after step D. Do **not** add an enabled `[SMTP]` to any e2e golden fixture
(that would trigger a real send); new SMTP/strip/env behavior is exercised by dedicated
unit/integration configs (inline dicts or small fixtures) in §5.

## 5. Tests (extend the existing `tests/` harness — honor its safety interlocks)

Reuse fixtures `psh`, `reset_sc`, `temp_db`, `program_runner`, `run_program`, and the config-path
allowlist. Never run `--all`/`--for-real`, `--create-tables`/`--import-older-metrics` against live
data. Per the PROMPT, **do not write SMTP-*sending* tests** this session — cover credential
sourcing and the enable-gate without performing a real send (monkeypatch `SMTP_SSL`).

### 5.1 `tests/unit/test_env_plugin.py` (new)
- `get_env`: set → value; unset + default → default; unset + no default → raises
  `ConfigSubstitutionError`; set-but-empty (`FOO=""`) → returns `""` (not the default).
- Registration: after `plugin.env` import, `sc.substitutions` contains the 4 expected entries and
  the 2-arg pattern precedes its 3-arg counterpart for both `env` and `secret env`.
- End-to-end through `psh.process_config` (with `reset_sc`): a config dict with values
  `<{env FOO}`, `<{secret env FOO}`, `<{env FOO def}`, `<{secret env FOO def}` resolves correctly;
  an unset var with no default raises `SystemExit` and the printed message contains the config
  path and the var name (capture via `capsys`/`console`).
- Malformed form `<{env}` (no name) raises `SystemExit` with a `malformed substitution` message
  (the `func_args` guard from §4.2), not a bare `KeyError` traceback.
- Hypothesis property: for arbitrary valid env-name/value pairs (monkeypatched), `get_env(name)`
  round-trips the set value; with the var unset, `get_env(name, d)` returns `d`.

### 5.2 `tests/unit/test_section_gating.py` (new)
- `gate_disabled_sections`: a section with `enabled = False` keeps only `{'enabled': False}`;
  sections with `enabled = True`, no `enabled` key, or `enabled = "false"` (string) are untouched.
- Integration-of-order: build a config where a **disabled** section contains
  `value = "<{secret env DEFINITELY_UNSET}"`; assert `gate_disabled_sections` then
  `process_config` runs **without** `SystemExit` (the substitution was dropped), while the same
  value in an **enabled** section raises `SystemExit`.

### 5.3 `tests/unit/test_argparse_contract.py` (update)
- Replace the `:24` assertion (`ns.smtp_username == os.environ.get("USER","")`) with
  `ns.smtp_username is None` (new default), and add a case that `sc.smtp_username()` falls back to
  `[SMTP].username` when the option is `None`.

### 5.4 `tests/integration/test_email_config.py` (update)
- **Migrate the credential seeding**: the existing cases seed the password via
  `monkeypatch.setenv("SMTP_PASSWORD", ...)` and set `reset_sc.config = {"SMTP": {host, port}}`
  (no `password`). After the `smtp_login` rewrite, `password = smtp_cfg.get("password")` → `None`
  → the new guard `sys.exit`s. So these cases must put `password` (and, where the CLI username is
  not set, `username`) **into the `[SMTP]` config dict**, not the environment.
- SMTP password/username are sourced from `[SMTP]` config (monkeypatch `SMTP_SSL` with a fake that
  captures `login(user, pass)`; assert the captured values come from config, not env). No real
  network/send.
- `smtp_enabled` gate: with `[SMTP].enabled` false/absent, the send path is skipped (no
  `SMTP_SSL` constructed) while the `.eml` is still produced.
- Dry-run `To:` omits the `{user}@{domain}` operator copy when `sc.smtp_username()` is empty, and
  includes it when set.

### 5.5 `tests/integration/test_cloudflare_auth.py` (new)
- Monkeypatch `cloudflare.Cloudflare` (capture kwargs) and `.ips.list`; call
  `plugin.cloudflare.ips.get_cloudflare_ips` with an inline `sc.config['Cloudflare']`:
  - `api_token` present → constructed with `api_token=…` (no `api_email`/`api_key`);
  - `api_token` absent → constructed with `api_email=email, api_key=api_key`.

### 5.6 e2e / golden
- The rendered **snapshots** must stay byte-identical (the Cloudflare key rename and
  disabled-section strip do not change rendered output): `./run-tests --update-goldens` yields an
  empty diff. Distinct from the snapshot content, the e2e **subprocess exit codes** are currently
  non-zero (§2 red baseline) and return to 0 once step D's `smtp_enabled` gate lands — after which
  the WordPress (`its-wws-test1`), Drupal (`its-wws-test2`), and non-U-M e2e tests pass.
- No fixture re-record (`--record`) is expected; no Pantheon interaction changes.

## 6. Acceptance criteria (exact commands + observable outcomes)

1. `./run-tests --fast` → all green (offline gate). Show output.
2. Goldens unchanged: `./run-tests --update-goldens` produces no snapshot diff.
3. Manual smoke, using a scratch config under `tests/fixtures` (never the live config/DB):
   - `<{env FOO}` with `FOO=bar` → resolves to `bar`.
   - `<{env FOO}` with `FOO` unset → process exits non-zero with
     `ERROR: configuration value for <path>: environment variable 'FOO' is not set`.
   - `<{env FOO fallback}` with `FOO` unset → resolves to `fallback`.
   - A `[Widget] enabled = false` section containing `<{secret env DEFINITELY_UNSET}` → run does
     **not** error (section stripped before substitution); the processed section is `{enabled: False}`.
   - Cloudflare: with `api_token` set in config, the SDK client is constructed with `api_token=`
     (asserted via `test_cloudflare_auth.py`).
4. `grep` shows no direct env reads remain in program code except the two boto plumbing lines in
   `plugin/aws/__init__.py` (items 5-6).
5. Full `./run-tests` green (the `live` tier runs only if Pantheon/SSH creds are present in the
   session; note in the run output whether live ran or was skipped).

## 7. Documentation updates

- **README.md**: document the `env` / `secret env` substitutions and the optional trailing default;
  the `[SMTP]` section (`enabled`/`host`/`port`/`username`/`password`) and `--smtp-username`
  override; the renamed `[Cloudflare]` keys (`email`/`api_key`) + preferred `api_token`; the
  `enabled = false` → keep-only-`enabled` rule; and the operational note that **enabled** sections'
  `<{secret env …}>` values require the env var to be present (no fallback). Correct any "SMTP send
  is commented out" wording — it is live and gated by `[SMTP].enabled`.
- **CLAUDE.md**: correct the "SMTP send is currently commented out" statement; note
  `ConfigSubstitutionError`, the gate-before-substitute ordering, the always-on `env` plugin
  exception to the enable-gate convention, and the Cloudflare config-only (no-fallback) auth.
- **docs/** (end-user only): new page `docs/env-and-smtp-configuration.md` — how to back a setting
  with an environment variable (`<{env NAME}` / `<{secret env NAME}` / with a default), configure
  `[SMTP]` for sending, and set Cloudflare credentials or an API token. No internal-implementation
  detail.

## 8. Rollout / observability / risk

- **Breaking config change**: renaming `[Cloudflare]` keys and adding `<{secret env …}>` values
  makes enabled sections require their env vars at substitution time (hard exit if missing, by
  design — decision 4). Mitigation: the live config repo is updated in the same effort (separate
  commit); the error message names both the config path and the missing var.
- **Live SMTP in prod**: prod `[SMTP].enabled = true` means monthly report runs send (test
  addresses unless `--for-real`). `--update`/`--only-warn` runs generate no reports and send
  nothing. `SMTP_PASSWORD` must be present on report runs or the run exits at substitution time
  with a path-annotated message.
- **Observability**: `gate_disabled_sections` emits a `sc.debug` line per stripped section; the
  post-setup `process_config` dump (`-v`) shows resolved values; substitution failures print a
  `[bold red]` path-annotated error before exit. No new silent failure modes.
- **Deferred (written down, not in scope)**: SMTP-*sending* tests (explicitly deferred by the
  user); migrating aws `get_secret` onto `ConfigSubstitutionError` (left raising as-is); relocating
  the boto `AWS_*` env plumbing (items 5-6).

## 9. Execution order

A (env plugin) → B (`ConfigSubstitutionError` + engine catch) → C (`gate_disabled_sections`) →
D (SMTP) → E (Cloudflare) → F (config files incl. separate prod-repo commit) → G (tests) →
H (docs).

## 10. Post-implementation review fixes

A `/code-review high` pass after implementation surfaced three issues, all fixed:

1. **Secrets re-interpreted by the second `process_config` pass (correctness).** Routing real
   secrets through `<{secret env …}>` newly exposed them to the two-pass design: a resolved value
   containing a `<{…}>` sequence (e.g. a password) was re-scanned by pass 2 and aborted the run.
   Fixed with a `sc.DEFER` sentinel + tagged-marker mechanism: pass 1 resolves everything (final
   values become inert literals); a substitution needing setup-hook data returns `sc.DEFER` and
   `config_substitution` re-emits its marker with an invisible NUL tag; the post-setup pass
   (`process_config(..., deferred_pass=True)`) re-resolves **only** those tagged markers. This
   fixes the secret case AND preserves `plugin.umich.plan_info`'s deferral (converted from the old
   magic-string re-emission to `return sc.DEFER`). Verified: `SMTP_PASSWORD='p@ss<{x}'` survives
   both passes. Tests: `test_resolved_value_with_delimiters_survives_two_passes`,
   `test_defer_sentinel_reresolves_on_second_pass`, `test_deferred_pass_ignores_untagged_markers`.
2. **Over-broad test assertion (test-coverage).** `test_get_env_unset_no_default_raises` now
   asserts `pytest.raises(sc.ConfigSubstitutionError)` rather than `Exception`.
3. **Inconsistent AWS error (consistency).** `plugin/aws/get_secret.py` now raises
   `sc.ConfigSubstitutionError` for a missing key (clean, path-annotated exit consistent with
   `env`) instead of a bare `KeyError`. Test updated:
   `test_missing_key_raises_config_substitution_error`.

**Per-step verification, given the red baseline (§2):** the e2e tier does not go green until D
lands. So after A–C, run the unaffected tiers (`./run-tests --fast -m "not e2e"`, i.e. unit +
integration) and expect green there; the 6 pre-existing e2e send failures persist. After **D**,
run full `./run-tests --fast` and expect the whole offline gate green (D restores the e2e exit
codes). Continue full `--fast` after E–H. Run the golden check (`--update-goldens`, empty diff)
before the final commit. Rationale: D is a prerequisite for a green e2e tier, not a neutral change;
attempting a full-green `--fast` gate after A–C would fail on the inherited baseline, not on the
new work.

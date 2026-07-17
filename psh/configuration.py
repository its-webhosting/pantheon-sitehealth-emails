"""Configuration engine: <{ ... }> substitution (two-pass, with DEFER), section gating, news
loading, and the umich/cloudflare feature flags.  Moved from psh/_legacy.py at campaign I3; the
remnant re-imports these names so its call sites resolve unchanged (CAMPAIGN.md §3.1)."""
import re
import shlex
import sys
from pathlib import Path
from typing import Any

import tomllib
from rich.markup import escape
from rich.pretty import pprint

import script_context as sc


def config_substitution(expr: str, path) -> str:  # noqa: C901, PLR0912, PLR0915 -- best-match scorer moved behavior-preserving; restructuring is a review activity, not part of a move (I2 run_terminus precedent). Covered by tests/unit/test_config_substitution.py.
    argv = list(shlex.shlex(expr, posix=True))
    argc = len(argv)
    if sc.options.verbose > 1:
        sc.debug(f"\nconfig_substitution: {path}")
        pprint(argv)
    if argc == 0:
        return ""

    # Figure out which substitution matches the expression most closely:
    best_match: dict[str, Any] | None = None
    best_match_score = 0
    best_match_args_map = {}
    for match in sc.substitutions:
        match_args = match["args"]
        match_args_len = len(match_args)
        match_score = 0
        args_map = {}
        for i in range(argc):
            if i >= match_args_len:
                break
            if match_args[i] == argv[i]:
                match_score += 1
            elif match_args[i].startswith("$"):
                match_score += 1
                args_map[match_args[i]] = argv[i]
            else:
                break
        if match_score > best_match_score:
            best_match = match
            best_match_score = match_score
            best_match_args_map = args_map
            if match_score == argc and match_score == match_args_len:
                break

    if sc.options.verbose >= 2:  # noqa: PLR2004 -- same: verbosity threshold, not a magic number to name
        sc.debug(f"best_match: {best_match_score}")
        pprint(best_match_args_map)
        pprint(best_match)

    if best_match_score == argc:
        # A malformed substitution can match on token count yet leave a $var uncaptured -- e.g.
        # the zero-name forms "<{env}" / "<{secret env}", which score == argc with an empty
        # args_map.  Guard the func_args build so that fails cleanly instead of with a bare
        # KeyError traceback.
        assert best_match is not None  # noqa: S101 -- pyright type-narrowing only: best_match_score > 0 implies best_match was assigned above; not a security/input-validation check, so stripping under -O is harmless (SPEC §Pyright findings #2)
        try:
            func_args = [best_match_args_map[arg] for arg in best_match["func_args"]]
        except KeyError:
            sc.console.print(
                f"[bold red]ERROR: configuration value for {path}: malformed substitution: {expr}"
            )
            sys.exit(1)
        if sc.options.verbose >= 2:  # noqa: PLR2004 -- same: verbosity threshold, not a magic number to name
            sc.debug("args:")
            pprint(func_args)
        try:
            result = best_match["func"](*func_args)
        except sc.ConfigSubstitutionError as e:
            sc.console.print(
                f"[bold red]ERROR: configuration value for {path}: {escape(str(e))}"
            )
            sys.exit(1)
        if result is None:
            sys.exit(1)
        if result is sc.DEFER:
            # The substitution's backing data is not ready yet (a setup hook populates it).
            # Re-emit the marker with an invisible tag so ONLY the post-setup pass re-resolves
            # it -- a pass-1 final value that merely happens to contain "<{...}" (e.g. a secret)
            # is left untouched by the second pass.  See process_config()/main().
            return "<{" + _DEFER_TAG + expr + "}"
        return str(result)

    if best_match_score == 0:
        sc.console.print(
            f"[bold red]ERROR: configuration file value for {path} contains an unknown substitution: {expr}"
        )
        sys.exit(1)

    assert best_match is not None  # noqa: S101 -- pyright type-narrowing only: best_match_score > 0 implies best_match was assigned above; not a security/input-validation check, so stripping under -O is harmless (SPEC §Pyright findings #2)
    sc.console.print(
        f"[bold red]ERROR: no match found for configuration file value of {path}"
    )
    sc.console.print(f"[bold red]value: {argv}")
    sc.console.print(f"[bold red]best match: {best_match['args']}")
    sc.console.print(f"[bold red]{best_match_score} out of {argc} arguments matched")
    sys.exit(1)


# A NUL tag marks a re-emitted DEFERred substitution (see config_substitution).  NUL cannot occur
# in a config/env/secret value, so the deferred pass can re-resolve exactly the deferred markers
# and never a pass-1 final value that merely happens to contain "<{...}".
_DEFER_TAG = "\x00"
config_substitution_re = re.compile(r"<\{(.*?)(?<!\\)}")
config_substitution_deferred_re = re.compile(r"<\{" + _DEFER_TAG + r"(.*?)(?<!\\)}")


def process_config(data: Any, path="", *, deferred_pass=False) -> Any:
    """Resolve <{ ... }> substitutions in every string value.

    Called twice by main(): the first (pre-setup) pass resolves everything, tagging any
    substitution that returns sc.DEFER for the second pass.  The second (`deferred_pass=True`,
    post-setup) pass re-resolves ONLY those tagged markers, so a value already resolved to a
    final literal in pass 1 is never re-interpreted -- even if it contains a "<{...}" sequence.
    """
    regex = config_substitution_deferred_re if deferred_pass else config_substitution_re
    if isinstance(data, dict):
        for key, value in data.items():
            new_path = f"{path}.{key}" if path else f"{key}"
            data[key] = process_config(value, new_path, deferred_pass=deferred_pass)
    elif isinstance(data, list):
        for index, item in enumerate(data):
            new_path = f"{path}[{index}]"
            data[index] = process_config(item, new_path, deferred_pass=deferred_pass)
    elif isinstance(data, str):
        data = re.sub(
            regex,
            lambda m: config_substitution(m.group(1), path),
            data,
        )
    return data


def gate_disabled_sections(config: dict) -> dict:
    """For every section (at any depth) whose `enabled` is the boolean False, keep only
    {'enabled': False} and drop the section's other settings.

    Done BEFORE substitution resolution (process_config) so a disabled feature never forces its
    `<{secret env ...}>` / `<{secret aws ...}>` values to exist -- turning a feature off must not
    require its credentials to be present.  Applies recursively: a nested table like
    [Cloudflare.cachecheck] with `enabled = false` is reduced to {'enabled': False}, and a
    disabled parent drops its nested tables entirely (a disabled parent wins over an enabled
    child).  Sections without an `enabled` key, or whose `enabled` is anything other than the
    boolean False (e.g. True, or the string "false"), are left untouched.
    """
    for name, value in list(config.items()):
        if isinstance(value, dict):
            if value.get("enabled") is False:
                sc.debug(f"Section [{name}] is disabled; keeping only 'enabled', dropping other keys")
                config[name] = {"enabled": False}
            else:
                gate_disabled_sections(value)
    return config


def load_news_items() -> None:
    """
    Populate sc.news from the config file's inline [News.<x>] sub-tables and from every
    *.toml file in [News].folder.

    Config-inline items are added first, then file-based items. Scalar directives in the
    [News] table (e.g. `folder`) are skipped -- only sub-tables (dict values) are news items.
    A missing [News] section is a no-op (previously the folder glob crashed with KeyError).
    """
    if "News" in sc.config:
        for name, value in sc.config["News"].items():
            if not isinstance(value, dict):
                continue  # skip scalar directives such as `folder`
            if value.get("enabled") is False:
                # A disabled item: either the operator set enabled = false here, or the
                # recursive gate_disabled_sections() already stripped the sub-table to
                # {'enabled': False}.  Skip it instead of hitting add_news_item's
                # missing-"message" fatal.
                sc.debug(f"Skipping disabled news item {name}")
                continue
            sc.add_news_item(
                value,
                f"{name} in configuration file {sc.options.config}",
            )
    folder = sc.config.get("News", {}).get("folder")
    if folder:
        for filename in sorted(Path(folder).glob("*.toml")):
            with filename.open("rb") as f:
                n = tomllib.load(f)
                if "News" not in n:
                    sys.exit(f'News item in {filename} is missing the "News" key.')
                for news_item_name in n["News"]:
                    if (isinstance(n["News"][news_item_name], dict)
                            and n["News"][news_item_name].get("enabled") is False):
                        # Same enabled = false semantics for file-based items (these are
                        # not part of sc.config, so gate_disabled_sections never sees
                        # them -- honor the flag here for consistency).
                        sc.debug(f"Skipping disabled news item {news_item_name} in {filename}")
                        continue
                    sc.add_news_item(
                        n["News"][news_item_name],
                        f"{news_item_name} in file {filename}",
                    )


def umich_enabled() -> bool:
    """
    True when the config enables the U-M plugin/check packages ([UMich].enabled).

    Institution-specific checks that would otherwise emit U-M content (e.g. the fqdns-gated
    Cloudflare-cache plugin/module checks that link to U-M documentation) are gated on this so
    a non-U-M deployment does not see them (P8b).
    """
    return (
        "UMich" in sc.config
        and "enabled" in sc.config["UMich"]
        and sc.config["UMich"]["enabled"]
    )


def cloudflare_enabled() -> bool:
    """True when [Cloudflare].enabled is set.

    Read from config, NOT `"plugin.cloudflare" in sc.plugin`: every plugin package is imported
    regardless of `enabled` (the gating lives inside the plugin's __init__), so the membership
    test is always True.  This is the true signal, and it guards the plugin_context reads
    (cloudflare_ipv*_nets, proxied_fqdns) that exist only when enabled.
    """
    return bool(sc.config.get("Cloudflare", {}).get("enabled"))

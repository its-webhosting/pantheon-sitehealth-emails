"""Module discovery and the hook engine (campaign I4; CAMPAIGN.md sections 3.1 and 4).

find_modules() moved from psh/_legacy.py; PHASES/add_hook/invoke_hooks moved from
script_context.py, which re-exports them so sc.add_hook et al. keep resolving for every
check/plugin package (Invariant 9).

Import direction (do not reverse either leg -- see SPEC D-i4-2):

        script_context.py --(module-level from-import: PHASES/add_hook/invoke_hooks)--> psh/modules.py
                ^                                                                          |
                +--------(function-level import, call-time only: hooks/console/debug)------+

script_context imports THIS module at its top, so a module-level `import script_context`
here would make first-import order decide between a working program and an ImportError on a
partially-initialized module.  Engine functions import it at call time instead; by then both
modules are fully initialized.  The mutable hook registry itself (sc.hooks) deliberately
STAYS in script_context: it is cross-cutting run state (CLAUDE.md), psh/ modules add no
module-level mutable state (CAMPAIGN.md section 3.4), and tests/conftest.py::reset_sc
rebinds sc.hooks around every test -- a second copy here would silently desync from it.
"""

import os
import stat
import sys
from collections.abc import MutableMapping
from typing import Any

from rich.markup import escape

# Ordered lifecycle phases.  'setup' runs once per run (NOTE: including --create-tables,
# which exits later); the site_* phases run once per processed site, in this order, each
# receiving the SiteContext -- but a per-site fatal error (e.g. a domain:list failure) skips
# that site's remaining phases, so hooks must not assume a later phase always follows an
# earlier one.  Phases through site_post_gather run on full-report and --only-warn paths;
# site_pre_render only on the full-report path; --update and --import-older-metrics never
# reach any site_* phase.  Dotted names (e.g. 'setup.umich.portal') are plugin-defined
# events: allowed, not ordered here.  The per-phase site_context data contract lives in
# CLAUDE.md ("Per-site report pipeline").
PHASES = (
    'setup',
    'site_pre',            # first per-site seam (rename of the old 'check' seam; fires
                           # after the traffic gather, just before site_post_traffic --
                           # no per-phase keys guaranteed)
    'site_post_traffic',
    'site_post_dns',
    'site_post_gather',
    'site_pre_render',
    'run_finish',          # once per run, inside finish_run(), before any artifact is
                           # written -- on completed AND aborted runs (both call finish_run).
                           # Fired with no arguments until I13 introduces RunState
                           # (CAMPAIGN.md section 4); no consumer yet, like site_pre_render
                           # at its introduction.
)


def find_modules(module_type: str) -> list[str]:
    modules = []
    # find all non-empty regular files in/under the directory f"{type}" that are named "__init__.py":
    for dirpath, _dirs, files in os.walk(module_type, followlinks=True):
        for file in files:
            if file == "__init__.py":
                target = os.path.join(dirpath, file)  # noqa: PTH118 -- target stays a str for the "/"-split below; a Path would need re-stringifying for no benefit
                st = os.stat(target)  # noqa: PTH116 -- os.stat, not Path.stat, keeps this a plain (dirpath, file) join+stat verbatim from the original
                if stat.S_ISREG(st.st_mode) and st.st_size != 0:
                    parts = target.split("/")[:-1]
                    target_name = ".".join(parts)
                    modules.append(target_name)
    modules.sort()  # ensure a consistent order when importing to simplify troubleshooting
    return modules


def _valid_hook_name(hook_name: str) -> bool:
    return hook_name in PHASES or '.' in hook_name


def add_hook(hook_name: str, target: dict) -> None:
    """Register a hook.  `target` MUST carry `name`, `func`, and the data-contract
    declarations `consumes` and `produces` (each a possibly-empty list of contract-key
    names, CLAUDE.md per-phase table; CAMPAIGN.md section 4).  Dotted plugin events must
    declare both empty.  Violations exit loudly here -- nothing enters sc.hooks
    undeclared, which is what lets validate_hooks()/ordered_hooks() index the keys
    unconditionally."""
    import script_context as sc  # noqa: PLC0415 -- call-time import; see the module docstring

    if not _valid_hook_name(hook_name):
        sc.console.print(f'[bold red]ERROR: add_hook: unknown phase "{hook_name}" '
                         f'(known phases: {", ".join(PHASES)}; dotted names are plugin events)')
        sys.exit(1)
    hook_label = escape(str(target.get("name", "<unnamed>")))
    for entry in ("consumes", "produces"):
        value = target.get(entry)
        if not isinstance(value, list) or not all(isinstance(key, str) for key in value):
            sc.console.print(
                f'[bold red]ERROR: add_hook: hook "{hook_label}" for "{escape(hook_name)}" must '
                f'declare "{entry}" as a list of contract-key names ([] when none) -- '
                f'see the per-phase data contract in CLAUDE.md')
            sys.exit(1)
    if '.' in hook_name and (target["consumes"] or target["produces"]):
        sc.console.print(
            f'[bold red]ERROR: add_hook: dotted event "{escape(hook_name)}" hook "{hook_label}" '
            f'must declare empty consumes/produces (contract keys are phase-anchored)')
        sys.exit(1)
    sc.hooks.setdefault(hook_name, []).append(target)


def invoke_hooks(hook_name: str, *args, **kwargs) -> None:
    import script_context as sc  # noqa: PLC0415 -- call-time import; see the module docstring

    if not _valid_hook_name(hook_name):
        sc.console.print(f'[bold red]ERROR: invoke_hooks: unknown phase "{hook_name}"')
        sys.exit(1)
    sc.debug(f'[bold magenta]=== Calling hooks for {hook_name}:')
    for hook in sc.hooks.get(hook_name, []):
        sc.debug(f'Invoking {hook_name} hook target {hook["name"]}')
        hook['func'](*args, **kwargs)


# The machine-readable form of CLAUDE.md's per-phase data-contract table -- THIS is
# authoritative (CAMPAIGN.md section 4); the CLAUDE.md table is its prose rendering.
# Keys FIRST guaranteed at each phase; availability is cumulative (site_pre_render
# guarantees everything above it and adds nothing).  The base SiteContext keys
# (site/notices/sections/attachments) are construction, not contract, and hooks do not
# declare them.  validate_hooks() reads this to resolve consumed keys (SPEC section 4).
CONTRACT: dict[str, tuple[str, ...]] = {
    "setup": (),
    "site_pre": (),
    "site_post_traffic": ("traffic_rows", "start_date", "end_date"),
    "site_post_dns": (
        "domains", "custom_domains", "primary_domain", "main_fqdn",
        "fqdns_behind_cloudflare", "fqdns_not_behind_cloudflare", "not_in_dns",
        "behind_cloudflare_not_proxied", "proxied_in_multiple_zones", "dns_transient",
    ),
    "site_post_gather": (
        "framework", "site_url", "wordpress_version", "drupal_version",
        "wordpress_plugins", "drupal_modules",
    ),
    "site_pre_render": (),
    "run_finish": (),
}


def stuff_traffic_contract(site_context: MutableMapping[str, Any], traffic_rows, start_date,
                           end_date) -> None:
    """Publish the site_post_traffic contract keys (CONTRACT above).  Pure dict writes,
    extracted from main() (campaign I4) so the stuffing is registry-testable -- the
    dns_classify.stuff_dns_contract precedent."""
    site_context["traffic_rows"] = traffic_rows
    site_context["start_date"] = start_date
    site_context["end_date"] = end_date


def stuff_gather_contract(site_context: MutableMapping[str, Any], framework, site_url,  # noqa: PLR0913 -- one param per site_post_gather contract key (6), matching CLAUDE.md's table; a config object would just re-wrap the same six names for one call site
                          wordpress_version, plugins, drupal_version, mods) -> None:
    """Publish the site_post_gather contract keys (CONTRACT above).  NOTE: the *_version
    values are the string "unknown" (not None) when the version fetch failed -- None only
    means "not that framework".  Only the plugins/modules keys use None for "gather
    failed"."""
    site_context["framework"] = framework
    site_context["site_url"] = site_url
    site_context["wordpress_version"] = wordpress_version
    site_context["wordpress_plugins"] = plugins if isinstance(plugins, list) else None
    site_context["drupal_version"] = drupal_version
    # NOTE: drush pm:list returns a DICT keyed by module name (unlike wp plugin list,
    # which returns a list) -- check_drupal_module requires the dict shape.
    site_context["drupal_modules"] = mods if isinstance(mods, dict) else None

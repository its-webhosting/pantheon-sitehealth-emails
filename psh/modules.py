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
    import script_context as sc  # noqa: PLC0415 -- call-time import; see the module docstring

    if not _valid_hook_name(hook_name):
        sc.console.print(f'[bold red]ERROR: add_hook: unknown phase "{hook_name}" '
                         f'(known phases: {", ".join(PHASES)}; dotted names are plugin events)')
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

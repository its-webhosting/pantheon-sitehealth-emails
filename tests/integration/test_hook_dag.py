"""Load EVERY real check/ and plugin/ package with everything enabled, then prove the
hook DAG validates -- the permanent "future changes can never make the DAG impossible"
guarantee (CAMPAIGN.md section 4).  If this test fails after you added a hook, your
declarations (or a duplicate producer) are the cause -- read psh/modules.py.

Loading mechanics reuse tests/helpers/checkload.py's probe-package pattern (the same
mechanism test_check_cloudflare_init.py / test_plugin_cloudflare_init.py use), extended
with a `base` argument so it can load plugin/ packages too, not just check/ ones -- see
checkload.load_check_package.
"""
import pytest

from helpers.checkload import load_check_package

pytestmark = pytest.mark.integration

# Enables every gate the in-repo packages read at registration time (CLAUDE.md "Plugin /
# check module system"): check/umich + plugin/umich gate on [UMich].enabled;
# check/cloudflare + plugin/cloudflare gate on [Cloudflare].enabled, and
# check/cloudflare additionally requires [Cloudflare.cachecheck].enabled +
# account_id/list_name (check/cloudflare/cfg.py's REQUIRED, presence-only at import
# time -- see plugin/umich/portal.py's docstring: the deeper portal DB config is read at
# hook RUN time, not registration, so no [UMich.portal] section is needed here).
EVERYTHING_ENABLED = {
    "UMich": {"enabled": True},
    "Cloudflare": {
        "enabled": True,
        "cachecheck": {"enabled": True, "account_id": "acct", "list_name": "egress"},
    },
}

# (base, package, probe-name) for every non-empty __init__.py under check/ and plugin/
# (find_modules()'s discovery set).  plugin.aws and plugin.env register no hooks at all
# (substitutions only -- CLAUDE.md's "Config substitutions" mechanism, not a hook) but are
# loaded anyway: the guarantee under test is "every in-repo registration surface is
# present", not "every hook-bearing package".  Probe names are distinct even where the
# check/ and plugin/ trees share a package name (both have a "cloudflare").
ALL_PACKAGES = (
    ("check", "cloudflare", "hookdag_check_cloudflare"),
    ("check", "dns", "hookdag_check_dns"),
    ("check", "pantheon_cdn_change", "hookdag_check_pantheon_cdn_change"),
    ("check", "umich", "hookdag_check_umich"),
    ("plugin", "aws", "hookdag_plugin_aws"),
    ("plugin", "cloudflare", "hookdag_plugin_cloudflare"),
    ("plugin", "env", "hookdag_plugin_env"),
    ("plugin", "umich", "hookdag_plugin_umich"),
)


def test_all_real_hooks_validate(psh, reset_sc, request):
    sc = reset_sc
    sc.config = EVERYTHING_ENABLED
    for base, package, probe in ALL_PACKAGES:
        load_check_package(psh, package, probe, request, base=base)

    import psh.modules

    psh.modules.validate_hooks()  # must not raise

    bare = {phase: [h["name"] for h in sc.hooks.get(phase, [])] for phase in sc.PHASES}
    # Edgeless today (SPEC section 6: every in-repo hook declares produces=[]): validated
    # order == registration order for every phase.
    for phase, names in bare.items():
        got = [h["name"] for h in psh.modules.ordered_hooks(sc.hooks.get(phase, []))]
        assert got == names

    # The retrofit reached everything: at least the known 11 bare+dotted registrations
    # (CAMPAIGN.md I4 SPEC section 6's table -- 2 check.cloudflare + 1 check.dns +
    # 1 check.pantheon_cdn_change + 4 check.umich + 2 plugin.cloudflare +
    # 1 plugin.umich; sc.hooks.values() also counts the dotted 'setup.umich.portal' key).
    total = sum(len(v) for v in sc.hooks.values())
    assert total >= 11

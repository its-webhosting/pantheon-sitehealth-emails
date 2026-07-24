"""The notice-code roster: every code the program can emit, registered exactly once.

Codes are registered at module import (campaign I14c, SPEC D-i14c-6), so this test loads every
check/ and plugin/ package with everything enabled -- check/umich and check/cloudflare import
their producing submodules only inside their `enabled` guards -- and compares the registry
against the frozen roster below.  A new notice code MUST be added here deliberately; a duplicate
cannot get this far, because registry.register() raises DuplicateNoticeCodeError at import.

What this pins that nothing else does (SPEC §4 instrument I4): the registration SIDE of every
code.  The csv assertions scattered through the suite pin the construction side (code= reaching
the csv row), and the two only agree because every producer builds its Notice with the
module-level NOTICE_* constant register() returned -- a bare literal at the construction site
could drift from the registered code with every test still green.

The psh/ codes (no-domains, no-primary-domain, wp-error, drush-error, the six psh/gather.py
codes, its-recommends-plan) are already registered when this test runs: psh.cli imports those
modules, and reset_sc's registry snapshot/restore preserves them across tests.

Roster arithmetic at I14c close: 12 from psh/ + 24 from check/ = 36.
"""
import pytest
from helpers.checkload import load_check_package
from test_hook_dag import ALL_PACKAGES, EVERYTHING_ENABLED

from psh.notice import registry

pytestmark = pytest.mark.integration

# Frozen roster.  Grouped by owning module so a reader can trace a code to its register() call.
ROSTER = frozenset({
    # psh/cli.py
    "no-domains", "no-primary-domain",
    # psh/gateway.py
    "wp-error", "drush-error",
    # psh/gather.py
    "not-installed", "multiple-installed", "turned-off", "composer-update",
    "wp-smell", "drush-smell", "composer-smell",
    # psh/plans.py
    "its-recommends-plan",
    # check/addon_updates/table.py
    "updates-addons",
    # check/cloudflare/notices.py
    "cloudflare-cache",
    # check/dns/notices.py
    "dns-lookup-failed", "not-in-dns", "not-behind-cloudflare",
    "behind-cloudflare-not-proxied", "proxied-in-multiple-cloudflare-zones",
    # check/drupal/d7_eol.py
    "drupal7-eol",
    # check/pantheon/
    "frozen", "no-live-env-but-paid-plan", "php-eol-warning", "php-eol-alert",
    "updates-info", "updates-warning", "updates-alert",
    # check/pantheon_cdn_change/notices.py
    "pantheon-cdn-change",
    # check/umich/
    "annual-bill", "drupal-ua", "unsupported-turned-off", "unsupported",
    "umich-oidc-login-reinstall", "sitelens-url-paths",
    # check/wordpress/
    "no-favicon", "ocp-config-fix-needed",
})


def test_roster_is_exactly_the_registered_codes(psh, reset_sc, request):
    reset_sc.config = EVERYTHING_ENABLED
    for base, package, probe in ALL_PACKAGES:
        load_check_package(psh, package, probe, request, base=base)

    codes = registry.codes()
    assert sorted(codes - ROSTER) == [], "notice codes registered but not in the roster"
    assert sorted(ROSTER - codes) == [], "roster codes that nothing registers"
    assert codes == ROSTER


def test_the_roster_is_the_documented_size():
    # The count SPEC I14c §2.4 measured and CAMPAIGN.md §11's I14c row closes on.  A code
    # added without touching this line would leave the set assertion above red anyway; this
    # is the number a reader can check against the spec without counting braces.
    assert len(ROSTER) == 36

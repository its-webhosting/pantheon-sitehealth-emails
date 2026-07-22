"""The pending add-on (plugin/theme/composer-package) updates table notice (campaign I10,
CAMPAIGN.md section 3.2, BLOCKMAP B39).  Gated by [Check.addon_updates].enabled, default
TRUE -- this notice rendered unconditionally (inline in main(), after site_post_gather)
before the relocation (section 5).

CAMPAIGN.md amendment 1 (D-i10-1): B48's smell-notice EMISSION stays in main() -- only
this table's builder moves here.  add_on_updates is the SAME list object the I9 stuffer
publishes (test_contract_registry.py pins the stuffer side); this hook reads it live."""

import script_context as sc

if sc.config.get('Check', {}).get('addon_updates', {}).get('enabled', True) is not False:
    from . import table
    sc.add_hook('site_post_gather', {'name': 'check.addon_updates.table.check_add_on_updates',
                                     'func': table.check_add_on_updates,
                                     'consumes': ['add_on_updates'],
                                     'produces': []})
else:
    sc.console.print('[bold yellow] Skipping check.addon_updates because it is disabled in the config')

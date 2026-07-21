"""Generic Pantheon site-health checks (campaign I8, CAMPAIGN.md section 3.2): frozen
site + uninitialized live environment at site_pre; unapplied upstream updates + PHP EOL
at site_post_gather (added in the same increment).  Gated by [Check.pantheon].enabled,
default TRUE -- these checks ran unconditionally before the relocation (section 5)."""

import script_context as sc

if sc.config.get('Check', {}).get('pantheon', {}).get('enabled', True) is not False:
    from . import frozen, live_env
    sc.add_hook('site_pre', {'name': 'check.pantheon.frozen.check_frozen_site',
                             'func': frozen.check_frozen_site,
                             'consumes': [], 'produces': []})
    sc.add_hook('site_pre', {'name': 'check.pantheon.live_env.check_live_env',
                             'func': live_env.check_live_env,
                             'consumes': ['envs'], 'produces': []})
else:
    sc.console.print('[bold yellow] Skipping check.pantheon because it is disabled in the config')

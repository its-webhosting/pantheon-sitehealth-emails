"""Generic WordPress site-health checks (campaign I9, CAMPAIGN.md section 3.2):
PAPC + native-PHP-sessions + OCP-config + favicon at site_post_gather.  Gated by
[Check.wordpress].enabled, default TRUE -- these checks ran unconditionally before
the relocation (section 5)."""

import script_context as sc

if sc.config.get('Check', {}).get('wordpress', {}).get('enabled', True) is not False:
    from . import favicon, ocp, papc, sessions
    sc.add_hook('site_post_gather', {'name': 'check.wordpress.papc.check_papc',
                                     'func': papc.check_papc,
                                     'consumes': ['framework', 'wordpress_plugins'],
                                     'produces': []})
    sc.add_hook('site_post_gather', {'name': 'check.wordpress.sessions.check_native_php_sessions',
                                     'func': sessions.check_native_php_sessions,
                                     'consumes': ['framework', 'wordpress_plugins'],
                                     'produces': []})
    sc.add_hook('site_post_gather', {'name': 'check.wordpress.ocp.check_ocp_config',
                                     'func': ocp.check_ocp_config,
                                     'consumes': ['framework', 'wordpress_plugins'],
                                     'produces': []})
    sc.add_hook('site_post_gather', {'name': 'check.wordpress.favicon.check_favicon',
                                     'func': favicon.check_favicon,
                                     'consumes': ['framework', 'fqdns_not_behind_cloudflare'],
                                     'produces': []})
else:
    sc.console.print('[bold yellow] Skipping check.wordpress because it is disabled in the config')

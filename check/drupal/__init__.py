"""Generic Drupal site-health checks (campaign I10, CAMPAIGN.md section 3.2): the
multisite probe at site_post_dns, PAPC-module + Drupal-7-EOL/tag1_d7es at
site_post_gather.  Gated by [Check.drupal].enabled, default TRUE -- these checks ran
unconditionally (inline in main()'s B30/B35) before the relocation (section 5).

The multisite hook is the campaign's first to declare a non-empty `produces`
(drupal_multisite/drupal_multisite_smell -- SPEC D-i10-3, CAMPAIGN.md section 4
amendment 2): DAG-declared, .get()-read keys, present only when the hook actually
probed, NOT part of the guaranteed per-phase contract."""

import script_context as sc

if sc.config.get('Check', {}).get('drupal', {}).get('enabled', True) is not False:
    from . import d7_eol, multisite, papc
    sc.add_hook('site_post_dns', {'name': 'check.drupal.multisite.check_multisite',
                                  'func': multisite.check_multisite,
                                  'consumes': ['custom_domains', 'primary_domain'],
                                  'produces': ['drupal_multisite', 'drupal_multisite_smell']})
    sc.add_hook('site_post_gather', {'name': 'check.drupal.papc.check_papc',
                                     'func': papc.check_papc,
                                     'consumes': ['framework', 'drupal_modules'],
                                     'produces': []})
    sc.add_hook('site_post_gather', {'name': 'check.drupal.d7_eol.check_d7_eol',
                                     'func': d7_eol.check_d7_eol,
                                     'consumes': ['framework', 'drupal_version', 'drupal_modules'],
                                     'produces': []})
else:
    sc.console.print('[bold yellow] Skipping check.drupal because it is disabled in the config')

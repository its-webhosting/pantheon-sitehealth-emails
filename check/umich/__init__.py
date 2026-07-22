
import script_context as sc

if 'UMich' in sc.config and 'enabled' in sc.config['UMich'] and sc.config['UMich']['enabled']:
    from .cloudflare_cms import check_cloudflare_cms_integrations
    from .drupal_ua import check_drupal_ua
    from .hummingbird import check_hummingbird_fork
    from .oidc_login import check_oidc_login
    from .sitelens import check_sitelens_scores, check_sitelens_urls, setup_sitelens
    sc.add_hook('setup.umich.portal', {'name': 'check.umich.sitelens.setup_sitelens', 'func': setup_sitelens,
                                       'consumes': [], 'produces': []})
    sc.add_hook('site_pre', {'name': 'check.umich.sitelens.check_sitelens_urls', 'func': check_sitelens_urls,
                             'consumes': [], 'produces': []})
    sc.add_hook('site_pre', {'name': 'check.umich.sitelens.check_sitelens_scores', 'func': check_sitelens_scores,
                             'consumes': [], 'produces': []})
    sc.add_hook('site_post_gather', {'name': 'check.umich.cloudflare_cms.check_cloudflare_cms_integrations',
                                     'func': check_cloudflare_cms_integrations,
                                     'consumes': ['fqdns_behind_cloudflare', 'framework',
                                                  'wordpress_plugins', 'drupal_version',
                                                  'drupal_modules'],
                                     'produces': []})
    sc.add_hook('site_post_gather', {'name': 'check.umich.oidc_login.check_oidc_login',
                                     'func': check_oidc_login,
                                     'consumes': ['framework', 'wordpress_plugins'],
                                     'produces': []})
    sc.add_hook('site_post_gather', {'name': 'check.umich.hummingbird.check_hummingbird_fork',
                                     'func': check_hummingbird_fork,
                                     'consumes': ['framework', 'wordpress_plugins'],
                                     'produces': []})
    sc.add_hook('site_post_gather', {'name': 'check.umich.drupal_ua.check_drupal_ua',
                                     'func': check_drupal_ua,
                                     'consumes': ['framework', 'drupal_version'],
                                     'produces': []})
else:
    sc.console.print('[bold yellow] Skipping check.umich.sitelens because UMich plugin is not enabled')

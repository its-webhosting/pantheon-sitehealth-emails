
import script_context as sc


if 'UMich' in sc.config and 'enabled' in sc.config['UMich'] and sc.config['UMich']['enabled']:
    from .sitelens import setup_sitelens, check_sitelens_urls, check_sitelens_scores
    sc.add_hook('setup.umich.portal', {'name': 'check.umich.sitelens.setup_sitelens', 'func': setup_sitelens})
    sc.add_hook('check', {'name': 'check.umich.sitelens.check_sitelens_urls', 'func': check_sitelens_urls})
    sc.add_hook('check', {'name': 'check.umich.sitelens.check_sitelens_scores', 'func': check_sitelens_scores})
else:
    sc.console('[bold yellow] Skipping check.umich.sitelens because UMich plugin is not enabled')

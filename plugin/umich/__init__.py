
import script_context as sc


if 'UMich' in sc.config and 'enabled' in sc.config['UMich'] and sc.config['UMich']['enabled']:
    from .portal import setup_portal_db, plan_info
    sc.hooks['setup'].append({ 'name': 'plugin.umich.portal.setup_portal_db', 'func': setup_portal_db})
    sc.substitutions.append({
        'args': ['umich', 'portal', 'plan_info', '$plan', '$field'],
        'func': plan_info,
        'func_args': ['$plan', '$field']
    })

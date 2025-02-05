
import os

import script_context as sc


if 'AWS' in sc.config and 'enabled' in sc.config['AWS'] and sc.config['AWS']['enabled']:

    # set the following for boto to use
    if os.getenv('AWS_PROFILE') is None and 'profile' in sc.config['AWS']:
        os.environ['AWS_PROFILE'] = sc.config['AWS']['profile']
    if os.getenv('AWS_DEFAULT_REGION') is None and 'default_region' in sc.config['AWS']:
        os.environ['AWS_DEFAULT_REGION'] = sc.config['AWS']['default_region']

    from .get_secret import get_secret
    sc.substitutions.append({
        'args': ['secret', 'aws', '$name', '$key'],
        'func': get_secret,
        'func_args': ['$name', '$key']
    })


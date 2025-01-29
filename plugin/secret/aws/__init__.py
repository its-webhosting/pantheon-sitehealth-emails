
import os

import script_context

if 'AWS' in script_context.config and 'enabled' in script_context.config['AWS'] and script_context.config['AWS']['enabled']:

    # set the following for boto to use
    if os.getenv('AWS_PROFILE') is None and 'profile' in script_context.config['AWS']:
        os.environ['AWS_PROFILE'] = script_context.config['AWS']['profile']
    if os.getenv('AWS_DEFAULT_REGION') is None and 'default_region' in script_context.config['AWS']:
        os.environ['AWS_DEFAULT_REGION'] = script_context.config['AWS']['default_region']

    from .get_secret import get_secret


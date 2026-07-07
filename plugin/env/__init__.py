import script_context as sc

from .get_env import get_env


# The `env` substitution has no external dependency and is needed by core [SMTP] config
# (e.g. username = "<{env USER}"), so it is registered unconditionally rather than gated on an
# `enabled` flag -- gating it would create a chicken-and-egg problem (a disabled [Env] would
# break every <{env ...}> in the file).  This is a deliberate exception to the plugin
# enable-flag convention.
#
# Order matters: the 2-argument (no-default) pattern must be registered BEFORE its 3-argument
# ($default) counterpart, so the best-match engine's perfect-match short-circuit binds
# "<{env NAME}" to the no-default form.  If the 3-arg pattern came first, "<{env NAME}" would
# match it (score == argc, but not a perfect-length match, so no short-circuit) and then
# KeyError on the uncaptured $default.  See config_substitution() and SPEC section 4.5.
sc.substitutions.append({'args': ['env', '$name'],
                         'func': get_env, 'func_args': ['$name']})
sc.substitutions.append({'args': ['env', '$name', '$default'],
                         'func': get_env, 'func_args': ['$name', '$default']})
sc.substitutions.append({'args': ['secret', 'env', '$name'],
                         'func': get_env, 'func_args': ['$name']})
sc.substitutions.append({'args': ['secret', 'env', '$name', '$default'],
                         'func': get_env, 'func_args': ['$name', '$default']})

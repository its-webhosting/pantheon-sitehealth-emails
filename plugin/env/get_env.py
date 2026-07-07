import os

import script_context as sc


_UNSET = object()  # distinguishes "no default supplied" from an empty-string default


def get_env(name, default=_UNSET):
    """Return the value of environment variable `name` for a config substitution.

    An env var that is set but empty returns "" (set != unset).  If the var is unset:
    return `default` when one was supplied (the optional trailing argument of the
    <{env ...}> / <{secret env ...}> forms), else raise ConfigSubstitutionError so the
    framework aborts with a config-path-annotated message (see config_substitution).
    """
    if name in os.environ:
        return os.environ[name]
    if default is not _UNSET:
        return default
    raise sc.ConfigSubstitutionError(f"environment variable '{name}' is not set")

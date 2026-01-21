# The contents of this file are subject to the Common Public Attribution
# License Version 1.0. (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://code.reddit.com/LICENSE. The License is based on the Mozilla Public
# License Version 1.1, but Sections 14 and 15 have been added to cover use of
# software over a computer network and provide for limited attribution for the
# Original Developer. In addition, Exhibit A has been modified to be consistent
# with Exhibit B.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is reddit.
#
# The Original Developer is the Initial Developer.  The Initial Developer of
# the Original Code is reddit Inc.
#
# All portions of the code written by reddit are Copyright (c) 2006-2015 reddit
# Inc. All Rights Reserved.
###############################################################################

"""r2

This file loads the finished app from r2.config.middleware.
"""

# _strptime is imported with PyImport_ImportModuleNoBlock which can fail
# miserably when multiple threads try to import it simultaneously.
# import this here to get it over with
# see "Non Blocking Module Imports" in:
# http://code.google.com/p/modwsgi/wiki/ApplicationIssues
import _strptime
import sys
import types

# Provide a shim for old `boto.vendored.six` and `boto.vendored.six.moves`
# imports. Legacy boto expects several names exported from a vendored six
# package (e.g. `moves`, `BytesIO`, `StringIO`, `ConfigParser`, etc.).
# Map those to modern stdlib / `six` equivalents so boto can import on
# Python 3 without modifying site packages.
try:
    import six
    import io
    import os
    import configparser

    mod = sys.modules.setdefault('boto.vendored.six', types.ModuleType('boto.vendored.six'))
    # Copy important attributes from the real `six` module so checks like
    # `six.PY3` and type aliases work when boto inspects the vendored module.
    copy_names = [
        'PY2', 'PY3', 'string_types', 'text_type', 'binary_type',
        'integer_types', 'iteritems', 'iterkeys', 'itervalues',
        'BytesIO', 'StringIO', 'u', 'b', 'moves',
    ]
    for name in copy_names:
        try:
            if hasattr(six, name):
                setattr(mod, name, getattr(six, name))
        except Exception:
            pass

    # IO helpers used by boto.compat
    try:
        setattr(mod, 'BytesIO', io.BytesIO)
    except Exception:
        pass
    try:
        setattr(mod, 'StringIO', io.StringIO)
    except Exception:
        pass

    # Config helpers expected by boto.compat
    try:
        setattr(mod, 'ConfigParser', configparser.ConfigParser)
        setattr(mod, 'NoOptionError', configparser.NoOptionError)
        setattr(mod, 'NoSectionError', configparser.NoSectionError)
    except Exception:
        pass

    # small utilities
    try:
        setattr(mod, 'expanduser', os.path.expanduser)
    except Exception:
        pass

    # Also map the moves module into sys.modules so `from boto.vendored.six.moves import ...`
    # works as expected.
    sys.modules.setdefault('boto.vendored.six.moves', six.moves)
    # Register a few common submodules under the legacy dotted names so
    # imports like `boto.vendored.six.moves.queue` resolve to the real
    # modules from the stdlib / six.moves.
    common_subs = [
        'queue',
        'urllib',
        'urllib.request',
        'urllib.parse',
        'http_client',
        '_thread',
        'thread',
    ]
    for sub in common_subs:
        try:
            # resolve attribute path on six.moves (e.g. six.moves.urllib.request)
            parts = sub.split('.')
            obj = six.moves
            for p in parts:
                obj = getattr(obj, p)
            sys.modules.setdefault(f'boto.vendored.six.moves.{sub}', obj)
        except Exception:
            # ignore any missing attributes â€” they'll error later if actually used
            pass
except Exception:
    # If anything goes wrong, don't break import-time; errors will surface
    # later when boto is actually used.
    pass


# defer the (hefty) import until it's actually needed. this allows
# modules below r2 to be imported before cython files are built, also
# provides a hefty speed boost to said imports when they don't need
# the app initialization.
def make_app(*args, **kwargs):
    from r2.config.middleware import make_app as real_make_app
    return real_make_app(*args, **kwargs)

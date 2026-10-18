# The contents of this file are subject to the Common Public Attribution
# License Version 1.0 (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# https://github.com/TechIdiots-LLC/tippr/blob/master/LICENSE.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is Tippr.
#
# The Initial Developer of the Original Code is TechIdiots LLC.
# Copyright (c) 2026 TechIdiots LLC. All Rights Reserved.
###############################################################################

"""Pylons util compatibility shim.

Provides minimal implementations of ContextObj, AttribSafeContextObj, and
PylonsContext for code that imports from pylons.util.
"""
from types import SimpleNamespace


class ContextObj(SimpleNamespace):
    """A simple namespace object that acts as a context container.

    This is a minimal shim for the original Pylons ContextObj.
    """
    pass


class AttribSafeContextObj(ContextObj):
    """A ContextObj that returns None for missing attributes instead of raising.

    This is useful for template contexts where missing attributes should
    gracefully return None.
    """

    def __getattr__(self, name):
        try:
            return super().__getattribute__(name)
        except AttributeError:
            return None


class PylonsContext:
    """Minimal shim for PylonsContext.

    In original Pylons, this held references to the request, response,
    tmpl_context, etc. This shim provides a simple container.
    """

    def __init__(self):
        self.request = None
        self.response = None
        self.tmpl_context = None
        self.app_globals = None
        self.config = None
        self.translator = None
        self.url = None

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)

    def __getattr__(self, name):
        try:
            return object.__getattribute__(self, name)
        except AttributeError:
            return None


__all__ = ['ContextObj', 'AttribSafeContextObj', 'PylonsContext']

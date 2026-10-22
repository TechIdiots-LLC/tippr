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

"""Minimal Pylons compatibility shim for tests and progressive migration.

Provides simple LocalStack objects for `config`, `app_globals`, `tmpl_context`, and
`translator`, and a small url pushable object. This is intentionally lightweight
and intended to be replaced by Pyramid-specific code during migration.
"""
import threading
from typing import Any, List
from types import SimpleNamespace

from .configuration import PylonsConfig


# Per-thread request bookkeeping. paster serves requests from a thread pool,
# so anything pushed while handling a request (request, response, c, the
# translator, ...) must only be visible to that thread. Objects pushed outside
# a request (config, app_globals and the defaults below, at startup) are shared
# by every thread.
_request_state = threading.local()


def _begin_request():
    """Start a request on this thread: pushes from now on are thread-local.

    Nested calls (an app re-entered for an include or an error page while a
    request is running) keep the outer request's objects.
    """
    depth = getattr(_request_state, 'depth', 0)
    if depth == 0:
        # a new generation makes every stack start this request empty
        _request_state.generation = getattr(_request_state, 'generation', 0) + 1
    _request_state.depth = depth + 1


def _end_request():
    """End the request started by the matching _begin_request()."""
    depth = getattr(_request_state, 'depth', 0)
    if depth > 0:
        _request_state.depth = depth - 1


class _ThreadAwareStack:
    """Storage shared by LocalStack and UrlPushable.

    Outside a request, pushes and pops act on a process-wide base stack. During
    a request (see _begin_request) they act on a per-thread layer above it,
    which starts empty each request, so concurrent requests can't see or pop
    each other's objects.
    """

    def __init__(self):
        object.__setattr__(self, '_base', [])
        object.__setattr__(self, '_local', threading.local())

    def _layer(self):
        """This request's thread-local list, or None outside a request."""
        if getattr(_request_state, 'depth', 0) <= 0:
            return None
        local = self._local
        if getattr(local, 'generation', None) != _request_state.generation:
            local.items = []
            local.generation = _request_state.generation
        return local.items

    @property
    def _stack(self) -> List[Any]:
        """The objects visible to this thread, bottom to top.

        Outside a request this is the shared base list itself; during a request
        it is a copy (base plus this request's objects), so read it, don't
        modify it.
        """
        layer = self._layer()
        if layer is None:
            return self._base
        return self._base + layer

    @_stack.setter
    def _stack(self, value) -> None:
        object.__setattr__(self, '_base', list(value))

    def _top(self):
        layer = self._layer()
        if layer:
            return True, layer[-1]
        if self._base:
            return True, self._base[-1]
        return False, None

    def _push_object(self, obj: Any) -> None:
        layer = self._layer()
        (self._base if layer is None else layer).append(obj)

    # Accept an optional `obj` argument for compatibility with some
    # Paste versions that call `_pop_object(obj)`.
    def _pop_object(self, obj: Any = None) -> Any:
        layer = self._layer()
        if layer is None:
            return self._base.pop()
        # never let a request pop the shared objects underneath it
        return layer.pop() if layer else None


class LocalStack(_ThreadAwareStack):
    """A tiny stack-like holder that forwards attribute and item access to the
    currently pushed object.
    """

    def _current_obj(self) -> Any:
        """The object currently pushed (Pylons' StackedObjectProxy API)."""
        found, top = self._top()
        if not found:
            raise TypeError("no object pushed to LocalStack")
        return top

    def __getattr__(self, name: str) -> Any:
        found, top = self._top()
        if not found:
            raise AttributeError(f"no object pushed to LocalStack (requested {name})")
        return getattr(top, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in ('_stack', '_base', '_local'):
            # internal attributes (``_stack`` goes through its property)
            object.__setattr__(self, name, value)
            return
        found, top = self._top()
        if found:
            # Forward attribute setting to the top of the stack
            setattr(top, name, value)
        else:
            raise AttributeError(f"no object pushed to LocalStack (cannot set {name})")

    def get(self, key, default=None):
        found, top = self._top()
        if not found:
            return default
        try:
            return top.get(key, default)
        except Exception:
            return getattr(top, key, default)

    def __getitem__(self, key):
        found, top = self._top()
        if not found:
            raise KeyError(key)
        return top[key]

    def __bool__(self):
        return self._top()[0]


class UrlPushable(_ThreadAwareStack):
    """Holds a pushed URL generator (e.g. routes.util.URLGenerator).

    Only minimal API is implemented (_push_object/_pop_object). If code calls
    `url_for` on this object it will attempt to call a known method on the
    underlying generator.
    """

    def _get_current(self):
        return self._top()[1]

    def url_for(self, *args, **kwargs):
        gen = self._get_current()
        if gen is None:
            raise RuntimeError("no URL generator pushed")
        # routes.util.URLGenerator exposes a ``generate`` method; accept either
        # a callable or a generate attribute
        if hasattr(gen, 'generate'):
            return gen.generate(*args, **kwargs)
        if callable(gen):
            return gen(*args, **kwargs)
        raise RuntimeError("pushed URL generator is not callable/generate")


# Module-level instances expected by code/tests
config = LocalStack()
app_globals = LocalStack()
tmpl_context = LocalStack()
translator = LocalStack()
url = UrlPushable()
request = LocalStack()
response = LocalStack()


# Backwards-compatible aliases (sometimes code imports ``from pylons import g``)
g = app_globals
c = tmpl_context

# Push sensible defaults so tests and code that expect a current config/globals
# don't fail with "no object pushed to LocalStack". Tests can still push
# their own objects and pop them when needed.
class _DefaultTranslator:
    def gettext(self, s):
        return s

    def ngettext(self, s, p, n):
        return s if n == 1 else p

    def __call__(self, s):
        return s


class _DefaultRequest(SimpleNamespace):
    def __init__(self):
        super().__init__()
        self.environ = {}
        self.GET = {}
        self.POST = {}
        self.host = ''
        self.path = ''
        self.remote_addr = ''


class _DefaultResponse(SimpleNamespace):
    def __init__(self):
        super().__init__()
        self.headers = {}
        self.status = 200
        self.content = []
        self.charset = 'utf-8'
        self.content_type = 'text/html'


class _DefaultTmplContext(SimpleNamespace):
    def __init__(self):
        super().__init__()
        # commonly referenced flags/attributes in templates/tests
        self.have_sent_bucketing_event = False
        self.subdomain = None
        self.user = None
        self.have_messages = False
        self.have_mod_messages = False
        self.show_signing_body = False
        self.render_tracker = None  # Must be None or dict, not '' for wrapped.pyx
        self.render_style = 'html'
        self.site = None
        self.firsttime = None
        self.cookies = {}
        self.user_is_loggedin = False
        self.user_is_admin = False
        self.domain_prefix = ''
        self.secure = False
        self.lang = 'en'

    def __getattr__(self, name):
        # Pylons tmpl_context returns empty string for missing attributes
        # This allows code like `c.render_tracker` to work without raising AttributeError
        return ''


# Do not push a default `PylonsConfig` object so that `bool(pylons.config)` is
# initially False — tests expect no object pushed at import time. Tests that
# need a config can push one explicitly via `_push_object`.
app_globals._push_object(SimpleNamespace())
tmpl_context._push_object(_DefaultTmplContext())
translator._push_object(_DefaultTranslator())
request._push_object(_DefaultRequest())
response._push_object(_DefaultResponse())


__all__ = [
    'config', 'app_globals', 'tmpl_context', 'translator', 'url', 'g', 'c',
    'request', 'response', 'LocalStack', 'UrlPushable',
]

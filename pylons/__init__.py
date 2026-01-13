"""Minimal Pylons compatibility shim for tests and progressive migration.

Provides simple LocalStack objects for `config`, `app_globals`, `tmpl_context`, and
`translator`, and a small url pushable object. This is intentionally lightweight
and intended to be replaced by Pyramid-specific code during migration.
"""
from typing import Any, List
from types import SimpleNamespace

from .configuration import PylonsConfig


class LocalStack:
    """A tiny stack-like holder that forwards attribute and item access to the
    currently pushed object.
    """

    def __init__(self):
        self._stack: List[Any] = []

    def _push_object(self, obj: Any) -> None:
        self._stack.append(obj)
    # Accept an optional `obj` argument for compatibility with some
    # Paste versions that call `_pop_object(obj)`.
    def _pop_object(self, obj: Any = None) -> Any:
        return self._stack.pop()

    def __getattr__(self, name: str) -> Any:
        if not self._stack:
            raise AttributeError(f"no object pushed to LocalStack (requested {name})")
        return getattr(self._stack[-1], name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == '_stack':
            # Allow setting the internal _stack attribute
            object.__setattr__(self, name, value)
        elif self._stack:
            # Forward attribute setting to the top of the stack
            setattr(self._stack[-1], name, value)
        else:
            raise AttributeError(f"no object pushed to LocalStack (cannot set {name})")

    def get(self, key, default=None):
        if not self._stack:
            return default
        top = self._stack[-1]
        try:
            return top.get(key, default)
        except Exception:
            return getattr(top, key, default)

    def __getitem__(self, key):
        if not self._stack:
            raise KeyError(key)
        return self._stack[-1][key]

    def __bool__(self):
        return bool(self._stack)


class UrlPushable:
    """Holds a pushed URL generator (e.g. routes.util.URLGenerator).

    Only minimal API is implemented (_push_object/_pop_object). If code calls
    `url_for` on this object it will attempt to call a known method on the
    underlying generator.
    """

    def __init__(self):
        self._stack: List[Any] = []

    def _push_object(self, obj: Any) -> None:
        self._stack.append(obj)
    # Accept an optional `obj` argument for compatibility with some
    # Paste versions that call `_pop_object(obj)`.
    def _pop_object(self, obj: Any = None) -> Any:
        return self._stack.pop()

    def _get_current(self):
        if not self._stack:
            return None
        return self._stack[-1]

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

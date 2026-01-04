"""Compatibility layer for `pylons.wsgiapp`.

Provides a lightweight `PylonsApp` fallback that establishes the
minimal objects expected by `r2` middleware for migration to Pyramid.
"""
import traceback
from types import SimpleNamespace
from importlib import import_module
from webob import Request as WebObRequest, Response as WebObResponse
import pylons


class PylonsResponse(WebObResponse):
    """WebOb Response with Pylons-compatible `content` property.

    Old Pylons Response had a `content` property that was a list of strings.
    WebOb uses `body` (bytes) or `text` (unicode) instead.
    This wrapper provides the `content` property for backwards compatibility.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._content_list = []

    @property
    def content(self):
        """Get the response content as a list (Pylons compatibility)."""
        # If we have stored content, return it
        if self._content_list:
            return self._content_list
        # Otherwise, try to get from body
        if self.body:
            # Return as a list containing the body
            try:
                return [self.body.decode(self.charset or 'utf-8')]
            except (UnicodeDecodeError, AttributeError):
                return [self.body]
        return []

    @content.setter
    def content(self, value):
        """Set the response content (Pylons compatibility)."""
        if isinstance(value, (list, tuple)):
            self._content_list = list(value)
            # Also set the body for WebOb compatibility
            joined = ''.join(str(v) for v in value)
            if isinstance(joined, str):
                self.text = joined
            else:
                self.body = joined
        elif isinstance(value, str):
            self._content_list = [value]
            self.text = value
        elif isinstance(value, bytes):
            self._content_list = [value]
            self.body = value
        else:
            self._content_list = [value]
            self.text = str(value)


class _DefaultTranslator:
    """Minimal translator that returns strings unchanged."""
    def gettext(self, s):
        return s

    def ngettext(self, s, p, n):
        return s if n == 1 else p

    def __call__(self, s):
        return s


class _DefaultTmplContext(SimpleNamespace):
    """Default template context with common attributes."""
    def __init__(self):
        super().__init__()
        self.have_sent_bucketing_event = False
        self.subdomain = None
        self.user = None


class PylonsApp:
    """A very small PylonsApp polyfill.

    It intentionally implements only the bits `r2` expects: construction
    with a `config` mapping and a `setup_app_env` hook that places a
    minimal `pylons.pylons` object into the WSGI `environ`.
    """

    def __init__(self, config=None, **kwargs):
        self.config = config or {}
        self.package_name = self.config.get('pylons.package')
        self.helpers = self.config.get('pylons.h')
        self.globals = self.config.get('pylons.app_globals')
        self.environ_config = self.config.get('pylons.environ_config', {})
        self.request_options = self.config.get('pylons.request_options', {})
        self.response_options = self.config.get('pylons.response_options', {})
        self.controller_classes = {}

    def setup_app_env(self, environ, start_response):
        # Provide a minimal pylons.pylons-style object expected by code
        pylons_obj = SimpleNamespace()
        pylons_obj.config = self.config
        pylons_obj.app_globals = self.globals
        pylons_obj.h = self.helpers
        pylons_obj.tmpl_context = _DefaultTmplContext()
        pylons_obj.translator = _DefaultTranslator()

        # Create real WebOb request/response objects and push them onto
        # pylons' LocalStack objects so controllers and helpers can use
        # `from pylons import request, response` as expected.
        request_obj = WebObRequest(environ)
        response_obj = PylonsResponse()

        pylons.request._push_object(request_obj)
        pylons.response._push_object(response_obj)
        pylons.tmpl_context._push_object(pylons_obj.tmpl_context)
        pylons.translator._push_object(pylons_obj.translator)
        # Push the app globals so `from pylons import g` works
        if self.globals is not None:
            pylons.app_globals._push_object(self.globals)

        environ['pylons.pylons'] = pylons_obj
        environ['pylons.environ_config'] = self.environ_config

    def __call__(self, environ, start_response):
        # Ensure environment is prepared (push request/response, tmpl context)
        try:
            self.setup_app_env(environ, start_response)
        except Exception as e:
            tb = traceback.format_exc()
            start_response('500 Internal Server Error', [('Content-Type', 'text/plain')])
            return [f"Setup error: {e}\n\n{tb}".encode('utf-8')]

        # RoutesMiddleware (or other routing) places routing args here.
        routing = environ.get('wsgiorg.routing_args')
        if routing:
            environ['pylons.routes_dict'] = routing[1]

        routes_dict = environ.get('pylons.routes_dict', {})
        controller_name = routes_dict.get('controller')

        if not controller_name:
            start_response('404 Not Found', [('Content-Type', 'text/plain')])
            return [b'Not Found']

        # Try to resolve the controller class and call it as a WSGI app.
        controller_cls = None
        # Prefer a find_controller hook if the app implements it (TipprApp)
        find_fn = getattr(self, 'find_controller', None)
        if callable(find_fn):
            try:
                controller_cls = find_fn(controller_name)
            except Exception:
                controller_cls = None

        if controller_cls is None:
            try:
                controllers_mod = import_module(self.package_name + '.controllers')
                controller_cls = controllers_mod.get_controller(controller_name)
            except Exception:
                controller_cls = None

        if controller_cls is None:
            start_response('404 Not Found', [('Content-Type', 'text/plain')])
            return [b'Not Found']

        try:
            # Instantiate and call the controller (WSGIController subclass).
            controller = controller_cls()
            resp_iter = controller(environ, start_response)

            # Ensure pushed pylons locals are popped when the response is
            # finished or the iterator is closed.
            def closing_iterator(it):
                try:
                    for chunk in it:
                        yield chunk
                finally:
                    try:
                        pylons.request._pop_object()
                    except Exception:
                        pass
                    try:
                        pylons.response._pop_object()
                    except Exception:
                        pass
                    try:
                        pylons.tmpl_context._pop_object()
                    except Exception:
                        pass
                    try:
                        pylons.translator._pop_object()
                    except Exception:
                        pass
                    try:
                        pylons.app_globals._pop_object()
                    except Exception:
                        pass

            return closing_iterator(resp_iter)
        except Exception as e:
            tb = traceback.format_exc()
            start_response('500 Internal Server Error', [('Content-Type', 'text/plain')])
            return [f"Error: {e}\n\n{tb}".encode('utf-8')]


__all__ = ['PylonsApp']

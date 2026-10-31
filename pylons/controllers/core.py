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

# Pylons controllers.core compatibility shim
# Provides the WSGIController base class r2's controllers build on

import inspect
import logging

from paste.deploy.converters import asbool
from webob import Response
from webob.exc import HTTPException
import pylons

log = logging.getLogger(__name__)


class WSGIController:
    """A WSGI Controller base class.

    This is a compatibility shim that mimics the behavior of the original
    Pylons WSGIController. It:
    1. Calls __before__() before the action
    2. Dispatches to the action method based on environ['pylons.routes_dict']['action']
    3. Calls __after__() after the action
    4. Returns a WSGI response
    """

    def __before__(self):
        """Called before the action method. Override in subclasses."""
        pass

    def __after__(self):
        """Called after the action method. Override in subclasses."""
        pass

    def __call__(self, environ, start_response):
        """WSGI interface - dispatch to the appropriate action."""
        try:
            return self._call(environ, start_response)
        except HTTPException as e:
            # An abort (from __before__ or the action). As Pylons did,
            # __after__ still runs, with the response marked as an exception
            # (r2's post() reads response._exception), and what it put on the
            # response goes on the error's: the security headers, cookies,
            # Cache-Control. (It used to be returned as it was, without them.)
            environ['pylons.controller.exception'] = e
            current = _current_response()
            if current is not None:
                try:
                    current._exception = True
                except Exception:
                    pass
            try:
                self.__after__()
            except HTTPException:
                pass
            except Exception:
                log.exception("__after__ failed for %s %s",
                              environ.get('REQUEST_METHOD'),
                              environ.get('PATH_INFO'))
            if current is not None and current is not e:
                _copy_headers(current, e)
            if e.status_int == 304:
                # (no body, so no content type)
                e.headers.pop('Content-Type', None)
            return e(environ, start_response)

    def _call(self, environ, start_response):
        try:
            # Call __before__ hook
            self.__before__()

            # Get the action from the routes dict
            routes_dict = environ.get('pylons.routes_dict', {})
            action_name = routes_dict.get('action')

            if not action_name:
                start_response('404 Not Found', [('Content-Type', 'text/plain')])
                return [b'Action not found']

            # Get the action method
            action = getattr(self, action_name, None)
            if action is None:
                start_response('404 Not Found', [('Content-Type', 'text/plain')])
                return [f'Action {action_name} not found'.encode('utf-8')]

            # Call the action with the route variables it names, as Pylons
            # did (e.g. GET_user_redirect(self, username, rest=None)).
            # Actions wrapped by r2's validators take **kw and read the
            # routes dict themselves.
            result = action(**_route_args(action, routes_dict))

            # What the action returned is the response body before __after__
            # runs, as in Pylons: post() works on it (the admin bar's
            # timings, the .js wrapper)
            if result is not None:
                if isinstance(result, bytes):
                    pylons.response.body = result
                elif isinstance(result, str):
                    pylons.response.text = result

            # Call __after__ hook
            self.__after__()

            # Handle the response. `pylons.response` may be a proxy
            # exposing `_current_obj()`, or a plain `Response` instance,
            # or our `LocalStack` wrapper. Normalize to a real
            # `webob.Response` instance so we can call it as a WSGI app.
            if hasattr(pylons.response, '_current_obj'):
                response = pylons.response._current_obj()
            elif hasattr(pylons.response, '_stack') and pylons.response._stack:
                # LocalStack - get the top object from the stack
                response = pylons.response._stack[-1]
            else:
                response = pylons.response

            # If we didn't get a callable WSGI response (for example, the
            # test shim uses a `LocalStack` whose top is a simple namespace),
            # construct a `webob.Response` from the available attributes.
            if not callable(response):
                r = Response()
                # copy status and headers if present
                if hasattr(response, 'status'):
                    try:
                        r.status = str(response.status)
                    except Exception:
                        pass
                if hasattr(response, 'headers') and isinstance(response.headers, dict):
                    r.headers.update(response.headers)
                # Copy cookies if present (critical for login!)
                if hasattr(response, 'headerlist'):
                    for name, value in response.headerlist:
                        if name.lower() == 'set-cookie':
                            r.headers.add('Set-Cookie', value)
                # prefer explicit body/text attributes if present
                if hasattr(response, 'body'):
                    r.body = getattr(response, 'body')
                elif hasattr(response, 'text'):
                    r.text = getattr(response, 'text')
                elif hasattr(response, 'content'):
                    r.body = getattr(response, 'content')
                response = r

            # Return the WSGI response
            return response(environ, start_response)

        except HTTPException:
            # (__call__ runs __after__ and returns it)
            raise

        except Exception as e:
            # Log every unhandled error (to the service's journal); the error
            # middleware then shows the 500 page. Only debug mode puts the
            # traceback in the response.
            log.exception("Error handling %s %s", environ.get('REQUEST_METHOD'),
                          environ.get('PATH_INFO'))
            hook = getattr(self, 'on_unhandled_error', None)
            if hook is not None:
                try:
                    hook(e)
                except Exception:
                    log.exception("on_unhandled_error failed")
            start_response('500 Internal Server Error', [('Content-Type', 'text/plain')])
            try:
                debug = asbool(pylons.config.get('debug'))
            except Exception:
                debug = False
            if debug:
                import traceback
                return [f'Controller error: {e}\n\n{traceback.format_exc()}'.encode('utf-8')]
            return [b'Internal Server Error']


def _current_response():
    """The request's response object (pylons.response's current one)."""
    try:
        if hasattr(pylons.response, '_current_obj'):
            return pylons.response._current_obj()
    except Exception:
        return None
    return None


def _copy_headers(source, exc):
    """Put what __after__ set on the response onto the error being
    returned instead, as Pylons did: every cookie, and each other header
    the error doesn't set itself."""
    for name, value in getattr(source, 'headerlist', []):
        lower = name.lower()
        if lower == 'set-cookie':
            exc.headers.add(name, value)
        elif lower in ('content-type', 'content-length'):
            continue
        elif name not in exc.headers:
            exc.headers[name] = value


def _route_args(action, routes_dict):
    try:
        params = inspect.signature(action).parameters
    except (TypeError, ValueError):
        return {}
    return {name: routes_dict[name] for name, param in params.items()
            if name in routes_dict
            and name not in ('controller', 'action')
            and param.kind in (param.POSITIONAL_OR_KEYWORD,
                               param.KEYWORD_ONLY)}


__all__ = ['WSGIController']

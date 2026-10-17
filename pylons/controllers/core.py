# Pylons controllers.core compatibility shim
# Provides WSGIController base class for Pyramid migration

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

            # Call the action
            result = action()

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

            # If action returned something, use it as body
            if result is not None:
                if isinstance(result, bytes):
                    response.body = result
                elif isinstance(result, str):
                    response.text = result

            # Return the WSGI response
            return response(environ, start_response)

        except HTTPException as e:
            # HTTP exceptions are valid responses (redirects, errors, etc.)
            return e(environ, start_response)

        except Exception as e:
            # Log every unhandled error (to the service's journal); the error
            # middleware then shows the 500 page. Only debug mode puts the
            # traceback in the response.
            log.exception("Error handling %s %s", environ.get('REQUEST_METHOD'),
                          environ.get('PATH_INFO'))
            start_response('500 Internal Server Error', [('Content-Type', 'text/plain')])
            try:
                debug = asbool(pylons.config.get('debug'))
            except Exception:
                debug = False
            if debug:
                import traceback
                return [f'Controller error: {e}\n\n{traceback.format_exc()}'.encode('utf-8')]
            return [b'Internal Server Error']


__all__ = ['WSGIController']

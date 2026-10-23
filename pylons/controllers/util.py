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

# Pylons controllers.util compatibility shim
# Provides abort() and redirect() functions using webob.exc

from webob import exc as webob_exc


def abort(status_code, detail=None, headers=None, comment=None):
    """Abort the request with an HTTP error.

    This is a compatibility shim for pylons.controllers.util.abort
    that uses webob.exc exceptions. Like r2.lib.base.abort, it keeps the
    exception in environ['r2.controller.exception'], where the error page
    reads its explanation (the validators' 403s and 404s lost it).
    """
    exc_class = webob_exc.status_map.get(status_code,
                                         webob_exc.HTTPInternalServerError)

    kwargs = {}
    if detail:
        kwargs['detail'] = detail
    if comment:
        kwargs['comment'] = comment

    exc = exc_class(**kwargs)

    if headers:
        for header in headers:
            if isinstance(header, tuple) and len(header) == 2:
                exc.headers.add(header[0], header[1])

    try:
        import pylons
        pylons.request.environ['r2.controller.exception'] = exc
    except Exception:
        # (no request: a script)
        pass

    raise exc


def redirect(url, code=302):
    """Redirect to a URL.

    This is a compatibility shim for pylons.controllers.util.redirect
    that uses webob.exc exceptions.
    """
    if code == 301:
        raise webob_exc.HTTPMovedPermanently(location=url)
    elif code == 303:
        raise webob_exc.HTTPSeeOther(location=url)
    elif code == 307:
        raise webob_exc.HTTPTemporaryRedirect(location=url)
    else:
        raise webob_exc.HTTPFound(location=url)

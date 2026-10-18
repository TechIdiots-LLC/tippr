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

"""Compatibility layer for `pylons.middleware`.

Provides minimal fallback implementations for middleware components
that were previously provided by Pylons, to support migration to Pyramid.
"""
from webob import Response


def ErrorHandler(app, global_conf, **errorware):
    """No-op error handler for environments where WebError / EvalException
    are not available. Simply returns the wrapped app unchanged.

    In production, error handling should be done via Pyramid's exception
    views or other WSGI middleware.
    """
    return app


class StatusCodeRedirect:
    """Minimal status code redirect middleware stub."""

    def __init__(self, app, errors=(400, 401, 403, 404), path='/error/document'):
        self.app = app
        self.error_path = path

    def __call__(self, environ, start_response):
        return self.app(environ, start_response)


def debugger_filter_factory(global_conf, **kwargs):
    """Factory that returns a no-op filter."""
    def filter(app):
        return app
    return filter


def debugger_filter_app_factory(app, global_conf, **kwargs):
    """App factory that returns the app unchanged."""
    return app


__all__ = [
    'ErrorHandler',
    'StatusCodeRedirect',
    'debugger_filter_factory',
    'debugger_filter_app_factory',
]

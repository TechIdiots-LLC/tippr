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

import os
from pyramid.config import Configurator
from pyramid.response import Response
from pyramid.view import view_config


@view_config(route_name="health", renderer="json", request_method="GET")
def health_view(request):
    """Return a JSON object representing health/versions.

    This mimics the Pylons `HealthController.GET_health` behavior in a
    simplified form: it returns the `versions` mapping from the app
    settings as JSON, and returns 503 if the quiesce lock file exists.
    """
    if os.path.exists("/var/opt/tippr/quiesce"):
        return Response("No thanks, I'm full.", status=503, content_type="text/plain")

    versions = request.registry.settings.get("versions", {})
    return versions


def make_app(global_conf=None, **settings):
    """Create a minimal Pyramid WSGI app exposing the health endpoint.

    The `settings` dict may include a `versions` key (mapping) used by the
    health view. This factory allows standalone testing and later mounting
    inside a larger Pyramid application.
    """
    # Some callers (tests) pass a single `settings` kwarg containing the
    # real settings mapping (eg. `make_app(settings={"versions": {...}})`).
    # Normalize that shape so the Pyramid Configurator receives the actual
    # settings mapping.
    if 'settings' in settings and isinstance(settings['settings'], dict):
        cfg_settings = settings['settings']
    else:
        cfg_settings = settings

    config = Configurator(settings=cfg_settings)
    config.add_route("health", "/health")
    # Register the view directly to avoid relying on package scanning in tests.
    # Scanning can be brittle in test contexts; adding the view ensures the
    # route is handled and the view receives the Configurator settings.
    from .health import health_view
    config.add_view(health_view, route_name="health", renderer="json",
                    request_method="GET")
    return config.make_wsgi_app()

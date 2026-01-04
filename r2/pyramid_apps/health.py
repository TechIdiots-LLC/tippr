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

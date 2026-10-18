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

from webtest import TestApp
from pyramid_apps.health import make_app


def test_health_endpoint_returns_versions():
    app = make_app(settings={"versions": {"app": "1.2.3"}})
    testapp = TestApp(app)

    res = testapp.get("/health", status=200)
    assert res.json == {"app": "1.2.3"}


def test_health_endpoint_quiesce_returns_503(tmp_path, monkeypatch):
    # Create a temporary quiesce file and point path to it by monkeypatching
    # the path used by the view
    quiesce = tmp_path / "quiesce"
    quiesce.write_text("stop")

    # Monkeypatch os.path.exists to simulate quiesce file present
    import os

    orig_exists = os.path.exists

    def fake_exists(path):
        if path == "/var/opt/tippr/quiesce":
            return True
        return orig_exists(path)

    monkeypatch.setattr(os.path, "exists", fake_exists)

    app = make_app(settings={"versions": {"app": "1.2.3"}})
    testapp = TestApp(app)

    res = testapp.get("/health", status=503)
    assert b"No thanks, I'm full." in res.body

    # restore monkeypatch is automatic

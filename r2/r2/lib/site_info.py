# The contents of this file are subject to the Common Public Attribution
# License Version 1.0. (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://code.reddit.com/LICENSE. The License is based on the Mozilla Public
# License Version 1.1, but Sections 14 and 15 have been added to cover use of
# software over a computer network and provide for limited attribution for the
# Original Developer. In addition, Exhibit A has been modified to be consistent
# with Exhibit B.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is reddit.
#
# The Original Developer is the Initial Developer.  The Initial Developer of
# the Original Code is reddit Inc.
#
# All portions of the code written by reddit are Copyright (c) 2006-2015 reddit
# Inc. All Rights Reserved.
#
# Portions created by TechIdiots LLC (Tippr) are Copyright (c) 2026
# TechIdiots LLC. All Rights Reserved.
###############################################################################
"""The site's name, description, contact address and logo (/admin/site).

They start as ini settings. Values saved on /admin/site (site settings
group "site", in ZooKeeper) are set on g in every web process as soon as
they change, so everything reading g.site_name and the like sees them
without a restart; clearing one goes back to the ini value. They travel
with backups, since they're in ZooKeeper.

The domain isn't here: it is also in the nginx and haproxy configs, the TLS
certificate and cookies, so it's changed by re-running the installer.
"""

import hashlib
import io
import threading

from PIL import Image
from pylons import app_globals as g
from pylons.i18n import _

from r2.lib import site_settings

GROUP = "site"

# setting -> max length
SETTINGS = {
    "site_name": 40,
    "short_description": 200,
    "contact_email": 200,
    "site_logo": 500,
}

_lock = threading.Lock()
_installed = False


def install():
    """Start applying saved settings to g (once per process; cheap to call
    on every request)."""
    global _installed
    if _installed:
        return
    with _lock:
        if _installed:
            return
        real_g = g._current_obj() if hasattr(g, "_current_obj") else g
        site_settings.on_change(GROUP, lambda data: _apply(real_g, data))
        _installed = True


def _apply(target, data):
    for name in SETTINGS:
        value = data.get(name)
        if value:
            setattr(target, name, value)
        elif name in vars(target):
            # back to the ini value (Globals.__getattr__ reads the config)
            delattr(target, name)


# formats accepted for the logo (no SVG: it can carry scripts)
LOGO_FORMATS = {"PNG": ".png", "JPEG": ".jpg", "GIF": ".gif", "WEBP": ".webp"}
LOGO_MAX_PIXELS = 2000


def store_logo(data):
    """Check an uploaded logo and put it in the media store, as uploaded
    (keeping transparency and animation). Returns (url, None) or
    (None, error)."""
    if isinstance(data, str):
        data = data.encode("latin-1")
    try:
        image = Image.open(io.BytesIO(data))
        image.verify()
    except Exception:
        return None, _("That isn't an image tippr can read.")
    extension = LOGO_FORMATS.get(image.format)
    if not extension:
        return None, _("Use a PNG, JPEG, GIF or WebP image.")
    if max(image.size) > LOGO_MAX_PIXELS:
        return None, _("Use an image at most %(n)d pixels wide and high.") % {
            "n": LOGO_MAX_PIXELS}
    name = "logo-" + hashlib.sha256(data).hexdigest()[:20] + extension
    try:
        return g.media_provider.put("logos", name, data), None
    except Exception:
        g.log.exception("site_info: couldn't store the logo")
        return None, _("The logo couldn't be saved; see the error log.")


def saved():
    """The values saved on /admin/site (may be empty)."""
    return site_settings.get_settings(GROUP)


def current():
    """What the site uses now, for each setting."""
    return {name: getattr(g, name, "") or "" for name in SETTINGS}


def logo_url():
    """The saved logo's address over https (media URLs are stored as
    http), or None for the default logo."""
    from r2.lib.template_helpers import make_url_https
    logo = getattr(g, "site_logo", None)
    return make_url_https(logo) if logo else None


def ini_values():
    return {name: g.config.get(name) or "" for name in SETTINGS}


def save(values):
    """Save the given settings; an empty value goes back to the ini."""
    data = saved()
    for name, value in values.items():
        if name not in SETTINGS:
            continue
        value = (value or "").strip()
        if value:
            data[name] = value
        else:
            data.pop(name, None)
    site_settings.save_settings(GROUP, data)

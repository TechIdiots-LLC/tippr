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
"""The site's identity and front-of-house settings (/admin/site): name,
description, contact address, logo, favicon and share image, page titles,
search engine verification, an announcement banner and whether sign-ups are
open.

They start as ini settings (or empty). Values saved on /admin/site (site
settings group "site", in ZooKeeper) are set on g in every web process as
soon as they change, so everything reading g.site_name and the like sees
them without a restart; clearing one goes back to the ini value. They travel
with backups, since they're in ZooKeeper.

The domain isn't here: it is also in the nginx config, the TLS certificate
and cookies, so it's changed by re-running the installer.
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
    # page titles: the front page's own, and a format for every other page
    # ("{title}" is the page's title, "{site}" the site name)
    "front_page_title": 120,
    "title_format": 80,
    # meta tags search engines ask for to prove you own the site
    "google_site_verification": 120,
    "bing_site_verification": 120,
    # images (media store URLs)
    "site_favicon": 500,
    "share_image": 500,
    # a banner at the top of every page, with an optional link
    "announcement": 300,
    "announcement_link": 500,
    # "closed" to stop new accounts; anything else is open
    "signups": 10,
    # who runs the site, for the policy pages (docs/policies): the legal
    # name, and whose laws govern them
    "site_operator": 120,
    "governing_law": 120,
}

# the settings set from the /admin/site text form (the others have their
# own controls: image uploads, the sign-ups switch)
TEXT_SETTINGS = (
    "site_name", "short_description", "contact_email", "front_page_title",
    "title_format", "google_site_verification", "bing_site_verification",
    "announcement", "announcement_link", "site_operator", "governing_law",
)

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


# Uploaded images: setting -> (file name prefix, accepted formats, largest
# side in pixels). No SVG anywhere: it can carry scripts.
IMAGE_EXTENSIONS = {"PNG": ".png", "JPEG": ".jpg", "GIF": ".gif",
                    "WEBP": ".webp", "ICO": ".ico"}
IMAGES = {
    "site_logo": ("logo", ("PNG", "JPEG", "GIF", "WEBP"), 2000),
    "site_favicon": ("favicon", ("PNG", "ICO"), 512),
    "share_image": ("share", ("PNG", "JPEG", "WEBP"), 4000),
}
IMAGE_FORMAT_NAMES = {
    "site_logo": "PNG, JPEG, GIF or WebP",
    "site_favicon": "PNG or ICO",
    "share_image": "PNG, JPEG or WebP",
}
# kept for the logo upload's callers
LOGO_FORMATS = {f: IMAGE_EXTENSIONS[f] for f in IMAGES["site_logo"][1]}
LOGO_MAX_PIXELS = IMAGES["site_logo"][2]


def store_image(setting, data):
    """Check an uploaded image for one of IMAGES and put it in the media
    store, as uploaded (keeping transparency and animation). Returns
    (url, None) or (None, error)."""
    prefix, formats, max_pixels = IMAGES[setting]
    if isinstance(data, str):
        data = data.encode("latin-1")
    try:
        image = Image.open(io.BytesIO(data))
        image.verify()
    except Exception:
        return None, _("That isn't an image tippr can read.")
    if image.format not in formats:
        return None, _("Use a %(formats)s image.") % {
            "formats": IMAGE_FORMAT_NAMES[setting]}
    if max(image.size) > max_pixels:
        return None, _("Use an image at most %(n)d pixels wide and high.") % {
            "n": max_pixels}
    extension = IMAGE_EXTENSIONS[image.format]
    name = prefix + "-" + hashlib.sha256(data).hexdigest()[:20] + extension
    try:
        return g.media_provider.put("logos", name, data), None
    except Exception:
        g.log.exception("site_info: couldn't store the %s", setting)
        return None, _("The image couldn't be saved; see the error log.")


def store_logo(data):
    return store_image("site_logo", data)


def image_url(setting):
    """A saved image's address over https (media URLs are stored as http),
    or None when there is none."""
    from r2.lib.template_helpers import make_url_https
    url = getattr(g, setting, None)
    return make_url_https(url) if url else None


def title(page_title, front_page=False):
    """A page's <title>. The front page gets its own title when one is set
    (or keeps the one it has); other pages go through the title format,
    unless their title already names the site ("tippr: page not found")."""
    if front_page:
        return getattr(g, "front_page_title", None) or page_title
    fmt = getattr(g, "title_format", None)
    if not page_title or not fmt or "{title}" not in fmt:
        return page_title
    site_name = (g.site_name or "").strip()
    if site_name and site_name.lower() in page_title.lower():
        return page_title
    return fmt.replace("{title}", page_title).replace("{site}", site_name)


# sections of the contact page (templates/contactus.html) that other pages
# and the policies send people to
CONTACT_SECTIONS = ("message-the-admins", "privacy", "legal", "appeals",
                    "report-content", "moderators", "ratelimit", "gold")


def contact_url(section=None):
    """The contact page (or one of its sections), as a full address: it
    offers a message to the admins and the contact address when one is set,
    so no address has to be written into other pages."""
    url = g.https_endpoint.rstrip("/") + "/contact"
    if section:
        assert section in CONTACT_SECTIONS, section
        url += "#" + section
    return url


def gold_support():
    """Where gold messages (receipts, expiry notices, payment problems)
    send people: the contact page's gold section, which shows the
    goldsupport_email address too when one is set."""
    return contact_url("gold")


def contact_link_html(section=None, text=None):
    """contact_url() as a link."""
    from r2.lib.filters import websafe
    return '<a href="%s">%s</a>' % (websafe(contact_url(section)),
                                    websafe(text or _("the contact page")))


def policy_values():
    """What the {{PLACEHOLDERS}} in docs/policies/*.md stand for on this
    site (scripts/init_policy_wiki_pages.py fills them in)."""
    site_name = (g.site_name or g.domain).strip()
    return {
        "SITE_NAME": site_name,
        "DOMAIN": g.domain,
        "SITE_URL": g.https_endpoint.rstrip("/"),
        "OPERATOR": getattr(g, "site_operator", None) or site_name,
        "GOVERNING_LAW": (getattr(g, "governing_law", None) or
                          "the place where the site's operator is established"),
    }


def fill_policy(text):
    """docs/policies text with this site's details in place of the
    placeholders."""
    for name, value in policy_values().items():
        text = text.replace("{{%s}}" % name, value)
    return text


def signups_open():
    return getattr(g, "signups", None) != "closed"


def announcement():
    """(text, link, id) for the banner, or None. The id changes with the
    text, so a banner someone dismissed comes back when it's changed."""
    text = getattr(g, "announcement", None)
    if not text:
        return None
    link = getattr(g, "announcement_link", None) or ""
    ident = hashlib.sha256((text + "\n" + link).encode("utf-8")).hexdigest()[:12]
    return text, link, ident


def saved():
    """The values saved on /admin/site (may be empty)."""
    return site_settings.get_settings(GROUP)


def current():
    """What the site uses now, for each setting."""
    return {name: getattr(g, name, "") or "" for name in SETTINGS}


def logo_url():
    """The saved logo's address over https, or None for the default logo."""
    return image_url("site_logo")


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

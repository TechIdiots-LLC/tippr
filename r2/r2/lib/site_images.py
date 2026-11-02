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
"""The site's own images, replaceable from /admin/images.

Every image under static/ (except award images, which /admin/awards sets)
can be replaced by an upload. Uploads go to the media store, and which
image each one replaces is saved in the site settings group "images" (in
ZooKeeper, so it applies on every web process at once and moves with
backups): {"aupgray.png": {"url": ..., "size": [w, h]}}.

Replacements reach the page three ways:

- static() gives a replacement's address instead of the file's, for the
  images templates show (r2.lib.template_helpers.static);
- r.utils.staticURL does the same in scripts (r.config.static_overrides);
- images in the stylesheets get a small stylesheet after each one
  (templates/less.html), repeating each rule that uses a replaced image with
  the replacement. Most of those images are packed into sprite sheets when
  the static files are built, so the stylesheet only names the sheet and a
  position; the sprite builder (r2.lib.nymph) writes down which image is
  where, beside each sheet (sprite-tippr.json).

A replacement is shown at the original's size where the stylesheet decides
the size, so one with the same proportions works best. A replacement for an
image also stands in for its double-size version (foo_2x.png for foo.png),
unless that has its own.
"""

import hashlib
import io
import json
import os
import re
import threading

from PIL import Image
from pylons import app_globals as g
from pylons.i18n import _

from r2.lib import site_settings

GROUP = "images"

IMAGE_EXTENSIONS = (".png", ".gif", ".jpg", ".jpeg", ".ico", ".svg", ".webp")
# award images are each award's own (/admin/awards)
SKIPPED_FOLDERS = ("awards",)
# what uploads may be (no SVG: it can carry scripts)
UPLOAD_FORMATS = {"PNG": ".png", "JPEG": ".jpg", "GIF": ".gif",
                  "WEBP": ".webp", "ICO": ".ico"}
MAX_PIXELS = 4000

_safe_url_re = re.compile(r"^https?://[^\s\"'()\\<>]+$")
_double_re = re.compile(r"^(.*)_2x(\.\w+)$")
# r2.lib.static.generate_static_name's 11-character hash
_hashed_re = re.compile(r"\.[\w-]{11}\.css$")
_url_re = re.compile(r"""url\(\s*(['"]?)(.*?)\1\s*\)""", re.I)
_px_re = re.compile(r"(-?\d+(?:\.\d+)?)(?:px)?$")
# names of image files mentioned in the code
_mention_re = re.compile(
    r"[\w./%-]+\.(?:png|gif|jpe?g|ico|svg|webp)\b", re.I)

_lock = threading.Lock()
_cache = {}


# ---- the saved replacements

def replacements():
    """{image path: {"url": ..., "size": [w, h]}} (may be empty)."""
    try:
        data = site_settings._group(GROUP).data
    except Exception:
        # (no ZooKeeper: scripts, tests)
        return {}
    return data


def _replacement_url(path, saved):
    entry = saved.get(path)
    if not entry:
        match = _double_re.match(path)
        if match:
            entry = saved.get(match.group(1) + match.group(2))
    url = entry and entry.get("url")
    if not url:
        return None
    from r2.lib.template_helpers import make_url_https
    url = make_url_https(url)
    return url if _safe_url_re.match(url) else None


def replacement_url(path):
    """The address of a replaced static image, or None. Cheap when nothing
    has been replaced: static() asks for every image."""
    saved = replacements()
    if not saved:
        return None
    return _replacement_url(_normalize(path), saved)


def js_overrides():
    """{image path: address} for r.utils.staticURL."""
    saved = replacements()
    return {path: url for path in saved
            for url in [_replacement_url(path, saved)] if url}


def _normalize(path):
    path = (path or "").split("?")[0].split("#")[0].replace("\\", "/")
    while path.startswith("../"):
        path = path[3:]
    for prefix in ("/static/", "static/", "/"):
        if path.startswith(prefix):
            path = path[len(prefix):]
    return path


# ---- the images there are

def static_dir():
    return os.path.join(g.paths["static_files"], "static")


class SiteImage:
    def __init__(self, path, size):
        self.path = path
        self.size = size
        self.folder = path.rsplit("/", 1)[0] if "/" in path else ""
        self.name = path.rsplit("/", 1)[-1]


def catalogue():
    """Every image that can be replaced, by path (memoized per process)."""
    key = ("catalogue", static_dir())
    found = _cache.get(key)
    if found is not None:
        return found
    root = static_dir()
    mangled = set((getattr(g, "static_names", None) or {}).values())
    found = {}
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root).replace("\\", "/")
        rel_dir = "" if rel_dir == "." else rel_dir
        if rel_dir.split("/")[0] in SKIPPED_FOLDERS:
            dirnames[:] = []
            continue
        for filename in filenames:
            if not filename.lower().endswith(IMAGE_EXTENSIONS):
                continue
            if filename.startswith("sprite-") or filename in mangled:
                continue
            path = rel_dir + "/" + filename if rel_dir else filename
            found[path] = SiteImage(path, _image_size(os.path.join(dirpath, filename)))
    _cache[key] = found
    return found


def _image_size(filename):
    try:
        with Image.open(filename) as image:
            return image.size
    except Exception:
        # (SVG, or not an image PIL reads)
        return None


def mentioned():
    """The image file names the code mentions (templates, scripts, Python),
    for telling images in use from leftovers. Names put together in code
    ("aup%s.png") aren't found."""
    key = ("mentioned",)
    found = _cache.get(key)
    if found is not None:
        return found
    package = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    places = [os.path.join(package, name) for name in
              ("templates", "lib", "controllers", "models", "config")]
    places.append(os.path.join(package, "public", "static", "js"))
    found = set()
    for place in places:
        for dirpath, dirnames, filenames in os.walk(place):
            dirnames[:] = [d for d in dirnames
                           if d not in ("__pycache__", "tests")]
            for filename in filenames:
                if not filename.endswith((".py", ".html", ".js", ".compact",
                                          ".mobile", ".xml", ".txt",
                                          ".email", ".iframe")):
                    continue
                try:
                    with open(os.path.join(dirpath, filename),
                              encoding="utf-8", errors="replace") as f:
                        text = f.read()
                except OSError:
                    continue
                for name in _mention_re.findall(text):
                    found.add(name.rsplit("/", 1)[-1])
    _cache[key] = found
    return found


def in_stylesheets():
    """The images some built stylesheet uses."""
    used = set()
    for name in _stylesheet_names():
        for rule in _stylesheet_rules(name):
            used.update(rule.files)
    return used


# ---- uploads

def store(path, data):
    """Check an upload for the image at path and put it in the media store.
    Returns (entry, None) or (None, error)."""
    original = catalogue().get(path)
    if original is None:
        return None, _("There's no such image.")
    if isinstance(data, str):
        data = data.encode("latin-1")
    try:
        image = Image.open(io.BytesIO(data))
        image.verify()
    except Exception:
        return None, _("That isn't an image tippr can read.")
    if image.format not in UPLOAD_FORMATS or (
            image.format == "ICO" and not path.endswith(".ico")):
        return None, _("Use a PNG, JPEG, GIF or WebP image.")
    if max(image.size) > MAX_PIXELS:
        return None, _("Use an image at most %(n)d pixels wide and high.") % {
            "n": MAX_PIXELS}
    stem = re.sub(r"[^\w-]+", "-", os.path.splitext(path)[0])
    name = "site-%s-%s%s" % (stem, hashlib.sha256(data).hexdigest()[:16],
                             UPLOAD_FORMATS[image.format])
    try:
        url = g.media_provider.put("site-images", name, data)
    except Exception:
        g.log.exception("site_images: couldn't store a replacement for %s",
                        path)
        return None, _("The image couldn't be saved; see the error log.")
    return {"url": url, "size": list(image.size)}, None


def save(path, entry):
    """Replace the image at path (entry from store()), or with None go back
    to the original."""
    data = dict(site_settings.get_settings(GROUP))
    if entry:
        data[path] = entry
    else:
        data.pop(path, None)
    site_settings.save_settings(GROUP, data)


# ---- the stylesheets

class _Rule:
    """A stylesheet rule that shows an image."""
    def __init__(self, media, selector, prop, files, important,
                 sprite=None, has_size=False):
        self.media = media          # the @media (etc.) blocks it's in
        self.selector = selector
        self.prop = prop            # background or list-style-image
        self.files = files          # the image (several: identical images)
        self.important = important
        self.sprite = sprite        # (width, height, stretch) on the page
        self.has_size = has_size


def _stylesheet_names():
    root = static_dir()
    mangled = set((getattr(g, "static_names", None) or {}).values())
    try:
        names = os.listdir(root)
    except OSError:
        return []
    # (not the hashed copies, this build's or older ones: tippr.Ab3….css)
    return sorted(name for name in names
                  if name.endswith(".css") and name not in mangled and
                  not _hashed_re.search(name))


def _blocks(css):
    """The top-level (prelude, body) pairs of a stylesheet."""
    i, n, start = 0, len(css), 0
    while i < n:
        ch = css[i]
        if ch in "\"'":
            i = _skip_string(css, i)
            continue
        if ch == ";":
            start = i + 1
        elif ch == "{":
            depth, j = 1, i + 1
            while j < n and depth:
                if css[j] in "\"'":
                    j = _skip_string(css, j)
                    continue
                if css[j] == "{":
                    depth += 1
                elif css[j] == "}":
                    depth -= 1
                j += 1
            yield css[start:i].strip(), css[i + 1:j - 1]
            start = i = j
            continue
        elif ch == "}":
            start = i + 1
        i += 1


def _skip_string(css, i):
    quote, i = css[i], i + 1
    while i < len(css) and css[i] != quote:
        i += 2 if css[i] == "\\" else 1
    return i + 1


def _declarations(body):
    """[(property, value, important)] of a rule's body."""
    parts, depth, start, i = [], 0, 0, 0
    while i < len(body):
        ch = body[i]
        if ch in "\"'":
            i = _skip_string(body, i)
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == ";" and depth == 0:
            parts.append(body[start:i])
            start = i + 1
        i += 1
    parts.append(body[start:])
    found = []
    for part in parts:
        if ":" not in part:
            continue
        prop, value = part.split(":", 1)
        value = value.strip()
        important = value.lower().endswith("!important")
        if important:
            value = value[:-len("!important")].strip()
        found.append((prop.strip().lower(), value, important))
    return found


def _parse(css, sprites, media=()):
    rules = []
    for prelude, body in _blocks(css):
        lower = prelude.lower()
        if lower.startswith(("@media", "@supports", "@document")):
            rules.extend(_parse(body, sprites, media + (prelude,)))
            continue
        if not prelude or prelude.startswith("@"):
            continue  # @font-face, @keyframes …
        rule = _image_rule(media, prelude, _declarations(body), sprites)
        if rule:
            rules.append(rule)
    return rules


def _image_rule(media, selector, declarations, sprites):
    props = {}
    for prop, value, important in declarations:
        props[prop] = (value, important)
    for prop in ("background-image", "background", "list-style-image"):
        if prop not in props:
            continue
        value, important = props[prop]
        found = _url_re.search(value)
        if not found:
            continue
        path = _normalize(found.group(2))
        if not path or path.startswith(("data:", "http:", "https:", "//")):
            return None
        kind = "list-style-image" if prop == "list-style-image" else "background"
        # (the shorthand can set it too: "url(x) 0 0/20px 10px")
        has_size = ("background-size" in props or
                    (prop == "background" and "/" in _url_re.sub("", value)))
        name = path.rsplit("/", 1)[-1]
        if name.startswith("sprite-"):
            return _sprite_rule(media, selector, props, sprites.get(name),
                                important)
        return _Rule(media, selector, kind, (path,), important,
                     has_size=has_size)
    return None


def _px(value):
    found = _px_re.match(value.strip())
    return float(found.group(1)) if found else None


def _sprite_rule(media, selector, props, manifest, important):
    if not manifest or "background-position" not in props:
        return None
    position = [_px(v) for v in props["background-position"][0].split()]
    if len(position) != 2 or None in position:
        return None
    x, y = -position[0], -position[1]
    ratio = 1
    if "background-size" in props:
        width = _px(props["background-size"][0].split()[0])
        if width:
            ratio = max(1, int(round(manifest["size"][0] / width)))
    for image in manifest["images"]:
        # (nymph writes each position as a whole number of pixels)
        if (int(image["x"] / ratio) == x and int(image["y"] / ratio) == y):
            files = tuple(_normalize(f) for f in image["files"])
            sprite = (image["width"] / ratio, image["height"] / ratio,
                      image["stretch"])
            return _Rule(media, selector, "background", files, important,
                         sprite=sprite)
    return None


def _sprite_manifests():
    root = static_dir()
    manifests = {}
    try:
        names = os.listdir(root)
    except OSError:
        return manifests
    for name in names:
        if name.startswith("sprite-") and name.endswith(".json"):
            try:
                with open(os.path.join(root, name)) as f:
                    manifest = json.load(f)
            except (OSError, ValueError):
                continue
            manifests[manifest["sprite"]] = manifest
    return manifests


def _stylesheet_rules(name):
    """The rules showing images in a built stylesheet (memoized until the
    file changes)."""
    filename = os.path.join(static_dir(), name)
    try:
        mtime = os.path.getmtime(filename)
    except OSError:
        return []
    key = ("rules", filename)
    cached = _cache.get(key)
    if cached and cached[0] == mtime:
        return cached[1]
    with _lock:
        with open(filename, encoding="utf-8", errors="replace") as f:
            css = f.read()
        rules = _parse(css, _sprite_manifests())
        _cache[key] = (mtime, rules)
    return rules


def _css_url(url):
    return 'url("%s")' % url


def _override(rule, url):
    important = "!important" if rule.important else ""
    if rule.prop == "list-style-image":
        return "list-style-image:%s%s" % (_css_url(url), important)
    decls = ["background-image:%s%s" % (_css_url(url), important)]
    if rule.sprite:
        width, height, stretch = rule.sprite
        decls.append("background-position:0 0%s" % important)
        decls.append("background-size:%s %dpx%s" % (
            "auto" if stretch else "%dpx" % width, height, important))
    elif not rule.has_size:
        original = catalogue().get(rule.files[0])
        if original and original.size:
            # the replacement in the original's place, at its size
            decls.append("background-size:%dpx %dpx%s" % (
                original.size[0], original.size[1], important))
    return ";".join(decls)


def stylesheet_css(name):
    """The rules putting replaced images into the built stylesheet `name`
    ("tippr.css"), for after it on the page; "" if none."""
    saved = replacements()
    if not saved:
        return ""
    version = json.dumps(saved, sort_keys=True)
    key = ("css", name)
    cached = _cache.get(key)
    rules = _stylesheet_rules(name)
    if cached and cached[0] == version and cached[1] is rules:
        return cached[2]
    out = []
    for rule in rules:
        url = None
        for path in rule.files:
            url = _replacement_url(path, saved)
            if url:
                break
        if not url:
            continue
        css = "%s{%s}" % (rule.selector, _override(rule, url))
        for media in reversed(rule.media):
            css = "%s{%s}" % (media, css)
        out.append(css)
    text = "\n".join(out)
    _cache[key] = (version, rules, text)
    return text

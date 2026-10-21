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
"""Spam protection: the captcha and CleanTalk (/admin/antispam).

Two layers, set independently:

- **The captcha** shown where untrusted users (logged out, or new accounts
  without karma; see Account.needs_captcha) sign up, post, send messages
  or create vaults. The provider is tippr's own image captcha, Cloudflare
  Turnstile, hCaptcha, Google reCAPTCHA (v2, "I'm not a robot") or none.
  The services need their site and secret keys; without them the built-in
  captcha is used.
- **CleanTalk** (cleantalk.org) checks sign-ups and what untrusted users
  post, invisibly. Spam sign-ups are refused; spam posts, comments and
  messages are saved but marked as spam, so moderators see them in their
  spam queue. If CleanTalk can't be reached, things go through.

Settings saved on /admin/antispam (site settings group "antispam")
override the ini.
"""

import json
import os
import time

import requests
from pylons import app_globals as g
from pylons import request
from pylons import tmpl_context as c

from r2.lib import site_settings

GROUP = "antispam"
TIMEOUT = 5

# provider -> (name, widget script, widget class, response field,
#              verify URL)
PROVIDERS = {
    "builtin": ("tippr's image captcha", None, None, None, None),
    "turnstile": (
        "Cloudflare Turnstile",
        "https://challenges.cloudflare.com/turnstile/v0/api.js",
        "cf-turnstile", "cf-turnstile-response",
        "https://challenges.cloudflare.com/turnstile/v0/siteverify"),
    "hcaptcha": (
        "hCaptcha",
        "https://js.hcaptcha.com/1/api.js",
        "h-captcha", "h-captcha-response",
        "https://api.hcaptcha.com/siteverify"),
    "recaptcha": (
        "Google reCAPTCHA v2",
        "https://www.google.com/recaptcha/api.js",
        "g-recaptcha", "g-recaptcha-response",
        "https://www.google.com/recaptcha/api/siteverify"),
    "none": ("no captcha", None, None, None, None),
}

CLEANTALK_URL = "https://moderate.cleantalk.org/api2.0"
CLEANTALK_BOT_DETECTOR = "https://moderate.cleantalk.org/ct-bot-detector-wrapper.js"
CLEANTALK_TOKEN_FIELD = "ct_bot_detector_event_token"

# setting -> default (the ini can set any of them too)
DEFAULTS = {
    "captcha_provider": "builtin",
    "captcha_site_key": "",
    "captcha_secret_key": "",
    "captcha_on_register": True,
    "cleantalk_enabled": False,
    "cleantalk_auth_key": "",
    "cleantalk_check_register": True,
    "cleantalk_check_content": True,
    # tell CleanTalk when moderators mark what it checked as spam, or
    # approve what it flagged (send_feedback)
    "cleantalk_feedback": True,
}
SECRET_SETTINGS = ("captcha_secret_key", "cleantalk_auth_key")


def _bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def settings():
    """The effective settings: defaults, the ini, then /admin/antispam."""
    result = {}
    saved = site_settings.get_settings(GROUP)
    for name, default in DEFAULTS.items():
        value = saved.get(name, g.config.get(name, default))
        result[name] = _bool(value) if isinstance(default, bool) else (value or "")
    if result["captcha_provider"] not in PROVIDERS:
        result["captcha_provider"] = "builtin"
    return result


def save(values):
    data = site_settings.get_settings(GROUP)
    for name, value in values.items():
        if name in SECRET_SETTINGS and not value:
            continue  # a blank secret field keeps the saved one
        data[name] = value
    site_settings.save_settings(GROUP, data)


###############################################################################
# The captcha
###############################################################################

def captcha_provider():
    """The provider in use: a service only once it has both keys."""
    s = settings()
    provider = s["captcha_provider"]
    if PROVIDERS[provider][1] and not (s["captcha_site_key"]
                                       and s["captcha_secret_key"]):
        return "builtin"
    return provider


def captcha_enabled():
    return not g.disable_captcha and captcha_provider() != "none"


def captcha_on_register():
    return captcha_enabled() and settings()["captcha_on_register"]


def widget_html():
    """The captcha service's widget, or "" for the built-in captcha.

    Only a placeholder: the page loads the service's script once
    (script_html) and $.renderCaptchaWidgets draws the widget when its form
    is shown. Forms can sit inside <script type="text/template"> blocks (the
    login popup), where a <script> tag of their own would end the block.
    """
    provider = captcha_provider()
    name, script, css_class, field, url = PROVIDERS[provider]
    if not css_class:
        return ""
    from r2.lib.filters import websafe
    return '<div class="%s antispam-captcha" data-sitekey="%s"></div>' % (
        css_class, websafe(settings()["captcha_site_key"]))


def script_html():
    """The captcha service's script, for pages whose visitors may see a
    captcha (logged out, or not yet trusted). It loads in explicit mode and
    calls tipprCaptchaReady (jquery.tippr.js), which draws the widgets."""
    if not captcha_enabled() or not c.user.needs_captcha():
        return ""
    name, script, css_class, field, url = PROVIDERS[captcha_provider()]
    if not script:
        return ""
    return ('<script src="%s?render=explicit&amp;onload=tipprCaptchaReady" '
            'async defer></script>' % script)


def verify_captcha(iden=None, solution=None):
    """Whether this request's captcha answer is right."""
    provider = captcha_provider()
    if provider == "none":
        return True
    if provider == "builtin":
        from r2.lib import captcha
        return captcha.valid_solution(iden, solution)
    name, script, css_class, field, url = PROVIDERS[provider]
    token = request.POST.get(field) or ""
    if not token:
        return False
    try:
        resp = requests.post(url, timeout=TIMEOUT, data={
            "secret": settings()["captcha_secret_key"],
            "response": token,
            "remoteip": request.ip,
        })
        result = resp.json()
    except (requests.RequestException, ValueError) as e:
        # the service is down: don't lock everyone out
        g.log.warning("antispam: couldn't verify the %s captcha: %s",
                      name, e)
        return True
    if not result.get("success"):
        g.log.info("antispam: %s captcha failed: %s", name,
                   result.get("error-codes"))
    return bool(result.get("success"))


###############################################################################
# CleanTalk
###############################################################################

def cleantalk_enabled():
    s = settings()
    return s["cleantalk_enabled"] and bool(s["cleantalk_auth_key"])


def bot_detector_html():
    """CleanTalk's bot detector script, for visitors whose forms CleanTalk
    checks: logged out (sign-up) or untrusted. It adds a token to forms that
    CleanTalk uses to tell people from bots."""
    if not cleantalk_enabled() or getattr(c, "_cleantalk_script", False):
        return ""
    if c.user_is_loggedin and not should_check_content(c.user):
        return ""
    c._cleantalk_script = True
    return '<script src="%s" async></script>' % CLEANTALK_BOT_DETECTOR


def _sender():
    return {
        "sender_ip": request.ip,
        "event_token": request.POST.get(CLEANTALK_TOKEN_FIELD, ""),
        "js_on": 1 if request.POST.get(CLEANTALK_TOKEN_FIELD) else 0,
        "submit_time": None,
        "agent": "tippr-%s" % os.environ.get("TIPPR_VERSION", "dev"),
        "sender_info": json.dumps({
            "REFFERRER": request.referer or "",
            "USER_AGENT": request.user_agent or "",
        }),
    }


def _cleantalk(method, **fields):
    """Call CleanTalk; returns (allowed, reason). Allows on any error."""
    body = dict(_sender(), method_name=method,
                auth_key=settings()["cleantalk_auth_key"], **fields)
    body = {k: v for k, v in body.items() if v is not None}
    started = time.time()
    try:
        resp = requests.post(CLEANTALK_URL, json=body, timeout=TIMEOUT)
        result = resp.json()
    except (requests.RequestException, ValueError) as e:
        g.log.warning("antispam: CleanTalk unreachable (%s); allowing", e)
        _record(method, "error", None)
        return True, None
    if result.get("error_message") or result.get("error_no"):
        g.log.warning("antispam: CleanTalk error %s: %s; allowing",
                      result.get("error_no"), result.get("error_message"))
        _record(method, "error", time.time() - started)
        return True, None
    allowed = str(result.get("allow", 1)) == "1"
    seconds = time.time() - started
    g.log.info("antispam: CleanTalk %s -> %s in %.2fs (%s)", method,
               "allow" if allowed else "spam", seconds,
               result.get("comment", ""))
    _record(method, "allow" if allowed else "spam", seconds)
    # the check's id, for feedback later (remember_check)
    c.cleantalk_request_id = result.get("id")
    return allowed, result.get("comment")


def _record(method, outcome, seconds):
    """For the statistics on /admin/antispam (r2.lib.cleantalk_stats)."""
    try:
        from r2.lib import cleantalk_stats
        cleantalk_stats.record(method, outcome, seconds)
    except Exception:
        g.log.exception("antispam: couldn't record CleanTalk statistics")


def check_signup(name, email):
    """(allowed, reason) for a new account."""
    if not cleantalk_enabled() or not settings()["cleantalk_check_register"]:
        return True, None
    return _cleantalk("check_newuser", sender_email=email or "",
                      sender_nickname=name)


def should_check_content(user):
    """Whether CleanTalk checks what this user posts: the same untrusted
    users who get the captcha (new accounts without karma), even when the
    captcha itself is off."""
    if not cleantalk_enabled() or not settings()["cleantalk_check_content"]:
        return False
    if getattr(user, "employee", False):
        return False
    return (user.link_karma < g.live_config["captcha_exempt_link_karma"] and
            user.comment_karma < g.live_config["captcha_exempt_comment_karma"])


def check_content(user, text, kind, title=None):
    """(allowed, reason) for a post, comment or message (kind: "link",
    "comment" or "message")."""
    c.cleantalk_request_id = None
    if not should_check_content(user):
        return True, None
    post_info = {"comment_type": {"link": "general_post",
                                  "comment": "comment",
                                  "message": "contact_form"}.get(kind, kind)}
    if title:
        post_info["post_title"] = title
    return _cleantalk("check_message",
                      sender_email=getattr(user, "email", "") or "",
                      sender_nickname=user.name,
                      message=text or title or "",
                      post_info=json.dumps(post_info))


def mark_spam(thing, reason):
    """Hide a thing CleanTalk flagged, into the moderators' spam queue."""
    from r2.models import admintools
    g.stats.simple_event("spam.cleantalk")
    admintools.spam(thing, auto=True, moderator_banned=False,
                    banner="CleanTalk" + (": %s" % reason if reason else ""))


def after_check(thing, allowed, reason):
    """After check_content, with the thing it was for: keep the check's id
    (for feedback), and hide the thing if CleanTalk said spam."""
    request_id = getattr(c, "cleantalk_request_id", None)
    if request_id:
        thing.cleantalk_id = request_id
        thing.cleantalk_spam = not allowed
        thing._commit()
    if not allowed:
        mark_spam(thing, reason)


def feedback(thing, spam):
    """A moderator's verdict on something CleanTalk checked, sent back so
    it learns: spam (the "spam" button) or not spam (approving what it
    flagged). Sent in the background; nothing happens without the check's
    id, or with feedback off on /admin/antispam."""
    request_id = getattr(thing, "cleantalk_id", None)
    if not request_id or not cleantalk_enabled():
        return
    if not settings()["cleantalk_feedback"]:
        return
    if not spam and not getattr(thing, "cleantalk_spam", False):
        return  # approving what CleanTalk allowed tells it nothing new
    if getattr(thing, "cleantalk_feedback_sent", None) == spam:
        return  # already told it this
    thing.cleantalk_feedback_sent = spam
    thing._commit()
    body = {"method_name": "send_feedback",
            "auth_key": settings()["cleantalk_auth_key"],
            # 0: it was spam, 1: it was fine
            "feedback": "%s:%d" % (request_id, 0 if spam else 1)}
    log = g.log

    def send():
        try:
            resp = requests.post(CLEANTALK_URL, json=body, timeout=TIMEOUT)
            result = resp.json()
        except (requests.RequestException, ValueError) as e:
            log.warning("antispam: CleanTalk feedback failed: %s", e)
            return
        if result.get("error_message") or result.get("error_no"):
            log.warning("antispam: CleanTalk feedback error %s: %s",
                        result.get("error_no"), result.get("error_message"))
        else:
            log.info("antispam: told CleanTalk %s was %s", request_id,
                     "spam" if spam else "not spam")

    # a moderator's click shouldn't wait on CleanTalk
    import threading
    threading.Thread(target=send, daemon=True).start()


CLEANTALK_KEY_URL = "https://api.cleantalk.org/"


def test_cleantalk(auth_key):
    """Check an access key; returns a problem to show, or None if the key
    works. (The spam checks answer "allowed" even for a wrong key, so ask
    CleanTalk's key check instead.)"""
    try:
        resp = requests.get(CLEANTALK_KEY_URL, timeout=TIMEOUT, params={
            "method_name": "notice_paid_till", "auth_key": auth_key})
        result = resp.json().get("data") or {}
    except (requests.RequestException, ValueError, AttributeError) as e:
        return "couldn't reach CleanTalk: %s" % e
    if str(result.get("valid")) != "1":
        return "that access key isn't valid"
    if str(result.get("moderate", 1)) != "1":
        return "the key is valid, but checking is off for this website"
    return None

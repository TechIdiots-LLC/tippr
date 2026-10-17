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
"""Delivery of outgoing email.

The mail_transport setting picks how mail is sent:

  none   Don't send. Queued mail stays queued until a transport is set up.
  smtp   An SMTP server: smtp_server ("host" or "host:port"), smtp_security
         ("none", "starttls" or "ssl") and an optional smtp_username /
         smtp_password login. Works with transactional mail services and
         with a local mail server.
  gmail  The Gmail API, authorized with an OAuth2 refresh token for the
         gmail.send scope (gmail_client_id, gmail_client_secret,
         gmail_refresh_token; see scripts/gmail_oauth_setup.py). Mail is sent
         as the Google account, which replaces the From address unless it is
         one of that account's "send mail as" addresses.

Values come from the ini file, overridden by the admin email settings page
(the "email" group of r2.lib.site_settings).
"""

import base64
import smtplib
import ssl
import time

import requests
from pylons import app_globals as g

from r2.lib import site_settings

TRANSPORTS = ("none", "smtp", "gmail")
SMTP_SECURITY = ("none", "starttls", "ssl")
SETTINGS = (
    "mail_transport",
    "mail_from",
    "smtp_server",
    "smtp_security",
    "smtp_username",
    "smtp_password",
    "gmail_client_id",
    "gmail_client_secret",
    "gmail_refresh_token",
)
SECRET_SETTINGS = ("smtp_password", "gmail_client_secret", "gmail_refresh_token")

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
TIMEOUT = 30


class MessageRejected(Exception):
    """The message can never be delivered (e.g. a bad recipient address)."""


class MailTransportError(Exception):
    """Delivery failed in a way that may succeed later."""


def email_settings():
    """The effective email settings: the ini, overridden by admin settings."""
    settings = {name: g.config.get(name, "") or "" for name in SETTINGS}
    for name, value in site_settings.get_settings("email").items():
        if name in SETTINGS:
            settings[name] = value
    if settings["mail_transport"] not in TRANSPORTS:
        settings["mail_transport"] = "none"
    return settings


def from_address():
    """The address tippr's own mail is sent from (mail_from).

    Defaults to noreply@<domain>. With the gmail transport it should be the
    Google account or one of its "send mail as" addresses.
    """
    return email_settings()["mail_from"] or "noreply@%s" % g.domain


def open_transport(settings=None):
    settings = settings or email_settings()
    transport = settings["mail_transport"]
    if transport == "smtp":
        return SMTPTransport(settings)
    elif transport == "gmail":
        return GmailTransport(settings)
    return None


class SMTPTransport:
    def __init__(self, settings):
        server = settings["smtp_server"] or "localhost"
        security = settings["smtp_security"] or "none"
        context = ssl.create_default_context()
        try:
            if security == "ssl":
                self.session = smtplib.SMTP_SSL(server, timeout=TIMEOUT,
                                                context=context)
            else:
                self.session = smtplib.SMTP(server, timeout=TIMEOUT)
                if security == "starttls":
                    self.session.starttls(context=context)
            if settings["smtp_username"]:
                self.session.login(settings["smtp_username"],
                                   settings["smtp_password"])
        except (OSError, smtplib.SMTPException) as e:
            raise MailTransportError("SMTP connection to %s failed: %s"
                                     % (server, e))

    def send(self, from_addr, to_addrs, message):
        try:
            self.session.sendmail(from_addr, to_addrs, message)
        except (smtplib.SMTPRecipientsRefused,
                smtplib.SMTPSenderRefused) as e:
            raise MessageRejected(str(e))
        except (OSError, smtplib.SMTPException) as e:
            raise MailTransportError(str(e))

    def close(self):
        try:
            self.session.quit()
        except (OSError, smtplib.SMTPException):
            pass


class GmailTransport:
    def __init__(self, settings):
        self.client_id = settings["gmail_client_id"]
        self.client_secret = settings["gmail_client_secret"]
        self.refresh_token = settings["gmail_refresh_token"]
        if not (self.client_id and self.client_secret and self.refresh_token):
            raise MailTransportError(
                "gmail transport needs gmail_client_id, gmail_client_secret "
                "and gmail_refresh_token")
        self.access_token = None
        self.expires_at = 0

    def _token(self):
        if self.access_token and time.time() < self.expires_at - 60:
            return self.access_token
        try:
            response = requests.post(GOOGLE_TOKEN_URL, timeout=TIMEOUT, data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            })
        except requests.RequestException as e:
            raise MailTransportError("Google token request failed: %s" % e)
        if response.status_code != 200:
            # e.g. invalid_grant: the refresh token was revoked or expired
            raise MailTransportError("Google token request failed: %s %s"
                                     % (response.status_code, response.text))
        data = response.json()
        self.access_token = data["access_token"]
        self.expires_at = time.time() + int(data.get("expires_in", 3600))
        return self.access_token

    def send(self, from_addr, to_addrs, message):
        if isinstance(message, str):
            message = message.encode("utf-8")
        raw = base64.urlsafe_b64encode(message).decode("ascii")
        try:
            response = requests.post(
                GMAIL_SEND_URL, timeout=TIMEOUT, json={"raw": raw},
                headers={"Authorization": "Bearer %s" % self._token()})
        except requests.RequestException as e:
            raise MailTransportError("Gmail send failed: %s" % e)
        if response.status_code == 400:
            # malformed message or recipient; retrying won't help
            raise MessageRejected("Gmail rejected the message: %s"
                                  % response.text)
        if response.status_code != 200:
            raise MailTransportError("Gmail send failed: %s %s"
                                     % (response.status_code, response.text))

    def close(self):
        pass

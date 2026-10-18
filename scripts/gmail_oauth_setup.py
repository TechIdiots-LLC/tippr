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
"""Connect a Google account to send tippr's email through the Gmail API.

Run it as root with:

    sudo tippr-run /home/tippr/src/tippr/scripts/gmail_oauth_setup.py

You need an OAuth client of type "Desktop app" from the Google Cloud console
(APIs & Services > Credentials), with the Gmail API enabled for the project.
See docs/EMAIL.md.

The script prints a Google sign-in link. After you approve access, Google
sends your browser to a http://localhost address that won't load; copy that
address from the browser's address bar and paste it here. The script then
saves the client and refresh token to the site's email settings (the same
ones as /admin/email) and switches mail_transport to gmail.
"""

import base64
import hashlib
import secrets
import urllib.parse

import requests

from r2.lib import mail_transport, site_settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPE = "https://www.googleapis.com/auth/gmail.send"
REDIRECT_URI = "http://localhost:8765/"


def main():
    current = mail_transport.email_settings()
    client_id = (input("OAuth client ID [%s]: " % current["gmail_client_id"])
                 .strip() or current["gmail_client_id"])
    client_secret = (input("OAuth client secret%s: " % (
                         " [keep current]" if current["gmail_client_secret"]
                         else "")).strip()
                     or current["gmail_client_secret"])
    if not client_id or not client_secret:
        raise SystemExit("A client ID and secret are required.")

    # PKCE, so an intercepted code can't be redeemed by anyone else
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).decode("ascii").rstrip("=")
    state = secrets.token_urlsafe(16)

    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    print("\nOpen this link, sign in with the Google account tippr should send")
    print("mail as, and allow access:\n")
    print(url)
    print("\nYour browser will then try to open %s... and fail." % REDIRECT_URI)
    redirected = input("Paste the full address from the address bar here: ")

    query = urllib.parse.parse_qs(urllib.parse.urlparse(redirected.strip()).query)
    if query.get("error"):
        raise SystemExit("Google returned an error: %s" % query["error"][0])
    if query.get("state", [None])[0] != state:
        raise SystemExit("That address is not from this sign-in (state mismatch).")
    code = query.get("code", [None])[0]
    if not code:
        raise SystemExit("No authorization code in that address.")

    response = requests.post(mail_transport.GOOGLE_TOKEN_URL, timeout=30, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    })
    if response.status_code != 200:
        raise SystemExit("Token exchange failed: %s %s"
                         % (response.status_code, response.text))
    refresh_token = response.json().get("refresh_token")
    if not refresh_token:
        raise SystemExit("Google did not return a refresh token. Remove tippr's "
                         "access at https://myaccount.google.com/permissions "
                         "and run this again.")

    settings = site_settings.get_settings("email")
    settings.update({
        "mail_transport": "gmail",
        "gmail_client_id": client_id,
        "gmail_client_secret": client_secret,
        "gmail_refresh_token": refresh_token,
    })
    site_settings.save_settings("email", settings)
    print("\nSaved. tippr now sends email through Gmail.")
    print("Use /admin/email to send a test message.")


main()

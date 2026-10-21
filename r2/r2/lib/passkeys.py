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
"""Passkeys (WebAuthn) as a two-factor method (r2.lib.two_factor).

A passkey lives on the member's phone, computer or security key, and signs
in with a fingerprint, face or PIN. Here it stands in for a code from an
authenticator app: anywhere a code is asked for, "use a passkey" checks
one (authenticate), and the form gets a short-lived token that counts as
the code (two_factor.passkey_token).

Each ceremony is two steps: options from the server (with a challenge
kept here for a few minutes, under a token), then the browser's answer,
verified by the webauthn library against the site's address.
"""

import json
import secrets
from urllib.parse import urlparse

from pylons import app_globals as g

from r2.lib import two_factor

TTL = 300  # seconds to answer the browser's prompt


class PasskeyError(Exception):
    pass


def _site():
    """(relying party id, origin): the site's host name, and its https
    address. A passkey works only on the site that made it."""
    endpoint = urlparse(g.https_endpoint or "https://%s" % g.domain)
    return endpoint.hostname, "%s://%s" % (endpoint.scheme, endpoint.netloc)


def _hold(kind, account, challenge):
    from webauthn.helpers import bytes_to_base64url
    token = secrets.token_urlsafe(18)
    g.gencache.set("passkey_%s:%s" % (kind, token), {
        "account_id": account._id,
        "challenge": bytes_to_base64url(challenge)}, time=TTL)
    return token


def _take(kind, account, token):
    """The challenge kept for this ceremony (once only)."""
    from webauthn.helpers import base64url_to_bytes
    key = "passkey_%s:%s" % (kind, token or "")
    held = g.gencache.get(key) if token else None
    g.gencache.delete(key)
    if not held or held["account_id"] != account._id:
        raise PasskeyError("That took too long; please try again.")
    return base64url_to_bytes(held["challenge"])


def registration_options(account):
    """Options for the browser to make a new passkey: (json, token)."""
    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers import base64url_to_bytes
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )
    rp_id, origin = _site()
    existing = two_factor.methods(account, "passkey")
    if len(existing) >= two_factor.MAX_METHODS:
        raise PasskeyError("That's as many passkeys as an account can have.")
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=g.site_name or rp_id,
        user_id=account._id36.encode("ascii"),
        user_name=account.name,
        user_display_name=account.name,
        timeout=TTL * 1000,
        # the same passkey can't be added twice
        exclude_credentials=[
            PublicKeyCredentialDescriptor(
                id=base64url_to_bytes(m["credential_id"]))
            for m in existing],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED),
    )
    return options_to_json(options), _hold("reg", account, options.challenge)


def register(account, token, credential, name=None):
    """Check the browser's new passkey and add it; returns whether it's the
    first method (two-factor just turned on)."""
    from webauthn import verify_registration_response
    from webauthn.helpers import bytes_to_base64url
    challenge = _take("reg", account, token)
    rp_id, origin = _site()
    try:
        verified = verify_registration_response(
            credential=credential, expected_challenge=challenge,
            expected_rp_id=rp_id, expected_origin=origin)
    except Exception as e:
        g.log.info("passkeys: %s's new passkey wasn't accepted: %s",
                   account.name, e)
        raise PasskeyError("That passkey couldn't be added.")
    try:
        transports = ",".join(
            json.loads(credential)["response"].get("transports") or [])
    except (ValueError, KeyError, TypeError, AttributeError):
        transports = ""
    try:
        return two_factor.add_passkey(
            account, bytes_to_base64url(verified.credential_id),
            bytes_to_base64url(verified.credential_public_key),
            verified.sign_count, transports[:100], name)
    except two_factor.TooManyMethods:
        raise PasskeyError("That's as many passkeys as an account can have.")


def authentication_options(account):
    """Options for the browser to sign with one of account's passkeys:
    (json, token)."""
    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers import base64url_to_bytes
    from webauthn.helpers.structs import (
        AuthenticatorTransport,
        PublicKeyCredentialDescriptor,
        UserVerificationRequirement,
    )
    passkeys = two_factor.methods(account, "passkey")
    if not passkeys:
        raise PasskeyError("This account has no passkeys.")
    known = {t.value for t in AuthenticatorTransport}

    def descriptor(m):
        transports = [AuthenticatorTransport(t) for t in
                      (m["transports"] or "").split(",") if t in known]
        return PublicKeyCredentialDescriptor(
            id=base64url_to_bytes(m["credential_id"]),
            transports=transports or None)

    rp_id, origin = _site()
    options = generate_authentication_options(
        rp_id=rp_id, timeout=TTL * 1000,
        allow_credentials=[descriptor(m) for m in passkeys],
        user_verification=UserVerificationRequirement.PREFERRED)
    return options_to_json(options), _hold("auth", account, options.challenge)


def authenticate(account, token, credential):
    """Check the browser's answer: one of account's passkeys signed the
    challenge. Returns a token that counts as a two-factor code."""
    from webauthn import verify_authentication_response
    from webauthn.helpers import base64url_to_bytes
    challenge = _take("auth", account, token)
    try:
        credential_id = json.loads(credential)["id"]
    except (ValueError, KeyError, TypeError):
        raise PasskeyError("That passkey answer wasn't readable.")
    method = next((m for m in two_factor.methods(account, "passkey")
                   if m["credential_id"] == credential_id), None)
    if not method:
        raise PasskeyError("That passkey isn't one of this account's.")
    rp_id, origin = _site()
    try:
        verified = verify_authentication_response(
            credential=credential, expected_challenge=challenge,
            expected_rp_id=rp_id, expected_origin=origin,
            credential_public_key=base64url_to_bytes(method["public_key"]),
            credential_current_sign_count=method["sign_count"] or 0)
    except Exception as e:
        g.log.info("passkeys: %s's passkey wasn't accepted: %s",
                   account.name, e)
        raise PasskeyError("That passkey wasn't accepted.")
    two_factor.passkey_used(method["id"], verified.new_sign_count)
    return two_factor.passkey_token(account)

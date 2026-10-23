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

# Where a new passkey was saved, by the AAGUID its authenticator reports
# (from github.com/passkeydeveloper/passkey-authenticator-aaguids), for its
# name in the member's list: "iCloud Keychain" says more than "passkey 2".
PROVIDERS = {
    "ea9b8d66-4d01-1d21-3ce4-b6b48cb575d4": "Google Password Manager",
    "adce0002-35bc-c60a-648b-0b25f1f05503": "Chrome on Mac",
    "b5397666-4885-aa6b-cebf-e52262a439a2": "Chromium",
    "771b48fd-d3d4-4f74-9232-fc157ab0507a": "Edge on Mac",
    "08987058-cadc-4b81-b6e1-30de50dcbe96": "Windows Hello",
    "9ddd1817-af5a-4672-a2b9-3e3dd95000a9": "Windows Hello",
    "6028b017-b1d4-4c02-b4b3-afcdafc96bb2": "Windows Hello",
    "d3452668-01fd-4c12-926c-83a4204853aa": "Microsoft Password Manager",
    "fbfc3007-154e-4ecc-8c0b-6e020557d7bd": "iCloud Keychain",
    "dd4ec289-e01d-41c9-bb89-70fa845d4bf2": "iCloud Keychain",
    "53414d53-554e-4700-0000-000000000000": "Samsung Pass",
    "bada5566-a7aa-401f-bd96-45619a55120d": "1Password",
    "d548826e-79b4-db40-a3d8-11116f7e8349": "Bitwarden",
    "531126d6-e717-415c-9320-3d9aa6981239": "Dashlane",
    "b84e4048-15dc-4dd0-8640-f4f60813c8af": "NordPass",
    "0ea242b4-43c4-4a1b-8b17-dd6d0b6baec6": "Keeper",
    "b78a0a55-6ef8-d246-a042-ba0f6d55050c": "LastPass",
    "f3809540-7f14-49c1-a8b3-8f813b225541": "Enpass",
    "50726f74-6f6e-5061-7373-50726f746f6e": "Proton Pass",
    "fdb141b2-5d84-443e-8a35-4698c205a502": "KeePassXC",
    "eaecdef2-1c31-5634-8639-f1cbd9c00a08": "KeePassDX",
    "b35a26b2-8f6e-4697-ab1d-d44db4da28c6": "Zoho Vault",
}


def provider_name(aaguid, transports):
    """A name for a new passkey: where it was saved, or "security key" for
    one on a USB or NFC key nobody listed, else None (the usual name)."""
    name = PROVIDERS.get((aaguid or "").lower())
    if name:
        return name
    if set(transports or ()) & {"usb", "nfc"}:
        return "security key"
    return None


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
        transport_list = list(
            json.loads(credential)["response"].get("transports") or [])
    except (ValueError, KeyError, TypeError, AttributeError):
        transport_list = []
    transports = ",".join(transport_list)
    try:
        return two_factor.add_passkey(
            account, bytes_to_base64url(verified.credential_id),
            bytes_to_base64url(verified.credential_public_key),
            verified.sign_count, transports[:100], name,
            default_name=provider_name(verified.aaguid, transport_list))
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

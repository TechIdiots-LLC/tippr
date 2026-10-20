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
"""HTTP for the payment providers' APIs: JSON back, PaymentError on any
failure (with the provider's own message when it gives one)."""

import requests
from pylons import app_globals as g

from r2.lib.payments import PaymentError

TIMEOUT = 30


def _message(response):
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict):
        # PayPal: message/details; Stripe: error.message; Coinbase:
        # errorMessage/message; BitPay: error
        error = body.get("error")
        if isinstance(error, dict):
            return error.get("message") or str(error)
        details = body.get("details")
        if isinstance(details, list) and details:
            detail = details[0]
            if isinstance(detail, dict):
                return "%s: %s" % (detail.get("issue", ""),
                                   detail.get("description", ""))
        return (body.get("message") or body.get("errorMessage") or
                body.get("error_description") or error or str(body)[:200])
    return str(body)[:200]


def call(method, url, ok=(200, 201), **kwargs):
    """Make the request; returns (status code, parsed JSON)."""
    kwargs.setdefault("timeout", TIMEOUT)
    try:
        response = requests.request(method, url, **kwargs)
    except requests.RequestException as e:
        raise PaymentError("can't reach %s: %s" % (url.split("/")[2], e))
    if response.status_code not in ok:
        message = _message(response)
        g.log.warning("payments: %s %s -> %s: %s", method, url,
                      response.status_code, message)
        raise PaymentError((message or "").strip() or
                           "HTTP %s" % response.status_code)
    if not response.content:
        return response.status_code, {}
    try:
        return response.status_code, response.json()
    except ValueError:
        raise PaymentError("%s didn't send JSON" % url.split("/")[2])

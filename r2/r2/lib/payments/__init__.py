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
"""Taking payments (gold, coins, gift codes and sold ads).

Nothing is built in: the site owner turns on the payment providers they
have accounts with on /admin/payments and enters their own API keys there
(saved settings override the ini and apply without a restart):

- PayPal (Orders API): PayPal, Venmo, Pay Later and cards on PayPal's page.
- Stripe Checkout: cards, Google Pay, Apple Pay and the other methods
  turned on in the Stripe dashboard.
- Coinbase Business checkouts: USDC (a dollar stablecoin) on Base.
- BitPay invoices: Bitcoin and the other coins BitPay takes.

Every provider works the same way. The buyer picks one on the payment
page, which posts to /payments/checkout; that works out the price on the
server (never from the form), records a payment (the "payments" table),
creates the provider's checkout and sends the buyer to the provider's own
page. When they come back (/payments/return/<id>) or the provider sends a
webhook (/api/payments/webhook/<provider>), we never trust what we're told:
we ask the provider's API for the payment's state and act on that
(sync()). So webhooks need no signing secret, and a payment completes even
if the site never hears a webhook, as long as the buyer comes back.

A payment moves from "created" (checkout made) or "pending" (paid, waiting
for confirmations: crypto) to "paid" (the purchase is delivered, exactly
once: the status change is a conditional UPDATE), and may later become
"refunded" (the purchase is taken back). "failed" and "expired" checkouts
are never paid. Refunds go through the provider's API (PayPal, Stripe,
Coinbase); BitPay payments are refunded in its dashboard, then marked
refunded here.

What a payment buys is its "purpose": "gold" (anything bought on /gold, via
the payment blob in the hardcache) or "ad" (a sold ad's campaign). The
provider modules are in this package; r2.controllers.payments has the
pages.
"""

import json
import threading
import uuid
from datetime import datetime

import sqlalchemy as sa
from pylons import app_globals as g
from pylons.i18n import N_

from r2.lib import site_settings
from r2.lib.db.tdb_sql import create_table, index_str, make_metadata

GROUP = "payments"

# provider -> (name shown on the admin page, label on the buy buttons)
PROVIDERS = {
    "paypal": (N_("PayPal"), N_("PayPal")),
    "stripe": (N_("Stripe"), N_("Card / Google Pay")),
    "coinbase": (N_("Coinbase"), N_("Crypto (USDC)")),
    "bitpay": (N_("BitPay"), N_("Bitcoin")),
}
PROVIDER_ORDER = ["paypal", "stripe", "coinbase", "bitpay"]

# a prefix for each provider's transaction ids in the gold table
TRANSACTION_PREFIX = {
    "paypal": "PO",
    "stripe": "SC",
    "coinbase": "CB",
    "bitpay": "BP",
}

# setting name -> default; the secrets are never sent back to the browser
SETTINGS = {
    "paypal_enabled": False,
    "paypal_mode": "sandbox",
    "paypal_client_id": "",
    "paypal_client_secret": "",
    "stripe_enabled": False,
    "stripe_secret_key": "",
    "coinbase_enabled": False,
    "coinbase_mode": "sandbox",
    "coinbase_key_id": "",
    "coinbase_key_secret": "",
    "bitpay_enabled": False,
    "bitpay_mode": "test",
    "bitpay_token": "",
    "gold_enabled": True,
    "ads_enabled": True,
}
SECRET_SETTINGS = ("paypal_client_secret", "stripe_secret_key",
                   "coinbase_key_secret", "bitpay_token")
MODES = {
    "paypal": ("sandbox", "live"),
    "coinbase": ("sandbox", "live"),
    "bitpay": ("test", "live"),
}
# what a provider needs before it can be turned on
REQUIRED = {
    "paypal": ("paypal_client_id", "paypal_client_secret"),
    "stripe": ("stripe_secret_key",),
    "coinbase": ("coinbase_key_id", "coinbase_key_secret"),
    "bitpay": ("bitpay_token",),
}

CURRENCY = "USD"

STATUSES = ("created", "pending", "paid", "failed", "expired", "refunded")
# the statuses a payment can still become paid from
OPEN_STATUSES = ("created", "pending")
STATUS_NAMES = {
    "created": N_("waiting for the buyer"),
    "pending": N_("confirming"),
    "paid": N_("paid"),
    "failed": N_("failed"),
    "expired": N_("expired"),
    "refunded": N_("refunded"),
}


class PaymentError(Exception):
    """A provider refused a request, or couldn't be reached."""


def _bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def payment_settings():
    """The effective settings: the ini (payments_<name>), overridden by
    /admin/payments."""
    settings = {}
    for name, default in SETTINGS.items():
        value = g.config.get("payments_" + name)
        settings[name] = default if value in (None, "") else value
    for name, value in site_settings.get_settings(GROUP).items():
        if name in SETTINGS:
            settings[name] = value
    for name, default in SETTINGS.items():
        if isinstance(default, bool):
            settings[name] = _bool(settings[name])
        else:
            settings[name] = str(settings[name] or "").strip()
    for provider, modes in MODES.items():
        if settings[provider + "_mode"] not in modes:
            settings[provider + "_mode"] = modes[0]
    return settings


def configured(provider, settings=None):
    settings = settings or payment_settings()
    return all(settings[name] for name in REQUIRED[provider])


def enabled_providers(purpose=None, settings=None):
    """The providers buyers can pay with (for purpose "gold" or "ad", or
    for anything), in the order the buttons show."""
    settings = settings or payment_settings()
    if purpose == "gold" and not settings["gold_enabled"]:
        return []
    if purpose == "ad" and not settings["ads_enabled"]:
        return []
    return [p for p in PROVIDER_ORDER
            if settings[p + "_enabled"] and configured(p, settings)]


def provider_module(provider):
    if provider == "paypal":
        from r2.lib.payments import paypal as module
    elif provider == "stripe":
        from r2.lib.payments import stripe_checkout as module
    elif provider == "coinbase":
        from r2.lib.payments import coinbase as module
    elif provider == "bitpay":
        from r2.lib.payments import bitpay as module
    else:
        raise ValueError("unknown payment provider %r" % provider)
    return module


def can_refund(provider):
    """Whether refunds go through the provider's API (BitPay's are made in
    its dashboard, then marked refunded here)."""
    return provider in ("paypal", "stripe", "coinbase")


def can_check(provider):
    """Whether the admin page can test the saved keys."""
    return provider != "bitpay"


def webhook_url(provider):
    return "%s/api/payments/webhook/%s" % (g.https_endpoint.rstrip("/"),
                                            provider)


def return_url(payment_id):
    return "%s/payments/return/%s" % (g.https_endpoint.rstrip("/"),
                                      payment_id)


def cancel_url(payment_id):
    return "%s/payments/cancel/%s" % (g.https_endpoint.rstrip("/"),
                                      payment_id)


def dollars(pennies):
    """3.99 as the string "3.99" (what the providers' APIs take)."""
    return "%d.%02d" % divmod(int(pennies), 100)


###############################################################################
# Prices
###############################################################################

def gold_price(months):
    """(months, pennies) for buying months of gold, coins or a gift: by the
    month up to 11, then whole years at the yearly price (as the payment
    page shows it)."""
    months = int(months)
    if months < 1:
        raise ValueError("months must be at least 1")
    if months >= 12:
        years = months // 12
        return years * 12, g.gold_year_price.pennies * years
    return months, g.gold_month_price.pennies * months


###############################################################################
# The payments table
###############################################################################

ENGINE = g.dbm.get_engine("main")
METADATA = make_metadata(ENGINE)

payments_table = sa.Table(
    "payments", METADATA,
    # ours, also given to the provider (so its webhooks and dashboard show
    # it) and in our return address
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("provider", sa.String, nullable=False),
    # gold or ad
    sa.Column("purpose", sa.String, nullable=False),
    # the buyer, if signed in (gift codes can be bought signed out)
    sa.Column("account_id", sa.BigInteger, nullable=True),
    sa.Column("email", sa.String, nullable=True),
    sa.Column("pennies", sa.Integer, nullable=False),
    sa.Column("currency", sa.String, nullable=False),
    sa.Column("description", sa.String, nullable=False, default=""),
    sa.Column("status", sa.String, nullable=False),
    # the provider's checkout: PayPal order, Stripe Checkout Session,
    # Coinbase checkout or BitPay invoice id
    sa.Column("provider_ref", sa.String, nullable=True),
    # what a refund needs: PayPal's capture id, Stripe's payment intent
    sa.Column("capture_ref", sa.String, nullable=True),
    # gold: the payment blob's code; ad: "<link fullname>:<campaign id36>"
    sa.Column("reference", sa.String, nullable=True),
    # gold: months; ad: nothing yet. JSON.
    sa.Column("data", sa.Text, nullable=True),
    sa.Column("created", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated", sa.DateTime(timezone=True), nullable=False),
    sa.Column("paid", sa.DateTime(timezone=True), nullable=True),
    # who refunded it (an admin), or None if the provider told us
    sa.Column("refunded_by", sa.BigInteger, nullable=True),
)
create_table(payments_table, [
    index_str(payments_table, "provider_ref", "provider, provider_ref"),
    index_str(payments_table, "capture_ref", "provider, capture_ref"),
    index_str(payments_table, "account_id", "account_id"),
    index_str(payments_table, "created", "created"),
    index_str(payments_table, "reference", "purpose, reference"),
])


def _now():
    return datetime.now(g.tz)


def _row(row):
    if row is None:
        return None
    payment = dict(row)
    try:
        payment["data"] = json.loads(payment["data"] or "{}")
    except ValueError:
        payment["data"] = {}
    return payment


def create_payment(provider, purpose, pennies, description, reference,
                   account=None, email=None, data=None):
    payment = {
        "id": uuid.uuid4().hex[:24],
        "provider": provider,
        "purpose": purpose,
        "account_id": account._id if account else None,
        "email": email or None,
        "pennies": int(pennies),
        "currency": CURRENCY,
        "description": description[:250],
        "status": "created",
        "provider_ref": None,
        "capture_ref": None,
        "reference": reference,
        "data": json.dumps(data or {}),
        "created": _now(),
        "updated": _now(),
    }
    with ENGINE.begin() as conn:
        conn.execute(payments_table.insert().values(**payment))
    return get(payment["id"])


def get(payment_id):
    if not payment_id:
        return None
    with ENGINE.connect() as conn:
        row = conn.execute(sa.select(payments_table).where(
            payments_table.c.id == str(payment_id))).mappings().first()
    return _row(row)


def by_provider_ref(provider, ref, column="provider_ref"):
    if not ref:
        return None
    col = payments_table.c[column]
    with ENGINE.connect() as conn:
        row = conn.execute(sa.select(payments_table).where(
            (payments_table.c.provider == provider) &
            (col == str(ref)))).mappings().first()
    return _row(row)


def update(payment_id, **values):
    values["updated"] = _now()
    with ENGINE.begin() as conn:
        conn.execute(payments_table.update().where(
            payments_table.c.id == payment_id).values(**values))


def _transition(payment_id, from_statuses, to_status, **values):
    """Change the status only if it's one of from_statuses; True if this
    call changed it (so whoever gets True does the work, once)."""
    values.update(status=to_status, updated=_now())
    with ENGINE.begin() as conn:
        result = conn.execute(payments_table.update().where(
            (payments_table.c.id == payment_id) &
            (payments_table.c.status.in_(from_statuses))).values(**values))
    return result.rowcount == 1


def recent(limit=50, status=None):
    query = sa.select(payments_table)
    if status:
        query = query.where(payments_table.c.status == status)
    query = query.order_by(payments_table.c.created.desc()).limit(limit)
    with ENGINE.connect() as conn:
        return [_row(row) for row in conn.execute(query).mappings()]


def for_reference(purpose, reference):
    """The payments for one thing (an ad's campaign), newest first."""
    with ENGINE.connect() as conn:
        return [_row(row) for row in conn.execute(
            sa.select(payments_table)
            .where((payments_table.c.purpose == purpose) &
                   (payments_table.c.reference == reference))
            .order_by(payments_table.c.created.desc())).mappings()]


###############################################################################
# Checkout, syncing and refunds
###############################################################################

# purpose -> (on_paid(payment), on_refunded(payment)); registered by the
# code that sells things (r2.lib.payments.gold, r2.lib.payments.ads)
_handlers = {}
_handlers_lock = threading.Lock()


def register(purpose, on_paid, on_refunded):
    with _handlers_lock:
        _handlers[purpose] = (on_paid, on_refunded)


def _handler(purpose):
    if purpose not in _handlers:
        # importing them registers them
        if purpose == "gold":
            from r2.lib.payments import gold  # noqa: F401
        elif purpose == "ad":
            from r2.lib.payments import ads  # noqa: F401
    return _handlers[purpose]


def start_checkout(payment, buyer_email=None):
    """Create the provider's checkout for a new payment; returns the
    address to send the buyer to."""
    module = provider_module(payment["provider"])
    settings = payment_settings()
    try:
        provider_ref, url = module.create_checkout(
            payment, settings, return_url(payment["id"]),
            cancel_url(payment["id"]), buyer_email=buyer_email)
    except PaymentError:
        update(payment["id"], status="failed")
        raise
    update(payment["id"], provider_ref=provider_ref)
    return url


def sync(payment, returning=False):
    """Ask the provider what happened to a payment and act on it: deliver
    the purchase when it's paid, take it back when it's refunded. Returns
    the payment as it now stands."""
    if payment is None:
        return None
    if not payment["provider_ref"]:
        return payment
    module = provider_module(payment["provider"])
    settings = payment_settings()
    try:
        state = module.fetch_status(payment, settings, returning=returning)
    except PaymentError as e:
        g.log.warning("payments: can't check %s (%s): %s", payment["id"],
                      payment["provider"], e)
        return payment
    _apply_state(payment, state)
    return get(payment["id"])


def _apply_state(payment, state):
    """state: {"status": one of STATUSES, "capture_ref": ...}"""
    status = state.get("status")
    extra = {}
    if state.get("capture_ref"):
        extra["capture_ref"] = state["capture_ref"]

    if status == "paid":
        if _transition(payment["id"], OPEN_STATUSES + ("failed", "expired"),
                       "paid", paid=_now(), **extra):
            on_paid, _ = _handler(payment["purpose"])
            payment = get(payment["id"])
            try:
                on_paid(payment)
            except Exception:
                # the money is taken: an admin has to sort this out, so
                # make it loud (it's in /admin/errors too)
                g.log.exception("payments: %s was paid but delivering it "
                                "failed", payment["id"])
                raise
    elif status == "refunded":
        if _transition(payment["id"], ("paid",), "refunded", **extra):
            _, on_refunded = _handler(payment["purpose"])
            on_refunded(get(payment["id"]))
    elif status in ("pending", "failed", "expired"):
        _transition(payment["id"], OPEN_STATUSES, status, **extra)
    elif extra:
        update(payment["id"], **extra)


def refunded_pennies(payment):
    """How much of a paid payment has been refunded in part so far."""
    return int(payment["data"].get("refunded_pennies") or 0)


def refund(payment, admin=None, pennies=None, take_back=True):
    """Refund a paid payment through the provider, in full or pennies of it.

    A full refund marks it refunded and (with take_back) takes the purchase
    back; the code selling it passes take_back=False when it's already
    undoing the purchase itself. A partial refund (an ad that showed less
    than was paid for) leaves it paid. Raises PaymentError if the provider
    refuses, or can't refund (BitPay: its refunds are made in its
    dashboard)."""
    if payment["status"] != "paid":
        raise PaymentError("only paid payments can be refunded")
    if not can_refund(payment["provider"]):
        raise PaymentError("%s refunds are made in its dashboard"
                           % PROVIDERS[payment["provider"]][0])
    module = provider_module(payment["provider"])
    already = refunded_pennies(payment)
    if pennies and already + int(pennies) < payment["pennies"]:
        module.refund(payment, payment_settings(), pennies=int(pennies),
                      key="part%d" % (already + int(pennies)))
        data = dict(payment["data"], refunded_pennies=already + int(pennies))
        update(payment["id"], data=json.dumps(data))
        return
    remaining = payment["pennies"] - already
    module.refund(payment, payment_settings(),
                  pennies=remaining if already else None)
    mark_refunded(payment, admin, take_back=take_back)


def mark_refunded(payment, admin=None, take_back=True):
    """Mark a paid payment refunded and take back what it bought: after
    refund(), or after it was refunded outside the site (BitPay's
    dashboard)."""
    if _transition(payment["id"], ("paid",), "refunded",
                   refunded_by=admin._id if admin else None):
        if take_back:
            _, on_refunded = _handler(payment["purpose"])
            on_refunded(get(payment["id"]))
        return True
    return False


def handle_webhook(provider, body, headers):
    """A provider's webhook: find which of our payments it's about and sync
    that one (what the webhook says isn't trusted). Returns the payment,
    or None if it isn't one of ours."""
    module = provider_module(provider)
    try:
        event = json.loads(body or b"{}")
    except ValueError:
        return None
    payment_id, ref, capture_ref = module.webhook_refs(event)
    payment = (get(payment_id) or by_provider_ref(provider, ref) or
               by_provider_ref(provider, capture_ref, "capture_ref"))
    if not payment or payment["provider"] != provider:
        return None
    return sync(payment)


def check_credentials(provider):
    """None if the saved keys work, else what's wrong."""
    if not configured(provider):
        return "not set up"
    try:
        provider_module(provider).check_credentials(payment_settings())
    except PaymentError as e:
        return str(e) or "failed"
    return None

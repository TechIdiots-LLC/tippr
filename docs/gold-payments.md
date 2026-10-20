# Payments: gold and sold ads

tippr takes payments with your own accounts at PayPal, Stripe, Coinbase and BitPay. Nothing is built in: an admin
turns on the providers they use on **/admin/payments** and enters their API keys there. Buyers pick one on the
payment page and pay on the provider's own page, so card details and wallets never touch your server.

| provider | buyers pay with | refunds |
| --- | --- | --- |
| PayPal | PayPal, Venmo (US), Pay Later, or a card without a PayPal account | from /admin/payments |
| Stripe | cards, Google Pay, Apple Pay, Link and the other methods turned on in the Stripe dashboard | from /admin/payments |
| Coinbase | USDC (a dollar stablecoin) from Coinbase or any wallet, on Base | from /admin/payments |
| BitPay | Bitcoin and the other coins BitPay takes | in the BitPay dashboard, then "mark refunded" |

Prices are in US dollars: gold costs `gold_month_price` a month and `gold_year_price` a year (in the ini). The price
is always worked out on the server, never taken from the form.

## Setting up a provider

Save the keys on /admin/payments, then use **test the keys** (PayPal, Stripe and Coinbase). Each provider has a test
mode: try a purchase there before switching to live.

**PayPal.** On [developer.paypal.com](https://developer.paypal.com) open *Apps & Credentials* and create a REST API
app; copy its client ID and secret. Sandbox and live have separate apps (and keys), so set the environment to match.

**Stripe.** In the Stripe dashboard, *Developers > API keys*: the secret key (`sk_test_…` for testing, `sk_live_…`
for real payments). A restricted key (`rk_…`) works if it can write Checkout Sessions and Refunds. Google Pay and Apple
Pay appear on Stripe's page by themselves once they're on under *Settings > Payment methods*.

**Coinbase.** Coinbase Commerce, which the old "Bitcoin" button used, has shut down; tippr uses Coinbase Business
checkouts instead. In the [CDP portal](https://portal.cdp.coinbase.com), for the project linked to your Coinbase
Business account, create a *secret API key* and copy its ID and secret (Ed25519, the default, or ECDSA). Sandbox
makes test checkouts.

**BitPay.** In the BitPay dashboard, *Payment Tools > API Tokens*: add a point-of-sale token **without** "require
authentication". Test mode uses test.bitpay.com, which needs its own test account and token.

## Webhooks (optional)

Payments complete when the buyer comes back from paying, so webhooks aren't required. With them, a payment also
completes if the buyer closes the window before coming back (or a crypto payment confirms later), and refunds or
chargebacks made in the provider's dashboard reach the site. /admin/payments shows each provider's webhook address,
`https://<your domain>/api/payments/webhook/<provider>`:

- PayPal: in the app's settings, a webhook for *Checkout order approved*, *Payment capture completed*, *denied* and
  *refunded*.
- Stripe: *Developers > Webhooks*, an endpoint for `checkout.session.completed`,
  `checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed`, `checkout.session.expired` and
  `charge.refunded`.
- Coinbase: webhooks are created with the CDP command line tool, subscribed to the `checkout.payment` events.
- BitPay: nothing to do; each invoice tells BitPay where to send its notifications.

A webhook is only a cue. The site never acts on what a webhook says: it asks the provider's API about the payment
and acts on that answer, so webhooks need no signing secret and a forged one can't do anything.

## How a payment works

1. The payment page (`goldpayment.html`) makes a *payment blob* in the hardcache describing the purchase (what, how
   many months, for whom) and shows a button per provider. Each posts the blob's code to `/payments/checkout`.
2. `r2.lib.payments.gold.checkout` checks the blob, prices it (`payments.gold_price`), records a row in the `payments`
   table (PostgreSQL, so it moves with backups) and creates the provider's checkout: a PayPal order, a Stripe Checkout
   Session, a Coinbase checkout or a BitPay invoice. The buyer is sent to the provider's page.
3. The provider sends the buyer back to `/payments/return/<id>`. The site asks the provider about the payment
   (`payments.sync`); for PayPal, that's when the order is captured and the money moves. Crypto payments may show as
   "confirming" until the network confirms them.
4. Once the provider says it's paid, the status changes to `paid` with a conditional update, so the purchase is
   delivered exactly once however many times the return page and webhooks ask. Delivery is the same code every gold
   purchase uses (`GoldPaymentController.complete_gold_purchase` in `r2/r2/controllers/ipn.py`): gold days, coins, a
   gift (with its message, and the gilding), or a gift code sent by message or email.
5. A refund (from /admin/payments, or one the provider reports) takes the purchase back with `reverse_gold_purchase`
   and tells the buyer. A gift code that's already out can't be taken back.

Statuses: `created` (waiting for the buyer), `pending` (paid, confirming), `paid`, `failed`, `expired`, `refunded`.
The latest payments are on /admin/payments with buttons to check one with the provider and to refund it.

Code: `r2/r2/lib/payments/` (the shared layer in `__init__.py`, one module per provider, and `gold.py`),
`r2/r2/controllers/payments.py` (checkout, return, webhooks), `/admin/payments` (`AdminPaymentSettings`,
`adminpaymentsettings.html`, `POST_payment_settings` and `POST_payment_action` in `api.py`).

## Sold ads

Advertisers (/promoted) pay a campaign's whole budget when they submit it, with the same providers ("pay" in the
campaign list, `/promoted/pay/<ad>/<campaign>`). The ad is reviewed as before, and:

- **Rejected** (before the campaign has started showing): the payment is refunded in full, and the rejection email
  says so.
- **Budget changed, campaign deleted, or paid twice**: that payment is refunded in full; after a budget change the
  advertiser pays the new amount.
- **Showed less than paid for**: the refund page (sponsors only) refunds the unspent part through the provider.
- **Refunded in the provider's dashboard**: the campaign becomes unpaid and won't run.

BitPay payments can't be refunded from the site: the campaign's log says which payment needs a refund, which is made
in BitPay's dashboard and then marked refunded on /admin/payments.

How it fits reddit's ad code: reddit put an authorization hold on a card (authorize.net) and charged it the day
before the campaign ran. A campaign paid here gets a `Bid` that's already charged (payment method
`PROVIDER_PAYMENT_METHOD_ID`, in `r2/r2/lib/payments/ads.py`), so the daily charge step leaves it alone, and voiding or
refunding that bid (`r2/r2/lib/authorize/interaction.py`) refunds the payment through the provider instead. If no
provider is set up for ads, an authorize.net site (`authorizenetapi`) keeps its card form.

## Subscriptions and the old buttons

Gold subscriptions (autorenew) still go through the old flows: PayPal hosted subscription buttons (the
`PAYPAL_BUTTONID_*` ini settings and IPNs) and Stripe's card form (the `stripe_*` secrets). For one-time purchases, a
provider turned on at /admin/payments replaces the old button for the same provider.

Coins (spent on /gold) need no provider: `/api/spendcoins` applies them at once.

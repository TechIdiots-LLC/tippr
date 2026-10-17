# Email

tippr sends email for account verification, password resets, email-change
notices, gold receipts and optional message notifications. Mail is queued in
the database and sent every minute by `tippr-job-email.timer`.

How mail is sent is set by `mail_transport`:

| `mail_transport` | Sends through |
|---|---|
| `none` (default) | Nothing. Mail stays queued until a transport is set up. |
| `smtp` | An SMTP server, with optional login and STARTTLS/SSL. Use this for transactional mail services (Brevo, SMTP2GO, Mailjet, Amazon SES, ...) or a local mail server. |
| `gmail` | A Google account, through the Gmail API with OAuth2. |

The settings can be changed while the site is running at **`/admin/email`**
(admin mode required). Values saved there override `r2/example.ini` /
`development.update`, take effect immediately, and are stored in ZooKeeper
(`/tippr/settings/email`). The page can also send a test message.

## SMTP

| Setting | Example |
|---|---|
| `smtp_server` | `smtp-relay.brevo.com:587` |
| `smtp_security` | `starttls` (port 587), `ssl` (port 465) or `none` |
| `smtp_username` / `smtp_password` | from the mail service |

Send from an address on your own domain and add the SPF and DKIM DNS records
the service gives you, or messages are likely to end up in spam.

## Gmail (OAuth)

This sends as a Google account, using only the `gmail.send` permission
(tippr can't read the mailbox). Gmail sends as that account: it replaces the
From address unless it is one of the account's "Send mail as" addresses.
Google limits sending to a few hundred messages a day for personal accounts
and about 2,000 for Google Workspace.

### 1. Create an OAuth client

In the [Google Cloud console](https://console.cloud.google.com/), with the
Google account tippr will send as:

1. Create a project (or pick one).
2. **APIs & Services > Library**: enable the **Gmail API**.
3. **APIs & Services > OAuth consent screen**:
   - **Google Workspace account:** choose user type **Internal**. No Google
     review is needed and the authorization doesn't expire.
   - **Personal Gmail account:** choose **External**, add yourself as a test
     user, then **publish the app** ("In production"). While an External
     app is in "Testing", Google expires its refresh tokens after 7 days and
     email stops working. You'll see an "unverified app" warning when you
     authorize it; that is expected for your own app.
   - Add the scope `https://www.googleapis.com/auth/gmail.send`.
4. **APIs & Services > Credentials > Create credentials > OAuth client ID**,
   application type **Desktop app**. Keep the client ID and client secret.

### 2. Connect the account

On the tippr server:

```bash
sudo tippr-run /home/tippr/src/tippr/scripts/gmail_oauth_setup.py
```

Enter the client ID and secret, open the link it prints, sign in and allow
access. Google then sends your browser to a `http://localhost:8765/...`
address that won't load. Copy that whole address from the address bar and
paste it into the script. It saves the refresh token and switches
`mail_transport` to `gmail`.

### 3. Test

Open `/admin/email` and send a test message.

If sending later fails with `invalid_grant`, the authorization was revoked or
expired (for example, an External app still in "Testing"). Run the setup
script again.

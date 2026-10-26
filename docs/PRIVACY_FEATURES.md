# Privacy Compliance Features

This document describes the privacy compliance features implemented to support GDPR, CCPA, and general data protection requirements.

## Overview

Tippr provides comprehensive privacy features that allow users to:
- Request exports of their personal data
- View what data is collected about them
- Understand their privacy rights

Administrators can:
- View and manage privacy requests
- Process data export and deletion requests
- Monitor compliance status

## User Features

### Privacy Settings Page

**URL:** `/prefs/privacy`

Users can access their privacy settings to:
- View current privacy-related account settings
- Request a data export
- View status of pending requests
- Download completed data exports

### Deleting an account

Also on `/prefs/privacy` (the old `/prefs/deactivate` address redirects
there). The member chooses whether to keep their posts and comments (shown
by [deleted]) or delete them too, and confirms with their password, plus
their two-factor code if they use two-factor sign-in. Right away they're
logged out everywhere, nobody can log in to the account, and the name can't
be registered again; the password, email address and moderator roles are
removed 90 days later.

### Data Export

Users can request a complete export of their personal data, which includes:

- **Account Information**: Username, email, registration date, preferences
- **Posts**: All submitted posts with titles, content, timestamps
- **Comments**: All comments with content, timestamps, vote scores
- **Private Messages**: Sent and received messages
- **Votes**: History of upvotes and downvotes
- **Subscriptions**: List of subscribed communities
- **Saved and hidden items, friends and blocked users**
- **OAuth Applications**: Connected third-party applications
- **IP History**: the IP addresses the account was used from (logins, and visits at most hourly) and when, from the last 100 days

The export is a ZIP file with two files:
- `README.txt` - what's in the export and how to read it
- `tippr_data_export_<name>_<date>.json` - everything, in sections:
  `account`, `preferences`, `posts`, `comments`, `messages`, `saved`,
  `hidden`, `votes`, `subscriptions`, `friends`, `blocked`, `ip_history`,
  `oauth_apps` (and `export_info` about the export itself)

### Request Lifecycle

1. User requests data export at `/prefs/privacy`
2. Request is queued for background processing
3. Export consumer generates the ZIP file
4. User is notified when ready (and/or can check status)
5. Download link available for 7 days
6. Expired exports are automatically cleaned up

## Admin Features

### Privacy Dashboard

**URL:** `/admin/privacy`

Administrators can view:
- All pending privacy requests
- Request statistics and trends
- Quick actions for common tasks

### User Data View

**URL:** `/admin/privacy/user/:username`

Admins can view a summary of data held for a specific user without downloading the full export.

### Request Processing

**URL:** `/admin/privacy/process`

Admins can approve, reject, or escalate privacy requests. Actions are logged for audit purposes.

### Manual Export Trigger

**URL:** `/admin/privacy/trigger_export`

Admins can manually trigger data exports for users (e.g., in response to formal GDPR requests).

## API Endpoints

### User API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/privacy/request_export` | POST | Request data export |
| `/api/privacy/cancel_request` | POST | Cancel pending request |
| `/api/privacy/requests` | GET | List user's requests |

### Admin API

All admin endpoints require appropriate permissions (`is_admin` or designated privacy officer role).

## Background Processing

The privacy export consumer runs as a systemd service:

```bash
systemctl start tippr-consumer-privacy_export_q@1.service
```

Exports are written to `/var/lib/tippr/privacy_exports` (the installer
creates it, readable by the tippr user only) and kept for 7 days. There's
nothing to configure.

## Data Models

### PrivacyRequest

Stored in Cassandra, tracks:
- Request ID (UUID)
- User account ID
- Request type (export, deletion, access)
- Status (pending, processing, completed, cancelled, failed)
- Timestamps (created, updated, completed)
- Admin notes

### DataExportFile

Tracks generated export files:
- File path
- Creation timestamp
- Expiration timestamp
- File size
- Download count

## Compliance Notes

### GDPR (European Union)

- **Right of Access (Art. 15)**: Data export feature
- **Right to Data Portability (Art. 20)**: Machine-readable JSON format
- **Response Time**: Must respond within 30 days

### CCPA (California)

- **Right to Know**: Data export feature
- **Categories of Data**: Documented in export README
- **Response Time**: Must respond within 45 days

### Best Practices

1. **Verify Identity**: Ensure requests come from legitimate account holders
2. **Document Everything**: All actions are logged
3. **Timely Response**: Monitor pending requests queue
4. **Secure Transmission**: Exports available only via authenticated download
5. **Data Minimization**: Only collect what's necessary

## Troubleshooting

### Export Stuck in "Processing"

Check the consumer service:
```bash
systemctl status tippr-consumer-privacy_export_q@1.service
journalctl -u tippr-consumer-privacy_export_q@1.service
```

### Export File Not Found

Exports may have expired. Check retention settings and file system permissions.

### Permission Denied Errors

Ensure the export directory exists and is writable (re-running the
installer creates it):
```bash
install -d -m 0700 -o tippr /var/lib/tippr/privacy_exports
```

## See Also

- [Privacy Policy](policies/PRIVACY_POLICY.md)
- [Admin Features](ADMIN_FEATURES.md)
- [Production Deployment](PRODUCTION_DEPLOYMENT.md)

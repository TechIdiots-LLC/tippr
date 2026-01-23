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

### Data Export

Users can request a complete export of their personal data, which includes:

- **Account Information**: Username, email, registration date, preferences
- **Posts**: All submitted posts with titles, content, timestamps
- **Comments**: All comments with content, timestamps, vote scores
- **Private Messages**: Sent and received messages
- **Votes**: History of upvotes and downvotes
- **Subscriptions**: List of subscribed communities
- **OAuth Applications**: Connected third-party applications
- **IP History**: Login IP addresses and timestamps (for verification purposes)

The export is provided as a ZIP file containing:
- `README.txt` - Explanation of the export contents
- `account_info.json` - Account and profile data
- `posts.json` - Submitted content
- `comments.json` - Comment history
- `messages.json` - Private messages
- `votes.json` - Voting history
- `subscriptions.json` - Community subscriptions
- `oauth_apps.json` - Connected applications
- `ip_history.json` - IP address log

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

Configuration in `/etc/default/tippr`:
- `PRIVACY_EXPORT_DIR`: Directory for storing export files
- `PRIVACY_EXPORT_RETENTION_DAYS`: Days to retain exports (default: 7)

## Configuration

Add to your INI file:

```ini
# Privacy settings
privacy_export_enabled = true
privacy_export_retention_days = 7
privacy_export_dir = /var/lib/tippr/exports
```

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

Ensure the export directory exists and is writable:
```bash
mkdir -p /var/lib/tippr/exports
chown tippr:tippr /var/lib/tippr/exports
```

## See Also

- [Privacy Policy](policies/PRIVACY_POLICY.md)
- [Admin Features](ADMIN_FEATURES.md)
- [Production Deployment](PRODUCTION_DEPLOYMENT.md)

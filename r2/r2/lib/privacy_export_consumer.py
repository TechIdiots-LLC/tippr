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

"""
Privacy Export Queue Consumer

Background job that processes privacy data export requests.
This consumer listens to the privacy_export_q queue and generates
data export files for users.
"""

import os
import traceback
from datetime import datetime

from pylons import app_globals as g

from r2.lib import amqp
from r2.lib.privacy_export import UserDataExporter
from r2.models import Account, Message
from r2.models.privacy import (
    DataExportFile,
    PrivacyRequest,
    PrivacyRequestStatus,
    PrivacyRequestType,
)


# Directory to store export files
EXPORT_DIRECTORY = '/var/lib/tippr/privacy_exports'


def ensure_export_directory():
    """Ensure the export directory exists."""
    if not os.path.exists(EXPORT_DIRECTORY):
        try:
            os.makedirs(EXPORT_DIRECTORY, mode=0o750)
        except OSError as e:
            g.log.error("Failed to create export directory: %s", e)
            raise


def process_export_request(request_id):
    """
    Process a single data export request.
    
    Args:
        request_id: The ID of the PrivacyRequest to process
    """
    g.log.info("Processing privacy export request: %s", request_id)
    
    try:
        # Get the request
        privacy_request = PrivacyRequest._byID(request_id)
    except Exception as e:
        g.log.error("Failed to find privacy request %s: %s", request_id, e)
        return
    
    # Only process data export requests
    if privacy_request.request_type != PrivacyRequestType.DATA_EXPORT:
        g.log.warning("Request %s is not a data export request", request_id)
        return
    
    # Only process pending or processing requests
    if privacy_request.status not in (PrivacyRequestStatus.PENDING, 
                                       PrivacyRequestStatus.PROCESSING):
        g.log.warning("Request %s is not in a processable state: %s", 
                     request_id, privacy_request.status)
        return
    
    # Mark as processing
    if privacy_request.status == PrivacyRequestStatus.PENDING:
        privacy_request.mark_processing()
    
    try:
        # Get the user
        account = Account._byID36(privacy_request.account_id36, data=True)
        
        if account._deleted:
            privacy_request.mark_failed("Account has been deleted")
            return
        
        g.log.info("Generating data export for user: %s", account.name)
        
        # Ensure export directory exists
        ensure_export_directory()
        
        # Create the exporter and generate the file
        exporter = UserDataExporter(account)
        export_path = exporter.export_to_file(EXPORT_DIRECTORY)
        
        # Get file size
        file_size = os.path.getsize(export_path)
        
        g.log.info("Data export generated: %s (%d bytes)", export_path, file_size)
        
        # Create the download record
        export_file = DataExportFile.create(
            account=account,
            request=privacy_request,
            file_path=export_path,
            file_size=file_size,
        )
        
        # Mark the request as completed
        privacy_request.mark_completed(
            download_url=export_file.download_token,
            file_size=file_size,
        )
        
        # Notify the user
        send_export_ready_notification(account, privacy_request, export_file)
        
        g.log.info("Privacy export request %s completed successfully", request_id)
        
    except Exception as e:
        error_msg = str(e)
        g.log.error("Failed to process privacy export %s: %s\n%s", 
                   request_id, error_msg, traceback.format_exc())
        privacy_request.mark_failed(error_msg)
        
        # Notify user of failure
        try:
            account = Account._byID36(privacy_request.account_id36, data=True)
            send_export_failed_notification(account, privacy_request, error_msg)
        except Exception:
            pass


def send_export_ready_notification(account, privacy_request, export_file):
    """Send a notification to the user that their export is ready."""
    try:
        from r2.lib.db import queries
        
        subject = "Your Tippr data export is ready"
        body = """Your data export request has been processed and is ready for download.

**Download your data:**

Visit your [Privacy Settings](/prefs/privacy) page to download your data export.

**Important notes:**

- This download will expire in 7 days
- You can download the file up to 5 times
- The file is in ZIP format containing JSON data

If you did not request this export, please contact us at privacy@tippr.net.

---
This is an automated message from Tippr.
"""
        
        # Get system user for sending
        system_user = Account.system_user()
        
        item, inbox_rel = Message._new(
            system_user,
            account,
            subject,
            body,
            '',  # IP
            can_send_email=True,
        )
        queries.new_message(item, inbox_rel, update_modmail=False)
        
    except Exception as e:
        g.log.error("Failed to send export ready notification: %s", e)


def send_export_failed_notification(account, privacy_request, error_msg):
    """Send a notification to the user that their export failed."""
    try:
        from r2.lib.db import queries
        
        subject = "Your Tippr data export could not be completed"
        body = """Unfortunately, we were unable to process your data export request.

If you continue to experience issues, please contact us at privacy@tippr.net 
and we will assist you manually.

---
This is an automated message from Tippr.
"""
        
        system_user = Account.system_user()
        
        item, inbox_rel = Message._new(
            system_user,
            account,
            subject,
            body,
            '',  # IP
            can_send_email=True,
        )
        queries.new_message(item, inbox_rel, update_modmail=False)
        
    except Exception as e:
        g.log.error("Failed to send export failed notification: %s", e)


def consume_privacy_exports():
    """
    Main consumer function for the privacy export queue.
    
    This should be run as a background service.
    """
    
    def _process_message(msg):
        request_id = msg.body
        try:
            process_export_request(request_id)
        except Exception as e:
            g.log.error("Error processing privacy export message: %s", e)
    
    g.log.info("Starting privacy export consumer...")
    amqp.consume_items('privacy_export_q', _process_message)


def cleanup_expired_exports():
    """
    Cleanup expired export files.
    
    This should be run periodically (e.g., daily cron job).
    """
    from datetime import timedelta
    
    g.log.info("Cleaning up expired privacy exports...")
    
    if not os.path.exists(EXPORT_DIRECTORY):
        return
    
    now = datetime.now()
    expiry_days = 7
    
    deleted_count = 0
    for filename in os.listdir(EXPORT_DIRECTORY):
        filepath = os.path.join(EXPORT_DIRECTORY, filename)
        
        try:
            # Check file age
            mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            age = now - mtime
            
            if age > timedelta(days=expiry_days):
                os.remove(filepath)
                deleted_count += 1
                g.log.debug("Deleted expired export: %s", filename)
        except Exception as e:
            g.log.warning("Failed to check/delete file %s: %s", filename, e)
    
    g.log.info("Cleanup complete. Deleted %d expired files.", deleted_count)


if __name__ == '__main__':
    # When run directly, start the consumer
    consume_privacy_exports()

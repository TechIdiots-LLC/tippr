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
Privacy Controller

Handles user privacy requests including data export, data deletion,
and the privacy settings page.
"""

import os

from pylons import app_globals as g
from pylons import request
from pylons import tmpl_context as c
from pylons.i18n import _

from r2.controllers.tippr_base import TipprController
from r2.lib import amqp
from r2.lib.base import abort
from r2.lib.errors import errors
from r2.lib.pages import PrefsPage, Templated
from r2.lib.template_helpers import get_domain
from r2.lib.validator import (
    VAdmin,
    VModhash,
    VRatelimit,
    VUser,
    json_validate,
    nop,
    validate,
    validatedForm,
)
from r2.models import Account
from r2.models.privacy import (
    DataExportFile,
    PrivacyRequest,
    PrivacyRequestStatus,
    PrivacyRequestType,
)


class PrivacyController(TipprController):
    """Controller for privacy-related pages and actions."""

    @validate(VUser())
    def GET_privacy_settings(self):
        """Render the privacy settings page."""
        # Get user's privacy requests
        requests = PrivacyRequest.by_account(c.user)
        
        # Separate by type and status
        export_requests = [r for r in requests if r.request_type == PrivacyRequestType.DATA_EXPORT]
        deletion_requests = [r for r in requests if r.request_type == PrivacyRequestType.DATA_DELETION]
        
        # Check for pending/in-progress requests
        has_pending_export = any(
            r.status in (PrivacyRequestStatus.PENDING, PrivacyRequestStatus.PROCESSING)
            for r in export_requests
        )
        
        # Get the most recent completed export
        recent_export = None
        for r in export_requests:
            if r.status == PrivacyRequestStatus.COMPLETED and not r.is_expired:
                recent_export = r
                break
        
        content = PrivacySettings(
            export_requests=export_requests[:10],  # Show last 10
            deletion_requests=deletion_requests[:10],
            has_pending_export=has_pending_export,
            recent_export=recent_export,
        )
        
        return PrefsPage(
            content=content,
        ).render()

    @validatedForm(
        VUser(),
        VModhash(),
        VRatelimit(rate_user=True, rate_ip=True, prefix='privacy_export_'),
    )
    def POST_request_data_export(self, form, jquery):
        """Request a data export."""
        # Check for existing pending request
        existing = PrivacyRequest.by_account(c.user, request_type=PrivacyRequestType.DATA_EXPORT)
        pending = [r for r in existing if r.status in (
            PrivacyRequestStatus.PENDING, PrivacyRequestStatus.PROCESSING
        )]
        
        stuck = [r for r in pending if r.stuck()]
        if stuck:
            # its queue item was probably lost: send it again rather than
            # keep the member waiting on it forever
            for r in stuck:
                amqp.add_item('privacy_export_q', r._id)
            form.set_text('.status', _('Your data export request has been submitted. '
                                       'You will receive a notification when it is ready.'))
            return
        if pending:
            c.errors.add(errors.RATELIMIT, field='ratelimit',
                        msg_params={'time': '24 hours'})
            form.has_errors('ratelimit', errors.RATELIMIT)
            return
        
        # Check rate limit - one export per 24 hours
        recent = [r for r in existing if r.created_datetime and 
                  (c.start_time - r.created_datetime).total_seconds() < 86400]
        if recent:
            c.errors.add(errors.RATELIMIT, field='ratelimit',
                        msg_params={'time': '24 hours'})
            form.has_errors('ratelimit', errors.RATELIMIT)
            return
        
        # Create the request
        privacy_request = PrivacyRequest.create(
            account=c.user,
            request_type=PrivacyRequestType.DATA_EXPORT,
            request_ip=request.ip,
        )
        
        # Add to processing queue
        amqp.add_item('privacy_export_q', privacy_request._id)
        
        form.set_text('.status', _('Your data export request has been submitted. '
                                   'You will receive a notification when it is ready.'))
        jquery.refresh()

    @validatedForm(
        VUser(),
        VModhash(),
        request_id=nop('request_id'),
    )
    def POST_cancel_privacy_request(self, form, jquery, request_id):
        """Cancel a pending privacy request."""
        if not request_id:
            abort(400)
        
        try:
            privacy_request = PrivacyRequest._byID(request_id)
        except Exception:
            abort(404)
        
        # Verify ownership
        if privacy_request.account_id36 != c.user._id36:
            abort(403)
        
        # Can only cancel pending requests
        if privacy_request.status != PrivacyRequestStatus.PENDING:
            form.set_text('.status', _('This request cannot be cancelled.'))
            return
        
        privacy_request.cancel()
        form.set_text('.status', _('Request cancelled.'))
        jquery.refresh()

    @validate(
        VUser(),
        token=nop('token'),
    )
    def GET_download_export(self, token):
        """Download a completed data export."""
        if not token:
            abort(400)
        
        export_file = DataExportFile.by_token(token)
        if not export_file:
            abort(404)
        
        # Verify ownership
        if not export_file.can_download(c.user):
            abort(403)
        
        # The ZIP: in the database (r2.lib.privacy_export_store), or for an
        # export from before, on this server's disk
        from r2.lib import privacy_export_store
        if export_file.file_path == privacy_export_store.STORED:
            data = privacy_export_store.load(export_file.download_token)
        elif os.path.exists(export_file.file_path):
            with open(export_file.file_path, 'rb') as f:
                data = f.read()
        else:
            data = None
        if data is None:
            abort(404)

        # Record download
        export_file.record_download()

        # Serve the file
        from pylons import response
        response.content_type = 'application/zip'
        response.headers['Content-Disposition'] = (
            f'attachment; filename="tippr_data_export_{c.user.name}.zip"'
        )
        return data

    @json_validate(VUser())
    def GET_privacy_requests_json(self, responder):
        """Get user's privacy requests as JSON."""
        requests = PrivacyRequest.by_account(c.user)
        return {
            'requests': [r.to_dict() for r in requests],
        }


class PrivacySettings(Templated):
    """The member's privacy page (privacysettings.html)."""

    def __init__(self, export_requests=None, deletion_requests=None,
                 has_pending_export=False, recent_export=None):
        Templated.__init__(
            self,
            export_requests=export_requests or [],
            deletion_requests=deletion_requests or [],
            has_pending_export=has_pending_export,
            recent_export=recent_export,
        )

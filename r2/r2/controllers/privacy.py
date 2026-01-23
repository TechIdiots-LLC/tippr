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
from r2.lib.pages import BoringPage
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
        
        content = PrivacySettingsPage(
            export_requests=export_requests[:10],  # Show last 10
            deletion_requests=deletion_requests[:10],
            has_pending_export=has_pending_export,
            recent_export=recent_export,
        )
        
        return BoringPage(
            pagename=_("Privacy Settings"),
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
        
        # Check if file exists
        if not os.path.exists(export_file.file_path):
            abort(404)
        
        # Record download
        export_file.record_download()
        
        # Serve the file
        from pylons import response
        response.content_type = 'application/zip'
        response.headers['Content-Disposition'] = (
            f'attachment; filename="tippr_data_export_{c.user.name}.zip"'
        )
        
        with open(export_file.file_path, 'rb') as f:
            return f.read()

    @json_validate(VUser())
    def GET_privacy_requests_json(self, responder):
        """Get user's privacy requests as JSON."""
        requests = PrivacyRequest.by_account(c.user)
        return {
            'requests': [r.to_dict() for r in requests],
        }


class PrivacySettingsPage:
    """Page content for privacy settings."""
    
    def __init__(self, export_requests=None, deletion_requests=None,
                 has_pending_export=False, recent_export=None):
        self.export_requests = export_requests or []
        self.deletion_requests = deletion_requests or []
        self.has_pending_export = has_pending_export
        self.recent_export = recent_export
    
    def render(self):
        from r2.lib.pages import Templated
        # This will use the privacysettings.html template
        return PrivacySettingsContent(
            export_requests=self.export_requests,
            deletion_requests=self.deletion_requests,
            has_pending_export=self.has_pending_export,
            recent_export=self.recent_export,
        ).render()


class PrivacySettingsContent:
    """Templated content for privacy settings page."""
    
    cacheable = False
    
    def __init__(self, **kw):
        self.__dict__.update(kw)
    
    def render(self):
        from r2.lib.filters import unsafe
        from r2.lib.template_helpers import format_html
        
        html = []
        html.append('<div class="privacy-settings">')
        
        # Data Export Section
        html.append('<div class="privacy-section">')
        html.append('<h2>%s</h2>' % _('Download Your Data'))
        html.append('<p>%s</p>' % _(
            'You can request a copy of your personal data. This includes your posts, '
            'comments, messages, preferences, and other account information.'
        ))
        
        if self.has_pending_export:
            html.append('<div class="status-message">')
            html.append('<p>%s</p>' % _('A data export is currently being prepared. '
                                        'You will be notified when it is ready.'))
            html.append('</div>')
        elif self.recent_export:
            html.append('<div class="status-message success">')
            html.append('<p>%s</p>' % _('Your data export is ready for download.'))
            html.append('<a href="/prefs/privacy/download?token=%s" class="btn">%s</a>' % (
                self.recent_export.download_url, _('Download Export')))
            html.append('<p class="note">%s</p>' % _(
                'This download will expire in 7 days. Downloads are limited to 5 times.'))
            html.append('</div>')
        else:
            html.append('<form method="post" action="/api/privacy/request_export" '
                       'class="privacy-form">')
            html.append('<input type="hidden" name="uh" value="%s">' % c.modhash)
            html.append('<button type="submit" class="btn">%s</button>' % _('Request Data Export'))
            html.append('<p class="note">%s</p>' % _(
                'Data exports are processed within 24-48 hours. You can request one export per day.'))
            html.append('</form>')
        
        # Export History
        if self.export_requests:
            html.append('<h3>%s</h3>' % _('Export History'))
            html.append('<table class="privacy-requests-table">')
            html.append('<thead><tr><th>%s</th><th>%s</th><th>%s</th></tr></thead>' % (
                _('Date'), _('Status'), _('Action')))
            html.append('<tbody>')
            for req in self.export_requests[:5]:
                status_class = 'status-' + req.status
                html.append('<tr>')
                html.append('<td>%s</td>' % req.created_date[:10] if req.created_date else '-')
                html.append('<td class="%s">%s</td>' % (status_class, req.status))
                action = ''
                if req.status == PrivacyRequestStatus.COMPLETED and req.download_url and not req.is_expired:
                    action = '<a href="/prefs/privacy/download?token=%s">%s</a>' % (
                        req.download_url, _('Download'))
                elif req.status == PrivacyRequestStatus.PENDING:
                    action = '<a href="#" onclick="cancelRequest(\'%s\')">%s</a>' % (
                        req._id, _('Cancel'))
                html.append('<td>%s</td>' % action)
                html.append('</tr>')
            html.append('</tbody></table>')
        
        html.append('</div>')  # End data export section
        
        # Privacy Rights Section
        html.append('<div class="privacy-section">')
        html.append('<h2>%s</h2>' % _('Your Privacy Rights'))
        html.append('<p>%s</p>' % _(
            'Under privacy laws like GDPR and CCPA, you have the following rights:'
        ))
        html.append('<ul>')
        html.append('<li><strong>%s</strong> - %s</li>' % (
            _('Right to Access'), _('Request a copy of your personal data')))
        html.append('<li><strong>%s</strong> - %s</li>' % (
            _('Right to Deletion'), _('Delete your account and personal data')))
        html.append('<li><strong>%s</strong> - %s</li>' % (
            _('Right to Portability'), _('Download your data in a portable format')))
        html.append('<li><strong>%s</strong> - %s</li>' % (
            _('Right to Rectification'), _('Correct inaccurate personal data')))
        html.append('</ul>')
        html.append('<p>%s <a href="/help/privacypolicy">%s</a>.</p>' % (
            _('For more information, see our'), _('Privacy Policy')))
        html.append('</div>')
        
        # Delete Account Section
        html.append('<div class="privacy-section danger-zone">')
        html.append('<h2>%s</h2>' % _('Delete Your Account'))
        html.append('<p>%s</p>' % _(
            'You can permanently delete your account and all associated data. '
            'This action cannot be undone.'
        ))
        html.append('<a href="/prefs/deactivate" class="btn btn-danger">%s</a>' % _(
            'Delete My Account'))
        html.append('</div>')
        
        # Contact Section
        html.append('<div class="privacy-section">')
        html.append('<h2>%s</h2>' % _('Contact Us'))
        html.append('<p>%s</p>' % _(
            'For privacy-related inquiries or to exercise your rights, contact us at:'))
        html.append('<p><a href="mailto:privacy@tippr.net">privacy@tippr.net</a></p>')
        html.append('</div>')
        
        html.append('</div>')  # End privacy-settings
        
        return unsafe('\n'.join(html))

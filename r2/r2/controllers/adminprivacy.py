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
Admin Privacy Controller

Admin dashboard for managing privacy requests, viewing user data,
and handling GDPR/CCPA compliance.
"""

from datetime import datetime

from pylons import app_globals as g
from pylons import request
from pylons import tmpl_context as c
from pylons.i18n import _

from r2.controllers.tippr_base import TipprController
from r2.lib import amqp
from r2.lib.base import abort
from r2.lib.filters import unsafe
from r2.lib.pages import AdminPage
from r2.lib.validator import (
    VAdmin,
    VExistingUname,
    VModhash,
    json_validate,
    nop,
    validate,
    validatedForm,
)
from r2.models import Account
from r2.models.admin_notes import AdminNotesBySystem
from r2.models.privacy import (
    PrivacyRequest,
    PrivacyRequestStatus,
    PrivacyRequestType,
)


class AdminPrivacyController(TipprController):
    """Admin controller for privacy management."""

    @validate(VAdmin())
    def GET_privacy_dashboard(self):
        """Render the admin privacy dashboard."""
        # Get pending requests
        pending_requests = PrivacyRequest.pending_requests(limit=50)
        
        # Get recent requests (all types)
        # For a full implementation, you'd have additional indexes
        
        content = AdminPrivacyDashboard(
            pending_requests=pending_requests,
        )
        
        return AdminPage(
            title=_("Privacy Dashboard"),
            content=content,
        ).render()

    @validate(
        VAdmin(),
        username=VExistingUname('user'),
    )
    def GET_user_data_view(self, username):
        """View a user's data summary (for admin review of privacy requests)."""
        if not username:
            abort(404)
        
        try:
            user = Account._by_name(username)
        except Exception:
            abort(404)
        
        # Get user's privacy requests
        requests = PrivacyRequest.by_account(user)
        
        # Get admin notes for this user
        notes = list(AdminNotesBySystem.in_display_order('user', username))
        
        content = AdminUserDataView(
            target_user=user,
            privacy_requests=requests,
            admin_notes=notes,
        )
        
        return AdminPage(
            title=_("User Data: %s") % username,
            content=content,
        ).render()

    @validatedForm(
        VAdmin(),
        VModhash(),
        request_id=nop('request_id'),
        action=nop('action'),
        admin_notes=nop('admin_notes'),
    )
    def POST_process_request(self, form, jquery, request_id, action, admin_notes):
        """Process a privacy request (approve, reject, etc.)."""
        if not request_id:
            abort(400)
        
        try:
            privacy_request = PrivacyRequest._byID(request_id)
        except Exception:
            abort(404)
        
        if action == 'approve':
            # Queue for processing
            privacy_request.mark_processing()
            privacy_request.admin_notes = admin_notes or ''
            privacy_request.processed_by = c.user.name
            privacy_request._commit()
            
            # Add to processing queue
            amqp.add_item('privacy_export_q', privacy_request._id)
            
            form.set_text('.status', _('Request approved and queued for processing.'))
            
        elif action == 'reject':
            privacy_request.mark_failed(error_message=admin_notes or 'Request rejected by admin')
            privacy_request.processed_by = c.user.name
            privacy_request._commit()
            
            form.set_text('.status', _('Request rejected.'))
            
        elif action == 'complete':
            privacy_request.mark_completed()
            privacy_request.admin_notes = admin_notes or ''
            privacy_request.processed_by = c.user.name
            privacy_request._commit()
            
            form.set_text('.status', _('Request marked as completed.'))
        else:
            abort(400)
        
        # Log the action
        try:
            user = Account._byID36(privacy_request.account_id36)
            AdminNotesBySystem.add(
                system_name='user',
                subject=user.name,
                note=f"Privacy request ({privacy_request.request_type}) {action}d by {c.user.name}. Notes: {admin_notes or 'None'}",
                author=c.user.name,
                when=datetime.now(g.tz),
            )
        except Exception:
            pass

    @validatedForm(
        VAdmin(),
        VModhash(),
        username=VExistingUname('user'),
    )
    def POST_trigger_export(self, form, jquery, username):
        """Manually trigger a data export for a user (admin action)."""
        if not username:
            abort(400)
        
        try:
            user = Account._by_name(username)
        except Exception:
            abort(404)
        
        # Create an admin-initiated export request
        privacy_request = PrivacyRequest.create(
            account=user,
            request_type=PrivacyRequestType.DATA_EXPORT,
            request_ip='admin:' + request.ip,
        )
        privacy_request.admin_notes = f"Admin-initiated export by {c.user.name}"
        privacy_request._commit()
        
        # Queue for processing
        privacy_request.mark_processing()
        amqp.add_item('privacy_export_q', privacy_request._id)
        
        # Log the action
        AdminNotesBySystem.add(
            system_name='user',
            subject=username,
            note=f"Admin {c.user.name} initiated data export request",
            author=c.user.name,
            when=datetime.now(g.tz),
        )
        
        form.set_text('.status', _('Data export initiated for %s.') % username)

    @json_validate(VAdmin())
    def GET_pending_requests_json(self, responder):
        """Get pending privacy requests as JSON."""
        pending = PrivacyRequest.pending_requests(limit=100)
        
        requests_data = []
        for req in pending:
            try:
                user = Account._byID36(req.account_id36)
                username = user.name
            except Exception:
                username = '[unknown]'
            
            requests_data.append({
                'id': req._id,
                'username': username,
                'request_type': req.request_type,
                'status': req.status,
                'created_date': req.created_date,
                'request_ip': req.request_ip,
            })
        
        return {'requests': requests_data}


class AdminPrivacyDashboard:
    """Admin privacy dashboard content."""
    
    def __init__(self, pending_requests=None):
        self.pending_requests = pending_requests or []
    
    def render(self):
        html = []
        html.append('<div class="admin-privacy-dashboard">')
        
        # Overview Stats
        html.append('<div class="dashboard-section">')
        html.append('<h2>%s</h2>' % _('Privacy Request Overview'))
        html.append('<div class="stats-grid">')
        html.append('<div class="stat-box">')
        html.append('<span class="stat-number">%d</span>' % len(self.pending_requests))
        html.append('<span class="stat-label">%s</span>' % _('Pending Requests'))
        html.append('</div>')
        html.append('</div>')
        html.append('</div>')
        
        # Pending Requests Table
        html.append('<div class="dashboard-section">')
        html.append('<h2>%s</h2>' % _('Pending Privacy Requests'))
        
        if self.pending_requests:
            html.append('<table class="admin-table privacy-requests-table">')
            html.append('<thead><tr>')
            html.append('<th>%s</th>' % _('User'))
            html.append('<th>%s</th>' % _('Type'))
            html.append('<th>%s</th>' % _('Date'))
            html.append('<th>%s</th>' % _('IP'))
            html.append('<th>%s</th>' % _('Actions'))
            html.append('</tr></thead>')
            html.append('<tbody>')
            
            for req in self.pending_requests:
                try:
                    user = Account._byID36(req.account_id36)
                    username = user.name
                except Exception:
                    username = '[unknown]'
                
                html.append('<tr>')
                html.append('<td><a href="/admin/privacy/user/%s">%s</a></td>' % (username, username))
                html.append('<td>%s</td>' % req.request_type)
                html.append('<td>%s</td>' % (req.created_date[:16] if req.created_date else '-'))
                html.append('<td>%s</td>' % req.request_ip)
                html.append('<td class="actions">')
                html.append('<button onclick="approveRequest(\'%s\')" class="btn btn-sm btn-success">%s</button> ' % (
                    req._id, _('Approve')))
                html.append('<button onclick="rejectRequest(\'%s\')" class="btn btn-sm btn-danger">%s</button>' % (
                    req._id, _('Reject')))
                html.append('</td>')
                html.append('</tr>')
            
            html.append('</tbody></table>')
        else:
            html.append('<p class="no-data">%s</p>' % _('No pending privacy requests.'))
        
        html.append('</div>')
        
        # Quick Actions
        html.append('<div class="dashboard-section">')
        html.append('<h2>%s</h2>' % _('Quick Actions'))
        html.append('<form method="post" action="/admin/privacy/trigger_export" class="inline-form">')
        html.append('<input type="hidden" name="uh" value="%s">' % c.modhash)
        html.append('<label>%s</label>' % _('Trigger Data Export:'))
        html.append('<input type="text" name="user" placeholder="%s">' % _('username'))
        html.append('<button type="submit" class="btn">%s</button>' % _('Export'))
        html.append('</form>')
        html.append('</div>')
        
        # Links
        html.append('<div class="dashboard-section">')
        html.append('<h2>%s</h2>' % _('Resources'))
        html.append('<ul>')
        html.append('<li><a href="/help/privacypolicy">%s</a></li>' % _('Privacy Policy'))
        html.append('<li><a href="/help/useragreement">%s</a></li>' % _('User Agreement'))
        html.append('<li><a href="/help/moderatorguidelines">%s</a></li>' % _('Moderator Guidelines'))
        html.append('</ul>')
        html.append('</div>')
        
        html.append('</div>')  # End dashboard
        
        # JavaScript for actions
        html.append('''
<script>
function approveRequest(requestId) {
    if (confirm('Approve this privacy request?')) {
        $.post('/admin/privacy/process', {
            request_id: requestId,
            action: 'approve',
            uh: '%s'
        }, function() {
            location.reload();
        });
    }
}

function rejectRequest(requestId) {
    var reason = prompt('Reason for rejection (optional):');
    $.post('/admin/privacy/process', {
        request_id: requestId,
        action: 'reject',
        admin_notes: reason,
        uh: '%s'
    }, function() {
        location.reload();
    });
}
</script>
''' % (c.modhash, c.modhash))
        
        return unsafe('\n'.join(html))


class AdminUserDataView:
    """Admin view of a user's data."""
    
    def __init__(self, target_user, privacy_requests=None, admin_notes=None):
        self.target_user = target_user
        self.privacy_requests = privacy_requests or []
        self.admin_notes = admin_notes or []
    
    def render(self):
        html = []
        html.append('<div class="admin-user-data-view">')
        
        # User Summary
        html.append('<div class="section user-summary">')
        html.append('<h2>%s</h2>' % _('User Information'))
        html.append('<table class="info-table">')
        html.append('<tr><th>%s</th><td>%s</td></tr>' % (_('Username'), self.target_user.name))
        html.append('<tr><th>%s</th><td>%s</td></tr>' % (_('User ID'), self.target_user._id36))
        html.append('<tr><th>%s</th><td>%s</td></tr>' % (
            _('Email'), getattr(self.target_user, 'email', 'Not set')))
        html.append('<tr><th>%s</th><td>%s</td></tr>' % (
            _('Email Verified'), getattr(self.target_user, 'email_verified', False)))
        html.append('<tr><th>%s</th><td>%s</td></tr>' % (
            _('Created'), self.target_user._date.isoformat() if self.target_user._date else '-'))
        html.append('<tr><th>%s</th><td>%d</td></tr>' % (_('Link Karma'), self.target_user.link_karma))
        html.append('<tr><th>%s</th><td>%d</td></tr>' % (_('Comment Karma'), self.target_user.comment_karma))
        html.append('<tr><th>%s</th><td>%s</td></tr>' % (
            _('Deleted'), self.target_user._deleted))
        html.append('<tr><th>%s</th><td>%s</td></tr>' % (
            _('Banned'), getattr(self.target_user, '_banned', False)))
        html.append('</table>')
        html.append('</div>')
        
        # Privacy Requests
        html.append('<div class="section">')
        html.append('<h2>%s</h2>' % _('Privacy Requests'))
        if self.privacy_requests:
            html.append('<table class="admin-table">')
            html.append('<thead><tr>')
            html.append('<th>%s</th><th>%s</th><th>%s</th><th>%s</th>' % (
                _('Type'), _('Status'), _('Date'), _('Notes')))
            html.append('</tr></thead>')
            html.append('<tbody>')
            for req in self.privacy_requests:
                html.append('<tr>')
                html.append('<td>%s</td>' % req.request_type)
                html.append('<td class="status-%s">%s</td>' % (req.status, req.status))
                html.append('<td>%s</td>' % (req.created_date[:16] if req.created_date else '-'))
                html.append('<td>%s</td>' % (req.admin_notes or '-'))
                html.append('</tr>')
            html.append('</tbody></table>')
        else:
            html.append('<p>%s</p>' % _('No privacy requests from this user.'))
        html.append('</div>')
        
        # Admin Notes
        html.append('<div class="section">')
        html.append('<h2>%s</h2>' % _('Admin Notes'))
        if self.admin_notes:
            for note in self.admin_notes:
                html.append('<div class="admin-note">')
                html.append('<span class="note-author">%s</span>' % note.get('author', 'Unknown'))
                html.append('<span class="note-date">%s</span>' % note.get('when', ''))
                html.append('<p>%s</p>' % note.get('note', ''))
                html.append('</div>')
        else:
            html.append('<p>%s</p>' % _('No admin notes for this user.'))
        html.append('</div>')
        
        # Actions
        html.append('<div class="section actions">')
        html.append('<h2>%s</h2>' % _('Actions'))
        html.append('<form method="post" action="/admin/privacy/trigger_export">')
        html.append('<input type="hidden" name="uh" value="%s">' % c.modhash)
        html.append('<input type="hidden" name="user" value="%s">' % self.target_user.name)
        html.append('<button type="submit" class="btn">%s</button>' % _('Generate Data Export'))
        html.append('</form>')
        html.append('</div>')
        
        html.append('</div>')
        
        return unsafe('\n'.join(html))

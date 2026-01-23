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
Privacy Request Models

This module provides data models for handling GDPR/CCPA privacy requests,
including data export requests, data deletion requests, and tracking
their status.
"""

import json
import uuid
from datetime import datetime, timedelta

from pylons import app_globals as g

from r2.lib.db import tdb_cassandra


class PrivacyRequestType:
    """Types of privacy requests"""
    DATA_EXPORT = "data_export"
    DATA_DELETION = "data_deletion"
    DATA_ACCESS = "data_access"  # View what data we have


class PrivacyRequestStatus:
    """Status of privacy requests"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class PrivacyRequest(tdb_cassandra.Thing):
    """
    Represents a privacy request from a user.
    
    Tracks data export, deletion, and access requests for GDPR/CCPA compliance.
    """
    
    _use_db = True
    _connection_pool = 'main'
    _read_consistency_level = tdb_cassandra.CL.QUORUM
    _write_consistency_level = tdb_cassandra.CL.QUORUM
    
    _defaults = dict(
        account_id36='',
        request_type='',
        status=PrivacyRequestStatus.PENDING,
        created_date='',
        completed_date='',
        expires_date='',
        download_url='',
        error_message='',
        admin_notes='',
        processed_by='',
        request_ip='',
        file_size=0,
    )
    
    _str_props = (
        'account_id36',
        'request_type',
        'status',
        'created_date',
        'completed_date',
        'expires_date',
        'download_url',
        'error_message',
        'admin_notes',
        'processed_by',
        'request_ip',
    )
    
    _int_props = (
        'file_size',
    )
    
    @classmethod
    def create(cls, account, request_type, request_ip=''):
        """Create a new privacy request."""
        request_id = str(uuid.uuid4())
        now = datetime.now(g.tz)
        
        # Data exports expire after 7 days
        if request_type == PrivacyRequestType.DATA_EXPORT:
            expires = now + timedelta(days=7)
        else:
            expires = now + timedelta(days=30)
        
        request = cls(
            _id=request_id,
            account_id36=account._id36,
            request_type=request_type,
            status=PrivacyRequestStatus.PENDING,
            created_date=now.isoformat(),
            expires_date=expires.isoformat(),
            request_ip=request_ip,
        )
        request._commit()
        return request
    
    @classmethod
    def by_account(cls, account, request_type=None, limit=100):
        """Get all privacy requests for an account."""
        # Query by account - we'll need an index for this
        requests = []
        try:
            index = PrivacyRequestsByAccount._cf.get(
                account._id36,
                column_count=limit,
                column_reversed=True,
            )
            for request_id in index.values():
                try:
                    req = cls._byID(request_id)
                    if request_type is None or req.request_type == request_type:
                        requests.append(req)
                except tdb_cassandra.NotFound:
                    pass
        except tdb_cassandra.NotFound:
            pass
        return requests
    
    @classmethod
    def pending_requests(cls, limit=100):
        """Get all pending privacy requests (for admin dashboard)."""
        requests = []
        try:
            index = PrivacyRequestsByStatus._cf.get(
                PrivacyRequestStatus.PENDING,
                column_count=limit,
                column_reversed=True,
            )
            for request_id in index.values():
                try:
                    requests.append(cls._byID(request_id))
                except tdb_cassandra.NotFound:
                    pass
        except tdb_cassandra.NotFound:
            pass
        return requests
    
    def mark_processing(self):
        """Mark the request as being processed."""
        old_status = self.status
        self.status = PrivacyRequestStatus.PROCESSING
        self._commit()
        self._update_status_index(old_status, self.status)
    
    def mark_completed(self, download_url='', file_size=0):
        """Mark the request as completed."""
        old_status = self.status
        self.status = PrivacyRequestStatus.COMPLETED
        self.completed_date = datetime.now(g.tz).isoformat()
        if download_url:
            self.download_url = download_url
        if file_size:
            self.file_size = file_size
        self._commit()
        self._update_status_index(old_status, self.status)
    
    def mark_failed(self, error_message=''):
        """Mark the request as failed."""
        old_status = self.status
        self.status = PrivacyRequestStatus.FAILED
        self.error_message = error_message
        self.completed_date = datetime.now(g.tz).isoformat()
        self._commit()
        self._update_status_index(old_status, self.status)
    
    def cancel(self):
        """Cancel the request."""
        old_status = self.status
        self.status = PrivacyRequestStatus.CANCELLED
        self._commit()
        self._update_status_index(old_status, self.status)
    
    def _update_status_index(self, old_status, new_status):
        """Update the status index when status changes."""
        try:
            # Remove from old status index
            PrivacyRequestsByStatus._cf.remove(old_status, [self._id])
        except Exception:
            pass
        
        # Add to new status index
        PrivacyRequestsByStatus._cf.insert(
            new_status,
            {uuid.uuid1(): self._id},
        )
    
    @property
    def is_expired(self):
        """Check if the request has expired."""
        if not self.expires_date:
            return False
        expires = datetime.fromisoformat(self.expires_date)
        return datetime.now(g.tz) > expires
    
    @property
    def created_datetime(self):
        """Get created date as datetime object."""
        if self.created_date:
            return datetime.fromisoformat(self.created_date)
        return None
    
    @property
    def completed_datetime(self):
        """Get completed date as datetime object."""
        if self.completed_date:
            return datetime.fromisoformat(self.completed_date)
        return None
    
    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            'id': self._id,
            'request_type': self.request_type,
            'status': self.status,
            'created_date': self.created_date,
            'completed_date': self.completed_date,
            'expires_date': self.expires_date,
            'download_url': self.download_url if self.status == PrivacyRequestStatus.COMPLETED else None,
            'file_size': self.file_size,
            'error_message': self.error_message if self.status == PrivacyRequestStatus.FAILED else None,
        }


class PrivacyRequestsByAccount(tdb_cassandra.View):
    """Index of privacy requests by account."""
    
    _use_db = True
    _connection_pool = 'main'
    _compare_with = tdb_cassandra.TIME_UUID_TYPE
    _read_consistency_level = tdb_cassandra.CL.QUORUM
    _write_consistency_level = tdb_cassandra.CL.QUORUM
    
    @classmethod
    def add(cls, account, request):
        """Add a request to the account's index."""
        cls._cf.insert(account._id36, {uuid.uuid1(): request._id})
    
    @classmethod
    def remove(cls, account, request):
        """Remove a request from the account's index."""
        # This is a best-effort removal
        try:
            index = cls._cf.get(account._id36)
            for col_id, req_id in index.items():
                if req_id == request._id:
                    cls._cf.remove(account._id36, [col_id])
                    break
        except tdb_cassandra.NotFound:
            pass


class PrivacyRequestsByStatus(tdb_cassandra.View):
    """Index of privacy requests by status (for admin queue)."""
    
    _use_db = True
    _connection_pool = 'main'
    _compare_with = tdb_cassandra.TIME_UUID_TYPE
    _read_consistency_level = tdb_cassandra.CL.ONE
    _write_consistency_level = tdb_cassandra.CL.QUORUM
    
    @classmethod
    def add(cls, status, request):
        """Add a request to the status index."""
        cls._cf.insert(status, {uuid.uuid1(): request._id})


class DataExportFile(tdb_cassandra.Thing):
    """
    Represents a generated data export file.
    
    Stores metadata about exported files and their download tokens.
    """
    
    _use_db = True
    _connection_pool = 'main'
    _ttl = timedelta(days=7)  # Files expire after 7 days
    
    _defaults = dict(
        account_id36='',
        request_id='',
        file_path='',
        file_size=0,
        download_token='',
        created_date='',
        download_count=0,
        max_downloads=5,
    )
    
    _str_props = (
        'account_id36',
        'request_id',
        'file_path',
        'download_token',
        'created_date',
    )
    
    _int_props = (
        'file_size',
        'download_count',
        'max_downloads',
    )
    
    @classmethod
    def create(cls, account, request, file_path, file_size):
        """Create a new export file record."""
        download_token = str(uuid.uuid4())
        now = datetime.now(g.tz)
        
        export_file = cls(
            _id=download_token,
            account_id36=account._id36,
            request_id=request._id,
            file_path=file_path,
            file_size=file_size,
            download_token=download_token,
            created_date=now.isoformat(),
        )
        export_file._commit()
        return export_file
    
    @classmethod
    def by_token(cls, token):
        """Get export file by download token."""
        try:
            return cls._byID(token)
        except tdb_cassandra.NotFound:
            return None
    
    def can_download(self, account):
        """Check if the account can download this file."""
        if self.account_id36 != account._id36:
            return False
        if self.download_count >= self.max_downloads:
            return False
        return True
    
    def record_download(self):
        """Record a download of the file."""
        self.download_count += 1
        self._commit()

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
User Data Export Collector

This module collects user data for GDPR/CCPA data export requests.
It gathers all user data into a structured JSON format that can be
downloaded by the user.
"""

import json
import os
import tempfile
import zipfile
from datetime import datetime

from pylons import app_globals as g

from r2.lib.utils import tup
from r2.models import (
    Account,
    Comment,
    Link,
    Message,
    Vault,
)


class UserDataExporter:
    """
    Collects and exports all user data for privacy compliance.
    
    This class gathers:
    - Account information
    - Posts (Links)
    - Comments
    - Private messages (sent and received)
    - Saved items
    - Hidden items
    - Upvoted/Downvoted items
    - Vault subscriptions
    - Preferences
    - IP history
    """
    
    def __init__(self, account):
        self.account = account
        self.data = {}
        self.errors = []
    
    def collect_all(self):
        """Collect all user data."""
        self.data = {
            'export_info': self._export_info(),
            'account': self._collect_account_info(),
            'preferences': self._collect_preferences(),
            'posts': self._collect_posts(),
            'comments': self._collect_comments(),
            'messages': self._collect_messages(),
            'saved': self._collect_saved(),
            'hidden': self._collect_hidden(),
            'votes': self._collect_votes(),
            'subscriptions': self._collect_subscriptions(),
            'friends': self._collect_friends(),
            'blocked': self._collect_blocked(),
            'ip_history': self._collect_ip_history(),
            'oauth_apps': self._collect_oauth_apps(),
        }
        
        if self.errors:
            self.data['export_errors'] = self.errors
        
        return self.data
    
    def _export_info(self):
        """Export metadata."""
        return {
            'exported_at': datetime.now(g.tz).isoformat(),
            'account_name': self.account.name,
            'account_id': self.account._id36,
            'format_version': '1.0',
            'tippr_version': getattr(g, 'version', 'unknown'),
        }
    
    def _collect_account_info(self):
        """Collect basic account information."""
        try:
            return {
                'username': self.account.name,
                'id': self.account._id36,
                'email': getattr(self.account, 'email', None),
                'email_verified': getattr(self.account, 'email_verified', False),
                'created_utc': self.account._date.isoformat() if self.account._date else None,
                'link_karma': self.account.link_karma,
                'comment_karma': self.account.comment_karma,
                'is_gold': getattr(self.account, 'gold', False),
                'gold_expiration': getattr(self.account, 'gold_expiration', None),
                'has_verified_email': getattr(self.account, 'email_verified', False),
                'inbox_count': getattr(self.account, 'inbox_count', 0),
            }
        except Exception as e:
            self.errors.append(f"Error collecting account info: {str(e)}")
            return {}
    
    def _collect_preferences(self):
        """Collect user preferences."""
        try:
            prefs = {}
            pref_attrs = [
                'pref_lang', 'pref_content_langs', 'pref_over_18',
                'pref_show_stylesheets', 'pref_show_flair', 'pref_show_link_flair',
                'pref_no_profanity', 'pref_label_nsfw', 'pref_private_feeds',
                'pref_hide_ups', 'pref_hide_downs', 'pref_min_link_score',
                'pref_min_comment_score', 'pref_num_comments', 'pref_numsites',
                'pref_compress', 'pref_domain_details', 'pref_newwindow',
                'pref_media', 'pref_media_preview', 'pref_default_comment_sort',
                'pref_highlight_new_comments', 'pref_show_trending',
                'pref_email_messages', 'pref_email_digests', 'pref_email_unsubscribe_all',
            ]
            for attr in pref_attrs:
                if hasattr(self.account, attr):
                    prefs[attr] = getattr(self.account, attr)
            return prefs
        except Exception as e:
            self.errors.append(f"Error collecting preferences: {str(e)}")
            return {}
    
    def _collect_posts(self, limit=1000):
        """Collect user's posts (links)."""
        try:
            from r2.lib.db.queries import get_submitted
            
            posts = []
            query = get_submitted(self.account, 'new', 'all')
            if query:
                items = list(query)[:limit]
                links = Link._byID([item._id for item in items], data=True, return_dict=False)
                
                for link in links:
                    posts.append({
                        'id': link._id36,
                        'title': link.title,
                        'url': getattr(link, 'url', None),
                        'selftext': getattr(link, 'selftext', None),
                        'vault': link.vault.name if hasattr(link, 'vault') else None,
                        'created_utc': link._date.isoformat() if link._date else None,
                        'score': link._score,
                        'upvotes': link._ups,
                        'downvotes': link._downs,
                        'num_comments': getattr(link, 'num_comments', 0),
                        'is_self': getattr(link, 'is_self', False),
                        'over_18': getattr(link, 'over_18', False),
                        'deleted': link._deleted,
                        'removed': getattr(link, '_spam', False),
                        'permalink': link.make_permalink_slow() if hasattr(link, 'make_permalink_slow') else None,
                    })
            return posts
        except Exception as e:
            self.errors.append(f"Error collecting posts: {str(e)}")
            return []
    
    def _collect_comments(self, limit=1000):
        """Collect user's comments."""
        try:
            from r2.lib.db.queries import get_comments
            
            comments = []
            query = get_comments(self.account, 'new', 'all')
            if query:
                items = list(query)[:limit]
                comment_objs = Comment._byID([item._id for item in items], data=True, return_dict=False)
                
                for comment in comment_objs:
                    comments.append({
                        'id': comment._id36,
                        'body': comment.body,
                        'vault': comment.vault.name if hasattr(comment, 'vault') else None,
                        'link_id': comment.link_id if hasattr(comment, 'link_id') else None,
                        'parent_id': comment.parent_id if hasattr(comment, 'parent_id') else None,
                        'created_utc': comment._date.isoformat() if comment._date else None,
                        'score': comment._score,
                        'upvotes': comment._ups,
                        'downvotes': comment._downs,
                        'deleted': comment._deleted,
                        'removed': getattr(comment, '_spam', False),
                        'permalink': comment.make_permalink_slow() if hasattr(comment, 'make_permalink_slow') else None,
                    })
            return comments
        except Exception as e:
            self.errors.append(f"Error collecting comments: {str(e)}")
            return []
    
    def _collect_messages(self, limit=500):
        """Collect private messages (sent and received)."""
        try:
            from r2.lib.db.queries import get_inbox_messages, get_sent
            
            messages = {
                'inbox': [],
                'sent': [],
            }
            
            # Inbox messages
            try:
                inbox_query = get_inbox_messages(self.account)
                if inbox_query:
                    items = list(inbox_query)[:limit]
                    msg_objs = Message._byID([item._id for item in items], data=True, return_dict=False)
                    
                    for msg in msg_objs:
                        messages['inbox'].append({
                            'id': msg._id36,
                            'subject': getattr(msg, 'subject', None),
                            'body': msg.body,
                            'from_user': msg.author.name if hasattr(msg, 'author') and msg.author else '[deleted]',
                            'created_utc': msg._date.isoformat() if msg._date else None,
                            'read': not getattr(msg, 'new', True),
                        })
            except Exception as e:
                self.errors.append(f"Error collecting inbox: {str(e)}")
            
            # Sent messages
            try:
                sent_query = get_sent(self.account)
                if sent_query:
                    items = list(sent_query)[:limit]
                    msg_objs = Message._byID([item._id for item in items], data=True, return_dict=False)
                    
                    for msg in msg_objs:
                        messages['sent'].append({
                            'id': msg._id36,
                            'subject': getattr(msg, 'subject', None),
                            'body': msg.body,
                            'to_user': msg.to.name if hasattr(msg, 'to') and msg.to else '[deleted]',
                            'created_utc': msg._date.isoformat() if msg._date else None,
                        })
            except Exception as e:
                self.errors.append(f"Error collecting sent messages: {str(e)}")
            
            return messages
        except Exception as e:
            self.errors.append(f"Error collecting messages: {str(e)}")
            return {'inbox': [], 'sent': []}
    
    def _collect_saved(self, limit=500):
        """Collect saved items."""
        try:
            from r2.models.link import SavedLinksByAccount, SavedCommentsByAccount
            
            saved = {'links': [], 'comments': []}
            
            try:
                saved_links = SavedLinksByAccount.by_account(self.account, limit=limit)
                for link in saved_links:
                    saved['links'].append({
                        'id': link._id36,
                        'title': link.title,
                        'vault': link.vault.name if hasattr(link, 'vault') else None,
                        'saved_at': None,  # Timestamp not stored
                    })
            except Exception as e:
                self.errors.append(f"Error collecting saved links: {str(e)}")
            
            try:
                saved_comments = SavedCommentsByAccount.by_account(self.account, limit=limit)
                for comment in saved_comments:
                    saved['comments'].append({
                        'id': comment._id36,
                        'body_preview': comment.body[:200] if comment.body else None,
                        'vault': comment.vault.name if hasattr(comment, 'vault') else None,
                        'saved_at': None,
                    })
            except Exception as e:
                self.errors.append(f"Error collecting saved comments: {str(e)}")
            
            return saved
        except Exception as e:
            self.errors.append(f"Error collecting saved items: {str(e)}")
            return {'links': [], 'comments': []}
    
    def _collect_hidden(self, limit=500):
        """Collect hidden items."""
        try:
            from r2.models.link import HiddenLinksByAccount
            
            hidden = []
            try:
                hidden_links = HiddenLinksByAccount.by_account(self.account, limit=limit)
                for link in hidden_links:
                    hidden.append({
                        'id': link._id36,
                        'title': link.title,
                        'vault': link.vault.name if hasattr(link, 'vault') else None,
                    })
            except Exception:
                pass
            
            return hidden
        except Exception as e:
            self.errors.append(f"Error collecting hidden items: {str(e)}")
            return []
    
    def _collect_votes(self, limit=1000):
        """Collect voting history."""
        try:
            from r2.models.vote import VotesByAccount
            
            votes = {'upvoted': [], 'downvoted': []}
            
            try:
                # Get liked items
                liked = VotesByAccount.get_liked(self.account, limit=limit)
                for item in liked:
                    votes['upvoted'].append({
                        'id': item._id36,
                        'type': 'link' if isinstance(item, Link) else 'comment',
                        'title': getattr(item, 'title', None) or getattr(item, 'body', '')[:100],
                    })
            except Exception:
                pass
            
            try:
                # Get disliked items
                disliked = VotesByAccount.get_disliked(self.account, limit=limit)
                for item in disliked:
                    votes['downvoted'].append({
                        'id': item._id36,
                        'type': 'link' if isinstance(item, Link) else 'comment',
                        'title': getattr(item, 'title', None) or getattr(item, 'body', '')[:100],
                    })
            except Exception:
                pass
            
            return votes
        except Exception as e:
            self.errors.append(f"Error collecting votes: {str(e)}")
            return {'upvoted': [], 'downvoted': []}
    
    def _collect_subscriptions(self):
        """Collect vault subscriptions."""
        try:
            subscriptions = []
            if hasattr(self.account, 'has_vault_subscriptions') and self.account.has_vault_subscriptions:
                vault_ids = Vault.reverse_subscriber_ids(self.account)
                vaults = Vault._byID(vault_ids, data=True, return_dict=False)
                for vault in vaults:
                    subscriptions.append({
                        'name': vault.name,
                        'id': vault._id36,
                        'title': vault.title,
                        'subscribers': getattr(vault, '_ups', 0),
                    })
            return subscriptions
        except Exception as e:
            self.errors.append(f"Error collecting subscriptions: {str(e)}")
            return []
    
    def _collect_friends(self):
        """Collect friends list."""
        try:
            friends = []
            friend_ids = self.account.friend_ids()
            if friend_ids:
                friend_accounts = Account._byID(list(friend_ids), data=True, return_dict=False)
                for friend in friend_accounts:
                    friends.append({
                        'username': friend.name,
                        'id': friend._id36,
                    })
            return friends
        except Exception as e:
            self.errors.append(f"Error collecting friends: {str(e)}")
            return []
    
    def _collect_blocked(self):
        """Collect blocked users."""
        try:
            blocked = []
            enemy_ids = self.account.enemy_ids()
            if enemy_ids:
                blocked_accounts = Account._byID(list(enemy_ids), data=True, return_dict=False)
                for account in blocked_accounts:
                    blocked.append({
                        'username': account.name,
                        'id': account._id36,
                    })
            return blocked
        except Exception as e:
            self.errors.append(f"Error collecting blocked users: {str(e)}")
            return []
    
    def _collect_ip_history(self, limit=100):
        """Collect IP address history."""
        try:
            from r2.lib.ip_events import ips_by_account_id
            
            ip_history = []
            ips = ips_by_account_id(self.account._id, limit=limit)
            for ip_info in ips:
                ip, visit_time, location, org, count = ip_info
                ip_history.append({
                    'ip_address': ip,
                    'last_visit': visit_time.isoformat() if visit_time else None,
                    'location': location,
                    'organization': org,
                    'access_count': count,
                })
            return ip_history
        except Exception as e:
            self.errors.append(f"Error collecting IP history: {str(e)}")
            return []
    
    def _collect_oauth_apps(self):
        """Collect authorized OAuth applications."""
        try:
            from r2.models.token import OAuth2Client
            
            apps = []
            try:
                authorized_apps = OAuth2Client._by_user_grouped(self.account)
                for app in authorized_apps.get('authorized', []):
                    apps.append({
                        'name': app.name,
                        'description': app.description,
                        'developer': app.developer.name if hasattr(app, 'developer') else None,
                    })
            except Exception:
                pass
            
            return apps
        except Exception as e:
            self.errors.append(f"Error collecting OAuth apps: {str(e)}")
            return []
    
    def export_to_json(self):
        """Export data to JSON string."""
        self.collect_all()
        return json.dumps(self.data, indent=2, default=str, ensure_ascii=False)
    
    def export_to_file(self, directory=None):
        """
        Export data to a ZIP file containing JSON.
        
        Returns the path to the created ZIP file.
        """
        if directory is None:
            directory = tempfile.gettempdir()
        
        self.collect_all()
        
        # Create filename
        timestamp = datetime.now(g.tz).strftime('%Y%m%d_%H%M%S')
        base_name = f"tippr_data_export_{self.account.name}_{timestamp}"
        json_filename = f"{base_name}.json"
        zip_filename = f"{base_name}.zip"
        zip_path = os.path.join(directory, zip_filename)
        
        # Write JSON to ZIP
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            json_data = json.dumps(self.data, indent=2, default=str, ensure_ascii=False)
            zf.writestr(json_filename, json_data)
            
            # Add a readme
            readme = self._generate_readme()
            zf.writestr("README.txt", readme)
        
        return zip_path
    
    def _generate_readme(self):
        """Generate a readme file for the export."""
        return """Tippr Data Export
==================

This archive contains your personal data exported from Tippr.

File Contents:
- tippr_data_export_*.json - Your data in JSON format

Data Included:
- Account information (username, karma, creation date)
- Preferences and settings
- Posts you've submitted
- Comments you've made
- Private messages (sent and received)
- Saved items
- Hidden items
- Voting history
- Vault subscriptions
- Friends list
- Blocked users
- IP address history
- Authorized applications

Notes:
- Some data may be truncated if you have a large history
- Deleted content is marked as such but included for completeness
- This export was generated on: """ + datetime.now(g.tz).isoformat() + """

For questions about your data, contact: privacy@tippr.net

---
Generated by Tippr Data Export Tool
"""

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
"""Live comments: new comments appear on an open thread as they're posted.

Admins turn the feature on for the site (live_comments on /admin/config);
then each vault's moderators choose whether their vault uses it (the vault
settings page). Once a new comment is in its thread's comment tree, the
commentstree consumer calls announce(), which tells the websockets service
(sutro) about it on the thread's namespace; the thread page listens there
(public/static/js/live-comments.js) and fetches the comment itself.
"""

from pylons import app_globals as g

NAMESPACE = "/websocket/comments/%s"
# how long a page's websocket address stays valid; a page left open
# longer stops getting new comments until it's reloaded
URL_SECONDS = 6 * 60 * 60


def site_enabled():
    return bool(g.live_config.get("live_comments"))


def enabled_for(vault):
    """Whether threads in vault get live comments."""
    return site_enabled() and bool(getattr(vault, "live_comments", False))


def viewer_wants(user, logged_in):
    """Whether this viewer has live comments on (their preference; for
    logged-out visitors, what new accounts start with)."""
    if logged_in:
        return bool(getattr(user, "pref_live_comments", True))
    return bool(g.live_config.get("live_comments_new_user_default", True))


def namespace(link):
    return NAMESPACE % link._id36


def page_config(link, vault, sort, user=None, logged_in=False):
    """The r.config.live_comments a thread page gets, or None."""
    if (not enabled_for(vault) or not viewer_wants(user, logged_in) or
            link.is_archived(vault) or link.locked):
        return None
    from r2.lib import websockets
    return {
        "url": websockets.make_url(namespace(link), max_age=URL_SECONDS),
        "link": link._fullname,
        "sort": sort,
    }


def announce(comments):
    """Tell open thread pages about new comments (once they're in the
    comment tree, so /api/morechildren can find them)."""
    if not site_enabled():
        return
    from r2.lib import websockets
    from r2.lib.utils import to36
    from r2.models import Comment, Link, Vault

    comments = [cm for cm in comments if not cm._spam and not cm._deleted]
    if not comments:
        return
    links = Link._byID({cm.link_id for cm in comments}, data=True,
                       return_dict=True)
    vaults = Vault._byID({link.vault_id for link in links.values()},
                         data=True, return_dict=True)
    for cm in comments:
        link = links.get(cm.link_id)
        if not link or not enabled_for(vaults.get(link.vault_id)):
            continue
        parent = (Comment._fullname_from_id36(to36(cm.parent_id))
                  if cm.parent_id else link._fullname)
        websockets.send_broadcast(namespace(link), "new_comment", {
            "id": cm._id36,
            "name": cm._fullname,
            "parent": parent,
        })

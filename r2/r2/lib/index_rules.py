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
"""Which posts search engines are asked to index.

A post a feed bot made (r2.lib.feeds) is a title and a link to a page that
is already on the web. To a search engine, a site of thousands of those is
"low value content", and Google AdSense, which judges a site the same way,
turns it down for it. So until a person has commented on a feed bot's post,
its page says noindex (r2.lib.pages.LinkInfoPage) and the sitemaps leave it
out (r2.lib.sitemaps.live). Once someone comments it's a discussion, and it
is indexed like any other post. People's own posts are never held back.
"""

# comments a feed bot's post needs before it's indexed
MIN_COMMENTS = 1


def is_feed_bot(account):
    """Whether the account posts feeds (r2.lib.feeds.bot_account marks it).
    Kept after its feeds are removed, so their old posts still count."""
    return bool(account) and bool(getattr(account, "feed_bot", False))


def waits_for_people(link, author):
    """Whether this post is kept out of search engines for now: a feed
    bot's post that nobody has commented on yet."""
    if not is_feed_bot(author):
        return False
    return (getattr(link, "num_comments", 0) or 0) < MIN_COMMENTS

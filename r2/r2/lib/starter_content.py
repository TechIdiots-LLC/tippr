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
"""What the starter content (scripts/create_default_vaults.py and
scripts/starter_feeds.txt) has already offered this site.

Each install or upgrade adds the starter front page defaults and feeds that
are new since the last run, and nothing it offered before: a default vault
or a feed the admin took away stays away. Kept in ZooKeeper with the other
site settings (group "starter_content"):

    defaults_offered  names of starter vaults made front page defaults
    feeds_offered     "vault address" of starter feeds added (lowercase)
    feeds_on          whether to add the starter feeds (the installer's
                      TIPPR_STARTER_FEEDS, remembered); missing: not chosen
    new_site          the starter defaults were this site's first defaults
"""

from r2.lib import site_settings

GROUP = "starter_content"


def _data():
    return dict(site_settings.get_settings(GROUP) or {})


def _save(**changes):
    data = _data()
    data.update(changes)
    site_settings.save_settings(GROUP, data)


def offered_defaults():
    """Names of starter vaults made defaults before (None: never recorded,
    a site from before this was kept)."""
    names = _data().get("defaults_offered")
    return None if names is None else {n.lower() for n in names}


def record_defaults(names, new_site=None):
    offered = offered_defaults() or set()
    changes = {"defaults_offered": sorted(offered | {n.lower() for n in names})}
    if new_site is not None:
        changes["new_site"] = new_site
    _save(**changes)


def feed_key(vault_name, url):
    return "%s %s" % (vault_name.lower(), url.rstrip("/").lower())


def offered_feeds():
    keys = _data().get("feeds_offered")
    return None if keys is None else set(keys)


def record_feeds(keys):
    _save(feeds_offered=sorted((offered_feeds() or set()) | set(keys)))


def feeds_on():
    return _data().get("feeds_on")


def set_feeds_on(on):
    _save(feeds_on=bool(on))


def new_site():
    return bool(_data().get("new_site"))

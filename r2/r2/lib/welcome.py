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
"""What an empty listing shows instead of "there doesn't seem to be
anything here" (templates/listing.html): on the front page and /v/all, a
welcome with ways to start posting and the most subscribed vaults; in an
empty vault, an invitation to post there."""

from pylons import app_globals as g
from pylons import tmpl_context as c

POPULAR_COUNT = 12
CACHE_SECONDS = 600


# the listings the welcome is for: a vault's (or the front page's) posts
# by hot or new. Empty elsewhere (rising, gilded, the inbox, saved posts, a
# profile, top of the past hour …) doesn't mean the site or vault is empty.
WELCOME_CONTROLLERS = ("hot", "new")


def kind():
    """"site" (front page, /v/all), "vault" or None (other listings keep
    the plain message)."""
    from pylons import request
    from r2.models import AllSR, DefaultVault, Vault
    routes = request.environ.get("pylons.routes_dict") or {}
    if (routes.get("controller") not in WELCOME_CONTROLLERS or
            routes.get("action_name", routes.get("action")) != "listing"):
        return None
    if isinstance(c.site, (DefaultVault, AllSR)):
        return "site"
    if isinstance(c.site, Vault):
        return "vault"
    return None


def popular_vaults():
    """The most subscribed public vaults (names and titles), for exploring."""
    cached = g.gencache.get("welcome_popular_vaults")
    if cached is None:
        from r2.lib.db.operators import desc
        from r2.models import Vault
        query = Vault._query(Vault.c.type == "public",
                             Vault.c._spam == False,  # noqa: E712
                             sort=desc("_ups"), limit=POPULAR_COUNT * 3,
                             data=True)
        cached = []
        for vault in query:
            if vault.over_18 or getattr(vault, "quarantine", False):
                continue
            cached.append((vault.name, vault.title or vault.name))
            if len(cached) >= POPULAR_COUNT:
                break
        g.gencache.set("welcome_popular_vaults", cached, time=CACHE_SECONDS)
    return cached


def can_submit_here():
    if not c.user_is_loggedin:
        return True     # the submit page asks them to log in
    try:
        return bool(c.site.can_submit(c.user))
    except Exception:
        return True

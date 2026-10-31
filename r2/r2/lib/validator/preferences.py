# The contents of this file are subject to the Common Public Attribution
# License Version 1.0. (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://code.reddit.com/LICENSE. The License is based on the Mozilla Public
# License Version 1.1, but Sections 14 and 15 have been added to cover use of
# software over a computer network and provide for limited attribution for the
# Original Developer. In addition, Exhibit A has been modified to be consistent
# with Exhibit B.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is reddit.
#
# The Original Developer is the Initial Developer.  The Initial Developer of
# the Original Code is reddit Inc.
#
# All portions of the code written by reddit are Copyright (c) 2006-2015 reddit
# Inc. All Rights Reserved.
# 
# Portions created by TechIdiots LLC (Tippr) are Copyright (c) 2026
# TechIdiots LLC. All Rights Reserved.
###############################################################################

from pylons import app_globals as g
from pylons import tmpl_context as c

from r2.config import feature
from r2.lib import ai_content
from r2.lib.errors import errors
from r2.lib.menus import CommentSortMenu
from r2.lib import listing_filters
from r2.lib.validator.validator import (
    VBoolean,
    Validator,
    VInt,
    VLang,
    VOneOf,
    VVaultByName,
)
from r2.models import NotFound, Vault


class VFilterList(Validator):
    """A listing filter typed on /prefs: entries one per line or separated
    by commas, kept as a tidied tuple (r2.lib.listing_filters)."""

    def __init__(self, param, kind, **kw):
        self.kind = kind
        Validator.__init__(self, param, **kw)

    def run(self, val):
        return tuple(listing_filters.clean_list(val, self.kind))

    def param_docs(self):
        return {self.param: "a list of up to %d %s" % (
            listing_filters.MAX_ENTRIES, self.kind)}


# Validators that map directly to Account._preference_attrs
# The key MUST be the same string as the value in _preference_attrs
# Non-preference validators should be added to to the controller
# method directly (see PostController.POST_options)
PREFS_VALIDATORS = dict(
    pref_clickgadget=VBoolean('clickgadget'),
    pref_organic=VBoolean('organic'),
    pref_newwindow=VBoolean('newwindow'),
    pref_public_votes=VBoolean('public_votes'),
    pref_analytics_consent=VOneOf('analytics_consent', ('granted', 'denied')),
    pref_hide_from_robots=VBoolean('hide_from_robots'),
    pref_hide_ups=VBoolean('hide_ups'),
    pref_hide_downs=VBoolean('hide_downs'),
    pref_over_18=VBoolean('over_18'),
    pref_research=VBoolean('research'),
    pref_numsites=VInt('numsites', 1, 100),
    pref_lang=VLang('lang'),
    pref_media=VOneOf('media', ('on', 'off', 'vault')),
    # pref_media_preview=VOneOf('media_preview', ('on', 'off', 'vault')),
    pref_compress=VBoolean('compress'),
    pref_domain_details=VBoolean('domain_details'),
    pref_min_link_score=VInt('min_link_score', -100, 100),
    pref_min_comment_score=VInt('min_comment_score', -100, 100),
    pref_num_comments=VInt('num_comments', 1, g.max_comments,
                           default=g.num_comments),
    pref_highlight_controversial=VBoolean('highlight_controversial'),
    pref_default_comment_sort=VOneOf('default_comment_sort',
                                     CommentSortMenu.visible_options()),
    pref_ignore_suggested_sort=VBoolean("ignore_suggested_sort"),
    pref_show_stylesheets=VBoolean('show_stylesheets'),
    pref_show_flair=VBoolean('show_flair'),
    pref_show_link_flair=VBoolean('show_link_flair'),
    pref_no_profanity=VBoolean('no_profanity'),
    pref_label_nsfw=VBoolean('label_nsfw'),
    pref_nsfw_in_listings=VBoolean('nsfw_in_listings'),
    pref_ai_content=VOneOf('ai_content', ai_content.PREFS,
                           default=ai_content.PREF_SHOW),
    pref_hide_feed_bots=VBoolean("hide_feed_bots"),
    pref_show_promote=VBoolean('show_promote'),
    pref_mark_messages_read=VBoolean("mark_messages_read"),
    pref_threaded_messages=VBoolean("threaded_messages"),
    pref_collapse_read_messages=VBoolean("collapse_read_messages"),
    pref_email_messages=VBoolean("email_messages"),
    pref_private_feeds=VBoolean("private_feeds"),
    pref_store_visits=VBoolean('store_visits'),
    pref_hide_ads=VBoolean("hide_ads"),
    pref_show_trending=VBoolean("show_trending"),
    pref_show_multis=VBoolean("show_multis"),
    pref_infinite_scroll=VBoolean("infinite_scroll"),
    pref_keyboard_nav=VBoolean("keyboard_nav"),
    pref_nightmode=VBoolean("nightmode"),
    pref_hide_child_comments=VBoolean("hide_child_comments"),
    pref_show_images=VBoolean("show_images"),
    pref_auto_expand_images=VBoolean("auto_expand_images"),
    pref_user_tagger=VBoolean("user_tagger"),
    pref_user_info_hover=VBoolean("user_info_hover"),
    pref_parent_hover=VBoolean("parent_hover"),
    pref_new_comment_count=VBoolean("new_comment_count"),
    pref_visited_posts=VOneOf("visited_posts", ("show", "fade", "hide"),
                              default="show"),
    pref_comment_navigator=VBoolean("comment_navigator"),
    pref_account_switcher=VBoolean("account_switcher"),
    pref_filter_keywords=VFilterList("filter_keywords", "keywords"),
    pref_filter_domains=VFilterList("filter_domains", "domains"),
    pref_filter_vaults=VFilterList("filter_vaults", "vaults"),
    pref_filter_users=VFilterList("filter_users", "users"),
    pref_highlight_new_comments=VBoolean("highlight_new_comments"),
    pref_live_comments=VBoolean("live_comments"),
    pref_show_gold_expiration=VBoolean("show_gold_expiration"),
    pref_monitor_mentions=VBoolean("monitor_mentions"),
    pref_hide_locationbar=VBoolean("hide_locationbar"),
    pref_use_global_defaults=VBoolean("use_global_defaults"),
    pref_coin_autorenew=VBoolean("coin_autorenew"),
    pref_enable_default_themes=VBoolean("enable_default_themes", False),
    pref_default_theme_vault=VVaultByName("theme_selector", required=False,
        return_vaultname=True),
    pref_other_theme=VVaultByName("other_theme", required=False,
        return_vaultname=True),
    pref_beta=VBoolean('beta'),
    pref_legacy_search=VBoolean('legacy_search'),
    pref_threaded_modmail=VBoolean('threaded_modmail', False),
)


def set_prefs(user, prefs):
    for k, v in prefs.items():
        if k == 'pref_beta' and v and not getattr(user, 'pref_beta', False):
            # If a user newly opted into beta, we want to subscribe them
            # to the beta vault.
            try:
                vault = Vault._by_name(g.beta_vault)
                if not vault.is_subscriber(user):
                    vault.add_subscriber(user)
            except NotFound:
                g.log.warning("Could not find beta vault '%s'. It may "
                              "need to be created." % g.beta_vault)

        setattr(user, k, v)

def filter_prefs(prefs, user):
    # replace stylesheet_override with other_theme if it doesn't exist
    if feature.is_enabled('stylesheets_everywhere', user=user):
        if not prefs.get("pref_default_theme_vault"):
            if prefs.get("pref_other_theme", False):
                prefs["pref_default_theme_vault"] = prefs["pref_other_theme"]

    for pref_key in list(prefs.keys()):
        if pref_key not in user._preference_attrs:
            del prefs[pref_key]

    #temporary. eventually we'll change pref_clickgadget to an
    #integer preference
    prefs['pref_clickgadget'] = 5 if prefs['pref_clickgadget'] else 0
    if user.pref_show_promote is None:
        prefs['pref_show_promote'] = None
    elif not prefs.get('pref_show_promote'):
        prefs['pref_show_promote'] = False

    if not prefs.get("pref_over_18") or not user.pref_over_18:
        prefs['pref_no_profanity'] = True
        prefs['pref_nsfw_in_listings'] = False

    if prefs.get("pref_no_profanity") or user.pref_no_profanity:
        prefs['pref_label_nsfw'] = True

    # don't update the hide_ads pref if they don't have gold
    if not user.gold:
        del prefs['pref_hide_ads']
        del prefs['pref_show_gold_expiration']

    if not (user.gold or user.is_moderator_somewhere):
        prefs['pref_highlight_new_comments'] = True

    # the account switcher's checkbox is greyed out (so not sent) for those
    # who can't use it: keep what they had, for when they can
    from r2.lib import account_switcher
    if not account_switcher.allowed():
        prefs.pop('pref_account_switcher', None)

    # the domain and vault filters are gold's: without it, keep what's saved
    if not listing_filters.gold_allowed(user):
        for pref in listing_filters.GOLD_FILTERS:
            prefs.pop(pref, None)

    # the checkbox is only there while the site has live comments on:
    # otherwise leave the member's choice as it is
    if not g.live_config.get("live_comments"):
        prefs.pop('pref_live_comments', None)

    # the analytics choice is only on the form when the site uses Google
    # Analytics: without an answer, keep the one saved
    if not prefs.get('pref_analytics_consent'):
        prefs.pop('pref_analytics_consent', None)

    # check stylesheet override
    if (feature.is_enabled('stylesheets_everywhere', user=user) and
            prefs.get('pref_default_theme_vault')):
        override_vault = Vault._by_name(prefs['pref_default_theme_vault'])
        if not override_vault:
            del prefs['pref_default_theme_vault']
            if prefs.get('pref_enable_default_themes'):
                c.errors.add(errors.VAULT_REQUIRED, field="stylesheet_override")
        else:
            if override_vault.can_view(user):
                prefs['pref_default_theme_vault'] = override_vault.name
            else:
                # don't update if they can't view the chosen vault
                c.errors.add(errors.VAULT_NO_ACCESS, field='stylesheet_override')
                del prefs['pref_default_theme_vault']

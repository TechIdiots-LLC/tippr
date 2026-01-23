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

from pylons import request
from pylons.i18n import N_

from r2.lib.db import queries
from r2.lib.utils import blockquote_text
from r2.models import Account, Message

user_added_messages = {
    "moderator": {
        "pm": {
            "subject": N_("Welcome! You are now a moderator"),
            "msg": N_("**Congratulations!** You have been added as a moderator to [%(title)s](%(url)s).\n\n"
                      "---\n\n"
                      "## Welcome to the Tippr Moderator Community!\n\n"
                      "As a moderator, you play a vital role in building and maintaining our community. "
                      "Here are some important things to know:\n\n"
                      "### Your Responsibilities\n\n"
                      "- Enforce vault rules and site-wide policies\n"
                      "- Foster a welcoming environment for community members\n"
                      "- Review reports and take appropriate action\n"
                      "- Collaborate with fellow moderators\n\n"
                      "### Important Resources\n\n"
                      "- [Moderator Guidelines](/help/moderatorguidelines) - Learn about best practices and expectations\n"
                      "- [Content Policy](/help/contentpolicy) - Understand site-wide rules\n"
                      "- [User Agreement](/help/useragreement) - Know the terms of service\n"
                      "- [/v/ModSupport](/v/ModSupport) - Connect with other moderators\n\n"
                      "### Volunteer Status\n\n"
                      "Please note that moderators are independent volunteers, not employees of Tippr. "
                      "For more details, please review the [Moderator Guidelines](/help/moderatorguidelines).\n\n"
                      "---\n\n"
                      "Thank you for helping make Tippr a great place!"),
        },
    },
    "moderator_invite": {
        "pm": {
            "subject": N_("invitation to moderate %(url)s"),
            "msg": N_("**gadzooks! you are invited to become a moderator of [%(title)s](%(url)s)!**\n\n"
                      "*to accept*, visit the [moderators page for %(url)s](%(url)s/about/moderators) and click \"accept\".\n\n"
                      "*otherwise,* if you did not expect to receive this, you can simply ignore this invitation or report it.\n\n"
                      "---\n\n"
                      "*Before accepting, we encourage you to review our [Moderator Guidelines](/help/moderatorguidelines) "
                      "to understand the expectations and responsibilities of being a moderator.*"),
        },
        "modmail": {
            "subject": N_("moderator invited"),
            "msg": N_("%(user)s has been invited by %(author)s to moderate %(url)s."),
        },
    },
    "accept_moderator_invite": {
        "pm": {
            "subject": N_("Welcome! You are now a moderator"),
            "msg": N_("**Congratulations!** You have accepted the invitation to moderate [%(title)s](%(url)s).\n\n"
                      "---\n\n"
                      "## Welcome to the Tippr Moderator Community!\n\n"
                      "As a moderator, you play a vital role in building and maintaining our community. "
                      "Here are some important things to know:\n\n"
                      "### Your Responsibilities\n\n"
                      "- Enforce vault rules and site-wide policies\n"
                      "- Foster a welcoming environment for community members\n"
                      "- Review reports and take appropriate action\n"
                      "- Collaborate with fellow moderators\n\n"
                      "### Important Resources\n\n"
                      "- [Moderator Guidelines](/help/moderatorguidelines) - Learn about best practices and expectations\n"
                      "- [Content Policy](/help/contentpolicy) - Understand site-wide rules\n"
                      "- [User Agreement](/help/useragreement) - Know the terms of service\n"
                      "- [/v/ModSupport](/v/ModSupport) - Connect with other moderators\n\n"
                      "### Volunteer Status\n\n"
                      "Please note that moderators are independent volunteers, not employees of Tippr. "
                      "For more details, please review the [Moderator Guidelines](/help/moderatorguidelines).\n\n"
                      "---\n\n"
                      "Thank you for helping make Tippr a great place!"),
        },
        "modmail": {
            "subject": N_("moderator added"),
            "msg": N_("%(user)s has accepted an invitation to become moderator of %(url)s."),
        },
    },
    "contributor": {
        "pm": {
            "subject": N_("you are an approved submitter"),
            "msg": N_("you have been added as an approved submitter to [%(title)s](%(url)s)."),
        },
    },
    "traffic": {
        "pm": {
            "subject": N_("you can view traffic on a promoted link"),
            "msg": N_('you have been added to the list of users able to see [traffic for the sponsored link "%(title)s"](%(traffic_url)s).'),
        },
    },
}


def notify_user_added(rel_type, author, user, target):
    msgs = user_added_messages.get(rel_type)
    if not msgs:
        return

    vaultname = target.path.rstrip("/")
    d = {
        "url": vaultname,
        "title": "{}: {}".format(vaultname, target.title),
        "author": "/u/" + author.name,
        "user": "/u/" + user.name,
    }

    # Send PM to user
    # For most rel_types, only send if author != user
    # For accept_moderator_invite, always send (it's a welcome message)
    should_send_pm = "pm" in msgs and (
        author != user or rel_type == "accept_moderator_invite"
    )
    
    if should_send_pm:
        subject = msgs["pm"]["subject"] % d
        msg = msgs["pm"]["msg"] % d

        if rel_type in ("moderator_invite", "contributor"):
            # send the message from the vault
            item, inbox_rel = Message._new(
                author, user, subject, msg, request.ip, vault=target, from_vault=True,
                can_send_email=False)
        elif rel_type == "accept_moderator_invite":
            # send welcome message from the vault
            system_user = Account.system_user()
            item, inbox_rel = Message._new(
                system_user, user, subject, msg, request.ip, vault=target, from_vault=True,
                can_send_email=False)
        else:
            item, inbox_rel = Message._new(
                author, user, subject, msg, request.ip, can_send_email=False)

        queries.new_message(item, inbox_rel, update_modmail=False)

    if "modmail" in msgs:
        subject = msgs["modmail"]["subject"] % d
        msg = msgs["modmail"]["msg"] % d

        if rel_type == "moderator_invite":
            modmail_author = Account.system_user()
        else:
            modmail_author = author

        item, inbox_rel = Message._new(modmail_author, target, subject, msg,
                                       request.ip, vault=target)
        queries.new_message(item, inbox_rel)


def send_mod_removal_message(vault, mod, user):
    vault_name = "/v/" + vault.name
    u_name = "/u/" + user.name
    subject = "%(user)s has been removed as a moderator from %(vault)s"
    message = (
        "%(user)s: You have been removed as a moderator from %(vault)s.  "
        "If you have a question regarding your removal, you can "
        "contact the moderator team for %(vault)s by replying to this "
        "message."
    )
    subject %= {"vault": vault_name, "user": u_name}
    message %= {"vault": vault_name, "user": user.name}

    item, inbox_rel = Message._new(
        mod, user, subject, message, request.ip,
        vault=vault,
        from_vault=True,
        can_send_email=False,
    )
    queries.new_message(item, inbox_rel, update_modmail=True)


def send_ban_message(vault, mod, user, note=None, days=None, new=True):
    vault_name = "/v/" + vault.name
    if days:
        subject = "You've been temporarily banned from participating in %(vault)s"
        message = ("You have been temporarily banned from participating in "
            "%(vault)s. This ban will last for %(duration)s days. ")
    else:
        subject = "You've been banned from participating in %(vault)s"
        message = "You have been banned from participating in %(vault)s. "

    message += ("You can still view and subscribe to %(vault)s, but you "
                "won't be able to post or comment.")

    if not new:
        subject = "Your ban from %(vault)s has changed"

    subject %= {"vault": vault_name}
    message %= {"vault": vault_name, "duration": days}

    if note:
        message += "\n\n" + 'Note from the moderators:'
        message += "\n\n" + blockquote_text(note)

    message += "\n\n" + ("If you have a question regarding your ban, you can "
        "contact the moderator team for %(vault)s by replying to this "
        "message.") % {"vault": vault_name}

    message += "\n\n" + ("**Reminder from the Tippr staff**: If you use "
        "another account to circumvent this vault ban, that will be "
        "considered a violation of [the Content Policy](/help/contentpolicy#section_prohibited_behavior) "
        "and can result in your account being [suspended](https://reddit.zendesk.com/hc/en-us/articles/205687686) "
        "from the site as a whole.")

    item, inbox_rel = Message._new(
        mod, user, subject, message, request.ip, vault=vault, from_vault=True,
        can_send_email=False)
    queries.new_message(item, inbox_rel, update_modmail=False)

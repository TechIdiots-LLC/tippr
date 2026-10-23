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
"""How many people are on a thread now ("N here now").

The thread page asks POST /api/here_now when it opens and every minute
after (public/static/js/here-now.js): that records the visitor on the
thread in the activity service (tippr-activity) and returns how many
visitors it saw there in the last 15 minutes. Logged-in visitors count by
account, logged-out ones by their loid cookie. Counts under 100 come back
fuzzed (shown with a "~"), so a small number can't single anyone out.
"""

from pylons import app_globals as g
from pylons import tmpl_context as c
from thrift.protocol.TProtocol import TProtocolException
from thrift.Thrift import TApplicationException
from thrift.transport.TTransport import TTransportException

_ERRORS = (TApplicationException, TProtocolException, TTransportException)


def _activity_service():
    """The activity service client for this request, if one is configured
    (activity_endpoint); it lives on the baseplate request context. (The
    vaults' "users here now" uses it too.)"""
    context = getattr(c, "baseplate_context", None)
    return getattr(context, "activity_service", None) if context else None


def enabled():
    return bool(g.config.get("activity_endpoint"))


def visitor_id(user, logged_in, loid):
    """The id the activity service counts this visitor by, or None."""
    if logged_in:
        return user._fullname
    return getattr(loid, "loid", None) or None


def here_now(context_id, visitor):
    """Record visitor in context_id, then count it: (count, is_fuzzed),
    or None when the activity service can't be reached."""
    service = _activity_service()
    if not service:
        return None
    try:
        if visitor:
            service.record_activity(context_id, visitor)
        with service.retrying(attempts=4, budget=0.1) as svc:
            info = svc.count_activity(context_id)
    except _ERRORS:
        return None
    return info.count, info.is_fuzzed

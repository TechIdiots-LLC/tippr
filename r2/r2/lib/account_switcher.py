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

"""Switching between accounts, like the Reddit Enhancement Suite's account
switcher, without keeping anyone's password.

When a member adds another account (logging in to it with its password),
the session cookie of the account they were using goes into a second
cookie, the jar. Switching swaps the two. The jar is HttpOnly, like the
session cookie, so scripts can't read it, and each session in it is checked
the way a login is, so one stops working when that account's password
changes; suspended and deleted accounts drop out. Logging out empties the
jar, so a shared computer doesn't keep the other accounts.
"""

import base64
import json
import urllib.parse

from pylons import app_globals as g
from pylons import request
from pylons import tmpl_context as c

from r2.config import feature
from r2.lib.cookies import DELETE, NEVER, Cookie
from r2.lib.utils import constant_time_compare

JAR_COOKIE = "tippr_switch"
MAX_ACCOUNTS = 5


def _account_for(session):
    """The account a session cookie value logs in, if it still does."""
    from r2.models import Account, NotFound
    try:
        uid, timestr, _hash = session.split(",")
        account = Account._byID(int(uid), data=True)
    except (ValueError, NotFound):
        return None
    if account._deleted or account._banned:
        return None
    if not constant_time_compare(session, account.make_cookie(timestr)):
        return None
    return account


def _read_jar():
    raw = request.cookies.get(JAR_COOKIE)
    if not raw:
        return []
    try:
        data = base64.urlsafe_b64decode(urllib.parse.unquote(raw).encode())
        sessions = json.loads(data.decode())
    except (ValueError, TypeError):
        return []
    return [s for s in sessions if isinstance(s, str)][:MAX_ACCOUNTS]


def _write_jar(sessions):
    if not sessions:
        c.cookies[JAR_COOKIE] = Cookie(value="", expires=DELETE)
        return
    value = base64.urlsafe_b64encode(
        json.dumps(sessions[:MAX_ACCOUNTS]).encode()).decode()
    c.cookies[JAR_COOKIE] = Cookie(value=value, expires=NEVER, httponly=True,
                                   secure=feature.is_enabled("force_https"))


def _current_session():
    quoted = request.cookies.get(g.login_cookie)
    return urllib.parse.unquote(quoted) if quoted else None


def _kept():
    """[(account, session)] for the jar's valid accounts, not the current
    one."""
    found = []
    seen = {c.user._id} if c.user_is_loggedin else set()
    for session in _read_jar():
        account = _account_for(session)
        if account and account._id not in seen:
            seen.add(account._id)
            found.append((account, session))
    return found


def accounts():
    """The other accounts this browser can switch to: [(name, session)],
    valid ones only, never the current account."""
    return [(account.name, session) for account, session in _kept()]


def qualifies(account):
    """Gold members and admins get the switcher."""
    return bool(account.gold or account.name in g.admins)


def allowed():
    """Whether this browser can use the switcher: the account in use or one
    of those kept qualifies. Any of them counts, so switching to an account
    that doesn't qualify (an alt without gold) doesn't strand you there."""
    if not c.user_is_loggedin:
        return False
    return qualifies(c.user) or any(qualifies(account) for account, _s in _kept())


def names():
    return [name for name, _session in accounts()]


def remember_current():
    """Before logging in to another account: keep this one in the jar."""
    current = _current_session()
    if not current or not c.user_is_loggedin:
        return
    sessions = [current] + [s for _name, s in accounts()]
    _write_jar(sessions)


def switch_to(name):
    """Log in as one of the jar's accounts, keeping the current one in the
    jar. Returns the account, or None if it isn't in the jar."""
    others = accounts()
    target = next(((n, s) for n, s in others
                   if n.lower() == (name or "").lower()), None)
    if not target:
        return None
    current = _current_session()
    rest = [s for n, s in others if s != target[1]]
    if current and c.user_is_loggedin:
        rest.insert(0, current)
    _write_jar(rest)
    c.cookies[g.login_cookie] = Cookie(
        value=target[1], expires=NEVER, httponly=True,
        secure=feature.is_enabled("force_https"))
    # admin mode belongs to the account it was turned on for
    c.cookies[g.admin_cookie] = Cookie(value="", expires=DELETE)
    return _account_for(target[1])


def forget(name):
    """Take an account out of the jar; returns the names still in it."""
    left = [(n, s) for n, s in accounts() if n.lower() != (name or "").lower()]
    _write_jar([s for _n, s in left])
    return [n for n, _s in left]


def clear():
    """Forget every other account (on logout)."""
    if request.cookies.get(JAR_COOKIE):
        _write_jar([])

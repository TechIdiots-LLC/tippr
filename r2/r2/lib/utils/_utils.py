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
###############################################################################
"""Pure Python fallback for _utils.pyx (used when Cython module is not compiled)."""

import re
from datetime import datetime, timedelta

from pylons.i18n import _, ungettext


def to_base(q, alphabet):
    if q < 0:
        raise ValueError("must supply a positive integer")
    l = len(alphabet)
    converted = []
    while q != 0:
        q, r = divmod(q, l)
        converted.insert(0, alphabet[r])
    return "".join(converted) or '0'


def to36(q):
    return to_base(q, '0123456789abcdefghijklmnopqrstuvwxyz')


def tup(item, ret_is_single=False):
    """Forces casting of item to a tuple (for a list) or generates a
    single element tuple (for anything else)"""
    # return true for iterables, except for strings, which is what we want
    if hasattr(item, '__iter__') and not isinstance(item, (str, bytes)):
        return (item, False) if ret_is_single else item
    else:
        return ((item,), True) if ret_is_single else (item,)


def _strips(direction, text, remove):
    # Normalize bytes to text for safe startswith/endswith comparisons.
    if isinstance(text, bytes):
        text = text.decode('latin-1')
    if isinstance(remove, bytes):
        remove = remove.decode('latin-1')

    if direction == 'l':
        if text.startswith(remove):
            return text[len(remove):]
    elif direction == 'r':
        if text.endswith(remove):
            return text[:-len(remove)]
    else:
        raise ValueError("Direction needs to be r or l.")
    return text


def rstrips(text, remove):
    """
    removes the string `remove` from the right of `text`

        >>> rstrips("foobar", "bar")
        'foo'

    """
    return _strips('r', text, remove)


def lstrips(text, remove):
    """
    removes the string `remove` from the left of `text`

        >>> lstrips("foobar", "foo")
        'bar'

    """
    return _strips('l', text, remove)


def strips(text, remove):
    """removes the string `remove` from the both sides of `text`

        >>> strips("foobarfoo", "foo")
        'bar'

    """
    return rstrips(lstrips(text, remove), remove)


ESCAPE = re.compile(r'[\x00-\x19\\"\b\f\n\r\t]')
ESCAPE_ASCII = re.compile(r'([\\"/]|[^\ -~])')
ESCAPE_DCT = {
    # escape all forward slashes to prevent </script> attack
    '/': '\\/',
    '\\': '\\\\',
    '"': '\\"',
    '\b': '\\b',
    '\f': '\\f',
    '\n': '\\n',
    '\r': '\\r',
    '\t': '\\t',
}


def _string2js_replace(match):
    return ESCAPE_DCT[match.group(0)]


def string2js(s):
    """adapted from http://svn.red-bean.com/bob/simplejson/trunk/simplejson/encoder.py"""
    for i in range(20):
        ESCAPE_DCT.setdefault(chr(i), '\\u%04x' % (i,))

    if isinstance(s, bytes):
        s = s.decode('latin-1')

    return '"' + ESCAPE.sub(_string2js_replace, s) + '"'


def timeago(interval):
    """Returns a datetime object corresponding to time 'interval' in
    the past.  Interval is of the same form as is returned by
    timetext(), i.e., '10 seconds'.  The interval must be passed in in
    English (i.e., untranslated) and the format is

    [num] second|minute|hour|day|week|month|year(s)
    """
    from pylons import app_globals as g
    return datetime.now(g.tz) - timeinterval_fromstr(interval)


def timefromnow(interval):
    "The opposite of timeago"
    from pylons import app_globals as g
    return datetime.now(g.tz) + timeinterval_fromstr(interval)


def timedelta_by_name(interval):
    return timeinterval_fromstr('1 ' + interval)


timeintervald = dict(
    second=1,
    minute=60,
    hour=60 * 60,
    day=60 * 60 * 24,
    week=60 * 60 * 24 * 7,
    month=60 * 60 * 24 * 30,
    year=60 * 60 * 24 * 365,
)


def timeinterval_fromstr(interval):
    "Used by timeago and timefromnow to generate timedeltas from friendly text"
    parts = interval.strip().split(' ')
    if len(parts) == 1:
        num = 1
        period = parts[0]
    elif len(parts) == 2:
        num, period = parts
        num = int(num)
    else:
        raise ValueError('format should be ([num] second|minute|etc)')
    period = rstrips(period, 's')

    d = timeintervald[period]
    delta = num * d
    return timedelta(0, delta)


class TimeText:
    __slots__ = ('single', 'plural')

    def __init__(self, single, plural):
        self.single = single
        self.plural = plural

    def __call__(self, n):
        return ungettext(self.single, self.plural, n)


timechunks = (
    (60 * 60 * 24 * 365, TimeText('year', 'years')),
    (60 * 60 * 24 * 30, TimeText('month', 'months')),
    (60 * 60 * 24, TimeText('day', 'days')),
    (60 * 60, TimeText('hour', 'hours')),
    (60, TimeText('minute', 'minutes')),
    (1, TimeText('second', 'seconds')),
)


def timetext(delta, precision=None, bare=True):
    """
    Takes a datetime object, returns the time between then and now
    as a nicely formatted string, e.g "10 minutes"
    Adapted from django which was adapted from
    http://blog.natbat.co.uk/archive/2003/Jun/14/time_since
    """
    delta = max(delta, timedelta(0))
    since = delta.days * 24 * 60 * 60 + delta.seconds

    for i, (seconds, name) in enumerate(timechunks):
        count = since // seconds
        if count != 0:
            break

    from r2.lib.strings import strings
    if count == 0 and delta.seconds == 0 and delta != timedelta(0):
        n = delta.microseconds // 1000
        s = strings.time_label % dict(num=n,
                                      time=ungettext("millisecond",
                                                     "milliseconds", n))
    else:
        s = strings.time_label % dict(num=count, time=name(int(count)))
        if precision:
            j = 0
            while True:
                j += 1
                since -= seconds * count
                if i + j >= len(timechunks):
                    break
                if timechunks[i + j][0] < precision:
                    break
                seconds, name = timechunks[i + j]
                count = since // seconds
                if count != 0:
                    s += ', %d %s' % (count, name(count))

    if not bare:
        s += ' ' + _('ago')

    return s


def timesince(d, precision=None):
    from pylons import app_globals as g
    return timetext(datetime.now(g.tz) - d, precision)


def timeuntil(d, precision=None):
    from pylons import app_globals as g
    return timetext(d - datetime.now(g.tz), precision)


def keymap(keys, callfn, mapfn=None, prefix=''):
    """map a set of keys before a get_multi to return a dict using the
       original unmapped keys"""
    km = map_keys(keys, mapfn, prefix)
    res = callfn(km.keys())
    ret = unmap_keys(res, km)
    return ret


def map_keys(keys, mapfn, prefix):
    if (mapfn and prefix) or (not mapfn and not prefix):
        raise ValueError("Set one of mapfn or prefix")

    km = {}
    if mapfn:
        for key in keys:
            km[mapfn(key)] = key
    else:
        for key in keys:
            km[prefix + str(key)] = key
    return km


def unmap_keys(mapped_keys, km):
    ret = {}
    for key, value in mapped_keys.items():
        ret[km[key]] = value
    return ret


def prefix_keys(keys, prefix, callfn):
    if len(prefix):
        return keymap(keys, callfn, prefix=prefix)
    else:
        return callfn(keys)


def flatten(lists):
    """[[1,2], [3], [4,5,6]] -> [1,2,3,4,5,6]"""
    ret = []
    for l in lists:
        ret.extend(l)
    return ret


def _l(l):
    """Return a listified version of l, just returning l if it's
       already listified"""
    if isinstance(l, list):
        return l
    else:
        return list(l)


def get_after(fullnames, fullname, num, reverse=False):
    if reverse:
        fullnames = _l(reversed(fullnames))

    if not fullname:
        return fullnames[:num]

    for i, item in enumerate(fullnames):
        if item == fullname:
            return fullnames[i + 1:i + num + 1]

    return fullnames[:num]


__all__ = [
    'to_base', 'to36', 'tup', 'rstrips', 'lstrips', 'strips',
    'string2js', 'timeago', 'timefromnow', 'timedelta_by_name',
    'timeinterval_fromstr', 'TimeText', 'timechunks', 'timetext',
    'timesince', 'timeuntil', 'keymap', 'map_keys', 'unmap_keys',
    'prefix_keys', 'flatten', 'get_after',
]

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
"""Usernames new accounts can't take, because they'd pass for the site's
staff or the site itself: "admin", "Tippr_Mod", "SupportTeam", "аdmin" with
a Cyrillic а, "adm1n" and the like (VUname, at sign-up; accounts that
exist keep their names, and accounts the site makes itself, such as feed
bots, aren't checked).

Names are compared by their skeleton: lowercased, without accents, "_" or
"-", with letters that look like Latin ones (Cyrillic, Greek) and digits
standing in for letters made into those letters. Then:

- CONTAINED words are refused anywhere in a name ("xXadminXx");
- PART words are refused as a part of their own ("tippr_mod", "TipprMod",
  "mod-team"), but not inside other words ("modern");
- JOINED words are refused on their own, or joined to another reserved
  word or the site's name ("tipprsupport", "modteam"), but not with other
  words ("Team_Rocket", "steam");
- WHOLE words are refused only as the whole name ("root", but not
  "root_beer");
- the site's own name (site_name, and the domain's) is refused on its own
  or joined to a reserved word, but "tippr_fan" is fine;
- admins can add their own words on /admin/config (reserved_usernames),
  refused anywhere in a name.
"""

import re
import unicodedata

from pylons import app_globals as g

CONTAINED = ("admin", "moderator", "sysop", "superuser", "official")
PARTS = ("mod", "mods", "staff")
# refused as the whole name, or joined to the site's name or a reserved
# word ("tippr_team", "ModSupport"), but fine with others ("Team_Rocket")
JOINED = (
    "team", "support", "helpdesk", "help", "system", "owner", "operator",
    "security", "verified",
)
# refused only as the whole name
WHOLE = (
    "root", "abuse", "postmaster", "webmaster", "hostmaster", "noreply",
    "info", "contact", "everyone", "anonymous", "null", "undefined",
    "deleted", "removed",
)
# real words containing a CONTAINED one
ALLOWED = ("badminton",)

# letters that look like Latin ones (Cyrillic and Greek), and digits and
# letter pairs standing in for letters; applied to names and words alike
_LOOKALIKES = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "і": "i", "ј": "j", "ѕ": "s", "ԁ": "d", "һ": "h", "ӏ": "l", "м": "m",
    "т": "t", "к": "k", "в": "b", "н": "h",
    "α": "a", "ε": "e", "ο": "o", "ρ": "p", "ι": "i", "κ": "k", "ν": "v",
    "τ": "t", "υ": "u", "μ": "m",
    "0": "o", "1": "i", "l": "i", "3": "e", "4": "a", "5": "s", "7": "t",
    "8": "b", "9": "g",
})
_parts_re = re.compile(r"[_\-]+|(?<=[a-z])(?=[A-Z])|\d+")


def skeleton(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().translate(_LOOKALIKES)
    text = text.replace("rn", "m").replace("vv", "w")
    return re.sub(r"[^a-z]+", "", text)


def _site_words():
    words = set()
    for name in (getattr(g, "site_name", None),
                 (getattr(g, "domain", None) or "").split(".")[0]):
        word = skeleton(name)
        if len(word) >= 3:
            words.add(word)
    return words


def _admin_words():
    try:
        words = g.live_config.get("reserved_usernames") or ()
    except Exception:
        return set()
    return {w for w in (skeleton(word) for word in words) if len(w) >= 3}


def is_reserved(name):
    """Whether a new account may not be called name."""
    whole = skeleton(name)
    if not whole:
        return False
    for allowed in ALLOWED:
        whole = whole.replace(allowed, "")
    contained = {skeleton(w) for w in CONTAINED} | _admin_words()
    if any(word in whole for word in contained):
        return True
    parts = {skeleton(w) for w in PARTS}
    # each part of the name as written ("Tippr_Mod", "TipprMod", "mod2")
    if any(skeleton(part) in parts for part in _parts_re.split(name or "")):
        return True
    site = _site_words()
    joined = {skeleton(w) for w in JOINED}
    joinable = parts | joined | contained | site
    if whole in joinable or whole in {skeleton(w) for w in WHOLE}:
        return True
    # two reserved words (or the site's name and one) run together, or side
    # by side ("the_tippr_team")
    for i in range(1, len(whole)):
        if whole[:i] in joinable and whole[i:] in joinable:
            return True
    written = [skeleton(part) for part in _parts_re.split(name or "")]
    written = [part for part in written if part]
    return any(a in joinable and b in joinable
               for a, b in zip(written, written[1:]))

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

"""Members' private tags on other users, like the Reddit Enhancement Suite's
user tagger.

A tag is a short note and a colour that only its owner sees, next to the
user's name wherever it appears (enhancements.js shows them; the page gets
the member's tags in r.config.user_tags). They're kept on the member's
account, so they follow them to every device, and come with their data
export.
"""

MAX_TAGS = 2000
MAX_LENGTH = 64

# the colours a tag can have: name -> background (text is white on them)
COLORS = {
    "none": "",
    "gray": "#6b7f86",
    "red": "#c0392b",
    "orange": "#d35400",
    "yellow": "#b7950b",
    "green": "#1e8449",
    "teal": "#0b7f8c",
    "blue": "#2e5fa3",
    "purple": "#7d3c98",
    "pink": "#c2185b",
    "brown": "#795548",
    "black": "#222222",
}


class TooManyTags(Exception):
    pass


def get(user):
    """The member's tags: {lowercased username: {"tag", "color"}}."""
    return dict(getattr(user, "user_tags", None) or {})


def set_tag(user, username, tag, color):
    """Tag (or, with an empty tag and no colour, untag) a username."""
    tags = get(user)
    key = username.lower()
    tag = (tag or "").strip()[:MAX_LENGTH]
    if color not in COLORS:
        color = "none"
    if not tag and color == "none":
        tags.pop(key, None)
    else:
        if key not in tags and len(tags) >= MAX_TAGS:
            raise TooManyTags
        tags[key] = {"tag": tag, "color": color}
    # a new dict, so the account sees the change and saves it
    user.user_tags = tags
    user._commit()
    return tags.get(key)


def for_page(user):
    """What the page's script needs: {username: [tag, background]}."""
    return {name: [t.get("tag", ""), COLORS.get(t.get("color"), "")]
            for name, t in get(user).items()}

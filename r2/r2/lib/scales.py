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
"""Scales: what the community thinks a post is like.

Up and down votes rank posts; scales describe them. Each scale has two
sides, the two ends of one kind of difference (human-made or AI-generated, a
quick overview or a deep dive...), so they describe what kind of post it
is rather than how good it is (votes say that). A member can tip each
one toward a side, change their mind, or take the tip back. A scale's
tally is shown to a member once they've tipped it (so the first few tips
don't steer everyone else's), to the poster, and to the vault's
moderators and admins in admin mode, whose job is to read them. With
fewer than BAR_MIN tips the panel names them rather than drawing a bar,
since one person's tip isn't the community's view.

A member who'd rather not tip can "see results" instead: every tally, at
the price of tipping that post (they can't tip or change a tip after).

Scales are opinions, not reports: none of them asks moderators to act
(breaking a rule is what "report" is for), none changes a post's ranking,
and "AI-generated" is the community's view, beside the poster's own AI
label (r2.lib.ai_content), not a change to it.

Tips are a PostgreSQL table, so they move with backups; tallies are
counted when someone opens a post's scales.
"""

from collections import OrderedDict
from datetime import datetime

import sqlalchemy as sa
from pylons import app_globals as g
from pylons.i18n import N_, _

from r2.lib.utils import to36

LEFT = -1
RIGHT = 1
SIDES = (LEFT, RIGHT)

# name: (left side, right side), each pair two ends of one difference, not
# good and bad. A name is what tips are kept under: a scale whose sides
# change meaning gets a new name (helpful, level, purpose and sources were
# retired so; their tips are kept but no longer shown)
SCALES = OrderedDict([
    ("made", (N_("human-made"), N_("AI-generated"))),
    ("depth", (N_("quick overview"), N_("deep dive"))),
    ("nature", (N_("practical"), N_("thought piece"))),
    # how it backs up what it says, not whether it's right
    ("evidence", (N_("data-driven"), N_("personal experience"))),
    ("tone", (N_("matter-of-fact"), N_("passionate"))),
    ("scope", (N_("niche"), N_("broad"))),
])
# the retired ones' sides, for members' data exports of tips made then
RETIRED = {
    "helpful": ("helpful", "unhelpful"),
    "level": ("beginner-friendly", "in-depth"),
    "purpose": ("practical", "just for fun"),
    "sources": ("well-sourced", "opinion"),
}
# fewer tips than this are listed, not drawn as a bar (scales.js)
BAR_MIN = 3
# kept in the tips table under this name (no scale has it) once a member
# has seen a post's results without tipping (see_results)
SEEN = "_seen"

_db = {}


def _tips_table(metadata):
    return sa.Table(
        "scale_tips", metadata,
        sa.Column("link_id", sa.BigInteger, primary_key=True),
        sa.Column("account_id", sa.BigInteger, primary_key=True),
        sa.Column("scale", sa.String(20), primary_key=True),
        sa.Column("side", sa.SmallInteger, nullable=False),  # LEFT or RIGHT
        sa.Column("created", sa.DateTime(timezone=True), nullable=False),
    )


def _engine():
    """The database and the tips table (made on first use, so importing
    this needs no database)."""
    if "engine" not in _db:
        from r2.lib.db.tdb_sql import create_table, index_str, make_metadata
        engine = g.dbm.get_engine("main")
        table = _tips_table(make_metadata(engine))
        create_table(table, [
            index_str(table, "account_id", "account_id"),
        ])
        _db.update(engine=engine, table=table)
    return _db["engine"]


def _table():
    _engine()
    return _db["table"]


def can_tip(link, account):
    """Whether account may tip link's scales: a member's, on a post that
    isn't theirs and is still open."""
    return bool(
        account and link and
        link.author_id != account._id and
        not link._deleted and not link._spam and
        link.promoted is None and
        not link.archived_slow and
        not account.in_timeout)


def tip(link, account, scale, side):
    """Tip scale toward side (LEFT or RIGHT), or take the tip back
    (side 0)."""
    if scale not in SCALES or side not in SIDES + (0,):
        raise ValueError((scale, side))
    tips = _table()
    where = sa.and_(tips.c.link_id == link._id,
                    tips.c.account_id == account._id,
                    tips.c.scale == scale)
    with _engine().begin() as conn:
        conn.execute(tips.delete().where(where))
        if side:
            conn.execute(tips.insert().values(
                link_id=link._id, account_id=account._id, scale=scale,
                side=side, created=datetime.now(g.tz)))


def _rows_by(link, account):
    """{scale: side} of account's rows on link (SEEN among them)."""
    if not account:
        return {}
    tips = _table()
    with _engine().connect() as conn:
        rows = conn.execute(
            sa.select(tips.c.scale, tips.c.side).where(sa.and_(
                tips.c.link_id == link._id,
                tips.c.account_id == account._id)))
        return {scale: side for scale, side in rows}


def tips_by(link, account):
    """{scale: side} for the scales account has tipped on link."""
    return {scale: side for scale, side in _rows_by(link, account).items()
            if scale != SEEN}


def has_seen(link, account):
    """Whether account chose to see link's results (see_results)."""
    return SEEN in _rows_by(link, account)


def may_tip(link, account):
    """can_tip, unless they've seen the results (POST_tip_scale)."""
    return can_tip(link, account) and not has_seen(link, account)


def see_results(link, account):
    """Show account every tally of link, which ends their tipping on it:
    the tips they made stay, and they can't tip or change one after."""
    if has_seen(link, account):
        return
    with _engine().begin() as conn:
        conn.execute(_table().insert().values(
            link_id=link._id, account_id=account._id, scale=SEEN, side=0,
            created=datetime.now(g.tz)))


def tallies(link):
    """{scale: {LEFT: n, RIGHT: n}} for every scale."""
    found = {scale: {LEFT: 0, RIGHT: 0} for scale in SCALES}
    tips = _table()
    with _engine().connect() as conn:
        rows = conn.execute(
            sa.select(tips.c.scale, tips.c.side, sa.func.count())
            .where(tips.c.link_id == link._id)
            .group_by(tips.c.scale, tips.c.side))
        for scale, side, count in rows:
            if scale in found and side in SIDES:
                found[scale][side] = count
    return found


def summary(link, account, sees_all=False):
    """What a post's scales panel shows account (None: logged out): each
    scale's sides, their own tip, and the tally where they may see it.
    sees_all: every tally, untipped (the vault's moderators, admins in
    admin mode; POST_scales decides)."""
    rows = _rows_by(link, account)
    seen = SEEN in rows
    mine = {scale: side for scale, side in rows.items() if scale != SEEN}
    is_poster = bool(account and link.author_id == account._id)
    counts = tallies(link)
    scales = []
    for name, (left, right) in SCALES.items():
        side = mine.get(name, 0)
        shown = bool(side) or is_poster or sees_all or seen
        scales.append({
            "name": name,
            "left": _(left),
            "right": _(right),
            "mine": side,
            "tally": ({"left": counts[name][LEFT],
                       "right": counts[name][RIGHT]} if shown else None),
        })
    return {
        "scales": scales,
        "can_tip": can_tip(link, account) and not seen,
        "is_poster": is_poster,
        # chose to see the results, so can't tip any more
        "seen": seen,
        "sees_all": bool(sees_all) and not is_poster,
        "bar_min": BAR_MIN,
    }


def export(account, limit=1000):
    """The tips account has made, for their data export
    (r2.lib.privacy_export)."""
    tips = _table()
    with _engine().connect() as conn:
        rows = conn.execute(
            sa.select(tips.c.link_id, tips.c.scale, tips.c.side,
                      tips.c.created)
            .where(tips.c.account_id == account._id)
            .order_by(tips.c.created.desc())
            .limit(limit))
        found = []
        for link_id, scale, side, created in rows:
            if scale == SEEN:
                found.append({"post_id": to36(link_id),
                              "saw_results_at": created.isoformat()})
                continue
            left, right = (SCALES.get(scale) or
                           RETIRED.get(scale, (scale, scale)))
            found.append({
                "post_id": to36(link_id),
                "scale": scale,
                "tipped_toward": left if side == LEFT else right,
                "tipped_at": created.isoformat(),
            })
        return found

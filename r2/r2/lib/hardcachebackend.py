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

import random
from datetime import datetime
from datetime import timedelta as timedelta

import pytz
try:
    import sqlalchemy as sa
except Exception:
    # Minimal fallback namespace when SQLAlchemy isn't installed during test
    # collection. This stub only exists to avoid import-time failures; any
    # actual use of the DB-backed hardcache will raise at runtime.
    class _SAExc:
        class IntegrityError(Exception):
            pass

    def _raise_missing(*a, **kw):
        raise RuntimeError("sqlalchemy is required for HardCacheBackend")

    class _SAStub:
        exc = _SAExc
        Integer = int
        String = str
        DateTime = object

        @staticmethod
        def select(*a, **kw):
            return _raise_missing()

        @staticmethod
        def Table(*a, **kw):
            return _raise_missing()

        @staticmethod
        def Column(*a, **kw):
            return _raise_missing()

        @staticmethod
        def and_(*a, **kw):
            return _raise_missing()

        @staticmethod
        def or_(*a, **kw):
            return _raise_missing()

        @staticmethod
        def cast(*a, **kw):
            return _raise_missing()

    sa = _SAStub()
from pylons import app_globals as g

from r2.lib.db.tdb_lite import tdb_lite

COUNT_CATEGORY = 'hc_count'
ELAPSED_CATEGORY = 'hc_elapsed'
TZ = pytz.timezone("MST")


def _get_engine(table):
    """Get the engine from a table (SQLAlchemy 2.0 compat)."""
    return table.metadata._engine


def _execute(table, stmt):
    """Execute a statement and return the result."""
    engine = _get_engine(table)
    with engine.connect() as conn:
        result = conn.execute(stmt)
        conn.commit()
        return result


def _select(table, stmt):
    """Execute a select statement and return all rows."""
    engine = _get_engine(table)
    with engine.connect() as conn:
        return conn.execute(stmt).fetchall()

def expiration_from_time(time):
    if time <= 0:
        raise ValueError ("HardCache items *must* have an expiration time")
    return datetime.now(TZ) + timedelta(0, time)

class HardCacheBackend:
    def __init__(self, gc):
        self.tdb = tdb_lite(gc)
        self.profile_categories = {}
        TZ = gc.display_tz

        def _table(metadata):
            return sa.Table(gc.db_app_name + '_hardcache', metadata,
                            sa.Column('category', sa.String, nullable = False,
                                      primary_key = True),
                            sa.Column('ids', sa.String, nullable = False,
                                      primary_key = True),
                            sa.Column('value', sa.String, nullable = False),
                            sa.Column('kind', sa.String, nullable = False),
                            sa.Column('expiration',
                                      sa.DateTime(timezone = True),
                                      nullable = False)
                            )
        enginenames_by_category = {}
        all_enginenames = set()
        for item in gc.hardcache_categories:
            chunks = item.split(":")
            if len(chunks) < 2:
                raise ValueError("Invalid hardcache_overrides")
            category = chunks.pop(0)
            enginenames_by_category[category] = []
            for c in chunks:
                if c == '!profile':
                    self.profile_categories[category] = True
                elif c.startswith("!"):
                    raise ValueError("WTF is [%s] in hardcache_overrides?" % c)
                else:
                    all_enginenames.add(c)
                    enginenames_by_category[category].append(c)

        assert('*' in list(enginenames_by_category.keys()))

        engines_by_enginename = {}
        for enginename in all_enginenames:
            engine = gc.dbm.get_engine(enginename)
            md = self.tdb.make_metadata(engine)
            table = _table(md)
            indstr = self.tdb.index_str(table, 'expiration', 'expiration')
            self.tdb.create_table(table, [ indstr ])
            engines_by_enginename[enginename] = table

        self.mapping = {}
        for category, enginenames in enginenames_by_category.items():
            self.mapping[category] = [ engines_by_enginename[e]
                                       for e in enginenames]

    def engine_by_category(self, category, type="master"):
        if category not in self.mapping:
            category = '*'
        engines = self.mapping[category]
        if type == 'master':
            return engines[0]
        elif type == 'readslave':
            return random.choice(engines[1:])
        else:
            raise ValueError("invalid type %s" % type)

    def profile_start(self, operation, category):
        if category == COUNT_CATEGORY:
            return None

        if category == ELAPSED_CATEGORY:
            return None

        if category in self.mapping:
            effective_category = category
        else:
            effective_category = '*'

        if effective_category not in self.profile_categories:
            return None

        return (datetime.now(TZ), operation, category)

    def profile_stop(self, t):
        if t is None:
            return

        start_time, operation, category = t

        end_time = datetime.now(TZ)

        period = end_time.strftime("%Y/%m/%d_%H:%M")[:-1] + 'x'

        elapsed = end_time - start_time
        msec = elapsed.seconds * 1000 + elapsed.microseconds / 1000

        ids = "-".join((operation, category, period))

        self.add(COUNT_CATEGORY, ids, 0, time=86400)
        self.add(ELAPSED_CATEGORY, ids, 0, time=86400)

        self.incr(COUNT_CATEGORY, ids, time=86400)
        self.incr(ELAPSED_CATEGORY, ids, time=86400, delta=msec)


    def set(self, category, ids, val, time):

        self.delete(category, ids) # delete it if it already exists

        value, kind = self.tdb.py2db(val, True)

        expiration = expiration_from_time(time)

        prof = self.profile_start('set', category)

        table = self.engine_by_category(category, "master")

        _execute(table, table.insert().values(
            category=category,
            ids=ids,
            value=value,
            kind=kind,
            expiration=expiration
        ))

        self.profile_stop(prof)

    def add(self, category, ids, val, time=0):
        self.delete_if_expired(category, ids)

        expiration = expiration_from_time(time)

        value, kind = self.tdb.py2db(val, True)

        prof = self.profile_start('add', category)

        table = self.engine_by_category(category, "master")

        try:
            _execute(table, table.insert().values(
                category=category,
                ids=ids,
                value=value,
                kind=kind,
                expiration=expiration
            ))
            self.profile_stop(prof)
            return value

        except sa.exc.IntegrityError:
            self.profile_stop(prof)
            return self.get(category, ids, force_write_table=True)

    def incr(self, category, ids, time=0, delta=1):
        self.delete_if_expired(category, ids)

        expiration = expiration_from_time(time)

        prof = self.profile_start('incr', category)

        table = self.engine_by_category(category, "master")

        stmt = table.update().where(
            sa.and_(table.c.category==category,
                    table.c.ids==ids,
                    table.c.kind=='num')
        ).values({
            table.c.value: sa.cast(
                sa.cast(table.c.value, sa.Integer) + delta, sa.String),
            table.c.expiration: expiration
        })
        rp = _execute(table, stmt)

        self.profile_stop(prof)

        if rp.rowcount == 1:
            return self.get(category, ids, force_write_table=True)
        elif rp.rowcount == 0:
            existing_value = self.get(category, ids, force_write_table=True)
            if existing_value is None:
                raise ValueError("[%s][%s] can't be incr()ed -- it's not set" %
                                 (category, ids))
            else:
                raise ValueError("[%s][%s] has non-integer value %r" %
                                 (category, ids, existing_value))
        else:
            raise ValueError("Somehow %d rows got updated" % rp.rowcount)

    def get(self, category, ids, force_write_table=False):
        if force_write_table:
            type = "master"
        else:
            type = "readslave"

        table = self.engine_by_category(category, type)

        prof = self.profile_start('get', category)

        s = sa.select(table.c.value, table.c.kind, table.c.expiration).where(
            sa.and_(table.c.category==category, table.c.ids==ids)
        ).limit(1)
        rows = _select(table, s)

        self.profile_stop(prof)

        if len(rows) < 1:
            return None
        elif rows[0].expiration < datetime.now(TZ):
            return None
        else:
            return self.tdb.db2py(rows[0].value, rows[0].kind)

    def get_multi(self, category, idses):
        prof = self.profile_start('get_multi', category)

        table = self.engine_by_category(category, "readslave")

        s = sa.select(table.c.ids, table.c.value, table.c.kind, table.c.expiration).where(
            sa.and_(table.c.category==category,
                    sa.or_(*[table.c.ids==ids for ids in idses])))
        rows = _select(table, s)

        self.profile_stop(prof)

        results = {}

        for row in rows:
          if row.expiration >= datetime.now(TZ):
              k = "{}-{}".format(category, row.ids)
              results[k] = self.tdb.db2py(row.value, row.kind)

        return results

    def delete(self, category, ids):
        prof = self.profile_start('delete', category)
        table = self.engine_by_category(category, "master")
        _execute(table, table.delete().where(
            sa.and_(table.c.category==category, table.c.ids==ids)))
        self.profile_stop(prof)

    def ids_by_category(self, category, limit=1000):
        prof = self.profile_start('ids_by_category', category)
        table = self.engine_by_category(category, "readslave")
        s = sa.select(table.c.ids).where(
            sa.and_(table.c.category==category,
                    table.c.expiration > datetime.now(TZ))
        ).limit(limit)
        rows = _select(table, s)
        self.profile_stop(prof)
        return [ r.ids for r in rows ]

    def clause_from_expiration(self, table, expiration):
        if expiration is None:
            return True
        elif expiration == "now":
            return table.c.expiration < datetime.now(TZ)
        else:
            return table.c.expiration < expiration

    def expired(self, table, expiration_clause, limit=1000):
        s = sa.select(table.c.category, table.c.ids, table.c.expiration).where(
            expiration_clause
        ).limit(limit).order_by(table.c.expiration)
        rows = _select(table, s)
        return [ (r.expiration, r.category, r.ids) for r in rows ]

    def delete_if_expired(self, category, ids, expiration="now"):
        prof = self.profile_start('delete_if_expired', category)
        table = self.engine_by_category(category, "master")
        expiration_clause = self.clause_from_expiration(table, expiration)
        _execute(table, table.delete().where(
            sa.and_(table.c.category==category,
                    table.c.ids==ids,
                    expiration_clause)))
        self.profile_stop(prof)


def delete_expired(expiration="now", limit=5000):
    # the following depends on the structure of g.hardcache not changing
    backend = g.hardcache.caches[1].backend
    # localcache = g.hardcache.caches[0]

    masters = set()

    for tables in list(backend.mapping.values()):
        masters.add(tables[0])

    for table in masters:
        expiration_clause = backend.clause_from_expiration(table, expiration)

        # Get all the expired keys
        rows = backend.expired(table, expiration_clause, limit)

        if len(rows) == 0:
            continue

        # Delete from the backend.
        _execute(table, table.delete().where(expiration_clause))

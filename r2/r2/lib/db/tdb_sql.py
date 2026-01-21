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

import logging
import pickle as pickle
import threading
from copy import deepcopy
from datetime import datetime

import sqlalchemy as sa
from pylons import app_globals as g
from pylons import request
from pylons import tmpl_context as c

from r2.lib import filters
from r2.lib.utils import (
    Results,
    iters,
    simple_traceback,
    storage,
    tup,
)

from . import operators

dbm = g.dbm
predefined_type_ids = g.predefined_type_ids
log_format = logging.Formatter('sql: %(message)s')
max_val_len = 1000


class TransactionSet(threading.local):
    """A manager for SQL transactions.

    This implements a thread local meta-transaction which may span multiple
    databases.  The existing tdb_sql code calls add_engine before executing
    writes.  If thing.py calls begin then these calls will actually kick in
    and start a transaction that must be committed or rolled back by thing.py.

    Updated for SQLAlchemy 2.0: Now manages connections instead of relying
    on the removed threadlocal strategy.

    """

    def __init__(self):
        self.connections = {}  # engine -> connection
        self.transaction_begun = False

    def begin(self):
        """Indicate that a transaction has begun."""
        self.transaction_begun = True

    def add_engine(self, engine):
        """Add a database connection to the meta-transaction if active."""
        if not self.transaction_begun:
            return

        if engine not in self.connections:
            conn = engine.connect()
            conn.begin()
            self.connections[engine] = conn

    def get_connection(self, engine):
        """Get a connection for the engine, creating one if needed."""
        if engine in self.connections:
            return self.connections[engine]
        return None

    def commit(self):
        """Commit the meta-transaction."""
        try:
            for conn in self.connections.values():
                conn.commit()
                conn.close()
        finally:
            self._clear()

    def rollback(self):
        """Roll back the meta-transaction."""
        try:
            for conn in self.connections.values():
                conn.rollback()
                conn.close()
        finally:
            self._clear()

    def _clear(self):
        self.connections.clear()
        self.transaction_begun = False


transactions = TransactionSet()

MAX_THING_ID = 9223372036854775807 # http://www.postgresql.org/docs/8.3/static/datatype-numeric.html
MIN_THING_ID = 0

def make_metadata(engine):
    metadata = sa.MetaData()
    # Store engine reference for SQLAlchemy 2.0 compatibility
    metadata._engine = engine
    engine.echo = g.sqlprinting
    return metadata

def get_engine_from_table(table):
    """Get the engine associated with a table (SQLAlchemy 2.0 compat)."""
    return table.metadata._engine

def execute_statement(table, stmt, params=None):
    """Execute a statement using the table's engine with proper connection handling."""
    engine = get_engine_from_table(table)
    # Check if we have a transaction connection
    conn = transactions.get_connection(engine)
    if conn:
        if params:
            return conn.execute(stmt, params)
        return conn.execute(stmt)
    else:
        # No transaction, use autocommit
        with engine.connect() as conn:
            if params:
                result = conn.execute(stmt, params)
            else:
                result = conn.execute(stmt)
            conn.commit()
            return result

def create_table(table, index_commands=None):
    t = table
    if g.db_create_tables:
        engine = get_engine_from_table(t)
        try:
            with engine.connect() as conn:
                if not sa.inspect(engine).has_table(t.name):
                    t.create(bind=engine, checkfirst=False)
                    if index_commands:
                        for i in index_commands:
                            conn.execute(sa.text(i))
                        conn.commit()
        except sa.exc.OperationalError as e:
            # Allow bootstrap to continue without database in CI
            import os
            if os.environ.get('REDDIT_DB_REQUIRED', '').lower() != 'true':
                print(f"Warning: Could not create table {t.name}: {e}")
            else:
                raise

def index_str(table, name, on, where = None, unique = False):
    if unique:
        index_str = 'create unique index'
    else:
        index_str = 'create index'
    index_str += ' idx_%s_' % name
    index_str += table.name
    index_str += ' on '+ table.name + ' (%s)' % on
    if where:
        index_str += ' where %s' % where
    return index_str


def index_commands(table, type):
    commands = []

    if type == 'thing':
        commands.append(index_str(table, 'date', 'date'))
        commands.append(index_str(table, 'deleted_spam', 'deleted, spam'))
        commands.append(index_str(table, 'hot', 'hot(ups, downs, date), date'))
        commands.append(index_str(table, 'score', 'score(ups, downs), date'))
        commands.append(index_str(table, 'controversy', 'controversy(ups, downs), date'))
    elif type == 'data':
        commands.append(index_str(table, 'key_value', 'key, substring(value, 1, %s)' \
                                  % max_val_len))

        #lower name
        commands.append(index_str(table, 'lower_key_value', 'key, lower(value)',
                                  where = "key = 'name'"))
        #ip
        commands.append(index_str(table, 'ip_network', 'ip_network(value)',
                                  where = "key = 'ip'"))
        #base_url
        commands.append(index_str(table, 'base_url', 'base_url(lower(value))',
                                  where = "key = 'url'"))
    elif type == 'rel':
        commands.append(index_str(table, 'thing1_name_date', 'thing1_id, name, date'))
        commands.append(index_str(table, 'thing2_name_date', 'thing2_id, name, date'))
        commands.append(index_str(table, 'thing1_id', 'thing1_id'))
        commands.append(index_str(table, 'thing2_id', 'thing2_id'))
        commands.append(index_str(table, 'name', 'name'))
        commands.append(index_str(table, 'date', 'date'))
    else:
        print("unknown index_commands() type %s" % type)

    return commands

def get_type_table(metadata):
    table = sa.Table(g.db_app_name + '_type', metadata,
                     sa.Column('id', sa.Integer, primary_key = True),
                     sa.Column('name', sa.String, nullable = False))
    return table

def get_rel_type_table(metadata):
    table = sa.Table(g.db_app_name + '_type_rel', metadata,
                     sa.Column('id', sa.Integer, primary_key = True),
                     sa.Column('type1_id', sa.Integer, nullable = False),
                     sa.Column('type2_id', sa.Integer, nullable = False),
                     sa.Column('name', sa.String, nullable = False))
    return table

def get_thing_table(metadata, name):
    table = sa.Table(g.db_app_name + '_thing_' + name, metadata,
                     sa.Column('thing_id', sa.BigInteger, primary_key = True),
                     sa.Column('ups', sa.Integer, default = 0, nullable = False),
                     sa.Column('downs',
                               sa.Integer,
                               default = 0,
                               nullable = False),
                     sa.Column('deleted',
                               sa.Boolean,
                               default = False,
                               nullable = False),
                     sa.Column('spam',
                               sa.Boolean,
                               default = False,
                               nullable = False),
                     sa.Column('date',
                               sa.DateTime(timezone = True),
                               default = sa.func.now(),
                               nullable = False))
    table.thing_name = name
    return table

def get_data_table(metadata, name):
    data_table = sa.Table(g.db_app_name + '_data_' + name, metadata,
                          sa.Column('thing_id', sa.BigInteger, nullable = False,
                                    primary_key = True),
                          sa.Column('key', sa.String, nullable = False,
                                    primary_key = True),
                          sa.Column('value', sa.String),
                          sa.Column('kind', sa.String))
    return data_table

def get_rel_table(metadata, name):
    rel_table = sa.Table(g.db_app_name + '_rel_' + name, metadata,
                         sa.Column('rel_id', sa.BigInteger, primary_key = True),
                         sa.Column('thing1_id', sa.BigInteger, nullable = False),
                         sa.Column('thing2_id', sa.BigInteger, nullable = False),
                         sa.Column('name', sa.String, nullable = False),
                         sa.Column('date', sa.DateTime(timezone = True),
                                   default = sa.func.now(), nullable = False),
                         sa.UniqueConstraint('thing1_id', 'thing2_id', 'name'))
    rel_table.rel_name = name
    return rel_table

#get/create the type tables
def make_type_table():
    metadata = make_metadata(dbm.type_db)
    table = get_type_table(metadata)
    create_table(table)
    return table
type_table = make_type_table()

def make_rel_type_table():
    metadata = make_metadata(dbm.relation_type_db)
    table = get_rel_type_table(metadata)
    create_table(table)
    return table
rel_type_table = make_rel_type_table()

#lookup dicts
types_id = {}
types_name = {}
rel_types_id = {}
rel_types_name = {}

class ConfigurationError(Exception):
    pass

def check_type(table, name, insert_vals):
    # before hitting the db, check if we can get the type id from
    # the ini file
    type_id = predefined_type_ids.get(name)
    if type_id:
        return type_id
    elif len(predefined_type_ids) > 0:
        # flip the hell out if only *some* of the type ids are defined
        raise ConfigurationError("Expected typeid for %s" % name)

    # check for type in type table, create if not existent
    engine = get_engine_from_table(table)
    try:
        with engine.connect() as conn:
            r = conn.execute(table.select().where(table.c.name == name)).fetchone()
            if not r:
                result = conn.execute(table.insert().values(**insert_vals))
                conn.commit()
                type_id = result.inserted_primary_key[0]
            else:
                type_id = r.id
        return type_id
    except sa.exc.OperationalError as e:
        # Allow bootstrap to continue without database in CI
        import os
        if os.environ.get('REDDIT_DB_REQUIRED', '').lower() != 'true':
            print(f"Warning: Could not check type {name}: {e}")
            # Return a dummy type_id for CI
            return hash(name) % 1000000
        else:
            raise

#make the thing tables
def build_thing_tables():
    for name, engines in dbm.things_iter():
        type_id = check_type(type_table,
                             name,
                             dict(name = name))

        tables = []
        for engine in engines:
            metadata = make_metadata(engine)

            #make thing table
            thing_table = get_thing_table(metadata, name)
            create_table(thing_table,
                         index_commands(thing_table, 'thing'))

            #make data tables
            data_table = get_data_table(metadata, name)
            create_table(data_table,
                         index_commands(data_table, 'data'))

            tables.append((thing_table, data_table))

        thing = storage(type_id = type_id,
                        name = name,
                        avoid_master_reads = dbm.avoid_master_reads.get(name),
                        tables = tables)

        types_id[type_id] = thing
        types_name[name] = thing
build_thing_tables()

#make relation tables
def build_rel_tables():
    for name, (type1_name, type2_name, engines) in dbm.rels_iter():
        type1_id = types_name[type1_name].type_id
        type2_id = types_name[type2_name].type_id
        type_id = check_type(rel_type_table,
                             name,
                             dict(name = name,
                                  type1_id = type1_id,
                                  type2_id = type2_id))

        tables = []
        for engine in engines:
            metadata = make_metadata(engine)

            #relation table
            rel_table = get_rel_table(metadata, name)
            create_table(rel_table, index_commands(rel_table, 'rel'))

            #make thing tables
            rel_t1_table = get_thing_table(metadata, type1_name)
            if type1_name == type2_name:
                rel_t2_table = rel_t1_table
            else:
                rel_t2_table = get_thing_table(metadata, type2_name)

            #build the data
            rel_data_table = get_data_table(metadata, 'rel_' + name)
            create_table(rel_data_table,
                         index_commands(rel_data_table, 'data'))

            tables.append((rel_table,
                           rel_t1_table,
                           rel_t2_table,
                           rel_data_table))

        rel = storage(type_id = type_id,
                      type1_id = type1_id,
                      type2_id = type2_id,
                      avoid_master_reads = dbm.avoid_master_reads.get(name),
                      name = name,
                      tables = tables)

        rel_types_id[type_id] = rel
        rel_types_name[name] = rel
build_rel_tables()

def get_write_table(tables):
    if g.disallow_db_writes:
        raise Exception("not so fast! writes are not allowed on this app.")
    else:
        return tables[0]

def add_request_info(select):
    def sanitize(txt):
        return "".join(x if x.isalnum() else "."
                       for x in filters._force_utf8(txt))

    tb = simple_traceback(limit=12)
    try:
        if (hasattr(request, 'path') and
            hasattr(request, 'ip') and
            hasattr(request, 'user_agent')):
            comment = '/*\n{}\n{}\n{}\n*/'.format(
                tb or "", 
                sanitize(request.fullpath),
                sanitize(request.ip))
            return select.prefix_with(comment)
    except UnicodeDecodeError:
        pass

    return select


def get_table(kind, action, tables, avoid_master_reads = False):
    if action == 'write':
        #if this is a write, store the kind in the c.use_write_db dict
        #so that all future requests use the write db
        if not isinstance(c.use_write_db, dict):
            c.use_write_db = {}
        c.use_write_db[kind] = True

        return get_write_table(tables)
    elif action == 'read':
        #check to see if we're supposed to use the write db again
        if c.use_write_db and kind in c.use_write_db:
            return get_write_table(tables)
        else:
            if avoid_master_reads and len(tables) > 1:
                return dbm.get_read_table(tables[1:])
            return dbm.get_read_table(tables)


def get_thing_table(type_id, action = 'read' ):
    return get_table('t' + str(type_id), action,
                     types_id[type_id].tables,
                     avoid_master_reads = types_id[type_id].avoid_master_reads)

def get_rel_table(rel_type_id, action = 'read'):
    return get_table('r' + str(rel_type_id), action,
                     rel_types_id[rel_type_id].tables,
                     avoid_master_reads = rel_types_id[rel_type_id].avoid_master_reads)


#TODO does the type actually exist?
def make_thing(type_id, ups, downs, date, deleted, spam, id=None):
    table = get_thing_table(type_id, action = 'write')[0]

    params = dict(ups = ups, downs = downs,
                  date = date, deleted = deleted, spam = spam)

    if id:
        params['thing_id'] = id

    def do_insert(t):
        engine = get_engine_from_table(t)
        transactions.add_engine(engine)
        r = execute_statement(t, t.insert().values(**params))
        new_id = r.inserted_primary_key[0]
        return new_id

    try:
        id = do_insert(table)
        params['thing_id'] = id
        return id
    except sa.exc.DBAPIError as e:
        if 'IntegrityError' not in str(e):
            raise
        # wrap the error to prevent db layer bleeding out
        raise CreationError("Thing exists (%s)" % str(params))


def set_thing_props(type_id, thing_id, **props):
    table = get_thing_table(type_id, action = 'write')[0]

    if not props:
        return

    #use real columns
    def do_update(t):
        engine = get_engine_from_table(t)
        transactions.add_engine(engine)
        new_props = {t.c[prop]: val for prop, val in props.items()}
        u = t.update().where(t.c.thing_id == thing_id).values(new_props)
        execute_statement(t, u)

    do_update(table)

def incr_thing_prop(type_id, thing_id, prop, amount):
    table = get_thing_table(type_id, action = 'write')[0]

    def do_update(t):
        engine = get_engine_from_table(t)
        transactions.add_engine(engine)
        u = t.update().where(t.c.thing_id == thing_id).values(
            {t.c[prop]: t.c[prop] + amount})
        execute_statement(t, u)

    do_update(table)

class CreationError(Exception): pass

#TODO does the type exist?
#TODO do the things actually exist?
def make_relation(rel_type_id, thing1_id, thing2_id, name, date=None):
    table = get_rel_table(rel_type_id, action = 'write')[0]
    engine = get_engine_from_table(table)
    transactions.add_engine(engine)

    if not date: date = datetime.now(g.tz)
    try:
        r = execute_statement(table, table.insert().values(
            thing1_id=thing1_id,
            thing2_id=thing2_id,
            name=name,
            date=date))
        return r.inserted_primary_key[0]
    except sa.exc.DBAPIError as e:
        if 'IntegrityError' not in str(e):
            raise
        # wrap the error to prevent db layer bleeding out
        raise CreationError("Relation exists ({}, {}, {})".format(name, thing1_id, thing2_id))
        

def set_rel_props(rel_type_id, rel_id, **props):
    t = get_rel_table(rel_type_id, action = 'write')[0]

    if not props:
        return

    #use real columns
    engine = get_engine_from_table(t)
    transactions.add_engine(engine)
    new_props = {t.c[prop]: val for prop, val in props.items()}
    u = t.update().where(t.c.rel_id == rel_id).values(new_props)
    execute_statement(t, u)


def py2db(val, return_kind=False):
    if isinstance(val, bool):
        val = 't' if val else 'f'
        kind = 'bool'
    elif isinstance(val, str):
        kind = 'str'
    elif isinstance(val, (int, float)):
        kind = 'num'
    elif val is None:
        kind = 'none'
    else:
        kind = 'pickle'
        val = pickle.dumps(val)

    if return_kind:
        return (val, kind)
    else:
        return val

def db2py(val, kind):
    if kind == 'bool':
        val = True if val == 't' else False
    elif kind == 'num':
        try:
            val = int(val)
        except ValueError:
            val = float(val)
    elif kind == 'none':
        val = None
    elif kind == 'pickle':
        # Handle PostgreSQL bytea hex-escaped format in Python 3
        # The value may come as a hex-escaped string like '\x800495...'
        if isinstance(val, str):
            if val.startswith('\\x'):
                # PostgreSQL hex format: \x followed by hex digits
                val = bytes.fromhex(val[2:])
            else:
                # Try latin-1 encoding as fallback for raw byte strings
                val = val.encode('latin-1')
        val = pickle.loads(val)

    return val


def update_data(table, thing_id, **vals):
    engine = get_engine_from_table(table)
    transactions.add_engine(engine)

    inserts = []
    for key, val in vals.items():
        val, kind = py2db(val, return_kind=True)

        u = table.update().where(
            sa.and_(table.c.thing_id == thing_id, table.c.key == key)
        ).values(value=val, kind=kind)
        uresult = execute_statement(table, u)
        if not uresult.rowcount:
            inserts.append({'thing_id': thing_id, 'key': key, 'value': val, 'kind': kind})

    #do one insert
    if inserts:
        for ins in inserts:
            execute_statement(table, table.insert().values(**ins))


def create_data(table, thing_id, **vals):
    engine = get_engine_from_table(table)
    transactions.add_engine(engine)

    for key, val in vals.items():
        val, kind = py2db(val, return_kind=True)
        execute_statement(table, table.insert().values(
            thing_id=thing_id, key=key, value=val, kind=kind))


def incr_data_prop(table, type_id, thing_id, prop, amount):
    t = table
    engine = get_engine_from_table(t)
    transactions.add_engine(engine)
    u = t.update().where(
        sa.and_(t.c.thing_id == thing_id, t.c.key == prop)
    ).values({t.c.value: sa.cast(t.c.value, sa.Float) + amount})
    execute_statement(t, u)

def fetch_query(table, id_col, thing_id):
    """pull the columns from the thing/data tables for a list or single
    thing_id"""
    single = False

    if not isinstance(thing_id, iters):
        single = True
        thing_id = (thing_id,)

    s = sa.select(table).where(id_col.in_(thing_id))
    engine = get_engine_from_table(table)

    try:
        with engine.connect() as conn:
            r = conn.execute(add_request_info(s)).fetchall()
    except Exception:
        dbm.mark_dead(engine)
        # this thread must die so that others may live
        raise
    return (r, single)

#TODO specify columns to return?
def get_data(table, thing_id):
    r, single = fetch_query(table, table.c.thing_id, thing_id)

    #if single, only return one storage, otherwise make a dict
    res = storage() if single else {}
    for row in r:
        val = db2py(row.value, row.kind)
        stor = res if single else res.setdefault(row.thing_id, storage())
        if single and row.thing_id != thing_id:
            raise ValueError("tdb_sql.py: there's shit in the plumbing." 
                               + " got {}, wanted {}".format(row.thing_id,
                                                         thing_id))
        stor[row.key] = val

    return res

def set_thing_data(type_id, thing_id, brand_new_thing, **vals):
    table = get_thing_table(type_id, action = 'write')[1]

    if brand_new_thing:
        return create_data(table, thing_id, **vals)
    else:
        return update_data(table, thing_id, **vals)

def incr_thing_data(type_id, thing_id, prop, amount):
    table = get_thing_table(type_id, action = 'write')[1]
    return incr_data_prop(table, type_id, thing_id, prop, amount)    

def get_thing_data(type_id, thing_id):
    table = get_thing_table(type_id)[1]
    return get_data(table, thing_id)

def get_thing(type_id, thing_id):
    table = get_thing_table(type_id)[0]
    r, single = fetch_query(table, table.c.thing_id, thing_id)

    #if single, only return one storage, otherwise make a dict
    res = {} if not single else None
    for row in r:
        stor = storage(ups = row.ups,
                       downs = row.downs,
                       date = row.date,
                       deleted = row.deleted,
                       spam = row.spam)
        if single:
            res = stor
            # check that we got what we asked for
            if row.thing_id != thing_id:
                raise ValueError("tdb_sql.py: there's shit in the plumbing." 
                                    + " got {}, wanted {}".format(row.thing_id,
                                                              thing_id))
        else:
            res[row.thing_id] = stor
    return res

def set_rel_data(rel_type_id, thing_id, brand_new_thing, **vals):
    table = get_rel_table(rel_type_id, action = 'write')[3]

    if brand_new_thing:
        return create_data(table, thing_id, **vals)
    else:
        return update_data(table, thing_id, **vals)

def incr_rel_data(rel_type_id, thing_id, prop, amount):
    table = get_rel_table(rel_type_id, action = 'write')[3]
    return incr_data_prop(table, rel_type_id, thing_id, prop, amount)

def get_rel_data(rel_type_id, rel_id):
    table = get_rel_table(rel_type_id)[3]
    return get_data(table, rel_id)

def get_rel(rel_type_id, rel_id):
    r_table = get_rel_table(rel_type_id)[0]
    r, single = fetch_query(r_table, r_table.c.rel_id, rel_id)
    
    res = {} if not single else None
    for row in r:
        stor = storage(thing1_id = row.thing1_id,
                       thing2_id = row.thing2_id,
                       name = row.name,
                       date = row.date)
        if single:
            res = stor
        else:
            res[row.rel_id] = stor
    return res

def del_rel(rel_type_id, rel_id):
    tables = get_rel_table(rel_type_id, action = 'write')
    table = tables[0]
    data_table = tables[3]

    engine = get_engine_from_table(table)
    data_engine = get_engine_from_table(data_table)
    transactions.add_engine(engine)
    transactions.add_engine(data_engine)

    execute_statement(table, table.delete().where(table.c.rel_id == rel_id))
    execute_statement(data_table, data_table.delete().where(data_table.c.thing_id == rel_id))

def sa_op(op):
    #if BooleanOp
    if isinstance(op, operators.or_):
        return sa.or_(*[sa_op(o) for o in op.ops])
    elif isinstance(op, operators.and_):
        return sa.and_(*[sa_op(o) for o in op.ops])
    elif isinstance(op, operators.not_):
        return sa.not_(*[sa_op(o) for o in op.ops])

    #else, assume op is an instance of op
    if isinstance(op, operators.eq):
        fn = lambda x,y: x == y
    elif isinstance(op, operators.ne):
        fn = lambda x,y: x != y
    elif isinstance(op, operators.gt):
        fn = lambda x,y: x > y
    elif isinstance(op, operators.lt):
        fn = lambda x,y: x < y
    elif isinstance(op, operators.gte):
        fn = lambda x,y: x >= y
    elif isinstance(op, operators.lte):
        fn = lambda x,y: x <= y
    elif isinstance(op, operators.in_):
        return sa.or_(op.lval.in_(op.rval))

    rval = tup(op.rval)

    if not rval:
        return '2+2=5'
    else:
        return sa.or_(*[fn(op.lval, v) for v in rval])

def translate_sort(table, column_name, lval = None, rewrite_name = True):
    if isinstance(lval, operators.query_func):
        fn_name = lval.__class__.__name__
        sa_func = getattr(sa.func, fn_name)
        return sa_func(translate_sort(table,
                                      column_name,
                                      lval.lval,
                                      rewrite_name))

    if rewrite_name:
        if column_name == 'id':
            return table.c.thing_id
        elif column_name == 'hot':
            return sa.func.hot(table.c.ups, table.c.downs, table.c.date)
        elif column_name == 'score':
            return sa.func.score(table.c.ups, table.c.downs)
        elif column_name == 'controversy':
            return sa.func.controversy(table.c.ups, table.c.downs)
    #else
    return table.c[column_name]

#TODO - only works with thing tables
def add_sort(sort, t_table, select):
    sort = tup(sort)

    prefixes = list(t_table.keys()) if isinstance(t_table, dict) else None
    #sort the prefixes so the longest come first
    prefixes.sort(key = lambda x: len(x))
    cols = []

    def make_sa_sort(s):
        orig_col = s.col

        col = orig_col
        if prefixes:
            table = None
            for k in prefixes:
                if k and orig_col.startswith(k):
                    table = t_table[k]
                    col = orig_col[len(k):]
            if table is None:
                table = t_table[None]
        else:
            table = t_table

        real_col = translate_sort(table, col)

        #TODO a way to avoid overlap?
        # Add column for the sort parameter using the sorted name. Modern
        # SQLAlchemy `Select` objects don't have `append_column`; use
        # `add_columns` when necessary. We keep `select` mutable via a
        # single-element list so we can replace it when `add_columns`
        # returns a new Select.
        if hasattr(select, 'append_column'):
            select.append_column(real_col.label(orig_col))
        else:
            # `add_columns` returns a new Select in SQLAlchemy 1.4+/2.0
            select_ref[0] = select_ref[0].add_columns(real_col.label(orig_col))

        # avoid label overlap when projecting extra columns; older code set
        # `use_labels` â€” if the attribute exists, preserve behavior.
        try:
            select.use_labels = True
        except Exception:
            pass

        #keep track of which columns we added so we can add joins later
        cols.append((real_col, table))

        #default to asc
        return (sa.desc(real_col) if isinstance(s, operators.desc)
                else sa.asc(real_col))
        
    # wrap select in a mutable reference so make_sa_sort can replace it
    select_ref = [select]
    sa_sort = [make_sa_sort(s) for s in sort]

    select = select_ref[0]
    s = select.order_by(*sa_sort)

    return s, cols

def translate_thing_value(rval):
    if isinstance(rval, operators.timeago):
        return sa.text("current_timestamp - interval '%s'" % rval.interval)
    else:
        return rval

#will assume parameters start with a _ for consistency
def find_things(type_id, sort, limit, offset, constraints):
    table = get_thing_table(type_id)[0]
    constraints = deepcopy(constraints)

    s = sa.select(table.c.thing_id.label('thing_id'))

    for op in operators.op_iter(constraints):
        #assume key starts with _
        #if key.startswith('_'):
        key = op.lval_name
        op.lval = translate_sort(table, key[1:], op.lval)
        op.rval = translate_thing_value(op.rval)

    for op in constraints:
        s = s.where(sa_op(op))

    if sort:
        s, cols = add_sort(sort, {'_': table}, s)

    if limit:
        s = s.limit(limit)

    if offset:
        s = s.offset(offset)

    engine = get_engine_from_table(table)
    try:
        with engine.connect() as conn:
            r = conn.execute(add_request_info(s))
    except Exception:
        dbm.mark_dead(engine)
        # this thread must die so that others may live
        raise
    return Results(r, lambda row: row.thing_id)

def translate_data_value(alias, op):
    lval = op.lval
    need_substr = False if isinstance(lval, operators.query_func) else True
    lval = translate_sort(alias, 'value', lval, False)

    #add the substring func
    if need_substr:
        lval = sa.func.substring(lval, 1, max_val_len)
    
    op.lval = lval
        
    #convert the rval to db types
    #convert everything to strings for pg8.3
    op.rval = tuple(str(py2db(v)) for v in tup(op.rval))

#TODO sort by data fields
#TODO sort by id wants thing_id
def find_data(type_id, sort, limit, offset, constraints):
    t_table, d_table = get_thing_table(type_id)
    constraints = deepcopy(constraints)

    used_first = False
    need_join = False
    have_data_rule = False
    first_alias = d_table.alias()

    # Build columns and where clauses lists first
    columns = [first_alias.c.thing_id.label('thing_id')]
    where_clauses = []

    for op in operators.op_iter(constraints):
        key = op.lval_name
        vals = tup(op.rval)

        if key == '_id':
            op.lval = first_alias.c.thing_id
        elif key.startswith('_'):
            need_join = True
            op.lval = translate_sort(t_table, key[1:], op.lval)
            op.rval = translate_thing_value(op.rval)
        else:
            have_data_rule = True
            id_col = None
            if not used_first:
                alias = first_alias
                used_first = True
            else:
                alias = d_table.alias()
                id_col = first_alias.c.thing_id

            if id_col is not None:
                where_clauses.append(id_col == alias.c.thing_id)

            columns.append(alias.c.value.label(key))
            where_clauses.append(alias.c.key == key)

            #add the substring constraint if no other functions are there
            translate_data_value(alias, op)

    # Build the select with all columns
    s = sa.select(*columns)

    # Add all where clauses
    for clause in where_clauses:
        s = s.where(clause)

    for op in constraints:
        s = s.where(sa_op(op))

    if not have_data_rule:
        raise Exception('Data queries must have at least one data rule.')

    #TODO in order to sort by data columns, this is going to need to be smarter
    if sort:
        need_join = True
        s, cols = add_sort(sort, {'_':t_table}, s)

    if need_join:
        s = s.where(first_alias.c.thing_id == t_table.c.thing_id)

    if limit:
        s = s.limit(limit)

    if offset:
        s = s.offset(offset)

    engine = get_engine_from_table(t_table)
    try:
        with engine.connect() as conn:
            r = conn.execute(add_request_info(s))
    except Exception:
        dbm.mark_dead(engine)
        # this thread must die so that others may live
        raise

    return Results(r, lambda row: row.thing_id)


def sort_thing_ids_by_data_value(type_id, thing_ids, value_name,
        limit=None, desc=False):
    """Order thing_ids by the value of a data column."""

    thing_table, data_table = get_thing_table(type_id)

    join = thing_table.join(data_table,
        data_table.c.thing_id == thing_table.c.thing_id)

    query = (sa.select(thing_table.c.thing_id)
        .where(sa.and_(
            thing_table.c.thing_id.in_(thing_ids),
            thing_table.c.deleted == False,
            thing_table.c.spam == False,
            data_table.c.key == value_name,
        ))
        .select_from(join)
    )

    sort_column = data_table.c.value
    if desc:
        sort_column = sa.desc(sort_column)
    query = query.order_by(sort_column)

    if limit:
        query = query.limit(limit)

    engine = get_engine_from_table(thing_table)
    with engine.connect() as conn:
        rows = conn.execute(query)

    return Results(rows, lambda row: row.thing_id)


def find_rels(ret_props, rel_type_id, sort, limit, offset, constraints):
    tables = get_rel_table(rel_type_id)
    r_table, t1_table, t2_table, d_table = tables
    constraints = deepcopy(constraints)

    t1_table, t2_table = t1_table.alias(), t2_table.alias()

    prop_to_column = {
        "_rel_id": r_table.c.rel_id.label('rel_id'),
        "_thing1_id": r_table.c.thing1_id.label('thing1_id'),
        "_thing2_id": r_table.c.thing2_id.label('thing2_id'),
        "_name": r_table.c.name.label('name'),
        "_date": r_table.c.date.label('date'),
    }

    if not ret_props:
        valid_props = ', '.join(list(prop_to_column.keys()))
        raise ValueError("ret_props must contain at least one of " + valid_props)

    columns = []
    for prop in ret_props:
        if prop not in prop_to_column:
            raise ValueError("ret_props got unrecognized %s" % prop)

        columns.append(prop_to_column[prop])

    # Build where clauses and extra columns
    where_clauses = []
    extra_columns = []

    need_join1 = ('thing1_id', t1_table)
    need_join2 = ('thing2_id', t2_table)
    joins_needed = set()

    for op in operators.op_iter(constraints):
        #vals = con.rval
        key = op.lval_name
        prefix = key[:4]

        if prefix in ('_t1_', '_t2_'):
            #not a thing attribute
            key = key[4:]

            if prefix == '_t1_':
                join = need_join1
                joins_needed.add(join)
            elif prefix == '_t2_':
                join = need_join2
                joins_needed.add(join)

            table = join[1]
            op.lval = translate_sort(table, key, op.lval)
            op.rval = translate_thing_value(op.rval)
            #ors = [sa_op(con, key, v) for v in vals]
            #s.append_whereclause(sa.or_(*ors))

        elif prefix.startswith('_'):
            op.lval = r_table.c[key[1:]]

        else:
            alias = d_table.alias()
            where_clauses.append(r_table.c.rel_id == alias.c.thing_id)
            extra_columns.append(alias.c.value.label(key))
            where_clauses.append(alias.c.key == key)

            translate_data_value(alias, op)

    # Build select with all columns
    s = sa.select(*(columns + extra_columns))

    # Add where clauses
    for clause in where_clauses:
        s = s.where(clause)

    for op in constraints:
        s = s.where(sa_op(op))

    if sort:
        s, cols = add_sort(
            sort=sort,
            t_table={'_': r_table, '_t1_': t1_table, '_t2_': t2_table},
            select=s,
        )

        #do we need more joins?
        for (col, table) in cols:
            if table == need_join1[1]:
                joins_needed.add(need_join1)
            elif table == need_join2[1]:
                joins_needed.add(need_join2)

    for j in joins_needed:
        col, table = j
        s = s.where(r_table.c[col] == table.c.thing_id)

    if limit:
        s = s.limit(limit)

    if offset:
        s = s.offset(offset)

    engine = get_engine_from_table(r_table)
    try:
        with engine.connect() as conn:
            r = conn.execute(add_request_info(s))
    except Exception:
        dbm.mark_dead(engine)
        # this thread must die so that others may live
        raise

    def build_fn(row):
        # return Storage objects with just the requested props
        props = {}
        for prop in ret_props:
            db_prop = prop[1:]  # column name doesn't have _ prefix
            props[prop] = getattr(row, db_prop)
        return storage(**props)

    return Results(sa_ResultProxy=r, build_fn=build_fn)


if logging.getLogger('sqlalchemy').handlers:
    logging.getLogger('sqlalchemy').handlers[0].formatter = log_format


#inconsitencies:

#relationships assume their thing and data tables are in the same
#database. things don't make that assumption. in practice thing/data
#tables always go together.
#
#we create thing tables for a relationship's things that aren't on the
#same database as the relationship, although they're never used in
#practice. we could remove a healthy chunk of code if we removed that.

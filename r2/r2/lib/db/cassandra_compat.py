"""A minimal compatibility layer providing a subset of pycassa's
ConnectionPool and ColumnFamily APIs on top of the DataStax cassandra-driver.

This implements a simple storage model where each column family is stored
as a CQL table with schema:

  CREATE TABLE IF NOT EXISTS keyspace.cf_name (
      key text PRIMARY KEY,
      columns map<text, blob>
  )

Values are stored as pickled blobs. This is intentionally small and only
implements the operations used by the legacy code (multiget, get, insert,
remove, xget). It should be replaced with a proper CQL model in a full
refactor.
"""
from __future__ import annotations

import datetime
import logging
import pickle
import time
import uuid
from collections import OrderedDict
from typing import Dict, Iterable, Optional

from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement, BatchStatement, BatchType
from cassandra import InvalidRequest

log = logging.getLogger(__name__)

# Column and key type names, as pycassa had them (the models' _compare_with
# and schema arguments). Code compares against these, so there must be only
# one set: this one.
UTF8_TYPE = 'org.apache.cassandra.db.marshal.UTF8Type'
ASCII_TYPE = 'org.apache.cassandra.db.marshal.AsciiType'
TIME_UUID_TYPE = 'org.apache.cassandra.db.marshal.TimeUUIDType'
DATE_TYPE = 'org.apache.cassandra.db.marshal.DateType'
LONG_TYPE = 'org.apache.cassandra.db.marshal.LongType'
DOUBLE_TYPE = 'org.apache.cassandra.db.marshal.DoubleType'
FLOAT_TYPE = 'org.apache.cassandra.db.marshal.FloatType'
INT_TYPE = 'org.apache.cassandra.db.marshal.Int32Type'
COUNTER_COLUMN_TYPE = 'org.apache.cassandra.db.marshal.CounterColumnType'


# pycassa.types: column type classes some models declare their columns with
# (LongType() etc.). The storage here keeps column names as text, so these
# only mark the intended type.
class CassandraType:
    def __eq__(self, other):
        return type(self) is type(other)

    def __hash__(self):
        return hash(type(self))

    def __repr__(self):
        return "%s()" % type(self).__name__


class LongType(CassandraType):
    pass


class IntegerType(CassandraType):
    pass


class DateType(CassandraType):
    pass


class AsciiType(CassandraType):
    pass


class UTF8Type(CassandraType):
    pass


class CompositeType(CassandraType):
    """A column type made of several types, e.g. CompositeType(AsciiType(),
    AsciiType())."""
    def __init__(self, *types):
        self.types = types

    def __eq__(self, other):
        return isinstance(other, CompositeType) and self.types == other.types

    def __hash__(self):
        return hash((CompositeType, self.types))

    def __repr__(self):
        return "CompositeType(%s)" % ", ".join(map(repr, self.types))


def convert_uuid_to_time(uuid_obj):
    """Convert a UUID1 (or its string form) to a Unix timestamp, as
    pycassa.util.convert_uuid_to_time did.

    UUID1 timestamps are measured in 100-nanosecond intervals since
    October 15, 1582 (the date of Gregorian calendar reform).
    """
    if isinstance(uuid_obj, datetime.datetime):
        # pycassa turned datetime column names into TimeUUIDs; here they
        # are stored as they are (e.g. TryLater's scheduled times)
        return uuid_obj.timestamp()
    if not isinstance(uuid_obj, uuid.UUID):
        # column names come back from cassandra_compat as text: a UUID, or a
        # datetime written as a TimeUUID column name
        text = str(uuid_obj)
        try:
            uuid_obj = uuid.UUID(text)
        except ValueError:
            return datetime.datetime.fromisoformat(text).timestamp()
    # UUID1 timestamp is 100-nanosecond intervals since Oct 15, 1582
    # Unix epoch is Jan 1, 1970
    # Difference is 122192928000000000 (100-ns intervals)
    EPOCH_DIFF = 0x01b21dd213814000
    timestamp = (uuid_obj.time - EPOCH_DIFF) / 1e7
    return timestamp

def _stored_key(key):
    """Row keys are stored as text (inserts write str(key)), so look up UUID
    keys (UuidThing ids) by their string form too."""
    return str(key) if isinstance(key, uuid.UUID) else key


class NotFoundException(Exception):
    pass


class ConnectionPool:
    """Simple pool that holds a single Cluster and Session per keyspace.

    api: ConnectionPool(keyspace, server_list=[...], **kwargs)
    """
    def __init__(self, keyspace, server_list=None, **kwargs):
        self.keyspace = keyspace
        if not server_list:
            server_list = ["127.0.0.1"]
        # server_list items may be host:port
        self.server_list = server_list  # Store for compatibility
        hosts = [s.split(':', 1)[0] for s in server_list]
        self.cluster = Cluster(hosts)
        self.session = self.cluster.connect()
        try:
            self.session.set_keyspace(keyspace)
        except InvalidRequest:
            # keyspace may not exist yet; caller should create it
            pass


class SystemManager:
    """Minimal manager providing create_keyspace and create_column_family
    compatible with the expectations of the legacy code.
    """
    def __init__(self, host='127.0.0.1'):
        host_only = host.split(':', 1)[0]
        self.cluster = Cluster([host_only])
        self.session = self.cluster.connect()

    def create_keyspace(self, keyspace, strategy_options=None, replication_factor=1):
        # default to SimpleStrategy
        rf = replication_factor
        cql = "CREATE KEYSPACE IF NOT EXISTS %s WITH replication = {'class':'SimpleStrategy','replication_factor': '%d'};" % (keyspace, rf)
        self.session.execute(SimpleStatement(cql))

    def create_column_family(self, keyspace, cf_name, **kwargs):
        # create a simple table with a map<text, blob> to emulate thrift CF
        # normalize CF name to lowercase to match unquoted CQL identifiers
        cf_name_l = cf_name.lower()
        # allow callers to request a specific key type (e.g. timeuuid)
        key_validation = kwargs.get('key_validation_class') or kwargs.get('key_validation')
        if key_validation == TIME_UUID_TYPE:
            key_type = 'timeuuid'
        else:
            # default to text for most legacy CFs
            key_type = 'text'

        cql = (
            "CREATE TABLE IF NOT EXISTS %s.%s (\n"
            "  key %s PRIMARY KEY,\n"
            "  columns map<text, blob>\n"
            ")" % (keyspace, cf_name_l, key_type)
        )
        # ensure keyspace exists
        try:
            self.session.set_keyspace(keyspace)
        except Exception:
            # leave as is; creating table with fully qualified name
            pass
        self.session.execute(SimpleStatement(cql))


class ColumnFamily:
    """Minimal ColumnFamily API backed by a single map<text, blob> column.

    Methods implemented: multiget, multiget_slice (columns filter), get,
    insert, remove, xget.
    """
    def __init__(self, pool: ConnectionPool, name: str, **kwargs):
        self.pool = pool
        self.name = name
        self.keyspace = pool.keyspace
        # normalize table name to lowercase to avoid quoted/mixed-case
        # identifier mismatches with tables created via cqlsh
        self.table = name.lower()
        self.session = pool.session
        # Compatibility with pycassa - these are used by tdb_cassandra
        self.column_validators = {}
        self.default_validation_class = None  # Default column value type
        self.key_validation_class = None  # Key type
        # ensure table exists
        cql = (
            "CREATE TABLE IF NOT EXISTS %s.%s (\n"
            "  key text PRIMARY KEY,\n"
            "  columns map<text, blob>\n"
            ")" % (self.keyspace, self.table)
        )
        try:
            self.session.execute(SimpleStatement(cql))
        except Exception:
            # if keyspace doesn't exist, caller should create it first
            pass

    def _deserialize_map(self, raw_map: Dict[bytes, bytes]) -> OrderedDict:
        if not raw_map:
            return OrderedDict()
        od = OrderedDict()
        for k, v in raw_map.items():
            try:
                val = pickle.loads(v) if v is not None else None
            except Exception:
                val = v
            od[str(k)] = val
        return od

    @staticmethod
    def _strip_timestamps(od: OrderedDict) -> OrderedDict:
        """Values are written as (value, write timestamp); return just the
        values, as pycassa did without include_timestamp."""
        return OrderedDict(
            (k, v[0] if isinstance(v, tuple) and len(v) == 2
             and isinstance(v[1], int) else v)
            for k, v in od.items())

    def multiget(self, keys: Iterable[str], columns: Optional[Iterable[str]] = None,
                 column_count: Optional[int] = None, column_start: Optional[str] = None,
                 column_finish: Optional[str] = None, column_reversed: bool = False,
                 include_timestamp: bool = False):
        keys = list(keys)
        if not keys:
            return {}
        # keys are stored as text (insert() writes str(key)); results come
        # back under the keys the caller asked for, e.g. UUID objects
        requested = {_stored_key(k): k for k in keys}
        placeholders = ','.join(["%s"] * len(requested))
        cql = "SELECT key, columns FROM %s.%s WHERE key IN (%s)" % (self.keyspace, self.table, placeholders)
        rows = self.session.execute(cql, tuple(requested))
        ret = {}
        for row in rows:
            result_key = requested.get(str(row.key), str(row.key))
            raw = row.columns if hasattr(row, 'columns') else row[1]
            od = self._deserialize_map(raw)
            if columns is not None:
                od = OrderedDict((k, od[k]) for k in columns if k in od)

            # Handle column_start and column_finish filtering
            if column_start is not None or column_finish is not None:
                filtered = OrderedDict()
                for k, v in od.items():
                    # Convert to string for comparison
                    k_str = str(k) if not isinstance(k, str) else k
                    cs_str = str(column_start) if column_start is not None and not isinstance(column_start, str) else column_start
                    cf_str = str(column_finish) if column_finish is not None and not isinstance(column_finish, str) else column_finish

                    if column_start is not None and k_str < cs_str:
                        continue
                    if column_finish is not None and k_str > cf_str:
                        continue
                    filtered[k] = v
                od = filtered

            # Handle column_reversed
            if column_reversed:
                od = OrderedDict(reversed(list(od.items())))

            if column_count is not None and len(od) > column_count:
                # truncate (preserve insertion order)
                reduced = OrderedDict()
                for i, (k, v) in enumerate(od.items()):
                    if i >= column_count:
                        break
                    reduced[k] = v
                od = reduced
            if include_timestamp:
                # Legacy pycassa returned (value, timestamp) pairs per column
                # when include_timestamp=True. If we stored timestamps at
                # write-time, the deserialized value will be a tuple
                # (value, timestamp[, ttl]). Otherwise return None for
                # timestamp to preserve the API shape.
                od_ts = OrderedDict()
                for k, v in od.items():
                    if isinstance(v, tuple) and len(v) >= 2 and isinstance(v[1], (int, float)):
                        od_ts[k] = (v[0], v[1])
                    else:
                        od_ts[k] = (v, None)
                ret[result_key] = od_ts
            else:
                ret[result_key] = self._strip_timestamps(od)
        return ret

    def get_range(self, start: Optional[str] = None, row_count: Optional[int] = None):
        """Return an iterator of (key, columns) over rows in the table.

        This mirrors pycassa's `get_range` minimal usage in the legacy code.
        Parameters `start` and `row_count` are supported where `start`
        indicates the starting key (inclusive) and `row_count` limits the
        number of rows returned.
        """
        params = ()
        where = ''
        if start is not None:
            where = ' WHERE key >= %s'
            params = (start,)
        limit = ''
        if row_count is not None:
            limit = ' LIMIT %d' % int(row_count)

        cql = 'SELECT key, columns FROM %s.%s%s%s' % (self.keyspace, self.table, where, limit)
        rows = self.session.execute(cql, params)
        out = []
        for row in rows:
            raw = row.columns if hasattr(row, 'columns') else row[1]
            od = self._deserialize_map(raw)
            out.append((str(row.key), self._strip_timestamps(od)))
        return out

    def get(self, key: str, columns: Optional[Iterable[str]] = None,
            column_start: Optional[str] = None, column_finish: Optional[str] = None,
            column_reversed: bool = False, column_count: Optional[int] = None,
            include_timestamp: bool = False):
        """Fetch a single row and optionally filter/slice its columns.

        This mirrors the behaviour implemented in `multiget` so callers
        using pycassa-style kwargs like `column_reversed` or
        `include_timestamp` behave as expected.
        """
        cql = "SELECT columns FROM %s.%s WHERE key = %%s" % (self.keyspace, self.table)
        # pass key through as-is (text or UUID)
        params = (_stored_key(key),)
        row = self.session.execute(cql, params).one()
        if not row:
            raise NotFoundException()
        raw = row.columns if hasattr(row, 'columns') else row[0]
        od = self._deserialize_map(raw)

        # If a specific column list was requested, restrict to those keys
        if columns is not None:
            od = OrderedDict((k, od[k]) for k in columns if k in od)

        # Handle start/finish slicing
        if column_start is not None or column_finish is not None:
            filtered = OrderedDict()
            for k, v in od.items():
                k_str = str(k) if not isinstance(k, str) else k
                cs_str = str(column_start) if column_start is not None and not isinstance(column_start, str) else column_start
                cf_str = str(column_finish) if column_finish is not None and not isinstance(column_finish, str) else column_finish

                if column_start is not None and k_str < cs_str:
                    continue
                if column_finish is not None and k_str > cf_str:
                    continue
                filtered[k] = v
            od = filtered

        # Handle reversed ordering
        if column_reversed:
            od = OrderedDict(reversed(list(od.items())))

        # Truncate to column_count if requested
        if column_count is not None and len(od) > column_count:
            reduced = OrderedDict()
            for i, (k, v) in enumerate(od.items()):
                if i >= column_count:
                    break
                reduced[k] = v
            od = reduced

        if include_timestamp:
            od_ts = OrderedDict()
            for k, v in od.items():
                if isinstance(v, tuple) and len(v) >= 2 and isinstance(v[1], (int, float)):
                    od_ts[k] = (v[0], v[1])
                else:
                    od_ts[k] = (v, None)
            return od_ts

        return self._strip_timestamps(od)

    def insert(self, key: str, columns: Dict[str, object], ttl: Optional[int] = None):
        # Coerce key to str — UuidThing._id is a UUID object but the table key column is text.
        key = str(key)
        # serialize values and attach a write timestamp (microseconds)
        now_us = int(time.time() * 1e6)
        # Ensure map keys are text (CQL map<text, blob>)
        ser = {str(k): pickle.dumps((v, now_us)) for k, v in columns.items()}
        if ttl:
            cql = "UPDATE %s.%s USING TTL %d SET columns = columns + %%s WHERE key = %%s" % (self.keyspace, self.table, ttl)
        else:
            cql = "UPDATE %s.%s SET columns = columns + %%s WHERE key = %%s" % (self.keyspace, self.table)

        params = (ser, key)
        try:
            self.session.execute(cql, params)
        except Exception:
            log.exception("cassandra_compat: insert failed: %s", cql)
            raise

    def remove(self, key: str, columns: Optional[Iterable[str]] = None,
               timestamp: Optional[int] = None):
        """Delete a row, or some of its columns. With timestamp (pycassa's
        row delete "as of" a time), delete the columns written at or before
        that write timestamp, using the timestamps stored with each value.
        """
        key = _stored_key(key)
        if timestamp is not None and columns is None:
            try:
                row = self.get(key, include_timestamp=True)
            except NotFoundException:
                return
            columns = [name for name, (value, ts) in row.items()
                       if ts is not None and ts <= timestamp]
            if not columns:
                return
        if columns is None:
            cql = "DELETE FROM %s.%s WHERE key = %%s" % (self.keyspace, self.table)
            self.session.execute(cql, (key,))
        else:
            # remove specific entries from the map by setting them to null via delete
            for col in columns:
                cql = "DELETE columns[%%s] FROM %s.%s WHERE key = %%s" % (self.keyspace, self.table)
                # column names must be text; coerce column name to str, but keep row key type
                self.session.execute(cql, (str(col), key))

    def xget(self, key: str, column_start: Optional[str] = None,
             column_finish: Optional[str] = None,
             buffer_size: Optional[int] = None,
             include_timestamp: bool = False):
        """Iterate over a row's (column, value) pairs, like pycassa's xget.

        Yields nothing if the row does not exist. As in pycassa,
        column_start is inclusive and buffer_size only controls fetch
        batching (the whole row is fetched at once here), not how many
        columns are returned.
        """
        try:
            od = self.get(key, column_start=column_start,
                          column_finish=column_finish,
                          include_timestamp=include_timestamp)
        except NotFoundException:
            return
        yield from od.items()

    # convenience wrapper for older multiget usages with columns kw
    def multiget_slice(self, keys, columns=None):
        return self.multiget(keys, columns=columns)

    def get_count(self, key: str):
        od = self.get(key)
        return len(od)

    def batch(self, write_consistency_level=None):
        """Return a Mutator context manager to emulate pycassa's batch API.

        The legacy code expects `with cf.batch() as m:` to be available; provide
        a simple Mutator backed by the driver's session.
        """
        return Mutator(self.pool, default_cf=self)


class Mutator:
    """Batch mutator backed by DataStax driver's BatchStatement.

    This implements a small subset of the pycassa Mutator API used by r2:
    - context manager usage (`with Mutator(pool) as m:`)
    - `insert(key, columns, ttl=None)` when created with default_cf
    - `insert(cf, key, columns, ttl=None)` when cf is explicitly passed
    - `remove(cf, key, columns=None, timestamp=None)`
    - `send()` commits the batch

    The implementation translates the legacy map-based CF operations to CQL
    and executes them as a single BatchStatement against the session.
    """

    def __init__(self, pool_or_session, default_cf=None):
        # accept either a ConnectionPool or a Session
        if hasattr(pool_or_session, 'session'):
            self.session = pool_or_session.session
        else:
            self.session = pool_or_session
        self._ops = []
        self._default_cf = default_cf

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # Only send if the body of the with-block succeeded.  If the body
        # raised we skip the send (act like a rollback) and let the original
        # exception propagate.  Any exception raised by send() propagates
        # naturally — callers must see write failures.
        if exc_type is None:
            self.send()

    def insert(self, key_or_cf, columns_or_key, ttl_or_columns=None, ttl=None):
        # Handle both calling conventions:
        # 1. insert(key, columns, ttl=None) - when default_cf is set
        # 2. insert(cf, key, columns, ttl=None) - explicit cf
        if self._default_cf is not None and not isinstance(key_or_cf, ColumnFamily):
            # Called as insert(key, columns, ttl=None)
            cf = self._default_cf
            key = key_or_cf
            columns = columns_or_key
            if ttl is None and ttl_or_columns is not None and not isinstance(ttl_or_columns, dict):
                ttl = ttl_or_columns
            elif isinstance(ttl_or_columns, dict):
                columns = ttl_or_columns
        else:
            # Called as insert(cf, key, columns, ttl=None)
            cf = key_or_cf
            key = columns_or_key
            columns = ttl_or_columns if ttl_or_columns is not None else {}

        # columns expected to be a dict of name->value (already serialized by callers)
        # We'll serialize here using pickle to match ColumnFamily.insert behaviour
        # and attach a write timestamp (microseconds) so include_timestamp
        # consumers can see it.
        now_us = int(time.time() * 1e6)
        # ensure map keys are strings for CQL map<text, blob>
        ser = {str(k): pickle.dumps((v, now_us)) for k, v in columns.items()}
        # Coerce key to str — UuidThing._id is a UUID object but the table key column is text.
        key = str(key)
        if ttl:
            cql = "UPDATE %s.%s USING TTL %d SET columns = columns + %%s WHERE key = %%s" % (cf.keyspace, cf.table, int(ttl))
            params = (ser, key)
        else:
            cql = "UPDATE %s.%s SET columns = columns + %%s WHERE key = %%s" % (cf.keyspace, cf.table)
            params = (ser, key)
        self._ops.append(("insert", cql, params))

    def remove(self, cf, key, columns=None, timestamp=None):
        key = str(key)
        if columns is None:
            cql = "DELETE FROM %s.%s WHERE key = %%s" % (cf.keyspace, cf.table)
            params = (key,)
            self._ops.append(("delete_row", cql, params))
        else:
            # delete each map entry
            for col in columns:
                cql = "DELETE columns[%%s] FROM %s.%s WHERE key = %%s" % (cf.keyspace, cf.table)
                params = (str(col), key)
                self._ops.append(("delete_col", cql, params))

    def send(self):
        if not self._ops:
            return
        batch = BatchStatement(batch_type=BatchType.UNLOGGED)
        # add statements to the batch
        for kind, cql, params in self._ops:
            stmt = SimpleStatement(cql)
            batch.add(stmt, params)
        # execute the batch
        try:
            self.session.execute(batch)
        except Exception:
            log.exception("cassandra_compat: batch execute failed")
            raise
        self._ops = []

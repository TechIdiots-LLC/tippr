"""
Debug Cassandra schema and writes.
Run with: tippr-run /path/to/debug_cassandra_schema.py
"""
from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement
from cassandra import ConsistencyLevel

print("=" * 60)
print("DEBUG CASSANDRA SCHEMA")
print("=" * 60)

cluster = Cluster(['127.0.0.1'])
session = cluster.connect()

# Check keyspace
print("\n=== Keyspace Info ===")
rows = session.execute("SELECT * FROM system_schema.keyspaces WHERE keyspace_name = 'tippr'")
for row in rows:
    print(f"Keyspace: {row.keyspace_name}")
    print(f"Replication: {row.replication}")
    print(f"Durable writes: {row.durable_writes}")

session.set_keyspace('tippr')

# Check table schema
print("\n=== Table Schema for 'wikipage' ===")
rows = session.execute("""
    SELECT column_name, kind, type FROM system_schema.columns 
    WHERE keyspace_name = 'tippr' AND table_name = 'wikipage'
""")
for row in rows:
    print(f"  {row.column_name}: {row.type} ({row.kind})")

# Check all tables
print("\n=== All Tables in 'tippr' ===")
rows = session.execute("SELECT table_name FROM system_schema.tables WHERE keyspace_name = 'tippr'")
for row in rows:
    print(f"  {row.table_name}")

# Try insert with different consistency levels
print("\n=== Testing Writes ===")

# Test 1: Simple insert
print("\nTest 1: Simple INSERT")
try:
    session.execute("INSERT INTO wikipage (key, column1, value) VALUES ('test1', 'col1', 0x48454c4c4f)")
    print("  INSERT executed")
    rows = list(session.execute("SELECT * FROM wikipage WHERE key = 'test1'"))
    print(f"  Read back: {len(rows)} rows")
    for r in rows:
        print(f"    {r}")
except Exception as e:
    print(f"  ERROR: {e}")

# Test 2: With explicit consistency
print("\nTest 2: With ConsistencyLevel.ONE")
try:
    stmt = SimpleStatement(
        "INSERT INTO wikipage (key, column1, value) VALUES ('test2', 'col1', 0x48454c4c4f)",
        consistency_level=ConsistencyLevel.ONE
    )
    session.execute(stmt)
    print("  INSERT executed")
    
    stmt = SimpleStatement(
        "SELECT * FROM wikipage WHERE key = 'test2'",
        consistency_level=ConsistencyLevel.ONE
    )
    rows = list(session.execute(stmt))
    print(f"  Read back: {len(rows)} rows")
except Exception as e:
    print(f"  ERROR: {e}")

# Test 3: Check if the table is a map type
print("\nTest 3: Check table type")
try:
    rows = session.execute("DESCRIBE TABLE wikipage")
    for row in rows:
        print(f"  {row}")
except Exception as e:
    # DESCRIBE might not work, try another way
    rows = session.execute("""
        SELECT * FROM system_schema.columns 
        WHERE keyspace_name = 'tippr' AND table_name = 'wikipage'
    """)
    cols = list(rows)
    print(f"  Columns: {[(c.column_name, c.type, c.kind) for c in cols]}")

# Test 4: Try with the actual schema the app expects
print("\nTest 4: Check what schema the app expects")
try:
    from r2.lib.db import tdb_cassandra
    from r2.models.wiki import WikiPage
    
    print(f"  WikiPage._type_prefix: {getattr(WikiPage, '_type_prefix', 'NOT SET')}")
    print(f"  WikiPage._cf: {getattr(WikiPage, '_cf', 'NOT SET')}")
    print(f"  WikiPage._connection_pool: {getattr(WikiPage, '_connection_pool', 'NOT SET')}")
    
    # Check what column family it uses
    cf = getattr(WikiPage, '_cf', None)
    if cf:
        print(f"  CF type: {type(cf)}")
        print(f"  CF column_family: {getattr(cf, 'column_family', 'N/A')}")
except Exception as e:
    print(f"  ERROR: {e}")
    import traceback
    traceback.print_exc()

# Test 5: Count all rows
print("\n=== Current Row Counts ===")
for table in ['wikipage', 'wikirevision', 'permacache']:
    try:
        rows = list(session.execute(f"SELECT COUNT(*) FROM {table}"))
        print(f"  {table}: {rows[0].count} rows")
    except Exception as e:
        print(f"  {table}: ERROR - {e}")

print("\n" + "=" * 60)

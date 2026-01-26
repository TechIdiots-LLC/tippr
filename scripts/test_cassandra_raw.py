#!/usr/bin/env python3
"""
Test Cassandra directly WITHOUT tippr framework.
Run with: /home/tippr/venv/bin/python3 /path/to/test_cassandra_raw.py
"""
from cassandra.cluster import Cluster

print("=" * 60)
print("RAW CASSANDRA TEST (no tippr framework)")
print("=" * 60)

# Connect
print("\n1. Connecting to Cassandra...")
cluster = Cluster(['127.0.0.1'])
session = cluster.connect()
print("   Connected!")

# List keyspaces
print("\n2. Listing keyspaces...")
rows = session.execute("SELECT keyspace_name FROM system_schema.keyspaces")
keyspaces = [row.keyspace_name for row in rows]
print(f"   Found: {keyspaces}")

# Check tippr keyspace
if 'tippr' in keyspaces:
    print("\n3. 'tippr' keyspace exists, checking tables...")
    session.set_keyspace('tippr')
    
    rows = session.execute("SELECT table_name FROM system_schema.tables WHERE keyspace_name = 'tippr'")
    tables = [row.table_name for row in rows]
    print(f"   Tables: {tables}")
    
    # Check wikipage schema
    print("\n4. wikipage table schema:")
    rows = session.execute("""
        SELECT column_name, type, kind FROM system_schema.columns 
        WHERE keyspace_name = 'tippr' AND table_name = 'wikipage'
    """)
    for row in rows:
        print(f"   {row.column_name}: {row.type} ({row.kind})")
    
    # Test write
    print("\n5. Testing write to wikipage...")
    test_data = {'test_col': b'test_value'}
    session.execute(
        "UPDATE wikipage SET columns = columns + %s WHERE key = %s",
        (test_data, 'raw_test_key')
    )
    print("   Write executed!")
    
    # Test read
    print("\n6. Testing read from wikipage...")
    rows = session.execute("SELECT * FROM wikipage WHERE key = 'raw_test_key'")
    row = rows.one()
    if row:
        print(f"   SUCCESS! Row: key={row.key}, columns={row.columns}")
    else:
        print("   FAILURE: No row returned!")
    
    # List all rows
    print("\n7. All rows in wikipage:")
    rows = session.execute("SELECT key FROM wikipage")
    row_list = list(rows)
    print(f"   Count: {len(row_list)}")
    for r in row_list[:10]:
        print(f"   - {r.key}")
        
else:
    print("\n   ERROR: 'tippr' keyspace not found!")
    print("   Creating it now...")
    session.execute("""
        CREATE KEYSPACE IF NOT EXISTS tippr 
        WITH replication = {'class': 'SimpleStrategy', 'replication_factor': '1'}
    """)
    print("   Created! Please run this script again.")

print("\n" + "=" * 60)

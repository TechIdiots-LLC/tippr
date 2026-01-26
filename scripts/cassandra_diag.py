#!/usr/bin/env python3
"""
Ultra-basic Cassandra diagnostic.
Run with: /home/tippr/venv/bin/python3 /path/to/cassandra_diag.py
"""
import sys

print("=" * 60)
print("CASSANDRA DIAGNOSTIC")
print("=" * 60)

# Check cassandra-driver version
print("\n1. Cassandra driver info:")
try:
    import cassandra
    print(f"   cassandra-driver version: {cassandra.__version__}")
except Exception as e:
    print(f"   ERROR: {e}")

# Try to connect
print("\n2. Connecting...")
try:
    from cassandra.cluster import Cluster
    cluster = Cluster(['127.0.0.1'])
    print(f"   Cluster object: {cluster}")
    print(f"   Contact points: {cluster.contact_points}")
    
    session = cluster.connect()
    print(f"   Session: {session}")
    print(f"   Session keyspace: {session.keyspace}")
except Exception as e:
    print(f"   ERROR connecting: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Try raw CQL
print("\n3. Testing basic CQL...")
try:
    # This should always work
    result = session.execute("SELECT release_version FROM system.local")
    row = result.one()
    print(f"   Cassandra version: {row.release_version}")
except Exception as e:
    print(f"   ERROR: {e}")

# Try listing keyspaces from system.local
print("\n4. Querying system tables...")
try:
    # Try different approaches
    print("   a) system_schema.keyspaces:")
    rows = list(session.execute("SELECT keyspace_name FROM system_schema.keyspaces"))
    print(f"      Result: {[r.keyspace_name for r in rows]}")
    
    print("   b) system.peers:")
    rows = list(session.execute("SELECT peer FROM system.peers"))
    print(f"      Peers: {[str(r.peer) for r in rows]}")
    
    print("   c) system.local:")
    rows = list(session.execute("SELECT cluster_name, data_center FROM system.local"))
    for r in rows:
        print(f"      Cluster: {r.cluster_name}, DC: {r.data_center}")
        
except Exception as e:
    print(f"   ERROR: {e}")
    import traceback
    traceback.print_exc()

# Test if we can create/use keyspace
print("\n5. Testing keyspace operations...")
try:
    print("   Creating test keyspace...")
    session.execute("""
        CREATE KEYSPACE IF NOT EXISTS test_diag 
        WITH replication = {'class': 'SimpleStrategy', 'replication_factor': '1'}
    """)
    print("   Created!")
    
    print("   Setting keyspace...")
    session.set_keyspace('test_diag')
    print(f"   Current keyspace: {session.keyspace}")
    
    print("   Creating test table...")
    session.execute("CREATE TABLE IF NOT EXISTS test_tbl (id text PRIMARY KEY, val text)")
    print("   Created!")
    
    print("   Inserting data...")
    session.execute("INSERT INTO test_tbl (id, val) VALUES ('key1', 'value1')")
    print("   Inserted!")
    
    print("   Reading data...")
    rows = list(session.execute("SELECT * FROM test_tbl WHERE id = 'key1'"))
    if rows:
        print(f"   SUCCESS: {rows[0]}")
    else:
        print("   FAILURE: No data returned!")
        
    print("   Cleanup - dropping test keyspace...")
    session.execute("DROP KEYSPACE IF EXISTS test_diag")
    print("   Done!")
    
except Exception as e:
    print(f"   ERROR: {e}")
    import traceback
    traceback.print_exc()

# Check tippr keyspace specifically
print("\n6. Checking 'tippr' keyspace...")
try:
    session.execute("USE tippr")
    print("   Successfully switched to 'tippr' keyspace")
    
    rows = list(session.execute("SELECT table_name FROM system_schema.tables WHERE keyspace_name = 'tippr'"))
    print(f"   Tables in tippr: {[r.table_name for r in rows]}")
except Exception as e:
    print(f"   ERROR: {e}")

print("\n" + "=" * 60)

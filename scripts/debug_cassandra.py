"""
Debug script to directly test Cassandra read/write at the lowest level.
Run with: tippr-run scripts/debug_cassandra.py
"""
import sys

def main():
    try:
        from pylons import app_globals as g
        getattr(g, 'cassandra_local_cache')
    except (ImportError, AttributeError):
        print("\nERROR: Application environment not loaded.")
        print("Please run this script using: tippr-run scripts/debug_cassandra.py\n")
        sys.exit(1)

    from r2.lib.db.cassandra_compat import ColumnFamily, ConnectionPool, SystemManager
    import time

    print("=== Cassandra Direct Debug ===\n")

    # First, test raw Cassandra connection
    print("--- Test 0: Raw Cassandra Connection ---")
    try:
        from cassandra.cluster import Cluster
        cluster = Cluster(['127.0.0.1'])  # Default port 9042
        session = cluster.connect()
        print("  ✓ Connected to Cassandra cluster")
        
        # Check system keyspaces
        result = session.execute("SELECT keyspace_name FROM system_schema.keyspaces")
        keyspaces = [row.keyspace_name for row in result]
        print(f"  System keyspaces: {keyspaces}")
        
        # Create tippr keyspace if needed
        if 'tippr' not in keyspaces:
            print("  Creating 'tippr' keyspace...")
            session.execute("""
                CREATE KEYSPACE IF NOT EXISTS tippr 
                WITH replication = {'class': 'SimpleStrategy', 'replication_factor': '1'}
                AND durable_writes = true
            """)
            print("  ✓ Created 'tippr' keyspace")
        
        # Switch to tippr keyspace
        session.set_keyspace('tippr')
        print("  ✓ Switched to 'tippr' keyspace")
        
        # Create wikipage table
        session.execute("""
            CREATE TABLE IF NOT EXISTS wikipage (
                key text PRIMARY KEY,
                columns map<text, blob>
            )
        """)
        print("  ✓ Created/verified 'wikipage' table")
        
        cluster.shutdown()
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()

    # Get connection info
    pool = g.cassandra_pools['main']
    print(f"Keyspace: {pool.keyspace}")
    print(f"Server list: {pool.server_list}")

    # Test 1: Direct session query
    print("\n--- Test 1: Direct CQL Query ---")
    try:
        result = pool.session.execute("SELECT keyspace_name FROM system_schema.keyspaces")
        keyspaces = [row.keyspace_name for row in result]
        print(f"Available keyspaces: {keyspaces}")
        if 'tippr' in keyspaces:
            print("  ✓ 'tippr' keyspace exists")
        else:
            print("  ✗ 'tippr' keyspace NOT FOUND!")
    except Exception as e:
        print(f"  ERROR: {e}")

    # Test 2: Check tables in tippr keyspace
    print("\n--- Test 2: Tables in 'tippr' keyspace ---")
    try:
        result = pool.session.execute(
            "SELECT table_name FROM system_schema.tables WHERE keyspace_name = 'tippr'"
        )
        tables = [row.table_name for row in result]
        print(f"Tables: {tables}")
        if 'wikipage' in tables:
            print("  ✓ 'wikipage' table exists")
        else:
            print("  ✗ 'wikipage' table NOT FOUND!")
    except Exception as e:
        print(f"  ERROR: {e}")

    # Test 3: Direct write and read
    print("\n--- Test 3: Direct Write/Read Test ---")
    test_key = f"debug_test_{int(time.time())}"
    test_value = {"testcol": b"testvalue"}

    try:
        # Create test table if not exists
        pool.session.execute("""
            CREATE TABLE IF NOT EXISTS tippr.debug_test (
                key text PRIMARY KEY,
                columns map<text, blob>
            )
        """)
        print("  Created/verified debug_test table")

        # Write
        pool.session.execute(
            "UPDATE tippr.debug_test SET columns = columns + %s WHERE key = %s",
            (test_value, test_key)
        )
        print(f"  Wrote key: {test_key}")

        # Read back immediately
        result = pool.session.execute(
            "SELECT columns FROM tippr.debug_test WHERE key = %s",
            (test_key,)
        )
        row = result.one()
        if row and row.columns:
            print(f"  Read back: {row.columns}")
            print("  ✓ Immediate read works!")
        else:
            print("  ✗ Read returned no data!")
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()

    # Test 4: Check WikiPage table directly
    print("\n--- Test 4: WikiPage Table Contents ---")
    try:
        result = pool.session.execute("SELECT key, columns FROM tippr.wikipage LIMIT 10")
        rows = list(result)
        if rows:
            print(f"  Found {len(rows)} rows in wikipage:")
            for row in rows:
                print(f"    Key: {row.key}")
        else:
            print("  ✗ WikiPage table is EMPTY!")
    except Exception as e:
        print(f"  ERROR querying wikipage: {e}")

    # Test 5: Test via ColumnFamily wrapper
    print("\n--- Test 5: ColumnFamily Wrapper Test ---")
    try:
        cf = ColumnFamily(pool, 'debug_cf_test')
        test_key2 = f"cf_test_{int(time.time())}"
        cf.insert(test_key2, {'col1': 'value1'})
        print(f"  Inserted via ColumnFamily: {test_key2}")

        # Read back
        data = cf.get(test_key2)
        print(f"  Read back: {data}")
        print("  ✓ ColumnFamily wrapper works!")
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()

    print("\n=== Debug Complete ===")


if __name__ == '__main__':
    main()
else:
    main()

"""
Verify wiki pages are actually in Cassandra.
Run with: tippr-run /path/to/verify_wiki_cassandra.py
"""
from pylons import app_globals as g
from r2.models.wiki import WikiPage, PAGE_ID_SEP
from r2.models.vault import Frontpage
from r2.lib.db import tdb_cassandra

print("=" * 60)
print("VERIFY WIKI CASSANDRA")
print("=" * 60)

# Check Frontpage details
print(f"\nFrontpage._id36: '{Frontpage._id36}'")
print(f"Frontpage.name: '{Frontpage.name}'")
print(f"Frontpage.wikimode: {Frontpage.wikimode}")

# Check the wiki page names we expect
pages_to_check = ['useragreement', 'privacypolicy', 'contentpolicy', 'moderatorguidelines']

print(f"\n=== Checking Wiki Pages ===")

for page_name in pages_to_check:
    page_id = WikiPage.id_for(Frontpage, page_name)
    print(f"\nPage: {page_name}")
    print(f"  Expected ID: '{page_id}'")
    print(f"  ID repr: {repr(page_id)}")
    
    try:
        wp = WikiPage._byID(page_id)
        print(f"  FOUND: {wp}")
        print(f"    vault: {wp.vault}")
        print(f"    name: {wp.name}")
        print(f"    content length: {len(wp.content) if wp.content else 0}")
    except tdb_cassandra.NotFound:
        print(f"  NOT FOUND in Cassandra")

# Also try direct Cassandra query
print("\n=== Direct Cassandra Pool Check ===")
try:
    pool = g.cassandra_pools.get('main')
    if pool:
        print(f"Pool: {pool}")
        print(f"Pool type: {type(pool)}")
        
        # Try to get a column family
        from r2.lib.db.tdb_cassandra import THING_CLS
        print(f"\nRegistered Thing classes: {list(THING_CLS.keys())[:10]}...")
        
        # Check if WikiPage is registered
        if 'WikiPage' in THING_CLS:
            wp_cls = THING_CLS['WikiPage']
            print(f"WikiPage class: {wp_cls}")
            print(f"WikiPage._cf: {getattr(wp_cls, '_cf', 'NOT SET')}")
    else:
        print("WARNING: No 'main' pool found!")
        print(f"Available pools: {list(g.cassandra_pools.keys())}")
except Exception as e:
    print(f"Error checking pool: {e}")
    import traceback
    traceback.print_exc()

# Try raw cassandra-driver query
print("\n=== Raw Cassandra Query ===")
try:
    from cassandra.cluster import Cluster
    cluster = Cluster(['127.0.0.1'])
    session = cluster.connect()
    session.set_keyspace('tippr')
    
    # Check what's in the wikipage table
    rows = session.execute("SELECT key FROM wikipage LIMIT 10")
    row_list = list(rows)
    print(f"Keys in wikipage table: {len(row_list)} found")
    for row in row_list:
        print(f"  {repr(row.key)}")
    
    if not row_list:
        print("  (table is empty)")
    
    # Try to find our specific page
    page_id = WikiPage.id_for(Frontpage, 'useragreement')
    print(f"\nLooking for key: {repr(page_id)}")
    
    rows = session.execute("SELECT key, column1, value FROM wikipage WHERE key = %s", [page_id])
    row_list = list(rows)
    if row_list:
        print(f"Found {len(row_list)} columns:")
        for row in row_list:
            print(f"  column1={row.column1}, value_len={len(row.value) if row.value else 0}")
    else:
        print("  No rows found for this key")
    
    # Now let's try to WRITE directly and see if it persists
    print("\n=== Testing Direct Write ===")
    test_key = "test_direct_write"
    session.execute("INSERT INTO wikipage (key, column1, value) VALUES (%s, %s, %s)", 
                   [test_key, "test_col", b"test_value"])
    print(f"Wrote test row with key: {test_key}")
    
    # Read it back
    rows = session.execute("SELECT * FROM wikipage WHERE key = %s", [test_key])
    row_list = list(rows)
    if row_list:
        print(f"SUCCESS: Read back {len(row_list)} rows")
    else:
        print("FAILURE: Could not read back test row")
        
except Exception as e:
    print(f"Error with raw query: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)

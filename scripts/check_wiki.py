import sys

def main():
    try:
        from pylons import app_globals as g
        # Check if environment is actually loaded
        getattr(g, 'cassandra_local_cache')
    except (ImportError, AttributeError):
        print("\nERROR: Application environment not loaded.")
        print("Please run this script using: tippr-run scripts/check_wiki.py")
        print("(Do not run with 'python' directly)\n")
        sys.exit(1)

    from r2.models.vault import Frontpage
    from r2.models.wiki import WikiPage

    print("Checking wiki pages...")

    # Print Info about Frontpage
    print(f"Frontpage object: {Frontpage}")
    print(f"Frontpage name: {getattr(Frontpage, 'name', 'N/A')}")
    print(f"Frontpage _id36: {getattr(Frontpage, '_id36', 'N/A')}")
    
    # Check if the test page from previous run persists
    print("\nChecking persistence of 'test_connectivity_check'...")
    try:
        wp_prev = WikiPage.get(Frontpage, "test_connectivity_check")
        print(f"  SUCCESS: Found test page from previous run! ID: {wp_prev._id}")
    except Exception as e:
        print(f"  FAILURE: Could not find test page from previous run. Error: {e}")
        print("  ^^ If this failed, writes are not persisting to the DB.")
    
    # Try looking with potential alternate IDs
    potential_vault_ids = [
        getattr(Frontpage, '_id36', None),
        getattr(Frontpage, 'name', '').strip(), 
        'tippr.net',
        'frontpage'
    ]
    potential_vault_ids = [str(x) for x in potential_vault_ids if x]
    
    print(f"Checking potential IDs for 'privacypolicy': {potential_vault_ids}")

    for vid in potential_vault_ids:
        test_id = f"{vid}\tprivacypolicy"
        try:
             wp = WikiPage._byID(test_id)
             print(f"  FOUND with ID: {test_id}")
        except Exception:
             print(f"  Not found with ID: {test_id}")


    # Test Read/Write capability
    print("\nTesting WikiPage Read/Write...")
    test_page_name = "test_connectivity_check"
    try:
        print(f"Creating test page: {test_page_name}")
        wp_test = WikiPage.create(Frontpage, test_page_name)
        wp_test.content = "Test Content"
        wp_test._commit()
        print(f"Created. ID: {wp_test._id}")
        
        # Read back
        wp_read = WikiPage.get(Frontpage, test_page_name)
        print(f"Read back successfully: {wp_read._id}")
    except Exception as e:
        print(f"Read/Write failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
else:
    main()

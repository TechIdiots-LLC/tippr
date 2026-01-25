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
    for name in ['privacypolicy', 'useragreement']:
        print(f"Looking for '{name}' on Frontpage...")
        try:
            # First, check what ID is generated
            generated_id = WikiPage.id_for(Frontpage, name)
            print(f"  Expected ID: {generated_id}")
            
            wp = WikiPage.get(Frontpage, name)
            print(f"  FOUND: {wp._id}")
            print(f"  Content length: {len(wp.content)}")
        except Exception as e:
            print(f"  NOT FOUND or Error: {e}")

if __name__ == '__main__':
    main()
else:
    main()

import sys
import os
from paste.deploy import loadapp

def main():
    # Setup paths
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    r2_dir = os.path.join(root_dir, 'r2')
    sys.path.insert(0, root_dir)
    sys.path.insert(0, r2_dir)

    ini_path = os.path.join(r2_dir, 'example.ini')
    app_spec = 'config:' + os.path.basename(ini_path)
    
    print(f"Loading app from {ini_path}...")
    try:
        loadapp(app_spec, relative_to=os.path.dirname(ini_path))
    except Exception as e:
        print(f"Failed to load app: {e}")
        return

    from pylons import app_globals as g
    from r2.models.vault import Vault, Frontpage
    
    # First, enable wiki on the Frontpage's base vault (g.default_vault)
    # The Frontpage singleton delegates wikimode to this vault
    print("\n=== Enabling Wiki for Frontpage ===")
    
    default_vault_name = getattr(g, 'default_vault', None) or getattr(g, 'default_sr', None)
    print(f"Frontpage base vault name from config: {default_vault_name}")
    
    if default_vault_name:
        try:
            base_vault = Vault._by_name(default_vault_name, stale=False)
            print(f"  Found base vault '{default_vault_name}' (id: {base_vault._id})")
            print(f"  Current wikimode: {base_vault.wikimode}")
            
            if base_vault.wikimode == 'disabled':
                base_vault.wikimode = 'modonly'
                base_vault._commit()
                print(f"  SUCCESS: Updated wikimode to 'modonly'")
            else:
                print(f"  Info: Wiki already enabled (mode: {base_vault.wikimode})")
                
            # Verify through Frontpage
            print(f"  Frontpage.wikimode now reports: {Frontpage.wikimode}")
            
        except Exception as e:
            print(f"  ERROR: Could not access base vault '{default_vault_name}': {e}")
            print(f"  Attempting to create it...")
            
            # If the vault doesn't exist, we need to create it
            try:
                from r2.models.account import Account
                admin = Account._by_name('tippr')
                
                base_vault = Vault._new(
                    name=default_vault_name,
                    title=f"{default_vault_name} frontpage",
                    author_id=admin._id,
                    type='public',
                    lang='en',
                    ip='127.0.0.1',
                    over_18=False,
                )
                base_vault.wikimode = 'modonly'
                base_vault._commit()
                print(f"  SUCCESS: Created vault '{default_vault_name}' with wikimode='modonly'")
            except Exception as create_err:
                print(f"  ERROR creating vault: {create_err}")
    else:
        print("  ERROR: No default_vault configured in g!")
    
    # Also check some other common vaults that might need wiki enabled
    print("\n=== Checking Additional Vaults ===")
    additional_vaults = ['frontpage', 'tippr', 'beta']
    
    for name in additional_vaults:
        try:
            v = Vault._by_name(name, stale=False)
            print(f"Vault '{name}': wikimode={v.wikimode}")
            
            if v.wikimode == 'disabled':
                v.wikimode = 'modonly'
                v._commit()
                print(f"  -> Updated to 'modonly'")
                
        except Exception as e:
            print(f"Vault '{name}': not found or error ({e})")
    
    print("\n=== Done ===")
    print("Remember to restart the tippr service after running this script!")

if __name__ == '__main__':
    main()

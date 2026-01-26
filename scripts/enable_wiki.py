"""
Enable wiki on the Frontpage vault so /help/* policy pages work.
Run with: tippr-run /path/to/enable_wiki.py
"""
from pylons import app_globals as g
from r2.models.vault import Vault, Frontpage

print("=" * 60)
print("ENABLE WIKI SCRIPT")
print("=" * 60)

# First, enable wiki on the Frontpage's base vault (g.default_vault)
# The Frontpage singleton delegates wikimode to this vault
print("\n=== Enabling Wiki for Frontpage ===")

default_vault_name = getattr(g, 'default_vault', None) or getattr(g, 'default_sr', None)
print(f"Frontpage base vault name from config: {default_vault_name}")
print(f"Current Frontpage.wikimode: {Frontpage.wikimode}")
print(f"Frontpage._base: {Frontpage._base}")

if Frontpage._base:
    base_vault = Frontpage._base
    print(f"  Found base vault: {base_vault.name} (id: {base_vault._id})")
    print(f"  Current wikimode: {base_vault.wikimode}")
    
    if base_vault.wikimode == 'disabled':
        base_vault.wikimode = 'modonly'
        base_vault._commit()
        print(f"  SUCCESS: Updated wikimode to 'modonly'")
    else:
        print(f"  Info: Wiki already enabled (mode: {base_vault.wikimode})")
        
    # Verify through Frontpage - need to reload
    print(f"  Frontpage.wikimode now reports: {Frontpage.wikimode}")
    
elif default_vault_name:
    print(f"  Frontpage._base is None, trying to find vault by name...")
    try:
        base_vault = Vault._by_name(default_vault_name, stale=False)
        print(f"  Found vault '{default_vault_name}' (id: {base_vault._id})")
        print(f"  Current wikimode: {base_vault.wikimode}")
        
        if base_vault.wikimode == 'disabled':
            base_vault.wikimode = 'modonly'
            base_vault._commit()
            print(f"  SUCCESS: Updated wikimode to 'modonly'")
        else:
            print(f"  Info: Wiki already enabled (mode: {base_vault.wikimode})")
            
    except Exception as e:
        print(f"  ERROR: Could not access vault '{default_vault_name}': {e}")
        print(f"  The vault may need to be created first.")
        
        # Try to create it
        print(f"  Attempting to create vault '{default_vault_name}'...")
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
    print("  ERROR: No default_vault configured and Frontpage._base is None!")

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
        print(f"Vault '{name}': not found ({type(e).__name__})")

print("\n" + "=" * 60)
print("DONE - Remember to run: tippr-restart")
print("=" * 60)

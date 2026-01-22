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
    from r2.models.vault import Vault
    
    # Try multiple common default vault names if g.default_sr is not what we expect
    candidates = []
    if hasattr(g, 'default_sr') and g.default_sr:
        candidates.append(g.default_sr)
    candidates.extend(['tippr', 'reddit', 'all'])
    
    # Deduplicate
    candidates = list(dict.fromkeys(candidates))
    
    print(f"Checking vaults: {candidates}")
    
    for name in candidates:
        try:
            print(f"Checking vault: {name}")
            v = Vault._by_name(name)
            print(f"  Found '{name}'. Current wikimode: {v.wikimode}")
            
            if v.wikimode == 'disabled':
                # Enable it - set to 'modonly' so it's visible but not publicly editable by default
                v.wikimode = 'modonly'
                v._commit()
                print(f"  SUCCESS: Updated '{name}' wikimode to: {v.wikimode}")
            else:
                print(f"  Info: '{name}' wiki is already enabled (mode: {v.wikimode})")
                
        except Exception as e:
            # NotFound or similar
            print(f"  Could not access vault '{name}': {e}")

if __name__ == '__main__':
    main()

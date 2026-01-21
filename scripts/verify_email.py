import sys
import os

# Add the project root to sys.path so we prefer local packages (like baseplate shim)
root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root_path)

# Add the r2 directory to sys.path
r2_path = os.path.join(root_path, 'r2')
sys.path.insert(0, r2_path)

from paste.deploy import appconfig
from r2.config.environment import load_environment

def bootstrap():
    # Load configuration and environment
    conf_path = os.path.join(r2_path, 'example.ini')
    if not os.path.exists(conf_path):
        # Fallback for production or where example.ini is not used
        conf_path = os.path.join(r2_path, 'development.ini')
    
    # Check if run.ini exists (often used in production/docker)
    run_ini = os.path.join(r2_path, 'run.ini')
    if os.path.exists(run_ini):
        conf_path = run_ini

    print(f"Loading environment from {conf_path}...")
    conf = appconfig(f'config:{conf_path}')
    load_environment(conf.global_conf, conf.local_conf)

def verify_user(username):
    bootstrap()
    
    # Import models AFTER bootstrap
    from r2.models import Account, NotFound
    from pylons import app_globals as g

    print(f"Looking up user '{username}'...")

    try:
        user = Account._by_name(username)
        print(f"Found user: {user.name}")
        print(f"Current status - Email: {user.email}, Verified: {user.email_verified}")

        if user.email_verified:
            print(f"User '{username}' is already verified.")
        else:
            print(f"Verifying email for user '{username}'...")
            user.email_verified = True
            user._commit()
            print("Success! Email marked as verified.")
            # Clear cache to ensure immediate effect
            Account._cache.delete(user._id)
            
    except NotFound:
        print(f"User '{username}' not found.")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    if len(sys.argv) > 1:
        username = sys.argv[1]
    else:
        username = 'tippr' # Default based on your screenshot
    
    verify_user(username)

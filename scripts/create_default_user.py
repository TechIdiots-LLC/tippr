
from r2.models import Account, register, NotFound
from pylons import app_globals as g

username = "tippr"
password = "password"

print(f"Ensuring user '{username}' exists...")

try:
    user = Account._by_name(username)
    print(f"User '{username}' already exists.")
except NotFound:
    print(f"Creating user '{username}' with password '{password}'...")
    try:
        # Register the user with a local IP
        user = register(username, password, "127.0.0.1")
        
        # Ensure changes are committed
        user._commit()
        print(f"SUCCESS: User '{username}' created.")
    except Exception as e:
        print(f"ERROR: Failed to create user: {e}")

# The contents of this file are subject to the Common Public Attribution
# License Version 1.0 (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# https://github.com/TechIdiots-LLC/tippr/blob/master/LICENSE.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is Tippr.
#
# The Initial Developer of the Original Code is TechIdiots LLC.
# Copyright (c) 2026 TechIdiots LLC. All Rights Reserved.
###############################################################################

"""Create the site's first admin account.

The name and password come from TIPPR_ADMIN_USER (default "tippr") and
TIPPR_ADMIN_PASSWORD, which install/tippr.sh generates once per install.
An existing account's password is only changed when
TIPPR_ADMIN_PASSWORD_RESET=1 is set.
"""

import os

from r2.models import Account, NotFound, change_password, register

username = os.environ.get("TIPPR_ADMIN_USER", "tippr")
password = os.environ.get("TIPPR_ADMIN_PASSWORD")
reset = os.environ.get("TIPPR_ADMIN_PASSWORD_RESET") == "1"

if not password:
    raise SystemExit("TIPPR_ADMIN_PASSWORD is not set; not creating an admin account.")

try:
    user = Account._by_name(username)
except NotFound:
    user = register(username, password, "127.0.0.1")
    user._commit()
    print(f"Created admin account '{username}'.")
else:
    if reset:
        change_password(user, password)
        print(f"Reset the password of admin account '{username}'.")
    else:
        print(f"Admin account '{username}' already exists; password unchanged.")

#!/bin/bash
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0. (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://code.reddit.com/LICENSE. The License is based on the Mozilla Public
# License Version 1.1, but Sections 14 and 15 have been added to cover use of
# software over a computer network and provide for limited attribution for the
# Original Developer. In addition, Exhibit A has been modified to be consistent
# with Exhibit B.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is reddit.
#
# The Original Developer is the Initial Developer.  The Initial Developer of
# the Original Code is reddit Inc.
#
# All portions of the code written by reddit are Copyright (c) 2006-2015 reddit
# Inc. All Rights Reserved.
# 
# Portions created by TechIdiots LLC (Tippr) are Copyright (c) 2026
# TechIdiots LLC. All Rights Reserved.
###############################################################################

###############################################################################
# Configure Cassandra
###############################################################################

# load configuration
RUNDIR=$(dirname $0)
source $RUNDIR/install.cfg

source /etc/lsb-release

if [ "$DISTRIB_RELEASE" == "24.04" ]; then
    ###########################################################################
    # Ubuntu 24.04 - Use cqlsh (installed via apt with Cassandra)
    ###########################################################################

    # Verify Cassandra is actually accepting connections before running setup.
    # If this fails the keyspace will be silently missing and the app will 404.
    echo "Verifying Cassandra CQL port is open before running setup..."
    if ! nc -z localhost 9042 2>/dev/null; then
        echo "ERROR: Cassandra is not listening on port 9042 — cannot set up schema." >&2
        echo "Start Cassandra first, wait for it to be ready, then re-run setup_cassandra.sh" >&2
        exit 1
    fi

    # Use the venv's cassandra-driver directly — system cqlsh uses system Python
    # and cannot find packages installed in the venv (including six and its
    # six.moves virtual module which the bundled system cassandra driver needs).
    echo "Creating tippr keyspace and permacache table via venv cassandra-driver..."
    sudo -u $TIPPR_USER $TIPPR_VENV/bin/python - <<'PYEOF'
from cassandra.cluster import Cluster
cluster = Cluster(['127.0.0.1'])
session = cluster.connect()
session.execute("""
    CREATE KEYSPACE IF NOT EXISTS tippr
    WITH replication = {'class': 'SimpleStrategy', 'replication_factor': '1'}
""")
session.execute("""
    CREATE TABLE IF NOT EXISTS tippr.permacache (
        key text PRIMARY KEY,
        value blob
    )
""")
print("Cassandra keyspace and permacache table ready.")
cluster.shutdown()
PYEOF
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to set up Cassandra schema." >&2
        exit 1
    fi

    echo "Cassandra keyspace and tables created."

else
    ###########################################################################
    # Ubuntu 14.04 - Use pycassa (Python 2)
    ###########################################################################

    # update the per-thread stack size. this used to be set to 256k in cassandra
    # version 1.2.19, but we recently downgraded to 1.2.11 where it's set too low
    sed -i -e 's/-Xss180k/-Xss256k/g' /etc/cassandra/cassandra-env.sh

    python <<END
import pycassa
sys = pycassa.SystemManager("localhost:9160")

if "tippr" not in sys.list_keyspaces():
    print "creating keyspace 'tippr'"
    sys.create_keyspace("tippr", "SimpleStrategy", {"replication_factor": "1"})
    print "done"

if "permacache" not in sys.get_keyspace_column_families("tippr"):
    print "creating column family 'permacache'"
    sys.create_column_family("tippr", "permacache")
    print "done"
END

fi

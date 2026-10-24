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

    # Where clients connect (CQL, 9042): this server only, or on a backend
    # (TIPPR_ROLE=backend, docs/SERVERS.md) every address, so its frontends
    # can, telling them TIPPR_BACKEND_LISTEN. Cassandra has no password
    # here: the firewall keeps it to the frontends (TIPPR_FRONTEND_ALLOW).
    CASSANDRA_YAML=/etc/cassandra/cassandra.yaml
    if [ -f "$CASSANDRA_YAML" ]; then
        if [ "$TIPPR_ROLE" = "backend" ]; then
            rpc_address=0.0.0.0
            broadcast="broadcast_rpc_address: $TIPPR_BACKEND_LISTEN"
        else
            rpc_address=localhost
            broadcast=""
        fi
        yaml_before=$(md5sum < "$CASSANDRA_YAML")
        sed -i -E "s/^rpc_address:.*/rpc_address: $rpc_address/" "$CASSANDRA_YAML"
        sed -i -E '/^broadcast_rpc_address:/d' "$CASSANDRA_YAML"
        [ -n "$broadcast" ] && echo "$broadcast" >> "$CASSANDRA_YAML"
        if [ "$(md5sum < "$CASSANDRA_YAML")" != "$yaml_before" ]; then
            echo "Cassandra: clients on $rpc_address; restarting"
            systemctl restart cassandra
            for i in $(seq 1 120); do
                nc -z localhost 9042 2>/dev/null && break
                sleep 2
            done
        fi
    fi

    # Verify Cassandra is actually accepting connections before running setup.
    # If this fails the keyspace will be silently missing and the app will 404.
    echo "Verifying Cassandra CQL port is open before running setup..."
    if ! nc -z localhost 9042 2>/dev/null; then
        echo "ERROR: Cassandra is not listening on port 9042 — cannot set up schema." >&2
        echo "Start Cassandra first, wait for it to be ready, then re-run setup_cassandra.sh" >&2
        exit 1
    fi

    # Use system Python with a freshly pip-installed cassandra-driver.
    # We cannot use the tippr venv here because it has not been created yet
    # (setup_cassandra.sh runs before the venv creation step in tippr.sh).
    # System cqlsh bundles its own driver zip that requires six.moves but can't
    # find it reliably, so we bypass cqlsh entirely.
    pip3 install --quiet cassandra-driver 2>/dev/null || true

    echo "Creating tippr keyspace and permacache table via system cassandra-driver..."
    python3 - <<'PYEOF'
from cassandra.cluster import Cluster
cluster = Cluster(['127.0.0.1'])
session = cluster.connect()
session.execute("""
    CREATE KEYSPACE IF NOT EXISTS tippr
    WITH replication = {'class': 'SimpleStrategy', 'replication_factor': '1'}
""")
# Same layout as every table r2's cassandra_compat creates.
session.execute("""
    CREATE TABLE IF NOT EXISTS tippr.permacache (
        key text PRIMARY KEY,
        columns map<text, blob>
    )
""")
# Earlier installs created permacache with a "value" column, which
# cassandra_compat never reads; reading it failed ("Undefined column name
# columns"), which broke submitting posts.
permacache = cluster.metadata.keyspaces["tippr"].tables["permacache"]
if "columns" not in permacache.columns:
    session.execute("ALTER TABLE tippr.permacache ADD columns map<text, blob>")
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

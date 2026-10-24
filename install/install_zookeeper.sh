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
# All portions of the code written by reddit are Copyright (c) 2006-2016 reddit
# Inc. All Rights Reserved.
# 
# Portions created by TechIdiots LLC (Tippr) are Copyright (c) 2026
# TechIdiots LLC. All Rights Reserved.
###############################################################################

RUNDIR=$(dirname $0)
source $RUNDIR/install.cfg

sudo apt-get install $APTITUDE_OPTIONS zookeeperd

echo "Waiting for ZooKeeper to be available..."
while ! nc -vz localhost 2181; do
    sleep 1
done

# Ubuntu's zookeeperd ships dataDir=/tmp/zookeeper, which is cleared on
# reboot. Keep the data in /var/lib/zookeeper (moving any existing data), and
# only listen on localhost: r2 is the only client.
ZOO_CFG=/etc/zookeeper/conf/zoo.cfg
ZOO_DATA=/var/lib/zookeeper
if [ -f "$ZOO_CFG" ]; then
    restart_zookeeper=0
    # The package ships a placeholder myid ("replace this text with ..."),
    # which ZooKeeper rejects as an invalid config once dataDir points at
    # /var/lib/zookeeper (whose myid links to it). Use 1 for a single server.
    if ! grep -qE "^[0-9]+$" /etc/zookeeper/conf/myid 2>/dev/null; then
        echo 1 > /etc/zookeeper/conf/myid
        restart_zookeeper=1
    fi
    if grep -q '^dataDir=/tmp/zookeeper' "$ZOO_CFG"; then
        systemctl stop zookeeper || true
        if [ -d /tmp/zookeeper/version-2 ] && [ ! -d "$ZOO_DATA/version-2" ]; then
            cp -a /tmp/zookeeper/version-2 "$ZOO_DATA/"
            chown -R zookeeper:zookeeper "$ZOO_DATA/version-2"
        fi
        sed -i "s#^dataDir=.*#dataDir=$ZOO_DATA#" "$ZOO_CFG"
        restart_zookeeper=1
    fi
    # a backend (TIPPR_ROLE=backend, docs/SERVERS.md): every address, for
    # its frontends (r2's nodes need its password; the firewall keeps the
    # rest to them)
    if [ "$TIPPR_ROLE" = "backend" ]; then
        zk_address=0.0.0.0
    else
        zk_address=127.0.0.1
    fi
    if ! grep -qx "clientPortAddress=$zk_address" "$ZOO_CFG"; then
        sed -i '/^clientPortAddress=/d' "$ZOO_CFG"
        echo "clientPortAddress=$zk_address" >> "$ZOO_CFG"
        restart_zookeeper=1
    fi
    if [ "$restart_zookeeper" = "1" ]; then
        systemctl restart zookeeper
        while ! nc -z localhost 2181; do
            sleep 1
        done
    fi
fi

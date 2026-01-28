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

# load configuration
RUNDIR=$(dirname $0)
source $RUNDIR/install.cfg

source /etc/lsb-release

if [ "$DISTRIB_RELEASE" == "24.04" ]; then
    ###########################################################################
    # Ubuntu 24.04 - Install Cassandra 4.1.x from Apache repository
    ###########################################################################

    # Install Java 11 (required for Cassandra)
    apt-get install $APTITUDE_OPTIONS openjdk-11-jdk

    # Add Apache Cassandra 4.1.x repository if not already present
    if ! grep -q "debian.cassandra.apache.org" /etc/apt/sources.list.d/cassandra.sources.list 2>/dev/null; then
        echo "deb https://debian.cassandra.apache.org 41x main" | sudo tee /etc/apt/sources.list.d/cassandra.sources.list
    fi

    # Import Cassandra GPG key
    curl https://downloads.apache.org/cassandra/KEYS | sudo apt-key add -

    # Install Cassandra
    apt-get update
    apt-get install $APTITUDE_OPTIONS cassandra

    # Enable and start Cassandra
    sudo systemctl enable cassandra
    sudo systemctl start cassandra

    # Wait for Cassandra to be available (CQL native port 9042)
    echo "Waiting for Cassandra to be available..."
    for i in $(seq 1 60); do
        if nc -vz localhost 9042 2>/dev/null; then
            echo "Cassandra is up!"
            break
        fi
        sleep 2
    done

    # Ensure a usable cqlsh is available. Some distros/package choices ship
    # cqlsh with the Cassandra package, others require installing the CLI via
    # pip. Prefer a system `cqlsh` if present; otherwise install the pypi
    # `cqlsh` package so scripts like import_policy_cqlsh.py work reliably.
    if ! command -v cqlsh >/dev/null 2>&1; then
        echo "cqlsh not found on PATH; installing via pip3..."
        python3 -m pip install --upgrade pip setuptools wheel
        python3 -m pip install cqlsh || true
        if command -v cqlsh >/dev/null 2>&1; then
            echo "Installed cqlsh"
        else
            echo "Warning: failed to install system cqlsh; snap-based cqlsh may still work."
        fi
    else
        echo "cqlsh found: $(command -v cqlsh)"
    fi

else
    ###########################################################################
    # Ubuntu 14.04 - Legacy Cassandra 1.2.x installation
    ###########################################################################

    if [ ! -e $CASSANDRA_SOURCES_LIST ]; then
        echo "Cassandra repo not added.  Running install_apt.sh"
        $RUNDIR/install_apt.sh
    fi

    # install cassandra
    sudo apt-get install $APTITUDE_OPTIONS cassandra=1.2.19

    # we don't want to upgrade to C* 2.0 yet, so we'll put it on hold
    apt-mark hold cassandra || true

    # cassandra doesn't auto-start after install
    sudo service cassandra start

    # check each port for connectivity (Thrift port 9160)
    echo "Waiting for cassandra to be available..."
    while ! nc -vz localhost 9160; do
        sleep 1
    done
fi

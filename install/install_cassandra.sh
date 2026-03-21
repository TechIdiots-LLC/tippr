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

    # Install Java 11 (required for Cassandra 4.1 — Java 21 removed JVM flags
    # like UseBiasedLocking that Cassandra's cassandra-env.sh still uses)
    apt-get install $APTITUDE_OPTIONS openjdk-11-jdk

    # Set Java 11 as the system default. Cassandra 4.1 is incompatible with
    # Java 21 which is the Ubuntu 24.04 default. update-alternatives is the
    # most reliable way to ensure all paths (PATH, JAVA_HOME detection, sudo
    # invocations that strip env vars) all resolve to Java 11.
    JAVA11_ALT=$(update-java-alternatives -l 2>/dev/null \
        | grep 'java-1.11\|java-11-openjdk' | awk '{print $1}' | head -1)
    if [ -n "$JAVA11_ALT" ]; then
        echo "Setting Java 11 as default via update-java-alternatives ($JAVA11_ALT)"
        update-java-alternatives --set "$JAVA11_ALT"
        java -version
    else
        echo "WARNING: Java 11 alternative not found — Cassandra may fail to start" >&2
    fi

    # Import Cassandra GPG key using the modern /etc/apt/keyrings/ approach
    # (apt-key is deprecated on Ubuntu 22.04+ and non-functional on 24.04)
    # Always re-download so a corrupt/partial file from a previous run doesn't block us.
    mkdir -p /etc/apt/keyrings
    rm -f /etc/apt/keyrings/cassandra.gpg
    curl -fsSL https://downloads.apache.org/cassandra/KEYS \
        | gpg --dearmor --batch -o /etc/apt/keyrings/cassandra.gpg

    # Add Apache Cassandra 4.1.x repository if not already present.
    # Note: Apache now serves the repo via JFrog (apache.jfrog.io) but the
    # canonical apt source line still uses debian.cassandra.apache.org; both
    # may appear depending on when the list was created, so check for either.
    if ! grep -qE "debian\.cassandra\.apache\.org|apache\.jfrog\.io/artifactory/cassandra" \
            /etc/apt/sources.list.d/cassandra.sources.list 2>/dev/null; then
        echo "deb [signed-by=/etc/apt/keyrings/cassandra.gpg] https://debian.cassandra.apache.org 41x main" \
            | tee /etc/apt/sources.list.d/cassandra.sources.list
    fi

    # Install Cassandra (skip if already installed to avoid the package postinst
    # script restarting the running daemon mid-install)
    if dpkg -s cassandra >/dev/null 2>&1; then
        echo "Cassandra is already installed; skipping apt-get install to avoid service restart."
    else
        apt-get update
        apt-get install $APTITUDE_OPTIONS cassandra
    fi

    # Enable Cassandra and ensure the JVM is actually running.
    # `systemctl start` is a no-op when the SysV wrapper reports "active (exited)"
    # (systemd considers it up even if the JVM died). Use `restart` when the JVM
    # is not running so the daemon is reliably launched.
    systemctl enable cassandra
    if pgrep -f 'org.apache.cassandra' > /dev/null 2>&1; then
        echo "Cassandra JVM is already running; skipping start."
    else
        echo "Cassandra JVM is not running; restarting service..."
        systemctl restart cassandra
    fi

    # Cassandra 4.1 on Ubuntu 24.04 uses a SysV init wrapper: systemctl reports
    # "active (exited)" immediately but the JVM forks in the background and
    # takes 60-180 s to open port 9042.  Wait up to 5 minutes.
    echo "Waiting for Cassandra JVM to open port 9042 (up to 5 minutes)..."
    CASSANDRA_UP=0
    for i in $(seq 1 150); do
        # Bail early if the JVM died rather than spin the full 5 minutes
        if ! pgrep -f 'org.apache.cassandra' > /dev/null 2>&1; then
            echo "  Cassandra JVM process is not running — startup failed early." >&2
            break
        fi
        if nc -z localhost 9042 2>/dev/null; then
            echo "Cassandra is up! (attempt $i)"
            CASSANDRA_UP=1
            break
        fi
        echo "  attempt $i/150 — not yet available, sleeping 2s..."
        sleep 2
    done
    if [ "$CASSANDRA_UP" = "0" ]; then
        echo "ERROR: Cassandra did not start within expected time." >&2
        echo "--- systemctl status ---" >&2
        systemctl status cassandra --no-pager || true
        echo "--- last 80 lines of /var/log/cassandra/system.log ---" >&2
        tail -80 /var/log/cassandra/system.log 2>/dev/null || true
        echo "--- journalctl -u cassandra (last 50 lines) ---" >&2
        journalctl -u cassandra --no-pager | tail -50 || true
        exit 1
    fi

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

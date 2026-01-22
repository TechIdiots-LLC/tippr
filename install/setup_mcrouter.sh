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
# Configure mcrouter
###############################################################################
if [ ! -d /etc/mcrouter ]; then
    mkdir -p /etc/mcrouter
fi

if [ ! -f /etc/mcrouter/global.conf ]; then
    cat > /etc/mcrouter/global.conf <<MCROUTER
{
  // route all valid prefixes to the local memcached
  "pools": {
    "local": {
      "servers": [
        "127.0.0.1:11211",
      ],
      "protocol": "ascii",
      "keep_routing_prefix": false,
    },
  },
  "named_handles": [
    {
      "name": "local-pool",
      "type": "PoolRoute",
      "pool": "local",
    },
  ],
  "route": {
    "type": "PrefixSelectorRoute",
    "policies": {
      "rend:": "local-pool",
      "page:": "local-pool",
      "pane:": "local-pool",
      "vault:": "local-pool",
      "account:": "local-pool",
      "link:": "local-pool",
      "comment:": "local-pool",
      "message:": "local-pool",
      "campaign:": "local-pool",
      "award:": "local-pool",
      "trophy:": "local-pool",
      "flair:": "local-pool",
      "friend:": "local-pool",
      "inboxcomment:": "local-pool",
      "inboxmessage:": "local-pool",
      "reportlink:": "local-pool",
      "reportcomment:": "local-pool",
      "reportvault:": "local-pool",
      "reportmessage:": "local-pool",
      "modinbox:": "local-pool",
      "otp:": "local-pool",
      "captcha:": "local-pool",
      "queuedvote:": "local-pool",
      "geoip:": "local-pool",
      "geopromo:": "local-pool",
      "vaultpromos:": "local-pool",
      "rising:": "local-pool",
      "vaultid:": "local-pool",
      "defaultvaults:": "local-pool",
      "featuredvaults:": "local-pool",
      "query:": "local-pool",
      "rel:": "local-pool",
      "vaultmember:": "local-pool",
      "vaultmemberrel:": "local-pool",
    },
    "wildcard": {
      "type": "PoolRoute",
      "pool": "local",
    },
  },
}
MCROUTER
fi

if [ -x /etc/init.d/mcrouter ]; then
  /etc/init.d/mcrouter restart || true
else
  echo "mcrouter service not found; skipping restart" >&2
fi

# If mcrouter binary is not present, try building it under /opt/mcrouter using
# the community build scripts and copy the installed binary to /usr/local/bin.
if [ ! -x /usr/local/bin/mcrouter ]; then
  echo "mcrouter binary not found in /usr/local/bin; attempting build in /opt/mcrouter"
  
  # Ensure python command exists (required for mcrouter's configure)
  if ! command -v python >/dev/null 2>&1; then
    sudo apt-get update && sudo apt-get install -y python-is-python3 || true
  fi

  if [ ! -d /opt/mcrouter ]; then
    git clone https://github.com/facebook/mcrouter.git /opt/mcrouter || true
  fi
  # Disable ccache as it causes build failures on Ubuntu 24.04 with Folly/ASM.
  # We force the path to bypass /usr/lib/ccache and explicitly set the assembler.
  export PATH=$(echo $PATH | sed -e 's/:\/usr\/lib\/ccache//g' -e 's/\/usr\/lib\/ccache://g' -e 's/:\/usr\/bin\/ccache//g')
  export CC="gcc"
  export CXX="g++"
  export AS="/usr/bin/as"
  export CMAKE_ASM_COMPILER="/usr/bin/as"
  export CCACHE_DISABLE=1
  unset CMAKE_C_COMPILER_LAUNCHER
  unset CMAKE_CXX_COMPILER_LAUNCHER
  
  # Remove possibly corrupted or ccache-polluted build directories
  rm -rf /opt/mcrouter/mcrouter-install/pkgs/folly
  rm -rf /opt/mcrouter/mcrouter-install/pkgs/fbthrift
  rm -rf /opt/mcrouter/mcrouter-install/pkgs/fizz
  rm -rf /opt/mcrouter/mcrouter-install/pkgs/wangle
  rm -rf /opt/mcrouter/mcrouter-install/install

  pushd /opt/mcrouter >/dev/null 2>&1 || true
  # add known upstream fix branch if not already present
  git remote add markbhasawut https://github.com/markbhasawut/mcrouter.git 2>/dev/null || true
  git fetch markbhasawut 2>/dev/null || true
  git merge --no-edit markbhasawut/fix-oss-build 2>/dev/null || true

  # fix for missing thrift annotations in carbon build
  # we inject an include path that thrift1 can use
  export THRIFT1_INCLUDES="-I $(pwd)/mcrouter-install/install/include"

  # run the Ubuntu 24.04 helper to install deps and mcrouter
  if [ -x ./mcrouter/scripts/install_ubuntu_24.04.sh ]; then
    ./mcrouter/scripts/install_ubuntu_24.04.sh "$(pwd)"/mcrouter-install deps || true
    
    # Patch Makefile.am in lib/carbon to include the prefix include path for thrift1
    if [ -f ./mcrouter/lib/carbon/Makefile.am ]; then
      sed -i 's/\$(THRIFT1)/\$(THRIFT1) -I \$(prefix)\/include/g' ./mcrouter/lib/carbon/Makefile.am
    fi

    ./mcrouter/scripts/install_ubuntu_24.04.sh "$(pwd)"/mcrouter-install mcrouter || true
  fi
  popd >/dev/null 2>&1 || true

  # copy resulting binary into /usr/local/bin if present
  if [ -x /opt/mcrouter/mcrouter-install/install/bin/mcrouter ]; then
    cp /opt/mcrouter/mcrouter-install/install/bin/mcrouter /usr/local/bin/mcrouter || true
    chmod +x /usr/local/bin/mcrouter || true
  elif [ -x /opt/mcrouter/mcrouter ]; then
    cp /opt/mcrouter/mcrouter /usr/local/bin/mcrouter || true
    chmod +x /usr/local/bin/mcrouter || true
  fi
fi

# Install a service wrapper: prefer systemd unit if available, otherwise
# create a SysV init.d script that sources /etc/default/mcrouter.
if [ -x /usr/local/bin/mcrouter ]; then
  if command -v systemctl >/dev/null 2>&1; then
    cat > /etc/systemd/system/mcrouter.service <<'UNIT'
[Unit]
Description=mcrouter
After=network.target

[Service]
Type=simple
User=mcrouter
ExecStart=/usr/local/bin/mcrouter -f /etc/mcrouter/global.conf -p 5050 $MCROUTER_FLAGS
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT
    systemctl daemon-reload || true
    systemctl enable --now mcrouter.service || true
  else
    cat > /etc/init.d/mcrouter <<'SH'
#!/bin/sh
### BEGIN INIT INFO
# Provides:          mcrouter
# Required-Start:    $network $local_fs
# Required-Stop:     $network $local_fs
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: mcrouter
### END INIT INFO
. /lib/lsb/init-functions
[ -f /etc/default/mcrouter ] && . /etc/default/mcrouter
MCROUTER_BIN=/usr/local/bin/mcrouter
case "$1" in
  start)
  log_daemon_msg "Starting mcrouter"
  start-stop-daemon --start --background --exec $MCROUTER_BIN -- -p 5050 $MCROUTER_FLAGS
  log_end_msg $?
  ;;
  stop)
  log_daemon_msg "Stopping mcrouter"
  start-stop-daemon --stop --exec $MCROUTER_BIN
  log_end_msg $?
  ;;
  restart)
  $0 stop
  sleep 1
  $0 start
  ;;
  status)
  status_of_proc $MCROUTER_BIN mcrouter
  ;;
  *)
  echo "Usage: $0 {start|stop|restart|status}"
  exit 2
  ;;
esac
exit 0
SH
    chmod +x /etc/init.d/mcrouter || true
    update-rc.d mcrouter defaults || true
    /etc/init.d/mcrouter restart || true
  fi
fi

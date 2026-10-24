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

###############################################################################
# Configure RabbitMQ
###############################################################################
# r2 and the websockets service are the only clients, so AMQP and the
# management UI listen on localhost only; a backend (TIPPR_ROLE=backend,
# docs/SERVERS.md) also takes AMQP from its frontends, on the address they
# reach it on (the tippr account has a password). (epmd and Erlang
# distribution, ports 4369/25672, need the Erlang cookie; leave them to the
# firewall.) Upgrades re-run this: RabbitMQ restarts (about 20 seconds of
# the site's downtime) only when the file changes.
RABBIT_CONF=/etc/rabbitmq/rabbitmq.conf
rabbit_new_conf=$(mktemp)
sed '/^$/d' > "$rabbit_new_conf" <<RABBITCONF
# Managed by tippr install/setup_rabbitmq.sh
listeners.tcp.default = 127.0.0.1:5672
$([ "$TIPPR_ROLE" = "backend" ] && echo "listeners.tcp.frontends = $TIPPR_BACKEND_LISTEN:5672")
management.tcp.ip = 127.0.0.1
management.tcp.port = 15672
RABBITCONF
rabbit_restart=0
if ! cmp -s "$rabbit_new_conf" "$RABBIT_CONF"; then
    install -m 0644 "$rabbit_new_conf" "$RABBIT_CONF"
    rabbit_restart=1
fi
rm -f "$rabbit_new_conf"

if ! sudo rabbitmqctl list_vhosts | egrep "^/$"
then
    sudo rabbitmqctl add_vhost /
fi

if ! sudo rabbitmqctl list_users | egrep "^tippr"
then
    sudo rabbitmqctl add_user tippr "$TIPPR_AMQP_PASSWORD"
fi
# keep the password in step with the generated one on every run
sudo rabbitmqctl change_password tippr "$TIPPR_AMQP_PASSWORD"

sudo rabbitmqctl set_permissions -p / tippr ".*" ".*" ".*"
# (enabling a plugin takes effect without a restart)
if ! grep -q rabbitmq_management /etc/rabbitmq/enabled_plugins 2>/dev/null; then
    sudo rabbitmq-plugins enable rabbitmq_management
fi
if [ "$rabbit_restart" = 1 ] || ! sudo service rabbitmq-server status >/dev/null 2>&1; then
    sudo service rabbitmq-server restart
fi

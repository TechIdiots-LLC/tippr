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
# management UI listen on localhost only. (epmd and Erlang distribution,
# ports 4369/25672, need the Erlang cookie; leave them to the firewall.)
cat > /etc/rabbitmq/rabbitmq.conf <<RABBITCONF
# Managed by tippr install/setup_rabbitmq.sh
listeners.tcp.default = 127.0.0.1:5672
management.tcp.ip = 127.0.0.1
management.tcp.port = 15672
RABBITCONF

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
sudo rabbitmq-plugins enable rabbitmq_management
sudo service rabbitmq-server restart

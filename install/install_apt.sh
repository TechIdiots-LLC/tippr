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
###############################################################################

# load configuration
RUNDIR=$(dirname $0)
source $RUNDIR/install.cfg

# run an aptitude update to make sure dependencies are found
apt-get update

# Check Ubuntu version and install appropriate packages
source /etc/lsb-release

if [ "$DISTRIB_RELEASE" == "24.04" ]; then
    ###########################################################################
    # Ubuntu 24.04 (Noble) with Python 3.12
    ###########################################################################

    # install prerequisites - Python 3 versions
    cat <<PACKAGES | xargs apt-get install $APTITUDE_OPTIONS
netcat-openbsd
git
wget

python3-dev
python3-pip
python3-setuptools
python3-venv
python3-lib2to3
python3-six
python3-tz
python3-babel
python3-numpy
python3-dateutil
cython3
python3-sqlalchemy
python3-bs4
python3-chardet
python3-psycopg2
python3-pil
python3-lxml
python3-yaml
python3-redis
python3-pyramid
python3-flask
python3-bcrypt
python3-snappy
python3-cassandra

geoip-bin
geoip-database
python3-geoip

nodejs
npm
gettext
make
optipng
jpegoptim

ccache

libpcre3-dev
libpq-dev
build-essential
libssl-dev
libmemcached-dev
libsnappy-dev
libgeoip-dev
gperf
thrift-compiler

memcached
PACKAGES

    # Note: Python packages are installed via pip in the venv created by tippr.sh
    # The following packages are installed there: pyramid-mako, Paste, PasteDeploy,
    # pylibmc, simplejson, pytest, baseplate, gunicorn, PasteScript

else
    ###########################################################################
    # Ubuntu 14.04 (Trusty) - Legacy Python 2 installation
    ###########################################################################

    # add the datastax cassandra repos
    echo deb http://debian.datastax.com/community stable main | \
        sudo tee $CASSANDRA_SOURCES_LIST

    wget -qO- -L https://debian.datastax.com/debian/repo_key | \
        sudo apt-key add -

    # add the tippr ppa for some custom packages
    apt-get install $APTITUDE_OPTIONS python-software-properties
    apt-add-repository -y ppa:reddit/ppa

    # pin the ppa
    cat <<HERE > /etc/apt/preferences.d/reddit
Package: *
Pin: release o=LP-PPA-tippr
Pin-Priority: 600
HERE

    # grab the new ppas' package listings
    apt-get update

    # travis gives us a stock libmemcached. We have to remove that
    apt-get remove $APTITUDE_OPTIONS $(dpkg-query -W -f='${binary:Package}\n' | grep libmemcached | tr '\n' ' ') || true
    apt-get autoremove $APTITUDE_OPTIONS

    # install prerequisites - Python 2 versions
    cat <<PACKAGES | xargs apt-get install $APTITUDE_OPTIONS
netcat-openbsd
git-core

python-dev
python-setuptools
python-routes
python-pylons
python-boto
python-tz
python-crypto
python-babel
python-numpy
python-dateutil
cython
python-sqlalchemy
python3-bs4
python-chardet
python-psycopg2
python3-pycassa
python-imaging
python-pycaptcha
python-pylibmc=1.2.2-1~trusty5
python-amqplib
python-bcrypt
python-snappy
python-snudown
python-l2cs
python-lxml
python-kazoo
python-stripe
python-tinycss2
python-unidecode
python-mock
python-yaml
python-httpagentparser

python-baseplate

python-flask
geoip-bin
geoip-database
python-geoip

nodejs
node-less
node-uglify
gettext
make
optipng
jpegoptim

libpcre3-dev

python-gevent
python-gevent-websocket
python-haigha

python-redis
python-pyramid
python-raven
PACKAGES

fi

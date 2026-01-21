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

###############################################################################
# Configure PostgreSQL
###############################################################################
SQL="SELECT COUNT(1) FROM pg_catalog.pg_database WHERE datname = 'tippr';"
IS_DATABASE_CREATED=$(sudo -u postgres env LC_ALL=C psql -t -c "$SQL" | tr -d '[:space:]')

# Ensure the proper locale is generated and available. Prefer en_US.UTF-8 but
# tolerate variants like en_US.utf8 which PostgreSQL may expect.
if ! locale -a | grep -iq "en_US"; then
    echo "Generating en_US.UTF-8 locale..."
    apt-get update -y
    apt-get install -y locales || true
    locale-gen en_US.UTF-8 || true
    update-locale LANG=en_US.UTF-8 || true
fi

# Determine a locale string PostgreSQL will accept (try common variants).
LOCALE_NAME=""
for cand in "en_US.UTF-8" "en_US.utf8" "en_US.UTF8" "en_US"; do
    if locale -a | grep -iq "^${cand}$"; then
        LOCALE_NAME=$cand
        break
    fi
done

if [ "$IS_DATABASE_CREATED" != "1" ]; then
    # Try creating the DB specifying LC_COLLATE/LC_CTYPE if we detected a usable locale.
    if [ -n "$LOCALE_NAME" ]; then
        if sudo -u postgres env LC_ALL=C psql -c "CREATE DATABASE tippr WITH ENCODING = 'UTF8' TEMPLATE template0 LC_COLLATE='${LOCALE_NAME}' LC_CTYPE='${LOCALE_NAME}';" 2>/tmp/createdb.err; then
            echo "Database created with locale ${LOCALE_NAME}"
        else
            echo "Failed to create database with locale ${LOCALE_NAME}, retrying without explicit locale..."
            cat /tmp/createdb.err || true
                sudo -u postgres env LC_ALL=C psql -c "CREATE DATABASE tippr WITH ENCODING = 'UTF8' TEMPLATE template0;" || true
        fi
    else
          sudo -u postgres env LC_ALL=C psql -c "CREATE DATABASE tippr WITH ENCODING = 'UTF8' TEMPLATE template0;" || true
    fi
fi

# Create role if it doesn't exist
ROLE_EXISTS=$(sudo -u postgres env LC_ALL=C psql -t -c "SELECT 1 FROM pg_roles WHERE rolname='tippr';" | tr -d '[:space:]')
if [ "$ROLE_EXISTS" != "1" ]; then
     sudo -u postgres env LC_ALL=C psql -c "CREATE USER tippr WITH PASSWORD 'password';" || true
else
     sudo -u postgres env LC_ALL=C psql -c "ALTER USER tippr WITH PASSWORD 'password';" || true
fi

# Ensure the tippr user owns the tippr database so it can create tables
sudo -u postgres env LC_ALL=C psql -c "ALTER DATABASE tippr OWNER TO tippr;" || true

# Grant privileges on the public schema to the tippr user (needed when the
# database owner is different or defaults are restrictive)
sudo -u postgres env LC_ALL=C psql tippr -c "GRANT ALL PRIVILEGES ON SCHEMA public TO tippr;" || true

sudo -u postgres env LC_ALL=C psql tippr <<FUNCTIONSQL
create or replace function hot(ups integer, downs integer, date timestamp with time zone) returns numeric as \$\$
    select round(cast(log(greatest(abs(\$1 - \$2), 1)) * sign(\$1 - \$2) + (date_part('epoch', \$3) - 1134028003) / 45000.0 as numeric), 7)
\$\$ language sql immutable;

create or replace function score(ups integer, downs integer) returns integer as \$\$
    select \$1 - \$2
\$\$ language sql immutable;

create or replace function controversy(ups integer, downs integer) returns float as \$\$
    select CASE WHEN \$1 <= 0 or \$2 <= 0 THEN 0
                WHEN \$1 > \$2 THEN power(\$1 + \$2, cast(\$2 as float) / \$1)
                ELSE power(\$1 + \$2, cast(\$1 as float) / \$2)
           END;
\$\$ language sql immutable;

create or replace function ip_network(ip text) returns text as \$\$
    select substring(\$1 from E'[\\d]+\.[\\d]+\.[\\d]+')
\$\$ language sql immutable;

create or replace function base_url(url text) returns text as \$\$
    select substring(\$1 from E'(?i)(?:.+?://)?(?:www[\\d]*\\.)?([^#]*[^#/])/?')
\$\$ language sql immutable;

create or replace function domain(url text) returns text as \$\$
    select substring(\$1 from E'(?i)(?:.+?://)?(?:www[\\d]*\\.)?([^#/]*)/?')
\$\$ language sql immutable;
FUNCTIONSQL

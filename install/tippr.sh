#!/bin/bash
###############################################################################
# tippr dev environment installer
# --------------------------------
# This script installs a tippr stack suitable for development. DO NOT run this
# on a system that you use for other purposes as it might delete important
# files, truncate your databases, and otherwise do mean things to you.
#
# By default, this script will install the tippr code in the current user's
# home directory and all of its dependencies (including libraries and database
# servers) at the system level. The installed tippr will expect to be visited
# on the domain "tippr.local" unless specified otherwise.  Configuring name
# resolution for the domain is expected to be done outside the installed
# environment (e.g. in your host machine's /etc/hosts file) and is not
# something this script handles.
#
# Several configuration options (listed in the "Configuration" section below)
# are overridable with environment variables. e.g.
#
#    sudo TIPPR_DOMAIN=example.com ./install/tippr.sh
#
###############################################################################

# Installer options (environment variables)
# - TIPPR_BRANCH: when set, the installer will clone the specified branch or tag
#   from GitHub instead of the repository default. Example:
#     TIPPR_BRANCH=my-feature-branch ./install/tippr.sh
# - TIPPR_COPY_LOCAL: when set to a local path, the installer will copy that
#   checked-out tree into the install destination instead of cloning. Useful for
#   testing local changes. Example:
#     TIPPR_COPY_LOCAL=/home/user/code/tippr ./install/tippr.sh
# - TIPPR_GITHUB_TOKEN / GITHUB_TOKEN: optional token used for cloning private
#   repositories when anonymous clone fails.


# load configuration
RUNDIR=$(dirname $0)
export TIPPR_INSTALLER=1
source $RUNDIR/install.cfg

# Allow overriding service repo locations (format: owner/repo)
: ${TIPPR_WEBSOCKETS_REPO:=TechIdiots-LLC/tippr-service-websockets}
: ${TIPPR_ACTIVITY_REPO:=TechIdiots-LLC/tippr-service-activity}


###############################################################################
# Sanity Checks
###############################################################################
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: Must be run with root privileges."
    exit 1
fi

if [[ -z "$TIPPR_USER" ]]; then
    # in a production install, you'd want the code to be owned by root and run
    # by a less privileged user. this script is intended to build a development
    # install, so we expect the owner to run the app and not be root.
    cat <<END
ERROR: You have not specified a user. This usually means you're running this
script directly as root. It is not recommended to run tippr as the root user.

Please create a user to run tippr and set the TIPPR_USER variable
appropriately.
END
    exit 1
fi

# Ensure runtime OS user exists; if not, create it so installer can chown files
if ! id -u "$TIPPR_USER" >/dev/null 2>&1; then
    echo "System user $TIPPR_USER does not exist; creating..."
    # Ensure group exists
    if ! getent group "$TIPPR_GROUP" >/dev/null 2>&1; then
        groupadd -r "$TIPPR_GROUP" || true
    fi
    useradd -m -s /bin/bash -g "$TIPPR_GROUP" "$TIPPR_USER" || true
    echo "Created system user $TIPPR_USER"
fi

if [[ "amd64" != $(dpkg --print-architecture) ]]; then
    cat <<END
ERROR: This host is running the $(dpkg --print-architecture) architecture!

Because of the pre-built dependencies in our PPA, and some extra picky things
like ID generation in liveupdate, installing tippr is only supported on amd64
architectures.
END
    exit 1
fi

# Check for supported Ubuntu versions
source /etc/lsb-release
if [ "$DISTRIB_ID" != "Ubuntu" ]; then
    echo "ERROR: Only Ubuntu is supported."
    exit 1
fi

# Support Ubuntu 24.04 (noble) with Python 3.12
if [ "$DISTRIB_RELEASE" != "24.04" ] && [ "$DISTRIB_RELEASE" != "14.04" ]; then
    echo "ERROR: Only Ubuntu 14.04 and 24.04 are supported."
    exit 1
fi

if [[ "2000000" -gt $(awk '/MemTotal/{print $2}' /proc/meminfo) ]]; then
    LOW_MEM_PROMPT="tippr requires at least 2GB of memory to work properly, continue anyway? [y/n] "
    read -er -n1 -p "$LOW_MEM_PROMPT" response
    if [[ "$response" != "y" ]]; then
      echo "Quitting."
      exit 1
    fi
fi

TIPPR_AVAILABLE_PLUGINS=""
for plugin in $TIPPR_PLUGINS; do
    if [ -d $TIPPR_SRC/$plugin ]; then
        if [[ -z "$TIPPR_PLUGINS" ]]; then
            TIPPR_AVAILABLE_PLUGINS+="$plugin"
        else
            TIPPR_AVAILABLE_PLUGINS+=" $plugin"
        fi
        echo "plugin $plugin found"
    else
        echo "plugin $plugin not found"
    fi
done

# Add tippr source to the virtualenv path so all modules (pylons, r2, etc)
# are findable regardless of working directory or manual vs service start.
for p in "$TIPPR_VENV"/lib/python*/site-packages; do
    if [ -d "$p" ]; then
        cat > "$p/tippr.pth" <<PTH
$TIPPR_SRC/tippr
$TIPPR_SRC/tippr/r2
PTH
    fi
done

###############################################################################
# Install prerequisites
###############################################################################

# install primary packages
$RUNDIR/install_apt.sh

# install cassandra from datastax
$RUNDIR/install_cassandra.sh

# install zookeeper
$RUNDIR/install_zookeeper.sh

# install services (rabbitmq, postgres, memcached, etc.)
$RUNDIR/install_services.sh

# install opensearch (TIPPR_SEARCH=opensearch)
if [ "$TIPPR_SEARCH" = "opensearch" ]; then
    $RUNDIR/install_opensearch.sh
fi

###############################################################################
# Install the tippr source repositories
###############################################################################
if [ ! -d $TIPPR_SRC ]; then
    mkdir -p $TIPPR_SRC
    chown $TIPPR_USER $TIPPR_SRC
fi

function copy_systemd {
    if [ -d "${1}/systemd" ]; then
        echo "Copying and templating systemd units from ${1}/systemd to /etc/systemd/system/..."
        # Iterate over files to perform variable substitution before installation
        for f in "${1}"/systemd/*.service "${1}"/systemd/*.timer "${1}"/systemd/*.target "${1}"/systemd/*.path; do
            [ -e "$f" ] || continue
            dest="/etc/systemd/system/$(basename "$f")"
            echo "  -> Templating $(basename "$f")"
            sed -e "s|@TIPPR_USER@|$TIPPR_USER|g" \
                -e "s|@TIPPR_GROUP@|$TIPPR_GROUP|g" \
                -e "s|@TIPPR_HOME@|$TIPPR_HOME|g" \
                -e "s|@TIPPR_SRC@|$TIPPR_SRC|g" \
                -e "s|@TIPPR_VENV@|$TIPPR_VENV|g" \
                -e "s|@TIPPR_ROOT@|$TIPPR_SRC/tippr/r2|g" \
                -e "s|@TIPPR_INI@|$TIPPR_SRC/tippr/r2/run.ini|g" \
                -e "s|\${TIPPR_INI}|$TIPPR_SRC/tippr/r2/run.ini|g" \
                -e "s|\"\${TIPPR_INI}\"|\"$TIPPR_SRC/tippr/r2/run.ini\"|g" \
                -e "s|\${TIPPR_ROOT}|$TIPPR_SRC/tippr/r2|g" \
                "$f" > "$dest"
        done
        systemctl daemon-reload
    fi
}

function clone_tippr_repo {
    local destination=$TIPPR_SRC/${1}
    local repo_spec=${2}
    local repository_url
    # Optional env vars:
    # TIPPR_BRANCH: branch or tag to check out when cloning
    # TIPPR_COPY_LOCAL: when set to a local path, copy that tree to destination

    # Accept either an owner/repo spec or a full URL
    if echo "$repo_spec" | grep -qE '^https?://'; then
        repository_url="$repo_spec"
    else
        repository_url="https://github.com/${repo_spec}.git"
    fi


    # If TIPPR_COPY_LOCAL is set and points to an existing directory, copy it.
    # Only apply this behavior for the main `tippr` repository. Service
    # repositories (e.g. websockets, activity) should be cloned from their
    # upstream git locations instead of being populated from the single
    # checkout directory provided in TIPPR_COPY_LOCAL.
    if [ -n "$TIPPR_COPY_LOCAL" ] && [ -d "$TIPPR_COPY_LOCAL" ] && [ "$1" = "tippr" ]; then
        echo "Copying local tippr source from $TIPPR_COPY_LOCAL to $destination"
        rm -rf "$destination" || true
        mkdir -p "$(dirname "$destination")"
        # Copy as the tippr user
        # copy the contents ("dir/."), so a destination that rm could not fully
        # remove doesn't end up with the checkout nested inside it
        sudo -u $TIPPR_USER -H mkdir -p "$destination"
        sudo -u $TIPPR_USER -H bash -c "cp -a \"$TIPPR_COPY_LOCAL/.\" \"$destination/\""
    else
        if [ ! -d "$destination" ]; then
            # First try an anonymous clone (preserves previous CI behavior).
            # Support optional branch selection
            if [ -n "$TIPPR_BRANCH" ]; then
                CLONE_ARGS=("--branch" "${TIPPR_BRANCH}" "--single-branch")
            else
                CLONE_ARGS=()
            fi

            if sudo -u $TIPPR_USER -H git clone "${CLONE_ARGS[@]}" "$repository_url" "$destination"; then
                : # success
            else
                # Anonymous clone failed; if a token is available, retry with it.
                if [ -n "$TIPPR_GITHUB_TOKEN" ] || [ -n "$GITHUB_TOKEN" ]; then
                    token=${TIPPR_GITHUB_TOKEN:-$GITHUB_TOKEN}
                    repo_with_token=$(echo "$repository_url" | sed -E "s#https://#https://x-access-token:${token}@#")
                    sudo -u $TIPPR_USER -H git clone "${CLONE_ARGS[@]}" "$repo_with_token" "$destination" || true
                fi
            fi
        fi
    fi

    copy_systemd $destination
}

function clone_tippr_service_repo {
    local name=$1
    local repo=${2:-tippr/tippr-service-$1}
    clone_tippr_repo $name "$repo"
}

# On a re-install, stop the running stack first. A running app writes into the
# source tree (e.g. compiled templates) while it is being replaced, and jobs or
# consumers that start while Python packages are reinstalled fail (e.g. with
# pkg_resources missing mid-upgrade). Everything is started again at the end.
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ] &&         systemctl is-active -q tippr.target 2>/dev/null; then
    echo "Stopping tippr.target during the install"
    systemctl stop tippr.target
fi

clone_tippr_repo tippr TechIdiots-LLC/tippr
# i18n repo lives under the organization owner – ensure we clone the
# TechIdiots-LLC owner (not the old `tippr/` owner).
clone_tippr_repo i18n TechIdiots-LLC/tippr-i18n
clone_tippr_service_repo websockets "$TIPPR_WEBSOCKETS_REPO"
clone_tippr_service_repo activity "$TIPPR_ACTIVITY_REPO"

# Install systemd units from the current repository immediately
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    copy_systemd $RUNDIR/..
fi

###############################################################################
# Passwords and secrets
###############################################################################
# Every password and signing secret is generated once per install and kept in
# $TIPPR_SECRETS_FILE (readable by root only), so re-running the installer
# keeps the same values. A value passed in the environment, e.g.
#   TIPPR_DB_PASSWORD=... ./install-tippr.sh
# takes precedence and is saved for later runs.
TIPPR_SECRETS_FILE=${TIPPR_SECRETS_FILE:-/etc/tippr/secrets.env}
install -d -m 0700 "$(dirname "$TIPPR_SECRETS_FILE")"
touch "$TIPPR_SECRETS_FILE"
chmod 0600 "$TIPPR_SECRETS_FILE"

function random_password {
    openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | cut -c1-32
}

function random_secret {
    # r2 base64-decodes the values in its [secrets] section
    openssl rand -base64 32
}

# usage: tippr_secret NAME COMMAND...
# Sets and exports NAME from the environment, then the secrets file, then the
# output of COMMAND, and records the result in the secrets file.
function tippr_secret {
    local name=$1
    shift
    local value=${!name}
    if [ -z "$value" ]; then
        value=$(grep -E "^${name}=" "$TIPPR_SECRETS_FILE" | tail -n 1 | cut -d= -f2-)
    fi
    if [ -z "$value" ]; then
        value=$("$@")
    fi
    sed -i "/^${name}=/d" "$TIPPR_SECRETS_FILE"
    echo "${name}=${value}" >> "$TIPPR_SECRETS_FILE"
    export "${name}=${value}"
}

# Installs from before generated secrets used the ZooKeeper password "tippr",
# and ZooKeeper nodes are ACL'd to the credentials that created them. If r2
# has already created nodes (and no password was saved yet), keep "tippr"
# instead of locking the app out of its own nodes. A fresh ZooKeeper only has
# its own /zookeeper node.
function existing_zookeeper_password {
    local nodes
    nodes=$(/usr/share/zookeeper/bin/zkCli.sh -server 127.0.0.1:2181 ls / 2>/dev/null | tail -n 1)
    if echo "$nodes" | grep -qE '^\[' && [ "$nodes" != "[zookeeper]" ]; then
        echo "tippr"
    else
        random_password
    fi
}

tippr_secret TIPPR_DB_PASSWORD random_password
tippr_secret TIPPR_AMQP_PASSWORD random_password
tippr_secret TIPPR_ZOOKEEPER_PASSWORD existing_zookeeper_password
tippr_secret TIPPR_ADMIN_PASSWORD random_password
for secret in SECRET FEEDSECRET ADMINSECRET WEBSOCKET WEBSOCKET_ADMIN MEDIA_EMBED \
              ACTION_NAME EMAIL_NOTIFICATIONS CACHE_POISONING \
              ADSERVER_CLICK_URL_SECRET MODMAIL_EMAIL_SECRET \
              REQUEST_SIGNATURE_SECRET TRACKING_SECRET; do
    tippr_secret "TIPPR_SECRET_${secret}" random_secret
done

# psql and scripts/compute_time_listings read the database password from here
cat > "$TIPPR_HOME/.pgpass" <<PGPASS
localhost:5432:*:${TIPPR_USER}:${TIPPR_DB_PASSWORD}
127.0.0.1:5432:*:${TIPPR_USER}:${TIPPR_DB_PASSWORD}
PGPASS
chown "$TIPPR_USER:$TIPPR_GROUP" "$TIPPR_HOME/.pgpass"
chmod 0600 "$TIPPR_HOME/.pgpass"

# Configuration for the websockets service (sutro). Its example.ini points at
# a "rabbit.local" broker with the guest account and ships a sample signing
# key; use the local broker, the tippr account and the same "websocket"
# secret r2 signs with.
if [ -d "$TIPPR_SRC/websockets" ]; then
    cat > "$TIPPR_SRC/websockets/tippr.ini" <<WEBSOCKETSINI
# Generated by install/tippr.sh -- changes are overwritten on reinstall.
[app:main]
factory = reddit_service_websockets.app:make_app

amqp.endpoint = localhost:5672
amqp.vhost = /
amqp.username = tippr
amqp.password = $(echo "$TIPPR_AMQP_PASSWORD" | sed 's/%/%%/g')
amqp.exchange.broadcast = sutro
amqp.exchange.status = tippr_exchange
amqp.send_status_messages = false

web.ping_interval = 45
web.admin_auth = $TIPPR_SECRET_WEBSOCKET_ADMIN
web.conn_shed_rate = 5

metrics.namespace = websockets
metrics.endpoint =
# baseplate otherwise starts a Prometheus exporter on 0.0.0.0:6060
metrics.enabled = false

secrets.path = tippr_secrets.json

sentry.dsn =
sentry.environment = production

[server:main]
factory = baseplate.server.wsgi
handler = reddit_service_websockets.socketserver:WebSocketHandler
WEBSOCKETSINI
    cat > "$TIPPR_SRC/websockets/tippr_secrets.json" <<WEBSOCKETSSECRETS
{
    "secrets": {
        "secret/websockets/authorization_key": {
            "type": "versioned",
            "current": "$TIPPR_SECRET_WEBSOCKET",
            "encoding": "base64"
        }
    },
    "vault_token": ""
}
WEBSOCKETSSECRETS
    chown "$TIPPR_USER:$TIPPR_GROUP" "$TIPPR_SRC/websockets/tippr.ini" "$TIPPR_SRC/websockets/tippr_secrets.json"
    chmod 0600 "$TIPPR_SRC/websockets/tippr.ini" "$TIPPR_SRC/websockets/tippr_secrets.json"
fi

# The activity service runs from its example.ini plus metrics.enabled = false:
# baseplate otherwise starts a Prometheus exporter on 0.0.0.0:6060.
if [ -f "$TIPPR_SRC/activity/example.ini" ]; then
    sed -e 's/^\[app:main\]$/[app:main]\nmetrics.enabled = false/' \
        "$TIPPR_SRC/activity/example.ini" > "$TIPPR_SRC/activity/tippr.ini"
    chown "$TIPPR_USER:$TIPPR_GROUP" "$TIPPR_SRC/activity/tippr.ini"
fi

###############################################################################
# Environment (production or development)
###############################################################################
if [ "$TIPPR_ENVIRONMENT" = "auto" ]; then
    case "$TIPPR_DOMAIN" in
        *.local|*.localhost|*.test) TIPPR_ENVIRONMENT=development ;;
        *) TIPPR_ENVIRONMENT=production ;;
    esac
fi
case "$TIPPR_ENVIRONMENT" in
    production|development) ;;
    *)
        echo "ERROR: TIPPR_ENVIRONMENT must be production, development or auto" >&2
        exit 1
        ;;
esac
if [ -z "$TIPPR_WEB_WORKERS" ]; then
    TIPPR_WEB_WORKERS=$(nproc)
    [ "$TIPPR_WEB_WORKERS" -gt 8 ] && TIPPR_WEB_WORKERS=8
fi
if [ "$TIPPR_ENVIRONMENT" = "development" ]; then
    # restart workers when the code changes
    TIPPR_GUNICORN_ARGS="--reload"
else
    TIPPR_GUNICORN_ARGS=""
fi
echo "Installing tippr for $TIPPR_ENVIRONMENT with $TIPPR_WEB_WORKERS web workers"

# Create the environment file early so services can use it. It is managed by
# the installer and rewritten on every run.
CONSUMER_CONFIG_ROOT=$TIPPR_HOME/consumer-count.d
export TIPPR_CONSUMER_CONFIG=$CONSUMER_CONFIG_ROOT
cat > /etc/default/tippr <<DEFAULT
TIPPR_ROOT=${TIPPR_SRC}/tippr/r2
TIPPR_INI=${TIPPR_SRC}/tippr/r2/run.ini
TIPPR_USER=${TIPPR_USER}
TIPPR_GROUP=${TIPPR_GROUP}
TIPPR_CONSUMER_CONFIG=${CONSUMER_CONFIG_ROOT}
PATH=${TIPPR_VENV}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
PYTHONPATH=${TIPPR_SRC}/tippr:${TIPPR_SRC}/tippr/r2
TIPPR_ENVIRONMENT=${TIPPR_ENVIRONMENT}
TIPPR_WEB_WORKERS=${TIPPR_WEB_WORKERS}
TIPPR_GUNICORN_ARGS=${TIPPR_GUNICORN_ARGS}
DEFAULT

# Patch activity and websockets setup.py to use new baseplate module path
# (baseplate.integration was renamed to baseplate.frameworks in baseplate 1.0)
for repo in activity websockets; do
    if [ -f "$TIPPR_SRC/$repo/setup.py" ]; then
        sed -i 's/baseplate\.integration\./baseplate.frameworks./g' "$TIPPR_SRC/$repo/setup.py"
    fi
done

# (legacy) i18n Python 2 conversion will run after the virtualenv is created

###############################################################################
# Configure Services
###############################################################################

# Configure Cassandra
$RUNDIR/setup_cassandra.sh

# Configure PostgreSQL
$RUNDIR/setup_postgres.sh

# Configure mcrouter (optional; see TIPPR_BUILD_MCROUTER in install.cfg)
if [ "$TIPPR_BUILD_MCROUTER" = "1" ]; then
    $RUNDIR/setup_mcrouter.sh
else
    echo "Skipping mcrouter build (TIPPR_BUILD_MCROUTER=$TIPPR_BUILD_MCROUTER); r2 uses memcached directly."
fi

# Configure RabbitMQ
$RUNDIR/setup_rabbitmq.sh

###############################################################################
# Install and configure the tippr code
###############################################################################

# Create Python virtual environment for tippr
# Ensure the venv parent exists and is writable by the tippr user
# Remove any stale venv that is not writable by the runtime user so we can
# recreate it as the correct owner.
echo "Creating Python virtual environment at $TIPPR_VENV"
mkdir -p "$(dirname "$TIPPR_VENV")"
chown $TIPPR_USER:$TIPPR_GROUP "$(dirname "$TIPPR_VENV")" || true
if [ -d "$TIPPR_VENV" ] && [ ! -w "$TIPPR_VENV" ]; then
    echo "Existing venv at $TIPPR_VENV is not writable by $TIPPR_USER; removing"
    rm -rf "$TIPPR_VENV"
fi

# Check if a working venv already exists (e.g., pre-created by CI workflow).
# A working venv has a python executable that can import basic stdlib modules.
VENV_OK=0
if [ -x "$TIPPR_VENV/bin/python" ]; then
    if sudo -u $TIPPR_USER "$TIPPR_VENV/bin/python" -c "import sys, os, math; print('venv ok')" 2>/dev/null; then
        echo "Reusing existing working venv at $TIPPR_VENV"
        VENV_OK=1
    else
        echo "Existing venv at $TIPPR_VENV is broken; removing and recreating"
        rm -rf "$TIPPR_VENV"
    fi
fi

# Attempt to create venv; if ensurepip fails (some images lack ensurepip),
# install prerequisites and retry by bootstrapping pip via get-pip.py.
if [ "$VENV_OK" = "1" ]; then
    :
elif sudo -u $TIPPR_USER python3 -m venv $TIPPR_VENV; then
    :
else
    echo "python3 -m venv failed; attempting fallback (installing prerequisites)"
    apt-get update || true

    # Detect Python major.minor (e.g. 3.12) and prefer distro-specific packages
    PYVER=$(python3 -c 'import sys; print("{}.{}".format(sys.version_info.major, sys.version_info.minor))' 2>/dev/null || echo "")
    PKGS="python3-venv python3-pip python3-distutils"
    if [ -n "$PYVER" ]; then
        PKGS="$PKGS libpython${PYVER}-stdlib python${PYVER}"
    fi

    # Try installing candidate packages; tolerate failure and continue
    apt-get install -y $PKGS || apt-get install -y python3-venv python3-pip || true

    # Retry creating venv (this may succeed now that stdlib packages are present)
    if sudo -u $TIPPR_USER python3 -m venv $TIPPR_VENV; then
        :
    else
        # Fall back to creating venv without pip, then bootstrap pip using get-pip.py
        if sudo -u $TIPPR_USER python3 -m venv --without-pip $TIPPR_VENV; then
            echo "Bootstrapping pip into venv using get-pip.py"
            curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py || true
            if [ -f /tmp/get-pip.py ]; then
                # Ensure libpython is installed before attempting to run get-pip.py
                if [ -n "$PYVER" ]; then
                    apt-get update || true
                    apt-get install -y libpython${PYVER}-stdlib python${PYVER} || true
                fi
                if ! sudo -u $TIPPR_USER $TIPPR_VENV/bin/python /tmp/get-pip.py; then
                    # Retry once more
                    sudo -u $TIPPR_USER $TIPPR_VENV/bin/python /tmp/get-pip.py || true
                fi
                rm -f /tmp/get-pip.py || true
            else
                echo "Failed to download get-pip.py; attempting system pip to install pip into venv"
                sudo -u $TIPPR_USER python3 -m pip install --upgrade pip || true
            fi
        else
            echo "Retry to create venv failed; aborting venv setup" >&2
        fi
    fi
fi

# Create 'python' and 'python3' symlinks for compatibility
# Some tools expect 'python', others 'python3'; ensure both exist
if [ -x "$TIPPR_VENV/bin/python3" ] && [ ! -e "$TIPPR_VENV/bin/python" ]; then
    sudo -u $TIPPR_USER ln -sf python3 $TIPPR_VENV/bin/python
elif [ -x "$TIPPR_VENV/bin/python" ] && [ ! -e "$TIPPR_VENV/bin/python3" ]; then
    sudo -u $TIPPR_USER ln -sf python $TIPPR_VENV/bin/python3
fi

# Upgrade pip and install build tools in venv
# Install current setuptools/wheel and ensure `packaging` is recent so editable
# installs / metadata generation behave correctly.
# Some venvs (copied or created on minimal images) may not include pip. Try
# importing pip first; if missing, attempt to bootstrap it via ensurepip or
# get-pip.py as a fallback.
BOOT_PY="$TIPPR_VENV/bin/python"
if sudo -u $TIPPR_USER "$BOOT_PY" -c "import pip" >/dev/null 2>&1; then
    echo "pip present in venv"
else
    echo "pip not found in venv; attempting to bootstrap with ensurepip"
    if sudo -u $TIPPR_USER "$BOOT_PY" -m ensurepip --default-pip >/dev/null 2>&1; then
        echo "ensurepip succeeded"
    else
        echo "ensurepip not available or failed; downloading get-pip.py"
        rm -f /tmp/get-pip.py || true
        if curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py; then
            sudo -u $TIPPR_USER "$BOOT_PY" /tmp/get-pip.py || true
            rm -f /tmp/get-pip.py || true
        else
            echo "Failed to download get-pip.py; attempting system pip to install pip into venv"
            sudo -u $TIPPR_USER python3 -m pip install --upgrade pip || true
        fi
    fi
fi

# Now upgrade pip/setuptools/wheel and packaging
# setuptools stays below 81: paste.script (paster) imports pkg_resources, which
# setuptools 81 deprecates and later versions remove. r2/pyproject.toml pins
# the same for building r2.
sudo -u $TIPPR_USER "$BOOT_PY" -m pip install --upgrade pip 'setuptools<81' wheel
sudo -u $TIPPR_USER "$BOOT_PY" -m pip install --upgrade 'packaging>=23.1'

# Install `baseplate` early so packages that inspect/import it at build time
# (e.g., r2) can detect it. Prefer a local checkout at $TIPPR_SRC/tippr-baseplate.py
# when available, otherwise use the configured TIPPR_BASEPLATE_PIP_URL or
# fall back to PyPI.
if [ -d "$TIPPR_SRC/tippr-baseplate.py" ]; then
    echo "Installing local baseplate from $TIPPR_SRC/tippr-baseplate.py"
    sudo -u $TIPPR_USER $TIPPR_VENV/bin/pip install -e "$TIPPR_SRC/tippr-baseplate.py"
elif [ -n "$TIPPR_BASEPLATE_PIP_URL" ]; then
    echo "Installing baseplate from $TIPPR_BASEPLATE_PIP_URL"
    sudo -u $TIPPR_USER $TIPPR_VENV/bin/pip install "$TIPPR_BASEPLATE_PIP_URL"
else
    echo "Installing baseplate from PyPI"
    sudo -u $TIPPR_USER $TIPPR_VENV/bin/pip install baseplate
fi

# If provided, prefer a fork of `formenergy-observability` that supports
# modern `packaging`, install it early so it cannot force a downgrade of
# `packaging` during later bulk installs.
if [ -n "$TIPPR_FORMENERGY_OBSERVABILITY_PIP_URL" ]; then
    echo "Installing formenergy-observability from $TIPPR_FORMENERGY_OBSERVABILITY_PIP_URL"
    sudo -u $TIPPR_USER $TIPPR_VENV/bin/pip install "$TIPPR_FORMENERGY_OBSERVABILITY_PIP_URL" || true
fi

# Install baseplate and other runtime dependencies
# Installation order/options:
# 1. If `TIPPR_BASEPLATE_PIP_URL` is set, install baseplate from that pip
#    spec (supports git+ URLs, file://, or local editable installs).
# 2. Else if `TIPPR_BASEPLATE_REPO` is set, install from the given fork
#    (legacy behavior).
# 3. Otherwise install `baseplate` from PyPI.
if [ -n "$TIPPR_BASEPLATE_PIP_URL" ]; then
    echo "Installing baseplate from pip spec: $TIPPR_BASEPLATE_PIP_URL"
    sudo -u $TIPPR_USER $TIPPR_VENV/bin/pip install \
        "$TIPPR_BASEPLATE_PIP_URL" \
        "gunicorn" \
        "whoosh" \
        "PasteScript" \
        "pyramid-mako" \
        "Paste" \
        "PasteDeploy" \
        "pylibmc" \
        "simplejson" \
        "pytz" \
        "pytest" \
        "Babel" \
        "Cython" \
        "raven" \
        "Flask" \
        "GeoIP" \
        "pika>=1.3.2,<2" \
        "sentry-sdk"
elif [ -n "$TIPPR_BASEPLATE_REPO" ]; then
    echo "Installing baseplate from fork: $TIPPR_BASEPLATE_REPO"
    sudo -u $TIPPR_USER $TIPPR_VENV/bin/pip install \
        "git+https://github.com/$TIPPR_BASEPLATE_REPO.git@main#egg=baseplate" \
        "gunicorn" \
        "whoosh" \
        "PasteScript" \
        "pyramid-mako" \
        "Paste" \
        "PasteDeploy" \
        "pylibmc" \
        "simplejson" \
        "pytz" \
        "pytest" \
        "Babel" \
        "Cython" \
        "raven" \
        "Flask" \
        "GeoIP" \
        "pika>=1.3.2,<2" \
        "sentry-sdk"
else
    sudo -u $TIPPR_USER $TIPPR_VENV/bin/pip install \
        "baseplate" \
        "gunicorn" \
        "whoosh" \
        "PasteScript" \
        "pyramid-mako" \
        "Paste" \
        "PasteDeploy" \
        "pylibmc" \
        "simplejson" \
        "pytz" \
        "pytest" \
        "Babel" \
        "Cython" \
        "raven" \
        "Flask" \
        "GeoIP" \
        "pika>=1.3.2,<2" \
        "sentry-sdk"
fi

# Create a writable directory for Prometheus multiprocess mode if needed
# and make it owned by the tippr user so prometheus-client can write there.
PROMETHEUS_DIR=/var/lib/tippr/prometheus-multiproc
if [ ! -d "$PROMETHEUS_DIR" ]; then
    mkdir -p "$PROMETHEUS_DIR"
    chown $TIPPR_USER:$TIPPR_GROUP "$PROMETHEUS_DIR"
    chmod 0775 "$PROMETHEUS_DIR"
fi
# Additional packages that `r2` currently lists as runtime/test deps.
# Install them into the venv as the tippr user. Some packages require
# system libs (e.g. libpq-dev, libxml2-dev); failures will be reported
# but won't abort the installer.
sudo -u $TIPPR_USER $TIPPR_VENV/bin/pip install \
    bcrypt \
    beautifulsoup4 \
    boto3 \
    captcha \
    cassandra-driver \
    cqlsh \
    chardet \
    httpagentparser \
    kazoo \
    lxml \
    stripe \
    tinycss2 \
    unidecode \
    PyYAML \
    Pillow \
    python-snappy \
    pylibmc \
    whoosh \
    webtest \
    mock \
    pytest \
    coverage \
    "snudown @ https://github.com/nicnacnic/snudown/archive/refs/heads/master.zip" || true

# Prefer psycopg2-binary to avoid requiring system postgres headers during
# install; if you need the real psycopg2 build from source, install
# libpq-dev and python3-dev on the host instead.
sudo -u $TIPPR_USER $TIPPR_VENV/bin/pip install psycopg2-binary || true

# Ensure `packaging` remains at a modern version — some packages may pull
# older versions during bulk installs. Force-reinstall without deps to keep
# the build-toolchain compatible for later editable installs.
sudo -u $TIPPR_USER $TIPPR_VENV/bin/pip install --upgrade --force-reinstall --no-deps 'packaging>=23.1' || true

# Convert legacy Python 2 sources in i18n to Python 3 using lib2to3
if [ -d "$TIPPR_SRC/i18n" ]; then
    echo "Converting i18n Python files to Python 3 with lib2to3"
    for pyf in $(find "$TIPPR_SRC/i18n" -name "*.py"); do
        sudo -u $TIPPR_USER PATH="$TIPPR_VENV/bin:$PATH" python3 -m lib2to3 -w "$pyf" || true
    done
fi

function install_tippr_repo {
    pushd $TIPPR_SRC/$1
    # Ensure build-toolchain is pinned so metadata generation won't fail
    sudo -u $TIPPR_USER $TIPPR_VENV/bin/pip install --upgrade --force-reinstall --no-deps pip 'setuptools<81' wheel 'packaging>=23.1' || true

    sudo -u $TIPPR_USER $TIPPR_VENV/bin/python setup.py build
    # --no-build-isolation uses the venv's packages (like baseplate) instead of isolated env
    sudo -u $TIPPR_USER $TIPPR_VENV/bin/pip install --no-build-isolation -e .
    popd
}

install_tippr_repo tippr/r2
# Only install the external `i18n` package if its setup.py contains a
# valid version string. Some historical `i18n` checkouts have an empty
# version which breaks modern packaging tools; in that case skip the
# install and rely on local compatibility shims in the tree.
# Ensure i18n is installed; if its setup.py lacks a version, inject a
# minimal default to satisfy modern packaging tools.
if [ -f "$TIPPR_SRC/i18n/setup.py" ]; then
    if ! grep -Eq "version\s*=\s*['\"][^'\"]+['\"]" "$TIPPR_SRC/i18n/setup.py"; then
        echo "Patching i18n/setup.py to add default version 0.0.1"
        # Backup original for debugging
        cp "$TIPPR_SRC/i18n/setup.py" "$TIPPR_SRC/i18n/setup.py.orig" || true
        # Replace with a minimal, safe setup.py to avoid legacy packaging issues
        cat > "$TIPPR_SRC/i18n/setup.py" <<'PYSETUP'
from setuptools import setup, find_packages

setup(
    name='i18n',
    version='0.0.1',
    packages=find_packages(),
)
PYSETUP
    fi
    install_tippr_repo i18n
else
    echo "i18n checkout not present; skipping i18n install"
    SKIP_I18N=1
fi
for plugin in $TIPPR_AVAILABLE_PLUGINS; do
    copy_systemd $TIPPR_SRC/$plugin
    install_tippr_repo $plugin
done
install_tippr_repo websockets
install_tippr_repo activity

# generate binary translation files from source
if [ "${SKIP_I18N}" != "1" ]; then
    # Use venv's python for make commands
    sudo -u $TIPPR_USER PATH="$TIPPR_VENV/bin:$PATH" make -C $TIPPR_SRC/i18n clean all
else
    echo "Skipping i18n message compilation because i18n package was not installed"
fi

# this builds static files and should be run *after* languages are installed
# so that the proper language-specific static files can be generated and after
# plugins are installed so all the static files are available.
pushd $TIPPR_SRC/tippr/r2
# Use venv's python for make commands
sudo -u $TIPPR_USER PATH="$TIPPR_VENV/bin:$PATH" PYTHONPATH="$TIPPR_SRC/tippr:$TIPPR_SRC" make clean pyx

plugin_str=$(echo -n "$TIPPR_AVAILABLE_PLUGINS" | tr " " ,)
if [ ! -f development.update ]; then
    cat > development.update <<DEVELOPMENT
# after editing this file, run "make ini" to
# generate a new development.ini

[DEFAULT]
# debug, captcha, rate limits, admin TOTP and static file handling are set by
# the installer from TIPPR_ENVIRONMENT (see development.secrets).
# ads stay off until AdSense is set up on /admin/ads; true turns them off
# regardless
disable_ads = false

domain = $TIPPR_DOMAIN
oauth_domain = $TIPPR_DOMAIN
https_endpoint = https://$TIPPR_DOMAIN
payment_domain = https://pay.$TIPPR_DOMAIN/

plugins = $plugin_str

media_provider = filesystem
media_fs_root = /srv/www/media
media_fs_base_url_http = http://%(domain)s/media/

[server:main]
port = 8001
DEVELOPMENT
    chown $TIPPR_USER development.update
else
    sed -i "s/^plugins = .*$/plugins = $plugin_str/" $TIPPR_SRC/tippr/r2/development.update
    sed -i "s/^domain = .*$/domain = $TIPPR_DOMAIN/" $TIPPR_SRC/tippr/r2/development.update
    sed -i "s/^oauth_domain = .*$/oauth_domain = $TIPPR_DOMAIN/" $TIPPR_SRC/tippr/r2/development.update
    sed -i "s@^https_endpoint = .*@https_endpoint = https://$TIPPR_DOMAIN@" $TIPPR_SRC/tippr/r2/development.update
    sed -i "s@^payment_domain = .*@payment_domain = https://pay.$TIPPR_DOMAIN/@" $TIPPR_SRC/tippr/r2/development.update
fi

# Generated passwords and signing secrets. "make ini" merges this file over
# development.update, so local edits to development.update never collide
# with the generated values. It is rewritten from $TIPPR_SECRETS_FILE on
# every install; '%' is doubled because paster interpolates the ini.
# Settings that follow TIPPR_ENVIRONMENT. In production the debug flag must be
# off: its error pages allow remote code execution.
# Every request reaches r2 through the local nginx/haproxy, which set
# X-Forwarded-For to the real client, so trust it from local addresses; without
# this every visitor looks like 127.0.0.1 (rate limits, bans, spam checks).
function proxy_settings {
    echo "trust_local_proxies = true"
}

function environment_settings {
    if [ "$TIPPR_ENVIRONMENT" = "production" ]; then
        cat <<PRODUCTION
debug = false
template_debug = false
reload_templates = false
uncompressedJS = false
sqlprinting = false
disable_captcha = false
disable_ratelimit = false
disable_require_admin_otp = false
PRODUCTION
    else
        cat <<DEVELOPMENT
debug = true
reload_templates = true
uncompressedJS = true
disable_captcha = true
disable_ratelimit = true
disable_require_admin_otp = true
DEVELOPMENT
    fi
}

# Branding and contact settings given to the installer. Unset ones are left
# to development.update / example.ini.
function site_settings {
    [ -n "$TIPPR_SITE_NAME" ] && echo "site_name = $(ini_value "$TIPPR_SITE_NAME")"
    [ -n "$TIPPR_SITE_DESCRIPTION" ] && echo "short_description = $(ini_value "$TIPPR_SITE_DESCRIPTION")"
    [ -n "$TIPPR_CONTACT_EMAIL" ] && echo "contact_email = $(ini_value "$TIPPR_CONTACT_EMAIL")"
    true
}

function ini_value {
    local value=$1
    echo "${value//%/%%}"
}
cat > development.secrets <<SECRETS
# Installer-managed settings and secrets, generated by install/tippr.sh
# (secrets come from $TIPPR_SECRETS_FILE) -- do not edit. To change a value,
# re-run the installer with it set, e.g.
#   TIPPR_DB_PASSWORD=... ./install-tippr.sh
#   TIPPR_ENVIRONMENT=development ./install-tippr.sh

[DEFAULT]
$(environment_settings)
$(site_settings)
$(proxy_settings)

db_pass = $(ini_value "$TIPPR_DB_PASSWORD")
amqp_pass = $(ini_value "$TIPPR_AMQP_PASSWORD")
zookeeper_password = $(ini_value "$TIPPR_ZOOKEEPER_PASSWORD")
tracking_secret = $TIPPR_SECRET_TRACKING_SECRET

[secrets]
SECRET = $TIPPR_SECRET_SECRET
FEEDSECRET = $TIPPR_SECRET_FEEDSECRET
ADMINSECRET = $TIPPR_SECRET_ADMINSECRET
websocket = $TIPPR_SECRET_WEBSOCKET
media_embed = $TIPPR_SECRET_MEDIA_EMBED
action_name = $TIPPR_SECRET_ACTION_NAME
email_notifications = $TIPPR_SECRET_EMAIL_NOTIFICATIONS
cache_poisoning = $TIPPR_SECRET_CACHE_POISONING
adserver_click_url_secret = $TIPPR_SECRET_ADSERVER_CLICK_URL_SECRET
modmail_email_secret = $TIPPR_SECRET_MODMAIL_EMAIL_SECRET
request_signature_secret = $TIPPR_SECRET_REQUEST_SIGNATURE_SECRET

# Installer-managed: haproxy is the only client of the app server.
[server:main]
host = 127.0.0.1
SECRETS
chown $TIPPR_USER development.secrets
chmod 0600 development.secrets

# Regenerate development.ini so changed secrets always take effect.
rm -f development.ini
sudo -u $TIPPR_USER PATH="$TIPPR_VENV/bin:$PATH" PYTHONPATH="$TIPPR_SRC/tippr:$TIPPR_SRC" make ini || true

# Ensure `development.ini` exists. If `make ini` didn't create it (CI or
# permission issues), try generating it directly with `updateini.py`.
if [ ! -s development.ini ]; then
    echo "development.ini not found; attempting to generate with updateini.py"
    sudo -u $TIPPR_USER bash -lc "PATH=\"$TIPPR_VENV/bin:\$PATH\" PYTHONPATH=\"$TIPPR_SRC/tippr:$TIPPR_SRC\" python updateini.py example.ini development.update development.secrets > development.ini" || true
fi
# The ini files hold every password and secret.
chmod 0600 development.ini 2>/dev/null || true

# Ensure run.ini is a symlink to a real ini. Prefer development.ini, fall
# back to example.ini if generation failed.
if [ -s development.ini ]; then
    # Create a real file (not a symlink) to avoid broken-link surprises in CI
    sudo -u $TIPPR_USER cp -f development.ini run.ini
    sudo -u $TIPPR_USER chown $TIPPR_USER run.ini || true
    chmod 0600 run.ini
else
    echo "Falling back to example.ini for run.ini (development.ini missing)"
    sudo -u $TIPPR_USER cp -f example.ini run.ini
    sudo -u $TIPPR_USER chown $TIPPR_USER run.ini || true
fi

# Production serves pre-built, minified CSS and JS from r2/build/public. Build
# them with the tool versions the stylesheets and scripts were written for:
# LESS 1.4 and uglify-js 1.x (r2/lib/js.py uses its -nc flag).
if [ "$TIPPR_ENVIRONMENT" = "production" ]; then
    TIPPR_NODE_TOOLS=$TIPPR_HOME/node-tools
    sudo -u $TIPPR_USER -H npm install --no-audit --no-fund \
        --prefix "$TIPPR_NODE_TOOLS" less@1.4.2 uglify-js@1.3.5
    # LESSC: less 1.4's own lessc prints nothing on current Node, so use
    # scripts/lessc.js, which calls the library directly.
    function make_static {
        sudo -u $TIPPR_USER \
            PATH="$TIPPR_NODE_TOOLS/node_modules/.bin:$TIPPR_VENV/bin:/usr/bin:/bin" \
            PYTHONPATH="$TIPPR_SRC/tippr:$TIPPR_SRC/tippr/r2" \
            NODE_PATH="$TIPPR_NODE_TOOLS/node_modules" \
            make static LESSC="node $TIPPR_SRC/tippr/scripts/lessc.js"
    }
    # Rebuild from scratch: outputs from an earlier failed build (e.g. empty
    # CSS) would otherwise look up to date.
    sudo -u $TIPPR_USER PYTHONPATH="$TIPPR_SRC/tippr:$TIPPR_SRC/tippr/r2" \
        PATH="$TIPPR_VENV/bin:/usr/bin:/bin" make clean_static
    # make can miss files that the same run copies into build/, so a first
    # build on a clean tree may need a second pass.
    make_static || make_static
    # fail the install rather than serve empty stylesheets
    if [ ! -s "$(readlink -f build/public/static/tippr.css)" ]; then
        echo "ERROR: the static build produced an empty tippr.css" >&2
        exit 1
    fi
fi

popd

# Ensure generated Mako template cache files are owned by the app user
if [ -d "$TIPPR_SRC/tippr/r2/data/templates" ]; then
    chown -R $TIPPR_USER:$TIPPR_GROUP $TIPPR_SRC/tippr/r2/data/templates || true
fi

###############################################################################
# some useful helper scripts
###############################################################################
function helper-script() {
    cat > $1
    chmod 755 $1
}

# Create a Python script for tippr-run that bypasses paster's plugin discovery
cat > $TIPPR_VENV/bin/tippr-run-cmd <<PYCMD
#!/usr/bin/env python3
"""Direct invocation of r2's RunCommand, bypassing paster plugin discovery."""
import sys
import os

# Add tippr repo root to Python path for local shims (e.g., pylons)
# This must come before site-packages so local shims take precedence
tippr_root = '$TIPPR_SRC/tippr'
r2_dir = tippr_root + '/r2'
sys.path.insert(0, tippr_root)
sys.path.insert(0, r2_dir)
os.chdir(r2_dir)

from r2.commands import RunCommand
cmd = RunCommand('run')
# Args: config file + any additional args
cmd.run(sys.argv[1:])
PYCMD
chmod +x $TIPPR_VENV/bin/tippr-run-cmd

helper-script /usr/local/bin/tippr-run <<TIPPRRUN
#!/bin/bash
# Direct invocation of r2 RunCommand
cd $TIPPR_SRC/tippr/r2
exec $TIPPR_VENV/bin/python $TIPPR_VENV/bin/tippr-run-cmd run.ini "\$@"
TIPPRRUN

helper-script /usr/local/bin/tippr-shell <<TIPPRSHELL
#!/bin/bash
# Use paster shell command
cd $TIPPR_SRC/tippr/r2
exec $TIPPR_VENV/bin/paster shell run.ini
TIPPRSHELL

# tippr.target pulls in the app, consumers (via tippr-consumers.service) and
# job timers; every member is PartOf=tippr.target, so stopping or restarting
# the target covers all of them.
helper-script /usr/local/bin/tippr-start <<'TIPPRSTART'
#!/bin/bash
exec systemctl start tippr.target
TIPPRSTART

helper-script /usr/local/bin/tippr-stop <<'TIPPRSTOP'
#!/bin/bash
exec systemctl stop tippr.target
TIPPRSTOP

helper-script /usr/local/bin/tippr-restart <<'TIPPRRESTART'
#!/bin/bash
# usage: tippr-restart [unit]   (default: the whole stack)
if [ -n "$1" ] && [ "$1" != "all" ]; then
    exec systemctl restart "$1"
fi
exec systemctl restart tippr.target
TIPPRRESTART

helper-script /usr/local/bin/tippr-flush <<TIPPRFLUSH
#!/bin/bash
echo flush_all | nc localhost 11211
TIPPRFLUSH

# Site backups (docs/BACKUP.md): tippr-backup exports, imports and restores
# as root. /admin/backups queues requests in the queue folder (writable by
# the web app) for tippr-backup.service, started by tippr-backup.path.
# Backups belong to $TIPPR_USER and are private to it (and root).
install -d -m 0755 /var/lib/tippr
install -d -m 0700 -o $TIPPR_USER /var/lib/tippr/backups
install -d -m 0700 -o $TIPPR_USER /var/lib/tippr/backup-queue
helper-script /usr/local/bin/tippr-backup <<TIPPRBACKUP
#!/bin/bash
# usage: sudo tippr-backup export|list|import|restore ... (--help)
exec $TIPPR_VENV/bin/python $TIPPR_SRC/tippr/scripts/tippr_backup.py --ini $TIPPR_SRC/tippr/r2/run.ini "\$@"
TIPPRBACKUP

helper-script /usr/local/bin/tippr-serve <<TIPPRSERVE
#!/bin/bash
cd $TIPPR_SRC/tippr/r2
export PYTHONPATH="$TIPPR_SRC/tippr:$TIPPR_SRC:\$PYTHONPATH"
exec $TIPPR_VENV/bin/paster serve --reload run.ini
TIPPRSERVE

# Create a systemd unit for tippr-serve that uses the installer helper
# script so systemd runs paster with the correct PYTHONPATH and venv.
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    systemctl enable --now tippr-paster.service || true
fi

###############################################################################
# pixel and click server
###############################################################################
mkdir -p /var/opt/tippr/
chown $TIPPR_USER:$TIPPR_GROUP /var/opt/tippr/

# Create a mako module cache directory for compiled templates and make it writable
mkdir -p /var/opt/tippr/mako
chown $TIPPR_USER:$TIPPR_GROUP /var/opt/tippr/mako

mkdir -p /srv/www/pixel
chown $TIPPR_USER:$TIPPR_GROUP /srv/www/pixel
cp $TIPPR_SRC/tippr/r2/r2/public/static/pixel.png /srv/www/pixel

if [ ! -d /etc/gunicorn.d ]; then
    mkdir -p /etc/gunicorn.d
fi
if [ ! -f /etc/gunicorn.d/click.conf ]; then
    cat > /etc/gunicorn.d/click.conf <<CLICK
CONFIG = {
    "mode": "wsgi",
    "working_dir": "$TIPPR_SRC/tippr/scripts",
    "user": "$TIPPR_USER",
    "group": "$TIPPR_USER",
    "python": "$TIPPR_VENV/bin/python",
    "args": (
        "--bind=unix:/var/opt/tippr/click.sock",
        "--workers=1",
        "tracker:application",
    ),
}
CLICK
fi

# Create a per-app systemd service for the click server so it can be managed
# under systemd on modern systems. Only create/enable when systemd is present.
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    systemctl enable --now gunicorn-click.service || true
fi

###############################################################################
# nginx
###############################################################################

mkdir -p /srv/www/media
chown $TIPPR_USER:$TIPPR_GROUP /srv/www/media

cat > /etc/nginx/sites-available/tippr-media <<MEDIA
server {
    listen 127.0.0.1:9000;

    expires max;

    location /media/ {
        alias /srv/www/media/;
    }
}
MEDIA

cat > /etc/nginx/sites-available/tippr-pixel <<PIXEL
upstream click_server {
  server unix:/var/opt/tippr/click.sock fail_timeout=0;
}

server {
  listen 127.0.0.1:8082;
    access_log      /var/log/nginx/traffic/traffic.log directlog;

  location / {

    rewrite ^/pixel/of_ /pixel.png;

    add_header Last-Modified "";
    add_header Pragma "no-cache";

    expires -1;
    root /srv/www/pixel/;
  }

  location /click {
    proxy_pass http://click_server;
  }
}
PIXEL

###############################################################################
# TLS certificate
###############################################################################
# TIPPR_TLS_CERT / TIPPR_TLS_KEY: use those files (e.g. a Cloudflare Origin
# Certificate). TIPPR_LETSENCRYPT_EMAIL: get a certificate from Let's Encrypt
# once nginx and haproxy are running (see "Let's Encrypt" below). Otherwise,
# or until Let's Encrypt succeeds: a self-signed certificate for the domain,
# which browsers warn about.
TIPPR_TLS_DIR=/etc/tippr/tls
install -d -m 0755 "$TIPPR_TLS_DIR"
SELF_SIGNED_CERT=$TIPPR_TLS_DIR/self-signed.crt
SELF_SIGNED_KEY=$TIPPR_TLS_DIR/self-signed.key
if [ ! -s "$SELF_SIGNED_CERT" ] || \
        ! openssl x509 -in "$SELF_SIGNED_CERT" -noout -checkhost "$TIPPR_DOMAIN" | grep -q 'does match'; then
    openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
        -subj "/CN=$TIPPR_DOMAIN" \
        -addext "subjectAltName=DNS:$TIPPR_DOMAIN,DNS:*.$TIPPR_DOMAIN" \
        -keyout "$SELF_SIGNED_KEY" -out "$SELF_SIGNED_CERT"
    chmod 0600 "$SELF_SIGNED_KEY"
fi
LETSENCRYPT_CERT=/etc/letsencrypt/live/$TIPPR_DOMAIN/fullchain.pem
LETSENCRYPT_KEY=/etc/letsencrypt/live/$TIPPR_DOMAIN/privkey.pem

# usage: write_nginx_ssl CERT KEY TRUSTED
# TRUSTED=1 adds HSTS, which must not be sent with a self-signed certificate.
function write_nginx_ssl {
    local hsts=""
    if [ "$3" = "1" ]; then
        hsts='    add_header Strict-Transport-Security "max-age=31536000" always;'
    fi
    cat > /etc/nginx/sites-available/tippr-ssl <<SSL
map \$http_upgrade \$connection_upgrade {
  default upgrade;
  ''      close;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;

    ssl_certificate $1;
    ssl_certificate_key $2;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
$hsts

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$http_host;
        proxy_http_version 1.1;
        # \$remote_addr is the real client (see tippr-cloudflare.conf when
        # behind Cloudflare); r2 trusts this header from local proxies
        proxy_set_header X-Forwarded-For \$remote_addr;
        proxy_pass_header Server;

        # allow websockets through if desired
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
    }
}
SSL
}

if [ -n "$TIPPR_TLS_CERT" ] && [ -n "$TIPPR_TLS_KEY" ]; then
    write_nginx_ssl "$TIPPR_TLS_CERT" "$TIPPR_TLS_KEY" 1
elif [ -n "$TIPPR_LETSENCRYPT_EMAIL" ] && [ -s "$LETSENCRYPT_CERT" ]; then
    write_nginx_ssl "$LETSENCRYPT_CERT" "$LETSENCRYPT_KEY" 1
else
    write_nginx_ssl "$SELF_SIGNED_CERT" "$SELF_SIGNED_KEY" 0
fi

# Let's Encrypt's http-01 challenge files, served to haproxy on localhost
install -d -m 0755 /var/www/letsencrypt
cat > /etc/nginx/sites-available/tippr-acme <<ACME
server {
    listen 127.0.0.1:8083;
    root /var/www/letsencrypt;
    location / {
        try_files \$uri =404;
    }
}
ACME
ln -nsf /etc/nginx/sites-available/tippr-acme /etc/nginx/sites-enabled/

# Behind Cloudflare, take the client IP from CF-Connecting-IP, but only on
# connections from Cloudflare's published address ranges.
if [ "$TIPPR_BEHIND_CLOUDFLARE" = "1" ]; then
    CF_RANGES=$(curl -fsS https://www.cloudflare.com/ips-v4; echo; curl -fsS https://www.cloudflare.com/ips-v6)
    if ! echo "$CF_RANGES" | grep -qE '^[0-9a-f.:]+/[0-9]+$'; then
        echo "ERROR: could not download Cloudflare's IP ranges" >&2
        exit 1
    fi
    {
        echo "# Generated by install/tippr.sh (TIPPR_BEHIND_CLOUDFLARE=1)"
        echo "$CF_RANGES" | grep -E '^[0-9a-f.:]+/[0-9]+$' | sed 's/^/set_real_ip_from /; s/$/;/'
        echo "real_ip_header CF-Connecting-IP;"
    } > /etc/nginx/conf.d/tippr-cloudflare.conf
else
    rm -f /etc/nginx/conf.d/tippr-cloudflare.conf
fi

# remove the default nginx site that may conflict with haproxy
rm -rf /etc/nginx/sites-enabled/default
# put our config in place
ln -nsf /etc/nginx/sites-available/tippr-media /etc/nginx/sites-enabled/
ln -nsf /etc/nginx/sites-available/tippr-pixel /etc/nginx/sites-enabled/
ln -nsf /etc/nginx/sites-available/tippr-ssl /etc/nginx/sites-enabled/

# make the pixel log directory
mkdir -p /var/log/nginx/traffic

# Ensure the custom log_format is defined in the http context (conf.d)
cat > /etc/nginx/conf.d/tippr-log.conf <<'LOGCONF'
log_format directlog '$remote_addr - $remote_user [$time_local] '
                   '"$request_method $request_uri $server_protocol" $status $body_bytes_sent '
                   '"$http_referer" "$http_user_agent"';
LOGCONF

# link the ini file for the Flask click tracker
ln -nsf $TIPPR_SRC/tippr/r2/development.ini $TIPPR_SRC/tippr/scripts/production.ini

service nginx restart

###############################################################################
# haproxy
###############################################################################
if [ -e /etc/haproxy/haproxy.cfg ]; then
    BACKUP_HAPROXY=$(mktemp /etc/haproxy/haproxy.cfg.XXX)
    echo "Backing up /etc/haproxy/haproxy.cfg to $BACKUP_HAPROXY"
    cat /etc/haproxy/haproxy.cfg > $BACKUP_HAPROXY
fi

# make sure haproxy is enabled
cat > /etc/default/haproxy <<DEFAULT
ENABLED=1
DEFAULT

# configure haproxy
cat > /etc/haproxy/haproxy.cfg <<HAPROXY
global
    maxconn 350

frontend frontend
    mode http

    bind 0.0.0.0:80
    bind 127.0.0.1:8080

    timeout client 24h
    option forwardfor except 127.0.0.1
    option httpclose

    # ensure X-Forwarded-Proto is set to 'https' when requests arrive via TLS
    http-request del-header X-Forwarded-Proto
    acl is-ssl dst_port 8080
    http-request add-header X-Forwarded-Proto https if is-ssl

    # Let's Encrypt http-01 challenges are answered over plain http; every
    # other plain-http request is redirected to https
    acl is-acme path_beg /.well-known/acme-challenge/
    http-request redirect scheme https code 301 if !is-ssl !is-acme
    use_backend acme if is-acme

    # send websockets to the websocket service
    acl is-websocket hdr(Upgrade) -i WebSocket
    use_backend websockets if is-websocket

    # send media stuff to the local nginx
    acl is-media path_beg /media/
    use_backend media if is-media

    # send pixel stuff to local nginx
    acl is-pixel path_beg /pixel/
    acl is-click path_beg /click
    use_backend pixel if is-pixel || is-click

    default_backend tippr

backend tippr
    mode http
    timeout connect 4000
    timeout server 30000
    timeout queue 60000
    balance roundrobin

    server app01-8001 127.0.0.1:8001 maxconn 30

backend websockets
    mode http
    timeout connect 4s
    timeout server 24h
    balance roundrobin

    server websockets 127.0.0.1:9001 maxconn 250

backend media
    mode http
    timeout connect 4000
    timeout server 30000
    timeout queue 60000
    balance roundrobin

    server nginx 127.0.0.1:9000 maxconn 20

backend pixel
    mode http
    timeout connect 4000
    timeout server 30000
    timeout queue 60000
    balance roundrobin

    server nginx 127.0.0.1:8082 maxconn 20

backend acme
    mode http
    timeout connect 4000
    timeout server 30000

    server nginx 127.0.0.1:8083 maxconn 10
HAPROXY

# this will start it even if currently stopped
service haproxy restart

###############################################################################
# Let's Encrypt
###############################################################################
# nginx and haproxy now answer http-01 challenges, so request the certificate,
# then switch nginx over to it. certbot's timer renews it and reloads nginx.
if [ -n "$TIPPR_LETSENCRYPT_EMAIL" ] && [ -z "$TIPPR_TLS_CERT" ]; then
    apt-get install $APTITUDE_OPTIONS certbot
    if certbot certonly --webroot -w /var/www/letsencrypt \
            -d "$TIPPR_DOMAIN" --email "$TIPPR_LETSENCRYPT_EMAIL" \
            --agree-tos --non-interactive --keep-until-expiring \
            --deploy-hook "systemctl reload nginx"; then
        write_nginx_ssl "$LETSENCRYPT_CERT" "$LETSENCRYPT_KEY" 1
        systemctl reload nginx
    else
        echo "WARNING: Let's Encrypt failed; still using the self-signed certificate." >&2
        echo "Check that $TIPPR_DOMAIN resolves to this server and port 80 is reachable." >&2
    fi
fi

###############################################################################
# websocket service
###############################################################################
 
# Create a systemd unit for websockets (preferred on modern systems)
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    systemctl enable --now tippr-websockets.service || service tippr-websockets restart || true
fi

###############################################################################
# activity service
###############################################################################

# Create a systemd unit for activity service
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    systemctl enable --now tippr-activity.service || service tippr-activity restart || true
fi

###############################################################################
# geoip service
###############################################################################
if [ ! -f /etc/gunicorn.d/geoip.conf ]; then
    cat > /etc/gunicorn.d/geoip.conf <<GEOIP
CONFIG = {
    "mode": "wsgi",
    "working_dir": "$TIPPR_SRC/tippr/scripts",
    "user": "$TIPPR_USER",
    "group": "$TIPPR_USER",
    "python": "$TIPPR_VENV/bin/python",
    "args": (
        "--bind=127.0.0.1:5000",
        "--workers=1",
         "--limit-request-line=8190",
         "geoip_service:application",
    ),
}
GEOIP
fi

# Create a per-app systemd service for the geoip server
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    systemctl enable --now gunicorn-geoip.service || true
fi

###############################################################################
# Job Environment
###############################################################################
# CONSUMER_CONFIG_ROOT is already defined earlier in the script.
# /etc/default/tippr is already created earlier in the script.

###############################################################################
# Queue Processors
###############################################################################
mkdir -p $CONSUMER_CONFIG_ROOT

function set_consumer_count {
    if [ ! -f $CONSUMER_CONFIG_ROOT/$1 ]; then
        echo $2 > $CONSUMER_CONFIG_ROOT/$1
    fi
}

# search_q keeps the search index up to date
if [ "$TIPPR_SEARCH" = "opensearch" ]; then
    echo 1 > $CONSUMER_CONFIG_ROOT/search_q
else
    echo 0 > $CONSUMER_CONFIG_ROOT/search_q
fi
set_consumer_count del_account_q 1
set_consumer_count scraper_q 1
set_consumer_count markread_q 1
set_consumer_count commentstree_q 1
set_consumer_count newcomments_q 1
set_consumer_count vote_link_q 1
set_consumer_count vote_comment_q 1
set_consumer_count automoderator_q 0
set_consumer_count butler_q 1
set_consumer_count author_query_q 1
set_consumer_count vault_query_q 1
set_consumer_count domain_query_q 1
set_consumer_count privacy_export_q 1

chown -R $TIPPR_USER:$TIPPR_GROUP $CONSUMER_CONFIG_ROOT/

###############################################################################
# Complete plugin setup, if setup.sh exists
###############################################################################
for plugin in $TIPPR_AVAILABLE_PLUGINS; do
    if [ -x $TIPPR_SRC/$plugin/setup.sh ]; then
        echo "Found setup.sh for $plugin; running setup script"
        $TIPPR_SRC/$plugin/setup.sh $TIPPR_SRC $TIPPR_USER
    fi
done

###############################################################################
# Start everything up
###############################################################################

# the initial database setup should be done by one process rather than a bunch
# vying with eachother to get there first
tippr-run -c 'print("ok done")'

# Build the search index the first time (later changes go through search_q).
# To rebuild it from scratch:
#   tippr-run -c 'from pylons import app_globals as g; g.search.rebuild_index(recreate=True)'
if [ "$TIPPR_SEARCH" = "opensearch" ] && \
        ! curl -fsS -o /dev/null http://127.0.0.1:9200/tippr_links; then
    tippr-run -c 'from pylons import app_globals as g; g.search.rebuild_index()'
fi

###############################################################################
# Scheduled jobs (systemd timers)
###############################################################################
# Jobs used to be scheduled from /etc/cron.d/tippr; they are now systemd
# timers that are part of tippr.target. Remove the old cron file so jobs do
# not run twice on upgraded installs.
rm -f /etc/cron.d/tippr

TIPPR_TIMERS=(
    tippr-job-update_vault_names.timer
    tippr-job-update_tipprs.timer
    tippr-job-update_promos.timer
    tippr-job-clean_up_hardcache.timer
    tippr-job-broken_things.timer
    tippr-job-rising.timer
    tippr-job-trylater.timer
    tippr-job-update_popular_vaults.timer
    tippr-job-update_trending_vaults.timer
    tippr-job-compute_time_listings@link.timer
    tippr-job-compute_time_listings@comment.timer
    # sends queued email every minute; does nothing until email is set up
    # (mail_transport, or /admin/email)
    tippr-job-email.timer
)
# Disabled by default; enable with "systemctl enable --now <timer>":
#   tippr-job-update_gold_users.timer expire gold subscriptions daily

###############################################################################
# Firewall (optional)
###############################################################################
if [ "$TIPPR_FIREWALL" = "1" ]; then
    apt-get install $APTITUDE_OPTIONS ufw
    ufw allow "${TIPPR_SSH_PORT}/tcp"
    ufw allow 80/tcp
    ufw allow 443/tcp
    ufw --force enable
fi

# ok, now start everything else up
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    systemctl enable tippr.target tippr-consumers.service "${TIPPR_TIMERS[@]}"
    systemctl enable --now tippr-backup.path
    systemctl restart tippr.target
else
    echo "No systemd found; services not started."
fi

###############################################################################
# Finished with install script
###############################################################################
# Initialize policy wiki pages (Terms of Use, Privacy Policy, etc.)
echo "Ensuring application account exists..."
tippr-run $TIPPR_SRC/tippr/scripts/create_default_user.py || echo "Note: create_default_user.py skipped"
echo "Initializing policy wiki pages..."
tippr-run $TIPPR_SRC/tippr/scripts/init_policy_wiki_pages.py || echo "Note: Policy wiki pages initialization skipped (can be run manually later)"
# starter vaults and front page defaults (only sets defaults the first time)
echo "Creating starter vaults..."
tippr-run $TIPPR_SRC/tippr/scripts/create_default_vaults.py || echo "Note: starter vaults skipped (run scripts/create_default_vaults.py later)"

# print this out here. if vagrant's involved, it's gonna do more steps
# afterwards and then re-run this script but that's ok.
$RUNDIR/done.sh

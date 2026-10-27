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
# This server's role (docs/SERVERS.md)
###############################################################################
# all (one server), backend or frontend (install.cfg), decided before
# anything is installed: a frontend has no databases of its own. Remembered
# in the secrets file like the other settings, so later runs (updates) keep
# it.
TIPPR_SECRETS_FILE=${TIPPR_SECRETS_FILE:-/etc/tippr/secrets.env}
function remembered {
    [ -f "$TIPPR_SECRETS_FILE" ] && \
        grep -E "^$1=" "$TIPPR_SECRETS_FILE" | tail -n 1 | cut -d= -f2-
    true
}
TIPPR_ROLE=${TIPPR_ROLE:-$(remembered TIPPR_ROLE)}
TIPPR_ROLE=${TIPPR_ROLE:-all}
TIPPR_BACKEND_LISTEN=${TIPPR_BACKEND_LISTEN:-$(remembered TIPPR_BACKEND_LISTEN)}
TIPPR_FRONTEND_ALLOW=${TIPPR_FRONTEND_ALLOW:-$(remembered TIPPR_FRONTEND_ALLOW)}
case "$TIPPR_ROLE" in
    all) ;;
    backend)
        if [ -z "$TIPPR_BACKEND_LISTEN" ] || [ -z "$TIPPR_FRONTEND_ALLOW" ]; then
            echo "ERROR: TIPPR_ROLE=backend needs TIPPR_BACKEND_LISTEN (the address frontends reach it on) and TIPPR_FRONTEND_ALLOW (their address range): Cassandra, OpenSearch, memcached and the activity service have no password" >&2
            exit 1
        fi
        ;;
    frontend)
        # the backend's shared passwords, signing secrets, media storage and
        # address (written by the backend's install); anything given to this
        # run comes first
        if [ ! -f "$TIPPR_CLUSTER_FILE" ]; then
            echo "ERROR: TIPPR_ROLE=frontend needs the backend's $TIPPR_CLUSTER_FILE copied here first (same path, root's, mode 600)" >&2
            exit 1
        fi
        while IFS= read -r line || [ -n "$line" ]; do
            name=${line%%=*}
            [[ "$name" =~ ^TIPPR_[A-Z0-9_]+$ ]] || continue
            [ -z "${!name}" ] && export "$line"
        done < "$TIPPR_CLUSTER_FILE"
        TIPPR_BACKEND_HOST=${TIPPR_BACKEND_HOST:-$(remembered TIPPR_BACKEND_HOST)}
        if [ -z "$TIPPR_BACKEND_HOST" ]; then
            echo "ERROR: TIPPR_ROLE=frontend needs TIPPR_BACKEND_HOST (the backend's address)" >&2
            exit 1
        fi
        ;;
    *)
        echo "ERROR: TIPPR_ROLE is all, backend or frontend, not '$TIPPR_ROLE'" >&2
        exit 1
        ;;
esac
# where this server finds the databases, queue, search and cache: its own
# (all, backend) or the backend's
if [ "$TIPPR_ROLE" = "frontend" ]; then
    SERVICE_HOST=$TIPPR_BACKEND_HOST
else
    SERVICE_HOST=127.0.0.1
fi
export TIPPR_ROLE TIPPR_BACKEND_LISTEN TIPPR_FRONTEND_ALLOW TIPPR_BACKEND_HOST
echo "tippr: installing as $TIPPR_ROLE"

###############################################################################
# Install prerequisites
###############################################################################

# install primary packages
$RUNDIR/install_apt.sh

# the databases, queue and search: not on a frontend (which only needs nginx
# from install_services.sh)
if [ "$TIPPR_ROLE" != "frontend" ]; then
    # install cassandra from datastax
    $RUNDIR/install_cassandra.sh

    # install zookeeper
    $RUNDIR/install_zookeeper.sh
fi

# install services (rabbitmq, postgres, memcached, etc.; a frontend: nginx)
TIPPR_ROLE=$TIPPR_ROLE $RUNDIR/install_services.sh

# install opensearch (TIPPR_SEARCH=opensearch)
if [ "$TIPPR_SEARCH" = "opensearch" ] && [ "$TIPPR_ROLE" != "frontend" ]; then
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
    # the activity service ("here now" counts): on a backend its frontends
    # ask it too (the firewall keeps the port to them)
    local activity_bind=127.0.0.1
    [ "$TIPPR_ROLE" = "backend" ] && activity_bind=0.0.0.0
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
                -e "s|@TIPPR_ACTIVITY_BIND@|$activity_bind|g" \
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

# The translations aren't tied to a tippr release, so every install (first
# boot and upgrades re-run this script too) brings them up to date with the
# repository's default branch, even when the checkout already exists. If the
# update fails (e.g. no network), the existing translations are kept.
function update_i18n_repo {
    local destination=$TIPPR_SRC/i18n
    local repo_spec=TechIdiots-LLC/tippr-i18n
    local url=https://github.com/$repo_spec.git
    local git="sudo -u $TIPPR_USER -H git -C $destination"

    # A release's copy (the installer tarball has no .git) becomes a
    # checkout where it is, keeping its compiled catalogs: when the
    # repository hasn't changed since the release, they needn't be compiled
    # again (scripts/build-fingerprint). If that fails, it's moved aside and
    # cloned as before.
    if [ -d "$destination" ] && ! $git rev-parse --git-dir >/dev/null 2>&1; then
        echo "Making $destination a git checkout"
        if ! { $git init --quiet && $git remote add origin "$url" &&
                $git fetch --quiet --depth 1 origin &&
                $git remote set-head origin --auto >/dev/null &&
                $git reset --quiet --hard origin/HEAD; }; then
            local old="$destination.old-$(date +%Y%m%d%H%M%S)"
            echo "could not; moving it to $old"
            rm -rf "$destination/.git"
            mv "$destination" "$old"
        fi
    fi

    if [ ! -d "$destination" ]; then
        # TIPPR_BRANCH names a tippr branch; the translations use their own
        TIPPR_BRANCH= clone_tippr_repo i18n "$repo_spec"
        return
    fi

    echo "Updating the translations in $destination"
    # older installs cloned from the old owner
    $git remote set-url origin "$url"
    if $git fetch --quiet origin && $git remote set-head origin --auto >/dev/null &&
            $git reset --quiet --hard origin/HEAD; then
        echo "Translations are at $($git log -1 --format='%h %cd' --date=short)"
    else
        echo "WARNING: could not update the translations; keeping the existing ones"
    fi
}

# The slow build steps (Cython modules, translations, static files) are
# skipped when their inputs haven't changed since they were built: by the
# release (a tarball from the Docker image records them) or by an earlier
# run of this script (scripts/build-fingerprint).
function built_already {
    sudo -u $TIPPR_USER PYTHON="$TIPPR_VENV/bin/python" \
        bash "$TIPPR_SRC/tippr/scripts/build-fingerprint" "$TIPPR_SRC" "$1" check 2>/dev/null
}

function record_built {
    sudo -u $TIPPR_USER PYTHON="$TIPPR_VENV/bin/python" \
        bash "$TIPPR_SRC/tippr/scripts/build-fingerprint" "$TIPPR_SRC" "$1" record || true
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
update_i18n_repo
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

# Media storage (install.cfg, docs/STORAGE.md): remembered like the secrets,
# so a re-run without them keeps the site on the same storage
function default_media_storage { echo filesystem; }
tippr_secret TIPPR_MEDIA_STORAGE default_media_storage
for setting in TIPPR_S3_ENDPOINT TIPPR_S3_REGION TIPPR_S3_KEY_ID TIPPR_S3_SECRET \
        TIPPR_S3_MEDIA_BUCKET TIPPR_S3_UPLOADS_BUCKET TIPPR_S3_USE_ACLS \
        TIPPR_MEDIA_ORIGIN TIPPR_MEDIA_ORIGIN_HOST; do
    tippr_secret $setting true
done
case "$TIPPR_MEDIA_STORAGE" in
    filesystem) ;;
    s3)
        if [ -z "$TIPPR_S3_MEDIA_BUCKET" ]; then
            echo "ERROR: TIPPR_MEDIA_STORAGE=s3 needs TIPPR_S3_MEDIA_BUCKET" >&2
            exit 1
        fi
        TIPPR_S3_UPLOADS_BUCKET=${TIPPR_S3_UPLOADS_BUCKET:-$TIPPR_S3_MEDIA_BUCKET}
        if [ -z "$TIPPR_MEDIA_ORIGIN" ]; then
            if [ -n "$TIPPR_S3_ENDPOINT" ]; then
                TIPPR_MEDIA_ORIGIN="${TIPPR_S3_ENDPOINT%/}/$TIPPR_S3_MEDIA_BUCKET/"
            else
                TIPPR_MEDIA_ORIGIN="https://$TIPPR_S3_MEDIA_BUCKET.s3.amazonaws.com/"
            fi
        fi
        ;;
    *)
        echo "ERROR: TIPPR_MEDIA_STORAGE is filesystem or s3, not '$TIPPR_MEDIA_STORAGE'" >&2
        exit 1
        ;;
esac
# split over servers: media one server writes (thumbnails, uploads) must be
# there for the others to serve
if [ "$TIPPR_ROLE" != "all" ] && [ "$TIPPR_MEDIA_STORAGE" != "s3" ]; then
    echo "ERROR: TIPPR_ROLE=$TIPPR_ROLE needs media in object storage (TIPPR_MEDIA_STORAGE=s3, docs/STORAGE.md), which every server reaches" >&2
    exit 1
fi

# this server's role and addresses (decided above)
tippr_secret TIPPR_ROLE true
tippr_secret TIPPR_BACKEND_LISTEN true
tippr_secret TIPPR_FRONTEND_ALLOW true
tippr_secret TIPPR_BACKEND_HOST true

# memcached (install.cfg): remembered like the storage settings. A backend
# also listens on the address its frontends reach it on (it can't be just
# localhost, as an all-in-one install's was); a frontend uses the backend's.
function default_memcached_mb { echo auto; }
function default_memcached_server { echo "$SERVICE_HOST:11211"; }
function default_memcached_listen { echo 127.0.0.1; }
case "$TIPPR_ROLE" in
    backend)
        TIPPR_MEMCACHED_LISTEN=${TIPPR_MEMCACHED_LISTEN:-$(remembered TIPPR_MEMCACHED_LISTEN)}
        case "$TIPPR_MEMCACHED_LISTEN" in
            ""|127.0.0.1|localhost)
                TIPPR_MEMCACHED_LISTEN="127.0.0.1,$TIPPR_BACKEND_LISTEN" ;;
        esac
        TIPPR_MEMCACHED_ALLOW=${TIPPR_MEMCACHED_ALLOW:-$TIPPR_FRONTEND_ALLOW}
        ;;
    frontend)
        TIPPR_MEMCACHED_SERVER=${TIPPR_MEMCACHED_SERVER:-$(remembered TIPPR_MEMCACHED_SERVER)}
        case "$TIPPR_MEMCACHED_SERVER" in
            ""|127.0.0.1:*|localhost:*)
                TIPPR_MEMCACHED_SERVER="$TIPPR_BACKEND_HOST:11211" ;;
        esac
        ;;
esac
tippr_secret TIPPR_MEMCACHED_MB default_memcached_mb
tippr_secret TIPPR_MEMCACHED_SERVER default_memcached_server
tippr_secret TIPPR_MEMCACHED_LISTEN default_memcached_listen
tippr_secret TIPPR_MEMCACHED_ALLOW true
# this server's name on /admin/servers (its host name unless set)
tippr_secret TIPPR_SERVER_NAME true
# the account AutoModerator acts as ("off": no AutoModerator)
function default_automoderator_name { echo AutoModerator; }
tippr_secret TIPPR_AUTOMODERATOR_NAME default_automoderator_name
function default_page_cache_seconds { echo 30; }
# updating from /admin/servers (scripts/tippr_update.py)
function default_web_updates { echo 1; }
function default_release_repo { echo TechIdiots-LLC/tippr; }
tippr_secret TIPPR_WEB_UPDATES default_web_updates
tippr_secret TIPPR_RELEASE_REPO default_release_repo
# where tippr-monitor sends alerts ("off" for none)
tippr_secret TIPPR_ALERT_WEBHOOK true
tippr_secret TIPPR_ALERT_COMMAND true
# the daily backup and its off-site copy (docs/BACKUP.md); "off" clears one
function default_backup_schedule { echo daily; }
function default_backup_keep { echo 7; }
tippr_secret TIPPR_BACKUP_SCHEDULE default_backup_schedule
tippr_secret TIPPR_BACKUP_KEEP default_backup_keep
for setting in TIPPR_BACKUP_S3_BUCKET TIPPR_BACKUP_S3_PREFIX TIPPR_BACKUP_S3_KEEP \
        TIPPR_BACKUP_S3_ENDPOINT TIPPR_BACKUP_S3_REGION TIPPR_BACKUP_S3_KEY_ID \
        TIPPR_BACKUP_S3_SECRET; do
    tippr_secret $setting true
done
if ! [[ "$TIPPR_BACKUP_SCHEDULE" =~ ^(daily|off)$ ]]; then
    echo "ERROR: TIPPR_BACKUP_SCHEDULE is daily or off, not '$TIPPR_BACKUP_SCHEDULE'" >&2
    exit 1
fi
if ! [[ "$TIPPR_WEB_UPDATES" =~ ^[01]$ ]]; then
    echo "ERROR: TIPPR_WEB_UPDATES is 1 or 0, not '$TIPPR_WEB_UPDATES'" >&2
    exit 1
fi
if ! [[ "$TIPPR_RELEASE_REPO" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
    echo "ERROR: TIPPR_RELEASE_REPO is a GitHub owner/name, not '$TIPPR_RELEASE_REPO'" >&2
    exit 1
fi
tippr_secret TIPPR_PAGE_CACHE_SECONDS default_page_cache_seconds
if ! [[ "$TIPPR_PAGE_CACHE_SECONDS" =~ ^[0-9]+$ ]]; then
    echo "ERROR: TIPPR_PAGE_CACHE_SECONDS is a number of seconds (0: off), not '$TIPPR_PAGE_CACHE_SECONDS'" >&2
    exit 1
fi
if ! [[ "$TIPPR_MEMCACHED_MB" =~ ^(auto|[0-9]+)$ ]]; then
    echo "ERROR: TIPPR_MEMCACHED_MB is auto or a number of megabytes, not '$TIPPR_MEMCACHED_MB'" >&2
    exit 1
fi
if ! [[ "$TIPPR_MEMCACHED_SERVER" =~ ^[A-Za-z0-9.:_-]+:[0-9]+$ ]]; then
    echo "ERROR: TIPPR_MEMCACHED_SERVER is host:port, not '$TIPPR_MEMCACHED_SERVER'" >&2
    exit 1
fi
case "$TIPPR_MEMCACHED_LISTEN" in
    127.0.0.1|localhost|::1) ;;
    *)
        # memcached has no password: only open it to the frontends' range
        if [ -z "$TIPPR_MEMCACHED_ALLOW" ]; then
            echo "ERROR: TIPPR_MEMCACHED_LISTEN=$TIPPR_MEMCACHED_LISTEN needs TIPPR_MEMCACHED_ALLOW (the frontends' address range): memcached has no password" >&2
            exit 1
        fi
        ;;
esac
SIGNING_SECRETS="SECRET FEEDSECRET ADMINSECRET WEBSOCKET WEBSOCKET_ADMIN MEDIA_EMBED
                 ACTION_NAME EMAIL_NOTIFICATIONS CACHE_POISONING
                 ADSERVER_CLICK_URL_SECRET REQUEST_SIGNATURE_SECRET
                 TRACKING_SECRET"
# a frontend uses the backend's passwords and secrets (cluster.env): new ones
# here would lock it out of the databases and sign what the others reject
if [ "$TIPPR_ROLE" = "frontend" ]; then
    for name in TIPPR_DB_PASSWORD TIPPR_AMQP_PASSWORD TIPPR_ZOOKEEPER_PASSWORD; do
        if [ -z "${!name}" ]; then
            echo "ERROR: $TIPPR_CLUSTER_FILE has no $name: copy it again from the backend" >&2
            exit 1
        fi
    done
    for secret in $SIGNING_SECRETS; do
        name="TIPPR_SECRET_${secret}"
        if [ -z "${!name}" ]; then
            echo "ERROR: $TIPPR_CLUSTER_FILE has no $name: copy it again from the backend" >&2
            exit 1
        fi
    done
fi
tippr_secret TIPPR_AMQP_PASSWORD random_password
tippr_secret TIPPR_ZOOKEEPER_PASSWORD existing_zookeeper_password
tippr_secret TIPPR_ADMIN_PASSWORD random_password
for secret in $SIGNING_SECRETS; do
    tippr_secret "TIPPR_SECRET_${secret}" random_secret
done

# A backend writes what its frontends share with it: its address, the
# passwords and signing secrets, and the settings every server's ini must
# agree on. Copy it to each frontend (same path) before installing there,
# and again after changing one of these here.
if [ "$TIPPR_ROLE" = "backend" ]; then
    install -m 0600 /dev/null "$TIPPR_CLUSTER_FILE"
    {
        echo "# Generated by install/tippr.sh on the backend ($(hostname)):"
        echo "# copy to each frontend's $TIPPR_CLUSTER_FILE (docs/SERVERS.md)."
        echo "TIPPR_BACKEND_HOST=$TIPPR_BACKEND_LISTEN"
        for name in TIPPR_DOMAIN TIPPR_DB_PASSWORD TIPPR_AMQP_PASSWORD \
                TIPPR_ZOOKEEPER_PASSWORD TIPPR_SEARCH TIPPR_ENVIRONMENT \
                TIPPR_MEDIA_STORAGE TIPPR_S3_ENDPOINT TIPPR_S3_REGION \
                TIPPR_S3_KEY_ID TIPPR_S3_SECRET TIPPR_S3_MEDIA_BUCKET \
                TIPPR_S3_UPLOADS_BUCKET TIPPR_S3_USE_ACLS TIPPR_MEDIA_ORIGIN \
                TIPPR_MEDIA_ORIGIN_HOST TIPPR_AUTOMODERATOR_NAME \
                TIPPR_PAGE_CACHE_SECONDS TIPPR_WEB_UPDATES TIPPR_RELEASE_REPO \
                TIPPR_SITE_NAME TIPPR_SITE_DESCRIPTION TIPPR_CONTACT_EMAIL; do
            [ -n "${!name}" ] && echo "${name}=${!name}"
        done
        for secret in $SIGNING_SECRETS; do
            name="TIPPR_SECRET_${secret}"
            echo "${name}=${!name}"
        done
    } > "$TIPPR_CLUSTER_FILE"
fi

# psql and scripts/compute_time_listings read the database password from
# here. The entries are for the database role, tippr (setup_postgres.sh,
# db_user), which is the Linux user's name only when TIPPR_USER is tippr.
cat > "$TIPPR_HOME/.pgpass" <<PGPASS
localhost:5432:*:tippr:${TIPPR_DB_PASSWORD}
127.0.0.1:5432:*:tippr:${TIPPR_DB_PASSWORD}
${SERVICE_HOST}:5432:*:tippr:${TIPPR_DB_PASSWORD}
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

amqp.endpoint = ${SERVICE_HOST}:5672
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

# the databases, cache and queue: not on a frontend, which uses its backend's
if [ "$TIPPR_ROLE" != "frontend" ]; then
    # Configure Cassandra
    $RUNDIR/setup_cassandra.sh

    # Configure PostgreSQL
    $RUNDIR/setup_postgres.sh

    # memcached's memory and address (TIPPR_MEMCACHED_*, install.cfg). Ubuntu's
    # default is 64 MB, small for a busy site.
    if [ -f /etc/memcached.conf ]; then
        if [ "$TIPPR_MEMCACHED_MB" = "auto" ]; then
            memcached_mb=$(( $(awk '/^MemTotal:/ {print int($2 / 1024)}' /proc/meminfo) / 4 ))
            [ "$memcached_mb" -lt 64 ] && memcached_mb=64
            [ "$memcached_mb" -gt 1024 ] && memcached_mb=1024
        else
            memcached_mb=$TIPPR_MEMCACHED_MB
        fi
        memcached_before=$(md5sum < /etc/memcached.conf)
        sed -i -E "s/^-m [0-9]+/-m $memcached_mb/" /etc/memcached.conf
        grep -qE '^-m ' /etc/memcached.conf || echo "-m $memcached_mb" >> /etc/memcached.conf
        # one -l line: this server only, or the address frontends reach it on
        sed -i -E '/^-l /d' /etc/memcached.conf
        if [ "$TIPPR_MEMCACHED_LISTEN" = "localhost" ] || [ "$TIPPR_MEMCACHED_LISTEN" = "127.0.0.1" ]; then
            echo "-l 127.0.0.1" >> /etc/memcached.conf
        else
            echo "-l $TIPPR_MEMCACHED_LISTEN" >> /etc/memcached.conf
        fi
        if [ "$(md5sum < /etc/memcached.conf)" != "$memcached_before" ]; then
            echo "memcached: ${memcached_mb} MB, listening on $TIPPR_MEMCACHED_LISTEN"
            systemctl restart memcached || true
        fi
    fi

    # Configure mcrouter (optional; see TIPPR_BUILD_MCROUTER in install.cfg)
    if [ "$TIPPR_BUILD_MCROUTER" = "1" ]; then
        $RUNDIR/setup_mcrouter.sh
    else
        echo "Skipping mcrouter build (TIPPR_BUILD_MCROUTER=$TIPPR_BUILD_MCROUTER); r2 uses memcached directly."
    fi

    # Configure RabbitMQ
    $RUNDIR/setup_rabbitmq.sh
else
    # a frontend made from the Proxmox template (or once an all-in-one
    # install) has them installed: stop them, so they take no memory.
    # (Cassandra's and ZooKeeper's are init scripts, for which disable
    # --now only disables: stop first. Ones not installed just fail.)
    for unit in cassandra zookeeper postgresql rabbitmq-server memcached \
            redis-server opensearch; do
        systemctl stop "$unit.service" >/dev/null 2>&1 || true
        systemctl disable "$unit.service" >/dev/null 2>&1 || true
    done
fi

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

# Now upgrade pip/setuptools/wheel and packaging (nothing tippr runs needs
# setuptools' pkg_resources any more, so any version does; the list below
# pins the one tested)
sudo -u $TIPPR_USER "$BOOT_PY" -m pip install --upgrade pip setuptools wheel
# (not --upgrade: install/requirements.txt pins the version below)
sudo -u $TIPPR_USER "$BOOT_PY" -m pip install 'packaging>=23.1'

# The Python packages, at the versions the release was built and tested
# with: install/requirements.txt, the list the Docker image installs too.
# It's a complete freeze, installed as listed (--no-deps) in one go: pip's
# resolver would reject it (some packages declare an older `packaging` than
# the others need), and installing packages one group at a time let each
# install pull in whatever versions were newest that day. Upgrades skip it
# when this venv has installed the same list (scripts/build-fingerprint).
if built_already requirements; then
    echo "Python packages: already installed from this list"
else
    # psycopg2 is built from source (libpq-dev); earlier installs had the
    # binary wheel too, which provides the same module, so removing it
    # removes psycopg2's files: both go, and the list installs psycopg2 again
    if sudo -u $TIPPR_USER $TIPPR_VENV/bin/pip show psycopg2-binary >/dev/null 2>&1; then
        sudo -u $TIPPR_USER $TIPPR_VENV/bin/pip uninstall -y psycopg2-binary psycopg2 || true
    fi
    # The ones pinned to a URL (tippr's baseplate fork, at a fixed commit)
    # are reinstalled whatever is there: pip keeps an installed package of
    # the same name and version, even one from elsewhere.
    url_pinned=$(mktemp)
    grep -E '^[A-Za-z0-9_.-]+ @ ' "$TIPPR_SRC/tippr/install/requirements.txt" > "$url_pinned"
    chmod a+r "$url_pinned"
    if sudo -u $TIPPR_USER $TIPPR_VENV/bin/pip install --no-deps \
            -r "$TIPPR_SRC/tippr/install/requirements.txt" &&
       sudo -u $TIPPR_USER $TIPPR_VENV/bin/pip install --no-deps --force-reinstall \
            -r "$url_pinned"; then
        rm -f "$url_pinned"
        # and the packages that left the list (requirements-retired.txt),
        # which installing it doesn't remove
        retired=$(grep -vE '^\s*(#|$)' "$TIPPR_SRC/tippr/install/requirements-retired.txt" 2>/dev/null |
                  while read -r name; do
                      # (an if, so a package that isn't there doesn't end
                      # the loop, and with set -e the installer, with an error)
                      if sudo -u $TIPPR_USER $TIPPR_VENV/bin/pip show -q "$name" >/dev/null 2>&1; then
                          echo "$name"
                      fi
                  done)
        if [ -n "$retired" ]; then
            echo "Python packages no longer used, removing: $(echo $retired)"
            sudo -u $TIPPR_USER $TIPPR_VENV/bin/pip uninstall -y $retired || true
        fi
        record_built requirements
    else
        rm -f "$url_pinned"
        echo "ERROR: the Python packages didn't install (see above)" >&2
        exit 1
    fi
fi

# Another baseplate on top, to work on one
# (install.cfg): a checkout at $TIPPR_SRC/tippr-baseplate.py (editable), or
# a pip requirement
if [ -d "$TIPPR_SRC/tippr-baseplate.py" ]; then
    echo "Installing local baseplate from $TIPPR_SRC/tippr-baseplate.py"
    sudo -u $TIPPR_USER $TIPPR_VENV/bin/pip install --no-deps -e "$TIPPR_SRC/tippr-baseplate.py"
elif [ -n "$TIPPR_BASEPLATE_PIP_URL" ]; then
    echo "Installing baseplate from $TIPPR_BASEPLATE_PIP_URL"
    sudo -u $TIPPR_USER $TIPPR_VENV/bin/pip install --no-deps "$TIPPR_BASEPLATE_PIP_URL"
fi

# Create a writable directory for Prometheus multiprocess mode if needed
# and make it owned by the tippr user so prometheus-client can write there.
PROMETHEUS_DIR=/var/lib/tippr/prometheus-multiproc
if [ ! -d "$PROMETHEUS_DIR" ]; then
    mkdir -p "$PROMETHEUS_DIR"
    chown $TIPPR_USER:$TIPPR_GROUP "$PROMETHEUS_DIR"
    chmod 0775 "$PROMETHEUS_DIR"
fi

function install_tippr_repo {
    # r2's install builds its Cython extensions again (half a minute): not
    # when this venv has it installed from the same packaging and modules
    if [ "$1" = tippr/r2 ] && built_already r2; then
        echo "r2: already installed in $TIPPR_VENV for this code"
        return
    fi
    pushd $TIPPR_SRC/$1
    # a build toolchain metadata generation works with (already there from
    # install/requirements.txt, so normally nothing to do)
    sudo -u $TIPPR_USER $TIPPR_VENV/bin/pip install --no-deps setuptools wheel 'packaging>=23.1' || true

    sudo -u $TIPPR_USER $TIPPR_VENV/bin/python setup.py build
    # --no-build-isolation uses the venv's packages (like baseplate) instead
    # of isolated env; --no-deps, as the Docker image does: its dependencies
    # are install/requirements.txt's, at the versions tested together
    local installed=0
    sudo -u $TIPPR_USER $TIPPR_VENV/bin/pip install --no-build-isolation --no-deps -e . && installed=1
    popd
    if [ "$1" = tippr/r2 ] && [ "$installed" = 1 ]; then
        record_built r2
    fi
}

install_tippr_repo tippr/r2

# Check that every package r2 needs is there at a version it accepts, so a
# mismatch fails the install (and an update rolls back) rather than the
# queues and jobs failing later
if ! sudo -u $TIPPR_USER $TIPPR_VENV/bin/python \
        $TIPPR_SRC/tippr/scripts/check_requirements.py r2; then
    echo "ERROR: the Python packages don't fit together (see above); the queues and jobs wouldn't start" >&2
    exit 1
fi
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
    # Use venv's python for make commands. -k keeps going past a catalog
    # msgfmt rejects, so one broken language doesn't leave every language
    # after it uncompiled (the site shows those in English).
    if built_already i18n; then
        echo "Translations: already compiled for these catalogs"
    elif sudo -u $TIPPR_USER PATH="$TIPPR_VENV/bin:$PATH" make -k -C $TIPPR_SRC/i18n clean all; then
        record_built i18n
    else
        echo "WARNING: some translations failed to compile (see above); those languages show in English"
    fi
else
    echo "Skipping i18n message compilation because i18n package was not installed"
fi

# this builds static files and should be run *after* languages are installed
# so that the proper language-specific static files can be generated and after
# plugins are installed so all the static files are available.
pushd $TIPPR_SRC/tippr/r2
# Use venv's python for make commands. From scratch (clean): make goes by
# file dates, and a module whose .pyx is older than an old build is missed.
if built_already pyx; then
    echo "Cython modules: already built for this code"
else
    sudo -u $TIPPR_USER PATH="$TIPPR_VENV/bin:$PATH" PYTHONPATH="$TIPPR_SRC/tippr:$TIPPR_SRC" make clean pyx
    record_built pyx
fi

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
media_fs_base_url_http = https://%(domain)s/media/

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
    # uploaded media (thumbnails, previews) over https, as the site is: an
    # http address is mixed content on its https pages
    sed -i "s@^media_fs_base_url_http = http://@media_fs_base_url_http = https://@" $TIPPR_SRC/tippr/r2/development.update
fi

# Generated passwords and signing secrets. "make ini" merges this file over
# development.update, so local edits to development.update never collide
# with the generated values. It is rewritten from $TIPPR_SECRETS_FILE on
# every install; '%' is doubled because PasteDeploy interpolates the ini.
# Settings that follow TIPPR_ENVIRONMENT. In production the debug flag must be
# off: its error pages allow remote code execution.
# Every request reaches r2 through the local nginx, which sets
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

# Media storage (r2.lib.object_storage): the S3 connection whenever one is
# given (ad image uploads use it even with filesystem media), and the s3
# media provider when TIPPR_MEDIA_STORAGE=s3
function storage_settings {
    if [ -n "$TIPPR_S3_ENDPOINT$TIPPR_S3_KEY_ID$TIPPR_S3_UPLOADS_BUCKET" ] || \
            [ "$TIPPR_MEDIA_STORAGE" = "s3" ]; then
        [ -n "$TIPPR_S3_KEY_ID" ] && echo "S3KEY_ID = $(ini_value "$TIPPR_S3_KEY_ID")"
        [ -n "$TIPPR_S3_SECRET" ] && echo "S3SECRET_KEY = $(ini_value "$TIPPR_S3_SECRET")"
        if [ -n "$TIPPR_S3_ENDPOINT" ]; then
            echo "s3_endpoint_url = $(ini_value "$TIPPR_S3_ENDPOINT")"
            # browsers reach the service through this site (nginx /s3/)
            echo "s3_browser_endpoint_url = https://$TIPPR_DOMAIN/s3"
        fi
        [ -n "$TIPPR_S3_REGION" ] && echo "s3_region = $(ini_value "$TIPPR_S3_REGION")"
        [ -n "$TIPPR_S3_USE_ACLS" ] && echo "s3_use_acls = $TIPPR_S3_USE_ACLS"
        [ -n "$TIPPR_S3_UPLOADS_BUCKET" ] && echo "s3_client_uploads_bucket = $TIPPR_S3_UPLOADS_BUCKET"
    fi
    if [ "$TIPPR_MEDIA_STORAGE" = "s3" ]; then
        echo "media_provider = s3"
        echo "s3_media_buckets = $TIPPR_S3_MEDIA_BUCKET"
        echo "s3_image_buckets = $TIPPR_S3_MEDIA_BUCKET"
        # the same addresses as before: nginx passes /media/ to the bucket
        echo "s3_public_url = https://$TIPPR_DOMAIN/media"
    fi
    true
}
# the daily backups kept, and the bucket they're copied to (tippr_backup.py's
# Offsite); "off" leaves a setting out
function backup_settings {
    local name key value
    echo "backup_keep = $TIPPR_BACKUP_KEEP"
    for name in BUCKET:backup_s3_bucket PREFIX:backup_s3_prefix KEEP:backup_s3_keep \
            ENDPOINT:backup_s3_endpoint_url REGION:backup_s3_region \
            KEY_ID:backup_s3_key_id SECRET:backup_s3_secret; do
        key="TIPPR_BACKUP_S3_${name%%:*}"
        value=${!key}
        [ -n "$value" ] && [ "$value" != off ] && echo "${name#*:} = $(ini_value "$value")"
    done
    true
}
# where a frontend finds its backend's databases, Cassandra, queue,
# ZooKeeper, search and activity counts (TIPPR_ROLE=frontend); one server
# keeps example.ini's local addresses
function service_settings {
    [ "$SERVICE_HOST" = "127.0.0.1" ] && return 0
    local db
    for db in main comment comment2 email authorize award hc traffic; do
        echo "${db}_db = tippr, $SERVICE_HOST, *, *, *, *, *"
    done
    echo "cassandra_seeds = $SERVICE_HOST:9042"
    echo "amqp_host = $SERVICE_HOST:5672"
    echo "zookeeper_connection_string = $SERVICE_HOST:2181"
    echo "opensearch_url = http://$SERVICE_HOST:9200"
    echo "activity_endpoint = $SERVICE_HOST:9002"
}

# the memcached the site uses (TIPPR_MEMCACHED_SERVER): with several
# frontends, the same one for all, so what one writes the others see
function cache_settings {
    echo "lockcaches = $TIPPR_MEMCACHED_SERVER"
    echo "permacache_memcaches = $TIPPR_MEMCACHED_SERVER"
    echo "hardcache_memcaches = $TIPPR_MEMCACHED_SERVER"
    echo "mcrouter_addr = $TIPPR_MEMCACHED_SERVER"
    # the account AutoModerator acts as (r2.lib.automoderator)
    if [ "$TIPPR_AUTOMODERATOR_NAME" != "off" ]; then
        echo "automoderator_account = $TIPPR_AUTOMODERATOR_NAME"
    else
        echo "automoderator_account ="
    fi
    # this server's name on /admin/servers (r2.lib.server_status), and what
    # it does there (all, backend or frontend; docs/SERVERS.md)
    if [ -n "$TIPPR_SERVER_NAME" ]; then
        echo "server_name = $TIPPR_SERVER_NAME"
    fi
    echo "server_role = $TIPPR_ROLE"
    # where /admin/servers looks for releases, and whether it can update
    # (r2.lib.releases, r2.lib.server_update)
    echo "release_repo = $TIPPR_RELEASE_REPO"
    echo "web_updates = $([ "$TIPPR_WEB_UPDATES" = "1" ] && echo true || echo false)"
    # what nginx caches, for /admin/config to show (r2.lib.cache_status)
    if [ "$TIPPR_PAGE_CACHE_SECONDS" != "0" ]; then
        echo "nginx_page_cache = true"
    else
        echo "nginx_page_cache = false"
    fi
    if [ "$TIPPR_ENVIRONMENT" = "production" ]; then
        echo "nginx_static = true"
    else
        echo "nginx_static = false"
    fi
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
$(storage_settings)
$(backup_settings)
$(cache_settings)
$(service_settings)

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
request_signature_secret = $TIPPR_SECRET_REQUEST_SIGNATURE_SECRET

# Live settings' starting values (/admin/config can change them): logged-out
# pages nginx (or a CDN) may keep (TIPPR_PAGE_CACHE_SECONDS)
[live_config]
logged_out_page_cache_seconds = $TIPPR_PAGE_CACHE_SECONDS

# Installer-managed: nginx is the only client of the app server.
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
    if built_already static; then
        echo "Static files: already built for this code and these translations"
    else
        # Rebuild from scratch: outputs from an earlier failed build (e.g.
        # empty CSS) would otherwise look up to date.
        sudo -u $TIPPR_USER PYTHONPATH="$TIPPR_SRC/tippr:$TIPPR_SRC/tippr/r2" \
            PATH="$TIPPR_VENV/bin:/usr/bin:/bin" make clean_static
        # make can miss files that the same run copies into build/, so a
        # first build on a clean tree may need a second pass.
        make_static || make_static
        # fail the install rather than serve empty stylesheets
        if [ ! -s "$(readlink -f build/public/static/tippr.css)" ]; then
            echo "ERROR: the static build produced an empty tippr.css" >&2
            exit 1
        fi
        record_built static
    fi
    # nginx serves them from /srv/www/static (snippets/tippr-static.conf),
    # where it can read them. New files are added and old ones kept: with
    # several frontends upgraded one at a time, a page from one not yet
    # upgraded still finds its (differently named) files. Ones the build no
    # longer makes go after 60 days.
    install -d -o $TIPPR_USER -g $TIPPR_GROUP -m 0755 /srv/www/static
    cp -a build/public/static/. /srv/www/static/
    find /srv/www/static -type f -mtime +60 -print | while read -r f; do
        [ -e "build/public/static/${f#/srv/www/static/}" ] || rm -f "$f"
    done
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

# The Python script behind tippr-run (r2.commands, which the jobs and queue
# processors run too)
cat > $TIPPR_VENV/bin/tippr-run-cmd <<PYCMD
#!/usr/bin/env python3
"""tippr-run: r2.commands with the repo's own packages first."""
import sys
import os

# Add tippr repo root to Python path for local shims (e.g., pylons)
# This must come before site-packages so local shims take precedence
tippr_root = '$TIPPR_SRC/tippr'
r2_dir = tippr_root + '/r2'
sys.path.insert(0, tippr_root)
sys.path.insert(0, r2_dir)
os.chdir(r2_dir)

from r2.commands import main
# Args: config file + any additional args
main(sys.argv[1:])
PYCMD
chmod +x $TIPPR_VENV/bin/tippr-run-cmd

helper-script /usr/local/bin/tippr-run <<TIPPRRUN
#!/bin/bash
# A script or Python code with the app loaded (r2.commands). Run as root, it switches to
# $TIPPR_USER (keeping the environment, e.g. FEEDS_ADD=1): files it writes,
# such as compiled templates and media, must belong to the user the site
# runs as.
if [ "\$(id -u)" = 0 ] && [ "$TIPPR_USER" != root ]; then
    exec sudo -E -u $TIPPR_USER -- "\$0" "\$@"
fi
cd $TIPPR_SRC/tippr/r2
exec $TIPPR_VENV/bin/python $TIPPR_VENV/bin/tippr-run-cmd run.ini "\$@"
TIPPRRUN

helper-script /usr/local/bin/tippr-shell <<TIPPRSHELL
#!/bin/bash
# A Python prompt with the app loaded (tippr-run, then the prompt)
exec /usr/local/bin/tippr-run --shell "\$@"
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
# members' own data exports (/prefs/privacy), written by the
# privacy_export_q consumer
install -d -m 0700 -o $TIPPR_USER /var/lib/tippr/privacy_exports
helper-script /usr/local/bin/tippr-backup <<TIPPRBACKUP
#!/bin/bash
# usage: sudo tippr-backup export|list|import|restore ... (--help)
exec $TIPPR_VENV/bin/python $TIPPR_SRC/tippr/scripts/tippr_backup.py --ini $TIPPR_SRC/tippr/r2/run.ini "\$@"
TIPPRBACKUP

# Updates from /admin/servers (docs/PROXMOX.md): the page asks through
# ZooKeeper, and tippr-update.timer runs root's own copy of the updater with
# the system Python, reading its settings from root's updates.conf, so the
# site's user can't change what runs as root or where it downloads from.
if [ "$TIPPR_WEB_UPDATES" = "1" ]; then
    apt-get install $APTITUDE_OPTIONS python3-kazoo ||         echo "Note: python3-kazoo didn't install; updates from /admin/servers won't run"
    install -m 0755 -o root -g root $TIPPR_SRC/tippr/scripts/tippr_update.py /usr/local/sbin/tippr-update
    install -d -m 0755 -o root -g root /etc/tippr
    install -d -m 0700 -o root -g root /var/lib/tippr/updates
    cat > /etc/tippr/updates.conf <<UPDATESCONF
# Generated by install/tippr.sh (TIPPR_WEB_UPDATES, TIPPR_RELEASE_REPO):
# read by /usr/local/sbin/tippr-update, which runs as root
TIPPR_WEB_UPDATES=1
TIPPR_RELEASE_REPO=$TIPPR_RELEASE_REPO
TIPPR_USER=$TIPPR_USER
TIPPR_SRC=$TIPPR_SRC
TIPPR_INI=$TIPPR_SRC/tippr/r2/run.ini
# all, backend or frontend: how it checks the site came back
TIPPR_ROLE=$TIPPR_ROLE
UPDATESCONF
    chown root:root /etc/tippr/updates.conf
    chmod 0644 /etc/tippr/updates.conf
else
    rm -f /etc/tippr/updates.conf /usr/local/sbin/tippr-update
fi

# Alerts (tippr-monitor.timer, install.cfg's TIPPR_ALERT_*): it runs as root,
# so from root's own copies of the monitor and the smoke check, like the
# updater, which the site's user can't change.
install -m 0755 -o root -g root $TIPPR_SRC/tippr/scripts/tippr_monitor.py /usr/local/sbin/tippr-monitor
install -m 0755 -o root -g root $TIPPR_SRC/tippr/scripts/smoke_check.sh /usr/local/sbin/tippr-smoke-check
install -d -m 0755 -o root -g root /etc/tippr /var/lib/tippr
alert_setting() { [ "$1" = off ] || printf '%s' "$1"; }
install -m 0600 -o root -g root /dev/null /etc/tippr/alerts.conf
cat > /etc/tippr/alerts.conf <<ALERTSCONF
# Generated by install/tippr.sh (install.cfg's TIPPR_ALERT_*): where
# /usr/local/sbin/tippr-monitor (tippr-monitor.timer) sends alerts
TIPPR_ALERT_WEBHOOK=$(alert_setting "$TIPPR_ALERT_WEBHOOK")
TIPPR_ALERT_COMMAND=$(alert_setting "$TIPPR_ALERT_COMMAND")
# TIPPR_ALERT_REPEAT_HOURS=6
ALERTSCONF

helper-script /usr/local/bin/tippr-serve <<TIPPRSERVE
#!/bin/bash
cd $TIPPR_SRC/tippr/r2
export PYTHONPATH="$TIPPR_SRC/tippr:$TIPPR_SRC:\$PYTHONPATH"
# the address tippr-paster.service uses (stop it first), for nginx
exec $TIPPR_VENV/bin/gunicorn --paste run.ini --bind 127.0.0.1:8001 --reload
TIPPRSERVE

# The web app (gunicorn, tippr-paster.service); not on a backend: its
# frontends serve the pages
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    if [ "$TIPPR_ROLE" = "backend" ]; then
        systemctl disable --now tippr-paster.service 2>/dev/null || true
    else
        systemctl enable --now tippr-paster.service || true
    fi
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

# Clicks on sponsored posts (/click) are the site's own now
# (r2.controllers.redirect, r2.lib.ad_traffic): take reddit's separate
# click server off installs that had it
if [ -e /etc/systemd/system/gunicorn-click.service ]; then
    systemctl disable --now gunicorn-click.service 2>/dev/null || true
    rm -f /etc/systemd/system/gunicorn-click.service
    systemctl daemon-reload || true
fi
rm -f /etc/gunicorn.d/click.conf /var/opt/tippr/click.sock

###############################################################################
# nginx
###############################################################################
# nginx is the only web server in front of the app. It routes websocket
# upgrades to the websockets service, serves media and the tracking pixel
# from disk, passes /click to the click tracker and everything else to
# gunicorn (which it shields from slow clients).
#
# Standalone (the default): HTTPS on 443; port 80 redirects to it and
# answers Let's Encrypt's challenges.
# TIPPR_EXTERNAL_PROXY="ADDRESS ...": behind another proxy that does TLS
# (e.g. HAProxy on OPNsense or pfSense): plain HTTP on port 80, no certificate here, and
# the client address taken from X-Forwarded-For on connections from those
# addresses only.

mkdir -p /srv/www/media
chown $TIPPR_USER:$TIPPR_GROUP /srv/www/media
mkdir -p /var/log/nginx/traffic
install -d -m 0755 /var/www/letsencrypt

# Earlier installs had haproxy in front of nginx on port 80/8080, and
# separate nginx sites; nginx now does it all
if systemctl list-unit-files haproxy.service >/dev/null 2>&1; then
    systemctl disable --now haproxy.service 2>/dev/null || true
fi
rm -f /etc/nginx/sites-enabled/default \
      /etc/nginx/sites-enabled/tippr-media /etc/nginx/sites-available/tippr-media \
      /etc/nginx/sites-enabled/tippr-pixel /etc/nginx/sites-available/tippr-pixel \
      /etc/nginx/sites-enabled/tippr-ssl /etc/nginx/sites-available/tippr-ssl \
      /etc/nginx/sites-enabled/tippr-acme /etc/nginx/sites-available/tippr-acme \
      /etc/nginx/conf.d/tippr-cloudflare.conf

# The pixel log's format (http context)
cat > /etc/nginx/conf.d/tippr-log.conf <<'LOGCONF'
log_format directlog '$remote_addr - $remote_user [$time_local] '
                   '"$request_method $request_uri $server_protocol" $status $body_bytes_sent '
                   '"$http_referer" "$http_user_agent"';
LOGCONF

# Routing (http context): websocket upgrades go to the websockets service
cat > /etc/nginx/conf.d/tippr-upstreams.conf <<'UPSTREAMS'
# Generated by install/tippr.sh
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
map $http_upgrade $tippr_upstream {
    default        127.0.0.1:8001;
    ~*^websocket$  127.0.0.1:9001;
}
# behind an external proxy that does TLS: requests are https unless it says
map $http_x_forwarded_proto $tippr_external_proto {
    default https;
    http    http;
}
UPSTREAMS

# Where client addresses come from (http context). r2 trusts the
# X-Forwarded-For nginx sets ($remote_addr), so this decides what the rate
# limits, bans and spam checks see.
CF_RANGES=""
if [ "$TIPPR_BEHIND_CLOUDFLARE" = "1" ]; then
    CF_RANGES=$(curl -fsS https://www.cloudflare.com/ips-v4; echo; curl -fsS https://www.cloudflare.com/ips-v6)
    if ! echo "$CF_RANGES" | grep -qE '^[0-9a-f.:]+/[0-9]+$'; then
        echo "ERROR: could not download Cloudflare's IP ranges" >&2
        exit 1
    fi
    CF_RANGES=$(echo "$CF_RANGES" | grep -E '^[0-9a-f.:]+/[0-9]+$')
fi
TIPPR_EXTERNAL_PROXY=$(echo "${TIPPR_EXTERNAL_PROXY:-}" | tr ',' ' ' | xargs)
for proxy in $TIPPR_EXTERNAL_PROXY; do
    if ! echo "$proxy" | grep -qE '^[0-9a-fA-F.:]+(/[0-9]+)?$'; then
        echo "ERROR: TIPPR_EXTERNAL_PROXY: '$proxy' isn't an IP address or range" >&2
        exit 1
    fi
done
{
    echo "# Generated by install/tippr.sh"
    if [ -n "$TIPPR_EXTERNAL_PROXY" ]; then
        # the proxy (and, behind it, Cloudflare) appends to X-Forwarded-For;
        # walk back past the trusted addresses to the client
        for proxy in $TIPPR_EXTERNAL_PROXY $CF_RANGES; do
            echo "set_real_ip_from $proxy;"
        done
        echo "real_ip_header X-Forwarded-For;"
        echo "real_ip_recursive on;"
    elif [ -n "$CF_RANGES" ]; then
        # straight from Cloudflare: its header, on its addresses only
        echo "$CF_RANGES" | sed 's/^/set_real_ip_from /; s/$/;/'
        echo "real_ip_header CF-Connecting-IP;"
    fi
} > /etc/nginx/conf.d/tippr-realip.conf

# What every site server answers ($tippr_proto: https or http, as the
# client used)
install -d -m 0755 /etc/nginx/snippets
# passing a request to the app (the site's pages, and static files nginx
# doesn't have)
cat > /etc/nginx/snippets/tippr-proxy.conf <<'PROXY'
# Generated by install/tippr.sh
proxy_pass http://$tippr_upstream;
proxy_http_version 1.1;
proxy_set_header Host $http_host;
# the real client ($remote_addr after tippr-realip.conf); r2 trusts
# these headers from local proxies
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto $tippr_proto;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection $connection_upgrade;
proxy_pass_header Server;
# websockets stay open; app requests time out in gunicorn (60s)
proxy_read_timeout 1h;
client_max_body_size 10m;
PROXY

# /static/: the CSS, JS and images, from disk in production (copied to
# /srv/www/static after the build). Names with a content hash
# (tippr.cDFoRR5NTrs.css) never change, so browsers and CDNs keep them a
# year; others a day. Files nginx doesn't have go to the app. In
# development the app serves them, as they change.
if [ "$TIPPR_ENVIRONMENT" = "production" ]; then
    cat > /etc/nginx/snippets/tippr-static.conf <<'STATIC'
# Generated by install/tippr.sh
location /static/ {
    root /srv/www;
    access_log off;
    expires 1d;
    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml text/plain;
    try_files $uri @tippr_app;
    location ~ "\.[A-Za-z0-9_-]{11}\.[A-Za-z0-9]+$" {
        expires max;
        try_files $uri @tippr_app;
    }
}
STATIC
else
    echo "# development: the app serves /static/ (install/tippr.sh)" \
        > /etc/nginx/snippets/tippr-static.conf
fi

# Logged-out visitors' pages (TIPPR_PAGE_CACHE_SECONDS): nginx keeps the
# ones the app marks cacheable (X-Accel-Expires) and serves them again until
# they expire, building each at most once at a time (the others wait for
# it), and serving the old copy if the app is down or failing. Not while a
# new copy is built ("updating"): a page that's no longer cacheable never
# replaces the old copy, which was then served forever. Never for logged-in
# visitors (the login cookie) or apps; the cookies that change a logged-out
# page are part of the key, and the browser's language is Vary'd on.
if [ "$TIPPR_PAGE_CACHE_SECONDS" != "0" ]; then
    install -d -o www-data -g www-data -m 0700 /var/cache/nginx/tippr-pages
    # start empty: what an older version kept may be wrong now
    find /var/cache/nginx/tippr-pages -mindepth 1 -delete 2>/dev/null || true
    cat > /etc/nginx/conf.d/tippr-page-cache.conf <<'CACHEPATH'
# Generated by install/tippr.sh
proxy_cache_path /var/cache/nginx/tippr-pages levels=1:2 keys_zone=tippr_pages:20m
                 max_size=1g inactive=10m use_temp_path=off;
CACHEPATH
    cat > /etc/nginx/snippets/tippr-page-cache.conf <<'PAGECACHE'
# Generated by install/tippr.sh
proxy_cache tippr_pages;
proxy_cache_key "$scheme$host$request_uri|$cookie__options|$cookie_over18|$cookie_tippr_mobility";
proxy_cache_bypass $cookie_tippr_session $http_authorization $http_upgrade;
proxy_no_cache $cookie_tippr_session $http_authorization $http_upgrade;
proxy_cache_lock on;
proxy_cache_lock_timeout 5s;
proxy_cache_use_stale error timeout http_500 http_502 http_503 http_504;
PAGECACHE
else
    rm -f /etc/nginx/conf.d/tippr-page-cache.conf
    echo "# off (TIPPR_PAGE_CACHE_SECONDS=0)" > /etc/nginx/snippets/tippr-page-cache.conf
fi

cat > /etc/nginx/snippets/tippr-locations.conf <<'LOCATIONS'
# Generated by install/tippr.sh
location / {
    include snippets/tippr-proxy.conf;
    include snippets/tippr-page-cache.conf;
}

location @tippr_app {
    include snippets/tippr-proxy.conf;
}

# the websockets service (sutro), for live comments (r2.lib.live_comments):
# the path is the namespace a page listens on
location /websocket/ {
    proxy_pass http://127.0.0.1:9001;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 1h;
    proxy_send_timeout 1h;
}

include snippets/tippr-static.conf;

# /media/ (and /s3/, for uploads): snippets/tippr-media.conf, written below
include snippets/tippr-media.conf;

location /pixel/ {
    access_log /var/log/nginx/traffic/traffic.log directlog;
    rewrite ^/pixel/of_ /pixel.png break;
    root /srv/www/pixel/;
    add_header Last-Modified "";
    add_header Pragma "no-cache";
    expires -1;
}

location /.well-known/acme-challenge/ {
    root /var/www/letsencrypt;
    try_files $uri =404;
}
LOCATIONS

# Media: from /srv/www/media, or from the bucket (TIPPR_MEDIA_STORAGE=s3),
# at the same addresses either way. Uploads browsers send to the bucket
# (ad images) go through /s3/ to the S3 service, POSTs only.
{
    echo "# Generated by install/tippr.sh (TIPPR_MEDIA_STORAGE=$TIPPR_MEDIA_STORAGE)"
    if [ "$TIPPR_MEDIA_STORAGE" = "s3" ]; then
        origin_host=${TIPPR_MEDIA_ORIGIN_HOST:-$(echo "$TIPPR_MEDIA_ORIGIN" | sed -E 's#^[a-z]+://([^/]+).*#\1#')}
        cat <<MEDIA
location /media/ {
    proxy_pass ${TIPPR_MEDIA_ORIGIN%/}/;
    proxy_set_header Host $origin_host;
    proxy_set_header Authorization "";
    proxy_hide_header Set-Cookie;
    proxy_hide_header x-amz-request-id;
    proxy_hide_header x-amz-id-2;
    proxy_intercept_errors on;
    expires max;
}
MEDIA
    else
        cat <<'MEDIA'
location /media/ {
    alias /srv/www/media/;
    expires max;
}
MEDIA
    fi
    if [ -n "$TIPPR_S3_ENDPOINT" ]; then
        s3_host=$(echo "$TIPPR_S3_ENDPOINT" | sed -E 's#^[a-z]+://([^/]+).*#\1#')
        cat <<S3
location /s3/ {
    limit_except POST { deny all; }
    client_max_body_size 20m;
    proxy_pass ${TIPPR_S3_ENDPOINT%/}/;
    proxy_set_header Host $s3_host;
}
S3
    fi
} > /etc/nginx/snippets/tippr-media.conf

###############################################################################
# TLS certificate
###############################################################################
# TIPPR_TLS_CERT / TIPPR_TLS_KEY: use those files (e.g. a Cloudflare Origin
# Certificate). TIPPR_LETSENCRYPT_EMAIL: get a certificate from Let's Encrypt
# once nginx is running (see "Let's Encrypt" below). Otherwise, or until
# Let's Encrypt succeeds: a self-signed certificate for the domain, which
# browsers warn about. None of this applies behind an external proxy.
TIPPR_TLS_DIR=/etc/tippr/tls
install -d -m 0755 "$TIPPR_TLS_DIR"
SELF_SIGNED_CERT=$TIPPR_TLS_DIR/self-signed.crt
SELF_SIGNED_KEY=$TIPPR_TLS_DIR/self-signed.key
if [ -z "$TIPPR_EXTERNAL_PROXY" ] && { [ ! -s "$SELF_SIGNED_CERT" ] || \
        ! openssl x509 -in "$SELF_SIGNED_CERT" -noout -checkhost "$TIPPR_DOMAIN" | grep -q 'does match'; }; then
    openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
        -subj "/CN=$TIPPR_DOMAIN" \
        -addext "subjectAltName=DNS:$TIPPR_DOMAIN,DNS:*.$TIPPR_DOMAIN" \
        -keyout "$SELF_SIGNED_KEY" -out "$SELF_SIGNED_CERT"
    chmod 0600 "$SELF_SIGNED_KEY"
fi
LETSENCRYPT_CERT=/etc/letsencrypt/live/$TIPPR_DOMAIN/fullchain.pem
LETSENCRYPT_KEY=/etc/letsencrypt/live/$TIPPR_DOMAIN/privkey.pem

# usage: write_nginx_site [CERT KEY TRUSTED]
# With a certificate: HTTPS on 443, port 80 redirecting to it (TRUSTED=1
# adds HSTS, which must not be sent with a self-signed certificate).
# Without (behind an external proxy): plain HTTP on port 80.
function write_nginx_site {
    if [ -z "$1" ]; then
        cat > /etc/nginx/sites-available/tippr <<'SITE'
# Generated by install/tippr.sh: behind an external proxy that does TLS
# (TIPPR_EXTERNAL_PROXY)
server {
    listen 80;
    listen [::]:80;
    set $tippr_proto $tippr_external_proto;
    include snippets/tippr-locations.conf;
}
SITE
    else
        local hsts=""
        if [ "$3" = "1" ]; then
            hsts='    add_header Strict-Transport-Security "max-age=31536000" always;'
        fi
        cat > /etc/nginx/sites-available/tippr <<SITE
# Generated by install/tippr.sh
server {
    listen 80;
    listen [::]:80;
    # Let's Encrypt's http-01 challenges; everything else to https
    location /.well-known/acme-challenge/ {
        root /var/www/letsencrypt;
        try_files \$uri =404;
    }
    location / {
        return 301 https://\$host\$request_uri;
    }
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

    set \$tippr_proto https;
    include snippets/tippr-locations.conf;
}
SITE
    fi
    ln -nsf /etc/nginx/sites-available/tippr /etc/nginx/sites-enabled/tippr
}

if [ -n "$TIPPR_EXTERNAL_PROXY" ]; then
    write_nginx_site
elif [ -n "$TIPPR_TLS_CERT" ] && [ -n "$TIPPR_TLS_KEY" ]; then
    write_nginx_site "$TIPPR_TLS_CERT" "$TIPPR_TLS_KEY" 1
elif [ -n "$TIPPR_LETSENCRYPT_EMAIL" ] && [ -s "$LETSENCRYPT_CERT" ]; then
    write_nginx_site "$LETSENCRYPT_CERT" "$LETSENCRYPT_KEY" 1
else
    write_nginx_site "$SELF_SIGNED_CERT" "$SELF_SIGNED_KEY" 0
fi

# link the ini file for the Flask click tracker
ln -nsf $TIPPR_SRC/tippr/r2/development.ini $TIPPR_SRC/tippr/scripts/production.ini

# a backend serves no pages (its frontends do)
if [ "$TIPPR_ROLE" = "backend" ]; then
    systemctl disable --now nginx.service 2>/dev/null || true
    systemctl reset-failed nginx.service 2>/dev/null || true
else
    nginx -t
    systemctl enable nginx.service 2>/dev/null || true
    service nginx restart
fi

###############################################################################
# Let's Encrypt
###############################################################################
# nginx now answers http-01 challenges, so request the certificate, then
# switch nginx over to it. certbot's timer renews it and reloads nginx.
# (Behind an external proxy, that proxy has the certificate.)
if [ -n "$TIPPR_LETSENCRYPT_EMAIL" ] && [ -z "$TIPPR_TLS_CERT" ] && [ -z "$TIPPR_EXTERNAL_PROXY" ] && \
        [ "$TIPPR_ROLE" != "backend" ]; then
    apt-get install $APTITUDE_OPTIONS certbot
    if certbot certonly --webroot -w /var/www/letsencrypt \
            -d "$TIPPR_DOMAIN" --email "$TIPPR_LETSENCRYPT_EMAIL" \
            --agree-tos --non-interactive --keep-until-expiring \
            --deploy-hook "systemctl reload nginx"; then
        write_nginx_site "$LETSENCRYPT_CERT" "$LETSENCRYPT_KEY" 1
        systemctl reload nginx
    else
        echo "WARNING: Let's Encrypt failed; still using the self-signed certificate." >&2
        echo "Check that $TIPPR_DOMAIN resolves to this server and port 80 is reachable." >&2
    fi
fi

###############################################################################
# websocket service
###############################################################################
 
# Create a systemd unit for websockets (preferred on modern systems). On
# each frontend (each passes on every live update, from the backend's
# queue), not on a backend.
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    if [ "$TIPPR_ROLE" = "backend" ]; then
        systemctl disable --now tippr-websockets.service 2>/dev/null || true
    else
        systemctl enable --now tippr-websockets.service || service tippr-websockets restart || true
    fi
fi

###############################################################################
# activity service
###############################################################################

# Create a systemd unit for activity service. One for the whole site, so
# every frontend counts the same visitors: on the backend.
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    if [ "$TIPPR_ROLE" = "frontend" ]; then
        systemctl disable --now tippr-activity.service 2>/dev/null || true
    else
        systemctl enable --now tippr-activity.service || service tippr-activity restart || true
    fi
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
# applies each vault's AutoModerator rules (its wiki page
# config/automoderator) to new posts and comments. Older installs
# had it at 0 (reddit's default), so 0 becomes 1; another count is kept.
if [ "$TIPPR_AUTOMODERATOR_NAME" != "off" ]; then
    if [ "$(cat $CONSUMER_CONFIG_ROOT/automoderator_q 2>/dev/null || echo 0)" = "0" ]; then
        echo 1 > $CONSUMER_CONFIG_ROOT/automoderator_q
    fi
else
    echo 0 > $CONSUMER_CONFIG_ROOT/automoderator_q
fi
set_consumer_count butler_q 1
# analytics events (r2.lib.eventcollector) only go somewhere with an event
# collector service (events_collector_url in the ini). Without one the site
# makes none, and what older versions queued for nothing is emptied: it
# held members' ids, IP addresses and browsers.
if grep -qE '^events_collector_url *= *[^ ]' "$TIPPR_SRC/tippr/r2/run.ini" 2>/dev/null; then
    set_consumer_count event_collector_q 1
else
    echo 0 > $CONSUMER_CONFIG_ROOT/event_collector_q
    for queue in event_collector event_collector_test event_collector_failed; do
        rabbitmqctl -q purge_queue -p / "$queue" >/dev/null 2>&1 || true
    done
fi
set_consumer_count author_query_q 1
set_consumer_count vault_query_q 1
set_consumer_count domain_query_q 1
set_consumer_count privacy_export_q 1
# comments on the threads in fastlane_links (/admin/config) go to their
# own queue; one idle consumer waits for them
set_consumer_count commentstree_fastlane_q 1
# the shard_*_queues ini settings split a queue ten ways to cut lock
# contention on big sites: one consumer per shard (instance n is shard n-1).
# Until they run, items stay on the main queue.
for kind in commentstree author_query vault_query domain_query; do
    if grep -qiE "^shard_${kind}_queues *= *(true|yes|on|1) *$" "$TIPPR_SRC/tippr/r2/run.ini" 2>/dev/null; then
        if [ "$(cat $CONSUMER_CONFIG_ROOT/${kind}_shard_q 2>/dev/null || echo 0)" = "0" ]; then
            echo 10 > $CONSUMER_CONFIG_ROOT/${kind}_shard_q
        fi
    else
        echo 0 > $CONSUMER_CONFIG_ROOT/${kind}_shard_q
    fi
done

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
# vying with eachother to get there first (on the backend, which has the
# databases, before any frontend)
if [ "$TIPPR_ROLE" != "frontend" ]; then
    tippr-run -c 'print("ok done")'

    # Build the search index the first time (later changes go through
    # search_q). To rebuild it from scratch:
    #   tippr-run -c 'from pylons import app_globals as g; g.search.rebuild_index(recreate=True)'
    if [ "$TIPPR_SEARCH" = "opensearch" ] && \
            ! curl -fsS -o /dev/null http://127.0.0.1:9200/tippr_links; then
        tippr-run -c 'from pylons import app_globals as g; g.search.rebuild_index()'
    fi
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
    # ends gold when it runs out (and warns 3 days before); does nothing
    # without gold members
    tippr-job-update_gold_users.timer
    # posts new items from the feeds on /admin/feeds; does nothing without any
    tippr-job-feeds.timer
    # counts new vault subscriptions for the traffic pages (pageviews are
    # counted as pages are served, r2.lib.traffic_counter)
    tippr-job-subscribers.timer
    # predicts each vault's daily pageviews, the inventory sponsored posts
    # are sold from (r2.lib.inventory)
    tippr-job-update_promo_metrics.timer
    # gives members their X-Year Club trophies on their cake day
    # (r2.lib.year_club)
    tippr-job-year_clubs.timer
    # works out which vaults are like which, for the explore page
    # (r2.lib.vault_similarity)
    tippr-job-vault_similarity.timer
    # builds the complete sitemaps each day; does nothing unless /admin/site
    # asks for every post (r2.lib.sitemaps.complete)
    tippr-job-sitemaps.timer
    # this server's state for /admin/servers, every minute (on every server)
    tippr-job-server_status.timer
    # the smoke check every 5 minutes, alerting when it changes (on every
    # server; TIPPR_ALERT_*)
    tippr-monitor.timer
)
# A frontend runs the queue processors and scheduled jobs on its backend:
# only the timers every server has (its state for /admin/servers, its
# alerts, and updates from there, below).
if [ "$TIPPR_ROLE" = "frontend" ]; then
    EVERY_SERVER=(tippr-job-server_status.timer tippr-monitor.timer)
    FRONTEND_OFF=(tippr-consumers.service tippr-backup.path)
    for timer in "${TIPPR_TIMERS[@]}"; do
        [[ " ${EVERY_SERVER[*]} " == *" $timer "* ]] || FRONTEND_OFF+=("$timer")
    done
    TIPPR_TIMERS=("${EVERY_SERVER[@]}")
fi

###############################################################################
# Firewall (optional)
###############################################################################
# what a backend's frontends reach (TIPPR_ROLE=backend, docs/SERVERS.md):
# PostgreSQL, Cassandra, RabbitMQ, ZooKeeper, OpenSearch, memcached and the
# activity service. Several have no password, so only from their range.
BACKEND_PORTS="5432 9042 5672 2181 9200 11211 9002"
if [ "$TIPPR_FIREWALL" = "1" ]; then
    apt-get install $APTITUDE_OPTIONS ufw
    ufw allow "${TIPPR_SSH_PORT}/tcp"
    # pages: not on a backend
    if [ "$TIPPR_ROLE" != "backend" ]; then
        ufw allow 80/tcp
        ufw allow 443/tcp
    fi
    if [ "$TIPPR_ROLE" = "backend" ]; then
        for port in $BACKEND_PORTS; do
            ufw allow from "$TIPPR_FRONTEND_ALLOW" to any port "$port" proto tcp
        done
    # a shared cache server (TIPPR_MEMCACHED_LISTEN): the frontends only
    elif [ -n "$TIPPR_MEMCACHED_ALLOW" ]; then
        ufw allow from "$TIPPR_MEMCACHED_ALLOW" to any port 11211 proto tcp
    fi
    ufw --force enable
elif [ "$TIPPR_ROLE" = "backend" ]; then
    echo "NOTE: this backend takes its frontends' connections on ports ${BACKEND_PORTS// /, }; Cassandra, OpenSearch, memcached and the activity service have no password, so let only $TIPPR_FRONTEND_ALLOW reach them (the Proxmox firewall, or TIPPR_FIREWALL=1 with ufw; docs/SERVERS.md)"
elif [ -n "$TIPPR_MEMCACHED_ALLOW" ]; then
    echo "NOTE: memcached listens on $TIPPR_MEMCACHED_LISTEN; let only $TIPPR_MEMCACHED_ALLOW reach port 11211 (TIPPR_FIREWALL=1 does it with ufw)"
fi

# ok, now start everything else up
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    if [ "$TIPPR_ROLE" = "frontend" ]; then
        systemctl disable --now "${FRONTEND_OFF[@]}" 2>/dev/null || true
        systemctl enable tippr.target "${TIPPR_TIMERS[@]}"
    else
        systemctl enable tippr.target tippr-consumers.service "${TIPPR_TIMERS[@]}"
        systemctl enable --now tippr-backup.path
    fi
    # the daily backup runs where the data is (the one server, or the backend)
    if [ "$TIPPR_ROLE" != "frontend" ] && [ "$TIPPR_BACKUP_SCHEDULE" = "daily" ]; then
        systemctl enable --now tippr-backup-daily.timer
    else
        systemctl disable --now tippr-backup-daily.timer 2>/dev/null || true
    fi
    # /admin/backups on the frontends reaches a backend's tippr-backup
    # through ZooKeeper (scripts/backup_relay.py)
    if [ "$TIPPR_ROLE" = "backend" ]; then
        systemctl enable --now tippr-backup-relay.timer
    else
        systemctl disable --now tippr-backup-relay.timer 2>/dev/null || true
    fi
    if [ "$TIPPR_WEB_UPDATES" = "1" ]; then
        systemctl enable --now tippr-update.timer
    else
        systemctl disable --now tippr-update.timer 2>/dev/null || true
    fi
    systemctl restart tippr.target
else
    echo "No systemd found; services not started."
fi

###############################################################################
# Finished with install script
###############################################################################
# Initialize policy wiki pages (Terms of Use, Privacy Policy, etc.)
# (on the backend, or the one server: a frontend shares its backend's)
if [ "$TIPPR_ROLE" != "frontend" ]; then
    echo "Ensuring application account exists..."
    tippr-run $TIPPR_SRC/tippr/scripts/create_default_user.py || echo "Note: create_default_user.py skipped"
    echo "Initializing policy wiki pages..."
    tippr-run $TIPPR_SRC/tippr/scripts/init_policy_wiki_pages.py || echo "Note: Policy wiki pages initialization skipped (can be run manually later)"
    # starter vaults and front page defaults (then only defaults new since the
    # last run, so ones an admin took off stay off)
    echo "Creating starter vaults..."
    tippr-run $TIPPR_SRC/tippr/scripts/create_default_vaults.py || echo "Note: starter vaults skipped (run scripts/create_default_vaults.py later)"
    # starter feeds for them (TIPPR_STARTER_FEEDS; then only feeds new since the
    # last run, so ones an admin removed stay removed)
    echo "Adding starter feeds (TIPPR_STARTER_FEEDS=$TIPPR_STARTER_FEEDS)..."
    FEEDS_STARTER="$TIPPR_STARTER_FEEDS" tippr-run $TIPPR_SRC/tippr/scripts/import_feeds.py || echo "Note: starter feeds skipped (FEEDS_STARTER=1 tippr-run scripts/import_feeds.py later)"
    # starter awards (trophies); existing ones are left alone
    echo "Creating starter awards..."
    tippr-run $TIPPR_SRC/tippr/scripts/create_default_awards.py || echo "Note: starter awards skipped (run scripts/create_default_awards.py later)"
    # which vaults are like which, for the explore page (then daily, from
    # tippr-job-vault_similarity)
    tippr-run -c "from r2.lib import vault_similarity; vault_similarity.run()" || echo "Note: vault similarity skipped (tippr-job-vault_similarity runs it daily)"
fi

# print this out here. if vagrant's involved, it's gonna do more steps
# afterwards and then re-run this script but that's ok.
$RUNDIR/done.sh

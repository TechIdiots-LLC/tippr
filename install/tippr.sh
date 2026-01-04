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

# Ensure installed baseplate package exposes `metrics_client_from_config`
# for older code that imports it from `baseplate` directly. Prefer the
# implementation in `baseplate.lib.metrics` if available, otherwise
# provide a noop fallback. This edits the venv site-packages package
# after pip installs so runtime imports succeed regardless of PYTHONPATH.
#    sudo TIPPR_DOMAIN=example.com ./install/tippr.sh
#
###############################################################################

# load configuration
RUNDIR=$(dirname $0)
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

# Ensure venv-installed baseplate exposes `secrets_store_from_config` by
# creating a small `secrets.py` shim in the package when missing. This
# keeps runtime imports working for older services that import
# `baseplate.secrets` directly.
for p in "$TIPPR_VENV"/lib/python*/site-packages/baseplate; do
    if [ -d "$p" ]; then
        target="$p/secrets.py"
        if [ ! -f "$target" ]; then
            cat > "$target" <<'PYSECRETS'
"""Compatibility shim for baseplate.secrets added by installer.

Prefer `baseplate.lib.secrets.secrets_store_from_config` when available,
otherwise provide a noop secrets store for development.
"""
try:
    from baseplate.lib.secrets import secrets_store_from_config as _r2_secrets_store_from_config
except Exception:
    _r2_secrets_store_from_config = None

if _r2_secrets_store_from_config is not None:
    secrets_store_from_config = _r2_secrets_store_from_config
else:
    class _NoopSecretsStore:
        def get(self, key, default=None):
            return default

        def get_bytes(self, key, default=None):
            return default

        def put(self, key, value):
            return None

    def secrets_store_from_config(config=None):
        return _NoopSecretsStore()

__all__ = ['secrets_store_from_config']
PYSECRETS
        fi
    fi
done

# Provide a small compatibility module for Python 2 `urlparse` imports.
# Some older services do `import urlparse`; create a shim in the venv
# site-packages that re-exports `urllib.parse` for Python 3.
for p in "$TIPPR_VENV"/lib/python*/site-packages; do
    if [ -d "$p" ]; then
        target="$p/urlparse.py"
        if [ ! -f "$target" ]; then
            cat > "$target" <<'PYURL'
"""Compatibility shim: provide Python2 `urlparse` module for Python3.

This module re-exports the `urllib.parse` API under the old
`urlparse` name so legacy code importing `urlparse` continues to work.
"""
from urllib.parse import *

__all__ = [
    'urlparse', 'urlunparse', 'urljoin', 'urlsplit', 'urlunsplit',
    'parse_qs', 'parse_qsl', 'quote', 'quote_plus', 'unquote',
    'unquote_plus', 'urlencode',
]
PYURL
        fi
    fi
done

# Provide a compatibility module for Python 2 `imp` module.
# The `imp` module was removed in Python 3.12. Some legacy packages
# still use it. This shim provides the commonly used functions
# using importlib.
for p in "$TIPPR_VENV"/lib/python*/site-packages; do
    if [ -d "$p" ]; then
        target="$p/imp.py"
        if [ ! -f "$target" ]; then
            cat > "$target" <<'PYIMP'
"""Compatibility shim: provide deprecated `imp` module for Python 3.12+.

The `imp` module was removed in Python 3.12. This shim provides the
commonly used functions using importlib for legacy packages.
"""
import importlib
import importlib.util
import sys
import os
import tokenize

# Constants that were in the imp module
PY_SOURCE = 1
PY_COMPILED = 2
C_EXTENSION = 3
PKG_DIRECTORY = 5
C_BUILTIN = 6
PY_FROZEN = 7

def find_module(name, path=None):
    """Find a module, returning (file, pathname, description)."""
    if path is None:
        path = sys.path
    for directory in path:
        if not isinstance(directory, str):
            continue
        full_path = os.path.join(directory, name)
        # Check for package
        if os.path.isdir(full_path):
            init_path = os.path.join(full_path, '__init__.py')
            if os.path.exists(init_path):
                return (None, full_path, ('', '', PKG_DIRECTORY))
        # Check for .py file
        py_path = full_path + '.py'
        if os.path.exists(py_path):
            return (open(py_path, 'r'), py_path, ('.py', 'r', PY_SOURCE))
        # Check for .pyc file
        pyc_path = full_path + '.pyc'
        if os.path.exists(pyc_path):
            return (open(pyc_path, 'rb'), pyc_path, ('.pyc', 'rb', PY_COMPILED))
    raise ImportError(f"No module named {name}")

def load_module(name, file, pathname, description):
    """Load a module given the info from find_module."""
    suffix, mode, type_ = description
    if type_ == PKG_DIRECTORY:
        spec = importlib.util.spec_from_file_location(
            name, os.path.join(pathname, '__init__.py'),
            submodule_search_locations=[pathname]
        )
    elif type_ == PY_SOURCE:
        spec = importlib.util.spec_from_file_location(name, pathname)
    elif type_ == PY_COMPILED:
        spec = importlib.util.spec_from_file_location(name, pathname)
    else:
        spec = importlib.util.find_spec(name)

    if spec is None:
        raise ImportError(f"Cannot load module {name}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def reload(module):
    """Reload a module."""
    return importlib.reload(module)

def get_suffixes():
    """Return a list of (suffix, mode, type) tuples."""
    return [
        ('.py', 'r', PY_SOURCE),
        ('.pyc', 'rb', PY_COMPILED),
    ]

def new_module(name):
    """Create a new empty module."""
    import types
    return types.ModuleType(name)

def is_builtin(name):
    """Return True if the module is built-in."""
    return name in sys.builtin_module_names

def is_frozen(name):
    """Return True if the module is frozen."""
    return importlib.util.find_spec(name) is not None and \
           getattr(importlib.util.find_spec(name), 'origin', None) == 'frozen'

# NullImporter for compatibility
class NullImporter:
    def __init__(self, path):
        if os.path.isdir(path):
            raise ImportError("existing directory")

    def find_module(self, fullname, path=None):
        return None

def acquire_lock():
    """Acquire the import lock (no-op in Python 3)."""
    pass

def release_lock():
    """Release the import lock (no-op in Python 3)."""
    pass

def lock_held():
    """Return True if the import lock is held."""
    return False

__all__ = [
    'find_module', 'load_module', 'reload', 'get_suffixes', 'new_module',
    'is_builtin', 'is_frozen', 'NullImporter', 'acquire_lock', 'release_lock',
    'lock_held', 'PY_SOURCE', 'PY_COMPILED', 'C_EXTENSION', 'PKG_DIRECTORY',
    'C_BUILTIN', 'PY_FROZEN',
]
PYIMP
        fi
    fi
done

# Ensure venv-installed baseplate exposes a `crypto` module expected by
# older services (e.g. `from baseplate.crypto import validate_signature`).
for p in "$TIPPR_VENV"/lib/python*/site-packages/baseplate; do
    if [ -d "$p" ]; then
        target="$p/crypto.py"
        if [ ! -f "$target" ]; then
            cat > "$target" <<'PYCRYPTO'
"""Compatibility shim for baseplate.crypto added by installer.

Prefer `baseplate.lib.crypto.validate_signature` when available,
otherwise provide a no-op `validate_signature` and `SignatureError`.
"""
try:
    from baseplate.lib.crypto import validate_signature as _r2_validate_signature
    from baseplate.lib.crypto import SignatureError as _r2_SignatureError
except Exception:
    _r2_validate_signature = None
    _r2_SignatureError = None

if _r2_validate_signature is not None:
    validate_signature = _r2_validate_signature
    SignatureError = _r2_SignatureError
else:
    class SignatureError(Exception):
        pass

    def validate_signature(secret, payload):
        return True

__all__ = ['validate_signature', 'SignatureError']
PYCRYPTO
        fi
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

###############################################################################
# Install the tippr source repositories
###############################################################################
if [ ! -d $TIPPR_SRC ]; then
    mkdir -p $TIPPR_SRC
    chown $TIPPR_USER $TIPPR_SRC
fi

function copy_upstart {
    if [ -d ${1}/upstart ]; then
        # Prefer Upstart directory if present (older Ubuntu), otherwise
        # place the files in /etc/init.d so they are available on systemd
        # hosts for later conversion or wrapper usage.
        if [ -d /etc/init ]; then
            # Copy any tippr- or legacy reddit- upstart jobs; fall back to
            # copying all upstart files. Ignore errors if patterns don't match.
            cp ${1}/upstart/tippr-* ${1}/upstart/reddit-* ${1}/upstart/* /etc/init/ 2>/dev/null || true
        else
            mkdir -p /etc/init.d
            cp ${1}/upstart/tippr-* ${1}/upstart/reddit-* ${1}/upstart/* /etc/init.d/ 2>/dev/null || true
            # Make copied files executable so they can be used as simple
            # wrappers or inspected by administrators.
            chmod +x /etc/init.d/* || true
        fi
    fi
}

function clone_tippr_repo {
    local destination=$TIPPR_SRC/${1}
    local repo_spec=${2}
    local repository_url

    # Accept either an owner/repo spec or a full URL
    if echo "$repo_spec" | grep -qE '^https?://'; then
        repository_url="$repo_spec"
    else
        repository_url="https://github.com/${repo_spec}.git"
    fi


    if [ ! -d $destination ]; then
        # First try an anonymous clone (preserves previous CI behavior).
        if sudo -u $TIPPR_USER -H git clone "$repository_url" $destination; then
            : # success
        else
            # Anonymous clone failed; if a token is available, retry with it.
            if [ -n "$TIPPR_GITHUB_TOKEN" ] || [ -n "$GITHUB_TOKEN" ]; then
                token=${TIPPR_GITHUB_TOKEN:-$GITHUB_TOKEN}
                repo_with_token=$(echo "$repository_url" | sed -E "s#https://#https://x-access-token:${token}@#")
                sudo -u $TIPPR_USER -H git clone "$repo_with_token" $destination || true
            fi
        fi
    fi

    copy_upstart $destination
}

function clone_tippr_service_repo {
    local name=$1
    local repo=${2:-tippr/tippr-service-$1}
    clone_tippr_repo $name "$repo"
}

clone_tippr_repo tippr TechIdiots-LLC/tippr
# i18n repo lives under the organization owner – ensure we clone the
# TechIdiots-LLC owner (not the old `tippr/` owner).
clone_tippr_repo i18n TechIdiots-LLC/tippr-i18n
clone_tippr_service_repo websockets "$TIPPR_WEBSOCKETS_REPO"
clone_tippr_service_repo activity "$TIPPR_ACTIVITY_REPO"

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

# Configure mcrouter
$RUNDIR/setup_mcrouter.sh

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
sudo -u $TIPPR_USER $TIPPR_VENV/bin/python -m pip install --upgrade pip setuptools wheel
sudo -u $TIPPR_USER $TIPPR_VENV/bin/python -m pip install --upgrade 'packaging>=23.1'

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
    nose \
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
    sudo -u $TIPPR_USER $TIPPR_VENV/bin/pip install --upgrade --force-reinstall --no-deps pip setuptools wheel 'packaging>=23.1' || true

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
    copy_upstart $TIPPR_SRC/$plugin
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
# global debug flag -- displays pylons stacktrace rather than 500 page on error when true
# WARNING: a pylons stacktrace allows remote code execution. Make sure this is false
# if your server is publicly accessible.
debug = true

disable_ads = true
disable_captcha = true
disable_ratelimit = true
disable_require_admin_otp = true

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

sudo -u $TIPPR_USER PATH="$TIPPR_VENV/bin:$PATH" PYTHONPATH="$TIPPR_SRC/tippr:$TIPPR_SRC" make ini || true

# Ensure `development.ini` exists. If `make ini` didn't create it (CI or
# permission issues), try generating it directly with `updateini.py`.
if [ ! -f development.ini ]; then
    echo "development.ini not found; attempting to generate with updateini.py"
    sudo -u $TIPPR_USER bash -lc "PATH=\"$TIPPR_VENV/bin:\$PATH\" PYTHONPATH=\"$TIPPR_SRC/tippr:$TIPPR_SRC\" python updateini.py example.ini development.update > development.ini" || true
fi

# Ensure run.ini is a symlink to a real ini. Prefer development.ini, fall
# back to example.ini if generation failed.
if [ -f development.ini ]; then
    # Create a real file (not a symlink) to avoid broken-link surprises in CI
    sudo -u $TIPPR_USER cp -f development.ini run.ini
    sudo -u $TIPPR_USER chown $TIPPR_USER run.ini || true
else
    echo "Falling back to example.ini for run.ini (development.ini missing)"
    sudo -u $TIPPR_USER cp -f example.ini run.ini
    sudo -u $TIPPR_USER chown $TIPPR_USER run.ini || true
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

helper-script /usr/local/bin/tippr-start <<TIPPRSTART
#!/bin/bash
if command -v initctl >/dev/null 2>&1; then
    initctl emit tippr-start
elif command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    # Restart common tippr units if systemd is available
    systemctl restart tippr-websockets tippr-activity gunicorn-click gunicorn-geoip || true
else
    echo "No initctl or systemctl found; cannot start services"
fi
TIPPRSTART

helper-script /usr/local/bin/tippr-stop <<TIPPRSTOP
#!/bin/bash
if command -v initctl >/dev/null 2>&1; then
    initctl emit tippr-stop
elif command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    systemctl stop tippr-websockets tippr-activity gunicorn-click gunicorn-geoip || true
else
    echo "No initctl or systemctl found; cannot stop services"
fi
TIPPRSTOP

helper-script /usr/local/bin/tippr-restart <<TIPPRRESTART
#!/bin/bash
if command -v initctl >/dev/null 2>&1; then
    initctl emit tippr-restart TARGET=${1:-all}
elif command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    # If a specific target is provided, attempt to restart matching unit(s)
    if [ -n "$1" ] && [ "$1" != "all" ]; then
        systemctl restart "$1" || true
    else
        systemctl restart tippr-websockets tippr-activity gunicorn-click gunicorn-geoip || true
    fi
else
    echo "No initctl or systemctl found; cannot restart services"
fi
TIPPRRESTART

helper-script /usr/local/bin/tippr-flush <<REDDITFLUSH
#!/bin/bash
echo flush_all | nc localhost 11211
TIPPRFLUSH

helper-script /usr/local/bin/tippr-serve <<REDDITSERVE
#!/bin/bash
cd $TIPPR_SRC/tippr/r2
export PYTHONPATH="$TIPPR_SRC/tippr:$TIPPR_SRC:\$PYTHONPATH"
exec $TIPPR_VENV/bin/paster serve --reload run.ini
TIPPRSERVE

# Create a systemd unit for tippr-serve that uses the installer helper
# script so systemd runs paster with the correct PYTHONPATH and venv.
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    cat > /etc/systemd/system/tippr-serve.service <<UNIT
[Unit]
Description=Tippr web app (paster serve)
After=network.target

[Service]
Type=simple
User=$TIPPR_USER
Group=$TIPPR_USER
WorkingDirectory=$TIPPR_SRC/tippr/r2
Environment=VIRTUAL_ENV=$TIPPR_VENV
Environment=PATH=$TIPPR_VENV/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/bin
Environment=MAKO_MODULE_DIRECTORY=/var/opt/tippr/mako
ExecStart=/usr/local/bin/tippr-serve
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

    systemctl daemon-reload || true
    systemctl enable --now tippr-serve.service || true
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
    cat > /etc/systemd/system/gunicorn-click.service <<UNIT
[Unit]
Description=Gunicorn click server for tippr
After=network.target

[Service]
Type=simple
User=$TIPPR_USER
Group=$TIPPR_GROUP
WorkingDirectory=$TIPPR_SRC/tippr/scripts
Environment=PATH=$TIPPR_VENV/bin
Environment=PYTHONPATH=$TIPPR_SRC:$TIPPR_SRC/tippr
Environment=PROMETHEUS_MULTIPROC_DIR=$PROMETHEUS_DIR
ExecStart=$TIPPR_VENV/bin/gunicorn --bind unix:/var/opt/tippr/click.sock --workers=1 tracker:application
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

    systemctl daemon-reload || true
    systemctl enable --now gunicorn-click.service || true
fi

###############################################################################
# nginx
###############################################################################

mkdir -p /srv/www/media
chown $TIPPR_USER:$TIPPR_GROUP /srv/www/media

cat > /etc/nginx/sites-available/tippr-media <<MEDIA
server {
    listen 9000;

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
  listen 8082;
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

cat > /etc/nginx/sites-available/tippr-ssl <<SSL
map \$http_upgrade \$connection_upgrade {
  default upgrade;
  ''      close;
}

server {
    listen 443;

    ssl on;
    ssl_certificate /etc/ssl/certs/ssl-cert-snakeoil.pem;
    ssl_certificate_key /etc/ssl/private/ssl-cert-snakeoil.key;

    ssl_protocols TLSv1 TLSv1.1 TLSv1.2;
    ssl_ciphers EECDH+AES128:RSA+AES128:EECDH+AES256:RSA+AES256:EECDH+3DES:RSA+3DES:!MD5;
    ssl_prefer_server_ciphers on;

    ssl_session_cache shared:SSL:1m;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$http_host;
        proxy_http_version 1.1;
        proxy_set_header X-Forwarded-For \$remote_addr;
        proxy_pass_header Server;

        # allow websockets through if desired
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
    }
}
SSL

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

    server app01-8001 localhost:8001 maxconn 30

backend websockets
    mode http
    timeout connect 4s
    timeout server 24h
    balance roundrobin

    server websockets localhost:9001 maxconn 250

backend media
    mode http
    timeout connect 4000
    timeout server 30000
    timeout queue 60000
    balance roundrobin

    server nginx localhost:9000 maxconn 20

backend pixel
    mode http
    timeout connect 4000
    timeout server 30000
    timeout queue 60000
    balance roundrobin

    server nginx localhost:8082 maxconn 20
HAPROXY

# this will start it even if currently stopped
service haproxy restart

###############################################################################
# websocket service
###############################################################################
 
# Only install Upstart jobs if /etc/init exists (do not create it)
if [ -d /etc/init ]; then
    if [ ! -f /etc/init/tippr-websockets.conf ]; then
        cat > /etc/init/tippr-websockets.conf << UPSTART_WEBSOCKETS
description "websockets service"

stop on runlevel [!2345] or tippr-restart all or tippr-restart websockets
start on runlevel [2345] or tippr-restart all or tippr-restart websockets

respawn
respawn limit 10 5
kill timeout 15

limit nofile 65535 65535

exec $TIPPR_VENV/bin/baseplate-serve --bind localhost:9001 $TIPPR_SRC/websockets/example.ini
UPSTART_WEBSOCKETS
    fi
fi

# Create a systemd unit for websockets (preferred on modern systems)
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    cat > /etc/systemd/system/tippr-websockets.service <<UNIT
[Unit]
Description=Tippr Websockets Service
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$TIPPR_USER
# Use the app user as group to avoid permission issues with user-owned venvs
Group=$TIPPR_USER
WorkingDirectory=$TIPPR_SRC/websockets
# Provide the venv bin first, but keep system PATH entries so helpers are found
# Omit /sbin which can cause the service to fail on some systems
Environment=PATH=$TIPPR_VENV/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/bin
Environment=VIRTUAL_ENV=$TIPPR_VENV
Environment=PROMETHEUS_MULTIPROC_DIR=$PROMETHEUS_DIR

# Ensure prometheus multiproc dir exists and is owned by the service user
ExecStartPre=/bin/mkdir -p $PROMETHEUS_DIR
ExecStartPre=/bin/chown $TIPPR_USER:$TIPPR_USER $PROMETHEUS_DIR

# Bind to 127.0.0.1 to avoid potential localhost resolution issues
Environment=HOME=/home/$TIPPR_USER
ExecStart=$TIPPR_VENV/bin/baseplate-serve --bind 127.0.0.1:9001 $TIPPR_SRC/websockets/example.ini
Restart=on-failure
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
UNIT

    systemctl daemon-reload || true
    systemctl enable --now tippr-websockets.service || service tippr-websockets restart || true
fi

###############################################################################
# activity service
###############################################################################

# Only install Upstart jobs if /etc/init exists (do not create it)
if [ -d /etc/init ]; then
    if [ ! -f /etc/init/tippr-activity.conf ]; then
        cat > /etc/init/tippr-activity.conf << UPSTART_ACTIVITY
description "activity service"

stop on runlevel [!2345] or tippr-restart all or tippr-restart activity
start on runlevel [2345] or tippr-restart all or tippr-restart activity

respawn
respawn limit 10 5
kill timeout 15

exec $TIPPR_VENV/bin/baseplate-serve --bind localhost:9002 $TIPPR_SRC/activity/example.ini
UPSTART_ACTIVITY
    fi
fi

# Create a systemd unit for activity service
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    cat > /etc/systemd/system/tippr-activity.service <<UNIT
[Unit]
Description=Tippr Activity Service
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$TIPPR_USER
Group=$TIPPR_GROUP
WorkingDirectory=$TIPPR_SRC/activity
# Provide the venv bin first and common system paths; omit /sbin for compatibility
Environment=PATH=$TIPPR_VENV/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/bin
Environment=VIRTUAL_ENV=$TIPPR_VENV
Environment=PROMETHEUS_MULTIPROC_DIR=$PROMETHEUS_DIR
Environment=HOME=/home/$TIPPR_USER
ExecStartPre=/bin/mkdir -p $PROMETHEUS_DIR
ExecStartPre=/bin/chown $TIPPR_USER:$TIPPR_USER $PROMETHEUS_DIR
ExecStart=$TIPPR_VENV/bin/baseplate-serve --bind 127.0.0.1:9002 $TIPPR_SRC/activity/example.ini
Restart=on-failure
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
UNIT

    systemctl daemon-reload || true
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
    cat > /etc/systemd/system/gunicorn-geoip.service <<UNIT
[Unit]
Description=Gunicorn geoip server for tippr
After=network.target

[Service]
Type=simple
User=$TIPPR_USER
Group=$TIPPR_GROUP
WorkingDirectory=$TIPPR_SRC/tippr/scripts
Environment=PATH=$TIPPR_VENV/bin
ExecStart=$TIPPR_VENV/bin/gunicorn --bind 127.0.0.1:5000 --workers=1 --limit-request-line=8190 geoip_service:application
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

    systemctl daemon-reload || true
    systemctl enable --now gunicorn-geoip.service || true
fi

###############################################################################
# Job Environment
###############################################################################
CONSUMER_CONFIG_ROOT=$TIPPR_HOME/consumer-count.d

if [ ! -f /etc/default/tippr ]; then
    cat > /etc/default/tippr <<DEFAULT
export TIPPR_ROOT=$TIPPR_SRC/tippr/r2
export TIPPR_INI=$TIPPR_SRC/tippr/r2/run.ini
export TIPPR_USER=$TIPPR_USER
export TIPPR_GROUP=$TIPPR_GROUP
export TIPPR_CONSUMER_CONFIG=$CONSUMER_CONFIG_ROOT
alias wrap-job=$TIPPR_SRC/tippr/scripts/wrap-job
alias manage-consumers=$TIPPR_SRC/tippr/scripts/manage-consumers
DEFAULT
fi

###############################################################################
# Queue Processors
###############################################################################
mkdir -p $CONSUMER_CONFIG_ROOT

function set_consumer_count {
    if [ ! -f $CONSUMER_CONFIG_ROOT/$1 ]; then
        echo $2 > $CONSUMER_CONFIG_ROOT/$1
    fi
}

set_consumer_count search_q 0
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
set_consumer_count subreddit_query_q 1
set_consumer_count domain_query_q 1

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

# ok, now start everything else up (portable)
if command -v initctl >/dev/null 2>&1; then
    initctl emit tippr-stop
    initctl emit tippr-start
elif command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    systemctl stop tippr-websockets tippr-activity gunicorn-click gunicorn-geoip || true
    systemctl start tippr-websockets tippr-activity gunicorn-click gunicorn-geoip || true
else
    echo "No init system found (initctl/systemctl); services not started."
fi

###############################################################################
# Cron Jobs
###############################################################################
if [ ! -f /etc/cron.d/tippr ]; then
    cat > /etc/cron.d/tippr <<CRON
0    3 * * * root /sbin/start --quiet tippr-job-update_sr_names
30  16 * * * root /sbin/start --quiet tippr-job-update_reddits
0    * * * * root /sbin/start --quiet tippr-job-update_promos
*/5  * * * * root /sbin/start --quiet tippr-job-clean_up_hardcache
*/2  * * * * root /sbin/start --quiet tippr-job-broken_things
*/2  * * * * root /sbin/start --quiet tippr-job-rising
0    * * * * root /sbin/start --quiet tippr-job-trylater

# liveupdate
*    * * * * root /sbin/start --quiet tippr-job-liveupdate_activity

# jobs that recalculate time-limited listings (e.g. top this year)
PGPASSWORD=password
*/15 * * * * $TIPPR_USER $TIPPR_SRC/tippr/scripts/compute_time_listings link year "['hour', 'day', 'week', 'month', 'year']"
*/15 * * * * $TIPPR_USER $TIPPR_SRC/tippr/scripts/compute_time_listings comment year "['hour', 'day', 'week', 'month', 'year']"

# disabled by default, uncomment if you need these jobs
#*    * * * * root /sbin/start --quiet tippr-job-email
#0    0 * * * root /sbin/start --quiet tippr-job-update_gold_users
CRON
fi

###############################################################################
# Finished with install script
###############################################################################
# print this out here. if vagrant's involved, it's gonna do more steps
# afterwards and then re-run this script but that's ok.
$RUNDIR/done.sh

# Run inside the systemd box (systemd-box.sh run), as root: the steps of
# .github/workflows/ci-ubuntu-24.yml. The services come from the install
# scripts, with the database password example.ini expects; the r2 unit
# tests run with the C extensions built, and write a JUnit report to
# /tmp/unit-tests.xml.
set -euxo pipefail
cd /home/tippr/src/tippr
chmod +x install/*.sh
install/install_apt.sh
install/install_services.sh
TIPPR_DB_PASSWORD=password install/setup_postgres.sh
install/install_cassandra.sh
install/setup_cassandra.sh

python3 -m venv /opt/ci-venv
export PATH=/opt/ci-venv/bin:$PATH
pip install --upgrade pip setuptools wheel cython
pip install pyramid pyramid-mako cassandra-driver simplejson Paste PasteDeploy \
    Pylons pytest pylibmc
pip install -e r2/
python -c "import r2; print('r2 loaded from:', r2.__file__)"

export DATABASE_URL=postgresql://tippr:password@127.0.0.1/tippr
python -m pytest r2/r2/tests/unit -v --tb=short --junitxml=/tmp/unit-tests.xml

#!/usr/bin/env bash
###############################################################################
# tippr Drone environment installer
# ----------------------------------
# This script re-purposes some of our existing vagrant/Travis install and
# setup scripts for our Drone CI builds.
#
# NOTE: You don't want to run this script directly in your development
# environment, since we assume that it's running within this Docker image
# that Drone runs our builds within: https://github.com/tippr/docker-tippr-py
#
# docker-tippr-py has most of the apt dependencies pre-installed in order to
# significantly reduce our build times.
#
# Refer to .drone.yml in the repo root to see where this script gets called
# during a build.
###############################################################################

# load configuration
RUNDIR=$(dirname $0)
source $RUNDIR/install.cfg

###############################################################################
# Install prerequisites
###############################################################################

# Under normal operation, this won't install anything new. We're re-using the
# logic that checks to make sure all services have finished starting before
# continuing.
install/install_services.sh

###############################################################################
# Install and configure the tippr code
###############################################################################

# Create venv if it doesn't exist
if [ ! -d "$TIPPR_VENV" ]; then
    python3 -m venv $TIPPR_VENV
    $TIPPR_VENV/bin/pip install --upgrade pip setuptools wheel
fi

pushd r2
$TIPPR_VENV/bin/pip install -e .
$TIPPR_VENV/bin/python setup.py build
make pyx
ln -sf example.ini test.ini
popd

###############################################################################
# Configure local services
###############################################################################

# Creates the column families required for the tests
install/setup_cassandra.sh

#!/bin/bash

set -x
psql -h ${DB_HOST:-localhost} \
     -d ${DB_NAME:-tippr} \
     -U ${DB_USER:-tippr} \
     -p ${DB_PORT:-5432} \
     -F"\t" -A -t

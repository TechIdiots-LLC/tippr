#!/bin/bash
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0 (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# https://github.com/TechIdiots-LLC/tippr/blob/master/LICENSE.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is Tippr.
#
# The Initial Developer of the Original Code is TechIdiots LLC.
# Copyright (c) 2026 TechIdiots LLC. All Rights Reserved.
###############################################################################

# Start the compose stack (in this directory, with its .env), wait for the
# setup container, and check that the site answers over HTTPS. Leaves the
# stack running; "docker compose down -v" removes it. SMOKE_ADDRESS: the
# address the published ports are on (default 127.0.0.1; under
# Docker-in-Docker, the docker service's).
set -euo pipefail
cd "$(dirname "$0")"
# (|| true: a setting left out of .env isn't an error)
domain=$(grep -E '^TIPPR_DOMAIN=' .env | cut -d= -f2 || true)
https_port=$(grep -E '^TIPPR_HTTPS_PORT=' .env | cut -d= -f2 || true)
https_port=${https_port:-443}
address=${SMOKE_ADDRESS:-127.0.0.1}

docker compose up -d

echo "waiting for setup..."
for i in $(seq 120); do
    state=$(docker compose ps -a --format '{{.State}} {{.ExitCode}}' setup)
    case "$state" in
        "exited 0") echo "setup finished"; break ;;
        exited*) echo "setup failed: $state"; docker compose logs setup; exit 1 ;;
    esac
    sleep 10
done
[ "$state" = "exited 0" ] || { echo "setup didn't finish"; docker compose logs setup; exit 1; }

check() {
    curl -sk -o /dev/null -w '%{http_code}' \
        --resolve "$domain:$https_port:$address" "https://$domain:$https_port$1"
}
for i in $(seq 60); do
    code=$(check /) || true
    [ "$code" = "200" ] && break
    sleep 5
done
echo "GET / -> $code"
[ "$code" = "200" ]
for path in /v/technology/ /search?q=test /login /health; do
    code=$(check "$path")
    echo "GET $path -> $code"
    [ "$code" = "200" ]
done
# an uploaded file is served from the media volume
docker compose exec -T web sh -c 'echo ok > /srv/www/media/smoke.txt'
code=$(check /media/smoke.txt)
echo "GET /media/smoke.txt -> $code"
[ "$code" = "200" ]
docker compose exec -T web rm -f /srv/www/media/smoke.txt
# log in, post, and check the consumers handled it (listing, search)
docker compose exec -T web /opt/tippr/venv/bin/python \
    /opt/tippr/src/tippr/docker/smoke-post.py
# give the consumers and jobs a minute, then fail on any traceback
sleep 60
if docker compose logs --no-color consumers jobs websockets activity geoip \
        2>&1 | grep -A15 "Traceback"; then
    echo "a background container logged an error"
    exit 1
fi
# every long-running container is still up
docker compose ps --format '{{.Service}} {{.State}}'
if docker compose ps --format '{{.Service}} {{.State}}' | grep -v ' running$'; then
    echo "a container isn't running"
    exit 1
fi
echo "smoke test passed"

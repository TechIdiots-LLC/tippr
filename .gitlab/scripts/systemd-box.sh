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
# A whole Ubuntu 24.04 machine for CI jobs on the Docker runner: a container
# from proxmox/Dockerfile.base with systemd as PID 1 (as the Proxmox
# template build uses), so the install scripts can start services the way
# they do on a real server. GitHub's runners are VMs and don't need this.
#
#   systemd-box.sh start NAME            boot it and copy the checkout to
#                                        /home/tippr/src/tippr (user tippr)
#   systemd-box.sh run NAME SCRIPT [VAR=value ...]
#                                        run a local bash script in it, as root
#   systemd-box.sh logs NAME DIR         copy its logs and journal to DIR
#   systemd-box.sh stop NAME             remove it
#
# Needs a privileged job container talking to Docker-in-Docker (the runner
# registered with --privileged). OpenSearch needs vm.max_map_count >= 262144
# on the host; start raises it.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
log() { echo "[$(date +%H:%M:%S)] $*"; }
cmd=${1:?usage: systemd-box.sh start|run|logs|stop NAME ...}
name=${2:?name the container}

case "$cmd" in
start)
    if [ "$(sysctl -n vm.max_map_count)" -lt 262144 ]; then
        log "raising vm.max_map_count for OpenSearch"
        sysctl -w vm.max_map_count=262144
    fi
    log "building the base image"
    docker build -q -t tippr-ci-base -f "$root/proxmox/Dockerfile.base" "$root/proxmox"
    log "booting it"
    docker run -d --name "$name" --hostname tippr-ci --privileged \
        --cgroupns=private --tmpfs /run --tmpfs /run/lock \
        tippr-ci-base >/dev/null
    state=
    for i in $(seq 60); do
        state=$(docker exec "$name" systemctl is-system-running 2>/dev/null || true)
        case "$state" in running|degraded) break ;; esac
        sleep 2
    done
    log "systemd is $state"
    case "$state" in running|degraded) ;; *) exit 1 ;; esac
    log "copying the checkout"
    docker exec "$name" useradd -m -s /bin/bash tippr
    docker exec "$name" install -d -o tippr -g tippr /home/tippr/src/tippr
    tar -C "$root" -cf - . | docker exec -i "$name" \
        sh -c 'tar -xf - -C /home/tippr/src/tippr && chown -R tippr:tippr /home/tippr/src'
    ;;
run)
    script=${3:?name the script}
    envs=()
    for kv in "${@:4}"; do envs+=(-e "$kv"); done
    docker exec -i "${envs[@]}" "$name" bash -s < "$script"
    ;;
logs)
    dir=${3:?name the folder}
    mkdir -p "$dir"
    docker exec "$name" sh -c 'journalctl --no-pager -n 5000 > /tmp/journal.txt' || true
    docker cp "$name:/tmp/journal.txt" "$dir/" || true
    docker cp "$name:/var/log" "$dir/var-log" || true
    ;;
stop)
    docker rm -f "$name" >/dev/null 2>&1 || true
    ;;
*)
    echo "unknown command $cmd" >&2
    exit 2
    ;;
esac

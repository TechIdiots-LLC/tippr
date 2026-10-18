#!/bin/bash
# Build the tippr Proxmox LXC template: an Ubuntu 24.04 container with the
# whole site installed (the single-VM layout), ready for first boot.
#
# usage (as root, on a Linux host with Docker):
#   proxmox/build-template.sh INSTALLER_TARBALL OUTPUT.tar.zst
#
# INSTALLER_TARBALL is a release's tippr-VERSION-installer.tar.gz
# (docker/make-bundles.sh): the tippr, i18n, websockets and activity
# sources the installer uses without cloning.
#
# How: boot docker/Dockerfile.base with systemd as PID 1, unpack the sources
# into /home/tippr/src, run install-tippr.sh for a placeholder domain, then
# reset what must differ per container (passwords and secrets, ZooKeeper's
# data, SSH host keys, machine ID), arm tippr-firstboot and export the
# filesystem. OpenSearch needs vm.max_map_count >= 262144 on the host.
set -euo pipefail
tarball=$(readlink -f "$1")
# -m: the output's folder may not exist yet
output=$(readlink -m "$2")
mkdir -p "$(dirname "$output")"
here=$(cd "$(dirname "$0")" && pwd)
name=tippr-template-build-$$
placeholder=tippr.template

log() { echo "[$(date +%H:%M:%S)] $*"; }
cleanup() { docker rm -f "$name" >/dev/null 2>&1 || true; }
trap cleanup EXIT

if [ "$(sysctl -n vm.max_map_count)" -lt 262144 ]; then
    log "raising vm.max_map_count for OpenSearch"
    sysctl -w vm.max_map_count=262144
fi

log "building the base image"
docker build -q -t tippr-template-base -f "$here/Dockerfile.base" "$here"

log "booting it"
docker run -d --name "$name" --hostname "$placeholder" --privileged \
    --cgroupns=private --tmpfs /run --tmpfs /run/lock \
    tippr-template-base >/dev/null
for i in $(seq 60); do
    state=$(docker exec "$name" systemctl is-system-running 2>/dev/null || true)
    case "$state" in running|degraded) break ;; esac
    sleep 2
done
log "systemd is $state"

log "unpacking the sources"
docker exec "$name" useradd -m -s /bin/bash tippr
docker exec "$name" install -d -o tippr -g tippr /home/tippr/src
docker cp "$tarball" "$name:/tmp/tippr-installer.tar.gz"
docker exec "$name" sh -c 'tar -xzf /tmp/tippr-installer.tar.gz -C /home/tippr/src \
    && chown -R tippr:tippr /home/tippr/src && rm /tmp/tippr-installer.tar.gz'

log "running the installer (this takes a while)"
docker exec -e TIPPR_USER=tippr -e TIPPR_DOMAIN="$placeholder" \
    -e TIPPR_ENVIRONMENT=production -e TIPPR_YES=1 "$name" \
    sh -c 'cd /home/tippr/src/tippr && ./install-tippr.sh </dev/null' \
    > "$output.install.log" 2>&1 || {
        tail -50 "$output.install.log"
        log "the installer failed; full log in $output.install.log"
        exit 1
    }
log "installed; checking the site"
code=$(docker exec "$name" curl -sk -o /dev/null -w '%{http_code}' \
    --resolve "$placeholder:443:127.0.0.1" "https://$placeholder/")
[ "$code" = "200" ] || { log "the site answered $code"; exit 1; }

log "preparing for first boot"
docker cp "$here/tippr-firstboot" "$name:/usr/local/sbin/tippr-firstboot"
docker cp "$here/tippr-firstboot.service" "$name:/etc/systemd/system/tippr-firstboot.service"
# -i: the script comes on stdin
docker exec -i "$name" bash -s <<'FINALIZE'
set -e
chmod 0755 /usr/local/sbin/tippr-firstboot
systemctl stop tippr.target tippr-backup.path 2>/dev/null || true
# nothing of tippr starts until tippr-firstboot has set the container up;
# the installer it runs enables these again
systemctl disable tippr.target tippr-consumers.service tippr-backup.path \
    $(systemctl list-unit-files --plain --no-legend 'tippr-*' 'gunicorn-*' \
        | awk '$2=="enabled" {print $1}') 2>/dev/null || true
systemctl enable tippr-firstboot.service
# ZooKeeper's nodes are ACL'd to the template's password: start empty
systemctl stop zookeeper
rm -rf /var/lib/zookeeper/version-2
# OpenSearch starts empty too (first boot rebuilds the index): each
# container gets its own cluster, and its data isn't on a lower image layer
# whose copy-up trips Lucene's lock check (when testing under Docker)
systemctl stop opensearch
rm -rf /var/lib/opensearch/nodes
# per-container identity and secrets
rm -f /etc/tippr/secrets.env /etc/ssh/ssh_host_* /etc/tippr/tls/self-signed.*
: > /etc/machine-id
rm -f /var/lib/dbus/machine-id
touch /etc/tippr/firstboot-pending
cat > /etc/tippr/firstboot.env <<'ENV'
# Settings for the first boot (tippr-firstboot). Uncomment and set before
# starting the container, or leave the domain to come from its hostname.
#TIPPR_DOMAIN=forum.example.com
#TIPPR_LETSENCRYPT_EMAIL=you@example.com
# behind HAProxy on pfSense (or another proxy doing TLS): its address
#TIPPR_EXTERNAL_PROXY=192.168.1.1
#TIPPR_SITE_NAME=tippr
ENV
cat > /etc/motd <<'MOTD'

  tippr: login details are in /root/tippr-first-login.txt once the first
  boot setup has finished (journalctl -u tippr-firstboot -f to watch).
  Docs: /home/tippr/src/tippr/docs/PROXMOX.md

MOTD
# leave no build leftovers
apt-get clean
rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* /root/.bash_history
journalctl --rotate >/dev/null 2>&1 || true
journalctl --vacuum-time=1s >/dev/null 2>&1 || true
# (best effort: some services' logs can't be emptied while mounted this way)
find /var/log -type f \( -name '*.gz' -o -name '*.1' \) -delete || true
find /var/log -type f -exec truncate -s 0 {} + 2>/dev/null || true
FINALIZE

# make sure that took
docker exec "$name" test -f /etc/tippr/firstboot-pending
docker exec "$name" test ! -e /etc/tippr/secrets.env
docker exec "$name" systemctl is-enabled -q tippr-firstboot.service
! docker exec "$name" systemctl is-enabled -q tippr.target

log "stopping and exporting"
# Docker's marker file (systemd would think it's in Docker, not LXC);
# removed in the container, so the export leaves it out. pct writes its own
# hostname, hosts and resolv.conf.
docker exec "$name" rm -f /.dockerenv
docker stop -t 120 "$name" >/dev/null
docker export "$name" | zstd -q -T0 -19 --long=27 -o "$output" -f
# check the archive reads back
zstd -dc "$output" | tar -t >/dev/null
log "template: $output ($(du -h "$output" | cut -f1))"

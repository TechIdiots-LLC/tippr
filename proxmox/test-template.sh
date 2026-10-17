#!/bin/bash
# Boot a tippr Proxmox template the way a new container starts (with
# Docker standing in for pct), let tippr-firstboot set it up for a test
# domain, and check the site. Exits non-zero on failure.
#
# usage (as root, with Docker): proxmox/test-template.sh TEMPLATE.tar.zst
set -euo pipefail
template=$(readlink -f "$1")
name=tippr-template-test-$$
image=tippr-template-test:$$
domain=lxc.tippr.test

log() { echo "[$(date +%H:%M:%S)] $*"; }
cleanup() {
    docker rm -f "$name" >/dev/null 2>&1 || true
    docker rmi "$image" >/dev/null 2>&1 || true
}
trap cleanup EXIT

log "importing the template"
zstd -dc "$template" | docker import - "$image" >/dev/null

# what an admin would put in /etc/tippr/firstboot.env before starting
docker create --name "$name" --hostname tippr --privileged \
    --cgroupns=private --tmpfs /run --tmpfs /run/lock \
    "$image" /sbin/init >/dev/null
tmp=$(mktemp)
printf 'TIPPR_DOMAIN=%s\nTIPPR_SITE_NAME="Template Test"\n' "$domain" > "$tmp"
docker cp "$tmp" "$name:/etc/tippr/firstboot.env"
rm -f "$tmp"

log "booting"
docker start "$name" >/dev/null
for i in $(seq 360); do
    if docker exec "$name" test -f /root/tippr-first-login.txt 2>/dev/null; then
        break
    fi
    if docker exec "$name" systemctl is-failed -q tippr-firstboot 2>/dev/null; then
        docker exec "$name" journalctl -u tippr-firstboot --no-pager | tail -60
        log "tippr-firstboot failed"
        exit 1
    fi
    sleep 10
done
docker exec "$name" test -f /root/tippr-first-login.txt || {
    docker exec "$name" journalctl -u tippr-firstboot --no-pager | tail -60
    log "first boot didn't finish"; exit 1; }
log "first boot finished"
docker exec "$name" cat /root/tippr-first-login.txt | sed 's/^Password: .*/Password:      (hidden)/'

check() {
    docker exec "$name" curl -sk -o /dev/null -w '%{http_code}' \
        --resolve "$domain:443:127.0.0.1" "https://$domain$1"
}
for path in / /v/technology/ /login /health; do
    code=$(check "$path")
    log "GET $path -> $code"
    [ "$code" = "200" ]
done
# the template's placeholder domain and secrets are gone
docker exec "$name" sh -c "! grep -q 'tippr.template' /home/tippr/src/tippr/r2/run.ini"
docker exec "$name" sh -c "grep -q '^domain = $domain' /home/tippr/src/tippr/r2/run.ini"
docker exec "$name" test ! -f /etc/tippr/firstboot-pending
docker exec "$name" sh -c 'ls /etc/ssh/ssh_host_*_key >/dev/null'
docker exec "$name" sh -c 'test -s /etc/machine-id'
docker exec "$name" systemctl is-active -q tippr-paster.service
log "template test passed"

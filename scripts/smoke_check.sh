#!/bin/bash
# Is this server's tippr up? Run as root after installing or updating:
#
#     sudo scripts/smoke_check.sh [DOMAIN]
#
# Checks that the services this server runs are active (each one that's
# enabled, so it suits every TIPPR_ROLE) and that no tippr unit has failed,
# then, where nginx runs, that a few pages answer as they should, and that
# the web app logged no traceback meanwhile. Prints what failed and exits 1
# if anything did. CI runs it after the installer (ci-install-tippr.yml),
# and tippr-monitor every 5 minutes, from root's own copy
# (/usr/local/sbin/tippr-smoke-check, with TIPPR_INI set).

here=$(cd "$(dirname "$0")/.." && pwd)
ini=${TIPPR_INI:-$here/r2/run.ini}
domain=${1:-$(sed -n 's/^domain *= *//p' "$ini" 2>/dev/null | head -1)}
domain=${domain:-tippr.local}
started=$(date '+%Y-%m-%d %H:%M:%S')
failures=0

ok() { echo "  ok    $*"; }
bad() { echo "  FAIL  $*"; failures=$((failures + 1)); }

echo "== services"
for unit in postgresql cassandra zookeeper rabbitmq-server memcached opensearch \
        mcrouter nginx tippr-paster tippr-websockets tippr-activity \
        gunicorn-geoip tippr-consumers; do
    systemctl is-enabled --quiet "$unit" 2>/dev/null || continue
    if systemctl is-active --quiet "$unit"; then
        ok "$unit"
    else
        bad "$unit is $(systemctl is-active "$unit")"
    fi
done
unit_log() {
    journalctl -u "$1" --no-pager -n 25 2>/dev/null | sed 's/^/        /'
}
failed=$(systemctl list-units 'tippr*' --all --no-legend --plain --state=failed 2>/dev/null |
         awk '{print $1}')
for unit in $failed; do
    case "$unit" in
    tippr-job-*.service)
        # a scheduled job's last run failed: it may have run while the
        # site was still being installed or restarted, so what matters is
        # whether it works now; run it again (oneshot: start waits for it)
        echo "  ..    $unit failed; its log, then running it again:"
        unit_log "$unit"
        systemctl reset-failed "$unit"
        if timeout 900 systemctl start "$unit"; then
            ok "$unit (succeeded when run again)"
        else
            bad "$unit failed again:"
            unit_log "$unit"
        fi
        ;;
    *)
        bad "$unit failed:"
        unit_log "$unit"
        ;;
    esac
done
[ -z "$failed" ] && ok "no failed tippr units"

# a page: PATH EXPECTED_STATUS [TEXT the body must contain] [POST DATA]
page() {
    local path=$1 want=$2 text=$3 data=$4 body status
    body=$(mktemp)
    if [ -n "$data" ]; then
        status=$(curl -s -k -o "$body" -w '%{http_code}' --max-time 30 \
                 -H "Host: $domain" -d "$data" "$base$path")
    else
        status=$(curl -s -k -o "$body" -w '%{http_code}' --max-time 30 \
                 -H "Host: $domain" "$base$path")
    fi
    if [ "$status" != "$want" ]; then
        bad "$path: $status, not $want"
    elif [ -n "$text" ] && ! grep -q -- "$text" "$body"; then
        bad "$path: $status, but without '$text'"
    else
        ok "$path: $status"
    fi
    rm -f "$body"
}

if systemctl is-active --quiet nginx; then
    echo "== pages ($domain)"
    # HTTPS on a standalone server; plain HTTP behind an external proxy
    base=https://127.0.0.1
    curl -s -k -o /dev/null --max-time 10 "$base/" || base=http://127.0.0.1
    # the first request after a restart can take a while
    for _ in $(seq 30); do
        [ "$(curl -s -k -o /dev/null -w '%{http_code}' --max-time 30 \
             -H "Host: $domain" "$base/")" = 200 ] && break
        sleep 2
    done
    page / 200 'id="header"'
    page /vaults/ 200
    page /login 200 'id="login-form"'
    page /api/me.json 200 '{'
    page /v/all/.json 200 '"kind": "Listing"'
    page /smoke-check-no-such-page 404 'id="header"'
    page /favicon.ico 200
    page /api/login 200 'WRONG_PASSWORD' \
        'user=smoke_check_nobody&passwd=wrong&api_type=json'
fi

if systemctl is-active --quiet tippr-websockets; then
    status=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:9001/health)
    [ "$status" = 200 ] && ok "websockets /health: 200" || bad "websockets /health: $status"
fi

if systemctl is-active --quiet tippr-paster; then
    tracebacks=$(journalctl -u tippr-paster --no-pager --since "$started" 2>/dev/null |
                 grep -c Traceback)
    if [ "$tracebacks" -gt 0 ]; then
        bad "the web app logged $tracebacks traceback(s):"
        journalctl -u tippr-paster --no-pager --since "$started" | grep -A20 Traceback | head -60
    else
        ok "no tracebacks from the web app"
    fi
fi

if [ "$failures" -gt 0 ]; then
    echo "$failures check(s) failed"
    exit 1
fi
echo "all checks passed"

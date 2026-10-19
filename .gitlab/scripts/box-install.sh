# Run inside the systemd box (systemd-box.sh run), as root: the installer
# smoke test of .github/workflows/ci-install-tippr.yml. Installs the checkout
# in /home/tippr/src/tippr for a test domain, non-interactively, then checks
# that the site answers.
set -euo pipefail
domain=tippr.test
cd /home/tippr/src/tippr
chmod +x install/*.sh install-tippr.sh 2>/dev/null || true
TIPPR_USER=tippr TIPPR_DOMAIN=$domain TIPPR_YES=1 ./install-tippr.sh </dev/null

check() {
    curl -sk -o /dev/null -w '%{http_code}' \
        --resolve "$domain:443:127.0.0.1" "https://$domain$1"
}
for path in / /v/technology/ /login /health; do
    code=$(check "$path")
    echo "GET $path -> $code"
    [ "$code" = "200" ]
done
systemctl is-active tippr-paster.service
echo "installer smoke test passed"

#!/bin/bash
# Make a release's downloadable files from a built image:
#
#   tippr-VERSION-compose.tar.gz    docker-compose.yml, Caddyfile, .env.example
#                                   (pointing at IMAGE:VERSION) and a README
#   tippr-VERSION-installer.tar.gz  tippr, i18n, websockets and activity as
#                                   built in the image (static files,
#                                   translations, Cython modules included),
#                                   for install-tippr.sh without cloning
#   SHA256SUMS
#
# usage: make-bundles.sh VERSION IMAGE BUILT_IMAGE OUTDIR
set -euo pipefail
version=$1 image=$2 built=$3 out=$4
here=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$out"
out=$(cd "$out" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# compose bundle
dir="$work/tippr-$version-compose"
mkdir -p "$dir"
cp "$here/docker-compose.yml" "$here/Caddyfile" "$here/README.md" "$dir/"
sed -e "s|^TIPPR_IMAGE=.*|TIPPR_IMAGE=$image|" \
    -e "s|^TIPPR_VERSION=.*|TIPPR_VERSION=$version|" \
    "$here/.env.example" > "$dir/.env.example"
tar -C "$work" -czf "$out/tippr-$version-compose.tar.gz" "tippr-$version-compose"

# installer tarball: the image's source tree, without generated configs
container=$(docker create "$built")
docker cp "$container:/opt/tippr/src" "$work/src"
docker rm "$container" >/dev/null
rm -f "$work/src/websockets/tippr.ini" "$work/src/websockets/tippr_secrets.json" \
      "$work/src/activity/tippr.ini" "$work/src/tippr/r2/run.ini"
echo "$version" > "$work/src/tippr/VERSION"
tar -C "$work/src" --owner=0 --group=0 \
    -czf "$out/tippr-$version-installer.tar.gz" tippr i18n websockets activity

(cd "$out" && sha256sum tippr-*.tar.gz > SHA256SUMS)
ls -la "$out"

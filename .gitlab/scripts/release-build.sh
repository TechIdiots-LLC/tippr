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
# GitLab port of the build and proxmox jobs of .github/workflows/release.yml,
# in one job (the template is too big to pass between jobs as an artifact):
#
#   1. build docker/Dockerfile and smoke-test the compose stack with it
#   2. make the compose bundle and installer tarball (docker/make-bundles.sh)
#   3. build the Proxmox template from that tarball and test its first boot
#   4. when publishing (RELEASE_PUBLISH=true from release-check.ps1): push the
#      image and upload the files to the generic package registry, listing
#      them in release-files.txt for publish-release.ps1
#
# The image goes to this project's container registry when it has one, and
# to Docker Hub only when DOCKERHUB_USERNAME and DOCKERHUB_TOKEN are set
# (DOCKERHUB_IMAGE, default techidiotsllc/tippr, names it there; the compose
# bundle points at that name either way).
set -euo pipefail
version=${RELEASE_VERSION:?run release-check first}
publish=${RELEASE_PUBLISH:-false}
dockerhub_image=${DOCKERHUB_IMAGE:-techidiotsllc/tippr}
dist=$CI_PROJECT_DIR/dist
log() { echo "[$(date +%H:%M:%S)] $*"; }
mkdir -p "$dist"

log "building the image (version $version)"
docker build -f docker/Dockerfile -t tippr:release \
    --build-arg VERSION="$version" --build-arg REVISION="$CI_COMMIT_SHA" \
    --build-arg I18N_REF="${I18N_REF:-master}" \
    --build-arg WEBSOCKETS_REF="${WEBSOCKETS_REF:-master}" \
    --build-arg ACTIVITY_REF="${ACTIVITY_REF:-master}" .

log "smoke-testing the compose stack"
cat > docker/.env <<ENV
TIPPR_DOMAIN=tippr.test
TIPPR_DB_PASSWORD=$(openssl rand -hex 16)
TIPPR_AMQP_PASSWORD=$(openssl rand -hex 16)
TIPPR_TLS=internal
TIPPR_IMAGE=tippr
TIPPR_VERSION=release
TIPPR_ENVIRONMENT=production
TIPPR_CASSANDRA_HEAP=1G
TIPPR_OPENSEARCH_HEAP=512m
ENV
# the stack's ports are published on the Docker-in-Docker service
SMOKE_ADDRESS=$(getent ahostsv4 docker | awk 'NR==1 {print $1}')
export SMOKE_ADDRESS
if ! bash docker/smoke-test.sh; then
    (cd docker && docker compose logs --no-color --tail 200)
    exit 1
fi
(cd docker && docker compose down -v)

log "making the bundles"
bash docker/make-bundles.sh "$version" "$dockerhub_image" tippr:release "$dist"
docker image prune -f >/dev/null

log "building the Proxmox template"
template=$dist/tippr-$version-proxmox-amd64.tar.zst
bash proxmox/build-template.sh "$dist/tippr-$version-installer.tar.gz" "$template" || {
    tail -200 "$template.install.log" || true
    exit 1
}
mv "$template.install.log" "$CI_PROJECT_DIR/template-install.log"
log "testing its first boot"
bash proxmox/test-template.sh "$template"

(cd "$dist" && rm -f SHA256SUMS && sha256sum tippr-* > SHA256SUMS && cat SHA256SUMS)

if [ "$publish" != "true" ]; then
    log "not publishing (dry run, or already released)"
    exit 0
fi

tags=$version
# 1.2.3 also as 1.2 and latest; pre-releases (1.2.3-rc1) only as is
if [[ "$version" =~ ^([0-9]+)\.([0-9]+)\.[0-9]+$ ]]; then
    tags="$tags ${BASH_REMATCH[1]}.${BASH_REMATCH[2]} latest"
fi
push() {
    for tag in $tags; do
        docker tag tippr:release "$1:$tag"
        docker push "$1:$tag"
    done
}
if [ -n "${CI_REGISTRY:-}" ]; then
    log "pushing to $CI_REGISTRY_IMAGE"
    echo "$CI_REGISTRY_PASSWORD" | docker login -u "$CI_REGISTRY_USER" --password-stdin "$CI_REGISTRY"
    push "$CI_REGISTRY_IMAGE"
fi
if [ -n "${DOCKERHUB_USERNAME:-}" ] && [ -n "${DOCKERHUB_TOKEN:-}" ]; then
    log "pushing to Docker Hub as $dockerhub_image"
    echo "$DOCKERHUB_TOKEN" | docker login -u "$DOCKERHUB_USERNAME" --password-stdin
    push "$dockerhub_image"
else
    log "DOCKERHUB_USERNAME/DOCKERHUB_TOKEN not set: not pushing to Docker Hub"
fi

log "uploading the release files"
: > "$CI_PROJECT_DIR/release-files.txt"
for file in "$dist"/*; do
    base=$(basename "$file")
    curl -fsS --retry 3 -H "JOB-TOKEN: $CI_JOB_TOKEN" --upload-file "$file" \
        "$CI_API_V4_URL/projects/$CI_PROJECT_ID/packages/generic/tippr/$version/$base" >/dev/null
    echo "$base" >> "$CI_PROJECT_DIR/release-files.txt"
    log "uploaded $base"
done

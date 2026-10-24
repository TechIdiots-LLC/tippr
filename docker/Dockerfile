# syntax=docker/dockerfile:1.7
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

#
# The tippr application image: r2 (web app, queue consumers, scheduled jobs)
# and the websockets and activity services, all from one image. The data
# stores (PostgreSQL, Cassandra, ZooKeeper, RabbitMQ, memcached, OpenSearch,
# Redis) are separate containers; see docker/docker-compose.yml.
#
# Build from the repository root:
#
#   docker build -f docker/Dockerfile -t tippr .
#
# The i18n, websockets and activity repositories are cloned at the refs
# below. To build with a local checkout instead, pass it as a build context
# with the stage's name, e.g. --build-context i18n=../tippr-i18n

ARG UBUNTU=ubuntu:24.04

###############################################################################
# Companion repositories (each can be replaced with --build-context NAME=DIR)
###############################################################################
FROM alpine/git:latest AS git
FROM git AS i18n-clone
ARG I18N_REPO=https://github.com/TechIdiots-LLC/tippr-i18n.git
ARG I18N_REF=master
RUN git clone --depth 1 --branch "$I18N_REF" "$I18N_REPO" /src && rm -rf /src/.git

FROM git AS websockets-clone
ARG WEBSOCKETS_REPO=https://github.com/TechIdiots-LLC/tippr-service-websockets.git
ARG WEBSOCKETS_REF=master
RUN git clone --depth 1 --branch "$WEBSOCKETS_REF" "$WEBSOCKETS_REPO" /src && rm -rf /src/.git

FROM git AS activity-clone
ARG ACTIVITY_REPO=https://github.com/TechIdiots-LLC/tippr-service-activity.git
ARG ACTIVITY_REF=master
RUN git clone --depth 1 --branch "$ACTIVITY_REF" "$ACTIVITY_REPO" /src && rm -rf /src/.git

# each is the repository at /, like a directory given with --build-context
FROM scratch AS i18n
COPY --from=i18n-clone /src /
FROM scratch AS websockets
COPY --from=websockets-clone /src /
FROM scratch AS activity
COPY --from=activity-clone /src /

###############################################################################
# Build: Python packages, Cython extensions, translations, static files
###############################################################################
FROM ${UBUNTU} AS build
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential python3.12 python3.12-dev python3.12-venv \
        git ca-certificates curl gperf gettext make \
        libpq-dev libmemcached-dev zlib1g-dev libgeoip-dev libsnappy-dev \
        libxml2-dev libxslt1-dev libjpeg-dev libffi-dev libssl-dev \
        nodejs npm optipng jpegoptim thrift-compiler libpcre3-dev \
    && rm -rf /var/lib/apt/lists/*

ENV TIPPR_HOME=/opt/tippr \
    VIRTUAL_ENV=/opt/tippr/venv \
    PATH=/opt/tippr/venv/bin:/opt/tippr/node-tools/node_modules/.bin:$PATH
RUN python3.12 -m venv $VIRTUAL_ENV \
    && pip install --no-cache-dir --upgrade pip 'setuptools<81' wheel

# Pinned dependencies first, so code changes don't reinstall them
COPY install/requirements.txt /tmp/requirements.txt
# --no-deps: the list is a complete freeze of a working install, which pip's
# resolver would reject (the installer forces a newer packaging than some
# packages declare)
RUN pip install --no-cache-dir --no-deps -r /tmp/requirements.txt

# LESS 1.4 and uglify-js 1.x, the versions the stylesheets and scripts were
# written for (as install/tippr.sh uses)
RUN npm install --no-audit --no-fund --prefix /opt/tippr/node-tools \
        less@1.4.2 uglify-js@1.3.5

COPY --from=i18n / /opt/tippr/src/i18n
COPY --from=websockets / /opt/tippr/src/websockets
COPY --from=activity / /opt/tippr/src/activity
COPY . /opt/tippr/src/tippr

WORKDIR /opt/tippr/src
# the services still import baseplate's pre-1.0 module path
RUN sed -i 's/baseplate\.integration\./baseplate.frameworks./g' \
        websockets/setup.py activity/setup.py \
    && cd tippr/r2 && python setup.py build && pip install --no-cache-dir --no-build-isolation --no-deps -e . \
    && cd /opt/tippr/src/i18n && pip install --no-cache-dir --no-build-isolation --no-deps -e . \
    && cd /opt/tippr/src/websockets && pip install --no-cache-dir --no-build-isolation --no-deps -e . \
    && cd /opt/tippr/src/activity && pip install --no-cache-dir --no-build-isolation --no-deps -e .

ENV PYTHONPATH=/opt/tippr/src/tippr:/opt/tippr/src/tippr/r2 \
    NODE_PATH=/opt/tippr/node-tools/node_modules
RUN make -C /opt/tippr/src/i18n clean all
WORKDIR /opt/tippr/src/tippr/r2
# a throwaway ini: Makefile.py loads r2's config to find plugins
RUN cp example.ini run.ini \
    && make clean pyx \
    && make clean_static \
    && (make static LESSC="node /opt/tippr/src/tippr/scripts/lessc.js" \
        || make static LESSC="node /opt/tippr/src/tippr/scripts/lessc.js") \
    && test -s "$(readlink -f build/public/static/tippr.css)" \
    && rm -f run.ini \
    && for step in i18n pyx static; do \
           bash /opt/tippr/src/tippr/scripts/build-fingerprint /opt/tippr/src $step record; \
       done
# (the fingerprints go in the release's installer tarball: an upgrade from it
# skips building what's built here, scripts/build-fingerprint)

###############################################################################
# Runtime
###############################################################################
FROM ${UBUNTU}
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.12 libpython3.12 ca-certificates curl tini \
        libpq5 libmemcached11t64 libgeoip1t64 libsnappy1v5 \
        libxml2 libxslt1.1 libjpeg8 optipng jpegoptim geoip-database \
        postgresql-client-16 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 999 --user-group --home-dir /opt/tippr tippr

COPY --from=build --chown=tippr:tippr /opt/tippr /opt/tippr

ENV TIPPR_HOME=/opt/tippr \
    VIRTUAL_ENV=/opt/tippr/venv \
    PATH=/opt/tippr/venv/bin:$PATH \
    PYTHONPATH=/opt/tippr/src/tippr:/opt/tippr/src/tippr/r2 \
    PYTHONUNBUFFERED=1 \
    TIPPR_INI=/opt/tippr/src/tippr/r2/run.ini \
    TIPPR_CONFIG_DIR=/config \
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus

RUN install -d -o tippr -g tippr /config /srv/www/media /tmp/prometheus \
    && printf '#!/bin/sh\n# tippr ROLE|run|shell ... inside a running container\nexec /opt/tippr/venv/bin/python /opt/tippr/src/tippr/docker/tippr_docker.py "$@"\n' \
        > /usr/local/bin/tippr && chmod 0755 /usr/local/bin/tippr

ARG VERSION=dev
ARG REVISION=unknown
LABEL org.opencontainers.image.title="tippr" \
      org.opencontainers.image.description="tippr community site (r2): web app, consumers, jobs, websockets, activity" \
      org.opencontainers.image.source="https://github.com/TechIdiots-LLC/tippr" \
      org.opencontainers.image.licenses="CPAL-1.0" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}"
ENV TIPPR_VERSION=${VERSION} \
    TIPPR_REVISION=${REVISION}

USER tippr
WORKDIR /opt/tippr/src/tippr/r2
VOLUME ["/config", "/srv/www/media"]
EXPOSE 8001 9001 9002
ENTRYPOINT ["/usr/bin/tini", "--", "/opt/tippr/venv/bin/python", "/opt/tippr/src/tippr/docker/tippr_docker.py"]
CMD ["web"]

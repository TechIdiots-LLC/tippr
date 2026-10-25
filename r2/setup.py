#!/usr/bin/env python
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0. (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://code.reddit.com/LICENSE. The License is based on the Mozilla Public
# License Version 1.1, but Sections 14 and 15 have been added to cover use of
# software over a computer network and provide for limited attribution for the
# Original Developer. In addition, Exhibit A has been modified to be consistent
# with Exhibit B.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is reddit.
#
# The Original Developer is the Initial Developer.  The Initial Developer of
# the Original Code is reddit Inc.
#
# All portions of the code written by reddit are Copyright (c) 2006-2015 reddit
# Inc. All Rights Reserved.
# 
# Portions created by TechIdiots LLC (Tippr) are Copyright (c) 2026
# TechIdiots LLC. All Rights Reserved.
###############################################################################

import fnmatch
import os
import sys

from setuptools import Extension, find_packages, setup

# Avoid doing expensive or build-time only operations during metadata
# generation (e.g. `egg_info`) which may run setup.py without the build
# commands. Only attempt to locate and cythonize .pyx files when an actual
# build is requested.
pyx_extensions = []
# command class mapping used by setuptools (populated below if Thrift present)
commands = {}
build_commands = {"build", "build_ext", "bdist_wheel", "bdist_egg", "install",
                  "develop", "editable_wheel"}
if build_commands.intersection(sys.argv):
    # the .pyx modules (sorts, sgm, wrapped, utils, comment trees, mr_tools)
    # have no pure-Python copies, so the site can't run without them
    try:
        from Cython.Build import cythonize
    except ImportError:
        sys.exit("Building tippr needs Cython (pip install cython).")
    pyx_files = []
    for root, directories, files in os.walk('.'):
        for f in fnmatch.filter(files, '*.pyx'):
            pyx_files.append(os.path.join(root, f))
    pyx_extensions = cythonize(
        pyx_files,
        compiler_directives={"language_level": "3"},
    )


# guard against import errors in case this is the first run of setup.py and we
# don't have any dependencies (including baseplate) yet
try:
    # baseplate 1.0+ moved integration -> frameworks
    from baseplate.frameworks.thrift.command import ThriftBuildPyCommand
except Exception:
    try:
        # fallback for older baseplate versions
        from baseplate.integration.thrift.command import ThriftBuildPyCommand
    except Exception:
        print("Cannot find Baseplate. Skipping Thrift build.")
        ThriftBuildPyCommand = None

if ThriftBuildPyCommand is not None:
    commands["build_py"] = ThriftBuildPyCommand


setup(
    name="r2",
    # Provide a valid version string to satisfy packaging/version
    version="0.0.0",
    install_requires=[
        "Routes",
        "baseplate",
        "mako>=0.5",
        # boto3 replaces boto (which is Python 2 only)
        "boto3",
        "pytz",
        # pycrypto is deprecated and doesn't build on modern systems
        # pycryptodome is a drop-in replacement with the same API
        "pycryptodome",
        # passkeys (WebAuthn) for two-factor sign-in (r2.lib.passkeys)
        "webauthn",
        "Babel>=1.0",
        "cython>=0.14",
        "SQLAlchemy",
        "beautifulsoup4",
        "chardet",
        "psycopg2",
        # Modern Cassandra driver (DataStax) replaces pycassa
        "cassandra-driver",
        # Modern captcha library (Python 3 compatible) replaces pycaptcha
        "captcha",
        # amqp is the modern Python 3 replacement for amqplib
        "amqp",
        # py-bcrypt works but bcrypt is the modern maintained version
        "bcrypt",
        # markdown (r2.lib.markdown), in place of reddit's snudown
        "markdown-it-py",
        "linkify-it-py",
        "lxml",
        "kazoo",
        "stripe",
        "requests",
        "tinycss2",
        "unidecode",
        # :shortcode: emoji in comments and posts (r2.lib.filters.emojify_html)
        "emoji",
        "PyYAML",
        "Pillow",
        # pylibmc requires libmemcached-dev on Ubuntu: apt install libmemcached-dev
        "pylibmc",
        "webob",
        "webtest",
        # python-snappy requires libsnappy-dev on Ubuntu: apt install libsnappy-dev
        "python-snappy",
        # httpagentparser - remove version pin for latest Python 3 compatible version
        "httpagentparser",
        # raven is deprecated, sentry-sdk is the replacement
        # Using raven for now as it still works, but consider migrating to sentry-sdk
        "raven",
        # Test dependencies (formerly in tests_require, now in install_requires for modern setuptools)
        "mock",
        "pytest",
        "coverage",
    ],
    packages=find_packages(exclude=["ez_setup"]),
    cmdclass=commands,
    ext_modules=pyx_extensions + [
        Extension(
            "Cfilters",
            sources=[
                "r2/lib/c/filters.c",
            ]
        ),
    ],
    entry_points="""
    [paste.app_factory]
    main=r2:make_app
    [paste.filter_app_factory]
    gzip = r2.lib.gzipper:make_gzip_middleware
    [r2.provider.media]
    s3 = r2.lib.providers.media.s3:S3MediaProvider
    filesystem = r2.lib.providers.media.filesystem:FileSystemMediaProvider
    [r2.provider.cdn]
    fastly = r2.lib.providers.cdn.fastly:FastlyCdnProvider
    cloudflare = r2.lib.providers.cdn.cloudflare:CloudFlareCdnProvider
    null = r2.lib.providers.cdn.null:NullCdnProvider
    [r2.provider.auth]
    cookie = r2.lib.providers.auth.cookie:CookieAuthenticationProvider
    http = r2.lib.providers.auth.http:HttpAuthenticationProvider
    [r2.provider.search]
    solr = r2.lib.providers.search.solr:SolrSearchProvider
    opensearch = r2.lib.providers.search.opensearch:OpenSearchProvider
    [r2.provider.image_resizing]
    imgix = r2.lib.providers.image_resizing.imgix:ImgixImageResizingProvider
    no_op = r2.lib.providers.image_resizing.no_op:NoOpImageResizingProvider
    unsplashit = r2.lib.providers.image_resizing.unsplashit:UnsplashitImageResizingProvider
    [r2.provider.email]
    null = r2.lib.providers.email.null:NullEmailProvider
    mailgun = r2.lib.providers.email.mailgun:MailgunEmailProvider
    """,
)

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
###############################################################################

"""Generates all the data used in making sitemaps and sitemap links.

Currently only supports vault links but will soon support comment links.
"""

import tempfile

import boto3
from pylons import app_globals as g

from r2.lib.hadoop_decompress import hadoop_decompress


def _read_subreddit_etl_from_s3(s3path):
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(s3path.bucket)
    objects = bucket.objects.filter(Prefix=s3path.key)

    key_count = 0
    for obj in objects:
        g.log.info("Importing key %s", obj.key)

        with tempfile.TemporaryFile(mode='w+b') as ntf_download:
            with tempfile.TemporaryFile(mode='w+b') as ntf_decompress:

                # download it
                g.log.debug("Downloading %s", obj.key)
                obj.Object().download_fileobj(ntf_download)

                # decompress it
                ntf_download.flush()
                ntf_download.seek(0)
                g.log.debug("Decompressing %s", obj.key)
                hadoop_decompress(ntf_download, ntf_decompress)
                ntf_decompress.flush()
                ntf_decompress.seek(0)

                # import it
                g.log.debug("Starting import of %s", obj.key)
                yield from ntf_decompress
        key_count += 1

    if key_count == 0:
        raise ValueError('{} contains no readable keys.'.format(s3path))


def find_all_subreddits(s3path):
    for line in _read_subreddit_etl_from_s3(s3path):
        _, vault, __ = line.split('\x01')
        yield vault

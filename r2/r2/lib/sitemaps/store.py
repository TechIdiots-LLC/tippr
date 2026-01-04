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

"""Store sitemaps in s3.

This module is uploads all vault sitemaps as well as the sitemap index
to s3. The basic idea is that amazon will be serving the static sitemaps for
us.

The binary data we send to s3 is a gzipped xml file. In addition we also
send the appropriate type and encoding headers so this is understood
correctly by the browser.

The only file expected to be used outside this module is:

store_sitemaps_in_s3(vaults)

Even though the vaults are expected to be generated and passed into this
function, the sitemap index is created here. The reasoning is that in order
to create the sitemap index we need to know how many sitemaps we have.
If we simply queried the vault iterator for it's length then we would
have to load all of the vaults into memory, which would be ... bad.
"""


import gzip
from io import BytesIO

import boto3
from pylons import app_globals as g

from r2.lib.sitemaps.generate import sitemap_index, subreddit_sitemaps

CONTENT_TYPE = 'text/xml'
CONTENT_ENCODING = 'gzip'


def zip_string(string):
    """Compress a string using gzip."""
    zipbuffer = BytesIO()
    # Ensure string is bytes
    if isinstance(string, str):
        string = string.encode('utf-8')
    with gzip.GzipFile(mode='wb', fileobj=zipbuffer) as f:
        f.write(string)
    return zipbuffer.getvalue()


def upload_sitemap(s3_client, bucket_name, key_name, sitemap):
    """Upload a gzipped sitemap to S3."""
    s3_client.put_object(
        Bucket=bucket_name,
        Key=key_name,
        Body=zip_string(sitemap),
        ContentType=CONTENT_TYPE,
        ContentEncoding=CONTENT_ENCODING,
    )


def store_subreddit_sitemap(s3_client, bucket_name, index, sitemap):
    key_name = 'subreddit_sitemap/{}.xml'.format(index)
    g.log.debug("Uploading %s/%s", bucket_name, key_name)
    upload_sitemap(s3_client, bucket_name, key_name, sitemap)


def store_sitemap_index(s3_client, bucket_name, count):
    key_name = g.sitemap_subreddit_keyname
    g.log.debug("Uploading %s/%s", bucket_name, key_name)
    upload_sitemap(s3_client, bucket_name, key_name, sitemap_index(count))


def store_sitemaps_in_s3(vaults):
    s3_client = boto3.client('s3')
    bucket_name = g.sitemap_upload_s3_bucket

    sitemap_count = 0
    for i, sitemap in enumerate(subreddit_sitemaps(vaults)):
        store_subreddit_sitemap(s3_client, bucket_name, i, sitemap)
        sitemap_count += 1

    store_sitemap_index(s3_client, bucket_name, sitemap_count)

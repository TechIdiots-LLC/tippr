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

import io
import mimetypes
import os
import re

from botocore.exceptions import ClientError
from pylons import app_globals as g

from r2.lib import object_storage
from r2.lib.configparse import ConfigValue
from r2.lib.providers.media import MediaProvider

_NEVER = "Thu, 31 Dec 2037 23:59:59 GMT"


class S3MediaProvider(MediaProvider):
    """A media provider using Amazon S3 or any S3-compatible service
    (Garage, SeaweedFS, MinIO, Backblaze B2 …): see r2.lib.object_storage
    for the endpoint, region and public URL settings.

    Credentials for uploading objects can be provided via `S3KEY_ID` and
    `S3SECRET_KEY`. If not provided, boto3 will search for credentials in
    alternate venues including environment variables and EC2 instance roles if
    on Amazon EC2.

    The `s3_media_direct` option configures how URLs are generated. When true,
    URLs will use Amazon's domain name meaning a zero-DNS configuration. If
    false, the bucket name will be assumed to be a valid domain name that is
    appropriately CNAME'd to S3 and URLs will be generated accordingly.

    If more than one bucket is provided in `s3_media_buckets`, items will be
    sharded out to the various buckets based on their filename. This allows for
    hostname parallelization in the non-direct HTTP case.

    """
    config = {
        ConfigValue.str: [
            "S3KEY_ID",
            "S3SECRET_KEY",
            "s3_media_domain",
            # S3-compatible services (r2.lib.object_storage)
            "s3_endpoint_url",
            "s3_region",
            "s3_addressing_style",
            "s3_use_acls",
            "s3_public_url",
            "s3_browser_endpoint_url",
            "s3_client_uploads_bucket",
        ],
        ConfigValue.bool: [
            "s3_media_direct",
        ],
        ConfigValue.tuple: [
            "s3_media_buckets",
            "s3_image_buckets",
        ],
    }

    buckets = {
        'thumbs': 's3_media_buckets',
        'stylesheets': 's3_media_buckets',
        'icons': 's3_media_buckets',
        'previews': 's3_image_buckets',
    }

    def _get_s3_client(self):
        return object_storage.client()

    def _get_s3_resource(self):
        return object_storage.resource()

    def _get_bucket(self, bucket_name):
        """Get a bucket object."""
        s3 = self._get_s3_resource()
        return s3.Bucket(bucket_name)

    def _get_bucket_key_from_url(self, url):
        bucket_name, key_name = object_storage.bucket_and_key(url)
        if bucket_name:
            return bucket_name, key_name
        # URLs stored before s3_public_url / s3_endpoint_url were set
        if g.s3_media_domain in url:
            r_bucket = re.compile(r'.*\://(?:%s.)?([^\/]+)' % g.s3_media_domain)
        else:
            r_bucket = re.compile(r'.*\://?([^\/]+)')

        bucket_name = r_bucket.findall(url)[0]
        key_name = url.split('/')[-1]

        return bucket_name, key_name

    def make_inaccessible(self, url):
        """Make the content unavailable, but do not remove."""
        bucket_name, key_name = self._get_bucket_key_from_url(url)

        timer = g.stats.get_timer("providers.s3.key_set_private")
        timer.start()

        try:
            s3 = self._get_s3_client()
            if object_storage.use_acls():
                # Set the object ACL to private
                s3.put_object_acl(
                    Bucket=bucket_name,
                    Key=key_name,
                    ACL='private'
                )
            else:
                # services without ACLs (public buckets): set it aside
                # under a private prefix instead
                s3.copy_object(Bucket=bucket_name, Key="private/" + key_name,
                               CopySource={"Bucket": bucket_name,
                                           "Key": key_name})
                s3.delete_object(Bucket=bucket_name, Key=key_name)
        except ClientError:
            # Object may not exist
            pass

        timer.stop()

        return True

    def put(self, category, name, contents, headers=None):
        # categories reddit didn't have (site logos …) go to the media buckets
        buckets = getattr(g, self.buckets.get(category, "s3_media_buckets"))
        # choose a bucket based on the filename
        name_without_extension = os.path.splitext(name)[0]
        index = ord(name_without_extension[-1]) % len(buckets)
        bucket_name = buckets[index]

        # guess the mime type
        mime_type, encoding = mimetypes.guess_type(name)

        # build up the extra args for S3
        extra_args = {
            'ContentType': mime_type or 'application/octet-stream',
            'CacheControl': 'public, max-age=31536000',
        }
        if object_storage.use_acls():
            # Amazon S3 (other services make the bucket public instead)
            extra_args['ACL'] = 'public-read'
            extra_args['Expires'] = _NEVER
        if headers:
            # Map common header names to boto3 extra args
            header_mapping = {
                'Content-Type': 'ContentType',
                'Content-Encoding': 'ContentEncoding',
                'Content-Disposition': 'ContentDisposition',
                'Cache-Control': 'CacheControl',
            }
            for header_name, value in headers.items():
                if header_name in header_mapping:
                    extra_args[header_mapping[header_name]] = value

        # send the key
        s3 = self._get_s3_client()

        if isinstance(contents, str):
            contents = contents.encode('utf-8')

        if isinstance(contents, bytes):
            body = io.BytesIO(contents)
        else:
            body = contents

        s3.upload_fileobj(
            body,
            bucket_name,
            name,
            ExtraArgs=extra_args,
        )

        return object_storage.public_url(bucket_name, name)

    def purge(self, url):
        """Deletes the key as specified by the url"""
        bucket_name, key_name = self._get_bucket_key_from_url(url)

        timer = g.stats.get_timer("providers.s3.key_set_private")
        timer.start()

        try:
            s3 = self._get_s3_client()
            s3.delete_object(Bucket=bucket_name, Key=key_name)
        except ClientError:
            # Object may not exist
            pass

        timer.stop()

        return True

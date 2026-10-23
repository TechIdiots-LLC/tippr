#!/usr/bin/python
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


import argparse
import datetime
import hashlib
import mimetypes
import os
import urllib.parse

import boto3

NEVER = datetime.datetime(2037, 12, 31, 23, 59, 59,
                          tzinfo=datetime.timezone.utc)


def upload(static_root, bucket_url):
    """Upload the built static files under static_root to an S3 bucket
    (s3://bucket/prefix), skipping files already there unchanged.
    Credentials come from boto3's usual places (environment, ~/.aws)."""
    bucket = boto3.resource("s3").Bucket(bucket_url.netloc)
    prefix = bucket_url.path.lstrip("/")

    # build a list of files already in the bucket
    print("checking existing files on s3...")
    remote_files = {obj.key: obj.e_tag.strip('"')
                    for obj in bucket.objects.filter(Prefix=prefix)}

    # upload local files not already in the bucket
    for root, dirs, files in os.walk(static_root):
        for file in files:
            absolute_path = os.path.join(root, file)
            relative_path = os.path.relpath(absolute_path, start=static_root)
            key_name = os.path.join(prefix, relative_path).lstrip("/")

            type, encoding = mimetypes.guess_type(file)
            if not type:
                continue
            extra = {"ContentType": type, "Expires": NEVER,
                     "ACL": "public-read"}
            if encoding:
                extra["ContentEncoding"] = encoding

            with open(absolute_path, 'rb') as f:
                data = f.read()

            # don't upload the file if it already exists unmodified in the
            # bucket (a single-part upload's ETag is the MD5 of the file)
            if remote_files.get(key_name) == hashlib.md5(data).hexdigest():
                continue

            print("uploading", key_name, "to S3...")
            bucket.put_object(Key=key_name, Body=data, **extra)

    print("all done")


def s3_url(text):
    parsed = urllib.parse.urlparse(text)
    if parsed.scheme != "s3":
        raise ValueError("not an s3 url")
    if parsed.params or parsed.query or parsed.fragment:
        raise ValueError("params, query, and fragment not supported")
    return parsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("bucket", type=s3_url)
    args = parser.parse_args()
    upload(args.root, args.bucket)


if __name__ == "__main__":
    main()

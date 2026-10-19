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

"""Copy the media in /srv/www/media into an S3-compatible bucket, before
switching the site to it (docs/STORAGE.md).

Run it once the installer has the S3 connection (TIPPR_S3_ENDPOINT,
TIPPR_S3_KEY_ID, TIPPR_S3_SECRET) but before TIPPR_MEDIA_STORAGE=s3:

    sudo env MEDIA_BUCKET=tippr-media tippr-run /home/tippr/src/tippr/scripts/migrate_media_to_s3.py
    sudo env MEDIA_BUCKET=tippr-media TIPPR_ALLOW_MUTATE=1 tippr-run /home/tippr/src/tippr/scripts/migrate_media_to_s3.py

The first is a dry run: it checks the bucket can be written and counts what
would be copied. Files are copied under the same names, so their addresses
(https://<site>/media/<name>) stay the same once nginx serves /media/ from
the bucket. Files already in the bucket with the same size are skipped, so
it's safe to run again, e.g. once more right after switching, for anything
uploaded in between.

Settings (environment): MEDIA_BUCKET (default: s3_media_buckets, else
s3_client_uploads_bucket), MEDIA_DIR (default: media_fs_root, else
/srv/www/media).
"""

import mimetypes
import os
import sys

from botocore.exceptions import ClientError
from pylons import app_globals as g

from r2.lib import object_storage


def main():
    bucket = (os.environ.get("MEDIA_BUCKET") or
              (object_storage.configured_buckets() or [None])[0])
    media_dir = (os.environ.get("MEDIA_DIR") or
                 g.config.get("media_fs_root") or "/srv/www/media")
    copying = os.environ.get("TIPPR_ALLOW_MUTATE") == "1"
    if not bucket:
        sys.exit("Give MEDIA_BUCKET (or set TIPPR_S3_MEDIA_BUCKET / "
                 "TIPPR_S3_UPLOADS_BUCKET in the installer).")
    if not os.path.isdir(media_dir):
        sys.exit("%s isn't a directory" % media_dir)

    print("%s %s -> bucket %s at %s" % (
        "Copying" if copying else "Dry run (TIPPR_ALLOW_MUTATE=1 to copy):",
        media_dir, bucket, object_storage.endpoint_url() or "Amazon S3"))
    problem = object_storage.check(bucket)
    if problem:
        sys.exit("Can't write to the bucket: %s" % problem)

    s3 = object_storage.client()
    copied = skipped = failed = 0
    total_bytes = 0
    for root, _dirs, files in os.walk(media_dir):
        for name in sorted(files):
            path = os.path.join(root, name)
            key = os.path.relpath(path, media_dir).replace(os.sep, "/")
            size = os.path.getsize(path)
            try:
                head = s3.head_object(Bucket=bucket, Key=key)
                if head.get("ContentLength") == size:
                    skipped += 1
                    continue
            except ClientError:
                pass
            if not copying:
                copied += 1
                total_bytes += size
                continue
            extra = {
                "ContentType": (mimetypes.guess_type(name)[0] or
                                "application/octet-stream"),
                "CacheControl": "public, max-age=31536000",
            }
            if object_storage.use_acls():
                extra["ACL"] = "public-read"
            try:
                s3.upload_file(path, bucket, key, ExtraArgs=extra)
                copied += 1
                total_bytes += size
            except Exception as e:
                failed += 1
                print("FAILED %s: %s" % (key, e))

    print("%s %d files (%.1f MB), %d already there, %d failed" % (
        "copied" if copying else "would copy", copied,
        total_bytes / 1024.0 / 1024.0, skipped, failed))
    if failed:
        sys.exit(1)


main()

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

"""Check where the site keeps media, and that it works end to end
(docs/STORAGE.md):

    sudo tippr-run /home/tippr/src/tippr/scripts/check_media_storage.py

It saves a small test file the way uploads are saved, checks it's in the
bucket (and not in the media folder on disk) with S3 storage, fetches it
from this server's nginx at /media/ like a browser would, then deletes it.
"""

import os
import time
import uuid

import requests
import urllib3
from pylons import app_globals as g

from r2.lib.providers.media.s3 import S3MediaProvider

MEDIA_DIR = getattr(g, "media_fs_root", None) or "/srv/www/media"


def fetch(name):
    """The test file from this server's nginx, as a browser would get it."""
    urllib3.disable_warnings()
    for scheme in ("https", "http"):
        try:
            resp = requests.get("%s://127.0.0.1/media/%s" % (scheme, name),
                                headers={"Host": g.domain}, timeout=10,
                                verify=False, allow_redirects=False)
        except requests.RequestException:
            continue
        if resp.status_code not in (301, 302, 308):
            return resp
    return None


def main():
    provider = g.media_provider
    s3 = isinstance(provider, S3MediaProvider)
    print("media storage: %s" % ("s3" if s3 else "filesystem"))
    if s3:
        print("  bucket(s): %s" % ", ".join(g.s3_media_buckets))
        print("  endpoint: %s" % (getattr(g, "s3_endpoint_url", None) or
                                  "Amazon S3"))

    name = "storage-check-%s.txt" % uuid.uuid4().hex[:12]
    body = ("tippr media check %s" % time.time()).encode()
    problems = []
    url = provider.put("thumbs", name, body)
    print("saved %s -> %s" % (name, url))
    try:
        on_disk = os.path.exists(os.path.join(MEDIA_DIR, name))
        if s3:
            bucket = g.s3_media_buckets[0]
            try:
                provider._get_s3_client().head_object(Bucket=bucket, Key=name)
                print("  in the bucket: yes")
            except Exception as e:
                # with several buckets it may be in another one
                print("  in bucket %s: no (%s)" % (bucket, e))
                if len(g.s3_media_buckets) == 1:
                    problems.append("not in the bucket")
            print("  in %s: %s" % (MEDIA_DIR, "yes" if on_disk else "no"))
            if on_disk:
                problems.append("written to the disk too")
        else:
            print("  in %s: %s" % (MEDIA_DIR, "yes" if on_disk else "no"))

        resp = fetch(name)
        if resp is None:
            problems.append("nginx didn't answer on 127.0.0.1")
            print("  /media/%s through nginx: no answer" % name)
        else:
            same = resp.status_code == 200 and resp.content == body
            print("  /media/%s through nginx: %s%s" % (
                name, resp.status_code, ", same contents" if same else ""))
            if not same:
                problems.append("nginx gave %s for /media/" % resp.status_code)
    finally:
        # deleting goes through the same code as deleting a member's
        # media, so it's checked too
        try:
            provider.purge(url)
            print("deleted the test file")
        except Exception as e:
            print("  deleting it: failed (%s: %s)" % (type(e).__name__, e))
            problems.append("couldn't delete media (%s)" % name)
        if not s3:
            try:
                os.remove(os.path.join(MEDIA_DIR, name))
            except OSError:
                pass

    if problems:
        print("PROBLEMS: %s" % "; ".join(problems))
    else:
        print("OK: media is saved to %s and served at /media/" %
              ("the bucket" if s3 else MEDIA_DIR))


main()

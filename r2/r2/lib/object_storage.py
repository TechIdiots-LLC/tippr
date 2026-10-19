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
"""S3-compatible object storage: where to connect and how objects are
reached, for every part of tippr that stores files in buckets (the s3 media
provider, r2.lib.s3_helpers and the uploads it signs for browsers).

reddit's code assumed Amazon S3. These ini settings let it use any
S3-compatible service instead (Garage, SeaweedFS, MinIO, Ceph, Backblaze
B2, Cloudflare R2, Wasabi …); left blank, it's Amazon S3 as before.

    S3KEY_ID, S3SECRET_KEY  the access key (blank: boto3 looks for one)
    s3_endpoint_url         e.g. http://garage.lan:3900 (blank: Amazon S3)
    s3_region               e.g. garage (default us-east-1)
    s3_addressing_style     path (http://host/bucket/key, the default with
                            an endpoint) or virtual (http://bucket.host/key)
    s3_use_acls             send public-read ACLs and Amazon storage classes
                            (default: only for Amazon S3; Garage and others
                            make buckets public instead)
    s3_public_url           where browsers fetch objects: a base URL, with
                            {bucket} for the bucket's name, e.g.
                            https://example.com/media (nginx passes /media/
                            to the bucket) or https://{bucket}.cdn.example.com
                            (blank: the endpoint's own address)
    s3_browser_endpoint_url where browsers send direct uploads (ad images):
                            the S3 endpoint as browsers reach it, e.g.
                            https://example.com/s3 when nginx passes /s3/ to
                            a service on the LAN (blank: s3_endpoint_url)

The installer sets these from TIPPR_MEDIA_STORAGE and TIPPR_S3_* (see
docs/STORAGE.md).
"""

import boto3
from botocore.config import Config
from pylons import app_globals as g

_client = None
_resource = None


def _setting(name, default=""):
    value = g.config.get(name)
    if value is None:
        value = getattr(g, name, None) if name.isupper() else None
    value = ("" if value is None else str(value)).strip()
    return value or default


def endpoint_url():
    return _setting("s3_endpoint_url").rstrip("/") or None


def region():
    return _setting("s3_region", "us-east-1")


def addressing_style():
    style = _setting("s3_addressing_style",
                     "path" if endpoint_url() else "virtual").lower()
    return style if style in ("path", "virtual") else "path"


def use_acls():
    value = _setting("s3_use_acls")
    if not value:
        return endpoint_url() is None
    return value.lower() in ("true", "yes", "on", "1")


def credentials():
    key_id = _setting("S3KEY_ID")
    secret = _setting("S3SECRET_KEY")
    if key_id and secret:
        return dict(aws_access_key_id=key_id, aws_secret_access_key=secret)
    return {}


def _session_kwargs():
    kwargs = dict(credentials())
    kwargs["region_name"] = region()
    if endpoint_url():
        kwargs["endpoint_url"] = endpoint_url()
    kwargs["config"] = Config(signature_version="s3v4",
                              s3={"addressing_style": addressing_style()})
    return kwargs


def client():
    """A boto3 S3 client for the configured service (shared)."""
    global _client
    if _client is None:
        _client = boto3.client("s3", **_session_kwargs())
    return _client


def resource():
    """A boto3 S3 resource for the configured service (shared)."""
    global _resource
    if _resource is None:
        _resource = boto3.resource("s3", **_session_kwargs())
    return _resource


def reset():
    """Forget the shared connections (after the settings change)."""
    global _client, _resource
    _client = _resource = None


def _aws_domain():
    return _setting("s3_media_domain", "s3.amazonaws.com")


def bucket_url(bucket, browser=False):
    """The bucket's address (browser: as browsers reach it, for the uploads
    they POST to it)."""
    endpoint = endpoint_url()
    if browser and _setting("s3_browser_endpoint_url"):
        endpoint = _setting("s3_browser_endpoint_url").rstrip("/")
    if endpoint:
        if addressing_style() == "virtual":
            scheme, _, host = endpoint.partition("://")
            return "%s://%s.%s" % (scheme, bucket, host)
        return "%s/%s" % (endpoint, bucket)
    return "https://%s.%s" % (bucket, _aws_domain())


def public_url(bucket, key):
    """Where browsers fetch bucket/key."""
    base = _setting("s3_public_url")
    if base:
        return "%s/%s" % (base.replace("{bucket}", bucket).rstrip("/"), key)
    if not endpoint_url() and _setting("s3_media_direct", "true").lower() in (
            "false", "no", "off", "0"):
        # (reddit's s3_media_direct = false: the bucket is a CNAME'd domain)
        return "https://%s/%s" % (bucket, key)
    return "%s/%s" % (bucket_url(bucket), key)


def bucket_and_key(url):
    """(bucket, key) for a URL public_url() made (http or https), or
    (None, None)."""
    bare = url.split("://", 1)[-1]
    for bucket in configured_buckets():
        prefix = public_url(bucket, "").split("://", 1)[-1]
        if bare.startswith(prefix):
            return bucket, bare[len(prefix):].split("?", 1)[0]
    return None, None


def configured_buckets():
    names = []
    for setting in ("s3_media_buckets", "s3_image_buckets",
                    "s3_client_uploads_bucket"):
        for name in _setting(setting).split(","):
            name = name.strip()
            if name and name not in names:
                names.append(name)
    return names


def uploads_bucket():
    """The bucket browsers upload to directly (ad images …), or None."""
    return _setting("s3_client_uploads_bucket") or None


def check(bucket):
    """An error message if bucket can't be reached and written, else None
    (scripts/migrate_media_to_s3.py, the admin pages)."""
    try:
        s3 = client()
        s3.head_bucket(Bucket=bucket)
        s3.put_object(Bucket=bucket, Key=".tippr-check", Body=b"ok",
                      ContentType="text/plain")
        s3.delete_object(Bucket=bucket, Key=".tippr-check")
    except Exception as e:
        return "%s: %s" % (type(e).__name__, e)
    return None

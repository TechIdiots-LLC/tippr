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

import base64
import datetime
import hashlib
import hmac
import json
import os
import sys
import time
from collections import namedtuple

import boto3
from botocore.exceptions import ClientError
import pytz
from pylons import app_globals as g

HADOOP_FOLDER_SUFFIX = '_$folder$'

SIGNATURE_V4_ALGORITHM = "AWS4-HMAC-SHA256"

# Cache for boto3 clients/resources
_s3_client = None
_s3_resource = None


def _to_path(bucket, key):
    if not bucket:
        raise ValueError
    return 's3://{}/{}'.format(bucket, key)


def _from_path(path):
    """Return bucket and key names from an s3 path.

    Path of 's3://BUCKET/KEY/NAME' would return 'BUCKET', 'KEY/NAME'.

    """

    if not path.startswith('s3://'):
        raise ValueError('Bad S3 path %s' % path)

    r = path[len('s3://'):].split('/', 1)
    bucket = key = None

    if len(r) == 2:
        bucket, key = r[0], r[1]
    else:
        bucket = r[0]

    if not bucket:
        raise ValueError('Bad S3 path %s' % path)

    return bucket, key


S3Path = namedtuple('S3Path', ['bucket', 'key'])


def parse_s3_path(path):
    return S3Path(*_from_path(path))


def format_expires(expires):
    return expires.strftime(EXPIRES_DATE_FORMAT)


def get_s3_client():
    """Get or create a boto3 S3 client."""
    global _s3_client
    if _s3_client is None:
        kwargs = {}
        if g.S3KEY_ID:
            kwargs['aws_access_key_id'] = g.S3KEY_ID
        if g.S3SECRET_KEY:
            kwargs['aws_secret_access_key'] = g.S3SECRET_KEY
        _s3_client = boto3.client('s3', **kwargs)
    return _s3_client


def get_s3_resource():
    """Get or create a boto3 S3 resource."""
    global _s3_resource
    if _s3_resource is None:
        kwargs = {}
        if g.S3KEY_ID:
            kwargs['aws_access_key_id'] = g.S3KEY_ID
        if g.S3SECRET_KEY:
            kwargs['aws_secret_access_key'] = g.S3SECRET_KEY
        _s3_resource = boto3.resource('s3', **kwargs)
    return _s3_resource


def get_text_from_s3(s3_connection, path):
    """Read a file from S3 and return it as text."""
    bucket_name, key_name = _from_path(path)
    s3 = get_s3_resource()
    obj = s3.Object(bucket_name, key_name)
    return obj.get()['Body'].read()


def mv_file_s3(s3_connection, src_path, dst_path):
    """Move a file within S3."""
    src_bucket_name, src_key_name = _from_path(src_path)
    dst_bucket_name, dst_key_name = _from_path(dst_path)

    s3 = get_s3_resource()
    copy_source = {'Bucket': src_bucket_name, 'Key': src_key_name}
    s3.Object(dst_bucket_name, dst_key_name).copy_from(CopySource=copy_source)
    s3.Object(src_bucket_name, src_key_name).delete()


def s3_key_exists(s3_connection, path):
    bucket_name, key_name = _from_path(path)
    client = get_s3_client()
    try:
        client.head_object(Bucket=bucket_name, Key=key_name)
        return True
    except ClientError:
        return False


def copy_to_s3(s3_connection, local_path, dst_path, verbose=False):
    dst_bucket_name, dst_key_name = _from_path(dst_path)

    filename = os.path.basename(local_path)
    if not filename:
        return

    key_name = os.path.join(dst_key_name, filename)

    if verbose:
        print('Uploading {} to {}'.format(local_path, dst_path))

    s3 = get_s3_resource()
    s3.Object(dst_bucket_name, key_name).upload_file(local_path)


def get_connection():
    """Legacy compatibility - returns the S3 resource."""
    return get_s3_resource()


def get_key(bucket_name, key, connection=None):
    s3 = get_s3_resource()
    obj = s3.Object(bucket_name, key)
    try:
        obj.load()
        return obj
    except ClientError:
        return None


def get_keys(bucket_name, meta=False, connection=None, prefix='', **kwargs):
    s3 = get_s3_resource()
    bucket = s3.Bucket(bucket_name)
    objects = list(bucket.objects.filter(Prefix=prefix))

    if not meta:
        return objects

    return [s3.Object(bucket_name, obj.key) for obj in objects]


def delete_keys(bucket_name, prefix, connection=None):
    s3 = get_s3_resource()
    bucket = s3.Bucket(bucket_name)
    objects = list(bucket.objects.filter(Prefix=prefix))
    if objects:
        bucket.delete_objects(
            Delete={'Objects': [{'Key': obj.key} for obj in objects]}
        )
    return objects


def _get_v4_credential(aws_access_key_id, date, service_name, region_name):
    return ("{aws_access_key_id}/{datestamp}/{region_name}/{service_name}/aws4_request".format(
        aws_access_key_id=aws_access_key_id,
        datestamp=date.strftime("%Y%m%d"),
        region_name=region_name,
        service_name=service_name,
    ))


def _get_upload_policy(
        bucket, key, credential, date, acl,
        ttl=60,
        success_action_redirect=None,
        success_action_status="201",
        content_type=None,
        max_content_length=((1024**2) * 3),
        storage_class="STANDARD",
        region_name=None,
        meta=None,
        connection=None,
    ):

    meta = meta or {}

    expiration = time.gmtime(int(time.time() + ttl))
    conditions = []

    conditions.append({"bucket": bucket})

    if key.endswith("${filename}"):
        conditions.append(["starts-with", "$key", key[:-len("${filename}")]])
    else:
        conditions.append({"key": key})

    conditions.append({"acl": acl})
    conditions.append({"x-amz-storage-class": storage_class})

    conditions.append({"x-amz-credential": credential})
    conditions.append({"x-amz-algorithm": SIGNATURE_V4_ALGORITHM})
    conditions.append({"x-amz-date": date.strftime("%Y%m%dT%H%M%SZ")})

    # Get security token from session if available
    session = boto3.Session()
    credentials = session.get_credentials()
    if credentials and credentials.token:
        conditions.append({"x-amz-security-token": credentials.token})

    if success_action_redirect:
        conditions.append([
            "starts-with",
            "$success_action_redirect",
            success_action_redirect,
        ])
    else:
        conditions.append({
            "success_action_status": success_action_status,
        })

    conditions.append([
        "content-length-range", 0, max_content_length])

    for key, value in meta.items():
        conditions.append({key: value})

    if content_type:
        conditions.append({"content-type": content_type})

    # ISO8601 format for policy expiration
    iso8601_format = "%Y-%m-%dT%H:%M:%SZ"
    return base64.b64encode(json.dumps({
        "expiration": time.strftime(iso8601_format, expiration),
        "conditions": conditions,
    }).encode('utf-8'))


def _sign(secret, msg):
    return hmac.new(secret, msg.encode("utf-8"), hashlib.sha256).digest()


def _derive_v4_signature_key(secret, date, region_name, service_name):
    key_date = _sign(("AWS4" + secret).encode("utf-8"), date.strftime("%Y%m%d"))
    key_region = _sign(key_date, region_name)
    key_service = _sign(key_region, service_name)
    return _sign(key_service, "aws4_request")


def _get_upload_signature(
        policy,
        date,
        region_name,
        connection=None,
    ):

    session = boto3.Session()
    credentials = session.get_credentials()
    if credentials:
        secret_key = credentials.secret_key
    else:
        secret_key = g.S3SECRET_KEY

    key = secret_key.encode("utf-8") if isinstance(secret_key, str) else secret_key
    v4_key = _derive_v4_signature_key(
        secret=secret_key, date=date, region_name=region_name, service_name="s3")

    return hmac.new(v4_key, policy, hashlib.sha256).hexdigest()


def get_post_args(
        bucket, key,
        acl="public-read",
        success_action_redirect=None,
        success_action_status="201",
        content_type=None,
        storage_class="STANDARD",
        region_name="us-east-1",
        meta=None,
        connection=None,
        **kwargs
    ):

    meta = meta or []
    algorithm = "AWS4-HMAC-SHA256"
    date = datetime.datetime.now(pytz.utc)

    session = boto3.Session()
    credentials = session.get_credentials()
    if credentials:
        access_key = credentials.access_key
        security_token = credentials.token
    else:
        access_key = g.S3KEY_ID
        security_token = None

    credential = _get_v4_credential(
        aws_access_key_id=access_key,
        date=date,
        service_name="s3",
        region_name=region_name,
    )
    policy = _get_upload_policy(
        bucket=bucket,
        key=key,
        credential=credential,
        date=date,
        acl=acl,
        success_action_redirect=success_action_redirect,
        success_action_status=success_action_status,
        content_type=content_type,
        storage_class=storage_class,
        region_name=region_name,
        meta=meta,
        connection=connection,
    )
    signature = _get_upload_signature(
        policy=policy,
        date=date,
        region_name=region_name,
        connection=connection,
    )

    fields = []

    fields.append({
        "name": "acl",
        "value": acl,
    })

    fields.append({
        "name": "key",
        "value": key,
    })

    fields.append({
        "name": "X-Amz-Credential",
        "value": credential,
    })

    fields.append({
        "name": "X-Amz-Algorithm",
        "value": SIGNATURE_V4_ALGORITHM,
    })

    fields.append({
        "name": "X-Amz-Date",
        "value": date.strftime("%Y%m%dT%H%M%SZ"),
    })

    if success_action_redirect:
        fields.append({
            "name": "success_action_redirect",
            "value": success_action_redirect,
        })
    else:
        fields.append({
            "name": "success_action_status",
            "value": success_action_status,
        })

    fields.append({
        "name": "content-type",
        "value": content_type,
    })

    fields.append({
        "name": "x-amz-storage-class",
        "value": storage_class,
    })

    for k, value in meta.items():
        fields.append({
            "name": k,
            "value": value,
        })

    fields.append({
        "name": "policy",
        "value": policy.decode('utf-8') if isinstance(policy, bytes) else policy,
    })

    fields.append({
        "name": "X-Amz-Signature",
        "value": signature,
    })

    if security_token:
        fields.append({
            "name": "x-amz-security-token",
            "value": security_token,
        })

    return {
        "action": "//{}.{}".format(bucket, g.s3_media_domain),
        "fields": fields,
    }

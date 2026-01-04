import datetime
import json
import time

import boto3
from botocore.exceptions import ClientError
import dateutil
import pytz
from pylons import app_globals as g

from r2.lib.s3_helpers import parse_s3_path
from r2.lib.sitemaps.data import find_all_subreddits
from r2.lib.sitemaps.store import store_sitemaps_in_s3

"""Watch for SQS messages informing us to read, generate, and store sitemaps.

There is only function that should be used outside this module

watcher()

It is designed to be used in a daemon process.
"""


def watcher():
    """Poll for new sitemap data and process it as necessary."""
    while True:
        _process_message()


def _subreddit_sitemap_key():
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(g.sitemap_upload_s3_bucket)
    try:
        obj = s3.Object(g.sitemap_upload_s3_bucket, g.sitemap_subreddit_keyname)
        obj.load()
        return obj
    except ClientError:
        return None


def _datetime_from_timestamp(timestamp):
    return datetime.datetime.fromtimestamp(timestamp / 1000, pytz.utc)


def _before_last_sitemap(timestamp):
    sitemap_key = _subreddit_sitemap_key()
    if sitemap_key is None:
        return False

    sitemap_datetime = dateutil.parser.parse(sitemap_key.last_modified.isoformat())
    compare_datetime = _datetime_from_timestamp(timestamp)
    return compare_datetime < sitemap_datetime


def _process_message():
    if not g.sitemap_sqs_queue:
        return

    sqs = boto3.resource('sqs')
    sqs_q = sqs.get_queue_by_name(QueueName=g.sitemap_sqs_queue)

    messages = sqs_q.receive_messages(MaxNumberOfMessages=1)

    if not messages:
        return

    message, = messages

    js = json.loads(message.body)
    s3path = parse_s3_path(js['location'])

    # There are some error cases that allow us to get messages
    # for sitemap creation that are now out of date.
    timestamp = js.get('timestamp')
    if timestamp is not None and _before_last_sitemap(timestamp):
        message.delete()
        return

    g.log.info("Got import job %r", js)

    vaults = find_all_subreddits(s3path)
    store_sitemaps_in_s3(vaults)

    message.delete()


def _current_timestamp():
    return time.time() * 1000


def _create_test_message():
    """A dev only function that drops a new message on the sqs queue."""
    sqs = boto3.resource('sqs')
    sqs_q = sqs.get_queue_by_name(QueueName=g.sitemap_sqs_queue)

    # it returns None on failure
    assert sqs_q, "failed to connect to queue"

    sqs_q.send_message(MessageBody=json.dumps({
        'job_name': 'daily-sr-sitemap-reporting',
        'location': ('s3://tippr-data-analysis/big-data/r2/prod/' +
                     'daily_sr_sitemap_reporting/dt=2016-06-14'),
        'timestamp': _current_timestamp(),
    }))

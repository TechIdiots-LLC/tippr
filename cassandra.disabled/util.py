from datetime import datetime


def datetime_from_uuid1(u):
    """Convert a UUID1 to a Python datetime (UTC).

    This mirrors the DataStax driver's cassandra.util.datetime_from_uuid1
    used by the codebase. It expects a uuid.UUID instance with a .time
    attribute (UUID1). Returns a datetime in UTC or raises on invalid input.
    """
    # UUID1 timestamp is 100-ns intervals since Oct 15, 1582
    EPOCH_DIFF = 0x01b21dd213814000
    ts = (u.time - EPOCH_DIFF) / 1e7
    return datetime.utcfromtimestamp(ts)

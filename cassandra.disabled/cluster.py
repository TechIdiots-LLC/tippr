class Cluster:
    """Very small shim of DataStax Cluster for tests.

    connect() returns a Session-like object with the minimal methods used
    by the repository's cassandra compatibility layer: `execute` and
    `set_keyspace`.
    """
    def __init__(self, contact_points=None):
        self.contact_points = contact_points or ['127.0.0.1']

    def connect(self):
        return _DummySession()


class _DummyResult(list):
    def one(self):
        return None


class _DummySession:
    def __init__(self):
        self._keyspace = None

    def set_keyspace(self, keyspace):
        self._keyspace = keyspace

    def execute(self, statement, params=None):
        # Accept any statement and return an empty iterable result. Some
        # code expects an object with a `.one()` method, so return a
        # _DummyResult (subclass of list) with a one() that returns None.
        return _DummyResult()

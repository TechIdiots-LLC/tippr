class InvalidRequest(Exception):
    """Placeholder for cassandra.InvalidRequest used in compat layer."""


class ReadTimeout(Exception):
    """Placeholder for cassandra.ReadTimeout exception."""


class _ConsistencyLevel:
    ANY = 0
    ONE = 1
    QUORUM = 2
    ALL = 3


ConsistencyLevel = _ConsistencyLevel()

__all__ = ["InvalidRequest", "ReadTimeout", "ConsistencyLevel"]

# Minimal ttypes shim providing NotFoundException and ConsistencyLevel
# used by legacy code migrating from pycassa to cassandra-driver

# The exception cassandra_compat actually raises: a separate class here would
# never match `except NotFoundException` (comment pages broke on a missing
# visits row).
from r2.lib.db.cassandra_compat import NotFoundException  # noqa: F401


class ConsistencyLevel:
    """Cassandra consistency levels compatible with pycassa's API.

    These map to the cassandra-driver's ConsistencyLevel values.
    """
    ANY = 0
    ONE = 1
    TWO = 2
    THREE = 3
    QUORUM = 4
    ALL = 5
    LOCAL_QUORUM = 6
    EACH_QUORUM = 7
    SERIAL = 8
    LOCAL_SERIAL = 9
    LOCAL_ONE = 10

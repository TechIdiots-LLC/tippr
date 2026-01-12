# Auto-generated Thrift type stubs for ActivityService
# This is a minimal stub based on activity.thrift


class ActivityInfo:
    """A count of visitors active within a context.

    If the count is low enough, some fuzzing is applied to the number.
    If this kicks in, the `is_fuzzed` attribute will be True.
    """

    def __init__(self, count=None, is_fuzzed=None):
        self.count = count
        self.is_fuzzed = is_fuzzed

    def read(self, iprot):
        pass

    def write(self, oprot):
        pass

    def __repr__(self):
        return f"ActivityInfo(count={self.count}, is_fuzzed={self.is_fuzzed})"

    def __eq__(self, other):
        if not isinstance(other, ActivityInfo):
            return False
        return self.count == other.count and self.is_fuzzed == other.is_fuzzed


class InvalidContextIDException(Exception):
    """A specified context ID was invalid."""
    pass


__all__ = ['ActivityInfo', 'InvalidContextIDException']

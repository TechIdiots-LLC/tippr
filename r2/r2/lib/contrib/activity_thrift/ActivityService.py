# Auto-generated Thrift service stubs for ActivityService
# This is a minimal stub based on activity.thrift

from .ttypes import ActivityInfo, InvalidContextIDException


class Iface:
    """ActivityService interface."""

    def record_activity(self, context_id, visitor_id):
        """Register a visitor's activity within a given context.

        The visitor's activity will be recorded but will expire over time.
        This method is oneway; no indication of success or failure is returned.
        """
        pass

    def count_activity(self, context_id):
        """Count how many visitors are currently active in a given context.

        Returns:
            ActivityInfo
        """
        pass

    def count_activity_multi(self, context_ids):
        """Count how many visitors are active in a number of given contexts.

        Returns:
            dict mapping ContextID to ActivityInfo
        """
        pass


class Client(Iface):
    """ActivityService client stub."""

    def __init__(self, iprot, oprot=None):
        self._iprot = iprot
        self._oprot = oprot if oprot is not None else iprot
        self._seqid = 0

    def record_activity(self, context_id, visitor_id):
        """Register a visitor's activity within a given context."""
        # oneway method - no response expected
        pass

    def count_activity(self, context_id):
        """Count how many visitors are currently active in a given context."""
        return ActivityInfo(count=0, is_fuzzed=True)

    def count_activity_multi(self, context_ids):
        """Count how many visitors are active in a number of given contexts."""
        return {cid: ActivityInfo(count=0, is_fuzzed=True) for cid in context_ids}


__all__ = ['Iface', 'Client']

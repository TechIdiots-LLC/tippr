class SimpleStatement:
    def __init__(self, query):
        self.query = query


class BatchType:
    UNLOGGED = 1


class BatchStatement:
    def __init__(self, batch_type=None):
        self.batch_type = batch_type
        self._stmts = []

    def add(self, stmt, params=None):
        self._stmts.append((stmt, params))

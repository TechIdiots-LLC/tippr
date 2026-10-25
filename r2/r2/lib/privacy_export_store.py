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
"""Members' data exports (/prefs/privacy), kept in PostgreSQL.

The queue processor that makes an export (r2.lib.privacy_export_consumer)
and the server a member downloads it from can be different ones
(docs/SERVERS.md), so the ZIP goes where every server reads it, rather
than on the disk of the one that made it. Exports are small (JSON, capped
per kind), private (only their member downloads them, r2.models.privacy
DataExportFile), and gone after EXPIRY: each new one clears the old.
"""

from datetime import datetime, timedelta

import sqlalchemy as sa
from pylons import app_globals as g

# a little longer than the download record lasts (DataExportFile._ttl)
EXPIRY = timedelta(days=8)
# what DataExportFile.file_path holds for an export kept here
STORED = "db"

_db = {}


def _exports_table(metadata):
    return sa.Table(
        "privacy_export_files", metadata,
        sa.Column("token", sa.String, primary_key=True),
        sa.Column("data", sa.LargeBinary, nullable=False),
        sa.Column("created", sa.DateTime(timezone=True), nullable=False),
    )


def _engine():
    """The database and the exports table (made on first use, so importing
    this needs no database)."""
    if "engine" not in _db:
        from r2.lib.db.tdb_sql import create_table, make_metadata
        engine = g.dbm.get_engine("main")
        table = _exports_table(make_metadata(engine))
        create_table(table)
        _db.update(engine=engine, table=table)
    return _db["engine"]


def _table():
    _engine()
    return _db["table"]


def save(token, data):
    """Keep an export's ZIP (bytes) under its download token, and clear
    expired ones."""
    table = _table()
    now = datetime.now(g.tz)
    with _engine().begin() as conn:
        conn.execute(table.delete().where(table.c.created < now - EXPIRY))
        conn.execute(table.insert().values(token=token, data=data,
                                           created=now))


def load(token):
    """An export's ZIP (bytes), or None."""
    table = _table()
    with _engine().connect() as conn:
        row = conn.execute(sa.select(table.c.data)
                           .where(table.c.token == token)).fetchone()
    return bytes(row[0]) if row else None

#!/usr/bin/env python3
"""Backfill VaultMember subscriber relations into Cassandra."""

import time

from r2.lib.db.operators import desc
from r2.lib.utils import fetch_things2, to36
from r2.models.vault import VaultMember, SubscribedVaultsByAccount


def get_query(after_user_id):
    q = VaultMember._query(
        VaultMember.c._name == "subscriber",
        VaultMember.c._thing2_id < after_user_id,
        sort=desc("_thing2_id"),
    )
    return q


def get_vaultmembers(after_user_id):
    previous_user_id = None

    while True:
        # there isn't a good index on rel_id so we need to get a new query
        # for each batch rather than relying solely on fetch_things2
        q = get_query(after_user_id)
        users_seen = 0

        for rel in fetch_things2(q):
            user_id = rel._thing2_id

            if user_id != previous_user_id:
                if users_seen >= 20:
                    # set after_user_id to the previous id so we will pick up
                    # the query at this same point
                    after_user_id = previous_user_id
                    break

                users_seen += 1
                previous_user_id = user_id

            yield rel


def migrate_vaultmember_subscribers(after_user_id=39566712):
    columns = {}
    rowkey = None
    proc_time = time.time()

    for i, rel in enumerate(get_vaultmembers(after_user_id)):
        vault_id = rel._thing1_id
        user_id = rel._thing2_id
        action_date = rel._date
        new_rowkey = to36(user_id)

        if new_rowkey != rowkey and columns:
            SubscribedVaultsByAccount._cf.insert(
                rowkey, columns, timestamp=1434403336829573)
            columns = {}

        columns[to36(vault_id)] = action_date
        rowkey = new_rowkey

        if i % 1000 == 0:
            new_proc_time = time.time()
            duration = new_proc_time - proc_time
            print("{} ({:.3f}): {} - {}".format(i, duration, user_id, action_date))
            proc_time = new_proc_time


if __name__ == '__main__':
    migrate_vaultmember_subscribers()

# The contents of this file are subject to the Common Public Attribution
# License Version 1.0. (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://code.reddit.com/LICENSE. The License is based on the Mozilla Public
# License Version 1.1, but Sections 14 and 15 have been added to cover use of
# software over a computer network and provide for limited attribution for the
# Original Developer. In addition, Exhibit A has been modified to be consistent
# with Exhibit B.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is reddit.
#
# The Original Developer is the Initial Developer.  The Initial Developer of
# the Original Code is reddit Inc.
#
# All portions of the code written by reddit are Copyright (c) 2006-2015 reddit
# Inc. All Rights Reserved.
###############################################################################

from itertools import product

from pycassa.types import IntegerType

from r2.lib.db import tdb_cassandra
from r2.lib.utils import tup


class PromoMetrics(tdb_cassandra.View):
    '''
    Cassandra data store for promotion metrics. Used for inventory prediction.

    Usage:
      # set metric value for many vaults at once
      > PromoMetrics.set('min_daily_pageviews.GET_listing',
                          {'funny': 63432, 'pics': 48829, 'books': 4})

      # get metric value for one vault
      > res = PromoMetrics.get('min_daily_pageviews.GET_listing', 'funny')
      {'funny': 1234}

      # get metric value for many vaults
      > res = PromoMetrics.get('min_daily_pageviews.GET_listing',
                               ['funny', 'pics'])
      {'funny':1234, 'pics':4321}

      # get metric values for all vaults
      > res = PromoMetrics.get('min_daily_pageviews.GET_listing')
    '''
    _use_db = True
    _value_type = 'int'
    _fetch_all_columns = True

    @classmethod
    def get(cls, metric_name, vault_names=None):
        vault_names = tup(vault_names)
        try:
            metric = cls._byID(metric_name, properties=vault_names)
            return metric._values()  # might have additional values
        except tdb_cassandra.NotFound:
            return {}

    @classmethod
    def set(cls, metric_name, values_by_sr):
        cls._set_values(metric_name, values_by_sr)


class LocationPromoMetrics(tdb_cassandra.View):
    _use_db = True
    _write_consistency_level = tdb_cassandra.CL.QUORUM
    _read_consistency_level = tdb_cassandra.CL.ONE
    _extra_schema_creation_args = {
        "default_validation_class": IntegerType(),
    }

    @classmethod
    def _rowkey(cls, location):
        fields = [location.country, location.region, location.metro]
        return '-'.join([field or '' for field in fields])

    @classmethod
    def _column_name(cls, vault):
        return vault.name

    @classmethod
    def get(cls, vaults, locations):
        vaults, vaults_is_single = tup(vaults, ret_is_single=True)
        locations, locations_is_single = tup(locations, ret_is_single=True)
        is_single = vaults_is_single and locations_is_single

        rowkeys = {location: cls._rowkey(location) for location in locations}
        columns = {vault: cls._column_name(vault) for vault in vaults}
        rcl = cls._read_consistency_level
        metrics = cls._cf.multiget(list(rowkeys.values()), list(columns.values()),
                                   read_consistency_level=rcl)
        ret = {}

        for vault, location in product(vaults, locations):
            rowkey = rowkeys[location]
            column = columns[vault]
            impressions = metrics.get(rowkey, {}).get(column, 0)
            ret[(vault, location)] = impressions

        if is_single:
            return list(ret.values())[0]
        else:
            return ret

    @classmethod
    def set(cls, metrics):
        wcl = cls._write_consistency_level
        with cls._cf.batch(write_consistency_level=wcl) as b:
            for location, vault, impressions in metrics:
                rowkey = cls._rowkey(location)
                column = {cls._column_name(vault): impressions}
                b.insert(rowkey, column)

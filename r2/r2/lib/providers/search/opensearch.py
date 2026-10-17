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
#
# Portions created by TechIdiots LLC (Tippr) are Copyright (c) 2026
# TechIdiots LLC. All Rights Reserved.
###############################################################################
"""Search provider for OpenSearch (search_provider = opensearch).

Posts and vaults each get an index ("<opensearch_index_prefix>links" and
"<opensearch_index_prefix>vaults"). The search_q consumer keeps them up to
date from the cloudsearch_changes queue; rebuild_index() fills them from the
database.

Queries accept the familiar field syntax, mixed with free text:

    vault:pics author:someone site:example.com nsfw:no self:yes
    flair:meta title:words selftext:words url:words

A leading "-" negates a field term (-vault:pics). Free text supports quoted
phrases, "-word" and "OR", and tolerates small typos.

Only the REST API is used, through requests, so no OpenSearch client library
is needed.
"""

import json
import pickle
import re
import shlex
import time
from datetime import datetime

import requests
from pylons import app_globals as g
from pylons import tmpl_context as c

import r2.lib.utils as r2utils
from r2.lib import amqp, filters
from r2.lib.configparse import ConfigValue
from r2.lib.db.operators import desc
from r2.lib.providers.search import SearchProvider
from r2.lib.providers.search.common import (
    InvalidQuery,
    LinkFields,
    Results,
    SearchError,
    SearchHTTPError,
    VaultFields,
    safe_get,
)
from r2.models import (
    Account,
    All,
    AllMinus,
    DefaultVault,
    DomainVault,
    FakeVault,
    Friends,
    Link,
    MultiVault,
    NotFound,
    Thing,
    Vault,
)

# OpenSearch's default limit on from + size
MAX_RESULTS = 1000
DEFAULT_TIMEOUT = 10

_INDEX_SETTINGS = {
    # a single node can't hold replicas; more nodes can raise this later
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "analysis": {
        "normalizer": {
            "lower": {"type": "custom", "filter": ["lowercase", "asciifolding"]},
        },
    },
}

LINK_MAPPING = {
    "dynamic": False,
    "properties": {
        "fullname": {"type": "keyword"},
        "vault": {"type": "keyword", "normalizer": "lower"},
        "vault_id": {"type": "long"},
        "author": {"type": "keyword", "normalizer": "lower"},
        "author_fullname": {"type": "keyword"},
        "title": {
            "type": "text",
            "analyzer": "english",
            "fields": {"plain": {"type": "text", "analyzer": "standard"}},
        },
        "selftext": {
            "type": "text",
            "analyzer": "english",
            "fields": {"plain": {"type": "text", "analyzer": "standard"}},
        },
        "url": {"type": "text", "analyzer": "simple"},
        "site": {"type": "keyword", "normalizer": "lower"},
        "flair_text": {"type": "text"},
        "flair_css_class": {"type": "keyword"},
        "timestamp": {"type": "date", "format": "epoch_second"},
        "over18": {"type": "boolean"},
        "is_self": {"type": "boolean"},
        "ups": {"type": "integer"},
        "downs": {"type": "integer"},
        "score": {"type": "integer"},
        "hot": {"type": "double"},
        "num_comments": {"type": "integer"},
        "type_id": {"type": "integer"},
    },
}

VAULT_MAPPING = {
    "dynamic": False,
    "properties": {
        "fullname": {"type": "keyword"},
        "name": {
            "type": "search_as_you_type",
            "fields": {"raw": {"type": "keyword", "normalizer": "lower"}},
        },
        "title": {"type": "text", "analyzer": "english"},
        "header_title": {"type": "text"},
        "description": {"type": "text", "analyzer": "english"},
        "sidebar": {"type": "text", "analyzer": "english"},
        "type": {"type": "keyword"},
        "language": {"type": "keyword"},
        "link_type": {"type": "keyword"},
        "over18": {"type": "boolean"},
        "activity": {"type": "integer"},
        "subscribers": {"type": "integer"},
        "type_id": {"type": "integer"},
    },
}


###############################################################################
# HTTP
###############################################################################

def _setting(name, default=None):
    value = g.config.get(name)
    return default if value in (None, "") else value


def _base_url():
    return _setting("opensearch_url", "http://127.0.0.1:9200").rstrip("/")


def index_name(kind):
    return "%s%s" % (_setting("opensearch_index_prefix", "tippr_"), kind)


def _request(method, path, body=None, ndjson=None, params=None,
             ok_statuses=()):
    url = _base_url() + path
    headers = {}
    data = None
    if ndjson is not None:
        headers["Content-Type"] = "application/x-ndjson"
        data = ndjson.encode("utf-8")
    elif body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")

    auth = None
    if _setting("opensearch_username"):
        auth = (_setting("opensearch_username"),
                _setting("opensearch_password", ""))

    try:
        resp = requests.request(method, url, data=data, headers=headers,
                                params=params, auth=auth,
                                timeout=DEFAULT_TIMEOUT,
                                verify=_setting("opensearch_verify_tls", True))
    except requests.RequestException as e:
        raise SearchError(e, url)

    if resp.status_code >= 300 and resp.status_code not in ok_statuses:
        try:
            reason = resp.json().get("error")
        except ValueError:
            reason = resp.text
        if resp.status_code == 400 and path.endswith("/_search"):
            raise InvalidQuery(resp.status_code, reason, url)
        raise SearchHTTPError(resp.status_code, reason, url)

    if method == "HEAD" or not resp.content:
        return resp.status_code
    return resp.json()


def ensure_index(kind, mapping, recreate=False):
    """Create the index if it doesn't exist yet (or recreate it)."""
    name = index_name(kind)
    if recreate:
        _request("DELETE", "/" + name, ok_statuses=(404,))
    elif _request("HEAD", "/" + name, ok_statuses=(404,)) == 200:
        return
    _request("PUT", "/" + name,
             body={"settings": _INDEX_SETTINGS, "mappings": mapping})


def ensure_indexes(recreate=False):
    ensure_index("links", LINK_MAPPING, recreate=recreate)
    ensure_index("vaults", VAULT_MAPPING, recreate=recreate)


###############################################################################
# Queries
###############################################################################

# user-facing field name -> (index field, kind)
LINK_QUERY_FIELDS = {
    "vault": ("vault", "term"),
    "tippr": ("vault", "term"),
    "author": ("author", "term"),
    "site": ("site", "term"),
    "nsfw": ("over18", "bool"),
    "over18": ("over18", "bool"),
    "self": ("is_self", "bool"),
    "is_self": ("is_self", "bool"),
    "flair": ("flair_text", "match"),
    "flair_text": ("flair_text", "match"),
    "flair_css_class": ("flair_css_class", "term"),
    "title": ("title", "match"),
    "selftext": ("selftext", "match"),
    "text": ("selftext", "match"),
    "url": ("url", "match"),
}

LINK_TEXT_FIELDS = ["title^3", "title.plain^2", "selftext", "selftext.plain",
                    "flair_text", "url^0.5"]

_TRUE = ("1", "yes", "true", "y", "on")
_FALSE = ("0", "no", "false", "n", "off")
_FIELD_RE = re.compile(r"^(-?)([a-z_]+):(.+)$", re.S)


def split_query(query, known_fields):
    """Split a query into field terms and free text.

    Returns ([(negate, field, value), ...], free_text). Field names that
    aren't in known_fields stay in the free text.
    """
    try:
        tokens = shlex.split(query, posix=True)
    except ValueError:
        # unbalanced quotes: fall back to whitespace splitting
        tokens = query.replace('"', " ").split()

    terms = []
    free = []
    for token in tokens:
        m = _FIELD_RE.match(token)
        if m and m.group(2).lower() in known_fields:
            terms.append((m.group(1) == "-", m.group(2).lower(), m.group(3)))
        elif " " in token:
            # a phrase that shlex unquoted
            free.append('"%s"' % token.replace('"', ""))
        else:
            free.append(token)
    return terms, " ".join(free)


def _free_text_query(text, fields):
    """Relevance query for free text: exact matches score highest, close
    misspellings still match."""
    return {
        "bool": {
            "should": [
                {"simple_query_string": {
                    "query": text,
                    "fields": fields,
                    "default_operator": "and",
                    "flags": "AND|OR|NOT|PHRASE|PRECEDENCE|PREFIX|WHITESPACE",
                }},
                {"multi_match": {
                    "query": text,
                    "fields": fields,
                    "fuzziness": "AUTO",
                    "prefix_length": 1,
                    "operator": "and",
                    "boost": 0.3,
                }},
            ],
            "minimum_should_match": 1,
        },
    }


class OpenSearchQuery:
    kind = None
    sorts = {}
    recents = {None: None}
    known_syntaxes = ("lucene", "plain")
    default_syntax = "lucene"

    def __init__(self, query, vault=None, sort=None, syntax=None,
                 faceting=None, recent=None, include_over18=True, num=1000,
                 **kw):
        if syntax is None:
            syntax = self.default_syntax
        elif syntax not in self.known_syntaxes:
            raise ValueError("Unknown search syntax: %s" % syntax)
        self.query = filters._force_unicode(query or "")
        self.syntax = syntax
        # nothing is converted; kept for the search page template
        self.converted_data = None
        self.vault = vault
        self._sort = sort
        self.sort = sort if sort in self.sorts else self.default_sort
        self._recent = recent
        self.recent = recent if recent in self.recents else None
        self.include_over18 = include_over18
        self.faceting = faceting
        self.num = min(num, MAX_RESULTS)
        self.results = None

    def __repr__(self):
        return "<%s> query:%r sort:%s" % (self.__class__.__name__,
                                          self.query, self.sort)

    def run(self, after=None, reverse=False, num=1000, _update=False):
        results = self._run(num=min(max(num, self.num), MAX_RESULTS))
        docs = r2utils.get_after(results.docs, after, num, reverse=reverse)
        self.results = Results(docs, results.hits, results._facets)
        return self.results

    def build(self):
        raise NotImplementedError

    def _run(self, num):
        body = self.build()
        if body is None:
            return Results([], 0, {})
        body["size"] = num
        body["_source"] = False
        body["track_total_hits"] = True
        if self.faceting:
            body["aggs"] = self.aggregations()

        if g.sqlprinting:
            g.log.info("%s %s", self, json.dumps(body))

        timer = g.stats.get_timer("opensearch_timer")
        timer.start()
        try:
            response = _request("POST", "/%s/_search" % index_name(self.kind),
                                body=body)
        except (SearchHTTPError, SearchError) as e:
            g.log.error("Search Error: %r", e)
            raise
        finally:
            timer.stop()

        hits = response["hits"]["total"]["value"]
        docs = [hit["_id"] for hit in response["hits"]["hits"]]
        facets = {}
        for name, agg in response.get("aggregations", {}).items():
            facets[name] = [dict(value=b["key"], count=b["doc_count"])
                            for b in agg["buckets"]]
        return Results(docs, hits, facets)

    def aggregations(self):
        return {}


class OpenSearchLinkQuery(OpenSearchQuery):
    kind = "links"
    sorts = {
        "relevance": None,
        "hot": [{"hot": "desc"}],
        "top": [{"score": "desc"}],
        "new": [{"timestamp": "desc"}],
        "comments": [{"num_comments": "desc"}],
    }
    default_sort = "relevance"
    recents = {
        "hour": "now-1h",
        "day": "now-1d",
        "week": "now-7d",
        "month": "now-31d",
        "year": "now-366d",
        "all": None,
        None: None,
    }

    def build(self):
        if self.syntax == "plain":
            terms, text = [], self.query.strip()
        else:
            terms, text = split_query(self.query, LINK_QUERY_FIELDS)
        if not terms and not text:
            return None

        must = []
        filter_ = []
        must_not = []

        for negate, name, value in terms:
            field, kind = LINK_QUERY_FIELDS[name]
            if kind == "bool":
                value = value.lower()
                if value in _TRUE:
                    clause = {"term": {field: True}}
                elif value in _FALSE:
                    clause = {"term": {field: False}}
                else:
                    raise InvalidQuery("%s must be yes or no" % name)
                (must_not if negate else filter_).append(clause)
            elif kind == "term":
                clause = {"term": {field: value}}
                (must_not if negate else filter_).append(clause)
            else:
                clause = {"match": {field: {"query": value,
                                            "operator": "and"}}}
                (must_not if negate else must).append(clause)

        if text:
            must.append(_free_text_query(text, LINK_TEXT_FIELDS))

        restriction = self._vault_restriction(self.vault)
        if restriction == "nothing":
            return None
        if restriction:
            filter_.append(restriction)
        if self.recent and self.recents[self.recent]:
            filter_.append({"range": {"timestamp": {
                "gte": self.recents[self.recent]}}})
        if not self.include_over18:
            filter_.append({"term": {"over18": False}})

        query = {"bool": {"must": must or [{"match_all": {}}],
                          "filter": filter_, "must_not": must_not}}

        body = {}
        sort = self.sorts[self.sort]
        if sort is None:
            # relevance, nudged by votes and age
            body["query"] = {"function_score": {
                "query": query,
                "functions": [
                    {"field_value_factor": {"field": "ups",
                                            "modifier": "log2p",
                                            "missing": 0}},
                    {"gauss": {"timestamp": {"origin": "now",
                                             "offset": "7d",
                                             "scale": "180d",
                                             "decay": 0.5}}},
                ],
                "score_mode": "multiply",
                "boost_mode": "multiply",
            }}
            body["sort"] = ["_score", {"timestamp": "desc"}]
        else:
            body["query"] = query
            body["sort"] = sort + [{"timestamp": "desc"}]
        return body

    def aggregations(self):
        aggs = {}
        for name, options in self.faceting.items():
            if name in ("tippr", "vault"):
                aggs[name] = {"terms": {"field": "vault",
                                        "size": options.get("count", 20)}}
        return aggs

    @staticmethod
    def _vault_restriction(vault):
        """A filter clause limiting results to the vault (or None for no
        limit, or "nothing" when the restriction can't match anything)."""
        if (not vault) or vault == All or isinstance(vault, DefaultVault):
            return None
        elif isinstance(vault, MultiVault):
            return {"terms": {"vault_id": list(vault.vault_ids)}}
        elif isinstance(vault, DomainVault):
            return {"term": {"site": vault.domain}}
        elif vault == Friends:
            if not c.user_is_loggedin or not c.user.friends:
                return "nothing"
            return {"terms": {"author_fullname": [
                Account._fullname_from_id36(r2utils.to36(id_))
                for id_ in c.user.friends]}}
        elif isinstance(vault, AllMinus):
            return {"bool": {"must_not": [
                {"terms": {"vault_id": list(vault.exclude_sr_ids)}}]}}
        elif not isinstance(vault, FakeVault):
            return {"term": {"vault_id": vault._id}}
        return None


class OpenSearchVaultQuery(OpenSearchQuery):
    kind = "vaults"
    sorts = {"relevance": None}
    default_sort = "relevance"
    known_syntaxes = ("plain", "lucene")
    default_syntax = "plain"

    def __init__(self, query, sort=None, **kw):
        # the vault search page passes no vault
        kw.pop("vault", None)
        super().__init__(query, sort=sort, **kw)

    def build(self):
        text = self.query.strip()
        if not text:
            return None
        name = text.lower()
        if name.startswith("/v/"):
            name = name[3:]
        elif name.startswith("v/"):
            name = name[2:]

        query = {"bool": {
            "should": [
                # exact name first
                {"term": {"name.raw": {"value": name, "boost": 20}}},
                # then names starting with the text
                {"multi_match": {
                    "query": name,
                    "type": "bool_prefix",
                    "fields": ["name", "name._2gram", "name._3gram"],
                    "boost": 4,
                }},
                {"multi_match": {
                    "query": text,
                    "fields": ["title^2", "header_title", "description",
                               "sidebar^0.5"],
                    "fuzziness": "AUTO",
                    "prefix_length": 1,
                    "operator": "and",
                }},
            ],
            "minimum_should_match": 1,
            "filter": ([] if self.include_over18 else
                       [{"term": {"over18": False}}]),
        }}
        return {
            "query": {"function_score": {
                "query": query,
                "field_value_factor": {"field": "subscribers",
                                       "modifier": "log2p", "missing": 0},
                "boost_mode": "multiply",
            }},
            "sort": ["_score", {"subscribers": "desc"}],
        }


def suggest_vaults(prefix, include_over18=True, num=10):
    """Vault names starting with prefix, most subscribed first."""
    prefix = prefix.strip().lower()
    if not prefix:
        return []
    filter_ = [] if include_over18 else [{"term": {"over18": False}}]
    body = {
        "size": num,
        "_source": ["name"],
        "query": {"bool": {
            "must": [{"multi_match": {
                "query": prefix,
                "type": "bool_prefix",
                "fields": ["name", "name._2gram", "name._3gram"],
            }}],
            "filter": filter_,
        }},
        "sort": [{"subscribers": "desc"}],
    }
    response = _request("POST", "/%s/_search" % index_name("vaults"),
                        body=body)
    return [hit["_source"]["name"] for hit in response["hits"]["hits"]]


###############################################################################
# Indexing
###############################################################################

class OpenSearchUploader:
    types = ()
    kind = None
    use_safe_get = False

    def __init__(self, fullnames=None, things=None):
        self.fullnames = fullnames or []
        self.things = things

    @classmethod
    def desired_fullnames(cls, items):
        """Fullnames in items that are instances of cls.types"""
        type_ids = [type_._type_id for type_ in cls.types]
        fullnames = set()
        for item in items:
            if r2utils.decompose_fullname(item["fullname"])[1] in type_ids:
                fullnames.add(item["fullname"])
        return fullnames

    def batch_lookups(self):
        if self.things is not None:
            return
        try:
            self.things = Thing._by_fullname(self.fullnames, data=True,
                                             return_dict=False)
        except NotFound:
            if self.use_safe_get:
                self.things = safe_get(Thing._by_fullname, self.fullnames,
                                       data=True, return_dict=False)
            else:
                raise

    def actions(self):
        """NDJSON lines for the _bulk API"""
        self.batch_lookups()
        index = index_name(self.kind)
        lines = []
        for thing in self.things:
            try:
                if (not thing._spam and not thing._deleted and
                        self.should_index(thing)):
                    doc = self.document(thing)
                    lines.append(json.dumps(
                        {"index": {"_index": index, "_id": thing._fullname}}))
                    lines.append(json.dumps(doc))
                else:
                    lines.append(json.dumps(
                        {"delete": {"_index": index, "_id": thing._fullname}}))
            except (AttributeError, KeyError) as e:
                # As with the other providers: leave the batch on the queue
                # (it may be DB lag) unless told to skip bad things.
                if not self.use_safe_get:
                    raise
                g.log.warning("Ignoring problem on thing %r.\n\n%r", thing, e)
        return lines

    def inject(self, quiet=False):
        """Send the things to OpenSearch. Returns the seconds spent on it."""
        lines = self.actions()
        if not lines:
            return 0

        start = time.time()
        response = _request("POST", "/_bulk", ndjson="\n".join(lines) + "\n")
        elapsed = time.time() - start

        adds = deletes = errors = 0
        for item in response.get("items", []):
            action, result = next(iter(item.items()))
            status = result.get("status", 500)
            if action == "delete":
                if status < 300 or status == 404:
                    deletes += 1
                else:
                    errors += 1
            elif status < 300:
                adds += 1
            else:
                errors += 1
                g.log.warning("opensearch: %s %s failed: %r", action,
                              result.get("_id"), result.get("error"))

        g.stats.simple_event("opensearch.uploads.adds", delta=adds)
        g.stats.simple_event("opensearch.uploads.deletes", delta=deletes)
        g.stats.simple_event("opensearch.uploads.errors", delta=errors)
        if not quiet:
            print("%s Changes: +%i -%i (%i errors)" % (
                self.__class__.__name__, adds, deletes, errors))
        return elapsed


class LinkUploader(OpenSearchUploader):
    types = (Link,)
    kind = "links"

    def batch_lookups(self):
        super().batch_lookups()
        author_ids = [thing.author_id for thing in self.things
                      if hasattr(thing, "author_id")]
        vault_ids = [thing.vault_id for thing in self.things
                     if hasattr(thing, "vault_id")]
        try:
            self.accounts = Account._byID(author_ids, data=True,
                                          return_dict=True)
            self.vaults = Vault._byID(vault_ids, data=True, return_dict=True)
        except NotFound:
            if not self.use_safe_get:
                raise
            self.accounts = safe_get(Account._byID, author_ids, data=True,
                                     return_dict=True)
            self.vaults = safe_get(Vault._byID, vault_ids, data=True,
                                   return_dict=True)

    def should_index(self, thing):
        return (thing.promoted is None and
                getattr(thing, "vault_id", None) != -1)

    def document(self, thing):
        account = self.accounts[thing.author_id]
        vault = self.vaults[thing.vault_id]
        doc = LinkFields(thing, account, vault).fields()
        doc.pop("tippr", None)
        doc["over18"] = bool(doc.get("over18"))
        doc["is_self"] = bool(doc.get("is_self"))
        doc["score"] = thing._score
        doc["hot"] = thing._hot
        return doc


class VaultUploader(OpenSearchUploader):
    types = (Vault,)
    kind = "vaults"

    def should_index(self, thing):
        return thing._id != Vault.get_promote_vault_id()

    def document(self, thing):
        doc = VaultFields(thing).fields()
        doc["fullname"] = thing._fullname
        doc["over18"] = bool(doc.get("over18"))
        return doc


@g.stats.amqp_processor("search_q")
def _run_changed(msgs, chan):
    """Index the things named in a batch of cloudsearch_changes messages"""
    start = datetime.now(g.tz)
    changed = [pickle.loads(msg.body) for msg in msgs]

    link_fns = LinkUploader.desired_fullnames(changed)
    vault_fns = VaultUploader.desired_fullnames(changed)

    elapsed = 0
    if link_fns:
        elapsed += LinkUploader(fullnames=link_fns).inject()
    if vault_fns:
        elapsed += VaultUploader(fullnames=vault_fns).inject()

    totaltime = (datetime.now(g.tz) - start).total_seconds()
    print("%s: %d messages in %.2fs (%.2fs waiting on opensearch); "
          "%d duplicates, %s remaining" % (
              start, len(changed), totaltime, elapsed,
              len(changed) - len(link_fns | vault_fns),
              msgs[-1].delivery_info.get("message_count", "unknown")))


def _progress_key(item):
    return "%s/%s" % (item._id, item._date)


def _rebuild(cls, uploader_cls, estimate, chunk_size=500, sleeptime=0):
    q = cls._query(cls.c._deleted == (True, False),
                   cls.c._spam == (True, False), sort=desc("_date"))
    q = r2utils.fetch_things2(q, chunk_size=chunk_size)
    q = r2utils.progress(q, verbosity=1000, estimate=estimate, persec=True,
                         key=_progress_key)
    for chunk in r2utils.in_chunks(q, size=chunk_size):
        uploader = uploader_cls(things=chunk)
        uploader.use_safe_get = True
        for attempt in range(5):
            try:
                uploader.inject(quiet=True)
            except (SearchHTTPError, SearchError) as e:
                if attempt == 4:
                    raise
                print("Got %r, sleeping %d secs" % (e, attempt + 1))
                time.sleep(attempt + 1)
            else:
                break
        if sleeptime:
            time.sleep(sleeptime)


class OpenSearchProvider(SearchProvider):
    """Search with OpenSearch (https://opensearch.org).

    example config:

    search_provider = opensearch
    opensearch_url = http://127.0.0.1:9200
    opensearch_index_prefix = tippr_
    # only if the security plugin is enabled
    opensearch_username =
    opensearch_password =
    opensearch_verify_tls = true
    """

    config = {
        ConfigValue.str: [
            "opensearch_url",
            "opensearch_index_prefix",
            "opensearch_username",
            "opensearch_password",
        ],
        ConfigValue.bool: [
            "opensearch_verify_tls",
        ],
    }

    InvalidQuery = (InvalidQuery,)
    SearchException = (SearchHTTPError, SearchError)

    SearchQuery = OpenSearchLinkQuery
    VaultSearchQuery = OpenSearchVaultQuery

    def run_changed(self, drain=False, min_size=1, limit=500, sleep_time=2,
                    use_safe_get=False, verbose=False):
        """Run by the search_q consumer: index things as they change"""
        ensure_indexes()
        if use_safe_get:
            OpenSearchUploader.use_safe_get = True
        amqp.handle_items("cloudsearch_changes", _run_changed,
                          min_size=min_size, limit=limit, drain=drain,
                          sleep_time=sleep_time, verbose=verbose)

    def rebuild_index(self, recreate=False):
        """Index every post and vault from the database.

        recreate=True drops the indexes first (needed after a mapping
        change); search returns nothing until the rebuild finishes.
        """
        ensure_indexes(recreate=recreate)
        _rebuild(Vault, VaultUploader, estimate=200000)
        _rebuild(Link, LinkUploader, estimate=50000000)

    def rebuild_link_index(self, *args, **kw):
        ensure_indexes()
        _rebuild(Link, LinkUploader, estimate=50000000)

    def rebuild_vault_index(self):
        ensure_indexes()
        _rebuild(Vault, VaultUploader, estimate=200000)

    def suggest_vaults(self, prefix, include_over18=True, num=10):
        return suggest_vaults(prefix, include_over18=include_over18, num=num)

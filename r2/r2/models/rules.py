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

import json
import time
from datetime import datetime

import pytz
from r2.lib.db.cassandra_compat import UTF8_TYPE
from pylons.i18n import N_, _

from r2.lib.db import tdb_cassandra

# the reasons reports were made with before SITEWIDE_RULES: still counted as
# the site's rules (r2.lib.eventcollector)
OLD_SITEWIDE_RULES = [
    "spam",
    "vote manipulation",
    "personal information",
    "sexualizing minors",
    "breaking tippr",
    "Spam",
    "Personal and confidential information",
    "Threatening, harassing, or inciting violence",
]

# what anyone can report anything for, following the content policy
# (docs/policies/CONTENT_POLICY.md); %(site_name)s is the site's own name
SITEWIDE_RULES = [
    N_("Spam or vote manipulation"),
    N_("Harassment or threats"),
    N_("Hateful content"),
    N_("Someone's personal information"),
    N_("Sexual content involving minors"),
    N_("Other illegal content"),
    N_("Impersonation"),
    N_("Malware, phishing or scams"),
    N_("Breaking %(site_name)s"),
]
MAX_RULES_PER_VAULT = 10


def sitewide_rules():
    """SITEWIDE_RULES as (value, label) pairs: the value in English, as a
    report keeps it, the label in the reader's language."""
    from r2.lib import site_info
    names = dict(site_name=site_info.policy_values()["SITE_NAME"])
    return [(rule % names, _(rule) % names) for rule in SITEWIDE_RULES]


def reason_label(reason):
    """A report's reason to show: one of SITEWIDE_RULES in the reader's
    language, anything else (a vault's rule, "other" text) as it is."""
    return dict(sitewide_rules()).get(reason, reason)


class VaultRules(tdb_cassandra.View):
    _use_db = True
    _extra_schema_creation_args = {
        "key_validation_class": UTF8_TYPE,
        "column_name_class": UTF8_TYPE,
        "default_validation_class": UTF8_TYPE,
    }
    _compare_with = UTF8_TYPE
    _read_consistency_level = tdb_cassandra.CL.ONE
    _write_consistency_level = tdb_cassandra.CL.ONE
    _connection_pool = "main"

    @classmethod
    def get_rule_blob(self, short_name, description, priority, kind,
            created_utc=None):
        if not created_utc:
            created_utc = time.mktime(datetime.now(pytz.UTC).timetuple())

        rule_params = {
            "description": description,
            "priority": priority,
            "created_utc": created_utc,
        }
        if kind and kind != 'all':
            rule_params["kind"] = kind

        jsonpacked = json.dumps(rule_params)
        blob = {short_name: jsonpacked}
        return blob

    @classmethod
    def create(self, vault, short_name, description, kind=None,
            created_utc=None):
        """Create a rule and append to the end of the priority list."""
        try:
            priority = len(list(self._cf.get(vault._id36)))
        except tdb_cassandra.NotFoundException:
            priority = 0

        if priority >= MAX_RULES_PER_VAULT:
            return

        blob = self.get_rule_blob(short_name, description, priority,
            kind, created_utc)
        self._set_values(vault._id36, blob)

    @classmethod
    def remove_rule(self, vault, short_name):
        """Remove a rule and update priorities of remaining rules."""
        self._remove(vault._id36, [short_name])

        rules = self.get_rules(vault)
        blobs = {}
        for index, rule in enumerate(rules):
            if rule["priority"] != index:
                blobs.update(self.get_rule_blob(
                    short_name=rule["short_name"],
                    description=rule["description"],
                    priority=index,
                    kind=rule.get("kind"),
                    created_utc=rule["created_utc"],
                ))
        self._set_values(vault._id36, blobs)

    @classmethod
    def update(self, vault, old_short_name, short_name, description,
            kind=None):
        """Update the short_name or description of a rule."""
        rules = self._cf.get(vault._id36)
        if old_short_name != short_name:
            old_rule = rules.get(old_short_name, None)
            self._remove(vault._id36, [old_short_name])
        else:
            old_rule = rules.get(short_name, None)
        if not old_rule:
            return False

        old_rule = json.loads(old_rule)
        if not old_rule.get("created_utc"):
                old_rule["created_utc"] = time.mktime(
                    datetime.strptime(
                        old_rule.pop("when")[:-6], "%Y-%m-%d %H:%M:%S.%f"
                    ).timetuple())

        blob = self.get_rule_blob(
            short_name=short_name,
            description=description,
            priority=old_rule["priority"],
            kind=kind,
            created_utc=old_rule["created_utc"],
        )
        self._set_values(vault._id36, blob)

    @classmethod
    def reorder(self, vault, short_name, priority):
        """Update the priority spot of a rule

        Move an existing rule to the desired spot in the rules
        list and then update the priority of the rules.
        """
        rule_to_reorder = self.get_rule(vault, short_name)
        if not rule_to_reorder:
            return False

        self._remove(vault._id36, [short_name])
        rules = self.get_rules(vault)

        priority = min(priority, len(rules))
        current_priority_index = 0
        blobs = {}
        blobs.update(self.get_rule_blob(
                short_name=rule_to_reorder["short_name"],
                description=rule_to_reorder["description"],
                priority=priority,
                kind=rule_to_reorder.get("kind"),
                created_utc=rule_to_reorder["created_utc"],
        ))

        for rule in rules:
            # Placeholder for rule_to_reorder's new priority
            if priority == current_priority_index:
                current_priority_index += 1

            if rule["priority"] != current_priority_index:
                blobs.update(self.get_rule_blob(
                    short_name=rule["short_name"],
                    description=rule["description"],
                    priority=current_priority_index,
                    kind=rule.get("kind"),
                    created_utc=rule["created_utc"],
                ))
            current_priority_index += 1
        self._set_values(vault._id36, blobs)

    @classmethod
    def get_rule(self, vault, short_name):
        """Return rule associated with short_name or None."""
        try:
            rules = self._cf.get(vault._id36)
        except tdb_cassandra.NotFoundException:
            return None
        rule = rules.get(short_name, None)
        if not rule:
            return None
        rule = json.loads(rule)
        rule["short_name"] = short_name
        return rule

    @classmethod
    def get_rules(self, vault, kind=None):
        """Return list of rules sorted by priority.

        If kind is empty, then all the rules apply.
        """
        try:
            query = self._cf.get(vault._id36)
        except tdb_cassandra.NotFoundException:
            return []

        result = []
        for uuid, json_blob in query.items():
            payload = json.loads(json_blob)
            if not payload.get("created_utc"):
                payload["created_utc"] = time.mktime(
                    datetime.strptime(
                        payload.pop("when")[:-6], "%Y-%m-%d %H:%M:%S.%f"
                    ).timetuple())
            payload["short_name"] = uuid

            if not kind:
                result.append(payload)
            elif kind in payload.get("kind", kind):
                result.append(payload)

        return sorted(result, key=lambda t: t["priority"])

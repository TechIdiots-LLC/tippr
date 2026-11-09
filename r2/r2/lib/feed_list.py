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
"""Lists of feeds: /admin/feeds' import and export, and
scripts/import_feeds.py.

Each line has a vault (/v/name), a feed address and, if you like, a [prefix]
for the posts' titles, separated by tabs, commas or spaces, and any of:
nsfw, ai:human, ai:assisted, ai:generated, bot:name, every:minutes, paused.
A prefix that isn't in square brackets is a tab-separated prefix:text. A
line without a vault uses the vault of the line above, anything else on a
line is ignored, and lines starting with # are skipped.

A list is matched to the feeds by vault and address. plan() works out what
a list would do and changes nothing; apply() does it. Importing doesn't
fetch the feeds, so a long list fits in a request: an address that isn't a
feed shows on /admin/feeds as an error at its first check.
"""

import re

from r2.lib import ai_content

URL_RE = re.compile(r"https?://[^\s|<>\"',]+")
WHOLE_URL_RE = re.compile(r"https?://\S+$")
VALID_URL_RE = re.compile(r"https?://[^\s/]+")
VAULT_RE = re.compile(r"(?:^|[\s|,;])/?v/([A-Za-z0-9_]{2,21})\b")
PREFIX_RE = re.compile(r"(\[[^\[\]\t|]{1,38}\])")
PREFIX_FIELD_RE = re.compile(r"(?:^|\t)prefix:([^\t]+)(?=\t|$)")
NSFW_RE = re.compile(r"(?:^|[\s|,;])nsfw(?=$|[\s|,;])", re.I)
AI_RE = re.compile(r"(?:^|[\s|,;])ai[:=](%s)(?=$|[\s|,;])"
                   % "|".join(ai_content.LABELS), re.I)
BOT_RE = re.compile(r"(?:^|[\s|,;])bot[:=](\S+)", re.I)
EVERY_RE = re.compile(r"(?:^|[\s|,;])every[:=](\d{1,6})(?=$|[\s|,;])", re.I)
PAUSED_RE = re.compile(r"(?:^|[\s|,;])paused(?=$|[\s|,;])", re.I)

MAX_PREFIX = 40
MAX_URL = 2000
MAX_INTERVAL_MINUTES = 10080


def _address(line):
    """(the line's feed address, the text to take out of the line); a
    tab-separated field that's all address is taken whole, so an address
    with a comma in it comes back from an export as it went."""
    for field in line.split("\t"):
        if WHOLE_URL_RE.match(field.strip()):
            return field.strip(), field
    found = URL_RE.search(line)
    if found:
        return found.group(0).rstrip(".;)"), found.group(0)
    return None, None


def read_lines(lines):
    """Each line with a feed address on it, as a dict: number, vault (None
    with no vault on or above it), url, prefix, over_18, ai_label, bot,
    every and paused."""
    entries, vault = [], None
    for number, line in enumerate(lines, 1):
        line = line.rstrip("\r\n")
        if line.lstrip().startswith("#"):
            continue
        # what's free text comes out first, so it isn't read as the rest
        prefix = None
        field = PREFIX_FIELD_RE.search(line)
        if field:
            prefix = field.group(1).strip()
            line = line[:field.start()] + line[field.end():]
        url, text = _address(line)
        rest = line.replace(text, " ") if url else line
        if not prefix:
            bracketed = PREFIX_RE.search(rest)
            if bracketed:
                prefix = bracketed.group(1)
                rest = rest.replace(prefix, " ")
        vault_match = VAULT_RE.search(" " + rest)
        if vault_match:
            vault = vault_match.group(1)
        if not url:
            continue
        ai_label = AI_RE.search(rest)
        bot = BOT_RE.search(rest)
        every = EVERY_RE.search(rest)
        entries.append(dict(
            number=number, vault=vault, url=url, prefix=prefix,
            over_18=bool(NSFW_RE.search(rest)),
            ai_label=ai_label.group(1).lower() if ai_label else None,
            bot=bot.group(1) if bot else None,
            every=int(every.group(1)) if every else None,
            paused=bool(PAUSED_RE.search(rest))))
    return entries


def export_line(feed):
    """A feed (r2.lib.feeds' row with vault_name and bot_name) as a line of
    a list."""
    fields = ["/v/%s" % feed["vault_name"]]
    prefix = feed["title_prefix"]
    if prefix:
        fields.append(prefix if PREFIX_RE.fullmatch(prefix)
                      else "prefix:%s" % prefix)
    fields.append(feed["url"])
    if feed["bot_name"]:
        fields.append("bot:%s" % feed["bot_name"])
    fields.append("every:%d" % feed["interval_minutes"])
    if feed["over_18"]:
        fields.append("nsfw")
    if feed["ai_content"]:
        fields.append("ai:%s" % feed["ai_content"])
    if not feed["enabled"]:
        fields.append("paused")
    return "\t".join(fields)


def export(feeds):
    """The feeds as a list to import. Feeds being deleted aren't in it, and
    one whose vault has gone can only be a comment."""
    lines = ["# One feed per line (/admin/feeds, Import or export a list)"]
    for feed in feeds:
        if feed.get("removing"):
            continue
        lines.append(export_line(feed) if feed["vault_name"]
                     else "# its vault is gone: %s" % feed["url"])
    return "\n".join(lines) + "\n"


def _key(vault_id, url):
    return (vault_id, url.rstrip("/").lower())


class _Lookups:
    """Vaults and bots by name, each looked up once in a list."""
    def __init__(self):
        self.vaults, self.bots = {}, {}

    def vault(self, name):
        from r2.lib.db.thing import NotFound
        from r2.models import Vault
        if name not in self.vaults:
            try:
                vault = Vault._by_name(name)
            except NotFound:
                vault = None
            # (/v/all and the like are no place to post)
            self.vaults[name] = vault if getattr(vault, "_id", None) else None
        return self.vaults[name]

    def bot_problem(self, name):
        """Why this name can't post feeds, or None (one that doesn't exist
        yet is made)."""
        from r2.lib.db.thing import NotFound
        from r2.lib.validator import chkuser
        from r2.models import Account
        if name not in self.bots:
            problem = None
            if not name:
                problem = "no_bot"
            elif not chkuser(name):
                problem = "bad_bot"
            else:
                try:
                    account = Account._by_name(name, allow_deleted=True)
                    if account._banned or account._deleted:
                        problem = "bot_suspended"
                except NotFound:
                    pass
            self.bots[name] = problem
        return self.bots[name]


def _changes(feed, entry, prefix, interval):
    """The settings that differ between a feed and its line, with the line's
    values. Whether it's paused, and its prefix and labels, are as the line
    has them; the interval only changes if the line names it (the bot is
    plan()'s, as it's an account to look up)."""
    values = {}
    if (feed["title_prefix"] or None) != prefix:
        values["title_prefix"] = prefix
    if bool(feed["over_18"]) != entry["over_18"]:
        values["over_18"] = entry["over_18"]
    if (feed["ai_content"] or None) != entry["ai_label"]:
        values["ai_content"] = entry["ai_label"]
    if bool(feed["enabled"]) == entry["paused"]:
        values["enabled"] = not entry["paused"]
    if interval and interval != feed["interval_minutes"]:
        values["interval_minutes"] = interval
    return values


def plan(text, default_bot, everything, update=False, remove_from=()):
    """What a list would do, changing nothing: a dict with rows, in the
    order they'd happen, each with action ("add", "change", "same", "remove"
    or "problem"), number (the line), vault and url; counts of the actions;
    and remove_blocked, when feeds weren't going to be removed because the
    list has problems or no feeds in it.

    everything: the feeds, with vault_name and bot_name. update: change the
    feeds already there to match their lines. remove_from: the feeds to
    remove from if they aren't in the list."""
    from r2.lib import feeds
    default_bot = (default_bot or "").strip()
    lookups = _Lookups()
    existing = {_key(f["vault_id"], f["url"]): f for f in everything}
    rows, listed, planned = [], set(), set()

    def problem(row, code):
        row.update(action="problem", problem=code)
        rows.append(row)

    entries = read_lines(text.splitlines())
    for entry in entries:
        row = dict(entry, action=None, changes=[])
        if not entry["vault"]:
            problem(row, "no_vault")
            continue
        if not VALID_URL_RE.match(entry["url"]) or len(entry["url"]) > MAX_URL:
            problem(row, "bad_address")
            continue
        vault = lookups.vault(entry["vault"])
        if not vault:
            problem(row, "no_such_vault")
            continue
        row["vault"] = vault.name
        key = _key(vault._id, entry["url"])
        feed = existing.get(key)
        if feed:
            listed.add(feed["id"])
        if key in planned or (feed and (not update or feed.get("removing"))):
            planned.add(key)
            row["action"] = "same"
            rows.append(row)
            continue
        planned.add(key)
        prefix = (entry["prefix"] or "").strip()[:MAX_PREFIX] or None
        interval = (max(feeds.MIN_INTERVAL_MINUTES,
                        min(MAX_INTERVAL_MINUTES, entry["every"]))
                    if entry["every"] else None)
        row.update(prefix=prefix, interval=interval, vault_obj=vault)
        if (entry["ai_label"] and entry["ai_label"] not in
                ai_content.allowed_labels(vault.ai_policy)):
            problem(row, "ai_label")
            continue
        if feed:
            row["feed"] = feed
            row["values"] = _changes(feed, entry, prefix, interval)
            row["changes"] = list(row["values"])
            row["new_bot"] = None
            if entry["bot"] and entry["bot"].lower() != feed["bot_name"].lower():
                row["new_bot"] = entry["bot"]
                row["changes"].append("bot")
                if lookups.bot_problem(row["new_bot"]):
                    problem(row, lookups.bot_problem(row["new_bot"]))
                    continue
            row["action"] = "change" if row["changes"] else "same"
        else:
            row["bot"] = entry["bot"] or default_bot
            if lookups.bot_problem(row["bot"]):
                problem(row, lookups.bot_problem(row["bot"]))
                continue
            row["action"] = "add"
        rows.append(row)

    # a mistyped vault would otherwise delete the feeds it was meant to keep
    remove_blocked = bool(remove_from) and (
        not entries or any(r["action"] == "problem" for r in rows))
    if not remove_blocked:
        for feed in remove_from:
            if feed["id"] not in listed and not feed.get("removing"):
                rows.append(dict(action="remove", number=None, feed=feed,
                                 vault=feed["vault_name"], url=feed["url"],
                                 changes=[]))
    counts = {}
    for row in rows:
        counts[row["action"]] = counts.get(row["action"], 0) + 1
    return dict(rows=rows, counts=counts, remove_blocked=remove_blocked)


def apply(planned):
    """Do what plan() worked out. Removed feeds' posts stay."""
    from r2.lib import feeds
    for row in planned["rows"]:
        if row["action"] == "add":
            feeds.add(row["url"], row["vault_obj"],
                      feeds.bot_account(row["bot"]),
                      row["interval"] or feeds.DEFAULT_INTERVAL_MINUTES,
                      row["prefix"], over_18=row["over_18"],
                      ai_content=row["ai_label"],
                      enabled=not row["paused"])
        elif row["action"] == "change":
            values = dict(row["values"])
            if row["new_bot"]:
                values["account_id"] = feeds.bot_account(row["new_bot"])._id
            feeds.update(row["feed"]["id"], **values)
        elif row["action"] == "remove":
            feeds.remove(row["feed"]["id"])

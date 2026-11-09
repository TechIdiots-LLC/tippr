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
"""Vaults' settings as a spreadsheet: /admin/vaults' CSV import and export.

The first row names the columns: name and any of the rest of COLUMNS. A
column left out isn't touched, so a file can be just name,ai_policy. A blank
cell leaves that setting as it is, except the two descriptions, where blank
is empty (as an export of a vault without one has it).

plan() works out what a file would do and changes nothing; apply() does it.
Vaults a file doesn't list are left alone: vaults can't be deleted
(r2.lib.vault_admin), so there's nothing to remove.
"""

import csv
import io

from pylons import app_globals as g

from r2.lib import ai_content

BOOLEANS = ("over_18", "allow_top", "show_media")
# the site-wide lists (r2.lib.vault_admin), where which is its name there
LISTS = {"default": "default", "featured": "feature"}
# column: the wiki page that holds it (as /about/edit saves them)
WIKI_PAGES = {"description": "config/sidebar",
              "public_description": "config/description"}
MAX_LENGTHS = {"title": 100, "public_description": 500, "description": 5120}
CHOICES = {"link_type": ("any", "link", "self"),
           "ai_policy": ai_content.POLICIES}
# what an admin can give a vault on /about/edit (gold_only needs gold, and
# employees_only an employee); a vault already another type can stay it
SETTABLE_TYPES = ("public", "restricted", "private", "archived",
                  "gold_restricted")

COLUMNS = ("name", "title", "public_description", "description", "type",
           "link_type", "ai_policy", "lang") + BOOLEANS + tuple(LISTS)

YES = ("yes", "y", "true", "1")
NO = ("no", "n", "false", "0")

# a spreadsheet runs a cell starting with one of these as a formula, and
# members write these titles and descriptions
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _safe(value):
    return "'" + value if value.startswith(FORMULA_START) else value


def _cell(value):
    """A cell as it was before _safe, in the line endings vaults keep (a
    textarea sends \\r\\n), without the spaces around it."""
    value = (value or "").replace("\r\n", "\n").strip()
    if value[:1] == "'" and value[1:].startswith(FORMULA_START):
        value = value[1:]
    return value


def all_vaults():
    """Every vault, the banned ones too."""
    from r2.lib.db.operators import asc
    from r2.lib.utils import fetch_things2
    from r2.models import Vault
    return fetch_things2(Vault._query(Vault.c._spam == (True, False),
                                      sort=asc("_date"), data=True))


def export(vaults):
    """The vaults as a CSV to import."""
    from r2.lib import vault_admin
    defaults, featured = vault_admin.default_ids(), vault_admin.featured_ids()
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for v in vaults:
        writer.writerow([
            v.name, _safe(v.title or ""),
            _safe(getattr(v, "public_description", "") or ""),
            _safe(getattr(v, "description", "") or ""),
            v.type, v.link_type, v.ai_policy, v.lang]
            + ["yes" if getattr(v, b, False) else "no" for b in BOOLEANS]
            + ["yes" if v._id in defaults else "no",
               "yes" if v._id in featured else "no"])
    return out.getvalue()


def _read(text):
    """(the columns we know, the columns we don't, [(row number, row)]);
    None if there's no name column. csv.Error if it can't be read."""
    first_line = text.split("\n", 1)[0]
    delimiter = max((",", ";", "\t"), key=first_line.count)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    header = [h.strip().lower() for h in next(reader, [])]
    if "name" not in header:
        return None
    rows = []
    for number, cells in enumerate(reader, 2):
        if any(c.strip() for c in cells):
            rows.append((number, dict(zip(header, cells))))
    return ([h for h in header if h in COLUMNS],
            [h for h in header if h and h not in COLUMNS], rows)


def _wanted(row, columns):
    """(the settings a row gives, or None; the problem and its column)."""
    wanted = {}
    for column in columns:
        if column == "name":
            continue
        value = _cell(row.get(column))
        if column in WIKI_PAGES:
            pass
        elif not value:
            continue
        if len(value) > MAX_LENGTHS.get(column, len(value)):
            return None, ("too_long", column)
        if column in CHOICES and value not in CHOICES[column]:
            return None, ("bad_value", column)
        if column == "lang" and value not in g.all_languages:
            return None, ("bad_value", column)
        if column == "type":
            from r2.models import Vault
            if value not in Vault.valid_types:
                return None, ("bad_value", column)
        if column in BOOLEANS or column in LISTS:
            if value.lower() not in YES + NO:
                return None, ("bad_value", column)
            value = value.lower() in YES
        wanted[column] = value
    return wanted, None


def _current(vault, column, defaults, featured):
    if column == "default":
        return vault._id in defaults
    if column == "featured":
        return vault._id in featured
    if column in WIKI_PAGES:
        return (getattr(vault, column, "") or "").replace("\r\n", "\n").strip()
    if column in BOOLEANS:
        return bool(getattr(vault, column, False))
    return getattr(vault, column)


def plan(text, create=False):
    """What a CSV would do, changing nothing: a dict with rows, each with
    action ("create", "change", "same" or "problem"), number (the row) and
    name; counts of the actions; ignored, the columns it doesn't know; and
    error ("no_name" or "unreadable") when it can't be read at all."""
    from r2.lib import vault_admin
    from r2.lib.db.thing import NotFound
    from r2.models import Vault
    result = dict(rows=[], counts={}, ignored=[], error=None)
    try:
        read = _read(text)
    except csv.Error:
        result["error"] = "unreadable"
        return result
    if read is None:
        result["error"] = "no_name"
        return result
    columns, result["ignored"], lines = read
    defaults, featured = vault_admin.default_ids(), vault_admin.featured_ids()
    seen = set()
    for number, line in lines:
        name = _cell(line.get("name")).lstrip("/").removeprefix("v/").strip("/")
        row = dict(number=number, name=name, action=None, changes=[],
                   problem=None, column=None)
        result["rows"].append(row)

        def problem(code, column=None):
            row.update(action="problem", problem=code, column=column)

        wanted, trouble = _wanted(line, columns)
        if trouble:
            problem(*trouble)
            continue
        if name.lower() in seen:
            problem("repeated")
            continue
        seen.add(name.lower())
        try:
            vault = Vault._by_name(name, _update=True)
        except NotFound:
            vault = None
        except ValueError:
            vault = None
        # (/v/all and the like aren't vaults to set up)
        if vault is not None and not getattr(vault, "_id", None):
            problem("not_a_vault")
            continue

        if vault is None:
            if not create:
                problem("no_such_vault")
            elif not Vault.is_valid_name(name):
                problem("bad_name")
            elif not wanted.get("title"):
                problem("no_title")
            elif wanted.get("type", "public") not in SETTABLE_TYPES:
                problem("bad_value", "type")
            else:
                row.update(action="create", wanted=wanted,
                           changes=list(wanted))
            continue

        row["name"] = vault.name
        changes = {column: value for column, value in wanted.items()
                   if value != _current(vault, column, defaults, featured)}
        if getattr(vault, "quarantine", False):
            changes.pop("allow_top", None)
            changes.pop("show_media", None)
        if changes.get("type") and changes["type"] not in SETTABLE_TYPES:
            problem("bad_value", "type")
            continue
        if vault._spam and (changes.get("default") or changes.get("featured")):
            problem("banned")
            continue
        row.update(action="change" if changes else "same", vault=vault,
                   wanted=changes, changes=list(changes))
    for row in result["rows"]:
        result["counts"][row["action"]] = (
            result["counts"].get(row["action"], 0) + 1)
    return result


def _set_wiki_text(vault, column, value, admin):
    """A description, kept in its wiki page as /about/edit keeps it."""
    from r2.lib.db import tdb_cassandra
    from r2.models import ModAction, wiki
    pagename = WIKI_PAGES[column]
    try:
        page = wiki.WikiPage.get(vault, pagename)
    except tdb_cassandra.NotFound:
        page = wiki.WikiPage.create(vault, pagename)
    if page.revise(value, author=admin._id36):
        ModAction.create(vault, admin, "wikirevise",
                         details=wiki.modactions.get(pagename))
    setattr(vault, column, value)


def _save(vault, settings, admin):
    from r2.lib import vault_admin
    from r2.models import ModAction
    for column, value in settings.items():
        if column in WIKI_PAGES:
            _set_wiki_text(vault, column, value, admin)
        elif column not in LISTS:
            ModAction.create(vault, admin, action="editsettings",
                             details=column)
            setattr(vault, column, value)
    vault._commit()
    vault.update_search_index()
    for column, which in LISTS.items():
        if column in settings:
            vault_admin.set_listed(vault, which, settings[column], admin)


def _create(row, admin):
    """As /vaults/create makes one: the importing admin is its moderator."""
    from r2.lib.db import queries
    from r2.models import Vault
    wanted = dict(row["wanted"])
    kw = {column: wanted.pop(column) for column in tuple(wanted)
          if column in COLUMNS and column not in WIKI_PAGES
          and column not in LISTS}
    vault = Vault._new(name=row["name"], author_id=admin._id,
                       ip="127.0.0.1", **kw)
    vault.add_subscriber(admin)
    vault.add_moderator(admin)
    if not vault.hide_contributors:
        vault.add_contributor(admin)
    queries.new_Vault(vault)
    # (descriptions and the site-wide lists: what's left)
    _save(vault, wanted, admin)


def apply(planned, admin):
    """Do what plan() worked out."""
    for row in planned["rows"]:
        if row["action"] == "create":
            _create(row, admin)
        elif row["action"] == "change":
            _save(row["vault"], row["wanted"], admin)

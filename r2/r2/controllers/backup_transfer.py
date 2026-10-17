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
"""The backup transfer API: lets another tippr server copy this one's
backups (`tippr-backup import`, or "import from another server" on its
/admin/backups). Every call needs this server's transfer key, made on
/admin/backups, as "Authorization: Bearer <key>".

    GET  /backup_transfer/list               finished and running backups
    GET  /backup_transfer/manifest/<name>    one backup's manifest and files
    GET  /backup_transfer/file/<name>?path=&offset=
                                             up to 16 MB of one file
    POST /backup_transfer/export             start a new backup (offline=1
                                             stops this site while it runs)
"""

import json
import logging

from pylons import request, response

from r2.controllers.tippr_base import MinimalController
from r2.lib import backups
from r2.lib.base import abort
from r2.lib.csrf import csrf_exempt

log = logging.getLogger(__name__)


class BackupTransferController(MinimalController):
    def pre(self):
        MinimalController.pre(self)
        response.headers["Cache-Control"] = "no-store"
        auth = request.headers.get("Authorization", "")
        key = auth[len("Bearer "):] if auth.startswith("Bearer ") else ""
        if not backups.check_transfer_key(key.strip()):
            log.warning("backup transfer: refused a request from %s",
                        request.ip)
            abort(403)

    def _name(self):
        # route variables reach actions only through validators
        return request.environ["pylons.routes_dict"].get("name", "")

    def _json(self, data):
        response.content_type = "application/json"
        return json.dumps(data)

    def GET_list(self):
        return self._json({"backups": [backups.public_summary(m)
                                       for m in backups.list_backups()]})

    def GET_manifest(self):
        manifest = backups.get_backup(self._name())
        if not manifest:
            abort(404)
        return self._json(manifest)

    def GET_file(self):
        try:
            offset = int(request.GET.get("offset", 0))
        except ValueError:
            abort(400)
        chunk = backups.read_chunk(self._name(), request.GET.get("path", ""),
                                   offset)
        if chunk is None:
            abort(404)
        response.content_type = "application/octet-stream"
        return chunk

    # authenticated by the transfer key, never by cookies, so a page in the
    # browser can't make this request on someone's behalf
    @csrf_exempt
    def POST_export(self):
        if not backups.service_installed():
            abort(503)
        offline = request.POST.get("offline") in ("1", "true", "on")
        log.info("backup transfer: export requested by %s", request.ip)
        backups.queue_request("export", "transfer key (%s)" % request.ip,
                              offline=offline)
        return self._json({"queued": True})

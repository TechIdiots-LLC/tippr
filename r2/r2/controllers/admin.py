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

from pylons.i18n import _

from r2.lib.pages import (
    AdminAdSettings,
    AdminAntispam,
    AdminBackups,
    AdminCoins,
    AdminEmailSettings,
    AdminErrors,
    AdminGold,
    AdminPage,
    AdminSiteSettings,
)
from r2.lib.validator import (
    VAdmin,
    VModhash,
    VUploadLength,
    nop,
    validate,
)

from .tippr_base import TipprController


class AdminToolController(TipprController):
    @validate(
        VAdmin(),
        recipient=nop('recipient'),
    )
    def GET_coins(self, recipient):
        return AdminPage(content=AdminCoins(recipient)).render()

    @validate(
        VAdmin(),
        recipient=nop('recipient'),
    )
    def GET_gold(self, recipient):
        return AdminPage(content=AdminGold(recipient)).render()

    @validate(VAdmin())
    def GET_email(self):
        return AdminPage(content=AdminEmailSettings()).render()

    @validate(VAdmin())
    def GET_antispam(self):
        return AdminPage(content=AdminAntispam()).render()

    @validate(VAdmin())
    def GET_site(self):
        return AdminPage(content=AdminSiteSettings()).render()

    @validate(
        VAdmin(),
        VModhash(),
        file=VUploadLength("file", max_length=1024 * 1024, empty_error=None),
        remove=nop("remove"),
        kind=nop("kind"),
    )
    def POST_site_image(self, file, remove, kind):
        """Upload the header logo, favicon or share image, or go back to
        the default one."""
        from r2.lib import site_info
        if kind not in site_info.IMAGES:
            kind = "site_logo"
        if remove:
            site_info.save({kind: ""})
            return self.redirect("/admin/site")
        if not file:
            error = _("Choose an image of at most 1 MB.")
        else:
            url, error = site_info.store_image(kind, file)
            if url:
                site_info.save({kind: url})
                return self.redirect("/admin/site")
        return AdminPage(content=AdminSiteSettings(
            image_errors={kind: error})).render()

    # the logo's upload address before favicons and share images
    POST_site_logo = POST_site_image

    @validate(VAdmin())
    def GET_ads(self):
        return AdminPage(content=AdminAdSettings()).render()

    @validate(VAdmin())
    def GET_backups(self):
        return AdminPage(content=AdminBackups()).render()

    @validate(VAdmin())
    def GET_errors(self):
        return AdminPage(content=AdminErrors()).render()

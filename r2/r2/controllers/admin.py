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

from pylons import app_globals as g
from pylons import response
from pylons import tmpl_context as c
from pylons.i18n import _

from r2.lib.pages import (
    AdminAdSettings,
    AdminAntispam,
    AdminApps,
    AdminBackups,
    AdminCoins,
    AdminEmailSettings,
    AdminDomain,
    AdminDomains,
    AdminErrors,
    AdminFeeds,
    AdminImages,
    AdminPrivacy,
    AdminLiveConfig,
    AdminPostCleanup,
    AdminLoginSettings,
    AdminServerStatus,
    AdminPage,
    AdminPaymentSettings,
    AdminSiteSettings,
    AdminSupport,
    AdminSupportActivity,
    AdminSupportStaff,
    AdminSupportTicket,
    AdminUser,
    AdminUsers,
    AdminVault,
    AdminVaults,
)
from r2.lib.validator import (
    VAdmin,
    VBoolean,
    VInt,
    VLength,
    VSupportStaff,
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
        """Gold is given, made permanent or taken on the account's page on
        /admin/users now."""
        from urllib.parse import quote
        if recipient:
            return self.redirect("/admin/users/" + quote(recipient.strip()))
        return self.redirect("/admin/users")

    @validate(VAdmin())
    def GET_email(self):
        return AdminPage(content=AdminEmailSettings()).render()

    @validate(VAdmin())
    def GET_antispam(self):
        return AdminPage(content=AdminAntispam()).render()

    @validate(VAdmin())
    def GET_config(self):
        return AdminPage(content=AdminLiveConfig()).render()

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

    @validate(VAdmin(), show=nop("show"))
    def GET_images(self, show):
        return AdminPage(content=AdminImages(show=show)).render()

    @validate(
        VAdmin(),
        VModhash(),
        file=VUploadLength("file", max_length=1024 * 1024, empty_error=None),
        path=nop("path"),
        remove=nop("remove"),
        show=nop("show"),
    )
    def POST_images(self, file, path, remove, show):
        """Replace one of the site's images (r2.lib.site_images), or go
        back to the original."""
        from r2.lib import site_images
        error = None
        if path not in site_images.catalogue():
            error = _("There's no such image.")
        elif remove:
            site_images.save(path, None)
        elif not file:
            error = _("Choose an image of at most 1 MB.")
        else:
            entry, error = site_images.store(path, file)
            if entry:
                site_images.save(path, entry)
        if error:
            return AdminPage(content=AdminImages(
                show=show, errors={path: error})).render()
        query = "?show=%s" % show if show in AdminImages.SHOW else ""
        return self.redirect("/admin/images%s#image-%s" % (
            query, AdminImages.anchor(path)))

    @validate(VAdmin())
    def GET_ads(self):
        return AdminPage(content=AdminAdSettings()).render()

    @validate(VAdmin())
    def GET_logins(self):
        return AdminPage(content=AdminLoginSettings()).render()

    @validate(VAdmin())
    def GET_servers(self):
        """Each server's version, load, memory, disks and services
        (r2.lib.server_status)."""
        return AdminPage(content=AdminServerStatus()).render()

    @validate(VAdmin())
    def GET_payments(self):
        return AdminPage(content=AdminPaymentSettings()).render()

    @validate(VAdmin())
    def GET_backups(self):
        return AdminPage(content=AdminBackups()).render()

    @validate(VAdmin(), name=nop("name"))
    def GET_backup_download(self, name):
        """A finished backup as one .tar file, sent as it's read
        (r2.lib.backups.download)."""
        from r2.lib import backups
        found = backups.download(name)
        if not found:
            return self.abort404()
        size, chunks = found
        g.log.info("backups: %s downloaded %s", c.user.name, name)
        response.content_type = "application/x-tar"
        response.headers["Content-Disposition"] = (
            'attachment; filename="%s.tar"' % name)
        response.headers["Cache-Control"] = "no-store"
        response.app_iter = chunks
        response.content_length = size

    @validate(VAdmin())
    def GET_errors(self):
        return AdminPage(content=AdminErrors()).render()

    @validate(VAdmin())
    def GET_privacy(self):
        return AdminPage(content=AdminPrivacy()).render()

    @validate(VAdmin(), q=nop("q"), before=nop("before"), after=nop("after"),
              status=nop("status"))
    def GET_users(self, q, before, after, status):
        """Find accounts by name, email, IP or internal status, or with no
        search list them all a page at a time (r2.lib.user_admin)."""
        return AdminPage(content=AdminUsers(q, before=before, after=after,
                                            status=status)).render()

    @validate(VAdmin())
    def GET_user(self, username):
        from r2.lib.db.thing import NotFound
        from r2.models import Account
        try:
            account = Account._by_name(username, allow_deleted=True)
        except NotFound:
            return self.abort404()
        return AdminPage(content=AdminUser(account)).render()

    @validate(VAdmin(), q=nop("q"), show=nop("show"))
    def GET_vaults(self, q, show):
        """Find vaults by name; the newest or the banned ones
        (r2.lib.vault_admin)."""
        return AdminPage(content=AdminVaults(q, show)).render()

    @validate(VAdmin())
    def GET_vault(self, vaultname):
        from r2.lib.db.thing import NotFound
        from r2.models import Vault
        try:
            vault = Vault._by_name(vaultname, _update=True)
        except NotFound:
            return self.abort404()
        if not isinstance(vault, Vault):
            return self.abort404()
        return AdminPage(content=AdminVault(vault)).render()

    @validate(VAdmin())
    def GET_domains(self):
        """Banned domains (r2.lib.domain_bans)."""
        return AdminPage(content=AdminDomains()).render()

    @validate(VAdmin())
    def GET_domain(self, domain):
        """A domain: its ban and its recent links (r2.lib.domain_bans)."""
        from r2.lib import domain_bans
        domain = domain_bans.normalize(domain)
        if not domain:
            return self.abort404()
        return AdminPage(content=AdminDomain(domain)).render()

    @validate(VAdmin(), kind=nop("kind"), days=VInt("days", min=1, max=36500),
              vault=nop("vault"), bot=nop("bot"))
    def GET_cleanup(self, kind, days, vault, bot):
        """The post cleanup's rules and runs, and with kind, the posts that
        qualify now (r2.lib.post_cleanup)."""
        return AdminPage(content=AdminPostCleanup(kind, days, vault,
                                                  bot)).render()

    @validate(VAdmin(), q=nop("q"), vault=nop("vault"), bot=nop("bot"),
              status=nop("status"), sort=nop("sort"), order=nop("order"))
    def GET_feeds(self, q, vault, bot, status, sort, order):
        """Feeds posted to vaults by bot accounts (r2.lib.feeds): searched,
        filtered and sorted by the query (AdminFeeds)."""
        return AdminPage(content=AdminFeeds(q, vault, bot, status, sort,
                                            order)).render()

    @validate(VAdmin(), q=nop("q"), vault=nop("vault"), bot=nop("bot"),
              status=nop("status"), sort=nop("sort"), order=nop("order"))
    def GET_feeds_export(self, q, vault, bot, status, sort, order):
        """The feeds in this view as a list to import (r2.lib.feed_list)."""
        from r2.lib import feed_list
        page = AdminFeeds(q, vault, bot, status, sort, order)
        g.log.info("admin_feed: %s exported %d feeds", c.user.name,
                   len(page.feeds))
        response.content_type = "text/plain"
        response.charset = "utf-8"
        response.headers["Content-Disposition"] = (
            'attachment; filename="feeds.txt"')
        response.headers["Cache-Control"] = "no-store"
        return feed_list.export(page.feeds)

    @validate(
        VAdmin(),
        VModhash(),
        file=VUploadLength("file", max_length=1024 * 1024, empty_error=None),
        text=VLength("list", max_length=1024 * 1024, empty_error=None),
        default_bot=nop("default_bot"),
        update=VBoolean("update"),
        remove=VBoolean("remove"),
        go=nop("go"),
        q=nop("q"), vault=nop("vault"), bot=nop("bot"),
        status=nop("status"), sort=nop("sort"), order=nop("order"),
    )
    def POST_feeds(self, file, text, default_bot, update, remove, go, q, vault,
                   bot, status, sort, order):
        """Import a list of feeds, or (the "preview" button) show what it
        would do (r2.lib.feed_list). Only the feeds in this view are removed
        if they aren't in the list, so a list exported from a filtered view
        doesn't delete everything outside it."""
        from r2.lib import feed_list
        page = AdminFeeds(q, vault, bot, status, sort, order)
        if file:
            text = file.decode("utf-8-sig", "replace")
        bulk = dict(text=text or "", default_bot=default_bot or "",
                    update=update, remove=remove, result=None, done=False)
        if not (text or "").strip():
            bulk["error"] = _("Choose a file or paste a list, of at most 1 MB.")
        else:
            bulk["result"] = feed_list.plan(text, default_bot, page.everything,
                                            update,
                                            page.feeds if remove else ())
            if go == "import":
                feed_list.apply(bulk["result"])
                bulk["done"] = True
                g.log.info("admin_feed: %s imported a list: %s", c.user.name,
                           bulk["result"]["counts"])
                page = AdminFeeds(q, vault, bot, status, sort, order)
        page.bulk = bulk
        return AdminPage(content=page).render()

    @validate(VAdmin(), show=nop("show"))
    def GET_apps(self, show):
        """Registered API apps: approve, suspend or delete them."""
        if show not in AdminApps.FILTERS:
            show = "pending"
        return AdminPage(content=AdminApps(show)).render()

    @validate(VSupportStaff(), view=nop("view"), category=nop("category"))
    def GET_support(self, view, category):
        """The support queue (r2.lib.support)."""
        from r2.lib import support
        if view not in support.VIEWS:
            view = "needs_reply"
        if category not in support.CATEGORIES:
            category = None
        return AdminPage(content=AdminSupport(view, category)).render()

    @validate(VAdmin())
    def GET_support_staff(self):
        """Who besides the admins may use the support queue, and in which
        categories (r2.lib.support)."""
        return AdminPage(content=AdminSupportStaff()).render()

    @validate(VSupportStaff(), by=nop("by"))
    def GET_support_activity(self, by):
        """What the support staff have done lately (r2.lib.support)."""
        return AdminPage(content=AdminSupportActivity(by)).render()

    @validate(VSupportStaff())
    def GET_support_ticket(self, ticket_id):
        from r2.lib import support
        try:
            ticket = support.get_ticket(int(ticket_id))
        except (TypeError, ValueError):
            ticket = None
        if not ticket or not support.can_view(c.user, ticket["category"]):
            return self.abort404()
        return AdminPage(content=AdminSupportTicket(ticket)).render()

// The contents of this file are subject to the Common Public Attribution
// License Version 1.0 (the "License"); you may not use this file except in
// compliance with the License. You may obtain a copy of the License at
// https://github.com/TechIdiots-LLC/tippr/blob/master/LICENSE.
//
// Software distributed under the License is distributed on an "AS IS" basis,
// WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
// the specific language governing rights and limitations under the License.
//
// The Original Code is Tippr.
//
// The Initial Developer of the Original Code is TechIdiots LLC.
// Copyright (c) 2026 TechIdiots LLC. All Rights Reserved.
///////////////////////////////////////////////////////////////////////////////

/*
 * /admin/servers while an update runs (data-watch on .admin-servers,
 * r2.lib.pages.AdminServerStatus): every few seconds the page asks for
 * itself again and puts the new servers section in place, keeping the logs
 * that are open open. While the site doesn't answer (it's down while a
 * server installs), it says so and keeps asking; it stops once every
 * server has finished.
 */
r.adminServers = {
  EVERY: 5000,

  init: function() {
    if (!$('.admin-servers[data-watch]').length) {
      return
    }
    this._downSince = null
    this._schedule()
  },

  _schedule: function() {
    setTimeout(_.bind(this._check, this), this.EVERY)
  },

  _check: function() {
    $.ajax({url: window.location.pathname, dataType: 'html', cache: false,
            timeout: 20000})
      .done(_.bind(this._got, this))
      .fail(_.bind(this._down, this))
  },

  _got: function(html) {
    var $fresh = $('<div>').append($.parseHTML(html)).find('.admin-servers')
    if (!$fresh.length) {
      // an error page (the site is still coming up)
      return this._down()
    }
    var $page = $('.admin-servers')
    // the logs someone opened (or closed) stay that way
    var logs = {}
    $page.find('.server-card').each(function() {
      var $log = $(this).find('details')
      if ($log.length) {
        logs[$(this).data('server')] = $log.prop('open')
      }
    })
    $fresh.find('.server-card').each(function() {
      var open = logs[$(this).data('server')]
      if (open !== undefined) {
        $(this).find('details').prop('open', open)
      }
    })
    $page.replaceWith($fresh)
    this._downSince = null
    if ($fresh.is('[data-watch]')) {
      this._schedule()
    }
  },

  _down: function() {
    if (!this._downSince) {
      this._downSince = Date.now()
    }
    var minutes = Math.floor((Date.now() - this._downSince) / 60000)
    var text = r._("The site isn't answering: it's down while a server installs the update. This page keeps checking and catches up when it's back.")
    if (minutes) {
      text += ' ' + r.P_('(down %(num)s minute so far)',
                         '(down %(num)s minutes so far)', minutes)
                     .format({num: minutes})
    }
    $('.admin-servers .server-update-down').text(text).show()
    this._schedule()
  }
}

$(function() {
  r.adminServers.init()
})

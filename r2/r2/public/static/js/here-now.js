/* "N here now" on a thread: how many people have been on it in the last
 * 15 minutes (r2.lib.activity). The page asks /api/here_now when it opens
 * and every minute while it's on screen; each ask also counts this visitor
 * as still here. Counts under 100 are fuzzed by the service, shown with
 * a "~". */
r.hereNow = {
  EVERY: 60 * 1000,

  init: function () {
    var config = r.config.here_now
    var $heading = $('.commentarea .panestack-title')
    if (!config || !$heading.length) {
      return
    }
    this._link = config.link
    this._$label = $('<span class="here-now"></span>').appendTo($heading)
    this._ask()
    setInterval(_.bind(function () {
      if (!document.hidden) {
        this._ask()
      }
    }, this), this.EVERY)
  },

  _ask: function () {
    $.ajax({
      type: 'POST',
      url: '/api/here_now.json',
      data: {link_id: this._link},
      dataType: 'json',
      success: _.bind(this._show, this),
    })
  },

  _show: function (res) {
    if (!res || typeof res.count !== 'number') {
      return
    }
    var num = (res.fuzzed ? '~' : '') + res.count
    this._$label.text(r.P_('%(num)s here now', '%(num)s here now', res.count)
      .format({num: num}))
  },
}

$(function () { r.hereNow.init() })

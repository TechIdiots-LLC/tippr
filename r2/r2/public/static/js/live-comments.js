/* Live comments: new comments on this thread appear as they're posted,
 * when the site and the vault have them on (r2.lib.live_comments puts the
 * thread's websocket address in r.config.live_comments).
 *
 * The socket only says a comment arrived; it's fetched with
 * /api/morechildren, so it's rendered for this viewer (blocked users,
 * score threshold and so on) and put under its parent. That endpoint takes
 * one request per user at a time and 20 comments at most, so arrivals are
 * gathered for a moment and fetched in turn. */
r.liveComments = {
  WAIT: 1500,       // ms to gather arrivals before fetching them
  BATCH: 20,

  init: function () {
    var config = r.config.live_comments
    if (!config || !('WebSocket' in window)) {
      return
    }
    this._config = config
    this._queue = []
    this._timer = null
    this._busy = false
    this._socket = new r.WebSocket(config.url)
    this._socket.on('message:new_comment', this._arrived, this)
    this._socket.start()
  },

  _arrived: function (comment) {
    // already here (the viewer's own reply, or a reconnect)
    if ($('#thing_' + comment.name).length) {
      return
    }
    // a reply to a comment that isn't on the page: its "load more" link
    // will bring it
    if (comment.parent !== this._config.link &&
        !$('#thing_' + comment.parent).length) {
      return
    }
    this._queue.push(comment.id)
    this._schedule(this.WAIT)
  },

  _schedule: function (delay) {
    if (this._timer || this._busy || !this._queue.length) {
      return
    }
    this._timer = setTimeout(_.bind(this._fetch, this), delay)
  },

  _fetch: function () {
    this._timer = null
    var ids = _.uniq(this._queue.splice(0, this.BATCH))
    this._busy = true

    var done = _.bind(function () {
      this._busy = false
      this._schedule(this.WAIT)
    }, this)

    var inserted = _.bind(function (res) {
      $.handleResponse('morechildren')(res)
      var arrived = 0
      _.each(ids, function (id) {
        var $comment = $('.thing.comment[data-fullname$="_' + id + '"]')
          .not('.live-comment')
        if ($comment.length) {
          $comment.addClass('live-comment')
          arrived += 1
        }
      })
      this._counted(arrived)
      done()
    }, this)

    var failed = _.bind(function () {
      // try these again a little later
      this._queue = ids.concat(this._queue)
      this._busy = false
      this._schedule(this.WAIT * 4)
    }, this)

    $.request('morechildren', {
      link_id: this._config.link,
      sort: this._config.sort,
      children: ids.join(','),
    }, inserted, undefined, undefined, true, failed)
  },

  // the thread's comment count, in its "N comments" link and the "all N
  // comments" heading over the comments
  _counted: function (arrived) {
    if (!arrived) {
      return
    }
    var config = this._config
    config.num_comments += arrived
    var num = config.num_comments
    $('.thing.link[data-fullname="' + config.link + '"] a.comments')
      .text(r.P_('%(num)s comment', '%(num)s comments', num).format({num: num}))
    if (config.all_shown) {
      $('.commentarea .panestack-title .title')
        .text(r.P_('all %(num)s comment', 'all %(num)s comments', num)
          .format({num: num}))
    }
  },
}

$(function () { r.liveComments.init() })

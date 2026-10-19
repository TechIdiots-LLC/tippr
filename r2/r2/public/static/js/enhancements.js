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
 * Optional enhancements, like the Reddit Enhancement Suite's, so members
 * don't need a browser extension for them. Each is a preference under
 * "enhancements" on /prefs (night mode is a body class and a stylesheet,
 * nightmode.less):
 *
 *  - infinite scroll: the next page of a listing is added when you get to
 *    the bottom, after a "page N" divider
 *  - keyboard navigation: j/k move between posts or comments, a/z vote,
 *    enter opens, and so on (? shows the list)
 *  - hide child comments: links that fold up the replies under a comment,
 *    or under every top-level comment at once
 *  - show images: a button on posts that link straight to an image shows it
 *    in the listing, a "show images" tab shows them all, and they can open
 *    by themselves (not NSFW or spoiler posts)
 */
r.enhancements = {}

/* infinite scroll */

r.enhancements.infiniteScroll = {
  page: 1,
  loading: false,

  init: function() {
    this.$table = $('#siteTable')
    if (!this.$table.length || !this.nextUrl()) {
      return
    }
    this.$status = $('<div class="infinite-scroll-status"></div>')
      .insertAfter(this.$table)
    this.seen = {}
    this.$table.children('.thing').each(_.bind(function(i, el) {
      this.seen[$(el).data('fullname')] = true
    }, this))

    if (!('IntersectionObserver' in window)) {
      return
    }
    this.observer = new IntersectionObserver(_.bind(function(entries) {
      if (entries[0].isIntersecting) {
        this.load()
      }
    }, this), {rootMargin: '600px'})
    this.observer.observe(this.$status[0])
  },

  nextUrl: function() {
    var $next = this.$table.children('.nav-buttons')
      .find('a[rel~="next"]').last()
    return $next.attr('href')
  },

  load: function() {
    var url = this.nextUrl()
    if (this.loading || !url) {
      return
    }
    this.loading = true
    this.$status.text(r._('loading…')).removeClass('error')

    $.ajax({url: url, dataType: 'html'})
      .done(_.bind(function(html) {
        this.add(url, $($.parseHTML(html)).find('#siteTable').addBack('#siteTable'))
      }, this))
      .fail(_.bind(function() {
        this.$status.addClass('error').empty().append(
          $('<a href="#"></a>').text(r._('couldn\'t load more; try again'))
            .on('click', _.bind(function(e) {
              e.preventDefault()
              this.load()
            }, this)))
      }, this))
      .always(_.bind(function() {
        this.loading = false
      }, this))
  },

  add: function(url, $newTable) {
    var $oldNav = this.$table.children('.nav-buttons')
    var $newNav = $newTable.children('.nav-buttons')
    var $items = $newTable.children().not('.nav-buttons')
    var seen = this.seen

    // listings shift while you read them: skip posts already on the page
    $items = $items.filter(function() {
      var fullname = $(this).data('fullname')
      if (!fullname) {
        return true
      }
      if (seen[fullname]) {
        $(this).next('.clearleft').addClass('infinite-scroll-skip')
        return false
      }
      seen[fullname] = true
      return true
    }).not('.infinite-scroll-skip')

    this.page += 1
    var $divider = $('<div class="infinite-scroll-page"></div>').append(
      $('<a></a>').attr('href', url).text(
        r._('page %(num)s').format({num: this.page})))

    $oldNav.before($divider, $items)
    if ($newNav.length) {
      $oldNav.replaceWith($newNav)
    } else {
      $oldNav.remove()
    }

    if (this.nextUrl()) {
      this.$status.empty()
      // the observer only fires when the marker comes into view, so if a
      // short page left it in view, carry on
      _.defer(_.bind(function() {
        if (this.$status[0].getBoundingClientRect().top < window.innerHeight + 600) {
          this.load()
        }
      }, this))
    } else {
      this.$status.text(r._('there doesn\'t seem to be anything more here'))
      if (this.observer) {
        this.observer.disconnect()
      }
    }
    $(document).trigger('new_things_inserted')
  },
}

/* keyboard navigation */

r.enhancements.keyboardNav = {
  $selected: $(),

  init: function() {
    // [key, what it does, method]
    this.keys = [
      ['j', r._('next post or comment'), 'next'],
      ['k', r._('previous post or comment'), 'previous'],
      ['a', r._('upvote'), 'upvote'],
      ['z', r._('downvote'), 'downvote'],
      ['enter', r._('open the link (shift: in a new tab)'), 'open'],
      ['c', r._('open the comments'), 'comments'],
      ['x', r._('expand or collapse the preview, or the comment'), 'expand'],
      ['s', r._('save'), 'save'],
      ['r', r._('reply to the comment'), 'reply'],
      ['p', r._('parent comment'), 'parent'],
      ['n', r._('next page'), 'nextPage'],
      ['?', r._('show these keys'), 'help'],
    ]
    $(document).on('keydown', _.bind(this.keydown, this))
    // clicking a post or comment selects it (the innermost, for replies)
    $(document.body).on('click', _.bind(function(e) {
      var $thing = $(e.target).closest('.thing')
      if ($thing.length) {
        this.select($thing, false)
      }
    }, this))
  },

  typing: function(e) {
    var el = e.target
    return el.isContentEditable ||
      /^(input|textarea|select|button)$/i.test(el.tagName)
  },

  keydown: function(e) {
    if (e.ctrlKey || e.altKey || e.metaKey || this.typing(e)) {
      return
    }
    var key = e.key === 'Enter' ? 'enter' : e.key
    if (key !== '?' && key !== 'enter') {
      key = key.toLowerCase()
    }
    var action = _.find(this.keys, function(k) { return k[0] === key })
    if (!action) {
      return
    }
    if (key !== '?' && $('.keyboard-nav-help').length) {
      this.closeHelp()
    }
    if (this[action[2]](e) !== false) {
      e.preventDefault()
    }
  },

  things: function() {
    var $area = $('.commentarea')
    if ($area.length) {
      return $('.sitetable.linklisting > .thing.link')
        .add($area.find('.thing.comment'))
        .filter(':visible')
    }
    return $('#siteTable > .thing.link:visible, #siteTable > .thing.comment:visible')
  },

  select: function($thing, scroll) {
    if (!$thing.length) {
      return
    }
    this.$selected.removeClass('keyboard-selected')
    this.$selected = $thing.first().addClass('keyboard-selected')
    if (scroll) {
      var top = this.$selected.offset().top
      var height = this.$selected.outerHeight()
      var viewTop = $(window).scrollTop()
      var viewHeight = $(window).height()
      if (top < viewTop + 40 || top + Math.min(height, viewHeight / 2) > viewTop + viewHeight) {
        $('html, body').scrollTop(top - Math.round(viewHeight / 4))
      }
    }
  },

  move: function(step) {
    var $things = this.things()
    if (!$things.length) {
      return
    }
    var i = $things.index(this.$selected)
    if (i < 0) {
      this.select(step > 0 ? $things.first() : $things.last(), true)
      return
    }
    var next = i + step
    if (next >= $things.length && step > 0) {
      // infinite scroll may still be loading the next page
      r.enhancements.infiniteScroll.load()
      return
    }
    this.select($things.eq(Math.max(0, next)), true)
  },

  selected: function() {
    if (!this.$selected.length || !$.contains(document, this.$selected[0])) {
      this.$selected = $()
      this.move(1)
    }
    return this.$selected
  },

  entry: function() {
    // a comment's own parts, not its replies'
    return this.selected().children('.entry')
  },

  next: function() { this.move(1) },
  previous: function() { this.move(-1) },

  vote: function(dir) {
    this.selected().children('.midcol').find('.arrow.' + dir + ', .arrow.' + dir + 'mod')
      .first().click()
  },
  upvote: function() { this.vote('up') },
  downvote: function() { this.vote('down') },

  open: function(e) {
    var $title = this.entry().find('a.title').first()
    var href = $title.attr('href')
    if (!href) {
      return false
    }
    if (e.shiftKey || r.config.new_window) {
      window.open(href, '_blank', 'noopener')
    } else {
      window.location.href = href
    }
  },

  comments: function(e) {
    var href = this.entry().find('a.comments').first().attr('href')
    if (!href) {
      return false
    }
    if (e.shiftKey) {
      window.open(href, '_blank', 'noopener')
    } else {
      window.location.href = href
    }
  },

  expand: function() {
    var $thing = this.selected()
    var $button = this.entry().find('.expando-button').first()
    if ($button.length) {
      $button.click()
    } else if ($thing.hasClass('comment')) {
      this.entry().find('a.expand').first().click()
    }
  },

  save: function() {
    this.entry().find('.save-button a, .unsave-button a').first().click()
  },

  reply: function() {
    var $reply = this.entry().find('a[onclick*="reply"], .reply-button a').first()
    if (!$reply.length) {
      return false
    }
    $reply.click()
  },

  parent: function() {
    var $parent = this.selected().parent().closest('.thing.comment')
    this.select($parent, true)
  },

  nextPage: function() {
    var href = $('.nav-buttons a[rel~="next"]').last().attr('href')
    if (!href) {
      return false
    }
    window.location.href = href
  },

  help: function() {
    if ($('.keyboard-nav-help').length) {
      this.closeHelp()
      return
    }
    var $list = $('<dl></dl>')
    _.each(this.keys, function(k) {
      $list.append($('<dt></dt>').text(k[0]), $('<dd></dd>').text(k[1]))
    })
    $('<div class="keyboard-nav-help" role="dialog"></div>')
      .append($('<h2></h2>').text(r._('keyboard shortcuts')), $list,
              $('<p class="details"></p>').text(
                r._('turn these off under "enhancements" in your preferences')))
      .on('click', _.bind(this.closeHelp, this))
      .appendTo(document.body)
  },

  closeHelp: function() {
    $('.keyboard-nav-help').remove()
  },
}

/* hide child comments */

r.enhancements.hideChildComments = {
  init: function() {
    var $area = $('.commentarea')
    if (!$area.length) {
      return
    }
    $area.find('> .sitetable > .thing.comment').each(_.bind(function(i, el) {
      this.addLink($(el))
    }, this))
    if (!$area.find('> .sitetable > .thing.comment > .child .thing').length) {
      return
    }
    this.$all = $('<a href="#" class="hide-all-child-comments"></a>')
      .text(r._('hide all child comments'))
      .on('click', _.bind(this.toggleAll, this))
    $area.find('.panestack-title').first().append(' ', this.$all)
    $(document).on('new_things_inserted', _.bind(function() {
      $area.find('> .sitetable > .thing.comment').each(_.bind(function(i, el) {
        this.addLink($(el))
      }, this))
    }, this))
  },

  addLink: function($comment) {
    var $buttons = $comment.children('.entry').find('ul.buttons').first()
    if (!$buttons.length || $buttons.find('.hide-child-comments').length ||
        !$comment.children('.child').find('.thing').length) {
      return
    }
    var $link = $('<a href="#"></a>').text(r._('hide child comments'))
      .on('click', _.bind(function(e) {
        e.preventDefault()
        this.toggle($comment)
      }, this))
    $('<li class="hide-child-comments"></li>').append($link).appendTo($buttons)
  },

  toggle: function($comment, hide) {
    var $child = $comment.children('.child')
    if (hide === undefined) {
      hide = !$child.hasClass('children-hidden')
    }
    $child.toggleClass('children-hidden', hide)
    $comment.children('.entry').find('.hide-child-comments a').text(
      hide ? r._('show child comments') : r._('hide child comments'))
  },

  toggleAll: function(e) {
    e.preventDefault()
    var hide = !this.$all.hasClass('hiding')
    this.$all.toggleClass('hiding', hide)
      .text(hide ? r._('show all child comments') : r._('hide all child comments'))
    $('.commentarea > .sitetable > .thing.comment').each(_.bind(function(i, el) {
      this.toggle($(el), hide)
    }, this))
  },
}

/* show images */

r.enhancements.images = {
  // links straight to an image, and imgur pages with a single image
  imageUrl: function(url) {
    if (!url || !/^https:\/\//i.test(url)) {
      return null
    }
    if (/\.(jpe?g|png|gif|webp|avif)(\?.*)?$/i.test(url)) {
      return url
    }
    var imgur = url.match(/^https:\/\/(?:i\.|m\.)?imgur\.com\/([a-z0-9]{5,8})$/i)
    if (imgur) {
      return 'https://i.imgur.com/' + imgur[1] + '.jpg'
    }
    return null
  },

  init: function(auto) {
    this.auto = auto
    this.allExpanded = auto
    this.addButtons()
    var $menu = $('.tabmenu').first()
    if ($menu.length && $('#siteTable .inline-image-button').length) {
      this.$all = $('<a href="#"></a>')
        .text(auto ? r._('hide images') : r._('show images'))
        .on('click', _.bind(this.toggleAll, this))
      $('<li class="show-images"></li>').append(this.$all).appendTo($menu)
    }
    $(document).on('new_things_inserted', _.bind(this.addButtons, this))
  },

  addButtons: function() {
    var self = this
    $('.thing.link').each(function() {
      var $thing = $(this)
      if ($thing.data('inline-image') !== undefined) {
        return
      }
      var src = self.imageUrl($thing.data('url'))
      $thing.data('inline-image', src || '')
      // the site's own expando already shows this one
      if (!src || $thing.children('.entry').find('.expando-button').length) {
        return
      }
      var $button = $('<button type="button" class="inline-image-button collapsed"></button>')
        .attr('aria-label', r._('show image'))
        .on('click', function(e) {
          e.preventDefault()
          self.toggle($thing)
        })
      $thing.children('.entry').find('.tagline').first().before($button)
      if (self.allExpanded && self.autoOk($thing)) {
        self.toggle($thing, true)
      }
    })
  },

  autoOk: function($thing) {
    return !$thing.hasClass('over18') && !$thing.hasClass('spoiler')
  },

  toggle: function($thing, show) {
    var $entry = $thing.children('.entry')
    var $button = $entry.find('.inline-image-button').first()
    var $box = $entry.children('.inline-image')
    if (show === undefined) {
      show = !$box.length || $box.is(':hidden')
    }
    if (show) {
      if (!$box.length) {
        var src = $thing.data('inline-image')
        $box = $('<div class="inline-image"></div>').append(
          $('<a></a>').attr({href: $thing.data('url'), target: '_blank', rel: 'noopener noreferrer'})
            .append($('<img alt="">').attr({
              src: src, loading: 'lazy', referrerpolicy: 'no-referrer',
            })))
        $entry.append($box)
      }
      $box.show()
    } else {
      $box.hide()
    }
    $button.toggleClass('expanded', show).toggleClass('collapsed', !show)
      .attr('aria-label', show ? r._('hide image') : r._('show image'))
  },

  toggleAll: function(e) {
    e.preventDefault()
    this.allExpanded = !this.allExpanded
    this.$all.text(this.allExpanded ? r._('hide images') : r._('show images'))
    var self = this
    $('#siteTable .thing.link').each(function() {
      var $thing = $(this)
      if ($thing.children('.entry').find('.inline-image-button').length &&
          (!self.allExpanded || self.autoOk($thing))) {
        self.toggle($thing, self.allExpanded)
      }
    })
  },
}

$(function() {
  if (r.config.show_images || r.config.auto_expand_images) {
    r.enhancements.images.init(r.config.auto_expand_images)
  }
  if (r.config.infinite_scroll) {
    r.enhancements.infiniteScroll.init()
  }
  if (r.config.keyboard_nav) {
    r.enhancements.keyboardNav.init()
  }
  if (r.config.hide_child_comments) {
    r.enhancements.hideChildComments.init()
  }
})

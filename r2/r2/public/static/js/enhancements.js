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
 *  - user tags: a private note and colour by a username (r2.lib.user_tags;
 *    the member's tags come in r.config.user_tags)
 *  - user info on hover: karma, account age and your tag
 *  - the parent comment on hover over a reply's "parent" link
 *  - posts you've opened: "(3 new)" by them in listings, the new comments
 *    highlighted when you go back, and fading or hiding them; remembered
 *    in this browser (localStorage), as RES does
 *  - comment navigator: jump between top-level comments, the submitter's,
 *    yours, new ones or ones with links
 *
 * Filters (hiding posts by keyword, domain, vault or user) happen on the
 * server: r2.lib.listing_filters.
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

    // jQuery drops the new page's scripts, so start its AdSense units here
    var $ads = $items.find('ins.adsbygoogle').add($items.filter('ins.adsbygoogle'))
    $ads.each(function() {
      try {
        (window.adsbygoogle = window.adsbygoogle || []).push({})
      } catch (e) {}
    })
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
    if (!this.$selected.length || !$.contains(document.documentElement, this.$selected[0])) {
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

/* user tags */

r.enhancements.userTags = {
  init: function(showButtons) {
    this.tags = r.config.user_tags || {}
    this.showButtons = showButtons
    this.decorate()
    $(document).on('new_things_inserted', _.bind(this.decorate, this))
    $(document).on('click', '.user-tag-button, .user-tag', _.bind(function(e) {
      e.preventDefault()
      e.stopPropagation()
      this.edit($(e.currentTarget).data('user'), $(e.currentTarget))
    }, this))
  },

  nameOf: function($author) {
    var href = $author.attr('href') || ''
    var m = href.match(/\/u(?:ser)?\/([^\/?#]+)/)
    return m ? decodeURIComponent(m[1]) : $author.text()
  },

  decorate: function() {
    var self = this
    $('a.author').each(function() {
      var $author = $(this)
      if ($author.data('user-tagged')) {
        return
      }
      $author.data('user-tagged', true)
      self.render($author, self.nameOf($author))
    })
  },

  render: function($author, name) {
    $author.nextAll('.user-tag, .user-tag-button').first()
      .filter(function() { return $(this).data('user') === name }).remove()
    var tag = this.tags[name.toLowerCase()]
    var $after = $author
    if (tag && (tag[0] || tag[1])) {
      var $tag = $('<a href="#" class="user-tag"></a>').data('user', name)
        .text(tag[0] || ' ')
        .attr('title', r._('your tag; click to change it'))
      if (tag[1]) {
        $tag.css({backgroundColor: tag[1], color: '#fff', borderColor: tag[1]})
      }
      $author.after($tag)
    } else if (this.showButtons) {
      $author.after($('<a href="#" class="user-tag-button"></a>').data('user', name)
        .attr({title: r._('tag this user'), 'aria-label': r._('tag this user')}))
    }
  },

  refresh: function(name) {
    var self = this
    $('a.author').filter(function() {
      return self.nameOf($(this)).toLowerCase() === name.toLowerCase()
    }).each(function() {
      var $author = $(this)
      $author.nextAll('.user-tag, .user-tag-button').first().remove()
      self.render($author, self.nameOf($author))
    })
  },

  edit: function(name, $near) {
    this.close()
    var tag = this.tags[name.toLowerCase()] || ['', '']
    var colors = r.config.user_tag_colors || {}
    var chosen = 'none'
    _.each(colors, function(bg, color) {
      if (bg && bg === tag[1]) {
        chosen = color
      }
    })
    var $box = $('<form class="user-tag-editor"></form>')
    var $input = $('<input type="text" maxlength="64">').val(tag[0])
      .attr({placeholder: r._('tag'), 'aria-label': r._('tag for %(user)s').format({user: name})})
    var $swatches = $('<div class="user-tag-colors"></div>')
    _.each(colors, function(bg, color) {
      $('<button type="button" class="user-tag-color"></button>')
        .toggleClass('selected', color === chosen)
        .css('background-color', bg || 'transparent')
        .attr({'aria-label': color, title: color})
        .data('color', color)
        .on('click', function() {
          chosen = color
          $swatches.children().removeClass('selected')
          $(this).addClass('selected')
        })
        .appendTo($swatches)
    })
    var $status = $('<span class="error"></span>')
    $box.append(
      $('<div class="user-tag-editor-title"></div>').text(
        r._('tag %(user)s').format({user: name})),
      $input, $swatches,
      $('<div class="user-tag-editor-buttons"></div>').append(
        $('<button type="submit" class="btn"></button>').text(r._('save')),
        $('<button type="button" class="user-tag-clear"></button>').text(r._('remove tag'))
          .on('click', _.bind(function() { this.save(name, '', 'none', $status) }, this)),
        $status))
    $box.on('submit', _.bind(function(e) {
      e.preventDefault()
      this.save(name, $input.val(), chosen, $status)
    }, this))
    $box.on('click keydown', function(e) {
      e.stopPropagation()
      if (e.type === 'keydown' && e.key === 'Escape') {
        r.enhancements.userTags.close()
      }
    })
    $box.appendTo(document.body)
    var offset = $near.offset()
    $box.css({top: offset.top + $near.outerHeight() + 4,
              left: Math.max(4, Math.min(offset.left, $(window).width() - $box.outerWidth() - 8))})
    $input.focus()
    $(document).one('click', _.bind(this.close, this))
  },

  save: function(name, tag, color, $status) {
    $.ajax({
      url: '/api/user_tag.json',
      type: 'POST',
      dataType: 'json',
      data: {user: name, tag: tag, color: color, uh: r.config.modhash},
    }).done(_.bind(function(res) {
      if (res && res.error) {
        $status.text(res.error)
        return
      }
      if (res && (res.tag || res.background)) {
        this.tags[name.toLowerCase()] = [res.tag, res.background]
      } else {
        delete this.tags[name.toLowerCase()]
      }
      this.close()
      this.refresh(name)
    }, this)).fail(function() {
      $status.text(r._('couldn\'t save the tag; try again'))
    })
  },

  close: function() {
    $('.user-tag-editor').remove()
  },
}

/* user info on hover */

r.enhancements.userInfo = {
  cache: {},

  init: function() {
    if (window.matchMedia && !window.matchMedia('(hover: hover)').matches) {
      return
    }
    var self = this
    $(document.body)
      .on('mouseenter', 'a.author', function() {
        var $author = $(this)
        self.leave = clearTimeout(self.leave)
        self.timer = setTimeout(function() { self.show($author) }, 500)
      })
      .on('mouseleave', 'a.author, .user-info-card', function() {
        clearTimeout(self.timer)
        self.leave = setTimeout(function() { self.hide() }, 300)
      })
      .on('mouseenter', '.user-info-card', function() {
        clearTimeout(self.leave)
      })
  },

  age: function(created) {
    var days = Math.max(0, Math.floor((Date.now() / 1000 - created) / 86400))
    if (days >= 365) {
      var years = Math.floor(days / 365)
      return r.P_('%(num)s year', '%(num)s years', years).format({num: years})
    }
    if (days >= 31) {
      var months = Math.floor(days / 30.4)
      return r.P_('%(num)s month', '%(num)s months', months).format({num: months})
    }
    return r.P_('%(num)s day', '%(num)s days', days).format({num: days})
  },

  show: function($author) {
    var name = r.enhancements.userTags.nameOf($author)
    var self = this
    var load = this.cache[name] ||
      (this.cache[name] = $.ajax({url: '/user/' + encodeURIComponent(name) + '/about.json',
                                  dataType: 'json'}))
    load.done(function(res) {
      if (!res || !res.data || !$.contains(document.documentElement, $author[0])) {
        return
      }
      self.render($author, res.data)
    })
  },

  render: function($author, d) {
    this.hide()
    var $card = $('<div class="user-info-card"></div>')
    var $title = $('<div class="user-info-name"></div>').append(
      $('<a></a>').attr('href', '/user/' + encodeURIComponent(d.name)).text(d.name))
    if (d.is_gold) {
      $title.append(' ', $('<span class="user-info-badge gold"></span>').text(r._('gold')))
    }
    if (d.is_mod) {
      $title.append(' ', $('<span class="user-info-badge"></span>').text(r._('moderator')))
    }
    var $facts = $('<dl></dl>').append(
      $('<dt></dt>').text(r._('member for')), $('<dd></dd>').text(this.age(d.created_utc)),
      $('<dt></dt>').text(r._('post karma')), $('<dd></dd>').text(d.link_karma),
      $('<dt></dt>').text(r._('comment karma')), $('<dd></dd>').text(d.comment_karma))
    var tags = r.enhancements.userTags
    var tag = (tags.tags || {})[d.name.toLowerCase()]
    var $tagRow = $('<div class="user-info-tag"></div>')
    if (tag && tag[0]) {
      $tagRow.append($('<span class="user-tag-label"></span>').text(tag[0])
        .css(tag[1] ? {backgroundColor: tag[1], color: '#fff', borderColor: tag[1]} : {}))
    }
    $tagRow.append(' ', $('<a href="#"></a>').text(tag ? r._('change tag') : r._('tag this user'))
      .on('click', function(e) {
        e.preventDefault()
        e.stopPropagation()
        tags.edit(d.name, $(this))
      }))
    var $links = $('<div class="user-info-links"></div>').append(
      $('<a></a>').attr('href', '/user/' + encodeURIComponent(d.name)).text(r._('profile')),
      ' | ',
      $('<a></a>').attr('href', '/message/compose/?to=' + encodeURIComponent(d.name))
        .text(r._('send a message')))
    $card.append($title, $facts, $tagRow, $links).appendTo(document.body)
    var offset = $author.offset()
    $card.css({top: offset.top + $author.outerHeight() + 4,
               left: Math.max(4, Math.min(offset.left, $(window).width() - $card.outerWidth() - 8))})
  },

  hide: function() {
    $('.user-info-card').remove()
  },
}

/* the parent comment on hover */

r.enhancements.parentHover = {
  init: function() {
    if (window.matchMedia && !window.matchMedia('(hover: hover)').matches) {
      return
    }
    var self = this
    $(document.body)
      .on('mouseenter', 'a[data-event-action="parent"]', function() {
        var $link = $(this)
        self.timer = setTimeout(function() { self.show($link) }, 250)
      })
      .on('mouseleave', 'a[data-event-action="parent"]', function() {
        clearTimeout(self.timer)
        $('.parent-comment-preview').remove()
      })
  },

  show: function($link) {
    var id = ($link.attr('href') || '').replace(/^.*#/, '')
    var $parent = $('#thing_t4_' + id).children('.entry')
    if (!id || !$parent.length) {
      return
    }
    // the tagline without what only makes sense in place (the collapse
    // toggle, the reply count, and scores whose shown one depends on how
    // you voted)
    var $tagline = $parent.find('.tagline').first().clone()
    $tagline.find('.user-tag-button, a.expand, .numchildren, .score').remove()
    var $preview = $('<div class="parent-comment-preview"></div>').append(
      $tagline, $parent.find('.usertext-body').first().clone())
    $preview.appendTo(document.body)
    var offset = $link.offset()
    var top = offset.top - $preview.outerHeight() - 6
    if (top < $(window).scrollTop()) {
      top = offset.top + $link.outerHeight() + 6
    }
    $preview.css({top: top,
                  left: Math.max(4, Math.min(offset.left, $(window).width() - $preview.outerWidth() - 8))})
  },
}

/* posts you've opened: new comment counts, and fading or hiding them */

r.enhancements.visits = {
  MAX: 2000,
  MAX_AGE: 60 * 86400,

  key: function() {
    return 'tippr.visits.' + r.config.user_id
  },

  // {fullname: [comment count when you last read them or null, time]}
  load: function() {
    try {
      return JSON.parse(window.localStorage.getItem(this.key()) || '{}') || {}
    } catch (e) {
      return {}
    }
  },

  store: function(visits) {
    var now = Date.now() / 1000
    var entries = _.pairs(visits).filter(_.bind(function(kv) {
      return now - kv[1][1] < this.MAX_AGE
    }, this))
    if (entries.length > this.MAX) {
      entries = _.sortBy(entries, function(kv) { return -kv[1][1] }).slice(0, this.MAX)
    }
    try {
      window.localStorage.setItem(this.key(), JSON.stringify(_.object(entries)))
    } catch (e) {}
  },

  count: function($thing) {
    var text = $thing.children('.entry').find('a.comments').first().text()
    var m = text.replace(/[,.  ]/g, '').match(/\d+/)
    return m ? parseInt(m[0], 10) : 0
  },

  init: function() {
    this.newCounts = r.config.new_comment_count
    this.visited = r.config.visited_posts
    var visits = this.load()
    var $link = $('.commentarea').length &&
      $('.sitetable.linklisting > .thing.link').first()

    if ($link && $link.length) {
      this.onCommentsPage($link, visits)
    } else {
      this.onListing(visits)
      $(document).on('new_things_inserted', _.bind(function() {
        this.onListing(this.load())
      }, this))
      // opening a post counts as visiting it (its comments aren't read yet)
      $(document.body).on('click', '#siteTable .thing.link a.title', _.bind(function(e) {
        var fullname = $(e.currentTarget).closest('.thing').data('fullname')
        var v = this.load()
        if (!v[fullname]) {
          v[fullname] = [null, Date.now() / 1000]
          this.store(v)
        }
      }, this))
    }
  },

  onCommentsPage: function($link, visits) {
    var fullname = $link.data('fullname')
    var before = visits[fullname]
    // highlight what's new since you last read them (gold members already
    // get this from the server)
    if (this.newCounts && before && before[0] !== null &&
        !$('.comment-visits-box').length) {
      var since = before[1] * 1000
      $('.commentarea .thing.comment').each(function() {
        var time = $(this).children('.entry').find('.tagline time').first().attr('datetime')
        if (time && Date.parse(time) > since) {
          $(this).addClass('new-comment')
        }
      })
    }
    visits[fullname] = [this.count($link), Date.now() / 1000]
    this.store(visits)
  },

  onListing: function(visits) {
    var self = this
    var hideHere = !/^\/(user|u)\/|\/saved\/?$/.test(location.pathname)
    $('#siteTable > .thing.link').each(function() {
      var $thing = $(this)
      var visit = visits[$thing.data('fullname')]
      if (!visit || $thing.data('visit-marked')) {
        return
      }
      $thing.data('visit-marked', true)
      if (self.visited === 'fade' || (self.visited === 'hide' && !hideHere)) {
        $thing.addClass('visited-post-faded')
      } else if (self.visited === 'hide') {
        $thing.addClass('visited-post-hidden')
      }
      if (self.newCounts && visit[0] !== null) {
        var fresh = self.count($thing) - visit[0]
        if (fresh > 0) {
          $thing.children('.entry').find('a.comments').first().after(
            $('<span class="new-comment-count"></span>').text(
              r.P_('(%(num)s new)', '(%(num)s new)', fresh).format({num: fresh})))
        }
      }
    })
  },
}

/* comment navigator */

r.enhancements.commentNavigator = {
  init: function() {
    if (!$('.commentarea .thing.comment').length) {
      return
    }
    var me = (r.config.logged || '').toLowerCase()
    this.categories = [
      ['top', r._('top-level comments'), function() {
        return $('.commentarea > .sitetable > .thing.comment')
      }],
      ['submitter', r._('the submitter\'s'), function() {
        return $('.commentarea .thing.comment').filter(function() {
          return $(this).children('.entry').find('.tagline a.author.submitter').length
        })
      }],
      ['mine', r._('yours'), function() {
        return $('.commentarea .thing.comment').filter(function() {
          return $(this).children('.entry').find('.tagline a.author').first()
            .text().toLowerCase() === me
        })
      }],
      ['new', r._('new'), function() {
        return $('.commentarea .thing.comment.new-comment')
      }],
      ['links', r._('with links'), function() {
        return $('.commentarea .thing.comment').filter(function() {
          return $(this).children('.entry').find('.usertext-body .md a[href]').length
        })
      }],
    ]
    this.index = -1
    var $select = $('<select class="comment-navigator-category"></select>')
      .attr('aria-label', r._('jump between'))
    _.each(this.categories, function(cat) {
      $select.append($('<option></option>').val(cat[0]).text(cat[1]))
    })
    this.$select = $select.on('change', _.bind(function() {
      this.index = -1
      this.update()
    }, this))
    this.$count = $('<span class="comment-navigator-count"></span>')
    this.$box = $('<div class="comment-navigator" role="navigation"></div>')
      .attr('aria-label', r._('comment navigator'))
      .append(
        $select,
        $('<button type="button" class="comment-navigator-prev">▲</button>')
          .attr('aria-label', r._('previous'))
          .on('click', _.bind(function() { this.move(-1) }, this)),
        $('<button type="button" class="comment-navigator-next">▼</button>')
          .attr('aria-label', r._('next'))
          .on('click', _.bind(function() { this.move(1) }, this)),
        this.$count)
      .appendTo(document.body)
    this.update()
  },

  current: function() {
    var key = this.$select.val()
    var cat = _.find(this.categories, function(c) { return c[0] === key })
    return cat[2]().filter(':visible')
  },

  update: function() {
    var $all = this.current()
    this.$count.text($all.length ?
      ((this.index >= 0 ? this.index + 1 : '–') + ' / ' + $all.length) : '0')
  },

  move: function(step) {
    var $all = this.current()
    if (!$all.length) {
      this.update()
      return
    }
    this.index = (this.index + step + $all.length) % $all.length
    if (this.index < 0) {
      this.index = $all.length - 1
    }
    r.enhancements.keyboardNav.select($all.eq(this.index), true)
    this.update()
  },
}

/* account switcher */

r.enhancements.accountSwitcher = {
  init: function() {
    var $users = $('#header-bottom-right .user, .mobile-drawer .user').first()
    if (!$users.length) {
      return
    }
    this.$toggle = $('<a href="#" class="account-switcher-toggle"></a>')
      .text(r._('switch account'))
      .attr('aria-haspopup', 'true')
      .on('click', _.bind(function(e) {
        e.preventDefault()
        e.stopPropagation()
        if ($('.account-switcher-menu').length) {
          this.close()
        } else {
          this.open()
        }
      }, this))
    $users.after($('<span class="separator">|</span>'), this.$toggle)
  },

  post: function(action, data) {
    return $.ajax({url: '/api/' + action + '.json', type: 'POST', dataType: 'json',
                   data: _.extend({uh: r.config.modhash}, data)})
  },

  open: function() {
    var self = this
    var $menu = $('<div class="account-switcher-menu" role="menu"></div>')
    var names = r.config.switch_accounts || []
    if (names.length) {
      var $list = $('<ul></ul>')
      _.each(names, function(name) {
        $('<li></li>').append(
          $('<a href="#" class="account-switcher-account" role="menuitem"></a>').text(name)
            .on('click', function(e) {
              e.preventDefault()
              self.post('switch_account', {name: name}).done(function(res) {
                if (res && res.ok) {
                  window.location.reload()
                } else {
                  self.$status.text((res && res.error) || r._('couldn\'t switch; try again'))
                }
              })
            }),
          $('<button type="button" class="account-switcher-forget"></button>')
            .text('×').attr({title: r._('forget this account'),
                                  'aria-label': r._('forget %(user)s').format({user: name})})
            .on('click', function(e) {
              e.stopPropagation()
              var $li = $(this).closest('li')
              self.post('switch_forget', {name: name}).done(function(res) {
                r.config.switch_accounts = (res && res.accounts) || []
                $li.remove()
              })
            }))
          .appendTo($list)
      })
      $menu.append($list)
    } else {
      $menu.append($('<p class="details"></p>').text(r._('no other accounts yet')))
    }
    var $form = $('<form class="account-switcher-add"></form>').append(
      $('<div class="account-switcher-title"></div>').text(r._('add an account')),
      $('<input type="text" name="user" autocomplete="username">')
        .attr({placeholder: r._('username'), 'aria-label': r._('username')}),
      $('<input type="password" name="passwd" autocomplete="current-password">')
        .attr({placeholder: r._('password'), 'aria-label': r._('password')}),
      $('<button type="submit" class="btn"></button>').text(r._('add and switch')))
    this.$status = $('<p class="error"></p>')
    $form.on('submit', function(e) {
      e.preventDefault()
      self.$status.text('')
      self.post('switch_add', {user: $form.find('[name=user]').val(),
                               passwd: $form.find('[name=passwd]').val(),
                               otp: $form.find('[name=otp]').val() || ''})
        .done(function(res) {
          if (res && res.ok) {
            window.location.reload()
          } else {
            if (res && res.need_otp && !$form.find('[name=otp]').length) {
              // that account wants its two-factor code at login
              $('<input type="text" name="otp" inputmode="numeric" autocomplete="one-time-code" maxlength="12">')
                .attr({placeholder: r._('two-factor code'), 'aria-label': r._('two-factor code')})
                .insertBefore($form.find('button[type=submit]'))
                .focus()
            }
            self.$status.text((res && res.error) || r._('couldn\'t add the account'))
          }
        })
        .fail(function() { self.$status.text(r._('couldn\'t add the account')) })
    })
    $menu.append($form, this.$status,
      $('<p class="details"></p>').text(
        r._('logging out forgets these accounts')))
      .on('click keydown', function(e) {
        e.stopPropagation()
        if (e.type === 'keydown' && e.key === 'Escape') {
          self.close()
        }
      })
      .appendTo(document.body)
    var offset = this.$toggle.offset()
    $menu.css({top: offset.top + this.$toggle.outerHeight() + 4,
               left: Math.max(4, Math.min(offset.left, $(window).width() - $menu.outerWidth() - 8))})
    this.$toggle.attr('aria-expanded', 'true')
    $(document).one('click', _.bind(this.close, this))
  },

  close: function() {
    $('.account-switcher-menu').remove()
    if (this.$toggle) {
      this.$toggle.attr('aria-expanded', 'false')
    }
  },
}

$(function() {
  if (r.config.account_switcher) {
    r.enhancements.accountSwitcher.init()
  }
  if (r.config.new_comment_count || (r.config.visited_posts &&
                                     r.config.visited_posts !== 'show')) {
    r.enhancements.visits.init()
  }
  if (r.config.comment_navigator) {
    r.enhancements.commentNavigator.init()
  }
  if (r.config.user_tagger || r.config.user_info_hover) {
    r.enhancements.userTags.init(r.config.user_tagger)
  }
  if (r.config.user_info_hover) {
    r.enhancements.userInfo.init()
  }
  if (r.config.parent_hover) {
    r.enhancements.parentHover.init()
  }
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

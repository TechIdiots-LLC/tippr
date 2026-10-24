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
 * A post's scales (r2.lib.scales): its "scales" link opens a panel under
 * the post where a member tips each scale toward one side (clicking the
 * side again takes the tip back). A scale's tally shows once they've
 * tipped it, and to the poster. Logged out, the link asks them to log in
 * (login.js).
 */
r.scales = {
  post: function(action, data) {
    return $.ajax({url: '/api/' + action + '.json', type: 'POST',
                   dataType: 'json',
                   data: _.extend({uh: r.config.modhash}, data)})
  },

  panelFor: function($thing) {
    return $thing.children('.entry').children('.scales-panel')
  },

  open: function($thing, $toggle) {
    var self = this
    var $panel = $('<div class="scales-panel" role="region">')
      .attr('aria-label', r._('scales'))
      .text(r._('loading…'))
    $thing.children('.entry').append($panel)
    $toggle.attr('aria-expanded', 'true')
    this.post('scales', {link_id: $thing.data('fullname')})
      .done(function(res) { self.render($thing, $panel, res) })
      .fail(function() { $panel.text(r._('an error occurred')) })
  },

  close: function($thing, $toggle) {
    this.panelFor($thing).remove()
    $toggle.attr('aria-expanded', 'false')
  },

  render: function($thing, $panel, res) {
    var self = this
    if (!res || !res.scales) {
      $panel.text(r._('an error occurred'))
      return
    }
    $panel.empty()
    var hidden = false
    // the scales behind "more scales": as they last opened or folded them,
    // or open when one of them has their tip
    var more = _.filter(res.scales, function(scale) { return scale.more })
    var moreOpen = $panel.data('more-open')
    if (moreOpen === undefined) {
      moreOpen = _.some(more, function(scale) { return scale.mine })
    }
    _.each(res.scales, function(scale) {
      var $row = $('<div class="scale">').attr('data-scale', scale.name)
        .toggleClass('scale-more', !!scale.more)
        .toggleClass('scale-folded', !!scale.more && !moreOpen)
      var $left = self.side(scale, -1, scale.left, res.can_tip)
      var $right = self.side(scale, 1, scale.right, res.can_tip)
      var $beam = $('<div class="scale-beam" aria-hidden="true">')
      var $count = $('<div class="scale-count">')
      if (scale.tally) {
        var total = scale.tally.left + scale.tally.right
        if (total) {
          $beam.addClass('scale-beam-tipped')
          $beam.append($('<span class="scale-fill">')
            .css('width', Math.round(scale.tally.left / total * 100) + '%'))
        }
        $count.text(total ? r.P_('%(num)s tip', '%(num)s tips', total)
                              .format({num: total}) +
                            ' · ' + scale.tally.left + ' / ' +
                            scale.tally.right
                          : r._('no tips yet'))
      } else {
        hidden = true
        $beam.addClass('scale-beam-hidden')
      }
      $row.append($left, $beam, $right, $count)
      $panel.append($row)
    })

    if (more.length) {
      $panel.append($('<a href="javascript: void 0;" class="scales-more">')
        .attr('aria-expanded', moreOpen ? 'true' : 'false')
        .text(moreOpen ? r._('fewer scales') : r._('more scales')))
    }

    var $note = $('<p class="scales-note">')
    if (res.is_poster) {
      $note.text(r._('How others have tipped your post.') + ' ')
    } else if (hidden && res.can_tip) {
      $note.text(r._('Tip a scale to see how others tipped it.') + ' ')
    }
    if (!res.is_poster && $thing.find('.reportbtn').length) {
      $note.append(document.createTextNode(r._('Breaks a rule?') + ' '),
                   $('<a href="javascript: void 0;" class="scales-report">')
                     .text(r._('report it')))
    }
    if ($note.contents().length) {
      $panel.append($note)
    }
  },

  side: function(scale, side, label, canTip) {
    var mine = scale.mine === side
    return $('<button type="button" class="scale-side">')
      .addClass(side < 0 ? 'scale-left' : 'scale-right')
      .toggleClass('scale-tipped', mine)
      .attr('aria-pressed', mine ? 'true' : 'false')
      .attr('data-side', side)
      .prop('disabled', !canTip)
      .text(label)
  },

  tip: function($thing, $button) {
    var self = this
    var $row = $button.closest('.scale')
    var side = parseInt($button.attr('data-side'), 10)
    if ($button.hasClass('scale-tipped')) {
      side = 0
    }
    $row.find('.scale-side').prop('disabled', true)
    this.post('tip_scale', {link_id: $thing.data('fullname'),
                            scale: $row.attr('data-scale'), side: side})
      .done(function(res) {
        self.render($thing, self.panelFor($thing), res)
      })
      .fail(function() {
        $row.find('.scale-side').prop('disabled', false)
      })
  }
}

$(function() {
  $(document).on('click', '.scales-toggle', function(e) {
    e.preventDefault()
    if (!r.config.logged) {
      return  // login.js asks them to log in
    }
    var $thing = $(this).thing()
    if (r.scales.panelFor($thing).length) {
      r.scales.close($thing, $(this))
    } else {
      r.scales.open($thing, $(this))
    }
  })

  $(document).on('click', '.scales-panel .scale-side', function(e) {
    e.preventDefault()
    r.scales.tip($(this).thing(), $(this))
  })

  $(document).on('click', '.scales-panel .scales-more', function(e) {
    e.preventDefault()
    var $panel = $(this).closest('.scales-panel')
    var open = $(this).attr('aria-expanded') !== 'true'
    $panel.data('more-open', open)
    $panel.find('.scale-more').toggleClass('scale-folded', !open)
    $(this).attr('aria-expanded', open ? 'true' : 'false')
      .text(open ? r._('fewer scales') : r._('more scales'))
  })

  $(document).on('click', '.scales-panel .scales-report', function(e) {
    e.preventDefault()
    $(this).thing().find('.reportbtn').first().click()
  })
})

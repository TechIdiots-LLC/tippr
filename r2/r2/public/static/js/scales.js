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
 * tipped it, to the poster, and to the vault's moderators; under
 * bar_min tips it's listed rather than drawn. "see the results" shows them
 * all, giving up tipping that post. Logged out, the link asks
 * them to log in (login.js).
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
    r.ui.closeThingPanels($thing, 'scales')
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
    _.each(res.scales, function(scale) {
      var $row = $('<div class="scale">').attr('data-scale', scale.name)
      var $left = self.side(scale, -1, scale.left, res.can_tip,
                            scale.tally && scale.tally.left)
      var $right = self.side(scale, 1, scale.right, res.can_tip,
                             scale.tally && scale.tally.right)
      var $beam = $('<div class="scale-beam" aria-hidden="true">')
      var $count = $('<div class="scale-count">')
      if (scale.tally) {
        var total = scale.tally.left + scale.tally.right
        // a bar only once there are enough tips to mean something: one
        // person's tip would fill it with one colour
        if (total >= (res.bar_min || 1)) {
          $beam.addClass('scale-beam-tipped')
          $beam.append($('<span class="scale-fill">')
            .css('width', Math.round(scale.tally.left / total * 100) + '%'))
        }
        $count.text(self.describe(scale, total, res.bar_min || 1))
      } else {
        hidden = true
        $beam.addClass('scale-beam-hidden')
      }
      $row.append($left, $beam, $right, $count)
      $panel.append($row)
    })

    var $note = $('<p class="scales-note">')
    if (res.is_poster) {
      $note.text(r._('How others have tipped your post.') + ' ')
    } else if (res.sees_all) {
      $note.text(r._('As a moderator, you see every scale’s tips without tipping.') + ' ')
    } else if (res.seen) {
      $note.text(r._('You saw the results, so you can’t tip this post’s scales.') + ' ')
    } else if (hidden && res.can_tip) {
      // or every tally now, giving up tipping this post (see)
      $note.append(document.createTextNode(
                     r._('Tip a scale to see how others tipped it, or') + ' '),
                   $('<a href="javascript: void 0;" class="scales-see">')
                     .text(r._('see the results')),
                   document.createTextNode(' ' +
                     r._('(you can’t tip after).') + ' '))
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

  // a side's button, with its count beside the label where the tally shows
  side: function(scale, side, label, canTip, count) {
    var mine = scale.mine === side
    var $button = $('<button type="button" class="scale-side">')
      .addClass(side < 0 ? 'scale-left' : 'scale-right')
      .toggleClass('scale-tipped', mine)
      .attr('aria-pressed', mine ? 'true' : 'false')
      .attr('data-side', side)
      .prop('disabled', !canTip)
      .append($('<span class="scale-side-label">').text(label))
    if (typeof count === 'number') {
      $button.append(' ', $('<span class="scale-side-count">').text(count))
    }
    return $button
  },

  // the line under a scale: "75% human-made · 4 tips", or with fewer than
  // barMin tips, who tipped which way ("1 tip so far: human-made")
  describe: function(scale, total, barMin) {
    var left = scale.tally.left, right = scale.tally.right
    if (!total) {
      return r._('no tips yet')
    }
    var tips = r.P_('%(num)s tip', '%(num)s tips', total).format({num: total})
    if (total < barMin) {
      var parts = []
      if (left) {
        parts.push(left === total ? scale.left
                   : r._('%(num)s %(side)s').format({num: left, side: scale.left}))
      }
      if (right) {
        parts.push(right === total ? scale.right
                   : r._('%(num)s %(side)s').format({num: right, side: scale.right}))
      }
      return r.P_('%(num)s tip so far', '%(num)s tips so far', total)
               .format({num: total}) + ': ' + parts.join(', ')
    }
    if (left === right) {
      return r._('evenly split') + ' · ' + tips
    }
    var winner = left > right ? scale.left : scale.right
    var percent = Math.round(Math.max(left, right) / total * 100)
    return r._('%(percent)s %(side)s').format({percent: percent + '%',
                                               side: winner}) + ' · ' + tips
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
  },

  // every tally now, after asking: it ends their tipping on this post
  see: function($thing) {
    var self = this
    if (!window.confirm(r._('See how everyone tipped this post? You won’t be able to tip its scales or change your tips afterwards.'))) {
      return
    }
    this.post('see_scales', {link_id: $thing.data('fullname')})
      .done(function(res) {
        self.render($thing, self.panelFor($thing), res)
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

  $(document).on('click', '.scales-panel .scales-see', function(e) {
    e.preventDefault()
    r.scales.see($(this).thing())
  })

  $(document).on('click', '.scales-panel .scales-report', function(e) {
    e.preventDefault()
    $(this).thing().find('.reportbtn').first().click()
  })
})

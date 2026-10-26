!function(r) {
  'use strict';

  /*
    Sites shared to by opening their "compose a post" page with the link
    filled in. None of these need an app ID or API key. params(link, title)
    returns the query string.
   */
  var WEB_INTENTS = {
    bluesky: {
      name: 'Bluesky',
      url: 'https://bsky.app/intent/compose',
      params: function(link, title) { return { text: title + ' ' + link }; },
    },
    threads: {
      name: 'Threads',
      url: 'https://www.threads.com/intent/post',
      params: function(link, title) { return { text: title + ' ' + link }; },
    },
    facebook: {
      name: 'Facebook',
      url: 'https://www.facebook.com/sharer/sharer.php',
      params: function(link, title) { return { u: link }; },
    },
    x: {
      name: 'X',
      url: 'https://x.com/intent/post',
      params: function(link, title) { return { text: title, url: link }; },
    },
    linkedin: {
      name: 'LinkedIn',
      url: 'https://www.linkedin.com/sharing/share-offsite/',
      params: function(link, title) { return { url: link }; },
    },
    tumblr: {
      name: 'Tumblr',
      url: 'https://www.tumblr.com/widgets/share/tool',
      params: function(link, title) {
        return { canonicalUrl: link, posttype: 'link', title: title };
      },
    },
  };

  var MASTODON_INSTANCE_KEY = 'post-sharing.mastodon-instance';

  /*
    Renders a single sharing option and it's tooltip
   */
  var shareOptionTemplate = _.template(
    '<div class="post-sharing-option post-sharing-option-<%- name %>" ' +
                 'data-post-sharing-option="<%- name %>">' +
      '<div class="c-tooltip" role="tooltip">' +
        '<div class="tooltip-arrow bottom"></div>' +
        '<div class="tooltip-inner"><%- tooltip %></div>' +
      '</div>' +
    '</div>'
  );

  /*
    Render's the widget used by $.fn.stateify to display feedback to the user,
    e.g. error messages.
   */
  var feedbackTemplate = _.template(
    '<div class="c-form-control-feedback-wrapper" ref="<%- ref %>">' +
      '<span class="c-form-control-feedback c-form-control-feedback-throbber"></span>' +
      '<span class="c-form-control-feedback c-form-control-feedback-error"></span>' +
      '<span class="c-form-control-feedback c-form-control-feedback-success"></span>' +
    '</div>'
  );

  var postSharingTemplate = _.template(
    '<a href="javascript: void 0;" class="c-close c-hide-text">' +
      _.escape(r._('close this window')) +
    '</a>' +
    '<div class="post-sharing-main post-sharing-form" ref="$mainForm">' +
      '<% if (options) { %>' +
        '<div class="c-form-group">' +
          '<div class="post-sharing-label">' +
            _.escape(r._('Share with:')) +
          '</div>' +
          '<div class="post-sharing-options">' +
            '<% options.forEach(function(option) { %>' +
              '<%= option %>' +
            '<% }) %>' +
          '</div>' +
        '</div>' +
      '<% } %>' +
      '<% if (link) { %>' +
        '<div class="c-form-group">' +
          '<div class="post-sharing-label">' +
            _.escape(r._('Link:')) +
          '</div>' +
          '<input class="post-sharing-link-input c-form-control" ' +
                 'ref="$postSharingLinkInput" ' +
                 'name="link" ' +
                 'type="text" ' +
                 'readonly ' +
                 'value="<%- link %>">' +
          '<button class="post-sharing-copy c-btn c-btn-primary" ' +
                  'ref="$copyButton" type="button">' +
            _.escape(r._('copy')) +
          '</button>' +
        '</div>' +
      '<% } %> ' +
    '</div>' +
    '<div class="post-sharing-email-form post-sharing-form" ref="$emailForm">' +
      '<p class="post-sharing-label">' +
        '<span ref="$emailFormEmailLabel">' + _.escape(r._('Share via email as %(username)s').format({ username: r.config.logged })) + '</span>' +
        '<span ref="$emailFormPMLabel">' + _.escape(r._('Share via private message on tippr as %(username)s').format({ username: r.config.logged })) + '</span>' +
      '</p>' +
      '<div class="c-form-group">' +
        '<input class="post-sharing-recipient-input c-form-control" ' +
               'ref="$shareTo" ' +
               'name="recipient" type="text" ' +
               'placeholder="name@example.com, name@example.com" ' +
               'data-placeholder-email="name@example.com, name@example.com" ' +
               'data-placeholder-tippr-pm="username">' +
        feedbackTemplate({ ref: '$shareToFeedback' }) +
      '</div>' +
      '<div class="c-form-group">' +
        '<textarea class="post-sharing-message-input c-form-control" ' +
                  'ref="$shareMessage" ' +
                  'name="message" ' +
                  'placeholder="' + _.escape(r._('add optional message')) + '"></textarea>' +
        feedbackTemplate({ ref: '$messageFeedback' }) +
      '</div>' +
      '<div class="c-form-group">' +
        '<div class="post-sharing-buttons">' +
          '<button class="post-sharing-submit c-btn c-btn-primary c-pull-right">' +
            _.escape(r._('send')) +
          '</button>' +
          '<button class="post-sharing-cancel c-btn c-btn-secondary c-pull-right">' +
            _.escape(r._('cancel')) +
          '</button>' +
        '</div>' +
        feedbackTemplate({ ref: '$requestStateFeedback' }) +
        '<div class="post-sharing-shareplane" ref="$shareplane">' +
          _.escape(r._('sent!')) +
        '</div>' +
      '</div>' +
    '</div>'
  );

  var PostSharingState = Backbone.Model.extend({
    defaults: function() {
      return {
        errors: [],
        options: null,
        requestState: 'UNSENT',
        selectedOption: null,
        link: null,
      };
    },
  });


  r.ui.PostSharing = Backbone.View.extend({
    animationSpeed: 200,

    _template: postSharingTemplate,

    _model: PostSharingState,

    events: {
      'click .post-sharing-link-input': 'selectLinkInputText',
      'copy .post-sharing-link-input': 'fireCopyEvent',
      'click .post-sharing-option': 'setPostSharingOption',
      'click .post-sharing-copy': 'copyLink',
      'click .post-sharing-cancel': 'clearPostSharingOption',
      'click .post-sharing-submit': 'shareToEmail',
      'click .c-close': 'close',
    },

    initialize: function() {
      var $thing = this.options.$thing;

      var fullname = $thing.data('fullname');
      var id = fullname.split('_')[1];
      var title = $thing.find('.entry a.title').text();
      var link = $thing.find('.entry a.comments').attr('href');

      this.thingData = {
        fullname: fullname,
        title: title,
        link: link,
      };

      var props = this.options.props || {};
      props.link = this.getShareLink('link');
      this.state = new this._model(props);
      this.listenTo(this.state, 'change', this.render);

      this.initialRender();
    },

    initialRender: function() {
      var renderVars = this.state.toJSON();

      if (renderVars.options) {
        renderVars.options = renderVars.options.map(shareOptionTemplate);
      }

      this.$el.html(this._template(renderVars));

      this.refs = {};
      var $refs = this.$el.find('[ref]');
      $refs.toArray().forEach(function(ref) {
        var $ref = $(ref);
        var refName = $ref.attr('ref');
        this.refs[refName] = $ref;
      }, this);

      this.refs.$mainForm.css('display', 'block');
      this.render();
    },

    show: function() {
      this.$el.slideDown(this.animationSpeed, 'swing', function() {
        this.trigger('show', this);
        this.selectLinkInputText();
      }.bind(this));
    },

    hide: function() {
      this.$el.slideUp(this.animationSpeed, 'swing', function() {
        this.trigger('hide');
      }.bind(this));
    },

    unmount: function() {
      this.remove();
      this.trigger('unmount', this);
    },

    close: function() {
      this.once('hide', this.unmount.bind(this));
      this.hide();
      this.trigger('close');
    },

    setPostSharingOption: function(e) {
      var $el = $(e.target).closest('.post-sharing-option');
      var option = $el.data('post-sharing-option');

      switch (option) {
        case 'email':
          // fall through
        case 'tippr-pm':
          return this.state.set({
            selectedOption: option,
          });

        case 'native':
          return this.shareToNative();

        case 'mastodon':
          return this.shareToMastodon();

        default:
          if (WEB_INTENTS[option]) {
            return this.shareToWebIntent(option);
          }
          this.close();
      }
    },

    getShareLink: function(refSource) {
      var refParams = {
        ref: 'share',
        ref_source: refSource,
      };

      return r.utils.replaceUrlParams(this.thingData.link, refParams);
    },

    shareToWebIntent: function(option) {
      var intent = WEB_INTENTS[option];
      var shareUrl = r.utils.replaceUrlParams(
        intent.url, intent.params(this.getShareLink(option), this.thingData.title));

      this.openWebIntent(shareUrl, option);
    },

    /*
      Mastodon has no central site to share through: each person is on their
      own server. Ask for it once and remember it in this browser.
     */
    shareToMastodon: function() {
      var instance = null;
      try {
        instance = window.localStorage.getItem(MASTODON_INSTANCE_KEY);
      } catch (e) {}

      instance = window.prompt(
        r._('Your Mastodon server (for example mastodon.social):'),
        instance || '');
      if (!instance) {
        return;
      }
      instance = instance.trim().replace(/^https?:\/\//i, '').replace(/\/.*$/, '');
      if (!/^[a-z0-9.-]+\.[a-z]{2,}(:\d+)?$/i.test(instance)) {
        window.alert(r._('That doesn\'t look like a server name.'));
        return;
      }
      try {
        window.localStorage.setItem(MASTODON_INSTANCE_KEY, instance);
      } catch (e) {}

      var text = this.thingData.title + ' ' + this.getShareLink('mastodon');
      var shareUrl = r.utils.replaceUrlParams(
        'https://' + instance + '/share', { text: text });
      this.openWebIntent(shareUrl, 'mastodon');
    },

    /* The device's own share sheet (phones, and some desktop browsers). */
    shareToNative: function() {
      var shareData = {
        title: this.thingData.title,
        url: this.getShareLink('native'),
      };
      navigator.share(shareData).then(function() {
        this.trigger('web-intent', 'native');
      }.bind(this), function() {
        // cancelled, or not allowed: nothing to do
      });
    },

    copyLink: function() {
      var link = this.refs.$postSharingLinkInput.val();
      var $button = this.refs.$copyButton;
      var done = function() {
        $button.text(r._('copied!'));
        setTimeout(function() { $button.text(r._('copy')); }, 1500);
        this.trigger('link', 'copy');
      }.bind(this);

      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(link).then(done, function() {
          this.selectLinkInputText();
        }.bind(this));
      } else {
        this.selectLinkInputText();
        try {
          if (document.execCommand('copy')) {
            done();
          }
        } catch (e) {}
      }
    },

    openWebIntent: function(shareUrl, windowTitle) {
      var windowWidth = window.innerWidth;
      var windowHeight = window.innerHeight;
      var popupWidth = 550;
      var popupHeight = 420;

      var windowFeatures = {
        height: popupHeight,
        width: popupWidth,
        left: windowWidth / 2 - popupWidth / 2,
        top: windowHeight / 2 - popupHeight / 2,
      };

      var windowFeaturesString = Object.keys(windowFeatures).map(function(key) {
        return key + '=' + windowFeatures[key];
      }).join(',');

      window.open(shareUrl, windowTitle, windowFeaturesString);
      this.trigger('web-intent', windowTitle);
    },

    shareToEmail: function() {
      this.state.set({
        requestState: 'LOADING',
      });

      $.request('share', {
          share_from: '',
          replyto: '',
          share_to: this.refs.$shareTo.val(),
          message: this.refs.$shareMessage.val(),
          parent: this.thingData.fullname,
          api_type: 'json',
        }, function(res) {
          if (this.state.get('requestState') !== 'LOADING') {
            return;
          }

          var jsonResponse = res.json;

          if (!jsonResponse) {
            throw 'share api response error';
          } else if (!jsonResponse.errors.length) {
            this.state.set({
              errors: [],
              requestState: 'DONE',
            });

            setTimeout(function() {
              this.close();
            }.bind(this), 1500);
          } else {
            this.state.set({
              errors: jsonResponse.errors,
              requestState: 'DONE',
            });
          }
        }.bind(this));
    },

    clearPostSharingOption: function(e) {
      this.state.set({
        requestState: 'UNSENT',
        selectedOption: null,
      });
    },

    selectLinkInputText: function() {
      this.refs.$postSharingLinkInput.focus().select();
    },

    fireCopyEvent: function() {
      this.trigger('link', 'copy');
    },

    getFeedbackRef: function(key) {
      switch (key) {
        case "BAD_EMAIL":
        case "BAD_EMAILS":
        case "NO_EMAILS":
          return this.refs.$shareToFeedback;

        case "TOO_LONG":
          return this.refs.$messageFeedback;

        default:
          return this.refs.$requestStateFeedback;
      }
    },

    onOpenEmailForm: function() {
        this.refs.$shareTo.focus();
    },

    render: function() {
      var requestState = this.state.get('requestState');
      var errors = this.state.get('errors');
      var changed = this.state.changed;
      var selectedOption = this.state.get('selectedOption');

      if ('selectedOption' in changed) {
          this.refs.$emailFormEmailLabel.toggle(selectedOption === 'email');
          this.refs.$emailFormPMLabel.toggle(selectedOption === 'tippr-pm');

          this.refs.$shareTo.attr('placeholder', this.refs.$shareTo.data('placeholder-' + selectedOption));

        if (selectedOption === 'email' || selectedOption === 'tippr-pm') {
          this.refs.$mainForm.slideUp('fast');
          this.refs.$emailForm.slideDown('fast', this.onOpenEmailForm.bind(this));
        } else {
          this.refs.$mainForm.slideDown('fast');
          this.refs.$emailForm.slideUp('fast');
        }
      }


      if (selectedOption === 'email' || selectedOption === 'tippr-pm') {
        this.refs.$shareToFeedback.stateify('clear');
        this.refs.$messageFeedback.stateify('clear');
        this.refs.$requestStateFeedback.stateify('clear');

        if (errors.length) {
          errors.forEach(function(error) {
            var key = error[0];
            var message = error[1];
            var $ref = this.getFeedbackRef(key)

            $ref.stateify('set', 'error', message);
          }, this);
        }

        if (requestState === 'LOADING') {
          this.refs.$requestStateFeedback.stateify('set', 'loading');
        } else if (requestState === 'DONE' && !errors.length) {
          this.refs.$requestStateFeedback.stateify('set', 'success');
          this.refs.$emailForm.addClass('shared');
        }
      }
    },
  });


  $(function() {
    $('body').on('click', '.post-sharing-button', function(e) {
      e.preventDefault();

      var $shareButton = $(e.target);
      var $parentThing = $shareButton.closest('.thing');
      var thingId = $parentThing.thing_id();

      if (r.ui.activeShareMenu && r.ui.activeShareMenu.$el.is(':visible')) {
        var isSameLink = r.ui.activeShareMenu.options.$thing[0] === $parentThing[0];
        r.ui.activeShareMenu.close();

        if (isSameLink) {
          return;
        }
      }

      // the only panel open under it (scales, report)
      r.ui.closeThingPanels($parentThing, 'share');

      var shareTo = function(name, label) {
        return {
          name: name,
          tooltip: r._('Share to %(name)s').format({name: label}),
        };
      };

      var shareOptions = [];

      // the device's share sheet first where there is one (mostly phones):
      // it reaches every app the person has installed
      if (navigator.share) {
        shareOptions.push({
          name: 'native',
          tooltip: r._('More ways to share'),
        });
      }

      shareOptions.push(
        shareTo('bluesky', WEB_INTENTS.bluesky.name),
        shareTo('mastodon', 'Mastodon'),
        shareTo('threads', WEB_INTENTS.threads.name),
        shareTo('facebook', WEB_INTENTS.facebook.name),
        shareTo('x', WEB_INTENTS.x.name),
        shareTo('linkedin', WEB_INTENTS.linkedin.name),
        shareTo('tumblr', WEB_INTENTS.tumblr.name)
      );

      if (r.config.logged && !r.config.user_in_timeout
          && r.config.email_verified) {
        shareOptions.push({
          name: 'email',
          tooltip: r._('Email to a Friend'),
        });
      }

      if (r.config.logged && !r.config.user_in_timeout) {
        shareOptions.push({
          name: 'tippr-pm',
          tooltip: r._('Private Message a Friend on Tippr'),
        });
      }

      var postSharing = new r.ui.PostSharing({
        className: 'post-sharing',
        $thing: $parentThing,
        props: {
          options: shareOptions,
        }
      });

      $parentThing.find('.entry .buttons').after(postSharing.el);

      r.ui.activeShareMenu = postSharing;

      postSharing.on('show', function() {
        r.analytics.fireGAEvent('post-sharing', 'open', thingId);
      });

      postSharing.on('unmount', function() {
        if (r.ui.activeShareMenu === postSharing) {
          r.ui.activeShareMenu = null;
        }
      });

      postSharing.on('close', function() {
        var eventName = postSharing.state.get('selectedOption') ? 'close' : 'cancel';
        r.analytics.fireGAEvent('post-sharing', eventName, thingId);
      });

      postSharing.on('web-intent', function(refSource) {
        r.analytics.fireGAEvent('post-sharing', 'share-to-' + refSource, thingId);
      });

      postSharing.on('link', function(action) {
        r.analytics.fireGAEvent('post-sharing', 'link-' + action, thingId);
      });

      postSharing.show();
    });
  });
}(r);

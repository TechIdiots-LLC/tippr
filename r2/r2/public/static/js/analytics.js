r.analytics = {
  init: function() {
    // these guys are relying on the custom 'onshow' from jquery.tippr.js
    $(document).delegate(
      '.organic-listing .promotedlink.promoted',
      'onshow',
      _.bind(function(ev) {
        this.fireTrackingPixel(ev.target);
      }, this)
    );

    $('.promotedlink.promoted:visible').trigger('onshow');

    // dont track sponsor's activity
    r.analytics.addEventPredicate('ads', function() {
      return !r.config.is_sponsor;
    });

    // virtual page tracking for ads funnel
    if (r.config.ads_virtual_page) {
      r.analytics.fireFunnelEvent('ads', r.config.ads_virtual_page);
    }

    r.analytics.contextData = {
      dnt: window.DO_NOT_TRACK,
      language: document.getElementsByTagName('html')[0].getAttribute('lang'),
      link_id: r.config.cur_link ? r.utils.fullnameToId(r.config.cur_link) : null,
      loid: null,
      loid_created: null,
      referrer_url: document.referrer || '',
      referrer_domain: null,
      vault_id: r.config.cur_site ? r.utils.fullnameToId(r.config.cur_site) : null,
      vault_name: r.config.post_site || null,
      user_id: null,
      user_name: null,
      user_in_beta: r.config.pref_beta,
    };

    if (r.config.user_id) {
      r.analytics.contextData.user_id = r.config.user_id;
      r.analytics.contextData.user_name = r.config.logged;
    } else {
      var tracker = new redditlib.Tracker();
      var loggedOutData = tracker.getTrackingData();
      if (loggedOutData && loggedOutData.loid) {
        r.analytics.contextData.loid = loggedOutData.loid;
        if (loggedOutData.loidcreated) {
          r.analytics.contextData.loid_created = decodeURIComponent(loggedOutData.loidcreated);
        }
      }
    }

    if (document.referrer) {
      var referrerDomain = document.referrer.match(/\/\/([^\/]+)/);
      if (referrerDomain && referrerDomain.length > 1) {
        r.analytics.contextData.referrer_domain = referrerDomain[1];
      }
    }

    if ($('body').hasClass('comments-page')) {
      r.analytics.contextData.page_type = 'comments';
    } else if ($('body').hasClass('listing-page')) {
      r.analytics.contextData.page_type = 'listing';

      if (r.config.cur_listing) {
        r.analytics.contextData.listing_name = r.config.cur_listing;
      }
    }

    if (r.config.feature_screenview_events) {
      r.analytics.screenviewEvent();
    }

    if (r.config.expando_preference) {
      r.analytics.contextData.expando_preference = r.config.expando_preference;
    }

    if (r.config.pref_no_profanity) {
      r.analytics.contextData.media_preference_hide_nsfw = r.config.pref_no_profanity
    }

    r.analytics.firePageTrackingPixel(r.analytics.stripAnalyticsParams);

    // a search (what was searched for isn't sent)
    if ($('body').hasClass('search-page')) {
      r.analytics.sendGA4Event('search', {});
    }

    r.hooks.get('analytics').call();
  },

  _eventPredicates: {},

  addEventPredicate: function(category, predicate) {
    var predicates = this._eventPredicates[category] || [];

    predicates.push(predicate);

    this._eventPredicates[category] = predicates;
  },

  shouldFireEvent: function(category/*, arguments*/) {
    var args = _.rest(arguments);

    return !this._eventPredicates[category] ||
        this._eventPredicates[category].every(function(fn) {
          return fn.apply(this, args);
        });
  },

  // Google Analytics 4: templates/utils.html defines window.gtag only for
  // visitors it may track (they allowed it, or the site doesn't ask, and
  // their browser doesn't ask not to be tracked); otherwise nothing is
  // sent. Events take GA4's recommended names where one fits, so its
  // reports understand them. No usernames, titles or ids go to Google.
  _GA4_EVENTS: {
    'login-form/submit': ['login', {method: 'password'}],
    'register-form/submit': ['sign_up', {method: 'password'}],
    'newsletter-form/submit': ['newsletter_signup', {}],
  },

  sendGA4Event: function(name, params, callback) {
    callback = callback || function() {};
    if (typeof window.gtag !== 'function') {
      callback();
      return;
    }
    // GA may be slow or blocked: go on regardless after a moment
    var done = _.once(callback);
    window.gtag('event', name, _.extend({}, params, {
      event_callback: done,
      event_timeout: 500,
    }));
    setTimeout(done, 600);
  },

  _eventName: function(category, action) {
    // GA4: letters, digits and underscores, starting with a letter, <= 40
    return (category + '_' + action).toLowerCase()
      .replace(/[^a-z0-9_]+/g, '_').replace(/^[^a-z]+/, '').slice(0, 40);
  },

  fireFunnelEvent: function(category, action, options, callback) {
    options = options || {};
    callback = callback || function() {};

    if (!this.shouldFireEvent.apply(this, arguments)) {
      callback();
      return;
    }

    var name = (category === 'gold' && action === 'checkout') ?
      'begin_checkout' : this._eventName(category, action);
    var params = {};
    if (options.value) {
      params.value = options.value;
      params.currency = 'USD';
    }
    this.sendGA4Event(name, params, callback);
  },

  fireGAEvent: function(category, action, opt_label, opt_value, opt_noninteraction, callback) {
    callback = callback || function() {};

    if (!this.shouldFireEvent.apply(this, arguments)) {
      callback();
      return;
    }

    var known = this._GA4_EVENTS[category + '/' + action];
    var name, params;
    if (known) {
      name = known[0];
      params = _.clone(known[1]);
    } else if (category === 'post-sharing' && action.indexOf('share-to-') === 0) {
      name = 'share';
      params = {method: action.slice('share-to-'.length), content_type: 'post'};
    } else if (category === 'post-sharing' && action.indexOf('link-') === 0) {
      name = 'share';
      params = {method: 'link', content_type: 'post'};
    } else {
      // (the label is left out: reddit's code put ids in it)
      name = this._eventName(category, action);
      params = {};
    }
    if (opt_value) {
      params.value = opt_value;
    }
    if (opt_noninteraction) {
      params.non_interaction = true;
    }
    this.sendGA4Event(name, params, callback);
  },

  // community actions, from $.request (jquery.tippr.js) once they've
  // worked: (request parameters) -> [GA4 event, params], or null to skip
  _ACTIONS: {
    vote: function(params) {
      if (params.dir == 1) {
        return ['vote', {direction: 'up'}];
      } else if (params.dir == -1) {
        return ['vote', {direction: 'down'}];
      }
      return null;
    },
    comment: function() {
      return ['post_comment', {}];
    },
    submit: function(params) {
      return ['submit_post', {post_type: params.kind === 'self' ? 'text' : 'link'}];
    },
    subscribe: function(params) {
      return params.action === 'sub' ? ['join_group', {group_id: params.vault}] : null;
    },
  },

  requestDone: function(action, params, res) {
    var make = this._ACTIONS[action];
    if (!make) {
      return;
    }
    var errors = res && res.json && res.json.errors;
    if (errors && errors.length) {
      return;
    }
    var event = make(params || {});
    if (event) {
      this.sendGA4Event(event[0], event[1]);
    }
  },

  fireTrackingPixel: function(el) {
    var $el = $(el);
    var onCommentsPage = $('body').hasClass('comments-page');

    if ($el.data('trackerFired') || onCommentsPage) {
      return;
    }

    var pixel = new Image();
    var impPixel = $el.data('impPixel');

    if (impPixel) {
      pixel.src = impPixel;
    }

    if (!adBlockIsEnabled) {
      var thirdPartyTrackingUrl = $el.data('thirdPartyTrackingUrl');
      if (thirdPartyTrackingUrl) {
        var thirdPartyTrackingImage = new Image();
        thirdPartyTrackingImage.src = thirdPartyTrackingUrl;
      }

      var thirdPartyTrackingUrl2 = $el.data('thirdPartyTrackingTwoUrl');
      if (thirdPartyTrackingUrl2) {
        var thirdPartyTrackingImage2 = new Image();
        thirdPartyTrackingImage2.src = thirdPartyTrackingUrl2;
      }
    }

    var adServerPixel = new Image();
    var adServerImpPixel = $el.data('adserverImpPixel');
    var adServerClickUrl = $el.data('adserverClickUrl');

    if (adServerImpPixel) {
      adServerPixel.src = adServerImpPixel;
    }

    $el.data('trackerFired', true);
  },

  fireUITrackingPixel: function(action, srname, extraParams) {
    var pixel = new Image();
    pixel.src = r.config.uitracker_url + '?' + $.param(
      _.extend(
        {
          act: action,
          vault: srname,
          r: Math.round(Math.random() * 2147483647), // cachebuster
        },
        r.analytics.breadcrumbs.toParams(),
        extraParams
      )
    );
  },

  firePageTrackingPixel: function(callback) {
    var url = r.config.tracker_url;
    if (!url) {
      return;
    }
    var params = {
      dnt: this.contextData.dnt,
    };

    if (this.contextData.loid) {
      params.loid = this.contextData.loid;
    }
    if (this.contextData.loid_created) {
      params.loidcreated = decodeURIComponent(this.contextData.loid_created);
    }

    var querystring = [
      'r=' + Math.random(),
    ];

    if (this.contextData.referrer_domain) {
      querystring.push(
        'referrer_domain=' + encodeURIComponent(this.contextData.referrer_domain)
      );
    }

    for(var p in params) {
      if (params.hasOwnProperty(p)) {
        querystring.push(
          encodeURIComponent(p) + '=' + encodeURIComponent(params[p])
        );
      }
    }

    var pixel = new Image();
    pixel.onload = pixel.onerror = callback;
    pixel.src = url + '&' + querystring.join('&');
  },

  // If we passed along referring tags to this page, after it's loaded, remove them from the URL so that 
  // the user can have a clean, copy-pastable URL. This will also help avoid erroneous analytics if they paste the URL
  // in an email or something.
  stripAnalyticsParams: function() {
    var hasReplaceState = !!(window.history && window.history.replaceState);
    var params = $.url().param();
    var stripParams = ['ref', 'ref_source', 'ref_campaign'];
    // strip utm tags as well
    _.keys(params).forEach(function(paramKey){
      if (paramKey.indexOf('utm_') === 0){
        stripParams.push(paramKey);
      }
    });

    var strippedParams = _.omit(params, stripParams);

    if (hasReplaceState && !_.isEqual(params, strippedParams)) {
      var a = document.createElement('a');
      a.href = window.location.href;
      a.search = $.param(strippedParams);
      if (!a.search) {
        // Safari leaves a trailing ? when search is empty
        a.href = a.href.replace(/\?(#.+)?$/, a.hash);
      }

      window.history.replaceState({}, document.title, a.href);
    }
  },

  addContextData: function(properties, payload) {
    /* jshint sub: true */
    payload = payload || {};

    if (this.contextData.user_id) {
      payload['user_id'] = this.contextData.user_id;
      payload['user_name'] = this.contextData.user_name;
    } else {
      payload['loid'] = this.contextData.loid;
      payload['loid_created'] = decodeURIComponent(this.contextData.loid_created);
    }

    properties.forEach(function(contextProperty) {
      /* jshint eqnull: true */
      if (this.contextData[contextProperty] != null) {
        payload[contextProperty] = this.contextData[contextProperty];
      }
    }.bind(this));

    return payload;
  },

  screenviewEvent: function() {
    var eventTopic = 'screenview_events';
    var eventType = 'cs.screenview';
    var payload = this.addContextData([
      'vault_name',
      'vault_id',
      'listing_name',
      'language',
      'dnt',
      'referrer_domain',
      'referrer_url',
      'user_in_beta',
    ]);

    if (r.config.event_target) {
      for (var key in r.config.event_target) {
        var value = r.config.event_target[key];
        if (value !== null) {
          payload[key] = value;
        }
      }
    }

    var rank_by_link = {};
    $('.linklisting .thing.link').each(function() {
        var $thing = $(this);
        var fullname = $thing.data('fullname');
        var rank = parseInt($thing.data('rank')) || '';
        rank_by_link[fullname] = rank;
    });
    if (!_.isEmpty(rank_by_link)) {
        payload['rank_by_link'] = rank_by_link;
    }

    // event collector
    r.events.track(eventTopic, eventType, payload).send();
  },

  loginRequiredEvent: function(actionName, actionDetail, targetType, targetFullname) {
    var eventTopic = 'login_events';
    var eventType = 'cs.loggedout_' + actionName;
    var payload = this.addContextData([
      'vault_name',
      'vault_id',
      'listing_name',
      'referrer_domain',
      'referrer_url',
    ]);

    payload['process_notes'] = 'LOGIN_REQUIRED';

    if (actionDetail) {
      payload['details_text'] = actionDetail;
    }

    if (targetType) {
      payload['target_type'] = targetType;
    }

    if (targetFullname) {
      payload['target_fullname'] = targetFullname;
      payload['target_id'] = r.utils.fullnameToId(targetFullname);
    }

    // event collector
    r.events.track(eventTopic, eventType, payload).send();
  },

  timeoutForbiddenEvent: function(actionName, actionDetail, targetType, targetFullname) {
    var eventTopic = 'forbidden_actions';
    var eventType = 'cs.forbidden_' + actionName;
    var payload = this.addContextData([
      'vault_name',
      'vault_id',
    ]);

    payload['process_notes'] = 'IN_TIMEOUT';

    if (actionDetail) {
      payload['details_text'] = actionDetail;
    }

    if (targetType) {
      payload['target_type'] = targetType;
    }

    if (targetFullname) {
      payload['target_fullname'] = targetFullname;
      payload['target_id'] = r.utils.fullnameToId(targetFullname);
    }

    // event collector
    r.events.track(eventTopic, eventType, payload).send();
  },

  expandoEvent: function(actionName, targetData) {
    var eventTopic = 'expando_events';
    var eventType = 'cs.' + actionName;
    var payload = this.addContextData([
      'page_type',
      'listing_name',
      'referrer_domain',
      'referrer_url',
      'expando_preference',
      'media_preference_hide_nsfw',
    ]);

    if ('linkIsNSFW' in targetData) {
      payload['nsfw'] = targetData.linkIsNSFW;
    }

    if ('linkType' in targetData) {
      payload['target_type'] = targetData.linkType;
      
    }

    if ('provider' in targetData) {
      payload['provider'] = targetData.provider;
    }

    if ('linkFullname' in targetData) {
      payload['target_fullname'] = targetData.linkFullname;
      payload['target_id'] = r.utils.fullnameToId(targetData.linkFullname);
    }

    if ('linkCreated' in targetData) {
      payload['target_create_ts'] = targetData.linkCreated;
    }

    if ('linkURL' in targetData) {
      payload['target_url'] = targetData.linkURL;
    }

    if ('linkDomain' in targetData) {
      payload['target_url_domain'] = targetData.linkDomain;
    }

    if ('authorFullname' in targetData) {
      payload['target_author_id'] = r.utils.fullnameToId(targetData.authorFullname);
    }
      
    if ('VaultName' in targetData) {
      payload['vault_name'] = targetData.VaultName;
    }

    if ('VaultFullname' in targetData) {
      payload['vault_id'] = r.utils.fullnameToId(targetData.VaultFullname);
    }

    r.events.track(eventTopic, eventType, payload).send();
  },

  sendEvent: function(eventTopic, actionName, defaultFields, customFields, done) {
    var eventType = 'cs.' + actionName;
    var payload = this.addContextData(defaultFields, customFields);
    r.events.track(eventTopic, eventType, payload).send(done);
  },
};

r.analytics.breadcrumbs = {
  selector: '.thing, .side, .vault-list, .srdrop, .tagline, .md, .organic-listing, .gadget, .vault-interest-bar, .trending-vaults, a, button, input',
  maxLength: 3,
  sendLength: 2,

  init: function() {
    this.hasSessionStorage = this._checkSessionStorage();
    this.data = this._load();

    var refreshed = this.data[0] && this.data[0].url == window.location;
    if (!refreshed) {
      this._storeBreadcrumb();
    }

    $(document).delegate('a, button', 'click', $.proxy(function(ev) {
      this.storeLastClick($(ev.target));
    }, this));
  },

  _checkSessionStorage: function() {
    // Via modernizr.com's sessionStorage check.
    try {
      sessionStorage.setItem('__test__', 'test');
      sessionStorage.removeItem('__test__');
      return true;
    } catch(e) {
      return false;
    }
  },

  _load: function() {
    if (!this.hasSessionStorage) {
      return [{stored: false}];
    }

    var data;

    try {
      data = JSON.parse(sessionStorage.breadcrumbs);
    } catch (e) {
      data = [];
    }

    if (!_.isArray(data)) {
      data = [];
    }

    return data;
  },

  store: function() {
    if (this.hasSessionStorage) {
      sessionStorage.breadcrumbs = JSON.stringify(this.data);
    }
  },

  _storeBreadcrumb: function() {
    var cur = {
      url: location.toString(),
    };

    if ('referrer' in document) {
      var referrerExternal = !document.referrer.match('^' + r.config.currentOrigin);
      var referrerUnexpected = this.data[0] && document.referrer != this.data[0].url;

      if (referrerExternal || referrerUnexpected) {
        cur.ref = document.referrer;
      }
    }

    this.data.unshift(cur);
    this.data = this.data.slice(0, this.maxLength);
    this.store();
  },

  storeLastClick: function(el) {
    try {
      this.data[0].click =
        r.utils.querySelectorFromEl(el, this.selector);
      this.store();
    } catch (e) {
      // Band-aid for Firefox NS_ERROR_DOM_SECURITY_ERR until fixed.
    }
  },

  lastClickFullname: function() {
    var lastClick = _.find(this.data, function(crumb) {
      return crumb.click;
    });

    if (lastClick) {
      var match = lastClick.click.match(/.*data-fullname="(\w+)"/);
      return match && match[1];
    }
  },

  toParams: function() {
    params = [];
    for (var i = 0; i < this.sendLength; i++) {
      _.each(this.data[i], function(v, k) {
        params['c' + i + '_' + k] = v;
      });
    }
    return params;
  },

};


r.hooks.get('setup').register(function() {
  r.analytics.breadcrumbs.init();
});


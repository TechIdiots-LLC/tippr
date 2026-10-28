/*
 * The contents of this file are subject to the Common Public Attribution
 * License Version 1.0 (the "License"); you may not use this file except in
 * compliance with the License. You may obtain a copy of the License at
 * https://github.com/TechIdiots-LLC/tippr/blob/master/LICENSE.
 *
 * Software distributed under the License is distributed on an "AS IS" basis,
 * WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
 * the specific language governing rights and limitations under the License.
 *
 * The Original Code is Tippr.
 *
 * The Initial Developer of the Original Code is TechIdiots LLC.
 * Copyright (c) 2026 TechIdiots LLC. All Rights Reserved.
 */

// Passkeys as a two-factor method (r2.lib.passkeys). Next to each two-factor
// code field, "use a passkey" asks the browser for one; the server answers a
// right one with a token that the field sends as its code. On preferences,
// security, "add a passkey" makes a new one.
r.passkey = {
  supported: function() {
    return !!(window.PublicKeyCredential && navigator.credentials &&
              navigator.credentials.create && window.isSecureContext)
  },

  fromB64: function(s) {
    s = s.replace(/-/g, '+').replace(/_/g, '/')
    while (s.length % 4) { s += '=' }
    var bin = atob(s), bytes = new Uint8Array(bin.length)
    for (var i = 0; i < bin.length; i++) { bytes[i] = bin.charCodeAt(i) }
    return bytes.buffer
  },

  toB64: function(buf) {
    var bytes = new Uint8Array(buf), s = ''
    for (var i = 0; i < bytes.length; i++) { s += String.fromCharCode(bytes[i]) }
    return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  },

  // the server's options (JSON, base64url) as the browser wants them
  creationOptions: function(o) {
    var self = this
    o.challenge = self.fromB64(o.challenge)
    o.user.id = self.fromB64(o.user.id)
    _.each(o.excludeCredentials || [], function(c) { c.id = self.fromB64(c.id) })
    return o
  },

  requestOptions: function(o) {
    var self = this
    o.challenge = self.fromB64(o.challenge)
    _.each(o.allowCredentials || [], function(c) { c.id = self.fromB64(c.id) })
    return o
  },

  // the browser's answer as JSON for the server
  credentialJSON: function(cred) {
    var resp = cred.response, out = {
      id: cred.id,
      rawId: this.toB64(cred.rawId),
      type: cred.type,
      clientExtensionResults: cred.getClientExtensionResults ? cred.getClientExtensionResults() : {},
      response: {clientDataJSON: this.toB64(resp.clientDataJSON)},
    }
    if (cred.authenticatorAttachment) { out.authenticatorAttachment = cred.authenticatorAttachment }
    if (resp.attestationObject) {
      out.response.attestationObject = this.toB64(resp.attestationObject)
      out.response.transports = resp.getTransports ? resp.getTransports() : []
    } else {
      out.response.authenticatorData = this.toB64(resp.authenticatorData)
      out.response.signature = this.toB64(resp.signature)
      out.response.userHandle = resp.userHandle ? this.toB64(resp.userHandle) : null
    }
    return JSON.stringify(out)
  },

  // a native Promise (jQuery 1.x deferreds don't chain with the browser's)
  post: function(url, data) {
    return new Promise(function(resolve, reject) {
      $.ajax({url: url, type: 'POST', dataType: 'json', data: data})
        .done(resolve)
        .fail(function() { reject({error: r._("couldn't reach the site")}) })
    })
  },

  api: function(action, data) {
    return this.post('/api/' + action + '.json', _.extend({uh: r.config.modhash}, data))
  },

  // what happened, and what to do next (the FIDO Alliance's guidance for
  // passkey failures: say what happened, without blame, and a next step)
  failed: function(err, creating, hasApp) {
    if (hasApp === undefined) { hasApp = !!r.config.two_factor_app }
    // the person cancelled, or no passkey was there
    if (err && (err.name === 'NotAllowedError' || err.name === 'AbortError')) {
      if (creating) {
        return r._('No passkey was created. Try again, or add an authenticator app instead.')
      }
      return hasApp ? r._('No passkey was used. Try again, or enter a code instead.')
                    : r._('No passkey was used. Try again, or use a recovery code instead.')
    }
    if (err && err.name === 'InvalidStateError') {
      return r._('This device already has a passkey for your account: it is in your list.')
    }
    if (err && err.error) { return err.error }
    if (creating) {
      return r._("We couldn't create your passkey. Try again, or add an authenticator app instead.")
    }
    return hasApp ? r._("We couldn't check your passkey. Try again, or enter a code instead.")
                  : r._("We couldn't check your passkey. Try again, or use a recovery code instead.")
  },

  // whether the account the form is for has an authenticator app, so has
  // codes to type (the login code page says on its form; otherwise it's
  // the account signed in)
  hasApp: function($form) {
    var attr = $form.attr('data-has-app')
    if (attr !== undefined) { return attr === '1' }
    return !!r.config.two_factor_app
  },

  // sign with a passkey; resolves to the code for the form
  authenticate: function($form) {
    var self = this, login = $form.attr('data-passkey-login')
    var options = login ? self.post('/logins/passkey_options', {token: login})
                        : self.api('passkey_auth_options', {})
    return options.then(function(res) {
      if (!res || res.error) { return Promise.reject(res) }
      return navigator.credentials.get({publicKey: self.requestOptions(res.options)})
        .then(function(cred) {
          var data = {credential: self.credentialJSON(cred)}
          if (login) {
            return self.post('/logins/passkey_auth', _.extend(data, {token: login, challenge: res.token}))
          }
          return self.api('passkey_auth', _.extend(data, {token: res.token}))
        })
    }).then(function(res) {
      if (!res || res.error) { return Promise.reject(res) }
      return res.code
    })
  },

  // "use a passkey" with a code field. With an authenticator app, the field
  // stays and the button is the other way ("or use a passkey"). Without
  // one there's no code to type: the button leads, the field (and a submit
  // button that's only for it, .otp-submit) hide behind "use a recovery
  // code instead", and sending the form with no code asks for the passkey
  // first.
  addButton: function(input) {
    var self = this, $input = $(input), $form = $input.closest('form')
    if ($input.data('passkey-button') || $form.is('#pref-otp-qr')) { return }
    // no code wanted there (the computer is remembered)
    if ($input.prop('disabled')) { return }
    $input.data('passkey-button', true)
    var hasApp = self.hasApp($form)
    var $status = $('<span class="passkey-status"></span>')
    var $button = $('<button type="button" class="btn passkey-use"></button>')
      .text(hasApp ? r._('or use a passkey') : r._('use a passkey'))
    var usePasskey = function() {
      $status.text('')
      $button.prop('disabled', true)
      self.authenticate($form).then(function(code) {
        $input.val(code)
        if ($form.hasClass('passkey-add')) {
          // proved with a passkey: on to adding the new one
          self.register($form.find('.passkey-add-button'))
        } else if ($form[0].requestSubmit) {
          // send the form as if the code had been typed
          $form[0].requestSubmit()
        } else {
          $form.submit()
        }
      }, function(err) {
        $status.text(self.failed(err, false, hasApp))
      }).then(function() { $button.prop('disabled', false) })
    }
    $button.on('click', usePasskey)
    // "remember this computer" goes above the button: the passkey sends the
    // form as soon as it's used, so the box has to be ticked before
    var $remember = $form.find('input[name=remember]').closest('label')
    if (hasApp) {
      ($remember.length ? $remember : $input).after($button, $status)
      return
    }

    var $submit = $form.find('.otp-submit')
    var $recovery = $('<a href="#" class="passkey-recovery"></a>')
      .text(r._('use a recovery code instead'))
      .on('click', function(e) {
        e.preventDefault()
        $recovery.hide()
        $input.attr('placeholder', r._('recovery code')).show().focus()
        $submit.show()
      })
    $input.hide().before($button, $status, $recovery)
    $remember.insertBefore($button)
    $submit.hide()
    // sent without a code (the field still hidden): the passkey first.
    // (A capture listener runs before the form's own onsubmit, and stops it.)
    // (not where one entered a few minutes ago still counts: data-otp-optional)
    $form[0].addEventListener('submit', function(e) {
      if ($input.val() || $input.is(':visible') || $input.attr('data-otp-optional')) { return }
      e.preventDefault()
      e.stopImmediatePropagation()
      usePasskey()
    }, true)
  },

  // "add a passkey" on preferences, security
  register: function($button) {
    var self = this, $form = $button.closest('form'), $status = $form.find('.status')
    $status.text('')
    var data = {otp: $form.find('[name=otp]').val() || '',
                password: $form.find('[name=password]').val() || ''}
    self.api('passkey_register_options', data).then(function(res) {
      if (!res || res.error) { return Promise.reject(res) }
      // before the browser's own prompt: what it's for
      $status.text(r._('Follow your browser’s prompt to create a passkey for this site.'))
      return navigator.credentials.create({publicKey: self.creationOptions(res.options)})
        .then(function(cred) {
          return self.api('passkey_register', {
            token: res.token, credential: self.credentialJSON(cred),
            name: $form.find('[name=passkey_name]').val() || ''})
        })
    }).then(function(res) {
      if (!res || res.error) { return Promise.reject(res) }
      // "Passkey created" on the page it comes back to
      var page = '/prefs/security?passkey=created'
      var hash = res.first ? '#recovery-codes' : '#two-factor-methods'
      if (window.location.pathname + window.location.search === page) {
        // (only the hash would change, which doesn't load the page)
        window.location.hash = hash
        window.location.reload()
      } else {
        window.location = page + hash
      }
    }).catch(function(err) {
      // (the server's refusal too, which the step above turns into this)
      $status.text(self.failed(err, true))
    })
  },

  // Signing in with a passkey alone, on the login forms. The browser's
  // autofill on the username field offers the site's passkeys (conditional
  // mediation: the FIDO Alliance found it works far better than a separate
  // button); browsers without that get a "sign in with a passkey" button.
  signinStart: function($scope) {
    var self = this
    $scope = $scope || $(document)
    var $inputs = $scope.find('input[autocomplete~="webauthn"]')
    if (!$inputs.length || !self.supported()) { return }
    $scope.find('.passkey-signin-button').off('click.passkey').on('click.passkey', function() {
      self.signinWith($(this), false)
    })
    var PKC = window.PublicKeyCredential
    var check = PKC.isConditionalMediationAvailable ? PKC.isConditionalMediationAvailable() : Promise.resolve(false)
    check.then(function(available) {
      if (available) {
        self.signinTries = 0
        self.signinWith($inputs.first(), true)
      } else {
        $scope.find('.passkey-signin-button').show()
      }
    }, function() { $scope.find('.passkey-signin-button').show() })
  },

  // the login form the passkey is for: the one being typed in, else el's
  signinForm: function($el) {
    var $active = $(document.activeElement).closest('form')
    if ($active.find('input[autocomplete~="webauthn"]').length) { return $active }
    var $form = $el.closest('form')
    if ($form.length) { return $form }
    return $el.closest('.passkey-signin').prevAll('form').first()
  },

  signinDest: function($form) {
    // where to go after: the form's dest, else back to this page
    var dest = $form.find('[name=dest]').val() || (window.location.pathname + window.location.search)
    try {
      var url = new URL(dest, window.location.origin)
      if (url.origin === window.location.origin) { dest = url.pathname + url.search + url.hash }
    } catch (e) {}
    return dest
  },

  signinWith: function($el, conditional) {
    var self = this
    // one passkey request at a time: a new one replaces the autofill's
    if (self.signinAbort) { self.signinAbort.abort(); self.signinAbort = null }
    var ctrl = (conditional && window.AbortController) ? new AbortController() : null
    if (ctrl) { self.signinAbort = ctrl }
    var $form = self.signinForm($el)
    var $status = $form.nextAll('.passkey-signin').first().find('.passkey-signin-status')
    if (!conditional) {
      $status.text(r._('Follow your browser’s prompt to choose a passkey for this site.'))
    }
    self.post('/logins/passkey_signin_options', {}).then(function(res) {
      if (!res || res.error) { return Promise.reject(res) }
      var request = {publicKey: self.requestOptions(res.options)}
      if (conditional) {
        request.mediation = 'conditional'
        if (ctrl) { request.signal = ctrl.signal }
      }
      return navigator.credentials.get(request).then(function(cred) {
        $form = self.signinForm($el)
        $status = $form.nextAll('.passkey-signin').first().find('.passkey-signin-status')
        $status.text(r._('Signing in…'))
        return self.post('/logins/passkey_signin', {
          token: res.token, credential: self.credentialJSON(cred),
          rem: $form.find('[name=rem]').is(':checked') ? 'on' : '',
          dest: self.signinDest($form)})
      })
    }).then(function(res) {
      if (!res || res.error) { return Promise.reject(res) }
      window.location = res.dest || '/'
    }).catch(function(err) {
      // replaced by another request (the button, or the popup opening)
      if (err && err.name === 'AbortError' && ctrl && ctrl.signal.aborted) { return }
      var cancelled = err && (err.name === 'NotAllowedError' || err.name === 'AbortError')
      if (!(conditional && cancelled)) {
        $status.text((err && err.error) ||
          (cancelled ? r._('No passkey was used. Try again, or log in with your password.')
                     : r._("We couldn't sign you in with a passkey. Try again, or log in with your password.")))
      }
      // keep offering passkeys in the autofill (a few times, not forever)
      if (conditional && (self.signinTries = (self.signinTries || 0) + 1) < 5) {
        self.signinWith($el, true)
      }
    })
  },

  init: function() {
    var self = this
    if (!r.config.logged) { self.signinStart() }
    if (!self.supported()) {
      // the browser can't make one: only the authenticator app is offered
      $('.passkey-only').hide()
      return
    }
    $('.passkey-add-button').on('click', function() { self.register($(this)) })
    var forLogin = $('form[data-passkey-login]')
    if (r.config.two_factor_passkeys || forLogin.length) {
      var $fields = forLogin.length ? forLogin.find('input[name=otp]') : $('input[name=otp]')
      $fields.each(function() { self.addButton(this) })
    }
  },
}

$(function() { r.passkey.init() })

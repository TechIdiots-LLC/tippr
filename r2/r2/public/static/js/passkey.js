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

  failed: function(err) {
    // the person cancelled, or no passkey was there
    if (err && (err.name === 'NotAllowedError' || err.name === 'AbortError')) {
      return r._('no passkey was used')
    }
    if (err && err.name === 'InvalidStateError') {
      return r._('that passkey is already added')
    }
    return (err && err.error) || r._("the passkey didn't work")
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

  // "use a passkey" next to a code field
  addButton: function(input) {
    var self = this, $input = $(input), $form = $input.closest('form')
    if ($input.data('passkey-button') || $form.is('#pref-otp-qr')) { return }
    $input.data('passkey-button', true)
    var $status = $('<span class="passkey-status"></span>')
    var $button = $('<button type="button" class="btn passkey-use"></button>')
      .text(r._('use a passkey'))
      .on('click', function() {
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
          $status.text(self.failed(err))
        }).then(function() { $button.prop('disabled', false) })
      })
    $input.after($button, $status)
  },

  // "add a passkey" on preferences, security
  register: function($button) {
    var self = this, $form = $button.closest('form'), $status = $form.find('.status')
    $status.text('')
    var data = {otp: $form.find('[name=otp]').val() || '',
                password: $form.find('[name=password]').val() || ''}
    self.api('passkey_register_options', data).then(function(res) {
      if (!res || res.error) { return Promise.reject(res) }
      return navigator.credentials.create({publicKey: self.creationOptions(res.options)})
        .then(function(cred) {
          return self.api('passkey_register', {
            token: res.token, credential: self.credentialJSON(cred),
            name: $form.find('[name=passkey_name]').val() || ''})
        })
    }).then(function(res) {
      if (!res || res.error) { return Promise.reject(res) }
      window.location = '/prefs/security' + (res.first ? '#recovery-codes' : '#two-factor-methods')
      window.location.reload()
    }, function(err) {
      $status.text(self.failed(err))
    })
  },

  init: function() {
    var self = this
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

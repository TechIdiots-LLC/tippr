/*
Adds temporary logging of gets/sets through the legacy global `tippr` object.
 */
!function(r, undefined) {
  r.hooks.get('setup').register(function() {
    try {
      // create a new object to detect if anywhere is still using the
      // the legacy config global object
      window.tippr = {};

      function migrateWarn(message) {
        r.sendError(message, { tag: 'tippr-config-migrate-error' })
      }

      var keys = Object.keys(r.config);

      keys.forEach(function(key) {
        Object.defineProperty(window.tippr, key, {
          configurable: false,
          enumerable: true,
          get: function() {
            var message = "config property %(key)s accessed through global tippr object.";
            migrateWarn(message.format({ key: key }));
            return r.config[key];
          },
          set: function(value) {
            var message = "config property %(key)s set through global tippr object.";
            migrateWarn(message.format({ key: key }));
            return r.config[key] = value;
          },
        });
      });
    } catch (err) {
      // for the odd browser that doesn't support getters/setters, just let
      // it function as-is.
      window.tippr = r.config;
    }
  });
}(r);

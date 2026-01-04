/*
  Init modules defined in tippr-init.js

  requires r.hooks (hooks.js)
 */
!function(r) {
  r.hooks.get('tippr-init').register(function() {
    try {
        r.events.init();
        r.analytics.init();
        r.access.init();
    } catch (err) {
        r.sendError('Error during tippr-init.js init', err.toString());
    }
  })

  $(function() {
    r.hooks.get('tippr-init').call();
  });
}(r);

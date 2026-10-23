// A tippr button for other sites: the page sets tippr_url, tippr_title,
// tippr_target (a vault), tippr_bgcolor, tippr_bordercolor and
// tippr_newwindow if it likes, then includes this script, which adds an
// iframe with button1.html from wherever this script was loaded.
(function() {
  var script = document.currentScript || (function() {
    var scripts = document.getElementsByTagName('script');
    return scripts[scripts.length - 1];
  })();
  var base = script.src.substring(0, script.src.lastIndexOf('/') + 1);
  var src = base + 'button1.html?url=' +
      encodeURIComponent(window.tippr_url || window.location.href);
  var options = {
    title: window.tippr_title,
    vault: window.tippr_target,
    bgcolor: window.tippr_bgcolor,
    bordercolor: window.tippr_bordercolor,
    newwindow: window.tippr_newwindow
  };
  for (var name in options) {
    if (options[name]) {
      src += '&' + name + '=' + encodeURIComponent(options[name]);
    }
  }
  var frame = document.createElement('iframe');
  frame.src = src;
  frame.height = '22';
  frame.width = '120';
  frame.scrolling = 'no';
  frame.frameBorder = '0';
  script.parentNode.insertBefore(frame, script.nextSibling);
})();

var buttonEmbed = (function() {
  // the site serving these button files: its posts, submit page and API
  var baseUrl = window.location.protocol + "//" + window.location.host
  var apiUrl = baseUrl
  var logo = $q('a.logo')
  var up = $q('a.up')
  var down = $q('a.down')
  var submission = $q('a.submission-details')
  var query = getQueryParams()

  function $q(s) {
    return document.querySelector(s)
  }

  function getQueryParams() {
    var params = {}
    var segments = window.location.search.substring(1).split('&')

    for (var i=0; i < segments.length; i++) {
      var pair = segments[i].split('=')
      params[pair[0]] = decodeURIComponent(pair[1])
    }

    return params
  }

  function pointLabel(x) {
    x = parseInt(x, 10)
    return x + " <span class='points-label'>point" + (x !== 1 ? "s" : "") + "</span>"
  }

  function submitUrl() {
    var url = baseUrl

    if (query.vault) {
      url += '/v/' + encodeURIComponent(query.vault)
    }

    url += '/submit?url=' + encodeURIComponent(query.url)

    if (query.title) {
      url += '&title=' + encodeURIComponent(query.title)
    }

    return url
  }

  function parseSubmission(response) {
    if (response.data && response.data.children.length > 0) {
      var child = response.data.children[0];

      submission.href = baseUrl + child.data.permalink;
      submission.innerHTML = pointLabel(child.data.score);
      submission.className += ' has-points';
      logo.href = up.href = down.href = submission.href;
    } else {
      submission.innerHTML = 'submit';
    }
  }

  function loadSubmission() {
    var script = document.createElement('script');
    script.type = 'text/javascript';
    script.src = apiUrl + '/button_info.json?jsonp=buttonEmbed.parseSubmission&url=' + encodeURIComponent(query.url);
    document.body.appendChild(script);
  }

  function safeColor(colorString) {
    var match = colorString.match(/([A-F0-9]{6}|[A-F0-9]{3})/i)
    if (match) {
      return '#' + match[0]
    }
    return null
  }

  function applyParams() {
    if (query.bgcolor) {
      document.body.style.backgroundColor = safeColor(query.bgcolor)
    }

    if (query.bordercolor) {
      $q('.wrap').style.borderColor = safeColor(query.bordercolor)
    }

    var links = document.getElementsByTagName('a')
    for (var i=0; i < links.length; i++) {
      links[i].target = query.newwindow ? "_blank" : "_top"
    }
  }

  function init() {
    // the site's name, and where the button hides that text, its icon
    logo.textContent = window.location.hostname.replace(/^www\./, "")
    if (parseInt(window.getComputedStyle(logo).textIndent, 10) < 0) {
      logo.style.backgroundImage = "url(" + baseUrl + "/favicon.ico)"
    }
    submission.href = logo.href = up.href = down.href = submitUrl()
    applyParams()
    loadSubmission()
  }

  return {
    init: init,
    parseSubmission: parseSubmission
  }
}())

buttonEmbed.init()

# The contents of this file are subject to the Common Public Attribution
# License Version 1.0 (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# https://github.com/TechIdiots-LLC/tippr/blob/master/LICENSE.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is Tippr.
#
# The Initial Developer of the Original Code is TechIdiots LLC.
# Copyright (c) 2026 TechIdiots LLC. All Rights Reserved.
###############################################################################
"""The middleware that replaced Paste's: error pages, static files."""

import os
import tempfile
import unittest

import webob

from r2.config.middleware import ErrorDocuments, StaticFiles, path_info_split


def app_answering(responses):
    """An app answering each path with (status, headers, body), recording
    the requests it got."""
    calls = []

    def app(environ, start_response):
        calls.append((environ["PATH_INFO"], environ.get("QUERY_STRING", "")))
        status, headers, body = responses[environ["PATH_INFO"]]
        start_response(status, list(headers))
        return [body]
    app.calls = calls
    return app


def mapper(code, message, environ, global_conf=None, **kw):
    if environ.get("pylons.error_call"):
        return None
    environ["pylons.error_call"] = True
    if code in (403, 404):
        return "/error/document/?code=%d" % code


class ErrorDocumentsTest(unittest.TestCase):
    def get(self, app, path):
        return webob.Request.blank(path).get_response(
            ErrorDocuments(app, {}, mapper))

    def test_other_statuses_pass_through(self):
        app = app_answering({"/ok": ("200 OK", [("X-A", "1")], b"fine")})
        res = self.get(app, "/ok")
        self.assertEqual((res.status, res.body), ("200 OK", b"fine"))
        self.assertEqual(app.calls, [("/ok", "")])

    def test_error_gets_the_error_page_with_its_status(self):
        app = app_answering({
            "/missing": ("404 Not Found",
                         [("Set-Cookie", "a=1"), ("X-Frame-Options", "DENY"),
                          ("Content-Type", "text/plain")], b"bare"),
            "/error/document/": ("200 OK",
                                 [("Content-Type", "text/html"),
                                  ("Set-Cookie", "b=2")], b"<p>styled</p>"),
        })
        res = self.get(app, "/missing")
        self.assertEqual(res.status, "404 Not Found")
        self.assertEqual(res.body, b"<p>styled</p>")
        self.assertEqual(app.calls, [("/missing", ""),
                                     ("/error/document/", "code=404")])
        # the first response's headers stay unless the page sets them;
        # cookies from both are kept
        self.assertEqual(res.headers["Content-Type"], "text/html")
        self.assertEqual(res.headers["X-Frame-Options"], "DENY")
        self.assertEqual(res.headers.getall("Set-Cookie"), ["a=1", "b=2"])

    def test_an_error_page_error_is_not_forwarded_again(self):
        app = app_answering({
            "/missing": ("404 Not Found", [], b"bare"),
            "/error/document/": ("403 Forbidden", [], b"page broke"),
        })
        res = self.get(app, "/missing")
        self.assertEqual((res.status, res.body), ("404 Not Found", b"page broke"))
        self.assertEqual(len(app.calls), 2)


class StaticFilesTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.first = os.path.join(self.root, "first")
        self.second = os.path.join(self.root, "second")
        for directory in (self.first, os.path.join(self.second, "static")):
            os.makedirs(directory)
        self.write(self.first, "plugin.js", b"plugin")
        self.write(self.second, "static/site.css", b"body{}")
        self.write(self.second, "plugin.js", b"not the plugin's")
        self.write(self.root, "secret.txt", b"secret")
        self.passed = []

        def fallback(environ, start_response):
            self.passed.append(environ["PATH_INFO"])
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"from the app"]
        self.app = StaticFiles(fallback, [self.first, self.second])

    def write(self, directory, name, data):
        with open(os.path.join(directory, name), "wb") as f:
            f.write(data)

    def get(self, path, method="GET"):
        return webob.Request.blank(path, method=method).get_response(self.app)

    def test_serves_files(self):
        res = self.get("/static/site.css")
        self.assertEqual((res.status_int, res.body), (200, b"body{}"))
        self.assertEqual(res.content_type, "text/css")
        self.assertEqual(self.passed, [])

    def test_first_directory_wins(self):
        self.assertEqual(self.get("/plugin.js").body, b"plugin")

    def test_everything_else_goes_to_the_app(self):
        for path in ("/", "/static", "/static/", "/nope.css",
                     "/../secret.txt", "/static/../../secret.txt"):
            self.assertEqual(self.get(path).body, b"from the app", path)
        self.assertEqual(self.get("/plugin.js", method="POST").body,
                         b"from the app")

    def test_conditional_get(self):
        first = self.get("/plugin.js")
        req = webob.Request.blank("/plugin.js")
        req.if_modified_since = first.last_modified
        self.assertEqual(req.get_response(self.app).status_int, 304)


class PathInfoSplitTest(unittest.TestCase):
    def test_split(self):
        self.assertEqual(path_info_split("/domain/example.com/hot"),
                         ("domain", "/example.com/hot"))
        self.assertEqual(path_info_split("/domain"), ("domain", ""))
        self.assertEqual(path_info_split("/a/"), ("a", "/"))
        self.assertEqual(path_info_split("/"), (None, ""))
        self.assertEqual(path_info_split(""), (None, ""))

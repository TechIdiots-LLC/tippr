#!/usr/bin/env python
# Copyright (c) 2026 TechIdiots LLC (Tippr). All Rights Reserved.
#
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0, as described in the LICENSE file in this repository.
###############################################################################
"""The order r2's own Pylons (pylons/controllers/core.py) does things in."""

import unittest

import pylons
from pylons.controllers.core import WSGIController
from pylons.wsgiapp import PylonsResponse
from webob import Request


class Page(WSGIController):
    def GET_page(self):
        return "<html><body>the page</body></html>"

    def __after__(self):
        # as post() does for the admin bar's timings
        pylons.response.text = pylons.response.text.replace(
            "</body>", "<script>r.timings = []</script></body>")


class Download(WSGIController):
    def GET_file(self):
        # sent as it's made (a backup download)
        pylons.response.content_type = "application/x-tar"
        pylons.response.app_iter = (b"chunk%d" % i for i in range(3))
        pylons.response.content_length = 18


class TestActionResult(unittest.TestCase):
    def setUp(self):
        pylons.response._push_object(PylonsResponse())
        self.addCleanup(pylons.response._pop_object)

    def test_after_sees_what_the_action_returned(self):
        request = Request.blank("/")
        request.environ["pylons.routes_dict"] = {"action": "GET_page"}
        response = request.get_response(Page())
        self.assertEqual(
            response.text,
            "<html><body>the page<script>r.timings = []</script></body></html>")

    def test_a_streamed_response(self):
        request = Request.blank("/")
        request.environ["pylons.routes_dict"] = {"action": "GET_file"}
        response = request.get_response(Download())
        self.assertEqual(response.body, b"chunk0chunk1chunk2")
        self.assertEqual(response.content_length, 18)

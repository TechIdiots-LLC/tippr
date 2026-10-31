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

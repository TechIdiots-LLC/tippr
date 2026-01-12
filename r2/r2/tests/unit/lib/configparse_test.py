#!/usr/bin/env python
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0. (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://code.reddit.com/LICENSE. The License is based on the Mozilla Public
# License Version 1.1, but Sections 14 and 15 have been added to cover use of
# software over a computer network and provide for limited attribution for the
# Original Developer. In addition, Exhibit A has been modified to be consistent
# with Exhibit B.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is reddit.
#
# The Original Developer is the Initial Developer.  The Initial Developer of
# the Original Code is reddit Inc.
#
# All portions of the code written by reddit are Copyright (c) 2006-2015 reddit
# Inc. All Rights Reserved.
###############################################################################
import datetime
import unittest

from r2.lib.configparse import ConfigValue


class TestConfigValue(unittest.TestCase):

    def test_str(self):
        self.assertEqual('x', ConfigValue.str('x'))

    def test_int(self):
        self.assertEqual(3, ConfigValue.int('3'))
        self.assertEqual(-3, ConfigValue.int('-3'))
        with self.assertRaises(ValueError):
            ConfigValue.int('asdf')

    def test_float(self):
        self.assertEqual(3.0, ConfigValue.float('3'))
        self.assertEqual(-3.0, ConfigValue.float('-3'))
        with self.assertRaises(ValueError):
            ConfigValue.float('asdf')

    def test_bool(self):
        self.assertEqual(True, ConfigValue.bool('TrUe'))
        self.assertEqual(False, ConfigValue.bool('fAlSe'))
        with self.assertRaises(ValueError):
            ConfigValue.bool('asdf')

    def test_tuple(self):
        self.assertEqual((), ConfigValue.tuple(''))
        self.assertEqual(('a', 'b'), ConfigValue.tuple('a, b'))

    def test_set(self):
        self.assertEqual(set(), ConfigValue.set(''))
        self.assertEqual({'a', 'b'}, ConfigValue.set('a, b'))

    def test_set_of(self):
        self.assertEqual(set(), ConfigValue.set_of(str)(''))
        self.assertEqual({'a', 'b'}, ConfigValue.set_of(str)('a, b, b'))
        self.assertEqual({'a', 'b'},
                          ConfigValue.set_of(str, delim=':')('b : a : b'))

    def test_tuple_of(self):
        self.assertEqual((), ConfigValue.tuple_of(str)(''))
        self.assertEqual(('a', 'b'), ConfigValue.tuple_of(str)('a, b'))
        self.assertEqual(('a', 'b'),
                          ConfigValue.tuple_of(str, delim=':')('a : b'))

    def test_dict(self):
        self.assertEqual({}, ConfigValue.dict(str, str)(''))
        self.assertEqual({'a': ''}, ConfigValue.dict(str, str)('a'))
        self.assertEqual({'a': 3}, ConfigValue.dict(str, int)('a: 3'))
        self.assertEqual({'a': 3, 'b': 4},
                          ConfigValue.dict(str, int)('a: 3, b: 4'))
        self.assertEqual({'a': (3, 5), 'b': (4, 6)},
                          ConfigValue.dict(
                              str, ConfigValue.tuple_of(int), delim=';')
                          ('a: 3, 5;  b: 4, 6'))

    def test_choice(self):
        self.assertEqual(1, ConfigValue.choice(alpha=1)('alpha'))
        self.assertEqual(2, ConfigValue.choice(alpha=1, beta=2)('beta'))
        with self.assertRaises(ValueError):
            ConfigValue.choice(alpha=1)('asdf')

    def test_timeinterval(self):
        self.assertEqual(datetime.timedelta(0, 60),
                          ConfigValue.timeinterval('1 minute'))
        with self.assertRaises(KeyError):
            ConfigValue.timeinterval('asdf')

# TODO: test ConfigValue.messages
# TODO: test ConfigValue.baseplate
# TODO: test ConfigValue.json_dict

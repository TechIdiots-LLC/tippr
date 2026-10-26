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

import pylons
from pylons.i18n.translation import _get_translator


def test_config_push_and_get():
    # Ensure deterministic behavior even if package import-time setup
    # has pushed a config object (tests import the package which may push
    # a default config). Temporarily clear the stack for the duration of
    # the assertions and restore it afterwards.
    original_stack = list(pylons.config._stack)
    try:
        pylons.config._stack.clear()
        # After clearing, the stack should be empty
        assert len(pylons.config._stack) == 0, f"Stack should be empty but has {len(pylons.config._stack)} items"
        assert not bool(pylons.config), "bool(pylons.config) should be False when stack is empty"
        assert pylons.config.get('nonexistent', 'default') == 'default'

        pylons.config._push_object({'lang': 'en', 'foo': 'bar'})
        assert pylons.config.get('lang') == 'en'
        assert pylons.config['foo'] == 'bar'

        pylons.config._pop_object()
        assert pylons.config.get('lang') is None
    finally:
        pylons.config._stack[:] = original_stack


def test_translator_push_and_get():
    trans = _get_translator('en')
    # translator should expose gettext-like API
    assert hasattr(trans, 'gettext')

    pylons.translator._push_object(trans)
    assert hasattr(pylons.translator._stack[-1], 'gettext')
    pylons.translator._pop_object()


def test_request_locals_are_per_thread():
    # paster serves requests from a thread pool: what one request pushes
    # (c, the translator, ...) must not be seen or popped by another.
    import threading
    from types import SimpleNamespace

    shared = pylons.tmpl_context._current_obj()
    first_pushed = threading.Event()
    second_done = threading.Event()
    seen = {}

    def first():
        pylons._begin_request()
        pylons.tmpl_context._push_object(SimpleNamespace(user='first'))
        first_pushed.set()
        second_done.wait(5)
        seen['first'] = pylons.tmpl_context.user
        pylons.tmpl_context._pop_object()
        pylons._end_request()

    def second():
        first_pushed.wait(5)
        pylons._begin_request()
        # sees the shared default, not the first request's object
        seen['second_start'] = pylons.tmpl_context._current_obj()
        pylons.tmpl_context._push_object(SimpleNamespace(user='second'))
        seen['second'] = pylons.tmpl_context.user
        pylons.tmpl_context._pop_object()
        # an extra pop must not remove the shared default
        pylons.tmpl_context._pop_object()
        pylons._end_request()
        second_done.set()

    threads = [threading.Thread(target=first), threading.Thread(target=second)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)

    assert seen == {'first': 'first', 'second_start': shared,
                    'second': 'second'}
    assert pylons.tmpl_context._current_obj() is shared


def test_replace_object_swaps_this_requests_object():
    # set_lang swaps the translator setup_app_env pushed; the request's
    # end then pops it, leaving the shared one
    shared = pylons.translator._current_obj()
    pylons._begin_request()
    pylons.translator._push_object('default')
    pylons.translator._replace_object('de')
    assert pylons.translator._current_obj() == 'de'
    pylons.translator._replace_object('fr')
    assert pylons.translator._current_obj() == 'fr'
    pylons.translator._pop_object()
    assert pylons.translator._current_obj() is shared
    pylons._end_request()
    assert pylons.translator._current_obj() is shared


def test_replace_object_pushes_when_the_request_has_none():
    shared = pylons.translator._current_obj()
    pylons._begin_request()
    pylons.translator._replace_object('de')
    assert pylons.translator._current_obj() == 'de'
    pylons.translator._pop_object()
    pylons._end_request()
    assert pylons.translator._current_obj() is shared

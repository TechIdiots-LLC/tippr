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

"""Pylons i18n compatibility shim.

Provides `_`, `ungettext`, and other i18n functions that mimic Pylons' i18n API.
These functions use a thread-local translator that can be set per-request.
"""
from threading import local

from .translation import _get_translator, _NoopTranslator

# Thread-local storage for the current translator
_translator_local = local()


def get_translator():
    """Get the current translator: the one r2's set_lang() installed on
    pylons.translator for this request, else the thread-local one."""
    import pylons
    stack = pylons.translator._stack
    if stack and hasattr(stack[-1], 'gettext'):
        return stack[-1]
    translator = getattr(_translator_local, 'translator', None)
    if translator is None:
        translator = _NoopTranslator()
        _translator_local.translator = translator
    return translator


def set_translator(translator):
    """Set the current thread-local translator."""
    _translator_local.translator = translator


def _(message):
    """Mark a string for translation and translate it.

    This is the primary translation function, equivalent to gettext.
    """
    return get_translator().gettext(message)


def ungettext(singular, plural, n):
    """Translate a string with plural forms.

    Returns the singular form if n == 1, otherwise the plural form.
    """
    return get_translator().ngettext(singular, plural, n)


def ugettext(message):
    """Unicode version of gettext (same as _ in Python 3)."""
    return get_translator().gettext(message)


def ngettext(singular, plural, n):
    """Alias for ungettext."""
    return ungettext(singular, plural, n)


def N_(message):
    """Mark a string for translation without translating it.

    Used for lazy translation where the actual translation happens later.
    """
    return message


def lazy_ugettext(message):
    """Lazy version of ugettext that defers translation."""
    # For now, just return the translated string immediately
    # A full implementation would return a lazy proxy object
    return ugettext(message)


def get_lang():
    """Return the currently active language for the translator.

    Prefer the translator installed on `pylons.translator` (a LocalStack),
    falling back to the thread-local translator used by this shim.
    Returns the `pylons_lang` attribute set by translators or `None`.
    """
    # Prefer Pylons translator if available
    try:
        import pylons
    except Exception:
        pylons = None

    if pylons is not None:
        try:
            lang = getattr(pylons.translator, 'pylons_lang', None)
        except Exception:
            lang = None
        if not lang:
            t = getattr(_translator_local, 'translator', None)
            lang = getattr(t, 'pylons_lang', None) if t is not None else None
        if lang:
            return lang

    # Pyramid fallback: return a list like ['en'] to match existing callers
    try:
        from pyramid.threadlocal import get_current_request
        from pyramid.i18n import get_locale_name
        req = get_current_request()
        if req is not None:
            loc = get_locale_name(req)
            if loc:
                return [loc]
    except Exception:
        pass

    return None


__all__ = [
    '_', 'ungettext', 'ugettext', 'ngettext', 'N_', 'lazy_ugettext',
    'get_translator', 'set_translator', 'get_lang', '_get_translator',
]

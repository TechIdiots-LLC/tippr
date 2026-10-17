"""Minimal i18n translation helper for the Pylons shim.

Provides `_get_translator(lang)` which returns an object with gettext-like
methods. If Babel is available it will use Babel translations; otherwise it
falls back to a no-op translator.
"""
import gettext as gettext_module
import os

try:
    from babel.support import Translations as BabelTranslations
except Exception:
    BabelTranslations = None


class LanguageError(Exception):
    """Exception raised when a language cannot be found or loaded."""
    pass


class NullTranslations(gettext_module.NullTranslations):
    """A translations class that doesn't translate anything.

    This is used as a fallback when no translations are available.
    """

    def ugettext(self, message):
        """Unicode version of gettext."""
        return message

    def ungettext(self, singular, plural, n):
        """Unicode version of ngettext."""
        return singular if n == 1 else plural


class _NoopTranslator:
    def gettext(self, s):
        return s

    def ugettext(self, s):
        return s

    def ngettext(self, singular, plural, n):
        return singular if n == 1 else plural

    def ungettext(self, singular, plural, n):
        return singular if n == 1 else plural


def _get_translator(lang=None):
    """Return a translator object for the given language.

    This intentionally returns a minimal translator that supports the calls
    tests and the codebase make (gettext / ugettext / ngettext).
    """
    if BabelTranslations is None:
        return _NoopTranslator()
    try:
        # Construct a simple Translations object if message catalogs exist on
        # the environment; otherwise fall back to no-op translator.
        return BabelTranslations.load(locale=lang) if lang else BabelTranslations()
    except Exception:
        return _NoopTranslator()


def translation(domain, localedir=None, languages=None, class_=None,
                fallback=False):
    """Load the gettext catalog `domain` for `languages`, like Pylons'
    translation(): <localedir>/<lang>/LC_MESSAGES/<domain>.mo.

    Raises OSError (as Pylons does) if none of the languages has a catalog,
    unless fallback is true.
    """
    if class_ is None:
        class_ = gettext_module.GNUTranslations
    return gettext_module.translation(
        domain,
        localedir=localedir,
        languages=languages,
        class_=class_,
        fallback=fallback,
    )


__all__ = [
    '_get_translator', '_NoopTranslator', 'LanguageError', 'NullTranslations',
    'translation',
]

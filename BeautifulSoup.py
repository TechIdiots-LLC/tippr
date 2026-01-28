"""Compatibility shim providing a legacy BeautifulSoup 3-like API backed by bs4.

This module exposes: BeautifulSoup, BeautifulStoneSoup, SoupStrainer, Tag,
and constants HTML_ENTITIES/XML_ENTITIES so existing imports like
`from BeautifulSoup import BeautifulSoup` continue to work.
"""
from bs4 import BeautifulSoup as _BS4, SoupStrainer as _SoupStrainer

# bs4's Tag constructor signature differs from BeautifulSoup3's. Provide a
# small compatibility factory that matches the older call-site usage
# `Tag(soup, name, attrs)` by delegating to `soup.new_tag` and attaching a
# `findParent` alias expected by older code.


# Constants used by older code — kept as simple markers.
HTML_ENTITIES = 'html'
XML_ENTITIES = 'xml'


def _make_bs(markup, parser, parseOnlyThese=None, **kwargs):
    if parseOnlyThese is not None:
        # bs4 accepts a SoupStrainer instance (or tag name/attrs)
        strainer = parseOnlyThese if isinstance(parseOnlyThese, _SoupStrainer) else _SoupStrainer(parseOnlyThese)
        return _BS4(markup, parser, parse_only=strainer)
    return _BS4(markup, parser)


def BeautifulSoup(markup, convertEntities=None, parseOnlyThese=None, **kwargs):
    """Drop-in replacement for BeautifulSoup(markup, convertEntities=..., parseOnlyThese=...)

    - `convertEntities` is ignored (bs4 handles entities differently).
    - `parseOnlyThese` is passed to bs4 via `parse_only` using SoupStrainer where possible.
    """
    parser = kwargs.pop('features', 'html.parser')
    return _make_bs(markup, parser, parseOnlyThese, **kwargs)


def BeautifulStoneSoup(markup, **kwargs):
    """Approximate BeautifulStoneSoup behaviour by parsing as XML."""
    return _make_bs(markup, 'xml', **kwargs)


# Expose names expected by imports like `import BeautifulSoup` then
# `BeautifulSoup.BeautifulSoup(...)` or `from BeautifulSoup import BeautifulSoup`.
SoupStrainer = _SoupStrainer

# Attach legacy constants onto the callable to mimic older API usage
BeautifulSoup.HTML_ENTITIES = HTML_ENTITIES
BeautifulSoup.XML_ENTITIES = XML_ENTITIES

# Make module-level references
__all__ = [
    'BeautifulSoup',
    'BeautifulStoneSoup',
    'SoupStrainer',
    'Tag',
    'HTML_ENTITIES',
    'XML_ENTITIES',
]

# For code that does `import BeautifulSoup; BeautifulSoup.BeautifulSoup(...)`
BeautifulSoup_module = None
try:
    # expose the callable at module attribute with same name
    globals()['BeautifulSoup'] = BeautifulSoup
    globals()['BeautifulStoneSoup'] = BeautifulStoneSoup
    globals()['SoupStrainer'] = SoupStrainer
    # Provide a legacy-compatible Tag factory
    def Tag(soup, name, attrs=None):
        # attrs may be a list of (k,v) tuples in older code; convert to dict
        if isinstance(attrs, list):
            attrs = dict(attrs)
        attrs = attrs or {}
        t = soup.new_tag(name, attrs=attrs)
        # bs3 used findParent; provide an alias to bs4's find_parent
        try:
            t.findParent = t.find_parent
        except Exception:
            pass
        return t

    globals()['Tag'] = Tag
except Exception:
    pass

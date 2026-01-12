"""Pure-Python fallback for the Cython `wrapped.pyx` implementation.

This provides minimal implementations of `Templated`, `CachedTemplate`,
`Wrapped`, and `Styled` sufficient for import-time use during tests
and for basic rendering paths. It intentionally implements a subset of
the original behaviour to avoid requiring C compilation in test CI.
"""
from datetime import datetime
from hashlib import md5
import random
import re
import types

from r2.lib.utils import SimpleSillyStub

CACHE_HIT_SAMPLE_RATE = 0.001
RENDER_TIMER_SAMPLE_RATE = 0.001


class _TemplateUpdater:
    """Helper class to do regex-based template substitution."""
    def __init__(self, d, start, end, template, pattern):
        self.d = d
        self.start = start
        self.end = end
        self.template = template
        self.pattern = pattern

    def update(self):
        return self.pattern.sub(self._convert, self.template)

    def _convert(self, m):
        name = m.group("named")
        return self.d.get(name, self.start + name + self.end)


class StringTemplate:
    start_delim = "<$>"
    end_delim = "</$>"
    pattern2 = r"[_a-z][_a-z0-9]*"
    pattern2 = r"%(start_delim)s(?:(?P<named>%(pattern)s))%(end_delim)s" % \
               dict(pattern=pattern2,
                    start_delim=re.escape(start_delim),
                    end_delim=re.escape(end_delim))
    pattern2 = re.compile(pattern2, re.UNICODE)

    def __init__(self, template):
        if template is None:
            template = ''
        if isinstance(template, bytes):
            self.template = template.decode('utf-8')
        else:
            self.template = str(template)

    def update(self, d):
        """Replace variables in the template and return an updated Template."""
        if d:
            updater = _TemplateUpdater(d, self.start_delim, self.end_delim,
                                       self.template, self.pattern2)
            return self.__class__(updater.update())
        return self

    def finalize(self, d=None):
        """Same as update but returns the final string."""
        if d:
            return self.update(d).template
        return self.template


class CacheStub:
    def __init__(self, item, style):
        self.name = "h%s%s" % (id(item), str(style).replace('-', '_'))

    def __str__(self):
        return StringTemplate.start_delim + self.name + StringTemplate.end_delim

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self.name)


class CachedVariable(CacheStub):
    def __init__(self, name):
        self.name = name


class Templated(object):
    cachable = False
    cache_ignore = set()

    def __repr__(self):
        return "<Templated: %s>" % self.__class__.__name__

    def __init__(self, **context):
        for k, v in context.items():
            setattr(self, k, v)
        if not hasattr(self, 'render_class'):
            self.render_class = self.__class__

    def template(self, style='html'):
        from r2.config.templates import tpm
        return tpm.get(self.render_class, style)

    def template_is_null(self, style='html'):
        template = self.template(style)
        return getattr(template, 'is_null', False)

    def cache_key(self, *a):
        raise NotImplementedError

    @property
    def render_class_name(self):
        return self.render_class.__name__

    def render_nocache(self, style):
        """No-frills rendering of the template."""
        from pylons import tmpl_context as c
        from pylons import app_globals as g

        if (self.cachable and
                style != "api" and
                random.random() < RENDER_TIMER_SAMPLE_RATE):
            timer = g.stats.get_timer(name="render.%s" % self.render_class_name)
        else:
            timer = SimpleSillyStub()

        timer.start()
        template = self.template(style)

        # store the global render style (child templates might override it)
        render_style = c.render_style
        c.render_style = style

        res = template.render(thing=self)
        if not isinstance(res, StringTemplate):
            res = StringTemplate(res)

        # reset the global render style
        c.render_style = render_style
        timer.stop()
        return res

    def _render(self, style, **kwargs):
        """Renders the current template with the current style.

        If this is the first template to be rendered, it will track
        cachable templates, insert stubs for them in the output,
        get_multi from the cache, and render the uncached templates.
        """
        from pylons import tmpl_context as c
        from pylons import app_globals as g

        style = style or getattr(c, 'render_style', None) or 'html'

        # prepare (and store) the list of cachable items
        primary = False
        if not isinstance(c.render_tracker, dict):
            primary = True
            c.render_tracker = {}

        if (self.cachable and
                not self.template_is_null(style) and
                style != "api"):
            # insert a stub for cachable non-primary templates
            res = CacheStub(self, style)
            cache_key = self.cache_key(style)
            c.render_tracker[res.name] = (cache_key, (self, (style, kwargs)))
        else:
            # either a primary template or not cachable, so render it
            res = self.render_nocache(style)

        # if this is the primary template, let the caching games begin
        if primary:
            updates = {}
            to_cache = set()
            while c.render_tracker:
                current = c.render_tracker
                c.render_tracker = {}

                # do a multi-get
                cached = self._read_cache(dict(current.values()))
                replacements = {}
                new_updates = {}

                for key, (cache_key, others) in current.items():
                    item, (style, kw) = others
                    if cache_key not in cached:
                        to_cache.add(cache_key)
                        r = item.render_nocache(style)
                    else:
                        r = cached[cache_key]

                    event_name = 'render-cache.%s' % item.render_class_name
                    name = 'hit' if cache_key in cached else 'miss'
                    g.stats.event_count(
                        event_name, name, sample_rate=CACHE_HIT_SAMPLE_RATE)

                    replacements[key] = r.finalize(kw)
                    new_updates[key] = (cache_key, (r, kw))

                for k in updates.keys():
                    cache_key, (value, kw) = updates[k]
                    value = value.update(replacements)
                    updates[k] = cache_key, (value, kw)

                updates.update(new_updates)

            # cache content that was newly rendered
            _to_cache = {}
            for k, (v, kw) in updates.values():
                if k in to_cache:
                    _to_cache[k] = v
            self._write_cache(_to_cache)

            # edge case: this may be the primary template and cachable
            if isinstance(res, CacheStub):
                res = updates[res.name][1][0]

            # now we can update the updates to make use of their kw args
            _updates = {}
            for k, (foo, (v, kw)) in updates.items():
                _updates[k] = v.finalize(kw)
            updates = _updates

            # replace till we can't replace any more
            npasses = 0
            while True:
                npasses += 1
                r = res
                res = res.update(kwargs).update(updates)
                semi_final = res.finalize()
                if r.finalize() == res.finalize():
                    res = semi_final
                    break

            # wipe out the render tracker object
            c.render_tracker = None
        elif not isinstance(res, CacheStub):
            res = res.finalize(kwargs)

        return res

    def _write_cache(self, keys):
        from pylons import app_globals as g
        from r2.lib.cache import MemcachedError

        if not keys:
            return

        try:
            g.rendercache.set_multi(keys, time=3600)
        except MemcachedError as e:
            g.log.warning("rendercache error: %s", e)
            return

    def _read_cache(self, keys):
        from pylons import app_globals as g
        ret = g.rendercache.get_multi(keys)
        return ret

    def render(self, style=None, **kw):
        from r2.lib.filters import unsafe
        res = self._render(style, **kw)
        return unsafe(res) if isinstance(res, str) else res


class Uncachable(Exception):
    pass


_easy_cache_cls = set([bool, int, float, str, type(None), datetime])


def make_cachable(v, style):
    if v.__class__ in _easy_cache_cls or isinstance(v, type):
        try:
            return str(v)
        except UnicodeDecodeError:
            return repr(v)
    elif isinstance(v, (types.MethodType, CachedVariable)):
        return ''
    elif isinstance(v, (tuple, list, set)):
        return repr([make_cachable(x, style) for x in v])
    elif isinstance(v, dict):
        ret = {}
        for k in sorted(v.keys()):
            ret[k] = make_cachable(v[k], style)
        return repr(ret)
    elif hasattr(v, "cache_key"):
        result = v.cache_key(style)
        if result is None:
            return ''
        return str(result) if not isinstance(result, str) else result
    else:
        raise Uncachable("%s, %s" % (v, type(v)))


class CachedTemplate(Templated):
    # Temporarily disable template caching to debug placeholder issues.
    # Set to True to re-enable fragment caching once memcached is working.
    cachable = False

    def template_hash(self, style):
        template = self.template(style)
        template_hash = getattr(template, "hash", id(self.__class__))
        return template_hash

    def cachable_attrs(self):
        """Returns attrs that should be used in generating the cache key."""
        ret = []
        for k in sorted(self.__dict__):
            if k not in self.cache_ignore and not k.startswith('_'):
                ret.append((k, self.__dict__[k]))
        return ret

    def cache_key(self, style):
        from pylons import request
        from pylons import tmpl_context as c

        keys = [
            c.user_is_loggedin,
            c.user_is_admin,
            c.domain_prefix,
            style,
            c.secure,
            c.lang,
            c.site.user_path if hasattr(c.site, 'user_path') else '',
            self.template_hash(style),
        ]

        if c.secure:
            keys.append(request.host)

        keys = [make_cachable(x, style) for x in keys]

        auto_keys = [(k, make_cachable(v, style))
                     for k, v in self.cachable_attrs()]
        keys.append(repr(auto_keys))
        h = md5(''.join(keys).encode('utf-8')).hexdigest()
        return "rend:%s:%s" % (self.render_class_name, h)


class Wrapped(CachedTemplate):
    cachable = False
    cache_ignore = set(['lookups'])

    def __init__(self, *lookups, **context):
        self.lookups = lookups
        if self.__class__ == Wrapped and lookups:
            self.render_class = lookups[0].__class__
        else:
            self.render_class = self.__class__
        self.cache_ignore = self.cache_ignore.union(set(['cachable', 'render', 'cache_ignore', 'lookups']))
        Templated.__init__(self, **context)

    def _any_hasattr(self, lookups, attr):
        for l in lookups:
            if hasattr(l, attr):
                return True

    def __repr__(self):
        return "<Wrapped: %s,  %s>" % (self.__class__.__name__, self.lookups)

    def __getattr__(self, attr):
        if attr == 'lookups':
            raise AttributeError(attr)
        for lookup in self.lookups:
            try:
                res = getattr(lookup, attr)
                setattr(self, attr, res)
                return res
            except AttributeError:
                continue
        raise AttributeError("%r has no %s" % (self, attr))

    def __iter__(self):
        if self.lookups and hasattr(self.lookups[0], '__iter__'):
            return iter(self.lookups[0])
        raise NotImplementedError


class Styled(CachedTemplate):
    def __init__(self, style, _id='', css_class='', **kw):
        self._id = _id
        self.css_class = css_class
        self.style = style
        super().__init__(**kw)

    def template(self, style='html'):
        base_template = super().template(style)
        # best-effort: return base_template (dummy)
        return base_template


def make_cachable(v, style):
    # best-effort serializer for cache keys
    if v is None:
        return 'None'
    if isinstance(v, (bool, int, float, str)):
        return str(v)
    if isinstance(v, (list, tuple, set)):
        return repr([make_cachable(x, style) for x in v])
    if isinstance(v, dict):
        return repr({k: make_cachable(v[k], style) for k in sorted(v)})
    if hasattr(v, 'cache_key'):
        try:
            return v.cache_key(style)
        except Exception:
            return repr(v)
    return repr(v)

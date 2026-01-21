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

import os.path
import sys
from collections import OrderedDict

from importlib.metadata import entry_points as get_entry_points, distributions


def _iter_entry_points(group, name=None):
    """Get entry points for a group, optionally filtered by name.

    Compatible replacement for pkg_resources working_set.iter_entry_points().
    """
    eps = get_entry_points(group=group)
    if name is not None:
        eps = [ep for ep in eps if ep.name == name]
    return iter(eps)


def _get_dist_location(entry_point):
    """Get the location (path) of a distribution from an entry point."""
    if hasattr(entry_point, 'dist') and entry_point.dist:
        dist = entry_point.dist
        # In importlib.metadata, dist._path points to the metadata directory
        if hasattr(dist, '_path') and dist._path:
            return str(dist._path.parent)
    return None


class Plugin:
    js = {}
    config = {}
    live_config = {}
    needs_static_build = False
    needs_translation = True
    errors = {}
    source_root_url = None

    def __init__(self, entry_point):
        self.entry_point = entry_point

    @property
    def name(self):
        return self.entry_point.name

    @property
    def path(self):
        module = sys.modules[type(self).__module__]
        return os.path.dirname(module.__file__)

    @property
    def template_dir(self):
        """Add module/templates/ as a template directory."""
        return os.path.join(self.path, 'templates')

    @property
    def static_dir(self):
        return os.path.join(self.path, 'public')

    def on_load(self, g):
        pass

    def add_js(self, module_registry=None):
        if not module_registry:
            from r2.lib import js
            module_registry = js.module

        for name, module in self.js.items():
            if name not in module_registry:
                module_registry[name] = module
            else:
                module_registry[name].extend(module)

    def declare_queues(self, queues):
        pass

    def add_routes(self, mc):
        pass

    def load_controllers(self):
        pass

    def get_documented_controllers(self):
        return []


class PluginLoader:
    def __init__(self, working_set=None, plugin_names=None):
        # working_set parameter kept for backwards compatibility but ignored
        # We now use importlib.metadata directly

        if plugin_names is None:
            entry_points = list(self.available_plugins())
        else:
            entry_points = []
            for name in plugin_names:
                try:
                    entry_point = next(self.available_plugins(name))
                except StopIteration:
                    print(("Unable to locate plugin "
                                          "%s. Skipping." % name), file=sys.stderr)
                    continue
                else:
                    entry_points.append(entry_point)

        self.plugins = OrderedDict()
        for entry_point in entry_points:
            try:
                plugin_cls = entry_point.load()
            except Exception as e:
                if plugin_names:
                    # if this plugin was specifically requested, fail.
                    raise e
                else:
                    print(("Error loading plugin %s (%s)."
                                          " Skipping." % (entry_point.name, e)), file=sys.stderr)
                    continue
            self.plugins[entry_point.name] = plugin_cls(entry_point)

    def __len__(self):
        return len(self.plugins)

    def __iter__(self):
        return iter(self.plugins.values())

    def __reversed__(self):
        return reversed(list(self.plugins.values()))

    def __getitem__(self, key):
        return self.plugins[key]

    def available_plugins(self, name=None):
        return _iter_entry_points('r2.plugin', name)

    def declare_queues(self, queues):
        for plugin in self:
            plugin.declare_queues(queues)

    def load_plugins(self, config):
        g = config['pylons.app_globals']
        for plugin in self:
            # Record plugin version
            entry = plugin.entry_point
            dist_location = _get_dist_location(entry)
            if dist_location:
                git_dir = os.path.join(dist_location, '.git')
                g.record_repo_version(entry.name, git_dir)

            # Load plugin
            g.config.add_spec(plugin.config)
            config['pylons.paths']['templates'].insert(0, plugin.template_dir)
            plugin.add_js()
            plugin.on_load(g)

    def load_controllers(self):
        # this module relies on pylons.i18n._ at import time (for translating
        # messages) which isn't available 'til we're in request context.
        from r2.lib import errors

        for plugin in self:
            errors.add_error_codes(plugin.errors)
            plugin.load_controllers()

    def get_documented_controllers(self):
        for plugin in self:
            yield from plugin.get_documented_controllers()

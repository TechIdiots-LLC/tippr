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

"""Compatibility layer for `pylons.configuration`.

Provides a PylonsConfig class that mimics the original Pylons configuration
object for migration to Pyramid.
"""
import os
import copy


class PylonsConfig(dict):
    """A dictionary-like configuration object that mimics Pylons' PylonsConfig.

    This provides the `init_app` method and standard configuration keys
    expected by the r2 codebase.
    """

    defaults = {
        'debug': False,
        'pylons.package': None,
        'pylons.paths': {},
        'pylons.environ_config': {},
        'pylons.request_options': {},
        'pylons.response_options': {'headers': {}},
        'pylons.strict_tmpl_context': True,
        'pylons.c_attach_args': True,
        'pylons.errorware': {},
    }

    def __init__(self):
        super().__init__()
        self.update(copy.deepcopy(self.defaults))

    def init_app(self, global_conf, app_conf, package=None, paths=None):
        """Initialize the configuration for an application.

        Args:
            global_conf: Global configuration dictionary (from [DEFAULT] section)
            app_conf: Application configuration dictionary (from [app:main] section)
            package: The package name for the application
            paths: Dictionary of paths for the application
        """
        # Store original configs
        self['global_conf'] = global_conf
        self['app_conf'] = app_conf

        # Merge global_conf and app_conf into this config
        self.update(global_conf)
        self.update(app_conf)

        # Set the package name
        if package:
            self['pylons.package'] = package

        # Set up paths
        if paths:
            self['pylons.paths'] = paths

        # Set debug mode
        debug = global_conf.get('debug', 'false')
        if isinstance(debug, str):
            self['debug'] = debug.lower() in ('true', '1', 'yes', 'on')
        else:
            self['debug'] = bool(debug)

        # Set up errorware for error handling middleware
        self['pylons.errorware'] = {
            'debug': self['debug'],
            'error_email': global_conf.get('email_to'),
            'error_log': global_conf.get('error_log'),
            'smtp_server': global_conf.get('smtp_server', 'localhost'),
            'error_subject_prefix': global_conf.get('error_subject_prefix', '[Application Error]'),
            'from_address': global_conf.get('error_email_from', 'errors@localhost'),
            'error_message': global_conf.get('error_message', 'An error occurred'),
        }

    def __getattr__(self, name):
        # Allow attribute-style access for common configuration keys.
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


__all__ = ['PylonsConfig']

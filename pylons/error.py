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

"""Compatibility layer for `pylons.error`.

Provides error handling utilities for Mako templates that were
previously provided by Pylons.
"""
import sys


def handle_mako_error(context, error):
    """Error handler for Mako template rendering.

    This is used as the `error_handler` argument to Mako's TemplateLookup.
    When a template error occurs, this function is called to handle it.

    In the original Pylons implementation, this would format the error
    nicely. For now, we simply re-raise the exception.

    Args:
        context: The Mako context object
        error: The exception that occurred

    Raises:
        The original exception with its traceback preserved.
    """
    raise error.with_traceback(sys.exc_info()[2])


__all__ = ['handle_mako_error']

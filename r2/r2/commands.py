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
# 
# Portions created by TechIdiots LLC (Tippr) are Copyright (c) 2026
# TechIdiots LLC. All Rights Reserved.
###############################################################################
"""tippr-run: a script or a line of Python with the app loaded, for the
scheduled jobs, the queue processors and admins (tippr-run, tippr-shell).

    python -m r2.commands [--proctitle NAME] [--shell] CONFIGFILE [SCRIPT.py] [-c CODE]

It used to be a `paster run` command (PasteScript), which needs
pkg_resources; this loads the app with PasteDeploy itself."""

import argparse
import os
import sys

from paste.deploy import loadapp

from r2.lib.log import RavenErrorReporter


def parser():
    p = argparse.ArgumentParser(
        prog="tippr-run",
        description="Run a script or Python code with the tippr app loaded.")
    p.add_argument("config", metavar="CONFIGFILE", help="the ini, e.g. run.ini")
    p.add_argument("script", metavar="SCRIPT.py", nargs="?",
                   help="a script to run first")
    p.add_argument("-c", "--command", help="Python code to run")
    p.add_argument("--proctitle", help="set the title seen by ps and top")
    p.add_argument("--shell", action="store_true",
                   help="then an interactive prompt (tippr-shell)")
    # paster run's, still accepted
    p.add_argument("-v", "--verbose", action="count", help=argparse.SUPPRESS)
    return p


def load_app(config_file):
    """The app from the ini, set up the way a web request finds it (g, c and
    the rest), with the settings saved on /admin/site and /admin/config."""
    here_dir = os.getcwd()
    sys.path.insert(0, here_dir)

    # loading it sets up config and g for everything outside a request
    # (pylons' shared objects)
    wsgiapp = loadapp("config:%s" % config_file, relative_to=here_dir,
                      global_conf={"running_as_script": "true"})

    # the settings saved on /admin/site and /admin/config: web processes
    # apply them on their first request (BaseController), which scripts,
    # consumers and jobs never get
    from r2.lib import live_config_admin, site_info
    site_info.install()
    live_config_admin.install()
    return wsgiapp


def main(argv=None):
    args = parser().parse_args(argv)
    if args.proctitle:
        try:
            import setproctitle
            setproctitle.setproctitle("tippr " + args.proctitle)
        except ImportError:
            pass

    load_app(args.config)

    loaded_namespace = {}
    try:
        if args.script:
            with open(args.script, "rb") as f:
                exec(compile(f.read(), args.script, "exec"), loaded_namespace)
        if args.command:
            exec(args.command, loaded_namespace)
    except Exception:
        if "REDDIT_ERRORS_TO_SENTRY" in os.environ:
            RavenErrorReporter.capture_exception(exc_info=sys.exc_info())
        raise

    if args.shell:
        interact(loaded_namespace)


def interact(namespace):
    """tippr-shell: a Python prompt with the app loaded (paster shell
    was Pylons', which tippr doesn't have)."""
    import code

    from pylons import app_globals as g
    from pylons import request
    from pylons import tmpl_context as c

    import r2.models
    namespace.setdefault("g", g)
    namespace.setdefault("c", c)
    namespace.setdefault("request", request)
    for name in getattr(r2.models, "__all__", None) or dir(r2.models):
        if not name.startswith("_"):
            namespace.setdefault(name, getattr(r2.models, name))
    try:
        import readline  # noqa: F401 (history and editing at the prompt)
    except ImportError:
        pass
    code.interact(
        banner="tippr shell: g, c, request and r2.models are loaded "
               "(Account, Link, Vault...). Ctrl-D to leave.",
        local=namespace, exitmsg="")


if __name__ == "__main__":
    main()

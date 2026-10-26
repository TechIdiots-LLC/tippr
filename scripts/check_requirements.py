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

"""Check that a package's requirements, and theirs, are installed at
versions they accept (install/tippr.sh, after installing the pinned list):

    python scripts/check_requirements.py r2

Prints each mismatch and exits 1 if there is one. It's what
pkg_resources.require() did, with importlib.metadata and packaging, which
don't need setuptools.
"""

import importlib.metadata as metadata
import re
import sys

from packaging.requirements import Requirement


def _key(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def problems(name):
    found, seen, todo = [], set(), [(name, ())]
    while todo:
        name, extras = todo.pop()
        if (_key(name), extras) in seen:
            continue
        seen.add((_key(name), extras))
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            found.append("%s isn't installed" % name)
            continue
        for line in dist.requires or ():
            req = Requirement(line)
            if req.marker and not any(req.marker.evaluate({"extra": extra})
                                      for extra in extras or ("",)):
                continue
            try:
                installed = metadata.version(req.name)
            except metadata.PackageNotFoundError:
                found.append("%s needs %s, which isn't installed" % (name, req))
                continue
            if not req.specifier.contains(installed, prereleases=True):
                found.append("%s needs %s, but %s is installed" %
                             (name, req, installed))
            todo.append((req.name, tuple(sorted(req.extras))))
    return found


if __name__ == "__main__":
    bad = [p for name in sys.argv[1:] for p in problems(name)]
    for p in bad:
        print(p, file=sys.stderr)
    sys.exit(1 if bad else 0)

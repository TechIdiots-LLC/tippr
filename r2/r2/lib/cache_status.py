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
"""How the site's caches are doing, for /admin/config: each memcached the
site uses (its own statistics), and the nginx caches the installer set up.
"""

import socket

from pylons import app_globals as g

# the settings that name memcached servers (r2.lib.app_globals)
MEMCACHE_SETTINGS = ("mcrouter_addr", "lockcaches", "permacache_memcaches",
                     "hardcache_memcaches", "stalecaches")


def servers():
    """The memcached addresses the site is set to use."""
    found = []
    for name in MEMCACHE_SETTINGS:
        value = g.config.get(name) or ""
        if isinstance(value, (list, tuple)):
            value = ",".join(value)
        for address in str(value).split(","):
            address = address.strip()
            if address and address not in found:
                found.append(address)
    return found


def _stats(address, timeout=1.0):
    host, _, port = address.rpartition(":")
    with socket.create_connection((host or "127.0.0.1", int(port)),
                                  timeout=timeout) as conn:
        conn.sendall(b"stats\r\n")
        data = b""
        while not data.endswith(b"END\r\n"):
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
    stats = {}
    for line in data.decode("ascii", "replace").splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] == "STAT":
            stats[parts[1]] = parts[2]
    return stats


def memcached():
    """[{address, error or the numbers}] for each memcached."""
    result = []
    for address in servers():
        try:
            s = _stats(address)
        except (OSError, ValueError) as e:
            result.append(dict(address=address, error=str(e)))
            continue
        number = lambda key: int(s.get(key, 0) or 0)
        hits, misses = number("get_hits"), number("get_misses")
        limit = number("limit_maxbytes")
        result.append(dict(
            address=address,
            version=s.get("version", ""),
            limit_mb=limit // (1024 * 1024),
            used_mb=round(number("bytes") / (1024 * 1024), 1),
            used_percent=round(100.0 * number("bytes") / limit) if limit else 0,
            items=number("curr_items"),
            hit_percent=(round(100.0 * hits / (hits + misses), 1)
                         if hits + misses else None),
            evictions=number("evictions"),
            uptime_hours=round(number("uptime") / 3600.0, 1),
        ))
    return result


def nginx():
    """What the installer set nginx up to cache (it says so in the ini)."""
    page_cache = str(g.config.get("nginx_page_cache", "")).lower()
    static = str(g.config.get("nginx_static", "")).lower()
    return dict(
        page_cache=(None if not page_cache else page_cache in ("1", "true")),
        static=(None if not static else static in ("1", "true")),
    )

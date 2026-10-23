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
"""Fetching addresses members give the site (a post's link for its preview
and thumbnail, "suggest title") without reaching inside its own network.

The server would otherwise fetch whatever it's handed, 127.0.0.1, the
LAN, a cloud's metadata service (169.254.169.254) included, and publish
an internal image it found as a thumbnail. Here every connection, each
redirect's included, goes only to a public address (ipaddress.is_global):
the host name is resolved, checked, and connected to by the address
checked, so a DNS answer that changes in between can't slip past. Only
http and https are spoken: a redirect to ftp: or file: goes nowhere.
"""

import http.client
import ipaddress
import socket
import ssl
import urllib.error
import urllib.request


class BlockedAddress(urllib.error.URLError):
    """The address isn't on the public internet."""


def is_public(address):
    """Whether an IP address (a string) is a public one."""
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return ip.is_global and not ip.is_multicast


def public_address(host, port):
    """The first public address host resolves to, as (family, sockaddr);
    BlockedAddress if it has none (or doesn't resolve)."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise urllib.error.URLError(e)
    for family, _type, _proto, _name, sockaddr in infos:
        if is_public(sockaddr[0]):
            return family, sockaddr
    raise BlockedAddress("%s isn't a public address" % host)


def _connect(conn):
    family, sockaddr = public_address(conn.host, conn.port)
    sock = socket.socket(family, socket.SOCK_STREAM)
    if conn.timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
        sock.settimeout(conn.timeout)
    try:
        sock.connect(sockaddr)
    except OSError:
        sock.close()
        raise
    return sock


class _PublicHTTPConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = _connect(self)


class _PublicHTTPSConnection(http.client.HTTPSConnection):
    def connect(self):
        sock = _connect(self)
        # the certificate is checked against the name, not the address
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _PublicHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_PublicHTTPConnection, req)


class _PublicHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self):
        urllib.request.HTTPSHandler.__init__(
            self, context=ssl.create_default_context())

    def https_open(self, req):
        return self.do_open(_PublicHTTPSConnection, req,
                            context=self._context)


def _opener():
    # (built by hand, not build_opener: that adds ftp:, file: and data:)
    opener = urllib.request.OpenerDirector()
    for handler in (_PublicHTTPHandler(), _PublicHTTPSHandler(),
                    urllib.request.HTTPDefaultErrorHandler(),
                    urllib.request.HTTPRedirectHandler(),
                    urllib.request.HTTPErrorProcessor(),
                    urllib.request.UnknownHandler()):
        opener.add_handler(handler)
    return opener


_OPENER = _opener()


def urlopen(request, timeout=15):
    """urllib.request.urlopen, for addresses a member gave: public hosts
    only, http and https only. BlockedAddress (a URLError) otherwise."""
    if isinstance(request, str):
        request = urllib.request.Request(request)
    if request.type not in ("http", "https"):
        raise BlockedAddress("only http and https addresses are fetched")
    return _OPENER.open(request, timeout=timeout)

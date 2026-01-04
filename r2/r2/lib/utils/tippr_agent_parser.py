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
# All portions of the code written by reddit are Copyright (c) 2006-2016 reddit
# Inc. All Rights Reserved.
###############################################################################

import re

from httpagentparser import AndroidBrowser, Browser, DetectorBase, detectorshub
from httpagentparser import detect as de


def register_detector(cls):
    """Collector of all the tippr detectors."""
    detectorshub.register(cls())
    return cls


class TipprDetectorBase(DetectorBase):
    agent_string = None
    version_string = r'(\.?\d+)*'

    def __init__(self):
        if self.agent_string:
            self.agent_regex = re.compile(self.agent_string.format(
                look_for=self.look_for, version_string=self.version_string))
        else:
            self.agent_regex = None

        self.version_regex = re.compile('(?P<version>{})'.format(
            self.version_string))

    def getVersion(self, agent, word):
        match = None
        if self.agent_regex:
            match = self.agent_regex.search(agent)

        if not match:
            match = self.version_regex.search(agent)

        if match and 'version' in list(match.groupdict().keys()):
            return match.group('version')

    def detect(self, agent, result):
        detected = super().detect(agent, result)

        # If there's no custom agent regex, just return whatever the base
        # detector found. Otherwise, attempt to match our custom regex and
        # populate `result` even if the base detector didn't detect anything.
        if not self.agent_regex:
            return detected

        match = self.agent_regex.search(agent)
        if not match:
            return detected

        groups = match.groupdict()
        platform_name = groups.get('platform')
        version = groups.get('pversion') or groups.get('version') or self.getVersion(agent, None)

        # Ensure there's a browser dict present for our detector to populate
        if 'browser' not in result or not isinstance(result.get('browser'), dict):
            result['browser'] = {}

        # Set browser name/version based on detector metadata and regex
        if self.name and 'name' not in result['browser']:
            result['browser']['name'] = self.name
        if version and 'version' not in result['browser']:
            result['browser']['version'] = version

        if platform_name:
            platform = {}
            platform['name'] = platform_name
            if version:
                platform['version'] = version
            result['platform'] = platform

        if self.is_app:
            result['app_name'] = result['browser']['name']

        return True


class TipprBrowser(TipprDetectorBase, Browser):
    """Base class for all tippr specific browsers."""
    # is_app denotes a client that is a native mobile application, but not a
    # browser.
    is_app = False


@register_detector
class TipprIsFunDetector(TipprBrowser):
    is_app = True
    look_for = 'tippr is fun'
    name = 'tippr is fun'
    agent_string = (r'^{look_for} \((?P<platform>.*?)\) '
                    '(?P<version>{version_string})$')
    override = [AndroidBrowser]


@register_detector
class TipprAndroidDetector(TipprBrowser):
    is_app = True
    look_for = 'TipprAndroid'
    name = 'Tippr: The Official App'
    agent_string = '{look_for} (?P<version>{version_string})$'


@register_detector
class TipprIOSDetector(TipprBrowser):
    is_app = True
    look_for = 'Tippr'
    name = 'tippr iOS'
    skip_if_found = ['Android']
    agent_string = (
        r'{look_for}\/Version (?P<version>{version_string})\/Build '
        r'(?P<b_number>\d+)\/(?P<platform>.*?) Version '
        r'(?P<pversion>{version_string}) \(Build .*?\)')


@register_detector
class AlienBlueDetector(TipprBrowser):
    is_app = True
    look_for = 'AlienBlue'
    name = 'Alien Blue'
    agent_string = (
        r'{look_for}\/(?P<version>{version_string}) CFNetwork\/'
        r'{version_string} (?P<platform>.*?)\/(?P<pversion>{version_string})')


@register_detector
class RelayForRedditDetector(TipprBrowser):
    is_app = True
    look_for = 'Relay by /u/DBrady'
    name = 'relay for tippr'
    agent_string = '{look_for} v(?P<version>{version_string})'


@register_detector
class TipprSyncDetector(TipprBrowser):
    is_app = True
    look_for = 'tippr_sync'
    name = 'Sync for tippr'
    agent_string = (
        r'android:com\.laurencedawson\.{look_for}'
        r':v(?P<version>{version_string}) \(by /u/ljdawson\)')


@register_detector
class NarwhalForRedditDetector(TipprBrowser):
    is_app = True
    look_for = 'narwhal'
    name = 'narwhal for tippr'
    agent_string = r'{look_for}-(?P<platform>.*?)\/\d+ by det0ur'


@register_detector
class McRedditDetector(TipprBrowser):
    is_app = True
    look_for = 'McReddit'
    name = 'McReddit'
    agent_string = '{look_for} - Tippr Client for (?P<platform>.*?)$'


@register_detector
class ReaditDetector(TipprBrowser):
    look_for = 'Readit'
    name = 'Readit'
    agent_string = r'(\({look_for} for WP /u/MessageAcrossStudios\) ?){{1,2}}'


@register_detector
class BaconReaderDetector(TipprBrowser):
    is_app = True
    look_for = 'BaconReader'
    name = 'Bacon Reader'
    agent_string = (
        r'{look_for}\/(?P<version>{version_string}) \([a-zA-Z]+; '
        '(?P<platform>.*?) (?P<pversion>{version_string}); '
        r'Scale\/{version_string}\)')


def detect(*args, **kw):
    return de(*args, **kw)


class Agent:
    __slots__ = (
        "agent_string",
        "browser_name",
        "browser_version",
        "os_name",
        "os_version",
        "platform_name",
        "platform_version",
        "sub_platform_name",
        "bot",
        "app_name",
        "is_mobile_browser",
    )

    MOBILE_PLATFORMS = {'iOS', 'Windows', 'Android', 'BlackBerry'}

    def __init__(self, **kw):
        kw.setdefault("is_mobile_browser", False)
        for k in self.__slots__:
            setattr(self, k, kw.get(k))

    @classmethod
    def parse(cls, ua):
        agent = cls(agent_string=ua)
        parsed = detect(ua)
        for attr in ("browser", "os", "platform"):
            d = parsed.get(attr)
            if d:
                for subattr in ("name", "version"):
                    if subattr in d:
                        key = "{}_{}".format(attr, subattr)
                        setattr(agent, key, d[subattr])

        agent.bot = parsed.get('bot')
        dist = parsed.get('dist')
        if dist:
            agent.sub_platform_name = dist.get('name')

        # if this is a known app, extract the app_name
        agent.app_name = parsed.get('app_name')
        agent.is_mobile_browser = agent.determine_mobile_browser()
        return agent

    def determine_mobile_browser(self):
        if self.platform_name in self.MOBILE_PLATFORMS:
            if self.sub_platform_name == 'IPad':
                return False

            if (
                self.platform_name == 'Android' and
                not (
                    'Mobile' in self.agent_string or
                    self.browser_name == 'Opera Mobile'
                )
            ):
                return False

            if (
                self.platform_name == 'Windows' and
                self.sub_platform_name != 'Windows Phone'
            ):
                return False

            if 'Opera Mini' in self.agent_string:
                return False

            return True
        return False

    def to_dict(self):
        d = {}
        for k in self.__slots__:
            if k != "agent_string":
                v = getattr(self, k, None)
                if v:
                    d[k] = v
        return d

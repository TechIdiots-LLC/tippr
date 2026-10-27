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
"""scripts/tippr_monitor.py: when it tells someone, and what."""

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import r2

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(r2.__file__)))), "scripts", "tippr_monitor.py")


def load_monitor():
    spec = importlib.util.spec_from_file_location("tippr_monitor", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


monitor = load_monitor()

SMOKE_OUTPUT = """== services
  ok    postgresql
  FAIL  cassandra is inactive
  ..    tippr-job-rising.service failed; its log, then running it again:
        rising: NoHostAvailable
  ok    tippr-job-rising.service (succeeded when run again)
  FAIL  tippr-consumer-vote_link_q@0.service failed:
        vote_link_q: connection refused
== pages (tippr.local)
  ok    /: 200
2 check(s) failed
"""


class DecideTest(unittest.TestCase):
    def test_quiet_while_ok(self):
        self.assertEqual(monitor.decide({"ok": True}, True, 100, 6), ({"ok": True}, None))

    def test_tells_when_it_starts_failing(self):
        state, event = monitor.decide({"ok": True}, False, 100, 6)
        self.assertEqual(event, "failing")
        self.assertEqual(state, {"ok": False, "since": 100, "alerted": 100})

    def test_quiet_while_still_failing_until_the_repeat(self):
        failing = {"ok": False, "since": 100, "alerted": 100}
        self.assertEqual(monitor.decide(failing, False, 100 + 3600, 6), (failing, None))
        state, event = monitor.decide(failing, False, 100 + 6 * 3600, 6)
        self.assertEqual(event, "still failing")
        self.assertEqual(state["alerted"], 100 + 6 * 3600)
        self.assertEqual(state["since"], 100)

    def test_tells_when_it_recovers(self):
        failing = {"ok": False, "since": 100, "alerted": 100}
        self.assertEqual(monitor.decide(failing, True, 200, 6), ({"ok": True}, "recovered"))

    def test_first_run_ever_is_like_ok_before(self):
        self.assertEqual(monitor.decide({}, False, 5, 6)[1], "failing")


class ReportTest(unittest.TestCase):
    def test_only_the_failures_and_their_logs(self):
        result = subprocess.CompletedProcess([], 1, SMOKE_OUTPUT, "")
        with patch.object(monitor.subprocess, "run", return_value=result):
            ok, report = monitor.run_check()
        self.assertFalse(ok)
        self.assertEqual(report, [
            "  FAIL  cassandra is inactive",
            "  FAIL  tippr-consumer-vote_link_q@0.service failed:",
            "        vote_link_q: connection refused",
        ])

    def test_messages(self):
        state = {"ok": False, "since": 0}
        text = monitor.message("still failing", "web1", ["  FAIL  nginx is inactive"], state, 1800)
        self.assertEqual(text, "tippr on web1: still failing after 30 minutes\n"
                               "  FAIL  nginx is inactive")
        self.assertEqual(monitor.message("recovered", "web1", [], {}, 0),
                         "tippr on web1 is working again.")
        long_report = ["x" * 100] * 50
        self.assertLess(len(monitor.message("failing", "h", long_report, state, 0)), 1800)


class SendTest(unittest.TestCase):
    def test_webhook_json_for_discord_and_slack(self):
        with patch.object(monitor.urllib.request, "urlopen") as urlopen:
            self.assertTrue(monitor.send({"TIPPR_ALERT_WEBHOOK": "https://hooks.example/x"},
                                         "failing", "tippr on h: down", "h"))
        request = urlopen.call_args[0][0]
        body = json.loads(request.data)
        self.assertEqual(body["content"], "tippr on h: down")
        self.assertEqual(body["text"], "tippr on h: down")
        self.assertEqual(body["status"], "failing")

    def test_ntfy_gets_plain_text(self):
        with patch.object(monitor.urllib.request, "urlopen") as urlopen:
            monitor.send({"TIPPR_ALERT_WEBHOOK": "https://ntfy.sh/mysite"},
                         "recovered", "back", "h")
        self.assertEqual(urlopen.call_args[0][0].data, b"back")

    def test_command_gets_the_message_and_subject(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            command = 'printf "%%s|" "$TIPPR_ALERT_SUBJECT" > %s; cat >> %s' % (out, out)
            self.assertTrue(monitor.send({"TIPPR_ALERT_COMMAND": command},
                                         "failing", "subject line\nmore", "h"))
            with open(out) as f:
                self.assertEqual(f.read(), "subject line|subject line\nmore")

    def test_failed_webhook_is_reported_not_raised(self):
        with patch.object(monitor.urllib.request, "urlopen", side_effect=OSError("down")):
            self.assertFalse(monitor.send({"TIPPR_ALERT_WEBHOOK": "https://x"}, "failing", "t", "h"))


class ConfTest(unittest.TestCase):
    def test_reads_shell_style_settings(self):
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
            f.write("# comment\nTIPPR_ALERT_WEBHOOK='https://x/y?a=b'\n\nTIPPR_ALERT_REPEAT_HOURS=2\n")
        self.addCleanup(os.unlink, f.name)
        self.assertEqual(monitor.read_conf(f.name), {
            "TIPPR_ALERT_WEBHOOK": "https://x/y?a=b", "TIPPR_ALERT_REPEAT_HOURS": "2"})
        self.assertEqual(monitor.read_conf("/nonexistent"), {})

    def test_quotes_inside_a_command_kept(self):
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
            f.write('TIPPR_ALERT_COMMAND=mail -s "$TIPPR_ALERT_SUBJECT" "me@example.com"\n')
        self.addCleanup(os.unlink, f.name)
        self.assertEqual(monitor.read_conf(f.name)["TIPPR_ALERT_COMMAND"],
                         'mail -s "$TIPPR_ALERT_SUBJECT" "me@example.com"')

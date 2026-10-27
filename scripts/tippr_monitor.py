#!/usr/bin/env python3
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
"""Tell someone when this server's tippr stops working, and when it's back.

tippr-monitor.timer runs this as root every 5 minutes (installed as
/usr/local/sbin/tippr-monitor). It runs the smoke check
(/usr/local/sbin/tippr-smoke-check, scripts/smoke_check.sh) and, when the
result changes, or every TIPPR_ALERT_REPEAT_HOURS (6) while it keeps
failing, sends what failed:

- to TIPPR_ALERT_WEBHOOK, a URL it POSTs to: a Discord or Slack webhook,
  an ntfy topic, or anything that takes JSON ({"text", "content", "host",
  "status"});
- to TIPPR_ALERT_COMMAND, a command given the message on its input and
  TIPPR_ALERT_SUBJECT in its environment (e.g. mail -s "$TIPPR_ALERT_SUBJECT"
  admin@example.com).

Both are in /etc/tippr/alerts.conf (install.cfg's TIPPR_ALERT_*). With
neither set it only logs (journalctl -u tippr-monitor). Only the standard
library, so it works while the site's own packages or stores don't.
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

CONF = "/etc/tippr/alerts.conf"
STATE = "/var/lib/tippr/monitor.json"
SMOKE_CHECK = "/usr/local/sbin/tippr-smoke-check"


def read_conf(path=CONF):
    conf = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    value = value.strip()
                    # quotes around the whole value, not ones inside a command
                    if len(value) > 1 and value[0] == value[-1] and value[0] in "'\"":
                        value = value[1:-1]
                    conf[key.strip()] = value
    except OSError:
        pass
    return conf


def run_check():
    """(ok, the lines worth sending)."""
    result = subprocess.run([SMOKE_CHECK], capture_output=True, text=True,
                            timeout=1500)
    lines = (result.stdout + result.stderr).splitlines()
    # what failed, and the log lines printed under it
    report, keep = [], False
    for line in lines:
        if line.startswith("  FAIL"):
            keep = True
        elif line.startswith(("  ok", "  ..", "==")):
            keep = False
        if keep:
            report.append(line.rstrip())
    return result.returncode == 0, report


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"ok": True}


def save_state(state):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE + ".tmp", "w") as f:
        json.dump(state, f)
    os.replace(STATE + ".tmp", STATE)


def decide(state, ok, now, repeat_hours):
    """(the new state, what to say: "failing", "still failing",
    "recovered" or None)."""
    if ok:
        if state.get("ok", True):
            return {"ok": True}, None
        return {"ok": True}, "recovered"
    if state.get("ok", True):
        return {"ok": False, "since": now, "alerted": now}, "failing"
    if now - state.get("alerted", 0) >= repeat_hours * 3600:
        return dict(state, alerted=now), "still failing"
    return state, None


def message(event, host, report, state, now):
    if event == "recovered":
        return "tippr on %s is working again." % host
    minutes = int((now - state.get("since", now)) / 60)
    head = "tippr on %s: %s" % (host, "checks are failing" if event == "failing"
                               else "still failing after %d minutes" % minutes)
    body = "\n".join(report) or "(the smoke check failed without saying why)"
    if len(body) > 1700:
        body = body[:1700] + "\n..."
    return head + "\n" + body


def post_webhook(url, text, host, status):
    if "ntfy" in url:
        data, headers = text.encode(), {"Title": "tippr on %s" % host}
    else:
        # Discord reads "content", Slack "text"; both ignore the other
        data = json.dumps({"content": text, "text": text, "host": host,
                           "status": status}).encode()
        headers = {"Content-Type": "application/json"}
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=20) as response:
        response.read()


def send(conf, event, text, host):
    sent = False
    url = conf.get("TIPPR_ALERT_WEBHOOK")
    if url:
        try:
            post_webhook(url, text, host, "ok" if event == "recovered" else "failing")
            sent = True
        except Exception as e:
            print("tippr-monitor: the webhook failed: %s" % e, file=sys.stderr)
    command = conf.get("TIPPR_ALERT_COMMAND")
    if command:
        env = dict(os.environ, TIPPR_ALERT_SUBJECT=text.splitlines()[0])
        result = subprocess.run(command, shell=True, input=text, text=True,
                                env=env, timeout=60)
        if result.returncode == 0:
            sent = True
        else:
            print("tippr-monitor: the alert command failed (%d)" % result.returncode,
                  file=sys.stderr)
    return sent


def main():
    conf = read_conf()
    repeat = float(conf.get("TIPPR_ALERT_REPEAT_HOURS") or 6)
    host = conf.get("TIPPR_ALERT_HOST") or socket.gethostname()
    ok, report = run_check()
    now = time.time()
    state, event = decide(load_state(), ok, now, repeat)
    if event:
        text = message(event, host, report, state, now)
        print(text)
        if not send(conf, event, text, host) and (
                conf.get("TIPPR_ALERT_WEBHOOK") or conf.get("TIPPR_ALERT_COMMAND")):
            # not saved, so the next run tells it again rather than lose
            # the news (exiting 0: a failed tippr-monitor unit would be
            # one of the failures it reports)
            return 0
    else:
        print("tippr-monitor: %s" % ("ok" if ok else "still failing (told already)"))
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())

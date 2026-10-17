"""Part of docker/smoke-test.sh, run inside the web container: log in as the
admin, submit a post, and check that the consumers put it in its vault's
listing and the search index. Exits non-zero on failure."""
import os
import sys
import time

import requests

BASE = "http://127.0.0.1:8001"
domain = os.environ["TIPPR_DOMAIN"]
user = os.environ.get("TIPPR_ADMIN_USER") or "tippr"
secrets = dict(line.strip().split("=", 1) for line in open("/config/secrets.env")
               if "=" in line and not line.startswith("#"))

s = requests.Session()
s.headers.update({"Host": domain, "X-Forwarded-Proto": "https",
                  "User-Agent": "tippr-smoke-test"})


def fail(message):
    print("FAIL: " + message)
    sys.exit(1)


login = s.post(BASE + "/api/login/" + user, data={
    "user": user, "passwd": secrets["TIPPR_ADMIN_PASSWORD"],
    "api_type": "json"}).json()["json"]
if login["errors"]:
    fail("login: %s" % login["errors"])
print("logged in as " + user)

title = "smoke test post %d" % time.time()
submit = s.post(BASE + "/api/submit", data={
    "kind": "self", "vault": "technology", "title": title,
    "text": "posted by docker/smoke-test.sh", "ai_content": "human",
    "uh": login["data"]["modhash"], "api_type": "json"}).json()["json"]
if submit["errors"]:
    fail("submit: %s" % submit["errors"])
print("posted " + submit["data"]["url"])


def wait_for(what, check, seconds=120):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if check():
            print(what)
            return
        time.sleep(3)
    fail("not " + what)


def in_listing():
    listing = s.get(BASE + "/v/technology/new.json").json()
    return title in [c["data"]["title"] for c in listing["data"]["children"]]


def in_search():
    found = s.get(BASE + "/search.json", params={"q": title}).json()
    return title in [c["data"]["title"] for c in found["data"]["children"]]


wait_for("in /v/technology/new", in_listing)
wait_for("found by search", in_search)

geo = requests.get("http://geoip:5000/geoip/8.8.8.8", timeout=10).json()
if geo.get("8.8.8.8", {}).get("country_code") != "US":
    fail("geoip lookup: %s" % geo)
print("geoip works")

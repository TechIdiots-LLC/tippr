// The contents of this file are subject to the Common Public Attribution
// License Version 1.0 (the "License"); you may not use this file except in
// compliance with the License. You may obtain a copy of the License at
// https://github.com/TechIdiots-LLC/tippr/blob/master/LICENSE.
//
// Software distributed under the License is distributed on an "AS IS" basis,
// WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
// the specific language governing rights and limitations under the License.
//
// The Original Code is Tippr.
//
// The Initial Developer of the Original Code is TechIdiots LLC.
// Copyright (c) 2026 TechIdiots LLC. All Rights Reserved.
///////////////////////////////////////////////////////////////////////////////
//
// The browser test (docker/smoke-test.sh with VISUAL_TEST=1, after the smoke
// test): ordinary members (docker/visual-seed.py makes them) use the site in
// real browsers, and every page they see is checked and saved as a
// screenshot, at desktop and phone width, in the light and the night theme.
// CI runs it on every push (ci-docker.yml) and before a release, from
// .github/actions/stack-test.
//
//   - alice logs in through the login form and posts through the submit form
//   - bob, carol and dave log in, and reply to each other down a thread
//   - they vote on the post and the comments, change and undo votes; the
//     arrows must show each voter's vote at once and after reloading, and
//     the scores must follow (votes are counted by the vote queues)
//   - scales: bob and carol tip the post's scales (all six shown), seeing a
//     scale's tally only once they've tipped it; bob changes his mind and
//     takes a tip back; tips stay after reloading; alice, the poster, sees
//     the tallies and can't tip; visual_mod sees them without tipping; a
//     visitor is asked to log in
//   - visual_mod, a moderator of the test vault and nothing else: a member's
//     report reaches its reports queue and clears when approved; a comment
//     it removes shows "removed by" to it and vanishes for visitors, and
//     comes back when approved; its own comment is distinguished; locking
//     the thread stops members replying, unlocking lets them; a member it
//     bans can't comment until the ban is lifted; the log lists it all
//   - support: bob and carol write to the admins from the contact page (a
//     question and a privacy request); visual_admin turns on admin mode
//     with a code from its authenticator app (made here from the seed's
//     secret), finds both in /admin/support, takes bob's, leaves a staff
//     note and replies, and lets visual_support (an employee) answer
//     general questions only, who then sees bob's ticket and not carol's;
//     bob's answer comes from the admin team, not a named admin, without
//     the note, and his reply goes back to the ticket
//   - gold: visual_gold filters the test vault out of /all (/me/f/all) and
//     back, and can use the account switcher, which bob, without gold,
//     sees greyed out; a domain listing shows alice's post
//
// On each page: no JavaScript errors, no failed requests to the site, no
// sideways scrolling at phone width, and no text that can't be read on its
// background (faint text is a warning). Screenshots and report.json go to
// VISUAL_OUT; it exits 1 when something failed.
//
// usage: VISUAL_BASE=https://tippr.test VISUAL_SEED=seed.json \
//        [VISUAL_OUT=dir] [VISUAL_RESOLVE=127.0.0.1] [CHROME=path] \
//        [PLAYWRIGHT=path to playwright-core] node docker/visual-test.mjs

import { createHmac } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const BASE = (process.env.VISUAL_BASE || "https://tippr.test").replace(/\/$/, "");
const OUT = process.env.VISUAL_OUT || "visual-results";
const seed = JSON.parse(readFileSync(process.env.VISUAL_SEED || "seed.json", "utf8"));
const VAULT = seed.vault;
const accounts = seed.accounts;
const pw = process.env.PLAYWRIGHT;
const { chromium } = await import(pw ? pathToFileURL(join(pw, "index.mjs")).href : "playwright-core");

const VIEWPORTS = { desktop: { width: 1366, height: 900 }, phone: { width: 390, height: 844 } };
// page loads wait for the page, not the "load" event, which a live comments
// connection can hold up
const READY = { waitUntil: "domcontentloaded" };
// Text contrast against its background (WCAG ratios; its minimum for
// large text is 3:1). Below UNREADABLE the text is as good as invisible (the
// dark theme's black trophy names were about 1.2:1) and the run fails;
// below FAINT it's listed as a warning: reddit's design has pale bits on
// purpose (unvoted scores, ranks), worth improving but not a broken page.
const UNREADABLE = 1.5;
const FAINT = 2.5;

mkdirSync(OUT, { recursive: true });
const failures = [];
const warnings = [];
const shots = [];
function warn(where, what) {
  warnings.push({ where, what });
}
function fail(where, what) {
  failures.push({ where, what });
  console.log(`FAIL ${where}: ${what}`);
}

const host = new URL(BASE).hostname;
const chromeCandidates = [
  process.env.CHROME, "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
].filter(Boolean);
const browser = await chromium.launch({
  executablePath: chromeCandidates.find((p) => existsSync(p)),
  args: process.env.VISUAL_RESOLVE ? [`--host-resolver-rules=MAP ${host} ${process.env.VISUAL_RESOLVE}`] : [],
});

// A browser of its own for each person (logged out: null), at each size.
async function session(name, viewport) {
  const context = await browser.newContext({
    viewport: VIEWPORTS[viewport], ignoreHTTPSErrors: true,
    userAgent: `tippr-visual-test (${viewport})`,
  });
  const page = await context.newPage();
  page.problems = [];
  page.on("pageerror", (e) => page.problems.push("JavaScript error: " + e.message));
  page.on("console", (m) => {
    if (m.type() === "error" && !/Failed to load resource/.test(m.text())) {
      page.problems.push("console error: " + m.text());
    }
  });
  page.on("response", (r) => {
    const url = new URL(r.url());
    if (url.hostname === host && r.status() >= 400 && !url.pathname.startsWith("/api/")) {
      page.problems.push(`${r.status()} for ${url.pathname}`);
    }
  });
  if (name) {
    await page.goto(BASE + "/login", READY);
    await page.fill("#login-form input[name=user]", name);
    await page.fill("#login-form input[name=passwd]", accounts[name].password);
    await Promise.all([page.waitForNavigation(READY), page.click("#login-form button[type=submit]")]);
    const logged = await page.evaluate(() => window.r && r.config && r.config.logged);
    if (logged !== name) throw new Error(`${name} couldn't log in (logged in as ${logged})`);
  }
  return { context, page, name: name || "logged-out", viewport };
}

// What a page shows that a person would notice is wrong.
async function inspect(page, phone) {
  return page.evaluate(({ phone, unreadable, faintBelow }) => {
    const found = [];
    const doc = document.documentElement;
    if (phone && doc.scrollWidth > window.innerWidth + 1) {
      found.push(`scrolls sideways: ${doc.scrollWidth}px wide in a ${window.innerWidth}px window`);
    }
    for (const img of document.images) {
      if (img.complete && img.naturalWidth === 0 && img.getBoundingClientRect().width > 0 && img.src) {
        found.push("broken image: " + img.src);
      }
    }
    const rgba = (s) => (s.match(/[\d.]+/g) || []).map(Number);
    const lum = ([r, g, b]) => {
      const f = (v) => ((v /= 255) <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
      return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
    };
    function background(el) {
      for (; el; el = el.parentElement) {
        const s = getComputedStyle(el);
        if (s.backgroundImage !== "none") return null;  // can't tell over an image
        const c = rgba(s.backgroundColor);
        if (c.length >= 3 && (c.length < 4 || c[3] > 0.5)) return c;
      }
      return [255, 255, 255];
    }
    const faint = new Map();
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let node; (node = walker.nextNode());) {
      if (!node.textContent.trim()) continue;
      const el = node.parentElement;
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      const s = getComputedStyle(el);
      if (s.visibility === "hidden" || +s.opacity === 0) continue;
      if (el.closest("[disabled], .disabled, option, script, style, noscript")) continue;
      const bg = background(el);
      if (!bg) continue;
      const fg = rgba(s.color);
      const a = fg.length >= 4 ? fg[3] : 1;
      if (a === 0) continue;
      const mixed = fg.slice(0, 3).map((v, i) => v * a + bg[i] * (1 - a));
      const [l1, l2] = [lum(mixed), lum(bg)].sort((x, y) => y - x);
      const ratio = (l1 + 0.05) / (l2 + 0.05);
      if (ratio < faintBelow) {
        const text = node.textContent.trim().slice(0, 40);
        const key = `${el.tagName.toLowerCase()}.${[...el.classList].join(".")}`;
        const kind = ratio < unreadable ? "unreadable text" : "faint text";
        if (!faint.has(key) || ratio < faint.get(key).ratio) {
          faint.set(key, { ratio, text: `${kind}: "${text}" (${key}, ${ratio.toFixed(2)}:1)` });
        }
      }
    }
    for (const v of faint.values()) found.push(v.text);
    return found;
  }, { phone, unreadable: UNREADABLE, faintBelow: FAINT });
}

// Check the page, save its screenshot, report what's wrong with it.
async function shoot(s, label) {
  const { page } = s;
  // (pages with live comments or "here now" never go quiet for long)
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => {});
  const name = `${label}-${s.name}-${s.viewport}`;
  const where = `${label} (${s.name}, ${s.viewport})`;
  const problems = [...page.problems, ...(await inspect(page, s.viewport === "phone"))];
  page.problems = [];
  for (const p of problems) (p.startsWith("faint text") ? warn : fail)(where, p);
  const file = name.replace(/[^\w.-]+/g, "_") + ".png";
  await page.screenshot({ path: join(OUT, file), fullPage: true });
  shots.push({ file, page: label, who: s.name, viewport: s.viewport,
               theme: (await page.evaluate(() => document.body.classList.contains("nightmode"))) ? "night" : "light",
               problems });
}

async function check(where, condition, what) {
  try {
    if (!(await condition())) fail(where, what);
  } catch (e) {
    fail(where, `${what} (${e.message.split("\n")[0]})`);
  }
}

// Wait for something the queues do (counting votes, adding comments).
async function eventually(where, what, test, seconds = 90) {
  const deadline = Date.now() + seconds * 1000;
  let last;
  while (Date.now() < deadline) {
    try {
      last = await test();
      if (last === true) return true;
    } catch (e) {
      last = e.message.split("\n")[0];
    }
    await new Promise((r) => setTimeout(r, 3000));
  }
  fail(where, `${what} (last seen: ${last})`);
  return false;
}

// After an action: reload until the page shows its effect, for up to 30
// seconds (another web worker can answer with what it had a moment
// before), and say how long it took when it wasn't straight away.
async function settles(where, what, load, test, seconds = 30) {
  const started = Date.now();
  const ok = await eventually(where, what, async () => {
    await load();
    return (await test()) || "not yet";
  }, seconds);
  const took = Math.round((Date.now() - started) / 1000);
  if (ok && took >= 2) console.log(`${where}: showed after ${took}s`);
}

const thing = (page, fullname) => page.locator(`.thing[data-fullname="${fullname}"]`).first();
const arrows = (page, fullname) => page.locator(`.thing[data-fullname="${fullname}"] > .midcol`).first();
const visibleScore = async (page, fullname, comment) => {
  const scope = comment
    ? page.locator(`.thing[data-fullname="${fullname}"] > .entry .tagline .score`)
    : page.locator(`.thing[data-fullname="${fullname}"] > .midcol .score`);
  for (const el of await scope.all()) {
    if (await el.isVisible()) return (await el.innerText()).trim();
  }
  return null;
};
const voteState = (page, fullname) => arrows(page, fullname).evaluate((m) =>
  m.querySelector(".arrow.upmod") ? "up" : m.querySelector(".arrow.downmod") ? "down" : "none");

async function vote(s, fullname, dir, expect) {
  const where = `${s.name} votes ${dir} on ${fullname}`;
  // at a person's pace: the page drops a vote made within a third of a
  // second of the last one (jquery.tippr.js, rate_limit)
  await s.page.waitForTimeout(600);
  // (and wait for the site to take it: a reload straight after would cancel it)
  await Promise.all([
    s.page.waitForResponse((r) => r.url().includes("/api/vote"), { timeout: 30000 }),
    arrows(s.page, fullname).locator(`.arrow.${dir === "up" ? "up" : "down"}, .arrow.${dir}mod`).first().click(),
  ]);
  await check(where, async () => (await voteState(s.page, fullname)) === expect,
              `the arrows should show "${expect}" straight away, not "${await voteState(s.page, fullname)}"`);
}

// A post's scales panel (scales.js): opened, how many scales show, one
// scale's state, and tipping one (waiting for the site to take it, and for
// the panel to redraw from its answer).
const scaleRow = (s, fullname, scale) =>
  thing(s.page, fullname).locator(`:scope > .entry .scales-panel .scale[data-scale="${scale}"]`);
async function openScales(s, fullname) {
  const t = thing(s.page, fullname);
  if (!(await t.locator(":scope > .entry .scales-panel").count())) {
    await t.locator(":scope > .entry .scales-toggle").first().click();
  }
  await t.locator(":scope > .entry .scales-panel .scale").first().waitFor({ timeout: 30000 });
}
const visibleScales = (s, fullname) =>
  thing(s.page, fullname).locator(":scope > .entry .scales-panel .scale:visible").count();
const scaleState = (s, fullname, scale) => scaleRow(s, fullname, scale).evaluate((row) => ({
  mine: row.querySelector(".scale-tipped .scale-side-label")?.textContent || null,
  tally: row.querySelector(".scale-count").textContent,
  disabled: row.querySelector(".scale-side").disabled,
}));
async function tipScale(s, fullname, scale, side) {
  await Promise.all([
    s.page.waitForResponse((r) => r.url().includes("/api/tip_scale"), { timeout: 30000 }),
    scaleRow(s, fullname, scale).locator(side === "left" ? ".scale-left" : ".scale-right").click(),
  ]);
  await s.page.waitForTimeout(300);
}
async function scaleShows(where, s, fullname, scale, mine, tally) {
  await check(where, async () => {
    const st = await scaleState(s, fullname, scale);
    return st.mine === mine && st.tally === tally;
  }, `"${scale}" should show ${mine ? `"${mine}" tipped` : "no tip"} and the tally "${tally}"`);
}

// A moderator's button on a post or comment ("remove", "lock", ...), with
// its "are you sure?" answered (confirm: the answer's text), waiting for the
// site to take it. (Some buttons have a hidden copy: the visible one is
// used; "approve" on a removed comment is a button, not a link.) It waits
// for the action's own request, /api/<label>: a thread page also posts on
// its own (/api/here_now when it opens, live comments), and taking one of
// those for the action reloaded the page before the action was sent.
// The buttons only work once the page's scripts have run: a page opened
// with READY (the HTML, not yet the scripts) is waited on first, and a click
// that neither asks "are you sure?" nor sends the request is tried again.
async function modAction(s, fullname, label, confirm = "yes") {
  const t = thing(s.page, fullname);
  const endpoint = new RegExp(`/api/${label}(?:[./?]|$)`);
  const isAction = (r) => endpoint.test(r.url()) && r.method() === "POST";
  let sent = false;
  const onRequest = (r) => { if (isAction(r)) sent = true; };
  s.page.on("request", onRequest);
  const done = s.page.waitForResponse((r) => isAction(r.request()), { timeout: 30000 });
  try {
    // (not for ever: a live comments connection can hold "load" up)
    await s.page.waitForLoadState("load", { timeout: 10000 }).catch(() => {});
    const button = t.locator(":scope > .entry :is(a, button):visible", { hasText: new RegExp(`^${label}$`) }).first();
    const answer = t.locator(":scope > .entry .flat-list a:visible", { hasText: new RegExp(`^${confirm}$`) }).first();
    for (let attempt = 0; attempt < 3 && !sent; attempt++) {
      await button.click();
      // the "are you sure?" (most buttons), or the request itself (no question)
      const asked = await answer.waitFor({ state: "visible", timeout: 4000 }).then(() => true, () => false);
      if (asked) {
        await answer.click();
        break;
      }
    }
    await done;
  } finally {
    s.page.off("request", onRequest);
  }
}

// What a page says about a thing: shown at all, its classes, its text.
const seen = (page, fullname) => page.evaluate((fullname) => {
  const t = document.querySelector(`.thing[data-fullname="${fullname}"]`);
  return t ? { classes: t.className, text: t.querySelector(":scope > .entry").innerText.replace(/\s+/g, " ") } : null;
}, fullname);

// Post a comment that may be refused: the error the form shows, or null.
async function tryComment(s, text) {
  const form = s.page.locator(".commentarea > form.usertext").first();
  if (!(await form.count())) return "no comment box";
  await form.locator("textarea[name=text]").fill(text);
  await Promise.all([
    s.page.waitForResponse((r) => r.url().includes("/api/comment"), { timeout: 30000 }),
    form.locator("button.save").first().click(),
  ]);
  await s.page.waitForTimeout(800);
  return form.evaluate((f) => {
    const shown = [...f.querySelectorAll(".error, .status")].filter((e) => e.offsetParent && e.innerText.trim());
    return shown.length ? shown.map((e) => e.innerText.trim()).join(" / ") : null;
  });
}

// The code an authenticator app shows for a base32 secret (RFC 6238, as
// r2/lib/totp.py makes them).
function totp(secret) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const ch of secret.replace(/=+$/, "")) bits += alphabet.indexOf(ch).toString(2).padStart(5, "0");
  const key = Buffer.from(bits.match(/.{8}/g).map((b) => parseInt(b, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 1000 / 30)));
  const hmac = createHmac("sha1", key).update(counter).digest();
  const offset = hmac[hmac.length - 1] & 0x0f;
  return String((hmac.readUInt32BE(offset) & 0x7fffffff) % 1000000).padStart(6, "0");
}

// Write to the admins from the contact page: open the topic, and its link
// opens the message form with the subject filled in.
async function contactAdmins(s, topic, linkText, text) {
  await s.page.goto(`${BASE}/contact`, READY);
  await s.page.getByText(topic, { exact: true }).click();
  await Promise.all([s.page.waitForURL(/\/message\/compose/, READY), s.page.getByText(linkText, { exact: true }).click()]);
  const form = s.page.locator("form#compose-message");
  const subject = await form.locator("input[name=subject]").inputValue();
  await form.locator("textarea[name=text]").fill(text);
  await Promise.all([
    s.page.waitForResponse((r) => r.url().includes("/compose"), { timeout: 30000 }),
    form.locator("button#send").click(),
  ]);
  await check(`${s.name} writes to the admins`, async () =>
    /delivered/.test(await form.locator(".status").innerText().catch(() => "")),
    "the form should say the message was delivered");
  return subject;
}

let post;  // the post's fullname (tippr's posts are t1_, not reddit's t3_)
async function comment(s, parentFullname, text) {
  const { page } = s;
  let form;
  if (parentFullname === post) {
    form = page.locator(".commentarea > form.usertext").first();
  } else {
    // made since this page loaded: reload, as a person would, until the
    // comment tree queue has added it (a few seconds)
    for (let i = 0; i < 20 && !(await thing(page, parentFullname).count()); i++) {
      await new Promise((r) => setTimeout(r, 3000));
      await page.reload(READY);
    }
    await thing(page, parentFullname).locator("> .entry .flat-list a", { hasText: /^reply$/ }).first().click();
    form = thing(page, parentFullname).locator("> .child form.usertext").first();
  }
  await form.locator("textarea[name=text]").fill(text);
  await form.locator("button[type=submit].save, .usertext-buttons button.save").first().click();
  // the comment whose own text it is (not a parent's, which holds its
  // replies' text too)
  const first = text.split("\n")[0];
  const find = () => page.evaluate((first) => {
    for (const el of document.querySelectorAll(".thing.comment")) {
      const md = el.querySelector(":scope > .entry .md");
      if (md && md.textContent.includes(first)) return el.getAttribute("data-fullname");
    }
    return null;
  }, first);
  for (let i = 0; i < 30; i++) {
    const fullname = await find();
    if (fullname) return fullname;
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`${s.name}'s comment didn't appear: ${first}`);
}

try {
  // logged out
  for (const viewport of Object.keys(VIEWPORTS)) {
    const s = await session(null, viewport);
    for (const [label, path] of [["front", "/"], ["vault", `/v/${VAULT}/`], ["login", "/login"]]) {
      await s.page.goto(BASE + path, READY);
      await shoot(s, label);
    }
    await s.context.close();
  }

  // alice posts, through the submit form
  const alice = await session("visual_alice", "desktop");
  const title = `Visual test ${new Date().toISOString().slice(0, 16)}`;
  await alice.page.goto(`${BASE}/v/${VAULT}/submit?selftext=true`, READY);
  await shoot(alice, "submit");
  await alice.page.fill("#newlink textarea[name=title]", title);
  await alice.page.fill("#newlink textarea[name=text]",
    "A post made by the release's browser test.\n\n* a list\n* with items\n\n" +
    "Some `inline code`, a [link](https://example.com) and a longer paragraph that wraps " +
    "across the width of the page so line spacing and wrapping can be seen at both sizes.");
  await alice.page.check("#newlink input[name=ai_content][value=human]");
  await Promise.all([
    alice.page.waitForURL(/\/comments\//, { timeout: 60000 }),
    alice.page.click("#newlink button[name=submit]"),
  ]);
  const postUrl = alice.page.url();
  post = await alice.page.locator(".thing.link").first().getAttribute("data-fullname");
  console.log(`alice posted ${postUrl} (${post})`);

  const bob = await session("visual_bob", "desktop");
  const carol = await session("visual_carol", "desktop");
  const dave = await session("visual_dave", "desktop");
  for (const s of [bob, carol, dave]) await s.page.goto(postUrl, READY);

  // a thread four replies deep, and a second top-level comment
  const c1 = await comment(bob, post, "First! A top-level comment from bob.");
  const c2 = await comment(carol, c1, "A reply from carol, in night mode.");
  const c3 = await comment(dave, c2, "dave replies to carol, a level further in.");
  const c4 = await comment(alice, c3, "And the post's author answers, four levels deep.");
  const c5 = await comment(carol, post,
    "A second top-level comment with a longer body, so it wraps:\n\n" +
    "> a quote\n\n    some code\n    on two lines\n\nand a closing line.");
  console.log(`comments ${c1} ${c2} ${c3} ${c4} ${c5}`);

  // votes on the post: bob up, carol up, dave down; bob takes his back and
  // gives it again
  for (const s of [bob, carol, dave]) await s.page.reload(READY);
  await vote(bob, post, "up", "up");
  await vote(carol, post, "up", "up");
  await vote(dave, post, "down", "down");
  await vote(bob, post, "up", "none");
  await vote(bob, post, "up", "up");
  // on bob's comment: carol and dave up, alice down then changes her mind
  await alice.page.reload(READY);
  await vote(carol, c1, "up", "up");
  await vote(dave, c1, "up", "up");
  await vote(alice, c1, "down", "down");
  await vote(alice, c1, "up", "up");
  // carol's comment: dave down
  await vote(dave, c2, "down", "down");

  // each vote stays after reloading
  const expected = [[bob, post, "up"], [carol, post, "up"], [dave, post, "down"],
                    [carol, c1, "up"], [dave, c1, "up"], [alice, c1, "up"], [dave, c2, "down"]];
  for (const s of [alice, bob, carol, dave]) await s.page.reload(READY);
  for (const [s, fullname, want] of expected) {
    await check(`${s.name}'s vote on ${fullname} after reloading`,
                async () => (await voteState(s.page, fullname)) === want, `should show "${want}"`);
  }

  // the scores follow, once the vote queues have counted them: the post
  // 1 + 2 - 1 (its score is shown only to its author in its first hours),
  // bob's comment 1 + 3, carol's 1 - 1
  await eventually("post score (as alice)", "the post's score should become 2", async () => {
    await alice.page.reload(READY);
    return (await visibleScore(alice.page, post, false)) === "2" || await visibleScore(alice.page, post, false);
  });
  await eventually("comment scores (as bob)", "bob's comment should have 4 points and carol's 0", async () => {
    await bob.page.reload(READY);
    const a = await visibleScore(bob.page, c1, true), b = await visibleScore(bob.page, c2, true);
    return (a === "4 points" && b === "0 points") || `${a} / ${b}`;
  });

  // ---- scales: members tip the post toward what it's like ----
  // bob and carol see all six scales and no tallies until they tip; bob
  // changes his mind and takes a tip back; tips stay after reloading;
  // alice, the poster, sees the tallies and can't tip (fewer than three tips
  // are listed, not drawn as a bar)
  await openScales(bob, post);
  await check("scales (as bob)", async () => (await visibleScales(bob, post)) === 6,
              "all six scales should show");
  await check("scales before tipping (as bob)", async () => (await scaleState(bob, post, "made")).tally === "",
              "the tally should be hidden until he tips");
  await tipScale(bob, post, "made", "left");
  await scaleShows("bob tips human-made", bob, post, "made", "human-made", "1 tip so far: human-made");
  await openScales(carol, post);
  await check("scales before tipping (as carol)", async () => (await scaleState(carol, post, "made")).tally === "",
              "bob's tip shouldn't show until she tips");
  await tipScale(carol, post, "made", "right");
  await scaleShows("carol tips AI-generated", carol, post, "made", "AI-generated",
                   "2 tips so far: 1 human-made, 1 AI-generated");
  await tipScale(carol, post, "tone", "left");
  await scaleShows("carol tips matter-of-fact", carol, post, "tone", "matter-of-fact",
                   "1 tip so far: matter-of-fact");
  await shoot(carol, "scales");
  await tipScale(bob, post, "made", "right");
  await scaleShows("bob changes to AI-generated", bob, post, "made", "AI-generated",
                   "2 tips so far: AI-generated");
  await tipScale(bob, post, "made", "right");
  await scaleShows("bob takes his tip back", bob, post, "made", null, "");
  await tipScale(bob, post, "made", "left");
  await bob.page.reload(READY);
  await openScales(bob, post);
  await scaleShows("bob's tip after reloading", bob, post, "made", "human-made",
                   "2 tips so far: 1 human-made, 1 AI-generated");
  await shoot(bob, "scales");
  await openScales(alice, post);
  await check("scales (as alice, the poster)", async () => {
    const s = await scaleState(alice, post, "made");
    return s.tally === "2 tips so far: 1 human-made, 1 AI-generated" && s.disabled;
  }, "she should see the tally and not be able to tip");
  const passerby = await session(null, "desktop");
  await passerby.page.goto(postUrl, READY);
  await thing(passerby.page, post).locator(":scope > .entry .scales-toggle").first().click();
  await passerby.page.waitForTimeout(1000);
  await check("scales (logged out)", async () =>
    !(await passerby.page.locator(".scales-panel").count()) &&
    (await passerby.page.locator(".login-popup:visible, .modal:visible").count()) > 0,
    "a visitor should be asked to log in, not shown the scales");
  await passerby.context.close();

  // ---- moderation: visual_mod moderates /v/visualtest and nothing else ----
  const mod = await session("visual_mod", "desktop");
  const visitor = await session(null, "desktop");
  const fresh = (s) => s.page.goto(`${postUrl}?t=${Date.now()}`, READY);  // past any page cache

  // the vault's moderator sees the scales' tallies without tipping
  await fresh(mod);
  await openScales(mod, post);
  await check("scales (as visual_mod)", async () => {
    const s = await scaleState(mod, post, "made");
    return (s.mine === null && s.tally === "2 tips so far: 1 human-made, 1 AI-generated") || JSON.stringify(s);
  }, "a moderator should see the tally without tipping");

  // a member's report reaches the moderator, who approves it from the queue
  await carol.page.reload(READY);
  {
    const t = thing(carol.page, c3);
    await t.locator(":scope > .entry .flat-list a", { hasText: /^report$/ }).first().click();
    const form = t.locator("form.report-action-form").first();
    await form.locator("input[name=reason][value=\"Spam or vote manipulation\"]").check();
    await Promise.all([
      carol.page.waitForResponse((r) => r.url().includes("/api/report"), { timeout: 30000 }),
      form.locator("button.submit-action-thing").click(),
    ]);
  }
  await eventually("reports queue (as visual_mod)", "carol's report should be in the queue", async () => {
    await mod.page.goto(`${BASE}/v/${VAULT}/about/reports/`, READY);
    return (await thing(mod.page, c3).count()) > 0 || "not there";
  });
  await shoot(mod, "mod-reports");
  if (await thing(mod.page, c3).count()) {
    await modAction(mod, c3, "approve");
    await mod.page.reload(READY);
    await check("reports queue after approving", async () => !(await thing(mod.page, c3).count()),
                "the approved comment should have left the queue");
  }

  // remove a comment: the moderator sees why, nobody else sees it; approve
  // brings it back
  await mod.page.goto(postUrl, READY);
  await modAction(mod, c5, "remove");
  await mod.page.reload(READY);
  await check("removed comment (as visual_mod)", async () => /removed by visual_mod/.test((await seen(mod.page, c5) || {}).text || ""),
              'the moderator should see "removed by visual_mod" on it');
  await shoot(mod, "thread-removed");
  await settles("removed comment (logged out)", "visitors shouldn't see it", () => fresh(visitor),
                async () => !(await seen(visitor.page, c5)));
  await modAction(mod, c5, "approve");
  await settles("approved comment (logged out)", "visitors should see it again", () => fresh(visitor),
                async () => !!(await seen(visitor.page, c5)));

  // a moderator's comment, distinguished as the moderator's
  const note = await comment(mod, post, "Moderator note: please keep the discussion civil.");
  await mod.page.reload(READY);
  await modAction(mod, note, "distinguish");
  await settles("distinguished comment (logged out)", "it should be marked as a moderator's", () => fresh(visitor),
                async () => (await thing(visitor.page, note).locator(":scope > .entry .tagline .moderator").count()) > 0);
  await shoot(visitor, "thread-mod-note");

  // lock the thread: members are told, and can't reply (the reply links stay,
  // as the kind that explains it's locked); unlock and they can
  await mod.page.reload(READY);
  await modAction(mod, post, "lock");
  await settles("locked thread (as visual_bob)",
                "members should be told it's locked, with no comment box and no working reply links",
                () => bob.page.reload(READY), async () =>
    (await bob.page.getByText("This post is locked").count()) > 0 &&
    !(await bob.page.locator(".commentarea > form.usertext").count()) &&
    !(await bob.page.locator(".thing.comment > .entry .flat-list a:not(.locked-error)", { hasText: /^reply$/ }).count()));
  await shoot(bob, "thread-locked");
  await shoot(mod, "thread-locked");
  await mod.page.reload(READY);
  await modAction(mod, post, "unlock");
  {
    const started = Date.now();
    if (await eventually("unlocked thread (as visual_bob)", "members should have the comment box again", async () => {
      await bob.page.reload(READY);
      return (await bob.page.locator(".commentarea > form.usertext").count()) > 0 || "no comment box";
    }, 30)) console.log(`unlocked thread: the comment box was back after ${Math.round((Date.now() - started) / 1000)}s`);
  }

  // ban dave from the vault: his comment is refused; lift it and he can again
  await mod.page.goto(`${BASE}/v/${VAULT}/about/banned/`, READY);
  {
    const form = mod.page.locator("form#banned");
    await form.locator("input[name=name]").fill("visual_dave");
    await form.locator("input[name=note]").fill("browser test");
    await form.locator("input[name=duration]").fill("1");
    await form.locator("textarea[name=ban_message]").fill("A one-day ban from the browser test.");
    await Promise.all([
      mod.page.waitForResponse((r) => r.url().includes("/api/friend"), { timeout: 30000 }),
      form.locator("button[type=submit], input[type=submit]").first().click(),
    ]);
  }
  await mod.page.reload(READY);
  await check("banned list", async () => (await mod.page.locator("table, .usertable, #banned-table").filter({ hasText: "visual_dave" }).count()) > 0,
              "visual_dave should be on the banned list");
  await shoot(mod, "mod-banned");
  await dave.page.goto(postUrl, READY);
  const refused = await tryComment(dave, "A comment while banned.");
  await check("banned member's comment", async () => !!refused, "it should be refused");
  console.log(`banned dave's comment: ${refused}`);
  await shoot(dave, "thread-banned");
  {
    const row = mod.page.locator("tr", { hasText: "visual_dave" }).first();
    await Promise.all([
      mod.page.waitForResponse((r) => r.url().includes("/api/unfriend"), { timeout: 30000 }),
      (async () => {
        await row.locator("a", { hasText: /^remove$/ }).first().click();
        await mod.page.waitForTimeout(400);
        const yes = row.locator(".option.active a", { hasText: /^yes$/ });
        if (await yes.count()) await yes.first().click();
      })(),
    ]);
  }
  await dave.page.reload(READY);
  await check("unbanned member's comment", async () => (await tryComment(dave, "Back after the ban was lifted.")) === null,
              "it should be accepted");

  // the moderation log has all of it
  await mod.page.goto(`${BASE}/v/${VAULT}/about/log/`, READY);
  const log = await mod.page.evaluate(() => (document.querySelector(".modactionlisting") || document.body).innerText);
  for (const [what, pattern] of [["the removal", /remove/i], ["the approval", /approve/i], ["the lock", /lock/i],
                                 ["the ban", /ban/i], ["the distinguish", /distinguish/i]]) {
    await check("moderation log", async () => pattern.test(log), `it should list ${what}`);
  }
  await shoot(mod, "mod-log");
  for (const label of ["mod-log", "mod-reports"]) {
    const s = await session("visual_mod", "phone");
    await s.page.goto(`${BASE}/v/${VAULT}/about/${label === "mod-log" ? "log" : "reports"}/`, READY);
    await shoot(s, label);
    await s.context.close();
  }
  await visitor.context.close();

  // ---- support: members write to the admins, staff answer ----
  // bob asks a general question, carol makes a privacy request, both from
  // the contact page
  const bobSubject = await contactAdmins(bob, "message the admins", "Send the admins a message",
                                         "Hello admins, a question from the browser test.");
  const carolSubject = await contactAdmins(carol, "privacy and your data", "Send a privacy request",
                                           "A privacy request from the browser test.");
  await shoot(bob, "contact-sent");

  // the admin turns on admin mode (a code from the app, not the password
  // again) and finds both in the queue
  const admin = await session("visual_admin", "desktop");
  await admin.page.goto(`${BASE}/adminon?dest=${encodeURIComponent("/admin/support")}`, READY);
  await shoot(admin, "adminon");
  await admin.page.fill("#adminon input[name=otp]", totp(accounts.visual_admin.totp));
  await Promise.all([admin.page.waitForURL(/\/admin\/support/, { timeout: 30000, ...READY }),
                     admin.page.click("#adminon button[type=submit]")]);
  const ticketLink = (page, subject) => page.locator("a", { hasText: subject.replace(/^\[\w+\]\s*/, "") }).first();
  await eventually("support queue (as visual_admin)", "both requests should be in the queue", async () => {
    await admin.page.goto(`${BASE}/admin/support?view=all`, READY);
    const found = [await ticketLink(admin.page, bobSubject).count(), await ticketLink(admin.page, carolSubject).count()];
    return (found[0] > 0 && found[1] > 0) || `found ${found}`;
  });
  await shoot(admin, "support-queue");

  // bob's ticket: take it, a note for the staff, a reply as the admin team
  await ticketLink(admin.page, bobSubject).click();
  await admin.page.waitForLoadState("domcontentloaded");
  const ticketUrl = admin.page.url();
  const post_ = (action) => admin.page.waitForResponse((r) => r.url().includes(`/api/${action}`), { timeout: 30000 });
  // (taking, notes and replies reload the ticket page themselves)
  const andReload = (action, click) => Promise.all([post_(action), admin.page.waitForNavigation(READY), click]);
  await andReload("support_assign", admin.page.getByRole("button", { name: "take this" }).click());
  const staffNote = "Staff only: checked the account, nothing unusual.";
  await admin.page.fill("form.support-note-form textarea[name=note]", staffNote);
  await andReload("support_note", admin.page.click("form.support-note-form button"));
  const answer = "Thanks for writing. This is the admin team's answer from the browser test.";
  const replyForm = admin.page.locator("form[action='/api/support_reply']");
  await replyForm.locator("textarea[name=text]").fill(answer);
  await andReload("support_reply", replyForm.locator("button[type=submit]").click());
  await check("support ticket (as visual_admin)", async () => {
    const text = await admin.page.locator(".content").first().innerText();
    return text.includes(staffNote) && text.includes(answer);
  }, "the ticket should show the staff note and the reply");
  await shoot(admin, "support-ticket");

  // the admin lets visual_support read and answer general questions only
  await admin.page.goto(`${BASE}/admin/support/staff`, READY);
  {
    const form = admin.page.locator("form.support-staff-form", { has: admin.page.locator("input[name=username][value=visual_support]") });
    await form.locator("select[name=perm_general]").selectOption("reply");
    await Promise.all([post_("support_staff"), form.locator("button[type=submit]").click()]);
  }
  await admin.page.reload(READY);
  await shoot(admin, "support-staff");

  // visual_support (an employee with two-factor on) sees bob's general
  // question, not carol's privacy request
  const helper = await session("visual_support", "desktop");
  await helper.page.goto(`${BASE}/admin/support?view=all`, READY);
  await check("support queue (as visual_support)", async () =>
    (await ticketLink(helper.page, bobSubject).count()) > 0 && !(await ticketLink(helper.page, carolSubject).count()),
    "an employee allowed general questions should see bob's and not carol's privacy request");
  await shoot(helper, "support-queue");
  await helper.context.close();

  // bob gets the answer from the admin team, not from a named admin, and
  // without the staff note; his reply goes back to the ticket
  await eventually("bob's inbox", "the admins' answer should arrive", async () => {
    await bob.page.goto(`${BASE}/message/inbox/`, READY);
    return (await bob.page.getByText(answer).count()) > 0 || "not there";
  });
  await check("bob's inbox", async () => {
    const text = await bob.page.locator(".content").first().innerText();
    return !text.includes("visual_admin") && !text.includes(staffNote);
  }, "the answer shouldn't name the admin or show the staff note");
  await shoot(bob, "inbox-answer");
  {
    const msg = bob.page.locator(".thing.message", { hasText: answer }).first();
    await msg.locator(":scope > .entry .flat-list a", { hasText: /^reply$/ }).first().click();
    const form = msg.locator("form.usertext").first();
    await form.locator("textarea[name=text]").fill("Thanks, that answers it.");
    await Promise.all([bob.page.waitForResponse((r) => r.url().includes("/api/comment"), { timeout: 30000 }),
                       form.locator("button.save").first().click()]);
  }
  await eventually("support ticket after bob's reply", "his reply should be on the ticket", async () => {
    await admin.page.goto(ticketUrl, READY);
    return (await admin.page.getByText("Thanks, that answers it.").count()) > 0 || "not there";
  });
  await admin.context.close();

  // gold's pages, as visual_gold: filtered /all (/me/f/all), filtering the
  // test vault out and back; the account switcher in preferences, which
  // bob, without gold, sees greyed out
  const gold = await session("visual_gold", "desktop");
  await gold.page.goto(`${BASE}/me/f/all`, READY);
  await shoot(gold, "filtered-all");
  await check("filtered /all (visual_gold)",
              async () => (await gold.page.locator(".filtered-details").count()) > 0,
              "the page should have the box for the vaults filtered out");
  const filtered = (page) => page.locator(`.filtered-details .vaults li[data-name="${VAULT}"]`);
  await gold.page.fill(".filtered-details .add-vault .vault-name", VAULT);
  await gold.page.click(".filtered-details .add-vault button.add");
  await settles("filtered /all (visual_gold)", `${VAULT} should be filtered out, and alice's post with it`,
    () => gold.page.goto(`${BASE}/me/f/all?t=${Date.now()}`, READY),
    async () => (await filtered(gold.page).count()) > 0 && (await thing(gold.page, post).count()) === 0);
  await shoot(gold, "filtered-all-vault");
  await filtered(gold.page).locator(".remove-vault").click();
  await settles("filtered /all (visual_gold)", `${VAULT} should be back`,
    () => gold.page.goto(`${BASE}/me/f/all?t=${Date.now()}`, READY),
    async () => (await filtered(gold.page).count()) === 0);
  await gold.page.goto(`${BASE}/prefs/`, READY);
  await check("preferences (visual_gold)",
              async () => !(await gold.page.locator("input#account_switcher").isDisabled()),
              "a gold member should be able to turn the account switcher on");
  await shoot(gold, "prefs");
  await bob.page.goto(`${BASE}/prefs/`, READY);
  await check("preferences (visual_bob)",
              async () => await bob.page.locator("input#account_switcher").isDisabled(),
              "the account switcher is for gold members: bob's should be greyed out");
  await gold.context.close();

  // a domain listing: alice's post, a text post, under self.<vault>
  // (domain listings once redirected to a broken address)
  await settles("domain listing", "alice's post should be listed under its domain",
    () => bob.page.goto(`${BASE}/domain/self.${VAULT}/?t=${Date.now()}`, READY),
    async () => (await thing(bob.page, post).count()) > 0, 90);
  await shoot(bob, "domain-listing");
  await bob.page.goto(postUrl, READY);  // (the thread, next)

  // the thread, as each of them sees it (their own votes on the arrows)
  for (const s of [alice, bob, carol, dave]) {
    await s.page.reload(READY);
    await shoot(s, "thread");
  }
  // and the rest at phone width, in both themes, and logged out
  for (const [name, label, path] of [
    ["visual_alice", "thread", postUrl], ["visual_carol", "thread", postUrl],
    ["visual_alice", "vault", `/v/${VAULT}/`], ["visual_carol", "vault", `/v/${VAULT}/`],
    ["visual_carol", "profile", "/user/visual_carol/"], ["visual_alice", "prefs", "/prefs/"],
    [null, "thread", postUrl],
  ]) {
    const s = await session(name, "phone");
    await s.page.goto(path.startsWith("http") ? path : BASE + path, READY);
    await shoot(s, label);
    await s.context.close();
  }
  for (const [s, label, path] of [[carol, "profile", "/user/visual_carol/"], [alice, "prefs", "/prefs/"],
                                  [carol, "vault", `/v/${VAULT}/`]]) {
    await s.page.goto(BASE + path, READY);
    await shoot(s, label);
  }
  const outsider = await session(null, "desktop");
  await outsider.page.goto(postUrl, READY);
  await shoot(outsider, "thread");
} catch (e) {
  fail("test run", e.stack || e.message);
} finally {
  await browser.close();
}

writeFileSync(join(OUT, "report.json"), JSON.stringify({ base: BASE, failures, warnings, shots }, null, 1));
const faintKinds = new Set(warnings.map((w) => w.what.replace(/^faint text: "[^"]*" /, "")));
if (faintKinds.size) {
  console.log("warnings (faint text, see report.json):");
  for (const kind of faintKinds) console.log("  " + kind);
}
console.log(`${shots.length} screenshots in ${OUT}; ${failures.length} problem(s), ${warnings.length} warning(s)`);
process.exit(failures.length ? 1 : 0);

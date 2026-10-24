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
//
//   - alice logs in through the login form and posts through the submit form
//   - bob, carol and dave log in, and reply to each other down a thread
//   - they vote on the post and the comments, change and undo votes; the
//     arrows must show each voter's vote at once and after reloading, and
//     the scores must follow (votes are counted by the vote queues)
//
// On each page: no JavaScript errors, no failed requests to the site, no
// sideways scrolling at phone width, and no text that can't be read on its
// background (faint text is a warning). Screenshots and report.json go to VISUAL_OUT; it exits 1 when
// something failed.
//
// usage: VISUAL_BASE=https://tippr.test VISUAL_SEED=seed.json \
//        [VISUAL_OUT=dir] [VISUAL_RESOLVE=127.0.0.1] [CHROME=path] \
//        [PLAYWRIGHT=path to playwright-core] node docker/visual-test.mjs

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
    await Promise.all([page.waitForNavigation(), page.click("#login-form button[type=submit]")]);
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

# Content: default vaults, feeds, scales, reports and AI labels

## Starter vaults

The installer runs `scripts/create_default_vaults.py`, which creates a
starter set of vaults owned and moderated by the admin account, and makes
some of them the front page defaults (what logged-out and new users see).

- Only vaults with starter feeds are defaults, so a newcomer's front page
  has no empty vaults: technology, programming, linux, selfhosted,
  cybersecurity, privacy, electronics, mechanicalkeyboards, science, space,
  gaming, cozygaming, retrogaming, anime, diy, fiberarts, thrift,
  3dprinting, food, art, music, photography, writing, aesthetics, pics,
  aww, books, comics, memes, popculture, movies, til, skincare and lgbtq.
- lgbtq is a default on purpose: tippr is meant to be a welcoming site for
  LGBTQ+ people, and the content policy bans hate based on sexual
  orientation and gender identity. dragrace exists too, but isn't a
  default.
- The rest exist without being defaults: the site's own community vaults,
  which have no feeds (tippr, asktippr), heavy news (news, worldnews,
  politics, business), and more specialised ones
  (devops, ainews, gis, marketing, sports, podcasts, videos, blogs,
  curated, design). aiart and aimusic are for AI-generated work, so art
  and music can stay human-made.

The script is safe to re-run (the installer runs it on every install and
upgrade): existing vaults are left as their moderators set them, the default
list is set when the site has none yet, and after that only defaults new to
the list are added, so a default an admin took off stays off
(`TIPPR_RESET_DEFAULTS=1` replaces the defaults with the list). Edit
the `VAULTS` list in the script to change what a new install gets. Admins
can add or remove defaults on /admin/vaults; `scripts/prune_default_vaults.py`
takes every default without a feed off the list (`PRUNE_DRY_RUN=1` to
preview).

## Feeds

Vaults can fill themselves from RSS and Atom feeds (/admin/feeds): every
15 minutes `tippr-job-feeds` checks the feeds that are due and posts their
new items into each feed's vault, from a bot account, with an optional
title prefix such as `[NASA]`. A feed can also mark every post it makes
NSFW and give them an AI label (human-made, AI-assisted or AI-generated,
one the vault accepts); in a list for `import_feeds.py`, put `nsfw` or
`ai:generated` (etc.) on the feed's line. `scripts/starter_feeds.txt` lists public
feeds for the starter vaults. The installer adds them on a new site
(`TIPPR_STARTER_FEEDS`: `auto`, the default, adds them on a new site and
keeps the site's choice after that; `1` turns them on, `0` off), and on
upgrades adds the feeds new to the list since the last run. Feeds an admin
removed from /admin/feeds aren't added back. To add from a list yourself,

```bash
FEEDS_ADD=1 tippr-run $TIPPR_HOME/src/tippr/scripts/import_feeds.py
```

adds them (without `FEEDS_ADD=1` it only lists what it would add). It's
safe to re-run: feeds already on a vault are skipped. Feed posts get
thumbnails like any link post.

On /admin/feeds, feeds are listed newest first; search them, filter them
by vault, bot or status (active, paused, with errors, never checked), sort
by any column, and edit one in place. Changing a feed's vault sends its new
items there; posts it already made stay where they are.

The reports column counts the reports made on each feed's posts, by reason
(the rule reported, or "other" for a reporter's own words), so a feed that
keeps getting reported for the same thing stands out; sort by it to see the
most reported first. Counts include reports a moderator later dismissed. To
count reports made before the column existed:
`tippr-run -c 'from r2.lib import feeds; print(feeds.recount_reports())'`
(which counts every reason as written, "other" ones too).

Deleting a feed asks what happens to its posts: kept (the default), the
ones nobody voted on or commented on deleted too, or all of them. They
go as the post cleanup deletes posts: as their author would, with the
images no other post uses, and listed under recent cleanups on
/admin/cleanup. Up to 200 go at once; until the rest have (tippr-job-feeds
deletes 200 more every 15 minutes), the feed stays on the page, paused
and marked as being deleted, and then it goes.

The votes column adds up the votes and comments on each feed's posts that
are still up: upvotes besides the bot's own, downvotes, comments, and the
share of its posts that got a vote or a comment at all. Sort by comments
or interest from its heading; interest goes least first, so the feeds
nobody reads (and whose posts the post cleanup would take) come to the
top. `tippr-job-feed_stats` adds them up each hour from the posts
themselves, so a vote changed or taken back counts as it stands. To count
now: `tippr-run -c 'from r2.lib import feeds; print(feeds.recount_stats())'`.

Members can leave the feed bots' posts out altogether: "hide posts by the
site's feed bots" under content options on /prefs (`pref_hide_feed_bots`,
off by default). Like the AI preference, it applies to listings and search,
not to a post opened directly. The bots are the accounts on /admin/feeds,
looked up again every five minutes. On a site where feeds post most of what
there is, it can leave listings nearly empty.

Each run posts its new items one vault at a time in turn (and within a
vault, one feed at a time), so a run doesn't post a block of one vault's
items. The front page and multis mix vaults anyway; /v/all ranks every post together, so its hot list also
keeps two posts from one vault apart while another vault's post is close
behind.

## Scales and reports

**Scales** describe what kind of post it is, not how good it is (votes say
that). Each is two ends of one difference, and a member tips it toward a
side, changes their mind or takes the tip back:

| Scale | Sides |
|---|---|
| made | human-made, AI-generated |
| depth | quick overview, deep dive |
| nature | practical, thought piece |
| evidence | data-driven, personal experience |
| tone | matter-of-fact, passionate |
| scope | niche, broad |

A scale's tally shows once the member has tipped it, so the first tips
don't steer everyone else; "see the results" shows them all, at the price
of tipping that post. The poster, the vault's moderators and admins (in
admin mode) see every tally. Fewer than three tips are listed rather than
drawn as a bar. Scales don't rank posts or go to moderators. Tips are kept
in PostgreSQL (`scale_tips`) and are in members' data exports
(`r2/lib/scales.py`).

**Reports** go to the vault's moderators. The reasons follow the
[content policy](policies/CONTENT_POLICY.md): spam or vote manipulation,
harassment or threats, hateful content, someone's personal information,
sexual content involving minors, other illegal content, impersonation,
malware, phishing or scams, breaking the site's rules, and "other" with a
short note. A vault's own rules come first. A report keeps its reason in
English, and moderators see it in their own language
(`r2/models/rules.py`).

## AI content labels

Every new post says how much AI went into it, chosen on the submit form:

| Label | Meaning |
|---|---|
| human-made | made by people, without AI |
| AI-assisted | made by people with some AI help (editing, fixes, ideas) |
| AI-generated | mostly or entirely made by AI |

AI-assisted and AI-generated posts show a small label next to the title.
Posts from before labels existed are unlabelled and treated as not AI. The
label comes from the poster; nothing tries to detect AI. The author, the
vault's moderators and admins can correct it with the post's "AI label"
button.

**Vault policy** (vault settings, "AI content"):

- any posts (labelled): the default
- no AI-generated posts: human-made and AI-assisted
- AI-assisted and AI-generated posts only

The author is held to the vault's policy when posting or relabelling;
moderators can set any label.

**User preference** (preferences, "content options"):

- show everything (with labels): the default
- hide AI-generated posts
- hide AI-generated and AI-assisted posts

Hidden posts are left out of listings and search. People always see their
own posts, and posts in an AI-only vault are always shown in that vault:
visiting one is a choice to see them.

**API:** `POST /api/submit` takes `ai_content` (`human`, `assisted` or
`generated`) and requires it. `POST /api/set_ai_label` changes it (`id`,
`ai_content`). Post JSON has `ai_content` (null when unlabelled).

**Search:** `ai:human`, `ai:assisted`, `ai:generated`, `ai:yes` (either AI
label) and `ai:no`; see [SEARCH.md](SEARCH.md).

# Default vaults and AI content labels

## Starter vaults

The installer runs `scripts/create_default_vaults.py`, which creates a
starter set of vaults owned and moderated by the admin account, and makes
most of them the front page defaults (what logged-out and new users see).

- Defaults lean toward technology, science, making things and fun:
  technology, programming, linux, selfhosted, electronics, science, space,
  diy, 3dprinting, gaming, retrogaming, anime, art, music, photography,
  writing, books, movies, food, pics, funny, aww, til, asktippr, lgbtq and
  tippr.
- lgbtq is a default on purpose: tippr is meant to be a welcoming site for
  LGBTQ+ people, and the content policy bans hate based on sexual
  orientation and gender identity. dragrace exists too, but isn't a
  default.
- news, worldnews and politics exist but aren't defaults. They don't fill
  the front page unless people subscribe.
- aiart and aimusic are for AI-generated work, so art and music can stay
  human-made. They aren't defaults either.

The script is safe to re-run: existing vaults are left as their moderators
set them, and the default list is only set when the site has none yet. Edit
the `VAULTS` list in the script to change what a new install gets.

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

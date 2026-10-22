# AutoModerator

AutoModerator checks every new post and comment in a vault against rules its moderators write, and acts on the ones that match: removing spam, flagging posts for a moderator to look at, setting flair, replying with a note, and so on. It only does anything in vaults that have rules; a vault without them is never touched.

## Where the rules go

Moderators with the "wiki" permission write the rules on the vault's wiki page **config/automoderator**: go to `/v/yourvault/wiki/config/automoderator` and edit it. Only moderators can see the page. When you save, the rules are checked, and a mistake is pointed out instead of saved. New rules apply to posts and comments made after you save; they don't go back over old ones.

Rules are written in [YAML](https://yaml.org/). Each rule is a list of settings, and rules are separated by a line of three dashes:

    # remove links to a spam site
    domain: spamsite.example
    action: remove
    action_reason: "spam domain"
    ---
    # hold posts from brand-new accounts for a moderator to look at
    type: submission
    author:
        account_age: "< 1 day"
    action: filter
    action_reason: "new account"

Lines starting with `#` are notes for you, and AutoModerator ignores them.

## Which items a rule looks at

- `type`: `any` (the default), `submission`, `text submission`, `link submission` or `comment`.
- `priority`: a number. Rules with a higher priority are checked first; the default is 0.
- `moderators_exempt`: `true` or `false`. Moderators' posts are skipped by rules that remove, filter or report, unless you say otherwise.

## Checks

A rule's checks must **all** match for it to act.

**Text in the post or comment.** The field name, and what to look for. Several values in a list match if **any** of them is there:

    title: [free, giveaway, "click here"]

- On submissions: `title`, `body` (a text post's text), `url`, `domain`, `flair_text`, `flair_css_class`, `id`, and for embedded media `media_author`, `media_author_url`, `media_title` and `media_description`.
- On comments: `body`, `id`.
- Several fields at once, joined with `+`: `title+body: [discount]`.
- `~` in front means **doesn't** match: `~domain: [example.com]`.

How the text is searched, in parentheses after the field name, e.g. `title (starts-with): "[meta]"`:

- `includes-word` (the default for most fields): the words appear on their own.
- `includes` (the default for `url`): anywhere, even inside other words.
- `starts-with`, `ends-with`, `full-exact` (the whole text, exactly), `full-text` (the whole text, ignoring punctuation around it).
- `regex`: the value is a regular expression. Use single quotes around it.
- `case-sensitive`: capitals matter, which they don't otherwise.

**Other checks on the post or comment:**

- `reports`: at least this many reports (the rule is checked again when one comes in).
- `body_longer_than`, `body_shorter_than`: the length of the text, in characters.
- `ignore_blockquotes: true`: leave quoted text out when looking at `body`.
- `is_edited`: `true` or `false`.
- `is_top_level` (comments): `true` for replies to the post itself, not to other comments.

**Checks on the author**, inside `author:`:

    author:
        post_karma: "< 5"
        comment_karma: "< 5"
        account_age: "< 3 days"
        satisfy_any_threshold: true

- `post_karma`, `comment_karma`, `combined_karma`: a number with `<`, `>` or `==` in front.
- `account_age`: a number of `minutes`, `hours`, `days`, `weeks`, `months` or `years`, with `<` or `>`.
- `satisfy_any_threshold: true`: any **one** of the karma and age checks is enough, instead of all of them.
- `is_gold`, `is_submitter` (the comment's author also made the post), `is_contributor` (an approved submitter), `is_moderator`: `true` or `false`.
- `name`, `flair_text`, `flair_css_class`: text, like the fields above.

**Checks on the post a comment is in**, inside `parent_submission:`, with the submission fields above:

    type: comment
    parent_submission:
        flair_text: "Announcement"
    action: remove

## Actions

What happens when everything matches:

- `action`:
  - `remove`: takes it down; moderators find it in the removed queue.
  - `spam`: takes it down as spam.
  - `filter`: takes it down until a moderator approves it, and keeps it in the moderation queue.
  - `report`: reports it to the moderators.
  - `approve`: approves it, for example from a trusted author.
- `action_reason`: the reason shown in the moderation log and on the report.
- `comment`: AutoModerator replies to it with this text (`comment_stickied: true` pins the reply on a post).
- `message`: sends the author a private message (`message_subject` sets its subject).
- `modmail`: sends the vault's moderators a message (`modmail_subject` sets its subject).
- On submissions:
  - `set_flair`: text, or a list of [text, css class].
  - `overwrite_flair: true`: replaces flair that's already set.
  - `set_nsfw`, `set_locked` (no new comments), `set_contest_mode`: `true` or `false`.
  - `set_sticky`: `true`, or which slot.
  - `set_suggested_sort`: `top`, `new`, `old`, `qa`, `confidence` and so on.
- `author:` can take `set_flair` too, for the member's user flair in the vault.

Replies and messages to the author end with a note that AutoModerator is a bot, with a link to message the moderators; messages to the moderators start with a link to the post or comment.

## Placeholders

In `comment`, `message`, `modmail`, their subjects and `action_reason`, these are filled in:

- `{{author}}`, `{{vault}}`, `{{kind}}` (submission or comment), `{{title}}`, `{{body}}`, `{{permalink}}`, `{{url}}` and `{{domain}}`.
- `{{author_flair_text}}` and `{{author_flair_css_class}}`.
- `{{match}}`: the text that matched (with several checks, `{{match-title}}`, `{{match-body}}` and the like).

## Examples

Reply to every new post with a reminder of the rules:

    type: submission
    comment: |
        Thanks for posting, {{author}}! Please make sure your post follows the
        rules in the sidebar.

Report posts that collect three reports, so they're easy to find:

    reports: 3
    action: filter
    modmail: "{{permalink}} has 3 reports and is waiting in the queue."

Mark posts with "nsfw" in the title as NSFW:

    type: submission
    title: [nsfw, "18+"]
    set_nsfw: true

Remove comments that only say "first":

    type: comment
    body (full-text): ["first", "first!"]
    action: remove
    action_reason: "low effort"

## Tips

- Start with `action: report` or `filter` rather than `remove` until you're sure a rule only catches what you mean.
- The moderation log shows every action AutoModerator takes, with the reason you gave.
- AutoModerator acts as its own account. Its replies and messages come from it, not from a moderator.
- Something wrong with how AutoModerator behaves on the site itself? [Tell the admins](/contact#moderators).

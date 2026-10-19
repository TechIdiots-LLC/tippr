# Using the API

{{SITE_NAME}} has an API for programs, bots and apps: most of what you can do on the site, you can do through it. The reference is at [/dev/api](/dev/api).

## Registering an app

Apps sign in with OAuth2, as the members who authorize them. Register yours under [preferences, apps](/prefs/apps). To keep spam bots out, registering usually needs an account that's been around for a little while, has some karma and has a verified email address. A new app may need approval from the admins before anyone but its own developers can use it; until then it works for its developers only.

## The rules

- **Identify yourself.** Send a User-Agent header that names your app, its version and your username, like `myapp/1.2 (by /user/yourname)`. Generic or fake browser User-Agents may be blocked.
- **Mind the rate limit.** Each OAuth client can make a few hundred requests every 10 minutes (about one every two seconds on average). Every response tells you where you are: `X-Ratelimit-Used`, `X-Ratelimit-Remaining`, and `X-Ratelimit-Reset` (seconds until the count starts over). Slow down when the remaining number gets low; going over gets you HTTP 429 errors.
- **Don't spam or manipulate.** Bots must not vote, post the same thing in many places, or act for people who haven't authorized them. Everything in the [user agreement](/help/useragreement) and [content policy](/help/contentpolicy) applies to bots too.
- **Say you're a bot.** A bot account's name or profile should make clear it's a bot, and it should reply only where it's wanted (many vaults have rules about bots).
- **Respect deletions.** If you keep copies of posts or comments, remove them when they're deleted on the site.
- **Keep secrets secret.** Your app's secret and members' tokens are passwords: never publish them.

Apps that break these rules can be suspended, which stops their tokens working at once.

## Without signing in

Listings, posts and comments can be read as JSON by adding `.json` to their address (for example /v/books/.json), within the same rate limit. For simply following new posts, [RSS feeds](/help/rss) are easier.

Questions? [Message the admins](/contact#message-the-admins).

# RSS feeds

Most listings on {{SITE_NAME}} have an RSS feed you can follow in a feed reader: add `.rss` to the end of the address.

| address | feed |
|---|---|
| `/.rss` | the front page |
| `/v/books/.rss` | a vault's hot posts |
| `/v/books/new/.rss` | a vault's newest posts |
| `/v/books/comments/.rss` | a vault's newest comments |
| `/user/name/submitted/.rss` | a member's posts |
| `/domain/example.com/.rss` | links to a site |
| `/search.rss?q=words` | a search |

A post's comments have a feed too: add `.rss` to the post's address.

## Private feeds

Some feeds are about your account: your front page as you see it, your inbox, and your saved posts. Their addresses include a secret key, so anyone with the address can read them. Find them under [preferences, RSS feeds](/prefs/feeds); if one leaks, you can make new ones there, which stops the old addresses working.

Feeds of things only moderators see (a vault's modqueue, banned users …) need such a key too.

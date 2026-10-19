# Searching

The search box finds posts by their title, text, flair and address. Type words to match any of them, or put a phrase in "double quotes" to match it exactly. Searching inside a vault looks in that vault only; tick or untick "limit my search to /v/…" to change that.

## Narrowing a search

Add any of these to the words you search for:

| search for | finds |
|---|---|
| `vault:books` | posts in /v/books |
| `author:name` | posts by /user/name |
| `site:example.com` | links to example.com (and its subdomains) |
| `url:word` | links whose address contains "word" |
| `title:word` | posts with "word" in the title |
| `selftext:word` | text posts with "word" in their text |
| `flair:meta` | posts with the flair "meta" |
| `self:yes` or `self:no` | only text posts, or only links |
| `nsfw:yes` or `nsfw:no` | only, or no, posts marked NSFW |

Put a minus sign in front of one to exclude it: `-vault:politics` leaves out /v/politics.

For example, `vault:aww site:imgur.com dog` finds dog pictures on imgur posted in /v/aww, and `"raspberry pi" -author:somebody` finds posts mentioning the Raspberry Pi that aren't by /user/somebody.

## Sorting

Results can be sorted by relevance, by what's hot now, by top votes, by newest, or by most comments, and limited to the past hour, day, week, month or year.

## Finding vaults

Searching from the [vaults page](/vaults/) looks for vaults by name and description instead of posts.

# Formatting posts and comments

{{SITE_NAME}} uses Markdown, a way of writing formatting with plain characters. It follows [CommonMark](https://commonmark.org), the standard most sites use, with GitHub's tables, strikethrough and task lists, and a few additions of our own. The buttons above the text box add it for you, and "preview" shows how it will look.

## Text

| you type | you get |
|---|---|
| `*italics*` or `_italics_` | *italics* |
| `**bold**` | **bold** |
| `~~struck out~~` | ~~struck out~~ |
| `super^script` or `^(several words)` | super^script |
| `` `code` `` | `code` |
| `>!a spoiler!<` | a spoiler, hidden until clicked |
| `:tada:` | an emoji (the 🙂 button lists them) |

Emoji and every language's letters can also be typed or pasted directly.

## Links

Paste an address (starting `https://` or `www.`) and it becomes a link. To link words instead, write `[the words](https://example.com)`; `[the words](example.com)` works too.

Vaults and members link on their own: /v/books, v/books, /u/name and u/name. Mentioning a member this way in a comment lets them know (unless they've turned that off in their preferences).

A picture's address can be linked the same way, `![a description](https://example.com/picture.png)`: it shows as a link to the picture, with the description as its words.

## Paragraphs and lines

Leave a blank line between paragraphs. A single line break is ignored; to break a line without starting a new paragraph, end it with two spaces or a backslash (`\`).

## Lists

    * one item
    * another item

    1. first
    2. second

Indent a line under an item to put a list inside it.

### Task lists

    - [ ] still to do
    - [x] done

show as ☐ still to do and ☑ done.

## Quotes

Start a line with `>` to quote it:

    > what someone else said

Put `>>` for a quote inside a quote.

## Code blocks

Put a line of three backticks before and after some lines to show them exactly as typed, in a fixed-width font. A language after the first backticks (` ```python `) names it. Lines indented by four spaces work too.

    ```
    if a < b:
        print("hello")
    ```

## Tables

    | column | another | numbers |
    |:---|:---:|---:|
    | a | b | 1 |

Colons in the line under the headings line a column up on the left, in the middle or on the right.

## Headings and lines

`# Heading`, `## Smaller heading` and so on make headings: put a space after the `#`s (`#1` on its own stays as typed). A line of `***` or `---` draws a horizontal rule.

## Showing the characters themselves

Put a backslash before a character to stop it formatting: `\*not italic\*`. HTML is shown as typed, not used.

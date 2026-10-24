# The contents of this file are subject to the Common Public Attribution
# License Version 1.0. (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# https://github.com/TechIdiots-LLC/tippr/blob/master/LICENSE.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is Tippr.
#
# The Initial Developer of the Original Code is TechIdiots LLC.
# Copyright (c) 2026 TechIdiots LLC. All Rights Reserved.
###############################################################################
"""Markdown for posts, comments, messages and the wiki.

CommonMark (markdown-it-py) with GitHub's tables, ~~strikethrough~~, task
lists and bare links, plus tippr's own: super^script and ^(several words),
>!spoilers!<, and /v/vault, /u/user links. Raw HTML is never let through,
and the output is XHTML that r2.lib.souptest accepts: only its tags,
attributes and link schemes.
"""

import re

from markdown_it import MarkdownIt
from markdown_it.common.utils import escapeHtml
from markdown_it.rules_block import blockquote as _blockquote
from markdown_it.token import Token

from r2.lib.souptest import valid_link_schemes


# characters XML can't hold, even as references (souptest would refuse the
# page); typed or pasted text sometimes has them
_xml_unsafe_re = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ud800-\udfff￾￿]")

_scheme_re = re.compile(r"\A[a-z][a-z0-9+.\-]*:", re.I)
# [a link](example.com): a site's address without https://
_bare_domain_re = re.compile(
    r"\A(?:www\.)?[a-z0-9\-]+(?:\.[a-z0-9\-]+)*\.[a-z]{2,}(?:[/?#].*)?\Z", re.I)
# a wiki stylesheet image, ![](%%name%%) (r2.lib.filters.wikimarkdown)
_wiki_image_re = re.compile(r"\A%%[a-zA-Z0-9\-]+%%\Z")

# /v/vault, v/vault (and /v/one+two), /u/user, u/user and /user/user, not
# inside a word or a path; names as r2.models.vault.vault_rx and
# r2.lib.validator.user_rx allow
_mention_re = re.compile(
    r"(?<![\w/])"
    r"(?P<all>/?(?:(?P<vkind>v)/(?P<vault>[A-Za-z0-9][A-Za-z0-9_]{1,20}"
    r"(?:\+[A-Za-z0-9][A-Za-z0-9_]{1,20})*)"
    r"|(?P<ukind>u|user)/(?P<user>[\w\-]{2,20})))"
    r"(?![\w\-])")

_task_re = re.compile(r"\A\[([ xX])\][ \t]+")
TASK_OPEN = "☐"  # ☐
TASK_DONE = "☑"  # ☑


def _validate_link(url):
    if _scheme_re.match(url):
        return url.lower().startswith(valid_link_schemes)
    return url.startswith(("/", "#")) or bool(_wiki_image_re.match(url))


def _make_normalize_link(normalize):
    def normalize_link(url):
        url = url.strip()
        if _wiki_image_re.match(url):
            return url
        if not _scheme_re.match(url) and _bare_domain_re.match(url):
            url = "https://" + url
        return normalize(url)
    return normalize_link


def _spoiler_line(state, line):
    pos = state.bMarks[line] + state.tShift[line]
    end = state.eMarks[line]
    return (state.src.startswith(">!", pos) and
            state.src.find("!<", pos + 2, end) != -1)


def blockquote(state, startLine, endLine, silent):
    """A line that starts >!spoiler!< is a paragraph, not a quote."""
    if _spoiler_line(state, startLine):
        return False
    return _blockquote(state, startLine, endLine, silent)


# how deep spoilers and superscripts nest (^a^b^c...), and how far ^( looks
# for its ), so no text makes rendering slow
MAX_NESTING = 8
MAX_SUPERSCRIPT_PARENS = 200


def _too_deep(state):
    return state.env.get("tippr_nesting", 0) >= MAX_NESTING


def _tokenize_between(state, start, end):
    # as its own text: markdown-it's text rule reads past a shortened posMax
    tokens = []
    env = state.env
    env["tippr_nesting"] = env.get("tippr_nesting", 0) + 1
    try:
        state.md.inline.parse(state.src[start:end], state.md, env, tokens)
    finally:
        env["tippr_nesting"] -= 1
    state.tokens.extend(tokens)


def spoiler(state, silent):
    """>!hidden until clicked!<"""
    start = state.pos
    if not state.src.startswith(">!", start) or _too_deep(state):
        return False
    close = state.src.find("!<", start + 2, state.posMax)
    if close == -1 or not state.src[start + 2:close].strip():
        return False
    if not silent:
        token = state.push("spoiler_open", "span", 1)
        token.attrSet("class", "md-spoiler-text")
        token.markup = ">!"
        _tokenize_between(state, start + 2, close)
        state.push("spoiler_close", "span", -1).markup = "!<"
    state.pos = close + 2
    return True


def superscript(state, silent):
    """super^script, to the next space, or ^(several words)"""
    src, start, end = state.src, state.pos, state.posMax
    if src[start] != "^" or start + 1 >= end or _too_deep(state):
        return False
    if src[start + 1] == "(":
        depth = 0
        i = start + 1
        while i < min(end, start + 2 + MAX_SUPERSCRIPT_PARENS):
            ch = src[i]
            if ch == "\\":
                i += 2
                continue
            if ch == "\n":
                return False
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        else:
            return False
        content_start, content_end, after = start + 2, i, i + 1
    else:
        # to the next space, or to an emphasis mark it didn't open (the end
        # of *a^b*); ^**bold** opens its own
        i = start + 1
        while i < end and not src[i].isspace():
            if (src[i] in "*_~" and i > start + 1 and
                    src[i] not in src[start + 1:i]):
                break
            i += 1
        content_start, content_end, after = start + 1, i, i
    if content_end <= content_start:
        return False
    if not silent:
        state.push("sup_open", "sup", 1).markup = "^"
        _tokenize_between(state, content_start, content_end)
        state.push("sup_close", "sup", -1).markup = "^"
    state.pos = after
    return True


def _mention_tokens(text, level):
    tokens = []
    last = 0
    for m in _mention_re.finditer(text):
        if m.start() > last:
            t = Token("text", "", 0)
            t.content = text[last:m.start()]
            tokens.append(t)
        if m.group("vault"):
            href = "/v/" + m.group("vault")
        else:
            href = "/u/" + m.group("user")
        link = Token("link_open", "a", 1, attrs={"href": href}, level=level)
        link.markup = link.info = "auto"
        label = Token("text", "", 0, level=level + 1)
        label.content = m.group("all")
        tokens += [link, label, Token("link_close", "a", -1, level=level)]
        last = m.end()
    if last < len(text):
        t = Token("text", "", 0)
        t.content = text[last:]
        tokens.append(t)
    return tokens


def _bare_word_link(token, label):
    """A link linkify made of a word with a dot (README.md, example.com),
    not an address with http(s):// or www., or an email address."""
    return (token.markup == "linkify" and
            not (token.attrGet("href") or "").startswith("mailto:") and
            "://" not in label and not label.lower().startswith("www."))


def mentions(state):
    """Link /v/vault and /u/user written in the text, and unlink words
    such as README.md that bare-link detection took for addresses."""
    for block in state.tokens:
        if block.type != "inline" or not block.children:
            continue
        children = []
        in_link = 0
        unlinking = False
        for i, token in enumerate(block.children):
            if token.type == "link_open":
                label = (block.children[i + 1].content
                         if i + 1 < len(block.children) else "")
                if _bare_word_link(token, label):
                    unlinking = True
                    continue
                in_link += 1
            elif token.type == "link_close":
                if unlinking:
                    unlinking = False
                    continue
                in_link -= 1
            if (token.type == "text" and not in_link and
                    "/" in token.content and _mention_re.search(token.content)):
                children += _mention_tokens(token.content, token.level)
            else:
                children.append(token)
        block.children = children


def task_lists(state):
    """- [ ] to do / - [x] done, shown as ☐ and ☑."""
    tokens = state.tokens
    for i, token in enumerate(tokens):
        if token.type != "list_item_open" or i + 2 >= len(tokens):
            continue
        inline = tokens[i + 2]
        if (tokens[i + 1].type != "paragraph_open" or inline.type != "inline"
                or not inline.children or inline.children[0].type != "text"):
            continue
        first = inline.children[0]
        m = _task_re.match(first.content)
        if not m:
            continue
        box = TASK_OPEN if m.group(1) == " " else TASK_DONE
        first.content = box + " " + first.content[m.end():]
        token.attrSet("class", "md-task")


def html_tags(state):
    """The tags souptest allows: align="..." on table cells instead of a
    style attribute, and <del> for ~~strikethrough~~ (not <s>)."""
    for token in state.tokens:
        for child in token.children or ():
            if child.tag == "s":
                child.tag = "del"
        if token.type in ("th_open", "td_open") and token.attrs.get("style"):
            style = token.attrs.pop("style")
            align = style.split(":", 1)[-1].strip()
            if align in ("left", "center", "right"):
                token.attrs["align"] = align


def _link_attrs(token, env):
    href = token.attrGet("href") or ""
    if env.get("nofollow") and _scheme_re.match(href):
        token.attrSet("rel", "nofollow")
    if env.get("target"):
        token.attrSet("target", env["target"])


def render_link_open(self, tokens, idx, options, env):
    _link_attrs(tokens[idx], env)
    return self.renderToken(tokens, idx, options, env)


def render_image(self, tokens, idx, options, env):
    """Pictures only in the wiki (its own uploaded ones); elsewhere
    ![words](address) is a link to the picture."""
    token = tokens[idx]
    if env.get("wiki"):
        token.attrSet("alt", self.renderInlineAsText(token.children,
                                                     options, env))
        return self.renderToken(tokens, idx, options, env)
    link = Token("link_open", "a", 1, attrs={"href": token.attrGet("src")})
    if token.attrGet("title"):
        link.attrSet("title", token.attrGet("title"))
    _link_attrs(link, env)
    label = self.renderInline(token.children, options, env) if \
        token.children else escapeHtml(token.attrGet("src"))
    return self.renderToken([link], 0, options, env) + label + "</a>"


def _build():
    md = MarkdownIt("commonmark", {
        "html": False,
        "linkify": True,
        "xhtmlOut": True,
        "typographer": False,
    })
    md.enable(["table", "strikethrough", "linkify"])
    md.validateLink = _validate_link
    md.normalizeLink = _make_normalize_link(md.normalizeLink)

    md.block.ruler.at("blockquote", blockquote,
                      {"alt": ["paragraph", "reference", "blockquote", "list"]})
    md.inline.ruler.before("emphasis", "tippr_spoiler", spoiler)
    md.inline.ruler.before("emphasis", "tippr_superscript", superscript)
    md.core.ruler.push("tippr_mentions", mentions)
    md.core.ruler.push("tippr_task_lists", task_lists)
    md.core.ruler.push("tippr_html_tags", html_tags)
    md.add_render_rule("link_open", render_link_open)
    md.add_render_rule("image", render_image)
    return md


_md = _build()


def render(text, nofollow=False, target=None, wiki=False):
    """Markdown text as HTML (a str)."""
    if not text:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    text = _xml_unsafe_re.sub("", text)
    env = {"nofollow": nofollow, "target": target, "wiki": wiki}
    return _md.render(text, env)

"""X (Twitter) handler — uses fxtwitter API for tweet, thread, and X Article extraction.

X is JS-rendered and login-gated, so direct scraping returns a page shell. The
fxtwitter API (api.fxtwitter.com) acts as an unauthenticated proxy that returns
clean JSON metadata for any public tweet or thread.

For X Articles (long-form posts), the tweet's `text` is empty and the actual
content lives in `tweet.article.content.blocks` as a Draft.js-style block array.
"""

from __future__ import annotations

import html as html_lib
import re
from urllib.parse import urlparse

import httpx

from .base import BaseHandler, ExtractResult

_X_HOSTS = {
    "x.com",
    "www.x.com",
    "twitter.com",
    "www.twitter.com",
    "mobile.twitter.com",
}
# Matches /<user>/status/<id> and /i/status/<id>; captures the numeric id.
_STATUS_PATH_RE = re.compile(r"^/(?:[^/]+/)?status(?:es)?/(\d+)")
_FXTWITTER_API = "https://api.fxtwitter.com"
# fxtwitter's API is fronted by Cloudflare and challenges non-browser UAs.
_FX_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


class XHandler(BaseHandler):
    @classmethod
    def matches(cls, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc.lower() not in _X_HOSTS:
            return False
        return bool(_STATUS_PATH_RE.match(parsed.path))

    async def extract(self, url: str) -> ExtractResult:
        m = _STATUS_PATH_RE.match(urlparse(url).path)
        if not m:
            return ExtractResult(strategy="fxtwitter-miss")
        status_id = m.group(1)

        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            single = await self._fetch_single(client, status_id)
            if not single:
                return ExtractResult(strategy="fxtwitter-fail")

            # X Article (long-form post) — render the article body directly.
            article = single.get("article")
            if isinstance(article, dict) and article.get("content"):
                return _render_article(single, article)

            # Plain tweet — try to fetch the full thread if there is one.
            tweets = await self._fetch_thread(client, status_id) or [single]

        return _render_tweets(tweets)

    async def _fetch_thread(
        self, client: httpx.AsyncClient, status_id: str
    ) -> list[dict] | None:
        try:
            resp = await client.get(
                f"{_FXTWITTER_API}/status/{status_id}/thread",
                headers=_FX_HEADERS,
            )
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        try:
            data = resp.json()
        except ValueError:
            return None
        if data.get("code") != 200:
            return None
        tweets = (data.get("thread") or {}).get("tweets")
        return tweets if isinstance(tweets, list) and tweets else None

    async def _fetch_single(
        self, client: httpx.AsyncClient, status_id: str
    ) -> dict | None:
        try:
            resp = await client.get(
                f"{_FXTWITTER_API}/status/{status_id}",
                headers=_FX_HEADERS,
            )
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        try:
            data = resp.json()
        except ValueError:
            return None
        if data.get("code") != 200:
            return None
        tweet = data.get("tweet")
        return tweet if isinstance(tweet, dict) else None


def _render_article(tweet: dict, article: dict) -> ExtractResult:
    """Render an X Article (long-form post) from its Draft.js-style block content."""
    author = _format_author(tweet.get("author") or {})
    title = (article.get("title") or "").strip() or "X Article"
    published_date = (article.get("created_at") or tweet.get("created_at") or "")[:10] or None

    blocks = (article.get("content") or {}).get("blocks") or []
    html_parts: list[str] = []
    text_parts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        btype = block.get("type") or "unstyled"
        text = block.get("text") or ""
        if btype == "atomic" or not text.strip():
            continue
        styled_html = _apply_inline_styles(text, block.get("inlineStyleRanges") or [])
        if btype == "header-one":
            html_parts.append(f"<h1>{styled_html}</h1>")
        elif btype == "header-two":
            html_parts.append(f"<h2>{styled_html}</h2>")
        elif btype == "header-three":
            html_parts.append(f"<h3>{styled_html}</h3>")
        elif btype == "blockquote":
            html_parts.append(f"<blockquote><p>{styled_html}</p></blockquote>")
        elif btype == "unordered-list-item":
            html_parts.append(f"<li>{styled_html}</li>")
        elif btype == "ordered-list-item":
            html_parts.append(f"<li>{styled_html}</li>")
        else:
            html_parts.append(f"<p>{styled_html}</p>")
        text_parts.append(text)

    return ExtractResult(
        title=title,
        author=author,
        published_date=published_date,
        content_html="\n".join(html_parts),
        content_text="\n\n".join(text_parts),
        strategy="fxtwitter-article",
        force_confident=True,
    )


def _apply_inline_styles(text: str, ranges: list) -> str:
    """Wrap byte ranges with <strong>/<em>/<u> tags from Draft.js inlineStyleRanges."""
    if not ranges:
        return html_lib.escape(text)

    style_tags = {"BOLD": "strong", "ITALIC": "em", "UNDERLINE": "u"}
    # Build a per-character set of active styles
    chars = list(text)
    active: list[set[str]] = [set() for _ in chars]
    for r in ranges:
        if not isinstance(r, dict):
            continue
        style = (r.get("style") or "").upper()
        tag = style_tags.get(style)
        if not tag:
            continue
        offset = int(r.get("offset") or 0)
        length = int(r.get("length") or 0)
        for i in range(offset, min(offset + length, len(chars))):
            active[i].add(tag)

    out: list[str] = []
    open_tags: list[str] = []
    for i, ch in enumerate(chars):
        want = active[i] if i < len(active) else set()
        # Close any tags no longer active (in reverse open order)
        while open_tags and open_tags[-1] not in want:
            out.append(f"</{open_tags.pop()}>")
        # Open any newly active tags
        for tag in sorted(want):
            if tag not in open_tags:
                out.append(f"<{tag}>")
                open_tags.append(tag)
        out.append(html_lib.escape(ch))
    while open_tags:
        out.append(f"</{open_tags.pop()}>")
    return "".join(out)


def _render_tweets(tweets: list[dict]) -> ExtractResult:
    first = tweets[0]
    author = _format_author(first.get("author") or {})
    published_date = (first.get("created_at") or "")[:10] or None

    first_text = (first.get("text") or "").strip()
    first_line = first_text.split("\n", 1)[0].strip()
    if len(tweets) > 1:
        title = first_line[:80] or f"Thread by {author or 'X user'}"
    else:
        title = first_line[:80] or f"Tweet by {author or 'X user'}"

    html_parts: list[str] = []
    text_parts: list[str] = []
    for t in tweets:
        text = (t.get("text") or "").strip()
        if not text:
            continue
        ts = t.get("created_at") or ""
        html_parts.append("<article class='tweet'>")
        if ts:
            html_parts.append(
                f"<p class='tweet-meta'><em>{html_lib.escape(ts)}</em></p>"
            )
        for para in text.split("\n\n"):
            para = para.strip()
            if not para:
                continue
            escaped = html_lib.escape(para).replace("\n", "<br>")
            html_parts.append(f"<p>{escaped}</p>")
        html_parts.append("</article>")
        text_parts.append(text)

    return ExtractResult(
        title=title,
        author=author,
        published_date=published_date,
        content_html="\n".join(html_parts),
        content_text="\n\n".join(text_parts),
        strategy="fxtwitter-thread" if len(tweets) > 1 else "fxtwitter-tweet",
        force_confident=True,
    )


def _format_author(author_obj: dict) -> str | None:
    name = (author_obj.get("name") or "").strip()
    screen = (author_obj.get("screen_name") or "").strip()
    if name and screen:
        return f"{name} (@{screen})"
    if name:
        return name
    if screen:
        return f"@{screen}"
    return None

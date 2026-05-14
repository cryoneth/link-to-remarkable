"""Medium handler — uses RSS feed for clean extraction."""

from __future__ import annotations

import re
from urllib.parse import urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup

from .base import BaseHandler, ExtractResult

_MEDIUM_HOST_RE = re.compile(r"(^|\.)(medium\.com)$")
# Medium post URL: /username/slug-hashid  OR  /p/hashid  OR  /publication/slug
_MEDIUM_POST_RE = re.compile(r"/[^/]+/[^/]+-([0-9a-f]{8,12})$")


class MediumHandler(BaseHandler):
    @classmethod
    def matches(cls, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return bool(_MEDIUM_HOST_RE.search(host))

    async def extract(self, url: str) -> ExtractResult:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        path = parsed.path.rstrip("/")

        # Try to derive RSS feed URL.
        # medium.com/@username/... → feed URL is medium.com/feed/@username
        # medium.com/publication/... → medium.com/feed/publication
        rss_url = _derive_rss_url(host, path)

        feed_content = None
        if rss_url:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                try:
                    r = await client.get(rss_url)
                    if r.status_code == 200:
                        feed_content = r.text
                except httpx.HTTPError:
                    pass

        # If we couldn't derive RSS, look for it in the HTML
        if not feed_content:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                try:
                    page_r = await client.get(url)
                    if page_r.status_code == 200:
                        rss_url = _find_rss_from_html(page_r.text, url)
                        if rss_url:
                            r2 = await client.get(rss_url)
                            if r2.status_code == 200:
                                feed_content = r2.text
                except httpx.HTTPError:
                    pass

        if not feed_content:
            return ExtractResult(strategy="medium-rss-miss")

        feed = feedparser.parse(feed_content)
        entry = _find_matching_entry(feed, url)
        if not entry:
            return ExtractResult(strategy="medium-rss-no-match")

        title = entry.get("title", "")
        author = entry.get("author") or None
        # feedparser returns published_parsed as time.struct_time; use it for
        # reliable ISO formatting regardless of the raw RFC 822 string format.
        parsed_time = entry.get("published_parsed") or entry.get("updated_parsed")
        if parsed_time:
            published_date = f"{parsed_time.tm_year:04d}-{parsed_time.tm_mon:02d}-{parsed_time.tm_mday:02d}"
        else:
            published_date = None

        body_html = ""
        for content in entry.get("content", []):
            if content.get("type") == "text/html":
                body_html = content.get("value", "")
                break
        if not body_html:
            body_html = entry.get("summary", "")

        content_text = BeautifulSoup(body_html, "lxml").get_text(separator="\n", strip=True)

        return ExtractResult(
            title=title,
            author=author,
            published_date=published_date,
            content_html=body_html,
            content_text=content_text,
            strategy="medium-rss",
        )


def _derive_rss_url(host: str, path: str) -> str | None:
    # medium.com/@username or medium.com/@username/slug
    m = re.match(r"^/(@[^/]+)", path)
    if m:
        return f"https://{host}/feed/{m.group(1)}"
    # medium.com/publication/slug
    m = re.match(r"^/([^/@][^/]+)/", path)
    if m:
        return f"https://{host}/feed/{m.group(1)}"
    return None


def _find_rss_from_html(html: str, page_url: str) -> str | None:
    soup = BeautifulSoup(html[:16384], "lxml")
    for link in soup.find_all("link", rel="alternate", type="application/rss+xml"):
        href = link.get("href", "")
        if href:
            if href.startswith("/"):
                parsed = urlparse(page_url)
                href = f"{parsed.scheme}://{parsed.netloc}{href}"
            return href
    return None


def _find_matching_entry(feed: feedparser.FeedParserDict, url: str) -> dict | None:
    # Normalize URL for comparison: strip fragment, trailing slash, and query
    norm_url = url.split("#")[0].split("?")[0].rstrip("/")
    for entry in feed.entries:
        entry_link = (entry.get("link") or "").split("#")[0].split("?")[0].rstrip("/")
        if entry_link == norm_url:
            return entry
    return None

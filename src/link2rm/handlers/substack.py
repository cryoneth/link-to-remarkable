"""Substack handler — uses the post JSON API for clean full-text extraction."""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from .base import BaseHandler, ExtractResult

# Substack post URLs look like:
#   https://authorname.substack.com/p/post-slug
#   https://www.customdomain.com/p/post-slug  (custom domain Substack)
_SUBSTACK_HOST_RE = re.compile(r"\.substack\.com$")
_POST_PATH_RE = re.compile(r"^/p/([^/?#]+)")


def _is_substack_domain(host: str) -> bool:
    return bool(_SUBSTACK_HOST_RE.search(host))


def _looks_like_substack_custom_domain(html: str) -> bool:
    """Detect custom-domain Substack blogs via meta tags."""
    if not html:
        return False
    lower = html[:4096].lower()
    return "substack.com" in lower and 'name="generator"' in lower


class SubstackHandler(BaseHandler):
    @classmethod
    def matches(cls, url: str) -> bool:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if _is_substack_domain(host) and _POST_PATH_RE.match(parsed.path):
            return True
        return False

    async def extract(self, url: str) -> ExtractResult:
        parsed = urlparse(url)
        m = _POST_PATH_RE.match(parsed.path)
        if not m:
            return ExtractResult(strategy="substack-api-miss")

        slug = m.group(1)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        api_url = f"{origin}/api/v1/posts/{slug}"

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(api_url, headers={"Accept": "application/json"})
            if resp.status_code != 200:
                return ExtractResult(strategy="substack-api-fail")
            data = resp.json()

        title = data.get("title") or data.get("name") or ""
        author = _extract_author(data)
        published_date = _extract_date(data)
        body_html = data.get("body_html") or data.get("bodyHtml") or ""

        if not body_html:
            return ExtractResult(strategy="substack-api-empty")

        content_text = BeautifulSoup(body_html, "lxml").get_text(separator="\n", strip=True)

        return ExtractResult(
            title=title,
            author=author,
            published_date=published_date,
            content_html=body_html,
            content_text=content_text,
            strategy="substack-api",
        )


def _extract_author(data: dict) -> str | None:
    # Various shapes Substack API returns author info
    authors = data.get("publishedBylines") or data.get("authors") or []
    if authors and isinstance(authors, list):
        names = [a.get("name") or a.get("displayName") for a in authors if isinstance(a, dict)]
        names = [n for n in names if n]
        if names:
            return ", ".join(names)
    byline = data.get("byline") or data.get("authorName")
    return byline or None


def _extract_date(data: dict) -> str | None:
    raw = data.get("post_date") or data.get("publishedAt") or data.get("published_at")
    if raw:
        return raw[:10]  # YYYY-MM-DD
    return None

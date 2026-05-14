"""arXiv handler — uses the arXiv API for metadata + sets passthrough PDF URL."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import httpx

from .base import BaseHandler, ExtractResult

_ARXIV_RE = re.compile(
    r"arxiv\.org/(?:abs|pdf|html)/([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)",
    re.IGNORECASE,
)
_ARXIV_OLD_RE = re.compile(
    r"arxiv\.org/(?:abs|pdf)/([a-z\-]+(?:\.[A-Z]+)?/[0-9]+(?:v[0-9]+)?)",
    re.IGNORECASE,
)
_NS = "http://www.w3.org/2005/Atom"
_API_URL = "https://export.arxiv.org/api/query"


class ArXivHandler(BaseHandler):
    @classmethod
    def matches(cls, url: str) -> bool:
        return bool(_ARXIV_RE.search(url) or _ARXIV_OLD_RE.search(url))

    async def extract(self, url: str) -> ExtractResult:
        arxiv_id = _extract_id(url)
        if not arxiv_id:
            return ExtractResult(strategy="arxiv-id-miss")

        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            r = await client.get(_API_URL, params={"id_list": arxiv_id, "max_results": 1})
            if r.status_code != 200:
                return ExtractResult(strategy="arxiv-api-fail")

        root = ET.fromstring(r.text)
        entry = root.find(f"{{{_NS}}}entry")
        if entry is None:
            return ExtractResult(strategy="arxiv-api-no-entry")

        title = _text(entry, f"{{{_NS}}}title") or ""
        title = " ".join(title.split())  # collapse whitespace
        abstract = _text(entry, f"{{{_NS}}}summary") or ""
        abstract = " ".join(abstract.split())

        authors = [
            _text(a, f"{{{_NS}}}name") or ""
            for a in entry.findall(f"{{{_NS}}}author")
        ]
        author_str = ", ".join(a for a in authors if a) or None

        published = _text(entry, f"{{{_NS}}}published") or ""
        published_date = published[:10] if published else None

        # PDF URL: always set — caller decides whether to use passthrough or render
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

        # Abstract page content for when the user wants a summary rather than full paper
        content_html = f"<h2>Abstract</h2><p>{abstract}</p>"
        content_text = abstract

        return ExtractResult(
            title=title,
            author=author_str,
            published_date=published_date,
            content_html=content_html,
            content_text=content_text,
            strategy="arxiv-api",
            passthrough_pdf_url=pdf_url,
        )


def _extract_id(url: str) -> str | None:
    m = _ARXIV_RE.search(url)
    if m:
        return m.group(1)
    m = _ARXIV_OLD_RE.search(url)
    if m:
        return m.group(1)
    return None


def _text(element: ET.Element, tag: str) -> str | None:
    el = element.find(tag)
    return el.text if el is not None else None

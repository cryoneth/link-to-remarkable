from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse


@dataclass
class ExtractResult:
    title: str = ""
    author: Optional[str] = None
    published_date: Optional[str] = None
    content_html: str = ""
    content_text: str = ""
    strategy: str = ""
    # Set by arXiv handler when the user should receive the source PDF directly.
    # The pipeline skips HTML→PDF rendering and downloads this URL instead.
    passthrough_pdf_url: Optional[str] = None

    @property
    def is_confident(self) -> bool:
        if self.passthrough_pdf_url:
            return True
        return (
            bool(self.title.strip())
            and len(self.content_text.strip()) > 500
            and (self.author is not None or self.published_date is not None)
        )

    @property
    def is_empty(self) -> bool:
        return not self.title and not self.content_text


class BaseHandler:
    """Base class for site-specific extraction handlers."""

    @classmethod
    def matches(cls, url: str) -> bool:
        raise NotImplementedError

    async def extract(self, url: str) -> ExtractResult:
        raise NotImplementedError

    @staticmethod
    def _domain(url: str) -> str:
        return urlparse(url).netloc.lower()

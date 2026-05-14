"""Integration tests — require network access.

Run with:  uv run pytest -m integration
These are skipped in normal test runs.
"""

from __future__ import annotations

import pytest

from link2rm.extractor import extract
from link2rm.handlers.arxiv import ArXivHandler
from link2rm.handlers.substack import SubstackHandler


@pytest.mark.integration
@pytest.mark.asyncio
async def test_arxiv_real():
    """arXiv API for the original Attention Is All You Need paper."""
    url = "https://arxiv.org/abs/1706.03762"
    handler = ArXivHandler()
    result = await handler.extract(url)
    assert result.title
    assert result.author
    assert result.passthrough_pdf_url
    assert result.is_confident


@pytest.mark.integration
@pytest.mark.asyncio
async def test_paul_graham_essay():
    """Paul Graham essays have minimal structure — trafilatura or readability fallback."""
    url = "http://www.paulgraham.com/identity.html"
    result = await extract(url)
    assert result.title or result.content_text
    # Paul Graham site has no author/date meta so may not be "confident"
    assert len(result.content_text) > 300
    assert result.strategy in ("trafilatura", "readability", "playwright-readability")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generic_news_site():
    """A stable, well-structured news article should extract confidently."""
    url = "https://www.theguardian.com/science/2024/jan/01/guardian-science-review-2023"
    result = await extract(url)
    # We just verify the cascade runs without crashing and returns something
    assert isinstance(result.strategy, str)
    assert result.strategy != "failed"

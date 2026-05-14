"""Unit tests for site-specific handlers — no network calls."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import respx
import httpx

from link2rm.handlers import ArXivHandler, MediumHandler, SubstackHandler
from link2rm.handlers.base import ExtractResult


# ── Substack ──────────────────────────────────────────────────────────────


class TestSubstackHandler:
    def test_matches_substack_post(self):
        assert SubstackHandler.matches("https://author.substack.com/p/my-post")

    def test_matches_with_query_params(self):
        assert SubstackHandler.matches("https://author.substack.com/p/my-post?utm_source=share")

    def test_no_match_non_post(self):
        assert not SubstackHandler.matches("https://author.substack.com/archive")

    def test_no_match_different_domain(self):
        assert not SubstackHandler.matches("https://paulgraham.com/keep.html")

    @pytest.mark.asyncio
    async def test_extract_success(self, substack_json_text):
        url = "https://example.substack.com/p/why-constraints-fuel-creativity"
        api_url = "https://example.substack.com/api/v1/posts/why-constraints-fuel-creativity"

        with respx.mock:
            respx.get(api_url).mock(
                return_value=httpx.Response(200, text=substack_json_text)
            )
            handler = SubstackHandler()
            result = await handler.extract(url)

        assert result.title == "Why Constraints Fuel Creativity"
        assert result.author == "Alice Wren"
        assert result.published_date == "2024-03-15"
        assert len(result.content_text) > 500
        assert result.strategy == "substack-api"
        assert result.is_confident

    @pytest.mark.asyncio
    async def test_extract_api_fail_returns_empty(self):
        url = "https://example.substack.com/p/my-post"
        api_url = "https://example.substack.com/api/v1/posts/my-post"

        with respx.mock:
            respx.get(api_url).mock(return_value=httpx.Response(404))
            handler = SubstackHandler()
            result = await handler.extract(url)

        assert result.strategy == "substack-api-fail"
        assert not result.is_confident


# ── Medium ────────────────────────────────────────────────────────────────


class TestMediumHandler:
    def test_matches_medium_com(self):
        assert MediumHandler.matches("https://medium.com/@pragprog/the-hidden-cost-of-abstractions-a1b2c3d4e5f6")

    def test_no_match_other_domain(self):
        assert not MediumHandler.matches("https://example.com/article")

    @pytest.mark.asyncio
    async def test_extract_rss_success(self, medium_rss_text):
        url = "https://medium.com/@pragprog/the-hidden-cost-of-abstractions-a1b2c3d4e5f6"
        rss_url = "https://medium.com/feed/@pragprog"

        with respx.mock:
            respx.get(rss_url).mock(return_value=httpx.Response(200, text=medium_rss_text))
            handler = MediumHandler()
            result = await handler.extract(url)

        assert result.title == "The Hidden Cost of Abstractions"
        assert result.author == "David Thomas"
        assert result.published_date == "2024-03-22"
        assert len(result.content_text) > 500
        assert result.strategy == "medium-rss"
        assert result.is_confident

    @pytest.mark.asyncio
    async def test_extract_rss_miss_falls_back(self, medium_rss_text):
        """When URL doesn't match any RSS entry, handler returns no-match result."""
        url = "https://medium.com/@pragprog/different-article-xyz"
        rss_url = "https://medium.com/feed/@pragprog"

        with respx.mock:
            respx.get(rss_url).mock(return_value=httpx.Response(200, text=medium_rss_text))
            respx.get(url).mock(return_value=httpx.Response(200, text="<html><body>no rss link</body></html>"))
            handler = MediumHandler()
            result = await handler.extract(url)

        assert result.strategy == "medium-rss-no-match"
        assert not result.is_confident


# ── arXiv ─────────────────────────────────────────────────────────────────


class TestArXivHandler:
    def test_matches_abs_url(self):
        assert ArXivHandler.matches("https://arxiv.org/abs/2312.12245")

    def test_matches_pdf_url(self):
        assert ArXivHandler.matches("https://arxiv.org/pdf/2312.12245")

    def test_matches_with_version(self):
        assert ArXivHandler.matches("https://arxiv.org/abs/2312.12245v2")

    def test_no_match_non_arxiv(self):
        assert not ArXivHandler.matches("https://example.com/paper")

    @pytest.mark.asyncio
    async def test_extract_success(self, arxiv_xml_text):
        url = "https://arxiv.org/abs/2312.12245"

        with respx.mock:
            respx.get("https://export.arxiv.org/api/query").mock(
                return_value=httpx.Response(200, text=arxiv_xml_text)
            )
            handler = ArXivHandler()
            result = await handler.extract(url)

        assert result.title == "Attention Is All You Need: Revisited"
        assert "Ashish Vaswani" in result.author
        assert result.published_date == "2023-12-19"
        assert result.passthrough_pdf_url == "https://arxiv.org/pdf/2312.12245.pdf"
        assert result.strategy == "arxiv-api"
        assert result.is_confident  # passthrough_pdf_url always → confident

    @pytest.mark.asyncio
    async def test_api_failure_returns_empty(self):
        url = "https://arxiv.org/abs/2312.12245"

        with respx.mock:
            respx.get("https://export.arxiv.org/api/query").mock(
                return_value=httpx.Response(500)
            )
            handler = ArXivHandler()
            result = await handler.extract(url)

        assert result.strategy == "arxiv-api-fail"
        assert not result.is_confident

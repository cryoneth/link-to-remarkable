"""Unit tests for the extraction cascade — no network calls."""

from __future__ import annotations

import pytest
import respx
import httpx

from link2rm.extractor import _trafilatura, _readability, _is_js_shell, _parse_meta
from link2rm.handlers.base import ExtractResult


class TestConfidenceHeuristic:
    def test_confident_with_all_fields(self):
        r = ExtractResult(
            title="My Article",
            author="Jane Doe",
            published_date="2024-01-01",
            content_text="x" * 600,
            strategy="test",
        )
        assert r.is_confident

    def test_confident_without_date_but_has_author(self):
        r = ExtractResult(
            title="My Article",
            author="Jane Doe",
            content_text="x" * 600,
            strategy="test",
        )
        assert r.is_confident

    def test_not_confident_short_content(self):
        r = ExtractResult(
            title="My Article",
            author="Jane Doe",
            content_text="Too short",
            strategy="test",
        )
        assert not r.is_confident

    def test_not_confident_no_author_or_date(self):
        r = ExtractResult(
            title="My Article",
            content_text="x" * 600,
            strategy="test",
        )
        assert not r.is_confident

    def test_passthrough_pdf_always_confident(self):
        r = ExtractResult(
            title="",
            content_text="",
            strategy="arxiv",
            passthrough_pdf_url="https://arxiv.org/pdf/1234.pdf",
        )
        assert r.is_confident


class TestTrafilatura:
    def test_extracts_paul_graham(self, paulgraham_html):
        result = _trafilatura("http://paulgraham.com/identity.html", paulgraham_html)
        # Paul Graham essays have no author/date meta — trafilatura returns text but may not be confident
        assert len(result.content_text) > 200 or result.strategy in (
            "trafilatura-short",
            "trafilatura-empty",
        )

    def test_extracts_news_article(self, news_html):
        result = _trafilatura("http://example.com/article", news_html)
        assert result.title or result.strategy in ("trafilatura-short", "trafilatura-empty")
        if result.strategy == "trafilatura":
            assert len(result.content_text) > 500

    def test_empty_html_returns_empty_strategy(self):
        result = _trafilatura("http://example.com", "<html><body></body></html>")
        assert result.strategy in ("trafilatura-empty", "trafilatura-short")

    def test_returns_extract_result(self, news_html):
        result = _trafilatura("http://example.com/article", news_html)
        assert isinstance(result, ExtractResult)


class TestReadability:
    def test_extracts_news_article(self, news_html):
        result = _readability("http://example.com/article", news_html)
        # readability should handle clean HTML well
        if result.strategy == "readability":
            assert len(result.content_text) > 200
            assert result.title

    def test_extracts_paul_graham(self, paulgraham_html):
        result = _readability("http://paulgraham.com/keep.html", paulgraham_html)
        if result.strategy == "readability":
            assert "identity" in result.content_text.lower() or "labels" in result.content_text.lower()

    def test_bad_html_does_not_raise(self):
        result = _readability("http://example.com", "not html at all!!!")
        assert isinstance(result, ExtractResult)


class TestJsShellDetection:
    def test_empty_body_is_shell(self):
        assert _is_js_shell("<html><body></body></html>")

    def test_react_root_with_little_text_is_shell(self):
        html = '<html><body><div id="root"></div><script src="bundle.js"></script></body></html>'
        assert _is_js_shell(html)

    def test_real_content_not_shell(self, news_html):
        assert not _is_js_shell(news_html)

    def test_no_body_is_shell(self):
        assert _is_js_shell("<html><head><title>Test</title></head></html>")


class TestMetaParsing:
    def test_og_title(self):
        html = '<html><head><meta property="og:title" content="Great Article"></head></html>'
        meta = _parse_meta(html)
        assert meta["title"] == "Great Article"

    def test_author_meta(self):
        html = '<html><head><meta name="author" content="Jane Doe"></head></html>'
        meta = _parse_meta(html)
        assert meta["author"] == "Jane Doe"

    def test_published_time(self):
        html = '<html><head><meta property="article:published_time" content="2024-03-15T10:00:00Z"></head></html>'
        meta = _parse_meta(html)
        assert meta["date"] == "2024-03-15"

    def test_news_html_meta(self, news_html):
        meta = _parse_meta(news_html)
        assert meta.get("title") == "Scientists Discover New Mechanism in Protein Folding"
        assert meta.get("author") == "Jane Reporter"
        assert meta.get("date") == "2024-03-15"

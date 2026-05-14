"""Shared fixtures for the test suite."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def substack_json() -> dict:
    import json
    return json.loads((FIXTURES / "substack_post.json").read_text())


@pytest.fixture
def substack_json_text() -> str:
    return (FIXTURES / "substack_post.json").read_text()


@pytest.fixture
def medium_rss_text() -> str:
    return (FIXTURES / "medium_rss.xml").read_text()


@pytest.fixture
def arxiv_xml_text() -> str:
    return (FIXTURES / "arxiv_api.xml").read_text()


@pytest.fixture
def paulgraham_html() -> str:
    return (FIXTURES / "paulgraham_essay.html").read_text()


@pytest.fixture
def news_html() -> str:
    return (FIXTURES / "news_article.html").read_text()

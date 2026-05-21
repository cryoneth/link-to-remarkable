"""Extraction cascade: site handler → trafilatura → readability → playwright."""

from __future__ import annotations

import time
from typing import Optional

import httpx
import trafilatura
from bs4 import BeautifulSoup
from readability import Document

from link2rm.handlers import ExtractResult, get_handler

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
_CONFIDENCE_MIN_CHARS = 500


async def extract(url: str, use_llm: bool = False) -> ExtractResult:
    """Run the extraction cascade and return the best result."""
    # Sentinel: updated throughout the cascade; last writer before the
    # return statement wins. Always initialised so no UnboundLocalError.
    result = ExtractResult(strategy="not-attempted")

    # ── 1. Site-specific handler ──────────────────────────────────
    handler = get_handler(url)
    if handler:
        handler_result = await handler.extract(url)
        if handler_result.is_confident:
            return handler_result
        # Keep as best-so-far even if not confident (e.g. partial Substack)
        if not handler_result.is_empty:
            result = handler_result

    # ── 2. Fetch raw HTML ─────────────────────────────────────────
    html, _fetch_error = await _fetch_html(url)

    # ── 3. Trafilatura ────────────────────────────────────────────
    if html:
        traf = _trafilatura(url, html)
        if traf.is_confident:
            return traf
        if not traf.is_empty:
            result = traf

    # ── 4. Readability-lxml ───────────────────────────────────────
    if html:
        rdbl = _readability(url, html)
        if rdbl.is_confident:
            return rdbl
        if not rdbl.is_empty:
            result = rdbl

    # ── 5. Playwright (JS-rendered pages) ────────────────────────
    if not html or _is_js_shell(html):
        pw = await _playwright(url)
        if pw.is_confident:
            return pw
        if not pw.is_empty:
            result = pw

    # ── 6. LLM cleanup (opt-in) ──────────────────────────────────
    if use_llm and result.content_text:
        from link2rm.llm_cleanup import cleanup  # lazy import — optional dep
        result = await cleanup(result)

    if result.strategy == "not-attempted" or result.is_empty:
        return ExtractResult(title=url, content_text="", strategy="failed")
    return result


async def _fetch_html(url: str) -> tuple[str, Optional[Exception]]:
    try:
        async with httpx.AsyncClient(
            timeout=20, follow_redirects=True, headers=_BROWSER_HEADERS
        ) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.text, None
    except Exception as e:
        return "", e


def _trafilatura(url: str, html: str) -> ExtractResult:
    try:
        extracted = trafilatura.extract(
            html,
            url=url,
            include_images=True,
            include_links=True,
            favor_precision=True,
            output_format="xml",
            with_metadata=True,
        )
    except Exception:
        return ExtractResult(strategy="trafilatura-error")
    if not extracted:
        return ExtractResult(strategy="trafilatura-empty")

    # trafilatura XML output includes metadata tags
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(extracted)
        title = root.findtext(".//{http://www.w3.org/1999/xhtml}head/{http://www.w3.org/1999/xhtml}title") or ""
        if not title:
            # fallback: parse as plain text
            pass
    except Exception:
        pass

    # Use HTML output for rendering, plain text for confidence check.
    # Trafilatura's HTML metadata-rendering pipeline crashes on multi-author
    # articles (lxml expects a string but gets a list), so we wrap each
    # individually and degrade gracefully on failure.
    try:
        html_out = trafilatura.extract(
            html,
            url=url,
            include_images=True,
            include_links=True,
            favor_precision=True,
            output_format="html",
            with_metadata=True,
        ) or ""
    except Exception:
        html_out = ""
    try:
        text_out = trafilatura.extract(
            html,
            url=url,
            include_images=True,
            include_links=True,
            favor_precision=True,
            output_format="txt",
            with_metadata=True,
        ) or ""
    except Exception:
        text_out = ""

    # If the HTML render failed but text survived, fall through so readability
    # can have a try; trafilatura with no HTML body is useless for ePub render.
    if not html_out:
        return ExtractResult(strategy="trafilatura-html-fail")

    if len(text_out.strip()) < 200:
        return ExtractResult(strategy="trafilatura-short")

    # Extract metadata from the HTML page directly for title/author/date
    meta = _parse_meta(html)
    title = meta.get("title") or _extract_title_from_html(html) or ""
    author = meta.get("author")
    date = meta.get("date")

    return ExtractResult(
        title=title,
        author=author,
        published_date=date,
        content_html=html_out,
        content_text=text_out,
        strategy="trafilatura",
    )


def _readability(url: str, html: str) -> ExtractResult:
    try:
        doc = Document(html)
        title = doc.title() or ""
        content_html = doc.summary(html_partial=True)
        content_text = BeautifulSoup(content_html, "lxml").get_text(
            separator="\n", strip=True
        )

        if len(content_text.strip()) < 200:
            return ExtractResult(strategy="readability-short")

        meta = _parse_meta(html)
        return ExtractResult(
            title=title,
            author=meta.get("author"),
            published_date=meta.get("date"),
            content_html=content_html,
            content_text=content_text,
            strategy="readability",
        )
    except Exception:
        return ExtractResult(strategy="readability-error")


def _is_js_shell(html: str) -> bool:
    """Return True if the page looks like an SPA shell with no real content."""
    soup = BeautifulSoup(html, "lxml")
    body = soup.find("body")
    if not body:
        return True
    text = body.get_text(strip=True)
    if len(text) < 200:
        return True
    # Common SPA root patterns
    root_divs = body.find_all("div", id=lambda x: x in ("root", "app", "__next", "app-root"))
    if root_divs and len(text) < 500:
        return True
    return False


async def _playwright(url: str) -> ExtractResult:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return ExtractResult(strategy="playwright-not-installed")

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page(
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"}
            )
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            html = await page.content()
            await browser.close()

        # Run readability on the JS-rendered HTML
        result = _readability(url, html)
        if result.strategy == "readability":
            result.strategy = "playwright-readability"
        return result
    except Exception as e:
        return ExtractResult(strategy=f"playwright-error:{type(e).__name__}")


def _parse_meta(html: str) -> dict:
    """Extract title, author, date from common meta tags."""
    soup = BeautifulSoup(html[:32768], "lxml")
    out: dict = {}

    # Title: OG → twitter → <title>
    for attr, name in [
        ("property", "og:title"),
        ("name", "twitter:title"),
    ]:
        tag = soup.find("meta", attrs={attr: name})
        if tag and tag.get("content"):
            out["title"] = tag["content"].strip()
            break
    if "title" not in out:
        t = soup.find("title")
        if t:
            out["title"] = t.get_text(strip=True)

    # Author
    for attr, name in [
        ("name", "author"),
        ("property", "article:author"),
        ("name", "twitter:creator"),
    ]:
        tag = soup.find("meta", attrs={attr: name})
        if tag and tag.get("content"):
            val = tag["content"].strip().lstrip("@")
            if val:
                out["author"] = val
                break

    # Published date
    for attr, name in [
        ("property", "article:published_time"),
        ("name", "date"),
        ("name", "DC.date"),
        ("itemprop", "datePublished"),
    ]:
        tag = soup.find("meta", attrs={attr: name})
        if tag and tag.get("content"):
            out["date"] = tag["content"][:10]
            break
    if "date" not in out:
        time_tag = soup.find("time", attrs={"datetime": True})
        if time_tag:
            out["date"] = str(time_tag["datetime"])[:10]

    return out


def _extract_title_from_html(html: str) -> str:
    soup = BeautifulSoup(html[:8192], "lxml")
    for tag in ("h1", "h2"):
        el = soup.find(tag)
        if el:
            return el.get_text(strip=True)
    return ""

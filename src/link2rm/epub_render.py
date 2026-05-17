"""EPUB renderer — packages extracted content into a reMarkable-friendly ePub.

The ePub format gives reMarkable native reflow, adjustable font size, margins,
and line spacing — a much better reading experience than a fixed PDF layout.

Structure mirrors what the official "Read on reMarkable" extension produces:
  article.xhtml  — sanitised article body
  style/main.css — clean reading stylesheet
  EPUB metadata  — title, author, date, language
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from bs4 import BeautifulSoup
from ebooklib import epub

from link2rm.handlers.base import ExtractResult
from link2rm.pdf_render import make_filename  # reuse slug/date logic

# ── Reading stylesheet ────────────────────────────────────────────────────────
# Kept intentionally minimal: reMarkable's ePub renderer applies its own
# spacing/font controls on top of these, so heavy CSS fights the reader.
_CSS = """\
body {
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 1em;
    line-height: 1.6;
    margin: 0;
    padding: 0;
    color: #000;
}

h1.article-title {
    font-size: 1.6em;
    font-weight: bold;
    line-height: 1.25;
    margin: 0 0 0.3em 0;
}

p.article-meta {
    font-size: 0.85em;
    color: #444;
    margin: 0 0 1.5em 0;
    border-bottom: 1px solid #ccc;
    padding-bottom: 0.8em;
}

h1 { font-size: 1.4em; margin: 1.2em 0 0.4em; }
h2 { font-size: 1.2em; margin: 1em 0 0.35em; }
h3 { font-size: 1.05em; margin: 0.9em 0 0.3em; }

p  { margin: 0 0 0.8em 0; }

blockquote {
    margin: 0.8em 0 0.8em 1.2em;
    padding-left: 0.8em;
    border-left: 3px solid #999;
    font-style: italic;
}

pre, code {
    font-family: 'Courier New', Courier, monospace;
    font-size: 0.88em;
}

pre {
    padding: 0.6em;
    border: 1px solid #ddd;
    white-space: pre-wrap;
    word-break: break-all;
}

img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 0.75em auto;
}

a { color: #000; }

table { border-collapse: collapse; width: 100%; font-size: 0.9em; }
th, td { border: 1px solid #bbb; padding: 0.3em 0.5em; text-align: left; }
th { font-weight: bold; }
"""


def make_epub_filename(title: str, date: str | None) -> str:
    return make_filename(title, date).replace(".pdf", ".epub")


def render_to_epub(result: ExtractResult, output_path: Path) -> None:
    """Write an ePub file from an ExtractResult."""
    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid4()))
    book.set_title(result.title or "Article")
    book.set_language("en")

    if result.author:
        book.add_author(result.author)

    # ── Stylesheet ────────────────────────────────────────────────────────────
    css_item = epub.EpubItem(
        uid="main-css",
        file_name="style/main.css",
        media_type="text/css",
        content=_CSS.encode(),
    )
    book.add_item(css_item)

    # ── Article chapter ───────────────────────────────────────────────────────
    chapter = epub.EpubHtml(
        title=result.title or "Article",
        file_name="article.xhtml",
        lang="en",
    )
    chapter.content = _build_xhtml(result).encode()
    chapter.add_link(href="../style/main.css", rel="stylesheet", type="text/css")
    book.add_item(chapter)

    # ── Spine / TOC ───────────────────────────────────────────────────────────
    # The nav item is registered (so readers that show a TOC in their UI can use
    # it) but kept OUT of the spine. Putting it in the spine makes reMarkable
    # render the auto-generated TOC ("1. <title>") as the first content page,
    # which is useless for a single-chapter article.
    book.toc = [chapter]
    book.spine = [chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    epub.write_epub(str(output_path), book, {})


def render_to_bytes(result: ExtractResult) -> bytes:
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as f:
        tmp = Path(f.name)
    render_to_epub(result, tmp)
    data = tmp.read_bytes()
    tmp.unlink(missing_ok=True)
    return data


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_xhtml(result: ExtractResult) -> str:
    """Return a complete XHTML string for the article chapter."""
    import html as html_module

    safe_title = html_module.escape(result.title or "Untitled")

    meta_parts = []
    if result.author:
        meta_parts.append(html_module.escape(result.author))
    if result.published_date:
        meta_parts.append(html_module.escape(result.published_date))
    meta_html = (
        f'<p class="article-meta">{" · ".join(meta_parts)}</p>'
        if meta_parts else ""
    )

    body = result.content_html or f"<p>{html_module.escape(result.content_text)}</p>"
    body = _sanitise_for_xhtml(body)

    return f"""\
<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>{safe_title}</title>
  <link rel="stylesheet" type="text/css" href="../style/main.css"/>
</head>
<body>
  <h1 class="article-title">{safe_title}</h1>
  {meta_html}
  {body}
</body>
</html>"""


def _sanitise_for_xhtml(html: str) -> str:
    """Strip scripts/styles and self-close void elements for XHTML validity."""
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>",  "", html, flags=re.DOTALL | re.IGNORECASE)
    # Self-close void elements so the XHTML parser doesn't choke
    for tag in ("br", "hr", "img", "input", "meta", "link"):
        html = re.sub(rf"<({tag}(\s[^>]*)?)(?<!/)>", r"<\1/>", html, flags=re.IGNORECASE)
    return html

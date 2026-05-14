"""WeasyPrint HTML → PDF with reMarkable-tuned CSS."""

from __future__ import annotations

import html as html_module
import re
import tempfile
from pathlib import Path

from slugify import slugify

from link2rm.handlers.base import ExtractResult

# reMarkable 2: 1404×1872 px at 226 DPI → ~158×210 mm usable area
_CSS = """\
@font-face {
    font-family: 'Charter';
    src: local('Charter'), local('Bitstream Charter');
}

@page {
    size: 155mm 207mm;
    margin: 18mm 14mm 20mm 14mm;
}

*, *::before, *::after {
    box-sizing: border-box;
}

body {
    font-family: Charter, 'Bitstream Charter', Georgia, 'Times New Roman', serif;
    font-size: 11pt;
    line-height: 1.55;
    color: #000;
    max-width: 100%;
    word-wrap: break-word;
    overflow-wrap: break-word;
    -webkit-hyphens: auto;
    hyphens: auto;
}

.article-header {
    margin-bottom: 1.8em;
    padding-bottom: 1em;
    border-bottom: 1pt solid #777;
}

.article-title {
    font-size: 17pt;
    font-weight: bold;
    line-height: 1.25;
    margin: 0 0 0.35em 0;
}

.article-meta {
    font-size: 9pt;
    color: #444;
    margin: 0;
}

h1 { font-size: 15pt; margin: 1.4em 0 0.4em; line-height: 1.2; page-break-after: avoid; }
h2 { font-size: 13pt; margin: 1.2em 0 0.35em; line-height: 1.2; page-break-after: avoid; }
h3 { font-size: 11.5pt; margin: 1em 0 0.3em; line-height: 1.2; page-break-after: avoid; }
h4, h5, h6 { font-size: 11pt; font-weight: bold; margin: 0.8em 0 0.25em; }

p {
    margin: 0 0 0.75em 0;
    orphans: 3;
    widows: 3;
}

ul, ol {
    margin: 0.5em 0 0.75em 1.4em;
    padding: 0;
}
li { margin-bottom: 0.25em; }

blockquote {
    margin: 0.75em 0 0.75em 1.2em;
    padding-left: 0.8em;
    border-left: 2pt solid #888;
    font-style: italic;
    color: #222;
}

pre {
    font-family: 'Courier New', 'Courier', monospace;
    font-size: 8.5pt;
    line-height: 1.4;
    padding: 0.6em 0.8em;
    border: 0.5pt solid #bbb;
    white-space: pre-wrap;
    word-break: break-all;
    page-break-inside: avoid;
    margin: 0.75em 0;
}

code {
    font-family: 'Courier New', 'Courier', monospace;
    font-size: 9pt;
    background: none;
}

img {
    max-width: 100%;
    max-height: 130mm;
    height: auto;
    display: block;
    margin: 0.75em auto;
    /* No colour — greyscale for e-ink */
    filter: grayscale(100%);
}

figure { margin: 0.75em 0; }
figcaption {
    font-size: 8.5pt;
    color: #555;
    text-align: center;
    margin-top: 0.25em;
}

a {
    color: #000;
    text-decoration: underline;
    text-decoration-thickness: 0.5pt;
}

table {
    border-collapse: collapse;
    width: 100%;
    font-size: 9.5pt;
    margin: 0.75em 0;
}
th, td {
    border: 0.5pt solid #888;
    padding: 0.3em 0.5em;
    text-align: left;
}
th { font-weight: bold; background: none; }

hr {
    border: none;
    border-top: 0.5pt solid #aaa;
    margin: 1.2em 0;
}

/* Suppress nav, ads, and other chrome that leaked through */
nav, [role="navigation"], .nav, .navigation,
[class*="navbar"], [class*="nav-bar"],
[class*="cookie"], [class*="banner"], [class*="modal"],
[class*="popup"], [class*="newsletter"], [class*="subscribe"],
[id*="cookie"], [id*="banner"], [id*="ad-"],
[class*="ad "], [class*=" ad"], [class^="ad-"],
footer, .footer, [role="contentinfo"],
.site-header, .site-footer, .sidebar,
.share-buttons, [class*="social-"],
[class*="related"], [class*="recommended"],
[class*="comments"], #comments {
    display: none !important;
}
"""


def make_filename(title: str, date: str | None) -> str:
    date_part = date or ""
    if date_part:
        date_part = date_part.replace("-", "")[:8]
    slug = slugify(title, max_length=80) if title else "article"
    return f"{slug}-{date_part}.pdf" if date_part else f"{slug}.pdf"


def render_to_pdf(result: ExtractResult, output_path: Path) -> None:
    """Render an ExtractResult to a PDF file via WeasyPrint."""
    from weasyprint import CSS, HTML  # lazy import so CLI is fast when just doing --help

    doc_html = _build_html(result)
    HTML(string=doc_html).write_pdf(
        str(output_path),
        stylesheets=[CSS(string=_CSS)],
    )


def render_to_bytes(result: ExtractResult) -> bytes:
    """Render to bytes (used by the server)."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        tmp = Path(f.name)
    render_to_pdf(result, tmp)
    data = tmp.read_bytes()
    tmp.unlink(missing_ok=True)
    return data


def _build_html(result: ExtractResult) -> str:
    meta_parts = []
    if result.author:
        meta_parts.append(html_module.escape(result.author))
    if result.published_date:
        meta_parts.append(html_module.escape(result.published_date))
    meta_html = " · ".join(meta_parts)

    # Sanitise title for HTML context
    safe_title = html_module.escape(result.title or "Untitled")

    body = result.content_html or f"<p>{html_module.escape(result.content_text)}</p>"

    # Strip any <script>/<style> tags that slipped through
    body = re.sub(r"<script[^>]*>.*?</script>", "", body, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r"<style[^>]*>.*?</style>", "", body, flags=re.DOTALL | re.IGNORECASE)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{safe_title}</title>
</head>
<body>
<div class="article-header">
  <div class="article-title">{safe_title}</div>
  {f'<p class="article-meta">{meta_html}</p>' if meta_html else ''}
</div>
{body}
</body>
</html>"""

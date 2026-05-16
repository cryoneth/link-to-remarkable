"""End-to-end pipeline: URL → extract → render → upload."""

from __future__ import annotations

import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import httpx

from link2rm import config, remarkable
from link2rm.extractor import extract
from link2rm.handlers.base import ExtractResult
from link2rm.logger import log_request
from link2rm.pdf_render import make_filename, render_to_pdf
from link2rm.epub_render import make_epub_filename, render_to_epub

Format = Literal["epub", "pdf"]


@dataclass
class PipelineResult:
    url: str
    doc_name: str
    strategy: str
    extraction_ms: int
    file_bytes: int
    upload_status: str
    output_format: str
    remarkable_id: Optional[str] = None
    llm_tokens: int = 0
    local_output: Optional[Path] = None


async def run(
    url: str,
    use_llm: bool = False,
    folder: Optional[str] = None,
    fmt: Optional[Format] = None,
    local_output: Optional[Path] = None,
) -> PipelineResult:
    """Extract, render, and optionally upload a URL.

    fmt defaults to config.REMARKABLE_FORMAT ("epub").
    arXiv passthrough URLs always use PDF regardless of fmt.
    """
    target_folder = folder or config.REMARKABLE_FOLDER
    output_fmt: Format = fmt or config.REMARKABLE_FORMAT  # type: ignore[assignment]

    # ── 1. Extract ────────────────────────────────────────────────────────────
    t0 = time.monotonic()
    result = await extract(url, use_llm=use_llm)
    extraction_ms = int((time.monotonic() - t0) * 1000)
    llm_tokens = getattr(result, "_llm_tokens", 0)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        file_path: Path
        doc_name: str

        # ── 2. Render / passthrough ───────────────────────────────────────────
        if result.passthrough_pdf_url:
            # arXiv et al: download the source PDF directly; skip local render
            file_path, doc_name = await _download_pdf(
                result.passthrough_pdf_url, result, tmp
            )
            effective_fmt: Format = "pdf"
        elif output_fmt == "epub":
            filename = make_epub_filename(result.title, result.published_date)
            file_path = tmp / filename
            render_to_epub(result, file_path)
            doc_name = (result.title or filename).strip()
            effective_fmt = "epub"
        else:
            filename = make_filename(result.title, result.published_date)
            file_path = tmp / filename
            render_to_pdf(result, file_path)
            doc_name = (result.title or filename).strip()
            effective_fmt = "pdf"

        file_size = file_path.stat().st_size

        # ── 3. Copy to local path if requested ───────────────────────────────
        if local_output:
            shutil.copy2(file_path, local_output)

        # ── 4. Upload to reMarkable ───────────────────────────────────────────
        rm_id = None
        upload_status = "skipped"
        if not local_output:
            try:
                token_file = remarkable.ensure_authenticated()
                if effective_fmt == "epub":
                    entry = remarkable.upload_epub(file_path, doc_name, target_folder, token_file)
                else:
                    entry = remarkable.upload_pdf(file_path, doc_name, target_folder, token_file)
                rm_id = entry.get("id")
                upload_status = "ok"
            except Exception as e:
                upload_status = f"error:{type(e).__name__}"
                raise

    # ── 5. Log ────────────────────────────────────────────────────────────────
    log_request(
        url=url,
        strategy=result.strategy,
        extraction_ms=extraction_ms,
        pdf_bytes=file_size,
        upload_status=upload_status,
        llm_tokens=llm_tokens,
    )

    return PipelineResult(
        url=url,
        doc_name=doc_name,
        strategy=result.strategy,
        extraction_ms=extraction_ms,
        file_bytes=file_size,
        upload_status=upload_status,
        output_format=effective_fmt,
        remarkable_id=rm_id,
        llm_tokens=llm_tokens,
        local_output=local_output,
    )


async def _download_pdf(
    pdf_url: str, result: ExtractResult, tmpdir: Path
) -> tuple[Path, str]:
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        r = await client.get(pdf_url)
        r.raise_for_status()

    filename = make_filename(result.title, result.published_date)
    pdf_path = tmpdir / filename
    pdf_path.write_bytes(r.content)
    doc_name = (result.title or filename).strip()
    return pdf_path, doc_name

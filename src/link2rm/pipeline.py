"""End-to-end pipeline: URL → extract → render → upload."""

from __future__ import annotations

import httpx
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from link2rm import config
from link2rm.extractor import extract
from link2rm.handlers.base import ExtractResult
from link2rm.logger import log_request
from link2rm.pdf_render import make_filename, render_to_pdf
from link2rm import remarkable


@dataclass
class PipelineResult:
    url: str
    doc_name: str
    strategy: str
    extraction_ms: int
    pdf_bytes: int
    upload_status: str
    remarkable_id: Optional[str] = None
    llm_tokens: int = 0
    local_pdf: Optional[Path] = None


async def run(
    url: str,
    use_llm: bool = False,
    folder: Optional[str] = None,
    local_output: Optional[Path] = None,
) -> PipelineResult:
    """Extract, render, and optionally upload a URL."""
    target_folder = folder or config.REMARKABLE_FOLDER

    # ── 1. Extract ────────────────────────────────────────────────
    t0 = time.monotonic()
    result = await extract(url, use_llm=use_llm)
    extraction_ms = int((time.monotonic() - t0) * 1000)
    llm_tokens = getattr(result, "_llm_tokens", 0)

    # ── 2. Render / download PDF ──────────────────────────────────
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path: Path
        doc_name: str

        if result.passthrough_pdf_url:
            # arXiv or similar: download source PDF directly
            pdf_path, doc_name = await _download_pdf(
                result.passthrough_pdf_url, result, Path(tmpdir)
            )
        else:
            filename = make_filename(result.title, result.published_date)
            pdf_path = Path(tmpdir) / filename
            render_to_pdf(result, pdf_path)
            doc_name = (result.title or filename).strip()

        pdf_size = pdf_path.stat().st_size

        # ── 3. Copy to local output if requested ──────────────────
        if local_output:
            import shutil
            shutil.copy2(pdf_path, local_output)

        # ── 4. Upload to reMarkable ───────────────────────────────
        rm_id = None
        upload_status = "skipped"
        if not local_output:
            try:
                token_file = remarkable.ensure_authenticated()
                entry = remarkable.upload_pdf(pdf_path, doc_name, target_folder, token_file)
                rm_id = entry.get("id")
                upload_status = "ok"
            except Exception as e:
                upload_status = f"error:{type(e).__name__}"
                raise

    # ── 5. Log ────────────────────────────────────────────────────
    log_request(
        url=url,
        strategy=result.strategy,
        extraction_ms=extraction_ms,
        pdf_bytes=pdf_size,
        upload_status=upload_status,
        llm_tokens=llm_tokens,
    )

    return PipelineResult(
        url=url,
        doc_name=doc_name,
        strategy=result.strategy,
        extraction_ms=extraction_ms,
        pdf_bytes=pdf_size,
        upload_status=upload_status,
        remarkable_id=rm_id,
        llm_tokens=llm_tokens,
        local_pdf=local_output,
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

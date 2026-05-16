"""FastAPI ingest server.

POST /ingest   {"url": "...", "llm": false, "folder": null}
               → 202 {"job_id": "..."}

GET  /jobs/{id}
               → {"status": "pending|running|done|error", ...}
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl

from link2rm import config

app = FastAPI(title="link2rm", version="0.1.0")

# In-process job store — sufficient for single-user use.
# Does not persist across restarts. For multi-process, swap for Redis.
_jobs: dict[str, dict] = {}


class IngestRequest(BaseModel):
    url: str
    llm: bool = False
    folder: Optional[str] = None
    format: Optional[str] = None  # "epub" | "pdf" | None → uses REMARKABLE_FORMAT default


class IngestResponse(BaseModel):
    job_id: str
    status: str = "pending"


@app.post("/ingest", status_code=202, response_model=IngestResponse)
async def ingest(req: IngestRequest, background_tasks: BackgroundTasks) -> IngestResponse:
    job_id = str(uuid4())
    _jobs[job_id] = {
        "status": "pending",
        "url": req.url,
        "queued_at": time.time(),
    }
    background_tasks.add_task(_process, job_id, req.url, req.llm, req.folder, req.format)
    return IngestResponse(job_id=job_id)


@app.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return _jobs[job_id]


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


async def _process(
    job_id: str,
    url: str,
    use_llm: bool,
    folder: Optional[str],
    fmt: Optional[str] = None,
) -> None:
    from link2rm.pipeline import run

    _jobs[job_id]["status"] = "running"
    _jobs[job_id]["started_at"] = time.time()
    try:
        effective_llm = use_llm or config.LLM_CLEANUP
        result = await run(url, use_llm=effective_llm, folder=folder, fmt=fmt)
        _jobs[job_id].update(
            {
                "status": "done",
                "doc_name": result.doc_name,
                "strategy": result.strategy,
                "extraction_ms": result.extraction_ms,
                "pdf_bytes": result.pdf_bytes,
                "upload_status": result.upload_status,
                "output_format": result.output_format,
                "remarkable_id": result.remarkable_id,
                "llm_tokens": result.llm_tokens,
                "finished_at": time.time(),
            }
        )
    except Exception as e:
        _jobs[job_id].update(
            {
                "status": "error",
                "error": str(e),
                "finished_at": time.time(),
            }
        )

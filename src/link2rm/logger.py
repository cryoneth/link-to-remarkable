import json
from datetime import datetime, timezone

from link2rm.config import LOG_FILE


def log_request(
    url: str,
    strategy: str,
    extraction_ms: int,
    pdf_bytes: int,
    upload_status: str,
    llm_tokens: int = 0,
) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "url": url,
        "strategy": strategy,
        "extraction_ms": extraction_ms,
        "pdf_bytes": pdf_bytes,
        "upload": upload_status,
        "llm_tokens": llm_tokens,
    }
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")

# link-to-remarkable

Send any URL to a reMarkable tablet as a clean, readable PDF.

## Architecture

```
URL → extractor (cascade) → ExtractResult → pdf_render → PDF → remarkable (upload)
         │
         ├── site handlers (substack, medium, arxiv)  ← cheapest, tried first
         ├── trafilatura                               ← primary general extractor
         ├── readability-lxml                          ← fallback
         ├── playwright + readability                  ← JS-rendered pages only
         └── LLM cleanup                              ← opt-in, text only
```

## Key invariants

- **No LLM by default.** The `--llm` flag or `LLM_CLEANUP=true` env var must be set explicitly per request. The extractor NEVER sends HTML to an LLM.
- **Confidence check stops the cascade.** `ExtractResult.is_confident` requires title + content > 500 chars + (author or date). A result that passes this check is returned immediately.
- **reMarkable upload uses rmapi-js via Node.js shim.** The `scripts/` directory contains a tiny Node.js helper (`rm-upload.mjs`, `rm-register.mjs`) that wraps `rmapi-js@^9`. Python calls it via subprocess, passing args as env vars. The token file format is compatible with `telegram-monitor`.

## Module guide

| Module | Role |
|---|---|
| `extractor.py` | Orchestrates the cascade, returns `ExtractResult` |
| `handlers/` | Site-specific extractors. Drop a new `*.py` file here and register it in `__init__.py`. |
| `pdf_render.py` | WeasyPrint HTML→PDF with reMarkable-tuned CSS |
| `remarkable.py` | Thin Python wrapper around the Node.js rmapi-js shim |
| `logger.py` | Appends a JSONL line to `~/.link2rm/log.jsonl` per request |
| `cli.py` | Click CLI entry point (`link2rm <url>`) |
| `server.py` | FastAPI server (POST /ingest, GET /jobs/{id}) |
| `config.py` | Reads env vars with defaults |

## Do not

- Do NOT send raw HTML to any LLM. The LLM path (`llm_cleanup.py`) receives only the already-extracted `content_text`.
- Do NOT hardcode credentials. Use `.env` and `config.py`.
- Do NOT add per-site extraction logic outside of `src/link2rm/handlers/`. The cascade handles unknown sites automatically.
- Do NOT use synchronous `requests` — use `httpx.AsyncClient` for all HTTP.
- Do NOT commit `.env`, token files, or generated PDFs.

## Adding a new site handler

1. Create `src/link2rm/handlers/mysite.py` implementing `BaseHandler`.
2. Register it in `src/link2rm/handlers/__init__.py` by adding to `HANDLERS`.
3. Add a fixture HTML/JSON file to `tests/fixtures/`.
4. Add a test in `tests/test_handlers.py`.

## Running

```bash
uv sync
uv run link2rm https://example.com/article   # CLI
uv run link2rm --server                       # Start FastAPI server
```

## Test suite

```bash
uv run pytest                          # unit tests only (no network)
uv run pytest -m integration           # integration tests (needs network)
```

# link-to-remarkable

Send any URL to your reMarkable tablet as a clean, readable PDF. No LLM calls by default — rules-based extraction only.

**Handles:** Substack, Medium, arXiv, Paul Graham essays, news sites, personal blogs, random web pages. No per-site configuration needed for anything not listed.

---

## How it works

```
URL  →  extractor cascade  →  WeasyPrint PDF  →  reMarkable cloud
             │
             ├─ Site handler (Substack/Medium/arXiv)   cheapest, first
             ├─ Trafilatura                             primary fallback
             ├─ readability-lxml                        secondary fallback
             └─ Playwright + readability                JS-rendered pages
```

A strategy is accepted the moment it produces: a non-empty title + content text > 500 chars + (author or date). The cascade stops immediately.

---

## Prerequisites

| Tool | Why | Install |
|---|---|---|
| Python 3.11+ | Runtime | `brew install python` or pyenv |
| uv | Package manager | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js 18+ | reMarkable upload shim | `brew install node` |

---

## Install

```bash
git clone <repo> link-to-remarkable
cd link-to-remarkable

# Python deps
uv sync --extra playwright --extra dev

# Playwright browser (Chromium, ~100 MB — JS-rendered pages only)
uv run playwright install chromium

# reMarkable Node.js shim (rmapi-js)
cd scripts && npm install && cd ..

# Config
cp .env.example .env
# Edit .env — at minimum set REMARKABLE_FOLDER
```

### First-run reMarkable auth

```bash
uv run link2rm --register
# → Go to https://my.remarkable.com/device/desktop/connect
# → Enter the 8-letter one-time code
# Token saved to ~/.config/link2rm/rmapi-token
```

The token is the same format used by `telegram-monitor` — you can share the same `.rmapi-token` file by pointing `RMAPI_TOKEN_FILE` at it in your `.env`.

---

## Run

### CLI

```bash
# Send a URL to reMarkable
uv run link2rm https://noahpinion.substack.com/p/my-post

# Save PDF locally instead of uploading
uv run link2rm -o article.pdf https://example.com/post

# With LLM cleanup (requires ANTHROPIC_API_KEY)
uv run link2rm --llm https://some-messy-blog.com/post

# Override destination folder
uv run link2rm --folder "/Articles/Reading" https://example.com/post
```

### Server

```bash
uv run link2rm --server          # binds 0.0.0.0:8765 by default
uv run link2rm --server --port 9000 --host 127.0.0.1

# Ingest
curl -X POST http://localhost:8765/ingest \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://arxiv.org/abs/1706.03762"}'
# → {"job_id": "...", "status": "pending"}

# Poll status
curl http://localhost:8765/jobs/<job_id>
```

---

## Share-target setup

### Android — HTTP Shortcuts (over Tailscale)

To reach the server from your phone when off the home network, put both machines on Tailscale and use the Mac's Tailscale IP (`100.x.x.x`) in the shortcut URL.

1. **Tailscale:** install on the Mac (`brew install --cask tailscale`) and on the phone (Play Store). Sign into the same account on both. Note the Mac's `100.x.x.x` IP from the Tailscale menu bar.
2. Install **HTTP Shortcuts** (by Waboodoo) from the Play Store.
3. **Create a global variable** (this is the part that's easy to miss):
   - Main menu → Variables → **+**
   - Name: `url`, Type: `Text Input` (any type works)
   - Open **Advanced Settings** → toggle **"Allow Receiving Value from Share Dialog"** ON
   - Set "Use" to **"the text"**
4. **Create the shortcut:**
   - Name: `Send to reMarkable`
   - Basic Request Settings → Method `POST`, URL `http://<tailscale-ip>:8765/ingest`
   - Request Body / Parameters → body type `Custom text`, content type `application/json`
   - Body: `{"url": "{url}"}` — **insert the `url` variable using the `{}` picker, don't type it as text**. A properly inserted variable renders as a coloured chip, not plain text. If you just type `{url}`, the server will receive the literal string.
   - Response Handling → Success toast: `Sent to reMarkable ✓`
   - Trigger & Execution Settings → enable **"Show as app shortcut on launcher"** (this also enables Direct Share)
5. **Test:** open any article in Chrome / Firefox / Substack → Share → **Send to reMarkable** → article appears on the tablet within ~30 s.

If you see "No suitable shortcuts found" when sharing, the `url` variable doesn't have "Allow Receiving Value from Share Dialog" enabled. If the reMarkable receives a document titled literally `{url}`, the variable wasn't inserted via the picker — it was typed as text.

### macOS — Raycast / Alfred / shortcuts

**Option A: Raycast script**

Create a Raycast script command at `~/.raycast/scripts/link2rm.sh`:

```bash
#!/bin/bash
# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Send to reMarkable
# @raycast.mode compact

URL=$(pbpaste)
~/.local/bin/uv run --directory /path/to/link-to-remarkable link2rm "$URL"
```

**Option B: macOS Shortcut**

1. Open Shortcuts → New Shortcut
2. Add action: **Get Contents of URL** (POST to `http://localhost:8765/ingest`, JSON body `{"url": "Input"}`)
3. Add it to the Share Sheet
4. Now: Safari → Share → your shortcut

**Option C: CLI alias**

```bash
# In ~/.zshrc or ~/.bashrc
alias rm2='uv run --directory ~/Documents/Coding/link-to-remarkable link2rm'

# Usage: copy URL, then
rm2 "$(pbpaste)"
```

---

## Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `REMARKABLE_FOLDER` | `/Articles/Inbox` | Destination folder on the tablet. Must exist — create from the tablet first. Supports nested paths: `Articles/Inbox` |
| `RMAPI_TOKEN_FILE` | `~/.config/link2rm/rmapi-token` | Path to the device auth token. Share with telegram-monitor by pointing at the same file. |
| `LLM_CLEANUP` | `false` | Enable LLM cleanup globally (per-request `--llm` flag takes precedence) |
| `ANTHROPIC_API_KEY` | — | Required only if `LLM_CLEANUP=true` or `--llm` is passed |
| `HOST` | `0.0.0.0` | Server bind host |
| `PORT` | `8765` | Server bind port |
| `LINK2RM_LOG_FILE` | `~/.link2rm/log.jsonl` | Per-request strategy log |

---

## Observability

Every request appends one JSON line to `~/.link2rm/log.jsonl`:

```json
{
  "ts": "2026-05-14T08:08:57.069211+00:00",
  "url": "https://noahpinion.substack.com/p/...",
  "strategy": "substack-api",
  "extraction_ms": 995,
  "pdf_bytes": 48887,
  "upload": "ok",
  "llm_tokens": 0
}
```

Analyse strategy distribution:

```bash
# Which strategies are running
cat ~/.link2rm/log.jsonl | jq -r .strategy | sort | uniq -c | sort -rn

# Failed extractions
cat ~/.link2rm/log.jsonl | jq 'select(.strategy == "failed")'
```

---

## Adding a new site handler

1. Create `src/link2rm/handlers/mysite.py`:

```python
from .base import BaseHandler, ExtractResult

class MySiteHandler(BaseHandler):
    @classmethod
    def matches(cls, url: str) -> bool:
        return "mysite.com" in url

    async def extract(self, url: str) -> ExtractResult:
        # fetch, parse, return ExtractResult(...)
        ...
```

2. Register it in `src/link2rm/handlers/__init__.py`:

```python
from .mysite import MySiteHandler
HANDLERS = [ArXivHandler, SubstackHandler, MediumHandler, MySiteHandler]
```

3. Add a fixture to `tests/fixtures/` and a test to `tests/test_handlers.py`.

---

## Tests

```bash
# Unit tests (no network)
uv run pytest

# Integration tests (requires network)
uv run pytest -m integration

# With coverage
uv run pytest --cov=link2rm --cov-report=term-missing
```

---

## Project layout

```
link-to-remarkable/
├── src/link2rm/
│   ├── cli.py            CLI entry point
│   ├── server.py         FastAPI server (POST /ingest, GET /jobs/{id})
│   ├── pipeline.py       Orchestrates extract → render → upload
│   ├── extractor.py      Extraction cascade
│   ├── handlers/         Site-specific handlers
│   │   ├── substack.py   JSON API
│   │   ├── medium.py     RSS feed
│   │   └── arxiv.py      arXiv API + passthrough PDF
│   ├── pdf_render.py     WeasyPrint → reMarkable-tuned PDF
│   ├── remarkable.py     Upload client (Node.js shim)
│   ├── llm_cleanup.py    Optional Claude Haiku cleanup (--llm only)
│   ├── logger.py         JSONL request log
│   └── config.py         Env-var configuration
├── scripts/
│   ├── rm-register.mjs   One-time device registration
│   └── rm-upload.mjs     PDF upload via rmapi-js@^9
├── tests/
│   ├── fixtures/         Recorded HTML/XML/JSON — no network in unit tests
│   ├── test_extractor.py
│   ├── test_handlers.py
│   └── test_integration.py
└── CLAUDE.md             Project conventions for Claude Code
```

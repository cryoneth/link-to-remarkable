"""reMarkable upload via rmapi-js Node.js shim.

The shim (scripts/rm-upload.mjs) uses rmapi-js@^9 — the same library as
telegram-monitor — so the token file format is identical and can be shared.

Auth:
  First run: the device must be registered via register_device() which calls
  scripts/rm-register.mjs.  After that, the token is cached on disk.

Upload flow (mirrors telegram-monitor/remarkable-daily.js):
  1. remarkable(token) → api
  2. api.listItems() → find folder by name
  3. api.uploadPdf(name, bytes) → entry
  4. api.move(entry.hash, folderId) with retry
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from link2rm.config import RMAPI_TOKEN_FILE, SCRIPTS_DIR


def ensure_authenticated(token_file: Path | None = None) -> Path:
    """Return the token file path, prompting for registration if needed."""
    tf = token_file or RMAPI_TOKEN_FILE
    tf.parent.mkdir(parents=True, exist_ok=True)
    if not tf.exists():
        print("\nNo reMarkable token found.")
        print("Go to: https://my.remarkable.com/device/desktop/connect")
        code = input("Enter the 8-letter one-time code: ").strip()
        register_device(code, tf)
        print(f"Token saved to {tf}")
    return tf


def register_device(code: str, token_file: Path | None = None) -> None:
    """Register this device using a one-time code from my.remarkable.com."""
    tf = token_file or RMAPI_TOKEN_FILE
    _run_node(
        SCRIPTS_DIR / "rm-register.mjs",
        {"REG_CODE": code, "TOKEN_FILE": str(tf)},
    )


def upload_epub(
    epub_path: Path,
    doc_name: str,
    folder: str,
    token_file: Path | None = None,
) -> dict:
    """Upload an ePub to reMarkable (default format).

    reMarkable renders ePubs natively with adjustable font size, margins, and
    line spacing — a better reading experience than PDF.
    """
    return _upload_file(epub_path, doc_name, folder, "epub", token_file)


def upload_pdf(
    pdf_path: Path,
    doc_name: str,
    folder: str,
    token_file: Path | None = None,
) -> dict:
    """Upload a PDF to reMarkable."""
    return _upload_file(pdf_path, doc_name, folder, "pdf", token_file)


def _upload_file(
    file_path: Path,
    doc_name: str,
    folder: str,
    file_type: str,
    token_file: Path | None = None,
) -> dict:
    """Shared upload implementation — routes to putEpub or putPdf in the shim."""
    tf = token_file or RMAPI_TOKEN_FILE
    if not tf.exists():
        raise FileNotFoundError(
            f"reMarkable token not found at {tf}. "
            "Run `link2rm --register` or `link2rm <url>` to trigger first-time auth."
        )

    import os as _os
    env_extras = {
        "TOKEN_FILE": str(tf),
        "DOC_NAME": doc_name,
        "FILE_PATH": str(file_path),
        "FILE_TYPE": file_type,          # "epub" | "pdf"
        "FOLDER_NAME": folder,
    }
    if folder_id := _os.getenv("REMARKABLE_FOLDER_ID", ""):
        env_extras["REMARKABLE_FOLDER_ID"] = folder_id

    out = _run_node(
        SCRIPTS_DIR / "rm-upload.mjs",
        env_extras,
        capture_stdout=True,
    )
    return json.loads(out.strip()) if out.strip() else {}


def _run_node(
    script: Path,
    env_vars: dict[str, str],
    capture_stdout: bool = False,
) -> str:
    env = {**os.environ, **env_vars}
    result = subprocess.run(
        ["node", str(script)],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Node.js script {script.name} failed (exit {result.returncode}):\n"
            f"{result.stderr.strip()}"
        )
    return result.stdout if capture_stdout else ""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REMARKABLE_FOLDER: str = os.getenv("REMARKABLE_FOLDER", "/Articles/Inbox")
RMAPI_TOKEN_FILE: Path = Path(
    os.getenv("RMAPI_TOKEN_FILE", "~/.config/link2rm/rmapi-token")
).expanduser()
LLM_CLEANUP: bool = os.getenv("LLM_CLEANUP", "false").lower() == "true"
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
LOG_FILE: Path = Path(
    os.getenv("LINK2RM_LOG_FILE", "~/.link2rm/log.jsonl")
).expanduser()
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8765"))
SCRIPTS_DIR: Path = Path(__file__).parent.parent.parent / "scripts"

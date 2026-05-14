"""Optional LLM cleanup step — only imported when --llm is active.

Sends EXTRACTED TEXT (never raw HTML) to Claude Haiku.
Returns a cleaned ExtractResult with the same or better content.
"""

from __future__ import annotations

import json

from link2rm.config import ANTHROPIC_API_KEY
from link2rm.handlers.base import ExtractResult

_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 4096
_PROMPT = """\
You are a text cleaner for a read-it-later app. The text below was extracted from a web page.

Tasks:
1. Remove any residual navigation, footer, cookie notices, or boilerplate text that leaked in.
2. Fix obvious paragraph-break issues (merged paragraphs, missing line breaks).
3. Correct the title if it is clearly wrong or cut off. Confirm or correct the author if provided.
4. Return ONLY valid JSON — no markdown fences, no extra text.

Format: {{"title": "...", "author": "..." or null, "content_text": "..."}}

Keep every substantive word of the article. Do NOT summarize or shorten.

TITLE: {title}
AUTHOR: {author}
TEXT:
{content_text}"""


async def cleanup(result: ExtractResult) -> ExtractResult:
    """Call Claude Haiku to clean up already-extracted text. Returns updated result."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Required for --llm / LLM_CLEANUP=true."
        )

    import anthropic  # optional dependency

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    prompt = _PROMPT.format(
        title=result.title or "(unknown)",
        author=result.author or "(unknown)",
        content_text=result.content_text[:12000],  # cap to stay within token budget
    )

    message = await client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    tokens_used = message.usage.input_tokens + message.usage.output_tokens

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Haiku returned something non-JSON; return original with updated strategy
        result.strategy += "+llm-parse-fail"
        return result

    result.title = data.get("title") or result.title
    result.author = data.get("author") or result.author
    if cleaned_text := data.get("content_text"):
        result.content_text = cleaned_text
    result.strategy += "+llm"
    result._llm_tokens = tokens_used  # type: ignore[attr-defined]
    return result

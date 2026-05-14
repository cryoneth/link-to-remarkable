"""Site-specific handler registry.

To add a new handler:
1. Create src/link2rm/handlers/mysite.py implementing BaseHandler.
2. Import and append to HANDLERS below.
"""

from .arxiv import ArXivHandler
from .base import BaseHandler, ExtractResult
from .medium import MediumHandler
from .substack import SubstackHandler

# Handlers are tried in order; first match wins.
HANDLERS: list[type[BaseHandler]] = [
    ArXivHandler,
    SubstackHandler,
    MediumHandler,
]


def get_handler(url: str) -> BaseHandler | None:
    for handler_class in HANDLERS:
        if handler_class.matches(url):
            return handler_class()
    return None


__all__ = [
    "BaseHandler",
    "ExtractResult",
    "ArXivHandler",
    "SubstackHandler",
    "MediumHandler",
    "HANDLERS",
    "get_handler",
]

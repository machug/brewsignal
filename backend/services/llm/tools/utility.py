"""System and utility tools for the AI brewing assistant."""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AgUiThread, AgUiMessage

logger = logging.getLogger(__name__)


def get_current_datetime() -> dict[str, Any]:
    """Get the current date and time in the system timezone.

    Returns a dictionary with various date/time representations
    useful for making time-based calculations and predictions.
    """
    import zoneinfo

    # Get current time in UTC
    now_utc = datetime.now(timezone.utc)

    # Try to get local timezone, fallback to UTC
    try:
        # Try common Australian timezone (where the system is)
        local_tz = zoneinfo.ZoneInfo("Australia/Sydney")
        now_local = now_utc.astimezone(local_tz)
    except Exception:
        # Fallback to UTC if timezone not available
        now_local = now_utc
        local_tz = timezone.utc

    # Calculate day of week
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_of_week = day_names[now_local.weekday()]

    return {
        "current_datetime": now_local.isoformat(),
        "date": now_local.strftime("%Y-%m-%d"),
        "time": now_local.strftime("%H:%M:%S"),
        "day_of_week": day_of_week,
        "timezone": str(local_tz),
        "timestamp_utc": now_utc.isoformat(),
        "unix_timestamp": int(now_utc.timestamp()),
        "human_readable": now_local.strftime("%A, %B %d, %Y at %I:%M %p"),
    }


def strip_html_tags(html: str) -> str:
    """Strip HTML tags and clean up text content."""
    # Remove script and style elements entirely
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', html)
    # Decode common HTML entities
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'")
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


async def fetch_url(url: str) -> dict[str, Any]:
    """Fetch and extract text content from a URL."""
    MAX_CONTENT_LENGTH = 6000  # Limit content to avoid overwhelming LLM

    # Basic URL validation
    if not url.startswith(('http://', 'https://')):
        return {"error": "Invalid URL - must start with http:// or https://"}

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; BrewSignal/1.0; +https://brewsignal.local)"
                }
            )
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")

            # Handle JSON responses directly
            if "application/json" in content_type:
                return {
                    "url": str(response.url),
                    "content_type": "json",
                    "content": response.text[:MAX_CONTENT_LENGTH],
                }

            # For HTML, strip tags
            if "text/html" in content_type:
                text = strip_html_tags(response.text)
            else:
                text = response.text

            # Truncate if too long
            if len(text) > MAX_CONTENT_LENGTH:
                text = text[:MAX_CONTENT_LENGTH] + "\n... [truncated]"

            return {
                "url": str(response.url),
                "content_type": content_type.split(";")[0] if content_type else "unknown",
                "content": text,
            }

    except httpx.TimeoutException:
        return {"error": f"Request timed out fetching {url}"}
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code} fetching {url}"}
    except Exception as e:
        logger.warning(f"Error fetching URL {url}: {e}")
        return {"error": f"Failed to fetch URL: {str(e)}"}


async def rename_chat(
    db: AsyncSession,
    thread_id: Optional[str],
    title: str,
) -> dict[str, Any]:
    """Rename the current chat thread."""
    if not thread_id:
        return {"error": "No active thread to rename"}

    # Clean and validate title
    title = title.strip()
    if not title:
        return {"error": "Title cannot be empty"}
    if len(title) > 60:
        title = title[:57] + "..."

    try:
        result = await db.execute(
            select(AgUiThread).where(AgUiThread.id == thread_id)
        )
        thread = result.scalar_one_or_none()

        if not thread:
            return {"error": f"Thread not found: {thread_id}"}

        old_title = thread.title
        thread.title = title
        thread.title_locked = True  # Prevent auto-summarization from overwriting
        await db.commit()

        logger.info(f"Renamed thread {thread_id}: '{old_title}' -> '{title}'")
        return {
            "success": True,
            "thread_id": thread_id,
            "old_title": old_title,
            "new_title": title,
        }
    except Exception as e:
        logger.error(f"Error renaming thread {thread_id}: {e}")
        return {"error": f"Failed to rename chat: {str(e)}"}


async def search_threads(
    db: AsyncSession,
    query: str,
    current_thread_id: Optional[str] = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Search previous chat threads for recipes, discussions, and brewing information."""
    if not query or not query.strip():
        return {"error": "Search query cannot be empty"}

    query = query.strip().lower()
    limit = min(max(1, limit), 10)  # Clamp between 1 and 10

    try:
        # Search in thread titles and message content
        # Use LIKE for SQLite compatibility
        search_pattern = f"%{query}%"

        # Find threads with matching titles or message content
        result = await db.execute(
            select(AgUiThread)
            .outerjoin(AgUiMessage, AgUiThread.id == AgUiMessage.thread_id)
            .where(
                or_(
                    func.lower(AgUiThread.title).like(search_pattern),
                    func.lower(AgUiMessage.content).like(search_pattern),
                )
            )
            .distinct()
            .order_by(AgUiThread.updated_at.desc())
            .limit(limit)
        )
        threads = result.scalars().all()

        if not threads:
            return {
                "results": [],
                "message": f"No conversations found matching '{query}'",
            }

        # For each matching thread, get relevant message snippets
        results = []
        for thread in threads:
            # Skip current thread
            if current_thread_id and thread.id == current_thread_id:
                continue

            # Get messages that match the query
            msg_result = await db.execute(
                select(AgUiMessage)
                .where(
                    AgUiMessage.thread_id == thread.id,
                    func.lower(AgUiMessage.content).like(search_pattern),
                )
                .order_by(AgUiMessage.created_at)
                .limit(3)  # Get up to 3 matching messages
            )
            matching_messages = msg_result.scalars().all()

            # Extract relevant snippets
            snippets = []
            for msg in matching_messages:
                content = msg.content
                # Find the query in the content and extract surrounding context
                lower_content = content.lower()
                idx = lower_content.find(query)
                if idx != -1:
                    # Extract ~150 chars around the match
                    start = max(0, idx - 75)
                    end = min(len(content), idx + len(query) + 75)
                    snippet = content[start:end]
                    if start > 0:
                        snippet = "..." + snippet
                    if end < len(content):
                        snippet = snippet + "..."
                    snippets.append({
                        "role": msg.role,
                        "snippet": snippet,
                    })

            results.append({
                "thread_id": thread.id,
                "title": thread.title or "Untitled",
                "updated_at": thread.updated_at.isoformat(),
                "snippets": snippets[:2],  # Limit to 2 snippets per thread
            })

        if not results:
            return {
                "results": [],
                "message": f"No conversations found matching '{query}' (excluding current thread)",
            }

        return {
            "results": results,
            "message": f"Found {len(results)} conversation(s) matching '{query}'",
        }

    except Exception as e:
        logger.error(f"Error searching threads for '{query}': {e}")
        return {"error": f"Failed to search conversations: {str(e)}"}

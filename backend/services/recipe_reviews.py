"""Saved AI recipe reviews: score parsing and recipe fingerprints (tilt_ui-de6v)."""
import hashlib
import json
import re
from typing import Any, Optional

from backend.models import serialize_datetime_to_utc

_SCORE = re.compile(r"Style Fit Score:?[\s*_]*(\d+(?:\.\d+)?)\s*/\s*10", re.IGNORECASE)


def parse_score(review: str) -> Optional[float]:
    """The judge's "Style Fit Score: N/10", or None when the line is missing or out of range."""
    m = _SCORE.search(review or "")
    if not m:
        return None
    score = float(m.group(1))
    return score if 0 <= score <= 10 else None


def fingerprint(document: dict[str, Any]) -> str:
    """Stable hash of a recipe's v2 document: changes only when the recipe does."""
    return hashlib.sha256(json.dumps(document, sort_keys=True, default=str).encode()).hexdigest()


def summary(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "created_at": serialize_datetime_to_utc(row.created_at),
        "score": row.score,
        "stats_score": row.stats_score,
        "style_name": row.style_name,
        "model": row.model,
        "fingerprint": row.fingerprint,
    }


def detail(row) -> dict[str, Any]:
    return {**summary(row), "review": row.review, "compliance": row.compliance}

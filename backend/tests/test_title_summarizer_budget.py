"""Regression tests for thread-title generation budget (tilt_ui-i6b).

Pi logs showed titles being truncated mid-sentence with finish_reason=max_tokens
because the old ag_ui caller passed max_tokens=30 (overriding the prompty's
own value). The model also produced full sentences instead of titles
because the prompty instruction was too soft. These tests pin the
budget + prompty content so the bug can't quietly regress.
"""

from pathlib import Path

import yaml

PROMPTS_DIR = (
    Path(__file__).resolve().parent.parent
    / "services"
    / "llm"
    / "prompts"
)
CHAT = (
    Path(__file__).resolve().parent.parent / "routers" / "chat.py"
)


def _load_prompty_front_matter(path: Path) -> dict:
    """Parse the YAML front matter from a prompty file."""
    text = path.read_text()
    assert text.startswith("---\n"), f"{path} missing front matter"
    end = text.index("\n---", 4)
    return yaml.safe_load(text[4:end])


class TestTitleSummarizerBudget:
    def test_prompty_max_tokens_at_least_60(self):
        meta = _load_prompty_front_matter(PROMPTS_DIR / "title.prompty")
        budget = meta["model"]["parameters"]["max_tokens"]
        assert budget >= 60, (
            f"title.prompty max_tokens dropped to {budget}; titles will "
            f"truncate. Keep it >=60."
        )

    def test_chat_does_not_undercut_prompty_budget(self):
        text = CHAT.read_text()
        assert "max_tokens=60" in text, (
            "chat.py title summarizer no longer passes max_tokens=60. "
            "If you changed it, also update title.prompty."
        )

    def test_prompty_instructs_title_not_sentence(self):
        text = (PROMPTS_DIR / "title.prompty").read_text().lower()
        # Spot-check that the instruction explicitly bans prose output.
        assert "do not output a full sentence" in text
        assert "good examples" in text

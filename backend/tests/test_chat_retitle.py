"""Legacy fragment titles get re-titled in the background (tilt_ui-qzk0.4)."""
import pytest
from pydantic_ai.messages import ModelRequest, UserPromptPart
from sqlalchemy.ext.asyncio import async_sessionmaker

import backend.database as db_module
from backend.models import AgUiThread, ChatHistory
from backend.routers import chat
from backend.services.chat_store import dump_history

FRAGMENT = "**y in the library...\nnext line"


def test_looks_like_content():
    for bad in [FRAGMENT, "(0 min) | 15 |", "x" * 61, "- bullet", "see [a](http://b)"]:
        assert chat.looks_like_content(bad), bad
    for ok in ["Hop Substitution Advice", "", None, "x" * 60]:
        assert not chat.looks_like_content(ok), ok


def test_snippet_title_is_plain_and_short():
    t = chat.snippet_title("## **Citra**  vs\n| Mosaic | for `IPA` " + "word " * 30)
    assert t and len(t) <= 60 and not chat.looks_like_content(t)
    assert chat.snippet_title("**|") is None


async def _thread(db, tid, title, first_user, locked=False):
    db.add(AgUiThread(id=tid, user_id="local", title=title, title_locked=locked))
    await db.flush()
    db.add(ChatHistory(thread_id=tid, user_id="local", message_count=1,
                       messages=dump_history([ModelRequest(parts=[UserPromptPart(first_user)])])))


@pytest.mark.asyncio
async def test_retitle_legacy_threads(test_db, monkeypatch):
    monkeypatch.setattr(db_module, "async_session_factory", async_sessionmaker(test_db.bind, expire_on_commit=False))
    await _thread(test_db, "frag", FRAGMENT, "## How do I **dry hop** an IPA?\nthanks")
    await _thread(test_db, "locked", FRAGMENT, "anything", locked=True)
    await _thread(test_db, "clean", "Stout Brewing Plan", "stout?")
    await test_db.commit()

    async def no_model(thread_id):  # summariser unavailable -> snippet fallback
        return None

    monkeypatch.setattr(chat, "summarize_title", no_model)
    assert await chat.retitle_legacy_threads() == 1

    test_db.expire_all()
    assert (await test_db.get(AgUiThread, "frag")).title == "How do I dry hop an IPA? thanks"
    assert (await test_db.get(AgUiThread, "locked")).title == FRAGMENT
    assert (await test_db.get(AgUiThread, "clean")).title == "Stout Brewing Plan"

    assert await chat.retitle_legacy_threads() == 0  # idempotent


@pytest.mark.asyncio
async def test_retitle_prefers_summariser(test_db, monkeypatch):
    monkeypatch.setattr(db_module, "async_session_factory", async_sessionmaker(test_db.bind, expire_on_commit=False))
    await _thread(test_db, "frag", FRAGMENT, "hops?")
    await test_db.commit()

    async def model(thread_id):
        async with db_module.async_session_factory() as db:
            t = await db.get(AgUiThread, thread_id)
            t.title = "Dry Hopping Advice"
            await db.commit()
        return "Dry Hopping Advice"

    monkeypatch.setattr(chat, "summarize_title", model)
    assert await chat.retitle_legacy_threads() == 1
    test_db.expire_all()
    assert (await test_db.get(AgUiThread, "frag")).title == "Dry Hopping Advice"

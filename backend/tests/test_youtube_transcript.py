"""YouTube transcript tool (tilt_ui-eevz.9). No network: the library call is replaced."""

import pytest

from backend.services import youtube as yt

VID = "dQw4w9WgXcQ"


@pytest.mark.parametrize("value", [
    VID,
    f"https://www.youtube.com/watch?v={VID}",
    f"https://www.youtube.com/watch?feature=share&v={VID}&t=30",
    f"https://youtu.be/{VID}?t=5",
    f"https://m.youtube.com/shorts/{VID}",
    f"https://www.youtube.com/embed/{VID}",
    f"https://www.youtube.com/live/{VID}",
    f"youtube.com/watch?v={VID}",
])
def test_video_links_are_understood(value):
    assert yt.video_id(value) == VID


@pytest.mark.parametrize("value", [
    "", "hello", f"https://example.com/watch?v={VID}", "https://www.youtube.com/watch?v=short",
    "https://www.youtube.com/channel/UC123", "http://[broken/",
])
def test_non_video_links_are_refused(value):
    assert yt.video_id(value) is None


@pytest.mark.asyncio
async def test_errors_come_back_as_tool_errors(monkeypatch):
    yt._CACHE.clear()
    monkeypatch.setattr(yt, "_fetch_sync", lambda vid: {"error": "This video has no captions (they are turned off)."})
    assert "no captions" in (await yt.get_transcript(VID))["error"]

    def boom(vid):
        raise RuntimeError("YouTube changed its page")

    monkeypatch.setattr(yt, "_fetch_sync", boom)
    assert (await yt.get_transcript(VID))["error"] == "Could not read this video's captions."


@pytest.mark.asyncio
async def test_long_transcripts_come_in_parts(monkeypatch):
    yt._CACHE.clear()
    text = "x" * (yt.PAGE_CHARS + 500)
    monkeypatch.setattr(yt, "_fetch_sync", lambda vid: {"language": "English (auto-generated)", "text": text})
    first = await yt.get_transcript(VID)
    assert len(first["content"]) == yt.PAGE_CHARS and first["next_offset"] == yt.PAGE_CHARS
    assert "mishear" in first["note"] and "Untrusted" in first["note"]
    second = await yt.get_transcript(VID, offset=first["next_offset"])
    assert len(second["content"]) == 500 and "next_offset" not in second


class _Snip:
    def __init__(self, start, text):
        self.start, self.text = start, text


class _Track:
    def __init__(self, code, generated, snips=()):
        self.language_code, self.is_generated = code, generated
        self.language = {"en": "English", "de": "German"}.get(code.split("-")[0], code)
        self._snips = list(snips)

    def fetch(self):
        return self._snips


def _fake_api(monkeypatch, tracks):
    class Api:
        def __init__(self, **kw):
            assert kw["http_client"].trust_env is False

        def list(self, vid):
            return iter(tracks)

    import youtube_transcript_api
    monkeypatch.setattr(youtube_transcript_api, "YouTubeTranscriptApi", Api)


def test_timestamps_mark_each_minute(monkeypatch):
    _fake_api(monkeypatch, [_Track("en", True, [_Snip(0, "Mash at"), _Snip(30, "sixty seven"),
                                                 _Snip(61, "Add Citra"), _Snip(3700, "Done")])])
    out = yt._fetch_sync(VID)
    assert out["text"] == "[0:00] Mash at sixty seven\n[1:01] Add Citra\n[1:01:40] Done"
    assert out["language"] == "English (auto-generated)"


def test_prefers_english_and_uploader_captions(monkeypatch):
    _fake_api(monkeypatch, [
        _Track("de", False, [_Snip(0, "deutsch")]),
        _Track("en-CA", True, [_Snip(0, "auto")]),
        _Track("en-orig", False, [_Snip(0, "uploader")]),
    ])
    assert yt._fetch_sync(VID)["text"] == "[0:00] uploader"


@pytest.mark.asyncio
async def test_reading_parts_asks_youtube_once(monkeypatch):
    calls = []

    def fetch(vid):
        calls.append(vid)
        return {"language": "English", "text": "y" * (yt.PAGE_CHARS + 10)}

    yt._CACHE.clear()
    monkeypatch.setattr(yt, "_fetch_sync", fetch)
    first = await yt.get_transcript(VID)
    await yt.get_transcript(VID, offset=first["next_offset"])
    assert calls == [VID]
    yt._CACHE.clear()


def test_session_requests_always_have_a_timeout(monkeypatch):
    seen = {}

    def fake(self, method, url, **kw):
        seen.update(kw)

    monkeypatch.setattr(yt.requests.Session, "request", fake)
    yt._TimeoutSession().get("https://www.youtube.com/")
    assert seen["timeout"] == (5, 15)

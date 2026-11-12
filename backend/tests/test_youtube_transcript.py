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
    monkeypatch.setattr(yt, "_fetch_sync", lambda vid: {"error": "This video has no captions (they are turned off)."})
    assert "no captions" in (await yt.get_transcript(VID))["error"]

    def boom(vid):
        raise RuntimeError("YouTube changed its page")

    monkeypatch.setattr(yt, "_fetch_sync", boom)
    assert (await yt.get_transcript(VID))["error"] == "Could not read this video's captions."


@pytest.mark.asyncio
async def test_long_transcripts_come_in_parts(monkeypatch):
    text = "x" * (yt.PAGE_CHARS + 500)
    monkeypatch.setattr(yt, "_fetch_sync", lambda vid: {"language": "English (auto-generated)", "text": text})
    first = await yt.get_transcript(VID)
    assert len(first["content"]) == yt.PAGE_CHARS and first["next_offset"] == yt.PAGE_CHARS
    assert "mishear" in first["note"] and "Untrusted" in first["note"]
    second = await yt.get_transcript(VID, offset=first["next_offset"])
    assert len(second["content"]) == 500 and "next_offset" not in second


def test_timestamps_mark_each_minute(monkeypatch):
    class Snip:
        def __init__(self, start, text):
            self.start, self.text = start, text

    class Transcript:
        language, is_generated = "English", True

        def fetch(self):
            return [Snip(0, "Mash at"), Snip(30, "sixty seven"), Snip(61, "Add Citra"), Snip(3700, "Done")]

    class Listing:
        def find_manually_created_transcript(self, langs):
            from youtube_transcript_api._errors import NoTranscriptFound
            raise NoTranscriptFound(VID, langs, [])

        def find_generated_transcript(self, langs):
            return Transcript()

    class Api:
        def __init__(self, **kw):
            assert kw["http_client"].trust_env is False

        def list(self, vid):
            return Listing()

    import youtube_transcript_api
    monkeypatch.setattr(youtube_transcript_api, "YouTubeTranscriptApi", Api)
    out = yt._fetch_sync(VID)
    assert out["text"] == "[0:00] Mash at sixty seven\n[1:01] Add Citra\n[1:01:40] Done"
    assert out["language"] == "English (auto-generated)"

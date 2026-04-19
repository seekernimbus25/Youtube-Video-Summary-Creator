from models import Metadata, Chapter, TranscriptSegment, TranscriptResult
from unittest.mock import MagicMock, patch


def test_metadata_defaults_chapters_to_empty_list():
    metadata = Metadata(
        title="Test Video",
        channel="Test Channel",
        duration_seconds=300,
        duration_formatted="5:00",
        thumbnail_url="https://example.com/thumb.jpg",
    )

    assert metadata.chapters == []


def test_transcript_result_preserves_timed_segments():
    result = TranscriptResult(
        text="Hello world",
        segments=[
            TranscriptSegment(text="Hello", start=0.0, duration=1.0),
            TranscriptSegment(text="world", start=1.0, duration=1.0),
        ],
    )

    assert result.text == "Hello world"
    assert len(result.segments) == 2
    assert result.segments[0].start == 0.0
    assert result.segments[1].text == "world"


def _make_ydl_info(chapters=None):
    return {
        "title": "Test Video",
        "uploader": "Test Channel",
        "duration": 300,
        "thumbnail": "https://example.com/thumb.jpg",
        "chapters": [] if chapters is None else chapters,
    }


def test_metadata_includes_chapters_when_present():
    chapters_raw = [
        {"title": "Intro", "start_time": 0.0, "end_time": 60.0},
        {"title": "Deep Dive", "start_time": 60.0, "end_time": 240.0},
        {"title": "Conclusion", "start_time": 240.0, "end_time": 300.0},
    ]
    info = _make_ydl_info(chapters=chapters_raw)

    with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = info
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl

        from services.video_service import _fetch_video_metadata_sync

        result = _fetch_video_metadata_sync("https://youtube.com/watch?v=test")

    assert len(result.chapters) == 3
    assert result.chapters[0].title == "Intro"
    assert result.chapters[0].start_time == 0.0
    assert result.chapters[1].title == "Deep Dive"
    assert result.chapters[1].start_time == 60.0


def test_metadata_has_empty_chapters_when_none():
    info = _make_ydl_info(chapters=None)

    with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = info
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl

        from services.video_service import _fetch_video_metadata_sync

        result = _fetch_video_metadata_sync("https://youtube.com/watch?v=test")

    assert result.chapters == []


def test_parse_json3_returns_segments_with_timestamps():
    import json
    from services.transcript_service import _parse_json3_with_segments

    raw = json.dumps(
        {
            "events": [
                {"tStartMs": 0, "dDurationMs": 3000, "segs": [{"utf8": "Hello world"}]},
                {"tStartMs": 5000, "dDurationMs": 2000, "segs": [{"utf8": "Next sentence"}]},
                {"tStartMs": 8000, "dDurationMs": 1500, "segs": [{"utf8": "\n"}]},
            ]
        }
    )

    result = _parse_json3_with_segments(raw)
    assert result.text == "Hello world Next sentence"
    assert len(result.segments) == 2
    assert result.segments[0].start == 0.0
    assert result.segments[0].duration == 3.0
    assert result.segments[0].text == "Hello world"
    assert result.segments[1].start == 5.0


def test_transcript_api_segments_preserved():
    from services.transcript_service import _segments_from_transcript_api_data

    raw_data = [
        {"text": "First sentence.", "start": 1.5, "duration": 2.0},
        {"text": "Second sentence.", "start": 3.5, "duration": 1.8},
    ]

    result = _segments_from_transcript_api_data(raw_data)
    assert result.text == "First sentence. Second sentence."
    assert len(result.segments) == 2
    assert result.segments[0].start == 1.5
    assert result.segments[1].start == 3.5

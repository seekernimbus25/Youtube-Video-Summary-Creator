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


def _make_summary_with_sections():
    return {
        "key_sections": [
            {
                "title": "Introduction",
                "timestamp": "0:00",
                "timestamp_seconds": 0,
                "description": "Overview of the topic",
            },
            {
                "title": "Deep Dive",
                "timestamp": "1:00",
                "timestamp_seconds": 60,
                "description": "Technical details explained",
            },
            {
                "title": "Conclusion",
                "timestamp": "4:00",
                "timestamp_seconds": 240,
                "description": "Summary and takeaways",
            },
        ],
        "screenshot_timestamps": [
            {"seconds": 5, "caption": "Intro frame", "section_title": "Introduction"},
            {"seconds": 65, "caption": "Deep dive frame", "section_title": "Deep Dive"},
        ],
        "keywords": ["AI", "technology"],
    }


def test_chapters_anchor_screenshot_timestamps():
    from main import _build_screenshot_plan

    chapters = [
        Chapter(title="Introduction", start_time=0.0, end_time=58.0),
        Chapter(title="Deep Dive", start_time=58.0, end_time=238.0),
        Chapter(title="Conclusion", start_time=238.0, end_time=300.0),
    ]

    plan = _build_screenshot_plan(
        _make_summary_with_sections(),
        duration_seconds=300,
        chapters=chapters,
        transcript_segments=[],
    )

    intro_shot = next((shot for shot in plan if shot["section_title"] == "Introduction"), None)
    assert intro_shot is not None
    assert intro_shot["window_start"] == 0
    assert intro_shot["window_end"] == 58

    deep_shot = next((shot for shot in plan if shot["section_title"] == "Deep Dive"), None)
    assert deep_shot is not None
    assert deep_shot["window_start"] == 58
    assert deep_shot["window_end"] == 238


def test_transcript_segments_anchor_when_no_chapters():
    from main import _build_screenshot_plan

    segments = [
        TranscriptSegment(text="Welcome to the introduction of our topic", start=2.0, duration=3.0),
        TranscriptSegment(text="Now let us deep dive into the technical details", start=55.0, duration=4.0),
        TranscriptSegment(text="To conclude today's session", start=235.0, duration=3.0),
    ]

    plan = _build_screenshot_plan(
        _make_summary_with_sections(),
        duration_seconds=300,
        chapters=[],
        transcript_segments=segments,
    )

    deep_shot = next((shot for shot in plan if shot["section_title"] == "Deep Dive"), None)
    assert deep_shot is not None
    assert 50 <= deep_shot["window_start"] <= 60

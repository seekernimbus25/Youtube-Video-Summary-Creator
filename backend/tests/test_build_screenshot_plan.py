from models import Metadata, Chapter, TranscriptSegment, TranscriptResult


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

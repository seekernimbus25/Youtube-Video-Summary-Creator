from utils.validators import extract_video_id


def test_extract_video_id_from_watch_url():
    assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_extract_video_id_from_short_url():
    assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_extract_video_id_rejects_invalid_url():
    assert extract_video_id("https://example.com/not-youtube") is None


def test_extract_video_id_rejects_non_youtube_domain_with_youtube_substring():
    assert extract_video_id("https://www.notyoutube.com/watch?v=dQw4w9WgXcQ") is None

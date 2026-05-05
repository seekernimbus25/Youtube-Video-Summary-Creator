from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.mark.anyio
async def test_persist_called_after_transcript_fetch():
    mock_transcript = MagicMock()
    mock_transcript.text = "hello world"
    mock_segment = MagicMock()
    mock_segment.model_dump.return_value = {"text": "hello", "start": 0.0, "duration": 5.0}
    mock_transcript.segments = [mock_segment]
    mock_transcript.model_dump.return_value = {"text": "hello world", "segments": []}

    mock_metadata = MagicMock()
    mock_metadata.title = "Test"
    mock_metadata.channel = "Ch"
    mock_metadata.duration_formatted = "1:00"
    mock_metadata.duration_seconds = 60
    mock_metadata.chapters = []
    mock_metadata.model_dump.return_value = {}

    from main import app

    with patch("main.fetch_transcript", AsyncMock(return_value=mock_transcript)), \
         patch("main.fetch_video_metadata", AsyncMock(return_value=mock_metadata)), \
         patch("main.generate_timestamped_transcript", return_value="[00:00] hello"), \
         patch("main.detect_video_type", return_value="general"), \
         patch("main.generate_summary_and_mindmap", new_callable=AsyncMock, return_value={"summary": {}, "mindmap": {}}), \
         patch("services.transcript_cache_service.persist") as mock_persist:

        client = TestClient(app)
        response = client.post(
            "/api/summarize",
            json={"url": "https://youtu.be/dQw4w9WgXcQ"},
            headers={"x-api-key": ""},
        )

    assert response.status_code == 200
    mock_persist.assert_called_once_with(
        "dQw4w9WgXcQ",
        "hello world",
        [{"text": "hello", "start": 0.0, "duration": 5.0}],
    )

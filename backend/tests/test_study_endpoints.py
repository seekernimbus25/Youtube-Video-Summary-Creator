from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def _client():
    from main import app

    return TestClient(app)


def test_flashcards_returns_409_when_no_manifest():
    with patch("services.rag_service.get_manifest", AsyncMock(return_value=None)):
        resp = _client().post("/api/flashcards", json={"video_id": "vid1"})

    assert resp.status_code == 409


def test_quiz_returns_409_when_no_manifest():
    with patch("services.rag_service.get_manifest", AsyncMock(return_value=None)):
        resp = _client().post("/api/quiz", json={"video_id": "vid1"})

    assert resp.status_code == 409


def test_flashcards_passes_buddy_headers_and_returns_payload():
    captured = {}

    async def _fake_generate(video_id, user_api_key=None, user_provider=None, user_model=None):
        captured.update({
            "video_id": video_id,
            "key": user_api_key,
            "provider": user_provider,
            "model": user_model,
        })
        return type("Resp", (), {
            "model_dump": lambda self: {
                "cards": [
                    {"id": "fc-1", "front": "Q", "back": "A", "topic": "Topic", "timestamp": "00:12"}
                ]
            }
        })()

    with patch("services.rag_service.get_manifest", AsyncMock(return_value={
        "chunking_version": "v1",
        "dense_model": "voyage-3-lite",
    })), patch("main.generate_flashcards", side_effect=_fake_generate):
        resp = _client().post(
            "/api/flashcards",
            json={"video_id": "vid1"},
            headers={
                "x-buddy-provider": "openrouter",
                "x-buddy-api-key": "key123",
                "x-buddy-model": "llama",
            },
        )

    assert resp.status_code == 200
    assert resp.json()["cards"][0]["id"] == "fc-1"
    assert captured == {
        "video_id": "vid1",
        "key": "key123",
        "provider": "openrouter",
        "model": "llama",
    }


def test_quiz_returns_controlled_error_when_generation_fails():
    with patch("services.rag_service.get_manifest", AsyncMock(return_value={
        "chunking_version": "v1",
        "dense_model": "voyage-3-lite",
    })), patch("main.generate_quiz", AsyncMock(side_effect=RuntimeError("bad json"))):
        resp = _client().post("/api/quiz", json={"video_id": "vid1"})

    assert resp.status_code == 500
    assert resp.json()["error"] == "study_generation_failed"
    assert "bad json" in resp.json()["message"]


def test_demo_flashcards_bypass_manifest_gate():
    with patch("services.rag_service.get_manifest", AsyncMock()) as mock_manifest:
        resp = _client().post("/api/flashcards", json={"video_id": "demo"})

    assert resp.status_code == 200
    assert resp.json()["cards"][0]["id"] == "fc-1"
    mock_manifest.assert_not_called()


def test_demo_quiz_bypass_manifest_gate():
    with patch("services.rag_service.get_manifest", AsyncMock()) as mock_manifest:
        resp = _client().post("/api/quiz", json={"video_id": "demo"})

    assert resp.status_code == 200
    assert resp.json()["questions"][0]["id"] == "qq-1"
    mock_manifest.assert_not_called()

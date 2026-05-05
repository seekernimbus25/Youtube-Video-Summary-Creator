from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


def _client():
    from main import app

    return TestClient(app)


def test_chat_returns_409_when_no_manifest():
    with patch("services.rag_service.get_manifest", AsyncMock(return_value=None)):
        resp = _client().post(
            "/api/chat",
            json={"video_id": "vid1", "messages": [{"role": "user", "content": "hello"}]},
        )

    assert resp.status_code == 409


def test_chat_streams_events_when_manifest_valid():
    async def _fake_chat(*args, **kwargs):
        yield {"type": "token", "text": "Here is the answer."}
        yield {"type": "done"}

    with patch("services.rag_service.get_manifest", AsyncMock(return_value={
        "chunking_version": "v1",
        "dense_model": "voyage-3-lite",
    })), \
         patch("services.claude_service.get_claude_client", return_value=(MagicMock(), "model", "anthropic")), \
         patch("main.run_chat", side_effect=_fake_chat):
        resp = _client().post(
            "/api/chat",
            json={"video_id": "vid1", "messages": [{"role": "user", "content": "hello"}]},
        )

    assert resp.status_code == 200
    assert "token" in resp.text
    assert "done" in resp.text


def test_chat_passes_x_buddy_headers():
    async def _fake_chat(*args, **kwargs):
        yield {"type": "done"}

    captured = {}

    def _capture_client(user_provider, user_api_key, user_model):
        captured.update({"provider": user_provider, "key": user_api_key, "model": user_model})
        return MagicMock(), "model", user_provider or "anthropic"

    with patch("services.rag_service.get_manifest", AsyncMock(return_value={
        "chunking_version": "v1",
        "dense_model": "voyage-3-lite",
    })), \
         patch("services.claude_service.get_claude_client", side_effect=_capture_client), \
         patch("main.run_chat", side_effect=_fake_chat):
        _client().post(
            "/api/chat",
            json={"video_id": "vid1", "messages": [{"role": "user", "content": "q"}]},
            headers={
                "x-buddy-provider": "openrouter",
                "x-buddy-api-key": "key123",
                "x-buddy-model": "llama",
            },
        )

    assert captured["provider"] == "openrouter"
    assert captured["key"] == "key123"
    assert captured["model"] == "llama"


def test_demo_chat_bypasses_manifest_gate():
    async def _fake_demo_chat(*args, **kwargs):
        yield {"type": "token", "text": "This is a demo video."}
        yield {"type": "done"}

    with patch("main.run_demo_chat", side_effect=_fake_demo_chat):
        resp = _client().post(
            "/api/chat",
            json={"video_id": "demo", "messages": [{"role": "user", "content": "hello"}]},
        )

    assert resp.status_code == 200
    assert "This is a demo video." in resp.text

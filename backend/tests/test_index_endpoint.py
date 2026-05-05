from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def _client():
    from main import app

    return TestClient(app)


def test_index_returns_200_when_manifest_valid():
    with patch("services.rag_service.get_manifest", AsyncMock(return_value={
        "chunking_version": "v1",
        "dense_model": "voyage-3-lite",
    })), patch("services.job_state_service.set_state") as mock_set_state:
        resp = _client().post("/api/index", json={"video_id": "vid1"})

    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"
    mock_set_state.assert_called_once_with("vid1", "ready")


def test_index_returns_503_when_redis_down():
    with patch("services.rag_service.get_manifest", AsyncMock(return_value=None)), \
         patch("services.job_state_service.ping", return_value=False):
        resp = _client().post("/api/index", json={"video_id": "vid1"})

    assert resp.status_code == 503


def test_index_returns_202_when_job_already_running():
    with patch("services.rag_service.get_manifest", AsyncMock()) as mock_manifest, \
         patch("services.job_state_service.ping", return_value=True), \
         patch("services.job_state_service.get", return_value={"status": "indexing"}):
        resp = _client().post("/api/index", json={"video_id": "vid1"})

    assert resp.status_code == 202
    assert resp.json()["status"] == "indexing"
    mock_manifest.assert_not_called()


def test_index_returns_202_and_starts_task_when_no_existing_job():
    with patch("services.rag_service.get_manifest", AsyncMock(return_value=None)), \
         patch("services.job_state_service.ping", return_value=True), \
         patch("services.job_state_service.get", return_value=None), \
         patch("services.job_state_service.acquire_lock", return_value=True), \
         patch("services.job_state_service.set_state"), \
         patch("services.transcript_cache_service.get", return_value={"transcript_text": "hello", "segments": []}), \
         patch("services.rag_service.chunk_transcript", return_value=[{"text": "hello", "chunk_index": 0, "start_time": 0, "end_time": 0}]), \
         patch("services.rag_service.index_video") as mock_index, \
         patch("services.rag_service.write_manifest", AsyncMock()):

        async def _fake_index(*args, **kwargs):
            yield 100

        mock_index.return_value = _fake_index()
        resp = _client().post("/api/index", json={"video_id": "vid1"})

    assert resp.status_code == 202


def test_index_returns_ready_for_demo_video():
    with patch("services.job_state_service.set_state") as mock_set_state:
        resp = _client().post("/api/index", json={"video_id": "demo"})

    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"
    mock_set_state.assert_called_once_with("demo", "ready")

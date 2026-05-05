from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def _client():
    from main import app

    return TestClient(app)


def test_status_returns_ready_when_manifest_valid():
    with patch("services.rag_service.get_manifest", AsyncMock(return_value={
        "chunking_version": "v1",
        "dense_model": "voyage-3-lite",
    })):
        resp = _client().get("/api/index/status?video_id=vid1")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_status_returns_indexing_from_job_state():
    with patch("services.rag_service.get_manifest", AsyncMock()) as mock_manifest, \
         patch("services.job_state_service.get", return_value={"status": "indexing", "progress_pct": 42}):
        resp = _client().get("/api/index/status?video_id=vid1")

    assert resp.json()["status"] == "indexing"
    assert resp.json()["progress_pct"] == 42
    mock_manifest.assert_not_called()


def test_status_returns_not_found_when_no_manifest_no_job():
    with patch("services.rag_service.get_manifest", AsyncMock(return_value=None)), \
         patch("services.job_state_service.get", return_value=None):
        resp = _client().get("/api/index/status?video_id=vid1")

    assert resp.json()["status"] == "not_found"


def test_status_returns_failed_with_error():
    with patch("services.rag_service.get_manifest", AsyncMock()) as mock_manifest, \
         patch("services.job_state_service.get", return_value={"status": "failed", "error": "transcript_not_found"}):
        resp = _client().get("/api/index/status?video_id=vid1")

    assert resp.json()["status"] == "failed"
    assert resp.json()["error"] == "transcript_not_found"
    mock_manifest.assert_not_called()


def test_status_returns_ready_for_demo_video():
    resp = _client().get("/api/index/status?video_id=demo")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"

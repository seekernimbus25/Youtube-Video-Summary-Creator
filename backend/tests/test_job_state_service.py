from unittest.mock import MagicMock, patch

import services.job_state_service as svc


def _mock_redis():
    r = MagicMock()
    r.ping.return_value = True
    r.set.return_value = True
    return r


def test_ping_returns_true_when_redis_ok():
    r = _mock_redis()
    with patch("services.job_state_service._redis", return_value=r):
        assert svc.ping() is True


def test_ping_returns_false_when_redis_down():
    r = _mock_redis()
    r.ping.side_effect = Exception("connection refused")
    with patch("services.job_state_service._redis", return_value=r):
        assert svc.ping() is False


def test_get_returns_none_on_miss():
    r = _mock_redis()
    r.get.return_value = None
    with patch("services.job_state_service._redis", return_value=r):
        assert svc.get("vid1") is None


def test_set_and_get_round_trip():
    stored = {}
    r = _mock_redis()
    r.set.side_effect = lambda k, v, ex=None, nx=None: stored.update({k: v})
    r.get.side_effect = lambda k: stored.get(k)
    with patch("services.job_state_service._redis", return_value=r):
        svc.set_state("vid1", "indexing", progress_pct=42)
        result = svc.get("vid1")
    assert result["status"] == "indexing"
    assert result["progress_pct"] == 42


def test_acquire_lock_returns_true_when_key_absent():
    r = _mock_redis()
    r.set.return_value = "OK"
    with patch("services.job_state_service._redis", return_value=r):
        assert svc.acquire_lock("vid1") is True


def test_acquire_lock_returns_false_when_key_exists():
    r = _mock_redis()
    r.set.return_value = None
    with patch("services.job_state_service._redis", return_value=r):
        assert svc.acquire_lock("vid1") is False


def test_heartbeat_calls_expire():
    r = _mock_redis()
    with patch("services.job_state_service._redis", return_value=r):
        svc.heartbeat_lock("vid1", ttl=300)
    r.expire.assert_called_once_with("index_lock:vid1", 300)


def test_release_lock_calls_delete():
    r = _mock_redis()
    with patch("services.job_state_service._redis", return_value=r):
        svc.release_lock("vid1")
    r.delete.assert_called_once_with("index_lock:vid1")

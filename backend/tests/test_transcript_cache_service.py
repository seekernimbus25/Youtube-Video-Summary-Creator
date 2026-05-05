from unittest.mock import MagicMock, patch

import services.transcript_cache_service as svc


def _mock_redis(get_val=None, set_raises=False):
    r = MagicMock()
    r.get.return_value = get_val
    if set_raises:
        r.set.side_effect = Exception("redis down")
    return r


def test_persist_and_get_round_trip():
    stored = {}

    def fake_set(key, value, ex=None):
        stored[key] = value

    def fake_get(key):
        return stored.get(key)

    r = MagicMock()
    r.set.side_effect = fake_set
    r.get.side_effect = fake_get

    with patch("services.transcript_cache_service._redis", return_value=r):
        svc.persist("vid1", "hello world", [{"start": 0, "text": "hello", "duration": 5}])
        result = svc.get("vid1")

    assert result["transcript_text"] == "hello world"
    assert result["segments"][0]["start"] == 0


def test_get_returns_none_on_miss():
    r = _mock_redis(get_val=None)
    with patch("services.transcript_cache_service._redis", return_value=r):
        assert svc.get("missing") is None


def test_persist_does_not_raise_on_redis_error():
    r = _mock_redis(set_raises=True)
    with patch("services.transcript_cache_service._redis", return_value=r):
        svc.persist("vid1", "text", [])

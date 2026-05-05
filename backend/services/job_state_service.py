import json
import logging
import os

logger = logging.getLogger(__name__)

JOB_TTL = 172800
LOCK_TTL = 300


def _redis():
    from upstash_redis import Redis

    return Redis(
        url=os.environ.get("UPSTASH_REDIS_URL", ""),
        token=os.environ.get("UPSTASH_REDIS_TOKEN", ""),
    )


def ping() -> bool:
    try:
        _redis().ping()
        return True
    except Exception:
        return False


def get(video_id: str) -> dict | None:
    try:
        r = _redis()
        raw = r.get(f"index_job:{video_id}")
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.warning("job_state get failed for %s: %s", video_id, exc)
        return None


def set_state(
    video_id: str,
    status: str,
    progress_pct: int | None = None,
    error: str | None = None,
    message: str | None = None,
) -> None:
    try:
        r = _redis()
        value: dict = {"status": status}
        if progress_pct is not None:
            value["progress_pct"] = progress_pct
        if error is not None:
            value["error"] = error
        if message is not None:
            value["message"] = message
        r.set(f"index_job:{video_id}", json.dumps(value), ex=JOB_TTL)
    except Exception as exc:
        logger.warning("job_state set failed for %s: %s", video_id, exc)


def acquire_lock(video_id: str, ttl: int = LOCK_TTL) -> bool:
    try:
        r = _redis()
        result = r.set(f"index_lock:{video_id}", "1", nx=True, ex=ttl)
        return result is not None
    except Exception as exc:
        logger.warning("acquire_lock failed for %s: %s", video_id, exc)
        return False


def heartbeat_lock(video_id: str, ttl: int = LOCK_TTL) -> None:
    try:
        _redis().expire(f"index_lock:{video_id}", ttl)
    except Exception as exc:
        logger.warning("heartbeat_lock failed for %s: %s", video_id, exc)


def release_lock(video_id: str) -> None:
    try:
        _redis().delete(f"index_lock:{video_id}")
    except Exception as exc:
        logger.warning("release_lock failed for %s: %s", video_id, exc)

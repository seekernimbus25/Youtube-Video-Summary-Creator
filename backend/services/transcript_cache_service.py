import json
import logging
import os

logger = logging.getLogger(__name__)


def _redis():
    from upstash_redis import Redis

    return Redis(
        url=os.environ.get("UPSTASH_REDIS_URL", ""),
        token=os.environ.get("UPSTASH_REDIS_TOKEN", ""),
    )


def _segment_to_dict(segment) -> dict:
    if hasattr(segment, "model_dump"):
        return segment.model_dump()
    if isinstance(segment, dict):
        return {
            "text": segment.get("text", ""),
            "start": segment.get("start", 0),
            "duration": segment.get("duration", 0),
        }
    return {
        "text": getattr(segment, "text", ""),
        "start": getattr(segment, "start", 0),
        "duration": getattr(segment, "duration", 0),
    }


def persist(video_id: str, transcript_text: str, segments: list, ttl: int = 86400) -> None:
    try:
        r = _redis()
        safe_segments = [_segment_to_dict(seg) for seg in (segments or [])]
        value = json.dumps({"transcript_text": transcript_text, "segments": safe_segments})
        r.set(f"transcript:{video_id}", value, ex=ttl)
    except Exception as exc:
        logger.warning("transcript_cache persist failed for %s: %s", video_id, exc)


def get(video_id: str) -> dict | None:
    try:
        r = _redis()
        raw = r.get(f"transcript:{video_id}")
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.warning("transcript_cache get failed for %s: %s", video_id, exc)
        return None

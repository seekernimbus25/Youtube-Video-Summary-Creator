import os
import re
import json
import tempfile
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from models import TranscriptSegment, TranscriptResult
from utils.network import without_proxy_env

logger = logging.getLogger(__name__)
executor = ThreadPoolExecutor(max_workers=2)


def _apply_ytdlp_cookie_settings(ydl_opts: dict) -> None:
    """
    Optionally enable yt-dlp cookie auth from env vars:
    - YTDLP_COOKIES_FILE=absolute/or/relative/path/to/cookies.txt
    - YTDLP_COOKIES_FROM_BROWSER=chrome[,profile][,keyring][,container]
    """
    cookie_file = os.environ.get("YTDLP_COOKIES_FILE", "").strip()
    if cookie_file:
        ydl_opts["cookiefile"] = cookie_file

    from_browser_raw = os.environ.get("YTDLP_COOKIES_FROM_BROWSER", "").strip()
    if from_browser_raw:
        parts = tuple(part.strip() for part in from_browser_raw.split(",") if part.strip())
        if parts:
            ydl_opts["cookiesfrombrowser"] = parts


def _fetch_with_ytdlp(video_url: str, video_id: str) -> TranscriptResult:
    """
    Use yt-dlp to download auto-generated or manual subtitles.
    This is the most reliable method as yt-dlp handles all edge cases.
    """
    temp_dir = tempfile.mkdtemp()
    subtitle_path = os.path.join(temp_dir, f"{video_id}")

    ydl_opts = {
        'skip_download': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['en', 'en-.*', 'en-US', 'en-GB', 'a.en'],
        'subtitlesformat': 'json3',
        'outtmpl': subtitle_path,
        'quiet': True,
        'no_warnings': True,
        'proxy': '',
    }
    _apply_ytdlp_cookie_settings(ydl_opts)

    import yt_dlp
    try:
        with without_proxy_env():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])

        # yt-dlp saves subtitles as {id}.{lang}.json3
        # Look for any subtitle file that was downloaded
        sub_file = None
        for fname in os.listdir(temp_dir):
            if fname.endswith('.json3'):
                sub_file = os.path.join(temp_dir, fname)
                break
            elif fname.endswith('.vtt') or fname.endswith('.srt'):
                sub_file = os.path.join(temp_dir, fname)
                break

        if not sub_file:
            raise FileNotFoundError("yt-dlp did not produce any subtitle files.")

        # Parse the subtitle file
        with open(sub_file, 'r', encoding='utf-8') as f:
            content = f.read()

        if sub_file.endswith('.json3'):
            return _parse_json3_with_segments(content)
        if sub_file.endswith('.vtt'):
            return TranscriptResult(text=_parse_vtt(content), segments=[])
        if sub_file.endswith('.srt'):
            return TranscriptResult(text=_parse_srt(content), segments=[])
        return TranscriptResult(text=content, segments=[])

    finally:
        # Cleanup temp files
        import shutil
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


def _parse_json3(content: str) -> str:
    """Parse YouTube json3 subtitle format."""
    try:
        data = json.loads(content)
        segments = []
        events = data.get('events', [])
        for event in events:
            segs = event.get('segs', [])
            for seg in segs:
                text = seg.get('utf8', '').strip()
                if text and text != '\n':
                    segments.append(text)
        return ' '.join(segments).replace('\n', ' ')
    except json.JSONDecodeError:
        logger.warning("Failed to parse json3, returning raw content.")
        return content


def _parse_vtt(content: str) -> str:
    """Parse WebVTT subtitle format."""
    lines = content.split('\n')
    text_lines = []
    for line in lines:
        line = line.strip()
        # Skip empty lines, headers, timestamps
        if not line or line.startswith('WEBVTT') or line.startswith('Kind:') or line.startswith('Language:'):
            continue
        if '-->' in line:
            continue
        if re.match(r'^\d+$', line):
            continue
        # Remove HTML tags
        clean = re.sub(r'<[^>]+>', '', line)
        if clean.strip():
            text_lines.append(clean.strip())
    return ' '.join(text_lines)


def _parse_srt(content: str) -> str:
    """Parse SRT subtitle format."""
    lines = content.split('\n')
    text_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.match(r'^\d+$', line):
            continue
        if '-->' in line:
            continue
        text_lines.append(line)
    return ' '.join(text_lines)


def _segments_from_transcript_api_data(data: list) -> TranscriptResult:
    """Convert youtube-transcript-api data into a text + segment result."""
    def _read_value(item, key, default=None):
        if isinstance(item, dict):
            return item.get(key, default)
        return getattr(item, key, default)

    segments = [
        TranscriptSegment(
            text=str(_read_value(item, 'text', '')).replace('\n', ' ').strip(),
            start=float(_read_value(item, 'start', 0) or 0),
            duration=float(_read_value(item, 'duration', 0) or 0),
        )
        for item in data
        if str(_read_value(item, 'text', '')).replace('\n', '').strip()
    ]
    return TranscriptResult(
        text=' '.join(segment.text for segment in segments),
        segments=segments,
    )


def generate_timestamped_transcript(segments: list[TranscriptSegment], interval_seconds: int = 20) -> str:
    """
    Format transcript as '[MM:SS] text' segments.
    Adds a timestamp entry every 'interval_seconds' to keep it concise but accurate.
    """
    if not segments:
        return ""

    output = []
    last_timestamp = -999.0

    for seg in segments:
        if seg.start - last_timestamp >= interval_seconds:
            mins = int(seg.start) // 60
            secs = int(seg.start) % 60
            timestamp_str = f"[{mins:02d}:{secs:02d}]"
            output.append(f"\n{timestamp_str} {seg.text}")
            last_timestamp = seg.start
        else:
            output.append(seg.text)

    return " ".join(output).strip()


def _parse_json3_with_segments(content: str) -> TranscriptResult:
    """Parse YouTube json3 subtitles while keeping segment timing."""
    try:
        data = json.loads(content)
        segments = []
        for event in data.get('events', []):
            segs = event.get('segs', [])
            text_parts = [seg.get('utf8', '').strip() for seg in segs]
            combined = ' '.join(part for part in text_parts if part and part != '\n').strip()
            if not combined:
                continue
            segments.append(
                TranscriptSegment(
                    text=combined,
                    start=float(event.get('tStartMs', 0)) / 1000.0,
                    duration=float(event.get('dDurationMs', 0)) / 1000.0,
                )
            )
        return TranscriptResult(
            text=' '.join(segment.text for segment in segments),
            segments=segments,
        )
    except json.JSONDecodeError:
        logger.warning("Failed to parse json3 with segments, returning raw content.")
        return TranscriptResult(text=content, segments=[])


def _fetch_with_transcript_api(video_id: str) -> TranscriptResult:
    """
    Fallback: Use youtube-transcript-api library.
    Verified to use .fetch() and .list() instance methods in local environment.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        with without_proxy_env():
            api = YouTubeTranscriptApi()
            
            # 1. Direct fetch (standard for this environment's version)
            try:
                data = api.fetch(video_id)
                if data:
                    return _segments_from_transcript_api_data(list(data))
            except Exception as e:
                logger.info(f"Direct fetch failed, trying list fallback: {e}")

            # 2. List fallback
            try:
                transcript_list = api.list(video_id)
                # Prefer English manual transcripts, then generated English transcripts.
                try:
                    transcript = transcript_list.find_transcript(['en'])
                except Exception:
                    try:
                        transcript = transcript_list.find_generated_transcript(['en'])
                    except Exception:
                        # As a last resort, just take the first available transcript.
                        transcript = next(iter(transcript_list))
                
                if transcript:
                    data = transcript.fetch()
                    if data:
                        return _segments_from_transcript_api_data(list(data))
            except Exception as e:
                logger.warning(f"Transcript list lookup failed for {video_id}: {e}")

    except Exception as e:
        logger.warning(f"youtube-transcript-api logic failed for {video_id}: {e}")
        raise

    raise ValueError("youtube-transcript-api could not find any compatible transcript.")


async def fetch_transcript(video_id: str) -> TranscriptResult:
    """
    Primary: yt-dlp (handles auto-generated captions reliably)
    Fallback: youtube-transcript-api
    """
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    loop = asyncio.get_running_loop()

    # Method 1: yt-dlp (most reliable for auto-generated subs)
    try:
        logger.info(f"Fetching transcript via yt-dlp for {video_id}")
        result = await loop.run_in_executor(executor, _fetch_with_ytdlp, video_url, video_id)
        if result and len(result.text.strip()) > 50:
            logger.info(
                f"Successfully fetched transcript via yt-dlp ({len(result.text)} chars, {len(result.segments)} segments)"
            )
            return result
        else:
            logger.warning("yt-dlp returned very short or empty transcript, trying fallback.")
    except Exception as e:
        logger.warning(f"yt-dlp transcript fetch failed: {e}")

    # Method 2: youtube-transcript-api fallback
    try:
        logger.info(f"Falling back to youtube-transcript-api for {video_id}")
        result = await loop.run_in_executor(executor, _fetch_with_transcript_api, video_id)
        if result and len(result.text.strip()) > 50:
            logger.info(
                f"Successfully fetched transcript via youtube-transcript-api ({len(result.text)} chars, {len(result.segments)} segments)"
            )
            return result
    except Exception as e:
        logger.warning(f"youtube-transcript-api also failed: {e}")

    raise RuntimeError("TRANSCRIPT_UNAVAILABLE: Could not fetch transcript using any method. The video may have no captions available.")

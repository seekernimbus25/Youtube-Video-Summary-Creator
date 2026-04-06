import os
import re
import json
import tempfile
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)
executor = ThreadPoolExecutor(max_workers=2)


def _fetch_with_ytdlp(video_url: str, video_id: str) -> str:
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
        'subtitleslangs': ['en', 'en-US', 'en-GB'],
        'subtitlesformat': 'json3',
        'outtmpl': subtitle_path,
        'quiet': True,
        'no_warnings': True,
    }

    import yt_dlp
    try:
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
            return _parse_json3(content)
        elif sub_file.endswith('.vtt'):
            return _parse_vtt(content)
        elif sub_file.endswith('.srt'):
            return _parse_srt(content)
        else:
            return content

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


def _fetch_with_transcript_api(video_id: str) -> str:
    """
    Fallback: Use youtube-transcript-api library.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()

        # Try instance .fetch() method first (v1.2.4+)
        if hasattr(api, 'fetch'):
            data = api.fetch(video_id)
            return ' '.join([item['text'] for item in data]).replace('\n', ' ')

        # Try instance .list() method
        if hasattr(api, 'list'):
            transcript_list = api.list(video_id)
            transcript = None
            try:
                transcript = transcript_list.find_transcript(['en'])
            except Exception:
                for t in transcript_list:
                    transcript = t
                    break
            if transcript:
                fetched = transcript.fetch()
                return ' '.join([item['text'] for item in fetched]).replace('\n', ' ')

    except Exception as e:
        logger.warning(f"youtube-transcript-api failed: {e}")
        raise

    raise ValueError("youtube-transcript-api could not fetch transcript.")


async def fetch_transcript(video_id: str) -> str:
    """
    Primary: yt-dlp (handles auto-generated captions reliably)
    Fallback: youtube-transcript-api
    """
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    loop = asyncio.get_running_loop()

    # Method 1: yt-dlp (most reliable for auto-generated subs)
    try:
        logger.info(f"Fetching transcript via yt-dlp for {video_id}")
        text = await loop.run_in_executor(executor, _fetch_with_ytdlp, video_url, video_id)
        if text and len(text.strip()) > 50:
            logger.info(f"Successfully fetched transcript via yt-dlp ({len(text)} chars)")
            return text
        else:
            logger.warning("yt-dlp returned very short or empty transcript, trying fallback.")
    except Exception as e:
        logger.warning(f"yt-dlp transcript fetch failed: {e}")

    # Method 2: youtube-transcript-api fallback
    try:
        logger.info(f"Falling back to youtube-transcript-api for {video_id}")
        text = await loop.run_in_executor(executor, _fetch_with_transcript_api, video_id)
        if text and len(text.strip()) > 50:
            logger.info(f"Successfully fetched transcript via youtube-transcript-api ({len(text)} chars)")
            return text
    except Exception as e:
        logger.warning(f"youtube-transcript-api also failed: {e}")

    raise RuntimeError("TRANSCRIPT_UNAVAILABLE: Could not fetch transcript using any method. The video may have no captions available.")

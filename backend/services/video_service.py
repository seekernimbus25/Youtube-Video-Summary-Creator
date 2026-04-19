import yt_dlp
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from models import Metadata, Chapter
from utils.network import without_proxy_env

logger = logging.getLogger(__name__)
executor = ThreadPoolExecutor(max_workers=2)


def _fetch_video_metadata_sync(video_url: str) -> Metadata:
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'proxy': '',
    }

    with without_proxy_env():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Extracting metadata for {video_url}")
            info = ydl.extract_info(video_url, download=False)

            duration_s = info.get('duration', 0)
            mins = duration_s // 60
            secs = duration_s % 60
            duration_formatted = f"{mins}:{secs:02d}"
            chapters_raw = info.get('chapters') or []
            chapters = [
                Chapter(
                    title=chapter.get('title', f'Chapter {index + 1}'),
                    start_time=float(chapter.get('start_time', 0)),
                    end_time=float(chapter.get('end_time', duration_s)),
                )
                for index, chapter in enumerate(chapters_raw)
            ]

            return Metadata(
                title=info.get('title', 'Unknown Title'),
                channel=info.get('uploader', 'Unknown Channel'),
                duration_seconds=duration_s,
                duration_formatted=duration_formatted,
                thumbnail_url=info.get('thumbnail', ''),
                chapters=chapters,
            )

async def fetch_video_metadata(video_url: str) -> Metadata:
    """
    Fetches video metadata using yt-dlp and returns a formatted Pydantic Metadata model.
    """
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(executor, _fetch_video_metadata_sync, video_url)
    except Exception as e:
        logger.error(f"Failed to fetch metadata for {video_url}: {e}")
        raise RuntimeError(f"VIDEO_NOT_FOUND: {str(e)}")

import yt_dlp
import logging
from typing import Dict, Any
from models import Metadata

logger = logging.getLogger(__name__)

async def fetch_video_metadata(video_url: str) -> Metadata:
    """
    Fetches video metadata using yt-dlp and returns a formatted Pydantic Metadata model.
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False, # we need the full info like duration
    }
    
    try:
        # Wrap the synchronous yt_dlp call
        # Usually it's fast enough, but we might consider ThreadPoolExecutor if it blocks
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Extracting metadata for {video_url}")
            info = ydl.extract_info(video_url, download=False)
            
            duration_s = info.get('duration', 0)
            mins = duration_s // 60
            secs = duration_s % 60
            duration_formatted = f"{mins}:{secs:02d}"

            return Metadata(
                title=info.get('title', 'Unknown Title'),
                channel=info.get('uploader', 'Unknown Channel'),
                duration_seconds=duration_s,
                duration_formatted=duration_formatted,
                thumbnail_url=info.get('thumbnail', '')
            )
            
    except Exception as e:
        logger.error(f"Failed to fetch metadata for {video_url}: {e}")
        raise RuntimeError(f"VIDEO_NOT_FOUND: {str(e)}")

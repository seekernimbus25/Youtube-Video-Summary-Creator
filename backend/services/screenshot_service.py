import os
import shutil
import tempfile
import asyncio
import logging
import time
from typing import List
import yt_dlp
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None

# Thread pool for synchronous blocking tasks like yt-dlp
executor = ThreadPoolExecutor(max_workers=4)

def cleanup_old_screenshots(static_dir: str):
    """Cleanup files > 24h old at request start"""
    now = time.time()
    try:
        os.makedirs(static_dir, exist_ok=True)
        for filename in os.listdir(static_dir):
            if filename.endswith(".jpg"):
                filepath = os.path.join(static_dir, filename)
                if os.stat(filepath).st_mtime < now - 86400:
                    try:
                        os.unlink(filepath)
                    except Exception:
                        pass
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

async def extract_screenshots_for_video(video_url: str, video_id: str, duration_seconds: int, timestamps_sec: List[int], static_dir: str) -> List[str]:
    """
    Downloads minimum video quality, extracts frames using ffmpeg concurrently,
    cleans up temp files gracefully, and returns the list of generated screenshot filenames.
    """
    if not FFMPEG_AVAILABLE:
        logger.warning("ffmpeg is not available. Skipping screenshot extraction.")
        return []
        
    cleanup_old_screenshots(static_dir)

    loop = asyncio.get_running_loop()
    temp_dir = tempfile.mkdtemp()
    temp_video_path = os.path.join(temp_dir, f"{video_id}.mp4")
    
    generated_files = []

    try:
        # Video download using yt-dlp via ThreadPoolExecutor
        def download_video():
            ydl_opts = {
                'format': 'bestvideo[height<=360][ext=mp4]/bestvideo[height<=360]/best[height<=360]/best',
                'outtmpl': temp_video_path,
                'quiet': True,
                'no_warnings': True,
                'merge_output_format': 'mp4',
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
        
        logger.info(f"Downloading short video segment to {temp_video_path}...")
        await loop.run_in_executor(executor, download_video)

        # yt-dlp may write the file with a different extension — find it
        if not os.path.exists(temp_video_path):
            candidates = [f for f in os.listdir(temp_dir) if f.startswith(video_id)]
            if candidates:
                temp_video_path = os.path.join(temp_dir, candidates[0])
                logger.info(f"Using downloaded file: {temp_video_path}")
            else:
                raise RuntimeError("Video download failed.")

        # Extract frames concurrently using ffmpeg
        async def extract_frame(sec: int) -> str:
            # Clamp timestamp: max(0, min(seconds, duration_seconds - 2))
            clamped_sec = max(0, min(sec, duration_seconds - 2))
            
            output_filename = f"{video_id}_{clamped_sec}.jpg"
            output_filepath = os.path.join(static_dir, output_filename)
            
            if os.path.exists(output_filepath):
                return output_filename

            # keyframe seek (-ss before -i) for videos > 5 min
            is_long = duration_seconds > 300
            
            if is_long:
                cmd = ["ffmpeg", "-y", "-ss", str(clamped_sec), "-i", temp_video_path, "-vframes", "1", "-q:v", "2", output_filepath]
            else:
                cmd = ["ffmpeg", "-y", "-i", temp_video_path, "-ss", str(clamped_sec), "-vframes", "1", "-q:v", "2", output_filepath]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            
            if os.path.exists(output_filepath):
                return output_filename
            return None

        # Run extraction
        tasks = [extract_frame(sec) for sec in timestamps_sec]
        results = await asyncio.gather(*tasks)
        generated_files = [res for res in results if res is not None]

    except Exception as e:
        logger.error(f"Screenshot extraction failed: {e}")
        # Explicit error but non-fatal for whole request
        return []
    finally:
        # Wrap os.unlink in try/except for Windows locks
        try:
            if os.path.exists(temp_video_path):
                os.unlink(temp_video_path)
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            logger.error(f"Failed to clean up temp files: {e}")

    return generated_files

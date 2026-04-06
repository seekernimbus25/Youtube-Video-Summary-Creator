import os
import json
import logging
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, Request

load_dotenv() # Load environment variables from .env file
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from utils.logger import get_logger
from utils.validators import extract_video_id
from models import SummarizeRequest, SSEEventResult, SSEEventError, ResultData
from services.transcript_service import fetch_transcript
from services.video_service import fetch_video_metadata
from services.claude_service import generate_summary_and_mindmap
from services.screenshot_service import extract_screenshots_for_video, FFMPEG_AVAILABLE

logger = get_logger("main")

app = FastAPI(title="YT Video Summariser")

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directories
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
os.makedirs(os.path.join(STATIC_DIR, "screenshots"), exist_ok=True)
os.makedirs(FRONTEND_DIR, exist_ok=True) # Ensure it exists if hit early

# Mount static for screenshots
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "ffmpeg_available": FFMPEG_AVAILABLE,
        "version": "1.0.0"
    }

@app.post("/api/summarize")
async def summarize(request: Request, body: SummarizeRequest):
    async def event_generator():
        try:
            url = body.url
            include_screenshots = body.include_screenshots
            
            video_id = extract_video_id(url)
            if not video_id:
                yield f"data: {json.dumps({'type': 'error', 'code': 'INVALID_URL', 'message': 'Invalid YouTube URL'})}\n\n"
                return

            def yield_progress(step: int, message: str):
                return f"data: {json.dumps({'type': 'progress', 'step': step, 'total_steps': 5, 'message': message})}\n\n"
                
            # Step 1
            yield yield_progress(1, "Fetching video metadata...")
            metadata = await fetch_video_metadata(url)
            
            # Step 2
            yield yield_progress(2, "Fetching transcript...")
            transcript_text = await fetch_transcript(video_id)
            
            # Step 3
            yield yield_progress(3, "Generating AI summary...")
            claude_val = await generate_summary_and_mindmap(
                title=metadata.title,
                channel=metadata.channel,
                duration=metadata.duration_formatted,
                transcript=transcript_text
            )
            
            # Step 4
            yield yield_progress(4, "Extracting screenshots...")
            screenshot_data = []
            if include_screenshots and FFMPEG_AVAILABLE:
                timestamps = [s.get('seconds', 0) for s in claude_val.get('summary', {}).get('screenshot_timestamps', [])]
                extracted_files = await extract_screenshots_for_video(
                    video_url=url,
                    video_id=video_id,
                    duration_seconds=metadata.duration_seconds,
                    timestamps_sec=timestamps,
                    static_dir=os.path.join(STATIC_DIR, "screenshots")
                )
                
                # Pair the files back to the timestamps to form the array
                for ts_info in claude_val.get('summary', {}).get('screenshot_timestamps', []):
                    sec = ts_info.get('seconds', 0)
                    clamped_sec = max(0, min(sec, metadata.duration_seconds - 2))
                    filename = f"{video_id}_{clamped_sec}.jpg"
                    if filename in extracted_files:
                        mins = clamped_sec // 60
                        secs = clamped_sec % 60
                        time_fmt = f"{mins}:{secs:02d}"
                        screenshot_data.append({
                            "seconds": clamped_sec,
                            "timestamp_formatted": time_fmt,
                            "caption": ts_info.get('caption', ''),
                            "url": f"/static/screenshots/{filename}",
                            "section_title": ts_info.get('section_title', '')
                        })
            elif include_screenshots and not FFMPEG_AVAILABLE:
                logger.warning("Screenshots requested but ffmpeg is missing.")
            
            # Step 5
            yield yield_progress(5, "Done!")
            
            # Final result
            result_payload = {
                "type": "result",
                "data": {
                    "video_id": video_id,
                    "metadata": metadata.model_dump(),
                    "summary": claude_val.get('summary', {}),
                    "mindmap": claude_val.get('mindmap', {}),
                    "screenshots": screenshot_data
                }
            }
            yield f"data: {json.dumps(result_payload)}\n\n"

        except Exception as e:
            logger.error(f"Error terminating SSE: {str(e)}")
            error_str = str(e)
            code = "UNKNOWN_ERROR"
            message = error_str
            if ":" in error_str:
                parts = error_str.split(":", 1)
                code = parts[0].strip()
                message = parts[1].strip()
                
            yield f"data: {json.dumps({'type': 'error', 'code': code, 'message': message})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# Mount frontend
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

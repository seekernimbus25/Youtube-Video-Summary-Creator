import os
import json
import logging
import asyncio
import time
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from utils.network import disable_system_proxies_if_configured

# Load environment variables from .env file located in the same directory as this script
base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(base_dir, ".env"))
disable_system_proxies_if_configured()
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

RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "900"))
RATE_LIMIT_MAX_REQUESTS = int(os.environ.get("RATE_LIMIT_MAX_REQUESTS", "5"))
SUMMARIZER_API_KEY = os.environ.get("SUMMARIZER_API_KEY", "").strip()
ALLOWED_ORIGINS = [
    origin.strip() for origin in os.environ.get(
        "ALLOWED_ORIGINS",
        "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000,http://127.0.0.1:3000"
    ).split(",") if origin.strip()
]
_rate_limit_store: dict[str, list[float]] = {}


def _normalize_title(value: str) -> str:
    return (value or "").strip().lower()


def _build_screenshot_plan(summary: dict, duration_seconds: int) -> list[dict]:
    sections = summary.get("key_sections", []) or []
    requested = summary.get("screenshot_timestamps", []) or []
    max_second = max(0, duration_seconds - 2)
    keywords = summary.get("keywords", []) or []

    section_windows = []
    for idx, section in enumerate(sections):
        start = max(0, min(int(section.get("timestamp_seconds", 0) or 0), max_second))
        if idx + 1 < len(sections):
            next_start = int(sections[idx + 1].get("timestamp_seconds", start + 1) or (start + 1))
            end = max(start, min(next_start - 1, max_second))
        else:
            end = max_second

        section_context_parts = [
            section.get("title", ""),
            section.get("description", ""),
            section.get("notable_detail", ""),
            " ".join(section.get("sub_points", []) or []),
            " ".join(section.get("steps", []) or []),
            " ".join(section.get("trade_offs", []) or []),
            " ".join(keywords[:10]),
        ]
        section_windows.append({
            "title": section.get("title", ""),
            "title_norm": _normalize_title(section.get("title", "")),
            "start": start,
            "end": end,
            "context": " ".join(part for part in section_context_parts if part).strip(),
        })

    used_seconds = set()
    covered_sections = set()
    section_by_title = {section["title_norm"]: section for section in section_windows if section["title_norm"]}

    def allocate_second(preferred: int, window: dict | None) -> int:
        if window:
            start, end = window["start"], window["end"]
        else:
            start, end = 0, max_second

        preferred = max(start, min(int(preferred), end))
        candidates = [preferred]

        if window:
            candidates.extend([
                min(start + 2, end),
                min(start + 5, end),
                start,
            ])

        for candidate in candidates:
            if candidate not in used_seconds:
                return candidate

        for candidate in range(start, end + 1):
            if candidate not in used_seconds:
                return candidate

        return preferred

    planned = []
    for item in requested:
        section = section_by_title.get(_normalize_title(item.get("section_title", "")))
        preferred = int(item.get("seconds", 0) or 0)

        if section:
            if preferred < section["start"] or preferred > section["end"]:
                preferred = min(section["start"] + 2, section["end"])
            covered_sections.add(section["title_norm"])

        second = allocate_second(preferred, section)
        used_seconds.add(second)
        planned.append({
            "seconds": second,
            "preferred_seconds": preferred,
            "window_start": section["start"] if section else max(0, second - 12),
            "window_end": section["end"] if section else min(max_second, second + 12),
            "caption": item.get("caption", ""),
            "section_title": item.get("section_title", ""),
            "section_context": section["context"] if section else "",
        })

    target_count = min(max(len(section_windows), 6), 8)
    for section in section_windows:
        if len(planned) >= target_count:
            break
        if section["title_norm"] in covered_sections:
            continue

        second = allocate_second(min(section["start"] + 2, section["end"]), section)
        used_seconds.add(second)
        planned.append({
            "seconds": second,
            "preferred_seconds": second,
            "window_start": section["start"],
            "window_end": section["end"],
            "caption": f"{section['title']} screenshot",
            "section_title": section["title"],
            "section_context": section["context"],
        })
        covered_sections.add(section["title_norm"])

    return planned

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _check_rate_limit(client_ip: str) -> bool:
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    recent_requests = [ts for ts in _rate_limit_store.get(client_ip, []) if ts >= window_start]
    if len(recent_requests) >= RATE_LIMIT_MAX_REQUESTS:
        _rate_limit_store[client_ip] = recent_requests
        return False
    recent_requests.append(now)
    _rate_limit_store[client_ip] = recent_requests
    return True

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
            clean_url = (url or "").strip().lower()
            logger.info(f"Received summarize request for URL: {clean_url}")

            def yield_progress(step, msg):
                return f"data: {json.dumps({'type': 'progress', 'step': step, 'total_steps': 5, 'message': msg})}\n\n"

            # 🚀 HIGH-PRIORITY DEMO HANDLING
            if "demo" in clean_url:
                logger.info("Triggering Zero-Cost Demo Mode")
                yield yield_progress(1, "Loading locally cached intelligence...")
                await asyncio.sleep(0.3)
                yield yield_progress(3, "Synthesizing demo results...")
                
                from models import Metadata
                demo_metadata = Metadata(
                    video_id="demo",
                    title="Introduction to AI Synthesis (Demo)",
                    channel="Youtube Buddy Lab",
                    duration_formatted="12:45",
                    duration_seconds=765,
                    thumbnail_url="https://images.unsplash.com/photo-1677442136019-21780ecad995?auto=format&fit=crop&q=80&w=800"
                )
                
                demo_result = {
                    "summary": {
                        "video_overview": {"title": "The Future of AI Synthesis", "elevator_pitch": "Explore how automated intelligence distillation transforms the way we consume video content."},
                        "key_insights": [
                            "AI can compress 1 hour of video into 5 minutes of strategic summary.",
                            "Structural mindmaps provide a multi-dimensional mental model of topics.",
                            "Visual context (Shots) anchor abstract concepts to real video moments."
                        ],
                        "key_sections": [
                            {"title": "The Problem of Information Overload", "timestamp": "0:00", "timestamp_seconds": 0, "description": "Why we struggle to keep up with the volume of educational video content.", "steps": ["Identify cognitive limits", "Measure watch-time vs retention"], "trade_offs": ["Time spent vs value extracted"], "notable_detail": "The average professional watches 4 hours of video weekly but retains only 15%."},
                            {"title": "The Synthesis Engine", "timestamp": "4:30", "timestamp_seconds": 270, "description": "How LLMs extract structural meaning from raw transcripts.", "steps": ["Semantic chunking", "Relational mapping"], "trade_offs": ["Depth vs Granularity"], "notable_detail": "Context-aware extraction is 4x more accurate than keyword-based methods."}
                        ],
                        "important_concepts": [
                            {"concept": "Semantic Distillation", "explanation": "The process of extracting core intent while discarding redundancy.", "why_it_matters": "Increases learning speed by up to 300%.", "example_from_video": "Reducing the transcript to its core logical skeleton."},
                            {"concept": "Visual Anchoring", "explanation": "Using screenshots to provide cognitive context to written text.", "why_it_matters": "Enhances long-term memory visual encoding."}
                        ],
                        "comparison_table": {
                            "applicable": True,
                            "headers": ["Feature", "Traditional Watching", "Youtube Buddy"],
                            "rows": [["Speed", "1x (Real-time)", "10x (Summary)"], ["Structure", "Linear", "Multidimensional"], ["Searchability", "Low", "Instant"]]
                        },
                        "practical_recommendations": [
                            "Distill complex technical roadmaps before deep-diving.",
                            "Use the Mindmap to build a mental directory before watching.",
                            "Share distilled DOCX files with teams for faster alignment."
                        ],
                        "conclusion": "AI synthesis isn't about replacing watching—it's about making your watching intentional and hyper-efficient."
                    },
                    "mindmap": {
                        "label": "AI Synthesis",
                        "children": [
                            {"label": "Core Tech", "children": [{"label": "LLMs"}, {"label": "Transcription"}]},
                            {"label": "Benefits", "children": [{"label": "Time Saving"}, {"label": "Retention"}]},
                            {"label": "Output", "children": [{"label": "Mindmaps"}, {"label": "Tables"}]}
                        ]
                    }
                }
                
                yield f"data: {json.dumps({'type': 'result', 'data': {'video_id': 'demo', 'metadata': demo_metadata.model_dump(), 'summary': demo_result['summary'], 'mindmap': demo_result['mindmap'], 'screenshots': []}})}\n\n"
                return

            video_id = extract_video_id(url)
            if not video_id:
                yield f"data: {json.dumps({'type': 'error', 'code': 'INVALID_URL', 'message': 'Invalid YouTube URL'})}\n\n"
                return

            # --- Standard Path Verification ---
            include_screenshots = body.include_screenshots
            client_ip = _get_client_ip(request)

            if SUMMARIZER_API_KEY:
                provided_api_key = request.headers.get("x-api-key", "").strip()
                if provided_api_key != SUMMARIZER_API_KEY:
                    yield f"data: {json.dumps({'type': 'error', 'code': 'UNAUTHORIZED', 'message': 'Missing or invalid API key'})}\n\n"
                    return

            if not _check_rate_limit(client_ip):
                yield f"data: {json.dumps({'type': 'error', 'code': 'RATE_LIMITED', 'message': 'Too many requests. Please try again later.'})}\n\n"
                return

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
                screenshot_plan = _build_screenshot_plan(
                    claude_val.get('summary', {}),
                    metadata.duration_seconds
                )
                extracted_files = await extract_screenshots_for_video(
                    video_url=url,
                    video_id=video_id,
                    duration_seconds=metadata.duration_seconds,
                    screenshot_requests=screenshot_plan,
                    static_dir=os.path.join(STATIC_DIR, "screenshots")
                )

                for shot in extracted_files:
                    actual_sec = int(shot.get('actual_seconds', 0) or 0)
                    clamped_sec = max(0, min(actual_sec, metadata.duration_seconds - 2))
                    filename = shot.get('filename', '')
                    if filename:
                        mins = clamped_sec // 60
                        secs = clamped_sec % 60
                        time_fmt = f"{mins}:{secs:02d}"
                        screenshot_data.append({
                            "seconds": clamped_sec,
                            "timestamp_formatted": time_fmt,
                            "caption": shot.get('caption', ''),
                            "url": f"/static/screenshots/{filename}",
                            "section_title": shot.get('section_title', '')
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

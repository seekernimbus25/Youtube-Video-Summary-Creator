import os
import json
import logging
import asyncio
import time
import re
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
from services.playwright_service import extract_screenshots_playwright, PLAYWRIGHT_AVAILABLE
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


def _find_chapter_for_section(section_title: str, section_start_sec: int, chapters: list) -> dict | None:
    """Match a summary section to a YouTube chapter by time first, then title."""
    if not chapters:
        return None
    normalized_title = _normalize_title(section_title)
    for chapter in chapters:
        if chapter.start_time <= section_start_sec <= chapter.end_time:
            return chapter
    for chapter in chapters:
        chapter_title = _normalize_title(chapter.title)
        if normalized_title and (
            normalized_title in chapter_title or chapter_title in normalized_title
        ):
            return chapter
    return None


def _find_segment_anchor(section_title: str, section_desc: str, section_start_sec: int, segments: list) -> dict | None:
    """Use weighted transcript overlap to anchor a section to a nearby transcript segment."""
    if not segments:
        return None

    title_words = {
        word.lower()
        for word in re.split(r"\W+", section_title or "")
        if len(word) > 3
    }
    desc_words = {
        word.lower()
        for word in re.split(r"\W+", section_desc or "")
        if len(word) > 3
    }
    all_words = title_words | desc_words
    if not all_words:
        return None

    best = None
    for segment in segments:
        segment_text = getattr(segment, "text", "") or ""
        segment_words = {
            word.lower()
            for word in re.split(r"\W+", segment_text)
            if len(word) > 3
        }
        if not segment_words:
            continue
        title_overlap = len(title_words & segment_words)
        desc_overlap = len(desc_words & segment_words)
        all_overlap = len(all_words & segment_words)

        seg_start = float(getattr(segment, "start", 0.0) or 0.0)
        time_distance = abs(seg_start - float(section_start_sec))
        time_penalty = min(time_distance / 20.0, 8.0)
        score = (title_overlap * 3.0) + (desc_overlap * 1.5) + (all_overlap * 0.8) - time_penalty

        if best is None or score > best["score"]:
            best = {
                "start": seg_start,
                "score": score,
                "title_overlap": title_overlap,
                "desc_overlap": desc_overlap,
                "all_overlap": all_overlap,
            }

    if not best:
        return None
    if best["title_overlap"] < 1 and best["all_overlap"] < 2:
        return None
    if best["score"] < 1.2:
        return None
    return best


def _build_screenshot_plan(
    summary: dict,
    duration_seconds: int,
    chapters: list = None,
    transcript_segments: list = None,
) -> list[dict]:
    sections = summary.get("key_sections", []) or []
    requested = summary.get("screenshot_timestamps", []) or []
    max_second = max(0, duration_seconds - 2)
    keywords = summary.get("keywords", []) or []
    chapters = chapters or []
    transcript_segments = transcript_segments or []

    section_windows = []
    for idx, section in enumerate(sections):
        claude_start = max(0, min(int(section.get("timestamp_seconds", 0) or 0), max_second))
        section_title = section.get("title", "")
        section_desc = section.get("description", "")

        chapter = _find_chapter_for_section(section_title, claude_start, chapters)
        if chapter:
            start = max(0, min(int(chapter.start_time), max_second))
            end = max(start, min(int(chapter.end_time), max_second))
            planner_source = "chapter"
            planner_confidence = 0.92
        else:
            segment_anchor = _find_segment_anchor(section_title, section_desc, claude_start, transcript_segments)
            if segment_anchor is not None:
                start = max(0, min(int(segment_anchor["start"]), max_second))
                if idx + 1 < len(sections):
                    next_start = int(
                        sections[idx + 1].get("timestamp_seconds", start + 60) or (start + 60)
                    )
                    end = max(start, min(next_start - 1, max_second))
                else:
                    end = max_second
                planner_source = "transcript"
                planner_confidence = min(0.9, 0.45 + (segment_anchor["score"] / 12.0))
            else:
                start = claude_start
                if idx + 1 < len(sections):
                    next_start = int(sections[idx + 1].get("timestamp_seconds", start + 1) or (start + 1))
                    end = max(start, min(next_start - 1, max_second))
                else:
                    end = max_second
                planner_source = "timestamp"
                planner_confidence = 0.55

        section_context_parts = [
            section_title,
            section_desc,
            section.get("notable_detail", ""),
            " ".join(section.get("sub_points", []) or []),
            " ".join(section.get("steps", []) or []),
            " ".join(section.get("trade_offs", []) or []),
            " ".join(keywords[:10]),
        ]
        section_windows.append({
            "index": idx,
            "request_id": f"sec-{idx}",
            "title": section_title,
            "title_norm": _normalize_title(section_title),
            "start": start,
            "end": end,
            "claude_start": claude_start,
            "source": planner_source,
            "planner_confidence": round(float(planner_confidence), 3),
            "context": " ".join(part for part in section_context_parts if part).strip(),
        })

    used_seconds = set()
    covered_sections = set()
    section_by_title = {section["title_norm"]: section for section in section_windows if section["title_norm"]}

    def find_section_for_title(raw_title: str) -> dict | None:
        normalized = _normalize_title(raw_title)
        if not normalized:
            return None
        direct = section_by_title.get(normalized)
        if direct:
            return direct
        for section in section_windows:
            title_norm = section["title_norm"]
            if normalized in title_norm or title_norm in normalized:
                return section
        raw_tokens = {tok for tok in re.split(r"\W+", normalized) if len(tok) > 2}
        best = None
        best_overlap = 0
        for section in section_windows:
            sec_tokens = {tok for tok in re.split(r"\W+", section["title_norm"]) if len(tok) > 2}
            overlap = len(raw_tokens & sec_tokens)
            if overlap > best_overlap:
                best_overlap = overlap
                best = section
        return best if best_overlap >= 2 else None

    def allocate_second(preferred: int, window: dict | None) -> int:
        if window:
            start, end = window["start"], window["end"]
        else:
            start, end = 0, max_second

        preferred = max(start, min(int(preferred), end))
        candidates = [preferred]

        if window:
            candidates.extend([
                min(start + 3, end),
                min(start + 6, end),
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
    for req_idx, item in enumerate(requested):
        section = find_section_for_title(item.get("section_title", ""))
        preferred = int(item.get("seconds", 0) or 0)

        if section:
            if preferred < section["start"] or preferred > section["end"]:
                preferred = min(section["start"] + 3, section["end"])
            covered_sections.add(section["title_norm"])

        second = allocate_second(preferred, section)
        used_seconds.add(second)
        planner_confidence = float(section["planner_confidence"]) if section else 0.4
        request_id = f"req-{req_idx}"
        if section:
            request_id = f"{section['request_id']}-req{req_idx}"
        planned.append({
            "request_id": request_id,
            "section_index": section["index"] if section else -1,
            "seconds": second,
            "target_seconds": second,
            "preferred_seconds": preferred,
            "window_start": section["start"] if section else max(0, second - 12),
            "window_end": section["end"] if section else min(max_second, second + 12),
            "caption": item.get("caption", ""),
            "section_title": item.get("section_title", ""),
            "section_context": section["context"] if section else "",
            "planner_source": section["source"] if section else "requested",
            "planner_confidence": round(planner_confidence, 3),
        })

    target_count = min(max(len(section_windows), 6), 8)
    for section in section_windows:
        if len(planned) >= target_count:
            break
        if section["title_norm"] in covered_sections:
            continue

        second = allocate_second(min(section["start"] + 3, section["end"]), section)
        used_seconds.add(second)
        planned.append({
            "request_id": section["request_id"],
            "section_index": section["index"],
            "seconds": second,
            "target_seconds": second,
            "preferred_seconds": second,
            "window_start": section["start"],
            "window_end": section["end"],
            "caption": f"{section['title']} screenshot",
            "section_title": section["title"],
            "section_context": section["context"],
            "planner_source": section["source"],
            "planner_confidence": round(float(section["planner_confidence"]), 3),
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
        "playwright_available": PLAYWRIGHT_AVAILABLE,
        "llm_provider": os.environ.get("LLM_PROVIDER", "anthropic").strip().lower(),
        "llm_model": (
            os.environ.get("OPENROUTER_MODEL", "").strip()
            if os.environ.get("LLM_PROVIDER", "anthropic").strip().lower() == "openrouter"
            else os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001").strip()
        ),
        "version": "2.0.0"
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
            transcript_result = await fetch_transcript(video_id)
            
            # Step 3
            yield yield_progress(3, "Generating AI summary...")
            claude_val = await generate_summary_and_mindmap(
                title=metadata.title,
                channel=metadata.channel,
                duration=metadata.duration_formatted,
                transcript=transcript_result.text
            )
            
            # Step 4
            yield yield_progress(4, "Extracting screenshots...")
            screenshot_data = []
            if include_screenshots:
                screenshot_plan = _build_screenshot_plan(
                    claude_val.get('summary', {}),
                    metadata.duration_seconds,
                    metadata.chapters,
                    transcript_result.segments,
                )
                extracted_files = []

                if FFMPEG_AVAILABLE:
                    extracted_files = await extract_screenshots_for_video(
                        video_url=body.url,
                        video_id=video_id,
                        duration_seconds=metadata.duration_seconds,
                        screenshot_requests=screenshot_plan,
                        static_dir=os.path.join(STATIC_DIR, "screenshots"),
                    )
                    if not extracted_files and PLAYWRIGHT_AVAILABLE:
                        logger.warning(
                            "ffmpeg screenshot extraction returned no frames; falling back to Playwright pipeline."
                        )

                if not extracted_files and PLAYWRIGHT_AVAILABLE:
                    extracted_files = await extract_screenshots_playwright(
                        video_id=video_id,
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
                            "request_id": shot.get("request_id", ""),
                            "section_index": int(shot.get("section_index", -1) or -1),
                            "target_seconds": int(shot.get("target_seconds", clamped_sec) or clamped_sec),
                            "selected_seconds": clamped_sec,
                            "planner_confidence": float(shot.get("planner_confidence", 0.0) or 0.0),
                            "quality_score": float(shot.get("quality_score", 0.0) or 0.0),
                            "selection_reason": shot.get("selection_reason", ""),
                            "seconds": clamped_sec,
                            "timestamp_formatted": time_fmt,
                            "caption": shot.get('caption', ''),
                            "url": f"/static/screenshots/{filename}",
                            "section_title": shot.get('section_title', '')
                        })
                if not extracted_files and not PLAYWRIGHT_AVAILABLE and not FFMPEG_AVAILABLE:
                    logger.warning("Screenshots requested but neither Playwright nor ffmpeg is available.")
            
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

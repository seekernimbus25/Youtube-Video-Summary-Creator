import os
import json
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
from models import SummarizeRequest
from services.transcript_service import fetch_transcript, generate_timestamped_transcript
from services.video_service import fetch_video_metadata
from services.claude_service import (
    detect_video_type,
    generate_summary_and_mindmap,
)

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
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
os.makedirs(FRONTEND_DIR, exist_ok=True) # Ensure it exists if hit early

@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
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

            total_steps = 5

            def yield_progress(step, msg):
                return f"data: {json.dumps({'type': 'progress', 'step': step, 'total_steps': total_steps, 'message': msg})}\n\n"

            def build_partial_payload(video_id_value, metadata_value, summary_value=None, mindmap_value=None, transcript_value=None, stage=""):
                return {
                    "type": "partial_result",
                    "stage": stage,
                    "data": {
                        "video_id": video_id_value,
                        "metadata": metadata_value.model_dump() if hasattr(metadata_value, "model_dump") else metadata_value,
                        "summary": summary_value or {},
                        "mindmap": mindmap_value or {},
                        "transcript": transcript_value.model_dump() if hasattr(transcript_value, "model_dump") else (transcript_value or {}),
                    }
                }

            # 🚀 HIGH-PRIORITY DEMO HANDLING
            if "demo" in clean_url:
                logger.info("Triggering Zero-Cost Demo Mode")
                yield yield_progress(1, "Loading locally cached intelligence...")
                await asyncio.sleep(0.3)
                yield yield_progress(3, "Building demo structure...")
                
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
                        "video_type": "lecture",
                        "video_overview": {"title": "The Future of AI Synthesis", "elevator_pitch": "Explore how automated intelligence distillation transforms the way we consume video content."},
                        "key_insights": {
                            "bullets": [
                                "AI video synthesis is positioned as a way to compress long-form content into a faster first-pass understanding without losing the main logic of the source.",
                                "The product's real value comes from structure, not just shortening: section backbones, insight bullets, and mind maps each help the viewer retain different layers of the material.",
                                "Mind maps are framed as the most visual summary surface, giving users a fast conceptual layout before they decide whether to read sections or watch the original video.",
                                "The strongest workflow is sequential: scan the key insights, inspect the section backbone, then export the distilled result for later reference or team sharing."
                            ]
                        },
                        "deep_dive": {
                            "sections": [
                                {
                                    "heading": "What This Demo Is Really Arguing",
                                    "paragraphs": [
                                        "The demo frames AI synthesis as a structural reading aid rather than a simple compression trick. Its core argument is that most people do not fail because they lack access to information; they fail because long videos hide the hierarchy of ideas, the important transitions, and the practical implications inside a linear stream."
                                    ]
                                },
                                {
                                    "heading": "How The Summary Surfaces Divide Their Jobs",
                                    "paragraphs": [
                                        "A second layer of the argument is that different summary surfaces serve different cognitive jobs. Key insights provide a fast, high-signal scan of the whole video and help the user decide whether the source is worth deeper attention.",
                                        "Key sections serve a different role. They preserve chronology and let the viewer move through the original material in a way that still respects the order in which the speaker built the argument."
                                    ]
                                },
                                {
                                    "heading": "Why The Mind Map Matters",
                                    "paragraphs": [
                                        "The mind map is positioned as the visual counterpart to the section backbone. Instead of asking the viewer to hold the whole structure in working memory, it externalizes the conceptual layout of the video."
                                    ]
                                },
                                {
                                    "heading": "What Makes The Product More Than A Short Summary",
                                    "paragraphs": [
                                        "The demo also implies that compression alone is not enough. A short summary without explicit structure can still leave the user unable to navigate, verify, or reuse what they learned.",
                                        "That is why the product leans on multiple outputs rather than one monolithic answer. The user can scan, inspect, branch outward, and export according to the task in front of them."
                                    ]
                                },
                                {
                                    "heading": "How A User Is Supposed To Work With It",
                                    "paragraphs": [
                                        "There is also a practical workflow embedded in the product design. Start with the overall synthesis, move into the section backbone to inspect the structure, and then export the relevant surface into notes or team documentation."
                                    ]
                                },
                                {
                                    "heading": "Why The Positioning Is Strong",
                                    "paragraphs": [
                                        "Taken together, the demo presents AI synthesis as a way to make video consumption more intentional, navigable, and reusable. The claim is not that watching disappears, but that structured distillation makes watching more selective and more valuable."
                                    ]
                                }
                            ]
                        },
                        "key_sections": [
                            {"title": "The Problem of Information Overload", "timestamp": "0:00", "timestamp_seconds": 0, "description": "Why we struggle to keep up with the volume of educational video content.", "steps": ["Identify cognitive limits", "Measure watch-time vs retention"], "trade_offs": ["Time spent vs value extracted"], "notable_detail": "The average professional watches 4 hours of video weekly but retains only 15%."},
                            {"title": "The Synthesis Engine", "timestamp": "4:30", "timestamp_seconds": 270, "description": "How LLMs extract structural meaning from raw transcripts.", "steps": ["Semantic chunking", "Relational mapping"], "trade_offs": ["Depth vs Granularity"], "notable_detail": "Context-aware extraction is 4x more accurate than keyword-based methods."}
                        ],
                        "important_concepts": [
                            {"concept": "Semantic Distillation", "explanation": "The process of extracting core intent while discarding redundancy.", "why_it_matters": "Increases learning speed by up to 300%.", "example_from_video": "Reducing the transcript to its core logical skeleton."},
                            {"concept": "Structural Mapping", "explanation": "Organizing ideas into an explicit hierarchy so the viewer can see how concepts connect.", "why_it_matters": "Improves recall and makes dense content easier to revisit."}
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
                    "transcript": {
                        "text": "AI synthesis helps people process long videos faster by surfacing structure, insight bullets, and reusable outputs. The demo explains that summaries are most useful when they preserve hierarchy rather than only compressing text. It also shows why exports and mind maps matter for review and collaboration.",
                        "segments": [
                            {"text": "AI synthesis helps people process long videos faster by surfacing structure, insight bullets, and reusable outputs.", "start": 0.0, "duration": 8.0},
                            {"text": "The demo explains that summaries are most useful when they preserve hierarchy rather than only compressing text.", "start": 8.0, "duration": 8.0},
                            {"text": "It also shows why exports and mind maps matter for review and collaboration.", "start": 16.0, "duration": 7.0},
                        ],
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
                
                yield f"data: {json.dumps(build_partial_payload('demo', demo_metadata, demo_result['summary'], {}, demo_result['transcript'], 'summary'))}\n\n"
                yield yield_progress(5, "Finalizing demo mindmap...")
                yield f"data: {json.dumps({'type': 'result', 'data': {'video_id': 'demo', 'metadata': demo_metadata.model_dump(), 'summary': demo_result['summary'], 'mindmap': demo_result['mindmap'], 'transcript': demo_result['transcript']}})}\n\n"
                return

            video_id = extract_video_id(url)
            if not video_id:
                yield f"data: {json.dumps({'type': 'error', 'code': 'INVALID_URL', 'message': 'Invalid YouTube URL'})}\n\n"
                return

            # --- Standard Path Verification ---
            client_ip = _get_client_ip(request)

            if SUMMARIZER_API_KEY:
                provided_api_key = request.headers.get("x-api-key", "").strip()
                if provided_api_key != SUMMARIZER_API_KEY:
                    yield f"data: {json.dumps({'type': 'error', 'code': 'UNAUTHORIZED', 'message': 'Missing or invalid API key'})}\n\n"
                    return

            if not _check_rate_limit(client_ip):
                yield f"data: {json.dumps({'type': 'error', 'code': 'RATE_LIMITED', 'message': 'Too many requests. Please try again later.'})}\n\n"
                return

            yield yield_progress(1, "Fetching video metadata...")
            metadata = await fetch_video_metadata(url)
            yield f"data: {json.dumps(build_partial_payload(video_id, metadata, stage='metadata'))}\n\n"
            
            yield yield_progress(2, "Fetching transcript...")
            transcript_result = await fetch_transcript(video_id)
            yield f"data: {json.dumps(build_partial_payload(video_id, metadata, transcript_value=transcript_result, stage='transcript'))}\n\n"

            timestamped_transcript = generate_timestamped_transcript(transcript_result.segments)
            video_type = detect_video_type(metadata.title, timestamped_transcript)
            logger.info("Detected video type: %s", video_type)
            
            user_api_key = request.headers.get("x-buddy-api-key")
            user_provider = request.headers.get("x-buddy-provider")
            user_model = request.headers.get("x-buddy-model")

            progress_messages = {
                "sections": (3, "Structuring the video outline..."),
                "summary": (4, "Writing the summary live..."),
                "mindmap": (5, "Rendering the mindmap...")
            }
            partial_queue: asyncio.Queue[dict] = asyncio.Queue()

            async def emit_partial(stage_payload: dict):
                await partial_queue.put(stage_payload)

            summarization_task = asyncio.create_task(
                generate_summary_and_mindmap(
                    title=metadata.title,
                    channel=metadata.channel,
                    duration=metadata.duration_formatted,
                    transcript=timestamped_transcript,
                    chapters=metadata.chapters,
                    transcript_segments=transcript_result.segments,
                    video_type=video_type,
                    user_api_key=user_api_key,
                    user_provider=user_provider,
                    user_model=user_model,
                    partial_callback=emit_partial,
                )
            )

            last_stage = None
            while True:
                if summarization_task.done() and partial_queue.empty():
                    break
                try:
                    stage_payload = await asyncio.wait_for(partial_queue.get(), timeout=0.2)
                except asyncio.TimeoutError:
                    continue

                stage = str(stage_payload.get("stage", "") or "")
                summary_value = stage_payload.get("summary", {}) or {}
                mindmap_value = stage_payload.get("mindmap", {}) or {}
                if stage in progress_messages and stage != last_stage:
                    step_num, message = progress_messages[stage]
                    yield yield_progress(step_num, message)
                    last_stage = stage
                yield f"data: {json.dumps(build_partial_payload(video_id, metadata, summary_value, mindmap_value, transcript_result, stage))}\n\n"

            claude_val = await summarization_task

            yield yield_progress(5, "Done!")
            
            # Final result
            result_payload = {
                "type": "result",
                "data": {
                    "video_id": video_id,
                    "metadata": metadata.model_dump(),
                    "summary": claude_val.get('summary', {}),
                    "mindmap": claude_val.get('mindmap', {}),
                    "transcript": transcript_result.model_dump(),
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

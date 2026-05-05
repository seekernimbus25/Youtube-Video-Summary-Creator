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
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from utils.logger import get_logger
from utils.validators import extract_video_id
from models import ChatRequest, IndexRequest, IndexStatusResponse, StudyRequest, SummarizeRequest
from services import job_state_service, rag_service, transcript_cache_service
from services.chat_service import chat as run_chat, demo_chat as run_demo_chat
from services.study_service import (
    generate_flashcards,
    generate_quiz,
)
from services.transcript_service import fetch_transcript, generate_timestamped_transcript
from services.video_service import fetch_video_metadata
from services.claude_service import (
    detect_video_type,
    generate_summary_and_mindmap,
)

logger = get_logger("main")
DEMO_VIDEO_ID = "demo"
DEMO_TRANSCRIPT = {
    "text": (
        "AI synthesis helps people process long videos faster by surfacing structure, insight bullets, "
        "and reusable outputs. The demo explains that summaries are most useful when they preserve "
        "hierarchy rather than only compressing text. It also shows why exports and mind maps matter "
        "for review and collaboration."
    ),
    "segments": [
        {
            "text": "AI synthesis helps people process long videos faster by surfacing structure, insight bullets, and reusable outputs.",
            "start": 0.0,
            "duration": 8.0,
        },
        {
            "text": "The demo explains that summaries are most useful when they preserve hierarchy rather than only compressing text.",
            "start": 8.0,
            "duration": 8.0,
        },
        {
            "text": "It also shows why exports and mind maps matter for review and collaboration.",
            "start": 16.0,
            "duration": 7.0,
        },
    ],
}
DEMO_FLASHCARDS = {
    "cards": [
        {
            "id": "fc-1",
            "front": "What is AI synthesis trying to improve?",
            "back": "It tries to help people process long videos faster by surfacing structure, key insights, and reusable outputs instead of forcing a full linear watch every time.",
            "topic": "Value",
            "timestamp": "00:00",
        },
        {
            "id": "fc-2",
            "front": "What is the demo's core argument about summaries?",
            "back": "The demo argues that summaries are strongest when they preserve hierarchy and structure, not when they only shorten content.",
            "topic": "Argument",
            "timestamp": "00:08",
        },
        {
            "id": "fc-3",
            "front": "Why are mind maps highlighted in the demo?",
            "back": "Mind maps are presented as a visual layer that helps users see the conceptual layout of a video quickly before deciding where to go deeper.",
            "topic": "Mindmap",
            "timestamp": "00:16",
        },
        {
            "id": "fc-4",
            "front": "What makes the product more than just a short summary?",
            "back": "Its value comes from multiple structured outputs like insights, section backbones, mind maps, and exports, each serving a different cognitive job.",
            "topic": "Product",
            "timestamp": "00:08",
        },
        {
            "id": "fc-5",
            "front": "How does the demo describe the best workflow?",
            "back": "Start with the overall synthesis, inspect the section backbone, then export the output you need for notes, collaboration, or later review.",
            "topic": "Workflow",
            "timestamp": "00:16",
        },
        {
            "id": "fc-6",
            "front": "What problem does the demo say people actually have?",
            "back": "It says the real problem is not lack of information, but difficulty seeing hierarchy, transitions, and practical implications in long linear videos.",
            "topic": "Problem",
            "timestamp": "00:00",
        },
    ]
}
DEMO_QUIZ = {
    "questions": [
        {
            "id": "qq-1",
            "prompt": "According to the demo, what makes summaries most useful?",
            "options": [
                "They preserve structure and hierarchy",
                "They remove all nuance",
                "They replace the original video entirely",
                "They focus only on one-paragraph outputs",
            ],
            "correct_index": 0,
            "explanation": "The demo repeatedly emphasizes that structure matters more than simple compression.",
            "timestamp": "00:08",
        },
        {
            "id": "qq-2",
            "prompt": "What role does the mind map play in the product?",
            "options": [
                "It stores API keys",
                "It acts as the visual summary surface",
                "It replaces transcript retrieval",
                "It measures video duration",
            ],
            "correct_index": 1,
            "explanation": "The mind map is framed as a visual way to understand the conceptual layout of the video.",
            "timestamp": "00:16",
        },
        {
            "id": "qq-3",
            "prompt": "What is the strongest workflow described in the demo?",
            "options": [
                "Watch the full video twice before reading anything",
                "Skip directly to export",
                "Scan insights, inspect sections, then export",
                "Only use the transcript",
            ],
            "correct_index": 2,
            "explanation": "The demo outlines a sequential workflow: scan insights, inspect the section backbone, then export.",
            "timestamp": "00:16",
        },
        {
            "id": "qq-4",
            "prompt": "What broader problem is the demo trying to solve?",
            "options": [
                "Information overload in long educational videos",
                "Slow internet speeds",
                "Thumbnail generation",
                "Browser cookie errors",
            ],
            "correct_index": 0,
            "explanation": "The product is positioned as a response to information overload and the difficulty of extracting value from long videos.",
            "timestamp": "00:00",
        },
    ]
}
DEMO_METADATA = {
    "video_id": DEMO_VIDEO_ID,
    "title": "Introduction to AI Synthesis (Demo)",
    "channel": "Youtube Buddy Lab",
    "duration_formatted": "12:45",
    "duration_seconds": 765,
    "thumbnail_url": "https://images.unsplash.com/photo-1677442136019-21780ecad995?auto=format&fit=crop&q=80&w=800",
}
DEMO_SUMMARY = {
    "video_type": "lecture",
    "video_overview": {
        "title": "The Future of AI Synthesis",
        "elevator_pitch": "Explore how automated intelligence distillation transforms the way we consume video content.",
    },
    "key_insights": {
        "bullets": [
            "AI video synthesis is positioned as a way to compress long-form content into a faster first-pass understanding without losing the main logic of the source.",
            "The product's real value comes from structure, not just shortening: section backbones, insight bullets, and mind maps each help the viewer retain different layers of the material.",
            "Mind maps are framed as the most visual summary surface, giving users a fast conceptual layout before they decide whether to read sections or watch the original video.",
            "The strongest workflow is sequential: scan the key insights, inspect the section backbone, then export the distilled result for later reference or team sharing.",
        ],
    },
    "deep_dive": {
        "sections": [
            {
                "heading": "What This Demo Is Really Arguing",
                "paragraphs": [
                    "The demo frames AI synthesis as a structural reading aid rather than a simple compression trick. Its core argument is that most people do not fail because they lack access to information; they fail because long videos hide the hierarchy of ideas, the important transitions, and the practical implications inside a linear stream.",
                ],
            },
            {
                "heading": "How The Summary Surfaces Divide Their Jobs",
                "paragraphs": [
                    "A second layer of the argument is that different summary surfaces serve different cognitive jobs. Key insights provide a fast, high-signal scan of the whole video and help the user decide whether the source is worth deeper attention.",
                    "Key sections serve a different role. They preserve chronology and let the viewer move through the original material in a way that still respects the order in which the speaker built the argument.",
                ],
            },
            {
                "heading": "Why The Mind Map Matters",
                "paragraphs": [
                    "The mind map is positioned as the visual counterpart to the section backbone. Instead of asking the viewer to hold the whole structure in working memory, it externalizes the conceptual layout of the video.",
                ],
            },
            {
                "heading": "What Makes The Product More Than A Short Summary",
                "paragraphs": [
                    "The demo also implies that compression alone is not enough. A short summary without explicit structure can still leave the user unable to navigate, verify, or reuse what they learned.",
                    "That is why the product leans on multiple outputs rather than one monolithic answer. The user can scan, inspect, branch outward, and export according to the task in front of them.",
                ],
            },
            {
                "heading": "How A User Is Supposed To Work With It",
                "paragraphs": [
                    "There is also a practical workflow embedded in the product design. Start with the overall synthesis, move into the section backbone to inspect the structure, and then export the relevant surface into notes or team documentation.",
                ],
            },
            {
                "heading": "Why The Positioning Is Strong",
                "paragraphs": [
                    "Taken together, the demo presents AI synthesis as a way to make video consumption more intentional, navigable, and reusable. The claim is not that watching disappears, but that structured distillation makes watching more selective and more valuable.",
                ],
            },
        ],
    },
    "key_sections": [
        {
            "title": "The Problem of Information Overload",
            "timestamp": "0:00",
            "timestamp_seconds": 0,
            "description": "Why we struggle to keep up with the volume of educational video content.",
            "steps": ["Identify cognitive limits", "Measure watch-time vs retention"],
            "trade_offs": ["Time spent vs value extracted"],
            "notable_detail": "The average professional watches 4 hours of video weekly but retains only 15%.",
        },
        {
            "title": "The Synthesis Engine",
            "timestamp": "4:30",
            "timestamp_seconds": 270,
            "description": "How LLMs extract structural meaning from raw transcripts.",
            "steps": ["Semantic chunking", "Relational mapping"],
            "trade_offs": ["Depth vs Granularity"],
            "notable_detail": "Context-aware extraction is 4x more accurate than keyword-based methods.",
        },
    ],
    "important_concepts": [
        {
            "concept": "Semantic Distillation",
            "explanation": "The process of extracting core intent while discarding redundancy.",
            "why_it_matters": "Increases learning speed by up to 300%.",
            "example_from_video": "Reducing the transcript to its core logical skeleton.",
        },
        {
            "concept": "Structural Mapping",
            "explanation": "Organizing ideas into an explicit hierarchy so the viewer can see how concepts connect.",
            "why_it_matters": "Improves recall and makes dense content easier to revisit.",
        },
    ],
    "comparison_table": {
        "applicable": True,
        "headers": ["Feature", "Traditional Watching", "Youtube Buddy"],
        "rows": [
            ["Speed", "1x (Real-time)", "10x (Summary)"],
            ["Structure", "Linear", "Multidimensional"],
            ["Searchability", "Low", "Instant"],
        ],
    },
    "practical_recommendations": [
        "Distill complex technical roadmaps before deep-diving.",
        "Use the Mindmap to build a mental directory before watching.",
        "Share distilled DOCX files with teams for faster alignment.",
    ],
    "conclusion": "AI synthesis isn't about replacing watching - it's about making your watching intentional and hyper-efficient.",
}
DEMO_MINDMAP = {
    "label": "AI Synthesis",
    "children": [
        {"label": "Core Tech", "children": [{"label": "LLMs"}, {"label": "Transcription"}]},
        {"label": "Benefits", "children": [{"label": "Time Saving"}, {"label": "Retention"}]},
        {"label": "Output", "children": [{"label": "Mindmaps"}, {"label": "Tables"}]},
    ],
}

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


def _manifest_is_current(manifest: dict | None) -> bool:
    return bool(
        manifest
        and manifest.get("chunking_version") == rag_service.CHUNKING_VERSION
        and manifest.get("dense_model") == rag_service.DENSE_MODEL
    )


def _ensure_demo_transcript_cached() -> None:
    cached = transcript_cache_service.get(DEMO_VIDEO_ID)
    if cached:
        return
    transcript_cache_service.persist(
        DEMO_VIDEO_ID,
        DEMO_TRANSCRIPT["text"],
        DEMO_TRANSCRIPT["segments"],
    )


def _demo_flashcards_response() -> dict:
    return DEMO_FLASHCARDS


def _demo_quiz_response() -> dict:
    return DEMO_QUIZ


async def _run_indexing_job(video_id: str) -> None:
    try:
        cached = transcript_cache_service.get(video_id)
        if not cached:
            job_state_service.set_state(
                video_id,
                "failed",
                error="transcript_not_found",
                message="Please re-summarize the video to enable AI Chat.",
            )
            return

        transcript_text = cached["transcript_text"]
        segments = cached["segments"]
        chunks = rag_service.chunk_transcript(transcript_text, segments)

        async for pct in rag_service.index_video(video_id, chunks):
            job_state_service.set_state(video_id, "indexing", progress_pct=pct)
            job_state_service.heartbeat_lock(video_id)

        await rag_service.write_manifest(video_id, transcript_text, len(chunks))
        job_state_service.set_state(video_id, "ready")
    except Exception as exc:
        error_text = str(exc).strip() or exc.__class__.__name__
        logger.exception("Indexing failed for %s: %s", video_id, error_text)
        job_state_service.set_state(
            video_id,
            "failed",
            error=error_text,
            message=f"Indexing failed: {error_text}",
        )
    finally:
        job_state_service.release_lock(video_id)


async def _ensure_indexing_started(video_id: str) -> str:
    state = job_state_service.get(video_id)
    if state and state.get("status") == "indexing":
        return "indexing"

    manifest = await rag_service.get_manifest(video_id)
    if _manifest_is_current(manifest):
        job_state_service.set_state(video_id, "ready")
        return "ready"

    if not job_state_service.ping():
        return "unavailable"

    if not job_state_service.acquire_lock(video_id):
        return "indexing"

    job_state_service.set_state(video_id, "indexing", progress_pct=0)
    asyncio.create_task(_run_indexing_job(video_id))
    return "indexing"

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
                demo_metadata = Metadata(**DEMO_METADATA)
                
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
                
                _ensure_demo_transcript_cached()
                yield f"data: {json.dumps(build_partial_payload(DEMO_VIDEO_ID, demo_metadata, DEMO_SUMMARY, {}, DEMO_TRANSCRIPT, 'summary'))}\n\n"
                yield yield_progress(5, "Finalizing demo mindmap...")
                yield f"data: {json.dumps({'type': 'result', 'data': {'video_id': DEMO_VIDEO_ID, 'metadata': demo_metadata.model_dump(), 'summary': DEMO_SUMMARY, 'mindmap': DEMO_MINDMAP, 'transcript': DEMO_TRANSCRIPT}})}\n\n"
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
            transcript_cache_service.persist(
                video_id,
                transcript_result.text,
                [segment.model_dump() for segment in transcript_result.segments],
            )
            indexing_state = await _ensure_indexing_started(video_id)
            if indexing_state == "unavailable":
                logger.warning("Background indexing could not start for %s because the indexing service is unavailable.", video_id)
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


@app.post("/api/index")
async def index_video(request: Request, body: IndexRequest):
    video_id = body.video_id

    if video_id == DEMO_VIDEO_ID:
        _ensure_demo_transcript_cached()
        job_state_service.set_state(video_id, "ready")
        return JSONResponse({"status": "ready"}, status_code=200)

    status = await _ensure_indexing_started(video_id)
    if status == "ready":
        return JSONResponse({"status": "ready"}, status_code=200)
    if status == "indexing":
        return JSONResponse({"status": "indexing"}, status_code=202)
    if status == "unavailable":
        return JSONResponse(
            {"error": "service_unavailable", "message": "Indexing service temporarily unavailable. Please try again."},
            status_code=503,
        )
    return JSONResponse({"error": "service_unavailable", "message": "Indexing service temporarily unavailable. Please try again."}, status_code=503)


@app.get("/api/index/status")
async def index_status(video_id: str):
    if video_id == DEMO_VIDEO_ID:
        _ensure_demo_transcript_cached()
        return IndexStatusResponse(status="ready")

    state = job_state_service.get(video_id)
    if state and state.get("status") in {"indexing", "failed"}:
        return IndexStatusResponse(
            status=state.get("status", "not_found"),
            progress_pct=state.get("progress_pct"),
            error=state.get("error"),
            message=state.get("message"),
        )

    manifest = await rag_service.get_manifest(video_id)
    if _manifest_is_current(manifest):
        return IndexStatusResponse(status="ready")

    if not state:
        return IndexStatusResponse(status="not_found")

    return IndexStatusResponse(
        status=state.get("status", "not_found"),
        progress_pct=state.get("progress_pct"),
        error=state.get("error"),
        message=state.get("message"),
    )


@app.post("/api/chat")
async def chat_endpoint(request: Request, body: ChatRequest):
    video_id = body.video_id
    user_api_key = request.headers.get("x-buddy-api-key")
    user_provider = request.headers.get("x-buddy-provider")
    user_model = request.headers.get("x-buddy-model")
    messages = [{"role": msg.role, "content": msg.content} for msg in body.messages]

    if video_id == DEMO_VIDEO_ID:
        _ensure_demo_transcript_cached()
        async def event_generator():
            try:
                async for event in run_demo_chat(video_id, messages, user_api_key, user_provider, user_model):
                    yield f"data: {json.dumps(event)}\n\n"
            except Exception as exc:
                logger.error("Demo chat error for %s: %s", video_id, exc)
                yield f"data: {json.dumps({'type': 'error', 'text': str(exc)})}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    manifest = await rag_service.get_manifest(video_id)
    if not _manifest_is_current(manifest):
        return JSONResponse({"error": "not_indexed"}, status_code=409)

    from services.claude_service import get_claude_client

    llm_client, model, provider = get_claude_client(user_provider, user_api_key, user_model)

    async def event_generator():
        try:
            async for event in run_chat(video_id, messages, provider, llm_client, model):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            logger.error("Chat error for %s: %s", video_id, exc)
            yield f"data: {json.dumps({'type': 'error', 'text': str(exc)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/flashcards")
async def flashcards_endpoint(request: Request, body: StudyRequest):
    video_id = body.video_id

    try:
        if video_id == DEMO_VIDEO_ID:
            return JSONResponse(_demo_flashcards_response(), status_code=200)
        else:
            manifest = await rag_service.get_manifest(video_id)
            if not _manifest_is_current(manifest):
                return JSONResponse({"error": "not_indexed"}, status_code=409)
            result = await generate_flashcards(
                video_id,
                user_api_key=request.headers.get("x-buddy-api-key"),
                user_provider=request.headers.get("x-buddy-provider"),
                user_model=request.headers.get("x-buddy-model"),
            )
    except Exception as exc:
        message = str(exc).strip() or repr(exc)
        logger.error("Flashcards error for %s: %s", video_id, message)
        return JSONResponse({"error": "study_generation_failed", "message": message}, status_code=500)

    return JSONResponse(result.model_dump(), status_code=200)


@app.post("/api/quiz")
async def quiz_endpoint(request: Request, body: StudyRequest):
    video_id = body.video_id

    try:
        if video_id == DEMO_VIDEO_ID:
            return JSONResponse(_demo_quiz_response(), status_code=200)
        else:
            manifest = await rag_service.get_manifest(video_id)
            if not _manifest_is_current(manifest):
                return JSONResponse({"error": "not_indexed"}, status_code=409)
            result = await generate_quiz(
                video_id,
                user_api_key=request.headers.get("x-buddy-api-key"),
                user_provider=request.headers.get("x-buddy-provider"),
                user_model=request.headers.get("x-buddy-model"),
            )
    except Exception as exc:
        message = str(exc).strip() or repr(exc)
        logger.error("Quiz error for %s: %s", video_id, message)
        return JSONResponse({"error": "study_generation_failed", "message": message}, status_code=500)

    return JSONResponse(result.model_dump(), status_code=200)

# Mount frontend
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

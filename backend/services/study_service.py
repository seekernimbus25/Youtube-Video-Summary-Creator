import asyncio
import json
import logging
from typing import Iterable, Optional

from models import FlashcardsResponse, QuizResponse
from services import rag_service, transcript_cache_service
from services.claude_service import complete_llm_text

logger = logging.getLogger(__name__)

FLASHCARD_COUNT = 8
QUIZ_COUNT = 6
QUIZ_OPTIONS = 4
SEARCH_RESULTS_PER_QUERY = 4
MAX_CONTEXT_CHUNKS = 8

STUDY_SYSTEM_PROMPT = """
You create rigorous study materials from a YouTube video transcript.

Rules:
- Use only the supplied transcript evidence.
- Keep wording specific and concrete.
- Every item must include one timestamp copied exactly from the evidence.
- Return JSON only. No markdown, prose, or code fences.
""".strip()


def _strip_code_fences(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _dedupe_chunks(chunk_lists: Iterable[list[dict]]) -> list[dict]:
    merged = []
    seen = set()
    for chunks in chunk_lists:
        for chunk in chunks:
            key = (chunk.get("timestamp", ""), chunk.get("text", ""))
            if key in seen:
                continue
            seen.add(key)
            merged.append(chunk)
    return merged[:MAX_CONTEXT_CHUNKS]


async def _gather_context(video_id: str, queries: list[str]) -> list[dict]:
    chunk_lists = await asyncio.gather(
        *(rag_service.search(video_id, query, n=SEARCH_RESULTS_PER_QUERY) for query in queries)
    )
    chunks = _dedupe_chunks(chunk_lists)
    if not chunks:
        raise RuntimeError("No indexed transcript content found for study generation.")
    return chunks


def _context_block(chunks: list[dict]) -> str:
    return "\n\n".join(
        f"Source {idx + 1} [{chunk.get('timestamp', '00:00')}]\n{chunk.get('text', '').strip()}"
        for idx, chunk in enumerate(chunks)
        if chunk.get("text")
    )


def _cached_transcript_chunks(video_id: str) -> list[dict]:
    cached = transcript_cache_service.get(video_id)
    if not cached:
        raise RuntimeError("Transcript cache not found for this video.")

    segments = cached.get("segments") or []
    chunks = []
    for seg in segments:
        start = float(seg.get("start", 0) or 0)
        mm, ss = divmod(int(start), 60)
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        chunks.append({
            "text": text,
            "timestamp": f"{mm:02d}:{ss:02d}",
            "start_time": start,
        })
    if chunks:
        return chunks

    transcript_text = str(cached.get("transcript_text", "")).strip()
    if not transcript_text:
        raise RuntimeError("Transcript cache is empty for this video.")
    return [{"text": transcript_text, "timestamp": "00:00", "start_time": 0.0}]


async def _complete_json(
    user_prompt: str,
    user_api_key: Optional[str],
    user_provider: Optional[str],
    user_model: Optional[str],
) -> dict:
    raw = await complete_llm_text(
        STUDY_SYSTEM_PROMPT,
        user_prompt,
        4000,
        user_api_key,
        user_provider,
        user_model,
    )
    return json.loads(_strip_code_fences(raw))


async def _generate_flashcards_from_chunks(
    chunks: list[dict],
    user_api_key: Optional[str],
    user_provider: Optional[str],
    user_model: Optional[str],
) -> FlashcardsResponse:
    payload = await _complete_json(
        f"""
Generate exactly {FLASHCARD_COUNT} study flashcards from the transcript evidence below.

Return JSON with this shape:
{{
  "cards": [
    {{
      "id": "fc-1",
      "front": "short prompt or term",
      "back": "clear answer or explanation",
      "topic": "brief category label",
      "timestamp": "MM:SS"
    }}
  ]
}}

Constraints:
- `front` should be concise and test recall.
- `back` should teach the idea in 1-3 sentences.
- `topic` should be 1-4 words.
- `timestamp` must match one transcript timestamp from the evidence.
- No duplicate cards.

Transcript evidence:
{_context_block(chunks)}
""".strip(),
        user_api_key,
        user_provider,
        user_model,
    )
    return FlashcardsResponse.model_validate(payload)


async def _generate_quiz_from_chunks(
    chunks: list[dict],
    user_api_key: Optional[str],
    user_provider: Optional[str],
    user_model: Optional[str],
) -> QuizResponse:
    payload = await _complete_json(
        f"""
Generate exactly {QUIZ_COUNT} multiple-choice study questions from the transcript evidence below.

Return JSON with this shape:
{{
  "questions": [
    {{
      "id": "qq-1",
      "prompt": "question text",
      "options": ["option a", "option b", "option c", "option d"],
      "correct_index": 0,
      "explanation": "why the correct answer is right",
      "timestamp": "MM:SS"
    }}
  ]
}}

Constraints:
- Each question must have exactly {QUIZ_OPTIONS} options.
- `correct_index` must be an integer from 0 to {QUIZ_OPTIONS - 1}.
- Wrong answers should be plausible but clearly false from the evidence.
- `explanation` should be 1-2 sentences and reference the evidence idea.
- `timestamp` must match one transcript timestamp from the evidence.
- No duplicate questions.

Transcript evidence:
{_context_block(chunks)}
""".strip(),
        user_api_key,
        user_provider,
        user_model,
    )
    return QuizResponse.model_validate(payload)


async def generate_flashcards(
    video_id: str,
    user_api_key: Optional[str] = None,
    user_provider: Optional[str] = None,
    user_model: Optional[str] = None,
) -> FlashcardsResponse:
    chunks = await _gather_context(
        video_id,
        [
            "core concepts definitions",
            "key lessons takeaways",
            "important facts examples",
        ],
    )
    return await _generate_flashcards_from_chunks(chunks, user_api_key, user_provider, user_model)


async def generate_quiz(
    video_id: str,
    user_api_key: Optional[str] = None,
    user_provider: Optional[str] = None,
    user_model: Optional[str] = None,
) -> QuizResponse:
    chunks = await _gather_context(
        video_id,
        [
            "important concepts and tradeoffs",
            "steps process examples",
            "specific facts and comparisons",
        ],
    )
    return await _generate_quiz_from_chunks(chunks, user_api_key, user_provider, user_model)


async def generate_flashcards_from_cached_transcript(
    video_id: str,
    user_api_key: Optional[str] = None,
    user_provider: Optional[str] = None,
    user_model: Optional[str] = None,
) -> FlashcardsResponse:
    return await _generate_flashcards_from_chunks(
        _cached_transcript_chunks(video_id),
        user_api_key,
        user_provider,
        user_model,
    )


async def generate_quiz_from_cached_transcript(
    video_id: str,
    user_api_key: Optional[str] = None,
    user_provider: Optional[str] = None,
    user_model: Optional[str] = None,
) -> QuizResponse:
    return await _generate_quiz_from_chunks(
        _cached_transcript_chunks(video_id),
        user_api_key,
        user_provider,
        user_model,
    )

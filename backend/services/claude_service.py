import os
import json
import logging
import asyncio
from anthropic import AsyncAnthropic, RateLimitError
from openai import AsyncOpenAI
from openai import RateLimitError as OpenAIRateLimitError
from openai import APIError as OpenAIAPIError
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _extract_openrouter_text(message_obj: Any) -> str:
    """Handle OpenRouter/OpenAI content variants safely."""
    if message_obj is None:
        return ""
    content = getattr(message_obj, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks: List[str] = []
        for item in content:
            if isinstance(item, dict):
                txt = item.get("text")
                if txt:
                    chunks.append(str(txt))
            else:
                txt = getattr(item, "text", None)
                if txt:
                    chunks.append(str(txt))
        return "\n".join(chunks).strip()
    txt = getattr(message_obj, "text", None)
    if txt:
        return str(txt).strip()
    return ""


def _strip_code_fences(raw: str) -> str:
    t = raw.strip()
    if t.startswith("```json"):
        t = t[7:]
    if t.startswith("```"):
        t = t[3:]
    if t.endswith("```"):
        t = t[:-3]
    return t.strip()

# Lazy initialization helper
_client = None
_model = None
_provider = None

def get_claude_client(user_provider: str = None, user_api_key: str = None, user_model: str = None):
    global _client, _model, _provider
    
    # If user provides a key/provider, we bypass the global singleton and create a one-off client
    if user_api_key:
        provider = user_provider or "anthropic"
        if provider == "openrouter":
            client = AsyncOpenAI(
                api_key=user_api_key,
                base_url="https://openrouter.ai/api/v1",
            )
            model = user_model or "openrouter/auto"
        elif provider == "openai":
            client = AsyncOpenAI(api_key=user_api_key)
            model = user_model or "gpt-4o"
        else:
            client = AsyncAnthropic(api_key=user_api_key)
            model = user_model or "claude-3-5-sonnet-20241022"
        return client, model, provider

    # Normal singleton path
    if _client is None:
        _provider = os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()

        if _provider == "openrouter":
            api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
            if not api_key:
                raise RuntimeError("CLAUDE_API_ERROR: OPENROUTER_API_KEY not found in environment. Please check your .env file.")
            _client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
            )
            _model = os.environ.get("OPENROUTER_MODEL", "openrouter/free").strip()
            if not _model:
                _model = "openrouter/free"
        else:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
            if not api_key:
                raise RuntimeError("CLAUDE_API_ERROR: ANTHROPIC_API_KEY not found in environment. Please check your .env file.")
            _client = AsyncAnthropic(api_key=api_key)
            _model = os.environ.get("CLAUDE_MODEL", "claude-3-5-sonnet-20241022").strip()

    return _client, _model, _provider


async def complete_llm_text(
    system_prompt: str,
    user_prompt: str,
    max_out_tokens: int,
    user_api_key: Optional[str] = None,
    user_provider: Optional[str] = None,
    user_model: Optional[str] = None,
    *,
    openrouter_full_fallback: bool = True,
) -> str:
    """
    One LLM call (Anthropic or OpenRouter). For map-reduce, use openrouter_full_fallback=False
    to only try the primary model (faster, fewer side requests).
    """
    client, model, provider = get_claude_client(user_provider, user_api_key, user_model)
    if provider == "openrouter":
        if openrouter_full_fallback:
            fallback_raw = os.environ.get(
                "OPENROUTER_FALLBACK_MODELS",
                "qwen/qwen3-next-80b-a3b-instruct:free,meta-llama/llama-3.3-70b-instruct:free,google/gemma-4-31b-it:free",
            ).strip()
            fallback_models = [m.strip() for m in fallback_raw.split(",") if m.strip()]
            use_low_cost_fallback = os.environ.get("OPENROUTER_USE_LOW_COST_FALLBACK", "true").strip().lower() in (
                "1", "true", "yes", "on",
            )
            low_cost_model = os.environ.get("OPENROUTER_LOW_COST_MODEL", "openai/gpt-4o-mini").strip()
            low_cost_models = [low_cost_model] if (use_low_cost_fallback and low_cost_model) else []
            candidate_models: List[str] = []
            for m in [model, *fallback_models, *low_cost_models]:
                if m and m not in candidate_models:
                    candidate_models.append(m)
        else:
            candidate_models = [model] if model else []
        if not candidate_models:
            raise RuntimeError("CLAUDE_API_ERROR: No model configured for OpenRouter.")

        last_router_error = None
        raw_content = ""
        for candidate_model in candidate_models:
            try:
                logger.info(f"OpenRouter model: {candidate_model}")
                request_kwargs: Dict[str, Any] = {
                    "model": candidate_model,
                    "temperature": 0,
                    "max_tokens": min(max_out_tokens, 16384),
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                }
                try:
                    response = await client.chat.completions.create(
                        **request_kwargs,
                        response_format={"type": "json_object"},
                    )
                except OpenAIAPIError as json_format_error:
                    json_err = str(json_format_error).lower()
                    if "response_format" in json_err or "unsupported" in json_err:
                        logger.warning("response_format not supported; retrying without it.")
                        response = await client.chat.completions.create(**request_kwargs)
                    else:
                        raise
                choices = getattr(response, "choices", None) or []
                if not choices:
                    continue
                message = getattr(choices[0], "message", None)
                raw_content = _extract_openrouter_text(message)
                if getattr(choices[0], "finish_reason", None) == "length" and not raw_content:
                    raise RuntimeError("CLAUDE_PARSE_ERROR: Response was cut off — increase max_tokens.")
                if raw_content:
                    return raw_content
            except OpenAIAPIError as e:
                err_text = str(e)
                status_code = getattr(e, "status_code", None)
                if status_code == 404 or "No endpoints found" in err_text:
                    last_router_error = e
                    continue
                raise
        if last_router_error:
            raise RuntimeError(
                "CLAUDE_API_ERROR: No OpenRouter model returned content. Set OPENROUTER_MODEL / OPENROUTER_FALLBACK_MODELS."
            )
        raise RuntimeError("CLAUDE_API_ERROR: OpenRouter returned empty content.")
    # Anthropic
    response = await client.messages.create(
        model=model,
        max_tokens=max_out_tokens,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw_content = response.content[0].text.strip()
    if response.stop_reason == "max_tokens" and not raw_content:
        raise RuntimeError("CLAUDE_PARSE_ERROR: Response was cut off — increase max_tokens.")
    return raw_content


SYSTEM_PROMPT = """
You are a world-class content analyst and knowledge synthesizer. Your job is to produce deep, insight-rich analysis of video transcripts — the kind of notes a brilliant student would take after watching the video twice and reflecting carefully.

Your summaries must:
- Capture SPECIFIC facts, numbers, examples, and arguments — never vague generalities
- Surface non-obvious insights that a casual viewer might miss
- Connect ideas across sections to reveal the video's underlying logic
- Be detailed enough that someone who never watches the video gains genuine expertise

You MUST respond ONLY with valid JSON. Do not include any conversational text or markdown codeblocks outside the JSON.
"""

def truncate_transcript(transcript: str) -> str:
    """
    Fit the transcript into the model input budget.

    The previous implementation (first 36k + last 12k only) **dropped the entire
    middle** of long videos. A 3h upload still had a ~100k+ char transcript, so the
    model only "saw" the opening (~tens of minutes) and the closing lines — hence
    key_sections clustered near the start and one late section (e.g. ~3h) with
    nothing representative of the full arc.

    Strategy now:
    - ``TRANSCRIPT_MAX_INPUT_CHARS`` (default 180_000) — raise for 200k-context
      models, lower for small OpenRouter models via env.
    - If still over the cap: take **head + several evenly-spaced middle windows
      + tail** so every part of the timeline is sampled, not a blind hole.
    """
    max_chars = int(os.environ.get("TRANSCRIPT_MAX_INPUT_CHARS", "180000"))
    if max_chars <= 0 or len(transcript) <= max_chars:
        return transcript

    head_ratio = float(os.environ.get("TRANSCRIPT_HEAD_RATIO", "0.2"))
    tail_ratio = float(os.environ.get("TRANSCRIPT_TAIL_RATIO", "0.12"))
    n_windows = max(3, min(12, int(os.environ.get("TRANSCRIPT_MID_WINDOWS", "6"))))

    head_n = max(0, int(max_chars * head_ratio))
    tail_n = max(0, int(max_chars * tail_ratio))
    overhead = 200 + n_windows * 80
    mid_budget = max_chars - head_n - tail_n - overhead
    if mid_budget < 2000:
        head_n = min(head_n, max_chars // 2)
        tail_n = min(tail_n, max_chars - head_n - 500)
        mid_budget = max(1000, max_chars - head_n - tail_n - overhead)

    head = transcript[:head_n]
    tail = transcript[-tail_n:] if tail_n else ""
    mid = transcript[head_n : len(transcript) - tail_n] if tail_n else transcript[head_n:]

    if not mid:
        return f"{head}\n\n[... truncated ...]\n\n{tail}"

    window = max(1200, mid_budget // n_windows)
    n_windows = min(n_windows, max(1, mid_budget // max(800, window // 2)))
    window = max(800, mid_budget // n_windows)

    L = len(mid)
    parts = []
    for i in range(n_windows):
        if L <= window + 1:
            parts.append(mid)
            break
        center = int((i + 0.5) * L / n_windows) if n_windows else L // 2
        a = max(0, min(center - window // 2, L - window))
        parts.append(mid[a : a + window])

    mid_blocks = "\n\n".join(
        f"--- [Middle sample {i + 1}/{len(parts)} — chronological stretch of full video] ---\n{block}"
        for i, block in enumerate(parts)
    )

    logger.warning(
        "Transcript exceeds TRANSCRIPT_MAX_INPUT_CHARS=%s; using head+spaced mid "
        "windows+tail (raw_len=%s). Set TRANSCRIPT_MAX_INPUT_CHARS higher for "
        "200k-context models if the provider allows.",
        max_chars,
        len(transcript),
    )

    return (
        f"{head}\n\n"
        f"--- [Video opening — the model should anchor early key_sections here] ---\n\n"
        f"{mid_blocks}\n\n"
        f"--- [Video closing — the model should anchor late/conclusion key_sections here] ---\n\n"
        f"{tail}"
    )


# --- Map-reduce (long video) ---

CHUNK_MAP_SYSTEM = """
You are summarizing one contiguous slice of a YouTube transcript. The full video is long; your output will be merged with other slices. Be dense and factual. Respond with JSON only, no markdown fences.
""".strip()


def _map_reduce_enabled() -> bool:
    return os.environ.get("MAP_REDUCE_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def _map_reduce_min_transcript_len() -> int:
    return int(os.environ.get("MAP_REDUCE_MIN_TRANSCRIPT_CHARS", "80000"))


def _map_chunk_target_chars() -> int:
    return int(os.environ.get("MAP_CHUNK_TARGET_CHARS", "45000"))


def _map_max_chunks() -> int:
    return int(os.environ.get("MAP_REDUCE_MAX_CHUNKS", "16"))


def _map_concurrency() -> int:
    return max(1, int(os.environ.get("MAP_REDUCE_CONCURRENCY", "2")))


def split_transcript_for_map(transcript: str) -> List[str]:
    """Equal-sized sequential chunks; each fits comfortably in a single context with the map prompt."""
    if not _map_reduce_enabled() or len(transcript) < _map_reduce_min_transcript_len():
        return [transcript]
    L = len(transcript)
    target = _map_chunk_target_chars()
    max_c = _map_max_chunks()
    n = min(max_c, max(1, (L + target - 1) // target))
    if n <= 1:
        return [transcript]
    size = (L + n - 1) // n
    chunks: List[str] = []
    i = 0
    while i < L:
        end = min(i + size, L)
        chunk = transcript[i:end]
        if len(chunk) < 500 and chunks:
            chunks[-1] = chunks[-1] + chunk
        else:
            chunks.append(chunk)
        i = end
    return chunks if len(chunks) > 1 else [transcript]


def _map_chunk_user_prompt(
    title: str,
    channel: str,
    duration: str,
    chunk_index: int,
    num_chunks: int,
    chunk_text: str,
) -> str:
    return f"""Video context (shared across all parts):
Title: {title}
Channel: {channel}
Stated duration: {duration}
This is PART {chunk_index + 1} of {num_chunks} of the full timestamped transcript. [MM:SS] or [H:MM:SS] marks refer to the real video timeline.

Transcript (this part only):
{chunk_text}

Return a single JSON object with this schema (all fields required; use [] or "" if nothing applies):
{{
  "chunk_index": {chunk_index},
  "part_of": {num_chunks},
  "summary_paragraph": "3-5 sentences covering what happens in this span only, with specifics (names, numbers, tools) when present",
  "subsection_candidates": [
    {{
      "title": "Short section title for this time span",
      "timestamp": "MM:SS or H:MM:SS as first seen in this chunk (must match transcript labels)",
      "timestamp_seconds": <integer, seconds from video start, infer from the bracket labels>,
      "description": "1-2 sentences",
      "steps": ["process step if any, else []"],
      "notable_detail": "one concrete fact or empty string"
    }}
  ],
  "insight_seeds": ["2-4 specific, evidence-backed insights that refer only to this part"],
  "concept_seeds": [{{"concept": "name", "note": "1 sentence"}}],
  "keywords_local": ["terms named in this chunk"]
}}
""".strip()


def _reduce_user_prompt(
    title: str,
    channel: str,
    duration: str,
    chunk_json_lines: str,
    num_map_parts: int,
) -> str:
    return f"""You are producing the final deliverable for a long YouTube video. Below are structured notes from {num_map_parts} sequential parts of the full transcript (map phase). Synthesize them into one coherent analysis — do not treat any part as more important by position; the video is long and content is distributed.

Video:
Title: {title}
Channel: {channel}
Duration: {duration}

MAP PHASE NOTES (JSON lines, in timeline order):
{chunk_json_lines}

Task: produce the same comprehensive JSON you would for a full transcript read, but using ONLY these notes plus logical merging (no invention). Deduplicate overlapping subsection_candidates into unified key_sections with correct timestamps. Include early, middle, and late key_sections when the notes support that.

The JSON structure MUST match the following (same as single-pass full analysis):

{{
  "summary": {{
    "video_overview": {{
      "title": "{title}",
      "channel": "{channel}",
      "duration": "{duration}",
      "main_topic": "...",
      "elevator_pitch": "..."
    }},
    "key_sections": [ ... same shape as your standard long-form key_sections ... ],
    "key_insights": [ ... 6-12 items ... ],
    "important_concepts": [ ... ],
    "comparison_table": {{ "applicable": true/false, "headers": [], "rows": [] }},
    "practical_recommendations": [ ... ],
    "conclusion": "...",
    "keywords": [ ... ],
    "action_items": [ ... ],
    "screenshot_timestamps": [ {{ "seconds": 120, "caption": "...", "section_title": "..." }} ]
  }},
  "mindmap": {{
    "id": "root",
    "label": "...",
    "category": "root",
    "children": [ ... same nested id/label/category/children as standard ... ]
  }}
}}

Rules:
- key_sections: aim for 8-15 sections for very long content if the notes support it; each needs timestamp, timestamp_seconds, description, steps, sub_points, trade_offs, notable_detail.
- sub_points: merge from concept_seeds and subsection candidates; no empty filler.
- screenshot_timestamps: 6-12 items with seconds and section_title matching a key_sections title.
- mindmap: 4-7 main branches, leaves are substantive sentences.
- Return valid JSON only, no ``` fences.
"""


async def _map_one_chunk(
    *,
    title: str,
    channel: str,
    duration: str,
    chunk: str,
    idx: int,
    total: int,
    user_api_key: Optional[str],
    user_provider: Optional[str],
    user_model: Optional[str],
) -> Dict[str, Any]:
    u = _map_chunk_user_prompt(title, channel, duration, idx, total, chunk)
    raw = await complete_llm_text(
        CHUNK_MAP_SYSTEM,
        u,
        4096,
        user_api_key,
        user_provider,
        user_model,
        openrouter_full_fallback=False,
    )
    t = _strip_code_fences(raw)
    return json.loads(t)


async def run_map_reduce_summarization(
    title: str,
    channel: str,
    duration: str,
    full_transcript: str,
    user_api_key: Optional[str] = None,
    user_provider: Optional[str] = None,
    user_model: Optional[str] = None,
) -> Dict[str, Any]:
    chunks = split_transcript_for_map(full_transcript)
    if len(chunks) <= 1:
        raise RuntimeError("internal: run_map_reduce called with single chunk")

    logger.info("Map-reduce: %s transcript chars → %s chunks", len(full_transcript), len(chunks))
    conc = _map_concurrency()
    sem = asyncio.Semaphore(conc)

    async def _protected(i: int, text: str) -> Tuple[int, Dict[str, Any]]:
        async with sem:
            for attempt in range(3):
                try:
                    data = await _map_one_chunk(
                        title=title,
                        channel=channel,
                        duration=duration,
                        chunk=text,
                        idx=i,
                        total=len(chunks),
                        user_api_key=user_api_key,
                        user_provider=user_provider,
                        user_model=user_model,
                    )
                    return (i, data)
                except (json.JSONDecodeError, Exception) as e:
                    if attempt == 2:
                        logger.error("Map chunk %s failed: %s", i, e)
                        raise
                    await asyncio.sleep(1.5 * (attempt + 1))
            raise RuntimeError(f"Map chunk {i} failed after retries")

    results = await asyncio.gather(*[_protected(i, c) for i, c in enumerate(chunks)])
    results.sort(key=lambda x: x[0])
    merged_lines: List[str] = []
    for _i,obj in results:
        merged_lines.append("---CHUNK-JSON---")
        merged_lines.append(json.dumps(obj, ensure_ascii=False))
    chunk_block = "\n".join(merged_lines)

    max_reduce = int(os.environ.get("REDUCE_MAX_INPUT_CHARS", "200000"))
    if len(chunk_block) > max_reduce - 8000:
        logger.warning(
            "Map JSON for reduce is %s chars (soft cap %s); trimming with head+tail.",
            len(chunk_block),
            max_reduce,
        )
        budget = max_reduce - 8000
        head = int(budget * 0.78)
        tail = budget - head
        chunk_block = (
            chunk_block[:head]
            + "\n\n[... OMITTED MIDDLE OF MAP JSON; chunk_index order is chronological ...]\n\n"
            + chunk_block[-tail:]
        )
    reduce_in = _reduce_user_prompt(title, channel, duration, chunk_block, len(chunks))
    raw_final = await complete_llm_text(
        SYSTEM_PROMPT,
        reduce_in,
        16000,
        user_api_key,
        user_provider,
        user_model,
        openrouter_full_fallback=True,
    )
    return json.loads(_strip_code_fences(raw_final))


async def generate_summary_and_mindmap_single_pass(
    title: str, channel: str, duration: str, transcript: str, user_api_key: str = None, user_provider: str = None, user_model: str = None) -> Dict[str, Any]:
    """Original single-LLM path (transcript may be pre-truncated)."""
    trimmed_transcript = truncate_transcript(transcript)
    user_prompt = f"""
Analyze the following YouTube video with deep, expert-level attention.

Title: {title}
Channel: {channel}
Duration: {duration}

Transcript:
{trimmed_transcript}

Produce a comprehensive study-note-quality analysis. Think of it as the notes a brilliant student would write after watching the video twice — specific, structured, and genuinely useful to someone who never watches it.

Respond strictly with a JSON object following this exact schema:

{{
  "summary": {{
    "video_overview": {{
      "title": "...",
      "channel": "...",
      "duration": "...",
      "main_topic": "One precise sentence describing what this video is fundamentally about",
      "elevator_pitch": "2-3 sentences covering: the core argument or story arc, what methods/approaches are presented, and what the viewer will walk away knowing"
    }},
    "key_sections": [
      {{
        "title": "Descriptive section title",
        "timestamp": "01:23",
        "timestamp_seconds": 83,
        "description": "2-3 sentence overview of what this section covers and why it matters in the context of the full video",
        "steps": ["If this section demonstrates a process or how-to, list each step the speaker walks through. Empty list [] if not a process section."],
        "sub_points": ["Key sub-points, arguments, or facts covered in this section — include specific names, numbers, tools, or claims from the transcript", "another sub-point"],
        "trade_offs": ["If this section discusses a method/approach, list its trade-offs or limitations. Empty list [] if not applicable."],
        "notable_detail": "One concrete fact, stat, quote, or example from this section worth highlighting — or empty string if none"
      }}
    ],
    "key_insights": [
      "Specific, non-obvious, share-worthy insight — not a generic observation. Must include the actual evidence or reasoning from the video. Format: claim + why/evidence."
    ],
    "important_concepts": [
      {{
        "concept": "Concept name",
        "explanation": "3-5 sentence explanation covering what it is, how it works, and its role in the video's context",
        "why_it_matters": "1-2 sentences on the practical significance",
        "example_from_video": "The specific example, analogy, or demonstration the speaker used"
      }}
    ],
    "comparison_table": {{
      "applicable": true,
      "headers": ["Option/Method", "Performance", "Cost", "Best For", "Trade-offs"],
      "rows": [
        ["Option name", "performance detail", "cost detail", "use case", "trade-off"]
      ]
    }},
    "practical_recommendations": [
      "Concrete, actionable recommendation based on the video — tied to a specific use case or condition (e.g., 'If X, then do Y because Z')"
    ],
    "conclusion": "3-5 sentence synthesis: what was covered, what the presenter's overall conclusion was, and the key takeaway message",
    "keywords": ["keyword1", "keyword2"],
    "action_items": ["Immediate actionable step the viewer can take"],
    "screenshot_timestamps": [
      {{ "seconds": 120, "caption": "descriptive caption of what is shown on screen", "section_title": "matching section title" }}
    ]
  }},
  "mindmap": {{
    "id": "root",
    "label": "Central thesis (max 35 chars)",
    "category": "root",
    "children": [
      {{
        "id": "branch-1",
        "label": "Major Theme (max 35 chars)",
        "category": "concept",
        "children": [
          {{
            "id": "branch-1-1",
            "label": "Key sub-concept or point",
            "category": "data",
            "children": [
              {{
                "id": "branch-1-1-1",
                "label": "Specific detail or example",
                "category": "example",
                "children": []
              }}
            ]
          }}
        ]
      }}
    ]
  }}
}}

RULES — follow every one:

SUMMARY RULES:
1. key_sections: Identify 5-8 distinct sections. Use the [MM:SS] timestamps in the transcript to determine precise start times. For tutorial/how-to videos, steps[] must list each actual step the speaker demonstrates. sub_points[] must include specific names, numbers, or tools mentioned — no vague filler. If the input contains multiple "Middle sample" bands (common for long videos), you still receive material from the full timeline — **spread** key_sections across the whole video (early, middle, and late), not only the first and last few minutes.
2. key_insights: 6-10 points. Each must be specific with evidence — "X because Y, demonstrated by Z" — not "the speaker discusses X". Use timestamps to reference evidence where possible.
3. important_concepts: 4-8 concepts with substantive explanations.
4. comparison_table: Set applicable=true only if the video compares multiple options/methods/tools. If applicable, create a table reflecting the actual comparisons made in the video. If not applicable, set applicable=false and use empty arrays for headers and rows.
5. practical_recommendations: 4-8 recommendations tied to specific conditions or use cases.
6. conclusion: Must reflect the presenter's actual closing argument, not just a restatement of the title.
7. keywords: 8-15 specific technical terms or named entities from the video.
8. action_items: If none exist, return [].
9. screenshot_timestamps: Return 6-10 moments, aiming for roughly one per major section. section_title must exactly match one of key_sections.title values. Pick the exact [MM:SS] moment from the transcript where a new concept is introduced, a slide changes, or a specific tool is shown.

MINDMAP RULES:
10. Structure: root → 4-7 major branch nodes → 3-6 leaf nodes per branch.
11. Branch node labels (depth 1, direct children of root): concise section titles, max 55 characters.
12. Leaf node labels (depth 2+): full descriptive sentences — these are the actual content the user reads. 60-100 characters, written as a complete informative statement (e.g. "Local models run on your own hardware, ensuring full privacy with no API costs").
13. Categories: root, intro, concept, example, process, conclusion, recommendation, data, tool.
14. The mindmap must map directly to the video's content sections — branches are themes, leaves are the specific facts, steps, or insights within each theme.

QUALITY RULES:
14. Never use placeholder text. Every field must contain real content from the transcript.
15. Ensure JSON is perfectly valid. Do not wrap in markdown.
"""

    max_retries = 3
    backoff = [2, 4, 8]
    for attempt in range(max_retries):
        try:
            logger.info("Single-pass summary request...")
            raw_content = await complete_llm_text(
                SYSTEM_PROMPT,
                user_prompt,
                16000,
                user_api_key,
                user_provider,
                user_model,
                openrouter_full_fallback=True,
            )
            return json.loads(_strip_code_fences(raw_content))
        except (RateLimitError, OpenAIRateLimitError):
            if attempt < max_retries - 1:
                logger.warning("Rate limited. Retrying in %s s...", backoff[attempt])
                await asyncio.sleep(backoff[attempt])
            else:
                logger.error("Rate limit retry exhausted.")
                raise RuntimeError("CLAUDE_API_ERROR: Rate limits exhausted.")
        except OpenAIAPIError as e:
            if attempt < max_retries - 1 and getattr(e, "status_code", None) == 429:
                await asyncio.sleep(backoff[attempt])
                continue
            logger.error("OpenRouter API error: %s", e)
            raise RuntimeError(f"CLAUDE_API_ERROR: {str(e)}")
        except json.JSONDecodeError as e:
            logger.error("Claude returned invalid JSON: %s", e)
            if attempt < max_retries - 1:
                await asyncio.sleep(backoff[attempt])
                continue
            raise RuntimeError("CLAUDE_PARSE_ERROR: Failed to parse AI response.")
        except Exception as e:
            err = str(e)
            if "Rate limited" in err or "429" in err:
                if attempt < max_retries - 1:
                    await asyncio.sleep(backoff[attempt])
                    continue
            logger.error("Error calling LLM: %s", e)
            raise
    raise RuntimeError("CLAUDE_API_ERROR: Unknown failure.")


async def generate_summary_and_mindmap(
    title: str,
    channel: str,
    duration: str,
    transcript: str,
    user_api_key: str = None,
    user_provider: str = None,
    user_model: str = None,
) -> Dict[str, Any]:
    """
    Picks map-reduce when the raw transcript is long enough; otherwise one LLM call
    with optional truncate_transcript in single-pass.
    """
    if _map_reduce_enabled() and len(transcript) >= _map_reduce_min_transcript_len():
        parts = split_transcript_for_map(transcript)
        if len(parts) > 1:
            try:
                logger.info(
                    "Using map-reduce pipeline (%s chars, %s chunks).",
                    len(transcript),
                    len(parts),
                )
                return await run_map_reduce_summarization(
                    title, channel, duration, transcript,
                    user_api_key=user_api_key,
                    user_provider=user_provider,
                    user_model=user_model,
                )
            except Exception as e:
                logger.warning(
                    "Map-reduce failed (%s). Falling back to single-pass with truncation.",
                    e,
                )
    return await generate_summary_and_mindmap_single_pass(
        title, channel, duration, transcript,
        user_api_key=user_api_key,
        user_provider=user_provider,
        user_model=user_model,
    )

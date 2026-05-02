import asyncio
from copy import deepcopy
import json
import logging
import math
import os
import re
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from anthropic import AsyncAnthropic, RateLimitError
from openai import APIError as OpenAIAPIError
from openai import AsyncOpenAI
from openai import RateLimitError as OpenAIRateLimitError

logger = logging.getLogger(__name__)

PartialCallback = Callable[[Dict[str, Any]], Awaitable[None]]


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


_client = None
_model = None
_provider = None


def get_claude_client(
    user_provider: str = None,
    user_api_key: str = None,
    user_model: str = None,
):
    global _client, _model, _provider

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

    if _client is None:
        _provider = os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()

        if _provider == "openrouter":
            api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
            if not api_key:
                raise RuntimeError(
                    "CLAUDE_API_ERROR: OPENROUTER_API_KEY not found in environment. "
                    "Please check your .env file."
                )
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
                raise RuntimeError(
                    "CLAUDE_API_ERROR: ANTHROPIC_API_KEY not found in environment. "
                    "Please check your .env file."
                )
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
    One LLM call (Anthropic or OpenRouter). For map-reduce, use
    openrouter_full_fallback=False to only try the primary model.
    """
    client, model, provider = get_claude_client(user_provider, user_api_key, user_model)
    if provider == "openrouter":
        if openrouter_full_fallback:
            fallback_raw = os.environ.get(
                "OPENROUTER_FALLBACK_MODELS",
                (
                    "qwen/qwen3-next-80b-a3b-instruct:free,"
                    "meta-llama/llama-3.3-70b-instruct:free,"
                    "google/gemma-4-31b-it:free"
                ),
            ).strip()
            fallback_models = [m.strip() for m in fallback_raw.split(",") if m.strip()]
            use_low_cost_fallback = os.environ.get(
                "OPENROUTER_USE_LOW_COST_FALLBACK",
                "true",
            ).strip().lower() in ("1", "true", "yes", "on")
            low_cost_model = os.environ.get(
                "OPENROUTER_LOW_COST_MODEL",
                "openai/gpt-4o-mini",
            ).strip()
            low_cost_models = [low_cost_model] if (use_low_cost_fallback and low_cost_model) else []
            candidate_models: List[str] = []
            for candidate in [model, *fallback_models, *low_cost_models]:
                if candidate and candidate not in candidate_models:
                    candidate_models.append(candidate)
        else:
            candidate_models = [model] if model else []
        if not candidate_models:
            raise RuntimeError("CLAUDE_API_ERROR: No model configured for OpenRouter.")

        last_router_error = None
        for candidate_model in candidate_models:
            try:
                logger.info("OpenRouter model: %s", candidate_model)
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
                    raise RuntimeError(
                        "CLAUDE_PARSE_ERROR: Response was cut off - increase max_tokens."
                    )
                if raw_content:
                    return raw_content
            except OpenAIAPIError as exc:
                err_text = str(exc)
                status_code = getattr(exc, "status_code", None)
                if status_code == 404 or "No endpoints found" in err_text:
                    last_router_error = exc
                    continue
                raise
        if last_router_error:
            raise RuntimeError(
                "CLAUDE_API_ERROR: No OpenRouter model returned content. "
                "Set OPENROUTER_MODEL / OPENROUTER_FALLBACK_MODELS."
            )
        raise RuntimeError("CLAUDE_API_ERROR: OpenRouter returned empty content.")

    response = await client.messages.create(
        model=model,
        max_tokens=max_out_tokens,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw_content = response.content[0].text.strip()
    if response.stop_reason == "max_tokens" and not raw_content:
        raise RuntimeError("CLAUDE_PARSE_ERROR: Response was cut off - increase max_tokens.")
    return raw_content


SYSTEM_PROMPT = """
You are a world-class content analyst and knowledge synthesizer. Your job is to produce deep, insight-rich analysis of video transcripts - the kind of notes a brilliant student would take after watching the video twice and reflecting carefully.

Your summaries must:
- Capture SPECIFIC facts, numbers, examples, and arguments - never vague generalities
- Surface non-obvious insights that a casual viewer might miss
- Connect ideas across sections to reveal the video's underlying logic
- Be detailed enough that someone who never watches the video gains genuine expertise

You MUST respond ONLY with valid JSON. Do not include any conversational text or markdown codeblocks outside the JSON.
"""


_TUTORIAL_TITLE_KW = {
    "tutorial",
    "how to",
    "how i",
    "guide",
    "walkthrough",
    "build",
    "setup",
    "install",
    "step by step",
}
_LECTURE_TITLE_KW = {
    "lecture",
    "course",
    "lesson",
    "explained",
    "theory",
    "introduction to",
    "101",
}
_OPINION_TITLE_KW = {
    "opinion",
    "thoughts on",
    "why i",
    "my take",
    "review",
    "ranked",
    "tier list",
    "react to",
}
_TUTORIAL_TRANSCRIPT_KW = ["pip install", "import ", "def ", "git clone"]
_LECTURE_TRANSCRIPT_KW = [
    "in this lecture",
    "today we'll",
    "as we can see from",
    "in the next section",
]
_OPINION_TRANSCRIPT_KW = [
    "i think",
    "in my opinion",
    "i believe",
    "personally",
    "i feel like",
]

_TIMESTAMP_RE = re.compile(r"\[\d+:\d{2}(?::\d{2})?\]")
_BOUNDS_RE = re.compile(r"\[(\d+):(\d{2})(?::(\d{2}))?\]")
_INSIGHT_RULE = (
    "Insight rule: each insight_seeds entry MUST follow "
    "[specific claim] + [why/mechanism] + [timestamp evidence]. "
    "Generic observations are not valid insights."
)


def detect_video_type(title: str, transcript: str) -> str:
    """Return tutorial, lecture, opinion, or general via keyword heuristic."""
    lowered_title = (title or "").lower()
    if any(kw in lowered_title for kw in _TUTORIAL_TITLE_KW):
        return "tutorial"
    if any(kw in lowered_title for kw in _LECTURE_TITLE_KW):
        return "lecture"
    if any(kw in lowered_title for kw in _OPINION_TITLE_KW):
        return "opinion"

    sample = (transcript or "")[:3000].lower()
    if any(kw in sample for kw in _TUTORIAL_TRANSCRIPT_KW):
        return "tutorial"
    if any(kw in sample for kw in _LECTURE_TRANSCRIPT_KW):
        return "lecture"
    if sum(sample.count(kw) for kw in _OPINION_TRANSCRIPT_KW) >= 3:
        return "opinion"
    return "general"


def _find_split_point(transcript: str, target: int, min_start: int = 0) -> int:
    """
    Return the index to split at: nearest [MM:SS] marker within +/-500 chars,
    else sentence boundary, else target. Never return before min_start.
    """
    lo = max(min_start, target - 500)
    hi = min(len(transcript), target + 500)
    window = transcript[lo:hi]

    best_pos = None
    best_dist = float("inf")
    for match in _TIMESTAMP_RE.finditer(window):
        pos = lo + match.start()
        dist = abs(pos - target)
        if dist < best_dist:
            best_dist = dist
            best_pos = pos
    if best_pos is not None:
        return best_pos

    for punct in (". ", "? ", "! "):
        idx = transcript.rfind(punct, lo, target)
        if idx != -1:
            return idx + len(punct)
    return target


def _extract_chunk_bounds(chunk: str) -> Tuple[int, int]:
    """Return the first and last timestamp found in a chunk, else (0, 0)."""
    matches = list(_BOUNDS_RE.finditer(chunk or ""))
    if not matches:
        return 0, 0

    def _to_seconds(match: re.Match[str]) -> int:
        first = match.group(1)
        second = match.group(2)
        third = match.group(3)
        if third is None:
            return int(first) * 60 + int(second)
        return int(first) * 3600 + int(second) * 60 + int(third)

    return _to_seconds(matches[0]), _to_seconds(matches[-1])


def _format_seconds_label(seconds: int) -> str:
    total = max(0, int(seconds))
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _parse_duration_to_seconds(duration: str) -> int:
    parts = [int(part) for part in str(duration or "").split(":") if part.isdigit()]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return 0


def _string_list(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    out: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if text:
            out.append(text)
    return out


def _strip_inline_timestamps(text: str) -> str:
    cleaned = re.sub(r"\[\d+:\d{2}(?::\d{2})?\]", "", str(text or ""))
    cleaned = re.sub(r"\bEvidence:\s*\d+:\d{2}(?::\d{2})?\.?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bTimestamp:\s*\d+:\d{2}(?::\d{2})?\.?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" -,.")


def _normalize_insight(insight: Any) -> str:
    if isinstance(insight, dict):
        claim = str(insight.get("claim", "") or "").strip()
        why = str(
            insight.get("why_it_matters", "")
            or insight.get("why", "")
            or insight.get("mechanism", "")
            or ""
        ).strip()
        timestamp = str(
            insight.get("timestamp_reference", "")
            or insight.get("timestamp", "")
            or ""
        ).strip()
        parts = [claim]
        if why:
            parts.append(f"This matters because {why[:1].lower() + why[1:] if len(why) > 1 else why.lower()}.")
        if timestamp:
            parts.append(f"Evidence: {timestamp}.")
        return " ".join(part for part in parts if part).strip()
    return str(insight or "").strip()


def _extract_key_insight_items(value: Any) -> List[Any]:
    if isinstance(value, dict):
        bullets = value.get("bullets")
        return bullets if isinstance(bullets, list) else []
    if isinstance(value, list):
        return value
    return []


def _string_paragraphs(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item or "").strip() for item in value if str(item or "").strip()]
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"\n{2,}", value) if part.strip()]
    return []


def _normalize_deep_dive(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        raw_sections = value.get("sections")
        sections: List[Dict[str, Any]] = []
        if isinstance(raw_sections, list):
            for item in raw_sections:
                if not isinstance(item, dict):
                    continue
                heading = str(item.get("heading", item.get("title", "")) or "").strip()
                paragraphs = _string_paragraphs(item.get("paragraphs", item.get("content", [])))
                if heading and paragraphs:
                    sections.append({"heading": heading, "paragraphs": paragraphs})
        text = str(value.get("text", "") or "").strip()
        return {"sections": sections, "text": text}
    if isinstance(value, str):
        return {
            "sections": [{"heading": "Full Analysis", "paragraphs": _string_paragraphs(value)}] if value.strip() else [],
            "text": value.strip(),
        }
    return {"sections": [], "text": ""}


def _deep_dive_theme_for_section(section: Dict[str, Any]) -> str:
    haystack = " ".join(
        [
            str(section.get("title", "") or ""),
            str(section.get("description", "") or ""),
            " ".join(_string_list(section.get("sub_points", []))),
            " ".join(_string_list(section.get("trade_offs", []))),
            str(section.get("notable_detail", "") or ""),
        ]
    ).lower()
    theme_rules = [
        (("goal", "overview", "intro", "framing", "why"), "Framing And Goal"),
        (("setup", "prerequisite", "install", "configure", "start"), "Setup And Prerequisites"),
        (("step", "workflow", "process", "how to", "walkthrough"), "Workflow And Process"),
        (("decision", "choice", "trade-off", "tradeoff", "option"), "Key Decisions And Trade-Offs"),
        (("mistake", "failure", "edge case", "fix", "pitfall"), "Mistakes And Fixes"),
        (("concept", "definition", "framework", "theory"), "Core Concepts And Framework"),
        (("example", "evidence", "proof", "demo", "case", "illustration"), "Examples And Evidence"),
        (("limit", "limitation", "counter", "weak", "caveat", "question"), "Limits And Counterpoints"),
        (("takeaway", "next", "apply", "do now", "action"), "Takeaway And Next Steps"),
    ]
    for needles, heading in theme_rules:
        if any(needle in haystack for needle in needles):
            return heading
    return "Main Throughline"


def _normalize_deep_dive_heading_label(label: str, fallback: str = "Main Throughline") -> str:
    text = re.sub(r"\s+", " ", str(label or "").strip())
    if not text:
        return fallback
    text = text[:1].upper() + text[1:]
    return text if len(text) <= 64 else text[:64].rstrip()


def _min_section_count_for_duration(duration: str) -> int:
    return _target_section_count_for_duration(duration)


def _target_section_range_for_duration(duration: str) -> str:
    return str(_target_section_count_for_duration(duration))


def _target_section_count_for_duration(duration: str) -> int:
    duration_seconds = _parse_duration_to_seconds(duration)
    if duration_seconds <= 0:
        return 1
    return max(1, math.ceil(duration_seconds / (5 * 60)))


def _target_section_span_seconds(duration: str) -> int:
    duration_seconds = _parse_duration_to_seconds(duration)
    target_count = _target_section_count_for_duration(duration)
    if duration_seconds <= 0:
        return 0
    return max(1, math.ceil(duration_seconds / target_count))


def _build_equal_section_windows(duration: str) -> List[Tuple[int, int]]:
    duration_seconds = _parse_duration_to_seconds(duration)
    target_count = _target_section_count_for_duration(duration)
    if duration_seconds <= 0:
        return [(0, 0)]

    windows: List[Tuple[int, int]] = []
    for index in range(target_count):
        start = int((index * duration_seconds) / target_count)
        end = int(((index + 1) * duration_seconds) / target_count)
        if index == target_count - 1:
            end = duration_seconds
        windows.append((start, max(start, end)))
    return windows


def _normalize_chapter_sections(chapters: Optional[List[Any]], duration: str) -> List[Dict[str, Any]]:
    duration_seconds = _parse_duration_to_seconds(duration)
    normalized: List[Dict[str, Any]] = []
    if not chapters:
        return normalized

    for index, chapter in enumerate(chapters):
        if isinstance(chapter, dict):
            title = str(chapter.get("title", "") or "").strip()
            start_raw = chapter.get("start_time", chapter.get("start", 0))
            end_raw = chapter.get("end_time", chapter.get("end", duration_seconds))
        else:
            title = str(getattr(chapter, "title", "") or "").strip()
            start_raw = getattr(chapter, "start_time", getattr(chapter, "start", 0))
            end_raw = getattr(chapter, "end_time", getattr(chapter, "end", duration_seconds))

        try:
            start_seconds = max(0, int(float(start_raw or 0)))
        except (TypeError, ValueError):
            start_seconds = 0
        try:
            end_seconds = max(start_seconds, int(float(end_raw or duration_seconds)))
        except (TypeError, ValueError):
            end_seconds = max(start_seconds, duration_seconds)

        if not title:
            title = f"Chapter {index + 1}"
        normalized.append(
            {
                "title": title,
                "start_seconds": start_seconds,
                "end_seconds": end_seconds,
                "timestamp": _format_seconds_label(start_seconds),
            }
        )

    normalized.sort(key=lambda item: item["start_seconds"])
    for index, item in enumerate(normalized):
        if index < len(normalized) - 1:
            item["end_seconds"] = max(item["start_seconds"], normalized[index + 1]["start_seconds"])
        elif duration_seconds:
            item["end_seconds"] = max(item["start_seconds"], duration_seconds)

    return [item for item in normalized if item["end_seconds"] >= item["start_seconds"]]


def _section_windows(duration: str, chapters: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
    chapter_windows = _normalize_chapter_sections(chapters, duration)
    if chapter_windows:
        return chapter_windows
    return [
        {
            "title": "",
            "start_seconds": start,
            "end_seconds": end,
            "timestamp": _format_seconds_label(start),
        }
        for start, end in _build_equal_section_windows(duration)
    ]


def _format_window_range(start_seconds: int, end_seconds: int) -> str:
    start_label = _format_seconds_label(start_seconds)
    end_label = _format_seconds_label(end_seconds)
    return f"{start_label} to {end_label}"


def _target_section_count_for_span(start_seconds: int, end_seconds: int) -> int:
    span_seconds = max(0, end_seconds - start_seconds)
    if span_seconds <= 0:
        return 1
    return max(1, math.ceil(span_seconds / (5 * 60)))


def _build_equal_windows_for_span(start_seconds: int, end_seconds: int) -> List[Tuple[int, int]]:
    span_seconds = max(0, end_seconds - start_seconds)
    target_count = _target_section_count_for_span(start_seconds, end_seconds)
    if span_seconds <= 0:
        return [(start_seconds, end_seconds)]

    windows: List[Tuple[int, int]] = []
    for index in range(target_count):
        start = start_seconds + int((index * span_seconds) / target_count)
        end = start_seconds + int(((index + 1) * span_seconds) / target_count)
        if index == target_count - 1:
            end = end_seconds
        windows.append((start, max(start, end)))
    return windows


def _chunk_window_plan(start_seconds: int, end_seconds: int) -> str:
    lines = []
    for idx, (start, end) in enumerate(_build_equal_windows_for_span(start_seconds, end_seconds), start=1):
        lines.append(f"{idx}. {_format_window_range(start, end)}")
    return "\n".join(lines)


def _section_window_plan(duration: str, chapters: Optional[List[Any]] = None) -> str:
    windows = _section_windows(duration, chapters)
    lines = []
    for idx, window in enumerate(windows, start=1):
        label = _format_window_range(window["start_seconds"], window["end_seconds"])
        title = str(window.get("title", "") or "").strip()
        if title:
            lines.append(f"{idx}. {label} - {title}")
        else:
            lines.append(f"{idx}. {label}")
    return "\n".join(lines)


def _compact_section_window_plan(duration: str, chapters: Optional[List[Any]] = None) -> str:
    windows = _section_windows(duration, chapters)
    return " | ".join(
        (
            f"{idx}:{_format_window_range(window['start_seconds'], window['end_seconds'])}"
            + (f" ({window['title']})" if window.get("title") else "")
        )
        for idx, window in enumerate(windows, start=1)
    )


def _log_section_plan(duration: str, chapters: Optional[List[Any]] = None) -> None:
    logger.info(
        "Section plan for duration=%s -> target_count=%s, target_span_seconds=%s, windows=%s",
        duration,
        len(_section_windows(duration, chapters)),
        _target_section_span_seconds(duration),
        _compact_section_window_plan(duration, chapters),
    )


def _log_chunk_boundaries(chunks: List[str]) -> None:
    for idx, chunk in enumerate(chunks, start=1):
        start_seconds, end_seconds = _extract_chunk_bounds(chunk)
        logger.info(
            "Transcript chunk %s/%s -> chars=%s, time_range=%s to %s",
            idx,
            len(chunks),
            len(chunk),
            _format_seconds_label(start_seconds),
            _format_seconds_label(end_seconds),
        )


def _log_section_timestamps(label: str, sections: List[Dict[str, Any]]) -> None:
    logger.info(
        "%s -> count=%s, timestamps=%s",
        label,
        len(sections),
        [section.get("timestamp") or _format_seconds_label(section.get("timestamp_seconds", 0)) for section in sections],
    )


def _section_description_budget(duration: str) -> str:
    duration_seconds = _parse_duration_to_seconds(duration)
    if duration_seconds >= 60 * 60:
        return "120-165 words"
    if duration_seconds >= 45 * 60:
        return "150-200 words"
    if duration_seconds >= 20 * 60:
        return "110-150 words"
    if duration_seconds >= 8 * 60:
        return "80-120 words"
    return "60-90 words"


def _section_subpoint_budget(duration: str) -> str:
    duration_seconds = _parse_duration_to_seconds(duration)
    if duration_seconds >= 60 * 60:
        return "3-5"
    return "4-7" if duration_seconds >= 45 * 60 else "3-5"


def _insight_word_budget(duration: str) -> str:
    return "30-60 words"


def _concept_explanation_budget(duration: str) -> str:
    duration_seconds = _parse_duration_to_seconds(duration)
    return "90-180 words" if duration_seconds >= 45 * 60 else "60-140 words"


def _recommendation_word_budget(duration: str) -> str:
    duration_seconds = _parse_duration_to_seconds(duration)
    return "20-60 words" if duration_seconds >= 45 * 60 else "15-45 words"


def _conclusion_word_budget(duration: str) -> str:
    duration_seconds = _parse_duration_to_seconds(duration)
    return "120-220 words" if duration_seconds >= 45 * 60 else "80-160 words"


def _deep_dive_min_word_count(duration: str) -> int:
    duration_seconds = _parse_duration_to_seconds(duration)
    if duration_seconds <= 5 * 60:
        return 350
    if duration_seconds <= 20 * 60:
        return 450
    if duration_seconds <= 45 * 60:
        return 650
    if duration_seconds <= 60 * 60:
        return 800
    if duration_seconds <= int(1.5 * 60 * 60):
        return 1200
    if duration_seconds <= 3 * 60 * 60:
        return 1800
    return 2200


def _count_words(text: str) -> int:
    return len([part for part in str(text or "").split() if part.strip()])


def _normalize_key_section(section: Any) -> Dict[str, Any]:
    if not isinstance(section, dict):
        return {}
    timestamp_raw = section.get("timestamp_seconds", section.get("seconds", 0)) or 0
    try:
        timestamp_seconds = int(float(timestamp_raw))
    except (TypeError, ValueError):
        timestamp_seconds = 0
    return {
        "title": str(section.get("title", section.get("heading", "")) or "").strip(),
        "timestamp": str(section.get("timestamp", section.get("time", "")) or "").strip(),
        "timestamp_seconds": timestamp_seconds,
        "description": _strip_inline_timestamps(str(section.get("description", section.get("body", section.get("details", ""))) or "").strip()),
        "steps": [_strip_inline_timestamps(item) for item in _string_list(section.get("steps")) if _strip_inline_timestamps(item)],
        "sub_points": [_strip_inline_timestamps(item) for item in _string_list(section.get("sub_points", section.get("subPoints"))) if _strip_inline_timestamps(item)],
        "trade_offs": [_strip_inline_timestamps(item) for item in _string_list(section.get("trade_offs", section.get("tradeOffs"))) if _strip_inline_timestamps(item)],
        "notable_detail": _strip_inline_timestamps(str(section.get("notable_detail", section.get("notable", "")) or "").strip()),
    }


def _extract_key_sections_payload(payload: Any) -> List[Any]:
    def _pick_sections(container: Any) -> List[Any]:
        if not isinstance(container, dict):
            return []
        for key in ("key_sections", "sections"):
            value = container.get(key)
            if isinstance(value, list):
                return value
        return []

    if not isinstance(payload, dict):
        return []
    direct = _pick_sections(payload)
    if direct:
        return direct
    summary = payload.get("summary")
    nested_summary = _pick_sections(summary)
    if nested_summary:
        return nested_summary
    data = payload.get("data")
    if isinstance(data, dict):
        direct_data = _pick_sections(data)
        if direct_data:
            return direct_data
        nested_data_summary = _pick_sections(data.get("summary"))
        if nested_data_summary:
            return nested_data_summary
    return []


def _normalize_chunk_support(obj: Dict[str, Any], chunk_index: int, chunk_text: str = "") -> Dict[str, Any]:
    summary_paragraph = _strip_inline_timestamps(str(obj.get("summary_paragraph", "") or "").strip())
    insight_seeds = [_strip_inline_timestamps(item) for item in _string_list(obj.get("insight_seeds")) if _strip_inline_timestamps(item)]
    recommendation_seeds = [_strip_inline_timestamps(item) for item in _string_list(obj.get("recommendation_seeds")) if _strip_inline_timestamps(item)]
    concept_seeds_raw = obj.get("concept_seeds", [])
    concept_summaries: List[str] = []
    if isinstance(concept_seeds_raw, list):
        for concept in concept_seeds_raw:
            if not isinstance(concept, dict):
                continue
            concept_name = str(concept.get("concept", "") or "").strip()
            explanation = str(concept.get("explanation", "") or "").strip()
            why_it_matters = str(concept.get("why_it_matters", "") or "").strip()
            example = str(concept.get("example_from_video", "") or "").strip()
            parts = [concept_name, explanation, why_it_matters, example]
            combined = ": ".join(part for part in [concept_name, explanation] if part).strip(": ")
            if why_it_matters:
                combined = f"{combined} Why it matters: {why_it_matters}".strip()
            if example:
                combined = f"{combined} Example: {example}".strip()
            combined = _strip_inline_timestamps(combined)
            if combined:
                concept_summaries.append(combined)

    start_seconds = 0
    end_seconds = 0
    if chunk_text:
        start_seconds, end_seconds = _extract_chunk_bounds(chunk_text)

    return {
        "chunk_index": chunk_index,
        "start_seconds": start_seconds,
        "end_seconds": end_seconds,
        "summary_paragraph": summary_paragraph,
        "insight_seeds": insight_seeds,
        "recommendation_seeds": recommendation_seeds,
        "concept_summaries": concept_summaries,
    }


def _window_support_for_range(
    start_seconds: int,
    end_seconds: int,
    chunk_supports: Optional[List[Dict[str, Any]]],
) -> Dict[str, List[str]]:
    if not chunk_supports:
        return {
            "summary_paragraphs": [],
            "insight_seeds": [],
            "recommendation_seeds": [],
            "concept_summaries": [],
        }

    summary_paragraphs: List[str] = []
    insight_seeds: List[str] = []
    recommendation_seeds: List[str] = []
    concept_summaries: List[str] = []

    for support in chunk_supports:
        chunk_start = int(support.get("start_seconds", 0))
        chunk_end = int(support.get("end_seconds", 0))
        overlaps = not (chunk_end < start_seconds or chunk_start > end_seconds)
        if not overlaps:
            continue
        summary = str(support.get("summary_paragraph", "") or "").strip()
        if summary and summary not in summary_paragraphs:
            summary_paragraphs.append(summary)
        for item in support.get("insight_seeds", []) or []:
            if item and item not in insight_seeds:
                insight_seeds.append(item)
        for item in support.get("recommendation_seeds", []) or []:
            if item and item not in recommendation_seeds:
                recommendation_seeds.append(item)
        for item in support.get("concept_summaries", []) or []:
            if item and item not in concept_summaries:
                concept_summaries.append(item)

    return {
        "summary_paragraphs": summary_paragraphs,
        "insight_seeds": insight_seeds,
        "recommendation_seeds": recommendation_seeds,
        "concept_summaries": concept_summaries,
    }


def _merge_candidate_group(
    candidates: List[Dict[str, Any]],
    *,
    title_override: str = "",
    timestamp_override: str = "",
    timestamp_seconds_override: Optional[int] = None,
    support: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    if not candidates:
        return {}

    ordered = sorted(candidates, key=lambda item: item.get("timestamp_seconds", 0))
    first = deepcopy(ordered[0])
    merged_title = title_override or first.get("title", "")
    merged_timestamp = timestamp_override or first.get("timestamp", "")
    merged_timestamp_seconds = (
        int(timestamp_seconds_override)
        if timestamp_seconds_override is not None
        else int(first.get("timestamp_seconds", 0))
    )
    descriptions = [_strip_inline_timestamps(str(item.get("description", "") or "").strip()) for item in ordered if _strip_inline_timestamps(str(item.get("description", "") or "").strip())]
    steps: List[str] = []
    sub_points: List[str] = []
    trade_offs: List[str] = []
    notable_detail = ""

    for item in ordered:
        for step in item.get("steps", []) or []:
            step = _strip_inline_timestamps(step)
            if step and step not in steps:
                steps.append(step)
        for point in item.get("sub_points", []) or []:
            point = _strip_inline_timestamps(point)
            if point and point not in sub_points:
                sub_points.append(point)
        for trade_off in item.get("trade_offs", []) or []:
            trade_off = _strip_inline_timestamps(trade_off)
            if trade_off and trade_off not in trade_offs:
                trade_offs.append(trade_off)
        detail = _strip_inline_timestamps(str(item.get("notable_detail", "") or "").strip())
        if detail and not notable_detail:
            notable_detail = detail

    support = support or {}
    for paragraph in support.get("summary_paragraphs", [])[:2]:
        if paragraph and paragraph not in descriptions:
            descriptions.append(paragraph)
    for concept_summary in support.get("concept_summaries", [])[:4]:
        if concept_summary and concept_summary not in sub_points:
            sub_points.append(concept_summary)
    for insight in support.get("insight_seeds", [])[:5]:
        if insight and insight not in sub_points:
            sub_points.append(insight)
    for recommendation in support.get("recommendation_seeds", [])[:3]:
        if recommendation and recommendation not in sub_points:
            sub_points.append(recommendation)
    if not notable_detail:
        for fallback_detail in support.get("insight_seeds", [])[:1] + support.get("concept_summaries", [])[:1]:
            if fallback_detail:
                notable_detail = fallback_detail
                break

    return {
        "title": merged_title,
        "timestamp": merged_timestamp,
        "timestamp_seconds": merged_timestamp_seconds,
        "description": _strip_inline_timestamps(" ".join(descriptions).strip()),
        "steps": steps[:10],
        "sub_points": sub_points[:14],
        "trade_offs": trade_offs[:8],
        "notable_detail": _strip_inline_timestamps(notable_detail),
    }


def _build_sections_from_candidates(
    candidates: List[Dict[str, Any]],
    duration: str,
    chapters: Optional[List[Any]] = None,
    chunk_supports: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    windows = _section_windows(duration, chapters)
    target_count = len(windows)
    normalized_candidates = [
        normalized
        for normalized in (_normalize_key_section(item) for item in candidates)
        if normalized.get("title")
    ]
    normalized_candidates.sort(key=lambda item: item.get("timestamp_seconds", 0))

    unique_candidates: List[Dict[str, Any]] = []
    seen_timestamps: set[int] = set()
    for candidate in normalized_candidates:
        timestamp_seconds = int(candidate.get("timestamp_seconds", 0))
        if timestamp_seconds in seen_timestamps:
            continue
        seen_timestamps.add(timestamp_seconds)
        unique_candidates.append(candidate)

    if not unique_candidates:
        return []

    if _normalize_chapter_sections(chapters, duration):
        chapter_sections: List[Dict[str, Any]] = []
        for index, window in enumerate(windows):
            start_seconds = int(window["start_seconds"])
            end_seconds = int(window["end_seconds"])
            in_window = [
                candidate
                for candidate in unique_candidates
                if (
                    start_seconds <= int(candidate.get("timestamp_seconds", 0)) <= end_seconds
                    if index == len(windows) - 1
                    else start_seconds <= int(candidate.get("timestamp_seconds", 0)) < end_seconds
                )
            ]
            if not in_window:
                nearest = min(
                    unique_candidates,
                    key=lambda item: abs(int(item.get("timestamp_seconds", 0)) - start_seconds),
                )
                in_window = [nearest]
            support = _window_support_for_range(start_seconds, end_seconds, chunk_supports)
            merged = _merge_candidate_group(
                in_window,
                title_override=str(window.get("title", "") or ""),
                timestamp_override=str(window.get("timestamp", "") or _format_seconds_label(start_seconds)),
                timestamp_seconds_override=start_seconds,
                support=support,
            )
            if merged:
                chapter_sections.append(merged)
        chapter_sections.sort(key=lambda item: item.get("timestamp_seconds", 0))
        return chapter_sections

    if len(unique_candidates) >= target_count:
        if target_count == 1:
            support = _window_support_for_range(0, _parse_duration_to_seconds(duration), chunk_supports)
            return [_merge_candidate_group([unique_candidates[0]], support=support)]
        sampled_sections = []
        max_index = len(unique_candidates) - 1
        for output_index in range(target_count):
            candidate_index = math.floor((output_index * max_index) / (target_count - 1))
            candidate = unique_candidates[candidate_index]
            if output_index < len(windows):
                window = windows[output_index]
                support = _window_support_for_range(
                    int(window["start_seconds"]),
                    int(window["end_seconds"]),
                    chunk_supports,
                )
            else:
                support = None
            sampled_sections.append(_merge_candidate_group([candidate], support=support))
        return sampled_sections

    selected_sections: List[Dict[str, Any]] = []
    used_indices: set[int] = set()

    for window_index, (start_seconds, end_seconds) in enumerate(windows):
        in_window: List[Tuple[int, Dict[str, Any]]] = []
        for idx, candidate in enumerate(unique_candidates):
            ts = int(candidate.get("timestamp_seconds", 0))
            in_range = start_seconds <= ts <= end_seconds if window_index == len(windows) - 1 else start_seconds <= ts < end_seconds
            if in_range and idx not in used_indices:
                in_window.append((idx, candidate))

        if in_window:
            support = _window_support_for_range(start_seconds, end_seconds, chunk_supports)
            best_idx, best_candidate = min(
                in_window,
                key=lambda pair: abs(int(pair[1].get("timestamp_seconds", 0)) - start_seconds),
            )
            used_indices.add(best_idx)
            selected_sections.append(
                _merge_candidate_group(
                    [best_candidate],
                    support=support,
                )
            )
            continue

        remaining: List[Tuple[int, Dict[str, Any]]] = [
            (idx, candidate)
            for idx, candidate in enumerate(unique_candidates)
            if idx not in used_indices
        ]
        if not remaining:
            remaining = list(enumerate(unique_candidates))

        best_idx, best_candidate = min(
            remaining,
            key=lambda pair: abs(int(pair[1].get("timestamp_seconds", 0)) - start_seconds),
        )
        used_indices.add(best_idx)
        support = _window_support_for_range(start_seconds, end_seconds, chunk_supports)
        selected_sections.append(
            _merge_candidate_group(
                [best_candidate],
                support=support,
            )
        )

    selected_sections.sort(key=lambda item: item.get("timestamp_seconds", 0))
    return selected_sections


def _section_windows_from_sections(sections: List[Dict[str, Any]], duration: str) -> List[Tuple[int, int]]:
    duration_seconds = _parse_duration_to_seconds(duration)
    ordered = sorted(sections, key=lambda item: int(item.get("timestamp_seconds", 0)))
    windows: List[Tuple[int, int]] = []
    for index, section in enumerate(ordered):
        start_seconds = int(section.get("timestamp_seconds", 0))
        end_seconds = duration_seconds if index == len(ordered) - 1 else int(ordered[index + 1].get("timestamp_seconds", start_seconds))
        windows.append((start_seconds, max(start_seconds, end_seconds)))
    return windows


def _section_source_material(
    sections: List[Dict[str, Any]],
    transcript_segments: Optional[List[Any]],
    duration: str,
) -> List[Dict[str, Any]]:
    if not transcript_segments:
        return []

    windows = _section_windows_from_sections(sections, duration)
    ordered = sorted(sections, key=lambda item: int(item.get("timestamp_seconds", 0)))
    materials: List[Dict[str, Any]] = []
    for index, section in enumerate(ordered):
        start_seconds, end_seconds = windows[index]
        parts: List[str] = []
        for segment in transcript_segments:
            text = str(getattr(segment, "text", "") or "").replace("\n", " ").strip()
            seg_start = float(getattr(segment, "start", 0) or 0)
            seg_duration = float(getattr(segment, "duration", 0) or 0)
            seg_end = seg_start + seg_duration
            in_range = seg_start < end_seconds and seg_end >= start_seconds if index == len(windows) - 1 else seg_start < end_seconds and seg_end > start_seconds
            if text and in_range:
                parts.append(text)
        source_text = " ".join(parts).strip()
        source_words = _count_words(source_text)
        excerpt = source_text
        if len(excerpt) > 2200:
            excerpt = f"{excerpt[:1300].rstrip()} ... {excerpt[-700:].lstrip()}"
        materials.append(
            {
                "title": section.get("title", ""),
                "timestamp": section.get("timestamp", ""),
                "timestamp_seconds": int(section.get("timestamp_seconds", 0)),
                "source_words": source_words,
                "transcript_excerpt": excerpt,
            }
        )
    return materials


def _key_sections_polish_prompt(
    title: str,
    channel: str,
    duration: str,
    sections: List[Dict[str, Any]],
    section_materials: List[Dict[str, Any]],
) -> str:
    materials_by_ts = {int(item.get("timestamp_seconds", 0)): item for item in section_materials}
    payload = []
    for section in sections:
        material = materials_by_ts.get(int(section.get("timestamp_seconds", 0)), {})
        payload.append(
            {
                "section": section,
                "source_words": int(material.get("source_words", 0)),
                "transcript_excerpt": material.get("transcript_excerpt", ""),
            }
        )

    return f"""
You are rewriting key sections so they read like rich summaries, not transcript copies.

Video:
Title: {title}
Channel: {channel}
Duration: {duration}

Return valid JSON only:
{{
  "key_sections": [
    {{
      "title": "Same title",
      "timestamp": "Same timestamp",
      "timestamp_seconds": 0,
      "description": "Rich summary",
      "steps": ["rewritten step"],
      "sub_points": ["rewritten detail"],
      "trade_offs": ["rewritten limitation"],
      "notable_detail": "memorable specific detail"
    }}
  ]
}}

Section inputs:
{json.dumps(payload, ensure_ascii=False, indent=2)}

Rules:
- Keep the same number of sections.
- Preserve each section's title, timestamp, and timestamp_seconds exactly.
- description must be a summary, not a transcript copy.
- For each section, description length should be at least 30% and at most 65% of that section's source_words count. Aim for roughly 45%-55%.
- Do not quote or copy long contiguous spans from the transcript excerpt.
- Do not mention timestamps inside description, steps, sub_points, trade_offs, or notable_detail.
- Remove repetition across fields.
""".strip()


async def _polish_key_sections(
    *,
    title: str,
    channel: str,
    duration: str,
    sections: List[Dict[str, Any]],
    transcript_segments: Optional[List[Any]],
    user_api_key: Optional[str],
    user_provider: Optional[str],
    user_model: Optional[str],
) -> List[Dict[str, Any]]:
    if not sections or not transcript_segments:
        return sections

    section_materials = _section_source_material(sections, transcript_segments, duration)
    if not section_materials:
        return sections

    payload = await _run_json_llm(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=_key_sections_polish_prompt(title, channel, duration, sections, section_materials),
        max_out_tokens=12000,
        user_api_key=user_api_key,
        user_provider=user_provider,
        user_model=user_model,
        openrouter_full_fallback=True,
    )
    polished = [
        normalized
        for normalized in (_normalize_key_section(item) for item in _extract_key_sections_payload(payload))
        if normalized.get("title")
    ]
    if len(polished) != len(sections):
        return sections
    return polished


def _normalize_concept(concept: Any) -> Dict[str, str]:
    if not isinstance(concept, dict):
        return {}
    return {
        "concept": str(concept.get("concept", "") or "").strip(),
        "explanation": str(concept.get("explanation", "") or "").strip(),
        "why_it_matters": str(concept.get("why_it_matters", "") or "").strip(),
        "example_from_video": str(concept.get("example_from_video", "") or "").strip(),
    }


def _backfill_summary_depth(payload: Dict[str, Any], duration: str = "", video_type: str = "general") -> Dict[str, Any]:
    """Normalize LLM output and backfill obviously missing depth fields."""
    if not isinstance(payload, dict):
        return payload

    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return payload

    sections = [
        normalized
        for normalized in (_normalize_key_section(item) for item in summary.get("key_sections", []))
        if normalized.get("title")
    ]
    sections.sort(key=lambda item: item.get("timestamp_seconds", 0))
    summary["key_sections"] = sections

    insights = [
        normalized
        for normalized in (_normalize_insight(item) for item in _extract_key_insight_items(summary.get("key_insights", [])))
        if normalized
    ]
    concepts = [
        normalized
        for normalized in (_normalize_concept(item) for item in summary.get("important_concepts", []))
        if normalized.get("concept") and normalized.get("explanation")
    ]

    if len(insights) < 6:
        for section in sections:
            timestamp = section.get("timestamp") or _format_seconds_label(section.get("timestamp_seconds", 0))
            candidate_bits = []
            if section.get("notable_detail"):
                candidate_bits.append(section["notable_detail"])
            candidate_bits.extend(section.get("sub_points", [])[:2])
            for bit in candidate_bits:
                text = f"{bit} This matters because it is a central point in {section['title']}. Evidence: {timestamp}."
                if text not in insights:
                    insights.append(text)
                if len(insights) >= 8:
                    break
            if len(insights) >= 8:
                break
    summary["key_insights"] = {"bullets": insights}

    if not concepts:
        for section in sections[:8]:
            explanation_parts = [section.get("description", "")]
            if section.get("sub_points"):
                explanation_parts.append("Key details: " + "; ".join(section["sub_points"][:3]))
            explanation = " ".join(part for part in explanation_parts if part).strip()
            if not explanation:
                continue
            concepts.append(
                {
                    "concept": section["title"],
                    "explanation": explanation,
                    "why_it_matters": section.get("notable_detail") or f"This section is one of the video's core ideas at {section.get('timestamp', '')}.",
                    "example_from_video": section.get("notable_detail", ""),
                }
            )
            if len(concepts) >= 6:
                break
    summary["important_concepts"] = concepts

    deep_dive = _normalize_deep_dive(summary.get("deep_dive", {}))
    existing_deep_dive_sections = deep_dive.get("sections", []) if isinstance(deep_dive, dict) else []
    if len(existing_deep_dive_sections) < 4:
        grouped_paragraphs: Dict[str, List[str]] = {}
        grouped_order: List[str] = []
        overview = summary.get("video_overview", {})
        elevator_pitch = ""
        if isinstance(overview, dict):
            elevator_pitch = str(overview.get("elevator_pitch", "") or "").strip()
        if elevator_pitch:
            grouped_paragraphs.setdefault("Main Throughline", []).append(elevator_pitch)
            if "Main Throughline" not in grouped_order:
                grouped_order.append("Main Throughline")

        for section in sections:
            theme = _deep_dive_theme_for_section(section)
            section_bits = [str(section.get("description", "") or "").strip()]
            sub_points = section.get("sub_points", []) or []
            notable = str(section.get("notable_detail", "") or "").strip()
            if sub_points:
                section_bits.append("Key details: " + "; ".join(str(point).strip() for point in sub_points[:2] if str(point).strip()))
            if notable:
                section_bits.append(notable)
            paragraph = " ".join(bit for bit in section_bits if bit).strip()
            if not paragraph:
                continue
            if theme not in grouped_paragraphs:
                grouped_paragraphs[theme] = []
                grouped_order.append(theme)
            grouped_paragraphs[theme].append(paragraph)

        deep_dive_sections = []
        for theme in grouped_order[:6]:
            paragraphs = grouped_paragraphs.get(theme, [])[:4]
            if paragraphs:
                deep_dive_sections.append({
                    "heading": _normalize_deep_dive_heading_label(theme),
                    "paragraphs": paragraphs,
                })

        if not deep_dive_sections and concepts:
            concept_paragraphs: List[str] = []
            for concept in concepts[:3]:
                concept_text = " ".join(
                    part for part in [
                        f"{concept.get('concept', '').strip()}: {concept.get('explanation', '').strip()}".strip(": "),
                        str(concept.get("why_it_matters", "") or "").strip(),
                        str(concept.get("example_from_video", "") or "").strip(),
                    ] if part
                ).strip()
                if concept_text:
                    concept_paragraphs.append(concept_text)
            if concept_paragraphs:
                deep_dive_sections.append({"heading": "Core Concepts And Implications", "paragraphs": concept_paragraphs[:2]})

        min_words = _deep_dive_min_word_count(duration)
        current_words = _count_words(
            " ".join(
                " ".join(section.get("paragraphs", []))
                for section in deep_dive_sections
            )
        )
        if current_words < min_words:
            extra_paragraphs: List[str] = []
            for section in sections:
                paragraph_bits = [str(section.get("description", "") or "").strip()]
                if section.get("steps"):
                    paragraph_bits.append("Steps: " + "; ".join(str(step).strip() for step in section.get("steps", [])[:3] if str(step).strip()))
                if section.get("sub_points"):
                    paragraph_bits.append("Key details: " + "; ".join(str(point).strip() for point in section.get("sub_points", [])[:3] if str(point).strip()))
                if section.get("trade_offs"):
                    paragraph_bits.append("Trade-offs: " + "; ".join(str(point).strip() for point in section.get("trade_offs", [])[:3] if str(point).strip()))
                if section.get("notable_detail"):
                    paragraph_bits.append(str(section.get("notable_detail", "") or "").strip())
                paragraph = " ".join(bit for bit in paragraph_bits if bit).strip()
                if paragraph:
                    extra_paragraphs.append(paragraph)
                if _count_words(" ".join(extra_paragraphs)) + current_words >= min_words:
                    break
            if extra_paragraphs:
                if deep_dive_sections:
                    deep_dive_sections[-1]["paragraphs"].extend(extra_paragraphs[:2])
                else:
                    deep_dive_sections.append({
                        "heading": "Additional Synthesis",
                        "paragraphs": extra_paragraphs[:2],
                    })

        final_text = "\n\n".join(
            "\n\n".join(section["paragraphs"])
            for section in deep_dive_sections
            if section.get("paragraphs")
        ).strip()
        if _count_words(final_text) < min_words and concepts:
            concept_texts = [
                " ".join(
                    part for part in [
                        f"{concept.get('concept', '').strip()}: {concept.get('explanation', '').strip()}".strip(": "),
                        str(concept.get("why_it_matters", "") or "").strip(),
                        str(concept.get("example_from_video", "") or "").strip(),
                    ] if part
                ).strip()
                for concept in concepts[:4]
            ]
            concept_texts = [text for text in concept_texts if text]
            if concept_texts:
                if deep_dive_sections:
                    deep_dive_sections[-1]["paragraphs"].extend(concept_texts[:2])
                else:
                    deep_dive_sections.append({
                        "heading": "Core Concepts And Implications",
                        "paragraphs": concept_texts[:2],
                    })

        deep_dive = {
            "sections": deep_dive_sections[:6],
            "text": "\n\n".join(
                "\n\n".join(section["paragraphs"])
                for section in deep_dive_sections
                if section.get("paragraphs")
            ).strip(),
        }
    summary["deep_dive"] = deep_dive

    duration_seconds = _parse_duration_to_seconds(duration)
    target_sections = _target_section_count_for_duration(duration)
    if len(sections) != target_sections:
        logger.warning(
            "Section count mismatch for duration=%s: expected %s key sections, got %s.",
            duration,
            target_sections,
            len(sections),
        )

    payload["summary"] = summary
    return payload


def truncate_transcript(transcript: str) -> str:
    """
    Fit the transcript into the model input budget without dropping the middle.
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
        (
            f"--- [Middle sample {i + 1}/{len(parts)} - chronological stretch of full video] ---\n"
            f"{block}"
        )
        for i, block in enumerate(parts)
    )

    logger.warning(
        "Transcript exceeds TRANSCRIPT_MAX_INPUT_CHARS=%s; using head+spaced mid windows+tail "
        "(raw_len=%s). Set TRANSCRIPT_MAX_INPUT_CHARS higher for 200k-context models if the "
        "provider allows.",
        max_chars,
        len(transcript),
    )

    return (
        f"{head}\n\n"
        f"--- [Video opening - the model should anchor early key_sections here] ---\n\n"
        f"{mid_blocks}\n\n"
        f"--- [Video closing - the model should anchor late/conclusion key_sections here] ---\n\n"
        f"{tail}"
    )


CHUNK_MAP_SYSTEM = (
    "You are summarizing one contiguous slice of a YouTube transcript. "
    "The full video is long; your output will be merged with other slices. "
    "Be dense and factual.\n"
    f"{_INSIGHT_RULE}\n"
    "Respond with JSON only, no markdown fences."
).strip()

CHUNK_MAP_SYSTEM_TUTORIAL = f"""
You are summarizing one contiguous slice of a YouTube TUTORIAL transcript. Focus on:
- Steps demonstrated in sequence (exact order matters)
- Tools and commands named (capture exact names and flags)
- Before/after states the speaker shows
- Gotchas, errors encountered, or caveats mentioned
{_INSIGHT_RULE}
Be dense and factual. Respond with JSON only, no markdown fences.
""".strip()

CHUNK_MAP_SYSTEM_LECTURE = f"""
You are summarizing one contiguous slice of a YouTube LECTURE transcript. Focus on:
- Claims made and the evidence provided for each claim
- Concepts defined, using the speaker's own wording where possible
- Argument structure and how each section builds on prior ones
- Named references, studies, or examples cited
{_INSIGHT_RULE}
Be dense and factual. Respond with JSON only, no markdown fences.
""".strip()

CHUNK_MAP_SYSTEM_OPINION = f"""
You are summarizing one contiguous slice of a YouTube OPINION/ESSAY transcript. Focus on:
- The speaker's core claim and the step-by-step reasoning structure
- Counterarguments raised and how the speaker addresses each
- Specific examples or evidence cited in support
- Points where the speaker's position is qualified or shifts
{_INSIGHT_RULE}
Be dense and factual. Respond with JSON only, no markdown fences.
""".strip()

_CHUNK_MAP_SYSTEM_BY_TYPE: Dict[str, str] = {
    "tutorial": CHUNK_MAP_SYSTEM_TUTORIAL,
    "lecture": CHUNK_MAP_SYSTEM_LECTURE,
    "opinion": CHUNK_MAP_SYSTEM_OPINION,
    "general": CHUNK_MAP_SYSTEM,
}


def _get_chunk_map_system(video_type: str) -> str:
    return _CHUNK_MAP_SYSTEM_BY_TYPE.get(video_type, CHUNK_MAP_SYSTEM)


def _map_reduce_enabled() -> bool:
    return os.environ.get("MAP_REDUCE_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _map_reduce_min_transcript_len() -> int:
    return int(os.environ.get("MAP_REDUCE_MIN_TRANSCRIPT_CHARS", "46000"))


def _map_chunk_target_chars() -> int:
    return int(os.environ.get("MAP_CHUNK_TARGET_CHARS", "45000"))


def _map_max_chunks() -> int:
    return int(os.environ.get("MAP_REDUCE_MAX_CHUNKS", "16"))


def _map_concurrency() -> int:
    return max(1, int(os.environ.get("MAP_REDUCE_CONCURRENCY", "2")))


def _parse_timestamp_match_to_seconds(match: re.Match[str]) -> int:
    first = match.group(1)
    second = match.group(2)
    third = match.group(3)
    if third is None:
        return int(first) * 60 + int(second)
    return int(first) * 3600 + int(second) * 60 + int(third)


def _timestamp_marker_positions(transcript: str) -> List[Tuple[int, int]]:
    return [
        (match.start(), _parse_timestamp_match_to_seconds(match))
        for match in _BOUNDS_RE.finditer(transcript or "")
    ]


def _split_transcript_for_map_by_chapters(
    transcript: str,
    chapters: Optional[List[Any]],
    duration: str,
) -> List[str]:
    chapter_windows = _normalize_chapter_sections(chapters, duration)
    if len(chapter_windows) <= 1:
        return [transcript]

    markers = _timestamp_marker_positions(transcript)
    if not markers:
        return [transcript]

    split_positions: List[int] = []
    last_pos = 0
    for chapter in chapter_windows[1:]:
        boundary_seconds = int(chapter.get("start_seconds", 0))
        candidates = [
            pos
            for pos, seconds in markers
            if pos > last_pos and abs(seconds - boundary_seconds) <= 30
        ]
        if candidates:
            split_pos = candidates[0]
        else:
            future_markers = [(pos, seconds) for pos, seconds in markers if pos > last_pos]
            if not future_markers:
                continue
            split_pos, _ = min(
                future_markers,
                key=lambda item: abs(item[1] - boundary_seconds),
            )
        if split_pos <= last_pos:
            continue
        split_positions.append(split_pos)
        last_pos = split_pos

    if not split_positions:
        return [transcript]

    chunks: List[str] = []
    start_pos = 0
    for split_pos in split_positions:
        chunk = transcript[start_pos:split_pos]
        if chunk.strip():
            chunks.append(chunk)
        start_pos = split_pos
    final_chunk = transcript[start_pos:]
    if final_chunk.strip():
        chunks.append(final_chunk)
    return chunks if len(chunks) > 1 else [transcript]


def split_transcript_for_map(transcript: str, chapters: Optional[List[Any]] = None, duration: str = "") -> List[str]:
    """Split the transcript into sequential chunks anchored near timestamps."""
    if not _map_reduce_enabled() or len(transcript) < _map_reduce_min_transcript_len():
        return [transcript]

    chapter_chunks = _split_transcript_for_map_by_chapters(transcript, chapters, duration)
    if len(chapter_chunks) > 1:
        return chapter_chunks

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
        raw_end = min(i + size, L)
        end = _find_split_point(transcript, raw_end, min_start=i) if raw_end < L else L
        end = max(i + 1, end)
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
    chunk_start_seconds: int = 0,
    chunk_end_seconds: int = 0,
) -> str:
    target_count = _target_section_count_for_span(chunk_start_seconds, chunk_end_seconds)
    span_seconds = max(0, chunk_end_seconds - chunk_start_seconds)
    return f"""Video context (shared across all parts):
Title: {title}
Channel: {channel}
Stated duration: {duration}
This is PART {chunk_index + 1} of {num_chunks} of the full timestamped transcript. [MM:SS] or [H:MM:SS] marks refer to the real video timeline.
This chunk covers roughly {_format_window_range(chunk_start_seconds, chunk_end_seconds)}.
Transcript (this part only):
{chunk_text}

Return a single JSON object with this schema (all fields required; use [] or "" if nothing applies):
{{
  "chunk_index": {chunk_index},
  "part_of": {num_chunks},
  "summary_paragraph": "5-8 dense sentences covering what happens in this span only, with specifics (names, numbers, tools, claims, examples) when present",
  "subsection_candidates": [
    {{
      "title": "Short section title for this time span",
      "timestamp": "MM:SS or H:MM:SS as first seen in this chunk (must match transcript labels)",
      "timestamp_seconds": <integer, seconds from video start, infer from the bracket labels>,
      "description": "2-3 sentences with concrete detail",
      "steps": ["process step if any, else []"],
      "sub_points": ["specific fact, number, named tool, argument, or example from this section"],
      "trade_offs": ["limitations, caveats, or trade-offs if discussed; else []"],
      "notable_detail": "one concrete fact or empty string"
    }}
  ],
  "insight_seeds": ["4-8 insights each following [specific claim] + [why/mechanism] + [timestamp evidence]"],
  "concept_seeds": [{{"concept": "name", "explanation": "2-3 sentences", "why_it_matters": "1 sentence", "example_from_video": "specific example or demo"}}],
  "recommendation_seeds": ["specific action tied to a use case or condition"],
  "keywords_local": ["terms named in this chunk"]
}}

Rules:
- subsection_candidates: return EXACTLY {target_count} chronological subsection_candidates for this chunk.
- Treat this chunk as a timeline span of about {span_seconds} seconds and divide it into {target_count} equal windows of roughly 5 minutes each.
- Chunk window plan:
{_chunk_window_plan(chunk_start_seconds, chunk_end_seconds)}
- Return exactly one subsection_candidate per chunk window.
- Each subsection_candidate timestamp_seconds must fall inside its assigned chunk window and should anchor the strongest material in that window.
- Do not collapse the whole chunk into one broad candidate. Missing the middle or back half of this chunk is a failure.
""".strip()


def _reduce_user_prompt(
    title: str,
    channel: str,
    duration: str,
    chunk_json_lines: str,
    num_map_parts: int,
    video_type: str = "general",
    chapters: Optional[List[Any]] = None,
) -> str:
    target_count = len(_section_windows(duration, chapters))
    section_span_seconds = _target_section_span_seconds(duration)
    return f"""You are producing the final deliverable for a long YouTube video. Below are structured notes from {num_map_parts} sequential parts of the full transcript (map phase). Synthesize them into one coherent analysis - do not treat any part as more important by position; the video is long and content is distributed.

Video:
Title: {title}
Channel: {channel}
Duration: {duration}

MAP PHASE NOTES (JSON lines, in timeline order):
{chunk_json_lines}

Task: produce the same comprehensive JSON you would for a full transcript read, but using ONLY these notes plus logical merging (no invention). Build a full-runtime section backbone that covers the entire video from start to finish. You may merge nearby subsection_candidates when they belong to the same target time window, but do not let any target window go missing.

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
    "key_sections": [
      {{
        "title": "Descriptive section title (required)",
        "timestamp": "MM:SS or H:MM:SS",
        "timestamp_seconds": 0,
        "description": "2-3 dense sentences with concrete detail",
        "steps": ["process step if applicable, else []"],
        "sub_points": ["specific fact, named tool, metric, argument, or example"],
        "trade_offs": ["limitation or caveat if discussed, else []"],
        "notable_detail": "one concrete memorable fact or empty string"
      }}
    ],
    "key_insights": {{ "bullets": [ ... 4-8 items ... ] }},
    "deep_dive": {{ "sections": [{{"heading": "Heading", "paragraphs": ["Paragraph"]}}] }},
    "important_concepts": [ ... ],
    "comparison_table": {{ "applicable": true/false, "headers": [], "rows": [] }},
    "practical_recommendations": [ ... ],
    "conclusion": "...",
    "keywords": [ ... ],
    "action_items": [ ... ]
  }},
  "mindmap": {{
    "id": "root",
    "label": "...",
    "category": "root",
    "children": [ ... same nested id/label/category/children as standard ... ]
  }}
}}

Rules:
- key_sections: return EXACTLY {target_count} sections for this {duration} video.
- Divide the runtime into {target_count} equal chronological windows of about {section_span_seconds} seconds each and return exactly one section for each window.
- Window plan:
{_section_window_plan(duration, chapters)}
- Merge subsection_candidates within the same window when needed, but do not skip any window.
- The timestamp for each section must fall inside its assigned window and should anchor the most important material in that span.
- Sections MUST cover the entire runtime from start to finish. Missing the middle or back half is a failure.
- Every section MUST include a non-empty "title" field plus timestamp, timestamp_seconds, description, steps, sub_points, trade_offs, notable_detail.
- sub_points: merge from concept_seeds and subsection candidates; no empty filler.
- key_insights.bullets: return 4-8 high-signal bullets that summarize major takeaways from the whole video.
- Do not use the old specific-claim-plus-timestamp pattern item by item.
- deep_dive.sections: make it a real standalone analysis with explicit headings, not a padded recap.
- deep_dive.sections should contain 4-6 headed sections with 1-2 dense paragraphs each.
- The deep dive headings should be type-aware for this video type ({video_type}) and should function like a self-contained AI summary, not a loose extension of key_sections.
- important_concepts: 6-10 items for long videos, with substantial explanations and an example_from_video where possible.
- practical_recommendations: synthesize recommendation_seeds from across chunks into actionable recommendations.
- mindmap: 4-7 main branches, leaves are substantive sentences.
- Return valid JSON only, no ``` fences.
"""


def _sections_only_user_prompt(
    title: str,
    channel: str,
    duration: str,
    transcript: str,
    video_type: str,
    chapters: Optional[List[Any]] = None,
) -> str:
    target_count = len(_section_windows(duration, chapters))
    section_span_seconds = _target_section_span_seconds(duration)
    type_emphasis = {
        "tutorial": "Focus on the actual demonstrated sequence: commands, tools, before/after states, and mistakes or caveats.",
        "lecture": "Focus on the argument structure: claims, evidence, definitions, and how later sections build on earlier ones.",
        "opinion": "Focus on the thesis, supporting reasons, counterarguments, and moments where the speaker qualifies the position.",
        "general": "Focus on the real topic shifts, concrete examples, and the logic that connects sections.",
    }.get(video_type, "Focus on the real topic shifts, concrete examples, and the logic that connects sections.")

    chapter_instructions = ""
    if _normalize_chapter_sections(chapters, duration):
        chapter_instructions = f"""
- Use the uploader-provided YouTube chapters as the canonical key section backbone.
- Return EXACTLY one key_section per uploader chapter.
- Keep each key_section title aligned to the uploader chapter title unless the transcript clearly shows a minor wording improvement.
- Use this uploader chapter plan:
{_section_window_plan(duration, chapters)}
""".strip()

    return f"""
You are extracting the section backbone for a long-form video summary.

Video:
Title: {title}
Channel: {channel}
Duration: {duration}
Type hint: {video_type}

Your job is ONLY to identify the strongest chronological key sections. Do not write the full summary yet.
{type_emphasis}

Transcript:
{transcript}

Respond with valid JSON only:
{{
  "key_sections": [
    {{
      "title": "Descriptive section title",
      "timestamp": "01:23",
      "timestamp_seconds": 83,
      "description": "2-3 dense sentences explaining exactly what happens in this section and why it matters in the overall video",
      "steps": ["Actual steps shown by the speaker if applicable, else []"],
      "sub_points": ["Specific named fact, metric, example, argument, or tool from this section"],
      "trade_offs": ["Actual trade-offs or limitations discussed here, else []"],
      "notable_detail": "One concrete memorable detail from this section or empty string"
    }}
  ]
}}

Rules:
- Return EXACTLY {target_count} key_sections for this duration.
- Divide the runtime into {target_count} equal chronological windows of about {section_span_seconds} seconds each and return exactly one section for each window.
- Window plan:
{_section_window_plan(duration, chapters)}
- If uploader chapters are present, prefer those chapter windows and titles over synthetic 5-minute windows.
- {chapter_instructions if chapter_instructions else "If uploader chapters are absent, use the window plan above as the section backbone."}
- Cover the entire runtime in order. Do not skip any window even if the content feels lighter there.
- Every section must be anchored to a real transcript timestamp.
- Each section timestamp must fall inside its assigned window and should represent the strongest material in that span.
- Avoid generic titles like "Introduction", "Main Discussion", "More Details", "Conclusion" unless the transcript itself is truly generic.
- description and sub_points must contain specifics: names, tools, metrics, examples, claims, or decisions.
- Each description should be about {_section_description_budget(duration)}. Do not write a one-line stub.
- For videos over 45 minutes, each description should land in the 150-200 word range and should feel like a substantial section note, not a teaser.
- Each section should have {_section_subpoint_budget(duration)} sub_points unless the source for that section is genuinely sparse.
- notable_detail should be 1 concrete fact, stat, quote, or example in 15-40 words whenever the transcript supports it.
- steps should contain the actual demonstrated sequence for process-heavy sections; do not leave them empty if the speaker clearly walks through a process.
- Missing the back half of the video is a failure.
""".strip()


def _summary_from_sections_user_prompt(
    title: str,
    channel: str,
    duration: str,
    sections: List[Dict[str, Any]],
    video_type: str,
) -> str:
    sections_json = json.dumps(sections, ensure_ascii=False, indent=2)
    return f"""
You are writing the final study-note-quality summary for a video using an already-extracted section backbone.

Video:
Title: {title}
Channel: {channel}
Duration: {duration}

Section backbone (chronological and authoritative):
{sections_json}

Respond with valid JSON only:
{{
  "video_overview": {{
    "title": "{title}",
    "channel": "{channel}",
    "duration": "{duration}",
    "main_topic": "One precise sentence describing the video's true subject",
    "elevator_pitch": "2-4 sentences covering the overall arc, what the speaker actually does, and what the viewer learns"
  }},
  "key_insights": {{
    "bullets": [
      "A high-signal bullet that synthesizes a major takeaway from the whole video"
    ]
  }},
  "deep_dive": {{
    "sections": [
      {{
        "heading": "Type-aware heading",
        "paragraphs": [
          "Dense paragraph grounded in the section backbone",
          "Dense paragraph grounded in the section backbone"
        ]
      }}
    ]
  }},
  "important_concepts": [
    {{
      "concept": "Concept name",
      "explanation": "3-5 sentences explaining it in the context of this video",
      "why_it_matters": "1-2 sentences of practical significance",
      "example_from_video": "Specific example or demonstration from the video"
    }}
  ],
  "comparison_table": {{
    "applicable": true,
    "headers": ["Option/Method", "Performance", "Cost", "Best For", "Trade-offs"],
    "rows": [["Option", "detail", "detail", "detail", "detail"]]
  }},
  "practical_recommendations": ["Actionable recommendation tied to a specific condition or use case"],
  "conclusion": "3-5 sentence synthesis of the speaker's real ending and the most important takeaway",
  "keywords": ["specific named entities, tools, methods, or topics"],
  "action_items": ["Immediate action the viewer can take"]
}}

Rules:
- Do not rewrite or merge the sections. Treat them as fixed source material.
- key_insights.bullets: return 4-8 bullets.
- Each bullet should summarize a major takeaway from the whole video, not one narrow local moment.
- Do not use the old [claim] + [why/mechanism] + [timestamp evidence] formula.
- Each bullet should be roughly {_insight_word_budget(duration)} and must stay under 220 words.
- Bullets should feel like a strong overall summary a user can scan before opening Key Sections.
- deep_dive.sections: write a strong standalone deep dive with proper headings, not a shallow recap.
- Use 4-6 sections with headings.
- Infer the best 4-6 headings directly from the section backbone. Do not force a tutorial/lecture/opinion outline unless the sections themselves clearly support it.
- Group related sections under headings that reflect the actual content themes, not the video type label.
- Each heading should represent a major component that emerges from the section backbone and should synthesize the grouped sections rather than repeating them verbatim.
- If the wording of a heading can be improved, rewrite it, but keep the theme and grouping logic intact.
- Each section should contain 1-2 dense paragraphs.
- The total deep dive should be at least {_deep_dive_min_word_count(duration)} words for this video, and longer videos should naturally produce more text.
- Taken together, the deep dive should read like a complete AI summary with explicit subheadings and should synthesize the video's logic, examples, trade-offs, and practical significance.
- It should be useful even if the user reads only the deep dive and never opens the other tabs.
- important_concepts: 6-10 items for long videos and each should pull from different parts of the section backbone where possible.
- Each important_concepts.explanation should be roughly {_concept_explanation_budget(duration)} and should not exceed 220 words.
- practical_recommendations: 4-8 items, each grounded in something specific from the sections.
- Each practical recommendation should be roughly {_recommendation_word_budget(duration)} and should not exceed 80 words.
- conclusion should be roughly {_conclusion_word_budget(duration)} and should not exceed 260 words.
- video_overview.elevator_pitch should be 70-140 words for long videos and should not exceed 180 words.
- comparison_table: only set applicable=true if the sections actually support a real comparison.
- Never use placeholder filler. Everything must trace back to the supplied sections.
""".strip()


def _mindmap_from_sections_user_prompt(
    title: str,
    channel: str,
    duration: str,
    sections: List[Dict[str, Any]],
) -> str:
    sections_json = json.dumps(sections, ensure_ascii=False, indent=2)
    return f"""
You are building a mind map tree from a video's extracted sections.

Video:
Title: {title}
Channel: {channel}
Duration: {duration}

Section backbone:
{sections_json}

Respond with valid JSON only:
{{
  "mindmap": {{
    "id": "root",
    "label": "Central thesis, max 40 chars",
    "category": "root",
    "children": [
      {{
        "id": "branch-1",
        "label": "Major theme or section, max 55 chars",
        "category": "concept",
        "children": [
          {{
            "id": "branch-1-1",
            "label": "Full sentence leaf with a concrete fact, claim, step, metric, or example",
            "category": "data",
            "children": []
          }}
        ]
      }}
    ]
  }}
}}

Rules:
- Use 5-9 major branches when the source supports them.
- Branches must map directly to the real section backbone, not generic categories.
- Leaves must be concrete, standalone sentences, not topic labels.
- Prefer one fact per leaf.
- Include process steps where relevant by making them leaves under the relevant branch.
- Avoid duplicate branches and duplicate leaves.
""".strip()


async def _run_json_llm(
    *,
    system_prompt: str,
    user_prompt: str,
    max_out_tokens: int,
    user_api_key: Optional[str],
    user_provider: Optional[str],
    user_model: Optional[str],
    openrouter_full_fallback: bool = True,
) -> Dict[str, Any]:
    raw_content = await complete_llm_text(
        system_prompt,
        user_prompt,
        max_out_tokens,
        user_api_key,
        user_provider,
        user_model,
        openrouter_full_fallback=openrouter_full_fallback,
    )
    return json.loads(_strip_code_fences(raw_content))


def _summary_shell_with_sections(
    summary_rest: Dict[str, Any],
    sections: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "video_overview": summary_rest.get("video_overview", {}),
        "key_sections": sections,
        "key_insights": summary_rest.get("key_insights", {"bullets": []}),
        "deep_dive": summary_rest.get("deep_dive", {"sections": [], "text": ""}),
        "important_concepts": summary_rest.get("important_concepts", []),
        "comparison_table": summary_rest.get(
            "comparison_table",
            {"applicable": False, "headers": [], "rows": []},
        ),
        "practical_recommendations": summary_rest.get("practical_recommendations", []),
        "conclusion": summary_rest.get("conclusion", ""),
        "keywords": summary_rest.get("keywords", []),
        "action_items": summary_rest.get("action_items", []),
    }


async def _emit_partial(
    partial_callback: Optional[PartialCallback],
    *,
    summary: Dict[str, Any],
    mindmap: Optional[Dict[str, Any]] = None,
    stage: str = "",
) -> None:
    if not partial_callback:
        return
    await partial_callback(
        {
            "stage": stage,
            "summary": summary,
            "mindmap": mindmap or {},
        }
    )


async def _extract_sections_single_pass(
    *,
    title: str,
    channel: str,
    duration: str,
    transcript: str,
    user_api_key: Optional[str],
    user_provider: Optional[str],
    user_model: Optional[str],
    video_type: str,
    chapters: Optional[List[Any]] = None,
    transcript_segments: Optional[List[Any]] = None,
) -> List[Dict[str, Any]]:
    _log_section_plan(duration, chapters)
    payload = await _run_json_llm(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=_sections_only_user_prompt(
            title,
            channel,
            duration,
            truncate_transcript(transcript),
            video_type,
            chapters,
        ),
        max_out_tokens=10000,
        user_api_key=user_api_key,
        user_provider=user_provider,
        user_model=user_model,
        openrouter_full_fallback=True,
    )
    sections = [
        normalized
        for normalized in (_normalize_key_section(item) for item in _extract_key_sections_payload(payload))
        if normalized.get("title")
    ]
    sections = await _polish_key_sections(
        title=title,
        channel=channel,
        duration=duration,
        sections=sections,
        transcript_segments=transcript_segments,
        user_api_key=user_api_key,
        user_provider=user_provider,
        user_model=user_model,
    )
    _log_section_timestamps("Single-pass extracted key sections", sections)
    return sections


async def _synthesize_summary_from_sections(
    *,
    title: str,
    channel: str,
    duration: str,
    sections: List[Dict[str, Any]],
    video_type: str,
    user_api_key: Optional[str],
    user_provider: Optional[str],
    user_model: Optional[str],
) -> Dict[str, Any]:
    return await _run_json_llm(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=_summary_from_sections_user_prompt(
            title,
            channel,
            duration,
            sections,
            video_type,
        ),
        max_out_tokens=12000,
        user_api_key=user_api_key,
        user_provider=user_provider,
        user_model=user_model,
        openrouter_full_fallback=True,
    )


async def _synthesize_mindmap_from_sections(
    *,
    title: str,
    channel: str,
    duration: str,
    sections: List[Dict[str, Any]],
    user_api_key: Optional[str],
    user_provider: Optional[str],
    user_model: Optional[str],
) -> Dict[str, Any]:
    payload = await _run_json_llm(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=_mindmap_from_sections_user_prompt(title, channel, duration, sections),
        max_out_tokens=8000,
        user_api_key=user_api_key,
        user_provider=user_provider,
        user_model=user_model,
        openrouter_full_fallback=True,
    )
    mindmap = payload.get("mindmap", payload)
    return mindmap if isinstance(mindmap, dict) else {"id": "root", "label": title[:40] or "Summary", "category": "root", "children": []}


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
    video_type: str = "general",
) -> Dict[str, Any]:
    chunk_start_seconds, chunk_end_seconds = _extract_chunk_bounds(chunk)
    user_prompt = _map_chunk_user_prompt(
        title,
        channel,
        duration,
        idx,
        total,
        chunk,
        chunk_start_seconds=chunk_start_seconds,
        chunk_end_seconds=chunk_end_seconds,
    )
    raw = await complete_llm_text(
        _get_chunk_map_system(video_type),
        user_prompt,
        6000,
        user_api_key,
        user_provider,
        user_model,
        openrouter_full_fallback=False,
    )
    return json.loads(_strip_code_fences(raw))


async def run_map_reduce_summarization(
    title: str,
    channel: str,
    duration: str,
    full_transcript: str,
    user_api_key: Optional[str] = None,
    user_provider: Optional[str] = None,
    user_model: Optional[str] = None,
    video_type: str = "general",
    chapters: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    chunks = split_transcript_for_map(full_transcript, chapters, duration)
    if len(chunks) <= 1:
        raise RuntimeError("internal: run_map_reduce called with single chunk")

    logger.info("Map-reduce: %s transcript chars -> %s chunks", len(full_transcript), len(chunks))
    _log_section_plan(duration, chapters)
    _log_chunk_boundaries(chunks)
    sem = asyncio.Semaphore(_map_concurrency())

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
                        video_type=video_type,
                    )
                    return i, data
                except (json.JSONDecodeError, Exception) as exc:
                    if attempt == 2:
                        logger.error("Map chunk %s failed: %s", i, exc)
                        raise
                    await asyncio.sleep(1.5 * (attempt + 1))
            raise RuntimeError(f"Map chunk {i} failed after retries")

    results = await asyncio.gather(*[_protected(i, chunk) for i, chunk in enumerate(chunks)])
    results.sort(key=lambda item: item[0])
    chunk_supports = [
        _normalize_chunk_support(obj, chunk_index=i, chunk_text=chunks[i])
        for i, obj in results
    ]

    merged_lines: List[str] = []
    for i, (_, obj) in enumerate(results):
        merged_lines.append("---CHUNK-JSON---")
        merged_lines.append(json.dumps(obj, ensure_ascii=False))
        candidates = obj.get("subsection_candidates", [])
        logger.warning("Map chunk %s: %s subsection_candidates: %s", i, len(candidates), [c.get("timestamp","?") for c in candidates])
    logger.warning("Map total subsection_candidates across %s chunks: %s", len(results), sum(len(obj.get("subsection_candidates", [])) for _, obj in results))
    all_candidates = [
        candidate
        for _, obj in results
        for candidate in obj.get("subsection_candidates", [])
        if isinstance(candidate, dict)
    ]
    selected_sections = _build_sections_from_candidates(all_candidates, duration, chapters, chunk_supports)
    _log_section_timestamps("Deterministic map-stage key sections", selected_sections)
    return {
        "summary": {
            "key_sections": selected_sections,
        }
    }


async def generate_summary_and_mindmap_single_pass(
    title: str,
    channel: str,
    duration: str,
    transcript: str,
    user_api_key: str = None,
    user_provider: str = None,
    user_model: str = None,
    video_type: str = "general",
    partial_callback: Optional[PartialCallback] = None,
    chapters: Optional[List[Any]] = None,
    transcript_segments: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """Single-pass staged path."""
    max_retries = 3
    backoff = [2, 4, 8]
    for attempt in range(max_retries):
        try:
            logger.info("Single-pass staged summary request...")
            sections = await _extract_sections_single_pass(
                title=title,
                channel=channel,
                duration=duration,
                transcript=transcript,
                user_api_key=user_api_key,
                user_provider=user_provider,
                user_model=user_model,
                video_type=video_type,
                chapters=chapters,
                transcript_segments=transcript_segments,
            )
            await _emit_partial(
                partial_callback,
                summary=_summary_shell_with_sections({}, sections),
                stage="sections",
            )
            summary_rest = await _synthesize_summary_from_sections(
                title=title,
                channel=channel,
                duration=duration,
                sections=sections,
                video_type=video_type,
                user_api_key=user_api_key,
                user_provider=user_provider,
                user_model=user_model,
            )
            await _emit_partial(
                partial_callback,
                summary=_summary_shell_with_sections(summary_rest, sections),
                stage="summary",
            )
            mindmap = await _synthesize_mindmap_from_sections(
                title=title,
                channel=channel,
                duration=duration,
                sections=sections,
                user_api_key=user_api_key,
                user_provider=user_provider,
                user_model=user_model,
            )
            await _emit_partial(
                partial_callback,
                summary=_summary_shell_with_sections(summary_rest, sections),
                mindmap=mindmap,
                stage="mindmap",
            )
            return _backfill_summary_depth(
                {
                    "summary": _summary_shell_with_sections(summary_rest, sections),
                    "mindmap": mindmap,
                },
                duration=duration,
                video_type=video_type,
            )
        except (RateLimitError, OpenAIRateLimitError):
            if attempt < max_retries - 1:
                logger.warning("Rate limited. Retrying in %s s...", backoff[attempt])
                await asyncio.sleep(backoff[attempt])
            else:
                logger.error("Rate limit retry exhausted.")
                raise RuntimeError("CLAUDE_API_ERROR: Rate limits exhausted.")
        except OpenAIAPIError as exc:
            if attempt < max_retries - 1 and getattr(exc, "status_code", None) == 429:
                await asyncio.sleep(backoff[attempt])
                continue
            logger.error("OpenRouter API error: %s", exc)
            raise RuntimeError(f"CLAUDE_API_ERROR: {str(exc)}")
        except json.JSONDecodeError as exc:
            logger.error("Claude returned invalid JSON: %s", exc)
            if attempt < max_retries - 1:
                await asyncio.sleep(backoff[attempt])
                continue
            raise RuntimeError("CLAUDE_PARSE_ERROR: Failed to parse AI response.")
        except Exception as exc:
            err = str(exc)
            if ("Rate limited" in err or "429" in err) and attempt < max_retries - 1:
                await asyncio.sleep(backoff[attempt])
                continue
            logger.error("Error calling LLM: %s", exc)
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
    video_type: str = "general",
    partial_callback: Optional[PartialCallback] = None,
    chapters: Optional[List[Any]] = None,
    transcript_segments: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """
    Pick map-reduce for long transcripts, otherwise use single-pass.
    """
    if _map_reduce_enabled() and len(transcript) >= _map_reduce_min_transcript_len():
        parts = split_transcript_for_map(transcript, chapters, duration)
        if len(parts) > 1:
            try:
                logger.info(
                    "Using map-reduce pipeline (%s chars, %s chunks) with staged synthesis.",
                    len(transcript),
                    len(parts),
                )
                section_seed = await run_map_reduce_summarization(
                    title,
                    channel,
                    duration,
                    transcript,
                    user_api_key=user_api_key,
                    user_provider=user_provider,
                    user_model=user_model,
                    video_type=video_type,
                    chapters=chapters,
                )
                sections = [
                    normalized
                    for normalized in (
                        _normalize_key_section(item)
                        for item in _extract_key_sections_payload(section_seed)
                    )
                    if normalized.get("title")
                ]
                sections = await _polish_key_sections(
                    title=title,
                    channel=channel,
                    duration=duration,
                    sections=sections,
                    transcript_segments=transcript_segments,
                    user_api_key=user_api_key,
                    user_provider=user_provider,
                    user_model=user_model,
                )
                _log_section_timestamps("Post-reduce normalized key sections", sections)
                await _emit_partial(
                    partial_callback,
                    summary=_summary_shell_with_sections({}, sections),
                    stage="sections",
                )
                summary_rest = await _synthesize_summary_from_sections(
                    title=title,
                    channel=channel,
                    duration=duration,
                    sections=sections,
                    video_type=video_type,
                    user_api_key=user_api_key,
                    user_provider=user_provider,
                    user_model=user_model,
                )
                await _emit_partial(
                    partial_callback,
                    summary=_summary_shell_with_sections(summary_rest, sections),
                    stage="summary",
                )
                mindmap = await _synthesize_mindmap_from_sections(
                    title=title,
                    channel=channel,
                    duration=duration,
                    sections=sections,
                    user_api_key=user_api_key,
                    user_provider=user_provider,
                    user_model=user_model,
                )
                await _emit_partial(
                    partial_callback,
                    summary=_summary_shell_with_sections(summary_rest, sections),
                    mindmap=mindmap,
                    stage="mindmap",
                )
                return _backfill_summary_depth(
                    {
                        "summary": _summary_shell_with_sections(summary_rest, sections),
                        "mindmap": mindmap,
                    },
                    duration=duration,
                    video_type=video_type,
                )
            except Exception as exc:
                logger.warning(
                    "Map-reduce staged synthesis failed (%s). Falling back to staged single-pass.",
                    exc,
                )
    return await generate_summary_and_mindmap_single_pass(
        title,
        channel,
        duration,
        transcript,
        user_api_key=user_api_key,
        user_provider=user_provider,
        user_model=user_model,
        video_type=video_type,
        partial_callback=partial_callback,
        chapters=chapters,
        transcript_segments=transcript_segments,
    )

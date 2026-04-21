import os
import json
import logging
import asyncio
from anthropic import AsyncAnthropic, RateLimitError
from openai import AsyncOpenAI
from openai import RateLimitError as OpenAIRateLimitError
from openai import APIError as OpenAIAPIError
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Lazy initialization helper
_client = None
_model = None
_provider = None

def get_claude_client():
    global _client, _model, _provider
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
            # Primary model; runtime fallbacks handled in generate_summary_and_mindmap().
            _model = os.environ.get("OPENROUTER_MODEL", "openrouter/free").strip()
            if not _model:
                _model = "openrouter/free"
        else:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
            if not api_key:
                raise RuntimeError("CLAUDE_API_ERROR: ANTHROPIC_API_KEY not found in environment. Please check your .env file.")
            _client = AsyncAnthropic(api_key=api_key)
            _model = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001").strip()

    return _client, _model, _provider

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
    Truncate transcript to ~48k characters.
    First 36k + [...truncated...] + last 12k.
    """
    if len(transcript) <= 48000:
        return transcript

    first_part = transcript[:36000]
    last_part = transcript[-12000:]
    return f"{first_part}\n\n[...truncated...]\n\n{last_part}"

async def generate_summary_and_mindmap(title: str, channel: str, duration: str, transcript: str) -> Dict[str, Any]:
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
1. key_sections: Identify 5-8 distinct sections. For tutorial/how-to videos, steps[] must list each actual step the speaker demonstrates. sub_points[] must include specific names, numbers, or tools mentioned — no vague filler.
2. key_insights: 6-10 points. Each must be specific with evidence — "X because Y, demonstrated by Z" — not "the speaker discusses X".
3. important_concepts: 4-8 concepts with substantive explanations.
4. comparison_table: Set applicable=true only if the video compares multiple options/methods/tools. If applicable, create a table reflecting the actual comparisons made in the video. If not applicable, set applicable=false and use empty arrays for headers and rows.
5. practical_recommendations: 4-8 recommendations tied to specific conditions or use cases.
6. conclusion: Must reflect the presenter's actual closing argument, not just a restatement of the title.
7. keywords: 8-15 specific technical terms or named entities from the video.
8. action_items: If none exist, return [].
9. screenshot_timestamps: Return 6-10 moments, aiming for roughly one per major section. section_title must exactly match one of key_sections.title values. Keep each timestamp inside that section's time window, usually 2-10 seconds after the section begins unless the transcript strongly indicates a later visual moment.

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
            logger.info(f"Sending request to Claude...")
            client, model, provider = get_claude_client()
            if provider == "openrouter":
                fallback_raw = os.environ.get(
                    "OPENROUTER_FALLBACK_MODELS",
                    "qwen/qwen3-next-80b-a3b-instruct:free,meta-llama/llama-3.3-70b-instruct:free,google/gemma-4-31b-it:free"
                ).strip()
                fallback_models = [m.strip() for m in fallback_raw.split(",") if m.strip()]
                use_low_cost_fallback = os.environ.get("OPENROUTER_USE_LOW_COST_FALLBACK", "true").strip().lower() in ("1", "true", "yes", "on")
                low_cost_model = os.environ.get("OPENROUTER_LOW_COST_MODEL", "openai/gpt-4o-mini").strip()
                candidate_models = []
                low_cost_models = [low_cost_model] if (use_low_cost_fallback and low_cost_model) else []
                for m in [model, *fallback_models, *low_cost_models]:
                    if m and m not in candidate_models:
                        candidate_models.append(m)

                last_router_error = None
                raw_content = ""

                def _extract_openrouter_text(message_obj: Any) -> str:
                    """Handle OpenRouter/OpenAI content variants safely."""
                    if message_obj is None:
                        return ""

                    content = getattr(message_obj, "content", None)
                    if isinstance(content, str):
                        return content.strip()

                    # Some providers return content as a list of typed chunks.
                    if isinstance(content, list):
                        chunks = []
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

                    # Fallback for unusual SDK objects.
                    txt = getattr(message_obj, "text", None)
                    if txt:
                        return str(txt).strip()
                    return ""

                for candidate_model in candidate_models:
                    try:
                        logger.info(f"Trying OpenRouter model: {candidate_model}")
                        request_kwargs = {
                            "model": candidate_model,
                            "temperature": 0,
                            "messages": [
                                {"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user", "content": user_prompt},
                            ],
                        }

                        # Ask for strict JSON when supported.
                        try:
                            response = await client.chat.completions.create(
                                **request_kwargs,
                                response_format={"type": "json_object"},
                            )
                        except OpenAIAPIError as json_format_error:
                            json_err = str(json_format_error).lower()
                            if "response_format" in json_err or "unsupported" in json_err:
                                logger.warning(
                                    f"Model {candidate_model} does not support response_format=json_object. Retrying without it."
                                )
                                response = await client.chat.completions.create(**request_kwargs)
                            else:
                                raise

                        choices = getattr(response, "choices", None) or []
                        if not choices:
                            logger.warning(f"OpenRouter model returned no choices: {candidate_model}. Trying next fallback.")
                            continue

                        choice = choices[0]
                        message = getattr(choice, "message", None)
                        raw_content = _extract_openrouter_text(message)
                        finish_reason = getattr(choice, "finish_reason", None)
                        if finish_reason == "length":
                            logger.error("OpenRouter response was truncated (token limit reached).")
                            raise RuntimeError("CLAUDE_PARSE_ERROR: Response was cut off — increase max_tokens/model context.")
                        if not raw_content:
                            logger.warning(f"OpenRouter model returned empty content: {candidate_model}. Trying next fallback.")
                            continue
                        break
                    except OpenAIAPIError as e:
                        err_text = str(e)
                        status_code = getattr(e, "status_code", None)
                        if status_code == 404 or "No endpoints found" in err_text:
                            logger.warning(f"OpenRouter model unavailable: {candidate_model}. Trying next fallback.")
                            last_router_error = e
                            continue
                        raise

                if not raw_content:
                    if last_router_error:
                        raise RuntimeError(
                            "CLAUDE_API_ERROR: No OpenRouter free model endpoint available. "
                            "Set OPENROUTER_MODEL/OPENROUTER_FALLBACK_MODELS to currently available slugs."
                        )
                    raise RuntimeError("CLAUDE_API_ERROR: OpenRouter returned empty content.")
            else:
                response = await client.messages.create(
                    model=model,
                    max_tokens=16000,
                    temperature=0,
                    system=SYSTEM_PROMPT,
                    messages=[
                        {"role": "user", "content": user_prompt}
                    ]
                )
                raw_content = response.content[0].text.strip()

                if response.stop_reason == "max_tokens":
                    logger.error("Claude response was truncated (max_tokens reached). Increase max_tokens.")
                    raise RuntimeError("CLAUDE_PARSE_ERROR: Response was cut off — increase max_tokens.")

            # Defensive clean up just in case Claude wraps in markdown
            if raw_content.startswith("```json"):
                raw_content = raw_content[7:]
            if raw_content.startswith("```"):
                raw_content = raw_content[3:]
            if raw_content.endswith("```"):
                raw_content = raw_content[:-3]
                
            data = json.loads(raw_content)
            return data
            
        except (RateLimitError, OpenAIRateLimitError):
            if attempt < max_retries - 1:
                logger.warning(f"Rate limited. Retrying in {backoff[attempt]} seconds...")
                await asyncio.sleep(backoff[attempt])
            else:
                logger.error("Rate limit retry exhausted.")
                raise RuntimeError("CLAUDE_API_ERROR: Rate limits exhausted.")
        except OpenAIAPIError as e:
            logger.error(f"OpenRouter API error: {e}")
            raise RuntimeError(f"CLAUDE_API_ERROR: {str(e)}")
        except json.JSONDecodeError as e:
            logger.error(f"Claude returned invalid JSON: {e}")
            raise RuntimeError("CLAUDE_PARSE_ERROR: Failed to parse AI response.")
        except Exception as e:
            logger.error(f"Error calling Claude: {e}")
            raise RuntimeError(f"CLAUDE_API_ERROR: {str(e)}")
            
    raise RuntimeError("CLAUDE_API_ERROR: Unknown failure.")

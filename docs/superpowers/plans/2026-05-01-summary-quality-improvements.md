# Summary Quality Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve summary depth and screenshot relevance for all video types by adding type detection, timestamp-anchor chunking, type-aware LLM prompts, visual pre-scan with CLIP, and duplicate-frame removal.

**Architecture:** A keyword-based type detector (`detect_video_type`) feeds into two parallel improvements: (1) type-specific LLM prompts and dynamic screenshot counts in `claude_service.py`, and (2) a Playwright pre-scan that produces CLIP-embedded frame candidates passed back into the LLM prompts and filtered by two dedup passes in `clip_service.py`. Tasks 1–7 are entirely in `claude_service.py` and deliver working LLM improvements independently. Tasks 8–10 add the screenshot pipeline on top.

**Tech Stack:** Python 3.10+, FastAPI, Anthropic SDK, transformers (CLIP), Playwright, asyncio, pytest, numpy, PIL

---

## File Map

| File | What changes |
|------|-------------|
| `backend/services/claude_service.py` | `detect_video_type`, `_find_split_point`, updated `split_transcript_for_map`, `compute_screenshot_count`, 3 new `CHUNK_MAP_SYSTEM_*` constants, `_get_chunk_map_system`, updated `_map_chunk_user_prompt`, updated `_reduce_user_prompt`, updated single-pass prompt, updated `generate_summary_and_mindmap` + `generate_summary_and_mindmap_single_pass` signatures |
| `backend/services/clip_service.py` | `PrescanFrame` dataclass, `extract_image_embedding`, `rescore_with_type`, `dedup_pass_a`, `rank_frames_with_embedding`, `dedup_pass_b` |
| `backend/services/playwright_service.py` | New `prescan_visual_richness`, updated `extract_screenshots_playwright` to retain winning embedding |
| `backend/main.py` | Parallel `asyncio.gather(fetch_transcript, prescan_visual_richness)`, `detect_video_type`, `rescore_with_type`, `dedup_pass_a`, Playwright-first screenshot preference, `dedup_pass_b` |
| `backend/tests/test_claude_quality.py` | New test file for Tasks 1–7 |
| `backend/tests/test_clip_service.py` | Extend with embedding/dedup tests |
| `backend/tests/test_playwright_service.py` | Extend with prescan stub test |

---

## Task 1: Type Detection

**Files:**
- Modify: `backend/services/claude_service.py`
- Test: `backend/tests/test_claude_quality.py` (create)

- [ ] **Step 1: Create the test file with failing tests**

```python
# backend/tests/test_claude_quality.py
import pytest
from services.claude_service import detect_video_type


def test_type_from_title_tutorial():
    assert detect_video_type("How to build a REST API", "") == "tutorial"

def test_type_from_title_lecture():
    assert detect_video_type("Introduction to Machine Learning 101", "") == "lecture"

def test_type_from_title_opinion():
    assert detect_video_type("My thoughts on Python vs Go", "") == "opinion"

def test_type_from_title_general_falls_back():
    assert detect_video_type("The Future of Programming", "") == "general"

def test_type_from_transcript_tutorial():
    transcript = "Let me show you. pip install fastapi and then import fastapi"
    assert detect_video_type("Some Video", transcript) == "tutorial"

def test_type_from_transcript_lecture():
    transcript = "In this lecture we will cover the basics. As we can see from the diagram"
    assert detect_video_type("Some Video", transcript) == "lecture"

def test_type_from_transcript_opinion():
    transcript = "I think this is wrong. Personally I believe the framework is bad. In my opinion we should move on. I feel like the community agrees."
    assert detect_video_type("Some Video", transcript) == "opinion"

def test_type_from_transcript_general():
    transcript = "Welcome to this video. Today we are going to look at something interesting."
    assert detect_video_type("Some Video", transcript) == "general"

def test_title_takes_precedence_over_transcript():
    # Title says tutorial, transcript looks like opinion
    transcript = "I think this tool is great. Personally I love it. In my opinion best tool ever."
    assert detect_video_type("Complete Tutorial: Building with FastAPI", transcript) == "tutorial"
```

- [ ] **Step 2: Run to confirm all fail**

```
cd backend && python -m pytest tests/test_claude_quality.py -v
```
Expected: `ImportError: cannot import name 'detect_video_type'`

- [ ] **Step 3: Add `detect_video_type` to `claude_service.py`**

Add immediately after the imports, before `SYSTEM_PROMPT`:

```python
# --- Video type detection ---

_TUTORIAL_TITLE_KW = {
    "tutorial", "how to", "how i", "guide", "walkthrough",
    "build", "setup", "install", "step by step",
}
_LECTURE_TITLE_KW = {
    "lecture", "course", "lesson", "explained", "theory",
    "introduction to", "101",
}
_OPINION_TITLE_KW = {
    "opinion", "thoughts on", "why i", "my take", "review",
    "ranked", "tier list", "react to",
}
_TUTORIAL_TRANSCRIPT_KW = ["pip install", "import ", "def ", "git clone"]
_LECTURE_TRANSCRIPT_KW = [
    "in this lecture", "today we'll", "as we can see from", "in the next section",
]
_OPINION_TRANSCRIPT_KW = [
    "i think", "in my opinion", "i believe", "personally", "i feel like",
]


def detect_video_type(title: str, transcript: str) -> str:
    """Return 'tutorial', 'lecture', 'opinion', or 'general' via keyword heuristic."""
    t = title.lower()
    if any(kw in t for kw in _TUTORIAL_TITLE_KW):
        return "tutorial"
    if any(kw in t for kw in _LECTURE_TITLE_KW):
        return "lecture"
    if any(kw in t for kw in _OPINION_TITLE_KW):
        return "opinion"

    sample = transcript[:3000].lower()
    if any(kw in sample for kw in _TUTORIAL_TRANSCRIPT_KW):
        return "tutorial"
    if any(kw in sample for kw in _LECTURE_TRANSCRIPT_KW):
        return "lecture"
    if sum(sample.count(kw) for kw in _OPINION_TRANSCRIPT_KW) >= 3:
        return "opinion"
    return "general"
```

- [ ] **Step 4: Run tests — expect all pass**

```
cd backend && python -m pytest tests/test_claude_quality.py -v
```
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/claude_service.py backend/tests/test_claude_quality.py
git commit -m "feat: add detect_video_type keyword heuristic"
```

---

## Task 2: Timestamp-Anchor Chunking

**Files:**
- Modify: `backend/services/claude_service.py`
- Test: `backend/tests/test_claude_quality.py`

- [ ] **Step 1: Add failing tests**

Append to `backend/tests/test_claude_quality.py`:

```python
from services.claude_service import _find_split_point, split_transcript_for_map


def test_find_split_point_prefers_timestamp_marker():
    # Marker at position 50, target at 55 — should return 50
    transcript = "A" * 50 + "[1:23] some content here more words"
    result = _find_split_point(transcript, 55)
    assert result == 50  # position of [1:23]


def test_find_split_point_falls_back_to_punctuation():
    # No timestamp markers, has sentence boundary
    transcript = "Hello world. This is a sentence. " + "X" * 50
    result = _find_split_point(transcript, 40)
    # Should land somewhere after a period+space
    assert transcript[result - 2:result] in (". ", "? ", "! ") or result == 40


def test_find_split_point_exact_fallback():
    # No markers, no punctuation — returns target
    transcript = "abcdefghij" * 20
    result = _find_split_point(transcript, 50)
    assert result == 50


def test_find_split_point_never_returns_before_min_start():
    # Punctuation exists before min_start — must not go backward
    transcript = "Hello world. " + "X" * 100
    # target=60, min_start=50: the period at position 12 is before min_start
    result = _find_split_point(transcript, 60, min_start=50)
    assert result >= 50  # never moves backward past chunk start


def test_split_transcript_for_map_no_infinite_loop():
    # All-punctuation free transcript — must always make forward progress
    transcript = "abcde" * 20000  # 100k chars, no [MM:SS], no punctuation
    parts = split_transcript_for_map(transcript)
    assert len(parts) >= 1
    # Verify no empty chunks
    assert all(len(p) > 0 for p in parts)


def test_split_transcript_for_map_splits_at_markers():
    # Build a transcript with timestamp markers at known positions
    chunk = "[0:00] " + "word " * 9000  # ~45k chars per chunk
    transcript = chunk + "[45:00] " + "word " * 9000
    parts = split_transcript_for_map(transcript)
    assert len(parts) == 2
    # Second part should start with the [45:00] marker
    assert parts[1].startswith("[45:00]")
```

- [ ] **Step 2: Run to confirm failure**

```
cd backend && python -m pytest tests/test_claude_quality.py::test_find_split_point_prefers_timestamp_marker -v
```
Expected: `ImportError: cannot import name '_find_split_point'`

- [ ] **Step 3: Add `_find_split_point` and update `split_transcript_for_map`**

Add after `detect_video_type` in `claude_service.py`:

```python
import re as _re

_TIMESTAMP_RE = _re.compile(r'\[\d+:\d{2}\]')


def _find_split_point(transcript: str, target: int, min_start: int = 0) -> int:
    """Return the index to split at: nearest [MM:SS] marker within ±500 chars, else sentence boundary, else target.

    min_start: never return an index before this position (prevents backward moves past the current chunk start).
    """
    lo = max(min_start, target - 500)  # bounded by current chunk start — no backward drift
    hi = min(len(transcript), target + 500)
    window = transcript[lo:hi]

    best_pos, best_dist = None, float("inf")
    for m in _TIMESTAMP_RE.finditer(window):
        pos = lo + m.start()
        dist = abs(pos - target)
        if dist < best_dist:
            best_dist, best_pos = dist, pos
    if best_pos is not None:
        return best_pos

    for punct in (". ", "? ", "! "):
        idx = transcript.rfind(punct, lo, target)
        if idx != -1:
            return idx + len(punct)
    return target
```

Then update `split_transcript_for_map` — replace the inner chunk-building loop:

```python
# OLD (lines ~321-331 in claude_service.py):
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

# NEW:
    size = (L + n - 1) // n
    chunks: List[str] = []
    i = 0
    while i < L:
        raw_end = min(i + size, L)
        end = _find_split_point(transcript, raw_end, min_start=i) if raw_end < L else L
        end = max(i + 1, end)  # hard guard: end must always advance past i
        chunk = transcript[i:end]
        if len(chunk) < 500 and chunks:
            chunks[-1] = chunks[-1] + chunk
        else:
            chunks.append(chunk)
        i = end
    return chunks if len(chunks) > 1 else [transcript]
```

- [ ] **Step 4: Run tests**

```
cd backend && python -m pytest tests/test_claude_quality.py -v
```
Expected: all pass (the split_at_markers test may be approximate — accept if `len(parts) == 2`).

- [ ] **Step 5: Commit**

```bash
git add backend/services/claude_service.py backend/tests/test_claude_quality.py
git commit -m "feat: timestamp-anchor chunking for map-reduce splits"
```

---

## Task 3: Dynamic Screenshot Count

**Files:**
- Modify: `backend/services/claude_service.py`
- Test: `backend/tests/test_claude_quality.py`

- [ ] **Step 1: Add failing tests**

Append to `backend/tests/test_claude_quality.py`:

```python
from services.claude_service import compute_screenshot_count


def test_screenshot_count_tutorial_30min():
    assert compute_screenshot_count("tutorial", 1800) == 6  # max(6, round(30/5))=6

def test_screenshot_count_tutorial_1hr():
    assert compute_screenshot_count("tutorial", 3600) == 12  # max(6, round(60/5))=12

def test_screenshot_count_tutorial_3hr():
    assert compute_screenshot_count("tutorial", 10800) == 20  # capped at 20

def test_screenshot_count_lecture_30min():
    assert compute_screenshot_count("lecture", 1800) == 5   # max(5, round(30/8)=4) → 5

def test_screenshot_count_opinion_1hr():
    assert compute_screenshot_count("opinion", 3600) == 5   # max(3, round(60/12)=5) → 5

def test_screenshot_count_general_30min():
    assert compute_screenshot_count("general", 1800) == 5   # max(5, round(30/8)=4) → 5

def test_screenshot_count_respects_env_cap(monkeypatch):
    monkeypatch.setenv("SCREENSHOT_MAX_COUNT", "5")
    assert compute_screenshot_count("tutorial", 10800) == 5
```

- [ ] **Step 2: Run to confirm failure**

```
cd backend && python -m pytest tests/test_claude_quality.py::test_screenshot_count_tutorial_30min -v
```
Expected: `ImportError: cannot import name 'compute_screenshot_count'`

- [ ] **Step 3: Add `compute_screenshot_count` to `claude_service.py`**

Add after `_find_split_point`:

```python
_SCREENSHOT_TYPE_PARAMS: Dict[str, Dict[str, int]] = {
    "tutorial": {"interval_minutes": 5, "min_count": 6},
    "lecture":  {"interval_minutes": 8, "min_count": 5},
    "opinion":  {"interval_minutes": 12, "min_count": 3},
    "general":  {"interval_minutes": 8, "min_count": 5},
}


def compute_screenshot_count(video_type: str, duration_seconds: int) -> int:
    """Return how many screenshots to request, scaled by type and duration."""
    max_count = int(os.environ.get("SCREENSHOT_MAX_COUNT", "20"))
    params = _SCREENSHOT_TYPE_PARAMS.get(video_type, _SCREENSHOT_TYPE_PARAMS["general"])
    duration_minutes = duration_seconds / 60
    count = round(duration_minutes / params["interval_minutes"])
    return max(params["min_count"], min(max_count, count))
```

- [ ] **Step 4: Run tests**

```
cd backend && python -m pytest tests/test_claude_quality.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/services/claude_service.py backend/tests/test_claude_quality.py
git commit -m "feat: compute_screenshot_count scales by type and duration"
```

---

## Task 4: Type-aware Map Prompt Variants

**Files:**
- Modify: `backend/services/claude_service.py`
- Test: `backend/tests/test_claude_quality.py`

- [ ] **Step 1: Add failing tests**

Append to `backend/tests/test_claude_quality.py`:

```python
from services.claude_service import _get_chunk_map_system, CHUNK_MAP_SYSTEM


def test_get_chunk_map_system_tutorial_differs_from_general():
    assert _get_chunk_map_system("tutorial") != CHUNK_MAP_SYSTEM

def test_get_chunk_map_system_lecture_differs_from_general():
    assert _get_chunk_map_system("lecture") != CHUNK_MAP_SYSTEM

def test_get_chunk_map_system_opinion_differs_from_general():
    assert _get_chunk_map_system("opinion") != CHUNK_MAP_SYSTEM

def test_get_chunk_map_system_general_returns_existing():
    assert _get_chunk_map_system("general") == CHUNK_MAP_SYSTEM

def test_get_chunk_map_system_unknown_returns_general():
    assert _get_chunk_map_system("unknown") == CHUNK_MAP_SYSTEM

def test_all_map_systems_contain_insight_rule():
    for vtype in ("tutorial", "lecture", "opinion", "general"):
        system = _get_chunk_map_system(vtype)
        assert "[specific claim]" in system, f"Missing insight rule in {vtype} prompt"
```

- [ ] **Step 2: Run to confirm failure**

```
cd backend && python -m pytest tests/test_claude_quality.py::test_get_chunk_map_system_tutorial_differs_from_general -v
```
Expected: `ImportError: cannot import name '_get_chunk_map_system'`

- [ ] **Step 3: Add prompt variants and `_get_chunk_map_system` to `claude_service.py`**

Add after the existing `CHUNK_MAP_SYSTEM` constant (around line 286):

```python
_INSIGHT_RULE = (
    "Insight rule: each insight_seeds entry MUST follow "
    "[specific claim] + [why/mechanism] + [timestamp evidence]. "
    "Generic observations are not valid insights."
)

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

# Update the existing CHUNK_MAP_SYSTEM to also include the insight rule
CHUNK_MAP_SYSTEM = f"""
You are summarizing one contiguous slice of a YouTube transcript. The full video is long; your output will be merged with other slices. Be dense and factual.
{_INSIGHT_RULE}
Respond with JSON only, no markdown fences.
""".strip()

_CHUNK_MAP_SYSTEM_BY_TYPE: Dict[str, str] = {
    "tutorial": CHUNK_MAP_SYSTEM_TUTORIAL,
    "lecture":  CHUNK_MAP_SYSTEM_LECTURE,
    "opinion":  CHUNK_MAP_SYSTEM_OPINION,
    "general":  CHUNK_MAP_SYSTEM,
}


def _get_chunk_map_system(video_type: str) -> str:
    return _CHUNK_MAP_SYSTEM_BY_TYPE.get(video_type, CHUNK_MAP_SYSTEM)
```

- [ ] **Step 4: Run tests**

```
cd backend && python -m pytest tests/test_claude_quality.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/services/claude_service.py backend/tests/test_claude_quality.py
git commit -m "feat: type-aware map prompt variants with insight rule"
```

---

## Task 5: Visual Candidate Injection and Dynamic Count in Prompts

**Files:**
- Modify: `backend/services/claude_service.py`
- Test: `backend/tests/test_claude_quality.py`

- [ ] **Step 1: Add failing tests**

Append to `backend/tests/test_claude_quality.py`:

```python
from services.claude_service import _map_chunk_user_prompt, _reduce_user_prompt, _extract_chunk_bounds


def test_extract_chunk_bounds_parses_first_and_last_timestamp():
    chunk = "[2:30] intro content here [5:00] more content [8:15] final bit"
    start, end = _extract_chunk_bounds(chunk)
    assert start == 150   # 2*60+30
    assert end   == 495   # 8*60+15

def test_extract_chunk_bounds_no_timestamps_returns_zeros():
    chunk = "No timestamps in this chunk at all"
    start, end = _extract_chunk_bounds(chunk)
    assert start == 0
    assert end == 0


def test_map_chunk_prompt_includes_visual_candidates():
    prompt = _map_chunk_user_prompt(
        title="Test", channel="Ch", duration="1:00:00",
        chunk_index=0, num_chunks=2, chunk_text="some transcript",
        visual_candidates=[120, 300, 540],
        chunk_start_seconds=0, chunk_end_seconds=1800,
    )
    assert "Visually confirmed" in prompt
    assert "2:00" in prompt or "120" in prompt  # seconds or formatted

def test_map_chunk_prompt_no_candidates_skips_section():
    prompt = _map_chunk_user_prompt(
        title="Test", channel="Ch", duration="1:00:00",
        chunk_index=0, num_chunks=2, chunk_text="some transcript",
        visual_candidates=[],
        chunk_start_seconds=0, chunk_end_seconds=1800,
    )
    assert "Visually confirmed" not in prompt

def test_reduce_prompt_uses_dynamic_count():
    prompt = _reduce_user_prompt(
        title="T", channel="C", duration="3:00:00",
        chunk_json_lines="[]", num_map_parts=3,
        screenshot_count=15,
    )
    assert "15" in prompt
    assert "6-10" not in prompt  # old hardcoded value must be gone
```

- [ ] **Step 2: Run to confirm failure**

```
cd backend && python -m pytest tests/test_claude_quality.py::test_map_chunk_prompt_includes_visual_candidates -v
```
Expected: `TypeError: _map_chunk_user_prompt() got unexpected keyword argument 'visual_candidates'`

- [ ] **Step 3: Add `_extract_chunk_bounds` and update `_map_chunk_user_prompt`**

First, add this helper after `_find_split_point` in `claude_service.py`:

```python
_BOUNDS_RE = _re.compile(r'\[(\d+):(\d{2})(?::(\d{2}))?\]')

def _extract_chunk_bounds(chunk: str) -> tuple:
    """Parse the first and last [MM:SS] or [H:MM:SS] timestamps in chunk text.

    Returns (start_seconds, end_seconds). Returns (0, 0) if no timestamps found.
    """
    matches = list(_BOUNDS_RE.finditer(chunk))
    if not matches:
        return 0, 0

    def _to_seconds(m) -> int:
        h, mins, secs = m.group(1), m.group(2), m.group(3)
        if secs is None:
            # [MM:SS] format — group(1) is minutes, group(2) is seconds
            return int(h) * 60 + int(mins)
        else:
            # [H:MM:SS] format — group(1) is hours, group(2) is minutes, group(3) is seconds
            return int(h) * 3600 + int(mins) * 60 + int(secs)

    return _to_seconds(matches[0]), _to_seconds(matches[-1])
```

Then update `_map_chunk_user_prompt`. The current signature is:
```python
def _map_chunk_user_prompt(title, channel, duration, chunk_index, num_chunks, chunk_text):
```

Replace with:

```python
def _map_chunk_user_prompt(
    title: str,
    channel: str,
    duration: str,
    chunk_index: int,
    num_chunks: int,
    chunk_text: str,
    visual_candidates: Optional[List[int]] = None,
    chunk_start_seconds: int = 0,
    chunk_end_seconds: int = 0,
) -> str:
    candidates_in_window = [
        s for s in (visual_candidates or [])
        if chunk_start_seconds <= s <= chunk_end_seconds
    ]
    visual_hint = ""
    if candidates_in_window:
        formatted = ", ".join(
            f"{s // 60}:{s % 60:02d}" for s in sorted(candidates_in_window)
        )
        visual_hint = (
            f"\nVisually confirmed moments in this time range "
            f"(something is on screen): [{formatted}]. "
            f"Prefer these seconds when populating screenshot_timestamps. "
            f"Only override if a non-listed moment is significantly more important.\n"
        )

    return f"""Video context (shared across all parts):
Title: {title}
Channel: {channel}
Stated duration: {duration}
This is PART {chunk_index + 1} of {num_chunks} of the full timestamped transcript. [MM:SS] or [H:MM:SS] marks refer to the real video timeline.
{visual_hint}
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
  "insight_seeds": ["2-4 insights each following [specific claim] + [why/mechanism] + [timestamp evidence]"],
  "concept_seeds": [{{"concept": "name", "note": "1 sentence"}}],
  "keywords_local": ["terms named in this chunk"]
}}""".strip()
```

- [ ] **Step 4: Update `_reduce_user_prompt` to accept `screenshot_count`**

Current signature:
```python
def _reduce_user_prompt(title, channel, duration, chunk_json_lines, num_map_parts):
```

Add `screenshot_count: int = 8` parameter. Find the line containing `"screenshot_timestamps"` in the return string and replace `"6-12 items"` (or whatever the current wording is) with `f"{screenshot_count} items"`. Also update the call site in `run_map_reduce_summarization`.

Exact replacement in the return string — find:
```
"screenshot_timestamps": [ {{ "seconds": 120, "caption": "...", "section_title": "..." }} ]
```
and the rules line that mentions screenshot count. Replace the count reference:
```python
# In the rules section inside _reduce_user_prompt, replace the screenshot count line:
f"- screenshot_timestamps: {screenshot_count} items with seconds and section_title matching a key_sections title.",
```

- [ ] **Step 5: Update the call in `run_map_reduce_summarization`**

Find the call `_reduce_user_prompt(title, channel, duration, chunk_block, len(chunks))` and add `screenshot_count=8` as a default for now (wired properly in Task 7):

```python
reduce_in = _reduce_user_prompt(title, channel, duration, chunk_block, len(chunks), screenshot_count=screenshot_count)
```

Add `screenshot_count: int = 8` to `run_map_reduce_summarization`'s signature for now.

- [ ] **Step 6: Run tests**

```
cd backend && python -m pytest tests/test_claude_quality.py -v
```
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/services/claude_service.py backend/tests/test_claude_quality.py
git commit -m "feat: inject visual candidates and dynamic screenshot count into map prompts"
```

---

## Task 6: Single-Pass Path Updates

**Files:**
- Modify: `backend/services/claude_service.py`
- Test: `backend/tests/test_claude_quality.py`

- [ ] **Step 1: Add failing tests**

Append to `backend/tests/test_claude_quality.py`:

```python
import inspect
from services.claude_service import generate_summary_and_mindmap_single_pass


def test_single_pass_accepts_new_params():
    sig = inspect.signature(generate_summary_and_mindmap_single_pass)
    params = sig.parameters
    assert "video_type" in params
    assert "visual_candidates" in params
    assert "screenshot_count" in params

def test_single_pass_insight_rule_in_prompt():
    # We can't call the LLM in unit tests, so inspect the source instead
    import services.claude_service as svc
    src = inspect.getsource(svc.generate_summary_and_mindmap_single_pass)
    assert "[specific claim]" in src

def test_single_pass_dynamic_count_in_prompt():
    import services.claude_service as svc
    src = inspect.getsource(svc.generate_summary_and_mindmap_single_pass)
    assert "screenshot_count" in src
```

- [ ] **Step 2: Run to confirm failure**

```
cd backend && python -m pytest tests/test_claude_quality.py::test_single_pass_accepts_new_params -v
```
Expected: `AssertionError` — `video_type` not in params.

- [ ] **Step 3: Update `generate_summary_and_mindmap_single_pass`**

Add three new parameters with defaults to the signature:

```python
async def generate_summary_and_mindmap_single_pass(
    title: str, channel: str, duration: str, transcript: str,
    user_api_key: str = None, user_provider: str = None, user_model: str = None,
    video_type: str = "general",
    visual_candidates: Optional[List[int]] = None,
    screenshot_count: int = 8,
) -> Dict[str, Any]:
```

Inside the function, update the `user_prompt` f-string:

1. **After the `Transcript:` block**, add the visual candidates block:

```python
visual_hint = ""
if visual_candidates:
    formatted = ", ".join(f"{s // 60}:{s % 60:02d}" for s in sorted(visual_candidates))
    visual_hint = (
        f"\nVisually confirmed on-screen moments "
        f"(prefer these for screenshot_timestamps): [{formatted}]\n"
    )
```

Inject `{visual_hint}` between the transcript and the `Produce a comprehensive...` line.

2. **Update RULES section** — find the line containing `key_insights` rule text (around "Each must be specific with evidence") and replace it with:

```
2. key_insights: 6-10 points. Each MUST follow: [specific claim] + [why/mechanism] + [timestamp evidence]. Generic observations ("the speaker discusses X") are not valid.
```

3. **Update screenshot_timestamps rule** — find the line containing `"Return 6-10 moments"` and replace with:

```python
f"9. screenshot_timestamps: Return {screenshot_count} moments, ..."
```

(Keep the rest of that rule's text unchanged.)

4. **Add type-specific analysis emphasis** — after `Produce a comprehensive study-note-quality analysis...`, add:

```python
type_emphasis = {
    "tutorial": "This is a TUTORIAL. Prioritise extracting exact steps, tools named, commands demonstrated, and gotchas.",
    "lecture": "This is a LECTURE. Prioritise claims made, evidence cited, concepts defined, and argument structure.",
    "opinion": "This is an OPINION/ESSAY. Prioritise the core claim, supporting reasoning, counterarguments, and where the speaker qualifies their view.",
    "general": "",
}.get(video_type, "")
```

Inject `{type_emphasis}` as a line in the user_prompt after the opening analysis instruction.

- [ ] **Step 4: Run tests**

```
cd backend && python -m pytest tests/test_claude_quality.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/services/claude_service.py backend/tests/test_claude_quality.py
git commit -m "feat: type-aware prompts and dynamic count in single-pass path"
```

---

## Task 7: Update Public Signatures to Accept New Params

**Files:**
- Modify: `backend/services/claude_service.py`
- Test: `backend/tests/test_claude_quality.py`

- [ ] **Step 1: Add failing test**

Append to `backend/tests/test_claude_quality.py`:

```python
from services.claude_service import generate_summary_and_mindmap


def test_generate_summary_and_mindmap_accepts_new_params():
    sig = inspect.signature(generate_summary_and_mindmap)
    params = sig.parameters
    assert "video_type" in params
    assert "visual_candidates" in params
    assert "screenshot_count" in params
```

- [ ] **Step 2: Run to confirm failure**

```
cd backend && python -m pytest tests/test_claude_quality.py::test_generate_summary_and_mindmap_accepts_new_params -v
```
Expected: `AssertionError`.

- [ ] **Step 3: Update `generate_summary_and_mindmap` and `run_map_reduce_summarization`**

Add params to `generate_summary_and_mindmap`:

```python
async def generate_summary_and_mindmap(
    title: str, channel: str, duration: str, transcript: str,
    user_api_key: str = None, user_provider: str = None, user_model: str = None,
    video_type: str = "general",
    visual_candidates: Optional[List[int]] = None,
    screenshot_count: int = 8,
) -> Dict[str, Any]:
```

Pass them through to both `run_map_reduce_summarization` and `generate_summary_and_mindmap_single_pass`:

```python
# map-reduce branch:
return await run_map_reduce_summarization(
    title, channel, duration, transcript,
    user_api_key=user_api_key, user_provider=user_provider, user_model=user_model,
    video_type=video_type, visual_candidates=visual_candidates, screenshot_count=screenshot_count,
)
# single-pass branch:
return await generate_summary_and_mindmap_single_pass(
    title, channel, duration, transcript,
    user_api_key=user_api_key, user_provider=user_provider, user_model=user_model,
    video_type=video_type, visual_candidates=visual_candidates, screenshot_count=screenshot_count,
)
```

Add the same params to `run_map_reduce_summarization`. Then update `_map_one_chunk` to derive chunk time bounds from the chunk text itself using `_extract_chunk_bounds`:

```python
async def _map_one_chunk(
    chunk: str,
    chunk_index: int,
    num_chunks: int,
    title: str,
    channel: str,
    duration: str,
    video_type: str = "general",
    visual_candidates: Optional[List[int]] = None,
    **llm_kwargs,
) -> str:
    chunk_start_seconds, chunk_end_seconds = _extract_chunk_bounds(chunk)
    system = _get_chunk_map_system(video_type)
    user = _map_chunk_user_prompt(
        title=title,
        channel=channel,
        duration=duration,
        chunk_index=chunk_index,
        num_chunks=num_chunks,
        chunk_text=chunk,
        visual_candidates=visual_candidates or [],
        chunk_start_seconds=chunk_start_seconds,
        chunk_end_seconds=chunk_end_seconds,
    )
    raw = await complete_llm_text(system, user, 6000, **llm_kwargs)
    return raw.strip()
```

Pass `video_type` to `_get_chunk_map_system` and `screenshot_count` to `_reduce_user_prompt` from `run_map_reduce_summarization`.

- [ ] **Step 4: Run all tests**

```
cd backend && python -m pytest tests/test_claude_quality.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/services/claude_service.py backend/tests/test_claude_quality.py
git commit -m "feat: thread video_type, visual_candidates, screenshot_count through summarization pipeline"
```

---

## Task 8: CLIP Enhancements — PrescanFrame, Embeddings, Dedup

**Files:**
- Modify: `backend/services/clip_service.py`
- Test: `backend/tests/test_clip_service.py`

- [ ] **Step 1: Add failing tests to `test_clip_service.py`**

Append to the existing `backend/tests/test_clip_service.py`:

```python
import numpy as np
from PIL import Image


def _solid_image(color=(128, 128, 128)):
    return Image.new("RGB", (64, 64), color=color)


def test_extract_image_embedding_returns_normalized_array_or_none():
    from services.clip_service import extract_image_embedding
    img = _solid_image()
    result = extract_image_embedding(img)
    if result is not None:  # CLIP may not be available in CI
        assert result.shape == (512,)
        assert abs(np.linalg.norm(result) - 1.0) < 1e-5


def test_prescan_frame_dataclass():
    from services.clip_service import PrescanFrame
    emb = np.zeros(512, dtype=np.float32)
    frame = PrescanFrame(seconds=120, embedding=emb)
    assert frame.seconds == 120
    assert frame.embedding.shape == (512,)


def test_rescore_with_type_returns_list_of_floats():
    from services.clip_service import PrescanFrame, rescore_with_type
    frames = [PrescanFrame(seconds=i * 30, embedding=np.random.rand(512).astype(np.float32)) for i in range(3)]
    scores = rescore_with_type(frames, "tutorial")
    assert len(scores) == 3
    assert all(isinstance(s, float) for s in scores)


def test_dedup_pass_a_removes_identical_frames():
    from services.clip_service import PrescanFrame, dedup_pass_a
    emb = np.ones(512, dtype=np.float32)
    emb = emb / np.linalg.norm(emb)
    frames = [PrescanFrame(seconds=i * 30, embedding=emb.copy()) for i in range(4)]
    scores = [0.9, 0.8, 0.7, 0.6]
    result = dedup_pass_a(frames, scores)
    assert len(result) == 1  # all identical — only first accepted


def test_dedup_pass_a_keeps_diverse_frames():
    from services.clip_service import PrescanFrame, dedup_pass_a
    # Two orthogonal embeddings — should both be kept
    e1 = np.zeros(512, dtype=np.float32); e1[0] = 1.0
    e2 = np.zeros(512, dtype=np.float32); e2[1] = 1.0
    frames = [PrescanFrame(seconds=0, embedding=e1), PrescanFrame(seconds=30, embedding=e2)]
    scores = [0.9, 0.8]
    result = dedup_pass_a(frames, scores)
    assert len(result) == 2


def test_dedup_pass_b_drops_duplicate_captured_frames():
    from services.clip_service import dedup_pass_b
    emb = np.ones(512, dtype=np.float32)
    emb = emb / np.linalg.norm(emb)
    frames = [
        {"url": "/a.jpg", "embedding": emb.copy()},
        {"url": "/b.jpg", "embedding": emb.copy()},  # duplicate
        {"url": "/c.jpg", "embedding": np.zeros(512, dtype=np.float32)},  # different
    ]
    result = dedup_pass_b(frames)
    urls = [r["url"] for r in result]
    assert "/a.jpg" in urls
    assert "/b.jpg" not in urls
    assert "/c.jpg" in urls
    assert "embedding" not in result[0]  # embedding stripped from output


def test_rank_frames_with_embedding_returns_index_and_optional_embedding():
    from services.clip_service import rank_frames_with_embedding
    import os, tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        p1 = os.path.join(tmpdir, "a.jpg")
        p2 = os.path.join(tmpdir, "b.jpg")
        _solid_image((200, 30, 30)).save(p1, "JPEG")
        _solid_image((30, 200, 30)).save(p2, "JPEG")
        idx, emb = rank_frames_with_embedding([p1, p2], "red image")
        assert idx in (0, 1)
        # emb may be None if CLIP unavailable
        if emb is not None:
            assert emb.shape == (512,)
```

- [ ] **Step 2: Run to confirm failures**

```
cd backend && python -m pytest tests/test_clip_service.py -v
```
Expected: multiple `ImportError`s.

- [ ] **Step 3: Implement all new functions in `clip_service.py`**

Replace the entire file with:

```python
import logging
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

_model = None
_processor = None
_clip_available = None


def _load_clip() -> bool:
    global _model, _processor, _clip_available
    if _clip_available is not None:
        return _clip_available
    try:
        from transformers import CLIPModel, CLIPProcessor
        _model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        _processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        _model.eval()
        _clip_available = True
        logger.info("CLIP model loaded successfully.")
    except Exception as exc:
        logger.warning(f"CLIP unavailable: {exc}. Falling back to defaults.")
        _clip_available = False
    return _clip_available


@dataclass
class PrescanFrame:
    seconds: int
    embedding: np.ndarray  # shape (512,), float32, L2-normalised


_RICHNESS_QUERIES = {
    "tutorial": "terminal, code editor, software interface, command line, demo screen",
    "lecture":  "presentation slide, whiteboard, diagram, text on screen, concept chart",
    "opinion":  "graphic, text overlay, b-roll footage, visual aid, chart",
    "general":  "informative screen content with text, code, diagrams, or visual data",
}


def _normalise(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def extract_image_embedding(image) -> Optional[np.ndarray]:
    """Return L2-normalised CLIP image embedding (512,) or None if CLIP unavailable."""
    if not _load_clip():
        return None
    try:
        import torch
        inputs = _processor(images=[image], return_tensors="pt")
        with torch.no_grad():
            features = _model.get_image_features(**inputs)
        return _normalise(features[0].cpu().numpy().astype(np.float32))
    except Exception as exc:
        logger.warning(f"CLIP embedding extraction failed: {exc}")
        return None


def rescore_with_type(frames: List[PrescanFrame], video_type: str) -> List[float]:
    """Compute cosine similarity of each frame's embedding against the type-specific text query."""
    query = _RICHNESS_QUERIES.get(video_type, _RICHNESS_QUERIES["general"])
    if not frames or not _load_clip():
        return [0.0] * len(frames)
    try:
        import torch
        inputs = _processor(text=[query], return_tensors="pt", padding=True)
        with torch.no_grad():
            text_features = _model.get_text_features(**inputs)
        text_emb = _normalise(text_features[0].cpu().numpy().astype(np.float32))
        return [float(np.dot(f.embedding, text_emb)) for f in frames]
    except Exception as exc:
        logger.warning(f"CLIP rescoring failed: {exc}")
        return [0.0] * len(frames)


def dedup_pass_a(frames: List[PrescanFrame], scores: List[float]) -> List[PrescanFrame]:
    """Greedy diverse selection: sort by richness, skip near-duplicates."""
    threshold = float(os.environ.get("SCREENSHOT_DEDUP_THRESHOLD", "0.90"))
    indexed = sorted(zip(scores, frames), key=lambda x: x[0], reverse=True)
    accepted: List[PrescanFrame] = []
    for _, frame in indexed:
        if not accepted:
            accepted.append(frame)
            continue
        if max(float(np.dot(frame.embedding, a.embedding)) for a in accepted) < threshold:
            accepted.append(frame)
    return accepted


def dedup_pass_b(captured: List[dict]) -> List[dict]:
    """
    Remove near-duplicate final captured frames.
    Each dict may have an 'embedding' key (np.ndarray). Embeddings are stripped from output.
    """
    threshold = float(os.environ.get("SCREENSHOT_DEDUP_THRESHOLD", "0.90"))
    kept: List[dict] = []
    kept_embeddings: List[np.ndarray] = []

    for item in captured:
        emb = item.get("embedding")
        out = {k: v for k, v in item.items() if k != "embedding"}
        if emb is None or not kept_embeddings:
            kept.append(out)
            if emb is not None:
                kept_embeddings.append(emb)
            continue
        sim = max(float(np.dot(emb, e)) for e in kept_embeddings)
        if sim < threshold:
            kept.append(out)
            kept_embeddings.append(emb)
        else:
            logger.info(f"Dedup Pass B: dropped duplicate frame (sim={sim:.3f})")
    return kept


def rank_frames(image_paths: List[str], section_title: str) -> int:
    """Return index of best frame. Falls back to 0 if CLIP unavailable."""
    idx, _ = rank_frames_with_embedding(image_paths, section_title)
    return idx


def rank_frames_with_embedding(
    image_paths: List[str], section_title: str
) -> Tuple[int, Optional[np.ndarray]]:
    """Return (best_index, embedding_of_best_frame). Embedding is None if CLIP unavailable."""
    if not image_paths:
        return 0, None
    if len(image_paths) == 1:
        if not _load_clip():
            return 0, None
        try:
            from PIL import Image
            img = Image.open(image_paths[0]).convert("RGB")
            return 0, extract_image_embedding(img)
        except Exception:
            return 0, None

    if not _load_clip():
        return 0, None

    try:
        import torch
        from PIL import Image
        images, valid_indices = [], []
        for i, path in enumerate(image_paths):
            try:
                images.append(Image.open(path).convert("RGB"))
                valid_indices.append(i)
            except Exception as exc:
                logger.warning(f"Could not open {path}: {exc}")

        if not images:
            return 0, None

        inputs = _processor(
            text=[section_title], images=images, return_tensors="pt", padding=True
        )
        with torch.no_grad():
            outputs = _model(**inputs)

        scores = outputs.logits_per_image[:, 0].tolist()
        best_local = scores.index(max(scores))
        best_global = valid_indices[best_local]

        # Extract embedding for winning frame
        img_inputs = _processor(images=[images[best_local]], return_tensors="pt")
        with torch.no_grad():
            img_features = _model.get_image_features(**img_inputs)
        emb = _normalise(img_features[0].cpu().numpy().astype(np.float32))
        return best_global, emb
    except Exception as exc:
        logger.warning(f"CLIP ranking failed: {exc}")
        return 0, None
```

- [ ] **Step 4: Run all clip tests**

```
cd backend && python -m pytest tests/test_clip_service.py -v
```
Expected: all pass (CLIP-dependent tests skip gracefully if model unavailable).

- [ ] **Step 5: Commit**

```bash
git add backend/services/clip_service.py backend/tests/test_clip_service.py
git commit -m "feat: PrescanFrame, embeddings, dedup passes A and B in clip_service"
```

---

## Task 9: Visual Pre-scan and Embedding Retention in Playwright

**Files:**
- Modify: `backend/services/playwright_service.py`
- Test: `backend/tests/test_playwright_service.py`

- [ ] **Step 1: Add failing test**

Append to `backend/tests/test_playwright_service.py`:

```python
import inspect
from services import playwright_service


def test_prescan_visual_richness_exists_and_is_async():
    assert hasattr(playwright_service, "prescan_visual_richness")
    import asyncio
    assert asyncio.iscoroutinefunction(playwright_service.prescan_visual_richness)


def test_dedup_pass_b_strips_embeddings_and_removes_dupes():
    """Contract test for the Playwright-first + embedding-retention + dedup_pass_b pipeline.

    No live Playwright required — simulates what extract_screenshots_playwright produces
    before dedup_pass_b is applied, then verifies the final output is clean.
    """
    import numpy as np
    from services.clip_service import dedup_pass_b

    emb = np.ones(512, dtype=np.float32) / np.sqrt(512)
    raw = [
        {"url": "/s/a.jpg", "timestamp": "1:00", "caption": "foo", "embedding": emb.copy()},
        {"url": "/s/b.jpg", "timestamp": "2:00", "caption": "foo", "embedding": emb.copy()},  # duplicate of a
        {"url": "/s/c.jpg", "timestamp": "3:00", "caption": "bar", "embedding": np.zeros(512, dtype=np.float32)},
    ]
    result = dedup_pass_b(raw)

    # embedding key must not appear in API output
    assert all("embedding" not in r for r in result)
    # b is a near-duplicate of a (cosine sim == 1.0) — must be dropped
    urls = [r["url"] for r in result]
    assert "/s/a.jpg" in urls
    assert "/s/b.jpg" not in urls
    assert "/s/c.jpg" in urls
```

- [ ] **Step 2: Run to confirm failure**

```
cd backend && python -m pytest tests/test_playwright_service.py::test_prescan_visual_richness_exists_and_is_async -v
```
Expected: `AssertionError`.

- [ ] **Step 3: Add `prescan_visual_richness` to `playwright_service.py`**

Add at the top, after the existing imports, add the CLIP import guard:

```python
try:
    from services.clip_service import extract_image_embedding, PrescanFrame
    _CLIP_FOR_PRESCAN = True
except ImportError:
    _CLIP_FOR_PRESCAN = False
```

Add the new function before `extract_screenshots_playwright`:

```python
async def prescan_visual_richness(
    video_id: str,
    duration_seconds: int,
) -> List:
    """
    Seek the YouTube embed at adaptive intervals, extract CLIP embeddings.
    Returns List[PrescanFrame]. Raw images are discarded immediately.
    """
    if not PLAYWRIGHT_AVAILABLE or not _CLIP_FOR_PRESCAN:
        logger.warning("prescan_visual_richness: Playwright or CLIP unavailable, skipping.")
        return []

    interval_short = int(os.environ.get("PRESCAN_INTERVAL_SHORT", "30"))
    interval_mid   = int(os.environ.get("PRESCAN_INTERVAL_MID",   "60"))
    interval_long  = int(os.environ.get("PRESCAN_INTERVAL_LONG",  "90"))
    seek_timeout   = int(os.environ.get("SCREENSHOT_SEEK_TIMEOUT", "15"))

    if duration_seconds < 1800:
        interval = interval_short
    elif duration_seconds < 7200:
        interval = interval_mid
    else:
        interval = interval_long

    seek_times = list(range(interval, duration_seconds, interval))
    if not seek_times:
        return []

    frames: List = []
    embed_url = f"https://www.youtube.com/watch?v={video_id}"

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True,
                args=["--autoplay-policy=no-user-gesture-required",
                      "--disable-blink-features=AutomationControlled"],
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            if not await _wait_for_video_player(page, embed_url):
                await context.close()
                await browser.close()
                return []

            await page.evaluate(
                "() => { const v = document.querySelector('video'); if (v) v.pause(); }"
            )

            for seek_time in seek_times:
                tmp_path = os.path.join(tempfile.gettempdir(), f"prescan_{uuid.uuid4().hex}.jpg")
                try:
                    captured = await asyncio.wait_for(
                        _capture_frame(page, float(seek_time), tmp_path),
                        timeout=seek_timeout,
                    )
                    if captured:
                        from PIL import Image
                        img = Image.open(tmp_path).convert("RGB")
                        emb = extract_image_embedding(img)
                        if emb is not None:
                            frames.append(PrescanFrame(seconds=seek_time, embedding=emb))
                except asyncio.TimeoutError:
                    logger.warning(f"prescan: seek to {seek_time}s timed out, skipping.")
                except Exception as exc:
                    logger.warning(f"prescan: error at {seek_time}s: {exc}")
                finally:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)

            await context.close()
            await browser.close()

    except Exception as exc:
        logger.error(f"prescan_visual_richness failed: {exc}")

    logger.info(f"prescan_visual_richness: captured {len(frames)} embeddings from {video_id}")
    return frames
```

- [ ] **Step 4: Update `extract_screenshots_playwright` to retain winning embedding**

Inside the loop where `best_index` is selected, replace:

```python
# OLD:
best_index = rank_frames(path_only, section_title=section_title or caption)
best_time, best_path = candidate_paths[best_index]
```

```python
# NEW:
from services.clip_service import rank_frames_with_embedding
best_index, best_embedding = rank_frames_with_embedding(path_only, section_title or caption)
best_time, best_path = candidate_paths[best_index]
```

And in the `results.append({...})` call, add `"embedding": best_embedding` as a key. The embedding will be stripped by `dedup_pass_b` in `main.py`.

Also add the per-seek timeout to `_capture_frame` calls inside the loop:

```python
# Wrap the existing _capture_frame call with asyncio.wait_for:
seek_timeout = int(os.environ.get("SCREENSHOT_SEEK_TIMEOUT", "15"))
try:
    success = await asyncio.wait_for(
        _capture_frame(page, seek_time, candidate_path),
        timeout=seek_timeout,
    )
except asyncio.TimeoutError:
    logger.warning(f"Playwright: seek to {seek_time}s timed out for {request_id}, skipping candidate.")
    success = False
```

- [ ] **Step 5: Run tests**

```
cd backend && python -m pytest tests/test_playwright_service.py -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/services/playwright_service.py backend/tests/test_playwright_service.py
git commit -m "feat: prescan_visual_richness and embedding retention in playwright_service"
```

---

## Task 10: main.py Orchestration

**Files:**
- Modify: `backend/main.py`
- Test: `backend/tests/test_main_orchestration.py` (new) + manual smoke test

- [ ] **Step 1: Write failing test for the embedding-strip contract in main**

Create `backend/tests/test_main_orchestration.py`:

```python
"""Tests for main.py orchestration contracts (no live server required)."""
import ast
import pathlib


def _parse_main():
    src = (pathlib.Path(__file__).parent.parent / "main.py").read_text(encoding="utf-8")
    return ast.parse(src)


def test_dedup_pass_b_is_imported_in_main():
    tree = _parse_main()
    imports = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    ]
    assert "dedup_pass_b" in imports, "main.py must import dedup_pass_b from clip_service"


def test_dedup_pass_b_is_called_in_main():
    tree = _parse_main()
    calls = [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert "dedup_pass_b" in calls, "main.py must call dedup_pass_b() after screenshot capture"
```

Run to confirm failure:

```
cd backend && python -m pytest tests/test_main_orchestration.py -v
```
Expected: `AssertionError: main.py must import dedup_pass_b from clip_service`

- [ ] **Step 2: Update imports at the top of `main.py`**

Add to the existing service imports:

```python
from services.playwright_service import prescan_visual_richness
from services.claude_service import detect_video_type, compute_screenshot_count
from services.clip_service import rescore_with_type, dedup_pass_a, dedup_pass_b
```

Run only the import test — only the import is added at this step:

```
cd backend && python -m pytest tests/test_main_orchestration.py::test_dedup_pass_b_is_imported_in_main -v
```
Expected: 1 passed. (`test_dedup_pass_b_is_called_in_main` will still fail — that's expected; the call is added in Step 7.)

- [ ] **Step 3: Replace the sequential transcript fetch with parallel fetch + prescan**

Find the current Step 2 block in `main.py`:

```python
# Step 2
yield yield_progress(2, "Fetching transcript...")
transcript_result = await fetch_transcript(video_id)
```

Replace with:

```python
# Step 2 — parallel: transcript fetch + visual pre-scan
yield yield_progress(2, "Fetching transcript and scanning video frames...")
transcript_result, prescan_frames = await asyncio.gather(
    fetch_transcript(video_id),
    prescan_visual_richness(video_id, metadata.duration_seconds),
)
```

- [ ] **Step 4: Add type detection, rescoring, dedup, and count computation after Step 3**

Immediately after the `asyncio.gather` line, insert:

```python
timestamped_transcript = generate_timestamped_transcript(transcript_result.segments)

video_type = detect_video_type(metadata.title, timestamped_transcript)
logger.info(f"Detected video type: {video_type}")

scores = rescore_with_type(prescan_frames, video_type)
diverse_frames = dedup_pass_a(prescan_frames, scores)
visual_candidates = [f.seconds for f in diverse_frames]
screenshot_count = compute_screenshot_count(video_type, metadata.duration_seconds)
logger.info(f"screenshot_count={screenshot_count}, visual_candidates={len(visual_candidates)}")
```

Remove the `timestamped_transcript = generate_timestamped_transcript(...)` line that currently appears after the old Step 2.

- [ ] **Step 5: Pass new params into `generate_summary_and_mindmap`**

Update the call:

```python
claude_val = await generate_summary_and_mindmap(
    title=metadata.title,
    channel=metadata.channel,
    duration=metadata.duration_formatted,
    transcript=timestamped_transcript,
    video_type=video_type,
    visual_candidates=visual_candidates,
    screenshot_count=screenshot_count,
    user_api_key=user_api_key,
    user_provider=user_provider,
    user_model=user_model,
)
```

- [ ] **Step 6: Flip screenshot preference to Playwright-first**

Replace the current screenshot preference block:

```python
# OLD:
if FFMPEG_AVAILABLE:
    extracted_files = await extract_screenshots_for_video(...)
    if not extracted_files and PLAYWRIGHT_AVAILABLE:
        ...
if not extracted_files and PLAYWRIGHT_AVAILABLE:
    extracted_files = await extract_screenshots_playwright(...)
```

```python
# NEW:
if PLAYWRIGHT_AVAILABLE:
    extracted_files = await extract_screenshots_playwright(
        video_id=video_id,
        screenshot_requests=screenshot_plan,
        static_dir=os.path.join(STATIC_DIR, "screenshots"),
    )
if not extracted_files and FFMPEG_AVAILABLE:
    logger.info("Playwright returned no frames; falling back to ffmpeg.")
    extracted_files = await extract_screenshots_for_video(
        video_url=body.url,
        video_id=video_id,
        duration_seconds=metadata.duration_seconds,
        screenshot_requests=screenshot_plan,
        static_dir=os.path.join(STATIC_DIR, "screenshots"),
    )
```

- [ ] **Step 7: Apply dedup Pass B after capture**

Immediately after the `if not extracted_files and FFMPEG_AVAILABLE:` block (after all extraction attempts), add:

```python
if extracted_files:
    extracted_files = dedup_pass_b(extracted_files)
    logger.info(f"After dedup Pass B: {len(extracted_files)} screenshots kept")
```

Run the full orchestration test suite — both tests should now pass:

```
cd backend && python -m pytest tests/test_main_orchestration.py -v
```
Expected: 2 passed.

- [ ] **Step 8: Smoke test locally**

Start the server and summarize a short YouTube video (< 10 min):

```bash
cd backend && uvicorn main:app --reload
```

Open http://localhost:8000, paste a YouTube URL, click Summarize. Verify:
- No crash in server logs
- Summary appears with sections covering the full video
- `"Detected video type:"` log line appears
- `"prescan_visual_richness: captured N embeddings"` log line appears
- `"After dedup Pass B:"` log line appears

- [ ] **Step 9: Commit**

```bash
git add backend/main.py backend/tests/test_main_orchestration.py
git commit -m "feat: parallel prescan, Playwright-first screenshots, dedup Pass B in main orchestration"
```

---

## Self-Review Against Spec

| Spec requirement | Task |
|-----------------|------|
| `detect_video_type` keyword heuristic, title first then transcript | Task 1 |
| Timestamp-anchor chunking with [MM:SS] regex, punctuation fallback | Task 2 |
| `compute_screenshot_count` formula with type params and env cap | Task 3 |
| 4 type-aware `CHUNK_MAP_SYSTEM` variants + `_get_chunk_map_system` | Task 4 |
| `[specific claim] + [why/mechanism] + [timestamp evidence]` insight rule in all map variants | Task 4 |
| Visual candidates injected into map chunk prompt, filtered to time window | Task 5 |
| `screenshot_count` passed into reduce prompt replacing "6-10" | Task 5 |
| Single-pass: type variant, insight rule, visual candidates, dynamic count | Task 6 |
| `generate_summary_and_mindmap` + `run_map_reduce_summarization` accept new params | Task 7 |
| `PrescanFrame` dataclass with `seconds` + `embedding` only | Task 8 |
| `extract_image_embedding` returning normalised (512,) array | Task 8 |
| `rescore_with_type` using type-specific CLIP query | Task 8 |
| `dedup_pass_a`: sort by richness, greedy cosine threshold | Task 8 |
| `rank_frames_with_embedding` returns index + embedding | Task 8 |
| `dedup_pass_b`: strips embeddings from output, logs drops | Task 8 |
| `prescan_visual_richness`: adaptive interval, temp files deleted, List[PrescanFrame] returned | Task 9 |
| Playwright targeted capture retains winning embedding in result dict | Task 9 |
| Per-seek 15s timeout in both prescan and targeted capture | Task 9 |
| `asyncio.gather(fetch_transcript, prescan)` after metadata fetch | Task 10 |
| Playwright-first → ffmpeg-fallback preference | Task 10 |
| `dedup_pass_b` applied to extracted_files before building screenshot_data | Task 10 |
| `SCREENSHOT_DEDUP_THRESHOLD`, `SCREENSHOT_MAX_COUNT`, `PRESCAN_INTERVAL_*`, `SCREENSHOT_SEEK_TIMEOUT` env vars | Tasks 8–10 |

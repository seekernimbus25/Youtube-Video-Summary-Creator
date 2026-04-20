# Playwright + CLIP Screenshot Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current ffmpeg-based screenshot pipeline with a three-layer approach: YouTube chapter/transcript-anchored timing (Options 3 & 4), Playwright browser-based capture (Option 8), and CLIP semantic frame ranking (Option 7).

**Architecture:** The pipeline splits into two independent concerns — TIMING (what second to capture) and CAPTURE (how to get a clean frame at that second). Timing is solved by preferring YouTube chapters from yt-dlp, falling back to transcript segment boundaries. Capture is handled by Playwright seeking within the YouTube embed player, which eliminates video download and ffmpeg seek drift entirely. CLIP then ranks 3 candidate screenshots per section to pick the one that best matches the section's semantic meaning.

**Tech Stack:** `playwright` (Chromium automation), `transformers` + `torch` (CLIP model, CPU-only), `Pillow` (image loading for CLIP), existing `yt-dlp` (chapter extraction), existing `youtube-transcript-api` (segment timestamps).

---

## File Map

**New files:**
- `backend/services/playwright_service.py` — Playwright browser session, seek, screenshot, CLIP ranking per section
- `backend/services/clip_service.py` — CLIP model load + `rank_frames(image_paths, text) -> int`
- `backend/tests/test_clip_service.py`
- `backend/tests/test_playwright_service.py`
- `backend/tests/test_build_screenshot_plan.py`

**Modified files:**
- `backend/models.py` — Add `Chapter`, `TranscriptSegment`, `TranscriptResult`; add `chapters` field to `Metadata`
- `backend/services/video_service.py` — Extract `chapters` from yt-dlp info dict
- `backend/services/transcript_service.py` — Return `TranscriptResult` (text + segments) instead of plain string
- `backend/main.py` — Update `_build_screenshot_plan()` to use chapters/segments; swap Playwright in; update health check
- `backend/requirements.txt` — Add `playwright`, `transformers`, `torch`, `pillow`

**Unchanged (kept as dead fallback):**
- `backend/services/screenshot_service.py` — No changes; Playwright service is a drop-in replacement; old service stays for potential future fallback use.

---

## Task 1: Extend Data Models

**Files:**
- Modify: `backend/models.py`
- Test: `backend/tests/test_build_screenshot_plan.py` (models used in later tasks)

- [ ] **Step 1: Add Chapter, TranscriptSegment, TranscriptResult to models.py**

Open `backend/models.py`. After the existing imports, add these three classes before `SummarizeRequest`:

```python
class Chapter(BaseModel):
    title: str
    start_time: float
    end_time: float

class TranscriptSegment(BaseModel):
    text: str
    start: float
    duration: float

class TranscriptResult(BaseModel):
    text: str
    segments: List[TranscriptSegment]
```

- [ ] **Step 2: Add `chapters` field to `Metadata`**

Change the `Metadata` class to:

```python
class Metadata(BaseModel):
    title: str
    channel: str
    duration_seconds: int
    duration_formatted: str
    thumbnail_url: str
    chapters: List[Chapter] = Field(default_factory=list)
```

- [ ] **Step 3: Verify models import cleanly**

```bash
cd backend && python -c "from models import Chapter, TranscriptSegment, TranscriptResult, Metadata; print('OK')"
```

Expected output: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/models.py
git commit -m "feat: add Chapter, TranscriptSegment, TranscriptResult models"
```

---

## Task 2: Chapter Extraction from yt-dlp (Option 3)

**Files:**
- Modify: `backend/services/video_service.py:12-36`
- Test: `backend/tests/test_build_screenshot_plan.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_build_screenshot_plan.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from models import Metadata, Chapter


def _make_ydl_info(chapters=None):
    return {
        'title': 'Test Video',
        'uploader': 'Test Channel',
        'duration': 300,
        'thumbnail': 'https://example.com/thumb.jpg',
        'chapters': chapters or [],
    }


def test_metadata_includes_chapters_when_present():
    chapters_raw = [
        {'title': 'Intro', 'start_time': 0.0, 'end_time': 60.0},
        {'title': 'Deep Dive', 'start_time': 60.0, 'end_time': 240.0},
        {'title': 'Conclusion', 'start_time': 240.0, 'end_time': 300.0},
    ]
    info = _make_ydl_info(chapters=chapters_raw)

    with patch('yt_dlp.YoutubeDL') as mock_ydl_cls:
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = info
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl

        from services.video_service import _fetch_video_metadata_sync
        result = _fetch_video_metadata_sync('https://youtube.com/watch?v=test')

    assert len(result.chapters) == 3
    assert result.chapters[0].title == 'Intro'
    assert result.chapters[0].start_time == 0.0
    assert result.chapters[1].title == 'Deep Dive'
    assert result.chapters[1].start_time == 60.0


def test_metadata_has_empty_chapters_when_none():
    info = _make_ydl_info(chapters=None)

    with patch('yt_dlp.YoutubeDL') as mock_ydl_cls:
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = info
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl

        from services.video_service import _fetch_video_metadata_sync
        result = _fetch_video_metadata_sync('https://youtube.com/watch?v=test')

    assert result.chapters == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_build_screenshot_plan.py::test_metadata_includes_chapters_when_present -v
```

Expected: FAIL — `Metadata` has no `chapters` attribute yet (Task 1 must be done first, or TypeError on attribute access).

- [ ] **Step 3: Update `_fetch_video_metadata_sync` in `video_service.py`**

Replace the existing function body (lines 12–36) with:

```python
def _fetch_video_metadata_sync(video_url: str) -> Metadata:
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'proxy': '',
    }

    with without_proxy_env():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Extracting metadata for {video_url}")
            info = ydl.extract_info(video_url, download=False)

            duration_s = info.get('duration', 0)
            mins = duration_s // 60
            secs = duration_s % 60
            duration_formatted = f"{mins}:{secs:02d}"

            chapters_raw = info.get('chapters') or []
            chapters = [
                Chapter(
                    title=ch.get('title', f'Chapter {i + 1}'),
                    start_time=float(ch.get('start_time', 0)),
                    end_time=float(ch.get('end_time', duration_s)),
                )
                for i, ch in enumerate(chapters_raw)
            ]

            return Metadata(
                title=info.get('title', 'Unknown Title'),
                channel=info.get('uploader', 'Unknown Channel'),
                duration_seconds=duration_s,
                duration_formatted=duration_formatted,
                thumbnail_url=info.get('thumbnail', ''),
                chapters=chapters,
            )
```

Add `Chapter` to the import at the top of `video_service.py`:

```python
from models import Metadata, Chapter
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_build_screenshot_plan.py -v
```

Expected: Both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/video_service.py backend/tests/test_build_screenshot_plan.py
git commit -m "feat: extract YouTube chapters from yt-dlp metadata"
```

---

## Task 3: Transcript Segments with Timestamps (Option 4)

**Files:**
- Modify: `backend/services/transcript_service.py`
- Modify: `backend/main.py:293` (call site for `fetch_transcript`)
- Test: `backend/tests/test_build_screenshot_plan.py` (add new tests)

- [ ] **Step 1: Write failing tests for transcript segments**

Add to `backend/tests/test_build_screenshot_plan.py`:

```python
def test_parse_json3_returns_segments_with_timestamps():
    import json
    from services.transcript_service import _parse_json3_with_segments

    raw = json.dumps({
        "events": [
            {"tStartMs": 0, "dDurationMs": 3000, "segs": [{"utf8": "Hello world"}]},
            {"tStartMs": 5000, "dDurationMs": 2000, "segs": [{"utf8": "Next sentence"}]},
            {"tStartMs": 8000, "dDurationMs": 1500, "segs": [{"utf8": "\n"}]},  # newline-only, should be skipped
        ]
    })

    result = _parse_json3_with_segments(raw)
    assert result.text == "Hello world Next sentence"
    assert len(result.segments) == 2
    assert result.segments[0].start == 0.0
    assert result.segments[0].duration == 3.0
    assert result.segments[0].text == "Hello world"
    assert result.segments[1].start == 5.0


def test_transcript_api_segments_preserved():
    from services.transcript_service import _segments_from_transcript_api_data

    raw_data = [
        {'text': 'First sentence.', 'start': 1.5, 'duration': 2.0},
        {'text': 'Second sentence.', 'start': 3.5, 'duration': 1.8},
    ]

    result = _segments_from_transcript_api_data(raw_data)
    assert result.text == "First sentence. Second sentence."
    assert len(result.segments) == 2
    assert result.segments[0].start == 1.5
    assert result.segments[1].start == 3.5
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_build_screenshot_plan.py::test_parse_json3_returns_segments_with_timestamps tests/test_build_screenshot_plan.py::test_transcript_api_segments_preserved -v
```

Expected: FAIL — functions don't exist yet.

- [ ] **Step 3: Add helper functions and update transcript_service.py**

Add these two new functions and update existing ones in `backend/services/transcript_service.py`. Add the import at the top:

```python
from models import TranscriptSegment, TranscriptResult
```

Add these two new helper functions (place after `_parse_srt`):

```python
def _segments_from_transcript_api_data(data: list) -> TranscriptResult:
    """Convert youtube-transcript-api list to TranscriptResult."""
    segments = [
        TranscriptSegment(
            text=item['text'].replace('\n', ' ').strip(),
            start=float(item['start']),
            duration=float(item.get('duration', 0)),
        )
        for item in data
        if item.get('text', '').replace('\n', '').strip()
    ]
    text = ' '.join(s.text for s in segments)
    return TranscriptResult(text=text, segments=segments)


def _parse_json3_with_segments(content: str) -> TranscriptResult:
    """Parse YouTube json3 subtitle format, preserving segment timestamps."""
    try:
        data = json.loads(content)
        segments = []
        for event in data.get('events', []):
            segs = event.get('segs', [])
            text_parts = [s.get('utf8', '').strip() for s in segs]
            combined = ' '.join(p for p in text_parts if p and p != '\n').strip()
            if not combined:
                continue
            start_ms = event.get('tStartMs', 0)
            duration_ms = event.get('dDurationMs', 0)
            segments.append(TranscriptSegment(
                text=combined,
                start=start_ms / 1000.0,
                duration=duration_ms / 1000.0,
            ))
        text = ' '.join(s.text for s in segments)
        return TranscriptResult(text=text, segments=segments)
    except json.JSONDecodeError:
        logger.warning("Failed to parse json3 with segments, returning raw content.")
        return TranscriptResult(text=content, segments=[])
```

- [ ] **Step 4: Update `_fetch_with_ytdlp` to return TranscriptResult**

In `transcript_service.py`, replace the final block inside the `try` of `_fetch_with_ytdlp` that calls `_parse_json3` / `_parse_vtt` / `_parse_srt`:

```python
        if sub_file.endswith('.json3'):
            return _parse_json3_with_segments(content)
        elif sub_file.endswith('.vtt'):
            # VTT doesn't carry reliable per-segment ms timestamps; return text only
            return TranscriptResult(text=_parse_vtt(content), segments=[])
        elif sub_file.endswith('.srt'):
            return TranscriptResult(text=_parse_srt(content), segments=[])
        else:
            return TranscriptResult(text=content, segments=[])
```

Also change the function signature and raise type:

```python
def _fetch_with_ytdlp(video_url: str, video_id: str) -> TranscriptResult:
```

- [ ] **Step 5: Update `_fetch_with_transcript_api` to return TranscriptResult**

Replace the two `return` statements inside `_fetch_with_transcript_api` that currently return joined strings:

```python
# In the "Direct fetch" block, replace:
#   return ' '.join([item['text'] for item in data]).replace('\n', ' ')
# With:
            if data:
                return _segments_from_transcript_api_data(list(data))

# In the "List fallback" block, replace:
#   return ' '.join([item['text'] for item in data]).replace('\n', ' ')
# With:
                    if data:
                        return _segments_from_transcript_api_data(list(data))
```

Change the function signature:

```python
def _fetch_with_transcript_api(video_id: str) -> TranscriptResult:
```

- [ ] **Step 6: Update `fetch_transcript` to return TranscriptResult**

Replace the body of `fetch_transcript` in `transcript_service.py`:

```python
async def fetch_transcript(video_id: str) -> TranscriptResult:
    """
    Primary: yt-dlp (handles auto-generated captions reliably)
    Fallback: youtube-transcript-api
    Returns TranscriptResult with both plain text and timed segments.
    """
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    loop = asyncio.get_running_loop()

    try:
        logger.info(f"Fetching transcript via yt-dlp for {video_id}")
        result = await loop.run_in_executor(executor, _fetch_with_ytdlp, video_url, video_id)
        if result and len(result.text.strip()) > 50:
            logger.info(f"Successfully fetched transcript via yt-dlp ({len(result.text)} chars, {len(result.segments)} segments)")
            return result
        else:
            logger.warning("yt-dlp returned very short or empty transcript, trying fallback.")
    except Exception as e:
        logger.warning(f"yt-dlp transcript fetch failed: {e}")

    try:
        logger.info(f"Falling back to youtube-transcript-api for {video_id}")
        result = await loop.run_in_executor(executor, _fetch_with_transcript_api, video_id)
        if result and len(result.text.strip()) > 50:
            logger.info(f"Successfully fetched transcript via youtube-transcript-api ({len(result.text)} chars, {len(result.segments)} segments)")
            return result
    except Exception as e:
        logger.warning(f"youtube-transcript-api also failed: {e}")

    raise RuntimeError("TRANSCRIPT_UNAVAILABLE: Could not fetch transcript using any method. The video may have no captions available.")
```

- [ ] **Step 7: Update main.py call site for fetch_transcript**

In `backend/main.py` at line 293, `fetch_transcript` now returns `TranscriptResult`. Update the call and downstream usage:

```python
# Step 2
yield yield_progress(2, "Fetching transcript...")
transcript_result = await fetch_transcript(video_id)

# Step 3
yield yield_progress(3, "Generating AI summary...")
claude_val = await generate_summary_and_mindmap(
    title=metadata.title,
    channel=metadata.channel,
    duration=metadata.duration_formatted,
    transcript=transcript_result.text      # <-- was: transcript_text
)
```

Also update `_build_screenshot_plan` call (Step 4 of this plan handles the signature — for now just pass empty list):

```python
screenshot_plan = _build_screenshot_plan(
    claude_val.get('summary', {}),
    metadata.duration_seconds,
    metadata.chapters,
    transcript_result.segments,
)
```

Update `_build_screenshot_plan` signature temporarily (full logic comes in Task 4):

```python
def _build_screenshot_plan(summary: dict, duration_seconds: int, chapters: list = None, transcript_segments: list = None) -> list[dict]:
```

- [ ] **Step 8: Run all transcript tests**

```bash
cd backend && python -m pytest tests/test_build_screenshot_plan.py -v
```

Expected: All 4 tests pass.

- [ ] **Step 9: Smoke-test the server starts without error**

```bash
cd backend && python -c "from services.transcript_service import fetch_transcript; from main import _build_screenshot_plan; print('imports OK')"
```

Expected: `imports OK`

- [ ] **Step 10: Commit**

```bash
git add backend/services/transcript_service.py backend/models.py backend/main.py backend/tests/test_build_screenshot_plan.py
git commit -m "feat: transcript service now returns timed segments alongside plain text"
```

---

## Task 4: Upgrade Screenshot Plan to Use Chapters and Transcript Segments

**Files:**
- Modify: `backend/main.py:46-150` (`_build_screenshot_plan`)
- Test: `backend/tests/test_build_screenshot_plan.py` (add new tests)

This task upgrades the timing logic. Priority order: **chapters first → transcript segments → Claude's guessed seconds**.

- [ ] **Step 1: Write failing tests for chapter-anchored timing**

Add to `backend/tests/test_build_screenshot_plan.py`:

```python
def _make_summary_with_sections():
    return {
        "key_sections": [
            {"title": "Introduction", "timestamp": "0:00", "timestamp_seconds": 0, "description": "Overview of the topic"},
            {"title": "Deep Dive", "timestamp": "1:00", "timestamp_seconds": 60, "description": "Technical details explained"},
            {"title": "Conclusion", "timestamp": "4:00", "timestamp_seconds": 240, "description": "Summary and takeaways"},
        ],
        "screenshot_timestamps": [
            {"seconds": 5, "caption": "Intro frame", "section_title": "Introduction"},
            {"seconds": 65, "caption": "Deep dive frame", "section_title": "Deep Dive"},
        ],
        "keywords": ["AI", "technology"],
    }


def test_chapters_anchor_screenshot_timestamps():
    from main import _build_screenshot_plan
    from models import Chapter

    chapters = [
        Chapter(title="Introduction", start_time=0.0, end_time=58.0),
        Chapter(title="Deep Dive", start_time=58.0, end_time=238.0),
        Chapter(title="Conclusion", start_time=238.0, end_time=300.0),
    ]

    plan = _build_screenshot_plan(
        _make_summary_with_sections(),
        duration_seconds=300,
        chapters=chapters,
        transcript_segments=[],
    )

    # When chapters exist, preferred_seconds for "Introduction" should be chapter start + 3 = 3
    intro_shot = next((p for p in plan if p['section_title'] == 'Introduction'), None)
    assert intro_shot is not None
    assert intro_shot['window_start'] == 0
    assert intro_shot['window_end'] == 58

    deep_shot = next((p for p in plan if p['section_title'] == 'Deep Dive'), None)
    assert deep_shot is not None
    assert deep_shot['window_start'] == 58
    assert deep_shot['window_end'] == 238


def test_transcript_segments_anchor_when_no_chapters():
    from main import _build_screenshot_plan
    from models import TranscriptSegment

    segments = [
        TranscriptSegment(text="Welcome to the introduction of our topic", start=2.0, duration=3.0),
        TranscriptSegment(text="Now let us deep dive into the technical details", start=55.0, duration=4.0),
        TranscriptSegment(text="To conclude today's session", start=235.0, duration=3.0),
    ]

    plan = _build_screenshot_plan(
        _make_summary_with_sections(),
        duration_seconds=300,
        chapters=[],
        transcript_segments=segments,
    )

    # Deep dive section should be anchored near segment at 55.0
    deep_shot = next((p for p in plan if p['section_title'] == 'Deep Dive'), None)
    assert deep_shot is not None
    # window_start should be close to the transcript segment start (55s)
    assert deep_shot['window_start'] <= 60
    assert deep_shot['window_start'] >= 50
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_build_screenshot_plan.py::test_chapters_anchor_screenshot_timestamps tests/test_build_screenshot_plan.py::test_transcript_segments_anchor_when_no_chapters -v
```

Expected: FAIL.

- [ ] **Step 3: Add helper functions for chapter and segment matching**

Add these two functions to `backend/main.py` (place them just before `_build_screenshot_plan`):

```python
def _find_chapter_for_section(section_title: str, section_start_sec: int, chapters: list) -> dict | None:
    """Return the chapter whose time range contains section_start_sec, or best title match."""
    if not chapters:
        return None
    norm_title = _normalize_title(section_title)
    # Prefer time-based match first
    for ch in chapters:
        if ch.start_time <= section_start_sec <= ch.end_time:
            return ch
    # Fallback: title substring match
    for ch in chapters:
        if norm_title and (norm_title in _normalize_title(ch.title) or _normalize_title(ch.title) in norm_title):
            return ch
    return None


def _find_segment_anchor(section_title: str, section_desc: str, segments: list) -> float | None:
    """Return start time of the transcript segment most relevant to this section."""
    if not segments:
        return None

    section_words = set(
        w.lower() for w in re.split(r'\W+', f"{section_title} {section_desc}")
        if len(w) > 3
    )
    if not section_words:
        return None

    best_score = 0
    best_start = None
    for seg in segments:
        seg_words = set(w.lower() for w in re.split(r'\W+', seg.text) if len(w) > 3)
        overlap = len(section_words & seg_words)
        if overlap > best_score:
            best_score = overlap
            best_start = seg.start

    return best_start if best_score >= 2 else None
```

- [ ] **Step 4: Rewrite `_build_screenshot_plan` with chapter/segment anchoring**

Replace the entire `_build_screenshot_plan` function in `backend/main.py` (lines 46–150) with:

```python
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

    # Build section windows, anchored by chapters > transcript segments > Claude's seconds
    section_windows = []
    for idx, section in enumerate(sections):
        claude_start = max(0, min(int(section.get("timestamp_seconds", 0) or 0), max_second))
        section_title = section.get("title", "")
        section_desc = section.get("description", "")

        chapter = _find_chapter_for_section(section_title, claude_start, chapters)
        if chapter:
            start = max(0, min(int(chapter.start_time), max_second))
            end = max(start, min(int(chapter.end_time), max_second))
        else:
            segment_anchor = _find_segment_anchor(section_title, section_desc, transcript_segments)
            if segment_anchor is not None:
                start = max(0, min(int(segment_anchor), max_second))
                # End: next section's anchor or Claude's next section start
                if idx + 1 < len(sections):
                    next_start = int(sections[idx + 1].get("timestamp_seconds", start + 60) or (start + 60))
                    end = max(start, min(next_start - 1, max_second))
                else:
                    end = max_second
            else:
                # Fallback: use Claude's timestamp
                start = claude_start
                if idx + 1 < len(sections):
                    next_start = int(sections[idx + 1].get("timestamp_seconds", start + 1) or (start + 1))
                    end = max(start, min(next_start - 1, max_second))
                else:
                    end = max_second

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
            "title": section_title,
            "title_norm": _normalize_title(section_title),
            "start": start,
            "end": end,
            "context": " ".join(part for part in section_context_parts if part).strip(),
        })

    used_seconds = set()
    covered_sections = set()
    section_by_title = {s["title_norm"]: s for s in section_windows if s["title_norm"]}

    def allocate_second(preferred: int, window: dict | None) -> int:
        if window:
            start, end = window["start"], window["end"]
        else:
            start, end = 0, max_second

        preferred = max(start, min(int(preferred), end))
        candidates = [preferred]
        if window:
            candidates.extend([min(start + 3, end), min(start + 6, end), start])

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
                preferred = min(section["start"] + 3, section["end"])
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

        second = allocate_second(min(section["start"] + 3, section["end"]), section)
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
```

Add `re` to imports at top of `main.py` if not already present.

- [ ] **Step 5: Run all tests**

```bash
cd backend && python -m pytest tests/test_build_screenshot_plan.py -v
```

Expected: All 6 tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/main.py backend/tests/test_build_screenshot_plan.py
git commit -m "feat: screenshot plan uses chapters and transcript segments for timing"
```

---

## Task 5: CLIP Semantic Frame Ranking Service (Option 7)

**Files:**
- Create: `backend/services/clip_service.py`
- Create: `backend/tests/test_clip_service.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add dependencies to requirements.txt**

Add to `backend/requirements.txt`:

```
transformers==4.51.3
pillow==11.2.1
```

For `torch`, add as a CPU-only install to avoid the 2GB GPU build. Add a comment explaining this:

```
# torch CPU-only — install separately: pip install torch --index-url https://download.pytorch.org/whl/cpu
```

Install now:

```bash
pip install transformers==4.51.3 pillow==11.2.1
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

- [ ] **Step 2: Write failing test**

Create `backend/tests/test_clip_service.py`:

```python
import os
import tempfile
import pytest
from PIL import Image


def _make_test_image(color: tuple, path: str):
    """Create a solid-color 64x64 JPEG for testing."""
    img = Image.new("RGB", (64, 64), color=color)
    img.save(path, "JPEG")


def test_rank_frames_returns_valid_index():
    from services.clip_service import rank_frames

    with tempfile.TemporaryDirectory() as tmpdir:
        red_path = os.path.join(tmpdir, "red.jpg")
        blue_path = os.path.join(tmpdir, "blue.jpg")
        _make_test_image((220, 30, 30), red_path)
        _make_test_image((30, 30, 220), blue_path)

        result = rank_frames([red_path, blue_path], section_title="red color sample")
        assert result in (0, 1)  # just a valid index, not testing model accuracy


def test_rank_frames_single_image_returns_zero():
    from services.clip_service import rank_frames

    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = os.path.join(tmpdir, "frame.jpg")
        _make_test_image((100, 100, 100), img_path)
        result = rank_frames([img_path], section_title="any text")
        assert result == 0


def test_rank_frames_empty_list_returns_zero():
    from services.clip_service import rank_frames

    result = rank_frames([], section_title="anything")
    assert result == 0
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_clip_service.py -v
```

Expected: FAIL — `clip_service` module doesn't exist.

- [ ] **Step 4: Create `backend/services/clip_service.py`**

```python
import logging
from typing import List

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
    except Exception as e:
        logger.warning(f"CLIP unavailable: {e}. Frame ranking will use index 0 as fallback.")
        _clip_available = False
    return _clip_available


def rank_frames(image_paths: List[str], section_title: str) -> int:
    """
    Return the index of the image in image_paths that is most semantically
    similar to section_title. Returns 0 on empty list or CLIP unavailable.
    """
    if not image_paths:
        return 0
    if len(image_paths) == 1:
        return 0
    if not _load_clip():
        return 0

    try:
        import torch
        from PIL import Image

        images = []
        valid_indices = []
        for i, path in enumerate(image_paths):
            try:
                img = Image.open(path).convert("RGB")
                images.append(img)
                valid_indices.append(i)
            except Exception as e:
                logger.warning(f"Could not open image {path}: {e}")

        if not images:
            return 0

        inputs = _processor(
            text=[section_title],
            images=images,
            return_tensors="pt",
            padding=True,
        )

        with torch.no_grad():
            outputs = _model(**inputs)

        # logits_per_image shape: (num_images, num_texts)
        scores = outputs.logits_per_image[:, 0].tolist()

        best_local_idx = scores.index(max(scores))
        return valid_indices[best_local_idx]

    except Exception as e:
        logger.warning(f"CLIP ranking failed: {e}. Falling back to index 0.")
        return 0
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_clip_service.py -v
```

Expected: All 3 tests pass. Note: First run downloads CLIP model (~600MB) — this is a one-time download cached in `~/.cache/huggingface/`.

- [ ] **Step 6: Commit**

```bash
git add backend/services/clip_service.py backend/tests/test_clip_service.py backend/requirements.txt
git commit -m "feat: add CLIP semantic frame ranking service"
```

---

## Task 6: Playwright Screenshot Capture Service (Option 8)

**Files:**
- Create: `backend/services/playwright_service.py`
- Create: `backend/tests/test_playwright_service.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Install Playwright**

```bash
pip install playwright==1.51.0
playwright install chromium
```

Add to `backend/requirements.txt`:

```
playwright==1.51.0
```

- [ ] **Step 2: Write failing tests**

Create `backend/tests/test_playwright_service.py`:

```python
import pytest


def test_get_candidate_times_returns_three_times():
    from services.playwright_service import _get_candidate_times

    request = {
        "preferred_seconds": 60,
        "window_start": 50,
        "window_end": 120,
    }
    times = _get_candidate_times(request)
    assert len(times) == 3
    assert all(50 <= t <= 120 for t in times)
    assert 60 in times or any(abs(t - 60) <= 1 for t in times)


def test_get_candidate_times_clamped_to_window():
    from services.playwright_service import _get_candidate_times

    request = {
        "preferred_seconds": 5,
        "window_start": 10,
        "window_end": 30,
    }
    times = _get_candidate_times(request)
    assert all(10 <= t <= 30 for t in times)


def test_playwright_available_flag_is_bool():
    from services.playwright_service import PLAYWRIGHT_AVAILABLE
    assert isinstance(PLAYWRIGHT_AVAILABLE, bool)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_playwright_service.py -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 4: Create `backend/services/playwright_service.py`**

```python
import os
import asyncio
import logging
import shutil
import tempfile
from typing import List, Optional

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("playwright not installed — Playwright screenshot capture disabled.")

try:
    from services.clip_service import rank_frames
except ImportError:
    def rank_frames(image_paths, section_title):
        return 0


def _get_candidate_times(request: dict) -> List[float]:
    """
    Return 3 candidate seek times within the section window.
    Candidates: window_start+3s, preferred_seconds, midpoint of window.
    All clamped to [window_start, window_end].
    """
    preferred = float(request.get("preferred_seconds", request.get("seconds", 0)) or 0)
    window_start = float(request.get("window_start", max(0, preferred - 12)) or max(0, preferred - 12))
    window_end = float(request.get("window_end", preferred + 12) or preferred + 12)

    def clamp(v):
        return max(window_start, min(v, window_end))

    c1 = clamp(window_start + 3)
    c2 = clamp(preferred)
    c3 = clamp((window_start + window_end) / 2)

    # Deduplicate while preserving order
    seen = set()
    candidates = []
    for c in [c1, c2, c3]:
        key = round(c, 1)
        if key not in seen:
            seen.add(key)
            candidates.append(c)

    # Always return exactly 3 (pad with shifted values if deduplication collapsed them)
    while len(candidates) < 3:
        candidates.append(clamp(candidates[-1] + 2))

    return candidates[:3]


async def _capture_frame(page, seek_time: float, output_path: str) -> bool:
    """Seek the player to seek_time and screenshot the video element."""
    try:
        await page.evaluate(f"document.querySelector('video').currentTime = {seek_time}")
        await asyncio.sleep(0.6)
        video_el = page.locator("video")
        await video_el.screenshot(path=output_path, type="jpeg")
        return os.path.exists(output_path) and os.path.getsize(output_path) > 1000
    except Exception as e:
        logger.warning(f"Frame capture failed at {seek_time:.1f}s: {e}")
        return False


async def extract_screenshots_playwright(
    video_id: str,
    screenshot_requests: List[dict],
    static_dir: str,
) -> List[dict]:
    """
    Capture screenshots by seeking within the YouTube embed player.
    For each request, takes 3 candidate frames and picks the best via CLIP.
    Returns list of dicts with actual_seconds, filename, caption, section_title.
    """
    if not PLAYWRIGHT_AVAILABLE:
        logger.warning("Playwright not available. Returning empty screenshot list.")
        return []

    os.makedirs(static_dir, exist_ok=True)
    tmp_dir = tempfile.mkdtemp(prefix="pw_candidates_")
    results = []

    embed_url = (
        f"https://www.youtube-nocookie.com/embed/{video_id}"
        f"?autoplay=1&mute=1&controls=0&rel=0&modestbranding=1"
    )

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            logger.info(f"Playwright: loading YouTube embed for video {video_id}")
            await page.goto(embed_url, wait_until="domcontentloaded", timeout=20000)

            # Wait for video element to be present and ready
            try:
                await page.wait_for_selector("video", timeout=15000)
            except Exception:
                logger.error("Playwright: video element never appeared. Aborting.")
                await browser.close()
                return []

            # Pause and wait for seekable
            await page.evaluate("document.querySelector('video').pause()")
            await asyncio.sleep(1.0)

            for req in screenshot_requests:
                section_title = req.get("section_title", "")
                caption = req.get("caption", "")
                candidate_times = _get_candidate_times(req)

                candidate_paths: List[tuple] = []
                for i, t in enumerate(candidate_times):
                    tmp_path = os.path.join(tmp_dir, f"{video_id}_{section_title[:20]}_{i}.jpg")
                    ok = await _capture_frame(page, t, tmp_path)
                    if ok:
                        candidate_paths.append((t, tmp_path))

                if not candidate_paths:
                    logger.warning(f"No valid candidates for section '{section_title}'")
                    continue

                # CLIP ranks by section title
                paths_only = [p for _, p in candidate_paths]
                best_idx = rank_frames(paths_only, section_title=section_title or caption)
                best_time, best_tmp_path = candidate_paths[best_idx]

                # Read actual player time after the winning seek
                try:
                    actual_time = await page.evaluate("document.querySelector('video').currentTime")
                except Exception:
                    actual_time = best_time

                actual_sec = int(round(actual_time))
                final_name = f"{video_id}_{actual_sec}.jpg"
                final_path = os.path.join(static_dir, final_name)

                # Move best frame to static dir
                shutil.copy2(best_tmp_path, final_path)

                results.append({
                    **req,
                    "actual_seconds": actual_sec,
                    "filename": final_name,
                })
                logger.info(f"Playwright: captured '{section_title}' at {actual_sec}s → {final_name}")

            await browser.close()

    except Exception as e:
        logger.error(f"Playwright screenshot extraction failed: {e}")
        return []
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return results
```

- [ ] **Step 5: Run unit tests**

```bash
cd backend && python -m pytest tests/test_playwright_service.py -v
```

Expected: All 3 tests pass.

- [ ] **Step 6: Smoke test — verify Playwright can open a page**

```bash
cd backend && python -c "
import asyncio
from playwright.async_api import async_playwright

async def smoke():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto('https://example.com')
        title = await page.title()
        await browser.close()
        print(f'Page title: {title}')

asyncio.run(smoke())
"
```

Expected: `Page title: Example Domain`

- [ ] **Step 7: Commit**

```bash
git add backend/services/playwright_service.py backend/tests/test_playwright_service.py backend/requirements.txt
git commit -m "feat: add Playwright-based screenshot capture service with CLIP frame ranking"
```

---

## Task 7: Wire Playwright into main.py — Replace ffmpeg Screenshot Path

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Import playwright service in main.py**

Add to the imports at the top of `backend/main.py`:

```python
from services.playwright_service import extract_screenshots_playwright, PLAYWRIGHT_AVAILABLE
```

Remove the existing import:
```python
from services.screenshot_service import extract_screenshots_for_video, FFMPEG_AVAILABLE
```

- [ ] **Step 2: Replace the screenshot extraction block in `summarize()`**

Find the block starting at the `# Step 4` comment (around line 305). Replace the entire `if include_screenshots` block:

```python
# Step 4
yield yield_progress(4, "Extracting screenshots...")
screenshot_data = []
if include_screenshots and PLAYWRIGHT_AVAILABLE:
    screenshot_plan = _build_screenshot_plan(
        claude_val.get('summary', {}),
        metadata.duration_seconds,
        metadata.chapters,
        transcript_result.segments,
    )
    extracted_files = await extract_screenshots_playwright(
        video_id=video_id,
        screenshot_requests=screenshot_plan,
        static_dir=os.path.join(STATIC_DIR, "screenshots"),
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
elif include_screenshots and not PLAYWRIGHT_AVAILABLE:
    logger.warning("Screenshots requested but Playwright is not installed.")
```

- [ ] **Step 3: Update the health check endpoint**

Replace the `/api/health` handler:

```python
@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "playwright_available": PLAYWRIGHT_AVAILABLE,
        "version": "2.0.0"
    }
```

- [ ] **Step 4: Verify the server starts cleanly**

```bash
cd backend && python -c "
import asyncio
from main import app
print('main.py imported OK')
print('PLAYWRIGHT_AVAILABLE:', end=' ')
from services.playwright_service import PLAYWRIGHT_AVAILABLE
print(PLAYWRIGHT_AVAILABLE)
"
```

Expected:
```
main.py imported OK
PLAYWRIGHT_AVAILABLE: True
```

- [ ] **Step 5: Run the full test suite**

```bash
cd backend && python -m pytest tests/ -v --ignore=tests/test_screenshot_ranking.py
```

Expected: All tests in `test_build_screenshot_plan.py`, `test_clip_service.py`, `test_playwright_service.py`, `test_validators.py` pass.

Note: `test_screenshot_ranking.py` tests the old ffmpeg service which is no longer in the active path — skip it for now, don't delete it.

- [ ] **Step 6: Integration smoke test**

Start the server and hit the health endpoint:

```bash
cd backend && uvicorn main:app --port 8001 &
sleep 3
curl http://localhost:8001/api/health
```

Expected response:
```json
{"status":"ok","playwright_available":true,"version":"2.0.0"}
```

Kill the test server: `pkill -f "uvicorn main:app --port 8001"`

- [ ] **Step 7: Commit**

```bash
git add backend/main.py
git commit -m "feat: wire Playwright screenshot pipeline into summarize endpoint"
```

---

## Task 8: End-to-End Manual Verification

This task has no code changes — it verifies the full pipeline on a real video.

- [ ] **Step 1: Start the app**

```bash
cd backend && uvicorn main:app --port 8000
```

- [ ] **Step 2: Submit a real YouTube video with chapters**

Use a video known to have YouTube chapters (any tutorial video with a table of contents in the description). Submit it through the frontend.

In the browser dev tools Network tab, watch the SSE stream. Verify:
- Progress step 2 says "Fetching transcript..." and completes
- Progress step 4 says "Extracting screenshots..."
- The final result payload contains a `screenshots` array with items

- [ ] **Step 3: Verify screenshot timestamps are chapter-aligned**

In the result JSON, the `screenshots[n].seconds` values should correspond to chapter start times (± a few seconds), not arbitrary values that Claude guessed.

- [ ] **Step 4: Verify screenshots show correct visual content**

Open each screenshot URL (`/static/screenshots/{filename}`) and visually confirm the image matches the section caption. The timestamp badge in the UI should match what's actually visible in the screenshot.

- [ ] **Step 5: Test a video without chapters**

Submit a video that has no YouTube chapters. Verify screenshots still generate (falling back to transcript segment anchoring + Claude seconds), and the process completes without errors.

- [ ] **Step 6: Final commit**

```bash
git add .
git commit -m "chore: complete Playwright + CLIP screenshot pipeline integration"
```

---

## Self-Review

### Spec Coverage

| Feature | Covered by |
|---------|-----------|
| Option 3: YouTube chapters | Task 2 (video_service) + Task 4 (plan upgrade) |
| Option 4: Transcript segments | Task 3 (transcript_service) + Task 4 (plan upgrade) |
| Option 7: CLIP ranking | Task 5 (clip_service) + Task 6 (playwright_service calls rank_frames) |
| Option 8: Playwright capture | Task 6 (playwright_service) + Task 7 (wired into main.py) |
| Fallback when no chapters | Task 4 (segment anchor → Claude fallback) |
| Fallback when Playwright unavailable | Task 7 (elif branch with warning) |
| Actual timestamp badge accuracy | Task 6 (`video.currentTime` read back after seek) |
| Health check reflects new stack | Task 7 (playwright_available field) |

### Type Consistency Check

- `TranscriptResult` defined in Task 1, used in Task 3 (`fetch_transcript` return type) and Task 4 (`_build_screenshot_plan` param)
- `Chapter` defined in Task 1, extracted in Task 2, stored in `Metadata.chapters`, passed in Task 4
- `rank_frames(image_paths: List[str], section_title: str) -> int` defined in Task 5, called in Task 6 with same signature
- `extract_screenshots_playwright(video_id, screenshot_requests, static_dir)` defined in Task 6, called in Task 7 with same signature
- `_get_candidate_times(request: dict) -> List[float]` defined and tested in Task 6

### Placeholder Check

No TBD, TODO, or "similar to above" patterns present. All code blocks are complete.

# Summary Quality Improvements — Design Spec
**Date:** 2026-05-01
**Status:** Approved, ready for implementation
**Revision:** 3 — addresses single-pass coverage, input token budgeting, PrescanFrame contract, and execution ordering

## Problem

All video summaries suffer from three compounding issues:

1. **Shallow sections** — descriptions are vague, could apply to any video on the topic
2. **Missing content** — chunks of what the video covered don't appear in the summary
3. **Weak insights** — key insights read as topic labels, not evidence-backed takeaways

Additionally, the screenshot pipeline selects frames based on transcript text alone, producing:
- Evenly-spaced generic moments regardless of what is actually on screen
- Repeated frames when the same slide or terminal state persists across timestamps
- Fixed screenshot count regardless of video type or duration

---

## Screenshot Path Decision

**Playwright is the authoritative screenshot path going forward.** ffmpeg is retained only as a legacy fallback for environments where `PLAYWRIGHT_AVAILABLE` is false.

`main.py` currently prefers ffmpeg first. New order: **Playwright first → ffmpeg fallback**. The ffmpeg path (`screenshot_service.py`) is unchanged.

---

## Execution Ordering

```
1. fetch_video_metadata()           — sequential; provides duration_seconds, video_id, chapters
                                      (prescan needs duration_seconds, so this must come first)
2. asyncio.gather(
     fetch_transcript(),
     prescan_visual_richness()      — both are I/O-bound and independent of each other
   )
3. type_detection()                 — uses title + first 3,000 chars of transcript
4. clip_rescore_with_type()         — applies type-specific CLIP query to stored embeddings
5. dedup_pass_a()                   — selects diverse visually-confirmed candidate timestamps
6. summarization pipeline           — map-reduce or single-pass (see below)
7. playwright targeted capture      — Phase 6
8. dedup_pass_b()                   — Phase 7
```

---

## PrescanFrame Data Contract

```python
@dataclass
class PrescanFrame:
    seconds: int
    embedding: np.ndarray   # shape (512,), float32 — the only durable artifact
                            # reused for: type-specific rescoring (step 4) and dedup pass A (step 5)
                            # NOT reused for dedup pass B — see Phase 6/7 below
```

**Raw images** are discarded immediately after CLIP embedding extraction. Never written to disk.

**`richness_score` is not stored.** It is computed on-demand once — with the type-specific query after type detection (execution step 4). Dedup Pass A then sorts on those scores. There is no generic-query scoring step; the type-specific query is the only one used.

Memory footprint for 120 frames: 120 × 512 × 4 bytes = ~245KB. Request-scoped lifetime.

---

## Type Detection (`claude_service.py`)

Applied to both summarization paths (map-reduce and single-pass).

Keyword heuristic on `title + first 3,000 chars of transcript`. No LLM call.

**Title keywords (checked first):**
| Type | Title contains |
|------|---------------|
| `tutorial` | "tutorial", "how to", "how i", "guide", "walkthrough", "build", "setup", "install", "step by step" |
| `lecture` | "lecture", "course", "lesson", "explained", "theory", "introduction to", "101" |
| `opinion` | "opinion", "thoughts on", "why i", "my take", "review", "ranked", "tier list", "react to" |
| `general` | default — no match above |

**Transcript fallback (used when title gives no match):**
- Contains `"pip install"`, `"import "`, `"def "`, `"git clone"` → `tutorial`
- Contains `"in this lecture"`, `"today we'll"`, `"as we can see from"`, `"in the next section"` → `lecture`
- Contains `"I think"`, `"in my opinion"`, `"I believe"`, `"personally"`, `"I feel like"` (≥ 3 occurrences) → `opinion`
- No match → `general`

**CLIP richness queries by type:**
| Type | Query string |
|------|-------------|
| `tutorial` | `"terminal, code editor, software interface, command line, demo screen"` |
| `lecture` | `"presentation slide, whiteboard, diagram, text on screen, concept chart"` |
| `opinion` | `"graphic, text overlay, b-roll footage, visual aid, chart"` |
| `general` | `"informative screen content with text, code, diagrams, or visual data"` |

---

## Visual Pre-scan (`playwright_service.py` + `clip_service.py`)

Adaptive seek interval from `duration_seconds`:
- < 1,800s → every 30s (≤ 60 seeks)
- 1,800s – 7,200s → every 60s (≤ 120 seeks)
- > 7,200s → every 90s (≤ 120 seeks)

Returns `List[PrescanFrame]`. Raw images discarded immediately after embedding extraction.

**Dedup Pass A** (in `clip_service.py`, execution step 5 — after type detection (step 3) and rescoring (step 4)):
1. Type-specific richness scores already computed (execution step 4) — sort frames by richness descending
2. Greedily accept each frame; skip if cosine_similarity(candidate.embedding, any_accepted.embedding) > `SCREENSHOT_DEDUP_THRESHOLD`
3. Return diverse `List[PrescanFrame]` — the LLM's candidate pool

---

## Summarization Paths

Both paths receive the same upstream inputs: `video_type`, `duration_seconds`, `screenshot_count`, and `visual_candidates` (the deduped prescan timestamps filtered to each chunk's or the full video's time range).

### Map-Reduce Path

**Phase 3 — Timestamp-Anchor Chunking:**
At each target split point, find the nearest `[MM:SS]` marker within ±500 chars using regex. Split immediately before that marker. Fallback to nearest sentence-ending punctuation if no marker found.

**Phase 4 — Type-aware Map Prompt:**

Four `CHUNK_MAP_SYSTEM` variants:
| Type | Prompt emphasis |
|------|----------------|
| `tutorial` | Steps demonstrated, tools and commands named, gotchas, before/after states |
| `lecture` | Claims made, evidence provided, concepts defined, argument structure |
| `opinion` | Core claim, supporting reasoning, counterarguments addressed |
| `general` | Current generic prompt — unchanged |

Stronger insight rule added to all variants:
> Each `insight_seeds` entry MUST follow: `[specific claim] + [why/mechanism] + [timestamp evidence]`.

Visual candidates injected at the end of each chunk prompt (filtered to chunk's time window):
> "Visually confirmed moments in this time range: [12:30, 14:45, 18:10]. Prefer these for `screenshot_timestamps`."

**Phase 5 — Reduce:** Dynamic screenshot count instruction passed in (see formula below).

### Single-Pass Path (`generate_summary_and_mindmap_single_pass`)

The same four improvements apply:

1. **Type-aware prompt variant** — the `user_prompt` built in `generate_summary_and_mindmap_single_pass` switches on `video_type` to adjust the `RULES` section emphasis (same four variants as map, applied to the single-pass instruction block).
2. **Stronger insight rule** — `key_insights` rule updated: "Each must follow `[specific claim] + [why/mechanism] + [timestamp evidence]`. Generic observations are not valid."
3. **Visual candidates injected** — all prescan timestamps appended after the transcript:
   > "Visually confirmed on-screen moments (prefer for `screenshot_timestamps`): [12:30, 14:45, ...]"
4. **Dynamic screenshot count** — `screenshot_timestamps` rule uses the same computed count (see below).

---

## Dynamic Screenshot Count

Applied to both paths via the `screenshot_timestamps` instruction in the prompt.

**Formula:** `count = max(min_count, min(MAX_SCREENSHOTS, round(duration_minutes / interval_minutes)))`

| Type | Interval | Min | Hard cap | 30 min | 1 hr | 3 hr |
|------|----------|-----|----------|--------|------|------|
| tutorial | 5 min | 6 | 20 | 6 | 12 | 20 |
| lecture | 8 min | 5 | 20 | 5 | 8 | 20 |
| opinion | 12 min | 3 | 20 | 3 | 5 | 15 |
| general | 8 min | 5 | 20 | 5 | 8 | 20 |

`MAX_SCREENSHOTS = 20` (env var `SCREENSHOT_MAX_COUNT`, default 20).

---

## Token Budget

### Added prompt input overhead

| Location | Added content | Chars | Tokens |
|----------|--------------|-------|--------|
| Each map chunk prompt | Visual candidates (filtered to chunk window, ~40 timestamps × 8 chars) | ~320 | ~80 |
| Each map chunk prompt | Type label + emphasis lines | ~100 | ~25 |
| Each map chunk prompt | Stronger insight rule | ~120 | ~30 |
| Single-pass prompt | Visual candidates (all prescan, ~120 timestamps × 8 chars) | ~960 | ~240 |
| Single-pass prompt | Type variant + stronger insight rule | ~220 | ~55 |
| Reduce prompt | Screenshot count instruction (replaces "6-10") | ~10 | ~3 |

**Map chunk input overhead: ~135 tokens per chunk.** Existing chunk input is ~45,000 chars ≈ 11,250 tokens. Overhead is 1.2% — well within `MAP_CHUNK_TARGET_CHARS = 45,000`.

**Single-pass input overhead: ~295 tokens.** Existing cap is `TRANSCRIPT_MAX_INPUT_CHARS = 180,000` chars ≈ 45,000 tokens. Overhead is <1%. Safe.

**Reduce input overhead: ~3 tokens.** Negligible against `REDUCE_MAX_INPUT_CHARS = 392,000`.

### Added output overhead

20 screenshot entries × ~50 chars each ≈ 250 tokens. Well within the 20,000 token output budget for both reduce and single-pass.

**Conclusion: no changes to `TRANSCRIPT_MAX_INPUT_CHARS`, `REDUCE_MAX_INPUT_CHARS`, or any output token limits are required.**

---

## Playwright Targeted Capture (Phase 6)

Unchanged except: per-seek timeout of 15 seconds. On timeout, log warning and skip that timestamp.

**Latency budget:** 20 screenshots × 3 candidates × ~1.5s per seek ≈ 90s.

## Dedup Pass B (Phase 7, `clip_service.py`)

Operates on **final captured frames from Phase 6** — these are different images from the pre-scan frames, so pre-scan embeddings are not reused here.

During Phase 6, CLIP already computes embeddings for all 3 candidate frames per timestamp in order to rank them. The winning frame's embedding is retained (in memory, not disk) after selection. Dedup Pass B uses this set of Phase-6-computed embeddings.

Compare embeddings across all retained winning-frame embeddings. For any pair with cosine similarity > `SCREENSHOT_DEDUP_THRESHOLD`, drop the later frame (earlier frame had higher LLM relevance rank).

---

## Files Changed

| File | Changes |
|------|---------|
| `claude_service.py` | Type detection · timestamp-anchor chunking · 4 map prompt variants · stronger insight rule · visual candidate injection · dynamic screenshot count — **all applied to both map-reduce and single-pass paths** |
| `playwright_service.py` | `prescan_visual_richness()` · per-seek 15s timeout |
| `clip_service.py` | CLIP embedding extraction · type-specific rescoring · Dedup Pass A · Dedup Pass B |
| `main.py` | Playwright-first screenshot preference · sequential metadata fetch → parallel `asyncio.gather(fetch_transcript, prescan)` → type detection |

## Files Unchanged

`transcript_service.py` · `video_service.py` · `screenshot_service.py` (ffmpeg fallback) · all frontend files · UI theme.

---

## Configuration (env vars)

| Variable | Default | Purpose |
|----------|---------|---------|
| `SCREENSHOT_DEDUP_THRESHOLD` | `0.90` | Cosine similarity threshold for duplicate detection |
| `SCREENSHOT_MAX_COUNT` | `20` | Hard cap on screenshots per video regardless of formula |
| `PRESCAN_INTERVAL_SHORT` | `30` | Seek interval (s) for videos < 30 min |
| `PRESCAN_INTERVAL_MID` | `60` | Seek interval (s) for 30 min – 2 hr |
| `PRESCAN_INTERVAL_LONG` | `90` | Seek interval (s) for 2 hr+ |
| `SCREENSHOT_SEEK_TIMEOUT` | `15` | Per-seek timeout (s); timed-out timestamps are skipped |

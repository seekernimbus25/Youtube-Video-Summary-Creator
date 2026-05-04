# Agentic RAG Pipeline + AI Chat — Design Spec

**Date:** 2026-05-05
**Status:** Approved
**Scope:** RAG infrastructure (on-demand indexing) + AI Chat feature (Approach 2: Agentic RAG)

---

## 1. Overview

This spec introduces a RAG pipeline and AI Chat feature to the YT Video Summariser. The vector DB becomes the foundation for chat now, and for quiz and flashcards later. The existing summarization pipeline (key insights, sections, deep dive, mindmap) is **not changed**.

**Trigger:** Embedding is on-demand — initiated when the user first opens the AI Chat tab. Embeddings are cached per `video_id` in Qdrant indefinitely, so subsequent opens (by any user) skip re-indexing.

**External services added:**
| Service | Purpose | Free Tier |
|---|---|---|
| Qdrant Cloud | Vector store (dense + sparse) | 1GB, no expiry |
| Voyage AI (`voyage-3-lite`) | Embedding model | 50M tokens/month |
| fastembed | Sparse BM25 vectors | Open source, local |

---

## 2. Architecture & Data Flow

### Phase 1 — Indexing (once per video)

```
Existing transcript (already in memory from summarization)
  → Chunker: 512-token chunks, 64-token overlap, sentence boundaries
     metadata per chunk: { video_id, chunk_index, start_time, end_time, text }
  → Voyage AI batch embed (voyage-3-lite)
  → fastembed sparse BM25 encode
  → Qdrant upsert: dense + sparse vectors with payload
  → video_id marked as indexed (detectable via point count)
```

### Phase 2 — Agentic Chat (every message)

```
User message
  → Claude receives: conversation history + search_transcript(query, n=5) tool
  → Agent loop (max 3 iterations):
      Claude calls search_transcript(query)
        → Voyage embeds query (~80ms)
        → Qdrant hybrid search: dense + BM25, RRF fusion (~50ms)
        → return top-5 chunks with timestamps
      Claude reads chunks, decides to search again or answer
  → Claude streams final answer with [MM:SS] timestamp citations
  → Frontend emits "Searching transcript..." during tool calls, then streams tokens
```

### What stays unchanged

The summarization pipeline (transcript fetch → map-reduce → key sections/insights/deep dive/mindmap/SSE streaming) is completely untouched. The vector DB is additive.

---

## 3. Backend — New Services & Endpoints

### `backend/services/rag_service.py`

| Function | Description |
|---|---|
| `chunk_transcript(transcript_text, segments)` | Splits into 512-token chunks at sentence boundaries; attaches `start_time`/`end_time` from segment data; handles very short transcripts (<200 tokens) as single chunk |
| `index_video(video_id, chunks)` | Batch-embeds via Voyage AI + fastembed BM25, upserts into Qdrant; idempotent |
| `is_indexed(video_id)` | Checks Qdrant point count for video_id filter; returns bool |
| `search(video_id, query, n=5)` | Embeds query, runs hybrid search, returns ranked chunks with timestamps |

### `backend/services/chat_service.py`

| Function | Description |
|---|---|
| `chat(video_id, messages)` | Async generator; drives agentic loop; streams SSE events |

**Agentic loop logic:**
1. Build `search_transcript` tool definition for Claude
2. Send conversation history + tool to Claude (streaming)
3. On `tool_use` stop reason: execute searches, append results, loop (max 3 iterations)
4. On `end_turn`: stream final answer tokens to client
5. If max iterations reached without `end_turn`: force close loop, return partial answer with note

**SSE event types emitted:**
```json
{ "type": "status", "text": "Searching transcript..." }
{ "type": "token",  "text": "Based on [02:14]..." }
{ "type": "error",  "text": "Search failed, please retry" }
{ "type": "done" }
```

### New endpoints in `main.py`

```
POST /api/index
  Body:    { video_id: str, transcript: str, segments: [...] }
  Returns: SSE stream → { status: "indexing" | "ready" | "already_indexed" }

POST /api/chat
  Body:    { video_id: str, messages: [{role, content}] }
  Returns: SSE stream → status events + token stream
```

### New dependencies (`requirements.txt`)

```
qdrant-client
voyageai
fastembed
```

### New environment variables (`.env`)

```
VOYAGE_API_KEY=
QDRANT_URL=
QDRANT_API_KEY=
```

---

## 4. Frontend — AI Chat Tab

### New tab

Added to the existing tab bar: **Insights | Key Sections | Deep Dive | Mind Map | AI Chat**

### Tab states

| State | Condition | UI |
|---|---|---|
| Blocked | Summarization not yet complete | "Finish summarizing the video first." |
| Indexing | First open, `POST /api/index` in progress | "Indexing video..." progress indicator |
| Ready | `is_indexed` true | Chat interface |

### Chat interface

```
┌─────────────────────────────────────┐
│  AI Chat                            │
├─────────────────────────────────────┤
│                                     │
│  [assistant] Welcome! Ask me        │
│  anything about this video.         │
│                                     │
│  [user] What did he say about X?    │
│                                     │
│  [assistant] 🔍 Searching...        │
│  Based on [02:14] and [07:43]...    │
│                                     │
├─────────────────────────────────────┤
│  [ Ask anything about this video ] →│
└─────────────────────────────────────┘
```

### UX details

- "Searching transcript..." appears **inline in the message bubble** during tool-call iterations — not a spinner overlay
- `[MM:SS]` timestamp citations rendered as clickable chips — clicking scrolls the transcript view to that timestamp
- Conversation history lives in React state only (lost on page refresh — no server-side persistence in v1)
- Input disabled while response is streaming; re-enabled on `done` event
- No new frontend dependencies — React + vanilla CSS only

---

## 5. Error Handling & Edge Cases

### Indexing

| Scenario | Handling |
|---|---|
| Voyage API down / rate-limited | Show "Indexing failed" + retry button; partial index detected by point count mismatch and re-triggered |
| Qdrant connection failure | Same retry surface; log server-side |
| Very short transcript (<200 tokens) | Skip chunking, embed as single chunk; chat still works |

### Chat

| Scenario | Handling |
|---|---|
| Agent hits 3-iteration limit | Force `end_turn`; return partial answer + note: "I searched 3 times — here's what I found" |
| Voyage query embedding fails | Emit `error` SSE event; show "Search failed, please retry" |
| Query has no matching chunks | Claude gets empty results, responds naturally: "I couldn't find that in the transcript" |
| Off-topic question | Claude answers from its own knowledge — expected, no special handling |

### Qdrant free tier

- 1GB storage — a 1-hour video ≈ ~120 chunks ≈ ~0.5MB (voyage-3-lite: 512 dimensions × 4 bytes). Thousands of videos fit comfortably.
- No TTL — embeddings persist indefinitely; correct behaviour for per-video caching.
- No user auth needed — `video_id` is the cache key; all users share the same indexed vectors for a given video.

---

## 6. Testing Strategy

### Unit tests (`backend/tests/`)

**`test_rag_service.py`**
- Chunk boundary correctness: no chunk splits mid-sentence; timestamps preserved
- Idempotency: indexing same video twice does not duplicate Qdrant points
- `is_indexed` returns correct state before and after indexing

**`test_chat_service.py`**
- Tool-calling loop exits cleanly at max 3 iterations
- SSE event sequence is correct (status → tokens → done)
- Conversation history passed correctly to Claude across turns

### Integration tests (real Qdrant + Voyage, fixture transcript)

- Index a known 5-minute transcript → verify expected chunk count
- Search with a known query → verify top result contains expected text
- Full chat turn with a factual question → verify timestamp citations appear in response
- Use dedicated Qdrant collection `test_<video_id>`, cleaned up after each run

**No mocking of Qdrant or Voyage** in integration tests — aligns with existing project policy.

### Manual QA checklist

- [ ] First open of AI Chat: indexing spinner appears, completes, chat ready
- [ ] Sending a question: "Searching transcript..." appears, then answer streams
- [ ] Timestamp chips are clickable and scroll transcript view correctly
- [ ] Reload page, reopen AI Chat: skips re-indexing, goes straight to chat
- [ ] Very long video (2hr+): indexing completes without timeout
- [ ] Off-topic question: Claude answers naturally without hallucinating transcript content

---

## 7. Future Extensions (out of scope for this spec)

- **Quiz**: `POST /api/quiz` — retrieve chunks by topic, generate N MCQ/short-answer questions; reuses same RAG infrastructure
- **Flashcards**: `POST /api/flashcards` — retrieve concept-dense chunks, generate card pairs; same infrastructure
- **Migrate existing features to RAG**: incremental, with quality validation per feature before shipping
- **Multimodal**: YouTube storyboard thumbnails (via yt-dlp, no full video download) as v1.5 visual layer; full multimodal embeddings as v2
- **Agentic upgrade path**: query decomposition for multi-hop questions once usage patterns are clear

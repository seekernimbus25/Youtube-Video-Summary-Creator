# Agentic RAG Pipeline + AI Chat — Design Spec

**Date:** 2026-05-05 (revised post-review)
**Status:** Approved
**Scope:** RAG infrastructure (on-demand background indexing) + AI Chat feature (Approach 2: Agentic RAG, provider-agnostic)

---

## 1. Overview

This spec introduces a RAG pipeline and AI Chat feature to the YT Video Summariser. The vector DB becomes the foundation for chat now, and for quiz and flashcards later. The existing summarization pipeline (key insights, sections, deep dive, mindmap) is **not behaviorally changed**, but it is extended to persist transcript data for downstream use.

**Key architectural decisions:**
- Transcript is persisted to Redis at summarization time; indexing reads from there
- Indexing is a background job with SSE progress + Redis state; client can disconnect and poll
- Tool calling is provider-agnostic (Anthropic + OpenRouter both supported)
- Chat is a general assistant with video context; non-video answers are clearly labeled
- AI Chat is only available after a successful `/api/summarize`

**External services added:**

| Service | Purpose | Free Tier |
|---|---|---|
| Qdrant Cloud | Vector store (dense + sparse) | 1GB, no expiry |
| Voyage AI (`voyage-3-lite`) | Dense embedding model | 50M tokens/month |
| fastembed | Sparse BM25 vectors | Open source, local |
| Upstash Redis | Transcript cache + indexing job state | 10K commands/day, 256MB |

---

## 2. Architecture & Data Flow

### Phase 0 — Transcript Persistence (change to existing pipeline)

`/api/summarize` is extended to persist transcript data to Redis after fetching it, before summarization begins. This is additive — no summarization logic changes.

```
/api/summarize (existing)
  → fetch transcript + segments (existing)
  → NEW: persist to Redis
      key: transcript:{video_id}
      value: { transcript_text, segments, fetched_at }
      TTL: 24 hours
  → continue summarization as before (unchanged)
```

If Redis is unavailable, the persist step is skipped with a warning — summarization continues normally. Indexing will re-fetch transcript from YouTube in that case (see error handling).

### Phase 1 — Indexing (background, triggered on first AI Chat open)

```
Client opens AI Chat tab
  → POST /api/index { video_id }
  → Server checks Redis job state for video_id:
      "ready"    → return 200 { status: "already_indexed" }, done
      "indexing" → return 202 { status: "in_progress" }, client polls
      absent     → set job state = "indexing", return 202, begin work

Background indexing work (SSE progress stream):
  → read transcript from Redis (transcript:{video_id})
  → if Redis miss: re-fetch from YouTube via transcript_service (fallback)
  → check index manifest in Qdrant for video_id:
      if manifest exists and is valid (hash + version match): skip, set state = "ready"
      if manifest stale or absent: delete existing points for video_id, re-index
  → chunk transcript: 512-token chunks, 64-token overlap, sentence boundaries
      metadata per chunk: { video_id, chunk_index, start_time, end_time, text }
      special case: transcript < 200 tokens → single chunk
  → batch embed via Voyage AI (voyage-3-lite), 20 chunks per batch
  → batch BM25 encode via fastembed, same batches
  → upsert to Qdrant with dense + sparse vectors + payload
  → write index manifest to Qdrant (special point, payload only):
      { video_id, transcript_hash, chunking_version: "v1", dense_model: "voyage-3-lite",
        sparse_model: "bm25", chunk_count: N, indexed_at }
  → set Redis job state = "ready"
  → emit SSE: { type: "done", chunk_count: N }
```

Client polls `GET /api/index/status?video_id=...` every 2 seconds while job state is `"indexing"`. Response includes `{ status, progress_pct }`.

### Phase 2 — Agentic Chat (every message)

```
User sends message
  → POST /api/chat { video_id, messages: [{role, content}] }
  → check job state: if not "ready" → 409 { error: "not_indexed" }
  → chat_service.chat(video_id, messages, provider) → SSE stream

Agent loop (max 3 iterations, provider-agnostic via ToolCallingAdapter):
  → ToolCallingAdapter.complete(messages, tools=[search_transcript])
  → if tool calls returned:
      for each call: rag_service.search(video_id, query, n=5)
        → embed query via Voyage (~80ms)
        → Qdrant hybrid search: dense + BM25, RRF fusion (~50ms)
        → return top-5 chunks with [MM:SS] timestamps
      append tool results, loop
  → if end_turn: stream final answer tokens to client

System prompt (chat):
  You are a helpful assistant for this YouTube video.
  When your answer comes from the video transcript, cite the timestamp like [02:14].
  When your answer comes from your general knowledge and not the video, start your
  response with "[General knowledge]" so the user knows it is not from this video.
```

### What changes in the existing pipeline

`/api/summarize` is extended in one place: after transcript fetch, before summarization, persist to Redis. No summarization logic, prompts, chunking, or SSE output changes.

---

## 3. Data Models

New Pydantic models in `backend/models.py`:

```python
class IndexRequest(BaseModel):
    video_id: str

class IndexStatusResponse(BaseModel):
    status: Literal["already_indexed", "in_progress", "queued", "failed", "not_found"]
    progress_pct: Optional[int] = None  # 0-100 during indexing
    error: Optional[str] = None

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class ChatRequest(BaseModel):
    video_id: str
    messages: list[ChatMessage]

# SSE envelope (consistent with /api/summarize)
class ChatSSEEvent(BaseModel):
    type: Literal["status", "token", "error", "done"]
    text: Optional[str] = None

class IndexSSEEvent(BaseModel):
    type: Literal["progress", "done", "error"]
    progress_pct: Optional[int] = None
    chunk_count: Optional[int] = None
    text: Optional[str] = None
```

---

## 4. Backend — New Services & Endpoints

### `backend/services/transcript_cache_service.py`

| Function | Description |
|---|---|
| `persist(video_id, transcript_text, segments, ttl=86400)` | Writes to Redis; key: `transcript:{video_id}`; fire-and-forget, errors logged not raised |
| `get(video_id)` | Returns `{ transcript_text, segments }` or `None` on miss/error |

### `backend/services/rag_service.py`

| Function | Description |
|---|---|
| `chunk_transcript(transcript_text, segments)` | 512-token chunks, 64-token overlap, sentence boundaries; attaches `start_time`/`end_time`; single-chunk fallback for short transcripts |
| `get_manifest(video_id)` | Reads index manifest point from Qdrant; returns dict or `None` |
| `is_index_valid(video_id, transcript_text)` | Compares manifest hash + chunking_version + dense_model against current values |
| `index_video(video_id, chunks)` | Batch embed (Voyage, 20/batch) + BM25 encode (fastembed) + Qdrant upsert; writes manifest on completion; yields `(progress_pct, chunk_count)` |
| `search(video_id, query, n=5)` | Embed query → Qdrant hybrid search → return ranked chunks with timestamps |

### `backend/services/job_state_service.py`

| Function | Description |
|---|---|
| `get(video_id)` | Returns job state dict or `None`; key: `index_job:{video_id}` |
| `set(video_id, status, progress_pct=None, error=None)` | Upserts job state in Redis; TTL: 48h |
| `acquire_lock(video_id, ttl=300)` | SET NX with TTL; returns bool — used to prevent duplicate concurrent indexing |
| `release_lock(video_id)` | DEL lock key |

Lock key: `index_lock:{video_id}`, TTL 300s (5 min). If `acquire_lock` returns False, the endpoint returns 202 with status `"in_progress"` immediately without starting a second job.

### `backend/services/tool_calling_adapter.py`

Normalizes tool calling across Anthropic and OpenRouter (OpenAI-shaped) APIs.

```python
class ToolCallingAdapter:
    def __init__(self, provider: str, client, model: str): ...

    async def complete(
        self,
        messages: list[dict],
        tools: list[ToolDefinition],
        max_tokens: int,
    ) -> AdapterResponse:
        # Returns: { content: str | None, tool_calls: list[ToolCall] | None, stop_reason: str }
        # Normalizes:
        #   Anthropic: stop_reason="tool_use", content[i].type=="tool_use"
        #   OpenAI:    finish_reason="tool_calls", message.tool_calls[i]
```

```python
@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict  # JSON Schema

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict  # parsed, not raw string

@dataclass
class AdapterResponse:
    text: str | None          # final text if stop_reason is end_turn/stop
    tool_calls: list[ToolCall] | None
    stop_reason: str          # "end_turn" | "tool_calls" | "max_tokens"
```

The adapter handles message formatting for tool results:
- Anthropic: `{ role: "user", content: [{ type: "tool_result", tool_use_id, content }] }`
- OpenAI: `{ role: "tool", tool_call_id, content }`

### `backend/services/chat_service.py`

| Function | Description |
|---|---|
| `chat(video_id, messages, provider, client, model)` | Async generator; drives agentic loop via `ToolCallingAdapter`; streams `ChatSSEEvent` dicts; max 3 tool-call iterations |

**Agent loop:**
1. Build `search_transcript` tool definition
2. Call `adapter.complete(messages, tools, max_tokens=4096)`
3. If `tool_calls`: execute each via `rag_service.search`, append normalized tool results, emit `status` event, loop
4. If `end_turn`: stream `token` events for response text, emit `done`
5. If max iterations reached: emit remaining text + note, emit `done`

### New endpoints in `main.py`

```
POST /api/index
  Body:    IndexRequest
  Auth:    same as /api/summarize
  Returns: 200 { status: "already_indexed" }
         | 202 { status: "in_progress" | "queued" } + SSE progress stream

GET /api/index/status?video_id=...
  Returns: IndexStatusResponse

POST /api/chat
  Body:    ChatRequest
  Auth:    same as /api/summarize
  Returns: 409 if not indexed
         | SSE stream of ChatSSEEvent
```

### New environment variables

```
VOYAGE_API_KEY=
QDRANT_URL=
QDRANT_API_KEY=
UPSTASH_REDIS_URL=
UPSTASH_REDIS_TOKEN=
```

### New dependencies (`requirements.txt`)

```
qdrant-client
voyageai
fastembed
upstash-redis
```

---

## 5. Frontend — AI Chat Tab

### Tab placement

Existing tabs: **Insights | Key Sections | Deep Dive | Mind Map | Transcript**
New tab appended: **Insights | Key Sections | Deep Dive | Mind Map | Transcript | AI Chat**

### Tab states

| State | Condition | UI |
|---|---|---|
| Blocked | No summary result yet | "Summarize a video first to use AI Chat." |
| Queued / Indexing | Job state is `queued` or `in_progress` | "Indexing video..." + progress bar (polls `/api/index/status` every 2s) |
| Failed | Job state is `failed` | Error message + "Retry" button |
| Ready | Job state is `ready` | Chat interface |

On first open: fires `POST /api/index { video_id }` immediately. If response is `already_indexed`, shows chat. Otherwise, begins polling.

### Chat interface

```
┌─────────────────────────────────────┐
│  AI Chat                            │
├─────────────────────────────────────┤
│                                     │
│  [assistant] Ask me anything about  │
│  this video. I'll tell you when an  │
│  answer comes from general          │
│  knowledge rather than the video.   │
│                                     │
│  [user] What did he say about X?    │
│                                     │
│  [assistant] 🔍 Searching...        │
│  Based on [02:00] and [07:40]...    │
│                                     │
├─────────────────────────────────────┤
│  [ Ask anything about this video ] →│
└─────────────────────────────────────┘
```

### UX details

- "Searching transcript..." appears inline in the message bubble during tool-call iterations
- `[MM:SS]` timestamp citations rendered as clickable chips — clicking scrolls the transcript view to the **containing 2-minute bucket** (limitation of current batched transcript UI; exact per-timestamp anchors are out of scope for this spec)
- `[General knowledge]` prefix rendered with a distinct visual style (e.g. muted italic) so users can distinguish video-grounded vs. general answers
- Conversation history in React state only (lost on page refresh — no server-side persistence in v1)
- Input disabled while response is streaming; re-enabled on `done` event
- No new frontend dependencies

---

## 6. Error Handling & Edge Cases

### Indexing

| Scenario | Handling |
|---|---|
| Redis unavailable at persist time | Log warning, skip persist; summarization continues normally |
| Redis miss when indexing reads transcript | Re-fetch from YouTube via `transcript_service`; log warning |
| Transcript TTL expired (>24h since summarize) | Same as Redis miss — re-fetch from YouTube |
| Two users trigger indexing simultaneously | `acquire_lock` returns False for second request → return 202 `in_progress` immediately; no duplicate job |
| Voyage API rate-limited during indexing | Retry with exponential backoff (2s, 4s, 8s) per batch; if exhausted, set job state `failed`, emit `error` SSE event |
| Qdrant upsert fails mid-batch | Job state set to `failed`; partial index detected on next trigger via manifest chunk_count mismatch → re-index from scratch |
| Very short transcript (<200 tokens) | Skip chunking, embed as single chunk; chat works normally |
| Stale index (chunking_version or model changed) | `is_index_valid` returns False → delete old points, re-index |

### Chat

| Scenario | Handling |
|---|---|
| Chat requested before indexing complete | 409 `{ error: "not_indexed" }` |
| Agent hits 3-iteration limit | Force stop, return partial answer + appended note: "I searched the transcript 3 times — here's what I found." |
| Voyage query embed fails | Emit `error` SSE event; show "Search failed, please retry" |
| Search returns empty results | Claude receives empty chunks, responds naturally; if answer is from general knowledge, prefixes with `[General knowledge]` |
| Provider is OpenRouter | `ToolCallingAdapter` uses OpenAI tool-calling format transparently |

### Qdrant free tier

- Realistic storage per video: dense vectors (512 dim × 4 bytes × ~120 chunks ≈ 250KB) + sparse vectors (~100KB) + payload text (~250KB) + index overhead ≈ **~3-5MB per video**
- 1GB free tier → ~200-300 videos before approaching limit. Sufficient for dev/early prod; a Qdrant collection eviction policy (LRU by `indexed_at`) should be added before going beyond ~150 indexed videos.

---

## 7. Testing Strategy

### Unit tests (`backend/tests/`)

**`test_transcript_cache_service.py`**
- Persist + get round-trip
- Get returns None on miss
- Redis error in persist does not raise (fire-and-forget)

**`test_rag_service.py`**
- Chunk boundary correctness: no mid-sentence splits, timestamps preserved
- Single-chunk fallback for short transcripts
- `is_index_valid` returns False when transcript_hash, chunking_version, or dense_model differs

**`test_job_state_service.py`**
- `acquire_lock` returns True first call, False on second concurrent call
- `release_lock` allows re-acquisition

**`test_tool_calling_adapter.py`**
- Anthropic tool_use response correctly parsed into `AdapterResponse`
- OpenAI tool_calls response correctly parsed into `AdapterResponse`
- Tool result messages formatted correctly for each provider

**`test_chat_service.py`**
- Agent loop exits at max 3 iterations
- Partial-answer note appended at iteration limit
- SSE event sequence: status → tokens → done

### Integration tests (real services, fixture transcript)

- `POST /api/index` for a known 5-minute transcript → job state reaches `"ready"`, manifest written to Qdrant
- `GET /api/index/status` reflects progress during indexing
- Concurrent `POST /api/index` for same video_id → only one job runs (lock test)
- `POST /api/chat` with a factual question → timestamp citations appear in response
- `POST /api/chat` with an off-topic question → response contains `[General knowledge]` prefix
- Use dedicated Qdrant collection `test_{video_id}`, cleaned up after each run
- No mocking of Qdrant, Voyage, or Redis in integration tests

### Manual QA checklist

- [ ] Summarize a video; open AI Chat tab: indexing progress bar appears, completes
- [ ] `GET /api/index/status` returns `ready` after completion
- [ ] Reload page; reopen AI Chat: skips re-indexing (job state cached in Redis), goes straight to chat
- [ ] Factual question: "Searching transcript..." appears inline, answer streams with `[MM:SS]` chips
- [ ] Clicking `[MM:SS]` chip scrolls Transcript tab to the containing 2-minute bucket
- [ ] Off-topic question: response starts with `[General knowledge]` in muted style
- [ ] Two browser tabs open AI Chat simultaneously for same video: only one indexing job runs
- [ ] 2hr+ video: indexing completes (via batch progress), job state reaches `"ready"`
- [ ] Voyage API key missing: indexing fails gracefully with error message + retry button

---

## 8. Future Extensions (out of scope for this spec)

- **Quiz**: `POST /api/quiz` — retrieve chunks by topic, generate MCQ/short-answer; reuses RAG infrastructure
- **Flashcards**: `POST /api/flashcards` — retrieve concept-dense chunks, generate card pairs; same infrastructure
- **Per-timestamp transcript anchors**: add `id` attributes to transcript segments so citation chips can scroll precisely (prerequisite for exact-timestamp citations)
- **Qdrant LRU eviction**: evict oldest indexed videos when approaching 1GB limit
- **Redis persistence tier upgrade**: Upstash free tier is 10K commands/day; upgrade path is a paid Upstash plan or self-hosted Redis
- **Migrate existing features to RAG**: incremental, quality-validated per feature
- **Multimodal**: YouTube storyboard thumbnails as visual layer (yt-dlp, no full video download) — v1.5

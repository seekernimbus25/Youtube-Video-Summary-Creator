# Agentic RAG Pipeline + AI Chat — Design Spec

**Date:** 2026-05-05 (revised post-review ×2)
**Status:** Approved
**Scope:** RAG infrastructure (on-demand background indexing) + AI Chat feature (Approach 2: Agentic RAG, provider-agnostic)

---

## 1. Overview

This spec introduces a RAG pipeline and AI Chat feature to the YT Video Summariser. The vector DB becomes the foundation for chat now, and for quiz and flashcards later. The existing summarization pipeline (key insights, sections, deep dive, mindmap) is **not behaviorally changed**, but it is extended to persist transcript data for downstream use.

**Key architectural decisions:**
- Transcript is persisted to Redis at summarization time; indexing reads from there
- If Redis misses and no valid Qdrant index exists, the async indexing task sets job state to `failed` with a clear error message — no silent re-fetch fallback that could produce a different transcript than the one used for summarization
- Indexing runs as an **in-process async task** (not a durable background queue); if the FastAPI process restarts mid-index, the job is lost — lock expires within 300s of the last heartbeat and the client can retry. This is acceptable for v1; a durable queue is a future extension.
- `/api/index` returns JSON 200/202 immediately; client polls `/api/index/status` every 5s for progress
- Indexing lock is heartbeated every 60s to survive long videos without expiring mid-job
- **Readiness source of truth is the Qdrant manifest** — `/api/chat` gates on manifest validity only; Redis job state is never consulted for chat access. A stale or missing Redis job state cannot open or close the chat gate.
- Tool calling is provider-agnostic (Anthropic + OpenRouter both supported); `/api/chat` reads same `x-buddy-*` headers as `/api/summarize`
- Chat is a general assistant with video context; non-video answers are clearly labeled
- AI Chat is only available after a successful `/api/summarize`

**External services added:**

| Service | Purpose | Free Tier |
|---|---|---|
| Qdrant Cloud | Vector store (dense + sparse) | 1GB, no expiry |
| Voyage AI (`voyage-3-lite`) | Dense embedding model | 50M tokens/month |
| fastembed | Sparse BM25 vectors | Open source, local |
| Upstash Redis | Transcript cache + indexing job state | 10K commands/day, 256MB |

**Redis command budget:** Transcript persist = 1 cmd/summarize. Indexing job: ~12 cmds (state sets + lock + heartbeats for a 10-min job). Status polling at 5s interval for 10 min = 120 cmds/user. Estimated ~135 Redis commands per video indexed. 10K daily free tier supports ~74 video indexing sessions/day — sufficient for early prod; upgrade path is paid Upstash or self-hosted Redis.

---

## 2. Architecture & Data Flow

### Phase 0 — Transcript Persistence (additive change to existing pipeline)

`/api/summarize` is extended to persist transcript data to Redis after fetching it, before summarization begins. No summarization logic changes.

```
/api/summarize (existing)
  → fetch transcript + segments (existing)
  → NEW: persist to Redis
      key: transcript:{video_id}
      value: { transcript_text, segments, fetched_at }
      TTL: 24 hours
  → continue summarization as before (unchanged)
```

If Redis is unavailable, the persist step is skipped with a warning — summarization continues normally. If Redis misses when indexing reads transcript and no valid Qdrant index exists, the async task sets job state to `failed`; the client surfaces this on the next poll (see Phase 1).

### Phase 1 — Indexing (in-process async task, triggered on first AI Chat open)

Transport: `/api/index` returns plain JSON (200 or 202) immediately. No SSE. Client polls `/api/index/status` for progress.

**Durability note:** Indexing runs as an `asyncio` task inside the FastAPI process — not a durable queue. If the server restarts mid-index, the task is lost. The lock expires within 300s of the last heartbeat, after which the next `POST /api/index` starts a clean retry. Partial Qdrant writes are detected via manifest chunk_count mismatch and re-indexed from scratch.

```
Client opens AI Chat tab
  → POST /api/index { video_id }
  → Server checks Redis availability (ping):
      Redis unavailable → return 503 { error: "service_unavailable",
          message: "Indexing service temporarily unavailable. Please try again." }
      (no async task started; client shows error with retry button)
  → Server checks Qdrant manifest for video_id:
      valid manifest exists → set Redis job state = "ready" (refresh cache)
                            → return 200 { status: "ready" }, done
  → Server checks Redis job state:
      "indexing" → return 202 { status: "indexing" }, client begins polling
      absent/failed → acquire_lock(video_id, ttl=300)
          lock acquired → set job state = "indexing", return 202, begin async task
          lock not acquired → return 202 { status: "indexing" }, client begins polling

In-process async indexing task:
  → heartbeat loop: every 60s, extend lock TTL to 300s (runs until job completes/fails)
  → read transcript from Redis (transcript:{video_id})
  → if Redis miss: set job state = failed, error = "transcript_not_found",
      message = "Please re-summarize the video to enable AI Chat."
      release_lock(video_id), exit task
      (client sees "failed" on next poll and surfaces the message)
  → check Qdrant manifest:
      stale or absent → delete existing points for video_id, proceed
  → chunk transcript: 512-token chunks, 64-token overlap, sentence boundaries
      metadata per chunk: { video_id, chunk_index, start_time, end_time, text }
      special case: transcript < 200 tokens → single chunk
  → for each batch of 20 chunks:
      batch embed via Voyage AI (voyage-3-lite)
      batch BM25 encode via fastembed
      upsert to Qdrant with dense + sparse vectors + payload
      set Redis job state: { status: "indexing", progress_pct: N }
  → write index manifest to Qdrant (special point, payload only):
      { video_id, transcript_hash, chunking_version: "v1", dense_model: "voyage-3-lite",
        sparse_model: "bm25", chunk_count: N, indexed_at }
  → set Redis job state: { status: "ready" }
  → release_lock(video_id)
```

Client polls `GET /api/index/status?video_id=...` every **5 seconds** while job state is `"indexing"`. Response includes `{ status, progress_pct }`.

### Phase 2 — Agentic Chat (every message)

```
User sends message
  → POST /api/chat { video_id, messages: [{role, content}] }
      headers: x-buddy-api-key, x-buddy-provider, x-buddy-model (same as /api/summarize)
  → check Qdrant manifest: valid manifest exists → proceed
  → if no valid manifest: 409 { error: "not_indexed" }  — Redis state is not consulted
  → resolve provider/client/model from headers (same logic as /api/summarize)
  → chat_service.chat(video_id, messages, provider, client, model) → SSE stream

Agent loop (max 3 iterations, provider-agnostic via ToolCallingAdapter):
  → ToolCallingAdapter.complete(messages, tools=[search_transcript])
  → if tool calls returned:
      for each call: rag_service.search(video_id, query, n=5)
        → embed query via Voyage (~80ms)
        → Qdrant hybrid search: dense + BM25, RRF fusion (~50ms)
        → return top-5 chunks; each chunk carries exact start_time (e.g. 134s)
          formatted as [MM:SS] for model context (e.g. [02:14])
      append normalized tool results, loop
  → if end_turn: stream final answer tokens to client

Timestamp semantics: chunks carry exact start_time from transcript segments. The model
sees and cites exact [MM:SS] values — this precision helps it distinguish between parts
of the video. The frontend renders all citations as ~MM:SS chips that navigate to the
containing 2-minute bucket; the approximation is a rendering concern, not a model concern.

System prompt (chat):
  You are a helpful assistant for this YouTube video.
  When your answer comes from the video transcript, cite the section timestamp like [02:14].
  These timestamps are shown to users as approximate navigation points in the video.
  When your answer comes from your general knowledge and not the video, start your
  response with "[General knowledge]" so the user knows it is not from this video.
```

### What changes in the existing pipeline

`/api/summarize` gains one step: after transcript fetch, persist to Redis. No other logic, prompts, or SSE output changes.

---

## 3. Data Models

New Pydantic models in `backend/models.py`:

```python
class IndexRequest(BaseModel):
    video_id: str

class IndexStatusResponse(BaseModel):
    # Canonical job states:
    # "indexing"       — job running
    # "ready"          — indexed and available
    # "failed"         — job errored; retry is allowed
    # "not_found"      — no job exists for this video_id
    status: Literal["indexing", "ready", "failed", "not_found"]
    progress_pct: Optional[int] = None   # 0-100 during indexing
    error: Optional[str] = None

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class ChatRequest(BaseModel):
    video_id: str
    messages: list[ChatMessage]

# SSE envelope for /api/chat (consistent with /api/summarize pattern)
class ChatSSEEvent(BaseModel):
    type: Literal["status", "token", "error", "done"]
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
| `is_index_valid(video_id, transcript_text)` | Compares manifest `transcript_hash` + `chunking_version` + `dense_model` against current values |
| `index_video(video_id, chunks)` | Batch embed (Voyage, 20/batch) + BM25 encode (fastembed) + Qdrant upsert; writes manifest on completion; yields `progress_pct` per batch |
| `search(video_id, query, n=5)` | Embed query → Qdrant hybrid search → return ranked chunks with timestamps |

### `backend/services/job_state_service.py`

| Function | Description |
|---|---|
| `get(video_id)` | Returns job state dict or `None`; key: `index_job:{video_id}` |
| `set(video_id, status, progress_pct=None, error=None)` | Upserts job state in Redis; TTL: 48h |
| `acquire_lock(video_id, ttl=300)` | SET NX with TTL 300s; returns bool |
| `heartbeat_lock(video_id, ttl=300)` | EXPIRE on lock key; called every 60s during active indexing to prevent expiry on long videos |
| `release_lock(video_id)` | DEL lock key |

Lock key: `index_lock:{video_id}`, TTL 300s. The indexing coroutine runs `heartbeat_lock` every 60s, extending the lock by 300s on each call. If the job crashes, heartbeating stops and the lock expires naturally (within 300s of the last heartbeat), allowing the next request to start a clean retry.

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
        # Normalizes:
        #   Anthropic: stop_reason="tool_use", content[i].type=="tool_use"
        #   OpenAI:    finish_reason="tool_calls", message.tool_calls[i]

@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict  # JSON Schema

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict  # parsed from JSON, not raw string

@dataclass
class AdapterResponse:
    text: str | None           # final text if stop_reason is end_turn/stop
    tool_calls: list[ToolCall] | None
    stop_reason: str           # "end_turn" | "tool_calls" | "max_tokens"
```

Tool result message formatting (handled by adapter, not caller):
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
5. If max iterations reached without `end_turn`: emit remaining text + note "I searched the transcript 3 times — here's what I found.", emit `done`

### New endpoints in `main.py`

```
POST /api/index
  Body:    IndexRequest
  Auth:    same as /api/summarize
  Returns: 200 { status: "ready" }    — valid manifest exists, skip polling
         | 202 { status: "indexing" }  — job running or just started, begin polling
         | 503 { error: "service_unavailable" } — Redis is down; client shows error + retry
  Note: transcript_not_found surfaces as job state "failed" via polling, not as HTTP 4xx

GET /api/index/status?video_id=...
  Returns: IndexStatusResponse

POST /api/chat
  Body:    ChatRequest
  Headers: x-buddy-api-key, x-buddy-provider, x-buddy-model (same as /api/summarize)
  Auth:    same as /api/summarize
  Returns: 409 { error: "not_indexed" }     — if no valid Qdrant manifest (Redis state not consulted)
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
| Indexing | Job state is `indexing` | "Indexing video..." + progress bar (polls `/api/index/status` every 5s) |
| Failed | Job state is `failed` | Error message + "Retry" button (re-fires `POST /api/index`) |
| Ready | Job state is `ready` | Chat interface |

On first open: fires `POST /api/index { video_id }`. If response is `{ status: "ready" }` (200), shows chat immediately. If 202, begins polling. If 503, shows error with retry button.

### Chat interface

```
┌─────────────────────────────────────┐
│  AI Chat                            │
├─────────────────────────────────────┤
│                                     │
│  [assistant] Ask me anything about  │
│  this video. I'll note when an      │
│  answer comes from general          │
│  knowledge rather than the video.   │
│                                     │
│  [user] What did he say about X?    │
│                                     │
│  [assistant] 🔍 Searching...        │
│  Based on [~02:00] and [~07:40]...  │
│                                     │
├─────────────────────────────────────┤
│  [ Ask anything about this video ] →│
└─────────────────────────────────────┘
```

### UX details

- "Searching transcript..." appears inline in the message bubble during tool-call iterations
- Timestamp citations rendered as `~MM:SS` clickable chips. The `~` prefix and tooltip ("Scrolls to approximately this point in the transcript") communicate that navigation lands at the **containing 2-minute bucket**, not an exact second — matching what the current batched transcript UI can deliver. Exact per-timestamp anchors are a future extension.
- `[General knowledge]` prefix rendered with distinct visual style (muted italic) so users can distinguish video-grounded vs. general answers
- Conversation history in React state only (lost on page refresh — no server-side persistence in v1)
- Input disabled while response is streaming; re-enabled on `done` event
- No new frontend dependencies

---

## 6. Error Handling & Edge Cases

### Indexing

| Scenario | Handling |
|---|---|
| Redis unavailable at persist time | Log warning, skip persist; summarization continues normally |
| Redis miss when indexing reads transcript | Set job state to `failed`, error = "transcript_not_found", message = "Please re-summarize the video to enable AI Chat."; release lock; client sees failure on next poll |
| Transcript TTL expired (>24h since summarize) | Same as Redis miss — job state set to `failed` |
| Valid Qdrant index already exists | Skip all work; return 200 `ready` immediately |
| Two users trigger indexing simultaneously | Second `acquire_lock` returns False → return 202 `indexing`; client polls |
| Long video (lock would expire mid-job) | `heartbeat_lock` called every 60s extends lock to 300s; crash stops heartbeat → lock expires within 300s, retry allowed |
| Voyage API rate-limited during indexing | Retry per batch: exponential backoff (2s, 4s, 8s); if exhausted, set job state `failed` |
| Qdrant upsert fails mid-batch | Set job state `failed`; manifest not written; next trigger detects absent/stale manifest and re-indexes from scratch |
| Very short transcript (<200 tokens) | Single chunk; chat works normally |
| Stale index (version or model changed) | `is_index_valid` returns False → delete old points, re-index |

### Chat

| Scenario | Handling |
|---|---|
| Chat requested before indexing complete | Check manifest: not valid → 409 `{ error: "not_indexed" }` (Redis not consulted) |
| Agent hits 3-iteration limit | Force stop; return partial answer + note |
| Voyage query embed fails | Emit `error` SSE event; show "Search failed, please retry" |
| Search returns empty results | Claude receives empty chunks, responds naturally; labels general knowledge |
| Provider is OpenRouter | `ToolCallingAdapter` uses OpenAI tool-calling format transparently |
| `x-buddy-*` headers absent | Fall back to server-configured defaults (same behaviour as `/api/summarize`) |

### Qdrant free tier

- Storage per video: dense vectors (~250KB) + sparse vectors (~100KB) + payload text (~250KB) + index overhead ≈ **~3-5MB per video**
- 1GB free tier → ~200-300 videos. Add Qdrant LRU eviction (by `indexed_at` in manifest) before approaching ~150 indexed videos.

### Upstash Redis free tier

- 10K commands/day, 256MB
- ~135 Redis commands per video indexing session (persist + lock + heartbeats + job state sets + ~120 polling calls at 5s over 10 min)
- Supports ~74 full indexing sessions/day. Upgrade to paid Upstash or self-hosted Redis if daily usage exceeds that.

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
- `is_index_valid` returns False when `transcript_hash`, `chunking_version`, or `dense_model` differs

**`test_job_state_service.py`**
- `acquire_lock` returns True first call, False on second concurrent call
- `heartbeat_lock` extends TTL on lock key
- `release_lock` allows re-acquisition

**`test_tool_calling_adapter.py`**
- Anthropic `tool_use` response correctly parsed into `AdapterResponse`
- OpenAI `tool_calls` response correctly parsed into `AdapterResponse`
- Tool result messages formatted correctly for each provider

**`test_chat_service.py`**
- Agent loop exits at max 3 iterations
- Partial-answer note appended at iteration limit
- SSE event sequence: status → tokens → done

### Integration tests (real services, fixture transcript)

- `POST /api/index` for a known 5-minute transcript → `GET /api/index/status` eventually returns `ready`; manifest written to Qdrant
- Concurrent `POST /api/index` for same video_id → only one job runs (lock test)
- `POST /api/index` after Redis TTL expiry (no Qdrant index) → 202; polling shows `failed` with transcript_not_found message
- `POST /api/index` after Redis TTL expiry (valid Qdrant index exists) → 200 `ready`
- `POST /api/chat` with a factual question → `~MM:SS` citation chips appear in response
- `POST /api/chat` with an off-topic question → response contains `[General knowledge]` prefix
- Use dedicated Qdrant collection `test_{video_id}`, cleaned up after each run
- No mocking of Qdrant, Voyage, or Redis in integration tests

### Manual QA checklist

- [ ] Summarize a video; open AI Chat tab: indexing progress appears, job state reaches `ready`
- [ ] `GET /api/index/status` returns `ready` after completion
- [ ] Reload page; reopen AI Chat: POST /api/index returns 200 `ready` immediately, no re-indexing
- [ ] Factual question: "Searching transcript..." inline, answer streams with `~MM:SS` chips
- [ ] Clicking `~MM:SS` chip scrolls Transcript tab to the containing 2-minute bucket
- [ ] Off-topic question: response starts with `[General knowledge]` in muted style
- [ ] Two browser tabs open AI Chat simultaneously: only one indexing job runs
- [ ] 2hr+ video: indexing completes across all batches, job state reaches `ready`
- [ ] Voyage API key missing: indexing fails with error state, retry button works
- [ ] Redis unavailable: summarize still completes; `POST /api/index` returns 503 with retry button; Qdrant-indexed videos still allow chat (manifest check bypasses Redis)

---

## 8. Future Extensions (out of scope for this spec)

- **Quiz**: `POST /api/quiz` — retrieve chunks by topic, generate MCQ/short-answer; reuses RAG infrastructure and `ToolCallingAdapter`
- **Flashcards**: `POST /api/flashcards` — retrieve concept-dense chunks, generate card pairs; same infrastructure
- **Per-timestamp transcript anchors**: add `id` attributes to transcript segment rows so `~MM:SS` chips can scroll precisely; removes the need for `~` approximation marker
- **Qdrant LRU eviction**: evict oldest indexed videos (by `indexed_at` manifest field) when approaching 1GB limit
- **Redis upgrade path**: paid Upstash plan or self-hosted Redis when daily session count exceeds ~74
- **Migrate existing features to RAG**: incremental migration of key insights / sections / deep dive / mindmap, quality-validated per feature before shipping
- **Multimodal**: YouTube storyboard thumbnails as lightweight visual layer (yt-dlp, no full video download) — v1.5

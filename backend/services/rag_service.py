import asyncio
import hashlib
import logging
import os
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

CHUNKING_VERSION = "v1"
DENSE_MODEL = "voyage-3-lite"
DENSE_DIM = 512
CHUNK_TOKEN_TARGET = 512
CHUNK_TOKEN_OVERLAP = 64
SHORT_TRANSCRIPT_TOKEN_LIMIT = 200
BATCH_SIZE = 20
CHUNKS_COLLECTION = "yt_transcripts"
MANIFESTS_COLLECTION = "yt_manifests"

_sparse_model = None
_collections_ready = False
_collections_lock = threading.Lock()

try:
    from qdrant_client.models import (
        Distance,
        FieldCondition,
        Filter,
        Fusion,
        FusionQuery,
        MatchValue,
        PayloadSchemaType,
        PointStruct,
        Prefetch,
        SparseIndexParams,
        SparseVector,
        SparseVectorParams,
        VectorParams,
    )
except ModuleNotFoundError:
    class Distance(Enum):
        COSINE = "cosine"

    class Fusion(Enum):
        RRF = "rrf"

    class PayloadSchemaType(Enum):
        KEYWORD = "keyword"

    @dataclass
    class VectorParams:
        size: int
        distance: object

    @dataclass
    class SparseIndexParams:
        dummy: bool = True

    @dataclass
    class SparseVectorParams:
        index: object | None = None

    @dataclass
    class MatchValue:
        value: object

    @dataclass
    class FieldCondition:
        key: str
        match: object

    @dataclass
    class Filter:
        must: list

    @dataclass
    class SparseVector:
        indices: list
        values: list

    @dataclass
    class Prefetch:
        query: object
        using: str
        limit: int

    @dataclass
    class FusionQuery:
        fusion: object

    @dataclass
    class PointStruct:
        id: object
        vector: object
        payload: dict


def _qdrant():
    from qdrant_client import AsyncQdrantClient

    return AsyncQdrantClient(
        url=os.environ.get("QDRANT_URL", ""),
        api_key=os.environ.get("QDRANT_API_KEY", ""),
        timeout=float(os.environ.get("QDRANT_TIMEOUT_SECONDS", "20")),
        check_compatibility=False,
    )


def _voyage():
    import voyageai

    return voyageai.AsyncClient(api_key=os.environ.get("VOYAGE_API_KEY", ""))


def _bm25():
    global _sparse_model
    if _sparse_model is None:
        from fastembed import SparseTextEmbedding

        _sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")
    return _sparse_model


def _chunk_id(video_id: str, chunk_index: int) -> int:
    digest = hashlib.md5(f"{video_id}:{chunk_index}".encode()).hexdigest()
    return int(digest[:16], 16) & 0x7FFFFFFFFFFFFFFF


def _manifest_id(video_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"manifest:{video_id}"))


def _transcript_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _seg_attr(seg, attr: str, default=0):
    if hasattr(seg, attr):
        return getattr(seg, attr)
    return seg.get(attr, default) if isinstance(seg, dict) else default


def _token_count(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [part.strip() for part in parts if part.strip()]


async def _ensure_collections(client) -> None:
    global _collections_ready
    if _collections_ready:
        return

    with _collections_lock:
        if _collections_ready:
            return

    existing = {c.name for c in (await client.get_collections()).collections}
    if CHUNKS_COLLECTION not in existing:
        await client.create_collection(
            CHUNKS_COLLECTION,
            vectors_config={"dense": VectorParams(size=DENSE_DIM, distance=Distance.COSINE)},
            sparse_vectors_config={"sparse": SparseVectorParams(index=SparseIndexParams())},
        )
    if MANIFESTS_COLLECTION not in existing:
        await client.create_collection(
            MANIFESTS_COLLECTION,
            vectors_config=VectorParams(size=1, distance=Distance.COSINE),
        )
    for collection_name in (CHUNKS_COLLECTION, MANIFESTS_COLLECTION):
        try:
            await client.create_payload_index(
                collection_name=collection_name,
                field_name="video_id",
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except Exception as exc:
            msg = (str(exc) or repr(exc)).lower()
            if "already exists" not in msg and "existing" not in msg and "409" not in msg and "conflict" not in msg:
                raise

    _collections_ready = True


def chunk_transcript(transcript_text: str, segments: list) -> list[dict]:
    if _token_count(transcript_text) < SHORT_TRANSCRIPT_TOKEN_LIMIT:
        start = _seg_attr(segments[0], "start") if segments else 0
        end = _seg_attr(segments[-1], "start") if segments else 0
        return [{
            "text": transcript_text.strip(),
            "chunk_index": 0,
            "start_time": start,
            "end_time": end,
        }]

    if not segments:
        sentences = _split_sentences(transcript_text)
        chunks = []
        current_sentences = []
        current_tokens = 0
        for sentence in sentences:
            sent_tokens = _token_count(sentence)
            if current_sentences and current_tokens + sent_tokens > CHUNK_TOKEN_TARGET:
                chunks.append({
                    "text": " ".join(current_sentences).strip(),
                    "chunk_index": len(chunks),
                    "start_time": 0,
                    "end_time": 0,
                })
                overlap_sentences = []
                overlap_tokens = 0
                for existing in reversed(current_sentences):
                    overlap_sentences.insert(0, existing)
                    overlap_tokens += _token_count(existing)
                    if overlap_tokens >= CHUNK_TOKEN_OVERLAP:
                        break
                current_sentences = overlap_sentences
                current_tokens = overlap_tokens

            current_sentences.append(sentence)
            current_tokens += sent_tokens

        if current_sentences:
            chunks.append({
                "text": " ".join(current_sentences).strip(),
                "chunk_index": len(chunks),
                "start_time": 0,
                "end_time": 0,
            })
        return chunks

    chunks = []
    current_segs = []
    current_tokens = 0

    for seg in segments:
        text = _seg_attr(seg, "text", "").strip()
        seg_tokens = _token_count(text)
        if not text:
            continue

        current_segs.append(seg)
        current_tokens += seg_tokens

        if current_tokens >= CHUNK_TOKEN_TARGET:
            chunk_text = " ".join(_seg_attr(s, "text", "").strip() for s in current_segs).strip()
            chunks.append({
                "text": chunk_text,
                "chunk_index": len(chunks),
                "start_time": _seg_attr(current_segs[0], "start"),
                "end_time": _seg_attr(current_segs[-1], "start"),
            })
            overlap_segs = []
            overlap_tokens = 0
            for existing in reversed(current_segs):
                overlap_segs.insert(0, existing)
                overlap_tokens += _token_count(_seg_attr(existing, "text", ""))
                if overlap_tokens >= CHUNK_TOKEN_OVERLAP:
                    break
            current_segs = overlap_segs
            current_tokens = overlap_tokens

    if current_segs:
        chunk_text = " ".join(_seg_attr(s, "text", "").strip() for s in current_segs).strip()
        if chunk_text:
            chunks.append({
                "text": chunk_text,
                "chunk_index": len(chunks),
                "start_time": _seg_attr(current_segs[0], "start"),
                "end_time": _seg_attr(current_segs[-1], "start"),
            })

    return [chunk for chunk in chunks if chunk["text"]]


async def get_manifest(video_id: str) -> dict | None:
    try:
        client = _qdrant()
        await _ensure_collections(client)
        results, _ = await client.scroll(
            collection_name=MANIFESTS_COLLECTION,
            scroll_filter=Filter(must=[FieldCondition(key="video_id", match=MatchValue(value=video_id))]),
            limit=1,
            with_payload=True,
            with_vectors=False,
        )
        return results[0].payload if results else None
    except Exception as exc:
        logger.warning("get_manifest failed for %s: %s", video_id, str(exc).strip() or repr(exc))
        return None


def is_index_valid(video_id: str, transcript_text: str) -> bool:
    manifest = asyncio.run(get_manifest(video_id))
    if not manifest:
        return False
    return (
        manifest.get("transcript_hash") == _transcript_hash(transcript_text)
        and manifest.get("chunking_version") == CHUNKING_VERSION
        and manifest.get("dense_model") == DENSE_MODEL
    )


async def index_video(video_id: str, chunks: list[dict]) -> AsyncGenerator[int, None]:
    client = _qdrant()
    await _ensure_collections(client)
    voyage = _voyage()
    bm25 = _bm25()
    total = len(chunks)
    if total == 0:
        yield 100
        return

    await client.delete(
        CHUNKS_COLLECTION,
        points_selector=Filter(must=[FieldCondition(key="video_id", match=MatchValue(value=video_id))]),
    )

    for batch_start in range(0, total, BATCH_SIZE):
        batch = chunks[batch_start: batch_start + BATCH_SIZE]
        texts = [c["text"] for c in batch]

        dense_result = await voyage.embed(texts, model=DENSE_MODEL)
        dense_vecs = dense_result.embeddings
        sparse_embeds = await asyncio.to_thread(lambda t=texts: list(bm25.embed(t)))

        points = [
            PointStruct(
                id=_chunk_id(video_id, chunk["chunk_index"]),
                vector={
                    "dense": dense,
                    "sparse": SparseVector(
                        indices=sparse_emb.indices.tolist(),
                        values=sparse_emb.values.tolist(),
                    ),
                },
                payload={
                    "video_id": video_id,
                    "chunk_index": chunk["chunk_index"],
                    "start_time": chunk["start_time"],
                    "end_time": chunk["end_time"],
                    "text": chunk["text"],
                },
            )
            for chunk, dense, sparse_emb in zip(batch, dense_vecs, sparse_embeds)
        ]

        await client.upsert(CHUNKS_COLLECTION, points=points)
        yield int((batch_start + len(batch)) / total * 100)


async def write_manifest(video_id: str, transcript_text: str, chunk_count: int) -> None:
    client = _qdrant()
    await _ensure_collections(client)
    await client.upsert(
        MANIFESTS_COLLECTION,
        points=[
            PointStruct(
                id=_manifest_id(video_id),
                vector=[0.0],
                payload={
                    "video_id": video_id,
                    "transcript_hash": _transcript_hash(transcript_text),
                    "chunking_version": CHUNKING_VERSION,
                    "dense_model": DENSE_MODEL,
                    "sparse_model": "bm25",
                    "chunk_count": chunk_count,
                    "indexed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        ],
    )


async def search(video_id: str, query: str, n: int = 5) -> list[dict]:
    client = _qdrant()
    await _ensure_collections(client)
    voyage = _voyage()
    bm25 = _bm25()

    dense_result = await voyage.embed([query], model=DENSE_MODEL)
    dense_vec = dense_result.embeddings[0]

    sparse_embeds = await asyncio.to_thread(lambda: list(bm25.embed([query])))
    sparse_emb = sparse_embeds[0]

    results = await client.query_points(
        collection_name=CHUNKS_COLLECTION,
        prefetch=[
            Prefetch(query=dense_vec, using="dense", limit=20),
            Prefetch(
                query=SparseVector(
                    indices=sparse_emb.indices.tolist(),
                    values=sparse_emb.values.tolist(),
                ),
                using="sparse",
                limit=20,
            ),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=n,
        query_filter=Filter(must=[FieldCondition(key="video_id", match=MatchValue(value=video_id))]),
        with_payload=True,
    )

    chunks = []
    for point in results.points:
        payload = point.payload
        start = float(payload.get("start_time", 0))
        mm, ss = divmod(int(start), 60)
        chunks.append({
            "text": payload.get("text", ""),
            "timestamp": f"{mm:02d}:{ss:02d}",
            "start_time": start,
        })
    return chunks

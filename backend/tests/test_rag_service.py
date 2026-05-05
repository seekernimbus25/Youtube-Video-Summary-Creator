import asyncio
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.rag_service as svc


@pytest.fixture(autouse=True)
def _reset_collection_cache():
    svc._collections_ready = False
    yield
    svc._collections_ready = False


def _make_segs(texts):
    current = 0.0
    segs = []
    for text in texts:
        segs.append({"text": text, "start": current, "duration": 5.0})
        current += 5.0
    return segs


def test_short_transcript_becomes_single_chunk():
    segs = _make_segs(["Hello world."])
    chunks = svc.chunk_transcript("Hello world.", segs)
    assert len(chunks) == 1
    assert chunks[0]["chunk_index"] == 0
    assert "Hello world." in chunks[0]["text"]


def test_chunks_have_ascending_chunk_index():
    words = ["word"] * 600
    text = " ".join(words)
    segs = _make_segs([" ".join(words[i:i + 50]) for i in range(0, 600, 50)])
    chunks = svc.chunk_transcript(text, segs)
    assert len(chunks) > 1
    assert [chunk["chunk_index"] for chunk in chunks] == list(range(len(chunks)))


def test_chunks_carry_start_time():
    segs = _make_segs(["word " * 500, "more " * 500])
    text = " ".join(seg["text"] for seg in segs)
    chunks = svc.chunk_transcript(text, segs)
    for chunk in chunks:
        assert "start_time" in chunk
        assert chunk["start_time"] >= 0


def test_no_chunk_is_empty():
    segs = _make_segs(["sentence " * 100] * 10)
    text = " ".join(seg["text"] for seg in segs)
    chunks = svc.chunk_transcript(text, segs)
    assert all(chunk["text"].strip() for chunk in chunks)


def test_chunk_transcript_handles_empty_segments():
    transcript = ("Sentence one. Sentence two. Sentence three. " * 120).strip()
    chunks = svc.chunk_transcript(transcript, [])
    assert len(chunks) > 1
    assert all("text" in chunk for chunk in chunks)


def test_is_index_valid_returns_true_when_manifest_matches():
    text = "hello world"
    digest = hashlib.sha256(text.encode()).hexdigest()[:16]
    manifest = {
        "transcript_hash": digest,
        "chunking_version": svc.CHUNKING_VERSION,
        "dense_model": svc.DENSE_MODEL,
    }
    with patch.object(svc, "get_manifest", AsyncMock(return_value=manifest)):
        assert svc.is_index_valid("vid1", text) is True


def test_is_index_valid_returns_false_on_version_mismatch():
    text = "hello world"
    digest = hashlib.sha256(text.encode()).hexdigest()[:16]
    manifest = {
        "transcript_hash": digest,
        "chunking_version": "v0",
        "dense_model": svc.DENSE_MODEL,
    }
    with patch.object(svc, "get_manifest", AsyncMock(return_value=manifest)):
        assert svc.is_index_valid("vid1", text) is False


@pytest.mark.anyio
async def test_ensure_collections_creates_video_id_payload_indexes():
    mock_client = AsyncMock()
    mock_client.get_collections.return_value = MagicMock(collections=[])
    mock_client.create_collection = AsyncMock()
    mock_client.create_payload_index = AsyncMock()

    await svc._ensure_collections(mock_client)

    assert mock_client.create_collection.await_count == 2
    mock_client.create_payload_index.assert_any_await(
        collection_name=svc.CHUNKS_COLLECTION,
        field_name="video_id",
        field_schema=svc.PayloadSchemaType.KEYWORD,
    )
    mock_client.create_payload_index.assert_any_await(
        collection_name=svc.MANIFESTS_COLLECTION,
        field_name="video_id",
        field_schema=svc.PayloadSchemaType.KEYWORD,
    )


@pytest.mark.anyio
async def test_ensure_collections_ignores_existing_payload_index_errors():
    mock_client = AsyncMock()
    mock_client.get_collections.return_value = MagicMock(collections=[])
    mock_client.create_collection = AsyncMock()
    mock_client.create_payload_index = AsyncMock(side_effect=[
        RuntimeError("Index already exists"),
        RuntimeError("409 conflict"),
    ])

    await svc._ensure_collections(mock_client)

    assert svc._collections_ready is True


@pytest.mark.anyio
async def test_index_video_yields_progress_and_reaches_100():
    chunks = [
        {"text": f"chunk {idx}", "chunk_index": idx, "start_time": float(idx * 5), "end_time": float(idx * 5 + 4)}
        for idx in range(5)
    ]
    mock_client = AsyncMock()
    mock_client.get_collections.return_value = MagicMock(collections=[])
    mock_client.create_collection = AsyncMock()
    mock_client.delete = AsyncMock()
    mock_client.upsert = AsyncMock()

    mock_voyage = AsyncMock()
    mock_voyage.embed.return_value = MagicMock(embeddings=[[0.0] * 512 for _ in range(5)])

    mock_sparse_emb = MagicMock()
    mock_sparse_emb.indices.tolist.return_value = [1, 2, 3]
    mock_sparse_emb.values.tolist.return_value = [0.1, 0.2, 0.3]

    async def fake_to_thread(fn, *args, **kwargs):
        return [mock_sparse_emb] * len(chunks)

    with patch.object(svc, "_qdrant", return_value=mock_client), \
         patch.object(svc, "_voyage", return_value=mock_voyage), \
         patch.object(svc, "_bm25", return_value=MagicMock()), \
         patch("asyncio.to_thread", side_effect=fake_to_thread):
        progress = []
        async for pct in svc.index_video("vid1", chunks):
            progress.append(pct)

    assert progress[-1] == 100
    assert all(0 <= pct <= 100 for pct in progress)


@pytest.mark.anyio
async def test_search_returns_formatted_chunks():
    mock_client = AsyncMock()
    mock_client.get_collections.return_value = MagicMock(collections=[])
    mock_client.create_collection = AsyncMock()
    mock_point = MagicMock()
    mock_point.payload = {"text": "hello there", "start_time": 134.0, "end_time": 145.0}
    mock_client.query_points.return_value = MagicMock(points=[mock_point])

    mock_voyage = AsyncMock()
    mock_voyage.embed.return_value = MagicMock(embeddings=[[0.0] * 512])

    mock_sparse_emb = MagicMock()
    mock_sparse_emb.indices.tolist.return_value = [1, 2]
    mock_sparse_emb.values.tolist.return_value = [0.5, 0.5]

    async def fake_to_thread(fn, *args, **kwargs):
        return [mock_sparse_emb]

    with patch.object(svc, "_qdrant", return_value=mock_client), \
         patch.object(svc, "_voyage", return_value=mock_voyage), \
         patch.object(svc, "_bm25", return_value=MagicMock()), \
         patch("asyncio.to_thread", side_effect=fake_to_thread):
        results = await svc.search("vid1", "hello query", n=5)

    assert len(results) == 1
    assert results[0]["text"] == "hello there"
    assert results[0]["timestamp"] == "02:14"
    assert results[0]["start_time"] == 134.0


@pytest.mark.anyio
async def test_search_timestamp_format():
    mock_client = AsyncMock()
    mock_client.get_collections.return_value = MagicMock(collections=[])
    mock_client.create_collection = AsyncMock()
    mock_point = MagicMock()
    mock_point.payload = {"text": "second minute", "start_time": 65.0, "end_time": 70.0}
    mock_client.query_points.return_value = MagicMock(points=[mock_point])

    mock_voyage = AsyncMock()
    mock_voyage.embed.return_value = MagicMock(embeddings=[[0.0] * 512])

    mock_sparse_emb = MagicMock()
    mock_sparse_emb.indices.tolist.return_value = []
    mock_sparse_emb.values.tolist.return_value = []

    async def fake_to_thread(fn, *args, **kwargs):
        return [mock_sparse_emb]

    with patch.object(svc, "_qdrant", return_value=mock_client), \
         patch.object(svc, "_voyage", return_value=mock_voyage), \
         patch.object(svc, "_bm25", return_value=MagicMock()), \
         patch("asyncio.to_thread", side_effect=fake_to_thread):
        results = await svc.search("vid1", "second minute", n=5)

    assert results[0]["timestamp"] == "01:05"

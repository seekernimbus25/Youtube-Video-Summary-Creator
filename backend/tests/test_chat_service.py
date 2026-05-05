from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.tool_calling_adapter import AdapterResponse, ToolCall
import services.chat_service as svc


def _adapter_response(stop_reason, text=None, tool_calls=None, messages=None):
    return AdapterResponse(
        text=text,
        tool_calls=tool_calls,
        stop_reason=stop_reason,
        updated_messages=messages or [],
    )


def _mock_stream(*tokens):
    async def _gen(*args, **kwargs):
        for token in tokens:
            yield token
    return _gen


@pytest.mark.anyio
async def test_chat_yields_token_and_done_on_end_turn():
    mock_adapter = AsyncMock()
    mock_adapter.complete = AsyncMock(return_value=_adapter_response(
        "end_turn",
        text="Here is the answer.",
        messages=[{"role": "assistant", "content": []}],
    ))
    mock_adapter.append_tool_results = MagicMock(return_value=[])

    with patch("services.chat_service.ToolCallingAdapter", return_value=mock_adapter), \
         patch("services.chat_service.search", AsyncMock(return_value=[])):
        events = [event async for event in svc.chat("vid1", [{"role": "user", "content": "q"}], "anthropic", MagicMock(), "model")]

    assert "token" in [event["type"] for event in events]
    assert events[-1]["type"] == "done"
    assert "Here is the answer." in "".join(event["text"] for event in events if event["type"] == "token")


@pytest.mark.anyio
async def test_chat_emits_status_during_tool_call():
    tool_call = ToolCall(id="tc1", name="search_transcript", arguments={"query": "ml"})
    mock_adapter = AsyncMock()
    mock_adapter.complete = AsyncMock(side_effect=[
        _adapter_response("tool_calls", tool_calls=[tool_call], messages=[]),
        _adapter_response("end_turn", text="Final answer.", messages=[]),
    ])
    mock_adapter.append_tool_results = MagicMock(return_value=[])

    with patch("services.chat_service.ToolCallingAdapter", return_value=mock_adapter), \
         patch("services.chat_service.search", AsyncMock(return_value=[{"text": "chunk", "timestamp": "01:00", "start_time": 60.0}])):
        events = [event async for event in svc.chat("vid1", [{"role": "user", "content": "q"}], "anthropic", MagicMock(), "model")]

    event_types = [event["type"] for event in events]
    assert "status" in event_types
    assert "token" in event_types
    assert "done" in event_types


@pytest.mark.anyio
async def test_chat_stops_at_max_iterations():
    tool_call = ToolCall(id="tc1", name="search_transcript", arguments={"query": "ml"})
    mock_adapter = AsyncMock()
    mock_adapter.complete = AsyncMock(return_value=_adapter_response(
        "tool_calls", tool_calls=[tool_call], messages=[]
    ))
    mock_adapter.stream_answer = _mock_stream("Final answer after search.")
    mock_adapter.append_tool_results = MagicMock(return_value=[])

    with patch("services.chat_service.ToolCallingAdapter", return_value=mock_adapter), \
         patch("services.chat_service.search", AsyncMock(return_value=[])):
        events = [event async for event in svc.chat("vid1", [{"role": "user", "content": "q"}], "anthropic", MagicMock(), "model")]

    token_text = "".join(event.get("text", "") for event in events if event["type"] == "token")
    assert events[-1]["type"] == "done"
    assert "searched" in token_text.lower()

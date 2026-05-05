import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.tool_calling_adapter import (
    ToolCallingAdapter,
    AdapterResponse,
    ToolCall,
    ToolDefinition,
)

SEARCH_TOOL = ToolDefinition(
    name="search_transcript",
    description="Search the transcript",
    parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
)


@pytest.mark.anyio
async def test_anthropic_end_turn_response():
    client = AsyncMock()
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Here is the answer."
    response = MagicMock()
    response.content = [text_block]
    response.stop_reason = "end_turn"
    client.messages.create = AsyncMock(return_value=response)

    adapter = ToolCallingAdapter("anthropic", client, "claude-haiku-4-5-20251001")
    result = await adapter.complete([{"role": "user", "content": "hello"}], [SEARCH_TOOL], system="Helpful")

    assert result.stop_reason == "end_turn"
    assert result.text == "Here is the answer."
    assert result.tool_calls is None
    assert result.updated_messages[-1]["role"] == "assistant"


@pytest.mark.anyio
async def test_anthropic_tool_use_response():
    client = AsyncMock()
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "tu_abc"
    tool_block.name = "search_transcript"
    tool_block.input = {"query": "machine learning"}
    response = MagicMock()
    response.content = [tool_block]
    response.stop_reason = "tool_use"
    client.messages.create = AsyncMock(return_value=response)

    adapter = ToolCallingAdapter("anthropic", client, "claude-haiku-4-5-20251001")
    result = await adapter.complete([{"role": "user", "content": "q"}], [SEARCH_TOOL])

    assert result.stop_reason == "tool_calls"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].id == "tu_abc"
    assert result.tool_calls[0].arguments == {"query": "machine learning"}


def test_anthropic_append_tool_results():
    adapter = ToolCallingAdapter("anthropic", None, "m")
    tool_call = ToolCall(id="tu_abc", name="search_transcript", arguments={"query": "ml"})
    updated = adapter.append_tool_results([{"role": "assistant", "content": []}], [tool_call], ["result text"])
    assert updated[-1]["role"] == "user"
    assert updated[-1]["content"][0]["type"] == "tool_result"
    assert updated[-1]["content"][0]["tool_use_id"] == "tu_abc"


@pytest.mark.anyio
async def test_openai_end_turn_response():
    client = AsyncMock()
    msg = MagicMock()
    msg.content = "The answer is 42."
    msg.tool_calls = None
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "stop"
    response = MagicMock()
    response.choices = [choice]
    client.chat.completions.create = AsyncMock(return_value=response)

    adapter = ToolCallingAdapter("openrouter", client, "meta-llama/llama")
    result = await adapter.complete([{"role": "user", "content": "q"}], [SEARCH_TOOL])

    assert result.stop_reason == "end_turn"
    assert result.text == "The answer is 42."
    assert result.tool_calls is None


@pytest.mark.anyio
async def test_openai_tool_calls_response():
    client = AsyncMock()
    tool_call = MagicMock()
    tool_call.id = "call_xyz"
    tool_call.function.name = "search_transcript"
    tool_call.function.arguments = json.dumps({"query": "neural nets"})
    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [tool_call]
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "tool_calls"
    response = MagicMock()
    response.choices = [choice]
    client.chat.completions.create = AsyncMock(return_value=response)

    adapter = ToolCallingAdapter("openrouter", client, "m")
    result = await adapter.complete([{"role": "user", "content": "q"}], [SEARCH_TOOL])

    assert result.stop_reason == "tool_calls"
    assert result.tool_calls[0].arguments == {"query": "neural nets"}


def test_openai_append_tool_results():
    adapter = ToolCallingAdapter("openrouter", None, "m")
    tool_call = ToolCall(id="call_xyz", name="search_transcript", arguments={"query": "ml"})
    updated = adapter.append_tool_results([{"role": "assistant", "content": None}], [tool_call], ["found text"])
    assert updated[-1]["role"] == "tool"
    assert updated[-1]["tool_call_id"] == "call_xyz"
    assert updated[-1]["content"] == "found text"

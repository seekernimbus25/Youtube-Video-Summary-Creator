import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class AdapterResponse:
    text: str | None
    tool_calls: list[ToolCall] | None
    stop_reason: str
    updated_messages: list[dict] = field(default_factory=list)


class ToolCallingAdapter:
    def __init__(self, provider: str, client, model: str):
        self.provider = provider
        self.client = client
        self.model = model

    async def complete(
        self,
        messages: list[dict],
        tools: list[ToolDefinition],
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> AdapterResponse:
        if self.provider == "anthropic":
            return await self._complete_anthropic(messages, tools, max_tokens, system)
        return await self._complete_openai(messages, tools, max_tokens)

    async def _complete_anthropic(
        self,
        messages: list[dict],
        tools: list[ToolDefinition],
        max_tokens: int,
        system: str | None,
    ) -> AdapterResponse:
        anthropic_tools = [
            {"name": tool.name, "description": tool.description, "input_schema": tool.parameters}
            for tool in tools
        ]
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools
        if system:
            kwargs["system"] = system

        response = await self.client.messages.create(**kwargs)

        tool_calls = []
        text_parts = []
        assistant_content = []
        for block in response.content:
            if block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input))
                assistant_content.append(
                    {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
                )
            elif block.type == "text":
                text_parts.append(block.text)
                assistant_content.append({"type": "text", "text": block.text})

        updated = messages + [{"role": "assistant", "content": assistant_content}]
        stop_reason = (
            "end_turn" if response.stop_reason == "end_turn"
            else "tool_calls" if response.stop_reason == "tool_use"
            else "max_tokens"
        )
        return AdapterResponse(
            text=" ".join(text_parts) or None,
            tool_calls=tool_calls or None,
            stop_reason=stop_reason,
            updated_messages=updated,
        )

    async def _complete_openai(
        self,
        messages: list[dict],
        tools: list[ToolDefinition],
        max_tokens: int,
    ) -> AdapterResponse:
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if openai_tools:
            kwargs["tools"] = openai_tools

        response = await self.client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        tool_calls = None
        assistant_msg = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tool_call.id,
                    name=tool_call.function.name,
                    arguments=json.loads(tool_call.function.arguments),
                )
                for tool_call in msg.tool_calls
            ]
            assistant_msg["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in msg.tool_calls
            ]

        updated = messages + [assistant_msg]
        stop_reason = (
            "end_turn" if finish_reason == "stop"
            else "tool_calls" if finish_reason == "tool_calls"
            else "max_tokens"
        )
        return AdapterResponse(
            text=msg.content,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            updated_messages=updated,
        )

    def append_tool_results(
        self,
        messages: list[dict],
        tool_calls: list[ToolCall],
        results: list[str],
    ) -> list[dict]:
        if self.provider == "anthropic":
            content = [
                {"type": "tool_result", "tool_use_id": tool_call.id, "content": result}
                for tool_call, result in zip(tool_calls, results)
            ]
            return messages + [{"role": "user", "content": content}]

        updated = list(messages)
        for tool_call, result in zip(tool_calls, results):
            updated.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})
        return updated

    async def stream_answer(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        system: str | None = None,
    ):
        if self.provider == "anthropic":
            kwargs = {"model": self.model, "messages": messages, "max_tokens": max_tokens}
            if system:
                kwargs["system"] = system
            async with self.client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield text
            return

        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

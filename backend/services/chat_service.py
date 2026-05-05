import logging
from typing import AsyncGenerator

from services.rag_service import search
from services.tool_calling_adapter import ToolCallingAdapter, ToolDefinition

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 3

SYSTEM_PROMPT = (
    "You are a helpful assistant for this YouTube video. "
    "When your answer comes from the video transcript, cite the section timestamp like [02:14]. "
    "These timestamps are shown to users as approximate navigation points in the video. "
    "When your answer comes from your general knowledge and not the video, start your "
    'response with "[General knowledge]" so the user knows it is not from this video.'
)

SEARCH_TOOL = ToolDefinition(
    name="search_transcript",
    description=(
        "Search the video transcript for information relevant to the user's question. "
        "Call this multiple times with different queries to find all relevant content."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query"},
            "n": {"type": "integer", "description": "Number of results (default 5)", "default": 5},
        },
        "required": ["query"],
    },
)


async def chat(
    video_id: str,
    messages: list[dict],
    provider: str,
    client,
    model: str,
) -> AsyncGenerator[dict, None]:
    adapter = ToolCallingAdapter(provider, client, model)

    if provider == "anthropic":
        api_messages = list(messages)
        system = SYSTEM_PROMPT
    else:
        api_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + list(messages)
        system = None

    for _ in range(MAX_ITERATIONS):
        response = await adapter.complete(api_messages, [SEARCH_TOOL], max_tokens=4096, system=system)
        api_messages = response.updated_messages

        if response.stop_reason in ("end_turn", "max_tokens") or response.tool_calls is None:
            final_text = response.text or ""
            if final_text:
                for piece in final_text.split(" "):
                    if piece:
                        yield {"type": "token", "text": piece + " "}
            yield {"type": "done"}
            return

        yield {"type": "status", "text": "Searching transcript..."}
        results = []
        for tool_call in response.tool_calls:
            query = tool_call.arguments.get("query", "")
            n = int(tool_call.arguments.get("n", 5))
            chunks = await search(video_id, query, n=n)
            if chunks:
                result_text = "\n\n".join(f"[{chunk['timestamp']}] {chunk['text']}" for chunk in chunks)
            else:
                result_text = "No relevant content found in transcript."
            results.append(result_text)

        api_messages = adapter.append_tool_results(api_messages, response.tool_calls, results)

    suffix = "\n\n*I searched the transcript 3 times — here's what I found.*"
    async for token in adapter.stream_answer(api_messages, max_tokens=4096, system=system):
        yield {"type": "token", "text": token}
    yield {"type": "token", "text": suffix}
    yield {"type": "done"}


async def demo_chat(
    video_id: str,
    messages: list[dict],
    user_api_key: str | None = None,
    user_provider: str | None = None,
    user_model: str | None = None,
) -> AsyncGenerator[dict, None]:
    text = (
        "Hey there awesome person, thanks for trying out my YouTube summarizer. "
        "This is a demo video in the public portfolio build, so AI Chat here is only a placeholder. "
        "To use the full service with real summaries and transcript-grounded AI chat, download the project "
        "from the GitHub repository at https://github.com/seekernimbus25/Youtube-Video-Summary-Creator, "
        "run it locally, and plug in your own API key."
    )
    for piece in text.split(" "):
        if piece:
            yield {"type": "token", "text": piece + " "}
    yield {"type": "done"}

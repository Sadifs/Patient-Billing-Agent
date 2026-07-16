"""OpenAI-compatible client for custom endpoints."""

from __future__ import annotations

import logging
from typing import Any, Generator

from openai import OpenAI

from ..messages import StreamChunk, ToolCallDelta
from .base import BaseModelClient

logger = logging.getLogger(__name__)


def _to_responses_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """Convert Chat Completions nested tools to Responses flat tools."""
    if not tools:
        return None

    converted: list[dict[str, Any]] = []
    for tool in tools:
        if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
            fn = tool["function"]
            converted.append(
                {
                    "type": "function",
                    "name": fn["name"],
                    "description": fn.get("description"),
                    "parameters": fn.get("parameters"),
                    # Responses defaults toward strict; keep current non-strict behavior.
                    "strict": False,
                }
            )
        else:
            converted.append(tool)
    return converted


def _to_responses_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Chat Completions messages to Responses input Items.

    AgentHarness appends assistant tool_calls and role=tool messages. Those
    must become function_call / function_call_output Items correlated by
    call_id (not the fc_ item id).
    """
    items: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")

        if role == "tool":
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": msg["tool_call_id"],
                    "output": msg.get("content") or "",
                }
            )
            continue

        if role == "assistant" and msg.get("tool_calls"):
            if msg.get("content"):
                items.append({"role": "assistant", "content": msg["content"]})
            for tc in msg["tool_calls"]:
                fn = tc.get("function") or {}
                items.append(
                    {
                        "type": "function_call",
                        "call_id": tc["id"],
                        "name": fn.get("name"),
                        "arguments": fn.get("arguments") or "{}",
                    }
                )
            continue

        items.append({"role": role, "content": msg.get("content")})
    return items


class OpenAICompatibleClient(BaseModelClient):
    """Client for any OpenAI-compatible API endpoint."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "gpt-4o",
    ):
        self.model = model

        if base_url.endswith("/responses"):
            base_url = base_url.rsplit("/responses", 1)[0]
        if not base_url.endswith("/v1") and "/v1" not in base_url:
            base_url = base_url.rstrip("/") + "/v1"

        self.client = OpenAI(base_url=base_url, api_key=api_key)

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Generator[StreamChunk, None, None]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "input": _to_responses_input(messages),
            "stream": True,
            # Avoid unexpected server-side persistence of PHI bill chats.
            "store": False,
        }

        responses_tools = _to_responses_tools(tools)
        if responses_tools:
            kwargs["tools"] = responses_tools

        stream = self.client.responses.create(**kwargs)

        for event in stream:
            etype = getattr(event, "type", None)

            if etype == "response.output_text.delta":
                yield StreamChunk(text=event.delta)
                continue

            if etype == "response.output_item.added":
                item = event.item
                if getattr(item, "type", None) == "function_call":
                    # Use call_id (not fc_ item id) so tool outputs can round-trip.
                    yield StreamChunk(
                        tool_call=ToolCallDelta(
                            index=event.output_index,
                            id=item.call_id,
                            name=item.name,
                            arguments="",
                        )
                    )
                continue

            if etype == "response.function_call_arguments.delta":
                yield StreamChunk(
                    tool_call=ToolCallDelta(
                        index=event.output_index,
                        arguments=event.delta,
                    )
                )
                continue

            if etype in {"response.completed", "response.incomplete"}:
                yield StreamChunk(finish_reason="stop")
                continue

            if etype == "error":
                raise RuntimeError(
                    getattr(event, "message", None) or "Responses API stream error"
                )

"""The LLM that plays the agents: one plain call, and one call with tools.

Anthropic is used when ``ANTHROPIC_API_KEY`` is set, otherwise OpenAI when
``OPENAI_API_KEY`` is. ``POC_MODEL`` picks the model. Nothing here knows about
SenseLab; the examples decide what goes into a prompt and what a tool does.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 4096


@dataclass
class Reply:
    """One model response, with the numbers a trace can record."""

    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float


@dataclass
class ToolRun:
    """A conversation in which the model could call tools."""

    text: str
    #: Every tool call in order: {"name": ..., "input": {...}, "output": "..."}.
    calls: list[dict[str, Any]] = field(default_factory=list)
    replies: list[Reply] = field(default_factory=list)


def provider() -> str:
    if (os.environ.get("ANTHROPIC_API_KEY") or "").strip():
        return "anthropic"
    if (os.environ.get("OPENAI_API_KEY") or "").strip():
        return "openai"
    raise SystemExit("Set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env: the agents are real LLM calls.")


def model() -> str:
    chosen = (os.environ.get("POC_MODEL") or "").strip()
    if chosen:
        return chosen
    if provider() == "anthropic":
        return DEFAULT_ANTHROPIC_MODEL
    raise SystemExit("Set POC_MODEL in .env to the OpenAI model to use: there is no default for OpenAI.")


def complete(system: str, user: str) -> Reply:
    """One system prompt, one user message, one answer."""
    return run_with_tools(system, user, tools=[], handlers={}).replies[-1]


def run_with_tools(
    system: str,
    user: str,
    tools: list[dict[str, Any]],
    handlers: dict[str, Callable[..., str]],
    *,
    max_steps: int = 6,
) -> ToolRun:
    """Let the model work on ``user``, calling ``tools`` as it sees fit.

    Each tool is ``{"name", "description", "parameters"}`` where ``parameters``
    is a JSON Schema object; ``handlers[name](**arguments)`` runs it and
    returns a string. With no tools this is a single call. The loop stops when
    the model answers without calling a tool, or after ``max_steps`` rounds.
    """
    if provider() == "anthropic":
        return _anthropic_loop(system, user, tools, handlers, max_steps)
    return _openai_loop(system, user, tools, handlers, max_steps)


def _call_tool(handlers: dict[str, Callable[..., str]], name: str, arguments: dict[str, Any]) -> str:
    handler = handlers.get(name)
    if handler is None:
        return f"error: there is no tool named {name}"
    try:
        return handler(**arguments)
    except Exception as exc:  # noqa: BLE001 - the model sees the failure and can react to it
        return f"error: {exc}"


# ── Anthropic ───────────────────────────────────────────────────────────────


def _anthropic_loop(system, user, tools, handlers, max_steps) -> ToolRun:
    import anthropic

    client = anthropic.Anthropic()
    name = model()
    messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
    request: dict[str, Any] = {"model": name, "max_tokens": MAX_TOKENS, "system": system}
    if tools:
        request["tools"] = [
            {"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
            for t in tools
        ]
    run = ToolRun(text="")
    for _ in range(max_steps):
        started = time.monotonic()
        response = client.messages.create(messages=messages, **request)
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        run.replies.append(
            Reply(
                text=text,
                provider="anthropic",
                model=response.model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                latency_ms=(time.monotonic() - started) * 1000,
            )
        )
        run.text = text or run.text
        uses = [block for block in response.content if block.type == "tool_use"]
        if not uses:
            break
        # The assistant turn goes back exactly as it arrived, then one result
        # per tool call.
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for use in uses:
            output = _call_tool(handlers, use.name, dict(use.input))
            run.calls.append({"name": use.name, "input": dict(use.input), "output": output})
            results.append({"type": "tool_result", "tool_use_id": use.id, "content": output})
        messages.append({"role": "user", "content": results})
    return run


# ── OpenAI ──────────────────────────────────────────────────────────────────


def _openai_loop(system, user, tools, handlers, max_steps) -> ToolRun:
    import openai

    client = openai.OpenAI()
    name = model()
    messages: list[Any] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    request: dict[str, Any] = {"model": name, "max_completion_tokens": MAX_TOKENS}
    if tools:
        request["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                },
            }
            for t in tools
        ]
    run = ToolRun(text="")
    for _ in range(max_steps):
        started = time.monotonic()
        response = client.chat.completions.create(messages=messages, **request)
        message = response.choices[0].message
        text = (message.content or "").strip()
        run.replies.append(
            Reply(
                text=text,
                provider="openai",
                model=response.model,
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                latency_ms=(time.monotonic() - started) * 1000,
            )
        )
        run.text = text or run.text
        if not message.tool_calls:
            break
        messages.append(message)
        for call in message.tool_calls:
            arguments = json.loads(call.function.arguments or "{}")
            output = _call_tool(handlers, call.function.name, arguments)
            run.calls.append({"name": call.function.name, "input": arguments, "output": output})
            messages.append({"role": "tool", "tool_call_id": call.id, "content": output})
    return run

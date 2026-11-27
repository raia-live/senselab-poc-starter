"""Connecting to hosted SenseLab, and the few things every example does with it."""

from __future__ import annotations

import os
import secrets
import time
from typing import Any

from amfs import AgentMemory, MemoryEntry, ScoredEntry


def hosted(agent_id: str, api_key: str | None = None) -> AgentMemory:
    """A memory connected to the hosted service, or an error saying why not.

    ``AgentMemory.from_env`` reads ``AMFS_HTTP_URL`` and ``AMFS_API_KEY`` and
    raises when either is missing. Do not replace it with a bare
    ``AgentMemory(agent_id)``: that one ignores both variables and writes to a
    local ``.amfs/`` folder, so a run looks fine and the dashboard stays empty.

    Each call returns a new object with a new session, which is what "a fresh
    agent" means in these examples: nothing carries over except what is stored
    on the server.
    """
    try:
        # agent_id is the name shown in the dashboard. api_key, when given,
        # replaces AMFS_API_KEY (example 05 uses it for the guest).
        return AgentMemory.from_env(agent_id, api_key=api_key)
    except ValueError as exc:
        raise SystemExit(f"{exc}\nCopy .env.example to .env and fill it in.") from exc


def second_key() -> str:
    """The key from the other account in the room examples, or an error naming it."""
    key = (os.environ.get("AMFS_API_KEY_B") or "").strip()
    if not key:
        raise SystemExit(
            "AMFS_API_KEY_B is not set. This needs a second SenseLab API key "
            "created in a different account; add it to .env."
        )
    return key


def new_run_id() -> str:
    """A short id that keeps one run's memory apart from every other run's.

    There is no delete, so "reset" means "use a path nobody has written to".
    Every example puts its entries under a path that contains this id.
    """
    return secrets.token_hex(4)  # eight hex characters, e.g. "02a2573d"


def entry_ref(entry: MemoryEntry) -> str:
    """The ``entity_path/key`` form that ``commit_outcome`` takes for causal keys."""
    return f"{entry.entity_path}/{entry.key}"


def retrieve_until_found(
    mem: AgentMemory,
    query: str,
    *,
    entity_path: str,
    limit: int = 3,
    timeout: float = 20.0,
    interval: float = 2.0,
) -> list[ScoredEntry]:
    """``mem.retrieve`` on one exact path, retried for a few seconds while empty.

    For the case where the entry was written a moment ago by another process
    and is expected to be there. Every attempt is a real retrieve: it is
    counted as an operation and logged as a query in the session's trace. Use
    plain ``mem.retrieve`` when an empty result is a valid answer.
    """
    deadline = time.monotonic() + timeout
    while True:
        # entity_path limits the search to one exact path. limit caps the
        # number of entries returned.
        hits = mem.retrieve(query, entity_path=entity_path, limit=limit)
        # Stop as soon as something comes back, or when the time is up.
        if hits or time.monotonic() >= deadline:
            return hits
        time.sleep(interval)


def as_notes(hits: list[ScoredEntry]) -> str:
    """Retrieved entries as the bullet list that goes into a prompt."""
    return "\n".join(f"- {_text(hit.entry.value)}" for hit in hits)


def _text(value: Any) -> str:
    return value if isinstance(value, str) else repr(value)

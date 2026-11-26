"""00 - Am I connected to hosted SenseLab?

Writes one entry, reads it back, and says where it went. No LLM calls.

    uv run python examples/00_preflight/run.py
"""

from __future__ import annotations

import argparse
import os
from urllib.parse import urlparse

import httpx

from poc.memory import hosted, new_run_id

# ── CUSTOMIZE ───────────────────────────────────────────────────────────────
# The agent ids this check registers. An id belongs to the user who first
# used it, so the second key needs a different one.
AGENT_ID = "poc-preflight"
AGENT_ID_B = "poc-preflight-guest"
# Where the test entry goes. Every run writes under a new id.
PATH_PREFIX = "poc/preflight"
# ────────────────────────────────────────────────────────────────────────────


def check_first_key(path: str) -> None:
    """Write with the main key and read the entry back."""
    mem = hosted(AGENT_ID)
    host = urlparse(os.environ["AMFS_HTTP_URL"]).netloc
    print(f"service     {host}")
    print(f"agent       {mem.agent_id}")
    print(f"session     {mem.session_id}")

    written = mem.write(path, "hello", "preflight entry, safe to ignore", confidence=1.0)
    print(f"wrote       {written.entity_path}/{written.key} (version {written.version})")

    back = mem.read(path, "hello")
    if back is None or back.value != written.value:
        raise SystemExit("FAILED: the entry was written but did not read back.")
    print("read back   ok")


def check_second_key(path: str) -> None:
    """With ``AMFS_API_KEY_B`` set: can the second key see the first key's entry?

    Example 05 needs two keys that do NOT already share memory. If this one
    can read the entry above, both keys belong to the same user and a room
    would demonstrate nothing.
    """
    key_b = (os.environ.get("AMFS_API_KEY_B") or "").strip()
    if not key_b:
        print("second key  not set (only example 05 needs it)")
        return
    guest = hosted(AGENT_ID_B, api_key=key_b)
    seen = guest.read(path, "hello")
    if seen is None:
        print("second key  ok, and it cannot see the first key's entry: ready for example 05")
    else:
        print(
            "second key  ok, but it CAN see the first key's entry. Both keys share memory "
            "already; example 05 needs a key from a different user or account."
        )


def main() -> None:
    path = f"{PATH_PREFIX}/{new_run_id()}"
    try:
        check_first_key(path)
        check_second_key(path)
    except httpx.HTTPStatusError as exc:
        # The server's own explanation is in the message: a wrong key is a
        # 401, an agent id that belongs to another user is a 409.
        raise SystemExit(f"FAILED: {exc}") from exc
    except httpx.TransportError as exc:
        raise SystemExit(f"FAILED: could not reach {os.environ.get('AMFS_HTTP_URL')}: {exc}") from exc
    print("\nConnected. The entry is in your dashboard under", path)


if __name__ == "__main__":
    # No options; this makes --help print the summary without running anything.
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    main()

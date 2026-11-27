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
# The agent ids this check registers. Within one account an id belongs to
# the user who first used it, so the second key gets a different one in case
# both keys turn out to be from the same account.
AGENT_ID = "poc-preflight"
AGENT_ID_B = "poc-preflight-guest"
# Where the test entry goes. Every run writes under a new id.
PATH_PREFIX = "poc/preflight"
# ────────────────────────────────────────────────────────────────────────────


# ── Step 1: the main key ──────────────────────────────────────────────────────


def check_first_key(path: str) -> None:
    """Write with the main key and read the entry back."""
    # Connect. Exits with a clear message if AMFS_HTTP_URL or AMFS_API_KEY is
    # missing, so the script can never fall back to local storage.
    mem = hosted(AGENT_ID)
    host = urlparse(os.environ["AMFS_HTTP_URL"]).netloc
    print(f"service     {host}")
    print(f"agent       {mem.agent_id}")
    print(f"session     {mem.session_id}")

    # write(entity_path, key, value) stores one entry and returns it.
    written = mem.write(path, "hello", "preflight entry, safe to ignore", confidence=1.0)
    print(f"wrote       {written.entity_path}/{written.key} (version {written.version})")

    # read(entity_path, key) fetches one entry by its exact path and key.
    back = mem.read(path, "hello")
    if back is None or back.value != written.value:
        raise SystemExit("FAILED: the entry was written but did not read back.")
    print("read back   ok")


# ── Step 2 (optional): the second key, for example 05 ─────────────────────────


def check_second_key(path: str) -> None:
    """With ``AMFS_API_KEY_B`` set: can the second key see the first key's entry?

    Example 05 needs two keys that do NOT already share memory. If this one
    can read the entry above, both keys belong to the same account and a room
    would demonstrate nothing.
    """
    key_b = (os.environ.get("AMFS_API_KEY_B") or "").strip()
    if not key_b:
        print("second key  not set (only examples 05 and 07 need it)")
        return
    # Connect with the second key and try to read what the first key wrote.
    guest = hosted(AGENT_ID_B, api_key=key_b)
    seen = guest.read(path, "hello")
    if seen is None:
        print("second key  ok, and it cannot see the first key's entry: ready for examples 05 and 07")
    else:
        print(
            "second key  ok, but it CAN see the first key's entry. Both keys share memory "
            "already; examples 05 and 07 need a key from a different account."
        )


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    # A new path on every run, so runs never overwrite each other.
    path = f"{PATH_PREFIX}/{new_run_id()}"
    try:
        check_first_key(path)
        check_second_key(path)
    except httpx.HTTPStatusError as exc:
        # The server's own explanation is in the message: a wrong key is a
        # 401, an agent id that belongs to another user in the account is a 409.
        raise SystemExit(f"FAILED: {exc}") from exc
    except httpx.TransportError as exc:
        raise SystemExit(f"FAILED: could not reach {os.environ.get('AMFS_HTTP_URL')}: {exc}") from exc
    print("\nConnected. The entry is in your dashboard under", path)


if __name__ == "__main__":
    # No options; this makes --help print the summary without running anything.
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    main()

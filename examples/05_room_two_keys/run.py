"""05 - Two API keys, one room.

Two agents whose keys belong to different users cannot see each other's
memory. A room changes that for one topic: the host creates it and shares a
join link, the guest redeems the link, and from then on both read and write
the same entries and can message each other. No LLM calls.

    uv run python examples/05_room_two_keys/run.py
    uv run python examples/05_room_two_keys/run.py cleanup   # delete rooms a crashed run left open
"""

from __future__ import annotations

import argparse

import httpx
from amfs import AgentMemory

from poc.memory import entry_ref, hosted, new_run_id, retrieve_until_found, second_key

# ── CUSTOMIZE ───────────────────────────────────────────────────────────────
# AMFS_API_KEY is the host, AMFS_API_KEY_B the guest. The two ids differ so
# the output and the dashboard show which agent did what.
HOST_ID = "poc-host"
GUEST_ID = "poc-guest"

# The room shares exactly one topic: <prefix>/<run id>. Both agents must read
# and write that exact path. `cleanup` only touches rooms under this prefix.
TOPIC_PREFIX = "poc-room"

# What the join link grants, and for how long.
GUEST_ROLE = "collaborator"  # "viewer" joins read-only
LINK_MAX_USES = 2
LINK_EXPIRES_IN_DAYS = 1

QUERY = "How do I write a date on a shipping label?"
# ────────────────────────────────────────────────────────────────────────────


# ── The steps, in the order run() calls them ──────────────────────────────────


def step(number: int, text: str) -> None:
    """Print a numbered heading for one step."""
    print(f"\n{number}. {text}")


def guest_sees_nothing_yet(guest: AgentMemory, topic: str) -> None:
    """Before the room exists the guest's key cannot see the host's topic."""
    hits = guest.retrieve(QUERY, entity_path=topic, limit=3)
    print(f"   guest retrieves on {topic}: {[entry_ref(h.entry) for h in hits] or 'nothing'}")


def host_opens_room(host: AgentMemory, topic: str, run_id: str) -> str:
    """The host creates a room on the topic and writes a rule into it."""
    room = host.room_create(
        topic,
        name=f"POC handoff {run_id}",
        description="Created by the SenseLab POC starter, example 05.",
        discussions=True,  # messages are refused with a 403 unless this is on at creation
    )
    room_id = str(room["id"])
    print(f"   room {room_id} on topic {topic}")

    # An ordinary write. It is shared with the room because its path is the
    # room's topic. The run id in the text lets later steps check that they
    # received this run's entry.
    rule = f"Dates on shipping labels are written DDMMMYY in upper case, e.g. 03FEB26. (run {run_id})"
    host.write(topic, "rule", rule, confidence=0.9)
    print(f"   host wrote {topic}/rule")
    return room_id


def host_shares_link(host: AgentMemory, room_id: str) -> str:
    """A join link is how someone who is not in the room gets in."""
    link = host.room_share(
        room_id,
        role=GUEST_ROLE,
        max_uses=LINK_MAX_USES,
        expires_in_days=LINK_EXPIRES_IN_DAYS,
    )
    # The token is returned once and is a credential: do not print or log it.
    print(f"   join link created (role {link.get('role', GUEST_ROLE)}, max uses {link.get('max_uses')})")
    return link["token"]


def guest_joins(guest: AgentMemory, token: str) -> None:
    """Redeeming admits the guest's user; joining places this agent in the room."""
    redeemed = guest.room_redeem(token)  # the whole URL works too
    room_id = redeemed["room_id"]
    print(f"   guest redeemed the link: role {redeemed.get('role')}, already a member: {redeemed.get('already_member')}")
    membership = guest.room_join(room_id)
    print(f"   agent {membership.get('agent_id', guest.agent_id)} joined")


def guest_reads_the_rule(guest: AgentMemory, topic: str, run_id: str) -> None:
    """The same retrieve as step 1 now returns what the host wrote."""
    # The same query and path as step 1. Membership of the room is the only
    # thing that changed.
    hits = retrieve_until_found(guest, QUERY, entity_path=topic)
    values = [str(h.entry.value) for h in hits]
    print(f"   guest retrieves on {topic}: {values or 'nothing'}")
    # A 200 that reached nobody looks the same as success until you check.
    if not any(run_id in value for value in values):
        raise SystemExit("FAILED: the guest did not get this run's rule through the room.")


def guest_reports_back(guest: AgentMemory, room_id: str, topic: str, run_id: str) -> str:
    """The guest writes to the shared topic and messages the host."""
    # The guest writes to the shared topic with its own key.
    guest.write(topic, "finding", f"Used the label rule on 17 November 2026: 17NOV26. (run {run_id})")
    print(f"   guest wrote {topic}/finding")
    # A message in the room, addressed to the host's agent id.
    message = guest.room_discuss(
        room_id,
        f"Applied your label-date rule and wrote my result under 'finding'. (run {run_id})",
        addressed_to=HOST_ID,
    )
    print(f"   guest posted a message addressed to {HOST_ID}")
    return str(message["id"])


def host_reads_and_replies(host: AgentMemory, room_id: str, topic: str, run_id: str, message_id: str) -> None:
    """The host sees the guest's entry and message, and answers in the thread."""
    # The host reads the guest's entry with a plain read on the topic.
    finding = host.read(topic, "finding")
    print(f"   host reads {topic}/finding: {finding.value if finding else 'nothing'}")
    if finding is None or run_id not in str(finding.value):
        raise SystemExit("FAILED: the host did not get this run's finding through the room.")

    # Messages addressed to the host. The result is a dict; the messages
    # are under "items".
    inbox = host.room_discussions(room_id, addressed_to=HOST_ID).get("items", [])
    for item in inbox:
        print(f"   host's inbox: [{item.get('agent_id')}] {item.get('content')}")
    if not any(run_id in str(item.get("content")) for item in inbox):
        raise SystemExit("FAILED: the guest's message did not reach the host.")

    # reply_to makes this message a reply to the guest's message.
    host.room_discuss(room_id, "Got it, thanks.", reply_to=message_id, addressed_to=GUEST_ID)
    print(f"   host replied to {GUEST_ID}")


# ── The whole flow ────────────────────────────────────────────────────────────


def run() -> None:
    run_id = new_run_id()
    # The one path the room shares. Both agents read and write exactly this.
    topic = f"{TOPIC_PREFIX}/{run_id}"
    # Two memory objects, one per API key.
    host = hosted(HOST_ID)
    guest = hosted(GUEST_ID, api_key=second_key())
    print(f"run id: {run_id}")

    step(1, "Before the room")
    guest_sees_nothing_yet(guest, topic)

    room_id = None
    try:
        step(2, "Host creates the room and writes a rule")
        room_id = host_opens_room(host, topic, run_id)
        step(3, "Host shares a join link")
        token = host_shares_link(host, room_id)
        step(4, "Guest joins with the other key")
        guest_joins(guest, token)
        step(5, "Guest reads what the host wrote")
        guest_reads_the_rule(guest, topic, run_id)
        step(6, "Guest writes back and messages the host")
        message_id = guest_reports_back(guest, room_id, topic, run_id)
        step(7, "Host reads it and replies")
        host_reads_and_replies(host, room_id, topic, run_id, message_id)
    finally:
        # A Free account has one open room. Leaving this one open would make
        # the next run fail at step 2.
        if room_id:
            host.room_delete(room_id)
            print(f"\nroom {room_id} deleted")
    print("Both directions worked: host -> guest through memory, guest -> host through memory and messages.")


# ── Cleanup after a crashed run ───────────────────────────────────────────────


def cleanup() -> None:
    """Delete rooms this example created and a failed run left behind."""
    host = hosted(HOST_ID)
    # my_rooms lists the rooms the host is in. Keep those whose topic starts
    # with this example's prefix.
    mine = [
        room
        for room in host.my_rooms()
        if any(str(path).startswith(f"{TOPIC_PREFIX}/") for path in room.get("entity_paths") or [])
    ]
    if not mine:
        print(f"No rooms with a topic under {TOPIC_PREFIX}/.")
    for room in mine:
        host.room_delete(str(room["id"]))
        print(f"deleted room {room['id']} ({', '.join(room.get('entity_paths') or [])})")


# ── Command line ──────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("step", nargs="?", default="run", choices=["run", "cleanup"])
    args = parser.parse_args()
    try:
        cleanup() if args.step == "cleanup" else run()
    except httpx.HTTPStatusError as exc:
        # The message carries the server's reason: 402 is the plan's room
        # limit, 403 a role that may not do this, 409 a topic already shared.
        raise SystemExit(f"FAILED: {exc}") from exc


if __name__ == "__main__":
    main()

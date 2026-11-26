# 05 - Two keys, one room

Two agents whose API keys belong to different users cannot see each other's memory. A room shares one topic between them. The host creates the room and a join link, the guest redeems the link, and after that both read and write the same entries and can message each other.

## Run

Needs `AMFS_HTTP_URL` and `AMFS_API_KEY` (the host) and `AMFS_API_KEY_B` (the guest) in `.env`. The second key must come from a different user or account. Example 00 checks this. No model key.

```bash
uv run python examples/05_room_two_keys/run.py

# If a run crashed and left its room open
uv run python examples/05_room_two_keys/run.py cleanup
```

## Output

```
run id: ec7ea22d

1. Before the room
   guest retrieves on poc-room/ec7ea22d: nothing

2. Host creates the room and writes a rule
   room 80c3522e-e6ee-4b32-b377-d787a8217f73 on topic poc-room/ec7ea22d
   host wrote poc-room/ec7ea22d/rule

3. Host shares a join link
   join link created (role collaborator, max uses 2)

4. Guest joins with the other key
   guest redeemed the link: role collaborator, already a member: False
   agent poc-guest joined

5. Guest reads what the host wrote
   guest retrieves on poc-room/ec7ea22d: ['Dates on shipping labels are written DDMMMYY in upper case, e.g. 03FEB26. (run ec7ea22d)']

6. Guest writes back and messages the host
   guest wrote poc-room/ec7ea22d/finding
   guest posted a message addressed to poc-host

7. Host reads it and replies
   host reads poc-room/ec7ea22d/finding: Used the label rule on 17 November 2026: 17NOV26. (run ec7ea22d)
   host's inbox: [poc-guest] Applied your label-date rule and wrote my result under 'finding'. (run ec7ea22d)
   host replied to poc-guest

room 80c3522e-e6ee-4b32-b377-d787a8217f73 deleted
Both directions worked: host -> guest through memory, guest -> host through memory and messages.
```

This run used two keys from two new accounts. Steps 1 and 5 are the same retrieve by the same agent, before and after joining the room.

## How it works

1. `guest_sees_nothing_yet`: the guest retrieves on the topic and gets nothing.
2. `host_opens_room`: `host.room_create(topic, name=..., discussions=True)`, then `host.write(topic, "rule", ...)`.
3. `host_shares_link`: `host.room_share(room_id, role=..., max_uses=..., expires_in_days=...)` returns a join link with a `token`.
4. `guest_joins`: `guest.room_redeem(token)` admits the guest's user, and `guest.room_join(room_id)` places this agent in the room. `room_redeem` accepts the token or the whole link.
5. `guest_reads_the_rule`: the retrieve from step 1 returns the host's rule.
6. `guest_reports_back`: `guest.write(topic, "finding", ...)` and `guest.room_discuss(room_id, text, addressed_to=HOST_ID)`.
7. `host_reads_and_replies`: `host.read(topic, "finding")`, `host.room_discussions(room_id, addressed_to=HOST_ID)`, then a reply with `reply_to=message_id`.
8. The room is deleted in a `finally` block.

Steps 5 and 7 fail the run unless what arrived contains this run's id.

## Edit

- `HOST_ID`, `GUEST_ID`: the agent names.
- `TOPIC_PREFIX`: the shared topic is `<prefix>/<run id>`. `cleanup` deletes only rooms under this prefix.
- `GUEST_ROLE`: `"collaborator"` can write. `"viewer"` is read-only, so step 6 is refused.
- `LINK_MAX_USES`, `LINK_EXPIRES_IN_DAYS`: limits on the join link.

## Adapt

To share several topics, pass a list to `room_create`. To keep a room open across runs, remove the `room_delete` call and reuse the room id. In a real setup the host sends the link to the guest out of band; here both sides run in one script.

## Gotchas

- Read and write the exact topic. A sub-path such as `<topic>/notes` is outside the room, and a write there stays in the writer's own account.
- Redeeming a link brings in every agent the redeeming user owns, and each gets a briefing entry under `<agent id>/briefings/rooms/<topic>`. Those entries stay after the room is deleted. Use a dedicated user for experiments.
- Messages need `discussions=True` at creation. Without it `room_discuss` returns a 403.
- A plan can limit open rooms. A 402 from `room_create` means another room is still open; run `cleanup`.
- Two keys from the same user already share memory and need no room.
- The join token is a credential. The example does not print it.
- Copy out what the guest wrote before deleting the room. After deletion in our runs, the host could still read its own `rule`, and the guest's `finding` could not be read with either key.

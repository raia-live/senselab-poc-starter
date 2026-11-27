# Notes for coding agents

Read this before changing or running anything in this repository. The human-facing documentation is `README.md` and the `README.md` in each example folder.

## Running an example has side effects

Every `examples/*/run.py` connects to the hosted SenseLab service with the keys in `.env` and writes entries to a real account. Entries cannot be deleted through the SDK, so every run leaves something behind. Do not run an example to explore it. Ask the developer before a run that uses their keys, and say what it will write.

Checks that make no network call:

```bash
uv run python -m py_compile examples/07_readonly_case_experiment/run.py   # syntax
uv run python examples/07_readonly_case_experiment/run.py --help          # imports and arguments; exits before connecting
uvx ruff check .                                                           # lint
```

Every example accepts `--help` and exits before it connects.

## Rules

1. Connect only through `poc.memory.hosted()`, which calls `AgentMemory.from_env()`. Never write `AgentMemory(agent_id)`: it ignores `.env`, stores entries in a local `.amfs/` folder, and the run looks successful.
2. Never print, log, or save an API key or a room join token. In example 07 each case's row is written to `results/` as it is, so nothing secret may be added to it.
3. Never commit `.env` or anything under `results/`.
4. Pass `entity_path` on every `retrieve` that is meant for one case. The match is exact: a parent path or a sub-path is a different path.
5. Keep every room inside a `try` / `finally` that deletes it. A leftover room makes the next run fail with a 402 until `run.py cleanup` is run.
6. In example 07, Agent B stays read-only: no `write` by B apart from the one in `write_is_refused`, and no `commit_outcome` by B with causal keys. The control arm receives no memory object and no retrieved entries.
7. `poc/cases.py`, `poc/llm.py` and `poc/memory.py` are shared by all examples. To change one example, edit that example's `run.py`.
8. Do not change the pinned versions in `pyproject.toml` unless asked. The signatures below are for those versions.
9. Do not call an SDK method that is not listed below without checking that it exists (see "Checking a signature"). There is no method that deletes an entry.

## Where to customise

| Goal | Change |
| --- | --- |
| Settings of one example (agent ids, paths, limits, prompts) | the `CUSTOMIZE` block at the top of its `run.py` |
| The developer's own agent in example 07 | the body of `solve(task, notes)` in `examples/07_readonly_case_experiment/run.py`, then set `SOLVE_USES_BUILTIN_MODEL = False` |
| The developer's own tasks | `CASES` in `poc/cases.py`. All examples that use cases read this list. Example 07 matches per-case keys to cases by position |
| Another model provider for the built-in agents | `poc/llm.py` |
| How long a retrieve waits, how run ids are made | `poc/memory.py` |

Each example README has an "Edit" table for its settings and an "Adapt" list for larger changes.

## SDK calls the examples use

From `amfs` 0.5.44 with `amfs-adapter-http` 0.1.39. Only the parameters the examples pass are shown.

Connecting:

```python
AgentMemory.from_env(agent_id, *, base_url=None, api_key=None) -> AgentMemory
# Reads AMFS_HTTP_URL and AMFS_API_KEY. api_key replaces AMFS_API_KEY.
# Raises ValueError if the URL or the key is missing.
```

Entries:

```python
mem.write(entity_path, key, value, *, confidence=1.0) -> MemoryEntry
# Writing a key that exists adds a version. Nothing is overwritten or deleted.

mem.read(entity_path, key) -> MemoryEntry | None

mem.retrieve(query, *, entity_path=None, limit=10) -> list[ScoredEntry]
# Semantic search. With entity_path: that exact path only.
# Without it: everything the key can read, including the user's own briefings.

mem.search(*, entity_path=None, limit=100) -> list[MemoryEntry]
# Listing. Example 07 uses it with an exact entity_path.
```

A `MemoryEntry` has `entity_path`, `key`, `value`, `version`, `confidence` and `provenance.agent_id`. A `ScoredEntry` has `entry` (the `MemoryEntry`), `score` and `breakdown`.

Outcomes and traces (examples 01 and 03):

```python
mem.commit_outcome(outcome_ref, outcome_type, causal_entry_keys=None, *,
                   task_input=None, response_text=None, attributes=None,
                   entity_path=None, verified_by=None) -> list[MemoryEntry]
# outcome_type is an amfs.OutcomeType, e.g. OutcomeType.SUCCESS or OutcomeType.FAILURE.
# causal_entry_keys=None applies the outcome to every entry the session read,
# which changes their confidence. causal_entry_keys=[] changes no confidence.

mem.record_context(label, summary, *, source=None)
mem.record_action(tool_name, arguments=None, *, result="", success=True)
mem.record_llm_call(model, input_tokens, output_tokens, *, latency_ms=None, provider=None)
mem.list_traces(*, agent_id=None, limit=100) -> list[DecisionTrace]
mem.get_trace(trace_id) -> DecisionTrace | None
```

Rooms (examples 05 and 07). All return a `dict`.

```python
mem.room_create(topics, *, name=None, description=None, discussions=True)   # ["id"]
mem.room_share(room_id, *, role="collaborator", max_uses=None, expires_in_days=None)
# role is "collaborator" (read and write) or "viewer" (read only). ["token"] is the credential.
mem.room_redeem(token)        # token or the whole join link. ["room_id"], ["role"], ["already_member"]
mem.room_join(room_id)
mem.room_delete(room_id)
mem.my_rooms()                # a list of dicts with "id" and "entity_paths"
mem.room_discuss(room_id, content, *, addressed_to=None, reply_to=None)
mem.room_discussions(room_id, *, addressed_to=None)   # ["items"]
```

### Checking a signature

```bash
uv run python -c "import inspect, amfs; print(inspect.signature(amfs.AgentMemory.retrieve))"
```

## Errors

A failed call raises `httpx.HTTPStatusError`. The examples catch it in `main()` and exit with `FAILED: ...`.

| Status | Meaning in these examples |
| --- | --- |
| 401 | the API key is wrong or revoked |
| 402 | a plan limit. In examples 05 and 07: another room is still open, run `cleanup` |
| 403 with `room_read_only` in the body | a viewer tried to write to a room's path |
| 403 from `room_discuss` | the room was created with `discussions=False` |
| 409 | the agent id belongs to another user in the same account (give each user its own agent ids), or `room_create` was called on a path that already has a room |

## Users, keys and rooms

- An account has one or more users. Memory belongs to the user whose key wrote it. Keys created by the same user read the same memory.
- Keys created by different users see nothing of each other's memory, also when both users are in one account. A room shares one path between them.
- Within an account an agent id belongs to the user who used it first. The same id can be used in different accounts.
- Redeeming a join link admits the user who owns the key and brings in every agent that user owns.
- Joining a room saves a briefing with the room's entries in the joiner's own memory, under `<agent id>/briefings/rooms/<room path>`. It stays after the room is deleted. A `retrieve` without `entity_path` can return it.
- A write by a room guest to a path that is not in a room succeeds and lands in the guest's own memory. The host does not see it.
- Give each user its own paths. Two users should not write to the same path and key unless a room shares that path.
- All of this was observed with two users in separate accounts and with two users in one account.

## What has been run

- Run on hosted SenseLab: examples 00, 02 and 05, and example 07 with `--memory-only` and one reader user. Examples 00, 05 and 07 were run both with the second key from another account and with the second key from another user of the same account.
- Not run: the model calls in examples 01, 03, 04, 06 and 07. Example 07 with `AMFS_API_KEYS_B_PER_CASE` and separate users.

If you change code on a path that has not been run, say so in your summary to the developer.

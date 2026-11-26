# 00 - Preflight

Writes one entry to hosted SenseLab and reads it back. Run it before the other examples to confirm that your key works and that the SDK is using the hosted service.

## Run

Needs `AMFS_HTTP_URL` and `AMFS_API_KEY` in `.env`. No model key.

```bash
uv run python examples/00_preflight/run.py
```

## Output

```
service     amfs-login.sense-lab.ai
agent       poc-preflight
session     sess-23e88522
wrote       poc/preflight/5983d3dc/hello (version 1)
read back   ok
second key  not set (only example 05 needs it)

Connected. The entry is in your dashboard under poc/preflight/5983d3dc
```

The session id and path suffix change on every run. With `AMFS_API_KEY_B` set to a key from another account, the `second key` line reads `ok, and it cannot see the first key's entry: ready for example 05`.

## How it works

1. `check_first_key` connects with `hosted(AGENT_ID)`, a wrapper around `AgentMemory.from_env`. It exits with a message if either variable is missing.
2. It writes an entry under `poc/preflight/<run id>` and reads it back.
3. `check_second_key` runs when `AMFS_API_KEY_B` is set. It connects with that key and tries to read the first key's entry. Failing to read it is the expected result, because example 05 needs two keys that do not already share memory.

## Edit

`AGENT_ID` and `AGENT_ID_B` are the agent names shown in your dashboard. `PATH_PREFIX` is where the test entry is written.

## Adapt

`check_first_key` works as a startup check in your own harness: call it before an experiment to fail early on a bad key or a missing variable.

## Gotchas

- `AgentMemory(agent_id)` with no adapter stores entries in `.amfs/` on disk and ignores the environment variables. Use `AgentMemory.from_env(agent_id)`.
- `FAILED: 401` means the key is wrong or revoked.
- `FAILED: 409` means the agent id already belongs to another user in your account. Choose a different id.
- The test entry stays in your account. Entries cannot be deleted.

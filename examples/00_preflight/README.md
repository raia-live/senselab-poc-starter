# 00 - Preflight

Writes one entry to hosted SenseLab and reads it back. Run it before the other examples to confirm that your key works and that the SDK is using the hosted service.

## Before you run

- `.env` exists in the repository root with `AMFS_HTTP_URL` and `AMFS_API_KEY` (see the [setup steps](../../README.md#setup)).
- No model key is needed.
- Optional: `AMFS_API_KEY_B`, to check the second key that examples 05 and 07 use.

## Run

From the repository root:

```bash
uv run python examples/00_preflight/run.py
```

It makes one write and one read, and takes a few seconds.

## Output

```
service     amfs-login.sense-lab.ai
agent       poc-preflight
session     sess-23e88522
wrote       poc/preflight/5983d3dc/hello (version 1)
read back   ok
second key  not set (only examples 05 and 07 need it)

Connected. The entry is in your dashboard under poc/preflight/5983d3dc
```

How to read it:

- `service` is the host from `AMFS_HTTP_URL`. It should be the hosted service.
- `wrote` and `read back ok` mean the key can write and read.
- `Connected.` means every check passed.
- The session id and the path suffix change on every run.
- With `AMFS_API_KEY_B` set to a key from another account, the `second key` line reads `ok, and it cannot see the first key's entry: ready for examples 05 and 07`.

## How it works

1. `check_first_key` connects with `hosted(AGENT_ID)`, a wrapper around `AgentMemory.from_env`. It exits with a message if either variable is missing.
2. It writes an entry under `poc/preflight/<run id>` and reads it back.
3. `check_second_key` runs when `AMFS_API_KEY_B` is set. It connects with that key and tries to read the first key's entry. Failing to read it is the expected result, because example 05 needs two keys that do not already share memory.

## Edit

In the `CUSTOMIZE` block at the top of `run.py`:

| Setting | Meaning |
| --- | --- |
| `AGENT_ID` | agent name for the main key, shown in your dashboard |
| `AGENT_ID_B` | agent name for the second key |
| `PATH_PREFIX` | where the test entry is written |

## Adapt

`check_first_key` works as a startup check in your own harness: call it before an experiment to fail early on a bad key or a missing variable.

## Gotchas

- `AgentMemory(agent_id)` with no adapter stores entries in `.amfs/` on disk and ignores the environment variables. Use `AgentMemory.from_env(agent_id)`.
- `FAILED: 401` means the key is wrong or revoked.
- `FAILED: 409` means the agent id already belongs to another user in your account. Choose a different id.
- The test entry stays in your account. Entries cannot be deleted.

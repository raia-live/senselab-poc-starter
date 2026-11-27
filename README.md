# SenseLab POC starter

Eight runnable examples for a first SenseLab memory experiment. One agent learns a rule and saves it. A second agent, starting fresh, is graded on the same kind of task with that memory and without it.

Each example is a folder with a `run.py` and a `README.md`. The only shared code is three small modules in `poc/`.

## What you need

- Python 3.11 or later.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) to install dependencies and run the scripts. `pip` works too (see step 2).
- A SenseLab account and an API key (step 3).
- For examples 01, 03, 04 and 06: a model API key from Anthropic or OpenAI. Example 07 needs one too, except with `--memory-only` or with your own agent.
- For examples 05 and 07: a second SenseLab API key created by a different user. The user can be in your account or in another one.
- For example 06: the Claude Code CLI.

## Setup

1. Clone the repository.

   ```bash
   git clone https://github.com/raia-live/senselab-poc-starter.git
   cd senselab-poc-starter
   ```

2. Install the dependencies. With `uv` there is nothing to do: `uv run` installs them on first use. With `pip`:

   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -e .
   ```

   If you use `pip`, replace `uv run python` with `python` in every command below.

3. Create a SenseLab API key. Sign in at https://amfs.sense-lab.ai (new accounts confirm their email first), open Settings, then API Keys, and create a key of type Agent. Copy it when it is shown. It starts with `amfs_`.

4. Create your `.env` file and paste the key into it.

   ```bash
   cp .env.example .env
   ```

   ```bash
   # .env
   AMFS_HTTP_URL=https://amfs-login.sense-lab.ai
   AMFS_API_KEY=amfs_your_key_here
   ```

5. Check the connection.

   ```bash
   uv run python examples/00_preflight/run.py
   ```

   The last line should start with `Connected.` If it does not, see [Troubleshooting](#troubleshooting).

Run every command from the repository root. Each script loads `.env` when it starts. A variable already set in your shell takes precedence over the file.

## Environment variables

All of them go in `.env`. `.env.example` lists them with comments.

| Variable | Needed for | Value |
| --- | --- | --- |
| `AMFS_HTTP_URL` | all examples | `https://amfs-login.sense-lab.ai` (already in `.env.example`) |
| `AMFS_API_KEY` | all examples | your SenseLab API key |
| `AMFS_API_KEY_B` | 05, 07, and optionally 00 | a second SenseLab key created by a different user, in your account or another |
| `AMFS_API_KEYS_B_PER_CASE` | 07, optional | comma-separated keys, one user per case. Replaces `AMFS_API_KEY_B` in 07 |
| `ANTHROPIC_API_KEY` | 01, 03, 04, 06, and 07 with the built-in agent | an Anthropic API key. 06 works only with this one |
| `OPENAI_API_KEY` | 01, 03, 04, and 07 with the built-in agent | use in place of the Anthropic key. Also set `POC_MODEL` |
| `POC_MODEL` | 01, 03, 04 | model name. Optional with Anthropic (default `claude-sonnet-5-5`), required with OpenAI |

If both model keys are set, Anthropic is used.

## Examples

Run them in order. Every command accepts `--help`.

| Example | Shows | Command | Run on hosted SenseLab |
| --- | --- | --- | --- |
| [00_preflight](examples/00_preflight) | The SDK reaches the hosted service with your key | `uv run python examples/00_preflight/run.py` | yes |
| [01_memory_handoff](examples/01_memory_handoff) | Agent A saves a rule; Agent B is graded with and without it | `uv run python examples/01_memory_handoff/run.py` | not yet |
| [02_isolation_and_control](examples/02_isolation_and_control) | Keeping test cases apart, and what a reset is | `uv run python examples/02_isolation_and_control/run.py` | yes |
| [03_inspect_traces](examples/03_inspect_traces) | What a trace stores by default and what you have to pass | `uv run python examples/03_inspect_traces/run.py` | not yet |
| [04_agent_memory_tools](examples/04_agent_memory_tools) | The model searches and writes memory itself, through tools | `uv run python examples/04_agent_memory_tools/run.py` | not yet |
| [05_room_two_keys](examples/05_room_two_keys) | Two agents on different API keys share memory and messages through a room | `uv run python examples/05_room_two_keys/run.py` | yes |
| [06_claude_code_headless](examples/06_claude_code_headless) | The handoff experiment with headless Claude Code | `uv run python examples/06_claude_code_headless/run.py` | not yet |
| [07_readonly_case_experiment](examples/07_readonly_case_experiment) | The handoff experiment with Agent B as another user, read-only, one case at a time, and a control with no memory | `uv run python examples/07_readonly_case_experiment/run.py` | memory steps yes, model steps not yet |

The READMEs for 00, 02 and 05 show real output, and so does the one for 07 for its memory steps. The model calls in 01, 03, 04, 06 and 07 have not been run end to end yet. Their READMEs show that output format with placeholders.

If Agent B must be limited by the server to reading one case, start with 07. If both agents can share one key, start with 01.

Each example README has the same sections: what it needs, how to run it, the output and how to read it, how the code works, what to edit, how to adapt it, and known gotchas.

## Connecting

Use `AgentMemory.from_env(agent_id)`. The examples call it through `poc.memory.hosted()`.

```python
from amfs import AgentMemory

mem = AgentMemory.from_env("my-agent")                # reads AMFS_HTTP_URL and AMFS_API_KEY
mem.write("my-experiment/run-1/case-1", "rule", "Dates are written DDMMMYY.")
hits = mem.retrieve("How do I write a date?", entity_path="my-experiment/run-1/case-1")
```

`AgentMemory(agent_id)` with no adapter ignores `AMFS_HTTP_URL` and `AMFS_API_KEY` and stores entries in a local `.amfs/` folder. The script runs without error and nothing appears in your dashboard.

## Common questions

Does Agent B need a room to read what Agent A wrote?

No, if both use keys created by the same user. Entries are shared between one user's agents, and B finds A's entry by retrieving on the same `entity_path` ([01](examples/01_memory_handoff)). A room is needed when the keys belong to different users, whether or not they are in the same account ([05](examples/05_room_two_keys)).

Can Agent B be limited to reading one case, with no write access?

Yes, when B's key was created by a different user from A's. Both users can be in the same account. A opens a room on the case's path and shares a join link with the viewer role. B can then read that path and nothing else of A's, and the server refuses B's writes ([07](examples/07_readonly_case_experiment)).

How do we isolate cases, reset memory, and run a control without memory?

Give each case and each run its own `entity_path` and pass it to every `retrieve`. Entries cannot be deleted, so a reset is a new path. The control arm never creates a memory object ([02](examples/02_isolation_and_control)).

What do traces capture?

Committing an outcome stores a trace of the session: its queries, the entries it read, and timing. To see what an agent retrieved without committing anything, save the return value of `retrieve` ([07](examples/07_readonly_case_experiment)). Prompts, responses, actions and model usage are stored only if you pass them ([03](examples/03_inspect_traces)). For retention and deletion terms, ask your SenseLab contact.

Is the setup different with headless Claude Code?

Claude Code connects through the SenseLab MCP server, and the Python SDK is not involved. The memory is the same ([06](examples/06_claude_code_headless)).

## Adapting the examples

| File | What it holds | Change it to |
| --- | --- | --- |
| `examples/*/run.py`, `CUSTOMIZE` block | agent ids, paths, prompts, limits | rename agents, move entries, reword prompts |
| `poc/cases.py` | three test cases with expected answers, shared by 01, 03, 04, 06 and 07 | use your own tasks |
| `examples/07_readonly_case_experiment/run.py`, `solve()` | the agent both arms of example 07 call | call your own agent |
| `poc/llm.py` | the model client: `complete()` and `run_with_tools()` | call your own agent or another provider |
| `poc/memory.py` | `hosted()`, `new_run_id()`, `retrieve_until_found()` | change how runs are named or how long a retrieve waits |

If a coding agent is making the changes, point it at [AGENTS.md](AGENTS.md) first. It lists what must not be changed, the SDK calls the examples use, and how to check an edit without running against the service.

The SenseLab SDK versions are pinned in `pyproject.toml`, and `uv.lock` records every dependency the examples were run with.

Every run writes under a path containing a new run id, so runs do not collide. Old entries stay in your account. Results are written to `results/`, which is gitignored.

## Troubleshooting

| Message | Cause | Fix |
| --- | --- | --- |
| `Copy .env.example to .env and fill it in.` | `AMFS_HTTP_URL` or `AMFS_API_KEY` is missing | create `.env` (setup step 4) |
| `FAILED: ... 401 ...` | the SenseLab key is wrong or revoked | create a new key and update `.env` |
| `FAILED: could not reach ...` | wrong `AMFS_HTTP_URL`, or no network | use the URL from `.env.example` |
| `Set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env` | no model key | add one |
| `Set POC_MODEL in .env` | OpenAI key without a model name | add `POC_MODEL` |
| `AMFS_API_KEY_B is not set` | examples 05 and 07 need a second key | see the [05 README](examples/05_room_two_keys) |
| `FAILED: ... 402 ...` in example 05 or 07 | a room from an earlier run is still open | run that example with `cleanup`, e.g. `uv run python examples/05_room_two_keys/run.py cleanup` |
| ``FAILED: `claude` is not on PATH.`` | Claude Code is not installed | see the [06 README](examples/06_claude_code_headless) |
| a `.amfs/` folder appears | a script built `AgentMemory(...)` without `from_env` | use `AgentMemory.from_env(...)` and delete the folder |

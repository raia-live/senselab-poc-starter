# SenseLab POC starter

Seven runnable examples for a first SenseLab memory experiment. One agent learns a rule and saves it. A second agent, starting fresh, is graded on the same kind of task with that memory and without it.

Each example is a folder with a `run.py` and a `README.md`. The only shared code is three small modules in `poc/`.

## Setup

```bash
git clone https://github.com/raia-live/senselab-poc-starter.git
cd senselab-poc-starter
cp .env.example .env    # add your AMFS_API_KEY
uv run python examples/00_preflight/run.py
```

Without `uv`: `python -m venv .venv && source .venv/bin/activate && pip install -e .`, then run the scripts with `python`. Python 3.11 or later.

API keys are created in the SenseLab dashboard under Settings, API Keys. Once preflight prints `Connected.`, the other examples can run.

## Examples

| Example | Shows | Needs | Run on hosted SenseLab |
| --- | --- | --- | --- |
| [00_preflight](examples/00_preflight) | The SDK reaches the hosted service with your key | SenseLab key | yes |
| [01_memory_handoff](examples/01_memory_handoff) | Agent A saves a rule; Agent B is graded with and without it | SenseLab key, model key | not yet |
| [02_isolation_and_control](examples/02_isolation_and_control) | Keeping test cases apart, and what a reset is | SenseLab key | yes |
| [03_inspect_traces](examples/03_inspect_traces) | What a trace stores by default and what you have to pass | SenseLab key, model key | not yet |
| [04_agent_memory_tools](examples/04_agent_memory_tools) | The model searches and writes memory itself, through tools | SenseLab key, model key | not yet |
| [05_room_two_keys](examples/05_room_two_keys) | Two agents on different API keys share memory and messages through a room | Two SenseLab keys | yes |
| [06_claude_code_headless](examples/06_claude_code_headless) | The handoff experiment with headless Claude Code | SenseLab key, Anthropic key, `claude` CLI | not yet |

The READMEs for 00, 02 and 05 show real output. The four examples that call a model have not been run end to end yet, so their READMEs describe the output without a sample.

## Connecting

Use `AgentMemory.from_env(agent_id)`. The examples call it through `poc.memory.hosted()`.

`AgentMemory(agent_id)` with no adapter ignores `AMFS_HTTP_URL` and `AMFS_API_KEY` and stores entries in a local `.amfs/` folder. The script runs without error and nothing appears in your dashboard.

## Common questions

Does Agent B need a room to read what Agent A wrote?

No, if both use the same API key. Entries are shared between agents on a key, and B finds A's entry by retrieving on the same `entity_path` ([01](examples/01_memory_handoff)). A room is needed when the keys belong to different users ([05](examples/05_room_two_keys)).

How do we isolate cases, reset memory, and run a control without memory?

Give each case and each run its own `entity_path` and pass it to every `retrieve`. Entries cannot be deleted, so a reset is a new path. The control arm never creates a memory object ([02](examples/02_isolation_and_control)).

What do traces capture?

Committing an outcome stores a trace of the session: its queries, the entries it read, and timing. Prompts, responses, actions and model usage are stored only if you pass them ([03](examples/03_inspect_traces)). For retention and deletion terms, ask your SenseLab contact.

Is the setup different with headless Claude Code?

Claude Code connects through the SenseLab MCP server, and the Python SDK is not involved. The memory is the same ([06](examples/06_claude_code_headless)).

## Adapting the examples

- Each `run.py` starts with a `CUSTOMIZE` block holding its agent ids, paths, prompts and limits.
- `poc/cases.py` holds the three test cases. Replace them with your own tasks and expected answers.
- `poc/llm.py` is the model client. It uses Anthropic when `ANTHROPIC_API_KEY` is set, otherwise OpenAI with `OPENAI_API_KEY` and `POC_MODEL`. To plug in your own agent, replace `complete()` and `run_with_tools()`.
- `poc/memory.py` holds the connection helper.

Every run writes under a path containing a new run id, so runs do not collide. Old entries stay in your account. Results are written to `results/`, which is gitignored.

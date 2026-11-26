# 04 - Agent-driven memory

In example 01 the script retrieves from SenseLab and pastes the result into the prompt. Here the model gets two tools, `memory_search` and `memory_write`, and chooses when to call them. The result tells you whether the agent uses memory unprompted, as well as whether memory helps.

## Run

Needs `AMFS_HTTP_URL`, `AMFS_API_KEY`, and a key for a model that supports tool use: `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY` with `POC_MODEL`.

```bash
uv run python examples/04_agent_memory_tools/run.py                    # all cases
uv run python examples/04_agent_memory_tools/run.py --case label-date  # one case
```

Each case runs four model conversations of a few turns each.

## Output

This example has not been run end to end yet, so there is no sample here. For each case it prints Agent A's tool calls, then `PASS` or `FAIL` for Agent B with tools (and its tool calls) and for Agent B without tools. Full answers go to `results/`.

## How it works

1. `memory_tools` builds the two tool handlers for one agent on one case. The model supplies the query, key and value. The handler supplies the `entity_path`, so the model cannot reach another case.
2. `agent_a` runs two conversations. The model first attempts the task with the tools available. It is then shown its answer with the grader's feedback and left to decide whether to call `memory_write`.
3. `agent_b_with_tools` is a new session on a second task with the same tools.
4. `agent_b_control` is the same model and task with no tools.
5. `run_with_tools` in `poc/llm.py` is the loop: call the model, run the tools it asked for, return the results, and stop when it answers or after `MAX_STEPS` rounds.

## Edit

- `TOOLS`: the names, descriptions and schemas the model sees. The descriptions have the most effect on how often the tools are called.
- `SYSTEM`: the only place the prompt mentions shared memory. Try removing that mention.
- `MAX_STEPS`, `SEARCH_LIMIT`: loop and retrieval limits.

## Adapt

To add your own tool, append it to `TOOLS` and add a handler with the same name to the dict that `memory_tools` returns. If your agent framework has its own tool loop, keep the two handlers and drop `run_with_tools`.

## Gotchas

- The model may never write or never search. Read the printed tool calls before the pass rates.
- If Agent B passes without calling `memory_search`, it guessed.
- Keep `entity_path` in the handler. If the model chooses the path, one case can read another's rule.
- The model chooses the keys, so two runs can save the same rule under different keys. Find entries with `retrieve`; a lookup by fixed key will miss them.

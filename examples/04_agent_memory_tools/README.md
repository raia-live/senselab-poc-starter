# 04 - Agent-driven memory

In example 01 the script retrieves from SenseLab and pastes the result into the prompt. Here the model gets two tools, `memory_search` and `memory_write`, and chooses when to call them. The result tells you whether the agent uses memory unprompted, as well as whether memory helps.

## Before you run

- Example 00 prints `Connected.`
- `.env` has a key for a model that supports tool use: `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY` together with `POC_MODEL`.

## Run

From the repository root:

```bash
uv run python examples/04_agent_memory_tools/run.py                    # all three cases
uv run python examples/04_agent_memory_tools/run.py --case label-date  # one case
```

The case ids are `invoice-ref`, `label-date` and `ticket-queue`. Each case runs four model conversations of a few turns each. Start with one case.

## Output

This example has not been run end to end yet. The format below comes from the code, with placeholders in angle brackets.

```
run id: <run id>

label-date
  Agent A        ['memory_search({"query": "..."})', 'memory_write({"key": "...", "value": "..."})']
  Agent B tools  <PASS or FAIL>  ['memory_search({"query": "..."})']
  Agent B bare   <PASS or FAIL>

full answers in results/04_agent_memory_tools-<run id>.json
```

How to read it:

- The lists are the tool calls each agent made, in order. `made no tool calls` appears when there were none.
- The handoff worked when Agent A called `memory_write`, Agent B called `memory_search`, and `Agent B tools` passed.
- `Agent B bare` is the control: the same model with no tools.
- If Agent B passes without calling `memory_search`, it guessed.

## How it works

1. `memory_tools` builds the two tool handlers for one agent on one case. The model supplies the query, key and value. The handler supplies the `entity_path`, so the model cannot reach another case.
2. `agent_a` runs two conversations. The model first attempts the task with the tools available. It is then shown its answer with the grader's feedback and left to decide whether to call `memory_write`.
3. `agent_b_with_tools` is a new session on a second task with the same tools.
4. `agent_b_control` is the same model and task with no tools.
5. `run_with_tools` in `poc/llm.py` is the loop: call the model, run the tools it asked for, return the results, and stop when it answers or after `MAX_STEPS` rounds.

## Edit

In the `CUSTOMIZE` block at the top of `run.py`:

| Setting | Meaning |
| --- | --- |
| `WRITER_ID`, `SOLVER_ID` | agent names |
| `PATH_PREFIX` | entries go under `<prefix>/<run id>/<case id>` |
| `MAX_STEPS` | how many model turns one attempt may take |
| `SEARCH_LIMIT` | how many entries `memory_search` returns |
| `TOOLS` | the names, descriptions and schemas the model sees. The descriptions have the most effect on how often the tools are called |
| `SYSTEM` | the prompt with tools. It is the only place shared memory is mentioned. Try removing that mention |
| `SYSTEM_NO_TOOLS` | the prompt for the control arm |

## Adapt

- Your own tool: append it to `TOOLS` and add a handler with the same name to the dict that `memory_tools` returns.
- Your own agent framework: keep the two handlers in `memory_tools`, register them as tools in your framework, and drop `run_with_tools`.
- Your own tasks: edit `CASES` in `poc/cases.py`.

## Gotchas

- The model may never write or never search. Read the printed tool calls before the pass rates.
- Keep `entity_path` in the handler. If the model chooses the path, one case can read another's rule.
- The model chooses the keys, so two runs can save the same rule under different keys. Find entries with `retrieve`; a lookup by fixed key will miss them.

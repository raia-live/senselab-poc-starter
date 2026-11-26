# 03 - Inspect traces

Solves the same task in two sessions. The first ends with the shortest possible commit. The second records everything the SDK accepts. Both traces are then fetched and printed field by field, so you can see what SenseLab stores by default and what it stores only when you pass it.

## Run

Needs `AMFS_HTTP_URL`, `AMFS_API_KEY`, and a model key: `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY` with `POC_MODEL`.

```bash
uv run python examples/03_inspect_traces/run.py
```

Two short model calls.

## Output

This example has not been run end to end yet, so there is no sample here. It prints two blocks, one per trace. Each lists the outcome, `task_input`, `response_text`, session timing, entries read, queries, external contexts, actions and session metadata. Empty fields are marked.

## How it works

1. `seed_rule` writes the rule both sessions read.
2. `solve` is the same for both sessions: retrieve on the case path, ask the model, grade the answer.
3. `bare_session` ends with `commit_outcome(ref, outcome)` and passes nothing else.
4. `full_session` first calls `record_context(...)` for something learned outside SenseLab, `record_action(...)` for something the agent did, and `record_llm_call(...)` for model usage. It then passes `task_input`, `response_text`, `verified_by` and `attributes` to `commit_outcome`.
5. `fetch_trace` finds each trace by its outcome reference with `list_traces(agent_id=...)` and loads it with `get_trace(id)`.
6. `describe` prints the fields.

Stored without asking: the session id and timing, each query with its parameters and result count, and the entries credited with the outcome.

Stored only if you pass it: the prompt (`task_input`), the answer (`response_text`), external contexts, actions, model usage, and your own attributes.

## Edit

`CASE_ID` picks the case from `poc/cases.py`. `ATTRIBUTES` holds your own labels, such as experiment name or arm, for filtering traces later.

## Adapt

In `full_session`, delete any `record_*` call or `commit_outcome` argument and compare the trace. To log your own tool calls, add a `record_action` call next to each one.

## Gotchas

- Prompts and responses are stored only when you pass `task_input` and `response_text`.
- `record_*` calls are held in the session until the next `commit_outcome`. Without a commit there is no trace.
- SenseLab sees its own calls only. Your tool calls and model calls appear on a trace when you record them.
- The bare commit applies the outcome to every entry the session read, which changes their confidence. Pass `causal_entry_keys=[]` to prevent that; the trace then lists no entries.

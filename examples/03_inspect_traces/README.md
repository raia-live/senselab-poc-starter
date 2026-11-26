# 03 - Inspect traces

Solves the same task in two sessions. The first ends with the shortest possible commit. The second records everything the SDK accepts. Both traces are then fetched and printed field by field, so you can see what SenseLab stores by default and what it stores only when you pass it.

## Before you run

- Example 00 prints `Connected.`
- `.env` has a model key: `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY` together with `POC_MODEL`.

## Run

From the repository root:

```bash
uv run python examples/03_inspect_traces/run.py
```

It makes 1 write, 2 retrieves, 2 outcome commits, a few trace reads and 2 short model calls.

## Output

This example has not been run end to end yet. The format below comes from the code, with placeholders in angle brackets.

```
run id: <run id>

── bare commit: commit_outcome(ref, outcome) ────────────────
  outcome            poc-traces-<run id>-bare -> <outcome>
  task_input         (not stored)
  response_text      (not stored)
  session            <session id>, <n> ms
  entries read       <n>
    poc/traces/<run id>/label-date/rule v1 confidence <c>: <the rule>
  queries            <n>
    <operation> {<parameters>} -> <n> result(s)
  external contexts  0
  actions            0
  session metadata   <JSON, or (empty)>

── full commit: record_* calls, task_input, response_text, attributes ──
  outcome            poc-traces-<run id>-full -> <outcome>
  task_input         <the task>
  response_text      <the model's answer>
  ...
  external contexts  1
    grader: expected 17NOV26 (source: poc/cases.py)
  actions            1
    submit_answer({"case": "label-date"}) -> <the model's answer>
  session metadata   <JSON with model usage and your attributes>
```

How to read it:

- Compare the two blocks line by line. Anything filled in the second and empty in the first is stored only when you pass it.
- `(not stored)` marks a field the session never sent.
- `no trace found for this commit` means the trace did not appear within 20 seconds. Run the example again.

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

In the `CUSTOMIZE` block at the top of `run.py`:

| Setting | Meaning |
| --- | --- |
| `WRITER_ID`, `SOLVER_ID` | agent names |
| `PATH_PREFIX` | entries go under `<prefix>/<run id>/<case id>` |
| `CASE_ID` | which case from `poc/cases.py` to run |
| `ATTRIBUTES` | your own labels, such as experiment name or arm, for filtering traces later |
| `SOLVER_SYSTEM` | the prompt |

## Adapt

- To see the effect of one field, delete a `record_*` call or a `commit_outcome` argument in `full_session` and run again.
- To log your own tool calls, add a `record_action` call next to each one.
- To read traces in your own code, copy `fetch_trace`. It needs the outcome reference you passed to `commit_outcome`.

## Gotchas

- Prompts and responses are stored only when you pass `task_input` and `response_text`.
- `record_*` calls are held in the session until the next `commit_outcome`. Without a commit there is no trace.
- SenseLab sees its own calls only. Your tool calls and model calls appear on a trace when you record them.
- The bare commit applies the outcome to every entry the session read, which changes their confidence. Pass `causal_entry_keys=[]` to prevent that; the trace then lists no entries.

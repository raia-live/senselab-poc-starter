# 01 - Memory handoff

Agent A gets a task wrong, is told why, and saves the rule to SenseLab. Agent B, in a new session, is graded on a different task that needs the same rule: once with no memory (control) and once after retrieving from SenseLab (treatment). Both agents use one API key, so no room is involved.

## Run

Needs `AMFS_HTTP_URL`, `AMFS_API_KEY`, and a model key: `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY` with `POC_MODEL`.

```bash
uv run python examples/01_memory_handoff/run.py

# The two halves as separate processes
uv run python examples/01_memory_handoff/run.py write --run-id demo1
uv run python examples/01_memory_handoff/run.py eval  --run-id demo1
```

The three built-in cases make 9 short model calls.

## Output

This example has not been run end to end yet, so there is no sample here. It prints one line per case with the control result, the treatment result and the entries retrieved, followed by totals. Full answers go to `results/01_memory_handoff-<run id>.json`.

## How it works

1. `agent_a_writes` shows the model each task with the grader's feedback and asks for a one-sentence rule. It saves the rule with `writer.write(path, "rule", rule, confidence=0.9)` under `poc/handoff/<run id>/<case id>`.
2. `agent_b_control` sends the new task to the model. No memory object exists in this arm.
3. `agent_b_treatment` creates a new memory object, calls `retrieve(task, entity_path=path, limit=3)`, and adds the hits to the prompt.
4. `poc/cases.py` grades the last line of each answer by string match.
5. The treatment arm ends with `commit_outcome(...)`, which stores a trace. It passes `causal_entry_keys=[]` so the outcome does not change the rule's confidence between runs.

## Edit

In the `CUSTOMIZE` block of `run.py`:

- `SOLVER_SYSTEM`, `DISTIL_SYSTEM`: the prompts.
- `RETRIEVE_LIMIT`: how many entries are added to Agent B's prompt.
- `OUTCOMES_MOVE_CONFIDENCE`: set to `True` to apply each outcome to the retrieved entries, as you would in production.
- `PATH_PREFIX`, `WRITER_ID`, `SOLVER_ID`: entry paths and agent names.

## Adapt

Put your own tasks in `poc/cases.py`. A case has a task Agent A fails, the grader's feedback, a second task for Agent B, and the expected answer. To test your own agent, replace the `complete()` calls in `agent_a_writes` and the two `agent_b_*` functions.

## Gotchas

- `commit_outcome(ref, outcome)` without `causal_entry_keys` applies the outcome to every entry the session read. Pass `causal_entry_keys=[]` to leave confidence unchanged.
- With `causal_entry_keys=[]`, the trace records the query and lists no entries.
- Choose rules the model cannot guess, or the control arm will pass.
- `retrieve_until_found` retries for up to 20 seconds when a retrieve returns nothing. Call `retrieve` directly if an empty result is valid in your experiment.

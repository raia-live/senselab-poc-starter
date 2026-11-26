# 01 - Memory handoff

Agent A gets a task wrong, is told why, and saves the rule to SenseLab. Agent B, in a new session, is graded on a different task that needs the same rule: once with no memory (control) and once after retrieving from SenseLab (treatment). Both agents use one API key, so no room is involved.

## Before you run

- Example 00 prints `Connected.`
- `.env` has a model key: `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY` together with `POC_MODEL`.

## Run

From the repository root:

```bash
uv run python examples/01_memory_handoff/run.py
```

This runs both halves: Agent A writes, then Agent B is graded. The three built-in cases make 9 short model calls.

To run the halves as separate processes, pass the same run id to both. Nothing is shared between them except what is stored in SenseLab.

```bash
uv run python examples/01_memory_handoff/run.py write --run-id demo1
uv run python examples/01_memory_handoff/run.py eval  --run-id demo1
```

## Output

This example has not been run end to end yet. The format below comes from the code, with placeholders in angle brackets.

```
run id: <run id>

Agent A (poc-writer) writes one rule per case

  invoice-ref: saved poc/handoff/<run id>/invoice-ref/rule
    <the rule the model wrote>
  ...

Agent B, graded on a new instance of each task

  invoice-ref   control <PASS or FAIL>   treatment <PASS or FAIL>   retrieved [<entries>]
  label-date    ...
  ticket-queue  ...

  control <n>/3   treatment <n>/3
  full answers in results/01_memory_handoff-<run id>.json
```

How to read it:

- The handoff worked for a case when treatment passes and `retrieved` lists Agent A's entry.
- A control pass means the model guessed the rule. Make the rule harder to guess.
- `retrieved nothing` means the retrieve used a different path from the write.
- The JSON file holds every answer, so you can see why a case failed.

## How it works

1. `agent_a_writes` shows the model each task with the grader's feedback and asks for a one-sentence rule. It saves the rule with `writer.write(path, "rule", rule, confidence=0.9)` under `poc/handoff/<run id>/<case id>`.
2. `agent_b_control` sends the new task to the model. No memory object exists in this arm.
3. `agent_b_treatment` creates a new memory object, calls `retrieve(task, entity_path=path, limit=3)`, and adds the hits to the prompt.
4. `poc/cases.py` grades the last line of each answer by string match.
5. The treatment arm ends with `commit_outcome(...)`, which stores a trace. It passes `causal_entry_keys=[]` so the outcome does not change the rule's confidence between runs.

## Edit

In the `CUSTOMIZE` block at the top of `run.py`:

| Setting | Meaning |
| --- | --- |
| `WRITER_ID`, `SOLVER_ID` | agent names shown in your dashboard |
| `PATH_PREFIX` | entries go under `<prefix>/<run id>/<case id>` |
| `RETRIEVE_LIMIT` | how many entries are added to Agent B's prompt |
| `RULE_CONFIDENCE` | confidence Agent A gives its rule, from 0 to 1 |
| `OUTCOMES_MOVE_CONFIDENCE` | `True` applies each outcome to the retrieved entries, as you would in production |
| `SOLVER_SYSTEM`, `DISTIL_SYSTEM` | the prompts for solving and for writing the rule |

## Adapt

- Your own tasks: edit `CASES` in `poc/cases.py`. A case has a task Agent A fails, the grader's feedback, a second task for Agent B, and the expected answer.
- Your own agent: replace the `complete()` calls in `agent_a_writes`, `agent_b_control` and `agent_b_treatment` with a call to your agent. Keep the `write`, `retrieve` and `commit_outcome` calls.
- Your own grader: change `Case.check` in `poc/cases.py`.

## Gotchas

- `commit_outcome(ref, outcome)` without `causal_entry_keys` applies the outcome to every entry the session read. Pass `causal_entry_keys=[]` to leave confidence unchanged.
- With `causal_entry_keys=[]`, the trace records the query and lists no entries.
- Choose rules the model cannot guess, or the control arm will pass.
- `retrieve_until_found` retries for up to 20 seconds when a retrieve returns nothing. Call `retrieve` directly if an empty result is valid in your experiment.

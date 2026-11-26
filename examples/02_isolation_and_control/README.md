# 02 - Isolation and control

Shows how to stop one test case's memory from reaching another, and how to reset when entries cannot be deleted.

## Run

Needs `AMFS_HTTP_URL` and `AMFS_API_KEY` in `.env`. No model key.

```bash
uv run python examples/02_isolation_and_control/run.py
```

## Output

```
run id: 02a2573d

wrote poc/isolation/02a2573d/case-1/rule
wrote poc/isolation/02a2573d/case-2/rule

retrieve(entity_path='poc/isolation/02a2573d/case-2')
  expected: case-2's rule and nothing from case-1
  got:      ['poc/isolation/02a2573d/case-2/rule']

retrieve(entity_path='poc/isolation/02a2573d')
  expected: nothing, because matching is exact and nothing was written to the parent itself
  got:      nothing

retrieve() with no entity_path
  expected: the best matches from the whole account, whatever they belong to
  got:      ['poc/isolation/02a2573d/case-2/rule', 'poc-room/eb77356d/rule', 'poc/traces/e3c72377/label-date/rule', 'poc/isolation/1fe5b758/case-2/rule', '<one unrelated entry, shortened here>']

retrieve(entity_path='poc/isolation/b172f90a/case-2')  <- a new run id
  expected: nothing: this is what a clean slate looks like
  got:      nothing
```

In the third block, the retrieve without `entity_path` returned a rule from an earlier run, rules written by two other examples, and an unrelated entry. Yours will list whatever else is in your account.

## How it works

1. `write_rules` writes a different rule under `poc/isolation/<run id>/case-1` and `.../case-2`.
2. `retrieve_three_ways` asks the same question scoped to `case-2`, scoped to the parent path, and with no scope.
3. `a_new_run_is_empty` retrieves on a path with a new run id.

For an experiment this means:

- Isolate by giving each case and each run its own `entity_path`, and pass it to every `retrieve`.
- Reset by starting a new run id. Old entries stay in the account and no longer match.
- For the control arm, create no memory object. `agent_b_control` in example 01 does this.

## Edit

`PATH_PREFIX` sets the path scheme, `RULES` holds one rule per case, and `QUERY` is the question asked each time.

## Adapt

Use the same path scheme in your own harness: `<experiment>/<run id>/<case id>`. Generate the run id once per run, as `poc.memory.new_run_id()` does.

## Gotchas

- A `retrieve` without `entity_path` does not fail. It returns the best matches from the whole account.
- A path matches exactly. `poc/isolation/<run id>` does not include `poc/isolation/<run id>/case-2`.
- Entries are not deleted or expired by these examples. Use a new run id.

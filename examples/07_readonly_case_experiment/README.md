# 07 - Read-only access to one case at a time

The handoff experiment with the access rules enforced by the server. Agent A owns the memory. Agent B uses a key from a different account and can read one case at a time, never write. The control arm has no memory. What B retrieved is saved to a file, and no outcome is committed.

For each case, A opens a room on that case's path and shares a join link with the viewer role. B joins, retrieves, and answers. A deletes the room before the next case.

Both arms answer the task through one function, `solve(task, notes)` in `run.py`. The control passes no notes and the treatment passes what B retrieved. To test your own agent, replace the body of `solve`.

## Before you run

- Example 00 prints `Connected.`
- `.env` has `AMFS_API_KEY` (Agent A's account) and `AMFS_API_KEY_B` (Agent B's account).
- The two keys come from different accounts. To get the second one, sign up at https://amfs.sense-lab.ai with another email address, confirm the email, and create an API key under Settings, API Keys.
- Use an account for B that has no other agents and no memory of its own. See the gotchas.
- For a first run, use `--memory-only`. It needs no model key: A stores the grader's feedback as the rule and the task is skipped, so you can check the access rules first.
- A full run needs a model key for the built-in agent, unless `solve` calls your own agent (see "Use your own agent").

## Run

From the repository root:

```bash
uv run python examples/07_readonly_case_experiment/run.py --memory-only   # SenseLab steps only
uv run python examples/07_readonly_case_experiment/run.py                 # with the task
```

The full run makes 9 short model calls for the three built-in cases: one per case for A to write its rule, and one per arm. Without a model key it stops before doing anything and says so.

A run makes about 45 SenseLab calls and takes under a minute. If a run crashed and left a room open, delete it with:

```bash
uv run python examples/07_readonly_case_experiment/run.py cleanup
```

### One reader account per case

With one `AMFS_API_KEY_B`, the same account reads every case in turn. For cases that are fully separate on the server, give B one account per case:

```bash
# .env
AMFS_API_KEYS_B_PER_CASE=amfs_key_for_case_1,amfs_key_for_case_2,amfs_key_for_case_3
```

The keys are used in the order of `CASES` in `poc/cases.py`. When this variable is set, `AMFS_API_KEY_B` is ignored. The difference between the two modes is explained under "How to read it".

### Use your own agent

1. Replace the body of `solve(task, notes)` in `run.py` with a call to your agent. `notes` is `None` in the control arm. In the treatment arm it is the retrieved entries, one per line, each starting with `- `.
2. Return the answer as text with the final answer alone on the last line. The grader reads only the last non-empty line.
3. In the `CUSTOMIZE` block set `SOLVE_USES_BUILTIN_MODEL = False`, so the script stops asking for a model key.
4. To store your feedback text as A's rule with no model involved, also set `REWRITE_RULE_WITH_MODEL = False`. If you leave it `True`, A's rule is written by the built-in model and a model key is still needed.

## Output

From a run with `--memory-only` and one reader account:

```
run id: 1aa7dad3
reader: one account for every case
rules:  the feedback, stored as given
task:   skipped; memory steps only

Agent A (poc-case-writer) writes one rule per case
  invoice-ref   poc-case/1aa7dad3/invoice-ref/rule
  label-date    poc-case/1aa7dad3/label-date/rule
  ticket-queue  poc-case/1aa7dad3/ticket-queue/rule

case invoice-ref
  A opened a room on poc-case/1aa7dad3/invoice-ref
  B joined with role viewer
  B retrieved               ['poc-case/1aa7dad3/invoice-ref/rule']
  other cases visible to B  none
  briefings in B's account  no other case
  B's write to the path     refused (403)
  room deleted; B retrieves nothing
  A's rule confidence       0.9 (unchanged)

case label-date
  A opened a room on poc-case/1aa7dad3/label-date
  B joined with role viewer
  B retrieved               ['poc-case/1aa7dad3/label-date/rule']
  other cases visible to B  none
  briefings in B's account  1 earlier case(s)
  B's write to the path     refused (403)
  room deleted; B retrieves nothing
  A's rule confidence       0.9 (unchanged)

case ticket-queue
  ...
  briefings in B's account  2 earlier case(s)
  ...

what B retrieved is in results/07_readonly_case_experiment-1aa7dad3.json
Every case was read-only for B and closed again afterwards.
```

Without `--memory-only`, the header says `rules:  rewritten by the built-in model` and `task:   answered by solve()`, each case also prints one line, and the run ends with totals. These lines have not been run yet; the format comes from the code.

```
  control <PASS or FAIL>   treatment <PASS or FAIL>   (expected <answer>)
...
control <n>/3   treatment <n>/3
```

How to read it:

- `B retrieved` lists the entries B got for the case. The results file has the same list with each entry's version, confidence, author, score and text. After a full run it also has, for each arm, the notes `solve` was given, its answer, and whether it passed.
- `other cases visible to B` is what B gets when it asks for the other cases by their paths. All three rules are in A's account from the start, so `none` means the room is the only way in.
- `B's write to the path` is one write B attempts on purpose. `refused (403)` is the viewer role at work.
- `room deleted; B retrieves nothing` shows that B's access ends with the room.
- `A's rule confidence` is read with A's key after B is done. B commits no outcome, so it stays at the value A wrote.
- `briefings in B's account` counts the other cases B's account holds a copy of. When B joins a room, a briefing containing the room's entries is saved in B's own account and stays there after the room is deleted. A retrieve with `entity_path` set to the case path does not return it. A retrieve without `entity_path` can.

That last line is the difference between the two modes. With one reader account, cases are kept apart by B always passing `entity_path`, which this script does. With one account per case, B's account never holds another case, and the script fails if it finds one.

The run with one reader account is the one shown above. `AMFS_API_KEYS_B_PER_CASE` has been run only with the same account repeated, which the script reports as a failure, as it should. It has not been run with three separate accounts.

## How it works

1. `agent_a_writes`: A saves one rule per case with `writer.write(path, "rule", rule, confidence=0.9)` under `poc-case/<run id>/<case id>`. All rules are written before any room exists. The rule is the built-in model's rewrite of the grader's feedback, or the feedback itself when `REWRITE_RULE_WITH_MODEL` is `False` or `--memory-only` is given.
2. `agent_a_opens_room`: `writer.room_create(path, discussions=False)`, then `writer.room_share(room_id, role="viewer", max_uses=1, expires_in_days=1)`, which returns a join link with a `token`.
3. `agent_b_joins`: `reader.room_redeem(token)` admits B's user, and `reader.room_join(room_id)` places B's agent in the room.
4. `agent_b_reads`: a new memory object calls `retrieve(task, entity_path=path, limit=3)`. It then runs the three checks: a retrieve on every other case's path, a search for briefings of other cases in B's account, and one write.
5. `control_arm` calls `solve(task, None)`. It is given no memory object, no key and no retrieved entries. `treatment_arm` calls `solve(task, notes)` with the retrieved entries as a bullet list. Both answers are graded by `Case.check` in `poc/cases.py`.
6. `run_case` deletes the room in a `finally` block, retrieves once more with B's key, and reads the rule with A's key.
7. `run` writes `results/07_readonly_case_experiment-<run id>.json` and exits with an error if any check failed.

B never calls `commit_outcome`. The record of what B retrieved is the return value of `retrieve`, which the script saves.

## Edit

In the `CUSTOMIZE` block at the top of `run.py`:

| Setting | Meaning |
| --- | --- |
| `WRITER_ID`, `READER_ID` | agent names for A and B |
| `PATH_PREFIX` | a case's path is `<prefix>/<run id>/<case id>`. `cleanup` deletes only rooms under this prefix |
| `RETRIEVE_LIMIT` | the most entries B retrieves and passes to `solve` as notes |
| `RULE_CONFIDENCE` | confidence A gives its rule, from 0 to 1 |
| `LINK_EXPIRES_IN_DAYS` | how long a join link is valid. Each link works once |
| `CHECK_WRITE_IS_REFUSED` | `False` skips B's deliberate write |
| `REWRITE_RULE_WITH_MODEL` | `True`: A's rule is the built-in model's rewrite of the feedback. `False`: the feedback is stored as it is |
| `SOLVE_USES_BUILTIN_MODEL` | `True`: the run needs a model key. Set to `False` once `solve` calls your own agent |
| `SOLVER_SYSTEM`, `DISTIL_SYSTEM` | the prompts for the built-in `solve` and for rewriting the rule |

## Adapt

- Your own tasks: edit `CASES` in `poc/cases.py`. The other examples that use cases read the same list.
- Your own agent: see "Use your own agent" above. `solve` runs inside this script's process, where `.env` has been loaded, so the SenseLab keys are in its environment in both arms. If your agent can reach SenseLab by itself, run the control as a separate process without the `AMFS_*` variables.
- A and B in separate processes: A's side is `agent_a_writes`, `agent_a_opens_room` and `room_delete`. B's side is `agent_b_joins` and `agent_b_reads`. Send the join link from A to B by a channel of your own; `room_redeem` accepts the whole link.
- Cases in parallel: this needs one reader account per case, and an account for A whose plan allows several open rooms.
- A trace of B's session: call `reader.commit_outcome(ref, outcome, causal_entry_keys=[])` after the task. The trace is stored in B's account, and A's entries are not changed.

## Gotchas

- Read and retrieve on the exact case path. A sub-path is outside the room.
- Redeeming a link brings in every agent in B's account, and each gets a briefing entry under `<agent id>/briefings/rooms/<case path>`. Use an account for B that has only this agent.
- Entries B's account already has under a case path are returned to B together with A's. Start with an account for B that has never written to these paths.
- A plan can limit open rooms. A 402 from `room_create` means another room is still open; run `cleanup`.
- The join token is a credential. The example does not print it.
- Nothing is recorded in A's account when B retrieves, except that the entry's recall count goes up.
- `retrieve_until_found` retries for up to 20 seconds when a retrieve returns nothing.

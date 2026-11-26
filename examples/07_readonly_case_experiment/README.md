# 07 - Read-only access to one case at a time

The handoff experiment with the access rules enforced by the server. Agent A owns the memory. Agent B uses a key from a different account and can read one case at a time, never write. The control arm has no memory. What B retrieved is saved to a file, and no outcome is committed.

For each case, A opens a room on that case's path and shares a join link with the viewer role. B joins, retrieves, and answers. A deletes the room before the next case.

## Before you run

- Example 00 prints `Connected.`
- `.env` has `AMFS_API_KEY` (Agent A's account) and `AMFS_API_KEY_B` (Agent B's account).
- The two keys come from different accounts. To get the second one, sign up at https://amfs.sense-lab.ai with another email address, confirm the email, and create an API key under Settings, API Keys.
- Use an account for B that has no other agents and no memory of its own. See the gotchas.
- A model key is optional. Without one the script stores the grader's feedback as the rule and skips the task, so you can check the access rules first.

## Run

From the repository root:

```bash
uv run python examples/07_readonly_case_experiment/run.py
```

With a model key in `.env` this makes 9 short model calls for the three built-in cases. To skip them:

```bash
uv run python examples/07_readonly_case_experiment/run.py --memory-only
```

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

## Output

From a run with `--memory-only` and one reader account:

```
run id: 1aa7dad3
reader: one account for every case
model:  not used; memory steps only

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

With a model key, each case also prints one line, and the run ends with totals. These lines have not been run yet; the format comes from the code.

```
  control <PASS or FAIL>   treatment <PASS or FAIL>   (expected <answer>)
...
control <n>/3   treatment <n>/3
```

How to read it:

- `B retrieved` lists the entries B got for the case. The results file has the same list with each entry's version, confidence, author, score and text.
- `other cases visible to B` is what B gets when it asks for the other cases by their paths. All three rules are in A's account from the start, so `none` means the room is the only way in.
- `B's write to the path` is one write B attempts on purpose. `refused (403)` is the viewer role at work.
- `room deleted; B retrieves nothing` shows that B's access ends with the room.
- `A's rule confidence` is read with A's key after B is done. B commits no outcome, so it stays at the value A wrote.
- `briefings in B's account` counts the other cases B's account holds a copy of. When B joins a room, a briefing containing the room's entries is saved in B's own account and stays there after the room is deleted. A retrieve with `entity_path` set to the case path does not return it. A retrieve without `entity_path` can.

That last line is the difference between the two modes. With one reader account, cases are kept apart by B always passing `entity_path`, which this script does. With one account per case, B's account never holds another case, and the script fails if it finds one.

The run with one reader account is the one shown above. `AMFS_API_KEYS_B_PER_CASE` has been run only with the same account repeated, which the script reports as a failure, as it should. It has not been run with three separate accounts.

## How it works

1. `agent_a_writes`: A saves one rule per case with `writer.write(path, "rule", rule, confidence=0.9)` under `poc-case/<run id>/<case id>`. All rules are written before any room exists.
2. `agent_a_opens_room`: `writer.room_create(path, discussions=False)`, then `writer.room_share(room_id, role="viewer", max_uses=1, expires_in_days=1)`, which returns a join link with a `token`.
3. `agent_b_joins`: `reader.room_redeem(token)` admits B's user, and `reader.room_join(room_id)` places B's agent in the room.
4. `agent_b_reads`: a new memory object calls `retrieve(task, entity_path=path, limit=3)`. It then runs the three checks: a retrieve on every other case's path, a search for briefings of other cases in B's account, and one write.
5. `control_arm` sends the task to the model. It is given no memory object and no key. `treatment_arm` adds the retrieved entries to the prompt.
6. `run_case` deletes the room in a `finally` block, retrieves once more with B's key, and reads the rule with A's key.
7. `run` writes `results/07_readonly_case_experiment-<run id>.json` and exits with an error if any check failed.

B never calls `commit_outcome`. The record of what B retrieved is the return value of `retrieve`, which the script saves.

## Edit

In the `CUSTOMIZE` block at the top of `run.py`:

| Setting | Meaning |
| --- | --- |
| `WRITER_ID`, `READER_ID` | agent names for A and B |
| `PATH_PREFIX` | a case's path is `<prefix>/<run id>/<case id>`. `cleanup` deletes only rooms under this prefix |
| `RETRIEVE_LIMIT` | how many entries are added to B's prompt |
| `RULE_CONFIDENCE` | confidence A gives its rule, from 0 to 1 |
| `LINK_EXPIRES_IN_DAYS` | how long a join link is valid. Each link works once |
| `CHECK_WRITE_IS_REFUSED` | `False` skips B's deliberate write |
| `SOLVER_SYSTEM`, `DISTIL_SYSTEM` | the prompts for solving and for writing the rule |

## Adapt

- Your own tasks: edit `CASES` in `poc/cases.py`.
- Your own agent: replace the `complete()` calls in `control_arm` and `treatment_arm` with a call to your agent. If your agent runs as its own process, start the control one without `AMFS_API_KEY` in its environment.
- A and B in separate processes: A's side is `agent_a_writes`, `agent_a_opens_room` and `room_delete`. B's side is `agent_b_joins` and `agent_b_reads`. Send the join link from A to B by a channel of your own; `room_redeem` accepts the whole link.
- Cases in parallel: this needs one reader account per case, and an account for A whose plan allows several open rooms.
- A trace of B's session: call `reader.commit_outcome(ref, outcome, causal_entry_keys=[])` after the task. The trace is stored in B's account, and A's entries are not changed.

## Gotchas

- Read and retrieve on the exact case path. A sub-path is outside the room.
- Redeeming a link brings in every agent B's user owns, and each gets a briefing entry under `<agent id>/briefings/rooms/<case path>`. Use an account for B that has only this agent.
- Entries B's account already has under a case path are returned to B together with A's. Start with an account for B that has never written to these paths.
- A plan can limit open rooms. A 402 from `room_create` means another room is still open; run `cleanup`.
- The join token is a credential. The example does not print it.
- Nothing is recorded in A's account when B retrieves, except that the entry's recall count goes up.
- `retrieve_until_found` retries for up to 20 seconds when a retrieve returns nothing.

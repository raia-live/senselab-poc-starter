"""07 - Agent B reads one case at a time, read-only, as another user.

Agent A owns the memory. For each case it opens a room on that case's path
and shares a join link with the viewer role. Agent B, whose API key belongs
to a different user, joins, retrieves, and is graded with that memory
(treatment) and without any memory (control). A deletes the room before the
next case. B never writes and never commits an outcome; what it retrieved is
saved to a results file.

Both arms answer the task through solve(task, notes) in this file. The control
passes no notes; the treatment passes what B retrieved. To test your own agent,
replace the body of solve().

The SenseLab calls, in order, for one case:

    A  write(path, "rule", ...)                  save the case's rule
    A  room_create(path)                         a room that shares only that path
    A  room_share(room_id, role="viewer")        a single-use, read-only join link
    B  room_redeem(token), room_join(room_id)    B's user enters the room
    B  retrieve(task, entity_path=path)          B reads the rule; the result is saved
    A  room_delete(room_id)                      B's access to the case ends

    uv run python examples/07_readonly_case_experiment/run.py
    uv run python examples/07_readonly_case_experiment/run.py --memory-only   # SenseLab steps only: no agent, no model
    uv run python examples/07_readonly_case_experiment/run.py cleanup         # delete rooms a crashed run left open
"""

from __future__ import annotations

import argparse
import json
import os

import httpx
from amfs import AgentMemory, ScoredEntry

from poc import RESULTS_DIR
from poc.cases import CASES, Case
from poc.llm import complete
from poc.memory import (
    as_notes,
    entry_ref,
    hosted,
    new_run_id,
    retrieve_until_found,
    second_key,
)

# ── CUSTOMIZE ───────────────────────────────────────────────────────────────
# AMFS_API_KEY is Agent A's user. Agent B's key comes from another user, in the
# same account or a different one:
# AMFS_API_KEY_B (one reader for every case), or AMFS_API_KEYS_B_PER_CASE
# (a comma-separated list, one user per case, in the order of CASES).
WRITER_ID = "poc-case-writer"
READER_ID = "poc-case-reader"

# Each case gets its own path: <prefix>/<run id>/<case id>. The room for a
# case shares exactly this path. `cleanup` only touches rooms under the prefix.
PATH_PREFIX = "poc-case"

# How many entries, at most, Agent B retrieves and passes to solve() as notes.
RETRIEVE_LIMIT = 3

# Confidence Agent A gives its rule (0 to 1).
RULE_CONFIDENCE = 0.9

# How long a join link stays valid. Each link can be used once.
LINK_EXPIRES_IN_DAYS = 1

# True: B also tries one write to the case path, to show the server refuses it.
CHECK_WRITE_IS_REFUSED = True

# True: Agent A asks the built-in model to turn the grader's feedback into one
# general rule and stores that, as in example 01. Needs a model key in .env.
# False: Agent A stores the grader's feedback as it is, with no model call.
# --memory-only stores the feedback as it is whatever this says.
REWRITE_RULE_WITH_MODEL = True

# True: solve() below calls the built-in model, so the run needs a model key
# in .env and stops before doing anything if there is none. Set this to False
# once solve() calls your own agent.
SOLVE_USES_BUILTIN_MODEL = True

# The system prompt for the built-in solve().
SOLVER_SYSTEM = (
    "You work at Northwind Freight, which has its own house rules. Do the task. "
    "Put the final answer alone on the last line."
)
# The prompt Agent A uses when REWRITE_RULE_WITH_MODEL is True.
DISTIL_SYSTEM = (
    "You are an agent that just got a task wrong and was told why. Write the one rule a "
    "colleague would need to get any task of this kind right. One sentence, general "
    "(not about this particular instance), and include a worked example. Reply with the rule only."
)
# ────────────────────────────────────────────────────────────────────────────


# ── The agent under test ──────────────────────────────────────────────────────


def solve(task: str, notes: str | None) -> str:
    """Answer one task. Both arms call this; replace the body with your own agent.

    ``task`` is a case's ``eval_task`` from ``poc/cases.py``.

    ``notes`` is ``None`` in the control arm. In the treatment arm it is what
    Agent B retrieved, one entry per line, each line starting with ``"- "``.
    It is also ``None`` in the treatment arm if B retrieved nothing.

    Return the answer as text with the final answer alone on the last line:
    the grader (``Case.check`` in ``poc/cases.py``) reads only the last
    non-empty line and passes when it contains the expected value, in the
    exact upper and lower case.

    This function is given no SenseLab object and no key. If your agent can
    reach SenseLab by other means (its own tools, or the AMFS_* variables that
    this process has loaded from .env), the control arm is not memory-free;
    run the control as a separate process without those variables.
    """
    prompt = task
    if notes:
        prompt += "\n\nNotes left by colleagues that may apply:\n" + notes
    return complete(SOLVER_SYSTEM, prompt).text


def case_path(run_id: str, case: Case) -> str:
    """The one path a case's rule is written to, shared from, and retrieved on."""
    return f"{PATH_PREFIX}/{run_id}/{case.id}"


# ── Which key Agent B uses for which case ─────────────────────────────────────


def reader_keys() -> tuple[list[str], bool]:
    """One key per case for Agent B, and whether each case has its own user."""
    # AMFS_API_KEYS_B_PER_CASE, if set, is "key1,key2,key3". Split it and drop
    # spaces and empty items.
    per_case = [k.strip() for k in (os.environ.get("AMFS_API_KEYS_B_PER_CASE") or "").split(",") if k.strip()]
    if per_case:
        if len(per_case) < len(CASES):
            raise SystemExit(
                f"AMFS_API_KEYS_B_PER_CASE has {len(per_case)} key(s) and there are {len(CASES)} cases. "
                "Give one key per case, each from a different user, or remove the variable."
            )
        # Case 1 uses the first key, case 2 the second, and so on.
        return per_case[: len(CASES)], True
    # Otherwise AMFS_API_KEY_B is the one reader user, reused for every case.
    return [second_key()] * len(CASES), False


def model_is_configured() -> bool:
    """True when .env has a model key for the built-in model in poc/llm.py."""
    return any((os.environ.get(name) or "").strip() for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"))


# ── Agent A: write the rules, open and close one room per case ────────────────


def agent_a_writes(writer: AgentMemory, run_id: str, rewrite: bool) -> None:
    """Agent A saves one rule per case, all of them before any room exists."""
    print(f"Agent A ({writer.agent_id}) writes one rule per case")
    for case in CASES:
        if rewrite:
            # Ask the model to turn the grader's feedback into one general rule.
            rule = complete(DISTIL_SYSTEM, f"Task: {case.teach_task}\nGrader's feedback: {case.feedback}").text
        else:
            # Store the grader's feedback as it is.
            rule = case.feedback
        # Save it under this case's own path with the key "rule". The path is
        # what the room will share and what B will retrieve on.
        entry = writer.write(case_path(run_id, case), "rule", rule, confidence=RULE_CONFIDENCE)
        print(f"  {case.id:<13} {entry_ref(entry)}")


def agent_a_opens_room(writer: AgentMemory, path: str, run_id: str, case: Case) -> tuple[str, str]:
    """A room on this case's path, and a single-use viewer link to it."""
    # The first argument is the topic: the one path the room shares. Nothing
    # else of A's becomes visible to the room's members.
    room = writer.room_create(
        path,
        name=f"POC case {case.id} ({run_id})",
        description="Created by the SenseLab POC starter, example 07.",
        discussions=False,  # B only reads; no messages are needed
    )
    room_id = str(room["id"])
    # role="viewer" is what makes B read-only. max_uses=1 means the link
    # admits one user and then stops working.
    link = writer.room_share(room_id, role="viewer", max_uses=1, expires_in_days=LINK_EXPIRES_IN_DAYS)
    # The token is a credential: do not print or log it.
    return room_id, link["token"]


# ── Agent B: join, retrieve, and the checks on what it can reach ──────────────


def agent_b_joins(api_key: str, token: str, room_id: str) -> str:
    """Redeeming admits B's user; joining places this agent in the room."""
    # Connect as B, with B's key in place of AMFS_API_KEY.
    reader = hosted(READER_ID, api_key=api_key)
    # Step 1: redeem the link. This makes B's user a member of the room with
    # the role the link carries ("viewer"). It accepts the token or the whole URL.
    role = reader.room_redeem(token).get("role")
    # Step 2: place this agent in the room, so its reads include the room's path.
    reader.room_join(room_id)
    return str(role)


def describe(hit: ScoredEntry) -> dict:
    """One retrieved entry as it goes into the results file."""
    # A hit is the stored entry plus the score retrieval gave it for this query.
    entry = hit.entry
    return {
        "entry": entry_ref(entry),
        "version": entry.version,
        "confidence": entry.confidence,
        "written_by": entry.provenance.agent_id,
        "score": getattr(hit, "score", None),
        "value": entry.value if isinstance(entry.value, str) else repr(entry.value),
    }


def write_is_refused(reader: AgentMemory, path: str) -> bool:
    """B tries one write to the case path. A viewer gets a 403 and nothing is saved."""
    try:
        # An ordinary write, the same call A uses. Only the role differs.
        reader.write(path, "viewer-write-check", "Written by the read-only check in example 07.")
    except httpx.HTTPStatusError as exc:
        # 403 with error "room_read_only" in the body is the server refusing
        # a viewer. A 403 for any other reason does not count.
        if exc.response.status_code == 403 and "room_read_only" in exc.response.text:
            return True
        raise  # any other error is a real failure, so let it stop the run
    # No error: the write was saved, which means B is not read-only.
    return False


def agent_b_reads(api_key: str, run_id: str, case: Case) -> tuple[AgentMemory, dict]:
    """A fresh Agent B retrieves on the case's path, then checks what else it can reach."""
    reader = hosted(READER_ID, api_key=api_key)  # new object, new session
    path = case_path(run_id, case)
    # The paths of the cases B has NOT been given, for the two checks below.
    other_paths = [case_path(run_id, other) for other in CASES if other.id != case.id]

    # The retrieve B's answer is built from. The task is the query, and
    # entity_path limits the search to this case's path. The return value is
    # the full record of what B retrieved; nothing else needs to be committed.
    hits = retrieve_until_found(reader, case.eval_task, entity_path=path, limit=RETRIEVE_LIMIT)

    # Check 1: the other cases exist in A's memory. Ask for each by its
    # exact path. B is not in a room for them, so this should find nothing.
    visible_others = [
        entry_ref(hit.entry)
        for other in other_paths
        for hit in reader.retrieve(case.eval_task, entity_path=other, limit=RETRIEVE_LIMIT)
    ]

    # Check 2: joining a room saves a briefing with the room's entries in B's
    # OWN memory, under <agent id>/briefings/rooms/<case path>, and it stays
    # there after the room is deleted. List which other cases B's user
    # holds such a copy of. With one user per case this stays empty.
    copies = [
        other
        for other in other_paths
        if reader.search(entity_path=f"{READER_ID}/briefings/rooms/{other}", limit=1)
    ]

    # Check 3: B tries to write to the case path and should be refused.
    refused = write_is_refused(reader, path) if CHECK_WRITE_IS_REFUSED else None
    # "hits" are the SDK objects for the prompt; "retrieved" is the same list
    # as plain data for the results file.
    return reader, {
        "hits": hits,
        "retrieved": [describe(hit) for hit in hits],
        "other_cases_visible": visible_others,
        "other_cases_copied_to_reader": copies,
        "write_refused": refused,
    }


# ── The task: control without memory, treatment with what B retrieved ─────────


def control_arm(case: Case) -> dict:
    """No memory: this function is given no SenseLab object, no key and no retrieved entries."""
    # The bare task goes to the agent with notes=None. Nothing from SenseLab is involved.
    answer = solve(case.eval_task, None)
    return {"notes": None, "answer": answer, "passed": case.check(answer)}


def treatment_arm(case: Case, hits: list[ScoredEntry]) -> dict:
    """The same task, with the retrieved entries passed to the agent as notes."""
    # One bullet per retrieved entry. If nothing was retrieved the agent gets
    # notes=None, the same call as the control.
    notes = as_notes(hits) if hits else None
    answer = solve(case.eval_task, notes)
    # Graded by the string-match checker in poc/cases.py, the same as the control.
    return {"notes": notes, "answer": answer, "passed": case.check(answer)}


# ── One case from start to finish ─────────────────────────────────────────────


def run_case(writer: AgentMemory, api_key: str, run_id: str, case: Case, *, run_task: bool, own_user: bool) -> dict:
    """Open the room, let B read and answer, close the room, check it is closed."""
    path = case_path(run_id, case)
    # Every check that fails adds a line here. The run exits with an error at
    # the end if any case has one.
    problems: list[str] = []
    print(f"\ncase {case.id}")

    # A's side: open the room and get the join link's token.
    room_id, token = agent_a_opens_room(writer, path, run_id, case)
    print(f"  A opened a room on {path}")
    try:
        # B's side: join with the token. In a real setup A sends the link to
        # B by another channel; here both sides run in one script.
        role = agent_b_joins(api_key, token, room_id)
        print(f"  B joined with role {role}")

        # B retrieves, then the three checks run with B's key.
        reader, seen = agent_b_reads(api_key, run_id, case)
        hits = seen.pop("hits")
        print(f"  B retrieved               {[r['entry'] for r in seen['retrieved']] or 'nothing'}")
        if not hits:
            problems.append("B retrieved nothing from the case it was given")

        print(f"  other cases visible to B  {seen['other_cases_visible'] or 'none'}")
        if seen["other_cases_visible"]:
            problems.append("B could retrieve another case by its path")

        # With one reader user this is expected from the second case on,
        # so it is only printed. With one user per case it is a failure.
        copies = seen["other_cases_copied_to_reader"]
        print(f"  briefings in B's memory   {f'{len(copies)} earlier case(s)' if copies else 'no other case'}")
        if copies and own_user:
            problems.append("a per-case key holds another case's briefing: two of the keys belong to the same user")

        if seen["write_refused"] is not None:
            print(f"  B's write to the path     {'refused (403)' if seen['write_refused'] else 'ACCEPTED'}")
            if not seen["write_refused"]:
                problems.append("B's write was accepted, so B is not read-only")

        # The task itself, answered by solve(). Skipped with --memory-only.
        control = treatment = None
        if run_task:
            control = control_arm(case)
            treatment = treatment_arm(case, hits)
            print(f"  control {_mark(control)}   treatment {_mark(treatment)}   (expected {case.expected})")
    finally:
        # One room open at a time: a Free account allows one, and closing it
        # is what ends B's access to this case.
        writer.room_delete(room_id)

    # After the room is gone, the same retrieve with B's key returns nothing.
    still_visible = reader.retrieve(case.eval_task, entity_path=path, limit=RETRIEVE_LIMIT)
    print(f"  room deleted; B retrieves {[entry_ref(h.entry) for h in still_visible] or 'nothing'}")
    if still_visible:
        problems.append("B could still retrieve the case after its room was deleted")

    # Read the rule with A's key. B committed no outcome, so the confidence
    # is still the value A wrote.
    rule = writer.read(path, "rule")
    unchanged = rule is not None and abs(rule.confidence - RULE_CONFIDENCE) < 1e-9
    print(f"  A's rule confidence       {rule.confidence if rule else 'missing'} ({'unchanged' if unchanged else 'CHANGED'})")
    if not unchanged:
        problems.append("A's rule changed while B had access")

    # One row of the results file.
    return {
        "case": case.id,
        "path": path,
        "expected": case.expected,
        **seen,
        "control": control,
        "treatment": treatment,
        "problems": problems,
    }


def _mark(arm: dict) -> str:
    return "PASS" if arm["passed"] else "FAIL"


# ── The whole experiment ──────────────────────────────────────────────────────


def run(memory_only: bool) -> None:
    # A new id per run, so every run writes under paths nobody has used.
    run_id = new_run_id()
    # B's key for each case, and whether each case has its own user.
    keys, own_user = reader_keys()
    # --memory-only switches off both the task and the rule rewriting, so the
    # run makes SenseLab calls only.
    run_task = not memory_only
    rewrite = REWRITE_RULE_WITH_MODEL and not memory_only
    # Stop now, before anything is written, if the built-in model is needed
    # and .env has no key for it.
    if (rewrite or (run_task and SOLVE_USES_BUILTIN_MODEL)) and not model_is_configured():
        raise SystemExit(
            "No model key in .env. Add ANTHROPIC_API_KEY (or OPENAI_API_KEY and POC_MODEL), "
            "or pass --memory-only to run the SenseLab steps without a model. If solve() calls "
            "your own agent, set SOLVE_USES_BUILTIN_MODEL and REWRITE_RULE_WITH_MODEL to False."
        )
    # Agent A, connected with AMFS_API_KEY.
    writer = hosted(WRITER_ID)

    print(f"run id: {run_id}")
    print(f"reader: {'one user per case' if own_user else 'one user for every case'}")
    print(f"rules:  {'rewritten by the built-in model' if rewrite else 'the feedback, stored as given'}")
    print(f"task:   {'answered by solve()' if run_task else 'skipped; memory steps only'}\n")

    # A writes every rule first, then the cases run one after another, each
    # with its own room and its own key for B.
    agent_a_writes(writer, run_id, rewrite)
    rows = [
        run_case(writer, key, run_id, case, run_task=run_task, own_user=own_user)
        for key, case in zip(keys, CASES, strict=True)
    ]

    # What B retrieved for every case, with no outcome committed anywhere.
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"07_readonly_case_experiment-{run_id}.json"
    out.write_text(json.dumps({"run_id": run_id, "reader_user_per_case": own_user, "cases": rows}, indent=2))

    print()
    if run_task:
        control_passed = sum(row["control"]["passed"] for row in rows)
        treatment_passed = sum(row["treatment"]["passed"] for row in rows)
        print(f"control {control_passed}/{len(rows)}   treatment {treatment_passed}/{len(rows)}")
    print(f"what B retrieved is in {out.relative_to(RESULTS_DIR.parent)}")

    # Collect the failed checks from all cases and stop with an error if any.
    problems = [f"{row['case']}: {problem}" for row in rows for problem in row["problems"]]
    if problems:
        raise SystemExit("FAILED:\n  " + "\n  ".join(problems))
    print("Every case was read-only for B and closed again afterwards.")


# ── Cleanup after a crashed run ───────────────────────────────────────────────


def cleanup() -> None:
    """Delete rooms this example created and a failed run left behind."""
    writer = hosted(WRITER_ID)
    # my_rooms lists the rooms A is in. Keep those whose topic starts with
    # this example's prefix.
    mine = [
        room
        for room in writer.my_rooms()
        if any(str(path).startswith(f"{PATH_PREFIX}/") for path in room.get("entity_paths") or [])
    ]
    if not mine:
        print(f"No rooms with a topic under {PATH_PREFIX}/.")
    for room in mine:
        writer.room_delete(str(room["id"]))
        print(f"deleted room {room['id']} ({', '.join(room.get('entity_paths') or [])})")


# ── Command line ──────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # "run" is the experiment. "cleanup" deletes rooms a crashed run left open.
    parser.add_argument("step", nargs="?", default="run", choices=["run", "cleanup"])
    parser.add_argument("--memory-only", action="store_true", help="run the SenseLab steps only: no agent and no model")
    args = parser.parse_args()
    try:
        cleanup() if args.step == "cleanup" else run(args.memory_only)
    except httpx.HTTPStatusError as exc:
        # The message carries the server's reason: 402 is the plan's room
        # limit, 403 a role that may not do this, 409 a topic already shared.
        raise SystemExit(f"FAILED: {exc}") from exc


if __name__ == "__main__":
    main()

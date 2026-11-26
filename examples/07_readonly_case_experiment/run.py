"""07 - Agent B reads one case at a time, read-only, from another account.

Agent A owns the memory. For each case it opens a room on that case's path
and shares a join link with the viewer role. Agent B, whose API key belongs
to a different account, joins, retrieves, and is graded with that memory
(treatment) and without any memory (control). A deletes the room before the
next case. B never writes and never commits an outcome; what it retrieved is
saved to a results file.

    uv run python examples/07_readonly_case_experiment/run.py
    uv run python examples/07_readonly_case_experiment/run.py --memory-only   # skip the model calls
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
# AMFS_API_KEY is Agent A's account. Agent B's key comes from another account:
# AMFS_API_KEY_B (one reader for every case), or AMFS_API_KEYS_B_PER_CASE
# (a comma-separated list, one account per case, in the order of CASES).
WRITER_ID = "poc-case-writer"
READER_ID = "poc-case-reader"

# Each case gets its own path: <prefix>/<run id>/<case id>. The room for a
# case shares exactly this path. `cleanup` only touches rooms under the prefix.
PATH_PREFIX = "poc-case"

# How many entries Agent B pulls into its prompt.
RETRIEVE_LIMIT = 3

# Confidence Agent A gives its rule (0 to 1).
RULE_CONFIDENCE = 0.9

# How long a join link stays valid. Each link can be used once.
LINK_EXPIRES_IN_DAYS = 1

# True: B also tries one write to the case path, to show the server refuses it.
CHECK_WRITE_IS_REFUSED = True

SOLVER_SYSTEM = (
    "You work at Northwind Freight, which has its own house rules. Do the task. "
    "Put the final answer alone on the last line."
)
DISTIL_SYSTEM = (
    "You are an agent that just got a task wrong and was told why. Write the one rule a "
    "colleague would need to get any task of this kind right. One sentence, general "
    "(not about this particular instance), and include a worked example. Reply with the rule only."
)
# ────────────────────────────────────────────────────────────────────────────


def case_path(run_id: str, case: Case) -> str:
    """The one path a case's rule is written to, shared from, and retrieved on."""
    return f"{PATH_PREFIX}/{run_id}/{case.id}"


# ── Which key Agent B uses for which case ─────────────────────────────────────


def reader_keys() -> tuple[list[str], bool]:
    """One key per case for Agent B, and whether each case has its own account."""
    per_case = [k.strip() for k in (os.environ.get("AMFS_API_KEYS_B_PER_CASE") or "").split(",") if k.strip()]
    if per_case:
        if len(per_case) < len(CASES):
            raise SystemExit(
                f"AMFS_API_KEYS_B_PER_CASE has {len(per_case)} key(s) and there are {len(CASES)} cases. "
                "Give one key per case, each from a different account, or remove the variable."
            )
        return per_case[: len(CASES)], True
    # One reader account, reused for every case.
    return [second_key()] * len(CASES), False


def model_is_configured() -> bool:
    """True when .env has a model key, so the task step can run."""
    return any((os.environ.get(name) or "").strip() for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"))


# ── Agent A: write the rules, open and close one room per case ────────────────


def agent_a_writes(writer: AgentMemory, run_id: str, use_model: bool) -> None:
    """Agent A saves one rule per case, all of them before any room exists."""
    print(f"Agent A ({writer.agent_id}) writes one rule per case")
    for case in CASES:
        if use_model:
            # Ask the model to turn the grader's feedback into one general rule.
            rule = complete(DISTIL_SYSTEM, f"Task: {case.teach_task}\nGrader's feedback: {case.feedback}").text
        else:
            # No model: store the grader's feedback as it is.
            rule = case.feedback
        entry = writer.write(case_path(run_id, case), "rule", rule, confidence=RULE_CONFIDENCE)
        print(f"  {case.id:<13} {entry_ref(entry)}")


def agent_a_opens_room(writer: AgentMemory, path: str, run_id: str, case: Case) -> tuple[str, str]:
    """A room on this case's path, and a single-use viewer link to it."""
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
    reader = hosted(READER_ID, api_key=api_key)
    role = reader.room_redeem(token).get("role")
    reader.room_join(room_id)
    return str(role)


def describe(hit: ScoredEntry) -> dict:
    """One retrieved entry as it goes into the results file."""
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
        reader.write(path, "viewer-write-check", "Written by the read-only check in example 07.")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            return True
        raise
    return False


def agent_b_reads(api_key: str, run_id: str, case: Case) -> tuple[AgentMemory, dict]:
    """A fresh Agent B retrieves on the case's path, then checks what else it can reach."""
    reader = hosted(READER_ID, api_key=api_key)  # new object, new session
    path = case_path(run_id, case)
    other_paths = [case_path(run_id, other) for other in CASES if other.id != case.id]

    # The retrieve B's answer is built from: this case's path only.
    hits = retrieve_until_found(reader, case.eval_task, entity_path=path, limit=RETRIEVE_LIMIT)

    # The other cases exist in A's account. Ask for each by its exact path.
    visible_others = [
        entry_ref(hit.entry)
        for other in other_paths
        for hit in reader.retrieve(case.eval_task, entity_path=other, limit=RETRIEVE_LIMIT)
    ]

    # Joining a room saves a briefing with the room's entries in B's OWN
    # account, under <agent id>/briefings/rooms/<case path>, and it stays
    # there. List which other cases B's account holds such a copy of.
    copies = [
        other
        for other in other_paths
        if reader.search(entity_path=f"{READER_ID}/briefings/rooms/{other}", limit=1)
    ]

    refused = write_is_refused(reader, path) if CHECK_WRITE_IS_REFUSED else None
    return reader, {
        "hits": hits,
        "retrieved": [describe(hit) for hit in hits],
        "other_cases_visible": visible_others,
        "other_cases_copied_to_reader_account": copies,
        "write_refused": refused,
    }


# ── The task: control without memory, treatment with what B retrieved ─────────


def control_arm(case: Case) -> dict:
    """No memory: this function is given no SenseLab object and no key."""
    answer = complete(SOLVER_SYSTEM, case.eval_task).text
    return {"answer": answer, "passed": case.check(answer)}


def treatment_arm(case: Case, hits: list[ScoredEntry]) -> dict:
    """The same task with the retrieved entries added to the prompt."""
    prompt = case.eval_task
    if hits:
        prompt += "\n\nNotes left by colleagues that may apply:\n" + as_notes(hits)
    answer = complete(SOLVER_SYSTEM, prompt).text
    return {"answer": answer, "passed": case.check(answer)}


# ── One case from start to finish ─────────────────────────────────────────────


def run_case(writer: AgentMemory, api_key: str, run_id: str, case: Case, *, use_model: bool, own_account: bool) -> dict:
    """Open the room, let B read and answer, close the room, check it is closed."""
    path = case_path(run_id, case)
    problems: list[str] = []
    print(f"\ncase {case.id}")

    room_id, token = agent_a_opens_room(writer, path, run_id, case)
    print(f"  A opened a room on {path}")
    try:
        role = agent_b_joins(api_key, token, room_id)
        print(f"  B joined with role {role}")

        reader, seen = agent_b_reads(api_key, run_id, case)
        hits = seen.pop("hits")
        print(f"  B retrieved               {[r['entry'] for r in seen['retrieved']] or 'nothing'}")
        if not hits:
            problems.append("B retrieved nothing from the case it was given")

        print(f"  other cases visible to B  {seen['other_cases_visible'] or 'none'}")
        if seen["other_cases_visible"]:
            problems.append("B could retrieve another case by its path")

        copies = seen["other_cases_copied_to_reader_account"]
        print(f"  briefings in B's account  {f'{len(copies)} earlier case(s)' if copies else 'no other case'}")
        if copies and own_account:
            problems.append("a per-case key holds another case's briefing: two of the keys share an account")

        if seen["write_refused"] is not None:
            print(f"  B's write to the path     {'refused (403)' if seen['write_refused'] else 'ACCEPTED'}")
            if not seen["write_refused"]:
                problems.append("B's write was accepted, so B is not read-only")

        # The task itself. Skipped when no model key is set.
        control = treatment = None
        if use_model:
            control = control_arm(case)
            treatment = treatment_arm(case, hits)
            print(f"  control {_mark(control)}   treatment {_mark(treatment)}   (expected {case.expected})")
    finally:
        # One room open at a time: a Free account allows one, and closing it
        # is what ends B's access to this case.
        writer.room_delete(room_id)

    # After the room is gone B gets nothing on the path, and A's entry is as A left it.
    still_visible = reader.retrieve(case.eval_task, entity_path=path, limit=RETRIEVE_LIMIT)
    print(f"  room deleted; B retrieves {[entry_ref(h.entry) for h in still_visible] or 'nothing'}")
    if still_visible:
        problems.append("B could still retrieve the case after its room was deleted")

    rule = writer.read(path, "rule")
    unchanged = rule is not None and abs(rule.confidence - RULE_CONFIDENCE) < 1e-9
    print(f"  A's rule confidence       {rule.confidence if rule else 'missing'} ({'unchanged' if unchanged else 'CHANGED'})")
    if not unchanged:
        problems.append("A's rule changed while B had access")

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
    run_id = new_run_id()
    keys, own_account = reader_keys()
    use_model = model_is_configured() and not memory_only
    writer = hosted(WRITER_ID)

    print(f"run id: {run_id}")
    print(f"reader: {'one account per case' if own_account else 'one account for every case'}")
    print(f"model:  {'used for the rules and the task' if use_model else 'not used; memory steps only'}\n")

    agent_a_writes(writer, run_id, use_model)
    rows = [
        run_case(writer, key, run_id, case, use_model=use_model, own_account=own_account)
        for key, case in zip(keys, CASES, strict=True)
    ]

    # What B retrieved for every case, with no outcome committed anywhere.
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"07_readonly_case_experiment-{run_id}.json"
    out.write_text(json.dumps({"run_id": run_id, "reader_account_per_case": own_account, "cases": rows}, indent=2))

    print()
    if use_model:
        control_passed = sum(row["control"]["passed"] for row in rows)
        treatment_passed = sum(row["treatment"]["passed"] for row in rows)
        print(f"control {control_passed}/{len(rows)}   treatment {treatment_passed}/{len(rows)}")
    print(f"what B retrieved is in {out.relative_to(RESULTS_DIR.parent)}")

    problems = [f"{row['case']}: {problem}" for row in rows for problem in row["problems"]]
    if problems:
        raise SystemExit("FAILED:\n  " + "\n  ".join(problems))
    print("Every case was read-only for B and closed again afterwards.")


# ── Cleanup after a crashed run ───────────────────────────────────────────────


def cleanup() -> None:
    """Delete rooms this example created and a failed run left behind."""
    writer = hosted(WRITER_ID)
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
    parser.add_argument("step", nargs="?", default="run", choices=["run", "cleanup"])
    parser.add_argument("--memory-only", action="store_true", help="skip the model calls even if a model key is set")
    args = parser.parse_args()
    try:
        cleanup() if args.step == "cleanup" else run(args.memory_only)
    except httpx.HTTPStatusError as exc:
        # The message carries the server's reason: 402 is the plan's room
        # limit, 403 a role that may not do this, 409 a topic already shared.
        raise SystemExit(f"FAILED: {exc}") from exc


if __name__ == "__main__":
    main()

"""01 - Agent A writes a rule, a fresh Agent B uses it.

For each case, Agent A learns a house rule from the grader's feedback and
saves it. Agent B then gets a new task that needs the same rule, twice: once
with no memory at all (control) and once after retrieving from SenseLab
(treatment). Same API key for both agents; no room is involved.

    uv run python examples/01_memory_handoff/run.py            # write, then evaluate
    uv run python examples/01_memory_handoff/run.py write --run-id demo1
    uv run python examples/01_memory_handoff/run.py eval  --run-id demo1
"""

from __future__ import annotations

import argparse
import json

from amfs import OutcomeType

from poc import RESULTS_DIR
from poc.cases import CASES, Case
from poc.llm import complete
from poc.memory import as_notes, entry_ref, hosted, new_run_id, retrieve_until_found

# ── CUSTOMIZE ───────────────────────────────────────────────────────────────
# The two agents. Different ids, so the dashboard shows who wrote and who read.
WRITER_ID = "poc-writer"
SOLVER_ID = "poc-solver"

# Each case gets its own path: <prefix>/<run id>/<case id>. Retrieval is
# scoped to that exact path, which is what keeps cases and runs apart.
PATH_PREFIX = "poc/handoff"

# How many entries Agent B pulls into its prompt.
RETRIEVE_LIMIT = 3

# Confidence Agent A gives its rule (0 to 1).
RULE_CONFIDENCE = 0.9

# False: outcomes are recorded as traces but do not change any entry's
# confidence, so every run of the experiment starts from the same memory.
# True: the outcome is credited to (or charged against) the entries Agent B
# retrieved, which is how memory improves in real use.
OUTCOMES_MOVE_CONFIDENCE = False

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
    return f"{PATH_PREFIX}/{run_id}/{case.id}"


def agent_a_writes(run_id: str) -> None:
    """Agent A turns the grader's feedback into a rule and saves it."""
    writer = hosted(WRITER_ID)
    print(f"Agent A ({writer.agent_id}) writes one rule per case\n")
    for case in CASES:
        rule = complete(
            DISTIL_SYSTEM,
            f"Task: {case.teach_task}\nGrader's feedback: {case.feedback}",
        ).text
        entry = writer.write(case_path(run_id, case), "rule", rule, confidence=RULE_CONFIDENCE)
        print(f"  {case.id}: saved {entry_ref(entry)}\n    {rule}\n")


def agent_b_control(case: Case) -> dict:
    """Agent B with no memory: no SenseLab object is created at all."""
    answer = complete(SOLVER_SYSTEM, case.eval_task).text
    return {"answer": answer, "passed": case.check(answer)}


def agent_b_treatment(run_id: str, case: Case) -> dict:
    """A fresh Agent B retrieves on the case's path and answers with what it found."""
    solver = hosted(SOLVER_ID)  # new object, new session: nothing carried over
    path = case_path(run_id, case)

    hits = retrieve_until_found(solver, case.eval_task, entity_path=path, limit=RETRIEVE_LIMIT)
    prompt = case.eval_task
    if hits:
        prompt += "\n\nNotes left by colleagues that may apply:\n" + as_notes(hits)
    answer = complete(SOLVER_SYSTEM, prompt).text
    passed = case.check(answer)

    # Seal a trace of what this session read and how it turned out.
    solver.commit_outcome(
        f"poc-handoff-{run_id}-{case.id}",
        OutcomeType.SUCCESS if passed else OutcomeType.FAILURE,
        causal_entry_keys=[entry_ref(h.entry) for h in hits] if OUTCOMES_MOVE_CONFIDENCE else [],
        entity_path=path,
        task_input=case.eval_task,
        response_text=answer,
        verified_by="verifier",  # the grader decided, not the agent
        attributes={"poc_run_id": run_id, "poc_case": case.id, "poc_arm": "treatment"},
    )
    return {
        "answer": answer,
        "passed": passed,
        "retrieved": [entry_ref(h.entry) for h in hits],
    }


def evaluate(run_id: str) -> None:
    """Run both arms for every case and print one line each."""
    print("Agent B, graded on a new instance of each task\n")
    rows = []
    for case in CASES:
        control = agent_b_control(case)
        treatment = agent_b_treatment(run_id, case)
        rows.append({"case": case.id, "expected": case.expected, "control": control, "treatment": treatment})
        print(
            f"  {case.id:<13} control {_mark(control)}   treatment {_mark(treatment)}"
            f"   retrieved {treatment['retrieved'] or 'nothing'}"
        )

    control_passed = sum(row["control"]["passed"] for row in rows)
    treatment_passed = sum(row["treatment"]["passed"] for row in rows)
    print(f"\n  control {control_passed}/{len(rows)}   treatment {treatment_passed}/{len(rows)}")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"01_memory_handoff-{run_id}.json"
    out.write_text(json.dumps({"run_id": run_id, "cases": rows}, indent=2))
    print(f"  full answers in {out.relative_to(RESULTS_DIR.parent)}")


def _mark(arm: dict) -> str:
    return "PASS" if arm["passed"] else "FAIL"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("step", nargs="?", default="all", choices=["all", "write", "eval"])
    parser.add_argument("--run-id", help="reuse an id to evaluate against rules written earlier")
    args = parser.parse_args()
    if args.step == "eval" and not args.run_id:
        parser.error("eval needs --run-id: the id that 'write' printed")

    run_id = args.run_id or new_run_id()
    print(f"run id: {run_id}\n")
    if args.step in ("all", "write"):
        agent_a_writes(run_id)
    if args.step in ("all", "eval"):
        evaluate(run_id)


if __name__ == "__main__":
    main()

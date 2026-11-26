"""03 - What a run captured.

Solves the same task twice. The first session ends with the shortest possible
commit. The second records what it consulted, what it did and what the model
cost, and passes the prompt and the answer. Then both traces are fetched back
and printed side by side, so you can see what is stored by default and what
is stored only because you passed it.

    uv run python examples/03_inspect_traces/run.py
"""

from __future__ import annotations

import argparse
import json
import time

from amfs import AgentMemory, DecisionTrace, OutcomeType

from poc.cases import by_id
from poc.llm import Reply, complete
from poc.memory import as_notes, hosted, new_run_id, retrieve_until_found

# ── CUSTOMIZE ───────────────────────────────────────────────────────────────
WRITER_ID = "poc-writer"
SOLVER_ID = "poc-solver"
PATH_PREFIX = "poc/traces"

# Which case from poc/cases.py to run.
CASE_ID = "label-date"

# Anything you want to slice traces by later. Keys and values are yours.
ATTRIBUTES = {"experiment": "poc-traces", "arm": "treatment"}

SOLVER_SYSTEM = (
    "You work at Northwind Freight, which has its own house rules. Do the task. "
    "Put the final answer alone on the last line."
)
# ────────────────────────────────────────────────────────────────────────────

# The case both sessions solve.
CASE = by_id(CASE_ID)


# ── Setup shared by both sessions ─────────────────────────────────────────────


def seed_rule(path: str) -> None:
    """Put the rule in memory, so both sessions have something to read."""
    hosted(WRITER_ID).write(path, "rule", CASE.feedback, confidence=0.9)


def solve(solver: AgentMemory, path: str) -> tuple[Reply, bool]:
    """Retrieve, answer, grade. Identical for both sessions."""
    # Retrieve the rule from this case's path. SenseLab logs this query on
    # the session, and it ends up in the trace.
    hits = retrieve_until_found(solver, CASE.eval_task, entity_path=path)
    # Put what was found into the prompt and ask the model.
    prompt = CASE.eval_task + "\n\nNotes left by colleagues that may apply:\n" + as_notes(hits)
    reply = complete(SOLVER_SYSTEM, prompt)
    # Return the reply (text and token counts) and whether it passed.
    return reply, CASE.check(reply.text)


# ── Session 1: the shortest possible commit ───────────────────────────────────


def bare_session(run_id: str, path: str) -> tuple[AgentMemory, str]:
    """The least you can do: a reference and an outcome."""
    solver = hosted(SOLVER_ID)
    _, passed = solve(solver, path)
    # The reference is your own name for this outcome. fetch_trace uses it
    # to find the trace again.
    ref = f"poc-traces-{run_id}-bare"
    # Only the two required arguments. Everything else on the trace is what
    # SenseLab recorded by itself.
    solver.commit_outcome(ref, OutcomeType.SUCCESS if passed else OutcomeType.FAILURE)
    return solver, ref


# ── Session 2: record everything the SDK accepts ──────────────────────────────


def full_session(run_id: str, path: str) -> tuple[AgentMemory, str]:
    """Everything the SDK lets a session put on its trace."""
    solver = hosted(SOLVER_ID)
    reply, passed = solve(solver, path)

    # Something the agent learned from outside SenseLab.
    solver.record_context("grader", f"expected {CASE.expected}", source="poc/cases.py")
    # Something the agent did. SenseLab only sees its own calls, so anything
    # else is on the trace only if you record it.
    solver.record_action("submit_answer", {"case": CASE.id}, result=reply.text, success=passed)
    # What the model call cost.
    solver.record_llm_call(
        reply.model,
        reply.input_tokens,
        reply.output_tokens,
        provider=reply.provider,
        latency_ms=reply.latency_ms,
    )

    # The three record_* calls above are held in the session. This commit
    # sends them, together with the arguments below, as one trace.
    ref = f"poc-traces-{run_id}-full"
    solver.commit_outcome(
        ref,
        OutcomeType.SUCCESS if passed else OutcomeType.FAILURE,
        entity_path=path,
        task_input=CASE.eval_task,  # the prompt is stored only because it is passed here
        response_text=reply.text,  # and so is the answer
        verified_by="verifier",
        attributes=ATTRIBUTES,
    )
    return solver, ref


# ── Read the two traces back and print them ───────────────────────────────────


def fetch_trace(mem: AgentMemory, ref: str, timeout: float = 20.0) -> DecisionTrace | None:
    """Find the trace a commit produced, by its outcome reference."""
    # A trace can take a moment to appear, so look again every 2 seconds
    # until the timeout.
    deadline = time.monotonic() + timeout
    while True:
        # list_traces returns recent traces for this agent.
        for trace in mem.list_traces(agent_id=mem.agent_id, limit=20):
            if trace.outcome_ref == ref:
                # get_trace loads the full record for one trace id.
                return mem.get_trace(trace.id) or trace
        if time.monotonic() >= deadline:
            return None
        time.sleep(2)


def describe(title: str, trace: DecisionTrace | None) -> None:
    """Print one trace, field by field, saying which fields are empty."""
    print(f"── {title} " + "─" * max(0, 60 - len(title)))
    if trace is None:
        print("  no trace found for this commit\n")
        return
    # What you passed to commit_outcome, and the session it closed.
    print(f"  outcome            {trace.outcome_ref} -> {trace.outcome_type}")
    print(f"  task_input         {_short(trace.task_input)}")
    print(f"  response_text      {_short(trace.response_text)}")
    print(f"  session            {trace.session_id}, {_ms(trace.session_duration_ms)}")

    # What SenseLab recorded about the session's use of memory.
    print(f"  entries read       {len(trace.causal_entries)}")
    for e in trace.causal_entries:
        print(f"    {e.entity_path}/{e.key} v{e.version} confidence {e.confidence}: {_short(e.value)}")
    print(f"  queries            {len(trace.query_events)}")
    for q in trace.query_events:
        print(f"    {q.operation} {json.dumps(q.parameters, default=str)[:110]} -> {q.result_count} result(s)")
    # What the session recorded itself with record_context and record_action.
    print(f"  external contexts  {len(trace.external_contexts)}")
    for c in trace.external_contexts:
        print(f"    {c.label}: {c.summary} (source: {c.source})")
    print(f"  actions            {len(trace.tool_calls)}")
    for a in trace.tool_calls:
        print(f"    {a.tool_name}({json.dumps(a.arguments)}) -> {_short(a.result_summary)}")

    # Model usage from record_llm_call and your attributes appear here.
    meta = trace.session_metadata.model_dump(mode="json", exclude_none=True) if trace.session_metadata else {}
    print(f"  session metadata   {json.dumps(meta, default=str)[:400] if meta else '(empty)'}")
    print()


def _short(value: object, width: int = 70) -> str:
    """One line of at most ``width`` characters, or a marker for an empty field."""
    if value is None or value == "":
        return "(not stored)"
    text = " ".join(str(value).split())
    return text if len(text) <= width else text[: width - 1] + "…"


def _ms(value: float | None) -> str:
    return "duration not recorded" if value is None else f"{value:.0f} ms"


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    run_id = new_run_id()
    path = f"{PATH_PREFIX}/{run_id}/{CASE.id}"
    print(f"run id: {run_id}\n")
    # 1. Put the rule in memory.
    seed_rule(path)

    # 2. Solve the task in two separate sessions that end differently.
    bare_mem, bare_ref = bare_session(run_id, path)
    full_mem, full_ref = full_session(run_id, path)

    # 3. Fetch both traces and print them one after the other.
    describe("bare commit: commit_outcome(ref, outcome)", fetch_trace(bare_mem, bare_ref))
    describe("full commit: record_* calls, task_input, response_text, attributes", fetch_trace(full_mem, full_ref))


if __name__ == "__main__":
    # No options; this makes --help print the summary without running anything.
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    main()

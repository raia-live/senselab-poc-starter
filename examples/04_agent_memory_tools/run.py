"""04 - The model decides when to use memory.

In example 01 the harness retrieves and pastes the result into the prompt.
Here the model gets two tools, memory_search and memory_write, and chooses
when to call them. That shows whether the agent uses memory unprompted, as
well as whether memory helps.

    uv run python examples/04_agent_memory_tools/run.py
    uv run python examples/04_agent_memory_tools/run.py --case label-date
"""

from __future__ import annotations

import argparse
import json

from amfs import AgentMemory

from poc import RESULTS_DIR
from poc.cases import CASES, Case, by_id
from poc.llm import ToolRun, run_with_tools
from poc.memory import hosted, new_run_id

# ── CUSTOMIZE ───────────────────────────────────────────────────────────────
WRITER_ID = "poc-writer"
SOLVER_ID = "poc-solver"
PATH_PREFIX = "poc/tools"

# How many model turns one attempt may take, tool calls included.
MAX_STEPS = 6
SEARCH_LIMIT = 3

# What the model is told about each tool. Wording here changes how often the
# tools get used; it is the first thing to experiment with.
TOOLS = [
    {
        "name": "memory_search",
        "description": (
            "Search the team's shared memory for rules and notes left by colleagues. "
            "Use it before answering anything that might depend on a house rule."
        ),
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "What you want to know."}},
            "required": ["query"],
        },
    },
    {
        "name": "memory_write",
        "description": (
            "Save a rule or note to the team's shared memory so colleagues can find it later. "
            "Use it when you learn something a colleague would otherwise get wrong."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Short kebab-case name, e.g. rule-invoice-format."},
                "value": {"type": "string", "description": "The rule, general enough to reuse."},
            },
            "required": ["key", "value"],
        },
    },
]

# The only hint the model gets that memory exists.
SYSTEM = (
    "You work at Northwind Freight, which has its own house rules. You have access to the "
    "team's shared memory through tools. Do the task. Put the final answer alone on the last line."
)
SYSTEM_NO_TOOLS = (
    "You work at Northwind Freight, which has its own house rules. Do the task. "
    "Put the final answer alone on the last line."
)
# ────────────────────────────────────────────────────────────────────────────


# ── The code behind the two tools ─────────────────────────────────────────────


def memory_tools(mem: AgentMemory, path: str) -> dict:
    """The tool handlers for one agent on one case.

    The model supplies the query, the key and the value. The path is fixed
    here, by the harness, so the model cannot read or write another case.
    """

    def memory_search(query: str) -> str:
        # Runs when the model calls memory_search. The returned text is what
        # the model sees as the tool result.
        hits = mem.retrieve(query, entity_path=path, limit=SEARCH_LIMIT)
        if not hits:
            return "No results."
        return json.dumps([{"key": h.entry.key, "value": h.entry.value} for h in hits])

    def memory_write(key: str, value: str) -> str:
        # Runs when the model calls memory_write.
        mem.write(path, key, value, confidence=0.8)
        return f"Saved as {key}."

    # The dict keys must match the tool names in TOOLS.
    return {"memory_search": memory_search, "memory_write": memory_write}


# ── Agent A: attempt the task, then react to the feedback ─────────────────────


def agent_a(case: Case, path: str) -> dict:
    """Agent A attempts the task, is told why it was wrong, and may save a rule."""
    mem = hosted(WRITER_ID)
    handlers = memory_tools(mem, path)
    # Conversation 1: the model attempts the task with both tools available.
    attempt = run_with_tools(SYSTEM, case.teach_task, TOOLS, handlers, max_steps=MAX_STEPS)
    # Conversation 2: it sees its answer and the grader's feedback. Nothing
    # tells it to save a rule; whether it calls memory_write is its decision.
    debrief = run_with_tools(
        SYSTEM,
        f"Earlier you were given this task:\n{case.teach_task}\n\n"
        f"You answered:\n{attempt.text}\n\n"
        f"The grader replied:\n{case.feedback}\n\n"
        "Do whatever is useful with that, then reply with one line saying what you did.",
        TOOLS,
        handlers,
        max_steps=MAX_STEPS,
    )
    return {"calls": _calls(attempt) + _calls(debrief), "wrote": _names(debrief).count("memory_write")}


# ── Agent B: a new session, with tools and without ────────────────────────────


def agent_b_with_tools(case: Case, path: str) -> dict:
    """A fresh Agent B on a new instance of the task, with the same tools."""
    # A new memory object and a new conversation. The only way the rule can
    # reach this agent is a memory_search call.
    mem = hosted(SOLVER_ID)
    run = run_with_tools(SYSTEM, case.eval_task, TOOLS, memory_tools(mem, path), max_steps=MAX_STEPS)
    return {"calls": _calls(run), "answer": run.text, "passed": case.check(run.text)}


def agent_b_control(case: Case) -> dict:
    """The same model and task with no tools and no memory."""
    run = run_with_tools(SYSTEM_NO_TOOLS, case.eval_task, tools=[], handlers={})
    return {"calls": [], "answer": run.text, "passed": case.check(run.text)}


def _names(run: ToolRun) -> list[str]:
    return [call["name"] for call in run.calls]


def _calls(run: ToolRun) -> list[str]:
    """Tool calls as short strings, in the order the model made them."""
    return [f"{c['name']}({json.dumps(c['input'])[:80]})" for c in run.calls]


# ── Command line ──────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", help="run one case from poc/cases.py instead of all of them")
    args = parser.parse_args()
    cases = [by_id(args.case)] if args.case else CASES

    run_id = new_run_id()
    print(f"run id: {run_id}\n")
    rows = []
    for case in cases:
        # One path per case. All three agents below are tied to it.
        path = f"{PATH_PREFIX}/{run_id}/{case.id}"
        a = agent_a(case, path)
        b = agent_b_with_tools(case, path)
        control = agent_b_control(case)
        rows.append({"case": case.id, "expected": case.expected, "agent_a": a, "agent_b": b, "control": control})

        print(case.id)
        print(f"  Agent A        {a['calls'] or 'made no tool calls'}")
        print(f"  Agent B tools  {'PASS' if b['passed'] else 'FAIL'}  {b['calls'] or 'made no tool calls'}")
        print(f"  Agent B bare   {'PASS' if control['passed'] else 'FAIL'}\n")

    # Keep the full answers and tool calls for later inspection.
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"04_agent_memory_tools-{run_id}.json"
    out.write_text(json.dumps({"run_id": run_id, "cases": rows}, indent=2))
    print(f"full answers in {out.relative_to(RESULTS_DIR.parent)}")


if __name__ == "__main__":
    main()

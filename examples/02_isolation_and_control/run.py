"""02 - Keeping test cases apart, and what "reset" means.

Writes a different rule under two case paths, then shows what a retrieve
returns when it is scoped to one case, to the parent path, and to nothing.
No LLM calls.

    uv run python examples/02_isolation_and_control/run.py
"""

from __future__ import annotations

import argparse

from poc.memory import entry_ref, hosted, new_run_id, retrieve_until_found

# ── CUSTOMIZE ───────────────────────────────────────────────────────────────
WRITER_ID = "poc-writer"
READER_ID = "poc-solver"

# The path scheme: <prefix>/<run id>/<case>. Change it to match how you want
# to group memory; what matters is that each case has a path of its own.
PATH_PREFIX = "poc/isolation"

# One rule per case. The query below is about the second one.
RULES = {
    "case-1": "Invoice references are written INV/<year>/<CUSTOMER>-<number>, number padded to six digits.",
    "case-2": "Dates on shipping labels are written DDMMMYY in upper case, for example 03FEB26.",
}
QUERY = "How do I write a date on a shipping label?"
# ────────────────────────────────────────────────────────────────────────────


def write_rules(run_id: str) -> None:
    """One rule under each case's own path."""
    writer = hosted(WRITER_ID)
    for case, rule in RULES.items():
        entry = writer.write(f"{PATH_PREFIX}/{run_id}/{case}", "rule", rule, confidence=0.9)
        print(f"wrote {entry_ref(entry)}")
    print()


def show(label: str, expectation: str, refs: list[str]) -> None:
    print(f"{label}\n  expected: {expectation}\n  got:      {refs or 'nothing'}\n")


def retrieve_three_ways(run_id: str) -> None:
    """The same query, scoped to a case, to the parent, and not at all."""
    reader = hosted(READER_ID)
    case_2 = f"{PATH_PREFIX}/{run_id}/case-2"

    # 1. Scoped to one case. This is the form to use in an experiment.
    hits = retrieve_until_found(reader, QUERY, entity_path=case_2)
    show(
        f"retrieve(entity_path='{case_2}')",
        "case-2's rule and nothing from case-1",
        [entry_ref(h.entry) for h in hits],
    )

    # 2. Scoped to the parent. Paths match exactly; a parent is a different path.
    hits = reader.retrieve(QUERY, entity_path=f"{PATH_PREFIX}/{run_id}", limit=5)
    show(
        f"retrieve(entity_path='{PATH_PREFIX}/{run_id}')",
        "nothing, because matching is exact and nothing was written to the parent itself",
        [entry_ref(h.entry) for h in hits],
    )

    # 3. Not scoped. Everything this key can see is a candidate: other cases,
    #    other runs, and anything else in the account. This is the leak to avoid.
    hits = reader.retrieve(QUERY, limit=5)
    show(
        "retrieve() with no entity_path",
        "the best matches from the whole account, whatever they belong to",
        [entry_ref(h.entry) for h in hits],
    )


def a_new_run_is_empty() -> None:
    """There is no delete. A reset is a path nobody has written to."""
    fresh = f"{PATH_PREFIX}/{new_run_id()}/case-2"
    hits = hosted(READER_ID).retrieve(QUERY, entity_path=fresh, limit=5)
    show(
        f"retrieve(entity_path='{fresh}')  <- a new run id",
        "nothing: this is what a clean slate looks like",
        [entry_ref(h.entry) for h in hits],
    )


def main() -> None:
    run_id = new_run_id()
    print(f"run id: {run_id}\n")
    write_rules(run_id)
    retrieve_three_ways(run_id)
    a_new_run_is_empty()


if __name__ == "__main__":
    # No options; this makes --help print the summary without running anything.
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    main()

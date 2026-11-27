"""Three synthetic cases. Each hides a house rule that cannot be guessed.

A case has two tasks that need the same rule. Agent A meets ``teach_task``,
gets it wrong, and is told why (``feedback``). Agent B is graded on
``eval_task``, a different instance, so what has to survive the handoff is
the rule and not the answer.

The grader is deterministic: no LLM judges anything.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    id: str
    #: What Agent A is asked, and gets wrong.
    teach_task: str
    #: What the grader tells Agent A afterwards. This is the only place the
    #: rule is ever stated; Agent B never sees it except through memory.
    feedback: str
    #: What Agent B is asked.
    eval_task: str
    #: The one right answer to ``eval_task``.
    expected: str

    def check(self, answer: str) -> bool:
        """True when the last line of ``answer`` contains the expected value.

        Exact case, because two of the rules are about casing.
        """
        lines = [line.strip() for line in answer.strip().splitlines() if line.strip()]
        return bool(lines) and self.expected in lines[-1]


# The built-in cases, used by examples 01, 03, 04, 06 and 07. To use your
# own, edit or append to this list. Keep each rule arbitrary: if the model can
# guess it, the control arm passes and the experiment shows nothing.
# Examples 03 and 06 run the first case by default. Example 07 matches the
# keys in AMFS_API_KEYS_B_PER_CASE to these cases by position.
CASES: list[Case] = [
    Case(
        id="invoice-ref",
        teach_task="Write the invoice reference for customer Acme, invoice number 482, issued in 2026.",
        feedback=(
            "Wrong. Invoice references here are written INV/<year>/<CUSTOMER>-<number>, "
            "with the customer name in upper case and the number zero-padded to six digits. "
            "The right answer was INV/2026/ACME-000482."
        ),
        eval_task="Write the invoice reference for customer Globex, invoice number 97, issued in 2026.",
        expected="INV/2026/GLOBEX-000097",
    ),
    Case(
        id="label-date",
        teach_task="Write the delivery date 3 February 2026 as it goes on a shipping label.",
        feedback=(
            "Wrong. Dates on shipping labels are written DDMMMYY: two-digit day, three-letter "
            "month in upper case, two-digit year, no separators. The right answer was 03FEB26."
        ),
        eval_task="Write the delivery date 17 November 2026 as it goes on a shipping label.",
        expected="17NOV26",
    ),
    Case(
        id="ticket-queue",
        teach_task="A customer reports being charged twice, $40 too much. Which queue does the ticket go to?",
        feedback=(
            "Wrong. Billing disputes under $50 go to queue BX-7; disputes of $50 or more go to "
            "queue FIN-2. The right answer was BX-7."
        ),
        eval_task="A customer reports being charged twice, $120 too much. Which queue does the ticket go to?",
        expected="FIN-2",
    ),
]


def by_id(case_id: str) -> Case:
    """Look a case up by its id, for the --case option and CASE_ID settings."""
    for case in CASES:
        if case.id == case_id:
            return case
    raise SystemExit(f"No case named {case_id!r}. Known: {', '.join(c.id for c in CASES)}")

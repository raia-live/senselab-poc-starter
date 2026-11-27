"""06 - The same experiment with Claude Code, headless.

Claude Code reaches SenseLab through the SenseLab MCP server instead of the
Python SDK. Agent A is one `claude -p` run that saves a rule; Agent B is two
more runs on a new task, one with the MCP server (treatment) and one without
any MCP server (control). Afterwards the rule is read back with the Python
SDK, to show both routes reach the same memory.

Needs the `claude` CLI, `uvx`, and ANTHROPIC_API_KEY.

    uv run python examples/06_claude_code_headless/run.py
    uv run python examples/06_claude_code_headless/run.py --case invoice-ref
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile

from poc.cases import CASES, Case, by_id
from poc.memory import hosted, new_run_id

# ── CUSTOMIZE ───────────────────────────────────────────────────────────────
# Which case from poc/cases.py to run when --case is not given: the first
# one, or an id from that file in quotes. One case is three Claude Code runs.
CASE_ID = CASES[0].id
PATH_PREFIX = "poc/claude-code"

# The agent ids the MCP server reports to SenseLab for each run.
WRITER_ID = "poc-claude-writer"
SOLVER_ID = "poc-claude-solver"

# None uses Claude Code's default model. Otherwise e.g. "claude-sonnet-5-5".
CLAUDE_MODEL: str | None = None

# The name Claude Code knows the server by. Tool names are derived from it:
# mcp__<name>__<tool>.
MCP_NAME = "senselab"
WRITE_TOOL = f"mcp__{MCP_NAME}__amfs_write"
RETRIEVE_TOOL = f"mcp__{MCP_NAME}__amfs_retrieve"

# How long one `claude -p` run may take, in seconds. The first run also
# downloads the MCP server.
TIMEOUT = 300

WRITER_PROMPT = """\
You were given this task and got it wrong:
{task}

The grader replied:
{feedback}

Save the one rule a colleague would need to get any task of this kind right. Call the
amfs_write tool with entity_path "{path}", key "rule", and the rule as the value. The rule
must be general (not about this instance) and include a worked example. Then reply "saved".
"""
SOLVER_PROMPT_WITH_MEMORY = """\
You work at Northwind Freight, which has its own house rules. First call the amfs_retrieve
tool with entity_path "{path}" and a query describing the task, and use what it returns.
Then do the task. Put the final answer alone on the last line.

Task: {task}
"""
SOLVER_PROMPT_CONTROL = """\
You work at Northwind Freight, which has its own house rules. Do the task. Put the final
answer alone on the last line.

Task: {task}
"""
# ────────────────────────────────────────────────────────────────────────────


# ── Running Claude Code ───────────────────────────────────────────────────────


def mcp_config(agent_id: str | None) -> str:
    """The --mcp-config value: the SenseLab server, or no servers at all.

    Passed as a JSON string, so nothing is written to disk. The URL and key
    are ${VAR} references, which Claude Code is expected to fill in from its
    environment so the key stays off the command line. This expansion is
    untested; if the server fails to authenticate, put the values in directly.
    """
    # Control arm: an empty server list, so Claude Code has no SenseLab tools.
    if agent_id is None:
        return json.dumps({"mcpServers": {}})
    # Treatment arm: start the SenseLab MCP server with uvx and tell it which
    # service, key and agent id to use.
    return json.dumps(
        {
            "mcpServers": {
                MCP_NAME: {
                    "command": "uvx",
                    "args": ["amfs-mcp-server@latest"],
                    "env": {
                        "AMFS_HTTP_URL": "${AMFS_HTTP_URL}",
                        "AMFS_API_KEY": "${AMFS_API_KEY}",
                        "AMFS_AGENT_ID": agent_id,
                    },
                }
            }
        }
    )


def claude(prompt: str, *, agent_id: str | None, allowed_tool: str | None) -> dict:
    """One headless Claude Code run. Returns its JSON result."""
    command = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        # No CLAUDE.md, no auto-memory, no hooks, no plugins: nothing of
        # Claude Code's own can stand in for SenseLab. Requires ANTHROPIC_API_KEY.
        "--bare",
        # No built-in tools either (no Bash, no file access).
        "--tools",
        "",
        # Only the MCP servers named here; ignore the user's own MCP settings.
        "--strict-mcp-config",
        "--mcp-config",
        mcp_config(agent_id),
        "--no-session-persistence",
    ]
    # Let this run call one SenseLab tool without asking for permission.
    if allowed_tool:
        command += ["--allowedTools", allowed_tool]
    if CLAUDE_MODEL:
        command += ["--model", CLAUDE_MODEL]

    # An empty working directory, so there is no project for it to look at.
    with tempfile.TemporaryDirectory() as workdir:
        done = subprocess.run(
            command, cwd=workdir, env=os.environ.copy(), capture_output=True, text=True, timeout=TIMEOUT, check=False
        )
    # Stop on a failed process, then on an error reported inside the JSON.
    if done.returncode != 0:
        raise SystemExit(f"FAILED: claude exited {done.returncode}\n{done.stderr.strip() or done.stdout.strip()}")
    result = json.loads(done.stdout)
    if result.get("is_error"):
        raise SystemExit(f"FAILED: claude reported an error: {result.get('result')}")
    # result["result"] is Claude Code's final message as text.
    return result


# ── The three roles ───────────────────────────────────────────────────────────


def agent_a_writes(case: Case, path: str) -> None:
    """Claude Code saves the rule through the MCP server's amfs_write tool."""
    result = claude(
        WRITER_PROMPT.format(task=case.teach_task, feedback=case.feedback, path=path),
        agent_id=WRITER_ID,
        allowed_tool=WRITE_TOOL,
    )
    print(f"Agent A (Claude Code + MCP): {_last_line(result['result'])}  [{result.get('num_turns')} turns]")


def read_back_with_sdk(path: str) -> None:
    """The entry Claude Code wrote, read with the Python SDK."""
    # A plain SDK read of the path and key the prompt told Claude Code to use.
    entry = hosted("poc-solver").read(path, "rule")
    if entry is None:
        raise SystemExit(
            f"FAILED: nothing at {path}/rule. Claude Code did not call {WRITE_TOOL}, "
            "or saved under a different path or key."
        )
    print(f"Python SDK reads {path}/rule:\n  {entry.value}\n  written by {entry.provenance.agent_id}\n")


def agent_b(case: Case, path: str, *, with_memory: bool) -> bool:
    """A new Claude Code run on a new instance of the task."""
    # Treatment: the MCP server is loaded and amfs_retrieve is allowed.
    # Control: no MCP server and no tools.
    if with_memory:
        result = claude(
            SOLVER_PROMPT_WITH_MEMORY.format(task=case.eval_task, path=path),
            agent_id=SOLVER_ID,
            allowed_tool=RETRIEVE_TOOL,
        )
    else:
        result = claude(SOLVER_PROMPT_CONTROL.format(task=case.eval_task), agent_id=None, allowed_tool=None)
    # Grade Claude Code's final message with the checker in poc/cases.py.
    passed = case.check(result["result"])
    arm = "treatment (MCP server)" if with_memory else "control (no MCP server)"
    print(f"Agent B {arm:<24} {'PASS' if passed else 'FAIL'}  answered: {_last_line(result['result'])}")
    return passed


def _last_line(text: str) -> str:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    return lines[-1] if lines else "(no output)"


# ── Command line ──────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", default=CASE_ID, help="a case id from poc/cases.py")
    args = parser.parse_args()

    # Fail early, with a clear message, if a program or variable is missing.
    for tool in ("claude", "uvx"):
        if shutil.which(tool) is None:
            raise SystemExit(f"FAILED: `{tool}` is not on PATH.")
    for name in ("ANTHROPIC_API_KEY", "AMFS_HTTP_URL", "AMFS_API_KEY"):
        if not (os.environ.get(name) or "").strip():
            raise SystemExit(f"FAILED: {name} is not set. Add it to .env.")

    case = by_id(args.case)
    run_id = new_run_id()
    path = f"{PATH_PREFIX}/{run_id}/{case.id}"
    print(f"run id: {run_id}\n")

    # 1. Agent A saves the rule through MCP. 2. The SDK reads it back.
    # 3. Agent B without memory. 4. Agent B with memory.
    agent_a_writes(case, path)
    read_back_with_sdk(path)
    agent_b(case, path, with_memory=False)
    agent_b(case, path, with_memory=True)


if __name__ == "__main__":
    main()

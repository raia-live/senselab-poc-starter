# 06 - Claude Code, headless

The experiment from example 01 with Claude Code as the agent. Claude Code reaches SenseLab through the SenseLab MCP server, and the entries it writes are the same ones the Python SDK reads. The control arm is Claude Code with no MCP server.

## Before you run

- Example 00 prints `Connected.`
- `.env` has `ANTHROPIC_API_KEY`. An OpenAI key does not work here.
- The Claude Code CLI is installed: `npm install -g @anthropic-ai/claude-code`. Check with `claude --version`.
- `uvx` is installed. It comes with `uv`. Check with `uvx --version`.

## Run

From the repository root:

```bash
uv run python examples/06_claude_code_headless/run.py                     # the first case in poc/cases.py
uv run python examples/06_claude_code_headless/run.py --case invoice-ref  # another case
```

One case is three `claude -p` runs. The first run downloads the MCP server, so allow a few minutes.

## Output

This example has not been run yet. The format below comes from the code, with placeholders in angle brackets.

```
run id: <run id>

Agent A (Claude Code + MCP): saved  [<n> turns]
Python SDK reads poc/claude-code/<run id>/<case id>/rule:
  <the rule Claude Code wrote>
  written by poc-claude-writer

Agent B control (no MCP server)  <PASS or FAIL>  answered: <last line of the answer>
Agent B treatment (MCP server)   <PASS or FAIL>  answered: <last line of the answer>
```

How to read it:

- `Python SDK reads ...` confirms that the entry Claude Code wrote through MCP is visible to the Python SDK.
- The handoff worked when treatment passes and control fails.
- `FAILED: nothing at .../rule` means Claude Code did not call `amfs_write`, or used another path or key.

## How it works

1. `claude` runs one headless session with `claude -p <prompt> --output-format json` in an empty temporary directory. The flags remove every other source of memory:
   - `--bare` skips `CLAUDE.md`, auto-memory, hooks and plugins.
   - `--tools ""` disables the built-in tools.
   - `--strict-mcp-config --mcp-config <json>` loads only the MCP servers in that JSON.
   - `--allowedTools <tool>` permits the one SenseLab tool that run needs.
2. `mcp_config` builds the server definition: `uvx amfs-mcp-server@latest` with `AMFS_HTTP_URL`, `AMFS_API_KEY` and `AMFS_AGENT_ID` in its environment. For the control arm it returns an empty server list.
3. `agent_a_writes` gives Claude Code the task with the grader's feedback and tells it to save a rule with `amfs_write` under the case path.
4. `read_back_with_sdk` reads the same path and key with the Python SDK and prints who wrote it.
5. `agent_b` runs Claude Code on a second task, once with no MCP server and once with `amfs_retrieve` allowed.

## Edit

In the `CUSTOMIZE` block at the top of `run.py`:

| Setting | Meaning |
| --- | --- |
| `CASE_ID` | the case to run when `--case` is not given. The default is the first one in `poc/cases.py` |
| `PATH_PREFIX` | entries go under `<prefix>/<run id>/<case id>` |
| `WRITER_ID`, `SOLVER_ID` | the agent ids the MCP server reports to SenseLab |
| `CLAUDE_MODEL` | `None` uses Claude Code's default model. Set a model name to pin one |
| `MCP_NAME` | the server name. Tool names are `mcp__<name>__<tool>` |
| `WRITE_TOOL`, `RETRIEVE_TOOL` | the SenseLab tools a run may call |
| `TIMEOUT` | seconds one `claude -p` run may take |
| `WRITER_PROMPT`, `SOLVER_PROMPT_WITH_MEMORY`, `SOLVER_PROMPT_CONTROL` | the prompts |

The treatment prompt tells Claude Code to retrieve. Remove that sentence to test whether it retrieves unprompted.

## Adapt

- A different MCP transport: change what `mcp_config` returns.
- More SenseLab tools: pass a longer list to `--allowedTools` in `claude`.
- Your own Claude Code setup: remove `--bare` and `--tools ""` to run with your normal configuration. The control arm then stops being a clean comparison (see Gotchas).

## Gotchas

- `--bare` requires `ANTHROPIC_API_KEY`. A Claude subscription login is not used.
- Without `--bare` and `--tools ""`, `CLAUDE.md`, auto-memory and file access can carry the rule to Agent B and make the control arm pass.
- Without `--strict-mcp-config`, your own MCP servers are loaded too.
- The MCP config refers to the key as `${AMFS_API_KEY}` and expects Claude Code to fill it in from its environment. This is untested. If the server fails to authenticate, put the values into `mcp_config` directly.
- Tool names include the server name. If you rename `MCP_NAME`, the allowed tool names change with it.

# 06 - Claude Code, headless

The experiment from example 01 with Claude Code as the agent. Claude Code reaches SenseLab through the SenseLab MCP server, and the entries it writes are the same ones the Python SDK reads. The control arm is Claude Code with no MCP server.

## Run

Needs `AMFS_HTTP_URL`, `AMFS_API_KEY` and `ANTHROPIC_API_KEY` in `.env`, plus the `claude` CLI and `uvx` on your `PATH`.

```bash
uv run python examples/06_claude_code_headless/run.py
uv run python examples/06_claude_code_headless/run.py --case invoice-ref
```

One case is three `claude -p` runs. The first run downloads the MCP server.

## Output

This example has not been run yet, so there is no sample here. It prints four results: Agent A saving the rule, the Python SDK reading that rule back, Agent B's control run, and Agent B's treatment run.

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

- `WRITER_PROMPT`, `SOLVER_PROMPT_WITH_MEMORY`, `SOLVER_PROMPT_CONTROL`: the prompts. The treatment prompt tells Claude Code to retrieve. Remove that sentence to test whether it retrieves unprompted.
- `WRITE_TOOL`, `RETRIEVE_TOOL`: the SenseLab tools a run may call.
- `CLAUDE_MODEL`: pin a model.
- `WRITER_ID`, `SOLVER_ID`: the agent ids the MCP server reports.

## Adapt

To use a different MCP transport, change what `mcp_config` returns. To let Claude Code use more SenseLab tools, pass a longer list to `--allowedTools` in `claude`.

## Gotchas

- `--bare` requires `ANTHROPIC_API_KEY`. A Claude subscription login is not used.
- Without `--bare` and `--tools ""`, `CLAUDE.md`, auto-memory and file access can carry the rule to Agent B and make the control arm pass.
- Without `--strict-mcp-config`, your own MCP servers are loaded too.
- The MCP config refers to the key as `${AMFS_API_KEY}` and expects Claude Code to fill it in from its environment. This is untested. If the server fails to authenticate, put the values into `mcp_config` directly.
- Tool names include the server name. If you rename `MCP_NAME`, the allowed tool names change with it.

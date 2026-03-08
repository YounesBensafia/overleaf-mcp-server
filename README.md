# Overleaf MCP Server

An MCP server focused only on Overleaf projects (via Overleaf Git sync).

## Quick Start

```bash
git clone https://github.com/younesbensafia/overleaf-mcp-server.git
cd overleaf-mcp-server

uv sync

# Required environment
OVERLEAF_TOKEN=your_git_token \
PROJECT_ID=your_project_id \
PYTHONPATH=. \
uv run src/main.py
```

## Environment

`.env` example:

```env
OVERLEAF_TOKEN=your_git_token
PROJECT_ID=your_project_id
# Optional local clone dir:
OVERLEAF_REPO_DIR=/tmp/overleaf_repos
```

Notes:
- `OVERLEAF_TOKEN` is required.
- `project_id` can be passed per tool call, or use default `PROJECT_ID`.
- Overleaf Git access requires a plan that supports Git integration.

## Claude Desktop Setup

Add to `~/.config/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "overleaf": {
      "command": "uv",
      "args": ["--directory", "/path/to/overleaf-mcp-server", "run", "src/main.py"],
      "env": {
        "PYTHONPATH": ".",
        "OVERLEAF_TOKEN": "your_git_token",
        "PROJECT_ID": "your_project_id"
      }
    }
  }
}
```

## Tools

| Tool | Description |
|------|-------------|
| `list_files` | Pull and list files from Overleaf project |
| `read_file` | Read file content |
| `write_file` | Update file, commit, and push to Overleaf |
| `sync_project` | Force a pull/sync from Overleaf |

## Requirements

- Python 3.10+
- `uv` package manager

## License

MIT - See [LICENSE](LICENSE)

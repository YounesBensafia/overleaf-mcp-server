# LaTeX MCP Server

A Model Context Protocol (MCP) server for AI-assisted LaTeX editing. Works with **any local LaTeX project** or syncs with Overleaf (Premium).

**Instead of copy-pasting between ChatGPT and your editor, the AI directly reads and edits your LaTeX documents.**

## Quick Start

```bash
# Clone
git clone https://github.com/younesbensafia/overleaf-mcp-server.git
cd overleaf-mcp-server

# Install
uv sync

# Run (point to your LaTeX project)
PROJECT_PATH=/path/to/your/thesis PYTHONPATH=. uv run src/main.py
```

## Who Is This For?

| User | Use Case |
|------|----------|
| PhD students | AI helps write/edit thesis chapters |
| Researchers | Quick paper drafting and error fixing |
| Students | Homework and assignments |
| Anyone | Any LaTeX document |

## Features

- **List Files** - See all files in your project
- **Read Files** - AI reads your `.tex` content
- **Write Files** - AI creates or edits files
- **Compile** - Run `pdflatex` and get errors
- **Get Outline** - Extract sections/chapters structure

## Modes

### Local Mode (Default) - Works for Everyone
```env
MODE=local
PROJECT_PATH=/home/user/my_thesis
```

### Overleaf Mode (Optional) - Requires Premium
```env
MODE=overleaf
OVERLEAF_TOKEN=your_git_token
PROJECT_ID=your_project_id
```

## Example Workflow

```
You: "Read main.tex and improve the introduction"
AI: [calls read_file] → reads content → suggests changes

You: "Add a new section about neural networks"
AI: [calls write_file] → adds the section

You: "Compile and check for errors"
AI: [calls compile] → sees errors → [calls write_file] → fixes them
```

## Claude Desktop Setup

Add to `~/.config/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "latex": {
      "command": "uv",
      "args": ["--directory", "/path/to/overleaf-mcp-server", "run", "src/main.py"],
      "env": {
        "PYTHONPATH": ".",
        "PROJECT_PATH": "/path/to/your/latex/project"
      }
    }
  }
}
```

## Tools

| Tool | Description |
|------|-------------|
| `list_files` | List all files in project |
| `read_file` | Read file content |
| `write_file` | Create or update file |
| `compile` | Run pdflatex, return errors |
| `get_outline` | Get document structure |

## Requirements

- Python 3.10+
- `uv` package manager
- `pdflatex` (for compilation) - `sudo apt install texlive-latex-base`

## License

MIT - See [LICENSE](LICENSE)

# Overleaf MCP Server

This is a Model Context Protocol (MCP) server that provides integration with Overleaf projects, allowing AI assistants to interact with your LaTeX documents.

**Instead of copy-pasting between ChatGPT and Overleaf, the AI directly edits your document and pushes changes to your project.**

## Why Use This?

| User | Use Case |
|------|----------|
| PhD students | Thesis writing with AI assistance |
| Researchers | Quick paper drafting and editing |
| Developers | Automating LaTeX documentation |
| Teams | Collaborative editing via AI |

### Example Workflow
```
You: "Read my main.tex and suggest improvements to the introduction"
Claude: [calls read_latex_file] → reads content → gives feedback

You: "Add a new section about neural networks after the introduction"  
Claude: [calls read_latex_file, then write_latex_file] → inserts the section

You: "Compile and check for errors"
Claude: [calls compile_latex] → sees errors → [calls write_latex_file] → fixes them
```

## Features

- **Fetch Project Files**: List all files within an Overleaf project.
- **Read LaTeX Files**: Retrieve the content of specific `.tex` files.
- **Write LaTeX Files**: Update or create files in your project.
- **LaTeX Parsing**: Extract sections and equations from LaTeX documents (powered by `pylatexenc`).
- **Trigger Compilation**: Compile and get error logs for automated fixing.
- **Mock Mode**: Test locally without an Overleaf premium account.

## Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/younesbensafia/overleaf-mcp-server.git
   cd overleaf-mcp-server
   ```

2. **Configure Environment Variables**:
   Create a `.env` file in the root directory:
   ```env
   OVERLEAF_TOKEN=your_git_token_here
   PROJECT_ID=your_project_id
   MOCK_MODE=false
   ```
   
   > **Note**: Git integration requires an Overleaf premium account. Set `MOCK_MODE=true` for local testing.

3. **Install Dependencies**:
   ```bash
   uv sync
   ```

## Usage

Run the server via stdio:
```bash
PYTHONPATH=. uv run src/main.py
```

### Mock Mode (for testing without premium)
```bash
MOCK_MODE=true PYTHONPATH=. uv run src/main.py
```

## Tools Provided

- `fetch_project_files(project_id)` - List all files in a project
- `read_latex_file(project_id, file_path)` - Read file content
- `write_latex_file(project_id, file_path, content)` - Update or create files
- `compile_latex(project_id)` - Compile and get status/errors
- `get_errors(project_id)` - Get compilation errors for fixing

## Claude Desktop Configuration

Add this to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "overleaf": {
      "command": "uv",
      "args": ["--directory", "/path/to/overleaf-mcp-server", "run", "src/main.py"],
      "env": {
        "PYTHONPATH": ".",
        "OVERLEAF_TOKEN": "your_token",
        "PROJECT_ID": "your_project_id"
      }
    }
  }
}
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

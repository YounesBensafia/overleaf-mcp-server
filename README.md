# Overleaf MCP Server

This is a Model Context Protocol (MCP) server that provides integration with Overleaf projects, allowing AI assistants to interact with your LaTeX documents.

## Features

- **Fetch Project Files**: List all files within an Overleaf project.
- **Read LaTeX Files**: Retrieve the content of specific `.tex` files.
- **LaTeX Parsing**: Extract sections and equations from LaTeX documents (powered by `pylatexenc`).
- **Trigger Compilation**: Prompt Overleaf to compile the project.

## Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/younesbensafia/overleaf-mcp-server.git
   cd overleaf-mcp-server
   ```

2. **Configure Environment Variables**:
   Create a `.env` file in the root directory:
   ```env
   OVERLEAF_TOKEN=your_token_here
   OVERLEAF_BASE_URL=https://www.overleaf.com
   PROJECT_ID=your_default_project_id
   ```

3. **Install Dependencies**:
   ```bash
   pip install .
   ```

## Usage

Run the server via stdio:
```bash
python src/main.py
```

## Tools Provided

- `fetch_project_files(project_id)`
- `read_latex_file(project_id, file_path)`
- `compile_latex(project_id)`

## License

MIT

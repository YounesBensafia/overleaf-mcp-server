import asyncio
from mcp.server import Server
import mcp.types as types
from src.overleaf_client import OverleafClient

client = OverleafClient()
server = Server("overleaf-mcp-server")

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="fetch_project_files",
            description="Fetch list of files from an Overleaf project",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "The Overleaf project ID"}
                },
                "required": ["project_id"]
            }
        ),
        types.Tool(
            name="read_latex_file",
            description="Read the content of a LaTeX file in an Overleaf project",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "The Overleaf project ID"},
                    "file_path": {"type": "string", "description": "Path to the file relative to project root"}
                },
                "required": ["project_id", "file_path"]
            }
        ),
        types.Tool(
            name="compile_latex",
            description="Trigger compilation for an Overleaf project and return compilation result status and errors",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "The Overleaf project ID"}
                },
                "required": ["project_id"]
            }
        ),
        types.Tool(
            name="get_errors",
            description="Get the list of errors from the last compilation for a project",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "The Overleaf project ID"}
                },
                "required": ["project_id"]
            }
        ),
        types.Tool(
            name="write_latex_file",
            description="Update the content of a LaTeX file in an Overleaf project",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "The Overleaf project ID"},
                    "file_path": {"type": "string", "description": "Path to the file relative to project root"},
                    "content": {"type": "string", "description": "New content for the file"}
                },
                "required": ["project_id", "file_path", "content"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "fetch_project_files":
        project_id = arguments["project_id"]
        files = client.fetch_project_files(project_id)
        return [types.TextContent(type="text", text=str(files))]
    
    elif name == "read_latex_file":
        project_id = arguments["project_id"]
        file_path = arguments["file_path"]
        content = client.read_file(project_id, file_path)
        return [types.TextContent(type="text", text=content)]

    elif name == "write_latex_file":
        project_id = arguments["project_id"]
        file_path = arguments["file_path"]
        content = arguments["content"]
        success = client.write_file(project_id, file_path, content)
        if success:
            return [types.TextContent(type="text", text=f"Successfully updated {file_path}")]
        else:
            return [types.TextContent(type="text", text=f"Failed to update {file_path}")]

    elif name == "compile_latex":
        project_id = arguments["project_id"]
        result = client.compile_project(project_id)
        # Return structured info for the AI to fix errors
        import json
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "get_errors":
        project_id = arguments["project_id"]
        result = client.get_compilation_logs(project_id)
        # Extract only errors for clarity
        errors = result.get("errors", [])
        return [types.TextContent(type="text", text=f"Found {len(errors)} errors.\n{json.dumps(errors, indent=2)}")]
    
    else:
        raise ValueError(f"Unknown tool: {name}")

async def run_server():
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

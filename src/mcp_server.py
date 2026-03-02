import asyncio
import json
from mcp.server import Server
import mcp.types as types
from src.latex_client import LaTeXClient

client = LaTeXClient()
server = Server("latex-mcp-server")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="list_files",
            description="List all files in the LaTeX project",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Overleaf project ID (only needed in overleaf mode)"
                    }
                },
                "required": []
            }
        ),
        types.Tool(
            name="read_file",
            description="Read the content of a file in the LaTeX project",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file (e.g., 'main.tex', 'chapters/intro.tex')"
                    },
                    "project_id": {
                        "type": "string",
                        "description": "Overleaf project ID (only needed in overleaf mode)"
                    }
                },
                "required": ["file_path"]
            }
        ),
        types.Tool(
            name="write_file",
            description="Create or update a file in the LaTeX project",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file (e.g., 'main.tex', 'chapters/intro.tex')"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file"
                    },
                    "project_id": {
                        "type": "string",
                        "description": "Overleaf project ID (only needed in overleaf mode)"
                    }
                },
                "required": ["file_path", "content"]
            }
        ),
        types.Tool(
            name="compile",
            description="Compile the LaTeX project and return status/errors",
            inputSchema={
                "type": "object",
                "properties": {
                    "main_file": {
                        "type": "string",
                        "description": "Main .tex file to compile (default: main.tex)"
                    },
                    "project_id": {
                        "type": "string",
                        "description": "Overleaf project ID (only needed in overleaf mode)"
                    }
                },
                "required": []
            }
        ),
        types.Tool(
            name="get_outline",
            description="Get the document structure (sections, chapters, etc.)",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Overleaf project ID (only needed in overleaf mode)"
                    }
                },
                "required": []
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    project_id = arguments.get("project_id")
    
    try:
        if name == "list_files":
            files = client.list_files(project_id)
            return [types.TextContent(type="text", text=json.dumps(files, indent=2))]
        
        elif name == "read_file":
            file_path = arguments["file_path"]
            content = client.read_file(file_path, project_id)
            return [types.TextContent(type="text", text=content)]
        
        elif name == "write_file":
            file_path = arguments["file_path"]
            content = arguments["content"]
            result = client.write_file(file_path, content, project_id)
            return [types.TextContent(type="text", text=result)]
        
        elif name == "compile":
            main_file = arguments.get("main_file", "main.tex")
            result = client.compile_latex(main_file, project_id)
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
        
        elif name == "get_outline":
            outline = client.get_project_outline(project_id)
            return [types.TextContent(type="text", text=json.dumps(outline, indent=2))]
        
        else:
            raise ValueError(f"Unknown tool: {name}")
            
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {str(e)}")]


async def run_server():
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

import asyncio
import json
from mcp.server import Server
import mcp.types as types
from src.overleaf_client import OverleafClient

client = OverleafClient()
server = Server("overleaf-mcp-server")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="list_files",
            description="List all files in the Overleaf project",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Overleaf project ID (optional if PROJECT_ID is configured)"
                    }
                },
                "required": []
            }
        ),
        types.Tool(
            name="read_file",
            description="Read the content of a file in the Overleaf project",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file in the Overleaf project"
                    },
                    "project_id": {
                        "type": "string",
                        "description": "Overleaf project ID (optional if PROJECT_ID is configured)"
                    }
                },
                "required": ["file_path"]
            }
        ),
        types.Tool(
            name="write_file",
            description="Create or update a file in the Overleaf project",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file in the Overleaf project"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file"
                    },
                    "project_id": {
                        "type": "string",
                        "description": "Overleaf project ID (optional if PROJECT_ID is configured)"
                    }
                },
                "required": ["file_path", "content"]
            }
        ),
        types.Tool(
            name="sync_project",
            description="Pull latest changes from Overleaf",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Overleaf project ID (optional if PROJECT_ID is configured)"
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
        
        elif name == "sync_project":
            project_path = client.ensure_repo(project_id)
            return [types.TextContent(type="text", text=f"Synchronized Overleaf project at: {project_path}")]
        
        else:
            raise ValueError(f"Unknown tool: {name}")
            
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {str(e)}")]


async def run_server():
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

import asyncio
import json

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from config.config import config
from src.overleaf_client import OverleafClient

mcp = FastMCP("overleaf-mcp-server")
client = OverleafClient()

READ_ONLY = ToolAnnotations(readOnlyHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True)


async def _run(fn, *args):
    try:
        return await asyncio.to_thread(fn, *args)
    except (ValueError, FileNotFoundError, UnicodeDecodeError) as e:
        msg = str(e)
        if config.OVERLEAF_TOKEN:
            msg = msg.replace(config.OVERLEAF_TOKEN, "***")
        raise RuntimeError(msg) from None


@mcp.tool(annotations=READ_ONLY)
async def list_files(project_id: str | None = None) -> str:
    files = await _run(client.list_files, project_id)
    return json.dumps(files, indent=2)


@mcp.tool(annotations=READ_ONLY)
async def read_file(file_path: str, project_id: str | None = None) -> str:
    return await _run(client.read_file, file_path, project_id)


@mcp.tool(annotations=WRITE)
async def write_file(file_path: str, content: str, project_id: str | None = None) -> str:
    return await _run(client.write_file, file_path, content, project_id)


@mcp.tool(annotations=WRITE)
async def sync_project(project_id: str | None = None) -> str:
    await _run(client.ensure_repo, project_id)
    return "Synchronized Overleaf project"


if __name__ == "__main__":
    mcp.run()
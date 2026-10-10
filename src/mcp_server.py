import asyncio
import json
from collections.abc import Callable
from functools import lru_cache
from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

if TYPE_CHECKING:
    from src.overleaf_client import OverleafClient

mcp = FastMCP("overleaf-mcp-server")


@lru_cache(maxsize=1)
def get_client() -> "OverleafClient":
    from src.overleaf_client import OverleafClient

    return OverleafClient()


READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True)
SYNC = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


async def _run[**P, T](fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(get_client().scrub(f"{type(e).__name__}: {e}")) from None


@mcp.tool(annotations=READ_ONLY)
async def list_files(project_id: str | None = None) -> str:
    """Synchronize and list visible files in an Overleaf project."""
    files = await _run(get_client().list_files, project_id)
    return json.dumps(files, indent=2)


@mcp.tool(annotations=READ_ONLY)
async def read_file(
    file_path: str,
    project_id: str | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> str:
    """Read a UTF-8 text file, optionally selecting a bounded range of lines."""
    from config.config import config

    if offset < 0:
        raise ValueError("offset must be non-negative.")
    if limit is not None and not 0 < limit <= config.MAX_READ_LINES:
        raise ValueError(f"limit must be between 1 and {config.MAX_READ_LINES}.")
    return await _run(get_client().read_file, file_path, project_id, offset, limit)


@mcp.tool(annotations=WRITE)
async def write_file(file_path: str, content: str, project_id: str | None = None) -> str:
    """Overwrite a UTF-8 text file, commit the change, and push it to Overleaf."""
    return await _run(get_client().write_file, file_path, content, project_id)


@mcp.tool(annotations=SYNC)
async def sync_project(project_id: str | None = None) -> str:
    """Refresh the local project cache from Overleaf without changing the remote."""
    await _run(get_client().ensure_repo, project_id)
    return "Synchronized Overleaf project"


if __name__ == "__main__":
    mcp.run()

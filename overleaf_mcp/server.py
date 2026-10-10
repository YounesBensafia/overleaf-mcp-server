import asyncio
import json
import sys
from collections.abc import Callable
from functools import lru_cache
from typing import TYPE_CHECKING, Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field, ValidationError

from .constants import MAX_READ_LINES

if TYPE_CHECKING:
    from .client import OverleafClient

mcp = FastMCP("overleaf-mcp-server")


@lru_cache(maxsize=1)
def get_client() -> "OverleafClient":
    from .client import OverleafClient

    return OverleafClient()


READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=True,
)
EDIT = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True)
SYNC = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


async def _run[**P, T](fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except RuntimeError as e:
        text = str(e)
    except Exception as e:
        text = f"{type(e).__name__}: {e}"
    raise RuntimeError(get_client().scrub(text)) from None


@mcp.tool(annotations=READ_ONLY)
async def list_files(project_id: str | None = None) -> str:
    """Synchronize and list visible files in an Overleaf project."""
    files = await _run(get_client().list_files, project_id)
    return json.dumps(files, indent=2)


@mcp.tool(annotations=READ_ONLY)
async def read_file(
    file_path: str,
    project_id: str | None = None,
    offset: Annotated[int, Field(ge=0)] = 0,
    limit: Annotated[int | None, Field(ge=1, le=MAX_READ_LINES)] = None,
) -> str:
    """Read a UTF-8 text file, optionally selecting a bounded range of lines."""
    return await _run(get_client().read_file, file_path, project_id, offset, limit)


@mcp.tool(annotations=WRITE)
async def write_file(file_path: str, content: str, project_id: str | None = None) -> str:
    """Overwrite the complete UTF-8 text file, commit the change, and push it to Overleaf."""
    return await _run(get_client().write_file, file_path, content, project_id)


@mcp.tool(annotations=EDIT)
async def edit_file(
    file_path: str,
    old_text: str,
    new_text: str,
    project_id: str | None = None,
) -> str:
    """Replace exactly one matching text range in a UTF-8 file and push the result."""
    return await _run(get_client().edit_file, file_path, old_text, new_text, project_id)


@mcp.tool(annotations=SYNC)
async def sync_project(project_id: str | None = None) -> str:
    """Refresh the local project cache from Overleaf without changing the remote."""
    await _run(get_client().ensure_repo, project_id)
    return "Synchronized Overleaf project"


def main() -> None:
    """Run the Overleaf MCP server over stdio."""
    try:
        get_client()
    except ValidationError as error:
        missing = [
            ".".join(str(part) for part in detail["loc"])
            for detail in error.errors()
            if detail["type"] == "missing"
        ]
        message = "Missing configuration: " + ", ".join(missing or ["invalid values"])
        print(message, file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print(f"Failed to initialize Overleaf client: {type(error).__name__}", file=sys.stderr)
        sys.exit(1)
    mcp.run()


if __name__ == "__main__":
    main()
